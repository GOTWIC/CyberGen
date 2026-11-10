"""AT0: atmosgen's spec, presets, plan schema and plan (docs/atmosgen_scope.md), on a small
synthetic build (a city model with a few lamps, signs and shopfronts in two districts)."""

import json
import math
from pathlib import Path

import pytest

from atmosgen import emitters as EM
from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P
from atmosgen import spec as S

ROOT = Path(__file__).resolve().parents[2]


def _model() -> dict:
    sq = {"exterior": [[0.0, 0.0], [20.0, 0.0], [20.0, 12.0], [0.0, 12.0]], "holes": []}
    return {
        "name": "Test Bay",
        "districts": [
            {"id": "d01", "name": "Core", "archetype": "corporate_core",
             "params": {"wealth": 0.9, "danger": 0.15}},
            {"id": "d02", "name": "Old Quarter", "archetype": "old_town",
             "params": {"wealth": 0.3, "danger": 0.65}}],
        "road_segments": [{"id": "rs.e10s5", "road_class": "street"},
                          {"id": "rs.e300n5", "road_class": "pedestrian"}],
        "props": [
            {"id": "d01.prop.street_light.e10s5", "type": "prop.street_light",
             "attrs": {"sidewalk": "rs.e10s5.swl"}, "position": [10.0, -5.0, 0.0],
             "yaw_deg": 90.0, "scale": [1.0, 1.0, 1.0]},
            {"id": "d02.prop.street_light.e300n5", "type": "prop.street_light",
             "attrs": {"sidewalk": "rs.e300n5.swl"}, "position": [300.0, 5.0, 0.0],
             "yaw_deg": 0.0, "scale": [1.0, 1.0, 1.0]},
            {"id": "d02.prop.wall_light.e310n12", "type": "prop.wall_light",
             "attrs": {"sidewalk": "rs.e300n5.swl"}, "position": [310.0, 12.0, 3.0],
             "yaw_deg": -90.0, "scale": [1.0, 1.0, 1.0]},
            {"id": "d01.prop.bench.e12s6", "type": "prop.bench", "position": [12.0, -6.0, 0.0],
             "yaw_deg": 0.0, "scale": [1.0, 1.0, 1.0]}],
        "sign_slots": [
            {"id": "d01.lot.e10n6.bld.slot.billboard.e10n12.z20", "kind": "billboard",
             "mount": "facade", "building_id": "d01.lot.e10n6.bld", "position": [10.0, 12.0, 20.0],
             "yaw_deg": 90.0, "width_m": 6.0, "height_m": 3.0, "emitter": True,
             "two_sided": False},
            {"id": "city.prop.sign.e5n0.slot", "kind": "shop_sign", "mount": "blade",
             "building_id": "d01.lot.e10n6.bld", "position": [5.0, -0.5, 4.0],
             "yaw_deg": -90.0, "width_m": 1.2, "height_m": 3.0, "emitter": True,
             "two_sided": True},
            {"id": "d01.lot.e10n6.bld.slot.holo_ad.e10n20.z40", "kind": "holo_ad",
             "mount": "front", "building_id": "d01.lot.e10n6.bld", "position": [10.0, 20.0, 40.0],
             "yaw_deg": 90.0, "width_m": 8.0, "height_m": 5.0, "emitter": True,
             "two_sided": True}],
        "buildings": [
            {"id": "d01.lot.e10n6.bld", "district_id": "d01", "footprint": sq,
             "units": [{"edge": [[0.0, 0.0], [10.0, 0.0]], "use": "bar", "width_m": 10.0},
                       {"edge": [[10.0, 0.0], [20.0, 0.0]], "use": "food", "width_m": 10.0}]}],
    }


@pytest.fixture
def build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    return b


def test_empty_spec_is_every_default():
    res = S.validate_spec({})
    assert res.ok and res.spec.preset == "neon_rain"
    f = S.fill(res.spec, _model()["districts"])
    assert f["weather"] == "rain" and f["hour"] == 23.0           # decision 12.4
    assert set(f["moods"]) == {"d01", "d02"}
    assert len(P.SCHEDULES["dusk_dawn"]) == 24                     # decision 12.3


def test_moods_clean_or_gritty_by_place():
    """Decision 12.5: a wealthy safe core is clean, a poor dangerous old town gritty."""
    core = S.mood("corporate_core", 0.9, 0.15)
    old = S.mood("old_town", 0.3, 0.65)
    assert core["grit"] < 0.15 < 0.8 < old["grit"]
    assert core["broken"] == 0.0 and old["broken"] > 0.0 and old["flicker"] > core["flicker"]
    assert core["temp"] == "cool" and old["temp"] == "sodium"
    # the same archetype poorer and more dangerous: grittier
    assert S.mood("midtown_mixed", 0.2, 0.9)["grit"] > S.mood("midtown_mixed", 0.8, 0.1)["grit"]


def test_spec_errors_and_names():
    res = S.validate_spec({"preset": "nope"})
    assert not res.ok
    res = S.validate_spec({"districts": {"Cor": {"grit": 0.5}}}, _model())
    assert not res.ok and "did you mean 'Core'" in str(res.errors[0])
    res = S.validate_spec({"palette": {"neon": {"#FF0000": 1}}})
    assert not res.ok                                      # lowercase #rrggbb only
    res = S.validate_spec({"preset": "clear_night", "hour": 2.5,
                           "districts": {"Core": {"grit": 0.6, "palette": ["#ff00aa"]}}},
                          _model())
    assert res.ok
    f = S.fill(res.spec, _model()["districts"])
    assert f["hour"] == 2.5 and f["weather"] == "clear"
    assert f["moods"]["d01"]["grit"] == 0.6 and f["moods"]["d01"]["palette"] == ["#ff00aa"]


