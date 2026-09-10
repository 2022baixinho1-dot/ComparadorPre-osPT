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

import io
import requests
from datetime import date
from pypdf import PdfReader

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}


def get_current_weekly_flyer_url() -> str:
    """Constrói o URL do folheto semanal atual a partir da semana ISO de hoje."""
    hoje = date.today()
    ano, semana, _ = hoje.isocalendar()
    return f"https://folhetos.pingodoce.pt/{ano}/poupe-esta-semana/continental-lojas-grandes/S{semana}/"


def get_flyer_pdf_text(flyer_url: str) -> str:
    """
    Descarrega o PDF do folheto via GetPDF.ashx (descoberto no DevTools —
    este endpoint redireciona automaticamente para o ficheiro PDF real com
    um token temporário) e devolve o texto de todas as páginas, junto.
    """
    pdf_download_url = flyer_url.rstrip("/") + "/GetPDF.ashx"
    resp = requests.get(pdf_download_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    reader = PdfReader(io.BytesIO(resp.content))
    paginas_texto = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(paginas_texto)


if __name__ == "__main__":
    flyer_url = get_current_weekly_flyer_url()
    print(f"URL do folheto: {flyer_url}")

    texto = get_flyer_pdf_text(flyer_url)
    print(f"Texto extraído: {len(texto)} caracteres.")
    print("\n--- Primeiros 1000 caracteres ---")
    print(texto[:1000])
