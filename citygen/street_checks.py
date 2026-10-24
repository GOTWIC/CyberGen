"""Checks and stats for the local network, blocks, lots and open space (M2; scope section 9).

Like `checks.py`, every check reads only the city model and the filled spec.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from . import blocks as BK
from . import dmath as M
from . import geom as G
from . import streets as ST
from .model import CityModel
from .spec import CitySpec

LOT_AREA_TOL = (0.75, 1.6)     # lot area within (min * a, max * b) of the archetype range
BLOCK_SIZE_TOL = (0.5, 1.8)    # median block size within (lo * a, hi * b)
LOT_MIN_W_M = 3.0
BLOCK_MIN_W_M = 6.0
CLEAR_PATH_M = 1.8
ANGLE_TOL_DEG = 2.0
OPEN_SHARE_TOL = 0.02
FRONTAGE_MIN_M = 2.0
ACCESS = ("avenue", "street", "alley", "service", "pedestrian")
PRIMARY = ("highway", "avenue")


class Check:  # same shape as checks.Check (imported lazily there)
    pass


def _check(id_: str, title: str):
    from .checks import Check as C

    return C(id_, title)


class _Net:
    def __init__(self, m: CityModel):
        self.m = m
        self.seg = {s.id: s for s in m.road_segments}
        self.lines = {s.id: LineString(s.centerline) for s in m.road_segments}
        self.pos = {n.id: n.position[:2] for n in m.road_nodes}
        self.at: dict[str, list] = {}
        for s in m.road_segments:
            self.at.setdefault(s.start, []).append((s, True))
            self.at.setdefault(s.end, []).append((s, False))
        self.dist_poly = {d.id: G.from_model_poly(d.polygon) for d in m.districts}
        self.zones = []
        for did in sorted(self.dist_poly):
            z = self.dist_poly[did].buffer(5.0)
            shapely.prepare(z)
            self.zones.append((did, z))
        self.arch = {d.id: d.archetype for d in m.districts}

    def district_at(self, p) -> str | None:
        pt = Point(p)
        for did, z in self.zones:
            if z.contains(pt):
                return did
        return None

    def leg_dir(self, s, at_start: bool):
        pts = list(s.centerline) if at_start else list(s.centerline)[::-1]
        L = ST._plen(pts)
        q, _ = ST._along(pts, min(10.0, L / 2))
        return ST._unit(q[0] - pts[0][0], q[1] - pts[0][1])


def _uf(pairs, items=()):
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for x in items:
        find(x)
    for a, b in pairs:
        parent[find(a)] = find(b)
    return {x: find(x) for x in list(parent)}


def check_street_graph(m: CityModel, n: _Net):
    c = _check("street_graph", "Street graph connected: every vehicle road (highway to alley "
                               "and service lane) in one network, every pedestrian street and "
                               "footbridge joined to it")
    veh = [s for s in m.road_segments if s.road_class in ST.VEHICLE]
    roots = _uf([(s.start, s.end) for s in veh])
    comps: dict = {}
    for s in veh:
        comps.setdefault(roots[s.start], []).append(s.id)
    if len(comps) > 1:
        sizes = sorted((len(v) for v in comps.values()), reverse=True)
        c.failures.append(f"{len(comps)} vehicle road components (segments per component: "
                          f"{', '.join(str(x) for x in sizes[:8])})")
    allr = _uf([(s.start, s.end) for s in m.road_segments])
    main = max(comps, key=lambda r: (len(comps[r]), r)) if comps else None
    main_all = allr.get(main) if main else None
    for s in m.road_segments:
        if s.road_class in ST.PEDESTRIAN and allr.get(s.start) != main_all:
            c.failures.append(f"{s.road_class} {s.id} is not joined to the street network")
    return c


def _scc_count(succ: dict[str, list[str]]) -> tuple[int, int]:
    """(number of strongly connected components, size of the largest), iterative Tarjan."""
    index: dict = {}
    low: dict = {}
    on: set = set()
    stack: list = []
    counter = 0
    comps = 0
    largest = 0
    for root in sorted(succ):
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on.add(v)
            nxt = succ.get(v, [])
            if i < len(nxt):
                work.append((v, i + 1))
                w = nxt[i]
                if w not in index:
                    work.append((w, 0))
                elif w in on:
                    low[v] = min(low[v], index[w])
                continue
            for w in nxt:
                if w in on:
                    low[v] = min(low[v], low[w])
            if low[v] == index[v]:
                size = 0
                while True:
                    w = stack.pop()
                    on.discard(w)
                    size += 1
                    if w == v:
                        break
                comps += 1
                largest = max(largest, size)
    return comps, largest


def check_lane_graph(m: CityModel, n: _Net):
    c = _check("lane_graph", "Lane graph strongly connected (every lane reaches every other "
                             "through junction connectors and lane changes) and every vehicle "
                             "road has lanes")
    succ = {ln.id: sorted(set(ln.successors) | set(ln.adjacent_ids)) for ln in m.lanes}
    ids = set(succ)
    for k, v in succ.items():
        bad = [x for x in v if x not in ids]
        if bad:
            c.failures.append(f"lane {k}: unknown successor {bad[0]}")
    if not succ:
        c.failures.append("no lanes")
        return c
    comps, largest = _scc_count(succ)
    if comps > 1:
        c.failures.append(f"{comps} strongly connected components (largest {largest} of "
                          f"{len(succ)} lanes)")
    have = {ln.segment_id for ln in m.lanes if ln.kind == "lane"}
    for s in m.road_segments:
        if s.road_class in ST.VEHICLE and s.id not in have:
            c.failures.append(f"segment {s.id} ({s.road_class}) has no lanes")
    return c


def walk_components(m: CityModel):
    pairs = []
    for w in m.walkways:
        a, b = tuple(w.line[0][:2]), tuple(w.line[-1][:2])
        pairs.append((a, b))
    return _uf(pairs)


def check_walkway_graph(m: CityModel, n: _Net, g):
    c = _check("walkway_graph", "Walkway graph connected on every landmass with districts "
                                "(sidewalks, crossings, crosswalks, pedestrian streets, "
                                "promenades, footbridges, alleys, paths into open space)")
    if not m.walkways:
        c.failures.append("no walkways")
        return c
    roots = walk_components(m)
    pts = sorted(roots)
    arr = shapely.points(np.array(pts, dtype=np.float64))
    for lm in m.landmasses:
        if not lm.district_ids:
            continue
        poly = g.landmasses[lm.id]
        inside = shapely.contains(poly.buffer(-1.0), arr)
        rs = {roots[pts[i]] for i in np.nonzero(inside)[0].tolist()}
        if len(rs) > 1:
            sizes = {}
            for i in np.nonzero(inside)[0].tolist():
                sizes[roots[pts[i]]] = sizes.get(roots[pts[i]], 0) + 1
            big = sorted(sizes.values(), reverse=True)
            c.failures.append(f"landmass {lm.id}: {len(rs)} walkway components (walk nodes "
                              f"{', '.join(str(x) for x in big[:6])})")
        elif not rs:
            c.failures.append(f"landmass {lm.id} has no walkways")
    total = len(set(roots.values()))
    c.notes.append(f"{total} walkway component(s) in the city (landmasses without a "
                   "pedestrian bridge stay apart)")
    return c


def check_lot_frontage(m: CityModel, n: _Net):
    c = _check("lot_frontage", f"Every lot fronts a street, alley, service lane or pedestrian "
                               f"street (at least {FRONTAGE_MIN_M:g} m) and records its "
                               "frontage and district")
    bad = 0
    for lt in m.lots:
        L = math.fsum(f.length_m for f in lt.frontage if f.road_class in ACCESS)
        if L < FRONTAGE_MIN_M or not lt.district_id or not lt.frontage_ids:
            bad += 1
            if bad <= 12:
                c.failures.append(f"lot {lt.id}: {L:.1f} m of frontage")
    if bad > 12:
        c.failures.append(f"... {bad} lots in all")
    return c


def check_sizes(m: CityModel, n: _Net):
    lo_a, hi_a = LOT_AREA_TOL
    c = _check("lot_block_sizes", f"Lot areas within the archetype range ({lo_a:g} x min to "
                                  f"{hi_a:g} x max) and each district's median block size "
                                  "(square root of area) within the archetype block range "
                                  f"({BLOCK_SIZE_TOL[0]:g} x lo to {BLOCK_SIZE_TOL[1]:g} x hi)")
    out = 0
    for lt in m.lots:
        st = ST.style_of(lt.archetype)
        a0, a1 = st.lot_area
        A = G.area1(G.from_model_poly(lt.polygon))
        if not (lo_a * a0 <= A <= hi_a * a1):
            out += 1
            if out <= 12:
                c.failures.append(f"lot {lt.id} ({lt.archetype}): {A:.0f} m2 (range "
                                  f"{a0:g} to {a1:g})")
    if out > 12:
        c.failures.append(f"... {out} lots in all")
    by: dict = {}
    for bk in m.blocks:
        by.setdefault(bk.district_id, []).append(math.sqrt(bk.area_m2))
    spec_blocks = {d.id: d.params.get("block_size_m") for d in m.districts}
    for did, sizes in sorted(by.items()):
        rng_ = spec_blocks.get(did) or (80.0, 140.0)
        med = float(np.median(np.array(sorted(sizes))))
        lo, hi = rng_
        if not (BLOCK_SIZE_TOL[0] * lo <= med <= BLOCK_SIZE_TOL[1] * hi):
            c.failures.append(f"district {did}: median block size {med:.0f} m (range "
                              f"{lo:g} to {hi:g})")
    return c


def check_slivers(m: CityModel, n: _Net):
    c = _check("lot_slivers", f"No lot narrower than {LOT_MIN_W_M:g} m and no block narrower "
                              f"than {BLOCK_MIN_W_M:g} m (strip width from exact area and "
                              "perimeter)")
    for lt in m.lots:
        p = G.from_model_poly(lt.polygon)
        w = BK.width_est(G.area1(p), G.length1(p.exterior))
        if w < LOT_MIN_W_M:
            c.failures.append(f"lot {lt.id}: {w:.1f} m wide")
    for bk in m.blocks:
        p = G.from_model_poly(bk.polygon)
        w = BK.width_est(G.area1(p), G.length1(p.exterior))
        if w < BLOCK_MIN_W_M:
            c.failures.append(f"block {bk.id}: {w:.1f} m wide")
    return c


def check_clear_path(m: CityModel, n: _Net):
    c = _check("sidewalk_clear_path", f"Sidewalk clear path at least {CLEAR_PATH_M:g} m "
                                      "(width minus furniture zone and curb)")
    for sw in m.sidewalks:
        if sw.clear_path_m < CLEAR_PATH_M - 1e-9:
            c.failures.append(f"sidewalk {sw.id} ({sw.segment_id}): clear path "
                              f"{sw.clear_path_m:g} m")
    return c


def check_crosswalks(m: CityModel, n: _Net):
    c = _check("crosswalks", "A crosswalk on every approach of every signalized junction, and on "
                             "the side street approaches of unsignalized junctions on avenues")
    have = {(x.junction_id, x.segment_id) for x in m.crosswalks}
    for j in m.junctions:
        if j.shape == "cul_de_sac":
            continue
        legs = n.at.get(j.node_id, [])
        avenue = any(s.road_class == "avenue" for s, _ in legs)
        for s, _ in legs:
            if s.road_class in ST.PEDESTRIAN:
                continue
            need = j.signalized or (avenue and s.road_class not in PRIMARY)
            if need and (j.id, s.id) not in have:
                c.failures.append(f"junction {j.id} ({'signalized' if j.signalized else 'avenue'}"
                                  f"): no crosswalk across {s.id} ({s.road_class})")
    return c


def _local_junctions(m: CityModel, n: _Net):
    for nid, legs in sorted(n.at.items()):
        if len(legs) >= 3 and any(s.road_class not in PRIMARY for s, _ in legs):
            yield nid, legs


def check_junction_placement(m: CityModel, n: _Net):
    c = _check("junction_placement", "No junction of a local road on a bridge or on a bridge "
                                     "approach ramp (z profile above ground)")
    br = {b.id: b for b in m.bridges}
    for nid, legs in _local_junctions(m, n):
        p = n.pos[nid]
        for s, at_start in legs:
            for bid in s.bridge_ids:
                b = br[bid]
                line = n.lines[s.id]
                bl = LineString([(x, y) for x, y, _ in b.line])
                s0 = line.project(Point(bl.coords[0]))
                s1 = line.project(Point(bl.coords[-1]))
                lo, hi = min(s0, s1), max(s0, s1)
                ramp = b.ramp_length_m or 0.0
                at = 0.0 if at_start else line.length
                gap = (lo - at) if at_start else (at - hi)
                if gap < ramp - 1.0:
                    c.failures.append(f"node {nid} at ({p[0]:.0f}, {p[1]:.0f}) is "
                                      f"{max(gap, 0):.0f} m from bridge {bid} (ramp "
                                      f"{ramp:.0f} m)")
            z0 = s.z_profile[0].z if at_start and s.z_profile else (
                s.z_profile[-1].z if s.z_profile else 0.0)
            if z0 > 0.05:
                c.failures.append(f"node {nid}: segment {s.id} is {z0:g} m above ground there")
    return c


def check_junction_angles(m: CityModel, n: _Net):
    c = _check("junction_angles", f"Minimum angle between roads at a junction of local roads: "
                                  f"{ST.GRID_ANGLE_DEG:g} degrees in grid districts, "
                                  f"{ST.ORGANIC_ANGLE_DEG:g} in organic ones (old town, "
                                  "entertainment market)")
    for nid, legs in _local_junctions(m, n):
        dirs = sorted((M.atan2(d[1], d[0]), s.id) for s, a in legs
                      for d in [n.leg_dir(s, a)])
        angs = [d for d, _ in dirs]
        k = len(angs)
        gaps = [M.degrees((angs[(i + 1) % k] - angs[i]) % (2 * M.PI)) for i in range(k)]
        did = n.district_at(n.pos[nid])
        want = ST.min_angle(n.arch.get(did, "midtown_mixed")) if did else ST.GRID_ANGLE_DEG
        if min(gaps) < want - ANGLE_TOL_DEG:
            p = n.pos[nid]
            c.failures.append(f"node {nid} at ({p[0]:.0f}, {p[1]:.0f}): {min(gaps):.0f} "
                              f"degrees (minimum {want:g})")
    return c


def check_street_duplicates(m: CityModel, n: _Net):
    c = _check("street_duplicates", f"No near-duplicate local roads: right-of-way edges closer "
                                    f"than {ST.DUP_GAP_M:g} m over more than {ST.DUP_LEN_M:g} m "
                                    "(30 m around shared points aside)")
    segs = m.road_segments
    lines = [n.lines[s.id] for s in segs]
    tree = shapely.STRtree(lines)
    for i, s in enumerate(segs):
        a = lines[i]
        for j in sorted(int(x) for x in tree.query(a, predicate="dwithin",
                                                   distance=s.width_m / 2 + 24.0)):
            if j <= i:
                continue
            t = segs[j]
            if s.road_class in PRIMARY and t.road_class in PRIMARY:
                continue  # checked by road_duplicates
            L = max(ST.side_by_side(a, lines[j], s.width_m, t.width_m),
                    ST.side_by_side(lines[j], a, t.width_m, s.width_m))
            if L > ST.DUP_LEN_M:
                c.failures.append(f"segments {s.id} ({s.road_class}) and {t.id} "
                                  f"({t.road_class}) run side by side for {L:.0f} m")
    return c


def open_shares(spec: CitySpec, m: CityModel) -> dict[str, tuple[float, float, float]]:
    """District id -> (open share, open m2, lot m2): open space (M2, plus central park and grand
    plaza reserves) over open space plus lots."""
    lot_a: dict = {}
    for lt in m.lots:
        lot_a[lt.district_id] = lot_a.get(lt.district_id, 0.0) + lt.area_m2
    open_a: dict = {}
    for o in m.open_spaces:
        if o.district_id:
            open_a[o.district_id] = open_a.get(o.district_id, 0.0) + G.area1(
                G.from_model_poly(o.polygon))
    for s in m.megasites:
        if s.kind in ("central_park", "grand_plaza"):
            open_a[s.district_id] = open_a.get(s.district_id, 0.0) + G.area1(
                G.from_model_poly(s.polygon))
    out = {}
    for d in m.districts:
        o, l_ = open_a.get(d.id, 0.0), lot_a.get(d.id, 0.0)
        out[d.id] = (o / (o + l_) if o + l_ > 0 else 0.0, o, l_)
    return out


def check_open_share(spec: CitySpec, m: CityModel, n: _Net):
    c = _check("open_space_share", "Open space share of each district's net land (open space "
                                   "over open space plus lots) within the archetype target")
    for d in m.districts:
        share, o, l_ = open_shares(spec, m)[d.id]
        lo, hi = ST.style_of(d.archetype).open_share
        if not (lo - OPEN_SHARE_TOL <= share <= hi + OPEN_SHARE_TOL):
            c.failures.append(f"'{d.name}' ({d.archetype}): {share:.0%} open (target "
                              f"{lo:.0%} to {hi:.0%})")
    return c


def check_places(spec: CitySpec, m: CityModel, n: _Net):
    c = _check("places_built", "Every named place of the spec is built in its district")
    got = {(p.name, p.district_id) for p in m.places}
    sites = {s.name for s in m.megasites}
    did = {d.name: d.id for d in m.districts}
    for d in spec.districts:
        for pl in d.places:
            if pl.kind in ("temple_complex", "spaceport", "transit_nexus", "freight_terminal",
                           "stadium", "arcology", "central_park", "grand_plaza", "attraction",
                           "skyport") and pl.name in sites:
                continue
            if (pl.name, did.get(d.name)) not in got:
                c.failures.append(f"place '{pl.name}' ({pl.kind}) in '{d.name}' was not built")
    return c


def run(spec: CitySpec, m: CityModel, g) -> list:
    n = _Net(m)
    return [
        check_street_graph(m, n),
        check_lane_graph(m, n),
        check_walkway_graph(m, n, g),
        check_lot_frontage(m, n),
        check_sizes(m, n),
        check_slivers(m, n),
        check_clear_path(m, n),
        check_crosswalks(m, n),
        check_junction_placement(m, n),
        check_junction_angles(m, n),
        check_street_duplicates(m, n),
        check_open_share(spec, m, n),
        check_places(spec, m, n),
    ]


def _pcts(vals: list[float]) -> dict:
    a = np.array(sorted(vals), dtype=np.float64)
    if not len(a):
        return {}
    q = lambda f: round(float(a[min(int(f * (len(a) - 1) + 0.5), len(a) - 1)]), 1)  # noqa
    return {"count": len(a), "min": round(float(a[0]), 1), "p10": q(0.1), "median": q(0.5),
            "p90": q(0.9), "max": round(float(a[-1]), 1)}


def stats(spec: CitySpec, m: CityModel) -> dict:
    jt: dict = {}
    sig = 0
    for j in m.junctions:
        key = f"{j.type.split('.', 1)[1] if '.' in j.type else j.type} {j.shape}"
        jt[key] = jt.get(key, 0) + 1
        sig += j.signalized
    lots_by: dict = {}
    front_by: dict = {}
    for lt in m.lots:
        lots_by.setdefault(lt.archetype, []).append(lt.area_m2)
        front_by.setdefault(lt.archetype, []).append(lt.frontage[0].length_m
                                                     if lt.frontage else 0.0)
    lot_dist = {}
    for k in sorted(lots_by):
        r = _pcts(lots_by[k])
        r["median_frontage_m"] = _pcts(front_by[k]).get("median")
        lot_dist[k] = r
    shares = open_shares(spec, m)
    names = {d.id: d.name for d in m.districts}
    open_tot = math.fsum(v[1] for v in shares.values())
    lot_tot = math.fsum(v[2] for v in shares.values())
    wk: dict = {}
    for w in m.walkways:
        wk[w.kind] = wk.get(w.kind, 0.0) + LineString([p[:2] for p in w.line]).length / 1000
    ok: dict = {}
    for o in m.open_spaces:
        if o.district_id:
            ok[o.kind] = ok.get(o.kind, 0) + 1
    return {
        "junctions": len(m.junctions), "junctions_signalized": sig,
        "junctions_by_type": dict(sorted(jt.items(), key=lambda t: (-t[1], t[0]))),
        "crosswalks": len(m.crosswalks), "sidewalks": len(m.sidewalks),
        "sidewalk_km": round(sum(LineString(s.line).length for s in m.sidewalks) / 1000, 2),
        "lanes": sum(1 for x in m.lanes if x.kind == "lane"),
        "lane_connectors": sum(1 for x in m.lanes if x.kind == "connector"),
        "one_way_segments": sum(1 for s in m.road_segments if s.one_way),
        "walkways": len(m.walkways),
        "walkway_km": {k: round(v, 2) for k, v in sorted(wk.items())},
        "footbridges": sum(1 for s in m.road_segments if s.road_class == "footbridge"),
        "blocks": len(m.blocks), "lots": len(m.lots),
        "merged_lot_groups": len({lt.merged_group_id for lt in m.lots if lt.merged_group_id}),
        "lot_area_m2_by_archetype": lot_dist,
        "block_size_m_by_district": {names[k]: _pcts([math.sqrt(b.area_m2) for b in m.blocks
                                                      if b.district_id == k])
                                     for k in sorted(names)},
        "open_spaces_by_kind": dict(sorted(ok.items())),
        "open_share_by_district": {names[k]: round(v[0], 4) for k, v in sorted(shares.items())},
        "open_share": round(open_tot / (open_tot + lot_tot), 4) if open_tot + lot_tot else 0.0,
        "places": len(m.places),
    }
