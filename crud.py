from __future__ import annotations

"""
crud.py
=======
Operações de banco para Produto.

FOCO DESTA REFATORAÇÃO:
- Persistir bytes da imagem sem "conversões" indevidas.
- Garantir hash (sha256) para ETag/caching e integridade.

Observação:
- Mantive a mesma "API" (funções) para não quebrar o resto do app.
"""

import hashlib
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

import models
import schemas


def _sha256(data: bytes) -> str:
    """Calcula sha256 em hexadecimal (ETag/integridade)."""
    return hashlib.sha256(data).hexdigest()


def get_produtos_ativos(db: Session):
    """Lista produtos ativos, ordenando pelos mais recentes."""
    return (
        db.query(models.Produto)
        .filter(models.Produto.ativo.is_(True))
        .order_by(desc(models.Produto.atualizado_em), desc(models.Produto.criado_em))
        .all()
    )


def count_produtos_ativos(db: Session) -> int:
    """Retorna a quantidade total de produtos ativos."""
    return (
        db.query(func.count(models.Produto.id))
        .filter(models.Produto.ativo.is_(True))
        .scalar()
        or 0
    )


def get_produtos_ativos_paginados(db: Session, *, page: int = 1, page_size: int = 10):
    """Lista produtos ativos paginados, ordenando pelos mais recentes."""
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
    """Retorna um produto ativo pelo id."""
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
    Cria produto e, se houver imagem, salva no DB.

    COMENTÁRIO IMPORTANTE:
    - `imagem_bytes` deve ser bytes puros.
    - Não fazemos encode/decode (isso é uma causa comum de corrupção).
    """
    payload = produto.model_dump() if hasattr(produto, "model_dump") else produto.dict()
    db_produto = models.Produto(**payload)

    if imagem_bytes is not None:
        db_produto.imagem_bytes = imagem_bytes
        db_produto.imagem_mime = imagem_mime or "application/octet-stream"
        db_produto.imagem_sha256 = _sha256(imagem_bytes)
        # url padrão para o frontend consumir
        db_produto.imagem_url = db_produto.imagem_url or ""  # mantém compatibilidade

    db.add(db_produto)
    db.commit()
    db.refresh(db_produto)

    # Depois de ter o ID, padroniza imagem_url se houver bytes no DB
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
    Atualiza campos do produto e (opcionalmente) substitui a imagem.
    """
    db_produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not db_produto:
        return None

    data = produto.model_dump(exclude_unset=True) if hasattr(produto, "model_dump") else produto.dict(exclude_unset=True)
    for k, v in data.items():
        # COMENTÁRIO: evita sobrescrever com None (quando excluído do form)
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
