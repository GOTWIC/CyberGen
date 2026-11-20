"""LG4: life at places (docs/lifegen_scope.md 6.4): the plan's slots, places by their hours,
gangs on their turf, police patrols, the pools' roles, the checks, and the exporter's layer 4
(`citygen/unreal_life.py`), on LG0's small synthetic build with a gang turf, a hideout, a police
precinct and its station, the police field, AG3's shop doors and a few more props."""

import json
import math
from pathlib import Path

import pytest

from lifegen import places as PL4
from lifegen import plan as PL
from lifegen import planmodel as PM
from lifegen import presets as P

from test_lg_plan import _flat, _model, _sq


def _model4() -> dict:
    m = _model()
    m["road_nodes"] = [{"id": "rn.x", "position": [200.0, 0.0]},
                       {"id": "rn.y", "position": [300.0, 0.0]},
                       {"id": "rn.w", "position": [0.0, 0.0]}]
    m["junctions"][1]["node_id"] = "rn.y"
    m["factions"] = [{"id": "fac.red", "kind": "gang", "name": "Red Hands",
                      "home_district_id": "d02", "color": "#aa2233"},
                     {"id": "fac.police", "kind": "police", "name": "Test Bay Police",
                      "color": "#5b8cff"}]
    m["zones"] = [{"id": "d02.turf1", "kind": "territory", "name": "Old Quarter",
                   "district_id": "d02", "faction_id": "fac.red", "level": 0.8,
                   "polygons": [_sq(250, -100, 500, 100)]},
                  {"id": "d01.police", "kind": "police", "name": "Core Precinct",
                   "district_id": "d01", "faction_id": "fac.police", "level": 0.7,
                   "polygons": [], "attrs": {"station_building_id": "d01.lot.e150n20.bld"}}]
    # (the police field: high in the core, low in the old quarter; 32 m cells over the bounds)
    nx = ny = 32
    vals = []
    for j in range(ny):
        for i in range(nx):
            x = -512.0 + (i + 0.5) * 32.0
            vals.append(0.7 if x < 250.0 else 0.15)
    m["fields"] = [{"id": "field.police", "kind": "police", "origin": [-512.0, -512.0],
                    "cell_m": 32.0, "nx": nx, "ny": ny, "values": vals}]
    m["pois"] = [{"id": "d02.lot.e350n20.bld.hideout", "kind": "hideout", "sub": "squat",
                  "name": "The Den", "district_id": "d02", "building_id": "d02.lot.e350n20.bld",
                  "position": [350.0, 10.0, 0.0], "zone_id": "d02.turf1",
                  "faction_id": "fac.red", "hours": [0, 24],
                  "entrances": [{"position": [350.0, -4.5], "kind": "main",
                                 "walkway_id": "wk.c"}]},
                 {"id": "d01.lot.e50n20.bld.u00.bar", "kind": "bar", "sub": "bar",
                  "name": "Quist's Bar", "district_id": "d01",
                  "building_id": "d01.lot.e50n20.bld", "unit_index": 0,
                  "position": [58.0, 10.0, 0.0], "hours": [18, 4],
                  "entrances": [{"position": [58.0, -4.5], "kind": "unit", "walkway_id": "wk.a"}]}]
    m["props"] += [
        {"id": "d01.prop.kiosk.e120s9", "type": "prop.kiosk", "position": [120.0, -9.0, 0.0],
         "yaw_deg": 90.0},
        {"id": "d01.prop.food_stall.e170s9", "type": "prop.food_stall",
         "position": [170.0, -9.5, 0.0], "yaw_deg": 90.0}]
    return m


def _doors() -> dict:
    """AG3's doors on the core's tower: a bar (Quist's, a POI), a club, a food unit, a main door;
    and the station building's door."""
    def door(i, kind, use, x):
        return {"id": f"d01.lot.e50n20.bld.door.{i}", "kind": kind, "use": use,
                "walkway_id": "wk.a", "position": [x, -15.0, 0.0], "normal": [0.0, -1.0],
                "width_m": 1.2, "height_m": 2.4}
    return {"entries": [
        {"key": "d01.lot.e50n20.bld", "ids": ["d01.lot.e50n20.bld"], "pivot": [50.0, 25.0, 0.0],
         "doors": [door("e0", "main", None, 0.0), door("u0", "shop", "bar", 8.0),
                   door("u1", "shop", "club", -8.0), door("u2", "shop", "food", 14.0)]},
        {"key": "d01.lot.e150n20.bld", "ids": ["d01.lot.e150n20.bld"],
         "pivot": [150.0, 25.0, 0.0],
         "doors": [{"id": "d01.lot.e150n20.bld.door.e0", "kind": "main", "walkway_id": "wk.b",
                    "position": [0.0, -15.0, 0.0], "normal": [0.0, -1.0], "width_m": 2.0,
                    "height_m": 2.4}]},
        {"key": "d02.lot.e350n20.bld", "ids": ["d02.lot.e350n20.bld"],
         "pivot": [350.0, 25.0, 0.0],
         "doors": [{"id": "d02.lot.e350n20.bld.door.e0", "kind": "main", "walkway_id": "wk.c",
                    "position": [0.0, -15.0, 0.0], "normal": [0.0, -1.0], "width_m": 2.0,
                    "height_m": 2.4}]}]}


