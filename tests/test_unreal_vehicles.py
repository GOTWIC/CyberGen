"""AG18: the Unreal exporter's vehicles (citygen/unreal_vehicles.py): a library of game packs
(vehicles/GAME.md) read into the manifest's `vehicles` (each car's files and hashes, parts and
pivots, materials, show colors, LODs, collision hulls) and the contributions' placement entries
into an actor each, keyed and hashed for incremental imports. A city whose contributions place
no vehicle exports as it did. The packs here are tiny ones made in the test (never the real
cache); the Unreal side runs in `citygen unreal --check-vehicles` (docs/progress/AG18/unreal)."""

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from citygen import unreal as U
from citygen import unreal_vehicles as UV
from citygen.cli import main

TILE = "t+00+00"


def _box(c, d):
    return [{"k": "box", "c": c, "d": d, "yaw": 0.0, "m": "m"}]


def _pack(lib: Path, car: str, hover=False, color=(0.4, 0.05, 0.02)) -> Path:
    """A tiny game pack: a box body, a box of glass, two wheels (none when `hover`), four
    LOD files, two hulls, five 4 px textures a slot."""
    d = lib / car
    d.mkdir(parents=True)
    parts = {"body": U.prototype_mesh(_box([0, 0, 0.2], [4, 1.8, 1.0])),
             "glass": U.prototype_mesh(_box([0, 0, 1.2], [2, 1.6, 0.4]))}
    if not hover:
        for w in ("wheel_fl", "wheel_fr"):
            parts[w] = U.prototype_mesh(_box([0, 0, -0.3], [0.6, 0.2, 0.6]))
    for k in range(4):
        U.write_glb(parts, {}, d / f"lod{k}.glb")
    U.write_glb({"UCX_body_00": U.prototype_mesh(_box([-1, 0, 0.2], [2, 1.8, 1.0])),
                 "UCX_body_01": U.prototype_mesh(_box([1, 0, 0.2], [2, 1.8, 0.8]))}, {},
                d / "collision.glb")
    slots = ["body"] if hover else ["body", "wheels"]
    mats = {}
    for s in slots:
        tex = {}
        for key in ("base_color", "normal", "orm", "mask", "emissive"):
            f = f"{s}_{key}.png"
            Image.new("RGBA", (4, 4), (10 * len(key), 20, 30, 255)).save(d / f)
            tex[key] = {"file": f, "size": 4}
        mats[s] = {"textures": tex, "params": {"coat_roughness": 0.06,
                                               "emissive_strength": 15.0}}
    mats["glass"] = {"params": {"material": "glass", "color": [0.3, 0.33, 0.36],
                                "roughness": 0.0, "ior": 1.5, "transmission": 1.0,
                                "opaque_from_lod": 2}}
    if hover:
        mats["wheels"] = None
    pk = {"format": "cybergen.vehicle_pack", "version": 1, "car": car, "title": car.title(),
          "kind": "hover" if hover else "wheeled",
          "dimensions": {"length": 4.0, "width": 1.8, "height": 1.4,
                         "min": [-2.0, -0.9, 0.0], "max": [2.0, 0.9, 1.4]},
          "lods": [{"lod": k, "file": f"lod{k}.glb", "triangles": 100 >> k,
                    "parts": {"body": 12}} for k in range(4)],
          "parts": [{"name": "body", "material": "body", "pivot": [0, 0, 0], "kind": "body"},
                    {"name": "glass", "material": "glass", "pivot": [0, 0, 0],
                     "kind": "glass"}] +
                   ([] if hover else [
                       {"name": "wheel_fl", "material": "wheels", "pivot": [1.4, 0.8, 0.3],
                        "kind": "wheel", "radius": 0.3, "steers": True, "spins": True},
                       {"name": "wheel_fr", "material": "wheels", "pivot": [1.4, -0.8, 0.3],
                        "kind": "wheel", "radius": 0.3, "steers": True, "spins": True}]),
          "materials": mats,
          "colors": {"primary": {"color": list(color), "channel": "R"},
                     "secondary": {"color": [0.8, 0.8, 0.8], "channel": "G"},
                     "accent": {"color": [0.9, 0.6, 0.0], "channel": "B"}},
          "emissive_strength": 15.0, "micro_detail": {},
          "collision": {"file": "collision.glb", "hulls": [{"name": "UCX_body_00"},
                                                           {"name": "UCX_body_01"}]},
          "size_class": {"name": "standard"}}
    (d / "pack.json").write_text(json.dumps(pk, indent=1))
    return d


@pytest.fixture
def lib(tmp_path):
    lib = tmp_path / "lib"
    _pack(lib, "test_coupe")
    _pack(lib, "test_hover", hover=True, color=(0.0, 0.2, 0.6))
    return lib


