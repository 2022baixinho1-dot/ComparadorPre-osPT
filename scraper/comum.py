"""
Scraper genérico, reutilizado por todos os supermercados.

A técnica é a mesma nos 4 sites: ler o bloco <script type="application/ld+json">
que cada página de produto tem embutido (para o Google indexar), que contém
o preço em formato estruturado. É mais estável do que depender do desenho
visual da página (CSS), que muda com mais frequência.

Se esse bloco não existir ou não tiver o preço, há um fallback que procura
diretamente no HTML um padrão tipo "1,99 €".
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


def _extrair_json_ld(soup):
    """Procura o bloco JSON-LD do tipo Product e devolve o dicionário."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue

        candidatos = data if isinstance(data, list) else [data]
        for item in candidatos:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
            # Alguns sites embrulham o produto dentro de "@graph"
            if isinstance(item, dict) and "@graph" in item:
                for sub in item["@graph"]:
                    if isinstance(sub, dict) and sub.get("@type") == "Product":
                        return sub
    return None


def _preco_fallback_regex(html):
    """Último recurso: procura um padrão de preço tipo '1,99 €' no HTML bruto."""
    match = re.search(r'(\d+[,.]\d{2})\s*€', html)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def scrape_produto(url: str, nome_produto: str, supermercado: str) -> dict:
    """
    Vai buscar o preço atual de um produto numa página de supermercado.

    Devolve: nome, supermercado, preco (preço da embalagem tal como está
    no site), url. Se não conseguir ler, preco fica a None.
    """
    resultado = {
        "nome": nome_produto,
        "supermercado": supermercado,
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
    produto = _extrair_json_ld(soup)

    if produto and "offers" in produto:
        oferta = produto["offers"]
        if isinstance(oferta, list):
            oferta = oferta[0]
        try:
            resultado["preco"] = float(oferta.get("price"))
        except (TypeError, ValueError):
            pass

    if resultado["preco"] is None:
        resultado["preco"] = _preco_fallback_regex(resp.text)

    if resultado["preco"] is None:
        resultado["erro"] = "Preço não encontrado na página (JSON-LD nem regex)."

    return resultado


if __name__ == "__main__":
    # Teste manual: python comum.py
    teste = scrape_produto(
        "https://www.continente.pt/produto/leite-uht-meio-gordo-continente-8504295.html",
        "Leite Meio Gordo",
        "Continente",
    )
    print(json.dumps(teste, indent=2, ensure_ascii=False))
