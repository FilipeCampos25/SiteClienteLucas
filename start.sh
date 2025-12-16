#!/usr/bin/env bash

# Inicializa o banco de dados (cria tabelas se não existirem)
python3 -c "from database import init_db; init_db()"

# Inicia o servidor Uvicorn
uvicorn main:app --host 0.0.0.0 --port $PORT
