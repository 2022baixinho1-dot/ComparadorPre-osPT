"""
Comparação de preços entre os folhetos do Continente, Lidl e Aldi.

Lê o histórico mais recente de cada supermercado (folhetos/dados/<loja>/),
encontra produtos parecidos entre eles (correspondência aproximada de
texto, tolerante a diferenças de formatação como "Meio Gordo" vs
"Meio-Gordo", ordem das palavras, marca no início ou no fim, etc.), e
para cada grupo de produtos parecidos indica qual supermercado tem o
preço mais baixo.

Dependências: rapidfuzz
    pip install rapidfuzz
"""

import glob
import json
import os
import re
import unicodedata

from rapidfuzz import fuzz

DADOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "dados"))
LIMIAR_CORRESPONDENCIA = 80  # 0-100; acima disto consideramos "o mesmo produto"


def normalizar(texto: str) -> str:
    """Baixa para minúsculas, remove acentos, e trata hífens/barras como espaços."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[-/,]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def preco_float(preco_str: str) -> float:
    """Converte preços em formato '3,39' (Continente) ou '8.19' (Lidl/Aldi) para float."""
    return float(str(preco_str).replace(",", "."))


def carregar_mais_recente(loja: str, sufixo: str | None = None, excluir: str | None = None) -> list[dict]:
    """
    Carrega os produtos do ficheiro de histórico mais recente de uma loja.
    - sufixo: só considera ficheiros cujo nome contenha esta substring
      (ex: "esta-semana" para a Aldi, "semanal" para o Lidl).
    - excluir: descarta ficheiros cujo nome contenha esta substring
      (ex: "fim-de-semana" para o Lidl, para não confundir com o semanal).
    Quando há mais que um ficheiro válido na execução mais recente (caso
    do Lidl, que grava "semanal atual" + "semanal seguinte" no mesmo dia),
    escolhe o de data de início mais cedo — ou seja, a semana atual.
    """
    padrao = os.path.join(DADOS_DIR, loja, "*.json")
    ficheiros = sorted(glob.glob(padrao))
    if sufixo:
        ficheiros = [f for f in ficheiros if sufixo in os.path.basename(f)]
    if excluir:
        ficheiros = [f for f in ficheiros if excluir not in os.path.basename(f)]

    if not ficheiros:
        raise RuntimeError(f"Não encontrei nenhum ficheiro de histórico para '{loja}'.")

    # entre os ficheiros da execução mais recente (mesmo prefixo de data),
    # fica com o primeiro por ordem alfabética = data de início mais cedo
    ultima_execucao = os.path.basename(ficheiros[-1])[:10]  # "AAAA-MM-DD"
    candidatos = sorted(f for f in ficheiros if os.path.basename(f).startswith(ultima_execucao))

    with open(candidatos[0], encoding="utf-8") as f:
        conteudo = json.load(f)
    return conteudo["produtos"]


def encontrar_correspondencias(lojas: dict[str, list[dict]]) -> list[dict]:
    """Agrupa produtos parecidos entre as lojas, usando correspondência aproximada de nomes."""
    usados = {loja: set() for loja in lojas}
    grupos = []
    lista_lojas = list(lojas.items())

    for i, (loja_a, produtos_a) in enumerate(lista_lojas):
        for idx_a, produto_a in enumerate(produtos_a):
            if idx_a in usados[loja_a]:
                continue
            grupo = {loja_a: produto_a}
            usados[loja_a].add(idx_a)
            nome_a_norm = normalizar(produto_a["nome"])

            for loja_b, produtos_b in lista_lojas[i + 1:]:
                melhor_idx, melhor_score = None, 0
                for idx_b, produto_b in enumerate(produtos_b):
                    if idx_b in usados[loja_b]:
                        continue
                    score = fuzz.token_set_ratio(nome_a_norm, normalizar(produto_b["nome"]))
                    if score > melhor_score:
                        melhor_score, melhor_idx = score, idx_b
                if melhor_score >= LIMIAR_CORRESPONDENCIA:
                    grupo[loja_b] = produtos_b[melhor_idx]
                    usados[loja_b].add(melhor_idx)

            if len(grupo) > 1:  # só interessa se apareceu em mais do que uma loja
                grupos.append(grupo)

    return grupos


def montar_resultado(grupos: list[dict]) -> list[dict]:
    """Transforma os grupos em resultado final, com o preço mais baixo assinalado."""
    resultado = []
    for grupo in grupos:
        precos = {loja: preco_float(p["preco"]) for loja, p in grupo.items()}
        loja_mais_barata = min(precos, key=precos.get)
        resultado.append({
            "produtos": {
                loja: {"nome": p["nome"], "preco": precos[loja]}
                for loja, p in grupo.items()
            },
            "mais_barato": loja_mais_barata,
        })
    return resultado


if __name__ == "__main__":
    lojas = {
        "continente": carregar_mais_recente("continente"),
        "lidl": carregar_mais_recente("lidl", sufixo="semanal", excluir="fim-de-semana"),
        "aldi": carregar_mais_recente("aldi", sufixo="esta-semana"),
    }
    for nome, produtos in lojas.items():
        print(f"{nome}: {len(produtos)} produtos carregados")

    grupos = encontrar_correspondencias(lojas)
    resultado = montar_resultado(grupos)

    print(f"\nEncontrados {len(resultado)} produtos correspondentes entre pelo menos 2 lojas.")

    os.makedirs(os.path.join(DADOS_DIR, "comparacao"), exist_ok=True)
    import datetime
    caminho = os.path.join(DADOS_DIR, "comparacao", f"{datetime.date.today().isoformat()}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"Resultado guardado em: {caminho}")

    for item in resultado[:10]:
        print("\n---")
        for loja, p in item["produtos"].items():
            marca = " <-- mais barato" if loja == item["mais_barato"] else ""
            print(f"  {loja}: {p['nome']} = {p['preco']:.2f}€{marca}")
