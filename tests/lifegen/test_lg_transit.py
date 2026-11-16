"""LG6: transit (docs/lifegen_scope.md 6.6, checks "Timetables"): every line's timetable, its
stops, trains and boarding (`lifegen/transit.py`), on LG0's small synthetic city (a metro under
its street, its station's stairs the board walkway) and on lines made here (a loop, a curve);
the checks failing where they should; the exporter's pack (`citygen/unreal_life.py`
`pack_transit`)."""

import copy
import json
import math
from pathlib import Path

import pytest

from lifegen import plan as PL
from lifegen import planmodel as PM
from lifegen import presets as P
from lifegen import transit as TR

from test_lg_plan import _flat, _model


@pytest.fixture
def build(tmp_path: Path) -> Path:
    b = tmp_path / "city"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    return b


def _circle(cx: float, cy: float, r: float, z: float, n: int = 96) -> list[list[float]]:
    pts = [[cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n), z]
           for k in range(n)]
    return pts + [pts[0]]


def _loop_model() -> dict:
    """A sky tube loop of 600 m radius round two stations (platforms on the ring), elevator
    access walkways down to a street."""
    m = _model()
    path = _circle(0.0, 0.0, 600.0, 90.0)
    m["transit_lines"] = [{"id": "tl.ring", "name": "Ring", "mode": "sky_tube",
                           "color": "#22e5ff", "loop": True,
                           "station_ids": ["stn.e", "stn.w"], "path": path}]
    m["stations"] = [
        {"id": "stn.e", "kind": "sky", "position": [600.0, 0.0, 90.0], "line_ids": ["tl.ring"],
         "access_ids": ["wk.pe"]},
        {"id": "stn.w", "kind": "sky", "position": [-600.0, 0.0, 90.0],
         "line_ids": ["tl.ring"], "access_ids": ["wk.pw"]}]
    m["walkways"] += [
        {"id": "wk.pe", "kind": "elevated", "line": [[600.0, -25.0, 90.0], [600.0, 25.0, 90.0]],
         "width_m": 8.0, "neighbors": ["wk.ee"], "attrs": {"station": "stn.e", "platform": True}},
        {"id": "wk.ee", "kind": "elevator", "line": [[600.0, 25.0, 0.0], [600.0, 25.0, 90.0]],
         "width_m": 2.5, "neighbors": ["wk.pe"], "attrs": {"station": "stn.e"}},
        {"id": "wk.pw", "kind": "elevated",
         "line": [[-600.0, -25.0, 90.0], [-600.0, 25.0, 90.0]],
         "width_m": 8.0, "neighbors": [], "attrs": {"station": "stn.w", "platform": True}}]
    m["structures"] = [{"id": "stn.e.pf", "kind": "deck",
                        "attrs": {"station": "stn.e", "role": "platform"},
                        "footprint": {"exterior": [[592.0, -25.0], [608.0, -25.0],
                                                   [608.0, 25.0], [592.0, 25.0]],
                                      "holes": []}}]
    return m


