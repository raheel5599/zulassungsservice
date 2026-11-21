#!/usr/bin/env bash
set -euo pipefail
old=tariq-websites
new=tariq-frontend
caddy=fahrschulpilot-caddy-1
volume=tariq-websites-public

if [[ "$(docker inspect --format '{{.State.Running}}' "$new" 2>/dev/null || true)" == true ]]; then
  echo 'tariq-frontend läuft bereits.'
  exit 0
fi

test "$(docker inspect --format '{{.State.Running}}' "$old")" = true
test "$(docker inspect --format '{{len .Mounts}}' "$old")" = 1
test "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/srv/public-sites"}}{{.Name}}{{end}}{{end}}' "$old")" = "$volume"
test "$(docker inspect --format '{{len .HostConfig.PortBindings}}' "$old")" = 0
for network in fahrschulpilot_web office_backend; do
  docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$old" | grep -Fxq "$network"
done
test "$(docker inspect --format '{{len .NetworkSettings.Networks}}' "$old")" = 2
image=$(docker inspect --format '{{.Image}}' "$old")
docker image inspect "$image" >/dev/null

ready() {
  local domain
  for domain in app.tariq-living.de fahrschul-pilot.de tariq-fahrdienst.de tariq-taxizentrale.de zulassung.tariq-itconsulting.de; do
    docker exec "$caddy" wget -qO /dev/null --header "Host: $domain" "http://$old/" || return 1
  done
  for domain in tariq-fahrdienst.de tariq-taxizentrale.de zulassung.tariq-itconsulting.de; do
    docker exec "$caddy" wget -qO- --header "Host: $domain" "http://$new/api/health" |
      grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' || return 1
  done
}

docker create --name "$new" --restart unless-stopped --network fahrschulpilot_web \
  --network-alias "$old" --mount "type=volume,src=$volume,dst=/srv/public-sites" "$image" >/dev/null
rollback() {
  docker rm -f "$new" >/dev/null 2>&1 || true
  docker start "$old" >/dev/null
}
if ! docker network connect office_backend "$new" || ! docker stop "$old" >/dev/null ||
   ! docker start "$new" >/dev/null; then
  rollback
  exit 1
fi
for attempt in {1..8}; do
  if ready; then
    echo 'tariq-frontend aktiv. Alle fünf Webseiten und drei API-Pfade bestätigt.'
    exit 0
  fi
  sleep 2
done
echo 'Frontend-Healthcheck fehlgeschlagen. Stelle bisherigen Container wieder her.' >&2
rollback
exit 1
