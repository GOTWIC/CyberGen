"""Barriers and props at junctions (issue #95): part of AG14's `asset_clash`, on the packs as
written.

What counts as a barrier: every street piece's `concrete.barrier` (AG7's median barriers,
an at-grade highway's guard walls, a raised road's parapets, an M14 deck ramp's barriers
and parapets, a junction's corner parapets, guard walls and median), a footbridge's railings
and stone parapets (`steel.painted`, `stone.coping` on a bridge piece along its deck's
edges: not its steps or its edge beam), M14's deck rails (`steel.painted`, `glass.panel`
on a deck piece), and an open tunnel approach's walls (a trench). What it may not cross:

- **barrier on road**: a barrier's points standing on another road's carriageway (its
  asphalt, or a pedestrian street's paving): over it in plan more than `INSET_M` in from
  its outline and between `BELOW_M` under and `ABOVE_M` over its surface there (a bridge's
  railings stand on its own road's deck);
- **barrier in junction**: the same on a junction's surface; a junction's own barriers (its
  corner parapets and guard walls, a median across it) on its own surface only where they
  stand in one of its connector lanes (within the lane's half width less `INSET_M`);
- **barrier on crosswalk**: the same on a crosswalk (the model's rectangle less `INSET_M`,
  at the pavement's height there), the road's own median barrier included;
- **barrier through barrier**: two pieces' barriers through each other: over `MEET_M2` of
  plan overlap at heights that overlap (two pieces meeting at a node they share join with
  at most `JOIN_M2`, a corner's worth);
- **prop on road**: a standing prop (AG8's instances, as `asset_grounded` takes them) whose
  low footprint (its vertices under `PROP_LOW_M` over its foot) reaches more than
  `INSET_M` into a vehicle carriageway or a junction (their asphalt) or a crosswalk at its
  height (a parked vehicle on its parking lane, a traffic signal at its crosswalk's end and
  a median barrier prop on its own highway excepted);
- **prop in barrier**: a standing prop's low footprint through a barrier.

Every computation is plain numpy and shapely on the triangles as read (as `index.py`).
"""

from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
import shapely

from .. import canon as C
from .index import Surfaces, TriIndex

INSET_M = 0.1           # how far into a surface a barrier or prop must reach to cross it
BELOW_M = 0.3           # a barrier point under a surface by this still stands on it
ABOVE_M = 2.0           # ... and over it by this (a parapet over a road under is not on it)
MEET_M2 = 0.05          # plan overlap of two barriers that counts as through each other
JOIN_M2 = 0.5           # ... and of two barriers that join at a node they share
SAMPLE_M = 0.5          # barrier triangles sampled along their edges this often
PROP_LOW_M = 2.0        # a prop's footprint: its vertices this far over its foot
NEAR_JUNCTION_M = 30.0  # what is reported as at a junction
LIST_MAX = 40

BARRIER_SLOTS = {"concrete.barrier"}
RAIL_SLOTS = {"steel.painted", "stone.coping", "glass.panel"}
CARRIAGE_SKIP = ("asphalt.patch",)
# props that stand on a carriageway (or a crosswalk's end) by design
ON_ROAD_OK = {"parked_vehicle"}
ON_XWALK_OK = {"traffic_signal"}
KEYS = ("barrier_on_road", "barrier_in_junction", "barrier_on_crosswalk",
        "barrier_through_barrier", "prop_on_road", "prop_in_barrier")


def barrier_mask(kind: str, mats: list[str], T: np.ndarray | None = None,
                 rail=None) -> np.ndarray:
    """Which triangles of a street piece are barrier (the module docstring); on a bridge
    (`rail`: its road's centerline and half width) the railings and stone parapets are the
    triangles of their slots along the deck's edges."""
    m = np.array([x in BARRIER_SLOTS for x in mats], dtype=bool)
    if kind.startswith("street.deck"):
        m |= np.array([x in RAIL_SLOTS for x in mats], dtype=bool)
    if kind == "street.bridge" and rail is not None and T is not None and len(T):
        r = np.array([x in RAIL_SLOTS for x in mats], dtype=bool)
        if r.any():
            ln, W2 = rail
            c = T.mean(axis=1)
            d = shapely.distance(ln, shapely.points(c[:, 0], c[:, 1]))
            stone = np.array([x == "stone.coping" for x in mats], dtype=bool)
            m |= r & (d >= W2 - 0.35) & ((d <= W2 - 0.005) | (stone & (d <= W2 + 0.01)))
    if kind == "street.trench":
        # an open approach's walls (and their parapets over the ground)
        m = np.array([x == "concrete" for x in mats], dtype=bool)
    return m


