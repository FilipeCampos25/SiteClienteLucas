from __future__ import annotations

import io
import math
import os
from typing import Generator, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
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
from config import ADMIN_PASSWORD, ADMIN_USER, CORS_ORIGINS, WHATSAPP_NUMERO
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
    LOGO_URL="/static/images/logomarca.png",
)


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


def _produto_catalogo_url(produto: models.Produto) -> Optional[str]:
    if getattr(produto, "catalogo_bytes", None):
        return f"/media/produto/{produto.id}/catalogo"

    url_externa = (getattr(produto, "catalogo_url", None) or "").strip()
    if url_externa:
        return url_externa

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


def _read_pdf(upload: Optional[UploadFile]) -> tuple[Optional[bytes], Optional[str], Optional[str]]:
    if not upload or not upload.filename:
        return None, None, None

    raw = upload.file.read()
    if not raw:
        return None, None, None

    mime = (upload.content_type or "").strip() or "application/pdf"
    if mime != "application/pdf":
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF valido")

    return raw, mime, upload.filename


def _build_paginacao(total_paginas: int, pagina_atual: int) -> list[Optional[int]]:
    if total_paginas <= 0:
        return []
    if total_paginas <= 7:
        return list(range(1, total_paginas + 1))

    paginas = {1, pagina_atual - 1, pagina_atual, pagina_atual + 1, total_paginas - 1, total_paginas}
    paginas_validas = sorted(p for p in paginas if 1 <= p <= total_paginas)

    resultado: list[Optional[int]] = []
    anterior: Optional[int] = None
    for pagina in paginas_validas:
        if anterior is not None and pagina - anterior > 1:
            resultado.append(None)
        resultado.append(pagina)
        anterior = pagina
    return resultado


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


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
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


