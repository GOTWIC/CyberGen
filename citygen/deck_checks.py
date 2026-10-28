"""M14 checks: layered districts (decks). A city without decks runs none of them."""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import decks as DK
from . import geom as G
from .checks import Check
from .model import CityModel

LIMIT = 12
SAMPLE_M = 6.0
TOL_M = 0.05


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < LIMIT:
        c.failures.append(msg)
    elif len(c.failures) == LIMIT:
        c.failures.append("... more")


def _samples(poly, step: float) -> list:
    from . import massing as MS

    return DK._grid(poly, step, MS.obb_angle(poly))


def check_columns(m: CityModel) -> Check:
    c = Check("deck_columns", f"Every deck on columns: no point of a slab farther than "
                              f"{DK.COLUMN_REACH:g} x its column grid from a column "
                              f"({DK.JUNCTION_REACH:g} x over a ground junction, "
                              f"{DK.CANTILEVER_M:g} m more within that of its edge), every "
                              "column from the ground to the slab's underside, none in a "
                              "lane, a crosswalk, a junction or a sidewalk's clear path")
    cols = {s.id: s for s in m.structures if s.kind == "column" and (s.attrs or {}).get("deck")}
    for dk in m.decks:
        P = G.from_model_poly(dk.polygon)
        mine = [cols[i] for i in dk.column_ids if i in cols]
        if len(mine) != len(dk.column_ids):
            _limit(c, f"{dk.id}: {len(dk.column_ids) - len(mine)} columns missing")
        if not mine:
            _limit(c, f"{dk.id}: no columns")
            continue
        under = G.q(dk.top_m - dk.slab_m)
        pts = []
        for s in mine:
            fp = G.from_model_poly(s.footprint)
            pts.append(G.centroid(fp))
            if abs(s.z0_m) > TOL_M or abs(s.z1_m - under) > TOL_M:
                _limit(c, f"{s.id}: from {s.z0_m:g} to {s.z1_m:g} m, the slab's underside is "
                          f"at {under:g} m")
        g = float(dk.attrs.get("column_m", 18.0))
        reach = DK.COLUMN_REACH * g
        tree = shapely.STRtree(shapely.points(pts))
        over = DK.span_zone(m, P)
        far = 0
        worst = 0.0
        for sp in _samples(P, SAMPLE_M):
            k = tree.query_nearest(Point(sp), return_distance=True)
            d = float(k[1][0])
            r = DK.JUNCTION_REACH * g if not over.is_empty and over.contains(Point(sp)) \
                else reach
            if G.dist(P.boundary, Point(sp)) <= DK.CANTILEVER_M:
                r += DK.CANTILEVER_M
            if d > r + TOL_M:
                far += 1
                worst = max(worst, d)
        if far:
            _limit(c, f"{dk.id}: {far} points of the slab farther than {reach:.1f} m from a "
                      f"column (up to {worst:.1f} m)")
        bad = DK._keepout(_without_columns(m), P)
        for s in mine:
            fp = G.from_model_poly(s.footprint)
            ov = G.area1(G.inter(fp, bad)) if not bad.is_empty else 0.0
            if ov > 0.05:
                _limit(c, f"{s.id}: in a lane, crosswalk, junction, clear path, walkway, "
                          f"doorway or structure ({ov:.2f} m2)")
    return c


def _without_columns(m: CityModel) -> CityModel:
    return m.model_copy(update={"structures": [s for s in m.structures if not (
        s.kind == "column" and (s.attrs or {}).get("deck"))]})