def surface_mask(mats: list[str]) -> np.ndarray:
    """A road or junction piece's pavement: asphalt (not its patches) and paving."""
    return np.array([(x.startswith("asphalt") and x not in CARRIAGE_SKIP) or
                     x.startswith("paving") for x in mats], dtype=bool)


def _samples(T: np.ndarray) -> np.ndarray:
    """Points on triangles: their vertices, middles and points along their edges every
    `SAMPLE_M`, (n, 3)."""
    if not len(T):
        return np.zeros((0, 3))
    pts = [T.reshape(-1, 3), T.mean(axis=1)]
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = T[:, i], T[:, j]
        L = np.linalg.norm(b - a, axis=1)
        n = np.maximum(1, np.ceil(L / SAMPLE_M).astype(np.int64))
        idx = np.repeat(np.arange(len(T)), n)
        f = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
        pts.append(a[idx] + (b[idx] - a[idx]) * f[:, None])
    return np.concatenate(pts)


def _outline(T: np.ndarray):
    """The plan outline of triangles (their union), shapely."""
    polys = shapely.polygons(T[:, :, :2])
    polys = polys[shapely.area(polys) > 1e-6]
    if not len(polys):
        return None
    return shapely.union_all(polys, grid_size=0.001)


class Targets:
    """Carriageways and junction surfaces (up-facing pavement per piece, with owners) and
    the model's crosswalks."""

    def __init__(self, pk, model):
        self.pk = pk
        tris, own, asph = [], [], []
        self.kind_of: dict[int, str] = {}
        for pid in pk.street_ids():
            k = pk.street_kind(pid)
            if k not in ("street.road", "street.junction"):
                continue
            T, mats = pk.street_tris(pid)
            if not len(T):
                continue
            keep = surface_mask(mats)
            if not keep.any():
                continue
            o = pk.owner(pid)
            self.kind_of[o] = k
            tris.append(T[keep])
            own.append(np.full(int(keep.sum()), o))
            asph.append(np.array([m.startswith("asphalt") for m, k_ in zip(mats, keep) if k_],
                                 dtype=bool))
        T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
        O = np.concatenate(own) if own else np.zeros(0, dtype=np.int64)
        A = np.concatenate(asph) if asph else np.zeros(0, dtype=bool)
        # (a vehicle carriageway: asphalt; a pedestrian street's paving is walked on)
        self.S = Surfaces(T, O, min_nz=0.5)
        self.V = Surfaces(T[A], O[A], min_nz=0.5)
        self._outlines: dict = {}
        xs, self.xw_ids = [], []
        for c in model.crosswalks:
            a, b = c.line[0], c.line[-1]
            ln = shapely.LineString([(a[0], a[1]), (b[0], b[1])])
            if ln.length < 0.5:
                continue
            xs.append(ln.buffer(c.width_m / 2.0, cap_style="flat"))
            self.xw_ids.append(c.id)
        self.xw_in = [x.buffer(-INSET_M) for x in xs]
        self.xw_tree = shapely.STRtree(self.xw_in) if xs else None
        self.jpolys = [shapely.Polygon([(p[0], p[1]) for p in j.polygon.exterior])
                       for j in model.junctions]
        self.jtree = shapely.STRtree(self.jpolys) if self.jpolys else None

    def outline(self, o: int, vehicle: bool = False):
        key = (o, vehicle)
        if key not in self._outlines:
            S = self.V if vehicle else self.S
            sel = S.owner == o
            self._outlines[key] = _outline(S.t[sel]) if sel.any() else None
        return self._outlines[key]

    def near_junction(self, xy: np.ndarray) -> bool:
        if self.jtree is None or not len(xy):
            return False
        i, _ = self.jtree.query(shapely.points(xy[:, 0], xy[:, 1]), predicate="dwithin",
                                distance=NEAR_JUNCTION_M)
        return bool(len(i))

    def on_pavement(self, P: np.ndarray, exclude: set, lo: float, hi: float,
                    vehicle: bool = False) -> list[tuple[int, int, float]]:
        """(point index, owner, depth) of points standing on a piece's pavement (`vehicle`:
        its asphalt only): inside one of its triangles in plan with the point between `lo`
        under and `hi` over it, and `INSET_M` in from the piece's outline; owners in
        `exclude` left out."""
        S = self.V if vehicle else self.S
        pid, tid = S.candidates(P[:, :2])
        if not len(pid):
            return []
        ins, z = S.heights(P[:, :2], pid, tid, eps=1e-6)
        dz = P[pid, 2] - z
        ok = ins & (dz >= -lo) & (dz <= hi)
        if exclude:
            ok &= ~np.isin(S.owner[tid], np.array(sorted(exclude), dtype=np.int64))
        pairs = sorted({(int(a), int(S.owner[b])) for a, b in
                        zip(pid[ok].tolist(), tid[ok].tolist())})
        by_o: dict[int, list[int]] = defaultdict(list)
        for a, o in pairs:
            by_o[o].append(a)
        out = []
        for o in sorted(by_o):
            g = self.outline(o, vehicle)
            if g is None:
                continue
            idx = np.array(by_o[o], dtype=np.int64)
            inside = shapely.contains_xy(g, P[idx, 0], P[idx, 1])
            d = shapely.distance(g.boundary, shapely.points(P[idx, 0], P[idx, 1]))
            sel = inside & (d > INSET_M)
            out += [(a, o, dd) for a, dd in zip(idx[sel].tolist(), d[sel].tolist())]
        return out

    def on_crosswalk(self, P: np.ndarray, lo: float, hi: float) -> list[tuple[int, int]]:
        """(point index, crosswalk index) of points on a crosswalk at the pavement's
        height there."""
        if self.xw_tree is None or not len(P):
            return []
        pi, ci = self.xw_tree.query(shapely.points(P[:, 0], P[:, 1]), predicate="within")
        if not len(pi):
            return []
        pid, tid = self.S.candidates(P[pi, :2])
        ins, z = self.S.heights(P[pi, :2], pid, tid, eps=1e-6)
        dz = P[pi[pid], 2] - z
        ok = ins & (dz >= -lo) & (dz <= hi)
        return sorted({(int(pi[a]), int(ci[a])) for a in pid[ok].tolist()})


