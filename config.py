import os
from dotenv import load_dotenv

load_dotenv()

# Banco de dados (AWS RDS PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")

# Admin
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "troque_essa_senha")



# WhatsApp
WHATSAPP_NUMERO = os.getenv("WHATSAPP_NUMERO")
INSTAGRAM_URL = os.getenv(
    "INSTAGRAM_URL",
    "https://www.instagram.com/casa_dascantoneiras?igsh=NWJvNnRsNXc2cTR4",
).strip()
FACEBOOK_URL = os.getenv("FACEBOOK_URL", "https://www.facebook.com/").strip()
STORE_ADDRESS = os.getenv(
    "STORE_ADDRESS",
    "Casa Das Cantoneiras, St. Hab. Vicente Pires - Vicente Pires, Brasilia - DF, 72005-512",
).strip()
STORE_CNPJ = os.getenv("STORE_CNPJ", "").strip()

# CORS
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if not CORS_ORIGINS:
    CORS_ORIGINS = ["*"]  # Padrão para desenvolvimento/teste local
