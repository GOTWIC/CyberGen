"""M21: cyberpunk massing. True arcs (`massing.Plate`, chord sag 2 cm at most), the tower and
slab forms (`forms`), the neighbor rule's selection (`buildout.select_forms`), the checks
`building_forms` and `tower_neighbors` with failing cases, and a small city built with them."""

import copy
import math

import pytest
from shapely.geometry import Point

from citygen import buildings as BL
from citygen import buildout as BO
from citygen import building_checks as BC
from citygen import forms as FM
from citygen import geom as G
from citygen import massing as MS
from citygen import streets as ST
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import SMALL


def _sag(poly, arcs) -> float:
    """Farthest distance from a point of an arc to the polygon's boundary."""
    worst = 0.0
    for a in arcs:
        cx, cy = a["center"]
        for i in range(48):
            t = math.radians(a["start_deg"] + a["sweep_deg"] * (i + 0.5) / 48)
            p = Point(cx + a["radius_m"] * math.cos(t), cy + a["radius_m"] * math.sin(t))
            worst = max(worst, poly.boundary.distance(p))
    return worst


@pytest.mark.parametrize("plate", [
    MS.Plate(MS.Frame(10.37, -4.21, 0.3), 30.0, 30.0, 30.0),          # circle
    MS.Plate(MS.Frame(0.0, 0.0, 1.0), 20.0, 12.0, 5.0),               # rounded rectangle
    MS.Plate(MS.Frame(5.0, 5.0, 0.2), 24.0, 15.0, oval=True),         # oval along u
    MS.Plate(MS.Frame(5.0, 5.0, 0.2), 14.0, 22.0, oval=True),         # oval along v
    MS.Plate(MS.Frame(-3.0, 7.0, 2.2), 18.0, 10.0, 10.0),             # stadium
    MS.Plate(MS.Frame(0.0, 0.0, 0.7), 1.3, 1.3, 1.3),                 # a mast
    MS.Plate(MS.Frame(0.0, 0.0, 0.7), 18.0, 18.2, oval=True),         # equal axes: a circle
])
def test_plates_follow_their_arcs_within_2_cm(plate):
    poly = plate.polygon()
    arcs = plate.arcs()
    assert poly.is_valid and len(arcs) == 4
    assert _sag(poly, arcs) <= BC.ARC_TOL_M
    # the turned and scaled plate keeps its arcs
    p2 = plate.turned(0.37).scaled(0.8)
    assert _sag(p2.polygon(), p2.arcs()) <= BC.ARC_TOL_M
    assert all(len(set(p2.ring())) == len(p2.ring()) for _ in (0,))


def test_sector_and_circle_helpers():
    poly, arcs = MS.sector(0.0, -100.0, 80.0, 96.0, 1.2, 0.5)
    assert poly.is_valid and len(arcs) == 2 and _sag(poly, arcs) <= BC.ARC_TOL_M
    c = MS.circle(3.0, 4.0, 6.5)
    assert abs(G.area1(c) - math.pi * 6.5 * 6.5) < 0.5
    assert MS.arc_steps(30.0, 2 * math.pi) > 100       # no 32-gon any more


def _shaft(form, v=0.9, seed=3, w=36.0, d=30.0, H=180.0, P=16.0, room=70.0):
    fr = MS.Frame(0.0, 0.0, 0.4)
    region = fr.rect(-room / 2.0, -room / 2.0, room / 2.0, room / 2.0)
    inner = MS.prep(MS.inset(region, 4.0))
    outer = MS.prep(MS.inset(region, 1.0))
    b = BL.Bld("podium_tower", "office", 4.0, fr)
    b.add(region, 0.0, P, "podium")
    plate = MS.Plate(fr, w / 2.0, d / 2.0)
    ok = FM.tower(b, form, plate, P, H, v, inner, outer, ST._rng(seed, 1), 320.0)
    return b, ok, region


@pytest.mark.parametrize("form", FM.FORMS)
def test_every_form_builds_inside_its_room(form):
    for seed in range(4):
        b, ok, region = _shaft(form, seed=seed)
        if not ok:
            assert len(b.masses) == 1      # nothing left behind
            continue
        assert b.form["kind"] == form and b.form["masses"]
        assert abs(b.height - 180.0) < 0.01
        for m in b.masses:
            assert region.covers(m[0]), (form, m[3])
            assert m[0].is_valid
        if form == "twist":
            bands = sorted((b.masses[i] for i in b.form["masses"] if b.masses[i][3] == "band"),
                           key=lambda m: m[1])
            for lo, hi in zip(bands, bands[1:]):
                fl = (hi[1] - lo[1]) / 4.0
                assert abs(hi[5]["turn"] - lo[5]["turn"]) / fl <= FM.MAX_TWIST_DEG + 1e-6


