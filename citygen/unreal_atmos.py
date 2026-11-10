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
CONTROLLER_KEY = "atmos"
CELL_M = 128.0                              # World Partition's main cells (unreal.MAIN_CELL_M)
PACK_VERSION = 1
FLOATS = 16                                 # CityGenAtmosCell.h, CityGenAtmosPack
INTS = 2
SHAPES = {"spot": 0, "point": 1, "rect": 2}
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
    counterclockwise heading is Unreal's -yaw) and INTS ints (flags, seed)."""
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
    flags = (shape | (4 if L.get("shadow") else 0) | (8 if L.get("tier") == "near" else 0)
             | (16 if L.get("on", True) else 0) | (schedules.index(L["schedule"]) << 8)
             | (kinds.index(L["kind"]) << 16) | (mounts.index(L.get("mount", "prop")) << 24))
    seed = int(L["hash"][:8], 16)
    if seed >= 2 ** 31:
        seed -= 2 ** 32
    return f, [flags, seed]


def cell_of(x: float, y: float) -> tuple[int, int]:
    return int(math.floor(x / CELL_M)), int(math.floor(y / CELL_M))


def cell_name(ix: int, iy: int) -> tuple[str, str]:
    """A 128 m cell's tile (citygen's 256 m tile) and its name `<tile>.<quarter>`."""
    tx, ty = ix // 2, iy // 2
    tile = f"t{tx:+03d}{ty:+03d}"
    return tile, f"{tile}.{QUARTERS[(ix - 2 * tx, iy - 2 * ty)]}"


def atmos_data(pdir: Path) -> tuple[dict | None, str]:
    """The plan in the importer's form ({controller, cells}), or (None, why not)."""
    text = (pdir / "atmos_plan.json").read_text(encoding="utf-8")
    plan = json.loads(text)
    lux = (plan.get("checks") or {}).get("lux")
    if lux is None:
        return None, "the plan has no lux check (an AT0 plan: run atmosgen plan again)"
    if not lux.get("ok"):
        return None, "the plan's lux check failed (scope 8: not delivered)"
    schedules = sorted(plan["schedules"])
    kinds, mounts = _kinds(), _mounts()
    cells: dict[tuple[int, int], list[dict]] = {}
    for t in plan["tiles"]:
        for L in json.loads((pdir / t["file"]).read_text(encoding="utf-8"))["lights"]:
            cells.setdefault(cell_of(L["pos"][0], L["pos"][1]), []).append(L)
    out = []
    for (ix, iy) in sorted(cells):
        ls = sorted(cells[(ix, iy)], key=lambda r: r["id"])
        fl, it = [], []
        for L in ls:
            f, i = pack(L, schedules, kinds, mounts)
            fl += f
            it += i
        tile, name = cell_name(ix, iy)
        out.append({"key": f"atmos.lights.{name}", "cell": name, "tile": tile,
                    "center": [(ix + 0.5) * CELL_M, (iy + 0.5) * CELL_M, 0.0],
                    "count": len(ls),
                    "hash": _sha16([PACK_VERSION, [L["hash"] for L in ls]]),
                    "floats": fl, "ints": it})
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
           "near_range_m": float(tiers.get("near_m", 60.0)), "cell_m": CELL_M}
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
    return {"file": f"unreal/{DATA}", "plan": str(pdir), "plan_hash": ctl["plan_hash"],
            "key": CONTROLLER_KEY, "hash": _sha16([PACK_VERSION, ctl]),
            "lights": sum(c["count"] for c in data["cells"]),
            "cells": [{k: c[k] for k in ("key", "cell", "tile", "center", "count", "hash")}
                      for c in data["cells"]]}


def actor_hashes(atmos: dict | None) -> dict[str, str]:
    """The controller's and every cell actor's key and hash (`unreal.actor_hashes`)."""
    if not atmos or not atmos.get("cells"):
        return {}
    out = {atmos["key"]: atmos["hash"]}
    out.update({c["key"]: c["hash"] for c in atmos["cells"]})
    return out
