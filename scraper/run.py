"""
Corre o scraper genérico para todas as "fontes" (supermercado + link) de
cada produto definido em config/produtos.json, e acrescenta os resultados
de hoje a dados/precos.json (histórico acumulado).

Cada produto pode ter várias fontes com "unidades" diferentes (ex: o
Continente vende um pack de 6, os outros à unidade) — o preço é sempre
guardado também como "preco_unitario" para a comparação ser justa.

Uso: python scraper/run.py
(É isto que o GitHub Actions corre automaticamente todos os dias.)
"""

import json
from datetime import date
from pathlib import Path

import aldi
import comum
import intermarche

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

        for fonte in produto.get("fontes", []):
            supermercado = fonte["supermercado"]
            url = fonte["url"]
            unidades = fonte.get("unidades", 1)

            if supermercado == "Intermarché":
                resultado = intermarche.scrape_produto(url, nome)
            elif supermercado == "Aldi":
                resultado = aldi.scrape_produto(url, nome)
            else:
                resultado = comum.scrape_produto(url, nome, supermercado)

            if resultado["preco"] is not None:
                preco_unitario = round(resultado["preco"] / unidades, 4)
                novos_registos.append({
                    "data": hoje,
                    "produto": nome,
                    "supermercado": supermercado,
                    "preco": resultado["preco"],
                    "unidades": unidades,
                    "preco_unitario": preco_unitario,
                    "promocao_ate": resultado.get("promocao_ate"),
                })
                print(f"OK: {nome} @ {supermercado} = {resultado['preco']} EUR "
                      f"({unidades}un -> {preco_unitario} EUR/un)")
            else:
                print(f"FALHOU: {nome} @ {supermercado} "
                      f"({resultado.get('erro', 'preço não encontrado')})")

    historico.extend(novos_registos)
    guardar_historico(historico)
    print(f"\nGuardados {len(novos_registos)} registos novos para {hoje}.")


if __name__ == "__main__":
    main()
