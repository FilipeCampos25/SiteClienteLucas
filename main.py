from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import psycopg2

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "secret_render")
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

# ---------------- HOME ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, nome, preco, imagem FROM produtos")
    produtos = cur.fetchall()
    cur.close()
    db.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "produtos": produtos
    })

# ---------------- PRODUTO ----------------
@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto(request: Request, produto_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, nome, descricao, preco, imagem FROM produtos WHERE id=%s", (produto_id,))
    produto = cur.fetchone()
    cur.close()
    db.close()

    return templates.TemplateResponse("produto.html", {
        "request": request,
        "produto": produto
    })

# ---------------- CARRINHO ----------------
@app.post("/carrinho/add/{produto_id}")
def add_carrinho(request: Request, produto_id: int):
    carrinho = request.session.get("carrinho", {})
    carrinho[str(produto_id)] = carrinho.get(str(produto_id), 0) + 1
    request.session["carrinho"] = carrinho
    return RedirectResponse("/carrinho", status_code=303)

@app.get("/carrinho", response_class=HTMLResponse)
def carrinho(request: Request):
    carrinho = request.session.get("carrinho", {})
    itens = []

    if carrinho:
        db = get_db()
        cur = db.cursor()
        for pid, qtd in carrinho.items():
            cur.execute("SELECT id, nome, preco FROM produtos WHERE id=%s", (pid,))
            produto = cur.fetchone()
            itens.append({
                "id": produto[0],
                "nome": produto[1],
                "preco": produto[2],
                "qtd": qtd,
                "total": produto[2] * qtd
            })
        cur.close()
        db.close()

    return templates.TemplateResponse("carrinho.html", {
        "request": request,
        "itens": itens
    })

# ---------------- ADMIN AUTH ----------------
def admin_required(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/admin/login", status_code=303)

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})

@app.post("/admin/login")
def admin_login_post(
    request: Request,
    usuario: str = Form(...),
    senha: str = Form(...)
):
    if usuario == os.getenv("ADMIN_USER") and senha == os.getenv("ADMIN_PASS"):
        request.session["admin"] = True
        return RedirectResponse("/admin/dashboard", status_code=303)

    return RedirectResponse("/admin/login", status_code=303)

@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, nome, preco FROM produtos")
    produtos = cur.fetchall()
    cur.close()
    db.close()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "produtos": produtos
    })
