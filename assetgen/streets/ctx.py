"""What the street pieces read from a city: indexes over the model, the ground (M13), the
district styles, and the blockout objects each piece supersedes.

The ground follows M13's contract (PR #28): a road's surface is its `ground` grade line plus
its `z_profile`, a node's is `ground_m` plus its z, anything else stands on the terrain's
finished `ground` grid at its point (bilinear, as M13 samples it). Where the model has none of
these (a flat city) the ground is 0.

The blockout keys come from citygen's own blockout code run on the model (the streets, open
space, megasite and tunnel parts of `citygen/blockout.py`, read only), so a piece's
`replaces` names exactly the objects M15 imports.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import shapely

from citygen import geom as G
from citygen.model import CityModel

from .. import canon as C
from . import materials as MT

TILE_M = 256.0


def tile_key(x: float, y: float) -> tuple[int, int]:
    return math.floor(x / TILE_M), math.floor(y / TILE_M)


def tile_name(ix: int, iy: int) -> str:
    """The blockout's tile names (`citygen/blockout.py`)."""
    return f"t{ix:+03d}{iy:+03d}"


def tile_of(x: float, y: float) -> str:
    return tile_name(*tile_key(x, y))


class Ground:
    """The finished ground of a model: bilinear on M13's grid, 0 on a flat city; the water's
    level (M13's on a terrain city, M16's `WaterBed.surface_m` on a flat one)."""

    def __init__(self, m: CityModel):
        t = getattr(m, "terrain", None)
        self.flat = t is None
        # AG12: M16's water surface of a flat city (the freeboard under the ground), by body
        self.surface = {e.id: float(e.bed.surface_m)
                        for e in [*m.seas, *m.rivers, *m.channels, *m.waterways]
                        if e.bed is not None and e.bed.surface_m is not None}
        if not self.flat:
            rows = t.ground or t.natural
            self.x0, self.y0, self.cell = float(t.x0), float(t.y0), float(t.cell_m)
            self.arr = np.array(rows, dtype=np.float64)
            self.nx, self.ny = self.arr.shape[1], self.arr.shape[0]
            self.water = {w.water_id: w for w in t.water_levels}

    def at(self, x: float, y: float) -> float:
        if self.flat:
            return 0.0
        fx = (x - self.x0) / self.cell
        fy = (y - self.y0) / self.cell
        fx = min(max(fx, 0.0), self.nx - 1.000001)
        fy = min(max(fy, 0.0), self.ny - 1.000001)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        a = self.arr
        h0 = float(a[j, i]) * (1.0 - tx) + float(a[j, i + 1]) * tx
        h1 = float(a[j + 1, i]) * (1.0 - tx) + float(a[j + 1, i + 1]) * tx
        return h0 * (1.0 - ty) + h1 * ty

    def samples(self, pts) -> list[float] | None:
        """Ground under points, to the millimeter; None on a flat city (so a flat city's
        inputs say nothing about terrain)."""
        if self.flat:
            return None
        return [C.m(self.at(p[0], p[1])) for p in pts]

    def along_road(self, seg, pts) -> list[float] | None:
        """The road's grade line under points near it (M13 lifts a road tunnel, its portals
        and open approaches by it), else the terrain; None on a flat city."""
        if self.flat:
            return None
        g = getattr(seg, "ground", None) if seg is not None else None
        if not g:
            return self.samples(pts)
        from .path import Path, Profile
        path = Path(seg.centerline)
        prof = Profile.of(g)
        return [C.m(prof(path.project(p[0], p[1])[0])) for p in pts]

    def water_level(self, wid: str | None, default: float) -> float:
        if self.flat:
            return self.surface.get(wid, default) if wid is not None else default
        if wid is None or wid not in self.water:
            return default
        return float(self.water[wid].level_m)


def dump(e) -> dict:
    return e.model_dump(mode="json", exclude_none=True)


