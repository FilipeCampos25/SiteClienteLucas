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

    primary_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )

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


def init_db():
    """Cria tabelas e aplica ajustes minimos de schema em bancos existentes."""
    import models  # Import local para evitar circular imports

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if "produtos" not in inspector.get_table_names():
        return

    colunas = {c["name"] for c in inspector.get_columns("produtos")}
    if "tipo" not in colunas:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE produtos "
                    "ADD COLUMN tipo VARCHAR(32) NOT NULL DEFAULT 'cantoneira'"
                )
            )
