"""Play features of the Unreal export (docs/unreal_export.md, "Play features"), the venv side.

`citygen unreal` writes, beside the manifest in BUILD_DIR/unreal/:

- `map.png`: the city from above, north up, in a dark map style (sea, land, parks, water,
  streets by class, sidewalks, bridges, transit tubes, buildings in their district's hue,
  landmarks brighter), drawn from blockout_plan.json at most MAP_PX pixels on its long side
  over the plan's bounds; drawn again only when the plan or MAP_VERSION changes;
- `play.json`: the map's bounds and size, the walkway graph's points thinned to one per
  WALK_GRID_M cell (where a walking player is teleported to; absolute heights on a terrain
  city), the street and wall lights' lamp heads (each instance's transform applied to its
  prototype's `prop_light` parts) and a label point per district;

and the manifest's `play` (files, hashes, counts). It installs the CityGenPlay plugin
(citygen/ue/CityGenPlay, C++) into the project and builds it with UnrealBuildTool for the
editor; when no compiler can build it, the city imports without the play features (a plugin
never built is taken out of the project again, one built before stays as it was built).
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

MAP_VERSION = "1"
MAP_PX = 4096                 # the map image's long side
WALK_GRID_M = 3.0             # one walkway point per cell of this size (and per level)
WALK_STEP_M = 5.0             # walkway lines sampled this often
# walkway kinds no one lands on (off the ground or the decks: a skybridge 40 m up)
WALK_SKIP = ("stairs", "elevator", "skybridge", "underpass", "elevated")
LAMPS = {"street_light": 0, "wall_light": 1}       # prototype kind -> lamp kind
PLUGIN = "CityGenPlay"
PLUGIN_DIR = Path(__file__).parent / "ue" / PLUGIN
BUILT_STAMP = ".citygen_built"                     # the source hash the binaries were built from

# the map's palette (sRGB): a night map, so the player arrow and labels stand out
SEA = "#0a1626"
STYLE = {   # category -> (fill, draw order); tunnels run under the ground and are left out
    "sea": (SEA, 0), "ground": ("#1a212d", 1),
    "water": ("#103152", 2), "site_pond": ("#103152", 2),
    "open_park": ("#1c3a29", 3), "open_green": ("#1c3a29", 3), "open_pocket_park": ("#1c3a29", 3),
    "open_marsh": ("#1f3529", 3), "lawn": ("#1d3a29", 3), "site_lawn": ("#1d3a29", 3),
    "open_plaza": ("#2a3242", 3), "open_market": ("#2e3443", 3), "open_promenade": ("#2a3242", 3),
    "open_courtyard": ("#262d3b", 3), "site_plaza": ("#2a3242", 3),
    "hedge": ("#22412c", 4), "quay": ("#2b3342", 4), "embankment": ("#252c39", 4),
    "sidewalk": ("#2c3443", 5),
    "road_pedestrian": ("#3a4253", 6), "road_alley": ("#454d5f", 6),
    "road_service": ("#454d5f", 6), "road_street": ("#566077", 6),
    "road_avenue": ("#7b87a1", 6), "road_highway": ("#c99441", 6), "junction": ("#566077", 6),
    "crosswalk": ("#6b748a", 7), "bridge": ("#69738a", 7), "site_rail_track": ("#7d6e60", 7),
    "elevated": ("#c99441", 8), "structure_deck": ("#4a5368", 8),
    "site_container_stack": ("#4a4f63", 9), "site_gantry_crane": ("#8a6b3a", 9),
    "green_roof": ("#24442f", 11), "structure_tube": ("#3ab0c8", 12),
}
BUILDING = "#353f52"          # buildings, tinted a little toward their district's color
BUILDING_ORDER = 10
LANDMARK = "#7d8db0"
BUILDING_TINT = 0.28


# --- the map ----------------------------------------------------------------------------------

def _rgb(c: str) -> tuple[float, float, float]:
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def _mix(a: str, b: str, t: float) -> tuple[float, float, float]:
    return tuple(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b)))


def _ring(pts) -> list[tuple[float, float]]:
    return [(float(p[0]), float(p[1])) for p in pts]


def _signed(r) -> float:
    return sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1]
               for i in range(len(r))) / 2.0


def _shape(part: dict) -> list[list[tuple[float, float]]] | None:
    """A plan part's outline from above: its rings (the exterior first, holes after, wound
    the other way so a nonzero fill leaves them open), or None (instances, beams)."""
    k = part["k"]
    if k in ("flat", "prism"):
        ext = _ring(part["r"])
        if len(ext) < 3:
            return None
        rings = [ext] + [_ring(h) for h in part.get("h") or [] if len(h) >= 3]
        s0 = _signed(ext)
        return [r if (i == 0 or _signed(r) * s0 < 0) else r[::-1] for i, r in enumerate(rings)]
    if k == "ribbon":
        left, right = _ring(part["l"]), _ring(part["rr"])
        return [left + right[::-1]] if len(left) >= 2 and len(right) >= 2 else None
    if k == "box":
        cx, cy = part["c"][0], part["c"][1]
        hx, hy = part["d"][0] / 2.0, part["d"][1] / 2.0
        a = math.radians(part.get("yaw", 0.0))
        c, s = math.cos(a), math.sin(a)
        return [[(cx + x * c - y * s, cy + x * s + y * c)
                 for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]]
    if k == "beam":
        (ax, ay), (bx, by) = part["a"][:2], part["b"][:2]
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            return None
        nx, ny = -(by - ay) / L * part["w"] / 2.0, (bx - ax) / L * part["w"] / 2.0
        return [[(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)]]
    return None


def map_size(bounds: list[float], px: int = MAP_PX) -> tuple[int, int]:
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    return (px, max(1, round(px * h / w))) if w >= h else (max(1, round(px * w / h)), px)


def render_map(plan: dict, path: Path, px: int = MAP_PX) -> tuple[int, int]:
    """The city from above as a PNG over the plan's bounds (north up); its size."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PathCollection
    from matplotlib.path import Path as MPath

    b = plan["bounds"]
    w, h = map_size(b, px)
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100, facecolor=SEA)
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(b[0], b[2])
    ax.set_ylim(b[1], b[3])
    ax.set_axis_off()
    ax.set_facecolor(SEA)
    mats = plan.get("materials", {})
    layers: dict[tuple[int, tuple], list] = {}

    def add(order, color, rings):
        verts, codes = [], []
        for r in rings:
            verts += r + [r[0]]
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(r) - 1) + [MPath.CLOSEPOLY]
        layers.setdefault((order, color), []).append(MPath(verts, codes))

    for o in plan["objects"]:
        cat = o["category"]
        for part in o["parts"]:
            rings = _shape(part)
            if rings is None:
                continue
            if cat in ("building", "skybridge"):
                hue = mats.get(part.get("m", ""), BUILDING)
                add(BUILDING_ORDER, _mix(BUILDING, hue if hue.startswith("#") else BUILDING,
                                         BUILDING_TINT), rings)
            elif cat == "landmark":
                add(BUILDING_ORDER + 1, _rgb(LANDMARK), rings)
            elif cat in STYLE:
                color, order = STYLE[cat]
                add(order, _rgb(color), rings)
    for (order, color), paths in sorted(layers.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        ax.add_collection(PathCollection(paths, facecolors=[color], edgecolors="none",
                                         linewidths=0.0, antialiaseds=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=100, facecolor=SEA, metadata={"Software": None})
    plt.close(fig)
    return w, h


# --- the play data ----------------------------------------------------------------------------

def walk_points(graphs: dict | None, grid: float = WALK_GRID_M,
                step: float = WALK_STEP_M) -> list[float]:
    """Points along the walkway graph's lines (every `step` m; not its stairs and lifts),
    one per `grid` cell and level (flat x, y, z)."""
    if not graphs or "walkways" not in graphs:
        return []
    g = graphs["walkways"]
    pts, start = g["points"], g["point_start"]
    seen, out = set(), []

    def keep(x, y, z):
        key = (math.floor(x / grid), math.floor(y / grid), round(z / 2.5))
        if key not in seen:
            seen.add(key)
            out.extend((round(x, 2), round(y, 2), round(z, 2)))

    for i in range(len(start) - 1):
        if g["kinds"][i] in WALK_SKIP:
            continue
        line = [tuple(pts[3 * k:3 * k + 3]) for k in range(start[i], start[i + 1])]
        for a, b in zip(line, line[1:]):
            n = max(1, math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
            for j in range(n):
                t = j / n
                keep(*(a[c] + (b[c] - a[c]) * t for c in range(3)))
        if line:
            keep(*line[-1])
    return out


def lamp_offsets(plan: dict) -> dict[str, list[tuple[float, float, float]]]:
    """Per lamp prototype kind, its lamp heads in its own frame (the `prop_light` parts)."""
    out = {}
    for kind in LAMPS:
        parts = plan.get("prototypes", {}).get(kind, [])
        heads = [tuple(p["c"]) for p in parts if p.get("m") == "prop_light" and "c" in p]
        if heads:
            out[kind] = heads
    return out


def lamp_points(plan: dict, instances: list[dict]) -> tuple[list[float], list[int]]:
    """Every street and wall light's lamp heads in the city (flat x, y, z) and their kinds:
    an instance's transform [x, y, z, yaw, sx, sy, sz] (yaw counterclockwise from east)
    applied to its prototype's heads."""
    heads = lamp_offsets(plan)
    pts, kinds = [], []
    for inst in sorted(instances, key=lambda i: i["key"]):
        kind = inst.get("proto")
        if kind not in heads:
            continue
        for x, y, z, yaw, sx, sy, sz in inst["xforms"]:
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            for ox, oy, oz in heads[kind]:
                px, py = ox * sx, oy * sy
                pts += [round(x + px * c - py * s, 2), round(y + px * s + py * c, 2),
                        round(z + oz * sz, 2)]
                kinds.append(LAMPS[kind])
    return pts, kinds


def _districts(build: Path) -> list[tuple[str, list[dict]]]:
    """(name, polygons) per district: the model's (city_model.json beside the plan, as
    `citygen build --blockout` leaves it), else the gameplay layer's zones of each district
    joined (gameplay.json, which every blockout output has; the district named after its
    police precinct)."""
    model = build / "city_model.json"
    if model.is_file():
        data = json.loads(model.read_text(encoding="utf-8"))
        return [(d["name"], [d["polygon"]]) for d in data.get("districts", [])
                if d.get("polygon")]
    gp = build / "gameplay.json"
    if not gp.is_file():
        return []
    zones = json.loads(gp.read_text(encoding="utf-8")).get("zones", [])
    names, polys = {}, {}
    for z in zones:
        did = z.get("district_id")
        if not did:
            continue
        polys.setdefault(did, []).extend(z.get("polygons") or [])
        if z.get("kind") == "police" and z.get("name"):
            names[did] = z["name"].removesuffix(" Precinct")
    return [(names.get(d, d), polys[d]) for d in sorted(polys)]


def district_labels(build: Path) -> list[dict]:
    """A label point inside each district, by name."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    out = []
    for name, polys in _districts(build):
        parts = []
        for poly in polys:
            ext = poly.get("exterior") or []
            if len(ext) >= 3:
                g = Polygon(ext, [h for h in poly.get("holes") or [] if len(h) >= 3])
                parts.append(g if g.is_valid else g.buffer(0))
        g = unary_union(parts) if parts else None
        if g is None or g.is_empty:
            continue
        # the largest piece's inside point (a district of islands is labeled on its largest)
        g = max(getattr(g, "geoms", [g]), key=lambda x: x.area)
        p = g.representative_point()
        out.append({"name": name, "x": round(p.x, 1), "y": round(p.y, 1)})
    return sorted(out, key=lambda r: r["name"])


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_play(build: Path, plan_sha: str, plan: dict, instances: list[dict],
               graphs: dict | None) -> dict:
    """BUILD_DIR/unreal/map.png and play.json; the manifest's `play`."""
    out = build / "unreal"
    out.mkdir(parents=True, exist_ok=True)
    png, data_path = out / "map.png", out / "play.json"
    source = {"plan_sha256": plan_sha, "map_version": MAP_VERSION, "px": MAP_PX}
    old = json.loads(data_path.read_text(encoding="utf-8")) if data_path.is_file() else {}
    if (old.get("map", {}).get("source") == source and png.is_file()
            and _sha(png.read_bytes()) == old["map"].get("sha256")):
        size = tuple(old["map"]["size"])
    else:
        size = render_map(plan, png)
    walk = walk_points(graphs)
    lamps, kinds = lamp_points(plan, instances)
    data = {"version": 1, "city": plan["city"],
            "map": {"file": "unreal/map.png", "bounds": plan["bounds"], "size": list(size),
                    "sha256": _sha(png.read_bytes()), "source": source},
            "walk": walk, "lamps": lamps, "lamp_kinds": kinds,
            "labels": district_labels(build)}
    text = json.dumps(data, separators=(",", ":")) + "\n"
    if not data_path.is_file() or data_path.read_text(encoding="utf-8") != text:
        data_path.write_text(text, encoding="utf-8", newline="\n")
    return {"data": "unreal/play.json", "map": "unreal/map.png", "map_bounds": plan["bounds"],
            "map_size": list(size), "map_sha256": data["map"]["sha256"],
            "hash": _sha(text.encode("utf-8"))[:16], "walk_points": len(walk) // 3,
            "lamps": len(kinds), "labels": len(data["labels"])}


# --- the plugin -------------------------------------------------------------------------------

def plugin_files() -> list[Path]:
    return sorted(p for p in PLUGIN_DIR.rglob("*") if p.is_file()
                  and not any(x in p.parts for x in ("Binaries", "Intermediate")))


def plugin_hash() -> str:
    h = hashlib.sha256()
    for p in plugin_files():
        h.update(p.relative_to(PLUGIN_DIR).as_posix().encode("utf-8") + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def install_plugin(uproject: Path) -> dict:
    """The plugin's source in PROJECT/Plugins/CityGenPlay (files written only where they
    differ, files it no longer has removed) and enabled in the .uproject."""
    dest = uproject.parent / "Plugins" / PLUGIN
    wrote = removed = 0
    want = {p.relative_to(PLUGIN_DIR).as_posix(): p for p in plugin_files()}
    for rel, src in want.items():
        d = dest / rel
        data = src.read_bytes()
        if not d.is_file() or d.read_bytes() != data:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes(data)
            wrote += 1
    if (dest / "Source").is_dir():
        for p in (dest / "Source").rglob("*"):
            if p.is_file() and p.relative_to(dest).as_posix() not in want:
                p.unlink()
                removed += 1
    _enable(uproject, True)
    return {"dir": str(dest), "wrote": wrote, "removed": removed}


def _enable(uproject: Path, on: bool) -> bool:
    data = json.loads(uproject.read_text(encoding="utf-8-sig"))
    plugins = data.setdefault("Plugins", [])
    have = [p for p in plugins if p.get("Name") == PLUGIN]
    if on and have and all(p.get("Enabled") for p in have):
        return False
    if not on and not have:
        return False
    data["Plugins"] = [p for p in plugins if p.get("Name") != PLUGIN]
    if on:
        data["Plugins"].append({"Name": PLUGIN, "Enabled": True})
    uproject.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8", newline="\n")
    return True


def remove_plugin(uproject: Path) -> None:
    """The plugin out of the project (its folder and its .uproject entry)."""
    shutil.rmtree(uproject.parent / "Plugins" / PLUGIN, ignore_errors=True)
    _enable(uproject, False)


def build_command(root: Path, uproject: Path) -> list[str]:
    """UnrealBuildTool's command that builds the project's editor modules (the plugin's).
    `-NoHotReloadFromIDE`: an editor open on another project with Live Coding on would
    otherwise block every editor build of this engine (UnrealBuildTool guards the engine's
    editor executable); this project is closed while it imports, so nothing live is patched."""
    bat = root / "Engine" / "Build" / "BatchFiles"
    flags = [f"-Project={uproject}", "-WaitMutex", "-NoHotReload", "-NoHotReloadFromIDE"]
    if sys.platform == "win32":
        return [str(bat / "Build.bat"), "UnrealEditor", "Win64", "Development", *flags]
    plat, script = ("Mac", bat / "Mac" / "Build.sh") if sys.platform == "darwin" else \
        ("Linux", bat / "Linux" / "Build.sh")
    return [str(script), "UnrealEditor", plat, "Development", *flags]


def build_plugin(root: Path, uproject: Path, log: Path, timeout: float = 3600.0) -> dict:
    """Install the plugin and build it (skipped when its binaries were built from the same
    source); on failure it is taken out of the project. {ok, built, seconds, log, error}."""
    t = time.time()
    try:
        inst = install_plugin(uproject)
    except OSError as e:
        return {"ok": False, "built": False, "error": f"install: {e}", "seconds": 0.0}
    dest = Path(inst["dir"])
    stamp = dest / "Binaries" / BUILT_STAMP
    # (the engine too: binaries built against another engine would not load)
    want = f"{plugin_hash()} {Path(root).resolve().as_posix()}"
    if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == want:
        return {"ok": True, "built": False, "seconds": round(time.time() - t, 1),
                "hash": want, **inst}
    cmd = build_command(root, uproject)
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", encoding="utf-8", errors="replace") as f:
            proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
        code = proc.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        code, msg = -1, str(e)
    else:
        msg = ""
    if code != 0:
        text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else msg
        why = [ln for ln in text.splitlines() if "error" in ln.lower() or "banned" in ln.lower()]
        # a plugin built before stays as it was built (the level's play actor keeps its class,
        # so the import can delete it); one never built leaves the project
        kept = stamp.is_file()
        if not kept:
            remove_plugin(uproject)
        return {"ok": False, "built": False, "exit_code": code, "log": str(log),
                "kept_earlier_build": kept,
                "error": (why[0] if why else msg or "the build failed").strip()[:400],
                "seconds": round(time.time() - t, 1)}
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(want + "\n", encoding="utf-8", newline="\n")
    return {"ok": True, "built": True, "seconds": round(time.time() - t, 1), "log": str(log),
            "hash": want, **inst}
