"""M15: the Unreal export. The manifest, prototypes glTF and flat graphs need no Unreal; the
import test runs only where Unreal Engine 5 and Blender are installed."""

import copy
import json
import math
import shutil
import struct
from pathlib import Path

import pytest
import shapely
from shapely.geometry import Point, Polygon

from citygen import blockout as BO
from citygen import edit as E
from citygen import exports as X
from citygen import geom as G
from citygen import unreal as U
from citygen.build import build_city
from citygen.cli import main
from citygen.validate import validate_spec

from conftest import SMALL
from test_terrain import hilly_data


REGEN = "Old Quarter"     # the small city's district regenerated (M10, `build --district`)


@pytest.fixture(scope="module")
def small_built():
    data = copy.deepcopy(SMALL)
    result = validate_spec(data)
    assert result.ok
    return data, build_city(result)


@pytest.fixture(scope="module")
def small(small_built):
    return small_built[1].model


@pytest.fixture(scope="module")
def regenerated(small_built):
    """The small city with REGEN regenerated at a new seed, as `citygen build --district`."""
    data, b = small_built
    r, _ = E.regenerate(E.new_state(data, b), b.model, REGEN)
    assert all(c.passed for c in r.checks), [c.id for c in r.checks if not c.passed]
    return r.model


def _blockout_files(m, out: Path) -> Path:
    """What `citygen blockout` writes before Blender runs (no glTF tiles)."""
    out.mkdir(parents=True, exist_ok=True)
    plan = BO.make_plan(m)
    (out / "blockout_plan.json").write_text(BO.plan_json(plan) + "\n", encoding="utf-8")
    (out / "tiles.json").write_text(json.dumps({"tile_size_m": BO.TILE_M,
                                                "tiles": plan["tiles"]}) + "\n")
    ground = BO._Ground(m) if m.terrain is not None else None     # as run_blockout does
    (out / "graphs.json").write_text(json.dumps(X.graphs(m, ground)) + "\n")
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


def test_district_regeneration_changes_only_its_neighborhood(small, regenerated, manifest,
                                                             tmp_path):
    """A regenerated district changes only objects of the tiles within 250 m of it (M10 keeps
    every entity farther away byte for byte) and no building of another district."""
    man = manifest[0]
    new = U.build_manifest(_blockout_files(regenerated, tmp_path / "regen"))[0]
    ch = U.manifest_changes(man, new)
    did = next(d.id for d in small.districts if d.name == REGEN)
    poly = G.from_model_poly(next(d for d in small.districts if d.id == did).polygon)
    ts = man["tile_size_m"]

    def tile_box(name):
        ix, iy = int(name[1:4]), int(name[4:7])
        return shapely.box(ix * ts, iy * ts, (ix + 1) * ts, (iy + 1) * ts)

    tile = {o["key"]: t["name"] for m in (man, new) for t in m["tiles"] for o in t["objects"]}
    tile.update({i["key"]: i["tile"] for m in (man, new) for i in m["instances"]})
    changed = [k for v in ch.values() for k in v]
    assert any(k.startswith(did + ".") and k.endswith(".bld") for k in ch["deleted"])
    assert any(k.startswith(did + ".") and k.endswith(".bld") for k in ch["created"])
    far = [k for k in changed if k in tile and tile_box(tile[k]).distance(poly) > 250.0]
    assert not far, far[:5]
    kept = [t["name"] for t in man["tiles"] if tile_box(t["name"]).distance(poly) > 250.0]
    assert kept      # the test city has tiles far enough to stay as they were
    # no building of another district changed (the district is close to half this city)
    others = [k for k in changed if k.endswith(".bld") and not k.startswith(did + ".")]
    assert not others, others[:5]
    blds = [k for k in U.actor_hashes(new) if k.endswith(".bld") and not k.startswith(did)]
    assert blds


@pytest.fixture(scope="module")
def hilly():
    res = validate_spec(hilly_data())
    assert res.ok, res.issues
    return build_city(res).model


def test_terrain_city(hilly, tmp_path):
    """M13: a terrain city's graphs carry absolute heights (sidewalks and lanes over their
    road's grade line, the rest over the finished ground), the player start stands on the
    ground, and the manifest keys the terrain's pieces by their stable ids: one actor per
    retaining wall, bored tunnel and terrain viaduct column, the ground a heightfield per
    tile, plinths in their building's actor."""
    ground = BO._Ground(hilly)
    rel, g = X.graphs(hilly), X.graphs(hilly, ground)
    assert g["heights"] == "absolute" and "heights" not in rel
    walks = {w.id: w for w in hilly.walkways}
    side = [w for w in g["walkways"] if walks[w["id"]].attrs.get("segment") in ground.segs]
    assert side
    for w in side[:50]:
        sid = walks[w["id"]].attrs["segment"]
        for (x, y, z), p in zip(w["line"], walks[w["id"]].line):
            assert abs(z - (p[2] + ground.road(sid, x, y))) < 0.011
    assert any(abs(p[2] - q[2]) > 1.0 for w in g["walkways"]
               for p, q in zip(w["line"], walks[w["id"]].line))
    build = _blockout_files(hilly, tmp_path / "b")
    man = U.build_manifest(build)[0]
    objs = {o["key"]: o for t in man["tiles"] for o in t["objects"]}
    x, y, z = man["player_start"]["position"]
    assert 0.5 < z - ground.at(x, y) < 20.0
    walls = {s.id for s in hilly.structures if s.kind == "retaining_wall"}
    keyed = [k for k, o in objs.items() if o["category"] == "retaining_wall"]
    assert keyed and set(keyed) <= walls and all(objs[k]["ids"] == [k] for k in keyed)
    for t in hilly.tunnels:
        if t.kind == "bored":
            assert objs[f"{t.id}.tunnel"]["ids"] == [t.id]
    cols = [s.id for s in hilly.structures if ".tvcol." in s.id]
    assert all(c in objs for c in cols)
    grounds = [o for o in objs.values() if o["category"] == "ground"]
    assert grounds and all(o["key"].startswith("city.ground.t") for o in grounds)
    assert any("plinth" in o["materials"] for o in objs.values() if o["category"] == "building")
    assert "plinth" in man["materials"] and "retaining_wall" in man["materials"]


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
    assert not [k for k in g if "levels" in g[k]] and "decks" not in manifest[0]  # (M14)
    assert not [o for t in manifest[0]["tiles"] for o in t["objects"] if "level" in o]
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


def test_levels():
    """M14: a deck's streets, slab and ramps and the buildings on it stand on its level; a
    road's own level (M7's viaducts 1 and 2, M9's tunnels -1) is not a deck's."""
    assert U._level("deck_road", {}) == 1 and U._level("deck_slab", {"level": 1}) == 1
    assert U._level("deck_ramp", {"level": 0}) == 1
    assert U._level("building", {"level": 1}) == 1 and U._level("building", {}) == 0
    assert U._level("elevated", {"level": 2}) == 0 and U._level("bridge", {"level": 1}) == 0
    assert U._level("tunnel_road", {"level": -1}) == 0


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
    assert sorted(U.prepare_project(up)) == ["EditorScriptingUtilities", "GeometryScripting",
                                             "PythonScriptPlugin"]
    assert U.prepare_project(up) == []
    plugins = json.loads(up.read_text())["Plugins"]
    assert {p["Name"] for p in plugins if p["Enabled"]} == set(U.PLUGINS)
    root = tmp_path / "UE_5.8"
    (root / "Engine" / "Binaries" / "Mac").mkdir(parents=True)
    assert U.find_engine(str(root)) == root
    assert U.find_engine(str(root / "Engine" / "Binaries" / "Mac")) == root
    assert U.find_engine(str(tmp_path / "nowhere")) is None


