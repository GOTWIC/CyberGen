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
# AT0 and AT1 (atmosgen, docs/progress/AT0, AT1): passes that switch atmosgen's runtime
# (CityGenAtmos, the controller the import places with the city's atmos plan since AT1) by
# console commands at their start, with `--bench-atmos`: the plan's lights with a live set by
# tier (the play features' light pools past it), volumetric fog, rain and wet streets,
# MegaLights (with `--bench-rt`). A pass without commands of its own switches all of it off,
# so passes do not leak into each other.
ATMOS_OFF = ("CityGenAtmos.Lights 0", "CityGenAtmos.Fog 0", "CityGenAtmos.Rain 0",
             "CityGenAtmos.Wet 0", "CityGenAtmos.MegaLights 0", "CityGenAtmos.Sky 1",
             "CityGenAtmos.Air 0", "CityGenAtmos.Tuned 0", "CityGenAtmos.Post 0",
             "CityGenAtmos.Far 0")
# AT4: the engine settings the exploring passes (`x_*`) set themselves, each pass all of them
# (so none leaks into the next): the volumetric fog's froxels (pixels a side, slices deep),
# Lumen's reflections' resolution, the non-Nanite meshes' LOD distances (the parked cars)
TUNABLE = ("r.VolumetricFog.GridPixelSize", "r.VolumetricFog.GridSizeZ",
           "r.Lumen.Reflections.DownsampleFactor", "r.StaticMeshLODDistanceScale")
UNTUNED = ("8", "128", "1", "1")


def _atmos(lights: bool = True, fog: bool = False, rain: bool = False, wet: bool = False,
           mega: bool = False, live: int = 512, range_m: float = 300.0,
           shadowed: int = 16, hour: str = "23", sky: bool = True, air: bool = False,
           tuned: bool = True, cvars: tuple | None = None,
           weather: str | None = None, post: bool = True,
           far: bool = True, dlss: bool = False, fg: bool = False) -> tuple[str, ...]:
    """AT3: `hour` a number or the plan's named hour (day, dusk, night); `sky` the sky and
    time (a game with an earlier plugin warns of the unknown command and runs the same).
    AT4: `air` the fog volumes and plumes; `tuned` the plan's engine settings (the
    controller's `RenderCVars`); `cvars` the TUNABLE values set by hand (an exploring pass:
    the plan's settings off first). AT5: `weather` a state set at once (the streets as wet
    as it leaves them, its fog the fog's; rain, neon rain's, by default, so no pass leaks its
    state into the next; a game with an earlier plugin warns of the unknown command and runs
    the same). AT6: `post` the look's post (bloom, flares, grain, fringes, the grade, local
    exposure; every pass sets it, so none leaks it into the next). AT7: `far` the far city's
    cards past the live set (off: the play features' light pools; every pass sets it).
    dlss_lamps_flicker: `dlss` NVIDIA's DLSS Super Resolution (its mode from the pass's
    screen percentage, `DLSS_PERCENT`), `fg` DLSS Frame Generation (every pass sets both; a
    game without the plugin warns of the unknown variables and runs the same)."""
    weather = weather or "rain"
    out = (f"CityGenAtmos.Tiers {live} {range_m:g} {shadowed}",
           f"CityGenAtmos.Lights {int(lights)}", f"CityGenAtmos.Fog {int(fog)}",
           f"CityGenAtmos.Rain {int(rain)}", f"CityGenAtmos.Wet {int(wet)}",
           f"CityGenAtmos.MegaLights {int(mega)}", f"CityGenAtmos.Sky {int(sky)}",
           f"CityGenAtmos.Air {int(air)}",
           f"CityGenAtmos.Tuned {int(tuned and cvars is None)}",
           f"CityGenAtmos.Weather {weather} now", f"CityGenAtmos.Post {int(post)}",
           f"CityGenAtmos.Far {int(far)}")
    if cvars is not None:
        out += tuple(f"{k} {v}" for k, v in zip(TUNABLE, cvars))
    out += (f"r.NGX.DLSS.Enable {int(dlss)}", f"r.Streamline.DLSSG.Enable {int(fg)}")
    return out + (f"CityGenAtmos.Hour {hour}",)


def _x(grid: int = 8, z: int = 128, refl: int = 1, lod: float = 1.0, **kw) -> tuple[str, ...]:
    """AT4: an exploring pass: the night with the air, rain and wet streets on and the
    TUNABLE settings set by hand."""
    a = dict(fog=True, air=True, rain=True, wet=True)
    a.update(kw)
    return _atmos(cvars=(str(grid), str(z), str(refl), f"{lod:g}"), **a)


# dlss_lamps_flicker: DLSS Super Resolution's modes by their screen percentage (the plugin picks
# the mode from it: NVIDIA's ratios, as `GetDLSSModeInformation` gives them at 1440p)
DLSS_PERCENT = {"q": 66.667, "b": 58.0, "p": 50.0}
_ALL = dict(fog=True, air=True, rain=True, wet=True)

