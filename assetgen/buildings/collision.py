"""Simple collision from the masses (scope section 8): every mass's footprint cut into convex
pieces (`rings.convex_pieces`), each a prism from the mass's base (on a slope, the bottom of
its plinth) to its top; a piece that is a rectangle becomes a box (center, half extents,
yaw), any other a convex prism (its ring and z range), in the building frame, meters. Spires, masts and thin decks under 0.5 m are
left out (nothing walks into them at street level and their boxes would only snag).

AG3: a mass on the ground (or on an M14 deck's top) starts at the street front's top
(`band_m`): the front under it
(doorways, steps, recesses, plinths, arcade columns) is its own mesh and collides as drawn
(complex collision in Unreal); a mass the front takes whole has none here.

AG5: a skybridge's landing door is left open (AG4's open item: the hulls closed it). The mass
it opens on is cut into storeys at each door's floor and head; in the door's storey its
footprint has a notch the door's width and `VESTIBULE_MM` deep at the door, so a walk across
the bridge steps through the door onto the solid below it.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from .. import canon as C
from ..triangulate import area2, orient
from . import rings as RG
from .shell import ground_mm, plinth_mm

SKIP_ROLES = ("spire", "mast")
VESTIBULE_MM = 2500          # AG5: how far a landing door's notch reaches into the hull


def _box(piece):
    """(center, half extents, yaw) if the piece is a rectangle, else None."""
    if len(piece) != 4:
        return None
    for i in range(4):
        a, b, c = piece[i - 1], piece[i], piece[(i + 1) % 4]
        if (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1]) != 0:
            return None
    p0, p1, p2 = piece[0], piece[1], piece[2]
    ex = math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2)
    ey = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
    cx = (p0[0] + p2[0]) / 2.0
    cy = (p0[1] + p2[1]) / 2.0
    yaw = float(M.degrees(M.atan2(p1[1] - p0[1], p1[0] - p0[0])))
    return (cx, cy), (ex / 2.0, ey / 2.0), yaw


def _notched(brief: dict, ext: list, doors: list) -> list | None:
    """The exterior ring with a notch at each door (on a ring edge that holds it), or None
    when a notch would not stay inside the ring."""
    from shapely.geometry import Polygon
    out = list(ext)
    for d in doors:
        e = brief["edges"][d["edge"]]
        ax, ay = e["a"][0] * 1000.0, e["a"][1] * 1000.0
        bx, by = e["b"][0] * 1000.0, e["b"][1] * 1000.0
        L = math.hypot(bx - ax, by - ay)
        if L <= 0:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L
        p0 = (int(round(ax + ux * d["s0"])), int(round(ay + uy * d["s0"])))
        p1 = (int(round(ax + ux * d["s1"])), int(round(ay + uy * d["s1"])))
        n = len(out)
        for i in range(n):
            p, q = out[i], out[(i + 1) % n]
            if _on(p, q, p0) and _on(p, q, p1) and \
                    (q[0] - p[0]) * ux + (q[1] - p[1]) * uy > 0:
                # (inward: to the left of the edge, the ring counterclockwise)
                ix, iy = -uy * VESTIBULE_MM, ux * VESTIBULE_MM
                i0 = (int(round(p0[0] + ix)), int(round(p0[1] + iy)))
                i1 = (int(round(p1[0] + ix)), int(round(p1[1] + iy)))
                if RG.inside(i0, ext) != 1 or RG.inside(i1, ext) != 1:
                    return None
                out = out[:i + 1] + [p0, i0, i1, p1] + out[i + 1:]
                break
    if len(out) == len(ext) or not Polygon(out).is_valid:
        return None              # (a notch that would cross the ring: the hull stays whole)
    return out


def _on(p, q, r) -> bool:
    """r on the segment p q, within 2 mm, strictly between its ends."""
    L2 = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
    if L2 <= 0:
        return False
    t = ((r[0] - p[0]) * (q[0] - p[0]) + (r[1] - p[1]) * (q[1] - p[1])) / L2
    if not 0.0 < t < 1.0:
        return False
    cr = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return cr * cr <= 4.0 * L2


def _bands(z0: float, z1: float, doors: list) -> list[tuple[float, float, list]]:
    """A mass's z range cut at its doors' floors and heads: (z0, z1, the doors open there)."""
    cuts = {z0, z1}
    for d in doors:
        lo, hi = d["z"] / 1000.0, d["hi"] / 1000.0
        if z0 < lo < hi <= z1 + 1e-6:
            cuts.update((lo, min(hi, z1)))
    zs = sorted(cuts)
    out = []
    for a, b in zip(zs, zs[1:]):
        if b - a < 1e-3:
            continue
        out.append((a, b, [d for d in doors if d["z"] / 1000.0 <= a + 1e-6 and
                           d["hi"] / 1000.0 >= b - 1e-6]))
    return out


def build(brief: dict, band_m: float | None = None, doors: list | None = None) -> dict:
    boxes, convex = [], []
    depth = plinth_mm(brief) / 1000.0
    ground = ground_mm(brief) / 1000.0
    by_mass: dict[int, list] = {}
    for d in doors or ():
        by_mass.setdefault(brief["edges"][d["edge"]]["mass"], []).append(d)
    for k, m in enumerate(brief["masses"]):
        z0, z1 = m["z"]
        if z1 - z0 < 0.5 or m["role"] in SKIP_ROLES:
            continue
        if z0 <= ground + 0.05 and band_m is not None and m["shape"] == "prism":
            if z1 <= band_m + 0.05:
                continue                       # (the street front takes it whole)
            z0 = band_m
        elif z0 <= 0.05 and depth:
            z0 = -depth                        # down its plinth on a slope
        ext = RG.tidy(RG.mm_ring(m["footprint"]["exterior"]))[0]
        holes = [RG.tidy(RG.mm_ring(h))[0] for h in m["footprint"]["holes"]]
        if len(ext) < 3:
            continue
        holes = [h for h in holes if len(h) >= 3]
        if area2(ext) < 0:
            ext = ext[::-1]
        for za, zb, open_ in _bands(z0, z1, by_mass.get(k, [])):
            ring = (_notched(brief, ext, open_) if open_ else None) or ext
            _pieces(ring, holes, za, zb, boxes, convex)
    return {"boxes": boxes, "convex": convex}


def _pieces(ext, holes, z0, z1, boxes, convex) -> None:
    for piece in RG.convex_pieces(ext, holes):
        piece = [p for i, p in enumerate(piece)
                 if orient(piece[i - 1], p, piece[(i + 1) % len(piece)]) != 0]
        if len(piece) < 3:
            continue
        bx = _box(piece)
        if bx is not None:
            (cx, cy), (hx, hy), yaw = bx
            boxes.append({"center": [C.m(cx / 1000.0), C.m(cy / 1000.0),
                                     C.m((z0 + z1) / 2.0)],
                          "extent": [C.m(hx / 1000.0), C.m(hy / 1000.0),
                                     C.m((z1 - z0) / 2.0)],
                          "yaw_deg": C.deg(yaw)})
        else:
            convex.append({"z": [C.m(z0), C.m(z1)],
                           "ring": [[C.m(p[0] / 1000.0), C.m(p[1] / 1000.0)]
                                    for p in piece]})
