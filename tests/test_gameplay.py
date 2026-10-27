"""M11: the gameplay layer; each M11 check with a failing case, the spec controls, the export,
the helpers, determinism of the stage."""

import copy
import functools
import json

import numpy as np
import shapely

from citygen import checks as C
from citygen import exports as X
from citygen import gameplay as GP
from citygen import gameplay_checks as GC
from citygen.build import build_city, with_rows
from citygen.model import CityModel
from citygen.validate import validate_spec

import pytest

from conftest import SMALL

M11_CHECKS = {"poi_reachable_foot", "poi_reachable_car", "poi_places", "territories",
              "gameplay_fields", "street_density", "parking", "travel_points", "sign_slots"}


@pytest.fixture(scope="module")
def city():
    result = validate_spec(copy.deepcopy(SMALL))
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


def _checks(m: CityModel, spec=None) -> dict:
    return {c.id: c for c in GC.run(spec, m)}


def _bare(m: CityModel) -> CityModel:
    return m.model_copy(update={k: [] for k in X.GAMEPLAY})


def test_city_passes_with_gameplay(city):
    failed = [(c.id, c.failures[:3]) for c in city.checks if not c.passed]
    assert not failed, failed
    assert M11_CHECKS <= {c.id for c in city.checks}


def test_build_checks_equal_a_fresh_run(city):
    fresh = {c.id: c for c in C.run_checks(city.spec, city.model)[0]}
    for c in city.checks:
        if c.id in M11_CHECKS:
            assert fresh[c.id].passed == c.passed, c.id


def test_layer_is_complete(city):
    m = city.model
    kinds = {p.kind for p in m.pois}
    assert {"bar", "vendor", "apartment", "fixer"} <= kinds
    assert {f.kind for f in m.factions} >= {"police", "gang"}
    for d in m.districts:
        assert any(z.district_id == d.id and z.kind == "territory" for z in m.zones), d.id
        assert any(z.district_id == d.id and z.kind == "police" for z in m.zones), d.id
    assert {f.kind for f in m.fields} == {"wealth", "danger", "police"}
    assert len(m.densities) == len(m.road_segments)
    assert any(t.kind == "taxi_stand" for t in m.travel_points)
    assert {s.kind for s in m.sign_slots} >= {"shop_sign", "billboard"}
    names = [p.name for p in m.pois] + [t.name for t in m.travel_points]
    assert len(names) == len(set(names))
    for p in m.pois:
        a = p.entrances[0]
        assert a.walkway_id and a.lane_id and a.curb_m <= GP.DRIVE_REACH_M
    st = city.stats["gameplay"]
    assert st["pois"] == len(m.pois)
    rep = city.report()
    assert rep["stage"].startswith("M11")
    assert "gameplay:" in C.report_text(rep)


def test_hideouts_belong_to_gangs(city):
    fac = {f.id: f for f in city.model.factions}
    for p in city.model.pois:
        if p.kind == "hideout":
            assert fac[p.faction_id].kind == "gang"
        if p.kind == "fixer":
            assert p.host_id in {x.id for x in city.model.pois}


# --- failing checks ---------------------------------------------------------------------

def _first_poi(m):
    return next(p for p in m.pois if p.kind != "fixer")


def _with_poi(m, pid, **upd):
    pois = [p.model_copy(update=upd) if p.id == pid else p for p in m.pois]
    return m.model_copy(update={"pois": pois})


def _with_access(m, pid, **upd):
    p = next(x for x in m.pois if x.id == pid)
    acc = [p.entrances[0].model_copy(update=upd)] + p.entrances[1:]
    return _with_poi(m, pid, entrances=acc)


def test_check_foot_fails(city):
    p = _first_poi(city.model)
    bad = _with_access(city.model, p.id, walkway_id="wk999999")
    assert not _checks(bad)["poi_reachable_foot"].passed
    far = _with_access(city.model, p.id, walk_link_m=p.entrances[0].walk_link_m + 3.0)
    assert not _checks(far)["poi_reachable_foot"].passed


def test_check_car_fails(city):
    m = city.model
    p = _first_poi(m)
    hw = next(ln for ln in m.lanes if ln.kind == "lane" and
              next(s for s in m.road_segments if s.id == ln.segment_id).road_class ==
              "highway")
    bad = _with_access(m, p.id, lane_id=hw.id)
    assert not _checks(bad)["poi_reachable_car"].passed
    off = _with_access(m, p.id, curb=(p.entrances[0].curb[0] + 2.0, p.entrances[0].curb[1]))
    assert not _checks(off)["poi_reachable_car"].passed


def test_check_pois_fails(city):
    m = city.model
    a, b = [p for p in m.pois if p.kind != "fixer"][:2]
    dup = _with_poi(m, b.id, name=a.name)
    assert not _checks(dup)["poi_places"].passed
    away = _with_access(m, a.id, position=(a.position[0] + 20.0, a.position[1]))
    assert not _checks(away)["poi_places"].passed


def test_check_zones_fails(city):
    m = city.model
    z = next(z for z in m.zones if z.kind == "territory" and z.block_ids)
    zones = [x.model_copy(update={"block_ids": x.block_ids[1:]}) if x.id == z.id else x
             for x in m.zones]
    assert not _checks(m.model_copy(update={"zones": zones}))["territories"].passed
    pol = [x for x in m.zones if not (x.kind == "police" and x.district_id == z.district_id)]
    assert not _checks(m.model_copy(update={"zones": pol}))["territories"].passed


