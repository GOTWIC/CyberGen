"""Quick profiles at fixed viewpoints (delta_rebuild): the standalone game (as the benchmark
runs it, `citygen.bench.run_game`'s command line) with an Unreal Insights trace, a job of
viewpoints held still (a path of 3 m at 0.1 m/s, 30 s), each first settled for 10 s, every
viewpoint measured under each pass named (the benchmark's own commands, `bench.ATMOS_PASSES`)
as a trace region `<pass>__<view>`; then Unreal Insights exports the game thread's timer
statistics per region (`<out>/stats/<pass>__<view>.csv`) and the job's events (load times).

    python profile.py BUILD UPROJECT OUT --engine DIR --views views.json --passes a,b

views.json: [{"name": ..., "eye": [x, y, z], "target": [x, y]}] in citygen meters (z the
eye's height over the datum)."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from citygen import bench as B          # noqa: E402

SETTLE_S = 10.0
HOLD_S = 30.0
CREEP_M = 3.0


def segments(views: list[dict], passes: list[str]) -> tuple[list[dict], dict[str, list[int]]]:
    segs, only = [], {}
    for p in passes:
        only[p] = []
        for v in views:
            (x, y, z), (tx, ty) = v["eye"], v["target"][:2]
            d = math.hypot(tx - x, ty - y) or 1.0
            ux, uy = (tx - x) / d, (ty - y) / d
            a = [round(x, 2), round(y, 2), round(z, 2)]
            b = [round(x + ux * CREEP_M, 2), round(y + uy * CREEP_M, 2), round(z, 2)]
            name = f"{p}__{v['name']}"
            only[p] += [len(segs), len(segs) + 1]
            segs.append({"name": f"settle__{name}", "group": "walk", "kind": "path",
                         "speed_m_s": CREEP_M / SETTLE_S, "pitch_deg": v.get("pitch", 0.0),
                         "points": [a, b], "commands": ["CityGenAtmos.Sight 1"]})
            segs.append({"name": name, "group": "walk", "kind": "path",
                         "speed_m_s": 0.001, "pitch_deg": v.get("pitch", 0.0),
                         "points": [b, [b[0] + ux * 0.001 * HOLD_S, b[1] + uy * 0.001 * HOLD_S, b[2]]],
                         "commands": ["CityGenAtmos.Sight 1", f"Trace.RegionBegin {name}"]})
    # (each settle segment ends the region before it)
    prev = None
    for s in segs:
        if s["name"].startswith("settle__") and prev:
            s["commands"].insert(0, f"Trace.RegionEnd {prev}")
        if not s["name"].startswith("settle__"):
            prev = s["name"]
    return segs, only


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build")
    ap.add_argument("uproject")
    ap.add_argument("out")
    ap.add_argument("--engine", required=True)
    ap.add_argument("--views", required=True)
    ap.add_argument("--passes", default="night_plan_all,night_life_noplaces")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    views = json.loads(Path(a.views).read_text(encoding="utf-8"))
    names = [n.strip() for n in a.passes.split(",") if n.strip()]
    allp = {p[0]: p for p in B.PASSES + B.ATMOS_PASSES}
    passes = [allp[n] for n in names]
    segs, only = segments(views, names)
    route = {"version": B.ROUTE_VERSION, "city": "", "segments": segs}
    job = B.job(route, out, passes=passes, warm=False)
    job["segments"] = segs                  # (our own commands per segment)
    for p in job["passes"]:
        p["segments"] = only[p["name"]]
    # (the last region ended by a closing segment of nothing: the pass's end ends the run)
    jp = out / "job.json"
    jp.write_text(json.dumps(job, indent=1), encoding="utf-8")
    man = json.loads((Path(a.build) / "unreal" / "manifest.json").read_text(encoding="utf-8"))
    from citygen.unreal import editor_binary, find_engine
    eng = find_engine(a.engine)
    exe = editor_binary(eng, gui=True)
    level = f"{man['content_root']}/Maps/{man['folder']}"
    trace = out / "profile.utrace"
    ini = ("[/Script/Engine.UserInterfaceSettings]:bAllowHighDPIInGameMode=True,"
           "[/Script/Engine.UserInterfaceSettings]:bAllowHighDpiWhenUnattended=True")
    cmd = [str(exe), str(Path(a.uproject)), level, "-game", "-windowed",
           f"-ResX={B.RESOLUTION[0]}", f"-ResY={B.RESOLUTION[1]}", "-WinX=0", "-WinY=0",
           f"-CityGenBench={jp.as_posix()}", "-NoSound", "-nosplash", "-unattended",
           "-NoLoadingScreen", "-stdout", "-FullStdOutLogOutput", f"-ini:Engine:{ini}",
           "-NoScreenMessages", "-trace=cpu,frame,bookmark,region,loadtime", "-statnamedevents",
           f"-tracefile={trace.as_posix()}"]
    t0 = time.time()
    with open(out / "game.log", "wb") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        B.unthrottle(proc.pid)
        rc = proc.wait(timeout=3600)
    print(f"game exit {rc} in {time.time() - t0:.0f} s; trace {trace}")
    (out / "stats").mkdir(exist_ok=True)
    rsp = out / "export.rsp"
    rsp.write_text(
        f"TimingInsights.ExportTimerStatistics {(out / 'stats').as_posix()}/{{region}}.csv "
        f"-threads=GameThread -region=night_* -sortBy=TotalInclusiveTime -sortOrder=Descending\n",
        encoding="utf-8")
    ins = eng / "Engine" / "Binaries" / "Win64" / "UnrealInsights.exe"
    r = subprocess.run([str(ins), f"-OpenTraceFile={trace}", "-NoUI", "-AutoQuit",
                        f"-ExecOnAnalysisCompleteCmd=@={rsp}", "-log"],
                       capture_output=True, text=True, timeout=3600)
    print("insights exit", r.returncode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
