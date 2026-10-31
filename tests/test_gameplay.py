"""M11: the gameplay layer; each M11 check with a failing case, the spec controls, the export,
the helpers, determinism of the stage."""

import copy
import functools
import json

import numpy as np
import shapely

from citygen import checks as C
from citygen import exports as X
from citygen import geom as G
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
    # the core district (it has drive lanes, so it must have a fast-travel point)
    did = m.districts[0].id
    assert any(t.kind == "fast_travel" and t.district_id == did for t in m.travel_points)
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


def test_large_ads(city):
    """M20: neon billboards (landscape and portrait) and banners on the facades, every one
    lit as neon; a banner round its corner names its pair."""
    from collections import Counter

    m = city.model
    kinds = Counter((s.kind, s.mount) for s in m.sign_slots)
    assert kinds[("billboard", "facade")] and kinds[("banner", "facade")]
    big = [s for s in m.sign_slots if s.kind in ("billboard", "banner")]
    assert all(s.attrs.get("lit") == "neon" for s in big)
    face = [s for s in big if s.mount == "facade" and s.kind == "billboard"]
    assert {s.attrs["orientation"] for s in face} == {"landscape", "portrait"}
    slot = {s.id: s for s in m.sign_slots}
    for s in big:
        if "wrap" in s.attrs:
            assert slot[s.attrs["wrap"]].attrs["wrap"] == s.id


def test_signage_spec(city):
    """A district's `signage` sets its large ads: none at density 0, only its kinds."""
    spec = copy.deepcopy(SMALL)
    for d in spec["districts"]:
        d["signage"] = {"density": 0.0}
    out = GP.build(validate_spec(spec).filled, _bare(city.model))
    assert not [s for s in out.rows["sign_slots"] if s["kind"] in ("banner",) or
                s["mount"] in ("front",) or (s["kind"] == "billboard" and
                                             s["mount"] == "facade")]
    spec = copy.deepcopy(SMALL)
    for d in spec["districts"]:
        d["signage"] = {"density": 1.0, "kinds": ["billboard"]}
    out = GP.build(validate_spec(spec).filled, _bare(city.model))
    kinds = {(s["kind"], s["mount"]) for s in out.rows["sign_slots"]}
    assert ("billboard", "facade") in kinds and ("banner", "facade") not in kinds
    assert ("holo_ad", "front") not in kinds and ("holo_ad", "roof") not in kinds


def test_check_slots_fails_for_large_ads(city):
    m = city.model
    bb = next(s for s in m.sign_slots if s.kind == "billboard" and s.mount == "facade")
    import math

    a = math.radians(bb.yaw_deg)
    out = [s.model_copy(update={"position": (s.position[0] + 6.0 * math.cos(a),
                                             s.position[1] + 6.0 * math.sin(a),
                                             s.position[2])})
           if s.id == bb.id else s for s in m.sign_slots]
    assert not _checks(m.model_copy(update={"sign_slots": out}))["sign_slots"].passed
    dark = [s.model_copy(update={"attrs": {**s.attrs, "lit": None}}) if s.id == bb.id else s
            for s in m.sign_slots]
    assert not _checks(m.model_copy(update={"sign_slots": dark}))["sign_slots"].passed


def test_lots_keep_clear_of_buildings(city):
    """Sweep regression: a setback lot over another lot's building is not placed, and the
    check sees the overlap."""
    m = city.model
    b = next(x for x in m.buildings if x.footprint is not None and x.lot_id)
    obstacles = GP.lot_obstacles(m)
    assert GP.lot_clash(G.from_model_poly(b.footprint), obstacles) > 1.0
    for p in m.parking:
        if p.kind == "lot":
            assert GP.lot_clash(G.from_model_poly(p.polygon), obstacles) <= 0.5
    if m.parking:
        bad = m.parking[0].model_copy(update={"kind": "lot", "type": "parking.lot",
                                              "polygon": b.footprint,
                                              "entrances": m.pois[0].entrances})
        rows = [bad] + list(m.parking[1:])
        assert not _checks(m.model_copy(update={"parking": rows}))["parking"].passed


def test_fast_travel_without_stations_or_signals(city):
    """Sweep regression: a district with no station, place, landmark or signalized junction
    still gets a fast-travel point (a junction or the middle of a drive lane)."""
    m = _bare(city.model)
    m = m.model_copy(update={
        "stations": [], "places": [],
        "junctions": [j.model_copy(update={"signalized": False}) for j in m.junctions],
        "buildings": [b.model_copy(update={"landmark": False}) for b in m.buildings]})
    out = GP.build(city.spec, m)
    m2 = with_rows(m, out.rows)
    assert _checks(m2)["travel_points"].passed
    have = {t.district_id for t in m2.travel_points if t.kind == "fast_travel"}
    assert have == {d.id for d in m.districts}


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
