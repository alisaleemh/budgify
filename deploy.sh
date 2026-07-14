#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

compose_file="${BUDGIFY_COMPOSE_FILE:-$repo_root/docker-compose.yml}"
compose_env_file="${BUDGIFY_COMPOSE_ENV_FILE:-$(dirname "$compose_file")/.env}"
read -r -a compose_services <<< "${BUDGIFY_COMPOSE_SERVICES:-web}"

if [[ ! -f "$compose_file" ]]; then
  echo "missing compose file: $compose_file" >&2
  exit 1
fi
if [[ ! -f "$compose_env_file" ]]; then
  echo "missing compose environment file: $compose_env_file" >&2
  exit 1
fi

deploy_commit="$(git rev-parse --short HEAD)"
export BUDGIFY_DEPLOY_COMMIT="$deploy_commit"

docker compose --env-file "$compose_env_file" -f "$compose_file" config --quiet
docker compose --env-file "$compose_env_file" -f "$compose_file" build --pull "${compose_services[@]}"
docker compose --env-file "$compose_env_file" -f "$compose_file" up -d --no-deps "${compose_services[@]}"
docker compose --env-file "$compose_env_file" -f "$compose_file" ps "${compose_services[@]}"
