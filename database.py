from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from config import DATABASE_URL

logger = logging.getLogger(__name__)


def create_database_engine(database_url: str = DATABASE_URL):
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": True,
    }

    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs.update(
            {
                "pool_recycle": 300,
                "poolclass": NullPool,
                "connect_args": {"connect_timeout": 5},
            }
        )

    database_engine = create_engine(database_url, **engine_kwargs)
    try:
        with database_engine.connect():
            logger.info("Conexao com banco de dados estabelecida.")
    except SQLAlchemyError as exc:
        database_engine.dispose()
        raise RuntimeError(
            "Falha ao conectar ao banco configurado em DATABASE_URL. "
            "O fallback para SQLite so ocorre quando DATABASE_URL esta ausente."
        ) from exc

    return database_engine


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
