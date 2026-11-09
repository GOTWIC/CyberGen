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
    assert jb["passes"][0]["warm"] and len(jb["passes"]) == 1 + len(B.PASSES)
    assert [p["screen_percentage"] for p in jb["passes"][1:]] == [100.0, 67.0, 100.0, 67.0]
    assert "r.VSync 0" in jb["commands"]


def _run(rd, rt, slow=1.0):
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
                rows.append(f"{pi},{si},{phase},0,{ms},{ms - 2},{ms - 3},2,{ms - 1},"
                            f"500,9000,{0 if k % 10 == 0 else 1},0,{6000 + k},12000,0,0,0")
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
