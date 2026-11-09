"""AG16's exporter changes on the venv side (citygen/unreal.py): a part or sign mesh that
several tiles' packs hold under one name imported once (`share_meshes`), and records as
components of one actor (`group_actors`: an entry's instanced parts, a building's street
front, a tile's small single-mesh pieces by kind), with what an import over an earlier one
does (`actor_hashes`, `actor_kinds`, `manifest_changes`)."""

import copy

from citygen import unreal as U


def _mesh(asset, h, collision=None, nanite=True):
    return {"asset": asset, "hash": h, "collision": collision or {"none": True},
            "nanite": nanite}


def _packs():
    def pk(part, use, folder, *meshes):
        return {"glb": f"{folder}.glb", "folder": folder, "part": part, "use": use,
                "meshes": {m["asset"]: m for m in meshes}}
    return {
        ("a", "BP/t0"): pk("buildings", "part", "Assets/BuildingsParts/t0",
                           _mesh("part_win_h1", "x0"), _mesh("part_fin_h2", "x0")),
        ("b", "BP/t1"): pk("buildings", "part", "Assets/BuildingsParts/t1",
                           _mesh("part_win_h1", "x1"), _mesh("part_ac_h3", "x1")),
        # the same name with other collision is another mesh
        ("c", "BP/t2"): pk("buildings", "part", "Assets/BuildingsParts/t2",
                           _mesh("part_win_h1", "x2", {"complex": True})),
        ("d", "S/t0"): pk("signs", "mesh", "Assets/Signs/t0", _mesh("sign_hab", "s0")),
        ("e", "S/t1"): pk("signs", "mesh", "Assets/Signs/t1", _mesh("sign_hab", "s0")),
        # whole meshes of other parts (buildings, streets) are never shared
        ("f", "B/t0"): pk("buildings", "mesh", "Assets/Buildings/t0", _mesh("bld", "b0")),
        ("g", "B/t1"): pk("buildings", "mesh", "Assets/Buildings/t1", _mesh("bld", "b1")),
    }


def test_share_meshes():
    packs = _packs()
    placed = [{"key": "k1", "mesh": "Assets/BuildingsParts/t1/part_win_h1", "hash": "h"},
              {"key": "k2", "mesh": "Assets/Signs/t1/sign_hab", "hash": "h"},
              {"key": "k3", "mesh": "Assets/BuildingsParts/t2/part_win_h1", "hash": "h"},
              {"key": "k4", "mesh": "Assets/Buildings/t1/bld", "hash": "h"}]
    before = copy.deepcopy(placed)
    assert U.share_meshes(packs, placed) == 2
    # the first pack by folder keeps the mesh, the others leave it out; a pack left empty
    # goes
    assert set(packs[("b", "BP/t1")]["meshes"]) == {"part_ac_h3"}
    assert ("e", "S/t1") not in packs
    assert set(packs[("c", "BP/t2")]["meshes"]) == {"part_win_h1"}
    assert set(packs[("g", "B/t1")]["meshes"]) == {"bld"}
    assert placed[0]["mesh"] == "Assets/BuildingsParts/t0/part_win_h1"
    assert placed[1]["mesh"] == "Assets/Signs/t0/sign_hab"
    # what points elsewhere is hashed again (an import over an earlier one updates it)
    assert placed[0]["hash"] != "h" and placed[1]["hash"] != "h"
    assert placed[2:] == before[2:]
    # the same packs, the same result
    p2, pl2 = _packs(), copy.deepcopy(before)
    U.share_meshes(p2, pl2)
    assert pl2 == placed


def _parts():
    actors = [{"key": "bld.a", "mesh": "m", "hash": "ha", "pivot": [1.0, 2.0, 0.0],
               "yaw_deg": 0.0, "category": "building", "type": "tower", "tile": "t+00+00"},
              {"key": "bld.a.front", "mesh": "f", "hash": "hf", "pivot": [1.0, 2.0, 0.0],
               "yaw_deg": 0.0, "category": "building", "type": "building.front",
               "tile": "t+00+00"},
              {"key": "sign.x", "mesh": "s1", "hash": "hs1", "pivot": [10.0, 20.0, 5.0],
               "yaw_deg": 90.0, "category": "prop_sign", "type": "sign_slot.shop_sign",
               "tile": "t+00+00"},
              {"key": "sign.y", "mesh": "s2", "hash": "hs2", "pivot": [30.0, 20.0, 5.0],
               "yaw_deg": 0.0, "category": "sign_billboard", "type": "sign_slot.billboard",
               "tile": "t+00+00"},
              {"key": "rs.e1n1", "mesh": "r", "hash": "hr", "pivot": [5.0, 5.0, 0.0],
               "yaw_deg": 0.0, "category": "road_street", "type": "street.road",
               "tile": "t+00+01"},
              {"key": "col.1", "mesh": "c", "hash": "hc", "pivot": [5.0, 5.0, 0.0],
               "yaw_deg": 0.0, "category": "structure_column", "type": "column",
               "tile": "t+00+01"}]
    base = {"pivot": [5.0, 6.0, 0.0], "yaw_deg": 30.0, "category": "prop_bench",
            "tile": "t+00+00", "district": "d01", "type": "part.x", "entry_type": "prop.bench"}
    insts = [{"key": "bld.a.part.win", "entry": "bld.a", "kind": "part.win", "hash": "p1",
              **base, "category": "building"},
             {"key": "bld.a.part.fin", "entry": "bld.a", "kind": "part.fin", "hash": "p2",
              **base, "category": "building"},
             {"key": "prop.bench.t.v0", "entry": "prop.bench.t", "kind": "v0", "hash": "p3",
              **base},
             {"key": "prop.bench.t.v1", "entry": "prop.bench.t", "kind": "v1", "hash": "p4",
              **base}]
    return actors, insts


