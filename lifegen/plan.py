"""`lifegen plan BUILD`: the life plan of a built city (scope sections 4.2, 7 and 8).

From the city model (read only) and the life spec:

- **People and vehicles by district and hour:** M11's densities (people, vehicles, gang
  members and police per 100 m and hour band, per road segment) times each segment's length,
  summed per district, shaped within each band by the district's day (`presets.DAY_SHAPE`,
  normalized so every band keeps M11's density) and its `busy` multiplier.
- **Spawn and sink points** (scope 6.3): every building entrance (M3, its walkway), station
  access (M5), garage and lot entrance (M11's parking) and taxi stand, with a rate per hour:
  the district's people on its streets turned over every `presets.TRIP_MIN` minutes, shared
  by the points' weights (`SPAWN_WEIGHT`).
- **Place slots** (scope 6.4): benches, bus stops, kiosks, vending machines, food stalls and
  taxi stands, each with its behavior and capacity, keyed `slot.<prop id>`.
- **The fleet** (decision 6): AG18's models by each district's weights (the parked cars'
  table).
- **The spike** (LG0): one district (default the one with the most buildings, the
  benchmark's walk) and a few cars on its lanes (LG3: its people only where the spec asks).
- **The crowd** (LG3, scope 6.3): every walkway's people per hour band (`crowd_walks`: a road
  segment's M11 people on its own walkways by length, the rest at the district's mean
  sidewalk density times `presets.OFFSTREET`), the signals' phases (`signals`, the ask
  `signal_phases` derived: `signals.json`), AG3's doors as the spawn points where the build
  has them (`door_points`), the pool of people the runtime simulates round the view
  (`crowd_plan`), checks (`crowd_checks`).
- **The traffic** (LG5, scope 6.5): every lane's cars per hour band (`traffic_lanes`: a road
  segment's M11 vehicles on its lanes by length, none off the lane graph's largest strongly
  connected part), the signal each lane's end stops at and where (`lane_signals`: LG3's derived
  phases, short of the crosswalk), the pool of cars the runtime simulates round the view, its
  slots by the districts' fleets and their paints (`traffic_plan`), checks
  (`traffic_checks`). LG0's spike cars go (`presets.SPIKE["cars"]` 0).
- **Life at places** (LG4, scope 6.4, `places.py`): the shop doors as places by their hours
  (their doors' rates by them), the slots people use (props, taxi stands, a club's queue, a
  bar's smokers, a gang's spots) with their use points, walkways and users per band, the gangs
  on their turfs, the police on foot and in patrol cars by the police field, the pools' slots
  kept for gang members, police and patrol cars (`role_counts`, `assign_roles`), checks
  (`places_checks`), `preview_places.png`.
- **Transit** (LG6, scope 6.6, `transit.py`): every line's timetable (its stops, runs by the
  mode's speeds and the track's curves, dwells, the cycle sampled, the trains per hour band,
  the people boarding and leaving a train at each stop), `timetables.json`, checks
  (`timetables`, `transit_stops`, `transit_boarding`, `transit_budget`),
  `preview_transit.png`; a layer 4 entry per train (`train.<line id>.<n>`).
- **Air and water** (LG7, scope 6.7, `airwater.py`): routes for flying cars (between M3's pads
  and round circuits over the avenues and highways, on layers by heading), drones, police and
  media fliers, aircraft and a spaceport's shuttles, boats, water taxis, ferries and ships, each
  a closed path run to a timetable; the pads and piers (the ask `piers`, derived);
  `airwater.json`, checks (`air_lanes`, `air_pads`, `water_lanes`, `airwater_timing`,
  `airwater_budget`), `preview_airwater.png`; a layer 4 entry per route
  (`air.<kind>.<...>`, `water.<kind>.<...>`).
- **The asks of citygen** (`asks.py`) and their state.
- **Checks** (scope 8, the ones LG0 can make): spawns on the graphs, spawns reaching each
  other, densities kept, slots placed, the spike within the budgets.

Outputs (written only when their bytes change): `life_plan.json`, `spawns/<tile>.json` (LG3:
with its walkways' people; LG5: its lanes' cars), `signals.json`, `life_report.json`, `life_report.txt`,
`unreal_contribution.life.json`, `preview_crowds.png`; LG4 `preview_places.png`; LG6
`timetables.json`, `preview_transit.png`; LG7 `airwater.json`, `preview_airwater.png`.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from . import airwater as AW
from . import asks as A
from . import garments as G
from . import library as L
from . import places as PL4
from . import planmodel as PM
from . import presets as P
from . import spec as S
from . import transit as TR
from . import weather as WX

TILE_M = 256.0
POOL_RAIN = 0.6             # LG8: the pool's rain looks at this share of the rainiest state's
# (LG1) a person's draws, kept per person as columns in the spike (`library.person`)
PERSON_COLUMNS = ("seed", "character", "scale", "gait", "pace", "tint")


def _sha(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()[:16]


def hashed(rec: dict) -> dict:
    rec = {k: v for k, v in rec.items() if k != "hash"}
    rec["hash"] = _sha(rec)
    return rec


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def tile_of(x: float, y: float) -> str:
    return f"t{math.floor(x / TILE_M):+03d}{math.floor(y / TILE_M):+03d}"


def tile_bounds(name: str) -> list[float]:
    ix, iy = int(name[1:4]), int(name[4:7])
    return [ix * TILE_M, iy * TILE_M, (ix + 1) * TILE_M, (iy + 1) * TILE_M]


def _length(line) -> float:
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(line, line[1:]))


def _length3(line) -> float:
    """A polyline's length in 3D (points without a z at 0)."""
    def p3(p):
        return (float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)
    return sum(math.dist(p3(a), p3(b)) for a, b in zip(line, line[1:]))


def _u(*parts) -> float:
    """A uniform draw in [0, 1) from a hash of ids (blake2b, as citygen's props._u)."""
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big") / 2.0 ** 64


def write(path: Path, text: str, wrote: list) -> None:
    """`text` to `path` only when its bytes differ."""
    data = text.encode("utf-8")
    if not path.is_file() or path.read_bytes() != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        wrote.append(str(path))


def canon(data) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# People and vehicles by district and hour
# ---------------------------------------------------------------------------

def district_hours(model: dict, filled: dict) -> dict[str, dict]:
    """Per district id: its streets' length and its people, vehicles, gang members and police
    by hour (M11's band densities over its segments' lengths, shaped by its day)."""
    seg_len = {s["id"]: float((s.get("attrs") or {}).get("length_m") or
                              _length(s.get("centerline") or []))
               for s in model.get("road_segments", [])}
    band = {d: {"street_m": 0.0, "crowd": [0.0] * 5, "vehicles": [0.0] * 5,
                "gangs": [0.0] * 5, "police": [0.0] * 5} for d in filled["districts"]}
    for row in sorted(model.get("densities", []), key=lambda r: r["id"]):
        d = row.get("district_id")
        if d not in band:
            continue
        L = seg_len.get(row.get("segment_id"), 0.0)
        b = band[d]
        b["street_m"] += L
        for k, f in (("crowd", "crowd_per_100m"), ("vehicles", "vehicles_per_100m"),
                     ("gangs", "gang_per_100m"), ("police", "police_per_100m")):
            vals = row.get(f) or [0.0] * 5
            for i in range(5):
                b[k][i] += float(vals[i]) * L / 100.0
    out = {}
    for d, b in band.items():
        fd = filled["districts"][d]
        shp = fd["shape"]
        hrs = {}
        for k, mul in (("people", fd["busy"]), ("vehicles", filled["fleet_busy"]),
                       ("gangs", fd["busy"]), ("police", 1.0)):
            src = b["crowd" if k == "people" else k]
            hrs[k] = [_r(src[P.band_of(h)] * shp[h] * mul, 2) for h in range(P.HOURS)]
        out[d] = {"street_m": _r(b["street_m"], 1), "band": b, **hrs}
    return out


# ---------------------------------------------------------------------------
# Spawn points and slots
# ---------------------------------------------------------------------------

def _ground_end(line) -> list[float]:
    """The end of an access walkway nearest the ground (a stair's street end)."""
    a, b = line[0], line[-1]
    za = abs(a[2] if len(a) > 2 else 0.0)
    zb = abs(b[2] if len(b) > 2 else 0.0)
    p = a if za <= zb else b
    return [float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0]


def spawn_points(model: dict, walk_by: dict, doors: list | None = None) -> list[dict]:
    """Every spawn point without its rates: (record, weight). LG3: `doors` (AG3's, from
    `door_points`) in place of M3's entrances where the build has them."""
    out = list(doors) if doors is not None else []
    for b in ([] if doors is not None else model.get("buildings", [])):
        for k, e in enumerate(b.get("entrances") or []):
            if not e.get("walkway_id"):
                continue
            p = e["position"]
            z = float(p[2]) if len(p) > 2 else 0.0
            w = P.SPAWN_WEIGHT.get(e.get("kind"), 1.0) * (1.0 + min(40, int(b.get("floors")
                                                                             or 1)) / 10.0)
            out.append(({"id": f"spawn.{b['id']}.e{k}", "owner_id": b["id"], "kind": "door",
                         "sub": e.get("kind") or "main", "district_id": b.get("district_id"),
                         "pos": [_r(p[0], 2), _r(p[1], 2), _r(z, 2)],
                         "level": int((b.get("attrs") or {}).get("level") or 0),
                         "walkway_id": e["walkway_id"], "lane_id": None}, w))
    for s in model.get("stations", []):
        for k, wid in enumerate(s.get("access_ids") or []):
            w = walk_by.get(wid)
            if w is None:
                continue
            p = _ground_end(w["line"])
            out.append(({"id": f"spawn.{s['id']}.a{k}", "owner_id": s["id"], "kind": "station",
                         "sub": s.get("kind") or "station", "district_id": None,
                         "pos": [_r(p[0], 2), _r(p[1], 2), _r(p[2], 2)], "level": 0,
                         "walkway_id": wid, "lane_id": None}, P.SPAWN_WEIGHT["station"]))
    for pk in model.get("parking", []):
        for k, e in enumerate(pk.get("entrances") or []):
            if not e.get("walkway_id"):
                continue
            p = e["position"]
            w = P.SPAWN_WEIGHT["parking"] * max(1.0, math.sqrt(float(pk.get("capacity") or 1)
                                                               / 25.0))
            out.append(({"id": f"spawn.{pk['id']}.e{k}", "owner_id": pk["id"],
                         "kind": "garage", "sub": pk.get("kind") or "garage",
                         "district_id": pk.get("district_id"),
                         "pos": [_r(p[0], 2), _r(p[1], 2), 0.0], "level": 0,
                         "walkway_id": e["walkway_id"], "lane_id": e.get("lane_id")}, w))
    for t in model.get("travel_points", []):
        if t.get("kind") != "taxi_stand" or not (t.get("access") or {}).get("walkway_id"):
            continue
        a = t["access"]
        p = a["position"]
        out.append(({"id": f"spawn.{t['id']}", "owner_id": t["id"], "kind": "taxi_stand",
                     "sub": "taxi_stand", "district_id": t.get("district_id"),
                     "pos": [_r(p[0], 2), _r(p[1], 2), 0.0], "level": 0,
                     "walkway_id": a["walkway_id"], "lane_id": a.get("lane_id")},
                    P.SPAWN_WEIGHT["taxi_stand"]))
    return out


def door_points(build: Path, model: dict, walk_by: dict) -> list | None:
    """LG3: every AG3 door (the street fronts' entries in the build's
    `assets/unreal_contribution.buildings.json`: a door per entrance and shop unit, on the
    facade, with the walkway it opens to) as a spawn point without its rates: (record,
    weight). None when the build has no stage 2 buildings (M3's entrances then)."""
    path = build / "assets" / "unreal_contribution.buildings.json"
    if not path.is_file():
        return None
    con = json.loads(path.read_text(encoding="utf-8"))
    bld = {b["id"]: b for b in model.get("buildings", [])}
    out = []
    for e in con.get("entries", []):
        doors = e.get("doors") or []
        if not doors:
            continue
        px, py, pz = (float(v) for v in e.get("pivot", [0.0, 0.0, 0.0]))
        bid = (e.get("ids") or [e["key"]])[0]
        b = bld.get(bid) or {}
        floors = 1.0 + min(40, int(b.get("floors") or 1)) / 10.0
        for d in doors:
            wid = d.get("walkway_id")
            if not wid or wid not in walk_by:
                continue
            x, y, z = (float(v) for v in d["position"])
            nx, ny = (float(v) for v in d.get("normal") or [1.0, 0.0])
            kind = d["kind"] if d["kind"] != "shop" else f"shop.{d.get('use') or 'unit'}"
            w = P.DOOR_WEIGHT.get(kind) or P.SPAWN_WEIGHT.get(kind) or (
                P.SPAWN_WEIGHT["unit"] if kind.startswith("shop.") else 1.0)
            out.append(({"id": f"spawn.{d['id']}", "owner_id": bid, "kind": "door",
                         "sub": kind, "district_id": b.get("district_id"),
                         "pos": [_r(px + x, 2), _r(py + y, 2), _r(pz + z, 2)],
                         "level": int(e.get("level") or 0), "walkway_id": wid,
                         "lane_id": None,
                         "yaw_deg": _r(math.degrees(math.atan2(ny, nx)), 2)}, w * floors))
    return out


def _district_at(polys: list, x: float, y: float) -> str | None:
    import shapely
    pt = shapely.Point(x, y)
    for did, poly in polys:
        if poly.covers(pt):
            return did
    return None


