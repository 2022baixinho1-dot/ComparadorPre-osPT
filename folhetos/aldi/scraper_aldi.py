"""
Scraper do Folheto da Aldi Portugal (esta semana + próxima semana).

Descoberta técnica: a Aldi usa a mesma plataforma iPaper que o
Continente. As páginas https://www.aldi.pt/folheto/esta-semana.html e
.../proxima-semana.html são uma app JavaScript, mas o HTML em bruto
que devolvem já contém, embutido, o URL real do folheto no site
"folhetos.aldi.pt" (campo apiData). A partir desse URL, aplica-se a
mesma técnica do Continente: a página do folheto embute o texto de
todas as páginas em "pageTexts", num único pedido HTTP.

Dependências: requests
    pip install requests
"""

import json
import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}

PAGINA_ESTA_SEMANA = "https://www.aldi.pt/folheto/esta-semana.html"
PAGINA_PROXIMA_SEMANA = "https://www.aldi.pt/folheto/proxima-semana.html"


def get_flyer_url(pagina_url: str) -> str:
    """
    Vai a uma das páginas (esta-semana.html / proxima-semana.html) e
    extrai o URL real do folheto em folhetos.aldi.pt, embutido no HTML.
    """
    resp = requests.get(pagina_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    match = re.search(r'https://folhetos\.aldi\.pt/[^"\\\s]+/', resp.text)
    if match is None:
        raise RuntimeError(
            f"Não encontrei o URL do folheto em {pagina_url}. "
            "É provável que a Aldi tenha mudado a estrutura da página."
        )
    return match.group(0)


def get_all_pages_text(flyer_url: str) -> list[str]:
    """Faz um único pedido ao folheto e extrai o campo 'pageTexts' embutido no HTML."""
    resp = requests.get(flyer_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    match = re.search(r'"pageTexts":(\[.*?\]),"device"', resp.text, re.DOTALL)
    if match is None:
        raise RuntimeError(
            f"Não encontrei 'pageTexts' em {flyer_url}. "
            "É provável que a estrutura da página tenha mudado."
        )
    return json.loads(match.group(1))


if __name__ == "__main__":
    for nome, pagina_url in [
        ("esta semana", PAGINA_ESTA_SEMANA),
        ("próxima semana", PAGINA_PROXIMA_SEMANA),
    ]:
        print(f"\n=== Folheto da {nome} ===")
        flyer_url = get_flyer_url(pagina_url)
        print(f"URL: {flyer_url}")

        pages_text = get_all_pages_text(flyer_url)
        print(f"Extraídas {len(pages_text)} páginas de texto.")
        print("Primeiros 300 caracteres da página 1:")
        print(pages_text[0][:300])
