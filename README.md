# Casa das Cantoneiras

Catalogo administravel construido com FastAPI, Jinja2, SQLAlchemy e Alembic.
Imagens de categorias, produtos e paginas institucionais continuam armazenadas
no banco nos campos `imagem_bytes`, `imagem_mime` e `imagem_sha256`.

## Desenvolvimento local

Crie o ambiente, instale as dependencias e configure o `.env`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

`APP_ENV=development` permite deixar `DATABASE_URL` vazio. Nesse caso o app usa
`sqlite:///./local.db` e registra warnings para credenciais/chaves de
desenvolvimento.

Antes de iniciar o servidor, aplique as migracoes:

```powershell
alembic upgrade head
uvicorn main:app --reload
```

Para verificar o estado:

```powershell
alembic current
alembic history
pytest
```

## Configuracao de producao

Producao e ativada por `APP_ENV=production` ou automaticamente por
`RENDER=true`. O app falha antes de iniciar se qualquer item abaixo estiver
ausente ou inseguro:

- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_USER`
- `ADMIN_PASSWORD`
- `CORS_ORIGINS`

`CORS_ORIGINS` deve conter origens explicitas separadas por virgula e nao pode
conter `*`. Gere `SECRET_KEY` e `ADMIN_PASSWORD` como valores longos e aleatorios.
O alias legado `ADMIN_PASS` funciona somente em desenvolvimento e deve ser
substituido por `ADMIN_PASSWORD`.

## Adocao do Alembic

Sempre crie um backup antes da primeira migracao de um banco existente.

Banco novo:

```bash
alembic upgrade head
```

Banco existente que ainda precisa receber tabelas ou colunas do schema atual:

```bash
alembic upgrade head
```

A revisao inicial e aditiva: cria tabelas ausentes e adiciona colunas e indices
ausentes. Ela preserva dados, blobs e colunas legadas. Se encontrar uma coluna
obrigatoria ausente em uma tabela com dados e sem valor seguro para preenchimento,
a migracao falha para exigir uma revisao controlada.

Use `stamp` somente quando o schema existente ja foi comparado com os models e
esta integralmente compativel:

```bash
alembic stamp head
alembic current
```

O downgrade automatico da revisao inicial nao e oferecido porque ela pode adotar
objetos que ja existiam antes do Alembic.

## Deploy no Render

Configure as variaveis obrigatorias no painel do Render. O `start.sh` executa:

```bash
alembic upgrade head
gunicorn main:app --workers "${WEB_CONCURRENCY:-2}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-10000}"
```

Fluxo recomendado para o primeiro deploy:

1. Fazer backup do Postgres.
2. Conferir se o banco e novo, compativel ou legado.
3. Publicar com todas as variaveis de producao configuradas.
4. Confirmar nos logs que `alembic upgrade head` concluiu antes do Gunicorn.
5. Validar `/admin/login`, uma edicao do catalogo e uma pagina publica.

Com varios workers, o rate limit de login e mantido separadamente em memoria por
processo. Redis ou outro armazenamento compartilhado permanece fora do escopo.
