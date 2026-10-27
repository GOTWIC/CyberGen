"""M13 checks: the ground. They run on cities with `terrain` only (a flat city passes them
all, with nothing to check):

- `ground_grades`: every road at most its class's grade on the ground (grade line plus z):
  highways 6%, avenues 8%, streets and service roads 12%, alleys and pedestrian ways 15%.
- `cut_fill`: open cuts at most CUT_MAX_M and fills at most FILL_MAX_M under the natural
  ground; deeper cuts only bored (with at least 1 m of rock over the roof).
- `retaining_walls`: the finished ground no steeper than an embankment (1:1.5) where grading
  made it so, unless a retaining wall, a bored tunnel's portal or a building stands there.
- `building_seats`: every building seated: base at its entrance ground (within half a floor),
  a plinth at most PLINTH_MAX_M under the base, the ground at most BURY_MAX_M over it.
- `water_levels`: every water body at its level (sea 0, rivers never rising downstream,
  waterways at the level of what they join), the ground at the water at that level and the
  land beside it over it.
"""

from __future__ import annotations

import math

import numpy as np
import shapely

from . import geom as G
from . import terrain as TE
from .checks import Check

GRADE_TOL = 0.002
PLINTH_MAX_M = 16.0
BURY_MAX_M = 16.0
LEVEL_TOL_M = 0.05
SHOW = 12


def _limit(c: Check, msg: str) -> None:
    if len(c.failures) < SHOW:
        c.failures.append(msg)
    elif len(c.failures) == SHOW:
        c.failures.append("...")


def _fields(m):
    t = m.terrain
    return TE.Field.from_rows(t, t.natural), TE.ground_of(m)


def check_grades(m) -> Check:
    c = Check("ground_grades", "Every road at most its class's grade on the ground (grade "
                               "line plus z): highways and ramps 6%, avenues 8%, streets 12%, "
                               "alleys and pedestrian ways 15%")
    for s in m.road_segments:
        if not s.ground or s.road_class == "footbridge":
            continue
        g = TE.MAX_GRADE.get(s.road_class, 0.12)
        if s.attrs.get("ramp") or s.type.endswith(".ramp"):
            g = TE.MAX_GRADE["highway"]
        zp = [(p.s, p.z) for p in s.z_profile]
        st = [(p.s, p.z) for p in s.ground]
        for (s0, g0), (s1, g1) in zip(st, st[1:]):
            L = s1 - s0
            if L < 0.5:
                continue
            dz = abs(g1 + TE.z_on(zp, s1) - g0 - TE.z_on(zp, s0))
            if (dz - 0.02) / L > g + GRADE_TOL:
                _limit(c, f"{s.id} ({s.road_class}): {dz / L:.1%} at s {s0:.0f} m "
                          f"(maximum {g:.0%})")
                break
    return c


def check_cut_fill(m) -> Check:
    c = Check("cut_fill", f"Open cuts at most {TE.CUT_MAX_M:g} m and fills at most "
                          f"{TE.FILL_MAX_M:g} m against the natural ground; deeper cuts bored "
                          "with at least 1 m of rock over the tunnel roof, higher roads on "
                          "viaducts")
    nat, _ = _fields(m)
    bored: dict[str, list[tuple[float, float]]] = {}
    for t in m.tunnels:
        if t.kind == "bored":
            for sid in t.segment_ids:
                bored.setdefault(sid, []).append((t.attrs["s0"], t.attrs["s1"]))
            if t.attrs.get("min_cover_m", 0.0) < 1.0 - 0.01:
                _limit(c, f"{t.id} (bored): {t.attrs.get('min_cover_m', 0.0):.1f} m of rock")
    raised: dict[str, list[tuple[float, float]]] = {}
    for st in m.structures:
        if st.attrs.get("terrain_viaduct") and st.kind == "deck":
            raised.setdefault(st.attrs["segment"], []).append((st.attrs["s0"], st.attrs["s1"]))
    water = TE.water_union(m)
    for s in m.road_segments:
        if not s.ground or s.bridge or s.road_class == "footbridge":
            continue
        line = [tuple(p) for p in s.centerline]
        cum = TE._cum(line)
        pts = [TE.point_at(line, cum, p.s) for p in s.ground]
        wet = shapely.contains_xy(water, np.array([p[0] for p in pts]),
                                  np.array([p[1] for p in pts])).tolist()
        for p, (x, y), w in zip(s.ground, pts, wet):
            if w:
                continue
            d = p.z - nat.at(x, y)
            if d > TE.FILL_MAX_M + 0.05 and not any(a - 1 <= p.s <= b + 1
                                                     for a, b in raised.get(s.id, [])):
                _limit(c, f"{s.id} ({s.road_class}): {d:.1f} m of fill at ({x:.0f}, {y:.0f})")
                break
            if -d > TE.CUT_MAX_M + 0.05 and not any(a - 1 <= p.s <= b + 1
                                                     for a, b in bored.get(s.id, [])):
                _limit(c, f"{s.id} ({s.road_class}): {-d:.1f} m open cut at ({x:.0f}, "
                          f"{y:.0f})")
                break
    return c


