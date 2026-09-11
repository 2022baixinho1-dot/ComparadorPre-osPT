from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[,.]\s*(\d{2})(?!\d)")
INTEGER_CENTS_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[€£]\s*(\d{2})(?!\d)")
UNIT_RE = re.compile(r"(?:/|por\s*)(kg|g|l|lt|ml|cl|un(?:idade)?s?|emb(?:alagem)?s?)\b", re.I)
BAD_NAME = re.compile(r"^(?:[€£]?\s*\d+[,.]?\d*|unid(?:ade)?|emb(?:alagem)?|cada)$", re.I)
NOISE = {
    "PROMOÇÃO", "PROMOCAO", "POUPE", "APROVEITE", "DESCONTO", "OFERTA",
    "PREÇO", "PRECO", "PVP", "PVPR", "CADA", "UNIDADE", "EMBALAGEM",
    "VENDIDO", "AO", "KG", "L", "ML", "G", "CL", "UNID", "UNID.",
    "PINGO", "DOCE", "€", "EUR",
}

@dataclass
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    block: int = -1
    par: int = -1
    line: int = -1

    @property
    def right(self): return self.left + self.width
    @property
    def bottom(self): return self.top + self.height
    @property
    def cx(self): return self.left + self.width / 2
    @property
    def cy(self): return self.top + self.height / 2

@dataclass
class Badge:
    left: int; top: int; width: int; height: int
    @property
    def right(self): return self.left + self.width
    @property
    def bottom(self): return self.top + self.height
    @property
    def cx(self): return self.left + self.width / 2
    @property
    def cy(self): return self.top + self.height / 2


def _ocr_words(image: Image.Image) -> list[Word]:
    data = pytesseract.image_to_data(image, lang="por", config="--psm 11", output_type=pytesseract.Output.DICT)
    out = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text: continue
        try: conf = float(data["conf"][i])
        except (TypeError, ValueError): conf = -1
        if conf < 32: continue
        out.append(Word(text, int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i]), conf,
                        int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i])))
    return out


def _price_value(text: str) -> float | None:
    t = text.replace("€", "").replace("EUR", "")
    m = PRICE_RE.search(t) or INTEGER_CENTS_RE.search(text)
    if not m: return None
    value = float(f"{m.group(1)}.{m.group(2)}")
    # Folheto promo: reject implausible OCR values and common merged numbers.
    if not (0.10 <= value <= 199.99): return None
    if value >= 100 and value != 159.0: return None
    return value


def _find_price_candidates(words: list[Word]) -> list[tuple[Word, float]]:
    candidates = []
    # Single OCR tokens.
    for w in words:
        value = _price_value(w.text)
        if value is not None: candidates.append((w, value))
    # Join only short tokens on the same line: 2 + ,99 / 2 + .99 / 2 + 99€.
    for i, a in enumerate(words):
        for b in words[i+1:]:
            if b.top > a.bottom + max(a.height, b.height): continue
            if abs(a.cy - b.cy) > max(a.height, b.height) * 0.8: continue
            gap = b.left - a.right
            if gap < 0 or gap > max(14, int(max(a.height,b.height)*1.2)): continue
            combo = f"{a.text}{b.text}".replace(" ", "")
            value = _price_value(combo)
            if value is not None:
                candidates.append((Word(combo, a.left, min(a.top,b.top), b.right-a.left,
                                        max(a.bottom,b.bottom)-min(a.top,b.top), min(a.conf,b.conf), a.block,a.par,a.line), value))
    # Keep the strongest candidate per small location bucket.
    best = {}
    for w, value in candidates:
        key = (round(w.cx/18), round(w.cy/18), round(value,2))
        if key not in best or w.conf > best[key][0].conf: best[key] = (w, value)
    return list(best.values())


