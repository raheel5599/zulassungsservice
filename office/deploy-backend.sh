#!/usr/bin/env bash
set -euo pipefail
container=office-api-1
previous="$container-before-backend-$(date -u +%Y%m%d%H%M%S)"
backend=(docker compose -f compose.backend.yml)
project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")
case "$project" in
  office|tariq-backend) ;;
  *) echo 'Unerwartetes Compose-Projekt der Zulassungs-API.' >&2; exit 1 ;;
esac
test "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "$container")" = office_portal_data
"${backend[@]}" config --quiet
"${backend[@]}" build zulassung-api
if [[ "$project" == office ]]; then
  docker stop "$container" >/dev/null
  docker rename "$container" "$previous" || { docker start "$container" >/dev/null; exit 1; }
fi

api_ready() {
  for attempt in {1..15}; do
    if [[ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" == healthy ]]; then return 0; fi
    sleep 2
  done
  return 1
}
if ! "${backend[@]}" up -d --no-deps --no-build zulassung-api || ! api_ready; then
  if docker container inspect "$previous" >/dev/null 2>&1; then
    "${backend[@]}" stop zulassung-api || true
    "${backend[@]}" rm -f zulassung-api || true
    docker rename "$previous" "$container"
    docker start "$container"
  fi
  exit 1
fi

test "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")" = tariq-backend
echo 'Zulassungs-API im Compose-Projekt tariq-backend gesund.'
