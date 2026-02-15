# projeto/crud.py
"""
crud.py
-------
Camada de acesso ao banco (SQLAlchemy) para Produtos.

OBJETIVO DESTA VERSÃO (DO ZERO):
- Garantir que as imagens sejam armazenadas e lidas EXCLUSIVAMENTE do banco (Postgres/Neon).
- NÃO usar filesystem local (Render free tier pode dormir/reiniciar).
- NÃO usar campos inexistentes (ex.: produto.imagem / imagem_etag) que quebravam em runtime.

Observação:
- O model Produto (models.py) deve possuir:
  imagem_bytes, imagem_mime, imagem_sha256, imagem_url (opcional), ativo, etc.
"""

from __future__ import annotations

import hashlib
from typing import Optional, List

from sqlalchemy.orm import Session

import models
import schemas


def _sha256_hex(data: bytes) -> str:
    """Calcula SHA256 (hex) para ETag/cache e integridade."""
    return hashlib.sha256(data).hexdigest()


# =============================================================================
# PATCH MÍNIMO (DB NOT NULL em imagem_url)
# -----------------------------------------------------------------------------
# Seu Postgres/Neon está com a coluna `imagem_url` como NOT NULL.
# Então, inserir/atualizar com imagem_url=None derruba o INSERT/UPDATE com 500.
#
# Como você NÃO autorizou mudar o schema, o menor delta possível é:
# - garantir que imagem_url sempre tenha uma string válida (fallback).
#
# Esse fallback NÃO muda HTML/CSS, NÃO muda rotas, NÃO muda templates.
# Só evita NULL no banco.
# =============================================================================
PLACEHOLDER_IMAGE_URL = "/static/images/placeholder.png"


# =============================================================================
# READ
# =============================================================================

def get_produto(db: Session, *, produto_id: int) -> Optional[models.Produto]:
    """Busca 1 produto por ID."""
    return db.query(models.Produto).filter(models.Produto.id == produto_id).first()


def get_produtos(db: Session) -> List[models.Produto]:
    """Lista todos os produtos (admin)."""
    return (
        db.query(models.Produto)
        .order_by(models.Produto.id.desc())
        .all()
    )


def get_produtos_ativos(db: Session) -> List[models.Produto]:
    """Lista produtos ativos (vitrine)."""
    return (
        db.query(models.Produto)
        .filter(models.Produto.ativo.is_(True))
        .order_by(models.Produto.id.desc())
        .all()
    )


# =============================================================================
# COMPATIBILIDADE (PATCH MÍNIMO)
# -----------------------------------------------------------------------------
# Seu main.py em produção (Render) está chamando:
#   crud.list_produtos(db, apenas_ativos=True/False)
#
# Porém, o crud.py do projeto não possuía essa função.
# Isso causava:
#   AttributeError: module 'crud' has no attribute 'list_produtos'
# e derrubava a rota "/" com 500.
#
# Para corrigir SEM mexer em rotas, templates ou arquitetura, criamos um ALIAS
# compatível, reaproveitando as funções já existentes:
#   - get_produtos_ativos(db)
#   - get_produtos(db)
#
# Assim o delta é mínimo e não altera o comportamento esperado do sistema.
# =============================================================================

def list_produtos(db: Session, apenas_ativos: bool = True) -> List[models.Produto]:
    """
    Alias de compatibilidade para código que espera `crud.list_produtos`.

    - apenas_ativos=True  -> lista só ativos (vitrine)
    - apenas_ativos=False -> lista todos (admin)

    Comentário (risco/decisão):
    - Isso NÃO altera schema, NÃO altera templates, NÃO altera rotas.
    - Apenas evita crash por falta de função.
    """
    if apenas_ativos:
        return get_produtos_ativos(db)
    return get_produtos(db)


# =============================================================================
# CREATE / UPDATE
# =============================================================================

def create_produto(
    db: Session,
    produto: schemas.ProdutoCreate,
    *,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> models.Produto:
    """
    Cria produto.

    IMPORTANTE:
    - Se vier imagem_bytes, salvamos no DB (imagem_bytes/mime/sha256).
    - NÃO escrevemos nada em disco.
    """
    novo = models.Produto(
        nome=produto.nome,
        descricao=(produto.descricao or "").strip(),
        valor=float(produto.valor),
        ativo=True,
    )

    # -------------------------------------------------------------------------
    # PATCH MÍNIMO:
    # O DB exige imagem_url NOT NULL, então garantimos um valor string.
    # Se você servir imagens via /media/produto/{id}, o placeholder é só fallback.
    # -------------------------------------------------------------------------
    # Nota: mesmo quando houver imagem_bytes, manteremos imagem_url preenchida
    # para não violar o NOT NULL e para manter compatibilidade com templates antigos.
    novo.imagem_url = PLACEHOLDER_IMAGE_URL

    if imagem_bytes:
        # Comentário: armazenamento confiável no Postgres/Neon
        novo.imagem_bytes = imagem_bytes
        novo.imagem_mime = (imagem_mime or "").strip() or None
        novo.imagem_sha256 = _sha256_hex(imagem_bytes)

        # PATCH: NÃO pode ser None por causa do NOT NULL
        # (antes: novo.imagem_url = None)
        novo.imagem_url = PLACEHOLDER_IMAGE_URL

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
) -> Optional[models.Produto]:
    """
    Atualiza produto existente.

    Regras:
    - Só atualiza campos que vierem preenchidos.
    - Se vier imagem_bytes, substitui a imagem e recalcula sha256.
    """
    p = get_produto(db, produto_id=produto_id)
    if not p:
        return None

    # Campos básicos
    if dados.nome is not None:
        p.nome = dados.nome
    if dados.descricao is not None:
        p.descricao = dados.descricao
    if dados.valor is not None:
        p.valor = float(dados.valor)
    if dados.ativo is not None:
        p.ativo = bool(dados.ativo)

    # -------------------------------------------------------------------------
    # PATCH MÍNIMO defensivo:
    # garante que imagem_url nunca esteja None no objeto (DB NOT NULL).
    # -------------------------------------------------------------------------
    if getattr(p, "imagem_url", None) is None:
        p.imagem_url = PLACEHOLDER_IMAGE_URL

    # Imagem (DB)
    if imagem_bytes:
        p.imagem_bytes = imagem_bytes
        p.imagem_mime = (imagem_mime or "").strip() or None
        p.imagem_sha256 = _sha256_hex(imagem_bytes)

        # PATCH: NÃO pode ser None por causa do NOT NULL
        # (antes: p.imagem_url = None)
        if not p.imagem_url:
            p.imagem_url = PLACEHOLDER_IMAGE_URL

    db.commit()
    db.refresh(p)
    return p


# =============================================================================
# DELETE
# =============================================================================

def delete_produto(db: Session, *, produto_id: int) -> bool:
    """Remove produto."""
    p = get_produto(db, produto_id=produto_id)
    if not p:
        return False

    db.delete(p)
    db.commit()
    return True
