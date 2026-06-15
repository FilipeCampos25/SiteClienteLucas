from __future__ import annotations

import io
import logging
import re
import secrets
import unicodedata
from typing import Generator, List, Optional
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import crud
import models
import schemas
from config import (
    ADMIN_PASSWORD,
    ADMIN_USER,
    CORS_ALLOW_CREDENTIALS,
    CORS_ORIGINS,
    FACEBOOK_URL,
    INSTAGRAM_URL,
    IS_PRODUCTION,
    MAX_IMAGE_BYTES,
    SECRET_KEY,
    STORE_ADDRESS,
    STORE_CNPJ,
    TRUST_PROXY_HEADERS,
    WHATSAPP_NUMERO,
)
from database import SessionLocal
from rate_limit import LoginRateLimiter, client_ip
from security import csrf_protect, get_csrf_token, rotate_session

logger = logging.getLogger(__name__)
login_rate_limiter = LoginRateLimiter()

app = FastAPI(title="Casa das Cantoneiras")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=IS_PRODUCTION,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _numero_whatsapp_limpo(numero: Optional[str]) -> str:
    return "".join(ch for ch in (numero or "") if ch.isdigit())


def _telefone_visivel_numero(numero: Optional[str]) -> str:
    num = _numero_whatsapp_limpo(numero)
    if not num:
        return ""

    if len(num) >= 12 and num.startswith("55"):
        country = "+" + num[:2]
        area = num[2:4]
        rest = num[4:]
        if len(rest) == 8:
            return f"{country} ({area}) {rest[:4]}-{rest[4:]}"
        if len(rest) == 9:
            return f"{country} ({area}) {rest[:5]}-{rest[5:]}"
        return f"{country} ({area}) {rest}"

    return "+" + num


def _whatsapp_link_numero(numero: Optional[str], texto: Optional[str] = None) -> str:
    num = _numero_whatsapp_limpo(numero)
    if not num:
        return "#"
    if texto:
        return f"https://wa.me/{num}?text={quote_plus(texto)}"
    return f"https://wa.me/{num}"


templates.env.globals.update(
    WHATSAPP_NUMERO=WHATSAPP_NUMERO or "",
    WHATSAPP_DISPLAY=_telefone_visivel_numero(WHATSAPP_NUMERO),
    WHATSAPP_LINK=_whatsapp_link_numero(WHATSAPP_NUMERO),
    INSTAGRAM_URL=INSTAGRAM_URL or "",
    FACEBOOK_URL=FACEBOOK_URL or "",
    STORE_ADDRESS=STORE_ADDRESS or "",
    STORE_CNPJ=STORE_CNPJ or "",
    LOGO_URL="/static/images/logomarca.png",
)

DEFAULT_CATEGORIAS_HOME = [
    {
        "slug": "cantoneiras-de-aluminio",
        "nome": "Cantoneiras de Aluminio",
        "nome_exibicao": "Cantoneiras de Alumínio",
        "subtitulo_exibicao": "",
        "imagem_url": "/static/images/img3.jpeg",
    },
    {
        "slug": "kits-para-montagem",
        "nome": "Cantoneiras para Suporte",
        "nome_exibicao": "Cantoneiras para Suporte",
        "subtitulo_exibicao": "",
        "imagem_url": "/static/images/img5.jpeg",
    },
    {
        "slug": "cantoneira-suporte-para-prateleira",
        "nome": "Acessorios",
        "nome_exibicao": "Acessórios",
        "subtitulo_exibicao": "Ferramentas",
        "imagem_url": "/static/images/img6.jpeg",
    },
    {
        "slug": "acessorios",
        "nome": "Faca voce mesmo",
        "nome_exibicao": "Faça você mesmo",
        "subtitulo_exibicao": "",
        "imagem_url": "/static/images/img8.jpeg",
    },
]
DEFAULT_SUBCATEGORIAS_POR_CATEGORIA = {
    "cantoneira-suporte-para-prateleira": [
        {
            "slug": "alicate-universal",
            "nome": "Alicate Universal",
            "nome_exibicao": "Alicate Universal",
            "imagem_url": "/static/images/alicate_universal.jpg",
        },
        {
            "slug": "chave-philips",
            "nome": "Chave Philips",
            "nome_exibicao": "Chave Philips",
            "imagem_url": "/static/images/Chave_Philips.jpeg",
        },
        {
            "slug": "kit-bits",
            "nome": "Kit Bits",
            "nome_exibicao": "Kit Bits",
            "imagem_url": "/static/images/Kit_Bits.jpg",
        },
        {
            "slug": "estilete",
            "nome": "Estilete",
            "nome_exibicao": "Estilete",
            "imagem_url": "/static/images/Estilete.jpeg",
        },
        {
            "slug": "trena",
            "nome": "Trena",
            "nome_exibicao": "Trena",
            "imagem_url": "/static/images/Trena.jpeg",
        },
    ],
}
DEFAULT_QUEM_SOMOS_IMAGENS = [
    {
        "alt_texto": "Casa das Cantoneiras",
        "imagem_url": "/static/images/img10.jpeg",
    },
    {
        "alt_texto": "Casa das Cantoneiras",
        "imagem_url": "/static/images/img11.jpeg",
    },
    {
        "alt_texto": "Casa das Cantoneiras",
        "imagem_url": "/static/images/img13.jpeg",
    },
    {
        "alt_texto": "Casa das Cantoneiras",
        "imagem_url": "/static/images/img14.jpeg",
    },
]

HOME_BANNER_IMAGE_KEY = "home_banner"
HOME_BANNER_DEFAULT_ALT = "Imagem institucional"
HOME_BANNER_DEFAULT_URL = "/static/images/img-larger.jpeg"
SITE_LOGO_IMAGE_KEY = "site_logo"
HOME_HERO_IMAGE_KEY = "home_hero_logo"

SITE_IMAGE_DEFAULTS = {
    SITE_LOGO_IMAGE_KEY: {
        "label": "Logo do header e footer",
        "help": "Usada na marca do topo e no rodape.",
        "alt_texto": "Logo Casa das Cantoneiras",
        "imagem_url": "/static/images/logomarca.png",
    },
    HOME_HERO_IMAGE_KEY: {
        "label": "Imagem principal da Home",
        "help": "Imagem exibida ao lado do texto principal da Home.",
        "alt_texto": "Logo Casa das Cantoneiras",
        "imagem_url": "/static/images/placeholder.png",
    },
    HOME_BANNER_IMAGE_KEY: {
        "label": "Banner institucional da Home",
        "help": "Imagem larga exibida abaixo das categorias.",
        "alt_texto": HOME_BANNER_DEFAULT_ALT,
        "imagem_url": HOME_BANNER_DEFAULT_URL,
    },
}

DEFAULT_MAP_EMBED_URL = (
    "https://www.google.com/maps?q=Rua%2008%2C%20Ch%C3%A1cara%20225%2C%20Loja%202%2F3%2C%20"
    "Vicente%20Pires%2C%20Bras%C3%ADlia%20-%20DF%2C%2072007-065&z=17&output=embed"
)

