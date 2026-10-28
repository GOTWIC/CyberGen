"""M10: stable ids, district regeneration, pins and overrides, locked cities, model diff."""

import copy
import json
import re

import pytest
import shapely
from shapely.geometry import Point

from conftest import MINIMAL, SMALL

from citygen import build as B
from citygen import diff as DF
from citygen import edit as E
from citygen import geom as G
from citygen import ids as ID
from citygen import lock as LK
from citygen import overrides as OV
from citygen.cli import main
from citygen.model import COLLECTIONS, CityModel
from citygen.validate import validate_spec

REGEN = "Old Quarter"     # old town on the coast, east of the core: land borders and roads
_CACHE: dict = {}


def small():
    """(the spec data, the built city, its build state), built once."""
    if "small" not in _CACHE:
        data = copy.deepcopy(SMALL)
        b = B.build_city(validate_spec(data))
        _CACHE["small"] = (data, b, E.new_state(data, b))
    return _CACHE["small"]


def regenerated(name: str = REGEN, seed: int | None = None, state: dict | None = None):
    key = (name, seed, json.dumps(state, sort_keys=True) if state else None)
    if key not in _CACHE:
        _, b, st = small()
        _CACHE[key] = E.regenerate(state or st, b.model, name, seed=seed)
    return _CACHE[key]


def _index(m) -> dict:
    d = m.model_dump(mode="json") if hasattr(m, "model_dump") else m
    return {e["id"]: (c, e) for c in COLLECTIONS for e in d.get(c, [])}


def _anchor_point(e: dict):
    a = E._anchor(e)
    return None if a is None else Point(a)


# --- stable ids ----------------------------------------------------------------------

BUILD_ORDER = re.compile(r"(^|\.)(rn|rs|jn|cw|sw|ln|lc|wk|br|st|tl|pl|os|lm|isl|r|sep|blk|lot|"
                         r"sb|ww|ms|mg|el|gr|col|hedge|lawn|tn|tm|tp)\d+[a-z]?(\.|$)")


def test_ids_come_from_what_and_where():
    _, b, _ = small()
    ids = [e.id for e in b.model.entities()]
    assert len(ids) == len(set(ids))
    counters = [i for i in ids if BUILD_ORDER.search(i)]
    assert not counters, counters[:10]
    m = b.model
    assert all(re.fullmatch(r"d\d\d\.lot\.[ew]\d+[ns]\d+(\.\d+)?", lt.id) for lt in m.lots)
    assert all(s.id.startswith(seg + ".sw") for s in m.sidewalks for seg in [s.segment_id])
    assert all(j.id == "jn." + j.node_id.split(".", 1)[1] for j in m.junctions)
    lot_of = {b.id: b.lot_id for b in m.buildings}
    assert all(bid == f"{lot}.bld" for bid, lot in lot_of.items()
               if lot and ".grp." not in bid and ".mg." not in bid and ".lm." not in bid)


def test_every_reference_names_an_entity():
    _, b, _ = small()
    d = b.model.model_dump(mode="json")
    have = {e["id"] for c in COLLECTIONS for e in d.get(c, [])}
    missing = []
    for c in COLLECTIONS:
        for e in d.get(c, []):
            for r in E._refs(c, e):
                if r not in have and not (c == "rivers" and r == "sea"):
                    missing.append((e["id"], r))
    assert not missing, missing[:10]


def test_no_reference_keeps_a_build_order_id():
    """Every string that is an id before the renaming is renamed wherever it appears (the
    reference table and attrs miss nothing)."""
    _, b, _ = small()
    data = b.model.model_dump(mode="json")
    # undo: the model with build-order ids is gone, so scan for counter-shaped strings
    bad = []

    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for v in x:
                walk(v, path + "[]")
        elif isinstance(x, str) and BUILD_ORDER.search(x) and " " not in x:
            if "m1b_segment" not in path and "split_of" not in path and \
                    "removed_buildings" not in path:
                bad.append((path, x))
    for c in COLLECTIONS:
        for e in data.get(c, []):
            walk(e, c)
    assert not bad, bad[:10]


def test_renaming_again_keeps_every_id():
    _, b, _ = small()
    keep = frozenset(e.id for e in b.model.entities())
    m2, mp = ID.rename(b.model, keep)
    assert m2.to_json() == b.model.to_json()
    assert all(k == v for k, v in mp.items())


