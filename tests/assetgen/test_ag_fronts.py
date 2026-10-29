"""AG3's street fronts on a small made-up shopfront row and on the small test city: a
shopfront per unit, a door at every entrance (a unit or entrance on a party wall moved to
an open facade), the band its own closed mesh inside the envelope, collision starting at
its top, mounts on solid wall, every street-front part closed, the access and mounts checks,
the contribution's front and decal entries and the materials of every AG3 slot."""

import json

from assetgen import contribution as UC
from assetgen.buildings import collision as CO
from assetgen.buildings import envelope as EN
from assetgen.buildings import frontparts as FP
from assetgen.buildings import genome as GN
from assetgen.buildings import meshbuf as MB
from assetgen.buildings import parts as PT
from assetgen.buildings import shell as SH
from assetgen.buildings import systems as SY
from assetgen.materials import catalog as CT

from agtools import small_assets, small_assets_report
from test_ag_shell import ERA, brief_of, mass, rect


def _closed(arrs):
    ck = MB.check(arrs)
    return ck["triangles"] > 0 and ck["degenerate"] == ck["duplicate"] == \
        ck["open_edges"] == ck["bad_edges"] == 0


def _unit(edge, s, w, use, a, b):
    t = (s / ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5)
    p = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
    return {"at": {"d": 0.0, "edge": edge, "mass": 0, "s": s}, "awning_m": 0.0,
            "edge": [a, b], "entrance": p, "segment_id": None, "sign": False, "use": use,
            "width_m": w}


def _entrance(edge, s, kind, a, b):
    t = (s / ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5)
    p = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
    return {"at": {"d": 0.0, "edge": edge, "mass": 0, "s": s}, "kind": kind, "position": p,
            "segment_id": None, "walkway_id": f"wk.test{edge}"}


def row():
    """A three-floor row, 24 by 12 m: a street to the south (three shops), a neighbor
    against its east wall (a unit there too), an alley north (a loading door), a street west
    (the main entrance); a wall light on the south wall."""
    era = dict(ERA, systems={"punched_brick": 1.0})
    br = brief_of([mass(rect(-12.0, -6.0, 12.0, 6.0), 0.0, 12.0, 3)],
                  btype="building.shopfront_row", era=era,
                  classes={(0, 0, 1): "party", (0, 0, 2): "alley"})
    br["building"]["use"] = "mixed"
    br["building"]["floor_grid"]["floor_height_m"] = 4.0
    S, E, N, W = ([-12.0, -6.0], [12.0, -6.0]), ([12.0, -6.0], [12.0, 6.0]), \
        ([12.0, 6.0], [-12.0, 6.0]), ([-12.0, 6.0], [-12.0, -6.0])
    br["units"] = [_unit(0, 4.0, 6.5, "bar", *S), _unit(0, 11.5, 6.0, "food", *S),
                   _unit(0, 19.0, 7.0, "shop", *S), _unit(1, 6.0, 5.0, "shop", *E)]
    br["entrances"] = [_entrance(3, 6.0, "main", *W), _entrance(2, 12.0, "loading", *N)]
    br["props"] = [{"at": {"d": 0.0, "edge": 0, "mass": 0, "s": 7.6}, "attrs": {},
                    "gap_m": 0.0, "id": "d01.prop.wall_light.test", "kind": "wall_light",
                    "on_wall": True, "position": [-4.4, -6.0, 3.6], "scale": [1.0, 1.0, 1.0],
                    "yaw_deg": -90.0}]
    return br


def test_street_front_parts_are_closed():
    br = row()
    sb = SH.ShellBuilder(br, GN.make(br))
    sb.build()
    fams = {}
    for k, (fam, p) in sb.parts.defs.items():
        if fam in FP.FAMILIES:
            fams.setdefault(fam, []).append(p)
    assert {"shopfront", "door"} <= set(fams)
    for fam, ps in fams.items():
        for p in ps:
            _, arrs = PT.mesh(fam, p)
            assert _closed(arrs), (fam, p)
            name = PT.node_name(fam, p)
            assert name.startswith(PT.type_of(fam, p)) and \
                not name.rsplit(".", 1)[1].isdigit()
    assert set(FP.FAMILIES) <= set(PT.GEN) and set(FP.FAMILIES) <= set(PT.REACH)


def test_a_door_at_every_entrance_and_unit():
    br = row()
    res = SH.build(br, GN.make(br))
    doors = res["doors"]
    assert sorted(d["entrance"] for d in doors if d["entrance"] is not None) == [0, 1]
    assert sorted(d["unit"] for d in doors if d["unit"] is not None) == [0, 1, 2, 3]
    acc = res["checks"]["access"]
    assert acc["missing"] == 0 and acc["doors"] == len(doors)
    main = next(d for d in doors if d["entrance"] == 0)
    assert main["kind"] == "main" and not main["flush"] and main["depth"] > 0
    load = next(d for d in doors if d["entrance"] == 1)
    assert load["kind"] in ("dock", "rollup")
    # the unit on the wall a neighbor stands against: its door on an open facade
    moved = next(d for d in doors if d["unit"] == 3)
    assert moved["moved"] and moved["class"] not in ("party", "hidden")
    assert res["stats"].get("storefronts", 0) >= 3
    for d in doors:
        assert d["walkway_id"] is None or d["walkway_id"].startswith("wk.test")


