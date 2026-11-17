"""LG7: air and water (docs/lifegen_scope.md 6.7, checks "Air and water lanes"): the routes of
what flies and floats (`lifegen/airwater.py`) on a small synthetic city made here (two roof pads
with a tower between them, a river with its banks and promenades, a canal with quays and a
moored boat, a sea along the south edge with a harbor basin, a spaceport's launch pad); the
checks failing where they should; the plan's file and contribution; the exporter's pack
(`citygen/unreal_life.py` `pack_airwater`)."""

import copy
import json
import math
from pathlib import Path

import pytest

from lifegen import airwater as AW
from lifegen import plan as PL
from lifegen import planmodel as PM
from lifegen import presets as P
from lifegen import spec as S

from test_lg_plan import _flat, _model, _sq


def _bld(bid, did, x0, y0, x1, y1, h, items=()):
    return {"id": bid, "district_id": did, "floors": int(h / 3.5), "height_m": h,
            "footprint": _sq(x0, y0, x1, y1), "entrances": [],
            "masses": [{"footprint": _sq(x0, y0, x1, y1), "z0_m": 0.0, "z1_m": h,
                        "role": "body", "shape": "prism"}],
            "roof_items": list(items)}


def _pad(x, y, z):
    return {"kind": "av_pad", "position": [x, y, z], "size": [14.0, 14.0, 0.5], "yaw_deg": 0.0}


