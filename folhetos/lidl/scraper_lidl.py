"""
Scraper do(s) Folheto(s) do Lidl Portugal.

Apanha todos os folhetos nacionais ainda válidos (semanais + fim de
semana, atual e seguinte) e classifica cada um usando o campo `name`
do PRÓPRIO FOLHETO ("Promoções Semanais" vs "Promoções Fim-de-Semana")
— não o `title`. O `title` (ex: "A partir de 07/09") repete-se entre o
folheto semanal e o de fim de semana com a mesma data de início, o que
tornava a deteção por título ambígua e causava colisão de nomes de
ficheiro.

Também restringe a folhetos com início recente, para não apanhar
catálogos "evergreen" antigos (ex: "Ferramentas e Bricolage" de 2022)
que a API devolve com offerEndDate no futuro distante.

Continua a usar a mesma infraestrutura pública do grupo Schwarz
(endpoints.leaflets.schwarz), sem necessidade de login.

Dependências: requests, pypdf
    pip install requests pypdf
"""

import io
import requests
from datetime import date, timedelta
from pypdf import PdfReader

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ComparadorPrecosPT/1.0)"}
OVERVIEW_URL = "https://endpoints.leaflets.schwarz/v4/overview"

# Janela de datas de início aceites: exclui catálogos antigos/"evergreen"
# mas continua a apanhar o folheto semanal atual + o da próxima semana,
# e o de fim de semana atual + o do próximo (tipicamente 4 no total).
DIAS_PASSADO_MAX = 10
DIAS_FUTURO_MAX = 21

# Palavras-chave que identificam "fim de semana" no campo `name` do
# folheto (ex: "Promoções Fim-de-Semana").
PALAVRAS_FIM_DE_SEMANA = ("fim de semana", "fim-de-semana", "weekend", "fds")


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
    """
    Classifica um folheto como 'fim-de-semana' ou 'semanal' usando o
    campo `name` do PRÓPRIO FOLHETO ("Promoções Semanais" vs
    "Promoções Fim-de-Semana") — confirmado por inspeção direta da API.
    O `title` não serve para isto: é igual ("A partir de 07/09") tanto
    para o folheto semanal como para o de fim de semana com a mesma
    data de início.
    """
    nome = flyer.get("name", "").lower()

    if any(palavra in nome for palavra in PALAVRAS_FIM_DE_SEMANA):
        return "fim-de-semana"
    return "semanal"


def get_folhetos_nacionais_validos() -> list[dict]:
    """
    Devolve os folhetos nacionais recentes (offerStartDate dentro da
    janela DIAS_PASSADO_MAX/DIAS_FUTURO_MAX) e cujo período de oferta
    ainda não terminou — tipicamente 4: semanal atual, semanal
    seguinte, fim de semana atual e fim de semana seguinte.
    """
    hoje = date.today()
    hoje_str = hoje.isoformat()
    limite_passado = (hoje - timedelta(days=DIAS_PASSADO_MAX)).isoformat()
    limite_futuro = (hoje + timedelta(days=DIAS_FUTURO_MAX)).isoformat()

    flyers = get_all_flyers()

    validos = [
        f for f in flyers
        if any(r.get("type") == "national" for r in f.get("regions", []))
        and f.get("offerEndDate", "0000-00-00") >= hoje_str
        and limite_passado <= f.get("offerStartDate", "0000-00-00") <= limite_futuro
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
        print(f"  [{f['_categoria']}] {f['name']} — {f['title']} — válido {f['offerStartDate']} a {f['offerEndDate']}")
