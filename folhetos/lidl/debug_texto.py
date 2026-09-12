"""
Script TEMPORÁRIO de diagnóstico — não faz parte do projeto, serve só
para ver o texto tal como sai do PDF do Lidl à volta de "Abacate", e
perceber porque é que o preço aparece trocado com o de outro produto.

Pode ser apagado depois de resolvido o problema do desalinhamento de
preços (ver conversa com o Claude).
"""

from scraper_lidl import get_folhetos_nacionais_validos, get_flyer_pdf_text

folhetos = get_folhetos_nacionais_validos()
for flyer in folhetos:
    pdf_text = get_flyer_pdf_text(flyer)
    if "Abacate" in pdf_text:
        i = pdf_text.find("Abacate")
        print(f"=== [{flyer['_categoria']}] {flyer['title']} ===")
        # janela bem maior: 200 antes, 2000 depois — para apanhar
        # também o Melão e a Maçã Fuji que vêm a seguir na mesma zona
        print(repr(pdf_text[max(0, i - 200): i + 2000]))
        print()
