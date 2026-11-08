"""AG17: street surfaces drawn from M22's pavement map (docs/assetgen_scope.md 14.18).

M22 keeps one exact map of every road surface in the model: faces (a road's carriageway each
way, median, curbs, furniture zones and clear paths, a bend where a band would fold; a
junction's carriageway, corner pads and a cul-de-sac's bulb) whose boundaries are edges stored
once, polylines of vertices on the 1 mm grid with one height each. AG7's road, junction and
sidewalk pieces draw those faces as they are, so two pieces meet on the same vertices at the
same heights by construction:

- **Boundaries:** a face's stored vertices in order, never split, never moved; its interior
  by `triangulate.triangulate_face` (the face's interior samples as Steiner points strictly
  inside).
- **Heights:** a vertex's height over sea level (the map's height over the finished ground
  plus that ground, `Ctx.ground`, on the millimeter) and the face's *lift* over it: a
  carriageway, junction, bulb, bend or walking surface `ROAD_DZ_MM` over its grade line; a
  curb band, furniture zone, clear path or corner pad `CURB_MM` more (dropped to `DROP_MM` at
  a curb ramp: the curb band's vertices beside a crosswalk's end or a driveway); an
  avenue's, street's or service road's median of a meter or more raised as a curbed island
  (level with the carriageway where a crosswalk crosses it and between that crosswalk and
  the road's end). Every piece reads the same lifts from `Index` (gather side), so a vertex
  two pieces share is drawn at one height in both.
- **Curbs:** where two faces meet at different lifts, the higher face's piece draws the wall
  between them, the same stored polyline at the two heights; the right of way's outer edges
  carry a wall down to the ground (a raised road's fascia, a raised junction's slab edge).

All values handed to a maker are integers on the millimeter grid, so a maker's arithmetic is
exact and two makers never disagree about a vertex.
"""

from __future__ import annotations

import math
from collections import defaultdict

ROAD_DZ_MM = 50         # a carriageway over its grade line (`roads.ROAD_DZ`)
CURB_MM = 150           # a curb band's, sidewalk's, corner pad's or raised median's top over it
DROP_MM = 20            # ... dropped to this at a curb ramp
RAISED_MM = 500         # a face this far over its ground stands on a girder or a slab
TOP_KINDS = ("carriageway", "junction", "bulb", "bend", "walk")
CURB_KINDS = ("curb", "sidewalk", "corner")
SIDE_BANDS = ("cr", "fn", "cl")
MEDIAN_MIN_M = 1.0      # a median this wide on an avenue, street or service road is an island
XWALK_PAD_M = 0.25      # a curb ramp reaches this past a crosswalk's edges along the curb
MEDIAN_PAD_M = 0.5      # a median is level with the road this far past a crosswalk's edges
MEDIAN_REACH_M = 40.0   # ... and from a crosswalk this near its road's end on to the end
DOOR_HALF_M = {"garage": 3.0, "loading": 2.5, "gate": 2.5}
DOOR_REACH_M = 8.0      # a driveway's entrance within this of the right of way's edge
GROUND_SINK_MM = 20     # an at-grade face's outer wall reaches this into the ground
FASCIA_MM = 450         # a raised road's outer edge: its fascia this deep under its grade line
EMBANK_SINK_MM = 100    # an embankment's faces reach this into the ground


def mm(v: float) -> int:
    return int(math.floor(v * 1000.0 + 0.5))


def street_class(s) -> str:
    """As citygen's `streets.street_class` (and `roads.street_class`)."""
    return "avenue" if s.road_class == "highway" and "pinned" in s.attrs else s.road_class


def side_of(band: str) -> str | None:
    """`l` or `r` for a sidewalk band (cr, fn, cl: `crl`, `fnr_b`), else None."""
    return band[2] if band[:2] in SIDE_BANDS and len(band) >= 3 else None


# ---------------------------------------------------------------------------
# Gather: the map of a city
# ---------------------------------------------------------------------------

