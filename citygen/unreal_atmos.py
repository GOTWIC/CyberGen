"""atmosgen's side of the Unreal exporter (docs/unreal_export.md, "From AT0" and "From AT1").

- The runtime plugin `CityGenAtmos` (citygen/ue/CityGenAtmos) is installed and built with the
  play features' (`unreal_play.PLUGINS`, one UnrealBuildTool run).
- Its assets (`citygen/ue/atmos_assets.py`: MPC_CityGenAtmos, M_CgRain, M_CgWet under
  /Game/CityGen/Core/Atmos) are made in the project by a headless editor run, skipped when the
  project has this version of them (`make_assets`); `citygen unreal` runs it before an import
  with an atmos plan.
- AT1: a city's atmos plan (BUILD/atmos, or `--atmos DIR`) becomes layer 3 of the manifest
  (`write_atmos`, the manifest's `atmos`): the controller (key `atmos`, always loaded) with
  the plan's settings, and a data actor per 128 m cell of World Partition's main grid (key
  `atmos.lights.<tile>.<quarter>`), each holding its lights packed (`pack`), its hash the
  hash of its lights' records. The bulky arrays go to `BUILD/unreal/atmos.json` beside the
  manifest, which keeps the keys and hashes. A plan whose lux check did not pass (or an AT0
  plan, which has none) is not delivered (scope 8): the city imports without it.
- AT2: the packing's version 2 (`PACK_VERSION`): 19 floats a light (a blink's or a sweep's
  period, amount and phase after AT1's 16), the flags' bit 6 the high tier and bits 28-29 the
  animation; the controller's `max_high` and `high_range_m` (the plan's high tier); a plan
  whose faces check failed is not delivered either.
- AT3: the controller's sky and time (`sky_settings`: where the sun and the moon stand, the
  exposure, Night, sun, sky light and stars curves over the sun's elevation, the cloud deck,
  the named hours), and the deck's glow raster copied beside the manifest
  (`BUILD/unreal/atmos_sky_glow.png`, `GLOW`), which the import makes a texture the
  controller's sky reads; both in the controller's hash.
- AT4: the packing's version 3: a cell also holds its fog volumes (`pack_volume`) and steam
  and smoke emitters (`pack_emitter`), a cell made where any of the three lie; the
  controller's air (`air_settings`: the height and volumetric fog by the hour, each light
  kind's volumetric scattering, the live sets of volumes and plumes, the engine settings it
  runs with); a plan whose air check failed is not delivered.
- Visible lights (after AT4, Swagnik's walk of the packaged Delta, 2026-11-12): the
  controller's `sight_settings` (the plan's sight raster, `atmosgen/sight.py`, as runs of
  its cells, `sight_runs`, with its bounds in Unreal's frame, cell, steps and skips; the
  tiers' `sight_m` and `sight_max`), by which the runtime keeps live round a walker the
  lights the walker sees out to `sight_m`. The cells are always loaded (the importer's
  `atmos_cells`): their lights reach past World Partition's loading range (768 m).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

SCRIPT = Path(__file__).parent / "ue" / "atmos_assets.py"
STAMP = "citygen_atmos_assets.txt"          # in PROJECT/Saved
PLAN_DIR = "atmos"                          # BUILD/atmos: `atmosgen plan`'s default
DATA = "atmos.json"                         # BUILD/unreal/atmos.json
GLOW = "atmos_sky_glow.png"                 # BUILD/unreal/atmos_sky_glow.png (AT3)
CONTROLLER_KEY = "atmos"
CELL_M = 128.0                              # World Partition's main cells (unreal.MAIN_CELL_M)
PACK_VERSION = 3                            # 2 (AT2): the high tier, a blink or a sweep;
                                            # 3 (AT4): a cell's fog volumes and emitters
FLOATS = 19                                 # CityGenAtmosCell.h, CityGenAtmosPack
INTS = 2
VFLOATS = 14                                # AT4: a fog volume (CityGenAtmosPack::VolFloats)
VINTS = 1
EFLOATS = 9                                 # AT4: an emitter (CityGenAtmosPack::EmitFloats)
EINTS = 2
VOLUME_KINDS = ("mist", "smog", "haze", "tunnel_haze", "steam_bank")
EMITTER_KINDS = ("steam", "smoke", "exhaust", "cooking")
EMITTER_MOUNTS = ("manhole", "drain", "vent", "roof", "stall", "chimney", "stove")
SHAPES = {"spot": 0, "point": 1, "rect": 2}
ANIMS = {"blink": 1, "sweep": 2}
QUARTERS = {(0, 0): "sw", (1, 0): "se", (0, 1): "nw", (1, 1): "ne"}


def assets_version() -> str:
    m = re.search(r'^VERSION = "([^"]+)"', SCRIPT.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "0"


def make_assets(root: Path, uproject: Path, log: Path, force: bool = False) -> dict:
    """atmosgen's runtime assets in the project (a headless editor run); skipped when the
    project's stamp names this version and engine. {ok, made, error, ...}."""
    from .unreal import run_editor
    up = Path(uproject).resolve()
    stamp = up.parent / "Saved" / STAMP
    want = f"{assets_version()} {Path(root).resolve().as_posix()}"
    if not force and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == want:
        return {"ok": True, "made": False, "version": assets_version()}
    log.parent.mkdir(parents=True, exist_ok=True)
    job = {"result": str(log.with_name("atmos_assets_result.json"))}
    res = run_editor(Path(root), up, SCRIPT, job, log, timeout=1800.0)
    if res.get("ok"):
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(want + "\n", encoding="utf-8", newline="\n")
        res["made"] = True
    return res


