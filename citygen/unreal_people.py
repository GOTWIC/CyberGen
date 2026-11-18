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
3. **The clothing** (LG2, `dress`): between two editor runs, the textiles drawn
   (`lifegen/textiles.py`) and every character's garments cut, built and draped on its body
   in Blender (`lifegen/blender/garments.py`, a process per character, `BLENDER_JOBS` at once),
   from the bodies the first run exported; the second run makes the looks' skeletal meshes,
   mid meshes and cards from them. Both kept in the cache (`<hash>/textiles`, `garments`).
4. **The cache** (`cache_dir`): the library's built assets (`/Game/CityGen/People`) are kept
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
PLUGINS = ("MetaHumanCharacter", "AnimToTexture", "IKRig", "HairStrands", "RigLogic",
           "GeometryScripting")
CACHE_SKIP = ("Characters",)
RUNS_MAX = 12
BLENDER_JOBS = 4
PHASE_A = ("characters", "clips", "bodies")
DEFAULT_GAS =Path.home() / "CityGen" / "UnrealProjects" / "GameAnimationSample" / \
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
    """people_library.py in the project's full editor, off screen (the creator's build bakes
    its textures through texture graphs, which a commandlet does not run; the impostor sheets
    are scene captures). It never opens a sign-in (`-NoMetaHumanAccountPortalLoginFallback`):
    the cloud requests use the sign-in the editor keeps."""
    from .unreal import run_editor
    return run_editor(Path(root), Path(uproject), LIB_SCRIPT, job, log, timeout=timeout,
                      gui=True, extra=["-RenderOffscreen", "-NoMetaHumanAccountPortalLoginFallback",
                                       "-nop4"])


# --- 3. the clothing (LG2) ------------------------------------------------------------------

def dress(spec: dict, bodies_dir: Path, out_dir: Path, textiles_dir: Path, log_dir: Path,
          renders: bool = True, jobs: int = BLENDER_JOBS) -> dict:
    """The textiles and every character's looks built in Blender from its exported body; a
    character whose job is unchanged since its last run (`done.json` names the job's hash) is
    kept. {characters, built, kept, failed, seconds}."""
    import hashlib
    import subprocess
    from lifegen import garments as G
    from lifegen import textiles as TX
    from .blockout import find_blender
    t0 = time.time()
    if not (Path(textiles_dir) / "textiles.json").is_file() or json.loads(
            (Path(textiles_dir) / "textiles.json").read_text(encoding="utf-8")).get("version") \
            != TX.VERSION:
        TX.build(Path(textiles_dir))
    blender = find_blender(os.environ.get("BLENDER"))
    if not blender:
        return {"ok": False, "error": "no Blender (set BLENDER)"}
    script = Path(__file__).resolve().parent.parent / "lifegen" / "blender" / "garments.py"
    todo, kept = [], 0
    for c, looks in zip(spec["characters"], spec["looks"]):
        bp = Path(bodies_dir) / f"{c['id']}.json"
        if not bp.is_file():
            return {"ok": False, "error": f"no exported body for {c['id']} ({bp})"}
        body = json.loads(bp.read_text(encoding="utf-8"))
        od = Path(out_dir) / c["id"]
        job = G.blender_job(c, looks, str(bp), str(od), body, render=renders)
        h = hashlib.sha256(json.dumps(job, sort_keys=True).encode("utf-8") +
                           script.read_bytes()).hexdigest()[:16]
        done = od / "done.json"
        # ($CITYGEN_PEOPLE_KEEP_DRESS keeps every character dressed before, whatever changed:
        # for working on the editor's steps)
        if done.is_file() and (os.environ.get("CITYGEN_PEOPLE_KEEP_DRESS") or json.loads(
                done.read_text(encoding="utf-8")).get("hash") == h):
            kept += 1
            continue
        od.mkdir(parents=True, exist_ok=True)
        jp = od / "job.json"
        jp.write_text(json.dumps(job, indent=1), encoding="utf-8")
        todo.append((c["id"], jp, od, h))
    running, failed, built = [], [], 0
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    while todo or running:
        while todo and len(running) < jobs:
            cid, jp, od, h = todo.pop(0)
            lf = open(log_dir / f"garments_{cid}.log", "w", encoding="utf-8")
            pr = subprocess.Popen([blender, "-b", "--factory-startup", "-P", str(script), "--",
                                   str(jp)], stdout=lf, stderr=subprocess.STDOUT)
            running.append((pr, lf, cid, od, h))
        time.sleep(2.0)
        for item in list(running):
            pr, lf, cid, od, h = item
            if pr.poll() is None:
                continue
            lf.close()
            running.remove(item)
            ok = (od / "report.json").is_file() and "CGGARMENT_DONE" in \
                (log_dir / f"garments_{cid}.log").read_text(encoding="utf-8", errors="replace")
            if ok:
                (od / "done.json").write_text(json.dumps({"hash": h}), encoding="utf-8")
                built += 1
            else:
                failed.append(cid)
            print(f"CITYGEN_PEOPLE dressed {cid} ok={ok}", flush=True)
    return {"ok": not failed, "characters": len(spec["characters"]), "built": built,
            "kept": kept, "failed": failed, "seconds": round(time.time() - t0, 1)}


