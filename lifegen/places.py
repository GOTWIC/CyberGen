"""LG4: life at places (scope 6.4): the slots people use, the places by their hours, gangs on
their turf and police patrols. Called by `plan.build_plan` (the plan's `places`, `gangs`,
`police`; each tile file's `slots` and `places`).

- **Slots** (`slots`): M6's benches, bus shelters, kiosks, vending machines and food stalls,
  M11's taxi stands, a club's queue and a bar's smokers at its door, a gang's spots: each a
  Smart Object in the runtime with its use points (`presets.SLOT_KINDS`: the points in the
  object's frame and the way each user faces; a bench's sitters away from its back, a bus
  stop's toward its road, a taxi stand's toward its curb, a kiosk's, vending machine's or
  stall's toward its counter, a queue's toward its door, a gang's ring toward its middle),
  its walkway (the nearest walkable one within `SLOT_REACH_M`, the one people leave to use it
  and come back to), how long a user stays, and per hour band how many of its points are in
  use (`use`: the kind's share by band, less where its walkway is quieter than
  `SLOT_REF_PER_M`; a queue's and smokers' by their place's open hours; a gang spot's its
  turf's loiterers). Points in a building's footprint are left out (a slot left with none is
  dropped, said so).
- **Places** (`places`): every AG3 shop door (a unit's use) with its hours (M11's POI's own
  where the door is a POI's unit, else `PLACE_KINDS` by use), open per hour, how busy by band
  (bars fill at night), a visit's length and its chance; its occupancy by band (people inside
  on a visit). The door's rates (its people out of and into it) follow the hours: none while
  closed, its `busy` while open, the district's other doors taking up what it loses
  (`apply_hours`, so every district keeps M11's people).
- **Gangs** (`gangs`): per gang turf (M11's territories of a gang faction) its walkways (their
  middle in the turf), the gang members its segments' M11 densities put on them per band
  (walking: `1 - GANG["loiter"]`; the rest at the turf's spots), its spots (hideout doors and
  the busiest corners), the faction's colors (`colors`: its own first).
- **Police** (`police`): per district its police (M11's) split into pairs on foot on its patrol
  walkways (the police field at least `POLICE["patrol_min"]`, weighted by the field squared)
  and patrol cars on its main lanes (`car_share`, `per_car`), its precinct's station doors;
  the patrol cars' model and livery.
- **Roles** (`reserve`): how many of the crowd's pool are kept for gang members and police
  (their looks), and of the traffic's pool for patrol cars: the most any tile wants within
  the live radius (at any hour band), with a margin, capped by a share of the pool.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict

from . import presets as P

TILE_M = 256.0


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def _u(*parts) -> float:
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big") / 2.0 ** 64


def _length(line) -> float:
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(line, line[1:]))


def _mid(line) -> tuple[float, float]:
    L = _length(line)
    if L <= 0.0:
        return float(line[0][0]), float(line[0][1])
    half, run = L / 2.0, 0.0
    for a, b in zip(line, line[1:]):
        d = math.dist(a[:2], b[:2])
        if run + d >= half and d > 0.0:
            t = (half - run) / d
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        run += d
    return float(line[-1][0]), float(line[-1][1])


def _tile(x: float, y: float) -> str:
    return f"t{math.floor(x / TILE_M):+03d}{math.floor(y / TILE_M):+03d}"


def _nearest_on(line, x: float, y: float) -> tuple[float, float, float, float, float]:
    """The point of a polyline nearest (x, y): its x, y, distance, and the line's unit
    direction there."""
    best = None
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 <= 0.0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
        px, py = a[0] + dx * t, a[1] + dy * t
        d = math.hypot(px - x, py - y)
        L = math.sqrt(L2) or 1.0
        if best is None or d < best[2]:
            best = (px, py, d, dx / L, dy / L)
    return best if best is not None else (x, y, 1e9, 1.0, 0.0)


def band_hours(b: int) -> range:
    _, a, e = P.HOUR_BANDS[b]
    return range(a, e)


def open_hours(hours) -> list[int]:
    """Per hour 1 while open: from <= h < to, past midnight when to < from, always on 0, 24."""
    a, b = int(hours[0]) % 25, int(hours[1]) % 25
    out = []
    for h in range(P.HOURS):
        if a == b or (a == 0 and b >= 24):
            out.append(1)
        elif a < b:
            out.append(1 if a <= h < b else 0)
        else:
            out.append(1 if h >= a or h < b else 0)
    return out


def open_share(opened: list[int]) -> list[float]:
    """Per hour band the share of its hours open."""
    return [_r(sum(opened[h] for h in band_hours(b)) / len(band_hours(b)), 4)
            for b in range(len(P.BANDS))]


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

class Field:
    """A gameplay field raster (M11's `fields`, rows from the south)."""

    def __init__(self, f: dict | None):
        self.f = f

    def at(self, x: float, y: float) -> float:
        f = self.f
        if not f:
            return 0.0
        i = int(math.floor((x - f["origin"][0]) / f["cell_m"]))
        j = int(math.floor((y - f["origin"][1]) / f["cell_m"]))
        i = min(max(i, 0), f["nx"] - 1)
        j = min(max(j, 0), f["ny"] - 1)
        return float(f["values"][j * f["nx"] + i])


def field_of(model: dict, kind: str) -> Field:
    return Field(next((f for f in model.get("fields", []) if f.get("kind") == kind), None))


class WalkIndex:
    """The walkable walkways (`ACCESS_KINDS`, the ground level and every deck) in plan, for
    the walkway nearest a point."""

    def __init__(self, walks: list[dict]):
        import shapely
        self.walks = [w for w in walks if w.get("kind") in P.ACCESS_KINDS and
                      len(w.get("line") or []) >= 2 and _length(w["line"]) > 0.5]
        self.geoms = [shapely.LineString([(p[0], p[1]) for p in w["line"]]) for w in self.walks]
        self.tree = shapely.STRtree(self.geoms) if self.geoms else None

    def nearest(self, x: float, y: float, reach: float, level: int | None = None):
        """(walkway, distance, nearest x, y, direction) of the nearest within reach (ties by
        id), else None."""
        import shapely
        if self.tree is None:
            return None
        hits = self.tree.query(shapely.Point(x, y).buffer(reach))
        best = None
        for k in sorted(int(h) for h in hits):
            w = self.walks[k]
            if level is not None and int(w.get("level") or 0) != level:
                continue
            px, py, d, ux, uy = _nearest_on(w["line"], x, y)
            if d <= reach and (best is None or (d, w["id"]) < (best[1], best[0]["id"])):
                best = (w, d, px, py, ux, uy)
        return best


class Footprints:
    """Building footprints (ground masses, in plan) a slot's point must keep out of."""

    def __init__(self, model: dict):
        import shapely
        polys = []
        for b in model.get("buildings", []):
            fp = b.get("footprint") or {}
            ext = fp.get("exterior") or []
            if len(ext) >= 3 and not (b.get("attrs") or {}).get("deck"):
                try:
                    p = shapely.Polygon(ext, fp.get("holes") or [])
                    if p.is_valid and p.area > 0.5:
                        polys.append(p)
                except Exception:                                    # noqa: BLE001
                    continue
        self.polys = polys
        self.tree = shapely.STRtree(polys) if polys else None

    def inside(self, x: float, y: float) -> bool:
        import shapely
        if self.tree is None:
            return False
        pt = shapely.Point(x, y)
        return any(self.polys[int(k)].contains(pt) for k in self.tree.query(pt))


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------

def frame_points(kind: str, x: float, y: float, z: float, yaw: float,
                 mirror: bool = False) -> list[list[float]]:
    """A slot kind's use points (`SLOT_KINDS`) for an object at (x, y, z) facing `yaw`
    (degrees counterclockwise from east): [x, y, z, the way its user faces]; `mirror` turns the
    layout over its x axis (a bus stop whose road is on its back's side)."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    out = []
    for lx, ly, dy in P.SLOT_KINDS[kind]["points"]:
        if mirror:
            ly, dy = -ly, -dy
        out.append([_r(x + lx * c - ly * s, 3), _r(y + lx * s + ly * c, 3), _r(z, 3),
                    _r(((yaw + dy + 180.0) % 360.0) - 180.0, 2)])
    return out


def _facing_ok(kind: str, obj: tuple[float, float, float], pts: list[list[float]],
               center: tuple[float, float] | None = None) -> bool:
    """The rule a slot's points face by: a bench's sitters away from its back (the object's
    yaw less 90 degrees), a ring toward its middle, the others toward their object (within 75
    degrees: a queue's back faces its front), a bus stop's and taxi stand's any way (toward
    their road, which the check cannot see), smokers beside a door any way (out from its wall
    or at each other)."""
    ox, oy, oyaw = obj
    for x, y, _, f in pts:
        if kind == "bench":
            d = abs(((f - (oyaw - 90.0)) + 180.0) % 360.0 - 180.0)
            if d > 1.0:
                return False
            continue
        if kind in ("bus_stop", "taxi_stand", "smoke"):
            if not math.isfinite(f):
                return False
            continue
        tx, ty = center if center is not None else (ox, oy)
        if math.hypot(tx - x, ty - y) < 0.05:
            continue
        want = math.degrees(math.atan2(ty - y, tx - x))
        if abs(((f - want) + 180.0) % 360.0 - 180.0) > 75.0:
            return False
    return True


def slot_use(kind: str, cap: int, per_m: list[float]) -> list[float]:
    """A slot's users per hour band: its kind's share of its points, less where its walkway
    has fewer than `SLOT_REF_PER_M` people a meter (never under `SLOT_USE_MIN` of it)."""
    sh = P.SLOT_KINDS[kind]["use"]
    out = []
    for b in range(len(P.BANDS)):
        f = min(1.0, max(P.SLOT_USE_MIN, per_m[b] / P.SLOT_REF_PER_M))
        out.append(_r(cap * sh[b] * f, 3))
    return out


def _side_from(seg: dict | None, x: float, y: float) -> tuple[float, float] | None:
    """The unit direction from (x, y) toward a road segment's centerline."""
    cl = (seg or {}).get("centerline") or []
    if len(cl) < 2:
        return None
    px, py, d, _, _ = _nearest_on(cl, x, y)
    if d < 1e-6:
        return None
    return (px - x) / d, (py - y) / d


def make_slots(model: dict, wi: WalkIndex, fp: Footprints, walk_rows: dict,
               places: list[dict]) -> tuple[list[dict], dict]:
    """Every slot but the gangs' (`gang_spots`): props, taxi stands, bars' and clubs' doors.
    Returns the slots (unhashed, without their tile) and what was left out."""
    segs = {s["id"]: s for s in model.get("road_segments", [])}
    walks = {w["id"]: w for w in model.get("walkways", [])}
    left = {"no_walkway": 0, "in_building": 0, "points_dropped": 0}
    out = []

    def per_m(wid: str) -> list[float]:
        r = walk_rows.get(wid)
        if not r or r["length_m"] <= 0.0:
            return [0.0] * 5
        return [v / r["length_m"] for v in r["people"]]

    def finish(rec: dict, kind: str, obj, center=None):
        pts = rec["points"]
        keep = [p for p in pts if not fp.inside(p[0], p[1])]
        left["points_dropped"] += len(pts) - len(keep)
        if not keep:
            left["in_building"] += 1
            return
        # (its users per band at most its points kept)
        k = len(keep) / len(pts)
        rec["use"] = [_r(min(len(keep), u * k), 3) for u in rec["use"]]
        rec["points"] = keep
        rec["capacity"] = len(keep)
        rec["dwell_s"] = list(P.SLOT_KINDS[kind]["dwell_s"])
        rec["behavior"] = P.SLOT_KINDS[kind]["behavior"]
        rec["anim"] = P.SLOT_KINDS[kind]["anim"]
        rec["_obj"] = obj
        rec["_center"] = center
        out.append(rec)

    for p in model.get("props", []):
        kind = P.SLOT_PROPS.get(p.get("type"))
        if kind is None:
            continue
        x, y = float(p["position"][0]), float(p["position"][1])
        z = float(p["position"][2]) if len(p["position"]) > 2 else 0.0
        yaw = float(p.get("yaw_deg") or 0.0)
        lvl = int(p.get("level") or 0)
        mirror = False
        if kind == "bus_stop":
            # (its users face its road: the segment of the sidewalk it stands on)
            stop = (p.get("attrs") or {}).get("stop") or ""
            w = walks.get(stop.rsplit(".", 1)[0]) if stop else None
            seg = segs.get(((w or {}).get("attrs") or {}).get("segment"))
            to = _side_from(seg, x, y)
            if to is not None:
                fx, fy = math.cos(math.radians(yaw - 90.0)), math.sin(math.radians(yaw - 90.0))
                mirror = fx * to[0] + fy * to[1] < 0.0
        pts = frame_points(kind, x, y, z, yaw, mirror)
        hit = wi.nearest(pts[0][0], pts[0][1], P.SLOT_REACH_M, lvl)
        if hit is None:
            left["no_walkway"] += 1
            continue
        w = hit[0]
        did = p["id"].split(".")[0] if p["id"].startswith("d") else None
        cap = len(pts)
        finish({"id": f"slot.{p['id']}", "owner_id": p["id"], "kind": kind,
                "district_id": did, "pos": [_r(x, 2), _r(y, 2), _r(z, 2)],
                "yaw_deg": _r(yaw, 2), "level": lvl, "walkway_id": w["id"],
                "reach_m": _r(hit[1], 2), "points": pts, "role": "crowd",
                "use": slot_use(kind, cap, per_m(w["id"]))}, kind, (x, y, yaw))
    for t in model.get("travel_points", []):
        if t.get("kind") != "taxi_stand":
            continue
        a = t.get("access") or {}
        pos = a.get("position") or t["position"]
        x, y = float(pos[0]), float(pos[1])
        w = walks.get(a.get("walkway_id"))
        if w is None:
            hit = wi.nearest(x, y, P.SLOT_REACH_M)
            if hit is None:
                left["no_walkway"] += 1
                continue
            w = hit[0]
        sx, sy, d, ux, uy = _nearest_on(w["line"], x, y)
        yaw = math.degrees(math.atan2(uy, ux))
        # (its queue on its sidewalk, along it, facing its curb)
        curb = a.get("curb")
        if d > 0.5 and curb:
            # (the access point's walkway may run off it: the queue where it is nearest)
            x, y, d = sx, sy, 0.0
        face = yaw - 90.0
        if curb:
            fx, fy = math.cos(math.radians(face)), math.sin(math.radians(face))
            if fx * (curb[0] - x) + fy * (curb[1] - y) < 0.0:
                face = yaw + 90.0
        pts = [[p[0], p[1], 0.0, _r(((face + 180.0) % 360.0) - 180.0, 2)]
               for p in frame_points("taxi_stand", x, y, 0.0, yaw)]
        finish({"id": f"slot.{t['id']}", "owner_id": t["id"], "kind": "taxi_stand",
                "district_id": t.get("district_id"), "pos": [_r(x, 2), _r(y, 2), 0.0],
                "yaw_deg": _r(face, 2), "level": 0, "walkway_id": w["id"],
                "reach_m": _r(d, 2), "points": pts, "role": "crowd",
                "use": slot_use("taxi_stand", len(pts), per_m(w["id"]))},
               "taxi_stand", (x, y, face))
    # (a club's queue and a bar's smokers at its door, by its hours)
    for pl in places:
        kind = pl.get("slot")
        if not kind:
            continue
        x, y, z = pl["pos"]
        yaw = pl["yaw_deg"]
        pts = frame_points(kind, x, y, z, yaw)
        cap = len(pts)
        share = open_share(pl["open"])
        use = [_r(cap * P.SLOT_KINDS[kind]["use"][b] * share[b] * pl["busy"][b], 3)
               for b in range(len(P.BANDS))]
        finish({"id": f"slot.{pl['id'][len('place.'):]}.{kind}", "owner_id": pl["id"],
                "kind": kind, "district_id": pl["district_id"],
                "pos": [_r(x, 2), _r(y, 2), _r(z, 2)], "yaw_deg": _r(yaw, 2),
                "level": pl.get("level", 0), "walkway_id": pl["walkway_id"], "reach_m": 0.0,
                "points": pts, "role": "crowd", "place_id": pl["id"], "use": use},
               kind, (x, y, yaw), (x, y) if kind == "bar_queue" else None)
    return out, left


# ---------------------------------------------------------------------------
# Places by their hours
# ---------------------------------------------------------------------------

def make_places(model: dict, spawns: list[dict]) -> list[dict]:
    """Every AG3 shop door (spawn points of sub `shop.<use>`, not lobbies) as a place: its
    hours (its POI's where the door is a POI's unit), open per hour, busy by band, a visit's
    length and chance, its slot kind (a club's queue, a share of bars' smokers)."""
    poi_at = {}
    for poi in model.get("pois", []):
        if poi.get("building_id") is not None and poi.get("unit_index") is not None:
            poi_at[(poi["building_id"], int(poi["unit_index"]))] = poi
    out = []
    for s in spawns:
        sub = s.get("sub") or ""
        if s.get("kind") != "door" or not sub.startswith("shop.") or sub == "shop.lobby":
            continue
        use = sub[len("shop."):]
        unit = None
        tail = s["id"].rsplit(".", 1)[-1]
        if tail.startswith("u") and tail[1:].isdigit():
            unit = int(tail[1:])
        poi = poi_at.get((s["owner_id"], unit)) if unit is not None else None
        kind = (poi or {}).get("sub") or use
        pk = P.PLACE_KINDS.get(kind) or P.PLACE_KINDS.get(use) or P.PLACE_DEFAULT
        hours = (poi or {}).get("hours")
        if hours is None:
            # (a kind with several hours, a food place's as M11 draws its POIs': one by hash)
            hs = pk.get("hours_any")
            hours = hs[int(_u("lg4.hours", s["id"]) * len(hs))] if hs else pk["hours"]
        hours = list(hours)
        opened = open_hours(hours)
        slot = pk.get("slot")
        if slot == "smoke" and poi is None and _u("lg4.smoke", s["id"]) >= P.BAR_SLOT_SHARE:
            slot = None
        out.append({"id": f"place.{s['id'][len('spawn.'):]}", "spawn_id": s["id"],
                    "building_id": s["owner_id"], "poi_id": (poi or {}).get("id"),
                    "name": (poi or {}).get("name"), "kind": kind, "use": use,
                    "district_id": s.get("district_id"), "pos": list(s["pos"]),
                    "yaw_deg": float(s.get("yaw_deg") or 0.0), "level": int(s.get("level") or 0),
                    "walkway_id": s["walkway_id"], "hours": [int(hours[0]), int(hours[1])],
                    "open": opened, "busy": list(pk["busy"]), "dwell_s": list(pk["dwell_s"]),
                    "visit": [_r(P.VISIT_P * pk["busy"][b] * open_share(opened)[b], 4)
                              for b in range(len(P.BANDS))],
                    "slot": slot})
    return out


def apply_hours(spawns: list[dict], places: list[dict]) -> None:
    """The doors' rates by their places' hours: a place's door sends out (and takes in) its
    rate times its `busy` while open, none while closed; the district's other doors (and open
    places) take up what it loses, so each district keeps its people every hour. Each place's
    occupancy by band (people inside on a visit) from its door's rate and visit length."""
    pl_of = {pl["spawn_id"]: pl for pl in places}
    before = defaultdict(lambda: [0.0] * P.HOURS)
    after = defaultdict(lambda: [0.0] * P.HOURS)
    for s in spawns:
        for h in range(P.HOURS):
            before[s["district_id"]][h] += s["rates"][h]
        pl = pl_of.get(s["id"])
        if pl is not None:
            s["rates"] = [s["rates"][h] * pl["open"][h] * pl["busy"][P.band_of(h)]
                          for h in range(P.HOURS)]
        for h in range(P.HOURS):
            after[s["district_id"]][h] += s["rates"][h]
    for s in spawns:
        d = s["district_id"]
        s["rates"] = [_r(s["rates"][h] * (before[d][h] / after[d][h]) if after[d][h] > 0.0
                         else s["rates"][h], 3) for h in range(P.HOURS)]
    rate = {s["id"]: s["rates"] for s in spawns}
    for pl in places:
        r = rate.get(pl["spawn_id"]) or [0.0] * P.HOURS
        mean = sum(pl["dwell_s"]) / 2.0
        pl["occupancy"] = [_r(sum(r[h] for h in band_hours(b)) / len(band_hours(b)) *
                              pl["busy"][b] * mean / 3600.0, 3) for b in range(len(P.BANDS))]


# ---------------------------------------------------------------------------
# Gangs on their turf
# ---------------------------------------------------------------------------

def faction_colors(color: str) -> list[str]:
    """A gang's colors (`OUTFIT_COLORS` of them): its own, then its shades and dark neutrals."""
    def shade(c, k):
        rgb = [min(255, int(round(int(c[1 + 2 * j:3 + 2 * j], 16) * k))) for j in range(3)]
        return "#" + "".join(f"{v:02x}" for v in rgb)
    out = []
    for c in [color, shade(color, 0.7), shade(color, 1.25), shade(color, 0.5),
              *P.GANG_NEUTRALS, color, shade(color, 0.85), P.GANG_NEUTRALS[0],
              shade(color, 0.6)]:
        out.append(c)
    return out[:P.OUTFIT_COLORS]


def gang_turfs(model: dict) -> list[dict]:
    """M11's territories held by a gang faction, with their shapes."""
    import shapely
    fac = {f["id"]: f for f in model.get("factions", [])}
    out = []
    for z in sorted(model.get("zones", []), key=lambda z: z["id"]):
        f = fac.get(z.get("faction_id"))
        if z.get("kind") != "territory" or f is None or f.get("kind") != "gang":
            continue
        polys = [shapely.Polygon(p["exterior"], p.get("holes") or [])
                 for p in z.get("polygons") or [] if len(p.get("exterior") or []) >= 3]
        if not polys:
            continue
        out.append({"id": z["id"], "faction": f, "district_id": z["district_id"],
                    "name": z.get("name"), "shape": shapely.union_all(polys)})
    return out


def gang_walks(model: dict, filled: dict, rows: list[dict], turfs: list[dict]) -> dict:
    """Each walkway row's turf (its middle in a gang turf) and gang members walking on it per
    band (`gang`: its segment's M11 gang members on its walkways in the turf by length, times
    the district's busy, the loitering share taken out); returns per turf its members by band
    (walking and loitering) and what was left out."""
    import shapely
    seg_len = {s["id"]: float((s.get("attrs") or {}).get("length_m") or
                              _length(s.get("centerline") or []))
               for s in model.get("road_segments", [])}
    dens = {}
    for row in model.get("densities", []):
        d = row.get("district_id")
        if d in filled["districts"]:
            dens[row["segment_id"]] = (d, [float(v) * seg_len.get(row["segment_id"], 0.0) / 100.0
                                           * filled["districts"][d]["busy"]
                                           for v in (row.get("gang_per_100m") or [0.0] * 5)])
    walks = {w["id"]: w for w in model.get("walkways", [])}
    on_seg = defaultdict(float)
    for w in model.get("walkways", []):
        s = (w.get("attrs") or {}).get("segment")
        if s in dens:
            on_seg[s] += _length(w["line"])
    loit = P.GANG["loiter"]
    by_turf = {t["id"]: {"walk": [0.0] * 5, "loiter": [0.0] * 5, "walkways": 0} for t in turfs}
    left = {"members": [0.0] * 5, "walkways": 0}
    placed = defaultdict(lambda: [0.0] * 5)
    for r in rows:
        w = walks.get(r["id"]) or {}
        mx, my = _mid(w.get("line") or [[0, 0]])
        turf = None
        if r["kind"] in P.ACCESS_KINDS or r["kind"] in ("crossing", "crosswalk"):
            for t in turfs:
                if shapely.contains_xy(t["shape"], mx, my):
                    turf = t["id"]
                    break
        r["turf"] = turf
        r["gang"] = None
        s = (w.get("attrs") or {}).get("segment")
        if turf is not None:
            by_turf[turf]["walkways"] += 1
        if s not in dens or on_seg[s] <= 0.0:
            continue
        band = dens[s][1]
        share = [v * _length(w["line"]) / on_seg[s] for v in band]
        if turf is None:
            if any(v > 0 for v in share):
                left["walkways"] += 1
                for i in range(5):
                    left["members"][i] += share[i]
            continue
        for i in range(5):
            placed[turf][i] += share[i]
        r["gang"] = [_r(v * (1.0 - loit[i]), 4) for i, v in enumerate(share)]
    for tid, v in placed.items():
        for i in range(5):
            by_turf[tid]["walk"][i] += v[i] * (1.0 - loit[i])
            by_turf[tid]["loiter"][i] += v[i] * loit[i]
    # (a segment with gang members and no walkway: said so)
    for s, (d, band) in dens.items():
        if on_seg[s] <= 0.0:
            for i in range(5):
                left["members"][i] += band[i]
    left["members"] = [_r(v, 2) for v in left["members"]]
    return {"turfs": by_turf, "left": left}


def gang_spots(model: dict, turfs: list[dict], members: dict, rows: dict, wi: WalkIndex,
               fp: Footprints) -> list[dict]:
    """Each gang turf's spots: its hideouts' doors and its busiest corners (sidewalk ends near
    a junction in the turf, on the side away from the road), one per `GANG["per_spot"]`
    loiterers at the late band, at least one; their use the turf's loiterers shared out, at
    most their points."""
    import shapely
    segs = {s["id"]: s for s in model.get("road_segments", [])}
    nodes = {n["id"]: n for n in model.get("road_nodes", [])}
    walks = {w["id"]: w for w in model.get("walkways", [])}
    out = []
    late = len(P.BANDS) - 1
    for t in turfs:
        m = members["turfs"][t["id"]]
        loit = m["loiter"]
        want = max(1, min(P.GANG["spots_max"], int(round(max(loit) / P.GANG["per_spot"]))))
        if max(loit) <= 0.0 and m["walkways"] == 0:
            continue
        cands = []
        for poi in model.get("pois", []):
            if poi.get("kind") != "hideout":
                continue
            if poi.get("zone_id") != t["id"] and poi.get("faction_id") != t["faction"]["id"]:
                continue
            e = (poi.get("entrances") or [{}])[0]
            pos = e.get("position") or poi["position"]
            if not shapely.contains_xy(t["shape"], pos[0], pos[1]):
                continue
            w = walks.get(e.get("walkway_id"))
            if w is None:
                continue
            px, py, d, _, _ = _nearest_on(w["line"], pos[0], pos[1])
            # (in front of its door, toward its walkway)
            k = min(1.8, d) / d if d > 1e-6 else 0.0
            cx, cy = pos[0] + (px - pos[0]) * k, pos[1] + (py - pos[1]) * k
            cands.append((-1e9, f"hideout.{poi['id']}", cx, cy, w["id"], poi["id"]))
        for j in sorted(model.get("junctions", []), key=lambda j: j["id"]):
            n = nodes.get(j.get("node_id"))
            if n is None:
                continue
            nx, ny = n["position"][0], n["position"][1]
            if not shapely.contains_xy(t["shape"], nx, ny):
                continue
            hit = None
            near = wi.tree.query(shapely.Point(nx, ny).buffer(P.GANG["corner_m"])) \
                if wi.tree is not None else []
            for k in sorted(int(h) for h in near):
                w = wi.walks[k]
                if w["kind"] != "sidewalk":
                    continue
                for end, nxt in ((w["line"][0], w["line"][1]), (w["line"][-1], w["line"][-2])):
                    d = math.hypot(end[0] - nx, end[1] - ny)
                    if d <= P.GANG["corner_m"] and (hit is None or (d, w["id"]) < hit[0]):
                        hit = ((d, w["id"]), w, end, nxt)
            if hit is None:
                continue
            _, w, end, nxt = hit
            L = math.dist(end[:2], nxt[:2]) or 1.0
            ux, uy = (nxt[0] - end[0]) / L, (nxt[1] - end[1]) / L
            run = min(2.5, 0.5 * L)
            cx, cy = end[0] + ux * run, end[1] + uy * run
            to = _side_from(segs.get((w.get("attrs") or {}).get("segment")), cx, cy)
            off = 0.3 * float(w.get("width_m") or 2.0)
            if to is not None:
                cx, cy = cx - to[0] * off, cy - to[1] * off
            r = rows.get(w["id"]) or {}
            g = (r.get("gang") or [0.0] * 5)[late]
            if r.get("turf") != t["id"]:
                continue
            cands.append((-g, f"corner.{j['id']}", cx, cy, w["id"], None))
        cands.sort(key=lambda c: (c[0], _u("lg4.spot", c[1])))
        chosen = []
        for c in cands:
            if len(chosen) >= want:
                break
            if any(math.hypot(c[2] - o[2], c[3] - o[3]) < 12.0 for o in chosen):
                continue
            pts = frame_points("gang_spot", c[2], c[3], 0.0, 0.0)
            pts = [[p[0], p[1], p[2], _r(math.degrees(math.atan2(c[3] - p[1], c[2] - p[0])), 2)]
                   for p in pts]
            if any(fp.inside(p[0], p[1]) for p in pts):
                continue
            chosen.append((*c, pts))
        n = max(1, len(chosen))
        for c in chosen:
            pts = c[6]
            use = [_r(min(len(pts), loit[b] / n), 3) for b in range(len(P.BANDS))]
            out.append({"id": f"slot.{t['id']}.{c[1]}", "owner_id": c[5] or t["id"],
                        "kind": "gang_spot", "district_id": t["district_id"],
                        "pos": [_r(c[2], 2), _r(c[3], 2), 0.0], "yaw_deg": 0.0, "level": 0,
                        "walkway_id": c[4], "reach_m": 0.0, "points": pts, "capacity": len(pts),
                        "dwell_s": list(P.SLOT_KINDS["gang_spot"]["dwell_s"]),
                        "behavior": "talk", "anim": "talk", "role": "gang",
                        "turf_id": t["id"], "faction_id": t["faction"]["id"], "use": use,
                        "_obj": (c[2], c[3], 0.0), "_center": (c[2], c[3])})
    return out


# ---------------------------------------------------------------------------
# Police patrols
# ---------------------------------------------------------------------------

def police_plan(model: dict, filled: dict, rows: list[dict], drows: list[dict],
                spawns: list[dict]) -> dict:
    """Per district its police (M11's) on foot on its patrol walkways and in patrol cars on
    its main lanes, by the police field; each walk row's `patrol`, `field` and `police` (pairs'
    people per band), each drive row's `police` (patrol cars per band); the precincts and their
    station doors."""
    po = P.POLICE
    fld = field_of(model, "police")
    seg_len = {s["id"]: float((s.get("attrs") or {}).get("length_m") or
                              _length(s.get("centerline") or []))
               for s in model.get("road_segments", [])}
    total = defaultdict(lambda: [0.0] * 5)
    for row in model.get("densities", []):
        d = row.get("district_id")
        if d in filled["districts"]:
            for i, v in enumerate(row.get("police_per_100m") or [0.0] * 5):
                total[d][i] += float(v) * seg_len.get(row["segment_id"], 0.0) / 100.0
    walks = {w["id"]: w for w in model.get("walkways", [])}
    wsum = defaultdict(float)
    for r in rows:
        w = walks.get(r["id"]) or {}
        mx, my = _mid(w.get("line") or [[0, 0]])
        f = fld.at(mx, my)
        r["field"] = _r(f, 3)
        # (a patrol walks its walkways and the crossings and crosswalks between them; its
        # people are put on the walkable ones)
        r["patrol"] = bool((r["kind"] in P.ACCESS_KINDS or r["kind"] in ("crossing",
                                                                          "crosswalk"))
                           and r["kind"] != "skybridge" and f >= po["patrol_min"]
                           and r["district_id"] in total and r["level"] == 0)
        r["police"] = None
        if r["patrol"] and r["kind"] in P.ACCESS_KINDS:
            wsum[r["district_id"]] += r["length_m"] * f * f
    lanes = {ln["id"]: ln for ln in model.get("lanes", [])}
    lsum = defaultdict(float)
    for r in drows:
        ln = lanes.get(r["id"]) or {}
        mx, my = _mid(ln.get("centerline") or [[0, 0]])
        f = fld.at(mx, my)
        r["_field"] = f
        r["police"] = None
        if r["main"] and r["district_id"] in total and r["road_class"] != "highway":
            lsum[r["district_id"]] += r["length_m"] * f * f
    left = {"foot": [0.0] * 5, "cars": [0.0] * 5}
    foot = {d: [v * (1.0 - po["car_share"]) for v in t] for d, t in total.items()}
    cars = {d: [v * po["car_share"] / po["per_car"] for v in t] for d, t in total.items()}
    for r in rows:
        if r["patrol"] and r["kind"] in P.ACCESS_KINDS and wsum[r["district_id"]] > 0.0:
            k = r["length_m"] * r["field"] ** 2 / wsum[r["district_id"]]
            r["police"] = [_r(v * k, 4) for v in foot[r["district_id"]]]
    for d, v in foot.items():
        if wsum[d] <= 0.0:
            for i in range(5):
                left["foot"][i] += v[i]
    for r in drows:
        d = r["district_id"]
        f = r.pop("_field")
        if r["main"] and d in total and r["road_class"] != "highway" and lsum[d] > 0.0:
            r["police"] = [_r(v * r["length_m"] * f * f / lsum[d], 4) for v in cars[d]]
    for d, v in cars.items():
        if lsum[d] <= 0.0:
            for i in range(5):
                left["cars"][i] += v[i]
    by_owner = defaultdict(list)
    for s in spawns:
        if s["kind"] == "door":
            by_owner[s["owner_id"]].append(s["id"])
    precincts = []
    for z in sorted(model.get("zones", []), key=lambda z: z["id"]):
        if z.get("kind") != "police":
            continue
        bid = (z.get("attrs") or {}).get("station_building_id")
        d = z["district_id"]
        precincts.append({"id": z["id"], "name": z.get("name"), "district_id": d,
                          "level": float(z.get("level") or 0.0),
                          "station_building_id": bid,
                          "station_doors": sorted(by_owner.get(bid) or []),
                          "police": [_r(v, 2) for v in total.get(d, [0.0] * 5)],
                          "foot": [_r(v, 2) for v in foot.get(d, [0.0] * 5)],
                          "cars": [_r(v, 2) for v in cars.get(d, [0.0] * 5)]})
    return {"precincts": precincts, "total": {d: [_r(x, 2) for x in v]
                                               for d, v in sorted(total.items())},
            "left": {k: [_r(x, 2) for x in v] for k, v in left.items()}}


# ---------------------------------------------------------------------------
# The preview
# ---------------------------------------------------------------------------

SLOT_COLORS = {"bench": "#3fd0ff", "bus_stop": "#7cff6b", "kiosk": "#ffd23f",
               "vending": "#ff9f3f", "stall": "#ff6b6b", "taxi_stand": "#f7f7a0",
               "bar_queue": "#ff3fb4", "smoke": "#c77dff", "gang_spot": "#ff2020"}


def preview_places(model: dict, slots: list[dict], places: list[dict], rows: list[dict],
                   turfs: list[dict], pol: dict, hour: int, path) -> str | None:
    """`preview_places.png`: the slots by kind, the gang turfs in their factions' colors with
    their spots, the patrol walkways by the police field and the stations; beside it the places
    open by hour per kind."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
    except ImportError:
        return None
    from pathlib import Path
    path = Path(path)
    walks = {w["id"]: w for w in model.get("walkways", [])}
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(17, 8), dpi=110,
                                 gridspec_kw={"width_ratios": [1.2, 1]})
    fig.patch.set_facecolor("#0c111a")
    for a in (ax, bx):
        a.set_facecolor("#0c111a")
        for sp in a.spines.values():
            sp.set_color("#3a4253")
        a.tick_params(colors="#9aa6bd")
    pl, pv = [], []
    for r in rows:
        if r.get("patrol"):
            w = walks.get(r["id"])
            if w:
                pl.append([(p[0], p[1]) for p in w["line"]])
                pv.append(r.get("field") or 0.0)
    if pl:
        lc = LineCollection(pl, array=pv, cmap="Blues", linewidths=0.6, alpha=0.8)
        lc.set_clim(0.0, 1.0)
        ax.add_collection(lc)
    for t in turfs:
        geoms = getattr(t["shape"], "geoms", [t["shape"]])
        for g in geoms:
            xs, ys = g.exterior.xy
            ax.fill(xs, ys, color=t["faction"]["color"], alpha=0.18, lw=0)
            ax.plot(xs, ys, color=t["faction"]["color"], lw=1.2)
    for d in model.get("districts", []):
        ring = (d.get("polygon") or {}).get("exterior") or []
        if ring:
            xs, ys = zip(*(ring + ring[:1]))
            ax.plot(xs, ys, color="#2c3443", lw=0.8)
    for k, col in SLOT_COLORS.items():
        pts = [s["pos"] for s in slots if s["kind"] == k]
        if pts:
            ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=6 if k != "gang_spot" else 14,
                       c=col, label=f"{k} {len(pts)}", lw=0)
    bld = {}
    for b in model.get("buildings", []):
        bld[b["id"]] = b
    for p in pol["precincts"]:
        b = bld.get(p.get("station_building_id"))
        ext = ((b or {}).get("footprint") or {}).get("exterior")
        if ext:
            cx = sum(q[0] for q in ext) / len(ext)
            cy = sum(q[1] for q in ext) / len(ext)
            ax.scatter([cx], [cy], marker="*", s=180, c="#5b8cff", edgecolors="white", lw=0.8)
    b = model.get("bounds") or [-1, -1, 1, 1]
    ax.set_xlim(b[0], b[2])
    ax.set_ylim(b[1], b[3])
    ax.set_aspect("equal")
    ax.legend(facecolor="#141a26", labelcolor="#e6ecf7", edgecolor="#3a4253", fontsize=8,
              loc="lower left", markerscale=2.5)
    ax.set_title("slots by kind, gang turfs, patrol walkways (blue by the police field), "
                 "stations", color="#e6ecf7", fontsize=10)
    by = defaultdict(lambda: [0] * P.HOURS)
    for p in places:
        for h in range(P.HOURS):
            by[p["kind"]][h] += p["open"][h]
    hrs = list(range(P.HOURS))
    for k in sorted(by, key=lambda k: -max(by[k])):
        n = sum(1 for p in places if p["kind"] == k)
        if n < 5:
            continue
        bx.plot(hrs, [v / n for v in by[k]], lw=1.8, label=f"{k} ({n})")
    bx.axvline(hour, color="#ff3fb4", lw=1.0, ls="--")
    bx.set_xlabel("hour", color="#9aa6bd")
    bx.set_ylabel("share open", color="#9aa6bd")
    bx.set_title("places open by hour (the crowd's hour dashed)", color="#e6ecf7", fontsize=10)
    bx.legend(facecolor="#141a26", labelcolor="#e6ecf7", edgecolor="#3a4253", fontsize=8)
    fig.tight_layout()
    tmp = path.with_suffix(".tmp.png")
    fig.savefig(tmp, facecolor=fig.get_facecolor())
    plt.close(fig)
    data = tmp.read_bytes()
    tmp.unlink()
    if path.is_file() and path.read_bytes() == data:
        return None
    path.write_bytes(data)
    return str(path)


# ---------------------------------------------------------------------------
# Roles in the pools
# ---------------------------------------------------------------------------

def most_near(values: dict[str, float], reach: float) -> float:
    """The most wanted within `reach` of any tile's middle (`values` per tile), the tiles
    within reach and half a tile's diagonal of it summed."""
    cen = {}
    for t in values:
        ix, iy = int(t[1:4]), int(t[4:7])
        cen[t] = ((ix + 0.5) * TILE_M, (iy + 0.5) * TILE_M)
    best = 0.0
    lim = reach + TILE_M / math.sqrt(2.0)
    for t, (x, y) in cen.items():
        s = sum(v for u, v in values.items() if math.dist(cen[u], (x, y)) <= lim)
        best = max(best, s)
    return best


def reserve(per_tile: dict[str, float], reach: float, pool: int, share: float) -> tuple[int, float]:
    """(slots kept, the most wanted near the view) for a role: the most wanted within `reach`
    of any tile times `ROLES["margin"]`, at least `ROLES["min"]` where any is wanted, at most
    `share` of the pool."""
    want = most_near(per_tile, reach)
    if want <= 0.0:
        return 0, 0.0
    n = int(math.ceil(want * P.ROLES["margin"]))
    return max(P.ROLES["min"], min(n, int(share * pool))), _r(want, 1)
