#!/usr/bin/env bash
set -Eeuo pipefail

web=tariq-frontend
if ! docker container inspect "$web" >/dev/null 2>&1; then
  web=tariq-websites
fi
caddy=fahrschulpilot-caddy-1
domain=zulassung.tariq-itconsulting.de
volume=tariq-websites-public
root=/srv/public-sites
site_dir=$(realpath "${1:?Build-Verzeichnis fehlt}")
test -s "$site_dir/index.html"
stamp=$(date -u +%Y%m%d%H%M%S%N)
work=$(mktemp -d)
preview="tariq-websites-zulassung-check-$stamp"
previous="tariq-websites-before-zulassung-$stamp"
trap 'docker rm -f "$preview" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

mount=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/srv/public-sites"}}{{.Name}}{{end}}{{end}}' "$web")
[[ "$mount" == "$volume" ]]
docker network inspect office_backend >/dev/null
cfg=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$caddy")
test -w "$cfg"

cp "$cfg" "$work/original"
python3 - "$work/original" "$work/candidate" <<'PY'
from pathlib import Path
import re, sys
original = Path(sys.argv[1]).read_text()
pattern = r'(?ms)^zulassung\.tariq-itconsulting\.de[ \t]*\{\n.*?^\}'
blocks = list(re.finditer(pattern, original))
if len(blocks) != 1:
    raise SystemExit("Zulassungsroute nicht eindeutig gefunden.")
block = blocks[0]
old = "reverse_proxy tariq-zulassung-office:8080"
new = "reverse_proxy tariq-websites:80"
if block[0].count(old) == 1:
    replacement = block[0].replace(old, new)
elif block[0].count(new) == 1:
    replacement = block[0]
else:
    raise SystemExit("Unbekanntes Ziel der Zulassungsroute.")
Path(sys.argv[2]).write_text(original[:block.start()] + replacement + original[block.end():])
PY

release=".zulassung-$stamp"
docker exec "$web" mkdir "$root/$release"
docker cp "$site_dir/." "$web:$root/$release/"
docker exec "$web" test -s "$root/$release/index.html"

if ! docker exec "$web" test -f /etc/nginx/conf.d/tariq-zulassung.conf; then
  image=$(docker inspect --format '{{.Image}}' "$web")
  base="tariq-websites-base:zulassung-$stamp"
  next="tariq-websites:zulassung-$stamp"
  docker image tag "$image" "$base"
  mkdir "$work/build"
  cp nginx.shared.conf "$work/build/tariq-zulassung.conf"
  printf 'FROM %s\nCOPY tariq-zulassung.conf /etc/nginx/conf.d/\nRUN nginx -t\n' "$base" > "$work/build/Dockerfile"
  docker build -t "$next" "$work/build"

  docker create --name "$preview" --network fahrschulpilot_web \
    --mount "type=volume,src=$volume,dst=$root,readonly" "$next" >/dev/null
  docker network connect office_backend "$preview"
  docker start "$preview" >/dev/null
  for vhost in app.tariq-living.de fahrschul-pilot.de tariq-fahrdienst.de tariq-taxizentrale.de; do
    docker exec "$caddy" wget -qO /dev/null --header "Host: $vhost" "http://$preview/"
  done
  docker exec "$caddy" wget -qO- --header "Host: $domain" "http://$preview/api/health" |
    grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'

  docker stop "$web" >/dev/null
  docker rename "$web" "$previous" || { docker start "$web" >/dev/null; exit 1; }
  if ! docker create --name "$web" --restart unless-stopped --network fahrschulpilot_web --network-alias tariq-websites \
       --mount "type=volume,src=$volume,dst=$root" "$next" >/dev/null ||
     ! docker network connect office_backend "$web" ||
     ! docker start "$web" >/dev/null; then
    docker rm -f "$web" >/dev/null 2>&1 || true
    docker rename "$previous" "$web"
    docker start "$web"
    exit 1
  fi
fi

prior_release=$(docker exec "$web" readlink "$root/$domain" || true)
docker exec "$web" sh -eu -c '
  cd "$1"
  test ! -e "$2" || test -L "$2"
  ln -s "$3" "$3-link"
  mv -Tf "$3-link" "$2"
' sh "$root" "$domain" "$release"
if ! docker exec "$caddy" wget -qO- --header "Host: $domain" "http://$web/" > "$work/shared.html" ||
   ! cmp "$site_dir/index.html" "$work/shared.html" ||
   ! docker exec "$caddy" wget -qO- --header "Host: $domain" "http://$web/api/health" |
      grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
  if [[ -n "$prior_release" ]]; then
    docker exec "$web" sh -eu -c 'cd "$1"; ln -s "$3" "$4-rollback"; mv -Tf "$4-rollback" "$2"' \
      sh "$root" "$domain" "$prior_release" "$release"
  fi
  exit 1
fi

if ! cmp -s "$work/candidate" "$work/original"; then
  docker exec -i "$caddy" sh -c 'cat > /tmp/zulassung-shared.caddy; caddy validate --config /tmp/zulassung-shared.caddy --adapter caddyfile' < "$work/candidate"
  cmp -s "$work/original" "$cfg" || { echo 'Caddyfile wurde parallel verändert.' >&2; exit 1; }
  backup="$cfg.before-zulassung-shared-$stamp"
  cp -p "$cfg" "$backup"
  cat "$work/candidate" > "$cfg"
  if ! docker restart "$caddy" >/dev/null ||
     ! curl -fsS --retry 8 --retry-all-errors --retry-delay 2 --max-time 8 --resolve "$domain:443:127.0.0.1" "https://$domain/api/health" -o /dev/null; then
    cat "$backup" > "$cfg"
    docker restart "$caddy" >/dev/null
    exit 1
  fi
fi

echo 'Zulassungsoberfläche und API im gemeinsamen Webseiten-Container geprüft.'
