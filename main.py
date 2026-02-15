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
# Admin auth (cookie assinado + basic)
# =============================================================================

security = HTTPBasic()

_COOKIE_NAME = "admin_session"
_COOKIE_TTL_SECONDS = 60 * 60 * 6  # 6h


def _sign_session_cookie(username: str) -> str:
    """
    Gera um cookie assinado (HMAC) com:
      base64(payload).base64(signature)
    payload = "username|exp"
    """
    exp = int(time.time()) + _COOKIE_TTL_SECONDS
    payload = f"{username}|{exp}".encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii")

    sig = hmac.new(
        ADMIN_PASSWORD.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii")
    return f"{payload_b64}.{sig_b64}"


def _verify_session_cookie(cookie_value: str) -> Optional[str]:
    """
    Valida cookie assinado.
    Retorna username se OK; senão None.
    """
    try:
        parts = cookie_value.split(".", 1)
        if len(parts) != 2:
            return None

        payload_b64, sig_b64 = parts
        payload = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        given_sig = base64.urlsafe_b64decode(sig_b64.encode("ascii"))

        expected_sig = hmac.new(
            ADMIN_PASSWORD.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(given_sig, expected_sig):
            return None

        # Payload = username|exp
        username, exp_str = payload.decode("utf-8").split("|", 1)
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

def _build_pagination(pagina_atual: int, total_paginas: int) -> list[Optional[int]]:
    """
    Monta a lista de páginas para o template (com reticências).

    O template espera:
      - int para páginas clicáveis
      - None para renderizar "…" (ellipsis)

    Mantemos a UI existente em templates/index.html, só alimentando os dados.
    """
    # Comentário: defesa simples para evitar estados inválidos
    if total_paginas <= 1:
        return [1]

    pagina_atual = max(1, min(pagina_atual, total_paginas))

    # Comentário: estratégia simples e previsível:
    # - sempre mostra 1 e última
    # - mostra um "miolo" de 2 páginas antes/depois da atual
    janela = 2

    paginas: list[Optional[int]] = []

    def _add(p: Optional[int]) -> None:
        # Evita duplicatas (principalmente quando total_paginas é pequeno)
        if paginas and paginas[-1] == p:
            return
        paginas.append(p)

    _add(1)

    inicio = max(2, pagina_atual - janela)
    fim = min(total_paginas - 1, pagina_atual + janela)

    if inicio > 2:
        _add(None)  # …

    for p in range(inicio, fim + 1):
        _add(p)

    if fim < total_paginas - 1:
        _add(None)  # …

    _add(total_paginas)

    return paginas


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db), page: int = 1):
    """
    Página inicial (catálogo) com paginação.

    Requisito:
    - Exibir 20 itens por página.
    - O template já possui o componente de paginação; aqui apenas
      fornecemos as variáveis (pagina_atual / total_paginas / paginacao).

    Observação importante (mínimo delta):
    - Não alteramos lógica de produto, carrinho, ou rotas.
    - Apenas limitamos a query + adicionamos metadados de paginação.
    """
    # ------------------------------
    # Paginação (20 por página)
    # ------------------------------
    POR_PAGINA = 20

    # Comentário: defesa para query param inválido (ex.: ?page=0 ou ?page=-1)
    if page < 1:
        page = 1

    # Conta total de produtos ativos (para calcular total_paginas)
    total_itens = (
        db.query(models.Produto)
        .filter(models.Produto.ativo.is_(True))
        .count()
    )

    # Comentário: se não tem itens, mantém total_paginas=0 e lista vazia
    total_paginas = (total_itens + POR_PAGINA - 1) // POR_PAGINA if total_itens else 0

    # Ajusta página caso o usuário peça uma página acima do máximo
    if total_paginas and page > total_paginas:
        page = total_paginas

    offset = (page - 1) * POR_PAGINA

    # Busca apenas os itens da página atual
    produtos = (
        db.query(models.Produto)
        .filter(models.Produto.ativo.is_(True))
        .order_by(models.Produto.id.desc())
        .offset(offset)
        .limit(POR_PAGINA)
        .all()
    )

    # Prepara URL da imagem (DB) para o template
    for p in produtos:
        p.imagem_url = _produto_image_url(p)

    # Link “fale conosco” do hero
    whatsapp_link = f"https://wa.me/{WHATSAPP_NUMERO}" if WHATSAPP_NUMERO else "#"

    # Lista de páginas para o componente já existente no template
    paginacao = _build_pagination(page, total_paginas) if total_paginas > 1 else [1]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "produtos": produtos,
            "WHATSAPP_LINK": whatsapp_link,
            "TEL_VISIVEL": telefone_visivel(),
            "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
            # Variáveis usadas pelo bloco de paginação em templates/index.html
            "pagina_atual": page,
            "total_paginas": total_paginas,
            "paginacao": paginacao,
        },
    )


