"""Per-city signage textures (scope 5.2, 5.5): sign atlases from M11's names and unit uses
in each district's scripts, brand logos and ad content, written to `BUILD/assets/textures/`
with `signs.json`.

- **Texts.** A shop sign shows the name of the point of interest in its unit (M11: a bar,
  club, arcade, clinic or vendor) or, without one, a shop name drawn for its district and
  use from a small pool (M11's adjective and noun lists with a use word: "JADE KOI RAMEN"),
  so a city has a few hundred distinct signs, not one per slot; a neon band shows its
  district's name; a lobby sign the owner's.
- **Scripts.** Each text is drawn in a script picked by its district's weights (the asset
  spec's `signage_scripts`, the era's by default): Latin as written, the others by a
  syllable transliteration (`glyphs`).
- **Styles.** neon (tubes with a glow on a dark panel), lightbox (a lit panel with dark
  letters) and LED (dot rows); the colors from the district's neon palette.
- **Pages.** Facade and neon-band signs in wide cells (4:1), blade signs in tall cells
  (1:4), 256 to a 4096 px page at 512 px/m (cells scale with the density); billboards and
  holo-ads from 16 ads per page (2:1); 16 brand logos (corporations and owners) in one page.

`signs.json` gives every sign slot its page, cell, UV rectangle (glTF convention: (0, 0) at
the image's top left, so a quad mapped onto it shows the text upright), text, script, style
and color, for AG8's sign meshes and the previews.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from . import glyphs as GL
from . import noise as N
from . import pbr as P

F = np.float32
USE_WORDS = {
    "food": ("RAMEN", "NOODLES", "DUMPLINGS", "GRILL", "SUSHI", "TACOS", "KEBAB", "PHO",
             "CAFE", "BBQ"),
    "bar": ("BAR", "LOUNGE", "TAVERN", "PUB"), "club": ("CLUB", "DISCO", "HALL"),
    "cyberware": ("CYBERWARE", "IMPLANTS", "OPTICS", "AUGS", "CHROME"),
    "convenience": ("24H", "MART", "MINI MART", "STORE"), "arcade": ("ARCADE", "GAMES", "VR"),
    "pawn": ("PAWN", "CASH", "GOLD BUY"), "laundromat": ("LAUNDRY", "WASH"),
    "clinic": ("CLINIC", "MEDIC", "PHARMACY"), "lobby": ("LOBBY",), "corporate": ("",),
}
POOL = 5                       # shop names per district and use
STYLES = ("neon", "lightbox", "led")
ACCENTS = ("#ff3fb4", "#2fe0ff", "#9d4dff", "#ff8a1f", "#39ff8f", "#ffd23f", "#ff4040")
AD_LINES = ("UPGRADE YOURSELF", "FEEL MORE", "LIVE FOREVER", "NEVER SLEEP", "OWN THE NIGHT",
            "BE NEW", "TRUST US", "THE FUTURE IS NOW", "SAFE AND SOUND", "GO FURTHER",
            "MORE IS MORE", "STAY CONNECTED")
AD_PRODUCTS = ("COLA", "IMPLANTS", "INSURANCE", "AIR", "SKYCAR", "NOODLES", "BANK", "STIM",
               "OPTICS", "TRAVEL", "HOMES", "SECURITY")
ADS_PER_PAGE = 16
LOBBY_WORDS = ("TOWER", "HOUSE", "PLAZA", "CENTER", "COURT", "BUILDING")
BRAND_MIN = 8                  # properties an owner needs to be a brand (corporations)


def _h(*parts) -> int:
    return int.from_bytes(hashlib.blake2b("|".join(str(p) for p in parts).encode(),
                                          digest_size=8).digest(), "little")


def _u(*parts) -> float:
    return _h(*parts) / 2.0 ** 64


def _pick(options, *parts):
    return options[_h(*parts) % len(options)]


def _wpick(weights: dict, *parts) -> str:
    keys = sorted(k for k, v in weights.items() if v > 0) or ["latin"]
    total = sum(weights[k] for k in keys)
    x = _u(*parts) * total
    acc = 0.0
    for k in keys:
        acc += weights[k]
        if x < acc:
            return k
    return keys[-1]


def _rgb(hexc: str) -> tuple:
    return tuple(int(hexc[1 + 2 * k:3 + 2 * k], 16) for k in range(3))


# --- texts per slot ----------------------------------------------------------------------------

def district_styles(model, spec: dict) -> dict[str, dict]:
    """Per district id: name, era, script weights and neon palette (asset spec over the era
    presets; citygen's era by archetype)."""
    from ..streets import materials as SM
    out = {}
    for d in model.districts:
        era = SM.era_of(d.archetype)
        ds = (spec.get("districts") or {}).get(d.name) or {}
        era = ds.get("era") or era
        es = (spec.get("eras") or {}).get(era) or {}
        scripts = ds.get("signage_scripts") or es.get("signage_scripts") or {"latin": 1.0}
        pal = ds.get("neon_palette") or list(ACCENTS)
        out[d.id] = {"name": d.name, "era": era, "scripts": scripts, "palette": pal,
                     "ads": float(ds.get("ad_density", 1.0))}
    return out


def _owner_name(owner: str) -> str:
    return " ".join(w.capitalize() for w in owner.replace("_", " ").split())


def slot_texts(model, styles: dict) -> tuple[dict, dict]:
    """Per sign slot its text key; per text key (text, script, style, color, shape)."""
    from citygen import gameplay as GP
    bld = {b.id: b for b in model.buildings}
    poi_at = {(p.building_id, p.unit_index): p for p in model.pois
              if p.building_id and p.unit_index is not None}
    owner_of = {}
    owner_n: dict[str, int] = {}
    for p in model.properties:
        owner_n[p.owner] = owner_n.get(p.owner, 0) + 1
        for bid in p.building_ids:
            owner_of[bid] = p.owner
    texts: dict[str, dict] = {}
    slots: dict[str, str] = {}
    city = model.name
    for s in sorted(model.sign_slots, key=lambda s: s.id):
        b = bld.get(s.building_id) if s.building_id else None
        dist = (b.district_id if b else None) or ""
        st = styles.get(dist) or {"name": city, "era": "mixed_modern", "scripts": {"latin": 1},
                                  "palette": list(ACCENTS)}
        shape = "tall" if s.mount == "blade" else "wide"
        if s.kind in ("billboard", "holo_ad"):
            slots[s.id] = f"ad:{_h(city, 'ad', s.id) % (2 * ADS_PER_PAGE)}"
            continue
        if s.kind == "neon":
            text, base = st["name"].upper(), f"district:{dist}"
        elif s.content == "corporate" or s.content == "lobby":
            own = owner_of.get(s.building_id or "", "")
            if own and owner_n.get(own, 0) >= BRAND_MIN:
                text, base = _owner_name(own).upper(), f"owner:{own}"
            elif b is not None and b.name:
                text, base = b.name.upper(), f"building:{b.id}"
            else:
                k = _h(city, "lobby", s.id) % POOL
                text = (f"{_pick(GP.NOUN, city, dist, 'lobby', k)} "
                        f"{_pick(LOBBY_WORDS, city, dist, 'lobby', k, 'w')}").upper()
                base = f"lobby:{dist}:{k}"
        else:
            poi = None
            if b is not None and b.units:
                px, py = s.position[0], s.position[1]
                best = None
                for i, un in enumerate(b.units):
                    (ax, ay), (bx, by) = un.edge
                    mx, my = (ax + bx) / 2, (ay + by) / 2
                    d = (mx - px) ** 2 + (my - py) ** 2
                    if best is None or d < best[0]:
                        best = (d, i)
                if best is not None and best[0] < 15.0 ** 2:
                    poi = poi_at.get((b.id, best[1]))
            if poi is not None:
                text, base = poi.name.upper(), f"poi:{poi.id}"
            else:
                use = s.content if s.content in USE_WORDS else "convenience"
                k = _h(city, "pool", s.id) % POOL
                word = _pick(USE_WORDS[use], city, dist, use, k)
                adj = _pick(GP.ADJ, city, dist, use, k, "a")
                noun = _pick(GP.NOUN, city, dist, use, k, "n")
                form = _h(city, dist, use, k, "form") % 3
                text = (f"{adj} {noun} {word}" if form == 0 else
                        f"{noun} {word}" if form == 1 else word).upper()
                base = f"shop:{dist}:{use}:{k}"
        script = _wpick(st["scripts"], city, base, "script")
        style = STYLES[_h(city, base, "style") % 3] if s.kind != "neon" else "neon"
        color = _pick(st["palette"], city, base, "color")
        key = f"{base}:{shape}"
        if key not in texts:
            texts[key] = {"text": text.strip() or "OPEN", "script": script, "style": style,
                          "color": color, "shape": shape,
                          "color2": _pick(st["palette"], city, base, "color2")}
        slots[s.id] = key
    return slots, texts


# --- drawing -----------------------------------------------------------------------------------

def _fit(text: str, script: str, w: int, h: int, vertical: bool):
    """Strokes placed in a w x h box: (strokes, x0, y0, scale) or stacked pieces."""
    if not vertical:
        st, tw = GL.layout(text, script)
        if tw <= 0:
            st, tw = GL.layout("OPEN", "latin")
        sc = min((w * 0.86) / tw, (h * 0.62) / 6.0)
        return [(st, (w - tw * sc) / 2, h / 2 + 3 * sc, sc)]
    pieces = GL.units(text, script)[:8] or ["O"]
    n = len(pieces)
    out = []
    sc = min((h * 0.9) / (n * 7.2), (w * 0.72) / 6.0)
    y = (h - n * 7.2 * sc) / 2 + 6.6 * sc
    for p in pieces:
        st, pw = GL.unit_layout(p, script)
        out.append((st, (w - pw * sc) / 2, y, sc))
        y += 7.2 * sc
    return out


def sign_cell(info: dict, w: int, h: int, seed: int) -> np.ndarray:
    """One sign (h x w x 3 uint8, emissive color)."""
    vertical = info["shape"] == "tall"
    col = _rgb(info["color"])
    col2 = _rgb(info["color2"])
    style = info["style"]
    placed = _fit(info["text"], info["script"], w, h, vertical)
    m = 2
    mask_img = Image.new("L", (w * m, h * m), 0)
    for st, x0, y0, sc in placed:
        GL.draw(mask_img, st, x0 * m, y0 * m, sc * m, max(2.0, sc * m * (0.9 if style != "led"
                                                                           else 1.1)), 255)
    mask = np.asarray(mask_img)
    mask = ((mask[0::2, 0::2].astype(np.uint32) + mask[1::2, 0::2] + mask[0::2, 1::2]
             + mask[1::2, 1::2] + 2) // 4).astype(F) / F(255.0)
    yy, xx = np.mgrid[0:h, 0:w]
    edge = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)).astype(F)
    bw = max(2.0, min(w, h) * 0.06)
    border = ((edge < F(bw)) & (edge >= F(bw * 0.5))).astype(F)
    c1 = np.array(col, F) / F(255.0)
    c2 = np.array(col2, F) / F(255.0)
    if style == "neon":
        tube = np.maximum(mask, border * F(0.9))
        r = max(1, int(min(w, h) * 0.04))
        glow = N.blur(N.blur(tube, r), r)
        tint = np.where(border[:, :, None] > F(0.5), c2[None, None, :], c1[None, None, :])
        bg = np.array([0.02, 0.02, 0.035], F)
        img = bg[None, None, :] + tint * (glow[:, :, None] * F(1.1)) \
            + (tint * F(0.6) + F(0.4)) * tube[:, :, None]
    elif style == "lightbox":
        bgc = np.clip(c1 * F(0.85) + F(0.15), 0, 1)
        grad = (F(0.85) + F(0.15) * (yy.astype(F) / F(max(h - 1, 1))))[:, :, None]
        ink = np.array([0.05, 0.05, 0.06], F) if float(c1.sum()) > 1.2 else \
            np.array([0.98, 0.98, 0.95], F)
        img = bgc[None, None, :] * grad
        img = img + (ink[None, None, :] - img) * mask[:, :, None]
        img = img * (F(1.0) - F(0.8) * border[:, :, None])
    else:
        pitch = max(2, int(min(w, h) * 0.05))
        dots = (((xx % pitch) < pitch - 1) & ((yy % pitch) < pitch - 1)).astype(F)
        bg = np.array([0.03, 0.03, 0.03], F)
        img = bg[None, None, :] + c1[None, None, :] * (mask * dots)[:, :, None] * F(1.2)
        img = img + c2[None, None, :] * (border * F(0.5))[:, :, None]
    return P.u8(np.clip(img, 0, 1))


