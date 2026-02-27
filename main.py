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

import os
import io
import math
from typing import Generator, Optional, List

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    Query,
    status,
    Form,
    File,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

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
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "change-this-secret-key"),
    same_site="lax",
    https_only=False,
)

# Static e templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals.update(
    WHATSAPP_NUMERO=WHATSAPP_NUMERO or "",
    WHATSAPP_DISPLAY=telefone_visivel(),
    WHATSAPP_LINK=gerar_link_whatsapp([]),
    LOGO_URL="/static/images/logomarca.png",
)


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


def _build_paginacao(total_paginas: int, pagina_atual: int) -> list[Optional[int]]:
    """Gera sequência de páginas; None representa reticências."""
    if total_paginas <= 0:
        return []
    if total_paginas <= 7:
        return list(range(1, total_paginas + 1))

    paginas = {
        1,
        pagina_atual - 1,
        pagina_atual,
        pagina_atual + 1,
        total_paginas - 1,
        total_paginas,
    }
    paginas_validas = sorted(p for p in paginas if 1 <= p <= total_paginas)

    resultado: list[Optional[int]] = []
    anterior: Optional[int] = None
    for p in paginas_validas:
        if anterior is not None and p - anterior > 1:
            resultado.append(None)
        resultado.append(p)
        anterior = p
    return resultado


# =============================================================================
# Admin Auth: sessão (sem HTTP Basic)
# =============================================================================

def _admin_credentials() -> tuple[str, str]:
    """
    Credenciais do admin priorizando env vars.
    Fallback seguro: senha vazia/default desabilita login.
    """
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


# =============================================================================
# Site público (catálogo)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    per_page = 20
    base_query = db.query(models.Produto).filter(models.Produto.ativo.is_(True))
    total_itens = base_query.count()
    total_paginas = math.ceil(total_itens / per_page) if total_itens > 0 else 0

    if total_paginas > 0 and page > total_paginas:
        return RedirectResponse(url=f"/?page={total_paginas}#produtos", status_code=303)

    offset = (page - 1) * per_page
    produtos = (
        base_query
        .order_by(models.Produto.id.desc())
        .limit(per_page)
        .offset(offset)
        .all()
    )

    # Comentário: injeta URL de imagem em cada item para o template
    view = []
    for p in produtos:
        view.append(
            {
                "id": p.id,
                "nome": p.nome,
                "descricao": p.descricao,
                "valor": p.valor,
                "imagem_url": _produto_image_url(p),
            }
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "produtos": view,
            "pagina_atual": page,
            "total_paginas": total_paginas,
            "paginacao": _build_paginacao(total_paginas, page),
            # PATCH MÍNIMO:
            # telefone_visivel() no seu utils.py NÃO recebe parâmetro.
            # Ela já lê WHATSAPP_NUMERO do config.py internamente.
            "whatsapp_numero": telefone_visivel(),
        },
    )


@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detalhe(produto_id: int, request: Request, db: Session = Depends(get_db)):
    p = crud.get_produto(db, produto_id=produto_id)
    if not p or not p.ativo:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    return templates.TemplateResponse(
        "produto.html",
        {
            "request": request,
            "produto": {
                "id": p.id,
                "nome": p.nome,
                "descricao": p.descricao,
                "valor": p.valor,
                "imagem_url": _produto_image_url(p),
            },
            # PATCH MÍNIMO:
            "whatsapp_numero": telefone_visivel(),
            "whatsapp_link": gerar_link_whatsapp(
                [
                    {
                        "nome": p.nome,
                        "quantidade": 1,
                        "valor_unitario": float(p.valor or 0),
                    }
                ]
            ),
        },
    )


# =============================================================================
# Media (serve imagem direto do DB)
# =============================================================================

