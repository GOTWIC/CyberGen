"""M5 checks: transit lines, stations and supports (scope section 9, transit parts)."""

from __future__ import annotations

import math

import numpy as np
import shapely
import shapely.ops
from shapely.geometry import LineString, Point

from . import geom as G
from . import presets
from .checks import Check
from .model import CityModel
from .spec import CitySpec
from .transit import (DECK_CLEAR_M, DECK_M, GROUND_TOP_M, INF, MAIN_SPAN_M, PLATFORM_M,
                      ROAD_CLEAR_M, SELF_GAP_M, SERVE_M, SIDE_PAD_M, SKY_CLEAR_M, WIDTH_M,
                      _cum, _graded, _runs, _xing_z, _z_along, above, below, deck_heights, floor_z,
                      over_deck, pier_reach, radii, raised_roads, resample, road_underside,
                      self_clear_m, self_meets, sidewalk_index, sidewalks_clear)

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
        from . import terrain as TE

        zs = [z + g for z, g in zip(zs, TE.on_ground(m, pts))]   # M13: on the ground
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


def _tracks(m: CityModel) -> dict:
    """Every line off the ground as its track, keyed by id: line, points, heights, arc
    lengths."""
    out = {}
    for t in m.transit_lines:
        if t.mode == "metro" or len(t.path) < 2:
            continue
        pts, zs = _track(t)
        out[t.id] = {"id": t.id, "mode": t.mode, "line": LineString(pts), "pts": pts,
                     "zs": zs, "cum": _cum(pts), "half": WIDTH_M[t.mode] / 2.0, "t": t}
    return out


def _crossing_caps(t, arr, tracks: dict) -> list[tuple[int, float]]:
    """(point index, the lowest z over it) where the track passes over another line: its
    underside DECK_CLEAR_M over the other's top (the generator also counts its platforms)."""
    out = []
    for o in tracks.values():
        if o["id"] == t.id:
            continue
        reach = WIDTH_M[t.mode] / 2.0 + o["half"] + PLATFORM_M[o["mode"]] + SIDE_PAD_M
        for i in np.nonzero(shapely.dwithin(o["line"], arr, reach))[0].tolist():
            zo = _xing_z(o, o["line"].project(arr[i]))[1]
            out.append((i, zo + above(o["mode"]) + DECK_CLEAR_M + below(t.mode)))
    return out


def check_altitude(spec: CitySpec, m: CityModel) -> Check:
    c = _check("transit_altitude", "Track altitude within the mode's range (scope 5.3), "
                                   "higher only where it climbs, at the mode's grade, to "
                                   "clear navigable water, a road deck or another line")
    wet = _water(m)
    decks, dtree = _raised_roads(m)
    tracks = _tracks(m)
    for t in m.transit_lines:
        if t.mode == "metro":
            continue
        lo, hi = presets.TRANSIT_MODES[t.mode].altitude_m
        # ramps down from what the track must clear, a little gentler than the mode's grade
        g = 0.9 * (presets.TRANSIT_MODES[t.mode].max_grade or 0.05)
        pts, zs = _track(t)
        arr = shapely.points(np.array(pts, dtype=np.float64))
        cap = [max(hi, floor_z(t.mode))] * len(pts)
        for poly, clr in wet:
            for i in np.nonzero(shapely.covers(poly, arr))[0].tolist():
                cap[i] = max(cap[i], clr + below(t.mode) + 1.0)
        for i, rz in deck_heights(decks, dtree, arr, WIDTH_M[t.mode] / 2.0):
            cap[i] = max(cap[i], over_deck(t.mode, rz))
        for i, z in _crossing_caps(t, arr, tracks):
            cap[i] = max(cap[i], z)
        # (around a loop both ways: a climb near its seam ramps down past it)
        cap = _graded(pts, cap, g, max, -1.0, t.loop and len(pts) > 2 and pts[0] == pts[-1])
        for k, z in enumerate(zs):
            if z < lo - 0.01 or z > cap[k] + 0.05:
                _limit(c, f"{t.name} ({t.mode}): z {z:g} m at {pts[k]} outside {lo:g} to "
                          f"{cap[k]:.1f} m")
                break
    return c