def check_walls(m) -> Check:
    c = Check("retaining_walls", "Where grading made the ground steeper than an embankment "
                                 "(1:1.5), a retaining wall, a bored tunnel portal or a "
                                 "building stands")
    nat, fin = _fields(m)
    lim = 1.0 / TE.EMBANK_SLOPE * fin.cell
    F, H = fin.arr, nat.arr
    X, Y = fin.grid()
    cand = []
    for axis in (0, 1):
        dF = np.abs(np.diff(F, axis=axis))
        dH = np.abs(np.diff(H, axis=axis))
        bad = (dF > lim + 0.05) & (dH <= lim)
        js, iss = np.nonzero(bad)
        for j, i in zip(js.tolist(), iss.tolist()):
            j2, i2 = (j + 1, i) if axis == 0 else (j, i + 1)
            cand.append(((X[j, i] + X[j2, i2]) / 2, (Y[j, i] + Y[j2, i2]) / 2,
                         abs(F[j2, i2] - F[j, i])))
    if not cand:
        return c
    cover = [shapely.LineString([p[:2] for p in w.line]).buffer(2 * fin.cell)
             for w in m.structures if w.kind == "retaining_wall" and len(w.line) >= 2]
    cover += [shapely.Point(p.position[:2]).buffer(30.0) for t in m.tunnels
              if t.kind == "bored" for p in t.portals]
    cover += [G.from_model_poly(b.footprint).buffer(fin.cell) for b in m.buildings
              if b.footprint is not None]
    cover += [G.from_model_poly(w.polygon).buffer(2 * fin.cell)
              for w in list(m.rivers) + list(m.channels) + list(m.waterways)]
    for s in m.seas:
        cover += [G.from_model_poly(p).buffer(2 * fin.cell) for p in s.polygons]
    tree = shapely.STRtree(cover)
    pts = shapely.points(np.array([(x, y) for x, y, _ in cand]))
    hit = set(tree.query(pts, predicate="intersects")[0].tolist())
    for k, (x, y, d) in enumerate(cand):
        if k not in hit:
            _limit(c, f"a {d:.1f} m step in {fin.cell:g} m at ({x:.0f}, {y:.0f}) with no "
                      "retaining wall")
    return c


