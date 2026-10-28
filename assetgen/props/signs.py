"""Sign assets (scope 5.5): an asset for every M11 sign slot.

Each slot is gathered into inputs (`inputs`: its kind, mount, size, text, script, look, neon
colors and the gap to its wall from the brief), and made from them alone (`make`), in the
slot's frame: x the direction it faces, y to its left along the face, z up, the origin the
middle of its face (M11's position). Text reads left to right for a viewer in front.

| slot | made as |
|---|---|
| shop sign, facade | a lightbox (lit face, dark letters), a panel (dark face, lit letters), neon tubes along the glyph strokes on a backboard with an outline, or channel letters on a raceway; standoffs back to the wall where the brief finds it off the wall |
| shop sign, blade | a vertical box on two arms from the wall, the text stacked down both faces, lit or in neon tubes |
| billboard | a steel frame and a lit content face (a headline, a color band, a logo disc), lamps on arms, a truss and catwalk on roofs (two faces), a standoff box on facades |
| holo-ad | a projector on the roof (Nanite) and the image: translucent emissive planes with the text, frame and scan bands, as a non-Nanite LOD chain (`extra`) |
| neon band | a backboard on the facade with a stacked word in neon tubes, an outline and chevrons |

Text: a point of interest's name where one is in the sign's unit, else a generated shop name
for the unit's use (`USE_WORDS` and citygen's name lists), billboard and holo-ad brands from
the city's corporations; the second line in the district's script (`glyphs.py`).
"""

from __future__ import annotations

from . import glyphs as GL
from . import materials as MT
from . import styles as ST
from .shapes import Mesh, add, blk, cross, fan, mul, quad_out, ring, sub, tube

USE_WORDS = {
    "food": ("NOODLES", "RAMEN", "DUMPLINGS", "GRILL", "TACOS", "PHO", "SUSHI", "KEBAB",
             "BAO", "CURRY", "EATS", "WOK", "BBQ", "DINER"),
    "bar": ("BAR", "LOUNGE", "TAVERN", "SAKE", "PUB", "COCKTAILS", "TAPROOM"),
    "club": ("CLUB", "DISCO", "LIVE", "DANCE", "NIGHT", "BASS", "RAVE"),
    "arcade": ("ARCADE", "GAMES", "VR", "PLAY", "PACHINKO", "SLOTS"),
    "cyberware": ("CYBERWARE", "CHROME", "IMPLANTS", "MODS", "AUGS", "OPTICS"),
    "clinic": ("CLINIC", "PHARMACY", "MEDS", "DOC", "DENTAL", "LAB"),
    "pawn": ("PAWN", "CASH", "GOLD", "LOANS", "BUY SELL", "TRADE"),
    "convenience": ("24/7", "MART", "SHOP", "MINI MART", "STORE", "DELI"),
    "laundromat": ("LAUNDRY", "WASH", "COIN WASH", "DRY CLEAN"),
    "lobby": ("LOBBY", "HOTEL", "OFFICES", "RESIDENCE", "TOWER"),
    "shop": ("SHOP", "STORE", "GOODS", "SUPPLY"),
}
BAND_WORDS = ("HOTEL", "LIVE", "BAR", "KARAOKE", "MAHJONG", "OPEN", "TATTOO", "CAFE",
              "NOODLE", "MASSAGE", "CLUB", "24H", "CAPSULE", "LOUNGE")
AD_WORDS = ("DRINK", "WEAR", "FEEL", "UPGRADE", "TRUST", "FLY", "LIVE", "BUY", "CHOOSE",
            "DREAM", "PLUG IN", "GO")
PRODUCTS = ("COLA", "ENERGY", "OPTICS", "CHROME", "NOODLE", "VAPOR", "JET", "SKIN", "SYNTH",
            "PULSE", "ZERO", "NOVA", "BLISS", "LINK")
LOOKS_FACADE = {"sleek": ("channel", "lightbox", "panel"), "civic": ("lightbox", "panel", "channel"),
                "heavy": ("lightbox", "panel", "lightbox"), "neon": ("neon", "neon", "lightbox", "panel"),
                "old": ("neon", "lightbox", "panel", "neon")}
LOOKS_BLADE = {"sleek": ("panel", "lightbox"), "civic": ("lightbox", "panel"),
               "heavy": ("lightbox", "panel"), "neon": ("neon", "neon", "lightbox"),
               "old": ("neon", "lightbox", "neon")}
