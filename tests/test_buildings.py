"""M3: buildings, complexes, landmarks, skybridges, megasites; each M3 check with a failing
case, shape helpers, determinism of the M3 stages."""

import copy
import functools
import hashlib
import json
import math

import numpy as np
import pytest
import shapely
from shapely import affinity
from shapely.geometry import Polygon, box

from citygen import buildout as BO
from citygen import checks as C
from citygen import geom as G
from citygen import massing as MS
from citygen import skybridges as SB
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import load_spec, validate_spec

from conftest import ROOT, SMALL

M3_CHECKS = {"building_footprints", "building_clear_zones", "building_overlaps",
             "building_heights", "building_entrances", "ground_floor_units", "roof_items",
             "complexes", "skybridges", "landmarks", "megasite_contents", "megasite_heights",
             "megasite_access"}

# The small city with every M3 feature asked for: complexes, landmarks, megasites.
RICH = copy.deepcopy(SMALL)
RICH["name"] = "Testport Rich"
RICH["districts"][0].update({"landmarks": ["megatower"],
                             "complexes": ["twin_towers", "tower_cluster"]})
RICH["districts"][2].update({"places": [{"name": "Shrine Court", "kind": "temple_complex"}]})
RICH["districts"].append({"name": "Pads", "archetype": "spaceport", "area_share": 0.12,
                          "megasites": [{"kind": "spaceport", "area_km2": 0.3}],
                          "placement": {"edge": "east"}})


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def rich():
    return _build(copy.deepcopy(RICH))


def _rerun(spec_data, model: CityModel) -> dict:
    spec = validate_spec(spec_data).filled
    checks, _ = C.run_checks(spec, model)
    return {c.id: c for c in checks}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


def _poly(p) -> dict:
    return G.to_model_poly(p)


# --- the build ------------------------------------------------------------------------

def test_rich_city_passes(rich):
    failed = [f for c in rich.checks for f in c.failures]
    assert not failed, failed
    assert M3_CHECKS <= {c.id for c in rich.checks}
    assert len(rich.checks) == 82  # 44 to M3, 6 M6, 5 M7, 4 M9, 9 M11, 2 M12, 5 M13, 4 M17,
    #                                3 M16
    # (no transit)


def test_build_checks_equal_a_fresh_run(rich):
    """The build runs the M1/M2 checks on the M2 model while the workers build the lots; a
    fresh run on the final model gives the same checks."""
    again = _rerun(RICH, rich.model)
    assert [c.to_dict() for c in rich.checks] == [again[c.id].to_dict() for c in rich.checks]


def test_every_lot_gets_a_building_mostly(rich):
    m = rich.model
    built = {lid for p in m.properties for lid in p.lot_ids}
    assert len(built) >= 0.95 * len(m.lots)
    assert all(b.masses and b.entrances for b in m.buildings)


def test_buildings_by_archetype(rich):
    m = rich.model
    arch = {d.id: d.archetype for d in m.districts}
    kinds: dict = {}
    for b in m.buildings:
        if b.district_id and not b.megasite_id:
            kinds.setdefault(arch[b.district_id], set()).add(b.type.split(".")[1])
    assert {"podium_tower"} <= kinds["corporate_core"]
    assert kinds["old_town"] & {"shopfront_row", "shanty_stack"}
    assert kinds["industrial_port"] & {"warehouse", "shed", "yard"}
    assert kinds["residential_heights"] & {"villa", "terraced", "slab"}
    # corporate towers are much taller than the old town
    hs = {a: [b.height_m for b in m.buildings if b.district_id and arch[b.district_id] == a
              and not b.landmark and not b.megasite_id] for a in arch.values()}
    assert np.median(hs["corporate_core"]) > 4 * np.median(hs["old_town"])


def test_units_rooftops_and_entrances(rich):
    m = rich.model
    units = [u for b in m.buildings for u in b.units]
    assert units and all(4.0 - 0.05 <= u.width_m <= 12.0 + 0.05 for u in units)
    assert {"food", "bar"} & {u.use for u in units}
    roof = {it.kind for b in m.buildings for it in b.roof_items}
    assert {"mechanical", "ac_unit"} <= roof
    assert any(it.kind in ("helipad", "av_pad") for b in m.buildings for it in b.roof_items)
    assert any(e.kind == "service" for b in m.buildings for e in b.entrances)
    assert all(e.walkway_id for b in m.buildings for e in b.entrances)


