from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[,.]\s*(\d{2})(?!\d)")
UNIT_RE = re.compile(
    r"(?:/|por\s*)(kg|g|l|lt|ml|cl|un(?:idade)?s?|emb(?:alagem)?s?)\b",
    re.I,
)
UNIT_PRICE_RE = re.compile(
    r"\b(\d{1,3}[,.]\d{2})\s*€?\s*/?\s*(kg|g|l|lt|ml|cl|un(?:idade)?s?|emb(?:alagem)?s?)\b",
    re.I,
)
NOISE = {
    "PROMOÇÃO", "PROMOCAO", "POUPE", "APROVEITE", "DESCONTO", "OFERTA",
    "PREÇO", "PRECO", "PVP", "PVPR", "CADA", "UNIDADE", "EMBALAGEM",
    "VENDIDO", "AO", "KG", "L", "ML", "G", "CL", "POR", "DE", "A",
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

    @property
    def cx(self) -> float:
        return self.left + self.width / 2

    @property
    def cy(self) -> float:
        return self.top + self.height / 2


@dataclass
class Badge:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def cx(self) -> float:
        return self.left + self.width / 2

    @property
    def cy(self) -> float:
        return self.top + self.height / 2


def _ocr_words(image: Image.Image) -> list[Word]:
    """OCR with coordinates; keep only reasonably confident words."""
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
        if conf < 20:
            continue
        words.append(
            Word(
                text=text,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                conf=conf,
            )
        )
    return words


def _price_value(text: str) -> float | None:
    text = text.replace("€", "").replace("EUR", "")
    m = PRICE_RE.search(text)
    if not m:
        return None
    value = float(f"{m.group(1)}.{m.group(2)}")
    return value if 0.10 <= value <= 999.99 else None


def _find_price_candidates(words: list[Word]) -> list[tuple[Word, float]]:
    """Find prices, including OCR-split forms such as '2 , 99'."""
    candidates: list[tuple[Word, float]] = []

    for w in words:
        value = _price_value(w.text)
        if value is not None:
            candidates.append((w, value))

    # Join only very close words on the same baseline. This prevents combining
    # unrelated prices from neighbouring products.
    for i, a in enumerate(words):
        for b in words[i + 1 :]:
            if abs(a.cy - b.cy) > max(a.height, b.height) * 0.8:
                continue
            if b.left < a.right:
                continue
            gap = b.left - a.right
            if gap > max(22, int(max(a.height, b.height) * 1.8)):
                continue
            combo = re.sub(r"\s+", "", f"{a.text}{b.text}").replace("€", "")
            value = _price_value(combo)
            if value is not None:
                candidates.append(
                    (
                        Word(
                            combo,
                            a.left,
                            min(a.top, b.top),
                            b.right - a.left,
                            max(a.bottom, b.bottom) - min(a.top, b.top),
                            min(a.conf, b.conf),
                        ),
                        value,
                    )
                )

    # Location-based deduplication.
    out: list[tuple[Word, float]] = []
    seen: set[tuple[int, int, int]] = set()
    for w, value in sorted(candidates, key=lambda x: (-x[0].height, x[0].top, x[0].left)):
        key = (round(w.cx / 12), round(w.cy / 12), round(value * 100))
        if key not in seen:
            seen.add(key)
            out.append((w, value))
    return out


def detect_price_badges(image: Image.Image) -> list[Badge]:
    """Find coloured price panels used as anchors in the Pingo Doce flyer.

    The exact colour can vary between pages. We therefore combine yellow/orange
    and red/pink saturation masks and keep medium-sized rectangular components.
    """
    rgb = np.array(image.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)

    masks = []
    # Yellow/orange highlights.
    masks.append(cv2.inRange(hsv, np.array([10, 75, 90]), np.array([45, 255, 255])))
    # Red/pink highlights (two hue ends in HSV).
    masks.append(cv2.inRange(hsv, np.array([0, 70, 80]), np.array([10, 255, 255])))
    masks.append(cv2.inRange(hsv, np.array([165, 70, 80]), np.array([179, 255, 255])))

    mask = masks[0]
    for m in masks[1:]:
        mask = cv2.bitwise_or(mask, m)

    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape
    badges: list[Badge] = []

    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        frac = area / float(w * h)
        if frac < 0.00008 or frac > 0.10:
            continue
        if cw < 28 or ch < 10:
            continue
        ratio = cw / float(ch)
        if ratio < 1.15 or ratio > 18:
            continue
        badges.append(Badge(x, y, cw, ch))

    return _dedupe_badges(badges)


def _dedupe_badges(badges: list[Badge]) -> list[Badge]:
    kept: list[Badge] = []
    for b in sorted(badges, key=lambda z: -(z.width * z.height)):
        duplicate = False
        for k in kept:
            ix = max(0, min(b.right, k.right) - max(b.left, k.left))
            iy = max(0, min(b.bottom, k.bottom) - max(b.top, k.top))
            inter = ix * iy
            union = b.width * b.height + k.width * k.height - inter
            if union and inter / union > 0.45:
                duplicate = True
                break
            # Also merge almost identical centres from different masks.
            if abs(b.cx - k.cx) < 0.15 * max(b.width, k.width) and abs(b.cy - k.cy) < 0.15 * max(b.height, k.height):
                duplicate = True
                break
        if not duplicate:
            kept.append(b)
    return sorted(kept, key=lambda z: (z.top, z.left))


def _badge_for_price(price_word: Word, badges: list[Badge], image_w: int, image_h: int) -> Badge | None:
    """Associate a price OCR box with the nearest colour badge."""
    best = None
    best_score = float("inf")
    for b in badges:
        # Price must be inside or immediately next to the coloured panel.
        dx = 0 if b.left <= price_word.cx <= b.right else min(abs(price_word.cx - b.left), abs(price_word.cx - b.right))
        dy = 0 if b.top <= price_word.cy <= b.bottom else min(abs(price_word.cy - b.top), abs(price_word.cy - b.bottom))
        dist = dx + dy
        max_dist = max(35, 0.035 * max(image_w, image_h))
        if dist > max_dist:
            continue
        score = dist + abs(b.width - max(price_word.width * 2, 40)) * 0.02
        if score < best_score:
            best_score = score
            best = b
    return best


def _is_price_word(w: Word) -> bool:
    return _price_value(w.text) is not None or bool(PRICE_RE.search(w.text))


def _clean_name(words: list[Word]) -> str:
    if not words:
        return ""
    # Remove obvious badges/units and join in visual reading order.
    ordered = sorted(words, key=lambda z: (z.top, z.left))
    parts: list[str] = []
    for w in ordered:
        text = w.text.strip(" |•·—-–_:;,.")
        upper = text.upper()
        if not text or len(text) <= 1 or upper in NOISE:
            continue
        if _is_price_word(w) or UNIT_RE.search(text):
            continue
        # Avoid obvious promotional labels.
        if re.fullmatch(r"\d+%?", text):
            continue
        parts.append(text)
    text = " ".join(parts)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.|")
    return text[:110]


def _name_near_badge(badge: Badge, words: list[Word], image_w: int, image_h: int) -> str:
    """Get words belonging to the same product card, not the whole page.

    Priority is given to the text immediately above the price badge and inside
    the same horizontal column. We intentionally use a narrow local window.
    """
    # Product names normally sit above the price. Allow a little text to the
    # right/left because some cards have wrapped names.
    x_margin = max(80, int(badge.width * 1.35))
    y_min = max(0, badge.top - max(260, int(image_h * 0.13)))
    y_max = badge.top + max(25, int(badge.height * 0.25))
    x_min = max(0, badge.left - x_margin)
    x_max = min(image_w, badge.right + x_margin)

    candidates: list[tuple[float, Word]] = []
    for w in words:
        if w.left < x_min or w.right > x_max or w.top < y_min or w.top > y_max:
            continue
        if _is_price_word(w) or UNIT_RE.search(w.text):
            continue
        t = w.text.strip(" |•·—-–_:;,.\n")
        if not t or len(t) <= 1 or t.upper() in NOISE:
            continue
        # Strong penalty for words far sideways from badge centre.
        dx = abs(w.cx - badge.cx) / max(1, badge.width)
        # Prefer text directly above the badge, but don't require a single line.
        gap = max(0, badge.top - w.bottom)
        if w.bottom > badge.top + badge.height * 0.5:
            continue
        score = gap * 1.0 + dx * 28
        if w.bottom <= badge.top:
            score *= 0.65
        candidates.append((score, w))

    candidates.sort(key=lambda x: x[0])
    # Select a compact group: don't take words that are much farther from the
    # best line than the first few candidates.
    chosen: list[Word] = []
    if candidates:
        best = candidates[0][0]
        for score, w in candidates:
            if len(chosen) >= 10:
                break
            if score > best + max(55, badge.height * 4):
                continue
            chosen.append(w)

    return _clean_name(chosen)


def _name_near_price_fallback(price_word: Word, words: list[Word], image_w: int, image_h: int) -> str:
    """Fallback when no colour badge is detected."""
    # Much narrower than the old global nearest-word approach.
    x_margin = max(100, int(image_w * 0.12))
    y_min = max(0, price_word.top - max(240, int(image_h * 0.12)))
    y_max = price_word.top + max(35, int(price_word.height * 1.5))
    candidates: list[tuple[float, Word]] = []
    for w in words:
        if w is price_word or w.left < price_word.left - x_margin or w.right > price_word.right + x_margin:
            continue
        if w.top < y_min or w.top > y_max:
            continue
        if _is_price_word(w) or UNIT_RE.search(w.text):
            continue
        t = w.text.strip(" |•·—-–_:;,.\n")
        if not t or len(t) <= 1 or t.upper() in NOISE:
            continue
        dy = max(0, price_word.top - w.bottom)
        dx = abs(w.cx - price_word.cx)
        candidates.append((dy * 1.0 + dx * 0.5, w))
    candidates.sort(key=lambda x: x[0])
    return _clean_name([w for _, w in candidates[:8]])


def _unit_price_near(badge: Badge, words: list[Word]) -> str | None:
    """Extract an explicit unit-price token close to the product card."""
    nearby = []
    for w in words:
        dx = abs(w.cx - badge.cx)
        dy = abs(w.cy - badge.cy)
        if dx > max(140, badge.width * 2.2) or dy > max(180, badge.height * 5):
            continue
        if UNIT_RE.search(w.text) or "/" in w.text:
            nearby.append(w)

    nearby.sort(key=lambda w: abs(w.cx - badge.cx) + abs(w.cy - badge.cy))
    for w in nearby:
        # First try the OCR token itself, then nearby words on same line.
        if UNIT_PRICE_RE.search(w.text):
            m = UNIT_PRICE_RE.search(w.text)
            return f"{m.group(1).replace(',', '.')} €/{m.group(2).lower()}"

        same_line = [
            z for z in nearby
            if abs(z.cy - w.cy) <= max(w.height, z.height) * 0.8
            and abs(z.cx - w.cx) <= max(180, badge.width * 2.5)
        ]
        text = " ".join(z.text for z in sorted(same_line, key=lambda z: z.left))
        m = UNIT_PRICE_RE.search(text)
        if m:
            return f"{m.group(1).replace(',', '.')} €/{m.group(2).lower()}"

    return None


def _dedupe_products(products: list[dict]) -> list[dict]:
    """Remove duplicate OCR detections while preserving distinct prices/cards."""
    out: list[dict] = []
    for p in products:
        name = re.sub(r"\s+", " ", p["nome"]).strip()
        if len(name) < 3:
            continue
        p["nome"] = name
        duplicate = False
        for q in out:
            # Same page, same price, and highly overlapping name = duplicate.
            if p["pagina"] != q["pagina"] or p["preco"] != q["preco"]:
                continue
            a = set(re.findall(r"[a-z0-9]+", name.lower()))
            b = set(re.findall(r"[a-z0-9]+", q["nome"].lower()))
            if not a or not b:
                continue
            similarity = len(a & b) / max(1, min(len(a), len(b)))
            if similarity >= 0.75:
                duplicate = True
                break
        if not duplicate:
            out.append(p)
    return out


def parse_page(image: Image.Image, page_number: int, use_color_anchors: bool = True) -> list[dict]:
    words = _ocr_words(image)
    prices = _find_price_candidates(words)
    badges = detect_price_badges(image) if use_color_anchors else []
    iw, ih = image.size
    products: list[dict] = []

    # When badges exist, one product is anchored to each badge. This is the
    # important difference from the previous parser: never choose a name by
    # looking at all words on the page.
    if badges:
        assigned_badges: set[int] = set()
        for price_word, price in prices:
            badge = _badge_for_price(price_word, badges, iw, ih)
            if badge is None:
                continue
            bi = badges.index(badge)
            if bi in assigned_badges:
                continue
            name = _name_near_badge(badge, words, iw, ih)
            if len(name) < 3:
                continue
            assigned_badges.add(bi)
            products.append({
                "pagina": page_number,
                "nome": name,
                "preco": round(price, 2),
                "preco_unidade": _unit_price_near(badge, words),
            })

    # Fallback: use price OCR only where no badge was available. It is kept
    # deliberately conservative rather than reintroducing page-wide mixing.
    if not products:
        for price_word, price in prices:
            name = _name_near_price_fallback(price_word, words, iw, ih)
            if len(name) < 3:
                continue
            products.append({
                "pagina": page_number,
                "nome": name,
                "preco": round(price, 2),
                "preco_unidade": None,
            })

    return _dedupe_products(products)


def parse_pdf(pdf_path: str | Path, render_dpi: int = 200,
              use_color_anchors: bool = True) -> list[dict]:
    import fitz

    doc = fitz.open(pdf_path)
    out: list[dict] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=render_dpi, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        out.extend(parse_page(image, i + 1, use_color_anchors=use_color_anchors))
    return out
