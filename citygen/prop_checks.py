"""M6 checks: props and vegetation (scope 5.6, 5.8 and section 9)."""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString

from . import geom as G
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
    from .vegetation import overhead

    ch = _check("tree_clearance", "Crowns 1 m from the facades, tops 1 m under decks, "
                                  "skybridges, raised roads and overhangs; trunks 6 m from "
                                  "junctions and clear of station stairs, metro entrances and "
                                  "bus stops")
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
    polys, under = overhead(c)
    if polys:
        otree = shapely.STRtree(polys)
        ip, ig = otree.query(pts, predicate="dwithin", distance=float(crown.max()))
        d = shapely.distance(pts[ip], np.array(polys, dtype=object)[ig])
        for i, k, dd in zip(ip.tolist(), ig.tolist(), d.tolist()):
            if dd < crown[i] and trees[i].height_m > under[k] - 1.0 + 0.02:
                _limit(ch, f"{trees[i].id}: {trees[i].height_m:g} m under something at "
                           f"{under[k]:g} m")
    street = [i for i, p in enumerate(trees) if _kind(p) in ("street_tree", "median_tree",
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


def run(spec, m: CityModel) -> list:
    if not m.props and not m.plants:
        return []
    with G.canonical():
        c = Ctx(spec, m)
        g = _ground(m)
        return [check_keepout(c, g), check_overlap(g), check_trees(c, m),
                check_lighting(c, m), check_parks(m), check_boats(c, m)]


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