def logo(name: str, color: str, n: int) -> np.ndarray:
    """A brand mark: a shape from the name's hash in its color, the initials under it."""
    from PIL import ImageDraw
    m = 2 * n
    img = Image.new("RGBA", (m, m), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = _rgb(color) + (255,)
    k = _h("logo", name) % 6
    cx, cy, r = m // 2, int(m * 0.4), int(m * 0.28)
    lw = max(2, m // 24)
    if k == 0:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=lw * 2)
        d.ellipse([cx - r // 3, cy - r // 3, cx + r // 3, cy + r // 3], fill=c)
    elif k == 1:
        pts = [(cx + int(r * x), cy + int(r * y)) for x, y in
               ((1, 0), (0.5, 0.87), (-0.5, 0.87), (-1, 0), (-0.5, -0.87), (0.5, -0.87))]
        d.polygon(pts, outline=c, width=lw * 2)
        d.line([pts[0], pts[3]], fill=c, width=lw)
    elif k == 2:
        d.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], fill=c)
        d.polygon([(cx, cy), (cx + r // 2, cy + r), (cx - r // 2, cy + r)], fill=(0, 0, 0, 0))
    elif k == 3:
        for j in range(3):
            y = cy - r + j * r * 2 // 3
            d.line([(cx - r, y + r // 2), (cx, y), (cx + r, y + r // 2)], fill=c, width=lw * 2)
    elif k == 4:
        for j in range(4):
            x = cx - r + j * r // 2
            d.rectangle([x, cy + r - (j + 1) * r // 2, x + r // 3, cy + r], fill=c)
    else:
        d.rectangle([cx - r, cy - r, cx + r, cy + r], outline=c, width=lw * 2)
        d.line([(cx - r, cy + r), (cx + r, cy - r)], fill=c, width=lw * 2)
    initials = "".join(w[:1] for w in name.replace("_", " ").split())[:3].upper()
    st, tw = GL.layout(initials or "X", "latin")
    sc = min(m * 0.6 / max(tw, 1), m * 0.14 / 6.0)
    GL.draw(img, st, (m - tw * sc) / 2, m * 0.93, sc, max(2, sc * 1.1), c)
    a = np.asarray(img)
    b = a.astype(np.uint32)
    s = b[0::2, 0::2] + b[1::2, 0::2] + b[0::2, 1::2] + b[1::2, 1::2]
    return ((s + 2) // 4).astype(np.uint8)


def ad(k: int, city: str, brands: list[tuple[str, str]], w: int, h: int,
       logos: dict, holo: bool) -> np.ndarray:
    """One billboard (h x w x 3): a gradient, shapes, a brand's logo, a headline."""
    name, color = brands[_h(city, "ad.brand", k) % len(brands)]
    c1 = np.array(_rgb(color), F) / F(255.0)
    c2 = np.array(_rgb(_pick(ACCENTS, city, "ad.c2", k)), F) / F(255.0)
    yy, xx = np.mgrid[0:h, 0:w]
    t = (yy.astype(F) / F(h - 1))[:, :, None]
    img = c1[None, None, :] * (F(0.25) + F(0.5) * t) + c2[None, None, :] * (F(0.6) - F(0.5) * t)
    # shapes: a disc or bands
    cx, cy = w * (0.68 + 0.15 * _u(city, "ad.x", k)), h * 0.45
    rr = (xx - F(cx)) ** 2 + (yy - F(cy)) ** 2
    disc = (rr < F((h * 0.33) ** 2)).astype(F)
    img = img * (F(1.0) - F(0.5) * disc[:, :, None]) + c2[None, None, :] * disc[:, :, None] * F(0.6)
    out = Image.fromarray(P.u8(np.clip(img, 0, 1)))
    lg = logos.get(name)
    if lg is not None:
        li = Image.fromarray(lg).resize((h // 2, h // 2), Image.NEAREST)
        out.paste(li, (int(w * 0.04), int(h * 0.06)), li)
    head = _pick(AD_LINES, city, "ad.line", k)
    prod = f"{_owner_name(name).upper()} {_pick(AD_PRODUCTS, city, 'ad.p', k)}"
    for text, y, frac in ((head, h * 0.82, 0.13), (prod, h * 0.95, 0.06)):
        st, tw = GL.layout(text, "latin")
        sc = min(w * 0.55 / max(tw, 1), h * frac / 6.0)
        x0 = w * 0.05
        GL.draw(out, st, x0 + sc * 0.4, y + sc * 0.4, sc, max(2, sc * 1.0), (10, 10, 12))
        GL.draw(out, st, x0, y, sc, max(2, sc * 1.0), (245, 245, 240))
    a = np.asarray(out)[:, :, :3].astype(F) / F(255.0)
    if holo:
        lum = (a[:, :, 0] * F(0.3) + a[:, :, 1] * F(0.59) + a[:, :, 2] * F(0.11))
        scan = np.where((yy % 4) < 2, F(1.0), F(0.55))
        cyan = np.array([0.25, 0.9, 1.0], F)
        a = cyan[None, None, :] * (lum * scan)[:, :, None] * F(1.3)
    return P.u8(np.clip(a, 0, 1))


# --- the city ----------------------------------------------------------------------------------

def brands(model, spec: dict) -> list[tuple[str, str]]:
    """(name, color) of every corporation and owner, sorted: brand colors from the asset
    spec's owners, a faction's color, else one drawn from the name."""
    count: dict[str, int] = {}
    for p in model.properties:
        count[p.owner] = count.get(p.owner, 0) + 1
    named = set(spec.get("owners") or {})
    owners = sorted(o for o, n in count.items() if n >= BRAND_MIN or o in named)
    out = []
    for o in owners:
        os_ = (spec.get("owners") or {}).get(o) or {}
        cols = os_.get("brand_colors") or []
        out.append((o, cols[0] if cols else _pick(ACCENTS + ("#e8e8e8", "#c8a040"), "brand", o)))
    for f in sorted(model.factions, key=lambda f: f.name):
        if f.kind == "corporate":
            out.append((f.name, f.color))
    return out


def build(model, spec: dict, out_dir: Path, density: int, log=print) -> dict:
    """Write the city's sign, ad and logo pages to out_dir (BUILD/assets/textures); the
    signs.json record (also returned)."""
    from ..manifest import dumps, write_if_changed
    scale = density / 512.0
    ww, wh = max(32, int(512 * scale)), max(8, int(128 * scale))
    page = max(256, int(4096 * scale))
    styles = district_styles(model, spec)
    slots, texts = slot_texts(model, styles)
    keys = sorted(texts)
    wide = [k for k in keys if texts[k]["shape"] == "wide"]
    tall = [k for k in keys if texts[k]["shape"] == "tall"]
    files: dict[str, dict] = {}
    cells: dict[str, dict] = {}
    wrote = 0

    def save(name, a):
        nonlocal wrote
        path = out_dir / f"{name}.png"
        sha = P.pixels_sha256(a)
        old = files_old.get(name)
        if not (old and old.get("pixels_sha256") == sha and path.is_file()):
            P.save_png(path, a)
            wrote += 1
        files[name] = {"file": f"textures/{name}.png", "size": [int(a.shape[1]),
                                                                int(a.shape[0])],
                       "channels": int(a.shape[2]), "pixels_sha256": sha}

    old_path = out_dir.parent / "signs.json"
    files_old = {}
    if old_path.is_file():
        import json
        try:
            files_old = json.loads(old_path.read_text(encoding="utf-8")).get("files", {})
        except ValueError:
            files_old = {}
    for shape, ks, (cw, ch) in (("wide", wide, (ww, wh)), ("tall", tall, (wh, ww))):
        cols, rows = page // cw, page // ch
        per = cols * rows
        for p0 in range(0, len(ks), per):
            chunk = ks[p0:p0 + per]
            nrows = (len(chunk) + cols - 1) // cols
            hpx = 1
            while hpx < nrows * ch:
                hpx *= 2
            img = np.zeros((hpx, page, 3), np.uint8)
            pname = f"signs_{shape}_{p0 // per}"
            for i, k in enumerate(chunk):
                r, c = divmod(i, cols)
                img[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw] = sign_cell(texts[k], cw, ch,
                                                                         _h(k))
                cells[k] = {**texts[k], "page": pname,
                            "uv": [round(c * cw / page, 6), round(r * ch / hpx, 6),
                                   round((c + 1) * cw / page, 6), round((r + 1) * ch / hpx, 6)]}
            save(pname, img)
    br = brands(model, spec)
    ln = max(32, int(256 * scale))
    logos = {name: logo(name, color, ln) for name, color in br}
    lg = np.zeros((4 * ln, 4 * ln, 4), np.uint8)
    for i, (name, _) in enumerate(br[:16]):
        r, c = divmod(i, 4)
        lg[r * ln:(r + 1) * ln, c * ln:(c + 1) * ln] = logos[name]
        cells[f"logo:{name}"] = {"page": "logos", "uv": [c / 4, r / 4, (c + 1) / 4, (r + 1) / 4],
                                 "text": name}
    save("logos", lg)
    aw, ah = max(64, int(1024 * scale)), max(32, int(512 * scale))
    for pg, holo in ((0, False), (1, True)):
        img = np.zeros((4 * ah, 4 * aw, 3), np.uint8)
        for i in range(ADS_PER_PAGE):
            r, c = divmod(i, 4)
            k = pg * ADS_PER_PAGE + i
            img[r * ah:(r + 1) * ah, c * aw:(c + 1) * aw] = ad(k, model.name, br, aw, ah,
                                                               logos, holo)
            cells[f"ad:{k}"] = {"page": f"ads_{pg}", "uv": [c / 4, r / 4, (c + 1) / 4,
                                                            (r + 1) / 4], "holo": holo}
        save(f"ads_{pg}", img)
    # every holo-ad slot takes a holo ad
    for s in model.sign_slots:
        if s.kind == "holo_ad" and slots.get(s.id, "").startswith("ad:"):
            k = int(slots[s.id][3:]) % ADS_PER_PAGE + ADS_PER_PAGE
            slots[s.id] = f"ad:{k}"
        elif s.kind == "billboard" and slots.get(s.id, "").startswith("ad:"):
            slots[s.id] = f"ad:{int(slots[s.id][3:]) % ADS_PER_PAGE}"
    doc = {"version": 1, "city": model.name, "density_px_m": density,
           "files": dict(sorted(files.items())), "cells": dict(sorted(cells.items())),
           "slots": dict(sorted(slots.items())),
           "counts": {"slots": len(slots), "texts": len(texts), "wide": len(wide),
                      "tall": len(tall), "brands": len(br)}}
    wrote += int(write_if_changed(old_path, dumps(doc)))
    doc["wrote"] = wrote
    return doc
