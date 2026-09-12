"""
Script principal do módulo de folhetos da Aldi: descobre os folhetos
de "esta semana" e "próxima semana", extrai os produtos em promoção
de cada um, e guarda os resultados em ficheiros JSON separados,
identificados pela data de execução, em folhetos/dados/aldi/.
"""

import json
import os
from datetime import date

from scraper_aldi import (
    PAGINA_ESTA_SEMANA,
    PAGINA_PROXIMA_SEMANA,
    get_flyer_url,
    get_all_pages_text,
)
from parser_aldi import parse_all_pages

DADOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "dados", "aldi"))


def processar_e_guardar(nome_periodo: str, pagina_url: str, hoje: str) -> str:
    flyer_url = get_flyer_url(pagina_url)
    pages_text = get_all_pages_text(flyer_url)
    produtos = parse_all_pages(pages_text)

    os.makedirs(DADOS_DIR, exist_ok=True)
    sufixo = "esta-semana" if nome_periodo == "esta semana" else "proxima-semana"
    caminho = os.path.join(DADOS_DIR, f"{hoje}-{sufixo}.json")

    conteudo = {
        "data_execucao": hoje,
        "periodo": nome_periodo,
        "url_folheto": flyer_url,
        "total_produtos": len(produtos),
        "produtos": produtos,
    }

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)

    return caminho


if __name__ == "__main__":
    hoje = date.today().isoformat()
    todos_produtos = []

    for nome_periodo, pagina_url in [
        ("esta semana", PAGINA_ESTA_SEMANA),
        ("proxima semana", PAGINA_PROXIMA_SEMANA),
    ]:
        print(f"\n=== Folheto da {nome_periodo} ===")
        flyer_url = get_flyer_url(pagina_url)
        pages_text = get_all_pages_text(flyer_url)
        produtos = parse_all_pages(pages_text)
        todos_produtos.extend(produtos)

        os.makedirs(DADOS_DIR, exist_ok=True)
        sufixo = "esta-semana" if nome_periodo == "esta semana" else "proxima-semana"
        caminho = os.path.join(DADOS_DIR, f"{hoje}-{sufixo}.json")
        conteudo = {
            "data_execucao": hoje,
            "periodo": nome_periodo,
            "url_folheto": flyer_url,
            "total_produtos": len(produtos),
            "produtos": produtos,
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False, indent=2)
        print(f"Histórico guardado em: {caminho}")

    # cópia combinada (esta semana + próxima semana), para a página web
    caminho_latest = os.path.join(DADOS_DIR, "latest.json")
    conteudo_latest = {
        "data_execucao": hoje,
        "total_produtos": len(todos_produtos),
        "produtos": todos_produtos,
    }
    with open(caminho_latest, "w", encoding="utf-8") as f:
        json.dump(conteudo_latest, f, ensure_ascii=False, indent=2)
    print(f"Latest combinado guardado em: {caminho_latest}")
