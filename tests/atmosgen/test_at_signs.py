"""AT2: neon and signs as light (docs/atmosgen_scope.md 6.1, 13): lit faces stood off their
walls, neon spill, crown floods in the colour of AG15's crown LEDs, aviation lights, searchlights,
a port's and a spaceport's lights, flicker and broken lights by the mood, district palettes and
the emitter ask of a sign's face and colour, on a small synthetic build."""

import json
import math

import numpy as np
import pytest

from atmosgen import emitters as EM
from atmosgen import lux as LX
from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P
from atmosgen import spec as S


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _mass(x0, y0, x1, y1, z0, z1, role="body"):
    return {"footprint": _sq(x0, y0, x1, y1), "z0_m": z0, "z1_m": z1, "role": role,
            "shape": "prism"}


def _model() -> dict:
    tower = {"id": "d01.lot.e0n0.bld", "type": "building.tower", "district_id": "d01",
             "use": "office", "height_m": 130.0, "footprint": _sq(-20, -20, 20, 20),
             "form": {"kind": "box", "tower": True, "crown": "mast"},
             "masses": [_mass(-20, -20, 20, 20, 0.0, 12.0, "podium"),
                        _mass(-12, -12, 12, 12, 12.0, 120.0, "body"),
                        _mass(-1, -1, 1, 1, 120.0, 130.0, "mast")]}
    lm = {"id": "d01.lm.e200n0.bld", "type": "building.landmark.spire", "district_id": "d01",
          "name": "Test Spire", "landmark": True, "use": "office", "height_m": 200.0,
          "attrs": {"landmark_kind": "spire"}, "footprint": _sq(180, -20, 220, 20),
          "form": {"kind": "spire", "tower": True},
          "masses": [_mass(180, -20, 220, 20, 0.0, 200.0, "body")]}
    low = {"id": "d02.lot.e300n0.bld", "type": "building.shophouse", "district_id": "d02",
           "use": "retail", "height_m": 12.0, "footprint": _sq(290, -10, 310, 10),
           "masses": [_mass(290, -10, 310, 10, 0.0, 12.0)]}
    vacant = {"id": "d02.lot.e400n0.bld", "type": "building.tower", "district_id": "d02",
              "use": "office", "height_m": 90.0, "footprint": _sq(390, -10, 410, 10),
              "form": {"kind": "box", "tower": True},
              "masses": [_mass(390, -10, 410, 10, 0.0, 90.0)]}
    ctl = {"id": "d03.ms.port.bld.w0", "type": "building.control_tower", "district_id": "d03",
           "megasite_id": "d03.ms.port", "use": "transport", "height_m": 45.0,
           "footprint": _sq(-610, -10, -598, 2),
           "masses": [_mass(-610, -10, -598, 2, 0.0, 38.0, "shaft"),
                      _mass(-612, -12, -596, 4, 38.0, 45.0, "cab")]}
    pad = {"exterior": [[-700 + 20 * math.cos(a), 100 + 20 * math.sin(a)]
                        for a in [2 * math.pi * k / 24 for k in range(24)]], "holes": []}
    els = [
        {"id": "d03.ms.port.el.apron", "kind": "apron", "megasite_id": "d03.ms.port",
         "footprint": _sq(-760, 60, -640, 140), "masses": [], "z_m": 0.0},
        {"id": "d03.ms.port.el.pad", "kind": "launch_pad", "megasite_id": "d03.ms.port",
         "footprint": pad, "attrs": {"radius_m": 20.0},
         "masses": [{"footprint": pad, "z0_m": 0.0, "z1_m": 1.2, "role": "pad",
                     "shape": "cylinder"}], "z_m": 0.0},
        {"id": "d03.ms.port.el.tower", "kind": "launch_tower", "megasite_id": "d03.ms.port",
         "footprint": _sq(-735, 96, -727, 104),
         "masses": [_mass(-735, 96, -727, 104, 0.0, 55.0, "tower")], "z_m": 0.0},
        {"id": "d04.ms.yard.el.crane", "kind": "gantry_crane", "megasite_id": "d04.ms.yard",
         "footprint": _sq(-209, -390, -191, -372),
         "masses": [_mass(-209, -390, -207, -388, 0.0, 42.0, "leg"),
                    _mass(-209, -420, -191, -361, 42.0, 48.0, "boom")], "z_m": 0.0},
        {"id": "d04.ms.yard.el.stack", "kind": "container_stack", "megasite_id": "d04.ms.yard",
         "footprint": _sq(-260, -500, -220, -488),
         "masses": [_mass(-260, -500, -220, -488, 0.0, 10.4, "stack")], "z_m": 0.0},
    ]
    return {
        "name": "Neon Test", "bounds": [-900.0, -700.0, 600.0, 300.0],
        "districts": [
            {"id": "d01", "name": "Core", "archetype": "corporate_core",
             "params": {"wealth": 0.9, "danger": 0.1}, "polygon": _sq(-100, -100, 250, 100)},
            {"id": "d02", "name": "Strand", "archetype": "entertainment_market",
             "params": {"wealth": 0.3, "danger": 0.9}, "polygon": _sq(250, -100, 600, 100)},
            {"id": "d03", "name": "Launch", "archetype": "spaceport",
             "params": {"wealth": 0.5, "danger": 0.3}, "polygon": _sq(-900, -100, -500, 300)},
            {"id": "d04", "name": "Docks", "archetype": "industrial_port",
             "params": {"wealth": 0.3, "danger": 0.6}, "polygon": _sq(-500, -700, 0, -300)}],
        "megasites": [
            {"id": "d03.ms.port", "kind": "spaceport", "district_id": "d03",
             "polygon": _sq(-800, 20, -580, 200)},
            {"id": "d04.ms.yard", "kind": "freight_terminal", "district_id": "d04",
             "polygon": _sq(-480, -680, -20, -320)}],
        "site_elements": els,
        "road_segments": [],
        "props": [],
        "sign_slots": [
            {"id": "d02.lot.e300n0.bld.slot.billboard.e300n10.z8", "kind": "billboard",
             "mount": "facade", "building_id": "d02.lot.e300n0.bld",
             "position": [300.0, 10.0, 8.0], "yaw_deg": 90.0, "width_m": 8.0,
             "height_m": 4.0, "emitter": True, "two_sided": False},
            {"id": "d02.lot.e300n0.bld.slot.banner.e290n5.z6", "kind": "banner",
             "mount": "facade", "building_id": "d02.lot.e300n0.bld",
             "position": [290.0, 5.0, 6.0], "yaw_deg": 180.0, "width_m": 2.0,
             "height_m": 8.0, "emitter": True, "two_sided": False},
            {"id": "d02.lot.e300n0.bld.slot.neon", "kind": "neon", "mount": "facade",
             "building_id": "d02.lot.e300n0.bld", "position": [305.0, 10.0, 4.5],
             "yaw_deg": 90.0, "width_m": 1.2, "height_m": 3.0, "emitter": True,
             "two_sided": False},
            {"id": "city.prop.sign.e295n10.slot", "kind": "shop_sign", "mount": "facade",
             "building_id": "d02.lot.e300n0.bld", "position": [295.0, 10.0, 3.6],
             "yaw_deg": 90.0, "width_m": 2.0, "height_m": 0.6, "emitter": True,
             "two_sided": False}],
        "buildings": [tower, lm, low, vacant, ctl],
    }


