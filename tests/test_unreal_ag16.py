"""AG16's exporter changes on the venv side (citygen/unreal.py): a part or sign mesh that
several tiles' packs hold under one name imported once (`share_meshes`), and an entry's
instanced parts as components of one actor (`group_parts`), with what an import over an
earlier one does (`actor_hashes`, `actor_kinds`, `manifest_changes`)."""

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
               "yaw_deg": 0.0}]
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


def test_group_parts():
    actors, insts = _parts()
    groups = U.group_parts(actors, insts)
    # parts of an entry with a mesh actor go on it; the others get a group actor
    assert [r["holder"] for r in insts] == ["bld.a", "bld.a", "prop.bench.t", "prop.bench.t"]
    assert actors[0]["parts"] == 2 and actors[0]["hash"] != "ha"
    assert [g["key"] for g in groups] == ["prop.bench.t"]
    g = groups[0]
    assert g["pivot"] == [5.0, 6.0, 0.0] and g["yaw_deg"] == 30.0 and g["parts"] == 2
    assert g["type"] == "prop.bench" and g["category"] == "prop_bench"
    # a part changing changes its holder's hash, and only that
    a2, i2 = _parts()
    i2[3]["hash"] = "p4b"
    g2 = U.group_parts(a2, i2)
    assert a2[0]["hash"] == actors[0]["hash"] and g2[0]["hash"] != g["hash"]


def test_grouped_manifest_changes():
    """An import with groups over one without: every part instancer goes, a group actor
    comes for each entry with no mesh actor, the mesh actors holding parts are updated."""
    actors, insts = _parts()
    old = {"tiles": [], "instances": [], "player_start": {"position": [0, 0, 0]},
           "stage2": {"replaced": [], "actors": copy.deepcopy(actors),
                      "instances": copy.deepcopy(insts)}}
    groups = U.group_parts(actors, insts)
    new = {"tiles": [], "instances": [], "player_start": {"position": [0, 0, 0]},
           "stage2": {"replaced": [], "actors": actors, "instances": insts, "groups": groups}}
    kinds = U.actor_kinds(new)
    assert kinds["bld.a"] == "mesh" and kinds["prop.bench.t"] == "group"
    assert "bld.a.part.win" not in kinds
    ch = U.manifest_changes(old, new)
    assert ch["created"] == ["prop.bench.t"]
    assert ch["updated"] == ["bld.a"]
    assert ch["deleted"] == sorted(r["key"] for r in insts)
    # and the same manifest twice: nothing
    assert U.manifest_changes(new, copy.deepcopy(new)) == {"created": [], "updated": [],
                                                          "deleted": []}
