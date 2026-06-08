from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CategoriaBase(BaseModel):
    slug: str
    nome: str
    nome_exibicao: str
    subtitulo_exibicao: Optional[str] = None
    imagem_url: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class CategoriaCreate(CategoriaBase):
    pass


class CategoriaUpdate(BaseModel):
    slug: Optional[str] = None
    nome: Optional[str] = None
    nome_exibicao: Optional[str] = None
    subtitulo_exibicao: Optional[str] = None
    imagem_url: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class SubcategoriaBase(BaseModel):
    categoria_slug: str
    slug: str
    nome: str
    nome_exibicao: str
    imagem_url: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class SubcategoriaCreate(SubcategoriaBase):
    pass


class SubcategoriaUpdate(BaseModel):
    categoria_slug: Optional[str] = None
    slug: Optional[str] = None
    nome: Optional[str] = None
    nome_exibicao: Optional[str] = None
    imagem_url: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class ProdutoBase(BaseModel):
    nome: str
    resumo_curto: Optional[str] = None
    categoria_slug: Optional[str] = None
    subcategoria_slug: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class ProdutoCreate(ProdutoBase):
    pass


class ProdutoUpdate(BaseModel):
    nome: Optional[str] = None
    resumo_curto: Optional[str] = None
    categoria_slug: Optional[str] = None
    subcategoria_slug: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class QuemSomosImagemBase(BaseModel):
    alt_texto: Optional[str] = None
    imagem_url: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class QuemSomosImagemCreate(QuemSomosImagemBase):
    pass


class QuemSomosImagemUpdate(BaseModel):
    alt_texto: Optional[str] = None
    imagem_url: Optional[str] = None
    ordem_exibicao: Optional[int] = None


class SiteImagemBase(BaseModel):
    chave: str
    alt_texto: Optional[str] = None
    imagem_url: Optional[str] = None


class SiteImagemCreate(SiteImagemBase):
    pass


class SiteImagemUpdate(BaseModel):
    alt_texto: Optional[str] = None
    imagem_url: Optional[str] = None


class ProdutoOut(ProdutoBase):
    id: int
    imagem_url: Optional[str] = None
    imagem_medidas_url: Optional[str] = None
    imagem_extra_url: Optional[str] = None
    imagens: list[str] = Field(default_factory=list)
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True
        orm_mode = True


class ItemCarrinho(BaseModel):
    nome: str
    quantidade: int
    valor_unitario: float
