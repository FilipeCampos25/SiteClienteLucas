from __future__ import annotations

import io
import os
import re
import unicodedata
from typing import Generator, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import crud
import models
import schemas
from config import ADMIN_PASSWORD, ADMIN_USER, CORS_ORIGINS, FACEBOOK_URL, INSTAGRAM_URL, WHATSAPP_NUMERO
from database import SessionLocal, init_db
from utils import gerar_link_whatsapp, gerar_link_whatsapp_text, telefone_visivel

app = FastAPI(title="Casa das Cantoneiras")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "change-this-secret-key"),
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals.update(
    WHATSAPP_NUMERO=WHATSAPP_NUMERO or "",
    WHATSAPP_DISPLAY=telefone_visivel(),
    WHATSAPP_LINK=gerar_link_whatsapp([]),
    INSTAGRAM_URL=INSTAGRAM_URL or "",
    FACEBOOK_URL=FACEBOOK_URL or "",
    LOGO_URL="/static/images/logomarca.png",
)

DEFAULT_CATEGORIAS_HOME = [
    {
        "slug": "cantoneiras-de-aluminio",
        "nome": "Cantoneiras de Aluminio",
        "nome_exibicao": "Cantoneiras de Alumínio",
        "subtitulo_exibicao": "",
        "imagem_url": "/static/images/img3.jpeg",
    },
    {
        "slug": "kits-para-montagem",
        "nome": "Cantoneiras para Suporte",
        "nome_exibicao": "Cantoneiras para Suporte",
        "subtitulo_exibicao": "",
        "imagem_url": "/static/images/img5.jpeg",
    },
    {
        "slug": "cantoneira-suporte-para-prateleira",
        "nome": "Acessorios",
        "nome_exibicao": "Acessórios",
        "subtitulo_exibicao": "Ferramentas",
        "imagem_url": "/static/images/img6.jpeg",
    },
    {
        "slug": "acessorios",
        "nome": "Faca voce mesmo",
        "nome_exibicao": "Faça você mesmo",
        "subtitulo_exibicao": "",
        "imagem_url": "/static/images/img8.jpeg",
    },
]
DEFAULT_SUBCATEGORIAS_POR_CATEGORIA = {
    "cantoneira-suporte-para-prateleira": [
        {
            "slug": "alicate-universal",
            "nome": "Alicate Universal",
            "nome_exibicao": "Alicate Universal",
            "imagem_url": "/static/images/alicate_universal.jpg",
        },
        {
            "slug": "chave-philips",
            "nome": "Chave Philips",
            "nome_exibicao": "Chave Philips",
            "imagem_url": "/static/images/Chave_Philips.jpeg",
        },
        {
            "slug": "kit-bits",
            "nome": "Kit Bits",
            "nome_exibicao": "Kit Bits",
            "imagem_url": "/static/images/Kit_Bits.jpg",
        },
        {
            "slug": "estilete",
            "nome": "Estilete",
            "nome_exibicao": "Estilete",
            "imagem_url": "/static/images/Estilete.jpeg",
        },
        {
            "slug": "trena",
            "nome": "Trena",
            "nome_exibicao": "Trena",
            "imagem_url": "/static/images/Trena.jpeg",
        },
    ],
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_catalogo_inicial() -> None:
    db = SessionLocal()
    try:
        if crud.list_categorias(db):
            return

        for idx, categoria in enumerate(DEFAULT_CATEGORIAS_HOME, start=1):
            crud.create_categoria(
                db,
                schemas.CategoriaCreate(
                    slug=categoria["slug"],
                    nome=categoria["nome"],
                    nome_exibicao=categoria["nome_exibicao"],
                    subtitulo_exibicao=categoria.get("subtitulo_exibicao", ""),
                    imagem_url=categoria.get("imagem_url", ""),
                    ordem_exibicao=idx,
                ),
            )

        for categoria_slug, subcategorias in DEFAULT_SUBCATEGORIAS_POR_CATEGORIA.items():
            for idx, subcategoria in enumerate(subcategorias, start=1):
                crud.create_subcategoria(
                    db,
                    schemas.SubcategoriaCreate(
                        categoria_slug=categoria_slug,
                        slug=subcategoria["slug"],
                        nome=subcategoria["nome"],
                        nome_exibicao=subcategoria["nome_exibicao"],
                        imagem_url=subcategoria.get("imagem_url", ""),
                        ordem_exibicao=idx,
                    ),
                )
    finally:
        db.close()


@app.on_event("startup")
def _startup() -> None:
    init_db()
    _seed_catalogo_inicial()


def _slugify(value: Optional[str]) -> str:
    texto = (value or "").strip()
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", texto)
    ascii_texto = normalizado.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_texto).strip("-").lower()


