"""M6: props and vegetation; each M6 check with a failing case, the placement helpers, the
blockout instancing plan, determinism of the stage."""

import copy
import functools
import json

import numpy as np
import pytest
import shapely

from citygen import blockout as BO
from citygen import checks as C
from citygen import geom as G
from citygen import props as PR
from citygen.build import build_city
from citygen.model import CityModel, Sidewalk
from citygen.validate import validate_spec

from conftest import SMALL

M6_CHECKS = {"props_keepout", "props_overlap", "tree_clearance", "street_lighting",
             "park_planting", "boats_afloat"}


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def city():
    return _build(copy.deepcopy(SMALL))


def _rerun(model: CityModel) -> dict:
    spec = validate_spec(copy.deepcopy(SMALL)).filled
    checks, _ = C.run_checks(spec, model)
    return {c.id: c for c in checks}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


def _kind(row) -> str:
    return row["type"].split(".", 1)[1]


# --- the build ------------------------------------------------------------------------

def test_city_passes_with_props(city):
    failed = [(c.id, c.failures[:3]) for c in city.checks if not c.passed]
    assert not failed, failed
    assert M6_CHECKS <= {c.id for c in city.checks}


def test_build_checks_equal_a_fresh_run(city):
    fresh = _rerun(city.model)
    for c in city.checks:
        if c.id in M6_CHECKS:
            assert fresh[c.id].passed == c.passed, c.id


def test_props_and_plants_placed(city):
    m = city.model
    kinds = {p.type.split(".", 1)[1] for p in m.props}
    assert {"street_light", "hydrant", "trash_can", "sign", "awning"} <= kinds
    plants = {p.type.split(".", 1)[1] for p in m.plants}
    assert {"street_tree", "park_tree", "shrub"} & plants
    assert len(m.props) + len(m.plants) > 2000
    ids = [p.id for p in m.props] + [p.id for p in m.plants]
    assert len(ids) == len(set(ids))
    for p in m.plants:
        assert p.height_m > 0 and p.crown_radius_m > 0


def test_report_has_prop_stats(city):
    st = city.stats["props"]
    assert st["props"] == len(city.model.props) and st["plants"] == len(city.model.plants)
    assert st["instances"] == st["props"] + st["plants"]
    rep = city.report()
    assert rep["stage"].startswith("M11")
    assert "props" in C.report_text(rep)


# --- failing checks ---------------------------------------------------------------------

