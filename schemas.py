from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProdutoBase(BaseModel):
    nome: str
    resumo_curto: Optional[str] = None
    catalogo_url: Optional[str] = None


class ProdutoCreate(ProdutoBase):
    pass


class ProdutoUpdate(BaseModel):
    nome: Optional[str] = None
    resumo_curto: Optional[str] = None
    catalogo_url: Optional[str] = None


class ProdutoOut(ProdutoBase):
    id: int
    imagem_url: Optional[str] = None
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True
        orm_mode = True


class ItemCarrinho(BaseModel):
    nome: str
    quantidade: int
    valor_unitario: float