def test_startup_map(tmp_path):
    """The imported city becomes the project's startup and default map; the rest of
    DefaultEngine.ini stays as it was (a Windows one's line endings too)."""
    up = tmp_path / "P" / "P.uproject"
    (tmp_path / "P" / "Config").mkdir(parents=True)
    ini = tmp_path / "P" / "Config" / "DefaultEngine.ini"
    ini.write_bytes(b"[/Script/EngineSettings.GameMapsSettings]\r\n"
                    b"EditorStartupMap=/Game/FirstPerson/Lvl_FirstPerson.Lvl_FirstPerson\r\n"
                    b"bUseSplitscreen=True\r\n[/Script/Engine.RendererSettings]\r\n"
                    b"r.Lumen=1\r\n")
    level = "/Game/CityGen/VesperBay/Maps/VesperBay"
    assert U.set_startup_map(up, level)
    text = ini.read_bytes().decode()
    assert text.count("\r\n") == text.count("\n") == 6
    lines = text.split("\r\n")
    assert lines[:4] == ["[/Script/EngineSettings.GameMapsSettings]",
                         "GameDefaultMap=/Game/CityGen/VesperBay/Maps/VesperBay.VesperBay",
                         "EditorStartupMap=/Game/CityGen/VesperBay/Maps/VesperBay.VesperBay",
                         "bUseSplitscreen=True"]
    assert lines[4:6] == ["[/Script/Engine.RendererSettings]", "r.Lumen=1"]
    assert not U.set_startup_map(up, level)
    ini.write_text("[/Script/Engine.RendererSettings]\nr.Lumen=1\n")
    assert U.set_startup_map(up, level)
    assert ini.read_text().endswith("[/Script/EngineSettings.GameMapsSettings]\n"
                                    "EditorStartupMap=/Game/CityGen/VesperBay/Maps/VesperBay."
                                    "VesperBay\nGameDefaultMap=/Game/CityGen/VesperBay/Maps/"
                                    "VesperBay.VesperBay\n")


def test_play_flags(tmp_path):
    """`--play`, `--fly-speed`, `--view-range`, `--no-startup` and `--no-hlod` parse; a play mode
    that is not one is refused before any editor runs."""
    from citygen.cli import build_parser
    a = build_parser().parse_args(["unreal", "B", "P.uproject"])
    assert (a.play, a.fly_speed, a.view_range, a.no_startup, a.no_hlod) == \
        ("fly", U.FLY_SPEED_M_S, U.VIEW_M, False, False)
    a = build_parser().parse_args(["unreal", "B", "P.uproject", "--play", "walk",
                                   "--fly-speed", "80", "--no-startup", "--no-hlod"])
    assert (a.play, a.fly_speed, a.no_startup, a.no_hlod) == ("walk", 80.0, True, True)
    with pytest.raises(SystemExit):
        build_parser().parse_args(["unreal", "B", "--play", "swim"])
    with pytest.raises(ValueError):
        U.import_city(tmp_path, tmp_path / "P.uproject", play="swim")


def test_names():
    assert U.pascal("Vesper Bay") == "VesperBay" and U.pascal("2077 City") == "City2077City"
    assert U.slug("Saltreach Free Port") == "saltreach_free_port"
    assert U.asset_name("d01.blk001.lot007.bld") == "d01_blk001_lot007_bld"
    assert U.asset_name("city.ground.t+00-03") == "city_ground_t+00-03"
    assert U.srgb_to_linear("#ffffff") == [1.0, 1.0, 1.0]


# --- stage 2 (assetgen's layer) -----------------------------------------------------------

def _dump(man) -> str:
    return json.dumps(man, sort_keys=True)


def _with_contributions(build: Path, out: Path, contribs: dict) -> Path:
    """A copy of `build` with BUILD/assets/unreal_contribution.<part>.json for each part."""
    shutil.copytree(build, out)
    (out / "assets").mkdir(exist_ok=True)
    for part, c in contribs.items():
        (out / "assets" / f"unreal_contribution.{part}.json").write_text(json.dumps(c))
    return out


def _fake(man, graphs_json):
    """Two small contributions in AG1's and AG7's format over the blockout `man`: two
    buildings by their blockout keys, a road piece replacing a joined road object, a
    container stack of parts only, a sky tube's glass as a LOD chain, a walkway on a deck."""
    objs = [o for t in man["tiles"] for o in t["objects"]]
    blds = sorted(o["key"] for o in objs if o["category"] == "building")[:2]
    road = sorted(o["key"] for o in objs if ".road_" in o["key"])[0]
    tile = next(t["name"] for t in man["tiles"] for o in t["objects"] if o["key"] == blds[0])
    box = {"center": [0.0, 0.0, 5.0], "extent": [4.0, 3.0, 5.0], "yaw_deg": 0.0}
    prism = {"z": [0.0, 12.0], "ring": [[-5.0, -4.0], [5.0, -4.0], [0.0, 6.0]]}
    buildings = {"version": 1, "stage": "assetgen", "part": "buildings", "layer": 2,
                 "materials": {"brick": {"master": "facade", "color": [0.2, 0.07, 0.04],
                                         "roughness": 0.9, "metallic": 0.0, "tint_cpd": 0},
                               "patch_tarp": {"master": "facade", "color": [0.03, 0.1, 0.25],
                                              "roughness": 0.8, "metallic": 0.0,
                                              "tint_cpd": 20, "tint_scale": 3.1,
                                              "tint_times_color": True}},
                 "entries": [{"key": k, "kind": "building", "hash": f"h{i}", "replaces": [],
                              "glb": f"tiles/{tile}.glb", "node": f"{k}.shell",
                              "asset": U.asset_name(f"{k}.shell"), "pivot": [10.0 * i, 5.0, 0.0],
                              "yaw_deg": 0.0, "nanite": True, "triangles": 100,
                              "slots": ["brick"], "cpd": [0.5] * 23,
                              "collision": {"simple": [box], "convex": [prism]},
                              "proxy": {"glb": f"proxies/{tile}.glb", "node": f"{k}.proxy",
                                        "asset": U.asset_name(k) + "_proxy", "triangles": 12},
                              "parts": [], "tags": {"cg.type": "building.test",
                                                    "cg.tile": tile}}
                             for i, k in enumerate(blds)]}
    walk = next(w for w in graphs_json["walkways"] if w["kind"] == "sidewalk")
    lifted = [[p[0], p[1], 9.2] for p in walk["line"]]
    streets = {"version": 1, "stage": "assetgen", "part": "streets", "layer": 2,
               "materials": {"asphalt.street": {"master": "road", "color": [0.2, 0.2, 0.22],
                                                "roughness": 0.88, "metallic": 0.0}},
               "entries": [
                   {"key": "rs.test1", "kind": "street.road", "hash": "s1", "replaces": [road],
                    "glb": "streets/t+00+00.glb", "node": "rs.test1", "asset": "rs_test1",
                    "pivot": [1.0, 2.0, 0.0], "yaw_deg": 0.0, "nanite": True,
                    "triangles": 40, "slots": ["asphalt.street"],
                    "collision": {"complex": True}, "tile": "t+00+00"},
                   {"key": "site.test.el", "kind": "street.site.container_stack",
                    "hash": "s2", "replaces": [], "glb": "streets/t+00+00.glb",
                    "node": "site.test.el", "asset": "site_test_el", "pivot": [3.0, 4.0, 0.0],
                    "yaw_deg": 0.0, "nanite": True, "triangles": 0, "slots": [],
                    "collision": {"complex": True}, "tile": "t+00+00",
                    "parts": [{"kind": "part.container.c3", "glb": "streets/parts.glb",
                               "node": "part.container.c3", "asset": "part_container_c3",
                               "count": 2, "triangles": 132,
                               "xforms": [[0.0, 0.0, 0.0, 0.0], [0.0, 2.6, 0.0, 90.0]]}]},
                   {"key": "tl.test.tb.glass", "kind": "street.transit.tube.glass",
                    "hash": "s3", "replaces": [], "glb": "streets/t+00+00.glb",
                    "node": "tl.test.tb.glass.lod0", "asset": "tl_test_tb_glass",
                    "pivot": [5.0, 6.0, 0.0], "yaw_deg": 0.0, "nanite": False,
                    "triangles": 24, "slots": [], "collision": {"none": True},
                    "tile": "t+00+00",
                    "lods": [{"node": f"tl.test.tb.glass.lod{k}", "screen_size": s,
                              "triangles": 24 >> k} for k, s in enumerate((1.0, 0.25, 0.06))]}],
               "graphs": {"walkways": {walk["id"]: lifted}}}
    return {"buildings": buildings, "streets": streets}, blds, road, walk, lifted


