from pydantic import BaseModel
from typing import Optional

class ProdutoBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    valor: float
    imagem_url: str

class ProdutoCreate(ProdutoBase):
    pass

class ProdutoUpdate(BaseModel):
    nome: Optional[str]
    descricao: Optional[str]
    valor: Optional[float]
    imagem_url: Optional[str]
    ativo: Optional[bool]

class ProdutoOut(ProdutoBase):
    id: int
    ativo: bool

    class Config:
        orm_mode = True

class ItemCarrinho(BaseModel):
    nome: str
    quantidade: int
    valor_unitario: float