def test_schemas_match_the_models():
    """atmosgen/schemas/*.json must match the models (regenerate with `atmosgen spec schema
    atmosgen/schemas/atmos_spec.schema.json` and `atmosgen plan schema --which W
    --out atmosgen/schemas/W.schema.json`)."""
    sdir = ROOT / "atmosgen" / "schemas"
    assert json.loads((sdir / "atmos_spec.schema.json").read_text()) == S.json_schema()
    for name, (model, title) in PM.SCHEMAS.items():
        assert json.loads((sdir / f"{name}.schema.json").read_text()) == \
            PM.json_schema(model, title), name


def test_kelvin():
    w = PL.kelvin_linear(6500)
    assert min(w) > 0.85 and max(w) == 1.0
    s = PL.kelvin_linear(2000)
    assert s[0] == 1.0 and s[2] < 0.1 < s[1] < 0.5


def test_plan(build):
    rep = PL.build_plan(build)
    od = build / "atmos"
    plan = PM.AtmosPlan.model_validate_json((od / "atmos_plan.json").read_text())
    assert plan.counts["street_light"] == 2 and plan.counts["wall_light"] == 1
    assert plan.counts["sign"] == 3 and plan.counts["shop_sign"] == 2 and plan.counts["spill"] == 2
    assert plan.sources["derived"] == plan.counts["all"] and plan.preset == "neon_rain"
    lights = {}
    for t in plan.tiles:
        doc = PM.TileLights.model_validate_json((od / t.file).read_text())
        assert all(L.tile == t.tile for L in doc.lights)
        lights.update({L.id: L for L in doc.lights})
    assert len(lights) == plan.counts["all"]
    # a cobra head over the street: its light hangs under the lamp head (outside its mesh),
    # at the arm's end, tilted toward the carriageway; cool white in the clean core
    a = lights["d01.prop.street_light.e10s5.light"]
    assert a.cls == "cobra_head" and a.shape == "spot" and a.shadow
    assert a.pos == [10.0, -3.5, 7.25] and a.aim == [90.0, -75.0]
    assert a.temp_k == P.TEMPS["cool"] and a.on and a.flicker == 0.0
    # on a pedestrian street a post top; sodium in the old town
    b = lights["d02.prop.street_light.e300n5.light"]
    assert b.cls == "post_top" and b.shape == "point" and b.temp_k == P.TEMPS["sodium"]
    w = lights["d02.prop.wall_light.e310n12.light"]
    assert w.cls == "wall_pack" and math.isclose(w.pos[2], 3.0 - 0.35 - 0.2, abs_tol=1e-6)
    # a billboard's lit face: a rect light its size, a little in front of its frame
    s = lights["d01.lot.e10n6.bld.slot.billboard.e10n12.z20.light"]
    assert s.shape == "rect" and s.size == [6.0, 3.0] and s.tier == "mid"
    assert s.pos[1] > 12.0 + 0.3 and math.isclose(s.cd, P.PHOTOMETRY["sign_face"]["nits"] * 18)
    # a blade sign: two faces, near-tier only; a two-sided holo-board: front and back
    assert {k for k in lights if k.startswith("city.prop.sign.e5n0.slot")} == \
        {"city.prop.sign.e5n0.slot.light", "city.prop.sign.e5n0.slot.light1"}
    assert lights["city.prop.sign.e5n0.slot.light"].tier == "near"
    holo = [L for k, L in lights.items() if "holo_ad" in k]
    assert len(holo) == 2 and {round(L.aim[0]) % 360 for L in holo} == {90, 270}
    # shopfronts spill out of the building, onto the sidewalk south of it
    sp = lights["d01.lot.e10n6.bld.u00.spill"]
    assert sp.pos[1] < 0.0 and round(sp.aim[0]) == -90 and sp.schedule == "bar"
    assert lights["d01.lot.e10n6.bld.u01.spill"].schedule == "food"
    # every light's hash is its record's
    for L in lights.values():
        rec = json.loads(L.model_dump_json(exclude_none=True))
        h = rec.pop("hash")
        assert h == PL.sha(PL.dumps(rec))[:16]
    # the contribution: the controller and a spawner per tile
    con = PM.Contribution.model_validate_json(
        (od / "unreal_contribution.atmos.json").read_text())
    assert con.entries[0].key == "atmos" and \
        {e.key for e in con.entries[1:]} == {f"atmos.lights.{t.tile}" for t in plan.tiles}
    assert rep["counts"] == plan.counts and (od / "atmos_report.txt").is_file()


def test_plan_writes_nothing_when_unchanged(build):
    PL.build_plan(build)
    snap = {p: p.read_bytes() for p in (build / "atmos").rglob("*") if p.is_file()}
    rep = PL.build_plan(build)
    assert rep["wrote"] == []
    assert {p: p.read_bytes() for p in (build / "atmos").rglob("*") if p.is_file()} == snap


def test_sign_faces_and_lamp_heads():
    head = EM.lamp_head("street_light", [0.0, 0.0, 0.0], 90.0, [1.0, 1.0, 2.0])
    assert [round(v, 6) for v in head] == [0.0, 1.5, 15.1]
    f = EM.sign_face({"kind": "billboard", "mount": "facade", "position": [0, 0, 10],
                      "yaw_deg": 0.0, "width_m": 4.0, "height_m": 2.0})
    assert len(f) == 1 and f[0]["c"] == [0.3, 0.0, 10] and f[0]["size"] == [4.0, 2.0]


def test_tiles_are_citygens():
    from citygen.blockout import tile_key, tile_name
    for x, y in ((0.0, 0.0), (-0.01, 255.99), (-1750.0, 1749.0), (512.0, -256.0)):
        assert PL.tile_of(x, y) == tile_name(*tile_key(x, y))