class Barriers:
    """Every barrier's triangles per piece."""

    def __init__(self, pk, model):
        self.T: list[np.ndarray] = []
        self.pids: list[str] = []
        self.what: dict[str, str] = {}
        self.segs = {s.id: s for s in model.road_segments}
        bridge_seg = {b.id: b.segment_ids[0] for b in model.bridges if b.segment_ids}
        self.own: dict[str, set] = {b.id: set(b.segment_ids) for b in model.bridges}
        for pid in pk.street_ids():
            k = pk.street_kind(pid)
            T, mats = pk.street_tris(pid)
            if not len(T):
                continue
            rail = None
            sid = bridge_seg.get(pid)
            if k == "street.bridge" and sid in self.segs:
                rail = (shapely.LineString([(p[0], p[1]) for p in self.segs[sid].centerline]),
                        self.segs[sid].width_m / 2.0)
            m = barrier_mask(k, mats, T, rail)
            if not m.any():
                continue
            self.pids.append(pid)
            self.T.append(T[m])
            self.what[pid] = k

    def classify(self, pid: str, P: np.ndarray) -> np.ndarray:
        """What each point's barrier is: median, guard, parapet, ramp barrier, ramp parapet
        (a road piece's, by its offset from the centerline), else its piece's kind."""
        k = self.what[pid]
        name = {"street.junction": "junction_barrier", "street.bridge": "footbridge_rail",
                "street.trench": "trench_wall"}.get(k, k.replace("street.", ""))
        if k.startswith("street.deck"):
            name = "deck_rail"
        out = np.full(len(P), name, dtype=object)
        s = self.segs.get(pid)
        if k != "street.road" or s is None:
            return out
        from ..streets.roads import deck_kind
        dk = deck_kind(s.model_dump(mode="json", exclude_none=True))
        d = shapely.distance(shapely.LineString([(p[0], p[1]) for p in s.centerline]),
                             shapely.points(P[:, 0], P[:, 1]))
        out[:] = {"deck": "parapet", "ramp": "ramp_barrier"}.get(dk, "guard")
        out[d < 0.6] = "median"
        if dk == "ramp":
            out[d > s.width_m / 2.0 + 0.2] = "ramp_parapet"
        return out


