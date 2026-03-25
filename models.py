from sqlalchemy import Column, DateTime, Integer, LargeBinary, String, Text, func

from database import Base


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)

    nome = Column(String(120), nullable=False)
    resumo_curto = Column(Text, nullable=True)
    catalogo_url = Column(String(500), nullable=True)
    catalogo_nome_arquivo = Column(String(255), nullable=True)
    catalogo_mime = Column(String(100), nullable=True)
    catalogo_bytes = Column(LargeBinary, nullable=True)

    imagem_url = Column(String, nullable=True)
    imagem_mime = Column(String(64), nullable=True)
    imagem_bytes = Column(LargeBinary, nullable=True)
    imagem_sha256 = Column(String(64), nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
