"""M5: transit lines, stations, supports and walkways; each transit check with a failing case,
the track geometry helpers, determinism of the transit stage. M8b: a loop is one simple ring
with its stations in route order, a line's route does not depend on the other lines."""

import copy
import functools
import hashlib
import json
import math

import numpy as np
import pytest
import shapely

from citygen import checks as C
from citygen import geom as G
from citygen import transit as TR
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import SMALL

TRANSIT_CHECKS = {"transit_routes", "transit_stops", "transit_curves", "transit_self_crossing",
                  "transit_grades", "transit_altitude", "transit_clearance", "transit_supports",
                  "station_access", "transit_skybridges", "transit_hubs"}

# The small city with one line of each kind: underground, along the avenues, through towers,
# and an elevated loop whose stops (west, east, north, middle) cross over if taken from the
# districts' middles.
LINES = copy.deepcopy(SMALL)
LINES["name"] = "Testport Lines"
LINES["transit"] = {"lines": [
    {"mode": "metro", "name": "Red Line", "route": ["Harbor", "Core", "Uptown"]},
    {"mode": "elevated_rail", "name": "Green Line", "route": ["Harbor", "Core", "Old Quarter"]},
    {"mode": "sky_tube", "name": "Sky Line", "through_towers": True,
     "route": ["Core", "Uptown"]},
    {"mode": "elevated_rail", "name": "Ring Line",
     "route": ["Harbor", "Old Quarter", "Uptown", "Core", "Harbor"]},
]}


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def lines():
    return _build(copy.deepcopy(LINES))


@pytest.fixture(scope="module")
def no_transit():
    """The same city without transit: the model the transit stage runs on."""
    data = copy.deepcopy(LINES)
    data["transit"] = {"lines": []}
    return _build(data).model


def _rerun(model: CityModel) -> dict:
    spec = validate_spec(copy.deepcopy(LINES)).filled
    checks, _ = C.run_checks(spec, model)
    return {c.id: c for c in checks}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


def _line(d, mode):
    return next(t for t in d["transit_lines"] if t["mode"] == mode)


# --- the build ------------------------------------------------------------------------

def test_lines_city_passes(lines):
    failed = [(c.id, c.failures[:3]) for c in lines.checks if not c.passed]
    assert not failed, failed
    assert TRANSIT_CHECKS <= {c.id for c in lines.checks}


def test_build_checks_equal_a_fresh_run(lines):
    fresh = _rerun(lines.model)
    for c in lines.checks:
        if c.id in TRANSIT_CHECKS:
            assert fresh[c.id].passed == c.passed, c.id


def test_every_line_built_with_stations(lines):
    m = lines.model
    assert [t.name for t in m.transit_lines] == ["Red Line", "Green Line", "Sky Line",
                                                 "Ring Line"]
    kinds = {t.mode: {s.kind for s in m.stations if t.id in s.line_ids}
             for t in m.transit_lines}
    assert kinds == {"metro": {"underground"}, "elevated_rail": {"elevated"},
                     "sky_tube": {"sky"}}
    for t in m.transit_lines:
        assert len(t.station_ids) >= 2
        assert t.attrs["length_m"] > 300
    metro = next(t for t in m.transit_lines if t.mode == "metro")
    assert all(p[2] < 0 for p in metro.path)


def test_structures_and_walkways(lines):
    m = lines.model
    sup = [s for s in m.structures if s.kind in ("column", "pylon") and
           s.attrs.get("line_id")]
    decks = [s for s in m.structures if s.kind in ("deck", "tube") and s.attrs.get("line_id")]
    assert sup and decks
    walks = {w.id: w for w in m.walkways}
    for s in m.stations:
        assert s.access_ids and all(i in walks for i in s.access_ids)
        assert any(walks[i].kind in ("stairs", "escalator", "elevator") for i in s.access_ids)
    for w in m.walkways:
        assert all(n in walks for n in w.neighbors)


def test_report_has_transit_stats(lines):
    st = lines.stats["transit"]
    assert set(st["by_mode"]) == {"metro", "elevated_rail", "sky_tube"}
    assert st["km"] > 1.0 and st["supports"] > 0
    rep = lines.report()
    assert rep["stage"].startswith("M7") and "transit" in rep["stage"]
    assert "transit" in C.report_text(rep)


# --- failing checks ---------------------------------------------------------------------

