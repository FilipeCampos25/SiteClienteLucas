from __future__ import annotations

"""
main.py
=======
Aplicação FastAPI (templates Jinja2) para catálogo + painel admin.

FOCO DESTA REFATORAÇÃO:
- Corrigir o fluxo de persistência e entrega de imagens (PNG/JPG) armazenadas no BANCO.
- Evitar "imagem corrompida" na hora de servir a imagem ao navegador.

O restante do comportamento do sistema foi preservado:
- Admin cadastra produtos em /admin/
- Usuários veem produtos na página inicial e detalhe do produto
"""

import base64
import hashlib
import hmac
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
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

import crud
import models
import schemas
from config import ADMIN_PASSWORD, ADMIN_USER, CORS_ORIGINS, WHATSAPP_NUMERO
from database import SessionLocal
from utils import gerar_link_whatsapp, telefone_visivel, gerar_link_whatsapp_text

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
app.mount("/images", StaticFiles(directory=os.path.join("static", "images")), name="images")
app.mount("/css", StaticFiles(directory=os.path.join("static", "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join("static", "js")), name="js")

templates = Jinja2Templates(directory="templates")

# Variáveis globais nas templates
templates.env.globals["WHATSAPP_NUMERO"] = WHATSAPP_NUMERO
templates.env.globals["WHATSAPP_LINK"] = f"https://wa.me/{WHATSAPP_NUMERO}" if WHATSAPP_NUMERO else ""
templates.env.globals["WHATSAPP_DISPLAY"] = telefone_visivel()
templates.env.globals["gerar_link_whatsapp_text"] = gerar_link_whatsapp_text


def _resolve_logo_url() -> Optional[str]:
    """
    COMENTÁRIO:
    - Se existir /static/images/logo.png, usamos como logo.
    - Se não existir, a template mostra apenas texto.
    """
    logo_path = os.path.join("static", "images", "logo.png")
    try:
        if os.path.exists(logo_path) and os.path.getsize(logo_path) > 0:
            return "/static/images/logo.png"
    except Exception:
        pass
    return None


templates.env.globals["LOGO_URL"] = _resolve_logo_url()

# =============================================================================
# DB dependency
# =============================================================================


def get_db() -> Generator[Session, None, None]:
    """
    COMENTÁRIO:
    Dependência padrão do FastAPI para abrir/fechar sessão do SQLAlchemy.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Imagens: validação + leitura segura
# =============================================================================

# Regras do usuário: apenas PNG/JPG
ALLOWED_MIME = {"image/png", "image/jpeg"}
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "4000000"))  # 4MB

# Assinaturas (magic bytes) para validação adicional.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPG_MAGIC = b"\xff\xd8\xff"


def _detect_image_mime(data: bytes) -> Optional[str]:
    """
    COMENTÁRIO:
    Valida o arquivo pela assinatura (magic bytes). Isso evita:
    - upload de arquivo com content_type falso
    - bytes inválidos que depois "quebram" no browser
    """
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPG_MAGIC):
        return "image/jpeg"
    return None


def _read_image_upload(file: UploadFile) -> Tuple[bytes, str]:
    """
    Lê o arquivo enviado pelo admin e valida:
    - Existe arquivo
    - MIME permitido (png/jpg)
    - Magic bytes compatível (anti-corrupção / anti-fake)
    - Tamanho máximo

    Retorna: (bytes, mime)
    """
    # 1) valida presença
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Nenhuma imagem enviada.")

    # 2) valida content-type declarado
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato inválido. Use PNG ou JPG.")

    # 3) lê bytes
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Imagem muito grande (max {MAX_IMAGE_BYTES} bytes).",
        )

    # 4) valida assinatura real (magic bytes)
    real_mime = _detect_image_mime(data)
    if real_mime is None:
        raise HTTPException(status_code=400, detail="Imagem inválida ou corrompida (assinatura não reconhecida).")

    # 5) garante consistência: se o browser mandou jpeg mas é png (ou vice-versa), usamos o real
    mime = real_mime

    # 6) rebobina (boa prática)
    try:
        file.file.seek(0)
    except Exception:
        pass

    return data, mime


def _produto_image_url(produto: models.Produto) -> str:
    """
    Retorna a melhor URL de imagem para o produto:
    - Se houver bytes no DB -> endpoint /media/produto/{id}
    - Se houver imagem_url legado -> usa, mas tenta evitar 404 em arquivos locais
    - Caso contrário -> placeholder local
    """
    if getattr(produto, "imagem_bytes", None):
        return f"/media/produto/{produto.id}"

    url = getattr(produto, "imagem_url", None)
    if url:
        # Se era URL local antiga (/uploads/... ou /images/...), valida se existe
        if url.startswith("/uploads/") or url.startswith("/images/"):
            local_path = os.path.join("static", url.lstrip("/"))
            if os.path.exists(local_path):
                return url
            return "/static/images/placeholder.png"
        return url

    return "/static/images/placeholder.png"


# =============================================================================
# Rotas públicas
# =============================================================================


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """
    Página inicial: lista produtos ativos.
    """
    produtos = crud.get_produtos_ativos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)
    return templates.TemplateResponse("index.html", {"request": request, "produtos": produtos})


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

    CAUSA MAIS COMUM DE "IMAGEM CORROMPIDA" NESTE TIPO DE SISTEMA:
    - Postgres retorna bytea como `memoryview` (psycopg2/psycopg3),
      e alguns fluxos acabam convertendo para string ou aplicando encoding.
    - Aqui nós:
        1) garantimos bytes puros (bytes(...))
        2) setamos corretamente o media_type (image/png ou image/jpeg)
        3) adicionamos ETag para cache sem inconsistências
    """
    produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not produto or not getattr(produto, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    # 1) normaliza o tipo: Postgres pode devolver memoryview; SQLite geralmente devolve bytes
    raw = produto.imagem_bytes
    img_bytes = bytes(raw) if isinstance(raw, (memoryview, bytearray)) else raw

    # 2) sanity-check opcional: garante que o que está no DB ainda é PNG/JPG válido
    real_mime = _detect_image_mime(img_bytes)
    if real_mime is None:
        # Se chegou aqui, significa que o DB realmente está com bytes inválidos
        # (ou foi gravado incorretamente no passado).
        raise HTTPException(status_code=500, detail="Imagem inválida no banco (bytes não reconhecidos).")

    mime = real_mime

    # 3) ETag (hash) para cache consistente
    etag = produto.imagem_sha256 or hashlib.sha256(img_bytes).hexdigest()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    headers = {
        "Cache-Control": "public, max-age=86400",  # 1 dia
        "ETag": etag,
        # Content-Length ajuda alguns proxies/CDNs e evita truncamentos estranhos
        "Content-Length": str(len(img_bytes)),
    }

    return Response(content=img_bytes, media_type=mime, headers=headers)


@app.post("/api/whatsapp")
def api_whatsapp(itens: list[schemas.ItemCarrinho]):
    """
    Recebe itens do carrinho e devolve URL formatada do WhatsApp.
    """
    url = gerar_link_whatsapp([it.dict() for it in itens])
    return {"url": url}


# =============================================================================
# Admin: autenticação e painel
# =============================================================================

security = HTTPBasic(auto_error=False)


def _create_admin_token(username: str) -> str:
    """
    Token HMAC simples: username:timestamp:assinatura
    COMENTÁRIO:
    - Não é JWT (intencional): menos dependências e suficiente aqui.
    """
    ts = str(int(time.time()))
    data = f"{username}:{ts}"
    sig = hmac.new(ADMIN_PASSWORD.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{data}:{sig}"


def _verify_admin_token(token: str, max_age: int = 86400) -> bool:
    """
    Valida token do cookie.
    """
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False

        username, ts, sig = parts
        if username != ADMIN_USER:
            return False

        data = f"{username}:{ts}"
        expected = hmac.new(ADMIN_PASSWORD.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False

        if int(time.time()) - int(ts) > max_age:
            return False

        return True
    except Exception:
        return False


async def verify_admin(request: Request, credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    """
    Aceita:
    - HTTP Basic (para scripts/testes)
    - Cookie token (login via /admin/login)
    """
    # 1) tenta basic auth, se veio
    if isinstance(credentials, HTTPBasicCredentials):
        if secrets.compare_digest(credentials.username, ADMIN_USER) and secrets.compare_digest(
            credentials.password, ADMIN_PASSWORD
        ):
            return True

    # 2) tenta cookie
    token = request.cookies.get("admin_token")
    if token and _verify_admin_token(token):
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Basic"},
    )


@app.get("/admin/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Dashboard admin com formulário de criação e lista de produtos.
    """
    try:
        await verify_admin(request)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse(url="/admin/login")
        raise

    produtos = db.query(models.Produto).all()
    for p in produtos:
        p.imagem_url = _produto_image_url(p)
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "produtos": produtos})


@app.post("/admin/produto")
async def admin_create(
    request: Request,
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem_arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Cria produto + grava imagem no banco.

    COMENTÁRIO:
    - Mantém UX simples para admin: upload direto PNG/JPG.
    """
    await verify_admin(request)

    img_bytes, img_mime = _read_image_upload(imagem_arquivo)

    produto_in = schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor)
    crud.create_produto(db, produto_in, imagem_bytes=img_bytes, imagem_mime=img_mime)

    return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/upload")
async def admin_upload(request: Request, file: UploadFile = File(...)):
    """
    Upload avulso para pré-visualização (não persiste).
    Retorna data-url.
    """
    await verify_admin(request)

    img_bytes, img_mime = _read_image_upload(file)
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return {"data_url": f"data:{img_mime};base64,{b64}"}


@app.post("/admin/produto/{produto_id}")
async def admin_update_or_delete(produto_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Suporte a PUT/DELETE via POST (_method).
    """
    await verify_admin(request)

    form = await request.form()
    method = (form.get("_method") or "").upper()

    if method == "PUT":
        update_kwargs = {
            "nome": form.get("nome"),
            "descricao": form.get("descricao"),
            "valor": float(form.get("valor")) if form.get("valor") else None,
        }

        img_bytes = None
        img_mime = None
        imagem_arquivo = form.get("imagem_arquivo")
        if isinstance(imagem_arquivo, UploadFile) and imagem_arquivo.filename:
            img_bytes, img_mime = _read_image_upload(imagem_arquivo)

        produto_up = schemas.ProdutoUpdate(**update_kwargs)
        updated = crud.update_produto(db, produto_id, produto_up, imagem_bytes=img_bytes, imagem_mime=img_mime)
        if not updated:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

        return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)

    if method == "DELETE":
        crud.delete_produto(db, produto_id)
        return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)

    raise HTTPException(status_code=400, detail="Método inválido")


# ----- Login / logout (gráfico) -----


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})


@app.post("/admin/login", response_class=HTMLResponse)
def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Login do admin: cria cookie com token.
    """
    if secrets.compare_digest(username, ADMIN_USER) and secrets.compare_digest(password, ADMIN_PASSWORD):
        token = _create_admin_token(username)
        resp = RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)

        # COMENTÁRIO:
        # - secure=True => requer HTTPS (recomendado em produção).
        # - em dev/local, se você estiver em HTTP, pode mudar para secure=False.
        resp.set_cookie(
            "admin_token",
            token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=86400,
            path="/",
        )
        return resp

    return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Credenciais inválidas"}, status_code=401)


@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("admin_token", path="/")
    return resp
