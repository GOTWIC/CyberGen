"""AT3: the sky and time (atmosgen/sky.py, docs/atmosgen_scope.md 6.2): the sun and the moon
by the hour, the curves over the sun's elevation the runtime follows, the schedules the sun
sets, the cloud deck's glow from the plan's upward light, and the plan's and the exporter's
records of them. The runtime renders them in Unreal (`citygen unreal --check`'s sky and time,
docs/progress/AT3)."""

import json
import math

import numpy as np
import pytest

from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P
from atmosgen import sky as SK
from atmosgen import spec as S


def _sky(**given):
    f = S.fill(S.AtmosSpec.model_validate({"sky": given} if given else {}), [])
    return SK.make(f, f["sky"]), f


def test_sun_by_latitude_and_season():
    # the equinox at 35 north: up at 6, culminating in the south at 55 degrees, down at 18
    s = {"latitude_deg": 35.0, "declination_deg": 0.0}
    e, az, d = SK.sun_at(s, 12.0)
    assert e == pytest.approx(55.0, abs=1e-6) and az == pytest.approx(180.0)
    assert d[1] < 0.0 and d[2] > 0.0 and math.hypot(*d) == pytest.approx(1.0)
    e6, az6, d6 = SK.sun_at(s, 6.0)
    assert e6 == pytest.approx(0.0, abs=1e-6) and az6 == pytest.approx(90.0) and d6[0] > 0.99
    assert SK.sun_at(s, 18.0)[1] == pytest.approx(270.0)
    # midsummer (the default day): a long day, the night's hour well under the horizon
    sky, _ = _sky()
    assert sky["declination_deg"] == pytest.approx(23.4, abs=0.2)
    rows = {r["hour"]: r for r in sky["by_hour"]}
    assert rows[12]["sun_elev"] == pytest.approx(90.0 - 35.0 + 23.44, abs=0.2)
    assert rows[23]["sun_elev"] < -18.0 and rows[16]["sun_elev"] > 20.0
    # the named hours: dusk where the sun stands at the dusk elevation in the evening
    h = sky["hours"]
    assert h["night"] == 23.0 and h["day"] == P.SKY["day_hour"]
    assert SK.sun_at(sky, h["dusk"])[0] == pytest.approx(P.SKY["dusk_elevation_deg"], abs=0.25)
    assert 18.5 < h["dusk"] < 20.5
    # the southern hemisphere's midsummer is the north's midwinter: a short day
    south, _ = _sky(latitude_deg=-35.0)
    assert south["hours"]["dusk"] < h["dusk"] - 1.5


def test_moon_trails_the_sun_by_its_phase():
    sky, _ = _sky()
    m = sky["moon"]
    assert m["lag_h"] == pytest.approx(24.0 * 0.62) and 0.8 < m["lit"] < 0.9
    # a waning gibbous: up in the east-southeast by the night's hour
    me, maz, _ = SK.moon_at(sky, 23.0)
    assert 5.0 < me < 30.0 and 90.0 < maz < 150.0
    # full: opposite the sun, fully lit; new: with it, dark
    full, _ = _sky(moon_phase=0.5)
    assert full["moon"]["lit"] == pytest.approx(1.0)
    e, az, _ = SK.sun_at(full, 21.0)
    me, maz, _ = SK.moon_at(full, 21.0)
    assert abs(((maz - az) % 360.0) - 180.0) < 30.0
    new, _ = _sky(moon_phase=0.0)
    assert new["moon"]["lit"] == 0.0


def test_curves_hold_the_night_and_follow_the_sun():
    sky, f = _sky()
    cv = sky["curve"]
    assert len({len(v) for v in cv.values()}) == 1 and cv["elev"] == sorted(cv["elev"])
    # the exposure: the night's below the twilight, the day's in daylight, monotone between
    evs = [SK.exposure(sky, e) for e in range(-30, 40)]
    assert all(b >= a for a, b in zip(evs, evs[1:]))
    assert SK.exposure(sky, -20.0) == P.SCENE_NIGHT_EV100 == sky["ev_night"]
    # (neon_rain's closed deck darkens the day: AT6, a clear day's exposure moved by the
    # overcast's compensation of the light it takes, a brighter exposure)
    from atmosgen.look import overcast_shift
    comp = P.POST_EXPOSURE["neon_rain"]["overcast_comp"]
    assert SK.exposure(sky, 40.0) == pytest.approx(P.DAY_EV100 + overcast_shift(comp, 0.8),
                                                   abs=1e-3)
    assert SK.exposure(sky, 40.0) < P.DAY_EV100
    assert SK.curve("night", -13.0) == 1.0 and SK.curve("night", 12.0) == 0.0
    assert 0.0 < SK.curve("night", -2.0) < 1.0
    # the stars only in the dark, the sun's light until well under the horizon
    assert SK.curve("stars", 10.0) == 0.0 and SK.curve("stars", -15.0) == 1.0
    assert SK.curve("sun", -5.0) > 0.0 and SK.curve("sun", -13.0) == 0.0
    # a clear night has no deck to darken its day
    clear = S.fill(S.AtmosSpec(preset="clear_night"), [])
    cs = SK.make(clear, clear["sky"])
    assert cs["ev_day"] > sky["ev_day"] and cs["stars"] > sky["stars"]
    # the spec's sky over the look's
    deck, _ = _sky(cloud_deck_m=0.0)
    assert deck["cloud_deck_m"] == 0.0 and deck["cloud_cover"] == 0.0


