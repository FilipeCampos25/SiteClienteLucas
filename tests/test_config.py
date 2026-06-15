from __future__ import annotations

import os
import subprocess
import sys

from conftest import PROJECT_ROOT


def run_config_import(**overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "development",
            "TRUST_PROXY_HEADERS": "false",
            "DATABASE_URL": "",
            "ADMIN_USER": "",
            "ADMIN_PASSWORD": "",
            "ADMIN_PASS": "",
            "SECRET_KEY": "",
            "CORS_ORIGINS": "",
        }
    )
    env.update(overrides)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import config; "
                "print(config.APP_ENV, config.DATABASE_URL, "
                "config.CORS_ALLOW_CREDENTIALS, config.TRUST_PROXY_HEADERS)"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_development_uses_sqlite_without_database_url() -> None:
    result = run_config_import()
    assert result.returncode == 0
    assert "development sqlite:///./local.db False False" in result.stdout


def test_production_reports_all_missing_critical_values() -> None:
    result = run_config_import(APP_ENV="production")
    assert result.returncode != 0
    for variable in [
        "DATABASE_URL",
        "SECRET_KEY",
        "ADMIN_USER",
        "ADMIN_PASSWORD",
        "CORS_ORIGINS",
    ]:
        assert variable in result.stderr


def test_production_rejects_wildcard_cors() -> None:
    result = run_config_import(
        APP_ENV="production",
        DATABASE_URL="sqlite:///production.db",
        SECRET_KEY="production-secret-key",
        ADMIN_USER="admin-user",
        ADMIN_PASSWORD="strong-production-password",
        CORS_ORIGINS="*",
    )
    assert result.returncode != 0
    assert "nao pode conter '*'" in result.stderr


def test_production_rejects_documented_secret_placeholders() -> None:
    result = run_config_import(
        APP_ENV="production",
        DATABASE_URL="sqlite:///production.db",
        SECRET_KEY="replace-with-a-long-random-secret",
        ADMIN_USER="admin-user",
        ADMIN_PASSWORD="replace-with-a-strong-password",
        CORS_ORIGINS="https://example.com",
    )
    assert result.returncode != 0
    assert "SECRET_KEY esta ausente ou usa um valor inseguro" in result.stderr
    assert "ADMIN_PASSWORD esta ausente ou usa um valor inseguro" in result.stderr


def test_production_accepts_trusted_nginx_proxy_configuration() -> None:
    result = run_config_import(
        APP_ENV="production",
        TRUST_PROXY_HEADERS="true",
        DATABASE_URL="sqlite:///production.db",
        SECRET_KEY="production-secret-key",
        ADMIN_USER="admin-user",
        ADMIN_PASSWORD="strong-production-password",
        CORS_ORIGINS="https://example.com",
    )
    assert result.returncode == 0
    assert "production sqlite:///production.db True True" in result.stdout
