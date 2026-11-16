"""LG0: lifegen's spec, presets, plan format, the asks of citygen and the plan
(docs/lifegen_scope.md), on a small synthetic build (two districts with a few streets,
buildings, walkways, lanes, benches, a bus stop, a taxi stand, a station and a garage), and
the exporter's layer 4 (`citygen/unreal_life.py`)."""

import json
from pathlib import Path

import pytest

from lifegen import asks as A
from lifegen import plan as PL
from lifegen import planmodel as PM
from lifegen import presets as P
from lifegen import spec as S

ROOT = Path(__file__).resolve().parents[2]


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _model() -> dict:
    walks = [
        {"id": "wk.a", "kind": "sidewalk", "line": [[0.0, -6.0, 0.0], [100.0, -6.0, 0.0]],
         "width_m": 3.0, "neighbors": ["wk.b"], "attrs": {"segment": "rs.a"}},
        {"id": "wk.b", "kind": "sidewalk", "line": [[100.0, -6.0, 0.0], [200.0, -6.0, 0.0]],
         "width_m": 3.0, "neighbors": ["wk.a", "wk.s"], "attrs": {"segment": "rs.a"}},
        {"id": "wk.s", "kind": "stairs", "line": [[150.0, -6.0, 0.0], [150.0, -6.0, -8.0]],
         "width_m": 2.0, "neighbors": ["wk.b"], "attrs": {"station": "stn.x"}},
        {"id": "wk.c", "kind": "sidewalk", "line": [[300.0, -6.0, 0.0], [400.0, -6.0, 0.0]],
         "width_m": 3.0, "neighbors": ["wk.b"], "attrs": {"segment": "rs.c"}},
        # (LG3: the crosswalks of a signalized junction at rs.a's end, where rs.n leaves north)
        {"id": "wk.xa", "kind": "crosswalk",
         "line": [[192.0, -6.0, 0.0], [195.0, -5.0, 0.0], [195.0, 5.0, 0.0], [192.0, 6.0, 0.0]],
         "width_m": 3.0, "neighbors": ["wk.b", "wk.xn"],
         "attrs": {"junction": "jn.x", "crosswalk": True}},
        {"id": "wk.xn", "kind": "crosswalk",
         "line": [[193.0, 7.0, 0.0], [195.0, 5.0, 0.0], [205.0, 5.0, 0.0], [207.0, 7.0, 0.0]],
         "width_m": 3.0, "neighbors": ["wk.xa"],
         "attrs": {"junction": "jn.x", "crosswalk": True}},
    ]
    walks[1]["neighbors"] += ["wk.c", "wk.xa"]
    return {
        "name": "Test Bay", "bounds": [-512.0, -512.0, 512.0, 512.0],
        "districts": [
            {"id": "d01", "name": "Core", "archetype": "corporate_core",
             "params": {"wealth": 0.9, "danger": 0.15}, "polygon": _sq(-10, -100, 250, 100)},
            {"id": "d02", "name": "Old Quarter", "archetype": "old_town",
             "params": {"wealth": 0.3, "danger": 0.65}, "polygon": _sq(250, -100, 500, 100)}],
        "road_segments": [
            {"id": "rs.a", "road_class": "street", "centerline": [[0.0, 0.0], [200.0, 0.0]],
             "attrs": {"length_m": 200.0}, "start": "rn.w", "end": "rn.x"},
            {"id": "rs.c", "road_class": "street", "centerline": [[300.0, 0.0], [400.0, 0.0]],
             "attrs": {}},
            {"id": "rs.n", "road_class": "street", "centerline": [[200.0, 0.0], [200.0, 90.0]],
             "attrs": {}}],
        "junctions": [
            {"id": "jn.x", "node_id": "rn.x", "signalized": True,
             "crosswalk_ids": ["cw.a", "cw.n"],
             "attrs": {"cuts": [["rs.a", "b", 5.0], ["rs.n", "a", 5.0]]}},
            {"id": "jn.y", "signalized": False, "crosswalk_ids": [], "attrs": {"cuts": []}}],
        "crosswalks": [
            {"id": "cw.a", "junction_id": "jn.x", "segment_id": "rs.a", "signalized": True,
             "line": [[195.0, -5.0], [195.0, 5.0]], "width_m": 3.0},
            {"id": "cw.n", "junction_id": "jn.x", "segment_id": "rs.n", "signalized": True,
             "line": [[195.0, 5.0], [205.0, 5.0]], "width_m": 3.0}],
        "densities": [
            {"id": "rs.a.density", "segment_id": "rs.a", "district_id": "d01",
             "crowd_per_100m": [2.0, 10.0, 8.0, 12.0, 4.0],
             "vehicles_per_100m": [1.0, 5.0, 4.0, 6.0, 2.0],
             "gang_per_100m": [0.0] * 5, "police_per_100m": [0.1] * 5},
            {"id": "rs.c.density", "segment_id": "rs.c", "district_id": "d02",
             "crowd_per_100m": [6.0, 4.0, 5.0, 8.0, 12.0],
             "vehicles_per_100m": [0.5, 2.0, 2.0, 3.0, 2.0],
             "gang_per_100m": [0.5] * 5, "police_per_100m": [0.05] * 5}],
        "walkways": walks,
        # (LG5: rs.a both ways, a turning connector at each end: the lane graph's main part)
        "lanes": [
            {"id": "rs.a.f0", "kind": "lane", "segment_id": "rs.a",
             "centerline": [[0.0, -1.8, 0.0], [200.0, -1.8, 0.0]],
             "width_m": 3.6, "successors": ["rs.a.f0.c1"], "forward": True, "index": 0,
             "adjacent_ids": []},
            {"id": "rs.a.f0.c1", "kind": "connector", "node_id": "rn.x",
             "centerline": [[200.0, -1.8, 0.0], [202.0, 0.0, 0.0], [200.0, 1.8, 0.0]],
             "width_m": 3.6, "successors": ["rs.a.b0"], "forward": True, "index": 0,
             "adjacent_ids": []},
            {"id": "rs.a.b0", "kind": "lane", "segment_id": "rs.a",
             "centerline": [[200.0, 1.8, 0.0], [0.0, 1.8, 0.0]],
             "width_m": 3.6, "successors": ["rs.a.b0.c1"], "forward": False, "index": 0,
             "adjacent_ids": []},
            {"id": "rs.a.b0.c1", "kind": "connector", "node_id": "rn.w",
             "centerline": [[0.0, 1.8, 0.0], [-2.0, 0.0, 0.0], [0.0, -1.8, 0.0]],
             "width_m": 3.6, "successors": ["rs.a.f0"], "forward": True, "index": 0,
             "adjacent_ids": []}],
        "buildings": [
            {"id": "d01.lot.e50n20.bld", "district_id": "d01", "floors": 20,
             "footprint": _sq(30, 10, 70, 40),
             "entrances": [{"position": [50.0, -4.5], "kind": "main", "walkway_id": "wk.a"},
                           {"position": [60.0, -4.5], "kind": "service", "walkway_id": "wk.a"}]},
            {"id": "d01.lot.e150n20.bld", "district_id": "d01", "floors": 8,
             "footprint": _sq(130, 10, 170, 40),
             "entrances": [{"position": [150.0, -4.5], "kind": "main", "walkway_id": "wk.b"}]},
            {"id": "d02.lot.e350n20.bld", "district_id": "d02", "floors": 4,
             "footprint": _sq(330, 10, 370, 40),
             "entrances": [{"position": [350.0, -4.5], "kind": "main", "walkway_id": "wk.c"}]},
            {"id": "d02.lot.e380n20.bld", "district_id": "d02", "floors": 3,
             "footprint": _sq(375, 10, 395, 40),
             "entrances": [{"position": [385.0, -4.5], "kind": "main", "walkway_id": "wk.c"}]},
            {"id": "d02.lot.e320n20.bld", "district_id": "d02", "floors": 3,
             "footprint": _sq(305, 10, 325, 40), "entrances": []}],
        "stations": [{"id": "stn.x", "kind": "underground", "position": [150.0, -6.0, -8.0],
                      "access_ids": ["wk.s"], "line_ids": ["tl.m"]}],
        "parking": [{"id": "d01.lot.e10n50.bld.garage", "kind": "garage", "district_id": "d01",
                     "capacity": 100,
                     "entrances": [{"position": [10.0, -4.5], "walkway_id": "wk.a",
                                    "lane_id": "rs.a.f0"}]}],
        "travel_points": [{"id": "rs.c.taxi", "kind": "taxi_stand", "district_id": "d02",
                           "position": [360.0, -2.0],
                           "access": {"position": [360.0, -6.0], "walkway_id": "wk.c",
                                      "lane_id": None}}],
        "props": [
            {"id": "d01.prop.bench.e80s8", "type": "prop.bench", "position": [80.0, -8.0, 0.0],
             "yaw_deg": 90.0},
            {"id": "d02.prop.bus_stop.e320s8", "type": "prop.bus_stop",
             "position": [320.0, -8.0, 0.0], "yaw_deg": -90.0, "attrs": {}},
            {"id": "d02.prop.trash_can.e330s8", "type": "prop.trash_can",
             "position": [330.0, -8.0, 0.0], "yaw_deg": 0.0}],
        "factions": [{"id": "fac.red", "kind": "gang", "home_district_id": "d02",
                      "color": "#aa2233"}],
        # (LG6: a metro under rs.a's sidewalk, its station's stairs the board walkway)
        "transit_lines": [{"id": "tl.m", "name": "Metro Line", "mode": "metro",
                           "color": "#2f7bff", "loop": False, "station_ids": ["stn.x"],
                           "path": [[-20.0, -6.0, -12.0], [420.0, -6.0, -12.0]]}],
    }