def check_self_crossing(m: CityModel) -> Check:
    c = _check("transit_self_crossing",
               f"A line never meets itself at the same level: two parts of its track more than "
               f"{SELF_GAP_M:g} m apart along it stay its structure width apart in plan, or "
               f"one passes {DECK_CLEAR_M:g} m over the other's structure; a loop closes where "
               f"it starts, and its stations come in route order")
    for t in m.transit_lines:
        pts, zs = _track(t)
        if t.loop and (len(pts) < 3 or pts[0] != pts[-1]):
            _limit(c, f"{t.name}: the loop does not close")
        for s, x, y in self_meets(pts, t.loop, WIDTH_M[t.mode], zs, self_clear_m(t.mode)):
            _limit(c, f"{t.name} ({t.mode}): meets itself at ({x:g}, {y:g}), {s:g} m along")
        at = t.attrs.get("stop_vertices", [])
        if any(b < a for a, b in zip(at, at[1:])):
            _limit(c, f"{t.name}: stations out of route order (stop vertices {at})")
    return c


def _station_lines(m: CityModel) -> dict:
    return {s.id: set(s.line_ids) for s in m.stations}


def _owner(s, st_lines: dict) -> set:
    """The lines a transit structure belongs to (its own, or its station's)."""
    a = s.attrs or {}
    if a.get("line_id"):
        return {a["line_id"]}
    return set(st_lines.get(a.get("station"), ()))


def _ground_roads(m: CityModel):
    """The roads and sidewalks at the ground: (corridors, STRtree)."""
    polys = []
    for s in m.road_segments:
        if s.bridge or any(z.z > 0.5 for z in s.z_profile):
            continue
        w = max(s.width_m, s.cross_section.total_width_m)
        polys.append(LineString(s.centerline).buffer(w / 2.0, cap_style="flat"))
    return polys, (shapely.STRtree(polys) if polys else None)


