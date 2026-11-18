"""lifegen's part of the Unreal exporter (LG0; venv side: no Unreal, no network).

A city's life plan (`lifegen plan BUILD`, BUILD/life or `--life DIR`) is layer 4 of the
manifest, its `life`: the `CityGenLife` controller (key `life`, always loaded), with the plan's
spike packed into `BUILD/unreal/life.json` for the importer:

- **walkway lanes:** the flat walkway graph's elements (graphs.json, stage 2's lines) of the
  spike's walk kinds within the spike's radius (and `MARGIN_M`) of its middle, their points,
  widths and links, each link `2 * lane + 1` where the other walkway meets this one's end
  (its last point), `2 * lane` at its start;
- **drive lanes:** the lane graph's lanes and junction connectors within the same reach,
  their successors (directed), which of them a car may start on (a lane, not a connector);
- **people:** the spike's count, walking speeds, the stand-ins' palette (linear RGB);
- **cars:** the spike's count, each car's model drawn by its district's weights from the
  models the manifest's vehicles section imports (AG18's packs, already in the project) and
  its paint by AG18's step H's rule (`assetgen/parked/table.py`), every part of every model
  used (its mesh path, its pivot).

LG3: a plan with a `crowd` packs the city's crowd instead of the spike's people
(`pack_crowd`): every walkway of the city with its kind, district, people per hour band and
signal window; the doors; the districts' days, dangers and palettes; the pool; the drive lanes
and cars stay the spike's.

LG5: a plan with `traffic` packs the city's traffic instead of the spike's cars
(`pack_traffic`): every lane and junction connector of the lane graph with its cars per hour
band, district, whether it is on the graph's largest strongly connected part, the signal it
stops at and where, the connectors it may not share (`conflicts`); the signals' windows for
cars; the pool's slots by model, the districts' fleets and paints (`traffic_cars`).

LG6: a plan with `transit` packs every transit line (`pack_transit`): its track, timetable
(the cycle sampled, the stop events, the trains per band), the train as drawn (the stand-ins'
parts per mode, `TRANSIT_MODELS`), its stops (platform walkway, boarding by band); the
platforms' walkways as wide as their decks, people keeping off their trains (`walk_clear`);
which doors are a served station's street accesses (`door_transit`).

LG7: a plan with `airwater` packs every route of what flies and floats (`pack_airwater`): its
kind, model, color, points with headings, cycle and samples, dwells, vehicles per band and their
paints; the models (AG18's hover cars with nav lights where the project has them, else the
stand-ins of `AIRWATER_MODELS`) as parts, their meshes.

The runtime builds ZoneGraph lanes from these at BeginPlay (no hand-drawn shapes). A plan
whose checks failed is named and left out (`skipped`); a build without a plan gets no
section, and its manifest is what it was.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

PACK_VERSION = 10           # 2 (cars_steam): smoothed drive lanes, their speeds; 3 (LG3): the
                            # city's crowd (every walkway, doors, signals, the pool); 4 (LG5):
                            # the city's traffic (every lane, signals, conflicts, the pool); 5 (LG2):
                            # looks for people, their groups, dye colors and wear; 6 (LG4): slots,
                            # places by their hours, gangs, police patrols and cars, the
                            # places' clips; 7 (LG6): transit's lines, timetables, stops and
                            # trains, the platforms' walkways kept off their trains; 8
                            # (LG7): air and water routes, their models and paints; 9 (LG8):
                            # the weather's table, umbrellas, shelter stretches, nightlife,
                            # the clear weather's groups, the reactions' settings; 10
                            # (delta_rebuild): slots seated on their surface (`slot_seated`)
DATA = "life.json"
CONTROLLER_KEY = "life"
MARGIN_M = 60.0             # lanes this far past the live radius come along (links out of it)
PAINT_FLOATS = 9
# LG5: how far each part of a moving car is drawn (m): the body out past the traffic's live
# radius (a flight sees the roads full), its glass, wheels and small parts nearer (the parked
# cars' import.VEHICLE_CULL_M is shorter: they are many more)
TRAFFIC_CULL_M = {"body": 900.0, "glass": 300.0, "wheel": 150.0, "brake": 80.0, "other": 200.0}


def _sha16(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()[:16]


def plan_dir(build: str | Path, given: str | Path | None = None) -> Path | None:
    d = Path(given) if given else Path(build) / "life"
    return d if (d / "life_plan.json").is_file() else None


def _lin(hexcol: str) -> list[float]:
    h = hexcol.lstrip("#")
    out = []
    for k in (0, 2, 4):
        c = int(h[k:k + 2], 16) / 255.0
        out.append(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 4))
    return out


def _elements(g: dict):
    """(index, kind, points, width, links, level) of a flat graph's elements."""
    ps, ls = g["point_start"], g["link_start"]
    pts, lnk = g["points"], g["links"]
    lev = g.get("levels")
    for i in range(g["count"]):
        p = [pts[3 * k:3 * k + 3] for k in range(ps[i], ps[i + 1])]
        yield i, g["kinds"][i], p, g["widths"][i], lnk[ls[i]:ls[i + 1]], \
            (lev[i] if lev else 0)


def _near(points, cx: float, cy: float, r: float) -> bool:
    r2 = r * r
    return any((p[0] - cx) ** 2 + (p[1] - cy) ** 2 <= r2 for p in points)


def pack_lanes(graphs: dict, spike: dict) -> dict:
    """The spike's walkway and drive lanes, flat (see the module docstring)."""
    cx, cy = spike["center"]
    reach = float(spike["radius_m"]) + MARGIN_M
    kinds = set(spike["walk_kinds"])
    walk = [e for e in _elements(graphs["walkways"])
            if e[1] in kinds and len(e[2]) >= 2 and _near(e[2], cx, cy, reach)]
    out = pack_walks(graphs, walk)
    out.update(pack_drive(graphs, spike))
    return out