def test_collisions_resolve_by_content():
    a = {"id": "x1", "position": [10.2, 5.1, 0.0], "type": "prop.bench", "attrs": {}}
    b2 = {"id": "x2", "position": [10.4, 4.9, 0.0], "type": "prop.bench", "attrs": {}}
    d1 = {"props": [dict(a, id="d01.prop.bench.00001"), dict(b2, id="d01.prop.bench.00002")],
          "districts": [{"id": "d01"}]}
    d2 = {"props": [dict(b2, id="d01.prop.bench.00001"), dict(a, id="d01.prop.bench.00002")],
          "districts": [{"id": "d01"}]}
    ID.rename_data(d1)
    ID.rename_data(d2)
    by1 = {tuple(p["position"]): p["id"] for p in d1["props"]}
    by2 = {tuple(p["position"]): p["id"] for p in d2["props"]}
    assert by1 == by2      # the build order does not decide who gets ".2"
    assert sorted(by1.values()) == ["d01.prop.bench.e10n5", "d01.prop.bench.e10n5.2"]


def test_a_generator_change_leaves_other_ids_alone(monkeypatch):
    """The bench generator changed (it makes no bench now): every entity that is not a bench
    keeps its id and its contents."""
    from citygen import props as PR

    data, b, _ = small()
    orig = PR.build

    def no_benches(spec, m):
        out = orig(spec, m)
        out.rows["props"] = [p for p in out.rows["props"] if p["type"] != "prop.bench"]
        return out

    monkeypatch.setattr(PR, "build", no_benches)
    b2 = B.build_city(validate_spec(copy.deepcopy(data)))
    old, new = _index(b.model), _index(b2.model)
    benches = {i for i, (c, e) in old.items() if e.get("type") == "prop.bench"}
    assert benches
    assert set(new) == set(old) - benches
    changed = [i for i in new if new[i] != old[i]]
    assert not changed, changed[:10]


# --- district regeneration ----------------------------------------------------------

def test_regeneration_keeps_the_city_outside_the_district():
    _, b, st = small()
    r, rec = regenerated()
    assert rec["district"] == REGEN and rec["seed"] != b.spec.district(REGEN).seed
    assert all(c.passed for c in r.checks), [(c.id, c.failures[:2]) for c in r.checks
                                             if not c.passed]
    did = next(d.id for d in b.model.districts if d.name == REGEN)
    old, new = _index(b.model), _index(r.model)
    # the district itself is new
    inside = [i for i, (c, e) in old.items() if c == "buildings" and e["district_id"] == did]
    assert inside and len(set(inside) & set(new)) < len(inside) / 2
    _outside_kept(b, r, REGEN)


def _outside_kept(b, r, name: str) -> None:
    """Every road not inside the district comes back as it was (id, geometry and all), and
    every entity more than 250 m from it too: outside it, only the seam changes."""
    info = r.stats["regenerated"]
    assert info["held_unchanged"] == info["held_segments"]
    did = next(d.id for d in b.model.districts if d.name == name)
    poly = G.from_model_poly(next(d for d in b.model.districts if d.id == did).polygon)
    old, new = _index(b.model), _index(r.model)
    frame = r.frame
    for i, (c, e) in old.items():
        if c == "road_segments" and not frame.inside_row(b.model.index()[i]):
            assert new.get(i) == (c, e), i
    far = [(c, i) for i, (c, e) in old.items() if new.get(i) != (c, e) and c != "fields" and
           _anchor_point(e) is not None and _anchor_point(e).distance(poly) > 250.0]
    assert not far, far[:5]


def test_regeneration_of_the_first_district_keeps_the_ones_after_it():
    """The districts laid after the regenerated one are laid again against its old streets
    (`streets._Ghosts`), so they come back as they were, with every road outside it."""
    _, b, st = small()
    first = b.spec.districts[0].name
    r, rec = regenerated(first)
    assert all(c.passed for c in r.checks), [(c.id, c.failures[:2]) for c in r.checks
                                             if not c.passed]
    _outside_kept(b, r, first)


def test_regeneration_with_new_spec_fields():
    data, b, st = small()
    spec2 = copy.deepcopy(data)
    d = next(x for x in spec2["districts"] if x["name"] == "Uptown")
    d["height_m"] = [70, 90]
    r, rec = E.regenerate(st, b.model, "Uptown", spec_data=spec2)
    assert rec["entry"]["height_m"] == [70, 90]
    assert rec["seed"] == b.spec.district("Uptown").seed     # fields changed: same seed
    did = next(x.id for x in b.model.districts if x.name == "Uptown")
    hs = [x.height_m for x in r.model.buildings if x.district_id == did and not x.landmark]
    assert hs and max(hs) > max(x.height_m for x in b.model.buildings
                                if x.district_id == did and not x.landmark)
    assert all(c.passed for c in r.checks), [(c.id, c.failures[:2]) for c in r.checks
                                             if not c.passed]
    _outside_kept(b, r, "Uptown")


