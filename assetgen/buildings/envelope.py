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
  `mast_cap` tall; AG4's equipment (instanced, or merged penthouses and billboard frames in
  their own slots, `roofparts.ROOF_SLOTS`) on a roof or inside the masses (the frames under
  an item on a pitched roof stand in its attic);
- AG4's roof forms in the top floor (their eaves as strips), finishes, copings and green
  roofs on the roof under the parapet's allowance;
- on M13's slopes, a mass on the base reaches down by its plinth (`shell.plinth_mm`);
- AG4's court floors, planters and gardens in a court: inside a mass's outline (its court
  is the building's), under its top.

Masses that M3 put past their lot (straddle buildings) are the envelope as they are.
Distances in IEEE doubles, element-wise in a fixed order (scope section 10).
"""

from __future__ import annotations

import numpy as np

from ..planar import dist_polyline, inside_poly
from . import roofparts as RP
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
COLLAR_MM = 300.0            # AG4: a skybridge's collar zone at the facades it meets
WHEEL_TOL_MM = 250.0         # AG5: a wheel's members past the box of its masses by their section
# merged parts keep their slots: how far each slot may reach (the rest: AG1's rule)
SLOT_REACH = {"frame": "flush", "sill": "flush", "mullion": "flush",
              "spandrel_panel": "flush", "shutter": "flush", "grille": "flush",
              "member": "flush", "timber": "flush", "patch_ply": "flush", "column": "flush",
              "balcony": "deep", "railing": "deep", "glazing": "deep", "canopy": "deep",
              "fin": "strip", "perforated": "strip", "pod": "strip", "ac": "strip",
              "dish": "strip", "tile": "strip", "louver": "strip",
              "stanchion": "street", "rope": "street"}
SLOT_REACH.update({"court_paving": "court", "planter": "court", "green_roof": "court",
                   "coping": "flush", "coping_stone": "flush",
                   # AG4's facade details and portal frames, merged, reach as their family
                   "escape": "deep", "duct": "strip", "cable": "flush", "camera": "strip",
                   "camera_lens": "strip", "portal_lining": "strip", "lamp_white": "strip"})
# AG5: plinths and skirts on slopes, eaves, columns, doors, lights, a wheel's structure
SLOT_REACH.update({"retaining": "flush", "eave_tile": "deep", "eave_soffit": "deep",
                   "stone": "flush", "hangar_door": "flush", "hero_frame": "flush",
                   "hero_light": "flush", "shanty_roof": "strip", "wheel_steel": "wheel",
                   "gondola": "wheel", "escape_rust": "deep", "atrium_glass": "court",
                   "atrium_frame": "court", "platform": "station"})
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
        groups.append((pos, "roof" if name in RP.ROOF_SLOTS else
                       SLOT_REACH.get(name, "shell"), name))
    for pos, reach in parts or []:
        groups.append((np.asarray(pos, dtype=np.float64), reach, "part"))
        out["parts"] += len(pos)
    for pos, reach, name in groups:
        x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
        out["vertices"] += len(pos)
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
        if reach == "roof":
            # on a mass's roof (within 1 m of its footprint), or inside the masses
            ok = np.zeros(len(pos), dtype=bool)
            for z0, z1, ext, holes in masses:
                d = dist_polyline(x, y, ext + ext[:1])
                on = (inside_poly(x, y, ext, []) | (d <= 1000.0)) & (z >= z1 - TOL_MM)
                if name == "mast":
                    on &= z <= z1 + cap
                ok |= on
            ok |= inside & (z <= top)
            out["equipment_off_roof"] += int((~ok).sum())
            continue
        over = ~inside
        high = z >= STRIP_MIN_MM
        allowed = (near <= OVERHANG_MM) & high
        if reach in ("flush", "strip", "deep"):
            allowed |= near <= FLUSH_MM
        if reach == "deep":
            allowed |= (near <= DEEP_MM) & high
        if reach == "street":
            allowed |= (near <= STREET_MM) & (z <= STREET_Z)
        if reach == "court":
            for z0, z1, ext, holes in masses:
                allowed |= inside_poly(x, y, ext, []) & (z >= z0 - TOL_MM) & \
                    (z <= z1 + PARAPET_MM)
        if reach == "wheel" and masses:
            # (AG5: a wheel's rim, axle and legs are one open-air structure: inside the
            # box of its masses)
            t = WHEEL_TOL_MM
            bx0 = min(min(p[0] for p in e) for _, _, e, _ in masses) - t
            bx1 = max(max(p[0] for p in e) for _, _, e, _ in masses) + t
            by0 = min(min(p[1] for p in e) for _, _, e, _ in masses) - t
            by1 = max(max(p[1] for p in e) for _, _, e, _ in masses) + t
            bz0 = min(z0 for z0, _, _, _ in masses) - t
            bz1 = max(z1 for _, z1, _, _ in masses) + t
            allowed |= (x >= bx0) & (x <= bx1) & (y >= by0) & (y <= by1) & (z >= bz0) & \
                (z <= bz1)
        if reach == "station":
            # (AG5: a sky station beside its tower: its platform within the station's
            # footprint and the deck across to the wall, down to a roof it rests on)
            from .connections import STATION_LINK, STATION_REST
            for pr in brief.get("portals") or []:
                pf = pr.get("platform")
                if not pr.get("station") or not pf:
                    continue
                ext = [(q[0] * 1000.0, q[1] * 1000.0) for q in pf["exterior"]]
                holes = [[(q[0] * 1000.0, q[1] * 1000.0) for q in h] for h in pf["holes"]]
                d = dist_polyline(x, y, ext + ext[:1])
                allowed |= (inside_poly(x, y, ext, holes) | (d <= STATION_LINK + TOL_MM)) & \
                    (z >= pr["z"][0] * 1000.0 - STATION_REST - TOL_MM) & \
                    (z <= pr["z"][1] * 1000.0 + TOL_MM)
        bad = over & ~allowed
        out["outside"] += int(bad.sum())
        out["low_overhang"] += int((bad & (near <= DEEP_MM) & ~high).sum())
        out["too_high"] += int((z > top + PARAPET_MM).sum())
    out["ok"] = out["outside"] == 0 and out["too_high"] == 0 and \
        out["equipment_off_roof"] == 0
    return out


def fits(brief: dict, family: str, p: dict, x: int, y: int, z: int, ux: float,
         uy: float) -> bool:
    """AG4: whether one part placed so stays inside the envelope, by its family's reach and
    its slots' (it may be instanced or merged); the details and the roof's extras ask
    before they place one."""
    from . import parts as PT
    _, arrs = PT.mesh(family, p)
    placed = PT.place(arrs, x, y, z, ux, uy)
    if not placed:
        return True
    pts = np.concatenate([np.unique(a["pos"], axis=0) for a in placed.values()])
    return check(brief, placed, [(pts, PT.REACH[family])])["ok"]


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


def clearances(brief: dict, arrs: dict, parts: list | None = None) -> dict:
    """AG4 (scope 9): nothing the asset adds to its masses (overhangs, roof forms, roof
    equipment, masts) inside the corridor of a skybridge, a transit guideway and its
    trains or a sky tube passing near it (the brief's `clearances`), and every portal open
    (no point of the building inside its sky tube's section and 0.15 m round it). A sky
    tube that passes through one of the building's portals is held to the portal's test:
    its corridor's margin there is the portal's lining, frame and platforms."""
    pts = [np.unique(a["pos"], axis=0).astype(np.float64) for a in arrs.values()]
    pts += [np.asarray(p, dtype=np.float64) for p, _ in (parts or [])]
    out = {"corridors": len(brief.get("clearances") or []), "hits": 0, "portal_hits": 0,
           "first": None}
    if not pts:
        out["ok"] = True
        return out
    P = np.concatenate(pts)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    if brief.get("clearances"):
        inside = np.zeros(len(P), dtype=bool)
        for m in brief["masses"]:
            ext = [(q[0] * 1000.0, q[1] * 1000.0) for q in m["footprint"]["exterior"]]
            holes = [[(q[0] * 1000.0, q[1] * 1000.0) for q in h] for h in
                     m["footprint"]["holes"]]
            z0, z1 = m["z"][0] * 1000.0, m["z"][1] * 1000.0
            d = dist_polyline(x, y, ext + ext[:1])
            inside |= (z >= z0 - TOL_MM) & (z <= z1 + TOL_MM) & \
                (inside_poly(x, y, ext, holes) | (d <= TOL_MM))
        through = {p["line_id"] for p in brief.get("portals") or []}
        for c in brief["clearances"]:
            if c["kind"] == "sky_tube" and any(c["id"].startswith(f"{t}.") for t in through):
                continue
            h = c["half_m"] * 1000.0 - 20.0
            ln = c["line"]
            for p, q in zip(ln, ln[1:]):
                ax, ay, bx, by = p[0] * 1000.0, p[1] * 1000.0, q[0] * 1000.0, q[1] * 1000.0
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                if L2 == 0:
                    continue
                t = ((x - ax) * dx + (y - ay) * dy) / L2
                tt = np.minimum(np.maximum(t, 0.0), 1.0)
                ex, ey = ax + dx * tt - x, ay + dy * tt - y
                d = np.sqrt(ex * ex + ey * ey)
                zlo = (p[2] + (q[2] - p[2]) * tt) * 1000.0 + 20.0
                zhi = (p[3] + (q[3] - p[3]) * tt) * 1000.0 - 20.0
                hit = (t >= 0.0) & (t <= 1.0) & (d < h) & (z > zlo) & (z < zhi) & ~inside
                if c["kind"] == "skybridge":
                    # (the bridge's collar zone at each facade it meets: 0.3 m)
                    L = L2 ** 0.5
                    hit &= (t * L > COLLAR_MM) & ((1.0 - t) * L > COLLAR_MM)
                k = int(hit.sum())
                if k:
                    out["hits"] += k
                    if out["first"] is None:
                        out["first"] = f"{c['kind']} {c['id']}"
    for pr in brief.get("portals") or []:
        R = pr["diameter_m"] * 500.0 + 150.0
        for ln in pr.get("lines") or []:
            for p, q in zip(ln, ln[1:]):
                ax, ay, bx, by = p[0] * 1000.0, p[1] * 1000.0, q[0] * 1000.0, q[1] * 1000.0
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                if L2 == 0:
                    continue
                t = ((x - ax) * dx + (y - ay) * dy) / L2
                tt = np.minimum(np.maximum(t, 0.0), 1.0)
                ex, ey = ax + dx * tt - x, ay + dy * tt - y
                ax_z = (p[2] + (q[2] - p[2]) * tt) * 1000.0 - pr["diameter_m"] * 500.0
                r2 = ex * ex + ey * ey + (z - ax_z) * (z - ax_z)
                hit = (t >= 0.0) & (t <= 1.0) & (r2 < R * R)
                k = int(hit.sum())
                if k:
                    out["portal_hits"] += k
                    if out["first"] is None:
                        out["first"] = f"portal {pr['line_id']}"
    out["ok"] = out["hits"] == 0 and out["portal_hits"] == 0
    return out