def test_variety_sets_the_forms_drawn():
    low = {f for f, _ in FM.weights(0.1)}
    high = {f for f, _ in FM.weights(0.95)}
    assert low == set(FM.MILD)
    assert high == set(FM.FORMS)
    order = FM.order(0.9, ST._rng(1, 2))
    assert sorted(order) == sorted(FM.FORMS) and order == FM.order(0.9, ST._rng(1, 2))


def test_band_heights_leave_the_band():
    for H in (60.0, 100.0, 150.0, 200.0):
        k = BL.tower_band(H)
        for h in BL.band_heights(H, 4.0, 40.0, 320.0, math.inf):
            assert abs(BL.tower_band(h) - k) == 1 and abs(h / 4.0 - round(h / 4.0)) < 1e-9


def _t(i, x, h, form, ok, prop=None, alt=()):
    return {"id": f"t{i}", "lot_id": f"lot{i}", "property_id": prop or f"p{i}", "height": h,
            "c": (x, 0.0), "form": form, "band": BL.tower_band(h), "ok": list(ok),
            "alt_h": list(alt)}


def test_select_forms_keeps_neighbors_apart():
    fixed = [_t(0, 0.0, 150.0, "box", ["box"], prop="cx")]
    movable = [_t(1, 40.0, 140.0, "box", ["box", "twist", "lean"]),
               _t(2, 80.0, 130.0, "box", ["box", "twist", "lean"]),
               _t(3, 400.0, 130.0, "box", ["box"]),                       # far away
               _t(4, 60.0, 120.0, "box", ["box"], alt=(100.0,)),          # into another band
               _t(5, 20.0, 125.0, "box", ["box"], prop="cx")]             # the complex's own
    ch = BO.select_forms(fixed, movable)
    # (t5 shares the complex's property: its box stays)
    assert ch == {"lot1": ("twist", None), "lot2": ("lean", None), "lot4": ("box", 100.0)}


SPEC = copy.deepcopy(SMALL)
SPEC["name"] = "Testport Forms"
SPEC["districts"][0].update({"variety": 1.0, "complexes": ["twin_towers"]})


@pytest.fixture(scope="module")
def city():
    r = validate_spec(copy.deepcopy(SPEC))
    assert r.ok
    return build_city(r)


def test_small_city_builds_forms_and_passes(city):
    m = city.model
    checks = {c.id: c for c in city.checks}
    for cid in ("building_forms", "tower_neighbors", "building_footprints",
                "building_overlaps", "skybridges", "complexes"):
        assert checks[cid].passed, (cid, checks[cid].failures[:3])
    kinds = {b.form.kind for b in m.buildings if b.form is not None and b.form.tower}
    assert len(kinds) >= 5, kinds
    arcs = [ms for b in m.buildings for ms in b.masses if ms.arcs]
    assert arcs, "no curved masses"


def test_checks_catch_broken_forms(city):
    m = city.model
    data = m.model_dump(mode="json")
    tw = [b for b in data["buildings"] if b.get("form") and b["form"]["tower"]]
    # two neighboring towers made one form and band
    a = tw[0]
    near = min(tw[1:], key=lambda b: (b["footprint"]["exterior"][0][0] - a["footprint"]["exterior"][0][0]) ** 2
               + (b["footprint"]["exterior"][0][1] - a["footprint"]["exterior"][0][1]) ** 2)
    near["form"]["kind"] = a["form"]["kind"]
    near["height_m"] = a["height_m"]
    near["form"]["band"] = a["form"]["band"]
    # a mass lifted off what holds it, and an arc moved off its footprint
    lifted = next(b for b in data["buildings"] if len(b["masses"]) >= 2 and
                  b["masses"][1]["z0_m"] > 1.0 and not b.get("level"))
    lifted["masses"][1]["z0_m"] += 3.0
    lifted["masses"][1]["z1_m"] += 3.0
    curved = next(b for b in data["buildings"] for ms in b["masses"] if ms.get("arcs"))
    ms = next(ms for ms in curved["masses"] if ms.get("arcs"))
    ms["arcs"][0]["radius_m"] += 0.5
    broken = CityModel.model_validate(data)
    bx = BC._B(broken)
    c = BC.check_tower_neighbors(broken, bx)
    d = math.dist(G.centroid(G.from_model_poly(a["footprint"])),
                  G.centroid(G.from_model_poly(near["footprint"])))
    if d <= BL.TOWER_NEAR_M and a["property_id"] != near["property_id"]:
        assert not c.passed
    f = BC.check_forms(broken, bx)
    assert any("rests on nothing" in x for x in f.failures)
    assert any("off its arc" in x for x in f.failures)