# --- layer 3: the plan in the manifest ------------------------------------------------------

def _sha16(data) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def plan_dir(build: str | Path, given: str | Path | None = None) -> Path | None:
    """The atmos plan's folder: `given`, else BUILD/atmos; None when it holds no plan."""
    d = Path(given) if given else Path(build) / PLAN_DIR
    return d if (d / "atmos_plan.json").is_file() else None


def _kinds() -> list[str]:
    from typing import get_args

    from atmosgen.planmodel import LightKind
    return list(get_args(LightKind))


def _mounts() -> list[str]:
    from typing import get_args

    from atmosgen.planmodel import Mount
    return list(get_args(Mount))


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def pack(L: dict, schedules: list[str], kinds: list[str], mounts: list[str]):
    """A light's record as the cell actor holds it (CityGenAtmosCell.h): FLOATS floats in
    Unreal's frame (cm, X east, Y south, pitch and yaw in degrees, yaw turned: citygen's
    counterclockwise heading is Unreal's -yaw; AT2: its animation's period, amount and
    phase) and INTS ints (flags, seed)."""
    x, y, z = L["pos"]
    yaw, pitch = L["aim"]
    shape = SHAPES[L["shape"]]
    w, h = (L.get("size") or [0.0, 0.0])
    cd = float(L["cd"])
    inten = cd / max(0.01, w * h) if shape == 2 else cd
    inner, outer = (L.get("cone") or [0.0, 0.0]) if shape == 0 else \
        ([float(L.get("barn_deg") or 90.0), 0.0] if shape == 2 else [0.0, 0.0])
    col = L["color"]
    f = [_r(x * 100.0, 1), _r(-y * 100.0, 1), _r(z * 100.0, 1), _r(pitch), _r(-yaw),
         _r(w * 100.0, 1), _r(h * 100.0, 1), _r(float(L.get("source_m") or 0.0) * 100.0, 1),
         _r(inten, 2), _r(col[0], 4), _r(col[1], 4), _r(col[2], 4),
         _r(float(L["reach_m"]) * 100.0, 1), _r(inner), _r(outer), _r(L.get("flicker", 0.0))]
    an = L.get("anim") or {}
    f += [_r(an.get("period_s", 0.0)), _r(an.get("amount", 0.0)), _r(an.get("phase", 0.0))]
    flags = (shape | (4 if L.get("shadow") else 0) | (8 if L.get("tier") == "near" else 0)
             | (16 if L.get("on", True) else 0)
             | (32 if float(L.get("specular", 1.0)) < 0.5 else 0)
             | (64 if L.get("tier") == "high" else 0)
             | (schedules.index(L["schedule"]) << 8)
             | (kinds.index(L["kind"]) << 16) | (mounts.index(L.get("mount", "prop")) << 24)
             | (ANIMS.get(an.get("mode"), 0) << 28))
    seed = int(L["hash"][:8], 16)
    if seed >= 2 ** 31:
        seed -= 2 ** 32
    return f, [flags, seed]


