#!/usr/bin/env bash
set -euo pipefail

# Apply versioned database migrations before starting the web process.
alembic upgrade head

# Start Gunicorn only after a successful migration.
exec gunicorn main:app \
  --workers "${WEB_CONCURRENCY:-2}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-10000}"
