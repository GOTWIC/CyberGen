"""What the props stage reads from a city: every prop, plant and sign slot, with its
district's style, its variant, its instance transform, and for the meshes made per tile
(exact props, signs) the canonical inputs their makers read.

- **Props**: kind, district style (the id's district, else the district under it), variant
  by a hash of the id; awnings and scaffolding turned so their wall is on the side the
  frames in `variants.py` expect (the side nearer their building's footprint); AC units and
  wall lights the brief finds off their wall get a bracket of that length
  (`brief.mount_props`: `gap_m`); M6's highway median barriers are dropped where AG7's road
  piece has its continuous barrier (scope 5.3; AG7's notes).
- **Plants**: species (M6's, else its type's), variant by a hash of the id, scaled to the
  plant's crown and height; facade greenery split into patches of about 1.5 m along its
  length (awnings likewise into segments of about 2 m).
- **Signs**: per slot AG6's text, script, style and colors (`materials/signage.py`, the
  same draw its sign pages make), the page cell that shows it when the city's pages are made
  (`BUILD/assets/signs.json`), the body AG8 makes it as and the gap to its wall.
- **Ground** (M13): a model z is measured from the ground where it stands, so every
  placement is lifted by its building's `base_m` when it hangs on a building or stands on
  its roof (AG1's shells stand there), else by the finished ground at its point (as the
  blockout lifts M15's instances); nothing on a flat city. A boat (its waterline at its z)
  floats on M16's water (AG12: the body's surface, 1.5 m under the ground on a flat city).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import shapely

from citygen import dmath as M
from citygen import geom as G

from .. import canon as C
from ..streets.ctx import Ground
from . import materials as MT
from . import styles as ST
from .build import tile_center, tile_of
from .trees import BASE
from .variants import REACH

IVY_PATCH_M = 1.5
AWNING_SEGMENT_M = 2.0
BRACKET_MIN_M = 0.02


@dataclass
class Gathered:
    families: list = field(default_factory=list)       # [(what, name)]
    groups: dict = field(default_factory=dict)         # blockout key -> group
    exact: dict = field(default_factory=dict)          # tile -> [(key, kind, items)]
    signs: dict = field(default_factory=dict)          # tile -> [sign]
    dropped: dict = field(default_factory=dict)        # prop id -> reason
    covered: dict = field(default_factory=dict)        # prop id -> how
    stats: dict = field(default_factory=dict)
    kinds: dict = field(default_factory=dict)          # prop kind -> count in the model
    species: dict = field(default_factory=dict)        # species -> count


class _Districts:
    def __init__(self, m):
        self.d = {d.id: d for d in m.districts}
        self.order = sorted(self.d)
        with G.canonical():
            self.polys = [G.from_model_poly(self.d[i].polygon) for i in self.order]
        self.tree = shapely.STRtree(self.polys) if self.polys else None

    def of(self, eid: str, x: float, y: float) -> str | None:
        head = eid.split(".", 1)[0]
        if head in self.d:
            return head
        if self.tree is None:
            return None
        hit = self.tree.query(shapely.points(x, y), predicate="intersects")
        return self.order[min(hit.tolist())] if len(hit) else None


def _wall_plus_y(poly, x: float, y: float, yaw: float, reach: float) -> bool:
    """Whether a facade thing's wall is on its local +y side: the point that far to its left
    is nearer the footprint than the point to its right."""
    a = M.radians(yaw)
    lx, ly = -M.sin(a), M.cos(a)
    if poly is None:
        return True
    dp = poly.distance(shapely.points(x + lx * reach, y + ly * reach))
    dm = poly.distance(shapely.points(x - lx * reach, y - ly * reach))
    return dp <= dm


FIT_CLEAR_M = 0.05      # a prop's footprint reaches at most this onto a carriageway
FIT_LOW_M = 2.0         # its footprint: what of it is this low (AG14's `PROP_LOW_M`)
FIT_Z_M = 1.5           # a road or junction counts within this of the prop's height
FIT_SKIP = ("parked_vehicle", "barrier")     # on a carriageway by design
# what does not stand on its feet (as AG14's `fit.build.NOT_STANDING`: mounted, hung, afloat,
# drawn whole as an exact mesh)
NOT_STANDING = {"awning", "wall_light", "ac_unit", "overhead_cable", "cable", "boat", "sign",
                "scaffolding", "bracket", "neon", "gate", "facade_greenery", "shop_sign",
                "blade_sign", "billboard", "holo_ad", "neon_band", "string_lights"}


class _Fit:
    """#95: whether a standing prop's variant stands clear of every vehicle carriageway
    (AG7 paves it between the curbs), junction and crosswalk at its height (a traffic
    signal at its crosswalk's end by design): its footprint (the variant's vertices up to
    `FIT_LOW_M` over its foot, their convex hull, turned and scaled as placed) reaches at
    most `FIT_CLEAR_M` onto one. Variants are made once to measure them."""

    def __init__(self, model, paved=()):
        from ..streets.roads import street_class
        shapes, rows = [], []
        node_z = {n.id: n.position[2] for n in model.road_nodes}
        legs: dict = defaultdict(list)
        for s in model.road_segments:
            legs[s.start].append(s)
            legs[s.end].append(s)
        car = ("pedestrian", "footbridge")
        with G.canonical():
            for j in model.junctions:
                if all(street_class(s) in car for n in j.attrs.get("nodes") or [j.node_id]
                       for s in legs.get(n, ())):
                    continue
                shapes.append(G.from_model_poly(j.polygon))
                rows.append(("junction", None, node_z.get(j.node_id, 0.0)))
            # (M22: every node of a cluster is its junction's)
            jring = {n: [list(p) for p in j.polygon.exterior] for j in model.junctions
                     for n in j.attrs.get("nodes") or [j.node_id]}
            for s in model.road_segments:
                if street_class(s) in car or len(s.centerline) < 2:
                    continue
                poly = _carriageway(s, street_class(s), jring)
                if poly is None:
                    continue
                ln = shapely.LineString([(p[0], p[1]) for p in s.centerline])
                shapes.append(poly)
                rows.append(("road", ln, [(z.s, z.z) for z in s.z_profile]))
            # (#82: the connector lanes' runs AG7 paves past a junction's outline)
            for ring in paved:
                if len(ring) < 3:
                    continue
                g = shapely.Polygon([(q[0], q[1]) for q in ring])
                shapes.append(g if g.is_valid else shapely.make_valid(g))
                rows.append(("junction", None, sum(q[2] for q in ring) / len(ring)))
            seg = {s.id: s for s in model.road_segments}
            for c in model.crosswalks:
                s = seg.get(c.segment_id)
                if s is None:
                    continue
                ln = shapely.LineString([(p[0], p[1]) for p in c.line])
                shapes.append(ln.buffer(c.width_m / 2.0, cap_style="flat"))
                rows.append(("xwalk", shapely.LineString([(p[0], p[1]) for p in s.centerline]),
                             [(z.s, z.z) for z in s.z_profile]))
        with G.canonical():
            self.shapes = [G.qpoly(g.buffer(-FIT_CLEAR_M)) for g in shapes]
        self.rows = rows
        self.tree = shapely.STRtree(self.shapes) if shapes else None
        self.hulls: dict = {}

    def hull(self, kind: str, style: str, k: int) -> list | None:
        key = (kind, style, k)
        if key not in self.hulls:
            from .variants import make
            m = make(kind, style, k)
            pts = [p for sl in m.slots.values() for p in sl.pos]
            if not pts:
                self.hulls[key] = None
            else:
                z0 = min(p[2] for p in pts)
                low = [(p[0] / 1000.0, p[1] / 1000.0) for p in pts
                       if p[2] <= z0 + FIT_LOW_M * 1000.0]
                h = shapely.convex_hull(shapely.multipoints(low))
                self.hulls[key] = list(h.exterior.coords)[:-1] if h.geom_type == "Polygon" \
                    else None
        return self.hulls[key]

    def clear(self, kind: str, style: str, k: int, x: float, y: float, z: float,
              yaw: float, scale) -> bool:
        if self.tree is None:
            return True
        ring = self.hull(kind, style, k)
        if ring is None:
            return True
        a = M.radians(yaw)
        c, s = M.cos(a), M.sin(a)
        poly = shapely.Polygon([(x + c * u * scale[0] - s * v * scale[1],
                                 y + s * u * scale[0] + c * v * scale[1]) for u, v in ring])
        for gi in sorted(self.tree.query(poly, predicate="intersects").tolist()):
            kind_, ln, zp = self.rows[gi]
            if kind_ == "xwalk" and kind == "traffic_signal":
                continue
            if kind_ == "junction":
                zt = zp
            else:
                zt = _z_along(zp, ln.project(shapely.points(x, y)))
            if abs(zt - z) <= FIT_Z_M:
                return False
        return True


RAISED_Z_M = 1.0        # #89: a thing within this of a raised junction's heights is on it
SEAT_SINK_M = 0.05      # #89: a plant's foot set this far into the ground at its middle


def _foot(feet: dict, sp: str, k: int):
    """A plant variant's foot as AG14 takes it (`fit.build.feet`): the middle of the plan box
    of its lowest vertices and their height, in its frame (m); made once per variant."""
    key = (sp, k)
    if key not in feet:
        from .trees import make
        m = make(sp, k)
        pts = [q for sl in m.slots.values() for q in sl.pos]
        if not pts:
            feet[key] = None
        else:
            z0 = min(q[2] for q in pts)
            low = [q for q in pts if q[2] <= z0 + 10]
            xs, ys = [q[0] for q in low], [q[1] for q in low]
            feet[key] = ((min(xs) + max(xs)) / 2000.0, (min(ys) + max(ys)) / 2000.0,
                         z0 / 1000.0)
    return feet[key]


def _prop_foot(feet: dict, kind: str, style: str, k: int):
    """#89: a prop variant's foot as AG14 takes it: the middle of the plan box of its lowest
    vertices and their height, in its frame (m); made once per variant."""
    key = (kind, style, k)
    if key not in feet:
        from .variants import make
        m = make(kind, style, k)
        pts = [q for sl in m.slots.values() for q in sl.pos]
        if not pts:
            feet[key] = None
        else:
            z0 = min(q[2] for q in pts)
            low = [q for q in pts if q[2] <= z0 + 10]
            xs, ys = [q[0] for q in low], [q[1] for q in low]
            feet[key] = ((min(xs) + max(xs)) / 2000.0, (min(ys) + max(ys)) / 2000.0,
                         z0 / 1000.0)
    return feet[key]


def _seat(gd, feet: dict, sp: str, k: int, x: float, y: float, yaw: float, sc) -> float:
    """#89: the height of a plant on a terrain city's ground (its instance's z): its foot
    (`_foot`, turned and scaled as placed) `SEAT_SINK_M` into the ground under the foot's
    middle. A shrub's foot is its crown's underside, off its pivot, over a hillside green's
    slope: at the ground under its pivot it floated a few centimeters over the slope."""
    f = _foot(feet, sp, k)
    if f is None:
        return C.m(gd.at(x, y))
    u, v, z0 = f
    a = M.radians(yaw)
    c, s = M.cos(a), M.sin(a)
    g = gd.at(x + c * u * sc[0] - s * v * sc[1], y + s * u * sc[0] + c * v * sc[1])
    return C.m(g - SEAT_SINK_M - z0 * sc[2])


def _quay_tops(model, gd) -> dict:
    """#89: per quay, the height of its top at a point as AG7 draws it: the quay piece made
    here from the same inputs (`streets.water.gather_quay`, `make_quay`), the highest of its
    paving and the coping along its edge (rows every 6 m, mitred at the line's bends); off
    them its paving's profile along the line (the ground at the line's vertices, linear
    between them, 2 cm over it)."""
    from ..streets.ctx import Ctx
    from ..streets.path import Path as SPath
    from ..streets.path import Profile
    from ..streets.water import QUAY_PAVE_DZ, gather_quay, make_quay
    out = {}
    cx = Ctx(model) if model.quays else None
    for q in model.quays:
        try:
            P = SPath(q.line)
        except ValueError:
            continue
        gnd = gd.samples(q.line)
        if not gnd or len(gnd) != len(P.p):
            continue
        prof = Profile(list(zip(P.cum, gnd)))
        pc = gather_quay(cx, q)
        o = make_quay(pc.inputs)
        tops = _Tops(o.mesh, pc.inputs.get("origin", (0.0, 0.0)),
                     lambda sn: sn.startswith("paving") or sn == "stone.coping")
        out[q.id] = (lambda x, y, P=P, prof=prof, tops=tops:
                     tops.at(x, y, prof(P.project(x, y)[0]) + QUAY_PAVE_DZ))
    return out


class _Tops:
    """#89: the up-facing triangles of some of a mesh's slots in world meters: the highest
    at a point, else a default."""

    def __init__(self, mesh, origin, keep):
        tris = []
        if mesh is not None:
            for sn, sl in sorted(mesh.slots.items()):
                if not keep(sn):
                    continue
                Q = [(q[0] / 1000.0 + origin[0], q[1] / 1000.0 + origin[1], q[2] / 1000.0)
                     for q in sl.pos]
                for t in range(0, len(sl.idx), 3):
                    a, b, c = Q[sl.idx[t]], Q[sl.idx[t + 1]], Q[sl.idx[t + 2]]
                    d = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                    if d > 1e-9:
                        tris.append((a, b, c, d))
        self.tris = tris
        self.box = [(min(a[0], b[0], c[0]), min(a[1], b[1], c[1]), max(a[0], b[0], c[0]),
                     max(a[1], b[1], c[1])) for a, b, c, _ in tris]

    def at(self, x: float, y: float, default: float) -> float:
        best = None
        for (a, b, c, d), (x0, y0, x1, y1) in zip(self.tris, self.box):
            if not (x0 - 1e-6 <= x <= x1 + 1e-6 and y0 - 1e-6 <= y <= y1 + 1e-6):
                continue
            u = ((b[0] - x) * (c[1] - y) - (b[1] - y) * (c[0] - x)) / d
            v = ((c[0] - x) * (a[1] - y) - (c[1] - y) * (a[0] - x)) / d
            if u >= -1e-9 and v >= -1e-9 and u + v <= 1.0 + 1e-9:
                z = u * a[2] + v * b[2] + (1.0 - u - v) * c[2]
                best = z if best is None else max(best, z)
        return default if best is None else best


class _RaisedCorners:
    """#89: the corners of AG7's raised junctions (`walks.make_junction`'s notes: the
    sectors between its legs and its legs' rights of way from the node to their cuts, its
    carriageway as drawn and the pads it drew there, with their tops). A standing thing
    there, at the junction's height, on neither a carriageway nor a pad nor a sidewalk has
    nothing under it: AG7 leaves a pad out where it would fold over another or the
    junction's lanes or a neighbor's pavement take its place, and draws no corner between
    two twin legs."""

    def __init__(self, notes: list, sidewalks=()):
        self.rows = []
        self.tops = []          # (each row's pads with their heights, for `pad_top`)
        self._tris: dict = {}
        polys = []
        bands = [shapely.LineString(w.line).buffer(w.width_m / 2.0 + 0.05, cap_style="flat")
                 for w in sidewalks if len(w.line) >= 2]
        self.bands = bands
        self.walks = shapely.STRtree(bands) if bands else None
        for rz in notes:
            pads = [p for p in rz.get("pads", ()) if len(p) >= 3]
            zs = [q[2] for p in pads for q in p] + list(rz.get("z", ()))
            area = [shapely.Polygon([(q[0], q[1]) for q in a])
                    for a in list(rz.get("area", ())) + list(rz.get("rows", ())) if len(a) >= 3]
            area = [a if a.is_valid else shapely.make_valid(a) for a in area]
            if not area:
                continue
            car = [shapely.Polygon([(q[0], q[1]) for q in c]) for c in rz.get("carriageway", ())
                   if len(c) >= 3]
            u = shapely.union_all(area)
            polys.append(u)
            self.tops.append(pads)
            self.rows.append((u, [shapely.Polygon([(q[0], q[1]) for q in p]) for p in pads],
                              [c if c.is_valid else shapely.make_valid(c) for c in car],
                              (min(zs), max(zs)) if zs else None))
        self.tree = shapely.STRtree(polys) if polys else None

    def unpaved(self, x: float, y: float, z: float) -> bool:
        if self.tree is None:
            return False
        pt = shapely.points(x, y)
        hit = False
        for k in sorted(self.tree.query(pt, predicate="intersects").tolist()):
            area, pads, car, zr = self.rows[k]
            if zr is not None and not zr[0] - 0.15 - RAISED_Z_M <= z <= zr[1] + RAISED_Z_M:
                continue
            if any(p.intersects(pt) for p in pads) or any(c.intersects(pt) for c in car):
                return False
            hit = True
        if hit and self.walks is not None and len(self.walks.query(pt, predicate="intersects")):
            return False        # (on a sidewalk: AG7 draws it off the carriageways)
        return hit

    def pad_top(self, x: float, y: float, z: float):
        """The height of the corner pad of a raised junction at (x, y), as AG7 triangulates
        it (its vertices at their heights), where the junction is at z; else None."""
        if self.tree is None:
            return None
        pt = shapely.points(x, y)
        for k in sorted(self.tree.query(pt, predicate="intersects").tolist()):
            _, pads, _, zr = self.rows[k]
            if zr is not None and not zr[0] - 0.15 - RAISED_Z_M <= z <= zr[1] + RAISED_Z_M:
                continue
            for i, pg in enumerate(pads):
                if not pg.intersects(pt):
                    continue
                for a, b, c in self._pad_tris(k, i):
                    d = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                    if abs(d) < 1e-12:
                        continue
                    u = ((b[0] - x) * (c[1] - y) - (b[1] - y) * (c[0] - x)) / d
                    v = ((c[0] - x) * (a[1] - y) - (c[1] - y) * (a[0] - x)) / d
                    if u >= -1e-9 and v >= -1e-9 and u + v <= 1.0 + 1e-9:
                        return u * a[2] + v * b[2] + (1.0 - u - v) * c[2]
        return None

    def _pad_tris(self, k: int, i: int) -> list:
        if (k, i) not in self._tris:
            from ..streets.kit import Mesh
            ring = self.tops[k][i]
            zmap = {(q[0], q[1]): q[2] for q in ring}
            m = Mesh((0.0, 0.0))
            m.poly("pad", [(q[0], q[1]) for q in ring],
                   zfun=lambda x_, y_: zmap.get((C.m2(x_), C.m2(y_)), 0.0))
            sl = m.slots.get("pad")
            tris = []
            if sl is not None:
                P = [(q[0] / 1000.0, q[1] / 1000.0, q[2] / 1000.0) for q in sl.pos]
                tris = [(P[sl.idx[t]], P[sl.idx[t + 1]], P[sl.idx[t + 2]])
                        for t in range(0, len(sl.idx), 3)]
            self._tris[(k, i)] = tris
        return self._tris[(k, i)]


def _carriageway(s, cls: str, jring: dict):
    """A road's carriageway as AG7's road piece draws it (`streets.roads.Road`: from the cut
    edge at one junction to the other's, mitred at its centerline's vertices), shapely; None
    where it has none."""
    from ..streets.roads import Road
    ends = []
    for at, nid in (("start", s.start), ("end", s.end)):
        e = {"at": at}
        if nid in jring:
            e["junction"] = {"ring": jring[nid]}
        ends.append(e)
    try:
        rd = Road({"seg": s.model_dump(mode="json", exclude_none=True), "cls": cls,
                   "ends": ends})
    except ValueError:
        return None
    if rd.s1 - rd.s0 < 0.05:
        return None
    left, right = [], []
    for sv, vi in rd.stations(rd.s0, rd.s1):
        left.append(rd.at(sv, rd.h, vi))
        right.append(rd.at(sv, -rd.h, vi))
    poly = shapely.Polygon(left + right[::-1])
    if not poly.is_valid:
        poly = shapely.make_valid(poly)
    return poly


def _z_along(prof, s: float) -> float:
    if not prof:
        return 0.0
    if s <= prof[0][0]:
        return prof[0][1]
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s <= s1:
            return z0 if s1 <= s0 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return prof[-1][1]


def _seg_dist(px, py, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    qx, qy = ax + dx * t - px, ay + dy * t - py
    return math.sqrt(qx * qx + qy * qy)


def gather(model, spec, briefs: dict | None, out_dir: Path, pages: bool = False) -> Gathered:
    """`pages`: the sign faces show the city's sign pages (AG6's library is there)."""
    g = Gathered()
    ds = _Districts(model)
    blds = {b.id: b for b in model.buildings}
    foot = {}
    with G.canonical():
        for b in model.buildings:
            if b.footprint is not None:
                foot[b.id] = G.from_model_poly(b.footprint)
    fids = sorted(foot)
    ftree = shapely.STRtree([foot[i] for i in fids]) if fids else None
    gd = Ground(model)
    bases = {b.id: float(b.base_m) for b in model.buildings
             if getattr(b, "base_m", None) is not None}
    quays = {} if gd.flat else _quay_tops(model, gd)

    def lift(x, y, z, bid=None) -> float:
        """The height a placement's z is measured from (module docstring, Ground)."""
        if gd.flat:
            return 0.0
        if bid is None and z > 0.6 and ftree is not None:
            hit = ftree.query(shapely.points(x, y), predicate="intersects")
            if len(hit):
                bid = fids[min(hit.tolist())]
        if bid in bases:
            return bases[bid]
        return gd.at(x, y)

    def near_foot(x, y):
        if ftree is None:
            return None
        hit = ftree.query(shapely.points(x, y), predicate="dwithin", distance=4.0)
        if not len(hit):
            return None
        best = min(hit.tolist(), key=lambda i: (round(foot[fids[i]].distance(
            shapely.points(x, y)), 4), fids[i]))
        return foot[fids[best]]

    # the briefs' facade props: building, on the wall, gap
    mount: dict[str, dict] = {}
    for bid in sorted(briefs or {}):
        for e in (briefs[bid].get("props") or []):
            if e.get("end") is not None:
                continue
            mount.setdefault(e["id"], {"building": bid, "on_wall": e["on_wall"],
                                       "gap": float(e["gap_m"])})
    # AG7's road pieces with their median barrier, and (#89) its raised junctions' corners
    roads = set()
    raised = []
    paved: list = []
    smf = Path(out_dir) / "streets" / "manifest.json"
    if smf.is_file():
        try:
            sm = json.loads(smf.read_text(encoding="utf-8"))
            for pid, r in sorted(sm.get("pieces", {}).items()):
                if r.get("kind") == "street.road" and r.get("triangles", 0) > 0:
                    roads.add(pid)
                rz = (r.get("notes") or {}).get("raised")
                if r.get("kind") == "street.junction" and rz:
                    raised.append(rz)
                if r.get("kind") == "street.junction":
                    paved += (r.get("notes") or {}).get("paved") or []
        except (OSError, ValueError):
            roads = set()
            raised = []
            paved = []
    corners = _RaisedCorners(raised, model.sidewalks)
    segs = {s.id: s for s in model.road_segments}

    def style_of(did):
        return ST.style_of(ds.d[did].archetype) if did in ds.d else "civic"

    # -- props
    groups: dict = {}
    exact: dict = defaultdict(lambda: defaultdict(list))
    kinds_used = set()

    def add(key, kind, cls, tile, part, xf, pid):
        gr = groups.setdefault(key, {"cls": cls, "kind": kind, "tile": tile, "parts": {}})
        p = gr["parts"].setdefault(part, {"xforms": [], "ids": []})
        p["xforms"].append(xf)
        p["ids"].append(pid)

    brackets = 0
    fit = None
    pfeet: dict = {}
    for p in sorted(model.props, key=lambda p: p.id):
        kind = p.type.split(".", 1)[1]
        g.kinds[kind] = g.kinds.get(kind, 0) + 1
        x, y, z = p.position
        t = tile_of(x, y)
        key = f"prop.{kind}.{t}"
        if kind in ST.SLOTTED:
            g.covered[p.id] = "sign slot"
            continue
        did = ds.of(p.id, x, y)
        st = style_of(did)
        mm = mount.get(p.id)
        if kind == "boat":
            # (M20: a boat's z is its water's surface over the ground at its point; AG14: so it
            # takes the ground as everything else does: it took the water's level on top of
            # that, 1.5 m under the water on a flat city)
            z = z + lift(x, y, min(z, 0.0))
        elif kind == "railing" and not gd.flat and (p.attrs or {}).get("quay") in quays:
            # (#89: on a terrain city a quay's railing stands on the quay's paving as AG7
            # draws it, its ground sampled at the quay line's vertices: M13's ground at the
            # railing's own point stood off it on a slope)
            z = z + quays[p.attrs["quay"]](x, y)
        else:
            z = z + lift(x, y, z, (mm or {}).get("building") or
                         (p.attrs or {}).get("building"))
        if kind in ST.EXACT:
            item = {"prop": {"id": p.id, "position": [C.m2(x), C.m2(y), C.m2(z)],
                             "yaw_deg": C.deg(p.yaw_deg), "scale": [C.m2(v) for v in p.scale],
                             "attrs": {k: v for k, v in sorted((p.attrs or {}).items())
                                       if k in ("sag_m", "name")}},
                    "style": st}
            if kind == "scaffolding":
                b = (p.attrs or {}).get("building")
                item["wall"] = 1.0 if _wall_plus_y(foot.get(b) or near_foot(x, y), x, y,
                                                   p.yaw_deg, 0.8) else -1.0
            if kind == "gate":
                pal = _palette(spec, ds.d.get(did), did)
                item["color"] = ST.choice(pal, "ag8.gate", p.id)
            item["digest"] = C.digest(item)
            exact[t][key].append(item)
            g.covered[p.id] = "exact"
            continue
        if kind == "barrier":
            sid = (p.attrs or {}).get("segment")
            s = segs.get(sid)
            if sid in roads and s is not None and s.road_class == "highway" and \
                    s.cross_section.median_m > 0:
                g.dropped[p.id] = "the road piece's median barrier (AG7)"
                groups.setdefault(key, {"cls": "prop", "kind": kind, "tile": t, "parts": {}})
                continue
        n = ST.PROP_VARIANTS[kind]
        if kind == "trash":
            item = (p.attrs or {}).get("item", "bag")
            base = {"bag": 0, "box": 4, "can": 8}.get(item, 0)
            k = base + ST.pick(4, "ag8.prop", p.id)
            alts = [base + (k - base + i) % 4 for i in range(4)]
        else:
            k = ST.pick(n, "ag8.prop", p.id)
            alts = [(k + i) % n for i in range(n)]
        if kind not in FIT_SKIP and kind not in NOT_STANDING and corners.unpaved(x, y, z):
            # (#89: in a raised junction's corner where AG7 draws no pad: nothing to stand on)
            g.dropped[p.id] = "a raised junction's corner with no pad (#89)"
            groups.setdefault(key, {"cls": "prop", "kind": kind, "tile": t, "parts": {}})
            continue
        if kind not in FIT_SKIP and kind not in NOT_STANDING:
            # (#95: the variant drawn, else the next of its family, that keeps clear of the
            # carriageways, junctions and crosswalks; none: the prop is left out)
            if fit is None:
                fit = _Fit(model, paved)
            k = next((kk for kk in alts if fit.clear(kind, st, kk, x, y, p.position[2],
                                                      p.yaw_deg, p.scale)), None)
            if k is None:
                g.dropped[p.id] = "no variant clear of the carriageway (#95)"
                groups.setdefault(key, {"cls": "prop", "kind": kind, "tile": t, "parts": {}})
                continue
        if kind not in FIT_SKIP and kind not in NOT_STANDING:
            # (#89: on a raised junction's corner pad, its foot on the pad as AG7 draws it:
            # a pad follows its nearest curb, off the model's height on a steep junction)
            f = _prop_foot(pfeet, kind, st, k)
            if f is not None:
                u, v, z0 = f
                a_ = M.radians(p.yaw_deg)
                c_, s_ = M.cos(a_), M.sin(a_)
                fx = x + c_ * u * p.scale[0] - s_ * v * p.scale[1]
                fy = y + s_ * u * p.scale[0] + c_ * v * p.scale[1]
                pz = corners.pad_top(fx, fy, z)
                if pz is not None:
                    z = C.m(pz - z0 * p.scale[2])
        kinds_used.add(kind)
        yaw = p.yaw_deg
        if kind == "railing" and not gd.flat and (p.attrs or {}).get("quay") in quays:
            # (#89: its foot, the variant's lowest posts, on the quay's paving: a 3 m
            # railing's end post stood off a steep quay by up to 0.5 m)
            f = _prop_foot(pfeet, kind, st, k)
            if f is not None:
                u, v, z0 = f
                a_ = M.radians(yaw)
                c_, s_ = M.cos(a_), M.sin(a_)
                fx = x + c_ * u * p.scale[0] - s_ * v * p.scale[1]
                fy = y + s_ * u * p.scale[0] + c_ * v * p.scale[1]
                z = C.m(quays[p.attrs["quay"]](fx, fy) - z0 * p.scale[2])
        if kind == "awning":
            poly = foot.get(mm["building"]) if mm else near_foot(x, y)
            if not _wall_plus_y(poly, x, y, yaw, p.scale[1] / 2.0 + 0.25):
                yaw = yaw + 180.0
        yaw = C.deg(((yaw + 180.0) % 360.0) - 180.0)
        cx, cy = tile_center(t)
        if kind == "awning":
            # in segments of about 2 m along the facade (arms, ribs and corrugation keep
            # their size), each a variant of the unit's own family member
            L = p.scale[0]
            n = max(1, int(round(L / AWNING_SEGMENT_M)))
            a = M.radians(yaw)
            c, s = M.cos(a), M.sin(a)
            for i in range(n):
                off = -L / 2.0 + L * (i + 0.5) / n
                add(key, kind, "prop", t, ST.variant_name(kind, st, k),
                    [C.m(x + c * off - cx), C.m(y + s * off - cy), C.m(z), yaw,
                     C.m(L / n), C.m(p.scale[1]), C.m(p.scale[2])], p.id)
        else:
            xf = [C.m(x - cx), C.m(y - cy), C.m(z), yaw] + [C.m(v) for v in p.scale]
            add(key, kind, "prop", t, ST.variant_name(kind, st, k), xf, p.id)
        if kind in REACH and mm and mm["gap"] > BRACKET_MIN_M and \
                (p.attrs or {}).get("mount") != "deck":
            a = M.radians(p.yaw_deg)
            bx = x - M.cos(a) * REACH[kind]
            by = y - M.sin(a) * REACH[kind]
            kb = ST.pick(ST.PROP_VARIANTS["bracket"], "ag8.bracket", p.id)
            add(key, kind, "prop", t, ST.variant_name("bracket", st, kb),
                [C.m(bx - cx), C.m(by - cy), C.m(z), C.deg(((p.yaw_deg + 180.0) % 360.0) - 180.0),
                 C.m(mm["gap"]), 1.0, 1.0], p.id)
            kinds_used.add("bracket")
            brackets += 1
    # -- plants
    species_used = set()
    feet: dict = {}
    for p in sorted(model.plants, key=lambda p: p.id):
        typ = p.type.split(".", 1)[1]
        sp = p.species if p.species in ST.PLANT_VARIANTS else ST.SPECIES_OF_TYPE.get(typ, "oak")
        g.species[sp] = g.species.get(sp, 0) + 1
        species_used.add(sp)
        x, y, z = p.position
        bid = (p.attrs or {}).get("building")
        seat = not gd.flat and z == 0.0 and bid is None and typ != "facade_greenery"
        if not seat:
            z = z + lift(x, y, z, bid)
        t = tile_of(x, y)
        key = f"plant.{typ}.{t}"
        cx, cy = tile_center(t)
        r0, h0 = BASE[sp]
        if typ == "facade_greenery":
            a = p.attrs or {}
            yaw = float(a.get("yaw_deg", 0.0))
            L = float(a.get("length_m", 1.0))
            n = max(1, int(round(L / IVY_PATCH_M)))
            c, s = M.cos(M.radians(yaw)), M.sin(M.radians(yaw))
            for i in range(n):
                off = -L / 2.0 + L * (i + 0.5) / n
                k = ST.pick(ST.PLANT_VARIANTS[sp], "ag8.plant", p.id, i)
                add(key, typ, "plant", t, ST.plant_name(sp, k),
                    [C.m(x + c * off - cx), C.m(y + s * off - cy), C.m(z), C.deg(yaw),
                     C.m(L / n / IVY_PATCH_M), 1.0, C.m(p.height_m / h0)], p.id)
            continue
        k = ST.pick(ST.PLANT_VARIANTS[sp], "ag8.plant", p.id)
        yaw = C.deg(360.0 * ST.u("ag8.yaw", p.id) - 180.0)
        sc = (C.m(p.crown_radius_m / r0), C.m(p.crown_radius_m / r0), C.m(p.height_m / h0))
        if seat:
            # (#89: on a terrain city a plant on the ground stands with its foot on the
            # slope, `_seat`)
            z = _seat(gd, feet, sp, k, x, y, yaw, sc)
        add(key, typ, "plant", t, ST.plant_name(sp, k),
            [C.m(x - cx), C.m(y - cy), C.m(z), yaw, *sc], p.id)
    g.families = sorted([("prop", k) for k in kinds_used | {kk for kk in g.kinds
                                                             if kk in ST.PROP_VARIANTS}]) + \
        sorted(("plant", s) for s in species_used)
    g.families = sorted(set(g.families))
    g.groups = {k: groups[k] for k in sorted(groups)}
    g.exact = {t: [(k, k.split(".")[1], exact[t][k]) for k in sorted(exact[t])]
               for t in sorted(exact)}
    # -- signs
    g.signs = _signs(model, spec, ds, blds, mount, lift, out_dir if pages else None)
    n_inst = sum(len(p["xforms"]) for gr in g.groups.values() for p in gr["parts"].values())
    g.stats = {"props": len(model.props), "plants": len(model.plants),
               "sign_slots": len(model.sign_slots), "instances": n_inst,
               "brackets": brackets, "dropped": len(g.dropped),
               "exact": sum(len(items) for t in g.exact.values() for _, _, items in t),
               "signs": sum(len(v) for v in g.signs.values())}
    return g


