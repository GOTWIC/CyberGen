"""AG16: the city benchmark (`citygen unreal BUILD UPROJECT --bench`, docs/unreal_export.md,
"From AG16").

A fixed route through an imported city, run in a standalone game process (`UnrealEditor
PROJECT MAP -game`, not play-in-editor) by the play plugin's `UCityGenBench`
(citygen/ue/CityGenPlay): sidewalk walks in the three districts with the most stage 2 actors,
a drive at street level along the lanes, a flight across the city at 150 m and a teleport
back across it, in passes by day and by night, at the native resolution and at a lower
screen percentage with TSR. Each frame's frame, game, render, RHI and GPU times, draw calls,
streaming state, VRAM and RAM, and the engine's CSV profile beside them (Nanite root pages,
the GPU's passes), become per pass and per part of the route: frame time p50, p95 and p99,
hitches, the thread that sets the frame, streaming waits and memory (`summarize`), over
several runs (`combine`), as JSON and a table (`write_results`).

The route depends on the build alone (`route`), so before and after a change it is the same
route. Venv side only: no Unreal module here.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path

ROUTE_VERSION = 1
EYE_M = 1.7                  # a walker's eye over the walkway
WALK_M = 150.0               # each sidewalk walk
WALK_SPEED = 5.0             # m/s: a run
WALK_DISTRICTS = 3           # walks in the districts with the most stage 2 actors
MAX_STEP_M = 0.6             # a walk's highest step where two walkways join
DRIVE_M = 1200.0             # the drive along the lanes
DRIVE_SPEED = 25.0           # m/s (90 km/h)
DRIVE_EYE_M = 4.0            # over the lane: at street level, over the traffic
FLY_Z_M = 150.0              # the flight across the city, over the ground
FLY_SPEED = 50.0             # m/s: the fly pawn's speed (citygen.unreal.FLY_SPEED_M_S)
FLY_MAX_M = 4000.0
FLY_PITCH = -15.0            # degrees: looking down over the city
DRIVE_PITCH = -5.0
HOLD_S = 6.0                 # held after the teleport has streamed in
RESOLUTION = (2560, 1440)    # 1440p (decision 13.4's target: the Windows PC)
TSR_PERCENT = 67.0
PASSES = (("day_native", False, 100.0), ("day_tsr67", False, TSR_PERCENT),
          ("night_native", True, 100.0), ("night_tsr67", True, TSR_PERCENT))
HITCH_MS = 50.0
BIG_HITCH_MS = 100.0
TARGET_MS = 16.7             # 60 fps at the 95th percentile (Swagnik, 2026-11-05)
FLOOR_MS = 25.0              # else 40 fps
VRAM_MB = 10240.0
# what the game runs before the route: no frame limit, TSR, a fixed exposure of its own
# nowhere (the level's), no on-screen messages
COMMANDS = ("r.VSync 0", "t.MaxFPS 0", "r.AntiAliasingMethod 4",
            "r.ScreenPercentage.Default.Desktop.Mode 0", "DisableAllScreenMessages")
LOAD_RADIUS_M = 150.0        # a load waits until the cells within this of the spot are in
STREAM_RADIUS_M = 100.0      # a moving frame counts as streamed when these are
ROOT_PAGE_MB = 32768 / 1048576.0     # NANITE_ROOT_PAGE_GPU_SIZE (32 KB)
GROUPS = ("walk", "drive", "fly", "teleport")


def _line(g: dict, i: int) -> list[tuple[float, float, float]]:
    ps, pts = g["point_start"], g["points"]
    return [(pts[3 * k], pts[3 * k + 1], pts[3 * k + 2]) for k in range(ps[i], ps[i + 1])]


def _length(path) -> float:
    return sum(math.dist(path[j][:2], path[j + 1][:2]) for j in range(len(path) - 1))


def _walk(g: dict, start: tuple[float, float], length_m: float) -> list:
    """A walk of `length_m` from the sidewalk point nearest `start`: along that sidewalk, then
    on into its neighbors, sidewalks first (as the check's `sidewalk_path`, without its
    traces), never up an elevator or a step over MAX_STEP_M; the longest of the first 12
    sidewalks nearest the start."""
    near = []
    for i, kind in enumerate(g["kinds"]):
        if kind != "sidewalk":
            continue
        ln = _line(g, i)
        d, k = min(((p[0] - start[0]) ** 2 + (p[1] - start[1]) ** 2, k)
                   for k, p in enumerate(ln))
        near.append((d, i, k))
    best = []
    for _, i, k in sorted(near)[:12]:
        ln = _line(g, i)
        path = ln[k:] if len(ln) - k >= 2 else ln[::-1][len(ln) - 1 - k:]
        seen, cur = {i}, i
        while _length(path) < length_m:
            links = g["links"][g["link_start"][cur]:g["link_start"][cur + 1]]
            nxt = None
            for j in sorted(links, key=lambda j: (g["kinds"][j] != "sidewalk", j)):
                if j in seen or g["kinds"][j] in ("elevator", "stairs"):
                    continue
                lj = _line(g, j)
                if len(lj) < 2:
                    continue
                if math.dist(lj[0][:2], path[-1][:2]) > math.dist(lj[-1][:2], path[-1][:2]):
                    lj = lj[::-1]
                if abs(lj[0][2] - path[-1][2]) > MAX_STEP_M:
                    continue
                nxt = (j, lj)
                break
            if nxt is None:
                break
            cur, lj = nxt
            seen.add(cur)
            path += lj[1:]
        if _length(path) > _length(best):
            best = path
        if _length(best) >= length_m:
            break
    return _cut(best, length_m)


def _cut(path: list, length_m: float) -> list:
    """`path` up to `length_m` along it."""
    out, total = path[:1], 0.0
    for a, b in zip(path, path[1:]):
        d = math.dist(a[:2], b[:2])
        if total + d >= length_m:
            f = (length_m - total) / d if d else 0.0
            out.append(tuple(a[k] + (b[k] - a[k]) * f for k in range(3)))
            return out
        total += d
        out.append(b)
    return out


def _drive(g: dict, start: tuple[float, float], length_m: float) -> list:
    """A drive of `length_m` along the lanes from the lane point nearest `start`: at each end
    on into the linked lane that turns least (lanes, then connectors through junctions),
    never a lane twice."""
    best = None
    for i, kind in enumerate(g["kinds"]):
        if kind != "lane":
            continue
        ln = _line(g, i)
        d, k = min(((p[0] - start[0]) ** 2 + (p[1] - start[1]) ** 2, k)
                   for k, p in enumerate(ln))
        if best is None or (d, i) < best[:2]:
            best = (d, i, k)
    if best is None:
        return []
    _, cur, k = best
    path = _line(g, cur)[k:]
    seen = {cur}
    while _length(path) < length_m and len(path) >= 2:
        hx, hy = path[-1][0] - path[-2][0], path[-1][1] - path[-2][1]
        links = g["links"][g["link_start"][cur]:g["link_start"][cur + 1]]
        cands = []
        for j in links:
            if j in seen:
                continue
            lj = _line(g, j)
            if len(lj) < 2 or math.dist(lj[0][:2], path[-1][:2]) > 3.0:
                continue
            dx, dy = lj[1][0] - lj[0][0], lj[1][1] - lj[0][1]
            turn = abs(math.atan2(hx * dy - hy * dx, hx * dx + hy * dy))
            cands.append((round(turn, 6), j, lj))
        if not cands:
            break
        _, cur, lj = min(cands)
        seen.add(cur)
        path += lj[1:]
    return _cut(path, length_m)


def _thin(path: list, step_m: float = 2.0) -> list:
    """Points closer than `step_m` to the last kept one dropped (the last always kept)."""
    out = path[:1]
    for p in path[1:-1]:
        if math.dist(p[:2], out[-1][:2]) >= step_m:
            out.append(p)
    if len(path) > 1:
        out.append(path[-1])
    return out


def route(build: str | Path, man: dict | None = None) -> dict:
    """The benchmark's route through the city of `build` (its imported manifest and graphs):
    segments in citygen meters, z the eye's absolute height."""
    build = Path(build)
    out = build / "unreal"
    man = man or json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    graphs = json.loads((out / "graphs.json").read_text(encoding="utf-8"))
    walks, lanes = graphs["walkways"], graphs["lanes"]
    s2 = man.get("stage2") or {}
    by = {}
    for a in s2.get("actors", []):
        if a.get("district"):
            by.setdefault(a["district"], []).append(a["pivot"])
    if not by:
        for t in man["tiles"]:
            for o in t["objects"]:
                if o.get("district"):
                    b = t["bounds"]
                    by.setdefault(o["district"], []).append(
                        [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0, 0.0])
    order = sorted(by, key=lambda d: (-len(by[d]), d))[:WALK_DISTRICTS]
    segs = []
    for d in order:
        ps = by[d]
        cx = sum(p[0] for p in ps) / len(ps)
        cy = sum(p[1] for p in ps) / len(ps)
        mid = min(ps, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[0], p[1]))
        path = _thin(_walk(walks, (mid[0], mid[1]), WALK_M))
        if len(path) >= 2:
            segs.append({"name": f"walk_{d}", "group": "walk", "kind": "path",
                         "speed_m_s": WALK_SPEED, "pitch_deg": 0.0,
                         "points": [[round(x, 2), round(y, 2), round(z + EYE_M, 2)]
                                    for x, y, z in path]})
    x0, y0, x1, y1 = man["bounds"]
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    drive = _thin(_drive(lanes, (cx, cy), DRIVE_M), 4.0)
    if len(drive) >= 2:
        segs.append({"name": "drive", "group": "drive", "kind": "path",
                     "speed_m_s": DRIVE_SPEED, "pitch_deg": DRIVE_PITCH,
                     "points": [[round(x, 2), round(y, 2), round(z + DRIVE_EYE_M, 2)]
                                for x, y, z in drive]})
    # the flight: the diagonal of the stage 2 buildings' middle 90% (else the bounds)
    xs = sorted(a["pivot"][0] for a in s2.get("actors", []) if a.get("category") == "building")
    ys = sorted(a["pivot"][1] for a in s2.get("actors", []) if a.get("category") == "building")
    if len(xs) >= 20:
        q = lambda v, f: v[int(f * (len(v) - 1))]     # noqa: E731
        bx0, bx1, by0, by1 = q(xs, 0.05), q(xs, 0.95), q(ys, 0.05), q(ys, 0.95)
    else:
        bx0, by0, bx1, by1 = x0 + 200, y0 + 200, x1 - 200, y1 - 200
    a, b = (bx0, by0), (bx1, by1)
    length = math.dist(a, b)
    if length > FLY_MAX_M:
        mx, my, f = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, FLY_MAX_M / length / 2.0
        a = (mx - (b[0] - a[0]) * f, my - (b[1] - a[1]) * f)
        b = (mx + (b[0] - a[0]) * f, my + (b[1] - a[1]) * f)
    segs.append({"name": "fly_150m", "group": "fly", "kind": "path", "speed_m_s": FLY_SPEED,
                 "pitch_deg": FLY_PITCH,
                 "points": [[round(a[0], 2), round(a[1], 2), FLY_Z_M],
                            [round(b[0], 2), round(b[1], 2), FLY_Z_M]]})
    # the teleport: from the flight's end back to the first walk's start, on foot
    if segs and segs[0]["group"] == "walk":
        p = segs[0]["points"][0]
        segs.append({"name": "teleport", "group": "teleport", "kind": "teleport",
                     "hold_s": HOLD_S, "pitch_deg": 0.0, "points": [p]})
    return {"version": ROUTE_VERSION, "city": man["city"], "districts": order,
            "segments": segs}


