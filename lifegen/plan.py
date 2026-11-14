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
  benchmark's walk), its people at the spike's hour (at most the budget's), a few cars.
- **The asks of citygen** (`asks.py`) and their state.
- **Checks** (scope 8, the ones LG0 can make): spawns on the graphs, spawns reaching each
  other, densities kept, slots placed, the spike within the budgets.

Outputs (written only when their bytes change): `life_plan.json`, `spawns/<tile>.json`,
`life_report.json`, `life_report.txt`, `unreal_contribution.life.json`,
`preview_crowds.png`.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from . import asks as A
from . import planmodel as PM
from . import presets as P
from . import spec as S

TILE_M = 256.0


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


def spawn_points(model: dict, walk_by: dict) -> list[dict]:
    """Every spawn point without its rates: (record, weight)."""
    out = []
    for b in model.get("buildings", []):
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


def _district_at(polys: list, x: float, y: float) -> str | None:
    import shapely
    pt = shapely.Point(x, y)
    for did, poly in polys:
        if poly.covers(pt):
            return did
    return None


def slots(model: dict) -> list[dict]:
    out = []
    for p in model.get("props", []):
        sk = P.SLOTS.get(p.get("type"))
        if sk is None:
            continue
        kind, beh, cap = sk
        pos = p["position"]
        did = p["id"].split(".")[0] if p["id"].startswith("d") else None
        out.append({"id": f"slot.{p['id']}", "owner_id": p["id"], "kind": kind,
                    "behavior": beh, "capacity": cap, "district_id": did,
                    "pos": [_r(pos[0], 2), _r(pos[1], 2), _r(pos[2] if len(pos) > 2 else 0, 2)],
                    "yaw_deg": _r(float(p.get("yaw_deg") or 0.0), 2)})
    for t in model.get("travel_points", []):
        if t.get("kind") != "taxi_stand":
            continue
        kind, beh, cap = P.TAXI_SLOT
        pos = (t.get("access") or {}).get("position") or t["position"]
        out.append({"id": f"slot.{t['id']}", "owner_id": t["id"], "kind": kind,
                    "behavior": beh, "capacity": cap, "district_id": t.get("district_id"),
                    "pos": [_r(pos[0], 2), _r(pos[1], 2), 0.0], "yaw_deg": 0.0})
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
    return out


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
    bud = filled["budgets"]
    people = sp.get("people")
    if people is None:
        people = min(P.SPIKE["people_max"], bud["people_view"],
                     int(round(hours[did]["people"][sp["hour"]])))
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
    style = filled["districts"][did]["style"]["groups"]
    gang = next((f.get("color") for f in model.get("factions", [])
                 if f.get("kind") == "gang" and f.get("home_district_id") == did), None)
    palette = []
    for k in range(P.SPIKE_PALETTE):
        g = _pick(style, "lg0.palette.group", did, k)
        cols = (gang,) if g == "gang" and gang else P.GROUP_COLORS[g]
        palette.append(cols[int(_u("lg0.palette.color", did, k) * len(cols))])
    return hashed({"district_id": did, "name": ds[did].get("name"), "hour": sp["hour"],
                   "palette": palette,
                   "center": [_r(mid[0], 2), _r(mid[1], 2)], "radius_m": P.SPIKE["radius_m"],
                   "people": int(people), "cars": int(sp["cars"]),
                   "models": [{"model": m, "weight": w} for m, w in models],
                   "walk_kinds": list(P.SPIKE_WALK_KINDS),
                   "walk_speed": list(P.SPIKE["walk_speed"]),
                   "drive_speed": list(P.SPIKE["drive_speed"]),
                   "car_gap_m": P.SPIKE["car_gap_m"],
                   "polygon": [[_r(x, 2), _r(y, 2)] for x, y in ring]})


def build_plan(build: str | Path, spec_path: str | Path | None = None,
               out: str | Path | None = None, preview: bool = True) -> dict:
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
    raw_spawns = spawn_points(model, walk_by)
    for rec, _ in raw_spawns:
        if rec["district_id"] is None:
            rec["district_id"] = _district_at(polys, rec["pos"][0], rec["pos"][1])
        rec["tile"] = tile_of(rec["pos"][0], rec["pos"][1])
    wsum = defaultdict(float)
    for rec, w in raw_spawns:
        wsum[rec["district_id"]] += w
    turn = 60.0 / P.TRIP_MIN
    spawns = []
    for rec, w in sorted(raw_spawns, key=lambda rw: rw[0]["id"]):
        d = rec["district_id"]
        ppl = hours[d]["people"] if d in hours else [0.0] * P.HOURS
        share = w / wsum[d] if wsum[d] > 0 else 0.0
        rec["rates"] = [_r(ppl[h] * turn * share, 3) for h in range(P.HOURS)]
        spawns.append(hashed(rec))
    slot_rows = []
    for s in sorted(slots(model), key=lambda s: s["id"]):
        if s["district_id"] is None or s["district_id"] not in hours:
            s["district_id"] = _district_at(polys, s["pos"][0], s["pos"][1])
        s["tile"] = tile_of(s["pos"][0], s["pos"][1])
        slot_rows.append(hashed(s))

    # per tile
    by_tile = defaultdict(lambda: {"spawns": [], "slots": []})
    for s in spawns:
        by_tile[s["tile"]]["spawns"].append(s)
    for s in slot_rows:
        by_tile[s["tile"]]["slots"].append(s)
    tiles = []
    keep = set()
    for t in sorted(by_tile):
        rec = PM.TileSpawns(city=city, tile=t, bounds=tile_bounds(t), **by_tile[t])
        text = canon(json.loads(rec.model_dump_json()))
        f = out / "spawns" / f"{t}.json"
        keep.add(f.name)
        write(f, text, wrote)
        tiles.append({"tile": t, "file": f"spawns/{t}.json", "spawns": len(by_tile[t]["spawns"]),
                      "slots": len(by_tile[t]["slots"]),
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
    asks = A.status(model, {"doors": (build / "assets" / "unreal_contribution.buildings.json")
                            .is_file()})
    totals = {"spawns": len(spawns), "slots": len(slot_rows), "tiles": len(tiles),
              "people_peak": _r(max(sum(h["people"][k] for h in hours.values())
                                    for k in range(P.HOURS)), 1),
              "vehicles_peak": _r(max(sum(h["vehicles"][k] for h in hours.values())
                                      for k in range(P.HOURS)), 1),
              "spawns_without_walkway": 0}
    body = {"city": city, "model_sha256": hashlib.sha256(raw).hexdigest(),
            "spec": {k: v for k, v in filled.items() if k != "districts"},
            "bands": list(P.BANDS), "districts": districts, "tiles": tiles, "asks": asks,
            "spike": spike, "checks": checks, "totals": totals}
    plan_hash = _sha([body["spec"], [d["hash"] for d in districts],
                      [t["sha256"] for t in tiles], spike and spike["hash"]])
    plan = PM.LifePlan(plan_hash=plan_hash, **body)
    pdata = json.loads(plan.model_dump_json())
    write(out / "life_plan.json", canon(pdata), wrote)

    entries = []
    if spike is not None:
        entries.append({"key": "life", "kind": "life_controller", "hash": _sha([plan_hash]),
                        "tile": None, "count": spike["people"] + spike["cars"]})
    for t in tiles:
        entries.append({"key": f"life.spawns.{t['tile']}", "kind": "spawner",
                        "hash": t["sha256"][:16], "tile": t["tile"], "count": t["spawns"]})
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
           "asks": {a["id"]: a["status"] for a in asks}}
    write(out / "life_report.json", canon(rep), wrote)
    write(out / "life_report.txt", report_text(rep), wrote)
    if preview:
        img = preview_crowds(model, hours, filled, spike, out / "preview_crowds.png")
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
