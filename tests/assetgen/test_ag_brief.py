"""Briefs: every building has one, valid against the schema, with edge classes, neighbors,
mounted props and the spec's sections; hashes; `brief diff`; a district regeneration
changes only its district's and seam's briefs."""

import json

import pytest

from assetgen import brief as B
from assetgen import briefdiff as D
from assetgen import briefmodel as BM
from assetgen import canon as C
from assetgen.cli import EXIT_INVALID, EXIT_OK, main

from agtools import small_build, small_regen, write


@pytest.fixture(scope="module")
def doc():
    return json.loads((small_build() / "base" / "assets" / "briefs.json").read_text())


@pytest.fixture(scope="module")
def model():
    return json.loads((small_build() / "base" / "city_model.json").read_text())


def test_every_building_has_a_valid_brief(doc, model):
    ids = sorted(b["id"] for b in model["buildings"])
    assert sorted(doc["briefs"]) == ids == sorted(doc["hashes"])
    assert doc["count"] == len(ids)
    for bid, br in doc["briefs"].items():
        BM.Brief.model_validate(br)
        assert doc["hashes"][bid] == C.digest(br)


def test_brief_file_is_canonical(doc):
    text = (small_build() / "base" / "assets" / "briefs.json").read_text(encoding="utf-8")
    assert text == C.dumps(doc) + "\n"
    assert doc["model_sha256"] == C.sha256_bytes(
        (small_build() / "base" / "city_model.json").read_bytes())


def test_edge_classes(doc):
    seen = {}
    for br in doc["briefs"].values():
        for e in br["edges"]:
            seen[e["class"]] = seen.get(e["class"], 0) + 1
            assert e["regions"] or e["class"] == "hidden"
            for r in e["regions"]:
                assert 0.0 <= r["s"][0] < r["s"][1] <= e["length_m"] + 0.001
                assert r["z"][0] < r["z"][1]
            # the regions tile the facade: their areas add up to length x height
            z = br["masses"][e["mass"]]["z"]
            area = sum((r["s"][1] - r["s"][0]) * (r["z"][1] - r["z"][0]) for r in e["regions"])
            assert area == pytest.approx(e["length_m"] * (z[1] - z[0]), rel=1e-3, abs=0.05)
    for c in ("front", "street", "alley", "party", "blind", "open", "upper", "hidden",
              "canal", "park"):
        assert seen.get(c, 0) > 0, c


def test_front_faces_the_main_frontage(doc):
    n = good = 0
    for br in doc["briefs"].values():
        lot = br["lot"]
        if lot is None:
            continue
        for e in br["edges"]:
            for r in e["regions"]:
                if r["class"] == "front":
                    n += 1
                    good += r["ref"] == lot["main_segment_id"]
    assert n > 0 and good == n


def test_party_walls_are_mutual(doc):
    """Neighbors are mutual, and a party or blind region names one of them."""
    for bid, br in doc["briefs"].items():
        names = {nb["id"] for nb in br["neighbors"]}
        for e in br["edges"]:
            for r in e["regions"]:
                if r["class"] in ("party", "blind"):
                    assert r["ref"] in names
                    other = doc["briefs"][r["ref"]]
                    assert bid in {nb["id"] for nb in other["neighbors"]}


def test_mounted_props_and_lookups(doc, model):
    kinds = {}
    for br in doc["briefs"].values():
        for p in br["props"]:
            kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
            assert p["at"] is not None
        for s in br["sign_slots"]:
            # (M20: a holo-board in front of a facade stands off its walls, as one over a roof)
            assert s["mount"] in ("roof", "front") or s["at"] is not None
    for k in ("sign", "awning"):
        assert kinds.get(k, 0) > 0, k
    on = sum(p["on_wall"] for br in doc["briefs"].values() for p in br["props"])
    assert on >= 0.75 * sum(kinds.values())
    slots = sum(len(br["sign_slots"]) for br in doc["briefs"].values())
    assert slots == sum(1 for s in model["sign_slots"] if s["building_id"])
    pois = sum(len(br["pois"]) for br in doc["briefs"].values())
    assert pois == sum(1 for p in model["pois"] if p["building_id"])


def test_spec_sections(doc):
    br = next(iter(doc["briefs"].values()))
    sp = br["spec"]
    assert sp["uniqueness"] == "U1" and sp["era"] == br["building"]["style"]["era"]
    assert sp["era_style"]["systems"]


