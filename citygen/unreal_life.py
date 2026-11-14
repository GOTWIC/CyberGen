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

PACK_VERSION = 1
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
                "drive_links": [], "drive_link_starts": [0], "drive_startable": []})
    for e in drive:
        for p in e[2]:
            out["drive_points"] += [round(float(v), 3) for v in p]
        out["drive_starts"].append(len(out["drive_points"]) // 3)
        out["drive_widths"].append(round(float(e[3]), 3))
        out["drive_links"] += [dmap[j] for j in e[4] if j in dmap]
        out["drive_link_starts"].append(len(out["drive_links"]))
        out["drive_startable"].append(1 if e[1] == "lane" else 0)
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


def life_data(pdir: Path, graphs: dict | None, veh: dict | None) -> tuple[dict | None, str]:
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
           "palette": [v for c in spike["palette"] for v in _lin(c)],
           "paint_floats": PAINT_FLOATS, **lanes, **cs}
    return {"version": PACK_VERSION, "controller": ctl}, ""


def write_life(build: str | Path, given: str | Path | None = None,
               graphs: dict | None = None, veh: dict | None = None) -> dict | None:
    """The manifest's `life` (and BUILD/unreal/life.json, written only when its bytes
    change); None without a plan, {"skipped": why} for a plan not delivered."""
    pdir = plan_dir(build, given)
    if pdir is None:
        if given:
            raise FileNotFoundError(f"{given}: no life_plan.json (run lifegen plan)")
        return None
    data, why = life_data(pdir, graphs, veh)
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
            "models": c["models"]}


def actor_hashes(life: dict | None) -> dict[str, str]:
    """The controller's key and hash (`unreal.actor_hashes`)."""
    if not life or not life.get("key"):
        return {}
    return {life["key"]: life["hash"]}
