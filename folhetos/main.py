from datetime import date, timedelta


def _segunda_feira_da_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


def guardar_historico(flyer_url: str, produtos: list[dict]) -> str:
    """Guarda os produtos extraídos num ficheiro JSON com a data de hoje."""
    os.makedirs(DADOS_DIR, exist_ok=True)

    hoje_date = date.today()
    hoje = hoje_date.isoformat()  # ex: "2026-09-09"
    segunda = _segunda_feira_da_semana(hoje_date)
    valido_de = segunda.isoformat()
    valido_ate = (segunda + timedelta(days=6)).isoformat()

    # anexa a validade (assumida: semana corrida, segunda a domingo) a
    # cada produto, para a página web mostrar sem ter de adivinhar
    produtos_com_validade = [
        {**p, "valido_de": valido_de, "valido_ate": valido_ate} for p in produtos
    ]

    caminho = os.path.join(DADOS_DIR, f"{hoje}.json")
    conteudo = {
        "data_execucao": hoje,
        "url_folheto": flyer_url,
        "total_produtos": len(produtos_com_validade),
        "produtos": produtos_com_validade,
    }

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)

    caminho_latest = os.path.join(DADOS_DIR, "latest.json")
    with open(caminho_latest, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)

    return caminho
