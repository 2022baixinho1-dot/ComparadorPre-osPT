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

import datetime
import glob
import json
import os
import re
import unicodedata

from rapidfuzz import fuzz

DADOS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "dados"))
CORRECOES_PATH = os.path.join(os.path.dirname(__file__), "correspondencias_manuais.json")
LIMIAR_CORRESPONDENCIA = 75  # 0-100; acima disto consideramos "o mesmo produto".
# Pode ser um valor relativamente permissivo porque os pares problemáticos
# já ficam bloqueados pela memória em correspondencias_manuais.json,
# independentemente da pontuação — por isso vale a pena arriscar mais
# correspondências novas e ir tratando os falsos positivos que aparecerem
# caso a caso, em vez de subir o limiar às cegas.

# Limite superior plausível para um preço promocional de folheto. Os
# parsers que extraem texto de PDF (Aldi, Lidl) por vezes juntam dois
# números por engano (ex: um preço "12.99" colado a outro valor da
# mesma zona da página, dando "9112910.49"). Este filtro evita que
# esse ruído entre na comparação.
PRECO_MAX_RAZOAVEL = 200.0


def normalizar(texto: str) -> str:
    """Baixa para minúsculas, remove acentos, e trata hífens/barras como espaços."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[-/,]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def carregar_correcoes_manuais(caminho: str = CORRECOES_PATH) -> tuple[set, set]:
    """
    Carrega a memória de correções manuais (ver correspondencias_manuais.json).
    Devolve dois conjuntos de pares (frozenset com os 2 nomes normalizados):
    `rejeitadas` (nunca corresponder, mesmo com pontuação alta) e
    `confirmadas` (corresponder sempre, mesmo com pontuação baixa).

    Se o ficheiro não existir, devolve dois conjuntos vazios — a memória
    é um extra opcional, o script funciona sem ela (só fuzzy matching).
    """
    if not os.path.exists(caminho):
        return set(), set()

    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)

    rejeitadas = {
        frozenset({normalizar(a), normalizar(b)})
        for a, b in dados.get("rejeitadas", [])
    }
    confirmadas = {
        frozenset({normalizar(a), normalizar(b)})
        for a, b in dados.get("confirmadas", [])
    }
    return rejeitadas, confirmadas


def preco_float(preco_str: str) -> float:
    """Converte preços em formato '3,39' (Continente) ou '8.19' (Lidl/Aldi) para float."""
    return float(str(preco_str).replace(",", "."))


def preco_razoavel(preco_str: str) -> bool:
    """Verifica se um preço parece plausível para um produto de supermercado (ver PRECO_MAX_RAZOAVEL)."""
    try:
        return 0 < preco_float(preco_str) <= PRECO_MAX_RAZOAVEL
    except (TypeError, ValueError):
        return False


def nome_informativo(nome: str, minimo_tokens: int = 2, tamanho_min_token: int = 3) -> bool:
    """
    Verifica se um nome de produto tem informação suficiente para uma
    correspondência fiável entre lojas.

    Os parsers de folheto (sobretudo o da Aldi, que extrai de PDF)
    por vezes deixam passar fragmentos de texto sem relação com o
    produto em si — ex: "embalado", ") embalado", "Sortido;" — que,
    por serem tão curtos e genéricos, acabam a corresponder por engano
    a qualquer produto que contenha essa palavra algures no nome (ex:
    "PREGUINHO DE VITELA EMBALADO" <-> "embalado"). Exigir pelo menos
    duas palavras "a sério" (3+ letras) evita esse tipo de falso
    positivo.
    """
    tokens = normalizar(nome).split()
    tokens_uteis = [t for t in tokens if t.isalpha() and len(t) >= tamanho_min_token]
    return len(tokens_uteis) >= minimo_tokens


def remover_duplicados(produtos: list[dict], loja: str) -> list[dict]:
    """
    Remove duplicados exatos (mesmo nome normalizado + mesmo preço)
    dentro da mesma loja — acontece quando um produto aparece em mais
    do que uma página do folheto (ex: "Camarão Cozido 30/50" do Lidl
    apareceu 2x em produção, e por isso correspondeu a 2 produtos
    diferentes do Continente ao mesmo tempo).
    """
    vistos = set()
    resultado = []
    duplicados = 0
    for p in produtos:
        chave = (normalizar(p.get("nome", "")), str(p.get("preco")))
        if chave in vistos:
            duplicados += 1
            continue
        vistos.add(chave)
        resultado.append(p)

    if duplicados:
        print(f"  ({loja}: descartados {duplicados} produto(s) duplicado(s) dentro da própria loja)")
    return resultado


def filtrar_produtos_validos(produtos: list[dict], loja: str) -> list[dict]:
    """Remove produtos com preço implausível, nome pouco informativo ou duplicados, avisando quantos foram descartados."""
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


def carregar_mais_recente(loja: str, sufixo: str | None = None) -> list[dict]:
    """
    Carrega os produtos do ficheiro de histórico mais recente de uma loja.
    Para a Aldi, usa sufixo="esta-semana" para escolher entre os dois
    ficheiros guardados por execução.

    NÃO usar para o Lidl — ver `carregar_lidl_atual()`, porque o Lidl
    guarda até 4 ficheiros por execução (semanal/fim-de-semana ×
    atual/seguinte) e "o último por ordem alfabética" não corresponde
    ao folheto atual.
    """
    padrao = os.path.join(DADOS_DIR, loja, "*.json")
    ficheiros = sorted(glob.glob(padrao))
    if sufixo:
        ficheiros = [f for f in ficheiros if sufixo in os.path.basename(f)]

    if not ficheiros:
        raise RuntimeError(f"Não encontrei nenhum ficheiro de histórico para '{loja}'.")

    with open(ficheiros[-1], encoding="utf-8") as f:
        conteudo = json.load(f)
    return filtrar_produtos_validos(conteudo["produtos"], loja)


def carregar_lidl_atual() -> list[dict]:
    """
    Carrega os produtos do Lidl desta semana: combina o folheto semanal
    atual com o de fim-de-semana atual.

    O Lidl guarda até 4 ficheiros por execução (semanal e fim-de-semana,
    cada um atual + seguinte). Escolher "o último ficheiro por ordem
    alfabética" dava sempre o semanal DA PRÓXIMA semana (porque
    "semanal" > "fim-de-semana" alfabeticamente, e dentro de "semanal"
    a data de início mais tardia ordena por último) — por isso aqui
    usamos os campos `categoria`, `valido_de` e `valido_ate` gravados
    em cada ficheiro para escolher, para cada categoria, o folheto cujo
    período de validade inclui a data de hoje.
    """
    padrao = os.path.join(DADOS_DIR, "lidl", "*.json")
    ficheiros = sorted(glob.glob(padrao))
    if not ficheiros:
        raise RuntimeError("Não encontrei nenhum ficheiro de histórico para 'lidl'.")

    # A execução mais recente é identificada pelos primeiros 10
    # caracteres do nome do ficheiro (data_execucao), que vêm sempre
    # em primeiro lugar no nome.
    ultima_execucao = os.path.basename(ficheiros[-1])[:10]
    ficheiros_ultima_execucao = [
        f for f in ficheiros if os.path.basename(f).startswith(ultima_execucao)
    ]

    hoje = datetime.date.today().isoformat()
    produtos = []
    for categoria in ("semanal", "fim-de-semana"):
        atual = None
        for caminho in ficheiros_ultima_execucao:
            with open(caminho, encoding="utf-8") as f:
                conteudo = json.load(f)
            if conteudo.get("categoria") != categoria:
                continue
            if conteudo.get("valido_de", "9999-99-99") <= hoje <= conteudo.get("valido_ate", "0000-00-00"):
                atual = conteudo
                break
        if atual is None:
            print(f"Aviso: não encontrei folheto Lidl '{categoria}' válido para hoje ({hoje}).")
            continue
        produtos.extend(atual["produtos"])

    return filtrar_produtos_validos(produtos, "lidl")


def encontrar_correspondencias(
    lojas: dict[str, list[dict]],
    rejeitadas: set | None = None,
    confirmadas: set | None = None,
) -> list[dict]:
    """
    Agrupa produtos parecidos entre as lojas, usando correspondência
    aproximada de nomes. Cada grupo guarda também, em "_scores", a
    pontuação (0-100) de cada correspondência em relação ao produto
    "âncora" (o primeiro encontrado) — útil para identificar casos
    duvidosos sem ter de adivinhar.

    `rejeitadas` e `confirmadas` vêm de carregar_correcoes_manuais():
    um par em `rejeitadas` nunca é escolhido, mesmo com a pontuação de
    fuzzy matching mais alta disponível; um par em `confirmadas` é
    sempre escolhido (score 100), mesmo que a pontuação real do fuzzy
    matching ficasse abaixo de LIMIAR_CORRESPONDENCIA.
    """
    rejeitadas = rejeitadas or set()
    confirmadas = confirmadas or set()
    usados = {loja: set() for loja in lojas}
    grupos = []
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
                    par = frozenset({nome_a_norm, nome_b_norm})
                    if par in rejeitadas:
                        continue  # memória diz que NUNCA é o mesmo produto
                    score = 100 if par in confirmadas else fuzz.token_set_ratio(nome_a_norm, nome_b_norm)
                    if score > melhor_score:
                        melhor_score, melhor_idx = score, idx_b
                if melhor_score >= LIMIAR_CORRESPONDENCIA:
                    grupo[loja_b] = produtos_b[melhor_idx]
                    usados[loja_b].add(melhor_idx)
                    scores[loja_b] = melhor_score

            if len(grupo) > 1:  # só interessa se apareceu em mais do que uma loja
                grupo["_scores"] = scores
                grupos.append(grupo)

    return grupos


def montar_resultado(grupos: list[dict]) -> list[dict]:
    """
    Transforma os grupos em resultado final: preço mais baixo assinalado,
    poupança em € e %, e pontuação de correspondência por loja. Ordenado
    da maior para a menor poupança em €.
    """
    resultado = []
    for grupo in grupos:
        scores = grupo.get("_scores", {})
        produtos = {loja: p for loja, p in grupo.items() if loja != "_scores"}
        precos = {loja: preco_float(p["preco"]) for loja, p in produtos.items()}
        loja_mais_barata = min(precos, key=precos.get)
        preco_min = precos[loja_mais_barata]
        preco_max = max(precos.values())
        poupanca_eur = round(preco_max - preco_min, 2)
        poupanca_pct = round((poupanca_eur / preco_max) * 100, 1) if preco_max else 0.0

        resultado.append({
            "produtos": {
                loja: {"nome": p["nome"], "preco": precos[loja]}
                for loja, p in produtos.items()
            },
            "mais_barato": loja_mais_barata,
            "poupanca_eur": poupanca_eur,
            "poupanca_pct": poupanca_pct,
            "pontuacoes_correspondencia": scores,
        })

    resultado.sort(key=lambda r: r["poupanca_eur"], reverse=True)
    return resultado


if __name__ == "__main__":
    rejeitadas, confirmadas = carregar_correcoes_manuais()
    print(f"Memória de correções: {len(confirmadas)} confirmada(s), {len(rejeitadas)} rejeitada(s)")

    lojas = {
        "continente": carregar_mais_recente("continente"),
        "lidl": carregar_lidl_atual(),
        "aldi": carregar_mais_recente("aldi", sufixo="esta-semana"),
    }
    for nome, produtos in lojas.items():
        print(f"{nome}: {len(produtos)} produtos carregados")

    grupos = encontrar_correspondencias(lojas, rejeitadas, confirmadas)
    resultado = montar_resultado(grupos)

    print(f"\nEncontrados {len(resultado)} produtos correspondentes entre pelo menos 2 lojas.")

    os.makedirs(os.path.join(DADOS_DIR, "comparacao"), exist_ok=True)
    caminho = os.path.join(DADOS_DIR, "comparacao", f"{datetime.date.today().isoformat()}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"Resultado guardado em: {caminho}")

    for item in resultado[:10]:
        print(f"\n--- poupança: {item['poupanca_eur']:.2f}€ ({item['poupanca_pct']:.0f}%) ---")
        for loja, p in item["produtos"].items():
            marca = " <-- mais barato" if loja == item["mais_barato"] else ""
            score = item["pontuacoes_correspondencia"].get(loja)
            score_txt = f" [score={score}]" if score is not None else " [âncora]"
            print(f"  {loja}: {p['nome']} = {p['preco']:.2f}€{marca}{score_txt}")