MAN = {"tiles": [{"name": "t+00+00", "bounds": [0.0, 0.0, 256.0, 256.0]},
                 {"name": "t+00+01", "bounds": [0.0, 256.0, 256.0, 512.0]}]}


def test_group_actors():
    actors, insts = _parts()
    groups = U.group_actors(actors, insts, MAN)
    by = {a["key"]: a for a in actors}
    # parts on their entry's actor, a front on its building's, signs and street pieces on
    # their tile's group; a column stays an actor of its own
    assert [r["holder"] for r in insts] == ["bld.a", "bld.a", "prop.bench.t", "prop.bench.t"]
    assert by["bld.a.front"]["holder"] == "bld.a"
    assert by["sign.x"]["holder"] == by["sign.y"]["holder"] == "group.signs.t+00+00.c00"
    assert by["rs.e1n1"]["holder"] == "group.streets.t+00+01.c00"
    assert "holder" not in by["col.1"] and "holder" not in by["bld.a"]
    assert by["bld.a"]["members"] == 3 and by["bld.a"]["hash"] != "ha"
    gk = [g["key"] for g in groups]
    assert gk == ["group.signs.t+00+00.c00", "group.streets.t+00+01.c00", "prop.bench.t"]
    g = {x["key"]: x for x in groups}
    # an entry's group at its pivot; a tile's at the tile's middle
    assert g["prop.bench.t"]["pivot"] == [5.0, 6.0, 0.0] and g["prop.bench.t"]["members"] == 2
    assert g["prop.bench.t"]["type"] == "prop.bench"
    assert g["group.signs.t+00+00.c00"]["pivot"] == [32.0, 32.0, 0.0]
    assert g["group.signs.t+00+00.c00"]["category"] == "signs"
    # a member changing changes its holder's hash, and only that
    a2, i2 = _parts()
    i2[3]["hash"] = "p4b"
    [x for x in a2 if x["key"] == "sign.y"][0]["hash"] = "hs2b"
    g2 = {x["key"]: x for x in U.group_actors(a2, i2, MAN)}
    assert [x for x in a2 if x["key"] == "bld.a"][0]["hash"] == by["bld.a"]["hash"]
    assert g2["prop.bench.t"]["hash"] != g["prop.bench.t"]["hash"]
    assert g2["group.signs.t+00+00.c00"]["hash"] != g["group.signs.t+00+00.c00"]["hash"]
    assert g2["group.streets.t+00+01.c00"]["hash"] == g["group.streets.t+00+01.c00"]["hash"]


def test_a_street_piece_with_parts_keeps_its_actor():
    """A street piece with instanced parts of its own (an AG7 bridge's) is no member of its
    tile's group: its parts are components of its own actor, placed relative to its pivot."""
    actors, insts = _parts()
    br = {"key": "br.e1n1", "mesh": "b", "hash": "hb", "pivot": [40.0, 300.0, 0.0],
          "yaw_deg": 15.0, "category": "road_bridge", "type": "street.bridge",
          "tile": "t+00+01"}
    part = {"key": "br.e1n1.part.rail", "entry": "br.e1n1", "kind": "part.rail", "hash": "pr",
            "pivot": [40.0, 300.0, 0.0], "yaw_deg": 15.0, "category": "road_bridge",
            "tile": "t+00+01", "district": "", "type": "part.rail",
            "entry_type": "street.bridge"}
    actors.append(br)
    insts.append(part)
    groups = U.group_actors(actors, insts, MAN)
    assert "holder" not in br and br["members"] == 1
    assert part["holder"] == "br.e1n1"
    assert "br.e1n1" not in {g["key"] for g in groups}
    tops = {a["key"] for a in actors if not a.get("holder")} | {g["key"] for g in groups}
    assert all(r["holder"] in tops for r in actors + insts if r.get("holder"))


def test_grouped_manifest_changes():
    """An import with groups over one without: every part instancer, front, sign and street
    piece actor goes, a group actor comes for each entry with no mesh actor and each tile
    group, the mesh actors holding parts or fronts are updated."""
    actors, insts = _parts()
    old = {"tiles": [], "instances": [], "player_start": {"position": [0, 0, 0]},
           "stage2": {"replaced": [], "actors": copy.deepcopy(actors),
                      "instances": copy.deepcopy(insts)}}
    groups = U.group_actors(actors, insts, MAN)
    new = {"tiles": [], "instances": [], "player_start": {"position": [0, 0, 0]},
           "stage2": {"replaced": [], "actors": actors, "instances": insts, "groups": groups}}
    kinds = U.actor_kinds(new)
    assert kinds["bld.a"] == "mesh" and kinds["prop.bench.t"] == "group"
    assert kinds["col.1"] == "mesh" and kinds["group.signs.t+00+00.c00"] == "group"
    assert not {"bld.a.part.win", "bld.a.front", "sign.x", "rs.e1n1"} & set(kinds)
    ch = U.manifest_changes(old, new)
    assert ch["created"] == ["group.signs.t+00+00.c00", "group.streets.t+00+01.c00", "prop.bench.t"]
    assert ch["updated"] == ["bld.a"]
    assert ch["deleted"] == sorted([r["key"] for r in insts] +
                                   ["bld.a.front", "rs.e1n1", "sign.x", "sign.y"])
    # and the same manifest twice: nothing
    assert U.manifest_changes(new, copy.deepcopy(new)) == {"created": [], "updated": [],
                                                          "deleted": []}
