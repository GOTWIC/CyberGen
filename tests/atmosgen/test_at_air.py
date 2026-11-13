"""AT4: the air (atmosgen/air.py, docs/atmosgen_scope.md 6.3): mist over the water, smog over
industry, haze under decks and in tunnels, steam and smoke plumes from their sources (AG7's
manholes and drains read from the street packs), the fog and light shafts' settings, the air
check, and the plan's and the exporter's records of them. The runtime renders them in Unreal
(`citygen unreal --check`'s air, docs/progress/AT4)."""

import json
import math
import struct

import numpy as np
import pytest

from atmosgen import air as AR
from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P
from atmosgen import spec as S


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _model():
    """A gritty industrial port (a canal, a warehouse with a roof unit, a food stall) beside a
    clean corporate core (a deck, a road tunnel)."""
    return {
        "name": "Air Test", "bounds": [0.0, 0.0, 800.0, 400.0],
        "districts": [
            {"id": "d01", "name": "Port", "archetype": "industrial_port",
             "params": {"wealth": 0.2, "danger": 0.9}, "polygon": _sq(0, 0, 400, 400)},
            {"id": "d02", "name": "Core", "archetype": "corporate_core",
             "params": {"wealth": 0.9, "danger": 0.1}, "polygon": _sq(400, 0, 800, 400)}],
        "waterways": [{"id": "d01.ww.e200n190", "kind": "canal", "district_id": "d01",
                       "ornamental": False, "polygon": _sq(50, 180, 350, 200),
                       "centerline": [[50.0, 190.0], [350.0, 190.0]],
                       "bed": {"surface_m": -1.5}}],
        "decks": [{"id": "d02.deck.e575n175", "district_id": "d02", "polygon": _sq(450, 50, 700, 300),
                   "top_m": 9.0, "slab_m": 1.2, "area_m2": 62500.0}],
        "tunnels": [{"id": "tn.e600n350", "kind": "cut_and_cover", "width_m": 20.0,
                     "clear_m": 5.5, "roof_m": 1.0,
                     "line": [[420.0, 350.0, 0.0], [780.0, 350.0, 0.0]],
                     "portals": [{"position": [470.0, 350.0, -6.5], "heading_deg": 0.0,
                                  "open_m": 50.0},
                                 {"position": [730.0, 350.0, -6.5], "heading_deg": 180.0,
                                  "open_m": 50.0}]}],
        "buildings": [{"id": "d01.lot.e130n275.bld", "type": "building.warehouse",
                       "district_id": "d01", "footprint": _sq(100, 250, 160, 300),
                       "masses": [{"footprint": _sq(100, 250, 160, 300), "z0_m": 0.0,
                                   "z1_m": 14.0}],
                       "roof_items": [{"kind": "mechanical", "position": [130.0, 275.0, 14.0],
                                       "size": [4.0, 3.0, 2.0], "yaw_deg": 0.0}]}],
        "road_segments": [{"id": "rs.e100n50", "road_class": "street", "width_m": 12.0,
                           "centerline": [[40.0, 50.0], [250.0, 50.0]]}],
        "props": [{"id": "d01.prop.food_stall.e60n100", "type": "prop.food_stall",
                   "attrs": {}, "position": [60.0, 100.0, 0.0], "yaw_deg": 0.0,
                   "scale": [1.0, 1.0, 1.0]}],
        "structures": [{"id": "tn.e600n350.vent0", "kind": "vent", "footprint": _sq(590, 360, 600, 370),
                        "z0_m": 0.0, "z1_m": 6.0}],
    }