@pytest.fixture
def build(tmp_path: Path) -> Path:
    b = tmp_path / "city"
    (b / "assets").mkdir(parents=True)
    (b / "city_model.json").write_text(json.dumps(_model4()), encoding="utf-8")
    (b / "assets" / "unreal_contribution.buildings.json").write_text(json.dumps(_doors()),
                                                                     encoding="utf-8")
    return b


def _tiles(out: Path) -> list:
    plan = json.loads((out / "life_plan.json").read_text(encoding="utf-8"))
    return [PM.TileSpawns.model_validate_json((out / t["file"]).read_text(encoding="utf-8"))
            for t in plan["tiles"]]


# --- pieces ---------------------------------------------------------------------------------

def test_open_hours_and_shares():
    assert PL4.open_hours([0, 24]) == [1] * 24
    bar = PL4.open_hours([18, 4])
    assert bar[17] == 0 and bar[18] == 1 and bar[23] == 1 and bar[3] == 1 and bar[4] == 0
    day = PL4.open_hours([6, 22])
    assert day[5] == 0 and day[6] == 1 and day[21] == 1 and day[22] == 0
    # (per band the share of its hours open: night 0-6, ..., late 20-24)
    assert PL4.open_share(bar) == [pytest.approx(4 / 6, abs=1e-3), 0.0, 0.0, 0.5, 1.0]


def test_frame_points_face_by_their_kind():
    # (a bench facing east: its sitters along its length, facing away from its back, south)
    pts = PL4.frame_points("bench", 10.0, 20.0, 0.0, 0.0)
    assert [p[:2] for p in pts] == [[9.55, 19.9], [10.45, 19.9]]
    assert all(p[3] == -90.0 for p in pts)
    assert PL4._facing_ok("bench", (10.0, 20.0, 0.0), pts)
    # (a kiosk's queue out from its counter, facing it)
    q = PL4.frame_points("kiosk", 0.0, 0.0, 0.0, 90.0)
    assert q[0][:2] == pytest.approx([0.0, 1.75]) and q[0][3] == -90.0
    assert PL4._facing_ok("kiosk", (0.0, 0.0, 90.0), q)
    # (a ring faces its middle; turned away it fails)
    ring = [[p[0], p[1], p[2], math.degrees(math.atan2(-p[1], -p[0]))]
            for p in PL4.frame_points("gang_spot", 0.0, 0.0, 0.0, 0.0)]
    assert PL4._facing_ok("gang_spot", (0.0, 0.0, 0.0), ring, (0.0, 0.0))
    bad = [[p[0], p[1], p[2], p[3] + 180.0] for p in ring]
    assert not PL4._facing_ok("gang_spot", (0.0, 0.0, 0.0), bad, (0.0, 0.0))


def test_faction_colors_and_reserve():
    cols = PL4.faction_colors("#aa2233")
    assert len(cols) == P.OUTFIT_COLORS and cols[0] == "#aa2233"
    # (the most wanted within reach of any tile, the margin, the minimum and the cap)
    per = {"t+00+00": 10.0, "t+01+00": 10.0, "t+09+09": 3.0}
    n, want = PL4.reserve(per, 340.0, 1000, 0.1)
    assert want == 20.0 and n == math.ceil(20.0 * P.ROLES["margin"])
    assert PL4.reserve({"t+00+00": 1.0}, 340.0, 100, 0.1)[0] == P.ROLES["min"]
    assert PL4.reserve(per, 340.0, 100, 0.1)[0] == 10
    assert PL4.reserve({}, 340.0, 100, 0.1) == (0, 0.0)


# --- the plan -------------------------------------------------------------------------------

