"""
Script TEMPORÁRIO de diagnóstico — não faz parte do projeto, serve só
para ver o texto tal como sai do PDF do Lidl à volta de "Abacate", e
perceber porque é que o preço aparece trocado com o de outro produto.

Pode ser apagado depois de resolvido o problema do desalinhamento de
preços (ver conversa com o Claude).
"""

from scraper_lidl import get_folhetos_nacionais_validos, get_flyer_pdf_text

folhetos = get_folhetos_nacionais_validos()
print(f"Encontrados {len(folhetos)} folhetos:")
for f in folhetos:
    print(f"  [{f['_categoria']}] {f['title']} — válido {f.get('offerStartDate')} a {f.get('offerEndDate')}")
print()

for flyer in folhetos:
    pdf_text = get_flyer_pdf_text(flyer)
    if "Alcobaça" in pdf_text:
        i = pdf_text.find("Alcobaça")
        print(f"=== [{flyer['_categoria']}] {flyer['title']} — válido {flyer.get('offerStartDate')} a {flyer.get('offerEndDate')} ===")
        print(repr(pdf_text[max(0, i - 400): i + 400]))
        print()
