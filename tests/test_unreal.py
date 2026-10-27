"""M15: the Unreal export. The manifest, prototypes glTF and flat graphs need no Unreal; the
import test runs only where Unreal Engine 5 and Blender are installed."""

import copy
import json
import math
import shutil
import struct
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from citygen import blockout as BO
from citygen import exports as X
from citygen import unreal as U
from citygen.build import build_city
from citygen.cli import main
from citygen.validate import validate_spec

from conftest import SMALL


@pytest.fixture(scope="module")
def small():
    result = validate_spec(copy.deepcopy(SMALL))
    assert result.ok
    return build_city(result).model


def _blockout_files(m, out: Path) -> Path:
    """What `citygen blockout` writes before Blender runs (no glTF tiles)."""
    out.mkdir(parents=True, exist_ok=True)
    plan = BO.make_plan(m)
    (out / "blockout_plan.json").write_text(BO.plan_json(plan) + "\n", encoding="utf-8")
    (out / "tiles.json").write_text(json.dumps({"tile_size_m": BO.TILE_M,
                                                "tiles": plan["tiles"]}) + "\n")
    (out / "graphs.json").write_text(json.dumps(X.graphs(m)) + "\n")
    (out / "gameplay.json").write_text(json.dumps(X.gameplay(m)) + "\n")
    return out


@pytest.fixture(scope="module")
def build(small, tmp_path_factory):
    return _blockout_files(small, tmp_path_factory.mktemp("ue") / "build")


@pytest.fixture(scope="module")
def manifest(build):
    return U.build_manifest(build)


def test_manifest_covers_the_plan(build, manifest):
    man, meshes, graphs = manifest
    plan = json.loads((build / "blockout_plan.json").read_text())
    inst = [o for o in plan["objects"] if o["parts"][0]["k"] == "inst"]
    solid = [o for o in plan["objects"] if o["parts"][0]["k"] != "inst"]
    objs = [o for t in man["tiles"] for o in t["objects"]]
    assert sorted(o["key"] for o in objs) == sorted(o["name"] for o in solid)
    assert sorted(i["key"] for i in man["instances"]) == sorted(o["name"] for o in inst)
    keys = [o["key"] for o in objs] + [i["key"] for i in man["instances"]]
    assert len(keys) == len(set(keys)) and "player_start" not in keys
    for t in man["tiles"]:
        names = [o["asset"] for o in t["objects"]]
        assert len({n.lower() for n in names}) == len(names), t["name"]
        assert all(o["asset"] == o["key"].replace(".", "_") for o in t["objects"])
        assert t["glb"] is None          # no Blender in this test
    used = {m for o in objs for m in o["materials"]}
    assert used <= set(man["materials"])
    for p in man["materials"].values():
        assert all(0.0 <= c <= 1.0 for c in p["color"]) and 0.0 < p["roughness"] <= 1.0
    assert set(man["prototypes"]["kinds"]) == set(plan["prototypes"])
    assert {i["proto"] for i in man["instances"]} <= set(plan["prototypes"])
    assert all(len(i["ids"]) == i["count"] == len(i["xforms"]) for i in man["instances"])
    b = man["bounds"]
    x, y, z = man["player_start"]["position"]
    assert b[0] <= x <= b[2] and b[1] <= y <= b[3] and 0.5 < z < 20.0
    assert man["counts"]["objects"] == len(solid)
    assert man["counts"]["instances"] == sum(len(o["parts"][0]["pts"]) for o in inst)
    assert man["content_root"] == "/Game/CityGen/Testport" and man["slug"] == "testport"
    ids = [i for o in objs for i in o["ids"]]
    assert any(i.endswith(".bld") for i in ids)   # buildings carry their citygen ids
    # a point on every building's roof, inside its highest prism (the check traces onto it)
    by_name = {o["name"]: o for o in solid}
    blds = [o for o in objs if o["category"] in ("building", "landmark")]
    assert blds
    for o in blds:
        prisms = [p for p in by_name[o["key"]]["parts"] if p["k"] == "prism"]
        top = max(prisms, key=lambda p: p["z1"])
        x, y, z = o["roof"]
        assert z == top["z1"]
        assert Polygon(top["r"], top.get("h", [])).buffer(1e-6).contains(Point(x, y)), o["key"]


