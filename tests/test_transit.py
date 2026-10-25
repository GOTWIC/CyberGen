"""M5: transit lines, stations, supports and walkways; each transit check with a failing case,
the track geometry helpers, determinism of the transit stage."""

import copy
import functools
import hashlib
import json
import math

import numpy as np
import pytest
import shapely

from citygen import checks as C
from citygen import transit as TR
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import SMALL

TRANSIT_CHECKS = {"transit_routes", "transit_stops", "transit_curves", "transit_grades",
                  "transit_altitude", "transit_clearance", "transit_supports",
                  "station_access", "transit_skybridges", "transit_hubs"}

# The small city with one line of each kind: underground, along the avenues, through towers.
LINES = copy.deepcopy(SMALL)
LINES["name"] = "Testport Lines"
LINES["transit"] = {"lines": [
    {"mode": "metro", "name": "Red Line", "route": ["Harbor", "Core", "Uptown"]},
    {"mode": "elevated_rail", "name": "Green Line", "route": ["Harbor", "Core", "Old Quarter"]},
    {"mode": "sky_tube", "name": "Sky Line", "through_towers": True,
     "route": ["Core", "Uptown"]},
]}


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def lines():
    return _build(copy.deepcopy(LINES))


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
    assert [t.name for t in m.transit_lines] == ["Red Line", "Green Line", "Sky Line"]
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
    assert rep["stage"].startswith("M6") and "transit" in rep["stage"]
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
        b = next(b for b in d["buildings"] if b["portals"])
        b["portals"] = []
        for p in t["path"]:
            p[2] = 60.0
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


def test_transit_stage_ignores_ulp_noise(monkeypatch):
    """The transit stage twice on the same M3 model, the second time with 2-ULP noise on what
    GEOS computes inside it (grid values and fixed-precision overlays aside): the same
    rows."""
    lines_b = _build(copy.deepcopy(LINES))
    spec = lines_b.spec
    m3 = CityModel.model_validate(json.loads(lines_b.model.to_json()))
    # the stage runs on the M3 model: rebuild it without transit
    no_tr = copy.deepcopy(LINES)
    no_tr["transit"] = {"lines": []}
    base = _build(no_tr).model
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
