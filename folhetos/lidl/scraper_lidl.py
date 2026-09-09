"""
Scraper do Folheto Semanal do Lidl Portugal.

Descoberta técnica: o Lidl usa, em todos os países, a mesma
infraestrutura do grupo Schwarz (dono do Lidl) para os folhetos —
uma API pública em endpoints.leaflets.schwarz, sem necessidade de
login, cookies, ou navegador. Confirmado com dados reais da Roménia;
a estrutura deveria ser idêntica para Portugal, só muda o
"client_locale". Este script ainda não foi testado ao vivo contra
lidl.pt — corre-o e vê o que aparece.

Passos:
1. Pede a lista de folhetos ativos (endpoint "overview")
2. Encontra o folheto semanal nacional (não é uma promoção regional
   de uma loja específica) que esteja a decorrer hoje
3. Pede o detalhe desse folheto (endpoint "flyer"), que traz o texto
   OCR de cada página em "keyWords" e "altText"

Dependências: requests
    pip install requests
"""

import requests
from datetime import date

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}
OVERVIEW_URL = "https://endpoints.leaflets.schwarz/v4/overview"
FLYER_URL = "https://endpoints.leaflets.schwarz/v4/flyer"


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

    # Se houver mais que um candidato, preferir o de título "mais parecido"
    # com uma promoção semanal genérica (evita brochuras especiais).
    return candidatos[0]


def get_flyer_detail(flyer: dict) -> dict:
    """Pede o detalhe completo de um folheto, usando o URL já fornecido em flyer['flyerJson']."""
    resp = requests.get(flyer["flyerJson"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()["flyer"]


if __name__ == "__main__":
    flyer = get_current_weekly_flyer()
    print(f"Folheto encontrado: {flyer['name']} — {flyer['title']}")
    print(f"Válido de {flyer['offerStartDate']} a {flyer['offerEndDate']}")

    detail = get_flyer_detail(flyer)
    pages = detail.get("pages", [])
    print(f"\nEncontradas {len(pages)} páginas.")

    for i, page in enumerate(pages[:3], start=1):
        print(f"\n--- Página {i} ---")
        print("altText:", page.get("altText"))
        print("keyWords (primeiros 300 caracteres):", (page.get("keyWords") or "")[:300])
