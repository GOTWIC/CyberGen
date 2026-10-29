"""M4 blockout plan: the city model as Blender-ready objects (scope sections 7 and 8).

`make_plan(model)` turns a `CityModel` into plain data that `citygen/blender/build.py` (run by
Blender, stdlib and bpy only) turns into meshes. Everything that decides geometry happens here,
in the canonical geometry of the generator, so the plan is the same bytes on every machine
and its sha256 sits next to the model's in `tests/data/golden_hashes.json`; Blender only
triangulates and draws.

Objects:
- one object per building (its masses and roof items), per skybridge, per bridge and per
  megasite element group;
- ground surfaces joined per district, category and 256 m tile (roads by class, junctions,
  crosswalks, sidewalks, open space, green roofs, quays);
- land and water clipped to the tiles.

Every object names its tile, so per-tile exports (glTF for World Partition style streaming)
are a selection. Parts are prisms (ring, holes, z0, z1, shape), flats (ring, holes, z),
ribbons (left and right edge, z per vertex, thickness), boxes (base center, size, yaw) and
beams (two end points, width, height). Coordinates: meters, x east, y north, z up.
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import shapely
import shapely.ops
from shapely.geometry import LineString, Point, Polygon, box

from . import dmath as M
from . import geom as G
from .model import CityModel
from .preview import OPEN_COLORS
from .preview_massing import ELEMENT_COLORS, FLAT_COLORS, ROAD, SKYBRIDGE
from .schematic import ARCHETYPE_COLORS, LAND, RIVER, SEA

PLAN_VERSION = 1
TILE_M = 256.0

# levels (m): water below the ground, the ground slab, surfaces just above it
Z_SEA = -1.2
Z_WATER = -0.9
Z_BASE = -4.0          # bottom of the ground slab (quay and canal walls show to here)
Z_ROAD = 0.05
Z_JUNCTION = 0.06
Z_CROSSWALK = 0.07
Z_OPEN = 0.1
CURB_M = 0.15
DECK_M = 1.2           # bridge and elevated deck thickness
EMBANKMENT_M = 3.0     # a raised street no higher than this is drawn as a solid embankment
PIER_STEP_M = 40.0

ROAD_COLORS = {"highway": "#2c3038", "avenue": "#353a44", "street": "#3b404b",
               "alley": "#43474f", "service": "#43474f", "pedestrian": "#7d786a",
               "footbridge": "#8a6a4a"}
MATERIALS = {
    "sea": SEA, "water": RIVER, "ground": LAND, "lot": "#2c3140",
    "junction": ROAD, "crosswalk": "#c9ccd2", "sidewalk": "#8d929c", "quay": "#9a9384",
    "bridge_deck": "#5e636e", "pier": "#6c717c", "embankment": "#6a6f79",
    "road_support": "#767b86", "landmark": "#eef0f4",
    "bld_accent": "#c8ccd6", "bld_deck": "#7a7f8a", "roof_item": "#8f949e",
    "skybridge": SKYBRIDGE, "green_roof": "#4f8a55", "canopy": "#9fb0c4",
    "site_default": "#b0b6c0", "rail": "#8a7a6a",
    "transit_deck": "#a4abb8", "transit_tube": "#bfe3f2", "transit_support": "#6f7480",
    "prop_metal": "#5d636e", "prop_light": "#ffe9a0", "prop_signal": "#d0453a",
    "prop_glass": "#8fd3ff", "prop_wood": "#a77b52", "prop_neon": "#ff4fd8",
    "prop_awning": "#e8a23a", "prop_car": "#c8ccd4", "prop_dumpster": "#3f7a4a",
    "prop_trash": "#6b6455", "prop_boat": "#eeeeee", "prop_concrete": "#9a9fa8",
    "prop_scaffold": "#d9b25a", "prop_kiosk": "#3a4150", "plant_trunk": "#6b4f3a",
    "plant_crown": "#3f8a47", "plant_conifer": "#2f6e45", "plant_palm": "#7fae45",
    "plant_shrub": "#5aa060", "plant_scrub": "#7a8a4a", "plant_ivy": "#5fae55",
    "hedge": "#2f6e45", "lawn": "#4f8a57",
    "plinth": "#5d5a55", "retaining_wall": "#8a8478",
    "tunnel_wall": "#9a9ea8", "tunnel_lid": "#b7a98f", "tunnel_metro": "#4a78d6",
    "tunnel_ped": "#7ee0c3", "tunnel_vent": "#c4c8d2", "soil": "#6b5a45",
    "deck_slab": "#8c9099", "deck_rail": "#c9ccd2", "deck_column": "#6f737d",
    "deck_stair": "#b0b4bc", "deck_elevator": "#8fd3ff", "bld_undercity": "#c2334d",
}
MATERIALS.update({f"road_{k}": v for k, v in ROAD_COLORS.items()})
MATERIALS.update({f"open_{k}": v for k, v in OPEN_COLORS.items()})
MATERIALS.update({f"bld_{k}": v for k, v in ARCHETYPE_COLORS.items()})
MATERIALS.update({f"site_{k}": v for k, v in {**ELEMENT_COLORS, **FLAT_COLORS}.items()})

ACCENT_ROLES = {"crown", "spire", "mechanical"}
DECK_ROLES = {"deck", "span"}
SKYBRIDGE_H = {"enclosed": None, "stack": None, "open_deck": 0.6, "catwalk": 0.4, "cable": 0.3}

# camera directions (unit vectors, plain constants): the isometric views look north, 20
# degrees east, 35 degrees down, like preview_massing.png
ISO_DIR = (0.280167, 0.769751, -0.573576)


def q(v: float) -> float:
    return round(float(v), 2)


def tile_key(x: float, y: float) -> tuple[int, int]:
    return math.floor(x / TILE_M), math.floor(y / TILE_M)


def tile_name(ix: int, iy: int) -> str:
    return f"t{ix:+03d}{iy:+03d}"


def _ring(coords) -> list[list[float]]:
    pts = [[q(x), q(y)] for x, y in coords]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def _poly_rings(p) -> tuple[list, list]:
    """(exterior, holes) of a model polygon, exterior counterclockwise, holes clockwise."""
    ext = _ring(p.exterior)
    holes = [_ring(h) for h in p.holes]
    if _signed_area(ext) < 0:
        ext.reverse()
    holes = [h[::-1] if _signed_area(h) > 0 else h for h in holes]
    return ext, holes


def _shapely_rings(poly) -> tuple[list, list]:
    poly = shapely.geometry.polygon.orient(poly, 1.0)
    return (_ring(poly.exterior.coords), [_ring(r.coords) for r in poly.interiors])


def _signed_area(ring) -> float:
    s = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _bbox(pts) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _center(pts) -> tuple[float, float]:
    x0, y0, x1, y1 = _bbox(pts)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def _dist(a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def _dedupe(pts) -> list:
    out = []
    for p in pts:
        if not out or _dist(out[-1], p) > 0.005:
            out.append(p)
    return out


def _z_along(pts, profile) -> list[float]:
    """z at each vertex of a polyline from (s, z) samples (linear between samples)."""
    if not profile:
        return [0.0] * len(pts)
    ss = [0.0]
    for a, b in zip(pts, pts[1:]):
        ss.append(ss[-1] + _dist(a, b))
    samples = [(z.s, z.z) for z in profile]
    out = []
    for s in ss:
        z = samples[-1][1]
        if s <= samples[0][0]:
            z = samples[0][1]
        else:
            for (s0, z0), (s1, z1) in zip(samples, samples[1:]):
                if s0 <= s <= s1:
                    z = z0 if s1 - s0 <= 1e-9 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
                    break
        out.append(z)
    return out


def ribbon(pts, width: float, zs=None, z: float = 0.0) -> tuple[list, list] | None:
    """Left and right edges of a strip `width` wide along a polyline (mitered joints, the
    miter capped at twice the half width), z per vertex. None for a degenerate line."""
    pts = _dedupe([(float(x), float(y)) for x, y in pts])
    if len(pts) < 2:
        return None
    if zs is None or len(zs) != len(pts):
        zs = [z] * len(pts)
    dirs = []
    for a, b in zip(pts, pts[1:]):
        L = _dist(a, b)
        dirs.append(((b[0] - a[0]) / L, (b[1] - a[1]) / L))
    h = width / 2.0
    left, right = [], []
    for i, p in enumerate(pts):
        d0 = dirs[max(i - 1, 0)]
        d1 = dirs[min(i, len(dirs) - 1)]
        nx, ny = -d0[1] - d1[1], d0[0] + d1[0]
        n = math.sqrt(nx * nx + ny * ny)
        if n < 1e-9:  # a U-turn: use the outgoing normal
            nx, ny, n = -d1[1], d1[0], 1.0
        nx, ny = nx / n, ny / n
        k = h / max(nx * -d1[1] + ny * d1[0], 0.5)
        left.append([q(p[0] + nx * k), q(p[1] + ny * k), q(zs[i])])
        right.append([q(p[0] - nx * k), q(p[1] - ny * k), q(zs[i])])
    return left, right


class _Plan:
    def __init__(self, m: CityModel):
        self.m = m
        self.objects: list[dict] = []
        self.joined: dict[tuple, dict] = {}
        self.tiles: set[tuple[int, int]] = set()
        self.dname = {d.id: d.name for d in m.districts}
        self.darch = {d.id: d.archetype for d in m.districts}
        dpolys = [(d.id, G.from_model_poly(d.polygon)) for d in m.districts]
        for _, p in dpolys:
            shapely.prepare(p)
        self.dpolys = dpolys
        self.city = m.name
        wet = [G.from_model_poly(w.polygon) for w in m.waterways]
        wet += [G.from_model_poly(r.polygon) for r in m.rivers]
        wet += [G.from_model_poly(c.polygon) for c in m.channels]
        wet += [G.from_model_poly(p) for sea in m.seas for p in sea.polygons]
        self.wet = G.union(wet) if wet else Polygon()
        shapely.prepare(self.wet)

    def wet_at(self, x: float, y: float) -> bool:
        """Over the water (bridge piers stand there; road columns over land)."""
        return bool(shapely.contains_xy(self.wet, x, y)) if not self.wet.is_empty else False

    # -- placement helpers ----------------------------------------------------------------

    def district_at(self, x: float, y: float) -> str | None:
        pt = Point(x, y)
        for did, p in self.dpolys:
            if p.covers(pt):
                return did
        return None

    def collection(self, did: str | None, category: str) -> list[str]:
        group = self.dname.get(did, "City") if did else "City"
        return [self.city, group, category]

    def add(self, name: str, collection: list[str], tile: tuple[int, int], category: str,
            parts: list[dict], props: dict) -> dict:
        self.tiles.add(tile)
        obj = {"name": name, "collection": collection, "tile": tile_name(*tile),
               "category": category, "parts": parts, "props": props}
        self.objects.append(obj)
        return obj

    def join(self, did: str | None, category: str, x: float, y: float, part: dict,
             eid: str) -> None:
        """Add a part to the joined object of (district, category, tile)."""
        t = tile_key(x, y)
        key = (did or "city", category, t)
        obj = self.joined.get(key)
        if obj is None:
            obj = self.add(f"{did or 'city'}.{category}.{tile_name(*t)}",
                           self.collection(did, _group_of(category)), t, category, [],
                           {"citygen_type": f"joined.{category}", "citygen_ids": []})
            self.joined[key] = obj
        obj["parts"].append(part)
        obj["props"]["citygen_ids"].append(eid)


def _group_of(category: str) -> str:
    if category.startswith("deck_"):
        return "Decks"
    if category.startswith("road_") or category in ("junction", "crosswalk", "sidewalk"):
        return "Streets"
    if category.startswith("open_") or category == "green_roof":
        return "Open space"
    if category in ("quay", "bridge"):
        return "Waterfront"
    return category.capitalize()


# --- land and water ------------------------------------------------------------------------

def _land_and_water(P: _Plan) -> None:
    m = P.m
    land = G.union([G.from_model_poly(p) for lnd in m.land for p in lnd.polygons])
    wet = G.union([G.from_model_poly(w.polygon) for w in [*m.rivers, *m.channels,
                                                         *m.waterways]])
    ground = G.diff(land, wet) if not wet.is_empty else land
    # M9: the open approaches of the road tunnels and the underpass stair wells are holes
    holes = [G.from_model_poly(st.footprint) for st in m.structures
             if st.kind == "trench" and st.footprint is not None]
    if holes:
        ground = G.diff(ground, G.union(holes))
    x0, y0, x1, y1 = m.bounds
    ix0, iy0 = tile_key(x0, y0)
    ix1, iy1 = tile_key(x1 - 1e-6, y1 - 1e-6)
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            tb = box(max(ix * TILE_M, x0), max(iy * TILE_M, y0),
                     min((ix + 1) * TILE_M, x1), min((iy + 1) * TILE_M, y1))
            t = (ix, iy)
            sea_ring = _ring(tb.exterior.coords)
            if _signed_area(sea_ring) < 0:
                sea_ring.reverse()
            P.add(f"city.sea.{tile_name(*t)}", [P.city, "Water"], t, "sea",
                  [{"k": "flat", "m": "sea", "z": Z_SEA, "r": sea_ring, "h": []}],
                  {"citygen_type": "sea"})
            for cat, geom, part in (("ground", ground, "prism"), ("water", wet, "flat")):
                if geom.is_empty:
                    continue
                parts = []
                for p in G.parts(G.inter(geom, tb)):
                    ext, holes = _shapely_rings(p)
                    if len(ext) < 3:
                        continue
                    if part == "prism":
                        parts.append({"k": "prism", "m": "ground", "z0": Z_BASE, "z1": 0.0,
                                      "r": ext, "h": holes, "s": "prism"})
                    else:
                        parts.append({"k": "flat", "m": "water", "z": Z_WATER, "r": ext,
                                      "h": holes})
                if parts:
                    P.add(f"city.{cat}.{tile_name(*t)}",
                          [P.city, "Ground" if cat == "ground" else "Water"], t, cat, parts,
                          {"citygen_type": cat})


# --- streets -----------------------------------------------------------------------------

def _streets(P: _Plan) -> None:
    m = P.m
    seg_district = {}
    for s in m.road_segments:
        did = s.district_ids[0] if s.district_ids else None
        seg_district[s.id] = did
        pts = [(x, y) for x, y in s.centerline]
        zs = _z_along(_dedupe(pts), s.z_profile)
        raised = max(zs) > 0.5 if zs else False
        r = ribbon(pts, s.width_m, [z + Z_ROAD for z in zs])
        if r is None:
            continue
        mid = pts[len(pts) // 2]
        if "deck" in s.attrs:
            # M14: a deck's street on its slab; a ramp a solid ramp down to the ground
            if s.attrs.get("role") == "deck_ramp":
                P.add(f"{s.id}.ramp", P.collection(did, "Decks"), tile_key(*mid), "deck_ramp",
                      [{"k": "ribbon", "m": "embankment", "l": r[0], "rr": r[1],
                        "t": q(max(zs) + 0.3)},
                       {"k": "ribbon", "m": f"road_{s.road_class}", "l": r[0], "rr": r[1],
                        "t": 0.0}],
                      {"citygen_id": s.id, "citygen_type": s.type, "road_class": s.road_class,
                       "name": s.name or "", "level": s.level})
            else:
                P.join(did, "deck_road", mid[0], mid[1],
                       {"k": "ribbon", "m": f"road_{s.road_class}", "l": r[0], "rr": r[1],
                        "t": 0.0}, s.id)
            continue
        if s.tunnel:
            # M9: a road in a tunnel, its own object (the tunnel shell is in `_tunnels`)
            t = tile_key(*mid)
            P.add(f"{s.id}.tunnel_road", P.collection(did, "Tunnels"), t, "tunnel_road",
                  [{"k": "ribbon", "m": f"road_{s.road_class}", "l": r[0], "rr": r[1],
                    "t": 0.3}],
                  {"citygen_id": s.id, "citygen_type": s.type, "road_class": s.road_class,
                   "name": s.name or "", "level": s.level})
            continue
        if raised or s.bridge:
            # a deck with its own object: thickness, and piers down to the water (M7: the
            # columns over land are model structures); a low raised street (a ramp up to a
            # raised junction, an approach's foot) is a solid embankment
            elev = bool(s.attrs.get("elevated")) or s.attrs.get("role") == "ramp"
            low = not elev and not s.bridge and max(zs) <= EMBANKMENT_M
            cat = "elevated" if elev else ("embankment" if low else "bridge")
            t_deck = q(max(zs) + 0.3) if low else DECK_M
            part = {"k": "ribbon", "m": "embankment" if low else "bridge_deck", "l": r[0],
                    "rr": r[1], "t": t_deck}
            road = {"k": "ribbon", "m": f"road_{s.road_class}", "l": r[0], "rr": r[1],
                    "t": 0.0}
            t = tile_key(*mid)
            parts = [part, road] + ([] if low else _piers(_dedupe(pts), zs, P.wet_at))
            P.add(f"{s.id}.deck", P.collection(did, "Elevated" if elev else "Waterfront"), t,
                  cat, parts,
                  {"citygen_id": s.id, "citygen_type": s.type, "road_class": s.road_class,
                   "name": s.name or "", "clearance_m": s.clearance_m or 0.0,
                   "level": s.level})
            continue
        P.join(did, f"road_{s.road_class}", mid[0], mid[1],
               {"k": "ribbon", "m": f"road_{s.road_class}", "l": r[0], "rr": r[1], "t": 0.0},
               s.id)
    nz = {n.id: n.position[2] for n in m.road_nodes}
    for j in m.junctions:
        ext, holes = _poly_rings(j.polygon)
        cx, cy = _center(ext)
        # (M7: a junction on a viaduct or an approach sits at its node's height)
        P.join(P.district_at(cx, cy), "deck_junction" if j.level else "junction", cx, cy,
               {"k": "flat", "m": "junction", "z": q(Z_JUNCTION + nz.get(j.node_id, 0.0)),
                "r": ext, "h": holes}, j.id)
    # (M14: a deck's crosswalks and sidewalks at its top)
    jtop = {j.id: nz.get(j.node_id, 0.0) for j in m.junctions if j.level}
    stop = {s.id: s.z_profile[0].z for s in m.road_segments if "deck" in s.attrs}
    for c in m.crosswalks:
        r = ribbon(c.line, c.width_m, z=q(Z_CROSSWALK + jtop.get(c.junction_id, 0.0)))
        if r is None:
            continue
        cx, cy = _center(c.line)
        P.join(P.district_at(cx, cy), "deck_crosswalk" if c.level else "crosswalk", cx, cy,
               {"k": "ribbon", "m": "crosswalk", "l": r[0], "rr": r[1], "t": 0.0}, c.id)
    for w in m.sidewalks:
        r = ribbon(w.line, w.width_m, z=q(CURB_M + stop.get(w.segment_id, 0.0)))
        if r is None:
            continue
        cx, cy = _center(w.line)
        P.join(seg_district.get(w.segment_id), "deck_sidewalk" if w.level else "sidewalk",
               cx, cy,
               {"k": "ribbon", "m": "sidewalk", "l": r[0], "rr": r[1], "t": CURB_M}, w.id)


def _piers(pts, zs, wet_at=None) -> list[dict]:
    """Square piers every PIER_STEP_M under a raised deck over the water (from below the
    water line); over land the road columns of the model carry it (M7)."""
    out = []
    acc, nxt = 0.0, PIER_STEP_M / 2.0
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        L = _dist(a, b)
        while L > 0 and acc + L >= nxt:
            f = (nxt - acc) / L
            z = zs[i] + (zs[i + 1] - zs[i]) * f
            x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            if z > DECK_M + 1.0 and (wet_at is None or wet_at(x, y)):
                out.append({"k": "box", "m": "pier", "c": [q(x), q(y), Z_SEA],
                            "d": [2.0, 2.0, q(z - DECK_M - Z_SEA)], "yaw": 0.0})
            nxt += PIER_STEP_M
        acc += L
    return out


# --- open space, quays ------------------------------------------------------------------------

def _open_space(P: _Plan) -> None:
    m = P.m
    for o in m.open_spaces:
        ext, holes = _poly_rings(o.polygon)
        cx, cy = _center(ext)
        did = o.district_id or P.district_at(cx, cy)
        P.join(did, f"open_{o.kind}", cx, cy,
               {"k": "flat", "m": f"open_{o.kind}" if f"open_{o.kind}" in MATERIALS
                else "open_park", "z": q(max(o.z_m, 0.0) + Z_OPEN), "r": ext, "h": holes},
               o.id)
    bdist = {b.id: b.district_id for b in m.buildings}
    for g in m.green_areas:
        if g.polygon is None:
            continue
        ext, holes = _poly_rings(g.polygon)
        cx, cy = _center(ext)
        P.join(bdist.get(g.building_id) or P.district_at(cx, cy), "green_roof", cx, cy,
               {"k": "flat", "m": "green_roof", "z": q(g.z_m + 0.05), "r": ext, "h": holes},
               g.id)
    wdist = {w.id: w.district_id for w in m.waterways}
    for qy in m.quays:
        r = ribbon(qy.line, qy.width_m, z=0.02)
        if r is None:
            continue
        cx, cy = _center(qy.line)
        P.join(wdist.get(qy.waterway_id), "quay", cx, cy,
               {"k": "ribbon", "m": "quay", "l": r[0], "rr": r[1], "t": 0.0}, qy.id)


# --- buildings ----------------------------------------------------------------------------

def _mass_part(ms, mat: str) -> dict:
    ext, holes = _poly_rings(ms.footprint)
    return {"k": "prism", "m": mat, "z0": q(ms.z0_m), "z1": q(ms.z1_m), "r": ext,
            "h": holes, "s": ms.shape}


def _buildings(P: _Plan) -> None:
    m = P.m
    for b in m.buildings:
        arch = P.darch.get(b.district_id, "")
        wall = "landmark" if b.landmark else (f"bld_{arch}" if f"bld_{arch}" in MATERIALS
                                              else "site_default")
        if b.attrs.get("deck_under"):
            wall = "bld_undercity"      # (M14: the low buildings under a deck)
        elif b.level and f"bld_{b.attrs.get('program')}" in MATERIALS:
            wall = f"bld_{b.attrs['program']}"   # (M14: on a deck, its own program's)
        parts = []
        for ms in b.masses:
            if ms.role == "void" or ms.z1_m <= ms.z0_m:
                continue
            mat = wall
            if ms.role in ACCENT_ROLES and not b.landmark:
                mat = "bld_accent"
            elif ms.role in DECK_ROLES:
                mat = "bld_deck"
            parts.append(_mass_part(ms, mat))
        for it in b.roof_items:
            x, y, z = it.position
            parts.append({"k": "box", "m": "roof_item", "c": [q(x), q(y), q(z)],
                          "d": [q(it.size[0]), q(it.size[1]), q(it.size[2])],
                          "yaw": q(it.yaw_deg)})
        if not parts:
            continue
        pts = [p for part in parts if part["k"] == "prism" for p in part["r"]]
        cx, cy = _center(pts) if pts else (0.0, 0.0)
        did = b.district_id or P.district_at(cx, cy)
        cat = "landmark" if b.landmark else "building"
        P.add(b.id, P.collection(did, "Landmarks" if b.landmark else "Buildings"),
              tile_key(cx, cy), cat, parts,
              {"citygen_id": b.id, "citygen_type": b.type, "use": b.use,
               "height_m": q(b.height_m), "floors": b.floors, "district": did or "",
               "archetype": arch, "name": b.name or "", "property_id": b.property_id or "",
               "lot_id": b.lot_id or "", "megasite_id": b.megasite_id or "",
               **({"level": b.level} if b.level else {})})   # (M14: on a deck)
    for s in m.skybridges:
        (ax, ay), (bx, by) = s.line[0], s.line[-1]
        hh = SKYBRIDGE_H.get(s.kind) or s.levels * s.level_height_m
        cx, cy = (ax + bx) / 2.0, (ay + by) / 2.0
        did = P.district_at(cx, cy)
        P.add(s.id, P.collection(did, "Skybridges"), tile_key(cx, cy), "skybridge",
              [{"k": "beam", "m": "skybridge", "a": [q(ax), q(ay), q(s.z_m)],
                "b": [q(bx), q(by), q(s.z_m)], "w": q(s.width_m), "h": q(hh)}],
              {"citygen_id": s.id, "citygen_type": s.type, "kind": s.kind,
               "z_m": q(s.z_m), "buildings": ",".join(s.building_ids)})


# --- megasites, structures --------------------------------------------------------------------

def _sites(P: _Plan) -> None:
    m = P.m
    sdist = {s.id: s.district_id for s in m.megasites}
    groups: dict[tuple, list] = {}
    for e in m.site_elements:
        mat = f"site_{e.kind}" if f"site_{e.kind}" in MATERIALS else "site_default"
        parts = [_mass_part(ms, mat) for ms in e.masses if ms.z1_m > ms.z0_m]
        if e.footprint is not None and not e.masses:
            ext, holes = _poly_rings(e.footprint)
            parts.append({"k": "flat", "m": mat, "z": q(e.z_m + 0.08), "r": ext, "h": holes})
        if len(e.line) >= 2:
            r = ribbon(e.line, 3.0, z=q(e.z_m + 0.1))
            if r is not None:
                parts.append({"k": "ribbon", "m": "rail" if e.kind == "rail_track" else mat,
                              "l": r[0], "rr": r[1], "t": 0.0})
        if not parts:
            continue
        pts = [p for part in parts for p in (part.get("r") or part.get("l") or [])]
        cx, cy = _center(pts)
        groups.setdefault((e.megasite_id or e.lot_id or "site", e.kind, tile_key(cx, cy)),
                          []).append((e, parts))
    for (owner, kind, t), items in sorted(groups.items()):
        did = sdist.get(owner) or P.district_at(*_center(
            [p for _, parts in items for part in parts for p in (part.get("r") or
                                                                  part.get("l"))]))
        P.add(f"{owner}.{kind}.{tile_name(*t)}", P.collection(did, "Megasites"), t,
              f"site_{kind}", [p for _, parts in items for p in parts],
              {"citygen_type": f"site_element.{kind}", "megasite_id": owner,
               "citygen_ids": [e.id for e, _ in items]})
    for s in m.structures:
        a = s.attrs or {}
        transit = bool(a.get("line_id") or a.get("station"))
        if s.z1_m <= 0.0:
            continue    # underground (metro concourses): not in the blockout
        if s.kind in ("trench", "portal"):
            continue    # M9: drawn with their tunnel (`_tunnels`)
        if s.kind == "retaining_wall":
            continue    # M13: drawn with the ground (`_terrain`)
        if a.get("deck"):
            continue    # M14: drawn with their deck (`_decks`)
        if s.kind == "vent":
            ext, holes = _poly_rings(s.footprint)
            cx, cy = _center(ext)
            P.add(s.id, P.collection(P.district_at(cx, cy), "Tunnels"), tile_key(cx, cy),
                  "tunnel_vent", [{"k": "prism", "m": "tunnel_vent", "z0": q(s.z0_m),
                                   "z1": q(s.z1_m), "r": ext, "h": holes, "s": "prism"}],
                  {"citygen_id": s.id, "citygen_type": s.type, "tunnel_id": a.get("tunnel", "")})
            continue
        parts = []
        if s.footprint is not None:
            mat = ("canopy" if s.kind == "canopy" else "transit_support"
                   if s.kind in ("column", "pylon") and transit else
                   "transit_deck" if transit else
                   "road_support" if a.get("road_id") else "bld_deck")
            ext, holes = _poly_rings(s.footprint)
            parts.append({"k": "prism", "m": mat, "z0": q(s.z0_m),
                          "z1": q(max(s.z1_m, s.z0_m + 0.3)), "r": ext, "h": holes,
                          "s": "prism"})
        elif len(s.line) >= 2:
            w = a.get("width_m", 4.0)
            t = a.get("deck_m", max(s.z1_m - s.z0_m, 0.5))
            mat = "transit_tube" if s.kind == "tube" else "transit_deck" if transit else \
                "bld_deck"
            r = ribbon([(p[0], p[1]) for p in s.line], w, [p[2] for p in s.line])
            if r is not None:
                parts.append({"k": "ribbon", "m": mat, "l": r[0], "rr": r[1], "t": q(t)})
        if not parts:
            continue
        pts = parts[0].get("r") or parts[0].get("l")
        cx, cy = _center(pts)
        P.add(s.id, P.collection(P.district_at(cx, cy), "Transit" if transit else
                                 "Elevated" if a.get("road_id") else "Structures"),
              tile_key(cx, cy), f"structure_{s.kind}", parts,
              {"citygen_id": s.id, "citygen_type": s.type, "line_id": a.get("line_id", ""),
               "station_id": a.get("station", "")})


# --- decks (M14) ---------------------------------------------------------------------------

RAIL_M = 1.1            # railing along a slab's edges and wells


def _decks(P: _Plan) -> None:
    """Every deck: its slab clipped to the tiles (one object per deck and tile) with a
    railing along its edges and wells, its columns joined per tile, a stair flight and an
    elevator shaft per link."""
    m = P.m
    for dk in m.decks:
        poly = G.from_model_poly(dk.polygon)
        z0, z1 = q(dk.top_m - dk.slab_m), q(dk.top_m)
        rail = G.qpoly(poly.boundary.buffer(0.12, cap_style="flat", join_style="mitre"))
        x0, y0, x1, y1 = poly.bounds
        ix0, iy0 = tile_key(x0, y0)
        ix1, iy1 = tile_key(x1, y1)
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                tb = box(ix * TILE_M, iy * TILE_M, (ix + 1) * TILE_M, (iy + 1) * TILE_M)
                parts = []
                for p in G.parts(G.inter(poly, tb)):
                    ext, holes = _shapely_rings(p)
                    if len(ext) >= 3:
                        parts.append({"k": "prism", "m": "deck_slab", "z0": z0, "z1": z1,
                                      "r": ext, "h": holes, "s": "prism"})
                for p in G.parts(G.inter(rail, tb)):
                    ext, holes = _shapely_rings(p)
                    if len(ext) >= 3:
                        parts.append({"k": "prism", "m": "deck_rail", "z0": z1,
                                      "z1": q(z1 + RAIL_M), "r": ext, "h": holes,
                                      "s": "prism"})
                if parts:
                    t = (ix, iy)
                    P.add(f"{dk.id}.slab.{tile_name(*t)}", P.collection(dk.district_id, "Decks"),
                          t, "deck_slab", parts,
                          {"citygen_id": dk.id, "citygen_type": dk.type or "deck",
                           "level": dk.level, "top_m": z1, "district": dk.district_id})
    for s in m.structures:
        a = s.attrs or {}
        if not a.get("deck"):
            continue
        if s.kind == "column":
            ext, holes = _poly_rings(s.footprint)
            cx, cy = _center(ext)
            P.join(P.district_at(cx, cy), "deck_column", cx, cy,
                   {"k": "prism", "m": "deck_column", "z0": q(s.z0_m), "z1": q(s.z1_m),
                    "r": ext, "h": holes, "s": "prism"}, s.id)
        elif s.kind == "stair" and len(s.line) >= 2:
            # (a flight per leg of its line: up, the landing, up again)
            parts = []
            for p0, p1 in zip(s.line, s.line[1:]):
                r = ribbon([p0[:2], p1[:2]], 2.4, [p0[2], p1[2]])
                if r is not None:
                    parts.append({"k": "ribbon", "m": "deck_stair", "l": r[0], "rr": r[1],
                                  "t": 0.4})
            if not parts:
                continue
            cx, cy = _center([p[:2] for p in s.line])
            P.add(s.id, P.collection(P.district_at(cx, cy), "Decks"), tile_key(cx, cy),
                  "deck_stair", parts,
                  {"citygen_id": s.id, "citygen_type": s.type, "deck": a["deck"]})
        elif s.kind == "elevator" and s.footprint is not None:
            ext, holes = _poly_rings(s.footprint)
            cx, cy = _center(ext)
            P.add(s.id, P.collection(P.district_at(cx, cy), "Decks"), tile_key(cx, cy),
                  "deck_elevator", [{"k": "prism", "m": "deck_elevator", "z0": q(s.z0_m),
                                     "z1": q(s.z1_m), "r": ext, "h": holes, "s": "prism"}],
                  {"citygen_id": s.id, "citygen_type": s.type, "deck": a["deck"]})


# --- props and plants (M6): one instancing object per kind and tile --------------------------

def _cyl(r: float, z0: float, z1: float, mat: str, shape: str = "prism", n: int = 8,
         cx: float = 0.0, cy: float = 0.0) -> dict:
    ring = [[q(cx + r * float(M.cos(2 * math.pi * k / n))),
             q(cy + r * float(M.sin(2 * math.pi * k / n)))] for k in range(n)]
    return {"k": "prism", "m": mat, "z0": q(z0), "z1": q(z1), "r": ring, "h": [], "s": shape}


def _bx(c, d, mat: str, yaw: float = 0.0) -> dict:
    return {"k": "box", "m": mat, "c": [q(v) for v in c], "d": [q(v) for v in d], "yaw": yaw}


def _tree_proto(crown_mat: str) -> list[dict]:
    return [_cyl(0.25, 0.0, 4.5, "plant_trunk", n=6), _cyl(3.0, 3.5, 6.5, crown_mat),
            _cyl(3.0, 6.5, 10.0, crown_mat, "dome")]


# Local frame: x along the thing's yaw, z up from its position; plants at a base size (crown
# radius, height) the instance scale stretches: trees 3 and 10 m, shrubs 1 and 1 m.
PROTOTYPES = {
    "street_light": [_bx((0, 0, 0), (0.25, 0.25, 8.0), "prop_metal"),
                     _bx((0.8, 0, 7.75), (1.6, 0.15, 0.15), "prop_metal"),
                     _bx((1.5, 0, 7.55), (0.7, 0.35, 0.2), "prop_light")],
    "wall_light": [_bx((0.15, 0, -0.1), (0.3, 0.12, 0.12), "prop_metal"),
                   _bx((0.35, 0, -0.35), (0.3, 0.3, 0.25), "prop_light")],
    "traffic_signal": [_bx((0, 0, 0), (0.2, 0.2, 5.5), "prop_metal"),
                       _bx((0.3, 0, 4.2), (0.35, 0.35, 1.1), "prop_signal")],
    "trash_can": [_cyl(0.3, 0.0, 0.9, "prop_metal")],
    "bus_stop": [_bx((0, 0, 2.5), (4.0, 1.6, 0.12), "prop_metal"),
                 _bx((0, 0.65, 0.1), (4.0, 0.08, 2.4), "prop_glass"),
                 _bx((-1.95, 0, 0), (0.1, 0.1, 2.5), "prop_metal"),
                 _bx((1.95, 0, 0), (0.1, 0.1, 2.5), "prop_metal"),
                 _bx((0, 0.35, 0), (3.0, 0.4, 0.45), "prop_wood")],
    "hydrant": [_cyl(0.18, 0.0, 0.65, "prop_signal"), _cyl(0.18, 0.65, 0.8, "prop_signal",
                                                           "dome")],
    "bollard": [_cyl(0.1, 0.0, 0.9, "prop_concrete", n=6)],
    "bench": [_bx((0, 0, 0.38), (1.8, 0.5, 0.08), "prop_wood"),
              _bx((-0.75, 0, 0), (0.08, 0.45, 0.38), "prop_metal"),
              _bx((0.75, 0, 0), (0.08, 0.45, 0.38), "prop_metal"),
              _bx((0, 0.22, 0.46), (1.8, 0.06, 0.45), "prop_wood")],
    "kiosk": [_bx((0, 0, 0), (2.2, 2.2, 2.6), "prop_kiosk"),
              _bx((0, 0, 2.6), (2.6, 2.6, 0.15), "prop_neon")],
    "vending_machine": [_bx((0, 0, 0), (1.0, 0.8, 1.9), "prop_neon")],
    "food_stall": [_bx((0, 0, 0), (3.0, 2.0, 1.0), "prop_wood"),
                   _bx((0, 0, 2.4), (3.4, 2.4, 0.1), "prop_awning"),
                   _bx((-1.5, -1.0, 0), (0.08, 0.08, 2.4), "prop_metal"),
                   _bx((1.5, -1.0, 0), (0.08, 0.08, 2.4), "prop_metal"),
                   _bx((-1.5, 1.0, 0), (0.08, 0.08, 2.4), "prop_metal"),
                   _bx((1.5, 1.0, 0), (0.08, 0.08, 2.4), "prop_metal")],
    "planter": [_bx((0, 0, 0), (1.2, 1.2, 0.6), "prop_concrete"),
                _cyl(0.5, 0.6, 1.1, "plant_shrub", "dome")],
    "parked_vehicle": [_bx((0, 0, 0.25), (4.6, 1.9, 0.75), "prop_car"),
                       _bx((-0.2, 0, 1.0), (2.4, 1.7, 0.55), "prop_glass")],
    "boat": [_bx((0, 0, -0.5), (8.0, 3.0, 1.3), "prop_boat"),
             _bx((-1.0, 0, 0.8), (3.0, 2.0, 1.1), "prop_boat")],
    "barrier": [_bx((0, 0, 0), (4.0, 0.6, 0.85), "prop_concrete")],
    "railing": [_bx((0, 0, 1.0), (3.0, 0.06, 0.06), "prop_metal"),
                _bx((-1.45, 0, 0), (0.06, 0.06, 1.05), "prop_metal")],
    "overhead_cable": [_bx((0, 0, 0), (1.0, 0.04, 0.04), "prop_metal")],
    "sign": [_bx((0, 0, 0), (0.2, 1.2, 1.8), "prop_neon")],
    "awning": [_bx((0, 0, 0), (1.0, 1.0, 0.15), "prop_awning")],
    "ac_unit": [_bx((0, 0, 0), (1.0, 0.6, 0.8), "prop_metal")],
    "scaffolding": [_bx((0, 0, 0), (1.0, 1.5, 1.0), "prop_scaffold")],
    "gate": [_bx((-0.45, 0, 0), (0.1, 1.0, 6.0), "prop_signal"),
             _bx((0.45, 0, 0), (0.1, 1.0, 6.0), "prop_signal"),
             _bx((0, 0, 5.0), (1.0, 1.2, 1.0), "prop_signal")],
    "dumpster": [_bx((0, 0, 0), (2.0, 1.2, 1.3), "prop_dumpster")],
    "trash": [_bx((0, 0, 0), (0.5, 0.5, 0.4), "prop_trash")],
    "street_tree": _tree_proto("plant_crown"), "median_tree": _tree_proto("plant_crown"),
    "park_tree": _tree_proto("plant_crown"), "roof_tree": _tree_proto("plant_crown"),
    "conifer": [_cyl(0.25, 0.0, 2.0, "plant_trunk", n=6),
                _cyl(3.0, 2.0, 10.0, "plant_conifer", "cone")],
    "palm": [_cyl(0.2, 0.0, 9.0, "plant_trunk", n=6),
             _cyl(3.0, 8.6, 10.0, "plant_palm", "dome")],
    "shrub": [_cyl(1.0, 0.0, 1.0, "plant_shrub", "dome")],
    "overgrowth": [_cyl(1.0, 0.0, 1.0, "plant_scrub", "dome", n=6)],
    "facade_greenery": [_bx((0, 0, 0), (1.0, 0.3, 2.0), "plant_ivy")],
}
PLANT_BASE = {"conifer": (3.0, 10.0), "palm": (3.0, 10.0), "shrub": (1.0, 1.0),
              "overgrowth": (1.0, 1.0)}


def _dressing(P: _Plan) -> None:
    m = P.m
    groups: dict = {}
    for p in m.props:
        kind = p.type.split(".", 1)[1]
        if kind not in PROTOTYPES:
            continue
        x, y, z = p.position
        groups.setdefault(("prop", kind, tile_key(x, y)), []).append(
            (p.id, [q(x), q(y), q(z), q(p.yaw_deg), q(p.scale[0]), q(p.scale[1]),
                    q(p.scale[2])]))
    for p in m.plants:
        kind = p.type.split(".", 1)[1]
        if kind not in PROTOTYPES:
            continue
        x, y, z = p.position
        a = p.attrs or {}
        if kind == "facade_greenery":
            pt = [q(x), q(y), q(z), q(a.get("yaw_deg", 0.0)), q(a.get("length_m", 1.0)), 1.0,
                  1.0]
        else:
            r0, h0 = PLANT_BASE.get(kind, (3.0, 10.0))
            k = p.crown_radius_m / r0
            yaw = q(360.0 * (int(hashlib.sha256(p.id.encode()).hexdigest()[:6], 16) % 3600)
                    / 3600.0)
            pt = [q(x), q(y), q(z), yaw, q(k), q(k), q(p.height_m / h0)]
        groups.setdefault(("plant", kind, tile_key(x, y)), []).append((p.id, pt))
    for (cls, kind, t), items in sorted(groups.items()):
        P.add(f"{cls}.{kind}.{tile_name(*t)}",
              [P.city, "Props" if cls == "prop" else "Vegetation", kind], t,
              f"{cls}_{kind}", [{"k": "inst", "proto": kind, "pts": [pt for _, pt in items]}],
              {"citygen_type": f"{cls}.{kind}", "count": len(items),
               "citygen_ids": ";".join(i for i, _ in items)})
    for g in m.green_areas:
        if g.kind == "lawn" and g.polygon is not None:
            ext, holes = _poly_rings(g.polygon)
            cx, cy = _center(ext)
            P.join(P.district_at(cx, cy), "lawn", cx, cy,
                   {"k": "flat", "m": "lawn", "z": q(g.z_m + 0.12), "r": ext, "h": holes}, g.id)
        elif g.kind == "hedge_line" and len(g.line) >= 2:
            r = ribbon(g.line, 1.0, z=q(g.z_m + (g.attrs or {}).get("height_m", 1.2)))
            if r is not None:
                cx, cy = _center(g.line)
                P.join(P.district_at(cx, cy), "hedge", cx, cy,
                       {"k": "ribbon", "m": "hedge", "l": r[0], "rr": r[1],
                        "t": q((g.attrs or {}).get("height_m", 1.2))}, g.id)


# --- cameras ----------------------------------------------------------------------------------

# --- tunnels (M9) -------------------------------------------------------------------------------

def _portal_s(pts, cum, t) -> tuple[float, float]:
    out = []
    for p in t.portals:
        best = None
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
            f = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((p.position[0] - a[0]) * (b[0] - a[0])
                                                       + (p.position[1] - a[1]) *
                                                       (b[1] - a[1])) / L2))
            x, y = a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
            d = _dist((x, y), p.position[:2])
            if best is None or d < best[0]:
                best = (d, cum[i] + f * (cum[i + 1] - cum[i]))
        out.append(best[1])
    out.sort()
    return (out[0], out[-1]) if out else (0.0, cum[-1])


def _tunnels(P: _Plan) -> None:
    """Road tunnels as open boxes (floor, walls, the roof over the covered stretch, a lintel
    over each portal; the walls of the open approaches up to a parapet), metro tunnels and
    pedestrian underpasses as solid boxes; one object each."""
    m = P.m
    for t in m.tunnels:
        pl: list = []
        for x, y, z in t.line:
            if not pl or _dist((x, y), pl[-1][:2]) > 0.01:
                pl.append((x, y, z))
        if len(pl) < 2:
            continue
        pts = [(x, y) for x, y, _ in pl]
        zs = [z for _, _, z in pl]
        cum = _cum2(pts)
        mid = pts[len(pts) // 2]
        did = P.district_at(*mid)
        parts = []
        if t.kind in ("metro", "pedestrian"):
            top = [z + t.clear_m + t.roof_m for z in zs]
            r = ribbon(pts, t.width_m, top)
            if r is not None:
                parts.append({"k": "ribbon", "m": "tunnel_metro" if t.kind == "metro" else
                              "tunnel_ped", "l": r[0], "rr": r[1],
                              "t": q(t.clear_m + t.roof_m + t.floor_m)})
        else:
            a, b = _portal_s(pts, cum, t)
            w = t.width_m
            fl = ribbon(pts, w, [z - 0.3 for z in zs])
            if fl is not None:
                parts.append({"k": "ribbon", "m": "tunnel_wall", "l": fl[0], "rr": fl[1],
                              "t": q(t.floor_m)})
            roof_z = [z + t.clear_m + t.roof_m for z in zs]
            tops = [rz if a - 0.01 <= s <= b + 0.01 else 1.0 for s, rz in zip(cum, roof_z)]
            outer = ribbon(pts, w, tops)
            inner = ribbon(pts, w - 2.0, tops)
            if outer is not None and inner is not None:
                # each wall one closed mesh: its top (roof top or parapet) and its foot (under
                # the floor) follow the road
                bots = [q(z - 0.3 - t.floor_m) for z in zs]
                for side in (0, 1):
                    vs, fs = [], []
                    for i in range(len(pts)):
                        o, n_ = outer[side][i], inner[side][i]
                        vs += [o, n_, [n_[0], n_[1], bots[i]], [o[0], o[1], bots[i]]]
                    for i in range(len(pts) - 1):
                        a0, b0 = 4 * i, 4 * (i + 1)
                        for k in range(4):
                            k1 = (k + 1) % 4
                            f = [a0 + k, b0 + k, b0 + k1, a0 + k1]
                            fs.append(f[::-1] if side == 0 else f)
                    e = 4 * (len(pts) - 1)
                    fs.append([0, 3, 2, 1] if side == 0 else [0, 1, 2, 3])
                    fs.append([e, e + 1, e + 2, e + 3] if side == 0 else [e, e + 3, e + 2, e + 1])
                    parts.append({"k": "mesh", "m": "tunnel_wall", "v": vs, "f": fs})
            cov = [(p, rz) for p, s, rz in zip(pts, cum, roof_z) if a - 0.01 <= s <= b + 0.01]
            if len(cov) >= 2:
                rr = ribbon([p for p, _ in cov], w, [z for _, z in cov])
                if rr is not None:
                    parts.append({"k": "ribbon", "m": "tunnel_wall", "l": rr[0], "rr": rr[1],
                                  "t": q(t.roof_m)})
            for p in t.portals:
                z_open = p.position[2] + t.clear_m
                h = M.radians(p.heading_deg)
                ux, uy = float(M.cos(h)), float(M.sin(h))
                c = [q(p.position[0] - ux * 0.75), q(p.position[1] - uy * 0.75), q(z_open)]
                parts.append({"k": "box", "m": "tunnel_wall", "c": c,
                              "d": [1.5, q(w + 1.0), q(1.0 - z_open)],
                              "yaw": q(p.heading_deg)})
        if not parts:
            continue
        P.add(f"{t.id}.tunnel", P.collection(did, "Tunnels"), tile_key(*mid), "tunnel",
              parts, {"citygen_id": t.id, "citygen_type": t.type, "kind": t.kind,
                      "name": t.name or ""})


def _cum2(pts) -> list[float]:
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + _dist(a, b))
    return out


def _cutaway(P: _Plan) -> dict | None:
    """M9: a section along the longest road tunnel (the city on the camera's side of its
    chord taken away, earth under the ground), seen from that side."""
    m = P.m
    road = [t for t in m.tunnels if t.kind in ("immersed_tube", "cut_and_cover")]
    if not road:
        return None
    t = max(road, key=lambda t: (t.attrs.get("length_m", 0.0), t.id))
    a, b = t.line[0], t.line[-1]
    L = _dist(a, b) or 1.0
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])
    # the camera on the side the isometric views look from (south): n points toward it
    if n[0] * ISO_DIR[0] + n[1] * ISO_DIR[1] > 0:
        n = (-n[0], -n[1])
    pts = [(p[0], p[1]) for p in t.line]
    cum = _cum2(pts)
    half = cum[-1] / 2.0
    mid = pts[0]
    for i in range(len(pts) - 1):
        if cum[i] <= half <= cum[i + 1]:
            f = (half - cum[i]) / max(cum[i + 1] - cum[i], 1e-9)
            mid = (pts[i][0] + f * (pts[i + 1][0] - pts[i][0]),
                   pts[i][1] + f * (pts[i + 1][1] - pts[i][1]))
    zmin = min(p[2] for p in t.line)
    half_len = L / 2.0 + 160.0
    # the tunnels' inner volumes (road to roof, wall to wall), opened in the ground and earth
    voids = []
    for o in m.tunnels:
        opts = [(p[0], p[1]) for p in o.line]
        near = [((x - mid[0]) * u[0] + (y - mid[1]) * u[1],
                 (x - mid[0]) * n[0] + (y - mid[1]) * n[1]) for x, y in opts]
        if not any(abs(a_) <= half_len and -60.0 <= b_ <= 900.0 for a_, b_ in near):
            continue
        r = ribbon(opts, max(o.width_m - 2.2, 1.0), [p[2] + o.clear_m - 0.05 for p in o.line])
        if r is not None:
            voids.append({"k": "ribbon", "m": "soil", "l": r[0], "rr": r[1],
                          "t": q(o.clear_m - 0.15)})
    # framed on the first portal: from over its open approach, down the ramp, through the
    # portal into the covered stretch
    a_s = min(_portal_s(pts, cum, t))

    def at(s_):
        s_ = min(max(s_, 0.0), cum[-1])
        for i in range(len(pts) - 1):
            if cum[i] <= s_ <= cum[i + 1]:
                f = (s_ - cum[i]) / max(cum[i + 1] - cum[i], 1e-9)
                return (pts[i][0] + f * (pts[i + 1][0] - pts[i][0]),
                        pts[i][1] + f * (pts[i + 1][1] - pts[i][1]))
        return pts[-1]
    ep, tp = at(a_s - 70.0), at(a_s + 25.0)
    return {"tunnel": t.id, "origin": [q(mid[0]), q(mid[1])], "u": [q(u[0]), q(u[1])],
            "n": [q(n[0]), q(n[1])], "half_len": q(half_len), "depth": 900.0,
            "z": [q(zmin - 40.0), 600.0], "voids": voids,
            "eye": [q(ep[0] + n[0] * 48.0), q(ep[1] + n[1] * 48.0), 7.0],
            "target": [q(tp[0]), q(tp[1]), -5.0], "lens_mm": 20}


def _cameras(P: _Plan) -> dict:
    m = P.m
    x0, y0, x1, y1 = m.bounds
    top = {"center": [q((x0 + x1) / 2), q((y0 + y1) / 2)], "size": [q(x1 - x0), q(y1 - y0)]}
    tall: dict[str, float] = {}
    for b in m.buildings:
        if b.district_id:
            tall[b.district_id] = max(tall.get(b.district_id, 0.0), b.height_m)
    districts = []
    for d in m.districts:
        ext, _ = _poly_rings(d.polygon)
        bx0, by0, bx1, by1 = _bbox(ext)
        districts.append({"id": d.id, "name": d.name, "archetype": d.archetype,
                          "box": [q(bx0), q(by0), 0.0, q(bx1), q(by1),
                                  q(tall.get(d.id, 30.0))]})
    out = {"top": top, "iso_dir": list(ISO_DIR), "districts": districts,
           "street": _street_views(P)}
    if m.terrain is not None:
        # M13: the boxes from the lowest to the highest ground, the views over the ground
        from . import terrain as TE

        fin = TE.ground_of(m)
        for d in districts:
            bx0, by0, _, bx1, by1, h = d["box"]
            js, iss = TE._window(fin, bx0, by0, bx1, by1)
            sub = fin.arr[js, iss]
            if sub.size:
                d["box"][2] = q(float(sub.min()))
                d["box"][5] = q(float(sub.max()) + h)
        for v in out["street"]:
            for key in ("eye", "target"):
                x, y, z = v[key]
                v[key] = [x, y, q(z + fin.at(x, y))]
    cut = _cutaway(P)
    if cut is not None:
        out["cutaway"] = cut
    dcut = _deck_cut(P)
    if dcut is not None:
        out["deck"] = dcut
    return out


def _deck_cut(P: _Plan) -> dict | None:
    """M14: a section across the biggest deck, square to its longest street through the
    street's middle (the city on the camera's side taken away), seen from that side a little
    over the deck: the ground street under the slab and the deck street over it."""
    m = P.m
    if not m.decks:
        return None
    dk = max(m.decks, key=lambda d: (d.area_m2, d.id))
    segs = {s.id: s for s in m.road_segments}
    streets = [segs[i] for i in dk.segment_ids if i in segs and
               segs[i].attrs.get("role") not in ("deck_ramp", "deck_end")]
    if not streets:
        return None
    s = max(streets, key=lambda s: (_plen(s.centerline), s.id))
    pts = [(x, y) for x, y in s.centerline]
    a, b = pts[0], pts[-1]
    L = _dist(a, b) or 1.0
    n = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)      # the cut plane is square to the street
    if n[0] * ISO_DIR[0] + n[1] * ISO_DIR[1] > 0:
        n = (-n[0], -n[1])
    u = (n[1], -n[0])
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    poly = G.from_model_poly(dk.polygon)
    span = max(abs((x - mid[0]) * u[0] + (y - mid[1]) * u[1])
               for x, y in poly.exterior.coords)
    top = dk.top_m
    return {"deck": dk.id, "origin": [q(mid[0]), q(mid[1])], "u": [q(u[0]), q(u[1])],
            "n": [q(n[0]), q(n[1])], "half_len": q(min(span + 80.0, 900.0)),
            "depth": 900.0, "z": [-60.0, 600.0], "voids": [],
            "eye": [q(mid[0] + n[0] * 95.0 + u[0] * 22.0),
                    q(mid[1] + n[1] * 95.0 + u[1] * 22.0), q(top + 3.0)],
            "target": [q(mid[0]), q(mid[1]), q(top * 0.7)],
            "lens_mm": 22}


def _street_views(P: _Plan, n: int = 4) -> list[dict]:
    """Eye-level views: from a ground road 150 to 450 m from each of the tallest buildings
    (one per district), looking at the tower, plus one along an old town or market street."""
    m = P.m
    roads = [s for s in m.road_segments if not s.bridge and s.road_class in
             ("avenue", "street", "pedestrian") and not any(z.z > 0.5 for z in s.z_profile)]
    seen, views = set(), []
    foot = []
    for b in m.buildings:
        if b.footprint is not None:
            foot.append((b, G.from_model_poly(b.footprint)))
    tree = shapely.STRtree([f for _, f in foot]) if foot else None
    for b in sorted(m.buildings, key=lambda b: (-b.height_m, b.id)):
        if len(views) >= n - 1 or b.height_m < 60:
            break
        if b.district_id in seen:
            continue
        pts = [p for ms in b.masses for p in ms.footprint.exterior]
        c = _center(pts)
        cands = []
        for s in roads:
            cl = _dedupe([(x, y) for x, y in s.centerline])
            for a, nb in zip(cl, cl[1:]):
                # looking down the road toward the tower: the road runs within 25 degrees
                # of the line of sight, either way
                d = _dist(c, a)
                if not 180.0 <= d <= 520.0:
                    continue
                L = _dist(a, nb)
                ux, uy = (nb[0] - a[0]) / L, (nb[1] - a[1]) / L
                along = abs(ux * (c[0] - a[0]) + uy * (c[1] - a[1])) / d
                if along >= 0.906:
                    cands.append((round(abs(d - 320.0) * (2.0 - along), 2), s.id, a, d))
        cands.sort(key=lambda k: (k[0], k[1], k[2]))
        for _, _, p, d in cands[:200]:
            # pitch at most about 12 degrees, aimed a third of the way up the tower
            tz = min(0.33 * b.height_m, 1.7 + 0.21 * d)
            if _visible(tree, foot, b, p, c, d, tz):
                seen.add(b.district_id)
                views.append({"name": f"view_{len(views) + 1}_{b.id}",
                              "eye": [q(p[0]), q(p[1]), 1.7],
                              "target": [q(c[0]), q(c[1]), q(tz)], "lens_mm": 28})
                break
    v = _viaduct_view(m, roads, tree, foot)
    if v is not None:
        views.append({**v, "name": f"view_{len(views) + 1}_{v['name']}"})
    dense = [d.id for d in m.districts if d.archetype in ("old_town", "entertainment_market")]
    for did in dense[:1]:
        cand = [s for s in roads if did in s.district_ids and len(s.centerline) >= 2]
        cand.sort(key=lambda s: (-_plen(s.centerline), s.id))
        if cand:
            pts = cand[0].centerline
            a, b = pts[0], pts[-1]
            L = _dist(a, b) or 1.0
            ahead = min(80.0, L)
            tgt = (a[0] + (b[0] - a[0]) / L * ahead, a[1] + (b[1] - a[1]) / L * ahead)
            views.append({"name": f"view_{len(views) + 1}_{did}_street",
                          "eye": [q(a[0]), q(a[1]), 1.7], "target": [q(tgt[0]), q(tgt[1]), 6.0],
                          "lens_mm": 28})
    return views


def _viaduct_view(m, roads, tree, foot) -> dict | None:
    """M7: from a ground road 70 to 140 m off the longest viaduct, looking at its deck where it
    is at least 8 m up and no building or tree crown blocks the view."""
    el = sorted((s for s in m.road_segments if s.attrs.get("elevated")),
                key=lambda s: (-s.attrs.get("length_m", 0.0), s.id))
    if not el or not roads:
        return None
    gl = [LineString(s.centerline) for s in roads]
    gtree = shapely.STRtree(gl)
    plants = [p for p in m.plants if p.position[2] <= 0.5]
    ptree = shapely.STRtree([Point(p.position[0], p.position[1]) for p in plants]) \
        if plants else None
    # (no deck over the eye or right beside it)
    up = [LineString(s.centerline) for s in m.road_segments
          if any(z.z > 0.5 for z in s.z_profile)]
    utree = shapely.STRtree(up) if up else None
    for s in el[:3]:
        line = LineString(s.centerline)
        prof = [(z.s, z.z) for z in s.z_profile]
        L = line.length
        for f in (0.5, 0.4, 0.6, 0.3, 0.7):
            d = f * L
            zs = [z for s_, z in prof]
            # deck height at d (linear in the profile)
            z = zs[0]
            for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
                if s0 <= d <= s1:
                    z = z0 + (z1 - z0) * (d - s0) / (s1 - s0 or 1.0)
                    break
            if z < 8.0:
                continue
            a, b = line.interpolate(max(d - 5.0, 0.0)), line.interpolate(min(d + 5.0, L))
            n = _dist((a.x, a.y), (b.x, b.y)) or 1.0
            ux, uy = (b.x - a.x) / n, (b.y - a.y) / n
            p = line.interpolate(d)
            for side in (1.0, -1.0):
                for off in (100.0, 80.0, 130.0):
                    want = Point(p.x - uy * off * side, p.y + ux * off * side)
                    best = None
                    for i in sorted(gtree.query(want, predicate="dwithin", distance=30.0)
                                    .tolist()):
                        e = shapely.ops.nearest_points(gl[i], want)[0]
                        k = (round(e.distance(want), 2), roads[i].id)
                        if best is None or k < best[0]:
                            best = (k, (q(e.x), q(e.y)))
                    if best is None:
                        continue
                    eye = best[1]
                    dd = _dist(eye, (p.x, p.y))
                    if not 70.0 <= dd <= 140.0 or (utree is not None and len(utree.query(
                            Point(eye), predicate="dwithin", distance=15.0))) or \
                            (tree is not None and len(tree.query(
                                Point(eye), predicate="dwithin", distance=7.0))):
                        continue      # (nor a facade filling the frame)
                    sight = LineString([eye, (eye[0] + (p.x - eye[0]) * 0.9,
                                              eye[1] + (p.y - eye[1]) * 0.9)])
                    blocked = False
                    if tree is not None:
                        for j in sorted(tree.query(sight, predicate="intersects").tolist()):
                            bl, fp = foot[j]
                            near = fp.distance(Point(eye))
                            if bl.height_m > 1.7 + (z - 1.7) * near / dd:
                                blocked = True
                                break
                    if not blocked and ptree is not None:
                        for j in sorted(ptree.query(sight, predicate="dwithin",
                                                    distance=12.0).tolist()):
                            pl = plants[j]
                            pp = Point(pl.position[0], pl.position[1])
                            near = Point(eye).distance(pp)
                            if pl.height_m > 1.7 + (z - 1.7) * near / dd and \
                                    sight.distance(pp) < pl.crown_radius_m + 0.5:
                                blocked = True
                                break
                    if not blocked:
                        return {"name": f"{s.id}_viaduct", "eye": [eye[0], eye[1], 1.7],
                                "target": [q(p.x), q(p.y), q(z - 1.0)], "lens_mm": 24}
    return None


def _visible(tree, foot, target, eye, c, d, tz) -> bool:
    """No other building rises above the line of sight over the first 85% of it."""
    if tree is None:
        return True
    end = (eye[0] + (c[0] - eye[0]) * 0.85, eye[1] + (c[1] - eye[1]) * 0.85)
    line = LineString([eye, end])
    e = Point(eye)
    for i in sorted(tree.query(line, predicate="intersects").tolist()):
        b, f = foot[i]
        if b.id == target.id or (b.property_id and b.property_id == target.property_id):
            continue
        near = round(f.distance(e), 1)
        if b.height_m > 1.7 + (tz - 1.7) * near / d:
            return False
    return True


def _plen(pts) -> float:
    return sum(_dist(a, b) for a, b in zip(pts, pts[1:]))


# --- the plan ---------------------------------------------------------------------------------

def make_plan(m: CityModel) -> dict:
    with G.canonical():
        P = _Plan(m)
        _land_and_water(P)
        _streets(P)
        _open_space(P)
        _buildings(P)
        _sites(P)
        _decks(P)
        _tunnels(P)
        _dressing(P)
        _terrain(P)
        cams = _cameras(P)
    for o in P.objects:
        ids = o["props"].get("citygen_ids")
        if isinstance(ids, list):
            o["props"]["citygen_ids"] = ";".join(ids)
            o["props"]["count"] = len(ids)
    protos = sorted({p["proto"] for o in P.objects for p in o["parts"] if p["k"] == "inst"})
    used = sorted({p["m"] for o in P.objects for p in o["parts"] if p["k"] != "inst"} |
                  {p["m"] for k in protos for p in PROTOTYPES[k]})
    tiles = sorted(P.tiles)
    x0, y0, x1, y1 = m.bounds
    counts: dict[str, int] = {}
    for o in P.objects:
        counts[o["category"]] = counts.get(o["category"], 0) + 1
    return {
        "version": PLAN_VERSION, "city": m.name, "seed": m.seed, "bounds": list(m.bounds),
        "tile_size_m": TILE_M,
        "materials": {k: MATERIALS[k] for k in used},
        "tiles": [{"name": tile_name(ix, iy), "ix": ix, "iy": iy,
                   "bounds": [max(ix * TILE_M, x0), max(iy * TILE_M, y0),
                              min((ix + 1) * TILE_M, x1), min((iy + 1) * TILE_M, y1)]}
                  for ix, iy in tiles],
        "cameras": cams,
        "prototypes": {k: PROTOTYPES[k] for k in protos},
        "objects": P.objects,
        "stats": {"objects": len(P.objects), "by_category": dict(sorted(counts.items())),
                  "parts": sum(len(o["parts"]) for o in P.objects), "tiles": len(tiles),
                  "buildings": sum(1 for o in P.objects if o["category"] in
                                   ("building", "landmark")),
                  "instances": sum(len(p["pts"]) for o in P.objects for p in o["parts"]
                                   if p["k"] == "inst")},
    }


def plan_json(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def plan_sha256(plan: dict) -> str:
    return hashlib.sha256((plan_json(plan) + "\n").encode("utf-8")).hexdigest()


# --- running Blender ------------------------------------------------------------------------

BLENDER_SCRIPT = Path(__file__).resolve().parent / "blender" / "build.py"
RERENDER_SCRIPT = Path(__file__).resolve().parent / "blender" / "rerender.py"
README_WIDTH = 7680  # README images: 8K wide
BUDGET_S = 600.0  # scope section 10: the Blender build under 10 minutes
VERIFY = ("import bpy, json\n"
          "objs = [o for o in bpy.data.objects if 'citygen_category' in o]\n"
          "print('CITYGEN_VERIFY ' + json.dumps({'objects': len(objs), 'buildings': sum(1 for o"
          " in objs if o['citygen_category'] in ('building', 'landmark')), 'faces': sum(len("
          "o.data.polygons) for o in objs if o.type == 'MESH'), 'tiles': len({o['citygen_tile']"
          " for o in objs}), 'instances': sum(int(o.get('citygen_instances', 0)) for o in objs),"
          " 'evaluated': sum(1 for i in bpy.context.evaluated_depsgraph_get().object_instances"
          " if i.is_instance)}))\n")


def _version_key(path: str) -> tuple:
    nums = re.findall(r"\d+", Path(path).name)
    return tuple(int(n) for n in nums) or (0,)


def find_blender(explicit: str | None = None) -> str | None:
    """Blender: `explicit`, $BLENDER, the newest /Applications/Blender*.app (a Mac) or
    Program Files/Blender Foundation/Blender * (Windows), or `blender`."""
    for cand in (explicit, os.environ.get("BLENDER")):
        if cand:
            return cand if Path(cand).exists() else None
    apps = sorted(glob.glob("/Applications/Blender*.app"), key=_version_key, reverse=True)
    for app in apps:
        exe = Path(app) / "Contents" / "MacOS" / "Blender"
        if exe.exists():
            return str(exe)
    if sys.platform == "win32":
        base = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Blender Foundation"
        for d in sorted(glob.glob(str(base / "Blender *")), key=_version_key, reverse=True):
            exe = Path(d) / "blender.exe"
            if exe.exists():
                return str(exe)
    return shutil.which("blender")


# Blender's stages on the progress line (citygen/blender/build.py's progress lines)
BLENDER_LABELS = {"blender_start": "Blender start", "objects": "Blender: objects",
                  "save": "Blender: saving city.blend", "usd": "Blender: USD export",
                  "gltf": "Blender: glTF tiles", "renders": "Blender: renders"}


def _run(cmd: list[str], marker: str, timeout: float,
         start: str | None = None) -> tuple[dict | None, str]:
    """Blender's output (its progress lines to the active progress, a `start` stage until
    the first) and the JSON of its `marker` line."""
    from . import progress as PG

    relay = PG.Relay(PG.active(), BLENDER_LABELS)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    if start:
        relay.open(start)
    lines: list[str] = []

    def pump():
        for line in proc.stdout:
            lines.append(line)
            if PG.MARKER in line:
                relay.feed(line)

    th = threading.Thread(target=pump, daemon=True)
    th.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        th.join(10)
        relay.close(ok=False)
        raise
    th.join(15)     # (a process Blender started may hold the pipe: not waited for long)
    relay.close(ok=proc.returncode == 0)
    out = "".join(lines)
    for line in out.splitlines():
        if line.startswith(marker + " "):
            return json.loads(line[len(marker) + 1:]), out
    return None, out


def rerender(blockout_dir: str | Path, to_dir: str | Path, views: list[str],
             width: int = README_WIDTH, blender: str | None = None,
             samples: int = 16, eye=None, target=None, lens: float = 35.0,
             name: str = "custom") -> list[str]:
    """Render chosen views of a blockout (`top`, `iso_city`, `iso_<district>`, `street_<n>`)
    again from its city.blend, `width` pixels wide, as to_dir/render_<view>.jpg (same cameras
    as the build), plus, with `eye` and `target` (plan coordinates, meters), a perspective
    view of one's own as render_<name>.jpg. Returns the files written."""
    exe = find_blender(blender)
    if exe is None:
        raise RuntimeError("no Blender (set BLENDER or --blender)")
    cmd = [exe, "-b", "--factory-startup", "-P", str(RERENDER_SCRIPT), "--",
           str(Path(blockout_dir)), str(Path(to_dir)), "--width", str(width), "--samples",
           str(samples), *views]
    if eye is not None and target is not None:
        cmd += ["--eye", *map(str, eye), "--target", *map(str, target), "--lens", str(lens),
                "--name", name]
    done, log = _run(cmd, "CITYGEN_RERENDER_DONE", timeout=BUDGET_S)
    if done is None:
        raise RuntimeError("Blender rerender failed:\n" + log[-2000:])
    return done["files"]


