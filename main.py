# projeto/main.py
"""
main.py
-------
Aplicação FastAPI + Jinja2 (catálogo + admin).

OBJETIVOS (DO ZERO, SEM REAPROVEITAR A LÓGICA QUEBRADA):
1) Imagens SEM filesystem local:
   - Imagens ficam no Postgres/Neon (columns imagem_bytes / imagem_mime / imagem_sha256).
   - Endpoint /media/produto/{id} serve os bytes direto do DB.

2) Admin login FUNCIONANDO:
   - templates/admin/login.html já existe e faz POST /admin/login
   - Implementamos sessão via cookie assinado (HttpOnly) + fallback HTTP Basic.

REGRAS:
- Sem mudanças fora do necessário para corrigir imagens + login admin.
"""

from __future__ import annotations

import base64
import hmac
import hashlib
import time
import io
from typing import Generator, Optional

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    status,
    Form,
    File,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from PIL import Image, ImageOps

from sqlalchemy.orm import Session

import crud
import schemas
import models
from database import SessionLocal, init_db
from config import (
    ADMIN_USER,
    ADMIN_PASSWORD,
    WHATSAPP_NUMERO,
    CORS_ORIGINS,
)
from utils import gerar_link_whatsapp, telefone_visivel


# =============================================================================
# App
# =============================================================================

app = FastAPI(title="Cantoneira Fácil")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static e templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# =============================================================================
# DB
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """Dependency: entrega uma Session por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def _startup() -> None:
    # Comentário: garante tabelas (se necessário)
    init_db()


# =============================================================================
# Helpers: imagem (DB) e URL para templates
# =============================================================================

def _produto_image_url(p: models.Produto) -> str:
    """
    Decide qual URL de imagem usar no template.

    Regra (seu combinado):
    - Se existe imagem_bytes -> sempre /media/produto/{id}
    - Senão, se existir imagem_url externa (caso alguém use CDN), usa ela
    - Senão, placeholder
    """
    if getattr(p, "imagem_bytes", None):
        return f"/media/produto/{p.id}"

    url_externa = (getattr(p, "imagem_url", None) or "").strip()
    if url_externa:
        return url_externa

    return "/static/images/placeholder.png"


def _compress_to_jpeg(raw: bytes) -> tuple[bytes, str]:
    """
    Compacta imagem (upload do admin) para JPEG com qualidade boa,
    limitando dimensões, sem depender de disco.

    Retorna:
      (bytes_compactados, mime)
    """
    # Comentário: tentamos abrir com Pillow; se falhar, devolve original como octet-stream
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # corrige rotação de celular
        img = img.convert("RGB")            # JPEG precisa RGB

        # Limita tamanho (mantém proporção)
        img.thumbnail((1600, 1600))

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:
        # Fallback: não derruba o admin se vier formato estranho
        return raw, "application/octet-stream"


# =============================================================================
# Admin Auth: cookie assinado + fallback HTTP Basic
# =============================================================================

security = HTTPBasic()

# Comentário:
# - Para evitar “sessão quebrar após restart”, a chave precisa ser estável.
# - Se você não quiser criar ENV nova, derivamos de ADMIN_USER/ADMIN_PASSWORD (que já são ENV).
# - Se quiser reforçar: crie ADMIN_SESSION_SECRET no Render e substitua abaixo.
_ADMIN_SESSION_KEY = hashlib.sha256(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode("utf-8")).digest()

_COOKIE_NAME = "admin_session"
_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 dias


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload: bytes) -> str:
    sig = hmac.new(_ADMIN_SESSION_KEY, payload, hashlib.sha256).hexdigest()
    return sig


def _make_session_cookie(username: str) -> str:
    """
    Cookie: base64url(payload).hexsig
    payload = "username|exp"
    """
    exp = int(time.time()) + _SESSION_TTL_SECONDS
    payload = f"{username}|{exp}".encode("utf-8")
    return f"{_b64url_encode(payload)}.{_sign(payload)}"


def _verify_session_cookie(cookie_value: str) -> Optional[str]:
    """Valida cookie e retorna username se OK."""
    try:
        b64, sig = cookie_value.split(".", 1)
        payload = _b64url_decode(b64)
        expected = _sign(payload)

        # Comentário: compare_digest evita timing attack
        if not hmac.compare_digest(sig, expected):
            return None

        text = payload.decode("utf-8")
        username, exp_str = text.split("|", 1)
        if int(exp_str) < int(time.time()):
            return None

        return username
    except Exception:
        return None


def _auth_admin(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """
    Autenticação admin:
    1) Se tiver cookie de sessão válido -> OK
    2) Caso contrário -> fallback HTTP Basic (não quebra o que já estava em uso)
    """
    cookie = request.cookies.get(_COOKIE_NAME)
    if cookie:
        user = _verify_session_cookie(cookie)
        if user:
            return user

    # Fallback HTTP Basic
    if (
        hmac.compare_digest(credentials.username, ADMIN_USER)
        and hmac.compare_digest(credentials.password, ADMIN_PASSWORD)
    ):
        return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Basic"},
    )


# =============================================================================
# Site (Catálogo)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    produtos = crud.get_produtos_ativos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)

    # Link “fale conosco” do hero
    whatsapp_link = f"https://wa.me/{WHATSAPP_NUMERO}" if WHATSAPP_NUMERO else "#"

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "produtos": produtos,
            "WHATSAPP_LINK": whatsapp_link,
            "TEL_VISIVEL": telefone_visivel(),
            "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
        },
    )


@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detalhe(produto_id: int, request: Request, db: Session = Depends(get_db)):
    p = crud.get_produto(db, produto_id=produto_id)
    if not p or not getattr(p, "ativo", True):
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    p.imagem_url = _produto_image_url(p)

    return templates.TemplateResponse(
        "produto.html",
        {
            "request": request,
            "p": p,
            "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
            "TEL_VISIVEL": telefone_visivel(),
        },
    )


# =============================================================================
# Media (Imagem do DB)
# =============================================================================

@app.get("/media/produto/{produto_id}")
def media_produto(produto_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Serve a imagem do produto diretamente do banco (Postgres/Neon).

    - Lê imagem_bytes + imagem_mime
    - Usa imagem_sha256 como ETag (cache HTTP)
    """
    p = crud.get_produto(db, produto_id=produto_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    img = getattr(p, "imagem_bytes", None)
    if not img:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    mime = getattr(p, "imagem_mime", None) or "application/octet-stream"
    etag = getattr(p, "imagem_sha256", None)

    # Cache condicional
    if etag:
        inm = request.headers.get("if-none-match")
        if inm and inm.strip('"') == etag:
            return Response(status_code=304, headers={"ETag": etag})

    headers = {}
    if etag:
        headers["ETag"] = etag
        # Comentário: cache leve (você pode ajustar se quiser)
        headers["Cache-Control"] = "public, max-age=3600"

    return Response(content=img, media_type=mime, headers=headers)


# =============================================================================
# API (Produtos)
# =============================================================================

@app.get("/api/produtos", response_model=list[schemas.ProdutoOut])
def api_produtos(db: Session = Depends(get_db)):
    produtos = crud.get_produtos_ativos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)
    return produtos