def assign_roles(cols: dict, n_gang: int, n_police: int) -> None:
    """LG4: the pool slots kept for gang members and police (`places.reserve`), drawn by hash
    among the pool; each a character of the library with a look of its group (LG2's gang and
    police looks), drawn by `character_weights`, wearing that look. `cols["role"]`: 0 the crowd,
    1 a gang member, 2 police (`presets.ROLE_CODES`)."""
    pool = len(cols["seed"])
    looks = G.spec(L.characters(L.CHARACTERS))["looks"]
    w = character_weights(L.CHARACTERS)
    order = sorted(range(pool), key=lambda k: (_u("lg4.role", k), k))
    role = [0] * pool
    for k in order[:n_police]:
        role[k] = 2
    for k in order[n_police:n_police + n_gang]:
        role[k] = 1
    for k, r in enumerate(role):
        if r == 0:
            continue
        g = P.ROLE_CODES[r]
        cands = [(c, j) for c, lks in enumerate(looks) for j, lk in enumerate(lks)
                 if lk["group"] == g]
        if not cands:
            role[k] = 0
            continue
        ws = [w[c] for c, _ in cands]
        x = _u("lg4.role.char", cols["seed"][k], k) * sum(ws)
        i = 0
        while i < len(cands) - 1 and x >= ws[i]:
            x -= ws[i]
            i += 1
        c, j = cands[i]
        cols["character"][k] = c
        cols["look"][k] = c * G.LOOKS + j
        cols["group"][k] = G.GROUPS.index(g)
    cols["role"] = role


# ---------------------------------------------------------------------------
# LG3: the city's crowd and the signals
# ---------------------------------------------------------------------------

def _heading(a, b) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _line_diff(a: float, b: float) -> float:
    """The angle (degrees, 0 to 90) between two lines (headings taken mod 180)."""
    d = abs((a - b) % 180.0)
    return min(d, 180.0 - d)


def _mid(line) -> tuple[float, float]:
    """The middle of a polyline by length (its middle point when it has no length)."""
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


def signals(model: dict) -> tuple[list[dict], dict[str, tuple[str, int]]]:
    """The derived signal phases of every signalized junction (`presets.SIGNAL`; the ask
    `signal_phases`), and each signalized crosswalk walkway's (signal id, phase)."""
    sg = P.SIGNAL
    segs = {s["id"]: s for s in model.get("road_segments", [])}
    cws = {c["id"]: c for c in model.get("crosswalks", [])}
    walks_at = defaultdict(list)
    for w in model.get("walkways", []):
        if w.get("kind") == "crosswalk" and (w.get("attrs") or {}).get("junction"):
            walks_at[w["attrs"]["junction"]].append(w)
    out, of = [], {}
    for j in sorted(model.get("junctions", []), key=lambda j: j["id"]):
        if not j.get("signalized"):
            continue
        legs = []
        for cut in (j.get("attrs") or {}).get("cuts") or []:
            s = segs.get(cut[0])
            cl = (s or {}).get("centerline") or []
            if len(cl) < 2:
                continue
            a, b = (cl[0], cl[1]) if cut[1] == "a" else (cl[-1], cl[-2])
            legs.append((cut[0], _heading(a, b)))
        legs.sort()
        axis = legs[0][1] if legs else 0.0
        phase_of = {sid: 0 if _line_diff(h, axis) <= 45.0 else 1 for sid, h in legs}
        cross = [[], []]
        for cid in sorted(j.get("crosswalk_ids") or []):
            c = cws.get(cid)
            if c is None or not c.get("signalized"):
                continue
            # (people cross a leg while it is stopped: in the other phase)
            cross[1 - phase_of.get(c.get("segment_id"), 0)].append(cid)
        # (each crosswalk walkway is the crosswalk nearest its middle stretch)
        cw_mid = {cid: _mid(cws[cid]["line"]) for p in cross for cid in p}
        ways = [[], []]
        for w in sorted(walks_at.get(j["id"], []), key=lambda w: w["id"]):
            ln = w["line"]
            core = ln[1:-1] if len(ln) >= 4 else ln
            m = _mid(core)
            best = min(cw_mid, key=lambda c: (math.dist(m, cw_mid[c]), c), default=None)
            if best is None or math.dist(m, cw_mid[best]) > 6.0:
                continue
            k = 0 if best in cross[0] else 1
            ways[k].append(w["id"])
        half = sg["cycle_s"] / 2.0
        sid = f"sig.{j['id']}"
        phases = []
        for k in (0, 1):
            phases.append({"index": k, "legs": sorted(s for s, p in phase_of.items() if p == k),
                           "crosswalks": cross[k], "walkways": ways[k],
                           "start_s": _r(k * half, 2),
                           "green_s": _r(half - sg["amber_s"] - sg["all_red_s"], 2),
                           "amber_s": sg["amber_s"], "all_red_s": sg["all_red_s"],
                           "walk_s": sg["walk_s"]})
            for wid in ways[k]:
                of[wid] = (sid, k)
        out.append(hashed({"id": sid, "junction_id": j["id"], "cycle_s": sg["cycle_s"],
                           "offset_s": _r(int(_u("lg3.signal", j["id"]) * sg["cycle_s"] * 10)
                                          / 10.0, 1),
                           "phases": phases}))
    return out, of


def district_palette(model: dict, filled: dict, did: str, tag: str = "lg0") -> list[str]:
    """A district's clothes' colors: its style's groups by weight, each a color of its
    group's, a gang's its faction's color (`presets.SPIKE_PALETTE` of them)."""
    style = filled["districts"][did]["style"]["groups"]
    gang = next((f.get("color") for f in model.get("factions", [])
                 if f.get("kind") == "gang" and f.get("home_district_id") == did), None)
    palette = []
    for k in range(P.SPIKE_PALETTE):
        g = _pick(style, f"{tag}.palette.group", did, k)
        cols = (gang,) if g == "gang" and gang else P.GROUP_COLORS[g]
        palette.append(cols[int(_u(f"{tag}.palette.color", did, k) * len(cols))])
    return palette


def crowd_walks(model: dict, filled: dict, polys: list, sig_of: dict,
                spawn_walks: set[str]) -> tuple[list[dict], dict]:
    """Every walkway's people per hour band (scope 6.3): a road segment's people (M11's
    crowd per 100 m over its length, the district's busy, the crowd's scale) on its own
    walkways by length; every other walkway its district's mean street density (people a
    meter) times its kind's `presets.OFFSTREET`; none on a walkway no spawn point's walkway
    reaches (nobody gets there). Returns the rows and what was left out."""
    scale = float(filled["crowd"]["scale"])
    seg_len = {s["id"]: float((s.get("attrs") or {}).get("length_m") or
                              _length(s.get("centerline") or []))
               for s in model.get("road_segments", [])}
    dens = {}
    for row in model.get("densities", []):
        d = row.get("district_id")
        if d in filled["districts"]:
            dens[row["segment_id"]] = (d, [float(v) * seg_len.get(row["segment_id"], 0.0)
                                           / 100.0 * filled["districts"][d]["busy"] * scale
                                           for v in (row.get("crowd_per_100m") or [0.0] * 5)])
    walks = model.get("walkways", [])
    on_seg = defaultdict(float)
    for w in walks:
        s = (w.get("attrs") or {}).get("segment")
        if s in dens:
            on_seg[s] += _length3(w["line"])
    comp = walk_components(walks)
    reach = {comp[w] for w in spawn_walks if w in comp}
    rows = []
    street_m = defaultdict(float)
    street_p = defaultdict(lambda: [0.0] * 5)
    for w in walks:
        # (along its slope: a stair's or an elevator's length is its rise)
        L = _length3(w["line"])
        s = (w.get("attrs") or {}).get("segment")
        mx, my = _mid(w["line"])
        if s in dens and on_seg[s] > 0.0:
            d, band = dens[s]
            ppl = [v * L / on_seg[s] for v in band]
            street = True
            # (the mean street density: its sidewalks', not the promenades' and pedestrian
            # streets', which are many times as busy)
            if w.get("kind") == "sidewalk":
                street_m[d] += L
                for i in range(5):
                    street_p[d][i] += ppl[i]
        else:
            d = _district_at(polys, mx, my)
            ppl, street = None, False
        rows.append({"id": w["id"], "kind": w.get("kind") or "path", "district_id": d,
                     "level": int(w.get("level") or (w.get("attrs") or {}).get("level") or 0),
                     "length_m": _r(L, 2), "street": street, "people": ppl,
                     "tile": tile_of(mx, my), "_comp": comp.get(w["id"])})
    mean = {d: [street_p[d][i] / street_m[d] if street_m[d] > 0 else 0.0 for i in range(5)]
            for d in street_m}
    left = {"walkways": 0, "people": [0.0] * 5, "street": {}, "segments": 0}
    # (a segment with people and no walkway of its own: its people go nowhere, said so)
    for s, (d, band) in sorted(dens.items()):
        if on_seg[s] <= 0.0 and any(v > 0.0 for v in band):
            left["segments"] += 1
            st = left["street"].setdefault(d, [0.0] * 5)
            for i in range(5):
                st[i] += band[i]
    for r in rows:
        if r["people"] is None:
            k = P.OFFSTREET.get(r["kind"], P.OFFSTREET_DEFAULT)
            m = mean.get(r["district_id"]) or [0.0] * 5
            r["people"] = [k * v * r["length_m"] for v in m]
        if r["_comp"] not in reach and any(v > 0.0 for v in r["people"]):
            left["walkways"] += 1
            for i in range(5):
                left["people"][i] += r["people"][i]
            if r["street"]:
                st = left["street"].setdefault(r["district_id"], [0.0] * 5)
                for i in range(5):
                    st[i] += r["people"][i]
            r["people"] = [0.0] * 5
        r["people"] = [_r(v, 4) for v in r["people"]]
        sig = sig_of.get(r["id"])
        r["signal"], r["phase"] = (sig[0], sig[1]) if sig else (None, None)
    left["people"] = [_r(v, 2) for v in left["people"]]
    left["street"] = {d: [_r(v, 3) for v in vs] for d, vs in sorted(left["street"].items())}
    for r in rows:
        del r["_comp"]
    return rows, left


CROWD_COLUMNS = PERSON_COLUMNS


def variety_checks(rows: list[dict], crowd: dict) -> dict:
    """LG2's variety check (scope 8): in every district at its busiest band, the people within
    `presets.VARIETY_M` of one another (its busiest tile's people per square meter over that
    circle, at most the pool's within it) alike in character, look and colors in fewer than
    `VARIETY_PAIRS` expected pairs; no look more than `LOOK_SHARE_MAX` of its people."""
    ps = crowd["persons"]
    out_f = crowd.get("outfits") or {}
    if not ps.get("look") or not out_f:
        return {}
    G_ = out_f["groups"]
    by_group = defaultdict(lambda: defaultdict(int))
    for lk, g in zip(ps["look"], ps["group"]):
        by_group[g][lk] += 1
    tile_ppl = defaultdict(lambda: [0.0] * 5)
    for r in rows:
        for i in range(5):
            tile_ppl[(r["district_id"], r["tile"])][i] += r["people"][i]
    pool_n = crowd["pool"] * (P.VARIETY_M / crowd["live_m"]) ** 2
    bad, notes = [], []
    worst = 0.0
    for d, w in sorted(out_f["district_groups"].items()):
        dens = max((max(v) for (dd, _), v in tile_ppl.items() if dd == d),
                   default=0.0) / (TILE_M * TILE_M)
        n50 = min(pool_n, dens * math.pi * P.VARIETY_M ** 2)
        alike = 0.0
        share = defaultdict(float)
        for gi, wg in enumerate(w):
            if wg <= 0.0 or gi not in by_group:
                continue
            tot = sum(by_group[gi].values())
            pl = sum((c / tot) ** 2 for c in by_group[gi].values())
            cols = out_f["palettes"][d][gi]
            pc = sum((cols.count(c) / len(cols)) ** 2 for c in set(cols))
            # (two people alike: the same group, the same look, the same colors on its two
            # dyed channels a look always has)
            alike += wg * wg * pl * pc * pc
            for lk, c in by_group[gi].items():
                share[lk] += wg * c / tot
        pairs = n50 * (n50 - 1) / 2.0 * alike
        worst = max(worst, pairs)
        top = max(share.values()) if share else 0.0
        notes.append(f"{d} {n50:.0f} within {P.VARIETY_M:.0f} m, {pairs:.2f} alike pairs, "
                     f"its commonest look {top:.1%}")
        if pairs > P.VARIETY_PAIRS:
            bad.append(f"{d}: {pairs:.2f} expected alike pairs within {P.VARIETY_M:.0f} m")
        if top > P.LOOK_SHARE_MAX:
            bad.append(f"{d}: a look is {top:.1%} of its people")
    return {"variety": {"ok": not bad, "detail": "; ".join(bad[:4]) if bad else
                        f"{len(set(ps['look']))} looks among the pool's {len(ps['look'])} "
                        f"people; " + "; ".join(notes)}}


def character_weights(n: int) -> list[float]:
    """lifegen_people_fixes: each of the library's `n` characters' weight in a crowd, by the
    preset it is made from (`presets.BODY_WEIGHT`: heavy builds rare)."""
    return [float(P.BODY_WEIGHT.get(L.character(k)["preset"], 1.0)) for k in range(n)]


