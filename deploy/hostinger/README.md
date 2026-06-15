# Deploy na Hostinger VPS Ubuntu

Esta configuracao usa:

- Ubuntu 22.04 ou 24.04;
- Nginx nas portas publicas 80/443;
- Gunicorn/FastAPI somente em `127.0.0.1:8000`;
- systemd para iniciar e reiniciar o app;
- PostgreSQL local ou um PostgreSQL externo;
- Certbot para HTTPS.

Substitua `example.com` pelo dominio real e confirme que os registros DNS `A`
do dominio e de `www` apontam para o IP publico da VPS.

## 1. Preparar a VPS

Entre por SSH como um usuario com `sudo`:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y \
  git nginx postgresql postgresql-contrib \
  python3 python3-venv python3-pip \
  certbot python3-certbot-nginx
```

Crie um usuario dedicado e permita que o Nginx leia apenas os arquivos estaticos:

```bash
sudo adduser --system --group --home /opt/sitecliente --shell /bin/bash sitecliente
sudo usermod -a -G www-data sitecliente
```

## 2. Baixar e instalar a aplicacao

Para repositorio publico:

```bash
sudo -u sitecliente git clone \
  https://github.com/FilipeCampos25/SiteClienteLucas.git \
  /opt/sitecliente
```

Para repositorio privado, configure antes uma deploy key somente leitura.

```bash
sudo -u sitecliente python3 -m venv /opt/sitecliente/.venv
sudo -u sitecliente /opt/sitecliente/.venv/bin/pip install --upgrade pip
sudo -u sitecliente /opt/sitecliente/.venv/bin/pip install \
  -r /opt/sitecliente/requirements.txt
```

Garanta acesso de leitura do Nginx aos arquivos estaticos:

```bash
sudo chown -R sitecliente:sitecliente /opt/sitecliente
sudo chown sitecliente:www-data /opt/sitecliente
sudo chown -R sitecliente:www-data /opt/sitecliente/static
sudo chmod 750 /opt/sitecliente
sudo find /opt/sitecliente/static -type d -exec chmod 750 {} \;
sudo find /opt/sitecliente/static -type f -exec chmod 640 {} \;
```

## 3. Configurar PostgreSQL

Se usar um banco externo, pule esta etapa e use a URL fornecida pelo provedor.

Para PostgreSQL local:

```bash
sudo -u postgres psql
```

Execute no prompt do PostgreSQL, usando uma senha forte:

```sql
CREATE USER sitecliente WITH PASSWORD 'SENHA_FORTE_DO_BANCO';
CREATE DATABASE sitecliente OWNER sitecliente;
\q
```

Caracteres especiais da senha precisam estar codificados corretamente na URL.
Exemplo:

```text
postgresql://sitecliente:SENHA_CODIFICADA@127.0.0.1:5432/sitecliente
```

Nao abra a porta `5432` no firewall quando o banco for local.

## 4. Configurar variaveis de producao

```bash
sudo install -d -m 700 /etc/sitecliente
sudo cp /opt/sitecliente/deploy/hostinger/sitecliente.env.example \
  /etc/sitecliente/sitecliente.env
sudo chmod 600 /etc/sitecliente/sitecliente.env
sudo nano /etc/sitecliente/sitecliente.env
```

Preencha obrigatoriamente:

- `DATABASE_URL`;
- `SECRET_KEY`;
- `ADMIN_USER`;
- `ADMIN_PASSWORD`;
- `CORS_ORIGINS=https://example.com,https://www.example.com`.

Mantenha:

```env
APP_ENV=production
TRUST_PROXY_HEADERS=true
```

Uma chave pode ser gerada com:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 5. Instalar o servico systemd

```bash
sudo cp /opt/sitecliente/deploy/hostinger/sitecliente.service \
  /etc/systemd/system/sitecliente.service
sudo systemctl daemon-reload
sudo systemctl enable --now sitecliente
sudo systemctl status sitecliente
```

O `ExecStartPre` executa `alembic upgrade head`. Se a migracao falhar, o processo
web nao inicia.

Logs:

```bash
sudo journalctl -u sitecliente -f
```

Teste interno:

```bash
curl -I http://127.0.0.1:8000/
```

## 6. Configurar Nginx

Edite `server_name` no arquivo antes de ativa-lo:

```bash
sudo cp /opt/sitecliente/deploy/hostinger/sitecliente.nginx.conf \
  /etc/nginx/sites-available/sitecliente
sudo nano /etc/nginx/sites-available/sitecliente
sudo ln -s /etc/nginx/sites-available/sitecliente \
  /etc/nginx/sites-enabled/sitecliente
sudo nginx -t
sudo systemctl reload nginx
```

Se o site padrao do Nginx conflitar com o dominio:

```bash
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## 7. Firewall e HTTPS

Mantenha SSH liberado antes de ativar o firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

Nao abra a porta `8000`; ela deve permanecer acessivel apenas localmente.

Depois que o DNS estiver propagado:

```bash
sudo certbot --nginx -d example.com -d www.example.com
sudo certbot renew --dry-run
```

## 8. Atualizar o site

```bash
sudo -u sitecliente git -C /opt/sitecliente pull --ff-only
sudo -u sitecliente /opt/sitecliente/.venv/bin/pip install \
  -r /opt/sitecliente/requirements.txt
sudo systemctl restart sitecliente
sudo systemctl status sitecliente
```

O restart aplica as migracoes antes de servir a nova versao.

## 9. Backup

Antes de cada atualizacao que altere schema:

```bash
sudo install -d -m 700 -o postgres -g postgres /var/backups/sitecliente
sudo -u postgres pg_dump -Fc sitecliente \
  -f "/var/backups/sitecliente/sitecliente-$(date +%F-%H%M).dump"
```

Proteja `/var/backups`, teste restauracoes periodicamente e use tambem os
snapshots da VPS. As imagens do catalogo estao dentro do banco e fazem parte
desse backup.
