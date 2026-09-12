"""
Comparação de preços entre os folhetos do Continente, Lidl e Aldi.

Lê TODOS os folhetos disponíveis de cada supermercado da última execução
(incluindo os futuros do Aldi e do Lidl), encontra produtos parecidos
entre eles, e para cada grupo indica:
- qual supermercado tem o preço mais baixo HOJE
- se alguma loja vai passar a ter um preço mais baixo no futuro (e a
  partir de quando)

Dependências: rapidfuzz
    pip install rapidfuzz
"""

import datetime
import glob
import json
import os
import re
import unicodedata
from collections import Counter
from itertools import combinations

from rapidfuzz import fuzz

DADOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "dados"))
CORRECOES_PATH = os.path.join(os.path.dirname(__file__), "correspondencias_manuais.json")
LIMIAR_CORRESPONDENCIA = 75  # 0-100; acima disto consideramos "o mesmo produto".
LIMIAR_VINHO = 95
PRECO_MAX_RAZOAVEL = 200.0


def normalizar(texto: str) -> str:
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[-/,]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def carregar_correcoes_manuais(caminho: str = CORRECOES_PATH) -> tuple[set, set]:
    if not os.path.exists(caminho):
        return set(), set()
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    rejeitadas = {frozenset({normalizar(a), normalizar(b)}) for a, b in dados.get("rejeitadas", [])}
    confirmadas = {frozenset({normalizar(a), normalizar(b)}) for a, b in dados.get("confirmadas", [])}
    return rejeitadas, confirmadas


def preco_float(preco_str) -> float:
    return float(str(preco_str).replace(",", "."))


def preco_razoavel(preco_str) -> bool:
    try:
        return 0 < preco_float(preco_str) <= PRECO_MAX_RAZOAVEL
    except (TypeError, ValueError):
        return False


STOPWORDS_GENERICAS = {
    "mais", "cores", "cor", "cada", "dose", "doses", "conjunto", "conjuntos",
    "unidade", "unidades", "pack", "pares", "par", "anos", "ano",
    "profissional", "couro", "variante", "variantes", "detalhe", "sortido",
    "sortidas", "sortidos", "tamanhos", "tamanho", "medidas", "medida",
    "aprox", "capacidade", "kg", "xxl", "xl",
}


def nome_informativo(nome: str, minimo_tokens: int = 2, tamanho_min_token: int = 3) -> bool:
    tokens = normalizar(nome).split()
    tokens_uteis = [
        t for t in tokens
        if t.isalpha() and len(t) >= tamanho_min_token and t not in STOPWORDS_GENERICAS
    ]
    return len(tokens_uteis) >= minimo_tokens


def eh_vinho(nome_norm: str) -> bool:
    return "vinho" in nome_norm.split()


def remover_duplicados(produtos: list[dict], loja: str) -> list[dict]:
    """
    Remove duplicados exatos (mesmo nome normalizado + mesmo preço +
    MESMO período de validade) dentro da mesma loja. Incluir a validade
    na chave é importante agora: o mesmo produto pode aparecer com o
    mesmo preço em dois folhetos diferentes (ex: Aldi esta-semana e
    próxima-semana) sem ser um duplicado de parsing — são dois períodos
    de validade genuinamente diferentes.
    """
    vistos = set()
    resultado = []
    duplicados = 0
    for p in produtos:
        chave = (normalizar(p.get("nome", "")), str(p.get("preco")), p.get("valido_de"))
        if chave in vistos:
            duplicados += 1
            continue
        vistos.add(chave)
        resultado.append(p)
    if duplicados:
        print(f"  ({loja}: descartados {duplicados} produto(s) duplicado(s) dentro da própria loja)")
    return resultado


def filtrar_produtos_validos(produtos: list[dict], loja: str) -> list[dict]:
    validos = []
    descartados_preco = 0
    descartados_nome = 0
    for p in produtos:
        if not preco_razoavel(p.get("preco")):
            descartados_preco += 1
            continue
        if not nome_informativo(p.get("nome", "")):
            descartados_nome += 1
            continue
        validos.append(p)
    if descartados_preco:
        print(f"  ({loja}: descartados {descartados_preco} produto(s) com preço implausível)")
    if descartados_nome:
        print(f"  ({loja}: descartados {descartados_nome} produto(s) com nome pouco informativo)")
    return remover_duplicados(validos, loja)