def test_check_curves_fails(lines):
    def fn(d):
        t = _line(d, "elevated_rail")
        k = len(t["path"]) // 2
        (x0, y0, _), (x, y, z), (x1, y1, _) = t["path"][k - 1:k + 2]
        L = math.hypot(x1 - x0, y1 - y0)
        # a kink: the vertex 25 m off the track, across it
        t["path"][k] = [x - (y1 - y0) / L * 25.0, y + (x1 - x0) / L * 25.0, z]
    assert not _rerun(_mutate(lines.model, fn))["transit_curves"].passed


def test_check_grades_fails(lines):
    def fn(d):
        t = _line(d, "elevated_rail")
        t["path"][5][2] += 8.0
    assert not _rerun(_mutate(lines.model, fn))["transit_grades"].passed


def test_check_altitude_fails(lines):
    def fn(d):
        t = _line(d, "sky_tube")
        for p in t["path"]:
            p[2] = 20.0
    assert not _rerun(_mutate(lines.model, fn))["transit_altitude"].passed


def test_check_clearance_fails(lines):
    def fn(d):
        t = _line(d, "sky_tube")
        for b in d["buildings"]:
            b["portals"] = []
        # a vertex of the tube in the tallest building, under its roof
        b = max(d["buildings"], key=lambda b: (b["height_m"], b["id"]))
        x, y = G.from_model_poly(b["masses"][0]["footprint"]).representative_point().coords[0]
        t["path"][len(t["path"]) // 2] = [x, y, b["height_m"] / 2.0]
    assert not _rerun(_mutate(lines.model, fn))["transit_clearance"].passed


def test_check_supports_fails(lines):
    def fn(d):
        lane = d["lanes"][0]
        x, y, _ = lane["centerline"][0]
        s = next(s for s in d["structures"] if s["kind"] == "column")
        s["footprint"] = {"exterior": [[x - 0.8, y - 0.8], [x + 0.8, y - 0.8],
                                       [x + 0.8, y + 0.8], [x - 0.8, y + 0.8]],
                          "holes": []}
    assert not _rerun(_mutate(lines.model, fn))["transit_supports"].passed


def test_check_station_access_fails(lines):
    def fn(d):
        d["stations"][0]["access_ids"] = []
    assert not _rerun(_mutate(lines.model, fn))["station_access"].passed


def test_check_stops_fails(lines):
    def fn(d):
        t = _line(d, "elevated_rail")
        keep = t["station_ids"][:1]
        d["stations"] = [s for s in d["stations"] if s["id"] not in t["station_ids"][1:]]
        t["station_ids"] = keep
    assert not _rerun(_mutate(lines.model, fn))["transit_stops"].passed


def test_check_skybridges_fails(lines):
    def fn(d):
        t = _line(d, "elevated_rail")
        (x0, y0, z), (x1, y1, _) = t["path"][10], t["path"][11]
        nx, ny = -(y1 - y0), x1 - x0
        L = math.hypot(nx, ny)
        nx, ny = nx / L * 15, ny / L * 15
        sb = copy.deepcopy(d["skybridges"][0])
        sb.update({"id": "sbx", "line": [[x0 + nx, y0 + ny], [x0 - nx, y0 - ny]],
                   "z_m": z - 1.0})
        d["skybridges"].append(sb)
    assert not _rerun(_mutate(lines.model, fn))["transit_skybridges"].passed


def test_check_routes_fails(lines):
    def fn(d):
        d["transit_lines"] = [t for t in d["transit_lines"] if t["mode"] != "sky_tube"]
    assert not _rerun(_mutate(lines.model, fn))["transit_routes"].passed


def test_check_self_crossing_fails(lines):
    def fn(d):
        # the line runs back along itself, 3 m aside, at the same height
        t = _line(d, "elevated_rail")
        back = [[x + 3.0, y + 3.0, z] for x, y, z in t["path"][::-1]]
        t["path"] = t["path"] + back
    c = _rerun(_mutate(lines.model, fn))["transit_self_crossing"]
    assert not c.passed and "meets itself" in c.failures[0]


def test_check_self_crossing_passes_over(lines):
    def fn(d):
        # the same, but back 12 m higher: one passes over the other
        t = _line(d, "elevated_rail")
        back = [[x + 3.0, y + 3.0, z + 12.0] for x, y, z in t["path"][::-1]]
        t["path"] = t["path"] + back
    assert _rerun(_mutate(lines.model, fn))["transit_self_crossing"].passed


def test_check_self_crossing_order_fails(lines):
    def fn(d):
        t = next(t for t in d["transit_lines"] if t["loop"])
        t["attrs"]["stop_vertices"] = t["attrs"]["stop_vertices"][::-1]
    c = _rerun(_mutate(lines.model, fn))["transit_self_crossing"]
    assert not c.passed and "route order" in c.failures[0]


def test_check_self_crossing_open_loop_fails(lines):
    def fn(d):
        t = next(t for t in d["transit_lines"] if t["loop"])
        t["path"] = t["path"][:-5]
    assert not _rerun(_mutate(lines.model, fn))["transit_self_crossing"].passed


# --- loops (M8b) ------------------------------------------------------------------------

def test_loop_is_one_ring(lines):
    m = lines.model
    t = next(t for t in m.transit_lines if t.name == "Ring Line")
    assert t.loop
    pts = [(p[0], p[1]) for p in t.path]
    assert pts[0] == pts[-1]
    assert not TR.self_meets(pts, True, TR.WIDTH_M[t.mode])
    # simple in plan: the ring is a valid polygon
    assert shapely.Polygon(pts).is_valid
    # the stations of its stops in route order, each in its district
    at = t.attrs["stop_vertices"]
    assert at[0] == 0 and at[-1] == len(pts) - 1 and at == sorted(at)
    dist = {d.name: G.from_model_poly(d.polygon) for d in m.districts}
    for name, i in zip(t.attrs["stops"], at):
        assert dist[name].covers(shapely.Point(pts[i])), name
    # no step where the ring closes
    assert t.path[0][2] == t.path[-1][2]


def test_line_route_ignores_other_lines(lines, no_transit):
    """Each line on the same city alone and with the others: the same track (the other
    lines only meet it through the buildings they remove, which changes heights)."""
    spec = lines.spec
    every = TR.build(spec, no_transit)
    for name in ("Green Line", "Ring Line"):
        tl = next(x for x in spec.transit.lines if x.name == name)
        one = spec.model_copy(update={"transit": spec.transit.model_copy(
            update={"lines": [tl]})})
        alone = TR.build(one, no_transit)
        a = next(r for r in every.rows["transit_lines"] if r["name"] == name)
        b = alone.rows["transit_lines"][0]
        assert [p[:2] for p in a["path"]] == [p[:2] for p in b["path"]], name


def test_self_meets():
    # a figure eight crosses itself once; a circle does not; one passing 12 m over is clear
    eight = [(400.0 * math.sin(2 * math.pi * k / 120), 200.0 * math.sin(4 * math.pi * k / 120))
             for k in range(121)]
    assert len(TR.self_meets(eight, True, 9.0)) == 1
    ring = [(300.0 * math.cos(2 * math.pi * k / 120), 300.0 * math.sin(2 * math.pi * k / 120))
            for k in range(121)]
    assert TR.self_meets(ring, True, 9.0) == []
    zs = [12.0 if 30 <= k < 90 else 24.0 for k in range(121)]
    assert TR.self_meets(eight, True, 9.0, zs, TR.self_clear_m("elevated_rail")) == []


def test_graded_closed():
    # a loop with a 20 m bound just before its seam: the climb ramps down on both sides
    side = [(10.0 * k, 0.0) for k in range(25)]
    pts = side + [(250.0, y) for x, y in [(0, 10.0 * k) for k in range(25)]] + \
        [(250.0 - x, 250.0) for x, _ in side] + [(0.0, 250.0 - x) for x, _ in side] + [side[0]]
    vals = [0.0] * len(pts)
    vals[-3] = 20.0
    open_ = TR._graded(pts, vals, 0.04, max, -1.0, False)
    loop = TR._graded(pts, vals, 0.04, max, -1.0, True)
    assert open_[0] == 0.0 and loop[0] == loop[-1] > 0.0
    assert all(abs(a - b) <= 0.04 * math.dist(p, r) + 1e-9
               for a, b, p, r in zip(loop, loop[1:], pts, pts[1:]) if p != r)


def _grid(seed: int, n: int = 40):
    """A raster context n by n with random costs and walls (no city)."""
    rng = np.random.default_rng(seed)
    c = TR.Ctx(None, None)
    c.nx = c.ny = n
    cost = rng.uniform(1.0, 4.0, n * n)
    cost[rng.random(n * n) < 0.18] = TR.INF
    return c, cost


def _path_cost(c, cost, path, turn, din):
    cl = [min(x, 2.0) if x == TR.INF else x for x in cost.tolist()]
    prev = None if din is None else max(range(16), key=lambda k: (
        (TR._MOVES[k][0] * din[0] + TR._MOVES[k][1] * din[1]) / TR._MOVES[k][2], -k))
    tot = 0.0
    for u, v in zip(path, path[1:]):
        dx, dy = v % c.nx - u % c.nx, v // c.nx - u // c.nx
        k = next(i for i, mv in enumerate(TR._MOVES) if mv[:2] == (dx, dy))
        L = TR._MOVES[k][2]
        step = L * TR.CELL_M * (cl[u] + cl[v]) / 2.0
        if prev is not None:
            ddx, ddy, dL = TR._MOVES[prev]
            cs = (ddx * dx + ddy * dy) / (dL * L)
            if cs < 0.70:
                step += turn * (1.0 - cs)
        tot += step
        prev = k
    return tot


def test_search_cost_to_go(monkeypatch):
    """M8b: guided by the exact turn-free cost to go, the search finds paths as cheap as with
    the straight-distance heuristic; `_togo` never overestimates; a cell it cannot reach
    gives None."""
    for seed in range(4):
        c, cost = _grid(seed)
        a, b = 0, c.nx * c.ny - 1
        monkeypatch.setattr(TR, "TOGO_M", math.inf)
        plain = TR.search(c, cost, a, b, 300.0, (1.0, 0.0))
        monkeypatch.setattr(TR, "TOGO_M", 0.0)
        guided = TR.search(c, cost, a, b, 300.0, (1.0, 0.0))
        assert (plain is None) == (guided is None)
        if plain is not None:
            assert _path_cost(c, cost, guided, 300.0, (1.0, 0.0)) == \
                pytest.approx(_path_cost(c, cost, plain, 300.0, (1.0, 0.0)), abs=1e-6)
            togo = TR._togo(c, [min(x, 2.0) if x == TR.INF else x for x in cost.tolist()], b)
            assert togo[a] <= _path_cost(c, cost, guided, 0.0, None) + 1e-6
    c, cost = _grid(9)
    walled = cost.copy()
    walled[[c.nx * j + 20 for j in range(c.ny)]] = TR.INF   # a wall two cells thick
    walled[[c.nx * j + 21 for j in range(c.ny)]] = TR.INF
    walled[[c.nx * j + 22 for j in range(c.ny)]] = TR.INF
    assert not TR.reachable(c, walled, 0, c.nx - 1)
    assert TR.search(c, walled, 0, c.nx - 1, 300.0) is None


# --- geometry helpers -------------------------------------------------------------------

def test_arc_path_right_angle_radius():
    pts = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0)]
    out, r = TR.arc_path(pts, 150.0, False, lambda run: True, 300.0)
    assert out[0] == (0.0, 0.0) and out[-1] == (1000.0, 1000.0)
    assert r >= 150.0
    rr = TR.radii(TR.resample(out, 10.0), False)
    assert min(rr) >= 0.98 * 150.0


