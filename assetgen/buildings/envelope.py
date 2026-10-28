"""The envelope check (scope section 9) on one shell: every vertex inside a mass that spans
its height, or an allowed overhang (a cornice or slab band at most 0.6 m out from a face, its
miter at a corner at most `OVERHANG_MM` from the footprint, and at least 3 m up, over the
sidewalk and never down to it; a parapet at most `PARAPET_MM` over its mass's top); roof equipment over a mass's roof. Masses that M3 put
past their lot (straddle buildings) are the envelope as they are. Distances in IEEE doubles,
element-wise in a fixed order (scope section 10).
"""

from __future__ import annotations

import numpy as np

from ..planar import dist_polyline, inside_poly

OVERHANG_MM = 910            # 0.6 m cornices, mitered up to 1.5 times at corners
PARAPET_MM = 1210
STRIP_MIN_MM = 2999
TOL_MM = 2.0


def check(brief: dict, arrs: dict) -> dict:
    masses = []
    for m in brief["masses"]:
        ext = [(p[0] * 1000.0, p[1] * 1000.0) for p in m["footprint"]["exterior"]]
        holes = [[(p[0] * 1000.0, p[1] * 1000.0) for p in h] for h in m["footprint"]["holes"]]
        masses.append((m["z"][0] * 1000.0, m["z"][1] * 1000.0, ext, holes))
    top = max(z1 for _, z1, _, _ in masses) if masses else 0.0
    out = {"vertices": 0, "outside": 0, "too_high": 0, "low_overhang": 0,
           "equipment_off_roof": 0}
    for name, a in arrs.items():
        pos = np.unique(a["pos"], axis=0).astype(np.float64)
        x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
        out["vertices"] += len(pos)
        if name == "equipment":
            ok = np.zeros(len(pos), dtype=bool)
            for z0, z1, ext, holes in masses:
                d = dist_polyline(x, y, ext + ext[:1])
                ok |= (inside_poly(x, y, ext, []) | (d <= 1000.0)) & (z >= z1 - TOL_MM)
            out["equipment_off_roof"] += int((~ok).sum())
            continue
        inside = np.zeros(len(pos), dtype=bool)
        near = np.full(len(pos), np.inf)
        for z0, z1, ext, holes in masses:
            span = (z >= z0 - TOL_MM) & (z <= z1 + PARAPET_MM)
            if not span.any():
                continue
            ins = inside_poly(x, y, ext, holes)
            d = dist_polyline(x, y, ext + ext[:1])
            for h in holes:
                d = np.minimum(d, dist_polyline(x, y, h + h[:1]))
            on = d <= TOL_MM
            inside |= span & (ins | on)
            near = np.where(span, np.minimum(near, d), near)
        over = ~inside
        bad = over & ~((near <= OVERHANG_MM) & (z >= STRIP_MIN_MM))
        out["outside"] += int(bad.sum())
        out["low_overhang"] += int((over & (near <= OVERHANG_MM) & (z < STRIP_MIN_MM)).sum())
        out["too_high"] += int((z > top + PARAPET_MM).sum())
    out["ok"] = out["outside"] == 0 and out["too_high"] == 0 and \
        out["equipment_off_roof"] == 0
    return out