FACE_COLORS = ("#f4f1ea", "#ffe39a", "#ffd0e0", "#d0f4ff", "#fff4d0", "#ff5050", "#ffcc33",
               "#33ccff", "#ff66cc")
TIP_MIN = 0.007


def _words(seq, *key) -> str:
    return ST.choice(seq, *key)


def shop_text(use: str, poi: str | None, *key) -> str:
    """A shop sign's text: its point of interest's name, else a generated name for its use
    (a use word, sometimes with a name from citygen's lists in front)."""
    if poi:
        return poi.upper()
    from citygen.gameplay import ADJ, NOUN, SURNAME
    w = _words(USE_WORDS.get(use, USE_WORDS["shop"]), *key, "w")
    r = ST.u(*key, "n")
    if r < 0.3:
        return f"{_words(ADJ, *key, 'a').upper()} {w}"
    if r < 0.5:
        return f"{_words(SURNAME, *key, 's').upper()} {w}"
    if r < 0.6:
        return f"{_words(NOUN, *key, 'o').upper()} {w}"
    return w


def script_of(era: str, weights: dict | None, *key) -> str:
    """The script a sign's second line is in: by the era's (or the spec's) weights."""
    from ..presets import ERA_PRESETS
    w = weights or ERA_PRESETS.get(era, {}).get("signage_scripts") or {"latin": 1.0}
    items = sorted(w.items())
    tot = sum(v for _, v in items)
    r = ST.u(*key, "script") * tot
    acc = 0.0
    for name, v in items:
        acc += v
        if r < acc:
            return name
    return items[-1][0]


# ---------------------------------------------------------------------------------------
# text on a plane
# ---------------------------------------------------------------------------------------

def put_text(m: Mesh, slot: str, strokes, origin, right, up, unit: float, mode: str,
             normal, thick: float = 0.85) -> None:
    """Glyph strokes (units) on the plane through `origin` spanned by `right` and `up`:
    `flat` quads `thick` units wide just in front along `normal`, or `tube` neon tubes
    standing off it."""
    def P(gx, gy, off=0.0):
        return (origin[0] + right[0] * gx * unit + up[0] * gy * unit + normal[0] * off,
                origin[1] + right[1] * gx * unit + up[1] * gy * unit + normal[1] * off,
                origin[2] + right[2] * gx * unit + up[2] * gy * unit + normal[2] * off)
    seen = set()
    if mode == "tube":
        r = max(TIP_MIN, min(0.03, 0.11 * unit))
        for st in strokes:
            pts = [P(x, y, r * 1.6) for x, y in st]
            clean = [pts[0]]
            for p in pts[1:]:
                if abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1]) + abs(p[2] - clean[-1][2]) > 0.002:
                    clean.append(p)
            k = tuple((round(p[0], 3), round(p[1], 3), round(p[2], 3)) for p in clean)
            if len(clean) < 2 or k in seen or k[::-1] in seen:
                continue
            seen.add(k)
            # (no caps: a tube's ends sit in the glow, and the sign carries thousands)
            tube(m, slot, clean, r, 4, caps=False)
        return
    t = thick * unit / 2.0
    off = 0.004
    for st in strokes:
        for (x0, y0), (x1, y1) in zip(st, st[1:]):
            k = (round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3))
            if k in seen or (k[2], k[3], k[0], k[1]) in seen:
                continue
            seen.add(k)
            a, b = P(x0, y0, off), P(x1, y1, off)
            d = sub(b, a)
            L = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) ** 0.5
            if L < 1e-6:
                d = right
                L = 1.0
            d = mul(d, 1.0 / L)
            p = cross(normal, d)
            a2, b2 = sub(a, mul(d, t)), add(b, mul(d, t))
            q = (sub(a2, mul(p, t)), sub(b2, mul(p, t)), add(b2, mul(p, t)), add(a2, mul(p, t)))
            # (two strokes of a generated glyph can land on the same millimeters)
            qk = tuple(sorted(tuple(int(round(v * 1000.0)) for v in c) for c in q))
            if qk in seen:
                continue
            seen.add(qk)
            quad_out(m, slot, *q, normal)


def fit(strokes_wh, w: float, h: float) -> float:
    """The unit that fits a text block of (width, height) units into w by h meters."""
    tw, th = strokes_wh
    if tw <= 0 or th <= 0:
        return 0.0
    return min(w / tw, h / th)


