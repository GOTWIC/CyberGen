"""AT5: the weather (atmosgen/weather.py, docs/atmosgen_scope.md 6.4): the rain shadow of the
covers (moved downwind by the rain's lean), the masks (cover, puddles, drips, gloss), the drip
lines, the states and the weather check, and the plan's record of them. The runtime renders
them in Unreal (`citygen unreal --check`'s weather, docs/progress/AT5)."""

import json

import numpy as np
import pytest
from PIL import Image

from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P
from atmosgen import spec as S
from atmosgen import weather as WE


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _net(faces):
    """A pavement map (M22's form) of axis-aligned rectangular faces: [(id, kind, box)]."""
    verts, edges, rows = {}, [], []
    for fid, kind, (x0, y0, x1, y1) in faces:
        ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        refs = []
        for k, (a, b) in enumerate(zip(ring, ring[1:] + ring[:1])):
            ids = []
            for p in (a, b):
                vid = f"v{p[0]:g}_{p[1]:g}"
                verts[vid] = {"id": vid, "p": [float(p[0]), float(p[1])], "z": 0.0}
                ids.append(vid)
            eid = f"{fid}.e{k}"
            edges.append({"id": eid, "kind": "outer", "v": ids})
            refs.append(eid)
        rows.append({"id": fid, "kind": kind, "layer": "g0", "owner_id": fid, "rings": [refs]})
    return rows, {"vertices": list(verts.values()), "edges": edges}


def _model():
    """Two districts along an east-west street (y 100 to 112): a gritty old town (west) and a
    clean corporate core (east); a shop with an awning on the street's north side, a deck over
    the core's south, a raised road (a viaduct 9 m up) across the core, a canal in the old town,
    a skybridge too high to shelter anything."""
    faces = [("rs.w.cw", "carriageway", (0, 100, 256, 112)),
             ("rs.w.cn", "curb", (0, 112, 256, 112.3)), ("rs.w.cs", "curb", (0, 99.7, 256, 100)),
             ("rs.w.sn", "sidewalk", (0, 112.3, 256, 116)),
             ("rs.w.ss", "sidewalk", (0, 96, 256, 99.7)),
             ("rs.e.cw", "carriageway", (256, 100, 512, 112)),
             ("rs.e.cn", "curb", (256, 112, 512, 112.3)),
             ("rs.e.sn", "sidewalk", (256, 112.3, 512, 116))]
    pv, net = _net(faces)
    return {
        "name": "Weather Test", "bounds": [0.0, 0.0, 512.0, 256.0],
        "land": [{"id": "land", "polygons": [{"exterior": _sq(0, 0, 512, 256)["exterior"],
                                              "holes": [_sq(20, 190, 236, 210)["exterior"]]}]}],
        "districts": [
            {"id": "d01", "name": "Old Town", "archetype": "old_town",
             "params": {"wealth": 0.2, "danger": 0.8}, "polygon": _sq(0, 0, 256, 256)},
            {"id": "d02", "name": "Core", "archetype": "corporate_core",
             "params": {"wealth": 0.9, "danger": 0.1}, "polygon": _sq(256, 0, 512, 256)}],
        "waterways": [{"id": "d01.ww.e128n200", "kind": "canal", "district_id": "d01",
                       "polygon": _sq(20, 190, 236, 210),
                       "centerline": [[20.0, 200.0], [236.0, 200.0]]}],
        "pavement": pv, "pavement_net": net,
        "buildings": [{"id": "d01.lot.e100n125.bld", "type": "building.shopfront_row",
                       "district_id": "d01", "footprint": _sq(80, 116, 120, 136),
                       "masses": [{"footprint": _sq(80, 116, 120, 136), "z0_m": 0.0,
                                   "z1_m": 12.0}]},
                      # a tower's block overhanging the sidewalk 6 m up
                      {"id": "d02.lot.e400n130.bld", "type": "building.tower",
                       "district_id": "d02", "footprint": _sq(380, 118, 420, 150),
                       "masses": [{"footprint": _sq(380, 118, 420, 150), "z0_m": 0.0,
                                   "z1_m": 60.0},
                                  {"footprint": _sq(380, 113, 420, 150), "z0_m": 6.0,
                                   "z1_m": 30.0}]}],
        "props": [{"id": "d01.prop.awning.e100n115", "type": "prop.awning", "attrs": {},
                   "position": [100.0, 115.0, 3.2], "yaw_deg": 0.0,
                   "scale": [30.0, 2.0, 1.0]}],
        "decks": [{"id": "d02.deck.e400n40", "district_id": "d02", "polygon": _sq(300, 20, 500, 60),
                   "top_m": 9.0, "slab_m": 1.2}],
        "road_segments": [
            {"id": "rs.w", "road_class": "street", "width_m": 12.0,
             "centerline": [[0.0, 106.0], [256.0, 106.0]]},
            {"id": "rs.e", "road_class": "street", "width_m": 12.0,
             "centerline": [[256.0, 106.0], [512.0, 106.0]]},
            {"id": "rs.via", "road_class": "avenue", "width_m": 16.0,
             "centerline": [[300.0, 180.0], [500.0, 180.0]],
             "z_profile": [{"s": 0.0, "z": 9.0}, {"s": 200.0, "z": 9.0}]}],
        "skybridges": [{"id": "d02.sb.e450n90", "line": [[450.0, 70.0], [450.0, 95.0]],
                        "z_m": 61.0, "width_m": 5.0, "clearance_m": 60.0}],
    }


