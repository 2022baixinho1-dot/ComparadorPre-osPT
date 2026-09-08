"""
Scraper para intermarche.pt

Ao contrário do Continente/Pingo Doce (que usam JSON-LD "application/ld+json"),
o Intermarché é feito em Next.js e guarda todos os dados da página, incluindo
o preço, num bloco <script id="__NEXT_DATA__" type="application/json">.

O preço está em: props.pageProps.prix.prix
"""

import json
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9",
}


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

    if not script or not script.string:
        resultado["erro"] = "Bloco __NEXT_DATA__ não encontrado."
        return resultado

    try:
        data = json.loads(script.string)
        preco = data["props"]["pageProps"]["prix"]["prix"]
        resultado["preco"] = float(preco)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        resultado["erro"] = f"Não consegui encontrar o preço na estrutura esperada: {e}"

    return resultado


if __name__ == "__main__":
    teste = scrape_produto(
        "https://intermarche.pt/product/leite-uht-meio-gordo-dos-acores-1l/5604260270569",
        "Leite Meio Gordo",
    )
    print(json.dumps(teste, indent=2, ensure_ascii=False))