def job(route_: dict, out_dir: Path, passes=PASSES, warm: bool = True,
        csv_name: str = "profile.csv") -> dict:
    """The game process's job: the route, the passes (a warm-up pass first: the route's
    first segments by day, recorded and left out), the console commands."""
    ps = [{"name": n, "night": night, "screen_percentage": sp} for n, night, sp in passes]
    if warm:
        ps.insert(0, {"name": "warm", "night": False, "screen_percentage": 100.0,
                      "warm": True})
    return {"out_dir": str(out_dir).replace("\\", "/"), "csv_name": csv_name,
            "commands": list(COMMANDS), "settle_s": 1.5, "load_timeout_s": 120.0,
            "load_radius_m": LOAD_RADIUS_M, "stream_radius_m": STREAM_RADIUS_M,
            "start_wait_s": 10.0, "stream_every": 5, "memory_every": 15,
            "passes": ps, "segments": route_["segments"]}


# --- running it ---------------------------------------------------------------------------

def busy() -> list[str]:
    """Heavy processes that would skew a benchmark (another build, test run, Blender or
    Unreal editor), as `name pid` strings; Windows only (else nothing)."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId)`t$($_.Name)`t$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    hits = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        pid, name, cmd = parts
        low = (name + " " + cmd).lower()
        if int(pid) == os.getpid():
            continue
        if ("unrealeditor" in name.lower() or "blender" in name.lower() or
                ("python" in name.lower() and re.search(r"citygen (build|sweep)|assetgen|pytest",
                                                         low))):
            hits.append(f"{name} {pid}")
    return hits


def run_game(root: Path, uproject: Path, level: str, job_path: Path, log: Path,
             resolution=RESOLUTION, timeout: float = 3600.0) -> int:
    """The standalone game on `level` with the bench's job; its exit code."""
    from .unreal import editor_binary
    exe = editor_binary(root, gui=True)
    cmd = [str(exe), str(uproject), level, "-game", "-windowed",
           f"-ResX={resolution[0]}", f"-ResY={resolution[1]}", "-WinX=0", "-WinY=0",
           f"-CityGenBench={job_path.as_posix()}", "-csvGpuStats", "-NoSound", "-nosplash",
           "-unattended", "-NoLoadingScreen", "-stdout", "-FullStdOutLogOutput",
           "-NoScreenMessages"]
    with open(log, "wb") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise


def bench(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
          runs: int = 3, passes=PASSES, label: str = "bench", out: str | Path | None = None,
          resolution=RESOLUTION, wait_idle: bool = True, timeout: float = 3600.0,
          say=print) -> dict:
    """`citygen unreal --bench`: `runs` game processes over the route, each run's raw frames
    kept in BUILD/unreal/bench/<label>/run<k>, the results (`combine`) written to `out`
    (default docs/progress/AG16/bench/<city>/<label>)."""
    from .unreal import find_engine
    build = Path(build_dir).resolve()
    up = Path(uproject).resolve()
    root = find_engine(engine)
    if root is None:
        raise RuntimeError("no Unreal Engine found (pass --engine or set CITYGEN_UE_ROOT)")
    man = json.loads((build / "unreal" / "manifest.json").read_text(encoding="utf-8"))
    level = f"{man['content_root']}/Maps/{man['folder']}"
    rt = route(build, man)
    raw = build / "unreal" / "bench" / label
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "route.json").write_text(json.dumps(rt, indent=1) + "\n", encoding="utf-8",
                                    newline="\n")
    results = []
    for k in range(runs):
        if wait_idle:
            t = time.time()
            while busy():
                if time.time() - t > 6 * 3600:
                    raise RuntimeError("other heavy processes kept running: "
                                       + ", ".join(busy()))
                say(f"bench: waiting for {', '.join(busy())}")
                time.sleep(180)
        rd = raw / f"run{k + 1}"
        if rd.exists():
            shutil.rmtree(rd)
        rd.mkdir(parents=True)
        jb = job(rt, rd, passes)
        jp = rd / "job.json"
        jp.write_text(json.dumps(jb, indent=1) + "\n", encoding="utf-8", newline="\n")
        say(f"bench: run {k + 1} of {runs} ({len(jb['passes'])} passes, "
            f"{len(rt['segments'])} segments)")
        t = time.time()
        code = run_game(root, up, level, jp, rd / "game_log.txt", resolution, timeout)
        if not (rd / "frames.csv").is_file():
            raise RuntimeError(f"run {k + 1}: the game wrote no frames (exit {code}); "
                               f"log {rd / 'game_log.txt'}")
        res = summarize(rd, rt)
        res["exit_code"], res["wall_s"] = code, round(time.time() - t, 1)
        (rd / "summary.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8",
                                         newline="\n")
        results.append(res)
        say(f"bench: run {k + 1}: " + "; ".join(
            f"{p['name']} p95 {p['all']['frame_ms']['p95']:.1f} ms"
            for p in res["passes"]))
    comb = combine(results, rt, label, resolution)
    dest = Path(out) if out else (Path(__file__).resolve().parent.parent / "docs" / "progress"
                                  / "AG16" / "bench" / man["slug"] / label)
    write_results(comb, dest, [raw / f"run{k + 1}" for k in range(runs)])
    comb["out"] = str(dest)
    return comb


