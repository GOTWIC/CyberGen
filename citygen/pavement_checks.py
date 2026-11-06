"""M22: the pavement map's checks, the proof obligations of its invariants
(docs/assetgen_scope.md 14.18); on a correct build they never fail.

- `pavement_edges`: every face's boundary is a closed chain of stored edges; every edge
  that is not the right of way's outer edge lies in exactly two faces, run in opposite
  directions, the outer ones in one; no segment is stored in two edges.
- `pavement_tiling`: every face is a simple polygon; no two faces overlap where they are at
  one level (an overpass over a road, a tunnel under it, may); no gap inside the pavement
  (a hole of the right of way smaller than `GAP_M2`).
- `pavement_heights`: one height per vertex; every port level across its road; every
  junction, corner, bulb and bend face, drawn from its boundary and samples, within its
  roads' grade.
- `pavement_junctions`: invariant 5: the slope between any two of a junction's ports (their
  heights over the least distance between them) within the grade of its roads.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import Polygon

from . import pavement as PV
from . import pavetri as PT
from .checks import Check

SHOW = 12
GAP_M2 = 1.0            # a hole in the pavement this small is a gap, not a block
GAP_MIN_M2 = 1e-4       # (smaller: the union's own rounding of edges the map shares)
OVERLAP_MIN_M2 = 1e-3   # (smaller: two faces' corners rounded onto the 1 mm grid apart)
SAME_Z_M = 2.5          # two faces this near in height where they overlap are one level
LEVEL_TOL_M = 0.0015    # a port's vertices within this of one height (stored to 1 mm)
GRADE_TOL = 0.005       # rounding: heights to 1 mm over short triangle sides
MIN_TRI_M2 = 0.25       # triangles smaller than this are left out of the grade test
JUNCTION_KINDS = ("junction", "corner", "bulb", "bend")
ROAD_KINDS = ("carriageway", "median", "curb", "sidewalk", "walk")


def _lim(c: Check, msg: str) -> None:
    if len(c.failures) < SHOW:
        c.failures.append(msg)
    elif len(c.failures) == SHOW:
        c.failures.append("...")


class Net:
    """The map of a model: vertex positions and heights over sea level, edges, every face's
    rings as vertex ids."""

    def __init__(self, m):
        from . import terrain as TE

        self.m = m
        net = m.pavement_net
        g = TE.ground_of(m)
        self.vert = {}
        for v in net.vertices:
            gz = g.at(v.p[0], v.p[1]) if g is not None else 0.0
            self.vert[v.id] = (v.p, v.z + gz)
        self.dup_vertices = len(net.vertices) - len(self.vert)
        self.edge = {e.id: e for e in net.edges}
        self.dup_edges = len(net.edges) - len(self.edge)
        self.faces = list(m.pavement)
        self.rings: dict = {}
        self.bad: dict = {}
        for f in self.faces:
            rs = []
            for refs in f.rings:
                r, why = self.chain(refs)
                if why:
                    self.bad[f.id] = why
                    break
                rs.append(r)
            self.rings[f.id] = rs

    def chain(self, refs) -> tuple[list, str | None]:
        out = []
        for k, ref in enumerate(refs):
            fwd = not ref.startswith("-")
            e = self.edge.get(ref if fwd else ref[1:])
            if e is None:
                return [], f"edge {ref} missing"
            vs = list(e.v) if fwd else list(e.v)[::-1]
            if any(v not in self.vert for v in vs):
                return [], f"edge {e.id} names a vertex that is missing"
            if out and out[-1] != vs[0]:
                return [], f"edges {refs[k - 1]} and {ref} do not meet"
            out += vs if not out else vs[1:]
        if not out or out[0] != out[-1]:
            return [], "its boundary is not closed"
        return out[:-1], None

    def xy(self, vid):
        return self.vert[vid][0]

    def z(self, vid) -> float:
        return self.vert[vid][1]

    def poly(self, fid) -> Polygon:
        rs = self.rings[fid]
        return Polygon([self.xy(v) for v in rs[0]], [[self.xy(v) for v in r] for r in rs[1:]])


def _grades(spec, m) -> tuple[dict, float]:
    """The steepest grade a face may have, by road class: M13's class grades (highway 6%,
    avenue 8%, street 12%, alley 15%), never less than M18's ramp maximum."""
    from . import terrain as TE

    cap = spec.highways.grades.ramp_max
    return {k: max(v, cap) for k, v in TE.MAX_GRADE.items()}, cap


