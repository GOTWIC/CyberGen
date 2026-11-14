"""lifegen's people library in the user's project (LG1; venv side, no Unreal Python).

The library (`lifegen/library.py`: its spec and hash) is made in the project the city is
imported into, by a step the user runs once (decision 5: MetaHumans, MetaHuman assets and
Epic's animations never go in the repo):

1. **Epic's animations** (`migrate`): the walks and idles the people use, with the
   mannequin they are made on, copied from the user's Game Animation Sample into the project
   (`citygen/ue/people_gas.py` lists the closure of their hard references in the sample, read
   only: `-userdir=` outside it; their notifies' Blueprints and sounds left behind).
2. **The characters** (`citygen/ue/people_library.py` in the project's editor): each a
   MetaHuman made from the engine's presets by script, rigged and given its skin's texture
   sources by Epic's MetaHuman cloud service (the user's own sign-in, which the editor keeps;
   the run never opens a sign-in: `-NoMetaHumanAccountPortalLoginFallback`), assembled by the
   creator's Optimized build; the clips retargeted onto its body; its walk baked to textures
   for the mid crowd (AnimToTexture) and drawn into an impostor sheet for the far crowd.
3. **The cache** (`cache_dir`): the library's built assets (`/Game/CityGen/People`) are kept
   outside the repo, `~/.cache/cybergen/people/<hash>/` (or `$CITYGEN_PEOPLE_CACHE`), as AG6's
   texture library is, with its manifest (`library.json`). A project whose stamp names the
   hash has it; another project gets it copied from the cache, so the cloud steps and the
   sample are needed only for a library not built before.

`ensure_library` does the three; `citygen unreal ... --people` calls it before the import, and
`write_life` reads its manifest (`unreal_life.people_data`).
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

UE_DIR = Path(__file__).resolve().parent / "ue"
GAS_SCRIPT = UE_DIR / "people_gas.py"
LIB_SCRIPT = UE_DIR / "people_library.py"
STAMP = "CityGenPeople.stamp"
MANIFEST = "library.json"
# the engine plugins the library's build and its assets need in the project
PLUGINS = ("MetaHumanCharacter", "AnimToTexture", "IKRig", "HairStrands", "RigLogic")
DEFAULT_GAS = Path.home() / "CityGen" / "UnrealProjects" / "GameAnimationSample" / \
    "GameAnimationSample.uproject"


def cache_root() -> Path:
    env = os.environ.get("CITYGEN_PEOPLE_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "cybergen" / "people"


def cache_dir(lib_hash: str) -> Path:
    return cache_root() / lib_hash


def content_dir(uproject: Path, game_path: str) -> Path:
    """A /Game/... folder's directory on disk."""
    assert game_path.startswith("/Game/")
    return Path(uproject).parent / "Content" / game_path[len("/Game/"):]


def enable_plugins(uproject: Path, names=PLUGINS) -> list[str]:
    """The engine plugins the library needs, enabled in the .uproject; those added."""
    data = json.loads(Path(uproject).read_text(encoding="utf-8-sig"))
    plugins = data.setdefault("Plugins", [])
    added = []
    for n in names:
        have = [p for p in plugins if p.get("Name") == n]
        if have and all(p.get("Enabled") for p in have):
            continue
        data["Plugins"] = plugins = [p for p in plugins if p.get("Name") != n]
        plugins.append({"Name": n, "Enabled": True})
        added.append(n)
    if added:
        Path(uproject).write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8",
                                  newline="\n")
    return added


# --- 1. Epic's animations from the user's Game Animation Sample ----------------------------