def _texto_obrigatorio(value: Optional[str], mensagem: str) -> str:
    texto = (value or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail=mensagem)
    return texto


def _ordem_normalizada(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return max(int(value), 0)


def _schema_dump(schema_obj: object) -> dict[str, object]:
    if hasattr(schema_obj, "model_dump"):
        return schema_obj.model_dump()  # type: ignore[no-any-return]
    if hasattr(schema_obj, "dict"):
        return schema_obj.dict()  # type: ignore[no-any-return]
    raise TypeError("Objeto de schema invalido para serializacao")


def _categoria_image_url(categoria: models.Categoria) -> str:
    if getattr(categoria, "imagem_bytes", None):
        return f"/media/categoria/{categoria.id}/imagem"

    return (getattr(categoria, "imagem_url", None) or "").strip() or crud.PLACEHOLDER_IMAGE_URL


def _subcategoria_image_url(subcategoria: models.Subcategoria) -> str:
    if getattr(subcategoria, "imagem_bytes", None):
        return f"/media/subcategoria/{subcategoria.id}/imagem"

    return (getattr(subcategoria, "imagem_url", None) or "").strip() or crud.PLACEHOLDER_IMAGE_URL


def _categoria_view(categoria: models.Categoria) -> dict[str, Optional[str]]:
    return {
        "id": categoria.id,
        "slug": categoria.slug,
        "nome": categoria.nome,
        "nome_exibicao": categoria.nome_exibicao,
        "subtitulo_exibicao": categoria.subtitulo_exibicao or "",
        "imagem_url": _categoria_image_url(categoria),
        "ordem_exibicao": categoria.ordem_exibicao,
    }


def _subcategoria_view(subcategoria: models.Subcategoria) -> dict[str, Optional[str]]:
    return {
        "id": subcategoria.id,
        "categoria_slug": subcategoria.categoria_slug,
        "slug": subcategoria.slug,
        "nome": subcategoria.nome,
        "nome_exibicao": subcategoria.nome_exibicao,
        "imagem_url": _subcategoria_image_url(subcategoria),
        "ordem_exibicao": subcategoria.ordem_exibicao,
    }


def _catalogo_index(db: Session) -> dict[str, object]:
    categorias = [_categoria_view(categoria) for categoria in crud.list_categorias(db)]
    subcategorias = [_subcategoria_view(subcategoria) for subcategoria in crud.list_subcategorias(db)]

    categorias_por_slug = {categoria["slug"]: categoria for categoria in categorias}
    subcategorias_por_categoria: dict[str, list[dict[str, Optional[str]]]] = {}
    subcategorias_por_chave: dict[tuple[str, str], dict[str, Optional[str]]] = {}

    for subcategoria in subcategorias:
        categoria_slug = str(subcategoria["categoria_slug"])
        subcategorias_por_categoria.setdefault(categoria_slug, []).append(subcategoria)
        subcategorias_por_chave[(categoria_slug, str(subcategoria["slug"]))] = subcategoria

    return {
        "categorias": categorias,
        "categorias_por_slug": categorias_por_slug,
        "subcategorias": subcategorias,
        "subcategorias_por_categoria": subcategorias_por_categoria,
        "subcategorias_por_chave": subcategorias_por_chave,
    }


def _produto_image_url(produto: models.Produto) -> str:
    if getattr(produto, "imagem_bytes", None):
        return f"/media/produto/{produto.id}/imagem"

    url_externa = (getattr(produto, "imagem_url", None) or "").strip()
    if url_externa:
        return url_externa

    return crud.PLACEHOLDER_IMAGE_URL


def _produto_medidas_image_url(produto: models.Produto) -> Optional[str]:
    if getattr(produto, "imagem_medidas_bytes", None):
        return f"/media/produto/{produto.id}/imagem-medidas"
    return None


def _produto_view(
    produto: models.Produto,
    *,
    categorias_por_slug: dict[str, dict[str, Optional[str]]],
    subcategorias_por_chave: dict[tuple[str, str], dict[str, Optional[str]]],
) -> dict[str, Optional[str]]:
    categoria_slug = (getattr(produto, "categoria_slug", None) or "").strip()
    subcategoria_slug = (getattr(produto, "subcategoria_slug", None) or "").strip()
    categoria = categorias_por_slug.get(categoria_slug)
    subcategoria = subcategorias_por_chave.get((categoria_slug, subcategoria_slug))

    return {
        "id": produto.id,
        "nome": produto.nome,
        "resumo_curto": produto.resumo_curto,
        "imagem_url": _produto_image_url(produto),
        "imagem_medidas_url": _produto_medidas_image_url(produto),
        "categoria_slug": categoria_slug or None,
        "categoria_nome_exibicao": categoria["nome_exibicao"] if categoria else None,
        "categoria_url": f"/categorias/{categoria['slug']}" if categoria else None,
        "subcategoria_slug": subcategoria_slug or None,
        "subcategoria_nome_exibicao": subcategoria["nome_exibicao"] if subcategoria else None,
        "subcategoria_url": (
            f"/categorias/{categoria['slug']}/subcategorias/{subcategoria['slug']}"
            if categoria and subcategoria
            else None
        ),
    }


def _convert_to_webp(raw: bytes) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        img.thumbnail((1600, 1600))

        out = io.BytesIO()
        img.save(out, format="WEBP", quality=82, method=6)
        return out.getvalue(), "image/webp"
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie uma imagem valida em PNG, JPG ou WEBP.",
        )


