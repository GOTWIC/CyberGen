"""M5 checks: transit lines, stations and supports (scope section 9, transit parts)."""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from . import presets
from .checks import Check
from .model import CityModel
from .spec import CitySpec
from .transit import (DECK_M, ROAD_CLEAR_M, SERVE_M, SIDE_PAD_M, SKY_CLEAR_M, UNDER_PAD_M,
                      WIDTH_M, above, road_underside,
                      below, deck_heights, radii, raised_roads, resample, sidewalk_index,
                      sidewalks_clear)

LIMIT = 12
RADIUS_TOL = 0.98    # radius measured on 30 m chords of a polyline arc
GRADE_TOL = 0.002
EXIT_M = 300.0


def _check(cid: str, desc: str) -> Check:
    return Check(cid, desc)


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < LIMIT:
        c.failures.append(msg)
    elif len(c.failures) == LIMIT:
        c.failures.append("... more")


def _xy(line) -> list[tuple]:
    return [(p[0], p[1]) for p in line.path]


def _track(line) -> tuple[list[tuple], list[float]]:
    pts = [(p[0], p[1]) for p in line.path]
    zs = [p[2] for p in line.path]
    return pts, zs


def check_routes(spec: CitySpec, m: CityModel) -> Check:
    c = _check("transit_routes", "Every transit line of the spec is built along its whole "
                                 "route (every leg found)")
    built = {t.name: t for t in m.transit_lines}
    for tl in spec.transit.lines:
        t = built.get(tl.name)
        if t is None:
            _limit(c, f"{tl.name}: not built")
        elif "route" in t.attrs.get("conflicts", []):
            _limit(c, f"{tl.name}: a leg has no route")
    return c


def check_stops(spec: CitySpec, m: CityModel) -> Check:
    c = _check("transit_stops", f"Every stop of a line is served by one of its stations (in "
                                f"the district, within {SERVE_M:g} m of the site, place or "
                                f"island), and a line to an exit reaches it")
    st = {s.id: s for s in m.stations}
    dist = {d.name: d for d in m.districts}
    sites = {s.name: s for s in m.megasites}
    places = {p.name: p for p in m.places}
    isles = {i.name: i for i in m.islands}
    nexus = {d.id: s for s in m.megasites if s.kind == "transit_nexus" for d in m.districts
             if d.id == s.district_id}
    exits = {n.attrs.get("exit"): (n.position[0], n.position[1]) for n in m.road_nodes
             if n.attrs.get("exit")}
    for t in m.transit_lines:
        pts = [Point(s_.position[0], s_.position[1]) for s_ in
               (st[i] for i in t.station_ids)]
        track = LineString(_xy(t))
        for name in t.attrs.get("stops", []):
            if name.endswith("_exit"):
                p = exits.get(name)
                end = [track.coords[0], track.coords[-1]]
                if p is not None and min(math.dist(p, e) for e in end) > EXIT_M:
                    _limit(c, f"{t.name}: ends {min(math.dist(p, e) for e in end):.0f} m from "
                              f"{name}")
                continue
            if name in sites:
                zone = G.from_model_poly(sites[name].polygon).buffer(SERVE_M)
            elif name in dist:
                zone = G.from_model_poly(dist[name].polygon)
                if dist[name].id in nexus:  # reached by its nexus: up to SERVE_M outside
                    zone = zone.buffer(SERVE_M)
            elif name in places:
                zone = G.from_model_poly(places[name].polygon).buffer(SERVE_M)
            elif name in isles:
                zone = G.from_model_poly(isles[name].polygon).buffer(SERVE_M)
            else:
                _limit(c, f"{t.name}: stop '{name}' unknown")
                continue
            if not any(zone.covers(p) for p in pts):
                d = min((zone.distance(p) for p in pts), default=math.inf)
                _limit(c, f"{t.name}: no station serves '{name}' (nearest {d:.0f} m away)")
    return c


def check_curves(m: CityModel) -> Check:
    c = _check("transit_curves", "Track curve radius at least the mode minimum (elevated rail "
                                 "150 m, monorail 100, maglev 500, sky tube 300; measured "
                                 "through points 30 m apart)")
    for t in m.transit_lines:
        r_min = presets.TRANSIT_MODES[t.mode].min_curve_radius_m
        if not r_min:
            continue
        pts = _xy(t)
        if t.loop and pts[0] == pts[-1]:
            pts = pts[:-1]
        rr = radii(resample(pts, 10.0, t.loop), t.loop)
        low = min(rr) if rr else math.inf
        if low < RADIUS_TOL * r_min:
            _limit(c, f"{t.name} ({t.mode}): radius {low:.0f} m (minimum {r_min:g})")
    return c


