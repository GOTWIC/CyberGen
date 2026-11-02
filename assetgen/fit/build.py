"""AG14's fit checks, on the packs as written (scope 14.15): the last stage of `assetgen
build` (`--no-fit` skips it), or alone, `assetgen fit BUILD`.

```
BUILD/assets/fit_report.json, .txt     the two checks, their counts and the worst cases
```

- **`asset_grounded`**: everything that should stand on something rests on a surface under
  it within `GAP_M` (2 cm): props and plants that stand (not those mounted on a wall, hung
  or afloat: `NOT_STANDING`), every building's roof equipment and dunnage (AG4's instanced
  roof parts), and the street pieces that stand on their feet (road, transit and deck
  columns, pylons, frame legs). A thing's feet are its mesh's lowest vertices (within 1 cm
  of its lowest point); five points of their plan box (its middle and corners pulled 10% in)
  each look for the highest surface at most `REACH_M` (0.6 m) over them (a foot set into
  gravel, a green roof or a sidewalk rests; a dunnage frame may stand through its form its
  whole height, a column's footing `FOOTING_M` into the ground or the bed); it rests when
  three of the five are within `GAP_M` over one. Surfaces are the faces facing up of every
  street, ground, water bed, building shell and front and skybridge pack, the dunnage
  frames' tops, and the blockout's land (0 on a flat city, M13's ground on a terrain city;
  none over the water, where a footing takes M16's bed), never the thing itself. With it,
  the junction seams (`seams`): every vertex of a road's carriageway on the outline of a
  junction at one of its ends, near where its centerline first leaves it, within `GAP_M` of
  the junction piece's surface there.
- **`asset_clash`**:
  - *road into building*: a vertex of a road or junction piece's carriageway, deck or
    embankment inside a building mass (10 cm in from its walls, floor and roof);
  - *building over road*: a vertex of a building's shell, front or instanced parts more
    than `RELIEF_M` (0.3 m: sills, frames, reveals) outside its own masses, over a
    carriageway (a road or junction piece's asphalt) and under `HEADROOM_M` (4.5 m) over
    it;
  - *bridge drawn twice*: the deck tops (carriageway, paving, deck) of two bridge or raised
    road pieces within 0.3 m of each other over more than `OVERLAP_M2` (two roads leaving
    one node, a ramp's gore, overlap by design);
  - *transit through building*: a vertex of a line's guideway, sky tube, beam or column
    inside a building mass, except in the band of a portal the building declares for that
    line (M5);
  - *transit through platform*: a vertex of a line's guideway or sky tube inside a station
    platform as drawn (less the tracks beside it, `streets.transit.platform_rings`).

Reading back every pack takes memory: the stage works tile by tile (a tile and its eight
neighbors). Nothing here writes an asset; the report is written only when its bytes change.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely

from .. import canon as C
from .. import manifest as MF
from . import glb as GL
from .index import Surfaces

TILE_M = 256.0
GAP_M = 0.02
REPORTED = ("prop.", "plant.")      # placed at the model's heights: reported, not failed
STEP_FAIL_M = 0.15                  # a junction step that fails (smaller ones reported)
SHELL_REPORT_M = 0.5                # a shell this close to its footprint over a lane: M3's
REACH_M = 0.6
FOOTING_M = 3.0         # how far a column's footing may be set into what it stands on
HEADROOM_M = 4.5
RELIEF_M = 0.3
INSET_M = 0.1
OVERLAP_M2 = 5.0
DECK_DZ_M = 0.3
FOOT_TOL_M = 0.01
LIST_MAX = 40

# props that do not stand on a surface: mounted on a wall, hung, afloat, or drawn whole
# elsewhere (AG8's exact props, signs)
NOT_STANDING = {"awning", "wall_light", "ac_unit", "overhead_cable", "cable", "boat", "sign",
                "scaffolding", "bracket", "neon", "gate", "facade_greenery", "shop_sign",
                "blade_sign", "billboard", "holo_ad", "neon_band", "string_lights"}
STANDING_STREET = ("street.column", "street.transit.column", "street.transit.pylon",
                   "street.deck.column")
ROADLIKE = ("street.road", "street.junction")
TRANSIT = ("street.transit.deck", "street.transit.tube", "street.transit.beam",
           "street.transit.column", "street.transit.pylon")
TRACKS = ("street.transit.deck", "street.transit.tube")
WATER_SURFACE = ("water", "sea")        # AG12's surface slots (not a floor)


def tile_of(x: float, y: float) -> str:
    ix, iy = int(np.floor(x / TILE_M)), int(np.floor(y / TILE_M))
    return f"t{ix:+03d}{iy:+03d}"


def _tile_xy(t: str) -> tuple[int, int]:
    return int(t[1:4]), int(t[4:7])


def _ring(ix: int, iy: int) -> list[str]:
    return [f"t{ix + dx:+03d}{iy + dy:+03d}" for dy in (-1, 0, 1) for dx in (-1, 0, 1)]


# ---------------------------------------------------------------------------
# The city's packs, read once
# ---------------------------------------------------------------------------

class Packs:
    """Up-facing triangles of every pack per tile (owner ids into `names`), the street
    pieces' meshes on demand, and the instanced parts' local meshes."""

    def __init__(self, assets: Path, model):
        self.a = assets
        self.m = model
        self.names: list[str] = []
        self.oid: dict[str, int] = {}
        self.up: dict[str, list] = defaultdict(list)       # tile -> [(tris, owner)]
        self.street: dict[str, dict] = {}                  # piece id -> {kind, tile}
        sm = assets / "streets" / "manifest.json"
        if sm.is_file():
            man = json.loads(sm.read_text(encoding="utf-8"))
            for pid, r in man.get("pieces", {}).items():
                if r.get("triangles", 0) > 0:
                    self.street[pid] = {"kind": r["kind"], "tile": r.get("tile")}
        self._street_nodes: dict[str, dict] = {}
        self._parts: dict[str, dict] = {}

    def owner(self, name: str) -> int:
        i = self.oid.get(name)
        if i is None:
            i = self.oid[name] = len(self.names)
            self.names.append(name)
        return i

    def _add_up(self, tris: np.ndarray, owner: int):
        if not len(tris):
            return
        e1 = tris[:, 1] - tris[:, 0]
        e2 = tris[:, 2] - tris[:, 0]
        n = np.cross(e1, e2)
        L = np.linalg.norm(n, axis=1)
        up = (L > 1e-9) & (n[:, 2] > 0.05 * np.maximum(L, 1e-12))
        tris = tris[up]
        if not len(tris):
            return
        c = tris.mean(axis=1)
        keys = [tile_of(x, y) for x, y in c[:, :2]]
        by = defaultdict(list)
        for k, i in zip(keys, range(len(tris))):
            by[k].append(i)
        for k, ids in by.items():
            self.up[k].append((tris[ids].astype(np.float32), np.full(len(ids), owner)))

    def load(self, progress=None):
        """Every pack's up-facing triangles, filed by the tile of their middle."""
        a = self.a
        # street pieces (their nodes, kept for the clash and the columns' feet)
        for f in sorted((a / "streets").glob("t*.glb")) if (a / "streets").is_dir() else []:
            for nd in GL.read(f):
                if nd.extras.get("lod", 0):
                    continue
                pid = nd.name.split(".glass.lod")[0]
                T = nd.triangles()
                kind = (self.street.get(pid) or {}).get("kind", nd.extras.get("kind", ""))
                self._street_nodes.setdefault(pid, {"kind": kind, "tris": []})["tris"].append(
                    (T, [m for m, _, tri in nd.prims for _ in range(len(tri))]))
                if ".glass.lod" not in nd.name:
                    self._add_up(T, self.owner(pid))
            if progress:
                progress()
        for sub in ("ground/tiles", "connections"):
            d = a / sub
            for f in sorted(d.glob("t*.glb")) if d.is_dir() else []:
                for nd in GL.read(f):
                    self._add_up(nd.triangles(), self.owner(f"{sub}:{nd.root or nd.name}"))
        d = a / "water"
        for f in sorted(d.glob("t*.glb")) if d.is_dir() else []:
            for nd in GL.read(f):
                T = nd.triangles(lambda mname: not any(w == mname.split(".")[0] or
                                                       mname.startswith(w + "_surface")
                                                       for w in WATER_SURFACE))
                self._add_up(T, self.owner(f"water:{nd.root or nd.name}"))
        # building shells and fronts
        d = a / "tiles"
        for f in sorted(d.glob("t*.glb")) if d.is_dir() else []:
            for nd in GL.read(f):
                self._add_up(nd.triangles(), self.owner(nd.root))
            if progress:
                progress()

    def street_tris(self, pid: str):
        """(triangles (m, 3, 3), material per triangle) of a street piece (its main mesh)."""
        r = self._street_nodes.get(pid)
        if r is None:
            return np.zeros((0, 3, 3)), []
        T = [t for t, _ in r["tris"]]
        mats = [m for _, ms in r["tris"] for m in ms]
        return (np.concatenate(T) if T else np.zeros((0, 3, 3))), mats

    def street_kind(self, pid: str) -> str:
        return (self._street_nodes.get(pid) or {}).get("kind", "")

    def street_ids(self) -> list[str]:
        return sorted(self._street_nodes)

    def part_mesh(self, glb: str, node: str):
        """(positions (n, 3), triangles (m, 3)) of an instanced part or variant in its own
        frame, citygen axes, all primitives together."""
        f = self.a / glb
        if glb not in self._parts:
            self._parts[glb] = GL.local_mesh(f) if f.is_file() else {}
        prims = self._parts[glb].get(node) or []
        if not prims:
            return None
        pos, tris, off = [], [], 0
        for _, p, t in prims:
            pos.append(p)
            tris.append(t + off)
            off += len(p)
        return np.concatenate(pos), np.concatenate(tris)

    def surfaces(self, t: str, extra=None) -> Surfaces:
        ix, iy = _tile_xy(t)
        parts = [x for k in _ring(ix, iy) for x in self.up.get(k, ())]
        if extra:
            parts += extra
        if not parts:
            return Surfaces(np.zeros((0, 3, 3)))
        return Surfaces(np.concatenate([p[0] for p in parts]).astype(np.float64),
                        np.concatenate([p[1] for p in parts]), min_nz=0.0)


