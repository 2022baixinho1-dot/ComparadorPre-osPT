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
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}


def get_current_weekly_flyer_url() -> str:
    """Constrói o URL do folheto semanal atual a partir da semana ISO de hoje."""
    hoje = date.today()
    ano, semana, _ = hoje.isocalendar()
    return f"https://folhetos.pingodoce.pt/{ano}/poupe-esta-semana/continental-lojas-grandes/S{semana}/"


def get_flyer_pdf_bytes(flyer_url: str) -> bytes:
    """Descarrega o PDF do folheto via GetPDF.ashx (descoberto no DevTools)."""
    pdf_download_url = flyer_url.rstrip("/") + "/GetPDF.ashx"
    resp = requests.get(pdf_download_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content


def get_flyer_pages_ocr_text(pdf_bytes: bytes, dpi: int = 200) -> list[str]:
    """
    Renderiza cada página do PDF como imagem e corre OCR (Tesseract, em
    português) sobre cada uma. Necessário porque o PDF do Pingo Doce não
    tem texto de produtos extraível diretamente — só imagens.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    textos = []

    zoom = dpi / 72  # o PDF assume 72 DPI por omissão
    matrix = fitz.Matrix(zoom, zoom)

    for pagina in doc:
        pix = pagina.get_pixmap(matrix=matrix)
        imagem = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        texto = pytesseract.image_to_string(imagem, lang="por")
        textos.append(texto)

    return textos


if __name__ == "__main__":
    flyer_url = get_current_weekly_flyer_url()
    print(f"URL do folheto: {flyer_url}")

    pdf_bytes = get_flyer_pdf_bytes(flyer_url)
    print(f"PDF descarregado: {len(pdf_bytes)} bytes.")

    textos = get_flyer_pages_ocr_text(pdf_bytes)
    print(f"OCR feito em {len(textos)} páginas.")

    for i in [0, 2, 5]:
        if i < len(textos):
            print(f"\n--- Página {i + 1} (OCR, primeiros 800 caracteres) ---")
            print(textos[i][:800])