def check_grades(m: CityModel) -> Check:
    c = _check("transit_grades", "Track grade at most the mode maximum (elevated rail 4%, "
                                 "monorail 6%, maglev 10%, sky tube 8%)")
    for t in m.transit_lines:
        g = presets.TRANSIT_MODES[t.mode].max_grade
        if g is None:
            continue
        pts, zs = _track(t)
        worst = 0.0
        for k in range(len(pts) - 1):
            L = math.dist(pts[k], pts[k + 1])
            if L > 0.5:
                worst = max(worst, abs(zs[k + 1] - zs[k]) / L)
        if worst > g + GRADE_TOL:
            _limit(c, f"{t.name} ({t.mode}): grade {worst:.3f} (maximum {g:g})")
    return c


def _water(m: CityModel) -> list:
    out = []
    for e in m.seas:
        out += [(G.from_model_poly(p), 25.0) for p in e.polygons]
    out += [(G.from_model_poly(e.polygon), 12.0) for e in m.rivers]
    out += [(G.from_model_poly(e.polygon), 25.0 if e.kind == "sea_channel" else 12.0)
            for e in m.channels]
    out += [(G.from_model_poly(e.polygon), 4.0) for e in m.waterways if not e.ornamental]
    return out


def _raised_roads(m: CityModel) -> tuple:
    decks = raised_roads(m)
    return decks, (shapely.STRtree([d[0] for d in decks]) if decks else None)


def check_altitude(spec: CitySpec, m: CityModel) -> Check:
    c = _check("transit_altitude", "Track altitude within the mode's range (scope 5.3), "
                                   "higher only where it climbs, at the mode's grade, to "
                                   "clear navigable water or a road deck")
    wet = _water(m)
    decks, dtree = _raised_roads(m)
    for t in m.transit_lines:
        if t.mode == "metro":
            continue
        lo, hi = presets.TRANSIT_MODES[t.mode].altitude_m
        # ramps down from what the track must clear, a little gentler than the mode's grade
        g = 0.9 * (presets.TRANSIT_MODES[t.mode].max_grade or 0.05)
        pts, zs = _track(t)
        arr = shapely.points(np.array(pts, dtype=np.float64))
        cap = [hi] * len(pts)
        for poly, clr in wet:
            for i in np.nonzero(shapely.covers(poly, arr))[0].tolist():
                cap[i] = max(cap[i], clr + below(t.mode) + 1.0)
        for i, rz in deck_heights(decks, dtree, arr, WIDTH_M[t.mode] / 2.0):
            cap[i] = max(cap[i], rz + ROAD_CLEAR_M + below(t.mode))
        for k in range(1, len(pts)):
            cap[k] = max(cap[k], cap[k - 1] - g * math.dist(pts[k - 1], pts[k]))
        for k in range(len(pts) - 2, -1, -1):
            cap[k] = max(cap[k], cap[k + 1] - g * math.dist(pts[k], pts[k + 1]))
        for k, z in enumerate(zs):
            if z < lo - 0.01 or z > cap[k] + 0.05:
                _limit(c, f"{t.name} ({t.mode}): z {z:g} m at {pts[k]} outside {lo:g} to "
                          f"{cap[k]:.1f} m")
                break
    return c


