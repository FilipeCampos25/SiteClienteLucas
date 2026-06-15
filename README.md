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

Producao e ativada explicitamente por `APP_ENV=production`. O app falha antes
de iniciar se qualquer item abaixo estiver ausente ou inseguro:

- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_USER`
- `ADMIN_PASSWORD`
- `CORS_ORIGINS`

`CORS_ORIGINS` deve conter origens explicitas separadas por virgula e nao pode
conter `*`. Gere `SECRET_KEY` e `ADMIN_PASSWORD` como valores longos e aleatorios.
O alias legado `ADMIN_PASS` funciona somente em desenvolvimento e deve ser
substituido por `ADMIN_PASSWORD`.

Quando o app estiver atras de um proxy controlado, como o Nginx da VPS, configure
`TRUST_PROXY_HEADERS=true`. Isso permite que o rate limit do login use o IP
encaminhado pelo proxy. Nao habilite essa opcao quando clientes puderem acessar
diretamente o processo Gunicorn.

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

## Deploy na Hostinger VPS Ubuntu

O deploy recomendado usa Nginx, systemd, Gunicorn e PostgreSQL. Os arquivos
prontos ficam em `deploy/hostinger/`:

- `sitecliente.service`: servico systemd;
- `sitecliente.nginx.conf`: proxy reverso Nginx;
- `sitecliente.env.example`: variaveis de producao;
- `README.md`: provisionamento completo, HTTPS, firewall, atualizacao e backup.

Guia completo:

```text
deploy/hostinger/README.md
```

O `start.sh`, quando usado manualmente, executa:

```bash
alembic upgrade head
gunicorn main:app --workers "${WEB_CONCURRENCY:-2}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "${HOST:-127.0.0.1}:${PORT:-8000}"
```

Na VPS:

1. Fazer backup do Postgres.
2. Apontar o DNS do dominio para o IP da VPS.
3. Instalar a aplicacao em `/opt/sitecliente`.
4. Configurar `/etc/sitecliente/sitecliente.env`.
5. Ativar o servico systemd e o site Nginx.
6. Emitir o certificado HTTPS com Certbot.
7. Validar `/admin/login`, uma edicao do catalogo e uma pagina publica.

Com varios workers, o rate limit de login e mantido separadamente em memoria por
processo. Redis ou outro armazenamento compartilhado permanece fora do escopo.
