"""Simple collision from the masses (scope section 8): every mass's footprint cut into convex
pieces (`rings.convex_pieces`), each a prism from the mass's base (on a slope, the bottom of
its plinth) to its top; a piece that is a rectangle becomes a box (center, half extents,
yaw), any other a convex prism (its ring and z range), in the building frame, meters. Spires, masts and thin decks under 0.5 m are
left out (nothing walks into them at street level and their boxes would only snag).

AG3: a mass on the ground (or on an M14 deck's top) starts at the street front's top
(`band_m`): the front under it
(doorways, steps, recesses, plinths, arcade columns) is its own mesh and collides as drawn
(complex collision in Unreal); a mass the front takes whole has none here.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from .. import canon as C
from ..triangulate import orient
from . import rings as RG
from .shell import ground_mm, plinth_mm

SKIP_ROLES = ("spire", "mast")


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


def build(brief: dict, band_m: float | None = None) -> dict:
    boxes, convex = [], []
    depth = plinth_mm(brief) / 1000.0
    ground = ground_mm(brief) / 1000.0
    for m in brief["masses"]:
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
        for piece in RG.convex_pieces(ext, [h for h in holes if len(h) >= 3]):
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
    return {"boxes": boxes, "convex": convex}