def test_without_assets_the_manifest_is_the_blockouts(build, manifest, tmp_path):
    """A build without stage 2 (no assets folder, an empty one, or --blockout-only) gives
    exactly the blockout's manifest and graphs."""
    man, _, graphs = manifest
    assert "stage2" not in man and "actors" not in man["counts"]
    empty = tmp_path / "empty"
    shutil.copytree(build, empty)
    (empty / "assets").mkdir()
    again = U.build_manifest(empty)
    assert _dump(again[0]) == _dump(man) and _dump(again[2]) == _dump(graphs)
    fake = _fake(man, json.loads((build / "graphs.json").read_text()))[0]
    staged = _with_contributions(build, tmp_path / "staged", fake)
    only = U.build_manifest(staged, assets=False)
    assert _dump(only[0]) == _dump(man) and _dump(only[2]) == _dump(graphs)
    assert "stage2" in U.build_manifest(staged)[0]
    assert main(["unreal", str(staged), "--manifest-only", "--blockout-only"]) == 0
    written = json.loads((staged / "unreal" / "manifest.json").read_text())
    assert _dump(written) == _dump(man)


def test_stage2_layer(build, manifest, tmp_path):
    """Stage 2 over the blockout: its entries' actors at their pivots, the blockout actors of
    their keys and `replaces` dropped, parts as instanced actors per entry and kind, a LOD
    chain, materials per part and slot, the walkway lines; `manifest_changes` from the
    blockout alone is exactly that."""
    man, _, graphs = manifest
    raw = json.loads((build / "graphs.json").read_text())
    fake, blds, road, walk, lifted = _fake(man, raw)
    staged = _with_contributions(build, tmp_path / "staged", fake)
    m2, _, g2 = U.build_manifest(staged)
    s2 = m2["stage2"]
    assert [f["file"] for f in s2["files"]] == ["assets/unreal_contribution.buildings.json",
                                                "assets/unreal_contribution.streets.json"]
    assert s2["replaced"] == sorted(blds + [road])
    keys = [a["key"] for a in s2["actors"]]
    assert keys == sorted(blds + ["rs.test1", "tl.test.tb.glass"])
    assert [a["key"] for a in s2["instances"]] == ["site.test.el.part.container.c3"]
    assert s2["instances"][0]["xforms"][1] == [0.0, 2.6, 0.0, 90.0]
    a = {x["key"]: x for x in s2["actors"]}
    assert a[blds[1]]["pivot"] == [10.0, 5.0, 0.0] and len(a[blds[1]]["cpd"]) == 23
    assert a[blds[0]]["category"] == "building" and a[blds[0]]["type"] == "building.test"
    assert a["rs.test1"]["category"] == next(
        o["category"] for t in man["tiles"] for o in t["objects"] if o["key"] == road)
    assert a["tl.test.tb.glass"]["no_collision"] and "no_collision" not in a["rs.test1"]
    # one mesh per shell, proxy, street and part node, named as Interchange names the node
    packs = {p["folder"]: p for p in s2["packs"]}
    shells = next(p for f, p in packs.items() if f.startswith("Assets/Buildings/"))
    assert [m["asset"] for m in shells["meshes"]] == sorted(U.asset_name(f"{k}.shell")
                                                           for k in blds)
    assert shells["meshes"][0]["collision"]["convex"] == [fake["buildings"]["entries"][0][
        "collision"]["convex"][0]]
    proxies = next(p for f, p in packs.items() if f.startswith("Assets/BuildingsProxies/"))
    assert all(not m["nanite"] and m["collision"] == {"none": True} for m in proxies["meshes"])
    street = packs["Assets/Streets/t+00+00"]
    assert [m["asset"] for m in street["meshes"]] == ["rs_test1"] + [
        f"tl_test_tb_glass_lod{k}" for k in range(3)]
    assert all(p["glb"] is None for p in s2["packs"])       # (no packs in this test)
    (ch,) = s2["lod_chains"]
    assert ch["mesh"] == "Assets/Streets/t+00+00/tl_test_tb_glass"
    assert [lo["screen_size"] for lo in ch["lods"]] == [1.0, 0.25, 0.06]
    # materials: per part and slot; AG7's sRGB colors made linear, AG1's kept
    mats = s2["materials"]
    assert mats["buildings.brick"]["color"] == [0.2, 0.07, 0.04]
    assert mats["buildings.brick"]["tint_cpd"] == 0 and mats["streets.asphalt.street"][
        "tint_cpd"] == -1
    assert mats["buildings.patch_tarp"]["tint_times_color"] and \
        mats["buildings.patch_tarp"]["tint_scale"] == 3.1
    assert mats["streets.asphalt.street"]["color"] == pytest.approx(
        [0.0331, 0.0331, 0.0397], abs=1e-4)
    assert s2["masters"] == ["facade", "road"]
    # the walkway on the deck, where graphs.json has it at z 0
    i = g2["walkways"]["ids"].index(walk["id"])
    ps = g2["walkways"]["point_start"]
    pts = g2["walkways"]["points"][3 * ps[i]:3 * ps[i + 1]]
    assert pts[2::3] == [9.2] * len(lifted)
    assert g2["walkways"]["hash"] != graphs["walkways"]["hash"]
    assert g2["lanes"] == graphs["lanes"]
    # what an import over the blockout's does
    ch = U.manifest_changes(man, m2)
    assert ch == {"created": sorted(["rs.test1", "tl.test.tb.glass",
                                     "site.test.el.part.container.c3"]),
                  "updated": sorted(blds), "deleted": [road]}
    assert m2["counts"]["actors"] == len(U.actor_hashes(m2)) == \
        len(U.actor_hashes(man)) + 2
    assert U.manifest_changes(m2, man) == {"created": [road], "updated": sorted(blds),
                                           "deleted": ch["created"]}
    # an entry's hash moves only its actor
    fake["buildings"]["entries"][1]["hash"] = "h9"
    m3 = U.build_manifest(_with_contributions(build, tmp_path / "s3", fake))[0]
    assert U.manifest_changes(m2, m3) == {"created": [], "updated": [blds[1]],
                                          "deleted": []}