def _aw_model() -> dict:
    """A city of 1.6 km: pads on two 40 m roofs 700 m apart west of a 160 m tower that stands
    between them, an avenue loop for circuits, a river (x 450 to 550) with promenades on both
    banks, a canal off it with its quays and a moored boat, the sea south of y -600 with a
    deep harbor basin, a spaceport megasite with a launch pad."""
    m = _model()
    m["bounds"] = [-800.0, -800.0, 800.0, 800.0]
    m["districts"] = [
        {"id": "d01", "name": "Core", "archetype": "corporate_core",
         "params": {"wealth": 0.9, "danger": 0.2}, "polygon": _sq(-800, -600, 450, 800)},
        {"id": "d02", "name": "Old Quarter", "archetype": "old_town",
         "params": {"wealth": 0.3, "danger": 0.7}, "polygon": _sq(550, -600, 800, 800)}]
    m["buildings"] = [
        _bld("d01.lot.w600n0.bld", "d01", -620, -20, -580, 20, 40.0, [_pad(-600, 0, 40.0)]),
        _bld("d01.lot.e100n0.bld", "d01", 80, -20, 120, 20, 40.0, [_pad(100, 0, 40.0)]),
        _bld("d01.lot.w250n0.bld", "d01", -280, -40, -220, 40, 160.0),
        _bld("d01.lot.w300n300.bld", "d01", -320, 280, -280, 320, 30.0),
        _bld("d01.lot.w100n300.bld", "d01", -120, 280, -80, 320, 20.0),
        _bld("d01.lot.w300s300.bld", "d01", -320, -320, -280, -280, 25.0)]
    nodes = [("rn.a", -600.0, 400.0), ("rn.b", 300.0, 400.0), ("rn.c", 300.0, -450.0),
             ("rn.d", -600.0, -450.0)]
    m["road_nodes"] = [{"id": n, "position": [x, y]} for n, x, y in nodes]
    m["road_segments"] += [
        {"id": f"rs.av{k}", "road_class": "avenue", "width_m": 18.0, "level": 0,
         "start": nodes[k][0], "end": nodes[(k + 1) % 4][0],
         "centerline": [[nodes[k][1], nodes[k][2]], [nodes[(k + 1) % 4][1], nodes[(k + 1) % 4][2]]],
         "attrs": {}} for k in range(4)]
    river = _sq(450, -600, 550, 800)
    m["rivers"] = [{"id": "rv.test", "name": "Test River", "depth_m": 5.0, "polygon": river,
                    "centerline": [[500.0, 800.0], [500.0, -600.0]],
                    "width_m": [100.0, 100.0],
                    "bed": {"profile": "channel", "reach_m": 50.0, "material": "mud",
                            "surface_m": -1.5},
                    "flow": {"kind": "downstream", "speed_m_s": 0.8, "toward": "sea"}}]
    m["seas"] = [{"id": "sea", "name": "Test Sea", "depth_m": 10.5,
                  "polygons": [_sq(-800, -800, 800, -600)],
                  "bed": {"profile": "shelf", "reach_m": 60.0, "material": "sand",
                          "surface_m": -1.5},
                  "flow": {"kind": "tidal", "speed_m_s": 0.1}}]
    m["waterways"] = [
        {"id": "d02.ww.e650n200", "kind": "canal", "district_id": "d02", "ornamental": False,
         "depth_m": 1.5, "polygon": _sq(550, 191, 800, 209),
         "centerline": [[550.0, 200.0], [800.0, 200.0]],
         "bed": {"profile": "flat", "reach_m": 4.0, "material": "silt", "surface_m": -1.5},
         "flow": {"kind": "tidal", "speed_m_s": 0.05}},
        {"id": "d01.ww.w400s650", "kind": "basin", "district_id": "d01", "ornamental": False,
         "depth_m": 10.5, "polygon": _sq(-460, -640, -340, -560),
         "centerline": [[-400.0, -640.0], [-400.0, -560.0]],
         "bed": {"profile": "flat", "reach_m": 4.0, "material": "mud", "surface_m": -1.5},
         "flow": {"kind": "still", "speed_m_s": 0.0}}]
    m["banks"] = [
        {"id": "rv.test.bank.w", "water_id": "rv.test", "kind": "natural_bank",
         "line": [[450.0, 800.0], [450.0, -600.0]], "width_m": 3.0, "toe_m": 1.5},
        {"id": "rv.test.bank.e", "water_id": "rv.test", "kind": "natural_bank",
         "line": [[550.0, -600.0], [550.0, 191.0]], "width_m": 3.0, "toe_m": 1.5}]
    m["quays"] = [
        {"id": "d02.ww.e650n200.q.n", "waterway_id": "d02.ww.e650n200",
         "line": [[560.0, 209.0], [800.0, 209.0]], "width_m": 5.0, "deck_z_m": 1.5},
        {"id": "d02.ww.e650n200.q.s", "waterway_id": "d02.ww.e650n200",
         "line": [[560.0, 191.0], [800.0, 191.0]], "width_m": 5.0, "deck_z_m": 1.5}]
    m["props"] = m["props"] + [
        {"id": "d02.prop.boat.e700n205", "type": "prop.boat", "position": [700.0, 205.0, -1.5],
         "yaw_deg": 0.0, "scale": [0.75, 0.8, 0.8], "attrs": {"moored": True}}]
    m["walkways"] = m["walkways"] + [
        {"id": "wk.pw", "kind": "promenade", "line": [[440.0, 700.0, 0.0], [440.0, -500.0, 0.0]],
         "width_m": 4.0, "neighbors": [], "attrs": {}},
        {"id": "wk.pe", "kind": "promenade", "line": [[560.0, 700.0, 0.0], [560.0, -500.0, 0.0]],
         "width_m": 4.0, "neighbors": [], "attrs": {}}]
    m["megasites"] = [{"id": "d01.ms.spaceport", "kind": "spaceport", "district_id": "d01",
                       "polygon": _sq(-780, 450, -400, 780),
                       "flight_cone": _sq(-800, 700, -400, 800)}]
    m["site_elements"] = [
        {"id": "d01.ms.spaceport.el.w600n600", "kind": "launch_pad",
         "megasite_id": "d01.ms.spaceport", "attrs": {"radius_m": 30.0},
         "footprint": _sq(-630, 570, -570, 630),
         "masses": [{"footprint": _sq(-630, 570, -570, 630), "z0_m": 0.0, "z1_m": 1.2,
                     "role": "pad", "shape": "cylinder"}]}]
    m["transit_lines"] = []
    m["stations"] = []
    return m


@pytest.fixture(scope="module")
def planned():
    m = _aw_model()
    res = S.load_spec(None, m)
    filled = S.fill(res.spec, m["districts"], PL.library_cars())
    routes, pads, piers, extra = AW.airwater_plan(m, filled, None)
    return m, filled, routes, pads, piers, extra


def _by_kind(routes, kind):
    return [r for r in routes if r["kind"] == kind]


def test_airspace_takes_masses_by_height():
    m = _aw_model()
    sp = AW.AirSpace(m, AW.Ground(m))
    # (the 160 m tower: blocked at 100 m, clear at 200 m; its margin round it)
    assert sp.hit(-250.0, 0.0, 100.0) and not sp.hit(-250.0, 0.0, 200.0)
    assert sp.hit(-218.0, 0.0, 100.0) and not sp.hit(-200.0, 0.0, 100.0)
    b = sp.blocked(100.0)
    j, i = sp.grid.ij(-250.0, 0.0)
    assert b[j, i] and not sp.blocked(200.0)[j, i]