def test_complexes_landmark_and_skybridges(rich):
    m = rich.model
    kinds = {p.complex for p in m.properties}
    assert {"twin_towers", "tower_cluster", "landmark", "megasite"} <= kinds
    twins = next(p for p in m.properties if p.complex == "twin_towers")
    a, b = (next(x for x in m.buildings if x.id == i) for i in twins.building_ids)
    assert a.height_m == b.height_m
    assert any(set(s.building_ids) == {a.id, b.id} for s in m.skybridges)
    mega = next(b for b in m.buildings if b.landmark)
    assert mega.attrs["landmark_kind"] == "megatower" and mega.attrs["arms"] == 3
    assert mega.height_m == max(x.height_m for x in m.buildings)
    walk = {w.id: w for w in m.walkways}
    for s in m.skybridges:
        assert 8.0 - 0.05 <= s.length_m <= 80.0 + 0.05
        kinds_ = {walk[w].kind for w in s.walkway_ids}
        assert {"skybridge", "elevator"} <= kinds_


def test_megasites_filled(rich):
    m = rich.model
    for s in m.megasites:
        assert s.member_ids and s.attrs["filled"], s.name
    sp = next(s for s in m.megasites if s.kind == "spaceport")
    assert {"launch_pad", "hangar", "terminal", "control_tower"} <= set(sp.attrs["contents"])
    for b in m.buildings:
        if b.megasite_id == sp.id:
            assert b.height_m <= sp.height_limit_m + 0.01


def test_report_has_building_stats(rich):
    st = rich.stats["buildings"]
    for k in ("count", "floor_area_km2", "by_type", "by_district", "skybridges",
              "units_by_use", "roof_items", "landmarks", "megasites"):
        assert k in st, k
    text = C.report_text(rich.report())
    assert "buildings by district" in text and "skybridges" in text


# --- each M3 check fails when broken --------------------------------------------------

def _first(m, pred):
    return next(i for i, b in enumerate(m["buildings"]) if pred(b))


def test_check_footprints_fails(rich):
    def fn(d):
        i = _first(d, lambda b: b["lot_id"] and not b["megasite_id"] and not b["landmark"])
        for mass in d["buildings"][i]["masses"]:
            p = affinity.translate(G.from_model_poly(mass["footprint"]), 60.0, 0.0)
            mass["footprint"] = _poly(p)
    assert not _rerun(RICH, _mutate(rich.model, fn))["building_footprints"].passed


def test_check_clear_zones_fails(rich):
    seg = rich.model.road_segments[0]
    mid = shapely.LineString(seg.centerline).interpolate(0.5, normalized=True)

    def fn(d):
        i = _first(d, lambda b: b["lot_id"] and not b["landmark"])
        d["buildings"][i]["masses"].append({"footprint": _poly(mid.buffer(4.0, 4)),
                                            "z0_m": 0.0, "z1_m": 9.0, "role": "body",
                                            "shape": "prism"})
    checks = _rerun(RICH, _mutate(rich.model, fn))
    assert not checks["building_clear_zones"].passed


def test_check_overlaps_fails(rich):
    def fn(d):
        i = _first(d, lambda b: b["lot_id"] and not b["landmark"])
        j = _first(d, lambda b: b["lot_id"] and not b["landmark"] and
                   b["id"] != d["buildings"][i]["id"])
        d["buildings"][j]["masses"].append(copy.deepcopy(d["buildings"][i]["masses"][0]))
    assert not _rerun(RICH, _mutate(rich.model, fn))["building_overlaps"].passed


def test_check_heights_fails(rich):
    def fn(d):
        i = _first(d, lambda b: b["lot_id"] and not b["landmark"] and not b["megasite_id"])
        d["buildings"][i]["height_m"] = 5000.0
    assert not _rerun(RICH, _mutate(rich.model, fn))["building_heights"].passed


def test_check_entrances_fails(rich):
    def fn(d):
        i = _first(d, lambda b: b["lot_id"] and not b["landmark"])
        d["buildings"][i]["entrances"] = []
    assert not _rerun(RICH, _mutate(rich.model, fn))["building_entrances"].passed


def test_check_units_fails(rich):
    def fn(d):
        i = _first(d, lambda b: b["units"])
        d["buildings"][i]["units"][0]["width_m"] = 20.0
    assert not _rerun(RICH, _mutate(rich.model, fn))["ground_floor_units"].passed


def test_check_roof_items_fails(rich):
    def fn(d):
        i = _first(d, lambda b: b["roof_items"])
        it = d["buildings"][i]["roof_items"][0]
        it["position"] = [it["position"][0], it["position"][1], it["position"][2] + 7.0]
    assert not _rerun(RICH, _mutate(rich.model, fn))["roof_items"].passed


def test_check_complexes_fails(rich):
    def fn(d):
        p = next(p for p in d["properties"] if p["complex"] == "twin_towers")
        p["complex"] = "single"
    assert not _rerun(RICH, _mutate(rich.model, fn))["complexes"].passed


