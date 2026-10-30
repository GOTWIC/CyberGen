"""M16 checks: water and ground detail. They run on cities that carry M16's data (banks or
ground cover):

- `water_beds`: every water body has its depth, bed and flow (still water for basins,
  marinas and ornamental pools; the sea's exposure covers it); no bed deeper than the bed
  M9's tunnels assume for its class (`water.max_depth`); every tunnel under the water keeps
  `tunnels.BED_COVER_M` of backfill under the bed as it is; every bridge foundation in the
  water (the piers every 40 m under a bridge deck over it, the columns and pylons standing
  in it) sits on bed no deeper than its footing (M9's bed).
- `water_banks`: the banks cover every water edge once (their length is the edge's, every
  point of the edge on a bank, no two overlapping); each bank is well formed (a quay on its
  quay with the quay's height, a road embankment on its road, a width and toe).
- `ground_cover`: the pieces tile the open land once: no two overlap, none lies under a
  building, a road or the water, and every part of the open land not covered is a curb
  corner narrower than `cover.SLIVER_M`.
- `regen_locality` (a district regeneration only, `edit.py`): outside the district and its
  seam (`SEAM_M`) the water bodies' data, the banks and the ground cover change only where
  what they are made from (`INPUTS`: a crowd density, a walkway the splice changed) changed
  within `SEAM_M` of them.
"""

from __future__ import annotations

import math

import shapely
from shapely.geometry import LineString, Point

from . import cover as CV
from . import geom as G
from . import water as WA
from .checks import Check

SHOW = 12
LEN_TOL = 0.005
SEAM_M = 60.0
PIER_STEP_M = 40.0      # the blockout's piers under a bridge deck over the water
DECK_M = 1.2


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < SHOW:
        c.failures.append(msg)
    elif len(c.failures) == SHOW:
        c.failures.append("...")


def _cum(pts) -> list[float]:
    return WA._cum(pts)