@pytest.fixture
def build(tmp_path: Path) -> Path:
    b = tmp_path / "city"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    return b


# --- presets and spec -------------------------------------------------------------------------

def test_bands_and_shape_keep_every_band():
    assert [P.band_of(h) for h in (0, 5, 6, 9, 10, 15, 16, 19, 20, 23)] == \
        [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    for raw in P.DAY_SHAPE.values():
        shp = S.shape(raw)
        for _, a, b in P.HOUR_BANDS:
            assert sum(shp[a:b]) / (b - a) == pytest.approx(1.0, abs=2e-3)


def test_empty_spec_and_names():
    m = _model()
    assert S.validate_spec({}, m).ok
    bad = S.validate_spec({"population": {"Cor": {"busy": 2.0}},
                           "transit": {"headway_min": {"Metro Lin": [5, 5, 5, 5, 5]}}}, m)
    assert not bad.ok
    msgs = " ".join(str(i) for i in bad.issues)
    assert "did you mean 'Core'" in msgs and "did you mean 'Metro Line'" in msgs
    assert not S.validate_spec({"budgets": {"people_view": -1}}).ok
    assert not S.validate_spec({"population": {"Core": {"mix": [0, 0, 0]}}}).ok


def test_fill_resolves_districts_and_the_fleet():
    spec = S.validate_spec({"fleet": {"weights": {"tanager_cab": 0.0}},
                            "styles": {"districts": {"Core": {"groups": {"punk": 1.0}}}}}).spec
    cars = ["tanager_cab", "tanager_mino", "halcyon_sable", "brakk_mule"]
    f = S.fill(spec, _model()["districts"], cars)
    core, old = f["districts"]["d01"], f["districts"]["d02"]
    assert set(core["fleet"]) <= set(cars) and "tanager_cab" not in core["fleet"]
    assert core["style"]["groups"] == {"punk": 1.0}
    assert abs(sum(old["mix"].values()) - 1.0) < 1e-3
    # (decision 12.7: the frame budget is 20 ms p95; 12.8: stepping aside and looking)
    assert f["budgets"]["frame_p95_ms"] == 20.0
    assert f["reactions"] == {"step_aside": True, "look": True, "flee": False, "gather": False}
    # (wear up where poor and dangerous)
    assert old["style"]["wear"] > core["style"]["wear"]


def test_schemas_match_the_committed_ones():
    got = json.loads((ROOT / "lifegen" / "schemas" / "life_spec.schema.json").read_text())
    assert got == json.loads(json.dumps(S.json_schema(), sort_keys=True))
    for which, (model, title) in PM.SCHEMAS.items():
        got = json.loads((ROOT / "lifegen" / "schemas" / f"{which}.schema.json").read_text())
        assert got == json.loads(json.dumps(PM.json_schema(model, title), sort_keys=True)), which


# --- the plan ---------------------------------------------------------------------------------

def test_plan_on_a_small_city(build: Path):
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"], rep["checks"]
    out = build / "life"
    plan = PM.LifePlan.model_validate_json((out / "life_plan.json").read_text(encoding="utf-8"))
    by = {d.id: d for d in plan.districts}
    # people by hour keep M11's band densities (rs.a: 200 m, crowd 10 per 100 m by morning)
    assert sum(by["d01"].people[6:10]) / 4 == pytest.approx(20.0, abs=0.05)
    assert sum(by["d02"].people[20:24]) / 4 == pytest.approx(12.0, abs=0.05)
    # spawn points: entrances, the station's stairs, the garage, the taxi stand; slots
    tiles = [PM.TileSpawns.model_validate_json((out / t.file).read_text(encoding="utf-8"))
             for t in plan.tiles]
    spawns = {s.id: s for t in tiles for s in t.spawns}
    assert set(spawns) == {"spawn.d01.lot.e50n20.bld.e0", "spawn.d01.lot.e50n20.bld.e1",
                           "spawn.d01.lot.e150n20.bld.e0", "spawn.d02.lot.e350n20.bld.e0",
                           "spawn.d02.lot.e380n20.bld.e0", "spawn.stn.x.a0",
                           "spawn.d01.lot.e10n50.bld.garage.e0", "spawn.rs.c.taxi"}
    st = spawns["spawn.stn.x.a0"]
    assert st.district_id == "d01" and st.pos[2] == 0.0       # (the stair's street end)
    # (a district's spawns share its people turned over every TRIP_MIN minutes)
    d01 = [s for s in spawns.values() if s.district_id == "d01"]
    assert sum(s.rates[8] for s in d01) == pytest.approx(by["d01"].people[8] * 4, rel=1e-3)
    slots = {s.id: s for t in tiles for s in t.slots}
    assert set(slots) == {"slot.d01.prop.bench.e80s8", "slot.d02.prop.bus_stop.e320s8",
                          "slot.rs.c.taxi"}
    assert slots["slot.d01.prop.bench.e80s8"].behavior == "sit"
    # the spike: the district with the most buildings, its palette with the gang's color
    assert plan.spike.district_id == "d02" and plan.spike.cars == P.SPIKE["cars"]
    assert len(plan.spike.palette) == P.SPIKE_PALETTE
    # (LG3: the city's crowd walks every street; the spike keeps only its cars)
    assert plan.spike.people == 0 and plan.crowd.pool == P.CROWD["pool"]
    # the asks: what the model lacks
    asks = {a.id: a.status for a in plan.asks}
    assert asks["bus_routes"] == "missing" and asks["signal_phases"] == "derived"
    # the contribution: the controller and a spawner per tile
    con = json.loads((out / "unreal_contribution.life.json").read_text(encoding="utf-8"))
    assert con["layer"] == 4 and con["entries"][0]["key"] == "life"
    # an unchanged plan writes nothing
    again = PL.build_plan(build, preview=False)
    assert again["wrote"] == [] and again["plan_hash"] == rep["plan_hash"]


def test_a_spawn_reaching_no_other_fails(build: Path):
    m = _model()
    m["walkways"][3]["neighbors"] = []          # wk.c cut off
    m["walkways"][1]["neighbors"] = ["wk.a", "wk.s"]
    m["buildings"] = [b for b in m["buildings"] if b["id"] != "d02.lot.e380n20.bld"]
    m["travel_points"] = []
    (build / "city_model.json").write_text(json.dumps(m), encoding="utf-8")
    rep = PL.build_plan(build, preview=False)
    assert not rep["ok"] and not rep["checks"]["spawns_reach"]["ok"]


def test_asks_met_when_the_model_has_them():
    m = _model()
    m["bus_routes"] = [{"id": "bus.1"}]
    m["lanes"][0]["restricted"] = False
    st = {a["id"]: a["status"] for a in A.status(m, {"doors": True})}
    assert st["bus_routes"] == "met" and st["turn_restrictions"] == "met"
    assert st["doors"] == "met" and st["piers"] == "missing"


# --- the exporter's layer 4 -------------------------------------------------------------------

def _flat(elems):
    from citygen.unreal import _flat as flat
    return flat(elems)


def test_exporter_packs_the_spike(build: Path):
    from citygen import unreal_life as UL
    PL.build_plan(build, preview=False)
    m = _model()
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in m["walkways"]]
    lanes = [{"id": "l1", "kind": "lane", "width": 3.6, "points": [[300, -2, 0], [350, -2, 0]],
              "links": ["c1"]},
             {"id": "c1", "kind": "connector", "width": 3.6,
              "points": [[350, -2, 0], [360, 2, 0]], "links": []}]
    graphs = {"walkways": _flat(walks), "lanes": _flat(lanes)}
    veh = {"cars": {"tanager_mino": {"folder": "/Game/CityGen/Vehicles/tanager_mino",
                                     "parts": [{"name": "body", "kind": "body",
                                                "pivot": [0, 0, 0]},
                                               {"name": "wheel_fl", "kind": "wheel",
                                                "pivot": [1.2, 0.7, 0.3]}]}}}
    lf = UL.write_life(build, None, graphs, veh)
    assert lf["key"] == "life" and lf["models"] == ["tanager_mino"]
    data = json.loads((build / "unreal" / "life.json").read_text(encoding="utf-8"))
    c = data["controller"]
    # (LG3: every walkway of the city, the stairs and crosswalks too; wk.a meets wk.b at its
    # end, wk.b wk.a at its start)
    assert len(c["walk_starts"]) - 1 == 6
    la = c["walk_links"][c["walk_link_starts"][0]:c["walk_link_starts"][1]]
    lb = c["walk_links"][c["walk_link_starts"][1]:c["walk_link_starts"][2]]
    assert la == [2 * 1 + 1] and 2 * 0 in lb
    assert c["drive_startable"] == [1, 0] and c["drive_links"] == [1]
    # (LG5: no spike cars; the traffic's pool drives the city's lanes, its models the plan's
    # the project has)
    assert c["car_models"] == [] and c["car_paints"] == []
    assert c["cars"] == P.TRAFFIC["pool"] == len(c["traffic_slots"])
    assert set(c["traffic_slots"]) == {0}
    assert [p["shadow"] for p in c["parts"]] == [True, False]
    assert len(c["palette"]) == 3 * P.SPIKE_PALETTE
    assert UL.actor_hashes(lf) == {"life": lf["hash"]}
    # a plan whose checks failed is named, not imported
    plan = json.loads((build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    plan["checks"]["densities"]["ok"] = False
    (build / "life" / "life_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    assert "skipped" in UL.write_life(build, None, graphs, veh)


def test_drive_lanes_smooth_and_slow_by_class():
    """cars_steam: a drive lane's sharp corners rounded off by arcs, then a centripetal
    Catmull-Rom curve through its points (ends kept, straight runs as chords), its cruise speed
    by its road's class, a connector the junction's share of its slower road, a bend at most
    sqrt(lateral R), braking before it."""
    import math
    from citygen import unreal_life as UL
    # a right angle: its ends kept, its corner cut by FILLET_CUT_M at most (an arc of radius
    # FILLET_CUT_M / (sqrt 2 - 1) there), steps near SMOOTH_STEP_M, no kink left
    corner = [[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [20.0, 20.0, 0.0]]
    s = UL.smooth(corner)
    assert s[0] == corner[0] and s[-1] == corner[-1]
    cut = min(math.dist(p[:2], (20.0, 0.0)) for p in s)
    assert UL.FILLET_CUT_M - 0.05 < cut < UL.FILLET_CUT_M + 0.05
    assert max(math.dist(a[:2], b[:2]) for a, b in zip(s, s[1:])) <= 1.25 * UL.SMOOTH_STEP_M
    assert max(UL._turn(a, b, c) for a, b, c in zip(s, s[1:], s[2:])) < 20.0
    # a gentle bend keeps its point
    gentle = [[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [40.0, 2.0, 0.0]]
    assert gentle[1] in UL.smooth(gentle)
    # a straight lane stays its two points
    assert UL.smooth([[0.0, 0.0, 0.0], [50.0, 0.0, 1.0]]) == [[0.0, 0.0, 0.0], [50.0, 0.0, 1.0]]
    # a bend of radius 10 m: about sqrt(2 * 10) m/s at the bend, the cruise speed at its ends
    arc = [[10.0 * math.sin(a / 10.0), 10.0 - 10.0 * math.cos(a / 10.0), 0.0]
           for a in range(0, 16)]
    v = UL.lane_vmax(arc, 9.5, 2.0)
    assert v[0] == 9.5 and v[-1] == 9.5 and abs(v[8] - math.sqrt(20.0)) < 0.1
    # a hairpin crawls at the floor, no slower
    assert min(UL.lane_vmax([[0, 0, 0], [0.5, 0, 0], [0, 0.01, 0]], 9.5, 2.0, 2.0)) == 2.0

    # an avenue lane, then a connector turning onto a street lane
    def flat(elems):
        out = {"count": len(elems), "kinds": [], "refs": [], "widths": [], "point_start": [0],
               "points": [], "link_start": [0], "links": []}
        for e in elems:
            out["kinds"].append(e[1])
            out["refs"].append(e[2])
            out["widths"].append(3.5)
            for p in e[3]:
                out["points"] += p
            out["point_start"].append(len(out["points"]) // 3)
            out["links"] += e[4]
            out["link_start"].append(len(out["links"]))
        return out
    lanes = flat([("l1", "lane", "rs.av", [[0, 0, 0], [100, 0, 0]], [1]),
                  ("c1", "connector", "jn.a", [[100, 0, 0], [108, 2, 0], [110, 10, 0]], [2]),
                  ("l2", "lane", "rs.st", [[110, 10, 0], [110, 80, 0]], [])])
    spike = {"center": [50.0, 0.0], "radius_m": 200.0, "walk_kinds": [],
             "drive_speeds": dict(P.DRIVE_SPEEDS), "drive": dict(P.DRIVE),
             "road_classes": {"rs.av": "avenue", "rs.st": "street"}}
    c = UL.pack_lanes({"walkways": flat([]), "lanes": lanes}, spike)
    assert c["drive_cruise"] == [P.DRIVE_SPEEDS["avenue"],
                                 round(P.DRIVE["junction"] * P.DRIVE_SPEEDS["street"], 3),
                                 P.DRIVE_SPEEDS["street"]]
    st = c["drive_starts"]
    v1 = c["drive_vmax"][st[0]:st[1]]
    vc = c["drive_vmax"][st[1]:st[2]]
    # the avenue lane brakes to the connector's speed at its end, cruises at its start
    assert v1[0] == P.DRIVE_SPEEDS["avenue"] and v1[-1] <= vc[0] + 1e-6
    assert len(vc) > 3 and max(vc) <= P.DRIVE["junction"] * P.DRIVE_SPEEDS["street"] + 1e-6
    # (a plan before cars_steam: no speeds, LG0's cruise in the runtime)
    old = UL.pack_lanes({"walkways": flat([]), "lanes": lanes},
                        {k: spike[k] for k in ("center", "radius_m", "walk_kinds")})
    assert set(old["drive_vmax"]) == {0.0}


# --- LG3: crowds on the streets ---------------------------------------------------------------

def _walks(out: Path, plan) -> dict:
    return {w.id: w for t in plan.tiles for w in PM.TileSpawns.model_validate_json(
        (out / t.file).read_text(encoding="utf-8")).walks}


def test_crowd_on_every_walkway(build: Path):
    """Every walkway's people per hour band: a segment's M11 people on its own walkways by
    length (its district's busy in), the rest at the district's mean sidewalk density times
    their kind's share; the checks pass; the crowd's pool drawn from the library."""
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"], {k: c for k, c in rep["checks"].items() if not c["ok"]}
    for k in ("crowd_densities", "crowd_levels", "signals", "crowd_budget", "crowd_spawns",
              "people_draws"):
        assert rep["checks"][k]["ok"], k
    out = build / "life"
    plan = PM.LifePlan.model_validate_json((out / "life_plan.json").read_text(encoding="utf-8"))
    w = _walks(out, plan)
    assert set(w) == {"wk.a", "wk.b", "wk.s", "wk.c", "wk.xa", "wk.xn"}
    # (rs.a: 200 m at 10 per 100 m by morning, 20 people on its two sidewalks by length)
    assert w["wk.a"].street and w["wk.a"].people[1] == pytest.approx(10.0, abs=1e-3)
    assert w["wk.a"].people[1] + w["wk.b"].people[1] == pytest.approx(20.0, abs=1e-3)
    assert w["wk.c"].district_id == "d02" and w["wk.c"].people[4] == pytest.approx(12.0, abs=1e-3)
    # (off-street: the stairs along their rise, the crosswalks; d01's sidewalks 0.1 a meter)
    dens = 20.0 / 200.0
    assert not w["wk.s"].street and w["wk.s"].length_m == pytest.approx(8.0)
    assert w["wk.s"].people[1] == pytest.approx(P.OFFSTREET["stairs"] * dens * 8.0, abs=1e-3)
    assert w["wk.xa"].people[1] == pytest.approx(
        P.OFFSTREET["crosswalk"] * dens * w["wk.xa"].length_m, abs=1e-3)
    c = plan.crowd
    assert c.pool == P.CROWD["pool"] and len(c.persons["character"]) == c.pool
    assert set(c.palettes) == {"d01", "d02"} and len(c.palettes["d02"]) == P.SPIKE_PALETTE
    assert max(c.persons["tint"]) < P.SPIKE_PALETTE
    assert c.totals["levels"] == [0] and c.totals["signals"] == 1
    # (the hours within a band shaped by the district's day; the street people keep M11's)
    by = {d.id: d for d in plan.districts}
    assert c.totals["street_people"][8] == pytest.approx(by["d01"].people[8] + by["d02"].people[8],
                                                         abs=0.2)


def test_signals_two_phases(build: Path):
    """A signalized junction's phases: legs by their lines (rs.a and rs.n square, apart),
    each crosswalk walking while the leg it crosses is stopped, the phases filling the
    cycle; its crosswalk walkways in their phase."""
    PL.build_plan(build, preview=False)
    out = build / "life"
    sg = PM.Signals.model_validate_json((out / "signals.json").read_text(encoding="utf-8"))
    assert sg.derived and [s.id for s in sg.signals] == ["sig.jn.x"]
    s = sg.signals[0]
    p0, p1 = s.phases
    assert p0.legs == ["rs.a"] and p1.legs == ["rs.n"]
    assert p0.crosswalks == ["cw.n"] and p1.crosswalks == ["cw.a"]
    assert p0.walkways == ["wk.xn"] and p1.walkways == ["wk.xa"]
    assert 0.0 <= s.offset_s < s.cycle_s == P.SIGNAL["cycle_s"]
    assert sum(p.green_s + p.amber_s + p.all_red_s for p in s.phases) == pytest.approx(s.cycle_s)
    plan = PM.LifePlan.model_validate_json((out / "life_plan.json").read_text(encoding="utf-8"))
    w = _walks(out, plan)
    assert (w["wk.xa"].signal, w["wk.xa"].phase) == ("sig.jn.x", 1)
    assert w["wk.a"].signal is None


def test_a_walkway_nobody_reaches_is_left_empty(build: Path):
    m = _model()
    m["walkways"].append({"id": "wk.lone", "kind": "sidewalk", "width_m": 3.0, "neighbors": [],
                          "line": [[0.0, 60.0, 0.0], [50.0, 60.0, 0.0]],
                          "attrs": {"segment": "rs.a"}})
    (build / "city_model.json").write_text(json.dumps(m), encoding="utf-8")
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"] and rep["crowd"]["left_out"]["walkways"] == 1
    plan = PM.LifePlan.model_validate_json(
        (build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    assert _walks(build / "life", plan)["wk.lone"].people == [0.0] * 5


def test_ag3_doors_are_the_spawn_points(build: Path):
    """With stage 2's buildings, AG3's doors (a door per entrance and shop unit, on the
    facade, opening to its walkway) are the spawn points in place of M3's entrances."""
    con = {"entries": [{"key": "d01.lot.e50n20.bld", "ids": ["d01.lot.e50n20.bld"],
                        "pivot": [50.0, 25.0, 0.0],
                        "doors": [{"id": "d01.lot.e50n20.bld.door.e0", "kind": "main",
                                   "walkway_id": "wk.a", "position": [0.0, -15.0, 0.0],
                                   "normal": [0.0, -1.0], "width_m": 2.0, "height_m": 2.4},
                                  {"id": "d01.lot.e50n20.bld.door.u0", "kind": "shop",
                                   "use": "bar", "walkway_id": "wk.a",
                                   "position": [8.0, -15.0, 0.0], "normal": [0.0, -1.0],
                                   "width_m": 1.1, "height_m": 2.3},
                                  {"id": "d01.lot.e50n20.bld.door.u1", "kind": "shop",
                                   "use": "food", "walkway_id": None,
                                   "position": [-8.0, -15.0, 0.0], "normal": [0.0, -1.0],
                                   "width_m": 1.1, "height_m": 2.3}]}]}
    (build / "assets").mkdir()
    (build / "assets" / "unreal_contribution.buildings.json").write_text(json.dumps(con),
                                                                        encoding="utf-8")
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"] and rep["totals"]["doors"] == 2
    out = build / "life"
    plan = PM.LifePlan.model_validate_json((out / "life_plan.json").read_text(encoding="utf-8"))
    spawns = {s.id: s for t in plan.tiles for s in PM.TileSpawns.model_validate_json(
        (out / t.file).read_text(encoding="utf-8")).spawns}
    door = spawns["spawn.d01.lot.e50n20.bld.door.u0"]
    assert door.sub == "shop.bar" and door.pos == [58.0, 10.0, 0.0] and door.yaw_deg == -90.0
    assert door.district_id == "d01" and door.walkway_id == "wk.a"
    # (no M3 entrance any more; the station, garage and taxi stand stay)
    assert "spawn.d01.lot.e50n20.bld.e0" not in spawns and "spawn.stn.x.a0" in spawns
    assert {a.id: a.status for a in plan.asks}["doors"] == "met"


def test_exporter_packs_the_crowd(build: Path):
    """The exporter packs every walkway with its kind, district, people per band and signal
    window; the doors on their walkways; the districts' days and palettes; the pool."""
    from citygen import unreal_life as UL
    PL.build_plan(build, preview=False)
    m = _model()
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in m["walkways"]]
    lanes = [{"id": "l1", "kind": "lane", "width": 3.6, "points": [[0, -2, 0], [50, -2, 0]],
              "links": []}]
    graphs = {"walkways": _flat(walks), "lanes": _flat(lanes)}
    data, why = UL.life_data(build / "life", graphs, None, None)
    assert why == ""
    c = data["controller"]
    ids = [w["id"] for w in m["walkways"]]
    k = {i: n for n, i in enumerate(ids)}
    codes = list(P.WALK_KIND_CODES)
    assert c["walk_kinds"] == [codes.index(w["kind"]) for w in m["walkways"]]
    assert c["walk_district"][k["wk.c"]] == 1 and c["walk_district"][k["wk.a"]] == 0
    assert c["walk_people"][5 * k["wk.a"] + 1] == pytest.approx(10.0, abs=1e-3)
    # (the signal windows: cycle, offset, walk from, walk to; wk.xa walks in phase 1)
    win = c["signal_windows"]
    assert len(win) == 8 and c["walk_signal"][k["wk.a"]] == -1
    s = c["walk_signal"][k["wk.xa"]]
    assert win[4 * s:4 * s + 4][2:] == [P.SIGNAL["cycle_s"] / 2,
                                        P.SIGNAL["cycle_s"] / 2 + P.SIGNAL["walk_s"]]
    # (the doors: every spawn point on its walkway lane, at its distance along it)
    assert len(c["door_lanes"]) == 8 and len(c["door_points"]) == 24
    pts = c["door_points"]
    j = next(n for n in range(0, len(pts), 3) if pts[n:n + 2] == [150.0, -6.0])  # (the station)
    assert c["door_lanes"][j // 3] == k["wk.s"] and c["door_dists"][j // 3] == 0.0
    assert len(c["district_shape"]) == 48 and c["palette_size"] == P.SPIKE_PALETTE
    assert len(c["district_palettes"]) == 2 * 3 * P.SPIKE_PALETTE
    assert len(c["person_char"]) == P.CROWD["pool"] == c["people"]
    assert len(c["person_tint_index"]) == P.CROWD["pool"]
    # (LG2: each person's look and group; per district and group its dye colors, its people
    # by group and its wear)
    from lifegen import garments as G
    assert len(c["person_group"]) == P.CROWD["pool"]
    assert max(c["person_char"]) < 24 * G.LOOKS
    ng, nc = c["outfit_groups"], c["outfit_colors"]
    assert ng == len(G.GROUPS) and nc == P.OUTFIT_COLORS
    assert len(c["outfit_palettes"]) == 2 * ng * nc * 3
    assert len(c["district_groups"]) == 2 * ng and len(c["district_wear"]) == 2
    assert abs(sum(c["district_groups"][:ng]) - 1.0) < 1e-3
    assert c["crowd"]["hour"] == P.CROWD["hour"] and c["crowd"]["live_m"] == P.CROWD["live_m"]
    # (the spike's cars keep their drive lanes)
    assert c["drive_startable"] == [1]
    # (the import's summary line names the crowd)
    from citygen.unreal import life_summary
    line = life_summary({"life_plan": {"plan": "x"},
                         "life": {"made": True, "people": c["people"], "cars": 0,
                                  "district": "d02", "walk_lanes": 6, "library": 0,
                                  "crowd": {"pool": c["people"], "hour": 23, "doors": 8,
                                            "signals": 1}}})
    assert "the city's crowd, a pool of 2400" in line and "stand-ins" in line


# --- LG5: traffic -----------------------------------------------------------------------------

def _drives(out: Path) -> dict:
    plan = json.loads((out / "life_plan.json").read_text(encoding="utf-8"))
    rows = {}
    for t in plan["tiles"]:
        tile = PM.TileSpawns.model_validate_json((out / t["file"]).read_text(encoding="utf-8"))
        rows.update({d.id: d for d in tile.drives})
    return rows


def test_traffic_on_every_lane(build: Path):
    """Every lane's cars per hour band from M11's vehicles per 100 m over its segment's lanes
    by length, its district and road class, the signal its end stops at and where (short of
    the crosswalk across it); the pool's slots by the districts' fleets (no Vex or Aurel), the
    districts' paints; the checks."""
    from assetgen.parked.table import EXCLUDED
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"], rep["checks"]
    for k in ("traffic_densities", "traffic_lanes", "traffic_signals", "traffic_budget",
              "traffic_fleet"):
        assert rep["checks"][k]["ok"], (k, rep["checks"][k])
    rows = _drives(build / "life")
    # (connectors carry no cars of their own: only the lanes are rows)
    assert set(rows) == {"rs.a.f0", "rs.a.b0"}
    f0, b0 = rows["rs.a.f0"], rows["rs.a.b0"]
    # rs.a: 200 m, 5 vehicles per 100 m by morning, over its two 200 m lanes (times the
    # traffic's scale)
    assert f0.vehicles[1] == pytest.approx(5.0 * P.TRAFFIC["scale"], abs=1e-3)
    assert b0.vehicles[1] == f0.vehicles[1]
    assert f0.district_id == "d01" and f0.road_class == "street" and f0.main and b0.main
    # rs.a.f0 ends at jn.x, rs.a its phase 0 leg; its cars stop short of cw.a (x 195, 3 m wide)
    assert f0.signal == "sig.jn.x" and f0.phase == 0
    assert f0.stop_back_m == pytest.approx(200.0 - (195.0 - 1.5 - P.TRAFFIC["stop_margin_m"]),
                                           abs=0.01)
    assert b0.signal is None and b0.stop_back_m is None
    plan = PM.LifePlan.model_validate_json(
        (build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    tr = plan.traffic
    assert tr.pool == P.TRAFFIC["pool"] == len(tr.slots) and tr.live_m == P.TRAFFIC["live_m"]
    assert tr.models and not set(tr.models) & set(EXCLUDED)
    assert set(tr.slots) <= set(range(len(tr.models)))
    assert all(c > 0 for c in tr.totals["slots"].values())
    assert set(tr.weights) == {"d01", "d02"} and len(tr.weights["d01"]) == len(tr.models)
    assert len(tr.paints["d02"]) == len(tr.models)
    assert len(tr.paints["d02"][0]) == 9 * P.TRAFFIC["paints"]
    # (rs.c has vehicles and no lane: left out, said so)
    assert tr.totals["left_out"]["segments"] == 1
    # (the hour's cars: the bands by the districts' days)
    band = P.band_of(tr.hour)
    shape = {d.id: d.shape for d in plan.districts}
    assert tr.totals["cars_by_hour"][tr.hour] == pytest.approx(
        2 * f0.vehicles[band] * shape["d01"][tr.hour], abs=0.1)


def test_traffic_off_the_main_part_is_left_out(build: Path):
    """A lane off the lane graph's largest strongly connected part (cars there could never
    leave) gets no cars; what it would have had is said, and the densities still hold."""
    m = _model()
    m["lanes"].append({"id": "rs.c.f0", "kind": "lane", "segment_id": "rs.c",
                       "centerline": [[300.0, -1.8, 0.0], [400.0, -1.8, 0.0]],
                       "width_m": 3.6, "successors": [], "forward": True, "index": 0,
                       "adjacent_ids": []})
    (build / "city_model.json").write_text(json.dumps(m), encoding="utf-8")
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"], rep["checks"]
    c = _drives(build / "life")["rs.c.f0"]
    assert not c.main and c.vehicles == [0.0] * 5 and c.district_id == "d02"
    assert rep["traffic"]["left_out"]["lanes"] == 1
    assert rep["traffic"]["left_out"]["segments"] == 0
    # rs.c's 100 m at 3 vehicles per 100 m in the evening band (times the scale), left out
    assert rep["traffic"]["left_out"]["vehicles"][3] == \
        pytest.approx(3.0 * P.TRAFFIC["scale"], abs=1e-3)


def test_traffic_budget_check_fails_past_the_budget(build: Path):
    (build / "life_spec.json").write_text(json.dumps({"traffic": {"pool": 5000,
                                                                   "live_m": 300.0}}),
                                          encoding="utf-8")
    rep = PL.build_plan(build, build / "life_spec.json", preview=False)
    assert not rep["ok"] and not rep["checks"]["traffic_budget"]["ok"]


def test_strong_components():
    from citygen import unreal_life as UL
    # 0 -> 1 -> 2 -> 0 a ring, 3 -> 0 a way in, 4 <-> 5 a pair
    succ = [[1], [2], [0], [0], [5], [4]]
    comp = UL.strong_components(succ)
    assert comp[0] == comp[1] == comp[2] and len({comp[3], comp[0], comp[4]}) == 3
    assert comp[4] == comp[5]
    assert UL.main_component(succ) == {0, 1, 2}
    # (a long chain: no recursion limit)
    n = 20000
    chain = [[k + 1] for k in range(n - 1)] + [[0]]
    assert len(UL.main_component(chain)) == n


def test_exporter_packs_the_traffic(build: Path):
    """The exporter packs every lane and connector of the lane graph with its cars per band,
    district, main part, signal window and stop, the connectors it may not share (crossing in
    plan at one height, not one over another), the signals' windows for cars, the pool's slots,
    the fleets and paints, the models' lengths, the wheels' radii and draw distances."""
    from citygen import unreal_life as UL
    from citygen.unreal import life_summary
    PL.build_plan(build, preview=False)
    m = _model()
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in m["walkways"]]
    lanes = [{"id": ln["id"], "kind": ln["kind"], "width": ln["width_m"],
              "points": ln["centerline"], "links": ln["successors"]} for ln in m["lanes"]]
    # (two connectors crossing at grade, a third over them on a deck, a fourth far off)
    lanes += [{"id": "x1", "kind": "connector", "width": 3.0,
               "points": [[100, -10, 0], [110, 10, 0]], "links": []},
              {"id": "x2", "kind": "connector", "width": 3.0,
               "points": [[100, 10, 0], [110, -10, 0]], "links": []},
              {"id": "x3", "kind": "connector", "width": 3.0,
               "points": [[95, 0, 9], [115, 0, 9]], "links": []},
              {"id": "x4", "kind": "connector", "width": 3.0,
               "points": [[300, 50, 0], [310, 50, 0]], "links": []}]
    graphs = {"walkways": _flat(walks), "lanes": _flat(lanes)}
    veh = {"cars": {"tanager_mino": {"folder": "/Game/CityGen/Vehicles/tanager_mino",
                                     "dimensions": {"length": 3.43},
                                     "parts": [{"name": "body", "kind": "body",
                                                "pivot": [0, 0, 0]},
                                               {"name": "wheel_fl", "kind": "wheel",
                                                "pivot": [1.2, 0.7, 0.3], "radius": 0.31,
                                                "spins": True}]}}}
    lf = UL.write_life(build, None, graphs, veh)
    c = json.loads((build / "unreal" / "life.json").read_text(encoding="utf-8"))["controller"]
    ids = [ln["id"] for ln in lanes]
    k = {i: n for n, i in enumerate(ids)}
    rows = _drives(build / "life")
    assert c["drive_cars"][5 * k["rs.a.f0"]:5 * k["rs.a.f0"] + 5] == \
        pytest.approx(rows["rs.a.f0"].vehicles)
    assert c["drive_cars"][5 * k["rs.a.f0.c1"]:5 * k["rs.a.f0.c1"] + 5] == [0.0] * 5
    assert c["drive_district"][k["rs.a.f0"]] == 0
    # (the ring of rs.a's lanes and connectors is the main part; the loose connectors are not)
    assert [c["drive_main"][k[i]] for i in ids[:4]] == [1, 1, 1, 1]
    assert c["drive_main"][k["x1"]] == 0
    # (the signal's windows for cars: cycle, offset, green from, green to, amber to; rs.a.f0
    # moves in phase 0 and stops short of its crosswalk)
    win = c["drive_windows"]
    assert len(win) == 10
    s = c["drive_signal"][k["rs.a.f0"]]
    sg = P.SIGNAL
    green = sg["cycle_s"] / 2 - sg["amber_s"] - sg["all_red_s"]
    assert win[5 * s + 2:5 * s + 5] == pytest.approx([0.0, green, green + sg["amber_s"]])
    assert c["drive_stop_back"][k["rs.a.f0"]] == pytest.approx(rows["rs.a.f0"].stop_back_m)
    assert c["drive_signal"][k["rs.a.b0"]] == -1
    # (conflicts: x1 and x2 cross at grade; x3 passes 9 m over them; x4 is far off)
    cs, cl = c["drive_conflict_starts"], c["drive_conflicts"]
    con = {i: sorted(ids[j] for j in cl[cs[k[i]]:cs[k[i] + 1]]) for i in ids}
    assert con["x1"] == ["x2"] and con["x2"] == ["x1"]
    assert con["x3"] == [] and con["x4"] == [] and con["rs.a.f0"] == []
    # (the pool, the fleet, paints, lengths, wheels, draw distances, settings)
    assert len(c["traffic_slots"]) == P.TRAFFIC["pool"] and set(c["traffic_slots"]) == {0}
    assert len(c["traffic_weights"]) == 2 and len(c["traffic_weights"][0]) == 1
    assert len(c["traffic_paints"][0]) == 9 * c["paints_per"] == 9 * P.TRAFFIC["paints"]
    assert c["car_lengths"] == [3.43]
    assert [p["spin_radius"] for p in c["parts"]] == [0.0, 0.31]
    assert [p["cull_m"] for p in c["parts"]] == [UL.TRAFFIC_CULL_M["body"],
                                                 UL.TRAFFIC_CULL_M["wheel"]]
    t = c["traffic"]
    assert t["pool"] == P.TRAFFIC["pool"] and t["live_m"] == P.TRAFFIC["live_m"]
    assert t["accel"] == P.TRAFFIC["accel"] and t["districts"] == ["d01", "d02"]
    assert lf["traffic"]["conflicts"] == 1 and lf["traffic"]["signal_lanes"] == 1
    # (the import's summary line names the traffic)
    line = life_summary({"life_plan": {"plan": "x"},
                         "life": {"made": True, "people": c["people"], "cars": c["cars"],
                                  "district": "d02", "walk_lanes": 6, "library": 0,
                                  "crowd": {"pool": c["people"], "hour": 23, "doors": 8,
                                            "signals": 1},
                                  "traffic": {"pool": t["pool"], "models": 1,
                                              "live_m": t["live_m"], "lanes": len(ids),
                                              "signal_lanes": 1}}})
    assert f"the city's traffic, a pool of {P.TRAFFIC['pool']} cars" in line
