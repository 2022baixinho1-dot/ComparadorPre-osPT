from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[,.:]\s*(\d{2})(?!\d)")
EURO_PRICE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*€\s*(\d{2})(?!\d)")
UNIT_RE = re.compile(r"(?:/|por\s*)(kg|g|l|lt|ml|cl|un(?:idade)?s?|emb(?:alagem)?s?)\b", re.I)
NOISE = {
    "PROMOÇÃO", "PROMOCAO", "POUPE", "APROVEITE", "DESCONTO", "OFERTA",
    "PREÇO", "PRECO", "PVP", "PVPR", "CADA", "UNIDADE", "EMBALAGEM",
    "VENDIDO", "AO", "KG", "L", "ML", "G", "CL", "UNID", "UNID.",
    "PINGO", "DOCE", "€", "EUR", "TODOS", "TODAS", "SABORES", "VARIEDADES",
}
BAD_FRAGMENT = re.compile(r"^[\W_\d]+$|^(?:unid|emb|cada)$", re.I)

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


def _ocr_words(image: Image.Image, psm: int = 11, min_conf: float = 32) -> list[Word]:
    data = pytesseract.image_to_data(image, lang="por", config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    out = []
    for i, text0 in enumerate(data["text"]):
        text = (text0 or "").strip()
        if not text: continue
        try: conf = float(data["conf"][i])
        except (TypeError, ValueError): conf = -1
        if conf < min_conf: continue
        out.append(Word(text, int(data["left"][i]), int(data["top"][i]), int(data["width"][i]),
                        int(data["height"][i]), conf, int(data["block_num"][i]), int(data["par_num"][i]),
                        int(data["line_num"][i])))
    return out


def _price_value(text: str) -> float | None:
    t = text.replace("EUR", "").replace("€", "")
    matches = list(PRICE_RE.finditer(t))
    if not matches:
        matches = list(EURO_PRICE_RE.finditer(text))
    if len(matches) != 1:
        return None
    m = matches[0]
    value = float(f"{m.group(1)}.{m.group(2)}")
    if not (0.10 <= value <= 199.99): return None
    # OCR frequently merges a second price or a unit price into the same token.
    digits = re.sub(r"\D", "", text)
    if len(digits) > 5 and value < 100: return None
    if value >= 100 and value != 159.0: return None
    return value


def _find_price_candidates(words: list[Word]) -> list[tuple[Word, float]]:
    candidates: list[tuple[Word, float]] = []
    for w in words:
        value = _price_value(w.text)
        if value is not None:
            candidates.append((w, value))

    # Join only genuinely adjacent OCR fragments (e.g. "2" + ",99").
    for i, a in enumerate(words):
        for b in words[i + 1:]:
            if b.left < a.left: continue
            if abs(a.cy - b.cy) > max(a.height, b.height) * 0.55: continue
            gap = b.left - a.right
            if gap < 0 or gap > max(12, int(max(a.height, b.height) * 0.9)): continue
            combo = f"{a.text}{b.text}".replace(" ", "")
            if len(re.sub(r"\D", "", combo)) > 5: continue
            value = _price_value(combo)
            if value is not None:
                candidates.append((Word(combo, a.left, min(a.top, b.top), b.right-a.left,
                                        max(a.bottom, b.bottom)-min(a.top, b.top), min(a.conf,b.conf),
                                        a.block,a.par,a.line), value))

    # Same price within a small area is almost always one OCR detection, not two products.
    kept: list[tuple[Word, float]] = []
    for w, value in sorted(candidates, key=lambda z: -z[0].conf):
        if any(abs(w.cx-k.cx) < max(22, w.width*.35) and abs(w.cy-k.cy) < max(22, w.height*.8)
               and abs(value-kv) < .01 for k, kv in kept):
            continue
        kept.append((w, value))
    return kept


def detect_price_badges(image: Image.Image) -> list[Badge]:
    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2HSV)
    # Yellow/orange price stickers. Keep components compact: large page decorations are rejected.
    mask = cv2.inRange(arr, np.array([10, 70, 90], np.uint8), np.array([50, 255, 255], np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5,5), np.uint8), iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape
    badges=[]
    for c in contours:
        x,y,cw,ch=cv2.boundingRect(c); area=cw*ch
        if area < w*h*0.00008 or area > w*h*0.035: continue
        if cw < 28 or ch < 9: continue
        ratio=cw/ch
        if 1.15 <= ratio <= 14:
            badges.append(Badge(x,y,cw,ch))
    return _dedupe_badges(badges)