def _build(tmp_path) -> Path:
    """A one-tile blockout output (the manifest needs no glTF tiles)."""
    b = tmp_path / "build"
    b.mkdir()
    ground = {"name": f"city.ground.{TILE}", "tile": TILE, "category": "ground", "props": {},
              "parts": [{"k": "prism", "r": [[0, 0], [256, 0], [256, 256], [0, 256]],
                         "z0": -0.5, "z1": 0.0, "m": "ground"}]}
    car = {"name": f"prop.parked_car.{TILE}", "tile": TILE, "category": "prop",
           "props": {"citygen_type": "prop.parked_car"},
           "parts": [{"k": "inst", "proto": "parked_car", "pts": [[10, 10, 0, 0, 1, 1, 1]]}]}
    plan = {"city": "Vehicle Test", "seed": 1, "tile_size_m": 256, "bounds": [0, 0, 256, 256],
            "tiles": [{"name": TILE, "ix": 0, "iy": 0, "bounds": [0, 0, 256, 256]}],
            "objects": [ground, car], "materials": {"ground": "#404040", "m": "#808080"},
            "prototypes": {"parked_car": _box([0, 0, 0], [4.6, 1.8, 1.4])}}
    (b / "blockout_plan.json").write_text(json.dumps(plan))
    (b / "tiles.json").write_text(json.dumps({"tile_size_m": 256, "tiles": plan["tiles"]}))
    return b


def _place(build: Path, entries, name="vehicles", other=None):
    (build / "assets").mkdir(exist_ok=True)
    c = {"version": 1, "stage": "assetgen", "part": name, "layer": 2,
         "entries": entries + (other or [])}
    (build / "assets" / f"unreal_contribution.{name}.json").write_text(json.dumps(c))


ENTRY = {"key": f"vehicles.parked.{TILE}", "kind": "vehicles", "hash": "h1", "tile": TILE,
         "pivot": [128.0, 128.0, 0.0], "replaces": [f"prop.parked_car.{TILE}"],
         "vehicles": [
             {"car": "test_coupe", "id": "d01.prop.parked_car.e10n10",
              "xform": [-118.0, -118.0, 0.0, 90.0],
              "paint": [[0.8, 0.0, 0.1], [0.1, 0.1, 0.1], [0.0, 0.6, 0.9]], "steer_deg": 20.0},
             {"car": "test_coupe", "id": "d01.prop.parked_car.e20n10",
              "xform": [-108.0, -118.0, 0.0, 90.0]},
             {"car": "test_hover", "id": "d01.prop.parked_car.e30n10",
              "xform": [-98.0, -118.0, 0.0, 0.0]}]}


def _man(build, lib, **kw):
    man, _, _ = U.build_manifest(build, vehicles=lib, **kw)
    return man


def test_read_pack(lib):
    rec = UV.read_pack(lib / "test_coupe")
    assert rec["car"] == "test_coupe" and rec["kind"] == "wheeled"
    assert rec["folder"] == "/Game/CityGen/Vehicles/test_coupe"
    assert sorted(rec["files"]) == sorted(
        ["collision.glb"] + [f"lod{k}.glb" for k in range(4)] +
        [f"{s}_{k}.png" for s in ("body", "wheels")
         for k in ("base_color", "normal", "orm", "mask", "emissive")])
    assert all(len(h) == 64 for h in rec["files"].values())
    t = rec["textures"]
    assert t["body.base_color"]["srgb"] and t["body.emissive"]["srgb"]
    assert not t["body.normal"]["srgb"] and t["body.normal"]["kind"] == "normal"
    assert not t["body.orm"]["srgb"] and not t["body.mask"]["srgb"]
    assert [lo["screen_size"] for lo in rec["lods"]] == list(UV.SCREEN_SIZES)
    assert all(lo["tangents"] is False for lo in rec["lods"])     # (the test's glTF has none)
    wheel = next(p for p in rec["parts"] if p["name"] == "wheel_fl")
    assert wheel["pivot"] == [1.4, 0.8, 0.3] and wheel["steers"]
    assert rec["colors"]["primary"] == [0.4, 0.05, 0.02]
    assert rec["glass"]["opaque_from_lod"] == 2
    # the hulls welded (a box: 8 corners, 12 triangles), in the car's frame (glTF's y up)
    assert [h["name"] for h in rec["hulls"]] == ["UCX_body_00", "UCX_body_01"]
    h = rec["hulls"][0]
    assert len(h["vertices"]) == 8 and len(h["triangles"]) == 12
    xs, ys, zs = zip(*h["vertices"])
    assert (min(xs), max(xs)) == (-2.0, 0.0) and (min(ys), max(ys)) == (-0.9, 0.9)
    assert (min(zs), max(zs)) == (0.2, 1.2)
    # a hover car has no wheels slot
    hv = UV.read_pack(lib / "test_hover")
    assert set(hv["materials"]) == {"body"} and not any(k.startswith("wheels.")
                                                        for k in hv["textures"])
    # the car's hash follows its files, not the folder it was read from
    other = lib.parent / "elsewhere"
    import shutil
    shutil.copytree(lib / "test_coupe", other / "test_coupe")
    assert UV.read_pack(other / "test_coupe")["hash"] == rec["hash"]
    (other / "test_coupe" / "body_mask.png").write_bytes(
        (other / "test_coupe" / "body_mask.png").read_bytes() + b"\0")
    assert UV.read_pack(other / "test_coupe")["hash"] != rec["hash"]