def _ends(model) -> dict[str, set]:
    """The nodes at the ends of each road, and of each bridge's roads."""
    out = {s.id: {s.start, s.end} for s in model.road_segments}
    for b in model.bridges:
        nodes: set = set()
        for i in b.segment_ids:
            nodes |= out.get(i, set())
        out[b.id] = nodes
    return out


def barrier_clash(pk, model) -> dict:
    """The clashes of the module docstring: {"counts", "by_kind" (by what and cause),
    "near_junction" (of the counts, those within `NEAR_JUNCTION_M` of a junction),
    "worst"}."""
    tg = Targets(pk, model)
    br = Barriers(pk, model)
    node_of_j = {j.id: j.node_id for j in model.junctions}
    seg_nodes = _ends(model)
    counts = {k: 0 for k in KEYS}
    rows: dict[str, list] = {k: [] for k in KEYS}
    by_kind: dict[str, int] = defaultdict(int)
    near_j: dict[str, int] = defaultdict(int)

    # (a junction's connector lanes, which its own barriers keep out of)
    lanes: dict[str, list] = defaultdict(list)
    for ln in model.lanes:
        if ln.kind == "connector" and ln.node_id and len(ln.centerline) >= 2:
            lanes[ln.node_id].append((shapely.LineString([(p[0], p[1]) for p in
                                                          ln.centerline]), ln.width_m / 2.0))

    def shared(pa: str, pb: str) -> bool:
        na = seg_nodes.get(pa, set()) | ({node_of_j[pa]} if pa in node_of_j else set())
        nb = seg_nodes.get(pb, set()) | ({node_of_j[pb]} if pb in node_of_j else set())
        return bool(na & nb)
    foot_polys, foot_pid, tops, samples = [], [], {}, {}
    for pid, T in zip(br.pids, br.T):
        P = _samples(T)
        samples[pid] = P
        what = br.classify(pid, P)
        own = {pk.oid[x] for x in br.own.get(pid, ()) if x in pk.oid} | {pk.owner(pid)}
        per: dict = {}
        for a, oo, dd in tg.on_pavement(P, own, BELOW_M, ABOVE_M):
            r = per.setdefault(oo, [0, 0.0, a, set()])
            r[0] += 1
            if dd > r[1]:
                r[1], r[2] = dd, a
            r[3].add(what[a])
        if pid in node_of_j and lanes.get(node_of_j[pid]):
            mine = [a for a, oo, _ in tg.on_pavement(P, set(), BELOW_M, ABOVE_M) if oo in own]
            if mine:
                idx = np.array(sorted(set(mine)), dtype=np.int64)
                pts = shapely.points(P[idx, 0], P[idx, 1])
                inl = np.zeros(len(idx), dtype=bool)
                for ln, hw in lanes[node_of_j[pid]]:
                    inl |= shapely.distance(ln, pts) < hw - INSET_M
                if inl.any():
                    a = int(idx[np.nonzero(inl)[0][0]])
                    per[pk.owner(pid)] = [int(inl.sum()), 0.0, a, {what[a]}]
        for oo, (n, dd, a, ws) in sorted(per.items()):
            tpid = pk.names[oo]
            junction = tg.kind_of.get(oo) == "street.junction"
            key = "barrier_in_junction" if junction else "barrier_on_road"
            if junction:
                cause = "its own lanes" if tpid == pid else "its own end" \
                    if node_of_j.get(tpid) in seg_nodes.get(pid, ()) else "another junction"
            else:
                cause = "a road at a node it shares" if shared(pid, tpid) else "another road"
            counts[key] += 1
            for w in sorted(ws):
                by_kind[f"{key}: {w}, {cause}"] += 1
            if tg.near_junction(P[a:a + 1, :2]):
                near_j[key] += 1
            rows[key].append({"barrier": pid, "on": tpid, "what": sorted(ws), "cause": cause,
                              "points": n, "depth_m": C.m(dd),
                              "at": [C.m2(v) for v in P[a]]})
        per_x: dict = {}
        for a, ci in tg.on_crosswalk(P, BELOW_M, ABOVE_M):
            r = per_x.setdefault(ci, [0, a, set()])
            r[0] += 1
            r[2].add(what[a])
        for ci, (n, a, ws) in sorted(per_x.items()):
            counts["barrier_on_crosswalk"] += 1
            for w in sorted(ws):
                by_kind[f"barrier_on_crosswalk: {w}"] += 1
            near_j["barrier_on_crosswalk"] += 1
            rows["barrier_on_crosswalk"].append({"barrier": pid, "crosswalk": tg.xw_ids[ci],
                                                 "what": sorted(ws), "points": n,
                                                 "at": [C.m2(v) for v in P[a]]})
        fp = _outline(T)
        if fp is not None:
            foot_polys.append(fp)
            foot_pid.append(pid)
            tops[pid] = Surfaces(T, None, min_nz=0.05)
    # -- barriers through each other
    if foot_polys:
        tree = shapely.STRtree(foot_polys)
        a_, b_ = tree.query(foot_polys, predicate="intersects")
        pairs = sorted({(min(i, j), max(i, j)) for i, j in zip(a_.tolist(), b_.tolist())
                        if i != j})
        for i, j in pairs:
            pa, pb = foot_pid[i], foot_pid[j]
            x = shapely.intersection(foot_polys[i], foot_polys[j], grid_size=0.001)
            if x.is_empty or x.area < MEET_M2:
                continue
            sh = shared(pa, pb)
            if sh and x.area <= JOIN_M2:
                continue                # (where they join)
            hit, at = 0, None
            for p_, q_ in ((pa, pb), (pb, pa)):
                P = samples[p_]
                inx = shapely.contains_xy(x, P[:, 0], P[:, 1])
                if not inx.any():
                    continue
                Q = P[inx]
                zt = tops[q_].under(Q, 0.05)
                ok = ~np.isnan(zt) & (Q[:, 2] >= zt - 1.6)
                if ok.any():
                    hit += int(ok.sum())
                    at = at if at is not None else Q[np.nonzero(ok)[0][0]]
            if not hit:
                continue
            counts["barrier_through_barrier"] += 1
            cause = "pieces at a node they share" if sh else "other pieces"
            by_kind[f"barrier_through_barrier: {br.what[pa].replace('street.', '')} / "
                    f"{br.what[pb].replace('street.', '')}, {cause}"] += 1
            if tg.near_junction(at[None, :2]):
                near_j["barrier_through_barrier"] += 1
            rows["barrier_through_barrier"].append(
                {"pieces": [pa, pb], "cause": cause, "area_m2": C.m2(x.area), "points": hit,
                 "at": [C.m2(v) for v in at]})
    _props(pk, model, tg, foot_polys, foot_pid, tops, counts, rows, by_kind, near_j)
    for k in rows:
        rows[k] = sorted(rows[k], key=lambda r: json.dumps(r, sort_keys=True))[:LIST_MAX]
    return {"counts": counts, "by_kind": dict(sorted(by_kind.items())),
            "near_junction": dict(sorted(near_j.items())), "worst": rows}