@pytest.fixture
def city(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    return b


def _weather(build, od):
    c = PL.City(build)
    f = S.fill(S.AtmosSpec(), list(c.districts.values()))
    pl = PL.Plan(c, f)
    w = WE.Weather(pl, f)
    w.covers()
    w.surfaces()
    w.spots()
    w.masks_of(od)
    w.drips_of(od)
    return w, f


def _mask(od, tile):
    with Image.open(od / "masks" / f"{tile}.png") as im:
        return np.asarray(im.convert("RGBA"), dtype=np.uint8)


def _at(a, x, y, tile_x0=0.0, tile_y1=256.0, t=0.5):
    return a[int((tile_y1 - y) / t), int((x - tile_x0) / t)]


def test_covers_and_their_shadow_downwind(city, tmp_path):
    w, _ = _weather(city, tmp_path / "atmos")
    by = {r["id"]: r for r in w.cover_list}
    aw = by["d01.prop.awning.e100n115"]
    # the awning at 3.2 m, its shadow moved downwind (north-east, 40 degrees) by its height
    # times the lean
    s = min(P.WIND["shift_max_m"], 3.15 * P.WIND["lean"])
    assert aw["dx"] == pytest.approx(s * np.cos(np.radians(40.0)), abs=1e-6)
    assert aw["dy"] == pytest.approx(s * np.sin(np.radians(40.0)), abs=1e-6)
    # its dripping edge the street's side (south, away from the shop's wall)
    (a, b), z = aw["drips"][0]
    assert a[1] == pytest.approx(114.0) and b[1] == pytest.approx(114.0) and z == pytest.approx(3.2)
    # the deck from its underside; the viaduct's pieces; the overhanging block; the skybridge
    # too high to shelter anything
    assert by["d02.deck.e400n40"]["under"] == pytest.approx(9.0 - 1.2)
    assert any(r["kind"] == "road" for r in w.cover_list)
    assert by["d02.lot.e400n130.bld.m1"]["under"] == pytest.approx(6.0)
    assert "d02.sb.e450n90" not in by
    assert w.report["skipped"].get("skybridge: higher than the rain shelters") == 1


def test_masks_cover_gloss_puddles_and_drips(city, tmp_path):
    od = tmp_path / "atmos"
    w, _ = _weather(city, od)
    assert sorted(m["tile"] for m in w.masks) == ["t+00+00", "t+01+00"]
    a = _mask(od, "t+00+00")
    assert a.shape == (512, 512, 4)
    z0, step = w.z0, w.step
    # under the awning (moved downwind): its underside; the street in front of it open
    v = _at(a, 101.0, 115.5)
    assert v[0] > 0 and z0 + v[0] * step == pytest.approx(3.15, abs=step)
    assert _at(a, 100.0, 106.0)[0] == 0
    # gloss by surface: the carriageway mirrors, the canal none, the shop's roof between
    assert _at(a, 50.0, 106.0)[3] == round(255 * P.SURFACE_GLOSS["road"])
    assert _at(a, 100.0, 200.0)[3] == 0
    assert _at(a, 100.0, 126.0)[3] == round(255 * P.SURFACE_GLOSS["roof"])
    # the drip band just past the awning's street edge, moved downwind as its shadow
    band = a[int((256 - 114.5) / 0.5) - 6:int((256 - 114.5) / 0.5) + 2, 200:240, 2]
    assert band.max() == 255
    # puddles: on the paved street only, never under a cover, on the roof or the water
    pud = a[..., 1] > 0
    assert pud.any()
    assert not (pud & (a[..., 0] > 0)).any()
    assert not (pud & (a[..., 3] == 0)).any()
    assert not (pud & (a[..., 3] == round(255 * P.SURFACE_GLOSS["roof"]))).any()
    # the deck's and the overhang's shadow in the core's tile, the viaduct's
    b = _mask(od, "t+01+00")
    assert z0 + _at(b, 400.0, 40.0, 256.0)[0] * step == pytest.approx(7.8, abs=step)
    assert z0 + _at(b, 400.0, 116.0, 256.0)[0] * step == pytest.approx(6.0, abs=step)
    assert _at(b, 400.0, 182.0, 256.0)[0] > 0


def test_gritty_streets_hold_more_water(city, tmp_path):
    od = tmp_path / "atmos"
    _weather(city, od)
    a, b = _mask(od, "t+00+00"), _mask(od, "t+01+00")
    rows = slice(int((256 - 112) / 0.5), int((256 - 100) / 0.5))
    old = float((a[rows, :, 1] > 0).mean())
    core = float((b[rows, :, 1] > 0).mean())
    # (the old town gritty, its drains clogged; the core clean: decision 12.5)
    assert old > core


def test_drips_by_tile(city, tmp_path):
    od = tmp_path / "atmos"
    w, _ = _weather(city, od)
    kinds = {d["kind"] for d in w.drip_list}
    assert {"awning", "deck", "road"} <= kinds
    aw = [d for d in w.drip_list if d["owner_id"] == "d01.prop.awning.e100n115"]
    # the awning's 30 m edge in pieces of at most 8 m
    assert len(aw) == 4 and all(d["z_m"] == pytest.approx(3.2) for d in aw)
    assert all(d["ground_m"] == 0.0 and d["a"][1] == pytest.approx(114.0) for d in aw)
    doc = json.loads((od / "drips" / "t+00+00.json").read_text(encoding="utf-8"))
    PM.TileDrips.model_validate(doc)
    assert len({d["id"] for d in w.drip_list}) == len(w.drip_list)


def test_states_and_settings(city, tmp_path):
    w, f = _weather(city, tmp_path / "atmos")
    s = w.settings()
    PM.Weather(**s)
    assert list(s["states"]) == list(P.WEATHERS) and s["start"] == f["weather"] == "rain"
    st = s["states"]
    # rain fills the puddles, drizzle a share with short streaks, a clear night opens the deck
    assert st["rain"]["puddles"] == 1.0 and 0 < st["drizzle"]["puddles"] < 1
    assert st["drizzle"]["streak"] < st["rain"]["streak"]
    assert st["clear"]["rain"] == 0 and st["clear"]["cover"] < st["rain"]["cover"]
    assert st["fog"]["fog_density"] > st["rain"]["fog_density"] > st["clear"]["fog_density"]
    assert s["times"]["drain_s"] > s["times"]["fill_s"] and s["times"]["dry_s"] > s["times"]["wet_s"]


def test_check_finds_a_misplaced_puddle(city, tmp_path):
    od = tmp_path / "atmos"
    w, _ = _weather(city, od)
    assert w.check(od)["ok"]
    # a puddle drawn on the water
    a = _mask(od, "t+00+00").copy()
    a[int((256 - 200) / 0.5) - 5:int((256 - 200) / 0.5) + 5, 200:260, 1] = 200
    Image.fromarray(a, "RGBA").save(od / "masks" / "t+00+00.png")
    c = w.check(od)
    assert not c["ok"] and c["puddles_misplaced"] >= 100
    assert "weather check: FAIL" in WE.check_text(c)


def test_wind_heading_from_the_spec(city, tmp_path):
    c = PL.City(city)
    f = S.fill(S.AtmosSpec(wind_deg=180.0), list(c.districts.values()))
    w = WE.Weather(PL.Plan(c, f), f)
    w.covers()
    aw = next(r for r in w.cover_list if r["kind"] == "awning")
    assert aw["dx"] < 0 and aw["dy"] == pytest.approx(0.0, abs=1e-9)


def test_noise_is_deterministic():
    x = np.array([0.0, 12.5, -300.25])
    y = np.array([5.0, -7.5, 1000.0])
    a = WE.value_noise(x, y, 3.0, 7)
    assert np.array_equal(a, WE.value_noise(x, y, 3.0, 7))
    assert ((a >= 0) & (a <= 1)).all()
    assert not np.array_equal(a, WE.value_noise(x, y, 3.0, 8))


def test_plan_records_the_weather(city):
    # (the deck's soffit lights need a whole model, AG10's; its shadow is tested above)
    m = _model()
    del m["decks"]
    (city / "city_model.json").write_text(json.dumps(m), encoding="utf-8")
    rep = PL.build_plan(city)
    od = city / "atmos"
    plan = json.loads((od / "atmos_plan.json").read_text(encoding="utf-8"))
    PM.AtmosPlan.model_validate(plan)
    wp = plan["weather_plan"]
    assert wp["start"] == "rain" and len(plan["masks"]) == 2
    assert plan["checks"]["weather"]["ok"] and rep["weather"]["ok"]
    assert wp["counts"]["drips"] == sum(d["count"] for d in wp["drip_tiles"]) > 0
    ctb = json.loads((od / "unreal_contribution.atmos.json").read_text(encoding="utf-8"))
    assert any(e["key"] == "atmos.weather.t+00+00" and e["kind"] == "weather"
               for e in ctb["entries"])
    assert "weather check: PASS" in (od / "atmos_report.txt").read_text(encoding="utf-8")
    # unchanged: nothing written again (the masks and drips neither)
    m0 = {f.name: f.stat().st_mtime_ns for f in (od / "masks").iterdir()}
    assert PL.build_plan(city)["wrote"] == []
    assert {f.name: f.stat().st_mtime_ns for f in (od / "masks").iterdir()} == m0
    # the previews
    out = WE.preview(od, plan)
    assert (od / WE.PREVIEW).is_file() and (od / WE.DETAIL).is_file()
    assert out["detail_tile"] in ("t+00+00", "t+01+00")