def _palette(spec, d, did) -> list[str]:
    era = ST.era_of(d.archetype if d is not None else None)
    if spec is not None and d is not None:
        sd = (getattr(spec, "districts", None) or {}).get(d.name)
        pal = getattr(sd, "neon_palette", None) if sd is not None else None
        if pal:
            return list(pal)
    return list(MT.NEON_ERA.get(era, MT.NEON))


def _signs(model, spec, ds: _Districts, blds: dict, mount: dict, lift, out_dir) -> dict:
    """Per tile its signs: per slot AG6's text, script, style and colors (`signage`: the
    same draw its pages make), the cell of the city's sign pages that shows it (`signs.json`,
    where the pages are made and the cell says the same text), the body AG8 makes it as
    (`signs.make`) and the gap to its wall."""
    from .. import spec as S
    from ..materials import signage as SG6
    doc = S.dump(spec if spec is not None else S.fill(S.AssetSpec()))
    styles6 = SG6.district_styles(model, doc)
    slots, texts = SG6.slot_texts(model, styles6)
    SG6.ad_slots(model, slots)
    cells = {}
    p = Path(out_dir) / "signs.json" if out_dir is not None else None
    if p is not None and p.is_file():
        try:
            cells = json.loads(p.read_text(encoding="utf-8")).get("cells") or {}
        except (OSError, ValueError):
            cells = {}
    out: dict = defaultdict(list)
    for s in sorted(model.sign_slots, key=lambda s: s.id):
        x, y, z = s.position
        t = tile_of(x, y)
        b = blds.get(s.building_id) if s.building_id else None
        did = b.district_id if b is not None and b.district_id in ds.d else ds.of(s.id, x, y)
        d = ds.d.get(did)
        st = ST.style_of(d.archetype if d is not None else None)
        key = slots.get(s.id, "")
        cell = cells.get(key)
        inp = {"kind": s.kind, "mount": s.mount, "w": C.m2(round(s.width_m * 20) / 20.0),
               "h": C.m2(round(s.height_m * 20) / 20.0), "style": st}
        sa = s.attrs or {}
        if sa.get("lit"):
            inp["lit"] = sa["lit"]          # (M20: billboards lit as neon)
        if s.mount == "front":
            inp["off"] = C.m2(float(sa.get("off_m", 3.0)))   # (M20: off its facade)
        if key.startswith("ad:"):
            pal = (styles6.get((b.district_id if b is not None else None) or "") or {}).get(
                "palette") or list(SG6.ACCENTS)
            c1 = ST.choice(pal, "ag8.c1", s.id)
            c2 = ST.choice([c for c in pal if c != c1] or pal, "ag8.c2", s.id)
            inp.update(colors=[c1, c2], two_sided=bool(s.two_sided), ad=key)
            if cell is not None:
                inp["cell"] = {"slot": ("holopage." if s.kind == "holo_ad" else "page.")
                               + cell["page"], "uv": cell["uv"]}
        else:
            info = texts[key]
            if s.kind == "neon" or info["style"] == "neon":
                look = "neon"
            elif info["style"] == "led":
                look = "led"
            elif s.mount != "blade" and st == "sleek" and ST.u("ag8.channel", s.id) < 0.5:
                look = "channel"
            else:
                look = "lightbox"
            inp.update(text=info["text"], script=info["script"], look=look,
                       colors=[info["color"], info["color2"]])
            if look in ("lightbox", "led") and cell is not None and \
                    cell.get("text") == info["text"]:
                inp["cell"] = {"slot": "page." + cell["page"], "uv": cell["uv"]}
            mm = mount.get(s.prop_id) if s.prop_id else None
            if mm and mm["gap"] > BRACKET_MIN_M:
                inp["gap"] = C.m2(mm["gap"])
        dg = C.digest(inp)
        # (an "h": Blender's glTF import reads a name ending in a dot and digits as a
        # counter, and a long one overflows it)
        out[t].append({"id": s.id, "node": "sign.h" + dg[:16], "inputs": inp, "digest": dg,
                       "extra_name": s.id,
                       "pivot": [C.m2(x), C.m2(y), C.m2(z + lift(x, y, z, s.building_id))],
                       "yaw": C.deg(s.yaw_deg), "kind": s.kind,
                       "prop_id": s.prop_id})
    for t in out:
        # holo-ads keep their own nodes (their LOD chain is named by the slot)
        for e in out[t]:
            if e["kind"] == "holo_ad":
                e["node"] = e["id"]
    return {t: out[t] for t in sorted(out)}