def test_the_band_is_its_own_closed_mesh_inside_the_envelope():
    br = row()
    res = SH.build(br, GN.make(br))
    shell, front = MB.split(res["arrays"])
    assert _closed(shell) and _closed(front)
    assert res["band_m"] == 4.0
    env = EN.check(br, res["arrays"], EN.part_points(res["parts"]))
    assert env["ok"], env
    col = CO.build(br, res["band_m"])
    assert col["boxes"] and all(abs(b["center"][2] - b["extent"][2] - 4.0) < 1e-6
                                for b in col["boxes"])
    # nothing under the band's top in the shell but the plinth's
    zs = [int(z) for a in shell.values() for z in a["pos"][:, 2]]
    assert min(zs) >= 4000 - 1


def test_a_building_on_a_deck_has_its_front_on_the_deck():
    """M14: a building on a deck stands on the deck's top (its masses from `deck_m` over a
    pivot on the ground): its band, doors and collision start there."""
    br = row()
    for m in br["masses"]:
        m["z"] = [m["z"][0] + 9.0, m["z"][1] + 9.0]
    for e in br["edges"]:
        for r in e["regions"]:
            r["z"] = [r["z"][0] + 9.0, r["z"][1] + 9.0]
    br["building"]["floor_grid"].update(level=1, deck_m=9.0)
    res = SH.build(br, GN.make(br))
    assert res["band_m"] == 13.0 and res["checks"]["access"]["missing"] == 0
    assert all(d["pos"][2] >= 9000 for d in res["doors"])
    shell, front = MB.split(res["arrays"])
    assert _closed(shell) and _closed(front)
    col = CO.build(br, res["band_m"])
    assert all(abs(b["center"][2] - b["extent"][2] - 13.0) < 1e-6 for b in col["boxes"])


def test_a_band_too_low_for_a_door_stays_closed():
    """A platform 1.4 m high (a temple's base, a loading dock's plinth) takes no door cut
    into its band: its entrance's door hangs flush on it, and both meshes close."""
    br = brief_of([mass(rect(-10.0, -6.0, 10.0, 6.0), 0.0, 1.4, 1),
                   mass(rect(-7.0, -4.0, 7.0, 4.0), 1.4, 10.0, 2, role="hall")],
                  btype="building.temple_hall")
    S = ([-10.0, -6.0], [10.0, -6.0])
    br["entrances"] = [_entrance(0, 10.0, "main", *S)]
    res = SH.build(br, GN.make(br))
    (door,) = res["doors"]
    assert door["flush"] and door["h"] <= 1400 and res["checks"]["access"]["missing"] == 0
    shell, front = MB.split(res["arrays"])
    assert _closed(shell) and _closed(front)


def test_mounts_sit_on_solid_wall():
    br = row()
    res = SH.build(br, GN.make(br))
    mc = res["checks"]["mounts"]
    assert mc["mounts"] >= 1 and mc["on_glass"] == 0 and mc["no_wall"] == 0


def test_decals_on_the_band():
    br = row()
    br["building"]["style"] = {"era": "heritage", "grime": 0.95, "neon": 0.6}
    br["district"] = {"id": "d01", "name": "Test", "danger": 0.9, "greenery": 0.6}
    res = SH.build(br, GN.make(br))
    from assetgen.materials.atlases import DECAL_CELLS
    assert res["decals"]
    for d in res["decals"]:
        assert d["cell"] in DECAL_CELLS and d["w"] > 0 and d["h"] > 0
        assert 0 <= d["pos"][2] <= 4000 + 500


def test_every_street_front_slot_has_a_material():
    for slot in SY.SLOTS:
        master, s = CT.set_for(slot, None)
        assert master in CT.MASTERS, slot
    from assetgen.materials.atlases import DECAL_CELLS
    for cell in DECAL_CELLS:
        assert CT.set_for(f"decal.{cell}", None)[0] == "decal"


def test_small_city_fronts_doors_and_checks():
    out = small_assets()
    rep = small_assets_report()
    checks = {c["name"]: c for c in rep["checks"]}
    assert checks["asset_access"]["ok"], checks["asset_access"]
    assert checks["asset_mounts"]["ok"], checks["asset_mounts"]
    man = json.loads((out / "assets" / "manifest.json").read_text())
    fronts = 0
    for bid, r in man["buildings"].items():
        if r["front"]["triangles"]:
            fronts += 1
            assert r["front"]["node"] == f"{bid}.front"
            assert r["front"]["band_m"] > 0
        ents = {d["entrance"] for d in r["doors"] if d["entrance"] is not None}
        units = {d["unit"] for d in r["doors"] if d["unit"] is not None}
        assert len(ents) + len(units) == r["checks"]["doors"]["entrances"] + \
            r["checks"]["doors"]["units"], bid
    assert fronts > 0.8 * len(man["buildings"])
    con = json.loads((out / "assets" / "unreal_contribution.buildings.json").read_text())
    fe = [e for e in con["entries"] if e["kind"] == "building.front"]
    assert len(fe) == fronts
    for e in fe[:50]:
        assert e["collision"] == {"complex": True} and e["fallback_full"]
        assert e["ids"] == [e["key"][:-len(".front")]]
        for d in e["doors"]:
            assert d["id"].startswith(e["ids"][0] + ".door.")
    dec = [e for e in con["entries"] if e["kind"] == "decals"]
    if "decal.grime_ground" in con["materials"]:
        assert dec and all(not e["nanite"] and e["collision"] == {"none": True} for e in dec)
        for e in dec:
            for s in e["slots"]:
                assert con["materials"][s]["master"] == "decal"
                assert "Cell" in con["materials"][s]["scalars"]
    assert UC.asset_name("a.b") == "a_b"