def gas_closure(root: Path, gas: Path, scratch: Path, packages: list[str],
                timeout: float = 3600.0) -> dict:
    """The hard references of `packages` in the sample (its editor, read only: Saved and
    Intermediate under `scratch`); {keep: [{package, class, file, uexp}], skipped: [...]}."""
    from .unreal import _streamed, editor_binary
    scratch.mkdir(parents=True, exist_ok=True)
    job = scratch / "gas_job.json"
    out = scratch / "gas_closure.json"
    job.write_text(json.dumps({"packages": packages, "out": str(out)}, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    if out.exists():
        out.unlink()
    cmd = [str(editor_binary(root)), str(gas), "-run=pythonscript", f"-script={GAS_SCRIPT}",
           "-unattended", "-nosplash", "-nullrhi", "-nop4", f"-userdir={scratch / 'user'}",
           "-stdout", "-FullStdOutLogOutput"]
    code = _streamed(cmd, scratch / "gas_log.txt", lambda line: None, timeout,
                     {**os.environ, "CITYGEN_GAS_JOB": str(job)})
    if not out.is_file():
        raise RuntimeError(f"the sample's editor wrote no closure (exit {code}; "
                           f"log {scratch / 'gas_log.txt'})")
    return json.loads(out.read_text(encoding="utf-8"))


def migrate(closure: dict, uproject: Path) -> dict:
    """The closure's files into the project at their own paths (/Game/... as in the sample),
    each copied only where it differs; {copied, same, bytes}."""
    dest = Path(uproject).parent / "Content"
    src_root = Path(closure["content"])
    copied = same = size = 0
    for rec in closure["keep"]:
        for key in ("file", "uexp"):
            f = rec.get(key)
            if not f:
                continue
            f = Path(f)
            d = dest / f.relative_to(src_root)
            size += f.stat().st_size
            if d.is_file() and d.stat().st_size == f.stat().st_size and \
                    d.read_bytes() == f.read_bytes():
                same += 1
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, d)
            copied += 1
    return {"copied": copied, "same": same, "bytes": size}


# --- 2. the library built in the project ----------------------------------------------------

def run_library(root: Path, uproject: Path, job: dict, log: Path,
                timeout: float = 4 * 3600.0) -> dict:
    """people_library.py in the project's editor (a commandlet that renders: the creator's
    build bakes textures, the impostor sheets are rendered)."""
    from .unreal import run_editor
    return run_editor(Path(root), Path(uproject), LIB_SCRIPT, job, log, timeout=timeout,
                      extra=["-AllowCommandletRendering", "-NoMetaHumanAccountPortalLoginFallback",
                             "-nop4"])


# --- 3. the cache ---------------------------------------------------------------------------

def _copy_tree(src: Path, dest: Path) -> tuple[int, int]:
    """Every file of `src` into `dest` where it differs; (copied, same)."""
    copied = same = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        d = dest / f.relative_to(src)
        if d.is_file() and d.stat().st_size == f.stat().st_size and \
                d.stat().st_mtime_ns >= f.stat().st_mtime_ns:
            same += 1
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, d)
        copied += 1
    return copied, same