def _load_uploaded_image(upload: Optional[UploadFile]) -> tuple[Optional[bytes], Optional[str]]:
    if not upload or not upload.filename:
        return None, None

    raw = upload.file.read()
    if not raw:
        return None, None

    return _convert_to_webp(raw)


def _admin_credentials() -> tuple[str, str]:
    user = (os.getenv("ADMIN_USER") or ADMIN_USER or "admin").strip()
    password = (os.getenv("ADMIN_PASS") or os.getenv("ADMIN_PASSWORD") or ADMIN_PASSWORD or "").strip()
    if password == "troque_essa_senha":
        password = ""
    return user, password


def _is_admin_authed(request: Request) -> bool:
    return request.session.get("admin_authed") is True


def _auth_admin(request: Request) -> str:
    if _is_admin_authed(request):
        return request.session.get("admin_user", "admin")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _get_categoria(db: Session, slug: str) -> dict[str, Optional[str]]:
    categoria = crud.get_categoria(db, slug=slug)
    if categoria:
        return _categoria_view(categoria)
    raise HTTPException(status_code=404, detail="Categoria nao encontrada")


def _get_subcategorias(db: Session, categoria_slug: str) -> list[dict[str, Optional[str]]]:
    return [_subcategoria_view(subcategoria) for subcategoria in crud.list_subcategorias(db, categoria_slug=categoria_slug)]


def _categoria_exige_subcategoria(db: Session, categoria_slug: Optional[str]) -> bool:
    slug = (categoria_slug or "").strip()
    if not slug:
        return False
    return bool(crud.list_subcategorias(db, categoria_slug=slug))


def _get_subcategoria(db: Session, categoria_slug: str, subcategoria_slug: str) -> dict[str, Optional[str]]:
    subcategoria = crud.get_subcategoria(db, categoria_slug=categoria_slug, slug=subcategoria_slug)
    if subcategoria:
        return _subcategoria_view(subcategoria)
    raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")


def _normalizar_categoria_slug(db: Session, categoria_slug: Optional[str], *, required: bool) -> Optional[str]:
    slug = (categoria_slug or "").strip()
    if not slug:
        if required:
            raise HTTPException(status_code=400, detail="Selecione uma categoria")
        return None
    if not crud.get_categoria(db, slug=slug):
        raise HTTPException(status_code=400, detail="Categoria invalida")
    return slug