class Index:
    """The pavement map of a model, read once: every vertex's plan position and height over
    sea level on the millimeter (`V`: id -> (x, y, z, z over its ground)), every edge
    (`E`: id -> (kind, vertex ids)), the faces by id and by owner, the faces along each
    edge, each face's class (top, curb, median) and the vertices dropped to a curb ramp
    (`drop`) or level with the road on a median (`mdrop`)."""

    def __init__(self, m, ground):
        net = m.pavement_net
        self.on = net is not None and bool(m.pavement)
        self.V: dict = {}
        self.E: dict = {}
        self.F: dict = {}
        self.by_owner: dict = defaultdict(list)
        self.edge_faces: dict = defaultdict(list)
        self.cls: dict = {}
        self.drop: set = set()
        self.mdrop: set = set()
        self.ground = ground
        if not self.on:
            return
        for v in net.vertices:
            g = ground.at(v.p[0], v.p[1])
            self.V[v.id] = (mm(v.p[0]), mm(v.p[1]), mm(g + v.z), mm(v.z))
        for e in net.edges:
            self.E[e.id] = (e.kind, list(e.v))
        self.seg = {s.id: s for s in m.road_segments}
        for f in sorted(m.pavement, key=lambda f: f.id):
            self.F[f.id] = f
            self.by_owner[f.owner_id].append(f.id)
            for refs in f.rings:
                for r in refs:
                    self.edge_faces[r.lstrip("-")].append(f.id)
            self.cls[f.id] = self._class(f)
        self._rings: dict = {}

    def _class(self, f) -> str:
        if f.kind in CURB_KINDS:
            return "curb"
        if f.kind == "median":
            s = self.seg.get(f.owner_id)
            if s is not None and street_class(s) in ("avenue", "street", "service") and \
                    (s.cross_section.median_m or 0.0) >= MEDIAN_MIN_M:
                return "median"
        return "top"

    # -- rings and heights -----------------------------------------------------------------

    def ring(self, refs) -> list[str]:
        """A ring's vertex ids in order (its edges joined, the closing vertex once)."""
        out: list[str] = []
        for ref in refs:
            vs = self.E[ref.lstrip("-")][1]
            vs = vs[::-1] if ref.startswith("-") else vs
            out += vs if not out else vs[1:]
        return out[:-1]

    def rings(self, fid: str) -> list[list[str]]:
        got = self._rings.get(fid)
        if got is None:
            got = self._rings[fid] = [self.ring(refs) for refs in self.F[fid].rings]
        return got

    def lift(self, fid: str, vid: str) -> int:
        c = self.cls[fid]
        if c == "top":
            return ROAD_DZ_MM
        if c == "curb":
            return ROAD_DZ_MM + (DROP_MM if vid in self.drop else CURB_MM)
        return ROAD_DZ_MM + (0 if vid in self.mdrop else CURB_MM)

    def top(self, fid: str, vid: str) -> int:
        return self.V[vid][2] + self.lift(fid, vid)

    def base_lift(self, fid: str) -> int:
        return ROAD_DZ_MM if self.cls[fid] == "top" else ROAD_DZ_MM + CURB_MM

    def face_input(self, fid: str) -> dict:
        """A face as a maker reads it, on the millimeter: its rings of vertices
        [x, y, top (drawn height), z (its height over sea level), z over its ground], and per
        ring segment (vertex k to k + 1) [edge kind, the face beside it: owner, kind, class
        and its tops at both ends] (the highest where several), or [edge kind] on the right
        of way's outer edge; its interior samples [x, y, top]."""
        f = self.F[fid]
        rings, segs = [], []
        for refs in f.rings:
            ids = self.ring(refs)
            rings.append([[*self.V[v][:2], self.top(fid, v), self.V[v][2], self.V[v][3]]
                          for v in ids])
            rs = []
            k = 0
            n = len(ids)
            for ref in refs:
                eid = ref.lstrip("-")
                kind, vs = self.E[eid]
                others = [g for g in self.edge_faces[eid] if g != fid]
                for _ in range(len(vs) - 1):
                    a, b = ids[k % n], ids[(k + 1) % n]
                    if others:
                        best = None
                        for g in others:
                            row = [self.F[g].owner_id, self.F[g].kind, self.cls[g],
                                   self.top(g, a), self.top(g, b)]
                            if best is None or row[3] + row[4] > best[3] + best[4]:
                                best = row
                        rs.append([kind, *best])
                    else:
                        rs.append([kind])
                    k += 1
            segs.append(rs)
        lift = self.base_lift(fid)
        g = self.ground
        smp = [[mm(x), mm(y), mm(g.at(x, y) + z) + lift] for x, y, z in f.samples]
        return {"id": fid, "kind": f.kind, "band": f.band, "layer": f.layer,
                "cls": self.cls[fid], "rings": rings, "segs": segs, "samples": smp}

    def faces_of(self, owner: str) -> list[str]:
        return list(self.by_owner.get(owner, ()))

    # -- curb ramps and median crossings ---------------------------------------------------

    def ramps(self, m) -> None:
        """The vertices dropped to a curb ramp (`drop`: a sidewalk's curb band beside a
        crosswalk's end or a garage, loading or gate entrance) and the median vertices
        level with the road (`mdrop`: under a crosswalk and from it on to a road end within
        `MEDIAN_REACH_M`). Ranges go along the road (its stations); every range takes at
        least the curb vertex nearest its middle (the map samples a band edge every 4 m or
        less, and its edges are never split)."""
        from .path import Path
        if not self.on:
            return
        cross_on: dict = defaultdict(list)
        for c in m.crosswalks:
            cross_on[c.segment_id].append(c)
        doors_on: dict = defaultdict(list)
        for b in m.buildings:
            for e in b.entrances:
                if e.kind in DOOR_HALF_M and e.segment_id:
                    doors_on[e.segment_id].append((b.id, e))
        for p in m.parking:
            for a in p.entrances:
                if a.kind in DOOR_HALF_M and p.segment_id:
                    doors_on[p.segment_id].append((p.id, a))
        for sid in sorted(self.seg):
            s = self.seg[sid]
            fids = self.by_owner.get(sid)
            if not fids or len(s.centerline) < 2:
                continue
            try:
                P = Path(s.centerline)
            except ValueError:
                continue
            curb: dict = {"l": {}, "r": {}}
            med: dict = {}
            for fid in fids:
                f = self.F[fid]
                sd = side_of(f.band)
                if sd is not None and f.band.startswith("cr"):
                    for r in self.rings(fid):
                        for v in r:
                            if v not in curb[sd]:
                                x, y = self.V[v][0] / 1000.0, self.V[v][1] / 1000.0
                                curb[sd][v] = P.project(x, y)[0]
                elif self.cls[fid] == "median":
                    for r in self.rings(fid):
                        for v in r:
                            if v not in med:
                                x, y = self.V[v][0] / 1000.0, self.V[v][1] / 1000.0
                                med[v] = P.project(x, y)[0]
            ranges: dict = {"l": [], "r": []}
            xs = []
            for c in sorted(cross_on.get(sid, ()), key=lambda c: c.id):
                if len(c.line) < 2:
                    continue
                for p in (c.line[0], c.line[-1]):
                    sc, t = P.project(p[0], p[1])
                    ranges["l" if t > 0 else "r"].append(
                        (sc - c.width_m / 2.0 - XWALK_PAD_M, sc + c.width_m / 2.0 + XWALK_PAD_M))
                a, b = c.line[0], c.line[-1]
                sc, _ = P.project((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                xs.append((sc - c.width_m / 2.0, sc + c.width_m / 2.0))
            row = s.width_m / 2.0
            for _, e in sorted(doors_on.get(sid, ()), key=lambda d: (d[0], d[1].kind)):
                half = DOOR_HALF_M.get(e.kind)
                if half is None:
                    continue
                se, te = P.project(e.position[0], e.position[1])
                if not (0.0 <= se <= P.L) or abs(te) < row - 0.5 or abs(te) > row + DOOR_REACH_M:
                    continue
                ranges["l" if te > 0 else "r"].append((se - half, se + half))
            for sd in ("l", "r"):
                if curb[sd]:
                    self.drop |= _in_ranges(curb[sd], ranges[sd])
            if med and xs:
                rs = [(a - MEDIAN_PAD_M, b + MEDIAN_PAD_M) for a, b in xs]
                lo, hi = min(med.values()), max(med.values())
                for a, b in xs:
                    if a - lo <= MEDIAN_REACH_M:
                        rs.append((lo - 1.0, b + MEDIAN_PAD_M))
                    if hi - b <= MEDIAN_REACH_M:
                        rs.append((a - MEDIAN_PAD_M, hi + 1.0))
                self.mdrop |= {v for v, sv in med.items() if any(a <= sv <= b for a, b in rs)}


def _in_ranges(st: dict, ranges: list) -> set:
    """The vertices whose station lies in a range, and for a range none lies in, the one
    nearest its middle."""
    out = set()
    if not ranges:
        return out
    items = sorted(st.items(), key=lambda kv: (kv[1], kv[0]))
    for a, b in ranges:
        hit = [v for v, sv in items if a <= sv <= b]
        if not hit:
            mid = (a + b) / 2.0
            v, sv = min(items, key=lambda kv: (abs(kv[1] - mid), kv[0]))
            if abs(sv - mid) <= (b - a) / 2.0 + 4.0:
                hit = [v]
        out.update(hit)
    return out


# ---------------------------------------------------------------------------
# Make: drawing faces
# ---------------------------------------------------------------------------

def face_points(fi: dict):
    """(rings of (x, y), Steiner points, height of each plan point) of a face input."""
    rings = [[(p[0], p[1]) for p in r] for r in fi["rings"]]
    z = {}
    for r in fi["rings"]:
        for p in r:
            z[(p[0], p[1])] = p[2]
    smp = []
    for x, y, t in fi.get("samples", ()):
        if (x, y) not in z:
            z[(x, y)] = t
            smp.append((x, y))
    return rings, smp, z


def triangles(fi: dict):
    """A face's triangles as world points on the millimeter: (points [(x, y, z)], index
    triples), its boundary vertices all kept (`triangulate_face`)."""
    from ..triangulate import TriangulationError, triangulate_face
    rings, smp, z = face_points(fi)
    try:
        pts, tris = triangulate_face(rings, smp)
    except TriangulationError:
        return [], []
    P = [(p[0], p[1], z[(p[0], p[1])]) for p in pts]
    return P, tris


def draw(mesh, fi: dict, slot, uv=None) -> list:
    """A face on the mesh: one slot, or `slot(tri)` -> name per triangle (tri: its three
    points). UV0: `uv(x, y)` in meters (default the plan position). Returns its triangles
    as world points (for `Surface`)."""
    P, tris = triangles(fi)
    if not tris:
        return []
    uvs = [uv(p[0] / 1000.0, p[1] / 1000.0) if uv else (p[0] / 1000.0, p[1] / 1000.0)
           for p in P]
    if callable(slot):
        by: dict = defaultdict(list)
        for t in tris:
            by[slot((P[t[0]], P[t[1]], P[t[2]]))].append(t)
        for name in sorted(by):
            mesh.tris_mm(name, P, by[name], uvs, expect=(0, 0, 1))
    else:
        mesh.tris_mm(slot, P, tris, uvs, expect=(0, 0, 1))
    return [(P[a], P[b], P[c]) for a, b, c in tris]


def segments(fi: dict):
    """Every ring segment of a face: (ring index, k, a, b, seg record), a and b its end
    vertices [x, y, top, z, z over ground]."""
    for ri, (r, rs) in enumerate(zip(fi["rings"], fi["segs"])):
        n = len(r)
        for k in range(n):
            yield ri, k, r[k], r[(k + 1) % n], rs[k] if k < len(rs) else ["outer"]


def walls(mesh, fi: dict, slot: str, bottom=None, curb_slot: str | None = None,
          out: list | None = None) -> None:
    """The walls of a face: down to the face beside it where that is lower (a curb), and
    on the right of way's outer edges down to `bottom(vertex)` (millimeters; None: no
    outer wall). Collected into `out` (drawn later by `draw_walls`, which sees every face
    of a piece), else drawn now."""
    specs = []
    for _, _, a, b, rec in segments(fi):
        if len(rec) > 1:
            ta, tb = rec[4], rec[5]
            if a[2] > ta or b[2] > tb:
                specs.append((curb_slot or slot, (a[0], a[1]), (b[0], b[1]), min(ta, a[2]),
                              a[2], min(tb, b[2]), b[2], False))
        elif bottom is not None:
            ba, bb = bottom(a), bottom(b)
            if ba is not None and bb is not None:
                specs.append((slot, (a[0], a[1]), (b[0], b[1]), min(ba, a[2]), a[2],
                              min(bb, b[2]), b[2], True))
    if out is not None:
        out.extend(specs)
    else:
        draw_walls(mesh, specs)


def draw_walls(mesh, specs: list) -> None:
    """Walls collected by `walls`. Where outer walls of a piece meet at a vertex where its
    faces only touch (two of them arrive at it, or leave it), each steps 1 mm back from it,
    so no two run up the same vertical edge the same way (the map's shapes allow a junction
    region pinched at a point)."""
    from collections import Counter
    starts, ends = Counter(), Counter()
    for sp in specs:
        if sp[7]:
            starts[sp[1]] += 1
            ends[sp[2]] += 1
    pinch = {p for p, n in starts.items() if n > 1} | {p for p, n in ends.items() if n > 1}
    u = 0.0
    for slot, a, b, za0, za1, zb0, zb1, outer in specs:
        L = math.sqrt(float(b[0] - a[0]) ** 2 + float(b[1] - a[1]) ** 2)
        if outer and pinch and (a in pinch or b in pinch):
            if L < 3.0:
                continue
            fx, fy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            a2 = (a[0] + int(round(fx)), a[1] + int(round(fy))) if a in pinch else a
            b2 = (b[0] - int(round(fx)), b[1] - int(round(fy))) if b in pinch else b
            a, b = a2, b2
        mesh.wall_mm(slot, a, b, za0, za1, zb0, zb1, u)
        u += L / 1000.0


def ground_bottom(v) -> int:
    """An outer wall's foot at grade: into the ground under the vertex (`GROUND_SINK_MM`),
    in a tunnel 0.3 m under the road."""
    if v[4] < -RAISED_MM:
        return v[3] - 300
    return v[3] - v[4] - GROUND_SINK_MM


def bottoms(dk: str, path=None, embs=()):
    """How far a road's faces' outer walls reach down, by its deck kind (`roads.deck_kind`):
    (bottom(vertex) in millimeters or None, the walls' slot or None for the face's own).
    A viaduct's or bridge's fascia `FASCIA_MM` under its grade line (into the ground on
    M18's embankment stretches), an embankment's into the ground, a deck street's onto its
    slab, a deck ramp's none (its walls are its own), else into the ground."""
    def in_emb(v) -> bool:
        if not embs or path is None:
            return False
        s, _ = path.project(v[0] / 1000.0, v[1] / 1000.0)
        return any(a - 0.01 <= s <= b + 0.01 for a, b in embs)

    if dk == "deck":
        def deck(v):
            if in_emb(v):
                return v[3] - v[4] - EMBANK_SINK_MM
            return v[3] - FASCIA_MM
        return deck, "concrete.deck"
    if dk == "embankment":
        return (lambda v: v[3] - v[4] - EMBANK_SINK_MM), "concrete"
    if dk == "slab":
        return (lambda v: v[3] - GROUND_SINK_MM), "concrete"
    if dk == "ramp":
        return None, "concrete"
    return ground_bottom, None


def is_raised(fi: dict) -> bool:
    return any(p[4] > RAISED_MM for r in fi["rings"] for p in r)


class Surface:
    """Heights of the faces a piece drew (their triangles in world millimeters): `z(x, y)`
    in meters over a point (the triangle under it, or the plane of the nearest one)."""

    CELL = 4000

    def __init__(self, tris=()):
        self.t: list = []
        self.b: dict = defaultdict(list)
        for t in tris:
            self.add(t)

    def add(self, t) -> None:
        i = len(self.t)
        self.t.append(t)
        xs = [p[0] for p in t]
        ys = [p[1] for p in t]
        c = self.CELL
        for ix in range(min(xs) // c, max(xs) // c + 1):
            for iy in range(min(ys) // c, max(ys) // c + 1):
                self.b[(ix, iy)].append(i)

    def __bool__(self) -> bool:
        return bool(self.t)

    def z(self, x: float, y: float, default: float | None = None) -> float | None:
        X, Y = x * 1000.0, y * 1000.0
        c = self.CELL
        ix, iy = int(math.floor(X / c)), int(math.floor(Y / c))
        best = None
        for r in (0, 1, 2):
            cand = set()
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    cand.update(self.b.get((ix + dx, iy + dy), ()))
            if not cand:
                continue
            for i in sorted(cand):
                a, b, cc = self.t[i]
                d = (b[0] - a[0]) * (cc[1] - a[1]) - (b[1] - a[1]) * (cc[0] - a[0])
                if d == 0:
                    continue
                u = ((b[0] - X) * (cc[1] - Y) - (b[1] - Y) * (cc[0] - X)) / d
                v = ((cc[0] - X) * (a[1] - Y) - (cc[1] - Y) * (a[0] - X)) / d
                w = 1.0 - u - v
                out = -min(u, v, w)
                zz = (u * a[2] + v * b[2] + w * cc[2]) / 1000.0
                if out <= 1e-9:
                    return zz
                if best is None or out < best[0]:
                    best = (out, zz)
            if best is not None:
                return best[1]
        return default
