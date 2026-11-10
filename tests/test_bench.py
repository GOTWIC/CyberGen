"""AG16: the benchmark's venv side (citygen/bench.py): the route from a build's manifest and
graphs, a run's results from the frames the game wrote, several runs together, the targets
and the table. The game process itself runs only with Unreal (`citygen unreal --bench`)."""

import json
import math

from citygen import bench as B


def _graph(lines, kinds, links):
    pts, start = [], [0]
    for ln in lines:
        for p in ln:
            pts += list(p)
        start.append(start[-1] + len(ln))
    ls, flat = [0], []
    for lk in links:
        flat += lk
        ls.append(len(flat))
    return {"ids": [f"w{i}" for i in range(len(lines))], "kinds": kinds,
            "refs": [""] * len(lines), "widths": [2.0] * len(lines), "point_start": start,
            "points": pts, "link_start": ls, "links": flat, "attrs": [""] * len(lines),
            "count": len(lines), "hash": "x"}


def _build(tmp_path):
    """A city of a straight sidewalk east (0 to 400 m) at y 10, an elevator off its start, a
    lane along y 0 joined to a second lane turning north, three districts' actors."""
    walks = _graph(
        [[(0.0, 10.0, 0.0), (100.0, 10.0, 0.0)], [(100.0, 10.0, 0.0), (400.0, 10.0, 0.0)],
         [(0.0, 10.0, 0.0), (0.0, 10.0, 8.0)]],
        ["sidewalk", "sidewalk", "elevator"], [[1, 2], [0], [0]])
    lanes = _graph(
        [[(-50.0, 0.0, 0.0), (300.0, 0.0, 0.0)], [(300.0, 0.0, 0.0), (300.0, 900.0, 0.0)],
         [(300.0, 0.0, 0.0), (300.0, -900.0, 0.0)]],
        ["lane", "lane", "lane"], [[1, 2], [], []])
    out = tmp_path / "unreal"
    out.mkdir()
    (out / "graphs.json").write_text(json.dumps({"walkways": walks, "lanes": lanes}),
                                     encoding="utf-8")
    actors = []
    for d, n, x in (("d01", 30, 10.0), ("d02", 50, 50.0), ("d03", 5, 90.0), ("d04", 20, 30.0)):
        actors += [{"category": "building", "district": d, "pivot": [x + i, 12.0 + i, 0.0]}
                   for i in range(n)]
    man = {"city": "Test City", "slug": "test_city", "bounds": [-1000, -1000, 1000, 1000],
           "tiles": [], "stage2": {"actors": actors}}
    (out / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    return man


def test_route_walks_drive_flight_teleport(tmp_path):
    _build(tmp_path)
    rt = B.route(tmp_path)
    names = [s["name"] for s in rt["segments"]]
    # the three districts with the most stage 2 actors, most first
    assert rt["districts"] == ["d02", "d01", "d04"]
    assert names == ["walk_d02", "walk_d01", "walk_d04", "drive", "fly_150m", "teleport"]
    w = rt["segments"][0]
    assert math.isclose(B._length(w["points"]), B.WALK_M, abs_tol=0.05)
    # along the sidewalks at eye height, never up the elevator
    assert all(abs(p[2] - B.EYE_M) < 1e-6 for p in w["points"])
    assert all(abs(p[1] - 10.0) < 1e-6 for p in w["points"])
    d = rt["segments"][3]
    # the drive goes on into the lane that turns least (both turn 90 degrees: the first)
    assert d["points"][-1][1] > 0 and abs(d["points"][-1][0] - 300.0) < 1e-6
    assert all(abs(p[2] - B.DRIVE_EYE_M) < 1e-6 for p in d["points"])
    f = rt["segments"][4]
    assert f["points"][0][2] == B.FLY_Z_M and len(f["points"]) == 2
    t = rt["segments"][5]
    assert t["kind"] == "teleport" and t["points"] == [w["points"][0]]
    # the same build, the same route
    assert B.route(tmp_path) == rt


def test_job_has_a_warm_pass_first(tmp_path):
    _build(tmp_path)
    jb = B.job(B.route(tmp_path), tmp_path / "run1")
    # by day and by night, the flight alone
    assert [p["name"] for p in jb["passes"][:2]] == ["warm_day", "warm_night"]
    assert all(p["warm"] and p["segments"] == [4] for p in jb["passes"][:2])
    assert len(jb["passes"]) == 2 + len(B.PASSES)
    assert [p["screen_percentage"] for p in jb["passes"][2:]] == [100.0, 67.0, 100.0, 67.0]
    assert "r.VSync 0" in jb["commands"]


def _run(rd, rt, slow=1.0, cpu=1.0):
    """A run's files as the game writes them: the warm pass and one measured pass, each
    segment loaded, then moving frames (phase 2) or the teleport's (phase 3)."""
    rd.mkdir(parents=True)
    rows = ["pass,seg,phase,t,frame_ms,game_ms,render_ms,rhi_ms,gpu_ms,draws,prims,streamed,"
            "perf,vram_mb,ram_mb,x,y,z"]
    events = [{"op": "pass", "pass": 0, "seg": 0, "name": "warm", "night": False,
               "screen_percentage": 100.0, "warm": True},
              {"op": "pass", "pass": 1, "seg": 0, "name": "day_tsr67", "night": False,
               "screen_percentage": 67.0, "warm": False}]
    for pi in (0, 1):
        for si, s in enumerate(rt["segments"]):
            events.append({"op": "loaded", "pass": pi, "seg": si, "seconds": 2.0,
                           "timeout": False})
            rows.append(f"{pi},{si},1,0,200,1,1,1,1,10,10,-1,0,5000,9000,0,0,0")
            phase = 3 if s["kind"] == "teleport" else 2
            for k in range(100):
                ms = (10.0 if k < 90 else 30.0) * slow
                if s["group"] == "fly" and k == 50:
                    ms = 120.0
                rows.append(f"{pi},{si},{phase},0,{ms * cpu},{(ms - 2) * cpu},"
                            f"{(ms - 3) * cpu},2,{ms - 1},500,9000,"
                            f"{0 if k % 10 == 0 else 1},0,{6000 + k},12000,0,0,0")
    (rd / "frames.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (rd / "bench_events.json").write_text(json.dumps(
        {"viewport": [2560, 1440], "adapter": "Test GPU", "rhi": "D3D12",
         "nanite_max_root_pages": 57344, "events": events}), encoding="utf-8")
    # the engine's CSV profile: its columns, the bench's events, a footer
    prof = ["FrameTime,NaniteStreaming/RootAllocationMB,GPU/Nanite,GPU/Lumen,EVENTS"]
    for pi in (0, 1):
        for si, _ in enumerate(rt["segments"]):
            prof.append(f"10,{100.0 + pi + si},3,{2 + si},cg:{pi}:{si}")
            prof.append("10,120,3,2,")
    prof.append("[HasHeaderRowAtEnd],1")
    (rd / "profile.csv").write_text("\n".join(prof) + "\n", encoding="utf-8")


