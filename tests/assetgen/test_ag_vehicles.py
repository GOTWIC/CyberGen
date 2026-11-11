"""AG18 step H: AG8's parked cars as the vehicle library's hero vehicles
(`assetgen/parked/`): the district table and paints, the library, the placements on the small
test city (footprints on their carriageway, off the crosswalks and their neighbors, varied),
the contribution replacing AG8's parked car entries, the fallback to AG8's variants without
the library, and what the Unreal exporter and AG16's scene count make of the placements.

The packs here are tiny ones written by the test (a pack.json and four placeholder LOD
files; never the real cache, which `tests/conftest.py` turns off for every other test)."""

import copy
import json
from pathlib import Path

import pytest

from agtools import copy_model, small_build, temp_dir
from assetgen import brief as B
from assetgen import spec as S
from assetgen.parked import build as VB
from assetgen.parked import library as LB
from assetgen.parked import place as PL
from assetgen.parked import table as T

# (length, width, kind, lowest point): the sizes of real packs
CARS = {"tanager_mino": (3.43, 1.87, "wheeled", -0.007),
        "tanager_porter": (5.33, 2.44, "wheeled", -0.007),
        "aurel_regent": (5.92, 2.08, "wheeled", 0.0),
        "orrin_pebble": (2.82, 1.61, "wheeled", -0.007),
        "orrin_lumen": (5.03, 2.0, "wheeled", 0.0),
        "brakk_mule": (6.65, 2.35, "wheeled", 0.0),
        "kestrel_dart": (4.66, 1.99, "hover", 0.317),
        "vex_wraith": (4.4, 2.0, "wheeled", 0.0)}


def make_lib(root: Path) -> Path:
    for car, (L, W, kind, z0) in CARS.items():
        d = root / car
        d.mkdir(parents=True)
        for k in range(4):
            (d / f"lod{k}.glb").write_bytes(b"glTF placeholder")
        pk = {"format": "cybergen.vehicle_pack", "version": 1, "car": car,
              "title": car.replace("_", " ").title(), "kind": kind,
              "dimensions": {"length": L, "width": W, "height": 1.5,
                             "min": [-L / 2, -W / 2, z0], "max": [L / 2, W / 2, 1.5]},
              "lods": [{"lod": k, "file": f"lod{k}.glb", "triangles": 100000 >> (2 * k)}
                       for k in range(4)],
              "parts": [{"name": "body"}, {"name": "glass"}] +
                       ([] if kind == "hover" else [{"name": f"wheel_{t}"} for t in
                                                    ("fl", "fr", "rl", "rr")]),
              "colors": {"primary": {"color": [0.5, 0.1, 0.1]}},
              "size_class": {"name": "standard"}}
        (d / "pack.json").write_text(json.dumps(pk))
    return root


_CITY: dict = {}


def city():
    """The small test city with AG8's props (no textures), and a library: (model, sha,
    assets dir, library)."""
    if not _CITY:
        from assetgen.props.build import build as props_build
        src = small_build() / "base"
        d = temp_dir("ag_vehicles")
        bdir = copy_model(src, d / "city")
        (bdir / "assets").mkdir()
        (bdir / "assets" / "briefs.json").write_bytes(
            (src / "assets" / "briefs.json").read_bytes())
        model, sha, _ = B.load_model(bdir)
        props_build(model, sha, bdir / "assets", None, workers=2)
        _CITY.update(model=model, sha=sha, out=bdir / "assets", lib=make_lib(d / "lib"))
    return _CITY["model"], _CITY["sha"], _CITY["out"], _CITY["lib"]


def _doc(lib, **kw):
    return {"vehicles": {"parked": "packs", "library": str(lib), "weights": {}, **kw}}