def pack_volume(V: dict, schedules: list[str]):
    """AT4: a fog volume as the cell actor holds it (CityGenAtmosCell.h): VFLOATS floats in
    Unreal's frame (its middle in cm, its yaw, its half sizes in cm, density (1/m), floor
    share, phase g, albedo r, g, b, glow) and VINTS ints (flags: schedule index, kind index << 8)."""
    x, y, z = V["center"]
    ex, ey, ez = V["extent"]
    a = V["albedo"]
    f = [_r(x * 100.0, 1), _r(-y * 100.0, 1), _r(z * 100.0, 1), _r(-V.get("yaw_deg", 0.0)),
         _r(ex * 100.0, 1), _r(ey * 100.0, 1), _r(ez * 100.0, 1), _r(V["density"], 5),
         _r(V.get("floor", 0.0)), _r(V.get("phase_g", 0.4)), _r(a[0], 4), _r(a[1], 4),
         _r(a[2], 4), _r(V.get("glow", 0.0))]
    return f, [schedules.index(V["schedule"]) | (VOLUME_KINDS.index(V["kind"]) << 8)]


def pack_emitter(E: dict, schedules: list[str]):
    """AT4: a steam or smoke plume as the cell actor holds it: EFLOATS floats (its foot in
    cm, its width and rise in cm, its opacity, its albedo r, g, b) and EINTS ints (flags:
    schedule index, kind index << 8, mount index << 16; a seed from its record's hash)."""
    x, y, z = E["pos"]
    c = E.get("color") or [0.8, 0.8, 0.8]
    f = [_r(x * 100.0, 1), _r(-y * 100.0, 1), _r(z * 100.0, 1),
         _r(float(E.get("width_m", 1.0)) * 100.0, 1), _r(float(E.get("rise_m", 5.0)) * 100.0, 1),
         _r(E["rate"]), _r(c[0], 4), _r(c[1], 4), _r(c[2], 4)]
    flags = (schedules.index(E["schedule"]) | (EMITTER_KINDS.index(E["kind"]) << 8)
             | (EMITTER_MOUNTS.index(E.get("mount", "manhole")) << 16))
    seed = int(E["hash"][:8], 16)
    if seed >= 2 ** 31:
        seed -= 2 ** 32
    return f, [flags, seed]


def air_settings(plan: dict) -> dict:
    """AT4: the controller's air from the plan's `air` (an AT3 plan has none: {}): the height
    and volumetric fog of the look and weather (over the weather's own), the fog by the hour,
    each light kind's volumetric scattering (light shafts), the searchlight beams' fog gain,
    the live sets, the engine settings it runs with."""
    a = plan.get("air")
    if not a:
        return {}
    kinds = _kinds()
    return {"air": True, "fog_density": float(a["fog_density"]),
            "fog_falloff": float(a["fog_falloff"]), "fog_start_m": float(a["fog_start_m"]),
            "fog_albedo_linear": [float(v) for v in a["fog_albedo"]],
            "fog_volumetric": float(a["fog_extinction"]), "fog_view_m": float(a["fog_view_m"]),
            "fog_phase_g": float(a["phase_g"]),
            "fog_hours": [float(v) for v in a["fog_hours"]],
            "kind_scatter": [float(a["scatter"].get(k, 1.0)) for k in kinds],
            "beam_fog_gain": float(a["beam_fog_gain"]),
            "max_volumes": int(a["max_volumes"]), "volume_range_m": float(a["volume_range_m"]),
            "emitter_range_m": float(a["emitter_range_m"]),
            "emitter_kinds": list(EMITTER_KINDS),
            "puffs": [int(a["puffs"].get(k, 4)) for k in EMITTER_KINDS],
            "steam_gain": float(a.get("steam_gain", 10.0)),
            "volume_glow": float(a.get("volume_glow", 0.15)),
            "cvars": [f"{k}={v}" for k, v in sorted(a.get("cvars", {}).items())],
            "volumes": len(plan.get("volumes") or []),
            "emitters": len(plan.get("emitters") or [])}


