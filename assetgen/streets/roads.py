"""Road segments: the road's faces of M22's pavement map (AG17: its carriageway each way, a
bend, a walking surface, its median, and its sidewalk bands where no sidewalk piece draws
them; `pave.py`), lane markings from the model's lanes (lane lines, center lines, edge lines,
stop lines, arrows), patches, manholes and drains on them, its barriers (`barriers.py`), and
under a raised road its deck (a box girder between its cuts, with expansion joints and
underside lights) or, for a low street ramp, an embankment.

Every face is drawn on its stored vertices at their stored heights (`pave.draw`), so the
road meets its junctions, its sidewalks and the road it goes on as with no gap and no step.
Markings and details lie on the faces as drawn (`Surface`), 4 mm over them.

UV0 runs along the road: u the distance along the centerline, v the offset across it
(meters), as AG6's road atlases expect.
"""

from __future__ import annotations

from citygen import dmath as M

from .. import canon as C
from . import materials as MT
from . import pave as PV
from .ctx import Ctx, bbox_center, dump
from .kit import Mesh
from .path import Path, Profile, unit
from .pieces import Out, Piece, maker, rnd

ROAD_DZ = 0.05          # road surface over its grade line (`pave.ROAD_DZ_MM`)
MARK_DZ = 0.004         # paint over the asphalt
PATCH_DZ = 0.002
STEP_M = 6.0
EMBANKMENT_M = 3.0      # a raised street no higher than this stands on an embankment
GIRDER_LIP_M = 0.01     # a deck's soffit reaches this past its fascia
DECK_D = {"highway": 1.8, "avenue": 1.6, "street": 1.2, "alley": 1.0, "service": 1.0,
          "pedestrian": 0.7, "footbridge": 0.6}
RANK = {"highway": 5, "avenue": 4, "street": 3, "service": 2, "alley": 1, "pedestrian": 0,
        "footbridge": 0}
DASH = {"highway": (4.5, 7.5), "avenue": (3.0, 6.0), "street": (3.0, 6.0),
        "service": (2.0, 4.0)}
PEDESTRIAN = ("pedestrian", "footbridge")
UP = (0.0, 0.0, 1.0)


def street_class(s) -> str:
    """As citygen's `streets.street_class`: a traced highway is an avenue at street level."""
    return "avenue" if s.road_class == "highway" and "pinned" in s.attrs else s.road_class


def asphalt_slot(cls: str, style: dict) -> str:
    if cls in ("highway", "avenue", "street"):
        return f"asphalt.{cls}"
    if cls in ("alley", "service"):
        return "asphalt.alley"
    if cls == "footbridge":
        return "paving.cobble" if style["era"] == "heritage" else "paving.timber" \
            if style["era"] in ("suburban_modern", "clean_tech") else "paving.concrete_tile"
    return MT.paving(style["archetype"])


def raised(seg: dict) -> bool:
    """As the blockout decides: a deck where the profile rises over 0.5 m, or a bridge."""
    zs = [z["z"] for z in seg.get("z_profile", [])]
    return bool(seg.get("bridge")) or (max(zs) > 0.5 if zs else False)


def deck_kind(seg: dict) -> str:
    """deck (a viaduct or bridge deck), embankment (a low ramp to a raised junction), or
    none; on M14's decks (AG10) slab (a deck's street, on its slab) or ramp (a deck's solid
    ramp, its walkways beside it)."""
    a = seg.get("attrs", {})
    if "deck" in a:
        return "ramp" if a.get("role") == "deck_ramp" else "slab"
    if seg.get("tunnel") or not raised(seg):
        return "none"
    elev = bool(a.get("elevated")) or a.get("role") == "ramp"
    zs = [z["z"] for z in seg.get("z_profile", [])]
    if not elev and not seg.get("bridge") and max(zs) <= EMBANKMENT_M:
        return "embankment"
    return "deck"


# ---------------------------------------------------------------------------
# Gather
# ---------------------------------------------------------------------------

def walk_sides(cx: Ctx, sid: str) -> set:
    """The sides (l, r) of a road whose sidewalk bands a sidewalk piece draws."""
    return {w.side[0] for w in cx.walks_on.get(sid, ())}


def road_face_ids(cx: Ctx, s) -> list[str]:
    """The faces of the map a road piece draws: its own, less the sidewalk bands of the
    sides a sidewalk piece draws."""
    sides = walk_sides(cx, s.id)
    return [f for f in cx.pave.faces_of(s.id) if PV.side_of(cx.pave.F[f].band) not in sides]


