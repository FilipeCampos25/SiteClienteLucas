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


# ----- Helpers for templates -----

def telefone_visivel():
    """Formata WHATSAPP_NUMERO para exibição amigável.
    Ex.: 5561985700278 -> +55 (61) 98570-0278
    Se o número não estiver no formato esperado, retorna '+<número>' ou string vazia.
    """
    if not WHATSAPP_NUMERO:
        return ''

    num = ''.join(ch for ch in WHATSAPP_NUMERO if ch.isdigit())
    if len(num) >= 12 and num.startswith('55'):
        country = '+' + num[:2]
        area = num[2:4]
        rest = num[4:]
        if len(rest) == 8:
            formatted = f"{country} ({area}) {rest[:4]}-{rest[4:]}"
        elif len(rest) == 9:
            formatted = f"{country} ({area}) {rest[:5]}-{rest[5:]}"
        else:
            formatted = f"{country} ({area}) {rest}"
        return formatted

    # Fallback simple
    return '+' + num


def gerar_link_whatsapp_text(texto):
    """Gera um link wa.me com texto já codificado para uso direto em templates."""
    if not WHATSAPP_NUMERO:
        return '#'
    return f"https://wa.me/{WHATSAPP_NUMERO}?text={quote_plus(texto)}"