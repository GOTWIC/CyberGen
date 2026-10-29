"""Roof equipment and facade details (scope 5.1.3, AG4) as parts of the kit (`parts.py`).

Roof equipment, one asset per M3 roof item (in its own frame: x along the building axis the
item is turned to, y across it, z up from the roof it stands on, millimeters):

| family | what it is |
|---|---|
| ac_unit | a packaged rooftop unit on base rails: fan shrouds on top (`fans`), a louvered casing (`box`) or old condensers on a stand (`old`) |
| water_tank | a timber barrel tank on a steel stand with a conical roof (`timber`), a steel cylinder on a plinth (`steel`) or a sectional panel tank on a skid (`panel`) |
| antenna | a triangular lattice mast (`lattice`), a tapered pole with cross arms and whips (`whip`) or a pole with two dishes (`dish`), an aviation light on top |
| pad | a helipad or an AV pad: the deck on a steel frame, its markings (the helipad's border, aiming circle and H; the AV pad's ring and cross) and edge lights |
| penthouse | the mechanical penthouse: louver bands, a door, a roof lip, exhaust stacks |
| hut | a roof access hut (the stair bulkhead): a door under a canopy, a lamp |
| dunnage | the steel frame an item stands on where the roof under it slopes (AG4's pitched roofs) |
| billboard_frame | an empty billboard frame (posts, rails, struts, catwalk): the neon era's crown where no billboard stands |
| roof_vent | vent stacks, mushroom vents and louvered boxes |
| skylight | a dome or flat skylight on its curb |

AG8 draws the billboards of M3's roof items (its sign asset has the frame, truss, catwalk
and legs), so a `billboard` roof item takes no AG4 mesh.

Facade details (x along the facade, y into the wall, outward negative, z up):

| family | what it is |
|---|---|
| escape | a fire escape: grated landings at the floor lines, stairs between them, a drop ladder under the lowest |
| duct | a kitchen exhaust duct from over a shop up past the roof, with a rain hood |
| wall_vent | a louvered wall vent |
| conduit | a bundle of cables along a floor line, clipped to the wall, dropping at its end |
| camera | a CCTV camera on its arm (a bullet or a dome) |
| landing | a skybridge's landing door: a frame and two glazed leaves |

AG3 draws the downpipes of blind and fire walls (its `pipe` family); AG4 puts the same pipe
at the corners of every flat-roofed building it suits. AG8 draws AC units on facades, wall
lights, signs, awnings, scaffolding and the overhead cables between facades; AG4's
conduits run along one wall only.

Roof equipment (`ROOF`) is always instanced (`INSTANCE_ALWAYS`): one mesh per kind and
parameters, the city's units share a handful of them, and the exporter gathers them per
tile as instanced kinds; their slots take no building tint (the tile's instances carry no
building's Custom Primitive Data). Penthouses and billboard frames, one size per building, are merged
into the shell.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from . import parts as PT
from .parts import _cross, _sub, box, face, frame_y, ngon, prism

OV = PT.OVERLAP


# ---------------------------------------------------------------------------
# A few closed solids beyond the kit's boxes and prisms
# ---------------------------------------------------------------------------

def _unit(v):
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / L, v[1] / L, v[2] / L)


def bar(b, slot: str, p0, p1, w: int, h: int | None = None) -> None:
    """A closed beam of section w x h from p0 to p1 (mm)."""
    h = h or w
    d = _sub(p1, p0)
    L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
    if L < 20:
        return
    e = (d[0] / L, d[1] / L, d[2] / L)
    up = (0.0, 0.0, 1.0) if abs(e[2]) < 0.95 else (1.0, 0.0, 0.0)
    p = _unit(_cross(e, up))
    q = _cross(e, p)
    hw, hh = w / 2.0, h / 2.0

    def c(base, sp, sq):
        return tuple(int(round(base[k] + p[k] * sp + q[k] * sq)) for k in range(3))
    A = [c(p0, -hw, -hh), c(p0, hw, -hh), c(p0, hw, hh), c(p0, -hw, hh)]
    B = [c(p1, -hw, -hh), c(p1, hw, -hh), c(p1, hw, hh), c(p1, -hw, hh)]
    if len(set(A + B)) < 8:
        return
    mid = tuple((p0[k] + p1[k]) / 2.0 for k in range(3))
    b.new_part()
    for f in ((A[0], A[3], A[2], A[1]), (B[0], B[1], B[2], B[3]), (A[0], A[1], B[1], B[0]),
              (A[1], A[2], B[2], B[1]), (A[2], A[3], B[3], B[2]), (A[3], A[0], B[0], B[3])):
        n = _cross(_sub(f[1], f[0]), _sub(f[3], f[0]))
        ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        if ln == 0:
            continue
        n = (n[0] / ln, n[1] / ln, n[2] / ln)
        cf = tuple(sum(v[k] for v in f) / 4.0 for k in range(3))
        if (cf[0] - mid[0]) * n[0] + (cf[1] - mid[1]) * n[1] + (cf[2] - mid[2]) * n[2] < 0:
            n = (-n[0], -n[1], -n[2])
        face(b, slot, list(f), n)


def cyl(b, slot: str, cx: int, cy: int, r: int, z0: int, z1: int, n: int = 12) -> None:
    prism(b, slot, ngon(cx, cy, r, n, 0.5), [], z0, z1, "z")


def cone(b, slot: str, cx: int, cy: int, r: int, z0: int, z1: int, n: int = 12) -> None:
    """A closed cone from a ring of radius r at z0 to its apex at z1 (over or under it)."""
    ring = [(p[0], p[1], z0) for p in ngon(cx, cy, r, n, 0.5)]
    apex = (cx, cy, z1)
    sg = 1.0 if z1 > z0 else -1.0
    b.new_part()
    face(b, slot, ring, (0.0, 0.0, -sg))
    for k in range(n):
        p0, p1 = ring[k], ring[(k + 1) % n]
        nn = _cross(_sub(p1, p0), _sub(apex, p0))
        L = math.sqrt(nn[0] * nn[0] + nn[1] * nn[1] + nn[2] * nn[2])
        face(b, slot, [p0, p1, apex], (sg * nn[0] / L, sg * nn[1] / L, sg * nn[2] / L))


def annulus(b, slot: str, r0: int, r1: int, z0: int, z1: int, n: int = 24) -> None:
    prism(b, slot, ngon(0, 0, r1, n, 0.5), [ngon(0, 0, r0, n, 0.5)], z0, z1, "z")


# ---------------------------------------------------------------------------
# Roof equipment
# ---------------------------------------------------------------------------

def gen_ac_unit(p: dict, b) -> None:
    w, d, h, st = p["w"], p["d"], p["h"], p["style"]
    if st == "old":
        # two condensers side by side on a low steel stand
        for x in (-w // 2 + 60, w // 2 - 60):
            for y in (-d // 2 + 60, d // 2 - 60):
                box(b, "steel", x - 30, x + 30, y - 30, y + 30, 0, 350)
        box(b, "steel", -w // 2, w // 2, -d // 2, d // 2, 350, 410)
        cw = (w - 120) // 2
        for k in (0, 1):
            x0 = -w // 2 + 40 + k * (cw + 40)
            box(b, "equipment", x0, x0 + cw, -d // 2 + 80, d // 2 - 80, 410, h)
            r = min(cw, h - 410) * 36 // 100
            prism(b, "equip_dark", ngon(x0 + cw // 2, (410 + h) // 2, r, 12, 0.5), [],
                  -d // 2 + 50, -d // 2 + 80, "y")
        return
    for y in (-d // 2 + 100, d // 2 - 200):
        box(b, "steel", -w // 2, w // 2, y, y + 100, 0, 120)
    box(b, "equipment", -w // 2, w // 2, -d // 2, d // 2, 120, h - 60)
    if st == "fans":
        r = min(d * 38 // 100, w * 20 // 100)
        for x in (-w // 4, w // 4):
            cyl(b, "equip_dark", x, 0, r, h - 60, h, 12)
            box(b, "steel", x - r, x + r, -15, 15, h, h + 20)
        box(b, "louver", -w // 2 + 120, w // 2 - 120, -d // 2 - 20, -d // 2, 250, h - 260)
    else:
        box(b, "louver", -w // 2 + 150, w // 2 - 150, -d // 2 - 20, -d // 2, 300, h - 200)
        box(b, "louver", -w // 2 + 150, w // 2 - 150, d // 2, d // 2 + 20, 300, h - 200)
        box(b, "equip_dark", -w // 3, w // 3, -d // 3, d // 3, h - 60, h)


def _ladder(b, slot: str, x: int, y: int, z0: int, z1: int, wide: int = 400) -> None:
    for dx in (-wide // 2, wide // 2):
        box(b, slot, x + dx - 20, x + dx + 20, y - 20, y + 20, z0, z1)
    z = z0 + 300
    while z < z1 - 100:
        box(b, slot, x - wide // 2 + 20, x + wide // 2 - 20, y - 12, y + 12, z, z + 25)
        z += 300


def gen_water_tank(p: dict, b) -> None:
    r, h, st = p["r"], p["h"], p["style"]
    if st == "timber":
        hs = h * 28 // 100
        for a in range(4):
            x, y = ngon(0, 0, r * 70 // 100, 4, 0.5)[a]
            box(b, "steel", x - 60, x + 60, y - 60, y + 60, 0, hs)
        box(b, "steel", -r - 150, r + 150, -r - 150, r + 150, hs, hs + 120)
        z0 = hs + 120
        hr = r * 45 // 100
        z1 = h - hr
        cyl(b, "tank_timber", 0, 0, r, z0, z1, 16)
        for f in (15, 50, 85):
            z = z0 + (z1 - z0) * f // 100
            annulus(b, "steel", r - 10, r + 20, z, z + 50, 16)
        cone(b, "tank_roof", 0, 0, r + 80, z1, h, 16)
        _ladder(b, "steel", 0, -r - 60, 0, z1)
        return
    if st == "steel":
        box(b, "pad_deck", -r - 100, r + 100, -r - 100, r + 100, 0, 300)
        cyl(b, "tank_steel", 0, 0, r, 300, h - r * 25 // 100, 16)
        cone(b, "tank_steel", 0, 0, r, h - r * 25 // 100, h, 16)
        _ladder(b, "steel", 0, -r - 50, 300, h - r * 25 // 100)
        return
    # a sectional panel tank on a steel skid, ribbed every metre
    box(b, "steel", -r, r, -r, r, 0, 250)
    box(b, "tank_panel", -r + 50, r - 50, -r + 50, r - 50, 250, h)
    k = max(2, (2 * r) // 1000)
    for j in range(1, k):
        x = -r + 50 + (2 * r - 100) * j // k
        box(b, "tank_panel", x - 30, x + 30, -r + 20, -r + 50, 250, h)
        box(b, "tank_panel", x - 30, x + 30, r - 50, r - 20, 250, h)
        box(b, "tank_panel", -r + 20, -r + 50, x - 30, x + 30, 250, h)
        box(b, "tank_panel", r - 50, r - 20, x - 30, x + 30, 250, h)
    box(b, "steel", -300, 300, -300, 300, h, h + 60)


def gen_antenna(p: dict, b) -> None:
    h, st = p["h"], p["style"]
    box(b, "steel", -300, 300, -300, 300, 0, 200)
    top = h - 150
    if st == "lattice":
        rr = 220
        legs = [(int(round(rr * float(M.cos(M.radians(a))))),
                 int(round(rr * float(M.sin(M.radians(a)))))) for a in (90, 210, 330)]
        for x, y in legs:
            bar(b, "antenna", (x, y, 200), (x, y, top), 50)
        z = 200
        step = 1500
        k = 0
        while z + step <= top:
            for i in range(3):
                (x0, y0), (x1, y1) = legs[i], legs[(i + 1) % 3]
                bar(b, "antenna", (x0, y0, z + step), (x1, y1, z + step), 30)
                if k % 2 == 0:
                    bar(b, "antenna", (x0, y0, z), (x1, y1, z + step), 25)
                else:
                    bar(b, "antenna", (x1, y1, z), (x0, y0, z + step), 25)
            z += step
            k += 1
        box(b, "lamp_red", -60, 60, -60, 60, top, h)
        return
    if st == "whip":
        z = 200
        for r, frac in ((90, 45), (65, 35), (40, 20)):
            dz = (top - 200) * frac // 100
            cyl(b, "antenna", 0, 0, r, z, z + dz, 8)
            z += dz
        for f in (70, 85):
            za = 200 + (top - 200) * f // 100
            box(b, "antenna", -650, 650, -20, 20, za, za + 40)
            for x in (-630, 630):
                box(b, "antenna", x - 12, x + 12, -12, 12, za + 40, za + 840)
        box(b, "lamp_red", -60, 60, -60, 60, top, h)
        return
    cyl(b, "antenna", 0, 0, 80, 200, top, 8)
    for zf, side in ((55, -1), (80, 1)):
        za = 200 + (top - 200) * zf // 100
        prism(b, "dish", ngon(0, za, 450, 16, 0.5), [], *sorted((side * 120, side * 160)),
              "y")
        bar(b, "antenna", (0, side * 160, za), (0, side * 520, za), 30)
    box(b, "lamp_red", -60, 60, -60, 60, top, h)


def gen_pad(p: dict, b) -> None:
    """A helipad or an AV pad of side s, its deck's top h over the roof."""
    s, h, kind = p["s"], p["h"], p["kind"]
    hs = s // 2
    t = 200
    k = max(2, s // 5000)
    for i in range(k + 1):
        for j in range(k + 1):
            x = -hs + 400 + (s - 800) * i // k
            y = -hs + 400 + (s - 800) * j // k
            box(b, "steel", x - 100, x + 100, y - 100, y + 100, 0, h - t)
    box(b, "pad_deck", -hs, hs, -hs, hs, h - t, h)
    m = h + 8
    lw = 300
    # the border line, 0.5 m in from the edge
    e = hs - 500
    for x0, x1, y0, y1 in ((-e, e, -e, -e + lw), (-e, e, e - lw, e), (-e, -e + lw, -e + lw,
                                                                      e - lw),
                           (e - lw, e, -e + lw, e - lw)):
        box(b, "pad_paint_white", x0, x1, y0, y1, h, m)
    ring = s * 36 // 100
    annulus(b, "pad_paint_yellow", ring - 450, ring, h, m, 32)
    if kind == "helipad":
        # the H: 3 m tall, 1.8 m wide
        box(b, "pad_paint_white", -1200, -700, -1500, 1500, h, m)
        box(b, "pad_paint_white", 700, 1200, -1500, 1500, h, m)
        box(b, "pad_paint_white", -700, 700, -250, 250, h, m)
        lamp = "lamp_green"
    else:
        # a cross and a center square
        box(b, "pad_paint_white", -ring + 700, ring - 700, -200, 200, h, m)
        box(b, "pad_paint_white", -200, 200, -ring + 700, -200, h, m)
        box(b, "pad_paint_white", -200, 200, 200, ring - 700, h, m)
        lamp = "lamp_amber"
    n = max(3, s // 3000)
    e = hs - 250
    for i in range(n):
        c = -e + 2 * e * i // n
        for x, y in ((c, -e), (e, c), (-c, e), (-e, -c)):
            box(b, lamp, x - 75, x + 75, y - 75, y + 75, h, h + 80)


STACK_UP = 1200      # a penthouse's exhaust stacks rise this (and a 0.1 m cap) over it


def gen_penthouse(p: dict, b) -> None:
    w, d, h = p["w"], p["d"], p["h"]
    hw, hd = w // 2, d // 2
    box(b, "roof_wall", -hw, hw, -hd, hd, 0, h - 300)
    lip = 150
    box(b, "roof_wall", -hw, hw, -hd, -hd + lip, h - 300, h)
    box(b, "roof_wall", -hw, hw, hd - lip, hd, h - 300, h)
    box(b, "roof_wall", -hw, -hw + lip, -hd + lip, hd - lip, h - 300, h)
    box(b, "roof_wall", hw - lip, hw, -hd + lip, hd - lip, h - 300, h)
    if w >= 2500 and h >= 3000:
        for y0, y1 in ((-hd - 40, -hd), (hd, hd + 40)):
            box(b, "equip_dark", -hw + 600, hw - 600, y0, y1, h * 45 // 100, h - 600)
    if d >= 1600:
        box(b, "equip_dark", -hw - 40, -hw, -500, 500, 0, 2200)
        box(b, "equip_steel", -hw - 900, -hw, -700, 700, 2300, 2400)
    if not p.get("stacks", 1):
        return               # (under a corridor with no room for them: no exhaust stacks)
    for x in ((-hw // 2, hw // 2) if w >= 3000 else (0,)):
        cyl(b, "equip_steel", x, hd // 3, 200, h - 300, h + STACK_UP, 10)
        cyl(b, "equip_steel", x, hd // 3, 260, h + STACK_UP, h + STACK_UP + 100, 10)


def gen_hut(p: dict, b) -> None:
    w, d, h = p["w"], p["d"], p["h"]
    hw, hd = w // 2, d // 2
    box(b, "roof_wall", -hw, hw, -hd, hd, 0, h - 150)
    box(b, "tank_roof", -hw - 50, hw + 50, -hd - 300, hd + 50, h - 150, h)
    box(b, "door_metal", -450, 450, -hd - 30, -hd, 0, 2100)
    box(b, "lamp_white", -100, 100, -hd - 120, -hd, 2200, 2300)
    cyl(b, "steel", hw - 300, hd - 300, 60, h, h + 600, 8)


def gen_dunnage(p: dict, b) -> None:
    w, d, leg = p["w"], p["d"], p["leg"]
    for x in (-w // 2 + 100, w // 2 - 100):
        for y in (-d // 2 + 100, d // 2 - 100):
            box(b, "steel", x - 40, x + 40, y - 40, y + 40, 0, leg - 100)
    for y in (-d // 2 + 100, d // 2 - 100):
        box(b, "steel", -w // 2, w // 2, y - 50, y + 50, leg - 100, leg)


def gen_billboard_frame(p: dict, b) -> None:
    """An empty billboard frame w wide with a face h tall on 1.5 m legs, struts reaching
    `back` behind it, a catwalk in front (y < 0)."""
    w, h, back = p["w"], p["h"], p["back"]
    hw = w // 2
    z0 = 1500
    n = max(2, w // 4000 + 1)
    xs = [-hw + 150 + (w - 300) * j // (n - 1) for j in range(n)]
    slot = p.get("slot", "equip_rust")
    for x in xs:
        box(b, slot, x - 100, x + 100, -100, 100, 0, z0 + h)
        bar(b, slot, (x, 80, z0 + h - 400), (x, back, 0), 120)
    for z in (z0, z0 + h // 2, z0 + h - 200):
        box(b, slot, -hw, hw, -100, 100, z, z + 200)
    for x0, x1 in zip(xs, xs[1:]):
        bar(b, slot, (x0, -110, z0 + 200), (x1, -110, z0 + h - 200), 60)
    box(b, "equip_steel", -hw, hw, -800, -100, z0 - 60, z0)
    for x in range(-hw, hw + 1, 1500):
        box(b, "equip_steel", x - 20, x + 20, -800, -760, z0, z0 + 1000)
    box(b, "equip_steel", -hw, hw, -800, -760, z0 + 960, z0 + 1000)


def gen_roof_vent(p: dict, b) -> None:
    st = p["style"]
    if st == "stack":
        cyl(b, "steel", 0, 0, 60, 0, 700, 8)
        cyl(b, "steel", 0, 0, 90, 700, 760, 8)
    elif st == "mushroom":
        cyl(b, "equipment", 0, 0, 160, 0, 420, 12)
        cyl(b, "equipment", 0, 0, 320, 420, 500, 12)
        cone(b, "equipment", 0, 0, 320, 500, 640, 12)
    else:
        box(b, "equipment", -300, 300, -300, 300, 0, 380)
        box(b, "louver", -260, 260, -320, -300, 80, 320)
        box(b, "louver", -260, 260, 300, 320, 80, 320)
        box(b, "equipment", -360, 360, -360, 360, 380, 440)


def gen_skylight(p: dict, b) -> None:
    w, d = p["w"], p["d"]
    hw, hd = w // 2, d // 2
    box(b, "roof_wall", -hw, hw, -hd, hd, 0, 300)
    if p["style"] == "dome":
        top = 300 + min(w, d) * 30 // 100
        base = [(-hw + 60, -hd + 60, 300), (hw - 60, -hd + 60, 300), (hw - 60, hd - 60, 300),
                (-hw + 60, hd - 60, 300)]
        ridge = [(-(hw - hd) // 2, 0, top), ((hw - hd) // 2, 0, top)] if hw > hd + 100 \
            else None
        b.new_part()
        face(b, "skylight", base, (0.0, 0.0, -1.0))
        apex = (0, 0, top)
        if ridge is None:
            for k in range(4):
                p0, p1 = base[k], base[(k + 1) % 4]
                nn = _cross(_sub(p1, p0), _sub(apex, p0))
                L = math.sqrt(nn[0] * nn[0] + nn[1] * nn[1] + nn[2] * nn[2])
                face(b, "skylight", [p0, p1, apex], (nn[0] / L, nn[1] / L, nn[2] / L))
        else:
            ra, rb = ridge
            for f in ([base[0], base[1], rb, ra], [base[1], base[2], rb], [base[2], base[3],
                                                                           ra, rb],
                      [base[3], base[0], ra]):
                nn = _cross(_sub(f[1], f[0]), _sub(f[2], f[0]))
                L = math.sqrt(nn[0] * nn[0] + nn[1] * nn[1] + nn[2] * nn[2])
                face(b, "skylight", f, (nn[0] / L, nn[1] / L, nn[2] / L))
    else:
        box(b, "skylight", -hw + 60, hw - 60, -hd + 60, hd - 60, 300, 360)
        box(b, "equip_steel", -hw + 40, hw - 40, -20, 20, 300, 380)


# ---------------------------------------------------------------------------
# Facade details
# ---------------------------------------------------------------------------

def gen_escape(p: dict, b) -> None:
    """A fire escape w wide and d out, a landing at each height of `zs` (from the lowest),
    stairs between them alternating ends, a drop ladder `ladder` long under the lowest."""
    w, d, zs = p["w"], p["d"], p["zs"]
    hw = w // 2
    y0, y1 = -d, -60
    for z in zs:
        box(b, "escape", -hw, hw, y0, y1, z - 60, z)
        n = max(2, w // 1200)
        for j in range(n + 1):
            x = -hw + (w - 40) * j // n
            box(b, "escape", x, x + 40, y0, y0 + 40, z, z + 960)
        box(b, "escape", -hw, hw, y0, y0 + 40, z + 960, z + 1000)
        box(b, "escape", -hw, -hw + 40, y0 + 40, y1, z + 960, z + 1000)
        box(b, "escape", hw - 40, hw, y0 + 40, y1, z + 960, z + 1000)
        for x in (-hw + 200, hw - 200):
            bar(b, "escape", (x, -30, z - 800), (x, y0 + 120, z - 80), 50)
    run = 0
    for k in range(len(zs) - 1):
        za, zb = zs[k], zs[k + 1]
        dz = zb - za
        run = min(w - 900, dz * 70 // 100)
        if k % 2 == 0:
            xa, xb = -hw + 300, -hw + 300 + run
        else:
            xa, xb = hw - 300, hw - 300 - run
        ya, yb = y0 + 80, y0 + d // 2
        for yy in (ya, yb):
            bar(b, "escape", (xa, yy, za), (xb, yy, zb), 40, 120)
        n = max(4, dz // 230)
        for i in range(1, n):
            x = xa + (xb - xa) * i // n
            z = za + dz * i // n
            lo, hi = sorted((x - 110, x + 110))
            box(b, "escape", lo, hi, ya + 25, yb - 25, z - 30, z)
    lad = p.get("ladder", 0)
    if lad > 400:
        x = hw - 500
        for dx in (-220, 220):
            box(b, "escape", x + dx - 20, x + dx + 20, y0 + 60, y0 + 100, -lad, -60)
        z = -lad + 150
        while z < -160:
            box(b, "escape", x - 200, x + 200, y0 + 65, y0 + 95, z, z + 25)
            z += 300


def gen_duct(p: dict, b) -> None:
    w, dd, h = p["w"], p["dd"], p["h"]
    box(b, "duct", -w // 2, w // 2, -dd - 60, -60, 0, h)
    box(b, "duct", -w // 2, w // 2, -60, 0, 0, w)
    z = 1500
    while z < h - 500:
        box(b, "steel", -w // 2 - 40, w // 2 + 40, -70, 0, z, z + 60)
        z += 2000
    box(b, "duct", -w // 2 - 80, w // 2 + 80, -dd - 140, -20, h, h + 60)
    box(b, "duct", -w // 2 + 40, w // 2 - 40, -dd - 20, -100, h + 60, h + 220)
    box(b, "duct", -w // 2 - 80, w // 2 + 80, -dd - 140, -20, h + 220, h + 280)


def gen_wall_vent(p: dict, b) -> None:
    w, h = p["w"], p["h"]
    box(b, "duct", -w // 2, w // 2, -30, 0, 0, h)
    k = max(2, h // 70)
    for j in range(1, k):
        z = h * j // k
        box(b, "louver", -w // 2 + 25, w // 2 - 25, -55, -30, z - 12, z + 12)


def gen_conduit(p: dict, b) -> None:
    """Cables from x 0 to L along the wall at z 0 (k of them, one above another), clipped
    every 1.5 m, dropping `drop` at x L."""
    L, k, drop = p["L"], p["k"], p["drop"]
    for i in range(k):
        y0 = -40 - 30 * i
        z = -30 * i
        box(b, "cable", 0, L, y0 - 22, y0, z - 22, z)
        if drop > 300:
            box(b, "cable", L - 22 - 30 * i, L - 30 * i, y0 - 22, y0, z - drop, z - 22)
    x = 0
    while x <= L - 60:
        box(b, "cable", x, x + 60, -40 - 30 * k, 0, -30 * k + 10, 15)
        x += 1500


def gen_camera(p: dict, b) -> None:
    box(b, "camera", -60, 60, -20, 0, -100, 100)
    box(b, "camera", -25, 25, -350, -20, -25, 25)
    if p["style"] == "dome":
        cyl(b, "camera", 0, -420, 110, -90, -25, 12)
        cone(b, "camera_lens", 0, -420, 110, -90, -170, 12)
    else:
        box(b, "camera", -60, 60, -650, -300, -110, 10)
        box(b, "camera_lens", -40, 40, -665, -650, -80, -20)
        box(b, "camera", -70, 70, -680, -280, 10, 30)


def gen_landing(p: dict, b) -> None:
    """A skybridge's landing door in its opening (w x h, the reveal r): a frame and two
    glazed leaves."""
    w, h, r = p["w"], p["h"], p["r"]
    y1 = r - 3
    y0 = max(r - 120, 6)
    frame_y(b, "frame", -w // 2 - OV, w // 2 + OV, -OV, h + OV, 90 + OV, y0, y1)
    from .frontparts import _door_leaf
    hw = w // 2 - 90
    _door_leaf(b, "glass", "door_metal", -hw, -8, 0, h - 90, y0 + 20, y0 + 60)
    _door_leaf(b, "glass", "door_metal", 8, hw, 0, h - 90, y0 + 20, y0 + 60)


ROOF = {"ac_unit": gen_ac_unit, "water_tank": gen_water_tank, "antenna": gen_antenna,
        "pad": gen_pad, "hut": gen_hut, "dunnage": gen_dunnage, "roof_vent": gen_roof_vent,
        "skylight": gen_skylight}
MERGED_ROOF = {"penthouse": gen_penthouse, "billboard_frame": gen_billboard_frame}
FACADE = {"escape": gen_escape, "duct": gen_duct, "wall_vent": gen_wall_vent,
          "conduit": gen_conduit, "camera": gen_camera, "landing": gen_landing}
REACH = {**{k: "roof" for k in ROOF}, **{k: "roof" for k in MERGED_ROOF},
         "escape": "deep", "duct": "strip", "wall_vent": "flush", "conduit": "flush",
         "camera": "strip", "landing": "flush"}
SUB = {"ac_unit": "style", "water_tank": "style", "antenna": "style", "pad": "kind",
       "roof_vent": "style", "skylight": "style"}
FIXED = {"hut": "access", "dunnage": "frame", "penthouse": "mechanical",
         "billboard_frame": "empty", "escape": "fire", "duct": "exhaust", "wall_vent": "grille",
         "conduit": "cables", "landing": "skybridge"}
# instanced whatever their count (the exporter's roof equipment kinds, per tile)
INSTANCE_ALWAYS = frozenset(ROOF)
# the slots of roof equipment merged into a shell (penthouses, billboard frames), which the
# envelope check holds to its roof rule: on a roof, or inside the masses
ROOF_SLOTS = ("equipment", "mast", "equip_dark", "equip_rust", "equip_steel", "roof_wall")


def register() -> None:
    for k, g in {**ROOF, **MERGED_ROOF, **FACADE}.items():
        PT.GEN[k] = g
        PT.REACH[k] = REACH[k]
    PT.TYPE_KEY.update(SUB)
    PT.TYPE_SUB.update(FIXED)
    PT.INSTANCE_ALWAYS = INSTANCE_ALWAYS


register()
