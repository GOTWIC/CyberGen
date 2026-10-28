"""M9 checks: tunnel grades, cover, portals and clashes (scope, After v1)."""

from __future__ import annotations

import math

import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from . import tunnels as TN
from .checks import Check
from .model import CityModel

LIMIT = 12
STEP_M = 5.0
PIECE_M = 10.0
Z_GAP_M = 1.0                   # between a tunnel and what it passes (in height)
GRADE_TOL = 1e-4
ROAD_KINDS = ("immersed_tube", "cut_and_cover")


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < LIMIT:
        c.failures.append(msg)
    elif len(c.failures) == LIMIT:
        c.failures.append("... more")


def _cum(pts) -> list[float]:
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2))
    return out


def _samples(line3, step: float = STEP_M) -> list[tuple[float, float, float, float]]:
    """(s, x, y, z) every `step` m along a 3D line (and at its vertices)."""
    pts = [(p[0], p[1]) for p in line3]
    cum = _cum(pts)
    out = []
    for i in range(len(pts) - 1):
        L = cum[i + 1] - cum[i]
        n = max(int(L / step), 1)
        for k in range(n):
            f = k / n
            out.append((cum[i] + f * L, pts[i][0] + f * (pts[i + 1][0] - pts[i][0]),
                        pts[i][1] + f * (pts[i + 1][1] - pts[i][1]),
                        line3[i][2] + f * (line3[i + 1][2] - line3[i][2])))
    out.append((cum[-1], pts[-1][0], pts[-1][1], line3[-1][2]))
    return out


def _wet(m: CityModel) -> list[tuple]:
    return TN.water_bodies(m)


def check_grades(m: CityModel) -> Check:
    c = Check("tunnel_grades", f"Tunnel grades within the class maximum: roads "
                               f"{TN.MAX_GRADE:.0%} (immersed tubes, cut-and-cover tunnels and "
                               f"their open approaches), metro {TN.METRO_MAX_GRADE:.0%}, "
                               "pedestrian underpasses level")
    from . import terrain as TE

    for t in m.tunnels:
        g = {"metro": TN.METRO_MAX_GRADE, "pedestrian": 0.0}.get(t.kind, TN.MAX_GRADE)
        pts = [(p[0], p[1]) for p in t.line]
        cum = _cum(pts)
        gz = TE.on_ground(m, pts) if t.kind == "metro" else [0.0] * len(pts)
        for k in range(len(pts) - 1):
            L = cum[k + 1] - cum[k]
            if L < 0.5:
                continue
            dz = abs(t.line[k + 1][2] + gz[k + 1] - t.line[k][2] - gz[k])
            if (dz - 0.01) / L > g + GRADE_TOL:
                _limit(c, f"{t.id} ({t.kind}): {dz / L:.1%} at s {cum[k]:.0f} m")
                break
    for ln in m.transit_lines:
        if ln.mode != "metro":
            continue
        pts = [(p[0], p[1]) for p in ln.path]
        cum = _cum(pts)
        za = [p[2] + g for p, g in zip(ln.path, TE.on_ground(m, pts))]
        for k in range(len(pts) - 1):
            L = cum[k + 1] - cum[k]
            if L > 0.5 and (abs(za[k + 1] - za[k]) - 0.01) / L > TN.METRO_MAX_GRADE + GRADE_TOL:
                _limit(c, f"{ln.name} (metro): {abs(za[k + 1] - za[k]) / L:.1%} at "
                          f"s {cum[k]:.0f} m")
                break
    return c