def outline(m: Mesh, slot: str, cy: float, cz: float, w: float, h: float, x: float,
            r: float, normal=(1.0, 0.0, 0.0), plane: str = "yz") -> None:
    """A neon tube round a rectangle (plane yz at x, or xz at y = x)."""
    if plane == "yz":
        pts = [(x, cy - w / 2, cz - h / 2), (x, cy + w / 2, cz - h / 2), (x, cy + w / 2, cz + h / 2),
               (x, cy - w / 2, cz + h / 2), (x, cy - w / 2, cz - h / 2 + 0.001)]
    else:
        pts = [(cy - w / 2, x, cz - h / 2), (cy + w / 2, x, cz - h / 2), (cy + w / 2, x, cz + h / 2),
               (cy - w / 2, x, cz + h / 2), (cy - w / 2, x, cz - h / 2 + 0.001)]
    tube(m, slot, pts, r, 4, caps=False)


# ---------------------------------------------------------------------------------------
# the makers
# ---------------------------------------------------------------------------------------

def make(inp: dict) -> tuple[Mesh, list]:
    """A slot's mesh and its extra meshes ([{"suffix", "lods", "nanite", "screen"}])."""
    m = Mesh((0.0, 0.0))
    k = inp["kind"]
    if k == "shop_sign" and inp["mount"] == "blade":
        blade(m, inp)
    elif k == "shop_sign":
        facade(m, inp)
    elif k == "billboard":
        billboard(m, inp)
    elif k == "holo_ad":
        return m, holo(m, inp)
    else:
        band(m, inp)
    return m, []


def _lines(inp: dict, vertical: bool = False):
    """(main strokes and size, second strokes and size or None)."""
    main = GL.layout(inp["text"], "latin", (), vertical)
    sec = None
    if inp.get("script", "latin") != "latin" and inp.get("glyphs", 0):
        sec = GL.layout("x" * inp["glyphs"], inp["script"], (inp["text"],), vertical)
        if inp["script"] == "cyrillic":
            sec = GL.layout(inp["text"], "cyrillic", (), vertical)
    return main, sec


def facade(m: Mesh, inp: dict) -> None:
    w, h, look = inp["w"], inp["h"], inp["look"]
    neon, neon2 = MT.neon_slot(inp["colors"][0]), MT.neon_slot(inp["colors"][1])
    lit = MT.face_slot(inp["face"])
    d = 0.15
    gap = inp.get("gap", 0.0)
    (main, mwh), sec = _lines(inp)
    if look == "lightbox":
        blk(m, "sign.box", -d, -0.012, -w / 2, w / 2, -h / 2, h / 2)
        blk(m, lit, -0.012, 0.0, -w / 2 + 0.03, w / 2 - 0.03, -h / 2 + 0.03, h / 2 - 0.03)
        tcol, mode = "sign.back", "flat"
    elif look == "panel":
        blk(m, "sign.face", -d, 0.0, -w / 2, w / 2, -h / 2, h / 2)
        tcol, mode = lit, "flat"
    elif look == "channel":
        blk(m, "sign.box", -d, -d + 0.06, -w / 2, w / 2, -h * 0.12, h * 0.12)
        tcol, mode = lit, "flat"
    else:
        blk(m, "sign.back", -d, -d + 0.04, -w / 2, w / 2, -h / 2, h / 2)
        outline(m, neon2, 0.0, 0.0, w - 0.08, h - 0.08, -d + 0.07, 0.015)
        blk(m, "sign.box", -d - 0.02, -d, w / 2 - 0.35, w / 2 - 0.1, -h / 2 + 0.05, -h / 2 + 0.25)
        tcol, mode = neon, "tube"
    face_x = 0.0 if look != "neon" else -d + 0.04
    mw, mh = (w - 0.16, h * (0.62 if sec else 0.8))
    u = fit(mwh, mw, mh)
    if u > 0:
        y0 = -mwh[0] * u / 2.0
        z0 = (h / 2 - 0.06 - mwh[1] * u) if sec else -mwh[1] * u / 2.0
        put_text(m, tcol, main, (face_x, y0, z0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), u, mode,
                 (1.0, 0.0, 0.0))
    if sec:
        swh = sec[1]
        u2 = fit(swh, w - 0.2, h * 0.26)
        if u2 > 0:
            put_text(m, neon2 if mode == "tube" else tcol, sec[0],
                     (face_x, -swh[0] * u2 / 2.0, -h / 2 + 0.06), (0.0, 1.0, 0.0),
                     (0.0, 0.0, 1.0), u2, mode, (1.0, 0.0, 0.0))
    if look == "channel":
        blk(m, "sign.box", -d, -0.02, -w / 2 + 0.05, w / 2 - 0.05, -h / 2, h / 2)
    if gap > 0.02:
        for y in (-w / 2 + 0.2, w / 2 - 0.2):
            for z in (-h / 4, h / 4):
                blk(m, "metal.dark", -d - gap, -d, y - 0.03, y + 0.03, z - 0.03, z + 0.03)


