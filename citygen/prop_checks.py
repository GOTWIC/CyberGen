"""M6 checks: props and vegetation (scope 5.6, 5.8 and section 9); M20's `prop_support` (every
prop, plant and roof item on a surface at its height) and `plant_headroom` (no plant within
1 m of the underside of what is over it, measured along it)."""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from . import vegetation as V
from .checks import Check
from .model import CityModel
from .props import EXCEPT, KEEP_R, KINDS, REQUIRED, Cand, Ctx

LIMIT = 12
LIGHT_REACH_M = 25.0
LIGHT_SHARE = 0.85
SIGHT_M = 6.0
TREE_KINDS = ("street_tree", "median_tree", "palm", "park_tree", "conifer")


def _check(cid: str, desc: str) -> Check:
    return Check(cid, desc)


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < LIMIT:
        c.failures.append(msg)
    elif len(c.failures) == LIMIT:
        c.failures.append("... more")


def _kind(e) -> str:
    return (e.type or "").split(".", 1)[-1]


def _ground(m: CityModel) -> list[tuple]:
    """(id, kind, x, y, radius) of everything standing on the ground: props with a ground
    radius and plants (trunks; shrubs and scrub by their crown)."""
    out = []
    for p in m.props:
        k = _kind(p)
        r = KINDS.get(k, (None,))[0]
        if r and k != "boat" and p.position[2] <= 0.5:
            out.append((p.id, k, p.position[0], p.position[1], r))
    for p in m.plants:
        k = _kind(p)
        if p.position[2] > 0.5 or k == "facade_greenery":
            continue
        r = 0.45 if k in TREE_KINDS else {"shrub": 0.8, "overgrowth": 0.7}.get(k, 0.45)
        out.append((p.id, k, p.position[0], p.position[1], r))
    return out


def check_keepout(c: Ctx, g: list) -> Check:
    ch = _check("props_keepout", "Props and trunks stay out of lanes, crosswalks, junctions, "
                                 "buildings, water, entrances and driveways, ground structures "
                                 "and the sidewalk clear path (1.8 m)")
    if not g:
        return ch
    cands = [Cand(k, x, y, r=KEEP_R.get(k, r), keep=REQUIRED & ~EXCEPT.get(k, 0))
             for _, k, x, y, r in g]
    bad = c.blocked(cands)
    for (pid, k, *_), b in zip(g, bad.tolist()):
        if b:
            _limit(ch, f"{pid}: in a keep-out")
    ch.notes.append(f"{len(g)} things on the ground")
    return ch


def check_overlap(g: list) -> Check:
    ch = _check("props_overlap", "Nothing on the ground overlaps anything else (props, "
                                 "trunks, shrubs)")
    if len(g) < 2:
        return ch
    xy = np.array([(x, y) for _, _, x, y, _ in g])
    r = np.array([v for *_, v in g])
    pts = shapely.points(xy)
    tree = shapely.STRtree(pts)
    ip, iq = tree.query(pts, predicate="dwithin", distance=2.0 * float(r.max()))
    keep = ip < iq
    ip, iq = ip[keep], iq[keep]
    d = np.hypot(xy[ip, 0] - xy[iq, 0], xy[ip, 1] - xy[iq, 1])
    hit = d < r[ip] + r[iq] - 0.01
    for a, b in sorted(zip(ip[hit].tolist(), iq[hit].tolist())):
        _limit(ch, f"{g[a][0]} overlaps {g[b][0]}")
    return ch


