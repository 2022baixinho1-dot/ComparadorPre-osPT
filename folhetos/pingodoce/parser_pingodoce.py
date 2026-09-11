from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps, ImageFilter

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[,.:]\s*(\d{2})(?!\d)")
EURO_PRICE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*€\s*(\d{2})(?!\d)")
UNIT_RE = re.compile(r"(?:/|por\s*)(kg|g|l|lt|ml|cl|un(?:idade)?s?|emb(?:alagem)?s?)\b", re.I)
NOISE = {
    "PROMOÇÃO", "PROMOCAO", "POUPE", "APROVEITE", "DESCONTO", "OFERTA",
    "PREÇO", "PRECO", "PVP", "PVPR", "CADA", "UNIDADE", "EMBALAGEM",
    "VENDIDO", "AO", "KG", "L", "ML", "G", "CL", "UNID", "UNID.",
    "PINGO", "DOCE", "€", "EUR", "TODOS", "TODAS", "SABORES", "VARIEDADES",
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


def _ocr_words(image: Image.Image, psm: int = 11, min_conf: float = 25, lang: str = "por") -> list[Word]:
    data = pytesseract.image_to_data(image, lang=lang, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    out = []
    for i, text0 in enumerate(data["text"]):
        text = (text0 or "").strip()
        if not text:
            continue
        try: conf = float(data["conf"][i])
        except (TypeError, ValueError): conf = -1
        if conf < min_conf:
            continue
        out.append(Word(text, int(data["left"][i]), int(data["top"][i]), int(data["width"][i]),
                        int(data["height"][i]), conf, int(data["block_num"][i]),
                        int(data["par_num"][i]), int(data["line_num"][i])))
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
    if not (0.10 <= value <= 199.99):
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) > 5 and value < 100:
        return None
    # Evita leituras absurdas dos elementos gráficos. 159€ é uma exceção
    # observada para pequenos eletrodomésticos.
    if value >= 60 and value not in (159.0, 159.99):
        return None
    return value


def _price_candidates(words: list[Word]) -> list[tuple[Word, float]]:
    out = []
    for w in words:
        v = _price_value(w.text)
        if v is not None:
            out.append((w, v))
    # Junta apenas tokens realmente adjacentes na mesma linha.
    for i, a in enumerate(words):
        for b in words[i + 1:]:
            if b.left < a.left or abs(a.cy - b.cy) > max(a.height, b.height) * .5:
                continue
            gap = b.left - a.right
            if gap < 0 or gap > max(10, int(max(a.height, b.height) * .9)):
                continue
            combo = f"{a.text}{b.text}".replace(" ", "")
            v = _price_value(combo)
            if v is not None:
                out.append((Word(combo, a.left, min(a.top, b.top), b.right-a.left,
                                 max(a.bottom, b.bottom)-min(a.top, b.top), min(a.conf,b.conf)), v))
    # Dedup espacial.
    kept = []
    for w, v in sorted(out, key=lambda z: -z[0].conf):
        if any(abs(w.cx-k.cx) < max(18, w.width*.35) and abs(w.cy-k.cy) < max(18,w.height*.8)
               and abs(v-kv) < .01 for k,kv in kept):
            continue
        kept.append((w,v))
    return kept


def detect_price_badges(image: Image.Image) -> list[Badge]:
    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2HSV)
    # Âmbar/amarelo/vermelho-alaranjado usado nos destaques de preço.
    mask = cv2.inRange(arr, np.array([7, 75, 85], np.uint8), np.array([48, 255, 255], np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7,7), np.uint8), iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h,w = mask.shape
    raw=[]
    for c in contours:
        x,y,cw,ch=cv2.boundingRect(c)
        area=cw*ch
        if area < w*h*0.00005 or area > w*h*0.025:
            continue
        if cw < 22 or ch < 8:
            continue
        ratio=cw/ch
        if 1.1 <= ratio <= 18:
            raw.append(Badge(x,y,cw,ch))
    return _dedupe_badges(raw)


def _iou(a: Badge,b: Badge) -> float:
    ix=max(0,min(a.right,b.right)-max(a.left,b.left)); iy=max(0,min(a.bottom,b.bottom)-max(a.top,b.top))
    inter=ix*iy; union=a.width*a.height+b.width*b.height-inter
    return inter/union if union else 0


def _dedupe_badges(badges: list[Badge]) -> list[Badge]:
    kept=[]
    for b in sorted(badges,key=lambda z: -(z.width*z.height)):
        if any(_iou(b,k)>.35 for k in kept):
            continue
        kept.append(b)
    return sorted(kept,key=lambda b:(b.cy,b.cx))


def _clean_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -:;,.|•·—–_=")
    text = re.sub(r"\b\d{1,3}\s*[,.:]\s*\d{2}\s*€?\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.|")
    return text[:120]