def test_stage2_skybridge_links(build, manifest, tmp_path):
    """AG4: a skybridge's entry (assetgen's `connections` part) is an actor at its pivot and
    yaw that carries what it joins (`links`, the importer's `cg.link=` tags) in its hash,
    in place of the blockout skybridge of its key."""
    man, _, _ = manifest
    objs = [o for t in man["tiles"] for o in t["objects"]]
    sky = sorted(o["key"] for o in objs if o["category"] == "skybridge")
    key = sky[0] if sky else "sb.test"
    tile = next((t["name"] for t in man["tiles"] for o in t["objects"] if o["key"] == key),
                man["tiles"][0]["name"])
    entry = {"key": key, "kind": "skybridge", "hash": "s1", "replaces": [],
             "glb": f"connections/{tile}.glb", "node": key, "asset": U.asset_name(key),
             "pivot": [1.0, 2.0, 0.0], "yaw_deg": 30.0, "nanite": True, "triangles": 40,
             "slots": ["bridge_deck"], "collision": {"complex": True}, "cpd": [],
             "ids": [key], "links": ["building:a.bld", "building:b.bld", "walkway:w1"],
             "tags": {"cg.type": "skybridge.enclosed", "cg.district": "", "cg.tile": tile}}
    conn = {"version": 1, "stage": "assetgen", "part": "connections", "layer": 2,
            "materials": {"bridge_deck": {"master": "facade", "color": [0.3, 0.3, 0.3],
                                          "roughness": 0.8, "metallic": 0.0,
                                          "tint_cpd": None}},
            "entries": [entry]}
    m2 = U.build_manifest(_with_contributions(build, tmp_path / "s", {"connections": conn}))[0]
    s2 = m2["stage2"]
    a = next(x for x in s2["actors"] if x["key"] == key)
    assert a["links"] == entry["links"] and a["yaw_deg"] == 30.0 and a["pivot"] == [1.0, 2.0,
                                                                                     0.0]
    assert a["type"] == "skybridge.enclosed"
    assert (key in s2["replaced"]) == bool(sky)
    assert "connections.bridge_deck" in s2["materials"]
    m3 = U.build_manifest(_with_contributions(build, tmp_path / "s3", {"connections": dict(
        conn, entries=[dict(entry, links=entry["links"][:2])])}))[0]
    assert U.manifest_changes(m2, m3) == {"created": [], "updated": [key], "deleted": []}
    src = (Path(U.__file__).parent / "ue" / "import_city.py").read_text()
    assert 'f"cg.link={x}"' in src and 'r.get("links", [])' in src


def test_stage2_refuses(build, manifest, tmp_path):
    """A key in two contributions, a tint index no master reads, a contribution of another
    version or layer."""
    man = manifest[0]
    fake = _fake(man, json.loads((build / "graphs.json").read_text()))[0]
    dup = copy.deepcopy(fake)
    dup["streets"]["entries"].append(copy.deepcopy(dup["buildings"]["entries"][0]))
    with pytest.raises(ValueError, match="in assets/unreal_contribution.buildings.json and"):
        U.build_manifest(_with_contributions(build, tmp_path / "dup", dup))
    bad = copy.deepcopy(fake)
    bad["buildings"]["materials"]["brick"]["tint_cpd"] = 5
    with pytest.raises(ValueError, match="tint_cpd 5"):
        U.build_manifest(_with_contributions(build, tmp_path / "tint", bad))
    old = copy.deepcopy(fake)
    old["streets"]["layer"] = 3
    with pytest.raises(ValueError, match="layer 2"):
        U.build_manifest(_with_contributions(build, tmp_path / "layer", old))