# ---------------------------------------------------------------------------
# Feet
# ---------------------------------------------------------------------------

def feet(pos: np.ndarray) -> np.ndarray | None:
    """Five plan points of a mesh's lowest vertices (its middle and the corners of their
    box pulled 10% in) at its lowest height, in its frame: (5, 3)."""
    if pos is None or not len(pos):
        return None
    z0 = pos[:, 2].min()
    f = pos[pos[:, 2] <= z0 + FOOT_TOL_M]
    lo, hi = f[:, :2].min(axis=0), f[:, :2].max(axis=0)
    c = (lo + hi) / 2.0
    h = (hi - lo) / 2.0 * 0.9
    pts = [c, c + [-h[0], -h[1]], c + [h[0], -h[1]], c + [h[0], h[1]], c + [-h[0], h[1]]]
    return np.array([[p[0], p[1], z0] for p in pts])


def _xform(P: np.ndarray, x: float, y: float, z: float, yaw: float, s=(1.0, 1.0, 1.0)):
    a = np.radians(yaw)
    c, s_ = np.cos(a), np.sin(a)
    Q = P * np.array(s, dtype=np.float64)
    return np.c_[x + c * Q[:, 0] - s_ * Q[:, 1], y + s_ * Q[:, 0] + c * Q[:, 1], z + Q[:, 2]]


