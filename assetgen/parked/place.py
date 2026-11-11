"""Where each parked car goes and which hero vehicle it is.

Every M6 parked vehicle AG8 draws (its props contribution's `prop.parked_vehicle.<tile>`
entries: their ids and transforms, already lifted onto the ground) becomes a pack vehicle or is
left out with a reason:

1. **Its curb.** Cars are taken curb by curb (a road segment and its side, from the M6 prop's
   `segment`), in order along the road, so each sees the cars before it as its neighbors.
2. **Its candidates.** The district's weights (`table.weights`) put the models in a weighted
   order by a hash of the car's id (each model's key $u^{1/w}$, highest first: the first is a
   weighted draw, the rest the draws after it).
3. **The first that fits** (`Fit`): the model's plan box (its pack's `dimensions`, mirrors
   included) at the car's spot and heading
   - lies on its own road's carriageway (the M22 pavement map's carriageway and bend faces of
     that segment, which leave out the curbs, sidewalks, medians and every junction) but for
     `INSET_M`;
   - covers no crosswalk (more than `INSET_M` into one);
   - keeps `GAP_M` from every car placed before it;
   - and is not the fourth of one model in a row along the curb (`MAX_RUN`).
   None fits: the car is left out, with the reason its smallest candidate failed on.
4. **Its paint** (`table.paint`), drawn again while the car before it on the curb is the same
   model in the same primary color.

**Hover cars parked** (Kestrel, the Aurel Zenith) are set down: the pack's lowest point (its
emitter pods or skids, 0.27 to 0.37 m under the hover pose's body) on the road, so they sit on
the parking lane as the wheeled cars do; a car on its wheels stands `ROAD_DZ_M` over the
model's height, on the asphalt as AG7 draws it (`streets.pave.ROAD_DZ_MM`).
"""

from __future__ import annotations

import math
from collections import defaultdict

import shapely

from citygen import dmath as M
from citygen import geom as G

from .. import canon as C
from . import table as T

INSET_M = 0.1          # a footprint may reach this far off its carriageway or onto a crosswalk
GAP_M = 0.5            # bumper to bumper (and side to side) between parked cars
MAX_RUN = 3            # at most this many of one model in a row along a curb
ROAD_DZ_M = 0.05       # AG7's carriageway over the pavement map's height
KIND = "parked_vehicle"
LANE_KINDS = ("carriageway", "bend")


def footprint(car: dict, x: float, y: float, yaw: float):
    """A pack's plan box (x forward, y left) at (x, y) turned by yaw (degrees)."""
    a = M.radians(yaw)
    c, s = M.cos(a), M.sin(a)
    (x0, y0), (x1, y1) = car["min"][:2], car["max"][:2]
    return shapely.Polygon([(x + c * u - s * v, y + s * u + c * v)
                            for u, v in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])


class Fit:
    """The surfaces a parked car must keep to (its segment's carriageway faces) and off (the
    crosswalks), from the model's pavement map; without a map (a model before M22) only the
    neighbors count."""

    def __init__(self, model):
        from ..streets import pave as PV
        from ..streets.ctx import Ground
        self.PI = PI = PV.Index(model, Ground(model))
        self.on = PI.on
        lanes: dict = defaultdict(list)
        if PI.on:
            from ..props.gather import _face_poly
            with G.canonical():
                for fid in sorted(PI.F):
                    f = PI.F[fid]
                    if f.kind not in LANE_KINDS:
                        continue
                    g = _face_poly(PI, fid)
                    if g is not None:
                        lanes[f.owner_id].append(g)
        self.lanes = {k: shapely.union_all(v).buffer(INSET_M, join_style="mitre")
                      for k, v in sorted(lanes.items())}
        xs = []
        for c in sorted(model.crosswalks, key=lambda c: c.id):
            if len(c.line) < 2:
                continue
            ln = shapely.LineString([(p[0], p[1]) for p in c.line])
            xs.append(ln.buffer(c.width_m / 2.0, cap_style="flat").buffer(-INSET_M))
        self.xwalks = [g for g in xs if not g.is_empty]
        self.xtree = shapely.STRtree(self.xwalks) if self.xwalks else None

    def lane_ok(self, seg: str | None, fp) -> bool:
        if not self.on:
            return True
        lane = self.lanes.get(seg)
        return lane is not None and lane.covers(fp)

    def xwalk_ok(self, fp) -> bool:
        if self.xtree is None:
            return True
        return not len(self.xtree.query(fp, predicate="intersects"))


class Placed:
    """The footprints placed so far, on a 16 m grid."""
    CELL = 16.0

    def __init__(self):
        self.cells: dict = defaultdict(list)

    def _keys(self, fp):
        x0, y0, x1, y1 = fp.bounds
        for i in range(math.floor((x0 - GAP_M) / self.CELL),
                       math.floor((x1 + GAP_M) / self.CELL) + 1):
            for j in range(math.floor((y0 - GAP_M) / self.CELL),
                           math.floor((y1 + GAP_M) / self.CELL) + 1):
                yield i, j

    def clear(self, fp) -> bool:
        seen = set()
        for k in self._keys(fp):
            for n, g in self.cells.get(k, ()):
                if n in seen:
                    continue
                seen.add(n)
                if g.distance(fp) < GAP_M:
                    return False
        return True

    def add(self, n, fp) -> None:
        for k in self._keys(fp):
            self.cells[k].append((n, fp))


