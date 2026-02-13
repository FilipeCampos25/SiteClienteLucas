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


## Mudança importante (imagens mais confiáveis)
Esta versão armazena a imagem do produto **no banco (Postgres)** (`imagem_bytes` + `imagem_mime`). Isso evita perda de arquivos em hospedagens com filesystem efêmero.

**Atenção:** como não há migração automatizada (alembic), se você já tem uma tabela `produtos` antiga sem essas colunas, você precisa:
- ou recriar a tabela (ambiente novo),
- ou aplicar um `ALTER TABLE` adicionando as colunas: `imagem_mime`, `imagem_bytes`, `imagem_sha256`, `atualizado_em` e tornar `imagem_url` nullable.

As imagens são servidas por: `/media/produto/{id}` com cache (ETag + Cache-Control).


& "C:\Program Files\Python312\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