def check_clearance(m: CityModel) -> Check:
    c = _check("transit_clearance",
               f"Every transit structure clears what is around it (M19), in 3D along the "
               f"whole line: buildings and their roof items {SIDE_PAD_M:g} m away in plan, or "
               f"under it by 2 m (an elevated deck's underside) or {SKY_CLEAR_M:g} m (a sky "
               f"tube's axis); a sky "
               f"tube passes through a tower only at a sky station inside it; other lines' "
               f"structures, platforms and canopies {SIDE_PAD_M:g} m away in plan or "
               f"{DECK_CLEAR_M:g} m apart in height; {ROAD_CLEAR_M:g} m over a road or "
               f"sidewalk, {DECK_CLEAR_M:g} m over (or under) a raised road's deck; navigable "
               f"water's clearance")
    portal = {}
    for b in m.buildings:
        for p in b.portals:
            portal.setdefault((b.id, p.line_id), []).append((p.z0_m, p.z1_m))
    hosted = {(s.building_id, lid) for s in m.stations if s.building_id for lid in s.line_ids}
    for (bid, lid) in sorted(portal):
        if (bid, lid) not in hosted:
            _limit(c, f"{lid}: passes through {bid} without a sky station in it")
    masses = []
    for b in m.buildings:
        for ms in b.masses:
            if ms.role != "void" and ms.z1_m > ms.z0_m:
                masses.append((b, G.from_model_poly(ms.footprint), ms.z0_m, ms.z1_m))
        for it in b.roof_items:
            r = math.hypot(it.size[0], it.size[1]) / 2.0
            masses.append((b, Point(it.position[0], it.position[1]).buffer(r, 8),
                           it.position[2], it.position[2] + it.size[2]))
    mtree = shapely.STRtree([x[1] for x in masses]) if masses else None
    wet = _water(m)
    decks, dtree = _raised_roads(m)
    roads, rtree = _ground_roads(m)
    tracks = _tracks(m)
    st_lines = _station_lines(m)
    # other structures of the lines and stations: (geometry, z0, z1, lines it belongs to)
    xs = []
    for s in m.structures:
        own = _owner(s, st_lines)
        if not own or s.z1_m <= 0.0 or s.kind in ("deck", "tube") and \
                not (s.attrs or {}).get("station"):
            continue
        if s.footprint is not None:
            g = G.from_model_poly(s.footprint)
        elif len(s.line) >= 2:
            g = LineString([p[:2] for p in s.line]).buffer(
                (s.attrs or {}).get("width_m", 2.0) / 2.0, cap_style="flat")
        else:
            continue
        xs.append((g, s.z0_m, s.z1_m, own, s.id))
    xtree = shapely.STRtree([x[0] for x in xs]) if xs else None
    for t in m.transit_lines:
        if t.mode == "metro":
            continue
        pts, zs = _track(t)
        deck = below(t.mode)
        r = DECK_M[t.mode] / 2.0
        half = WIDTH_M[t.mode] / 2.0
        arr = shapely.points(np.array(pts, dtype=np.float64))
        if mtree is not None:
            bad = set()
            ip, ib = mtree.query(arr, predicate="dwithin", distance=half + SIDE_PAD_M)
            for i, k in zip(ip.tolist(), ib.tolist()):
                b, _, z0, z1 = masses[k]
                z = zs[i]
                # (a sky tube's axis 10 m over the roof, an elevated deck's underside 2 m)
                if (z1 + SKY_CLEAR_M <= z + 0.01 if t.mode == "sky_tube" else
                        z1 + 2.0 <= z - deck + 0.01) or z0 >= z + 6.0:
                    continue
                if any(p0 - 0.01 <= z - r and z + r <= p1 + 0.01
                       for p0, p1 in portal.get((b.id, t.id), ())):
                    continue
                if b.id not in bad:
                    bad.add(b.id)
                    _limit(c, f"{t.name}: {b.id} ({z1:g} m) within {SIDE_PAD_M:g} m of the "
                              f"track at {z:g} m, ({pts[i][0]:g}, {pts[i][1]:g})")
        for poly, clr in wet:
            inside = np.nonzero(shapely.covers(poly, arr))[0].tolist()
            for i in inside:
                if zs[i] - deck < clr - 0.01:
                    _limit(c, f"{t.name}: {zs[i] - deck:.1f} m over water needing {clr:g} m")
                    break
        for i, rz in deck_heights(decks, dtree, arr, half):
            under = zs[i] + above(t.mode) + DECK_CLEAR_M <= road_underside(rz) + 0.01
            if zs[i] - deck < rz + DECK_CLEAR_M - 0.01 and not under:
                _limit(c, f"{t.name}: {zs[i] - deck:.1f} m over a road deck at {rz:.1f} m")
                break
        if rtree is not None:
            for i in sorted(set(rtree.query(arr, predicate="intersects")[0].tolist())):
                if zs[i] - deck < ROAD_CLEAR_M - 0.01:
                    _limit(c, f"{t.name}: {zs[i] - deck:.1f} m over a road at "
                              f"({pts[i][0]:g}, {pts[i][1]:g})")
                    break
        # other lines' tracks
        for o in tracks.values():
            if o["id"] == t.id:
                continue
            idx = np.nonzero(shapely.dwithin(o["line"], arr, half + o["half"] + SIDE_PAD_M)
                             )[0].tolist()
            for i in idx:
                zo = _z_along(o, o["line"].project(arr[i]))
                lo, hi = zs[i] - deck, zs[i] + above(t.mode)
                olo, ohi = zo - below(o["mode"]), zo + above(o["mode"])
                if not (lo >= ohi + DECK_CLEAR_M - 0.01 or hi + DECK_CLEAR_M <= olo + 0.01):
                    _limit(c, f"{t.name}: within {SIDE_PAD_M:g} m of {o['t'].name} at "
                              f"({pts[i][0]:g}, {pts[i][1]:g}), {abs(zs[i] - zo):.1f} m apart "
                              f"in height")
                    break
        # other lines' supports, platforms, beams, canopies, stations
        if xtree is not None:
            seen = set()
            ip, ix = xtree.query(arr, predicate="dwithin", distance=half + SIDE_PAD_M)
            for i, k in sorted(zip(ip.tolist(), ix.tolist())):
                g, z0, z1, own, sid = xs[k]
                if t.id in own or sid in seen:
                    continue
                lo, hi = zs[i] - deck, zs[i] + above(t.mode)
                if lo >= z1 + DECK_CLEAR_M - 0.01 or hi + DECK_CLEAR_M <= z0 + 0.01:
                    continue
                seen.add(sid)
                _limit(c, f"{t.name}: within {SIDE_PAD_M:g} m of {sid} ({z0:g} to {z1:g} m) "
                          f"at ({pts[i][0]:g}, {pts[i][1]:g})")
    # beams over the roads
    if rtree is not None:
        for s in m.structures:
            if s.kind != "beam" or len(s.line) < 2:
                continue
            g = LineString([p[:2] for p in s.line])
            if len(rtree.query(g, predicate="intersects")) and s.z0_m < ROAD_CLEAR_M - 0.01:
                _limit(c, f"{s.id}: {s.z0_m:g} m over a road")
    return c


