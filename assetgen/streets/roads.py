"""Road segments: the carriageway between its junctions' cut-backs, lane markings from the
model's lanes (lane lines, center lines, edge lines, stop lines, arrows), patches, manholes
and drains, medians (curbed islands with lawn, or a barrier on highways), and under a
raised road its deck (a box girder with parapets, expansion joints and underside lights)
or, for a low street ramp, an embankment.

UV0 runs along the road: u the distance along the centerline, v the offset across it
(meters), as AG6's road atlases expect.
"""

from __future__ import annotations

from citygen import dmath as M

from .. import canon as C
from . import materials as MT
from .ctx import Ctx, bbox_center, dump
from .kit import Mesh, ccw
from .kit import check as mesh_check
from .path import Path, Profile, first_exit, unit
from .pieces import Out, Piece, maker, rnd

ROAD_DZ = 0.05          # road surface over its grade line (the blockout's ground is at 0)
MARK_DZ = 0.004         # paint over the asphalt
PATCH_DZ = 0.002
STEP_M = 6.0
EMBANKMENT_M = 3.0      # a raised street no higher than this stands on an embankment
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

def gather(cx: Ctx, s) -> Piece:
    did = s.district_ids[0] if s.district_ids else s.attrs.get("district")
    others = []
    ends = []
    for which, nid in (("start", s.start), ("end", s.end)):
        node = cx.node.get(nid)
        e = {"at": which}
        j = cx.junction_at.get(nid)
        if j is not None:
            legs = cx.seg_at_node[nid]
            top = max((RANK[street_class(o)] for o in legs if o.id != s.id), default=0)
            e["junction"] = {"id": j.id, "ring": [list(p) for p in j.polygon.exterior],
                             "signalized": j.signalized, "legs": j.legs, "shape": j.shape,
                             "minor": RANK[street_class(s)] < top}
        if node is not None:
            e["node_z"] = node.position[2]
        ends.append(e)
        others.append(nid)
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
    inputs = {"seg": seg, "cls": street_class(s), "ends": ends, "crossings": xings,
              "lanes": lanes, "style": cx.style(did), "start": s.start, "end": s.end,
              "origin": list(bbox_center(s.centerline))}
    if "ground" not in seg and not cx.ground.flat:
        inputs["ground_pts"] = cx.ground.samples(s.centerline)
    if s.attrs.get("role") == "deck_ramp":
        # M14 (AG10): the walkways beside a deck's ramp, which the ramp carries
        inputs["ramp_walks"] = [{"id": w.id, "line": [list(p) for p in w.line]}
                                for w in cx.ramp_walks.get(s.id, ())]
    # M18: the model's embankments under its low stretches (the piece stands for them)
    emb = sorted((st for st in cx.m.structures if st.kind == "embankment" and
                  (st.attrs or {}).get("road_id") == s.id), key=lambda st: st.id)
    if emb:
        inputs["embankments"] = [[st.attrs["s0_m"], st.attrs["s1_m"]] for st in emb]
    return Piece(s.id, "street.road", "road", cx.tile_for(s.id, s.centerline),
                 cx.keys.get(s.id, []), inputs, covers=[st.id for st in emb])


# ---------------------------------------------------------------------------
# Make
# ---------------------------------------------------------------------------

