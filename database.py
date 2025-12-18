from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Verifica se a conexão está viva antes de usar
    pool_recycle=300,        # Recicla conexões a cada 5 minutos (recomendado para Neon)
    poolclass=NullPool       # Evita pool grande em ambientes serverless como Render
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()