def check_seats(m) -> Check:
    c = Check("building_seats", f"Every building seated on the ground: base at its entrance "
                                f"ground (within half a floor), at most {PLINTH_MAX_M:g} m of "
                                f"plinth under the base and {BURY_MAX_M:g} m of ground over it")
    fin = TE.ground_of(m)
    for b in m.buildings:
        if b.footprint is None:
            continue
        if b.base_m is None or b.plinth_m is None:
            _limit(c, f"{b.id}: no base")
            continue
        e = next((e for e in b.entrances if e.kind == "main"),
                 b.entrances[0] if b.entrances else None)
        if e is not None:
            g = fin.at(*e.position)
            if abs(b.base_m - g) > b.floor_height_m / 2.0 + 0.05:
                _limit(c, f"{b.id}: base {b.base_m:.1f} m, entrance ground {g:.1f} m")
                continue
        vals = TE.footprint_ground(fin, G.from_model_poly(b.footprint))
        if b.plinth_m > min(vals) + 0.05 or b.plinth_m > b.base_m + 0.01:
            _limit(c, f"{b.id}: plinth {b.plinth_m:.1f} m over the ground under it")
        elif b.base_m - b.plinth_m > PLINTH_MAX_M + 0.05:
            _limit(c, f"{b.id}: {b.base_m - b.plinth_m:.1f} m of plinth")
        elif max(vals) - b.base_m > BURY_MAX_M + 0.05:
            _limit(c, f"{b.id}: {max(vals) - b.base_m:.1f} m of ground over its base")
    for sb in m.skybridges:
        if sb.base_m is None:
            _limit(c, f"{sb.id}: skybridge with no base")
    return c


def check_water(m) -> Check:
    c = Check("water_levels", "Every water body at its level: the sea at 0, rivers never "
                              "rising downstream, waterways at the level of what they join; "
                              "the ground in the water at that level, the land beside it over it")
    t = m.terrain
    nat, _ = _fields(m)
    lv = {w.water_id: w for w in t.water_levels}
    bodies = TE.water_bodies(m)
    for wid, kind, poly, ent in bodies:
        w = lv.get(wid)
        if w is None:
            _limit(c, f"{wid}: no level")
            continue
        if kind == "sea" and abs(w.level_m) > 1e-9:
            _limit(c, f"{wid}: the sea at {w.level_m:g} m")
        if w.profile:
            zs = [p.z for p in w.profile]
            up = all(b <= a + 1e-9 for a, b in zip(zs, zs[1:]))
            down = all(b >= a - 1e-9 for a, b in zip(zs, zs[1:]))
            if not (up or down):
                _limit(c, f"{wid}: its level rises and falls along it")
        if kind == "waterway" and ent.connects_to and not ent.ornamental and \
                ent.connects_to in lv and not lv[ent.connects_to].profile and \
                abs(lv[ent.connects_to].level_m - w.level_m) > LEVEL_TOL_M:
            _limit(c, f"{wid}: at {w.level_m:g} m, joins {ent.connects_to} at "
                      f"{lv[ent.connects_to].level_m:g} m")
    X, Y = nat.grid()
    for wid, kind, poly, ent in bodies:
        w = lv.get(wid)
        if w is None or w.profile:
            continue
        bx0, by0, bx1, by1 = poly.bounds
        js, iss = TE._window(nat, bx0, by0, bx1, by1)
        if js.start >= js.stop or iss.start >= iss.stop:
            continue
        inn = shapely.contains_xy(poly, X[js, iss], Y[js, iss])
        vals = nat.arr[js, iss][inn]
        if vals.size and float(np.max(np.abs(vals - w.level_m))) > LEVEL_TOL_M:
            _limit(c, f"{wid}: ground in the water off its level {w.level_m:g} m by "
                      f"{float(np.max(np.abs(vals - w.level_m))):.2f} m")
    return c


def run(spec, m) -> list[Check]:
    ids = ("ground_grades", "cut_fill", "retaining_walls", "building_seats", "water_levels")
    if m.terrain is None:
        return [Check(i, "M13 (no terrain: nothing to check)") for i in ids]
    with G.canonical():
        return [check_grades(m), check_cut_fill(m), check_walls(m), check_seats(m),
                check_water(m)]


def stats(m) -> dict:
    t = m.terrain
    if t is None:
        return {}
    walls = [s for s in m.structures if s.kind == "retaining_wall"]
    bases = [b for b in m.buildings if b.base_m is not None]
    return {**t.stats, "retaining_walls": len(walls),
            "highest_wall_m": max((w.z1_m for w in walls), default=0.0),
            "bored_tunnels": sum(1 for u in m.tunnels if u.kind == "bored"),
            "highest_plinth_m": round(max((b.base_m - b.plinth_m for b in bases),
                                          default=0.0), 2),
            "slope_greens": sum(1 for o in m.open_spaces if o.attrs.get("slope"))}