def _glb(path, piece, disks):
    """A street pack (AG7's frame: glTF y up) with one node, its manholes as a primitive of
    12-gons in material `manhole`."""
    pos, idx = [], []
    for cx, cy, z in disks:
        b = len(pos)
        for i in range(12):
            a = 2 * math.pi * i / 12
            x, y = cx + 0.4 * math.cos(a), cy + 0.4 * math.sin(a)
            pos.append((x, z, -y))                     # citygen (x, y, z) -> glTF (x, z, -y)
        idx += [v for i in range(1, 11) for v in (b, b + i, b + i + 1)]
    pb = np.array(pos, dtype=np.float32).tobytes()
    ib = np.array(idx, dtype=np.uint32).tobytes()
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": piece, "mesh": 0}],
           "materials": [{"name": "asphalt.street"}, {"name": "manhole"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1,
                                       "material": 1}]}],
           "buffers": [{"byteLength": len(pb) + len(ib)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pb)},
                           {"buffer": 0, "byteOffset": len(pb), "byteLength": len(ib)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pos),
                          "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5125, "count": len(idx),
                          "type": "SCALAR"}]}
    js = json.dumps(doc).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    binary = pb + ib
    data = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary))
    data += struct.pack("<II", len(js), 0x4E4F534A) + js
    data += struct.pack("<II", len(binary), 0x004E4942) + binary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def city(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    # AG7's manholes on a road of the port (gritty: most of them steam)
    _glb(b / "assets" / "streets" / "t+00+00.glb", "rs.e100n50",
         [(60.0 + 20.0 * k, 50.0, 0.05) for k in range(8)])
    return b


def _air(build):
    c = PL.City(build)
    f = S.fill(S.AtmosSpec(), list(c.districts.values()))
    pl = PL.Plan(c, f)
    a = AR.Air(pl)
    for n in ("mist", "smog", "haze", "tunnel_haze", "street", "vents", "roofs", "stalls",
              "chimneys"):
        getattr(a, n)()
    return a, f


def test_volumes_over_water_industry_decks_and_tunnels(city):
    a, _ = _air(city)
    by = {}
    for v in a.volumes:
        by.setdefault(v["kind"], []).append(v)
    # mist along the canal, as wide as it, on its surface, after dusk
    mist = by["mist"]
    assert len(mist) == round(300 / P.VOLUMES["mist"]["step_m"])
    for v in mist:
        assert 50 <= v["center"][0] <= 350 and v["center"][1] == pytest.approx(190.0, abs=0.01)
        assert v["center"][2] == -1.5 and v["extent"][1] == pytest.approx(0.55 * 20.0, abs=0.01)
        assert v["yaw_deg"] == 0.0 and v["schedule"] == "mist" and v["floor"] > 0.5
    # smog over the port district only, haze under the deck, haze in the tunnel's covered part
    assert by["smog"] and all(v["owner_id"] == "d01" for v in by["smog"])
    assert by["haze"] and all(450 <= v["center"][0] <= 700 for v in by["haze"])
    assert all(v["center"][2] == pytest.approx(0.5 * (9.0 - 1.2)) for v in by["haze"])
    th = by["tunnel_haze"]
    assert th and all(470 <= v["center"][0] <= 730 for v in th)
    # thicker where danger is: the port's mist over the core's haze per its kind's base
    dens = {k: by[k][0]["density"] / P.VOLUMES[k]["density"] for k in ("mist", "haze")}
    assert dens["mist"] > dens["haze"]
    assert len({v["id"] for v in a.volumes}) == len(a.volumes)


def test_emitters_from_their_sources(city):
    a, _ = _air(city)
    by = {}
    for e in a.emitters:
        by.setdefault(e["mount"], []).append(e)
    # AG7's manholes read from the pack: on their disks' middles, at the road
    assert a.report["manholes"] == 8
    for e in by.get("manhole", []):
        assert e["source"] == "assetgen" and e["pos"][1] == pytest.approx(50.0, abs=0.01)
        assert (e["pos"][0] - 60.0) % 20.0 == pytest.approx(0.0, abs=0.01)
    # the port is gritty: most of its manholes steam (share 0.03 + 0.22 at grit 1)
    sk = a.report["skipped"]
    assert len(by.get("manhole", [])) + sk.get("manhole: not steaming (its district's grit)",
                                                0) == 8
    # the food stall cooks, the vent steams, over their sources
    st = by["stall"][0]
    assert st["kind"] == "cooking" and st["pos"][:2] == [60.0, 100.0] and st["schedule"] == "food"
    assert by["vent"][0]["pos"][2] == pytest.approx(6.0)
    # the roof unit's plume leaves its top; the warehouse's chimney stands over its roof
    for e in by.get("roof", []):
        assert e["pos"][2] == pytest.approx(16.0) and e["kind"] == "exhaust"
    for e in by.get("chimney", []):
        assert e["pos"][2] == pytest.approx(14.0 + P.CHIMNEY_M[1]) and e["kind"] == "smoke"
        assert 100 < e["pos"][0] < 160 and 250 < e["pos"][1] < 300
    assert len({e["id"] for e in a.emitters}) == len(a.emitters)


def test_pack_reader_finds_separate_disks(tmp_path):
    p = tmp_path / "t.glb"
    _glb(p, "rs.x", [(1.0, 2.0, 0.1), (5.0, 2.0, 0.1), (5.3, 9.0, 0.2)])
    got = AR.pack_details(p)
    assert len(got) == 1 and got[0][0] == "rs.x" and got[0][1] == "manhole"
    d = AR.disks(got[0][2])
    assert [(round(x, 2), round(y, 2)) for x, y, _ in d] == [(1.0, 2.0), (5.0, 2.0), (5.3, 9.0)]
    assert AR.street_details(tmp_path / "nothing") == {}


def test_only_road_pieces_steam(city):
    """A sidewalk piece's grates are tree pits: only a road segment's manholes and drains
    steam (the pack read whole, the plan keeping the road pieces)."""
    _glb(city / "assets" / "streets" / "t+00+01.glb", "rs.e100n50.swl",
         [(60.0, 300.0, 0.2)])
    assert "rs.e100n50.swl" in AR.street_details(city)
    a, _ = _air(city)
    assert a.report["manholes"] == 8
    assert all(not e["owner_id"].endswith(".swl") for e in a.emitters)


def test_air_check_finds_what_is_misplaced(city):
    a, _ = _air(city)
    assert a.check()["ok"]
    # a manhole's plume moved off its disk, a mist piece moved off the water
    e = next(e for e in a.emitters if e["mount"] == "stall")
    e["pos"] = [e["pos"][0] + 5.0, e["pos"][1], e["pos"][2]]
    v = next(v for v in a.volumes if v["kind"] == "mist")
    v["center"] = [v["center"][0], 50.0, v["center"][2]]
    c = a.check()
    assert not c["ok"] and c["bad_emitters"] == 1 and c["bad_volumes"] == 1
    assert "air check: FAIL" in AR.check_text(c)


def test_settings_shafts_and_fog_by_the_hour(city):
    a, f = _air(city)
    from atmosgen import sky as SK
    sky = SK.make(f, f["sky"])
    s = a.settings(f, sky)
    PM.Air(**s)
    # the small many lights scatter none, the strong ones more, a searchlight none (its beam)
    assert s["scatter"]["shop_sign"] == s["scatter"]["spill"] == s["scatter"]["neon"] == 0.0
    assert s["scatter"]["high_mast"] > s["scatter"]["street_light"] > 0.0
    assert s["scatter"]["searchlight"] == 0.0
    # the fog thicker by night than by day
    assert s["fog_hours"][23] > s["fog_hours"][14]
    assert s["counts"]["volumes"] == len(a.volumes) and s["cvars"] == dict(sorted(P.AIR_CVARS.items()))


def test_plan_records_the_air(city):
    # (the deck's soffit lights need a whole model, AG10's; the air's haze is tested above)
    m = _model()
    del m["decks"]
    (city / "city_model.json").write_text(json.dumps(m), encoding="utf-8")
    rep = PL.build_plan(city)
    plan = json.loads((city / "atmos" / "atmos_plan.json").read_text())
    PM.AtmosPlan.model_validate(plan)
    assert plan["air"]["counts"]["volumes"] == len(plan["volumes"]) > 0
    assert len(plan["emitters"]) == plan["air"]["counts"]["emitters"] > 0
    assert plan["checks"]["air"]["ok"] and rep["air"]["ok"]
    for k in P.AIR_SCHEDULES:
        assert len(plan["schedules"][k]) == 24
    assert "air check: PASS" in (city / "atmos" / "atmos_report.txt").read_text()
    # unchanged: nothing written again
    assert PL.build_plan(city)["wrote"] == []
    # the map of the air
    img = AR.air_map(city)
    assert (city / "atmos" / "preview_air.png").is_file() and img["volumes"]["mist"] > 0
