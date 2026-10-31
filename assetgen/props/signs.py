"""Sign assets (scope 5.5): an asset for every M11 sign slot, one sign path with AG6.

AG6 (`assetgen/materials/signage.py`) decides what every slot says and how it shows it: the
text (a point of interest's name, a shop name drawn for its district and use, a district's
or a brand's name), the script, the style (neon, lightbox or LED), the two colors, and for
the flat styles a cell of the city's sign pages (`signs.json`); billboards and holo-ads a
cell of its ad pages. AG8 makes the sign itself from those inputs alone (`make`), in the
slot's frame: x the direction it faces, y to its left along the face, z up, the origin the
middle of its face (M11's position).

| slot | made as |
|---|---|
| shop sign, facade | neon: tubes along the text's strokes (AG6's glyphs) on a backboard with an outline; lightbox: a box whose face shows the page cell; LED: a dark panel whose face shows the page cell; channel letters (a lightbox in a sleek district, by a hash): lit letters on a raceway; standoffs back to the wall where the brief finds it off the wall |
| shop sign, blade | neon: an open skeleton with the text stacked in tubes; lightbox and LED: a box on two arms, both faces showing the (tall) page cell |
| billboard | a steel frame, the ad's cell on its face (both faces on roofs), lamps on arms, a truss and catwalk on roofs |
| holo-ad | a projector on the roof (Nanite) and the image: the holo ad's cell on translucent emissive planes with frame and scan bands, as a non-Nanite LOD chain (`extra`); in front of a facade (M20) the projector on an arm off the wall |
| neon band | a backboard on the facade with the district's name stacked in neon tubes, an outline and chevrons |
| banner (M20) | as a neon band: a brand's name stacked in neon tubes down a tall backboard |

M20's billboards lit as neon (`lit`) have a neon tube round the face in place of the lamps
on arms. AG15 draws the large ads whole.

A face is a quad whose UV0 is its page cell (slot `page.<page>`, AG6's `sign` master;
`holopage.<page>` on the holo master), so the text, the brand and the ad are AG6's pixels;
neon and channel letters are geometry in AG6's strokes, so they read the same as AG6 would
draw them. Without the pages (no library: `--no-textures`) a lightbox or LED face is lit
flat and carries the text as flat strokes, and an ad face is lit flat.
"""

from __future__ import annotations

from ..materials import glyphs as GL
from . import materials as MT
from .shapes import Mesh, add, blk, cross, fan, mul, quad_out, ring, sub, tube

TIP_MIN = 0.007
ROW = 7.2                       # a stacked piece's height in glyph units (AG6's `_fit`)


# ---------------------------------------------------------------------------------------
# text on a plane
# ---------------------------------------------------------------------------------------

def layout(text: str, script: str, vertical: bool):
    """Strokes (glyph units: x right, y up, the block's bottom left at the origin) and the
    block's size, as AG6 lays a sign's text out: one line, or the pieces stacked one per
    row (blade signs, bands)."""
    if not vertical:
        st, tw = GL.layout(text, script)
        if tw <= 0:
            st, tw = GL.layout("OPEN", "latin")
        return st, (float(tw), 6.0)
    pieces = GL.units(text, script)[:8] or ["O"]
    rows = [GL.unit_layout(p, script) for p in pieces]
    wmax = max(float(w) for _, w in rows) or 1.0
    n = len(rows)
    out = []
    for i, (st, w) in enumerate(rows):
        ox, oy = (wmax - float(w)) / 2.0, (n - 1 - i) * ROW
        out += [[(x + ox, y + oy) for x, y in s] for s in st]
    return out, (wmax, n * ROW - (ROW - 6.0))


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
            # (two strokes of a composed glyph can land on the same millimeters)
            qk = tuple(sorted(tuple(int(round(v * 1000.0)) for v in c) for c in q))
            if qk in seen:
                continue
            seen.add(qk)
            quad_out(m, slot, *q, normal)


def place(m: Mesh, slot: str, inp: dict, center, right, up, normal, bw: float, bh: float,
          mode: str, vertical: bool = False, thick: float = 0.85) -> None:
    """A slot's text fitted into bw x bh meters round `center` on the plane (right, up)."""
    strokes, (tw, th) = layout(inp["text"], inp.get("script", "latin"), vertical)
    if tw <= 0 or th <= 0:
        return
    u = min(bw / tw, bh / th)
    if u <= 0:
        return
    origin = sub(sub(center, mul(right, tw * u / 2.0)), mul(up, th * u / 2.0))
    put_text(m, slot, strokes, origin, right, up, u, mode, normal, thick)


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


