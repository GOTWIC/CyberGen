"""AT0: atmosgen's side of the Unreal exporter (docs/unreal_export.md, "From AT0").

- The runtime plugin `CityGenAtmos` (citygen/ue/CityGenAtmos) is installed and built with the
  play features' (`unreal_play.PLUGINS`, one UnrealBuildTool run).
- Its assets (`citygen/ue/atmos_assets.py`: MPC_CityGenAtmos, M_CgRain, M_CgWet under
  /Game/CityGen/Core/Atmos) are made in the project by a headless editor run, skipped when the
  project has this version of them (`make_assets`). AT1 folds this into the import and
  places the controller and the tiles' lights in the level from the plan's contribution
  (`BUILD/atmos/unreal_contribution.atmos.json`).
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).parent / "ue" / "atmos_assets.py"
STAMP = "citygen_atmos_assets.txt"          # in PROJECT/Saved


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
