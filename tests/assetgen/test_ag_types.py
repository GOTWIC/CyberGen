"""AG5's types, landmarks and slopes on small made-up briefs: every type part closed and
named by its parameters; the listed types built by their own generators inside the envelope;
heroes with their U2 mask and hero UV; a building on a slope on a stepped plinth with
retaining skirts; a skybridge's landing door left open in the collision; a sky station beside
its tower with a platform; the new checks; the review sheet and the spec diff; a hero's
materials in the contribution."""

import copy
import json

import numpy as np

from assetgen import asset_checks as AC
from assetgen import contribution as UC
from assetgen import review as RV
from assetgen.buildings import collision as CO
from assetgen.buildings import envelope as EN
from assetgen.buildings import genome as GN
from assetgen.buildings import heroes as HE
from assetgen.buildings import meshbuf as MB
from assetgen.buildings import parts as PT
from assetgen.buildings import roofparts as RP
from assetgen.buildings import shell as SH
from assetgen.buildings import typeparts as TP
from assetgen.buildings import types as TY

from test_ag_facades import _closed, _tower
from test_ag_shell import brief_of, mass, rect

SAMPLE = {
    "eave": [{"W": 8000, "D": 6000, "w": 6000, "d": 4000, "out": 1200, "rise": 800,
              "drop": 200, "curl": 400, "t": 200}],
    "needle": [{"h": 20000, "r": 600}],
    "pillar": [{"r": 280, "h": 4000, "style": s} for s in ("steel", "temple", "round")],
    "stairs": [{"w": 3000, "n": 6, "rise": 170, "run": 300}],
    "ladder": [{"h": 6000, "w": 500}],
    "hangar_door": [{"w": 30000, "h": 12000, "leaves": 4}],
    "truss": [{"L": 12000, "h": 1500, "panels": 6, "w": 300}],
    "finial": [{"h": 3000, "r": 400}],
    "beacon": [{"s": 400}],
    "seam": [{"w": 500, "h": 30000, "d": 140}],
    "halo": [{"r0": 10000, "r1": 11000, "t": 600, "n": 12, "post": 2000}],
    "garden": [{"w": 2000, "d": 1000, "h": 700}],
    "terrace_rail": [{"L": 6000, "h": 1100, "style": s} for s in ("glass", "bars")],
    "gondola": [{"r": 1400, "h": 2600}],
    "lattice": [{"w0": 1800, "w1": 1080, "h": 30000, "bays": 4}],
    "dormer": [{"w": 1400, "h": 1800, "d": 3000, "style": s} for s in ("gable", "shed")],
    "tarp": [{"w": 3000, "d": 2500, "h": 2200, "tilt": 300}],
    "shack_roof": [{"W": 4000, "D": 3000, "rise": 600, "over": 300}],
    "stack": [{"r": 300, "h": 4000}],
    "monitor": [{"L": 12000, "w": 2400, "h": 1200}],
    "pergola": [{"w": 3000, "d": 2600, "h": 2500}],
    "chimney": [{"w": 900, "d": 700, "h": 2500}],
    "cab": [{"W": 9000, "D": 9000, "h": 4000, "lean": 600, "over": 800}],
    "radar": [{"r": 1500}],
    "neon_strip": [{"L": 6000, "h": 400, "d": 120, "slot": "neon"}],
    "girder": [{"L": 20000, "h": 2000, "w": 600}],
}


def test_type_parts_are_closed_and_named():
    assert set(SAMPLE) == set(TP.GEN)
    names = set()
    for fam, ps in SAMPLE.items():
        for p in ps:
            _, arrs = PT.mesh(fam, p)
            assert _closed(arrs), (fam, p)
            name = PT.node_name(fam, p)
            assert name.startswith(PT.type_of(fam, p))
            assert not name.rsplit(".", 1)[1].isdigit()
            names.add(name)
    assert len(names) == sum(len(v) for v in SAMPLE.values())
    for st in RP.PENTHOUSE_STYLES:          # (the AG4 penthouse, by era)
        _, arrs = PT.mesh("penthouse", {"w": 6000, "d": 5000, "h": 3500, "style": st})
        assert _closed(arrs), st


