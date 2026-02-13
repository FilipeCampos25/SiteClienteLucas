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

O restante do comportamento do sistema foi preservado:
- Admin cadastra produtos em /admin/
- Usuários veem produtos na página inicial e detalhe do produto
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
# Obs: exigirá adicionar `pillow` em requirements.txt.
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
# Imagens: validação + leitura segura (+ compactação no upload)
# =============================================================================

# Regras do usuário: apenas PNG/JPG
ALLOWED_MIME = {"image/png", "image/jpeg"}
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "4000000"))  # 4MB (limite de upload bruto)

# Tópico 2: Compactação automática no upload
# ------------------------------------------------------------
# Objetivo: permitir que o ADMIN suba "qualquer foto" (celular),
# mas armazenar no DB uma versão mais leve para não estourar storage
# e melhorar performance de carregamento.
#
# Defaults recomendados (ajustáveis via ENV):
# - alvo: ~200KB (200 * 1024)
# - maior lado: 1200px
TARGET_IMAGE_BYTES = int(os.getenv("TARGET_IMAGE_BYTES", str(200 * 1024)))
IMAGE_MAX_DIM = int(os.getenv("IMAGE_MAX_DIM", "1200"))

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


def _has_alpha(img: Image.Image) -> bool:
    """
    COMENTÁRIO:
    Retorna True se a imagem possui transparência (alpha).

    Por quê?
    - Se tiver transparência, não dá pra salvar como JPEG sem perder alpha.
    - Então mantemos como PNG nesse caso.
    """
    if img.mode in ("RGBA", "LA"):
        return True
    # Alguns PNGs em modo "P" podem ter transparência via paleta
    return "transparency" in img.info


def _resize_if_needed(img: Image.Image, max_dim: int) -> Image.Image:
    """
    Redimensiona mantendo proporção se a imagem exceder `max_dim` no maior lado.

    Nota:
    - Downscale controlado é uma das maiores economias de tamanho do arquivo.
    - Para vitrine, 1200px no maior lado costuma ser excelente.
    """
    if max_dim <= 0:
        return img

    w, h = img.size
    longest = max(w, h)
    if longest <= max_dim:
        return img

    scale = max_dim / float(longest)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    # LANCZOS é o melhor para downscale (qualidade).
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _encode_jpeg_under_target(img: Image.Image, target_bytes: int) -> bytes:
    """
    Codifica a imagem como JPEG tentando ficar <= target_bytes.

    Estratégia:
    - binary search de qualidade entre 35..90
    - se ainda ficar maior que o alvo, o chamador pode reduzir dimensões e tentar de novo

    Obs:
    - JPEG é excelente para fotos (sem transparência).
    - Esse método tenta manter qualidade o maior possível dentro do alvo.
    """
    # JPEG não suporta alfa: garante RGB.
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    low, high = 35, 90
    best: Optional[bytes] = None

    while low <= high:
        q = (low + high) // 2
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        data = buf.getvalue()

        if len(data) <= target_bytes:
            best = data
            # tenta melhorar a qualidade mantendo <= alvo
            low = q + 1
        else:
            high = q - 1

    # Se não conseguiu ficar abaixo, retorna o menor (qualidade mais baixa)
    if best is not None:
        return best

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=35, optimize=True, progressive=True)
    return buf.getvalue()