def test_stage2_textures(build, manifest, tmp_path):
    """AG6: textures by name with their pixel hashes (the shared library in Core, the
    city's pages in the city's folder), materials with texture, scalar and vector
    parameters, an entry's era materials as its actor's overrides; a texture's pixels move
    its materials, not the actors; an entry's material map moves only its actor; a material
    naming a texture no contribution lists, or a texture of an unknown kind, is refused."""
    man = manifest[0]
    fake, blds = _fake(man, json.loads((build / "graphs.json").read_text()))[:2]
    b = fake["buildings"]
    b["textures"] = {
        "set.brick_heritage.base": {"file": "library/sets/brick_heritage_base.png",
                                    "pixels_sha256": "a" * 64, "size": [1024, 1024],
                                    "srgb": True, "kind": "color"},
        "set.brick_heritage.normal": {"file": "library/sets/brick_heritage_normal.png",
                                      "pixels_sha256": "b" * 64, "size": [1024, 1024],
                                      "srgb": False, "kind": "normal"},
        "city.signs_wide_0": {"file": "textures/signs_wide_0.png", "pixels_sha256": "c" * 64,
                              "size": [4096, 1024], "srgb": True, "kind": "color"}}
    b["materials"]["brick@heritage"] = dict(
        b["materials"]["brick"], slot="brick",
        textures={"BaseTex": "set.brick_heritage.base",
                  "NormalTex": "set.brick_heritage.normal"},
        scalars={"TileM": 2.0, "Textured": 1.0}, vectors={"RefColor": [0.2, 0.08, 0.05]})
    b["entries"][0]["materials"] = {"brick": "brick@heritage"}
    b["entries"][0]["cpd"] = [0.5] * 30
    m2 = U.build_manifest(_with_contributions(build, tmp_path / "t1", fake))[0]
    s2 = m2["stage2"]
    t = s2["textures"]
    assert sorted(t) == sorted(b["textures"]) and s2["counts"]["textures"] == 3
    assert t["set.brick_heritage.base"]["folder"] == "/Game/CityGen/Core/Textures"
    assert t["city.signs_wide_0"]["folder"] == m2["content_root"] + "/Assets/Textures"
    assert t["set.brick_heritage.normal"]["file"] == \
        "assets/library/sets/brick_heritage_normal.png"
    assert t["set.brick_heritage.normal"]["kind"] == "normal" and \
        not t["set.brick_heritage.normal"]["srgb"]
    mat = s2["materials"]["buildings.brick@heritage"]
    assert mat["slot"] == "brick" and mat["key"] == "brick@heritage"
    assert mat["textures"]["BaseTex"] == {"texture": "set.brick_heritage.base",
                                          "hash": "a" * 16}
    assert mat["scalars"] == {"Textured": 1.0, "TileM": 2.0}
    assert "textures" not in s2["materials"]["buildings.brick"]
    a = {x["key"]: x for x in s2["actors"]}
    assert a[blds[0]]["materials"] == {"brick": "MI_" + U.asset_name("buildings.brick@heritage")}
    assert "materials" not in a[blds[1]] and len(a[blds[0]]["cpd"]) == 30
    # new pixels: the materials that read them change, no actor does
    f2 = copy.deepcopy(fake)
    f2["buildings"]["textures"]["set.brick_heritage.base"]["pixels_sha256"] = "d" * 64
    m3 = U.build_manifest(_with_contributions(build, tmp_path / "t2", f2))[0]
    assert U.manifest_changes(m2, m3) == {"created": [], "updated": [], "deleted": []}
    assert m3["stage2"]["materials"]["buildings.brick@heritage"] != mat
    assert m3["stage2"]["materials"]["buildings.brick"] == s2["materials"]["buildings.brick"]
    # another era for one building: that actor only
    f3 = copy.deepcopy(fake)
    f3["buildings"]["entries"][0]["materials"] = {}
    m4 = U.build_manifest(_with_contributions(build, tmp_path / "t3", f3))[0]
    assert U.manifest_changes(m2, m4) == {"created": [], "updated": [blds[0]], "deleted": []}
    # AG2's instanced parts of that building take its era's instances too, as the parts
    # merged into its shell do (the importer sets them on the HISM, as on the actor); the
    # importer keeps the city's texture pages out of the mesh prune and gives an instance
    # whose texture was deleted under it its textures again
    f5 = copy.deepcopy(fake)
    f5["buildings"]["entries"][0]["parts"] = [
        {"kind": "part.panel.infill", "glb": "parts/t+00+00.glb",
         "node": "part.panel.infill.std.h01", "asset": "part_panel_infill_std_h01",
         "count": 1, "triangles": 12, "xforms": [[1.0, 2.0, 3.0, 0.0]]}]
    m5 = U.build_manifest(_with_contributions(build, tmp_path / "t6", f5))[0]
    (pi,) = [x for x in m5["stage2"]["instances"] if x["entry"] == blds[0]]
    assert pi["materials"] == a[blds[0]]["materials"]
    src = (Path(U.__file__).parent / "ue" / "import_city.py").read_text()
    assert 'f"{folder}/Textures/"' in src and "own_textures(mi, " in src
    assert "comp.get_material_index(unreal.Name(slot))" in src
    # the masters' usage flags: Nanite too (opaque and masked), on new and existing masters
    assert '"used_with_nanite"' in src and src.count("in usage_flags(m)") == 3
    # a big prune deletes package files on an empty level, then loads the city again
    assert "delete_files if files else delete_assets" in src and "scan_paths_synchronous(" in src
    bad = copy.deepcopy(fake)
    bad["buildings"]["materials"]["brick@heritage"]["textures"]["OrmTex"] = "set.nope.orm"
    with pytest.raises(ValueError, match="no texture set.nope.orm"):
        U.build_manifest(_with_contributions(build, tmp_path / "t4", bad))
    bad = copy.deepcopy(fake)
    bad["buildings"]["textures"]["city.signs_wide_0"]["kind"] = "hdr"
    with pytest.raises(ValueError, match="kind hdr"):
        U.build_manifest(_with_contributions(build, tmp_path / "t5", bad))


def test_stage2_props_replace_prototypes(build, manifest, tmp_path):
    """AG8 over M15's prototype actors: an entry keyed by a prototype actor's key replaces
    it with its variants (transforms with a scale, an id per instance; plants as Nanite
    foliage without collision), a `drop` entry only removes one, a sign replaces its tile's
    sign prototypes through `replaces`, a holo-ad's image is a LOD chain on the `holo`
    master; the importer skips the replaced prototype actors."""
    man = manifest[0]
    insts = sorted(i["key"] for i in man["instances"])
    props_k = next(k for k in insts if k.startswith("prop."))
    plant_k = next(k for k in insts if k.startswith("plant."))
    drop_k = next(k for k in insts if k.startswith("prop.") and k != props_k)
    sign_k = next((k for k in insts if k.startswith("prop.sign.")), insts[-1])
    xf = [[1.0, 2.0, 0.0, 30.0, 1.0, 1.0, 1.0], [3.0, -4.0, 0.5, -90.0, 2.5, 1.2, 1.0]]
    props = {"version": 1, "stage": "assetgen", "part": "props", "layer": 2,
             "materials": {"metal.dark": {"master": "metal", "color": [0.02, 0.02, 0.03],
                                          "roughness": 0.5, "metallic": 0.8},
                           "leaf.oak": {"master": "foliage", "color": [0.04, 0.1, 0.02],
                                        "roughness": 0.8, "metallic": 0.0}},
             "entries": [
                 {"key": props_k, "kind": "prop.test", "hash": "p1", "replaces": [],
                  "pivot": [128.0, 128.0, 0.0], "yaw_deg": 0.0,
                  "parts": [{"kind": "prop.test.civic.v0", "glb": "props/variants/test.glb",
                             "node": "prop.test.civic.v0", "asset": "prop_test_civic_v0",
                             "count": 2, "triangles": 50, "xforms": xf,
                             "ids": ["a.prop.1", "a.prop.2"]}]},
                 {"key": plant_k, "kind": "plant.test", "hash": "p2", "replaces": [],
                  "pivot": [128.0, 128.0, 0.0], "yaw_deg": 0.0,
                  "parts": [{"kind": "plant.oak.v3", "glb": "props/plants/oak.glb",
                             "node": "plant.oak.v3", "asset": "plant_oak_v3", "count": 1,
                             "triangles": 9000, "xforms": xf[:1], "ids": ["a.plant.1"],
                             "nanite": True, "shape_preservation": "voxelize",
                             "collision": {"none": True}}]},
                 {"key": drop_k, "kind": "prop.barrier", "hash": "p3", "replaces": [],
                  "pivot": [0.0, 0.0, 0.0], "yaw_deg": 0.0, "drop": True}]}
    signs = {"version": 1, "stage": "assetgen", "part": "signs", "layer": 2,
             "materials": {"holo.05d9e8": {"master": "holo", "color": [0.0, 0.7, 0.8],
                                           "roughness": 0.1, "metallic": 0.0}},
             "entries": [
                 {"key": "a.sign.slot", "kind": "sign.shop_sign", "hash": "s1",
                  "replaces": [sign_k], "glb": "props/signs/t+00+00.glb",
                  "node": "sign.h0123", "asset": "sign_h0123", "pivot": [5.0, 6.0, 4.5],
                  "yaw_deg": 90.0, "nanite": True, "triangles": 200, "slots": [],
                  "collision": {"none": True}, "tile": "t+00+00"},
                 {"key": "a.holo.slot.holo", "kind": "sign.holo_ad.holo", "hash": "s2",
                  "replaces": [], "glb": "props/signs/t+00+00.glb",
                  "node": "a.holo.slot.holo.lod0", "asset": "a_holo_slot_holo",
                  "pivot": [7.0, 8.0, 90.0], "yaw_deg": 0.0, "nanite": False,
                  "triangles": 40, "slots": ["holo.05d9e8"], "collision": {"none": True},
                  "tile": "t+00+00",
                  "lods": [{"node": f"a.holo.slot.holo.lod{k}", "screen_size": s,
                            "triangles": 40 >> k} for k, s in enumerate((1.0, 0.3, 0.08))]}]}
    staged = _with_contributions(build, tmp_path / "props", {"props": props, "signs": signs})
    m2 = U.build_manifest(staged)[0]
    s2 = m2["stage2"]
    assert s2["replaced"] == sorted({props_k, plant_k, drop_k, sign_k})
    assert s2["counts"]["replaces_missing"] == 0
    inst = {a["key"]: a for a in s2["instances"]}
    a = inst[f"{props_k}.prop.test.civic.v0"]
    assert a["xforms"] == xf and a["ids"] == ["a.prop.1", "a.prop.2"]
    assert a["category"] == next(i["category"] for i in man["instances"] if i["key"] == props_k)
    assert "no_collision" not in a and inst[f"{plant_k}.plant.oak.v3"]["no_collision"]
    plants = next(p for p in s2["packs"] if p["folder"].endswith("PropsParts/oak"))
    (oak,) = plants["meshes"]
    assert oak["shape_preservation"] == "voxelize" and oak["collision"] == {"none": True}
    variants = next(p for p in s2["packs"] if p["folder"].endswith("PropsParts/test"))
    assert "shape_preservation" not in variants["meshes"][0]
    assert s2["materials"]["signs.holo.05d9e8"]["emissive"] == U.EMISSIVE2["holo"]
    assert "holo" in s2["masters"]
    (ch,) = s2["lod_chains"]
    assert [lo["screen_size"] for lo in ch["lods"]] == [1.0, 0.3, 0.08]
    hashes = U.actor_hashes(m2)
    assert not {props_k, plant_k, drop_k, sign_k} & set(hashes)
    assert {f"{props_k}.prop.test.civic.v0", f"{plant_k}.plant.oak.v3", "a.sign.slot",
            "a.holo.slot.holo"} <= set(hashes)
    ch = U.manifest_changes(man, m2)
    assert sorted(ch["deleted"]) == sorted({props_k, plant_k, drop_k, sign_k})
    # the importer leaves the replaced prototype actors out (its skip set)
    src = (Path(U.__file__).parent / "ue" / "import_city.py").read_text()
    assert 'if inst["key"] in self.skip:' in src and "xf[4:7]" in src
    assert 'r.get("ids")' in src and "NaniteShapePreservation" in src
    assert src.count('if r.get("no_collision"):') == 2


