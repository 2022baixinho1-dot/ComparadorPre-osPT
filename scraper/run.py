"""
Corre todos os scrapers para os produtos definidos em config/produtos.json
e acrescenta os resultados de hoje a dados/precos.json (histórico acumulado).

Uso: python scraper/run.py
(É isto que o GitHub Actions corre automaticamente todos os dias.)
"""

import json
from datetime import date
from pathlib import Path

import continente
# À medida que forem feitos, importar aqui: pingo_doce, intermarche, aldi

RAIZ = Path(__file__).resolve().parent.parent
FICHEIRO_PRODUTOS = RAIZ / "config" / "produtos.json"
FICHEIRO_DADOS = RAIZ / "dados" / "precos.json"


def carregar_produtos():
    with open(FICHEIRO_PRODUTOS, encoding="utf-8") as f:
        return json.load(f)


def carregar_historico():
    if FICHEIRO_DADOS.exists():
        with open(FICHEIRO_DADOS, encoding="utf-8") as f:
            return json.load(f)
    return []


def guardar_historico(historico):
    FICHEIRO_DADOS.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHEIRO_DADOS, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def main():
    produtos = carregar_produtos()
    historico = carregar_historico()
    hoje = date.today().isoformat()

    novos_registos = []

    for produto in produtos:
        nome = produto["nome"]

        if "continente_url" in produto:
            resultado = continente.scrape_produto(produto["continente_url"], nome)
            if resultado["preco"] is not None:
                novos_registos.append({
                    "data": hoje,
                    "produto": nome,
                    "supermercado": resultado["supermercado"],
                    "preco": resultado["preco"],
                })
                print(f"OK: {nome} @ Continente = {resultado['preco']} EUR")
            else:
                print(f"FALHOU: {nome} @ Continente ({resultado.get('erro', 'preço não encontrado')})")

        # Quando adicionarmos Pingo Doce / Intermarché / Aldi, o padrão repete-se aqui.

    historico.extend(novos_registos)
    guardar_historico(historico)
    print(f"\nGuardados {len(novos_registos)} registos novos para {hoje}.")


if __name__ == "__main__":
    main()
