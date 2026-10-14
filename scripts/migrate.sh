#!/usr/bin/env bash
# Runs every sql/*.sql in order. All scripts are idempotent, so re-running is safe.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

for f in sql/*.sql; do
  echo ">> applying $f"
  psql -v ON_ERROR_STOP=1 -q -f "$f"
done
echo "all good ✔"
