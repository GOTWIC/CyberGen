"""Quays and canal walls.

- **Quays**: the quay's paving at the ground, a stone coping and the quay wall down past the
  water line on the water side (found from the waterway's polygon), cast-iron bollards
  every 12 m, and stairs down to the water every 60 m along the wall.
- **Canal walls**: every edge of a canal, basin, inlet or marina, a stone wall from the
  ground down under the water, with a coping on the land side; creeks keep natural banks
  (no walls).

Water stands at the blockout's level (0.9 m under the ground) or at M13's water level.
"""

from __future__ import annotations

from .. import canon as C
from . import materials as MT
from .ctx import Ctx, _inside, bbox_center, dump
from .kit import Mesh, ccw
from .path import Path, dist, unit
from .pieces import Out, Piece, maker
from .structures import WATER_DEFAULT

BOLLARD_STEP = 12.0
STAIR_STEP = 60.0


def gather_quay(cx: Ctx, q) -> Piece:
    w = cx.waterway.get(q.waterway_id)
    side = 0
    try:
        P = Path(q.line)
        x, y, nx, ny, _ = P.frame(P.L / 2.0)
        if w is not None:
            d = q.width_m / 2.0 + 1.0
            if _inside(w.polygon.exterior, x + nx * d, y + ny * d):
                side = 1
            elif _inside(w.polygon.exterior, x - nx * d, y - ny * d):
                side = -1
    except ValueError:
        pass
    did = w.district_id if w is not None else None
    inputs = {"quay": dump(q), "side": side, "ground": cx.ground.samples(q.line),
              "water_z": C.m(cx.ground.water_level(q.waterway_id, WATER_DEFAULT)),
              "style": cx.style(did), "origin": list(bbox_center(q.line))}
    return Piece(q.id, "street.quay", "quay", cx.tile_for(q.id, q.line),
                 cx.keys.get(q.id, []), inputs)


@maker("quay", 1)
def make_quay(inp: dict) -> Out:
    q = inp["quay"]
    try:
        P = Path(q["line"])
    except ValueError:
        return Out(empty="degenerate line")
    gnd = inp.get("ground")
    gp = None
    if gnd and len(gnd) == len(P.p):
        from .path import Profile
        gp = Profile(list(zip(P.cum, gnd)))

    def g(s):
        return gp(s) if gp is not None else 0.0
    w = q["width_m"]
    h = w / 2.0
    ws = inp["side"] or 1
    wz = inp["water_z"]
    mesh = Mesh(inp["origin"])
    pave = MT.paving(inp["style"]["archetype"])
    st = P.stations(0.0, P.L, 6.0)
    rows, uvs, cop, cuv, wall, wuv, exp = [], [], [], [], [], [], []
    te = ws * h
    ti = ws * (h - 0.5)
    for s, vi in st:
        x, y, nx, ny, k = P.frame(s, vi)
        z = g(s) + 0.02
        at = lambda t: (x + nx * k * t, y + ny * k * t)
        a_, b_ = (-h, ti) if ws > 0 else (ti, h)
        rows.append([(*at(a_), z), (*at(b_), z)])
        uvs.append([(s, a_), (s, b_)])
        c0, c1 = (ti, te) if ws > 0 else (te, ti)
        cop.append([(*at(c0), z + 0.06), (*at(c1), z + 0.06)])
        cuv.append([(s, c0), (s, c1)])
        e = at(te)
        col = [(*e, z + 0.06), (*e, wz - 1.5)] if ws > 0 else [(*e, wz - 1.5), (*e, z + 0.06)]
        wall.append(col)
        wuv.append([(s, col[0][2]), (s, col[1][2])])
        exp.append((ws * nx, ws * ny, 0.0))
    up = (0.0, 0.0, 1.0)
    mesh.grid(pave, rows, _along(rows, uvs), expect=up)
    mesh.grid("stone.coping", cop, _along(cop, cuv), expect=up)
    mesh.grid("stone.quay", wall, _along(wall, wuv), expect=exp)
    s = BOLLARD_STEP / 2.0
    while s < P.L:
        x, y, nx, ny, _ = P.frame(s)
        t = ws * (h - 0.8)
        z = g(s) + 0.08
        mesh.cylinder("steel.painted", x + nx * t, y + ny * t, 0.17, z, z + 0.5, n=10)
        mesh.cylinder("steel.painted", x + nx * t, y + ny * t, 0.23, z + 0.5, z + 0.58, n=10)
        s += BOLLARD_STEP
    if P.L > 30.0:
        s = STAIR_STEP / 2.0
        while s + 4.0 < P.L:
            _stair(mesh, P, s, ws, h, g(s) + 0.02, wz)
            s += STAIR_STEP
    return Out(mesh=mesh)