def test_summarize_combine_and_table(tmp_path):
    _build(tmp_path)
    rt = B.route(tmp_path)
    res = []
    for k, slow in enumerate((1.0, 1.1, 0.9)):
        rd = tmp_path / f"run{k + 1}"
        _run(rd, rt, slow)
        res.append(B.summarize(rd, rt))
    p = res[0]["passes"]
    # the warm-up is left out
    assert [x["name"] for x in p] == ["day_tsr67"]
    walk = p[0]["walk"]
    assert walk["frames"] == 300 and walk["frame_ms"]["p50"] == 10.0
    assert walk["frame_ms"]["p95"] == 30.0 and walk["bound_by"] == "gpu"
    assert p[0]["fly"]["hitches"] == 1 and p[0]["fly"]["big_hitches"] == 1
    assert walk["unstreamed_share"] == 0.1 and walk["vram_mb_max"] == 6099
    # the root pages from the CSV profile's root allocation (32 KB pages)
    assert walk["nanite_root_pages_max"] == int(round(120.0 / B.ROOT_PAGE_MB))
    assert "Lumen" in walk["gpu_passes_ms"] and p[0]["load_s"] == 12.0
    comb = B.combine(res, rt, "before", B.RESOLUTION)
    w = comb["passes"][0]["walk"]
    assert w["frame_ms_p95_spread"] == {"median": 30.0, "min": 27.0, "max": 33.0}
    assert w["frame_ms"]["p95"] == 30.0
    # targets: 30 ms misses 60 and 40 fps; the flight's 120 ms frame is a hitch over 100 ms
    t = comb["targets"]
    assert any(x.startswith("day_tsr67/walk") for x in t["p95_60fps"])
    assert any(x.startswith("day_tsr67/fly") for x in t["big_hitches"])
    assert t["vram"] == []
    md = B.table(comb)
    assert "| day_tsr67 | walk | 300 |" in md and "Targets:" in md
    B.write_results(comb, tmp_path / "out", [tmp_path / "run1"])
    assert json.loads((tmp_path / "out" / "bench.json").read_text(encoding="utf-8")) == comb
    assert (tmp_path / "out" / "frame_times_day_tsr67.png").is_file()


