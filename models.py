from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, func, Text
from database import Base

class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    descricao = Column(Text)
    valor = Column(Numeric(10,2), nullable=False)
    imagem_url = Column(String, nullable=False)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