def _along(rows, uvs):
    """UV0 with u the distance along each column's own line (in plan) from the first row:
    a quay is 15 m wide, so round a sharp corner of its line (a basin's, or a jog of a few
    centimeters at one) the mitered outer edge runs meters where the line runs none, and u
    from the line's distance would stretch the texture there many times over."""
    out = [[(uvs[0][j][0], uvs[0][j][1]) for j in range(len(rows[0]))]]
    for i in range(1, len(rows)):
        out.append([(out[i - 1][j][0] + dist(rows[i - 1][j][:2], rows[i][j][:2]),
                     uvs[i][j][1]) for j in range(len(rows[i]))])
    return out


def _stair(mesh: Mesh, P: Path, s0: float, ws: int, h: float, ztop: float, wz: float):
    """A flight down the quay wall into the water, along the wall on the water side."""
    drop = ztop - (wz + 0.15)
    if drop < 0.3:
        return
    n = max(2, int(drop / 0.17 + 0.999))
    run = 0.3
    t0, t1 = ws * h, ws * (h + 1.4)
    for i in range(n):
        a, b = s0 + run * i, s0 + run * (i + 1)
        if b > P.L:
            break
        zt = ztop - drop * (i + 1) / n
        lo, hi = (t0, t1) if ws > 0 else (t1, t0)
        ring = [(a, lo), (b, lo), (b, hi), (a, hi)]
        mesh.poly_map("stone.quay", ring, (), lambda u, v, zt=zt: (
            *_xy(P, u, v), zt))
        p, q = _xy(P, a, lo), _xy(P, a, hi)
        # the riser up to the step before, facing down the flight (+s)
        mesh.wall("stone.quay", p, q, zt, zt + drop / n, zt, zt + drop / n)
    # the stair's outer side wall
    a, b = s0, min(s0 + run * n, P.L)
    p0, p1 = _xy(P, a, t1), _xy(P, b, t1)
    if ws > 0:
        mesh.wall("stone.quay", p1, p0, wz - 1.0, ztop - drop / n * (n - 1), wz - 1.0, ztop)
    else:
        mesh.wall("stone.quay", p0, p1, wz - 1.0, ztop, wz - 1.0, ztop - drop / n * (n - 1))


def _xy(P: Path, s: float, t: float):
    x, y, nx, ny, _ = P.frame(s)
    return x + nx * t, y + ny * t


def gather_canal(cx: Ctx, w) -> Piece:
    ext = w.polygon.exterior
    pts = list(ext) + [p for h in w.polygon.holes for p in h]
    inputs = {"waterway": dump(w), "ground": cx.ground.samples(pts),
              "water_z": C.m(cx.ground.water_level(w.id, WATER_DEFAULT)),
              "origin": list(bbox_center(ext))}
    return Piece(w.id, f"street.canal_wall.{w.kind}", "canal", cx.tile_for(w.id, ext),
                 cx.keys.get(w.id, []), inputs)


@maker("canal", 1)
def make_canal(inp: dict) -> Out:
    w = inp["waterway"]
    if w["kind"] == "creek":
        return Out(empty="natural banks")
    mesh = Mesh(inp["origin"])
    wz = inp["water_z"]
    poly = w["polygon"]
    rings = [ccw(poly["exterior"])] + [ccw(h)[::-1] for h in poly.get("holes", [])]
    gnd = inp.get("ground")
    gi = {}
    if gnd:
        raw = list(poly["exterior"]) + [p for h in poly.get("holes", []) for p in h]
        for p, z in zip(raw, gnd):
            gi[(p[0], p[1])] = z
    for r in rings:
        n = len(r)
        u = 0.0
        for i in range(n):
            a, b = r[i], r[(i + 1) % n]
            L = dist(a, b)
            if L < 0.01:
                continue
            za, zb = gi.get(a, 0.0) + 0.03, gi.get(b, 0.0) + 0.03
            # facing the water: left of a -> b
            mesh.wall("stone.quay", b, a, wz - 2.0, zb, wz - 2.0, za, u)
            ux, uy = unit(b[0] - a[0], b[1] - a[1])
            ox, oy = uy * 0.45, -ux * 0.45           # to the land side
            mesh.quad("stone.coping", (a[0], a[1], za + 0.02), (a[0] + ox, a[1] + oy, za + 0.02),
                      (b[0] + ox, b[1] + oy, zb + 0.02), (b[0], b[1], zb + 0.02))
            u += L
    return Out(mesh=mesh)