@app.get("/produtos", response_class=HTMLResponse)
def produtos(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    per_page = 20
    base_query = db.query(models.Produto)

    total_itens = base_query.count()
    total_paginas = math.ceil(total_itens / per_page) if total_itens > 0 else 0

    if total_paginas > 0 and page > total_paginas:
        return RedirectResponse(url=f"/produtos?page={total_paginas}#produtos", status_code=303)

    offset = (page - 1) * per_page
    produtos_db = base_query.order_by(models.Produto.id.desc()).limit(per_page).offset(offset).all()

    view = []
    for produto in produtos_db:
        view.append(
            {
                "id": produto.id,
                "nome": produto.nome,
                "catalogo_url": _produto_catalogo_url(produto),
                "resumo_curto": produto.resumo_curto,
                "imagem_url": _produto_image_url(produto),
            }
        )

    return templates.TemplateResponse(
        "produtos.html",
        {
            "request": request,
            "produtos": view,
            "pagina_atual": page,
            "total_paginas": total_paginas,
            "paginacao": _build_paginacao(total_paginas, page),
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
            "produto": {
                "id": produto.id,
                "nome": produto.nome,
                "resumo_curto": produto.resumo_curto,
                "catalogo_url": _produto_catalogo_url(produto),
                "imagem_url": _produto_image_url(produto),
            },
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


@app.get("/media/produto/{produto_id}/catalogo")
def media_produto_catalogo(produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not getattr(produto, "catalogo_bytes", None):
        raise HTTPException(status_code=404, detail="Catalogo nao encontrado")

    headers = {}
    nome_arquivo = (produto.catalogo_nome_arquivo or f"catalogo-produto-{produto.id}.pdf").replace('"', "")
    headers["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
    mime = getattr(produto, "catalogo_mime", None) or "application/pdf"
    return Response(content=produto.catalogo_bytes, media_type=mime, headers=headers)


@app.get("/api/produtos")
def api_produtos(db: Session = Depends(get_db)):
    produtos_db = crud.list_produtos(db, apenas_ativos=True)
    return [
        {
            "id": produto.id,
            "nome": produto.nome,
            "catalogo_url": _produto_catalogo_url(produto),
            "resumo_curto": produto.resumo_curto,
            "imagem_url": _produto_image_url(produto),
        }
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

    view = []
    for produto in crud.get_produtos(db):
        view.append(
            {
                "id": produto.id,
                "nome": produto.nome,
                "resumo_curto": produto.resumo_curto,
                "catalogo_url": _produto_catalogo_url(produto),
                "catalogo_nome_arquivo": produto.catalogo_nome_arquivo,
                "imagem_url": _produto_image_url(produto),
            }
        )

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
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
) -> schemas.ProdutoCreate:
    return schemas.ProdutoCreate(
        nome=nome,
        resumo_curto=resumo_curto,
        catalogo_url=None,
    )


def _update_produto_from_form(
    nome: Optional[str],
    resumo_curto: Optional[str],
) -> schemas.ProdutoUpdate:
    return schemas.ProdutoUpdate(
        nome=nome,
        resumo_curto=resumo_curto,
        catalogo_url=None,
    )


@app.post("/admin/produtos/novo")
def admin_produto_novo(
    _: str = Depends(_auth_admin),
    nome: str = Form(...),
    resumo_curto: str = Form(""),
    imagem: UploadFile = File(None),
    catalogo_pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    imagem_bytes: Optional[bytes] = None
    imagem_mime: Optional[str] = None
    if imagem and imagem.filename:
        raw = imagem.file.read()
        imagem_bytes, imagem_mime = _compress_to_jpeg(raw)

    catalogo_bytes, catalogo_mime, catalogo_nome_arquivo = _read_pdf(catalogo_pdf)
    if not catalogo_bytes:
        raise HTTPException(status_code=400, detail="Envie um catalogo em PDF")

    crud.create_produto(
        db,
        _create_produto_from_form(nome, resumo_curto),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        catalogo_bytes=catalogo_bytes,
        catalogo_mime=catalogo_mime,
        catalogo_nome_arquivo=catalogo_nome_arquivo,
    )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produtos/{produto_id}/atualizar")
def admin_produto_atualizar(
    produto_id: int,
    _: str = Depends(_auth_admin),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    imagem: UploadFile = File(None),
    catalogo_pdf: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    imagem_bytes: Optional[bytes] = None
    imagem_mime: Optional[str] = None
    if imagem and imagem.filename:
        raw = imagem.file.read()
        imagem_bytes, imagem_mime = _compress_to_jpeg(raw)

    catalogo_bytes, catalogo_mime, catalogo_nome_arquivo = _read_pdf(catalogo_pdf)
    crud.update_produto(
        db,
        produto_id=produto_id,
        dados=_update_produto_from_form(nome, resumo_curto),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        catalogo_bytes=catalogo_bytes,
        catalogo_mime=catalogo_mime,
        catalogo_nome_arquivo=catalogo_nome_arquivo,
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
    imagem: UploadFile = File(None),
    catalogo_pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return admin_produto_novo(
        _=_,
        nome=nome,
        resumo_curto=resumo_curto,
        imagem=imagem,
        catalogo_pdf=catalogo_pdf,
        db=db,
    )


@app.put("/admin/produto/{produto_id}")
def admin_produto_atualizar_alias(
    produto_id: int,
    _: str = Depends(_auth_admin),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    imagem: UploadFile = File(None),
    catalogo_pdf: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    return admin_produto_atualizar(
        produto_id=produto_id,
        _=_,
        nome=nome,
        resumo_curto=resumo_curto,
        imagem=imagem,
        catalogo_pdf=catalogo_pdf,
        db=db,
    )


@app.post("/admin/produto/{produto_id}")
def admin_produto_method_override(
    produto_id: int,
    _: str = Depends(_auth_admin),
    _method: Optional[str] = Form(None),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    imagem: UploadFile = File(None),
    catalogo_pdf: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_produto_atualizar_alias(
            produto_id=produto_id,
            _=_,
            nome=nome,
            resumo_curto=resumo_curto,
            imagem=imagem,
            catalogo_pdf=catalogo_pdf,
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
