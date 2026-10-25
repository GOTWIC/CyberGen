"""M1b: primary roads, bridges, megasite reserves, and cross-machine determinism.

Covers every highway pattern, bridge classes and ramps, connectivity (islands included),
avoidance of megasites, flight cones, marsh and park, curve radius, segment length,
duplicates, quantization (every coordinate on the 0.01 m grid), the golden hashes of the
sample cities, and the deterministic math.
"""

import copy
import hashlib
import json
import math
import os
import platform
import subprocess
import sys

import numpy as np
import pytest
from shapely.geometry import LineString, Point, box

from citygen import checks as C
from citygen import elevated as EL
from citygen import dmath as M
from citygen import geom as G
from citygen import roads as RD
from citygen.build import build_city
from citygen.cli import EXIT_OK
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import CITIES, GOLDEN, ROOT, SMALL, built_sample, write

PATTERNS = ["ring", "ring_plus_spine", "spine", "grid", "radial", "coastal", "none"]


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def small_built():
    return _build(copy.deepcopy(SMALL))


def _checks(spec_data, model: CityModel) -> dict[str, C.Check]:
    spec = validate_spec(spec_data).filled
    checks, _ = C.run_checks(spec, model, roads=True)
    return {c.id: c for c in checks}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


# --- highways -------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", PATTERNS)
def test_highway_pattern(pattern):
    data = copy.deepcopy(SMALL)
    data["highways"] = {"pattern": pattern}
    b = _build(data)
    failed = [f for c in b.checks for f in c.failures]
    assert not failed, failed
    roles = {s.attrs["role"] for s in b.model.road_segments if s.road_class == "highway"}
    expect = {"ring": {"ring"}, "ring_plus_spine": {"ring", "spine"}, "spine": {"spine"},
              "grid": {"grid"}, "radial": {"radial"}, "coastal": {"coastal"}, "none": set()}
    assert expect[pattern] <= roles, roles
    if pattern == "none":
        assert not roles
    # every exit leaves the map at the map edge
    exits = {n.attrs["exit"]: n.position for n in b.model.road_nodes
             if n.attrs.get("kind") == "exit"}
    assert set(exits) == {f"{d}_exit" for d in b.spec.highways.exits}
    minx, miny, maxx, maxy = b.model.bounds
    for x, y, _ in exits.values():
        assert min(x - minx, maxx - x, y - miny, maxy - y) < 0.01


def test_named_highway_route():
    data = copy.deepcopy(SMALL)
    data["highways"] = {"pattern": "none", "exits": ["north"],
                        "named": [{"name": "Harbor Link", "route": ["Harbor", "Old Quarter"]}]}
    b = _build(data)
    names = {s.name for s in b.model.road_segments if s.road_class == "highway"}
    assert "Harbor Link" in names


def test_elevated_share_is_an_attribute(small_built):
    hw = [s for s in small_built.model.road_segments if s.road_class == "highway"]
    # M7: viaducts and their ramps are on level 1 or 2, every other road on level 0
    for s in small_built.model.road_segments:
        up = bool(s.attrs.get("elevated")) or s.attrs.get("role") == "ramp"
        assert (s.level >= 1) == up, s.id
    total = sum(LineString(s.centerline).length for s in hw)
    elev = sum(LineString(s.centerline).length for s in hw if s.attrs.get("elevated"))
    want = small_built.spec.highways.elevated_share
    # whole segments are marked, so the share lands near the target, not on it
    assert abs(elev / total - want) < 0.25


# --- bridges ----------------------------------------------------------------------------

