from __future__ import annotations

import io
import os
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

CATEGORIAS_HOME = [
    {
        "slug": "cantoneiras-de-aluminio",
        "nome": "Cantoneiras de Aluminio",
        "nome_exibicao": "Cantoneiras de Alum\u00ednio",
        "imagem_url": "/static/images/img3.jpeg",
    },
    {
        "slug": "kits-para-montagem",
        "nome": "Kits para montagem",
        "nome_exibicao": "Kits para montagem",
        "imagem_url": "/static/images/img5.jpeg",
    },
    {
        "slug": "cantoneira-suporte-para-prateleira",
        "nome": "Cantoneira suporte para prateleira",
        "nome_exibicao": "Cantoneira Suporte para Prateleira",
        "imagem_url": "/static/images/img6.jpeg",
    },
    {
        "slug": "acessorios",
        "nome": "Acessorios",
        "nome_exibicao": "Acess\u00f3rios",
        "imagem_url": "/static/images/img8.jpeg",
    },
]
CATEGORIAS_POR_SLUG = {categoria["slug"]: categoria for categoria in CATEGORIAS_HOME}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _produto_image_url(produto: models.Produto) -> str:
    if getattr(produto, "imagem_bytes", None):
        return f"/media/produto/{produto.id}/imagem"

    url_externa = (getattr(produto, "imagem_url", None) or "").strip()
    if url_externa:
        return url_externa

    return "/static/images/placeholder.png"


def _produto_medidas_image_url(produto: models.Produto) -> Optional[str]:
    if getattr(produto, "imagem_medidas_bytes", None):
        return f"/media/produto/{produto.id}/imagem-medidas"
    return None


def _compress_to_jpeg(raw: bytes) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((1600, 1600))

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return raw, "application/octet-stream"


def _load_uploaded_image(upload: Optional[UploadFile]) -> tuple[Optional[bytes], Optional[str]]:
    if not upload or not upload.filename:
        return None, None

    raw = upload.file.read()
    if not raw:
        return None, None

    return _compress_to_jpeg(raw)


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


def _get_categoria(slug: str) -> dict[str, str]:
    categoria = CATEGORIAS_POR_SLUG.get(slug)
    if categoria:
        return categoria
    raise HTTPException(status_code=404, detail="Categoria nao encontrada")


def _normalizar_categoria_slug(categoria_slug: Optional[str], *, required: bool) -> Optional[str]:
    slug = (categoria_slug or "").strip()
    if not slug:
        if required:
            raise HTTPException(status_code=400, detail="Selecione um tipo de produto")
        return None
    if slug not in CATEGORIAS_POR_SLUG:
        raise HTTPException(status_code=400, detail="Tipo de produto invalido")
    return slug


