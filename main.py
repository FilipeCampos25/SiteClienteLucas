from __future__ import annotations

"""
main.py
=======
Aplicação FastAPI (templates Jinja2) para catálogo + painel admin.

FOCO DESTA REFATORAÇÃO:
- Corrigir o fluxo de persistência e entrega de imagens (PNG/JPG) armazenadas no BANCO.
- Evitar "imagem corrompida" na hora de servir a imagem ao navegador.

TÓPICO 2 (desta etapa):
- Compactar automaticamente as imagens no upload (admin), para reduzir peso no DB
  e melhorar performance do site (sem exigir burocracia do admin).

Correção aplicada agora (urgente /admin):
- Trocar TemplateResponse("admin.html") por TemplateResponse("admin/dashboard.html")
  porque NO SEU PROJETO NÃO EXISTE templates/admin.html e o Render quebra com TemplateNotFound.
"""

import base64
import io
import hashlib
import hmac
import math
import os
import secrets
import time
from typing import Generator, Optional, Tuple

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# Pillow é usado SOMENTE para compactação/redimensionamento no upload (tópico 2).
from PIL import Image, ImageOps

import crud
import models
import schemas
from config import ADMIN_PASSWORD, ADMIN_USER, CORS_ORIGINS, WHATSAPP_NUMERO
from database import SessionLocal
from utils import gerar_link_whatsapp, gerar_link_whatsapp_text, telefone_visivel

# =============================================================================
# App + Middleware
# =============================================================================

app = FastAPI(title="Cantoneira Fácil")

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Static + Templates
# =============================================================================

app.mount("/static", StaticFiles(directory="static"), name="static")
# Compatibilidade com URLs antigas (caso existam)
app.mount("/uploads", StaticFiles(directory=os.path.join("static", "uploads")), name="uploads")

templates = Jinja2Templates(directory="templates")

# =============================================================================
# Auth (Admin)
# =============================================================================

security = HTTPBasic()


