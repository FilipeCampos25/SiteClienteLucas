from sqlalchemy import create_engine
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
    """Cria as tabelas se ainda não existirem"""
    import models  # Import local para evitar circular imports
    Base.metadata.create_all(bind=engine)