def test_schedules_the_sun_sets():
    sky, _ = _sky()
    sc = SK.schedules(sky)
    dd = sc["dusk_dawn"]
    assert len(dd) == 24 and dd[0] == dd[23] == 1.0 and dd[12] == 0.0
    # on as the sun goes down: from +3 degrees, fully under -3
    for h in range(24):
        e = SK.sun_at(sky, float(h))[0]
        if e > 3.0:
            assert dd[h] == 0.0
        if e < -3.0:
            assert dd[h] == 1.0
    assert sc["tunnel"][12] == 0.6 and sc["tunnel"][0] == 1.0


def _light(x, y, cd, aim=(0.0, 90.0), shape="spot", cone=(10.0, 20.0), color=(1.0, 1.0, 1.0)):
    return {"id": f"l.{x}.{y}", "pos": [x, y, 10.0], "aim": list(aim), "shape": shape,
            "cd": cd, "cone": list(cone), "color": list(color), "schedule": "always",
            "on": True}


def test_flux_and_what_goes_up():
    up = _light(0.0, 0.0, 1000.0)
    assert SK.flux(up) == pytest.approx(1000.0 * 2 * math.pi * (1 - math.cos(math.radians(15))))
    assert SK.up_share(up) == 1.0
    down = _light(0.0, 0.0, 1000.0, aim=(0.0, -90.0))
    assert SK.up_share(down) == 0.0
    assert SK.upward(down) == pytest.approx(SK.flux(down) * P.GROUND_REFLECT * P.ESCAPE[1])
    face = {**up, "shape": "rect", "aim": [0.0, 0.0], "cd": 100.0}
    assert SK.flux(face) == pytest.approx(math.pi * 100.0) and SK.up_share(face) == 0.5
    level = _light(0.0, 0.0, 1000.0, aim=(0.0, 0.0))
    assert SK.up_share(level) == pytest.approx(0.5)


def test_glow_is_the_upward_flux_on_the_deck():
    sky, _ = _sky()
    h = sky["cloud_deck_m"]
    ls = [_light(1000.0, 500.0, 50000.0, color=(1.0, 0.3, 0.1))]
    g = SK.glow(sky, ls, {"always": [1.0] * 24}, [0.0, 0.0, 2000.0, 1000.0])
    phi = SK.upward(ls[0])
    assert g["upward_lm"] == pytest.approx(phi)
    # brightest over the light, falling off over the deck's height
    assert math.dist(g["peak_at"], [1000.0, 500.0]) <= P.GLOW_CELL_M
    # what lands on the deck is (nearly) all of it: the footprint integrates to 1 over the
    # plane (to GLOW_REACH deck heights out: 1 - 1/(1 + 3^2) = 0.9)
    Lum = g["rgb"]
    k = P.CLOUD_ALBEDO / math.pi * sky["cloud_glow"]
    Y = 0.2126 * Lum[..., 0] + 0.7152 * Lum[..., 1] + 0.0722 * Lum[..., 2]
    E_total = float(Y.sum()) * P.GLOW_CELL_M ** 2 / k
    assert E_total == pytest.approx(phi * (1.0 - 1.0 / (1.0 + P.GLOW_REACH ** 2)), rel=0.05)
    # its color the light's, the peak's luminance the footprint's at r = 0
    i, j = np.unravel_index(int(np.argmax(Y)), Y.shape)
    assert Lum[i, j, 0] > Lum[i, j, 1] > Lum[i, j, 2]
    assert float(Y.max()) == pytest.approx(phi / (math.pi * h * h) * k, rel=0.1)
    # rows north to south: the north row is the bounds' top
    assert g["bounds"][3] > g["bounds"][1]
    # no deck, no glow
    flat, _ = _sky(cloud_deck_m=0.0)
    assert SK.glow(flat, ls, {"always": [1.0] * 24}, [0.0, 0.0, 2000.0, 1000.0]) is None