def _dedupe_badges(badges: list[Badge]) -> list[Badge]:
    kept=[]
    for b in sorted(badges,key=lambda z: -(z.width*z.height)):
        if any(_iou(b,k) > .40 for k in kept): continue
        kept.append(b)
    return kept


def _iou(a: Badge,b: Badge) -> float:
    ix=max(0,min(a.right,b.right)-max(a.left,b.left)); iy=max(0,min(a.bottom,b.bottom)-max(a.top,b.top))
    inter=ix*iy; union=a.width*a.height+b.width*b.height-inter
    return inter/union if union else 0


def _clean_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -:;,.|•·—–_=")
    text = re.sub(r"\b\d{1,3}\s*[,. :]\s*\d{2}\s*€?\b", " ", text)
    text = re.sub(r"\b\d{1,2}\s*[x×]\s*\d+[a-zA-Z]*\b", lambda m: m.group(0), text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.|")
    return text[:120]


def _is_good_name(text: str) -> bool:
    t=_clean_name(text)
    if len(t) < 8: return False
    words=re.findall(r"[A-Za-zÀ-ÿ]{2,}",t)
    meaningful=[w for w in words if w.upper() not in NOISE and not BAD_FRAGMENT.match(w)]
    if len(meaningful) < 2: return False
    # Reject text dominated by OCR junk / numbers.
    if sum(ch.isdigit() for ch in t) / max(1,len(t)) > .28: return False
    return True


def _zone_for_badge(badge: Badge, badges: list[Badge], iw: int, ih: int) -> tuple[int,int,int,int]:
    """Create a Voronoi-like product cell around a price badge.
    Neighbouring price stickers define hard boundaries, preventing OCR from
    borrowing names from the next product.
    """
    same_row=[b for b in badges if abs(b.cy-badge.cy) < max(ih*.12, badge.height*7)]
    left_neigh=[b for b in same_row if b.cx < badge.cx]
    right_neigh=[b for b in same_row if b.cx > badge.cx]
    x1=(max((b.cx for b in left_neigh), default=0)+badge.cx)/2
    x2=(min((b.cx for b in right_neigh), default=iw)+badge.cx)/2
    # Do not let a very wide cell swallow the whole page.
    half=max(140, min(iw*.24, (x2-x1)/2))
    x1=max(0,int(badge.cx-half)); x2=min(iw,int(badge.cx+half))

    # Product text is normally above the price; include a moderate amount below for unit info.
    y1=max(0,int(badge.top-ih*.20))
    y2=min(ih,int(badge.bottom+ih*.08))
    return x1,y1,x2,y2


def _name_from_zone(zone: Image.Image, badge: Badge | None = None) -> str | None:
    # First OCR with a sparse layout, then line-aware OCR if needed.
    words=_ocr_words(zone, psm=6, min_conf=28)
    if not words: return None
    if badge:
        # badge coordinates are relative to the full page; convert approximately via crop later not needed here.
        pass
    # Remove price-looking fragments and obvious promo boilerplate.
    clean=[]
    for w in words:
        if _price_value(w.text) is not None: continue
        t=w.text.strip("|•·—-_:;,.=")
        if not t or t.upper() in NOISE: continue
        clean.append(w)
    if not clean: return None

    # Prefer the upper text rows. The price sticker is near the bottom of the zone.
    max_top=max(w.top for w in clean)
    min_top=min(w.top for w in clean)
    cutoff=min_top + (max_top-min_top)*0.72
    upper=[w for w in clean if w.top <= cutoff]
    if len(upper) < 2: upper=clean

    # Rebuild lines, preserving spatial order.
    lines=[]
    for w in sorted(upper,key=lambda z:(z.top,z.left)):
        if not lines or abs(w.cy-lines[-1][0].cy)>max(w.height,lines[-1][0].height)*.75:
            lines.append([w])
        else: lines[-1].append(w)
    lines=[sorted(line,key=lambda z:z.left) for line in lines]
    # Usually the product title is the last 1-3 coherent lines immediately above the price.
    lines=lines[-4:]
    text=" ".join(w.text for line in lines for w in line)
    text=_clean_name(text)
    return text if _is_good_name(text) else None


def _ocr_zone_direct(zone: Image.Image) -> tuple[str|None,float|None,str|None]:
    """Independent OCR of one product cell; this is the main extraction path."""
    # Upscale helps small flyer typography.
    scale=1.6
    img=zone.resize((int(zone.width*scale), int(zone.height*scale)), Image.Resampling.LANCZOS)
    words=_ocr_words(img, psm=6, min_conf=24)
    if not words: return None,None,None
    prices=_find_price_candidates(words)
    if not prices: return None,None,None
    # Choose the strongest price, preferring the lower part of the cell.
    pw,price=max(prices,key=lambda z:(z[0].cy/img.height, z[0].conf))

    nonprice=[]
    for w in words:
        if w is pw or _price_value(w.text) is not None: continue
        t=w.text.strip("|•·—-_:;,.=")
        if not t or t.upper() in NOISE: continue
        nonprice.append(w)
    if not nonprice: return None,None,None

    # Product name = coherent lines above the price, with a strict vertical window.
    above=[w for w in nonprice if w.bottom <= pw.top + max(20,pw.height*.8) and pw.top-w.bottom <= img.height*.55]
    if not above: above=nonprice
    lines=[]
    for w in sorted(above,key=lambda z:(z.top,z.left)):
        if not lines or abs(w.cy-lines[-1][0].cy)>max(w.height,lines[-1][0].height)*.7:
            lines.append([w])
        else: lines[-1].append(w)
    lines=[sorted(line,key=lambda z:z.left) for line in lines]
    # Avoid pulling tiny fragments from distant lines.
    selected=lines[-3:]
    text=" ".join(w.text for line in selected for w in line)
    text=_clean_name(text)
    if not _is_good_name(text): return None,None,None
    unit=None
    for w in nonprice:
        m=UNIT_RE.search(w.text)
        if m: unit=w.text
    return text,price,unit


def parse_page(image: Image.Image, page_number: int, use_color_anchors: bool=True) -> list[dict]:
    iw,ih=image.size
    badges=detect_price_badges(image) if use_color_anchors else []
    products=[]

    # Primary path: each price sticker defines one product cell. OCR is performed
    # independently per cell, so neighbouring products cannot contaminate the name.
    if badges:
        for b in sorted(badges,key=lambda z:(z.top,z.left)):
            x1,y1,x2,y2=_zone_for_badge(b,badges,iw,ih)
            zone=image.crop((x1,y1,x2,y2))
            name,price,unit=_ocr_zone_direct(zone)
            if name is None or price is None: continue
            products.append({"pagina":page_number,"nome":name,"preco":round(price,2),"preco_unidade":unit})

    # Conservative fallback only if there were no usable colour anchors.
    if not products and not badges:
        words=_ocr_words(image)
        for pw,price in _find_price_candidates(words):
            # tiny local crop around price, not the whole page
            x1=max(0,int(pw.left-220)); x2=min(iw,int(pw.right+220))
            y1=max(0,int(pw.top-260)); y2=min(ih,int(pw.bottom+80))
            name,_,unit=_ocr_zone_direct(image.crop((x1,y1,x2,y2)))
            if name:
                products.append({"pagina":page_number,"nome":name,"preco":round(price,2),"preco_unidade":unit})

    return _dedupe_products(products)


def _norm(s:str)->str:
    return re.sub(r"[^a-z0-9]+","",s.lower())


def _dedupe_products(products:list[dict])->list[dict]:
    out=[]
    for p in products:
        n=_norm(p["nome"])
        duplicate=False
        for q in out:
            if p["pagina"]!=q["pagina"]: continue
            if abs(p["preco"]-q["preco"])>.01: continue
            qn=_norm(q["nome"])
            a=set(re.findall(r"[a-z0-9]{3,}",n)); b=set(re.findall(r"[a-z0-9]{3,}",qn))
            sim=len(a&b)/max(1,min(len(a),len(b)))
            if sim>=.70 or (abs(len(n)-len(qn))<8 and n[:22]==qn[:22]):
                duplicate=True; break
        if not duplicate: out.append(p)
    return out


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
