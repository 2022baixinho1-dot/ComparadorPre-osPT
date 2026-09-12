"""
Parser de produtos do Folheto Semanal do Continente.

Recebe o texto em bruto de uma página (tal como devolvido por
scraper.get_all_pages_text) e devolve uma lista de produtos com:
- nome
- preco (preço promocional, em euros)
- preco_unidade (€/KG, €/L, etc., quando existir)

Nota: o texto do folheto mistura texto de produtos com badges
promocionais genéricos (ex: "Até 30% Desconto Direto" aplicado a uma
categoria, não a um produto específico). Isto significa que uma
pequena percentagem dos nomes pode ficar com texto residual a mais
no fim. Para efeitos de comparação de preços entre supermercados,
isto não impede a correspondência (o preço e a maior parte do nome
estão corretos).

Produtos vendidos ao quilo (ex: "Apenas 4,99€ KG BIFANAS DE PORCO"):
o preço mostrado já É o preço por kg — o folheto não repete essa
informação à parte. Nesses casos, quando não há um preço por unidade
explícito no texto, usa-se o próprio preço como preco_unidade.
"""

import re

# Preço final destacado no folheto: aparece sempre como
# "<inteiro> <cêntimos> , € <unidade>", ex: "3 39 , € UNID."
PRICE_RE = re.compile(r'(\d{1,3})\s+(\d{2})\s*,\s*€\s*(KG|UNID\.)')

# Preço por unidade, ex: "4,52€/L" ou "12,17€/KG"
UNIT_PRICE_RE = re.compile(r'([\d,]+)\s*€/(KG|L|CÁPSULA|DOSE|UNID|ROLO)')

# Marcadores que indicam o início do badge do PRÓXIMO produto (ou de
# texto genérico), usados para cortar o nome do produto atual.
STOP_MARKERS = re.compile(
    r'(\d+,\d+\s*€|Desconto Direto|Sobre PVPR|Apenas\b|Mais de\b|Até\b|Poupe\b|Leve\b|PVPR\b|\. )'
)

# Comprimento máximo razoável para o nome de um produto — acima disto
# é quase certo que apanhámos texto descritivo/marketing a mais.
NOME_MAX_LEN = 90


def parse_products(page_text: str) -> list[dict]:
    """Extrai produtos (nome, preço, preço/unidade) do texto de uma página."""
    products = []
    matches = list(PRICE_RE.finditer(page_text))

    for i, m in enumerate(matches):
        price = f"{m.group(1)},{m.group(2)}"
        end_of_price = m.end()
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(page_text)
        window = page_text[end_of_price:next_start]

        # o nome termina antes de "EMB.:" / "GARRAFA:" (info de embalagem)
        window_before_pack = re.split(r'\bEMB\.:|\bGARRAFA:', window)[0]

        # e termina também antes do primeiro marcador do próximo badge
        stop = STOP_MARKERS.search(window_before_pack)
        name = window_before_pack[:stop.start()] if stop else window_before_pack
        name = name.strip(" ,")[:NOME_MAX_LEN].strip(" ,")

        unit_price_match = UNIT_PRICE_RE.search(window)
        if unit_price_match:
            unit_price = f"{unit_price_match.group(1)}€/{unit_price_match.group(2)}"
        elif m.group(3) == "KG":
            # produto vendido ao quilo (ex: "Apenas 4,99€ KG BIFANAS...") —
            # o preço mostrado JÁ é o preço por kg, o folheto não o repete.
            unit_price = f"{price}€/KG"
        else:
            unit_price = None

        # ignora entradas sem nome (normalmente ruído de badges genéricos)
        if name and len(name) > 2:
            products.append({
                "nome": name,
                "preco": price,
                "preco_unidade": unit_price,
            })

    return products


def parse_all_pages(pages_text: list[str]) -> list[dict]:
    """Aplica parse_products a todas as páginas e junta os resultados."""
    all_products = []
    for page_text in pages_text:
        all_products.extend(parse_products(page_text))
    return all_products


if __name__ == "__main__":
    from scraper import get_current_weekly_flyer_url, get_all_pages_text

    flyer_url = get_current_weekly_flyer_url()
    pages_text = get_all_pages_text(flyer_url)
    products = parse_all_pages(pages_text)

    print(f"Extraídos {len(products)} produtos em promoção.")
    for p in products[:15]:
        print(p)