def test_timetables_on_a_small_city(build: Path):
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"], {k: v for k, v in rep["checks"].items() if not v["ok"]}
    for k in ("timetables", "transit_stops", "transit_boarding", "transit_budget"):
        assert rep["checks"][k]["ok"], k
    out = build / "life"
    tt = PM.Timetables.model_validate_json((out / "timetables.json").read_text(encoding="utf-8"))
    (ln,) = tt.lines
    mode = P.TRANSIT_MODES["metro"]
    assert ln.id == "tl.m" and not ln.loop and ln.cars == mode["cars"]
    # (the stop where the stairs' middle projects onto the track: 150 m east, 170 m along it)
    (st,) = ln.stops
    assert st.station_id == "stn.x" and st.s == pytest.approx(170.0, abs=0.01)
    assert st.walkway_id == "wk.s" and not st.board_level
    # (an open line: out and back between its turn points, a train's half length in from the
    # track's ends, turning at both with a layover; the stop called both ways)
    a, b = ln.turn
    assert a == pytest.approx(ln.train_m / 2.0 + 2.0, abs=0.01)
    assert b == pytest.approx(440.0 - ln.train_m / 2.0 - 2.0, abs=0.01)
    assert ln.samples[0] == 0.0 and ln.samples[-1] == pytest.approx(2.0 * ln.D, abs=0.01)
    assert all(y >= x - 1e-6 for x, y in zip(ln.samples, ln.samples[1:]))
    ev = [e for e in ln.events if e[2] >= 0]
    assert sorted(int(e[3]) for e in ev) == [0, 1]
    assert all(e[1] - e[0] == pytest.approx(mode["dwell_s"]) for e in ev)
    turns = [e for e in ln.events if e[2] < 0]
    assert len(turns) == 2 and all(e[1] - e[0] >= P.TRANSIT["turnback_s"] for e in turns)
    # (trains per band: the cycle over the headway asked, evenly spaced; ids per train)
    for k, n in enumerate(ln.trains):
        assert n >= 1 and ln.headway_min[k] == pytest.approx(ln.cycle_s / n / 60.0, abs=1e-3)
    assert ln.train_ids == [f"train.tl.m.{k}" for k in range(max(ln.trains))]
    # (the plan's record, its trains in the contribution)
    plan = json.loads((out / "life_plan.json").read_text(encoding="utf-8"))
    assert plan["transit"]["lines"][0]["stops"] == ["stn.x"]
    con = json.loads((out / "unreal_contribution.life.json").read_text(encoding="utf-8"))
    trains = [e for e in con["entries"] if e["kind"] == "train"]
    assert [e["key"] for e in trains] == ln.train_ids
    # (people boarding a train at least the band's minimum)
    assert all(v >= P.TRANSIT["board_min"][k] for k, v in enumerate(st.board))


def test_a_loop_runs_one_way_round(tmp_path: Path):
    m = _loop_model()
    lines, left = TR.transit_plan(m, {"transit": {}}, [])
    assert not left["lines"] and not left["stations"]
    (ln,) = lines
    L = 2 * math.pi * 600.0
    assert ln["loop"] and ln["closing_gap_m"] == 0.0
    assert ln["length_m"] == pytest.approx(L, rel=2e-3)
    # (one way round from its first stop, the cycle coming round to it; both stops called)
    assert ln["D"] == pytest.approx(ln["length_m"], abs=0.01)
    assert ln["samples"][-1] == pytest.approx(ln["D"], abs=0.01)
    assert sorted(e[2] for e in ln["events"]) == [0, 1] and {e[3] for e in ln["events"]} == {0}
    # (centered in its tube; people on its platforms keep off the tube)
    assert ln["car"]["track_m"] == 0.0 and ln["car"]["sides"] == 2
    pe = next(s for s in ln["stops"] if s["station_id"] == "stn.e")
    # (its deck 16 m across a ring that bends under it: the farthest corner 8 to 9 m off)
    assert 8.0 <= pe["half_m"] <= 9.0
    assert pe["clear_m"] == pytest.approx(TR.clear_of("sky_tube", True))
    # (a pylon station's platform over the pods: people board from its level)
    assert not pe["board_level"] and pe["board_z"] == pytest.approx(90.0)
    comp = PL.walk_components(m["walkways"])
    chk = TR.checks(m, lines, left, comp, [])
    assert chk["timetables"]["ok"], chk["timetables"]
    assert chk["transit_stops"]["ok"], chk["transit_stops"]