class Road:
    """A segment's geometry: its path, heights and the carriageway's ends."""

    def __init__(self, inp: dict, tidy: bool = False):
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
        if tidy:
            self.path = self.path.tidied()      # after the ground samples, which go by its vertices
        self.W = seg["width_m"]
        self.side = cs["sidewalk_m"][0]
        self.h = self.W / 2.0 if self.cls in PEDESTRIAN else self.W / 2.0 - self.side
        self.L = self.path.L
        self.s0, self.s1 = 0.0, self.L
        self.cut = {}
        for e in inp["ends"]:
            j = e.get("junction")
            if j is None:
                continue
            ring = ccw(j["ring"])
            pp = self.path.p if e["at"] == "start" else self.path.p[::-1]
            r = first_exit(pp, ring)
            if r is None:
                continue
            s, i, _ = r
            a, b = ring[i], ring[(i + 1) % len(ring)]
            s = min(s, self.L)
            if e["at"] == "start":
                self.s0 = s
                self.cut["start"] = self._edge(s, a, b)
            else:
                self.s1 = self.L - s
                self.cut["end"] = self._edge(self.L - s, a, b)

    def _edge(self, s, a, b):
        """The junction's cut edge as (right point, left point) when it spans the
        carriageway, else None (a perpendicular cut)."""
        x, y = self.path.point(s)
        tx, ty = self.path.tangent(s)
        ta = -ty * (a[0] - x) + tx * (a[1] - y)
        tb = -ty * (b[0] - x) + tx * (b[1] - y)
        L, R = (a, b) if ta > tb else (b, a)
        tl, tr = max(ta, tb), min(ta, tb)
        if abs(tl - self.h) > 0.35 or abs(tr + self.h) > 0.35:
            return None
        return (R, L)

    def z(self, s: float) -> float:
        return self.gp(s) + self.zp(s) + ROAD_DZ

    def ground(self, s: float) -> float:
        return self.gp(s)

    def knots(self, s0: float, s1: float) -> list[float]:
        return self.zp.knots(s0, s1) + self.gp.knots(s0, s1)

    def at(self, s: float, t: float, vi=None):
        """World (x, y) at distance s and offset t; at the carriageway's ends on the
        junction's cut edge."""
        for key, se in (("start", self.s0), ("end", self.s1)):
            e = self.cut.get(key)
            if e is not None and abs(s - se) < 1e-9 and abs(t) <= self.h + 1e-9:
                R, Lp = e
                f = (t + self.h) / (2.0 * self.h)
                return R[0] + (Lp[0] - R[0]) * f, R[1] + (Lp[1] - R[1]) * f
        x, y, nx, ny, k = self.path.frame(s, vi)
        return x + nx * k * t, y + ny * k * t

    def xy(self, s: float, t: float):
        """(x, y) for a small decal: the plain segment normal, no miter."""
        x, y, nx, ny, _ = self.path.frame(s)
        return x + nx * t, y + ny * t

    def stations(self, s0, s1, step=STEP_M, extra=()):
        return self.path.stations(s0, s1, step, list(extra) + self.knots(s0, s1))

    def strip(self, mesh: Mesh, slot: str, s0: float, s1: float, t0: float, t1: float,
              dz: float = 0.0, step: float = STEP_M, flip: bool = False):
        """A surface from s0 to s1 between offsets t0 < t1, dz over the road."""
        if s1 - s0 < 0.01:
            return
        rows, uvs = [], []
        for s, vi in self.stations(s0, s1, step):
            z = self.z(s) + dz
            rows.append([(*self.at(s, t, vi), z) for t in (t0, t1)])
            uvs.append([(s, t0), (s, t1)])
        mesh.grid(slot, rows, uvs, flip=flip, expect=(0.0, 0.0, -1.0 if flip else 1.0))

    def decal(self, mesh: Mesh, slot: str, ring_st, dz: float):
        """A flat mark given in (s, t) on the road."""
        mesh.poly_map(slot, ring_st, (), lambda s, t: (*self.xy(s, t), self.z(s) + dz))

    def sweep(self, mesh: Mesh, slot: str, s0: float, s1: float, profile, base=0.0,
              tc: float = 0.0, step: float = STEP_M):
        """A cross-section (t, dz) swept from s0 to s1 around offset tc, dz over the road
        plus base."""
        frames = []
        for s, vi in self.stations(s0, s1, step):
            x, y, nx, ny, k = self.path.frame(s, vi)
            frames.append((x + nx * k * tc, y + ny * k * tc, self.z(s) + base, nx, ny, k, s))
        if len(frames) >= 2:
            mesh.sweep(slot, frames, profile)


@maker("road", 1)
def make(inp: dict) -> Out:
    """The road from its centerline as given; a road whose mesh fails the winding check (a
    micro-kink in the line folds its curb's offset lines over each other) is made again
    from the line without its micro-kinks."""
    out = _make(inp, False)
    if out.mesh is not None and mesh_check(out.mesh.slots)["winding"]:
        out = _make(inp, True)
    return out