def _normalizar_subcategoria_slug(
    db: Session,
    categoria_slug: Optional[str],
    subcategoria_slug: Optional[str],
    *,
    required: bool,
) -> Optional[str]:
    categoria = (categoria_slug or "").strip()
    subcategoria = (subcategoria_slug or "").strip()
    subcategorias_validas = crud.list_subcategorias(db, categoria_slug=categoria)

    if not subcategorias_validas:
        return None
    if not subcategoria:
        if required:
            raise HTTPException(
                status_code=400,
                detail="Produtos dessa categoria precisam estar vinculados a um subcatalogo",
            )
        return None
    if not crud.get_subcategoria(db, categoria_slug=categoria, slug=subcategoria):
        raise HTTPException(status_code=400, detail="Subcatalogo invalido")
    return subcategoria


def _categoria_create_from_form(
    slug: str,
    nome: str,
    nome_exibicao: str,
    subtitulo_exibicao: str,
    imagem_url: Optional[str],
    ordem_exibicao: Optional[int],
) -> schemas.CategoriaCreate:
    nome_normalizado = _texto_obrigatorio(nome, "Informe o nome interno da categoria")
    nome_exibicao_normalizado = _texto_obrigatorio(nome_exibicao, "Informe o nome de exibicao da categoria")
    slug_normalizado = _slugify(slug) or _slugify(nome_exibicao_normalizado) or _slugify(nome_normalizado)
    if not slug_normalizado:
        raise HTTPException(status_code=400, detail="Informe um slug valido para a categoria")

    return schemas.CategoriaCreate(
        slug=slug_normalizado,
        nome=nome_normalizado,
        nome_exibicao=nome_exibicao_normalizado,
        subtitulo_exibicao=(subtitulo_exibicao or "").strip() or None,
        imagem_url=(imagem_url or "").strip() or None,
        ordem_exibicao=_ordem_normalizada(ordem_exibicao),
    )


def _subcategoria_create_from_form(
    db: Session,
    categoria_slug: str,
    slug: str,
    nome: str,
    nome_exibicao: str,
    imagem_url: Optional[str],
    ordem_exibicao: Optional[int],
) -> schemas.SubcategoriaCreate:
    categoria_normalizada = _normalizar_categoria_slug(db, categoria_slug, required=True)
    nome_normalizado = _texto_obrigatorio(nome, "Informe o nome interno do subcatalogo")
    nome_exibicao_normalizado = _texto_obrigatorio(nome_exibicao, "Informe o nome de exibicao do subcatalogo")
    slug_normalizado = _slugify(slug) or _slugify(nome_exibicao_normalizado) or _slugify(nome_normalizado)
    if not slug_normalizado:
        raise HTTPException(status_code=400, detail="Informe um slug valido para o subcatalogo")

    return schemas.SubcategoriaCreate(
        categoria_slug=categoria_normalizada,
        slug=slug_normalizado,
        nome=nome_normalizado,
        nome_exibicao=nome_exibicao_normalizado,
        imagem_url=(imagem_url or "").strip() or None,
        ordem_exibicao=_ordem_normalizada(ordem_exibicao),
    )


def _create_produto_from_form(
    db: Session,
    nome: str,
    resumo_curto: str,
    categoria_slug: str,
    subcategoria_slug: Optional[str],
) -> schemas.ProdutoCreate:
    categoria_normalizada = _normalizar_categoria_slug(db, categoria_slug, required=True)
    return schemas.ProdutoCreate(
        nome=_texto_obrigatorio(nome, "Informe o nome do produto"),
        resumo_curto=resumo_curto,
        categoria_slug=categoria_normalizada,
        subcategoria_slug=_normalizar_subcategoria_slug(
            db,
            categoria_normalizada,
            subcategoria_slug,
            required=_categoria_exige_subcategoria(db, categoria_normalizada),
        ),
    )


def _update_produto_from_form(
    db: Session,
    nome: Optional[str],
    resumo_curto: Optional[str],
    categoria_slug: Optional[str],
    subcategoria_slug: Optional[str],
) -> schemas.ProdutoUpdate:
    categoria_normalizada = _normalizar_categoria_slug(db, categoria_slug, required=True)
    return schemas.ProdutoUpdate(
        nome=_texto_obrigatorio(nome, "Informe o nome do produto"),
        resumo_curto=resumo_curto,
        categoria_slug=categoria_normalizada,
        subcategoria_slug=_normalizar_subcategoria_slug(
            db,
            categoria_normalizada,
            subcategoria_slug,
            required=_categoria_exige_subcategoria(db, categoria_normalizada),
        ),
    )


