from __future__ import annotations

import hashlib
from typing import List, Optional

from sqlalchemy.orm import Session

import models
import schemas

PLACEHOLDER_IMAGE_URL = "/static/images/placeholder.png"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean_optional_str(value: Optional[str]) -> Optional[str]:
    return (value or "").strip() or None


def _field_was_provided(schema_obj: object, field_name: str) -> bool:
    model_fields_set = getattr(schema_obj, "model_fields_set", None)
    if model_fields_set is not None:
        return field_name in model_fields_set

    fields_set = getattr(schema_obj, "__fields_set__", None)
    if fields_set is not None:
        return field_name in fields_set

    return getattr(schema_obj, field_name, None) is not None


def _apply_image_data(
    target: object,
    *,
    image_bytes_attr: str,
    image_mime_attr: str,
    image_sha_attr: str,
    image_bytes: Optional[bytes],
    image_mime: Optional[str],
) -> None:
    if image_bytes is None:
        return

    setattr(target, image_bytes_attr, image_bytes)
    setattr(target, image_mime_attr, _clean_optional_str(image_mime))
    setattr(target, image_sha_attr, _sha256_hex(image_bytes))


def _clear_image_data(
    target: object,
    *,
    image_bytes_attr: str,
    image_mime_attr: str,
    image_sha_attr: str,
) -> None:
    setattr(target, image_bytes_attr, None)
    setattr(target, image_mime_attr, None)
    setattr(target, image_sha_attr, None)


def _next_categoria_ordem(db: Session) -> int:
    ultima = db.query(models.Categoria).order_by(models.Categoria.ordem_exibicao.desc(), models.Categoria.id.desc()).first()
    return int(getattr(ultima, "ordem_exibicao", 0) or 0) + 1


def _next_subcategoria_ordem(db: Session, categoria_slug: str) -> int:
    ultima = (
        db.query(models.Subcategoria)
        .filter(models.Subcategoria.categoria_slug == categoria_slug)
        .order_by(models.Subcategoria.ordem_exibicao.desc(), models.Subcategoria.id.desc())
        .first()
    )
    return int(getattr(ultima, "ordem_exibicao", 0) or 0) + 1


def _next_produto_ordem(
    db: Session,
    categoria_slug: Optional[str],
    subcategoria_slug: Optional[str],
) -> int:
    ultima = (
        db.query(models.Produto)
        .filter(
            models.Produto.categoria_slug == categoria_slug,
            models.Produto.subcategoria_slug == subcategoria_slug,
        )
        .order_by(models.Produto.ordem_exibicao.desc(), models.Produto.id.desc())
        .first()
    )
    return int(getattr(ultima, "ordem_exibicao", 0) or 0) + 1


def _next_quem_somos_ordem(db: Session) -> int:
    ultima = (
        db.query(models.QuemSomosImagem)
        .order_by(models.QuemSomosImagem.ordem_exibicao.desc(), models.QuemSomosImagem.id.desc())
        .first()
    )
    return int(getattr(ultima, "ordem_exibicao", 0) or 0) + 1


def list_categorias(db: Session) -> List[models.Categoria]:
    return (
        db.query(models.Categoria)
        .order_by(models.Categoria.ordem_exibicao.asc(), models.Categoria.id.asc())
        .all()
    )


def get_categoria(
    db: Session,
    *,
    categoria_id: Optional[int] = None,
    slug: Optional[str] = None,
) -> Optional[models.Categoria]:
    query = db.query(models.Categoria)
    if categoria_id is not None:
        return query.filter(models.Categoria.id == categoria_id).first()
    if slug is not None:
        return query.filter(models.Categoria.slug == slug).first()
    return None


