"""
Script principal do módulo de folhetos do Lidl: descobre o folheto
semanal nacional atual, extrai os produtos em promoção do PDF e
guarda o resultado num ficheiro JSON identificado pela data de
execução, em folhetos/dados/lidl/.
"""

import json
import os
from datetime import date

from scraper_lidl import get_current_weekly_flyer, get_flyer_pdf_text
from parser_lidl import parse_products

DADOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "dados", "lidl"))


def guardar_historico(flyer: dict, produtos: list[dict]) -> str:
    """Guarda os produtos extraídos num ficheiro JSON com a data de hoje."""
    os.makedirs(DADOS_DIR, exist_ok=True)

    hoje = date.today().isoformat()
    caminho = os.path.join(DADOS_DIR, f"{hoje}.json")

    conteudo = {
        "data_execucao": hoje,
        "folheto": flyer.get("title"),
        "valido_de": flyer.get("offerStartDate"),
        "valido_ate": flyer.get("offerEndDate"),
        "total_produtos": len(produtos),
        "produtos": produtos,
    }

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)

    return caminho


if __name__ == "__main__":
    flyer = get_current_weekly_flyer()
    print(f"Folheto: {flyer['name']} — {flyer['title']}")

    pdf_text = get_flyer_pdf_text(flyer)
    produtos = parse_products(pdf_text)
    print(f"Extraídos {len(produtos)} produtos em promoção.")

    caminho = guardar_historico(flyer, produtos)
    print(f"Histórico guardado em: {caminho}")
