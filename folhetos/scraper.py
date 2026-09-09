"""
Scraper do Folheto Semanal do Continente.

Estratégia (sem PDF, sem OCR, sem percorrer página a página):
1. Vai a https://www.continente.pt/folhetos e encontra o link do
   "Folheto Semanal" atual (distingue-se de "Continente Bom Dia" e
   "Madeira" pelo atributo title="Folheto Semanal" exato na imagem).
2. Faz UM ÚNICO pedido a esse URL. O HTML da página inclui uma
   variável JavaScript (window.staticSettings) com um campo
   "pageTexts": uma lista com o texto de TODAS as páginas do
   folheto, já pronta a usar — não é preciso percorrer ?Page=1,
   ?Page=2, etc.

Dependências: requests, beautifulsoup4
    pip install requests beautifulsoup4
"""

import json
import re
import requests
from bs4 import BeautifulSoup

FOLHETOS_INDEX_URL = "https://www.continente.pt/folhetos"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}


def get_current_weekly_flyer_url() -> str:
    """Devolve o URL do folheto semanal atual (loja continente, não Bom Dia/Madeira)."""
    resp = requests.get(FOLHETOS_INDEX_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    img = soup.find("img", title="Folheto Semanal")
    if img is None:
        raise RuntimeError(
            "Não encontrei a imagem com title='Folheto Semanal'. "
            "É provável que o Continente tenha mudado o HTML da página de "
            "folhetos — é preciso reinspecionar."
        )

    link = img.find_parent("a")
    if link is None or not link.get("href"):
        raise RuntimeError("Encontrei a imagem do folheto mas não o link associado.")

    url = link["href"]
    if not url.startswith("http"):
        url = "https://www.continente.pt" + url
    return url.rstrip("/") + "/"


def get_all_pages_text(flyer_url: str) -> list[str]:
    """
    Faz um único pedido ao folheto e extrai o campo "pageTexts" da
    variável JavaScript window.staticSettings embutida no HTML.
    Devolve a lista de textos, um por página.
    """
    resp = requests.get(flyer_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text

    # A variável está definida como:
    #   window.staticSettings = { ...json grande..., "pageTexts": [...], ... };
    # Isolamos o valor do array "pageTexts" com um regex não-guloso,
    # que apanha desde "pageTexts":[ até ao ] correspondente antes de
    # ,"device" (o campo seguinte no objeto).
    match = re.search(r'"pageTexts":(\[.*?\]),"device"', html, re.DOTALL)
    if match is None:
        raise RuntimeError(
            "Não encontrei o campo 'pageTexts' no HTML do folheto. "
            "É provável que a estrutura da página tenha mudado."
        )

    page_texts = json.loads(match.group(1))
    return page_texts


if __name__ == "__main__":
    flyer_url = get_current_weekly_flyer_url()
    print(f"Folheto semanal atual: {flyer_url}")

    pages_text = get_all_pages_text(flyer_url)
    print(f"Extraídas {len(pages_text)} páginas de texto (1 único pedido HTTP).")

    for i, text in enumerate(pages_text[:3], start=1):
        print(f"\n--- Página {i} (primeiros 300 caracteres) ---")
        print(text[:300])
