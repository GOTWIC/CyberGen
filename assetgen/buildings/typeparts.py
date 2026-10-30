"""Parts of the type generators and hero landmarks (scope 5.1.5, AG5) in the kit of
`parts.py`: each in its own frame (millimeters; on a facade x along it, y into the wall,
outward negative, z up; on a roof or round a mass x and y along the frame it is turned to),
from quantized parameters, closed, named by its parameters.

| family | what it is |
|---|---|
| eave | a tier's roof skirt (temple halls, pagodas): from the upper tier's wall down and out past the lower tier's, its corners curled, tiled on top, a soffit under it |
| pillar | a column: lacquered on a stone base with a bracket capital (`temple`), round with a base and a cap ring (`round`), a square steel section (`steel`) |
| stairs | a flight of steps rising along +y (into what it climbs), w wide |
| ladder | two rails and rungs off a wall |
| hangar_door | sliding leaves with ribs, a header and a bottom track, flush on the facade |
| truss | a Warren truss along x (chords and diagonals), flush on a facade |
| finial | a pagoda's finial: stacked rings on a pole, a point on top |
| beacon | an aviation light on a little base |
| seam | an emissive light seam up a hero's edge |
| halo | a hero's crown halo: a ring on posts, lit under its rim |
| garden | a planter box with soil and planting (sky gardens, terraces; AG4's `planter` is a deck's) |
| terrace_rail | a glass or rail balustrade along a terrace edge (AG4's `balustrade` is a deck's) |
| gondola | a ferris wheel's capsule: an octagonal cabin with a glazed band on its hanger |
| lattice | a tapering four-chord lattice tower (a wheel's legs, masts) |
| dormer | a gabled or shed dormer on a pitched roof, its window and cheeks |
| tarp | a tarp on four poles over a shanty roof |
| shack_roof | a lean-to sheet roof over a shanty storey |
| stack | a laboratory's fume stack on the roof |
| monitor | a roof monitor (a raised louvered clerestory along a shed's or warehouse's ridge) |
| pergola | posts and beams over a roof terrace |
| chimney | a chimney stack with its cap |
| cab | a control tower's cab: a floor, an outward-leaning glazed band with mullions, a roof with its overhang |
| radar | a radome on its pedestal |
| neon_strip | a neon band along a facade |
| girder | a transfer girder with stiffeners (a straddle span's underside) |
"""

from __future__ import annotations

import math

from citygen import dmath as M

from . import parts as PT
from . import roofparts as RP
from .parts import _cross, _sub, box, face, frame_y, ngon, prism
from .roofparts import annulus, bar, cone, cyl

OV = PT.OVERLAP


def tri(b, slot: str, p0, p1, p2, hint) -> None:
    """A triangle wound so its normal agrees with `hint` (the solid's outward side)."""
    n = _cross(_sub(p1, p0), _sub(p2, p0))
    L = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    if L == 0:
        return
    n = (n[0] / L, n[1] / L, n[2] / L)
    if n[0] * hint[0] + n[1] * hint[1] + n[2] * hint[2] < 0:
        p1, p2 = p2, p1
        n = (-n[0], -n[1], -n[2])
    face(b, slot, [p0, p1, p2], n)


def quad(b, slot: str, a, bb, c, d, hint) -> None:
    tri(b, slot, a, bb, c, hint)
    tri(b, slot, a, c, d, hint)


def loop_solid(b, top_out, top_in, bot_out, bot_in, slot_top: str, slot_bot: str,
               slot_side: str, center=(0, 0)) -> None:
    """A closed ring solid between two loops of the same length (outer and inner, each with
    a top and a bottom): top strip, bottom strip, outer and inner sides."""
    n = len(top_out)
    b.new_part()
    cx, cy = center
    for k in range(n):
        j = (k + 1) % n
        mo = ((top_out[k][0] + top_out[j][0]) / 2.0 - cx, (top_out[k][1] + top_out[j][1]) / 2.0
              - cy)
        L = math.hypot(*mo) or 1.0
        out = (mo[0] / L, mo[1] / L, 0.0)
        quad(b, slot_top, top_out[k], top_out[j], top_in[j], top_in[k], (out[0] * 0.3,
                                                                       out[1] * 0.3, 1.0))
        quad(b, slot_bot, bot_out[k], bot_in[k], bot_in[j], bot_out[j], (0.0, 0.0, -1.0))
        quad(b, slot_side, bot_out[k], bot_out[j], top_out[j], top_out[k], out)
        quad(b, slot_side, bot_in[k], top_in[k], top_in[j], bot_in[j], (-out[0], -out[1], 0.0))


