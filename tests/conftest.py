from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def migration_env(database_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "development",
            "TRUST_PROXY_HEADERS": "false",
            "DATABASE_URL": sqlite_url(database_path),
            "ADMIN_USER": "test-admin",
            "ADMIN_PASSWORD": "test-admin-password",
            "SECRET_KEY": "test-secret-key-with-enough-entropy",
            "CORS_ORIGINS": "*",
        }
    )
    return env


def upgrade_database(database_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=migration_env(database_path),
        check=True,
        capture_output=True,
        text=True,
    )


def extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    database_path = tmp_path / "app.db"
    upgrade_database(database_path)

    env = migration_env(database_path)
    for key in {
        "APP_ENV",
        "TRUST_PROXY_HEADERS",
        "DATABASE_URL",
        "ADMIN_USER",
        "ADMIN_PASSWORD",
        "SECRET_KEY",
        "CORS_ORIGINS",
    }:
        monkeypatch.setenv(key, env[key])

    for module_name in [
        "main",
        "crud",
        "models",
        "database",
        "config",
        "security",
        "rate_limit",
    ]:
        sys.modules.pop(module_name, None)

    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def legacy_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE produtos (
            id INTEGER NOT NULL PRIMARY KEY,
            nome VARCHAR(120) NOT NULL,
            resumo_curto TEXT,
            categoria_slug VARCHAR(80),
            subcategoria_slug VARCHAR(80),
            imagem_url VARCHAR,
            imagem_mime VARCHAR(64),
            imagem_bytes BLOB,
            imagem_sha256 VARCHAR(64),
            imagem_medidas_mime VARCHAR(64),
            imagem_medidas_bytes BLOB,
            imagem_medidas_sha256 VARCHAR(64),
            imagem_extra_mime VARCHAR(64),
            imagem_extra_bytes BLOB,
            imagem_extra_sha256 VARCHAR(64),
            descricao TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    connection.execute(
        """
        INSERT INTO produtos (id, nome, imagem_mime, imagem_bytes, descricao)
        VALUES (?, ?, ?, ?, ?)
        """,
        (7, "Produto legado", "image/webp", b"legacy-image-bytes", "preservar"),
    )
    connection.commit()
    connection.close()
    return database_path