def check_cover(m: CityModel) -> Check:
    c = Check("tunnel_cover", f"Cover over every tunnel roof: at least {TN.COVER_M:g} m of "
                              f"ground ({TN.PORTAL_ZONE_M:g} m into the tunnel from a portal: "
                              "the roof under the ground), "
                              f"{TN.BED_COVER_M:g} m under the water bed (canal "
                              f"{TN.BED_M['canal']:g}, river {TN.BED_M['river']:g}, sea "
                              f"{TN.BED_M['sea']:g} m deep), 0.5 m under a road over a "
                              "pedestrian underpass")
    water = _wet(m)
    polys = [w[0] for w in water]
    tree = shapely.STRtree(polys) if polys else None
    for t in m.tunnels:
        top = t.clear_m + t.roof_m
        portals = [(p.position[0], p.position[1]) for p in t.portals]
        pts = [(p[0], p[1]) for p in t.line]
        cum = _cum(pts)
        from .elevated import _project

        sp = sorted(_project(pts, cum, p)[0] for p in portals)
        lo, hi = (sp[0], sp[-1]) if sp else (0.0, cum[-1])
        smp = _samples(t.line)
        arr = shapely.points([(x, y) for _, x, y, _ in smp])
        bed = [None] * len(smp)
        if tree is not None:
            ip, ig = tree.query(arr, predicate="intersects")
            for i, j in zip(ip.tolist(), ig.tolist()):
                d = TN.BED_M[water[j][1]]
                bed[i] = d if bed[i] is None else max(bed[i], d)
        need_ground = 0.5 if t.kind == "pedestrian" else TN.COVER_M
        bad = None
        for i, (s, x, y, z) in enumerate(smp):
            roof = z + top
            if t.kind in ROAD_KINDS and not lo - 0.01 <= s <= hi + 0.01:
                continue       # the open approach
            if bed[i] is not None:
                cov = -bed[i] - roof
                if cov < TN.BED_COVER_M - 0.05:
                    bad = f"{t.id} ({t.kind}): {cov:.2f} m under the water bed at ({x:.0f}, " \
                          f"{y:.0f})"
                    break
                continue
            zone = t.kind in ROAD_KINDS and min(s - lo, hi - s) < TN.PORTAL_ZONE_M
            cov = -roof
            if cov < (0.0 if zone else need_ground) - 0.05:
                bad = f"{t.id} ({t.kind}): {cov:.2f} m of cover at ({x:.0f}, {y:.0f})"
                break
        if bad:
            _limit(c, bad)
    return c


