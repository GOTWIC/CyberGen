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

The runtime builds ZoneGraph lanes from these at BeginPlay (no hand-drawn shapes). A plan
whose checks failed is named and left out (`skipped`); a build without a plan gets no
section, and its manifest is what it was.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

PACK_VERSION = 2            # 2 (cars_steam): smoothed drive lanes, their speeds
DATA = "life.json"
CONTROLLER_KEY = "life"
MARGIN_M = 60.0             # lanes this far past the live radius come along (links out of it)
PAINT_FLOATS = 9


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
    drive = [e for e in _elements(graphs["lanes"])
             if len(e[2]) >= 2 and _near(e[2], cx, cy, reach)]
    dmap = {e[0]: k for k, e in enumerate(drive)}
    out.update({"drive_points": [], "drive_starts": [0], "drive_widths": [],
                "drive_links": [], "drive_link_starts": [0], "drive_startable": [],
                "drive_vmax": [], "drive_cruise": []})
    refs = graphs["lanes"].get("refs") or [""] * graphs["lanes"]["count"]
    succ = [[dmap[j] for j in e[4] if j in dmap] for e in drive]
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
    speeds = spike.get("drive_speeds") or {}
    dv = spike.get("drive") or {}
    default = speeds.get(dv.get("default", "street"), 9.5) if speeds else None
    classes = spike.get("road_classes") or {}
    base = []
    for k, e in enumerate(drive):
        if default is None:
            base.append(0.0)                  # (a plan before cars_steam: no speeds)
        elif e[1] == "lane":
            base.append(float(speeds.get(classes.get(refs[e[0]], ""), default)))
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
    return {"person_char": [int(v) for v in ps["character"]],
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
    want = (spike.get("library") or {}).get("characters")
    if want and want != len(chars):
        return {"people_skipped": f"the plan draws from {want} characters, the project's "
                                  f"library has {len(chars)}"}
    near, starts, mid, mid_frames, cards = [], [0], [], [], []
    for c in chars:
        near += c["near"]["meshes"]
        starts.append(len(near))
        mid.append(c["mid"]["mesh"])
        mid_frames += [float(c["mid"]["start"]), float(c["mid"]["end"]),
                       float(c["mid"]["fps"]), float(c["mid"].get("cycle_s", 1.0))]
        cards.append(c["far"]["material"])
    walks = [lib["clips"][w] for w in spike.get("library", {}).get("walks", lib["walks"])]
    tiers = {**(lib.get("tiers") or {}), **((spike.get("library") or {}).get("tiers") or {})}
    return {"near_meshes": near, "near_mesh_starts": starts,
            "near_follow": [c["near"].get("follow", []) for c in chars],
            "walk_clips": [w["anim"] for w in walks],
            "walk_clip_speeds": [float(w["speed"]) for w in walks],
            "idle_clips": [lib["clips"][k]["anim"] for k in lib.get("idles", [])],
            "mid_meshes": mid, "mid_frames": mid_frames,
            "card_mesh": lib["far"]["card"], "card_materials": cards,
            "card_size": [float(v) for v in lib["far"].get("size", [1.0, 2.0])],
            "tiers": tiers, "library_hash": lib.get("hash")}


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
    lanes = pack_lanes(graphs, spike)
    cs = cars(spike, arch, veh)
    ctl = {"city": plan["city"], "plan_hash": plan["plan_hash"],
           "district": spike["district_id"], "hour": spike["hour"],
           "people": int(spike["people"]), "cars": len(cs["car_models"]),
           "center": spike["center"], "radius_m": spike["radius_m"],
           "walk_speed": spike["walk_speed"], "drive_speed": spike["drive_speed"],
           "car_gap_m": spike["car_gap_m"],
           "drive_vary": (spike.get("drive") or {}).get("vary") or [0.9, 1.08],
           "palette": [v for c in spike["palette"] for v in _lin(c)],
           "paint_floats": PAINT_FLOATS, **lanes, **cs, **persons(spike),
           **people_library(lib, spike)}
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
            "library": ({"characters": len(c["mid_meshes"]), "hash": c.get("library_hash"),
                        "tiers": c.get("tiers")} if c.get("mid_meshes") else
                       {"stand_ins": True, "why": c.get("people_skipped") or
                        "no people library in the project (--people)"})}


def actor_hashes(life: dict | None) -> dict[str, str]:
    """The controller's key and hash (`unreal.actor_hashes`)."""
    if not life or not life.get("key"):
        return {}
    return {life["key"]: life["hash"]}