def test_astar_goes_round_a_wall():
    import numpy as np
    c = np.ones((30, 30))
    c[0:25, 15] = np.inf
    path = AW.astar(c, (2, 2), (2, 28))
    assert path is not None and path[0] == (2, 2) and path[-1] == (2, 28)
    assert all(math.isfinite(c[j, i]) for j, i in path)
    assert max(j for j, _ in path) >= 25
    c[25:, 15] = np.inf
    assert AW.astar(c, (2, 2), (2, 28)) is None


def test_pads_flown_between_clear_of_the_tower(planned):
    m, filled, routes, pads, piers, extra = planned
    cars = [r for r in _by_kind(routes, "car") if r["id"].startswith("air.car.")]
    assert len(cars) == 1
    r = cars[0]
    roof = {p["id"] for p in pads if p["kind"] == "av_pad"}
    assert set(r["serves"]) == roof and all(p["served"] for p in pads if p["kind"] == "av_pad")
    # (lands on each pad: a pad dwell at its top; climbs and descends there straight up)
    ev = [e for e in r["events"] if AW.EVENT_CODES[e[2]] == "pad"]
    assert len(ev) == 2 and all(e[1] - e[0] >= P.AW_VEHICLES["car"]["dwell_s"] - 1e-6 for e in ev)
    for p in pads:
        if p["kind"] == "av_pad":
            assert any(math.dist(q[:3], p["pos"]) < 0.05 for q in r["points"])
    # (cruises at least pad_over_m over the roofs, on layers, never in the tower's air)
    tops = max(q[2] for q in r["points"])
    assert tops >= 40.0 + P.AIR["pad_over_m"] - 1e-6
    sp = AW.AirSpace(m, AW.Ground(m), margin=0.0)
    for a, b in zip(r["points"], r["points"][1:]):
        for t in (0.0, 0.25, 0.5, 0.75):
            x, y, z = (a[k] + (b[k] - a[k]) * t for k in range(3))
            if -280 <= x <= -220 and -40 <= y <= 40:
                assert z > 160.0
    ck = AW.checks(routes, pads, piers, extra)
    assert ck["air_lanes"]["ok"], ck["air_lanes"]["detail"]
    assert ck["air_pads"]["ok"], ck["air_pads"]["detail"]


def test_layers_by_heading():
    import types
    air = types.SimpleNamespace()
    L = P.AIR["car_layers"]
    east = AW.Air.layer(air, "car", 0.1, 0.0, 0)
    west = AW.Air.layer(air, "car", math.pi - 0.1, 0.0, 0)
    assert set(east) == set(L[0::2]) and set(west) == set(L[1::2])
    assert min(AW.Air.layer(air, "car", 0.1, 100.0, 0)) >= 100.0


def test_circuits_police_media_aircraft(planned):
    m, filled, routes, pads, piers, extra = planned
    lanes = [r for r in _by_kind(routes, "car") if r["id"].startswith("air.lane.")]
    assert lanes and all(r["counts"][4] >= 0 for r in lanes)
    assert _by_kind(routes, "police") and _by_kind(routes, "aircraft")
    for r in _by_kind(routes, "aircraft"):
        assert min(q[2] for q in r["points"]) >= min(P.AIR["aircraft_m"]) - 1e-6
    # (police orbit over the city by night, at their heights)
    pol = _by_kind(routes, "police")
    assert all(r["counts"][0] >= 1 for r in pol)
    assert all(min(q[2] for q in r["points"]) >= min(P.AIR["police_m"]) - 1e-6 for r in pol)


def test_shuttle_lands_on_its_launch_pad(planned):
    m, filled, routes, pads, piers, extra = planned
    sh = _by_kind(routes, "shuttle")
    assert len(sh) == 1
    lp = next(p for p in pads if p["kind"] == "launch_pad")
    assert lp["served"]
    assert any(math.dist(q[:3], lp["pos"]) < 0.05 for q in sh[0]["points"])
    assert any(AW.EVENT_CODES[e[2]] == "launch" for e in sh[0]["events"])
    # (in from its flight cone's side: the north)
    assert max(q[1] for q in sh[0]["points"]) > 2000.0


