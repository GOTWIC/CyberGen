"""What the ground stage reads from a city, per 256 m tile (a job holds every input of its
tile, so its hash is the tile's: a tile is made again only when something in it changes).

- **Pieces**: every M16 ground cover piece meeting the tile (its whole polygon; the tile
  clips it), with its kind, surface (`kinds.surface_of`: a paved piece by what it paves),
  maintenance, wear, shade, moisture, slope, desire lines and its district's flower palette
  (the district era's palette, `assetgen/presets.py`, pushed to petal colors).
- **Verges**: M6's median lawns (green areas `lawn` on a road's median), which the blockout
  draws flat over the road: where AG7 draws the median as a curbed island with a lawn top
  (`streets/roads.py`), grass only, at the top; on a highway (AG7: a barrier on the
  asphalt), a lawn strip with grass, clear of the barrier; where AG7 tops the island with
  concrete (industrial and aerospace eras), nothing. Heights from the road's surface (its
  grade line, z profile and AG7's `ROAD_DZ`).
- **Around them**: M14's decks (no grass under a slab), trees (ferns and shade under their
  crowns, clear of their trunks), the water near the tile (moisture), M16's shade raster
  (`citygen.cover.Raster`, 4 m), M13's ground grid under the tile, and the keep-outs the
  clearance check tests (M16's right of way and the buildings, solid site elements and
  structures, `citygen.cover.Ctx`), which the grass's footprints keep clear of whatever the
  pieces' topology.
- **Blockout keys**: the objects M15 imports for the cover (`<district>.cover_<kind>.<tile>`)
  and the median lawns (`<district>.lawn.<tile>`), from citygen's own blockout code.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString

from citygen import geom as G

from .. import canon as C
from . import clumps as CL
from . import kinds as K

TREE_SPECIES = ("plane", "maple", "ginkgo", "birch", "linden", "elm", "oak", "ficus", "pine",
                "fan_palm", "date_palm")
MOIST_REACH_M = 60.0
VERGE_TOP_M = 0.16             # AG7's lawn island top over the road surface
VERGE_STRIP_M = 0.03           # a highway verge's lawn strip over the asphalt
BARRIER_CLEAR_M = 0.45         # a highway verge's grass clear of the median barrier


def tile_key(x: float, y: float) -> tuple[int, int]:
    return math.floor(x / K.TILE_M), math.floor(y / K.TILE_M)


def tile_name(ix: int, iy: int) -> str:
    return f"t{ix:+03d}{iy:+03d}"


def tile_box(t: str) -> tuple[float, float, float, float]:
    ix, iy = int(t[1:4]), int(t[4:7])
    return (ix * K.TILE_M, iy * K.TILE_M, (ix + 1) * K.TILE_M, (iy + 1) * K.TILE_M)


def _tiles_of(bounds, pad: float = 0.0) -> list[str]:
    x0, y0, x1, y1 = bounds
    a, b = tile_key(x0 - pad, y0 - pad)
    c, d = tile_key(x1 + pad, y1 + pad)
    return [tile_name(i, j) for i in range(a, c + 1) for j in range(b, d + 1)]


def _rings(poly) -> list[list[list[float]]]:
    """A model polygon as rings of [x, y] (meters, as the model holds them)."""
    return [[[float(p[0]), float(p[1])] for p in poly.exterior]] + \
        [[[float(p[0]), float(p[1])] for p in h] for h in poly.holes]


def _box_rings(poly, box) -> list[list[list[list[float]]]]:
    """A shapely geometry clipped to a box, as polygons of rings (1 cm grid)."""
    g = G.inter(G.qpoly(poly), shapely.box(*box))
    out = []
    for p in G.parts(g):
        out.append([[[G.q(x), G.q(y)] for x, y in list(r.coords)[:-1]]
                    for r in [p.exterior, *p.interiors]])
    return out


@dataclass
class Gathered:
    tiles: dict[str, dict] = field(default_factory=dict)        # tile -> job inputs
    keys: dict[str, dict] = field(default_factory=dict)         # blockout key -> its record
    families: list[tuple[str, str | None]] = field(default_factory=list)
    palettes: dict[str, list[str]] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


def _palette(m, spec_doc: dict | None) -> dict[str | None, str]:
    """district id -> its flower palette key (petal colors from its era's palette)."""
    from ..presets import ERA_PRESETS
    from ..streets import materials as SM
    out: dict[str | None, str] = {}
    for d in m.districts:
        era = SM.era_of(d.archetype)
        pal = (ERA_PRESETS.get(era) or {}).get("palette")
        sd = ((spec_doc or {}).get("districts") or {}).get(d.name) or {}
        if sd.get("palette"):
            pal = list(sd["palette"]) + list(pal or [])
        out[d.id] = CL.palette_key(K.flower_colors(pal))
    out[None] = CL.palette_key(list(K.FLOWER_FALLBACK))
    return out


def _sources(m) -> dict[str, tuple[str, str | None]]:
    out: dict[str, tuple[str, str | None]] = {}
    for o in m.open_spaces:
        out[o.id] = ("open", o.kind)
    for lt in m.lots:
        out[lt.id] = ("lot", None)
    for s in m.megasites:
        out[s.id] = ("site", s.kind)
    for e in m.site_elements:
        out[e.id] = ("element", e.kind)
    return out


def blockout_keys(m) -> dict[str, dict]:
    """The blockout objects AG13 replaces: name -> {tile, ids, category}."""
    from citygen import blockout as BO
    with G.canonical():
        P = BO._Plan(m)
        BO._cover(P)
        BO._dressing(P)
    out = {}
    for o in P.objects:
        cat = o["category"]
        if not (cat.startswith("cover_") or cat == "lawn"):
            continue
        ids = o["props"].get("citygen_ids")
        if isinstance(ids, str):
            ids = ids.split(";") if ids else []
        out[o["name"]] = {"tile": o["tile"], "ids": sorted(ids or []), "category": cat}
    return out


def _verges(m, spec_doc) -> list[dict]:
    """M6's median lawns: how AG7 draws their median, and their surface along the road."""
    from ..streets import materials as SM
    from ..streets.ctx import Ground
    from ..streets.path import Path, Profile
    seg = {s.id: s for s in m.road_segments}
    dist = {d.id: d for d in m.districts}
    ground = Ground(m)
    out = []
    for g in m.green_areas:
        if g.kind != "lawn" or g.polygon is None:
            continue
        sid = (g.attrs or {}).get("median")
        s = seg.get(sid)
        if s is None:
            continue
        did = s.district_ids[0] if s.district_ids else None
        arch = dist[did].archetype if did in dist else None
        cls = s.road_class
        if cls == "highway":
            mode, lift = "strip", VERGE_STRIP_M
        elif s.cross_section.median_m >= 2.0 and \
                SM.era_of(arch) not in ("industrial", "aerospace"):
            mode, lift = "island", VERGE_TOP_M
        else:
            mode, lift = "drop", 0.0
        path = Path(s.centerline)
        zp = Profile.of(s.z_profile)
        pts = [s_ for s_, _ in path.stations(0.0, path.L, 8.0, [])]
        xy = [path.point(t) for t in pts]
        gr = ground.along_road(s, xy) or [0.0] * len(xy)
        zline = [[G.q(x), G.q(y), C.m(gz + zp(t) + 0.05 + lift)]
                 for (x, y), t, gz in zip(xy, pts, gr)]
        out.append({"id": g.id, "segment": s.id, "district": did, "mode": mode,
                    "rings": _rings(g.polygon), "zline": zline,
                    "bounds": list(G.from_model_poly(g.polygon).bounds)})
    return out


def gather(m, spec_doc: dict | None = None) -> Gathered:
    from citygen import cover as CV
    from citygen import water as WA
    from ..streets.ctx import Ground
    out = Gathered()
    pal = _palette(m, spec_doc)
    src = _sources(m)
    per_tile: dict[str, dict] = defaultdict(lambda: {"pieces": [], "verges": []})
    used_pal: set[str] = set()
    n_grassy = 0
    for g in m.ground_cover:
        what, sk = src.get(g.source_id, ("rest", None)) if g.source_id else ("rest", None)
        sf = K.surface_of(g.kind, what, sk)
        p = G.from_model_poly(g.polygon)
        rec = {"id": g.id, "kind": g.kind, "surface": sf, "district": g.district_id,
               "rings": _rings(g.polygon), "area": g.area_m2,
               "maint": g.maintenance, "wear": g.wear, "shade": g.shade,
               "moist": g.moisture, "slope": g.slope_deg,
               "desire": [[[[G.q(x), G.q(y)] for x, y in d.line], d.width_m, d.wear]
                          for d in g.desire_lines],
               "palette": pal.get(g.district_id, pal[None])}
        if g.kind in K.GRASSY:
            n_grassy += 1
            used_pal.add(rec["palette"])
        for t in _tiles_of(p.bounds):
            x0, y0, x1, y1 = tile_box(t)
            if shapely.intersects(p, shapely.box(x0, y0, x1, y1)):
                per_tile[t]["pieces"].append(rec)
    for v in _verges(m, spec_doc):
        if v["mode"] == "drop":
            continue
        v["palette"] = pal.get(v["district"], pal[None])
        used_pal.add(v["palette"])
        bounds = v.pop("bounds")
        for t in _tiles_of(bounds):
            per_tile[t]["verges"].append(v)
    if not per_tile:
        out.keys = blockout_keys(m)
        out.stats = {"pieces": 0, "tiles": 0}
        return out
    # what stands around the pieces
    decks = [(d.id, G.from_model_poly(d.polygon)) for d in getattr(m, "decks", []) or []]
    trees = [(p.id, float(p.position[0]), float(p.position[1]), float(p.crown_radius_m))
             for p in m.plants if p.type.split(".", 1)[-1] in TREE_SPECIES and
             not getattr(p, "level", 0) and float(p.position[2]) < 1.0]
    tgrid: dict[tuple[int, int], list] = defaultdict(list)
    for tr in trees:
        tgrid[tile_key(tr[1], tr[2])].append(tr)
    wet = [b.poly for b in WA.bodies(m)]
    wtree = shapely.STRtree(wet) if wet else None
    with G.canonical():
        cvx = CV.Ctx(m)             # (M16's right of way and what stands on the ground)
    raster = CV.Raster(m)
    shade_u8 = np.floor(np.clip(raster.shade, 0.0, 1.0) * 255.0 + 0.5).astype(np.int64)
    ground = Ground(m)
    for t in sorted(per_tile):
        x0, y0, x1, y1 = tile_box(t)
        job = per_tile[t]
        job["pieces"].sort(key=lambda r: r["id"])
        job["verges"].sort(key=lambda r: r["id"])
        job["tile"] = t
        job["box"] = [x0, y0, x1, y1]
        bx = shapely.box(x0 - 2.0, y0 - 2.0, x1 + 2.0, y1 + 2.0)
        job["decks"] = [r for did, dp in decks if shapely.intersects(dp, bx)
                        for r in _box_rings(dp, bx.bounds)]
        ix, iy = tile_key(x0 + 1.0, y0 + 1.0)
        near = []
        for a in (ix - 1, ix, ix + 1):
            for b in (iy - 1, iy, iy + 1):
                for tid, x, y, r in tgrid.get((a, b), ()):
                    if x0 - r <= x <= x1 + r and y0 - r <= y <= y1 + r:
                        near.append([tid, G.q(x), G.q(y), G.q(r)])
        job["trees"] = sorted(near)
        wb = (x0 - MOIST_REACH_M, y0 - MOIST_REACH_M, x1 + MOIST_REACH_M, y1 + MOIST_REACH_M)
        wbox = shapely.box(*wb)
        water = []
        if wtree is not None:
            for k in sorted(int(i) for i in wtree.query(wbox, predicate="intersects")):
                water += _box_rings(wet[k], wb)
        job["water"] = water
        # the keep-outs the clearance check tests (`checks._clear`): the roads' right of way,
        # the buildings, solid site elements and structures, near the tile
        kb = (x0 - 2.0, y0 - 2.0, x1 + 2.0, y1 + 2.0)
        job["keep_out"] = {
            name: [r for k in (sorted(int(i) for i in tree.query(shapely.box(*kb),
                                                                 predicate="intersects"))
                               if tree is not None else [])
                   for r in _box_rings(geoms[k], kb)]
            for name, tree, geoms in (("row", cvx.rtree, cvx.row),
                                      ("hard", cvx.htree, cvx.hard))}
        # M16's shade raster over the tile and a cell round it (4 m cells)
        c = raster.c
        i0 = max(0, int(math.floor((x0 - raster.x0) / c)) - 1)
        j0 = max(0, int(math.floor((y0 - raster.y0) / c)) - 1)
        i1 = min(raster.nx, int(math.ceil((x1 - raster.x0) / c)) + 1)
        j1 = min(raster.ny, int(math.ceil((y1 - raster.y0) / c)) + 1)
        job["shade"] = {"x0": C.m(raster.x0 + i0 * c), "y0": C.m(raster.y0 + j0 * c),
                        "cell": c, "rows": shade_u8[j0:j1, i0:i1].tolist()}
        if ground.flat:
            job["ground"] = None
        else:
            gc = ground.cell
            gi0 = max(0, int(math.floor((x0 - ground.x0) / gc)) - 1)
            gj0 = max(0, int(math.floor((y0 - ground.y0) / gc)) - 1)
            gi1 = min(ground.nx - 1, int(math.ceil((x1 - ground.x0) / gc)) + 1)
            gj1 = min(ground.ny - 1, int(math.ceil((y1 - ground.y0) / gc)) + 1)
            rows = [[int(round(float(v) * 1000.0)) for v in ground.arr[j, gi0:gi1 + 1]]
                    for j in range(gj0, gj1 + 1)]
            job["ground"] = {"x0": C.m(ground.x0 + gi0 * gc), "y0": C.m(ground.y0 + gj0 * gc),
                             "cell": gc, "rows_mm": rows}
        out.tiles[t] = job
    out.keys = blockout_keys(m)
    for k in sorted(K.CLUMPS):
        if k != "flowers":
            out.families.append((k, None))
    for pk in sorted(used_pal):
        out.families.append(("flowers", pk))
        out.palettes[pk] = ["#" + h for h in pk.split("_")]
    out.stats = {"pieces": len(m.ground_cover), "grassy_pieces": n_grassy,
                 "verges": sum(1 for g in m.green_areas if g.kind == "lawn"),
                 "tiles": len(out.tiles), "trees": len(trees), "decks": len(decks)}
    return out
