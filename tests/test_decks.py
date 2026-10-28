"""M14 layered districts: the deck plan (upper streets, ramps, wells, stairs and elevators,
upper lots), levels on every street, lot, walkway and prop, the deck checks (and that they
fail on broken copies), stable ids, that a city without decks carries none of it, and the
layered sample Vesper Bay Decks (golden hashes, model and blockout plan)."""

import copy
import hashlib
import json
import re

import pytest

from citygen import deck_checks as DC
from citygen import decks as DK
from citygen.build import build_city
from citygen.model import COLLECTIONS, CityModel, Lot, Walkway
from citygen.validate import validate_spec
from conftest import GOLDEN, ROOT, SMALL, built_sample

DECKS = ROOT / "cities" / "vesper_bay_decks" / "city_spec.json"


def deck_data() -> dict:
    d = copy.deepcopy(SMALL)
    for x in d["districts"]:
        if x["name"] == "Core":
            x["decks"] = {}
    return d


@pytest.fixture(scope="module")
def decked():
    res = validate_spec(deck_data())
    assert res.ok, res.issues
    return build_city(res)


def test_cities_without_decks_carry_no_levels():
    """The M14 fields are left out of a city's JSON where they are at their default."""
    lot = Lot.model_validate({"id": "d01.lot.e0n0", "block_id": "b", "district_id": "d01",
                              "archetype": "old_town", "area_m2": 1.0,
                              "polygon": {"exterior": [[0, 0], [1, 0], [1, 1]]}})
    assert "level" not in json.loads(lot.model_dump_json())
    w = Walkway(id="wk.e0n0", kind="sidewalk", line=[(0, 0, 0), (1, 0, 0)], width_m=2.0)
    assert "level" not in json.loads(w.model_dump_json())
    m = CityModel(name="x", seed=1, bounds=(0, 0, 1, 1))
    assert '"decks"' not in m.to_json()


def test_spec_decks_are_checked():
    d = deck_data()
    d["districts"][0]["decks"] = {"height_m": 5.0}
    assert not validate_spec(d).ok
    d["districts"][0]["decks"] = {"upper": "midtown_mixed", "cover": 0.3}
    assert validate_spec(d).ok


def test_ramp_profile_keeps_its_grade():
    for L in (DK.ramp_need(9.0), 140.0, 200.0):
        prof = DK.ramp_profile(L, 9.0)
        assert prof[0] == (0.0, 9.0) and prof[-1] == (round(L, 2), 0.0)
        for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
            if s1 > s0:
                assert abs(z1 - z0) / (s1 - s0) <= DK.RAMP_GRADE + 0.002


def test_the_deck_passes_every_check(decked):
    m = decked.model
    assert len(m.decks) == 1
    ids = {c.id for c in decked.checks}
    assert {"deck_columns", "deck_headroom", "deck_light", "deck_links", "deck_levels"} <= ids
    assert not [f for c in decked.checks for f in c.failures]


def test_levels_on_streets_lots_walkways_props(decked):
    m = decked.model
    dk = m.decks[0]
    up = [s for s in m.road_segments if s.attrs.get("deck") and
          s.attrs.get("role") != "deck_ramp"]
    assert up and all(s.level == 1 and all(z.z == dk.top_m for z in s.z_profile) for s in up)
    ramps = [s for s in m.road_segments if s.attrs.get("role") == "deck_ramp"]
    assert ramps and all(not s.one_way and s.lanes == 2 for s in ramps)
    # (the deck's streets and ramps name its district: the blockout joins them under it)
    assert all(s.district_ids == [dk.district_id] for s in up + ramps)
    assert any(lt.level == 1 for lt in m.lots)
    assert any(lt.attrs.get("deck_under") for lt in m.lots)
    assert any(ln.level == 1 for ln in m.lanes)
    assert any(w.level == 1 for w in m.walkways)
    assert any(p.level == 1 for p in m.props) and any(p.level == 1 for p in m.plants)
    assert {b.level for b in m.buildings} == {0, 1}
    kinds = sorted(m.walkways[i].kind for i in range(len(m.walkways))
                   if m.walkways[i].id in set(dk.walkway_ids))
    assert kinds.count("stairs") >= 2 and kinds.count("elevator") >= 2
    # no tree under the slab, lights hung from it
    poly = DK.G.from_model_poly(dk.polygon)
    from shapely.geometry import Point
    assert not [p for p in m.plants if not p.level and p.type.split(".")[1] in DK.TREES and
                poly.contains(Point(p.position[:2]))]
    assert any(p.attrs.get("mount") == "deck" for p in m.props)


def test_walkways_join_every_level(decked):
    """One walkway component holds the ground's sidewalks and the deck's; the stairs and
    elevators have a ground neighbor at their foot and a deck neighbor at their head."""
    from citygen.street_checks import walk_components

    m = decked.model
    roots = walk_components(m)
    ground = {roots[DK.walk_ends(w)[0]] for w in m.walkways if not w.level and
              w.kind == "sidewalk" and abs(w.line[0][0]) < 900}
    deck = {roots[DK.walk_ends(w)[0]] for w in m.walkways if w.level and DK.on_ground(w)}
    assert deck and deck <= ground