def check_portals(m: CityModel) -> Check:
    c = Check("tunnel_portals", f"Every road tunnel has a portal at each end on dry land, "
                                f"{TN.CLEAR_M:g} m clear inside, an open approach at most "
                                f"{TN.MAX_GRADE:.0%} steep, and nothing on or over its open "
                                f"approaches: no road node within {TN.FLAT_M:g} m of their "
                                "top, no other road, building or structure on them")
    water = G.union([w[0] for w in _wet(m)]) if m.seas or m.rivers or m.channels or \
        m.waterways else None
    nodes = [(n.position[0], n.position[1]) for n in m.road_nodes]
    ntree = shapely.STRtree(shapely.points(nodes)) if nodes else None
    others = [(LineString(s.centerline).buffer(s.width_m / 2.0, cap_style="flat"), s.id)
              for s in m.road_segments]
    segs = {s.id: s for s in m.road_segments}
    otree = shapely.STRtree([o[0] for o in others]) if others else None
    things = [(G.from_model_poly(b.footprint), b.id) for b in m.buildings
              if b.footprint is not None]
    things += [(G.from_model_poly(s.footprint), s.id) for s in m.structures
               if s.footprint is not None and s.z1_m > 0.0]
    ttree = shapely.STRtree([t[0] for t in things]) if things else None
    for t in m.tunnels:
        if t.kind not in ROAD_KINDS:
            continue
        if len(t.portals) != 2:
            _limit(c, f"{t.id}: {len(t.portals)} portals")
            continue
        if t.clear_m < TN.CLEAR_M - 1e-6:
            _limit(c, f"{t.id}: {t.clear_m:g} m clear")
        pts = [(p[0], p[1]) for p in t.line]
        cum = _cum(pts)
        from .elevated import _project, _sub

        mine = set(t.segment_ids)
        for p in t.portals:
            if water is not None and water.buffer(-1.0).contains(Point(p.position[:2])):
                _limit(c, f"{t.id}: a portal in the water at ({p.position[0]:.0f}, "
                          f"{p.position[1]:.0f})")
            if p.open_m <= 0 or -p.position[2] / p.open_m > TN.MAX_GRADE + GRADE_TOL:
                _limit(c, f"{t.id}: open approach {p.open_m:g} m for a portal "
                          f"{-p.position[2]:g} m down")
        sp = sorted(_project(pts, cum, p.position[:2])[0] for p in t.portals)
        for a, b, top in ((0.0, sp[0], pts[0]), (sp[-1], cum[-1], pts[-1])):
            if b - a < 0.5:
                continue
            strip = LineString(_sub(pts, cum, a, b)).buffer(t.width_m / 2.0, cap_style="flat")
            if ntree is not None:
                near = [int(i) for i in ntree.query(Point(top), predicate="dwithin",
                                                    distance=TN.FLAT_M - 1.0)]
                near += [int(i) for i in ntree.query(strip.buffer(-1.0),
                                                     predicate="intersects")]
                if near:
                    n = m.road_nodes[min(near)]
                    _limit(c, f"{t.id}: road node {n.id} on or by its open approach")
            if otree is not None:
                for i in sorted(int(x) for x in otree.query(strip.buffer(-1.0),
                                                            predicate="intersects")):
                    if others[i][1] in mine:
                        continue
                    # a deck high over the open trench is no obstacle
                    o = segs[others[i][1]]
                    ol = LineString(o.centerline)
                    hit = ol.intersection(strip.buffer(-1.0))
                    from .elevated import _z_at

                    prof = [(z.s, z.z) for z in o.z_profile]
                    pts_ = [ol.project(Point(q)) for q in
                            (hit.coords if hasattr(hit, "coords") else
                             [c_ for g in getattr(hit, "geoms", []) for c_ in g.coords])]
                    low = min((_z_at(prof, x) for x in pts_), default=0.0)
                    if low < 1.0 + TN.CLEAR_M + 1.8:
                        _limit(c, f"{t.id}: road {o.id} ({o.attrs.get('role')}, {low:.1f} m) "
                                  "over its open approach")
                        break
            if ttree is not None:
                for i in sorted(int(x) for x in ttree.query(strip.buffer(-1.0),
                                                            predicate="intersects")):
                    sid = things[i][1]
                    if not sid.startswith(f"{t.id}."):
                        _limit(c, f"{t.id}: {sid} on its open approach")
                        break
            if water is not None and strip.buffer(-1.0).intersects(water):
                _limit(c, f"{t.id}: its open approach reaches the water")
    return c


def _pieces(t) -> list[tuple]:
    """(plan polygon, z bottom, z top, s) of a tunnel in pieces about 10 m long."""
    pts = [(p[0], p[1]) for p in t.line]
    cum = _cum(pts)
    L = cum[-1]
    n = max(int(L / PIECE_M), 1)
    prof = [(s, p[2]) for s, p in zip(cum, t.line)]
    from .elevated import _sub, _z_at

    out = []
    for k in range(n):
        a, b = L * k / n, L * (k + 1) / n
        seg = _sub(pts, cum, a, b)
        if len(seg) < 2:
            continue
        zs = [_z_at(prof, a), _z_at(prof, b), _z_at(prof, (a + b) / 2.0)]
        poly = LineString(seg).buffer(t.width_m / 2.0, cap_style="flat")
        out.append((poly, min(zs) - t.floor_m, max(zs) + t.clear_m + t.roof_m, a))
    return out


