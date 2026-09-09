"""
Script principal do módulo de folhetos: descobre o folheto atual do
Continente, extrai os produtos em promoção e guarda o resultado num
ficheiro JSON identificado pela data de execução, em
folhetos/dados/continente/.

Cada execução cria um novo ficheiro (uma "fotografia" dessa semana),
para manter o histórico de quais produtos estiveram em promoção e a
que preço, semana a semana.
"""

import json
import os
from datetime import date

from scraper import get_current_weekly_flyer_url, get_all_pages_text
from parser import parse_all_pages

DADOS_DIR = os.path.join(os.path.dirname(__file__), "dados", "continente")


def guardar_historico(flyer_url: str, produtos: list[dict]) -> str:
    """Guarda os produtos extraídos num ficheiro JSON com a data de hoje."""
    os.makedirs(DADOS_DIR, exist_ok=True)

    hoje = date.today().isoformat()  # ex: "2026-09-09"
    caminho = os.path.join(DADOS_DIR, f"{hoje}.json")

    conteudo = {
        "data_execucao": hoje,
        "url_folheto": flyer_url,
        "total_produtos": len(produtos),
        "produtos": produtos,
    }

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)

    return caminho


if __name__ == "__main__":
    flyer_url = get_current_weekly_flyer_url()
    print(f"Folheto semanal atual: {flyer_url}")

    pages_text = get_all_pages_text(flyer_url)
    produtos = parse_all_pages(pages_text)
    print(f"Extraídos {len(produtos)} produtos em promoção.")

    caminho = guardar_historico(flyer_url, produtos)
    print(f"Histórico guardado em: {caminho}")