DEFAULT_SITE_CONFIG = {
    "site_title": "Casa das Cantoneiras - Catálogo",
    "header_brand_name": "CASA DAS CANTONEIRAS",
    "header_brand_tagline": "SOLUÇÕES EM PRODUTOS PARA FIXAÇÃO",
    "nav_home": "Home",
    "nav_quem_somos": "Quem Somos",
    "nav_produtos": "Produtos",
    "nav_contato": "Contato",
    "whatsapp_numero": WHATSAPP_NUMERO or "",
    "instagram_url": INSTAGRAM_URL or "",
    "facebook_url": FACEBOOK_URL or "",
    "home_hero_kicker": "Soluções em Cantoneiras e Acabamentos",
    "home_hero_title": (
        "Somos especialistas em acabamentos e suportes de alta qualidade. Oferecemos uma linha completa de "
        "cantoneiras de alumínio e zinco, soluções práticas para reboco, perfis antiderrapantes para escadas, "
        "além de cantoneiras reforçadas para o suporte de bancadas e prateleiras."
    ),
    "home_categories_kicker": "Categorias",
    "home_categories_title": "ESCOLHA UMA LINHA",
    "produtos_kicker": "Linha de produtos",
    "produtos_title": "ESCOLHA UMA LINHA",
    "produtos_subtitle": "Selecione uma categoria para acessar a página dedicada e visualizar os produtos disponíveis.",
    "quem_somos_title": "Quem somos:",
    "quem_somos_history_title": "Nossa História:",
    "quem_somos_history_text": (
        "A Casa das Cantoneiras surgiu da necessidade prática de encontrar tudo o que um projeto precisa em um só "
        "lugar, combinada com o desejo de empreender entregando excelência ao mercado. Somos especialistas em "
        "soluções de fixação e acabamento, oferecendo uma linha completa que vai de cantoneiras para escadas e "
        "paredes a suportes específicos para prateleiras e bancadas, seja para ambientes residenciais ou comerciais."
    ),
    "quem_somos_work_title": "Como Trabalhamos:",
    "quem_somos_work_text_1": (
        "Atendimento Próximo e Consultivo: Não queremos apenas vender, queremos entender. Oferecemos um suporte "
        "humanizado e técnico para que você encontre exatamente o que a sua estrutura precisa, sem complicações."
    ),
    "quem_somos_work_text_2": (
        "Compromisso Inegociável com a Qualidade: Trabalhamos com materiais de alto padrão que garantem "
        "durabilidade, resistência e o acabamento perfeito. Seu projeto merece a segurança de produtos que duram "
        "uma vida inteira."
    ),
    "quem_somos_button_label": "Fale com a equipe",
    "contato_title": "FALE COM A CASA DAS CANTONEIRAS!",
    "contato_subtitle": "Nossa equipe está pronta para orientar sua consulta, tirar dúvidas e indicar o melhor catálogo.",
    "contato_button_label": "Fale Conosco",
    "contato_cta_title": "ATENDIMENTO RÁPIDO POR WHATSAPP E TELEFONE",
    "contato_cta_button_label": "Iniciar conversa",
    "footer_brand_title": "Casa das Cantoneiras",
    "footer_description": "Catálogo de produtos com atendimento direto e rápido para sua obra.",
    "footer_privacy_label": "Política de Privacidade",
    "footer_copyright": "Todos os direitos reservados © 2026",
    "store_address": STORE_ADDRESS or "",
    "store_email": "contato@cantoneirafacil.com",
    "store_cnpj": STORE_CNPJ or "",
    "map_title": "LOCALIZAÇÃO",
    "map_address": STORE_ADDRESS or "",
    "map_embed_url": DEFAULT_MAP_EMBED_URL,
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_catalogo_inicial() -> None:
    db = SessionLocal()
    try:
        if crud.list_categorias(db):
            return

        for idx, categoria in enumerate(DEFAULT_CATEGORIAS_HOME, start=1):
            crud.create_categoria(
                db,
                schemas.CategoriaCreate(
                    slug=categoria["slug"],
                    nome=categoria["nome"],
                    nome_exibicao=categoria["nome_exibicao"],
                    subtitulo_exibicao=categoria.get("subtitulo_exibicao", ""),
                    imagem_url=categoria.get("imagem_url", ""),
                    ordem_exibicao=idx,
                ),
            )

        for categoria_slug, subcategorias in DEFAULT_SUBCATEGORIAS_POR_CATEGORIA.items():
            for idx, subcategoria in enumerate(subcategorias, start=1):
                crud.create_subcategoria(
                    db,
                    schemas.SubcategoriaCreate(
                        categoria_slug=categoria_slug,
                        slug=subcategoria["slug"],
                        nome=subcategoria["nome"],
                        nome_exibicao=subcategoria["nome_exibicao"],
                        imagem_url=subcategoria.get("imagem_url", ""),
                        ordem_exibicao=idx,
                    ),
                )
    finally:
        db.close()


def _seed_quem_somos_inicial() -> None:
    db = SessionLocal()
    try:
        if crud.list_quem_somos_imagens(db):
            return

        for idx, imagem in enumerate(DEFAULT_QUEM_SOMOS_IMAGENS, start=1):
            crud.create_quem_somos_imagem(
                db,
                schemas.QuemSomosImagemCreate(
                    alt_texto=imagem.get("alt_texto"),
                    imagem_url=imagem.get("imagem_url"),
                    ordem_exibicao=idx,
                ),
            )
    finally:
        db.close()


def _seed_site_imagens_inicial() -> None:
    db = SessionLocal()
    try:
        for chave, imagem in SITE_IMAGE_DEFAULTS.items():
            crud.ensure_site_imagem(
                db,
                chave=chave,
                alt_texto=imagem["alt_texto"],
                imagem_url=imagem["imagem_url"],
            )
    finally:
        db.close()


def _seed_site_config_inicial() -> None:
    db = SessionLocal()
    try:
        crud.ensure_site_config_defaults(db, DEFAULT_SITE_CONFIG)
    finally:
        db.close()


@app.on_event("startup")
def _startup() -> None:
    _seed_catalogo_inicial()
    _seed_quem_somos_inicial()
    _seed_site_imagens_inicial()
    _seed_site_config_inicial()


def _slugify(value: Optional[str]) -> str:
    texto = (value or "").strip()
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", texto)
    ascii_texto = normalizado.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_texto).strip("-").lower()


def _texto_obrigatorio(value: Optional[str], mensagem: str) -> str:
    texto = (value or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail=mensagem)
    return texto


