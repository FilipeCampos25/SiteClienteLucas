from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from config import DATABASE_URL

if not DATABASE_URL:
    raise ValueError("Erro crítico: DATABASE_URL não está definida nas variáveis de ambiente do Render!")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,      # Essencial para Neon (evita conexões mortas)
    poolclass=NullPool     # Melhor para ambientes serverless como Render
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def init_db():
    """Cria tabelas e aplica ajustes mínimos de schema em bancos existentes."""
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