def port_lines(cx: Ctx, s, path: Path, cuts) -> dict:
    """The road's ports at its two ends as the map stores them: {"start"|"end": [right
    point, left point]} (the outermost vertices [x, y, z over sea level], meters) of the
    edges its faces share with the faces at that end: its junction's, or those of the
    road it goes on as (port edges, and seams where M22 cut an overlap with them), within
    a road's width of its cut there. A port at a centerline vertex is mitred, so skewed."""
    PI = cx.pave
    L = path.L
    want = {"start": cuts[0], "end": L - cuts[1]}
    out = {}
    for at, nid in (("start", s.start), ("end", s.end)):
        j = cx.junction_at.get(nid)
        owners = {j.id} if j is not None else             {o.id for o in cx.seg_at_node.get(nid, ()) if o.id != s.id}
        if not owners:
            continue
        other = want["end" if at == "start" else "start"]
        rows = {}
        for fid in PI.faces_of(s.id):
            for refs in PI.F[fid].rings:
                for ref in refs:
                    eid = ref.lstrip("-")
                    kind, vs = PI.E[eid]
                    if kind == "outer" or not any(
                            PI.F[g].owner_id in owners for g in PI.edge_faces.get(eid, ())
                            if g != fid):
                        continue
                    for v in vs:
                        if v in rows:
                            continue
                        x, y = PI.V[v][0] / 1000.0, PI.V[v][1] / 1000.0
                        sv, t = path.project(x, y)
                        # (within a road's width of the cut, a skewed port's ends too, and
                        # nearer this end than the other: a loop ramp passes beside its
                        # own end junction, a road may meet one junction at both ends)
                        if abs(sv - want[at]) <= max(s.width_m, 2.0) and                                 abs(sv - want[at]) <= abs(sv - other):
                            rows[v] = (t, x, y, PI.V[v][2] / 1000.0)
        if len(rows) < 2:
            continue
        lo, hi = min(rows.values()), max(rows.values())
        if hi[0] - lo[0] < 0.5:
            continue
        out[at] = [[lo[1], lo[2], lo[3]], [hi[1], hi[2], hi[3]]]
    return out


def map_stations(seg: dict, cuts) -> list[float]:
    """The stations the map lays a road's ribbons on (`citygen.pavement.road_faces`: its
    vertices and every `pavement.STEP_M` or less between its cuts, each ribbon piece
    between the bends where a band folds), to the millimeter."""
    from citygen import pavement as CPV
    try:
        r = CPV.Road(seg)
    except (ValueError, ZeroDivisionError):
        return []
    L = r.path.L
    s0, s1 = cuts[0], L - cuts[1]
    if s1 - s0 < 0.001:
        return []
    out, cur = [], s0
    for a, b in r.folds(s0, s1):
        if a > cur + 0.001:
            out += r.path.stations(cur, a)
        cur = b
    if s1 > cur + 0.001:
        out += r.path.stations(cur, s1)
    return sorted({round(v, 4) for v in out})


def row_uvs(seg: dict, stations) -> dict:
    """UV0 of a road's ribbon vertices: {(x, y) mm: (station, offset)}, each the map's point
    at a station and a band offset (`citygen.pavement.Road`, as the map lays them), so a
    face's UV runs along the road without the squeeze a projection onto the centerline has
    outside a turn."""
    from citygen import pavement as CPV
    try:
        r = CPV.Road(seg)
    except (ValueError, ZeroDivisionError):
        return {}
    out = {}
    for sv in stations:
        for w in r.ws:
            out.setdefault(r.path.point(sv, w), (sv, w))
    return out


def face_uv(path: Path, rows: dict):
    """UV0 of a road face's vertex: its row's (station, offset), else its projection."""
    def uv(x, y):
        got = rows.get((int(round(x * 1000.0)), int(round(y * 1000.0))))
        return got if got is not None else path.project(x, y)
    return uv


def gather(cx: Ctx, s) -> Piece:
    did = s.district_ids[0] if s.district_ids else s.attrs.get("district")
    ends = []
    for which, nid in (("start", s.start), ("end", s.end)):
        node = cx.node.get(nid)
        e = {"at": which}
        j = cx.junction_at.get(nid)
        if j is not None:
            legs = cx.seg_at_node[nid]
            top = max((RANK[street_class(o)] for o in legs if o.id != s.id), default=0)
            e["junction"] = {"id": j.id, "signalized": j.signalized, "legs": j.legs,
                             "shape": j.shape, "minor": RANK[street_class(s)] < top}
        if node is not None:
            e["node_z"] = node.position[2]
        ends.append(e)
    xings = []
    for c in sorted(cx.cross_on.get(s.id, ()), key=lambda c: c.id):
        j = cx.idx.get(c.junction_id)
        xings.append({"id": c.id, "line": [list(p) for p in c.line], "width": c.width_m,
                      "node": j.node_id if j is not None else None})
    lanes = []
    for ln in sorted(cx.lanes.get(s.id, ()), key=lambda ln: ln.id):
        lanes.append({"forward": ln.forward, "index": ln.index, "width": ln.width_m,
                      "line": [[p[0], p[1]] for p in ln.centerline]})
    seg = dump(s)
    seg.pop("district_ids", None)
    cuts = list(cx.cuts.get(s.id, (0.0, 0.0)))
    inputs = {"seg": seg, "cls": street_class(s), "ends": ends, "crossings": xings,
              "lanes": lanes, "style": cx.style(did), "start": s.start, "end": s.end,
              "origin": list(bbox_center(s.centerline)), "cuts": cuts}
    if "ground" not in seg and not cx.ground.flat:
        inputs["ground_pts"] = cx.ground.samples(s.centerline)
    if cx.pave.on:
        inputs["faces"] = [cx.pave.face_input(f) for f in road_face_ids(cx, s)]
        try:
            inputs["ports"] = port_lines(cx, s, Path(s.centerline), cuts)
        except ValueError:
            pass
        inputs["stations"] = map_stations(seg, cuts)
    if s.attrs.get("role") == "deck_ramp":
        # M14 (AG10): the walkways beside a deck's ramp, which the ramp carries
        inputs["ramp_walks"] = [{"id": w.id, "line": [list(p) for p in w.line]}
                                for w in cx.ramp_walks.get(s.id, ())]
    # M18: the model's embankments under its low stretches (the piece stands for them)
    emb = sorted((st for st in cx.m.structures if st.kind == "embankment" and
                  (st.attrs or {}).get("road_id") == s.id), key=lambda st: st.id)
    if emb:
        inputs["embankments"] = [[st.attrs["s0_m"], st.attrs["s1_m"]] for st in emb]
    # (#95, AG17: where each barrier runs and how it ends, `barriers.road_runs`)
    from . import barriers as BR
    if cx.pave.on and not cx.pave.faces_of(s.id):
        inputs["barriers"] = []     # (no faces: a cluster's inner road, wholly inside it)
    elif BR.runs_of(inputs["seg"], inputs["cls"]):
        by: set = set()
        inputs["barriers"] = BR.road_runs(cx, s, inputs, by=by)
        inputs["barriers_by"] = sorted(by - {s.id})
    return Piece(s.id, "street.road", "road", cx.tile_for(s.id, s.centerline),
                 cx.keys.get(s.id, []), inputs, covers=[st.id for st in emb])