def _is_good_name(text: str) -> bool:
    t=_clean_name(text)
    if len(t)<8:
        return False
    words=re.findall(r"[A-Za-zÀ-ÿ]{2,}",t)
    meaningful=[w for w in words if w.upper() not in NOISE]
    if len(meaningful)<2:
        return False
    if sum(ch.isdigit() for ch in t)/max(1,len(t))>.20:
        return False
    if sum(ch.isalpha() for ch in t)<8:
        return False
    if _price_value(t) is not None:
        return False
    return True


def _line_groups(words: list[Word]) -> list[list[Word]]:
    """Agrupa palavras pela geometria, sem confiar no line_num do Tesseract."""
    lines=[]
    for w in sorted(words,key=lambda z:(z.cy,z.left)):
        placed=False
        for line in reversed(lines[-5:]):
            ref=line[0]
            tol=max(5, min(w.height,ref.height)*.65)
            if abs(w.cy-ref.cy)<=tol:
                line.append(w); placed=True; break
        if not placed:
            lines.append([w])
    return [sorted(x,key=lambda z:z.left) for x in lines]


def _line_box(line: list[Word]) -> tuple[int,int,int,int]:
    return min(w.left for w in line), min(w.top for w in line), max(w.right for w in line), max(w.bottom for w in line)


def _h_overlap(a1,a2,b1,b2):
    return max(0,min(a2,b2)-max(a1,b1))


def _badge_price_from_crop(image: Image.Image, b: Badge) -> tuple[float|None, float]:
    """OCR dedicado ao próprio sticker; retorna preço e confiança aproximada."""
    pad_x=max(8,int(b.width*.12)); pad_y=max(8,int(b.height*.25))
    x1=max(0,b.left-pad_x); y1=max(0,b.top-pad_y); x2=min(image.width,b.right+pad_x); y2=min(image.height,b.bottom+pad_y)
    crop=image.crop((x1,y1,x2,y2))
    scale=3.0
    crop=crop.resize((int(crop.width*scale),int(crop.height*scale)),Image.Resampling.LANCZOS)
    variants=[crop, ImageOps.grayscale(crop), ImageOps.autocontrast(ImageOps.grayscale(crop))]
    best=None
    for v in variants:
        data=pytesseract.image_to_data(v,config="--psm 7 -c tessedit_char_whitelist=0123456789,.€",output_type=pytesseract.Output.DICT)
        for i,t0 in enumerate(data['text']):
            t=(t0 or '').strip()
            val=_price_value(t)
            if val is None: continue
            try: conf=float(data['conf'][i])
            except: conf=0
            if best is None or conf>best[1]: best=(val,conf)
    return best if best else (None,0.0)


def _name_for_badge(image: Image.Image, badge: Badge, words: list[Word], badges: list[Badge]) -> tuple[str|None,str|None]:
    """Escolhe linhas de texto próximas do preço, usando distância + sobreposição.

    Isto substitui o crop gigante: cada preço só pode receber texto que esteja
    geometricamente na sua própria faixa/cartão.
    """
    # Limites horizontais derivados dos preços vizinhos na mesma linha.
    row=[b for b in badges if abs(b.cy-badge.cy)<max(45,b.height*5)]
    left=max((b.right for b in row if b.cx<badge.cx), default=0)
    right=min((b.left for b in row if b.cx>badge.cx), default=image.width)
    # Margem pequena: suficiente para títulos mas não para o cartão seguinte.
    gap=max(20,int((right-left)*.035))
    x1=int(max(left+gap, badge.cx-(right-left)*.43))
    x2=int(min(right-gap, badge.cx+(right-left)*.43))
    if x2-x1<120:
        x1=max(0,int(badge.cx-max(140,badge.width*3.8)))
        x2=min(image.width,int(badge.cx+max(140,badge.width*3.8)))

    # Texto só acima do preço e num raio curto.
    candidates=[]
    for line in _line_groups(words):
        lx,ly,rx,ry=_line_box(line)
        if ry > badge.top + max(8,int(badge.height*.35)):
            continue
        overlap=_h_overlap(lx,rx,x1,x2)
        if overlap < max(12,int((rx-lx)*.18)):
            continue
        dy=badge.top-ry
        if dy<0 or dy>max(230,int(image.height*.055)):
            continue
        useful=[]
        for w in line:
            t=w.text.strip("|•·—-_:;,.=")
            if not t or t.upper() in NOISE or _price_value(t) is not None:
                continue
            # palavra tem de estar dentro da faixa do preço.
            if w.right>=x1 and w.left<=x2:
                useful.append(w)
        if not useful:
            continue
        txt=_clean_name(" ".join(w.text for w in useful))
        if not txt:
            continue
        score=overlap/max(1,rx-lx)*2.0 + max(0,1-dy/max(1,image.height*.055))*1.8
        score += min(1.0, sum(w.conf for w in useful)/(100*max(1,len(useful))))
        candidates.append((score,txt,useful))

    if not candidates:
        return None,None
    candidates.sort(key=lambda z:z[0],reverse=True)
    # Junta no máximo 2 linhas consecutivas quando parecem pertencer ao mesmo cartão.
    best=candidates[0]
    selected=[best]
    for cand in sorted(candidates[1:], key=lambda z:min(w.top for w in z[2]), reverse=True):
        if len(selected)>=2: break
        if abs(min(w.top for w in cand[2])-min(w.top for w in best[2]))<max(35,badge.height*4):
            selected.append(cand)
    selected.sort(key=lambda z:min(w.top for w in z[2]))
    text=_clean_name(" ".join(x[1] for x in selected))
    if not _is_good_name(text):
        return None,None
    unit=None
    for x in selected:
        for w in x[2]:
            if UNIT_RE.search(w.text): unit=w.text
    return text,unit