def _carriers(m: CityModel, t, o: dict) -> list[tuple[float, float]]:
    """What carries a line's track where it has no support: a tower it passes through (at
    one of its sky stations), the ground (its underside within GROUND_TOP_M), a transit
    nexus's platform under it, a sky station's elevator core."""
    arr = shapely.points(np.array(o["pts"], dtype=np.float64))
    cum = o["cum"]
    out = []
    for b in m.buildings:
        if not any(p.line_id == t.id for p in b.portals) or b.footprint is None:
            continue
        polys = [G.from_model_poly(ms.footprint) for ms in b.masses
                 if ms.role != "void" and ms.z1_m > ms.z0_m]
        poly = G.union(polys) if polys else G.from_model_poly(b.footprint)
        for i0, i1 in _runs(np.nonzero(shapely.covers(poly, arr))[0].tolist()):
            out.append((cum[i0], cum[i1]))
    low = [i for i, z in enumerate(o["zs"]) if z - below(t.mode) <= GROUND_TOP_M]
    for i0, i1 in _runs(low):
        out.append((cum[i0], cum[i1]))
    for e in m.site_elements:
        if e.kind != "platform" or e.footprint is None or not e.masses:
            continue
        fp = G.from_model_poly(e.footprint)
        top = max(ms.z1_m for ms in e.masses)
        ins = [i for i in np.nonzero(shapely.covers(fp, arr))[0].tolist()
               if abs(o["zs"][i] - below(t.mode) - top) <= 3.0 or abs(o["zs"][i] - top) <= 3.0]
        for i0, i1 in _runs(ins):
            out.append((cum[i0], cum[i1]))
    sts = set(t.station_ids)
    for s in m.structures:
        a = s.attrs or {}
        if a.get("role") == "elevator_core" and a.get("station") in sts and s.footprint:
            x = o["line"].project(G.from_model_poly(s.footprint).centroid)
            out.append((max(x - 5.0, 0.0), min(x + 5.0, cum[-1])))
    return sorted(out)


