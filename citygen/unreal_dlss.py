"""NVIDIA's DLSS plugins in an Unreal project (`citygen unreal ... --dlss DIR` or
$CITYGEN_DLSS; docs/unreal_export.md, "DLSS"). dlss_lamps_flicker.

NVIDIA ships DLSS for Unreal as a zip of plugins under its own license (the NVIDIA RTX SDK
EULA in the zip's Documentation): nothing of it is in this repository. The user downloads it,
extracts it anywhere outside the repo and the engine, and names the folder (the zip's root,
which holds `Plugins/`, or that `Plugins/` folder itself). With it the exporter:

- copies the plugins DLSS needs into the project's `Plugins/` (`PLUGINS`: DLSS Super
  Resolution, Streamline's core, Frame Generation, Reflex and the NGX common module; not NIS,
  RTX Dynamic Vibrance, the Movie Render Queue support or the deprecated Streamline), again
  only when the source changes (`STAMP` in the project's `Plugins/DLSS`);
- enables them in the .uproject (so a packaged game builds, cooks and stages them: their
  runtime DLLs are the plugins' own runtime dependencies);
- sets their project settings (`SETTINGS`: DLSS's on-screen debug messages off, Frame
  Generation's debug overlay off) and the engine's anti-aliasing to TSR, which DLSS replaces
  when on (the plugin hooks the engine's temporal upscaler).

Without it the exporter does nothing of this: a project imported before keeps the plugins it
has. The play features' developer menu (CityGenPlay, `CityGenUpscaler`) offers DLSS's modes
and Frame Generation only where the plugin is in the game and runs on the machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

ENV = "CITYGEN_DLSS"
# the plugins copied, in dependency order (DLSS and Frame Generation need the NGX common
# module; Frame Generation and Reflex Streamline's core)
PLUGINS = ("StreamlineNGXCommon", "StreamlineCore", "StreamlineReflex", "StreamlineDLSSG",
           "DLSS")
STAMP = ".citygen_dlss"               # PROJECT/Plugins/DLSS/.citygen_dlss: what was copied
SETTINGS = {
    "[/Script/DLSS.DLSSSettings]": [("bShowDLSSSDebugOnScreenMessages", "False")],
    "[/Script/StreamlineRHI.StreamlineSettings]": [("bLoadDebugOverlay", "False")],
    "[/Script/Engine.RendererSettings]": [("r.AntiAliasingMethod", "4")],
}


def source(given: str | Path | None = None) -> Path | None:
    """The plugins' folder from `given` or $CITYGEN_DLSS (the extracted zip's root, or its
    `Plugins` folder); None when neither is set. Raises when it holds no DLSS plugin."""
    g = given or os.environ.get(ENV)
    if not g:
        return None
    p = Path(g)
    for d in (p / "Plugins", p):
        if (d / "DLSS" / "DLSS.uplugin").is_file():
            return d
    raise FileNotFoundError(f"{g}: no DLSS/DLSS.uplugin under it or its Plugins folder "
                            "(extract NVIDIA's DLSS plugin zip and name its folder)")


def version(src: Path) -> str:
    d = json.loads((src / "DLSS" / "DLSS.uplugin").read_text(encoding="utf-8-sig"))
    return str(d.get("VersionName") or d.get("Version") or "")


def _digest(src: Path) -> str:
    """What identifies the source: each plugin's descriptor, and every file's path, size and
    time (the binaries are large; a new download changes these)."""
    h = hashlib.sha256()
    for name in PLUGINS:
        base = src / name
        for f in sorted(base.rglob("*")):
            if f.is_file():
                st = f.stat()
                h.update(f"{name}/{f.relative_to(base).as_posix()} {st.st_size} "
                         f"{int(st.st_mtime)}\n".encode("utf-8"))
    return h.hexdigest()[:16]


def installed(uproject: str | Path) -> str:
    """The stamp of the DLSS plugins copied into a project ("" when none): what the play
    plugin's build stamp includes, so a project with DLSS added builds once more."""
    f = Path(uproject).parent / "Plugins" / "DLSS" / STAMP
    return f.read_text(encoding="utf-8").strip() if f.is_file() else ""


def install(src: Path, uproject: str | Path, say=None) -> dict:
    """The plugins into PROJECT/Plugins (skipped when the stamp names this source), enabled
    in the .uproject, their settings in Config/DefaultEngine.ini. {version, copied, files,
    enabled, settings_changed}."""
    from .unreal import set_engine_ini
    up = Path(uproject)
    missing = [n for n in PLUGINS if not (src / n / f"{n}.uplugin").is_file()]
    if missing:
        raise FileNotFoundError(f"{src}: no {', '.join(missing)} plugin (NVIDIA's DLSS zip "
                                "has them all under Plugins/)")
    want = f"{version(src)} {_digest(src)}"
    dest = up.parent / "Plugins"
    copied, files = False, 0
    if installed(up) != want or any(not (dest / n / f"{n}.uplugin").is_file()
                                    for n in PLUGINS):
        for name in PLUGINS:
            if say:
                say(f"dlss: copying {name}")
            # (not NVIDIA's own build intermediates: UnrealBuildTool builds the plugins'
            # modules for this project, as a packaged game's build does)
            shutil.copytree(src / name, dest / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("Intermediate"))
            files += sum(1 for f in (src / name).rglob("*")
                         if f.is_file() and "Intermediate" not in f.relative_to(src).parts)
        (dest / "DLSS" / STAMP).write_text(want + "\n", encoding="utf-8", newline="\n")
        copied = True
    enabled = enable(up)
    changed = False
    for section, keys in SETTINGS.items():
        changed = set_engine_ini(up, section, keys) or changed
    return {"version": version(src), "source": str(src), "copied": copied, "files": files,
            "enabled": enabled, "settings_changed": changed, "stamp": want}


def enable(uproject: Path) -> list[str]:
    """Each plugin enabled in the .uproject (the ones added or switched on)."""
    data = json.loads(uproject.read_text(encoding="utf-8-sig"))
    plugins = data.setdefault("Plugins", [])
    added = []
    for name in PLUGINS:
        have = [p for p in plugins if p.get("Name") == name]
        if have and all(p.get("Enabled") for p in have):
            continue
        data["Plugins"] = plugins = [p for p in plugins if p.get("Name") != name]
        plugins.append({"Name": name, "Enabled": True})
        added.append(name)
    if added:
        uproject.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8",
                            newline="\n")
    return added
