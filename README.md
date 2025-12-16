Cantoneira Fácil — entrega pronta para deploy (versão simplificada)
------------------------------------------------------------
Estrutura mínima do projeto. Configure variáveis de ambiente em .env antes de rodar.
- DATABASE_URL (ex: postgresql://user:pass@host:port/dbname) — se não definido, usa SQLite local.
- ADMIN_USER, ADMIN_PASSWORD — credenciais do admin.
- S3_BUCKET_IMAGENS, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (opcional) — para upload de imagens.

Para rodar localmente:
$ python -m venv .venv
$ . .venv/bin/activate
$ pip install -r requirements.txt
$ uvicorn main:app --reload

O pacote zip entregue aqui contém templates (Jinja2), static (CSS/JS), backend FastAPI e scripts básicos.
