"""AT6: the look (atmosgen/look.py, docs/atmosgen_scope.md 6.5): the post and grade per preset
(a night and a day set: neon rain's teal shadows and magenta highlights), a post per district
by its grit and archetype (decision 12.5: clean and crisp in the corporate core, gritty in
old towns and the port), the district raster the runtime blends them by, the exposure's day
bias and overcast compensation, the plan's and the exporter's records, the review sheet and
the spec diff. The runtime renders it in Unreal (`citygen unreal --check`'s look,
docs/progress/AT6)."""

import json

import numpy as np
import pytest

from atmosgen import look as LK
from atmosgen import plan as PL
from atmosgen import presets as P
from atmosgen import review as RV
from atmosgen import sky as SK
from atmosgen import spec as S
from citygen import unreal_atmos as UA


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _moods(arch, wealth, danger):
    return S.mood(arch, wealth, danger) | {"archetype": arch, "name": arch}


def test_tint_gain_is_a_hue_at_the_same_brightness():
    assert LK.tint_gain("#163a52", 0.0) == [1.0, 1.0, 1.0]
    teal = LK.tint_gain("#163a52", 0.16)
    assert teal[0] < 0.9 < 1.1 < teal[2] and sum(teal) / 3.0 == pytest.approx(1.0, abs=1e-3)
    mag = LK.tint_gain("#ff4fb4", 0.08)
    assert mag[0] > 1.0 > mag[1] and sum(mag) / 3.0 == pytest.approx(1.0, abs=1e-3)
    # a grey tints nothing
    assert LK.tint_gain("#808080", 0.5) == pytest.approx([1.0, 1.0, 1.0])


def test_look_sets_by_night_and_by_day_with_the_spec_over_them():
    base = LK.look_sets("neon_rain")
    n, d = base["night"], base["day"]
    assert set(P.POST_KEYS) <= set(n) and n["shadows"][0] == "#163a52"
    # neon rain: teal shadows and magenta highlights by night, softer by day; more glow,
    # grain and fringes by night; local exposure lifts the day's shadows (under a viaduct)
    assert n["shadows_gain"][2] > d["shadows_gain"][2] > 1.0
    assert n["highlights_gain"][0] > 1.0 > n["highlights_gain"][1]
    assert n["bloom"] > d["bloom"] and n["grain"] > d["grain"] and n["chromatic"] > d["chromatic"]
    assert d["local_shadows"] < n["local_shadows"] <= 1.0
    # the spec's art direction: multipliers, the tints' colors and strength
    sp = S.AtmosSpec.model_validate({"post": {"bloom": 2.0, "grain": 0.0, "tint": 0.0,
                                              "highlights": "#ffb000"}}).post.model_dump()
    g = LK.look_sets("neon_rain", sp)
    assert g["night"]["bloom"] == pytest.approx(2.0 * n["bloom"]) and g["night"]["grain"] == 0.0
    assert g["night"]["shadows_gain"] == [1.0, 1.0, 1.0]
    assert g["night"]["highlights"][0] == "#ffb000"
    # every look has both sets, every value in Unreal's range
    for look in P.LOOKS:
        for when, s in LK.look_sets(look).items():
            assert 0.0 <= s["grain"] <= 1.0 and 0.0 <= s["vignette"] <= 1.0, (look, when)


def test_districts_clean_or_gritty_by_place():
    """Decision 12.5: the corporate core crisp (little grain and fringing, more contrast and
    sharpening, no lift), old towns and the port gritty (grain, fringes, flares, lifted blacks,
    muted color but for the neon), each its archetype's tint."""
    base = LK.look_sets("neon_rain")
    core = LK.district_sets(base, _moods("corporate_core", 0.9, 0.1))["night"]
    old = LK.district_sets(base, _moods("old_town", 0.2, 0.8))["night"]
    port = LK.district_sets(base, _moods("industrial_port", 0.3, 0.7))["night"]
    for gritty in (old, port):
        assert gritty["grain"] > base["night"]["grain"] > core["grain"]
        assert gritty["chromatic"] > core["chromatic"] and gritty["flare"] > core["flare"]
        assert gritty["sharpen"] < core["sharpen"] and gritty["contrast"] < core["contrast"]
        assert gritty["lift"] > core["lift"] == 0.0 and gritty["vignette"] > core["vignette"]
        assert gritty["saturation"] < core["saturation"]
        assert gritty["highlight_sat"] > core["highlight_sat"]
        # sodium amber highlights, the core's cool blue shadows
        assert gritty["highlights_gain"][0] > gritty["highlights_gain"][2]
    assert core["shadows_gain"][2] > base["night"]["shadows_gain"][2]
    # the spec's district tint and its strength
    md = _moods("old_town", 0.2, 0.8) | {"tint": 0.0}
    assert LK.district_sets(base, md)["night"]["highlights_gain"] == \
        base["night"]["highlights_gain"]


