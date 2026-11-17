"""LG8: the crowd and the traffic by the hour and the weather, and reactions: the weather's
table, the walkways' stretches out of the rain (atmosgen's rain shadow), nightlife, the checks,
the exporter's pack; Vesper Bay's two fixes (a gang spot on its turf's edge, a deep metro's
concourse)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from lifegen import plan as PL
from lifegen import presets as P
from lifegen import transit as TR
from lifegen import weather as WX

from test_lg_plan import _flat
from test_lg_places import _doors, _model4


def _atmos(adir: Path, tile: str = "t+00-01", cover_rows: tuple[int, int] = (0, 64),
           value: int = 40) -> Path:
    """A minimal atmos plan: one tile's mask (512 px over 256 m, row 0 its north edge) with a
    cover `value` steps over the datum on rows `cover_rows`, the rest open sky."""
    from PIL import Image
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "masks").mkdir(exist_ok=True)
    a = np.zeros((512, 512, 4), dtype=np.uint8)
    a[cover_rows[0]:cover_rows[1], :, 0] = value
    a[:, :, 3] = 255
    Image.fromarray(a, "RGBA").save(adir / "masks" / f"{tile}.png")
    plan = {"weather_plan": {"cover": {"z0_m": -8.0, "step_m": 0.5}, "texel_m": 0.5},
            "masks": [{"tile": tile, "file": f"masks/{tile}.png", "px": 512}]}
    (adir / "atmos_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return adir


@pytest.fixture
def build(tmp_path: Path) -> Path:
    b = tmp_path / "city"
    (b / "assets").mkdir(parents=True)
    (b / "city_model.json").write_text(json.dumps(_model4()), encoding="utf-8")
    (b / "assets" / "unreal_contribution.buildings.json").write_text(json.dumps(_doors()),
                                                                     encoding="utf-8")
    return b


# --- pieces ---------------------------------------------------------------------------------

def test_weather_table_is_whole():
    for s, v in P.WEATHER_LIFE.items():
        assert set(v) == set(P.WEATHER_KEYS), s
        assert s in P.WEATHER_RAIN
    assert P.WEATHER_LIFE["clear"]["umbrella"] == 0.0 and P.WEATHER_LIFE["clear"]["out"] == 1.0
    # (rain: fewer out, faster, umbrellas and raincoats, the cars slower and further apart)
    r = P.WEATHER_LIFE["rain"]
    assert r["out"] < 1.0 and r["pace"] > 1.0 and r["umbrella"] > 0.0 and r["rain_looks"] > 0.0
    assert r["speed"] < 1.0 and r["headway_s"] > 0.0 and r["shelter"] > 0.0
    # (LG2's outfits and the table agree on the rain looks)
    assert all(abs(P.WEATHER_OUTFITS[s] - P.WEATHER_LIFE[s]["rain_looks"]) < 1e-9
               for s in P.WEATHER_OUTFITS)


def test_masks_read_the_cover_over_a_point(tmp_path: Path):
    # (tile t+00-01 spans x 0..256, y -256..0; rows 0 to 64 are its north 32 m: y -32..0)
    m = WX.Masks(_atmos(tmp_path / "atmos"))
    u = m.under(np.array([10.0, 10.0, 300.0]), np.array([-10.0, -100.0, -10.0]))
    assert u[0] == pytest.approx(-8.0 + 40 * 0.5)
    assert np.isnan(u[1]) and np.isnan(u[2])


def test_walk_cover_finds_covered_stretches(tmp_path: Path):
    model = {"walkways": [
        # (a sidewalk running south out from under the cover: covered for its first 20 m)
        {"id": "wk.s", "kind": "sidewalk", "line": [[10.0, -12.0, 0.0], [10.0, -60.0, 0.0]]},
        # (a skybridge: enclosed, whole)
        {"id": "wk.k", "kind": "skybridge", "line": [[0.0, 0.0, 10.0], [30.0, 0.0, 10.0]]},
        # (a metro's stair under the ground)
        {"id": "wk.m", "kind": "stairs", "line": [[50.0, -100.0, -3.0], [50.0, -110.0, -8.0]]},
        # (open sky)
        {"id": "wk.o", "kind": "sidewalk", "line": [[100.0, -100.0, 0.0], [130.0, -100.0, 0.0]]},
        # (a cover too low to stand under: 0.5 m over it)
        {"id": "wk.l", "kind": "sidewalk", "line": [[40.0, -5.0, 11.5], [60.0, -5.0, 11.5]]}]}
    cover, stats = WX.walk_cover(model, WX.Masks(_atmos(tmp_path / "atmos")))
    assert "wk.o" not in cover and "wk.l" not in cover
    (a, b), = cover["wk.s"]
    assert a == 0.0 and 19.0 <= b <= 22.0
    assert cover["wk.k"] == [[0.0, 30.0]] and stats["enclosed"] == 1
    assert "wk.m" in cover and stats["underground"] == 1
    # (without an atmos plan: only the enclosed and the underground)
    cover2, stats2 = WX.walk_cover(model, None)
    assert set(cover2) == {"wk.k", "wk.m"} and not stats2["masks"]


def test_nightlife_round_bars_by_night():
    places = [{"walkway_id": "wk.a", "kind": "bar", "open": [1 if h >= 18 or h < 4 else 0
                                                            for h in range(24)],
               "busy": [0.7, 0.0, 0.1, 0.5, 1.0]},
              {"walkway_id": "wk.b", "kind": "food", "open": [1] * 24,
               "busy": [1.0] * 5}]
    n = WX.nightlife({"pois": []}, places)
    assert set(n) == {"wk.a"}
    night = n["wk.a"]
    assert night[1] == 0.0 and night[4] == pytest.approx(P.NIGHTLIFE["kinds"]["bar"])
    assert night[0] > 0.0 and night[3] > 0.0
    # (a POI bar of M11's that is no place: its door walkway too)
    m = {"pois": [{"id": "p.club", "kind": "bar", "sub": "club", "hours": [21, 6],
                   "entrances": [{"walkway_id": "wk.c"}]}]}
    assert "wk.c" in WX.nightlife(m, [])


def test_metro_concourse_over_a_deep_track():
    # (Vesper Bay's Corporate Core: the concourse at -8 m, the track lowered to -24.2 m there)
    track = TR.Track([[0.0, 0.0, -24.2], [400.0, 0.0, -24.2]], False)
    model = {"stations": [{"id": "stn.x", "name": "X", "kind": "underground",
                           "position": [200.0, 0.0, -8.0], "line_ids": ["tl.m"],
                           "attrs": {"track_z_m": -24.2}, "access_ids": []}],
             "walkways": [{"id": "wk.cc", "kind": "path",
                           "line": [[190.0, 2.0, -8.0], [210.0, 2.0, -8.0]],
                           "attrs": {"station": "stn.x", "concourse": True}}],
             "structures": []}
    line = {"id": "tl.m", "mode": "metro", "station_ids": ["stn.x"]}
    stops, bad = TR.stops_of(model, line, track, P.TRANSIT_MODES["metro"])
    assert not bad and stops[0]["station_id"] == "stn.x"
    # (a concourse whose station names another depth than its track is still off it)
    model["stations"][0]["attrs"]["track_z_m"] = -60.0
    stops, bad = TR.stops_of(model, line, track, P.TRANSIT_MODES["metro"])
    assert bad and not stops


# --- the plan -------------------------------------------------------------------------------

def test_plan_weather_shelter_and_nightlife(build: Path, tmp_path: Path):
    # (a cover over the core's sidewalk wk.a, y -10 to 0 of tile t+00-01)
    adir = _atmos(build / "atmos", cover_rows=(0, 40))
    rep = PL.build_plan(build, preview=False)
    assert rep["ok"], {k: v for k, v in rep["checks"].items() if not v["ok"]}
    plan = json.loads((build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    w = plan["weather"]
    assert set(w["states"]) == set(P.WEATHER_LIFE) and w["state"] == "clear"
    assert w["shelter"]["masks"] and w["shelter"]["atmos"].endswith("atmos")
    assert {"weather", "shelter", "nightlife"} <= set(plan["checks"])
    rows = {r["id"]: r for t in plan["tiles"] for r in json.loads(
        (build / "life" / t["file"]).read_text(encoding="utf-8")).get("walks") or []}
    assert any(r.get("cover") for r in rows.values())
    # (Quist's Bar on wk.a: its nightlife late, none in the morning)
    assert rows["wk.a"]["night"][4] > 0.0 and rows["wk.a"]["night"][1] == 0.0
    # (the pool holds rain looks for the runtime's rain; the clear groups for its blend)
    of = plan["crowd"]["outfits"]
    assert of["rain_group"] == of["groups"].index("rain")
    assert all(v[of["rain_group"]] == 0.0 for v in of["district_groups_clear"].values())
    assert of["rain_group"] in plan["crowd"]["persons"]["group"]
    assert adir.is_dir()


def test_nightlife_check_fails_off_hours(build: Path):
    model = _model4()
    rows = [{"id": "wk.a", "night": [0.0, 2.0, 0.0, 0.0, 0.0]}]
    places = [{"walkway_id": "wk.a", "kind": "bar", "open": [1 if h >= 18 or h < 4 else 0
                                                            for h in range(24)],
               "busy": [0.7, 0.0, 0.1, 0.5, 1.0]}]
    rec = WX.weather_record({"crowd": {"weather": "clear"}, "reactions": dict(P.REACTIONS)},
                            {"masks": False, "enclosed": 0, "underground": 0, "shelter_m": 0.0},
                            {}, None)
    c = WX.checks(model, rows, places, rec)
    assert c["weather"]["ok"] and not c["nightlife"]["ok"]


def test_exporter_packs_the_weather(build: Path):
    from citygen import unreal_life as UL
    _atmos(build / "atmos", cover_rows=(0, 40))
    PL.build_plan(build, preview=False)
    m = _model4()
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in m["walkways"]]
    lanes = [{"id": ln["id"], "kind": ln["kind"], "width": 3.6, "points": ln["centerline"],
              "links": ln["successors"]} for ln in m["lanes"]]
    graphs = {"walkways": _flat(walks), "lanes": _flat(lanes)}
    data, why = UL.life_data(build / "life", graphs, None, None)
    assert why == "" and data["version"] == UL.PACK_VERSION == 9
    c = data["controller"]
    names, keys = c["weather_names"], c["weather_keys"]
    assert sorted(names) == sorted(P.WEATHER_LIFE) and keys == list(P.WEATHER_KEYS)
    assert len(c["weather_life"]) == len(names) * len(keys)
    assert len(c["weather_rain"]) == len(names) and c["weather_plan"] == "clear"
    nw = len(c["walk_kinds"])
    assert len(c["walk_cover_starts"]) == nw + 1
    assert len(c["walk_cover"]) == 2 * c["walk_cover_starts"][-1] > 0
    assert len(c["walk_night"]) == 5 * nw and max(c["walk_night"]) > 0.0
    assert len(c["umbrella"]) == 8 and len(c["umbrella_colors"]) % 3 == 0
    assert c["umbrella_meshes"]["canopy"].startswith("/Engine/BasicShapes/")
    assert c["reactions"]["flee"] and c["reactions"]["flee_m"] == P.REACTION["flee_m"]
    assert c["rain_group"] >= 0
    # (the district groups packed are the clear weather's)
    assert all(c["district_groups"][k] == 0.0
               for k in range(c["rain_group"], len(c["district_groups"]), c["outfit_groups"]))
    # (a plan before LG8 packs none of it)
    plan = json.loads((build / "life" / "life_plan.json").read_text(encoding="utf-8"))
    plan.pop("weather")
    (build / "life" / "life_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    data, _ = UL.life_data(build / "life", graphs, None, None)
    assert "weather_names" not in data["controller"]


def test_terminal_nearer_the_end_than_the_turn_is_called():
    # (Nexus City's Spire Line: a sky tube whose first stop is 10 m from its track's end, nearer
    # than the turn point half a train in: the train calls there as it turns)
    mode = P.TRANSIT_MODES["sky_tube"]
    track = TR.Track([[0.0, 0.0, 40.0], [700.0, 0.0, 40.0]], False)
    stops = [{"station_id": "a", "s": 10.35}, {"station_id": "b", "s": 690.0}]
    cyc = TR.cycle(track, mode, stops)
    called = {e[2] for e in cyc["events"] if e[2] >= 0}
    assert called == {0, 1}
    assert cyc["turn"][0] > 10.35


def test_road_sides_put_shelter_against_the_buildings():
    # (a sidewalk running east with its road to the south: the road on its right; running west,
    # on its left)
    model = {"road_segments": [{"id": "rs.a", "centerline": [[0.0, 0.0], [100.0, 0.0]]}],
             "walkways": [{"id": "wk.e", "line": [[0.0, 8.0, 0.0], [100.0, 8.0, 0.0]],
                           "attrs": {"segment": "rs.a"}},
                          {"id": "wk.w", "line": [[100.0, 8.0, 0.0], [0.0, 8.0, 0.0]],
                           "attrs": {"segment": "rs.a"}},
                          {"id": "wk.n", "line": [[0.0, 20.0, 0.0], [10.0, 20.0, 0.0]]}]}
    sides = WX.road_sides(model, {"wk.e": [[0, 5]], "wk.w": [[0, 5]], "wk.n": [[0, 5]]})
    assert sides == {"wk.e": 1, "wk.w": -1}