def test_arc_path_keeps_pins():
    # a shallow V: without the pin the middle vertex may go, with it the track passes it
    pts = [(0.0, 0.0), (300.0, -60.0), (600.0, 0.0)]
    out, _ = TR.arc_path(pts, 500.0, False, lambda run: True, 1000.0,
                         pins=frozenset({(300.0, -60.0)}))
    near = min(math.dist(p, (300.0, -60.0)) for p in out)
    assert near < 30.0


def _end_pose(pts):
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    return x1, y1, math.atan2(y1 - y0, x1 - x0)


@pytest.mark.parametrize("a, b", [
    ((0.0, 0.0, 0.0), (1500.0, 400.0, 0.0)),             # S-bend
    ((0.0, 0.0, 0.0), (0.0, 900.0, math.pi)),            # U-turn
    ((0.0, 0.0, math.pi / 2), (300.0, 0.0, -math.pi / 2)),  # close: a three-arc word
    ((0.0, 0.0, 0.0), (-800.0, 300.0, math.pi / 4)),     # behind it
])
def test_dubins_reaches_the_pose(a, b):
    rho = 200.0
    L, word, params = TR.dubins(a, b, rho)
    pts = TR.dubins_points(a, word, params, rho, step=5.0)
    x, y, h = _end_pose(pts)
    assert math.dist((x, y), b[:2]) < 0.05
    assert abs((h - b[2] + math.pi) % (2 * math.pi) - math.pi) < 0.05
    # the length is the path's, never shorter than the chord; no curve under the radius
    assert TR._plen(pts) == pytest.approx(L, abs=1.0)
    assert L >= math.dist(a[:2], b[:2]) - 1e-6
    assert min(TR.radii(TR.resample(pts, 10.0), False)) >= 0.98 * rho


