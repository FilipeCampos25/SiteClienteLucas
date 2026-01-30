from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ProdutoBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    valor: float

class ProdutoCreate(ProdutoBase):
    # imagem_url pode ser preenchida automaticamente (/media/produto/{id})
    imagem_url: Optional[str] = None

class ProdutoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    valor: Optional[float] = None
    imagem_url: Optional[str] = None
    ativo: Optional[bool] = None

class ProdutoOut(ProdutoBase):
    id: int
    imagem_url: Optional[str] = None
    ativo: bool
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True  # pydantic v2 compat (mas funciona no v1 com alias)
        orm_mode = True

class ItemCarrinho(BaseModel):
    nome: str
    quantidade: int
    valor_unitario: float
