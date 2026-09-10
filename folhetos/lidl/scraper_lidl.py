"""
Scraper do Folheto Semanal do Lidl Portugal.

Descoberta técnica: o Lidl usa, em todos os países, a mesma
infraestrutura do grupo Schwarz (dono do Lidl) para os folhetos —
uma API pública em endpoints.leaflets.schwarz, sem necessidade de
login, cookies, ou navegador. Confirmado com dados reais de Portugal.

Passos:
1. Pede a lista de folhetos ativos (endpoint "overview")
2. Encontra o folheto semanal nacional (não é uma promoção regional
   de uma loja específica) que esteja a decorrer hoje
3. Descarrega o PDF do folheto (campo "pdfUrl", já vem pronto a usar
   — sem o problema de botão JavaScript que tínhamos no Continente)
   e extrai o texto de todas as páginas de uma vez

Dependências: requests, pypdf
    pip install requests pypdf
"""

import io
import requests
from datetime import date
from pypdf import PdfReader

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}
OVERVIEW_URL = "https://endpoints.leaflets.schwarz/v4/overview"


def get_all_flyers() -> list[dict]:
    """Devolve a lista completa (achatada) de folhetos ativos do Lidl Portugal."""
    params = {"client_locale": "lidl/pt-PT"}
    resp = requests.get(OVERVIEW_URL, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    flyers = []
    for category in data.get("categories", []):
        for subcategory in category.get("subcategories", []):
            flyers.extend(subcategory.get("flyers", []))
    return flyers


def get_current_weekly_flyer() -> dict:
    """
    Encontra o folheto semanal NACIONAL (regions[0].type == "national")
    cujo período de oferta inclui hoje.
    """
    today = date.today().isoformat()
    flyers = get_all_flyers()

    candidatos = [
        f for f in flyers
        if any(r.get("type") == "national" for r in f.get("regions", []))
        and f.get("offerStartDate", "9999-99-99") <= today <= f.get("offerEndDate", "0000-00-00")
    ]

    if not candidatos:
        raise RuntimeError(
            "Não encontrei nenhum folheto semanal nacional ativo hoje. "
            "Pode ser preciso rever os critérios de filtro (ex: nomes de "
            "categoria/subcategoria específicos de Portugal)."
        )

    return candidatos[0]


def get_flyer_pdf_text(flyer: dict) -> str:
    """Descarrega o PDF do folheto e devolve o texto de todas as páginas, junto."""
    resp = requests.get(flyer["pdfUrl"], headers=HEADERS, timeout=60)
    resp.raise_for_status()

    reader = PdfReader(io.BytesIO(resp.content))
    paginas_texto = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(paginas_texto)


if __name__ == "__main__":
    flyer = get_current_weekly_flyer()
    print(f"Folheto encontrado: {flyer['name']} — {flyer['title']}")
    print(f"Válido de {flyer['offerStartDate']} a {flyer['offerEndDate']}")

    texto = get_flyer_pdf_text(flyer)
    print(f"\nTexto extraído: {len(texto)} caracteres.")
    print("\n--- Primeiros 500 caracteres ---")
    print(texto[:500])
