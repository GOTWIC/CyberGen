"""AG4's roofs and connections on small made-up briefs: every new part closed, named by its
parameters and (roof equipment) untinted and always instanced; roof forms inside the
envelope (a shed's sawtooth, gable and barrel, a villa's pitched roof, a mansard on a ring
that is no rectangle); an asset for every roof item, lowered under a corridor that passes
over it; the clearance check; every skybridge kind closed; landing doors where a skybridge
meets a floor line; portals cut open, a sky station's platforms."""

import copy

import numpy as np

from assetgen import asset_checks as AC
from assetgen.buildings import connections as CN
from assetgen.buildings import envelope as EN
from assetgen.buildings import genome as GN
from assetgen.buildings import parts as PT
from assetgen.buildings import roofparts as RP
from assetgen.buildings import shell as SH
from assetgen.buildings import systems as SY

from test_ag_facades import _closed, _tower
from test_ag_shell import brief_of, mass

SAMPLE = {
    "ac_unit": [{"w": 1600, "d": 1200, "h": 1200, "style": s}
                for s in ("box", "old", "split", "fan")],
    "water_tank": [{"r": 1500, "h": 3500, "style": s} for s in ("timber", "steel", "panel")],
    "antenna": [{"h": h, "style": s} for h, s in ((4000, "whip"), (4000, "dish"),
                                                 (12000, "lattice"))],
    "pad": [{"s": 20000, "h": 600, "kind": "helipad"}, {"s": 14000, "h": 500, "kind": "av_pad"}],
    "hut": [{"w": 3000, "d": 2500, "h": 2800}],
    "dunnage": [{"w": 2000, "d": 1600, "leg": 900}],
    "roof_vent": [{"style": s} for s in ("stack", "mushroom", "box")],
    "skylight": [{"w": 3000, "d": 2000, "style": s} for s in ("dome", "flat")],
    "penthouse": [{"w": 6000, "d": 5000, "h": 3500}],
    "billboard_frame": [{"w": 8000, "h": 4000, "back": 1500}],
    "escape": [{"w": 3000, "d": 1200, "zs": [3400, 6800, 10200], "ladder": 2000}],
    "duct": [{"w": 600, "dd": 400, "h": 9000}],
    "wall_vent": [{"w": 600, "h": 400}],
    "conduit": [{"L": 6000, "k": 3, "drop": 3000}],
    "camera": [{"style": s} for s in ("dome", "box")],
    "landing": [{"w": 3000, "h": 2800, "r": 200}],
    "portal_frame": [{"w": 9000, "h": 9000}],
    "balustrade": [{"L": 4000, "h": 1100}],
    "planter": [{"w": 2000, "d": 1000, "h": 600}],
}


def test_ag4_parts_are_closed_named_and_roof_equipment_untinted():
    assert set(SAMPLE) == set(RP.ROOF) | set(RP.MERGED_ROOF) | set(RP.FACADE) | \
        set(CN.FAMILIES)
    assert PT.INSTANCE_ALWAYS == frozenset(RP.ROOF)
    names = set()
    for fam, ps in SAMPLE.items():
        for p in ps:
            _, arrs = PT.mesh(fam, p)
            assert _closed(arrs), (fam, p)
            name = PT.node_name(fam, p)
            assert name.startswith(PT.type_of(fam, p))
            assert not name.rsplit(".", 1)[1].isdigit()
            names.add(name)
            if fam in RP.ROOF:
                # (instanced per tile in Unreal, with no building's Custom Primitive Data)
                assert all(SY.SLOTS[s][4] is None for s in arrs), (fam, sorted(arrs))
    assert len(names) == sum(len(v) for v in SAMPLE.values())


def _with(br, **genes):
    gm = GN.make(br)
    gm["genes"].update(genes)
    return gm, SH.build(br, gm)


def _kinds(res):
    return set((res["stats"].get("roof_form_kinds") or {}))


def _ok(br, res):
    assert _closed(res["arrays"])
    env = EN.check(br, res["arrays"], EN.part_points(res["parts"]))
    assert env["ok"], env