def _rect8(hx: float, hy: float, z: float, curl: float = 0.0):
    """A rectangle's corners and edge midpoints from (-hx, -hy) counterclockwise, the
    corners lifted by `curl`."""
    pts = [(-hx, -hy, z + curl), (0, -hy, z), (hx, -hy, z + curl), (hx, 0, z),
           (hx, hy, z + curl), (0, hy, z), (-hx, hy, z + curl), (-hx, 0, z)]
    return [(int(round(x)), int(round(y)), int(round(zz))) for x, y, zz in pts]


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_eave(p: dict, b) -> None:
    """The roof skirt of a tier: its inner edge `rise` up on the upper tier's wall (w x d,
    60 mm inside it), its outer edge `drop` under z 0 and `out` past the lower tier's walls
    (W x D), the corners curled up by `curl`, `t` thick."""
    W, D, w, d = p["W"], p["D"], p["w"], p["d"]
    out, rise, drop, curl, t = p["out"], p["rise"], p["drop"], p["curl"], p["t"]
    ho, hd = W / 2.0 + out, D / 2.0 + out
    hi_x, hi_y = w / 2.0 - 60, d / 2.0 - 60
    to = _rect8(ho, hd, -drop, curl)
    ti = _rect8(hi_x, hi_y, rise)
    bo = _rect8(ho, hd, -drop - t, curl)
    bi = _rect8(hi_x, hi_y, rise - t)
    loop_solid(b, to, ti, bo, bi, p.get("slot", "eave_tile"), "eave_soffit", "eave_tile")


def gen_pillar(p: dict, b) -> None:
    r, h, st = p["r"], p["h"], p["style"]
    if st == "temple":
        box(b, "stone", -r - 120, r + 120, -r - 120, r + 120, 0, 400)
        prism(b, "lacquer", ngon(0, 0, r, 8, 0.5), [], 400, h - 500, "z")
        box(b, "lacquer", -r - 60, r + 60, -r - 60, r + 60, h - 500, h - 300)
        box(b, "eave_soffit", -r - 260, r + 260, -r - 120, r + 120, h - 300, h)
    elif st == "round":
        prism(b, "column", ngon(0, 0, r + 80, 12, 0.5), [], 0, 300, "z")
        prism(b, "column", ngon(0, 0, r, 12, 0.5), [], 300, h - 250, "z")
        prism(b, "column", ngon(0, 0, r + 100, 12, 0.5), [], h - 250, h, "z")
    else:
        box(b, "steel", -r, r, -r, r, 0, h)
        box(b, "steel", -r - 80, r + 80, -r - 80, r + 80, 0, 30)
        box(b, "steel", -r - 80, r + 80, -r - 80, r + 80, h - 30, h)