@pytest.fixture(scope="module")
def staged(small, build, manifest, tmp_path_factory):
    """The small city with its assets built by assetgen (shells, proxies, streets, AG6's
    materials on a 64 px/m library of its own) beside the blockout files."""
    import os
    from assetgen.build import build as asset_build
    out = tmp_path_factory.mktemp("ue2") / "build"
    shutil.copytree(build, out)
    (out / "city_model.json").write_text(small.to_json() + "\n", encoding="utf-8")
    spec = out / "asset_spec.json"
    spec.write_text(json.dumps({"version": 1, "texel_density_px_m": 64,
                                "texel_density_upper_px_m": 32}))
    old = os.environ.get("ASSETGEN_LIBRARY")
    os.environ["ASSETGEN_LIBRARY"] = str(tmp_path_factory.mktemp("library"))
    try:
        rep = asset_build(out, str(spec), workers=2, log=lambda *a: None)
    finally:
        if old is None:
            os.environ.pop("ASSETGEN_LIBRARY", None)
        else:
            os.environ["ASSETGEN_LIBRARY"] = old
    assert rep["ok"], rep.get("checks")
    return out


def test_stage2_from_assetgen(staged, manifest):
    """assetgen's real contributions for the small city: every building replaces its blockout
    actor by key, every `replaces` names a blockout object, one mesh per node of the packs,
    and an import over the blockout's changes exactly the replaced keys and the new ones."""
    man = manifest[0]
    m2, _, g2 = U.build_manifest(staged)
    s2 = m2["stage2"]
    blockout = {o["key"]: o for t in man["tiles"] for o in t["objects"]}
    protos = {i["key"] for i in man["instances"]}
    con = json.loads((staged / "assets" / "unreal_contribution.buildings.json").read_text())
    blds = [e["key"] for e in con["entries"] if e["kind"] == "building"]
    assert blds and all(blockout[k]["category"] in ("building", "landmark") for k in blds)
    assert set(blds) <= set(s2["replaced"])
    assert s2["counts"]["replaces_missing"] == 0
    # (AG4's roof equipment entries, `roofs.<tile>`, are instanced parts with no node)
    assert all(e["asset"] == U.asset_name(e["node"]) for e in con["entries"] if "node" in e)
    assert all("node" in e or e["kind"] == "roof_equipment" for e in con["entries"])
    for p in s2["packs"]:
        assert p["glb"], p["folder"]
        nodes = {U.asset_name(n["name"]) for n in U.read_glb_json(staged / p["glb"])["nodes"]
                 if "mesh" in n}
        assert {m["asset"] for m in p["meshes"]} <= nodes, p["folder"]
    actor_keys = {a["key"] for a in s2["actors"]}
    assert set(blds) <= actor_keys
    ch = U.manifest_changes(man, m2)
    s2keys = actor_keys | {a["key"] for a in s2["instances"]}
    # AG8's exact props (cables, scaffolding, gates) take the key of M15's instanced actor
    # they replace: a static mesh actor in its place is deleted and created
    ka, kb = U.actor_kinds(man), U.actor_kinds(m2)
    moved = {k for k in ka.keys() & kb.keys() if ka[k] != kb[k]}
    assert moved and moved <= protos and all(kb[k] == "mesh" for k in moved)
    assert ch["deleted"] == sorted((set(s2["replaced"]) - s2keys) | moved)
    assert ch["updated"] == sorted((s2keys & (set(blockout) | protos)) - moved)
    assert ch["created"] == sorted((s2keys - set(blockout) - protos) | moved)
    # AG8: every prop and plant prototype actor of M15 replaced by props, plants and signs
    assert protos <= set(s2["replaced"])
    assert all(len(a["cpd"]) == 30 for a in s2["actors"] if a["key"] in set(blds))
    # AG6: every texture a material names is in the build (the library through its link)
    assert s2["textures"] and all((staged / t["file"]).is_file()
                                  for t in s2["textures"].values())
    assert {"facade", "glass", "metal", "road", "concrete", "sign", "decal"} <= \
        set(s2["masters"])
    era = [a for a in s2["actors"] if a.get("materials")]
    assert era and all(v in {m["asset"] for m in s2["materials"].values()}
                       for a in era for v in a["materials"].values())
    assert _dump(U.build_manifest(staged)[0]) == _dump(m2)