def draw_person(seed_parts: tuple, n: int, palette: list | None = None) -> dict:
    """A person of the crowd (`library.person`), its character drawn by `character_weights`
    from the same uniform draw (the plan stays a function of the seeds; kept out of
    `library.py`, whose hash names the built library)."""
    p = L.person(seed_parts, n, palette=palette)
    w = character_weights(n)
    x = L._u(*seed_parts, "char") * sum(w)
    k = 0
    while k < n - 1 and x >= w[k]:
        x -= w[k]
        k += 1
    p["character"] = k
    return p


def _lin(h: str) -> list[float]:
    def c(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return [c(int(h[1 + 2 * k:3 + 2 * k], 16)) for k in range(3)]


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(v * 255)))):02x}" for v in rgb)


def outfit_groups(filled: dict, rain: float | None = None) -> dict[str, list[float]]:
    """LG2: each district's people by look group (`garments.GROUPS`): its style's groups,
    with the weather's share in the rain looks (`rain`, default the plan's own state's)."""
    if rain is None:
        rain = float(P.WEATHER_OUTFITS.get(filled["crowd"].get("weather", "clear"), 0.0))
    out = {}
    for d, fd in sorted(filled["districts"].items()):
        w = [float(fd["style"]["groups"].get(g, 0.0)) for g in G.GROUPS]
        t = sum(w) or 1.0
        w = [v / t * (1.0 - rain) for v in w]
        w[G.GROUPS.index("rain")] += rain
        out[d] = [_r(v, 4) for v in w]
    return out


def outfit_palettes(model: dict, filled: dict) -> dict[str, list[list[str]]]:
    """LG2: per district and look group the colors a person's dye channels draw from
    (`presets.OUTFIT_COLORS`): the group's colors shaded, a gang's its faction's first."""
    out = {}
    for d in sorted(filled["districts"]):
        gang = next((f.get("color") for f in model.get("factions", [])
                     if f.get("kind") == "gang" and f.get("home_district_id") == d), None)
        rows = []
        for g in G.GROUPS:
            base = list(P.GROUP_COLORS.get("street" if g == "rain" else g, ("#808080",)))
            if g == "gang" and gang:
                base = [gang, gang] + base
            # (every color of the group in every shade, in an order drawn by hash, the first
            # OUTFIT_COLORS distinct ones; a gang's own color first)
            combos = sorted({(c, 1.0 if g == "police" else sh) for c in base
                             for sh in P.OUTFIT_SHADES},
                            key=lambda cs: (-(cs[0] == gang and g == "gang" and cs[1] == 1.0),
                                            _u("lg2.palette", d, g, cs[0], cs[1])))
            cols = []
            for c, sh in combos:
                rgb = [min(1.0, int(c[1 + 2 * j:3 + 2 * j], 16) / 255.0 * sh) for j in range(3)]
                h = _hex(rgb)
                if h not in cols:
                    cols.append(h)
                if len(cols) >= P.OUTFIT_COLORS:
                    break
            rows.append(cols)
        out[d] = rows
    return out


def assign_looks(persons: dict, mix: list[float]) -> tuple[list[int], list[int]]:
    """LG2: each pool person's look: a look of their character, its group drawn from the
    city's mix of groups among the character's looks (the runtime spawns a person in a
    district by its groups, so the pool holds every group by the city's people)."""
    looks = G.spec(L.characters(L.CHARACTERS))["looks"]
    out_look, out_group = [], []
    for k, (c, seed) in enumerate(zip(persons["character"], persons["seed"])):
        mine = looks[c]
        w = [mix[G.GROUPS.index(lk["group"])] for lk in mine]
        t = sum(w)
        x = _u("lg2.look", seed, k) * (t if t > 0 else len(mine))
        j = 0
        while j < len(mine) - 1 and x >= (w[j] if t > 0 else 1.0):
            x -= w[j] if t > 0 else 1.0
            j += 1
        out_look.append(c * G.LOOKS + j)
        out_group.append(G.GROUPS.index(mine[j]["group"]))
    return out_look, out_group


def crowd_plan(model: dict, filled: dict, rows: list[dict], sigs: list[dict],
               left: dict, roles: tuple[int, int] | None = None) -> dict:
    """The crowd's record in the plan: its settings, the pool's people by their seeds, the
    districts' palettes, its totals by hour; LG4: the slots kept for gang members and police
    (`roles`: how many of each, `assign_roles`)."""
    cr = filled["crowd"]
    n = L.CHARACTERS
    pool = int(cr["pool"])
    cols = {k: [] for k in CROWD_COLUMNS}
    for k in range(pool):
        p = draw_person(("lg3.person", k), n, palette=[0] * P.SPIKE_PALETTE)
        for c in CROWD_COLUMNS:
            cols[c].append(p[c])
    # (LG2: each person's look and its group, by the city's people per district and group)
    groups = outfit_groups(filled)
    # (LG8: the pool holds the rain looks the runtime's rain asks for: its mix is drawn at a
    # rain share between clear's and the rainiest state's, `POOL_RAIN` of it)
    pool_groups = outfit_groups(filled, POOL_RAIN * max(
        v["rain_looks"] for v in P.WEATHER_LIFE.values()))
    band = P.band_of(int(cr["hour"]))
    ppl = defaultdict(float)
    for r in rows:
        ppl[r["district_id"]] += r["people"][band]
    # (the pool lives round the view, a district or two at a time: half its mix is the city's
    # people by group, half each group's largest share of any district, so a quiet district's
    # group has people enough when the view is there)
    tot = sum(ppl.values()) or 1.0
    mix = [0.5 * sum(ppl[d] * pool_groups[d][i] for d in pool_groups) / tot +
           0.5 * max(pool_groups[d][i] for d in pool_groups) / max(1e-9, sum(
               max(pool_groups[d][j] for d in pool_groups) for j in range(len(G.GROUPS))))
           for i in range(len(G.GROUPS))]
    if not sum(mix):
        mix = [1.0] * len(G.GROUPS)
    cols["look"], cols["group"] = assign_looks(cols, mix)
    if roles is not None:
        assign_roles(cols, int(roles[0]), int(roles[1]))
    shapes = {d: fd["shape"] for d, fd in filled["districts"].items()}
    street = [0.0] * P.HOURS
    off = [0.0] * P.HOURS
    levels = set()
    with_people = 0
    for r in rows:
        if any(v > 0.0 for v in r["people"]):
            with_people += 1
            levels.add(r["level"])
        shp = shapes.get(r["district_id"]) or [1.0] * P.HOURS
        for h in range(P.HOURS):
            v = r["people"][P.band_of(h)] * shp[h]
            if r["street"]:
                street[h] += v
            else:
                off[h] += v
    c = P.CROWD
    return hashed({
        "hour": int(cr["hour"]), "pool": pool, "live_m": c["live_m"],
        "trip_s": float(cr["trip_s"]), "scale": float(cr["scale"]),
        "groups": list(c["groups"]), "group_gap_m": c["group_gap_m"],
        "jaywalk": list(c["jaywalk"]),
        "avoid": {k: c[k] for k in ("reach_m", "personal_m", "player_m", "avoid_m")},
        "speeds": {"stairs": c["stairs"], "escalator": list(c["escalator"]),
                   "elevator": c["elevator"]},
        "kinds": list(P.WALK_KIND_CODES),
        "palettes": {d: district_palette(model, filled, d) for d in filled["districts"]},
        "outfits": {"groups": list(G.GROUPS), "district_groups": groups,
                    # (LG8: the clear weather's, which the runtime blends with the rain looks
                    # by atmosgen's rain, `weather.states[...].rain_looks`)
                    "district_groups_clear": outfit_groups(filled, 0.0),
                    "rain_group": G.GROUPS.index("rain"),
                    "palettes": outfit_palettes(model, filled),
                    "wear": {d: fd["style"].get("wear", 0.3)
                             for d, fd in sorted(filled["districts"].items())},
                    "weather": filled["crowd"].get("weather", "clear"),
                    "looks_per": G.LOOKS},
        "library": {"version": L.LIB_VERSION, "characters": n,
                    "looks": n * G.LOOKS, "walks": list(L.WALKS),
                    "tiers": dict(sorted(L.TIERS.items()))},
        "persons": cols,
        **({"roles": {"names": list(P.ROLE_CODES),
                      "slots": [cols["role"].count(k) for k in range(len(P.ROLE_CODES))]}}
           if "role" in cols else {}),
        "totals": {"walkways": len(rows), "with_people": with_people,
                   "levels": sorted(levels), "signals": len(sigs),
                   "street_people": [_r(v, 1) for v in street],
                   "offstreet_people": [_r(v, 1) for v in off],
                   "left_out": left}})


def crowd_checks(model: dict, rows: list[dict], hours: dict, filled: dict, sigs: list[dict],
                 crowd: dict, spawns: list[dict]) -> dict:
    """LG3's checks: the walkways' people keep M11's densities per district and band, every
    level with people reachable from the ground, the signals' phases, the pool within the
    budget."""
    out = {}
    scale = float(filled["crowd"]["scale"])
    got = defaultdict(lambda: [0.0] * 5)
    for r in rows:
        if r["street"]:
            for i in range(5):
                got[r["district_id"]][i] += r["people"][i]
    lost = crowd["totals"]["left_out"]
    bad = []
    for d, h in hours.items():
        fd = filled["districts"][d]
        for i in range(5):
            want = h["band"]["crowd"][i] * fd["busy"] * scale
            # (people on walkways nobody reaches are left out and said so)
            have = got[d][i] + (lost["street"].get(d) or [0.0] * 5)[i]
            if abs(have - want) > max(0.5, 0.01 * want):
                bad.append(f"{d} {P.BANDS[i]} {have:.1f} != {want:.1f}")
    out["crowd_densities"] = {"ok": not bad, "detail": (
        f"every district's sidewalks carry M11's people per hour band (times its busy and "
        f"the crowd's scale) within 1%; off-street walkways "
        f"{max(crowd['totals']['offstreet_people']):.0f} more at the most; "
        f"{lost['walkways']} walkways no spawn reaches left empty "
        f"({max(lost['people']):.1f} people)" if not bad else "; ".join(bad[:5]))}
    # every level with people: its walkways meet the ground's largest walkway component
    comp = walk_components(model.get("walkways", []))
    size = defaultdict(int)
    for c in comp.values():
        size[c] += 1
    main = max(size, key=lambda c: (size[c], -c)) if size else None
    lv = defaultdict(lambda: [0, 0])
    for r in rows:
        if any(v > 0.0 for v in r["people"]):
            lv[r["level"]][0] += 1
            lv[r["level"]][1] += int(comp.get(r["id"]) == main)
    cut = [lvl for lvl, (n, m) in lv.items() if m == 0]
    out["crowd_levels"] = {"ok": not cut, "detail": (
        "levels " + ", ".join(f"{lvl}: {m} of {n} walkways with people on the main walkway "
                              f"graph" for lvl, (n, m) in sorted(lv.items()))
        if not cut else f"levels {cut} have no walkway on the main walkway graph")}
    # signals: every leg in one phase, a crosswalk never walking while its leg moves,
    # the phases filling the cycle
    segs_of = {}
    for c in model.get("crosswalks", []):
        segs_of[c["id"]] = c.get("segment_id")
    sbad = []
    for s in sigs:
        legs = [leg for p in s["phases"] for leg in p["legs"]]
        if len(legs) != len(set(legs)):
            sbad.append(f"{s['id']}: a leg in two phases")
        for p in s["phases"]:
            if set(segs_of.get(c) for c in p["crosswalks"]) & set(p["legs"]):
                sbad.append(f"{s['id']}: a crosswalk walks across a moving leg")
        tot = sum(p["green_s"] + p["amber_s"] + p["all_red_s"] for p in s["phases"])
        if abs(tot - s["cycle_s"]) > 0.05 or not 30.0 <= s["cycle_s"] <= 150.0:
            sbad.append(f"{s['id']}: phases {tot:.1f} s in a {s['cycle_s']:.0f} s cycle")
    nsig = sum(1 for j in model.get("junctions", []) if j.get("signalized"))
    served = sum(len(p["walkways"]) for s in sigs for p in s["phases"])
    out["signals"] = {"ok": not sbad and len(sigs) == nsig, "detail": (
        f"{len(sigs)} signalized junctions, two phases each (derived: the ask), no crosswalk "
        f"walking across a moving leg, the phases filling each cycle; {served} crosswalk "
        f"walkways served" if not sbad and len(sigs) == nsig else "; ".join(sbad[:5]) or
        f"{len(sigs)} signals for {nsig} signalized junctions")}
    bud = filled["budgets"]
    pool, live = crowd["pool"], crowd["live_m"]
    in_view = pool * min(1.0, (bud["view_m"] / live) ** 2)
    ok = in_view <= bud["people_view"] + 0.5
    out["crowd_budget"] = {"ok": ok, "detail": (
        f"a pool of {pool} people live within {live:.0f} m of the view, about "
        f"{in_view:.0f} within {bud['view_m']:.0f} m (the budget's {bud['people_view']})")}
    # (LG1's rule on the pool: every character among its people, none more than
    # PEOPLE_SHARE_MAX of them)
    chars = crowd["persons"].get("character") or []
    n = crowd["library"].get("characters") or 0
    if chars and n:
        cnt = [chars.count(k) for k in range(n)]
        ok = len(chars) < 10 * n or (min(cnt) > 0 and max(cnt) / len(chars) <= PEOPLE_SHARE_MAX)
        out["people_draws"] = {"ok": ok, "detail": (
            f"the crowd's pool of {len(chars)} people drawn from {n} characters, each "
            f"{min(cnt)} to {max(cnt)} of them (at most {PEOPLE_SHARE_MAX:.0%}), "
            f"{len(set(crowd['persons'].get('seed') or []))} distinct seeds")}
    out.update(variety_checks(rows, crowd))
    # every spawn point's walkway a walkway of the crowd
    ids = {r["id"] for r in rows}
    off = [s["id"] for s in spawns if s["walkway_id"] not in ids]
    out["crowd_spawns"] = {"ok": not off, "detail": (
        f"{len(spawns)} spawn points open to the crowd's walkways" if not off else
        f"{len(off)} spawn points on no walkway of the crowd, first {off[:3]}")}
    return out