def check_clearance(m: CityModel) -> Check:
    c = _check("transit_clearance", "Elevated lines clear the buildings under them (deck "
                                    "underside 2 m over the roof), navigable water (its "
                                    "clearance) and road decks (5.5 m over, or 1 m under a "
                                    "high one); sky lines clear buildings by 10 m or pass "
                                    "through a declared portal")
    portal = {}
    for b in m.buildings:
        for p in b.portals:
            portal.setdefault((b.id, p.line_id), []).append((p.z0_m, p.z1_m))
    polys, blds = [], []
    for b in m.buildings:
        ps = [G.from_model_poly(ms.footprint) for ms in b.masses
              if ms.role != "void" and ms.z1_m > ms.z0_m]
        if ps:
            polys.append(G.union(ps))
            blds.append(b)
    btree = shapely.STRtree(polys) if polys else None
    wet = _water(m)
    decks, dtree = _raised_roads(m)
    for t in m.transit_lines:
        if t.mode == "metro":
            continue
        pts, zs = _track(t)
        deck = below(t.mode)
        r = DECK_M[t.mode] / 2.0
        half = WIDTH_M[t.mode] / 2.0 + SIDE_PAD_M
        arr = shapely.points(np.array(pts, dtype=np.float64))
        bad = set()
        if btree is not None:
            ip, ib = btree.query(arr, predicate="dwithin", distance=half)
            for i, b_ in zip(ip.tolist(), ib.tolist()):
                b = blds[b_]
                z = zs[i]
                bottom = min(ms.z0_m for ms in b.masses if ms.z1_m > ms.z0_m)
                if bottom >= z + 6.0:
                    continue
                clear = SKY_CLEAR_M if t.mode == "sky_tube" else deck + 2.0
                if b.height_m <= z - clear + 0.01:
                    continue
                if any(z0 - 0.01 <= z - r and z + r <= z1 + 0.01
                       for z0, z1 in portal.get((b.id, t.id), ())):
                    continue
                if b.id not in bad:
                    bad.add(b.id)
                    _limit(c, f"{t.name}: {b.id} ({b.height_m:g} m) under the track at "
                              f"{z:g} m")
        for poly, clr in wet:
            inside = np.nonzero(shapely.covers(poly, arr))[0].tolist()
            for i in inside:
                if zs[i] - deck < clr - 0.01:
                    _limit(c, f"{t.name}: {zs[i] - deck:.1f} m over water needing {clr:g} m")
                    break
        for i, rz in deck_heights(decks, dtree, arr, WIDTH_M[t.mode] / 2.0):
            under = zs[i] + above(t.mode) <= road_underside(rz) - UNDER_PAD_M + 0.01
            if zs[i] - deck < rz + ROAD_CLEAR_M - 0.01 and not under:
                _limit(c, f"{t.name}: {zs[i] - deck:.1f} m over a road deck at {rz:.1f} m")
                break
    return c


def check_supports(m: CityModel) -> Check:
    c = _check("transit_supports", "Columns and pylons stand outside lanes, buildings, water "
                                   "and road decks, and leave 1.8 m of every sidewalk clear "
                                   "(in medians, just inside the curbs or off the street)")
    lanes = [(LineString([p[:2] for p in x.centerline]), x.width_m) for x in m.lanes]
    ltree = shapely.STRtree([x[0] for x in lanes]) if lanes else None
    sw = sidewalk_index(m)
    polys = [G.from_model_poly(b.footprint) for b in m.buildings if b.footprint is not None]
    btree = shapely.STRtree(polys) if polys else None
    wet = [poly for poly, _ in _water(m)]
    decks, dtree = _raised_roads(m)
    n = 0
    for s in m.structures:
        if s.kind not in ("column", "pylon") or not s.attrs.get("line_id") or \
                s.footprint is None:
            continue
        n += 1
        poly = G.from_model_poly(s.footprint)
        pt = poly.centroid
        size = math.sqrt(G.area(poly))
        if ltree is not None:
            for i in ltree.query(pt, predicate="dwithin", distance=4.0 + size).tolist():
                if lanes[i][0].distance(pt) < lanes[i][1] / 2 + size / 2 - 0.01:
                    _limit(c, f"{s.id}: in a lane")
                    break
        if not sidewalks_clear(sw, pt, size - 0.02):
            _limit(c, f"{s.id}: on a sidewalk clear path")
        if btree is not None and len(btree.query(poly, predicate="intersects")):
            _limit(c, f"{s.id}: inside a building")
        if any(w.intersects(poly) for w in wet):
            _limit(c, f"{s.id}: in the water")
        if dtree is not None and any(decks[i][0].distance(pt) < decks[i][1] + size / 2 - 0.01
                                     for i in dtree.query(pt, predicate="dwithin",
                                                          distance=40.0).tolist()):
            _limit(c, f"{s.id}: on a road deck")
    c.notes.append(f"{n} columns and pylons")
    return c


def check_station_access(m: CityModel) -> Check:
    from .street_checks import walk_components

    c = _check("station_access", "Every station has stairs, escalators or an elevator to the "
                                 "street and joins the walkway graph (elevated and sky "
                                 "stations next to a sidewalk or plaza)")
    roots = walk_components(m)
    walks = {w.id: w for w in m.walkways}
    ground_roots = set()
    from .buildout import GROUND_WALKS
    for w in m.walkways:
        if w.kind in GROUND_WALKS and all(abs(p[2]) < 1e-9 for p in w.line):
            ground_roots.add(roots.get((w.line[0][0], w.line[0][1])))
    for s in m.stations:
        acc = [walks[i] for i in s.access_ids if i in walks]
        vertical = [w for w in acc if w.kind in ("stairs", "escalator", "elevator")]
        if not vertical:
            _limit(c, f"{s.id} '{s.name}': no stairs or elevator")
            continue
        joined = any(roots.get((p[0], p[1])) in ground_roots for w in acc for p in
                     (w.line[0], w.line[-1]))
        if not joined:
            _limit(c, f"{s.id} '{s.name}': not joined to the street walkways")
    return c