def test_places_on_a_small_city(build: Path):
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"], {k: c for k, c in rep["checks"].items() if not c["ok"]}
    for k in ("slots_placed", "slot_use", "places_hours", "gang_turf", "police_patrols",
              "places_budget", "slot_heights"):
        assert rep["checks"][k]["ok"], (k, rep["checks"][k])
    out = build / "life"
    tiles = _tiles(out)
    slots = {s.id: s for t in tiles for s in t.slots}
    places = {p.id: p for t in tiles for p in t.places}
    walks = {w.id: w for t in tiles for w in t.walks}
    spawns = {s.id: s for t in tiles for s in t.spawns}
    # (slots: the bench, bus stop, kiosk, stall and taxi stand; the club's queue and the bar's
    # smokers at their doors; the gang's spots)
    kinds = {s.kind for s in slots.values()}
    assert {"bench", "bus_stop", "kiosk", "stall", "taxi_stand", "bar_queue", "smoke",
            "gang_spot"} <= kinds
    b = slots["slot.d01.prop.bench.e80s8"]
    assert b.behavior == "sit" and b.anim == "sit" and b.capacity == 2 and b.walkway_id == "wk.a"
    assert all(p[3] == 0.0 for p in b.points)            # (its yaw 90: sitters face east)
    k = slots["slot.d01.prop.kiosk.e120s9"]
    assert k.behavior == "buy" and k.walkway_id == "wk.b" and k.use[2] > 0.0
    # (places by their hours: the bar a POI's, the club and food by their use)
    bar = places["place.d01.lot.e50n20.bld.door.u0"]
    assert bar.poi_id == "d01.lot.e50n20.bld.u00.bar" and bar.hours == [18, 4]
    assert bar.open[23] == 1 and bar.open[12] == 0 and bar.slot == "smoke"
    club = places["place.d01.lot.e50n20.bld.door.u1"]
    assert club.kind == "club" and club.slot == "bar_queue" and club.open[2] == 1
    q = slots["slot.d01.lot.e50n20.bld.door.u1.bar_queue"]
    assert q.place_id == club.id and q.use[1] == 0.0 and q.use[4] > 0.0
    # (a closed door sends no one out; the district keeps its people every hour)
    assert spawns["spawn.d01.lot.e50n20.bld.door.u0"].rates[12] == 0.0
    assert spawns["spawn.d01.lot.e50n20.bld.door.u0"].rates[23] > 0.0
    # (the old quarter is the gang's turf: its walkways, members and spots)
    assert walks["wk.c"].turf == "d02.turf1" and walks["wk.c"].gang[4] > 0.0
    assert walks["wk.a"].turf is None and walks["wk.a"].gang is None
    spots = [s for s in slots.values() if s.kind == "gang_spot"]
    assert spots and all(s.turf_id == "d02.turf1" and s.role == "gang" for s in spots)
    assert any(".hideout." in s.id for s in spots)
    # (police patrol the core, where the field is high; the station's doors)
    assert walks["wk.a"].patrol and walks["wk.a"].police[2] > 0.0
    assert not walks["wk.c"].patrol and walks["wk.c"].police is None
    plan = json.loads((out / "life_plan.json").read_text(encoding="utf-8"))
    pre = {p["id"]: p for p in plan["police"]["precincts"]}
    assert pre["d01.police"]["station_doors"] == ["spawn.d01.lot.e150n20.bld.door.e0"]
    g = plan["gangs"]["turfs"][0]
    assert g["faction"] == "Red Hands" and g["colors"][0] == "#aa2233"
    # (the pools: slots kept for gang members and police in their looks; patrol cars)
    role = plan["crowd"]["persons"]["role"]
    assert plan["crowd"]["roles"]["slots"] == [role.count(0), role.count(1), role.count(2)]
    assert role.count(1) == plan["gangs"]["pool"] > 0
    assert role.count(2) == plan["police"]["pool"] > 0
    from lifegen import garments as G
    for k2, r in enumerate(role):
        if r:
            assert G.GROUPS[int(plan["crowd"]["persons"]["group"][k2])] == P.ROLE_CODES[int(r)]
    tr = plan["traffic"]
    assert len(tr["police_slots"]) == plan["police"]["cars"] > 0
    assert len(tr["slots"]) == tr["pool"] and len(tr["police_paint"]) == 9
    # (an unchanged plan writes nothing)
    assert PL.build_plan(build, preview=False)["wrote"] == []