# ---------------------------------------------------------------------------
# LG5: the city's traffic
# ---------------------------------------------------------------------------

def _cross_at(line, a, b) -> float | None:
    """The distance along a polyline (plan) where it first crosses the segment a-b, or
    None."""
    run = 0.0
    for p, q in zip(line, line[1:]):
        rx, ry = q[0] - p[0], q[1] - p[1]
        sx, sy = b[0] - a[0], b[1] - a[1]
        den = rx * sy - ry * sx
        seg = math.hypot(rx, ry)
        if abs(den) > 1e-9:
            t = ((a[0] - p[0]) * sy - (a[1] - p[1]) * sx) / den
            u = ((a[0] - p[0]) * ry - (a[1] - p[1]) * rx) / den
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                return run + t * seg
        run += seg
    return None


def lane_signals(model: dict, sigs: list[dict]) -> dict[str, tuple[str, int, float]]:
    """Per lane (a lane, not a connector) that ends at a signalized junction on one of its legs:
    its signal, the phase its leg moves in and where its cars stop on red (m back from the
    lane's end: `presets.TRAFFIC["stop_margin_m"]` short of the crosswalk across it, else of
    its end)."""
    tr = P.TRAFFIC
    segs = {s["id"]: s for s in model.get("road_segments", [])}
    juncs = {j["id"]: j for j in model.get("junctions", [])}
    cws = {c["id"]: c for c in model.get("crosswalks", [])}
    at_node: dict[str, tuple[dict, dict]] = {}
    for s in sigs:
        j = juncs.get(s["junction_id"])
        if j is None:
            continue
        phase_of = {leg: p["index"] for p in s["phases"] for leg in p["legs"]}
        for n in [j["node_id"], *((j.get("attrs") or {}).get("nodes") or [])]:
            at_node[n] = (s, phase_of, j)
    out = {}
    for ln in model.get("lanes", []):
        if ln.get("kind") != "lane" or ln.get("segment_id") not in segs:
            continue
        seg = segs[ln["segment_id"]]
        end = seg.get("end") if ln.get("forward", True) else seg.get("start")
        hit = at_node.get(end)
        if hit is None or ln["segment_id"] not in hit[1]:
            continue
        s, phase_of, j = hit
        line = ln["centerline"]
        L = _length(line)
        stop = L - tr["stop_margin_m"]
        for cid in j.get("crosswalk_ids") or []:
            c = cws.get(cid)
            if c is None or c.get("segment_id") != ln["segment_id"]:
                continue
            at = _cross_at(line, c["line"][0], c["line"][-1])
            if at is not None:
                stop = min(stop, at - 0.5 * float(c.get("width_m") or 3.0) - tr["stop_margin_m"])
        back = min(max(L - stop, 0.0), max(0.0, L - 1.0))
        out[ln["id"]] = (s["id"], phase_of[ln["segment_id"]], _r(back, 2))
    return out


def traffic_lanes(model: dict, filled: dict, sigs: list[dict]) -> tuple[list[dict], dict]:
    """Every lane's cars per hour band (scope 6.5): a road segment's vehicles (M11's per 100 m
    over its length, the fleet's busy, the traffic's scale) on its lanes by length; none on a
    lane off the lane graph's largest strongly connected part (cars that drive there could
    never leave: said in what is left out), nor on a segment with no lane. Returns the rows
    and what was left out."""
    from citygen.unreal_life import main_component
    scale = float(filled["traffic"]["scale"]) * float(filled["fleet_busy"])
    segs = {s["id"]: s for s in model.get("road_segments", [])}
    seg_len = {sid: float((s.get("attrs") or {}).get("length_m") or
                          _length(s.get("centerline") or [])) for sid, s in segs.items()}
    dens = {}
    for row in model.get("densities", []):
        d = row.get("district_id")
        if d in filled["districts"]:
            dens[row["segment_id"]] = (d, [float(v) * seg_len.get(row["segment_id"], 0.0)
                                           / 100.0 * scale
                                           for v in (row.get("vehicles_per_100m") or [0.0] * 5)])
    lanes = model.get("lanes", [])
    idx = {ln["id"]: k for k, ln in enumerate(lanes)}
    main = main_component([[idx[s] for s in ln.get("successors") or [] if s in idx]
                           for ln in lanes])
    on_seg = defaultdict(float)
    for k, ln in enumerate(lanes):
        if ln.get("kind") == "lane" and ln.get("segment_id") in dens:
            on_seg[ln["segment_id"]] += _length(ln["centerline"])
    sig_of = lane_signals(model, sigs)
    left = {"lanes": 0, "segments": 0, "vehicles": [0.0] * 5, "district": {}}

    def lose(d, band):
        st = left["district"].setdefault(d, [0.0] * 5)
        for i in range(5):
            st[i] += band[i]
            left["vehicles"][i] += band[i]

    for sid, (d, band) in sorted(dens.items()):
        if on_seg[sid] <= 0.0 and any(v > 0.0 for v in band):
            left["segments"] += 1
            lose(d, band)
    rows = []
    for k, ln in enumerate(lanes):
        if ln.get("kind") != "lane" or not ln.get("segment_id"):
            continue
        sid = ln["segment_id"]
        L = _length(ln["centerline"])
        d, band = dens.get(sid, (None, [0.0] * 5))
        veh = [v * L / on_seg[sid] for v in band] if on_seg[sid] > 0.0 else [0.0] * 5
        if k not in main and any(v > 0.0 for v in veh):
            left["lanes"] += 1
            lose(d, veh)
            veh = [0.0] * 5
        rc = (segs.get(sid) or {}).get("road_class") or P.DRIVE["default"]
        mx, my = _mid(ln["centerline"])
        sg = sig_of.get(ln["id"])
        rows.append({"id": ln["id"], "segment_id": sid, "district_id": d,
                     "road_class": rc if rc in P.DRIVE_SPEEDS else P.DRIVE["default"],
                     "length_m": _r(L, 2), "main": k in main,
                     "vehicles": [_r(v, 4) for v in veh],
                     "signal": sg[0] if sg else None, "phase": sg[1] if sg else None,
                     "stop_back_m": sg[2] if sg else None, "tile": tile_of(mx, my)})
    left["vehicles"] = [_r(v, 2) for v in left["vehicles"]]
    left["district"] = {d: [_r(v, 3) for v in vs] for d, vs in sorted(left["district"].items(),
                                                                     key=lambda kv: str(kv[0]))}
    left["main_lanes"] = sum(1 for k, ln in enumerate(lanes) if k in main)
    left["all_lanes"] = len(lanes)
    return rows, left


def traffic_plan(model: dict, filled: dict, rows: list[dict], left: dict,
                 police_cars: int = 0) -> dict:
    """The traffic's record in the plan: its settings, the pool's slots by model (shared out by
    the districts' fleets: half the city's mix at the hour, half each model's most in any
    district, so a district's own fleet finds its models free), the districts' fleets and
    paints, its totals by hour; LG4: `police_cars` slots at the pool's end kept for patrol
    cars (the first of `POLICE["car_models"]` the fleet has, in the police livery)."""
    from assetgen.parked.table import EXCLUDED, paint
    tr = filled["traffic"]
    hour = int(filled["crowd"]["hour"])
    dists = filled["districts"]
    models = sorted({m for fd in dists.values() for m, w in fd["fleet"].items()
                     if w > 0 and m not in EXCLUDED})
    police_cars = min(int(police_cars), int(tr["pool"]) - len(models)) if models else 0
    police_cars = max(0, police_cars)
    pool = int(tr["pool"]) - police_cars
    weights = {d: [float(fd["fleet"].get(m, 0.0)) for m in models] for d, fd in dists.items()}
    veh = defaultdict(float)
    for r in rows:
        if r["district_id"] in dists:
            veh[r["district_id"]] += r["vehicles"][P.band_of(hour)] * \
                dists[r["district_id"]]["shape"][hour]
    share = [0.0] * len(models)
    most = [0.0] * len(models)
    tot = sum(veh.values())
    for d, w in weights.items():
        s = sum(w)
        if s <= 0.0:
            continue
        for i, v in enumerate(w):
            if tot > 0.0:
                share[i] += veh[d] / tot * v / s
            if veh[d] > 0.0 or tot <= 0.0:
                most[i] = max(most[i], v / s)
    mix = [0.5 * a + 0.5 * b for a, b in zip(share, most)]
    ms = sum(mix) or 1.0
    want = [pool * v / ms for v in mix]
    count = [int(v) for v in want]
    if pool >= len(models):
        count = [max(1, c) for c in count]
    # (largest remainders, then the most drawn first, to the pool exactly)
    order = sorted(range(len(models)), key=lambda i: (-(want[i] - int(want[i])), models[i]))
    k = 0
    while models and sum(count) < pool:
        count[order[k % len(order)]] += 1
        k += 1
    while models and sum(count) > pool:
        i = max(range(len(models)), key=lambda i: (count[i], models[i]))
        count[i] -= 1
    slots = [i for i, c in enumerate(count) for _ in range(c)]
    slots =[s for _, s in sorted(((_u("lg5.slot", models[s], n), s)
                                   for n, s in enumerate(slots)))]
    kp = int(P.TRAFFIC["paints"])
    paints = {}
    for d, fd in dists.items():
        paints[d] = [[round(float(v), 4) for k2 in range(kp)
                      for c in paint(m, fd["archetype"], f"lg5.{d}.{m}.{k2}")[0] for v in c]
                     for m in models]
    at_hour = [0.0] * P.HOURS
    for r in rows:
        shp = (dists.get(r["district_id"]) or {}).get("shape") or [1.0] * P.HOURS
        for h in range(P.HOURS):
            at_hour[h] += r["vehicles"][P.band_of(h)] * shp[h]
    follow = {k: float(v) for k, v in P.TRAFFIC.items()
              if k not in ("pool", "live_m", "paints", "scale")}
    # (LG4: the patrol cars' slots at the pool's end, a model the fleet has, in the livery)
    pmodel = next((m for m in P.POLICE["car_models"] if m in models), None) or \
        (max(models, key=lambda m: (count[models.index(m)], m)) if models else None)
    pslots = []
    if police_cars and pmodel is not None:
        pslots = list(range(pool, pool + police_cars))
        slots = slots + [models.index(pmodel)] * police_cars
    livery = [v for c in P.POLICE["livery"] for v in _lin(c)]
    return hashed({
        "hour": hour, "pool": pool + len(pslots), "live_m": float(tr["live_m"]),
        "scale": float(tr["scale"]),
        "models": models, "slots": slots, "weights": weights, "paints": paints,
        "police_slots": pslots, "police_model": pmodel if pslots else None,
        "police_paint": [round(v, 4) for v in livery] if pslots else [],
        "drive": {k: (list(v) if isinstance(v, list) else v) for k, v in sorted(P.DRIVE.items())},
        "drive_speeds": dict(sorted(P.DRIVE_SPEEDS.items())), "follow": follow,
        "totals": {"lanes": len(rows),
                   "with_cars": sum(1 for r in rows if any(v > 0.0 for v in r["vehicles"])),
                   "main_lanes": left["main_lanes"], "graph_lanes": left["all_lanes"],
                   "signalized": sum(1 for r in rows if r["signal"]),
                   "slots": dict(zip(models, count)),
                   "cars_by_hour": [_r(v, 1) for v in at_hour], "left_out": left}})