def test_inside_concave():
    """The interior point of a U and of a square with a square hole."""
    u = [[0, 0], [30, 0], [30, 30], [20, 30], [20, 10], [10, 10], [10, 30], [0, 30]]
    x, y = U._inside([u])
    assert Polygon(u).contains(Point(x, y))
    ring = [[0, 0], [20, 0], [20, 20], [0, 20]]
    hole = [[5, 5], [15, 5], [15, 15], [5, 15]]
    x, y = U._inside([ring, hole])
    assert Polygon(ring, [hole]).contains(Point(x, y))


def test_manifest_is_deterministic(build, manifest):
    again = U.build_manifest(build)
    assert json.dumps(again[0], sort_keys=True) == json.dumps(manifest[0], sort_keys=True)
    assert json.dumps(again[2], sort_keys=True) == json.dumps(manifest[2], sort_keys=True)


def test_hash_follows_the_object(build, manifest, tmp_path):
    """Changing one object changes its hash and its tile's, nothing else."""
    man = manifest[0]
    plan = json.loads((build / "blockout_plan.json").read_text())
    target = next(o for o in plan["objects"] if o["category"] == "building")
    target["parts"][0]["z1"] += 3.0
    other = tmp_path / "b2"
    shutil.copytree(build, other)
    (other / "blockout_plan.json").write_text(json.dumps(plan))
    man2 = U.build_manifest(other)[0]
    h1 = {o["key"]: o["hash"] for t in man["tiles"] for o in t["objects"]}
    h2 = {o["key"]: o["hash"] for t in man2["tiles"] for o in t["objects"]}
    assert [k for k in h1 if h1[k] != h2[k]] == [target["name"]]
    t1 = {t["name"]: t["hash"] for t in man["tiles"]}
    t2 = {t["name"]: t["hash"] for t in man2["tiles"]}
    assert [k for k in t1 if t1[k] != t2[k]] == [target["tile"]]
    assert [i["hash"] for i in man["instances"]] == [i["hash"] for i in man2["instances"]]
    assert U.manifest_changes(man, man2) == {"created": [], "updated": [target["name"]],
                                             "deleted": []}


def test_manifest_changes(build, manifest, tmp_path):
    """What an import over the last one would do: objects gone, new and changed, by key."""
    man = manifest[0]
    assert U.manifest_changes(man, man) == {"created": [], "updated": [], "deleted": []}
    hashes = U.actor_hashes(man)
    assert len(hashes) == man["counts"]["objects"] + man["counts"]["instance_actors"] + 4
    plan = json.loads((build / "blockout_plan.json").read_text())
    blds = [o for o in plan["objects"] if o["category"] == "building"]
    gone, moved = blds[0], blds[1]
    plan["objects"] = [o for o in plan["objects"] if o is not gone]
    for p in moved["parts"]:
        for k in ("r", "h"):
            if k in p:
                p[k] = [[x + 1.0, y] for x, y in p[k]] if k == "r" else \
                    [[[x + 1.0, y] for x, y in ring] for ring in p[k]]
    new = copy.deepcopy(next(o for o in plan["objects"] if o["category"] == "building"))
    new["name"] += ".copy"
    plan["objects"].append(new)
    other = tmp_path / "b2"
    shutil.copytree(build, other)
    (other / "blockout_plan.json").write_text(json.dumps(plan))
    ch = U.manifest_changes(man, U.build_manifest(other)[0])
    assert ch == {"created": [new["name"]], "updated": [moved["name"]],
                  "deleted": [gone["name"]]}


def _glb(path):
    data = path.read_bytes()
    magic, version, total = struct.unpack("<4sII", data[:12])
    n, kind = struct.unpack("<I4s", data[12:20])
    doc = json.loads(data[20:20 + n])
    m, kind2 = struct.unpack("<I4s", data[20 + n:28 + n])
    return magic, version, total, len(data), kind, kind2, doc, data[28 + n:28 + n + m]


