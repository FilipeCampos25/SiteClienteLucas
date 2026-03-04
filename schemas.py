from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime

TIPOS_PRODUTO = ("cantoneira", "instalacao", "kits", "prateleiras")


class ProdutoBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    valor: float
    tipo: str = "cantoneira"

class ProdutoCreate(ProdutoBase):
    # imagem_url pode ser preenchida automaticamente (/media/produto/{id})
    imagem_url: Optional[str] = None

    @validator("tipo")
    def validar_tipo(cls, v: str) -> str:
        if v not in TIPOS_PRODUTO:
            raise ValueError(f"tipo inválido. Use um de: {', '.join(TIPOS_PRODUTO)}")
        return v

class ProdutoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    valor: Optional[float] = None
    tipo: Optional[str] = None
    imagem_url: Optional[str] = None
    ativo: Optional[bool] = None

    @validator("tipo")
    def validar_tipo_update(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in TIPOS_PRODUTO:
            raise ValueError(f"tipo inválido. Use um de: {', '.join(TIPOS_PRODUTO)}")
        return v

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