def test_speeds_keep_to_curves_and_rates():
    # (a ring of 150 m radius: a sky tube at sqrt(1.2 * 150) = 13.4 m/s at most round it)
    tr = TR.Track(_circle(0.0, 0.0, 150.0, 90.0, 120), True)
    mode = P.TRANSIT_MODES["sky_tube"]
    lim = TR.speed_limits(tr, mode, 2.0)
    assert max(lim) == pytest.approx(math.sqrt(mode["lateral"] * 150.0), rel=0.02)
    stops = [{"s": 0.0, "station_id": "a"}, {"s": tr.L / 2.0, "station_id": "b"}]
    cyc = TR.cycle(tr, mode, stops)
    for w in cyc["ways"]:
        assert all(v <= lim_ + 1e-9 for v, lim_ in zip(w["v"], w["lim"]))
        h = w["h"]
        for v0, v1 in zip(w["v"], w["v"][1:]):
            # (v squared changes along a step by at most twice the rate times the step)
            assert v1 * v1 - v0 * v0 <= 2.0 * mode["accel"] * h + 1e-6
            assert v0 * v0 - v1 * v1 <= 2.0 * mode["brake"] * h + 1e-6
    # (the samples read back at the mode's rates, sampled every step)
    dt = cyc["R"] / math.ceil(cyc["R"] / 0.5)
    s = TR.sample(cyc["knots"], cyc["R"], dt)
    vs = [(b - a) / dt for a, b in zip(s, s[1:])]
    assert max(abs(b - a) / dt for a, b in zip(vs, vs[1:])) <= mode["accel"] * 1.35 + 0.05


def test_too_close_a_headway_is_raised(build: Path):
    # (a train every 6 s asked: fewer trains, so no two come within a train's length and the
    # safety distance or into a terminal at once; said in the record, the plan delivered)
    (build / "life_spec.json").write_text(json.dumps(
        {"transit": {"headway_min": {"Metro Line": [0.1, 0.1, 0.1, 0.1, 0.1]}}}),
        encoding="utf-8")
    rep = PL.build_plan(build, build / "life_spec.json", preview=False)
    assert rep["ok"], {k: v for k, v in rep["checks"].items() if not v["ok"]}
    tt = json.loads((build / "life" / "timetables.json").read_text(encoding="utf-8"))
    ln = tt["lines"][0]
    assert ln["notes"] and all(h > 0.1 for h in ln["headway_min"])
    assert "headways raised" in rep["checks"]["timetables"]["detail"]


def test_a_bad_timetable_fails(build: Path):
    m = _model()
    lines, left = TR.transit_plan(m, {"transit": {}}, [])
    comp = PL.walk_components(m["walkways"])
    bad = copy.deepcopy(lines)
    # (a sample moved on 30 m: faster than the metro runs)
    bad[0]["samples"][40] += 30.0
    chk = TR.checks(m, bad, left, comp, [])
    assert not chk["timetables"]["ok"]
    # (more trains than fit: two within the safety distance)
    bad = copy.deepcopy(lines)
    bad[0]["trains"] = [40] * 5
    chk = TR.checks(m, bad, left, comp, [])
    assert not chk["timetables"]["ok"] and "come within" in chk["timetables"]["detail"]
    # (past the budget)
    bad = copy.deepcopy(lines)
    bad[0]["trains"] = [P.TRANSIT["budget_trains"] + 1] * 5
    assert not TR.checks(m, bad, left, comp, [])["transit_budget"]["ok"]


def test_a_station_off_its_track_fails():
    m = _model()
    m["stations"][0]["position"] = [150.0, 80.0, -8.0]
    m["stations"][0]["access_ids"] = []
    lines, left = TR.transit_plan(m, {"transit": {}}, [])
    assert left["stations"] and "off the track" in left["stations"][0]["why"]
    chk = TR.checks(m, lines, left, PL.walk_components(m["walkways"]), [])
    assert not chk["transit_stops"]["ok"]


