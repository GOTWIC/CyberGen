"""AG12's pieces of a city: gathered from the model (M16's water bodies, banks and levels,
the blockout's water objects they replace, AG7's bridge piers), each into `inputs` that hold
everything its maker reads, so a piece is made from its inputs alone and kept while their
hash is (as AG7's street pieces, `assetgen/streets/pieces.py`).

- **Body pieces** (`<body>@<tile>`): a water body's own water in a 256 m tile (its polygon
  less the bodies before it in M16's order, the order `Beds.body_at` takes: so two bodies
  never overlap), with the body's depth, profile and flow, its level, its banks within
  reach of the tile, the edges it shares with other water (the bed's skirts), the bridge
  piers there (foam) and the sea's exposure raster near it (waves). They make the bed
  (`<body>.bed.<tile>`) and the surface (`<body>.water.<tile>`, a LOD chain).
- **Bank pieces** (`<bank id>`): a natural slope, beach, marsh edge, riprap or road
  embankment, or a stone wall along a river or the sea (the quays and the waterways' canal
  walls are AG7's), with its body's level and the ground along it.
- **The drop** (`water.blockout`): the blockout's water objects no piece takes the place of
  (sea sheets of tiles with no sea, the quay and canal wall bands AG7 draws).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, box

from citygen import geom as G
from citygen import water as WA

from .. import canon as C
from ..streets.ctx import tile_key, tile_name
from . import materials as MT

TILE_M = 256.0
REACH_PAD_M = 10.0
EXPO_CELL_M = 16.0
EXPO_BLUR = 2                  # a (2 k + 1) square box blur of the exposure raster
TERRAIN_LIFT_M = 0.1           # the bed over M13's ground grid (it carries M16's beds too)
MARSH_SHARE = 0.4              # a body this much along marsh edges is marsh water
AG12_BANKS = ("natural_bank", "beach", "marsh_edge", "riprap", "road_embankment",
              "canal_wall")


@dataclass
class Piece:
    id: str
    kind: str
    maker: str
    tile: str
    replaces: list[str]
    inputs: dict
    covers: list[str] = field(default_factory=list)

    def digest(self) -> str:
        from .makers import VERSIONS
        return C.digest({"maker": self.maker, "v": VERSIONS.get(self.maker, 1),
                         "inputs": self.inputs})


def _q(v: float) -> float:
    return C.m2(float(v))


def _pts(line) -> list[list[float]]:
    return [[_q(p[0]), _q(p[1])] for p in line]


def _polys(geom) -> list[dict]:
    return G.to_model_polys(geom) if geom is not None and not geom.is_empty else []


class WCtx:
    """What the water pieces read from a city."""

    def __init__(self, m, assets: Path | None = None):
        self.m = m
        self.flat = m.terrain is None
        x0, y0, x1, y1 = m.bounds
        self.bounds = (x0, y0, x1, y1)
        with G.canonical():
            self.bodies = WA.bodies(m)
            own, prev = {}, []
            for b in self.bodies:
                own[b.id] = G.diff(b.poly, G.union(prev)) if prev else b.poly
                prev.append(b.poly)
            self.own = own
        self.lines_of: dict[str, list] = {}
        for k in m.banks:
            self.lines_of.setdefault(k.water_id, []).append(k)
        self.levels = WA.Levels(m)
        self.keys, self.key_tile, self.water_objects = _blockout_keys(m)
        self.piers = _piers(assets)
        self.ptree = shapely.STRtree([p for p in self.piers]) if self.piers else None
        self.expo = _exposure(m) if m.seas and m.seas[0].exposure else None
        self.quays = {q.id: q for q in m.quays}
        self.waterway = {w.id: w for w in m.waterways}

    def tiles(self):
        x0, y0, x1, y1 = self.bounds
        ix0, iy0 = tile_key(x0, y0)
        ix1, iy1 = tile_key(x1 - 1e-6, y1 - 1e-6)
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                tb = (max(ix * TILE_M, x0), max(iy * TILE_M, y0),
                      min((ix + 1) * TILE_M, x1), min((iy + 1) * TILE_M, y1))
                yield tile_name(ix, iy), tb

    def water_kind(self, b) -> str:
        bks = self.lines_of.get(b.id, [])
        tot = sum(G.length(LineString(k.line)) for k in bks)
        marsh = sum(G.length(LineString(k.line)) for k in bks if k.kind == "marsh_edge")
        if b.kind not in ("sea", "basin", "marina", "ornamental") and tot > 0 and \
                marsh / tot >= MARSH_SHARE:
            return "marsh"
        return MT.KIND_OF.get(b.kind, "canal")

    def body(self, b) -> dict:
        e = b.ent
        bed = e.bed
        out = {"id": b.id, "kind": b.kind, "coll": b.coll, "water": self.water_kind(b),
               "depth_m": _q(e.depth_m), "profile": bed.profile, "reach_m": _q(bed.reach_m),
               "material": bed.material}
        if b.coll in ("rivers", "channels") and bed.along:
            out["along"] = [[a.s, a.z] for a in bed.along]
            out["centerline"] = _pts(e.centerline)
            out["widths"] = [_q(w) for w in e.width_m]
        fl = e.flow
        if fl is not None:
            out["flow"] = {"kind": fl.kind, "speed": fl.speed_m_s, "line": _pts(fl.line)}
        return out

    def level(self, b) -> dict:
        if self.flat:
            s = b.ent.bed.surface_m if b.ent.bed is not None else None
            return {"z": _q(s if s is not None else -WA.FREEBOARD_M)}
        w = self.levels.lv.get(b.id)
        if w is None:
            return {"z": 0.0}
        if w.profile and b.id in self.levels.cl:
            return {"z": _q(w.level_m), "line": _pts(self.levels.cl[b.id][0]),
                    "profile": [[p.s, p.z] for p in w.profile]}
        return {"z": _q(w.level_m)}

    def reach(self, b) -> float:
        """How far a bank can set this body's bed (its reach, a river's widest half width,
        and its widest bank)."""
        r = float(b.ent.bed.reach_m)
        if b.coll in ("rivers", "channels"):
            r = max(r, max(b.ent.width_m) / 2.0)
        if b.ent.bed.profile == "flat":
            r = max(r, WA.FLAT_REACH_M)
        w = max((k.width_m * (1.0 + k.toe_m / max(k.height_m or 1.5, 0.1))
                 for k in self.lines_of.get(b.id, [])), default=0.0)
        return r + w + REACH_PAD_M

    def bank(self, k) -> dict:
        h = k.height_m
        if h is None:
            q = self.quays.get(k.quay_id)
            h = q.deck_z_m if q is not None else WA.FREEBOARD_M
        return {"id": k.id, "kind": k.kind, "line": _pts(k.line), "w": _q(k.width_m),
                "toe": _q(k.toe_m), "h": _q(h)}


# --- gathering -----------------------------------------------------------------------------

def gather(cx: WCtx) -> tuple[list[Piece], list[str]]:
    """The body and bank pieces of a city, and the blockout water objects none takes."""
    out: list[Piece] = []
    m = cx.m
    if not cx.bodies or not m.banks and all(b.ent.depth_m is None for b in cx.bodies):
        return out, []
    taken: set[str] = set()
    with G.canonical():
        polys = {b.id: b.poly for b in cx.bodies}
        for b in cx.bodies:
            if b.ent.depth_m is None or b.ent.bed is None:
                continue
            own = cx.own[b.id]
            if own.is_empty:
                continue
            others = [polys[o.id] for o in cx.bodies if o.id != b.id]
            oth = G.union(others) if others else None
            bks = cx.lines_of.get(b.id, [])
            btree = shapely.STRtree([LineString(k.line) for k in bks]) if bks else None
            R = cx.reach(b)
            body = cx.body(b)
            level = cx.level(b)
            open_ = None
            if oth is not None and not oth.is_empty:
                bd = shapely.intersection(own.boundary, oth.buffer(0.05))
                open_ = bd if not bd.is_empty else None
            ox0, oy0, ox1, oy1 = own.bounds
            for tname, tb in cx.tiles():
                if tb[2] <= ox0 or tb[0] >= ox1 or tb[3] <= oy0 or tb[1] >= oy1:
                    continue
                tbox = box(*tb)
                region = G.inter(own, tbox)
                if region.is_empty or G.area(region) < 0.5:
                    continue
                near = []
                if btree is not None:
                    hit = sorted(int(i) for i in btree.query(tbox, predicate="dwithin",
                                                            distance=R))
                    near = [cx.bank(bks[i]) for i in hit]
                inp = {"body": body, "level": level, "banks": near,
                       "region": _polys(region), "box": [_q(v) for v in tb],
                       "origin": [_q((tb[0] + tb[2]) / 2.0), _q((tb[1] + tb[3]) / 2.0)],
                       "lift": TERRAIN_LIFT_M if not cx.flat else 0.0}
                if open_ is not None:
                    ol = shapely.intersection(open_, tbox.buffer(0.01))
                    # (GEOS's order of the parts and their direction are its own: fixed here)
                    lines = sorted(min(p, p[::-1]) for p in
                                   (_pts(g.coords) for g in _lines(ol) if g.length > 0.05))
                    if lines:
                        inp["open"] = lines
                piers = _near_piers(cx, tb)
                if piers:
                    inp["piers"] = piers
                if cx.expo is not None and b.kind == "sea":
                    inp["waves"] = _wave_patch(cx.expo, tb)
                rep = []
                for name in (f"city.sea.{tname}" if b.kind == "sea" else
                             f"city.water.{tname}", f"city.bed.{tname}"):
                    if name in cx.water_objects:
                        rep.append(name)
                        taken.add(name)
                out.append(Piece(f"{b.id}@{tname}", f"water.body.{body['water']}", "body",
                                 tname, rep, inp))
    for k in m.banks:
        if k.kind not in AG12_BANKS:
            continue
        if k.kind == "canal_wall" and k.water_id in cx.waterway:
            continue                 # (AG7's canal walls)
        b = next(x for x in cx.bodies if x.id == k.water_id)
        rec = cx.bank(k)
        inp = {"bank": rec, "level": cx.level(b), "body": {"id": b.id, "kind": b.kind},
               "origin": list(_bbox_center(rec["line"]))}
        if not cx.flat:
            from ..streets.ctx import Ground
            if not hasattr(cx, "_ground"):
                cx._ground = Ground(m)
            inp["ground"] = cx._ground.samples(rec["line"])
        rep = cx.keys.get(k.id, [])
        taken.update(rep)
        tile = next((cx.key_tile[r] for r in rep if r in cx.key_tile), None) or \
            tile_name(*tile_key(*inp["origin"]))
        out.append(Piece(k.id, f"water.bank.{k.kind}", "bank", tile, list(rep), inp))
    drop = sorted(n for n in cx.water_objects if n not in taken)
    return out, drop


def _lines(g) -> list:
    if g is None or g.is_empty:
        return []
    t = g.geom_type
    if t == "LineString":
        return [g]
    if t in ("MultiLineString", "GeometryCollection"):
        out = []
        for x in g.geoms:
            out += _lines(x)
        return out
    return []


def _bbox_center(pts) -> tuple[float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return _q((min(xs) + max(xs)) / 2.0), _q((min(ys) + max(ys)) / 2.0)


def _near_piers(cx: WCtx, tb) -> list:
    if cx.ptree is None:
        return []
    hit = sorted(int(i) for i in cx.ptree.query(box(*tb).buffer(5.0)))
    return [[[_q(x), _q(y)] for x, y in list(cx.piers[i].exterior.coords)[:-1]] for i in hit]


def _piers(assets: Path | None) -> list:
    """AG7's bridge pier footprints (its streets manifest's notes), in a fixed order."""
    if assets is None:
        return []
    f = Path(assets) / "streets" / "manifest.json"
    if not f.is_file():
        return []
    man = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for pid in sorted(man.get("pieces", {})):
        for ring in (man["pieces"][pid].get("notes") or {}).get("piers") or []:
            if len(ring) >= 3:
                out.append(shapely.Polygon(ring))
    return out


def _exposure(m) -> dict:
    """M16's exposure zones as weights on a 16 m raster over the map, blurred."""
    x0, y0, x1, y1 = m.bounds
    c = EXPO_CELL_M
    nx = int(math.ceil((x1 - x0) / c))
    ny = int(math.ceil((y1 - y0) / c))
    X, Y = np.meshgrid(x0 + (np.arange(nx) + 0.5) * c, y0 + (np.arange(ny) + 0.5) * c)
    v = np.zeros(X.shape)
    for z in m.seas[0].exposure:
        p = G.from_model_poly(z.polygon)
        shapely.prepare(p)
        v = np.where(shapely.contains_xy(p, X, Y), FW[z.kind], v)
    k = EXPO_BLUR
    pad = np.pad(v, k, mode="edge")
    acc = np.zeros_like(v)
    for dj in range(2 * k + 1):
        for di in range(2 * k + 1):
            acc = acc + pad[dj:dj + ny, di:di + nx]
    v = np.round(acc / float((2 * k + 1) ** 2), 3)
    return {"x0": x0, "y0": y0, "c": c, "v": v}