def test_check_skybridges_fails(rich):
    def fn(d):
        s = d["skybridges"][0]
        s["z_m"] = s["z_m"] + 1.3   # off both floor grids
    assert not _rerun(RICH, _mutate(rich.model, fn))["skybridges"].passed


def test_check_landmarks_fails(rich):
    def fn(d):
        i = _first(d, lambda b: b["landmark"])
        d["buildings"][i]["name"] = "Somewhere Else"
    assert not _rerun(RICH, _mutate(rich.model, fn))["landmarks"].passed


def test_check_megasite_contents_fails(rich):
    def fn(d):
        s = next(s for s in d["megasites"] if s["kind"] == "spaceport")
        drop = {e["id"] for e in d["site_elements"] if e["megasite_id"] == s["id"] and
                e["kind"] == "launch_pad"}
        d["site_elements"] = [e for e in d["site_elements"] if e["id"] not in drop]
        s["member_ids"] = [x for x in s["member_ids"] if x not in drop]
    assert not _rerun(RICH, _mutate(rich.model, fn))["megasite_contents"].passed


def test_check_megasite_heights_fails(rich):
    def fn(d):
        s = next(s for s in d["megasites"] if s["kind"] == "spaceport")
        i = _first(d, lambda b: b["megasite_id"] == s["id"])
        d["buildings"][i]["masses"][0]["z1_m"] = 200.0
    assert not _rerun(RICH, _mutate(rich.model, fn))["megasite_heights"].passed


# --- shape helpers ---------------------------------------------------------------------

def test_frame_round_trip():
    fr = MS.Frame(10.0, -5.0, 0.7)
    x, y = fr.world(12.0, 3.0)
    u, v = fr.local(x, y)
    assert abs(u - 12.0) < 0.01 and abs(v - 3.0) < 0.01


def test_front_rect_on_a_sheared_lot():
    lot = Polygon([(0, 0), (60, 0), (110, 100), (50, 100)])
    fr = MS.Frame(30.0, 0.0, 0.0)
    r = MS.front_rect(MS.prep(lot), fr, 40.0, min_w=8.0, min_d=6.0)
    assert r is not None and lot.covers(r)
    u0, v0, u1, v1 = fr.bounds(r)
    assert v0 < 1.0 and (u1 - u0) * (v1 - v0) > 600.0


def test_obb_angle_ignores_ring_start():
    p = Polygon([(0, 0), (40, 10), (35, 30), (-5, 20)])
    q = Polygon(list(p.exterior.coords)[2:-1] + list(p.exterior.coords)[:2])
    assert MS.obb_angle(p) == MS.obb_angle(q)


def test_wheel_rim_band():
    rim = box(-50.0, -2.0, 50.0, 2.0)
    info = MS.ring_info(rim, 4.0, 104.0)
    lo, hi = MS.ring_zband(info, box(40.0, -2.0, 45.0, 2.0))
    assert 20.0 < lo < 35.0 and hi > 80.0
    low = MS.ring_ground(info, rim, 6.5)
    assert low.area < 0.4 * rim.area


def test_floor_step():
    assert SB.floor_step(4.0, 4.0) == 4.0
    assert SB.floor_step(3.5, 4.0) == 28.0
    assert SB.floor_step(3.2, 3.5) is None


# --- determinism ---------------------------------------------------------------------

def test_workers_do_not_change_m3():
    spec = validate_spec(copy.deepcopy(RICH))
    a = build_city(spec, workers=1).model.to_json()
    b = build_city(spec, workers=3).model.to_json()
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


_ACTIVE = [False]


def _perturb(v):
    c = np.asarray(v, dtype=np.float64)
    moved = np.nextafter(np.nextafter(c, np.inf), np.inf)
    return np.where(np.abs(c * 1000.0 - np.rint(c * 1000.0)) < 1e-6, c, moved)


def test_m3_stages_ignore_ulp_noise(monkeypatch):
    """The rich city twice in one process, the second time with 2-ULP noise on what GEOS
    computes inside the M3 stages (grid values and fixed-precision overlays aside):
    byte-identical models."""
    spec = validate_spec(copy.deepcopy(RICH))
    clean = build_city(spec, workers=1).model.to_json()
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
    real = BO.build

    def noisy_build(*a, **k):
        _ACTIVE[0] = True
        try:
            return real(*a, **k)
        finally:
            _ACTIVE[0] = False

    monkeypatch.setattr(BO, "build", noisy_build)
    noisy_json = build_city(spec, workers=1).model.to_json()
    assert hashlib.sha256(noisy_json.encode()).hexdigest() == \
        hashlib.sha256(clean.encode()).hexdigest()