# --- 4. the cache ---------------------------------------------------------------------------

def _copy_tree(src: Path, dest: Path, skip: tuple[str, ...] = ()) -> tuple[int, int]:
    """Every file of `src` into `dest` where it differs, but those under a folder named in
    `skip` (relative to `src`); (copied, same)."""
    copied = same = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in skip):
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
    # ($CITYGEN_PEOPLE_HASH pins a library while its code is worked on)
    h = os.environ.get("CITYGEN_PEOPLE_HASH") or L.library_hash(n, engine=_engine_version(root))
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
        # (a closure listed before from the same sample is used again: the sample's editor
        # is opened only when needed)
        prev = log_dir / "gas" / "gas_closure.json"
        clo = json.loads(prev.read_text(encoding="utf-8")) if prev.is_file() else None
        if clo is None or not set(pk) <= {r["package"] for r in clo["keep"]} or \
                not all(Path(r["file"]).is_file() for r in clo["keep"] if r.get("file")):
            clo = gas_closure(Path(root), gas, log_dir / "gas", pk)
        res["migrate"] = {**migrate(clo, up), "packages": len(clo["keep"]),
                          "skipped": len(clo["skipped"]), "gas": str(gas)}
    # (2) the build in the project's editor: the characters, clips and bodies first, then the
    # clothing in Blender (LG2), then the looks, mid meshes and cards
    work = cache_dir(h)
    job = {"result": str(log_dir / "library_result.json"), "spec": spec, "hash": h,
           "manifest": str(saved / MANIFEST), "sheets_dir": str(log_dir / "sheets"),
           "tiers": dict(L.TIERS), "bodies_dir": str(log_dir / "bodies"),
           "garments_dir": str(work / "garments"), "textiles_dir": str(work / "textiles")}
    # (an editor run makes a few characters and ends, `restart`: the assembly's memory grows
    # with each one; the next run goes on where it ended, every step keeping what is made)
    runs = []
    k = 0
    for phase in ("a", "dress", "b"):
        if phase == "dress":
            res["dress"] = dress(spec, log_dir / "bodies", work / "garments", work / "textiles",
                                 log_dir / "garments")
            if not res["dress"].get("ok"):
                return {**res, "ok": False, "how": "build",
                        "error": f"the clothing failed: {res['dress']}"}
            continue
        job["steps"] = list(PHASE_A) if phase == "a" else None
        if job["steps"] is None:
            job.pop("steps")
        while k < RUNS_MAX * 2:
            r = run_library(Path(root), up, job, log_dir / f"library_log_{k}.txt")
            k += 1
            runs.append({"phase": phase, "ok": r.get("ok"), "restart": r.get("restart"),
                         "wall_s": r.get("wall_s")})
            if not r.get("restart"):
                break
        if not r.get("ok"):
            break
    res["build"] = {k: r.get(k) for k in ("ok", "error", "steps", "wall_s", "log", "missing")
                    if k in r}
    res["build"]["runs"] = runs
    if not r.get("ok") or not (saved / MANIFEST).is_file():
        return {**res, "ok": False, "how": "build",
                "error": r.get("error") or "the library's build failed (see its log)"}
    # (3) the cache: the library's content and manifest
    # (the runtime's assets: not the MetaHuman Character sources, which only a rebuild needs,
    # nor the sheets' pose instances)
    c, _ = _copy_tree(people, cache / "Content" / Path(L.CONTENT[len("/Game/"):]),
                      skip=CACHE_SKIP)
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


# --- LG4: the places' clips -----------------------------------------------------------------

PLACES_SCRIPT = UE_DIR / "people_places.py"
PLACES_MANIFEST = "places.json"
# people_idles: the second mid bake and impostor sheet per look (`people_places.py`'s
# `step_idles`): the bake's rate (the library's), how long a standing idle's and the sitting
# loop's baked stretch may be (s: from, to), the sheet's rows (the library's walk frames, then
# sitting and standing idle cells), the library's idle clip baked. The key (`idle_key`) is the
# library's hash and these: bump `version` when the bake or the sheet changes, so the next run
# makes them again (a change to the script alone keeps them).
IDLE_BAKE = {"version": "idles1", "fps": 15.0, "idle_s": [4.0, 8.0], "sit_s": [4.0, 8.0],
             "walk_frames": 8, "sit_cells": 4, "idle_cells": 4, "idle_clip": "idle_relaxed"}