def test_prototypes_glb(manifest, tmp_path):
    man, meshes, _ = manifest
    path = U.write_glb(meshes, man["materials"], tmp_path / "prototypes.glb")
    magic, version, total, size, kind, kind2, doc, blob = _glb(path)
    assert (magic, version, total, kind, kind2) == (b"glTF", 2, size, b"JSON", b"BIN\0")
    names = [n["name"] for n in doc["nodes"]]
    assert names == sorted(v["node"] for v in man["prototypes"]["kinds"].values())
    assert {m["name"] for m in doc["materials"]} <= set(man["materials"])
    acc = doc["accessors"]
    for mesh in doc["meshes"]:
        for p in mesh["primitives"]:
            pos, nrm, idx = (acc[p["attributes"]["POSITION"]], acc[p["attributes"]["NORMAL"]],
                             acc[p["indices"]])
            assert pos["count"] == nrm["count"] == idx["count"] and idx["count"] % 3 == 0
            v = doc["bufferViews"][nrm["bufferView"]]
            ns = struct.unpack(f"<{3 * nrm['count']}f",
                               blob[v["byteOffset"]:v["byteOffset"] + v["byteLength"]])
            for i in range(0, len(ns), 3):
                assert abs(math.sqrt(ns[i] ** 2 + ns[i + 1] ** 2 + ns[i + 2] ** 2) - 1) < 1e-4
    # a street light is 8 m tall: glTF y up
    sl = next(m for m in doc["meshes"] if m["name"] == "proto.street_light")
    top = max(acc[p["attributes"]["POSITION"]]["max"][1] for p in sl["primitives"])
    assert 7.9 < top < 8.1


def test_glb_axes(tmp_path):
    """citygen (x east, y north, z up) to glTF (x, z, -y), as Blender's export: a box east and
    north of the origin lies at +x and -z, upward faces point at +y."""
    mesh = U.prototype_mesh([{"k": "box", "m": "m", "c": [10.0, 20.0, 0.0],
                              "d": [2.0, 2.0, 4.0], "yaw": 0.0}])
    _, _, _, _, _, _, doc, blob = _glb(U.write_glb({"box": mesh}, {}, tmp_path / "b.glb"))
    pos = doc["accessors"][0]
    assert pos["min"] == pytest.approx([9.0, 0.0, -21.0])
    assert pos["max"] == pytest.approx([11.0, 4.0, -19.0])
    assert len(mesh.tris["m"]) == 12


def test_flat_graphs(build, manifest):
    _, _, g = manifest
    raw = json.loads((build / "graphs.json").read_text())
    assert g["lanes"]["count"] == len(raw["lanes"])
    assert g["walkways"]["count"] == len(raw["walkways"])
    assert g["transit"]["count"] == len(raw["transit_lines"]) + len(raw["stations"])
    for name, f in g.items():
        n = f["count"]
        assert len(f["ids"]) == len(f["kinds"]) == len(f["refs"]) == len(f["widths"]) == n
        assert len(f["point_start"]) == len(f["link_start"]) == n + 1
        assert f["point_start"] == sorted(f["point_start"])
        assert f["point_start"][-1] * 3 == len(f["points"])
        assert f["link_start"][-1] == len(f["links"])
        assert all(0 <= i < n for i in f["links"]), name
    lanes = g["lanes"]
    i = next(k for k, x in enumerate(raw["lanes"]) if x["successors"])
    succ = [lanes["ids"][j] for j in lanes["links"][lanes["link_start"][i]:
                                                   lanes["link_start"][i + 1]]]
    assert succ == [s for s in raw["lanes"][i]["successors"] if s in set(lanes["ids"])]


def test_cli_manifest_only(build, tmp_path):
    out = tmp_path / "b"
    shutil.copytree(build, out)
    assert main(["unreal", str(out), "--manifest-only"]) == 0
    for f in ("manifest.json", "prototypes.glb", "graphs.json"):
        assert (out / "unreal" / f).is_file()
    assert main(["unreal", str(tmp_path / "missing"), "--manifest-only"]) == 2