def test_glow_png_round_trips(tmp_path):
    sky, _ = _sky()
    ls = [_light(500.0, 500.0, 80000.0)]
    g = SK.glow(sky, ls, {"always": [1.0] * 24}, [0.0, 0.0, 1000.0, 1000.0])
    rec = SK.write_glow(g, tmp_path)
    from PIL import Image
    img = np.asarray(Image.open(tmp_path / rec["file"]), dtype=float) / 255.0
    assert list(img.shape[:2]) == rec["px"][::-1]
    back = img ** 2 * rec["max_nits"]
    assert float(np.abs(back - g["rgb"]).max()) <= 0.02 * rec["max_nits"]
    # the same glow writes the same bytes, and no file again
    t0 = (tmp_path / rec["file"]).stat().st_mtime_ns
    assert SK.write_glow(g, tmp_path) == rec and (tmp_path / rec["file"]).stat().st_mtime_ns == t0


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _model():
    """test_unreal_atmos's city: street lights along a street, a bar's shopfront."""
    return {
        "name": "Atmos Sky", "bounds": [-50.0, -50.0, 350.0, 50.0],
        "districts": [{"id": "d01", "name": "Core", "archetype": "corporate_core",
                       "params": {"wealth": 0.9, "danger": 0.1},
                       "polygon": _sq(-50.0, -50.0, 350.0, 50.0)}],
        "road_segments": [{"id": "rs.e150s0", "road_class": "street",
                           "centerline": [[0.0, 0.0], [300.0, 0.0]], "width_m": 12.0,
                           "cross_section": {"sidewalk_m": [3.0, 3.0]}}],
        "props": [
            {"id": f"d01.prop.street_light.e{x}s5", "type": "prop.street_light",
             "attrs": {"sidewalk": "rs.e150s0.swr"}, "position": [float(x), -5.5, 0.0],
             "yaw_deg": 90.0, "scale": [1.0, 1.0, 1.0]} for x in range(10, 300, 15)],
        "buildings": [{"id": "d01.lot.e20s20.bld", "district_id": "d01",
                       "footprint": _sq(10, -30, 30, -10),
                       "masses": [{"footprint": _sq(10, -30, 30, -10), "z0_m": 0.0,
                                   "z1_m": 12.0}],
                       "units": [{"edge": [[10.0, -10.0], [30.0, -10.0]], "use": "bar",
                                  "width_m": 8.0}]}],
        "walkways": [{"id": "wk.e150s5", "kind": "sidewalk", "attrs": {"segment": "rs.e150s0"},
                      "line": [[0.0, -5.0, 0.0], [300.0, -5.0, 0.0]], "width_m": 3.0}],
    }


def _build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    return b


def test_plan_carries_the_sky(tmp_path):
    b = _build(tmp_path)
    rep = PL.build_plan(b)
    assert rep["ok"]
    plan = json.loads((b / "atmos" / "atmos_plan.json").read_text())
    PM.AtmosPlan.model_validate(plan)
    sky = plan["sky"]
    assert sky["hours"]["night"] == plan["hour"] == 23.0 and len(sky["by_hour"]) == 24
    # the sun sets the street lights' schedule; the glow came from the plan's lights
    assert plan["schedules"]["dusk_dawn"] == SK.schedules(sky)["dusk_dawn"]
    g = sky["glow"]
    assert g and (b / "atmos" / g["file"]).is_file() and sky["upward_lm"] > 0
    assert g["max_luma_nits"] > g["mean_nits"] > 0.0
    assert rep["sky"]["glow"]["max_luma_nits"] == g["max_luma_nits"]
    # without a deck the plan has no glow, and the file goes
    (b / "spec.json").write_text(json.dumps({"sky": {"cloud_deck_m": 0}}), encoding="utf-8")
    PL.build_plan(b, b / "spec.json")
    plan = json.loads((b / "atmos" / "atmos_plan.json").read_text())
    assert plan["sky"]["glow"] is None and not (b / "atmos" / SK.GLOW_FILE).exists()


def test_exporter_hands_the_sky_to_the_controller(tmp_path):
    from citygen import unreal_atmos as UA
    b = _build(tmp_path)
    PL.build_plan(b)
    at = UA.write_atmos(b)
    data = json.loads((b / "unreal" / UA.DATA).read_text())
    plan = json.loads((b / "atmos" / "atmos_plan.json").read_text())
    ctl, sky = data["controller"], plan["sky"]
    assert ctl["latitude_deg"] == sky["latitude_deg"] and ctl["dusk_hour"] == sky["hours"]["dusk"]
    # (AT6: the controller's day exposure is a clear day's, the post's: the runtime moves it by
    # the clouds there are, as the sky's own `ev_day` is at the look's cover)
    assert ctl["scene_ev100"] == sky["ev_night"]
    assert ctl["day_ev100"] == plan["post"]["exposure"]["day_ev100"] == P.DAY_EV100 >= \
        sky["ev_day"]
    assert len(ctl["curve_elev"]) == len(ctl["curve_ev"]) == len(ctl["curve_night"]) >= 2
    # the glow's bounds in Unreal's frame (cm, Y south), its file beside the manifest
    x0, y0, x1, y1 = sky["glow"]["bounds"]
    assert ctl["glow_bounds"] == [x0 * 100.0, -y1 * 100.0, x1 * 100.0, -y0 * 100.0]
    assert at["glow"]["file"] == f"unreal/{UA.GLOW}"
    assert (b / at["glow"]["file"]).read_bytes() == (b / "atmos" / SK.GLOW_FILE).read_bytes()
    # the glow is in the controller's hash: another glow, another controller
    h0 = at["hash"]
    (b / "spec.json").write_text(json.dumps({"sky": {"cloud_glow": 2.0}}), encoding="utf-8")
    PL.build_plan(b, b / "spec.json")
    assert UA.write_atmos(b)["hash"] != h0
    # an AT2 plan (no sky) gives the controller none
    assert UA.sky_settings({"sky": {"moon": 0.0, "stars": 0.0}}) == {}
