#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

required_files=(config.yaml password.txt .env)
for required_file in "${required_files[@]}"; do
  if [[ ! -f "$required_file" ]]; then
    echo "missing required local file: $required_file" >&2
    exit 1
  fi
done

git fetch origin main
git reset --hard origin/main

deploy_commit="$(git rev-parse --short HEAD)"
export BUDGIFY_DEPLOY_COMMIT="$deploy_commit"

docker compose config
docker compose pull
docker compose build --pull
docker compose up -d
docker compose ps