def _assets(b):
    """AG15's night (crown LEDs and their accent, a vacant tower) and a sign page."""
    from PIL import Image
    a = b / "assets"
    a.mkdir()
    man = {"buildings": {
        "d01.lot.e0n0.bld": {"genes": {"accent": "b967ff", "crown_light": "band"},
                             "ag15": {"night": {"schedule": "office"}, "tower": True}},
        "d02.lot.e400n0.bld": {"genes": {"accent": "ff2a6d", "crown_light": "edges"},
                               "ag15": {"night": {"schedule": "vacant"}, "tower": True}}}}
    (a / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (a / "textures").mkdir()
    img = Image.new("RGB", (64, 32), (0, 0, 0))
    for x in range(0, 32):                       # the left cell: a bright cyan ad
        for y in range(32):
            img.putpixel((x, y), (20, 200, 230))
    for x in range(40, 44):                      # the right: a thin magenta line on black
        for y in range(32):
            img.putpixel((x, y), (255, 40, 110))
    img.save(a / "textures" / "ads_0.png")
    signs = {"files": {"ads_0": {"file": "textures/ads_0.png"}},
             "cells": {"ad:0": {"page": "ads_0", "uv": [0.0, 0.0, 0.5, 1.0]},
                       "ad:1": {"page": "ads_0", "uv": [0.5, 0.0, 1.0, 1.0]},
                       "shop:0": {"color": "#39ff8a"}},
             "slots": {"d02.lot.e300n0.bld.slot.billboard.e300n10.z8": "ad:0",
                       "d02.lot.e300n0.bld.slot.banner.e290n5.z6": "ad:1",
                       "city.prop.sign.e295n10.slot": "shop:0"}}
    (a / "signs.json").write_text(json.dumps(signs), encoding="utf-8")


@pytest.fixture
def build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    _assets(b)
    return b


@pytest.fixture
def plan(build):
    rep = PL.build_plan(build)
    od = build / "atmos"
    lights = {}
    for t in json.loads((od / "atmos_plan.json").read_text())["tiles"]:
        for L in json.loads((od / t["file"]).read_text())["lights"]:
            PM.Light.model_validate(L)
            lights[L["id"]] = L
    return rep, lights


def test_lit_faces_stand_off_their_walls(plan):
    """A billboard and a banner light what they face from a rect the size of their face,
    stood off it so their own wall stays dark, in their page's colour, with no highlight."""
    rep, L = plan
    bb = L["d02.lot.e300n0.bld.slot.billboard.e300n10.z8.light"]
    ph = P.PHOTOMETRY["sign_face"]
    assert bb["shape"] == "rect" and bb["size"] == [8.0, 4.0] and bb["specular"] == 0.0
    assert math.isclose(bb["pos"][1], 10.0 + EM.FRAME_M["billboard"] + ph["out_m"])
    # (the cyan ad: its colour, its light brighter than a typical page's, within the scale)
    assert bb["color"][2] == 1.0 and bb["color"][0] < 0.1
    assert bb["cd"] > ph["nits"] * ph["light"] * 32.0
    bn = L["d02.lot.e300n0.bld.slot.banner.e290n5.z6.light"]
    # (the thin magenta line on black: magenta, and dimmer than a typical page)
    assert bn["color"][0] == 1.0 and bn["color"][1] < 0.2
    phb = P.PHOTOMETRY["banner_face"]
    assert bn["cd"] < phb["nits"] * phb["light"] * 16.0
    # the faces check: nothing on their own walls, the report says so
    f = rep["faces"]
    assert f["ok"] and f["faces"] == 2 and f["own_wall_max_lx"] <= P.FACE_WALL_MAX_LX
    plan_ = json.loads((PL.Path(rep["out"]) / "atmos_plan.json").read_text())
    assert plan_["checks"]["faces"]["ok"] and rep["ok"]


def test_face_check_finds_a_flooded_wall():
    """AT0's band: a rect 0.1 m in front of a face 0.1 m off its wall lights what stands out
    of the wall beside it, grazing; AT2's, 0.95 m out, nothing."""
    L = {"pos": [0.0, 0.2, 5.0], "aim": [90.0, 0.0], "shape": "rect", "cd": 5000.0,
         "barn_deg": 85.0, "reach_m": 20.0, "id": "x.light"}
    bad = LX.face_check([{"light": L, "yaw": 90.0, "size": [4.0, 1.0], "wall": [0, 0, 5.0]}],
                        None)
    assert not bad["ok"] and bad["over"] == 1
    good = LX.face_check([{"light": {**L, "pos": [0.0, 0.95, 5.0]}, "yaw": 90.0,
                           "size": [4.0, 1.0], "wall": [0, 0, 5.0]}], None)
    assert good["ok"]


def test_neon_spill_is_small_and_near(plan):
    _, L = plan
    n = L["d02.lot.e300n0.bld.slot.neon.light"]
    ph = P.PHOTOMETRY["neon_spill"]
    assert n["kind"] == "neon" and n["shape"] == "spot" and n["tier"] == "near"
    assert n["aim"][1] == ph["pitch"] and n["cone"][1] < 90.0 and n["specular"] == 0.0
    assert n["reach_m"] <= 10.0 and n["pos"][1] > 10.0 + 0.4
    s = L["city.prop.sign.e295n10.slot.light"]
    assert s["kind"] == "shop_sign" and s["cls"] == "shop_neon" and s["tier"] == "near"
    assert s["color"] == PL.unit(PL.hex_linear("#39ff8a"))     # (the shop cell's own colour)


def test_crown_floods_match_the_crown_leds(plan):
    """A tower with AG15's crown LEDs is flooded in their accent; a vacant tower is not; a
    landmark is flooded and uplit; floods live in the high tier, outside the building."""
    rep, L = plan
    crown = [v for k, v in L.items() if k.startswith("d01.lot.e0n0.bld.crown")]
    assert len(crown) == 4
    acc = PL.unit(PL.hex_linear("#b967ff"))
    for c in crown:
        assert c["kind"] == "flood" and c["tier"] == "high" and c["color"] == acc
        assert c["aim"][1] > 45.0 and not c["shadow"]
        # (below the crown's lit zone, off the shaft: outside the 24 m box)
        assert c["pos"][2] < 120.0 and max(abs(c["pos"][0]), abs(c["pos"][1])) > 12.0
    assert not any(k.startswith("d02.lot.e400n0.bld.crown") for k in L)
    lm = [k for k in L if k.startswith("d01.lm.e200n0.bld.")]
    assert any(".crown" in k for k in lm) and any(".up" in k for k in lm)
    assert rep["floods"]["matched_leds"] >= 1 and rep["floods"]["vacant"] == 1


def test_aviation_lights_blink_on_tall_things(plan):
    _, L = plan
    t = [v for k, v in L.items() if k.startswith("d01.lot.e0n0.bld.aviation")]
    top = [v for v in t if v.get("anim")]
    # (the mast's tip flashes; the body's corners steady 90 m under the top)
    assert len(top) == 1 and math.isclose(top[0]["pos"][2], 130.3)
    a = top[0]["anim"]
    assert a["mode"] == "blink" and (a["period_s"], a["amount"]) == P.AVIATION_BLINK
    assert top[0]["color"][0] == 1.0 and top[0]["color"][1] < 0.1
    assert all(v["mount"] == "beacon" and v["on"] and not v["flicker"] and v["tier"] == "near"
               for v in t)
    assert any(not v.get("anim") for v in t)
    # a 12 m building none; a 55 m launch tower in a spaceport, and its 45 m control tower
    assert not any(k.startswith("d02.lot.e300n0.bld.aviation") for k in L)
    assert any(k.startswith("d03.ms.port.el.tower.aviation") for k in L)
    assert any(k.startswith("d03.ms.port.bld.w0.aviation") for k in L)


def test_searchlights_sweep(plan):
    _, L = plan
    s = [v for v in L.values() if v["kind"] == "searchlight"]
    # the spire's two (its kind's), the spaceport's two on its control tower; the strand's
    # one tower is vacant
    assert len([v for v in s if v["owner_id"] == "d01.lm.e200n0.bld"]) == \
        P.LANDMARK_SEARCHLIGHTS["spire"]
    assert len([v for v in s if v["owner_id"] == "d03.ms.port.bld.w0"]) == 2
    for v in s:
        lo, hi = P.SEARCHLIGHT_PITCH
        assert lo <= v["aim"][1] <= hi and v["anim"]["mode"] == "sweep" and v["tier"] == "high"


def test_megasite_lights(plan):
    rep, L = plan
    masts = [v for v in L.values() if v["kind"] == "high_mast"]
    yard = [v for v in masts if v["owner_id"] == "d04.ms.yard"]
    assert yard and all(v["tier"] == "high" and v["mount"] == "mast" for v in yard)
    # (sodium in the port; none on its stack)
    assert all(v["temp_k"] == P.TEMPS["sodium"] for v in yard)
    assert not any(-260 - 3 < v["pos"][0] < -220 + 3 and -500 - 3 < v["pos"][1] < -488 + 3
                   for v in yard)
    assert len([k for k in L if k.startswith("d04.ms.yard.el.crane.boom")]) == 2
    edge = [v for k, v in L.items() if k.startswith("d03.ms.port.el.apron.edge")]
    rim = [v for k, v in L.items() if k.startswith("d03.ms.port.el.pad.rim")]
    assert edge and rim and all(v["kind"] == "runway" and v["mount"] == "ground"
                                for v in edge + rim)
    assert {tuple(v["color"]) for v in rim} == {tuple(PL.unit(PL.hex_linear(c)))
                                                for c in ("#39ff8a", "#f2f6ff")}
    assert "d03.ms.port.el.pad.flood" in L
    assert any(v["owner_id"] == "d03.ms.port.el.apron" and v["kind"] == "high_mast"
               for v in L.values())
    assert rep["megasites"]["runway"] == len(edge) + len(rim)


def test_palettes_and_grit_by_place():
    """Decision 12.5: the core's palette cool, the strand's hot; a gritty district's lamps of
    mixed temperatures and uneven, a clean one's uniform; a dying sign flickers, never dark."""
    core = S.mood("corporate_core", 0.9, 0.1)
    strand = S.mood("entertainment_market", 0.3, 0.9)
    assert core["palette"] == list(P.PALETTES["corporate_core"])
    assert "#ff2a6d" in strand["palette"] and "#ff2a6d" not in core["palette"]
    assert core["floods"] > strand["floods"] and strand["searchlights"] > 0
    # a city palette in the spec for districts without their own
    spec = S.validate_spec({"palette": {"neon": {"#ff0000": 2.0, "#00ff00": 1.0}}}).spec
    f = S.fill(spec, [{"id": "d01", "archetype": "old_town"}])
    assert f["moods"]["d01"]["palette"] == ["#ff0000", "#00ff00"]


def test_flicker_and_dying_signs_by_danger(build):
    m = json.loads((build / "city_model.json").read_text())
    # many shop signs in the dangerous strand and in the clean core
    for d, x0 in (("d02", 300.0), ("d01", 0.0)):
        for k in range(300):
            m["sign_slots"].append(
                {"id": f"city.prop.sign.{d}k{k}.slot", "kind": "shop_sign", "mount": "facade",
                 "building_id": "d02.lot.e300n0.bld" if d == "d02" else "d01.lot.e0n0.bld",
                 "position": [x0 + (k % 30) * 0.5, 30.0 + k // 30, 3.5], "yaw_deg": 90.0,
                 "width_m": 1.0, "height_m": 0.5, "emitter": True, "two_sided": False})
    (build / "city_model.json").write_text(json.dumps(m))
    PL.build_plan(build)
    od = build / "atmos"
    lights = [L for t in json.loads((od / "atmos_plan.json").read_text())["tiles"]
              for L in json.loads((od / t["file"]).read_text())["lights"]]
    strand = [L for L in lights if L["id"].startswith("city.prop.sign.d02")]
    core = [L for L in lights if L["id"].startswith("city.prop.sign.d01")]
    assert all(L["on"] for L in strand + core)          # (a sign's light never dark)
    fs = np.mean([L["flicker"] > 0 for L in strand])
    # (dlss_lamps_flicker: ten times fewer than AT2's 0.2 and more: `presets.FLICKER_SCALE`)
    assert 0.01 < fs < 0.12 and not any(L["flicker"] for L in core)
    assert any(L["flicker"] >= P.DYING_DEPTH[0] for L in strand)
    # the mood's share is the archetype's times the scale, pulled up by danger
    hi, lo = S.mood("entertainment_market", 0.3, 0.9), S.mood("entertainment_market", 0.3, 0.1)
    assert math.isclose(hi["flicker"], round(0.25 * P.FLICKER_SCALE * 1.4, 4))
    assert hi["flicker"] > lo["flicker"] > 0.0


def test_assetgen_face_and_emit_are_used(build):
    """The second ask met: a slot record with its drawn face and its cell's `emit`."""
    a = build / "assets" / "signs.json"
    sj = json.loads(a.read_text())
    sid = "d02.lot.e300n0.bld.slot.billboard.e300n10.z8"
    sj["slots"][sid] = {"cell": "ad:9", "face": {"c": [300.0, 10.5, 8.0], "n": [0.0, 1.0, 0.0],
                                                 "size": [7.5, 3.5], "two_sided": False}}
    sj["cells"]["ad:9"] = {"emit": {"color": "#ff0000", "nits": 500.0}}
    a.write_text(json.dumps(sj))
    PL.build_plan(build)
    od = build / "atmos"
    plan = json.loads((od / "atmos_plan.json").read_text())
    lights = {L["id"]: L for t in plan["tiles"]
              for L in json.loads((od / t["file"]).read_text())["lights"]}
    bb = lights[sid + ".light"]
    ph = P.PHOTOMETRY["sign_face"]
    assert bb["source"] == "assetgen" and bb["size"] == [7.5, 3.5]
    assert math.isclose(bb["pos"][1], 10.5 + ph["out_m"]) and bb["color"] == [1.0, 0.0, 0.0]
    assert math.isclose(bb["cd"], 500.0 * ph["light"] * 7.5 * 3.5, rel_tol=1e-3)
    assert plan["sources"]["assetgen"] == 1


def test_high_tier_in_the_plan(plan):
    rep, L = plan
    assert rep["tiers"]["high"] == sum(1 for v in L.values() if v["tier"] == "high")
    assert all(v["kind"] in P.HIGH_KINDS for v in L.values() if v["tier"] == "high")
    assert rep["code"] == PL.code_hash() and rep["code"].startswith("at7.")