def pack_walks(graphs: dict, walk: list) -> dict:
    """Walkway lanes (`_elements` of the walkway graph), flat: points, widths, links (each
    `2 * lane + 1` where the other walkway meets this one's end, `2 * lane` at its start)."""
    wmap = {e[0]: k for k, e in enumerate(walk)}
    out = {"walk_points": [], "walk_starts": [0], "walk_widths": [], "walk_links": [],
           "walk_link_starts": [0]}
    for e in walk:
        pts = e[2]
        for p in pts:
            out["walk_points"] += [round(float(v), 3) for v in p]
        out["walk_starts"].append(len(out["walk_points"]) // 3)
        out["walk_widths"].append(round(float(e[3]), 3))
        a, b = pts[0], pts[-1]
        for j in e[4]:
            if j not in wmap:
                continue
            q = graphs["walkways"]
            qa = q["points"][3 * q["point_start"][j]:3 * q["point_start"][j] + 3]
            qb = q["points"][3 * (q["point_start"][j + 1] - 1):3 * q["point_start"][j + 1]]
            da = min(math.dist(a[:2], qa[:2]), math.dist(a[:2], qb[:2]))
            db = min(math.dist(b[:2], qa[:2]), math.dist(b[:2], qb[:2]))
            out["walk_links"].append(2 * wmap[j] + (1 if db < da else 0))
        out["walk_link_starts"].append(len(out["walk_links"]))
    return out


def pack_drive(graphs: dict, spike: dict) -> dict:
    """The spike's drive lanes (lanes and junction connectors within its reach), flat, with
    their speeds (cars_steam)."""
    cx, cy = spike["center"]
    reach = float(spike["radius_m"]) + MARGIN_M
    drive = [e for e in _elements(graphs["lanes"])
             if len(e[2]) >= 2 and _near(e[2], cx, cy, reach)]
    refs = graphs["lanes"].get("refs") or [""] * graphs["lanes"]["count"]
    classes = spike.get("road_classes") or {}
    return pack_drive_lanes(graphs, drive, spike.get("drive_speeds") or {},
                            spike.get("drive") or {},
                            {e[0]: classes.get(refs[e[0]], "") for e in drive})


def pack_drive_lanes(graphs: dict, drive: list, speeds: dict, dv: dict,
                     lane_class: dict) -> dict:
    """Drive lanes (`_elements` of the lane graph), flat, with their speeds (cars_steam):
    `lane_class` the road class of each element (by its index in the graph; a connector's
    unused)."""
    dmap = {e[0]: k for k, e in enumerate(drive)}
    out = {"drive_points": [], "drive_starts": [0], "drive_widths": [],
           "drive_links": [], "drive_link_starts": [0], "drive_startable": [],
           "drive_vmax": [], "drive_cruise": []}
    succ =[[dmap[j] for j in e[4] if j in dmap] for e in drive]
    pred: list[list[int]] = [[] for _ in drive]
    for k, ss in enumerate(succ):
        for j in ss:
            pred[j].append(k)
    # (cars_steam) every lane a smooth curve through its points, leaving and joining its
    # neighbors on their tangents; its cruise speed by its road's class, a junction's
    # connector slower; per point at most what its bend allows, braking before it
    pts = []
    for k, e in enumerate(drive):
        p = [[float(v) for v in q] for q in e[2]]
        before = next((drive[j][2][-2] for j in pred[k]
                       if math.dist(drive[j][2][-1][:2], p[0][:2]) < 0.5), None)
        after = next((drive[j][2][1] for j in succ[k]
                      if math.dist(drive[j][2][0][:2], p[-1][:2]) < 0.5), None)
        pts.append(smooth(p, before, after))
    default = speeds.get(dv.get("default", "street"), 9.5) if speeds else None
    base = []
    for k, e in enumerate(drive):
        if default is None:
            base.append(0.0)                  # (a plan before cars_steam: no speeds)
        elif e[1] == "lane":
            base.append(float(speeds.get(lane_class.get(e[0], ""), default)))
        else:
            base.append(-1.0)                 # (a connector: from its roads, below)
    for k, e in enumerate(drive):
        if base[k] < 0.0:
            nb = [base[j] for j in pred[k] + succ[k] if base[j] > 0.0]
            base[k] = round(float(dv.get("junction", 0.6)) * (min(nb) if nb else default), 3)
    vmax = [lane_vmax(pts[k], base[k], float(dv.get("lateral", 2.0)),
                      float(dv.get("crawl", 2.0))) if base[k] > 0.0
            else [0.0] * len(pts[k]) for k in range(len(drive))]
    if default is not None:
        brake = float(dv.get("brake", 2.5))
        # (a lane's end at most its successors' starts, braking back from there; again while a
        # start that was lowered lowers its predecessors, a few rounds)
        todo = set(range(len(drive)))
        for _ in range(8):
            if not todo:
                break
            lowered = set()
            for k in sorted(todo):
                v = vmax[k]
                first = v[0]
                if succ[k]:
                    v[-1] = min(v[-1], min(vmax[j][0] for j in succ[k]))
                for i in range(len(v) - 2, -1, -1):
                    ds = math.dist(pts[k][i][:2], pts[k][i + 1][:2])
                    v[i] = min(v[i], round(math.sqrt(v[i + 1] ** 2 + 2.0 * brake * ds), 3))
                if v[0] < first:
                    lowered.update(pred[k])
            todo = lowered
    for k, e in enumerate(drive):
        for q in pts[k]:
            out["drive_points"] += [round(float(v), 3) for v in q]
        out["drive_vmax"] += [round(v, 2) for v in vmax[k]]
        out["drive_starts"].append(len(out["drive_points"]) // 3)
        out["drive_widths"].append(round(float(e[3]), 3))
        out["drive_links"] += succ[k]
        out["drive_link_starts"].append(len(out["drive_links"]))
        out["drive_startable"].append(1 if e[1] == "lane" else 0)
        out["drive_cruise"].append(round(base[k], 3))
    return out


def strong_components(succ: list[list[int]]) -> list[int]:
    """LG5: each node's strongly connected component (Tarjan's, iterative) of a directed graph
    given by its successors; components numbered in the order they close."""
    n = len(succ)
    index = [-1] * n
    low = [0] * n
    on = [False] * n
    comp = [-1] * n
    stack: list[int] = []
    count = 0
    nc = 0
    for root in range(n):
        if index[root] >= 0:
            continue
        work = [(root, 0)]
        while work:
            v, i = work[-1]
            if i == 0:
                index[v] = low[v] = count
                count += 1
                stack.append(v)
                on[v] = True
            if i < len(succ[v]):
                work[-1] = (v, i + 1)
                w = succ[v][i]
                if index[w] < 0:
                    work.append((w, 0))
                elif on[w]:
                    low[v] = min(low[v], index[w])
                continue
            work.pop()
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on[w] = False
                    comp[w] = nc
                    if w == v:
                        break
                nc += 1
    return comp


def main_component(succ: list[list[int]]) -> set[int]:
    """LG5: the nodes of a directed graph's largest strongly connected component (by nodes;
    of two as large, the one holding the lowest node)."""
    comp = strong_components(succ)
    size: dict[int, int] = {}
    first: dict[int, int] = {}
    for k, c in enumerate(comp):
        size[c] = size.get(c, 0) + 1
        first.setdefault(c, k)
    if not size:
        return set()
    best = min(size, key=lambda c: (-size[c], first[c]))
    return {k for k, c in enumerate(comp) if c == best}


def lane_vmax(pts, base: float, lateral: float, crawl: float = 0.0) -> list[float]:
    """A lane's speed at each of its points (m/s): its cruise speed, at most sqrt(lateral R)
    where it bends (R from the turn at the point over the mean of its two segments), never
    under `crawl` (nor over the cruise speed)."""
    out = []
    for i, q in enumerate(pts):
        v = base
        if 0 < i < len(pts) - 1:
            a, c = pts[i - 1], pts[i + 1]
            h0 = math.atan2(q[1] - a[1], q[0] - a[0])
            h1 = math.atan2(c[1] - q[1], c[0] - q[0])
            turn = abs((h1 - h0 + math.pi) % (2.0 * math.pi) - math.pi)
            ds = 0.5 * (math.dist(a[:2], q[:2]) + math.dist(q[:2], c[:2]))
            if turn > 1e-4 and ds > 1e-3:
                v = min(v, max(min(crawl, base), math.sqrt(lateral * ds / turn)))
        out.append(round(v, 3))
    return out



SMOOTH_STEP_M = 1.5         # a smoothed lane's points this far apart at most
SMOOTH_TURN_DEG = 1.0       # a lane is smoothed only where it turns more than this somewhere


def _turn(a, b, c) -> float:
    """The turn (degrees) at b from a to c in plan."""
    if math.dist(a[:2], b[:2]) < 1e-6 or math.dist(b[:2], c[:2]) < 1e-6:
        return 0.0
    h0 = math.atan2(b[1] - a[1], b[0] - a[0])
    h1 = math.atan2(c[1] - b[1], c[0] - b[0])
    return abs(math.degrees((h1 - h0 + math.pi) % (2.0 * math.pi) - math.pi))


def _cr_point(p0, p1, p2, p3, t):
    """A centripetal Catmull-Rom point (alpha 0.5) between p1 and p2 at t in [0, 1]."""
    def tj(ti, a, b):
        d = math.dist(a[:2], b[:2])
        return ti + max(d, 1e-6) ** 0.5
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    u = t1 + (t2 - t1) * t

    def lerp(a, b, ta, tb):
        w = (u - ta) / (tb - ta) if tb != ta else 0.0
        return [a[k] + (b[k] - a[k]) * w for k in range(3)]
    a1 = lerp(p0, p1, t0, t1)
    a2 = lerp(p1, p2, t1, t2)
    a3 = lerp(p2, p3, t2, t3)
    b1 = lerp(a1, a2, t0, t2)
    b2 = lerp(a2, a3, t1, t3)
    return lerp(b1, b2, t1, t2)


FILLET_DEG = 12.0           # an inner point turning more than this is rounded off by an arc
FILLET_CUT_M = 2.0          # ... cutting its corner by at most this much
FILLET_LEG = 0.45           # ... its tangents at most this share of each leg


def fillet(pts, step=SMOOTH_STEP_M):
    """A lane's sharp inner corners (the lane graph's polylines turn at single points) rounded
    off by circular arcs tangent to both legs: the tangent length the smallest of `FILLET_LEG`
    of each leg and what cuts the corner by `FILLET_CUT_M`; arc points about `step` apart. The
    ends stay where they are (the neighbor lanes meet them there)."""
    if len(pts) < 3:
        return [list(p) for p in pts]
    out = [list(pts[0])]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        th = math.radians(_turn(a, b, c))
        la, lc = math.dist(a[:2], b[:2]), math.dist(b[:2], c[:2])
        if th < math.radians(FILLET_DEG) or th > math.radians(150.0) or la < 1e-3 or lc < 1e-3:
            out.append(list(b))
            continue
        tn = math.tan(th / 2.0)
        # (the corner cut by an arc of radius R is R (1 / cos(th / 2) - 1); its tangent R tn)
        cut = 1.0 / math.cos(th / 2.0) - 1.0
        d = min(FILLET_LEG * la, FILLET_LEG * lc, FILLET_CUT_M / cut * tn)
        r = d / tn
        ua = [(b[k] - a[k]) / la for k in range(2)]
        uc = [(c[k] - b[k]) / lc for k in range(2)]
        p0 = [b[0] - ua[0] * d, b[1] - ua[1] * d, b[2] - (b[2] - a[2]) * d / la]
        p1 = [b[0] + uc[0] * d, b[1] + uc[1] * d, b[2] + (c[2] - b[2]) * d / lc]
        side = 1.0 if ua[0] * uc[1] - ua[1] * uc[0] > 0.0 else -1.0
        o = [p0[0] - side * ua[1] * r, p0[1] + side * ua[0] * r]
        a0 = math.atan2(p0[1] - o[1], p0[0] - o[0])
        m = max(2, int(math.ceil(r * th / step)))
        for j in range(m + 1):
            ang = a0 + side * th * j / m
            out.append([o[0] + r * math.cos(ang), o[1] + r * math.sin(ang),
                        p0[2] + (p1[2] - p0[2]) * j / m])
    out.append(list(pts[-1]))
    return out


def smooth(pts, before=None, after=None, step=SMOOTH_STEP_M):
    """A lane's points with its sharp corners rounded off (`fillet`), then as a centripetal
    Catmull-Rom spline through them (the neighbor lanes' points beyond its ends as the
    spline's end controls, so it leaves and joins them on their tangents), sampled at most
    `step` apart; its ends kept, and every point that turns less than `FILLET_DEG`."""
    pts = fillet(pts, step)
    n = len(pts)
    if n < 2:
        return [list(p) for p in pts]
    ext = [list(before) if before is not None else
           [2 * pts[0][k] - pts[1][k] for k in range(3)]] + [list(p) for p in pts] + \
        [list(after) if after is not None else [2 * pts[-1][k] - pts[-2][k] for k in range(3)]]
    out = [list(pts[0])]
    for i in range(1, n):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        # (a straight run, turning less than SMOOTH_TURN_DEG at both its ends, stays a chord)
        straight = _turn(p0, p1, p2) < SMOOTH_TURN_DEG and _turn(p1, p2, p3) < SMOOTH_TURN_DEG
        m = 1 if straight else max(1, int(math.ceil(math.dist(p1[:2], p2[:2]) / step)))
        for j in range(1, m + 1):
            q = list(p2) if j == m else _cr_point(p0, p1, p2, p3, j / m)
            # (z along the chord: the spline is for the plan's turns, not the grade)
            q[2] = p1[2] + (p2[2] - p1[2]) * j / m
            out.append(q)
    return out


def cars(spike: dict, archetype: str | None, veh: dict | None) -> dict:
    """Each car's model and paint, and every part of the models used."""
    from assetgen.parked.table import paint, pick_weighted
    have = (veh or {}).get("cars") or {}
    weights = {m["model"]: m["weight"] for m in spike["models"] if m["model"] in have}
    out = {"car_models": [], "car_paints": [], "parts": [], "models": []}
    if not weights or not spike["cars"]:
        return out
    drawn = [pick_weighted(weights, "lg0.car", spike["district_id"], k)
             for k in range(int(spike["cars"]))]
    used = sorted(set(drawn))
    for k, car in enumerate(drawn):
        out["car_models"].append(used.index(car))
        cols, _ = paint(car, archetype, f"lg0.{spike['district_id']}.car{k}")
        out["car_paints"] += [round(float(v), 4) for c in cols for v in c]
    for mi, car in enumerate(used):
        rec = have[car]
        out["models"].append(car)
        for p in rec["parts"]:
            out["parts"].append({"model": mi, "mesh": f"{rec['folder']}/SM_{car}_{p['name']}",
                                 "shadow": p.get("kind") not in ("glass", "wheel", "brake"),
                                 "pivot": [float(v) for v in p.get("pivot", [0.0, 0.0, 0.0])]})
    return out


def persons(spike: dict) -> dict:
    """LG1: each of the spike's people as the plan drew them (`lifegen.library.person`):
    their character of the library, height scale, gait, pace (m/s), the outfit's tint (linear
    RGB, 3 floats a person, from the spike's palette) and seed (signed 32 bits for Unreal's
    int32). Empty for a plan before LG1."""
    ps = spike.get("persons") or {}
    if not ps.get("character"):
        return {}
    pal = spike.get("palette") or []
    lin = [_lin(c) for c in pal]
    tint = []
    for t in ps.get("tint") or [0] * len(ps["character"]):
        tint += lin[int(t)] if lin else [0.5, 0.5, 0.5]
    # (LG2: the runtime's unit is a look, its character's body and face in its garments)
    unit = ps.get("look") or ps["character"]
    return {"person_char": [int(v) for v in unit],
            "person_group": [int(v) for v in ps.get("group") or []],
            "person_scale": [float(v) for v in ps["scale"]],
            "person_gait": [int(v) for v in ps["gait"]],
            "person_pace": [float(v) for v in ps["pace"]],
            "person_tint": [round(v, 4) for v in tint],
            "person_seed": [int(v) - (1 << 32) if int(v) >= (1 << 31) else int(v)
                            for v in ps["seed"]]}


def people_library(lib: dict | None, spike: dict) -> dict:
    """LG1: what the runtime draws people with, from the project's people library
    (`citygen/unreal_people.py`, its manifest): per character its near meshes (the assembled
    MetaHuman's skeletal meshes, the leader first), its mid mesh (its walk baked into
    textures), its impostor card's material; the walk clips and their speeds; the tiers. None
    without a library or when its characters are not the plan's."""
    if not lib or not lib.get("characters"):
        return {}
    chars = lib["characters"]
    # (LG2: the library's entries are looks; a plan before LG2 draws characters)
    pl = spike.get("library") or {}
    want = pl.get("looks") if lib.get("looks") else pl.get("characters")
    if want and want != len(chars):
        return {"people_skipped": f"the plan draws from {want} looks or characters, the "
                                  f"project's library has {len(chars)}"}
    near, starts, mid, mid_frames, cards = [], [0], [], [], []
    for c in chars:
        near += c["near"]["meshes"]
        starts.append(len(near))
        mid.append(c["mid"]["mesh"])
        mid_frames += [float(c["mid"]["start"]), float(c["mid"]["end"]),
                       float(c["mid"]["fps"]), float(c["mid"].get("cycle_s", 1.0))]
        cards.append(c["far"]["material"])
    names = (spike.get("library") or {}).get("walks") or lib["walks"]
    # (characters on one body skeleton share their clips: a group's walks in gait order)
    groups = lib.get("clip_groups") or {"s0": {"clips": lib["clips"]}}
    keys = sorted(groups)
    walks = [groups[k]["clips"][w] for k in keys for w in names]
    tiers = {**(lib.get("tiers") or {}), **((spike.get("library") or {}).get("tiers") or {})}
    # (LG4: the places' clips on each clip group's skeleton, `unreal_people.ensure_place_clips`:
    # a bench's sitting loop, standing idle breaks for talking, smoking and eating)
    pc = lib.get("place_clips") or {}
    pg = pc.get("groups") or {}
    talk = [c for c in pc.get("clips") or [] if c.startswith("talk")]
    place = {}
    if pg and all(k in pg for k in keys):
        place = {"sit_clips": [(pg[k].get("sit") or {}).get("anim", "") for k in keys],
                 "talk_clips": [(pg[k].get(c) or {}).get("anim", "") for k in keys for c in talk],
                 "talk_count": len(talk), "places_hash": pc.get("hash"),
                 # (LG8: the run, where the places' clips have it, and the speed it runs at:
                 # its root's travel over its length, made in place)
                 "run_clips": [(pg[k].get("run") or {}).get("anim", "") for k in keys]
                 if all((pg[k].get("run") or {}).get("anim") for k in keys) else [],
                 "run_clip_speed": round(max([math.hypot(*((pg[k].get("run") or {})
                                                          .get("travel_cm") or [0.0, 0.0]))
                                              / 100.0 / max(0.1, float((pg[k].get("run") or {})
                                                                       .get("length_s") or 1.0))
                                              for k in keys] or [0.0]), 3)}
    # (people_idles: the places' second mid bakes and still sheets, where every look has them:
    # per look the idle's and the sitting loop's frames in its bake, its material instances
    # (the library mid mesh's slots, flat with starts), its card on the still sheet; the
    # sheet's cells; the sit-downs and the stand-up, per group, with where they start and end)
    out = {"near_meshes": near, "near_mesh_starts": starts,
           "near_hair": [c["near"].get("hair") or "" for c in chars],
           "char_clip_group": [keys.index(c["skeleton"]) if c.get("skeleton") in keys else 0
                               for c in chars],
           "gaits": len(names),
           "walk_clips": [w["anim"] for w in walks],
           "walk_clip_speeds": [float(w["speed"]) for w in walks],
           "idle_clips": [groups[keys[0]]["clips"][k]["anim"] for k in lib.get("idles", [])],
           "mid_meshes": mid, "mid_frames": mid_frames,
           "card_mesh": lib["far"]["card"], "card_materials": cards,
           "card_size": [float(v) for v in lib["far"].get("size", [1.0, 2.0])],
           "tiers": tiers, "library_hash": lib.get("hash"), **place}
    out.update(idle_data(pc, chars, keys, cards))
    return out


def idle_data(pc: dict, chars: list, keys: list, cards: list) -> dict:
    """people_idles: the life controller's idles from the places' manifest (`unreal_people.
    ensure_place_clips`): `mid_still_frames` per look (the idle's first and last frame, the
    sitting loop's, in its second bake), `mid_idle_materials` flat with `mid_idle_starts`, the
    looks' cards on their still sheets in place of `cards` (`card_materials`) and the sheet's
    cells (`card_cells`: walk, sit, idle, a first cell and cells each); the sit-downs
    (`sit_in_clips` per group, `sit_in_count` a group, in `lifegen.presets.SIT_IN`'s order) and
    their start (`sit_in`: per group and sit-down its root's x, y (cm) and turn (deg) in the
    seat's frame, in the mesh's axes, and the stretch played, s; `sit_in_start` where in the
    clip that stretch starts) and the stand-up (`sit_out_clips`,
    `sit_out`: where it ends, and its length). Empty where the manifest has none of them, or
    not for every look and group."""
    from lifegen import presets as LP
    out: dict = {}
    pg = pc.get("groups") or {}
    if not pg or not all(k in pg for k in keys):
        return out
    ins = list(LP.SIT_IN)
    def played(r):
        # (the stretch of a transition a person plays: from `start_s` to `end_s`, the whole clip
        # where the manifest has no such bounds)
        t0 = float(r.get("start_s") or 0.0)
        t1 = float(r.get("end_s") or r.get("length_s") or 1.0)
        return t0, max(0.1, t1 - t0)

    if all(all((pg[k].get(c) or {}).get("anim") for c in ins + ["sit_out"]) for k in keys):
        out["sit_in_clips"] = [pg[k][c]["anim"] for k in keys for c in ins]
        out["sit_in_count"] = len(ins)
        out["sit_in"] = [float(v) for k in keys for c in ins
                         for v in (*(pg[k][c].get("other_cm") or [0.0, 0.0]),
                                   pg[k][c].get("other_yaw") or 0.0, played(pg[k][c])[1])]
        out["sit_in_start"] = [played(pg[k][c])[0] for k in keys for c in ins]
        out["sit_out_clips"] = [pg[k]["sit_out"]["anim"] for k in keys]
        out["sit_out"] = [float(v) for k in keys
                          for v in (*(pg[k]["sit_out"].get("other_cm") or [0.0, 0.0]),
                                    pg[k]["sit_out"].get("other_yaw") or 0.0,
                                    played(pg[k]["sit_out"])[1])]
    idl = pc.get("idles") or {}
    looks = idl.get("looks") or {}
    if chars and all((looks.get(c["id"]) or {}).get("mid", {}).get("materials")
                     and (looks.get(c["id"]) or {}).get("far", {}).get("material")
                     for c in chars):
        frames, mats, starts = [], [], [0]
        for c in chars:
            m = looks[c["id"]]["mid"]
            frames += [float(m["idle"][0]), float(m["idle"][1]), float(m["sit"][0]),
                       float(m["sit"][1])]
            mats += list(m["materials"])
            starts.append(len(mats))
        cd = idl.get("card") or {}
        out.update({"mid_still_frames": frames, "mid_idle_materials": mats,
                    "mid_idle_starts": starts,
                    "card_materials": [looks[c["id"]]["far"]["material"] for c in chars],
                    "card_cells": [float(v) for k in ("walk", "sit", "idle")
                                   for v in (cd.get(k) or [0, 0])],
                    "idles_key": idl.get("key")})
    return out


def _along(line, x: float, y: float) -> float:
    """The distance along a polyline (plan) of its point nearest (x, y)."""
    best, at, run = None, 0.0, 0.0
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 <= 0.0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
        px, py = a[0] + dx * t, a[1] + dy * t
        d = (px - x) ** 2 + (py - y) ** 2
        if best is None or d < best:
            best, at = d, run + math.sqrt(L2) * t
        run += math.sqrt(L2)
    return at


def pack_crowd(plan: dict, pdir: Path, graphs: dict) -> dict:
    """LG3: the city's crowd, flat: every walkway of the city a lane (`pack_walks`) with its
    kind, district, people per hour band and signal window; the districts' days, dangers and
    palettes (linear RGB); the signals' walk windows; the doors (every spawn point: its
    walkway lane, distance along it, point, people a hour out at the crowd's hour); the pool's
    people (`persons`, the tint an index into the district's palette); the settings."""
    crowd = plan["crowd"]
    walk = [e for e in _elements(graphs["walkways"]) if len(e[2]) >= 2]
    gids = graphs["walkways"].get("ids") or [str(e[0]) for e in walk]
    lane_of = {gids[e[0]]: k for k, e in enumerate(walk)}
    out = pack_walks(graphs, walk)
    rows, doors, slots, places = {}, [], [], {}
    for t in plan["tiles"]:
        tile = json.loads((pdir / t["file"]).read_text(encoding="utf-8"))
        for w in tile.get("walks") or []:
            rows[w["id"]] = w
        doors += tile.get("spawns") or []
        slots += tile.get("slots") or []
        for p in tile.get("places") or []:
            places[p["spawn_id"]] = p
    dids = [d["id"] for d in plan["districts"]]
    didx = {d: k for k, d in enumerate(dids)}
    codes = {k: i for i, k in enumerate(crowd["kinds"])}
    path = codes.get("path", 0)
    sigs = []
    sfile = pdir / "signals.json"
    if sfile.is_file():
        sigs = json.loads(sfile.read_text(encoding="utf-8")).get("signals") or []
    win, windows = {}, []
    for s in sigs:
        for p in s["phases"]:
            win[(s["id"], p["index"])] = len(windows) // 4
            windows += [float(s["cycle_s"]), float(s["offset_s"]), float(p["start_s"]),
                        round(float(p["start_s"]) + float(p["walk_s"]), 3)]
    kinds, dist, ppl, sig = [], [], [], []
    # (LG8: each walkway's stretches out of the rain, [from, to] m, and its nightlife per band)
    cov_starts, cov, night, rside = [0], [], [], []
    any_night = False
    for e in walk:
        r = rows.get(gids[e[0]]) or {}
        kinds.append(codes.get(e[1], path))
        dist.append(didx.get(r.get("district_id"), -1))
        ppl += [round(float(v), 4) for v in (r.get("people") or [0.0] * 5)]
        sig.append(win.get((r.get("signal"), r.get("phase")), -1))
        for a, b in r.get("cover") or []:
            cov += [round(float(a), 2), round(float(b), 2)]
        cov_starts.append(len(cov) // 2)
        rside.append(int(r.get("road_side") or 0))
        nv = r.get("night")
        any_night |= bool(nv)
        night += [round(float(v), 3) for v in (nv or [0.0] * 5)]
    hour = int(crowd["hour"])
    dl, dd, dp, dr = [], [], [], []
    # (LG4: each door's rates every hour, its place's open hours as 24 bits, visit chance by
    # band and visit length, a precinct station's door)
    drh, dopen, dvisit, ddwell, dpolice = [], [], [], [], []
    door_index = {}
    stations = {d for p in ((plan.get("police") or {}).get("precincts") or [])
                for d in p.get("station_doors") or []}
    # (LG6: a transit station's street accesses, whose people the trains bring while transit
    # runs)
    served = {sid for ln in ((plan.get("transit") or {}).get("lines") or [])
              for sid in ln.get("stops") or []}
    dtransit = []
    for s in sorted(doors, key=lambda s: s["id"]):
        k = lane_of.get(s.get("walkway_id"))
        if k is None:
            continue
        e = walk[k]
        door_index[s["id"]] = len(dl)
        dl.append(k)
        dd.append(round(_along(e[2], s["pos"][0], s["pos"][1]), 3))
        dp += [round(float(v), 3) for v in s["pos"]]
        dr.append(round(float(s["rates"][hour]), 4))
        drh += [round(float(v), 4) for v in s["rates"]]
        pl = places.get(s["id"])
        dopen.append(sum(1 << h for h, o in enumerate(pl["open"]) if o) if pl else (1 << 24) - 1)
        dvisit += [round(float(v), 4) for v in (pl["visit"] if pl else [0.0] * 5)]
        ddwell += [float(v) for v in (pl["dwell_s"] if pl else [0.0, 0.0])]
        dpolice.append(1 if s["id"] in stations else 0)
        dtransit.append(1 if s.get("kind") == "station" and s.get("owner_id") in served else 0)
    shape, danger, pal = [], [], []
    size = max((len(v) for v in crowd["palettes"].values()), default=0)
    for d in plan["districts"]:
        shape += [float(v) for v in d["shape"]]
        danger.append(float(d["danger"]))
        cols = crowd["palettes"].get(d["id"]) or ["#808080"]
        for k in range(size):
            pal += _lin(cols[k % len(cols)])
    # (LG2: per district and look group the dye colors, linear; the districts' people by
    # group and wear)
    of = crowd.get("outfits") or {}
    opal, ogrp, owear = [], [], []
    ncol = 0
    if of:
        ncol = max(len(c) for rows_ in of["palettes"].values() for c in rows_)
        for d in plan["districts"]:
            rows_ = of["palettes"].get(d["id"]) or [["#808080"]] * len(of["groups"])
            for cols in rows_:
                for k in range(ncol):
                    opal += _lin(cols[k % len(cols)])
            # (LG8: the clear weather's groups where the plan has them: the runtime blends in
            # the rain looks by atmosgen's rain)
            src = of.get("district_groups_clear") or of["district_groups"]
            ogrp += [float(v) for v in src.get(d["id"]) or
                     [1.0 / len(of["groups"])] * len(of["groups"])]
            owear.append(float(of["wear"].get(d["id"], 0.3)))
    av, sp = crowd["avoid"], crowd["speeds"]
    ps = persons({"palette": [], "persons": crowd["persons"]})
    ps["person_tint"] = [0.5] * (3 * len(ps.get("person_char") or []))
    ps["person_tint_index"] = [int(v) for v in crowd["persons"].get("tint") or []]
    if plan.get("places"):
        # (LG4: life at places)
        out.update(pack_places(plan, walk, gids, lane_of, rows, slots, door_index))
        out.update({"door_rates_h": drh, "door_open": dopen, "door_visit": dvisit,
                    "door_dwell": ddwell, "door_police": dpolice})
    if plan.get("weather"):
        out.update(pack_weather(plan["weather"], of))
        out.update({"walk_cover_starts": cov_starts, "walk_cover": cov,
                    "walk_road_side": rside,
                    "walk_night": night if any_night else []})
    out.update({"walk_kinds": kinds, "walk_district": dist, "walk_people": ppl,
                "walk_signal": sig, "signal_windows": windows,
                "district_ids": dids, "district_shape": shape, "district_danger": danger,
                "district_palettes": pal, "palette_size": size,
                "outfit_palettes": [round(v, 4) for v in opal], "outfit_colors": ncol,
                "outfit_groups": len(of.get("groups") or []), "district_groups": ogrp,
                "district_wear": owear,
                "door_lanes": dl, "door_dists": dd, "door_points": dp, "door_rates": dr,
                **({"door_transit": dtransit} if served else {}),
                "crowd": {"hour": hour, "pool": int(crowd["pool"]),
                          "live_m": float(crowd["live_m"]), "trip_s": float(crowd["trip_s"]),
                          "groups": [float(v) for v in crowd["groups"]],
                          "group_gap_m": float(crowd["group_gap_m"]),
                          "jaywalk": [float(v) for v in crowd["jaywalk"]],
                          "reach_m": float(av["reach_m"]), "personal_m": float(av["personal_m"]),
                          "player_m": float(av["player_m"]), "avoid_m": float(av["avoid_m"]),
                          "stairs": float(sp["stairs"]),
                          "escalator": [float(v) for v in sp["escalator"]],
                          "elevator": float(sp["elevator"])},
                **ps})
    return out


UMBRELLA_MESHES = {"canopy": "/Engine/BasicShapes/Cone", "shaft": "/Engine/BasicShapes/Cylinder"}


def pack_weather(w: dict, outfits: dict) -> dict:
    """LG8: the weather's table (per state of `weather.states`, `WEATHER_KEYS` floats, and its
    rain rate), the plan's own state, the rain looks' group, the umbrellas (canopy colors, lit
    shaft colors, share lit, their size and hold), shelter (the stand's length) and the
    reactions' settings, flat."""
    names = list(w["states"])
    keys = list(w["keys"])
    u = w["umbrella"]
    rx = w["reactions"]
    return {"weather_names": names, "weather_keys": keys,
            "weather_life": [float(w["states"][n][k]) for n in names for k in keys],
            "weather_rain": [float(w["rain"].get(n, 0.0)) for n in names],
            "weather_plan": w["state"],
            "rain_group": int(outfits.get("rain_group", -1)) if outfits else -1,
            "umbrella_colors": [float(v) for c in u["colors"] for v in c],
            "umbrella_lit": [float(v) for c in u["lit"] for v in c],
            "umbrella": [float(u[k]) for k in ("lit_share", "canopy_m", "canopy_h_m", "height",
                                               "side_m", "fwd_m", "tilt_deg", "shaft_m")],
            "umbrella_meshes": dict(UMBRELLA_MESHES),
            "shelter_s": [float(v) for v in w["shelter"]["dwell_s"]],
            "reactions": {"look": bool(rx.get("look", True)), "flee": bool(rx.get("flee", True)),
                          "gather": bool(rx.get("gather", True)),
                          "look_m": float(rx["look_m"]), "flee_m": float(rx["flee_m"]),
                          "flee_s": float(rx["flee_s"]), "flee_pace": float(rx["flee_pace"]),
                          "gather_m": float(rx["gather_m"]), "gather_s": float(rx["gather_s"]),
                          "gather_share": float(rx["gather_share"]),
                          "ring_m": [float(v) for v in rx["ring_m"]],
                          "stay_s": [float(v) for v in rx["stay_s"]]},
            "stuck": {k: float(v) for k, v in (w.get("traffic") or {}).items()}}


def pack_places(plan: dict, walk: list, gids: list, lane_of: dict, rows: dict, slots: list,
                door_index: dict) -> dict:
    """LG4: life at places, flat: every slot (its kind's code, walkway lane, distance along it,
    use points, users per band, dwell, role, turf, clip, the door a queue goes in at); per
    walkway lane its gang turf, gang members and police walking per band, whether police patrol
    it; the turfs' factions and their dye colors (linear); the pool's roles; the settings."""
    pl = plan["places"]
    kinds = pl["kinds"]
    anims = pl["anims"]
    turfs = (plan.get("gangs") or {}).get("turfs") or []
    tidx = {t["id"]: k for k, t in enumerate(turfs)}
    facs = sorted({t["faction_id"] for t in turfs})
    fidx = {f: k for k, f in enumerate(facs)}
    fcols = []
    ncol = max((len(t["colors"]) for t in turfs), default=0)
    for f in facs:
        cols = next(t["colors"] for t in turfs if t["faction_id"] == f)
        for k in range(ncol):
            fcols += _lin(cols[k % len(cols)])
    sk, sl, sd, sps, sp, su, sw, sr, st, sa, sdoor, sseat = ([] for _ in range(12))
    roles = {"crowd": 0, "gang": 1, "police": 2}
    for s in sorted(slots, key=lambda s: s["id"]):
        k = lane_of.get(s.get("walkway_id"))
        if k is None or not s.get("points"):
            continue
        p0 = s["points"][0]
        sk.append(kinds.index(s["kind"]))
        sl.append(k)
        sd.append(round(_along(walk[k][2], p0[0], p0[1]), 3))
        sps.append(len(sp) // 4)
        for p in s["points"]:
            sp += [round(float(v), 3) for v in p]
        su += [round(float(v), 4) for v in (s.get("use") or [0.0] * 5)]
        sw += [float(v) for v in (s.get("dwell_s") or [30.0, 120.0])]
        sr.append(roles.get(s.get("role"), 0))
        st.append(tidx.get(s.get("turf_id"), -1))
        sa.append(anims.index(s.get("anim") or "idle") if (s.get("anim") or "idle") in anims
                  else 0)
        pid = s.get("place_id") or ""
        sdoor.append(door_index.get("spawn." + pid[len("place."):], -1)
                     if s["kind"] == "bar_queue" else -1)
        # (delta_rebuild: its points' z the surface under them, over the datum as the lanes)
        sseat.append(1 if s.get("seated") else 0)
    sps.append(len(sp) // 4)
    wturf, wgang, wpol, wpat = [], [], [], []
    for e in walk:
        r = rows.get(gids[e[0]]) or {}
        wturf.append(tidx.get(r.get("turf"), -1))
        wgang += [round(float(v), 4) for v in (r.get("gang") or [0.0] * 5)]
        wpol += [round(float(v), 4) for v in (r.get("police") or [0.0] * 5)]
        wpat.append(1 if r.get("patrol") else 0)
    gp = plan.get("gangs") or {}
    po = plan.get("police") or {}
    return {"slot_kinds": sk, "slot_lanes": sl, "slot_dists": sd, "slot_point_starts": sps,
            "slot_points": sp, "slot_use": su, "slot_dwell": sw, "slot_roles": sr,
            "slot_turfs": st, "slot_anims": sa, "slot_doors": sdoor, "slot_seated": sseat,
            "slot_kind_names": list(kinds),
            "slot_kind_behaviors": [pl["slot_kinds"][k]["behavior"] for k in kinds],
            "walk_turf": wturf, "walk_gang": wgang, "walk_police": wpol, "walk_patrol": wpat,
            "turf_faction": [fidx[t["faction_id"]] for t in turfs],
            "turf_ids": [t["id"] for t in turfs],
            "faction_palettes": [round(v, 4) for v in fcols], "faction_colors": ncol,
            "person_role": [int(v) for v in (plan["crowd"]["persons"].get("role") or [])],
            "places": {"visit_p": float(pl["visit_p"]),
                       "gang_groups": [float(v) for v in gp.get("groups") or [1.0]],
                       "slots": len(sk), "turfs": len(turfs),
                       "gang_pool": int(gp.get("pool") or 0),
                       "police_pool": int(po.get("pool") or 0)}}


def conflicts(pts: list[list[list[float]]], connector: list[bool], reach: float,
              dz: float = 3.0) -> list[list[int]]:
    """LG5: per drive lane the junction connectors it may not be driven at once with: for a
    connector, every other connector whose line comes within `reach` (m, in plan) of its own
    where the two are within `dz` in height (crossing, merging or leaving one lane); none for
    a lane. GEOS's tree and distances (a pair is symmetric)."""
    import shapely
    ids = [k for k, c in enumerate(connector) if c and len(pts[k]) >= 2]
    out: list[list[int]] = [[] for _ in pts]
    if not ids:
        return out
    geoms = [shapely.LineString([(p[0], p[1], p[2]) for p in pts[k]]) for k in ids]
    tree = shapely.STRtree(geoms)
    a, b = tree.query(geoms, predicate="dwithin", distance=reach)
    for i, j in zip(a.tolist(), b.tolist()):
        if i >= j:
            continue
        gi, gj = geoms[i], geoms[j]
        pa, pb = shapely.shortest_line(gi, gj).coords
        za = shapely.line_interpolate_point(gi, shapely.line_locate_point(gi, shapely.Point(pa)))
        zb = shapely.line_interpolate_point(gj, shapely.line_locate_point(gj, shapely.Point(pb)))
        if abs(shapely.get_coordinates(za, include_z=True)[0][2] -
               shapely.get_coordinates(zb, include_z=True)[0][2]) > dz:
            continue
        out[ids[i]].append(ids[j])
        out[ids[j]].append(ids[i])
    return [sorted(c) for c in out]


def traffic_cars(traffic: dict, veh: dict | None, dids: list[str]) -> dict:
    """LG5: the traffic's models (the plan's that the project has: AG18's packs imported with
    the city's parked cars), every part of them (mesh, pivot, shadow, a wheel's radius to spin
    by), each model's length, the pool's slots by model, the districts' fleets and paints in
    those models' order."""
    have = (veh or {}).get("cars") or {}
    models = [m for m in traffic["models"] if m in have]
    out = {"models": models, "parts": [], "car_lengths": [], "traffic_slots": [],
           "traffic_weights": [], "traffic_paints": []}
    if not models:
        return out
    at = {m: k for k, m in enumerate(traffic["models"])}
    for mi, car in enumerate(models):
        rec = have[car]
        dim = rec.get("dimensions") or {}
        out["car_lengths"].append(round(float(dim.get("length") or 4.8), 3))
        for p in rec["parts"]:
            spin = p.get("kind") == "wheel" and p.get("spins", True) is not False
            out["parts"].append({"model": mi, "mesh": f"{rec['folder']}/SM_{car}_{p['name']}",
                                 "shadow": p.get("kind") not in ("glass", "wheel", "brake"),
                                 "pivot": [float(v) for v in p.get("pivot", [0.0, 0.0, 0.0])],
                                 "spin_radius": round(float(p.get("radius") or 0.0), 4)
                                 if spin else 0.0,
                                 "cull_m": TRAFFIC_CULL_M.get(p.get("kind"),
                                                             TRAFFIC_CULL_M["other"])})
    # (a slot of a model the project lacks: the models it has, in turn)
    for k, s in enumerate(traffic["slots"]):
        m = traffic["models"][s]
        out["traffic_slots"].append(models.index(m) if m in have else k % len(models))
    kp = None
    for d in dids:
        w = traffic["weights"].get(d) or [0.0] * len(traffic["models"])
        out["traffic_weights"].append([round(float(w[at[m]]), 5) for m in models])
        pd = traffic["paints"].get(d) or []
        rows = [pd[at[m]] for m in models]
        kp = len(rows[0]) // 9 if rows and rows[0] else 0
        out["traffic_paints"].append([v for r in rows for v in r])
    out["paints_per"] = kp or 0
    if traffic.get("police_slots") and traffic.get("police_model") in have:
        # (LG4: the slots kept for patrol cars, a model the project has, in the livery)
        flag = [0] * len(traffic["slots"])
        for k in traffic["police_slots"]:
            flag[k] = 1
        out["traffic_police"] = flag
        out["police_paint"] = [round(float(v), 4) for v in traffic["police_paint"]]
    return out


def pack_traffic(plan: dict, pdir: Path, graphs: dict, veh: dict | None) -> dict:
    """LG5: the city's traffic, flat: every lane and junction connector of the lane graph a
    drive lane (`pack_drive_lanes`, cars_steam's speeds) with its cars per hour band, district,
    whether it is on the lane graph's largest strongly connected part (cars drive only there),
    the signal window it stops at and where (m back from its end), the connectors it may not
    be driven at once with; the signals' windows for cars (cycle, offset, green from, green
    to, amber to: s); the models, pool slots, fleets and paints; the settings."""
    tr = plan["traffic"]
    g = graphs["lanes"]
    drive = [e for e in _elements(g) if len(e[2]) >= 2]
    gids = g.get("ids") or [str(e[0]) for e in drive]
    rows = {}
    for t in plan["tiles"]:
        tile = json.loads((pdir / t["file"]).read_text(encoding="utf-8"))
        for r in tile.get("drives") or []:
            rows[r["id"]] = r
    out = pack_drive_lanes(graphs, drive, tr["drive_speeds"], tr["drive"],
                           {e[0]: (rows.get(gids[e[0]]) or {}).get("road_class", "")
                            for e in drive})
    st = out["drive_starts"]
    fp = out["drive_points"]
    pts = [[fp[3 * i:3 * i + 3] for i in range(st[k], st[k + 1])] for k in range(len(drive))]
    succ = [out["drive_links"][out["drive_link_starts"][k]:out["drive_link_starts"][k + 1]]
            for k in range(len(drive))]
    main = main_component(succ)
    # (the districts in the plan's order: the crowd's, whose days DistrictShape holds)
    dids = [d["id"] for d in plan["districts"]]
    didx = {d: k for k, d in enumerate(dids)}
    sigs = []
    sfile = pdir / "signals.json"
    if sfile.is_file():
        sigs = json.loads(sfile.read_text(encoding="utf-8")).get("signals") or []
    win, windows = {}, []
    for s in sigs:
        for p in s["phases"]:
            win[(s["id"], p["index"])] = len(windows) // 5
            g0 = float(p["start_s"])
            g1 = g0 + float(p["green_s"])
            windows += [float(s["cycle_s"]), float(s["offset_s"]), g0, round(g1, 3),
                        round(g1 + float(p["amber_s"]), 3)]
    cars, dist, msk, sig, back, pol = [], [], [], [], [], []
    for k, e in enumerate(drive):
        r = rows.get(gids[e[0]]) or {}
        cars += [round(float(v), 4) for v in (r.get("vehicles") or [0.0] * 5)]
        pol += [round(float(v), 4) for v in (r.get("police") or [0.0] * 5)]
        dist.append(didx.get(r.get("district_id"), -1))
        msk.append(1 if k in main else 0)
        w = win.get((r.get("signal"), r.get("phase")), -1)
        sig.append(w)
        back.append(round(float(r.get("stop_back_m") or 0.0), 3) if w >= 0 else 0.0)
    fl = tr["follow"]
    con = conflicts(pts, [e[1] != "lane" for e in drive], float(fl["conflict_m"]))
    cflat, cstart = [], [0]
    for c in con:
        cflat += c
        cstart.append(len(cflat))
    out.update({"drive_cars": cars, "drive_district": dist, "drive_main": msk,
                "drive_signal": sig, "drive_stop_back": back, "drive_windows": windows,
                "drive_conflicts": cflat, "drive_conflict_starts": cstart,
                # (LG4: patrol cars per lane and band; the pool's patrol car slots, their
                # livery)
                **({"drive_police": pol} if tr.get("police_slots") else {}),
                "traffic": {"hour": int(tr["hour"]), "pool": int(tr["pool"]),
                            "live_m": float(tr["live_m"]), "scale": 1.0,
                            "districts": dids,
                            **{k: float(v) for k, v in fl.items()}},
                **traffic_cars(tr, veh, dids)})
    return out


# LG6: the trains' stand-ins (decision 6: the Mac designs the trains; lifegen generates no
# vehicle geometry): per mode the parts of a car, each a mesh of the engine's basic shapes (1 m
# across, its pivot at its middle) at its middle in the car's frame (m: x forward, y left, z up
# from the body's bottom) and its size, of a kind the runtime colors: `body` (light, the line's
# color in it), `window` (dark glass lit by night), `accent` (a band in the line's color, glowing),
# `dark` (gear). A mode's pack replaces its parts here (its meshes, `scale` 1) when the Mac's
# designs are in; the runtime adds each car's door leaves and the lit doorways between them.
TRANSIT_MESHES = {"cube": "/Engine/BasicShapes/Cube", "cylinder": "/Engine/BasicShapes/Cylinder"}
TRANSIT_KINDS = ("body", "window", "accent", "dark")


def transit_model(mode: str) -> list[dict]:
    """A car's parts for `mode` (`TRANSIT_MODELS`)."""
    from lifegen.presets import TRANSIT_MODES
    m = TRANSIT_MODES[mode]
    L, W, H, f = m["car_m"], m["width_m"], m["height_m"], m["floor_m"]
    win = min(1.0, H - f - 1.3)
    parts = [{"mesh": "cube", "kind": "body", "at": [0.0, 0.0, H / 2.0], "size": [L, W, H]},
             {"mesh": "cube", "kind": "window", "at": [0.0, 0.0, f + 1.0 + win / 2.0],
              "size": [L * 0.88, W + 0.04, win]},
             {"mesh": "cube", "kind": "accent", "at": [0.0, 0.0, f + 0.45],
              "size": [L * 0.995, W + 0.03, 0.14]},
             {"mesh": "cube", "kind": "dark", "at": [0.0, 0.0, H + 0.1],
              "size": [L * 0.7, W * 0.55, 0.2]}]
    # (a lamp band across each end, lit: a train seen from ahead or behind in the dark)
    for x in (-L / 2.0 - 0.01, L / 2.0 + 0.01):
        parts.append({"mesh": "cube", "kind": "window", "at": [x, 0.0, f + 0.7],
                      "size": [0.04, W * 0.7, 0.18]})
    if mode in ("metro", "elevated_rail"):
        for x in (-0.33 * L, 0.33 * L):
            parts.append({"mesh": "cube", "kind": "dark", "at": [x, 0.0, -0.4],
                          "size": [3.0, W * 0.8, 0.8]})
    elif mode == "maglev":
        parts.append({"mesh": "cube", "kind": "dark", "at": [0.0, 0.0, -0.2],
                      "size": [L * 0.96, W * 0.9, 0.4]})
        parts.append({"mesh": "cube", "kind": "accent", "at": [0.0, 0.0, H - 0.25],
                      "size": [L * 0.98, W + 0.02, 0.08]})
    elif mode == "monorail":
        # (the car beside the beam, its arms over the beam's top: the beam is on its left)
        y0, y1 = W / 2.0 - 0.1, m["track_m"] + 0.55
        for x in (-0.3 * L, 0.3 * L):
            parts.append({"mesh": "cube", "kind": "dark", "at": [x, (y0 + y1) / 2.0,
                                                                  -m["base_m"] + 0.25],
                          "size": [1.8, y1 - y0, 0.5]})
    elif mode == "sky_tube":
        parts.append({"mesh": "cylinder", "kind": "accent", "at": [0.0, 0.0, H + 0.02],
                      "size": [W * 0.5, W * 0.5, 0.04]})
    return parts


TRANSIT_MODELS = {k: transit_model(k) for k in ("metro", "elevated_rail", "monorail", "maglev",
                                                "sky_tube")}


def pack_transit(plan: dict, pdir: Path, graphs: dict) -> dict:
    """LG6: transit, flat: per line its mode, color (linear), loop, track (its points, citygen
    m), turn points, the train as run and drawn (cars, car size, floor, base over the line, its
    track off the middle, doors, sides), the cycle and its samples, the stop events, the trains
    per band; per stop its platform walkway (a walkway lane), where along the track, the
    people boarding and leaving per band, the height they board at, whether at the walkway's
    level; per walkway lane how far off its middle people keep (a platform's trains) and its
    width; the meshes and per mode the parts of a car (`TRANSIT_MODELS`); the settings."""
    tr = plan.get("transit") or {}
    f = pdir / (tr.get("file") or "timetables.json")
    if not tr.get("lines") or not f.is_file():
        return {}
    tt = json.loads(f.read_text(encoding="utf-8"))
    walk = [e for e in _elements(graphs["walkways"]) if len(e[2]) >= 2]
    gids = graphs["walkways"].get("ids") or [str(e[0]) for e in walk]
    lane_of = {gids[e[0]]: k for k, e in enumerate(walk)}
    modes = [m for m in TRANSIT_MODELS if any(ln["mode"] == m for ln in tt["lines"])]
    mesh_names = list(TRANSIT_MESHES)
    out = {k: [] for k in (
        "transit_line_mode", "transit_line_color", "transit_line_loop", "transit_line_car",
        "transit_line_turn", "transit_line_cycle", "transit_line_dt", "transit_line_trains",
        "transit_point_starts", "transit_points", "transit_sample_starts", "transit_samples",
        "transit_event_starts", "transit_events", "transit_stop_starts", "transit_stop_lane",
        "transit_stop_s", "transit_stop_board", "transit_stop_alight", "transit_stop_z",
        "transit_stop_level", "transit_part_starts", "transit_parts")}
    clear = [0.0] * len(walk)
    width = [float(e[3]) for e in walk]
    for key in ("transit_point_starts", "transit_sample_starts", "transit_event_starts",
                "transit_stop_starts"):
        out[key].append(0)
    ids, names = [], []
    for ln in tt["lines"]:
        c = ln["car"]
        ids.append(ln["id"])
        names.append(ln["name"])
        out["transit_line_mode"].append(modes.index(ln["mode"]))
        out["transit_line_color"] += _lin(ln["color"])
        out["transit_line_loop"].append(1 if ln["loop"] else 0)
        # (12 floats a line: cars, car length, gap, width, height, floor, base, track, doors a
        # side, door width, sides open (1 the right, 2 both), at the walkway's level)
        out["transit_line_car"] += [float(ln["cars"]), float(c["car_m"]), float(c["gap_m"]),
                                    float(c["width_m"]), float(c["height_m"]),
                                    float(c["floor_m"]), float(c["base_m"]),
                                    float(c["track_m"]), float(c["doors"]),
                                    float(c["door_m"]), float(c["sides"]),
                                    1.0 if c["board_level"] else 0.0]
        out["transit_line_turn"] += [float(v) for v in ln["turn"]]
        out["transit_line_cycle"].append(float(ln["cycle_s"]))
        out["transit_line_dt"].append(float(ln["sample_s"]))
        out["transit_line_trains"] += [int(v) for v in ln["trains"]]
        for p in ln["points"]:
            out["transit_points"] += [float(v) for v in p]
        out["transit_point_starts"].append(len(out["transit_points"]) // 3)
        out["transit_samples"] += [float(v) for v in ln["samples"]]
        out["transit_sample_starts"].append(len(out["transit_samples"]))
        for e in ln["events"]:
            out["transit_events"] += [float(e[0]), float(e[1]), float(e[2]), float(e[3])]
        out["transit_event_starts"].append(len(out["transit_events"]) // 4)
        for st in ln["stops"]:
            k = lane_of.get(st.get("walkway_id"), -1)
            out["transit_stop_lane"].append(k)
            out["transit_stop_s"].append(float(st["s"]))
            out["transit_stop_board"] += [float(v) for v in st["board"]]
            out["transit_stop_alight"] += [float(v) for v in st["alight"]]
            out["transit_stop_z"].append(float(st["board_z"]))
            out["transit_stop_level"].append(1 if st.get("board_level", c["board_level"]) else 0)
            if k >= 0 and st.get("clear_m"):
                clear[k] = max(clear[k], float(st["clear_m"]))
                width[k] = max(width[k], 2.0 * float(st.get("half_m") or 0.0))
        out["transit_stop_starts"].append(len(out["transit_stop_lane"]))
    out["transit_part_starts"].append(0)
    for m in modes:
        for p in TRANSIT_MODELS[m]:
            # (8 floats a part: mesh, kind, middle (3), scale (3): the basic shapes are 1 m)
            out["transit_parts"] += [float(mesh_names.index(p["mesh"])),
                                     float(TRANSIT_KINDS.index(p["kind"]))] + \
                [float(v) for v in p["at"]] + [float(v) for v in p["size"]]
        out["transit_part_starts"].append(len(out["transit_parts"]) // 8)
    st_ = tr.get("settings") or {}
    out.update({"transit_meshes": [TRANSIT_MESHES[k] for k in mesh_names],
                "transit_modes": modes, "transit_line_ids": ids, "transit_line_names": names,
                "walk_clear": [round(v, 3) for v in clear],
                "walk_transit_width": [round(v, 3) for v in width],
                "transit": {"lines": len(ids), "cross_m": float(st_.get("cross_m", 90.0)),
                            "hour": int(tr.get("hour", 23))}})
    return out


# LG7: what flies and floats, drawn (decision 6: the Mac designs the missing kinds; lifegen
# generates no vehicle geometry): flying cars and police fliers are AG18's hover cars where the
# project has them (`HOVER`), with nav lights and a police light bar added; every other kind a
# stand-in of the engine's basic shapes (1 m across, pivot at the middle) per kind in its frame
# (m: x forward, y left, z up from its keel or skids: a boat's z 0 is the water's surface), a
# part `[mesh, kind, middle, size, cull_m]` of a kind the runtime colors (`AW_PART_KINDS`: body
# (light, the route's color in it), window (dark glass lit by night), accent (the route's color,
# glowing), dark (gear), nav red, nav green, strobe (white, flashing), police red and blue
# (flashing in turn), lamp (bright white), hull (the route's color), beacon (red, flashing));
# `cull_m` 0 drawn as far as the vehicle is. A kind's pack replaces its parts here when the
# Mac's designs are in; the runtime is unchanged.
AW_MESHES = {"cube": "/Engine/BasicShapes/Cube", "cylinder": "/Engine/BasicShapes/Cylinder",
             "sphere": "/Engine/BasicShapes/Sphere"}
AW_PART_KINDS = ("body", "window", "accent", "dark", "nav_red", "nav_green", "strobe",
                 "police_red", "police_blue", "lamp", "hull", "beacon")
HOVER = ("kestrel_dart", "kestrel_meridian", "kestrel_atlas")
AW_PAINT = [0.35, 0.36, 0.38, 0.08, 0.08, 0.09, 0.8, 0.1, 0.1]


def _p(mesh, kind, at, size, cull=0.0) -> dict:
    return {"mesh": mesh, "kind": kind, "at": [float(v) for v in at],
            "size": [float(v) for v in size], "cull_m": float(cull)}


def nav_lights(L: float, W: float, H: float, cull: float = 0.0) -> list[dict]:
    """A flier's lights: red on its left, green on its right, a white strobe on top and a lamp
    ahead (`cull` past which the small ones are not drawn)."""
    s = max(0.16, 0.035 * max(L, W))
    return [_p("sphere", "nav_red", [0.0, W / 2.0 + s / 2.0, H * 0.45], [s, s, s], cull),
            _p("sphere", "nav_green", [0.0, -W / 2.0 - s / 2.0, H * 0.45], [s, s, s], cull),
            _p("sphere", "strobe", [-L * 0.3, 0.0, H + s / 2.0], [s * 1.3] * 3, cull),
            _p("cube", "lamp", [L / 2.0 + 0.01, 0.0, H * 0.35], [0.03, W * 0.5, s * 0.8], cull)]


def aw_model(kind: str) -> list[dict]:
    """A kind's stand-in (`AIRWATER_MODELS`)."""
    if kind in ("car", "police"):
        L, W, H = 4.8, 2.0, 1.5
        parts = [_p("cube", "body", [0.0, 0.0, 0.65], [L, W, 0.9]),
                 _p("cube", "window", [-0.2, 0.0, 1.25], [2.2, W * 0.85, 0.5]),
                 _p("cube", "accent", [0.0, 0.0, 0.18], [L * 0.85, W * 0.8, 0.05])]
        for x in (-1.6, 1.6):
            for y in (-1.15, 1.15):
                parts.append(_p("cylinder", "dark", [x, y, 0.3], [0.9, 0.9, 0.3], 300.0))
        parts.append(_p("cube", "beacon", [-L / 2.0 - 0.01, 0.0, 0.7], [0.03, W * 0.7, 0.12]))
        return parts + nav_lights(L, W, H)
    if kind == "drone":
        parts = [_p("cube", "body", [0.0, 0.0, 0.22], [0.5, 0.5, 0.16], 600.0),
                 _p("cube", "dark", [0.0, 0.0, 0.25], [0.95, 0.06, 0.04], 400.0),
                 _p("cube", "dark", [0.0, 0.0, 0.25], [0.06, 0.95, 0.04], 400.0),
                 _p("cube", "hull", [0.0, 0.0, 0.07], [0.32, 0.32, 0.14], 400.0),
                 _p("cube", "accent", [0.26, 0.0, 0.22], [0.02, 0.3, 0.04], 900.0)]
        for x in (-0.42, 0.42):
            for y in (-0.42, 0.42):
                parts.append(_p("cylinder", "dark", [x, y, 0.29], [0.36, 0.36, 0.015], 250.0))
        parts.append(_p("sphere", "nav_red", [0.0, 0.3, 0.2], [0.07] * 3, 1200.0))
        parts.append(_p("sphere", "nav_green", [0.0, -0.3, 0.2], [0.07] * 3, 1200.0))
        return parts
    if kind == "media":
        L, W, H = 3.6, 1.8, 1.4
        parts = [_p("cube", "body", [0.0, 0.0, 0.8], [L, W, 1.1]),
                 _p("cube", "window", [0.9, 0.0, 1.0], [1.4, W + 0.02, 0.5]),
                 _p("cube", "accent", [0.0, 0.0, 0.5], [L + 0.02, W + 0.02, 0.18]),
                 _p("sphere", "dark", [L / 2.0 - 0.3, 0.0, 0.2], [0.6, 0.6, 0.6]),
                 _p("sphere", "lamp", [L / 2.0 - 0.1, 0.0, 0.05], [0.3, 0.3, 0.3])]
        for x in (-2.2, 2.2):
            for y in (-2.0, 2.0):
                parts.append(_p("cylinder", "dark", [x * 0.8, y, 1.0], [1.6, 1.6, 0.35]))
                parts.append(_p("cube", "dark", [x * 0.4, y * 0.5, 1.0], [abs(x) * 0.8, 0.12, 0.1]))
        return parts + nav_lights(L, W * 2.2, H + 0.2)
    if kind == "aircraft":
        L, W, H = 42.0, 36.0, 12.0
        parts = [_p("cube", "body", [0.0, 0.0, 2.8], [L, 4.6, 4.6]),
                 _p("cube", "window", [2.0, 0.0, 3.6], [32.0, 4.65, 0.45]),
                 _p("cube", "body", [-1.0, 0.0, 1.6], [7.0, W, 0.7]),
                 _p("cube", "body", [-L / 2.0 + 3.0, 0.0, 7.5], [5.5, 0.5, 7.0]),
                 _p("cube", "body", [-L / 2.0 + 2.5, 0.0, 3.6], [3.5, 13.0, 0.4]),
                 _p("cube", "dark", [1.0, 6.5, 0.6], [4.5, 2.2, 2.2]),
                 _p("cube", "dark", [1.0, -6.5, 0.6], [4.5, 2.2, 2.2]),
                 _p("cube", "accent", [0.0, 0.0, 2.2], [L * 0.9, 4.65, 0.3]),
                 _p("sphere", "nav_red", [-1.0, W / 2.0, 1.6], [0.6] * 3),
                 _p("sphere", "nav_green", [-1.0, -W / 2.0, 1.6], [0.6] * 3),
                 _p("sphere", "strobe", [-1.5, W / 2.0, 1.6], [0.7] * 3),
                 _p("sphere", "strobe", [-1.5, -W / 2.0, 1.6], [0.7] * 3),
                 _p("sphere", "strobe", [-L / 2.0, 0.0, 3.0], [0.7] * 3),
                 _p("sphere", "beacon", [0.0, 0.0, 5.2], [0.7] * 3),
                 _p("sphere", "beacon", [0.0, 0.0, 0.4], [0.7] * 3),
                 _p("cube", "lamp", [L / 2.0, 0.0, 2.0], [0.1, 1.0, 0.4])]
        return parts
    if kind == "shuttle":
        L, W = 38.0, 22.0
        parts = [_p("cube", "body", [-2.0, 0.0, 3.5], [30.0, 8.0, 5.5]),
                 _p("cube", "body", [16.0, 0.0, 3.0], [8.0, 5.5, 3.6]),
                 _p("cube", "window", [17.0, 0.0, 4.2], [4.0, 5.6, 0.9]),
                 _p("cube", "body", [-6.0, 0.0, 1.6], [16.0, W, 0.7]),
                 _p("cube", "body", [-15.0, 4.0, 7.5], [6.0, 0.5, 5.0]),
                 _p("cube", "body", [-15.0, -4.0, 7.5], [6.0, 0.5, 5.0]),
                 _p("cube", "dark", [-6.0, 0.0, 0.5], [24.0, 7.0, 1.0]),
                 _p("cube", "accent", [-17.2, 0.0, 3.5], [0.4, 6.0, 4.0]),
                 _p("cube", "accent", [-2.0, 0.0, 6.3], [26.0, 8.05, 0.2]),
                 _p("sphere", "nav_red", [-6.0, W / 2.0, 1.6], [0.5] * 3),
                 _p("sphere", "nav_green", [-6.0, -W / 2.0, 1.6], [0.5] * 3),
                 _p("sphere", "strobe", [-17.0, 0.0, 10.2], [0.6] * 3),
                 _p("sphere", "beacon", [0.0, 0.0, 6.5], [0.6] * 3),
                 _p("cube", "lamp", [20.0, 0.0, 1.6], [0.1, 2.0, 0.4])]
        return parts
    if kind == "boat":
        return [_p("cube", "hull", [0.0, 0.0, 0.1], [7.0, 2.2, 0.9]),
                _p("cube", "dark", [3.6, 0.0, 0.2], [0.8, 1.2, 0.7]),
                _p("cube", "body", [-0.6, 0.0, 1.0], [2.6, 1.8, 0.9]),
                _p("cube", "window", [-0.4, 0.0, 1.15], [2.4, 1.84, 0.35]),
                _p("cube", "lamp", [3.95, 0.0, 0.55], [0.05, 0.3, 0.15], 800.0),
                _p("sphere", "nav_red", [2.5, 1.12, 0.6], [0.12] * 3, 800.0),
                _p("sphere", "nav_green", [2.5, -1.12, 0.6], [0.12] * 3, 800.0),
                _p("sphere", "lamp", [-3.4, 0.0, 1.0], [0.12] * 3, 800.0)]
    if kind == "taxi":
        return [_p("cube", "hull", [0.0, 0.0, 0.15], [9.0, 2.8, 1.0]),
                _p("cube", "body", [-0.3, 0.0, 1.3], [6.0, 2.5, 1.3]),
                _p("cube", "window", [-0.3, 0.0, 1.45], [5.8, 2.54, 0.6]),
                _p("cube", "accent", [-0.3, 0.0, 2.1], [1.6, 0.6, 0.35]),
                _p("cube", "dark", [-0.3, 0.0, 0.7], [9.05, 2.85, 0.12]),
                _p("cube", "lamp", [4.55, 0.0, 0.7], [0.05, 0.5, 0.2]),
                _p("sphere", "nav_red", [3.0, 1.42, 0.9], [0.14] * 3),
                _p("sphere", "nav_green", [3.0, -1.42, 0.9], [0.14] * 3)]
    if kind == "ferry":
        parts = [_p("cube", "hull", [0.0, 0.0, 0.2], [26.0, 9.0, 1.8]),
                 _p("cube", "dark", [0.0, 0.0, 1.15], [26.1, 9.1, 0.15]),
                 _p("cube", "body", [0.0, 0.0, 2.4], [16.0, 7.6, 2.4]),
                 _p("cube", "window", [0.0, 0.0, 2.6], [15.6, 7.65, 1.0]),
                 _p("cube", "body", [0.0, 0.0, 4.4], [6.0, 5.0, 1.6]),
                 _p("cube", "window", [0.0, 0.0, 4.6], [5.8, 5.05, 0.7]),
                 _p("cube", "accent", [0.0, 0.0, 3.65], [16.05, 7.66, 0.15]),
                 _p("cube", "lamp", [13.05, 0.0, 1.3], [0.05, 1.0, 0.25]),
                 _p("cube", "lamp", [-13.05, 0.0, 1.3], [0.05, 1.0, 0.25]),
                 _p("sphere", "nav_red", [0.0, 3.85, 5.3], [0.25] * 3),
                 _p("sphere", "nav_green", [0.0, -3.85, 5.3], [0.25] * 3),
                 _p("sphere", "lamp", [0.0, 0.0, 6.2], [0.25] * 3)]
        return parts
    if kind == "ship":
        parts = [_p("cube", "hull", [0.0, 0.0, -1.5], [120.0, 20.0, 9.0]),
                 _p("cube", "dark", [0.0, 0.0, -5.2], [120.2, 20.2, 1.8]),
                 _p("cube", "dark", [0.0, 0.0, 3.2], [118.0, 19.0, 0.4])]
        cols = ("hull", "body", "dark", "hull", "body")
        for q in range(5):
            parts.append(_p("cube", cols[q], [-28.0 + q * 14.5, 0.0, 6.4], [13.5, 17.0, 6.0]))
        parts += [_p("cube", "body", [48.0, 0.0, 10.5], [10.0, 18.0, 14.0]),
                  _p("cube", "window", [48.5, 0.0, 15.0], [9.6, 18.05, 1.2]),
                  _p("cube", "dark", [44.0, 0.0, 19.0], [3.0, 3.0, 4.0]),
                  _p("sphere", "nav_red", [50.0, 9.3, 17.0], [0.6] * 3),
                  _p("sphere", "nav_green", [50.0, -9.3, 17.0], [0.6] * 3),
                  _p("sphere", "lamp", [-59.5, 0.0, 6.0], [0.6] * 3),
                  _p("sphere", "lamp", [55.0, 0.0, 23.0], [0.6] * 3),
                  _p("sphere", "beacon", [44.0, 0.0, 21.4], [0.5] * 3)]
        return parts
    return [_p("cube", "body", [0.0, 0.0, 0.5], [2.0, 2.0, 1.0])]


AIRWATER_MODELS = {k: aw_model(k) for k in ("car", "drone", "police", "media", "aircraft",
                                            "shuttle", "boat", "taxi", "ferry", "ship")}


def _hover_parts(rec: dict, police: bool) -> list[dict]:
    """An AG18 hover car's own parts (its meshes, kind -1: painted) with nav lights and, a
    police flier's, a light bar on its roof."""
    dim = rec.get("dimensions") or {}
    L = float(dim.get("length") or 4.8)
    W = float(dim.get("width") or 2.0)
    H = float(dim.get("height") or 1.4)
    out = []
    for p in rec["parts"]:
        out.append({"mesh": f"{rec['folder']}/SM_{rec['car']}_{p['name']}", "kind": -1,
                    "at": [float(v) for v in p.get("pivot", [0.0, 0.0, 0.0])],
                    "size": [1.0, 1.0, 1.0],
                    "cull_m": 300.0 if p.get("kind") == "glass" else 0.0})
    # (an underglow in the route's color under its body: a flier read by night from afar)
    out.append(_p("cube", "accent", [0.0, 0.0, 0.06], [L * 0.7, W * 0.55, 0.05]))
    out += nav_lights(L, W, H)
    if police:
        out += [_p("cube", "police_red", [-0.2, 0.28, H + 0.06], [0.35, 0.45, 0.12]),
                _p("cube", "police_blue", [-0.2, -0.28, H + 0.06], [0.35, 0.45, 0.12]),
                _p("cube", "lamp", [L / 2.0 - 0.2, 0.0, 0.15], [0.3, 0.4, 0.1])]
    return out


def pack_airwater(plan: dict, pdir: Path, veh: dict | None) -> dict:
    """LG7: the city's air and water routes, flat: per route its kind (an index of
    `presets.AW_KINDS`), model (an index of the models packed), color (linear), cycle and its
    samples' step, vehicles per band, points (x, y, z citygen m, absolute; heading, degrees
    counterclockwise from east), samples (m along the path), dwells (arrive, depart, what), the
    paints of its vehicles (9 floats each: AG18's hover cars'); per model its parts (9 floats:
    mesh, kind (-1 painted, else `AW_PART_KINDS`), middle (3), size (3), cull m); the meshes
    and how many custom floats each one's instances carry (9 painted, 6 the stand-ins')."""
    from lifegen.presets import AW_KINDS
    aw = plan.get("airwater") or {}
    f = pdir / (aw.get("file") or "airwater.json")
    if not f.is_file():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    routes = data.get("routes") or []
    if not routes:
        return {}
    have = (veh or {}).get("cars") or {}
    tr = plan.get("traffic") or {}
    tmodels = tr.get("models") or []
    models, model_of = [], {}
    meshes = list(AW_MESHES.values())
    mesh_floats = [6] * len(meshes)
    parts_flat, part_starts = [], [0]

    def mesh_index(path: str, painted: bool) -> int:
        if path not in meshes:
            meshes.append(path)
            mesh_floats.append(9 if painted else 6)
        return meshes.index(path)

    def model_index(name: str, kind: str) -> int:
        key = name if name in HOVER and name in have else kind
        key = f"{key}@police" if kind == "police" else key
        if key in model_of:
            return model_of[key]
        if name in HOVER and name in have:
            parts = _hover_parts(have[name], kind == "police")
        else:
            parts = AIRWATER_MODELS.get(kind) or AIRWATER_MODELS["car"]
            if kind == "police":
                parts = parts + [_p("cube", "police_red", [-0.2, 0.28, 1.56], [0.35, 0.45, 0.12]),
                                 _p("cube", "police_blue", [-0.2, -0.28, 1.56], [0.35, 0.45, 0.12])]
        for p in parts:
            if p["kind"] == -1:
                mi = mesh_index(p["mesh"], True)
                kd = -1.0
            else:
                mi = mesh_index(AW_MESHES[p["mesh"]], False)
                kd = float(AW_PART_KINDS.index(p["kind"]))
            parts_flat.extend([float(mi), kd] + [round(v, 4) for v in p["at"]] +
                              [round(v, 4) for v in p["size"]] + [float(p["cull_m"])])
        part_starts.append(len(parts_flat) // 9)
        model_of[key] = len(models)
        models.append(key)
        return model_of[key]
    out = {k: [] for k in ("aw_route_kind", "aw_route_model", "aw_route_color", "aw_route_cycle",
                           "aw_route_dt", "aw_route_count", "aw_point_starts", "aw_points",
                           "aw_sample_starts", "aw_samples", "aw_event_starts", "aw_events",
                           "aw_paint_starts", "aw_paints")}
    for key in ("aw_point_starts", "aw_sample_starts", "aw_event_starts", "aw_paint_starts"):
        out[key].append(0)
    ids = []
    pol = [float(v) for v in (tr.get("police_paint") or [])]
    for r in routes:
        ids.append(r["id"])
        out["aw_route_kind"].append(AW_KINDS.index(r["kind"]))
        out["aw_route_model"].append(model_index(r.get("model") or r["kind"], r["kind"]))
        out["aw_route_color"] += _lin(r.get("color") or "#ffffff")
        out["aw_route_cycle"].append(float(r["cycle_s"]))
        out["aw_route_dt"].append(float(r["sample_s"]))
        out["aw_route_count"] += [int(v) for v in r["counts"]]
        for p in r["points"]:
            out["aw_points"] += [float(v) for v in p]
        out["aw_point_starts"].append(len(out["aw_points"]) // 4)
        out["aw_samples"] += [float(v) for v in r["samples"]]
        out["aw_sample_starts"].append(len(out["aw_samples"]))
        for e in r["events"]:
            out["aw_events"] += [float(e[0]), float(e[1]), float(e[2])]
        out["aw_event_starts"].append(len(out["aw_events"]) // 3)
        # (each vehicle's paint: a police flier the livery; a hover car one of its district's
        # paints for its model, by its id, as LG5's traffic paints a car)
        m = r.get("model")
        if m in HOVER and m in have:
            rows = ((tr.get("paints") or {}).get(r.get("district_id") or "") or [])
            row = rows[tmodels.index(m)] if m in tmodels and tmodels.index(m) < len(rows) else []
            kp = len(row) // 9
            for k in range(max(r["counts"])):
                if r["kind"] == "police" and len(pol) >= 9:
                    out["aw_paints"] += pol[:9]
                elif kp:
                    q = int(hashlib.blake2b(f"{r['id']}|{k}".encode(), digest_size=4)
                            .hexdigest(), 16) % kp
                    out["aw_paints"] += [float(v) for v in row[9 * q:9 * q + 9]]
                else:
                    out["aw_paints"] += AW_PAINT
        out["aw_paint_starts"].append(len(out["aw_paints"]) // 9)
    out.update({"aw_route_ids": ids, "aw_models": models, "aw_model_part_starts": part_starts,
                "aw_parts": parts_flat, "aw_meshes": meshes, "aw_mesh_floats": mesh_floats,
                "aw_kinds": list(AW_KINDS),
                "airwater": {"routes": len(ids), "hour": int(aw.get("hour", 23))}})
    return out


def life_data(pdir: Path, graphs: dict | None, veh: dict | None,
              lib: dict | None = None) -> tuple[dict | None, str]:
    plan = json.loads((pdir / "life_plan.json").read_text(encoding="utf-8"))
    bad = [k for k, c in (plan.get("checks") or {}).items() if not c.get("ok")]
    if bad:
        return None, f"the plan's checks failed: {', '.join(bad)}"
    spike = plan.get("spike")
    if not spike:
        return None, "the plan has no spike"
    if not graphs:
        return None, "no graphs (graphs.json) to build lanes from"
    arch = next((d["archetype"] for d in plan["districts"] if d["id"] == spike["district_id"]),
                None)
    traffic = None
    if plan.get("crowd"):
        # (LG3: every walkway of the city, the crowd's pool; LG5: every lane of the city, the
        # traffic's pool, else the spike's drive lanes and cars)
        lanes = pack_crowd(plan, pdir, graphs)
        if plan.get("traffic"):
            traffic = pack_traffic(plan, pdir, graphs, veh)
            tcars = {"parts": traffic.pop("parts"), "models": traffic.pop("models")}
            lanes.update(traffic)
        else:
            lanes.update(pack_drive(graphs, spike))
        # (LG6: every transit line's timetable, its stops and trains; a plan before it none)
        tpack = pack_transit(plan, pdir, graphs)
        if tpack:
            # (the platforms' walkways as wide as their decks, people keeping off their
            # trains; the other walkways as they were)
            w = tpack.pop("walk_transit_width")
            lanes["walk_widths"] = [round(max(float(a), float(b)), 3)
                                    for a, b in zip(lanes["walk_widths"], w)]
            lanes.update(tpack)
        # (LG7: every route of what flies and floats; a plan before it none)
        apack = pack_airwater(plan, pdir, veh)
        if apack:
            lanes.update(apack)
        crowd = plan["crowd"]
        spike = {**spike, "people": int(crowd["pool"]), "library": crowd.get("library") or {},
                 "persons": {}}
        lib_spike = {"library": crowd.get("library") or {}}
    else:
        lanes = pack_lanes(graphs, spike)
        lib_spike = spike
    if traffic is not None:
        # (LG5: no spike cars; the pool's slots carry the traffic's models)
        cs = {"car_models": [], "car_paints": [], **tcars}
        ncars = int(traffic["traffic"]["pool"]) if cs["models"] else 0
    else:
        cs = cars(spike, arch, veh)
        ncars = len(cs["car_models"])
    ctl = {"city": plan["city"], "plan_hash": plan["plan_hash"],
           "district": spike["district_id"], "hour": spike["hour"],
           "people": int(spike["people"]), "cars": ncars,
           "center": spike["center"], "radius_m": spike["radius_m"],
           "walk_speed": spike["walk_speed"], "drive_speed": spike["drive_speed"],
           "car_gap_m": spike["car_gap_m"],
           "drive_vary": (spike.get("drive") or {}).get("vary") or [0.9, 1.08],
           "palette": [v for c in spike["palette"] for v in _lin(c)],
           "paint_floats": PAINT_FLOATS, **cs, **persons(spike), **lanes,
           **people_library(lib, lib_spike)}
    return {"version": PACK_VERSION, "controller": ctl}, ""


def write_life(build: str | Path, given: str | Path | None = None,
               graphs: dict | None = None, veh: dict | None = None,
               lib: dict | None = None) -> dict | None:
    """The manifest's `life` (and BUILD/unreal/life.json, written only when its bytes
    change); None without a plan, {"skipped": why} for a plan not delivered. `lib` (LG1): the
    project's people library manifest (`unreal_people`), whose people replace the stand-ins."""
    pdir = plan_dir(build, given)
    if pdir is None:
        if given:
            raise FileNotFoundError(f"{given}: no life_plan.json (run lifegen plan)")
        return None
    data, why = life_data(pdir, graphs, veh, lib)
    if data is None:
        return {"skipped": why, "plan": str(pdir)}
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n"
    dest = Path(build) / "unreal" / DATA
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file() or dest.read_text(encoding="utf-8") != text:
        dest.write_text(text, encoding="utf-8", newline="\n")
    c = data["controller"]
    return {"file": f"unreal/{DATA}", "plan": str(pdir), "plan_hash": c["plan_hash"],
            "key": CONTROLLER_KEY, "hash": _sha16([PACK_VERSION, c]),
            "district": c["district"], "people": c["people"], "cars": c["cars"],
            "walk_lanes": len(c["walk_starts"]) - 1, "drive_lanes": len(c["drive_starts"]) - 1,
            "models": c["models"],
            **({"crowd": {"walkways": len(c["walk_starts"]) - 1, "doors": len(c["door_lanes"]),
                          "signals": len(c["signal_windows"]) // 8,
                          "hour": c["crowd"]["hour"], "pool": c["crowd"]["pool"]}}
               if c.get("crowd") else {}),
            **({"traffic": {"lanes": len(c["drive_starts"]) - 1,
                            "main": sum(c["drive_main"]),
                            "signal_lanes": sum(1 for v in c["drive_signal"] if v >= 0),
                            "conflicts": len(c["drive_conflicts"]) // 2,
                            "hour": c["traffic"]["hour"], "pool": c["traffic"]["pool"],
                            "live_m": c["traffic"]["live_m"], "models": len(c["models"])}}
               if c.get("traffic") else {}),
            **({"places": {"slots": len(c["slot_kinds"]), "turfs": len(c["turf_faction"]),
                           "roles": [c["person_role"].count(k) for k in range(3)],
                           "patrol_cars": sum(c.get("traffic_police") or []),
                           "clips": bool(c.get("sit_clips"))}}
               if c.get("slot_kinds") is not None else {}),
            **({"transit": {"lines": len(c["transit_line_mode"]), "modes": c["transit_modes"],
                            "stops": len(c["transit_stop_lane"]),
                            "trains": [sum(c["transit_line_trains"][5 * k + b]
                                           for k in range(len(c["transit_line_mode"])))
                                       for b in range(5)]}}
               if c.get("transit_line_mode") else {}),
            **({"airwater": {"routes": len(c["aw_route_kind"]), "models": c["aw_models"],
                             "meshes": len(c["aw_meshes"]),
                             "vehicles": [sum(c["aw_route_count"][5 * k + b]
                                              for k in range(len(c["aw_route_kind"])))
                                          for b in range(5)]}}
               if c.get("aw_route_kind") else {}),
            "library":({"characters": len(c["mid_meshes"]), "hash": c.get("library_hash"),
                        "tiers": c.get("tiers")} if c.get("mid_meshes") else
                       {"stand_ins": True, "why": c.get("people_skipped") or
                        "no people library in the project (--people)"})}


def actor_hashes(life: dict | None) -> dict[str, str]:
    """The controller's key and hash (`unreal.actor_hashes`)."""
    if not life or not life.get("key"):
        return {}
    return {life["key"]: life["hash"]}
