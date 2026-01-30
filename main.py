from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import SessionLocal  # Remova o ", init_db"
import crud, schemas, models
from config import ADMIN_USER, ADMIN_PASSWORD, WHATSAPP_NUMERO, CORS_ORIGINS
from utils import gerar_link_whatsapp
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import os
import shutil
import uuid
import secrets  # Já importado, mas confirme

# Função para ser chamada pelo start.sh (cria tabelas se não existirem)
def init_db_and_admin():
    from database import Base
    from sqlalchemy import create_engine
    from config import DATABASE_URL
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cantoneira Fácil")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# static & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
# Legacy/static aliases to avoid 404s from older URLs or cached HTML
app.mount("/uploads", StaticFiles(directory=os.path.join("static", "uploads")), name="uploads")
app.mount("/images", StaticFiles(directory=os.path.join("static", "images")), name="images")
app.mount("/css", StaticFiles(directory=os.path.join("static", "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join("static", "js")), name="js")
templates = Jinja2Templates(directory="templates")

# Expor variáveis e helpers úteis para todas as templates
import utils
templates.env.globals['WHATSAPP_NUMERO'] = WHATSAPP_NUMERO
templates.env.globals['WHATSAPP_LINK'] = f"https://wa.me/{WHATSAPP_NUMERO}" if WHATSAPP_NUMERO else ''
templates.env.globals['WHATSAPP_DISPLAY'] = utils.telefone_visivel()
templates.env.globals['gerar_link_whatsapp_text'] = utils.gerar_link_whatsapp_text

# DB dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Upload helpers (armazenamento confiável no DB para imagens de produto)
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "4000000"))  # 4MB padrão (ajuste via env)

# Placeholder inline to avoid 404s when product image is missing/legacy
PLACEHOLDER_IMAGE_DATA_URL = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2"
    "NDAiIGhlaWdodD0iNDgwIiB2aWV3Qm94PSIwIDAgNjQwIDQ4MCI+PHJlY3Qgd2lk"
    "dGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0iI2YyZjJmMiIvPjxyZWN0IHg9"
    "IjE2IiB5PSIxNiIgd2lkdGg9IjYwOCIgaGVpZ2h0PSI0NDgiIHJ4PSIxNiIgZmls"
    "bD0iI2U2ZTZlNiIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBkb21pbmFudC1iYXNl"
    "bGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjOWE5YTlh"
    "IiBmb250LWZhbWlseT0iQXJpYWwsIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMjgi"
    "PlNlbSBpbWFnZW08L3RleHQ+PC9zdmc+"
)

def _resolve_produto_imagem_url(produto) -> str:
    """Retorna a URL de imagem mais confiavel para o produto, sem 404."""
    if getattr(produto, "imagem_bytes", None):
        return f"/media/produto/{produto.id}"

    url = getattr(produto, "imagem_url", None)
    if url:
        if url.startswith("/uploads/") or url.startswith("/images/"):
            local_path = os.path.join("static", url.lstrip("/"))
            if os.path.exists(local_path):
                return url
            return PLACEHOLDER_IMAGE_DATA_URL
        return url

    return PLACEHOLDER_IMAGE_DATA_URL

def _resolve_logo_url() -> str | None:
    logo_path = os.path.join("static", "images", "logo.png")
    try:
        if os.path.exists(logo_path) and os.path.getsize(logo_path) > 0:
            return "/static/images/logo.png"
    except Exception:
        pass
    return None

templates.env.globals['LOGO_URL'] = _resolve_logo_url()

