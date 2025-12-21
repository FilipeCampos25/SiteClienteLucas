from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import SessionLocal  # Remova o ", init_db"
import crud, schemas, models
from config import ADMIN_USER, ADMIN_PASSWORD, WHATSAPP_NUMERO, CORS_ORIGINS
from utils import gerar_link_whatsapp
from fastapi.security import HTTPBasic, HTTPBasicCredentials
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

# Public pages
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    produtos = crud.get_produtos_ativos(db)
    return templates.TemplateResponse("index.html", {"request": request, "produtos": produtos})

@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detail(request: Request, produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return templates.TemplateResponse("produto.html", {"request": request, "p": produto})

@app.get("/api/produtos")
def api_produtos(db: Session = Depends(get_db)):
    produtos = crud.get_produtos_ativos(db)
    return produtos

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
def verify_admin(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    import logging
    import secrets as _secrets

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
def verify_admin_dep(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    return verify_admin(request, credentials)

@app.get("/admin/", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Redirect to graphical login if not authenticated
    try:
        verify_admin(request)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse(url="/admin/login")
        raise

    try:
        produtos = db.query(models.Produto).all()
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
    imagem_url: str = Form(""),
    db: Session = Depends(get_db),
    ok: bool = Depends(verify_admin_dep)
):
    novo = schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor, imagem_url=imagem_url)
    p = crud.create_produto(db, novo)
    return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/upload")
def admin_upload(file: UploadFile = File(...), ok: bool = Depends(verify_admin_dep)):
    return JSONResponse(
        {"error": "Upload de arquivos desativado. Configure um serviço de armazenamento externo."},
        status_code=400
    )

# Suporte a _method para forms (PUT/DELETE via POST)
@app.post("/admin/produto/{produto_id}")
async def admin_update_or_delete(produto_id: int, request: Request, db: Session = Depends(get_db), ok: bool = Depends(verify_admin_dep)):
    form = await request.form()
    _method = form.get('_method')
    
    if _method == 'PUT':
        update_data = schemas.ProdutoUpdate(
            nome=form.get('nome'),
            descricao=form.get('descricao'),
            valor=float(form.get('valor')) if form.get('valor') else None,
            imagem_url=form.get('imagem_url')
        )
        p = crud.update_produto(db, produto_id, update_data)
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