from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, func, Text, LargeBinary, text
from database import Base

class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)

    nome = Column(String(120), nullable=False)
    descricao = Column(Text)
    catalogo_url = Column(String(500), nullable=True)
    resumo_curto = Column(String(255), nullable=True)
    ordem_exibicao = Column(Integer, nullable=False, default=0, server_default="0")
    destaque_home = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    tipo = Column(String(32), nullable=False, server_default="cantoneira")

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