def test_boats_keep_right_on_their_water(planned):
    m, filled, routes, pads, piers, extra = planned
    boats = {r["water_id"]: r for r in _by_kind(routes, "boat")}
    assert "rv.test" in boats and "d02.ww.e650n200" in boats
    r = boats["rv.test"]
    # (at the surface; down one side of the river and up the other: right of the middle)
    assert all(abs(q[2] + 1.5) < 1e-6 for q in r["points"] if -580 < q[1] < 780)
    segs = [((a[0] + b[0]) / 2.0, b[1] - a[1]) for a, b in zip(r["points"], r["points"][1:])
            if abs(b[1] - a[1]) > 100.0]
    down = [x for x, dy in segs if dy < 0]
    up = [x for x, dy in segs if dy > 0]
    assert down and up
    assert all(x < 500.0 for x in down) and all(x > 500.0 for x in up)
    # (a canal's boat turns round at its ends, never runs stern first)
    canal = boats["d02.ww.e650n200"]
    yaws = sorted({round(q[3]) % 360 for q in canal["points"]})
    assert any(160 <= y <= 200 for y in yaws) and any(y <= 20 or y >= 340 for y in yaws)
    ck = AW.checks(routes, pads, piers, extra)
    assert ck["water_lanes"]["ok"], ck["water_lanes"]["detail"]
    assert ck["airwater_timing"]["ok"], ck["airwater_timing"]["detail"]
    # (the canal's boat passes clear of the moored one)
    hull = AW._box(700.0, 205.0, 0.0, 6.0, 2.4)
    from shapely.geometry import Point
    assert all(hull.distance(Point(q[0], q[1])) > 1.0 for q in boats["d02.ww.e650n200"]["points"])


def test_piers_and_ferries(planned):
    m, filled, routes, pads, piers, extra = planned
    taxi = [p for p in piers if p["kind"] == "taxi"]
    ferry = [p for p in piers if p["kind"] == "ferry"]
    # (one taxi pier for the canal: the quays across it would put two at one spot)
    assert len(taxi) == 1 and taxi[0]["quay_id"].startswith("d02.ww.e650n200.q.")
    assert any("across the canal" in x["why"] for x in extra["left"]["piers"])
    assert ferry and all(p["walkway_id"] in ("wk.pw", "wk.pe") for p in ferry)
    assert all(p["pair"] in {q["id"] for q in ferry} for p in ferry)
    fr = _by_kind(routes, "ferry")
    assert fr
    # (double-ended: it crosses back stern first, facing the way it faced going over: one
    # heading at each place it passes both ways)
    seen = {}
    for q in fr[0]["points"]:
        seen.setdefault((round(q[0], 1), round(q[1], 1)), set()).add(q[3])
    assert all(len(v) == 1 for v in seen.values())
    assert sum(len(v) for v in seen.values()) < len(fr[0]["points"])
    assert sum(AW.EVENT_CODES[e[2]] == "pier" for e in fr[0]["events"]) == 2


def test_ships_lie_at_a_basin_and_pass_offshore(planned):
    m, filled, routes, pads, piers, extra = planned
    ships = _by_kind(routes, "ship")
    ids = {r["id"] for r in ships}
    assert "water.ship.offshore" in ids
    basin = [r for r in ships if "d01.ww.w400s650" in r["id"]]
    assert basin
    off = next(r for r in ships if r["id"] == "water.ship.offshore")
    # (offshore: out past the map's edge both ways, on water deep enough)
    assert min(q[0] for q in off["points"]) < -800.0 or max(q[0] for q in off["points"]) > 800.0


def test_checks_fail_where_they_should(planned):
    m, filled, routes, pads, piers, extra = planned
    rs = copy.deepcopy(routes)
    car = next(r for r in rs if r["kind"] == "car")
    # (a car's point moved into the tower)
    k = len(car["points"]) // 3
    car["points"][k] = [-250.0, 0.0, 80.0, car["points"][k][3]]
    ck = AW.checks(rs, pads, piers, extra)
    assert not ck["air_lanes"]["ok"]
    rs = copy.deepcopy(routes)
    boat = next(r for r in rs if r["kind"] == "boat")
    boat["points"][2] = [0.0, 0.0, -1.5, boat["points"][2][3]]
    assert not AW.checks(rs, pads, piers, extra)["water_lanes"]["ok"]
    rs = copy.deepcopy(routes)
    d = next(r for r in rs if r["kind"] == "car")
    d["counts"] = [P.AW_BUDGET["fliers"] + 1] * 5
    out = AW.checks(rs, pads, piers, extra)
    assert not out["airwater_budget"]["ok"] and not out["airwater_timing"]["ok"]


def test_vehicles_kept_apart_on_a_route(planned):
    m, filled, routes, pads, piers, extra = planned
    for r in routes:
        for n in r["counts"]:
            if n > 1:
                assert AW._min_gap(r, n) >= P.AW_VEHICLES[r["kind"]]["spacing_m"] - 1e-6