class Floor:
    """The blockout's land under a point: 0 on a flat city (M13's ground on a terrain city),
    none over the water."""

    def __init__(self, m):
        from citygen import geom as G
        t = getattr(m, "terrain", None)
        self.flat = t is None
        if not self.flat:
            rows = t.ground or t.natural
            self.x0, self.y0, self.cell = float(t.x0), float(t.y0), float(t.cell_m)
            self.arr = np.array(rows, dtype=np.float64)
        wet = [G.from_model_poly(w.polygon) for w in m.waterways]
        wet += [G.from_model_poly(r.polygon) for r in m.rivers]
        wet += [G.from_model_poly(c.polygon) for c in m.channels]
        wet += [G.from_model_poly(p) for sea in m.seas for p in sea.polygons]
        with G.canonical():
            self.wet = G.union(wet) if wet else None
        if self.wet is not None and self.wet.is_empty:
            self.wet = None
        if self.wet is not None:
            shapely.prepare(self.wet)
        self.beds = self.levels = None
        if getattr(m, "banks", None):
            from citygen import water as WA
            self.beds, self.levels = WA.Beds(m), WA.Levels(m)

    def bed(self, xy: np.ndarray) -> np.ndarray:
        """M16's bed under points over the water (absolute), nan elsewhere."""
        out = np.full(len(xy), np.nan)
        if self.beds is None or self.wet is None or not len(xy):
            return out
        on = shapely.contains_xy(self.wet, xy[:, 0], xy[:, 1])
        for i in np.nonzero(on)[0].tolist():
            x, y = float(xy[i, 0]), float(xy[i, 1])
            wid = self.beds.body_at(x, y)
            if wid is not None:
                out[i] = self.levels.at(wid, x, y) - self.beds.depth(wid, x, y)
        return out

    def at(self, xy: np.ndarray) -> np.ndarray:
        if self.flat:
            z = np.zeros(len(xy))
        else:
            ny, nx = self.arr.shape
            fx = np.clip((xy[:, 0] - self.x0) / self.cell, 0.0, nx - 1.000001)
            fy = np.clip((xy[:, 1] - self.y0) / self.cell, 0.0, ny - 1.000001)
            i, j = fx.astype(np.int64), fy.astype(np.int64)
            tx, ty = fx - i, fy - j
            a = self.arr
            h0 = a[j, i] * (1 - tx) + a[j, i + 1] * tx
            h1 = a[j + 1, i] * (1 - tx) + a[j + 1, i + 1] * tx
            z = h0 * (1 - ty) + h1 * ty
        if self.wet is not None and len(xy):
            z = np.where(shapely.contains_xy(self.wet, xy[:, 0], xy[:, 1]), np.nan, z)
        return z


# ---------------------------------------------------------------------------
# asset_grounded
# ---------------------------------------------------------------------------

def _things(pk: Packs, model) -> list[dict]:
    """Everything that should stand: {id, what, tile, feet (5, 3) world}."""
    out = []
    a = pk.a
    # props and plants
    f = a / "unreal_contribution.props.json"
    if f.is_file():
        c = json.loads(f.read_text(encoding="utf-8"))
        for e in c.get("entries", []):
            kind = e["kind"].split(".", 1)[1] if "." in e["kind"] else e["kind"]
            if kind in NOT_STANDING:
                continue
            px, py, pz = e["pivot"]
            for p in e.get("parts", []):
                mesh = pk.part_mesh(p["glb"], p["node"])
                if mesh is None:
                    continue
                F = feet(mesh[0])
                for xf, pid in zip(p["xforms"], p["ids"]):
                    x, y, z, yaw = xf[:4]
                    s = xf[4:7] if len(xf) >= 7 else (1.0, 1.0, 1.0)
                    W = _xform(F, px + x, py + y, pz + z, yaw, s)
                    out.append({"id": pid, "what": e["kind"], "feet": W, "self": None})
    # roof equipment: AG4's instanced roof parts, per building
    mf = a / "manifest.json"
    if mf.is_file():
        man = json.loads(mf.read_text(encoding="utf-8"))
        for bid, rec in sorted(man.get("buildings", {}).items()):
            px, py, pz = rec["pivot"]
            for p in rec.get("parts", []):
                if not p.get("roof"):
                    continue
                mesh = pk.part_mesh(rec.get("parts_glb", ""), p["node"])
                if mesh is None:
                    continue
                F = feet(mesh[0])
                # (dunnage under an item on a roof form stands through the form where the
                # roof is higher under it: its legs may reach down its whole height)
                reach = max(REACH_M, float(np.ptp(mesh[0][:, 2])))                     if p["family"] == "dunnage" else REACH_M
                for xf in p["xforms"]:
                    W = _xform(F, px + xf[0], py + xf[1], pz + xf[2], xf[3])
                    out.append({"id": bid, "what": f"roof.{p['family']}", "feet": W,
                                "self": None, "reach": reach})
    # street pieces that stand on their feet
    for pid in pk.street_ids():
        k = pk.street_kind(pid)
        if k not in STANDING_STREET:
            continue
        T, _ = pk.street_tris(pid)
        F = feet(T.reshape(-1, 3))
        if F is not None:
            # (a column's footing may be set into the ground or the bed by up to 3 m)
            out.append({"id": pid, "what": k, "feet": F, "self": pk.oid.get(pid),
                        "reach": FOOTING_M, "bed": True})
    return out