def run_blockout(model_path: str | Path, out_dir: str | Path, blender: str | None = None,
                 render: bool = True, export: bool = True, res: int = 1600,
                 samples: int = 16) -> dict:
    """Plan, 2D map and exports here, then the .blend, USD, glTF tiles and renders in
    Blender, then the .blend reopened in a fresh Blender to count what it holds. Returns the
    report (also written as blockout_report.json and .txt)."""
    from . import exports as X

    from . import progress as PG

    P = PG.active()
    t0 = time.perf_counter()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ps = P.begin("blockout plan")
    m = CityModel.from_json(Path(model_path).read_text(encoding="utf-8"))
    plan = make_plan(m)
    text = plan_json(plan) + "\n"
    (out / "blockout_plan.json").write_text(text, encoding="utf-8", newline="\n")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    t_plan = time.perf_counter() - t0
    ps.finish()
    ps = P.begin("2D map and exports")
    X.map_svg(m, out / "map_2d.svg")
    X.map_png(m, out / "map_2d.png")
    (out / "unreal").mkdir(exist_ok=True)
    views = plan["cameras"]["street"]
    start = views[0]["eye"] if views else None
    (out / "unreal" / "corporate_core_plan.json").write_text(
        json.dumps(X.legacy_plan(m, start), indent=1) + "\n", encoding="utf-8", newline="\n")
    # (M13: a terrain city's graphs with absolute heights, as the blockout draws them)
    ground = _Ground(m) if m.terrain is not None else None
    (out / "graphs.json").write_text(json.dumps(X.graphs(m, ground)) + "\n",
                                     encoding="utf-8", newline="\n")
    (out / "tiles.json").write_text(json.dumps({"tile_size_m": TILE_M, "tiles": plan["tiles"]},
                                               indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "props.csv").write_text(X.props_csv(m), encoding="utf-8", newline="\n")
    if m.pois or m.zones or m.densities:
        (out / "gameplay.json").write_text(json.dumps(X.gameplay(m)) + "\n",
                                           encoding="utf-8", newline="\n")
    t_exports = time.perf_counter() - t0 - t_plan
    ps.finish()
    exe = find_blender(blender)
    checks = []
    blender_rep, verify = None, None
    if exe is None:
        checks.append(("blender_found", False, "no Blender (set BLENDER or --blender)"))
    else:
        cmd = [exe, "-b", "--factory-startup", "-P", str(BLENDER_SCRIPT), "--",
               str(out / "blockout_plan.json"), str(out), "--res", str(res), "--samples",
               str(samples)]
        if not render:
            cmd.append("--no-render")
        if not export:
            cmd.append("--no-export")
        done, log = _run(cmd, "CITYGEN_BLOCKOUT_DONE", timeout=3 * BUDGET_S,
                         start="blender_start")
        (out / "blender_log.txt").write_text(log, encoding="utf-8", newline="\n")
        if done is not None and (out / "blender_report.json").is_file():
            blender_rep = json.loads((out / "blender_report.json").read_text())
        checks.append(("blender_build", blender_rep is not None,
                       "built" if blender_rep else "Blender failed; see blender_log.txt"))
        if blender_rep is not None:
            with P.stage("blockout check (city.blend reopened)"):
                verify, vlog = _run([exe, "-b", str(out / "city.blend"), "--python-expr",
                                     VERIFY], "CITYGEN_VERIFY", timeout=BUDGET_S)
            checks += _checks(m, plan, blender_rep, verify, out, render, export)
    total = time.perf_counter() - t0
    if blender_rep is not None:
        checks.append(("blender_budget", blender_rep["timings"]["total_s"] <= BUDGET_S,
                       f"Blender {blender_rep['timings']['total_s']} s (budget "
                       f"{BUDGET_S:.0f} s)"))
    report = {
        "city": m.name, "passed": all(ok for _, ok, _ in checks),
        "checks": [{"id": i, "passed": ok, "detail": d} for i, ok, d in checks],
        "plan_sha256": sha, "plan": plan["stats"],
        "blender": blender_rep, "verify": verify,
        "timings": {"plan_s": round(t_plan, 1), "exports_s": round(t_exports, 1),
                    "total_s": round(total, 1)},
    }
    (out / "blockout_report.json").write_text(json.dumps(report, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")
    (out / "blockout_report.txt").write_text(report_text(report), encoding="utf-8", newline="\n")
    return report


def _checks(m, plan, rep, verify, out: Path, render: bool, export: bool) -> list:
    out_checks = []
    n_bld = sum(1 for b in m.buildings if any(ms.z1_m > ms.z0_m and ms.role != "void"
                                              for ms in b.masses) or b.roof_items)
    ok = verify is not None
    out_checks.append(("blend_opens", ok, "city.blend reopened in a fresh Blender" if ok else
                       "city.blend did not open"))
    if ok:
        out_checks.append(("blend_objects", verify["objects"] == len(plan["objects"]),
                           f"{verify['objects']} objects in the .blend, "
                           f"{len(plan['objects'])} in the plan"))
        out_checks.append(("blend_buildings", verify["buildings"] == n_bld,
                           f"{verify['buildings']} building objects, {n_bld} buildings with "
                           f"masses in the model"))
        want = plan["stats"].get("instances", 0)
        out_checks.append(("blend_instances", verify.get("instances", 0) == want and
                           verify.get("evaluated", 0) == want,
                           f"{verify.get('evaluated', 0)} prop and plant instances evaluated "
                           f"in the .blend, {want} in the plan"))
    if export:
        tiles = rep["files"].get("gltf_tiles", [])
        want = len({o["tile"] for o in plan["objects"]
                    if not (o["parts"] and o["parts"][0]["k"] == "inst")})
        out_checks.append(("gltf_tiles", len(tiles) == want and all(
            (out / t).is_file() and (out / t).stat().st_size > 0 for t in tiles),
            f"{len(tiles)} tile files for {want} tiles with objects"))
        usd = rep["files"].get("usd")
        out_checks.append(("usd_export", bool(usd) and (out / usd).is_file() and
                           (out / usd).stat().st_size > 0, f"{usd}"))
    if render:
        want = 1 + (1 if plan["cameras"]["districts"] else 0) + \
            len(plan["cameras"]["districts"]) + len(plan["cameras"]["street"]) + \
            (1 if plan["cameras"].get("cutaway") else 0) + \
            (1 if plan["cameras"].get("deck") else 0)
        got = [r for r in rep["files"].get("renders", []) if (out / r).is_file()]
        out_checks.append(("renders", len(got) == want, f"{len(got)} of {want} renders"))
    return out_checks


def report_text(rep: dict) -> str:
    lines = [f"citygen blockout: {rep['city']}",
             f"result: {'PASS' if rep['passed'] else 'FAIL'}", ""]
    for c in rep["checks"]:
        lines.append(f"  [{'pass' if c['passed'] else 'FAIL'}] {c['id']}: {c['detail']}")
    p = rep["plan"]
    lines += ["", f"plan: {p['objects']} objects, {p['parts']} parts, {p['tiles']} tiles, "
              f"{p['buildings']} buildings (sha256 {rep['plan_sha256'][:16]})"]
    b = rep.get("blender")
    if b:
        mb = {k: round(v / 1e6, 1) for k, v in b["bytes"].items()}
        lines += [f"blender {b['blender']}: {b['vertices']} vertices, {b['faces']} faces, "
                  f"{b.get('instances', 0)} instances, "
                  f"{b['materials']} materials, {b['collections']} collections",
                  f"files (MB): {json.dumps(mb)}",
                  f"timings (s): {json.dumps(b['timings'])}"]
    lines.append(f"total (s): {json.dumps(rep['timings'])}")
    return "\n".join(lines) + "\n"


# --- terrain (M13) ------------------------------------------------------------------------------

DRAPE_STEP_M = 6.0       # draped edges are sampled at least this often
DRAPE_CELL_M = 16.0      # a large flat (a park, a plaza) is draped cell by cell
BED_M = 2.0              # the ground mesh under the water, below its level
WATER_DROP_M = 0.3       # the water surface under its level (under the levee)


def _densify_ring(ring, step=DRAPE_STEP_M):
    out = []
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        out.append(a)
        L = _dist(a, b)
        k = int(math.ceil(L / step))
        for j in range(1, k):
            f = j / k
            out.append([q(a[0] + (b[0] - a[0]) * f), q(a[1] + (b[1] - a[1]) * f)])
    return out


def _densify_ribbon(part, step=DRAPE_STEP_M):
    l_, r_ = part["l"], part["rr"]
    L2, R2 = [l_[0]], [r_[0]]
    for i in range(len(l_) - 1):
        a, b, c, d = l_[i], l_[i + 1], r_[i], r_[i + 1]
        mid0 = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
        mid1 = ((b[0] + d[0]) / 2, (b[1] + d[1]) / 2)
        k = int(math.ceil(_dist(mid0, mid1) / step))
        for j in range(1, k):
            f = j / k
            L2.append([q(a[0] + (b[0] - a[0]) * f), q(a[1] + (b[1] - a[1]) * f),
                       q(a[2] + (b[2] - a[2]) * f)])
            R2.append([q(c[0] + (d[0] - c[0]) * f), q(c[1] + (d[1] - c[1]) * f),
                       q(c[2] + (d[2] - c[2]) * f)])
        L2.append(b)
        R2.append(d)
    part["l"], part["rr"] = L2, R2


class _Ground:
    """Heights for the blockout: the finished ground, roads' grade lines, building bases."""

    def __init__(self, m):
        from . import terrain as TE

        self.TE = TE
        self.fin = TE.ground_of(m)
        self.segs = {}
        for s in m.road_segments:
            if s.ground:
                line = [tuple(p) for p in s.centerline]
                self.segs[s.id] = (line, TE._cum(line), [(p.s, p.z) for p in s.ground])
        self.base = {b.id: b.base_m for b in m.buildings if b.base_m is not None}
        self.sky = {s.id: s.base_m for s in m.skybridges if s.base_m is not None}
        foots = [(G.from_model_poly(b.footprint), b.base_m) for b in m.buildings
                 if b.footprint is not None and b.base_m is not None]
        self.foots = foots
        self.ftree = shapely.STRtree([f for f, _ in foots]) if foots else None

    def at(self, x, y) -> float:
        return self.fin.at(x, y)

    def road(self, sid, x, y) -> float:
        rec = self.segs.get(sid)
        if rec is None:
            return self.fin.at(x, y)
        line, cum, prof = rec
        from .elevated import _project

        return self.TE.z_on(prof, _project(line, cum, (x, y))[0])

    def building_base(self, x, y) -> float | None:
        if self.ftree is None:
            return None
        hit = self.ftree.query(Point(x, y), predicate="intersects").tolist()
        return min((self.foots[i][1] for i in hit), default=None)


def _lift_part(p, fz, drape_big=False):
    """A part over the ground: fz(x, y) is the ground under each point."""
    k = p["k"]
    if p.get("abs"):
        return [p]
    if k == "prism":
        cx, cy = _center(p["r"])
        g = fz(cx, cy)
        return [{**p, "z0": q(p["z0"] + g), "z1": q(p["z1"] + g)}]
    if k == "flat":
        out = []
        poly = Polygon(p["r"], p["h"])
        bx0, by0, bx1, by1 = poly.bounds
        if drape_big and max(bx1 - bx0, by1 - by0) > DRAPE_CELL_M * 2:
            pieces = []
            i0, i1 = int(math.floor(bx0 / DRAPE_CELL_M)), int(math.ceil(bx1 / DRAPE_CELL_M))
            j0, j1 = int(math.floor(by0 / DRAPE_CELL_M)), int(math.ceil(by1 / DRAPE_CELL_M))
            cells = [box(i * DRAPE_CELL_M, j * DRAPE_CELL_M, (i + 1) * DRAPE_CELL_M,
                         (j + 1) * DRAPE_CELL_M) for j in range(j0, j1) for i in range(i0, i1)]
            for piece in shapely.intersection(np.array(cells, dtype=object), poly).tolist():
                pieces += G.parts(piece)
        else:
            pieces = [poly]
        for pc in pieces:
            ext, holes = _shapely_rings(pc)
            if len(ext) < 3:
                continue
            rings = [_densify_ring(ext)] + [_densify_ring(h) for h in holes]
            r3 = [[[x, y, q(p["z"] + fz(x, y))] for x, y in r] for r in rings]
            out.append({"k": "drape", "m": p["m"], "r": r3[0], "h": r3[1:]})
        return out
    if k == "ribbon":
        p = dict(p)
        _densify_ribbon(p)
        L, R = [], []
        for a, b in zip(p["l"], p["rr"]):
            g = fz((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            L.append([a[0], a[1], q(a[2] + g)])
            R.append([b[0], b[1], q(b[2] + g)])
        p["l"], p["rr"] = L, R
        return [p]
    if k == "box":
        c = p["c"]
        return [{**p, "c": [c[0], c[1], q(c[2] + fz(c[0], c[1]))]}]
    if k == "beam":
        a, b = p["a"], p["b"]
        return [{**p, "a": [a[0], a[1], q(a[2] + fz(a[0], a[1]))],
                 "b": [b[0], b[1], q(b[2] + fz(b[0], b[1]))]}]
    if k == "mesh":
        return [{**p, "v": [[x, y, q(z + fz(x, y))] for x, y, z in p["v"]]}]
    if k == "inst":
        return [{**p, "pts": [[pt[0], pt[1], q(pt[2] + fz(pt[0], pt[1]))] + pt[3:]
                              for pt in p["pts"]]}]
    return [p]


def _ground_grid(P: _Plan, gd: _Ground) -> None:
    """The ground as a heightfield per tile (the finished ground; under the water its bed)."""
    m = P.m
    fin = gd.fin
    X, Y = fin.grid()
    Z = fin.arr.copy()
    wet = shapely.contains_xy(P.wet, X, Y) if not P.wet.is_empty else np.zeros(Z.shape, bool)
    Z = np.where(wet, Z - BED_M, Z)
    land = G.union([G.from_model_poly(p) for lnd in m.land for p in lnd.polygons])
    holes = [G.from_model_poly(st.footprint) for st in m.structures
             if st.kind == "trench" and st.footprint is not None]
    trench = G.union(holes) if holes else None
    for o in [o for o in P.objects if o["category"] == "ground"]:
        P.objects.remove(o)
    x0, y0, x1, y1 = m.bounds
    ix0, iy0 = tile_key(x0, y0)
    ix1, iy1 = tile_key(x1 - 1e-6, y1 - 1e-6)
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            tb = box(max(ix * TILE_M, x0), max(iy * TILE_M, y0),
                     min((ix + 1) * TILE_M, x1), min((iy + 1) * TILE_M, y1))
            if not tb.intersects(land):
                continue
            i0 = int(math.floor((tb.bounds[0] - fin.x0) / fin.cell))
            i1 = min(fin.nx - 1, int(math.ceil((tb.bounds[2] - fin.x0) / fin.cell)))
            j0 = int(math.floor((tb.bounds[1] - fin.y0) / fin.cell))
            j1 = min(fin.ny - 1, int(math.ceil((tb.bounds[3] - fin.y0) / fin.cell)))
            nx, ny = i1 - i0 + 1, j1 - j0 + 1
            if nx < 2 or ny < 2:
                continue
            zs = [q(float(v)) for v in Z[j0:j1 + 1, i0:i1 + 1].ravel()]
            skip = []
            if trench is not None and tb.intersects(trench):
                cx = fin.x0 + (np.arange(i0, i1) + 0.5) * fin.cell
                cy = fin.y0 + (np.arange(j0, j1) + 0.5) * fin.cell
                CX, CY = np.meshgrid(cx, cy)
                skip = np.nonzero(shapely.contains_xy(trench, CX, CY).ravel())[0].tolist()
            t = (ix, iy)
            P.add(f"city.ground.{tile_name(*t)}", [P.city, "Ground"], t, "ground",
                  [{"k": "grid", "m": "ground", "abs": True, "x0": q(fin.x0 + i0 * fin.cell),
                    "y0": q(fin.y0 + j0 * fin.cell), "c": fin.cell, "nx": nx, "ny": ny,
                    "z": zs, "skip": skip}],
                  {"citygen_type": "ground"})


def _water_levels(P: _Plan, gd: _Ground):
    """(x, y) -> the water's level there (the river's at its nearest centerline point)."""
    m = P.m
    lv = {w.water_id: w for w in m.terrain.water_levels}
    polys = []
    for wid, kind, poly, ent in gd.TE.water_bodies(m):
        w = lv.get(wid)
        if w is None:
            continue
        if w.profile:
            line = [tuple(p) for p in ent.centerline]
            polys.append((poly, line, gd.TE._cum(line), [(p.s, p.z) for p in w.profile]))
        else:
            polys.append((poly, None, None, w.level_m))
    from .elevated import _project

    def level(x, y):
        pt = Point(x, y)
        best = None
        for poly, line, cum, v in polys:
            d = poly.distance(pt)
            if best is None or d < best[0]:
                best = (d, poly, line, cum, v)
        if best is None:
            return 0.0
        _, poly, line, cum, v = best
        if line is None:
            return v
        return gd.TE.z_on(v, _project(line, cum, (x, y))[0])
    return level


def _terrain(P: _Plan) -> None:
    """M13: everything onto the ground. The ground becomes a heightfield; the water sits at
    its level; roads on their grade lines; buildings, their roof items and skybridges on
    their bases, with stepped plinths down to the ground; everything else over the finished
    ground where it stands; retaining walls."""
    m = P.m
    if m.terrain is None:
        return
    gd = _Ground(m)
    level = _water_levels(P, gd)
    seg_ids = set(gd.segs)
    walk_seg = {w.id: w.segment_id for w in m.sidewalks}
    bored = {t.id: t.segment_ids[0] for t in m.tunnels if t.kind == "bored" and t.segment_ids}
    road_tun = {t.id: t.segment_ids[0] for t in m.tunnels
                if t.kind in ("immersed_tube", "cut_and_cover") and t.segment_ids}
    for o in list(P.objects):
        cat = o["category"]
        if cat in ("ground", "sea"):
            continue
        props = o["props"]
        cid = props.get("citygen_id")
        ids = props.get("citygen_ids")
        ids = ids if isinstance(ids, list) else None
        if cat == "water":
            o["parts"] = [{"k": "drape", "m": p["m"], "abs": True,
                           "r": [[x, y, q(level(x, y) - WATER_DROP_M)]
                                 for x, y in _densify_ring(p["r"], 24.0)],
                           "h": [[[x, y, q(level(x, y) - WATER_DROP_M)]
                                  for x, y in _densify_ring(h, 24.0)] for h in p["h"]]}
                          for p in o["parts"]]
            continue
        if cat in ("building", "landmark"):
            base = gd.base.get(cid)
            if base is None:
                o["parts"] = [x for p in o["parts"] for x in _lift_part(p, gd.at)]
                continue
            b = next(bb for bb in m.buildings if bb.id == cid)
            parts = [x for p in o["parts"] for x in _lift_part(p, lambda x_, y_: base)]
            parts += _plinth(b, gd)
            o["parts"] = parts
            continue
        if cat == "skybridge":
            base = gd.sky.get(cid, 0.0)
            o["parts"] = [x for p in o["parts"] for x in _lift_part(p, lambda x_, y_: base)]
            continue
        new = []
        for i, p in enumerate(o["parts"]):
            eid = ids[i] if ids is not None and i < len(ids) else cid
            if eid in seg_ids:
                fz = (lambda sid: lambda x, y: gd.road(sid, x, y))(eid)
            elif eid in walk_seg and walk_seg[eid] in seg_ids:
                fz = (lambda sid: lambda x, y: gd.road(sid, x, y))(walk_seg[eid])
            elif cid in bored or cid in road_tun:
                sid = bored.get(cid) or road_tun.get(cid)
                fz = (lambda sid: lambda x, y: gd.road(sid, x, y))(sid)
            elif cat in ("green_roof",) or (cat.startswith("open_") and p.get("z", 0.0) > 0.6):
                cx, cy = _center(p["r"])
                bb = gd.building_base(cx, cy)
                fz = (lambda v: lambda x, y: v)(bb) if bb is not None else gd.at
            else:
                fz = gd.at
            new += _lift_part(p, fz, drape_big=cat.startswith("open_") or cat in
                              ("junction", "lawn"))
        o["parts"] = new
    _ground_grid(P, gd)
    _walls(P, gd)


def _plinth(b, gd: _Ground) -> list[dict]:
    """A stepped plinth from the ground up to the base: the footprint cut into 8 m cells,
    each from the lowest ground at its corners."""
    if b.footprint is None or b.base_m is None or b.plinth_m is None or \
            b.base_m - b.plinth_m < 0.3:
        return []
    poly = G.from_model_poly(b.footprint)
    bx0, by0, bx1, by1 = poly.bounds
    step = 8.0
    cells = [box(bx0 + i * step, by0 + j * step, bx0 + (i + 1) * step, by0 + (j + 1) * step)
             for j in range(int(math.ceil((by1 - by0) / step)))
             for i in range(int(math.ceil((bx1 - bx0) / step)))]
    out = []
    for piece in shapely.intersection(np.array(cells, dtype=object), poly).tolist():
        for pc in G.parts(piece):
            ext, holes = _shapely_rings(pc)
            if len(ext) < 3:
                continue
            low = min(gd.at(x, y) for x, y in ext)
            if b.base_m - low < 0.3:
                continue
            out.append({"k": "prism", "m": "plinth", "abs": True, "z0": q(low - 0.5),
                        "z1": q(b.base_m), "r": ext, "h": holes, "s": "prism"})
    return out


def _walls(P: _Plan, gd: _Ground) -> None:
    """Retaining walls: a 0.5 m slab along each wall, from under the lower ground to a
    parapet over the upper; one object per wall, named by its id (M15: the Unreal exporter
    keys its actors by stable id)."""
    for w in P.m.structures:
        if w.kind != "retaining_wall" or len(w.line) < 2:
            continue
        pts = [(p[0], p[1]) for p in w.line]
        tops = [q(gd.at(x, y) + h / 2.0 + 0.3) for (x, y), (_, _, h) in zip(pts, w.line)]
        r = ribbon(pts, 0.5, tops)
        if r is None:
            continue
        cx, cy = _center(pts)
        P.add(w.id, [P.city, "Ground", "Retaining walls"], tile_key(cx, cy), "retaining_wall",
              [{"k": "ribbon", "m": "retaining_wall", "abs": True, "l": r[0], "rr": r[1],
                "t": q(max(h for _, _, h in w.line) + 1.0)}],
              {"citygen_id": w.id, "citygen_type": "structure.retaining_wall"})