# ---------------------------------------------------------------------------
# Make
# ---------------------------------------------------------------------------

class Road:
    """A segment's geometry: its path, its cuts (where its faces end, M22), its port lines,
    and the heights of its faces as drawn (`surf`, else its profile)."""

    def __init__(self, inp: dict):
        self.inp = inp
        self.seg = seg = inp["seg"]
        self.cls = inp["cls"]
        self.cs = cs = seg["cross_section"]
        self.path = Path(seg["centerline"])
        self.zp = Profile.of(seg.get("z_profile"))
        g = seg.get("ground")
        if g:
            self.gp = Profile.of(g)
        elif inp.get("ground_pts"):
            self.gp = Profile(list(zip(self.path.cum, inp["ground_pts"]))) \
                if len(inp["ground_pts"]) == len(self.path.p) else Profile([])
        else:
            self.gp = Profile([])
        self.W = seg["width_m"]
        self.side = cs["sidewalk_m"][0]
        self.h = self.W / 2.0 if self.cls in PEDESTRIAN else self.W / 2.0 - self.side
        self.L = self.path.L
        cuts = inp.get("cuts") or (0.0, 0.0)
        self.s0 = min(max(float(cuts[0]), 0.0), self.L)
        self.s1 = max(self.L - float(cuts[1]), self.s0)
        self.ports = inp.get("ports") or {}
        self.surf = None
        # (the map's stations along it, where its faces' heights turn, so marks and
        # barriers drawn row by row follow them exactly)
        self.map_s = list(inp.get("stations") or ())

    def z(self, s: float) -> float:
        """Its surface at s from its profile (ground plus profile plus `ROAD_DZ`)."""
        return self.gp(s) + self.zp(s) + ROAD_DZ

    def zxy(self, x: float, y: float) -> float:
        """Its surface at a point as drawn (its faces), else from its profile."""
        if self.surf:
            z = self.surf.z(x, y)
            if z is not None:
                return z
        return self.z(self.path.project(x, y)[0])

    def ground(self, s: float) -> float:
        return self.gp(s)

    def knots(self, s0: float, s1: float) -> list[float]:
        if self.map_s:
            return [s for s in self.map_s if s0 < s < s1]
        return self.zp.knots(s0, s1) + self.gp.knots(s0, s1)

    def at(self, s: float, t: float, vi=None):
        x, y, nx, ny, k = self.path.frame(s, vi)
        return x + nx * k * t, y + ny * k * t

    def xy(self, s: float, t: float):
        """(x, y) for a small decal: the plain segment normal, no miter."""
        x, y, nx, ny, _ = self.path.frame(s)
        return x + nx * t, y + ny * t

    def port_frame(self, at: str, z: float):
        """The frame on the road's port at one end (its section offsets land on the port
        line the map stores), or None where the map has none there."""
        pl = self.ports.get(at)
        if not pl:
            return None
        R, Lp = pl
        dx, dy = Lp[0] - R[0], Lp[1] - R[1]
        n = (dx * dx + dy * dy) ** 0.5
        if n < 1e-6:
            return None
        k = n / self.W
        s = self.s0 if at == "start" else self.s1
        return ((R[0] + Lp[0]) / 2.0, (R[1] + Lp[1]) / 2.0, z, dx / n, dy / n, k, s)

    def stations(self, s0, s1, step=STEP_M, extra=()):
        return self.path.stations(s0, s1, step, list(extra) + self.knots(s0, s1))

    def strip(self, mesh: Mesh, slot: str, s0: float, s1: float, t0: float, t1: float,
              dz: float = 0.0, step: float = STEP_M, flip: bool = False, drawn: bool = True):
        """A surface from s0 to s1 between offsets t0 < t1, dz over the road (its faces as
        drawn, or its profile: `drawn` False)."""
        if s1 - s0 < 0.01:
            return
        rows, uvs = [], []
        for s, vi in self.stations(s0, s1, step):
            row = []
            for t in (t0, t1):
                x, y = self.at(s, t, vi)
                row.append((x, y, (self.zxy(x, y) if drawn else self.z(s)) + dz))
            rows.append(row)
            uvs.append([(s, t0), (s, t1)])
        mesh.grid(slot, rows, uvs, flip=flip, expect=(0.0, 0.0, -1.0 if flip else 1.0))

    def decal(self, mesh: Mesh, slot: str, ring_st, dz: float):
        """A flat mark given in (s, t) on the road, on its faces as drawn."""
        def fmap(s, t):
            x, y = self.xy(s, t)
            return x, y, self.zxy(x, y) + dz
        mesh.poly_map(slot, ring_st, (), fmap)

    def sweep(self, mesh: Mesh, slot: str, s0: float, s1: float, profile, base=0.0,
              tc: float = 0.0, step: float = STEP_M, drawn: bool = False, ends=None):
        """A cross-section (t, dz) swept from s0 to s1 around offset tc, dz over the road
        plus base (its faces as drawn at the section's middle where `drawn`); `ends`: frames
        to put at its first and last station (a port line)."""
        frames = []
        for s, vi in self.stations(s0, s1, step):
            x, y, nx, ny, k = self.path.frame(s, vi)
            px, py = x + nx * k * tc, y + ny * k * tc
            z = (self.zxy(px, py) if drawn else self.z(s)) + base
            frames.append((px, py, z, nx, ny, k, s))
        if ends:
            for idx, fr in ((0, ends[0]), (-1, ends[1])):
                if fr is not None:
                    frames[idx] = fr
        if len(frames) >= 2:
            mesh.sweep(slot, frames, profile)
        return frames


