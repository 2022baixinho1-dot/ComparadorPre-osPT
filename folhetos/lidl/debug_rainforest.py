import re
from scraper_lidl import get_folhetos_nacionais_validos, get_flyer_pdf_text

folhetos = get_folhetos_nacionais_validos()
for flyer in folhetos:
    pdf_text = get_flyer_pdf_text(flyer)
    for m in re.finditer(r'Rainforest', pdf_text):
        start = max(0, m.start() - 300)
        end = min(len(pdf_text), m.end() + 300)
        print(f"--- Folheto {flyer.get('_categoria')} {flyer.get('offerStartDate')} ---")
        print(repr(pdf_text[start:end]))
        print()
