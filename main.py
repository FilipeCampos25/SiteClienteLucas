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

# Admin routes (HTTP Basic Auth)
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

@app.get("/admin/", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db), ok: bool = Depends(verify_admin)):
    produtos = db.query(models.Produto).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "produtos": produtos})

@app.post("/admin/produto")
def admin_create(
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem_url: str = Form(""),
    db: Session = Depends(get_db),
    ok: bool = Depends(verify_admin)
):
    novo = schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor, imagem_url=imagem_url)
    p = crud.create_produto(db, novo)
    return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/upload")
def admin_upload(file: UploadFile = File(...), ok: bool = Depends(verify_admin)):
    return JSONResponse(
        {"error": "Upload de arquivos desativado. Configure um serviço de armazenamento externo."},
        status_code=400
    )

# Suporte a _method para forms (PUT/DELETE via POST)
@app.post("/admin/produto/{produto_id}")
async def admin_update_or_delete(produto_id: int, request: Request, db: Session = Depends(get_db), ok: bool = Depends(verify_admin)):
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