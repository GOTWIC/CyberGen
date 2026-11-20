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
    # the glass's box in the car's frame (the importer: an eye inside it is in the cabin)
    assert rec["glass_box"] == {"min": [-1.0, -0.8, 1.2], "max": [1.0, 0.8, 1.6]}
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


def test_merged_cars(lib, tmp_path):
    """car_merge: each car's parts as one mesh a LOD in BUILD/unreal/vehicles/<car>: the
    parts at their pivots grouped by material, a rolling wheel's under its material with
    `_roll` and its middle (Unreal's x and z, cm) in UV1, nothing else in it; the car's own
    hash, and so the parked cars' actors, as before; the same build writes the same bytes."""
    import numpy as np
    b = _build(tmp_path)
    _place(b, [copy.deepcopy(ENTRY)])
    man = _man(b, lib)
    coupe, hover = man["vehicles"]["cars"]["test_coupe"], man["vehicles"]["cars"]["test_hover"]
    assert coupe["hash"] == UV.read_pack(lib / "test_coupe")["hash"]
    mg = coupe["merged"]
    assert mg["files"] == [f"unreal/vehicles/test_coupe/lod{k}.glb" for k in range(4)]
    assert mg["part"] == "merged" and mg["roll_radius"] == 0.3
    assert hover["merged"]["roll_radius"] == 0.0
    assert not any(m.endswith("_roll") for m in hover["merged"]["materials"])
    doc, blob = UV._glb(b / mg["files"][0])
    assert [n["name"] for n in doc["nodes"]] == ["merged"]
    mats = [m["name"] for m in doc["materials"]]
    assert mats == mg["materials"] and [m for m in mats if m.endswith("_roll")]
    src, sblob = UV._glb(lib / "test_coupe" / "lod0.glb")
    wheel = next(n for n in src["nodes"] if n.get("name") == "wheel_fl")
    wpos = UV._array(src, sblob, src["meshes"][wheel["mesh"]]["primitives"][0]
                     ["attributes"]["POSITION"])
    for prim in doc["meshes"][0]["primitives"]:
        mat = doc["materials"][prim["material"]]["name"]
        uv1 = UV._array(doc, blob, prim["attributes"]["TEXCOORD_1"])
        pos = UV._array(doc, blob, prim["attributes"]["POSITION"])
        if mat.endswith("_roll"):
            # (both wheels, each at its pivot: the car's (x, y, z) is glTF's (x, -z, y))
            assert sorted({tuple(r) for r in uv1.tolist()}) == [(140.0, 30.0)]
            n = len(wpos)
            assert np.allclose(pos[:n], wpos + [1.4, 0.3, -0.8], atol=1e-5)
            assert np.allclose(pos[n:2 * n], wpos + [1.4, 0.3, 0.8], atol=1e-5)
        else:
            assert not uv1.any()
    stamp = (b / mg["files"][0]).stat().st_mtime_ns
    again = _man(b, lib)
    assert again["vehicles"]["cars"]["test_coupe"]["merged"] == mg
    assert (b / mg["files"][0]).stat().st_mtime_ns == stamp
    assert U.actor_hashes(again) == U.actor_hashes(man)


