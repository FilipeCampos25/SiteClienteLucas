import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from config import DATABASE_URL

logger = logging.getLogger(__name__)

SQLITE_URL = "sqlite:///./local.db"


def _create_sqlite_engine():
    return create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
    )


def _create_primary_engine():
    if not DATABASE_URL:
        logger.warning("DATABASE_URL ausente. Usando SQLite local em %s.", SQLITE_URL)
        return _create_sqlite_engine()

    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "poolclass": NullPool,
    }
    if DATABASE_URL.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["connect_args"] = {"connect_timeout": 5}

    primary_engine = create_engine(DATABASE_URL, **engine_kwargs)

    try:
        with primary_engine.connect():
            logger.info("Conexao com banco remoto estabelecida.")
        return primary_engine
    except SQLAlchemyError as exc:
        logger.warning(
            "Falha ao conectar no banco remoto; usando SQLite local. Motivo: %s",
            exc,
        )
        return _create_sqlite_engine()


engine = _create_primary_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def _sqlite_rebuild_produtos(colunas_existentes: set[str]) -> None:
    campos_copiados = [
        "id",
        "nome",
        "resumo_curto",
        "catalogo_url",
        "imagem_url",
        "imagem_mime",
        "imagem_bytes",
        "imagem_sha256",
        "criado_em",
        "atualizado_em",
    ]
    select_campos = []
    for campo in campos_copiados:
        if campo in colunas_existentes:
            select_campos.append(campo)
        else:
            select_campos.append(f"NULL AS {campo}")

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS produtos_new"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS produtos_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    nome VARCHAR(120) NOT NULL,
                    resumo_curto TEXT,
                    catalogo_url VARCHAR(500),
                    catalogo_nome_arquivo VARCHAR(255),
                    catalogo_mime VARCHAR(100),
                    catalogo_bytes BLOB,
                    imagem_url VARCHAR,
                    imagem_mime VARCHAR(64),
                    imagem_bytes BLOB,
                    imagem_sha256 VARCHAR(64),
                    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                INSERT INTO produtos_new ({", ".join(campos_copiados)})
                SELECT {", ".join(select_campos)}
                FROM produtos
                """
            )
        )
        conn.execute(text("DROP TABLE produtos"))
        conn.execute(text("ALTER TABLE produtos_new RENAME TO produtos"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_produtos_id ON produtos (id)"))


def _postgres_sync_produtos(colunas: set[str]) -> None:
    alteracoes = {
        "resumo_curto": "TEXT",
        "catalogo_url": "VARCHAR(500)",
        "catalogo_nome_arquivo": "VARCHAR(255)",
        "catalogo_mime": "VARCHAR(100)",
        "catalogo_bytes": "BYTEA",
        "imagem_mime": "VARCHAR(64)",
        "imagem_bytes": "BYTEA",
        "imagem_sha256": "VARCHAR(64)",
        "atualizado_em": "TIMESTAMP DEFAULT NOW()",
    }
    for coluna, ddl in alteracoes.items():
        if coluna in colunas:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE produtos ADD COLUMN {coluna} {ddl}"))

    colunas_legadas = (
        "descricao",
        "tipo",
        "valor",
        "ativo",
        "ordem_exibicao",
        "destaque_home",
    )
    for coluna in colunas_legadas:
        if coluna not in colunas:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE produtos DROP COLUMN IF EXISTS {coluna}"))


def init_db():
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if "produtos" not in inspector.get_table_names():
        return

    colunas = {c["name"] for c in inspector.get_columns("produtos")}
    colunas_desejadas = {
        "id",
        "nome",
        "resumo_curto",
        "catalogo_url",
        "catalogo_nome_arquivo",
        "catalogo_mime",
        "catalogo_bytes",
        "imagem_url",
        "imagem_mime",
        "imagem_bytes",
        "imagem_sha256",
        "criado_em",
        "atualizado_em",
    }
    colunas_legadas = {
        "descricao",
        "tipo",
        "valor",
        "ativo",
        "ordem_exibicao",
        "destaque_home",
    }

    if engine.dialect.name == "sqlite":
        if colunas != colunas_desejadas:
            _sqlite_rebuild_produtos(colunas)
        return

    if (colunas_desejadas - colunas) or (colunas_legadas & colunas):
        _postgres_sync_produtos(colunas)
