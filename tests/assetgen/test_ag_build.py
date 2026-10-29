"""AG1: `assetgen build` on the small test city: every building has a shell and a proxy,
the checks pass, the street stage runs after the buildings, a second build writes no file,
the bytes do not depend on the worker count or the hash seed, a regenerated district
rebuilds only the tiles whose buildings changed, the Unreal contribution covers every
building; the goldens (scope section 10). The street stage's own properties are AG7's
tests (`test_ag_streets.py`)."""

import json
import os
import shutil
import subprocess
import sys

from assetgen import build as BD
from assetgen import canon as C
from assetgen import manifest as MF
from assetgen.brief import load_model
from assetgen.buildings import systems as SY
from assetgen.streets import build as SB

from agtools import (CITIES, HERE, ROOT, built_sample, copy_model, golden, small_assets,
                     small_assets_report, small_regen)


def _manifest(base):
    return json.loads((base / "assets" / "manifest.json").read_text())


def test_every_building_has_a_shell_and_a_proxy():
    base = small_assets()
    rep = small_assets_report()
    assert rep["ok"], {k: v for k, v in rep["checks"].items() if not v["ok"]}
    model, _, _ = load_model(base)
    man = _manifest(base)
    assert sorted(man["buildings"]) == sorted(b.id for b in model.buildings)
    for bid, r in man["buildings"].items():
        assert r["triangles"] > 0 and r["proxy"]["triangles"] > 0, bid
        assert r["checks"]["mesh"]["open_edges"] == 0
        # (AG3: a building its street front takes whole collides as the front is drawn)
        assert r["collision"]["boxes"] or r["collision"]["convex"] or r["front"]["triangles"]
    for t, info in man["tiles"].items():
        for sub in ("tiles", "proxies"):
            data = (base / "assets" / sub / f"{t}.glb").read_bytes()
            assert C.sha256_bytes(data) == info[sub]["sha256"]


def test_checks_are_the_seven():
    rep = small_assets_report()
    assert sorted(rep["checks"]) == ["asset_access", "asset_budget", "asset_coverage",
                                     "asset_envelope", "asset_meshes", "asset_mounts",
                                     "asset_unique"]
    assert rep["checks"]["asset_unique"]["pairs"] > 0


def test_build_writes_buildings_and_streets():
    """`assetgen build` runs AG7's street stage after the buildings: both stages' files, the
    street bytes `assetgen streets` writes (its golden), one verdict for both."""
    base = small_assets()
    rep = small_assets_report()
    st = rep["streets"]
    assert st["ok"] and st["pieces"] > 0 and not st["failed"]
    a = base / "assets"
    for name in BD.DELIVERED + ("streets/manifest.json", "streets/parts.glb",
                                "unreal_contribution.streets.json", "streets_report.json"):
        assert (a / name).is_file(), name
    want = json.loads((HERE / "data" / "golden_streets.json").read_text())["testport"]["all"]
    assert SB.outputs_digest(a)["all"] == want
    uc = json.loads((a / "unreal_contribution.streets.json").read_text())
    assert uc["part"] == "streets" and uc["layer"] == 2


def test_second_build_writes_no_file():
    base = small_assets()
    before = {p: p.stat().st_mtime_ns for p in (base / "assets").rglob("*") if p.is_file()}
    rep = BD.build(base, workers=2, log=lambda *a: None)
    assert rep["files_written"] == 0
    assert rep["tiles_made"] == 0 and rep["streets"]["tiles_made"] == 0
    after = {p: p.stat().st_mtime_ns for p in (base / "assets").rglob("*") if p.is_file()}
    assert after == before


def _tree(d):
    """The building packs and delivered files (the street and props packs have goldens of
    their own)."""
    return {p.relative_to(d).as_posix(): C.sha256_bytes(p.read_bytes())
            for p in sorted(d.rglob("*")) if p.is_file() and
            ((p.suffix == ".glb" and p.parent.parent == d and
              p.parent.name in ("tiles", "proxies", "parts")) or
             (p.parent == d and p.name in BD.DELIVERED))}


def test_bytes_do_not_depend_on_workers(tmp_path):
    base = small_assets()
    one = copy_model(base, tmp_path / "one")
    BD.build(one, workers=1, log=lambda *a: None, streets=False)
    a, b = _tree(one / "assets"), _tree(base / "assets")
    b = {k: v for k, v in b.items() if k in a}
    assert a == b


def test_same_bytes_with_another_hash_seed(tmp_path):
    base = small_assets()
    d = copy_model(base, tmp_path / "hs")
    env = {**os.environ, "PYTHONHASHSEED": "4242"}
    proc = subprocess.run([sys.executable, "-m", "assetgen", "build", str(d), "--workers",
                           "2", "--no-streets"], cwd=ROOT, env=env, capture_output=True,
                          text=True)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert (d / "assets" / "manifest.json").read_bytes() == \
        (base / "assets" / "manifest.json").read_bytes()


