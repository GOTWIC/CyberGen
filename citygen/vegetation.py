"""M6: vegetation (scope 5.8), placed with the machinery of `props.py`.

| kind | where |
|---|---|
| street_tree | tree pits every 8 to 15 m (closer with more greenery) in sidewalk furniture zones at least 1.2 m wide |
| median_tree / palm | avenue medians at least 2 m wide; palms on waterfront, corporate and spaceport avenues |
| park_tree / conifer | clustered scatter in parks, pocket parks, courtyards and greens, with clearings; conifers in residential and campus districts |
| shrub | park and plaza edges, roof gardens |
| hedge (green area line) | park borders, broken where a path crosses |
| lawn (green area) | avenue medians |
| roof_plant | green roofs: shrubs, small trees on large roofs |
| facade_greenery | street facades in old towns, residential and terraced buildings |
| overgrowth | vacant lots, grimy alleys |

Every tree's crown is kept 1 m from the facades at its height and its top 1 m under any deck,
skybridge, raised road or overhang above it; trunks stay off roads, the sidewalk clear path,
quays, crosswalks and 6 m from junctions (sight lines), and away from station stairs, metro
entrances and bus stops (all ground structures and props are in the occupancy grid).
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString

from . import geom as G
from .props import GROUND, PATH, SIDEWALK, Cand, Ctx, _u, furniture_points, length, walk, yaw_of

q = G.q
TRUNK_R = 0.45
SIGHT_M = 6.0         # trunks this far from junction areas

STREET_SPECIES = {"corporate_core": "ginkgo", "midtown_mixed": "plane",
                  "residential_heights": "linden", "research_campus": "maple",
                  "old_town": "plane", "entertainment_market": "ficus"}
PALM_ARCH = ("corporate_core", "spaceport")


def _tree(kind, x, y, h, crown, species, keep=GROUND, z=0.0, attrs=None) -> Cand:
    return Cand(kind, x, y, z=z, r=TRUNK_R, keep=keep, attrs=attrs or {},
                plant={"height_m": h, "crown_radius_m": crown, "species": species})


def _waterfront(c: Ctx, pts: np.ndarray, reach: float = 60.0) -> np.ndarray:
    tree, _ = c.trees["water"]
    out = np.zeros(len(pts), bool)
    if tree is None or not len(pts):
        return out
    ip, _ = tree.query(shapely.points(pts), predicate="dwithin", distance=reach)
    out[ip] = True
    return out


def street_trees(c: Ctx) -> list[Cand]:
    out = []
    for w in c.sw:
        s = c.seg[w.segment_id]
        if w.furniture_m < 1.2 or w.width_m < 3.5 or s.road_class in ("highway",):
            continue
        L = length(w.line)
        if L < 20.0:
            continue
        mid = w.line[len(w.line) // 2]
        did = c.district_of(np.array([mid]))[0]
        g = c.param(did, "greenery", 0.3)
        if _u("st", w.id) > 0.35 + g:
            continue
        step = 15.0 - 7.0 * g
        arch = c.arch.get(did, "")
        sp = STREET_SPECIES.get(arch, "plane")
        pts = furniture_points(w, step, 6.0 + step * _u("st0", w.id), 0.9, 6.0)
        for k, (x, y, ux, uy, _) in enumerate(pts):
            h = 7.0 + 5.0 * _u("sth", w.id, k)
            out.append(_tree("street_tree", x, y, h, 2.2 + 1.3 * _u("stc", w.id, k), sp,
                             keep=SIDEWALK, attrs={"sidewalk": w.id}))
    return _sight(c, out)


def _sight(c: Ctx, cands: list[Cand]) -> list[Cand]:
    """Trunks off the junction sight lines (SIGHT_M from every junction area), and not over
    station stairs, metro entrances or bus stops (3 m)."""
    if not cands:
        return cands
    pts = shapely.points(np.array([(t.x, t.y) for t in cands]))
    bad = set()
    tree, _ = c.trees["junc"]
    if tree is not None:
        ip, _ = tree.query(pts, predicate="dwithin", distance=SIGHT_M)
        bad |= set(ip.tolist())
    if c.no_tree:
        ft = shapely.STRtree(shapely.points(np.array(c.no_tree)))
        ip, _ = ft.query(pts, predicate="dwithin", distance=3.2)
        bad |= set(ip.tolist())
    return [t for i, t in enumerate(cands) if i not in bad]


def _sight_feet(c: Ctx, cands: list[Cand]) -> list[Cand]:
    """Park trees: only the 3 m around station stairs, metro entrances and bus stops."""
    if not cands or not c.no_tree:
        return cands
    pts = shapely.points(np.array([(t.x, t.y) for t in cands]))
    ft = shapely.STRtree(shapely.points(np.array(c.no_tree)))
    ip, _ = ft.query(pts, predicate="dwithin", distance=3.2)
    bad = set(ip.tolist())
    return [t for i, t in enumerate(cands) if i not in bad]


def median_trees(c: Ctx) -> list[Cand]:
    out = []
    for s in c.m.road_segments:
        cs = s.cross_section
        if s.bridge or s.road_class not in ("avenue", "highway") or cs.median_m < 2.0:
            continue
        if any(z.z > 0.5 for z in s.z_profile):
            continue
        L = length(s.centerline)
        if L < 40.0:
            continue
        mid = s.centerline[len(s.centerline) // 2]
        did = c.district_of(np.array([mid]))[0]
        g = c.param(did, "greenery", 0.3)
        arch = c.arch.get(did, "")
        wf = bool(_waterfront(c, np.array([mid]), 80.0)[0])
        palm = arch in PALM_ARCH or wf
        step = (11.0 if palm else 13.0) - 4.0 * g
        crown_max = min(cs.median_m / 2.0 + 1.5, 3.5)
        for k, (x, y, ux, uy, _) in enumerate(walk(s.centerline, step, 12.0, 12.0)):
            h = (9.0 + 4.0 * _u("mh", s.id, k)) if palm else (7.0 + 4.0 * _u("mh", s.id, k))
            out.append(_tree("palm" if palm else "median_tree", x, y, h,
                             2.0 if palm else crown_max * (0.75 + 0.25 * _u("mc", s.id, k)),
                             "fan_palm" if palm else STREET_SPECIES.get(arch, "plane"),
                             keep=GROUND, attrs={"segment": s.id}))
    return _sight(c, out)


def promenade_trees(c: Ctx) -> list[Cand]:
    out = []
    for w in c.m.walkways:
        if w.kind != "promenade":
            continue
        line = [p[:2] for p in w.line]
        if length(line) < 20.0:
            continue
        mid = line[len(line) // 2]
        wf = bool(_waterfront(c, np.array([mid]), 40.0)[0])
        off = w.width_m / 2.0 + 1.0
        for k, (x, y, ux, uy, _) in enumerate(walk(line, 12.0, 6.0, 4.0)):
            sgn = 1.0 if k % 2 == 0 else -1.0
            out.append(_tree("palm" if wf else "street_tree", x - uy * off * sgn,
                             y + ux * off * sgn, 8.0 + 4.0 * _u("ph", w.id, k),
                             1.8 if wf else 2.6, "date_palm" if wf else "plane",
                             keep=GROUND & ~PATH, attrs={"walkway": w.id}))
    return _sight(c, out)


def _noise(key: str, x: float, y: float, cell: float = 32.0) -> float:
    """Value noise in [0, 1): hashed lattice values, bilinear (smoothstep) between."""
    i, j = math.floor(x / cell), math.floor(y / cell)
    fx, fy = x / cell - i, y / cell - j
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _u(key, i, j), _u(key, i + 1, j)
    cc, d = _u(key, i, j + 1), _u(key, i + 1, j + 1)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (cc * (1 - fx) + d * fx) * fy


PARK_KINDS = {"park": (8.0, 3.0), "pocket_park": (7.0, 2.0), "courtyard": (9.0, 2.0),
              "green": (9.0, 1.5), "garden": (7.0, 2.0)}


def park_trees(c: Ctx) -> list[Cand]:
    """Clustered trees with clearings (value noise over 32 m), conifers in residential and
    campus districts, shrubs along the edges."""
    out = []
    for o in c.m.open_spaces:
        if o.kind not in PARK_KINDS or o.z_m > 0.5:
            continue
        poly = G.from_model_poly(o.polygon)
        if poly.area < 150.0:
            continue
        rp = poly.representative_point()
        did = o.district_id or c.district_of(np.array([[rp.x, rp.y]]))[0]
        g = c.param(did, "greenery", 0.3)
        arch = c.arch.get(did, "")
        spacing, inset = PARK_KINDS[o.kind]
        thresh = 0.55 - 0.35 * g
        conifer_share = 0.45 if arch in ("residential_heights", "research_campus") else 0.1
        x0, y0, x1, y1 = poly.bounds
        width = G._strip_width(G.parts(poly)[0]) if G.parts(poly) else 0.0
        if width < 2.0 * inset + 3.0:
            out += _strip_trees(c, o, poly, width, g)
            continue
        inner = poly.buffer(-inset)
        if inner.is_empty:
            continue
        shapely.prepare(inner)
        nx, ny = int((x1 - x0) / spacing) + 1, int((y1 - y0) / spacing) + 1
        n = 0
        for i in range(nx):
            for j in range(ny):
                x = x0 + (i + 0.5 + (_u(o.id, i, j, "x") - 0.5) * 0.7) * spacing
                y = y0 + (j + 0.5 + (_u(o.id, i, j, "y") - 0.5) * 0.7) * spacing
                if not shapely.contains_xy(inner, x, y):
                    continue
                if _noise(o.id, x, y) < thresh and o.kind == "park":
                    continue      # a clearing
                if o.kind != "park" and _u(o.id, i, j, "p") > 0.35 + 0.5 * g:
                    continue
                k = _u(o.id, i, j, "k")
                if k < conifer_share:
                    out.append(_tree("conifer", x, y, 9.0 + 8.0 * _u(o.id, i, j, "h"),
                                     1.8 + 1.0 * _u(o.id, i, j, "c"), "pine",
                                     attrs={"open_space": o.id}))
                else:
                    out.append(_tree("park_tree", x, y, 8.0 + 10.0 * _u(o.id, i, j, "h"),
                                     2.5 + 3.0 * _u(o.id, i, j, "c"),
                                     ("oak", "maple", "birch", "elm")[int(4 * _u(o.id, i, j,
                                                                                 "s"))],
                                     attrs={"open_space": o.id}))
                n += 1
                if n > 1500:
                    break
        out = out[:-n] + _sight_feet(c, out[-n:]) if n else out
        # shrubs along the edge
        ring = poly.buffer(-1.4)
        for part in G.parts(ring):
            for k, (x, y, ux, uy, _) in enumerate(walk(list(part.exterior.coords), 5.0, 2.0,
                                                       2.0)):
                if _u(o.id, "sh", k) > 0.35 + 0.5 * g:
                    continue
                out.append(Cand("shrub", x, y, r=0.8, keep=GROUND, attrs={"open_space": o.id},
                                plant={"height_m": 1.0 + 0.8 * _u(o.id, "shh", k),
                                       "crown_radius_m": 0.8, "species": "boxwood"}))
    return out


def _strip_trees(c: Ctx, o, poly, width: float, g: float) -> list[Cand]:
    """A linear park (a green strip): trees every 10 m along its middle (2 m apart at least,
    so the two sides of the thin middle ring do not both get one), shrubs along both
    edges."""
    out = []
    if width >= 3.0:
        mid = G.parts(G.qpoly(poly.buffer(-(width / 2.0 - 0.4))))
        trees = []
        for part in mid:
            for k, (x, y, *_) in enumerate(walk(list(part.exterior.coords), 10.0, 3.0, 3.0)):
                t = _tree("park_tree", x, y, 6.0 + 5.0 * _u(o.id, "st", k),
                          min(2.5, width / 2.0 + 1.0),
                          ("linden", "birch")[int(2 * _u(o.id, "ss", k))],
                          attrs={"open_space": o.id})
                t.r = 2.0
                trees.append(t)
        out += _sight_feet(c, trees)
    edge = G.parts(poly.buffer(-min(1.2, width / 4.0)))
    for part in edge:
        for k, (x, y, *_) in enumerate(walk(list(part.exterior.coords), 4.0, 2.0, 2.0)):
            if _u(o.id, "esh", k) > 0.35 + 0.5 * g:
                continue
            out.append(Cand("shrub", x, y, r=0.8, keep=GROUND, attrs={"open_space": o.id},
                            plant={"height_m": 0.9 + 0.6 * _u(o.id, "eh", k),
                                   "crown_radius_m": 0.7, "species": "boxwood"}))
    return out


def roof_plants(c: Ctx) -> list[Cand]:
    out = []
    for gr in c.m.green_areas:
        if gr.kind != "green_roof" or gr.polygon is None:
            continue
        poly = G.from_model_poly(gr.polygon)
        if poly.area < 60.0:
            continue
        big = poly.area > 400.0
        x0, y0, x1, y1 = poly.bounds
        inner = poly.buffer(-1.5)
        if inner.is_empty:
            continue
        shapely.prepare(inner)
        sp = 4.0
        nx, ny = int((x1 - x0) / sp) + 1, int((y1 - y0) / sp) + 1
        n = 0
        for i in range(nx):
            for j in range(ny):
                x = x0 + (i + 0.5 + (_u(gr.id, i, j, "x") - 0.5) * 0.6) * sp
                y = y0 + (j + 0.5 + (_u(gr.id, i, j, "y") - 0.5) * 0.6) * sp
                if not shapely.contains_xy(inner, x, y):
                    continue
                k = _u(gr.id, i, j, "k")
                if big and k < 0.06:
                    h = 3.5 + 2.0 * _u(gr.id, i, j, "h")
                    out.append(Cand("roof_tree", x, y, z=gr.z_m, r=0.0, keep=0,
                                    attrs={"roof": gr.id},
                                    plant={"height_m": h, "crown_radius_m": 1.4,
                                           "species": "maple"}))
                elif k < 0.32:
                    out.append(Cand("shrub", x, y, z=gr.z_m, r=0.0, keep=0,
                                    attrs={"roof": gr.id},
                                    plant={"height_m": 0.6 + 0.6 * _u(gr.id, i, j, "h"),
                                           "crown_radius_m": 0.6, "species": "sedum"}))
                n += 1
                if n > 400:
                    break
    return out


def facade_greenery(c: Ctx) -> list[Cand]:
    out = []
    for b in c.m.buildings:
        if not b.units or b.landmark:
            continue
        arch = c.arch.get(b.district_id, "")
        typ = (b.type or "").split(".")[-1]
        if arch not in ("old_town", "residential_heights") and typ not in ("terraced",
                                                                         "shopfront_row"):
            continue
        g = c.param(b.district_id, "greenery", 0.3)
        fp = G.from_model_poly(b.footprint) if b.footprint is not None else None
        for k, u in enumerate(b.units):
            if _u("fg", b.id, k) > 0.25 + 0.6 * g:
                continue
            (ax, ay), (bx, by) = u.edge
            L = math.hypot(bx - ax, by - ay)
            if L < 3.0:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            nx, ny = uy, -ux
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            if fp is not None and shapely.contains_xy(fp, mx + nx * 0.5, my + ny * 0.5):
                nx, ny = -nx, -ny
            floor = 1 + int(_u("fgf", b.id, k) * max(1, min(b.floors - 1, 3)))
            if floor >= b.floors:
                continue
            out.append(Cand("facade_greenery", mx + nx * 0.25, my + ny * 0.25,
                            z=q(floor * b.floor_height_m), yaw=yaw_of(ux, uy), r=0.0, keep=0,
                            scale=(q(min(L * 0.8, 8.0)), 1.0, 1.0),
                            attrs={"building": b.id},
                            plant={"height_m": 2.0, "crown_radius_m": 0.4,
                                   "species": "ivy"}))
    return out


def overgrowth(c: Ctx) -> list[Cand]:
    """Low scrub on vacant lots and along grimy alleys."""
    out = []
    built = {b.lot_id for b in c.m.buildings if b.lot_id}
    built |= {e.lot_id for e in c.m.site_elements if e.lot_id}
    for lt in c.m.lots:
        if lt.id in built:
            continue
        poly = G.from_model_poly(lt.polygon)
        g = c.param(lt.district_id, "grime", 0.4)
        x0, y0, x1, y1 = poly.bounds
        inner = poly.buffer(-1.0)
        if inner.is_empty:
            continue
        shapely.prepare(inner)
        sp = 5.0
        n = 0
        for i in range(int((x1 - x0) / sp) + 1):
            for j in range(int((y1 - y0) / sp) + 1):
                x = x0 + (i + _u(lt.id, i, j, "x")) * sp
                y = y0 + (j + _u(lt.id, i, j, "y")) * sp
                if not shapely.contains_xy(inner, x, y) or _u(lt.id, i, j, "k") > 0.3 + 0.5 * g:
                    continue
                out.append(Cand("overgrowth", x, y, r=0.7, keep=GROUND,
                                attrs={"lot": lt.id},
                                plant={"height_m": 0.5 + 1.2 * _u(lt.id, i, j, "h"),
                                       "crown_radius_m": 0.7 + 0.6 * _u(lt.id, i, j, "c"),
                                       "species": "scrub"}))
                n += 1
                if n > 200:
                    break
    return out


GENERATORS = [("median_trees", median_trees), ("promenade_trees", promenade_trees),
              ("park_trees", park_trees), ("roof_plants", roof_plants),
              ("facade_greenery", facade_greenery), ("overgrowth", overgrowth)]


# ---------------------------------------------------------------------------
# Crowns: clear of facades and overhead
# ---------------------------------------------------------------------------

def overhead(c: Ctx) -> tuple:
    """(footprints, underside z) of everything above the ground a tree could grow into."""
    m = c.m
    P = G.from_model_poly
    polys, under = [], []
    for s in m.structures:
        a = s.attrs or {}
        if len(s.line) >= 2 and s.z1_m > 0.5:
            w = a.get("width_m", 4.0)
            polys.append(LineString([p[:2] for p in s.line]).buffer(w / 2.0 + 1.0,
                                                                   cap_style="flat"))
            under.append(s.z0_m)
        elif s.footprint is not None and s.z0_m > 0.5:
            polys.append(P(s.footprint))
            under.append(s.z0_m)
    for sb in m.skybridges:
        polys.append(LineString(sb.line).buffer(sb.width_m / 2.0 + 1.0, cap_style="flat"))
        under.append(sb.z_m - 1.0)
    for s in m.road_segments:
        zs = [z.z for z in s.z_profile]
        if s.bridge or any(z > 0.5 for z in zs):
            polys.append(LineString(s.centerline).buffer(s.width_m / 2.0 + 1.0,
                                                         cap_style="flat"))
            under.append(max(0.0, min([z for z in zs if z > 0.5] or [6.0]) - 1.5))
    for b in m.buildings:
        for ms in b.masses:
            if ms.z0_m > 0.5:
                polys.append(P(ms.footprint))
                under.append(ms.z0_m)
    return polys, np.array(under)


def fit_crowns(c: Ctx, cands: list[Cand]) -> list[Cand]:
    """Each ground tree's crown narrowed to stay 1 m from the facades and its height capped
    1 m under anything overhead; dropped when too small."""
    trees = [t for t in cands if t.plant is not None and t.z == 0.0 and
             t.kind not in ("facade_greenery",)]
    if not trees:
        return cands
    if not hasattr(c, "_over"):
        polys, under = overhead(c)
        c._over = (shapely.STRtree(polys) if polys else None, np.array(polys, dtype=object),
                   under)
    pts = shapely.points(np.array([(t.x, t.y) for t in trees]))
    crown = np.array([t.plant["crown_radius_m"] for t in trees])
    # facades: the nearest building at the ground
    tree, geoms = c.trees["bld"]
    dmin = np.full(len(trees), np.inf)
    if tree is not None:
        ip, ig = tree.query(pts, predicate="dwithin", distance=float(crown.max()) + 1.0)
        if len(ip):
            np.minimum.at(dmin, ip, shapely.distance(pts[ip], geoms[ig]))
    cap = np.full(len(trees), np.inf)
    otree, ogeoms, under = c._over
    if otree is not None:
        ip, ig = otree.query(pts, predicate="dwithin", distance=float(crown.max()))
        if len(ip):
            d = shapely.distance(pts[ip], ogeoms[ig])
            hit = d < crown[ip]
            np.minimum.at(cap, ip[hit], under[ig[hit]] - 1.0)
    drop = set()
    for i, t in enumerate(trees):
        r = min(t.plant["crown_radius_m"], dmin[i] - 1.0)
        h = min(t.plant["height_m"], cap[i])
        small = 0.5 if t.kind in ("shrub", "overgrowth") else 1.2
        low = 0.4 if t.kind in ("shrub", "overgrowth") else 3.0
        if r < small or h < low:
            drop.add(id(t))
            continue
        t.plant["crown_radius_m"] = q(r)
        t.plant["height_m"] = q(h)
    return [t for t in cands if id(t) not in drop]


# ---------------------------------------------------------------------------
# Green areas: median lawns, park hedges
# ---------------------------------------------------------------------------

def green_rows(c: Ctx) -> list[dict]:
    m = c.m
    rows = []
    jtree, jgeoms = c.trees["junc"]
    n = 0
    for s in m.road_segments:
        cs = s.cross_section
        if s.bridge or s.road_class not in ("avenue", "highway") or cs.median_m < 2.0:
            continue
        if any(z.z > 0.5 for z in s.z_profile):
            continue
        strip = LineString(s.centerline).buffer(cs.median_m / 2.0 - 0.3, cap_style="flat")
        if jtree is not None:
            hits = sorted(jtree.query(strip, predicate="intersects").tolist())
            if hits:
                strip = G.diff(G.qpoly(strip), G.union([jgeoms[k].buffer(4.0) for k in hits]))
        for part in G.parts(G.qpoly(strip)):
            if G.area(part) < 20.0:
                continue
            n += 1
            rows.append({"id": f"{s.id}.lawn{n:04d}", "type": "green_area.lawn", "kind": "lawn",
                         "polygon": G.to_model_poly(part), "z_m": 0.0,
                         "attrs": {"median": s.id}})
    ptree, pgeoms = c.trees["paths"]
    for o in m.open_spaces:
        if o.kind not in ("park", "garden") or o.z_m > 0.5:
            continue
        poly = G.from_model_poly(o.polygon)
        did = o.district_id
        if poly.area < 1500.0 or c.param(did, "greenery", 0.3) < 0.25:
            continue
        ring = G.parts(G.qpoly(poly.buffer(-0.8)))
        if not ring:
            continue
        pts = walk(list(ring[0].exterior.coords), 2.0)
        if len(pts) < 4:
            continue
        arr = shapely.points(np.array([(x, y) for x, y, *_ in pts]))
        gap = np.zeros(len(pts), bool)
        if ptree is not None:
            ip, _ = ptree.query(arr, predicate="dwithin", distance=3.0)
            gap[ip] = True
        run: list = []
        k = 0
        for (x, y, *_), g in zip(pts, gap.tolist()):
            if g:
                if len(run) >= 3:
                    k += 1
                    rows.append({"id": f"{o.id}.hedge{k:03d}", "type": "green_area.hedge_line",
                                 "kind": "hedge_line", "line": run, "z_m": 0.0,
                                 "attrs": {"open_space": o.id, "height_m": 1.2}})
                run = []
            else:
                run.append([q(x), q(y)])
        if len(run) >= 3:
            k += 1
            rows.append({"id": f"{o.id}.hedge{k:03d}", "type": "green_area.hedge_line",
                         "kind": "hedge_line", "line": run, "z_m": 0.0,
                         "attrs": {"open_space": o.id, "height_m": 1.2}})
    return rows