def test_prepare_project_and_engine(tmp_path):
    up = tmp_path / "P.uproject"
    up.write_text(json.dumps({"FileVersion": 3, "Plugins": [
        {"Name": "PythonScriptPlugin", "Enabled": False}]}))
    assert sorted(U.prepare_project(up)) == ["EditorScriptingUtilities", "PythonScriptPlugin"]
    assert U.prepare_project(up) == []
    plugins = json.loads(up.read_text())["Plugins"]
    assert {p["Name"] for p in plugins if p["Enabled"]} == set(U.PLUGINS)
    root = tmp_path / "UE_5.8"
    (root / "Engine" / "Binaries" / "Mac").mkdir(parents=True)
    assert U.find_engine(str(root)) == root
    assert U.find_engine(str(root / "Engine" / "Binaries" / "Mac")) == root
    assert U.find_engine(str(tmp_path / "nowhere")) is None


def test_names():
    assert U.pascal("Vesper Bay") == "VesperBay" and U.pascal("2077 City") == "City2077City"
    assert U.slug("Saltreach Free Port") == "saltreach_free_port"
    assert U.asset_name("d01.blk001.lot007.bld") == "d01_blk001_lot007_bld"
    assert U.asset_name("city.ground.t+00-03") == "city_ground_t+00-03"
    assert U.srgb_to_linear("#ffffff") == [1.0, 1.0, 1.0]


# --- in Unreal (where it is installed) ------------------------------------------------------

UE_ROOT = U.find_engine()
BLENDER = BO.find_blender()


@pytest.mark.skipif(UE_ROOT is None or BLENDER is None,
                    reason="Unreal Engine 5 or Blender not installed")
def test_unreal_import_small_city(small, tmp_path):
    """The small city into a fresh First Person project: imported, a second import changes
    nothing, a changed city updates only the actors of what changed, and in play-in-editor
    the cells stream, traces hit the ground and roofs, and the player walks a sidewalk."""
    build = tmp_path / "build"
    build.mkdir()
    (build / "city_model.json").write_text(small.to_json() + "\n", encoding="utf-8")
    rep = BO.run_blockout(build / "city_model.json", build, render=False)
    assert rep["passed"], rep
    proj = U.new_project(tmp_path / "Proj", UE_ROOT)
    first = U.import_city(build, proj)
    assert first["ok"], first.get("error")
    assert first["actors"]["created"] == first["actor_count"] == \
        first["counts"]["objects"] + first["counts"]["instance_actors"] + 4
    second = U.import_city(build, proj)
    assert second["ok"], second.get("error")
    assert second["actors"]["created"] == second["actors"]["updated"] == \
        second["actors"]["deleted"] == 0
    assert second["tiles_imported"] == 0 and second["dirty_packages"] == 0
    assert (second["actor_digest"], second["asset_digest"]) == \
        (first["actor_digest"], first["asset_digest"])
    # the city changed: one building 6 m taller, another gone; the import touches exactly the
    # actors whose content changed and leaves the rest as they were
    m2 = small.model_copy(deep=True)
    blds = [b for b in m2.buildings if not b.landmark]
    taller, gone = blds[0].id, blds[1].id
    blds[0].masses[-1].z1_m += 6.0
    m2.buildings = [b for b in m2.buildings if b.id != gone]
    build2 = tmp_path / "build2"
    build2.mkdir()
    (build2 / "city_model.json").write_text(m2.to_json() + "\n", encoding="utf-8")
    assert BO.run_blockout(build2 / "city_model.json", build2, render=False)["passed"]
    third = U.import_city(build2, proj)
    assert third["ok"], third.get("error")
    want = U.manifest_changes(json.loads((build / "unreal" / "manifest.json").read_text()),
                              json.loads((build2 / "unreal" / "manifest.json").read_text()))
    assert taller in want["updated"] and gone in want["deleted"]
    assert {k: third["keys"][k] for k in want} == want
    assert third["actors"]["unchanged"] == \
        third["actor_count"] - len(want["created"]) - len(want["updated"])
    chk = U.check_city(build2, proj)
    assert chk["ok"], chk