def check_clashes(m: CityModel) -> Check:
    c = Check("tunnel_clash", f"No tunnel within {Z_GAP_M:g} m (in height, where they overlap "
                              "in plan) of another tunnel, a metro station box, a building's "
                              "foundations and basements (4 to 18 m deep by height) or a column "
                              "footing")
    solids = []          # (polygon, z0, z1, what, owner tunnel or line)
    for b in m.buildings:
        if b.footprint is not None:
            solids.append((G.from_model_poly(b.footprint), -TN.foundation_m(b.height_m), 0.0,
                           f"building {b.id}", None))
    for st in m.stations:
        if st.kind == "underground" and st.footprint is not None:
            z = st.attrs.get("track_z_m", -16.0)
            solids.append((G.from_model_poly(st.footprint), z - TN.FLOOR_M, -4.0,
                           f"station {st.id}", tuple(st.line_ids)))
    for s in m.structures:
        if s.kind in ("column", "pylon") and s.footprint is not None:
            solids.append((G.from_model_poly(s.footprint), -3.0, 0.0, f"column {s.id}", None))
    pieces = []
    for t in m.tunnels:
        for poly, z0, z1, s in _pieces(t):
            pieces.append((poly, z0, z1, t, s))
    if solids:
        tree = shapely.STRtree([x[0] for x in solids])
        for poly, z0, z1, t, s in pieces:
            for i in sorted(int(x) for x in tree.query(poly.buffer(-0.05),
                                                       predicate="intersects")):
                sp, a0, a1, what, owner = solids[i]
                if owner and t.line_id in owner:
                    continue
                if z0 < a1 + Z_GAP_M - 1e-6 and a0 < z1 + Z_GAP_M - 1e-6:
                    _limit(c, f"{t.id} ({t.kind}) at {s:.0f} m: {what} "
                              f"({a0:g} to {a1:g} m, the tunnel {z0:.1f} to {z1:.1f} m)")
                    break
    if len(pieces) > 1:
        tree = shapely.STRtree([p[0] for p in pieces])
        seen = set()
        for i, (poly, z0, z1, t, s) in enumerate(pieces):
            for j in sorted(int(x) for x in tree.query(poly.buffer(-0.05),
                                                       predicate="intersects")):
                if j <= i:
                    continue
                q, b0, b1, u, s2 = pieces[j]
                if u.id == t.id or (t.id, u.id) in seen:
                    continue
                if t.kind == "metro" and u.kind == "metro" and t.line_id == u.line_id:
                    continue
                if z0 < b1 + Z_GAP_M - 1e-6 and b0 < z1 + Z_GAP_M - 1e-6:
                    seen.add((t.id, u.id))
                    _limit(c, f"{t.id} ({t.kind}) and {u.id} ({u.kind}) at "
                              f"({poly.centroid.x:.0f}, {poly.centroid.y:.0f})")
    return c


def run(spec, m: CityModel) -> list[Check]:
    if any(t.kind == "bored" for t in m.tunnels):   # M13's bored tunnels: terrain checks
        m = m.model_copy(update={"tunnels": [t for t in m.tunnels if t.kind != "bored"]})
    with G.canonical():
        return [check_grades(m), check_cover(m), check_portals(m), check_clashes(m)]


def stats(m: CityModel) -> dict:
    by: dict = {}
    for t in m.tunnels:
        r = by.setdefault(t.kind, {"count": 0, "km": 0.0})
        r["count"] += 1
        r["km"] = round(r["km"] + t.attrs.get("length_m", 0.0) / 1000.0, 2)
    vents = sum(1 for s in m.structures if s.kind == "vent")
    deep = min((t.attrs.get("deepest_m", 0.0) for t in m.tunnels if t.kind in ROAD_KINDS),
               default=0.0)
    metro = min((min(p[2] for p in ln.path) for ln in m.transit_lines if ln.mode == "metro"),
                default=None)
    return {"by_kind": dict(sorted(by.items())), "vents": vents, "deepest_road_m": deep,
            "deepest_metro_m": metro,
            "over_tunnel_roads": sum(1 for s in m.road_segments
                                     if s.attrs.get("over_tunnel_at")),
            "over_tunnel_streets": sum(1 for s in m.road_segments
                                       if s.attrs.get("role") == "over_tunnel")}
