"""AT1: the Unreal exporter's layer 3 (citygen/unreal_atmos.py): an atmos plan into the
controller's settings and a data actor of packed lights per 128 m cell, keyed and hashed for
incremental imports; a plan whose lux check failed is not delivered. The Unreal side runs in
`citygen unreal --check` (the Delta check of docs/progress/AT1)."""

import json
import math

import pytest

from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P
from citygen import unreal_atmos as UA


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _model():
    """Two street lights 200 m apart (two cells), a shopfront, a sidewalk past them."""
    return {
        "name": "Atmos Export", "bounds": [-50.0, -50.0, 350.0, 50.0],
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


@pytest.fixture
def build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    rep = PL.build_plan(b)
    assert rep["ok"], rep["lux"]["failures"]
    return b


def test_cells_pack_every_light(build):
    at = UA.write_atmos(build)
    data = json.loads((build / "unreal" / UA.DATA).read_text())
    plan = json.loads((build / "atmos" / "atmos_plan.json").read_text())
    assert at["lights"] == plan["counts"]["all"] == sum(c["count"] for c in data["cells"])
    assert {c["key"] for c in at["cells"]} == {c["key"] for c in data["cells"]}
    for c in data["cells"]:
        assert len(c["floats"]) == c["count"] * UA.FLOATS
        assert len(c["ints"]) == c["count"] * UA.INTS
        # every light inside its 128 m cell, the cell named by its tile and quarter
        ix, iy = (math.floor(v / UA.CELL_M) for v in c["center"][:2])
        assert c["key"] == f"atmos.lights.{c['cell']}" and c["cell"].startswith(c["tile"])
        for k in range(c["count"]):
            x, y = c["floats"][k * UA.FLOATS] / 100.0, -c["floats"][k * UA.FLOATS + 1] / 100.0
            assert UA.cell_of(x, y) == (ix, iy)
    ctl = data["controller"]
    assert len(ctl["schedule_hours"]) == 24 * len(ctl["schedule_names"])
    assert ctl["schedule_names"] == sorted(plan["schedules"])
    assert ctl["max_live"] == plan["tiers"]["mid_max"] and ctl["cell_m"] == UA.CELL_M
    # AT2: the high tier's pool and range
    assert ctl["max_high"] == plan["tiers"]["high_max"] and \
        ctl["high_range_m"] == plan["tiers"]["high_m"]


def test_pack_frames_and_flags():
    L = {"pos": [10.0, 20.0, 7.0], "aim": [90.0, -75.0], "shape": "spot", "cd": 1200.0,
         "cone": [62.0, 80.0], "color": [1.0, 0.5, 0.25], "reach_m": 40.0, "source_m": 0.25,
         "shadow": True, "tier": "mid", "on": True, "schedule": "dusk_dawn",
         "kind": "street_light", "mount": "prop", "flicker": 0.4, "hash": "ffffffff00000000"}
    kinds, mounts = UA._kinds(), UA._mounts()
    f, i = UA.pack(L, ["always", "dusk_dawn"], kinds, mounts)
    # Unreal's frame: cm, Y south, the heading turned
    assert f[:5] == [1000.0, -2000.0, 700.0, -75.0, -90.0] and f[8] == 1200.0
    assert f[12] == 4000.0 and f[13:15] == [62.0, 80.0] and f[15] == 0.4
    flags, seed = i
    assert flags & 3 == 0 and flags & 4 and not flags & 8 and flags & 16
    assert (flags >> 8) & 0xff == 1 and (flags >> 16) & 0xff == kinds.index("street_light")
    assert (flags >> 24) & 0xf == mounts.index("prop") and seed == -1
    # a rect: its intensity in nits (candela over its area), its barn doors in the inner slot
    R = {**L, "shape": "rect", "size": [2.0, 0.5], "cd": 100.0, "barn_deg": 70.0,
         "kind": "spill", "mount": "facade"}
    f, i = UA.pack(R, ["always", "dusk_dawn"], kinds, mounts)
    assert f[8] == 100.0 and f[13] == 70.0 and f[5:7] == [200.0, 50.0] and i[0] & 3 == 2
    assert not flags & 32 and not i[0] & 32
    # a lit face's stand-in casts no specular highlight (bit 5)
    _, i = UA.pack({**R, "specular": 0.0}, ["always", "dusk_dawn"], kinds, mounts)
    assert i[0] & 32
    # AT2: a light without an animation packs zeros for it, and is not in the high tier
    assert f[16:19] == [0.0, 0.0, 0.0] and not i[0] & 64 and (i[0] >> 28) & 3 == 0
    # a blinking aviation light and a sweeping searchlight in the high tier
    B = {**L, "shape": "point", "kind": "aviation", "mount": "beacon",
         "anim": {"mode": "blink", "period_s": 2.0, "amount": 0.3, "phase": 0.25}}
    f, i = UA.pack(B, ["always", "dusk_dawn"], kinds, mounts)
    assert f[16:19] == [2.0, 0.3, 0.25] and (i[0] >> 28) & 3 == 1 and not i[0] & 64
    assert (i[0] >> 24) & 0xf == mounts.index("beacon")
    W = {**L, "kind": "searchlight", "tier": "high", "mount": "roof",
         "anim": {"mode": "sweep", "period_s": 20.0, "amount": 30.0, "phase": 0.5}}
    f, i = UA.pack(W, ["always", "dusk_dawn"], kinds, mounts)
    assert f[16:19] == [20.0, 30.0, 0.5] and (i[0] >> 28) & 3 == 2 and i[0] & 64
    assert len(f) == UA.FLOATS and i[0] > 0


def test_hashes_follow_the_lights(build, tmp_path):
    at = UA.write_atmos(build)
    h = UA.actor_hashes(at)
    assert set(h) == {"atmos"} | {c["key"] for c in at["cells"]}
    assert UA.write_atmos(build) == at                     # (the same plan: the same)
    # a light moved in one cell changes that cell's hash alone, and the controller's not
    d = build / "atmos" / "lights"
    f = sorted(d.glob("t*.json"))[0]
    doc = json.loads(f.read_text())
    doc["lights"][0]["hash"] = "0123456789abcdef"
    f.write_text(json.dumps(doc))
    h2 = UA.actor_hashes(UA.write_atmos(build))
    changed = sorted(k for k in h if h[k] != h2[k])
    assert len(changed) == 1 and changed[0].startswith("atmos.lights.")


def test_cells_pack_volumes_and_emitters(build):
    """AT4: a cell holds the fog volumes whose middle and the plumes whose foot lie in it (a
    cell made where only they lie), packed in Unreal's frame; the controller has the air."""
    p = build / "atmos" / "atmos_plan.json"
    plan = json.loads(p.read_text())
    assert plan["air"]["cvars"] and plan["air"]["scatter"]["shop_sign"] == 0.0
    plan["volumes"] = [{"id": "ww.mist000", "owner_id": "ww", "kind": "mist", "tile": "t+00+00",
                        "center": [600.0, 10.0, -1.5], "extent": [60.0, 10.0, 7.0],
                        "yaw_deg": 90.0, "density": 0.02, "floor": 0.7, "phase_g": 0.45,
                        "albedo": [0.4, 0.45, 0.5], "schedule": "mist", "hash": "a" * 16}]
    plan["emitters"] = [{"id": "rs.manhole00", "owner_id": "rs", "kind": "steam",
                         "mount": "manhole", "tile": "t+00+00", "pos": [20.0, -1.0, 0.05],
                         "width_m": 0.8, "rise_m": 4.5, "rate": 0.9, "color": [0.7, 0.7, 0.7],
                         "schedule": "steam", "source": "assetgen", "hash": "b" * 16}]
    p.write_text(json.dumps(plan))
    at = UA.write_atmos(build)
    data = json.loads((build / "unreal" / UA.DATA).read_text())
    assert at["volumes"] == 1 and at["emitters"] == 1
    cells = {c["cell"]: c for c in data["cells"]}
    vc = cells[UA.cell_name(*UA.cell_of(600.0, 10.0))[1]]
    assert vc["count"] == 0 and vc["volumes"] == 1                  # (a cell of its own)
    f, i = vc["volume_floats"], vc["volume_ints"]
    assert len(f) == UA.VFLOATS and len(i) == UA.VINTS
    assert f[:4] == [60000.0, -1000.0, -150.0, -90.0] and f[4:7] == [6000.0, 1000.0, 700.0]
    sched = sorted(plan["schedules"])
    assert i[0] & 0xff == sched.index("mist") and i[0] >> 8 == UA.VOLUME_KINDS.index("mist")
    ec = cells[UA.cell_name(*UA.cell_of(20.0, -1.0))[1]]
    assert ec["emitters"] == 1 and ec["count"] > 0
    f, i = ec["emitter_floats"], ec["emitter_ints"]
    assert f[:5] == [2000.0, 100.0, 5.0, 80.0, 450.0] and len(f) == UA.EFLOATS
    assert (i[0] >> 8) & 0xff == UA.EMITTER_KINDS.index("steam")
    assert (i[0] >> 16) & 0xff == UA.EMITTER_MOUNTS.index("manhole") and len(i) == UA.EINTS
    ctl = data["controller"]
    assert ctl["air"] and len(ctl["fog_hours"]) == 24
    assert len(ctl["kind_scatter"]) == len(ctl["kind_names"])
    assert ctl["kind_scatter"][ctl["kind_names"].index("spill")] == 0.0
    assert ctl["puffs"] == [P.PUFFS[k] for k in UA.EMITTER_KINDS]
    assert all("=" in c for c in ctl["cvars"])
    # the kinds the exporter indexes are the plan's
    from typing import get_args
    assert UA.VOLUME_KINDS == get_args(PM.FogVolume.model_fields["kind"].annotation)
    assert UA.EMITTER_KINDS == get_args(PM.Emitter.model_fields["kind"].annotation)
    assert UA.EMITTER_MOUNTS == get_args(PM.Emitter.model_fields["mount"].annotation)
    # a plan whose air check failed is not delivered
    plan["checks"]["air"] = {"ok": False}
    p.write_text(json.dumps(plan))
    assert "air" in UA.write_atmos(build)["skipped"]


def test_sight_rides_on_the_controller(build):
    """Visible lights: the plan's sight raster on the controller as runs over its rows from
    the north edge, its bounds in Unreal's frame (Y south), the tiers' range and size; part
    of the controller's hash, not the cells'."""
    from atmosgen import sight as SI
    at = UA.write_atmos(build)
    ctl = json.loads((build / "unreal" / UA.DATA).read_text())["controller"]
    plan = json.loads((build / "atmos" / "atmos_plan.json").read_text())
    s = plan["sight"]
    w, h = ctl["sight_px"]
    assert [w, h] == s["px"] and sum(ctl["sight_runs"][0::2]) == w * h
    x0, y0, x1, y1 = s["bounds"]
    assert ctl["sight_bounds"] == [x0 * 100.0, -y1 * 100.0, x1 * 100.0, -y0 * 100.0]
    assert ctl["sight_m"] == P.TIERS["sight"]["radius_m"] == 4 * P.TIERS["mid"]["radius_m"]
    assert ctl["sight_max"] == plan["tiers"]["sight_max"] and ctl["sight_cell_m"] == SI.CELL_M
    assert at["sight"]["runs"] == len(ctl["sight_runs"]) // 2
    # the raster's runs are its cells; the shopfront's building stands in some
    rgb = SI.load(build / "atmos" / SI.FILE, s)["rgb"]
    assert ctl["sight_runs"] == SI.runs(rgb) and rgb[..., 0].max() > 0
    # a plan before the sight raster delivers none, its cells as they were
    cells = {c["key"]: c["hash"] for c in at["cells"]}
    del plan["sight"]
    (build / "atmos" / "atmos_plan.json").write_text(json.dumps(plan))
    at2 = UA.write_atmos(build)
    assert at2["sight"] is None and at2["hash"] != at["hash"]
    assert {c["key"]: c["hash"] for c in at2["cells"]} == cells


def test_a_failed_check_is_not_delivered(build):
    p = build / "atmos" / "atmos_plan.json"
    plan = json.loads(p.read_text())
    plan["checks"]["lux"]["ok"] = False
    p.write_text(json.dumps(plan))
    at = UA.write_atmos(build)
    assert at.get("skipped") and not at.get("cells") and UA.actor_hashes(at) == {}
    # AT2: a plan whose faces check failed neither
    plan["checks"]["lux"]["ok"] = True
    plan["checks"]["faces"] = {"ok": False}
    p.write_text(json.dumps(plan))
    assert "faces" in UA.write_atmos(build)["skipped"]
    # an AT0 plan (no check) neither
    del plan["checks"]
    p.write_text(json.dumps(plan))
    assert "AT0" in UA.write_atmos(build)["skipped"]
    assert UA.write_atmos(build.parent / "nowhere") is None
    # a folder named for the plan that holds none is an error, not a city without one
    with pytest.raises(FileNotFoundError):
        UA.write_atmos(build, build.parent / "nowhere")


def test_weather_rides_on_the_controller(build):
    """AT5: the controller has the weather (its states' values in WEATHER_KEYS order, the start
    state, the rain's age, the wind, the cover's datum and step), the masks stitched city-wide
    into two textures beside the manifest (a power of two a side, row 0 the north edge), a
    cell its drip lines; a plan whose weather check failed is not delivered."""
    from PIL import Image
    at = UA.write_atmos(build)
    data = json.loads((build / "unreal" / UA.DATA).read_text())
    plan = json.loads((build / "atmos" / "atmos_plan.json").read_text())
    ctl = data["controller"]
    wp = plan["weather_plan"]
    assert ctl["weather"] and ctl["weather_names"] == list(wp["states"])
    assert len(ctl["weather_values"]) == len(UA.WEATHER_KEYS) * len(ctl["weather_names"])
    k = ctl["weather_names"].index("rain")
    row = ctl["weather_values"][k * len(UA.WEATHER_KEYS):(k + 1) * len(UA.WEATHER_KEYS)]
    assert row[UA.WEATHER_KEYS.index("rain")] == wp["states"]["rain"]["rain"]
    assert row[UA.WEATHER_KEYS.index("fog_albedo_b")] == wp["states"]["rain"]["fog_albedo"][2]
    assert ctl["weather_start"] == "rain" and ctl["cover_step_cm"] == wp["cover"]["step_m"] * 100
    # the textures: 1 m texels over the masks' extent, padded to a power of two
    w = at["weather"]["wet"]
    with Image.open(build / w["cover"]["file"]) as im:
        assert im.mode == "L" and im.size == (w["px"], w["px"])
    with Image.open(build / w["surface"]["file"]) as im:
        assert im.mode == "RGB"
    x0, y0, x1, y1 = wp["extent"]
    assert w["px"] >= (x1 - x0) / UA.WET_TEXEL_M and w["px"] & (w["px"] - 1) == 0
    assert w["bounds"][0] == x0 * 100.0 and w["bounds"][2] == w["px"] * UA.WET_TEXEL_M * 100.0
    # a drip line in a cell of its own: packed, the cell made, its hash following it
    D = {"id": "d01.prop.awning.e200n20.drip00", "owner_id": "d01.prop.awning.e200n20",
         "kind": "awning", "tile": "t+00+00", "a": [200.0, 20.0], "b": [206.0, 20.0],
         "z_m": 3.2, "ground_m": 0.0, "rate": 0.75, "hash": "00112233aabbccdd"}
    f = UA.pack_drip(D)
    assert f == [20000.0, -2000.0, 20600.0, -2000.0, 320.0, 0.0, 0.75]
    (build / "atmos" / "drips").mkdir(exist_ok=True)
    (build / "atmos" / "drips" / "t+00+00.json").write_text(json.dumps(
        {"version": 1, "city": plan["city"], "tile": "t+00+00", "drips": [D]}))
    plan["weather_plan"]["drip_tiles"] = [{"tile": "t+00+00", "file": "drips/t+00+00.json",
                                           "count": 1, "kinds": {"awning": 1}, "sha256": "x"}]
    (build / "atmos" / "atmos_plan.json").write_text(json.dumps(plan))
    at2 = UA.write_atmos(build)
    data2 = json.loads((build / "unreal" / UA.DATA).read_text())
    cell = next(c for c in data2["cells"] if c.get("drips"))
    assert cell["drip_floats"] == f and at2["weather"]["drips"] == 1
    assert UA.actor_hashes(at2)[cell["key"]] != UA.actor_hashes(at).get(cell["key"])
    # a failed weather check: not delivered
    plan["checks"]["weather"]["ok"] = False
    (build / "atmos" / "atmos_plan.json").write_text(json.dumps(plan))
    assert "weather" in UA.write_atmos(build)["skipped"]


def test_far_cards_ride_in_the_cells(build):
    """AT7: every far card packed into the cell its middle lies in (its color times its value,
    Unreal's frame, its flags), the controller's far settings, the manifest's count; a cell
    of far cards alone is made; a failed far check is not delivered."""
    at = UA.write_atmos(build)
    data = json.loads((build / "unreal" / UA.DATA).read_text())
    plan = json.loads((build / "atmos" / "atmos_plan.json").read_text())
    n = plan["far"]["counts"]["all"]
    assert n > 0 and at["far"]["cards"] == n == sum(c.get("far", 0) for c in data["cells"])
    ctl = data["controller"]
    assert ctl["far"] and ctl["far_gain"] == P.FAR_GAIN and ctl["far_px"] == P.FAR_PX
    for c in data["cells"]:
        if c.get("far"):
            assert len(c["far_floats"]) == UA.FFLOATS * c["far"] == \
                UA.FFLOATS * len(c["far_ints"])
    sch = sorted(plan["schedules"])
    C = {"id": "x.far.wash", "type": "wash", "tier": "high", "pos": [300.0, 400.0, 90.0],
         "color": [1.0, 0.5, 0.25], "value": 8.0, "size_m": 12.0, "h_m": 9.0, "yaw": 90.0,
         "schedule": "late", "hash": "aa"}
    f, i = UA.pack_far(C, sch)
    assert f == [30000.0, -40000.0, 9000.0, 8.0, 4.0, 2.0, 1200.0, 900.0, -90.0, 0.0, 1.0, 0.0]
    assert i == 2 | (1 << 2) | (sch.index("late") << 8)
    G = dict(C, type="glow", tier="fixture", yaw=None, h_m=0.0,
             anim={"mode": "blink", "period_s": 1.5, "amount": 0.3, "phase": 0.25})
    f, i = UA.pack_far(G, sch)
    assert f[9:] == [1.5, 0.3, 0.25] and i & 3 == 0 and (i >> 2) & 3 == 2 and i & 16
    # a cell of far cards alone
    far = plan["far"]
    (build / "atmos" / "far").mkdir(exist_ok=True)
    (build / "atmos" / "far" / "t+01+01.json").write_text(json.dumps(
        {"version": 1, "city": plan["city"], "tile": "t+01+01", "bounds": [256, 256, 512, 512],
         "cards": [C]}))
    far["tiles"].append({"tile": "t+01+01", "file": "far/t+01+01.json", "count": 1,
                         "sha256": "x"})
    (build / "atmos" / "atmos_plan.json").write_text(json.dumps(plan))
    at2 = UA.write_atmos(build)
    data2 = json.loads((build / "unreal" / UA.DATA).read_text())
    cell = next(c for c in data2["cells"] if c["cell"] == "t+01+01.nw")
    assert cell["count"] == 0 and cell["far"] == 1 and at2["far"]["cards"] == n + 1
    # a failed far check: not delivered
    plan["checks"]["far"]["ok"] = False
    (build / "atmos" / "atmos_plan.json").write_text(json.dumps(plan))
    assert "far" in UA.write_atmos(build)["skipped"]