def blade(m: Mesh, inp: dict) -> None:
    """A blade sign: x out from the wall (-w/2 to w/2; the wall at -0.7), z up, faces on
    +y and -y."""
    w, h, look = inp["w"], inp["h"], inp["look"]
    t = 0.24
    neon, neon2 = MT.neon_slot(inp["colors"][0]), MT.neon_slot(inp["colors"][1])
    lit = MT.face_slot(inp["face"])
    if look == "lightbox":
        blk(m, "sign.box", -w / 2, w / 2, -t / 2 + 0.012, t / 2 - 0.012, -h / 2, h / 2)
        for s in (-1.0, 1.0):
            y0, y1 = sorted((s * (t / 2 - 0.012), s * t / 2))
            blk(m, lit, -w / 2 + 0.04, w / 2 - 0.04, y0, y1, -h / 2 + 0.04, h / 2 - 0.04)
        tcol, mode, face = "sign.back", "flat", t / 2
    elif look == "panel":
        blk(m, "sign.face", -w / 2, w / 2, -t / 2, t / 2, -h / 2, h / 2)
        tcol, mode, face = lit, "flat", t / 2
    else:
        # neon on an open skeleton: a frame round the sign, the tubes once in its middle
        # plane (read from both sides, mirrored from the back, as on a real one)
        for z0, z1 in ((-h / 2, -h / 2 + 0.05), (h / 2 - 0.05, h / 2)):
            blk(m, "sign.frame", -w / 2, w / 2, -0.04, 0.04, z0, z1)
        for x0, x1 in ((-w / 2, -w / 2 + 0.05), (w / 2 - 0.05, w / 2)):
            blk(m, "sign.frame", x0, x1, -0.04, 0.04, -h / 2 + 0.05, h / 2 - 0.05)
        outline(m, neon2, 0.0, 0.0, w - 0.16, h - 0.16, 0.0, 0.014, plane="xz")
        tcol, mode, face = neon, "tube", 0.0
    # cap and the arms back to the wall
    blk(m, "sign.frame", -w / 2 - 0.03, w / 2 + 0.03, -t / 2 - 0.03, t / 2 + 0.03, h / 2,
        h / 2 + 0.06)
    wall = -0.7 - inp.get("gap", 0.0)
    for z in (h / 2 - 0.15, -h / 2 + 0.15):
        blk(m, "metal.dark", wall, -w / 2, -0.03, 0.03, z - 0.03, z + 0.03)
    blk(m, "metal.dark", wall, wall + 0.02, -0.12, 0.12, -h / 2 + 0.05, h / 2 - 0.05)
    (main, mwh), sec = _lines(inp, vertical=True)
    cols = [(main, mwh, tcol)]
    if sec:
        cols.append((sec[0], sec[1], neon2 if mode == "tube" else tcol))
    n = len(cols)
    colw = (w - 0.14) / n
    for i, (strokes, wh, col) in enumerate(cols):
        u = fit(wh, colw * 0.8, h - 0.2)
        if u <= 0:
            continue
        cx = -w / 2 + 0.07 + colw * (i + 0.5)
        for s in ((1.0,) if mode == "tube" else (-1.0, 1.0)):
            # the viewer on side s has "right" along -s x
            right = (-s, 0.0, 0.0)
            origin = (cx, s * face, wh[1] * u / 2.0)
            put_text(m, col, strokes, origin, right, (0.0, 0.0, 1.0), u, mode, (0.0, s, 0.0))