def test_stage2_takes_assetgen_parts(staged):
    """AG2's facade parts: every part a building's entry lists is an instanced actor keyed
    `<key>.<kind>` with the entry's pivot, Custom Primitive Data and the part's transforms,
    its mesh one node of the tile's part pack, and every part slot a material."""
    m2, _, _ = U.build_manifest(staged)
    s2 = m2["stage2"]
    con = json.loads((staged / "assets" / "unreal_contribution.buildings.json").read_text())
    want = {(e["key"], p["kind"]): (e, p) for e in con["entries"]
            for p in e.get("parts", [])}
    assert want
    got = {(a["entry"], a["kind"]): a for a in s2["instances"]
           if a["entry"] in {e["key"] for e in con["entries"]}}
    assert set(got) == set(want)
    for (key, kind), (e, p) in want.items():
        a = got[(key, kind)]
        assert a["key"] == f"{key}.{kind}" and a["xforms"] == p["xforms"]
        assert a["pivot"] == [float(v) for v in e["pivot"]] and a["cpd"] == e["cpd"]
        assert a["mesh"].endswith("/" + U.asset_name(p["node"]))
    packs = {pk["glb"]: pk for pk in s2["packs"]}
    for e, p in want.values():
        pk = packs[f"{U.ASSETS_DIR}/{p['glb']}"]
        assert pk["use"] == "part" and U.asset_name(p["node"]) in {m["asset"]
                                                                  for m in pk["meshes"]}
    assert {f"{con['part']}.{m}" for m in con["materials"]} <= set(s2["materials"])
    assert {"frame", "balcony", "dado"} <= set(con["materials"])
    assert sum(len(a["xforms"]) for a in got.values()) == sum(e.get("instances", 0)
                                                              for e in con["entries"])
    # no collision on a building's parts (AG2's contract: its simple collision covers its
    # masses), meshes and instancers; AG7's container stacks keep theirs
    assert all(a["no_collision"] for a in got.values())
    pm = {f"{pk['folder']}/{m['asset']}": m for pk in s2["packs"] for m in pk["meshes"]}
    assert all(pm[a["mesh"]]["collision"] == {"none": True} for a in got.values())
    cont = [a for a in s2["instances"] if a["kind"].startswith("part.container")]
    assert all(not a.get("no_collision") and pm[a["mesh"]]["collision"] == {"complex": True}
               for a in cont)


def test_stage2_takes_assetgen_fronts(staged):
    """AG3's street fronts: an actor per building's front keyed `<key>.front` at its
    building's pivot with its Custom Primitive Data and id, complex collision on a Nanite
    mesh whose fallback keeps every triangle, a `cg.door` tag per door (its id and walkway),
    and the doors graph (one element per door at its world point, its walkway as ref); the
    tiles' decal meshes as actors without Nanite or collision, each slot a decal material."""
    m2, _, g2 = U.build_manifest(staged)
    s2 = m2["stage2"]
    con = json.loads((staged / "assets" / "unreal_contribution.buildings.json").read_text())
    fronts = {e["key"]: e for e in con["entries"] if e["kind"] == "building.front"}
    assert fronts
    actors = {a["key"]: a for a in s2["actors"]}
    meshes = {f"{p['folder']}/{m['asset']}": m for p in s2["packs"] for m in p["meshes"]}
    ndoors = 0
    for key, e in fronts.items():
        a = actors[key]
        b = key[:-len(".front")]
        assert a["ids"] == [b] and a["pivot"] == actors[b]["pivot"] and a["cpd"] == e["cpd"]
        assert a["type"] == "building.front" and a["category"] == "building"
        m = meshes[a["mesh"]]
        assert m["collision"] == {"complex": True} and m["nanite"] and m["fallback_full"]
        assert a.get("doors", []) == [f"{d['id']}@{d.get('walkway_id') or ''}"
                                      for d in e["doors"]]
        ndoors += len(e["doors"])
    assert ndoors and g2["doors"]["count"] == ndoors
    by = {d["id"]: (e, d) for e in fronts.values() for d in e["doors"]}
    assert sorted(g2["doors"]["ids"]) == sorted(by)
    for k, did in enumerate(g2["doors"]["ids"]):
        e, d = by[did]
        assert g2["doors"]["refs"][k] == (d.get("walkway_id") or "")
        p = g2["doors"]["points"][3 * k:3 * k + 3]
        assert p == pytest.approx([e["pivot"][j] + d["position"][j] for j in range(3)],
                                  abs=1e-3)
    assert "doors" in m2["graphs"]
    dec = [e for e in con["entries"] if e["kind"] == "decals"]
    assert dec
    for e in dec:
        a = actors[e["key"]]
        assert a["no_collision"] and not meshes[a["mesh"]]["nanite"]
        for s in e["slots"]:
            mat = s2["materials"][f"buildings.{s}"]
            assert mat["master"] == "decal" and "Cell" in mat["scalars"]


def test_stage2_takes_assetgen_roofs_and_skybridges(staged):
    """AG4: roof equipment leaves the buildings' entries for one entry per tile
    (`roofs.<tile>`): an instanced actor per mesh at the origin with one building id per
    transform, its mesh a node of the tile's part pack, without collision or era materials;
    the green-roof objects a building replaces are blockout objects; every skybridge an
    actor of its own with its links."""
    m2, _, _ = U.build_manifest(staged)
    s2 = m2["stage2"]
    con = json.loads((staged / "assets" / "unreal_contribution.buildings.json").read_text())
    man = json.loads((staged / "assets" / "manifest.json").read_text())
    roofs = [e for e in con["entries"] if e["kind"] == "roof_equipment"]
    assert roofs
    for e in con["entries"]:
        if e["kind"] == "building":
            assert all(not p["kind"].startswith(("part.ac_unit", "part.water_tank",
                                                 "part.antenna", "part.pad", "part.hut"))
                       for p in e["parts"])
    inst = {a["key"]: a for a in s2["instances"]}
    n = 0
    for e in roofs:
        t = e["key"].split(".", 1)[1]
        assert e["pivot"] == [0.0, 0.0, 0.0] and e["tags"]["cg.tile"] == t
        for p in e["parts"]:
            a = inst[f"{e['key']}.{p['kind']}"]
            assert a["ids"] == p["ids"] and len(a["ids"]) == len(a["xforms"]) == p["count"]
            assert a["no_collision"] and "materials" not in a   # (as AG2's parts; no era)
            assert set(a["ids"]) <= set(man["buildings"])
            assert p["glb"] == f"parts/{t}.glb"
            n += p["count"]
    assert n == sum(1 for r in man["buildings"].values() for x in r["parts"] if x.get("roof")
                    for _ in x["xforms"])
    green = {g for e in con["entries"] for g in e.get("replaces", [])}
    assert green <= set(s2["replaced"]) and s2["counts"]["replaces_missing"] == 0
    cp = staged / "assets" / "unreal_contribution.connections.json"
    conn = json.loads(cp.read_text())
    actors = {a["key"]: a for a in s2["actors"]}
    for e in conn["entries"]:
        assert e["kind"] == "skybridge" and e["key"] in s2["replaced"]
        assert actors[e["key"]]["links"] == e["links"]
        assert actors[e["key"]]["mesh"].startswith("Assets/Connections/")


