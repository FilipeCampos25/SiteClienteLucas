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
    Resolve URL da imagem do produto.

    COMENTÁRIO:
    - Se a imagem estiver no banco (`imagem_bytes`), padroniza em /media/produto/{id}.
    - Se não houver, tenta fallback em `imagem_url`.
    - Se tudo falhar, usa placeholder.
    """
    if getattr(p, "imagem_bytes", None):
        return f"/media/produto/{p.id}"

    url = getattr(p, "imagem_url", "") or ""
    if url:
        return url

    return "/static/images/placeholder.png"


# =============================================================================
# Rotas públicas
# =============================================================================


# -----------------------------------------------------------------------------
# Paginação (HOME)
# - Carrega APENAS 10 produtos por página para reduzir carga no servidor/DB.
# - A navegação é feita via querystring: /?page=1, /?page=2 ...
# - O frontend (templates/index.html) renderiza botões com base em `paginacao`.
# -----------------------------------------------------------------------------

HOME_PAGE_SIZE = 10  # número fixo de produtos por página (otimização)


def _build_pagination_items(current_page: int, total_pages: int) -> list[int | None]:
    """
    Monta uma lista compacta de páginas para o frontend.
    `None` representa reticências.
    """
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    items: list[int | None] = [1]
    window_start = max(2, current_page - 1)
    window_end = min(total_pages - 1, current_page + 1)

    if window_start > 2:
        items.append(None)

    for p in range(window_start, window_end + 1):
        items.append(p)

    if window_end < total_pages - 1:
        items.append(None)

    items.append(total_pages)
    return items


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """
    Página inicial: lista produtos ativos.

    COMENTÁRIO (PAGINAÇÃO):
    - Conta o total de produtos ativos.
    - Calcula total de páginas com HOME_PAGE_SIZE (=10).
    - Busca só os itens do "page" atual via OFFSET/LIMIT.
    - Envia `paginacao` para o template montar os botões.
    """
    total_produtos = crud.count_produtos_ativos(db)
    total_paginas = max(1, math.ceil(total_produtos / HOME_PAGE_SIZE))
    pagina_atual = min(page, total_paginas)

    produtos = crud.get_produtos_ativos_paginados(db, page=pagina_atual, page_size=HOME_PAGE_SIZE)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)

    paginacao = _build_pagination_items(pagina_atual, total_paginas)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "produtos": produtos,
            "pagina_atual": pagina_atual,
            "total_paginas": total_paginas,
            "total_produtos": total_produtos,
            "paginacao": paginacao,
        },
    )


@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detail(request: Request, produto_id: int, db: Session = Depends(get_db)):
    """
    Página de detalhe do produto.
    """
    produto = crud.get_produto(db, produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    produto.imagem_url = _produto_image_url(produto)
    return templates.TemplateResponse("produto.html", {"request": request, "p": produto})


@app.get("/api/produtos", response_model=list[schemas.ProdutoOut])
def api_produtos(db: Session = Depends(get_db)):
    """
    API JSON: lista produtos ativos.
    """
    produtos = crud.get_produtos_ativos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)
    return produtos


@app.get("/media/produto/{produto_id}")
def media_produto(produto_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Entrega a imagem guardada no DB de forma *byte-perfect*.

    CAUSA MAIS COMUM DE "IMAGEM CORROMPIDA":
    - Converter bytes <-> base64 <-> str e voltar, ou escrever com modo errado.
    Aqui nós:
    - devolvemos exatamente os bytes salvos
    - colocamos Content-Type correto
    - usamos ETag com sha256 para cache do navegador
    """
    produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not produto or not produto.imagem_bytes:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    etag = produto.imagem_sha256 or hashlib.sha256(produto.imagem_bytes).hexdigest()
    client_etag = request.headers.get("if-none-match")

    if client_etag and client_etag.strip('"') == etag:
        return Response(status_code=304)

    return Response(
        content=produto.imagem_bytes,
        media_type=produto.imagem_mime or "application/octet-stream",
        headers={"ETag": f'"{etag}"'},
    )