def test_regenerated_district_rebuilds_only_changed_tiles(tmp_path):
    base = small_assets()
    regen = small_regen()
    d = copy_model(regen, tmp_path / "regen")
    shutil.copytree(base / "assets", d / "assets")
    old = _manifest(base)
    rep = BD.build(d, workers=2, log=lambda *a: None, streets=False)
    assert rep["ok"]
    new = _manifest(d)
    kept = [t for t in new["tiles"] if t in old["tiles"] and
            new["tiles"][t]["hash"] == old["tiles"][t]["hash"]]
    assert rep["tiles_kept"] == len(kept) > 0
    assert rep["tiles_made"] < len(new["tiles"])
    for t in kept:
        for sub in ("tiles", "proxies", "parts"):
            if (base / "assets" / sub / f"{t}.glb").is_file():
                assert (d / "assets" / sub / f"{t}.glb").read_bytes() == \
                    (base / "assets" / sub / f"{t}.glb").read_bytes()
    for bid, r in new["buildings"].items():
        if bid in old["buildings"] and old["buildings"][bid]["hash"] == r["hash"]:
            assert old["buildings"][bid]["cpd"] == r["cpd"]


def test_unreal_contribution_covers_every_building():
    base = small_assets()
    man = _manifest(base)
    uc = json.loads((base / "assets" / "unreal_contribution.buildings.json").read_text())
    assert uc["stage"] == "assetgen" and uc["layer"] == 2 and uc["part"] == "buildings"
    blds = [e for e in uc["entries"] if e["kind"] == "building"]
    assert [e["key"] for e in blds] == sorted(man["buildings"])
    # (AG3: a street front per building that has one, a decal mesh per tile)
    fronts = {e["key"] for e in uc["entries"] if e["kind"] == "building.front"}
    assert fronts == {f"{k}.front" for k, r in man["buildings"].items()
                      if r["front"]["triangles"]}
    # (AG4: the roof equipment of a tile, `roofs.<tile>`)
    assert {e["kind"] for e in uc["entries"]} <= {"building", "building.front", "decals",
                                                  "roof_equipment"}
    for e in blds:
        r = man["buildings"][e["key"]]
        assert e["glb"] == r["glb"] and e["node"] == f"{e['key']}.shell"
        assert e["pivot"] == r["pivot"] and e["nanite"] and not e["distance_field"]
        assert e["proxy"]["node"] == f"{e['key']}.proxy"
        assert len(e["cpd"]) == SY.CPD_SIZE + 7        # AG1's channels and AG6's
        assert set(e["slots"]) <= set(uc["materials"])


def test_parts_packs_and_their_instances():
    """AG2: every building's instanced parts are meshes of its tile's part pack, placed at
    least eight times, their transforms and building in the contribution."""
    from assetgen.buildings import parts as PT
    base = small_assets()
    man = _manifest(base)
    uc = json.loads((base / "assets" / "unreal_contribution.buildings.json").read_text())
    rep = small_assets_report()
    assert rep["parts"]["instances"] > 0 and rep["parts"]["merged"] > 0
    nodes: dict[str, bytes] = {}
    n = 0
    for e in uc["entries"]:
        if e["kind"] != "building":
            continue
        r = man["buildings"][e["key"]]
        assert len({p["kind"] for p in e["parts"]}) == len(e["parts"])
        assert e["instances"] == sum(p["count"] for p in e["parts"])
        for p in e["parts"]:
            assert p["glb"] == f"parts/{r['tile']}.glb" and p["building"] == e["key"]
            assert p["count"] == len(p["xforms"]) >= PT.INSTANCE_MIN
            assert all(len(x) == 4 for x in p["xforms"])
            assert p["kind"] == p["node"] and p["node"].startswith(p["type"] + ".h")
            if p["glb"] not in nodes:
                nodes[p["glb"]] = (base / "assets" / p["glb"]).read_bytes()
            assert p["node"].encode() in nodes[p["glb"]]
            n += 1
    assert n > 0
    for t, info in man["tiles"].items():
        if info.get("parts"):
            data = (base / "assets" / "parts" / f"{t}.glb").read_bytes()
            assert C.sha256_bytes(data) == info["parts"]["sha256"] and not info["parts"]["bad"]


def test_manifest_keeps_other_sections(tmp_path):
    old = {"buildings": {"a": 1}, "streets": {"x": 2}}
    new = MF.merge(old, {"buildings": {"b": 1}}, ("buildings",))
    assert new == {"buildings": {"b": 1}, "streets": {"x": 2}}
    p = tmp_path / "f.bin"
    assert MF.write_if_changed(p, b"abc") and not MF.write_if_changed(p, b"abc")


def test_small_city_golden():
    base = small_assets()
    g = golden()["ag1"]
    man = (base / "assets" / "manifest.json").read_bytes()
    assert C.sha256_bytes(man) == g["testport_manifest"]
    assert C.digest(_tree(base / "assets")) == g["testport_files"]


def _vesper_bay():
    path = next(p for p in CITIES if p.parent.name == "vesper_bay")
    return built_sample(path)


def test_vesper_bay_buildings_golden():
    """A few Vesper Bay buildings, one per kind: their shells and instanced parts as GLB
    bytes."""
    from assetgen import brief as B
    built, _, _ = _vesper_bay()
    want = golden()["ag1"]["buildings"]["vesper_bay"]
    res = B.build_briefs(built.model)
    got = {k: C.sha256_bytes(BD.building_glb(k, res["briefs"][k])) for k in want}
    assert got == want


def test_golden_file_has_ag1():
    g = golden()["ag1"]
    assert {"testport_manifest", "testport_files", "buildings"} <= set(g)
    assert len(g["buildings"]["vesper_bay"]) >= 5
