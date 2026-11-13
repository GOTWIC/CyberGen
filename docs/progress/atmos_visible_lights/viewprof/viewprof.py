"""Visible lights: quick GPU profiles at fixed viewpoints (not a route run). One standalone
game at 2560 x 1440 by night (the night_plan_all pass), each viewpoint a short slow walk
(3 m at 0.5 m/s, facing its target) twice: by the circle (CityGenAtmos.Sight 0) and by sight
(1). Per segment the frame and GPU times' median and p95 and the atmos status near its end.

python viewprof.py WORKTREE OUT_DIR [extra live sizes...]"""
import csv
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from citygen import bench as B  # noqa: E402
from citygen.unreal import find_engine  # noqa: E402

BUILD = Path("C:/Users/swagn/CityGen/builds/fix_play_cars/samples/delta_megacity")
UP = Path("C:/Users/swagn/CityGen/UnrealProjects/CityAG16/CityAG16.uproject")
VIEWS = {   # name: eye (citygen m, z the eye), target
    "oldtown": ((-1232.2, 1384.0, 1.7), (-1632.0, 1366.6, 4.0)),
    "core": ((687.8, -99.1, 1.7), (970.9, 183.5, 8.0)),
    "midtown": ((543.3, 1576.0, 1.7), (943.3, 1576.0, 6.0)),
    "avenue": ((-368.0, 1576.0, 1.7), (-768.0, 1576.0, 6.0)),
    "start": ((-104.72, -11.57, 1.7), (95.3, -14.9, 1.7)),
}
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
modes = [("circle", ["CityGenAtmos.Sight 0"]), ("sight", ["CityGenAtmos.Sight 1"])]
for extra in sys.argv[3:]:
    n, r = extra.split(":")
    modes.append((f"sight{n}_{r}", ["CityGenAtmos.Sight 1", f"CityGenAtmos.SightRange {r} {n}"]))
segs = []
for name, (eye, tg) in VIEWS.items():
    dx, dy = tg[0] - eye[0], tg[1] - eye[1]
    L = math.hypot(dx, dy)
    p1 = (eye[0] + 3.0 * dx / L, eye[1] + 3.0 * dy / L, eye[2])
    for mode, cmds in modes:
        segs.append({"name": f"{name}_{mode}", "group": "walk", "kind": "path",
                     "speed_m_s": 0.5, "pitch_deg": math.degrees(math.atan2(tg[2] - eye[2], L)),
                     "points": [list(eye), list(p1)], "commands": cmds})
rt = {"version": "viewprof", "city": "Delta Megacity", "lean": True, "segments": segs}
want = [p for p in B.ATMOS_PASSES if p[0] == "night_plan_all"]
jb = B.job(rt, out, want, warm=True, shots=True)
jb["segments"] = segs           # (their own modes, not the group's)
jp = out / "job.json"
jp.write_text(json.dumps(jb, indent=1) + "\n", encoding="utf-8")
man = json.loads((BUILD / "unreal" / "manifest.json").read_text(encoding="utf-8"))
level = f"{man['content_root']}/Maps/{man['folder']}"
while B.busy():
    print("waiting for", B.busy(), flush=True)
    import time
    time.sleep(120)
root = find_engine("C:/Games/UE_5.8")
samples = []
code = B.run_game(root, UP, level, jp, out / "game_log.txt", B.RESOLUTION, 1800.0, samples=samples)
print("exit", code, flush=True)
rows = list(csv.DictReader(open(out / "frames.csv", encoding="utf-8")))
res = {}
for si, s in enumerate(segs):
    fs = [r for r in rows if int(r["seg"]) == si and r["phase"] == "2"
          and int(r["pass"]) == len(jb["passes"]) - 1]
    if not fs:
        continue
    fr = sorted(float(r["frame_ms"]) for r in fs)
    gp = sorted(float(r["gpu_ms"]) for r in fs)
    q = lambda v, f: v[min(len(v) - 1, int(f * len(v)))]  # noqa: E731
    res[s["name"]] = {"frames": len(fs), "frame_p50": round(statistics.median(fr), 2),
                      "frame_p95": round(q(fr, 0.95), 2), "gpu_p50": round(statistics.median(gp), 2),
                      "gpu_p95": round(q(gp, 0.95), 2),
                      "draws": round(statistics.median(float(r["draws"]) for r in fs))}
# the atmos status lines the segments' starts logged
log = (out / "game_log.txt").read_text(encoding="utf-8", errors="replace")
st = [json.loads(ln.split("CITYGEN_ATMOS_STATUS ", 1)[1]) for ln in log.splitlines()
      if "CITYGEN_ATMOS_STATUS " in ln]
(out / "statuses.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
(out / "viewprof.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