def test_dubins_ring(lines):
    """A loop as one ring of Dubins paths on the test city: closed, clear of itself and of
    every cell the line cannot pass, its curves at the radius, each stop passed inside its
    district in route order."""
    m = lines.model
    spec = lines.spec
    with G.canonical():
        c = TR.context(spec, m)
        ln = TR.Line("tl99", "Test Ring", "elevated_rail", "#fff", True, (8.0, 20.0),
                     TR.base_z("elevated_rail", (8.0, 20.0)), False)
        ln.stops = [TR.resolve_stop(c, n, ln.mode)
                    for n in ("Harbor", "Old Quarter", "Uptown", "Core", "Harbor")]
        ring = TR._loop_points(c, ln)
        for s, p in zip(ln.stops, ring or [s.p for s in ln.stops]):
            s.p = p
        cost = TR.costs(c, ln.mode, ln.z0, False, None, 20.0, 8.0)[0]
        res = TR._dubins_track(c, ln, cost, 80.0)
    assert res is not None
    track, passes, rho = res
    assert track[0] == track[-1] and len(passes) == 4
    assert not TR.self_meets(track, True, TR.WIDTH_M[ln.mode])
    assert all(np.isfinite(cost[TR.cell_of(c, p)]) for p in track)
    assert min(TR.radii(TR.resample(track[:-1], 10.0, True), True)) >= 0.98 * rho
    for s, p in zip(ln.stops[:-1], passes):
        s.p = p
    at = TR.ordered_stops(track, ln.stops, True)
    assert at == sorted(at)
    dist = {d.name: G.from_model_poly(d.polygon) for d in m.districts}
    for s, i in zip(ln.stops, at):
        assert dist[s.name].covers(shapely.Point(track[i])), s.name


