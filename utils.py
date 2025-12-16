from urllib.parse import quote_plus
from config import WHATSAPP_NUMERO

def gerar_link_whatsapp(itens):
    if not itens:
        return f"https://wa.me/{WHATSAPP_NUMERO}"

    texto = "Olá! Tenho interesse nos seguintes itens da Cantoneira Fácil:\n\n"
    total = 0.0

    for item in itens:
        qtd = item["quantidade"]
        valor_un = float(item["valor_unitario"])
        subtotal = qtd * valor_un
        total += subtotal
        texto += f"• {qtd}x {item['nome']} - R$ {valor_un:.2f}/un → R$ {subtotal:.2f}\n"

    texto += f"\nTotal estimado: R$ {total:.2f}\n\nPode me passar orçamento com frete e prazo de entrega?\nObrigado!"

    return f"https://wa.me/{WHATSAPP_NUMERO}?text={quote_plus(texto)}"