def check_headroom(m: CityModel) -> Check:
    c = Check("deck_headroom", f"Under every deck {DK.CLEAR_M:g} m of clear height over the "
                               "ground streets; the buildings under it stop under its slab; "
                               "nothing else passes through a slab (towers, skybridges, "
                               "transit, raised roads)")
    for dk in m.decks:
        P = G.from_model_poly(dk.polygon)
        shapely.prepare(P)
        under = dk.top_m - dk.slab_m
        if under < DK.CLEAR_M - TOL_M:
            _limit(c, f"{dk.id}: {under:g} m clear under the slab")
        for b in m.buildings:
            if b.level:
                continue
            for ms in b.masses:
                fp = G.from_model_poly(ms.footprint)
                if not fp.intersects(P) or G.area1(G.inter(fp, P)) < 0.5:
                    continue
                if ms.z1_m > under + TOL_M and ms.z0_m < dk.top_m - TOL_M:
                    _limit(c, f"{b.id}: a mass from {ms.z0_m:g} to {ms.z1_m:g} m runs into "
                              f"{dk.id} (underside {under:g} m)")
                    break
        for s in m.skybridges:
            g = LineString(s.line).buffer(s.width_m / 2, cap_style="flat")
            lv = {x.level for x in m.buildings if x.id in s.building_ids}
            z0, z1 = s.z_m - 1.0, s.z_m + s.levels * s.level_height_m
            if g.intersects(P) and G.area1(G.inter(G.qpoly(g), P)) > 0.5 and \
                    z1 > under and z0 < dk.top_m + DK.CLEAR_M and lv != {1}:
                _limit(c, f"{s.id}: a skybridge through {dk.id}")
        for s in m.road_segments:
            if "deck" in s.attrs:
                continue
            if not any(z.z > 0.5 for z in s.z_profile):
                continue
            line = LineString(s.centerline)
            if not line.intersects(P):
                continue
            for p in DK.walk_points(s.centerline, 10.0):
                if P.contains(Point(p[0], p[1])):
                    t = line.project(Point(p))
                    z = _z_on(s.z_profile, t)
                    if z > under - DK.CLEAR_M and z < dk.top_m + DK.CLEAR_M:
                        _limit(c, f"{s.id}: a raised road through {dk.id} ({z:.1f} m)")
                        break
        for t in m.transit_lines:
            if t.mode == "metro":
                continue
            for x, y, z in t.path:
                if z > 0.5 and z < dk.top_m + DK.CLEAR_M and P.contains(Point(x, y)):
                    _limit(c, f"{t.id}: track at {z:.1f} m through {dk.id}")
                    break
    return c


def _z_on(prof, t: float) -> float:
    from .junctions import _z_at

    return _z_at([{"s": z.s, "z": z.z} for z in prof], t)


def check_light(m: CityModel) -> Check:
    c = Check("deck_light", "Light under every deck: no ground walkway under a slab farther "
                            "than the deck's light_m from open sky (its light wells and edge)")
    for dk in m.decks:
        P = G.from_model_poly(dk.polygon)
        lim = float(dk.attrs.get("light_m", 70.0))
        pts = []
        for w in m.walkways:
            if w.level or not DK.on_ground(w) or w.kind not in DK.LIGHT_KINDS:
                continue
            pts += DK.walk_points([p[:2] for p in w.line], DK.SAMPLE_M)
        if not pts:
            continue
        arr = shapely.points(sorted(set(pts)))
        inside = shapely.contains(P, arr)
        d = G.dists(P.boundary, arr[inside])
        far = int((d > lim + TOL_M).sum())
        if far:
            _limit(c, f"{dk.id}: {far} walkway points under the slab farther than {lim:g} m "
                      f"from the sky (up to {float(d.max()):.0f} m)")
        else:
            c.notes.append(f"{dk.id}: walkways under the slab within "
                           f"{float(d.max()) if len(d) else 0.0:.0f} m of the sky")
    return c


def check_links(m: CityModel) -> Check:
    c = Check("deck_links", "Every deck joined to the ground: at least two stairs and an "
                            "elevator from ground walkways to deck walkways, every deck "
                            "walkway in one walkway component with the ground's, at least one "
                            "ramp from a deck street to a ground junction, its lanes in the "
                            "lane graph's largest strongly connected part")
    from .gameplay import largest_scc, lane_graph
    from .street_checks import walk_components

    walk = {w.id: w for w in m.walkways}
    roots = walk_components(m)
    seg = {s.id: s for s in m.road_segments}
    nodes = {n.id: n for n in m.road_nodes}
    scc = largest_scc(lane_graph(m))
    for dk in m.decks:
        links = [walk[i] for i in dk.walkway_ids if i in walk]
        kinds = [w.kind for w in links]
        if kinds.count("stairs") < 2 or kinds.count("elevator") < 1:
            _limit(c, f"{dk.id}: {kinds.count('stairs')} stairs, "
                      f"{kinds.count('elevator')} elevators")
        for w in links:
            a, b = DK.walk_ends(w)
            ns = [walk[x] for x in w.neighbors if x in walk]
            lo = [x for x in ns if a in DK.walk_ends(x)]
            hi = [x for x in ns if b in DK.walk_ends(x)]
            if not lo or not hi:
                _limit(c, f"{w.id} ({w.kind}): joins {'no ground walkway' if not lo else ''}"
                          f"{' and ' if not lo and not hi else ''}"
                          f"{'no deck walkway' if not hi else ''}")
        ground = {roots[DK.walk_ends(w)[0]] for w in m.walkways if not w.level and
                  w.kind == "sidewalk"}
        mine = [w for w in m.walkways if w.level and (w.attrs or {}).get("deck", dk.id) ==
                dk.id and DK.on_ground(w)]
        off = [w.id for w in mine if roots.get(DK.walk_ends(w)[0]) not in ground]
        if off:
            _limit(c, f"{dk.id}: {len(off)} deck walkways cut off from the ground's "
                      f"({', '.join(off[:3])})")
        ramps = [seg[i] for i in dk.segment_ids if i in seg and
                 seg[i].attrs.get("role") == "deck_ramp"]
        if not ramps:
            _limit(c, f"{dk.id}: no ramp")
        for r in ramps:
            ends = [nodes[x] for x in (r.start, r.end) if x in nodes]
            if sorted(n.level for n in ends) != [0, 1]:
                _limit(c, f"{r.id}: does not join the ground to the deck")
        lanes = [ln for ln in m.lanes if ln.kind == "lane" and ln.segment_id in
                 set(dk.segment_ids)]
        out = [ln.id for ln in lanes if ln.id not in scc]
        if out:
            _limit(c, f"{dk.id}: {len(out)} deck lanes off the lane graph's largest strongly "
                      f"connected part ({', '.join(out[:3])})")
    return c


