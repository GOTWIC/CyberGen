"""Far proxies (scope section 8): one per building, its masses as prisms with their roofs
(no bottoms, no openings; on a slope down its plinth), 50 to 500 triangles, UV0 in meters
(u around the mass, v up) so a facade material can draw windows by UV; for Nanite
fallback, HLOD inputs and whole-city renders. Rings with many vertices are thinned (the vertex whose removal changes the area
least goes first, while the ring stays simple) until the proxy fits its budget.
"""

from __future__ import annotations

import math

from ..triangulate import TriangulationError, area2, orient, triangulate
from . import rings as RG
from .meshbuf import Buf
from .shell import plinth_mm

MAX_TRIS = 500


def _tris_of(rings_by_mass) -> int:
    t = 0
    for rings in rings_by_mass:
        nv = sum(len(r) for r in rings)
        t += 2 * nv + (nv - 2 + 2 * (len(rings) - 1))
    return t


def _thin(ring) -> list | None:
    """The ring without its least important vertex, or None if every removal folds it."""
    n = len(ring)
    if n <= 4:
        return None
    order = sorted(range(n), key=lambda i: (abs(orient(ring[i - 1], ring[i],
                                                         ring[(i + 1) % n])), i))
    for i in order[:8]:
        cand = ring[:i] + ring[i + 1:]
        if RG.is_simple(cand) and (area2(cand) > 0) == (area2(ring) > 0):
            return cand
    return None


def build(brief: dict, slot_wall: str = "proxy", slot_roof: str = "proxy_roof") -> dict:
    masses = []
    depth = plinth_mm(brief)
    for m in brief["masses"]:
        z0, z1 = int(round(m["z"][0] * 1000)), int(round(m["z"][1] * 1000))
        if z1 - z0 < 50:
            continue
        if z0 <= 50 and depth:
            z0 = -depth                        # down its plinth on a slope
        rings = [RG.tidy(RG.mm_ring(m["footprint"]["exterior"]))[0]] + \
            [RG.tidy(RG.mm_ring(h))[0] for h in m["footprint"]["holes"]]
        rings = [r for r in rings if len(r) >= 3]
        if not rings or len(rings[0]) < 3:
            continue
        masses.append([z0, z1, rings])
    # thin the largest rings first until the budget holds
    while _tris_of([m[2] for m in masses]) > MAX_TRIS:
        best = None
        for mi, m in enumerate(masses):
            for ri, r in enumerate(m[2]):
                if best is None or (len(r), -mi, -ri) > best[0]:
                    best = ((len(r), -mi, -ri), mi, ri)
        if best is None:
            break
        _, mi, ri = best
        t = _thin(masses[mi][2][ri])
        if t is None:
            if ri > 0:
                masses[mi][2].pop(ri)          # a court too small to matter far away
                continue
            # cannot thin further: drop the smallest mass
            if len(masses) <= 1:
                break
            small = min(range(len(masses)), key=lambda k: (abs(area2(masses[k][2][0])), k))
            masses.pop(small)
            continue
        masses[mi][2][ri] = t
    buf = Buf()
    for z0, z1, rings in masses:
        buf.new_part()
        u = 0.0
        for ring in rings:
            n = len(ring)
            for i in range(n):
                p, q = ring[i], ring[(i + 1) % n]
                dx, dy = q[0] - p[0], q[1] - p[1]
                L = math.sqrt(dx * dx + dy * dy)
                if L < 1:
                    continue
                ux, uy = dx / L, dy / L
                pl = buf.plane((uy, -ux, 0.0), (p[0], p[1], 0), (ux, uy, 0.0), (0.0, 0.0, 1.0),
                               u, 0.0)
                u += L / 1000.0
                buf.quad(slot_wall, pl, (p[0], p[1], z0), (q[0], q[1], z0), (q[0], q[1], z1),
                         (p[0], p[1], z1))
        try:
            tris = triangulate(rings[0], rings[1:])
        except TriangulationError:
            tris = []
        pts = [p for r in rings for p in r]
        top = buf.plane((0.0, 0.0, 1.0), (0, 0, z1), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        buf.add(slot_roof, top, [(p[0], p[1], z1) for p in pts], [i for t in tris for i in t])
    return {"buf": buf, "arrays": buf.arrays(), "triangles": buf.triangles}