def check_trees(c: Ctx, m: CityModel) -> Check:
    ch = _check("tree_clearance", "Crowns 1 m from the facades; trunks 6 m from junctions "
                                  "and clear of station stairs, metro entrances and bus stops "
                                  "(their tops under what is over them: plant_headroom)")
    trees = [p for p in m.plants if p.position[2] <= 0.5 and _kind(p) in TREE_KINDS]
    if not trees:
        return ch
    pts = shapely.points(np.array([p.position[:2] for p in trees]))
    crown = np.array([p.crown_radius_m for p in trees])
    tree, geoms = c.trees["bld"]
    if tree is not None:
        ip, ig = tree.query(pts, predicate="dwithin", distance=float(crown.max()) + 1.0)
        d = shapely.distance(pts[ip], geoms[ig])
        for i in sorted(set(ip[d < crown[ip] + 1.0 - 0.02].tolist())):
            _limit(ch, f"{trees[i].id}: crown within 1 m of a facade")
    street =[i for i, p in enumerate(trees) if _kind(p) in ("street_tree", "median_tree",
                                                              "palm")]
    jtree, _ = c.trees["junc"]
    if street and jtree is not None:
        ip, _ = jtree.query(pts[street], predicate="dwithin", distance=SIGHT_M - 0.05)
        for i in sorted(set(ip.tolist())):
            _limit(ch, f"{trees[street[i]].id}: trunk in a junction sight line")
    # station stairs and elevator feet, metro entrances, bus stops
    feet = []
    for w in m.walkways:
        if w.kind in ("stairs", "escalator", "elevator"):
            feet += [p[:2] for p in (w.line[0], w.line[-1]) if abs(p[2]) < 0.5]
    for s in m.structures:
        if (s.attrs or {}).get("role") == "metro_entrance" and s.footprint is not None:
            cc = G.from_model_poly(s.footprint).centroid
            feet.append((cc.x, cc.y))
    feet += [p.position[:2] for p in m.props if _kind(p) == "bus_stop"]
    if feet:
        ft = shapely.STRtree(shapely.points(np.array(feet)))
        ip, _ = ft.query(pts, predicate="dwithin", distance=3.0)
        for i in sorted(set(ip.tolist())):
            _limit(ch, f"{trees[i].id}: over station stairs, a metro entrance or a bus stop")
    return ch


def check_lighting(c: Ctx, m: CityModel) -> Check:
    ch = _check("street_lighting", f"Street or wall lights within {LIGHT_REACH_M:g} m of at "
                                   f"least {LIGHT_SHARE:.0%} of every district's sidewalks")
    lights = [p.position[:2] for p in m.props if _kind(p) in ("street_light", "wall_light")]
    if not m.sidewalks:
        return ch
    lt = shapely.STRtree(shapely.points(np.array(lights))) if lights else None
    from .props import walk
    tot: dict = {}
    lit: dict = {}
    samples = []
    for w in m.sidewalks:
        for x, y, *_ in walk(w.line, 5.0, 2.5):
            samples.append((x, y))
    if not samples:
        return ch
    arr = np.array(samples)
    dids = c.district_of(arr)
    ok = np.zeros(len(arr), bool)
    if lt is not None:
        ip, _ = lt.query(shapely.points(arr), predicate="dwithin", distance=LIGHT_REACH_M)
        ok[ip] = True
    for did, o in zip(dids, ok.tolist()):
        tot[did] = tot.get(did, 0) + 1
        lit[did] = lit.get(did, 0) + (1 if o else 0)
    names = {d.id: d.name for d in m.districts}
    for did in sorted(tot, key=lambda d: (d is None, d or "")):
        if did is None or tot[did] < 20:
            continue
        share = lit[did] / tot[did]
        ch.notes.append(f"{names.get(did, did)}: {share:.0%} lit")
        if share < LIGHT_SHARE:
            _limit(ch, f"{names.get(did, did)}: {share:.0%} of the sidewalks lit")
    return ch


def check_parks(m: CityModel) -> Check:
    ch = _check("park_planting", "Every park, pocket park and garden of 800 m2 or more at the "
                                 "ground, at least 6 m wide, has trees or shrubs (a narrower "
                                 "strip is a path with verges)")
    plants = [p.position[:2] for p in m.plants if p.position[2] <= 0.5]
    tree = shapely.STRtree(shapely.points(np.array(plants))) if plants else None
    for o in m.open_spaces:
        if o.kind not in ("park", "pocket_park", "garden") or o.z_m > 0.5:
            continue
        poly = G.from_model_poly(o.polygon)
        if G.area(poly) < 800.0 or G._strip_width(G.parts(poly)[0]) < 6.0:
            continue
        if tree is None or not len(tree.query(poly, predicate="intersects")):
            _limit(ch, f"{o.id} ({o.kind}, {G.area(poly):.0f} m2): no plants")
    return ch