def face(m: Mesh, inp: dict, x: float, y0: float, y1: float, z0: float, z1: float, s: float,
         lit: str) -> bool:
    """A sign's flat face at x (looking along s x): its page cell when it has one (True),
    else lit flat in `lit` (False). The cell reads upright for a viewer in front."""
    n = (s, 0.0, 0.0)
    cell = inp.get("cell")
    # the viewer on side s has "right" along s y
    a, b = (x, -s * (y1 - y0) / 2.0 + (y0 + y1) / 2.0, z0), (x, s * (y1 - y0) / 2.0 + (y0 + y1) / 2.0, z0)
    c, d = (b[0], b[1], z1), (a[0], a[1], z1)
    if cell:
        u0, v0, u1, v1 = cell["uv"]
        quad_out(m, cell["slot"], a, b, c, d, n, ((u0, v1), (u1, v1), (u1, v0), (u0, v0)))
        return True
    quad_out(m, lit, a, b, c, d, n)
    return False


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


def facade(m: Mesh, inp: dict) -> None:
    w, h, look = inp["w"], inp["h"], inp["look"]
    neon, neon2 = MT.neon_slot(inp["colors"][0]), MT.neon_slot(inp["colors"][1])
    lit = MT.face_slot(inp["colors"][0])
    d = 0.15
    gap = inp.get("gap", 0.0)
    xn = (1.0, 0.0, 0.0)
    if look == "lightbox":
        blk(m, "sign.box", -d, -0.012, -w / 2, w / 2, -h / 2, h / 2)
        if not face(m, inp, 0.0, -w / 2 + 0.03, w / 2 - 0.03, -h / 2 + 0.03, h / 2 - 0.03, 1.0,
                    MT.face_slot("#f4f1ea")):
            place(m, "sign.back", inp, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), xn,
                  w * 0.86, h * 0.62, "flat")
    elif look == "led":
        blk(m, "sign.face", -d, -0.004, -w / 2, w / 2, -h / 2, h / 2)
        if not face(m, inp, 0.0, -w / 2 + 0.02, w / 2 - 0.02, -h / 2 + 0.02, h / 2 - 0.02, 1.0,
                    "sign.face"):
            place(m, lit, inp, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), xn,
                  w * 0.86, h * 0.62, "flat")
    elif look == "channel":
        blk(m, "sign.box", -d, -d + 0.06, -w / 2, w / 2, -h * 0.12, h * 0.12)
        place(m, lit, inp, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), xn, w * 0.9,
              h * 0.8, "flat")
        blk(m, "sign.box", -d, -0.02, -w / 2 + 0.05, w / 2 - 0.05, -h / 2, h / 2)
    else:
        blk(m, "sign.back", -d, -d + 0.04, -w / 2, w / 2, -h / 2, h / 2)
        outline(m, neon2, 0.0, 0.0, w - 0.08, h - 0.08, -d + 0.07, 0.015)
        blk(m, "sign.box", -d - 0.02, -d, w / 2 - 0.35, w / 2 - 0.1, -h / 2 + 0.05, -h / 2 + 0.25)
        place(m, neon, inp, (-d + 0.04, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), xn,
              w * 0.86, h * 0.62, "tube")
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
    lit = MT.face_slot(inp["colors"][0])
    if look == "neon":
        # neon on an open skeleton: a frame round the sign, the tubes once in its middle
        # plane (read from both sides, mirrored from the back, as on a real one)
        for z0, z1 in ((-h / 2, -h / 2 + 0.05), (h / 2 - 0.05, h / 2)):
            blk(m, "sign.frame", -w / 2, w / 2, -0.04, 0.04, z0, z1)
        for x0, x1 in ((-w / 2, -w / 2 + 0.05), (w / 2 - 0.05, w / 2)):
            blk(m, "sign.frame", x0, x1, -0.04, 0.04, -h / 2 + 0.05, h / 2 - 0.05)
        outline(m, neon2, 0.0, 0.0, w - 0.16, h - 0.16, 0.0, 0.014, plane="xz")
        place(m, neon, inp, (0.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
              (0.0, 1.0, 0.0), w * 0.72, h * 0.9, "tube", vertical=True)
    else:
        box = "sign.box" if look == "lightbox" else "sign.face"
        blk(m, box, -w / 2, w / 2, -t / 2 + 0.012, t / 2 - 0.012, -h / 2, h / 2)
        for s in (-1.0, 1.0):
            # each face in the blade's xz plane, read from its side: the frame turned so
            # that face's normal is the frame's x
            g = Mesh((0.0, 0.0))
            ok = face(g, inp, 0.0, -w / 2 + 0.04, w / 2 - 0.04, -h / 2 + 0.04, h / 2 - 0.04, 1.0,
                      MT.face_slot("#f4f1ea") if look == "lightbox" else "sign.face")
            if not ok:
                place(g, "sign.back" if look == "lightbox" else lit, inp, (0.0, 0.0, 0.0),
                      (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), w * 0.72, h * 0.9,
                      "flat", vertical=True)
            _turned(m, g, s, t / 2)
    # cap and the arms back to the wall
    blk(m, "sign.frame", -w / 2 - 0.03, w / 2 + 0.03, -t / 2 - 0.03, t / 2 + 0.03, h / 2,
        h / 2 + 0.06)
    wall = -0.7 - inp.get("gap", 0.0)
    for z in (h / 2 - 0.15, -h / 2 + 0.15):
        blk(m, "metal.dark", wall, -w / 2, -0.03, 0.03, z - 0.03, z + 0.03)
    blk(m, "metal.dark", wall, wall + 0.02, -0.12, 0.12, -h / 2 + 0.05, h / 2 - 0.05)


def _turned(m: Mesh, g: Mesh, s: float, off: float) -> None:
    """g (a face made looking along +x) put on the blade's side s: its x to s y at `off`,
    its y to -s x."""
    si = 1 if s > 0 else -1
    shift = int(round(s * off * 1000.0))
    for name, sl in g.slots.items():
        dst = m._slot(name)
        base = len(dst.pos)
        for (x, y, z), uv in zip(sl.pos, sl.uv):
            dst.pos.append((-si * y, si * x + shift, z))
            dst.uv.append(uv)
        for n in sl.nrm:
            dst.nrm.append(None if n is None else (-si * n[1], si * n[0], n[2]))
        dst.auto = dst.auto or sl.auto
        dst.idx += [i + base for i in sl.idx]


def billboard(m: Mesh, inp: dict) -> None:
    w, h = inp["w"], inp["h"]
    roof = inp["mount"] == "roof"
    two = inp.get("two_sided", roof)
    sides = (1.0, -1.0) if two else (1.0,)
    fx = 0.15 if two else 0.35
    if two:
        blk(m, "sign.frame", -0.15, 0.15, -w / 2, w / 2, -h / 2, h / 2)
    else:
        blk(m, "sign.frame", 0.0, 0.33, -w / 2, w / 2, -h / 2, h / 2)
    for s in sides:
        x = s * fx
        inset = min(0.25, 0.03 * w)
        face(m, inp, x + s * 0.002, -w / 2 + inset, w / 2 - inset, -h / 2 + inset,
             h / 2 - inset, s, MT.face_slot(inp["colors"][0]))
        if inp.get("lit") == "neon":
            # (M20: lit as neon, a tube round its face; AG15 draws them whole)
            outline(m, MT.neon_slot(inp["colors"][-1]), 0.0, 0.0, w - inset, h - inset,
                    x + s * 0.03, min(0.06, max(0.02, 0.004 * min(w, h))))
            continue
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
    """The projector (in m, Nanite) and the image as a LOD chain of translucent planes; M20's
    holo-boards in front of a facade (`mount` front) project from a box on an arm off the
    wall (`off` behind the image) under the image."""
    w, h = inp["w"], inp["h"]
    roof = -h / 2 - 4.0
    c1, c2 = MT.holo_slot(inp["colors"][0]), MT.holo_slot(inp["colors"][1])
    if inp["mount"] == "front":
        wall = -inp.get("off", 3.0)
        roof = -h / 2 - 1.2
        blk(m, "metal.dark", wall, -0.4, -0.08, 0.08, roof + 0.25, roof + 0.4)
        blk(m, "holo.base", -1.0, 0.2, -0.9, 0.9, roof, roof + 0.6)
        pts = [(-0.4 + 0.45 * c, 0.45 * s, roof + 0.61) for c, s in ring(12)]
        fan(m, MT.neon_slot(inp["colors"][0]), (-0.4, 0.0, roof + 0.61), pts,
            (0.0, 0.0, 1.0))
    else:
        # the projector on the roof
        blk(m, "holo.base", -1.0, 1.0, -1.4, 1.4, roof, roof + 0.8)
        pts = [(0.7 * c, 0.7 * s, roof + 0.81) for c, s in ring(12)]
        fan(m, MT.neon_slot(inp["colors"][0]), (0.0, 0.0, roof + 0.81), pts, (0.0, 0.0, 1.0))
    lods = []
    for lod in range(3):
        q = Mesh((0.0, 0.0))
        face(q, inp, 0.0, -w / 2, w / 2, -h / 2, h / 2, 1.0, c1)
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
    """A neon band on a facade corner: a backboard (the wall at x = 0), its text stacked in
    neon tubes, an outline and chevrons."""
    w, h = inp["w"], inp["h"]
    neon, neon2 = MT.neon_slot(inp["colors"][0]), MT.neon_slot(inp["colors"][1])
    blk(m, "sign.back", 0.0, 0.1, -w / 2, w / 2, -h / 2, h / 2)
    outline(m, neon2, 0.0, 0.0, w - 0.1, h - 0.1, 0.13, 0.018)
    room = h - 0.3 - (1.2 if h > 6.0 else 0.0)
    place(m, neon, inp, (0.1, 0.0, h / 2 - 0.15 - room / 2.0), (0.0, 1.0, 0.0),
          (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), w * 0.7, room, "tube", vertical=h > w)
    if h > 6.0:
        for k in range(3):
            z = -h / 2 + 0.25 + k * 0.35
            tube(m, neon2, [(0.14, -w * 0.32, z), (0.14, 0.0, z + 0.22), (0.14, w * 0.32, z)],
                 0.016, 5)
