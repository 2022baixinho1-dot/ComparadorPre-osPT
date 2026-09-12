from datetime import timedelta


def _segunda_feira_da_semana(d) -> str:
    return (d - timedelta(days=d.weekday())).isoformat()


if __name__ == "__main__":
    hoje_date = date.today()
    hoje = hoje_date.isoformat()
    segunda = _segunda_feira_da_semana(hoje_date)
    todos_produtos = []

    for nome_periodo, pagina_url in [
        ("esta semana", PAGINA_ESTA_SEMANA),
        ("proxima semana", PAGINA_PROXIMA_SEMANA),
    ]:
        print(f"\n=== Folheto da {nome_periodo} ===")
        flyer_url = get_flyer_url(pagina_url)
        pages_text = get_all_pages_text(flyer_url)
        produtos = parse_all_pages(pages_text)

        if nome_periodo == "esta semana":
            valido_de = segunda
        else:
            from datetime import date as _date
            valido_de = (_date.fromisoformat(segunda) + timedelta(days=7)).isoformat()
        valido_ate = (
            __import__("datetime").date.fromisoformat(valido_de) + timedelta(days=6)
        ).isoformat()
        produtos = [{**p, "valido_de": valido_de, "valido_ate": valido_ate} for p in produtos]
        todos_produtos.extend(produtos)

        os.makedirs(DADOS_DIR, exist_ok=True)
        sufixo = "esta-semana" if nome_periodo == "esta semana" else "proxima-semana"
        caminho = os.path.join(DADOS_DIR, f"{hoje}-{sufixo}.json")
        conteudo = {
            "data_execucao": hoje,
            "periodo": nome_periodo,
            "url_folheto": flyer_url,
            "total_produtos": len(produtos),
            "produtos": produtos,
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False, indent=2)
        print(f"Histórico guardado em: {caminho}")

    caminho_latest = os.path.join(DADOS_DIR, "latest.json")
    conteudo_latest = {
        "data_execucao": hoje,
        "total_produtos": len(todos_produtos),
        "produtos": todos_produtos,
    }
    with open(caminho_latest, "w", encoding="utf-8") as f:
        json.dump(conteudo_latest, f, ensure_ascii=False, indent=2)
    print(f"Latest combinado guardado em: {caminho_latest}")
