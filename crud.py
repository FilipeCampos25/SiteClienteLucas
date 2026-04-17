from __future__ import annotations

import hashlib
from typing import List, Optional

from sqlalchemy.orm import Session

import models
import schemas

PLACEHOLDER_IMAGE_URL = "/static/images/placeholder.png"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _apply_image_data(
    produto: models.Produto,
    *,
    image_bytes_attr: str,
    image_mime_attr: str,
    image_sha_attr: str,
    image_bytes: Optional[bytes],
    image_mime: Optional[str],
) -> None:
    if image_bytes is None:
        return

    setattr(produto, image_bytes_attr, image_bytes)
    setattr(produto, image_mime_attr, (image_mime or "").strip() or None)
    setattr(produto, image_sha_attr, _sha256_hex(image_bytes))


def get_produto(db: Session, *, produto_id: int) -> Optional[models.Produto]:
    return db.query(models.Produto).filter(models.Produto.id == produto_id).first()


def get_produtos(db: Session, *, categoria_slug: Optional[str] = None) -> List[models.Produto]:
    query = db.query(models.Produto)
    if categoria_slug:
        query = query.filter(models.Produto.categoria_slug == categoria_slug)
    return query.order_by(models.Produto.id.desc()).all()


def get_produtos_home(db: Session, *, limite: int = 4) -> List[models.Produto]:
    return (
        db.query(models.Produto)
        .order_by(models.Produto.id.desc())
        .limit(max(limite, 1))
        .all()
    )


def list_produtos(
    db: Session,
    apenas_ativos: bool = True,
    *,
    categoria_slug: Optional[str] = None,
) -> List[models.Produto]:
    return get_produtos(db, categoria_slug=categoria_slug)


def create_produto(
    db: Session,
    produto: schemas.ProdutoCreate,
    *,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
    imagem_medidas_bytes: Optional[bytes] = None,
    imagem_medidas_mime: Optional[str] = None,
) -> models.Produto:
    novo = models.Produto(
        nome=produto.nome.strip(),
        resumo_curto=(produto.resumo_curto or "").strip() or None,
        categoria_slug=(produto.categoria_slug or "").strip() or None,
        imagem_url=PLACEHOLDER_IMAGE_URL,
    )

    _apply_image_data(
        novo,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )
    _apply_image_data(
        novo,
        image_bytes_attr="imagem_medidas_bytes",
        image_mime_attr="imagem_medidas_mime",
        image_sha_attr="imagem_medidas_sha256",
        image_bytes=imagem_medidas_bytes,
        image_mime=imagem_medidas_mime,
    )

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
    imagem_medidas_bytes: Optional[bytes] = None,
    imagem_medidas_mime: Optional[str] = None,
) -> Optional[models.Produto]:
    produto = get_produto(db, produto_id=produto_id)
    if not produto:
        return None

    if dados.nome is not None:
        produto.nome = dados.nome.strip()
    if dados.resumo_curto is not None:
        produto.resumo_curto = (dados.resumo_curto or "").strip() or None
    if dados.categoria_slug is not None:
        produto.categoria_slug = (dados.categoria_slug or "").strip() or None

    if not produto.imagem_url:
        produto.imagem_url = PLACEHOLDER_IMAGE_URL

    _apply_image_data(
        produto,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )
    _apply_image_data(
        produto,
        image_bytes_attr="imagem_medidas_bytes",
        image_mime_attr="imagem_medidas_mime",
        image_sha_attr="imagem_medidas_sha256",
        image_bytes=imagem_medidas_bytes,
        image_mime=imagem_medidas_mime,
    )

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