def create_categoria(
    db: Session,
    dados: schemas.CategoriaCreate,
    *,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> models.Categoria:
    if get_categoria(db, slug=dados.slug):
        raise ValueError("Ja existe uma categoria com esse slug")

    categoria = models.Categoria(
        slug=dados.slug.strip(),
        nome=dados.nome.strip(),
        nome_exibicao=dados.nome_exibicao.strip(),
        subtitulo_exibicao=_clean_optional_str(dados.subtitulo_exibicao),
        imagem_url=_clean_optional_str(dados.imagem_url) or PLACEHOLDER_IMAGE_URL,
        ordem_exibicao=dados.ordem_exibicao if dados.ordem_exibicao is not None else _next_categoria_ordem(db),
    )
    _apply_image_data(
        categoria,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return categoria


def update_categoria(
    db: Session,
    *,
    categoria_id: int,
    dados: schemas.CategoriaUpdate,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> Optional[models.Categoria]:
    categoria = get_categoria(db, categoria_id=categoria_id)
    if not categoria:
        return None

    slug_atual = categoria.slug
    novo_slug = (dados.slug or "").strip() if dados.slug is not None else slug_atual
    if novo_slug != slug_atual:
        existente = get_categoria(db, slug=novo_slug)
        if existente and existente.id != categoria.id:
            raise ValueError("Ja existe uma categoria com esse slug")

    if dados.slug is not None:
        categoria.slug = novo_slug
    if dados.nome is not None:
        categoria.nome = dados.nome.strip()
    if dados.nome_exibicao is not None:
        categoria.nome_exibicao = dados.nome_exibicao.strip()
    if _field_was_provided(dados, "subtitulo_exibicao"):
        categoria.subtitulo_exibicao = _clean_optional_str(dados.subtitulo_exibicao)
    if dados.imagem_url is not None:
        categoria.imagem_url = _clean_optional_str(dados.imagem_url) or PLACEHOLDER_IMAGE_URL
    if dados.ordem_exibicao is not None:
        categoria.ordem_exibicao = dados.ordem_exibicao
    if not categoria.imagem_url:
        categoria.imagem_url = PLACEHOLDER_IMAGE_URL
    _apply_image_data(
        categoria,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )

    if novo_slug != slug_atual:
        (
            db.query(models.Subcategoria)
            .filter(models.Subcategoria.categoria_slug == slug_atual)
            .update({models.Subcategoria.categoria_slug: novo_slug}, synchronize_session=False)
        )
        (
            db.query(models.Produto)
            .filter(models.Produto.categoria_slug == slug_atual)
            .update({models.Produto.categoria_slug: novo_slug}, synchronize_session=False)
        )

    db.commit()
    db.refresh(categoria)
    return categoria


def delete_categoria(db: Session, *, categoria_id: int) -> bool:
    categoria = get_categoria(db, categoria_id=categoria_id)
    if not categoria:
        return False

    slug = categoria.slug
    (
        db.query(models.Produto)
        .filter(models.Produto.categoria_slug == slug)
        .delete(synchronize_session=False)
    )
    (
        db.query(models.Subcategoria)
        .filter(models.Subcategoria.categoria_slug == slug)
        .delete(synchronize_session=False)
    )
    db.delete(categoria)
    db.commit()
    return True


def list_subcategorias(db: Session, *, categoria_slug: Optional[str] = None) -> List[models.Subcategoria]:
    query = db.query(models.Subcategoria)
    if categoria_slug:
        query = query.filter(models.Subcategoria.categoria_slug == categoria_slug)
    return query.order_by(
        models.Subcategoria.categoria_slug.asc(),
        models.Subcategoria.ordem_exibicao.asc(),
        models.Subcategoria.id.asc(),
    ).all()


def get_subcategoria(
    db: Session,
    *,
    subcategoria_id: Optional[int] = None,
    categoria_slug: Optional[str] = None,
    slug: Optional[str] = None,
) -> Optional[models.Subcategoria]:
    query = db.query(models.Subcategoria)
    if subcategoria_id is not None:
        return query.filter(models.Subcategoria.id == subcategoria_id).first()
    if categoria_slug is not None and slug is not None:
        return query.filter(
            models.Subcategoria.categoria_slug == categoria_slug,
            models.Subcategoria.slug == slug,
        ).first()
    return None


def create_subcategoria(
    db: Session,
    dados: schemas.SubcategoriaCreate,
    *,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> models.Subcategoria:
    if get_subcategoria(db, categoria_slug=dados.categoria_slug, slug=dados.slug):
        raise ValueError("Ja existe uma subcategoria com esse slug nessa categoria")

    subcategoria = models.Subcategoria(
        categoria_slug=dados.categoria_slug.strip(),
        slug=dados.slug.strip(),
        nome=dados.nome.strip(),
        nome_exibicao=dados.nome_exibicao.strip(),
        imagem_url=_clean_optional_str(dados.imagem_url) or PLACEHOLDER_IMAGE_URL,
        ordem_exibicao=(
            dados.ordem_exibicao
            if dados.ordem_exibicao is not None
            else _next_subcategoria_ordem(db, dados.categoria_slug.strip())
        ),
    )
    _apply_image_data(
        subcategoria,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )
    db.add(subcategoria)
    db.commit()
    db.refresh(subcategoria)
    return subcategoria


def update_subcategoria(
    db: Session,
    *,
    subcategoria_id: int,
    dados: schemas.SubcategoriaUpdate,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> Optional[models.Subcategoria]:
    subcategoria = get_subcategoria(db, subcategoria_id=subcategoria_id)
    if not subcategoria:
        return None

    categoria_atual = subcategoria.categoria_slug
    slug_atual = subcategoria.slug
    nova_categoria = (dados.categoria_slug or "").strip() if dados.categoria_slug is not None else categoria_atual
    novo_slug = (dados.slug or "").strip() if dados.slug is not None else slug_atual

    existente = get_subcategoria(db, categoria_slug=nova_categoria, slug=novo_slug)
    if existente and existente.id != subcategoria.id:
        raise ValueError("Ja existe uma subcategoria com esse slug nessa categoria")

    if dados.categoria_slug is not None:
        subcategoria.categoria_slug = nova_categoria
    if dados.slug is not None:
        subcategoria.slug = novo_slug
    if dados.nome is not None:
        subcategoria.nome = dados.nome.strip()
    if dados.nome_exibicao is not None:
        subcategoria.nome_exibicao = dados.nome_exibicao.strip()
    if dados.imagem_url is not None:
        subcategoria.imagem_url = _clean_optional_str(dados.imagem_url) or PLACEHOLDER_IMAGE_URL
    if dados.ordem_exibicao is not None:
        subcategoria.ordem_exibicao = dados.ordem_exibicao
    if not subcategoria.imagem_url:
        subcategoria.imagem_url = PLACEHOLDER_IMAGE_URL
    _apply_image_data(
        subcategoria,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )

    if categoria_atual != nova_categoria or slug_atual != novo_slug:
        (
            db.query(models.Produto)
            .filter(
                models.Produto.categoria_slug == categoria_atual,
                models.Produto.subcategoria_slug == slug_atual,
            )
            .update(
                {
                    models.Produto.categoria_slug: nova_categoria,
                    models.Produto.subcategoria_slug: novo_slug,
                },
                synchronize_session=False,
            )
        )

    db.commit()
    db.refresh(subcategoria)
    return subcategoria


def delete_subcategoria(db: Session, *, subcategoria_id: int) -> bool:
    subcategoria = get_subcategoria(db, subcategoria_id=subcategoria_id)
    if not subcategoria:
        return False

    (
        db.query(models.Produto)
        .filter(
            models.Produto.categoria_slug == subcategoria.categoria_slug,
            models.Produto.subcategoria_slug == subcategoria.slug,
        )
        .delete(synchronize_session=False)
    )
    db.delete(subcategoria)
    db.commit()
    return True


def list_quem_somos_imagens(db: Session) -> List[models.QuemSomosImagem]:
    return (
        db.query(models.QuemSomosImagem)
        .order_by(models.QuemSomosImagem.ordem_exibicao.asc(), models.QuemSomosImagem.id.asc())
        .all()
    )


def get_quem_somos_imagem(db: Session, *, imagem_id: int) -> Optional[models.QuemSomosImagem]:
    return db.query(models.QuemSomosImagem).filter(models.QuemSomosImagem.id == imagem_id).first()


def create_quem_somos_imagem(
    db: Session,
    dados: schemas.QuemSomosImagemCreate,
    *,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> models.QuemSomosImagem:
    imagem = models.QuemSomosImagem(
        alt_texto=_clean_optional_str(dados.alt_texto),
        imagem_url=_clean_optional_str(dados.imagem_url) or PLACEHOLDER_IMAGE_URL,
        ordem_exibicao=(
            dados.ordem_exibicao
            if dados.ordem_exibicao is not None
            else _next_quem_somos_ordem(db)
        ),
    )
    _apply_image_data(
        imagem,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )
    db.add(imagem)
    db.commit()
    db.refresh(imagem)
    return imagem


def update_quem_somos_imagem(
    db: Session,
    *,
    imagem_id: int,
    dados: schemas.QuemSomosImagemUpdate,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> Optional[models.QuemSomosImagem]:
    imagem = get_quem_somos_imagem(db, imagem_id=imagem_id)
    if not imagem:
        return None

    if _field_was_provided(dados, "alt_texto"):
        imagem.alt_texto = _clean_optional_str(dados.alt_texto)
    if dados.imagem_url is not None:
        imagem.imagem_url = _clean_optional_str(dados.imagem_url) or PLACEHOLDER_IMAGE_URL
    if dados.ordem_exibicao is not None:
        imagem.ordem_exibicao = dados.ordem_exibicao
    if not imagem.imagem_url:
        imagem.imagem_url = PLACEHOLDER_IMAGE_URL

    _apply_image_data(
        imagem,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )

    db.commit()
    db.refresh(imagem)
    return imagem


def delete_quem_somos_imagem(db: Session, *, imagem_id: int) -> bool:
    imagem = get_quem_somos_imagem(db, imagem_id=imagem_id)
    if not imagem:
        return False

    db.delete(imagem)
    db.commit()
    return True


def get_site_imagem(db: Session, *, chave: str) -> Optional[models.SiteImagem]:
    return db.query(models.SiteImagem).filter(models.SiteImagem.chave == chave.strip()).first()


def ensure_site_imagem(
    db: Session,
    *,
    chave: str,
    alt_texto: Optional[str],
    imagem_url: Optional[str],
) -> models.SiteImagem:
    imagem = get_site_imagem(db, chave=chave)
    if imagem:
        mudou = False
        if not _clean_optional_str(imagem.alt_texto):
            imagem.alt_texto = _clean_optional_str(alt_texto)
            mudou = True
        if not _clean_optional_str(imagem.imagem_url) and not getattr(imagem, "imagem_bytes", None):
            imagem.imagem_url = _clean_optional_str(imagem_url) or PLACEHOLDER_IMAGE_URL
            mudou = True
        if mudou:
            db.commit()
            db.refresh(imagem)
        return imagem

    nova_imagem = models.SiteImagem(
        chave=chave.strip(),
        alt_texto=_clean_optional_str(alt_texto),
        imagem_url=_clean_optional_str(imagem_url) or PLACEHOLDER_IMAGE_URL,
    )
    db.add(nova_imagem)
    db.commit()
    db.refresh(nova_imagem)
    return nova_imagem


def upsert_site_imagem(
    db: Session,
    *,
    chave: str,
    dados: schemas.SiteImagemUpdate,
    default_alt_texto: Optional[str] = None,
    default_imagem_url: Optional[str] = None,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
) -> models.SiteImagem:
    chave_normalizada = chave.strip()
    if not chave_normalizada:
        raise ValueError("Informe uma chave valida para a imagem do site")

    imagem = get_site_imagem(db, chave=chave_normalizada)
    if not imagem:
        imagem = models.SiteImagem(
            chave=chave_normalizada,
            alt_texto=_clean_optional_str(dados.alt_texto) or _clean_optional_str(default_alt_texto),
            imagem_url=(
                _clean_optional_str(dados.imagem_url)
                or _clean_optional_str(default_imagem_url)
                or PLACEHOLDER_IMAGE_URL
            ),
        )
        db.add(imagem)
    else:
        if _field_was_provided(dados, "alt_texto"):
            imagem.alt_texto = _clean_optional_str(dados.alt_texto) or _clean_optional_str(default_alt_texto)
        if dados.imagem_url is not None:
            imagem.imagem_url = (
                _clean_optional_str(dados.imagem_url)
                or _clean_optional_str(default_imagem_url)
                or PLACEHOLDER_IMAGE_URL
            )
        if not _clean_optional_str(imagem.imagem_url) and not getattr(imagem, "imagem_bytes", None):
            imagem.imagem_url = _clean_optional_str(default_imagem_url) or PLACEHOLDER_IMAGE_URL

    _apply_image_data(
        imagem,
        image_bytes_attr="imagem_bytes",
        image_mime_attr="imagem_mime",
        image_sha_attr="imagem_sha256",
        image_bytes=imagem_bytes,
        image_mime=imagem_mime,
    )

    db.commit()
    db.refresh(imagem)
    return imagem


def get_site_config(db: Session, *, chave: str) -> Optional[models.SiteConfig]:
    return db.query(models.SiteConfig).filter(models.SiteConfig.chave == chave.strip()).first()


def get_site_config_map(db: Session) -> dict[str, str]:
    configs = db.query(models.SiteConfig).all()
    return {config.chave: config.valor or "" for config in configs}


def ensure_site_config_defaults(db: Session, defaults: dict[str, str]) -> dict[str, str]:
    existentes = get_site_config_map(db)
    mudou = False

    for chave, valor_padrao in defaults.items():
        if chave in existentes:
            continue
        db.add(models.SiteConfig(chave=chave, valor=valor_padrao))
        existentes[chave] = valor_padrao
        mudou = True

    if mudou:
        db.commit()

    return existentes


def upsert_site_configs(db: Session, dados: dict[str, str]) -> dict[str, str]:
    for chave, valor in dados.items():
        chave_normalizada = chave.strip()
        if not chave_normalizada:
            continue

        config = get_site_config(db, chave=chave_normalizada)
        if config:
            config.valor = valor
            continue

        db.add(models.SiteConfig(chave=chave_normalizada, valor=valor))

    db.commit()
    return get_site_config_map(db)


def get_produto(db: Session, *, produto_id: int) -> Optional[models.Produto]:
    return db.query(models.Produto).filter(models.Produto.id == produto_id).first()


def get_produtos(
    db: Session,
    *,
    categoria_slug: Optional[str] = None,
    subcategoria_slug: Optional[str] = None,
) -> List[models.Produto]:
    query = db.query(models.Produto)
    if categoria_slug:
        query = query.filter(models.Produto.categoria_slug == categoria_slug)
    if subcategoria_slug:
        query = query.filter(models.Produto.subcategoria_slug == subcategoria_slug)
    return query.order_by(
        models.Produto.categoria_slug.asc(),
        models.Produto.subcategoria_slug.asc(),
        models.Produto.ordem_exibicao.asc(),
        models.Produto.id.desc(),
    ).all()


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
    subcategoria_slug: Optional[str] = None,
) -> List[models.Produto]:
    return get_produtos(
        db,
        categoria_slug=categoria_slug,
        subcategoria_slug=subcategoria_slug,
    )


def create_produto(
    db: Session,
    produto: schemas.ProdutoCreate,
    *,
    imagem_bytes: Optional[bytes] = None,
    imagem_mime: Optional[str] = None,
    imagem_medidas_bytes: Optional[bytes] = None,
    imagem_medidas_mime: Optional[str] = None,
    imagem_extra_bytes: Optional[bytes] = None,
    imagem_extra_mime: Optional[str] = None,
) -> models.Produto:
    novo = models.Produto(
        nome=produto.nome.strip(),
        resumo_curto=_clean_optional_str(produto.resumo_curto),
        categoria_slug=_clean_optional_str(produto.categoria_slug),
        subcategoria_slug=_clean_optional_str(produto.subcategoria_slug),
        imagem_url=PLACEHOLDER_IMAGE_URL,
        ordem_exibicao=(
            produto.ordem_exibicao
            if produto.ordem_exibicao is not None
            else _next_produto_ordem(
                db,
                _clean_optional_str(produto.categoria_slug),
                _clean_optional_str(produto.subcategoria_slug),
            )
        ),
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
    _apply_image_data(
        novo,
        image_bytes_attr="imagem_extra_bytes",
        image_mime_attr="imagem_extra_mime",
        image_sha_attr="imagem_extra_sha256",
        image_bytes=imagem_extra_bytes,
        image_mime=imagem_extra_mime,
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
    imagem_extra_bytes: Optional[bytes] = None,
    imagem_extra_mime: Optional[str] = None,
    remover_imagem: bool = False,
    remover_imagem_medidas: bool = False,
    remover_imagem_extra: bool = False,
) -> Optional[models.Produto]:
    produto = get_produto(db, produto_id=produto_id)
    if not produto:
        return None

    if dados.nome is not None:
        produto.nome = dados.nome.strip()
    if _field_was_provided(dados, "resumo_curto"):
        produto.resumo_curto = _clean_optional_str(dados.resumo_curto)
    if dados.categoria_slug is not None:
        produto.categoria_slug = _clean_optional_str(dados.categoria_slug)
    if _field_was_provided(dados, "subcategoria_slug"):
        produto.subcategoria_slug = _clean_optional_str(dados.subcategoria_slug)
    if dados.ordem_exibicao is not None:
        produto.ordem_exibicao = dados.ordem_exibicao

    if not produto.imagem_url:
        produto.imagem_url = PLACEHOLDER_IMAGE_URL

    if remover_imagem:
        produto.imagem_url = PLACEHOLDER_IMAGE_URL
        _clear_image_data(
            produto,
            image_bytes_attr="imagem_bytes",
            image_mime_attr="imagem_mime",
            image_sha_attr="imagem_sha256",
        )
    if remover_imagem_medidas:
        _clear_image_data(
            produto,
            image_bytes_attr="imagem_medidas_bytes",
            image_mime_attr="imagem_medidas_mime",
            image_sha_attr="imagem_medidas_sha256",
        )
    if remover_imagem_extra:
        _clear_image_data(
            produto,
            image_bytes_attr="imagem_extra_bytes",
            image_mime_attr="imagem_extra_mime",
            image_sha_attr="imagem_extra_sha256",
        )

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
    _apply_image_data(
        produto,
        image_bytes_attr="imagem_extra_bytes",
        image_mime_attr="imagem_extra_mime",
        image_sha_attr="imagem_extra_sha256",
        image_bytes=imagem_extra_bytes,
        image_mime=imagem_extra_mime,
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
