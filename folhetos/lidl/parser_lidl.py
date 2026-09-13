"""
Parser de produtos do Folheto Semanal do Lidl Portugal.

Recebe o texto extraído do PDF do folheto (ver scraper_lidl.get_flyer_pdf_text)
e devolve uma lista de produtos com nome, preço e preço por unidade.

Padrão "normal" de cada produto no texto do PDF:
    MARCA
    Nome do Produto
    Emb. 750 ml
    1 L = 7.72
    nº4052
    5.79
    PVPR -46% 10.89
    Stock limitado

Padrão "invertido" (muito comum em frutas, legumes e produtos vendidos
ao quilo — descoberto ao investigar um caso real em que o Abacate
aparecia com o preço do Melão, e o Melão com o preço da Maçã Fuji):
    0.65
    0.89-26%
    Melão Verde
    Nacional
    Vendido ao kg
    nº75/ 80580

Ou seja, aqui o preço vem ANTES do nome, logo a seguir ao preço (e
código) do produto anterior — por isso, se só se olhar para "o
primeiro número a seguir ao código", o código de UM produto acaba
ligado ao preço do produto SEGUINTE por engano (o código está
fisicamente colado ao preço errado no texto extraído do PDF).

Estratégia (3 passagens, por ordem de prioridade):
1. Padrão invertido: procura-se primeiro o par bem específico e fiável
   "X.XX \n Y.YY-Z%" (preço final + preço anterior riscado + desconto).
   O nome é o texto que vem A SEGUIR a este par, até ao código deste
   mesmo produto. Esta zona de texto fica "reservada", para as
   passagens seguintes não lhe voltarem a mexer.
2. Padrão normal: código seguido do preço final, tal como descrito
   acima — mas ignorando qualquer código/preço que já tenha sido
   reservado pela passagem 1.
3. Casos residuais (ex: selo "Nº1 Qualidade Preço"): quando um código
   não tem preço nenhum a seguir, procura-se para trás o preço solto
   mais próximo (sem ultrapassar uma zona já reservada, e sem repetir
   um preço já usado por outro produto).

O preço por unidade ("1 kg = X.XX" ou "1 L = X.XX") é sempre procurado
na mesma janela de texto usada para o nome, antes de essa janela ser
limpa — e é ignorado como candidato a "preço final" nas passagens 2/3,
para não ser confundido com o preço do produto.
"""

import re

CODE_PRICE_RE = re.compile(r'nº[\d/\s]+?(\d+\.\d{2})', re.DOTALL)
CODIGO_RE = re.compile(r'nº[\d/\s]+')
PRECO_SOLTO_RE = re.compile(r'(\d+\.\d{2})')
UNIT_PRICE_RE = re.compile(r'1\s*(kg|[lL])\s*=\s*([\d]+[.,][\d]+)')

# NOVO: par "preço final + preço anterior-desconto%" que aparece ANTES
# do nome (ordem invertida) — comum em frutas/legumes/produtos ao kg.
PRECO_INVERTIDO_RE = re.compile(r'(\d+\.\d{2})\s*\n?\s*(\d+\.\d{2})-\d+%')

NOISE_RE = re.compile(
    r'-?\d+[.,]\d+\s*€?|PVPR|Stock limitado|Com Lidl Plus|Promoção|'
    r'Oportunidade\s+da\s+semana|PVP\s*\d+|-\s?\d+%|'
    r'Descobre\s+mais\s+no\s+nosso\s+folheto\s+especial\s+em\s+Lidl\.pt'
)
FIM_DO_NOME_RE = re.compile(r'\bEmb\.|\bVendido ao kg\b|\bVendido à unid\.|\bCada emb\.')
NOME_MAX_LEN = 90


def _preco_unidade(window: str):
    m = UNIT_PRICE_RE.search(window)
    if not m:
        return None
    unidade, valor = m.group(1).upper(), m.group(2).replace(".", ",")
    return f"{valor}€/{unidade}"


VENDIDO_AO_KG_RE = re.compile(r'Vendido ao kg', re.IGNORECASE)


def _preco_unidade_ou_vendido_ao_kg(window: str, price: str):
    unit_price = _preco_unidade(window)
    if unit_price:
        return unit_price
    if VENDIDO_AO_KG_RE.search(window):
        return f"{price.replace('.', ',')}€/KG"
    return None


def _limpar_nome(name_part, pegar_primeiro=False):
    pieces = [p for p in NOISE_RE.split(name_part) if p.strip() and len(p.strip()) > 2]
    if not pieces:
        return " ".join(name_part.split())
    escolhido = pieces[0] if pegar_primeiro else pieces[-1]
    return " ".join(escolhido.split())