def _fallback_price_words(image: Image.Image, words: list[Word]) -> list[dict]:
    out=[]
    for pw,price in _price_candidates(words):
        x1=max(0,pw.left-180); x2=min(image.width,pw.right+180)
        y1=max(0,pw.top-190); y2=min(image.height,pw.bottom+40)
        crop=image.crop((x1,y1,x2,y2))
        local=_ocr_words(crop,psm=11,min_conf=25)
        # linhas próximas do preço local
        for line in reversed(_line_groups(local)):
            txt=_clean_name(' '.join(w.text for w in line if _price_value(w.text) is None and w.text.upper() not in NOISE))
            if _is_good_name(txt):
                out.append({'pagina':0,'nome':txt,'preco':round(price,2),'preco_unidade':None}); break
    return out


def _dedupe_products(products:list[dict])->list[dict]:
    def norm(s): return re.sub(r'[^a-z0-9]+','',s.lower())
    def toks(s): return set(re.findall(r'[a-z0-9à-ÿ]{3,}',norm(s)))
    ranked=sorted(products,key=lambda p:(len(toks(p['nome'])),len(p['nome'])),reverse=True)
    out=[]
    for p in ranked:
        dup=False
        for q in out:
            if p['pagina']!=q['pagina'] or abs(p['preco']-q['preco'])>.01: continue
            a,b=toks(p['nome']),toks(q['nome'])
            sim=len(a&b)/max(1,min(len(a),len(b)))
            na,nb=norm(p['nome']),norm(q['nome'])
            if sim>=.65 or na in nb or nb in na:
                dup=True; break
        if not dup: out.append(p)
    return sorted(out,key=lambda p:(p['pagina'],norm(p['nome'])))


def parse_page(image: Image.Image, page_number: int, use_color_anchors: bool=True) -> list[dict]:
    badges=detect_price_badges(image) if use_color_anchors else []
    # Uma única leitura espacial da página. A associação produto/preço é feita
    # depois pelas coordenadas, em vez de pedir ao Tesseract para ler um cartão inteiro.
    words=_ocr_words(image,psm=11,min_conf=24)
    prices=_price_candidates(words)
    products=[]

    if badges:
        for b in badges:
            price,conf=_badge_price_from_crop(image,b)
            if price is None:
                # Procura um preço OCR cujo centro esteja dentro do sticker.
                inside=[(w,v) for w,v in prices if w.cx>=b.left-b.width*.15 and w.cx<=b.right+b.width*.15
                        and w.cy>=b.top-b.height*.6 and w.cy<=b.bottom+b.height*.6]
                if inside:
                    w,v=max(inside,key=lambda z:z[0].conf); price=v
            if price is None:
                continue
            name,unit=_name_for_badge(image,b,words,badges)
            if not name:
                continue
            products.append({'pagina':page_number,'nome':name,'preco':round(price,2),'preco_unidade':unit})

    # Só usar preços OCR livres se não houver âncoras válidas na página.
    if not products and not badges:
        for p in _fallback_price_words(image,words):
            p['pagina']=page_number; products.append(p)

    safe=[]
    for p in _dedupe_products(products):
        if not _is_good_name(p['nome']): continue
        if not (0.10<=p['preco']<=199.99): continue
        if p['preco']>=60 and p['preco'] not in (159.0,159.99): continue
        safe.append(p)
    return safe


def parse_pdf(pdf_path: str|Path, render_dpi: int=240, use_color_anchors: bool=True) -> list[dict]:
    import pymupdf
    doc=pymupdf.open(pdf_path)
    out=[]
    for i,page in enumerate(doc):
        pix=page.get_pixmap(dpi=render_dpi,alpha=False)
        image=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
        page_products=parse_page(image,i+1,use_color_anchors=use_color_anchors)
        print(f'Página {i+1}: {len(page_products)} produtos')
        out.extend(page_products)
    doc.close()
    return out
