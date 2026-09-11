from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3})[,.](\d{2})(?!\d)")
UNIT_RE = re.compile(
    r"(?:/|por\s*)(kg|g|l|lt|ml|cl|un(?:idade)?s?|emb(?:alagem)?s?)",
    re.I,
)
NOISE = {
    "PROMOÇÃO", "PROMOCAO", "POUPE", "APROVEITE", "DESCONTO", "OFERTA",
    "PREÇO", "PRECO", "PVP", "PVPR", "CADA", "UNIDADE", "EMBALAGEM",
    "VENDIDO", "AO", "KG", "L", "ML", "G", "CL",
}


@dataclass
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass
class Badge:
    left: int
    top: int
    width: int
    height: int

    @property
    def cx(self) -> float:
        return self.left + self.width / 2

    @property
    def cy(self) -> float:
        return self.top + self.height / 2

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def _ocr_words(image: Image.Image) -> list[Word]:
    data = pytesseract.image_to_data(
        image,
        lang="por",
        config="--psm 11",
        output_type=pytesseract.Output.DICT,
    )
    words: list[Word] = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf < 25:
            continue
        words.append(Word(
            text=text,
            left=int(data["left"][i]),
            top=int(data["top"][i]),
            width=int(data["width"][i]),
            height=int(data["height"][i]),
            conf=conf,
        ))
    return words


def _price_value(text: str) -> float | None:
    m = PRICE_RE.search(text.replace("€", ""))
    if not m:
        return None
    return float(f"{m.group(1)}.{m.group(2)}")


def _find_price_candidates(words: list[Word]) -> list[tuple[Word, float]]:
    candidates: list[tuple[Word, float]] = []
    for w in words:
        value = _price_value(w.text)
        if value is not None and 0.10 <= value <= 999.99:
            candidates.append((w, value))
    # OCR often splits e.g. "2, 99" / "2 . 99". Join very close horizontal words.
    for a in words:
        for b in words:
            if b is a or abs(a.top - b.top) > max(a.height, b.height):
                continue
            gap = b.left - a.right
            if 0 <= gap <= max(18, int(a.height * 1.5)):
                combo = re.sub(r"\s+", "", f"{a.text}{b.text}").replace("€", "")
                value = _price_value(combo)
                if value is not None and 0.10 <= value <= 999.99:
                    candidates.append((Word(combo, a.left, min(a.top, b.top),
                                             b.right - a.left, max(a.bottom, b.bottom)-min(a.top,b.top),
                                             min(a.conf,b.conf)), value))
    # Deduplicate by location/value.
    seen = set()
    out = []
    for w, value in sorted(candidates, key=lambda x: (-x[0].height, x[0].left, x[0].top)):
        key = (round(w.left/8), round(w.top/8), round(value, 2))
        if key not in seen:
            seen.add(key)
            out.append((w, value))
    return out


def detect_price_badges(image: Image.Image) -> list[Badge]:
    """Detect strongly saturated/yellow price areas as visual anchors.

    This is deliberately conservative. It can be disabled from parse_pages()
    and the parser will then fall back to price-only OCR association.
    """
    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2HSV)
    # Broad yellow/orange band: the highlighted price cards used by the flyer.
    lower = np.array([15, 70, 100], dtype=np.uint8)
    upper = np.array([45, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(arr, lower, upper)
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h, w = mask.shape
    badges: list[Badge] = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        if area < (w * h) * 0.00015 or area > (w * h) * 0.12:
            continue
        if cw < 35 or ch < 12:
            continue
        ratio = cw / ch
        if ratio < 1.1 or ratio > 14:
            continue
        badges.append(Badge(x, y, cw, ch))
    return _dedupe_badges(badges)


def _dedupe_badges(badges: list[Badge]) -> list[Badge]:
    kept: list[Badge] = []
    for b in sorted(badges, key=lambda z: -(z.width*z.height)):
        overlap = False
        for k in kept:
            ix = max(0, min(b.right,k.right)-max(b.left,k.left))
            iy = max(0, min(b.bottom,k.bottom)-max(b.top,k.top))
            inter = ix*iy
            union = b.width*b.height + k.width*k.height - inter
            if union and inter/union > 0.45:
                overlap = True
                break
        if not overlap:
            kept.append(b)
    return sorted(kept, key=lambda z: (z.top, z.left))


def _text_near_price(price_word: Word, words: list[Word], image_w: int, image_h: int,
                     badge: Badge | None = None) -> str:
    # A product name is usually above/left of the price. Use a bounded window
    # and a score that strongly favours same-column words.
    anchor_x = badge.cx if badge else price_word.left + price_word.width/2
    anchor_y = badge.top if badge else price_word.top
    candidates = []
    for w in words:
        if w is price_word:
            continue
        if PRICE_RE.search(w.text):
            continue
        t = w.text.strip(" |•·—-–_:")
        if not t or len(t) <= 1 or t.upper() in NOISE:
            continue
        # Mostly above the price, with some room to the sides.
        dy = anchor_y - (w.top + w.height)
        dx = abs((w.left+w.width/2) - anchor_x)
        if dy < -45 or dy > image_h * 0.25:
            continue
        if dx > image_w * 0.35:
            continue
        score = abs(dy) * 0.8 + dx * 0.45
        if w.top < anchor_y:
            score *= 0.65
        candidates.append((score, w))
    candidates.sort(key=lambda x: x[0])
    chosen: list[Word] = []
    for _, w in candidates[:18]:
        chosen.append(w)
    chosen.sort(key=lambda z: (z.top, z.left))
    text = " ".join(w.text for w in chosen)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.")
    # Avoid swallowing long page prose.
    return text[:120]


def parse_page(image: Image.Image, page_number: int, use_color_anchors: bool = True) -> list[dict]:
    words = _ocr_words(image)
    prices = _find_price_candidates(words)
    badges = detect_price_badges(image) if use_color_anchors else []
    products: list[dict] = []
    used = set()
    iw, ih = image.size

    for price_word, price in prices:
        badge = min(badges, key=lambda b: abs(b.cx-(price_word.left+price_word.width/2)) + abs(b.cy-(price_word.top+price_word.height/2))*0.8, default=None)
        if badge:
            dist = abs(badge.cx-(price_word.left+price_word.width/2)) + abs(badge.cy-(price_word.top+price_word.height/2))
            if dist > max(iw, ih) * 0.10:
                badge = None
        name = _text_near_price(price_word, words, iw, ih, badge)
        if not name:
            continue
        key = (page_number, round(price_word.left/10), round(price_word.top/10), price)
        if key in used:
            continue
        used.add(key)
        unit = None
        # Look for a nearby explicit unit-price token.
        for w in words:
            if w.top < price_word.top - 220 or w.top > price_word.bottom + 220:
                continue
            if UNIT_RE.search(w.text):
                unit = w.text
                break
        products.append({
            "pagina": page_number,
            "nome": name,
            "preco": round(price, 2),
            "preco_unidade": unit,
        })
    return products


def parse_pdf(pdf_path: str | Path, render_dpi: int = 170,
              use_color_anchors: bool = True) -> list[dict]:
    import fitz
    doc = fitz.open(pdf_path)
    out: list[dict] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=render_dpi, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        out.extend(parse_page(image, i + 1, use_color_anchors=use_color_anchors))
    return out
