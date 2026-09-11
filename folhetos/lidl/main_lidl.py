"""
Script principal do módulo de folhetos do Lidl: descobre os folhetos
nacionais recentes e ainda válidos (semanais + fim de semana, atual e
seguinte), extrai os produtos de cada um, e guarda um ficheiro JSON
por folheto, identificado pela data de execução, categoria e data de
início do folheto, em folhetos/dados/lidl/.
"""

import json
import os
from datetime import date

from scraper_lidl import get_folhetos_nacionais_validos, get_flyer_pdf_text
from parser_lidl import parse_products

DADOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "dados", "lidl"))


def guardar_historico(flyer: dict, produtos: list[dict], hoje: str) -> str:
    os.makedirs(DADOS_DIR, exist_ok=True)

    # sufixo tipo "semanal-2026-09-07" ou "fim-de-semana-2026-09-07"
    # agora nunca colide entre categorias, porque a categoria vem da
    # subcategoria da API e não do título.
    sufixo = f"{flyer['_categoria']}-{flyer['offerStartDate']}"
    caminho = os.path.join(DADOS_DIR, f"{hoje}-{sufixo}.json")

    conteudo = {
        "data_execucao": hoje,
        "categoria": flyer["_categoria"],
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
    hoje = date.today().isoformat()
    folhetos = get_folhetos_nacionais_validos()
    print(f"Encontrados {len(folhetos)} folhetos válidos.")

    for flyer in folhetos:
        print(f"\n=== [{flyer['_categoria']}] {flyer['title']} ({flyer['offerStartDate']}) ===")
        # Debug temporário: confirmar que a subcategoria tem mesmo a
        # palavra-chave esperada. Remover esta linha depois de confirmado.
        print(f"    subcategoria (debug): {flyer['_subcategoria']}")

        pdf_text = get_flyer_pdf_text(flyer)
        produtos = parse_products(pdf_text)
        print(f"Extraídos {len(produtos)} produtos.")

        caminho = guardar_historico(flyer, produtos, hoje)
        print(f"Guardado em: {caminho}")