# =============================================================================
# Admin
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
def admin_page(request: Request, _: str = Depends(_auth_admin), db: Session = Depends(get_db)):
    """
    Página do admin: lista produtos + form de cadastro.

    CORREÇÃO IMPORTANTE:
    - Antes: tentava renderizar "admin.html" (que NÃO existe no seu projeto),
      gerando jinja2.exceptions.TemplateNotFound: admin.html
    - Agora: renderiza "admin/dashboard.html" (arquivo que EXISTE em templates/admin/dashboard.html)
    """
    produtos = crud.get_produtos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)

    # ✅ template correto (existe no ZIP)
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "produtos": produtos})


@app.post("/admin/produto")
def admin_create_produto(
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem_arquivo: UploadFile = File(...),
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    """
    Cria produto no DB.

    COMENTÁRIO:
    - A imagem é lida/validada e compactada automaticamente (_read_image_upload).
    """
    img_bytes, img_mime = _read_image_upload(imagem_arquivo)

    crud.create_produto(
        db,
        schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor),
        imagem_bytes=img_bytes,
        imagem_mime=img_mime,
    )
    return RedirectResponse(url="/admin/", status_code=303)


@app.post("/admin/produto/{produto_id}/delete")
def admin_delete_produto(produto_id: int, _: str = Depends(_auth_admin), db: Session = Depends(get_db)):
    """
    Remove produto do DB (delete lógico).
    """
    crud.delete_produto(db, produto_id)
    return RedirectResponse(url="/admin/", status_code=303)


@app.post("/admin/produto/{produto_id}/edit")
def admin_edit_produto(
    produto_id: int,
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem_arquivo: Optional[UploadFile] = File(None),
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    """
    Edita produto existente.

    COMENTÁRIO:
    - Se enviar uma nova imagem, ela também passa por compactação/validação.
    """
    imagem_bytes: bytes | None = None
    imagem_mime: str | None = None

    if imagem_arquivo is not None:
        imagem_bytes, imagem_mime = _read_image_upload(imagem_arquivo)

    crud.update_produto(
        db,
        produto_id,
        schemas.ProdutoUpdate(nome=nome, descricao=descricao, valor=valor),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
    )
    return RedirectResponse(url="/admin/", status_code=303)


# =============================================================================
# WhatsApp helpers (injeção no template)
# =============================================================================

@app.get("/_template_context")
def _template_context():
    """
    Endpoint auxiliar (opcional) para debug.
    """
    return {
        "WHATSAPP_NUMERO": WHATSAPP_NUMERO,
        "WHATSAPP_LINK": gerar_link_whatsapp(WHATSAPP_NUMERO),
        "WHATSAPP_TEL_VISIVEL": telefone_visivel(WHATSAPP_NUMERO),
    }


# =============================================================================
# Upload helpers (compactação no upload)
# =============================================================================

def _read_image_upload(file: UploadFile) -> Tuple[bytes, str]:
    """
    Lê e valida a imagem enviada no upload e aplica compactação.

    REGRAS:
    - Aceita PNG e JPEG.
    - Converte para RGB quando necessário (ex: PNG com alpha), garantindo compatibilidade.
    - Redimensiona para no máx 1200px no maior lado (mantém proporção).
    - Salva como JPEG (qualidade 82) ou mantém PNG se necessário.
    """
    if not file:
        raise HTTPException(status_code=400, detail="Imagem obrigatória")

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Imagem vazia")

    # Detecta pelo content-type
    mime = (file.content_type or "").lower().strip()
    if mime not in ("image/png", "image/jpeg", "image/jpg"):
        raise HTTPException(status_code=400, detail="Formato de imagem inválido (use PNG ou JPEG)")

    try:
        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img)  # respeita orientação EXIF (celular)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha ao ler imagem: {e}") from e

    # Redimensiona (mantém proporção)
    max_side = 1200
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))

    # Normaliza modo
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    out = io.BytesIO()

    # Mantém PNG apenas se o upload era PNG e o modo for compatível.
    # Caso contrário, salva JPEG (mais leve).
    if mime == "image/png":
        img.save(out, format="PNG", optimize=True)
        out_bytes = out.getvalue()
        out_mime = "image/png"
    else:
        img.save(out, format="JPEG", quality=82, optimize=True, progressive=True)
        out_bytes = out.getvalue()
        out_mime = "image/jpeg"

    return out_bytes, out_mime