def check_boats(c: Ctx, m: CityModel) -> Check:
    ch = _check("boats_afloat", "Boats lie in their waterway, clear of bridges")
    ww = {w.id: G.from_model_poly(w.polygon) for w in m.waterways}
    for p in m.props:
        if _kind(p) != "boat":
            continue
        poly = ww.get((p.attrs or {}).get("waterway"))
        a = math.radians(p.yaw_deg)
        hx, hy = 4.0 * p.scale[0], 1.5 * p.scale[1]
        ca, sa = math.cos(a), math.sin(a)
        x, y = p.position[0], p.position[1]
        hull = shapely.Polygon([(x + ca * u - sa * v, y + sa * u + ca * v)
                                for u, v in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))])
        if poly is None or not poly.buffer(0.05).contains(hull):
            _limit(ch, f"{p.id}: not in its waterway")
    return ch


# ---------------------------------------------------------------------------
# M20: on their surfaces, under what is over them
# ---------------------------------------------------------------------------

SUPPORT_TOL_M = 0.02
# things on a wall: how far from it their anchor may be (an awning's: half its depth more)
WALL_REACH_M = {"sign": 1.6, "awning": 1.6, "ac_unit": 1.6, "wall_light": 0.6,
                "facade_greenery": 1.6}


class _Roads:
    """Road corridors (property line to property line) and M18's fills, for the surfaces a
    thing may stand on."""

    def __init__(self, m: CityModel):
        self.rows, polys = [], []
        for s in m.road_segments:
            if len(s.centerline) < 2:
                continue
            line = LineString(s.centerline)
            half = max(s.cross_section.total_width_m, s.width_m) / 2.0
            # (round ends: the corners of a junction stand at its legs' heights there)
            polys.append(line.buffer(half + 0.05))
            self.rows.append((s.id, line, [(z.s, z.z) for z in s.z_profile]))
        self.tree = shapely.STRtree(polys) if polys else None
        fill = [G.from_model_poly(x.footprint) for x in m.structures
                if x.kind == "embankment" and x.footprint is not None]
        self.fill = shapely.STRtree(fill) if fill else None

    def at(self, x: float, y: float) -> list[tuple]:
        """(road id, its surface z) of each road whose corridor holds the point."""
        from .props import _z_at

        if self.tree is None:
            return []
        p = Point(x, y)
        out = []
        for k in sorted(self.tree.query(p, predicate="intersects").tolist()):
            sid, line, prof = self.rows[k]
            out.append((sid, _z_at(prof, line.project(p)) if prof else 0.0))
        return out

    def own(self, x: float, y: float, z: float) -> frozenset:
        """The roads whose surface a thing at z stands on (empty: the ground alone)."""
        return frozenset(sid for sid, zr in self.at(x, y) if abs(zr - z) <= SUPPORT_TOL_M)

    def in_fill(self, x: float, y: float) -> bool:
        return self.fill is not None and \
            len(self.fill.query(Point(x, y), predicate="within")) > 0


def _extent(p) -> tuple[float, float]:
    """A wall mount's z extent (a wall light hangs under its point, as its prototype)."""
    k = _kind(p)
    z = p.position[2]
    if k == "wall_light":
        return z - 0.4, z
    if k == "facade_greenery":
        return z, z + p.height_m
    return z, z + KINDS.get(k, (None, (0.0, 0.0, 0.0)))[1][2] * p.scale[2]