def _ordem_normalizada(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return max(int(value), 0)


def _schema_dump(schema_obj: object) -> dict[str, object]:
    if hasattr(schema_obj, "model_dump"):
        return schema_obj.model_dump()  # type: ignore[no-any-return]
    if hasattr(schema_obj, "dict"):
        return schema_obj.dict()  # type: ignore[no-any-return]
    raise TypeError("Objeto de schema invalido para serializacao")


def _categoria_image_url(categoria: models.Categoria) -> str:
    if getattr(categoria, "imagem_bytes", None):
        return f"/media/categoria/{categoria.id}/imagem"

    return (getattr(categoria, "imagem_url", None) or "").strip() or crud.PLACEHOLDER_IMAGE_URL


def _subcategoria_image_url(subcategoria: models.Subcategoria) -> str:
    if getattr(subcategoria, "imagem_bytes", None):
        return f"/media/subcategoria/{subcategoria.id}/imagem"

    return (getattr(subcategoria, "imagem_url", None) or "").strip() or crud.PLACEHOLDER_IMAGE_URL


def _quem_somos_image_url(imagem: models.QuemSomosImagem) -> str:
    if getattr(imagem, "imagem_bytes", None):
        return f"/media/quem-somos/{imagem.id}/imagem"

    return (getattr(imagem, "imagem_url", None) or "").strip() or crud.PLACEHOLDER_IMAGE_URL


def _site_image_url(imagem: models.SiteImagem) -> str:
    if getattr(imagem, "imagem_bytes", None):
        versao = (getattr(imagem, "imagem_sha256", None) or "").strip()[:12]
        cache_buster = f"?v={versao}" if versao else ""
        return f"/media/site-imagem/{imagem.chave}/imagem{cache_buster}"

    return (getattr(imagem, "imagem_url", None) or "").strip() or crud.PLACEHOLDER_IMAGE_URL


def _categoria_view(categoria: models.Categoria) -> dict[str, Optional[str]]:
    return {
        "id": categoria.id,
        "slug": categoria.slug,
        "nome": categoria.nome,
        "nome_exibicao": categoria.nome_exibicao,
        "subtitulo_exibicao": categoria.subtitulo_exibicao or "",
        "imagem_url": _categoria_image_url(categoria),
        "ordem_exibicao": categoria.ordem_exibicao,
    }


def _subcategoria_view(subcategoria: models.Subcategoria) -> dict[str, Optional[str]]:
    return {
        "id": subcategoria.id,
        "categoria_slug": subcategoria.categoria_slug,
        "slug": subcategoria.slug,
        "nome": subcategoria.nome,
        "nome_exibicao": subcategoria.nome_exibicao,
        "imagem_url": _subcategoria_image_url(subcategoria),
        "ordem_exibicao": subcategoria.ordem_exibicao,
    }


def _quem_somos_image_view(imagem: models.QuemSomosImagem) -> dict[str, Optional[str]]:
    return {
        "id": imagem.id,
        "alt_texto": (imagem.alt_texto or "").strip() or "Casa das Cantoneiras",
        "imagem_url": _quem_somos_image_url(imagem),
        "ordem_exibicao": imagem.ordem_exibicao,
    }


def _site_image_view(imagem: models.SiteImagem) -> dict[str, Optional[str]]:
    default_alt = SITE_IMAGE_DEFAULTS.get(imagem.chave, {}).get("alt_texto", HOME_BANNER_DEFAULT_ALT)
    return {
        "id": imagem.id,
        "chave": imagem.chave,
        "alt_texto": (imagem.alt_texto or "").strip() or default_alt,
        "imagem_url": _site_image_url(imagem),
    }


def _site_image_view_by_key(db: Session, chave: str) -> dict[str, Optional[str]]:
    default = SITE_IMAGE_DEFAULTS[chave]
    imagem = crud.ensure_site_imagem(
        db,
        chave=chave,
        alt_texto=default["alt_texto"],
        imagem_url=default["imagem_url"],
    )
    view = _site_image_view(imagem)
    view["label"] = default["label"]
    view["help"] = default["help"]
    return view


def _home_banner_image_view(db: Session) -> dict[str, Optional[str]]:
    return _site_image_view_by_key(db, HOME_BANNER_IMAGE_KEY)


def _site_settings(db: Session) -> dict[str, str]:
    settings = DEFAULT_SITE_CONFIG.copy()
    settings.update(crud.ensure_site_config_defaults(db, DEFAULT_SITE_CONFIG))
    return settings


def _site_context(db: Session) -> dict[str, object]:
    settings = _site_settings(db)
    whatsapp_numero = settings.get("whatsapp_numero", "")
    whatsapp_link = _whatsapp_link_numero(whatsapp_numero)
    map_address = settings.get("map_address", "")
    map_embed_url = settings.get("map_embed_url", "").strip()
    if not map_embed_url and map_address:
        map_embed_url = f"https://www.google.com/maps?q={quote_plus(map_address)}&z=17&output=embed"

    logo = _site_image_view_by_key(db, SITE_LOGO_IMAGE_KEY)
    return {
        "SITE_CONFIG": settings,
        "WHATSAPP_NUMERO": _numero_whatsapp_limpo(whatsapp_numero),
        "WHATSAPP_DISPLAY": _telefone_visivel_numero(whatsapp_numero),
        "WHATSAPP_LINK": whatsapp_link,
        "INSTAGRAM_URL": settings.get("instagram_url", ""),
        "FACEBOOK_URL": settings.get("facebook_url", ""),
        "STORE_ADDRESS": settings.get("store_address", ""),
        "STORE_EMAIL": settings.get("store_email", ""),
        "STORE_CNPJ": settings.get("store_cnpj", ""),
        "LOGO_URL": logo["imagem_url"],
        "LOGO_ALT": logo["alt_texto"],
        "MAP_EMBED_URL": map_embed_url,
    }


def _whatsapp_link_for_settings(settings: dict[str, str], texto: str) -> str:
    return _whatsapp_link_numero(settings.get("whatsapp_numero", ""), texto)


def _whatsapp_link_items(numero: Optional[str], itens: list[dict[str, object]]) -> str:
    if not itens:
        return _whatsapp_link_numero(numero)

    texto = "Ola! Tenho interesse nos seguintes itens da Casa das Cantoneiras:\n\n"
    total = 0.0
    for item in itens:
        qtd = int(item.get("quantidade") or 0)
        nome = str(item.get("nome") or "")
        valor_un = float(item.get("valor_unitario") or 0)
        subtotal = qtd * valor_un
        total += subtotal
        texto += f"- {qtd}x {nome} - R$ {valor_un:.2f}/un -> R$ {subtotal:.2f}\n"

    texto += f"\nTotal estimado: R$ {total:.2f}\n\nPode me passar orcamento com frete e prazo de entrega?"
    return _whatsapp_link_numero(numero, texto)



def _catalogo_index(db: Session) -> dict[str, object]:
    categorias = [_categoria_view(categoria) for categoria in crud.list_categorias(db)]
    subcategorias = [_subcategoria_view(subcategoria) for subcategoria in crud.list_subcategorias(db)]

    categorias_por_slug = {categoria["slug"]: categoria for categoria in categorias}
    subcategorias_por_categoria: dict[str, list[dict[str, Optional[str]]]] = {}
    subcategorias_por_chave: dict[tuple[str, str], dict[str, Optional[str]]] = {}

    for subcategoria in subcategorias:
        categoria_slug = str(subcategoria["categoria_slug"])
        subcategorias_por_categoria.setdefault(categoria_slug, []).append(subcategoria)
        subcategorias_por_chave[(categoria_slug, str(subcategoria["slug"]))] = subcategoria

    return {
        "categorias": categorias,
        "categorias_por_slug": categorias_por_slug,
        "subcategorias": subcategorias,
        "subcategorias_por_categoria": subcategorias_por_categoria,
        "subcategorias_por_chave": subcategorias_por_chave,
    }


def _produto_image_url(produto: models.Produto) -> str:
    url_real = _produto_real_image_url(produto)
    if url_real:
        return url_real

    return crud.PLACEHOLDER_IMAGE_URL


def _produto_real_image_url(produto: models.Produto) -> Optional[str]:
    if getattr(produto, "imagem_bytes", None):
        return f"/media/produto/{produto.id}/imagem"

    url_externa = (getattr(produto, "imagem_url", None) or "").strip()
    if url_externa and url_externa != crud.PLACEHOLDER_IMAGE_URL:
        return url_externa

    return None


def _produto_medidas_image_url(produto: models.Produto) -> Optional[str]:
    if getattr(produto, "imagem_medidas_bytes", None):
        return f"/media/produto/{produto.id}/imagem-medidas"
    return None


def _produto_extra_image_url(produto: models.Produto) -> Optional[str]:
    if getattr(produto, "imagem_extra_bytes", None):
        return f"/media/produto/{produto.id}/imagem-extra"
    return None


def _produto_image_urls(produto: models.Produto) -> list[str]:
    imagens = [
        url
        for url in (
            _produto_real_image_url(produto),
            _produto_medidas_image_url(produto),
            _produto_extra_image_url(produto),
        )
        if url
    ]
    return imagens or [crud.PLACEHOLDER_IMAGE_URL]


def _produto_view(
    produto: models.Produto,
    *,
    categorias_por_slug: dict[str, dict[str, Optional[str]]],
    subcategorias_por_chave: dict[tuple[str, str], dict[str, Optional[str]]],
) -> dict[str, Optional[str]]:
    categoria_slug = (getattr(produto, "categoria_slug", None) or "").strip()
    subcategoria_slug = (getattr(produto, "subcategoria_slug", None) or "").strip()
    categoria = categorias_por_slug.get(categoria_slug)
    subcategoria = subcategorias_por_chave.get((categoria_slug, subcategoria_slug))

    return {
        "id": produto.id,
        "nome": produto.nome,
        "resumo_curto": produto.resumo_curto,
        "imagem_url": _produto_image_url(produto),
        "tem_imagem": _produto_real_image_url(produto) is not None,
        "imagem_medidas_url": _produto_medidas_image_url(produto),
        "imagem_extra_url": _produto_extra_image_url(produto),
        "imagens": _produto_image_urls(produto),
        "categoria_slug": categoria_slug or None,
        "categoria_nome_exibicao": categoria["nome_exibicao"] if categoria else None,
        "categoria_url": f"/categorias/{categoria['slug']}" if categoria else None,
        "subcategoria_slug": subcategoria_slug or None,
        "subcategoria_nome_exibicao": subcategoria["nome_exibicao"] if subcategoria else None,
        "subcategoria_url": (
            f"/categorias/{categoria['slug']}/subcategorias/{subcategoria['slug']}"
            if categoria and subcategoria
            else None
        ),
        "ordem_exibicao": produto.ordem_exibicao,
    }


def _convert_to_webp(raw: bytes) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        img.thumbnail((1600, 1600))

        out = io.BytesIO()
        img.save(out, format="WEBP", quality=82, method=6)
        return out.getvalue(), "image/webp"
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie uma imagem valida em PNG, JPG ou WEBP.",
        )