def _along(pts, step: float):
    """Points every `step` along a polyline (with its z when it has one)."""
    cum = _cum([(p[0], p[1]) for p in pts])
    out = []
    n = max(1, int(cum[-1] // step))
    for k in range(n + 1):
        s = min(cum[-1], k * step)
        i = 0
        while i < len(pts) - 2 and cum[i + 1] < s:
            i += 1
        L = cum[i + 1] - cum[i]
        t = 0.0 if L <= 0 else (s - cum[i]) / L
        a, b = pts[i], pts[i + 1]
        p = [a[j] + (b[j] - a[j]) * t for j in range(len(a))]
        out.append(p)
    return out


def check_beds(m) -> Check:
    from .tunnels import BED_COVER_M, BED_M

    c = Check("water_beds", "Every water body has its depth, bed and flow (basins, marinas and "
                            "pools still; the sea's exposure covers it); no bed under M9's "
                            f"(canal {BED_M['canal']:g}, river {BED_M['river']:g}, sea "
                            f"{BED_M['sea']:g} m under the ground datum); tunnels keep "
                            f"{BED_COVER_M:g} m under the bed; bridge foundations in the water "
                            "on bed no deeper than their footings")
    flat = m.terrain is None
    beds = WA.Beds(m)
    for b in beds.bl.values():
        e = b.ent
        if e.depth_m is None or e.bed is None or e.flow is None:
            _limit(c, f"{b.id}: no depth, bed or flow")
            continue
        D = WA.max_depth(b.cls, flat)
        if e.depth_m > D + 0.01 or any(a.z > e.depth_m + 0.01 for a in e.bed.along):
            _limit(c, f"{b.id}: {e.depth_m:g} m deep, deeper than {D:g} m")
        if b.kind in ("basin", "marina", "ornamental") and e.flow.kind != "still":
            _limit(c, f"{b.id} ({b.kind}): flowing water")
        if e.flow.speed_m_s < 0:
            _limit(c, f"{b.id}: negative flow speed")
    for s in m.seas:
        if s.depth_m is None:
            continue
        sea = G.union([G.from_model_poly(p) for p in s.polygons])
        zone = G.union([G.from_model_poly(x.polygon) for x in s.exposure])
        miss = G.area(G.diff(sea, zone)) if not zone.is_empty else G.area(sea)
        if miss > max(0.005 * G.area(sea), 5000.0):
            _limit(c, f"{s.id}: {miss:.0f} m2 of the sea without an exposure")
    # tunnels under the water
    n_t = 0
    for t in m.tunnels:
        top = t.clear_m + t.roof_m
        for x, y, z in _along([tuple(p) for p in t.line], 10.0):
            wid = beds.body_at(x, y)
            if wid is None:
                continue
            n_t += 1
            cov = beds.bed_z(wid, x, y) - (z + top)
            if cov < BED_COVER_M - 0.05:
                _limit(c, f"{t.id} ({t.kind}): {cov:.2f} m under the bed of {wid} at "
                          f"({x:.0f}, {y:.0f})")
                break
    # bridge foundations
    feet = []
    for br in m.bridges:
        pts = [tuple(p) for p in br.line]
        if len(pts) < 2:
            continue
        for x, y, z in _along(pts, PIER_STEP_M):
            if z > DECK_M + 1.0:
                feet.append((br.id, x, y))
    for st in m.structures:
        if st.kind in ("column", "pylon") and st.footprint is not None:
            x, y = G.centroid(G.from_model_poly(st.footprint))
            feet.append((st.id, x, y))
    n_f = 0
    for fid, x, y in feet:
        wid = beds.body_at(x, y)
        if wid is None:
            continue
        n_f += 1
        b = beds.bl[wid]
        foot = -BED_M[b.cls]
        z = beds.bed_z(wid, x, y)
        if z < foot - 0.01:
            _limit(c, f"{fid}: the bed of {wid} at ({x:.0f}, {y:.0f}) {foot - z:.2f} m under "
                      "its footing")
    c.notes.append(f"{n_t} tunnel points and {n_f} bridge foundations under the water")
    return c


def check_banks(m) -> Check:
    c = Check("water_banks", "The banks cover every water edge once (the edge's length, every "
                             "point on a bank, none overlapping); quays on their quays at the "
                             "quay's height, road embankments on their roads, widths and toes")
    with G.canonical():
        ground, _ = WA.ground_of(m)
        shores = WA.shore_lines(m, ground)
    quays = {q.id: q for q in m.quays}
    segs = {s.id for s in m.road_segments}
    depth = {b.id: b.ent.depth_m for b in WA.bodies(m)}
    for k in m.banks:
        if k.type != f"bank.{k.kind}":
            _limit(c, f"{k.id}: type {k.type} for a {k.kind}")
        if k.kind == "quay":
            q = quays.get(k.quay_id)
            if q is None or q.waterway_id != k.water_id or k.height_m is not None:
                _limit(c, f"{k.id}: a quay bank without its quay (or with a height of its own)")
        elif k.height_m is None or k.height_m < 0 or k.quay_id is not None:
            _limit(c, f"{k.id}: no height")
        if k.kind == "road_embankment" and k.segment_id not in segs:
            _limit(c, f"{k.id}: a road embankment without its road")
        if k.width_m <= 0 or k.toe_m < 0 or (depth.get(k.water_id) is not None and
                                             k.toe_m > depth[k.water_id] + 0.01):
            _limit(c, f"{k.id}: width {k.width_m:g}, toe {k.toe_m:g}")
        if k.water_id not in depth:
            _limit(c, f"{k.id}: on no water body ({k.water_id})")
    total = math.fsum(_cum(s)[-1] for s in shores)
    banked = math.fsum(_cum(k.line)[-1] for k in m.banks)
    if abs(banked - total) > max(LEN_TOL * total, 1.0):
        _limit(c, f"banks {banked:.0f} m long, the water's edges {total:.0f} m")
    lines = [LineString(k.line) for k in m.banks]
    tree = shapely.STRtree(lines) if lines else None
    miss = 0
    for s in shores:
        for x, y in _along(s, 10.0):
            pt = Point(x, y)
            if tree is None or not len(tree.query(pt, predicate="dwithin", distance=0.05)):
                miss += 1
                if miss <= 3:
                    _limit(c, f"the water's edge at ({x:.0f}, {y:.0f}) on no bank")
    if miss > 3:
        _limit(c, f"{miss} points of the water's edges on no bank")
    if lines:
        union = G.length(shapely.union_all(lines, grid_size=0.01))
        if banked - union > max(LEN_TOL * banked, 1.0):
            _limit(c, f"banks overlap: {banked - union:.0f} m")
    return c


def check_cover(m) -> Check:
    c = Check("ground_cover", "The ground cover tiles the open land once: no two pieces "
                              "overlap, none under a building, a road or the water, and the "
                              "open land it leaves is curb corners narrower than "
                              f"{CV.SLIVER_M:g} m")
    if not m.ground_cover:
        return c
    with G.canonical():
        cx = CV.Ctx(m)
        P = G.from_model_poly
        polys = [P(g.polygon) for g in m.ground_cover]
        tree = shapely.STRtree(polys)
        # overlaps
        a, b = tree.query(polys, predicate="intersects")
        bad = 0
        for i, j in zip(a.tolist(), b.tolist()):
            if i >= j:
                continue
            ov = G.area(G.inter(polys[i], polys[j]))
            if ov > 0.5:
                bad += 1
                if bad <= 3:
                    _limit(c, f"{m.ground_cover[i].id} and {m.ground_cover[j].id} overlap "
                              f"({ov:.1f} m2)")
        if bad > 3:
            _limit(c, f"{bad} overlapping pairs")
        # under a building, a road or the water
        for what, tr, geoms in (("a building or site element", cx.htree, cx.hard),
                                ("the right of way", cx.rtree, cx.row),
                                ("the water", cx.wtree, cx.wet)):
            if tr is None:
                continue
            hits = 0
            a, b = tr.query(polys, predicate="intersects")
            seen = {}
            for i, j in zip(a.tolist(), b.tolist()):
                seen.setdefault(i, []).append(j)
            for i in sorted(seen):
                ov = G.area(G.inter(polys[i], G.union_local([geoms[j] for j in seen[i]])))
                if ov > 1.0:
                    hits += 1
                    if hits <= 3:
                        _limit(c, f"{m.ground_cover[i].id} under {what} ({ov:.1f} m2)")
            if hits > 3:
                _limit(c, f"{hits} pieces under {what}")
        # the open land it leaves
        left = 0
        for did, zone in CV._zones(cx):
            cut = cx._near(cx.rtree, cx.row, zone) + cx._near(cx.wtree, cx.wet, zone) + \
                cx._near(cx.htree, cx.hard, zone) + \
                [polys[k] for k in sorted(int(i) for i in tree.query(zone,
                                                                     predicate="intersects"))]
            rest = G.inter(G.diff(zone, G.union_local(cut)), cx.land)
            for p in G.parts(rest):
                A = G.area(p)
                if A >= CV.MIN_PIECE_M2 * 20 and CV.width_of(p) >= CV.SLIVER_M:
                    left += 1
                    if left <= 3:
                        x, y = G.qpoint(p.representative_point())
                        _limit(c, f"{A:.0f} m2 of open land in {did or 'no district'} "
                                  f"uncovered at ({x:.0f}, {y:.0f})")
        if left > 3:
            _limit(c, f"{left} uncovered pieces of open land")
    return c


def run(spec, m) -> list:
    return [check_beds(m), check_banks(m), check_cover(m)]


def stats(m) -> dict:
    banks: dict[str, list] = {}
    for k in m.banks:
        r = banks.setdefault(k.kind, [0, 0.0])
        r[0] += 1
        r[1] += _cum(k.line)[-1]
    cover: dict[str, list] = {}
    for g in m.ground_cover:
        r = cover.setdefault(g.kind, [0, 0.0])
        r[0] += 1
        r[1] += g.area_m2
    bodies = []
    for b in WA.bodies(m):
        e = b.ent
        if e.depth_m is None:
            continue
        bodies.append({"id": b.id, "kind": b.kind, "depth_m": e.depth_m,
                       "flow": e.flow.kind if e.flow else None,
                       "speed_m_s": e.flow.speed_m_s if e.flow else None})
    expo: dict[str, float] = {}
    for s in m.seas:
        for x in s.exposure:
            expo[x.kind] = expo.get(x.kind, 0.0) + G.area(G.from_model_poly(x.polygon))
    return {"water_bodies": len(bodies), "bodies": bodies,
            "banks": {k: {"count": v[0], "km": round(v[1] / 1000.0, 2)}
                      for k, v in sorted(banks.items())},
            "exposure_km2": {k: round(v / 1e6, 3) for k, v in sorted(expo.items())},
            "cover": {k: {"pieces": v[0], "km2": round(v[1] / 1e6, 3)}
                      for k, v in sorted(cover.items())},
            "desire_lines": sum(len(g.desire_lines) for g in m.ground_cover)}


# --- regeneration locality ---------------------------------------------------------------------

# what M16's rows are made from: a row may change where one of these changed near it
INPUTS = ("land", "districts", "road_segments", "junctions", "walkways", "quays", "lots",
          "open_spaces", "megasites", "site_elements", "buildings", "structures", "decks",
          "densities")


def _geom(e: dict):
    """The geometry of a model row (dict), or None."""
    from . import ids as ID

    for key in ("polygon", "footprint", "polygons"):
        v = e.get(key)
        if isinstance(v, dict):
            return G.from_model_poly(v)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return G.union([G.from_model_poly(x) for x in v])
    pts = ID._pts(e)
    if not pts:
        return None
    pts = [(p[0], p[1]) for p in pts]
    return LineString(pts) if len(pts) > 1 else shapely.geometry.Point(pts[0])


def check_locality(old, new, did: str, poly) -> Check:
    """`regen_locality`: what M16 made outside the district and its seam changed only where
    what it is made from changed near it (the splice's own seam: a crowd density, a walkway)."""
    c = Check("regen_locality", "A district regeneration changes the water bodies' data, the "
                                "banks and the ground cover outside the district and "
                                f"{SEAM_M:g} m around it only where what they are made from "
                                "changed within that distance")
    zone = poly.buffer(SEAM_M)
    shapely.prepare(zone)
    O, N = old.model_dump(mode="json"), new.model_dump(mode="json")
    segs = {s["id"]: s for side in (O, N) for s in side.get("road_segments", [])}
    moved = []
    for coll in INPUTS:
        a = {e["id"]: e for e in O.get(coll, [])}
        b = {e["id"]: e for e in N.get(coll, [])}
        for i in sorted(set(a) | set(b)):
            if a.get(i) == b.get(i):
                continue
            for e in (a.get(i), b.get(i)):
                if e is None:
                    continue
                if coll == "densities":
                    e = segs.get(e["segment_id"], {})
                g = _geom(e)
                if g is not None and not g.is_empty:
                    moved.append(g.buffer(SEAM_M))
    tree = shapely.STRtree(moved) if moved else None

    def explained(e) -> bool:
        if getattr(e, "district_id", None) == did:
            return True
        geo = getattr(e, "polygon", None)
        g = G.from_model_poly(geo) if geo is not None else LineString(e.line)
        if zone.intersects(g):
            return True
        return tree is not None and len(tree.query(g, predicate="intersects")) > 0

    for coll in ("banks", "ground_cover"):
        o = {e.id: e for e in getattr(old, coll)}
        n = {e.id: e for e in getattr(new, coll)}
        bad = 0
        for i in sorted(set(o) | set(n)):
            a, b = o.get(i), n.get(i)
            if a is not None and b is not None and a == b:
                continue
            if not all(explained(e) for e in (a, b) if e is not None):
                bad += 1
                if bad <= 3:
                    _limit(c, f"{coll}: {i} changed outside the district with nothing under "
                              "it changed")
        if bad > 3:
            _limit(c, f"{coll}: {bad} changed outside the district with nothing under them "
                      "changed")
    for coll in ("seas", "rivers", "channels", "waterways"):
        o = {e.id: e for e in getattr(old, coll)}
        for e in getattr(new, coll):
            a = o.get(e.id)
            if a is None or getattr(e, "district_id", None) == did:
                continue
            if ((a.depth_m, a.bed, a.flow) != (e.depth_m, e.bed, e.flow) or
                    getattr(a, "exposure", None) != getattr(e, "exposure", None)):
                _limit(c, f"{coll}: {e.id}'s depth, bed, flow or exposure changed")
    return c