def check_support(c: Ctx, m: CityModel) -> Check:
    from .props import STANDING
    from .vegetation import roof_lift

    ch = _check("prop_support", "Every prop, plant and roof item stands on a surface at its "
                                "height within 2 cm (the ground, a quay deck, a road's deck, "
                                "the water, a roof, a wall it is mounted on, a deck's "
                                "underside it hangs from), none in a road's fill, and every "
                                "prop standing fits 1 m under what is over it")
    oh = V.overhead(c)
    roads = _Roads(m)
    ww = {w.id for w in m.waterways}
    green = {g.id: g for g in m.green_areas}
    bld = {b.id: b for b in m.buildings}
    n = {"ground": 0, "road": 0, "wall": 0, "roof": 0, "water": 0, "hung": 0}
    stand: list = []
    for p in list(m.props) + list(m.plants):
        k = _kind(p)
        x, y, z = p.position
        a = p.attrs or {}
        if k == "boat":
            n["water"] += 1
            wid = a.get("waterway")
            if wid in ww and abs(z - c.water_z(wid, x, y)) > SUPPORT_TOL_M:
                _limit(ch, f"{p.id}: at {z:g} m, its water at {c.water_z(wid, x, y):g} m")
            continue
        if k == "wall_light" and a.get("mount") == "deck":
            n["hung"] += 1
            u = float(oh.under(np.array([[x, y]]), np.array([0.0]),
                               np.array([z - 0.5]), tol=SUPPORT_TOL_M)[0])
            if abs(u - z) > SUPPORT_TOL_M:
                _limit(ch, f"{p.id}: hung at {z:g} m, the underside over it at {u:g} m")
            continue
        if k in WALL_REACH_M:
            n["wall"] += 1
            reach = WALL_REACH_M[k] + (p.scale[1] / 2.0 if k == "awning" else 0.0) + (
                0.7 if k == "sign" and a.get("blade") else 0.0)
            lo, hi = _extent(p)
            if c.wall_top(x, y, reach, lo) < hi - SUPPORT_TOL_M:
                _limit(ch, f"{p.id}: no wall from {lo:.2f} to {hi:.2f} m within {reach:g} m")
            else:
                u = float(oh.under(np.array([[x, y]]), np.array([0.0]), np.array([lo]),
                                   tol=-SUPPORT_TOL_M)[0])
                if u < hi - SUPPORT_TOL_M:
                    _limit(ch, f"{p.id}: from {lo:.2f} to {hi:.2f} m, into something over "
                               f"it at {u:g} m")
            continue
        if k == "overhead_cable":
            n["wall"] += 1
            ya = math.radians(p.yaw_deg)
            half = p.scale[0] / 2.0
            for sgn in (1.0, -1.0):
                ex, ey = x + math.cos(ya) * half * sgn, y + math.sin(ya) * half * sgn
                if c.wall_top(ex, ey, 1.7, 0.0) < z - SUPPORT_TOL_M:
                    _limit(ch, f"{p.id}: an end tied to no wall as high as {z:g} m")
                    break
            continue
        if a.get("roof") is not None:
            n["roof"] += 1
            g = green.get(a["roof"])
            b = bld.get(g.building_id) if g is not None else None
            if g is None or abs(g.z_m - z) > SUPPORT_TOL_M or b is None or not any(
                    abs(ms.z1_m - g.z_m) <= SUPPORT_TOL_M and
                    shapely.contains_xy(G.from_model_poly(ms.footprint), x, y)
                    for ms in b.masses):
                _limit(ch, f"{p.id}: at {z:g} m, not on its roof")
            stand.append((p, frozenset()))
            continue
        own = roads.own(x, y, z)
        if abs(z) > SUPPORT_TOL_M and own:
            n["road"] += 1
        elif abs(z) > SUPPORT_TOL_M:
            _limit(ch, f"{p.id}: at {z:g} m, over the ground and on no road there")
            continue
        else:
            n["ground"] += 1
            if roads.in_fill(x, y):
                _limit(ch, f"{p.id}: on the ground inside a road's fill")
        if hasattr(p, "crown_radius_m") or KINDS.get(k, (None,))[0] or k in STANDING:
            stand.append((p, own))
    # roof items on the roofs they stand on
    for b in m.buildings:
        for it in b.roof_items:
            x, y, z = it.position
            n["roof"] += 1
            if not any(abs(ms.z1_m - z) <= SUPPORT_TOL_M and
                       shapely.contains_xy(G.from_model_poly(ms.footprint), x, y)
                       for ms in b.masses):
                _limit(ch, f"{b.id}: its {it.kind} at {z:g} m on no roof")
    # every prop standing fits under what is over it (plants: plant_headroom)
    props = [(p, o) for p, o in stand if not hasattr(p, "crown_radius_m")]
    if props:
        xy = np.array([p.position[:2] for p, _ in props], dtype=np.float64)
        reach = np.array([max(KINDS.get(_kind(p), (None,))[0] or 0.05, 0.05)
                          for p, _ in props])
        base = np.array([p.position[2] for p, _ in props])
        u = oh.under(xy, reach, base, own=[o for _, o in props], tol=-SUPPORT_TOL_M,
                     lift=roof_lift(c, [p for p, _ in props]))
        for (p, _), uu, b0 in zip(props, u.tolist(), base.tolist()):
            h = KINDS.get(_kind(p), (None, (0.0, 0.0, 0.0)))[1][2] * p.scale[2]
            if b0 + h > uu - V.HEADROOM_M + SUPPORT_TOL_M:
                _limit(ch, f"{p.id}: {h:g} m tall at {b0:g} m under something at {uu:g} m")
    ch.notes.append(", ".join(f"{v} on {k}" for k, v in n.items()))
    return ch


