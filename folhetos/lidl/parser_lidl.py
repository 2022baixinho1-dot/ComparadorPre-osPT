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
"""

import re

# Preço final: primeiro decimal depois do código "nº..."
CODE_PRICE_RE = re.compile(r'nº[\d/\s]+?(\d+\.\d{2})', re.DOTALL)

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