def test_spec_changes_only_its_district(tmp_path, model):
    """An asset spec entry for one district changes only that district's briefs."""
    base = small_build() / "base"
    spec = write(tmp_path, {"districts": {"Harbor": {"wear": 1.5}}}, "asset_spec.json")
    assert main(["brief", str(base), "--spec", str(spec), "--out", str(tmp_path / "a"),
                 "--no-preview"]) == EXIT_OK
    d = D.diff(base / "assets" / "briefs.json", tmp_path / "a" / "briefs.json")
    harbor = next(x["id"] for x in model["districts"] if x["name"] == "Harbor")
    in_harbor = {b["id"] for b in model["buildings"] if b["district_id"] == harbor}
    assert set(d["changed"]) == in_harbor and not d["added"] and not d["removed"]
    assert all(f == ["spec"] for f in d["changed"].values())


def test_diff_cli(tmp_path, capsys):
    base = small_build() / "base"
    assert main(["brief", "diff", str(base), str(base)]) == EXIT_OK
    assert "0 changed" in capsys.readouterr().out
    assert main(["brief", "diff", str(base), str(small_regen()), "--json",
                 str(tmp_path / "d.json")]) == EXIT_INVALID
    d = json.loads((tmp_path / "d.json").read_text())
    assert d["added"] and d["removed"]


def test_regenerated_district_changes_only_its_district_and_seam():
    """M10: Old Quarter regenerated on a new seed; every changed brief is the district's or
    on its seam (its building, or an entity its brief names, changed in the model)."""
    base, regen = small_build() / "base", small_regen()
    ma = json.loads((base / "city_model.json").read_text())
    mb = json.loads((regen / "city_model.json").read_text())
    did = next(x["id"] for x in mb["districts"] if x["name"] == "Old Quarter")
    r = D.seam(ma, mb, base / "assets" / "briefs.json", regen / "assets" / "briefs.json", did)
    assert r["unexplained"] == []
    assert r["own"] > 0 and r["same"] > 0


def test_seam_cli(capsys):
    """#90: `assetgen brief seam BASE REGEN --district NAME` sorts the briefs as `seam` does
    (and the genomes where both builds have their assets: `genome_seam`)."""
    base, regen = small_build() / "base", small_regen()
    assert main(["brief", "seam", str(base), str(regen), "--district", "Old Quarter"]) == \
        EXIT_OK
    out = capsys.readouterr().out
    assert "in Old Quarter" in out and "0 unexplained" in out
    sm = {"district": "d09", "seam_ids": ["b2"], "unexplained": []}
    a = {"buildings": {"b1": {"brief": "h1", "district": "d01", "genes": {"x": 1},
                              "ag15": {"sig": {"system": "s"}}},
                       "b2": {"brief": "h2", "district": "d01", "genes": {"x": 1}},
                       "b3": {"brief": "h3", "district": "d01", "genes": {"x": 1}}}}
    b = json.loads(json.dumps(a))
    b["buildings"]["b2"]["genes"] = {"x": 2}                 # (on the seam: explained)
    b["buildings"]["b3"]["genes"] = {"x": 2}                 # (same brief, other genes)
    b["buildings"]["b1"]["ag15"]["held"] = True
    g = D.genome_seam(a, b, sm)
    assert g == {"outside_same_brief": 2, "genome_changed": ["b3"], "held": 1}


def test_wall_mounts_in_the_building_frame():
    """#88: a facade prop's height in its building's frame: M20 measures it over the ground
    where it hangs, the masses from the building's base (M13); one and the same on a flat
    city or a building with no base."""
    from types import SimpleNamespace
    m = SimpleNamespace(buildings=[SimpleNamespace(base_m=10.0), SimpleNamespace(base_m=None)])
    hill = SimpleNamespace(flat=False, at=lambda x, y: 12.5)
    flat = SimpleNamespace(flat=True, at=lambda x, y: 0.0)
    assert B.frame_z(m, hill, 0, 1.0, 2.0, 4.0) == 6.5
    assert B.frame_z(m, flat, 0, 1.0, 2.0, 4.0) == 4.0
    assert B.frame_z(m, hill, 1, 1.0, 2.0, 4.0) == 4.0
    assert B.frame_z(m, None, 0, 1.0, 2.0, 4.0) == 4.0


def test_load_model_from_dir_and_file():
    base = small_build() / "base"
    m1, h1, d1 = B.load_model(base)
    m2, h2, d2 = B.load_model(base / "city_model.json")
    assert h1 == h2 and d1 == d2 and m1.name == m2.name