def test_refuses_bad_packs(lib, tmp_path):
    (lib / "test_coupe" / "lod3.glb").unlink()
    with pytest.raises(FileNotFoundError):
        UV.read_pack(lib / "test_coupe")
    pk = json.loads((lib / "test_hover" / "pack.json").read_text())
    pk["version"] = 2
    (lib / "test_hover" / "pack.json").write_text(json.dumps(pk))
    with pytest.raises(ValueError):
        UV.read_pack(lib / "test_hover")


def test_library_dir(tmp_path, monkeypatch):
    monkeypatch.delenv(UV.LIBRARY_ENV, raising=False)
    assert UV.library_dir() == UV.DEFAULT_LIBRARY
    monkeypatch.setenv(UV.LIBRARY_ENV, str(tmp_path / "env"))
    assert UV.library_dir() == tmp_path / "env"
    assert UV.library_dir(tmp_path / "arg") == tmp_path / "arg"


def test_no_placements_no_change(lib, tmp_path):
    """A city whose contributions place no vehicle exports byte for byte as before, whatever
    the library holds: no `vehicles`, the same contributions to stage 2."""
    b = _build(tmp_path)
    before, _, _ = U.build_manifest(b)
    assert "vehicles" not in before
    assert json.dumps(_man(b, lib)) == json.dumps(before)
    # a stage 2 contribution without placements reaches stage 2 as it was
    _place(b, [], name="props", other=[{"key": f"prop.parked_car.{TILE}", "drop": True,
                                        "kind": "prop.parked_car", "replaces": []}])
    contribs = U.contributions(b)
    rest, placed = UV.split(contribs)
    assert rest == contribs and placed == []
    plain, _, _ = U.build_manifest(b)
    assert json.dumps(_man(b, lib)) == json.dumps(plain)


def test_placements(lib, tmp_path):
    b = _build(tmp_path)
    before, _, _ = U.build_manifest(b)
    _place(b, [copy.deepcopy(ENTRY)])
    man = _man(b, lib)
    v = man["vehicles"]
    assert sorted(v["cars"]) == ["test_coupe", "test_hover"]
    assert v["folder"] == "/Game/CityGen/Vehicles" and v["paint_cpd"] == 9
    assert v["replaced"] == [f"prop.parked_car.{TILE}"]
    assert v["counts"] == {"cars": 2, "placements": 1, "vehicles": 3}
    assert man["counts"]["vehicles"] == 3
    (r,) = v["placements"]
    assert r["key"] == ENTRY["key"] and r["count"] == 3 and r["tile"] == TILE
    coupe = r["models"]["test_coupe"]
    assert coupe["ids"] == ["d01.prop.parked_car.e10n10", "d01.prop.parked_car.e20n10"]
    assert coupe["xforms"][0] == [-118.0, -118.0, 0.0, 90.0]
    assert coupe["paint"][0] == [0.8, 0.0, 0.1, 0.1, 0.1, 0.1, 0.0, 0.6, 0.9]
    # (no paint: the pack's show colors)
    assert coupe["paint"][1] == [0.4, 0.05, 0.02, 0.8, 0.8, 0.8, 0.9, 0.6, 0.0]
    assert coupe["steer"] == [20.0, 0.0]
    assert r["models"]["test_hover"]["paint"][0][:3] == [0.0, 0.2, 0.6]
    # stage 2 holds nothing of it (the file had only placements), and the rest of the
    # manifest is the blockout's
    assert "stage2" not in man
    rest = {k: x for k, x in man.items() if k not in ("vehicles", "hash", "counts")}
    assert rest == {k: x for k, x in before.items() if k not in ("hash", "counts")}
    # the actor: a group actor in place of the parked car prototype
    hashes, kinds = U.actor_hashes(man), U.actor_kinds(man)
    assert hashes[ENTRY["key"]] == r["hash"] and kinds[ENTRY["key"]] == "vehicles"
    assert f"prop.parked_car.{TILE}" not in hashes
    assert man["counts"]["actors"] == len(hashes)
    ch = U.manifest_changes(before, man)
    assert ch == {"created": [ENTRY["key"]], "updated": [],
                  "deleted": [f"prop.parked_car.{TILE}"]}