def face_slot(fi: dict, cls: str, style: dict):
    """The slot a road face is drawn in (a raised median: its top, asphalt where it is level
    with the road)."""
    k = fi["kind"]
    if k == "median" and fi["cls"] == "median":
        top = "lawn" if _median_w(fi) >= 2.0 and style["era"] not in ("industrial",
                                                                     "aerospace") \
            else "concrete"
        asph = asphalt_slot(cls, style)
        level = {(p[0], p[1]) for r in fi["rings"] for p in r
                 if p[2] - p[3] == PV.ROAD_DZ_MM}

        def by_tri(tri):
            return asph if all((p[0], p[1]) in level for p in tri) else top
        return by_tri
    if k in ("curb",):
        return MT.curb(style["archetype"])
    if k in ("sidewalk",):
        return MT.paving(style["archetype"])
    if k == "walk":
        return asphalt_slot(cls, style) if cls in PEDESTRIAN else MT.paving(style["archetype"])
    return asphalt_slot(cls, style)


def _median_w(fi: dict) -> float:
    return float(fi.get("median_m", 2.0))


@maker("road", 3)
def make(inp: dict) -> Out:
    try:
        rd = Road(inp)
    except ValueError:
        return Out(empty="degenerate centerline")
    seg, cls, style = rd.seg, rd.cls, inp["style"]
    mesh = Mesh(inp["origin"])
    dk = deck_kind(seg)
    out = Out(mesh=mesh)
    embs = [(max(a, rd.s0), min(b, rd.s1)) for a, b in inp.get("embankments", ())
            if min(b, rd.s1) - max(a, rd.s0) >= 0.5]
    rd.surf = _faces(rd, mesh, inp, dk, embs)
    if rd.surf and rd.s1 - rd.s0 >= 0.3 and cls not in PEDESTRIAN:
        stops = _markings(rd, mesh, inp)
        _details(rd, mesh, inp, stops)
    _barriers(rd, mesh, inp)
    if dk == "deck":
        # AG14: M18's embankments carry the road where it is low; the deck's girder only
        # between them, and (AG17) only between its cuts: a raised junction stands on its
        # own slab
        _deck(rd, mesh, inp, _spans(rd.s0, rd.s1, embs))
        for a, b in embs:
            _embankment_ends(rd, mesh, a, b)
    elif dk == "ramp":
        out.notes["walkways"] = _deck_ramp(rd, mesh, inp)
    if not mesh.triangles:
        return Out(empty="inside its junctions")
    return out


def _faces(rd: Road, mesh: Mesh, inp: dict, dk: str, embs) -> PV.Surface:
    """The road's faces (`pave.draw`) with their curbs and outer walls; their triangles."""
    surf = PV.Surface()
    style = inp["style"]
    curb = MT.curb(style["archetype"])
    med = rd.cs.get("median_m", 0.0) or 0.0

    uv = face_uv(rd.path, row_uvs(rd.seg, inp.get("stations") or ()))
    bottom, out_slot = PV.bottoms(dk, rd.path, embs)
    specs: list = []
    for fi in inp.get("faces", ()):
        fi = dict(fi, median_m=med)
        slot = face_slot(fi, rd.cls, style)
        if fi["kind"] == "bend" and rd.cls not in PEDESTRIAN and rd.h < rd.W / 2.0 - 0.05:
            fi, slot = _bend(rd, fi, slot, MT.paving(style["archetype"]))
        # (a bend's UV in plan: no row runs through a fold)
        tris = PV.draw(mesh, fi, slot, None if fi["kind"] == "bend" else uv)
        for t in tris:
            surf.add(t)
        wslot = out_slot or (slot if isinstance(slot, str) else curb)
        PV.walls(mesh, fi, wslot, bottom, curb_slot=curb, out=specs)
    PV.draw_walls(mesh, specs)
    return surf


