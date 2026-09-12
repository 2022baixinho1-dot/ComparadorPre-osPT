"""
Parser de produtos do Folheto Semanal do Lidl Portugal.

Recebe o texto extraído do PDF do folheto (ver scraper_lidl.get_flyer_pdf_text)
e devolve uma lista de produtos com nome e preço.

Padrão típico de cada produto no texto do PDF:
    MARCA
    Nome do Produto
    Emb. 750 ml
    1 L = 7.72
    nº4052
    5.79
    PVPR -46% 10.89
    Stock limitado

Estratégia: ancorar no preço final, que é sempre o primeiro número
decimal a aparecer depois do código "nº...". O nome do produto é o
texto que vem antes disso, depois de remover ruído (preços residuais
e badges do produto anterior, que por vezes ficam colados por causa
da ordem de leitura do PDF).

Exceção: produtos em destaque com o selo "Nº1 Qualidade Preço" têm
uma ordem invertida — o preço aparece ANTES do nome e do código, não
depois. Para esses casos, uma segunda passagem procura o preço solto
que precede imediatamente o nome, sem texto de ruído pelo meio (para
não confundir com o preço de outro produto mais distante no texto).
"""

import re

# Preço final: primeiro decimal depois do código "nº..."
CODE_PRICE_RE = re.compile(r'nº[\d/\s]+?(\d+\.\d{2})', re.DOTALL)

# Qualquer ocorrência de um código "nº...", com ou sem preço a seguir.
CODIGO_RE = re.compile(r'nº[\d/\s]+')

# Um preço "solto", sem contexto de código associado.
PRECO_SOLTO_RE = re.compile(r'(\d+\.\d{2})')

# Ruído comum entre produtos: preços residuais, percentagens, badges e
# frases promocionais genéricas que não fazem parte do nome do produto.
NOISE_RE = re.compile(
    r'-?\d+[.,]\d+\s*€?|PVPR|Stock limitado|Com Lidl Plus|Promoção|'
    r'Oportunidade\s+da\s+semana|PVP\s*\d+|-\s?\d+%|'
    r'Descobre\s+mais\s+no\s+nosso\s+folheto\s+especial\s+em\s+Lidl\.pt'
)

# O nome termina sempre antes de uma destas palavras (info de embalagem
# ou modo de venda).
FIM_DO_NOME_RE = re.compile(r'\bEmb\.|\bVendido ao kg\b|\bCada emb\.')

# Comprimento máximo razoável — acima disto é quase certo que apanhámos
# texto legal de rodapé (repete-se em todas as páginas) em vez do nome.
NOME_MAX_LEN = 90


def parse_products(pdf_text: str) -> list[dict]:
    """Extrai produtos (nome, preço) do texto extraído do PDF do folheto."""
    products = []
    matches = list(CODE_PRICE_RE.finditer(pdf_text))

    for i, m in enumerate(matches):
        price = m.group(1)
        start_window = matches[i - 1].end() if i > 0 else 0
        window = pdf_text[start_window:m.start()]

        name_part = FIM_DO_NOME_RE.split(window)[0]
        pieces = [p for p in NOISE_RE.split(name_part) if p.strip()]
        name = " ".join(pieces[-1].split()) if pieces else " ".join(name_part.split())
        name = name[-NOME_MAX_LEN:].strip() if len(name) > NOME_MAX_LEN else name

        if name and len(name) > 2:
            products.append({"nome": name, "preco": price})

    # 2ª passagem: produtos em destaque, onde o preço vem antes do nome.
    for cm in CODIGO_RE.finditer(pdf_text):
        if CODE_PRICE_RE.match(pdf_text, cm.start()):
            continue  # já foi apanhado na 1ª passagem

        inicio = max(0, cm.start() - 250)
        trecho = pdf_text[inicio:cm.start()]
        precos = list(PRECO_SOLTO_RE.finditer(trecho))
        if not precos:
            continue

        price = precos[-1].group(1)
        window = trecho[precos[-1].end():]

        name_part = FIM_DO_NOME_RE.split(window)[0]
        pieces = [p for p in NOISE_RE.split(name_part) if p.strip()]

        # só aceita quando não há ruído a mais entre o preço e o nome
        # (evita apanhar por engano um preço de um produto mais distante,
        # como acontece em referências/banners genéricos no folheto)
        if len(pieces) != 1:
            continue

        name = " ".join(pieces[0].split())
        name = name[-NOME_MAX_LEN:].strip() if len(name) > NOME_MAX_LEN else name

        if name and len(name) > 2:
            products.append({"nome": name, "preco": price})

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