def test_stage2_textured_props_and_signs(staged):
    """AG8 with AG6's library: leaf cards on the `leaves` master with their leaf tile, bark
    and painted metal textured, sign faces on the `sign` master with the city's sign page
    (the same texture record the materials contribution lists), holo screens on the `holo`
    master with its holo page; the importer builds both masters."""
    m2, _, _ = U.build_manifest(staged)
    s2 = m2["stage2"]
    mats = s2["materials"]
    leaf = [m for k, m in mats.items() if k.startswith("props.leaf.")]
    assert leaf and all(m["master"] == "leaves" and m["textures"]["BaseTex"]["texture"]
                        .startswith("set.leaves_") for m in leaf)
    bark = [m for k, m in mats.items() if k.startswith("props.bark.")]
    assert bark and all(m["textures"]["BaseTex"]["texture"].startswith("set.bark_")
                        for m in bark)
    assert any(k.startswith("props.metal.") and m.get("textures") for k, m in mats.items())
    faces = {k: m for k, m in mats.items() if k.startswith("signs.page.")}
    assert faces and all(m["master"] == "sign" for m in faces.values())
    for k, m in faces.items():
        page = k.split(".", 2)[2]
        assert m["textures"]["SignTex"]["texture"] == f"city.{page}"
        assert m["textures"]["SignTex"] == mats[f"materials.{page}"]["textures"]["SignTex"]
    assert "leaves" in s2["masters"] and "sign" in s2["masters"]
    con = json.loads((staged / "assets" / "unreal_contribution.signs.json").read_text())
    faced = [e for e in con["entries"] if any(s.startswith("page.") for s in e["slots"])]
    assert faced
    src = (Path(U.__file__).parent / "ue" / "import_city.py").read_text()
    assert 'elif master == "leaves":' in src and "MP_OPACITY_MASK" in src
    assert 'tparam(m, "SignTex", "color"' in src and "HOLO_CODE" in src


# --- in Unreal (where it is installed) ------------------------------------------------------

UE_ROOT = U.find_engine()
BLENDER = BO.find_blender()


@pytest.mark.skipif(UE_ROOT is None or BLENDER is None,
                    reason="Unreal Engine 5 or Blender not installed")
def test_unreal_import_small_city(small, regenerated, tmp_path):
    """The small city into a fresh First Person project: imported, a second import changes
    nothing, the city with a district regenerated updates only the actors of what changed (and
    an import after it changes nothing), and in play-in-editor the cells stream, traces hit
    the ground and roofs, and the player walks a sidewalk."""
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
    # Play flies by default, the level streams for it, the project opens on the city
    assert first["play"]["mode"] == "fly" and first["streaming"]["set"]
    assert first["startup_map"] == first["level"] and first["startup_map_changed"]
    assert f"GameDefaultMap={first['level']}." in \
        (proj.parent / "Config" / "DefaultEngine.ini").read_text()
    second = U.import_city(build, proj)
    assert second["ok"], second.get("error")
    assert second["actors"]["created"] == second["actors"]["updated"] == \
        second["actors"]["deleted"] == 0
    assert second["tiles_imported"] == 0 and second["dirty_packages"] == 0
    assert second["streaming"]["changed"] == 0 and not second["play"]["fly_classes_saved"]
    assert second["startup_map_changed"] is False
    assert (second["actor_digest"], second["asset_digest"]) == \
        (first["actor_digest"], first["asset_digest"])
    # the city with a district regenerated (`citygen build --district`): the import touches
    # exactly the actors whose content changed and leaves the rest as they were
    build2 = tmp_path / "build2"
    build2.mkdir()
    (build2 / "city_model.json").write_text(regenerated.to_json() + "\n", encoding="utf-8")
    assert BO.run_blockout(build2 / "city_model.json", build2, render=False)["passed"]
    third = U.import_city(build2, proj)
    assert third["ok"], third.get("error")
    want = U.manifest_changes(json.loads((build / "unreal" / "manifest.json").read_text()),
                              json.loads((build2 / "unreal" / "manifest.json").read_text()))
    did = next(d.id for d in small.districts if d.name == REGEN)
    assert any(k.startswith(did + ".") for k in want["created"])
    assert any(k.startswith(did + ".") for k in want["deleted"])
    assert {k: third["keys"][k] for k in want} == want
    assert third["actors"]["unchanged"] == \
        third["actor_count"] - len(want["created"]) - len(want["updated"])
    # and what it changed was saved: the same build again changes nothing
    fourth = U.import_city(build2, proj)
    assert fourth["ok"], fourth.get("error")
    assert fourth["actors"]["created"] == fourth["actors"]["updated"] == \
        fourth["actors"]["deleted"] == fourth["dirty_packages"] == 0
    chk = U.check_city(build2, proj)
    assert chk["ok"], chk
    # walked with the template's character, then flew with the fly pawn
    assert "FirstPerson" in chk["pawn"] and chk["checks"]["fly"]["ok"]
    # the project and the builds take most of a gigabyte: kept only when the test fails
    for d in (proj.parent, build, build2):
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(UE_ROOT is None or BLENDER is None,
                    reason="Unreal Engine 5 or Blender not installed")
def test_unreal_import_stage2_small_city(small, tmp_path):
    """Stage 2 over the blockout in Unreal: the small city imported alone, then with
    assetgen's buildings and streets (exactly the actors `manifest_changes` names change),
    imported again (nothing changes), checked in play-in-editor, back to the blockout (its
    actors only: stage 2's meshes stay) and to stage 2 again, every mesh reused."""
    from assetgen.build import build as asset_build
    build = tmp_path / "build"
    build.mkdir()
    (build / "city_model.json").write_text(small.to_json() + "\n", encoding="utf-8")
    assert BO.run_blockout(build / "city_model.json", build, render=False)["passed"]
    assert asset_build(build, workers=2, log=lambda *a: None)["ok"]
    proj = U.new_project(tmp_path / "Proj", UE_ROOT)
    first = U.import_city(build, proj, assets=False)
    assert first["ok"], first.get("error")
    old = json.loads((build / "unreal" / "manifest.json").read_text())
    assert "stage2" not in old and "stage2" not in first
    second = U.import_city(build, proj)
    assert second["ok"], second.get("error")
    new = json.loads((build / "unreal" / "manifest.json").read_text())
    want = U.manifest_changes(old, new)
    assert want["deleted"] and want["updated"] and want["created"]
    assert {k: second["keys"][k] for k in want} == want
    s2 = second["stage2"]
    assert s2["meshes"]["imported"] == new["stage2"]["counts"]["meshes"]
    assert s2["hulls"] > 0 and s2["complex_fallback"] == 0
    assert second["actor_count"] == new["counts"]["actors"]
    third = U.import_city(build, proj)
    assert third["ok"], third.get("error")
    assert third["actors"]["created"] == third["actors"]["updated"] == \
        third["actors"]["deleted"] == third["dirty_packages"] == 0
    assert third["stage2"]["packs_imported"] == third["tiles_imported"] == 0
    assert (third["actor_digest"], third["asset_digest"]) == \
        (second["actor_digest"], second["asset_digest"])
    chk = U.check_city(build, proj)
    assert chk["ok"], chk
    assert chk["checks"]["streaming"]["stage2_at_start"] > 0
    back = U.import_city(build, proj, assets=False)
    assert back["ok"], back.get("error")
    assert {k: back["keys"][k] for k in want} == U.manifest_changes(new, old)
    assert (back["actor_digest"], back["actor_count"]) == \
        (first["actor_digest"], first["actor_count"])
    again = U.import_city(build, proj)
    assert again["ok"], again.get("error")
    assert {k: again["keys"][k] for k in want} == want
    assert again["stage2"]["meshes"]["imported"] == again["stage2"]["packs_imported"] == 0
    assert again["actor_digest"] == second["actor_digest"]
    for d in (proj.parent, build):
        shutil.rmtree(d, ignore_errors=True)