FW = {"open": 1.0, "sheltered": 0.5, "harbor": 0.15}


def _wave_patch(ex: dict, tb) -> dict:
    c = ex["c"]
    v = ex["v"]
    i0 = max(0, int(math.floor((tb[0] - ex["x0"]) / c)) - 2)
    j0 = max(0, int(math.floor((tb[1] - ex["y0"]) / c)) - 2)
    i1 = min(v.shape[1], int(math.ceil((tb[2] - ex["x0"]) / c)) + 2)
    j1 = min(v.shape[0], int(math.ceil((tb[3] - ex["y0"]) / c)) + 2)
    sub = v[j0:j1, i0:i1]
    return {"x0": _q(ex["x0"] + i0 * c), "y0": _q(ex["y0"] + j0 * c), "cell": c,
            "nx": int(sub.shape[1]), "ny": int(sub.shape[0]),
            "v": [float(x) for x in sub.ravel().tolist()]}


def _blockout_keys(m) -> tuple[dict[str, list[str]], dict[str, str], set[str]]:
    """Bank id -> the blockout's joined bank objects that draw it, each object's tile, and
    the names of every blockout water object (sea sheets, inland water, beds, banks)."""
    from citygen import blockout as BO
    with G.canonical():
        P = BO._Plan(m)
        BO._land_and_water(P)
        BO._banks(P)
        BO._beds(P)
    keys: dict[str, list[str]] = {}
    tiles: dict[str, str] = {}
    names: set[str] = set()
    for o in P.objects:
        cat = o["category"]
        if cat not in ("sea", "water", "bed") and not cat.startswith("bank_"):
            continue
        names.add(o["name"])
        tiles[o["name"]] = o["tile"]
        for i in o["props"].get("citygen_ids") or []:
            keys.setdefault(i, []).append(o["name"])
    return {k: sorted(set(v)) for k, v in keys.items()}, tiles, names