def _produto_view(produto: models.Produto) -> dict[str, Optional[str]]:
    categoria = CATEGORIAS_POR_SLUG.get((getattr(produto, "categoria_slug", None) or "").strip())
    return {
        "id": produto.id,
        "nome": produto.nome,
        "resumo_curto": produto.resumo_curto,
        "imagem_url": _produto_image_url(produto),
        "imagem_medidas_url": _produto_medidas_image_url(produto),
        "categoria_slug": produto.categoria_slug,
        "categoria_nome_exibicao": categoria["nome_exibicao"] if categoria else None,
        "categoria_url": f"/categorias/{categoria['slug']}" if categoria else None,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "categorias_home": CATEGORIAS_HOME,
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
    categoria = _get_categoria(slug)
    produtos_db = crud.get_produtos(db, categoria_slug=slug)
    whatsapp_link = gerar_link_whatsapp_text(
        f"Ola! Tenho interesse na categoria {categoria['nome']}."
    )
    return templates.TemplateResponse(
        "categoria.html",
        {
            "request": request,
            "categoria": categoria,
            "produtos": [_produto_view(produto) for produto in produtos_db],
            "whatsapp_numero": telefone_visivel(),
            "whatsapp_link": whatsapp_link,
        },
    )


@app.get("/produtos", response_class=HTMLResponse)
def produtos(
    request: Request,
    db: Session = Depends(get_db),
):
    produtos_db = crud.get_produtos(db)
    produtos_por_categoria: dict[str, list[dict[str, Optional[str]]]] = {}
    produtos_sem_categoria: list[dict[str, Optional[str]]] = []

    for produto in produtos_db:
        produto_view = _produto_view(produto)
        categoria_slug = (produto.categoria_slug or "").strip()
        if categoria_slug in CATEGORIAS_POR_SLUG:
            produtos_por_categoria.setdefault(categoria_slug, []).append(produto_view)
        else:
            produtos_sem_categoria.append(produto_view)

    grupos_produtos = []
    for categoria in CATEGORIAS_HOME:
        itens = produtos_por_categoria.get(categoria["slug"], [])
        if not itens:
            continue
        grupos_produtos.append(
            {
                "slug": categoria["slug"],
                "nome_exibicao": categoria["nome_exibicao"],
                "produtos": itens,
            }
        )

    if produtos_sem_categoria:
        grupos_produtos.append(
            {
                "slug": "sem-categoria",
                "nome_exibicao": "Sem categoria",
                "produtos": produtos_sem_categoria,
            }
        )

    return templates.TemplateResponse(
        "produtos.html",
        {
            "request": request,
            "grupos_produtos": grupos_produtos,
            "total_produtos": len(produtos_db),
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

    whatsapp_link = gerar_link_whatsapp_text(f"Ola! Tenho interesse no produto {produto.nome}.")
    return templates.TemplateResponse(
        "produto.html",
        {
            "request": request,
            "produto": _produto_view(produto),
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


@app.get("/media/produto/{produto_id}/imagem-medidas")
def media_produto_imagem_medidas(produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not getattr(produto, "imagem_medidas_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem de medidas nao encontrada")

    mime = getattr(produto, "imagem_medidas_mime", None) or "application/octet-stream"
    return Response(content=produto.imagem_medidas_bytes, media_type=mime)


@app.get("/api/produtos")
def api_produtos(db: Session = Depends(get_db)):
    produtos_db = crud.list_produtos(db, apenas_ativos=True)
    return [_produto_view(produto) for produto in produtos_db]


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

    view = [_produto_view(produto) for produto in crud.get_produtos(db)]

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "categorias": CATEGORIAS_HOME,
            "produtos": view,
        },
    )


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


def _create_produto_from_form(
    nome: str,
    resumo_curto: str,
    categoria_slug: str,
) -> schemas.ProdutoCreate:
    return schemas.ProdutoCreate(
        nome=nome,
        resumo_curto=resumo_curto,
        categoria_slug=_normalizar_categoria_slug(categoria_slug, required=True),
    )


def _update_produto_from_form(
    nome: Optional[str],
    resumo_curto: Optional[str],
    categoria_slug: Optional[str],
) -> schemas.ProdutoUpdate:
    return schemas.ProdutoUpdate(
        nome=nome,
        resumo_curto=resumo_curto,
        categoria_slug=_normalizar_categoria_slug(categoria_slug, required=True),
    )


@app.post("/admin/produtos/novo")
def admin_produto_novo(
    _: str = Depends(_auth_admin),
    nome: str = Form(...),
    resumo_curto: str = Form(""),
    categoria_slug: str = Form(...),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    imagem_medidas_bytes, imagem_medidas_mime = _load_uploaded_image(imagem_medidas)

    crud.create_produto(
        db,
        _create_produto_from_form(nome, resumo_curto, categoria_slug),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        imagem_medidas_bytes=imagem_medidas_bytes,
        imagem_medidas_mime=imagem_medidas_mime,
    )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produtos/{produto_id}/atualizar")
def admin_produto_atualizar(
    produto_id: int,
    _: str = Depends(_auth_admin),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    categoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    imagem_medidas_bytes, imagem_medidas_mime = _load_uploaded_image(imagem_medidas)

    crud.update_produto(
        db,
        produto_id=produto_id,
        dados=_update_produto_from_form(nome, resumo_curto, categoria_slug),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        imagem_medidas_bytes=imagem_medidas_bytes,
        imagem_medidas_mime=imagem_medidas_mime,
    )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produtos/{produto_id}/excluir")
def admin_produto_excluir(
    produto_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    crud.delete_produto(db, produto_id=produto_id)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produto")
def admin_produto_novo_alias(
    _: str = Depends(_auth_admin),
    nome: str = Form(...),
    resumo_curto: str = Form(""),
    categoria_slug: str = Form(...),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    return admin_produto_novo(
        _=_,
        nome=nome,
        resumo_curto=resumo_curto,
        categoria_slug=categoria_slug,
        imagem=imagem,
        imagem_medidas=imagem_medidas,
        db=db,
    )


@app.put("/admin/produto/{produto_id}")
def admin_produto_atualizar_alias(
    produto_id: int,
    _: str = Depends(_auth_admin),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    categoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    return admin_produto_atualizar(
        produto_id=produto_id,
        _=_,
        nome=nome,
        resumo_curto=resumo_curto,
        categoria_slug=categoria_slug,
        imagem=imagem,
        imagem_medidas=imagem_medidas,
        db=db,
    )


@app.post("/admin/produto/{produto_id}")
def admin_produto_method_override(
    produto_id: int,
    _: str = Depends(_auth_admin),
    _method: Optional[str] = Form(None),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    categoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_produto_atualizar_alias(
            produto_id=produto_id,
            _=_,
            nome=nome,
            resumo_curto=resumo_curto,
            categoria_slug=categoria_slug,
            imagem=imagem,
            imagem_medidas=imagem_medidas,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/produto/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/produto/{produto_id}")
def admin_produto_excluir_alias(
    produto_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    crud.delete_produto(db, produto_id=produto_id)
    return Response(status_code=204)