CURB_STEP_M = 1.0       # a bend's curb lines as Steiner points this far apart


def _bend(rd: Road, fi: dict, asphalt: str, paving: str):
    """A bend face (M22: a road's stretch where a band would fold, its whole right of way
    one face at the carriageway's height): its curb lines (the road's offsets at its
    carriageway's half width) as Steiner points strictly inside, so its triangles part
    there; asphalt between them, the district's paving outside (its sidewalks, level with
    the road: no building or barrier check takes them for the carriageway)."""
    import shapely
    rings = [[(p[0] / 1000.0, p[1] / 1000.0) for p in r] for r in fi["rings"]]
    g = shapely.Polygon(rings[0], rings[1:])
    if not g.is_valid:
        g = shapely.make_valid(g)
    inner = g.buffer(-0.05)
    ss = [rd.path.project(x, y)[0] for r in rings for x, y in r]
    a, b = min(ss), max(ss)
    if inner.is_empty or b - a < 0.5:
        return fi, asphalt
    base = PV.Surface()
    P_, tris = PV.triangles(fi)
    for t in tris:
        base.add((P_[t[0]], P_[t[1]], P_[t[2]]))
    extra = []
    n = max(1, int((b - a) / CURB_STEP_M))
    for k in range(n + 1):
        s = a + (b - a) * k / n
        for t in (-rd.h, rd.h):
            x, y = rd.at(s, t)
            if not inner.contains(shapely.Point(x, y)):
                continue
            z = base.z(x, y)
            if z is not None:
                extra.append([PV.mm(x), PV.mm(y), PV.mm(z)])
    fi = dict(fi, samples=list(fi.get("samples", ())) + extra)
    h = rd.h + 0.05

    def slot(tri):
        # (asphalt only where the whole triangle is within the carriageway's half width)
        far = max(abs(rd.path.project(p[0] / 1000.0, p[1] / 1000.0)[1]) for p in tri)
        return asphalt if far <= h else paving
    return fi, slot


# -- markings -------------------------------------------------------------------------

