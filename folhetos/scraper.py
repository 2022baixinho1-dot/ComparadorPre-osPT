"""
Scraper do Folheto Semanal do Continente.

Estratégia (sem PDF, sem OCR):
1. Vai a https://www.continente.pt/folhetos e encontra o link do
   "Folheto Semanal" atual (distingue-se de "Continente Bom Dia" e
   "Madeira" pelo atributo title="Folheto Semanal" exato na imagem).
2. A partir desse URL base, percorre as páginas (?Page=1, ?Page=2, ...)
   e vai buscar o texto de cada página, que já vem incluído no HTML
   (usado pelo Continente para SEO), sem precisarmos de PDF nem imagens.
3. Para quando uma página deixa de trazer produtos novos.

Dependências: requests, beautifulsoup4
    pip install requests beautifulsoup4
"""

import re
import time
import requests
from bs4 import BeautifulSoup

FOLHETOS_INDEX_URL = "https://www.continente.pt/folhetos"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}


def get_current_weekly_flyer_url() -> str:
    """Devolve o URL do folheto semanal atual (loja continente, não Bom Dia/Madeira)."""
    resp = requests.get(FOLHETOS_INDEX_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # A imagem do folheto semanal "normal" tem title="Folheto Semanal" (exato).
    # As variantes ("Continente Bom Dia: Folheto Semanal", "Madeira: Folheto
    # Semanal", etc.) têm sempre texto adicional antes de "Folheto Semanal",
    # por isso o match exato evita apanhar a errada.
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


def get_page_text(base_url: str, page_number: int) -> str:
    """Devolve o texto em bruto (HTML->texto) de uma página do folheto."""
    url = f"{base_url}?Page={page_number}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def get_all_pages_text(base_url: str, max_pages: int = 40, pause_seconds: float = 1.0) -> list[str]:
    """
    Percorre as páginas do folheto até deixar de haver conteúdo novo
    (o Continente costuma repetir/ficar vazio a última página existente).
    """
    pages = []
    previous_text = None
    for page_number in range(1, max_pages + 1):
        text = get_page_text(base_url, page_number)
        if text == previous_text:
            # Página repetida = já passámos do fim do folheto.
            break
        pages.append(text)
        previous_text = text
        time.sleep(pause_seconds)  # não sobrecarregar o servidor
    return pages


if __name__ == "__main__":
    flyer_url = get_current_weekly_flyer_url()
    print(f"Folheto semanal atual: {flyer_url}")

    pages_text = get_all_pages_text(flyer_url)
    print(f"Encontradas {len(pages_text)} páginas com conteúdo.")

    for i, text in enumerate(pages_text, start=1):
        print(f"\n--- Página {i} (primeiros 300 caracteres) ---")
        print(text[:300])


Adiciona Scraper de Folhetos