def check_skybridges(m: CityModel) -> Check:
    c = _check("transit_skybridges", "No skybridge in the way of an elevated or sky line "
                                     "(within its corridor and 3 m of its height)")
    for t in m.transit_lines:
        if t.mode == "metro":
            continue
        pts, zs = _track(t)
        track = LineString(pts)
        half = WIDTH_M[t.mode] / 2.0 + SIDE_PAD_M
        for sb in m.skybridges:
            line = LineString(sb.line)
            if line.distance(track) > half + sb.width_m / 2:
                continue
            p = shapely.ops.nearest_points(track, line)[0]
            k = min(range(len(pts)), key=lambda i: (math.dist(pts[i], (p.x, p.y)), i))
            z = zs[k]
            top = sb.z_m + sb.levels * sb.level_height_m
            if top >= z - below(t.mode) - 3.0 and sb.z_m - 1.0 <= z + above(t.mode) + 3.0:
                _limit(c, f"{t.name}: skybridge {sb.id} at {sb.z_m:g} m crosses the track at "
                          f"{z:g} m")
    return c


def check_hubs(spec: CitySpec, m: CityModel) -> Check:
    c = _check("transit_hubs", "Every hub is served by its lines, and every megasite that "
                               "needs transit has a station of one of its modes within "
                               f"{SERVE_M:g} m")
    st = {s.id: s for s in m.stations}
    mode_of = {t.id: t.mode for t in m.transit_lines}
    for hub in spec.transit.hubs or []:
        n = sum(1 for t in m.transit_lines if hub in t.attrs.get("stops", []))
        if spec.transit.lines and n == 0:
            _limit(c, f"hub '{hub}': no line")
    if not m.transit_lines:
        return c
    for s in m.megasites:
        need = presets.MEGASITES[s.kind].needs_transit if s.kind in presets.MEGASITES else ()
        if not need:
            continue
        spec_modes = {tl.mode for tl in spec.transit.lines}
        if not set(need) & spec_modes:
            c.notes.append(f"{s.name}: no {' or '.join(need)} line in the spec")
            continue
        zone = G.from_model_poly(s.polygon).buffer(SERVE_M)
        ok = any(mode_of.get(x.line_ids[0]) in need and
                 zone.covers(Point(x.position[0], x.position[1])) for x in st.values())
        if not ok:
            c.notes.append(f"{s.name} ({s.kind}): no {' or '.join(need)} station within "
                           f"{SERVE_M:g} m")
    return c


def run(spec: CitySpec, m: CityModel) -> list:
    import shapely.ops  # noqa: F401

    if not spec.transit.lines:
        return []
    with G.canonical():
        return [check_routes(spec, m), check_stops(spec, m), check_curves(m),
                check_grades(m), check_altitude(spec, m), check_clearance(m),
                check_supports(m), check_station_access(m), check_skybridges(m),
                check_hubs(spec, m)]


def stats(m: CityModel) -> dict:
    by_mode: dict = {}
    for t in m.transit_lines:
        r = by_mode.setdefault(t.mode, {"lines": 0, "km": 0.0, "stations": 0})
        r["lines"] += 1
        r["km"] = round(r["km"] + t.attrs.get("length_m", 0.0) / 1000.0, 2)
        r["stations"] += len(t.station_ids)
    kinds: dict = {}
    for s in m.stations:
        kinds[s.kind] = kinds.get(s.kind, 0) + 1
    sup = sum(1 for s in m.structures if s.kind in ("column", "pylon") and
              s.attrs.get("line_id"))
    return {"by_mode": dict(sorted(by_mode.items())), "stations": dict(sorted(kinds.items())),
            "supports": sup,
            "portals": sum(len(b.portals) for b in m.buildings),
            "buildings_removed": len({b for t in m.transit_lines
                                      for b in t.attrs.get("removed_buildings", [])}),
            "km": round(sum(t.attrs.get("length_m", 0.0) for t in m.transit_lines) / 1000.0,
                        2)}