def check_levels(m: CityModel) -> Check:
    c = Check("deck_levels", "Every deck's streets at its top, its lots on its slab, its "
                             "buildings standing on its top, its props, plants and walkways "
                             "over its slab at its top; nothing on level 1 off a deck")
    deck = {dk.id: dk for dk in m.decks}
    polys = {dk.id: G.qpoly(G.from_model_poly(dk.polygon).buffer(0.5, join_style="mitre"))
             for dk in m.decks}
    for p in polys.values():
        shapely.prepare(p)
    union = G.union(list(polys.values())) if polys else None
    for s in m.road_segments:
        dk = deck.get(s.attrs.get("deck"))
        if dk is None or s.attrs.get("role") == "deck_ramp":
            continue
        if any(abs(z.z - dk.top_m) > TOL_M for z in s.z_profile):
            _limit(c, f"{s.id}: not at the top of {dk.id} ({dk.top_m:g} m)")
    for lt in m.lots:
        if not lt.level:
            continue
        dk = deck.get(lt.attrs.get("deck"))
        poly = G.from_model_poly(lt.polygon)
        if dk is None or G.area1(G.diff(poly, polys[dk.id])) > 1.0:
            _limit(c, f"{lt.id}: a deck lot off its slab")
    for b in m.buildings:
        if not b.level:
            continue
        dk = deck.get(b.attrs.get("deck"))
        z0 = min(ms.z0_m for ms in b.masses)
        if dk is None or abs(z0 - dk.top_m) > TOL_M:
            _limit(c, f"{b.id}: stands at {z0:g} m, not on its deck's top")
    for coll, kind in ((m.props, "prop"), (m.plants, "plant")):
        pts = [x for x in coll if x.level]
        if not pts:
            continue
        inside = shapely.contains(union, shapely.points([x.position[:2] for x in pts]))
        tops = [dk.top_m for dk in m.decks]
        for x, k in zip(pts, inside.tolist()):
            if not k or x.position[2] < min(tops) - TOL_M:
                _limit(c, f"{x.id}: a {kind} of level 1 off a deck or under its top")
    for w in m.walkways:
        if not w.level or not DK.on_ground(w):
            continue
        dk = deck.get(w.attrs.get("deck")) if w.attrs.get("deck") else None
        top = dk.top_m if dk is not None else m.decks[0].top_m
        if any(abs(p[2] - top) > TOL_M for p in w.line):
            _limit(c, f"{w.id}: a deck walkway off the deck's top")
    return c


def run(spec, m: CityModel) -> list:
    if not m.decks:
        return []
    with G.canonical():
        return [check_columns(m), check_headroom(m), check_light(m), check_links(m),
                check_levels(m)]


def stats(m: CityModel) -> dict:
    out = {}
    for dk in m.decks:
        out[dk.id] = {"area_m2": dk.area_m2, "top_m": dk.top_m,
                      "streets": len(dk.segment_ids), "wells": len(dk.well_ids),
                      "columns": len(dk.column_ids), "links": len(dk.walkway_ids),
                      "upper_lots": sum(1 for lt in m.lots if lt.level and
                                        lt.attrs.get("deck") == dk.id),
                      "upper_buildings": sum(1 for b in m.buildings if b.level and
                                             b.attrs.get("deck") == dk.id)}
    return out