def test_bridge_classes_and_ramps(small_built):
    m = small_built.model
    classes = {b.water_class for b in m.bridges}
    assert {"sea", "river", "canal"} <= classes
    for b in m.bridges:
        lo, hi = C.CLEARANCE_RANGE_M[b.water_class]
        assert lo <= b.clearance_m <= hi
        if b.attrs.get("footbridge"):  # M2 footbridges: stairs, no ramps
            assert b.ramp_length_m is None and b.attrs["access"] == "stairs"
            continue
        assert b.ramp_length_m == pytest.approx((b.clearance_m + 1.5) / EL.APPROACH_GRADE,
                                                abs=0.01)
        # (M7 raises a deck that carries a viaduct or crosses another bridge)
        assert all(z >= b.clearance_m + 1.5 - 0.01 for _, _, z in b.line)
    # sea crossings stay few: only where a landmass needs one
    assert sum(1 for b in m.bridges if b.water_class == "sea" and
               not b.attrs.get("footbridge")) <= 2


def test_clearance_by_width():
    assert RD.clearance_for(RD.SEA, 300.0) == 25.0
    assert RD.clearance_for(RD.RIVER, 40.0) == 10.0
    assert RD.clearance_for(RD.RIVER, 150.0) == 15.0
    assert 10.0 < RD.clearance_for(RD.RIVER, 90.0) < 15.0
    assert RD.clearance_for(RD.CANAL, 14.0) == 3.0
    assert RD.clearance_for(RD.CANAL, 40.0) == 4.0


def test_check_bridge_clearance_fails(small_built):
    m = small_built.model
    river = next(i for i, b in enumerate(m.bridges) if b.water_class == "river")
    bad = _mutate(m, lambda d: d["bridges"][river].update(clearance_m=4.0))
    assert not _checks(SMALL, bad)["bridge_clearance"].passed
    wrong = _mutate(m, lambda d: d["bridges"][river].update(water_class="canal"))
    assert not _checks(SMALL, wrong)["bridge_clearance"].passed


def test_road_over_water_needs_a_bridge(small_built):
    m = small_built.model
    seg = next(s for s in m.road_segments if s.bridge)
    k = next(i for i, s in enumerate(m.road_segments) if s.id == seg.id)
    bad = _mutate(m, lambda d: d["bridges"].__setitem__(
        slice(None), [b for b in d["bridges"] if seg.id not in b["segment_ids"]]))
    failures = _checks(SMALL, bad)["bridge_clearance"].failures
    assert any(m.road_segments[k].id in f and "without a bridge" in f for f in failures)


def test_named_bridges_built():
    data = copy.deepcopy(SMALL)
    data["water"]["bridges"] = {"named": [
        {"name": "Isle Bridge", "kind": "road_rail", "connects": ["Old Quarter", "Test Isle"],
         "crosses": "sea"},
        {"name": "Isle Walk", "kind": "pedestrian", "connects": ["Core", "Test Isle"]}]}
    b = _build(data)
    assert b.passed, [f for c in b.checks for f in c.failures]
    by_name = {x.name: x for x in b.model.bridges if x.name}
    assert by_name["Isle Bridge"].bridge_class == "road_rail"
    assert by_name["Isle Bridge"].water_class == "sea"
    assert by_name["Isle Walk"].bridge_class == "pedestrian"
    assert not by_name["Isle Walk"].segment_ids
    gone = _mutate(b.model, lambda d: [x.update(name=None) for x in d["bridges"]
                                       if x["name"] == "Isle Bridge"])
    assert not _checks(data, gone)["named_bridges"].passed


# --- connectivity -------------------------------------------------------------------------

def test_islands_connected(small_built):
    m = small_built.model
    isle = next(lm for lm in m.landmasses if lm.attrs.get("island") == "Test Isle")
    poly = G.from_model_poly(isle.polygon)
    on_isle = [s for s in m.road_segments if LineString(s.centerline).intersects(poly)]
    assert on_isle
    assert small_built.stats["landmasses_connected"] == [len(m.landmasses)] * 2
    assert small_built.stats["road_components"] == 1


def test_check_road_graph_fails_when_island_cut_off(small_built):
    m = small_built.model
    sea = next(b for b in m.bridges if b.water_class == "sea")
    drop = set(sea.segment_ids)
    cut = _mutate(m, lambda d: d.update(
        road_segments=[s for s in d["road_segments"] if s["id"] not in drop],
        bridges=[b for b in d["bridges"] if b["id"] != sea.id]))
    assert not _checks(SMALL, cut)["road_graph"].passed


