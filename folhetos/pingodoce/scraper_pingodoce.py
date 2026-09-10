"""
Scraper do Folheto do Pingo Doce.

Descoberta técnica: o Pingo Doce usa a mesma plataforma iPaper que o
Continente e a Aldi. O URL do folheto tem o formato previsível:

    https://folhetos.pingodoce.pt/<ano>/poupe-esta-semana/continental-lojas-grandes/S<semana>/

onde <semana> é o número da semana ISO do ano (ex: S37). Ao contrário
do Continente, este URL não tem sufixo aleatório, por isso pode ser
CONSTRUÍDO diretamente a partir da data de hoje, sem precisar de uma
página-índice para o descobrir.

Nota: esta construção direta do URL é uma assunção por testar — se a
Pingo Doce mudar o nome da campanha ("poupe-esta-semana") ou o formato
de loja ("continental-lojas-grandes"), o URL deixa de ser válido e é
preciso rever isto (nesse caso, procurar de novo uma página-índice,
tal como se fez para o Continente).

Dependências: requests
    pip install requests
"""

import json
import re
import requests
from datetime import date

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}


def get_current_weekly_flyer_url() -> str:
    """Constrói o URL do folheto semanal atual a partir da semana ISO de hoje."""
    hoje = date.today()
    ano, semana, _ = hoje.isocalendar()
    return f"https://folhetos.pingodoce.pt/{ano}/poupe-esta-semana/continental-lojas-grandes/S{semana}/"


def get_all_pages_text(flyer_url: str) -> list[str]:
    """Faz um único pedido ao folheto e extrai o campo 'pageTexts' embutido no HTML."""
    resp = requests.get(flyer_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    match = re.search(r'"pageTexts":(\[.*?\]),"device"', resp.text, re.DOTALL)
    if match is None:
        raise RuntimeError(
            f"Não encontrei 'pageTexts' em {flyer_url}. "
            "O URL construído pode estar errado (nome da campanha ou "
            "formato de loja pode ter mudado) — é preciso confirmar "
            "manualmente o URL correto do folheto desta semana."
        )
    return json.loads(match.group(1))


if __name__ == "__main__":
    flyer_url = get_current_weekly_flyer_url()
    print(f"URL construído: {flyer_url}")

    pages_text = get_all_pages_text(flyer_url)
    print(f"Extraídas {len(pages_text)} páginas de texto.")

    for i in [0, 2, 5]:
        if i < len(pages_text):
            print(f"\n--- Página {i + 1} (1000 primeiros caracteres) ---")
            print(pages_text[i][:1000])