def detect_price_badges(image: Image.Image) -> list[Badge]:
    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2HSV)
    # Pingo Doce price cards are often yellow/orange; keep this conservative.
    mask = cv2.inRange(arr, np.array([12, 75, 105], np.uint8), np.array([48, 255, 255], np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5,5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape
    badges=[]
    for c in contours:
        x,y,cw,ch=cv2.boundingRect(c); area=cw*ch
        if area < w*h*0.00012 or area > w*h*0.10: continue
        if cw < 30 or ch < 10: continue
        ratio=cw/ch
        if 1.05 <= ratio <= 16: badges.append(Badge(x,y,cw,ch))
    return _dedupe_badges(badges)


def _dedupe_badges(badges):
    kept=[]
    for b in sorted(badges,key=lambda z: -(z.width*z.height)):
        duplicate=False
        for k in kept:
            ix=max(0,min(b.right,k.right)-max(b.left,k.left)); iy=max(0,min(b.bottom,k.bottom)-max(b.top,k.top))
            inter=ix*iy; union=b.width*b.height+k.width*k.height-inter
            if union and inter/union>0.45: duplicate=True; break
        if not duplicate: kept.append(b)
    return kept


def _clean_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -:;,.|•·—–")
    text = re.sub(r"\b(?:\d{1,3}\s*[,.]\s*\d{2})\s*€?\b", " ", text)
    text = re.sub(r"\b\d{1,2}\s*[x×]\s*\d+[a-zA-Z]*\b", lambda m: m.group(0), text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.|")
    return text[:100]


def _is_good_name(text: str) -> bool:
    t = _clean_name(text)
    if not t or len(t) < 6 or BAD_NAME.match(t): return False
    words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", t)
    if len(words) < 2: return False
    meaningful = [w for w in words if w.upper() not in NOISE]
    if len(meaningful) < 2: return False
    digit_ratio = sum(ch.isdigit() for ch in t) / max(1,len(t))
    return digit_ratio < 0.30


def _name_for_price(price_word: Word, words: list[Word], badge: Badge | None, iw: int, ih: int) -> str | None:
    # Anchor to the visual price card when available. The product name is normally
    # above it and in the same horizontal cell. Avoid a wide page-wide search.
    ax = badge.cx if badge else price_word.cx
    ay = badge.top if badge else price_word.top
    bw = badge.width if badge else max(price_word.width * 4, 180)
    left_bound = max(0, ax - bw*1.15)
    right_bound = min(iw, ax + bw*1.15)
    top_bound = max(0, ay - min(ih*0.22, 430))
    bottom_bound = ay + max(35, price_word.height*2)
    cand=[]
    for w in words:
        if w is price_word: continue
        if PRICE_RE.search(w.text) or INTEGER_CENTS_RE.search(w.text): continue
        txt=w.text.strip(" |•·—-–_:")
        if not txt or len(txt)<=1 or txt.upper() in NOISE: continue
        if not (left_bound <= w.cx <= right_bound and top_bound <= w.cy <= bottom_bound): continue
        # Prefer words in same OCR line/block and above the price.
        dx=abs(w.cx-ax); dy=ay-w.bottom
        if dy < -25: continue
        score=dx*0.8 + abs(dy)*0.35
        if w.top < ay: score*=0.35
        if badge and b_overlap(w,badge): score*=0.75
        if w.block == price_word.block: score*=0.75
        cand.append((score,w))
    cand.sort(key=lambda x:x[0])
    chosen=[]
    # Take nearby lines, but stop before crossing a likely neighbouring product column.
    for _,w in cand[:24]:
        chosen.append(w)
    chosen.sort(key=lambda z:(z.top,z.left))
    # Build line groups; discard isolated OCR fragments.
    lines=[]
    for w in chosen:
        if not lines or abs(w.cy-lines[-1][0].cy) > max(w.height, lines[-1][0].height)*0.75:
            lines.append([w])
        else: lines[-1].append(w)
    lines=[sorted(line,key=lambda z:z.left) for line in lines]
    text=" ".join(w.text for line in lines for w in line)
    text=_clean_name(text)
    if not _is_good_name(text): return None
    return text


def b_overlap(w: Word,b: Badge):
    ix=max(0,min(w.right,b.right)-max(w.left,b.left)); iy=max(0,min(w.bottom,b.bottom)-max(w.top,b.top))
    return ix*iy > 0


def _unit_price(price_word: Word, words: list[Word], badge: Badge|None):
    ax=badge.cx if badge else price_word.cx; ay=badge.cy if badge else price_word.cy
    best=None
    for w in words:
        m=UNIT_RE.search(w.text)
        if not m: continue
        d=abs(w.cx-ax)+abs(w.cy-ay)*1.3
        if d < 260 and (best is None or d<best[0]): best=(d,w.text)
    return best[1] if best else None


def parse_page(image: Image.Image, page_number: int, use_color_anchors: bool=True) -> list[dict]:
    words=_ocr_words(image); prices=_find_price_candidates(words)
    badges=detect_price_badges(image) if use_color_anchors else []
    products=[]; seen=[]; iw,ih=image.size
    for pw,price in prices:
        badge=min(badges,key=lambda b: abs(b.cx-pw.cx)+abs(b.cy-pw.cy),default=None)
        if badge and abs(badge.cx-pw.cx)+abs(badge.cy-pw.cy) > max(iw,ih)*0.08: badge=None
        name=_name_for_price(pw,words,badge,iw,ih)
        if not name: continue
        # De-duplicate products with same price/name or nearly identical anchor.
        norm=re.sub(r"[^a-z0-9]+","",name.lower())
        if any(p[0]==norm and abs(p[1]-price)<0.01 for p in seen): continue
        seen.append((norm,price))
        products.append({"pagina":page_number,"nome":name,"preco":round(price,2),"preco_unidade":_unit_price(pw,words,badge)})
    return products


def parse_pdf(pdf_path: str|Path, render_dpi: int=200, use_color_anchors: bool=True) -> list[dict]:
    import pymupdf
    doc=pymupdf.open(pdf_path)
    out=[]
    for i,page in enumerate(doc):
        pix=page.get_pixmap(dpi=render_dpi,alpha=False)
        image=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
        out.extend(parse_page(image,i+1,use_color_anchors=use_color_anchors))
    doc.close()
    return out