def _lanes(rd: Road, inp: dict) -> list[dict]:
    out = []
    for ln in inp["lanes"]:
        line = ln["line"]
        if len(line) < 2:
            continue
        mid = line[len(line) // 2]
        if len(line) % 2 == 0:
            a, b = line[len(line) // 2 - 1], line[len(line) // 2]
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        _, t = rd.path.project(mid[0], mid[1])
        out.append({"t": t, "w": ln["width"], "fwd": ln["forward"], "index": ln["index"]})
    out.sort(key=lambda r: (r["t"], r["fwd"], r["index"]))
    return out


def _line(rd: Road, mesh: Mesh, slot: str, s0: float, s1: float, t: float, w: float,
          dash=None, phase: float = 0.0):
    if s1 - s0 < 0.2:
        return
    if dash is None:
        rd.strip(mesh, slot, s0, s1, t - w / 2.0, t + w / 2.0, MARK_DZ)
        return
    d, g = dash
    a = s0 + phase * (d + g)
    if a - (d + g) >= s0:
        a -= d + g
    while a < s1:
        b = min(a + d, s1)
        if b - max(a, s0) > 0.3:
            rd.strip(mesh, slot, max(a, s0), b, t - w / 2.0, t + w / 2.0, MARK_DZ)
        a += d + g


def _stop_s(rd: Road, inp: dict, at: str) -> float | None:
    """Where a stop line goes at an end: before the crosswalk at that end, else 1.5 m from
    the cut."""
    node = inp["start"] if at == "start" else inp["end"]
    best = None
    for x in inp["crossings"]:
        if x["node"] != node:
            continue
        a, b = x["line"][0], x["line"][-1]
        s, _ = rd.path.project((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if at == "start":
            v = s + x["width"] / 2.0 + 1.2
            best = v if best is None else max(best, v)
        else:
            v = s - x["width"] / 2.0 - 1.2
            best = v if best is None else min(best, v)
    if best is None:
        best = rd.s0 + 1.5 if at == "start" else rd.s1 - 1.5
    if not (rd.s0 + 0.5 < best < rd.s1 - 0.5):
        return None
    return best


def _markings(rd: Road, mesh: Mesh, inp: dict) -> dict:
    """Lane lines, center lines, edge lines, stop lines and arrows; returns the stop line
    positions."""
    cls = rd.cls
    lanes = _lanes(rd, inp)
    shared = rd.cs.get("shared") or cls == "alley"
    stops: dict = {}
    ends = {e["at"]: e for e in inp["ends"]}
    for at in ("start", "end"):
        j = ends.get(at, {}).get("junction")
        if j is None or cls == "highway" or shared or not lanes:
            continue
        if not (j["signalized"] or j["minor"] or any(
                x["node"] == (inp["start"] if at == "start" else inp["end"])
                for x in inp["crossings"])):
            continue
        s = _stop_s(rd, inp, at)
        if s is not None:
            stops[at] = s
    if shared or not lanes:
        return stops
    sa = stops.get("start", rd.s0 + 1.0)
    sb = stops.get("end", rd.s1 - 1.0)
    if sb - sa < 1.0:
        return stops
    W_ = "marking.white"
    Y_ = "marking.yellow"
    dash = DASH.get(cls, (3.0, 6.0))
    ph = rnd(inp["seg"]["id"], "dash")
    for a, b in zip(lanes, lanes[1:]):
        tb = (a["t"] + b["t"]) / 2.0
        gap = (b["t"] - b["w"] / 2.0) - (a["t"] + a["w"] / 2.0)
        if a["fwd"] == b["fwd"]:
            _line(rd, mesh, W_, sa, sb, tb, 0.15, dash, ph)
        elif gap > 0.6:
            if cls == "highway":
                _line(rd, mesh, Y_, sa, sb, a["t"] + a["w"] / 2.0 + 0.2, 0.15)
                _line(rd, mesh, Y_, sa, sb, b["t"] - b["w"] / 2.0 - 0.2, 0.15)
        elif cls in ("avenue", "highway"):
            _line(rd, mesh, Y_, sa, sb, tb - 0.12, 0.12)
            _line(rd, mesh, Y_, sa, sb, tb + 0.12, 0.12)
        else:
            _line(rd, mesh, Y_, sa, sb, tb, 0.12, dash, ph)
    lo, hi = lanes[0], lanes[-1]
    if cls == "highway":
        _line(rd, mesh, W_, sa, sb, lo["t"] - lo["w"] / 2.0 + 0.15, 0.15)
        _line(rd, mesh, W_, sa, sb, hi["t"] + hi["w"] / 2.0 - 0.15, 0.15)
    elif cls == "avenue":
        if lo["t"] - lo["w"] / 2.0 > -rd.h + 1.2:
            _line(rd, mesh, W_, sa, sb, lo["t"] - lo["w"] / 2.0, 0.12)
        if hi["t"] + hi["w"] / 2.0 < rd.h - 1.2:
            _line(rd, mesh, W_, sa, sb, hi["t"] + hi["w"] / 2.0, 0.12)
    # stop lines and arrows on the lanes coming in at each end
    for at, s in sorted(stops.items()):
        inbound = [ln for ln in lanes if ln["fwd"] == (at == "end")]
        if not inbound:
            continue
        t0 = min(ln["t"] - ln["w"] / 2.0 for ln in inbound)
        t1 = max(ln["t"] + ln["w"] / 2.0 for ln in inbound)
        sgn = 1.0 if at == "start" else -1.0
        rd.decal(mesh, W_, [(s, t0), (s, t1), (s + 0.4 * sgn, t1), (s + 0.4 * sgn, t0)]
                 if sgn < 0 else [(s, t0), (s + 0.4, t0), (s + 0.4, t1), (s, t1)], MARK_DZ)
        j = ends[at].get("junction") or {}
        if not j.get("signalized") or rd.s1 - rd.s0 < 35.0:
            continue
        # inbound lanes by their distance from the middle of the road: innermost first
        order = sorted(inbound, key=lambda ln: (abs(ln["t"]), ln["index"]))
        for k, ln in enumerate(order):
            kind = "straight"
            if len(order) >= 2 and j.get("legs", 3) >= 3:
                kind = "left" if k == 0 else ("right" if k == len(order) - 1 else "straight")
            tip = s + sgn * 6.0
            _arrow(rd, mesh, tip, ln["t"], -sgn, kind)
    return stops


ARROW = {
    "straight": [(0.0, 0.0), (-1.2, 0.3), (-1.2, 0.08), (-4.8, 0.08), (-4.8, -0.08),
                 (-1.2, -0.08), (-1.2, -0.3)],
    "left": [(-4.8, -0.08), (-1.44, -0.08), (-1.44, 0.9), (-1.2, 0.9), (-1.6, 1.5),
             (-2.0, 0.9), (-1.76, 0.9), (-1.76, 0.08), (-4.8, 0.08)],
}
ARROW["right"] = [(a, -c) for a, c in reversed(ARROW["left"])]


def _arrow(rd: Road, mesh: Mesh, tip_s: float, t: float, sgn: float, kind: str):
    """An arrow on a lane, its tip at tip_s, pointing along +s (sgn 1) or -s (-1); (a, c)
    in the arrow's frame: a along travel, c to the left of travel."""
    ring = [(tip_s + sgn * a, t + sgn * c) for a, c in ARROW[kind]]
    rd.decal(mesh, "marking.white", ring, MARK_DZ)


def _details(rd: Road, mesh: Mesh, inp: dict, stops: dict):
    """Manholes on the lanes, drains at the curbs, patches by the district's grime."""
    sid = inp["seg"]["id"]
    style = inp["style"]
    sa = stops.get("start", rd.s0) + 3.0
    sb = stops.get("end", rd.s1) - 3.0
    L = sb - sa
    if L < 4.0:
        return
    lanes = _lanes(rd, inp)
    n = int(L / 45.0)
    for k in range(n):
        s = sa + L * (k + 0.5 + 0.4 * (rnd(sid, "mh", k) - 0.5)) / n
        if lanes:
            ln = lanes[int(rnd(sid, "mhl", k) * len(lanes)) % len(lanes)]
            t = ln["t"]
        else:
            t = 0.0
        ring = [(s + 0.4 * M.cos(2 * M.PI * i / 12), t + 0.4 * M.sin(2 * M.PI * i / 12))
                for i in range(12)]
        rd.decal(mesh, "manhole", ring, MARK_DZ + 0.001)
    if rd.cls != "highway" and rd.h > 2.5:
        n = int(L / 35.0)
        for k in range(n):
            s = sa + L * (k + 0.5) / n
            for sgn in (-1.0, 1.0):
                t = sgn * (rd.h - 0.3)
                rd.decal(mesh, "grate", [(s - 0.45, t - 0.2), (s + 0.45, t - 0.2),
                                         (s + 0.45, t + 0.2), (s - 0.45, t + 0.2)],
                         MARK_DZ + 0.001)
    rate = 3.0 * style["grime"] * style.get("wear", 1.0)
    n = int(L / 100.0 * rate + rnd(sid, "pn"))
    for k in range(n):
        s = sa + L * rnd(sid, "ps", k)
        la = 1.5 + 3.5 * rnd(sid, "pl", k)
        ac = 0.8 + 1.7 * rnd(sid, "pw", k)
        t = (-rd.h + 0.6 + ac / 2.0) + (2.0 * rd.h - 1.2 - ac) * rnd(sid, "pt", k)
        if 2.0 * rd.h - 1.2 - ac <= 0:
            continue
        s0, s1 = max(s - la / 2.0, sa), min(s + la / 2.0, sb)
        if s1 - s0 < 0.5:
            continue
        rd.decal(mesh, "asphalt.patch", [(s0, t - ac / 2.0), (s1, t - ac / 2.0),
                                         (s1, t + ac / 2.0), (s0, t + ac / 2.0)], PATCH_DZ)


# -- barriers --------------------------------------------------------------------------

def _barriers(rd: Road, mesh: Mesh, inp: dict):
    """The road's barriers (a highway's median barrier and an at-grade highway's guard
    walls, a raised road's parapets, a deck ramp's barriers and parapets) over the spans
    `barriers.road_runs` gave them, ending on its ports (AG17); a road gathered without
    them (a bridge's own deck) from cut to cut, closed at both ends."""
    from . import barriers as BR
    runs = BR.runs_of(rd.seg, rd.cls)
    if not runs:
        return
    given = {r["name"]: r for r in inp.get("barriers", ())}
    for run in runs:
        if "barriers" in inp:
            g = given.get(run.name)
            if not g:
                continue
            spans = g["spans"]
        else:
            spans = [[rd.s0, rd.s1, "stop", "stop"]]
        BR.draw_run(mesh, rd, run, spans)


# -- decks and embankments -------------------------------------------------------------

def _spans(s0: float, s1: float, holes) -> list[tuple[float, float]]:
    """[s0, s1] less the intervals `holes` (sorted, merged), pieces of 0.05 m or more."""
    out, at = [], s0
    for a, b in sorted(holes):
        if a > at:
            out.append((at, min(a, s1)))
        at = max(at, b)
    if at < s1:
        out.append((at, s1))
    return [(a, b) for a, b in out if b - a >= 0.05]


def _deck(rd: Road, mesh: Mesh, inp: dict, spans=None):
    """A raised road's box girder under its faces (whose outer edges carry the fascia,
    `_faces`), from cut to cut, closed at both ends; its expansion joints and underside
    lights."""
    cls = rd.cls
    # (its soffit from the fascia's foot, `GIRDER_LIP_M` past it, so no slit shows between
    # the two where the map's mitres and the girder's differ by a millimeter)
    W2 = rd.W / 2.0 + GIRDER_LIP_M
    a = rd.seg.get("attrs", {})
    # viaducts and ramps stand on M7's columns, whose tops are 1.8 m under the road
    D = 1.8 if a.get("elevated") or a.get("role") == "ramp" else DECK_D.get(cls, 1.2)
    B = max(rd.W * 0.55, 2.0)
    F = PV.FASCIA_MM / 1000.0
    prof = [(W2, -F), (B / 2.0, -max(min(0.7, D * 0.6), F + 0.05)),
            (B / 2.0 - 0.25, -D), (-(B / 2.0 - 0.25), -D),
            (-B / 2.0, -max(min(0.7, D * 0.6), F + 0.05)), (-W2, -F)]
    from . import barriers as BR
    for a_, b_ in (spans if spans is not None else [(rd.s0, rd.s1)]):
        if b_ - a_ < 0.05:
            continue
        ends = []
        for s_ in (a_, b_):
            at = "start" if abs(s_ - rd.s0) < 1e-6 else ("end" if abs(s_ - rd.s1) < 1e-6
                                                         else None)
            fr = None
            if at is not None:
                x, y = rd.path.point(s_)
                fr = rd.port_frame(at, rd.zxy(x, y) - ROAD_DZ)
            ends.append(fr)
        frames = rd.sweep(mesh, "concrete.deck", a_, b_, prof, base=-ROAD_DZ, drawn=True,
                          ends=ends)
        if len(frames) >= 2:
            ring = prof + [prof[0]]
            BR.cap(mesh, "concrete.deck", frames[0], ring[:-1], 1.0, -1.0)
            BR.cap(mesh, "concrete.deck", frames[-1], ring[:-1], 1.0, 1.0)
    sid = inp["seg"]["id"]
    if cls not in PEDESTRIAN and rd.s1 - rd.s0 > 10.0:
        s = rd.s0 + 45.0 * rnd(sid, "joint")
        while s < rd.s1 - 1.0:
            if rd.zp(s) > 1.0 and s > rd.s0 + 1.0:
                rd.decal(mesh, "steel.joint", [(s - 0.15, -rd.h), (s + 0.15, -rd.h),
                                               (s + 0.15, rd.h), (s - 0.15, rd.h)],
                         MARK_DZ - 0.001)
            s += 45.0
    s = rd.s0 + 7.5
    while s < rd.s1 - 1.0:
        if rd.zp(s) > 4.0:
            x, y = rd.path.point(s)
            z = rd.zxy(x, y) - ROAD_DZ - D - 0.02
            ring = [(s - 0.4, -0.15), (s - 0.4, 0.15), (s + 0.4, 0.15), (s + 0.4, -0.15)]
            mesh.poly_map("light", ring, (), lambda u, v, z=z: (*rd.xy(u, v), z))
        s += 15.0


RAMP_WALK_M = 2.0       # M14's walkway beside each side of a deck's ramp
RAMP_PARAPET_M = 0.25
RAMP_PARAPET_H = 1.1


def _deck_ramp(rd: Road, mesh: Mesh, inp: dict) -> dict:
    """M14's ramp up to a deck (AG10): a walkway on each side at curb height (the model's
    walkways beside it), and the solid ramp's walls down to the ground on both sides (up to
    the walkways) and across its raised ends; its barriers at the carriageway's edges and
    the parapets outside the walkways are runs (`barriers.runs_of`, `_barriers`).
    Returns the walkways' lines put on the ramp (z over the ground, as the model's)."""
    W2 = rd.W / 2.0
    pave = MT.paving(inp["style"]["archetype"])
    wi, wo = W2 + RAMP_WALK_M, W2 + RAMP_WALK_M + RAMP_PARAPET_M
    rd.strip(mesh, pave, rd.s0, rd.s1, W2, wi, 0.15, drawn=False)
    rd.strip(mesh, pave, rd.s0, rd.s1, -wi, -W2, 0.15, drawn=False)
    for side in (1.0, -1.0):
        rows, uvs, exp = [], [], []
        for s, vi in rd.stations(rd.s0, rd.s1):
            x, y = rd.at(s, side * wo, vi)
            _, _, nx, ny, _ = rd.path.frame(s, vi)
            zt, zb = rd.z(s) + 0.15, rd.ground(s) - 0.1
            col = [(x, y, zt), (x, y, zb)] if side > 0 else [(x, y, zb), (x, y, zt)]
            rows.append(col)
            uvs.append([(s, zt), (s, zb)] if side > 0 else [(s, zb), (s, zt)])
            exp.append((side * nx, side * ny, 0.0))
        mesh.grid("concrete", rows, uvs, expect=exp)
    # (its raised ends: the ramp's body across, from the ground to the road)
    for s, sgn in ((rd.s0, -1.0), (rd.s1, 1.0)):
        zr, zg = rd.z(s) - ROAD_DZ, rd.ground(s) - 0.1
        if zr - zg < 0.4:
            continue
        x0, y0 = rd.xy(s, -wo)
        x1, y1 = rd.xy(s, wo)
        a, b = ((x0, y0), (x1, y1)) if sgn > 0 else ((x1, y1), (x0, y0))
        mesh.wall("concrete", a, b, zg, zr, zg, zr)
    out = {}
    for w in inp.get("ramp_walks", ()):
        line = []
        for p in w["line"]:
            s, _ = rd.path.project(p[0], p[1])
            z = rd.zp(s) + ROAD_DZ + 0.15 if rd.s0 < s < rd.s1 else p[2]
            line.append([p[0], p[1], C.m(z)])
        out[w["id"]] = line
    return out


def _embankment_ends(rd: Road, mesh: Mesh, s0: float, s1: float):
    """AG14: an M18 embankment's faces across a deck road where its girder goes on (where
    the road is raised 0.3 m or more there); its sides are the faces' outer walls."""
    W2 = rd.W / 2.0
    for s, sgn in ((s0, -1.0), (s1, 1.0)):
        if (sgn < 0 and s <= rd.s0 + 0.05) or (sgn > 0 and s >= rd.s1 - 0.05):
            continue
        x, y = rd.path.point(s)
        top = rd.zxy(x, y) - ROAD_DZ
        bot = rd.ground(s) - 0.1
        if top - bot < 0.4:
            continue
        pa, pb = rd.at(s, -W2), rd.at(s, W2)
        a_, b_ = (pa, pb) if sgn > 0 else (pb, pa)
        mesh.wall("concrete", a_, b_, bot, top, bot, top)


__all__ = ["gather", "make", "Road", "street_class", "deck_kind", "ROAD_DZ", "unit",
           "road_face_ids", "walk_sides", "port_lines"]