def _auth_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Protege endpoints /admin/* com HTTP Basic.

    COMENTÁRIO:
    - Mantém o comportamento atual e evita mudanças drásticas de autenticação.
    """
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# =============================================================================
# DB Dependency
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    Dependency do FastAPI para obter Session do SQLAlchemy.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Helpers (Imagens)
# =============================================================================

def _produto_image_url(p: models.Produto) -> str:
    """
    Retorna a URL correta para a imagem do produto.
    """
    # Se tiver imagem no banco, serve via endpoint /media/produto/{id}
    if getattr(p, "imagem", None):
        return f"/media/produto/{p.id}"
    # Se tiver imagem_url definida, usa ela
    if getattr(p, "imagem_url", None):
        return p.imagem_url
    # Fallback para placeholder
    return "/static/images/placeholder.png"


def _img_bytes_to_response(img_bytes: bytes) -> Response:
    """
    Detecta content-type de forma simples e retorna Response.
    """
    # Heurística mínima (sem mudanças drásticas):
    # - Se começar com bytes PNG -> image/png
    # - Se começar com bytes JPG -> image/jpeg
    if img_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return Response(content=img_bytes, media_type="image/png")
    if img_bytes.startswith(b"\xff\xd8"):
        return Response(content=img_bytes, media_type="image/jpeg")
    # fallback
    return Response(content=img_bytes, media_type="application/octet-stream")


# =============================================================================
# Rotas (Site)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """
    Página inicial do catálogo com paginação (se já existir no projeto).
    """
    # OBS: Mantido como está no seu projeto (não mexer fora do escopo)
    page_size = 20
    skip = (page - 1) * page_size

    total = crud.count_produtos_ativos(db)
    total_paginas = max(1, math.ceil(total / page_size))

    produtos = crud.get_produtos_ativos_paginado(db, skip=skip, limit=page_size)

    # Ajusta URLs das imagens
    for p in produtos:
        p.imagem_url = _produto_image_url(p)

    # Paginacao simples (com reticências)
    paginacao: list[Optional[int]] = []
    if total_paginas <= 7:
        paginacao = list(range(1, total_paginas + 1))
    else:
        # Exibe: 1, 2, ..., atual-1, atual, atual+1, ..., last
        paginacao = [1, 2, None]
        start = max(3, page - 1)
        end = min(total_paginas - 2, page + 1)
        if start > 3:
            paginacao.append(None)
        paginacao.extend(range(start, end + 1))
        if end < total_paginas - 2:
            paginacao.append(None)
        paginacao.extend([None, total_paginas - 1, total_paginas])

        # Normaliza duplicidades de None/valores
        cleaned: list[Optional[int]] = []
        last = object()
        for x in paginacao:
            if x == last:
                continue
            cleaned.append(x)
            last = x
        paginacao = cleaned

    # Link direto do WhatsApp (sem texto) para o botão geral do header/hero
    WHATSAPP_LINK = gerar_link_whatsapp([])

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "produtos": produtos,
            "pagina_atual": page,
            "total_paginas": total_paginas,
            "paginacao": paginacao,
            "WHATSAPP_LINK": WHATSAPP_LINK,
            "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
            "LOGO_URL": None,
        },
    )


@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def detalhe_produto(
    request: Request,
    produto_id: int,
    db: Session = Depends(get_db),
):
    """
    Página de detalhe de um produto.
    """
    p = crud.get_produto(db, produto_id=produto_id)
    if not p or not p.ativo:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    p.imagem_url = _produto_image_url(p)

    # Link direto do WhatsApp (sem texto) para CTA geral
    WHATSAPP_LINK = gerar_link_whatsapp([])

    return templates.TemplateResponse(
        "produto.html",
        {
            "request": request,
            "p": p,
            "WHATSAPP_LINK": WHATSAPP_LINK,
            "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
            "LOGO_URL": None,
        },
    )


# =============================================================================
# Rotas (Media)
# =============================================================================

@app.get("/media/produto/{produto_id}")
def media_produto(produto_id: int, db: Session = Depends(get_db)):
    """
    Serve a imagem do produto armazenada no banco.
    """
    p = crud.get_produto(db, produto_id=produto_id)
    if not p or not p.imagem:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    # p.imagem é bytes no banco
    return _img_bytes_to_response(p.imagem)


# =============================================================================
# API
# =============================================================================

@app.get("/api/produtos", response_model=list[schemas.ProdutoOut])
def api_produtos(db: Session = Depends(get_db)):
    """
    API JSON: lista produtos ativos.
    """
    produtos = crud.get_produtos_ativos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)
    return produtos


# =============================================================================
# API (Carrinho -> WhatsApp)
# =============================================================================
@app.post("/api/whatsapp")
def api_whatsapp(itens: list[schemas.ItemCarrinho]):
    """
    Recebe os itens do carrinho (vindos do frontend) e devolve um link do WhatsApp
    já com a mensagem pronta.

    IMPORTANTE (escopo desta tarefa):
    - O carrinho é mantido no navegador via localStorage (static/js/main.js).
    - Este endpoint existe apenas para centralizar a montagem do texto/URL
      (evita ter o número e o formato de mensagem "hardcoded" no JS).

    Retorno:
        {"url": "<link wa.me com texto codificado>"}
    """
    # COMENTÁRIO: compatibilidade pydantic v1/v2
    def _dump(model):
        return model.model_dump() if hasattr(model, "model_dump") else model.dict()

    itens_dict = [_dump(i) for i in (itens or [])]
    url = gerar_link_whatsapp(itens_dict)

    return {"url": url}


# =============================================================================
# Admin (mantido como está no seu projeto)
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    produtos = crud.get_produtos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "produtos": produtos,
            "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
            "TEL_VISIVEL": telefone_visivel(),
        },
    )


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@app.post("/admin/produtos/novo")
def admin_produto_novo(
    _: str = Depends(_auth_admin),
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    # ===========================
    # Upload de imagem (com compactação)
    # ===========================
    imagem_bytes: Optional[bytes] = None
    imagem_url: Optional[str] = None

    if imagem and imagem.filename:
        raw = imagem.file.read()

        # COMENTÁRIO: Compactação leve p/ reduzir peso no DB sem mudar UX
        try:
            pil = Image.open(io.BytesIO(raw))
            pil = ImageOps.exif_transpose(pil)
            pil = pil.convert("RGB")

            # Reduz dimensões (limite) mantendo proporção
            pil.thumbnail((1600, 1600))

            out = io.BytesIO()
            pil.save(out, format="JPEG", quality=82, optimize=True)
            imagem_bytes = out.getvalue()
        except Exception:
            # fallback se algo falhar
            imagem_bytes = raw

    novo = schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor, imagem_url=imagem_url)
    crud.create_produto(db, novo, imagem_bytes=imagem_bytes)

    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produtos/{produto_id}/atualizar")
def admin_produto_atualizar(
    produto_id: int,
    _: str = Depends(_auth_admin),
    nome: str = Form(None),
    descricao: str = Form(None),
    valor: float = Form(None),
    ativo: Optional[bool] = Form(None),
    imagem: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    imagem_bytes: Optional[bytes] = None

    if imagem and imagem.filename:
        raw = imagem.file.read()
        try:
            pil = Image.open(io.BytesIO(raw))
            pil = ImageOps.exif_transpose(pil)
            pil = pil.convert("RGB")
            pil.thumbnail((1600, 1600))

            out = io.BytesIO()
            pil.save(out, format="JPEG", quality=82, optimize=True)
            imagem_bytes = out.getvalue()
        except Exception:
            imagem_bytes = raw

    upd = schemas.ProdutoUpdate(
        nome=nome,
        descricao=descricao,
        valor=valor,
        ativo=ativo,
    )
    crud.update_produto(db, produto_id=produto_id, dados=upd, imagem_bytes=imagem_bytes)

    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produtos/{produto_id}/excluir")
def admin_produto_excluir(
    produto_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    crud.delete_produto(db, produto_id=produto_id)
    return RedirectResponse("/admin", status_code=303)
