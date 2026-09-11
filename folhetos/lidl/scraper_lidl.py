"""
Scraper do(s) Folheto(s) do Lidl Portugal.

Atualização: em vez de escolher só UM folheto semanal nacional, esta
versão apanha TODOS os folhetos nacionais que ainda não expiraram
(offerEndDate >= hoje) — isto inclui tipicamente 2 folhetos "semanais"
(o atual e o da próxima semana) e 2 "fim de semana" (o atual e o do
próximo), num total de 4.

Continua a usar a mesma infraestrutura pública do grupo Schwarz
(endpoints.leaflets.schwarz), sem necessidade de login.

Dependências: requests, pypdf
    pip install requests pypdf
"""

import io
import requests
from datetime import date
from pypdf import PdfReader

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}
OVERVIEW_URL = "https://endpoints.leaflets.schwarz/v4/overview"


def get_all_flyers() -> list[dict]:
    """Devolve a lista completa (achatada) de folhetos ativos do Lidl Portugal."""
    params = {"client_locale": "lidl/pt-PT"}
    resp = requests.get(OVERVIEW_URL, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    flyers = []
    for category in data.get("categories", []):
        for subcategory in category.get("subcategories", []):
            flyers.extend(subcategory.get("flyers", []))
    return flyers


def _categoria(flyer: dict) -> str:
    """Classifica um folheto como 'fim-de-semana' ou 'semanal', pelo título."""
    titulo = (flyer.get("title") or "").lower()
    if "fim de semana" in titulo or "fim-de-semana" in titulo:
        return "fim-de-semana"
    return "semanal"


def get_folhetos_nacionais_validos() -> list[dict]:
    """
    Devolve TODOS os folhetos nacionais cujo período de oferta ainda não
    terminou (inclui o atual e o(s) seguinte(s) já publicados, tanto
    semanais como de fim de semana).
    """
    hoje = date.today().isoformat()
    flyers = get_all_flyers()

    validos = [
        f for f in flyers
        if any(r.get("type") == "national" for r in f.get("regions", []))
        and f.get("offerEndDate", "0000-00-00") >= hoje
    ]

    if not validos:
        raise RuntimeError("Não encontrei nenhum folheto nacional válido (atual ou futuro).")

    for f in validos:
        f["_categoria"] = _categoria(f)

    return validos


def get_flyer_pdf_text(flyer: dict) -> str:
    """Descarrega o PDF do folheto e devolve o texto de todas as páginas, junto."""
    resp = requests.get(flyer["pdfUrl"], headers=HEADERS, timeout=60)
    resp.raise_for_status()

    reader = PdfReader(io.BytesIO(resp.content))
    paginas_texto = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(paginas_texto)


if __name__ == "__main__":
    folhetos = get_folhetos_nacionais_validos()
    print(f"Encontrados {len(folhetos)} folhetos nacionais válidos:")
    for f in folhetos:
        print(f"  [{f['_categoria']}] {f['title']} — válido {f['offerStartDate']} a {f['offerEndDate']}")