def check_supports(m: CityModel) -> Check:
    c = _check("transit_supports",
               "Supports stand under the structure (a column's middle within 0.5 m of the "
               "line, else a portal frame or a cantilever bent whose cap beam carries the deck "
               "where the line crosses it), outside lanes, buildings, road decks and the "
               "sidewalks' clear paths, in the water only as piers clear of the navigable "
               "channel; no span longer than the mode's longest (elevated rail 45 m, monorail "
               "40, maglev 80, sky tube 600), but a main span over a navigable channel or a "
               "raised road, and an end overhanging half of it at most")
    lanes = [(LineString([p[:2] for p in x.centerline]), x.width_m) for x in m.lanes]
    ltree = shapely.STRtree([x[0] for x in lanes]) if lanes else None
    sw = sidewalk_index(m)
    polys = [G.from_model_poly(b.footprint) for b in m.buildings if b.footprint is not None]
    btree = shapely.STRtree(polys) if polys else None
    wet = []
    for e in m.seas:
        wet += [(G.from_model_poly(p), INF) for p in e.polygons]
    for e in m.rivers:
        wet.append((G.from_model_poly(e.polygon), pier_reach(_mid_w(e), "river")))
    for e in m.channels:
        wet.append((G.from_model_poly(e.polygon), pier_reach(_mid_w(e), e.kind)))
    for e in m.waterways:
        poly = G.from_model_poly(e.polygon)
        w = 2.0 * G.area(poly) / poly.length if poly.length > 0 else 0.0
        wet.append((poly, INF if e.ornamental else pier_reach(w, e.kind)))
    shore = _shore(m, [p for p, _ in wet])
    decks, dtree = _raised_roads(m)
    tracks = _tracks(m)
    beams = {s.id: s for s in m.structures if s.kind == "beam"}
    at: dict = {}         # line id -> [support position along it]
    n = frames = piers = 0
    for s in m.structures:
        a = s.attrs or {}
        if s.kind not in ("column", "pylon") or not a.get("line_id") or s.footprint is None:
            continue
        n += 1
        o = tracks.get(a["line_id"])
        poly = G.from_model_poly(s.footprint)
        pt = poly.centroid
        size = math.sqrt(G.area(poly))
        if ltree is not None:
            for i in ltree.query(pt, predicate="dwithin", distance=4.0 + size).tolist():
                if lanes[i][0].distance(pt) < lanes[i][1] / 2 + size / 2 - 0.01:
                    _limit(c, f"{s.id}: in a lane")
                    break
        in_water = [r for w, r in wet if w.intersects(poly)]
        if not in_water and not sidewalks_clear(sw, pt, size - 0.02):
            _limit(c, f"{s.id}: on a sidewalk clear path")
        if btree is not None and len(btree.query(poly, predicate="intersects")):
            _limit(c, f"{s.id}: inside a building")
        if in_water:
            if a.get("form") != "pier" and not a.get("pier"):
                _limit(c, f"{s.id}: in the water, not a pier")
            elif shore is not None and shore.distance(pt) > min(in_water) + 0.01:
                _limit(c, f"{s.id}: a pier in a navigable channel")
        if dtree is not None and any(decks[i][0].distance(pt) < decks[i][1] + size / 2 - 0.01
                                     for i in dtree.query(pt, predicate="dwithin",
                                                          distance=40.0).tolist()):
            _limit(c, f"{s.id}: on a road deck")
        if o is None:
            continue
        if a.get("frame"):
            bm = beams.get(a["frame"])
            if bm is None:
                _limit(c, f"{s.id}: its cap beam {a['frame']} is missing")
                continue
            g = LineString([p[:2] for p in bm.line])
            if min(Point(p[:2]).distance(pt) for p in bm.line) > 0.5:
                _limit(c, f"{s.id}: not under its cap beam's end")
            continue
        piers += a.get("form") == "pier"
        if o["line"].distance(pt) > 0.5:
            _limit(c, f"{s.id}: {o['line'].distance(pt):.1f} m off its line")
        at.setdefault(a["line_id"], []).append(o["line"].project(pt))
    for s in beams.values():
        a = s.attrs or {}
        o = tracks.get(a.get("line_id"))
        if o is None or len(s.line) < 2:
            continue
        frames += 1
        g = LineString([p[:2] for p in s.line])
        x = o["line"].project(Point(s.line[-1][:2])) if a.get("form") == "cantilever" else None
        hit = shapely.intersection(g, o["line"])
        if not hit.is_empty:
            pt = hit.representative_point()
        else:
            pt, _ = shapely.ops.nearest_points(o["line"], g)
            if o["line"].distance(g) > 0.5:
                _limit(c, f"{s.id}: its cap beam does not reach under the line")
                continue
        x = o["line"].project(pt)
        under = _z_along(o, x) - below(o["mode"])
        if abs(s.z1_m - under) > 0.05:
            _limit(c, f"{s.id}: its top {s.z1_m:g} m, the deck's underside {under:.2f} m")
        at.setdefault(a["line_id"], []).append(x)
    for lid, o in sorted(tracks.items()):
        t = o["t"]
        span, longest = presets.TRANSIT_MODES[t.mode].support_spacing_m
        L = o["cum"][-1]
        closed = t.loop and o["pts"][0] == o["pts"][-1]
        car = _carriers(m, t, o)
        marks = sorted(at.get(lid, []) + [x for c0, c1 in car for x in (c0, c1)])
        if not closed:
            marks = [-longest / 2.0] + marks + [L + longest / 2.0]
        pairs = list(zip(marks, marks[1:]))
        if closed and marks:
            pairs.append((marks[-1], marks[0] + L))
        worst = 0.0
        for g0, g1 in pairs:
            if any(c0 - 0.01 <= g0 and g1 <= c1 + 0.01 for c0, c1 in car):
                continue
            G_ = g1 - g0
            worst = max(worst, G_)
            if G_ <= longest + 0.01:
                continue
            if G_ <= MAIN_SPAN_M[t.mode] + 0.01 and _over_channel(o, g0, g1, wet, shore,
                                                                  closed, decks, dtree):
                continue
            _limit(c, f"{t.name} ({t.mode}): {G_:.0f} m without a support from "
                      f"{max(g0, 0.0) % L if closed else max(g0, 0.0):.0f} m along it "
                      f"(longest {longest:g} m)")
        c.notes.append(f"{t.name}: longest span {worst:.0f} m")
    c.notes.insert(0, f"{n} columns and pylons ({piers} piers), {frames} frames and "
                      f"cantilevers")
    return c