def traffic_checks(model: dict, rows: list[dict], hours: dict, filled: dict, sigs: list[dict],
                   traffic: dict) -> dict:
    """LG5's checks: the lanes' cars keep M11's vehicle densities per district and band (what
    is left out said so), every car on the lane graph's largest strongly connected part, the
    signals' approaches, the pool within the budget, the fleet."""
    out = {}
    scale = float(filled["traffic"]["scale"]) * float(filled["fleet_busy"])
    got = defaultdict(lambda: [0.0] * 5)
    for r in rows:
        for i in range(5):
            got[r["district_id"]][i] += r["vehicles"][i]
    lost = traffic["totals"]["left_out"]
    bad = []
    for d, h in hours.items():
        for i in range(5):
            want = h["band"]["vehicles"][i] * scale
            have = got[d][i] + (lost["district"].get(d) or [0.0] * 5)[i]
            if abs(have - want) > max(0.5, 0.01 * want):
                bad.append(f"{d} {P.BANDS[i]} {have:.1f} != {want:.1f}")
    out["traffic_densities"] = {"ok": not bad, "detail": (
        f"every district's lanes carry M11's vehicles per hour band (times the fleet's busy "
        f"and the traffic's scale) within 1%; left out: {lost['lanes']} lanes off the lane "
        f"graph's main part and {lost['segments']} segments without a lane "
        f"({max(lost['vehicles']):.1f} cars at the most)" if not bad else "; ".join(bad[:5]))}
    off = [r["id"] for r in rows if not r["main"] and any(v > 0.0 for v in r["vehicles"])]
    tot_m = sum(r["length_m"] for r in rows) or 1.0
    main_m = sum(r["length_m"] for r in rows if r["main"])
    out["traffic_lanes"] = {"ok": not off and main_m >= 0.5 * tot_m, "detail": (
        f"every car on the lane graph's largest strongly connected part "
        f"({traffic['totals']['main_lanes']} of {traffic['totals']['graph_lanes']} lanes and "
        f"connectors, {main_m / tot_m:.1%} of the lanes' length)" if not off else
        f"{len(off)} lanes with cars off the main part, first {off[:3]}")}
    # every signal with lanes that stop at it, each stopping within its lane
    with_lanes = {r["signal"] for r in rows if r["signal"]}
    sbad = [r["id"] for r in rows if r["signal"] and
            not 0.0 <= (r["stop_back_m"] or 0.0) <= r["length_m"]]
    none = [s["id"] for s in sigs if s["id"] not in with_lanes]
    # (a signal no lane ends at, every leg leaving it, is noted, not failed)
    out["traffic_signals"] = {"ok": not sbad, "detail": (
        f"{len(with_lanes)} of {len(sigs)} signals with lanes stopping at them "
        f"({traffic['totals']['signalized']} lanes, each stopping within its lane, short of "
        f"its crosswalk)" + (f"; {len(none)} signals no lane ends at, first {none[:3]}"
                             if none else "")
        if not sbad else f"{len(sbad)} lanes stopping off their lane, first {sbad[:3]}")}
    bud = filled["budgets"]
    pool, live = traffic["pool"], traffic["live_m"]
    in_view = pool * min(1.0, (bud["view_m"] / live) ** 2)
    out["traffic_budget"] = {"ok": in_view <= bud["vehicles_view"] + 0.5, "detail": (
        f"a pool of {pool} cars live within {live:.0f} m of the view, about {in_view:.0f} "
        f"within {bud['view_m']:.0f} m (the budget's {bud['vehicles_view']})")}
    from assetgen.parked.table import EXCLUDED
    ms = traffic["models"]
    ex = [m for m in ms if m in EXCLUDED]
    empty = [d for d, w in traffic["weights"].items()
             if sum(w) <= 0.0 and any((got.get(d) or [0.0])[i] > 0.0 for i in range(5))]
    cnt = traffic["totals"]["slots"]
    out["traffic_fleet"] = {"ok": not ex and not empty and bool(ms) and
                            all(c > 0 for c in cnt.values()), "detail": (
        f"{len(ms)} of AG18's models ({', '.join(ms)}), each in {min(cnt.values()) if cnt else 0} "
        f"to {max(cnt.values()) if cnt else 0} pool slots; every district with cars has a "
        f"fleet; no Vex or Aurel" if not ex and not empty and ms else
        f"excluded {ex}, districts without a fleet {empty}")}
    return out


# ---------------------------------------------------------------------------
# LG4: life at places
# ---------------------------------------------------------------------------

def role_counts(filled: dict, rows: list[dict], drows: list[dict], slots: list[dict]) -> dict:
    """The pools' slots kept for gang members, police on foot and patrol cars
    (`places.reserve`): the most wanted within the crowd's (the traffic's) live radius of any
    tile, at any hour band. {role: (slots, wanted)}."""
    pool = int(filled["crowd"]["pool"])
    cars = int(filled["traffic"]["pool"])
    live = float(P.CROWD["live_m"])
    tlive = float(filled["traffic"]["live_m"])
    want = {"gang": 0.0, "police": 0.0, "cars": 0.0}
    for b in range(len(P.BANDS)):
        g, po, ca = defaultdict(float), defaultdict(float), defaultdict(float)
        for r in rows:
            if r.get("gang"):
                g[r["tile"]] += r["gang"][b]
            if r.get("police"):
                po[r["tile"]] += r["police"][b]
        for s in slots:
            if s.get("role") == "gang":
                g[tile_of(s["pos"][0], s["pos"][1])] += s["use"][b]
        for r in drows:
            if r.get("police"):
                ca[r["tile"]] += r["police"][b]
        want["gang"] = max(want["gang"], PL4.most_near(g, live))
        want["police"] = max(want["police"], PL4.most_near(po, live))
        want["cars"] = max(want["cars"], PL4.most_near(ca, tlive))
    out = {}
    for k, n, share in (("gang", pool, P.ROLES["gang_max_share"]),
                        ("police", pool, P.ROLES["police_max_share"]),
                        ("cars", cars, P.ROLES["car_max_share"])):
        w = want[k]
        if w <= 0.0:
            out[k] = (0, 0.0)
            continue
        keep = int(math.ceil(w * P.ROLES["margin"]))
        out[k] = (max(P.ROLES["min"], min(keep, int(share * n))), _r(w, 1))
    return out


def places_plan(filled: dict, slot_rows: list[dict], place_rows: list[dict],
                left: dict) -> dict:
    """LG4's `places` record: the slot kinds and place kinds, their totals."""
    kinds = list(P.SLOT_KINDS)
    by = {k: {"slots": 0, "points": 0, "use": [0.0] * 5} for k in kinds}
    for s in slot_rows:
        r = by[s["kind"]]
        r["slots"] += 1
        r["points"] += s["capacity"]
        for b in range(5):
            r["use"][b] += (s.get("use") or [0.0] * 5)[b]
    for r in by.values():
        r["use"] = [_r(v, 1) for v in r["use"]]
    pk = defaultdict(lambda: {"places": 0, "open": [0] * P.HOURS, "occupancy": [0.0] * 5})
    for p in place_rows:
        r = pk[p["kind"]]
        r["places"] += 1
        for h in range(P.HOURS):
            r["open"][h] += p["open"][h]
        for b in range(5):
            r["occupancy"][b] += p["occupancy"][b]
    for r in pk.values():
        r["occupancy"] = [_r(v, 1) for v in r["occupancy"]]
    return hashed({
        "hour": int(filled["crowd"]["hour"]),
        "slot_kinds": {k: {**v, "code": i} for i, (k, v) in enumerate(P.SLOT_KINDS.items())},
        "kinds": kinds, "behaviors": list(P.SLOT_BEHAVIORS), "anims": list(P.SLOT_ANIMS),
        "place_kinds": {**P.PLACE_KINDS, "default": P.PLACE_DEFAULT}, "visit_p": P.VISIT_P,
        "totals": {"slots": by, "places": dict(sorted(pk.items())),
                   "slots_all": len(slot_rows), "places_all": len(place_rows),
                   "left_out": left}})


def gangs_plan(turfs: list[dict], gm: dict, slot_rows: list[dict], roles: dict) -> dict:
    """LG4's `gangs` record: each gang turf with its faction's colors, members by band, spots."""
    out = []
    for t in turfs:
        m = gm["turfs"][t["id"]]
        spots = [s for s in slot_rows if s.get("turf_id") == t["id"]]
        out.append({"id": t["id"], "name": t["name"], "district_id": t["district_id"],
                    "faction_id": t["faction"]["id"], "faction": t["faction"]["name"],
                    "colors": PL4.faction_colors(t["faction"]["color"]),
                    "walkways": m["walkways"], "walking": [_r(v, 2) for v in m["walk"]],
                    "loitering": [_r(v, 2) for v in m["loiter"]],
                    "spots": [s["id"] for s in spots],
                    "hideouts": sorted({s["owner_id"] for s in spots
                                        if ".hideout." in s["id"]})})
    return hashed({"turfs": out, "groups": list(P.GANG["groups"]),
                   "loiter": list(P.GANG["loiter"]), "pool": roles["gang"][0],
                   "want_near": roles["gang"][1], "left_out": gm["left"]})


def police_record(pol: dict, roles: dict) -> dict:
    po = P.POLICE
    return hashed({"precincts": pol["precincts"], "patrol_min": po["patrol_min"],
                   "car_share": po["car_share"], "per_car": po["per_car"], "pair": 2,
                   "pool": roles["police"][0], "cars": roles["cars"][0],
                   "want_near": {"foot": roles["police"][1], "cars": roles["cars"][1]},
                   "left_out": pol["left"]})