def test_shed_roof_forms_stay_inside_the_envelope():
    for form, crown in (("sawtooth", "flat"), ("gable", "flat"), ("barrel", "flat"),
                        ("sawtooth", "sawtooth")):
        br = _tower("corrugated", 1, btype="building.warehouse", w=40.0, d=24.0, fh=9.0)
        gm, res = _with(br, **{"roof_form": form, "crown": crown, "body.system": "corrugated"})
        _ok(br, res)
        assert _kinds(res) == {form}, (form, res["stats"].get("roof_form_kinds"))
        assert res["stats"]["roof_forms"] == 1


def test_pitched_roofs_and_mansards():
    br = _tower("stucco_shutters", 3, btype="building.villa", w=16.0, d=11.0, fh=3.2)
    br["building"]["floors"] = 3
    gm, res = _with(br, crown="pitched")
    _ok(br, res)
    assert _kinds(res) <= {"gable", "hip"} and len(_kinds(res)) == 1
    # an L: no rectangle, so a mansard on its ring
    ell = [[-10.0, -8.0], [10.0, -8.0], [10.0, 2.0], [0.0, 2.0], [0.0, 8.0], [-10.0, 8.0]]
    br = brief_of([mass(ell, 0.0, 9.6, 3)], btype="building.villa")
    gm, res = _with(br, crown="pitched")
    _ok(br, res)
    assert _kinds(res) == {"mansard"}
    # a tower keeps its flat roof (pitched forms only up to roofs.PITCHED_FLOORS floors)
    br = _tower("stucco_shutters", 20, btype="building.tower")
    gm, res = _with(br, crown="pitched")
    assert not _kinds(res)


ROOF_ITEMS = [("ac_unit", (-14.0, -10.0), (1.6, 1.2, 1.2)),
              ("water_tank", (-14.0, 7.0), (3.0, 3.0, 3.5)),
              ("antenna", (16.0, -11.0), (0.6, 0.6, 8.0)),
              ("av_pad", (8.0, 3.0), (14.0, 14.0, 0.5)),
              ("mechanical", (-4.0, -9.0), (5.0, 4.0, 3.5)),
              ("billboard", (-4.0, 10.0), (8.0, 0.6, 4.0))]


def _roofed(clearance: bool = False):
    br = _tower("glass_curtain", 10, w=40.0, d=30.0, fh=3.4)
    top = br["masses"][0]["z"][1]
    br["roof_items"] = [{"kind": k, "position": [x, y, top], "size": list(s), "yaw_deg": 0.0,
                         "mass": 0} for k, (x, y), s in ROOF_ITEMS]
    if clearance:
        br["clearances"] = [{"kind": "guideway", "id": "tl.test", "mode": "monorail",
                             "half_m": 3.0, "line": [(-4.0, -11.0, top + 3.0, top + 8.0),
                                                     (36.0, -11.0, top + 3.0, top + 8.0)]}]
    return br, top


def test_every_roof_item_has_an_asset():
    br, _ = _roofed()
    gm, res = _with(br)
    _ok(br, res)
    got = res["roof_items"]
    assert [g["kind"] for g in got] == [k for k, _, _ in ROOF_ITEMS]
    assert all(g["asset"] for g in got)
    assert got[-1]["asset"] == "sign"                    # (AG8's billboard)
    fams = {x["family"]: len(x["at"]) for x in res["parts"]}
    for f in ("ac_unit", "water_tank", "antenna", "pad"):
        assert fams.get(f, 0) >= 1, f                    # instanced, even once
    rec = {"b": {"roof_items": got, "green": [], "portals": [], "checks": {}}}
    assert AC.roofs(rec, {"b": br})["ok"]
    rec["b"]["roof_items"] = got[:-1] + [dict(got[-1], asset=None)]
    assert not AC.roofs(rec, {"b": br})["ok"]


def test_roof_equipment_keeps_out_of_a_corridor_over_it():
    br, top = _roofed(clearance=True)
    gm, res = _with(br)
    _ok(br, res)
    assert res["stats"].get("roof_items_lowered", 0) >= 1
    clr = EN.clearances(br, res["arrays"], EN.part_points(res["parts"]))
    assert clr["ok"] and clr["corridors"] == 1, clr
    # a point of the building in the corridor is a hit
    arrs = {"x": {"pos": np.array([[16000, -11000, int((top + 5.0) * 1000)]], dtype=np.int64)}}
    clr = EN.clearances(br, arrs, [])
    assert not clr["ok"] and clr["hits"] == 1 and clr["first"] == "guideway tl.test"