def _props(pk, model, tg: Targets, foot_polys, foot_pid, tops, counts, rows, by_kind,
           near_j):
    """Standing props on a carriageway, a junction or a crosswalk, or through a barrier."""
    from .build import NOT_STANDING, _xform
    f = pk.a / "unreal_contribution.props.json"
    if not f.is_file():
        return
    c = json.loads(f.read_text(encoding="utf-8"))
    attrs = {p.id: (p.attrs or {}) for p in model.props}
    btree = shapely.STRtree(foot_polys) if foot_polys else None
    for e in c.get("entries", []):
        kind = e["kind"].split(".", 1)[1] if "." in e["kind"] else e["kind"]
        if not e["kind"].startswith("prop.") or kind in NOT_STANDING:
            continue
        px, py, pz = e["pivot"]
        for p in e.get("parts", []):
            mesh = pk.part_mesh(p["glb"], p["node"])
            if mesh is None:
                continue
            pos = mesh[0]
            low = pos[pos[:, 2] <= pos[:, 2].min() + PROP_LOW_M]
            hull = shapely.convex_hull(shapely.multipoints(low[:, :2]))
            if hull.area < 1e-4:
                continue
            ring = np.array(hull.exterior.coords)[:-1]
            for xf, iid in zip(p["xforms"], p["ids"]):
                x, y, z, yaw = xf[:4]
                s = xf[4:7] if len(xf) >= 7 else (1.0, 1.0, 1.0)
                R = _xform(np.c_[ring, np.zeros(len(ring))], px + x, py + y, pz + z, yaw, s)
                poly = shapely.Polygon(R[:, :2])
                if not poly.is_valid or poly.area < 1e-4:
                    continue
                inner = poly.buffer(-0.02)
                z0 = pz + z + pos[:, 2].min() * s[2]
                where = np.array([[px + x, py + y]])
                if kind not in ON_ROAD_OK:
                    pts = _poly_points(inner)
                    P = np.c_[pts, np.full(len(pts), z0)]
                    ex: set = set()
                    if kind == "barrier":
                        sid = attrs.get(iid, {}).get("segment")
                        if sid in pk.oid:
                            ex = {pk.oid[sid]}
                    hits = tg.on_pavement(P, ex, 0.5, 0.5, vehicle=True)
                    xw = [] if kind in ON_XWALK_OK else tg.on_crosswalk(P, 0.5, 0.5)
                    if hits or xw:
                        counts["prop_on_road"] += 1
                        on = sorted({pk.names[o] for _, o, _ in hits}) or \
                            [tg.xw_ids[ci] for _, ci in xw][:1]
                        by_kind[f"prop_on_road: {kind}"] += 1
                        if tg.near_junction(where):
                            near_j["prop_on_road"] += 1
                        rows["prop_on_road"].append({"prop": iid, "kind": kind, "on": on[:3],
                                                     "at": [C.m2(px + x), C.m2(py + y),
                                                            C.m2(z0)]})
                if btree is None:
                    continue
                for j in btree.query(inner, predicate="intersects").tolist():
                    x_ = shapely.intersection(foot_polys[j], inner)
                    if x_.is_empty or x_.area < 0.005:
                        continue
                    pts = _poly_points(x_)
                    zt = tops[foot_pid[j]].under(np.c_[pts, np.full(len(pts), z0)], 2.0)
                    if np.all(np.isnan(zt)) or np.nanmax(zt) < z0 - 0.05:
                        continue
                    counts["prop_in_barrier"] += 1
                    by_kind[f"prop_in_barrier: {kind} / {foot_pid[j].split('.')[0]}"] += 1
                    if tg.near_junction(where):
                        near_j["prop_in_barrier"] += 1
                    rows["prop_in_barrier"].append(
                        {"prop": iid, "kind": kind, "barrier": foot_pid[j],
                         "at": [C.m2(px + x), C.m2(py + y), C.m2(z0)]})
                    break


def _poly_points(g, step: float = 0.25) -> np.ndarray:
    """Points over a plan polygon: its vertices and a grid inside it."""
    if g.is_empty:
        return np.zeros((0, 2))
    pts = [np.array(p.exterior.coords)[:, :2] for p in shapely.get_parts(g)
           if p.geom_type == "Polygon"]
    lo = np.array(g.bounds[:2])
    hi = np.array(g.bounds[2:])
    nx = max(1, int(np.ceil((hi[0] - lo[0]) / step)))
    ny = max(1, int(np.ceil((hi[1] - lo[1]) / step)))
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], nx + 1), np.linspace(lo[1], hi[1], ny + 1))
    G = np.c_[gx.ravel(), gy.ravel()]
    pts.append(G[shapely.contains_xy(g, G[:, 0], G[:, 1])])
    return np.concatenate(pts) if pts else np.zeros((0, 2))


__all__ = ["barrier_clash", "barrier_mask", "Targets", "Barriers", "TriIndex", "KEYS"]