def _adicionar_dias(data_iso: str, dias: int) -> str:
    d = datetime.date.fromisoformat(data_iso)
    return (d + datetime.timedelta(days=dias)).isoformat()


def _segunda_feira_da_semana(data_iso: str) -> str:
    """
    Devolve a segunda-feira da semana ISO em que 'data_iso' cai.
    Usado para a janela de validade do Continente/Aldi não depender do
    dia exato em que o scraper corre (pode correr manualmente em
    qualquer dia, não só à segunda) — o folheto continua a ser da
    semana toda, mesmo que a execução seja a meio da semana.
    """
    d = datetime.date.fromisoformat(data_iso)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def carregar_ofertas_brutas(loja: str) -> list[dict]:
    """
    Lê TODOS os ficheiros da última execução de uma loja (não só "o
    atual") e devolve uma lista plana de ofertas, cada uma com
    valido_de/valido_ate anexados.

    Como cada tipo de folheto grava a validade de forma diferente,
    normaliza-se aqui:
    - Lidl: já grava valido_de/valido_ate reais no ficheiro — usa-se
      diretamente.
    - Aldi: só grava "periodo" ("esta semana"/"proxima semana"), sem
      datas exatas. ASSUNÇÃO: cada período é uma semana corrida
      (segunda a domingo) a partir da data de execução — pode não ser
      exato se o dia da semana em que o scraper corre não for sempre o
      mesmo.
    - Continente: não grava validade nenhuma (só 1 folheto, sem
      histórico de futuro). ASSUNÇÃO: mesma janela semanal do Aldi, a
      partir da data de execução — serve só para saber que está válido
      "agora", não há folheto futuro do Continente para comparar.
    """
    padrao = os.path.join(DADOS_DIR, loja, "*.json")
    ficheiros = sorted(f for f in glob.glob(padrao) if os.path.basename(f) != "latest.json")

    if not ficheiros:
        raise RuntimeError(f"Não encontrei nenhum ficheiro de histórico para '{loja}'.")

    ultima_execucao = os.path.basename(ficheiros[-1])[:10]
    ficheiros_ultima_execucao = [
        f for f in ficheiros if os.path.basename(f).startswith(ultima_execucao)
    ]

    ofertas = []
    for caminho in ficheiros_ultima_execucao:
        with open(caminho, encoding="utf-8") as f:
            conteudo = json.load(f)

        if "valido_de" in conteudo:  # Lidl
            valido_de = conteudo["valido_de"]
            valido_ate = conteudo["valido_ate"]
        elif "periodo" in conteudo:  # Aldi
            segunda = _segunda_feira_da_semana(conteudo["data_execucao"])
            if conteudo["periodo"] == "esta semana":
                valido_de = segunda
            else:
                valido_de = _adicionar_dias(segunda, 7)
            valido_ate = _adicionar_dias(valido_de, 6)
        else:  # Continente
            valido_de = _segunda_feira_da_semana(conteudo["data_execucao"])
            valido_ate = _adicionar_dias(valido_de, 6)

        for p in conteudo["produtos"]:
            oferta = dict(p)
            oferta["valido_de"] = valido_de
            oferta["valido_ate"] = valido_ate
            ofertas.append(oferta)

    return filtrar_produtos_validos(ofertas, loja)


def agrupar_por_nome_normalizado(ofertas: list[dict], loja: str) -> list[dict]:
    """
    Junta as várias entradas do mesmo produto na mesma loja (ex: Aldi
    "esta semana" e "próxima semana") num único registo com uma lista
    de preços por período — para a comparação entre lojas tratar isto
    como UM produto com vários preços ao longo do tempo, em vez de
    duas entradas concorrentes que se roubariam uma à outra no
    fuzzy matching.
    """
    grupos: dict[str, dict] = {}
    for o in ofertas:
        chave = normalizar(o["nome"])
        if chave not in grupos:
            grupos[chave] = {"nome": o["nome"], "loja": loja, "precos": []}
        grupos[chave]["precos"].append({
            "preco": preco_float(o["preco"]),
            "valido_de": o["valido_de"],
            "valido_ate": o["valido_ate"],
        })
    for g in grupos.values():
        g["precos"].sort(key=lambda x: x["valido_de"])
    return list(grupos.values())