def billboard(m: Mesh, inp: dict) -> None:
    w, h = inp["w"], inp["h"]
    roof = inp["mount"] == "roof"
    two = inp.get("two_sided", roof)
    base = MT.face_slot(inp["face"])
    band = MT.face_slot(inp["colors"][0])
    text = inp["text"]
    sides = (1.0, -1.0) if two else (1.0,)
    fx = 0.15 if two else 0.35
    if two:
        blk(m, "sign.frame", -0.15, 0.15, -w / 2, w / 2, -h / 2, h / 2)
    else:
        blk(m, "sign.frame", 0.0, 0.33, -w / 2, w / 2, -h / 2, h / 2)
    (main, mwh) = GL.layout(text, "latin")
    sub_t = GL.layout(inp.get("sub", ""), "latin") if inp.get("sub") else None
    for s in sides:
        x = s * fx
        n = (s, 0.0, 0.0)
        right = (0.0, s, 0.0)
        inset = min(0.25, 0.03 * w)
        # the content face, a band, a logo disc, the headline
        y0, y1 = -w / 2 + inset, w / 2 - inset
        z0, z1 = -h / 2 + inset, h / 2 - inset
        quad_out(m, base, (x + s * 0.002, y0, z0), (x + s * 0.002, y1, z0), (x + s * 0.002, y1, z1),
                 (x + s * 0.002, y0, z1), n)
        bz0 = z0 + (z1 - z0) * 0.12
        bz1 = bz0 + (z1 - z0) * 0.2
        quad_out(m, band, (x + s * 0.006, y0, bz0), (x + s * 0.006, y1, bz0),
                 (x + s * 0.006, y1, bz1), (x + s * 0.006, y0, bz1), n)
        r = (z1 - z0) * 0.22
        cy = s * (y1 - r * 1.3) if inp.get("logo_right", True) else s * (y0 + r * 1.3)
        pts = [(x + s * 0.008, cy + r * c, z1 - r * 1.3 + r * sn) for c, sn in ring(16)]
        fan(m, MT.face_slot(inp["colors"][1]), (x + s * 0.008, cy, z1 - r * 1.3), pts, n)
        u = fit(mwh, (y1 - y0) * 0.62, (z1 - z0) * 0.32)
        if u > 0:
            ty = -s * (y1 - y0) * 0.45
            put_text(m, "sign.back" if inp.get("dark_text") else "sign.white", main,
                     (x + s * 0.008, ty, bz1 + (z1 - z0) * 0.12), right, (0.0, 0.0, 1.0), u,
                     "flat", n, 1.1)
        if sub_t is not None:
            u2 = fit(sub_t[1], (y1 - y0) * 0.6, (bz1 - bz0) * 0.6)
            if u2 > 0:
                put_text(m, base, sub_t[0], (x + s * 0.01, -s * (y1 - y0) * 0.45,
                                             bz0 + (bz1 - bz0) * 0.2), right, (0.0, 0.0, 1.0),
                         u2, "flat", n, 1.0)
        # lamps on arms along the bottom, pointing up at the face
        nl = max(2, int(w / 4.0))
        for i in range(nl):
            ly = -w / 2 + w * (i + 0.5) / nl
            blk(m, "sign.frame", x if s > 0 else x - 0.9, x + 0.9 if s > 0 else x, ly - 0.03,
                ly + 0.03, -h / 2 - 0.25, -h / 2 - 0.19)
            blk(m, "sign.frame", s * (fx + 0.8) - 0.12, s * (fx + 0.8) + 0.12, ly - 0.15,
                ly + 0.15, -h / 2 - 0.3, -h / 2 - 0.15)
            quad_out(m, "billboard.lamp", (s * (fx + 0.8) - 0.1, ly - 0.12, -h / 2 - 0.148),
                     (s * (fx + 0.8) + 0.1, ly - 0.12, -h / 2 - 0.148),
                     (s * (fx + 0.8) + 0.1, ly + 0.12, -h / 2 - 0.148),
                     (s * (fx + 0.8) - 0.1, ly + 0.12, -h / 2 - 0.148), (0.0, 0.0, 1.0))
    if roof:
        # a catwalk and the legs of the truss down to the roof (the face's foot)
        legs = max(2, int(w / 6.0) + 1)
        for i in range(legs):
            ly = -w / 2 + 0.3 + (w - 0.6) * i / (legs - 1)
            for x0 in (-0.9, 0.9):
                tube(m, "metal.galv", [(x0, ly, -h / 2), (0.0, ly, -h / 2 + h * 0.4)], 0.06, 5)
        blk(m, "metal.galv", -0.9, 0.9, -w / 2, w / 2, -h / 2 - 0.05, -h / 2)