def _encode_png(img: Image.Image) -> bytes:
    """
    Codifica como PNG com compressão alta (sem perda).

    Nota:
    - PNG é maior que JPEG para fotos, mas é necessário quando há transparência.
    - compress_level=9: mais compressão (mais CPU), mas upload é raro (admin),
      então vale a pena.
    """
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def _optimize_image_bytes(data: bytes, mime: str) -> Tuple[bytes, str]:
    """
    Tópico 2: Compactar automaticamente a imagem no upload.

    Regras:
    - Entrada: PNG/JPG (já validado)
    - Saída: PNG ou JPG (sempre)
    - Mantém transparência (PNG) quando existir alfa
    - Para fotos (sem alfa), converte/salva como JPEG otimizado
    - Tenta ficar <= TARGET_IMAGE_BYTES, reduzindo qualidade/dimensões de forma controlada

    Por que isso é ideal para um admin leigo?
    - Ele sobe a imagem "do jeito que tem" (celular / galeria)
    - O sistema automaticamente padroniza e deixa leve para o DB/site.
    """
    try:
        img = Image.open(io.BytesIO(data))
        # Corrige rotação de fotos de celular (EXIF)
        img = ImageOps.exif_transpose(img)
    except Exception:
        # Se Pillow não conseguir abrir, é melhor falhar do que salvar bytes quebrados
        raise HTTPException(status_code=400, detail="Imagem inválida (não foi possível processar).")

    # 1) Redimensiona para um tamanho adequado de vitrine
    img = _resize_if_needed(img, IMAGE_MAX_DIM)

    # 2) Decide formato final
    alpha = _has_alpha(img)
    out_mime: str

    # 3) Tenta alcançar o alvo de tamanho.
    #    Se não alcançar, reduz dimensões gradualmente até um mínimo razoável.
    min_dim = 320  # mínimo para não ficar ridículo em vitrine

    while True:
        if alpha:
            # Mantém PNG quando existe transparência
            out_bytes = _encode_png(img.convert("RGBA") if img.mode != "RGBA" else img)
            out_mime = "image/png"
        else:
            # Para foto (sem alpha), JPEG é mais leve e mantém boa qualidade
            out_bytes = _encode_jpeg_under_target(img, TARGET_IMAGE_BYTES)
            out_mime = "image/jpeg"

        # Se já está <= alvo, sucesso
        if len(out_bytes) <= TARGET_IMAGE_BYTES:
            return out_bytes, out_mime

        # Se passou do alvo, tenta diminuir dimensões antes de desistir
        w, h = img.size
        if max(w, h) <= min_dim:
            # Não reduz mais: salva mesmo assim (melhor do que falhar cadastro do produto)
            # Obs: isso acontece raramente (ex.: PNG com alpha muito "complexo").
            return out_bytes, out_mime

        # reduz ~10% e tenta novamente
        scale = 0.90
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _read_image_upload(file: UploadFile) -> Tuple[bytes, str]:
    """
    Lê o arquivo enviado pelo admin e valida:
    - Existe arquivo
    - MIME permitido (png/jpg)
    - Magic bytes compatível (anti-corrupção / anti-fake)
    - Tamanho máximo (upload bruto)

    Retorna: (bytes, mime)

    IMPORTANTE:
    - Aqui é onde aplicamos a compactação automática (tópico 2) antes de gravar no DB.
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

    # 7) Tópico 2: compacta automaticamente antes de armazenar no DB.
    #    Isso evita estourar o banco (storage) e melhora o carregamento do site.
    data, mime = _optimize_image_bytes(data, mime)

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


HOME_PAGE_SIZE = 10


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

    items.extend(range(window_start, window_end + 1))

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

    CAUSA MAIS COMUM DE "IMAGEM CORROMPIDA" NESTE TIPO DE SISTEMA:
    - Postgres retorna bytea como `memoryview` (psycopg2/psycopg3),
      e alguns fluxos acabam convertendo para string ou aplicando encoding.

    A solução correta é:
    - Garantir `bytes(...)` ao entregar
    - Usar media_type correto
    - Opcional: ETag/cache
    """
    produto = crud.get_produto(db, produto_id)
    if not produto or not getattr(produto, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    raw = produto.imagem_bytes

    # psycopg2/psycopg3 podem devolver memoryview
    if isinstance(raw, memoryview):
        img_bytes = raw.tobytes()
    else:
        img_bytes = bytes(raw)

    # MIME preferencial do DB, mas validamos assinatura por segurança
    mime = getattr(produto, "imagem_mime", None) or _detect_image_mime(img_bytes) or "application/octet-stream"

    # Se assinatura não bate com PNG/JPG, falha (dados no banco estão inválidos)
    real_mime = _detect_image_mime(img_bytes)
    if real_mime is None:
        raise HTTPException(status_code=500, detail="Imagem no banco está inválida/corrompida.")

    # Normaliza mime com base no real
    mime = real_mime

    # ETag simples (hash do conteúdo). Ajuda browser a cachear.
    etag = hashlib.sha256(img_bytes).hexdigest()

    # If-None-Match: evita retransferir a imagem
    inm = request.headers.get("if-none-match")
    if inm and inm.strip('"') == etag:
        return Response(status_code=304)

    headers = {
        "Content-Type": mime,
        "Content-Length": str(len(img_bytes)),
        "ETag": f"\"{etag}\"",
        # Cache público (ajuste como preferir). Como o conteúdo muda quando a imagem muda,
        # o ETag protege.
        "Cache-Control": "public, max-age=86400",
    }
    return Response(content=img_bytes, media_type=mime, headers=headers)


# =============================================================================
# Auth Admin
# =============================================================================

security = HTTPBasic()


def _auth_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Autenticação básica do admin.

    COMENTÁRIO:
    Mantém o comportamento original: Basic Auth para /admin.
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
# Rotas Admin
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
def admin_page(request: Request, _: str = Depends(_auth_admin), db: Session = Depends(get_db)):
    """
    Página do admin: lista produtos + form de cadastro.
    """
    produtos = crud.get_produtos(db)
    for p in produtos:
        p.imagem_url = _produto_image_url(p)
    return templates.TemplateResponse("admin.html", {"request": request, "produtos": produtos})


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
    - A imagem é lida/validada e agora também é compactada automaticamente (tópico 2)
      dentro de _read_image_upload(...).
    """
    img_bytes, img_mime = _read_image_upload(imagem_arquivo)

    produto = crud.create_produto(
        db,
        schemas.ProdutoCreate(nome=nome, descricao=descricao, valor=valor),
        imagem_bytes=img_bytes,
        imagem_mime=img_mime,
    )
    return RedirectResponse(url="/admin/", status_code=303)


@app.post("/admin/produto/{produto_id}/delete")
def admin_delete_produto(produto_id: int, _: str = Depends(_auth_admin), db: Session = Depends(get_db)):
    """
    Remove produto do DB (comportamento atual).
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
    - Se o admin enviar uma nova imagem, ela também passa por _read_image_upload,
      portanto também é compactada automaticamente (tópico 2).
    """
    img_bytes: Optional[bytes] = None
    img_mime: Optional[str] = None

    if imagem_arquivo and imagem_arquivo.filename:
        img_bytes, img_mime = _read_image_upload(imagem_arquivo)

    crud.update_produto(
        db,
        produto_id,
        nome=nome,
        descricao=descricao,
        valor=valor,
        imagem_bytes=img_bytes,
        imagem_mime=img_mime,
    )
    return RedirectResponse(url="/admin/", status_code=303)


# =============================================================================
# WhatsApp (mantido)
# =============================================================================

@app.post("/api/whatsapp")
def api_whatsapp(payload: dict):
    """
    Gera link do WhatsApp com texto.
    (Mantido; não faz parte do tópico 2)
    """
    link = gerar_link_whatsapp(payload)
    return {"url": link}
