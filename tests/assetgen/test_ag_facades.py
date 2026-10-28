"""AG2's facades on small made-up briefs: every part closed and named by its parameters,
every facade system a closed shell inside its envelope, parts merged below eight placements
and instanced from eight, massing articulation (corner cuts, setback ledges, crowns,
arcades, canopies), balconies only where the facade has room, irregularity by grime and
wealth, the thumbnail hash and the budgets per building class."""

import copy

from assetgen import asset_checks as AC
from assetgen import build as BD
from assetgen.buildings import envelope as EN
from assetgen.buildings import genome as GN
from assetgen.buildings import meshbuf as MB
from assetgen.buildings import parts as PT
from assetgen.buildings import shell as SH
from assetgen.buildings import systems as SY
from assetgen.buildings import thumb as TH

from test_ag_shell import ERA, brief_of, mass, rect

SAMPLE = {
    "window": {"style": "casement", "w": 1200, "h": 1500, "r": 150, "fw": 70, "fd": 80,
               "sill": (50, 70, 60), "lintel": (25, 220, 90)},
    "cap": {"dir": "v", "w": 70, "p": 90, "h": 30000},
    "spandrel": {"w": 1200, "h": 700, "r": 150},
    "balcony": {"style": "enclosed", "w": 2800, "d": 1200, "t": 200, "rh": 1050, "eh": 2800},
    "louver": {"w": 2400, "h": 2000, "r": 100, "n": 9, "bd": 140, "tilt": 30},
    "fin": {"t": 100, "d": 450, "h": 30000},
    "shade": {"L": 2400, "d": 450, "t": 60},
    "shutter": {"w": 500, "h": 1500},
    "grille": {"w": 1200, "h": 1500},
    "panel": {"style": "screen", "w": 600, "h": 3800, "t": 30, "off": 330},
    "member": {"dx": -6000, "dz": 12000, "w": 280, "y0": -120, "y1": 400},
    "pod": {"w": 2300, "h": 2800, "r": 200, "d": 450, "pr": 690},
    "ac": {"w": 660, "h": 420, "do": 350, "di": 120},
    "dish": {"rd": 400},
    "column": {"w": 500, "h": 4500},
    "balconette": {"w": 1200, "rh": 900},
    "canopy": {"L": 20000, "d": 1500, "t": 300},
    "mast": {"style": "spire", "h": 30000},
}


def _closed(arrs):
    ck = MB.check(arrs)
    return ck["triangles"] > 0 and ck["degenerate"] == ck["duplicate"] == \
        ck["open_edges"] == ck["bad_edges"] == 0


def test_parts_are_closed_and_named_by_their_parameters():
    assert set(SAMPLE) == set(PT.GEN) == set(PT.REACH)
    names = set()
    for fam, p in SAMPLE.items():
        _, arrs = PT.mesh(fam, p)
        assert _closed(arrs), fam
        name = PT.node_name(fam, p)
        assert name == PT.node_name(fam, dict(p)) and name.startswith(PT.type_of(fam, p))
        assert not name.rsplit(".", 1)[1].isdigit()
        names.add(name)
    assert len(names) == len(SAMPLE)
    bigger = dict(SAMPLE["window"], w=1210)
    assert PT.node_name("window", bigger) != PT.node_name("window", SAMPLE["window"])


def _tower(system: str, floors: int, use="residential", btype="building.tower",
           classes=None, w=30.0, d=20.0, fh=3.4, style=None):
    era = dict(ERA, systems={system: 1.0}, crowns=["flat"])
    br = brief_of([mass(rect(-w / 2, -d / 2, w / 2, d / 2), 0.0, floors * fh, floors)],
                  btype=btype, era=era, classes=classes)
    br["building"]["use"] = use
    br["building"]["floor_grid"]["floor_height_m"] = fh
    for e in br["edges"]:
        for r in e["regions"]:
            r["road_class"] = "street"
    if style:
        br["override"] = {"style": style}
    return br


def _built(br):
    gm = GN.make(br)
    res = SH.build(br, gm)
    return gm, res


def test_every_system_builds_a_closed_shell_inside_its_envelope():
    for s in SY.ALL_SYSTEMS:
        lo, hi, _ = SY.FLOORS.get(s, (0, 999, None))
        floors = 4 if hi <= 6 else 12
        btype = "building.shanty_stack" if s == "shanty_patchwork" else "building.tower"
        br = _tower(s, floors, btype=btype)
        gm, res = _built(br)
        assert gm["genes"]["body.system"] == s
        assert _closed(res["arrays"]), s
        env = EN.check(br, res["arrays"], EN.part_points(res["parts"]))
        assert env["ok"], (s, env)
        placed = res["stats"]["parts_merged"] + res["stats"]["parts_instanced"]
        assert placed > 0, s
        for x in res["parts"]:
            assert len(x["at"]) >= PT.INSTANCE_MIN


def test_merged_parts_keep_the_shell_closed():
    br = _tower("punched_brick", 2, w=9.0, d=7.0)
    _, res = _built(br)
    assert res["stats"]["parts_merged"] > 0
    assert _closed(res["arrays"]) and "frame" in res["arrays"]


def test_corner_cuts_and_setbacks_stay_inside():
    for cut in ("chamfer", "round"):
        br = _tower("unitized_curtain_wall", 30, use="office",
                    style={"cut": cut, "cut_m": 2.0, "setback": "ledge", "setback_m": 1.5,
                           "setback_at": 0.6})
        gm = GN.make(br)
        sb = SH.ShellBuilder(br, gm)
        res = sb.build()
        assert "cut" in res["used"]["articulation"] and "setback" in res["used"]["articulation"]
        assert len(sb.masses) == 2
        assert len(sb.masses[0]["rings"][0]) > 4
        assert sb.masses[1]["z0"] == sb.masses[0]["z1"]
        assert _closed(res["arrays"])
        assert EN.check(br, res["arrays"], EN.part_points(res["parts"]))["ok"]