def check_headroom(c: Ctx, m: CityModel) -> Check:
    from .vegetation import roof_lift

    ch = _check("plant_headroom", "No plant under a raised road, ramp, flyover, guideway, "
                                  "deck, skybridge or overhang reaches higher than its "
                                  "underside less 1 m, measured along it where the plant "
                                  "stands; none in a road's fill")
    plants = [p for p in m.plants if _kind(p) != "facade_greenery"]
    if not plants:
        return ch
    oh = V.overhead(c)
    roads = _Roads(m)
    xy = np.array([p.position[:2] for p in plants], dtype=np.float64)
    base = np.array([p.position[2] for p in plants])
    own = [roads.own(*p.position) for p in plants]
    u = oh.under(xy, np.array([p.crown_radius_m for p in plants]), base, own=own,
                 tol=-SUPPORT_TOL_M, lift=roof_lift(c, plants))
    under = 0
    for p, uu, b0 in zip(plants, u.tolist(), base.tolist()):
        if uu == math.inf:
            continue
        under += 1
        if b0 + p.height_m > uu - V.HEADROOM_M + SUPPORT_TOL_M:
            _limit(ch, f"{p.id}: {p.height_m:g} m at {b0:g} m under something at {uu:g} m")
    ch.notes.append(f"{under} plants under something")
    return ch


def run(spec, m: CityModel) -> list:
    if not m.props and not m.plants:
        return []
    with G.canonical():
        c = Ctx(spec, m)
        g = _ground(m)
        return [check_keepout(c, g), check_overlap(g), check_trees(c, m),
                check_lighting(c, m), check_parks(m), check_boats(c, m),
                check_support(c, m), check_headroom(c, m)]


def stats(m: CityModel) -> dict:
    props: dict = {}
    for p in m.props:
        k = _kind(p)
        props[k] = props.get(k, 0) + 1
    plants: dict = {}
    for p in m.plants:
        k = _kind(p)
        plants[k] = plants.get(k, 0) + 1
    lawn = sum(G.area(G.from_model_poly(g.polygon)) for g in m.green_areas
               if g.kind == "lawn" and g.polygon is not None)
    hedge = sum(LineString(g.line).length for g in m.green_areas
                if g.kind == "hedge_line" and len(g.line) >= 2)
    trees = sum(v for k, v in plants.items() if k in TREE_KINDS)
    return {"props": len(m.props), "plants": len(m.plants), "trees": trees,
            "instances": len(m.props) + len(m.plants),
            "props_by_kind": dict(sorted(props.items(), key=lambda kv: (-kv[1], kv[0]))),
            "plants_by_kind": dict(sorted(plants.items(), key=lambda kv: (-kv[1], kv[0]))),
            "lawn_m2": round(lawn), "hedge_km": round(hedge / 1000.0, 2)}