def _catalogo_admin_context(db: Session) -> dict[str, object]:
    catalogo = _catalogo_index(db)
    produtos = [
        _produto_view(
            produto,
            categorias_por_slug=catalogo["categorias_por_slug"],
            subcategorias_por_chave=catalogo["subcategorias_por_chave"],
        )
        for produto in crud.get_produtos(db)
    ]
    return {
        "categorias": catalogo["categorias"],
        "subcategorias": catalogo["subcategorias"],
        "subcategorias_por_categoria": catalogo["subcategorias_por_categoria"],
        "produtos": produtos,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "categorias_home": catalogo["categorias"],
            "whatsapp_numero": telefone_visivel(),
        },
    )


@app.get("/quem-somos", response_class=HTMLResponse)
def quem_somos(request: Request):
    return templates.TemplateResponse(
        "quem_somos.html",
        {
            "request": request,
            "whatsapp_numero": telefone_visivel(),
        },
    )


@app.get("/categorias/{slug}", response_class=HTMLResponse)
def categoria_detalhe(slug: str, request: Request, db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    categoria = catalogo["categorias_por_slug"].get(slug)
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")

    subcategorias = catalogo["subcategorias_por_categoria"].get(slug, [])
    produtos_db = [] if subcategorias else crud.get_produtos(db, categoria_slug=slug)
    whatsapp_link = gerar_link_whatsapp_text(f"Ola! Tenho interesse na categoria {categoria['nome']}.")

    return templates.TemplateResponse(
        "categoria.html",
        {
            "request": request,
            "categoria": categoria,
            "produtos": [
                _produto_view(
                    produto,
                    categorias_por_slug=catalogo["categorias_por_slug"],
                    subcategorias_por_chave=catalogo["subcategorias_por_chave"],
                )
                for produto in produtos_db
            ],
            "subcategorias": subcategorias,
            "subcategoria_atual": None,
            "whatsapp_numero": telefone_visivel(),
            "whatsapp_link": whatsapp_link,
        },
    )


@app.get("/categorias/{slug}/subcategorias/{subcategoria_slug}", response_class=HTMLResponse)
def subcategoria_detalhe(
    slug: str,
    subcategoria_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    catalogo = _catalogo_index(db)
    categoria = catalogo["categorias_por_slug"].get(slug)
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")

    subcategoria = catalogo["subcategorias_por_chave"].get((slug, subcategoria_slug))
    if not subcategoria:
        raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")

    produtos_db = crud.get_produtos(db, categoria_slug=slug, subcategoria_slug=subcategoria_slug)
    whatsapp_link = gerar_link_whatsapp_text(
        f"Ola! Tenho interesse em {subcategoria['nome']} da categoria {categoria['nome']}."
    )

    return templates.TemplateResponse(
        "categoria.html",
        {
            "request": request,
            "categoria": categoria,
            "produtos": [
                _produto_view(
                    produto,
                    categorias_por_slug=catalogo["categorias_por_slug"],
                    subcategorias_por_chave=catalogo["subcategorias_por_chave"],
                )
                for produto in produtos_db
            ],
            "subcategorias": catalogo["subcategorias_por_categoria"].get(slug, []),
            "subcategoria_atual": subcategoria,
            "whatsapp_numero": telefone_visivel(),
            "whatsapp_link": whatsapp_link,
        },
    )


@app.get("/produtos", response_class=HTMLResponse)
def produtos(request: Request, db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    return templates.TemplateResponse(
        "produtos.html",
        {
            "request": request,
            "categorias_home": catalogo["categorias"],
            "whatsapp_numero": telefone_visivel(),
        },
    )


@app.get("/contato", response_class=HTMLResponse)
def contato(request: Request):
    return templates.TemplateResponse(
        "contato.html",
        {
            "request": request,
            "whatsapp_numero": telefone_visivel(),
        },
    )


@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detalhe(produto_id: int, request: Request, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")

    catalogo = _catalogo_index(db)
    whatsapp_link = gerar_link_whatsapp_text(f"Ola! Tenho interesse no produto {produto.nome}.")
    return templates.TemplateResponse(
        "produto.html",
        {
            "request": request,
            "produto": _produto_view(
                produto,
                categorias_por_slug=catalogo["categorias_por_slug"],
                subcategorias_por_chave=catalogo["subcategorias_por_chave"],
            ),
            "whatsapp_numero": telefone_visivel(),
            "whatsapp_link": whatsapp_link,
        },
    )


@app.get("/media/produto/{produto_id}/imagem")
def media_produto_imagem(produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not getattr(produto, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(produto, "imagem_mime", None) or "application/octet-stream"
    return Response(content=produto.imagem_bytes, media_type=mime)


@app.get("/media/categoria/{categoria_id}/imagem")
def media_categoria_imagem(categoria_id: int, db: Session = Depends(get_db)):
    categoria = crud.get_categoria(db, categoria_id=categoria_id)
    if not categoria or not getattr(categoria, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(categoria, "imagem_mime", None) or "application/octet-stream"
    return Response(content=categoria.imagem_bytes, media_type=mime)


@app.get("/media/subcategoria/{subcategoria_id}/imagem")
def media_subcategoria_imagem(subcategoria_id: int, db: Session = Depends(get_db)):
    subcategoria = crud.get_subcategoria(db, subcategoria_id=subcategoria_id)
    if not subcategoria or not getattr(subcategoria, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(subcategoria, "imagem_mime", None) or "application/octet-stream"
    return Response(content=subcategoria.imagem_bytes, media_type=mime)


@app.get("/media/produto/{produto_id}/imagem-medidas")
def media_produto_imagem_medidas(produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not getattr(produto, "imagem_medidas_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem de medidas nao encontrada")

    mime = getattr(produto, "imagem_medidas_mime", None) or "application/octet-stream"
    return Response(content=produto.imagem_medidas_bytes, media_type=mime)


@app.get("/api/produtos")
def api_produtos(db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    produtos_db = crud.list_produtos(db, apenas_ativos=True)
    return [
        _produto_view(
            produto,
            categorias_por_slug=catalogo["categorias_por_slug"],
            subcategorias_por_chave=catalogo["subcategorias_por_chave"],
        )
        for produto in produtos_db
    ]


@app.post("/api/whatsapp")
def api_whatsapp(itens: List[schemas.ItemCarrinho]):
    itens_dict = [i.model_dump() if hasattr(i, "model_dump") else i.dict() for i in itens]
    return {"url": gerar_link_whatsapp(itens_dict)}


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request):
    if _is_admin_authed(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("admin/login.html", {"request": request})


@app.post("/admin/login")
def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    admin_user, admin_pass = _admin_credentials()
    if not admin_pass or username != admin_user or password != admin_pass:
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Usuario ou senha invalidos"},
            status_code=200,
        )

    request.session["admin_authed"] = True
    request.session["admin_user"] = admin_user
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin_authed(request):
        return RedirectResponse("/admin/login", status_code=303)

    contexto = _catalogo_admin_context(db)
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            **contexto,
        },
    )


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@app.post("/admin/categoria")
def admin_categoria_novo(
    _: str = Depends(_auth_admin),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    subtitulo_exibicao: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    dados = _categoria_create_from_form(
        slug,
        nome,
        nome_exibicao,
        subtitulo_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        crud.create_categoria(db, dados, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin", status_code=303)


@app.put("/admin/categoria/{categoria_id}")
def admin_categoria_atualizar(
    categoria_id: int,
    _: str = Depends(_auth_admin),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    subtitulo_exibicao: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    create_data = _categoria_create_from_form(
        slug,
        nome,
        nome_exibicao,
        subtitulo_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        categoria = crud.update_categoria(
            db,
            categoria_id=categoria_id,
            dados=schemas.CategoriaUpdate(**_schema_dump(create_data)),
            imagem_bytes=imagem_bytes,
            imagem_mime=imagem_mime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/categoria/{categoria_id}")
def admin_categoria_method_override(
    categoria_id: int,
    _: str = Depends(_auth_admin),
    _method: Optional[str] = Form(None),
    slug: str = Form(""),
    nome: str = Form(None),
    nome_exibicao: str = Form(None),
    subtitulo_exibicao: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_categoria_atualizar(
            categoria_id=categoria_id,
            _=_,
            slug=slug,
            nome=nome,
            nome_exibicao=nome_exibicao,
            subtitulo_exibicao=subtitulo_exibicao,
            imagem=imagem,
            ordem_exibicao=ordem_exibicao,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/categoria/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/categoria/{categoria_id}")
def admin_categoria_excluir(
    categoria_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    if not crud.delete_categoria(db, categoria_id=categoria_id):
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    return Response(status_code=204)


@app.post("/admin/subcategoria")
def admin_subcategoria_novo(
    _: str = Depends(_auth_admin),
    categoria_slug: str = Form(...),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    dados = _subcategoria_create_from_form(
        db,
        categoria_slug,
        slug,
        nome,
        nome_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        crud.create_subcategoria(db, dados, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin", status_code=303)


@app.put("/admin/subcategoria/{subcategoria_id}")
def admin_subcategoria_atualizar(
    subcategoria_id: int,
    _: str = Depends(_auth_admin),
    categoria_slug: str = Form(...),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    create_data = _subcategoria_create_from_form(
        db,
        categoria_slug,
        slug,
        nome,
        nome_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        subcategoria = crud.update_subcategoria(
            db,
            subcategoria_id=subcategoria_id,
            dados=schemas.SubcategoriaUpdate(**_schema_dump(create_data)),
            imagem_bytes=imagem_bytes,
            imagem_mime=imagem_mime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not subcategoria:
        raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/subcategoria/{subcategoria_id}")
def admin_subcategoria_method_override(
    subcategoria_id: int,
    _: str = Depends(_auth_admin),
    _method: Optional[str] = Form(None),
    categoria_slug: str = Form(None),
    slug: str = Form(""),
    nome: str = Form(None),
    nome_exibicao: str = Form(None),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_subcategoria_atualizar(
            subcategoria_id=subcategoria_id,
            _=_,
            categoria_slug=categoria_slug,
            slug=slug,
            nome=nome,
            nome_exibicao=nome_exibicao,
            imagem=imagem,
            ordem_exibicao=ordem_exibicao,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/subcategoria/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/subcategoria/{subcategoria_id}")
def admin_subcategoria_excluir(
    subcategoria_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    if not crud.delete_subcategoria(db, subcategoria_id=subcategoria_id):
        raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")
    return Response(status_code=204)


@app.post("/admin/produto")
def admin_produto_novo(
    _: str = Depends(_auth_admin),
    nome: str = Form(...),
    resumo_curto: str = Form(""),
    categoria_slug: str = Form(...),
    subcategoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    imagem_medidas_bytes, imagem_medidas_mime = _load_uploaded_image(imagem_medidas)

    crud.create_produto(
        db,
        _create_produto_from_form(db, nome, resumo_curto, categoria_slug, subcategoria_slug),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        imagem_medidas_bytes=imagem_medidas_bytes,
        imagem_medidas_mime=imagem_medidas_mime,
    )
    return RedirectResponse("/admin", status_code=303)


@app.put("/admin/produto/{produto_id}")
def admin_produto_atualizar(
    produto_id: int,
    _: str = Depends(_auth_admin),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    categoria_slug: str = Form(None),
    subcategoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    imagem_medidas_bytes, imagem_medidas_mime = _load_uploaded_image(imagem_medidas)

    produto = crud.update_produto(
        db,
        produto_id=produto_id,
        dados=_update_produto_from_form(db, nome, resumo_curto, categoria_slug, subcategoria_slug),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        imagem_medidas_bytes=imagem_medidas_bytes,
        imagem_medidas_mime=imagem_medidas_mime,
    )
    if not produto:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produto/{produto_id}")
def admin_produto_method_override(
    produto_id: int,
    _: str = Depends(_auth_admin),
    _method: Optional[str] = Form(None),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    categoria_slug: str = Form(None),
    subcategoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_produto_atualizar(
            produto_id=produto_id,
            _=_,
            nome=nome,
            resumo_curto=resumo_curto,
            categoria_slug=categoria_slug,
            subcategoria_slug=subcategoria_slug,
            imagem=imagem,
            imagem_medidas=imagem_medidas,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/produto/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/produto/{produto_id}")
def admin_produto_excluir(
    produto_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    if not crud.delete_produto(db, produto_id=produto_id):
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return Response(status_code=204)
