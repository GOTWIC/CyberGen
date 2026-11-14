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
         "width_m": 3.0, "neighbors": ["wk.b"], "attrs": {}},
        {"id": "wk.b", "kind": "sidewalk", "line": [[100.0, -6.0, 0.0], [200.0, -6.0, 0.0]],
         "width_m": 3.0, "neighbors": ["wk.a", "wk.s"], "attrs": {}},
        {"id": "wk.s", "kind": "stairs", "line": [[150.0, -6.0, 0.0], [150.0, -6.0, -8.0]],
         "width_m": 2.0, "neighbors": ["wk.b"], "attrs": {"station": "stn.x"}},
        {"id": "wk.c", "kind": "sidewalk", "line": [[300.0, -6.0, 0.0], [400.0, -6.0, 0.0]],
         "width_m": 3.0, "neighbors": ["wk.b"], "attrs": {}},
    ]
    walks[1]["neighbors"].append("wk.c")
    return {
        "name": "Test Bay", "bounds": [-512.0, -512.0, 512.0, 512.0],
        "districts": [
            {"id": "d01", "name": "Core", "archetype": "corporate_core",
             "params": {"wealth": 0.9, "danger": 0.15}, "polygon": _sq(-10, -100, 250, 100)},
            {"id": "d02", "name": "Old Quarter", "archetype": "old_town",
             "params": {"wealth": 0.3, "danger": 0.65}, "polygon": _sq(250, -100, 500, 100)}],
        "road_segments": [
            {"id": "rs.a", "road_class": "street", "centerline": [[0.0, 0.0], [200.0, 0.0]],
             "attrs": {"length_m": 200.0}},
            {"id": "rs.c", "road_class": "street", "centerline": [[300.0, 0.0], [400.0, 0.0]],
             "attrs": {}}],
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
        "lanes": [
            {"id": "rs.a.f0", "kind": "lane", "centerline": [[0.0, -1.8, 0.0], [200.0, -1.8, 0.0]],
             "width_m": 3.6, "successors": [], "forward": True, "index": 0,
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
                      "access_ids": ["wk.s"]}],
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
        "transit_lines": [{"id": "tl.m", "name": "Metro Line"}],
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
    assert plan.spike.people == min(2000, round(by["d02"].people[23]))
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
    # (the stairs are not a spike walk kind; wk.a meets wk.b at its end, wk.b wk.a at its start)
    assert len(c["walk_starts"]) - 1 == 3
    la = c["walk_links"][c["walk_link_starts"][0]:c["walk_link_starts"][1]]
    lb = c["walk_links"][c["walk_link_starts"][1]:c["walk_link_starts"][2]]
    assert la == [2 * 1 + 1] and 2 * 0 in lb
    assert c["drive_startable"] == [1, 0] and c["drive_links"] == [1]
    assert len(c["car_models"]) == P.SPIKE["cars"] and set(c["car_models"]) == {0}
    assert len(c["car_paints"]) == 9 * P.SPIKE["cars"]
    assert [p["shadow"] for p in c["parts"]] == [True, False]
    assert len(c["palette"]) == 3 * P.SPIKE_PALETTE
    assert UL.actor_hashes(lf) == {"life": lf["hash"]}
    # a plan whose checks failed is named, not imported
    plan = json.loads((build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    plan["checks"]["densities"]["ok"] = False
    (build / "life" / "life_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    assert "skipped" in UL.write_life(build, None, graphs, veh)


def test_drive_lanes_smooth_and_slow_by_class():
    """cars_steam: a drive lane is a centripetal Catmull-Rom curve through its points (every
    point kept, straight runs as chords), its cruise speed by its road's class, a connector the
    junction's share of its slower road, a bend at most sqrt(lateral R), braking before it."""
    import math
    from citygen import unreal_life as UL
    # a right angle: smoothed, every point kept, steps near SMOOTH_STEP_M (it divides the
    # chords; the curve bulges past them), no kink left
    corner = [[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [20.0, 20.0, 0.0]]
    s = UL.smooth(corner)
    assert all(p in s for p in corner)
    assert max(math.dist(a[:2], b[:2]) for a, b in zip(s, s[1:])) <= 1.25 * UL.SMOOTH_STEP_M
    assert max(UL._turn(a, b, c) for a, b, c in zip(s, s[1:], s[2:])) < 30.0
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