def test_the_raster_finds_every_cell_its_district():
    m = {"bounds": [0.0, 0.0, 300.0, 200.0],
         "districts": [{"id": "d01", "polygon": _sq(0.0, 0.0, 140.0, 200.0)},
                       {"id": "d02", "polygon": _sq(160.0, 0.0, 300.0, 200.0)}]}
    r = LK.raster(m, ["d01", "d02"], cell_m=20.0)
    idx = r["idx"]
    assert idx.shape == (10, 15) and r["bounds"] == [0.0, 0.0, 300.0, 200.0]
    assert set(np.unique(idx).tolist()) == {0, 1}            # the gap the nearest's
    assert (idx[:, :7] == 0).all() and (idx[:, 8:] == 1).all()
    # rows from the north edge: a district in the north half only
    m["districts"][1]["polygon"] = _sq(160.0, 100.0, 300.0, 200.0)
    m["districts"].append({"id": "d03", "polygon": _sq(160.0, 0.0, 300.0, 100.0)})
    idx = LK.raster(m, ["d01", "d02", "d03"], cell_m=20.0)["idx"]
    assert idx[0, -1] == 1 and idx[-1, -1] == 2
    # the runs: every cell once, in order
    runs = LK.runs(idx)
    assert sum(runs[0::2]) == idx.size
    flat = np.concatenate([np.full(c, v) for c, v in zip(runs[0::2], runs[1::2])])
    assert (flat == idx.reshape(-1)).all()


def test_the_grade_is_unreals():
    """With every value at Unreal's default the grade changes nothing; teal shadows tint the
    dark, magenta highlights the bright, the mid tones neither."""
    ident = {"saturation": 1.0, "contrast": 1.0, "highlight_sat": 1.0, "lift": 0.0,
             "shadows_gain": [1.0, 1.0, 1.0], "highlights_gain": [1.0, 1.0, 1.0]}
    c = np.array([[0.01, 0.02, 0.03], [0.2, 0.18, 0.15], [2.0, 1.0, 0.5]])
    assert np.allclose(LK.grade(c, ident), c)
    s = LK.look_sets("neon_rain")["night"]
    g = LK.grade(np.array([[0.01, 0.01, 0.01], [3.0, 3.0, 3.0]]), s)
    assert g[0, 2] > g[0, 0] and g[1, 0] > g[1, 1]
    sw = LK.swatch(s)
    assert sw.dtype == np.uint8 and sw.shape[2] == 3


def test_exposure_by_day_and_the_overcast():
    f = S.fill(S.AtmosSpec.model_validate({"post": {"day_ev_bias": -0.5,
                                                    "overcast_comp": 0.4}}), [])
    sky = SK.make(f, f["sky"])
    post, ras = LK.make(f, sky, {"bounds": [0, 0, 10, 10], "districts": []})
    ex = post["exposure"]
    assert ras is None and post["districts"] == {}
    # (a clear day's exposure, the runtime moving it by the clouds there are)
    assert ex["day_ev100"] == pytest.approx(P.DAY_EV100 - 0.5) and ex["overcast_comp"] == 0.4
    assert ex["night_ev100"] == sky["ev_night"] and ex["ref_cover"] == 0.0
    # rain's clouds give a brighter exposure, a clear sky's none, the more the more given back
    assert LK.overcast_shift(0.75, 0.85) < LK.overcast_shift(0.4, 0.85) < 0.0
    assert LK.overcast_shift(0.75, 0.15) == 0.0
    assert ex["look_cover_shift"] == pytest.approx(LK.overcast_shift(0.4, sky["cloud_cover"]),
                                                   abs=1e-4)


def _model():
    return {
        "name": "Look Town", "bounds": [-50.0, -50.0, 350.0, 50.0],
        "districts": [
            {"id": "d01", "name": "Core", "archetype": "corporate_core",
             "params": {"wealth": 0.9, "danger": 0.1}, "polygon": _sq(-50.0, -50.0, 150.0, 50.0)},
            {"id": "d02", "name": "Old Quarter", "archetype": "old_town",
             "params": {"wealth": 0.2, "danger": 0.8}, "polygon": _sq(150.0, -50.0, 350.0, 50.0)}],
        "road_segments": [{"id": "rs.e150s0", "road_class": "street",
                           "centerline": [[0.0, 0.0], [300.0, 0.0]], "width_m": 12.0,
                           "cross_section": {"sidewalk_m": [3.0, 3.0]}}],
        "props": [
            {"id": f"d0{1 + (x >= 150)}.prop.street_light.e{x}s5", "type": "prop.street_light",
             "attrs": {"sidewalk": "rs.e150s0.swr"}, "position": [float(x), -5.5, 0.0],
             "yaw_deg": 90.0, "scale": [1.0, 1.0, 1.0]} for x in range(10, 300, 15)],
        "buildings": [],
        "walkways": [{"id": "wk.e150s5", "kind": "sidewalk", "attrs": {"segment": "rs.e150s0"},
                      "line": [[0.0, -5.0, 0.0], [300.0, -5.0, 0.0]], "width_m": 3.0}],
    }