def _dunnage(pk: Packs) -> dict[str, list]:
    """Roof dunnage tops (what roof items stand on): up-facing triangles per tile."""
    out: dict[str, list] = defaultdict(list)
    mf = pk.a / "manifest.json"
    if not mf.is_file():
        return out
    man = json.loads(mf.read_text(encoding="utf-8"))
    for bid, rec in sorted(man.get("buildings", {}).items()):
        px, py, pz = rec["pivot"]
        for p in rec.get("parts", []):
            if p.get("family") != "dunnage":
                continue
            mesh = pk.part_mesh(rec.get("parts_glb", ""), p["node"])
            if mesh is None:
                continue
            pos, _ = mesh
            # (a frame of steel members: what stands on it rests on its whole top, the plan
            # box of the frame at its top)
            lo, hi = pos.min(axis=0), pos.max(axis=0)
            top = np.array([[lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]],
                            [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
            quad = np.array([[0, 1, 2], [0, 2, 3]])
            for xf in p["xforms"]:
                W = _xform(top, px + xf[0], py + xf[1], pz + xf[2], xf[3])
                T = W[quad]
                c = T.mean(axis=(0, 1))
                out[tile_of(c[0], c[1])].append((T.astype(np.float32),
                                                 np.full(len(T), pk.owner(f"{bid}:dunnage"))))
    return out


def grounded(pk: Packs, model, floor: Floor) -> dict:
    things = _things(pk, model)
    dun = _dunnage(pk)
    by_tile: dict[str, list] = defaultdict(list)
    for i, th in enumerate(things):
        c = th["feet"][0]
        by_tile[tile_of(c[0], c[1])].append(i)
    gaps = np.full(len(things), np.nan)
    for t in sorted(by_tile):
        ix, iy = _tile_xy(t)
        extra = [x for k in _ring(ix, iy) for x in dun.get(k, ())]
        S = pk.surfaces(t, extra)
        ids = by_tile[t]
        P = np.concatenate([things[i]["feet"] for i in ids])
        ex = np.repeat(np.array([things[i]["self"] if things[i]["self"] is not None else -1
                                 for i in ids]), 5)
        R = np.repeat(np.array([things[i].get("reach", REACH_M) for i in ids]), 5)
        fl = floor.at(P[:, :2])
        # (in the water a footing stands on M16's bed)
        wb = np.repeat(np.array([bool(things[i].get("bed")) for i in ids]), 5)
        if wb.any():
            fl = np.where(wb & np.isnan(fl), floor.bed(P[:, :2]), fl)
        fl = np.where(P[:, 2] + R >= fl, fl, np.nan)     # (nan over the water too)
        zs = np.fmax(S.under(P, R, ex), fl)
        g = (P[:, 2] - zs).reshape(-1, 5)
        ok = g <= GAP_M
        for j, i in enumerate(ids):
            row = g[j]
            if ok[j].sum() >= 3:
                gaps[i] = float(np.nanmax(np.where(ok[j], row, -np.inf)))
            else:
                gaps[i] = float(np.nanmin(row)) if not np.all(np.isnan(row)) else np.inf
    steps = seams(pk, model)
    floating = [i for i in range(len(things)) if not gaps[i] <= GAP_M]
    by_what: dict[str, list] = defaultdict(lambda: [0, 0])
    for i, th in enumerate(things):
        by_what[th["what"]][0] += 1
    for i in floating:
        by_what[things[i]["what"]][1] += 1
    worst = sorted(floating, key=lambda i: (-min(gaps[i], 1e9), things[i]["id"]))[:LIST_MAX]
    # (what fails: what assetgen seats itself, roof items, dunnage and street pieces, and a
    # step a car would feel; props and plants stand at the model's heights (M20's
    # `prop_support`) and smaller steps are reported, as `asset_access` reports)
    failing = [i for i in floating if not things[i]["what"].startswith(REPORTED)]
    return {"id": "asset_grounded",
            "ok": not failing and steps["max_m"] <= STEP_FAIL_M,
            "things": len(things), "floating": len(floating), "failing": len(failing),
            "seams": steps,
            "by_kind": {k: {"things": v[0], "floating": v[1]}
                        for k, v in sorted(by_what.items()) if v[1]},
            "kinds": len(by_what),
            "worst": [{"id": things[i]["id"], "what": things[i]["what"],
                       "at": [C.m2(v) for v in things[i]["feet"][0]],
                       "gap_m": None if not np.isfinite(gaps[i]) else C.m(gaps[i])}
                      for i in worst]}


def seams(pk: Packs, model=None) -> dict:
    """A road meets its junctions: every vertex of a road piece's carriageway on the
    outline of a junction at one of its ends (its cut edge, within 3 cm) that lies on that
    junction piece's carriageway is within `GAP_M` of the junction's surface there (no step
    where a leg meets its junction), near where its centerline crosses the outline (within
    its half width and 1 m: not a road's side running along a junction's outline further
    out, M17's shared pavement)."""
    ring_of, own, cut = {}, {}, {}
    if model is not None:
        from citygen import geom as G
        jat = {j.node_id: j for j in model.junctions}
        for j in model.junctions:
            ring_of[j.id] = G.from_model_poly(j.polygon).exterior
        for s in model.road_segments:
            own[s.id] = {jat[n].id for n in (s.start, s.end) if n in jat}
            cl = shapely.LineString([(p[0], p[1]) for p in s.centerline])
            for n in (s.start, s.end):
                j = jat.get(n)
                if j is None:
                    continue
                x = cl.intersection(ring_of[j.id])
                pts = [p for p in shapely.get_parts(x) if p.geom_type == "Point"] \
                    if not x.is_empty else []
                if not pts:
                    cut[(s.id, j.id)] = None
                    continue
                # (the road's first crossing out of the junction from its node: its cut)
                at = [cl.project(p) for p in pts]
                k = at.index(min(at)) if n == s.start else at.index(max(at))
                cut[(s.id, j.id)] = (pts[k], s.width_m / 2.0 + 1.0)
    jt, jo = [], []
    for pid in pk.street_ids():
        if pk.street_kind(pid) != "street.junction":
            continue
        T, mats = pk.street_tris(pid)
        keep = np.array([m.startswith("asphalt") for m in mats],
                        dtype=bool)
        if len(T) and keep.any():
            jt.append(T[keep])
            jo.append(np.full(int(keep.sum()), pk.owner(pid)))
    out = {"legs": 0, "steps": 0, "max_m": 0.0, "worst": []}
    if not jt:
        return out
    S = Surfaces(np.concatenate(jt), np.concatenate(jo), min_nz=0.5)
    rows = []
    for pid in pk.street_ids():
        if pk.street_kind(pid) != "street.road":
            continue
        T, mats = pk.street_tris(pid)
        keep = np.array([m.startswith("asphalt") for m in mats],
                        dtype=bool)
        if not len(T) or not keep.any():
            continue
        P = np.unique(np.round(T[keep].reshape(-1, 3), 3), axis=0)
        p_, t_ = S.candidates(P[:, :2])
        if not len(p_):
            continue
        ins, z = S.heights(P[:, :2], p_, t_, eps=1e-4)
        dz = np.abs(P[p_, 2] - z)
        sel = ins & (dz < 1.0)
        if model is not None:
            mine = own.get(pid, set())
            jn = [pk.names[int(o)] for o in S.owner[t_].tolist()]
            on = np.array([j in mine for j in jn], dtype=bool)
            sel &= on
            for k in np.nonzero(sel)[0].tolist():
                pt = shapely.Point(P[p_[k], :2])
                c = cut.get((pid, jn[k]))
                if shapely.distance(ring_of[jn[k]], pt) > 0.03 or c is None or \
                        shapely.distance(c[0], pt) > c[1]:
                    sel[k] = False
        if not sel.any():
            continue
        out["legs"] += len({int(S.owner[t]) for t in t_[sel].tolist()})
        worst = float(dz[sel].max())
        if worst > GAP_M:
            out["steps"] += 1
            i = int(np.argmax(np.where(sel, dz, -1.0)))
            rows.append((worst, pid, pk.names[int(S.owner[t_[i]])],
                         [C.m2(v) for v in P[p_[i]]]))
        out["max_m"] = max(out["max_m"], C.m(worst))
    rows.sort(key=lambda r: (-r[0], r[1]))
    out["worst"] = [{"road": r[1], "junction": r[2], "step_m": C.m(r[0]), "at": r[3]}
                    for r in rows[:LIST_MAX]]
    return out


# ---------------------------------------------------------------------------
# asset_clash
# ---------------------------------------------------------------------------

class Masses:
    """Every building mass as a prism (its footprint 10 cm in, its floor and roof 10 cm
    in), world heights (M13's base), with the building's portals per line."""

    def __init__(self, m):
        from citygen import geom as G
        self.polys, self.z, self.bid, self.portals = [], [], [], {}
        for b in m.buildings:
            base = float(getattr(b, "base_m", None) or 0.0)
            for p in getattr(b, "portals", None) or []:
                self.portals.setdefault(b.id, []).append(
                    (p.line_id, base + p.z0_m, base + p.z1_m))
            for ms in b.masses:
                if ms.role in ("void",) or ms.shape == "ring":
                    continue
                if ms.z1_m - ms.z0_m < 2 * INSET_M + 0.05:
                    continue
                with G.canonical():
                    poly = G.from_model_poly(ms.footprint).buffer(-INSET_M, join_style="mitre")
                if poly.is_empty:
                    continue
                self.polys.append(poly)
                self.z.append((base + ms.z0_m + INSET_M, base + ms.z1_m - INSET_M))
                self.bid.append(b.id)
        self.tree = shapely.STRtree(self.polys) if self.polys else None
        self.z = np.array(self.z) if self.z else np.zeros((0, 2))

    def inside(self, P: np.ndarray):
        """(point index, mass index) pairs of points inside a mass."""
        if self.tree is None or not len(P):
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        pts = shapely.points(P[:, 0], P[:, 1])
        pi, mi = self.tree.query(pts, predicate="within")
        ok = (P[pi, 2] > self.z[mi, 0]) & (P[pi, 2] < self.z[mi, 1])
        return pi[ok], mi[ok]


def _verts(T: np.ndarray) -> np.ndarray:
    """A mesh's vertices and its triangles' middles (a long triangle through a mass has no
    vertex in it), unique."""
    if not len(T):
        return np.zeros((0, 3))
    P = np.concatenate([T.reshape(-1, 3), T.mean(axis=1)])
    return np.unique(np.round(P, 3), axis=0)


def clash(pk: Packs, model) -> dict:
    ms = Masses(model)
    out = {"road_into_building": [], "building_over_road": [], "bridge_twice": [],
           "transit_through_building": [], "transit_through_platform": []}
    counts = {k: 0 for k in out}
    lines_of = {}
    for st in model.structures:
        a = st.attrs or {}
        if a.get("line_id"):
            lines_of[st.id] = a["line_id"]
    # -- street pieces into masses
    for pid in pk.street_ids():
        k = pk.street_kind(pid)
        road = k in ROADLIKE
        transit = k in TRANSIT and pid.split(".glass")[0] in lines_of
        if not (road or transit):
            continue
        T, mats = pk.street_tris(pid)
        if road:
            # (the carriageway, its deck, barriers and embankment: not its sidewalk corners,
            # which meet the building line)
            keep = np.array([m.split(".")[0] in ("asphalt", "marking", "concrete")
                             for m in mats], dtype=bool)
            T = T[keep] if len(T) else T
        P = _verts(T)
        pi, mi = ms.inside(P)
        if transit and len(pi):
            ln = lines_of.get(pid)
            keep = []
            for a_, b_ in zip(pi.tolist(), mi.tolist()):
                bands = ms.portals.get(ms.bid[b_], ())
                z = P[a_, 2]
                if any(l_ == ln and z0 - 1.0 <= z <= z1 + 1.0 for l_, z0, z1 in bands):
                    continue
                keep.append((a_, b_))
            pi = np.array([x for x, _ in keep], dtype=np.int64)
            mi = np.array([y for _, y in keep], dtype=np.int64)
        if len(pi):
            key = "road_into_building" if road else "transit_through_building"
            bl = sorted({ms.bid[j] for j in mi.tolist()})
            counts[key] += 1
            out[key].append({"piece": pid, "kind": k, "buildings": bl[:5],
                             "vertices": int(len(pi)),
                             "at": [C.m2(v) for v in P[pi[0]]]})
    # -- tracks through platforms
    plats = [st for st in model.structures if (st.attrs or {}).get("role") == "platform"
             and st.footprint is not None]
    if plats:
        from citygen import geom as G

        from ..streets.transit import platform_rings
        pp = []
        for st in plats:
            # (the platform as drawn: less the tracks beside it, `platform_rings`)
            rings = platform_rings(model, st)
            poly = G.from_model_poly(st.footprint) if rings is None else \
                shapely.union_all([shapely.Polygon(r, hs) for r, hs in rings])
            pp.append(poly.buffer(-INSET_M, join_style="mitre"))
        ptree = shapely.STRtree(pp)
        floor = Floor(model)
        tracks = {st.id for st in model.structures if st.kind in ("deck", "tube") and
                  (st.attrs or {}).get("line_id") and not (st.attrs or {}).get("station")}
        for pid in pk.street_ids():
            if pid.split(".glass")[0] not in tracks:
                continue
            T, _ = pk.street_tris(pid)
            P = _verts(T)
            if not len(P):
                continue
            pi, si = ptree.query(shapely.points(P[:, 0], P[:, 1]), predicate="within")
            if not len(pi):
                continue
            g = floor.at(P[pi, :2])
            g = np.where(np.isnan(g), 0.0, g)
            z0 = np.array([plats[j].z0_m for j in si]) + g + INSET_M
            z1 = np.array([plats[j].z1_m for j in si]) + g - INSET_M
            ok = (P[pi, 2] > z0) & (P[pi, 2] < z1)
            if ok.any():
                counts["transit_through_platform"] += 1
                out["transit_through_platform"].append(
                    {"piece": pid, "platforms": sorted({plats[j].id for j in si[ok]})[:5],
                     "vertices": int(ok.sum())})
    # -- bridges drawn twice: deck tops of bridge and raised road pieces over each other
    decks = [pid for pid in pk.street_ids() if pk.street_kind(pid) in ("street.bridge",
                                                                       "street.road")]
    tris, own = [], []
    for pid in decks:
        T, mats = pk.street_tris(pid)
        if not len(T):
            continue
        # (the deck tops: carriageway, paving and deck; not parapets, copings or steps)
        keep = np.array([m.split(".")[0] in ("asphalt", "paving") or m == "concrete.deck"
                         for m in mats], dtype=bool)
        T = T[keep]
        if pk.street_kind(pid) == "street.road" and (not len(T) or T[:, :, 2].max() < 0.6):
            continue
        tris.append(T)
        own.append(np.full(len(T), pk.owner(pid)))
    if tris:
        S = Surfaces(np.concatenate(tris), np.concatenate(own), min_nz=0.5)
        if len(S.t):
            c = S.t.mean(axis=1)
            zs = S.under(c + [0.0, 0.0, DECK_DZ_M], 2 * DECK_DZ_M, S.owner, floor=None)
            hit = ~np.isnan(zs)
            pairs: dict = defaultdict(float)
            if hit.any():
                # who is under (the highest other surface within the band)
                idx = np.nonzero(hit)[0]
                pid_, tid_ = S.candidates(c[idx, :2])
                ins, z = S.heights(c[idx, :2], pid_, tid_)
                m_ = ins & (S.owner[tid_] != S.owner[idx[pid_]]) & \
                    (np.abs(z - c[idx[pid_], 2]) <= DECK_DZ_M)
                for a_, b_ in zip(idx[pid_[m_]].tolist(), tid_[m_].tolist()):
                    o1, o2 = int(S.owner[a_]), int(S.owner[b_])
                    pairs[(min(o1, o2), max(o1, o2), o1)] = 0.0
                seen = set()
                for a_, b_ in zip(idx[pid_[m_]].tolist(), tid_[m_].tolist()):
                    if a_ in seen:
                        continue
                    seen.add(a_)
                    o1, o2 = int(S.owner[a_]), int(S.owner[b_])
                    pairs[(min(o1, o2), max(o1, o2), o1)] += float(S.area[a_])
            tot: dict = defaultdict(float)
            for (o1, o2, _), ar in pairs.items():
                tot[(o1, o2)] = max(tot[(o1, o2)], ar)
            ends = {s.id: {s.start, s.end} for s in model.road_segments}
            for (o1, o2), ar in sorted(tot.items()):
                # (two roads leaving one node overlap at their gore by design: a ramp's
                # diverge off its viaduct)
                if ends.get(pk.names[o1], set()) & ends.get(pk.names[o2], set()):
                    continue
                if ar > OVERLAP_M2:
                    counts["bridge_twice"] += 1
                    out["bridge_twice"].append({"pieces": [pk.names[o1], pk.names[o2]],
                                                "area_m2": C.m2(ar)})
    # -- building parts and fronts over a carriageway
    car, cown = [], []
    for pid in pk.street_ids():
        if pk.street_kind(pid) not in ROADLIKE:
            continue
        T, mats = pk.street_tris(pid)
        keep = np.array([m.startswith("asphalt") for m in mats], dtype=bool)
        if len(T) and keep.any():
            car.append(T[keep])
            cown.append(np.full(int(keep.sum()), pk.owner(pid)))
    if car:
        _over_road(pk, model, Surfaces(np.concatenate(car), np.concatenate(cown), min_nz=0.5),
                   out, counts)
    # (a building's own shell within `SHELL_REPORT_M` of its footprint over a lane is the
    # model's mass pressed against the road: reported, not failed)
    reported = sum(1 for r in out["building_over_road"]
                   if r["what"] == ["shell"] and r["reach_m"] <= SHELL_REPORT_M)
    for k in out:
        out[k] = sorted(out[k], key=lambda r: json.dumps(r, sort_keys=True))[:LIST_MAX]
    n = sum(counts.values())
    return {"id": "asset_clash", "ok": n - reported == 0, "clashes": n,
            "reported": reported, "counts": counts, "worst": out}


def _over_road(pk: Packs, model, S: Surfaces, out: dict, counts: dict):
    """Building vertices (shell, front, instanced parts) outside their own footprint, over a
    carriageway within the headroom."""
    from citygen import geom as G
    foot = {}
    for b in model.buildings:
        polys = [G.from_model_poly(ms.footprint) for ms in b.masses]
        if b.footprint is not None:
            polys.append(G.from_model_poly(b.footprint))
        if not polys:
            continue
        with G.canonical():
            foot[b.id] = shapely.union_all(polys).buffer(RELIEF_M, join_style="mitre")
    man = {}
    mf = pk.a / "manifest.json"
    if mf.is_file():
        man = json.loads(mf.read_text(encoding="utf-8")).get("buildings", {})
    d = pk.a / "tiles"
    hits: dict[str, list] = {}
    for f in sorted(d.glob("t*.glb")) if d.is_dir() else []:
        for nd in GL.read(f):
            bid = nd.root
            fp = foot.get(bid)
            if fp is None:
                continue
            T = nd.triangles()
            _test_over(bid, _verts(T), fp, S, hits)
    for bid, rec in sorted(man.items()):
        fp = foot.get(bid)
        if fp is None:
            continue
        px, py, pz = rec["pivot"]
        for p in rec.get("parts", []):
            mesh = pk.part_mesh(rec.get("parts_glb", ""), p["node"])
            if mesh is None:
                continue
            pos = mesh[0]
            for xf in p["xforms"]:
                W = _xform(pos, px + xf[0], py + xf[1], pz + xf[2], xf[3])
                _test_over(bid, W, fp, S, hits, part=p["type"])
    for bid in sorted(hits):
        counts["building_over_road"] += 1
        h = hits[bid]
        out["building_over_road"].append({"building": bid, "vertices": h[0],
                                          "roads": sorted(h[1])[:5], "what": sorted(h[2])[:5],
                                          "at": h[3], "over_m": h[4], "reach_m": h[5]})


def _test_over(bid, P, fp, S: Surfaces, hits: dict, part: str | None = None):
    if not len(P):
        return
    out = ~shapely.contains_xy(fp, P[:, 0], P[:, 1])
    if not out.any():
        return
    Q = P[out]
    zs = S.under(Q, -0.05, None, floor=None)
    dz = Q[:, 2] - zs
    bad = ~np.isnan(zs) & (dz > 0.05) & (dz < HEADROOM_M)
    if not bad.any():
        return
    # which road: the owner of the surface under the farthest bad vertex
    B = Q[bad]
    reach = shapely.distance(fp, shapely.points(B[:, 0], B[:, 1])) + RELIEF_M
    k = int(np.argmax(reach))
    i = int(np.nonzero(bad)[0][k])
    pid_, tid_ = S.candidates(Q[i:i + 1, :2])
    ins, z = S.heights(Q[i:i + 1, :2], pid_, tid_)
    h = hits.setdefault(bid, [0, set(), set(), [C.m2(v) for v in Q[i]], C.m(float(dz[i])),
                              0.0])
    h[0] += int(bad.sum())
    h[1] |= {int(S.owner[t]) for t in tid_[ins & (z <= Q[i, 2] - 0.05)].tolist()}
    h[2].add(part or "shell")
    if float(reach[k]) > h[5]:
        h[3], h[4], h[5] = [C.m2(v) for v in Q[i]], C.m(float(dz[i])), C.m(float(reach[k]))


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------

def build(model, out_dir: Path, log=None, progress=None) -> dict:
    """Both checks on the packs under out_dir (BUILD/assets); the report written where its
    bytes change (`written`: the files written, 0 to 2)."""
    from ..progress import Progress
    P = progress if progress is not None else Progress(quiet=True)
    t0 = time.perf_counter()
    a = Path(out_dir)
    pk = Packs(a, model)
    with P.stage("fit: reading the packs"):
        pk.load()
    t1 = time.perf_counter()
    floor = Floor(model)
    with P.stage("fit: asset_grounded"):
        g = grounded(pk, model, floor)
    t2 = time.perf_counter()
    with P.stage("fit: asset_clash"):
        c = clash(pk, model)
    # owner ids of roads named
    for r in c["worst"].get("building_over_road", []):
        r["roads"] = sorted(pk.names[int(x)] for x in r["roads"])
    t3 = time.perf_counter()
    rep = {"city": model.name, "ok": g["ok"] and c["ok"], "checks": [g, c],
           "seconds": {"load": round(t1 - t0, 2), "grounded": round(t2 - t1, 2),
                       "clash": round(t3 - t2, 2), "total": round(t3 - t0, 2)}}
    text = report_text(rep)
    body = {k: v for k, v in rep.items() if k != "seconds"}
    rep["written"] = int(MF.write_if_changed(a / "fit_report.json", MF.dumps(body))) + \
        int(MF.write_if_changed(a / "fit_report.txt", text))
    if log:
        for line in text.splitlines()[:3]:
            log(line)
    return rep


def report_text(rep: dict) -> str:
    lines = [f"fit checks: {rep['city']}: {'all pass' if rep['ok'] else 'FAIL'}"]
    for c in rep["checks"]:
        if c["id"] == "asset_grounded":
            lines.append(f"{'PASS' if c['ok'] else 'FAIL'} asset_grounded: {c['things']} things "
                         f"({c['kinds']} kinds), {c['floating']} not resting on a surface "
                         f"({c['failing']} failing, the rest props and plants at the "
                         f"model's heights, reported)")
            sm = c["seams"]
            lines.append(f"    roads on their junctions: {sm['legs']} legs, {sm['steps']} roads "
                         f"with a step over {GAP_M} m (largest {sm['max_m']} m; failing over "
                         f"{STEP_FAIL_M} m)")
            for w in sm["worst"][:10]:
                lines.append(f"    step: {json.dumps(w, sort_keys=True)}")
            for k, v in c["by_kind"].items():
                lines.append(f"    {k}: {v['floating']} of {v['things']}")
            for w in c["worst"][:15]:
                lines.append(f"    {w['id']} ({w['what']}) at {w['at']} gap {w['gap_m']}")
        else:
            lines.append(f"{'PASS' if c['ok'] else 'FAIL'} asset_clash: {c['clashes']} "
                         f"({', '.join(f'{k} {v}' for k, v in c['counts'].items())}; "
                         f"{c['reported']} reported: a shell within {SHELL_REPORT_M} m of "
                         f"its footprint)")
            for k, rows in c["worst"].items():
                for r in rows[:10]:
                    lines.append(f"    {k}: {json.dumps(r, sort_keys=True)}")
    return "\n".join(lines) + "\n"
