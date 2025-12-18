#!/usr/bin/env bash

# Inicializa o banco de dados (cria tabelas se não existirem)
python3 -c "from main import init_db_and_admin; init_db_and_admin()"

# Inicia o servidor Uvicorn
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