def test_check_districts_served_fails(small_built):
    m = small_built.model
    core = next(d for d in m.districts if d.name == "Core")
    poly = G.from_model_poly(core.polygon).buffer(30.0)
    gone = _mutate(m, lambda d: d.update(road_segments=[
        s for s in d["road_segments"]
        if s["road_class"] != "avenue" or not LineString(s["centerline"]).intersects(poly)]))
    assert not _checks(SMALL, gone)["districts_served"].passed


# --- avoidance ----------------------------------------------------------------------------

def _through(model: CityModel, poly) -> list:
    return [s.id for s in model.road_segments
            if LineString(s.centerline).intersection(poly).length > 1.0]


@pytest.mark.parametrize("path", CITIES, ids=lambda p: p.parent.name)
def test_roads_avoid_reserves_cones_marsh_park(path):
    b, _, _ = built_sample(path)
    m = b.model
    for site in m.megasites:
        assert not _through(m, G.from_model_poly(site.polygon)), site.name
        if site.flight_cone is not None:
            assert not _through(m, G.from_model_poly(site.flight_cone)), site.name
    for o in m.open_spaces:
        if o.kind not in ("marsh", "park"):  # plazas and promenades carry pedestrian streets
            continue
        hits = [sid for sid in _through(m, G.from_model_poly(o.polygon))
                if not next(s for s in m.road_segments if s.id == sid).attrs.get("causeway")]
        assert not hits, (o.name, hits)


def test_check_avoidance_fails(small_built):
    m = small_built.model
    seg = m.road_segments[0]
    p = LineString(seg.centerline).interpolate(0.5, normalized=True)
    site = box(p.x - 40, p.y - 40, p.x + 40, p.y + 40)
    marsh = box(p.x - 60, p.y - 60, p.x + 60, p.y + 60)
    with_site = _mutate(m, lambda d: d["megasites"].append({
        "id": "d01.ms09", "type": "megasite.stadium", "kind": "stadium", "name": "Test Bowl",
        "district_id": "d01", "polygon": G.to_model_poly(site)}))
    assert not _checks(SMALL, with_site)["road_avoidance"].passed
    with_marsh = _mutate(m, lambda d: d["open_spaces"].append({
        "id": "os09", "type": "open_space.marsh", "kind": "marsh", "name": "Test Marsh",
        "polygon": G.to_model_poly(marsh)}))
    assert not _checks(SMALL, with_marsh)["road_avoidance"].passed
    causeway = _mutate(with_marsh, lambda d: [s["attrs"].update(causeway=True)
                                              for s in d["road_segments"]])
    assert _checks(SMALL, causeway)["road_avoidance"].passed


# --- alignment ------------------------------------------------------------------------------

def test_min_radius_measure():
    r = 120.0
    arc = LineString([(r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, 1.5, 200)])
    got, _ = C.min_radius(arc, 10.0)
    assert got == pytest.approx(r, rel=0.02)
    straight = LineString([(0, 0), (500, 0)])
    assert math.isinf(C.min_radius(straight, 10.0)[0])


def test_fillet_keeps_min_radius():
    ctx_free = type("F", (), {})()
    fit = RD.Fitter.__new__(RD.Fitter)
    fit.ctx = ctx_free
    pts = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (800.0, 400.0)]
    line, rmin = fit.fillet(pts, {0, 3}, "highway")
    assert rmin >= RD.CLASSES["highway"]["r_min"]
    got, _ = C.min_radius(line, 20.0)
    assert got >= 0.95 * RD.CLASSES["highway"]["r_min"]


@pytest.mark.parametrize("path", CITIES, ids=lambda p: p.parent.name)
def test_sample_alignment_rules(path):
    b, _, _ = built_sample(path)
    for cid in ("curve_radius", "segment_length", "road_duplicates"):
        check = next(c for c in b.checks if c.id == cid)
        assert check.passed, check.failures


