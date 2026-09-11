from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from folhetos.pingodoce.scraper_pingodoce import get_flyer_pdf_bytes
from folhetos.pingodoce.parser_pingodoce import parse_pdf

DATA_DIR = ROOT / "folhetos" / "dados" / "pingodoce"
TMP_DIR = ROOT / ".tmp" / "pingodoce"


def main() -> None:
    run_date = dt.date.today()
    pdf_bytes, flyer_url = get_flyer_pdf_bytes()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = TMP_DIR / "current.pdf"
    pdf_path.write_bytes(pdf_bytes)

    products = parse_pdf(pdf_path, render_dpi=170, use_color_anchors=True)
    payload = {
        "data_execucao": run_date.isoformat(),
        "supermercado": "Pingo Doce",
        "tipo_folheto": "Lojas Grandes",
        "folheto": {
            "url": flyer_url,
            "validade_aproximada": None,
        },
        "produtos": products,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{run_date.isoformat()}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Gravados {len(products)} registos em {out}")


if __name__ == "__main__":
    main()