# umbrella_hold: the right arm holding an umbrella (`people_places.py`'s `hold_pose`): from the
# group's standing idle at its first frame, the hand put by two-bone IK (the elbow toward
# `pole`: back, out, down) at the shoulder joint plus `fwd`, `out`, `up` (fractions of the arm's
# length, upper arm and forearm: on Delta's 47 cm arm about 22 cm ahead, 3 cm out, 8 cm down: the
# forearm raised, the hand by the shoulder), the wrist straight; the grip `grip` of the arm's length
# on from the wrist along the forearm (umb1 had the hand 19 cm down, the forearm level). The
# pose is a clip of its own per group (the idle, its arm held: `A_umb_hold`), which the near
# tier layers over any clip (the arm from the upper arm down) and the second mid bake bakes,
# with the walk its arm held (`A_umb_walk_*`), as two more loops. Its version is in the mid
# bakes' key only (`mid_key`): the still sheets keep `idle_key`.
UMB_HOLD = {"version": "umb2", "fwd": 0.46, "out": 0.06, "up": -0.18,
            "pole": [-0.3, 0.8, -1.0], "grip": 0.15}
PLACES_RUNS_MAX = 8
PLACES_PER_RUN = 48


def places_hash(lib_hash: str) -> str:
    """The places' clips' hash: the library's, the clips (`lifegen.presets.PLACE_CLIPS`), the
    script that makes them, the idles' bake (`IDLE_BAKE`)."""
    import hashlib
    from lifegen import presets as LP
    h = hashlib.sha256()
    h.update(lib_hash.encode("utf-8"))
    h.update(json.dumps(LP.PLACE_CLIPS, sort_keys=True).encode("utf-8"))
    h.update(PLACES_SCRIPT.read_bytes())
    h.update(json.dumps(IDLE_BAKE, sort_keys=True).encode("utf-8"))
    h.update(json.dumps(UMB_HOLD, sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:16]


def idle_key(lib_hash: str) -> str:
    """people_idles: the key the second mid bakes and sheets keep (`cg.idles`): the library's
    hash and `IDLE_BAKE`, not the script's bytes."""
    import hashlib
    h = hashlib.sha256()
    h.update(lib_hash.encode("utf-8"))
    h.update(json.dumps(IDLE_BAKE, sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:16]


def mid_key(lib_hash: str) -> str:
    """umbrella_hold: the key the second mid bakes keep (`cg.idles` on their data assets): the
    idles' key and `UMB_HOLD` (the still sheets keep `idle_key`, so a change of the hold bakes
    the mid tier again without capturing the sheets again)."""
    import hashlib
    h = hashlib.sha256()
    h.update(idle_key(lib_hash).encode("utf-8"))
    h.update(json.dumps(UMB_HOLD, sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:16]


def idle_bake(lib: dict) -> dict:
    """The job's `bake` for a library manifest: `IDLE_BAKE`, its key, the library's impostor
    layout (views, cell, the card's size in cm) and the sheet's rows."""
    from lifegen import library as L
    far = lib.get("far") or {}
    size = far.get("size") or [1.1, 2.2]
    rows = IDLE_BAKE["walk_frames"] + IDLE_BAKE["sit_cells"] + IDLE_BAKE["idle_cells"]
    return {**IDLE_BAKE, "key": idle_key(lib["hash"]), "mid_key": mid_key(lib["hash"]),
            "umbrella": dict(UMB_HOLD), "views": int(far.get("views") or 8),
            "rows": rows, "cell": list(far.get("cell") or L.IMPOSTOR_CELL),
            "card_cm": [round(float(size[0]) * 100.0, 3), round(float(size[1]) * 100.0, 3)]}


def read_places(uproject: Path) -> dict | None:
    """The places' clips' manifest in the project (Saved/CityGenPeople/places.json), if it
    belongs to the project's library."""
    p = Path(uproject).parent / "Saved" / "CityGenPeople" / PLACES_MANIFEST
    lib = read_manifest(uproject)
    if not p.is_file() or not lib:
        return None
    man = json.loads(p.read_text(encoding="utf-8"))
    return man if man.get("lib_hash") == lib.get("hash") else None


def ensure_place_clips(root: Path, uproject: Path, gas: Path | None = None,
                       log_dir: Path | None = None) -> dict:
    """LG4: the places' clips (a bench's sitting loop, standing idle breaks: `lifegen.presets.
    PLACE_CLIPS`; people_idles: the bench's sit-downs and stand-up) in the project, retargeted
    with the library's own retargeter onto each of its clip groups' body skeleton
    (`citygen/ue/people_places.py`); people_idles: per look a second mid bake (the walk, a
    standing idle, the sitting loop) and a still sheet for its card. Their manifest kept when
    its hash is the same; else the sample's clips copied in (its closure, `gas_closure`,
    `migrate`) and the editor's runs (a run makes at most `PLACES_PER_RUN` looks' bakes and
    sheets, the next going on). The library's assets and hash are untouched. {ok, how, hash,
    manifest}."""
    from lifegen import presets as LP
    t0 = time.time()
    up = Path(uproject).resolve()
    lib = read_manifest(up)
    if not lib or not lib.get("clip_groups"):
        return {"ok": False, "how": "none", "error": "no people library in the project"}
    h = places_hash(lib["hash"])
    saved = up.parent / "Saved" / "CityGenPeople"
    have = read_places(up)
    if have and have.get("hash") == h:
        return {"ok": True, "how": "kept", "hash": h, "manifest": have,
                "seconds": round(time.time() - t0, 1)}
    log_dir = Path(log_dir or saved)
    log_dir.mkdir(parents=True, exist_ok=True)
    res = {"hash": h}
    clips = dict(LP.PLACE_CLIPS)
    need = [p for p in clips.values()
            if not (content_dir(up, p.rsplit("/", 1)[0]) / (p.rsplit("/", 1)[1] + ".uasset"))
            .is_file()]
    if need:
        gas = Path(gas or os.environ.get("CITYGEN_GAS") or DEFAULT_GAS)
        if not gas.is_file():
            return {**res, "ok": False, "how": "build",
                    "error": f"no Game Animation Sample at {gas} (--gas UPROJECT): the places' "
                             "clips come from it (Epic's, in your project only)"}
        clo = gas_closure(Path(root), gas, log_dir / "gas_places", sorted(clips.values()))
        res["migrate"] = {**migrate(clo, up), "packages": len(clo["keep"]),
                          "skipped": len(clo["skipped"]), "gas": str(gas)}
    from lifegen import library as L
    groups = {}
    for key in sorted(lib["clip_groups"]):
        body = next((c["near"]["meshes"][0] for c in lib["characters"]
                     if c.get("skeleton") == key), None)
        if body is None:
            continue
        gclips = lib["clip_groups"][key].get("clips") or {}
        idle = (gclips.get(IDLE_BAKE["idle_clip"]) or next(
            (v for k, v in sorted(gclips.items()) if k.startswith("idle")), {})).get("anim", "")
        groups[key] = {"body": body, "idle": idle,
                       "retargeter": f"{lib['content']}/Anim/{key}/RTG_GasToBody_{lib['hash'][:8]}"}
    # (people_idles: the looks whose group has a body and an idle and that have the library's
    # mid data asset)
    looks = [{"id": c["id"], "skeleton": c.get("skeleton"), "mid": c["mid"]}
             for c in lib["characters"]
             if c.get("skeleton") in groups and groups[c["skeleton"]]["idle"]
             and (c.get("mid") or {}).get("data")]
    job = {"result": str(log_dir / "places_result.json"), "hash": h, "lib_hash": lib["hash"],
           "content": lib["content"], "gas_mesh": L.GAS_MESH, "clips": clips, "groups": groups,
           "manifest": str(saved / PLACES_MANIFEST), "looks": looks,
           "bake": idle_bake(lib) if looks else {}, "per_run": PLACES_PER_RUN,
           "sheets_dir": str(log_dir / "sheets_idle"),
           "export_sheets": [lk["id"] for lk in looks[:2]]}
    from .unreal import run_editor
    runs = []
    for k in range(PLACES_RUNS_MAX):
        r = run_editor(Path(root), up, PLACES_SCRIPT, job, log_dir / f"places_log_{k}.txt",
                       timeout=3 * 3600.0, gui=True, extra=["-RenderOffscreen", "-nop4"])
        runs.append({"ok": r.get("ok"), "restart": r.get("restart"), "wall_s": r.get("wall_s"),
                     "looks": len(r.get("looks") or {})})
        if not r.get("restart"):
            break
        # (the next run keeps the clips this one made, with their measures)
        job["old"] = r.get("groups") or {}
    res["build"] = {k: r.get(k) for k in ("ok", "error", "missing", "wall_in_editor_s",
                                          "groups", "windows") if k in r}
    res["build"]["runs"] = runs
    if not r.get("ok"):
        return {**res, "ok": False, "how": "build",
                "error": r.get("error") or "the places' clips failed (see its log)"}
    return {**res, "ok": True, "how": "build", "manifest": read_places(up),
            "seconds": round(time.time() - t0, 1)}


def _engine_version(root: Path) -> str:
    """The engine's version (Engine/Build/Build.version), part of the library's hash."""
    p = Path(root) / "Engine" / "Build" / "Build.version"
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return f"{v.get('MajorVersion')}.{v.get('MinorVersion')}.{v.get('PatchVersion')}"
    except (OSError, ValueError):
        return ""