def test_crowns_and_arcades():
    for crown, slot in (("stepped", None), ("halo", "fin"), ("mast", "mast"),
                        ("spire", "mast")):
        br = _tower("fin_wall", 24, use="office", style={"crown": crown})
        _, res = _built(br)
        assert res["used"]["crown"], crown
        if slot:
            assert slot in res["arrays"] or any(x["family"] == slot for x in res["parts"])
        assert _closed(res["arrays"])
        assert EN.check(br, res["arrays"], EN.part_points(res["parts"]))["ok"], crown
    br = _tower("board_marked_concrete", 8, use="office", fh=4.2,
                classes={(0, 0, i): "front" for i in range(4)},
                style={"arcade": "arcade", "arcade_m": 2.5})
    gm = GN.make(br)
    sb = SH.ShellBuilder(br, gm)
    res = sb.build()
    assert "arcade" in res["used"]["articulation"] and sb.arcades
    assert "column" in res["arrays"] or any(x["family"] == "column" for x in res["parts"])
    assert EN.check(br, res["arrays"], EN.part_points(res["parts"]))["ok"]


def test_balconies_only_where_there_is_room():
    style = {"body.balcony": "solid", "body.balcony_pat": "every", "body.balcony_m": 1.5}
    classes = {(0, 0, 0): "street", (0, 0, 1): "alley", (0, 0, 2): "park", (0, 0, 3): "party"}
    br = _tower("precast_panel", 8, classes=classes, style=style)
    gm, res = _built(br)
    balc = [x for x in res["parts"] if x["family"] == "balcony"]
    assert balc
    for x in balc:
        for a in x["at"]:
            # the street edge (y = -10 m) takes 1.2 m, the park (y = +10 m) 1.5 m, the alley
            # (x = +15 m) and the party wall (x = -15 m) none
            assert abs(a[0]) < 15000 - 10
            assert x["params"]["d"] <= (1200 if a[1] < 0 else 1500)
    assert EN.check(br, res["arrays"], EN.part_points(res["parts"]))["ok"]


def test_irregularity_follows_grime_and_wealth():
    def irregular(grime, wealth):
        br = _tower("punched_concrete", 6)
        br["building"]["style"]["grime"] = grime
        br["district"]["wealth"] = wealth
        gm, res = _built(br)
        fams = {x["family"] for x in res["parts"]} | {
            s for s in res["arrays"] if s in ("ac", "grille", "patch_ply", "dish")}
        return gm["cont"]["irreg"], res["used"]["irregular"], fams
    clean = irregular(0.0, 0.9)
    dirty = irregular(0.9, 0.1)
    assert clean[0] == 0.0 and not clean[1]
    assert dirty[0] > 0.5 and dirty[1]
    assert dirty[2] & {"ac", "grille", "patch_ply", "panel", "dish"}


def test_thumbnails_tell_buildings_apart():
    a = _tower("punched_brick", 6)
    b = _tower("unitized_curtain_wall", 20, use="office")
    recs = {}
    for k, br in (("a", a), ("b", b)):
        gm, res = _built(br)
        t = {c: SY.srgb_linear(v) for c, v in gm["colors"].items()}
        h, fill = TH.hash_of(br, res["arrays"], res["parts"], t)
        assert h == TH.hash_of(copy.deepcopy(br), res["arrays"], res["parts"], t)[0]
        assert len(h) * 4 >= TH.BITS and 0.05 < fill < 1.0
        recs[k] = h
    H = TH.distances([recs["a"], recs["b"]])
    import numpy as np
    assert int(np.bitwise_count(H[0] ^ H[1]).sum()) >= AC.THUMB_MIN
    # twins outside a family fail on their thumbnails even when their genes differ
    _, _, rec = BD.building_asset(a, GN.make(a))
    r1, r2 = copy.deepcopy(rec), copy.deepcopy(rec)
    r2["genes"] = {k: (v + "x" if isinstance(v, str) else v) for k, v in r2["genes"].items()}
    out = AC.unique({"a": r1, "b": r2}, 4)
    assert out["failures"] == 0 and out["thumbs"]["failures"] == 1 and not out["ok"]
    r2["thumb_fill"] = 0.01                      # a sliver: told apart by its genes alone
    assert AC.unique({"a": r1, "b": r2}, 4)["ok"]


def test_budget_classes():
    br = _tower("precast_panel", 12)
    _, _, rec = BD.building_asset(br, GN.make(br))
    assert rec["class"] == "high" and AC.budget_class(dict(rec, type="building.megabuilding")) \
        == "mega"
    ok = AC.budget({"a": rec})
    assert ok["ok"] and ok["over"] == 0
    fat = dict(rec, triangles=rec["triangles"] * 50)
    assert AC.budget({"a": fat})["over"] == 1


def test_building_glb_holds_its_instanced_parts():
    br = _tower("fin_wall", 16, use="office")
    gm = GN.make(br)
    data = BD.building_glb(br["id"], br, gm)
    _, res = _built(br)
    assert res["parts"]
    for x in res["parts"]:
        assert x["node"].encode() in data
    assert data == BD.building_glb(br["id"], copy.deepcopy(br), gm)