def holo(m: Mesh, inp: dict) -> list:
    """The projector (in m, Nanite) and the image as a LOD chain of translucent planes."""
    w, h = inp["w"], inp["h"]
    roof = -h / 2 - 4.0
    c1, c2 = MT.holo_slot(inp["colors"][0]), MT.holo_slot(inp["colors"][1])
    # the projector on the roof
    blk(m, "holo.base", -1.0, 1.0, -1.4, 1.4, roof, roof + 0.8)
    pts = [(0.7 * c, 0.7 * s, roof + 0.81) for c, s in ring(12)]
    fan(m, MT.neon_slot(inp["colors"][0]), (0.0, 0.0, roof + 0.81), pts, (0.0, 0.0, 1.0))
    (main, mwh) = GL.layout(inp["text"], "latin")
    sec = None
    if inp.get("script", "latin") != "latin":
        sec = GL.layout("x" * 3, inp["script"], (inp["text"],))
    lods = []
    for lod in range(3):
        q = Mesh((0.0, 0.0))
        quad_out(q, c1, (0.0, -w / 2, -h / 2), (0.0, w / 2, -h / 2), (0.0, w / 2, h / 2),
                 (0.0, -w / 2, h / 2), (1.0, 0.0, 0.0))
        if lod < 2:
            u = fit(mwh, w * 0.85, h * 0.25)
            if u > 0:
                put_text(q, c2, main, (0.03, -mwh[0] * u / 2.0, h * 0.12), (0.0, 1.0, 0.0),
                         (0.0, 0.0, 1.0), u, "flat", (1.0, 0.0, 0.0), 1.0)
            if sec:
                u2 = fit(sec[1], w * 0.7, h * 0.35)
                if u2 > 0:
                    put_text(q, c2, sec[0], (0.03, -sec[1][0] * u2 / 2.0, -h * 0.4),
                             (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), u2, "flat", (1.0, 0.0, 0.0), 1.0)
        if lod == 0:
            # frame strips, scan bands, the beam from the projector
            for z0, z1 in ((h / 2 - 0.25, h / 2), (-h / 2, -h / 2 + 0.25)):
                quad_out(q, c2, (0.05, -w / 2, z0), (0.05, w / 2, z0), (0.05, w / 2, z1),
                         (0.05, -w / 2, z1), (1.0, 0.0, 0.0))
            for k in range(1, 6):
                z = -h / 2 + h * k / 6
                quad_out(q, c2, (-0.03, -w / 2, z), (-0.03, w / 2, z), (-0.03, w / 2, z + 0.08),
                         (-0.03, -w / 2, z + 0.08), (-1.0, 0.0, 0.0))
            for s in (-1.0, 1.0):
                quad_out(q, c1, (0.0, s * 0.5, roof + 0.8), (0.0, s * w / 2, -h / 2),
                         (0.0, s * w / 2 * 0.9, -h / 2), (0.0, s * 0.2, roof + 0.8),
                         (1.0, 0.0, 0.0))
        lods.append(q)
    return [{"suffix": ".holo", "lods": lods, "nanite": False, "screen": [1.0, 0.3, 0.08]}]


def band(m: Mesh, inp: dict) -> None:
    """A neon band on a facade corner: a backboard (the wall at x = 0), a stacked word in
    neon tubes, an outline and chevrons."""
    w, h = inp["w"], inp["h"]
    neon, neon2 = MT.neon_slot(inp["colors"][0]), MT.neon_slot(inp["colors"][1])
    blk(m, "sign.back", 0.0, 0.1, -w / 2, w / 2, -h / 2, h / 2)
    outline(m, neon2, 0.0, 0.0, w - 0.1, h - 0.1, 0.13, 0.018)
    text = inp["text"]
    script = inp.get("script", "latin")
    strokes, wh = GL.layout(text, script, (inp.get("seed", text),), vertical=True)
    room = h - 0.3 - (1.2 if h > 6.0 else 0.0)
    u = fit(wh, w * 0.7, room)
    if u > 0:
        put_text(m, neon, strokes, (0.1, 0.0, h / 2 - 0.15), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                 u, "tube", (1.0, 0.0, 0.0))
    if h > 6.0:
        for k in range(3):
            z = -h / 2 + 0.25 + k * 0.35
            tube(m, neon2, [(0.14, -w * 0.32, z), (0.14, 0.0, z + 0.22), (0.14, w * 0.32, z)],
                 0.016, 5)