ATMOS_PASSES = (
    ("night_plan", True, 100.0, _atmos()),
    ("night_plan_fog", True, 100.0, _atmos(fog=True)),
    ("night_plan_all", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True)),
    ("night_plan_all_tsr67", True, TSR_PERCENT, _atmos(fog=True, air=True, rain=True,
                                                       wet=True)),
    ("night_plan_1024", True, 100.0, _atmos(fog=True, rain=True, wet=True, live=1024,
                                            range_m=400.0)),
    ("night_plan_256", True, 100.0, _atmos(fog=True, rain=True, wet=True, live=256,
                                           range_m=250.0, shadowed=8)),
    ("night_play_air", True, 100.0, _atmos(lights=False, fog=True, rain=True, wet=True)),
    ("night_plan_mega", True, 100.0, _atmos(fog=True, rain=True, wet=True, mega=True)),
    ("night_plan_mega_2048", True, 100.0, _atmos(fog=True, rain=True, wet=True, mega=True,
                                                 live=2048, range_m=500.0, shadowed=0)),
    # AT3: the plan's lights at dusk (the sun just set: the plan's `dusk` hour) and by day
    # (its `day` hour: no light live), under the sky and time; and the night with the sky dome
    # hidden (what it costs)
    ("dusk_plan", True, 100.0, _atmos(hour="dusk")),
    ("dusk_plan_all", True, 100.0, _atmos(fog=True, rain=True, wet=True, hour="dusk")),
    ("day_plan", False, 100.0, _atmos(hour="day")),
    ("day_plan_all", False, 100.0, _atmos(fog=True, rain=True, wet=True, hour="day")),
    ("night_plan_nosky", True, 100.0, _atmos(sky=False)),
    # AT4: the night as delivered (the plan's lights, the height and volumetric fog, the fog
    # volumes and plumes, the plan's engine settings), with AT0's rain and wet streets too
    # (`night_plan_all` above has the air on since AT4), and by dusk and day; the night with
    # AT0's prototypes as AT3 ran it (no air, not tuned) and the night untuned
    ("night_plan_air", True, 100.0, _atmos(fog=True, air=True)),
    ("dusk_plan_air", True, 100.0, _atmos(fog=True, air=True, hour="dusk")),
    ("day_plan_air", False, 100.0, _atmos(fog=True, air=True, hour="day")),
    ("night_plan_proto", True, 100.0, _atmos(fog=True, rain=True, wet=True, tuned=False)),
    ("night_plan_all_untuned", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True,
                                                   tuned=False)),
    # AT5: the weather's states by night, each settled (`night_plan_all` is the rain: its
    # streaks, splashes and drips, the wet streets' decals with their puddles, the rain's fog):
    # drizzle (finer rain, fewer puddles), clear (the streets dry, no rain), fog and smog (no
    # rain, their thicker fog and fog volumes; the streets damp)
    ("night_plan_drizzle", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True,
                                               weather="drizzle")),
    ("night_plan_clear", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True,
                                             weather="clear")),
    ("night_plan_fogstate", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True,
                                                weather="fog")),
    ("night_plan_smog", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True,
                                            weather="smog")),
    # AT6: the look's post is on in every pass above; the night and the day without it (what
    # bloom, flares, grain, fringes, the grade and local exposure cost)
    ("night_plan_nopost", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True,
                                              post=False)),
    ("day_plan_nopost", False, 100.0, _atmos(fog=True, rain=True, wet=True, hour="day",
                                             post=False)),
    # AT7: the far city's cards are on in every pass above; the night without them (the play
    # features' light pools past the live range instead, as before AT7: what the cards cost)
    ("night_plan_nofar", True, 100.0, _atmos(fog=True, air=True, rain=True, wet=True,
                                             far=False)),
    # AT4's exploring passes: what each engine setting gives back (TUNABLE, by hand)
    ("x_base", True, 100.0, _x()),
    ("x_grid12", True, 100.0, _x(grid=12, z=96)),
    ("x_grid16", True, 100.0, _x(grid=16, z=64)),
    ("x_refl2", True, 100.0, _x(refl=2)),
    ("x_lod2", True, 100.0, _x(lod=2.0)),
    ("x_all", True, 100.0, _x(grid=12, z=96, refl=2)),
    # dlss_lamps_flicker: the night as delivered with NVIDIA's DLSS (`citygen unreal --dlss`):
    # Super Resolution at its quality, balanced and performance modes, and Frame Generation
    # over each (and over native); the output at the benchmark's resolution
) + tuple((f"night_plan_all_dlss_{m}", True, pct, _atmos(dlss=True, **_ALL))
          for m, pct in DLSS_PERCENT.items()) +     tuple((f"night_plan_all_dlss_{m}_fg", True, pct, _atmos(dlss=True, fg=True, **_ALL))
          for m, pct in DLSS_PERCENT.items()) +     (("night_plan_all_fg", True, 100.0, _atmos(fg=True, **_ALL)),)


def _life(on: bool = True, shadows: bool = True, rebuild: bool = False,
          lumen: bool = False) -> tuple[str, ...]:
    """LG0: lifegen's spike (the level's CityGenLife controller) over the night as delivered:
    on or off, the stand-ins' and cars' shadows, each frame's move recreating the instanced
    components' render state, the people and cars in Lumen's scene (every pass sets all
    four, so none leaks into the next; a game without the plugin warns of the unknown
    commands and runs the same)."""
    # (before the atmos commands, whose hour is the pass's last)
    return (f"CityGenLife.Enable {int(on)}", f"CityGenLife.Shadows {int(shadows)}",
            f"CityGenLife.Rebuild {int(rebuild)}", f"CityGenLife.Lumen {int(lumen)}") + \
        _atmos(fog=True, air=True, rain=True, wet=True)