def _make(inp: dict, tidy: bool) -> Out:
    try:
        rd = Road(inp, tidy)
    except ValueError:
        return Out(empty="degenerate centerline")
    seg, cls, style = rd.seg, rd.cls, inp["style"]
    mesh = Mesh(inp["origin"])
    dk = deck_kind(seg)
    out = Out(mesh=mesh)
    if rd.s1 - rd.s0 >= 0.3:
        rows, uvs = [], []
        for s, vi in rd.stations(rd.s0, rd.s1):
            z = rd.z(s)
            rows.append([(*rd.at(s, t, vi), z) for t in (-rd.h, rd.h)])
            uvs.append([(s, -rd.h), (s, rd.h)])
        mesh.grid(asphalt_slot(cls, style), rows, uvs, expect=UP)
        if cls not in PEDESTRIAN:
            stops = _markings(rd, mesh, inp)
            _details(rd, mesh, inp, stops)
            _median(rd, mesh, inp, stops)
    if dk == "deck":
        _deck(rd, mesh, inp)
        for a, b in inp.get("embankments", ()):
            if min(b, rd.s1) - max(a, rd.s0) >= 0.5:
                _embankment(rd, mesh, max(a, rd.s0), min(b, rd.s1))
    elif dk == "embankment":
        _embankment(rd, mesh)
    elif dk == "ramp":
        out.notes["walkways"] = _deck_ramp(rd, mesh, inp)
    if not mesh.triangles:
        return Out(empty="inside its junctions")
    return out


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
    positions (the medians stop there too)."""
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


# -- medians -------------------------------------------------------------------------

JERSEY = [(-0.3, 0.0), (-0.3, 0.08), (-0.15, 0.33), (-0.075, 0.81), (0.075, 0.81),
          (0.15, 0.33), (0.3, 0.08), (0.3, 0.0)]


def _median(rd: Road, mesh: Mesh, inp: dict, stops: dict):
    m = rd.cs.get("median_m", 0.0)
    cls = rd.cls
    if cls == "highway":
        if m > 0.0:
            rd.sweep(mesh, "concrete.barrier", rd.s0, rd.s1, JERSEY)
        if deck_kind(rd.seg) == "none":
            # guard walls along the outer edges of an at-grade highway
            for tc in (-rd.h + 0.35, rd.h - 0.35):
                rd.sweep(mesh, "concrete.barrier", rd.s0, rd.s1, JERSEY, tc=tc)
        return
    if m < 1.0 or cls not in ("avenue", "street", "service"):
        return
    sa = stops.get("start", rd.s0 + 1.0) + 1.0
    sb = stops.get("end", rd.s1 - 1.0) - 1.0
    if sb - sa < 3.0:
        return
    hm = m / 2.0
    curb = MT.curb(inp["style"]["archetype"])
    top = "lawn" if m >= 2.0 and inp["style"]["era"] not in ("industrial", "aerospace") \
        else "concrete"
    rd.sweep(mesh, curb, sa, sb, [(-hm, 0.0), (-hm, 0.15), (-hm + 0.2, 0.15)])
    rd.sweep(mesh, curb, sa, sb, [(hm - 0.2, 0.15), (hm, 0.15), (hm, 0.0)])
    rd.sweep(mesh, top, sa, sb, [(-hm + 0.2, 0.16), (hm - 0.2, 0.16)])
    for s, flip in ((sa, True), (sb, False)):
        a = rd.xy(s, -hm)
        b = rd.xy(s, hm)
        z = rd.z(s)
        if flip:
            a, b = b, a
        mesh.wall(curb, a, b, z, z + 0.16, z, z + 0.16)


# -- decks and embankments -------------------------------------------------------------

def _deck(rd: Road, mesh: Mesh, inp: dict):
    cls = rd.cls
    W2 = rd.W / 2.0
    a = rd.seg.get("attrs", {})
    # viaducts and ramps stand on M7's columns, whose tops are 1.8 m under the road
    D = 1.8 if a.get("elevated") or a.get("role") == "ramp" else DECK_D.get(cls, 1.2)
    B = max(rd.W * 0.55, 2.0)
    prof = [(W2, 0.0), (W2, -0.45), (B / 2.0, -min(0.7, D * 0.6)), (B / 2.0 - 0.25, -D),
            (-(B / 2.0 - 0.25), -D), (-B / 2.0, -min(0.7, D * 0.6)), (-W2, -0.45),
            (-W2, 0.0)]
    rd.sweep(mesh, "concrete.deck", 0.0, rd.L, prof, base=-ROAD_DZ)
    if cls not in PEDESTRIAN:
        sw = rd.side if cls in ("avenue", "street") else 0.0
        base = 0.15 if sw > 0 else 0.0
        rd.sweep(mesh, "concrete.barrier", 0.0, rd.L,
                 [(W2 - 0.45, 0.0), (W2 - 0.35, 1.05), (W2, 1.05), (W2, -0.0)], base=base)
        rd.sweep(mesh, "concrete.barrier", 0.0, rd.L,
                 [(-W2, -0.0), (-W2, 1.05), (-W2 + 0.35, 1.05), (-W2 + 0.45, 0.0)],
                 base=base)
    sid = inp["seg"]["id"]
    if cls not in PEDESTRIAN and rd.s1 - rd.s0 > 10.0:
        s = rd.s0 + 45.0 * rnd(sid, "joint")
        while s < rd.s1 - 1.0:
            if rd.zp(s) > 1.0 and s > rd.s0 + 1.0:
                rd.decal(mesh, "steel.joint", [(s - 0.15, -rd.h), (s + 0.15, -rd.h),
                                               (s + 0.15, rd.h), (s - 0.15, rd.h)],
                         MARK_DZ - 0.001)
            s += 45.0
    s = 7.5
    while s < rd.L - 1.0:
        if rd.zp(s) > 4.0:
            z = rd.z(s) - ROAD_DZ - D - 0.02
            ring = [(s - 0.4, -0.15), (s - 0.4, 0.15), (s + 0.4, 0.15), (s + 0.4, -0.15)]
            mesh.poly_map("light", ring, (), lambda u, v, z=z: (*rd.xy(u, v), z))
        s += 15.0


RAMP_WALK_M = 2.0       # M14's walkway beside each side of a deck's ramp
RAMP_PARAPET_M = 0.25
RAMP_PARAPET_H = 1.1


def _deck_ramp(rd: Road, mesh: Mesh, inp: dict) -> dict:
    """M14's ramp up to a deck (AG10): barriers at the carriageway's edges, a walkway on
    each side at curb height (the model's walkways beside it), a parapet outside it, and
    the solid ramp's walls down to the ground on both sides and across its raised ends.
    Returns the walkways' lines put on the ramp (z over the ground, as the model's)."""
    W2 = rd.W / 2.0
    pave = MT.paving(inp["style"]["archetype"])
    wi, wo = W2 + RAMP_WALK_M, W2 + RAMP_WALK_M + RAMP_PARAPET_M
    top = RAMP_PARAPET_H + 0.15
    rd.sweep(mesh, "concrete.barrier", rd.s0, rd.s1,
             [(W2 - 0.45, 0.0), (W2 - 0.35, 1.05), (W2, 1.05), (W2, -0.0)])
    rd.sweep(mesh, "concrete.barrier", rd.s0, rd.s1,
             [(-W2, -0.0), (-W2, 1.05), (-W2 + 0.35, 1.05), (-W2 + 0.45, 0.0)])
    rd.strip(mesh, pave, rd.s0, rd.s1, W2, wi, 0.15)
    rd.strip(mesh, pave, rd.s0, rd.s1, -wi, -W2, 0.15)
    rd.sweep(mesh, "concrete.barrier", rd.s0, rd.s1, [(wi, 0.15), (wi, top), (wo, top)])
    rd.sweep(mesh, "concrete.barrier", rd.s0, rd.s1, [(-wo, top), (-wi, top), (-wi, 0.15)])
    for side in (1.0, -1.0):
        rows, uvs, exp = [], [], []
        for s, vi in rd.stations(rd.s0, rd.s1):
            x, y = rd.at(s, side * wo, vi)
            _, _, nx, ny, _ = rd.path.frame(s, vi)
            zt, zb = rd.z(s) + top, rd.ground(s) - 0.1
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


def _embankment(rd: Road, mesh: Mesh, s0: float = 0.0, s1: float | None = None):
    """Retained fill under the road from s0 to s1 (all of it by default): its two faces
    from the road's edge down into the ground."""
    W2 = rd.W / 2.0
    for side in (1.0, -1.0):
        rows, uvs, exp = [], [], []
        for s, vi in rd.stations(s0, rd.L if s1 is None else s1):
            x, y = rd.at(s, side * W2, vi)
            _, _, nx, ny, _ = rd.path.frame(s, vi)
            top = rd.z(s) + (0.15 if rd.side > 0 else 0.0)
            bot = rd.ground(s) - 0.1
            col = [(x, y, top), (x, y, bot)] if side > 0 else [(x, y, bot), (x, y, top)]
            rows.append(col)
            uvs.append([(s, top), (s, bot)] if side > 0 else [(s, bot), (s, top)])
            exp.append((side * nx, side * ny, 0.0))
        mesh.grid("concrete", rows, uvs, expect=exp)


def walkway_fix(rd: Road, line, curb: float) -> list:
    """A walkway's line put on its road's deck (z over the ground, as the model's)."""
    out = []
    for p in line:
        s, _ = rd.path.project(p[0], p[1])
        out.append([p[0], p[1], C.m(rd.zp(s) + ROAD_DZ + curb)])
    return out


def heading_of(dx: float, dy: float) -> float:
    return M.degrees(M.atan2(dy, dx))


__all__ = ["gather", "make", "Road", "street_class", "deck_kind", "ROAD_DZ", "unit"]
