import datetime as dt
import io
import re
from pathlib import Path

import requests

BASE = "https://folhetos.pingodoce.pt"
TIMEOUT = 60


def current_iso_week(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.isocalendar().week


def build_flyer_url(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    week = current_iso_week(today)
    return (
        f"{BASE}/{today.year}/poupe-esta-semana/"
        f"continental-lojas-grandes/S{week}/"
    )


def get_flyer_pdf_bytes(session: requests.Session | None = None,
                        flyer_url: str | None = None) -> tuple[bytes, str]:
    """Download the official Pingo Doce 'Lojas Grandes' flyer PDF.

    The iPaper viewer exposes the PDF through <flyer_url>GetPDF.ashx and
    redirects to a temporary Download.pdf URL. We intentionally keep the
    original flyer URL in the returned metadata.
    """
    session = session or requests.Session()
    flyer_url = flyer_url or build_flyer_url()
    pdf_endpoint = flyer_url.rstrip("/") + "/GetPDF.ashx"

    r = session.get(
        pdf_endpoint,
        timeout=TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ComparadorPre-osPT/1.0)"},
        allow_redirects=True,
    )
    r.raise_for_status()
    content_type = (r.headers.get("Content-Type") or "").lower()
    if not r.content.startswith(b"%PDF") and "pdf" not in content_type:
        raise RuntimeError(
            "O endpoint do Pingo Doce não devolveu um PDF. "
            f"URL final: {r.url} | Content-Type: {content_type}"
        )
    return r.content, flyer_url


def save_pdf(pdf_bytes: bytes, output_dir: str | Path, run_date: dt.date | None = None) -> Path:
    run_date = run_date or dt.date.today()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{run_date:%Y-%m-%d}.pdf"
    path.write_bytes(pdf_bytes)
    return path