def test_merged_last_lod_is_one_section(lib, tmp_path):
    """car_merge_followups: the merged mesh's last LOD is one section, the body's: the glass
    and the wheels (a rolling wheel's too) join it with UV1 (gray, -1 - roughness), which
    M_CgVehicle draws flat, the glass already from the LOD it is dark in; a pack whose parts
    share the body's material folds nothing."""
    import numpy as np

    def box(c, d, m):
        return U.prototype_mesh([{"k": "box", "c": c, "d": d, "yaw": 0.0, "m": m}])
    d = lib / "test_coupe"
    parts = {"body": box([0, 0, 0.2], [4, 1.8, 1.0], "pack_body"),
             "glass": box([0, 0, 1.2], [2, 1.6, 0.4], "pack_glass"),
             "wheel_fl": box([0, 0, -0.3], [0.6, 0.2, 0.6], "pack_wheels"),
             "wheel_fr": box([0, 0, -0.3], [0.6, 0.2, 0.6], "pack_wheels")}
    for k in range(4):
        U.write_glb(parts, {}, d / f"lod{k}.glb")
    b = _build(tmp_path)
    _place(b, [copy.deepcopy(ENTRY)])
    man = _man(b, lib)
    mg = man["vehicles"]["cars"]["test_coupe"]["merged"]
    glass = round(UV.FLAT_GLASS * sum([0.3, 0.33, 0.36]) / 3, 4)
    assert mg["flat"] == {"into": "pack_body", "pack_glass": [glass, UV.FLAT_GLASS_ROUGH],
                          "pack_wheels": list(UV.FLAT_TIRE)}
    mats = []
    for rel in mg["files"]:
        doc, blob = UV._glb(b / rel)
        mats.append([m["name"] for m in doc["materials"]])
    assert mats[0] == mats[1] == ["pack_body", "pack_glass", "pack_wheels_roll"] == \
        mg["materials"]
    # (the glass in the body's section from the pack's opaque_from_lod, 2; the wheels in the
    # last LOD)
    assert mats[2] == ["pack_body", "pack_wheels_roll"] and mats[3] == ["pack_body"]
    prim = doc["meshes"][0]["primitives"][0]
    uv1 = UV._array(doc, blob, prim["attributes"]["TEXCOORD_1"])
    rows = {tuple(round(v, 4) for v in r) for r in uv1.tolist()}
    assert rows == {(0.0, 0.0), (glass, round(-1.0 - UV.FLAT_GLASS_ROUGH, 4)),
                    (UV.FLAT_TIRE[0], round(-1.0 - UV.FLAT_TIRE[1], 4))}
    assert np.all(uv1[:, 1] <= 0.0)
    # (the hover car's test pack: one material for every part, nothing folded)
    assert man["vehicles"]["cars"]["test_hover"]["merged"]["flat"] == {"into": "m"}


def test_traffic_and_fliers_take_the_merged_mesh(lib, tmp_path):
    """car_merge: the traffic's model is its merged mesh, one part drawn as far as a body, its
    wheels rolled within ROLL_M by the first wheel's radius; a hover car (no wheels) rolls
    none; a flier's own meshes are its merged one; a record without `merged` keeps its
    parts."""
    from citygen import unreal_life as UL
    b = _build(tmp_path)
    _place(b, [copy.deepcopy(ENTRY)])
    veh = _man(b, lib)["vehicles"]
    tr = {"models": ["test_coupe", "test_hover"], "slots": [0, 1, 0],
          "weights": {"d01": [1.0, 1.0]}, "paints": {"d01": [[0.5] * 9, [0.4] * 9]}}
    out = UL.traffic_cars(tr, veh, ["d01"])
    assert [p["mesh"] for p in out["parts"]] == [
        "/Game/CityGen/Vehicles/test_coupe/SM_test_coupe_merged",
        "/Game/CityGen/Vehicles/test_hover/SM_test_hover_merged"]
    assert [p["model"] for p in out["parts"]] == [0, 1]
    assert [p["spin_radius"] for p in out["parts"]] == [0.3, 0.0]
    assert [p["roll_m"] for p in out["parts"]] == [UL.ROLL_M, 0.0]
    assert all(p["cull_m"] == UL.TRAFFIC_CULL_M["body"] and p["shadow"] and
               p["pivot"] == [0.0, 0.0, 0.0] for p in out["parts"])
    fl = UL._hover_parts(veh["cars"]["test_hover"], False)
    assert [p["mesh"] for p in fl if p["kind"] == -1] == [
        "/Game/CityGen/Vehicles/test_hover/SM_test_hover_merged"]
    plain = copy.deepcopy(veh)
    for rec in plain["cars"].values():
        rec.pop("merged")
    out = UL.traffic_cars(tr, plain, ["d01"])
    assert len(out["parts"]) == 6 and not any(p.get("roll_m") for p in out["parts"])