def test_table():
    cars = list(CARS)
    core = T.weights("corporate_core", 0.9, 0.15, cars)
    old = T.weights("old_town", 0.3, 0.65, cars)
    port = T.weights("industrial_port", 0.35, 0.55, cars)
    assert "vex_wraith" not in core and "vex_wraith" not in old
    share = lambda w, cs: sum(w.get(c, 0) for c in cs) / sum(w.values())  # noqa: E731
    assert share(core, ["aurel_regent"]) > 3 * share(old, ["aurel_regent"])
    assert share(old, ["tanager_mino", "tanager_porter"]) > 0.5
    assert share(port, ["brakk_mule", "tanager_porter"]) > 0.5
    assert share(core, ["kestrel_dart"]) < 0.06
    assert T.weights("old_town", 0.3, 0.65, cars, {"tanager_mino": 0})["tanager_porter"] > 0
    assert "tanager_mino" not in T.weights("old_town", 0.3, 0.65, cars, {"tanager_mino": 0})
    # every model of the table is a class and a role; rows are as long as the models
    assert set(T.MODELS) == set(T.CLASS) == set(T.ROLE)
    assert all(len(r) == len(T.MODELS) for r in T._ROWS.values())
    # paint: linear, deterministic, the variety turn draws again
    p, hx = T.paint("tanager_cab", "entertainment_market", "d01.prop.parked_vehicle.e1n1")
    assert p == T.paint("tanager_cab", "entertainment_market",
                        "d01.prop.parked_vehicle.e1n1")[0]
    assert len(p) == 3 and all(0.0 <= c <= 1.0 for col in p for c in col)
    assert T.lin("#ffffff") == [1.0, 1.0, 1.0] and T.lin("#000000") == [0.0, 0.0, 0.0]
    hexes = {T.paint("tanager_cab", None, "x", k)[1] for k in range(12)}
    assert len(hexes) > 2


def test_library(tmp_path, monkeypatch):
    lib = make_lib(tmp_path / "lib")
    got, cars = LB.load(_doc(lib))
    assert got == lib and sorted(cars) == sorted(c for c in CARS if not c.startswith("vex"))
    assert cars["kestrel_dart"]["kind"] == "hover" and cars["kestrel_dart"]["min"][2] == 0.317
    (lib / "orrin_lumen" / "lod2.glb").unlink()            # a pack missing a LOD is not used
    assert "orrin_lumen" not in LB.load(_doc(lib))[1]
    monkeypatch.setenv(LB.ENV, "off")
    assert LB.library_dir(None) is None
    monkeypatch.setenv(LB.ENV, str(lib))
    assert LB.library_dir(None) == lib
    monkeypatch.delenv(LB.ENV)
    monkeypatch.setenv(LB.EXPORTER_ENV, str(tmp_path))
    assert LB.library_dir(None) == tmp_path


def test_spec_option():
    """The spec's `vehicles` is left out of its dump while unset (every hash as before)."""
    assert "vehicles" not in S.dump(S.fill(S.AssetSpec()))
    s = S.AssetSpec.model_validate({"vehicles": {"parked": "variants"}})
    assert S.dump(S.fill(s))["vehicles"]["parked"] == "variants"
    with pytest.raises(ValueError):
        S.AssetSpec.model_validate({"vehicles": {"parked": "maybe"}})


def test_parked_on_the_small_city():
    model, sha, out, lib = city()
    props = (out / "unreal_contribution.props.json").read_bytes()
    rep = VB.build(model, sha, out, _doc(lib))
    assert rep["on"], rep.get("why_off")
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    st = rep["stats"]
    assert st["parked"] > 20 and st["placed"] + st["left_out"] == st["parked"]
    assert st["placed"] > st["parked"] * 0.7
    assert "vex_wraith" not in st["by_model"] and len(st["by_model"]) >= 4
    con = json.loads((out / VB.CONTRIB).read_text())
    ag8 = VB.ag8_entries(out)
    assert sorted(e["replaces"][0] for e in con["entries"]) == [e["key"] for e in ag8]
    assert all(e["kind"] == "vehicles" and e["key"] == f"vehicles.parked.{e['tile']}"
               for e in con["entries"])
    # every vehicle at its AG8 car's spot and heading, on the asphalt (a hover car set down)
    at = {pid: (e, xf) for e in ag8 for xf, pid in zip(e["xforms"], e["ids"])}
    for e in con["entries"]:
        for v in e["vehicles"]:
            e8, xf = at[v["id"]]
            assert e8["pivot"] == e["pivot"]
            assert abs(v["xform"][0] - xf[0]) < 2e-3 and abs(v["xform"][1] - xf[1]) < 2e-3
            assert abs(v["xform"][3] - xf[3]) < 0.011
            dz = PL.ROAD_DZ_M - (CARS[v["car"]][3] if CARS[v["car"]][2] == "hover" else 0.0)
            assert abs(v["xform"][2] - (xf[2] + dz)) < 2e-3
            assert len(v["paint"]) == 3
    # AG8's own outputs untouched
    assert (out / "unreal_contribution.props.json").read_bytes() == props
    # an unchanged city writes nothing
    again = VB.build(model, sha, out, _doc(lib), report_always=False)
    assert again["files"]["written"] == []
    # a pack too long for every lane is left out with its reason, not placed
    w = {c: 0 for c in CARS}
    w["brakk_mule"] = 1
    rep2 = VB.build(model, sha, out, _doc(lib, weights=w))
    assert set(rep2["stats"]["by_model"]) <= {"brakk_mule"}
    assert all(r.startswith("no model fits") or r.startswith("no model has")
               for r in rep2["stats"]["left_out_by_reason"])
    assert rep2["stats"]["left_out"] > 0
    assert rep2["stats"]["longest_model_run"] <= PL.MAX_RUN
    VB.build(model, sha, out, _doc(lib))