def gen_stairs(p: dict, b) -> None:
    """n steps of `rise` and `run` from y 0 (z 0) up into +y, w wide (x centered), as one
    solid on its stringer down to z 0."""
    w, n, rise, run = p["w"], p["n"], p["rise"], p["run"]
    prof = [(0, 0)]
    for k in range(n):
        prof += [(k * run, (k + 1) * rise), ((k + 1) * run, (k + 1) * rise)]
    prof.append((n * run, 0))
    prism(b, p.get("slot", "step"), prof, [], -w // 2, w // 2, "x")


def gen_ladder(p: dict, b) -> None:
    h, w = p["h"], p["w"]
    slot = p.get("slot", "escape")
    for x in (-w // 2, w // 2 - 40):
        box(b, slot, x, x + 40, -160, -120, 0, h)
        for z in range(600, h - 300, 1800):
            box(b, slot, x, x + 40, -120, 0, z, z + 40)
    z = 250
    while z < h - 100:
        box(b, slot, -w // 2 + 40, w // 2 - 40, -150, -130, z, z + 25)
        z += 300


def gen_hangar_door(p: dict, b) -> None:
    """Sliding leaves w wide and h tall in all (`leaves` of them, alternately 30 mm in
    front), ribs every 1.2 m, a header and a bottom track, all within 0.16 m of the wall."""
    w, h, n = p["w"], p["h"], p["leaves"]
    for k in range(n):
        x0 = -w // 2 + w * k // n
        x1 = -w // 2 + w * (k + 1) // n + (40 if k + 1 < n else 0)
        y0, y1 = (-100, -40) if k % 2 == 0 else (-130, -70)
        box(b, "hangar_door", x0, x1, y0, y1, 120, h - 300)
        z = 1200
        while z < h - 600:
            box(b, "steel", x0 + 60, x1 - 60, y0 - 25, y0, z, z + 80)
            z += 1200
    box(b, "steel", -w // 2 - 300, w // 2 + 300, -150, 0, h - 300, h)
    box(b, "steel", -w // 2 - 300, w // 2 + 300, -150, 0, 0, 120)


def gen_truss(p: dict, b) -> None:
    """A Warren truss from x 0 to L, h deep under z 0 (its top chord at z 0), `panels`
    panels, `w` out of the wall."""
    L, h, n, w = p["L"], p["h"], p["panels"], p["w"]
    slot = p.get("slot", "steel")
    y = -w // 2
    box(b, slot, 0, L, -w, 0, -160, 0)
    box(b, slot, 0, L, -w, 0, -h, -h + 160)
    for k in range(n):
        xa = L * k // n
        xb = L * (k + 1) // n
        xm = (xa + xb) // 2
        bar(b, slot, (xa, y, -h + 80), (xm, y, -80), 120, w - 20)
        bar(b, slot, (xm, y, -80), (xb, y, -h + 80), 120, w - 20)
        box(b, slot, xa - 60 if k else 0, xa + 60, -w, 0, -h + 160, -160)
    box(b, slot, L - 120, L, -w, 0, -h + 160, -160)


def gen_finial(p: dict, b) -> None:
    h, r = p["h"], p["r"]
    cyl(b, "lacquer", 0, 0, r, 0, h // 6, 12)
    z = h // 6
    k = 0
    while z < h * 3 // 4 and k < 9:
        annulus(b, "finial", 60, r * (8 - k) // 10 + 40, z, z + 80, 12)
        z += h // 14
        k += 1
    cyl(b, "finial", 0, 0, 50, h // 6, h * 9 // 10, 8)
    cone(b, "finial", 0, 0, 140, h * 9 // 10, h, 8)


def gen_beacon(p: dict, b) -> None:
    s = p["s"]
    box(b, "equip_steel", -s, s, -s, s, 0, s)
    box(b, "lamp_red", -s // 2, s // 2, -s // 2, s // 2, s, 2 * s)


def gen_seam(p: dict, b) -> None:
    w, h, d = p["w"], p["h"], p["d"]
    box(b, "hero_frame", -w // 2 - 40, w // 2 + 40, -d // 2, 0, 0, h)
    box(b, "hero_light", -w // 2, w // 2, -d, -d // 2, 40, h - 40)


def gen_halo(p: dict, b) -> None:
    """A ring r0..r1 at `post` over the roof on n posts, t thick, lit under its rim."""
    r0, r1, t, n, post = p["r0"], p["r1"], p["t"], p["n"], p["post"]
    annulus(b, "halo_frame", r0, r1, post, post + t, 48)
    annulus(b, "halo_light", r1 - 220, r1 - 60, post - 60, post, 48)
    for k in range(n):
        a = 2.0 * M.PI * k / n
        c, s = float(M.cos(a)), float(M.sin(a))
        rm = (r0 + r1) / 2.0
        bar(b, "halo_frame", (int(rm * 0.55 * c), int(rm * 0.55 * s), 0),
            (int(rm * c), int(rm * s), post + t // 2), 300)


def gen_garden(p: dict, b) -> None:
    w, d, h = p["w"], p["d"], p["h"]
    box(b, "planter", -w // 2, w // 2, -d // 2, d // 2, 0, h)
    box(b, "soil", -w // 2 + 80, w // 2 - 80, -d // 2 + 80, d // 2 - 80, h, h + 40)
    box(b, "green_roof", -w // 2 + 120, w // 2 - 120, -d // 2 + 120, d // 2 - 120, h + 40,
        h + 40 + p.get("g", 400))


def gen_terrace_rail(p: dict, b) -> None:
    """Along x from 0 to L at the terrace edge (y 0 the edge, the terrace +y), h tall."""
    L, h, st = p["L"], p["h"], p["style"]
    if st == "glass":
        box(b, "glazing", 0, L, 40, 60, 80, h - 50)
        box(b, "railing", 0, L, 20, 80, h - 50, h)
        box(b, "railing", 0, L, 20, 80, 0, 80)
    else:
        n = max(2, L // 1500 + 1)
        for j in range(n):
            x = (L - 50) * j // (n - 1)
            box(b, "railing", x, x + 50, 20, 70, 0, h - 40)
        for z0, z1 in ((h - 40, h), (h // 2 - 20, h // 2 + 20)):
            box(b, "railing", 0, L, 20, 70, z0, z1)


def gen_gondola(p: dict, b) -> None:
    """A capsule hanging under its pivot (z 0): a hanger, an octagonal cabin r wide and h
    tall, a glazed band round its middle; x along the wheel's axle."""
    r, h = p["r"], p["h"]
    top = -400
    box(b, "hero_frame", -80, 80, -80, 80, top, 0)
    z0, z1 = top - h, top
    zb0, zb1 = z0 + h * 30 // 100, z1 - h * 22 // 100
    prism(b, "gondola", ngon(0, 0, r, 8, 0.5), [], z0, zb0, "z")
    prism(b, "glazing", ngon(0, 0, r - 30, 8, 0.5), [], zb0, zb1, "z")
    prism(b, "gondola", ngon(0, 0, r, 8, 0.5), [], zb1, z1, "z")
    box(b, "hero_light", -60, 60, -60, 60, z0 - 60, z0)


def gen_lattice(p: dict, b) -> None:
    """A four-chord lattice from w0 wide at z 0 to w1 at h, `bays` bays of X bracing."""
    w0, w1, h, n = p["w0"], p["w1"], p["h"], p["bays"]
    slot = p.get("slot", "wheel_steel")

    def corner(sx, sy, z):
        w = w0 + (w1 - w0) * z / h
        return (int(round(sx * w / 2.0)), int(round(sy * w / 2.0)), int(z))
    cs = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    for sx, sy in cs:
        bar(b, slot, corner(sx, sy, 0), corner(sx, sy, h), p.get("chord", 300))
    for k in range(n):
        za, zb = h * k // n, h * (k + 1) // n
        for i in range(4):
            a, c = cs[i], cs[(i + 1) % 4]
            bar(b, slot, corner(*a, za), corner(*c, zb), 120)
            bar(b, slot, corner(*c, za), corner(*a, zb), 120)
            bar(b, slot, corner(*a, zb), corner(*c, zb), 140)


def gen_dormer(p: dict, b) -> None:
    """A dormer: its front wall at y 0 (w wide, h tall to the eaves), cheeks back to `d`
    into the roof, a gabled (or shed) roof over it, a window in its face."""
    w, h, d, st = p["w"], p["h"], p["d"], p["style"]
    hw = w // 2
    box(b, "dormer", -hw, hw, 0, d, 0, h)
    ww, wh = w - 400, h - 500
    if ww >= 400 and wh >= 500:
        frame_y(b, "frame", -ww // 2, ww // 2, 250, 250 + wh, 60, -30, 10)
        box(b, "glass", -ww // 2 + 60, ww // 2 - 60, -10, 0, 310, 250 + wh - 60)
    slot = p.get("slot", "tile")
    if st == "gable":
        rise = w * 45 // 100
        prism(b, slot, [(-hw - 120, h), (hw + 120, h), (0, h + rise)], [], -150, d, "y")
    else:
        prism(b, slot, [(-150, h + 250), (d, h - 150), (d, h), (-150, h + 400)], [],
              -hw - 120, hw + 120, "x")


def gen_tarp(p: dict, b) -> None:
    w, d, h, tilt = p["w"], p["d"], p["h"], p["tilt"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            hh = h - (tilt if sy > 0 else 0)
            box(b, "equip_steel", sx * (w // 2 - 60) - 30, sx * (w // 2 - 60) + 30,
                sy * (d // 2 - 60) - 30, sy * (d // 2 - 60) + 30, 0, hh)
    prism(b, "tarp", [(-d // 2, h), (d // 2, h - tilt), (d // 2, h - tilt + 40),
                      (-d // 2, h + 40)], [], -w // 2, w // 2, "x")


def gen_shack_roof(p: dict, b) -> None:
    """A lean-to sheet over a W x D storey (z 0 its top), `over` past its walls, rising
    `rise` from -y to +y."""
    W, D, rise, over = p["W"], p["D"], p["rise"], p["over"]
    y0, y1 = -D // 2 - over, D // 2 + over
    prism(b, "shanty_roof", [(y0, 0), (y1, rise), (y1, rise + 60), (y0, 60)], [],
          -W // 2 - over, W // 2 + over, "x")
    prism(b, "steel", [(-D // 2 + 60, 0), (D // 2 - 60, 0), (D // 2 - 60, rise * (D - 120)
                                                            // max(D + 2 * over, 1)),
                       (-D // 2 + 60, 10)], [], -60, 60, "x")


def gen_stack(p: dict, b) -> None:
    r, h = p["r"], p["h"]
    box(b, "equip_steel", -r - 150, r + 150, -r - 150, r + 150, 0, 300)
    cyl(b, "equip_steel", 0, 0, r, 300, h, 12)
    cyl(b, "equip_dark", 0, 0, r + 60, h * 2 // 3, h * 2 // 3 + 150, 12)
    cyl(b, "equip_dark", 0, 0, r + 40, h, h + 120, 12)


def gen_monitor(p: dict, b) -> None:
    L, w, h = p["L"], p["w"], p["h"]
    box(b, "roof_wall", -L // 2, L // 2, -w // 2, w // 2, 0, 200)
    box(b, "louver", -L // 2 + 60, L // 2 - 60, -w // 2 + 40, w // 2 - 40, 200, h - 120)
    box(b, "roof_metal", -L // 2 - 100, L // 2 + 100, -w // 2 - 150, w // 2 + 150, h - 120, h)


def gen_pergola(p: dict, b) -> None:
    w, d, h = p["w"], p["d"], p["h"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (w // 2 - 100), sy * (d // 2 - 100)
            box(b, "pergola", x - 70, x + 70, y - 70, y + 70, 0, h - 150)
    for sy in (-1, 1):
        y = sy * (d // 2 - 100)
        box(b, "pergola", -w // 2, w // 2, y - 60, y + 60, h - 250, h - 150)
    n = max(3, w // 500)
    for k in range(n + 1):
        x = -w // 2 + 40 + (w - 80) * k // n
        box(b, "pergola", x - 40, x + 40, -d // 2, d // 2, h - 150, h)


def gen_chimney(p: dict, b) -> None:
    w, d, h = p["w"], p["d"], p["h"]
    box(b, "chimney", -w // 2, w // 2, -d // 2, d // 2, 0, h - 200)
    box(b, "chimney", -w // 2 - 60, w // 2 + 60, -d // 2 - 60, d // 2 + 60, h - 200, h - 80)
    for x in ((-w // 4, w // 4) if w >= 900 else (0,)):
        cyl(b, "chimney", x, 0, 110, h - 80, h + 250, 8)


def gen_cab(p: dict, b) -> None:
    """A control tower cab W x D (centered, z 0 its floor): a 0.6 m floor band, the glazed
    band `h` tall leaning out by `lean` from its foot to its head (the foot inside the
    footprint), mullions, a roof slab with `over` of overhang."""
    W, D, h, lean, over = p["W"], p["D"], p["h"], p["lean"], p["over"]
    hx, hy = W // 2, D // 2
    box(b, "structure", -hx, hx, -hy, hy, 0, 600)
    z0, z1 = 600, 600 + h
    bot = [(-hx + lean, -hy + lean, z0), (hx - lean, -hy + lean, z0),
           (hx - lean, hy - lean, z0), (-hx + lean, hy - lean, z0)]
    top = [(-hx, -hy, z1), (hx, -hy, z1), (hx, hy, z1), (-hx, hy, z1)]
    k = 80
    bi = [(x - k * (1 if x > 0 else -1), y - k * (1 if y > 0 else -1), z) for x, y, z in bot]
    ti = [(x - k * (1 if x > 0 else -1), y - k * (1 if y > 0 else -1), z) for x, y, z in top]
    b.new_part()
    for i in range(4):
        j = (i + 1) % 4
        mo = ((top[i][0] + top[j][0]) / 2.0, (top[i][1] + top[j][1]) / 2.0)
        L = math.hypot(*mo) or 1.0
        o = (mo[0] / L, mo[1] / L, -0.2)
        quad(b, "glass", bot[i], bot[j], top[j], top[i], o)
        quad(b, "structure", bi[i], ti[i], ti[j], bi[j], (-o[0], -o[1], 0.0))
        quad(b, "structure", bot[i], bi[i], bi[j], bot[j], (0.0, 0.0, -1.0))
        quad(b, "structure", top[i], top[j], ti[j], ti[i], (0.0, 0.0, 1.0))
    n = max(2, W // 1500)
    for i in range(4):
        j = (i + 1) % 4
        for m in range(n + 1):
            f = m / n
            pb = tuple(int(round(bot[i][c] + (bot[j][c] - bot[i][c]) * f)) for c in range(3))
            pt = tuple(int(round(top[i][c] + (top[j][c] - top[i][c]) * f)) for c in range(3))
            bar(b, "mullion", pb, pt, 90)
    box(b, "canopy", -hx - over, hx + over, -hy - over, hy + over, z1, z1 + 450)
    box(b, "structure", -hx + 300, hx - 300, -hy + 300, hy - 300, z1 + 450, z1 + 1100)


def gen_radar(p: dict, b) -> None:
    r = p["r"]
    box(b, "equip_steel", -r // 2, r // 2, -r // 2, r // 2, 0, r // 2)
    cyl(b, "radome", 0, 0, r, r // 2, r * 3 // 2, 16)
    cone(b, "radome", 0, 0, r, r * 3 // 2, r * 5 // 2, 16)


def gen_neon_strip(p: dict, b) -> None:
    L, h, d = p["L"], p["h"], p["d"]
    box(b, "mount", 0, L, -d // 2, 0, 0, h)
    box(b, p["slot"], 30, L - 30, -d, -d // 2, h // 4, h * 3 // 4)


def gen_girder(p: dict, b) -> None:
    """A transfer girder from x 0 to L, h deep (z 0 its top), `w` out of the wall, a
    stiffener every 3 m and a lamp strip along its foot."""
    L, h, w = p["L"], p["h"], p["w"]
    box(b, "steel", 0, L, -w, 0, -h, 0)
    x = 1500
    while x < L - 1000:
        box(b, "steel", x - 60, x + 60, -w - 40, -w, -h + 60, -60)
        x += 3000
    box(b, "lamp_white", 200, L - 200, -w + 20, -20, -h - 40, -h)


def gen_needle(p: dict, b) -> None:
    """A hero's needle spire h tall from a base r wide: four tapering lengths, a ring at
    each joint, an aviation beacon on top."""
    h, r = p["h"], p["r"]
    z = 0
    rs = [r, r * 7 // 10, r * 45 // 100, r * 25 // 100]
    fr = (35, 30, 20, 15)
    for k, (rr, f) in enumerate(zip(rs, fr)):
        dz = (h - 600) * f // 100
        prism(b, "hero_frame", ngon(0, 0, max(rr, 80), 8, 0.5), [], z, z + dz, "z")
        if k:
            annulus(b, "hero_light", max(rr, 80) + 20, max(rr, 80) + 160, z, z + 200, 16)
        z += dz
    box(b, "lamp_red", -120, 120, -120, 120, z, z + 600)


GEN = {"eave": gen_eave, "needle": gen_needle, "pillar": gen_pillar, "stairs": gen_stairs, "ladder": gen_ladder,
       "hangar_door": gen_hangar_door, "truss": gen_truss, "finial": gen_finial,
       "beacon": gen_beacon, "seam": gen_seam, "halo": gen_halo, "garden": gen_garden,
       "terrace_rail": gen_terrace_rail, "gondola": gen_gondola, "lattice": gen_lattice,
       "dormer": gen_dormer, "tarp": gen_tarp, "shack_roof": gen_shack_roof,
       "stack": gen_stack, "monitor": gen_monitor, "pergola": gen_pergola,
       "chimney": gen_chimney, "cab": gen_cab, "radar": gen_radar,
       "neon_strip": gen_neon_strip, "girder": gen_girder}
# how far each family may reach (the envelope check; merged parts go by their slots,
# `envelope.SLOT_REACH`): "type" is what a type or hero generator builds inside its masses
# or within a deep allowance (eaves, cab roofs), "roof" on a roof, "wheel" inside the
# wheel's box (its rim, axle and legs are one open-air structure)
REACH = {"eave": "deep", "needle": "roof", "pillar": "flush", "stairs": "flush", "ladder": "flush",
         "hangar_door": "flush", "truss": "flush", "finial": "roof", "beacon": "roof",
         "seam": "flush", "halo": "roof", "garden": "roof", "terrace_rail": "deep",
         "gondola": "wheel", "lattice": "wheel", "dormer": "roof", "tarp": "roof",
         "shack_roof": "strip", "stack": "roof", "monitor": "roof", "pergola": "roof",
         "chimney": "roof", "cab": "deep", "radar": "roof", "neon_strip": "flush",
         "girder": "flush"}
SUB = {"pillar": "style", "dormer": "style", "terrace_rail": "style"}
FIXED = {"eave": "tier", "needle": "spire", "stairs": "flight", "ladder": "rungs", "hangar_door": "sliding",
         "truss": "warren", "finial": "pagoda", "beacon": "aviation", "seam": "light",
         "halo": "crown", "garden": "box", "gondola": "capsule", "lattice": "tower",
         "tarp": "poles", "shack_roof": "lean_to", "stack": "fume", "monitor": "ridge",
         "pergola": "terrace", "chimney": "stack", "cab": "glazed", "radar": "dome",
         "neon_strip": "band", "girder": "transfer"}
# slots of these parts, merged into a shell, that stand on a roof (the envelope's roof
# rule: on a roof, or inside the masses)
ROOF_SLOTS = ("tarp", "pergola", "chimney", "radome", "halo_frame", "halo_light", "finial",
              "lacquer")


def register() -> None:
    for k, g in GEN.items():
        PT.GEN[k] = g
        PT.REACH[k] = REACH[k]
    PT.TYPE_KEY.update(SUB)
    PT.TYPE_SUB.update(FIXED)
    RP.ROOF_SLOTS = tuple(dict.fromkeys(RP.ROOF_SLOTS + ROOF_SLOTS))


register()