def test_gang_members_off_their_turf_fail(build: Path):
    """The checks catch gang members put off their turf and police off the patrol walkways."""
    PL.build_plan(build, preview=False)
    model = json.loads((build / "city_model.json").read_text(encoding="utf-8"))
    rows = [{"id": "wk.a", "kind": "sidewalk", "district_id": "d01", "level": 0,
             "length_m": 100.0, "street": True, "people": [1.0] * 5, "tile": "t+00-01",
             "turf": "d02.turf1", "gang": [1.0] * 5, "patrol": False, "field": 0.1,
             "police": [1.0] * 5}]
    turfs = PL4.gang_turfs(model)
    gm = {"turfs": {t["id"]: {"walk": [0.0] * 5, "loiter": [0.0] * 5, "walkways": 1}
                    for t in turfs}, "left": {"members": [0.0] * 5, "walkways": 0}}
    pol = {"total": {}, "left": {"foot": [0.0] * 5, "cars": [0.0] * 5}, "precincts": []}
    crowd = {"persons": {"role": [], "group": []}, "pool": 10}
    traffic = {"police_slots": [], "slots": [], "models": [], "police_model": None}
    roles = {"gang": (0, 0.0), "police": (0, 0.0), "cars": (0, 0.0)}
    filled = {"crowd": {"hour": 23}}
    out = PL.places_checks(model, filled, [], [], rows, [], turfs, gm, pol, crowd, traffic,
                           roles, [], {})
    assert not out["gang_turf"]["ok"] and "off their turf" in out["gang_turf"]["detail"]
    assert not out["police_patrols"]["ok"]


def test_slots_stand_on_their_surface():
    """delta_rebuild: a slot's points take the surface stage 2 draws under them: a raised
    road's sidewalk face (its vertices 1 m over the ground, lifted 0.2 m as AG17's curb), the
    ground cover (0.1 m) or the bare ground, whatever their walkway's height in the model; the
    check fails a point moved off it."""
    net = {"vertices": [{"id": "a", "p": [0.0, 0.0], "z": 1.0}, {"id": "b", "p": [10.0, 0.0], "z": 1.0},
                        {"id": "c", "p": [10.0, 4.0], "z": 2.0}, {"id": "d", "p": [0.0, 4.0], "z": 2.0}],
           "edges": [{"id": "ab", "kind": "outer", "v": ["a", "b"]},
                     {"id": "bc", "kind": "port", "v": ["b", "c"]},
                     {"id": "cd", "kind": "curb", "v": ["c", "d"]},
                     {"id": "da", "kind": "port", "v": ["d", "a"]}]}
    model = {"pavement_net": net,
             "pavement": [{"id": "rs.x.pv.cl", "owner_id": "rs.x", "kind": "sidewalk", "band": "cl",
                           "layer": "g0", "rings": [["ab", "bc", "cd", "da"]]},
                          {"id": "rs.y.pv.cl", "owner_id": "rs.y", "kind": "sidewalk", "band": "cl",
                           "layer": "g1", "rings": [["ab", "bc", "cd", "da"]]}],
             "ground_cover": [{"id": "gc", "kind": "lawn", "polygon": {"exterior": _sq(20, 0, 30, 10)["exterior"]}}],
             "walkways": [{"id": "wk.s", "kind": "sidewalk", "line": [[0.0, 2.0, 0.0], [10.0, 2.0, 0.0]]}]}
    sf = PL4.Surface(model)
    z, what = sf.at(5.0, 2.0)
    assert what == "pavement" and abs(z - 1.7) < 1e-6        # (1.5 m between the curbs, + 0.2)
    assert sf.at(25.0, 5.0) == (P.COVER_LIFT_M, "cover")
    assert sf.at(50.0, 50.0) == (0.0, "ground")
    slots = [{"id": "slot.a", "level": 0, "walkway_id": "wk.s",
              "points": [[5.0, 2.0, 0.0, 0.0], [25.0, 5.0, 0.0, 90.0]]},
             {"id": "slot.deck", "level": 1, "walkway_id": "wk.s", "points": [[5.0, 2.0, 9.0, 0.0]]}]
    st = PL4.seat_slots(slots, sf)
    assert st["seated"] == 1 and st["pavement"] == 1 and st["cover"] == 1
    assert slots[0]["seated"] and slots[0]["points"][0][2] == 1.7 and slots[0]["points"][1][2] == 0.1
    assert "seated" not in slots[1] and slots[1]["points"][0][2] == 9.0
    ok = PL4.height_check(model, slots, sf, st)
    assert ok["ok"] and "0 slots more than 0.3 m off" in ok["detail"], ok
    slots[0]["points"][0][2] = 0.0
    assert not PL4.height_check(model, slots, sf, st)["ok"]
    # (a slot leaves from a walkway at its height: the sidewalk on the raised road, 1.5 m off,
    # not the skybridge 10 m over it right beside the bench; the walkway's height is the face's
    # where the model keeps a raised road's sidewalk at the ground)
    model["walkways"].append({"id": "wk.bridge", "kind": "skybridge",
                              "line": [[0.0, 2.4, 10.0], [10.0, 2.4, 10.0]]})
    wi = PL4.WalkIndex(model["walkways"], sf)
    assert abs(wi.height(wi.walks[0], 5.0, 2.0) - 1.7) < 1e-6
    assert wi.nearest(5.0, 2.5, 15.0)[0]["id"] == "wk.bridge"
    assert wi.nearest(5.0, 2.5, 15.0, 0, sf.at(5.0, 2.5)[0])[0]["id"] == "wk.s"