def test_riders_board_by_the_hour():
    lines = [{"mode": "metro", "trains": [2, 4, 3, 4, 3], "cycle_s": 600.0,
              "events": [[0, 60, -1, 0], [100, 125, 0, 0], [300, 360, -1, 1],
                         [400, 425, 0, 1]],
              "stops": [{"station_id": "stn.x"}]}]
    riders = {"stn.x": [600.0] * 24}
    TR.boarding(lines, riders)
    st = lines[0]["stops"][0]
    # (two calls a cycle: 2 x 4 trains x 6 cycles an hour = 48 calls, 600 people: 12.5 a train)
    assert st["calls_h"][1] == pytest.approx(48.0)
    assert st["board"][1] == pytest.approx(12.5) and st["alight"] == st["board"]
    # (at least the band's minimum, at most the mode's most)
    TR.boarding(lines, {"stn.x": [0.0] * 24})
    assert lines[0]["stops"][0]["board"] == [float(v) for v in P.TRANSIT["board_min"]]
    TR.boarding(lines, {"stn.x": [1.0e6] * 24})
    assert max(lines[0]["stops"][0]["board"]) == P.TRANSIT_MODES["metro"]["board_max"]


def test_exporter_packs_transit(build: Path):
    from citygen import unreal_life as UL
    PL.build_plan(build, preview=False)
    m = _model()
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in m["walkways"]]
    lanes = [{"id": "l1", "kind": "lane", "width": 3.6, "points": [[300, -2, 0], [350, -2, 0]],
              "links": []}]
    graphs = {"walkways": _flat(walks), "lanes": _flat(lanes)}
    lf = UL.write_life(build, None, graphs, None)
    assert lf["transit"]["lines"] == 1 and lf["transit"]["modes"] == ["metro"]
    c = json.loads((build / "unreal" / "life.json").read_text(encoding="utf-8"))["controller"]
    tt = json.loads((build / "life" / "timetables.json").read_text(encoding="utf-8"))
    ln = tt["lines"][0]
    assert c["transit_line_mode"] == [0] and c["transit_modes"] == ["metro"]
    assert c["transit_line_ids"] == ["tl.m"] and c["transit_line_loop"] == [0]
    assert len(c["transit_line_car"]) == 12 and c["transit_line_car"][0] == ln["cars"]
    assert c["transit_point_starts"] == [0, 2] and len(c["transit_points"]) == 6
    assert c["transit_sample_starts"] == [0, len(ln["samples"])]
    assert len(c["transit_events"]) == 4 * len(ln["events"])
    assert c["transit_line_trains"] == ln["trains"]
    # (the stop's board walkway the stairs' lane; the station's street access served)
    ids = [w["id"] for w in m["walkways"]]
    assert c["transit_stop_lane"] == [ids.index("wk.s")]
    assert c["transit_stop_level"] == [0]
    assert len(c["walk_clear"]) == len(ids) and max(c["walk_clear"]) == 0.0
    assert len(c["door_transit"]) == len(c["door_lanes"]) and sum(c["door_transit"]) == 1
    # (the model table: a car's parts per mode, 8 floats each, the basic shapes)
    parts = UL.TRANSIT_MODELS["metro"]
    assert c["transit_part_starts"] == [0, len(parts)]
    assert len(c["transit_parts"]) == 8 * len(parts)
    assert c["transit_meshes"][0] == "/Engine/BasicShapes/Cube"
    # (a plan before LG6 packs none)
    plan = json.loads((build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    plan["transit"] = None
    assert UL.pack_transit(plan, build / "life", graphs) == {}


def test_every_mode_has_a_model_and_a_headway():
    from citygen import unreal_life as UL
    for mode in P.TRANSIT_MODE_CODES:
        assert mode in P.TRANSIT_MODES and len(P.TRANSIT_HEADWAY_MIN[mode]) == 5
        parts = UL.TRANSIT_MODELS[mode]
        assert parts[0]["kind"] == "body"
        assert all(p["kind"] in UL.TRANSIT_KINDS and p["mesh"] in UL.TRANSIT_MESHES
                   for p in parts)
    # (a sky tube's pods inside its 7 m tube round the line (M19's axis), two side by side on
    # an open line: their bottom corners and top inside it)
    st = P.TRANSIT_MODES["sky_tube"]
    assert math.hypot(st["track_m"] + st["width_m"] / 2.0, st["base_m"]) < 3.5
    assert math.hypot(st["track_m"] + st["width_m"] / 2.0, st["base_m"] + st["height_m"]) < 3.5