def test_check_curve_radius_fails_on_a_kink(small_built):
    m = small_built.model
    deg: dict[str, int] = {}
    for s in m.road_segments:
        deg[s.start] = deg.get(s.start, 0) + 1
        deg[s.end] = deg.get(s.end, 0) + 1
    k, seg = max(((i, s) for i, s in enumerate(m.road_segments)
                  if s.road_class in ("highway", "avenue")),
                 key=lambda t: LineString(t[1].centerline).length)
    (x0, y0), (x1, y1) = seg.centerline[0], seg.centerline[-1]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0), x1 - x0
    n = math.hypot(nx, ny)
    kink = [(x0, y0), (mx + 120.0 * nx / n, my + 120.0 * ny / n), (x1, y1)]
    bad = _mutate(m, lambda d: d["road_segments"][k].update(centerline=kink))
    assert not _checks(SMALL, bad)["curve_radius"].passed


def test_check_segment_length_and_duplicates(small_built):
    m = small_built.model
    ordinary = {n.id for n in m.road_nodes if n.attrs.get("kind") == "junction"}
    # an avenue as M1b laid it: its pieces between M2 street junctions share `m1b_segment`
    # (and the pieces M7 split it into, `split_of`)
    groups: dict = {}
    for i, s in enumerate(m.road_segments):
        if s.road_class == "avenue":
            groups.setdefault(s.attrs.get("split_of") or s.attrs.get("m1b_segment", s.id),
                              []).append(i)
    def ordered(idx):
        by_start = {m.road_segments[i].start: i for i in idx}
        ends = {m.road_segments[i].end for i in idx}
        cur = next(i for i in idx if m.road_segments[i].start not in ends)
        out = [cur]
        while m.road_segments[cur].end in by_start and len(out) < len(idx):
            cur = by_start[m.road_segments[cur].end]
            out.append(cur)
        return out

    chains = [ordered(v) for _, v in sorted(groups.items())]
    idx = max((c for c in chains if m.road_segments[c[0]].start in ordinary
               and m.road_segments[c[-1]].end in ordinary), key=len)
    k = idx[0]
    chain = list(m.road_segments[k].centerline)
    for i in idx[1:]:
        chain += list(m.road_segments[i].centerline)[1:]
    a = m.road_segments[k].centerline[0]

    def shorten(d):
        d["road_segments"][k].update(centerline=[a, (a[0] + 10.0, a[1])])
        d["road_segments"] = [s for j, s in enumerate(d["road_segments"])
                              if j not in idx[1:]]
    assert not _checks(SMALL, _mutate(m, shorten))["segment_length"].passed
    twin = json.loads(m.road_segments[k].model_dump_json())
    twin["id"] = "rs9999"
    twin["attrs"].pop("m1b_segment", None)
    twin["centerline"] = [(x + 8.0, y + 8.0) for x, y in LineString(chain).coords]
    dup = _mutate(m, lambda d: d["road_segments"].append(twin))
    assert LineString(chain).length > C.ROAD_DUP_LEN_M + 150
    assert not _checks(SMALL, dup)["road_duplicates"].passed


# --- quantization and determinism ------------------------------------------------------------

COORD_KEYS = ("exterior", "holes", "centerline", "line", "position", "polygons", "bounds",
              "flight_cone", "polygon")


def _coords(node, inside=False):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _coords(v, inside or k in COORD_KEYS)
    elif isinstance(node, list):
        for v in node:
            yield from _coords(v, inside)
    elif inside and isinstance(node, (int, float)) and not isinstance(node, bool):
        yield node


def test_every_coordinate_on_the_grid(small_built):
    data = json.loads(small_built.model.to_json())
    values = list(_coords(data))
    assert len(values) > 10_000
    off = [v for v in values if abs(v * 100 - round(v * 100)) > 1e-6]
    assert not off, off[:5]
    for s in data["road_segments"]:
        for z in s["z_profile"]:
            assert abs(z["s"] * 100 - round(z["s"] * 100)) < 1e-6
            assert abs(z["z"] * 100 - round(z["z"] * 100)) < 1e-6


