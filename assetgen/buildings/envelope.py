"""The envelope check (scope section 9) on one building: every vertex of its shell and every
corner of its instanced parts inside a mass that spans its height, or an allowed overhang:

- AG1's strips (cornices, slab bands, eaves, ribs): at most 0.6 m out from a face (its
  miter at a corner at most `OVERHANG_MM` from the footprint) and at least 3 m up, over the
  sidewalk and never down to it; a parapet at most `PARAPET_MM` over its mass's top;
- AG2's parts by how far they reach (`parts.REACH`; merged ones by their slot): "flush"
  (frames, sills, caps, shutters, grilles, members, columns) up to `FLUSH_MM` out at any
  height, "strip" (fins, sunshades, louvers, pods, screens, AC units, dishes) as a strip,
  "deep" (balconies, podium canopies) up to `DEEP_MM` out at least 3 m up (the facade's
  room for them, over a sidewalk, a lot or a park and never over a lane, is the
  generator's rule: `shell.Facade.room`);
- AG3's street fronts: shopfronts, doors, mounts, pipes and painted surfaces "flush" (what
  goes deeper stays inside its opening's recess), entrance canopies "deep", a club's queue
  rail "street" (on a street or avenue sidewalk, at most `STREET_MM` out and `STREET_Z`
  high);
- roof equipment over a mass's roof; a crown mast or spire over the highest roof, at most
  `mast_cap` tall;
- on M13's slopes, a mass on the base reaches down by its plinth (`shell.plinth_mm`).

Masses that M3 put past their lot (straddle buildings) are the envelope as they are.
Distances in IEEE doubles, element-wise in a fixed order (scope section 10).
"""

from __future__ import annotations

import numpy as np

from ..planar import dist_polyline, inside_poly
from . import systems as SY
from .shell import plinth_mm

OVERHANG_MM = 910            # 0.6 m cornices, mitered up to 1.5 times at corners
PARAPET_MM = 1210
STRIP_MIN_MM = 2999
FLUSH_MM = 160
DEEP_MM = 1810
STREET_MM = 810
STREET_Z = 1210
TOL_MM = 2.0
# merged parts keep their slots: how far each slot may reach (the rest: AG1's rule)
SLOT_REACH = {"frame": "flush", "sill": "flush", "mullion": "flush",
              "spandrel_panel": "flush", "shutter": "flush", "grille": "flush",
              "member": "flush", "timber": "flush", "patch_ply": "flush", "column": "flush",
              "balcony": "deep", "railing": "deep", "glazing": "deep", "canopy": "deep",
              "fin": "strip", "perforated": "strip", "pod": "strip", "ac": "strip",
              "dish": "strip", "tile": "strip", "louver": "strip",
              "stanchion": "street", "rope": "street"}
for _s in SY.SLOTS:
    if _s not in SLOT_REACH and (_s.startswith(("paint_", "neon_", "screen_", "poster_",
                                                "mural_", "graffiti_", "riser_", "lit_",
                                                "door_")) or _s in (
            "step", "steel", "rubber", "seal", "rollup", "mount", "trellis", "pipe",
            "cabinet", "frosted", "club", "storefront_dark", "fascia")):
        SLOT_REACH[_s] = "flush"


def mast_cap(height_mm: float) -> float:
    """How tall a crown mast or spire may stand over the highest roof."""
    return max(12000.0, 0.2 * height_mm) + 1500.0


def check(brief: dict, arrs: dict, parts: list | None = None) -> dict:
    """`parts`: (points (n, 3) mm in the building frame, reach) of instanced parts."""
    masses = []
    depth = float(plinth_mm(brief))
    for m in brief["masses"]:
        ext = [(p[0] * 1000.0, p[1] * 1000.0) for p in m["footprint"]["exterior"]]
        holes = [[(p[0] * 1000.0, p[1] * 1000.0) for p in h] for h in m["footprint"]["holes"]]
        z0 = m["z"][0] * 1000.0
        masses.append((z0 - depth if z0 <= 50.0 else z0, m["z"][1] * 1000.0, ext, holes))
    top = max(z1 for _, z1, _, _ in masses) if masses else 0.0
    cap = mast_cap(float(brief["building"]["height_m"]) * 1000.0)
    out = {"vertices": 0, "outside": 0, "too_high": 0, "low_overhang": 0,
           "equipment_off_roof": 0, "parts": 0}
    groups = []
    for name, a in arrs.items():
        pos = np.unique(a["pos"], axis=0).astype(np.float64)
        groups.append((pos, "roof" if name in ("equipment", "mast") else
                       SLOT_REACH.get(name, "shell"), name))
    for pos, reach in parts or []:
        groups.append((np.asarray(pos, dtype=np.float64), reach, "part"))
        out["parts"] += len(pos)
    for pos, reach, name in groups:
        x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
        out["vertices"] += len(pos)
        if reach == "roof":
            ok = np.zeros(len(pos), dtype=bool)
            for z0, z1, ext, holes in masses:
                d = dist_polyline(x, y, ext + ext[:1])
                on = (inside_poly(x, y, ext, []) | (d <= 1000.0)) & (z >= z1 - TOL_MM)
                if name == "mast":
                    on &= z <= z1 + cap
                ok |= on
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
        high = z >= STRIP_MIN_MM
        allowed = (near <= OVERHANG_MM) & high
        if reach in ("flush", "strip", "deep"):
            allowed |= near <= FLUSH_MM
        if reach == "deep":
            allowed |= (near <= DEEP_MM) & high
        if reach == "street":
            allowed |= (near <= STREET_MM) & (z <= STREET_Z)
        bad = over & ~allowed
        out["outside"] += int(bad.sum())
        out["low_overhang"] += int((bad & (near <= DEEP_MM) & ~high).sum())
        out["too_high"] += int((z > top + PARAPET_MM).sum())
    out["ok"] = out["outside"] == 0 and out["too_high"] == 0 and \
        out["equipment_off_roof"] == 0
    return out


def part_points(inst: list[dict]) -> list:
    """The corners of every instanced part's box at each of its placements, with its reach
    (`parts.REACH`), for `check`."""
    from . import parts as PT
    out = []
    for x in inst:
        _, arrs = PT.mesh(x["family"], x["params"])
        lo, hi = PT.bounds(arrs)
        cx = np.array([lo[0], hi[0]] * 4, dtype=np.float64)
        cy = np.array([lo[1], lo[1], hi[1], hi[1]] * 2, dtype=np.float64)
        cz = np.array([lo[2]] * 4 + [hi[2]] * 4, dtype=np.float64)
        at = np.array([a[:3] for a in x["at"]], dtype=np.float64)
        rot = np.array([a[3:] for a in x["at"]], dtype=np.float64)
        ux, uy = rot[:, 0:1], rot[:, 1:2]
        px = (cx[None, :] * ux - cy[None, :] * uy) + at[:, 0:1]
        py = (cx[None, :] * uy + cy[None, :] * ux) + at[:, 1:2]
        pz = cz[None, :] + at[:, 2:3]
        pts = np.stack([px.reshape(-1), py.reshape(-1), pz.reshape(-1)], axis=1)
        out.append((pts, PT.REACH[x["family"]]))
    return out
