#!/usr/bin/env bash
set -euo pipefail
caddy_container=fahrschulpilot-caddy-1
domain=zulassung.tariq-itconsulting.de
caddy_source=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$caddy_container")
if [ -z "$caddy_source" ]; then
  caddy_dir=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}' "$caddy_container")
  if [ -n "$caddy_dir" ]; then caddy_source="$caddy_dir/Caddyfile"; fi
fi
test -f "$caddy_source" || { echo "Caddyfile mount could not be resolved"; exit 1; }
test -w "$caddy_source" || { echo "Caddyfile is not writable by the deploy user: $caddy_source"; exit 1; }
candidate=$(mktemp)
trap 'rm -f "$candidate"' EXIT
python3 - "$caddy_source" "$candidate" <<'PY'
import pathlib,sys,re
source=pathlib.Path(sys.argv[1]).read_text()
domain="zulassung.tariq-itconsulting.de"
block='''zulassung.tariq-itconsulting.de {
  encode zstd gzip
  header {
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    Referrer-Policy "strict-origin-when-cross-origin"
    -Server
  }
  reverse_proxy tariq-zulassung-office:8080
}
'''
# Remove only the exact obsolete block previously managed by this script.
obsolete=block.replace("zulassung.tariq-itconsulting.de","zulassung.tariqit-consulting.de")
source=source.replace(obsolete,"")
if re.search(r'(?m)^\s*zulassung\.tariq-itconsulting\.de\s*\{',source):
    if "reverse_proxy tariq-zulassung-office:8080" not in source:
        raise SystemExit("Existing domain route differs; refusing to overwrite it")
    pathlib.Path(sys.argv[2]).write_text(source)
else:
    pathlib.Path(sys.argv[2]).write_text(source.rstrip()+"\n\n"+block)
PY
docker exec -i "$caddy_container" sh -c 'cat > /tmp/tariq-caddy-candidate; caddy validate --config /tmp/tariq-caddy-candidate --adapter caddyfile' < "$candidate"
if ! cmp -s "$candidate" "$caddy_source"; then
  backup="$caddy_source.before-zulassung-$(date +%Y%m%d%H%M%S)"
  cp -p "$caddy_source" "$backup"
  # Preserve the inode used by Docker's existing file bind mount.
  cat "$candidate" > "$caddy_source"
  if ! docker restart "$caddy_container"; then
    cat "$backup" > "$caddy_source"
    docker restart "$caddy_container"
    exit 1
  fi
fi
echo "Checking HTTPS for $domain"
for attempt in $(seq 1 8); do
  if curl -fSs --connect-timeout 5 --max-time 10 --resolve "$domain:443:127.0.0.1" "https://$domain/" -o /dev/null; then
    echo "HTTPS Office route verified successfully"
    exit 0
  fi
  sleep 5
done
echo "Route configured, but HTTPS could not be verified. Check DNS and certificate issuance."
docker logs --since 3m "$caddy_container" 2>&1 | tail -n 35
exit 1