# LG0: the spike's passes (with --bench-atmos): what the people and cars cost, by part
LIFE_PASSES = (
    ("night_life_off", True, 100.0, _life(on=False)),
    ("night_life_lumen", True, 100.0, _life(rebuild=True, lumen=True)),
    ("night_life_rebuild", True, 100.0, _life(rebuild=True)),
    ("night_life", True, 100.0, _life()),
    ("night_life_noshadow", True, 100.0, _life(shadows=False)),
)
ATMOS_PASSES = ATMOS_PASSES + LIFE_PASSES
# what a game with hardware ray tracing needs at startup (MegaLights traces its shadows; UE
# 5.8 marks MegaLights experimental), in the game's -ini override of the project's settings
RT_INI = ("[/Script/Engine.RendererSettings]:r.RayTracing=True,"
          "[/Script/Engine.RendererSettings]:r.SkinCache.CompileShaders=True")
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
# visible lights: atmosgen's live set by sight on the ground (the walks and the drive: the
# player's walker, whom the route moves through the sky as well), the circle in the air (the
# flights, the warm-up), as the fly pawn and the free camera keep it (`CityGenAtmos.Sight`)
SIGHT = {"walk": 1, "drive": 1, "teleport": 1}


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


def route(build: str | Path, man: dict | None = None, lean: bool = False) -> dict:
    """The benchmark's route through the city of `build` (its imported manifest and graphs):
    segments in citygen meters, z the eye's absolute height. `lean` (Swagnik, 2026-11-12:
    the benchmarks were too slow): the first walk, the drive and the flight, no teleport,
    and a short warm-up (`warm_fly`, the flight's first third, group `warm`, flown only by
    the warm-up passes)."""
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
    order = sorted(by, key=lambda d: (-len(by[d]), d))[:1 if lean else WALK_DISTRICTS]
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
    if lean:
        # (the warm-up's flight: the first third of the measured one)
        w = (a[0] + (b[0] - a[0]) / 3.0, a[1] + (b[1] - a[1]) / 3.0)
        segs.append({"name": "warm_fly", "group": "warm", "kind": "path",
                     "speed_m_s": FLY_SPEED, "pitch_deg": FLY_PITCH,
                     "points": [[round(a[0], 2), round(a[1], 2), FLY_Z_M],
                                [round(w[0], 2), round(w[1], 2), FLY_Z_M]]})
    # the teleport: from the flight's end back to the first walk's start, on foot
    elif segs and segs[0]["group"] == "walk":
        p = segs[0]["points"][0]
        segs.append({"name": "teleport", "group": "teleport", "kind": "teleport",
                     "hold_s": HOLD_S, "pitch_deg": 0.0, "points": [p]})
    return {"version": ROUTE_VERSION, "city": man["city"], "districts": order,
            "lean": lean, "segments": segs}


def job(route_: dict, out_dir: Path, passes=PASSES, warm: bool = True,
        csv_name: str = "profile.csv", resolution=RESOLUTION, shots: bool = False) -> dict:
    """The game process's job: the route, the passes (warm-up passes first: the flight
    across the city by day and by night, which meets most of the city's materials and
    lights, so the first measured pass does not pay for their first use alone; recorded and
    left out), the console commands."""
    atmos = any(len(p) > 3 for p in passes)
    ps = []
    for p in passes:
        n, night, sp = p[:3]
        e = {"name": n, "night": night, "screen_percentage": sp}
        if atmos:
            # (AT0: a pass of atmosgen's spike runs its commands; the rest switch it off)
            e["commands"] = list(p[3]) if len(p) > 3 else list(ATMOS_OFF)
        ps.append(e)
    fly = [i for i, s in enumerate(route_["segments"]) if s["group"] == "fly"]
    # (a lean route: the warm-up flies its own short segment, the measured passes the rest)
    short = [i for i, s in enumerate(route_["segments"]) if s["group"] == "warm"]
    if short:
        rest = [i for i, s in enumerate(route_["segments"]) if s["group"] != "warm"]
        for e in ps:
            e["segments"] = rest
        fly = short
    if warm:
        nights = sorted({p[1] for p in passes})
        ps[:0] = [{"name": f"warm_{'night' if n else 'day'}", "night": n,
                   "screen_percentage": 100.0, "warm": True, "segments": fly}
                  for n in nights]
        if atmos:
            # (the night's warm-up with all of atmosgen's spike on: its materials' and
            # lights' shaders compiled before a measured pass meets them)
            for w in ps[:len(nights)]:
                w["commands"] = (list(_atmos(fog=True, air=True, rain=True, wet=True))
                                 if w["night"] else list(ATMOS_OFF))
    return {"out_dir": str(out_dir).replace("\\", "/"), "csv_name": csv_name,
            # (windowed fullscreen at the resolution: a window of that size with its
            # borders would not fit a screen of that size)
            "commands": list(COMMANDS) + [f"r.SetRes {resolution[0]}x{resolution[1]}wf"],
            "segments": [dict(s, commands=[f"CityGenAtmos.Sight {SIGHT.get(s['group'], 0)}"])
                         if atmos else s for s in route_["segments"]],
            "settle_s": 1.5, "load_timeout_s": 120.0,
            "load_radius_m": LOAD_RADIUS_M, "stream_radius_m": STREAM_RADIUS_M,
            "start_wait_s": 10.0, "stream_every": 5, "memory_every": 15,
            # a screenshot of each segment's start once loaded (`shots/<pass>_<segment>.png`):
            # the same views before and after a change
            "shots": shots,
            "passes": ps}


