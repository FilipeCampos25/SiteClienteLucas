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

# CORS
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if not CORS_ORIGINS:
    CORS_ORIGINS = ["*"]  # Padrão para desenvolvimento/teste local