def test_slots_leave_from_a_walkway_at_their_height():
    """City open items: a slot whose walkway is far above or below it (a bar's door on a raised
    road's sidewalk, a vending machine beside a platform) takes the nearest walkway at its
    height within reach, else is left out; the check fails one still off its walkway."""
    model = {"walkways": [{"id": "wk.g", "kind": "sidewalk", "line": [[0.0, 0.0, 0.0], [20.0, 0.0, 0.0]]},
                          {"id": "wk.p", "kind": "elevated", "line": [[0.0, 38.0, 31.0], [20.0, 38.0, 31.0]]}]}
    sf = PL4.Surface(model)
    wi = PL4.WalkIndex(model["walkways"], sf)
    slots = [{"id": "slot.near", "kind": "vending", "level": 0, "walkway_id": "wk.p",
              "points": [[5.0, 2.0, 0.0, 0.0]]},
             {"id": "slot.far", "kind": "bench", "level": 0, "walkway_id": "wk.p",
              "points": [[5.0, 40.0, 0.0, 0.0]]}]
    st = PL4.seat_slots(slots, sf)
    bad = PL4.height_check(model, slots, sf, st)
    assert not bad["ok"] and "31.00 m off its walkway wk.p" in bad["detail"], bad
    kept, stats = PL4.level_slots(slots, wi, {})
    assert stats["moved"] == 1 and stats["dropped_ids"] == ["slot.far"]
    assert [s["id"] for s in kept] == ["slot.near"] and kept[0]["walkway_id"] == "wk.g"
    assert kept[0]["reach_m"] == 2.0
    assert PL4.height_check(model, kept, sf, st)["ok"]


# --- the exporter ---------------------------------------------------------------------------

def test_exporter_packs_the_places(build: Path):
    from citygen import unreal_life as UL
    PL.build_plan(build, preview=False)
    m = _model4()
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in m["walkways"]]
    lanes = [{"id": ln["id"], "kind": ln["kind"], "width": 3.6, "points": ln["centerline"],
              "links": ln["successors"]} for ln in m["lanes"]]
    graphs = {"walkways": _flat(walks), "lanes": _flat(lanes)}
    data, why = UL.life_data(build / "life", graphs, None, None)
    assert why == ""
    c = data["controller"]
    ns = len(c["slot_kinds"])
    assert ns > 0 and len(c["slot_point_starts"]) == ns + 1
    assert len(c["slot_points"]) == 4 * c["slot_point_starts"][-1]
    assert len(c["slot_use"]) == 5 * ns and len(c["slot_dwell"]) == 2 * ns
    names = c["slot_kind_names"]
    assert names == list(P.SLOT_KINDS) and len(c["slot_kind_behaviors"]) == len(names)
    # (a club's queue goes in at its door: a door index)
    qi = [k for k in range(ns) if names[c["slot_kinds"][k]] == "bar_queue"]
    assert qi and all(0 <= c["slot_doors"][k] < len(c["door_lanes"]) for k in qi)
    # (delta_rebuild: every ground level slot seated on its surface)
    assert c["slot_seated"] == [1] * ns
    nw = len(c["walk_kinds"])
    assert len(c["walk_turf"]) == nw and len(c["walk_gang"]) == 5 * nw
    assert len(c["walk_police"]) == 5 * nw and len(c["walk_patrol"]) == nw
    nd = len(c["door_lanes"])
    assert len(c["door_rates_h"]) == 24 * nd and len(c["door_open"]) == nd
    assert len(c["door_visit"]) == 5 * nd and len(c["door_dwell"]) == 2 * nd
    assert sum(c["door_police"]) == 1
    assert len(c["person_role"]) == c["people"] and c["turf_faction"] == [0]
    assert len(c["faction_palettes"]) == 3 * c["faction_colors"]
    # (no traffic models in the project: no patrol car slots packed)
    assert "traffic_police" not in c
    # (a plan before LG4 packs none of it)
    plan = json.loads((build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    plan.pop("places")
    (build / "life" / "life_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    data, why = UL.life_data(build / "life", graphs, None, None)
    assert "slot_kinds" not in data["controller"] and "door_rates_h" not in data["controller"]