def test_updates_by_hash(lib, tmp_path):
    """The same build twice changes nothing; a new paint or a changed pack updates the
    placement's actor alone; a second placement is created alone."""
    b = _build(tmp_path)
    _place(b, [copy.deepcopy(ENTRY)])
    a = _man(b, lib)
    assert json.dumps(_man(b, lib)) == json.dumps(a)
    assert U.manifest_changes(a, _man(b, lib)) == {"created": [], "updated": [], "deleted": []}
    e = copy.deepcopy(ENTRY)
    e["vehicles"][1]["paint"] = [[0.1, 0.2, 0.3]] * 3
    _place(b, [e])
    assert U.manifest_changes(a, _man(b, lib))["updated"] == [ENTRY["key"]]
    _place(b, [copy.deepcopy(ENTRY)])
    img = Image.new("RGBA", (4, 4), (1, 2, 3, 255))
    img.save(lib / "test_hover" / "body_base_color.png")
    c = _man(b, lib)
    assert c["vehicles"]["cars"]["test_hover"]["hash"] != a["vehicles"]["cars"]["test_hover"][
        "hash"]
    assert c["vehicles"]["cars"]["test_coupe"] == a["vehicles"]["cars"]["test_coupe"]
    assert U.manifest_changes(a, c) == {"created": [], "updated": [ENTRY["key"]],
                                        "deleted": []}
    e2 = copy.deepcopy(ENTRY)
    e2.update(key="vehicles.lineup", replaces=[])
    _place(b, [copy.deepcopy(ENTRY), e2])
    d = _man(b, lib)
    assert U.manifest_changes(c, d) == {"created": ["vehicles.lineup"], "updated": [],
                                        "deleted": []}


def test_placements_beside_stage2(lib, tmp_path):
    """Placement entries in another part's contribution leave its other entries to stage 2;
    a placement may not take another actor's key."""
    b = _build(tmp_path)
    drop = {"key": f"prop.parked_car.{TILE}", "drop": True, "kind": "prop.parked_car",
            "replaces": []}
    e = copy.deepcopy(ENTRY)
    e["replaces"] = []
    _place(b, [e], name="props", other=[drop])
    man = _man(b, lib)
    assert man["stage2"]["replaced"] == [f"prop.parked_car.{TILE}"]
    assert [f["entries"] for f in man["stage2"]["files"]] == [1]
    assert [r["key"] for r in man["vehicles"]["placements"]] == [ENTRY["key"]]
    e = copy.deepcopy(ENTRY)
    e["key"] = f"city.ground.{TILE}"
    _place(b, [e])
    with pytest.raises(ValueError, match="other actors"):
        _man(b, lib)


def test_refuses_bad_placements(lib, tmp_path):
    b = _build(tmp_path)
    e = copy.deepcopy(ENTRY)
    e["vehicles"][0]["car"] = "no_such_car"
    _place(b, [e])
    with pytest.raises(FileNotFoundError):
        _man(b, lib)
    e = copy.deepcopy(ENTRY)
    e["vehicles"][0]["paint"] = [[1, 0, 0]]
    _place(b, [e])
    with pytest.raises(ValueError, match="paint"):
        _man(b, lib)
    e = copy.deepcopy(ENTRY)
    e["vehicles"][0]["xform"] = [0, 0, 0]
    _place(b, [e])
    with pytest.raises(ValueError, match="xform"):
        _man(b, lib)
    e = copy.deepcopy(ENTRY)
    del e["tile"]
    _place(b, [e])
    with pytest.raises(ValueError, match="tile"):
        _man(b, lib)


def test_all_vehicles(lib, tmp_path):
    """--all-vehicles: every car of the library, placed or not, and no placement."""
    b = _build(tmp_path)
    man = _man(b, lib, all_vehicles=True)
    assert sorted(man["vehicles"]["cars"]) == ["test_coupe", "test_hover"]
    assert man["vehicles"]["placements"] == []
    assert U.actor_hashes(man) == U.actor_hashes(U.build_manifest(b)[0])


def test_cli(lib, tmp_path):
    b = _build(tmp_path)
    _place(b, [copy.deepcopy(ENTRY)])
    assert main(["unreal", str(b), "--manifest-only", "--no-play",
                 "--vehicles", str(lib)]) == 0
    man = json.loads((b / "unreal" / "manifest.json").read_text())
    assert man["vehicles"]["library"] == str(lib.resolve())
    assert main(["unreal", str(b), "--manifest-only", "--no-play", "--blockout-only",
                 "--vehicles", str(lib)]) == 0
    assert "vehicles" not in json.loads((b / "unreal" / "manifest.json").read_text())