# --- running it ---------------------------------------------------------------------------

# AT3: games and screen recorders, by their executable's name (without .exe)
GAMES = ("javaw", "ow-obs", "obs64", "obs32")


def busy() -> list[str]:
    """Heavy processes that would skew a benchmark (another build, test run, Blender or
    Unreal editor, another benchmark, AT3: a game or a screen recorder), as `name pid`
    strings; Windows only (else nothing).
    This process, its ancestors (the venv's python.exe launcher runs the interpreter as its
    child, with the same command line) and its descendants are its own, never another's."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | ForEach-Object { "
             "\"$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.Name)`t$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    procs = {}
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4 or not parts[0].strip().isdigit():
            continue
        pid, ppid, name, cmd = parts
        procs[int(pid)] = (int(ppid) if ppid.strip().isdigit() else 0, name, cmd)
    hits = _busy(procs, os.getpid())
    # (dlss_lamps_flicker: the Epic Games Launcher downloading or installing, an engine or
    # MetaHuman content, takes the disk and the CPU: busy while it works, idle it is not)
    if any(n.lower().startswith(DOWNLOADERS) for _, n, _ in procs.values()):
        hits += downloading()
    return hits


# the Epic Games Launcher (and its helper) count as busy while they take more than
# DOWNLOAD_CORES of the CPU over DOWNLOAD_S seconds: downloading, verifying or installing
DOWNLOADERS = ("epicgameslauncher", "epicwebhelper")
DOWNLOAD_CORES = 0.15
DOWNLOAD_S = 4.0


def downloading() -> list[str]:
    """The Epic Games Launcher's processes busy downloading or installing (`name pid`): their
    CPU between two samples `DOWNLOAD_S` apart over `DOWNLOAD_CORES`."""
    a = cpu_times()
    time.sleep(DOWNLOAD_S)
    b = cpu_times()
    tot, who = 0.0, []
    for pid, (name, sec) in sorted(b.items()):
        if name.lower().startswith(DOWNLOADERS) and pid in a and a[pid][0] == name:
            tot += max(0.0, sec - a[pid][1])
            who.append(f"{name}.exe {pid}")
    return [who[0] + f" (downloading: {tot / DOWNLOAD_S:.2f} cores)"] if \
        who and tot / DOWNLOAD_S > DOWNLOAD_CORES else []


def _busy(procs: dict[int, tuple[int, str, str]], me: int) -> list[str]:
    """`busy` on a process table {pid: (parent pid, name, command line)} seen from `me`."""
    own = {me}
    p = me
    while p in procs and procs[p][0] not in own and procs[p][0] != 0:
        p = procs[p][0]
        own.add(p)                                   # (the launcher, the shell, ...)
    kids = {}
    for pid, (ppid, _, _) in procs.items():
        kids.setdefault(ppid, []).append(pid)
    todo = [me]
    while todo:
        for c in kids.get(todo.pop(), []):
            if c not in own:
                own.add(c)                           # (the game it runs, its helpers)
                todo.append(c)
    hits = []
    for pid, (_, name, cmd) in sorted(procs.items()):
        if pid in own:
            continue
        low = (name + " " + cmd).lower()
        # (AT0: another benchmark's game too, a packaged one among them: its executable is
        # the project's own, so only its -CityGenBench= names it; a shell that only names
        # it, waiting on it, is not one)
        shell = name.lower().split(".")[0] in ("bash", "sh", "powershell", "pwsh", "cmd")
        # (AT3: a game or a screen recorder shares the GPU: Delta's night ran 1.5 to 2 times
        # slower under a Java game and Overwolf's recorder, `GAMES`)
        if ("unrealeditor" in name.lower() or "blender" in name.lower() or
                name.lower().split(".")[0] in GAMES or
                (not shell and ("-citygenbench=" in low or "automationtool" in low)) or
                ("python" in name.lower() and re.search(
                    r"citygen (build|sweep)|assetgen|pytest|bench", low))):
            hits.append(f"{name} {pid}")
    return hits


# While a run plays, the CPU other processes take is sampled every SAMPLE_S seconds
# (Windows): the game's own helpers (OWN_NAMES) and the driver left out. A run whose game or
# render thread median is STARVED_CPU times the fastest run's while its GPU median stays
# within STARVED_GPU of the fastest run's is flagged (`starved`): a first run after an
# import builds the meshes' derived data on the CPU's cores, and other work on the PC takes
# them the same way (Vesper Bay's and Delta's first runs: the threads twice as slow at the
# same GPU time)
SAMPLE_S = 30.0
OWN_NAMES = ("Idle", "ShaderCompileWorker", "UnrealTraceServer")
STARVED_CPU = 1.5
STARVED_GPU = 1.15


def cpu_times() -> dict[int, tuple[str, float]]:
    """Every process's CPU seconds so far, by pid: (name, seconds); Windows only (else
    nothing)."""
    if os.name != "nt":
        return {}
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process | ForEach-Object { \"$($_.Id)`t$($_.ProcessName)`t$($_.CPU)\" }"],
            capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    res = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].strip():
            try:
                res[int(parts[0])] = (parts[1], float(parts[2]))
            except ValueError:
                continue
    return res


def others(prev: dict, cur: dict, dt: float, own: set[int]) -> dict:
    """The cores other processes took between two `cpu_times` samples `dt` seconds apart
    (a process started since is not counted), with the five busiest by name."""
    per: dict[str, float] = {}
    for pid, (name, sec) in cur.items():
        if pid in own or name in OWN_NAMES or pid not in prev or prev[pid][0] != name:
            continue
        d = sec - prev[pid][1]
        if d > 0:
            per[name] = per.get(name, 0.0) + d / max(dt, 1e-6)
    top = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {"cores": round(sum(per.values()), 2), "top": [[n, round(c, 2)] for n, c in top]}


# AT1: on a hybrid CPU (the PC's i7-12700K: 8 performance and 4 efficiency cores) Windows
# moves a window that loses the foreground onto the efficiency cores (EcoQoS): Delta's
# night runs then had their game and render threads twice as slow from wherever the desktop
# was used, at the same GPU time. The game is opted out of that power throttling and run
# above normal priority (`unthrottle`), and each sample says whether it had the foreground
# (`in_front`; the summary's `front`, the share of samples).
PROCESS_POWER_THROTTLING = 4            # PROCESS_INFORMATION_CLASS ProcessPowerThrottling
POWER_THROTTLING_EXECUTION_SPEED = 0x1
ABOVE_NORMAL_PRIORITY_CLASS = 0x8000


def unthrottle(pid: int) -> dict:
    """Windows: the process out of execution-speed power throttling (EcoQoS: the
    efficiency cores when not in front) and at above normal priority; what was set."""
    if os.name != "nt":
        return {}
    import ctypes
    from ctypes import wintypes

    class _State(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG),
                    ("StateMask", wintypes.ULONG)]

    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x0200 | 0x1000, False, pid)   # SET_INFORMATION, QUERY_LIMITED
    if not h:
        return {"error": "OpenProcess failed"}
    try:
        st = _State(1, POWER_THROTTLING_EXECUTION_SPEED, 0)
        eco = bool(k.SetProcessInformation(h, PROCESS_POWER_THROTTLING, ctypes.byref(st),
                                           ctypes.sizeof(st)))
        pri = bool(k.SetPriorityClass(h, ABOVE_NORMAL_PRIORITY_CLASS))
    finally:
        k.CloseHandle(h)
    return {"no_power_throttling": eco, "above_normal": pri}


def in_front(pid: int) -> bool | None:
    """Windows: whether the foreground window belongs to `pid`."""
    own = front_owner()
    return None if own is None else own[0] == pid


def front_owner() -> tuple[int, str] | None:
    """Windows: the process owning the foreground window, (pid, name), (0, "") with none."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    w = u.GetForegroundWindow()
    if not w:
        return 0, ""
    owner = wintypes.DWORD()
    u.GetWindowThreadProcessId(w, ctypes.byref(owner))
    name = ""
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, owner.value)        # QUERY_LIMITED_INFORMATION
    if h:
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = os.path.basename(buf.value)
        finally:
            k.CloseHandle(h)
    return owner.value, name