def test_every_skybridge_kind_is_closed():
    for kind, levels in (("enclosed", 1), ("open_deck", 1), ("stack", 3), ("catwalk", 1),
                         ("cable", 1)):
        s = {"id": f"sb.{kind}", "kind": kind, "line": [[0.0, 0.0], [24.0, 10.0]],
             "z_m": 22.0, "width_m": 4.0, "levels": levels, "level_height_m": 4.0,
             "building_ids": ["a", "b"], "walkway_ids": [], "base_m": None}
        b, arrs, info = CN.skybridge(s)
        assert _closed(arrs), kind
        ck = info["check"]
        assert ck["degenerate"] == ck["duplicate"] == ck["open_edges"] == ck["bad_edges"] == 0
        z = np.concatenate([a["pos"][:, 2] for a in arrs.values()])
        assert z.min() >= 22000 - 1500 and z.max() <= 22000 + levels * 4000 + 1500, kind


def _bridged():
    br = _tower("glass_curtain", 10, w=30.0, d=20.0, fh=3.4)
    end = {"kind": "enclosed", "width_m": 4.0, "levels": 1, "level_height_m": 4.0,
           "other": "d01.lot.e9n9.bld", "end": [15.0, 0.0]}
    br["skybridges"] = [
        dict(end, id="sb.on_floor", z_m=6 * 3.4, at={"mass": 0, "edge": 1, "s": 10.0, "d": 0.0}),
        dict(end, id="sb.off_floor", z_m=6 * 3.4 + 1.5,
             at={"mass": 0, "edge": 3, "s": 10.0, "d": 0.0}),
        dict(end, id="sb.no_edge", z_m=6 * 3.4, at=None)]
    return br


def test_landing_doors_where_a_skybridge_meets_a_floor_line():
    br = _bridged()
    gm, res = _with(br)
    _ok(br, res)
    ld = {x["id"]: x for x in res["landings"]}
    assert ld["sb.on_floor"]["door"]
    assert not ld["sb.off_floor"]["door"] and ld["sb.off_floor"]["why"] == "off_floor"
    assert ld["sb.no_edge"]["why"] == "no_edge"
    assert any(x["family"] == "landing" for x in res["parts"]) or \
        res["stats"].get("parts_merged", 0) > 0
    rec = {"b": {"landings": res["landings"]}}
    c = AC.landings(rec)
    assert c["ok"] and c["doors"] == 1 and c["off_floor"] == 1 and c["no_edge"] == 1


def _portal(station: bool):
    br = _tower("glass_curtain", 20, w=30.0, d=20.0, fh=3.4)
    p = {"line_id": "tl.sky", "z": [32.0, 41.0], "station": station,
         "lines": [[[-40.0, 0.0, 40.0], [40.0, 0.0, 40.0]]], "diameter_m": 7.0}
    if station:
        p.update(station_id="st.sky", station_name="Sky", track_z_m=36.5,
                 platform={"exterior": [[-14.0, -8.0], [14.0, -8.0], [14.0, 8.0],
                                        [-14.0, 8.0]], "holes": []})
    br["portals"] = [p]
    return br


def test_portals_are_cut_open():
    for station in (False, True):
        br = _portal(station)
        gm, res = _with(br)
        _ok(br, res)
        rec = res["portals"][0]
        assert rec["cut"], station
        assert rec["platform"] == station
        clr = EN.clearances(br, res["arrays"], EN.part_points(res["parts"]))
        assert clr["portal_hits"] == 0, clr
        c = AC.roofs({"b": {"roof_items": [], "green": [], "portals": res["portals"]}},
                     {"b": br})
        assert c["ok"] and c["portals_cut"] == 1
    # no point of a solid tower left in the tube
    br = _portal(False)
    solid = copy.deepcopy(br)
    solid["portals"] = []
    gm = GN.make(solid)
    res = SH.build(solid, gm)
    assert EN.clearances(br, res["arrays"], EN.part_points(res["parts"]))["portal_hits"] > 0