def carregar_produtos_com_precos(loja: str) -> list[dict]:
    """Carrega e junta os produtos de uma loja, prontos para a comparação entre lojas."""
    ofertas = carregar_ofertas_brutas(loja)
    return agrupar_por_nome_normalizado(ofertas, loja)


def bloquear_confirmadas(lojas: dict[str, list[dict]], confirmadas: set, usados: dict[str, set]) -> list[dict]:
    indice: dict[str, list[tuple[str, int]]] = {}
    for loja, produtos in lojas.items():
        for idx, p in enumerate(produtos):
            indice.setdefault(normalizar(p["nome"]), []).append((loja, idx))

    grupos = []
    for par in confirmadas:
        if len(par) != 2:
            continue
        nome_x, nome_y = tuple(par)
        candidatos_x = indice.get(nome_x, [])
        candidatos_y = indice.get(nome_y, [])
        for loja_x, idx_x in candidatos_x:
            if idx_x in usados[loja_x]:
                continue
            for loja_y, idx_y in candidatos_y:
                if loja_x == loja_y or idx_y in usados[loja_y]:
                    continue
                usados[loja_x].add(idx_x)
                usados[loja_y].add(idx_y)
                grupos.append({
                    loja_x: lojas[loja_x][idx_x],
                    loja_y: lojas[loja_y][idx_y],
                    "_scores": {loja_y: 100},
                })
                break
            else:
                continue
            break
    return grupos


def encontrar_correspondencias(
    lojas: dict[str, list[dict]],
    rejeitadas: set | None = None,
    confirmadas: set | None = None,
) -> list[dict]:
    rejeitadas = rejeitadas or set()
    confirmadas = confirmadas or set()
    usados = {loja: set() for loja in lojas}

    grupos = bloquear_confirmadas(lojas, confirmadas, usados)

    lista_lojas = list(lojas.items())
    for i, (loja_a, produtos_a) in enumerate(lista_lojas):
        for idx_a, produto_a in enumerate(produtos_a):
            if idx_a in usados[loja_a]:
                continue
            grupo = {loja_a: produto_a}
            scores = {}
            usados[loja_a].add(idx_a)
            nome_a_norm = normalizar(produto_a["nome"])

            for loja_b, produtos_b in lista_lojas[i + 1:]:
                melhor_idx, melhor_score = None, 0
                for idx_b, produto_b in enumerate(produtos_b):
                    if idx_b in usados[loja_b]:
                        continue
                    nome_b_norm = normalizar(produto_b["nome"])
                    if frozenset({nome_a_norm, nome_b_norm}) in rejeitadas:
                        continue
                    score = fuzz.token_set_ratio(nome_a_norm, nome_b_norm)
                    if score > melhor_score:
                        melhor_score, melhor_idx = score, idx_b

                if melhor_idx is None:
                    continue

                limiar = LIMIAR_CORRESPONDENCIA
                if eh_vinho(nome_a_norm) and eh_vinho(normalizar(produtos_b[melhor_idx]["nome"])):
                    limiar = LIMIAR_VINHO

                if melhor_score >= limiar:
                    grupo[loja_b] = produtos_b[melhor_idx]
                    usados[loja_b].add(melhor_idx)
                    scores[loja_b] = melhor_score

            if len(grupo) > 1:
                grupo["_scores"] = scores
                grupos.append(grupo)

    return grupos


