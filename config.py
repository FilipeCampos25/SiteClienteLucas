from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEV_DATABASE_URL = "sqlite:///./local.db"
DEV_ADMIN_USER = "admin"
DEV_ADMIN_PASSWORD = "troque_essa_senha"
DEV_SECRET_KEY = "change-this-secret-key"

INSECURE_SECRET_KEYS = {
    "",
    DEV_SECRET_KEY,
    "secret",
    "secret-key",
    "changeme",
    "replace-with-a-long-random-secret",
}
INSECURE_ADMIN_PASSWORDS = {
    "",
    DEV_ADMIN_PASSWORD,
    "admin",
    "password",
    "changeme",
    "replace-with-a-strong-password",
}


def _clean_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip() or None


def _env_is_true(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() == "true"


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


_configured_app_env = (_clean_env("APP_ENV") or "development").lower()
if _configured_app_env not in {"development", "production"}:
    raise RuntimeError("APP_ENV deve ser 'development' ou 'production'.")

IS_PRODUCTION = _configured_app_env == "production"
APP_ENV = "production" if IS_PRODUCTION else "development"
TRUST_PROXY_HEADERS = _env_is_true("TRUST_PROXY_HEADERS")

_raw_database_url = _clean_env("DATABASE_URL")
_raw_admin_user = _clean_env("ADMIN_USER")
_raw_admin_password = _clean_env("ADMIN_PASSWORD")
_legacy_admin_password = _clean_env("ADMIN_PASS")
_raw_secret_key = _clean_env("SECRET_KEY")
_raw_cors_origins = _clean_env("CORS_ORIGINS")

if IS_PRODUCTION:
    config_errors: list[str] = []
    if not _raw_database_url:
        config_errors.append("DATABASE_URL esta ausente")
    if not _raw_secret_key or _raw_secret_key in INSECURE_SECRET_KEYS:
        config_errors.append("SECRET_KEY esta ausente ou usa um valor inseguro")
    if not _raw_admin_user:
        config_errors.append("ADMIN_USER esta ausente")
    if not _raw_admin_password or _raw_admin_password in INSECURE_ADMIN_PASSWORDS:
        config_errors.append("ADMIN_PASSWORD esta ausente ou usa um valor inseguro")
    if not _raw_cors_origins:
        config_errors.append("CORS_ORIGINS esta ausente ou vazio")

    configured_origins = [
        origin.strip()
        for origin in (_raw_cors_origins or "").split(",")
        if origin.strip()
    ]
    if "*" in configured_origins:
        config_errors.append("CORS_ORIGINS nao pode conter '*' em producao")

    if config_errors:
        details = "\n- ".join(config_errors)
        raise RuntimeError(f"Configuracao de producao invalida:\n- {details}")
    if not TRUST_PROXY_HEADERS:
        logger.warning(
            "TRUST_PROXY_HEADERS esta desabilitado em producao. "
            "Habilite-o quando o app estiver atras de um proxy confiavel como o Nginx."
        )
else:
    configured_origins = [
        origin.strip()
        for origin in (_raw_cors_origins or "").split(",")
        if origin.strip()
    ]
    if not _raw_database_url:
        logger.warning(
            "DATABASE_URL ausente em desenvolvimento. Usando SQLite local em %s.",
            DEV_DATABASE_URL,
        )
    if not _raw_secret_key:
        logger.warning("SECRET_KEY ausente em desenvolvimento. Usando chave local insegura.")
    elif _raw_secret_key in INSECURE_SECRET_KEYS:
        logger.warning("SECRET_KEY usa um valor conhecido como inseguro em desenvolvimento.")
    if not _raw_admin_user:
        logger.warning("ADMIN_USER ausente em desenvolvimento. Usando usuario 'admin'.")
    if not _raw_admin_password and _legacy_admin_password:
        logger.warning(
            "ADMIN_PASS esta obsoleta. Migre para ADMIN_PASSWORD; o alias so funciona em desenvolvimento."
        )
    if not _raw_admin_password and not _legacy_admin_password:
        logger.warning(
            "ADMIN_PASSWORD ausente em desenvolvimento. O login admin usara a senha local insegura."
        )
    elif (_raw_admin_password or _legacy_admin_password or "") in INSECURE_ADMIN_PASSWORDS:
        logger.warning("ADMIN_PASSWORD usa um valor conhecido como inseguro em desenvolvimento.")
    if not configured_origins:
        logger.warning("CORS_ORIGINS ausente em desenvolvimento. Usando origem wildcard sem credenciais.")
        configured_origins = ["*"]
    elif "*" in configured_origins:
        logger.warning("CORS wildcard habilitado em desenvolvimento sem envio de credenciais.")

DATABASE_URL = normalize_database_url(_raw_database_url or DEV_DATABASE_URL)
ADMIN_USER = _raw_admin_user or DEV_ADMIN_USER
ADMIN_PASSWORD = _raw_admin_password or _legacy_admin_password or DEV_ADMIN_PASSWORD
SECRET_KEY = _raw_secret_key or DEV_SECRET_KEY
CORS_ORIGINS = configured_origins
CORS_ALLOW_CREDENTIALS = "*" not in CORS_ORIGINS

# Public site settings
WHATSAPP_NUMERO = _clean_env("WHATSAPP_NUMERO")
INSTAGRAM_URL = (
    _clean_env("INSTAGRAM_URL")
    or "https://www.instagram.com/casa_dascantoneiras?igsh=NWJvNnRsNXc2cTR4"
)
FACEBOOK_URL = _clean_env("FACEBOOK_URL") or "https://www.facebook.com/"
STORE_ADDRESS = (
    _clean_env("STORE_ADDRESS")
    or "Rua 08, Chacara 225, Loja 2/3, Vicente Pires, Brasilia - DF, CEP 72007-065"
)
STORE_CNPJ = _clean_env("STORE_CNPJ") or "55.291.020/0001-50"
MAX_IMAGE_BYTES = int(_clean_env("MAX_IMAGE_BYTES") or "4000000")
