#!/usr/bin/env bash
set -euo pipefail

# Inicializa o banco de dados (cria tabelas se não existirem)
python -c "from main import init_db_and_admin; init_db_and_admin()"

# Inicia o servidor Gunicorn
exec gunicorn main:app \
  --workers "${WEB_CONCURRENCY:-2}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-10000}"
