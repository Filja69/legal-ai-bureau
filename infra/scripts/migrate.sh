#!/usr/bin/env bash
# Run Alembic migrations against DATABASE_URL (see .env). Usage: ./infra/scripts/migrate.sh
set -euo pipefail
cd "$(dirname "$0")/../../backend"
alembic upgrade head
