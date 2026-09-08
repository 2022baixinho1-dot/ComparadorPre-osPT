"""
Scraper para aldi.pt

Estrutura própria: os dados do produto vêm dentro de __NEXT_DATA__, mas
escondidos num campo chamado "apiData" que é, ele próprio, uma string com
JSON lá dentro (não um objeto direto) — por isso há um segundo json.loads().

O Aldi tem uma vantagem sobre os outros: mostra não só o preço atual
(currentPrice) mas também uma lista de promoções futuras (promotionPrices),
cada uma com data de início e fim. Isso permite-nos já preparar o campo
"promocao_ate" para o site, sem termos de adivinhar via histórico.
"""

import json
from datetime import date

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
        "supermercado": "Aldi",
        "preco": None,
        "promocao_ate": None,
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
        api_data_bruto = data["props"]["pageProps"]["apiData"]
        api_data = json.loads(api_data_bruto)

        produto = None
        for entrada in api_data:
            if entrada[0] == "PRODUCT_DETAIL_GET":
                produto = entrada[1]["res"]["products"][0]
                break

        if produto is None:
            resultado["erro"] = "Não encontrei o bloco PRODUCT_DETAIL_GET."
            return resultado

        preco_atual = produto["currentPrice"]["priceValue"]
        hoje = date.today().isoformat()

        # Se houver uma promoção ativa hoje, essa é que manda no preço.
        for promo in produto.get("promotionPrices", []):
            if promo.get("validFromLocalDate", "") <= hoje <= promo.get("validUntilLocalDate", ""):
                preco_atual = promo["priceValue"]
                resultado["promocao_ate"] = promo["validUntilLocalDate"]
                break

        resultado["preco"] = float(preco_atual)

    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as e:
        resultado["erro"] = f"Não consegui encontrar o preço na estrutura esperada: {e}"

    return resultado


if __name__ == "__main__":
    teste = scrape_produto(
        "https://www.aldi.pt/produto-detalhe/leite-meio-gordo-70012530000.html",
        "Leite Meio Gordo",
    )
    print(json.dumps(teste, indent=2, ensure_ascii=False))