def _load_uploaded_image(upload: Optional[UploadFile]) -> tuple[Optional[bytes], Optional[str]]:
    if not upload or not upload.filename:
        return None, None

    raw = upload.file.read()
    if not raw:
        return None, None
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Imagem muito grande. Envie um arquivo de ate {MAX_IMAGE_BYTES} bytes.",
        )

    return _convert_to_webp(raw)


def _admin_credentials() -> tuple[str, str]:
    return ADMIN_USER.strip(), ADMIN_PASSWORD.strip()


def _is_admin_authed(request: Request) -> bool:
    return request.session.get("admin_authed") is True


def _auth_admin(request: Request) -> str:
    if _is_admin_authed(request):
        return request.session.get("admin_user", "admin")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


async def _auth_admin_mutation(request: Request) -> str:
    admin_user = _auth_admin(request)
    await csrf_protect(request)
    return admin_user


def _get_categoria(db: Session, slug: str) -> dict[str, Optional[str]]:
    categoria = crud.get_categoria(db, slug=slug)
    if categoria:
        return _categoria_view(categoria)
    raise HTTPException(status_code=404, detail="Categoria nao encontrada")


def _get_subcategorias(db: Session, categoria_slug: str) -> list[dict[str, Optional[str]]]:
    return [_subcategoria_view(subcategoria) for subcategoria in crud.list_subcategorias(db, categoria_slug=categoria_slug)]


def _categoria_exige_subcategoria(db: Session, categoria_slug: Optional[str]) -> bool:
    slug = (categoria_slug or "").strip()
    if not slug:
        return False
    return bool(crud.list_subcategorias(db, categoria_slug=slug))


def _get_subcategoria(db: Session, categoria_slug: str, subcategoria_slug: str) -> dict[str, Optional[str]]:
    subcategoria = crud.get_subcategoria(db, categoria_slug=categoria_slug, slug=subcategoria_slug)
    if subcategoria:
        return _subcategoria_view(subcategoria)
    raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")


def _normalizar_categoria_slug(db: Session, categoria_slug: Optional[str], *, required: bool) -> Optional[str]:
    slug = (categoria_slug or "").strip()
    if not slug:
        if required:
            raise HTTPException(status_code=400, detail="Selecione uma categoria")
        return None
    if not crud.get_categoria(db, slug=slug):
        raise HTTPException(status_code=400, detail="Categoria invalida")
    return slug


def _normalizar_subcategoria_slug(
    db: Session,
    categoria_slug: Optional[str],
    subcategoria_slug: Optional[str],
    *,
    required: bool,
) -> Optional[str]:
    categoria = (categoria_slug or "").strip()
    subcategoria = (subcategoria_slug or "").strip()
    subcategorias_validas = crud.list_subcategorias(db, categoria_slug=categoria)

    if not subcategorias_validas:
        return None
    if not subcategoria:
        if required:
            raise HTTPException(
                status_code=400,
                detail="Produtos dessa categoria precisam estar vinculados a um subcatalogo",
            )
        return None
    if not crud.get_subcategoria(db, categoria_slug=categoria, slug=subcategoria):
        raise HTTPException(status_code=400, detail="Subcatalogo invalido")
    return subcategoria