@pytest.fixture
def build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    rep = PL.build_plan(b)
    assert rep["ok"], rep["lux"]["failures"]
    return b


def test_the_plan_and_the_exporter_carry_the_look(build):
    plan = json.loads((build / "atmos" / "atmos_plan.json").read_text())
    post = plan["post"]
    assert post["order"] == ["d01", "d02"] and set(post["districts"]) == {"d01", "d02"}
    assert post["districts"]["d02"]["night"]["grain"] > post["districts"]["d01"]["night"]["grain"]
    r = post["raster"]
    assert (build / "atmos" / r["file"]).is_file() and r["cell_m"] == P.POST_CELL_M
    idx = LK.read(build / "atmos", r)
    assert set(np.unique(idx).tolist()) == {0, 1}
    rep = json.loads((build / "atmos" / "atmos_report.json").read_text())
    assert set(rep["post"]["districts"]) == {"Core", "Old Quarter"}
    assert "post: exposure" in (build / "atmos" / "atmos_report.txt").read_text()
    # the exporter: the sets in POST_FLOATS order, the district raster as runs in Unreal's frame
    UA.write_atmos(build)
    ctl = json.loads((build / "unreal" / UA.DATA).read_text())["controller"]
    nf = len(UA.POST_FLOATS)
    assert nf == len(P.POST_KEYS) + 6 == 20
    assert list(UA.POST_FLOATS[:len(P.POST_KEYS)]) == list(P.POST_KEYS)
    assert ctl["post"] and len(ctl["post_base"]) == 2 * nf
    assert ctl["post_base"][0] == post["base"]["night"]["bloom"]
    assert ctl["post_base"][nf + UA.POST_FLOATS.index("shadows_b")] == \
        post["base"]["day"]["shadows_gain"][2]
    assert ctl["post_names"] == ["Core", "Old Quarter"]
    assert len(ctl["post_districts"]) == 2 * 2 * nf
    w, h = ctl["post_px"]
    assert sum(ctl["post_runs"][0::2]) == w * h
    x0, y0, x1, y1 = r["bounds"]
    assert ctl["post_bounds"] == [x0 * 100.0, -y1 * 100.0, x1 * 100.0, -y0 * 100.0]
    assert ctl["day_ev100"] == post["exposure"]["day_ev100"]
    assert ctl["steam_glow"] == P.STEAM_GLOW and ctl["steam_far"] == list(P.STEAM_FAR)
    # a plan before AT6 has no look on the controller
    del plan["post"]
    (build / "atmos" / "atmos_plan.json").write_text(json.dumps(plan))
    assert not UA.post_settings(plan, build / "atmos")


def test_the_review_sheet(build, tmp_path):
    from PIL import Image
    shots = tmp_path / "shots"
    shots.mkdir()
    Image.new("RGB", (64, 36), (10, 12, 20)).save(shots / "unreal_night_core.png")
    Image.new("RGB", (64, 36), (120, 120, 120)).save(shots / "unreal_pday_core.png")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"post": {"grain": 1.2}}))
    rec = RV.review(build, spec, shots=shots)
    md = (build / "atmos" / "review.md").read_text()
    assert rec["round"] == 1 and rec["passed"] and "Old Quarter" in md and "## Shots" in md
    assert rec["shot_numbers"]["night_core"]["stops"] < rec["shot_numbers"]["pday_core"]["stops"]
    assert (build / "atmos" / "review_shots.jpg").is_file()
    # a second round: the spec's changes and the last round's shots beside
    first = tmp_path / "round1"
    first.mkdir()
    (first / "review.json").write_text((build / "atmos" / "review.json").read_text())
    spec.write_text(json.dumps({"post": {"grain": 0.8}, "districts": {"Core": {"grit": 0.0}}}))
    rec2 = RV.review(build, spec, prev=first, shots=shots, prev_shots=shots)
    assert rec2["round"] == 2
    assert "post.grain: 1.2 -> 0.8" in rec2["spec_changes"]
    assert any(c.startswith("districts:") for c in rec2["spec_changes"])
    assert rec2["prev_shot_numbers"]["night_core"] == rec2["shot_numbers"]["night_core"]


def test_spec_diff():
    a = {"preset": "neon_rain", "post": {"bloom": 1.0}}
    b = {"preset": "clear_night", "post": {"bloom": 1.0, "grain": 0.5}}
    assert RV.spec_diff(a, b) == ['post.grain: (none) -> 0.5',
                                  'preset: "neon_rain" -> "clear_night"']