def test_spec_kinds_leave_kinds_out():
    m = _aw_model()
    res = S.validate_spec({"air": {"kinds": {"drone": 0.0, "aircraft": 0.0}},
                           "water": {"kinds": {"ship": 0.0}}}, m)
    assert res.ok
    filled = S.fill(res.spec, m["districts"], PL.library_cars())
    routes, pads, piers, extra = AW.airwater_plan(m, filled, None)
    kinds = {r["kind"] for r in routes}
    assert "drone" not in kinds and "aircraft" not in kinds and "ship" not in kinds
    assert "car" in kinds and "boat" in kinds
    assert not S.validate_spec({"air": {"kinds": {"blimp": 1.0}}}, m).ok


def test_plan_writes_airwater_and_the_exporter_packs_it(tmp_path: Path):
    from citygen import unreal_life as UL
    b = tmp_path / "city"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_aw_model()), encoding="utf-8")
    rep = PL.build_plan(b, preview=False)
    for k in ("air_lanes", "air_pads", "water_lanes", "airwater_timing", "airwater_budget"):
        assert rep["checks"][k]["ok"], (k, rep["checks"][k]["detail"])
    data = json.loads((b / "life" / "airwater.json").read_text(encoding="utf-8"))
    PM.AirWater.model_validate(data)
    plan = json.loads((b / "life" / "life_plan.json").read_text(encoding="utf-8"))
    assert plan["airwater"]["file"] == "airwater.json"
    con = json.loads((b / "life" / "unreal_contribution.life.json").read_text(encoding="utf-8"))
    keys = {e["key"]: e for e in con["entries"] if e["kind"] in ("air_route", "water_route")}
    assert set(keys) == {r["id"] for r in data["routes"]}
    # (the exporter: stand-ins without the vehicle library; AG18's hover cars with it)
    m = _aw_model()
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in m["walkways"]]
    lanes = [{"id": "l1", "kind": "lane", "width": 3.6, "points": [[300, -2, 0], [350, -2, 0]],
              "links": []}]
    graphs = {"walkways": _flat(walks), "lanes": _flat(lanes)}
    lf = UL.write_life(b, None, graphs, None)
    assert lf["airwater"]["routes"] == len(data["routes"])
    c = json.loads((b / "unreal" / "life.json").read_text(encoding="utf-8"))["controller"]
    n = len(data["routes"])
    assert len(c["aw_route_kind"]) == n and len(c["aw_route_count"]) == 5 * n
    assert c["aw_point_starts"][-1] * 4 == len(c["aw_points"])
    assert c["aw_sample_starts"][-1] == len(c["aw_samples"])
    assert c["aw_event_starts"][-1] * 3 == len(c["aw_events"])
    assert c["aw_model_part_starts"][-1] * 9 == len(c["aw_parts"])
    assert c["aw_meshes"][:3] == list(UL.AW_MESHES.values())
    assert all(f == 6 for f in c["aw_mesh_floats"]) and "car" in c["aw_models"]
    veh = {"cars": {"kestrel_dart": {
        "car": "kestrel_dart", "folder": "/Game/CityGen/Vehicles/kestrel_dart",
        "dimensions": {"length": 4.9, "width": 2.1, "height": 1.4},
        "parts": [{"name": "body", "kind": "body", "pivot": [0, 0, 0]},
                  {"name": "glass", "kind": "glass", "pivot": [0, 0, 0]}]}}}
    for r in data["routes"]:
        if r["kind"] == "car":
            r["model"] = "kestrel_dart"
    (b / "life" / "airwater.json").write_text(json.dumps(data), encoding="utf-8")
    out = UL.pack_airwater(plan, b / "life", veh)
    assert "kestrel_dart" in out["aw_models"]
    assert "/Game/CityGen/Vehicles/kestrel_dart/SM_kestrel_dart_body" in out["aw_meshes"]
    assert 9 in out["aw_mesh_floats"]
    cars = sum(max(r["counts"]) for r in data["routes"] if r["kind"] == "car")
    assert len(out["aw_paints"]) >= 9 * cars
    # (a plan before LG7 packs none)
    plan["airwater"] = None
    (b / "life" / "airwater.json").unlink()
    assert UL.pack_airwater(plan, b / "life", None) == {}


def test_every_kind_has_a_model():
    from citygen import unreal_life as UL
    for k in P.AW_KINDS:
        assert k in P.AW_VEHICLES and k in UL.AIRWATER_MODELS
        for p in UL.AIRWATER_MODELS[k]:
            assert p["kind"] in UL.AW_PART_KINDS and p["mesh"] in UL.AW_MESHES
    # (the hover cars are AG18's, never Vex or Aurel)
    from assetgen.parked.table import EXCLUDED
    assert not set(UL.HOVER) & set(EXCLUDED) and not set(AW.HOVER) & set(EXCLUDED)
