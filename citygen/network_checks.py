"""M17 checks of the road network as a whole (scope section 12, M17; `docs/run_through_1.md`):
every dead end deliberate and tagged, two roads at one level overlapping only inside a
junction, bridges apart in plan or by their clearance in height, roads clear of buildings at
their own height.

Like `checks.py`, every check reads only the city model and the filled spec. Heights are
measured as the model gives them: over the ground where it stands (M13), so on a terrain city
a road's surface is its grade line plus its z profile and a building's masses stand on its
base.
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from . import streets as ST
from .model import CityModel
from .spec import CitySpec

OVERLAP_M2 = 25.0       # rights of way of two roads at one level overlapping outside every
#                         junction (the corner where two sidewalks meet fits within it)
JUNCTION_PAD_M = 1.0    # ... a junction polygon taken this much wider
LEVEL_M = 4.0           # two road surfaces within this in height are at one level
GATE_REACH_M = 1.0      # a gate or water end within its half width, GATE_M and this of it
BRIDGE_M2 = 2.0         # bridge decks overlapping in plan by more than this ...
CLEAR_UNDER_M = {"road": 5.5, "pedestrian": 2.5, "transit": 5.5}   # ... keep this clear
DECK_M = {"road": 1.5, "pedestrian": 0.8}     # under the upper deck (M1b's road deck: M7
#                                               keeps crossing road decks 7 m apart)
CLEAR_TOL_M = 0.15
MASS_M2 = 2.0           # a road's right of way over a building mass by more than this ...
HEADROOM_M = 5.0        # ... clashes unless the mass is this far above the road surface or
#                         below it
PATH_HEADROOM_M = 2.5   # ... over a pedestrian path


class _Check:  # same shape as checks.Check (imported lazily there)
    pass


def _check(id_: str, title: str):
    from .checks import Check as C

    return C(id_, title)


def _z_at(prof, s: float) -> float:
    if not prof:
        return 0.0
    if s <= prof[0].s:
        return prof[0].z
    for a, b in zip(prof, prof[1:]):
        if a.s <= s <= b.s:
            return a.z if b.s == a.s else a.z + (s - a.s) / (b.s - a.s) * (b.z - a.z)
    return prof[-1].z


def surface_z(seg, line: LineString, p) -> float:
    """A road's surface height at the point of it nearest p: its z profile over its grade
    line (M13), else over flat ground."""
    s = line.project(p if isinstance(p, Point) else Point(p))
    return _z_at(seg.z_profile, s) + (_z_at(seg.ground, s) if seg.ground else 0.0)


def _rows(m: CityModel) -> tuple[list, list]:
    lines = [LineString(s.centerline) for s in m.road_segments]
    rows = G.snap_many(shapely.buffer(
        np.array(lines, dtype=object), np.array([s.width_m / 2 for s in m.road_segments]),
        cap_style="flat", join_style="mitre", mitre_limit=2.0))
    return lines, list(rows)


def _inter(a, b):
    """Intersection on the 1 cm grid (GEOS's floating overlay can take two corridors that only
    share an edge on a 45 degree line for one inside the other)."""
    return G.polygonal(shapely.intersection(a, b, grid_size=G.GRID_M))


def _water(m: CityModel):
    polys = [G.from_model_poly(p) for s in m.seas for p in s.polygons]
    polys += [G.from_model_poly(x.polygon) for x in list(m.rivers) + list(m.channels) +
              list(m.waterways)]
    return shapely.union_all([shapely.make_valid(p) for p in polys]) if polys else None


def check_dead_ends(spec: CitySpec, m: CityModel):
    c = _check("road_dead_ends", "Every dead end is deliberate and says so (`dead_end`): at "
                                 "the map edge, a water end, a park, plaza or megasite gate, a "
                                 "path's end, a cul-de-sac with its turning bulb, a deck "
                                 "street's end")
    deg: dict = {}
    seg_at: dict = {}
    for s in m.road_segments:
        for n in (s.start, s.end):
            deg[n] = deg.get(n, 0) + 1
            seg_at[n] = s
    edge = shapely.box(*m.bounds).exterior
    water = _water(m)
    opens = [G.from_model_poly(o.polygon) for o in m.open_spaces]
    opens += [G.from_model_poly(s.polygon) for s in m.megasites]
    opens += [G.from_model_poly(p.polygon) for p in m.places if p.polygon is not None]
    otree = shapely.STRtree(opens) if opens else None
    bulbs = {j.node_id for j in m.junctions if j.shape == "cul_de_sac"}
    for n in m.road_nodes:
        if deg.get(n.id) != 1:
            continue
        s = seg_at[n.id]
        kind = n.attrs.get("dead_end")
        p = Point(n.position[:2])
        prim = s.road_class in ("highway", "avenue")
        reach = s.width_m / 2 + (ST.PRIMARY_GATE_M if prim else ST.GATE_M) + GATE_REACH_M
        where = f"node {n.id} ({s.road_class} {s.id}) at ({p.x:.0f}, {p.y:.0f})"
        if kind not in ST.DEAD_END_KINDS:
            c.failures.append(f"{where}: a dead end that says nothing of why")
        elif kind == "map_edge":
            if edge.distance(p) > 1.0:
                c.failures.append(f"{where}: a map edge {edge.distance(p):.0f} m from it")
        elif kind == "water_end":
            if water is None or water.distance(p) > reach:
                c.failures.append(f"{where}: a water end away from the water")
        elif kind in ("park_gate", "plaza_gate", "site_gate"):
            near = otree.query(p, predicate="dwithin", distance=reach) if otree else []
            if not len(near):
                c.failures.append(f"{where}: a {kind.replace('_', ' ')} with no open space, "
                                  "plaza or megasite at it")
        elif kind == "path_end":
            if s.road_class not in ST.PEDESTRIAN:
                c.failures.append(f"{where}: a path end on a {s.road_class}")
        elif kind == "cul_de_sac":
            if n.id not in bulbs and s.attrs.get("role") not in ("deck_ramp",):
                c.failures.append(f"{where}: a cul-de-sac without its turning bulb")
        elif kind == "deck_end":
            if "deck" not in s.attrs:
                c.failures.append(f"{where}: a deck street's end off a deck")
    return c


def road_overlaps(m: CityModel) -> list[tuple]:
    """Pairs of segments at one level whose rights of way overlap outside every junction:
    (a, b, m2, point)."""
    segs = m.road_segments
    if not segs:
        return []
    lines, rows = _rows(m)
    jpolys = [G.from_model_poly(j.polygon).buffer(JUNCTION_PAD_M) for j in m.junctions]
    jtree = shapely.STRtree(jpolys) if jpolys else None
    tree = shapely.STRtree(rows)
    a_idx, b_idx = tree.query(rows, predicate="intersects")
    out = []
    for i, j in sorted(zip(a_idx.tolist(), b_idx.tolist())):
        if j <= i:
            continue
        ov = _inter(rows[i], rows[j])
        if ov.area <= OVERLAP_M2:
            continue
        if jtree is not None:
            near = [jpolys[k] for k in sorted(int(x) for x in jtree.query(ov))]
            if near:
                ov = shapely.difference(ov, shapely.union_all(near), grid_size=G.GRID_M)
        if ov.area <= OVERLAP_M2:
            continue
        p = ov.representative_point()
        za = surface_z(segs[i], lines[i], p)
        zb = surface_z(segs[j], lines[j], p)
        if abs(za - zb) < LEVEL_M:
            out.append((segs[i], segs[j], ov.area, p))
    return out


def check_overlaps(spec: CitySpec, m: CityModel):
    c = _check("road_overlaps", f"Two roads at one level (within {LEVEL_M:g} m) overlap only "
                                f"inside a junction: rights of way overlapping by more than "
                                f"{OVERLAP_M2:g} m2 outside every junction polygon")
    for a, b, area, p in road_overlaps(m):
        c.failures.append(f"segments {a.id} ({a.road_class}) and {b.id} ({b.road_class}) "
                          f"overlap by {area:.0f} m2 at ({p.x:.0f}, {p.y:.0f})")
    return c


def _bridge_parts(m: CityModel) -> list[tuple]:
    """(bridge or line id, part id, kind, plan polygon, z at a point, deck depth, end nodes,
    centerline) of every bridge's segments (road and pedestrian, approaches included) and
    every transit deck or tube over water."""
    out = []
    segs = {s.id: s for s in m.road_segments}
    for b in m.bridges:
        kind = "pedestrian" if b.bridge_class == "pedestrian" else "road"
        for sid in b.segment_ids:
            s = segs.get(sid)
            if s is None:
                continue
            line = LineString(s.centerline)
            poly = line.buffer(s.width_m / 2, cap_style="flat")
            out.append((b.id, sid, kind, poly, (lambda p, s=s, ln=line: surface_z(s, ln, p)),
                        DECK_M[kind], {s.start, s.end}, line))
    water = _water(m)
    if water is None:
        return out
    for st in m.structures:
        if st.kind not in ("deck", "tube") or "line_id" not in st.attrs or len(st.line) < 2:
            continue
        line = LineString([(x, y) for x, y, _ in st.line])
        if not line.intersects(water):
            continue
        zs = [z for _, _, z in st.line]
        poly = line.buffer(st.attrs.get("width_m", 6.0) / 2, cap_style="flat")

        def z_of(p, line=line, zs=zs, pts=st.line):
            s = line.project(p)
            acc = 0.0
            for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:]):
                d = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
                if acc + d >= s:
                    return z0 + (z1 - z0) * ((s - acc) / d if d else 0.0)
                acc += d
            return zs[-1]
        out.append((st.attrs["line_id"], st.id, "transit", poly, z_of,
                    st.attrs.get("deck_m", 2.0), set(), line))
    return out


def check_bridge_clash(spec: CitySpec, m: CityModel):
    c = _check("bridge_clash", "Road, pedestrian and transit bridges keep their decks and "
                               "approaches apart in plan, or the lower one's clearance under the "
                               "upper deck")
    parts = _bridge_parts(m)
    if len(parts) < 2:
        return c
    tree = shapely.STRtree([x[3] for x in parts])
    a_idx, b_idx = tree.query([x[3] for x in parts], predicate="intersects")
    seen = set()
    for i, j in sorted(zip(a_idx.tolist(), b_idx.tolist())):
        a, b = parts[i], parts[j]
        if j <= i or a[0] == b[0] or (a[0], b[0]) in seen or a[6] & b[6]:
            continue
        ov = _inter(a[3], b[3])
        if ov.area <= BRIDGE_M2:
            continue
        # (where the two cross, else in the overlap)
        pts = [q for q in shapely.get_parts(a[7].intersection(b[7])) if q.geom_type == "Point"]
        p = pts[0] if pts else ov.representative_point()
        za, zb = a[4](p), b[4](p)
        lo, hi = (a, b) if za <= zb else (b, a)
        need = CLEAR_UNDER_M[lo[2]] + hi[5]
        if abs(za - zb) < need - CLEAR_TOL_M:
            seen.add((a[0], b[0]))
            c.failures.append(f"bridges {a[0]} ({a[2]}, {a[1]}) and {b[0]} ({b[2]}, {b[1]}) "
                              f"overlap by {ov.area:.0f} m2 at ({p.x:.0f}, {p.y:.0f}), "
                              f"{abs(za - zb):.1f} m apart in height (needs {need:g} m)")
    return c


def check_building_clash(spec: CitySpec, m: CityModel):
    c = _check("road_building_clash", "No road, sidewalk, ramp or deck street right of way over "
                                      "a building mass at the road's own height (the mass "
                                      f"under it, or {HEADROOM_M:g} m over it, clears)")
    segs = m.road_segments
    if not segs or not m.buildings:
        return c
    lines, rows = _rows(m)
    masses = []
    for b in m.buildings:
        base = b.base_m or 0.0
        for k, ms in enumerate(b.masses):
            masses.append((b, k, G.from_model_poly(ms.footprint), base + ms.z0_m,
                           base + ms.z1_m, ms.shape))
    tree = shapely.STRtree([x[2] for x in masses])
    a_idx, b_idx = tree.query(rows, predicate="intersects")
    for i, k in sorted(zip(a_idx.tolist(), b_idx.tolist())):
        b, mk, fp, z0, z1, shape = masses[k]
        ov = _inter(rows[i], fp)
        if ov.area <= MASS_M2:
            continue
        z = surface_z(segs[i], lines[i], ov.representative_point())
        if shape == "ring":
            z0 = _rim_low(fp, ov, z0, z1)
        head = PATH_HEADROOM_M if segs[i].road_class in ST.PEDESTRIAN else HEADROOM_M
        if z0 < z + head and z1 > z + 0.5:
            c.failures.append(f"segment {segs[i].id} ({segs[i].road_class}) runs through "
                              f"building {b.id} (mass {mk}, {z0:.1f} to {z1:.1f} m) over "
                              f"{ov.area:.0f} m2 at {z:.1f} m")
    return c


def _rim_low(fp, ov, z0: float, z1: float) -> float:
    """A vertical wheel's (`Mass.shape` ring) lowest rim height over the part ov of its plan:
    the rim is a circle from z0 to z1 over the footprint's long middle line."""
    r = (z1 - z0) / 2.0
    c = fp.centroid
    d = min(Point(q).distance(c) for q in list(shapely.get_coordinates(ov)) +
            [(ov.centroid.x, ov.centroid.y)])
    return z0 + r - (max(r * r - d * d, 0.0)) ** 0.5


def run_streets(spec: CitySpec, m: CityModel) -> list:
    """The checks a city with local streets has (M2 on)."""
    return [check_dead_ends(spec, m), check_overlaps(spec, m)]


def run_finished(spec: CitySpec, m: CityModel) -> list:
    """The checks that need the buildings and the transit structures (M3 and M5 on)."""
    return [check_bridge_clash(spec, m), check_building_clash(spec, m)]