def read_manifest(uproject: Path) -> dict | None:
    """The library's manifest in the project (Saved/CityGenPeople/library.json)."""
    p = Path(uproject).parent / "Saved" / "CityGenPeople" / MANIFEST
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def ensure_library(root: Path, uproject: Path, gas: Path | None = None,
                   log_dir: Path | None = None, force: bool = False,
                   characters: int | None = None) -> dict:
    """The people library in the project: as stamped (nothing to do), from the cache, or
    built (the sample's clips copied, the editor's build run, the result cached). {ok, how,
    hash, manifest, ...}."""
    from lifegen import library as L
    from .unreal import find_engine  # noqa: F401  (the caller resolved `root`)
    t0 = time.time()
    up = Path(uproject).resolve()
    n = characters or L.CHARACTERS
    eng = Path(root).resolve().as_posix()
    h = L.library_hash(n, engine=_engine_version(root))
    saved = up.parent / "Saved" / "CityGenPeople"
    stamp = up.parent / "Saved" / STAMP
    people = content_dir(up, L.CONTENT)
    added = enable_plugins(up)
    if not force and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == h and \
            (saved / MANIFEST).is_file():
        return {"ok": True, "how": "stamped", "hash": h, "plugins_enabled": added,
                "manifest": json.loads((saved / MANIFEST).read_text(encoding="utf-8")),
                "seconds": round(time.time() - t0, 1)}
    cache = cache_dir(h)
    if not force and (cache / MANIFEST).is_file() and (cache / "Content").is_dir():
        c, s = _copy_tree(cache / "Content", up.parent / "Content")
        saved.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache / MANIFEST, saved / MANIFEST)
        stamp.write_text(h + "\n", encoding="utf-8", newline="\n")
        return {"ok": True, "how": "cache", "hash": h, "copied": c, "same": s,
                "plugins_enabled": added, "cache": str(cache),
                "manifest": json.loads((cache / MANIFEST).read_text(encoding="utf-8")),
                "seconds": round(time.time() - t0, 1)}
    log_dir = Path(log_dir or saved)
    log_dir.mkdir(parents=True, exist_ok=True)
    res = {"hash": h, "plugins_enabled": added, "engine": eng}
    # (1) the sample's clips, unless the project has them from an earlier build
    spec = L.spec(n)
    have_clips = all((content_dir(up, p.rsplit("/", 1)[0]) / (p.rsplit("/", 1)[1] + ".uasset"))
                     .is_file() for p in spec["clips"].values())
    if not have_clips:
        gas = Path(gas or os.environ.get("CITYGEN_GAS") or DEFAULT_GAS)
        if not gas.is_file():
            return {**res, "ok": False, "how": "build",
                    "error": f"no Game Animation Sample at {gas} (--gas UPROJECT): the "
                             "people's clips come from it (Epic's, in your project only)"}
        pk = sorted(set(spec["clips"].values()) | {spec["gas"]["mesh"], spec["gas"]["skeleton"],
                                                   spec["gas"]["ik_rig"]})
        clo = gas_closure(Path(root), gas, log_dir / "gas", pk)
        res["migrate"] = {**migrate(clo, up), "packages": len(clo["keep"]),
                          "skipped": len(clo["skipped"]), "gas": str(gas)}
    # (2) the build in the project's editor
    job = {"result": str(log_dir / "library_result.json"), "spec": spec, "hash": h,
           "manifest": str(saved / MANIFEST)}
    r = run_library(Path(root), up, job, log_dir / "library_log.txt")
    res["build"] = {k: r.get(k) for k in ("ok", "error", "steps", "wall_s", "log", "missing")
                    if k in r}
    if not r.get("ok") or not (saved / MANIFEST).is_file():
        return {**res, "ok": False, "how": "build",
                "error": r.get("error") or "the library's build failed (see its log)"}
    # (3) the cache: the library's content and manifest
    c, _ = _copy_tree(people, cache / "Content" / Path(L.CONTENT[len("/Game/"):]))
    for extra in (json.loads((saved / MANIFEST).read_text(encoding="utf-8")).get("extra_folders")
                  or []):
        src = content_dir(up, extra)
        if src.is_dir():
            _copy_tree(src, cache / "Content" / Path(extra[len("/Game/"):]))
    shutil.copy2(saved / MANIFEST, cache / MANIFEST)
    stamp.write_text(h + "\n", encoding="utf-8", newline="\n")
    return {**res, "ok": True, "how": "build", "cached": c, "cache": str(cache),
            "manifest": json.loads((saved / MANIFEST).read_text(encoding="utf-8")),
            "seconds": round(time.time() - t0, 1)}


def _engine_version(root: Path) -> str:
    """The engine's version (Engine/Build/Build.version), part of the library's hash."""
    p = Path(root) / "Engine" / "Build" / "Build.version"
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return f"{v.get('MajorVersion')}.{v.get('MinorVersion')}.{v.get('PatchVersion')}"
    except (OSError, ValueError):
        return ""