def test_deck_checks_fail_on_broken_copies(decked):
    m = decked.model
    dk = m.decks[0]
    cols = set(dk.column_ids[: len(dk.column_ids) // 2])
    broken = m.model_copy(update={"structures": [s for s in m.structures if s.id not in cols]})
    assert DC.check_columns(broken).failures
    under = next(b for b in m.buildings if b.attrs.get("deck_under"))
    d = under.model_dump(mode="python")
    d["masses"][0]["z1_m"] = dk.top_m + 5.0
    tall = type(under).model_validate(d)
    broken = m.model_copy(update={"buildings": [tall if b.id == under.id else b
                                                for b in m.buildings]})
    assert DC.check_headroom(broken).failures
    links = set(dk.walkway_ids)
    broken = m.model_copy(update={"walkways": [w for w in m.walkways if w.id not in links]})
    assert DC.check_links(broken).failures
    d = dk.model_dump(mode="python")
    d["attrs"] = {**d["attrs"], "light_m": 5.0}
    broken = m.model_copy(update={"decks": [type(dk).model_validate(d)]})
    assert DC.check_light(broken).failures


def test_deck_ids_come_from_what_and_where(decked):
    from test_edit import BUILD_ORDER

    from citygen import edit as E

    d = decked.model.model_dump(mode="json")
    ids = [e["id"] for c in COLLECTIONS for e in d.get(c, [])]
    assert len(ids) == len(set(ids))
    extra = re.compile(r"(^|\.)(rw|up|deck|st|el|wk|rs|rn|l1)\d+[a-z]?(\.|$)")
    assert not [i for i in ids if BUILD_ORDER.search(i) or extra.search(i)]
    have = set(ids)
    missing = [(e["id"], r) for c in COLLECTIONS for e in d.get(c, []) for r in E._refs(c, e)
               if r not in have and not (c == "rivers" and r == "sea")]
    assert not missing, missing[:10]
    assert all(re.fullmatch(r"d\d\d\.lot\.[ew]\d+[ns]\d+(\.\d+)?\.l1", lt["id"])
               for lt in d["lots"] if lt.get("level"))
    assert all(n["id"].endswith(".l1") for n in d["road_nodes"] if n.get("level") == 1 and
               "deck" in n["attrs"])


def test_the_layered_sample_golden_hashes():
    from citygen import blockout as BO

    golden = json.loads(GOLDEN.read_text())
    b, _, data = built_sample(DECKS)
    assert b.passed, [c.failures for c in b.checks if not c.passed]
    assert b.model.decks
    assert hashlib.sha256(data).hexdigest() == golden["deck_cities"]["vesper_bay_decks"]
    plan = BO.make_plan(b.model)
    assert BO.plan_sha256(plan) == golden["blockout_plans"]["vesper_bay_decks"]
    assert plan["cameras"].get("deck") is not None


def test_briefs_of_deck_buildings_stand_on_the_deck(decked):
    """assetgen: a building on a deck counts its floors from the deck top."""
    from assetgen import brief as B

    m = decked.model
    briefs = B.build_briefs(m)["briefs"]
    up = [b for b in m.buildings if b.level]
    assert up
    for b in up:
        fg = briefs[b.id]["building"]["floor_grid"]
        assert fg["level"] == 1 and fg["deck_m"] == m.decks[0].top_m
    flat = next(b for b in m.buildings if not b.level)
    assert "level" not in briefs[flat.id]["building"]["floor_grid"]


def test_unreal_manifest_carries_the_levels(decked, tmp_path):
    """The exporter (M15): deck actors carry their level, the manifest lists the decks with
    their slab actors, and the lane and walkway graphs a level per element."""
    from test_unreal import _blockout_files

    from citygen import unreal as U

    m = decked.model
    man, _, graphs = U.build_manifest(_blockout_files(m, tmp_path / "b"))
    objs = {o["key"]: o for t in man["tiles"] for o in t["objects"]}
    (dk,) = man["decks"]
    assert dk["id"] == m.decks[0].id and dk["top_m"] == m.decks[0].top_m and dk["keys"]
    assert all(objs[k]["level"] == 1 and objs[k]["category"] == "deck_slab"
               for k in dk["keys"])
    up = [b for b in m.buildings if b.level]
    assert all(objs[b.id]["level"] == 1 for b in up if b.id in objs)
    assert not [o for o in objs.values() if o["category"] == "building" and
                o.get("level") and o["key"] not in {b.id for b in up}]
    for g, coll in (("walkways", m.walkways), ("lanes", m.lanes)):
        lv = dict(zip(graphs[g]["ids"], graphs[g]["levels"]))
        assert all(lv[x.id] == x.level for x in coll)
