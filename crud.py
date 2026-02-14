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

    Observação:
    - Guarda bytes puros (sem base64) para evitar corrupção.
    - Preenche imagem_sha256 para cache/ETag.
    """
    data = produto.dict() if hasattr(produto, "dict") else dict(produto)
    db_produto = models.Produto(**data)

    if imagem_bytes is not None:
        db_produto.imagem_bytes = imagem_bytes
        db_produto.imagem_mime = imagem_mime or "application/octet-stream"
        db_produto.imagem_sha256 = _sha256(imagem_bytes)

    db.add(db_produto)
    db.commit()
    db.refresh(db_produto)

    # Após ter ID, define URL padrão se houver bytes
    if db_produto.imagem_bytes:
        db_produto.imagem_url = f"/media/produto/{db_produto.id}"
        db.commit()
        db.refresh(db_produto)

    return db_produto


def update_produto(
    db: Session,
    produto_id: int,
    produto: schemas.ProdutoUpdate,
    *,
    imagem_bytes: bytes | None = None,
    imagem_mime: str | None = None,
):
    """
    Atualiza campos do produto e substitui imagem (se enviada).
    """
    db_produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not db_produto:
        return None

    data = produto.dict(exclude_unset=True) if hasattr(produto, "dict") else dict(produto)
    for k, v in data.items():
        # Evita sobrescrever campos com None vindo do form
        if v is not None:
            setattr(db_produto, k, v)

    if imagem_bytes is not None:
        db_produto.imagem_bytes = imagem_bytes
        db_produto.imagem_mime = imagem_mime or "application/octet-stream"
        db_produto.imagem_sha256 = _sha256(imagem_bytes)
        db_produto.imagem_url = f"/media/produto/{produto_id}"

    db.commit()
    db.refresh(db_produto)
    return db_produto


def delete_produto(db: Session, produto_id: int):
    """
    Delete lógico: marca produto como inativo.
    """
    db_produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not db_produto:
        return None

    db_produto.ativo = False
    db.commit()
    db.refresh(db_produto)
    return db_produto
