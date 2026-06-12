"""Create or adopt the current catalog schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-12
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


ColumnFactory = Callable[[], sa.Column]


def _timestamps() -> list[ColumnFactory]:
    return [
        lambda: sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        lambda: sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def _image_columns() -> list[ColumnFactory]:
    return [
        lambda: sa.Column("imagem_url", sa.String(), nullable=True),
        lambda: sa.Column("imagem_mime", sa.String(length=64), nullable=True),
        lambda: sa.Column("imagem_bytes", sa.LargeBinary(), nullable=True),
        lambda: sa.Column("imagem_sha256", sa.String(length=64), nullable=True),
    ]


TABLES: dict[str, list[ColumnFactory]] = {
    "categorias": [
        lambda: sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        lambda: sa.Column("slug", sa.String(length=120), nullable=False),
        lambda: sa.Column("nome", sa.String(length=120), nullable=False),
        lambda: sa.Column("nome_exibicao", sa.String(length=120), nullable=False),
        lambda: sa.Column("subtitulo_exibicao", sa.String(length=120), nullable=True),
        *_image_columns(),
        lambda: sa.Column(
            "ordem_exibicao",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *_timestamps(),
    ],
    "subcategorias": [
        lambda: sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        lambda: sa.Column("categoria_slug", sa.String(length=120), nullable=False),
        lambda: sa.Column("slug", sa.String(length=120), nullable=False),
        lambda: sa.Column("nome", sa.String(length=120), nullable=False),
        lambda: sa.Column("nome_exibicao", sa.String(length=120), nullable=False),
        *_image_columns(),
        lambda: sa.Column(
            "ordem_exibicao",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *_timestamps(),
    ],
    "produtos": [
        lambda: sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        lambda: sa.Column("nome", sa.String(length=120), nullable=False),
        lambda: sa.Column("resumo_curto", sa.Text(), nullable=True),
        lambda: sa.Column("categoria_slug", sa.String(length=80), nullable=True),
        lambda: sa.Column("subcategoria_slug", sa.String(length=80), nullable=True),
        *_image_columns(),
        lambda: sa.Column("imagem_medidas_mime", sa.String(length=64), nullable=True),
        lambda: sa.Column("imagem_medidas_bytes", sa.LargeBinary(), nullable=True),
        lambda: sa.Column("imagem_medidas_sha256", sa.String(length=64), nullable=True),
        lambda: sa.Column("imagem_extra_mime", sa.String(length=64), nullable=True),
        lambda: sa.Column("imagem_extra_bytes", sa.LargeBinary(), nullable=True),
        lambda: sa.Column("imagem_extra_sha256", sa.String(length=64), nullable=True),
        lambda: sa.Column(
            "ordem_exibicao",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *_timestamps(),
    ],
    "quem_somos_imagens": [
        lambda: sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        lambda: sa.Column("alt_texto", sa.String(length=160), nullable=True),
        *_image_columns(),
        lambda: sa.Column(
            "ordem_exibicao",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *_timestamps(),
    ],
    "site_imagens": [
        lambda: sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        lambda: sa.Column("chave", sa.String(length=80), nullable=False),
        lambda: sa.Column("alt_texto", sa.String(length=160), nullable=True),
        *_image_columns(),
        *_timestamps(),
    ],
    "site_config": [
        lambda: sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        lambda: sa.Column("chave", sa.String(length=120), nullable=False),
        lambda: sa.Column("valor", sa.Text(), nullable=True),
        *_timestamps(),
    ],
}


INDEXES = [
    ("ix_categorias_id", "categorias", ["id"], False),
    ("ix_categorias_slug", "categorias", ["slug"], True),
    ("ix_subcategorias_id", "subcategorias", ["id"], False),
    ("ix_subcategorias_categoria_slug", "subcategorias", ["categoria_slug"], False),
    ("ix_subcategorias_slug", "subcategorias", ["slug"], False),
    (
        "uq_subcategorias_categoria_slug_slug",
        "subcategorias",
        ["categoria_slug", "slug"],
        True,
    ),
    ("ix_produtos_id", "produtos", ["id"], False),
    ("ix_quem_somos_imagens_id", "quem_somos_imagens", ["id"], False),
    ("ix_site_imagens_id", "site_imagens", ["id"], False),
    ("ix_site_imagens_chave", "site_imagens", ["chave"], True),
    ("ix_site_config_id", "site_config", ["id"], False),
    ("ix_site_config_chave", "site_config", ["chave"], True),
]


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_has_rows(table_name: str) -> bool:
    quoted_name = op.get_bind().dialect.identifier_preparer.quote(table_name)
    result = op.get_bind().execute(sa.text(f"SELECT 1 FROM {quoted_name} LIMIT 1"))
    return result.first() is not None


def _ensure_table(table_name: str, factories: list[ColumnFactory]) -> None:
    inspector = _inspector()
    if table_name not in inspector.get_table_names():
        constraints: list[sa.SchemaItem] = []
        if table_name == "subcategorias":
            constraints.append(
                sa.UniqueConstraint(
                    "categoria_slug",
                    "slug",
                    name="uq_subcategorias_categoria_slug_slug",
                )
            )
        op.create_table(
            table_name,
            *(factory() for factory in factories),
            *constraints,
        )
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns(table_name)
    }
    has_rows = _table_has_rows(table_name)
    dialect_name = op.get_bind().dialect.name

    for factory in factories:
        column = factory()
        if column.name in existing_columns:
            continue
        if column.primary_key:
            raise RuntimeError(
                f"A tabela existente '{table_name}' nao possui a chave primaria "
                f"esperada '{column.name}'. Revise o schema antes de migrar."
            )
        if not column.nullable and column.server_default is None and has_rows:
            raise RuntimeError(
                f"A coluna obrigatoria '{table_name}.{column.name}' esta ausente "
                "em uma tabela com dados. Crie uma migracao controlada para preencher os valores."
            )
        if (
            dialect_name == "sqlite"
            and has_rows
            and column.server_default is not None
            and "CURRENT_TIMESTAMP" in str(column.server_default.arg).upper()
        ):
            raise RuntimeError(
                f"A coluna temporal '{table_name}.{column.name}' esta ausente no SQLite "
                "com dados. Crie uma migracao controlada para preencher os valores."
            )
        op.add_column(table_name, column)
        existing_columns.add(column.name)


def _indexed_column_sets(table_name: str) -> set[tuple[str, ...]]:
    inspector = _inspector()
    column_sets = {
        tuple(index.get("column_names") or [])
        for index in inspector.get_indexes(table_name)
    }
    column_sets.update(
        tuple(constraint.get("column_names") or [])
        for constraint in inspector.get_unique_constraints(table_name)
    )
    return column_sets


def _ensure_indexes() -> None:
    for name, table_name, columns, unique in INDEXES:
        if tuple(columns) in _indexed_column_sets(table_name):
            continue
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    for table_name, factories in TABLES.items():
        _ensure_table(table_name, factories)
    _ensure_indexes()


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade automatico indisponivel: esta revisao pode ter adotado tabelas preexistentes."
    )