def test_check_fields_fails(city):
    m = city.model
    f = m.fields[0]
    vals = list(f.values)
    vals[0] = 1.5
    fields = [f.model_copy(update={"values": vals})] + list(m.fields[1:])
    assert not _checks(m.model_copy(update={"fields": fields}))["gameplay_fields"].passed
    assert not _checks(m.model_copy(update={"fields": m.fields[1:]}))["gameplay_fields"].passed


def test_check_density_fails(city):
    m = city.model
    assert not _checks(m.model_copy(update={"densities": m.densities[1:]}))[
        "street_density"].passed
    d = m.densities[0]
    loud = [d.model_copy(update={"traffic_vph": [1e6] * 5})] + list(m.densities[1:])
    assert not _checks(m.model_copy(update={"densities": loud}))["street_density"].passed


def test_check_parking_fails(city):
    m = city.model
    p = m.parking[0]
    rows = [p.model_copy(update={"capacity": 0})] + list(m.parking[1:])
    assert not _checks(m.model_copy(update={"parking": rows}))["parking"].passed


def test_check_travel_fails(city):
    m = city.model
    did = next(t.district_id for t in m.travel_points if t.kind == "fast_travel")
    rows = [t for t in m.travel_points if not (t.kind == "fast_travel" and
                                               t.district_id == did)]
    assert not _checks(m.model_copy(update={"travel_points": rows}))["travel_points"].passed


def test_check_slots_fails(city):
    m = city.model
    shop = next(s for s in m.sign_slots if s.kind == "shop_sign")
    twice = list(m.sign_slots) + [shop.model_copy(update={"id": shop.id + "x"})]
    assert not _checks(m.model_copy(update={"sign_slots": twice}))["sign_slots"].passed
    face = next(s for s in m.sign_slots if s.mount == "facade" and s.kind != "shop_sign")
    low = [s.model_copy(update={"position": (s.position[0], s.position[1], 3.0)})
           if s.id == face.id else s for s in m.sign_slots]
    assert not _checks(m.model_copy(update={"sign_slots": low}))["sign_slots"].passed


# --- spec controls, export, helpers ----------------------------------------------------------

def test_spec_defaults_and_faction(city):
    spec = copy.deepcopy(SMALL)
    filled = validate_spec(spec).filled
    core = filled.district("Core")
    assert (core.wealth, core.danger, core.police) == (0.9, 0.15, 0.9)
    spec["districts"][2]["faction"] = "Harbor Rats"
    spec["districts"][1]["faction"] = "Harbor Rats"
    spec["districts"][1]["danger"] = 0.9
    filled = validate_spec(spec).filled
    out = GP.build(filled, _bare(city.model))
    names = {f["name"]: f for f in out.rows["factions"]}
    assert "Harbor Rats" in names
    held = {z["district_id"] for z in out.rows["zones"]
            if z["faction_id"] == names["Harbor Rats"]["id"]}
    ids = {d.name: d.id for d in city.model.districts}
    assert {ids["Harbor"], ids["Old Quarter"]} <= held


def test_export_indexes_tiles(city):
    g = X.gameplay(city.model)
    assert [b["name"] for b in g["hour_bands"]] == list(GP.BANDS)
    listed = {i for t in g["tiles"].values() for i in t.get("pois", [])}
    assert listed == {p.id for p in city.model.pois}
    json.dumps(g)


def test_compass_and_scc():
    assert GP.compass(10, 0) == "East" and GP.compass(0, -5) == "South"
    assert GP.compass(3, 3) == "Northeast" and GP.compass(-3, -3) == "Southwest"
    succ = {"a": ["b"], "b": ["a", "c"], "c": ["d"], "d": ["c"], "e": []}
    assert GP.largest_scc(succ) == {"a", "b"}


def test_names_stay_unique():
    n = GP.Names()
    got = [n.take(lambda k: "Same") for _ in range(3)]
    assert got == ["Same", "Same 2", "Same 3"]


# --- determinism -------------------------------------------------------------------------------

_ACTIVE = [False]


def _perturb(v):
    c = np.asarray(v, dtype=np.float64)
    moved = np.nextafter(np.nextafter(c, np.inf), np.inf)
    return np.where(np.abs(c * 1000.0 - np.rint(c * 1000.0)) < 1e-6, c, moved)


def test_gameplay_stage_ignores_ulp_noise(monkeypatch, city):
    """The stage twice on the same model (its own rows dropped), the second time with 2-ULP
    noise on what GEOS computes inside it: the same rows."""
    base = _bare(city.model)
    clean = GP.build(city.spec, base)
    geo = ["intersection", "difference", "union", "buffer", "make_valid", "centroid",
           "point_on_surface", "line_interpolate_point", "convex_hull", "simplify"]

    def noisy(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            out = fn(*a, **k)
            if not _ACTIVE[0] or k.get("grid_size"):
                return out
            return shapely.transform(out, _perturb)
        return w

    for name in geo:
        monkeypatch.setattr(shapely, name, noisy(getattr(shapely, name)))
    _ACTIVE[0] = True
    try:
        noisy_out = GP.build(city.spec, base)
    finally:
        _ACTIVE[0] = False
    for key in X.GAMEPLAY:
        a = json.dumps(clean.rows[key], sort_keys=True, default=str)
        b = json.dumps(noisy_out.rows[key], sort_keys=True, default=str)
        assert a == b, key
    rebuilt = with_rows(base, clean.rows)
    assert rebuilt.to_json() == city.model.to_json()