# AT3: a game window that lost the foreground (nobody at the desktop: a notification, another
# app's window) is given it back, checked every FRONT_EVERY seconds: the input of the
# foreground window's thread joined for a moment, so Windows lets this process set it
# (SetForegroundWindow alone is refused to a background process); no keys are sent
FRONT_EVERY = 2.0


def take_front(pid: int) -> bool:
    """Windows: the foreground to `pid`'s main visible window; whether it holds it now."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    found = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(hwnd, _):
        owner = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4):
            found.append(hwnd)                       # (visible, unowned: GW_OWNER 4)
        return True

    u.EnumWindows(proto(each), 0)
    if not found:
        return False
    hwnd = found[0]
    fg = u.GetForegroundWindow()
    fg_thread = u.GetWindowThreadProcessId(fg, None) if fg else 0
    me = k.GetCurrentThreadId()
    joined = bool(fg_thread and fg_thread != me and u.AttachThreadInput(me, fg_thread, True))
    try:
        u.ShowWindow(hwnd, 5)                        # SW_SHOW
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
    finally:
        if joined:
            u.AttachThreadInput(me, fg_thread, False)
    if in_front(pid) is not True:
        # (Windows may still refuse a background process; SwitchToThisWindow, the shell's own
        # Alt+Tab call, is not refused: the first after_sky runs lost the game to the Claude
        # app's window and took it back 0 times without it)
        u.SwitchToThisWindow(hwnd, True)
    return in_front(pid) is True


def others_summary(samples: list[dict]) -> dict | None:
    """A run's `others` samples in short: the mean and most cores, the busiest by name, the
    share of samples with the game in front, what `unthrottle` set."""
    un = next((x["unthrottle"] for x in samples if "unthrottle" in x), None)
    samples = [x for x in samples if "unthrottle" not in x]
    if not samples:
        return None
    tot: dict[str, float] = {}
    for x in samples:
        for n, c in x["top"]:
            tot[n] = tot.get(n, 0.0) + c / len(samples)
    fr = [x["in_front"] for x in samples if x.get("in_front") is not None]
    # (AT3: who took the foreground, and how often it was taken back)
    lost: dict[str, int] = {}
    for x in samples:
        for n in x.get("lost_to", []):
            lost[n or "(none)"] = lost.get(n or "(none)", 0) + 1
    return {"samples": len(samples),
            "front": round(sum(fr) / len(fr), 2) if fr else None, "unthrottle": un,
            "lost_to": dict(sorted(lost.items(), key=lambda kv: (-kv[1], kv[0]))),
            "retaken": sum(x.get("retaken", 0) for x in samples),
            "cores_mean": round(statistics.fmean(x["cores"] for x in samples), 2),
            "cores_max": round(max(x["cores"] for x in samples), 2),
            "top": [[n, round(c, 2)] for n, c in
                    sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]}


def run_game(root: Path, uproject: Path, level: str, job_path: Path, log: Path,
             resolution=RESOLUTION, timeout: float = 3600.0,
             samples: list | None = None, rt: bool = False) -> int:
    """The standalone game on `level` with the bench's job; its exit code. With `samples`,
    the CPU other processes take is appended to it every SAMPLE_S seconds while it plays.
    AT0: `rt`, hardware ray tracing on for this game alone (MegaLights)."""
    from .unreal import editor_binary
    exe = editor_binary(root, gui=True)
    ini = ("[/Script/Engine.UserInterfaceSettings]:bAllowHighDPIInGameMode=True,"
           "[/Script/Engine.UserInterfaceSettings]:bAllowHighDpiWhenUnattended=True")
    if rt:
        ini += "," + RT_INI
    cmd = [str(exe), str(uproject), level, "-game", "-windowed",
           f"-ResX={resolution[0]}", f"-ResY={resolution[1]}", "-WinX=0", "-WinY=0",
           f"-CityGenBench={job_path.as_posix()}", "-csvGpuStats", "-NoSound", "-nosplash",
           "-unattended", "-NoLoadingScreen", "-stdout", "-FullStdOutLogOutput",
           # (a DPI-unaware process on a 1440p screen at 125% gets a 2048 x 1152 window: the
           # engine leaves a game DPI-unaware, BaseEngine.ini's bAllowHighDPIInGameMode, and
           # an unattended one too, bAllowHighDpiWhenUnattended)
           f"-ini:Engine:{ini}", "-NoScreenMessages"]
    with open(log, "wb") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        if samples is not None:
            samples.append({"t": 0.0, "cores": 0.0, "top": [],
                            "unthrottle": unthrottle(proc.pid)})
        t0 = time.time()
        watch = samples is not None and os.name == "nt"
        prev, tl = (cpu_times(), t0) if watch else ({}, t0)
        # (AT3: the foreground watched every FRONT_EVERY s, taken back when lost; the
        # processes it was lost to and the times it was taken back go in the next sample)
        lost_to, retaken, front_at = [], 0, t0
        while True:
            left = timeout - (time.time() - t0)
            step = min(left, FRONT_EVERY if watch else left)
            try:
                return proc.wait(timeout=max(0.1, step))
            except subprocess.TimeoutExpired:
                if time.time() - t0 >= timeout:
                    proc.kill()
                    proc.wait()
                    raise
                if not watch:
                    continue
                own = front_owner()
                # (a game still loading has no window: nothing to take back yet)
                if own is not None and own[0] != proc.pid and time.time() - t0 > 20.0:
                    lost_to.append(own[1])
                    retaken += 1 if take_front(proc.pid) else 0
                if time.time() - front_at < SAMPLE_S:
                    continue
                front_at = time.time()
                cur, now = cpu_times(), time.time()
                samples.append({"t": round(now - t0, 1), "in_front": in_front(proc.pid),
                                "lost_to": sorted(set(lost_to)), "retaken": retaken,
                                **others(prev, cur, now - tl, {proc.pid, os.getpid()})})
                prev, tl = cur, now
                lost_to, retaken = [], 0


def bench(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
          runs: int = 3, passes=PASSES, label: str = "bench", out: str | Path | None = None,
          resolution=RESOLUTION, wait_idle: bool = True, timeout: float = 3600.0,
          say=print, atmos: bool = False, rt: bool = False, lean: bool = False) -> dict:
    """`citygen unreal --bench`: `runs` game processes over the route, each run's raw frames
    kept in BUILD/unreal/bench/<label>/run<k>, the results (`combine`) written to `out`
    (default docs/progress/AG16/bench/<city>/<label>). `atmos` (AT1): the passes switch the
    level's atmos controller (the import placed it with the city's plan; its assets made
    first; `ATMOS_PASSES`); `rt` (AT0) hardware ray tracing on in the game; `lean` the lean
    route (`route`: one walk, the drive, the flight, a short warm-up)."""
    from .unreal import find_engine
    build = Path(build_dir).resolve()
    up = Path(uproject).resolve()
    root = find_engine(engine)
    if root is None:
        raise RuntimeError("no Unreal Engine found (pass --engine or set CITYGEN_UE_ROOT)")
    man = json.loads((build / "unreal" / "manifest.json").read_text(encoding="utf-8"))
    level = f"{man['content_root']}/Maps/{man['folder']}"
    use_rt = rt
    rt = route(build, man, lean=lean)
    raw = build / "unreal" / "bench" / label
    raw.mkdir(parents=True, exist_ok=True)
    # the play plugin drives the route: built as the import builds it (skipped when its
    # binaries are of this source)
    from .unreal_play import build_plugin
    pl = build_plugin(root, up, raw / "plugin_build_log.txt")
    if not pl.get("ok"):
        raise RuntimeError(f"the play plugin (the benchmark's driver) did not build: "
                           f"{pl.get('error')}")
    if atmos:
        if not (man.get("atmos") or {}).get("cells"):
            raise RuntimeError("the level has no atmos plan: import the city with one first "
                               "(atmosgen plan, then citygen unreal)")
        from .unreal_atmos import make_assets
        ma = make_assets(root, up, raw / "atmos_assets_log.txt")
        if not ma.get("ok"):
            raise RuntimeError(f"atmosgen's assets: {ma.get('error')}")
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
        # (the last run shoots: its caches are warm; a first run after an import builds
        # the meshes' derived data as it loads them and draws coarse Nanite meanwhile)
        jb = job(rt, rd, passes, resolution=resolution, shots=k == runs - 1)
        jp = rd / "job.json"
        jp.write_text(json.dumps(jb, indent=1) + "\n", encoding="utf-8", newline="\n")
        say(f"bench: run {k + 1} of {runs} ({len(jb['passes'])} passes, "
            f"{len(rt['segments'])} segments)")
        t = time.time()
        samples: list[dict] = []
        code = run_game(root, up, level, jp, rd / "game_log.txt", resolution, timeout,
                        samples=samples, rt=use_rt)
        (rd / "others.json").write_text(json.dumps(samples, indent=0) + "\n",
                                        encoding="utf-8", newline="\n")
        if not (rd / "frames.csv").is_file():
            raise RuntimeError(f"run {k + 1}: the game wrote no frames (exit {code}); "
                               f"log {rd / 'game_log.txt'}")
        res = summarize(rd, rt)
        res["exit_code"], res["wall_s"] = code, round(time.time() - t, 1)
        res["others"] = others_summary(samples)
        if res.get("viewport") != list(resolution):
            # (a run at another resolution is not this benchmark: say so in its results)
            res["resolution_mismatch"] = True
            say(f"bench: run {k + 1} rendered at {res.get('viewport')}, not "
                f"{resolution[0]}x{resolution[1]}")
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
        if p.get("upscaler"):
            entry["upscaler"] = p["upscaler"]          # (dlss_lamps_flicker: its state)
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
    # (dlss_lamps_flicker: with DLSS Frame Generation the frames shown per second and
    # presented per rendered frame, Reflex's game to render latency; a run before has none)
    hz = [f["fg_hz"] for f in fs if f.get("fg_hz", -1.0) > 0.0]
    if hz:
        out["fg_hz"] = _stats(hz)
        out["fg_presented"] = round(sum(f["fg_presented"] for f in fs
                                        if f.get("fg_hz", -1.0) > 0.0) / len(hz), 2)
    lat = [f["latency_ms"] for f in fs if f.get("latency_ms", -1.0) > 0.0]
    if lat:
        out["latency_ms"] = _stats(lat)
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
    out["starved"] = starved(results)
    out["others"] = [r.get("others") for r in results]
    return out


def starved(results: list[dict]) -> list[dict]:
    """The runs whose CPU threads were slow at the same GPU time: a pass where the run's game
    or render thread median (all moving frames) is STARVED_CPU times the fastest run's while
    its GPU median stays within STARVED_GPU of the fastest run's; per run its passes, the
    most it was slower by, and the cores other processes took meanwhile (`others`)."""
    flags: dict[int, list] = {}
    if len(results) < 2:
        return []
    for i, p in enumerate(results[0]["passes"]):
        rows = [r["passes"][i].get("all") or {} for r in results]
        if not all(r.get("frames") for r in rows):
            continue
        g0 = min(r["game_ms"]["p50"] for r in rows)
        r0 = min(r["render_ms"]["p50"] for r in rows)
        u0 = min(r["gpu_ms"]["p50"] for r in rows)
        for k, r in enumerate(rows):
            cpu = max(r["game_ms"]["p50"] / max(g0, 0.01), r["render_ms"]["p50"] / max(r0, 0.01))
            gpu = r["gpu_ms"]["p50"] / max(u0, 0.01)
            if cpu >= STARVED_CPU and gpu <= STARVED_GPU:
                flags.setdefault(k + 1, []).append((p["name"], cpu))
    return [{"run": k, "passes": [n for n, _ in fs], "cpu_x": round(max(c for _, c in fs), 2),
             "others_cores": (results[k - 1].get("others") or {}).get("cores_mean"),
             "others_top": (results[k - 1].get("others") or {}).get("top")}
            for k, fs in sorted(flags.items())]


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
                # (frames over 100 ms a run: the median and the most of any run, and the
                # longest frame of the runs' medians)
                out["big_hitches"].append(
                    f"{tag} {e['big_hitches']['median']:g} a run (at most "
                    f"{e['big_hitches']['max']:g})")
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
    if res.get("starved"):
        lines += ["", "CPU-starved runs (a thread's median at least "
                  f"{STARVED_CPU:g} times the fastest run's at the same GPU time; a first run "
                  "after an import builds the meshes' derived data, or other work on the PC; "
                  "the median of the runs leaves one out): " + "; ".join(
                      f"run {x['run']} ({', '.join(x['passes'])}; up to {x['cpu_x']:g}x"
                      + (f"; other processes {x['others_cores']:g} cores on average"
                         if x.get("others_cores") is not None else "") + ")"
                      for x in res["starved"])]
    oth = [(k + 1, o) for k, o in enumerate(res.get("others") or []) if o]
    if oth:
        lines += ["", "Other processes' CPU during the runs (cores, mean and most; the "
                  "busiest): " + "; ".join(
                      f"run {k} {o['cores_mean']:g} / {o['cores_max']:g} ("
                      + ", ".join(f"{n} {c:g}" for n, c in o["top"][:3]) + ")"
                      for k, o in oth)]
    t = res["targets"]
    lines += ["", "Targets: 60 fps (p95 16.7 ms) missed by: "
              + (", ".join(t["p95_60fps"]) or "none")
              + "; 40 fps (25 ms) missed by: " + (", ".join(t["p95_40fps"]) or "none")
              + "; hitches over 100 ms: " + (", ".join(t["big_hitches"]) or "none")
              + "; VRAM over 10 GB: " + (", ".join(t["vram"]) or "none")]
    return "\n".join(lines) + "\n"


def write_results(res: dict, dest: Path, run_dirs: list[Path]) -> None:
    """bench.json and bench.md, and a frame-time graph along the route per pass of the last
    run (frame_times_<pass>.png), with its screenshots."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "bench.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8",
                                     newline="\n")
    (dest / "bench.md").write_text(table(res), encoding="utf-8", newline="\n")
    try:
        graphs(run_dirs[-1], dest, res)
    except Exception as e:          # noqa: BLE001 (a graph is not worth failing the run)
        (dest / "graph_error.txt").write_text(str(e) + "\n", encoding="utf-8")
    shots(run_dirs[-1], dest)