# --- reading the results --------------------------------------------------------------------

def _pct(v: list[float], q: float) -> float:
    if not v:
        return float("nan")
    s = sorted(v)
    k = (len(s) - 1) * q
    lo = int(math.floor(k))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _stats(v: list[float]) -> dict:
    return {"p50": round(_pct(v, 0.5), 2), "p95": round(_pct(v, 0.95), 2),
            "p99": round(_pct(v, 0.99), 2), "max": round(max(v), 2) if v else None,
            "mean": round(sum(v) / len(v), 2) if v else None}


def read_frames(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]


def read_profile(rd: Path) -> dict | None:
    """The engine's CSV profile of a run: per frame its columns and the bench's events
    (`cg:<pass>:<seg>`), split into the route's frames (pass, segment) by those events."""
    files = sorted(rd.glob("*.csv"))
    files = [f for f in files if f.name != "frames.csv"]
    if not files:
        return None
    with open(files[-1], encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return None
    head = rows[0]
    ev = head.index("EVENTS") if "EVENTS" in head else None
    cur, out = None, {}
    for r in rows[1:]:
        if not r or r[0].startswith("[") or r[0] == head[0]:
            break
        if ev is not None and ev < len(r) and r[ev]:
            for e in r[ev].split(";"):
                m = re.match(r"cg:(\d+):(\d+)", e.strip())
                if m:
                    cur = (int(m.group(1)), int(m.group(2)))
        if cur is None:
            continue
        vals = {}
        for i, h in enumerate(head):
            if i < len(r) and i != ev:
                try:
                    vals[h] = float(r[i])
                except ValueError:
                    pass
        out.setdefault(cur, []).append(vals)
    return {"columns": head, "frames": out}


def summarize(rd: Path, rt: dict) -> dict:
    """One run's results: per pass (the warm-up left out), the route's moving frames
    (phase 2) per group (walk, drive, fly) and in all, the teleport's frames (phase 3), the
    loads; the CSV profile's Nanite root pages and the GPU's costliest passes."""
    frames = read_frames(rd / "frames.csv")
    info = json.loads((rd / "bench_events.json").read_text(encoding="utf-8"))
    prof = read_profile(rd)
    segs = rt["segments"]
    passes = [e for e in info["events"] if e.get("op") == "pass"]
    loads = {}
    for e in info["events"]:
        if e.get("op") == "loaded":
            loads.setdefault(e["pass"], []).append(
                {"segment": segs[e["seg"]]["name"], "seconds": round(e["seconds"], 2),
                 "timeout": e["timeout"]})
    res = {"viewport": info.get("viewport"), "adapter": info.get("adapter"),
           "rhi": info.get("rhi"), "scalability": info.get("scalability"),
           "nanite_max_root_pages": info.get("nanite_max_root_pages"), "passes": []}
    for p in passes:
        if p.get("warm"):
            continue
        pi = p["pass"]
        fp = [f for f in frames if int(f["pass"]) == pi]
        entry = {"name": p["name"], "night": p["night"],
                 "screen_percentage": p["screen_percentage"]}
        for g in GROUPS:
            ids = {i for i, s in enumerate(segs) if s["group"] == g}
            phase = 3 if g == "teleport" else 2
            fs = [f for f in fp if int(f["seg"]) in ids and int(f["phase"]) == phase]
            entry[g] = _group(fs, prof, pi, ids)
        moving = [f for f in fp if int(f["phase"]) == 2]
        entry["all"] = _group(moving, prof, pi, {i for i, s in enumerate(segs)
                                                 if s["kind"] == "path"})
        entry["loads"] = loads.get(pi, [])
        entry["load_s"] = round(sum(x["seconds"] for x in entry["loads"]), 2)
        allf = fp
        entry["hitches_any_phase"] = sum(1 for f in allf if f["frame_ms"] > HITCH_MS)
        entry["max_frame_any_phase_ms"] = round(max((f["frame_ms"] for f in allf),
                                                    default=0.0), 1)
        res["passes"].append(entry)
    return res


def _group(fs: list[dict], prof: dict | None, pi: int, ids: set) -> dict:
    if not fs:
        return {"frames": 0}
    ft = [f["frame_ms"] for f in fs]
    out = {"frames": len(fs), "seconds": round(sum(ft) / 1000.0, 1),
           "frame_ms": _stats(ft),
           "game_ms": _stats([f["game_ms"] for f in fs]),
           "render_ms": _stats([f["render_ms"] for f in fs]),
           "rhi_ms": _stats([f["rhi_ms"] for f in fs]),
           "gpu_ms": _stats([f["gpu_ms"] for f in fs]),
           "draws": _stats([f["draws"] for f in fs]),
           "prims": _stats([f["prims"] for f in fs]),
           "hitches": sum(1 for x in ft if x > HITCH_MS),
           "big_hitches": sum(1 for x in ft if x > BIG_HITCH_MS)}
    st = [f["streamed"] for f in fs if f["streamed"] >= 0]
    out["unstreamed_share"] = round(1.0 - sum(st) / len(st), 4) if st else None
    out["slow_streaming_frames"] = sum(1 for f in fs if f["perf"] >= 1)
    vr = [f["vram_mb"] for f in fs if f["vram_mb"] >= 0]
    rm = [f["ram_mb"] for f in fs if f["ram_mb"] >= 0]
    out["vram_mb_max"] = round(max(vr)) if vr else None
    out["ram_mb_max"] = round(max(rm)) if rm else None
    # the thread that sets the frame at its 95th percentile
    lim = {"game": out["game_ms"]["p95"], "render": out["render_ms"]["p95"],
           "rhi": out["rhi_ms"]["p95"], "gpu": out["gpu_ms"]["p95"]}
    out["bound_by"] = max(lim, key=lambda k: lim[k])
    if prof:
        rows = [r for s in ids for r in prof["frames"].get((pi, s), [])]
        root = [r["NaniteStreaming/RootAllocationMB"] for r in rows
                if "NaniteStreaming/RootAllocationMB" in r]
        if root:
            out["nanite_root_pages_max"] = int(round(max(root) / ROOT_PAGE_MB))
        gpu = {}
        for r in rows:
            for k, v in r.items():
                if k.startswith("GPU/") and k != "GPU/Total":
                    gpu.setdefault(k[4:], []).append(v)
        if gpu:
            out["gpu_passes_ms"] = {k: round(sum(v) / len(rows), 2) for k, v in sorted(
                gpu.items(), key=lambda kv: -sum(kv[1]))[:12]}
    return out


def combine(results: list[dict], rt: dict, label: str, resolution) -> dict:
    """The runs together: per pass and group the median of the runs' figures and their
    spread (min and max over the runs, the variance's measure)."""
    first = results[0]
    out = {"label": label, "city": rt["city"], "route_version": rt["version"],
           "districts": rt["districts"], "resolution": list(resolution),
           "runs": len(results), "viewport": first.get("viewport"),
           "adapter": first.get("adapter"), "rhi": first.get("rhi"),
           "scalability": first.get("scalability"),
           "nanite_max_root_pages": first.get("nanite_max_root_pages"),
           "segments": [{"name": s["name"], "group": s["group"],
                         "length_m": round(_length(s["points"]), 1) if s["kind"] == "path"
                         else 0.0} for s in rt["segments"]],
           "passes": []}
    for i, p in enumerate(first["passes"]):
        ent = {"name": p["name"], "night": p["night"],
               "screen_percentage": p["screen_percentage"]}
        for g in GROUPS + ("all",):
            runs = [r["passes"][i][g] for r in results if r["passes"][i][g].get("frames")]
            if not runs:
                ent[g] = {"frames": 0}
                continue
            ent[g] = _median_of(runs)
        ent["load_s"] = _spread([r["passes"][i]["load_s"] for r in results])
        ent["hitches_any_phase"] = _spread([r["passes"][i]["hitches_any_phase"]
                                            for r in results])
        ent["max_frame_any_phase_ms"] = _spread([r["passes"][i]["max_frame_any_phase_ms"]
                                                 for r in results])
        out["passes"].append(ent)
    out["targets"] = verdict(out)
    return out


def _spread(v: list[float]) -> dict:
    return {"median": round(statistics.median(v), 2), "min": round(min(v), 2),
            "max": round(max(v), 2)}


def _median_of(runs: list[dict]) -> dict:
    out = {"frames": int(statistics.median(r["frames"] for r in runs))}
    for k in ("frame_ms", "game_ms", "render_ms", "rhi_ms", "gpu_ms", "draws", "prims"):
        out[k] = {q: round(statistics.median(r[k][q] for r in runs), 2)
                  for q in ("p50", "p95", "p99", "max", "mean")}
    out["frame_ms_p95_spread"] = _spread([r["frame_ms"]["p95"] for r in runs])
    out["frame_ms_p50_spread"] = _spread([r["frame_ms"]["p50"] for r in runs])
    for k in ("hitches", "big_hitches", "slow_streaming_frames"):
        out[k] = _spread([r[k] for r in runs])
    for k in ("unstreamed_share", "vram_mb_max", "ram_mb_max", "nanite_root_pages_max"):
        v = [r[k] for r in runs if r.get(k) is not None]
        out[k] = round(statistics.median(v), 4) if v else None
    out["bound_by"] = statistics.mode(r["bound_by"] for r in runs)
    gp = [r["gpu_passes_ms"] for r in runs if r.get("gpu_passes_ms")]
    if gp:
        keys = sorted({k for g in gp for k in g})
        med = {k: round(statistics.median(g.get(k, 0.0) for g in gp), 2) for k in keys}
        out["gpu_passes_ms"] = dict(sorted(med.items(), key=lambda kv: -kv[1])[:12])
    return out


def verdict(res: dict) -> dict:
    """The targets (Swagnik, 2026-11-05): p95 of the moving frames at most 16.7 ms (else
    25 ms) walking, driving and flying in every pass at the lower screen percentage (native
    reported beside it); no hitch over 100 ms; under 10 GB of VRAM."""
    out = {"p95_60fps": [], "p95_40fps": [], "big_hitches": [], "vram": []}
    for p in res["passes"]:
        for g in ("walk", "drive", "fly"):
            e = p.get(g) or {}
            if not e.get("frames"):
                continue
            p95 = e["frame_ms"]["p95"]
            tag = f"{p['name']}/{g}"
            if p95 > TARGET_MS:
                out["p95_60fps"].append(f"{tag} {p95:.1f} ms")
            if p95 > FLOOR_MS:
                out["p95_40fps"].append(f"{tag} {p95:.1f} ms")
            if e["big_hitches"]["max"] > 0:
                out["big_hitches"].append(f"{tag} {e['big_hitches']['median']:g}")
            if (e.get("vram_mb_max") or 0) > VRAM_MB:
                out["vram"].append(f"{tag} {e['vram_mb_max']:.0f} MB")
    return out


def table(res: dict) -> str:
    """The results as a Markdown table: a row per pass and part of the route."""
    lines = [f"**{res['city']}**, {res['label']}: {res['runs']} runs at "
             f"{res['resolution'][0]}x{res['resolution'][1]} ({res.get('adapter') or ''}, "
             f"{res.get('rhi') or ''}); frame times in ms, median of the runs (p95's spread "
             "min to max)",
             "",
             "| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 "
             "| GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB "
             "| RAM MB | root pages |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in res["passes"]:
        for g in ("walk", "drive", "fly", "teleport", "all"):
            e = p.get(g) or {}
            if not e.get("frames"):
                continue
            f, s = e["frame_ms"], e["frame_ms_p95_spread"]
            us = e.get("unstreamed_share")
            lines.append(
                f"| {p['name']} | {g} | {e['frames']} | {f['p50']:.1f} | {f['p95']:.1f} "
                f"({s['min']:.1f} to {s['max']:.1f}) | {f['p99']:.1f} | {f['max']:.0f} | "
                f"{e['game_ms']['p95']:.1f} | {e['render_ms']['p95']:.1f} | "
                f"{e['gpu_ms']['p95']:.1f} | {e['bound_by']} | {e['draws']['p50']:.0f} | "
                f"{e['hitches']['median']:g} / {e['big_hitches']['median']:g} | "
                f"{'' if us is None else f'{100 * us:.1f}%'} | "
                f"{e.get('vram_mb_max') or ''} | {e.get('ram_mb_max') or ''} | "
                f"{e.get('nanite_root_pages_max') or ''} |")
    lines += ["", "Loads (s, after each teleport onto a segment's start, all segments): "
              + "; ".join(f"{p['name']} {p['load_s']['median']:g}" for p in res["passes"])]
    t = res["targets"]
    lines += ["", "Targets: 60 fps (p95 16.7 ms) missed by: "
              + (", ".join(t["p95_60fps"]) or "none")
              + "; 40 fps (25 ms) missed by: " + (", ".join(t["p95_40fps"]) or "none")
              + "; hitches over 100 ms: " + (", ".join(t["big_hitches"]) or "none")
              + "; VRAM over 10 GB: " + (", ".join(t["vram"]) or "none")]
    return "\n".join(lines) + "\n"


def write_results(res: dict, dest: Path, run_dirs: list[Path]) -> None:
    """bench.json and bench.md, and a frame-time graph along the route per pass of the first
    run (frame_times_<pass>.png)."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "bench.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8",
                                     newline="\n")
    (dest / "bench.md").write_text(table(res), encoding="utf-8", newline="\n")
    try:
        graphs(run_dirs[0], dest, res)
    except Exception as e:          # noqa: BLE001 (a graph is not worth failing the run)
        (dest / "graph_error.txt").write_text(str(e) + "\n", encoding="utf-8")


def graphs(rd: Path, dest: Path, res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    frames = read_frames(rd / "frames.csv")
    info = json.loads((rd / "bench_events.json").read_text(encoding="utf-8"))
    names = {e["pass"]: e["name"] for e in info["events"] if e.get("op") == "pass"}
    segs = res["segments"]
    for pi, name in names.items():
        if name == "warm":
            continue
        fs = [f for f in frames if int(f["pass"]) == pi and int(f["phase"]) in (2, 3)]
        if not fs:
            continue
        fig, ax = plt.subplots(figsize=(14, 4), dpi=110)
        t = list(range(len(fs)))
        ax.plot(t, [f["frame_ms"] for f in fs], lw=0.6, color="#1f5aa6", label="frame")
        ax.plot(t, [f["gpu_ms"] for f in fs], lw=0.5, color="#c2410c", alpha=0.7, label="GPU")
        ax.plot(t, [f["game_ms"] for f in fs], lw=0.5, color="#15803d", alpha=0.7,
                label="game")
        ax.axhline(TARGET_MS, color="#555", ls="--", lw=0.8)
        ax.axhline(FLOOR_MS, color="#999", ls=":", lw=0.8)
        last = None
        for k, f in enumerate(fs):
            if int(f["seg"]) != last:
                last = int(f["seg"])
                ax.axvline(k, color="#ccc", lw=0.6)
                ax.text(k, ax.get_ylim()[1] * 0.98, segs[last]["name"], fontsize=7,
                        va="top", ha="left", color="#444")
        ax.set_ylim(0, max(60.0, min(150.0, _pct([f["frame_ms"] for f in fs], 0.999) * 1.2)))
        ax.set_xlabel("frame along the route")
        ax.set_ylabel("ms")
        ax.set_title(f"{res['city']} {res['label']}: {name}")
        ax.legend(loc="upper right", fontsize=7)
        fig.tight_layout()
        fig.savefig(dest / f"frame_times_{name}.png")
        plt.close(fig)