def _categoria_create_from_form(
    slug: str,
    nome: str,
    nome_exibicao: str,
    subtitulo_exibicao: str,
    imagem_url: Optional[str],
    ordem_exibicao: Optional[int],
) -> schemas.CategoriaCreate:
    nome_normalizado = _texto_obrigatorio(nome, "Informe o nome interno da categoria")
    nome_exibicao_normalizado = _texto_obrigatorio(nome_exibicao, "Informe o nome de exibicao da categoria")
    slug_normalizado = _slugify(slug) or _slugify(nome_exibicao_normalizado) or _slugify(nome_normalizado)
    if not slug_normalizado:
        raise HTTPException(status_code=400, detail="Informe um slug valido para a categoria")

    return schemas.CategoriaCreate(
        slug=slug_normalizado,
        nome=nome_normalizado,
        nome_exibicao=nome_exibicao_normalizado,
        subtitulo_exibicao=(subtitulo_exibicao or "").strip() or None,
        imagem_url=(imagem_url or "").strip() or None,
        ordem_exibicao=_ordem_normalizada(ordem_exibicao),
    )


def _quem_somos_imagem_from_form(
    alt_texto: Optional[str],
    ordem_exibicao: Optional[int],
    imagem_url: Optional[str] = None,
) -> schemas.QuemSomosImagemCreate:
    return schemas.QuemSomosImagemCreate(
        alt_texto=(alt_texto or "").strip() or None,
        imagem_url=(imagem_url or "").strip() or None,
        ordem_exibicao=_ordem_normalizada(ordem_exibicao),
    )


def _subcategoria_create_from_form(
    db: Session,
    categoria_slug: str,
    slug: str,
    nome: str,
    nome_exibicao: str,
    imagem_url: Optional[str],
    ordem_exibicao: Optional[int],
) -> schemas.SubcategoriaCreate:
    categoria_normalizada = _normalizar_categoria_slug(db, categoria_slug, required=True)
    nome_normalizado = _texto_obrigatorio(nome, "Informe o nome interno do subcatalogo")
    nome_exibicao_normalizado = _texto_obrigatorio(nome_exibicao, "Informe o nome de exibicao do subcatalogo")
    slug_normalizado = _slugify(slug) or _slugify(nome_exibicao_normalizado) or _slugify(nome_normalizado)
    if not slug_normalizado:
        raise HTTPException(status_code=400, detail="Informe um slug valido para o subcatalogo")

    return schemas.SubcategoriaCreate(
        categoria_slug=categoria_normalizada,
        slug=slug_normalizado,
        nome=nome_normalizado,
        nome_exibicao=nome_exibicao_normalizado,
        imagem_url=(imagem_url or "").strip() or None,
        ordem_exibicao=_ordem_normalizada(ordem_exibicao),
    )


def _create_produto_from_form(
    db: Session,
    nome: str,
    resumo_curto: str,
    categoria_slug: str,
    subcategoria_slug: Optional[str],
    ordem_exibicao: Optional[int],
) -> schemas.ProdutoCreate:
    categoria_normalizada = _normalizar_categoria_slug(db, categoria_slug, required=True)
    return schemas.ProdutoCreate(
        nome=_texto_obrigatorio(nome, "Informe o nome do produto"),
        resumo_curto=resumo_curto,
        categoria_slug=categoria_normalizada,
        subcategoria_slug=_normalizar_subcategoria_slug(
            db,
            categoria_normalizada,
            subcategoria_slug,
            required=_categoria_exige_subcategoria(db, categoria_normalizada),
        ),
        ordem_exibicao=_ordem_normalizada(ordem_exibicao),
    )


def _update_produto_from_form(
    db: Session,
    nome: Optional[str],
    resumo_curto: Optional[str],
    categoria_slug: Optional[str],
    subcategoria_slug: Optional[str],
    ordem_exibicao: Optional[int],
) -> schemas.ProdutoUpdate:
    categoria_normalizada = _normalizar_categoria_slug(db, categoria_slug, required=True)
    return schemas.ProdutoUpdate(
        nome=_texto_obrigatorio(nome, "Informe o nome do produto"),
        resumo_curto=resumo_curto,
        categoria_slug=categoria_normalizada,
        subcategoria_slug=_normalizar_subcategoria_slug(
            db,
            categoria_normalizada,
            subcategoria_slug,
            required=_categoria_exige_subcategoria(db, categoria_normalizada),
        ),
        ordem_exibicao=_ordem_normalizada(ordem_exibicao),
    )


def _catalogo_admin_context(db: Session) -> dict[str, object]:
    catalogo = _catalogo_index(db)
    produtos = [
        _produto_view(
            produto,
            categorias_por_slug=catalogo["categorias_por_slug"],
            subcategorias_por_chave=catalogo["subcategorias_por_chave"],
        )
        for produto in crud.get_produtos(db)
    ]
    return {
        "categorias": catalogo["categorias"],
        "subcategorias": catalogo["subcategorias"],
        "subcategorias_por_categoria": catalogo["subcategorias_por_categoria"],
        "quem_somos_imagens": [
            _quem_somos_image_view(imagem) for imagem in crud.list_quem_somos_imagens(db)
        ],
        "home_banner_image": _home_banner_image_view(db),
        "produtos": produtos,
    }


def _frontend_admin_context(db: Session) -> dict[str, object]:
    return {
        "site_config": _site_settings(db),
        "site_images": {
            chave: _site_image_view_by_key(db, chave)
            for chave in SITE_IMAGE_DEFAULTS
        },
        "site_image_fields": [
            {
                "chave": chave,
                "label": dados["label"],
                "help": dados["help"],
            }
            for chave, dados in SITE_IMAGE_DEFAULTS.items()
        ],
    }


def _admin_context(db: Session, *, admin_page: str) -> dict[str, object]:
    contexto = _catalogo_admin_context(db)
    contexto.update(_frontend_admin_context(db))
    contexto["admin_page"] = admin_page
    return contexto


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    site_context = _site_context(db)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            **site_context,
            "categorias_home": catalogo["categorias"],
            "home_banner_image": _home_banner_image_view(db),
            "home_hero_image": _site_image_view_by_key(db, HOME_HERO_IMAGE_KEY),
            "whatsapp_numero": site_context["WHATSAPP_DISPLAY"],
        },
    )


@app.get("/quem-somos", response_class=HTMLResponse)
def quem_somos(request: Request, db: Session = Depends(get_db)):
    site_context = _site_context(db)
    return templates.TemplateResponse(
        "quem_somos.html",
        {
            "request": request,
            **site_context,
            "galeria_quem_somos": [
                _quem_somos_image_view(imagem) for imagem in crud.list_quem_somos_imagens(db)
            ],
            "whatsapp_numero": site_context["WHATSAPP_DISPLAY"],
        },
    )