def test_choices_keep_the_layout_salt():
    """A city built again with its local layout salted (a whole-city retry) records the salt,
    so a replay and a district regeneration start from the same city."""
    data, b, _ = small()
    ch = dict(B.choices(b), layout_salt=1)
    r = B.replay(validate_spec(copy.deepcopy(data)), ch, local=True, buildings=False)
    assert B.choices(r) == ch


def test_regeneration_keeps_a_lowered_metro():
    """A held metro line comes back at its depth: the tunnel stage lowers it again from the
    mode's base depth, not from the depth it lowered it to before (the minimal city's Line 1
    dips under the Core megatower's foundations only)."""
    data = copy.deepcopy(MINIMAL)
    b = B.build_city(validate_spec(data))
    line = next(ln for ln in b.model.transit_lines if ln.mode == "metro")
    zs = [p[2] for p in line.path]
    assert min(zs) < max(zs)
    r, _ = E.regenerate(E.new_state(data, b), b.model, "Uptown")

    def depths(m):
        return {s.id: s.attrs["track_z_m"] for s in m.stations if "track_z_m" in s.attrs}
    assert depths(b.model) and depths(r.model) == depths(b.model)


def test_regeneration_is_deterministic():
    _, b, st = small()
    r, rec = regenerated()
    r2, rec2 = E.regenerate(st, b.model, REGEN, seed=rec["seed"])
    assert r2.model.to_json() == r.model.to_json()


# --- pins and overrides ------------------------------------------------------------

def _pick_building(m, did):
    return next(x for x in sorted(m.buildings, key=lambda x: -x.height_m)
                if x.district_id == did and not x.landmark and x.lot_id)


def test_pins_survive_a_regeneration():
    _, b, st = small()
    did = next(d.id for d in b.model.districts if d.name == REGEN)
    tower = _pick_building(b.model, did)
    road = next(s for s in b.model.road_segments
                if s.attrs.get("district") == did and s.road_class == "street")
    ov = {"version": 1, "pins": [tower.id, road.id], "edits": []}
    r, _ = regenerated(state={**st, "overrides": ov})
    idx = r.model.index()
    assert road.id in idx and idx[road.id].centerline == road.centerline
    kept = idx[tower.id]
    assert kept.masses == tower.masses and kept.footprint == tower.footprint
    foot = G.from_model_poly(tower.footprint or tower.masses[0].footprint)
    others = [x.id for x in r.model.buildings if x.id != tower.id and
              G.area(G.inter(G.from_model_poly(x.footprint or x.masses[0].footprint),
                             foot)) > 1.0]
    assert not others
    assert all(e.walkway_id in idx for e in kept.entrances)
    assert all(c.passed for c in r.checks), [(c.id, c.failures[:2]) for c in r.checks
                                             if not c.passed]


def test_override_edits():
    _, b, _ = small()
    m = b.model
    did = m.districts[0].id
    tower = _pick_building(m, did)
    lot = next(lt for lt in m.lots if lt.district_id == did and lt.id != tower.lot_id and
               any(x.lot_id == lt.id for x in m.buildings))
    prop = next(p for p in m.props if p.type == "prop.bench")
    os_ = next(o for o in m.open_spaces if o.district_id and o.name is None)
    road = m.road_segments[0]
    ov = {"version": 1, "pins": [], "edits": [
        {"op": "move", "id": tower.id, "by": [0.5, -0.25]},
        {"op": "replace", "id": tower.id, "height_m": tower.height_m + 30.0},
        {"op": "plaza", "id": lot.id, "name": "Test Square"},
        {"op": "remove", "id": prop.id},
        {"op": "replace", "id": os_.id, "kind": "garden", "name": "Test Garden"},
        {"op": "replace", "id": road.id, "name": "Test Mile"},
        {"op": "move", "id": road.id, "by": [1, 1]}]}
    m2, notes = OV.apply(m, ov)
    idx = m2.index()
    t2 = idx[tower.id]
    assert t2.height_m == pytest.approx(tower.height_m + 30.0)
    assert t2.masses[0].footprint.exterior[0][0] == pytest.approx(
        tower.masses[0].footprint.exterior[0][0] + 0.5)
    assert lot.id not in idx and f"{lot.id}.plaza" in idx
    assert idx[f"{lot.id}.plaza"].kind == "plaza"
    assert not [x for x in m2.buildings if x.lot_id == lot.id]
    assert prop.id not in idx
    assert idx[os_.id].kind == "garden" and idx[os_.id].name == "Test Garden"
    assert idx[road.id].name == "Test Mile" and idx[road.id].centerline == road.centerline
    assert any("skipped" in n and "cannot be moved" in n for n in notes)
    # every reference still names an entity
    have = set(idx)
    d = m2.model_dump(mode="json")
    missing = [(e["id"], r) for c in COLLECTIONS for e in d.get(c, []) for r in E._refs(c, e)
               if r not in have and r != "sea"]
    assert not missing, missing[:5]
    with pytest.raises(OV.OverrideError):
        OV.validate({"pins": [], "edits": [{"op": "paint", "id": "x"}]})


