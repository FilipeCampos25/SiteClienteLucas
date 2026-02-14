from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, func, Text, LargeBinary
from database import Base

class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)

    nome = Column(String(120), nullable=False)
    descricao = Column(Text)

    # Numeric no Postgres vira Decimal na leitura; convertemos no schema de saída
    valor = Column(Numeric(20, 2), nullable=False)

    # Mantido por compatibilidade: pode apontar para CDN/S3 ou para endpoint local (/media/...)
    imagem_url = Column(String, nullable=True)

    # Armazenamento confiável (DB): evita perder imagens em filesystem efêmero (Render/free tiers)
    imagem_mime = Column(String(64), nullable=True)
    imagem_bytes = Column(LargeBinary, nullable=True)
    imagem_sha256 = Column(String(64), nullable=True)

    ativo = Column(Boolean, default=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