def test_falls_back_to_variants(monkeypatch):
    """Off (the spec's `variants`, or no library): nothing written, what an earlier run left
    taken away, AG8's props contribution as it was."""
    model, sha, out, lib = city()
    VB.build(model, sha, out, _doc(lib))
    assert (out / VB.CONTRIB).is_file()
    props = (out / "unreal_contribution.props.json").read_bytes()
    rep = VB.build(model, sha, out, _doc(lib, parked="variants"))
    assert not rep["on"] and "variants" in rep["why_off"]
    assert not (out / VB.CONTRIB).exists() and not (out / "vehicles_report.json").exists()
    assert sorted(rep["files"]["removed"]) == sorted(
        [VB.CONTRIB, "vehicles_report.json", "vehicles_report.txt"])
    monkeypatch.setenv(LB.ENV, "off")
    rep = VB.build(model, sha, out, None)
    assert not rep["on"] and rep["files"] == {"written": [], "removed": []}
    assert (out / "unreal_contribution.props.json").read_bytes() == props
    VB.build(model, sha, out, _doc(lib))


def test_exporter_and_scene(tmp_path):
    """The exporter: a placement replacing AG8's entry of its tile takes it out of stage 2
    (with the blockout's prototype), and the placements' library is the one their
    contribution names; AG16's scene count adds the vehicles' components and instances."""
    import test_unreal_vehicles as TV
    from citygen import unreal as U
    from assetgen import scene as SC
    lib = tmp_path / "lib"
    TV._pack(lib, "test_coupe")
    TV._pack(lib, "test_hover", hover=True)
    b = TV._build(tmp_path)
    key = f"prop.parked_car.{TV.TILE}"
    props = {"key": key, "kind": "prop.parked_car", "replaces": [], "pivot": [128, 128, 0],
             "tile": TV.TILE, "hash": "p1", "parts": [
                 {"kind": "prop.parked_car.civic.v0", "glb": "props/variants/x.glb",
                  "node": "prop.parked_car.civic.v0", "asset": "x", "count": 1,
                  "triangles": 10, "xforms": [[-118, -118, 0, 0, 1, 1, 1]],
                  "ids": ["d01.prop.parked_car.e10n10"]}]}
    TV._place(b, [], name="props", other=[props])
    before, _, _ = U.build_manifest(b)
    assert key in U.actor_hashes(before)
    e = copy.deepcopy(TV.ENTRY)
    TV._place(b, [e])
    c = json.loads((b / "assets" / "unreal_contribution.vehicles.json").read_text())
    c["library"] = str(lib)
    (b / "assets" / "unreal_contribution.vehicles.json").write_text(json.dumps(c))
    man, _, _ = U.build_manifest(b)          # (the library the contribution names)
    assert man["vehicles"]["library"] == str(lib.resolve())
    hashes = U.actor_hashes(man)
    assert key not in hashes and e["key"] in hashes
    s2 = man.get("stage2") or {"actors": [], "instances": [], "groups": []}
    assert all(r.get("entry") != key and r["key"] != key
               for r in s2.get("instances", []) + s2.get("actors", []))
    assert key in man["vehicles"]["replaced"]
    sc = SC.count(man)
    v = sc["city"]["vehicles"]
    assert v["vehicles"] == 3 and v["models"] == 2
    # (the coupe: body, glass, two wheels; the hover car: body and glass)
    assert v["components"] == 4 + 2 and v["instances"] == 2 * 4 + 2
    assert sc["city"]["actors"] == len(hashes)
    assert "vehicles" not in SC.count(before)["city"]