def montar_resultado(grupos: list[dict], hoje: str | None = None) -> list[dict]:
    """
    Para cada grupo de produtos correspondentes: preço mais baixo HOJE
    (considerando só ofertas cuja validade inclui a data de hoje), e,
    se existir, a próxima alteração — uma oferta FUTURA (de qualquer
    loja) mais barata do que o preço mais baixo de hoje.
    """
    hoje = hoje or datetime.date.today().isoformat()
    resultado = []

    for grupo in grupos:
        scores = grupo.get("_scores", {})
        produtos = {loja: p for loja, p in grupo.items() if loja != "_scores"}

        precos_hoje = {}
        for loja, p in produtos.items():
            candidatos = [pr["preco"] for pr in p["precos"] if pr["valido_de"] <= hoje <= pr["valido_ate"]]
            if candidatos:
                precos_hoje[loja] = min(candidatos)

        if not precos_hoje:
            continue  # só há ofertas futuras para este grupo, nada válido hoje

        loja_mais_barata = min(precos_hoje, key=precos_hoje.get)
        preco_min = precos_hoje[loja_mais_barata]
        preco_max = max(precos_hoje.values())
        poupanca_eur = round(preco_max - preco_min, 2)
        poupanca_pct = round((poupanca_eur / preco_max) * 100, 1) if preco_max else 0.0

        melhor_futuro = None
        for loja, p in produtos.items():
            for pr in p["precos"]:
                if pr["valido_de"] > hoje and pr["preco"] < preco_min:
                    if melhor_futuro is None or pr["preco"] < melhor_futuro["preco"]:
                        melhor_futuro = {"loja": loja, "preco": pr["preco"], "a_partir_de": pr["valido_de"]}

        resultado.append({
            "produtos": {
                loja: {"nome": p["nome"], "preco_hoje": precos_hoje.get(loja)}
                for loja, p in produtos.items()
            },
            "mais_barato_hoje": loja_mais_barata,
            "poupanca_eur": poupanca_eur,
            "poupanca_pct": poupanca_pct,
            "proxima_alteracao": melhor_futuro,
            "pontuacoes_correspondencia": scores,
        })

    resultado.sort(key=lambda r: r["poupanca_eur"], reverse=True)
    return resultado


def contar_por_par_lojas(resultado: list[dict]) -> Counter:
    contagem = Counter()
    for item in resultado:
        lojas_envolvidas = sorted(item["produtos"].keys())
        for par in combinations(lojas_envolvidas, 2):
            contagem[par] += 1
    return contagem


if __name__ == "__main__":
    rejeitadas, confirmadas = carregar_correcoes_manuais()
    print(f"Memória de correções: {len(confirmadas)} confirmada(s), {len(rejeitadas)} rejeitada(s)")

    lojas = {
        "continente": carregar_produtos_com_precos("continente"),
        "lidl": carregar_produtos_com_precos("lidl"),
        "aldi": carregar_produtos_com_precos("aldi"),
    }
    for nome, produtos in lojas.items():
        total_precos = sum(len(p["precos"]) for p in produtos)
        print(f"{nome}: {len(produtos)} produtos únicos, {total_precos} preços (atuais+futuros) carregados")

    grupos = encontrar_correspondencias(lojas, rejeitadas, confirmadas)
    resultado = montar_resultado(grupos)

    print(f"\nEncontrados {len(resultado)} produtos correspondentes entre pelo menos 2 lojas, válidos hoje.")

    for (loja_x, loja_y), n in contar_por_par_lojas(resultado).most_common():
        print(f"  {loja_x} <-> {loja_y}: {n}")

    os.makedirs(os.path.join(DADOS_DIR, "comparacao"), exist_ok=True)
    caminho = os.path.join(DADOS_DIR, "comparacao", f"{datetime.date.today().isoformat()}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"Resultado guardado em: {caminho}")

    for item in resultado[:10]:
        print(f"\n--- poupança: {item['poupanca_eur']:.2f}€ ({item['poupanca_pct']:.0f}%) ---")
        for loja, p in item["produtos"].items():
            marca = " <-- mais barato hoje" if loja == item["mais_barato_hoje"] else ""
            score = item["pontuacoes_correspondencia"].get(loja)
            score_txt = f" [score={score}]" if score is not None else " [âncora]"
            print(f"  {loja}: {p['nome']} = {p['preco_hoje']:.2f}€{marca}{score_txt}")
        if item["proxima_alteracao"]:
            fa = item["proxima_alteracao"]
            print(f"  >> a partir de {fa['a_partir_de']}: {fa['loja']} passa a {fa['preco']:.2f}€ (mais barato)")