# --- locks ----------------------------------------------------------------------------

def _write_build(tmp_path, built, state):
    from citygen.build import write_outputs

    write_outputs(built, tmp_path, dpi=40)
    E.write_state(tmp_path, state)


def test_a_locked_city_rebuilds_byte_for_byte(tmp_path):
    data, b, st = small()
    r, rec = regenerated()
    state = {**st, "edits": [rec], "overrides": rec["overrides"],
             "model_sha256": rec["model_sha256"]}
    (tmp_path / "city_model.json").write_text(r.model.to_json() + "\n", encoding="utf-8")
    E.write_state(tmp_path, state)
    lk = LK.make(tmp_path, "1.0")
    assert lk["release"] == "1.0" and lk["edits"][0]["district"] == REGEN
    ok, lines, rebuilt = LK.verify(lk)
    assert ok, lines
    assert rebuilt.model.to_json() == r.model.to_json()
    bad = {**lk, "model_sha256": "0" * 64}
    ok2, _, _ = LK.verify(bad)
    assert not ok2


def test_lock_refuses_a_model_edited_by_hand(tmp_path):
    data, b, st = small()
    (tmp_path / "city_model.json").write_text(b.model.to_json().replace(
        '"name":"Testport"', '"name":"Testport 2"') + "\n", encoding="utf-8")
    E.write_state(tmp_path, st)
    with pytest.raises(ValueError):
        LK.make(tmp_path)


def test_lock_refuses_a_build_of_other_code(tmp_path):
    """A release names the code it ships with: a build state from other code is refused,
    not copied into the lock."""
    data, b, st = small()
    (tmp_path / "city_model.json").write_text(b.model.to_json() + "\n", encoding="utf-8")
    E.write_state(tmp_path, {**st, "code_sha256": "0" * 64})
    with pytest.raises(ValueError, match="other citygen code"):
        LK.make(tmp_path)
    E.write_state(tmp_path, st)
    assert LK.make(tmp_path)["code_sha256"] == E.code_version()["code_sha256"]


# --- model diff ---------------------------------------------------------------------

def test_model_diff(tmp_path):
    _, b, _ = small()
    r, _ = regenerated()
    assert DF.diff(b.model, b.model) == {}
    d = DF.diff(b.model, r.model)
    assert "buildings" in d and d["buildings"]["added"] and d["buildings"]["removed"]
    assert "districts" in d and list(d["districts"]["changed"]) == [
        next(x.id for x in b.model.districts if x.name == REGEN)]
    txt = DF.text(d, 2)
    assert "buildings:" in txt and "total:" in txt
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(b.model.to_json(), encoding="utf-8")
    pb.write_text(r.model.to_json(), encoding="utf-8")
    assert main(["model", "diff", str(pa), str(pa)]) == 0
    assert main(["model", "diff", str(pa), str(pb), "--json", str(tmp_path / "d.json")]) == 1
    assert json.loads((tmp_path / "d.json").read_text())["districts"]["changed"]


def test_cli_build_district_and_lock(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SMALL), encoding="utf-8")
    out = tmp_path / "city"
    assert main(["build", str(spec), str(out), "--dpi", "40"]) == 0
    st = json.loads((out / "city_state.json").read_text())
    assert st["edits"] == [] and st["spec"] == SMALL
    _, b, _ = small()
    assert E.model_sha(CityModel.from_json((out / "city_model.json").read_text())) == \
        E.model_sha(b.model)
    r, rec = regenerated()
    assert main(["build", str(spec), str(out), "--district", REGEN, "--dpi", "40"]) == 0
    st = json.loads((out / "city_state.json").read_text())
    assert [e["district"] for e in st["edits"]] == [REGEN]
    assert st["model_sha256"] == E.model_sha(r.model)
    assert main(["lock", str(out), "--release", "2"]) == 0
    lk = json.loads((out / "city.lock.json").read_text())
    assert lk["release"] == "2" and lk["model_sha256"] == st["model_sha256"]
    assert main(["build", str(spec), str(out), "--district", "Nowhere"]) == 2