def _read_upload_image(file: UploadFile) -> tuple[bytes, str]:
    """Lê uma imagem do upload e valida tipo/tamanho."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Nenhuma imagem enviada.")
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Formato inválido. Use PNG ou JPG.")

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"Imagem muito grande (max {MAX_IMAGE_BYTES} bytes).")

    # rebobina para evitar efeitos colaterais
    try:
        file.file.seek(0)
    except Exception:
        pass

    return data, file.content_type

# Public pages
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    produtos = crud.get_produtos_ativos(db)
    for p in produtos:
        p.imagem_url = _resolve_produto_imagem_url(p)
    return templates.TemplateResponse("index.html", {"request": request, "produtos": produtos})

@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detail(request: Request, produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id)
    if produto:
        produto.imagem_url = _resolve_produto_imagem_url(produto)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return templates.TemplateResponse("produto.html", {"request": request, "p": produto})

@app.get("/api/produtos", response_model=list[schemas.ProdutoOut])
def api_produtos(db: Session = Depends(get_db)):
    produtos = crud.get_produtos_ativos(db)
    for p in produtos:
        p.imagem_url = _resolve_produto_imagem_url(p)
    return produtos


@app.get("/media/produto/{produto_id}")
def media_produto(produto_id: int, request: Request, db: Session = Depends(get_db)):
    # Para servir imagens de forma confiável (armazenadas no DB)
    p = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not p or not getattr(p, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    etag = getattr(p, "imagem_sha256", None)
    if etag and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    headers = {"Cache-Control": "public, max-age=86400"}  # 1 dia
    if etag:
        headers["ETag"] = etag

    return Response(content=p.imagem_bytes, media_type=p.imagem_mime or "application/octet-stream", headers=headers)

@app.post("/api/whatsapp")
def api_whatsapp(itens: list[schemas.ItemCarrinho]):
    url = gerar_link_whatsapp([it.dict() for it in itens])
    return {"url": url}

# Admin routes (HTTP Basic Auth + cookie token)
security = HTTPBasic(auto_error=False)

import hmac
import hashlib
import time

# token helpers (HMAC of username:timestamp) - used for cookie-based login
def _create_admin_token(username: str) -> str:
    ts = str(int(time.time()))
    data = f"{username}:{ts}"
    sig = hmac.new(ADMIN_PASSWORD.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}:{sig}"

def _verify_admin_token(token: str, max_age: int = 86400) -> bool:
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        username, ts, sig = parts
        data = f"{username}:{ts}"
        expected = hmac.new(ADMIN_PASSWORD.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False
        if username != ADMIN_USER:
            return False
        if int(time.time()) - int(ts) > max_age:
            return False
        return True
    except Exception:
        return False

# Core verifier: accepts either Basic auth or a valid cookie token
async def verify_admin(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    import logging
    import secrets as _secrets

    # If called manually (not via DI), credentials may be a Depends object or awaitable; resolve it via security(request)
    if not isinstance(credentials, HTTPBasicCredentials):
        try:
            credentials = await security(request)
        except Exception:
            credentials = None

    try:
        # Try HTTP Basic if present
        if credentials:
            try:
                correct_user = _secrets.compare_digest(credentials.username, ADMIN_USER)
                correct_pass = _secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
                if correct_user and correct_pass:
                    return True
            except Exception:
                logging.exception("Erro ao comparar credenciais de admin")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Erro no servidor ao validar credenciais",
                )

        # Try cookie token
        token = request.cookies.get("admin_token")
        if token and _verify_admin_token(token):
            return True

        # Not authenticated
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    except HTTPException:
        raise
    except Exception:
        logging.exception("Erro inesperado ao verificar admin")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro no servidor ao validar credenciais")

# Dependency wrapper usable with Depends()
async def verify_admin_dep(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    return await verify_admin(request, credentials)

@app.get("/admin/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Redirect to graphical login if not authenticated
    try:
        await verify_admin(request)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse(url="/admin/login")
        raise

    try:
        produtos = db.query(models.Produto).all()
        for p in produtos:
            p.imagem_url = _resolve_produto_imagem_url(p)
        return templates.TemplateResponse("admin/dashboard.html", {"request": request, "produtos": produtos})
    except Exception:
        import logging
        logging.exception("Erro ao renderizar dashboard admin")
        # Mensagem diminuta para o usuário, detalhe no log
        return HTMLResponse("Internal Server Error while rendering admin dashboard. Check logs for details.", status_code=500)

@app.post("/admin/produto")
def admin_create(
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem_arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    ok: bool = Depends(verify_admin)
):
    imagem_bytes, imagem_mime = _read_upload_image(imagem_arquivo)
    novo = schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor)
    p = crud.create_produto(db, novo, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
    return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/upload")
def admin_upload(file: UploadFile = File(...), ok: bool = Depends(verify_admin)):
    imagem_bytes, imagem_mime = _read_upload_image(file)
    # endpoint de upload avulso sem vínculo com produto não persiste; devolvemos data-url para prévia
    import base64
    b64 = base64.b64encode(imagem_bytes).decode("ascii")
    return {"data_url": f"data:{imagem_mime};base64,{b64}"}

# Suporte a _method para forms (PUT/DELETE via POST)
@app.post("/admin/produto/{produto_id}")
async def admin_update_or_delete(produto_id: int, request: Request, db: Session = Depends(get_db), ok: bool = Depends(verify_admin)):
    form = await request.form()
    _method = form.get('_method')
    
    if _method == 'PUT':
        update_kwargs = {
            "nome": form.get('nome'),
            "descricao": form.get('descricao'),
            "valor": float(form.get('valor')) if form.get('valor') else None,
        }
        imagem_bytes = None
        imagem_mime = None
        imagem_arquivo = form.get('imagem_arquivo')
        if isinstance(imagem_arquivo, UploadFile) and imagem_arquivo.filename:
            imagem_bytes, imagem_mime = _read_upload_image(imagem_arquivo)
        update_data = schemas.ProdutoUpdate(**update_kwargs)
        p = crud.update_produto(db, produto_id, update_data, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
        if not p:
            raise HTTPException(404, "Produto não encontrado")
        return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)
    
    elif _method == 'DELETE':
        p = crud.delete_produto(db, produto_id)
        return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)
    
    raise HTTPException(400, "Método inválido")

# ----- Login / logout (graphical) -----
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})

@app.post("/admin/login")
def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    import secrets
    try:
        if secrets.compare_digest(username, ADMIN_USER) and secrets.compare_digest(password, ADMIN_PASSWORD):
            token = _create_admin_token(username)
            resp = RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)
            resp.set_cookie("admin_token", token, httponly=True, secure=True, samesite="lax", max_age=86400, path="/")
            return resp
        else:
            return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Credenciais inválidas"}, status_code=401)
    except Exception:
        import logging
        logging.exception("Erro no login admin")
        return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Erro no servidor"}, status_code=500)

@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("admin_token", path="/")
    return resp
