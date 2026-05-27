import os
from dotenv import load_dotenv

load_dotenv()

# Banco de dados (AWS RDS PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")
IS_RENDER = os.getenv("RENDER") == "true"

# Admin
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "troque_essa_senha")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")



# WhatsApp
WHATSAPP_NUMERO = os.getenv("WHATSAPP_NUMERO")
INSTAGRAM_URL = os.getenv(
    "INSTAGRAM_URL",
    "https://www.instagram.com/casa_dascantoneiras?igsh=NWJvNnRsNXc2cTR4",
).strip()
FACEBOOK_URL = os.getenv("FACEBOOK_URL", "https://www.facebook.com/").strip()
STORE_ADDRESS = os.getenv(
    "STORE_ADDRESS",
    "Rua 08, Chacara 225, Loja 2/3, Vicente Pires, Brasilia - DF, CEP 72007-065",
).strip()
STORE_CNPJ = os.getenv("STORE_CNPJ", "55.291.020/0001-50").strip()
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "4000000"))

# CORS
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if not CORS_ORIGINS:
    CORS_ORIGINS = ["*"]  # Padrão para desenvolvimento/teste local