def sight_settings(plan: dict, pdir: Path) -> dict:
    """Visible lights: the controller's sight from the plan's `sight` (a plan before it has
    none: {}): the raster as runs over its rows from the north edge ([count, red | green << 8
    | blue << 16] pairs, `atmosgen.sight.runs`), its bounds in Unreal's frame (cm: [min X,
    min Y, max X, max Y], Y south, so row 0 is min Y), its cell (m), size, steps (top,
    bottom, ground; m), skips (eye, light; m), and the tiers' range and size."""
    s = plan.get("sight")
    if not s or not (pdir / s["file"]).is_file():
        return {}
    import numpy as np
    from PIL import Image

    from atmosgen.sight import runs
    with Image.open(pdir / s["file"]) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = s["bounds"]
    t = plan.get("tiers") or {}
    return {"sight_m": float(t.get("sight_m", 1200.0)),
            "sight_max": int(t.get("sight_max", 512)),
            "sight_bounds": [_r(x0 * 100.0, 1), _r(-y1 * 100.0, 1), _r(x1 * 100.0, 1),
                             _r(-y0 * 100.0, 1)],
            "sight_cell_m": float(s["cell_m"]), "sight_px": [int(w), int(h)],
            "sight_steps": [float(s["top_step_m"]), float(s["bottom_step_m"]),
                            float(s["ground_step_m"])],
            "sight_skips": [float(s["skip_eye_m"]), float(s["skip_light_m"])],
            "sight_sha256": s["sha256"], "sight_runs": runs(rgb)}


def cell_of(x: float, y: float) -> tuple[int, int]:
    return int(math.floor(x / CELL_M)), int(math.floor(y / CELL_M))


def cell_name(ix: int, iy: int) -> tuple[str, str]:
    """A 128 m cell's tile (citygen's 256 m tile) and its name `<tile>.<quarter>`."""
    tx, ty = ix // 2, iy // 2
    tile = f"t{tx:+03d}{ty:+03d}"
    return tile, f"{tile}.{QUARTERS[(ix - 2 * tx, iy - 2 * ty)]}"


def _linear(h: str) -> list[float]:
    out = []
    for k in range(3):
        c = int(h[1 + 2 * k:3 + 2 * k], 16) / 255.0
        out.append(_r(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 4))
    return out


def sky_settings(plan: dict) -> dict:
    """AT3: the controller's sky and time from the plan's `sky` (an AT2 plan has none: {}).
    The glow's bounds in Unreal's frame (cm: [min X, min Y, max X, max Y], Y south)."""
    s = plan.get("sky") or {}
    if "curve" not in s:
        return {}
    m, cv, g = s["moon"], s["curve"], s.get("glow") or {}
    out = {"latitude_deg": float(s["latitude_deg"]),
           "declination_deg": float(s["declination_deg"]),
           "moon_lag_h": float(m["lag_h"]), "moon_declination_deg": float(m["declination_deg"]),
           "moon_lit": float(m["lit"]), "moon_share": float(m["share"]),
           "moon_color": _linear(m["color"]), "moon_disk_nits": float(m["disk_nits"]),
           "moon_disk_deg": float(m["disk_deg"]), "moon_rise": [float(v) for v in m["rise"]],
           "moon_cloud": float(m["cloud"]), "sun_lux": float(s["sun_lux"]),
           "scene_ev100": float(s["ev_night"]), "day_ev100": float(s["ev_day"]),
           "curve_elev": [float(v) for v in cv["elev"]],
           "curve_ev": [float(v) for v in cv["ev"]],
           "curve_night": [float(v) for v in cv["night"]],
           "curve_sun": [float(v) for v in cv["sun"]],
           "curve_sky": [float(v) for v in cv["sky"]],
           "curve_stars": [float(v) for v in cv["stars"]],
           "stars": float(s["stars"]), "cloud_deck_m": float(s["cloud_deck_m"]),
           "cloud_cover": float(s["cloud_cover"]),
           "day_hour": float(s["hours"]["day"]), "dusk_hour": float(s["hours"]["dusk"]),
           "night_hour": float(s["hours"]["night"])}
    if g:
        x0, y0, x1, y1 = g["bounds"]
        out.update({"glow_bounds": [_r(x0 * 100.0, 1), _r(-y1 * 100.0, 1),
                                    _r(x1 * 100.0, 1), _r(-y0 * 100.0, 1)],
                    "glow_max_nits": float(g["max_nits"]), "glow_sha256": g["sha256"]})
    return out