def test_every_scope_type_has_its_generator():
    scope = ("shanty_stack", "megabuilding", "warehouse", "shed", "yard", "hangar", "lab",
             "villa", "terraced", "temple_hall", "pagoda", "gate_house", "terminal",
             "control_tower", "station", "parking_structure", "straddle_building")
    for t in scope:
        assert TY.generator_of(f"building.{t}") not in (None, "general"), t
        assert TY.generator_of(f"building.{t}") in TY.PRE or \
            TY.generator_of(f"building.{t}") in TY.MASS or \
            TY.generator_of(f"building.{t}") in TY.POST, t
    for k in ("megatower", "spire", "arcology", "ferris_wheel"):
        assert TY.generator_of(f"building.landmark.{k}") == f"hero.{k}"
    assert TY.generator_of("building.tower") == "general"


def _check(sh, br):
    ck = MB.check(sh["arrays"])
    assert ck["degenerate"] == ck["duplicate"] == ck["open_edges"] == ck["bad_edges"] == 0
    env = EN.check(br, sh["arrays"], EN.part_points(sh["parts"]))
    assert env["ok"], env


def test_types_build_inside_their_envelope():
    feats = 0
    for t, floors, attrs in (("building.shanty_stack", 5, {}), ("building.warehouse", 1, {}),
                             ("building.shed", 1, {"open_sides": True}),
                             ("building.villa", 2, {}), ("building.lab", 4, {}),
                             ("building.parking_structure", 4, {}),
                             ("building.temple_hall", 1, {}), ("building.pagoda", 3, {})):
        h = 9.0 if floors == 1 else floors * 3.2
        br = brief_of([mass(rect(-12.0, -9.0, 12.0, 9.0), 0.0, h, floors)], btype=t,
                      bid=f"d01.lot.{t.rsplit('.', 1)[1]}.bld")
        br["building"]["attrs"] = dict(attrs)
        sh = SH.build(br, GN.make(br))
        assert sh["generator"] == TY.generator_of(t)
        _check(sh, br)
        feats += sh["stats"].get("type_features", 0)
    assert feats >= 8


def _tower_hero(kind="megatower"):
    masses = [mass(rect(-20.0, -20.0, 20.0, 20.0), 0.0, 24.0, 6),
              mass(rect(-12.0, -12.0, 12.0, 12.0), 24.0, 150.0, 34, role="tower")]
    br = brief_of(masses, btype=f"building.landmark.{kind}", bid="d01.lm.e0n0.bld")
    br["building"]["landmark"] = True
    br["spec"]["landmark"] = {"brief": "", "palette": ["#0d1117", "#c1121f", "#9fb4c7"],
                              "crown": "halo"}
    return br