def test_barriers_absorb_machine_noise():
    """Last-bit noise entering any quantization barrier (1e-9 m, far above the 1e-13 m of
    a few ULP at city scale) changes nothing."""
    def one_process():  # the jitter is set in this process only
        return build_city(validate_spec(copy.deepcopy(SMALL)), workers=1).model.to_json()

    base = one_process()
    G.JITTER_M = 1e-9
    try:
        noisy = one_process()
    finally:
        G.JITTER_M = 0.0
    assert noisy == base


@pytest.mark.skipif(platform.machine().lower() not in ("x86_64", "amd64"),
                    reason="the SIMD switch below names x86 features")
def test_same_model_without_simd(tmp_path):
    """numpy's AVX512 math (Intel SVML) against its baseline code path: same bytes."""
    spec = write(tmp_path, SMALL)
    outs = []
    for k, env_extra in enumerate(({}, {"NPY_DISABLE_CPU_FEATURES":
                                        "X86_V3 X86_V4 AVX512_ICL AVX512_SPR"})):
        out = tmp_path / f"out{k}"
        env = {**os.environ, **env_extra}
        proc = subprocess.run([sys.executable, "-m", "citygen", "build", str(spec), str(out)],
                              cwd=ROOT, env=env, capture_output=True, text=True)
        if proc.returncode != EXIT_OK and "NPY_DISABLE_CPU_FEATURES" in proc.stderr:
            pytest.skip("this numpy cannot disable those features")
        assert proc.returncode == EXIT_OK, proc.stderr
        outs.append((out / "city_model.json").read_bytes())
    assert outs[0] == outs[1]


def test_golden_hashes():
    """sha256 of every sample city_model.json, as committed (produced on the cloud machine,
    x86_64 Linux; the same bytes are expected on the M4 Mac)."""
    golden = json.loads(GOLDEN.read_text())
    assert set(golden["cities"]) == {p.parent.name for p in CITIES}
    wrong = []
    for path in CITIES:
        _, _, data = built_sample(path)
        got, want = hashlib.sha256(data).hexdigest(), golden["cities"][path.parent.name]
        if got != want:
            wrong.append(f"{path.parent.name}: {got} (golden {want})")
    # every city is built and compared, so one run names all that differ
    assert not wrong, "sample cities differ from the golden hashes:\n" + "\n".join(wrong)


def test_dmath_matches_libm():
    rng = np.random.default_rng(3)
    x = rng.uniform(-80, 80, 50_000)
    assert np.max(np.abs(M.sin(x) - np.sin(x))) < 1e-14
    assert np.max(np.abs(M.cos(x) - np.cos(x))) < 1e-14
    e = rng.uniform(-40, 8, 50_000)
    assert np.max(np.abs(M.exp(e) / np.exp(e) - 1)) < 1e-14
    p = rng.uniform(1e-6, 1e6, 50_000)
    assert np.max(np.abs(M.log(p) - np.log(p))) < 1e-13
    y, z = rng.uniform(-5, 5, (2, 50_000))
    assert np.max(np.abs(M.atan2(y, z) - np.arctan2(y, z))) < 1e-14
    assert isinstance(M.sin(0.3), float) and isinstance(M.hypot(3.0, 4.0), float)
    assert M.hypot(3.0, 4.0) == 5.0
    assert M.atan2(0.0, -1.0) == pytest.approx(math.pi)


def test_report_has_road_stats(small_built):
    st = small_built.stats
    for key in ("road_km", "bridges_by_class", "landmasses_connected", "exits",
                "named_bridges", "road_components"):
        assert key in st
    text = C.report_text(small_built.report())
    assert "roads " in text and "bridges " in text


def test_samples_point_at_m1b_outputs():
    for path in CITIES:
        assert (ROOT / "docs" / "progress" / "M1b" / path.parent.name).is_dir()
