"""
Parser de produtos do Folheto da Aldi Portugal.

Recebe o texto de uma página (ver scraper_aldi.get_all_pages_text) e
devolve uma lista de produtos com nome e preço.

Descoberta chave: o preço promocional destacado é sempre escrito com
um espaço a seguir ao ponto decimal (ex: "1. 79", "9. 99"), o que o
distingue do preço "de" normal, escrito sem espaço (ex: "2.69"). Isto
serve de âncora fiável, tal como o padrão "X XX , € UNID." no
Continente.
"""

import re

# Preço promocional: "<inteiro>. <cêntimos>" com espaço a seguir ao ponto
PRICE_RE = re.compile(r'(\d{1,3})\.\s(\d{2})\b')

# Info de embalagem/venda: separa o nome do produto do resto dos detalhes
PACKAGING_RE = re.compile(r'\d+\s?(?:g|kg|ml|l)\s(?:embalagem|unidade)\b', re.IGNORECASE)

# Ruído comum: badges, percentagens de desconto, datas, texto promocional genérico
NOISE_RE = re.compile(
    r'CUSTA POUCO COMPRAR BEM|Preços válidos.*?existente\.?|'
    r'-?\d+\s?%|APROVEITA|SEMPRE DISPONÍVEL|POUPA|Seg\.|Dom\.|Sex\.|Sáb\.|'
    r'\d{1,2}\.\d{1,2}\b|\u200b'
)

NOME_MAX_LEN = 90


def parse_products(page_text: str) -> list[dict]:
    """Extrai produtos (nome, preço) do texto de uma página do folheto."""
    products = []
    matches = list(PRICE_RE.finditer(page_text))

    for i, m in enumerate(matches):
        price = f"{m.group(1)}.{m.group(2)}"
        start = matches[i - 1].end() if i > 0 else 0
        window = page_text[start:m.start()]

        name_part = PACKAGING_RE.split(window)[0]
        pieces = [p for p in NOISE_RE.split(name_part) if p.strip()]
        name = " ".join(pieces[-1].split()) if pieces else " ".join(name_part.split())
        name = name[-NOME_MAX_LEN:].strip() if len(name) > NOME_MAX_LEN else name

        if name and len(name) > 2:
            products.append({"nome": name, "preco": price})

    return products


def parse_all_pages(pages_text: list[str]) -> list[dict]:
    """Aplica parse_products a todas as páginas e junta os resultados."""
    all_products = []
    for page_text in pages_text:
        all_products.extend(parse_products(page_text))
    return all_products


if __name__ == "__main__":
    from scraper_aldi import (
        PAGINA_ESTA_SEMANA,
        PAGINA_PROXIMA_SEMANA,
        get_flyer_url,
        get_all_pages_text,
    )

    for nome, pagina_url in [
        ("esta semana", PAGINA_ESTA_SEMANA),
        ("próxima semana", PAGINA_PROXIMA_SEMANA),
    ]:
        print(f"\n=== Folheto da {nome} ===")
        flyer_url = get_flyer_url(pagina_url)
        pages_text = get_all_pages_text(flyer_url)
        produtos = parse_all_pages(pages_text)
        print(f"Extraídos {len(produtos)} produtos em promoção.")
        for p in produtos[:10]:
            print(p)