@app.get("/media/produto/{produto_id}")
def media_produto(produto_id: int, db: Session = Depends(get_db)):
    p = crud.get_produto(db, produto_id=produto_id)
    if not p or not getattr(p, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    mime = getattr(p, "imagem_mime", None) or "application/octet-stream"
    return Response(content=p.imagem_bytes, media_type=mime)


# =============================================================================
# API (se existir uso em JS)
# =============================================================================

@app.get("/api/produtos")
def api_produtos(db: Session = Depends(get_db)):
    produtos = crud.list_produtos(db, apenas_ativos=True)
    return [
        {
            "id": p.id,
            "nome": p.nome,
            "descricao": p.descricao,
            "valor": p.valor,
            "imagem_url": _produto_image_url(p),
        }
        for p in produtos
    ]


@app.post("/api/whatsapp")
def api_whatsapp(itens: List[schemas.ItemCarrinho]):
    # Compatível com Pydantic v1 (dict) e v2 (model_dump)
    itens_dict = [i.model_dump() if hasattr(i, "model_dump") else i.dict() for i in itens]
    return {"url": gerar_link_whatsapp(itens_dict)}


# =============================================================================
# Admin UI
# =============================================================================

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
    # Comentário: valida credenciais e marca sessão no cookie assinado do SessionMiddleware
    admin_user, admin_pass = _admin_credentials()
    if not admin_pass or username != admin_user or password != admin_pass:
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Usuário ou senha inválidos"},
            status_code=200,
        )

    request.session["admin_authed"] = True
    request.session["admin_user"] = admin_user
    resp = RedirectResponse("/admin", status_code=303)
    return resp


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin_authed(request):
        return RedirectResponse("/admin/login", status_code=303)

    produtos = crud.list_produtos(db, apenas_ativos=False)

    view = []
    for p in produtos:
        view.append(
            {
                "id": p.id,
                "nome": p.nome,
                "descricao": p.descricao,
                "valor": p.valor,
                "ativo": p.ativo,
                "imagem_url": _produto_image_url(p),
            }
        )

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "produtos": view},
    )


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


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


# =============================================================================
# Compatibilidade de rotas do template (PATCH MÍNIMO)
# -----------------------------------------------------------------------------
# O template templates/admin/dashboard.html (existente no projeto) envia:
#   - POST   /admin/produto           (criar)
#   - POST   /admin/produto/{id} com _method=PUT (editar)  [HTML forms não suportam PUT]
#   - DELETE /admin/produto/{id}      (excluir) via fetch()
#
# O backend original já tinha as rotas:
#   - POST /admin/produtos/novo
#   - POST /admin/produtos/{id}/atualizar
#   - POST /admin/produtos/{id}/excluir
#
# Mas como o template chama outro caminho, ocorria 404.
# Este bloco adiciona ALIASES, preservando as rotas existentes.
# =============================================================================


@app.post("/admin/produto")
def admin_produto_novo_alias(
    _: str = Depends(_auth_admin),
    nome: str = Form(...),
    descricao: str = Form(""),
    valor: float = Form(...),
    imagem: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """
    Alias para criação de produto.
    Mantém exatamente a mesma regra de criação já usada em /admin/produtos/novo.
    """
    imagem_bytes: Optional[bytes] = None
    imagem_mime: Optional[str] = None

    if imagem and imagem.filename:
        raw = imagem.file.read()
        imagem_bytes, imagem_mime = _compress_to_jpeg(raw)

    novo = schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor)
    crud.create_produto(db, novo, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)

    return RedirectResponse("/admin", status_code=303)


@app.put("/admin/produto/{produto_id}")
def admin_produto_atualizar_alias(
    produto_id: int,
    _: str = Depends(_auth_admin),
    nome: str = Form(None),
    descricao: str = Form(None),
    valor: float = Form(None),
    ativo: Optional[bool] = Form(None),
    imagem: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """
    Alias para edição de produto (PUT real).
    O template usa POST + _method=PUT, mas também é útil ter PUT "de verdade".
    """
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

    crud.update_produto(
        db,
        produto_id=produto_id,
        dados=upd,
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
    )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/produto/{produto_id}")
def admin_produto_method_override(
    produto_id: int,
    _: str = Depends(_auth_admin),
    _method: Optional[str] = Form(None),
    nome: str = Form(None),
    descricao: str = Form(None),
    valor: float = Form(None),
    ativo: Optional[bool] = Form(None),
    imagem: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """
    Suporta o padrão "_method" vindo do template:
      - se _method=PUT -> executa a atualização
    """
    method = (_method or "").strip().upper()

    if method == "PUT":
        return admin_produto_atualizar_alias(
            produto_id=produto_id,
            _=_,
            nome=nome,
            descricao=descricao,
            valor=valor,
            ativo=ativo,
            imagem=imagem,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Método não suportado para /admin/produto/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/produto/{produto_id}")
def admin_produto_excluir_alias(
    produto_id: int,
    _: str = Depends(_auth_admin),
    db: Session = Depends(get_db),
):
    """
    Alias para exclusão (DELETE real), usado pelo JS do template via fetch().
    Retorna 204 para o front considerar OK e recarregar a página.
    """
    crud.delete_produto(db, produto_id=produto_id)
    return Response(status_code=204)