# =============================================================================
# API (Carrinho -> WhatsApp)
# =============================================================================

@app.post("/api/whatsapp")
def api_whatsapp(itens: list[schemas.ItemCarrinho]):
    # Comentário: backend só monta link (JS mantém carrinho no localStorage)
    itens_dict = [i.model_dump() for i in itens]
    return {"url": gerar_link_whatsapp(itens_dict)}


# =============================================================================
# Admin (Login por formulário + sessão)
# =============================================================================

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@app.post("/admin/login")
def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    # Comentário: valida credenciais do ENV
    if not (hmac.compare_digest(username, ADMIN_USER) and hmac.compare_digest(password, ADMIN_PASSWORD)):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Usuário ou senha inválidos."},
            status_code=401,
        )

    resp = RedirectResponse("/admin", status_code=303)
    cookie_value = _make_session_cookie(username)

    # Comentário: HttpOnly impede JS de ler; SameSite=Lax evita CSRF básico
    resp.set_cookie(
        key=_COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        samesite="lax",
        secure=True,  # Render serve via HTTPS publicamente
        max_age=_SESSION_TTL_SECONDS,
    )
    return resp


# =============================================================================
# Admin (Painel + CRUD)
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


@app.post("/admin/produtos/novo")
def admin_produto_novo(
    _: str = Depends(_auth_admin),
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    # Comentário: zero disco; compacta em memória e salva no DB
    imagem_bytes: Optional[bytes] = None
    imagem_mime: Optional[str] = None

    if imagem and imagem.filename:
        raw = imagem.file.read()
        imagem_bytes, imagem_mime = _compress_to_jpeg(raw)

    novo = schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor)
    crud.create_produto(db, novo, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)

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
    imagem_mime: Optional[str] = None

    if imagem and imagem.filename:
        raw = imagem.file.read()
        imagem_bytes, imagem_mime = _compress_to_jpeg(raw)

    upd = schemas.ProdutoUpdate(
        nome=nome,
        descricao=descricao,
        valor=valor,
        ativo=ativo,
    )

    crud.update_produto(db, produto_id=produto_id, dados=upd, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produtos/{produto_id}/excluir")
def admin_produto_excluir(
    produto_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    crud.delete_produto(db, produto_id=produto_id)
    return RedirectResponse("/admin", status_code=303)