def _owner_roads(N: Net) -> dict:
    """Owner id (junction) -> the road segments its faces meet at their ports."""
    face_of = {}
    for f in N.faces:
        for refs in f.rings:
            for ref in refs:
                face_of.setdefault(ref.lstrip("-"), []).append(f)
    out: dict = {}
    for eid, fs in face_of.items():
        e = N.edge.get(eid)
        if e is None or e.kind != "port":
            continue
        own = {f.owner_id for f in fs}
        roads = {f.owner_id for f in fs if f.kind in ROAD_KINDS}
        for o in own - roads:
            out.setdefault(o, set()).update(roads)
    return out


def check_edges(spec, m) -> Check:
    c = Check("pavement_edges", "M22: every pavement face's boundary is a closed chain of "
                                "stored edges; every edge but the right of way's outer edge "
                                "lies in exactly two faces, run in opposite directions, an "
                                "outer edge in one; no segment stored twice")
    if m.pavement_net is None:
        return c
    N = Net(m)
    if N.dup_vertices or N.dup_edges:
        _lim(c, f"{N.dup_vertices} vertex ids and {N.dup_edges} edge ids stored twice")
    for fid, why in sorted(N.bad.items()):
        _lim(c, f"face {fid}: {why}")
    uses: dict = {}
    for f in N.faces:
        if f.id in N.bad:
            continue
        for refs in f.rings:
            for ref in refs:
                uses.setdefault(ref.lstrip("-"), []).append((f.id, not ref.startswith("-")))
    for eid, e in sorted(N.edge.items()):
        u = uses.get(eid, [])
        if e.kind == "outer":
            if len(u) != 1:
                _lim(c, f"outer edge {eid} in {len(u)} faces")
        elif len(u) != 2 or u[0][0] == u[1][0] or u[0][1] == u[1][1]:
            _lim(c, f"{e.kind} edge {eid} in {len(u)} faces "
                    f"({', '.join(sorted(x[0] for x in u))})")
    seen: dict = {}
    for eid, e in N.edge.items():
        vs = list(e.v)
        for a, b in zip(vs, vs[1:]):
            if a == b:
                _lim(c, f"edge {eid}: vertex {a} twice in a row")
                continue
            key = (min(a, b), max(a, b))
            if key in seen and seen[key] != eid:
                _lim(c, f"segment {a} to {b} in edges {seen[key]} and {eid}")
            seen[key] = eid
    for f in N.faces:
        rs = N.rings.get(f.id) or []
        for k, r in enumerate(rs):
            if len(r) < 3:
                _lim(c, f"face {f.id}: a ring of {len(r)} vertices")
                continue
            a = _area2([N.xy(v) for v in r])
            if (k == 0 and a <= 0) or (k > 0 and a >= 0):
                _lim(c, f"face {f.id}: ring {k} runs the wrong way round")
    return c