def order(w: dict, pid: str) -> list[str]:
    """The models in a weighted order by the car's id (Efraimidis and Spirakis' keys)."""
    keys = []
    for c in sorted(w):
        uu = max(T.u("ag18.model", pid, c), 1e-12)
        keys.append((-math.log(uu) / w[c], c))
    return [c for _, c in sorted(keys)]


def curb_of(model) -> dict[str, tuple]:
    """Per parked car its curb (segment, side) and its station along the segment."""
    segs = {s.id: s for s in model.road_segments}
    lines = {}
    out = {}
    for p in sorted(model.props, key=lambda p: p.id):
        if p.type.split(".", 1)[1] != KIND:
            continue
        sid = (p.attrs or {}).get("segment")
        s = segs.get(sid)
        if s is None or len(s.centerline) < 2:
            out[p.id] = ("", 0, 0.0)
            continue
        if sid not in lines:
            lines[sid] = shapely.LineString([(q[0], q[1]) for q in s.centerline])
        ln = lines[sid]
        pt = shapely.points(p.position[0], p.position[1])
        st = ln.project(pt)
        a = ln.interpolate(max(0.0, st - 0.5))
        b = ln.interpolate(min(ln.length, st + 0.5))
        cross = (b.x - a.x) * (p.position[1] - a.y) - (b.y - a.y) * (p.position[0] - a.x)
        out[p.id] = (sid, 0 if cross >= 0 else 1, round(st, 3))
    return out


def place(model, cars: dict, ag8: list[dict], spec_weights: dict | None = None) -> dict:
    """Every parked car of AG8's entries placed or left out. `ag8`: [{key, tile, pivot,
    xforms, ids}] (one per tile). Returns {placed: {id: rec}, left_out: {id: reason},
    district: {id: district id}, curbs: {(seg, side): [ids in order]}}."""
    from citygen.presets import ARCHETYPES
    from ..props.gather import _Districts
    ds = _Districts(model)
    fit = Fit(model)
    curb = curb_of(model)
    spot = {}
    for e in ag8:
        px, py, pz = e["pivot"]
        for xf, pid in zip(e["xforms"], e["ids"]):
            spot[pid] = (e["tile"], xf[0] + px, xf[1] + py, xf[2] + pz, xf[3])
    dw: dict = {}

    def weights_of(did):
        if did not in dw:
            d = ds.d.get(did)
            arch = d.archetype if d is not None else None
            pre = ARCHETYPES.get(arch or "")
            par = d.params if d is not None else {}
            wealth = par.get("wealth")
            danger = par.get("danger")
            wealth = float(wealth if wealth is not None else (pre.wealth if pre else 0.5))
            danger = float(danger if danger is not None else (pre.danger if pre else 0.4))
            dw[did] = (arch, T.weights(arch, wealth, danger, cars, spec_weights))
        return dw[did]

    groups: dict = defaultdict(list)
    for pid in sorted(spot):
        seg, side, st = curb.get(pid, ("", 0, 0.0))
        groups[(seg, side)].append((st, pid))
    placed, left, dist = {}, {}, {}
    taken = Placed()
    curbs = {}
    smallest = sorted(cars, key=lambda c: (cars[c]["length"] * cars[c]["width"], c))
    for key in sorted(groups):
        run: list = []                 # (car, primary) of the cars placed along this curb
        ids = []
        for _, pid in sorted(groups[key]):
            tile, x, y, z, yaw = spot[pid]
            did = ds.of(pid, x, y)
            dist[pid] = did
            arch, w = weights_of(did)
            if not w:
                left[pid] = "no model has a weight in its district"
                continue
            got, why = None, {}
            for c in order(w, pid):
                if len(run) >= MAX_RUN and all(r[0] == c for r in run[-MAX_RUN:]):
                    why[c] = "the fourth of one model in a row"
                    continue
                fp = footprint(cars[c], x, y, yaw)
                if not fit.lane_ok(key[0], fp.buffer(-INSET_M, join_style="mitre")):
                    why[c] = "off its parking lane"
                elif not fit.xwalk_ok(fp):
                    why[c] = "on a crosswalk"
                elif not taken.clear(fp):
                    why[c] = "too close to a neighbor"
                else:
                    got = (c, fp)
                    break
            if got is None:
                c0 = next((c for c in smallest if c in why), None)
                left[pid] = (f"no model fits: {why[c0]}" if c0 else "no model fits")
                continue
            c, fp = got
            turn = 0
            while True:
                paint, p1 = T.paint(c, arch, pid, turn)
                if not run or run[-1] != (c, p1) or turn >= 8:
                    break
                turn += 1
            car = cars[c]
            # (on its wheels on AG7's asphalt; a hover car set down on its lowest point)
            zz = z + ROAD_DZ_M - (car["min"][2] if car["kind"] == "hover" else 0.0)
            placed[pid] = {"car": c, "tile": tile, "x": C.m(x), "y": C.m(y), "z": C.m(zz),
                           "yaw": C.deg(yaw), "paint": paint, "primary": p1,
                           "district": did, "footprint": fp}
            taken.add(pid, fp)
            run.append((c, p1))
            ids.append(pid)
        curbs[key] = ids
    return {"placed": placed, "left_out": left, "district": dist, "curbs": curbs, "fit": fit}