def test_a_hero_has_its_mask_and_hero_uv():
    br = _tower_hero()
    gm = GN.make(br)
    sh = SH.build(br, gm)
    _check(sh, br)
    h = sh["hero"]
    assert h["kind"] == "megatower" and h["accent"] == "#c1121f"
    assert h["height_m"] == 150.0 and h["perimeter_m"] > 0
    m = sh["mask"]
    assert m.shape == (HE.MASK_PX, HE.MASK_PX, 3) and m.dtype == np.uint8
    assert np.array_equal(m, SH.build(copy.deepcopy(br), gm)["mask"])
    assert m[-1, :, 0].mean() > m[HE.MASK_PX // 2, :, 0].mean()     # grime at the foot
    assert sh["stats"].get("type_features", 0) + sh["stats"].get("hero_features", 0) > 0
    arrs = MB.split(sh["arrays"])[0]
    prims = sh["buf"].primitives(arrs, {k: 0 for k in arrs}, (h["perimeter_m"],
                                                              h["height_m"]))
    for name, pr in zip(arrs, prims):
        assert pr.uv1 is not None, name
        if name not in ("glass", "glazing"):
            assert 0.0 <= pr.uv1[:, 1].min() and pr.uv1[:, 1].max() <= 1.0


def _slope_brief():
    br = brief_of([mass(rect(-12.0, -8.0, 12.0, 8.0), 0.0, 12.8, 4)],
                  bid="d01.lot.slope.bld")
    fg = br["building"]["floor_grid"]
    fg["base_m"], fg["plinth_m"] = 50.0, 48.2
    rows = []
    for e in br["edges"]:
        (ax, ay), (bx, by) = e["a"], e["b"]
        n = int(e["length_m"] // 1.0)
        pts = [k / e["length_m"] for k in range(n + 1)] + [1.0]
        # the ground falls 0.12 per meter to the west, the base at the east third
        rows.append([round(0.12 * (ax + (bx - ax) * f - 4.0), 2) for f in pts])
    br["terrain"] = {"step_m": 1.0, "out_m": 0.3, "grade": rows}
    return br


def test_a_building_on_a_slope_stands_on_a_stepped_plinth():
    br = _slope_brief()
    assert SH.plinth_mm(br) > 1500
    sh = SH.build(br, GN.make(br))
    _check(sh, br)
    st = sh["stats"]
    assert st.get("plinth_facades", 0) >= 3 and st.get("retaining_skirts", 0) >= 1
    low = -min(v for r in br["terrain"]["grade"] for v in r)
    assert low >= AC.SLOPE_MIN_M
    rec = {"type": br["building"]["type"], "plinth_m": SH.plinth_mm(br) / 1000.0,
           "grade_low_m": low, "stats": st}
    r = AC.slopes({"a": rec})
    assert r["ok"] and r["falling"] == 1
    flat = dict(rec, stats={})
    assert not AC.slopes({"a": flat})["ok"]
    # (a plinth whose walls' ground stays within 0.3 m of the base needs no step)
    assert AC.slopes({"a": dict(flat, grade_low_m=0.2)})["ok"]


def _inside(col, x, y, z):
    import math
    for b in col["boxes"]:
        (cx, cy, cz), (hx, hy, hz) = b["center"], b["extent"]
        a = math.radians(-b["yaw_deg"])
        dx, dy = x - cx, y - cy
        u, v = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
        if abs(u) <= hx and abs(v) <= hy and abs(z - cz) <= hz:
            return True
    for c in col["convex"]:
        if not c["z"][0] <= z <= c["z"][1]:
            continue
        r = c["ring"]
        if all((r[(i + 1) % len(r)][0] - r[i][0]) * (y - r[i][1]) -
               (r[(i + 1) % len(r)][1] - r[i][1]) * (x - r[i][0]) >= 0 for i in range(len(r))):
            return True
    return False


def test_collision_leaves_a_landing_door_open():
    br = brief_of([mass(rect(-10.0, -8.0, 10.0, 8.0), 0.0, 30.0, 10)])
    door = {"edge": 0, "s0": 4000, "s1": 7000, "z": 9000, "hi": 12000}
    col = CO.build(br, None, [door])
    assert _inside(col, -4.5, -7.0, 10.5) is False       # through the door, 1 m in
    assert _inside(col, -4.5, -4.0, 10.5) is True        # past the vestibule
    assert _inside(col, -4.5, -7.0, 8.0) and _inside(col, -4.5, -7.0, 13.0)
    assert _inside(CO.build(br, None), -4.5, -7.0, 10.5)  # (no door: closed)


def test_collision_lets_a_walk_under_an_open_shed():
    br = brief_of([mass(rect(-12.0, -9.0, 12.0, 9.0), 0.0, 9.0, 1)], btype="building.shed",
                  bid="d01.lot.shed.bld")
    br["building"]["attrs"] = {"open_sides": True}
    sh = SH.build(br, GN.make(br))
    under = {mi["mass"]: mi["under_m"] for mi in sh["masses"] if mi.get("under_m") is not None}
    assert list(under) == [0] and 3.0 < under[0] < 8.4     # (under its eave's 0.6 m slab)
    col = CO.build(br, sh["band_m"], None, under)
    assert not _inside(col, 0.0, 0.0, 1.7) and not _inside(col, -11.5, 8.5, 1.7)
    assert _inside(col, 0.0, 0.0, under[0] + 0.3)          # (the roof still collides)
    assert _inside(CO.build(br, sh["band_m"]), 0.0, 0.0, 1.7)  # (closed without it)


def test_a_sky_station_beside_its_tower_gets_a_platform():
    br = _tower("glass_curtain", 20, w=30.0, d=20.0, fh=3.4)
    # (the tube runs 7 m south of the tower and climbs 1 m along the station)
    br["portals"] = [{"line_id": "tl.sky", "z": [32.0, 42.0], "station": True,
                      "station_id": "st.sky", "station_name": "Sky", "track_z_m": 36.5,
                      "lines": [[[-40.0, -17.0, 40.0], [40.0, -17.0, 41.0]]],
                      "diameter_m": 7.0,
                      "platform": {"exterior": [[-14.0, -24.0], [14.0, -24.0], [14.0, -12.0],
                                                [-14.0, -12.0]], "holes": []}}]
    gm = GN.make(br)
    res = SH.build(br, gm)
    rec = res["portals"][0]
    assert not rec["cut"] and rec["through"] == 0
    assert rec["platform"] and rec["beside"] and rec["floor_m"] == 33.98      # (under the lowest axis)
    pos = res["arrays"]["platform"]["pos"]
    assert pos[:, 1].min() >= -14_300 and pos[:, 1].max() == -10_000   # (to the wall only)
    assert EN.check(br, res["arrays"], EN.part_points(res["parts"]))["ok"]
    assert EN.clearances(br, res["arrays"], EN.part_points(res["parts"]))["portal_hits"] == 0
    c = AC.roofs({"b": {"roof_items": [], "green": [], "portals": res["portals"]}}, {"b": br})
    assert c["ok"] and c["portals_passing"] == 1 and c["platforms"] == 1


def _rec(t, gen, genes=None, fam=None, cx=None, hero=None):
    r = {"type": t, "generator": gen, "genes": genes or {}, "family": fam,
         "stats": {}, "bounds": [[0, 0, 0], [10, 10, 10]]}
    if cx:
        r["complex"] = cx
    if hero:
        r["hero"] = hero
    return r


def test_the_types_and_families_checks():
    ok = {"a": _rec("building.shed", "shed"), "b": _rec("building.tower", "general"),
          "c": _rec("building.landmark.spire", "hero.spire",
                    hero={"kind": "spire", "mask": "textures/hero/c.png"}),
          "d": _rec("building.stadium", "general")}
    r = AC.types(ok)
    assert r["ok"] and r["heroes"] == 1 and r["unlisted_types"] == {"building.stadium": 1}
    bad = dict(ok, a=_rec("building.shed", "general"))
    assert not AC.types(bad)["ok"]
    nomask = dict(ok, c=_rec("building.landmark.spire", "hero.spire", hero={"kind": "spire"}))
    assert not AC.types(nomask)["ok"]
    g = {"body.system": "fin_wall", "body.window": "strip", "body.bay_m": 3.0, "dirt_m": 2.0}
    fam = {"x": _rec("building.tower", "general", g, "p1", "tower_cluster"),
           "y": _rec("building.tower", "general", dict(g, **{"body.bay_m": 3.2, "dirt_m": 6.0}),
                     "p1", "tower_cluster")}
    assert AC.families(fam)["ok"]                 # (a cluster's members step their sizes)
    tw = {k: dict(v, complex="twin_towers") for k, v in fam.items()}
    assert not AC.families(tw)["ok"]              # (twins are one design)
    fam["y"]["genes"]["body.window"] = "punched"
    assert not AC.families(fam)["ok"]
    assert AC.budget_class(ok["c"]) == "hero"


def test_review_rounds_and_spec_diff(tmp_path):
    a = {"city": "X", "districts": {"Old": {"wear": 1.0}}, "landmarks": {}}
    b = {"city": "X", "districts": {"Old": {"wear": 1.4, "era": "heritage"}},
         "landmarks": {"T": {"crown": "halo"}}}
    assert RV.spec_diff(a, b) == ['districts.Old.era: added "heritage"',
                                  "districts.Old.wear: 1.0 -> 1.4",
                                  'landmarks.T: added {"crown": "halo"}']
    man = {"city": "X", "buildings": {
        "b1": {"district": "d01", "genes": {"body.system": "fin_wall"},
               "material": {"era": "heritage"}, "generator": "shed", "cpd": [0, 0, 0, 0.6],
               "hero": None},
        "b2": {"district": "d01", "genes": {"body.system": "punched_brick"}, "material": None,
               "generator": "general", "cpd": [0, 0, 0, 0.4], "plinth_m": 1.2}}}
    rep = {"buildings": 2, "triangles": {"unique": 1000}, "parts": {"instances": 10},
           "stats": {"type_features": 3}, "checks": {"asset_types": {"name": "asset_types",
                                                                      "ok": True}}}
    for r, spec in (("r1", a), ("r2", b)):
        d = tmp_path / r / "assets"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps(man))
        (d / "asset_report.json").write_text(json.dumps(rep))
        (tmp_path / f"{r}.json").write_text(json.dumps(spec))
    r1 = RV.review(tmp_path / "r1", tmp_path / "r1.json")
    assert r1["round"] == 1 and r1["passed"] and r1["numbers"]["city"]["on_slopes"] == 1
    assert r1["numbers"]["districts"]["d01"]["systems"].startswith("fin_wall 50%")
    r2 = RV.review(tmp_path / "r2", tmp_path / "r2.json", tmp_path / "r1")
    assert r2["round"] == 2 and r2["spec_changes"] == RV.spec_diff(a, b)
    md = (tmp_path / "r2" / "assets" / "review.md").read_text()
    assert "round 2 of at most 3" in md and "districts.Old.wear" in md


def test_a_hero_gets_materials_of_its_own():
    mats = {"wall": {"master": "facade", "color": [0.5, 0.5, 0.5], "textures": {"BaseTex": "t"},
                     "scalars": {"Textured": 1.0}, "vectors": {}},
            "hero_light": {"master": "neon", "color": [1.0, 1.0, 1.0]},
            "glass": {"master": "glass", "color": [0.1, 0.1, 0.1], "textures": {"X": "t"}}}
    def con():
        return {"materials": copy.deepcopy(mats), "textures": {"t": {"kind": "color"}},
                "entries": [{"key": "h", "kind": "building",
                             "slots": ["glass", "hero_light", "wall"]},
                            {"key": "o", "kind": "building", "slots": ["wall"]}]}
    man = {"buildings": {"h": {"hero": {"kind": "spire", "accent": "#ff0000",
                                        "mask": "textures/hero/h.png", "mask_sha256": "a" * 64,
                                        "mask_px": 512}},
                         "o": {}}}
    out = UC.heroes(con(), man, True)
    e = out["entries"][0]
    assert e["hero"] == {"kind": "spire", "accent": "#ff0000"}
    assert e["materials"] == {"hero_light": "hero_light#h", "wall": "wall#h"}
    assert out["materials"]["wall#h"]["textures"]["HeroMask"] == "city.hero.h"
    assert out["materials"]["wall#h"]["scalars"]["HeroMaskOn"] == 1.0
    assert out["materials"]["hero_light#h"]["color"] == [1.0, 0.0, 0.0]
    assert out["textures"]["city.hero.h"]["kind"] == "mask"
    assert "materials" not in out["entries"][1] and out["materials"]["wall"] == mats["wall"]
    flat = UC.heroes(con(), man, False)            # (no library: the accent only)
    assert flat["entries"][0]["materials"] == {"hero_light": "hero_light#h"}