def test_served_exit():
    s = TR.Stop("north_exit", (0.0, 1000.0), None, "exit")
    assert TR._served([(0.0, 0.0), (0.0, 900.0)], s)
    assert not TR._served([(0.0, 0.0), (400.0, 700.0)], s)


def test_z_at_interpolates():
    prof = [(0.0, 0.0), (100.0, 10.0), (200.0, 10.0)]
    assert TR._z_at(prof, 50.0) == pytest.approx(5.0)
    assert TR._z_at(prof, 250.0) == 10.0
    assert TR._z_at(prof, -5.0) == 0.0


class _B:
    def __init__(self, top, portal_ok=True, bottom=0.0):
        self.top, self.portal_ok, self.bottom = top, portal_ok, bottom


def test_sky_pass():
    alt = (70.0, 120.0)
    assert TR.sky_pass(_B(60.0), 92.5, alt, True) == "clear"
    assert TR.sky_pass(_B(85.0), 92.5, alt, True) == "climb"      # 2.5 m up beats 19 m down
    assert TR.sky_pass(_B(102.0), 92.5, alt, True) == "portal"    # 4 m down beats 19.5 m up
    assert TR.sky_pass(_B(200.0), 92.5, alt, True) == "portal"
    assert TR.sky_pass(_B(200.0), 92.5, alt, False) == "block"
    assert TR.sky_pass(_B(200.0, portal_ok=False), 92.5, alt, True) == "block"
    assert TR.sky_pass(_B(105.0, portal_ok=False), 92.5, alt, True) == "climb"


# --- determinism ---------------------------------------------------------------------

def test_workers_do_not_change_m5():
    spec = validate_spec(copy.deepcopy(LINES))
    a = build_city(spec, workers=1).model.to_json()
    b = build_city(spec, workers=3).model.to_json()
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


_ACTIVE = [False]


def _perturb(v):
    c = np.asarray(v, dtype=np.float64)
    moved = np.nextafter(np.nextafter(c, np.inf), np.inf)
    return np.where(np.abs(c * 1000.0 - np.rint(c * 1000.0)) < 1e-6, c, moved)


def test_transit_stage_ignores_ulp_noise(monkeypatch, lines, no_transit):
    """The transit stage twice on the same M3 model, the second time with 2-ULP noise on what
    GEOS computes inside it (grid values and fixed-precision overlays aside): the same
    rows."""
    spec = lines.spec
    m3 = CityModel.model_validate(json.loads(lines.model.to_json()))
    # the stage runs on the M3 model: the city without transit
    base = no_transit
    clean = TR.build(spec, base)
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
        noisy_out = TR.build(spec, base)
    finally:
        _ACTIVE[0] = False
    a = json.dumps(clean.rows["transit_lines"], sort_keys=True, default=str)
    b = json.dumps(noisy_out.rows["transit_lines"], sort_keys=True, default=str)
    assert a == b
    assert len(m3.transit_lines) == len(clean.rows["transit_lines"])