def atmos_data(pdir: Path) -> tuple[dict | None, str]:
    """The plan in the importer's form ({controller, cells}), or (None, why not)."""
    text = (pdir / "atmos_plan.json").read_text(encoding="utf-8")
    plan = json.loads(text)
    lux = (plan.get("checks") or {}).get("lux")
    if lux is None:
        return None, "the plan has no lux check (an AT0 plan: run atmosgen plan again)"
    if not lux.get("ok"):
        return None, "the plan's lux check failed (scope 8: not delivered)"
    faces = (plan.get("checks") or {}).get("faces")
    if faces is not None and not faces.get("ok"):
        return None, "the plan's faces check failed (AT2: a lit face floods its wall)"
    air = (plan.get("checks") or {}).get("air")
    if air is not None and not air.get("ok"):
        return None, "the plan's air check failed (AT4: an emitter off its source, a volume " \
                     "off its water or district, or a tile over its budget)"
    schedules = sorted(plan["schedules"])
    kinds, mounts = _kinds(), _mounts()
    cells: dict[tuple[int, int], list[dict]] = {}
    vols: dict[tuple[int, int], list[dict]] = {}
    emits: dict[tuple[int, int], list[dict]] = {}
    for t in plan["tiles"]:
        for L in json.loads((pdir / t["file"]).read_text(encoding="utf-8"))["lights"]:
            cells.setdefault(cell_of(L["pos"][0], L["pos"][1]), []).append(L)
    # AT4: a cell's fog volumes (by their middle) and emitters (by their foot)
    for V in plan.get("volumes") or []:
        vols.setdefault(cell_of(V["center"][0], V["center"][1]), []).append(V)
    for E in plan.get("emitters") or []:
        emits.setdefault(cell_of(E["pos"][0], E["pos"][1]), []).append(E)
    out = []
    for (ix, iy) in sorted(set(cells) | set(vols) | set(emits)):
        ls = sorted(cells.get((ix, iy), []), key=lambda r: r["id"])
        vs = sorted(vols.get((ix, iy), []), key=lambda r: r["id"])
        es = sorted(emits.get((ix, iy), []), key=lambda r: r["id"])
        fl, it = [], []
        for L in ls:
            f, i = pack(L, schedules, kinds, mounts)
            fl += f
            it += i
        vf, vi, ef, ei = [], [], [], []
        for V in vs:
            f, i = pack_volume(V, schedules)
            vf += f
            vi += i
        for E in es:
            f, i = pack_emitter(E, schedules)
            ef += f
            ei += i
        tile, name = cell_name(ix, iy)
        rec = {"key": f"atmos.lights.{name}", "cell": name, "tile": tile,
               "center": [(ix + 0.5) * CELL_M, (iy + 0.5) * CELL_M, 0.0],
               "count": len(ls),
               "hash": _sha16([PACK_VERSION, [L["hash"] for L in ls]] +
                              ([[V["hash"] for V in vs], [E["hash"] for E in es]]
                               if vs or es else [])),
               "floats": fl, "ints": it}
        if vs or es:
            rec.update({"volumes": len(vs), "emitters": len(es), "volume_floats": vf,
                        "volume_ints": vi, "emitter_floats": ef, "emitter_ints": ei})
        out.append(rec)
    ws = plan.get("weather_state") or {}
    tiers = plan.get("tiers") or {}
    ctl = {"city": plan["city"], "plan_hash": hashlib.sha256(text.encode("utf-8"))
           .hexdigest()[:16], "schedule_names": schedules,
           "schedule_hours": [float(v) for s in schedules for v in plan["schedules"][s]],
           "kind_names": kinds, "plan_ev100": float(plan.get("night_ev100", 3.0)),
           "hour": float(plan.get("hour", 23.0)),
           "fog_density": float(ws.get("fog_density", 0.018)),
           "fog_falloff": float(ws.get("fog_falloff", 0.08)),
           "fog_volumetric": float(ws.get("volumetric", 1.0)),
           "fog_albedo": ws.get("fog_albedo", "#8a97ad"),
           "rain_rate": float(ws.get("rain", 0.8)), "wind_ms": float(ws.get("wind_m_s", 6.0)),
           "max_live": int(tiers.get("mid_max", 512)),
           "mid_range_m": float(tiers.get("mid_m", 300.0)),
           "max_shadowed": int(tiers.get("near_max", 16)),
           "near_range_m": float(tiers.get("near_m", 60.0)),
           "max_high": int(tiers.get("high_max", 0)),
           "high_range_m": float(tiers.get("high_m", 750.0)), "cell_m": CELL_M}
    ctl.update(sky_settings(plan))
    ctl.update(air_settings(plan))
    ctl.update(sight_settings(plan, pdir))
    return {"version": PACK_VERSION, "controller": ctl, "cells": out}, ""