@app.get("/categorias/{slug}", response_class=HTMLResponse)
def categoria_detalhe(slug: str, request: Request, db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    categoria = catalogo["categorias_por_slug"].get(slug)
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")

    subcategorias = catalogo["subcategorias_por_categoria"].get(slug, [])
    produtos_db = [] if subcategorias else crud.get_produtos(db, categoria_slug=slug)
    site_context = _site_context(db)
    whatsapp_link = _whatsapp_link_for_settings(
        site_context["SITE_CONFIG"],
        f"Ola! Tenho interesse na categoria {categoria['nome']}.",
    )

    return templates.TemplateResponse(
        "categoria.html",
        {
            "request": request,
            **site_context,
            "categoria": categoria,
            "produtos": [
                _produto_view(
                    produto,
                    categorias_por_slug=catalogo["categorias_por_slug"],
                    subcategorias_por_chave=catalogo["subcategorias_por_chave"],
                )
                for produto in produtos_db
            ],
            "subcategorias": subcategorias,
            "subcategoria_atual": None,
            "whatsapp_numero": site_context["WHATSAPP_DISPLAY"],
            "whatsapp_link": whatsapp_link,
        },
    )


@app.get("/categorias/{slug}/subcategorias/{subcategoria_slug}", response_class=HTMLResponse)
def subcategoria_detalhe(
    slug: str,
    subcategoria_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    catalogo = _catalogo_index(db)
    categoria = catalogo["categorias_por_slug"].get(slug)
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")

    subcategoria = catalogo["subcategorias_por_chave"].get((slug, subcategoria_slug))
    if not subcategoria:
        raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")

    produtos_db = crud.get_produtos(db, categoria_slug=slug, subcategoria_slug=subcategoria_slug)
    site_context = _site_context(db)
    whatsapp_link = _whatsapp_link_for_settings(
        site_context["SITE_CONFIG"],
        f"Ola! Tenho interesse em {subcategoria['nome']} da categoria {categoria['nome']}.",
    )

    return templates.TemplateResponse(
        "categoria.html",
        {
            "request": request,
            **site_context,
            "categoria": categoria,
            "produtos": [
                _produto_view(
                    produto,
                    categorias_por_slug=catalogo["categorias_por_slug"],
                    subcategorias_por_chave=catalogo["subcategorias_por_chave"],
                )
                for produto in produtos_db
            ],
            "subcategorias": catalogo["subcategorias_por_categoria"].get(slug, []),
            "subcategoria_atual": subcategoria,
            "whatsapp_numero": site_context["WHATSAPP_DISPLAY"],
            "whatsapp_link": whatsapp_link,
        },
    )


@app.get("/produtos", response_class=HTMLResponse)
def produtos(request: Request, db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    site_context = _site_context(db)
    return templates.TemplateResponse(
        "produtos.html",
        {
            "request": request,
            **site_context,
            "categorias_home": catalogo["categorias"],
            "whatsapp_numero": site_context["WHATSAPP_DISPLAY"],
        },
    )


@app.get("/contato", response_class=HTMLResponse)
def contato(request: Request, db: Session = Depends(get_db)):
    site_context = _site_context(db)
    return templates.TemplateResponse(
        "contato.html",
        {
            "request": request,
            **site_context,
            "whatsapp_numero": site_context["WHATSAPP_DISPLAY"],
        },
    )


@app.get("/produto/{produto_id}", response_class=HTMLResponse)
def produto_detalhe(produto_id: int, request: Request, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")

    catalogo = _catalogo_index(db)
    site_context = _site_context(db)
    whatsapp_link = _whatsapp_link_for_settings(
        site_context["SITE_CONFIG"],
        f"Ola! Tenho interesse no produto {produto.nome}.",
    )
    return templates.TemplateResponse(
        "produto.html",
        {
            "request": request,
            **site_context,
            "produto": _produto_view(
                produto,
                categorias_por_slug=catalogo["categorias_por_slug"],
                subcategorias_por_chave=catalogo["subcategorias_por_chave"],
            ),
            "whatsapp_numero": site_context["WHATSAPP_DISPLAY"],
            "whatsapp_link": whatsapp_link,
        },
    )


@app.get("/media/produto/{produto_id}/imagem")
def media_produto_imagem(produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not getattr(produto, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(produto, "imagem_mime", None) or "application/octet-stream"
    return Response(content=produto.imagem_bytes, media_type=mime)


@app.get("/media/categoria/{categoria_id}/imagem")
def media_categoria_imagem(categoria_id: int, db: Session = Depends(get_db)):
    categoria = crud.get_categoria(db, categoria_id=categoria_id)
    if not categoria or not getattr(categoria, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(categoria, "imagem_mime", None) or "application/octet-stream"
    return Response(content=categoria.imagem_bytes, media_type=mime)


@app.get("/media/subcategoria/{subcategoria_id}/imagem")
def media_subcategoria_imagem(subcategoria_id: int, db: Session = Depends(get_db)):
    subcategoria = crud.get_subcategoria(db, subcategoria_id=subcategoria_id)
    if not subcategoria or not getattr(subcategoria, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(subcategoria, "imagem_mime", None) or "application/octet-stream"
    return Response(content=subcategoria.imagem_bytes, media_type=mime)


@app.get("/media/quem-somos/{imagem_id}/imagem")
def media_quem_somos_imagem(imagem_id: int, db: Session = Depends(get_db)):
    imagem = crud.get_quem_somos_imagem(db, imagem_id=imagem_id)
    if not imagem or not getattr(imagem, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(imagem, "imagem_mime", None) or "application/octet-stream"
    return Response(content=imagem.imagem_bytes, media_type=mime)


@app.get("/media/site-imagem/{chave}/imagem")
def media_site_imagem(chave: str, db: Session = Depends(get_db)):
    imagem = crud.get_site_imagem(db, chave=chave)
    if not imagem or not getattr(imagem, "imagem_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem nao encontrada")

    mime = getattr(imagem, "imagem_mime", None) or "application/octet-stream"
    return Response(content=imagem.imagem_bytes, media_type=mime)


@app.get("/media/produto/{produto_id}/imagem-medidas")
def media_produto_imagem_medidas(produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not getattr(produto, "imagem_medidas_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem de medidas nao encontrada")

    mime = getattr(produto, "imagem_medidas_mime", None) or "application/octet-stream"
    return Response(content=produto.imagem_medidas_bytes, media_type=mime)


@app.get("/media/produto/{produto_id}/imagem-extra")
def media_produto_imagem_extra(produto_id: int, db: Session = Depends(get_db)):
    produto = crud.get_produto(db, produto_id=produto_id)
    if not produto or not getattr(produto, "imagem_extra_bytes", None):
        raise HTTPException(status_code=404, detail="Imagem extra nao encontrada")

    mime = getattr(produto, "imagem_extra_mime", None) or "application/octet-stream"
    return Response(content=produto.imagem_extra_bytes, media_type=mime)


@app.get("/api/produtos")
def api_produtos(db: Session = Depends(get_db)):
    catalogo = _catalogo_index(db)
    produtos_db = crud.list_produtos(db, apenas_ativos=True)
    return [
        _produto_view(
            produto,
            categorias_por_slug=catalogo["categorias_por_slug"],
            subcategorias_por_chave=catalogo["subcategorias_por_chave"],
        )
        for produto in produtos_db
    ]


@app.post("/api/whatsapp")
def api_whatsapp(itens: List[schemas.ItemCarrinho], db: Session = Depends(get_db)):
    itens_dict = [i.model_dump() if hasattr(i, "model_dump") else i.dict() for i in itens]
    settings = _site_settings(db)
    return {"url": _whatsapp_link_items(settings.get("whatsapp_numero", ""), itens_dict)}


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request):
    if _is_admin_authed(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        "admin/login.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
        },
    )


@app.post("/admin/login")
def admin_login_post(
    request: Request,
    _: None = Depends(csrf_protect),
    username: str = Form(...),
    password: str = Form(...),
):
    ip_address = client_ip(request, trust_proxy_headers=TRUST_PROXY_HEADERS)
    retry_after = login_rate_limiter.retry_after(ip_address)
    if retry_after:
        logger.warning("Tentativa de login admin bloqueada para o IP %s.", ip_address)
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "csrf_token": get_csrf_token(request),
                "error": "Nao foi possivel realizar o login. Tente novamente mais tarde.",
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
        )

    admin_user, admin_pass = _admin_credentials()
    valid_user = secrets.compare_digest(username, admin_user)
    valid_password = secrets.compare_digest(password, admin_pass)
    if not admin_pass or not valid_user or not valid_password:
        login_rate_limiter.record_failure(ip_address)
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "csrf_token": get_csrf_token(request),
                "error": "Usuario ou senha invalidos",
            },
            status_code=200,
        )

    login_rate_limiter.reset(ip_address)
    rotate_session(request, admin_user=admin_user)
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin_authed(request):
        return RedirectResponse("/admin/login", status_code=303)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
            **_admin_context(db, admin_page="dashboard"),
        },
    )


@app.get("/admin/catalogo", response_class=HTMLResponse)
def admin_catalogo(
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin_authed(request):
        return RedirectResponse("/admin/login", status_code=303)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
            **_admin_context(db, admin_page="catalogo"),
        },
    )


@app.get("/admin/frontend", response_class=HTMLResponse)
def admin_frontend(
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin_authed(request):
        return RedirectResponse("/admin/login", status_code=303)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "csrf_token": get_csrf_token(request),
            **_admin_context(db, admin_page="frontend"),
        },
    )


@app.post("/admin/logout")
async def admin_logout(
    request: Request,
    _: str = Depends(_auth_admin_mutation),
):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@app.post("/admin/frontend/config")
async def admin_frontend_config_atualizar(
    request: Request,
    _: str = Depends(_auth_admin_mutation),
    db: Session = Depends(get_db),
):
    form = await request.form()
    dados = {
        chave: str(form.get(chave, "")).strip()
        for chave in DEFAULT_SITE_CONFIG
    }
    crud.upsert_site_configs(db, dados)
    return RedirectResponse("/admin/frontend", status_code=303)


@app.post("/admin/site-imagem/{chave}")
def admin_site_imagem_atualizar(
    chave: str,
    _: str = Depends(_auth_admin_mutation),
    alt_texto: str = Form(""),
    imagem: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    if chave not in SITE_IMAGE_DEFAULTS:
        raise HTTPException(status_code=404, detail="Imagem do site nao encontrada")

    default = SITE_IMAGE_DEFAULTS[chave]
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    crud.upsert_site_imagem(
        db,
        chave=chave,
        dados=schemas.SiteImagemUpdate(alt_texto=(alt_texto or "").strip() or None),
        default_alt_texto=default["alt_texto"],
        default_imagem_url=default["imagem_url"],
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
    )
    return RedirectResponse("/admin/frontend", status_code=303)


@app.post("/admin/categoria")
def admin_categoria_novo(
    _: str = Depends(_auth_admin_mutation),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    subtitulo_exibicao: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    dados = _categoria_create_from_form(
        slug,
        nome,
        nome_exibicao,
        subtitulo_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        crud.create_categoria(db, dados, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin/catalogo", status_code=303)


@app.put("/admin/categoria/{categoria_id}")
def admin_categoria_atualizar(
    categoria_id: int,
    _: str = Depends(_auth_admin_mutation),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    subtitulo_exibicao: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    create_data = _categoria_create_from_form(
        slug,
        nome,
        nome_exibicao,
        subtitulo_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        categoria = crud.update_categoria(
            db,
            categoria_id=categoria_id,
            dados=schemas.CategoriaUpdate(**_schema_dump(create_data)),
            imagem_bytes=imagem_bytes,
            imagem_mime=imagem_mime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    return RedirectResponse("/admin/catalogo", status_code=303)


@app.post("/admin/categoria/{categoria_id}")
def admin_categoria_method_override(
    categoria_id: int,
    _: str = Depends(_auth_admin_mutation),
    _method: Optional[str] = Form(None),
    slug: str = Form(""),
    nome: str = Form(None),
    nome_exibicao: str = Form(None),
    subtitulo_exibicao: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_categoria_atualizar(
            categoria_id=categoria_id,
            _=_,
            slug=slug,
            nome=nome,
            nome_exibicao=nome_exibicao,
            subtitulo_exibicao=subtitulo_exibicao,
            imagem=imagem,
            ordem_exibicao=ordem_exibicao,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/categoria/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/categoria/{categoria_id}")
def admin_categoria_excluir(
    categoria_id: int,
    _: str = Depends(_auth_admin_mutation),
    db: Session = Depends(get_db),
):
    if not crud.delete_categoria(db, categoria_id=categoria_id):
        raise HTTPException(status_code=404, detail="Categoria nao encontrada")
    return Response(status_code=204)


@app.post("/admin/subcategoria")
def admin_subcategoria_novo(
    _: str = Depends(_auth_admin_mutation),
    categoria_slug: str = Form(...),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    dados = _subcategoria_create_from_form(
        db,
        categoria_slug,
        slug,
        nome,
        nome_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        crud.create_subcategoria(db, dados, imagem_bytes=imagem_bytes, imagem_mime=imagem_mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/admin/catalogo", status_code=303)


@app.put("/admin/subcategoria/{subcategoria_id}")
def admin_subcategoria_atualizar(
    subcategoria_id: int,
    _: str = Depends(_auth_admin_mutation),
    categoria_slug: str = Form(...),
    slug: str = Form(""),
    nome: str = Form(...),
    nome_exibicao: str = Form(...),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    create_data = _subcategoria_create_from_form(
        db,
        categoria_slug,
        slug,
        nome,
        nome_exibicao,
        None,
        ordem_exibicao,
    )
    try:
        subcategoria = crud.update_subcategoria(
            db,
            subcategoria_id=subcategoria_id,
            dados=schemas.SubcategoriaUpdate(**_schema_dump(create_data)),
            imagem_bytes=imagem_bytes,
            imagem_mime=imagem_mime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not subcategoria:
        raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")
    return RedirectResponse("/admin/catalogo", status_code=303)


@app.post("/admin/subcategoria/{subcategoria_id}")
def admin_subcategoria_method_override(
    subcategoria_id: int,
    _: str = Depends(_auth_admin_mutation),
    _method: Optional[str] = Form(None),
    categoria_slug: str = Form(None),
    slug: str = Form(""),
    nome: str = Form(None),
    nome_exibicao: str = Form(None),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_subcategoria_atualizar(
            subcategoria_id=subcategoria_id,
            _=_,
            categoria_slug=categoria_slug,
            slug=slug,
            nome=nome,
            nome_exibicao=nome_exibicao,
            imagem=imagem,
            ordem_exibicao=ordem_exibicao,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/subcategoria/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/subcategoria/{subcategoria_id}")
def admin_subcategoria_excluir(
    subcategoria_id: int,
    _: str = Depends(_auth_admin_mutation),
    db: Session = Depends(get_db),
):
    if not crud.delete_subcategoria(db, subcategoria_id=subcategoria_id):
        raise HTTPException(status_code=404, detail="Subcatalogo nao encontrado")
    return Response(status_code=204)


@app.post("/admin/quem-somos/imagem")
def admin_quem_somos_imagem_nova(
    _: str = Depends(_auth_admin_mutation),
    alt_texto: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    if imagem_bytes is None:
        raise HTTPException(status_code=400, detail="Selecione uma imagem para a galeria")

    crud.create_quem_somos_imagem(
        db,
        _quem_somos_imagem_from_form(alt_texto, ordem_exibicao),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
    )
    return RedirectResponse("/admin/frontend", status_code=303)


@app.put("/admin/quem-somos/imagem/{imagem_id}")
def admin_quem_somos_imagem_atualizar(
    imagem_id: int,
    _: str = Depends(_auth_admin_mutation),
    alt_texto: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    imagem_atualizada = crud.update_quem_somos_imagem(
        db,
        imagem_id=imagem_id,
        dados=schemas.QuemSomosImagemUpdate(
            **_schema_dump(_quem_somos_imagem_from_form(alt_texto, ordem_exibicao))
        ),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
    )
    if not imagem_atualizada:
        raise HTTPException(status_code=404, detail="Imagem da galeria nao encontrada")
    return RedirectResponse("/admin/frontend", status_code=303)


@app.post("/admin/quem-somos/imagem/{imagem_id}")
def admin_quem_somos_imagem_method_override(
    imagem_id: int,
    _: str = Depends(_auth_admin_mutation),
    _method: Optional[str] = Form(None),
    alt_texto: str = Form(""),
    imagem: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_quem_somos_imagem_atualizar(
            imagem_id=imagem_id,
            _=_,
            alt_texto=alt_texto,
            imagem=imagem,
            ordem_exibicao=ordem_exibicao,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/quem-somos/imagem/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/quem-somos/imagem/{imagem_id}")
def admin_quem_somos_imagem_excluir(
    imagem_id: int,
    _: str = Depends(_auth_admin_mutation),
    db: Session = Depends(get_db),
):
    if not crud.delete_quem_somos_imagem(db, imagem_id=imagem_id):
        raise HTTPException(status_code=404, detail="Imagem da galeria nao encontrada")
    return Response(status_code=204)


@app.post("/admin/produto")
def admin_produto_novo(
    _: str = Depends(_auth_admin_mutation),
    nome: str = Form(...),
    resumo_curto: str = Form(""),
    categoria_slug: str = Form(...),
    subcategoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    imagem_extra: UploadFile = File(None),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    imagem_medidas_bytes, imagem_medidas_mime = _load_uploaded_image(imagem_medidas)
    imagem_extra_bytes, imagem_extra_mime = _load_uploaded_image(imagem_extra)

    crud.create_produto(
        db,
        _create_produto_from_form(
            db,
            nome,
            resumo_curto,
            categoria_slug,
            subcategoria_slug,
            ordem_exibicao,
        ),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        imagem_medidas_bytes=imagem_medidas_bytes,
        imagem_medidas_mime=imagem_medidas_mime,
        imagem_extra_bytes=imagem_extra_bytes,
        imagem_extra_mime=imagem_extra_mime,
    )
    return RedirectResponse("/admin/catalogo", status_code=303)


@app.put("/admin/produto/{produto_id}")
def admin_produto_atualizar(
    produto_id: int,
    _: str = Depends(_auth_admin_mutation),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    categoria_slug: str = Form(None),
    subcategoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    imagem_extra: UploadFile = File(None),
    remover_imagem: bool = Form(False),
    remover_imagem_medidas: bool = Form(False),
    remover_imagem_extra: bool = Form(False),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    imagem_bytes, imagem_mime = _load_uploaded_image(imagem)
    imagem_medidas_bytes, imagem_medidas_mime = _load_uploaded_image(imagem_medidas)
    imagem_extra_bytes, imagem_extra_mime = _load_uploaded_image(imagem_extra)

    produto = crud.update_produto(
        db,
        produto_id=produto_id,
        dados=_update_produto_from_form(
            db,
            nome,
            resumo_curto,
            categoria_slug,
            subcategoria_slug,
            ordem_exibicao,
        ),
        imagem_bytes=imagem_bytes,
        imagem_mime=imagem_mime,
        imagem_medidas_bytes=imagem_medidas_bytes,
        imagem_medidas_mime=imagem_medidas_mime,
        imagem_extra_bytes=imagem_extra_bytes,
        imagem_extra_mime=imagem_extra_mime,
        remover_imagem=remover_imagem,
        remover_imagem_medidas=remover_imagem_medidas,
        remover_imagem_extra=remover_imagem_extra,
    )
    if not produto:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return RedirectResponse("/admin/catalogo", status_code=303)


@app.post("/admin/produto/{produto_id}")
def admin_produto_method_override(
    produto_id: int,
    _: str = Depends(_auth_admin_mutation),
    _method: Optional[str] = Form(None),
    nome: str = Form(None),
    resumo_curto: str = Form(None),
    categoria_slug: str = Form(None),
    subcategoria_slug: str = Form(None),
    imagem: UploadFile = File(None),
    imagem_medidas: UploadFile = File(None),
    imagem_extra: UploadFile = File(None),
    remover_imagem: bool = Form(False),
    remover_imagem_medidas: bool = Form(False),
    remover_imagem_extra: bool = Form(False),
    ordem_exibicao: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if (_method or "").strip().upper() == "PUT":
        return admin_produto_atualizar(
            produto_id=produto_id,
            _=_,
            nome=nome,
            resumo_curto=resumo_curto,
            categoria_slug=categoria_slug,
            subcategoria_slug=subcategoria_slug,
            imagem=imagem,
            imagem_medidas=imagem_medidas,
            imagem_extra=imagem_extra,
            remover_imagem=remover_imagem,
            remover_imagem_medidas=remover_imagem_medidas,
            remover_imagem_extra=remover_imagem_extra,
            ordem_exibicao=ordem_exibicao,
            db=db,
        )

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Metodo nao suportado para /admin/produto/{id}. Use _method=PUT ou DELETE.",
    )


@app.delete("/admin/produto/{produto_id}")
def admin_produto_excluir(
    produto_id: int,
    _: str = Depends(_auth_admin_mutation),
    db: Session = Depends(get_db),
):
    if not crud.delete_produto(db, produto_id=produto_id):
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return Response(status_code=204)
