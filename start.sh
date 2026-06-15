#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-2}"

# Apply versioned database migrations before starting the web process.
alembic upgrade head

# Start Gunicorn only after a successful migration.
exec gunicorn main:app \
  --workers "${WEB_CONCURRENCY}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "${HOST}:${PORT}" \
  --access-logfile - \
  --error-logfile -