def write_atmos(build: str | Path, given: str | Path | None = None) -> dict | None:
    """The manifest's `atmos` (and BUILD/unreal/atmos.json, written only when its bytes
    change); None without a plan, {"skipped": why} for a plan not delivered."""
    pdir = plan_dir(build, given)
    if pdir is None:
        if given:
            raise FileNotFoundError(f"{given}: no atmos_plan.json (run atmosgen plan)")
        return None
    data, why = atmos_data(pdir)
    if data is None:
        return {"skipped": why, "plan": str(pdir)}
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n"
    dest = Path(build) / "unreal" / DATA
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file() or dest.read_text(encoding="utf-8") != text:
        dest.write_text(text, encoding="utf-8", newline="\n")
    ctl = data["controller"]
    # AT3: the deck's glow beside the manifest (the import makes it a texture)
    glow = None
    plan_sky = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8")).get("sky") or {}
    g = plan_sky.get("glow")
    gdest = Path(build) / "unreal" / GLOW
    if g and (pdir / g["file"]).is_file():
        b = (pdir / g["file"]).read_bytes()
        if not gdest.is_file() or gdest.read_bytes() != b:
            gdest.write_bytes(b)
        glow = {"file": f"unreal/{GLOW}", "sha256": hashlib.sha256(b).hexdigest()}
    elif gdest.is_file():
        gdest.unlink()
    return {"file": f"unreal/{DATA}", "plan": str(pdir), "plan_hash": ctl["plan_hash"],
            "key": CONTROLLER_KEY, "hash": _sha16([PACK_VERSION, ctl]), "glow": glow,
            "lights": sum(c["count"] for c in data["cells"]),
            "volumes": sum(c.get("volumes", 0) for c in data["cells"]),
            "emitters": sum(c.get("emitters", 0) for c in data["cells"]),
            "sight": ({"px": ctl["sight_px"], "cell_m": ctl["sight_cell_m"],
                       "runs": len(ctl["sight_runs"]) // 2, "sha256": ctl["sight_sha256"]}
                      if ctl.get("sight_runs") is not None else None),
            "cells": [{k: c[k] for k in ("key", "cell", "tile", "center", "count", "hash")}
                      for c in data["cells"]]}


def actor_hashes(atmos: dict | None) -> dict[str, str]:
    """The controller's and every cell actor's key and hash (`unreal.actor_hashes`)."""
    if not atmos or not atmos.get("cells"):
        return {}
    out = {atmos["key"]: atmos["hash"]}
    out.update({c["key"]: c["hash"] for c in atmos["cells"]})
    return out