def _area2(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        s += pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
    return s


def _near_z(N: Net, fid: str, x: float, y: float) -> float:
    best = None
    for r in N.rings[fid]:
        for v in r:
            p = N.xy(v)
            d = (p[0] - x) ** 2 + (p[1] - y) ** 2
            if best is None or d < best[0]:
                best = (d, N.z(v))
    return best[1] if best else 0.0


def check_tiling(spec, m) -> Check:
    c = Check("pavement_tiling", f"M22: every pavement face a simple polygon; no two faces "
                                 f"overlap where they are within {SAME_Z_M:g} m in height "
                                 f"(one over the other, an overpass, may); no hole in the "
                                 f"pavement under {GAP_M2:g} m2 (a gap); every face on its "
                                 f"owner's right of way (a road's half width, a junction's "
                                 f"legs out to their cuts)")
    if m.pavement_net is None:
        return c
    N = Net(m)
    ids = [f.id for f in N.faces if f.id not in N.bad and N.rings.get(f.id)]
    geoms = []
    for fid in ids:
        g = N.poly(fid)
        if not g.is_valid:
            _lim(c, f"face {fid}: not a simple polygon ({shapely.is_valid_reason(g)})")
            g = g.buffer(0)
        geoms.append(g)
    if not geoms:
        return c
    arr = np.array(geoms, dtype=object)
    tree = shapely.STRtree(arr)
    a, b = tree.query(arr, predicate="intersects")
    keep = a < b
    a, b = a[keep], b[keep]
    n_over = 0
    if len(a):
        rel = shapely.relate_pattern(arr[a], arr[b], "2********")
        for i, j in zip(a[rel].tolist(), b[rel].tolist()):
            ov = shapely.intersection(arr[i], arr[j])
            if ov.area < OVERLAP_MIN_M2:
                continue
            p = ov.representative_point()
            if abs(_near_z(N, ids[i], p.x, p.y) - _near_z(N, ids[j], p.x, p.y)) > SAME_Z_M:
                n_over += 1
                continue
            _lim(c, f"faces {ids[i]} and {ids[j]} overlap ({ov.area:.4f} m2 at "
                    f"({p.x:.1f}, {p.y:.1f}))")
    layer = {f.id: f.layer for f in N.faces}
    for lv in sorted({layer[i] for i in ids}):
        u = shapely.union_all([g for i, g in zip(ids, geoms) if layer[i] == lv],
                              grid_size=0.001)
        for g in [u] if u.geom_type == "Polygon" else list(getattr(u, "geoms", [])):
            if g.geom_type != "Polygon":
                continue
            for h in g.interiors:
                hp = Polygon(h)
                if GAP_MIN_M2 <= hp.area < GAP_M2:
                    q = hp.representative_point()
                    _lim(c, f"a gap of {hp.area:.4f} m2 in the pavement ({lv}) at "
                            f"({q.x:.1f}, {q.y:.1f})")
    if n_over:
        c.notes.append(f"{n_over} overlaps of faces one over the other (overpasses, tunnels)")
    _on_owner(c, m, N, ids)
    return c


def _on_owner(c: Check, m, N: Net, ids: list) -> None:
    """Every face on its owner's ground: a road's within its half width (and ON_OWNER_M)
    of its centerline; a junction's within its legs' cuts and half widths (a bulb's radius)
    of its nodes, or on a cluster's inner roads."""
    from shapely.geometry import LineString, Point

    seg = {s.id: s for s in m.road_segments if len(s.centerline) >= 2}
    line = {sid: LineString([p[:2] for p in s.centerline]) for sid, s in seg.items()}
    node = {n.id: n for n in m.road_nodes}
    at: dict = {}
    for s in m.road_segments:
        cuts = s.attrs.get("cuts") or [0.0, 0.0]
        at.setdefault(s.start, []).append(cuts[0] + s.width_m / 2.0)
        at.setdefault(s.end, []).append(cuts[1] + s.width_m / 2.0)
    reach: dict = {}
    for j in m.junctions:
        disks = []
        for nid in j.attrs.get("nodes") or [j.node_id]:
            n = node.get(nid)
            if n is not None:
                head = (n.attrs.get("turning_head_m") or 0.0) + 6.0
                disks.append((Point(n.position[:2]), max(at.get(nid, []) + [head])))
        strips = [(line[i], seg[i].width_m / 2.0) for i in j.attrs.get("inner") or []
                  if i in line]
        reach[j.id] = (disks, strips)
    by_id = {f.id: f for f in N.faces}
    for fid in ids:
        f = by_id[fid]
        pts = shapely.points([N.xy(v) for v in N.rings[fid][0]])
        if f.owner_id in line:
            ok = shapely.distance(pts, line[f.owner_id]) <=                 seg[f.owner_id].width_m / 2.0 + ON_OWNER_M
        elif f.owner_id in reach:
            disks, strips = reach[f.owner_id]
            ok = np.zeros(len(pts), dtype=bool)
            for P, r in disks:
                ok |= shapely.distance(pts, P) <= r + ON_OWNER_M
            for ln, h in strips:
                ok |= shapely.distance(pts, ln) <= h + ON_OWNER_M
        else:
            continue
        if not bool(np.all(ok)):
            k = int(np.argmin(ok))
            q = N.xy(N.rings[fid][0][k])
            _lim(c, f"face {fid} ({f.kind}) reaches off its owner's right of way at "
                    f"({q[0]:.1f}, {q[1]:.1f})")


ON_OWNER_M = 1.0        # a face may reach this far past its owner's right of way


def _tri_grade(p, q, r) -> tuple[float, float]:
    """(grade, plan area) of a 3D triangle."""
    ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
    vx, vy, vz = r[0] - p[0], r[1] - p[1], r[2] - p[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    if abs(nz) < 1e-12:
        return math.inf, 0.0
    return math.sqrt(nx * nx + ny * ny) / abs(nz), abs(nz) / 2.0


def face_triangles(N: Net, f) -> list:
    """A face's triangles in 3D (sea level heights): its boundary, its samples."""
    rings = [[(int(round(N.xy(v)[0] * 1000)), int(round(N.xy(v)[1] * 1000))) for v in r]
             for r in N.rings[f.id]]
    zs = {}
    for r in N.rings[f.id]:
        for v in r:
            p = N.xy(v)
            zs[(int(round(p[0] * 1000)), int(round(p[1] * 1000)))] = N.z(v)
    from . import terrain as TE

    g = TE.ground_of(N.m)
    smp = []
    for x, y, z in f.samples:
        k = (int(round(x * 1000)), int(round(y * 1000)))
        zs[k] = z + (g.at(x, y) if g is not None else 0.0)
        smp.append(k)
    pts, tris = PT.triangulate(rings, smp)
    return [tuple((pts[i][0] / 1000.0, pts[i][1] / 1000.0, zs[pts[i]]) for i in t)
            for t in tris]


def face_grade(N: Net, f) -> float:
    """The steepest a face's surface is: along its boundary (vertex to vertex), between
    neighboring interior samples (SAMPLE_M apart), and from every sample to the boundary
    vertices within SAMPLE_M of it; a face with no samples is the plane its boundary lies
    on (or its boundary alone where that is not planar)."""
    worst = 0.0
    pts = []
    for r in N.rings[f.id]:
        k = len(r)
        for i in range(k):
            a, b = N.xy(r[i]), N.xy(r[(i + 1) % k])
            d = math.dist(a, b)
            pts.append((a[0], a[1], N.z(r[i])))
            if d >= 0.25:
                dz = abs(N.z(r[i]) - N.z(r[(i + 1) % k]))
                worst = max(worst, (dz - PV.step_tol(d)) / d)
    if not f.samples:
        if len(pts) >= 3:
            p0 = pts[0]
            p1 = max(pts, key=lambda p: (p[0] - p0[0]) ** 2 + (p[1] - p0[1]) ** 2)
            p2 = max(pts, key=lambda p: abs((p[0] - p0[0]) * (p1[1] - p0[1]) -
                                            (p[1] - p0[1]) * (p1[0] - p0[0])))
            g, a = _tri_grade(p0, p1, p2)
            if a > 1.0:
                worst = max(worst, g)
        return worst
    from . import terrain as TE

    gr = TE.ground_of(N.m)
    smp = {}
    for x, y, z in f.samples:
        smp[(round(x / SAMPLE_M), round(y / SAMPLE_M))] = (x, y, z + (gr.at(x, y) if gr is
                                                                    not None else 0.0))
    import numpy as np

    poly = N.poly(f.id)
    shapely.prepare(poly)
    pairs = []
    for (i, j), (x, y, z) in smp.items():
        for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
            o = smp.get((i + di, j + dj))
            if o is not None:
                pairs.append(((x, y, z), o))
    if pts:
        P = np.array(pts)
        for x, y, z in smp.values():
            d = np.sqrt((P[:, 0] - x) ** 2 + (P[:, 1] - y) ** 2)
            for k in np.nonzero((d <= SAMPLE_M) & (d >= 0.25))[0].tolist():
                pairs.append(((x, y, z), tuple(P[k])))
    if pairs:
        # (only across the face: two points either side of a notch are far apart in it)
        segs = shapely.linestrings([[a[:2], b[:2]] for a, b in pairs])
        ok = shapely.covers(poly.buffer(0.01), segs)
        for (a, b), inside in zip(pairs, ok.tolist()):
            if inside:
                worst = max(worst, (abs(a[2] - b[2]) - 0.002) / math.dist(a[:2], b[:2]))
    return worst


SAMPLE_M = 2.0          # the map's interior sample grid (`pavement.SAMPLE_M`)


def check_heights(spec, m) -> Check:
    c = Check("pavement_heights", "M22: one height per pavement vertex; every port level "
                                  "across its road; every junction, corner pad, bulb and "
                                  "bend face, drawn from its boundary and samples, within "
                                  "the grade of its roads (M13's class grades, at least "
                                  "M18's ramp maximum; a junction the levelling keeps as M18 "
                                  "left it noted)")
    if m.pavement_net is None:
        return c
    N = Net(m)
    if N.dup_vertices:
        _lim(c, f"{N.dup_vertices} vertices stored twice")
    for eid, e in sorted(N.edge.items()):
        if e.kind != "port":
            continue
        zs = [N.z(v) for v in e.v]
        if max(zs) - min(zs) > LEVEL_TOL_M:
            _lim(c, f"port {eid}: {min(zs):.3f} to {max(zs):.3f} m across")
    held = {j.id: j.attrs["unbuildable"] for j in m.junctions if j.attrs.get("unbuildable")}
    # (and the faces of a junction beside one, sharing its vertices: its heights reach them)
    held_v = {v for f in N.faces if f.owner_id in held for r in N.rings.get(f.id, []) for v in r}
    steep = 0.0
    noted = set()
    for f, worst, lim in face_slopes(spec, m, N):
        if worst > lim + GRADE_TOL:
            if f.owner_id in held or any(v in held_v for r in N.rings[f.id] for v in r):
                noted.add(f.owner_id)     # (held as M18 left it: `pavement_junctions`)
                continue
            _lim(c, f"face {f.id} ({f.kind}): {worst:.1%} steep (its roads {lim:.0%})")
        steep = max(steep, worst)
    c.notes.append(f"steepest junction face {steep:.1%}")
    if noted:
        c.notes.append(f"{len(noted)} junctions held as M18 left them, or beside one (what "
                       f"holds each: `pavement_junctions`), with faces steeper than their "
                       f"roads: {', '.join(sorted(noted)[:SHOW])}")
    return c


def face_slopes(spec, m, N: Net | None = None) -> list[tuple]:
    """(face, its steepest slope, its limit) of every junction, corner pad, bulb and bend
    face: a junction's limit the steepest class grade of its roads (M13's, at least M18's
    ramp maximum), a bend's BEND_FACTOR times its road's (its inner edge climbs over a
    shorter run than its centerline)."""
    N = N or Net(m)
    by_class, cap = _grades(spec, m)
    cls = {s.id: s.road_class for s in m.road_segments}
    roads = _owner_roads(N)
    out = []
    for f in N.faces:
        if f.kind not in JUNCTION_KINDS or f.id in N.bad or not N.rings.get(f.id):
            continue
        if f.kind == "bend":
            lim = BEND_FACTOR * by_class.get(cls.get(f.owner_id), cap)
        else:
            lim = max([by_class.get(cls.get(r), cap) for r in roads.get(f.owner_id, ())] or
                      [cap])
        out.append((f, face_grade(N, f), lim))
    return out


def drawn_steep(spec, m) -> dict:
    """{junction id: its steepest face} of the junctions not yet held whose faces the map
    draws steeper than their grade."""
    held = {j.id for j in m.junctions if j.attrs.get("unbuildable")}
    jids = {j.id for j in m.junctions}
    out: dict = {}
    for f, worst, lim in face_slopes(spec, m):
        if f.owner_id in jids and f.owner_id not in held and worst > lim + GRADE_TOL:
            out[f.owner_id] = max(out.get(f.owner_id, 0.0), round(worst, 3))
    return out


BEND_FACTOR = 1.25      # a bend face's limit: this times its road's grade


def _seg_dist(p, q, a, b) -> float:
    def d(pt, s0, s1):
        dx, dy = s1[0] - s0[0], s1[1] - s0[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((pt[0] - s0[0]) * dx +
                                                   (pt[1] - s0[1]) * dy) / L2))
        x, y = s0[0] + t * dx - pt[0], s0[1] + t * dy - pt[1]
        return math.sqrt(x * x + y * y)
    from .pavetri import _cross

    if _cross(p, q, a, b):
        return 0.0
    return min(d(p, a, b), d(q, a, b), d(a, p, q), d(b, p, q))


def junction_slopes(spec, m) -> list[tuple]:
    """Per junction face: (face, road a, z a, road b, z b, distance, slope, limit) for every
    pair of its ports (heights the mean of each port's vertices)."""
    N = Net(m)
    by_class, cap = _grades(spec, m)
    cls = {s.id: s.road_class for s in m.road_segments}
    face_of: dict = {}
    for f in N.faces:
        for refs in f.rings:
            for ref in refs:
                face_of.setdefault(ref.lstrip("-"), []).append(f)
    out = []
    for f in N.faces:
        if f.kind not in ("junction", "bulb") or f.id in N.bad:
            continue
        ports: dict = {}
        for refs in f.rings:
            for ref in refs:
                eid = ref.lstrip("-")
                e = N.edge.get(eid)
                if e is None or e.kind != "port":
                    continue
                other = [g for g in face_of.get(eid, []) if g.id != f.id]
                if not other or other[0].kind not in ROAD_KINDS:
                    continue
                ports.setdefault(other[0].owner_id, []).append(list(e.v))
        keys = sorted(ports)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                ra, rb = keys[i], keys[j]
                za = [N.z(v) for ch in ports[ra] for v in ch]
                zb = [N.z(v) for ch in ports[rb] for v in ch]
                z1, z2 = sum(za) / len(za), sum(zb) / len(zb)
                d = math.inf
                for ca in ports[ra]:
                    for cb in ports[rb]:
                        for p, q in zip(ca, ca[1:]):
                            for a, b in zip(cb, cb[1:]):
                                d = min(d, _seg_dist(N.xy(p), N.xy(q), N.xy(a), N.xy(b)))
                lim = max(by_class.get(cls.get(r), cap) for r in keys)
                slope = abs(z1 - z2) / max(d, 0.5)
                out.append((f.id, ra, z1, rb, z2, d, slope, lim))
    return out


def check_junctions(spec, m) -> Check:
    c = Check("pavement_junctions", "M22: every junction is buildable: the slope between any "
                                    "two of its ports (their height difference over the least "
                                    "distance between them across it) within the grade of its "
                                    "roads (M13's class grades, at least M18's ramp maximum); "
                                    "a junction the levelling can make so only by moving a "
                                    "bridge span, a fixed road or M7's local junction limit is "
                                    "kept as M18 left it and noted with what holds it")
    if m.pavement_net is None:
        return c
    worst = 0.0
    held = {j.id: j.attrs["unbuildable"] for j in m.junctions if j.attrs.get("unbuildable")}
    noted: dict = {}
    for fid, ra, za, rb, zb, d, slope, lim in junction_slopes(spec, m):
        if slope > lim + GRADE_TOL:
            jid = fid.split(".pv.")[0]
            if jid in held:
                noted[jid] = max(noted.get(jid, 0.0), slope)
                continue
            _lim(c, f"{fid}: ports of {ra} at {za:.2f} m and {rb} at {zb:.2f} m, {d:.1f} m "
                    f"apart: {slope:.1%} (its roads {lim:.0%})")
        worst = max(worst, slope)
    c.notes.append(f"steepest between two ports of a junction {worst:.1%}")
    # (a junction the levelling cannot make buildable without moving what it may not move:
    # a bridge's locked approach, a fixed road, M7's limit for a local junction)
    from .junctions import why_text

    for jid in sorted(noted):
        c.notes.append(f"{jid}: {noted[jid]:.1%} between ports, held as M18 left it by "
                       f"{why_text(held[jid])}")
    return c


def run(spec, m) -> list[Check]:
    if m.pavement_net is None:
        return []
    return [check_edges(spec, m), check_tiling(spec, m), check_heights(spec, m),
            check_junctions(spec, m)]


def stats(m) -> dict:
    if m.pavement_net is None:
        return {}
    kinds: dict = {}
    for f in m.pavement:
        kinds[f.kind] = kinds.get(f.kind, 0) + 1
    ek: dict = {}
    for e in m.pavement_net.edges:
        ek[e.kind] = ek.get(e.kind, 0) + 1
    return {"faces": len(m.pavement), "faces_by_kind": dict(sorted(kinds.items())),
            "vertices": len(m.pavement_net.vertices), "edges": len(m.pavement_net.edges),
            "edges_by_kind": dict(sorted(ek.items())),
            "samples": sum(len(f.samples) for f in m.pavement)}
