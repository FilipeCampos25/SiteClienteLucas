from __future__ import annotations

import hashlib
from typing import List, Optional

from sqlalchemy.orm import Session

import models
import schemas

PLACEHOLDER_IMAGE_URL = "/static/images/placeholder.png"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_produto(db: Session, *, produto_id: int) -> Optional[models.Produto]:
    return db.query(models.Produto).filter(models.Produto.id == produto_id).first()


def get_produtos(db: Session) -> List[models.Produto]:
    return db.query(models.Produto).order_by(models.Produto.id.desc()).all()


def get_produtos_home(db: Session, *, limite: int = 4) -> List[models.Produto]:
    return (
        db.query(models.Produto)
        .order_by(models.Produto.id.desc())
        .limit(max(limite, 1))
        .all()
    )


def list_produtos(db: Session, apenas_ativos: bool = True) -> List[models.Produto]:
    return get_produtos(db)


def create_produto(
    db: Session,
    produto: schemas.ProdutoCreate,
    *,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
    catalogo_bytes: Optional[bytes] = None,
    catalogo_mime: Optional[str] = None,
    catalogo_nome_arquivo: Optional[str] = None,
) -> models.Produto:
    novo = models.Produto(
        nome=produto.nome.strip(),
        resumo_curto=(produto.resumo_curto or "").strip() or None,
        catalogo_url=(produto.catalogo_url or "").strip() or None,
        imagem_url=PLACEHOLDER_IMAGE_URL,
    )

    if imagem_bytes:
        novo.imagem_bytes = imagem_bytes
        novo.imagem_mime = (imagem_mime or "").strip() or None
        novo.imagem_sha256 = _sha256_hex(imagem_bytes)

    if catalogo_bytes:
        novo.catalogo_bytes = catalogo_bytes
        novo.catalogo_mime = (catalogo_mime or "").strip() or "application/pdf"
        novo.catalogo_nome_arquivo = (catalogo_nome_arquivo or "").strip() or "catalogo.pdf"

    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


def update_produto(
    db: Session,
    *,
    produto_id: int,
    dados: schemas.ProdutoUpdate,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
    catalogo_bytes: Optional[bytes] = None,
    catalogo_mime: Optional[str] = None,
    catalogo_nome_arquivo: Optional[str] = None,
) -> Optional[models.Produto]:
    produto = get_produto(db, produto_id=produto_id)
    if not produto:
        return None

    if dados.nome is not None:
        produto.nome = dados.nome.strip()
    if dados.resumo_curto is not None:
        produto.resumo_curto = (dados.resumo_curto or "").strip() or None
    if dados.catalogo_url is not None:
        produto.catalogo_url = (dados.catalogo_url or "").strip() or None

    if not produto.imagem_url:
        produto.imagem_url = PLACEHOLDER_IMAGE_URL

    if imagem_bytes:
        produto.imagem_bytes = imagem_bytes
        produto.imagem_mime = (imagem_mime or "").strip() or None
        produto.imagem_sha256 = _sha256_hex(imagem_bytes)

    if catalogo_bytes:
        produto.catalogo_bytes = catalogo_bytes
        produto.catalogo_mime = (catalogo_mime or "").strip() or "application/pdf"
        produto.catalogo_nome_arquivo = (catalogo_nome_arquivo or "").strip() or "catalogo.pdf"

    db.commit()
    db.refresh(produto)
    return produto


def delete_produto(db: Session, *, produto_id: int) -> bool:
    produto = get_produto(db, produto_id=produto_id)
    if not produto:
        return False

    db.delete(produto)
    db.commit()
    return True