def _mid_w(e) -> float:
    return sorted(e.width_m)[len(e.width_m) // 2] if e.width_m else 60.0


def _shore(m: CityModel, polys: list):
    """The water's edge (where it meets land, not the map edge)."""
    if not polys:
        return None
    x0, y0, x1, y1 = m.bounds
    edge = shapely.box(x0, y0, x1, y1).boundary.buffer(1.0)
    bd = G.union(polys).boundary
    segs = []
    for g in getattr(bd, "geoms", [bd]):
        cs = list(g.coords)
        segs += [LineString([a, b]) for a, b in zip(cs, cs[1:])
                 if not edge.covers(LineString([a, b]))]
    return shapely.MultiLineString(segs) if segs else None


def _over_channel(o: dict, g0: float, g1: float, wet: list, shore, closed: bool, decks,
                  dtree) -> bool:
    """Whether the track crosses a navigable channel or a raised road between g0 and g1
    (where a main span may pass the longest)."""
    L = o["cum"][-1]
    x = g0
    while x < g1:
        y = x % L if closed else min(max(x, 0.0), L)
        p = o["line"].interpolate(y)
        reach = [r for w, r in wet if w.covers(p)]
        if shore is not None and reach and shore.distance(p) > min(reach) + 0.01:
            return True
        if dtree is not None and any(decks[i][0].distance(p) <= decks[i][1] + 0.01 for i in
                                     dtree.query(p, predicate="dwithin", distance=40.0)):
            return True
        x += 5.0
    return False


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
                check_self_crossing(m), check_grades(m), check_altitude(spec, m),
                check_clearance(m),
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
    form: dict = {}
    for s in m.structures:
        if s.attrs.get("line_id") and s.kind in ("column", "pylon") and \
                not s.attrs.get("frame"):
            k = s.attrs.get("form", "column")
            form[k] = form.get(k, 0) + 1
        elif s.kind == "beam" and s.attrs.get("line_id"):
            k = s.attrs.get("form", "frame")
            form[k] = form.get(k, 0) + 1
    spans: dict = {}
    for t in m.transit_lines:
        for a, b, k in t.attrs.get("spans", []):
            spans[k] = spans.get(k, 0) + 1
    return {"by_mode": dict(sorted(by_mode.items())), "stations": dict(sorted(kinds.items())),
            "supports": sup, "support_forms": dict(sorted(form.items())),
            "long_spans": dict(sorted(spans.items())),
            "portals": sum(len(b.portals) for b in m.buildings),
            "buildings_removed": len({b for t in m.transit_lines
                                      for b in t.attrs.get("removed_buildings", [])}),
            "km": round(sum(t.attrs.get("length_m", 0.0) for t in m.transit_lines) / 1000.0,
                        2)}