SHOT_W = 1600


def shots(rd: Path, dest: Path) -> list[Path]:
    """A run's screenshots (each segment's start in each pass) as JPEGs SHOT_W
    wide in `dest/shots`."""
    from PIL import Image
    out = []
    src = sorted((rd / "shots").glob("*.png")) if (rd / "shots").is_dir() else []
    if src:
        (dest / "shots").mkdir(parents=True, exist_ok=True)
    for f in src:
        im = Image.open(f).convert("RGB")
        h = round(im.height * SHOT_W / im.width)
        o = dest / "shots" / (f.stem + ".jpg")
        im.resize((SHOT_W, h), Image.LANCZOS).save(o, quality=85)
        out.append(o)
    return out


def graphs(rd: Path, dest: Path, res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    frames = read_frames(rd / "frames.csv")
    info = json.loads((rd / "bench_events.json").read_text(encoding="utf-8"))
    names = {e["pass"]: e["name"] for e in info["events"]
             if e.get("op") == "pass" and not e.get("warm")}
    segs = res["segments"]
    for pi, name in names.items():
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
        top = max(60.0, min(150.0, _pct([f["frame_ms"] for f in fs], 0.999) * 1.2))
        ax.set_ylim(0, top)
        last = None
        for k, f in enumerate(fs):
            if int(f["seg"]) != last:
                last = int(f["seg"])
                ax.axvline(k, color="#999", lw=0.6)
                ax.text(k + 20, top * 0.97, segs[last]["name"], fontsize=7, va="top",
                        ha="left", color="#222",
                        bbox={"facecolor": "white", "edgecolor": "none", "pad": 1})
        ax.set_xlabel("frame along the route")
        ax.set_ylabel("ms")
        ax.set_title(f"{res['city']} {res['label']}: {name}")
        ax.legend(loc="lower right", fontsize=7)
        fig.subplots_adjust(left=0.05, right=0.99, top=0.9, bottom=0.14)
        fig.savefig(dest / f"frame_times_{name}.png")
        plt.close(fig)


def side_by_side(before: Path, after: Path, dest: Path, width: int = 1600) -> list[Path]:
    """The shots two benchmarks share (`<label>/shots/<pass>_<segment>.jpg`), before on the
    left and after on the right, each `width` / 2 wide, a label over each, as
    `dest/<pass>_<segment>.jpg`: the same views before and after a change."""
    from PIL import Image, ImageDraw
    out = []
    names = sorted({p.name for p in (before / "shots").glob("*.jpg")} &
                   {p.name for p in (after / "shots").glob("*.jpg")})
    if names:
        dest.mkdir(parents=True, exist_ok=True)
    half = width // 2
    for n in names:
        ims = []
        for d in (before, after):
            im = Image.open(d / "shots" / n).convert("RGB")
            ims.append(im.resize((half, round(im.height * half / im.width)), Image.LANCZOS))
        h = max(im.height for im in ims)
        sheet = Image.new("RGB", (half * 2 + 8, h + 28), (255, 255, 255))
        draw = ImageDraw.Draw(sheet)
        for k, (im, label) in enumerate(zip(ims, (before.name, after.name))):
            sheet.paste(im, (k * (half + 8), 28))
            draw.text((k * (half + 8) + 6, 6), f"{label}: {n[:-4]}", fill=(20, 20, 20))
        o = dest / n
        sheet.save(o, quality=85)
        out.append(o)
    return out