def bbox_center(pts) -> tuple[float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return C.m2((min(xs) + max(xs)) / 2.0), C.m2((min(ys) + max(ys)) / 2.0)


class Ctx:
    def __init__(self, m: CityModel, spec=None):
        self.m = m
        self.spec = spec
        self.ground = Ground(m)
        self.idx = {e.id: e for e in m.entities()}
        self.dist = {d.id: d for d in m.districts}
        self.node = {n.id: n for n in m.road_nodes}
        self.seg = {s.id: s for s in m.road_segments}
        self.seg_at_node: dict[str, list] = defaultdict(list)
        for s in m.road_segments:
            self.seg_at_node[s.start].append(s)
            if s.end != s.start:
                self.seg_at_node[s.end].append(s)
        self.junction_at = {}
        for j in m.junctions:
            self.junction_at.setdefault(j.node_id, j)
        self.lanes: dict[str, list] = defaultdict(list)
        for ln in m.lanes:
            if ln.kind == "lane" and ln.segment_id:
                self.lanes[ln.segment_id].append(ln)
        self.cross_on: dict[str, list] = defaultdict(list)
        for c in m.crosswalks:
            self.cross_on[c.segment_id].append(c)
        self.walks_on: dict[str, list] = defaultdict(list)
        for w in m.sidewalks:
            self.walks_on[w.segment_id].append(w)
        self.walkways_of: dict[str, list] = defaultdict(list)
        self.ramp_walks: dict[str, list] = defaultdict(list)
        for w in m.walkways:
            sw = w.attrs.get("sidewalk")
            if w.kind == "sidewalk" and sw:
                self.walkways_of[sw].append(w)
            if w.attrs.get("ramp"):
                self.ramp_walks[w.attrs["ramp"]].append(w)      # (M14: beside a deck's ramp)
        for v in self.ramp_walks.values():
            v.sort(key=lambda w: w.id)
        self.doors_on: dict[str, list] = defaultdict(list)
        for b in m.buildings:
            for e in b.entrances:
                if e.kind in ("garage", "loading", "gate") and e.segment_id:
                    self.doors_on[e.segment_id].append((b.id, e))
        for p in m.parking:
            for a in p.entrances:
                if a.kind in ("garage", "loading", "gate") and p.segment_id:
                    self.doors_on[p.segment_id].append((p.id, a))
        self.trees = _Grid([(p.position[0], p.position[1], p) for p in m.plants
                            if p.type == "plant.street_tree"], 32.0)
        self.lines = {t.id: t for t in m.transit_lines}
        self.waterway = {w.id: w for w in m.waterways}
        self.tunnel = {t.id: t for t in m.tunnels}
        self.megasite = {s.id: s for s in m.megasites}
        wet = [G.from_model_poly(w.polygon) for w in m.waterways]
        wet += [G.from_model_poly(r.polygon) for r in m.rivers]
        wet += [G.from_model_poly(c.polygon) for c in m.channels]
        wet += [G.from_model_poly(p) for sea in m.seas for p in sea.polygons]
        with G.canonical():
            self.wet = G.union(wet) if wet else None
        if self.wet is not None and not self.wet.is_empty:
            shapely.prepare(self.wet)
        else:
            self.wet = None
        self.keys, self.key_tile = _blockout_keys(m)
        # AG12: M16's beds (bridge piers stand on them; quay and canal walls reach them)
        self.beds = None
        if m.banks:
            from citygen import water as WA
            self.beds = WA.Beds(m)
            self.levels = WA.Levels(m)
        self.banks_of: dict[str, list] = defaultdict(list)
        for k in m.banks:
            self.banks_of[k.water_id].append(k)

    # -- helpers ---------------------------------------------------------------------------

    def bed_z(self, x: float, y: float) -> float | None:
        """M16's bed under a point of the water (absolute), None over land or without M16."""
        if self.beds is None:
            return None
        wid = self.beds.body_at(x, y)
        if wid is None:
            return None
        return C.m(self.levels.at(wid, x, y) - self.beds.depth(wid, x, y))

    def wet_at(self, x: float, y: float) -> bool:
        return bool(shapely.contains_xy(self.wet, x, y)) if self.wet is not None else False

    def archetype(self, did: str | None) -> str | None:
        d = self.dist.get(did) if did else None
        return d.archetype if d else None

    def district_of_point(self, x: float, y: float) -> str | None:
        for d in self.m.districts:
            if _inside(d.polygon.exterior, x, y):
                return d.id
        return None

    def style(self, did: str | None) -> dict:
        """The district values a street piece uses: archetype, era, grime, wealth, and the
        asset spec's district section (wear) when it has one."""
        d = self.dist.get(did) if did else None
        if d is None:
            return {"archetype": None, "era": MT.era_of(None), "grime": 0.4, "wealth": 0.5,
                    "wear": 1.0}
        p = d.params or {}
        wear = 1.0
        if self.spec is not None:
            sd = (getattr(self.spec, "districts", None) or {}).get(d.name)
            if sd is not None:
                w = getattr(sd, "wear", None) if not isinstance(sd, dict) else sd.get("wear")
                wear = float(w) if w is not None else 1.0
        return {"archetype": d.archetype, "era": MT.era_of(d.archetype),
                "grime": C.m2(float(p.get("grime", 0.4))),
                "wealth": C.m2(float(p.get("wealth", 0.5))), "wear": C.m2(wear)}

    def tile_for(self, eid: str, pts) -> str:
        """The tile of the blockout object a piece supersedes (so both live in the same
        tile), else of the middle of its points."""
        for k in self.keys.get(eid, ()):
            t = self.key_tile.get(k)
            if t:
                return t
        x, y = bbox_center(pts)
        return tile_of(x, y)


class _Grid:
    def __init__(self, items, cell: float):
        self.cell = cell
        self.b: dict = defaultdict(list)
        for x, y, v in items:
            self.b[(math.floor(x / cell), math.floor(y / cell))].append((x, y, v))

    def near(self, x0: float, y0: float, x1: float, y1: float) -> list:
        out = []
        c = self.cell
        for ix in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for iy in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for x, y, v in self.b.get((ix, iy), ()):
                    if x0 <= x <= x1 and y0 <= y <= y1:
                        out.append(v)
        out.sort(key=lambda v: v.id)
        return out


def _inside(ring, x: float, y: float) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i - 1]
        x1, y1 = ring[i]
        if (y0 > y) != (y1 > y):
            xs = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xs:
                inside = not inside
    return inside


def _blockout_keys(m: CityModel) -> tuple[dict[str, list[str]], dict[str, str]]:
    """citygen id -> the names of the blockout objects that draw it, and each name's tile."""
    from citygen import blockout as BO
    with G.canonical():
        P = BO._Plan(m)
        BO._streets(P)
        BO._open_space(P)
        BO._sites(P)
        BO._tunnels(P)
        if getattr(m, "decks", None):
            BO._decks(P)            # M14: slabs per tile, joined columns, stairs, elevators
        if getattr(m, "terrain", None) is not None and hasattr(BO, "_terrain"):
            BO._terrain(P)          # M13: the retaining walls (one object each since M15)
    keys: dict[str, list[str]] = defaultdict(list)
    tiles: dict[str, str] = {}
    for o in P.objects:
        props = o["props"]
        tiles[o["name"]] = o["tile"]
        ids = props.get("citygen_ids")
        if isinstance(ids, str):
            ids = ids.split(";") if ids else []
        for i in ids or ():
            keys[i].append(o["name"])
        if props.get("citygen_id"):
            keys[props["citygen_id"]].append(o["name"])
    return {k: sorted(set(v)) for k, v in keys.items()}, tiles