def parse_products(pdf_text: str) -> list:
    products = []
    zonas_usadas = []

    # --- passagem 1: padrão invertido (preço ANTES do nome) ---
    invertidos = list(PRECO_INVERTIDO_RE.finditer(pdf_text))
    for i, m in enumerate(invertidos):
        price = m.group(1)
        fim = m.end()
        limite = invertidos[i + 1].start() if i + 1 < len(invertidos) else len(pdf_text)
        prox_codigo = CODIGO_RE.search(pdf_text, fim)
        if prox_codigo and prox_codigo.start() < limite:
            limite = prox_codigo.end()

        window = pdf_text[fim:limite]
        preco_unidade = _preco_unidade_ou_vendido_ao_kg(window, price)
        name_part = FIM_DO_NOME_RE.split(window)[0]
        name = _limpar_nome(name_part, pegar_primeiro=True)
        name = name[-NOME_MAX_LEN:].strip() if len(name) > NOME_MAX_LEN else name

        if name and len(name) > 2:
            products.append({"nome": name, "preco": price, "preco_unidade": preco_unidade})
            zonas_usadas.append((m.start(), limite))

    def em_zona_usada(pos):
        return any(a <= pos < b for a, b in zonas_usadas)

    # --- passagem 2: ordem normal (código -> preço a seguir) ---
    matches = [m for m in CODE_PRICE_RE.finditer(pdf_text) if not em_zona_usada(m.start(1))]
    fins_zonas = sorted(fim for (_, fim) in zonas_usadas)

    for i, m in enumerate(matches):
        price = m.group(1)
        fim_anterior = matches[i - 1].end() if i > 0 else 0
        # nunca recuar para antes do fim de uma zona já reservada pela
        # passagem 1, mesmo que o match anterior nesta lista (já
        # filtrada) fique bem mais atrás no texto
        fins_zona_antes = [f for f in fins_zonas if f <= m.start()]
        start_window = max([fim_anterior] + fins_zona_antes)
        window = pdf_text[start_window:m.start()]
        preco_unidade = _preco_unidade_ou_vendido_ao_kg(window, price)
        name_part = FIM_DO_NOME_RE.split(window)[0]
        name = _limpar_nome(name_part, pegar_primeiro=False)
        name = name[-NOME_MAX_LEN:].strip() if len(name) > NOME_MAX_LEN else name

        if name and len(name) > 2:
            products.append({"nome": name, "preco": price, "preco_unidade": preco_unidade})

    # --- passagem 3: código sem preço a seguir (casos residuais) ---
    precos_usados = set()
    for cm in CODIGO_RE.finditer(pdf_text):
        if em_zona_usada(cm.start()):
            continue
        if CODE_PRICE_RE.match(pdf_text, cm.start()):
            continue

        inicio = max(0, cm.start() - 250)
        fins_zona_antes = [f for f in fins_zonas if inicio <= f <= cm.start()]
        if fins_zona_antes:
            inicio = max(inicio, max(fins_zona_antes))
        trecho = pdf_text[inicio:cm.start()]

        # ignora números que sejam o "preço por kg/L" (ex: "1 kg = 0.74"),
        # para não confundir esse valor com o preço final do produto
        zonas_unidade = [u.span() for u in UNIT_PRICE_RE.finditer(trecho)]
        precos = [
            p for p in PRECO_SOLTO_RE.finditer(trecho)
            if not any(a <= p.start() < b for a, b in zonas_unidade)
            and (inicio + p.start()) not in precos_usados
        ]
        if not precos:
            continue

        price_match = precos[-1]
        price = price_match.group(1)
        window = trecho[precos[-1].end():]
        preco_unidade = _preco_unidade_ou_vendido_ao_kg(trecho, price)
        name_part = FIM_DO_NOME_RE.split(window)[0]

        pieces = [p for p in NOISE_RE.split(name_part) if p.strip() and len(p.strip()) > 2]
        if len(pieces) != 1:
            continue

        name = " ".join(pieces[0].split())
        name = name[-NOME_MAX_LEN:].strip() if len(name) > NOME_MAX_LEN else name

        if name and len(name) > 2:
            products.append({"nome": name, "preco": price, "preco_unidade": preco_unidade})
            precos_usados.add(inicio + price_match.start())

    return products


if __name__ == "__main__":
    from scraper_lidl import get_current_weekly_flyer, get_flyer_pdf_text

    flyer = get_current_weekly_flyer()
    print(f"Folheto: {flyer['name']} — {flyer['title']}")

    pdf_text = get_flyer_pdf_text(flyer)
    products = parse_products(pdf_text)

    print(f"Extraídos {len(products)} produtos em promoção.")
    for p in products[:15]:
        print(p)
