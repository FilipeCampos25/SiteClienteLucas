from sqlalchemy import Column, DateTime, Integer, LargeBinary, String, Text, UniqueConstraint, func

from database import Base


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, index=True)

    slug = Column(String(120), nullable=False, unique=True, index=True)
    nome = Column(String(120), nullable=False)
    nome_exibicao = Column(String(120), nullable=False)
    subtitulo_exibicao = Column(String(120), nullable=True)
    imagem_url = Column(String, nullable=True)
    imagem_mime = Column(String(64), nullable=True)
    imagem_bytes = Column(LargeBinary, nullable=True)
    imagem_sha256 = Column(String(64), nullable=True)
    ordem_exibicao = Column(Integer, nullable=False, default=0, server_default="0")

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Subcategoria(Base):
    __tablename__ = "subcategorias"
    __table_args__ = (
        UniqueConstraint("categoria_slug", "slug", name="uq_subcategorias_categoria_slug_slug"),
    )

    id = Column(Integer, primary_key=True, index=True)

    categoria_slug = Column(String(120), nullable=False, index=True)
    slug = Column(String(120), nullable=False, index=True)
    nome = Column(String(120), nullable=False)
    nome_exibicao = Column(String(120), nullable=False)
    imagem_url = Column(String, nullable=True)
    imagem_mime = Column(String(64), nullable=True)
    imagem_bytes = Column(LargeBinary, nullable=True)
    imagem_sha256 = Column(String(64), nullable=True)
    ordem_exibicao = Column(Integer, nullable=False, default=0, server_default="0")

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)

    nome = Column(String(120), nullable=False)
    resumo_curto = Column(Text, nullable=True)
    categoria_slug = Column(String(80), nullable=True)
    subcategoria_slug = Column(String(80), nullable=True)

    imagem_url = Column(String, nullable=True)
    imagem_mime = Column(String(64), nullable=True)
    imagem_bytes = Column(LargeBinary, nullable=True)
    imagem_sha256 = Column(String(64), nullable=True)
    imagem_medidas_mime = Column(String(64), nullable=True)
    imagem_medidas_bytes = Column(LargeBinary, nullable=True)
    imagem_medidas_sha256 = Column(String(64), nullable=True)
    imagem_extra_mime = Column(String(64), nullable=True)
    imagem_extra_bytes = Column(LargeBinary, nullable=True)
    imagem_extra_sha256 = Column(String(64), nullable=True)
    ordem_exibicao = Column(Integer, nullable=False, default=0, server_default="0")

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class QuemSomosImagem(Base):
    __tablename__ = "quem_somos_imagens"

    id = Column(Integer, primary_key=True, index=True)

    alt_texto = Column(String(160), nullable=True)
    imagem_url = Column(String, nullable=True)
    imagem_mime = Column(String(64), nullable=True)
    imagem_bytes = Column(LargeBinary, nullable=True)
    imagem_sha256 = Column(String(64), nullable=True)
    ordem_exibicao = Column(Integer, nullable=False, default=0, server_default="0")

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SiteImagem(Base):
    __tablename__ = "site_imagens"

    id = Column(Integer, primary_key=True, index=True)

    chave = Column(String(80), nullable=False, unique=True, index=True)
    alt_texto = Column(String(160), nullable=True)
    imagem_url = Column(String, nullable=True)
    imagem_mime = Column(String(64), nullable=True)
    imagem_bytes = Column(LargeBinary, nullable=True)
    imagem_sha256 = Column(String(64), nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SiteConfig(Base):
    __tablename__ = "site_config"

    id = Column(Integer, primary_key=True, index=True)

    chave = Column(String(120), nullable=False, unique=True, index=True)
    valor = Column(Text, nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