def test_check_keepout_fails(city):
    def fn(d):
        lane = d["lanes"][0]
        x, y, _ = lane["centerline"][len(lane["centerline"]) // 2]
        p = next(p for p in d["props"] if _kind(p) == "street_light")
        p["position"] = [x, y, 0.0]
    assert not _rerun(_mutate(city.model, fn))["props_keepout"].passed


def test_check_overlap_fails(city):
    def fn(d):
        a = next(p for p in d["props"] if _kind(p) == "hydrant")
        b = copy.deepcopy(a)
        b["id"] = a["id"] + "x"
        b["position"] = [a["position"][0] + 0.1, a["position"][1], 0.0]
        d["props"].append(b)
    assert not _rerun(_mutate(city.model, fn))["props_overlap"].passed


def test_check_trees_fails(city):
    def fn(d):
        t = next(p for p in d["plants"] if _kind(p) in ("street_tree", "park_tree"))
        t["crown_radius_m"] = 80.0   # (the first tree may stand 42 m from any facade)
    assert not _rerun(_mutate(city.model, fn))["tree_clearance"].passed


def test_check_lighting_fails(city):
    def fn(d):
        d["props"] = [p for p in d["props"] if _kind(p) not in ("street_light", "wall_light")]
    assert not _rerun(_mutate(city.model, fn))["street_lighting"].passed


def test_check_parks_fails(city):
    def fn(d):
        d["plants"] = [p for p in d["plants"] if p["position"][2] > 0.5]
        d["props"] = d["props"][:1]
    ch = _rerun(_mutate(city.model, fn))["park_planting"]
    parks = [o for o in city.model.open_spaces if o.kind in ("park", "pocket_park", "garden")
             and G.area(G.from_model_poly(o.polygon)) >= 800.0 and
             G._strip_width(G.parts(G.from_model_poly(o.polygon))[0]) >= 6.0]
    assert ch.passed == (not parks)


def test_check_boats_fails(city):
    if not any(_kind(json.loads(p.model_dump_json())) == "boat" for p in city.model.props):
        pytest.skip("no boats in the small city")

    def fn(d):
        b = next(p for p in d["props"] if _kind(p) == "boat")
        b["position"] = [0.0, 0.0, 0.0]
    assert not _rerun(_mutate(city.model, fn))["boats_afloat"].passed


# --- M20: on their surfaces, under what is over them -----------------------------------

M20_CHECKS = {"prop_support", "plant_headroom"}


def test_m20_checks_run(city):
    assert M20_CHECKS <= {c.id for c in city.checks}


def test_check_support_fails(city):
    def lifted(d):
        p = next(p for p in d["props"] if _kind(p) == "bench" and p["position"][2] == 0.0)
        p["position"][2] = 0.5     # (over the ground, on no road)
    assert not _rerun(_mutate(city.model, lifted))["prop_support"].passed

    def off_wall(d):
        p = next(p for p in d["props"] if _kind(p) == "sign")
        p["position"][2] = 400.0   # (no wall that high)
    assert not _rerun(_mutate(city.model, off_wall))["prop_support"].passed


def test_quay_props_on_the_deck(city):
    """The quay's deck is the ground (M16: the freeboard over the water): railings and
    benches stand at z 0; boats float on the water."""
    from citygen import water as WA

    rail = [p for p in city.model.props if p.type == "prop.railing"]
    assert rail and all(p.position[2] == 0.0 for p in rail)
    for p in city.model.props:
        if p.type == "prop.boat":
            assert p.position[2] == -WA.FREEBOARD_M


def test_overhead_measured_along_a_ramp(city):
    """A raised road's underside is its surface less the deck where a thing stands under it,
    and its fill (from the ground) where it is low."""
    from citygen import vegetation as V

    m = city.model
    c = PR.Ctx(None, m)
    oh = V.Overhead(m)
    for s in m.road_segments:
        prof = [(z.s, z.z) for z in s.z_profile]
        if len(prof) < 2 or max(z for _, z in prof) < 8.0 or min(z for _, z in prof) > 1.0:
            continue
        line = shapely.LineString(s.centerline)
        hi = max(prof, key=lambda p: p[1])
        # (a station where the road is a little up: on its fill)
        low = next((sv / 10.0 for sv in range(int(line.length * 10))
                    if 0.6 < V._z_on(prof, sv / 10.0) < 1.5), None)
        if low is None:
            continue
        pts = [line.interpolate(hi[0]), line.interpolate(low)]
        u = oh.under(np.array([[p.x, p.y] for p in pts]), np.array([0.1, 0.1]),
                     np.array([0.0, 0.0]))
        assert abs(u[0] - (V._lowest(prof, hi[0] - 0.1, hi[0] + 0.1) - V.ROAD_DECK_M)) < 0.6
        assert u[1] == 0.0
        assert c.road_z(s.id, pts[0].x, pts[0].y)[0] == pytest.approx(hi[1], abs=0.05)
        return
    pytest.skip("no ramp in the small city")


def test_check_headroom_fails(city):
    m = city.model
    seg = max((s for s in m.road_segments if s.z_profile),
              key=lambda s: (max(z.z for z in s.z_profile), s.id))
    if max(z.z for z in seg.z_profile) < 6.0:
        pytest.skip("no raised road in the small city")
    top = max(seg.z_profile, key=lambda z: z.z)
    pt = shapely.LineString(seg.centerline).interpolate(top.s)

    def fn(d):
        t = next(p for p in d["plants"] if _kind(p) == "park_tree")
        t["position"] = [pt.x, pt.y, 0.0]
        t["height_m"] = top.z      # (into its deck)
    assert not _rerun(_mutate(m, fn))["plant_headroom"].passed


# --- helpers ----------------------------------------------------------------------------

def test_hash_rng_is_fixed():
    # the same numbers on every machine and process (blake2b of the key)
    assert PR._u("a", 1) == PR._u("a", 1)
    assert PR._u("a", 1) != PR._u("a", 2)
    assert abs(PR._u("street", 7) - 0.9764843436801451) < 1e-15


def test_walk_spacing():
    pts = PR.walk([(0, 0), (100, 0)], 10.0, 5.0, 0.0)
    assert [round(p[0], 6) for p in pts] == [5 + 10 * k for k in range(10)]
    assert all(p[2] == 1.0 and p[3] == 0.0 for p in pts)


def _sw(width, furniture, clear, side="left"):
    return Sidewalk(id="sw1", segment_id="rs1", side=side, line=[(0.0, 0.0), (100.0, 0.0)],
                    width_m=width, clear_path_m=clear, furniture_m=furniture)


def test_furniture_points_keep_the_clear_path():
    wide = PR.furniture_points(_sw(5.0, 1.5, 3.35), 30.0, 0.0, 0.3)
    assert wide and all(abs(p[1] + (2.5 - 0.15 - 0.75)) < 1e-9 for p in wide)  # road below
    assert PR.furniture_points(_sw(2.0, 0.15, 1.7), 30.0, 0.0, 0.3) == []


def test_blockout_plan_instances(city):
    plan = BO.make_plan(city.model)
    inst = [o for o in plan["objects"] if o["parts"] and o["parts"][0]["k"] == "inst"]
    assert inst
    assert plan["stats"]["instances"] == sum(len(o["parts"][0]["pts"]) for o in inst)
    # (M20: and the large ads, as sign prototypes)
    ads = sum(1 for s in city.model.sign_slots if (s.kind, s.mount) in BO.SIGN_PROTO)
    assert ads
    assert plan["stats"]["instances"] == len(city.model.props) + len(city.model.plants) + ads
    for o in inst:
        assert o["parts"][0]["proto"] in plan["prototypes"]
        assert all(len(pt) == 7 for pt in o["parts"][0]["pts"])
    for parts in plan["prototypes"].values():
        assert all(p["m"] in plan["materials"] for p in parts)


# --- determinism ---------------------------------------------------------------------

_ACTIVE = [False]


def _perturb(v):
    c = np.asarray(v, dtype=np.float64)
    moved = np.nextafter(np.nextafter(c, np.inf), np.inf)
    return np.where(np.abs(c * 1000.0 - np.rint(c * 1000.0)) < 1e-6, c, moved)


def test_props_stage_ignores_ulp_noise(monkeypatch, city):
    """The props stage twice on the same model (its own props and plants dropped), the
    second time with 2-ULP noise on what GEOS computes inside it: the same rows."""
    base = city.model.model_copy(update={"props": [], "plants": [], "green_areas": [
        g for g in city.model.green_areas if g.kind == "green_roof"]})
    spec = city.spec
    clean = PR.build(spec, base)
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
        noisy_out = PR.build(spec, base)
    finally:
        _ACTIVE[0] = False
    for key in ("props", "plants"):
        a = json.dumps(clean.rows[key], sort_keys=True, default=str)
        b = json.dumps(noisy_out.rows[key], sort_keys=True, default=str)
        assert a == b, key
    assert len(clean.rows["props"]) == len(city.model.props)