def test_a_cpu_starved_run_is_flagged(tmp_path):
    """A run whose threads take twice as long at the same GPU time (a first run after an
    import, or other work on the PC) is named under the table; the median leaves it out."""
    _build(tmp_path)
    rt = B.route(tmp_path)
    res = []
    for k, cpu in enumerate((2.0, 1.0, 1.05)):
        rd = tmp_path / f"run{k + 1}"
        _run(rd, rt, 1.0, cpu)
        res.append(B.summarize(rd, rt))
    res[0]["others"] = {"samples": 4, "cores_mean": 3.5, "cores_max": 6.0,
                        "top": [["OneDrive", 3.0]]}
    comb = B.combine(res, rt, "after", B.RESOLUTION)
    assert [x["run"] for x in comb["starved"]] == [1]
    assert comb["starved"][0]["passes"] == ["day_tsr67"] and comb["starved"][0]["cpu_x"] >= 1.9
    assert comb["starved"][0]["others_cores"] == 3.5
    md = B.table(comb)
    assert "CPU-starved runs" in md and "run 1 (day_tsr67" in md and "OneDrive 3" in md
    # the other processes between two samples: a new process and the game's own left out
    prev = {1: ("OneDrive", 10.0), 2: ("UnrealEditor", 50.0), 3: ("ShaderCompileWorker", 5.0)}
    cur = {1: ("OneDrive", 25.0), 2: ("UnrealEditor", 80.0), 3: ("ShaderCompileWorker", 9.0),
           4: ("MsMpEng", 30.0)}
    assert B.others(prev, cur, 30.0, {2}) == {"cores": 0.5, "top": [["OneDrive", 0.5]]}


def test_side_by_side(tmp_path):
    from PIL import Image
    for label, color in (("before", (200, 0, 0)), ("after", (0, 0, 200))):
        d = tmp_path / label / "shots"
        d.mkdir(parents=True)
        Image.new("RGB", (160, 90), color).save(d / "day_tsr67_walk_d01.jpg")
    Image.new("RGB", (160, 90)).save(tmp_path / "before" / "shots" / "only_before.jpg")
    out = B.side_by_side(tmp_path / "before", tmp_path / "after", tmp_path / "pairs", width=320)
    assert [p.name for p in out] == ["day_tsr67_walk_d01.jpg"]
    im = Image.open(out[0])
    assert im.size == (328, 90 + 28)
    # before on the left, after on the right
    assert im.getpixel((40, 70))[0] > 150 and im.getpixel((200, 70))[2] > 150


def test_job_with_atmosgens_passes(tmp_path):
    """AT0: a pass of atmosgen's spike carries its console commands; with one in the job every
    other pass switches atmosgen off and the night's warm-up has all of it on."""
    _build(tmp_path)
    names = {p[0] for p in B.ATMOS_PASSES}
    assert len(names) == len(B.ATMOS_PASSES) and not names & {p[0] for p in B.PASSES}
    want = [p for p in B.PASSES if p[0] == "night_native"] + \
        [p for p in B.ATMOS_PASSES if p[0] == "night_plan_all"]
    jb = B.job(B.route(tmp_path), tmp_path / "run1", want)
    assert [p["name"] for p in jb["passes"]] == ["warm_night", "night_native", "night_plan_all"]
    warm, native, plan = jb["passes"]
    assert native["commands"] == list(B.ATMOS_OFF)
    assert "CityGenAtmos.Lights 1" in plan["commands"] and "CityGenAtmos.Rain 1" in plan["commands"]
    assert "CityGenAtmos.Wet 1" in warm["commands"] and warm["warm"]
    # without atmosgen's passes the job is AG16's (no commands per pass)
    jb = B.job(B.route(tmp_path), tmp_path / "run2")
    assert all("commands" not in p for p in jb["passes"])


def test_atmos_assets_version():
    from citygen import unreal_atmos as UA
    assert UA.assets_version().isdigit()


def test_busy_sees_any_benchmark():
    """AT0: another benchmark's game (a packaged one: the project's own executable) and its
    driver count as busy; a shell that only names one in its command line does not, nor this
    benchmark's own driver, its launcher (the venv's python.exe runs the interpreter as a
    child with the same command line) or the game it runs."""
    procs = {
        1: (0, "explorer.exe", "explorer.exe"),
        10: (1, "bash.exe", "bash bench.sh at0 1 night_native"),
        11: (10, "python.exe", "python -m citygen unreal B P --bench-only"),      # launcher
        12: (11, "python.exe", "python -m citygen unreal B P --bench-only"),      # me
        13: (12, "UnrealEditor.exe", "UnrealEditor.exe P.uproject -game -CityGenBench=j"),
        101: (1, "CityAG16.exe", "CityAG16.exe /Game/X -CityGenBench=C:/b/job.json"),
        102: (1, "python.exe", "python -u bench_packaged.py 3"),
        103: (1, "bash.exe", "bash -c until ! powershell ... -CityGenBench=* ; do sleep 60"),
        104: (1, "notepad.exe", "notepad.exe notes.txt"),
        105: (1, "UnrealEditor.exe", "UnrealEditor.exe Q.uproject")}
    assert B._busy(procs, 12) == ["CityAG16.exe 101", "python.exe 102", "UnrealEditor.exe 105"]
    # (from the packaged run's side, this benchmark and its game are busy)
    assert B._busy(procs, 102) == ["python.exe 11", "python.exe 12", "UnrealEditor.exe 13",
                                   "CityAG16.exe 101", "UnrealEditor.exe 105"]
