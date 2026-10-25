"""M4: blockout plan, 2D map and exports, and (when Blender is installed) the Blender build."""

import copy
import json
import re
import xml.etree.ElementTree as ET

import pytest

from citygen import blockout as BO
from citygen import exports as X
from citygen.build import build_city
from citygen.validate import validate_spec

from conftest import CITIES, GOLDEN, SMALL, built_sample

INK = "{http://www.inkscape.org/namespaces/inkscape}"


@pytest.fixture(scope="module")
def small():
    result = validate_spec(copy.deepcopy(SMALL))
    assert result.ok
    return build_city(result).model


@pytest.fixture(scope="module")
def small_plan(small):
    return BO.make_plan(small)


def test_ribbon_offsets_and_miters():
    left, right = BO.ribbon([(0, 0), (10, 0)], 4.0, z=0.5)
    assert left == [[0.0, 2.0, 0.5], [10.0, 2.0, 0.5]]
    assert right == [[0.0, -2.0, 0.5], [10.0, -2.0, 0.5]]
    # a right angle: the miter vertex sits on the diagonal, sqrt(2) times the half width out
    left, right = BO.ribbon([(0, 0), (10, 0), (10, 10)], 4.0)
    assert left[1][:2] == [8.0, 2.0] and right[1][:2] == [12.0, -2.0]
    # a hairpin: the miter is capped at twice the half width
    left, _ = BO.ribbon([(0, 0), (10, 0), (0, 0.5)], 2.0)
    assert abs(left[1][0] - 10.0) <= 2.0 + 1e-9
    assert BO.ribbon([(1, 1), (1, 1)], 3.0) is None


def test_z_profile_interpolation():
    from citygen.model import ZSample

    prof = [ZSample(s=0, z=0), ZSample(s=10, z=5), ZSample(s=10, z=5), ZSample(s=30, z=5)]
    assert BO._z_along([(0, 0), (5, 0), (10, 0), (40, 0)], prof) == [0.0, 2.5, 5.0, 5]


def test_plan_covers_the_model(small, small_plan):
    plan = small_plan
    names = [o["name"] for o in plan["objects"]]
    assert len(names) == len(set(names)), "object names must be unique"
    with_masses = {b.id for b in small.buildings if any(
        ms.z1_m > ms.z0_m and ms.role != "void" for ms in b.masses)}
    built = {o["name"] for o in plan["objects"] if o["category"] in ("building", "landmark")}
    assert with_masses <= built
    assert {s.id for s in small.skybridges} <= set(names)
    tiles = {t["name"] for t in plan["tiles"]}
    assert {o["tile"] for o in plan["objects"]} <= tiles
    joined_ids = ";".join(o["props"].get("citygen_ids", "") for o in plan["objects"])
    for s in small.sidewalks[:50]:
        assert s.id in joined_ids
    assert set(plan["materials"]) == {p["m"] for o in plan["objects"] for p in o["parts"]}
    for color in plan["materials"].values():
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", color)
    for o in plan["objects"]:
        assert o["collection"][0] == small.name and o["parts"]
        for p in o["parts"]:
            if p["k"] in ("prism", "flat"):
                assert len(p["r"]) >= 3 and all(len(h) >= 3 for h in p["h"])
                assert BO._signed_area(p["r"]) > 0, o["name"]
                assert all(BO._signed_area(h) < 0 for h in p["h"]), o["name"]
            if p["k"] == "prism":
                assert p["z1"] > p["z0"], o["name"]
            if p["k"] == "ribbon":
                assert len(p["l"]) == len(p["rr"]) >= 2
    x0, y0, x1, y1 = small.bounds
    for o in plan["objects"]:
        for p in o["parts"]:
            for pt in p.get("r") or p.get("l") or []:
                assert x0 - 50 <= pt[0] <= x1 + 50 and y0 - 50 <= pt[1] <= y1 + 50


def test_plan_cameras(small, small_plan):
    cams = small_plan["cameras"]
    assert len(cams["districts"]) == len(small.districts)
    assert 1 <= len(cams["street"]) <= 4
    for v in cams["street"]:
        assert v["eye"][2] == 1.7 and v["target"] != v["eye"]
    d = cams["iso_dir"]
    assert abs(sum(c * c for c in d) - 1.0) < 1e-5 and d[2] < 0


def test_plan_is_deterministic(small, small_plan):
    assert BO.plan_json(BO.make_plan(small)) == BO.plan_json(small_plan)


def test_golden_plan_hashes():
    """sha256 of each sample's blockout plan, as committed: the plan, like the model, is the
    same bytes on every machine (Blender only draws it)."""
    golden = json.loads(GOLDEN.read_text())["blockout_plans"]
    wrong = []
    for path in CITIES:
        built, _, _ = built_sample(path)
        got = BO.plan_sha256(BO.make_plan(built.model))
        if got != golden[path.parent.name]:
            wrong.append(f"{path.parent.name}: {got} (golden {golden[path.parent.name]})")
    assert not wrong, "blockout plans differ from the golden hashes:\n" + "\n".join(wrong)


