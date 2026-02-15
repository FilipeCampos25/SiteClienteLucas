from __future__ import annotations

"""
crud.py
=======
CRUD do banco (SQLAlchemy) para Produto.

CORREÇÃO CRÍTICA (deploy Render):
- Este arquivo NÃO pode ter FastAPI (não existe `@app.context_processor` no FastAPI).
- No seu estado atual, o crud.py estava contaminado com código de main.py e decoradores
  que derrubam o servidor no boot.

Regra:
- CRUD = apenas operações de DB (Session, query, commit, refresh).
"""

import hashlib
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

import models
import schemas


def _sha256(data: bytes) -> str:
    """Gera sha256 hex para ETag/integridade."""
    return hashlib.sha256(data).hexdigest()


def get_produtos(db: Session):
    """
    Retorna TODOS os produtos (ativos e inativos).
    Usado no painel /admin.
    """
    return (
        db.query(models.Produto)
        .order_by(desc(models.Produto.ativo), desc(models.Produto.atualizado_em), desc(models.Produto.criado_em))
        .all()
    )


def get_produtos_ativos(db: Session):
    """Retorna apenas produtos ativos (usado na home / api)."""
    return (
        db.query(models.Produto)
        .filter(models.Produto.ativo.is_(True))
        .order_by(desc(models.Produto.atualizado_em), desc(models.Produto.criado_em))
        .all()
    )


def count_produtos_ativos(db: Session) -> int:
    """Conta produtos ativos (para paginação)."""
    return (
        db.query(func.count(models.Produto.id))
        .filter(models.Produto.ativo.is_(True))
        .scalar()
        or 0
    )


def get_produtos_ativos_paginados(db: Session, *, page: int = 1, page_size: int = 10):
    """
    Retorna produtos ativos paginados (para otimizar a home).
    """
    page = max(1, page)
    page_size = max(1, page_size)
    offset = (page - 1) * page_size

    return (
        db.query(models.Produto)
        .filter(models.Produto.ativo.is_(True))
        .order_by(desc(models.Produto.atualizado_em), desc(models.Produto.criado_em))
        .offset(offset)
        .limit(page_size)
        .all()
    )


def get_produtos_ativos_paginado(db: Session, *, skip: int = 0, limit: int = 10):
    """
    COMPATIBILIDADE (hotfix):
    -----------------------
    Algumas versões do main.py chamam:
        crud.get_produtos_ativos_paginado(db, skip=..., limit=...)

    Porém, neste projeto o método "oficial" é:
        get_produtos_ativos_paginados(db, page=..., page_size=...)

    Para NÃO quebrar deploys já publicados (Render) e manter mudanças mínimas,
    este alias implementa o mesmo comportamento usando OFFSET/LIMIT.

    Parâmetros:
      - skip: quantos itens pular (OFFSET)
      - limit: quantos itens retornar (LIMIT)
    """
    # COMENTÁRIO: garantindo valores válidos para não gerar erro no SQLAlchemy
    skip = max(0, int(skip or 0))
    limit = max(1, int(limit or 10))

    return (
        db.query(models.Produto)
        .filter(models.Produto.ativo.is_(True))
        .order_by(desc(models.Produto.atualizado_em), desc(models.Produto.criado_em))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_produto(db: Session, produto_id: int):
    """Busca produto ativo por ID (página detalhe)."""
    return (
        db.query(models.Produto)
        .filter(models.Produto.id == produto_id, models.Produto.ativo.is_(True))
        .first()
    )


def create_produto(
    db: Session,
    produto: schemas.ProdutoCreate,
    *,
    imagem_bytes: bytes | None = None,
    imagem_mime: str | None = None,
):
    """
    Cria produto e salva imagem no DB (se enviada).

    Observações:
    - imagem_bytes pode ser None (produto sem imagem).
    - imagem_mime pode ser None (heurística na entrega).
    """
    novo = models.Produto(
        nome=produto.nome,
        descricao=produto.descricao or "",
        valor=float(produto.valor),
        ativo=True,
    )

    if imagem_bytes:
        novo.imagem = imagem_bytes
        novo.imagem_etag = _sha256(imagem_bytes)
        novo.imagem_mime = imagem_mime

    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


def update_produto(
    db: Session,
    produto_id: int,
    dados: schemas.ProdutoUpdate,
    *,
    imagem_bytes: bytes | None = None,
    imagem_mime: str | None = None,
):
    """
    Atualiza um produto existente.

    Regras:
    - Só atualiza campos se vierem preenchidos.
    - Se imagem_bytes vier, substitui a imagem e recalcula ETag.
    """
    p = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not p:
        return None

    if dados.nome is not None:
        p.nome = dados.nome
    if dados.descricao is not None:
        p.descricao = dados.descricao
    if dados.valor is not None:
        p.valor = float(dados.valor)
    if dados.ativo is not None:
        p.ativo = bool(dados.ativo)

    if imagem_bytes:
        p.imagem = imagem_bytes
        p.imagem_etag = _sha256(imagem_bytes)
        p.imagem_mime = imagem_mime

    db.commit()
    db.refresh(p)
    return p


def delete_produto(db: Session, produto_id: int) -> bool:
    """
    Exclui produto do banco.

    Retorna:
      - True se excluiu
      - False se não encontrou
    """
    p = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not p:
        return False

    db.delete(p)
    db.commit()
    return True