@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detalhe(produto_id: int, request: Request, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not produto.ativo:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    produto.imagem_url = _produto_image_url(produto)

    return templates.TemplateResponse(
        "produto.html",
        {
            "request": request,
            "produto": produto,
            "TEL_VISIVEL": telefone_visivel(),
            "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
        },
    )


@app.post("/whatsapp", response_class=RedirectResponse)
def whatsapp_redirect(request: Request):
    """
    Recebe os itens do carrinho (via JS) e redireciona para o WhatsApp.
    Não usa DB aqui: apenas monta o texto com base no payload.
    """
    # Comentário: o JS monta um form e faz POST com itens
    form = request._form if hasattr(request, "_form") else None  # defensivo
    raise HTTPException(status_code=400, detail="Use /api/whatsapp para gerar link.")


@app.post("/api/whatsapp")
async def api_whatsapp(request: Request):
    """
    API para gerar link WhatsApp a partir do carrinho.
    O frontend manda JSON: { itens: [ {id, nome, valor_unitario, quantidade}, ... ] }
    """
    data = await request.json()
    itens = data.get("itens", [])
    link = gerar_link_whatsapp(itens)
    return {"link": link}


# =============================================================================
# Media: serve imagem do DB
# =============================================================================

@app.get("/media/produto/{produto_id}")
def media_produto(produto_id: int, db: Session = Depends(get_db)):
    """
    Serve bytes da imagem armazenada no banco (Neon/Postgres).
    Usa SHA256 como ETag simples.
    """
    p = crud.get_produto(db, produto_id=produto_id)
    if not p or not p.ativo:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    if not p.imagem_bytes:
        # Fallback: sem imagem -> 404 (template usa placeholder via onerror)
        raise HTTPException(status_code=404, detail="Imagem não disponível")

    # Comentário: ETag simples (SHA256) para cache
    etag = (p.imagem_sha256 or "").strip()
    if not etag:
        # Se não tiver sha salvo, calcula em runtime (raro)
        etag = hashlib.sha256(p.imagem_bytes).hexdigest()

    headers = {"ETag": etag, "Cache-Control": "public, max-age=86400"}
    return Response(
        content=p.imagem_bytes,
        media_type=p.imagem_mime or "application/octet-stream",
        headers=headers,
    )


# =============================================================================
# Admin
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, user: str = Depends(_auth_admin), db: Session = Depends(get_db)):
    """
    Admin: lista produtos (todos) e permite criar/editar.
    """
    produtos = crud.get_produtos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)

    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "user": user,
            "produtos": produtos,
        },
    )


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@app.post("/admin/login")
def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    # Comentário: valida credenciais e seta cookie
    if not (
        hmac.compare_digest(username, ADMIN_USER)
        and hmac.compare_digest(password, ADMIN_PASSWORD)
    ):
        # Mantém mensagem simples
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Usuário/senha inválidos"},
            status_code=400,
        )

    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie(
        _COOKIE_NAME,
        _sign_session_cookie(username),
        httponly=True,
        max_age=_COOKIE_TTL_SECONDS,
        samesite="lax",
    )
    return resp


@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin/login", status_code=303)
    resp.delete_cookie(_COOKIE_NAME)
    return resp


@app.post("/admin/produto")
async def admin_create_produto(
    request: Request,
    user: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    ativo: bool = Form(True),
    imagem: UploadFile = File(None),
):
    """
    Cria produto (admin).
    Se vier imagem, compacta para JPEG e salva bytes no Postgres.
    """
    imagem_bytes = None
    imagem_mime = None

    if imagem is not None:
        raw = await imagem.read()
        if raw:
            compact, mime = _compress_to_jpeg(raw)
            imagem_bytes = compact
            imagem_mime = mime

    produto_in = schemas.ProdutoCreate(
        nome=nome,
        descricao=descricao,
        valor=valor,
        ativo=ativo,
    )

    crud.create_produto(db, produto_in, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/produto/{produto_id}")
async def admin_update_produto(
    produto_id: int,
    request: Request,
    user: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    ativo: bool = Form(True),
    imagem: UploadFile = File(None),
):
    """
    Atualiza produto (admin). Se enviar imagem nova, substitui bytes.
    """
    imagem_bytes = None
    imagem_mime = None

    if imagem is not None:
        raw = await imagem.read()
        if raw:
            compact, mime = _compress_to_jpeg(raw)
            imagem_bytes = compact
            imagem_mime = mime

    produto_in = schemas.ProdutoUpdate(
        nome=nome,
        descricao=descricao,
        valor=valor,
        ativo=ativo,
    )

    updated = crud.update_produto(
        db,
        produto_id=produto_id,
        produto=produto_in,
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/produto/{produto_id}/delete")
def admin_delete_produto(
    produto_id: int,
    user: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    deleted = crud.delete_produto(db, produto_id=produto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return RedirectResponse(url="/admin", status_code=303)


# =============================================================================
# API (opcional)
# =============================================================================

@app.get("/api/produtos")
def api_produtos(db: Session = Depends(get_db)):
    """
    Endpoint auxiliar que lista produtos ativos.
    Mantido para compatibilidade, mesmo que o carrinho não dependa dele.
    """
    produtos = crud.get_produtos_ativos(db)
    out = []
    for p in produtos:
        out.append(
            {
                "id": p.id,
                "nome": p.nome,
                "descricao": p.descricao,
                "valor": float(p.valor),
                "imagem_url": _produto_image_url(p),
            }
        )
    return {"produtos": out}