def test_map_svg_layers(small, tmp_path):
    path = X.map_svg(small, tmp_path / "map.svg")
    root = ET.parse(path).getroot()
    layers = {g.get(INK + "label"): g for g in root.iter("{http://www.w3.org/2000/svg}g")
              if g.get(INK + "groupmode") == "layer"}
    for name in ("sea", "coast", "water", "district", "park", "plaza", "pier", "megasite",
                 "highway", "avenue", "street", "alley", "pedestrian", "elevated road",
                 "building", "landmark", "transit", "labels", "legend"):
        assert name in layers, name
    blds = list(layers["building"])
    assert len(blds) == sum(1 for b in small.buildings if b.footprint is not None
                            and not b.landmark)
    for el in blds[:100]:
        assert float(el.get(INK + "label")) > 0  # the height, as in the traced maps
    for el in list(layers["street"])[:20]:
        assert float(el.get("stroke-width")) > 0


def test_map_png(small, tmp_path):
    path = X.map_png(small, tmp_path / "map.png", dpi=40)
    assert path.stat().st_size > 10_000


def test_legacy_plan_for_the_unreal_script(small):
    plan = X.legacy_plan(small, [1.0, 2.0, 1.7])
    cats = {p["cat"] for p in plan["primitives"]}
    # the categories unreal/build_greybox_unreal.py has colors for
    known = {"water", "ground", "pier", "bridge", "highway", "avenue", "street", "plaza",
             "green", "canal", "podium", "tower", "lowrise", "landmark"}
    assert cats <= known and {"water", "ground", "street", "lowrise"} <= cats
    assert plan["meta"]["player_start"] == [1.0, 2.0, 1.7]
    for p in plan["primitives"]:
        assert p["kind"] in ("box", "cyl") and len(p["center"]) == len(p["size"]) == 3
        assert min(p["size"]) > 0


def test_graphs_and_props(small):
    g = X.graphs(small)
    assert len(g["lanes"]) == len(small.lanes) and len(g["walkways"]) == len(small.walkways)
    ids = {w["id"] for w in g["walkways"]}
    assert all(n in ids for w in g["walkways"][:200] for n in w["neighbors"])
    assert X.props_csv(small).splitlines()[0] == ",".join(X.PROP_FIELDS)


@pytest.mark.skipif(BO.find_blender() is None, reason="Blender not installed")
def test_blender_build_small_city(small, tmp_path):
    """The whole blockout in Blender: .blend (reopened and counted), USD, glTF per tile,
    renders, every check passing."""
    model = tmp_path / "city_model.json"
    model.write_text(small.to_json() + "\n", encoding="utf-8")
    rep = BO.run_blockout(model, tmp_path / "out", res=240, samples=1)
    assert rep["passed"], [c for c in rep["checks"] if not c["passed"]]
    ids = {c["id"] for c in rep["checks"]}
    assert {"blend_opens", "blend_objects", "blend_buildings", "gltf_tiles", "usd_export",
            "renders"} <= ids
    out = tmp_path / "out"
    assert (out / "city.blend").is_file() and (out / "city.usdc").is_file()
    assert (out / "render_top.jpg").is_file()
    assert len(list((out / "tiles").glob("*.glb"))) == len(
        {o["tile"] for o in json.loads((out / "blockout_plan.json").read_text())["objects"]})


def test_map_svg_reads_in_the_traced_map_pipeline(small, tmp_path):
    """pipeline/svg_to_plan.py (the hand-traced map converter) reads the citygen map: every
    building, with its height from the object label."""
    import subprocess
    import sys

    from conftest import ROOT

    svg = X.map_svg(small, tmp_path / "map.svg")
    (tmp_path / "legacy").mkdir()
    proc = subprocess.run([sys.executable, str(ROOT / "pipeline" / "svg_to_plan.py"), str(svg),
                           str(tmp_path / "legacy")], capture_output=True, text=True,
                          timeout=600)
    assert proc.returncode == 0, proc.stderr
    line = next(x for x in proc.stdout.splitlines() if x.startswith("{"))
    stats = json.loads(line[:line.rindex("}") + 1])
    # it skips footprints under 4 m2 (kiosks), nothing else
    want = sum(1 for b in small.buildings if b.footprint is not None)
    assert 0.99 * want <= stats["buildings"] <= want
    geo = json.loads((tmp_path / "legacy" / "geometry.json").read_text())
    assert sum(1 for b in geo["buildings"] if b.get("height_source") == "label") == \
        stats["buildings"]
