from __future__ import annotations

import sqlite3
from pathlib import Path

from conftest import upgrade_database

EXPECTED_TABLES = {
    "alembic_version",
    "categorias",
    "subcategorias",
    "produtos",
    "quem_somos_imagens",
    "site_imagens",
    "site_config",
}


def table_names(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path)
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    connection.close()
    return names


def test_initial_migration_creates_current_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "new.db"
    upgrade_database(database_path)
    assert EXPECTED_TABLES <= table_names(database_path)


def test_initial_migration_preserves_legacy_data_and_columns(
    legacy_database: Path,
) -> None:
    upgrade_database(legacy_database)

    connection = sqlite3.connect(legacy_database)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info('produtos')")
    }
    product = connection.execute(
        "SELECT id, nome, imagem_bytes, descricao, ordem_exibicao FROM produtos"
    ).fetchone()
    connection.close()

    assert EXPECTED_TABLES <= table_names(legacy_database)
    assert "descricao" in columns
    assert "ordem_exibicao" in columns
    assert product == (7, "Produto legado", b"legacy-image-bytes", "preservar", 0)
