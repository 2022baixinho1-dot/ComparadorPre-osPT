"""
Scraper para intermarche.pt

Ao contrário do Continente/Pingo Doce (que usam JSON-LD "application/ld+json"),
o Intermarché é feito em Next.js e guarda todos os dados da página, incluindo
o preço, num bloco <script id="__NEXT_DATA__" type="application/json">.
"""

import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9",
}


def _preco_via_html_visivel(soup):
    """
    Plano B: o preço também está escrito no HTML visível da página, dentro de
    <span class="productDetail__productPrice">, mesmo que o bloco JSON não
    tenha o campo esperado (ex: por causa de proteção anti-scraping).
    O markup vem com comentários HTML no meio dos números (ex: "0<!-- -->,
    <!-- -->87"), por isso extraímos só os dígitos.
    """
    tag = soup.find(class_="productDetail__productPrice")
    if not tag:
        return None
    digitos = re.findall(r"\d+", str(tag))
    if len(digitos) >= 2:
        try:
            return float(f"{digitos[0]}.{digitos[1]}")
        except ValueError:
            return None
    return None


def scrape_produto(url: str, nome_produto: str) -> dict:
    resultado = {
        "nome": nome_produto,
        "supermercado": "Intermarché",
        "preco": None,
        "url": url,
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        resultado["erro"] = f"Falha ao aceder à página: {e}"
        return resultado

    soup = BeautifulSoup(resp.text, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")

    preco = None

    if script and script.string:
        try:
            data = json.loads(script.string)
            page_props = data["props"]["pageProps"]
            if isinstance(page_props.get("prix"), (int, float)):
                preco = page_props["prix"]
            elif isinstance(page_props.get("unitPrice"), (int, float)):
                preco = page_props["unitPrice"]
            elif "product" in page_props and "prix" in page_props["product"]:
                preco = page_props["product"]["prix"].get("prix")
        except (KeyError, TypeError, json.JSONDecodeError):
            pass

    if preco is None:
        preco = _preco_via_html_visivel(soup)

    if preco is None:
        resultado["erro"] = "Preço não encontrado (nem no JSON nem no HTML visível)."
    else:
        resultado["preco"] = float(preco)

    return resultado


if __name__ == "__main__":
    teste = scrape_produto(
        "https://intermarche.pt/product/leite-uht-meio-gordo-dos-acores-1l/5604260270569",
        "Leite Meio Gordo",
    )
    print(json.dumps(teste, indent=2, ensure_ascii=False))
