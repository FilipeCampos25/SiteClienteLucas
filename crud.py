from sqlalchemy.orm import Session
from sqlalchemy import desc
import hashlib
import models, schemas

def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def get_produtos_ativos(db: Session):
    return (
        db.query(models.Produto)
        .filter(models.Produto.ativo == True)
        .order_by(desc(models.Produto.atualizado_em), desc(models.Produto.criado_em))
        .all()
    )

def get_produto(db: Session, produto_id: int):
    return (
        db.query(models.Produto)
        .filter(models.Produto.id == produto_id, models.Produto.ativo == True)
        .first()
    )

def create_produto(db: Session, produto: schemas.ProdutoCreate, *, imagem_bytes: bytes | None = None, imagem_mime: str | None = None):
    db_produto = models.Produto(**produto.model_dump() if hasattr(produto, "model_dump") else produto.dict())
    if imagem_bytes:
        db_produto.imagem_bytes = imagem_bytes
        db_produto.imagem_mime = imagem_mime or "application/octet-stream"
        db_produto.imagem_sha256 = _compute_sha256(imagem_bytes)

    db.add(db_produto)
    db.commit()
    db.refresh(db_produto)

    # Se tem imagem no DB, padroniza a URL do frontend para o endpoint de mídia
    if db_produto.imagem_bytes and not db_produto.imagem_url:
        db_produto.imagem_url = f"/media/produto/{db_produto.id}"
        db.commit()
        db.refresh(db_produto)

    return db_produto

def update_produto(db: Session, produto_id: int, produto: schemas.ProdutoUpdate, *, imagem_bytes: bytes | None = None, imagem_mime: str | None = None):
    db_produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not db_produto:
        return None

    data = produto.model_dump(exclude_unset=True) if hasattr(produto, "model_dump") else produto.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(db_produto, key, value)

    if imagem_bytes:
        db_produto.imagem_bytes = imagem_bytes
        db_produto.imagem_mime = imagem_mime or "application/octet-stream"
        db_produto.imagem_sha256 = _compute_sha256(imagem_bytes)
        db_produto.imagem_url = f"/media/produto/{produto_id}"

    db.commit()
    db.refresh(db_produto)
    return db_produto

def delete_produto(db: Session, produto_id: int):
    db_produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if db_produto:
        db_produto.ativo = False
        db.commit()
    return db_produto