def places_checks(model, filled, slots, place_rows, rows, drows, turfs, gm, pol, crowd,
                  traffic, roles, spawns, hours) -> dict:
    """LG4's checks: slots on their walkways, clear of buildings and facing their objects; their
    use within their points; places' hours and their doors' rates by them; gang members and
    spots only on their own turf; patrols within the police field and every district's police
    kept; the pools' roles."""
    import shapely
    out = {}
    walks = {w["id"]: w for w in model.get("walkways", [])}
    fp = PL4.Footprints(model)
    bad = []
    for s in slots:
        w = walks.get(s.get("walkway_id"))
        pts = s.get("points") or []
        if not pts or s["capacity"] != len(pts):
            bad.append(f"{s['id']}: {len(pts)} points for capacity {s['capacity']}")
        elif w is None:
            bad.append(f"{s['id']}: no walkway")
        elif any(fp.blocked(p[0], p[1]) for p in pts):
            bad.append(f"{s['id']}: a point in a building or on a carriageway")
        elif PL4._nearest_on(w["line"], pts[0][0], pts[0][1])[2] > P.SLOT_REACH_M + 1.0 and \
                s["kind"] not in ("gang_spot",):
            bad.append(f"{s['id']}: {PL4._nearest_on(w['line'], pts[0][0], pts[0][1])[2]:.1f} m "
                       f"off its walkway")
        elif not PL4._facing_ok(s["kind"], s["_obj"], pts, s.get("_center")):
            bad.append(f"{s['id']}: a user not facing its object")
    kinds = defaultdict(int)
    for s in slots:
        kinds[s["kind"]] += 1
    out["slots_placed"] = {"ok": not bad, "detail": (
        f"{len(slots)} slots ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}), "
        f"each on its walkway (its first point within {P.SLOT_REACH_M:.0f} m), its points out "
        f"of every building and carriageway, each user facing its object (a bench's away "
        f"from its back, a ring's to its middle)" if not bad else "; ".join(bad[:5]))}
    ubad = [s["id"] for s in slots if any(u < 0.0 or u > s["capacity"] + 1e-6
                                          for u in s.get("use") or [])]
    use = [sum((s.get("use") or [0.0] * 5)[b] for s in slots) for b in range(5)]
    out["slot_use"] = {"ok": not ubad, "detail": (
        f"users per band within their slots' points: "
        + ", ".join(f"{P.BANDS[b]} {use[b]:.0f}" for b in range(5))
        if not ubad else f"{len(ubad)} slots used past their points, first {ubad[:3]}")}
    # places by their hours: open hours from their hours, closed doors sending no one, every
    # district's doors keeping its people every hour
    pbad = []
    rate = {s["id"]: s["rates"] for s in spawns}
    for p in place_rows:
        if p["open"] != PL4.open_hours(p["hours"]):
            pbad.append(f"{p['id']}: open hours not its hours")
        r = rate.get(p["spawn_id"]) or [0.0] * P.HOURS
        if any(r[h] > 0.0 and not p["open"][h] for h in range(P.HOURS)):
            pbad.append(f"{p['id']}: people out of its door while closed")
    got = defaultdict(lambda: [0.0] * P.HOURS)
    for s in spawns:
        for h in range(P.HOURS):
            got[s["district_id"]][h] += s["rates"][h]
    turn = 60.0 / P.TRIP_MIN
    for d, h in hours.items():
        if d not in got:
            continue
        for k in range(P.HOURS):
            want = h["people"][k] * turn
            if abs(got[d][k] - want) > max(0.5, 0.01 * want):
                pbad.append(f"{d} {k}:00 doors {got[d][k]:.1f} != {want:.1f}")
                break
    hour = int(filled["crowd"]["hour"])
    opened = defaultdict(lambda: [0, 0])
    for p in place_rows:
        opened[p["kind"]][0] += p["open"][hour]
        opened[p["kind"]][1] += 1
    out["places_hours"] = {"ok": not pbad, "detail": (
        f"{len(place_rows)} places by their hours, their doors closed while they are; every "
        f"district's doors keep its people every hour; open at {hour}:00: "
        + ", ".join(f"{k} {a} of {n}" for k, (a, n) in sorted(opened.items()))
        if not pbad else "; ".join(pbad[:5]))}
    # gangs on their turf
    gbad = []
    shape = {t["id"]: t["shape"] for t in turfs}
    for r in rows:
        if r.get("gang") and any(v > 0.0 for v in r["gang"]):
            w = walks.get(r["id"]) or {}
            mx, my = PL4._mid(w.get("line") or [[0, 0]])
            if r.get("turf") not in shape or not shapely.contains_xy(shape[r["turf"]], mx, my):
                gbad.append(f"{r['id']}: gang members off their turf")
    for s in slots:
        if s["role"] == "gang":
            if s.get("turf_id") not in shape or not all(
                    shapely.contains_xy(shape[s["turf_id"]], p[0], p[1]) for p in s["points"][:1]):
                gbad.append(f"{s['id']}: a gang spot off its turf")
    nturf = sum(1 for t in turfs if gm["turfs"][t["id"]]["walkways"])
    walk_m = sum(max(r["gang"]) for r in rows if r.get("gang"))
    out["gang_turf"] = {"ok": not gbad, "detail": (
        f"{len(turfs)} gang turfs ({nturf} with walkways), their members only on their own "
        f"turf's walkways and spots ({sum(1 for s in slots if s['role'] == 'gang')} spots); up "
        f"to {walk_m:.0f} walking; {max(gm['left']['members']):.0f} of M11's gang members "
        f"outside every gang turf left out" if not gbad else "; ".join(gbad[:5]))}
    # police patrols within the police field, every district's police kept
    obad = []
    pmin = P.POLICE["patrol_min"]
    for r in rows:
        if r.get("police") and any(v > 0.0 for v in r["police"]):
            if not r.get("patrol") or (r.get("field") or 0.0) < pmin:
                obad.append(f"{r['id']}: police off the patrol walkways")
    for r in drows:
        if r.get("police") and any(v > 0.0 for v in r["police"]) and not r["main"]:
            obad.append(f"{r['id']}: a patrol car off the lane graph's main part")
    foot = defaultdict(lambda: [0.0] * 5)
    cars = defaultdict(lambda: [0.0] * 5)
    for r in rows:
        if r.get("police"):
            for b in range(5):
                foot[r["district_id"]][b] += r["police"][b]
    for r in drows:
        if r.get("police"):
            for b in range(5):
                cars[r["district_id"]][b] += r["police"][b]
    pc = P.POLICE
    for d, tot in pol["total"].items():
        for b in range(5):
            have = foot[d][b] + cars[d][b] * pc["per_car"]
            if abs(have - tot[b]) > max(0.5, 0.01 * tot[b]) and \
                    not (pol["left"]["foot"][b] or pol["left"]["cars"][b]):
                obad.append(f"{d} {P.BANDS[b]}: police {have:.1f} != {tot[b]:.1f}")
                break
    stations = sum(1 for p in pol["precincts"] if p["station_doors"])
    out["police_patrols"] = {"ok": not obad, "detail": (
        f"every district's police (M11's) on foot on its patrol walkways (the police field at "
        f"least {pmin}) and in patrol cars on its main lanes; {stations} of "
        f"{len(pol['precincts'])} precincts with a station's doors; at {hour}:00 "
        f"{sum(v[P.band_of(hour)] for v in foot.values()):.0f} on foot, "
        f"{sum(v[P.band_of(hour)] for v in cars.values()):.0f} patrol cars"
        if not obad else "; ".join(obad[:5]))}
    # the pools' roles
    ps = crowd["persons"]
    role = ps.get("role") or []
    g = G.GROUPS
    rbad = []
    for k, r in enumerate(role):
        if r and g[ps["group"][k]] != P.ROLE_CODES[r]:
            rbad.append(f"pool slot {k}: a {P.ROLE_CODES[r]} in a {g[ps['group'][k]]} look")
    kept = sum(1 for r in role if r)
    if kept > 0.25 * crowd["pool"]:
        rbad.append(f"{kept} of the pool's {crowd['pool']} kept for gangs and police")
    ps_ = traffic.get("police_slots") or []
    if any(traffic["slots"][k] != traffic["models"].index(traffic["police_model"])
           for k in ps_):
        rbad.append("a patrol car's slot not of the police model")
    notes = []
    for k, name in (("gang", "gang members"), ("police", "police on foot"),
                    ("cars", "patrol cars")):
        n, w = roles[k]
        notes.append(f"{name} {n} kept ({w:.0f} wanted near the view at most"
                     + (", scaled down there" if w > n else "") + ")")
    out["places_budget"] = {"ok": not rbad, "detail": (
        "; ".join(notes) + f"; patrol cars {traffic.get('police_model')}"
        if not rbad else "; ".join(rbad[:5]))}
    return out


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def walk_components(walks: list[dict]) -> dict[str, int]:
    """Walkway id -> its connected component (the walkway graph's neighbors), every level."""
    idx = {w["id"]: i for i, w in enumerate(walks)}
    parent = list(range(len(walks)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, w in enumerate(walks):
        for n in w.get("neighbors") or []:
            j = idx.get(n)
            if j is not None:
                a, b = find(i), find(j)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    return {w["id"]: find(i) for i, w in enumerate(walks)}


def run_checks(model, spawns, slot_rows, hours, filled, spike) -> dict:
    walk_ids = {w["id"] for w in model.get("walkways", [])}
    lane_ids = {ln["id"] for ln in model.get("lanes", [])}
    out = {}
    off = [s["id"] for s in spawns if s["walkway_id"] not in walk_ids or
           (s["lane_id"] is not None and s["lane_id"] not in lane_ids)]
    out["spawns_on_graph"] = {"ok": not off, "detail": (
        f"{len(spawns)} spawn points, each on a walkway (and a drive lane where it has one)"
        if not off else f"{len(off)} off the graphs, first {off[:5]}")}
    comp = walk_components(model.get("walkways", []))
    per = defaultdict(int)
    for s in spawns:
        per[comp.get(s["walkway_id"])] += 1
    alone = [s["id"] for s in spawns if per[comp.get(s["walkway_id"])] < 2]
    out["spawns_reach"] = {"ok": not alone, "detail": (
        f"every spawn point's walkway reaches another spawn point ({len(per)} walkway "
        f"components with spawns; the largest holds "
        f"{max(per.values()) if per else 0} of {len(spawns)})" if not alone else
        f"{len(alone)} spawn points reach no other, first {alone[:5]}")}
    bad = []
    for d, h in hours.items():
        fd = filled["districts"][d]
        for i, (_, a, b) in enumerate(P.HOUR_BANDS):
            want = h["band"]["crowd"][i] * fd["busy"]
            got = sum(h["people"][a:b]) / (b - a)
            if abs(got - want) > max(0.5, 0.01 * want):
                bad.append(f"{d} {P.BANDS[i]} {got:.1f} != {want:.1f}")
    out["densities"] = {"ok": not bad, "detail": (
        "every district's people per hour band keep M11's densities (times its busy) within "
        "1%" if not bad else "; ".join(bad[:5]))}
    badslot = [s["id"] for s in slot_rows if not math.isfinite(s["yaw_deg"])]
    out["slots"] = {"ok": not badslot, "detail": f"{len(slot_rows)} slots, each facing its "
                                                 f"object's way" if not badslot else
                    f"{len(badslot)} without a facing"}
    bud = filled["budgets"]
    if spike is not None:
        ok = spike["people"] <= bud["people_view"] and spike["cars"] <= bud["vehicles_view"]
        out["spike_budget"] = {"ok": ok, "detail": (
            f"the spike's {spike['people']} people and {spike['cars']} cars within the "
            f"budget's {bud['people_view']} and {bud['vehicles_view']}")}
        # (LG1) every character of the library among the spike's people, none of them more
        # than PEOPLE_SHARE_MAX of the crowd
        ps = spike.get("persons") or {}
        chars = ps.get("character") or []
        n = (spike.get("library") or {}).get("characters") or 0
        if chars and n:
            cnt = [chars.count(k) for k in range(n)]
            most = max(cnt) / len(chars)
            # (a crowd of a few people cannot spread over the library: only past 10 a character)
            ok = len(chars) < 10 * n or (min(cnt) > 0 and most <= PEOPLE_SHARE_MAX)
            out["people_draws"] = {"ok": ok, "detail": (
                f"the spike's {len(chars)} people drawn from {n} characters, each "
                f"{min(cnt)} to {max(cnt)} of them (at most {PEOPLE_SHARE_MAX:.0%}), "
                f"{len(set(ps.get('seed') or []))} distinct seeds")}
    return out


# (LG1) no character of the library more than this share of a crowd
PEOPLE_SHARE_MAX = 0.12


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def library_cars() -> list[str]:
    from citygen.unreal_vehicles import DEFAULT_LIBRARY, library_cars as lc
    cars = lc(DEFAULT_LIBRARY)
    if cars:
        return cars
    from assetgen.parked.table import CLASS, EXCLUDED
    return sorted(c for c in CLASS if c not in EXCLUDED)


def _pick(items: dict, *salt) -> str:
    keys = sorted(items)
    x = _u(*salt) * sum(items[k] for k in keys)
    for k in keys:
        x -= items[k]
        if x < 0.0:
            return k
    return keys[-1]


def _centroid(b: dict) -> tuple[float, float]:
    ring = (b.get("footprint") or {}).get("exterior") or [[0.0, 0.0]]
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def road_classes(model: dict, mid, reach: float) -> dict[str, str]:
    """cars_steam: the road class of every segment with a point within `reach` of the
    spike's middle (its lanes' cruise speed, `presets.DRIVE_SPEEDS`; a class without a speed
    of its own drives as `DRIVE["default"]`)."""
    out = {}
    r2 = reach * reach
    for s in model.get("road_segments", []):
        if any((p[0] - mid[0]) ** 2 + (p[1] - mid[1]) ** 2 <= r2
               for p in s.get("centerline") or []):
            rc = s.get("road_class") or P.DRIVE["default"]
            out[s["id"]] = rc if rc in P.DRIVE_SPEEDS else P.DRIVE["default"]
    return dict(sorted(out.items()))


def spike_plan(model: dict, filled: dict, hours: dict) -> dict | None:
    sp = filled["spike"]
    ds = {d["id"]: d for d in model.get("districts", [])}
    if not ds:
        return None
    if sp.get("district"):
        did = next(d for d, r in ds.items() if r.get("name") == sp["district"])
    else:
        count = defaultdict(int)
        for b in model.get("buildings", []):
            if b.get("district_id") in ds:
                count[b["district_id"]] += 1
        did = min(ds, key=lambda d: (-count[d], d))
    # (LG3: the city's crowd walks every street; the spike keeps its cars until LG5's
    # traffic, and people only when the spec asks for them)
    people = int(sp.get("people") or 0)
    fleet = filled["districts"][did]["fleet"]
    models = sorted(fleet.items(), key=lambda kv: (-kv[1], kv[0]))
    ring = (ds[did].get("polygon") or {}).get("exterior") or []
    # (its middle: the building nearest its buildings' centroid, as the benchmark's walk
    # starts by its stage 2 actors; the stand-ins live within `radius_m` of it, the
    # budget's 2,000 people within 300 m of the view)
    bs = [b for b in model.get("buildings", []) if b.get("district_id") == did]
    if bs:
        cs = [_centroid(b) for b in bs]
        cx = sum(c[0] for c in cs) / len(cs)
        cy = sum(c[1] for c in cs) / len(cs)
        mid = min(cs, key=lambda c: ((c[0] - cx) ** 2 + (c[1] - cy) ** 2, c[0], c[1]))
    else:
        mid = (sum(p[0] for p in ring) / max(1, len(ring)), sum(p[1] for p in ring) /
               max(1, len(ring)))
    # (the stand-ins' clothes: the district's style's groups by weight, each a color of its
    # group's, a gang's its faction's color)
    palette = district_palette(model, filled, did)
    # (LG1: who each of them is, by their seed: a character of the people library, a height
    # scale, a gait, a pace, the outfit's tint from the palette)
    n = L.CHARACTERS
    cols = {k: [] for k in PERSON_COLUMNS}
    for k in range(int(people)):
        p = draw_person(("lg1.person", did, k), n, palette=palette)
        for c in PERSON_COLUMNS:
            cols[c].append(p[c])
    return hashed({"district_id": did, "name": ds[did].get("name"), "hour": sp["hour"],
                   "palette": palette,
                   "library": {"version": L.LIB_VERSION, "characters": n,
                               "walks": list(L.WALKS), "tiers": dict(sorted(L.TIERS.items()))},
                   "persons": cols,
                   "center": [_r(mid[0], 2), _r(mid[1], 2)], "radius_m": P.SPIKE["radius_m"],
                   "people": int(people), "cars": int(sp["cars"]),
                   "models": [{"model": m, "weight": w} for m, w in models],
                   "walk_kinds": list(P.SPIKE_WALK_KINDS),
                   "walk_speed": list(P.SPIKE["walk_speed"]),
                   "drive_speed": list(P.SPIKE["drive_speed"]),
                   "car_gap_m": P.SPIKE["car_gap_m"],
                   # (cars_steam: each lane's speed by its road's class, its curves, its
                   # junctions)
                   "drive_speeds": dict(sorted(P.DRIVE_SPEEDS.items())),
                   "drive": {k: (list(v) if isinstance(v, list) else v)
                             for k, v in sorted(P.DRIVE.items())},
                   "road_classes": road_classes(model, mid, P.SPIKE["radius_m"] + 80.0),
                   "polygon": [[_r(x, 2), _r(y, 2)] for x, y in ring]})


def walk_heights(build: Path, model: dict, ground) -> dict:
    """people_surfaces: `walk_heights`, the walkway lines the runtime walks (BUILD/graphs.json,
    which `citygen.walksurf` drapes on the surface stage 2 draws) against that surface,
    sampled every 0.5 m (`walksurf.check`): none more than `CHECK_FAIL_M` off it outside a
    step in the surface (a curb, which a line rounds off over a meter); noted, those more than
    `CHECK_TOL_M` off. A graphs.json from before (heights at the model's vertices only) is
    not measured."""
    from citygen import walksurf as WS

    gp = build / "graphs.json"
    if not gp.is_file():
        return {"ok": True, "detail": "no graphs.json: not measured"}
    g = json.loads(gp.read_text(encoding="utf-8"))
    if not g.get("walk_surface"):
        return {"ok": True, "detail": "graphs.json's walkways from before people_surfaces "
                                      "(heights at the model's vertices): not measured"}
    lines = {w["id"]: w["line"] for w in g.get("walkways") or []}
    gfun = (lambda wid, x, y: ground.one(x, y)) if g.get("heights") == "absolute" else None
    r = WS.check(model, lines, ground=gfun)
    detail = (f"{r['walkways']} walkways on the surface within {WS.CHECK_TOL_M * 100:.0f} cm "
              f"but {r['off']} (worst {r['worst_m']} m; {r['at_steps']} samples at steps in "
              f"the surface left out)")
    if r["first"]:
        detail += ": " + "; ".join(r["first"][:5])
    return {"ok": r["failed"] == 0, "detail": detail}


def build_plan(build: str | Path, spec_path: str | Path | None = None,
               out: str | Path | None = None, preview: bool = True,
               atmos: str | Path | None = None) -> dict:
    t0 = time.time()
    build = Path(build)
    mpath = build / "city_model.json"
    raw = mpath.read_bytes()
    model = json.loads(raw)
    res = S.load_spec(spec_path, model)
    if not res.ok:
        raise ValueError("life spec: " + "; ".join(str(i) for i in res.errors))
    cars = library_cars()
    filled = S.fill(res.spec, model.get("districts", []), cars)
    city = model.get("name") or build.name
    out = Path(out) if out else build / "life"
    wrote: list[str] = []

    hours = district_hours(model, filled)
    walk_by = {w["id"]: w for w in model.get("walkways", [])}
    import shapely
    polys = [(d["id"], shapely.Polygon(d["polygon"]["exterior"],
                                       [h for h in d["polygon"].get("holes", [])]))
             for d in sorted(model.get("districts", []), key=lambda d: d["id"])
             if d.get("polygon")]
    raw_spawns = spawn_points(model, walk_by, door_points(build, model, walk_by))
    for rec, _ in raw_spawns:
        if rec["district_id"] is None:
            rec["district_id"] = _district_at(polys, rec["pos"][0], rec["pos"][1])
        rec["tile"] = tile_of(rec["pos"][0], rec["pos"][1])
    wsum = defaultdict(float)
    for rec, w in raw_spawns:
        wsum[rec["district_id"]] += w
    turn = 60.0 / P.TRIP_MIN
    recs = []
    for rec, w in sorted(raw_spawns, key=lambda rw: rw[0]["id"]):
        d = rec["district_id"]
        ppl = hours[d]["people"] if d in hours else [0.0] * P.HOURS
        share = w / wsum[d] if wsum[d] > 0 else 0.0
        rec["rates"] = [_r(ppl[h] * turn * share, 3) for h in range(P.HOURS)]
        # (LG1: the people a spawn point sends out are drawn from its seed and their count,
        # `library.person((seed, n), ...)`)
        rec["seed"] = L.person((rec["id"],), 1)["seed"]
        recs.append(rec)
    # LG4: the shop doors as places by their hours, their doors' rates by them
    places = PL4.make_places(model, recs)
    PL4.apply_hours(recs, places)
    spawns = [hashed(r) for r in recs]

    # LG3: the signals, every walkway's people
    sigs, sig_of = signals(model)
    rows, left = crowd_walks(model, filled, polys, sig_of, {s["walkway_id"] for s in spawns})
    # LG5: every lane's cars
    drows, dleft = traffic_lanes(model, filled, sigs)
    # LG4: the slots, gangs on their turf, police patrols, the pools' roles
    row_by = {r["id"]: r for r in rows}
    # (delta_rebuild: the surface stage 2 draws: a slot leaves from a walkway at its height,
    # and every ground level slot's points stand on it)
    surface = PL4.Surface(model)
    wi = PL4.WalkIndex(model.get("walkways", []), surface)
    fp = PL4.Footprints(model)
    slot_raw, sleft = PL4.make_slots(model, wi, fp, row_by, places)
    turfs = PL4.gang_turfs(model)
    gm = PL4.gang_walks(model, filled, rows, turfs)
    slot_raw += PL4.gang_spots(model, turfs, gm, row_by, wi, fp)
    seat_stats = PL4.seat_slots(slot_raw, surface)
    # (city open items: every slot leaves from a walkway at its height, else it is left out)
    slot_raw, lvl_stats = PL4.level_slots(slot_raw, wi, row_by)
    sleft["not_at_height"] = lvl_stats["dropped"]
    sleft["moved_to_height"] = lvl_stats["moved"]
    seat_stats["seated"] -= lvl_stats["dropped"]
    pol = PL4.police_plan(model, filled, rows, drows, spawns)
    # LG8: each walkway's stretches out of the rain (atmosgen's rain shadow), nightlife round
    # the bars, clubs and arcades, the weather's table
    adir = WX.atmos_dir(build, atmos)
    cover, cstats = WX.walk_cover(model, WX.Masks(adir) if adir else None, AW.Ground(model))
    night = WX.nightlife(model, places)
    sides = WX.road_sides(model, cover)
    for r in rows:
        if r["id"] in cover:
            r["cover"] = cover[r["id"]]
        if r["id"] in sides:
            r["road_side"] = sides[r["id"]]
        if r["id"] in night:
            r["night"] = night[r["id"]]
    weather = WX.weather_record(filled, cstats, night, adir)
    roles = role_counts(filled, rows, drows, slot_raw)
    crowd = crowd_plan(model, filled, rows, sigs, left,
                       roles=(roles["gang"][0], roles["police"][0]))
    traffic = traffic_plan(model, filled, drows, dleft, police_cars=roles["cars"][0])
    walk_rows = [hashed({k: v for k, v in r.items() if k != "tile"}) for r in rows]
    drive_rows = [hashed({k: v for k, v in r.items() if k != "tile"}) for r in drows]
    slot_rows = []
    for s in sorted(slot_raw, key=lambda s: s["id"]):
        if s["district_id"] is None or s["district_id"] not in hours:
            s["district_id"] = _district_at(polys, s["pos"][0], s["pos"][1])
        s["tile"] = tile_of(s["pos"][0], s["pos"][1])
        slot_rows.append(hashed({k: v for k, v in s.items() if not k.startswith("_")}))
    place_rows = []
    for pl in sorted(places, key=lambda p: p["id"]):
        pl["tile"] = tile_of(pl["pos"][0], pl["pos"][1])
        place_rows.append(hashed(pl))
    places_rec = places_plan(filled, slot_rows, place_rows, sleft)
    gangs_rec = gangs_plan(turfs, gm, slot_rows, roles)
    police_rec = police_record(pol, roles)
    # LG6: every transit line's timetable, its stops, trains and boarding
    tlines, tleft = TR.transit_plan(model, filled, spawns)
    ttab = PM.Timetables(city=city, lines=TR.timetables(tlines))
    ttext = canon(json.loads(ttab.model_dump_json()))
    write(out / "timetables.json", ttext, wrote)
    transit_rec = hashed({**TR.plan_record(tlines, tleft, crowd["hour"]),
                          "file": "timetables.json",
                          "sha256": hashlib.sha256(ttext.encode("utf-8")).hexdigest()})
    # LG7: what flies and what floats, every route to a timetable; the pads and piers
    aw_routes, aw_pads, aw_piers, aw_extra = AW.airwater_plan(model, filled, build)
    awdata = PM.AirWater(city=city, routes=AW.records(aw_routes), pads=aw_pads, piers=aw_piers)
    awtext = canon(json.loads(awdata.model_dump_json()))
    write(out / "airwater.json", awtext, wrote)
    aw_rec = hashed({**AW.plan_record(aw_routes, aw_pads, aw_piers, aw_extra["left"],
                                      crowd["hour"]),
                     "file": "airwater.json",
                     "sha256": hashlib.sha256(awtext.encode("utf-8")).hexdigest()})

    # per tile
    by_tile = defaultdict(lambda: {"spawns": [], "slots": [], "walks": [], "drives": [],
                                   "places": []})
    for s in spawns:
        by_tile[s["tile"]]["spawns"].append(s)
    for s in slot_rows:
        by_tile[s["tile"]]["slots"].append(s)
    for p in place_rows:
        by_tile[p["tile"]]["places"].append(p)
    for r, w in sorted(zip(rows, walk_rows), key=lambda rw: rw[1]["id"]):
        by_tile[r["tile"]]["walks"].append(w)
    for r, w in sorted(zip(drows, drive_rows), key=lambda rw: rw[1]["id"]):
        by_tile[r["tile"]]["drives"].append(w)
    tiles = []
    keep = set()
    for t in sorted(by_tile):
        rec = PM.TileSpawns(city=city, tile=t, bounds=tile_bounds(t), **by_tile[t])
        text = canon(json.loads(rec.model_dump_json()))
        f = out / "spawns" / f"{t}.json"
        keep.add(f.name)
        write(f, text, wrote)
        tiles.append({"tile": t, "file": f"spawns/{t}.json", "spawns": len(by_tile[t]["spawns"]),
                      "slots": len(by_tile[t]["slots"]), "walks": len(by_tile[t]["walks"]),
                      "drives": len(by_tile[t]["drives"]),
                      "places": len(by_tile[t]["places"]),
                      "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    if (out / "spawns").is_dir():
        for f in sorted((out / "spawns").glob("*.json")):
            if f.name not in keep:
                f.unlink()
                wrote.append(f"removed {f}")

    nsp = defaultdict(int)
    nsl = defaultdict(int)
    for s in spawns:
        nsp[s["district_id"]] += 1
    for s in slot_rows:
        nsl[s["district_id"]] += 1
    districts = []
    for d, fd in filled["districts"].items():
        h = hours[d]
        districts.append(hashed({"id": d, "name": fd["name"], "archetype": fd["archetype"],
                                 "wealth": fd["wealth"], "danger": fd["danger"],
                                 "busy": fd["busy"], "mix": fd["mix"], "shape": fd["shape"],
                                 "style": fd["style"], "fleet": fd["fleet"],
                                 "street_m": h["street_m"], "people": h["people"],
                                 "vehicles": h["vehicles"], "gangs": h["gangs"],
                                 "police": h["police"], "spawns": nsp[d], "slots": nsl[d]}))
    spike = spike_plan(model, filled, hours)
    checks = run_checks(model, spawns, slot_rows, hours, filled, spike)
    checks.update(crowd_checks(model, rows, hours, filled, sigs, crowd, spawns))
    checks.update(traffic_checks(model, drows, hours, filled, sigs, traffic))
    checks.update(places_checks(model, filled, slot_raw, place_rows, rows, drows, turfs, gm,
                                pol, crowd, traffic, roles, spawns, hours))
    checks["slot_heights"] = PL4.height_check(model, slot_raw, surface, seat_stats)
    checks["walk_heights"] = walk_heights(build, model, surface.ground)
    checks.update(TR.checks(model, tlines, tleft, walk_components(model.get("walkways", [])),
                            spawns))
    checks.update(AW.checks(aw_routes, aw_pads, aw_piers, aw_extra))
    checks.update(WX.checks(model, rows, place_rows, weather))
    sdata = PM.Signals(city=city, derived=True, signals=sigs)
    write(out / "signals.json", canon(json.loads(sdata.model_dump_json())), wrote)
    asks = A.status(model, {"doors": (build / "assets" / "unreal_contribution.buildings.json")
                            .is_file()})
    totals = {"spawns": len(spawns), "slots": len(slot_rows), "tiles": len(tiles),
              "people_peak": _r(max(sum(h["people"][k] for h in hours.values())
                                    for k in range(P.HOURS)), 1),
              "vehicles_peak": _r(max(sum(h["vehicles"][k] for h in hours.values())
                                      for k in range(P.HOURS)), 1),
              "spawns_without_walkway": 0,
              "doors": sum(1 for s in spawns if s["kind"] == "door"),
              "walkways": len(rows), "signals": len(sigs),
              "lanes": len(drows),
              "cars_at_hour": traffic["totals"]["cars_by_hour"][traffic["hour"]],
              "places": len(place_rows),
              "transit_lines": len(tlines),
              "trains_at_hour": transit_rec["totals"]["trains_at_hour"],
              "air_routes": sum(1 for r in aw_routes if r["kind"] in P.AIR_KINDS),
              "water_routes": sum(1 for r in aw_routes if r["kind"] in P.WATER_KINDS),
              "fliers_at_hour": aw_rec["totals"]["air_at_hour"],
              "boats_at_hour": aw_rec["totals"]["water_at_hour"]}
    body = {"city": city, "model_sha256": hashlib.sha256(raw).hexdigest(),
            "spec": {k: v for k, v in filled.items() if k != "districts"},
            "bands": list(P.BANDS), "districts": districts, "tiles": tiles, "asks": asks,
            "spike": spike, "crowd": crowd, "traffic": traffic, "places": places_rec,
            "gangs": gangs_rec, "police": police_rec, "transit": transit_rec,
            "airwater": aw_rec, "weather": weather, "checks": checks, "totals": totals}
    plan_hash = _sha([body["spec"], [d["hash"] for d in districts],
                      [t["sha256"] for t in tiles], spike and spike["hash"], crowd["hash"],
                      sdata.model_dump(mode="json"), traffic["hash"], places_rec["hash"],
                      gangs_rec["hash"], police_rec["hash"]] +
                     ([transit_rec["hash"]] if tlines else []) +
                     ([aw_rec["hash"]] if aw_routes else []) +
                     [_sha(weather)])
    plan = PM.LifePlan(plan_hash=plan_hash, **body)
    pdata = json.loads(plan.model_dump_json())
    write(out / "life_plan.json", canon(pdata), wrote)

    entries = []
    if spike is not None:
        entries.append({"key": "life", "kind": "life_controller", "hash": _sha([plan_hash]),
                        "tile": None,
                        "count": spike["people"] + spike["cars"] + crowd["pool"] +
                        traffic["pool"]})
    for t in tiles:
        entries.append({"key": f"life.spawns.{t['tile']}", "kind": "spawner",
                        "hash": t["sha256"][:16], "tile": t["tile"], "count": t["spawns"]})
    # (LG6: a transit vehicle per train of every line, keyed by its id, its line's timetable's
    # hash; the controller draws and runs them)
    for ln in tlines:
        h = _sha({k: v for k, v in ln.items() if not k.startswith("_")})
        for tid in ln["train_ids"]:
            entries.append({"key": tid, "kind": "train", "hash": h, "tile": None,
                            "count": ln["cars"]})
    # (LG7: a route of what flies or floats, keyed by its id, its record's hash; the
    # controller draws and runs its vehicles)
    for r in AW.records(aw_routes):
        entries.append({"key": r["id"], "kind": "air_route" if r["kind"] in P.AIR_KINDS
                        else "water_route", "hash": _sha(r), "tile": None,
                        "count": max(r["counts"])})
    con = PM.Contribution(city=city, plan_hash=plan_hash, entries=entries)
    write(out / "unreal_contribution.life.json", canon(json.loads(con.model_dump_json())),
          wrote)
    ok = all(c["ok"] for c in checks.values())
    rep = {"city": city, "ok": ok, "plan_hash": plan_hash, "out": str(out),
           "checks": checks, "totals": totals,
           "districts": {d["id"]: {"name": d["name"], "people_23": d["people"][23],
                                   "people_peak": max(d["people"]),
                                   "vehicles_peak": max(d["vehicles"]),
                                   "spawns": d["spawns"], "slots": d["slots"]}
                         for d in districts},
           "spike": spike and {k: spike[k] for k in ("district_id", "name", "hour", "people",
                                                     "cars")},
           "crowd": {"hour": crowd["hour"], "pool": crowd["pool"],
                     "live_m": crowd["live_m"],
                     **{k: crowd["totals"][k] for k in ("walkways", "with_people", "levels",
                                                        "signals")},
                     "people_at_hour": _r(crowd["totals"]["street_people"][crowd["hour"]] +
                                          crowd["totals"]["offstreet_people"][crowd["hour"]],
                                          1),
                     "left_out": crowd["totals"]["left_out"]},
           "traffic": {"hour": traffic["hour"], "pool": traffic["pool"],
                       "live_m": traffic["live_m"], "models": len(traffic["models"]),
                       **{k: traffic["totals"][k] for k in ("lanes", "with_cars",
                                                            "main_lanes", "graph_lanes",
                                                            "signalized")},
                       "cars_at_hour": traffic["totals"]["cars_by_hour"][traffic["hour"]],
                       "cars_peak": max(traffic["totals"]["cars_by_hour"]),
                       "left_out": {k: traffic["totals"]["left_out"][k]
                                    for k in ("lanes", "segments", "vehicles")}},
           "places": {"slots": {k: v for k, v in places_rec["totals"]["slots"].items()
                                if v["slots"]},
                      "places": {k: {"places": v["places"],
                                     "open_at_hour": v["open"][crowd["hour"]]}
                                 for k, v in places_rec["totals"]["places"].items()},
                      "left_out": places_rec["totals"]["left_out"]},
           "gangs": {"turfs": [{"id": t["id"], "faction": t["faction"], "walkways": t["walkways"],
                                "walking": t["walking"][P.band_of(crowd["hour"])],
                                "loitering": t["loitering"][P.band_of(crowd["hour"])],
                                "spots": len(t["spots"])} for t in gangs_rec["turfs"]],
                     "pool": gangs_rec["pool"], "want_near": gangs_rec["want_near"],
                     "left_out": gangs_rec["left_out"]},
           "transit": {"lines": [{"id": ln["id"], "name": ln["name"], "mode": ln["mode"],
                                  "loop": ln["loop"], "length_m": ln["length_m"],
                                  "stops": len(ln["stops"]), "cycle_s": ln["cycle_s"],
                                  "trains": ln["trains"], "headway_min": ln["headway_min"],
                                  "top_mps": ln["runs"]["top_mps"], "notes": ln["notes"]}
                                 for ln in tlines],
                       **{k: transit_rec["totals"][k] for k in
                          ("trains_at_hour", "cars_at_hour", "boarding_at_hour")},
                       "left_out": transit_rec["totals"]["left_out"]},
           "airwater": {"kinds": {k: {"routes": v["routes"], "by_band": v["vehicles_by_band"]}
                                  for k, v in aw_rec["kinds"].items()},
                        **{k: aw_rec["totals"][k] for k in
                           ("air_at_hour", "water_at_hour", "pads", "pads_served", "piers",
                            "piers_served")},
                        "left_out": {k: len(v) for k, v in aw_extra["left"].items()}},
           "police": {"precincts": [{"id": p["id"], "station_doors": len(p["station_doors"]),
                                     "foot": p["foot"][P.band_of(crowd["hour"])],
                                     "cars": p["cars"][P.band_of(crowd["hour"])]}
                                    for p in police_rec["precincts"]],
                      "pool": police_rec["pool"], "cars": police_rec["cars"],
                      "want_near": police_rec["want_near"], "model": traffic["police_model"]},
           "asks": {a["id"]: a["status"] for a in asks}}
    write(out / "life_report.json", canon(rep), wrote)
    write(out / "life_report.txt", report_text(rep), wrote)
    if preview:
        img = preview_crowds(model, hours, filled, spike, out / "preview_crowds.png")
        if img:
            wrote.append(img)
        img = PL4.preview_places(model, slot_rows, place_rows, rows, turfs, pol, crowd["hour"],
                                 out / "preview_places.png")
        if img:
            wrote.append(img)
        if tlines:
            img = TR.preview(model, tlines, crowd["hour"], out / "preview_transit.png")
            if img:
                wrote.append(img)
        if aw_routes:
            img = AW.preview(model, aw_routes, aw_pads, aw_piers, crowd["hour"],
                             out / "preview_airwater.png")
            if img:
                wrote.append(img)
        # (LG8: the stretches out of the rain, nightlife, the weather's table)
        img = WX.preview(model, rows, weather, out / "preview_weather.png")
        if img:
            wrote.append(img)
    rep["wrote"] = wrote
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def report_text(rep: dict) -> str:
    L = [f"lifegen plan: {rep['city']} ({'ok' if rep['ok'] else 'FAILED'}), plan "
         f"{rep['plan_hash']}", ""]
    t = rep["totals"]
    L.append(f"spawn points {t['spawns']}, slots {t['slots']}, tiles {t['tiles']}; people on "
             f"the streets at the peak hour {t['people_peak']:.0f}, vehicles "
             f"{t['vehicles_peak']:.0f}")
    L.append("")
    L.append("district  people@23  people peak  vehicles peak  spawns  slots  name")
    for d, r in rep["districts"].items():
        L.append(f"{d:8}  {r['people_23']:9.0f}  {r['people_peak']:11.0f}  "
                 f"{r['vehicles_peak']:13.0f}  {r['spawns']:6}  {r['slots']:5}  {r['name']}")
    if rep.get("crowd"):
        c = rep["crowd"]
        lo = c["left_out"]
        L += ["", f"crowd: {c['people_at_hour']:.0f} people on {c['with_people']} of "
                  f"{c['walkways']} walkways at {c['hour']}:00 (levels {c['levels']}), a pool "
                  f"of {c['pool']} live within {c['live_m']:.0f} m of the view; "
                  f"{c['signals']} signals; left out: {lo['walkways']} walkways no spawn "
                  f"reaches, {lo['segments']} segments without a walkway"]
    if rep.get("traffic"):
        c = rep["traffic"]
        lo = c["left_out"]
        L += ["", f"traffic: {c['cars_at_hour']:.0f} cars on {c['with_cars']} of {c['lanes']} "
                  f"lanes at {c['hour']}:00 ({c['cars_peak']:.0f} at the busiest hour), "
                  f"{c['models']} models; a pool of {c['pool']} live within {c['live_m']:.0f} m "
                  f"of the view; {c['signalized']} lanes stop at signals; left out: "
                  f"{lo['lanes']} lanes off the lane graph's main part, {lo['segments']} "
                  f"segments without a lane"]
    if rep.get("places"):
        c = rep["places"]
        L += ["", "slots: " + ", ".join(f"{k} {v['slots']} ({v['points']} points, users by "
                                        f"band {v['use']})" for k, v in c["slots"].items())]
        L.append("places (open at the crowd's hour): " + ", ".join(
            f"{k} {v['open_at_hour']}/{v['places']}" for k, v in c["places"].items()))
        L.append(f"slots left out: {c['left_out']}")
    if rep.get("gangs"):
        c = rep["gangs"]
        L += ["", f"gangs: {len(c['turfs'])} turfs, {c['pool']} pool slots kept "
                  f"({c['want_near']:.0f} wanted near the view at most); left out "
                  f"{c['left_out']}"]
        for t in c["turfs"]:
            L.append(f"  {t['id']} {t['faction']}: {t['walkways']} walkways, "
                     f"{t['walking']:.0f} walking, {t['loitering']:.0f} at {t['spots']} spots")
    if rep.get("police"):
        c = rep["police"]
        L += ["", f"police: {c['pool']} pool slots on foot, {c['cars']} patrol cars "
                  f"({c['model']}), wanted near the view {c['want_near']}"]
        for p in c["precincts"]:
            L.append(f"  {p['id']}: {p['foot']:.0f} on foot, {p['cars']:.1f} cars, "
                     f"{p['station_doors']} station doors")
    if rep.get("transit") and rep["transit"]["lines"]:
        c = rep["transit"]
        L += ["", f"transit: {len(c['lines'])} lines, {c['trains_at_hour']} trains "
                  f"({c['cars_at_hour']} cars) at the crowd's hour, "
                  f"{c['boarding_at_hour']:.0f} people boarding a hour; left out "
                  f"{c['left_out']}"]
        for ln in c["lines"]:
            L.append(f"  {ln['id']} {ln['name']} ({ln['mode']}{', loop' if ln['loop'] else ''}): "
                     f"{ln['length_m']:.0f} m, {ln['stops']} stops, a {ln['cycle_s']:.0f} s "
                     f"cycle, trains by band {ln['trains']}, every {ln['headway_min']} min, "
                     f"top {ln['top_mps']:.1f} m/s" +
                     (f"; {'; '.join(ln['notes'])}" if ln["notes"] else ""))
    if rep.get("airwater"):
        c = rep["airwater"]
        L += ["", f"air and water: {c['air_at_hour']} fliers and {c['water_at_hour']} boats at "
                  f"the crowd's hour; pads {c['pads_served']} of {c['pads']} flown from, piers "
                  f"{c['piers_served']} of {c['piers']} called at; left out {c['left_out']}"]
        for k, v in c["kinds"].items():
            L.append(f"  {k}: {v['routes']} routes, vehicles by band {v['by_band']}")
    if rep.get("spike"):
        s = rep["spike"]
        L += ["", f"spike: {s['name']} ({s['district_id']}) at {s['hour']}:00, {s['people']} "
                  f"people, {s['cars']} cars"]
    L += ["", "checks:"]
    for k, c in rep["checks"].items():
        L.append(f"  {'ok  ' if c['ok'] else 'FAIL'} {k}: {c['detail']}")
    L += ["", "asks: " + ", ".join(f"{k} {v}" for k, v in rep["asks"].items()), ""]
    return "\n".join(L)


def preview_crowds(model: dict, hours: dict, filled: dict, spike: dict | None,
                   path: Path) -> str | None:
    """The streets by people per 100 m at the spike's hour (each segment's band density
    times its district's shape), the spike's district outlined; beside it each district's
    people by hour."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
    except ImportError:
        return None
    hour = spike["hour"] if spike else 23
    segs = {s["id"]: s for s in model.get("road_segments", [])}
    lines, vals = [], []
    for row in model.get("densities", []):
        s = segs.get(row.get("segment_id"))
        d = row.get("district_id")
        if s is None or d not in filled["districts"]:
            continue
        fd = filled["districts"][d]
        v = float(row["crowd_per_100m"][P.band_of(hour)]) * fd["shape"][hour] * fd["busy"]
        lines.append([(p[0], p[1]) for p in s["centerline"]])
        vals.append(v)
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(16, 8), dpi=110,
                                 gridspec_kw={"width_ratios": [1.15, 1]})
    fig.patch.set_facecolor("#0c111a")
    for a in (ax, bx):
        a.set_facecolor("#0c111a")
        for sp in a.spines.values():
            sp.set_color("#3a4253")
        a.tick_params(colors="#9aa6bd")
    vmax = max(vals) if vals else 1.0
    lc = LineCollection(lines, array=vals, cmap="inferno", linewidths=1.2)
    lc.set_clim(0.0, vmax)
    ax.add_collection(lc)
    for d in model.get("districts", []):
        ring = (d.get("polygon") or {}).get("exterior") or []
        if ring:
            xs, ys = zip(*(ring + ring[:1]))
            on = spike and d["id"] == spike["district_id"]
            ax.plot(xs, ys, color="#ff3fb4" if on else "#2c3443", lw=2.2 if on else 0.8)
    b = model.get("bounds") or [-1, -1, 1, 1]
    ax.set_xlim(b[0], b[2])
    ax.set_ylim(b[1], b[3])
    ax.set_aspect("equal")
    cb = fig.colorbar(lc, ax=ax, fraction=0.04, pad=0.01)
    cb.set_label("people per 100 m", color="#9aa6bd")
    cb.ax.tick_params(colors="#9aa6bd")
    ax.set_title(f"people on the streets at {hour}:00 (spike district outlined)",
                 color="#e6ecf7")
    hrs = list(range(P.HOURS))
    for d in sorted(hours):
        bx.plot(hrs, hours[d]["people"], lw=1.8,
                label=f"{d} {filled['districts'][d]['name']}")
    bx.set_xlabel("hour", color="#9aa6bd")
    bx.set_ylabel("people on its streets", color="#9aa6bd")
    bx.set_title("each district's people by hour", color="#e6ecf7")
    bx.legend(facecolor="#141a26", labelcolor="#e6ecf7", edgecolor="#3a4253", fontsize=9)
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
