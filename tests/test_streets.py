"""M2: local streets, junctions, sidewalks, crosswalks, lane and walkway graphs, blocks, lots,
open space and places.

Covers the street pattern of every archetype, footbridge spacing, lot frontage, lane and
walkway connectivity, junction angles, no junction on a bridge or ramp, each new check with a
failing case, and determinism inside the new stages (4-ULP noise on every GEOS result, the
scalar paths of `dmath`, canonical snapping).
"""

import copy
import functools
import hashlib
import json
import math

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Point

from citygen import checks as C
from citygen import dmath as M
from citygen import geom as G
from citygen import local as LC
from citygen import street_checks as SC
from citygen import streets as ST
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import load_spec, validate_spec

from conftest import CITIES, ROOT, SMALL, built_sample

# A second small city with the archetypes SMALL lacks.
SMALL2 = {
    "name": "Testgrid", "seed": 11, "size_km": [2.6, 2.6],
    "water": {"coast": {"form": "straight", "side": "south", "sea_share": 0.25},
              "rivers": [{"name": "Mid River", "from": "north", "to": "sea",
                          "width_m": [45, 70]}]},
    "highways": {"pattern": "spine"},
    "districts": [
        {"name": "Hub", "archetype": "transit_hub", "placement": {"edge": "center"}},
        {"name": "Blocks", "archetype": "megablock_residential",
         "placement": {"edge": "north"}},
        {"name": "Mid", "archetype": "midtown_mixed", "placement": {"west_of": "Hub"}},
        {"name": "Lights", "archetype": "entertainment_market",
         "placement": {"east_of": "Hub", "coast": True},
         "places": [{"name": "Lantern Plaza", "kind": "plaza"},
                    {"name": "Night Lane", "kind": "street"}]},
        {"name": "Pads", "archetype": "spaceport", "placement": {"coast": True,
                                                                  "south_of": "Hub"}},
    ],
}
VESPER_BAY = ROOT / "cities" / "vesper_bay" / "city_spec.json"


def _build(data):
    result = validate_spec(copy.deepcopy(data))
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def small():
    return _build(SMALL)


@pytest.fixture(scope="module")
def small2():
    return _build(SMALL2)


def _checks(spec_data, model: CityModel) -> dict:
    spec = validate_spec(copy.deepcopy(spec_data)).filled
    checks, _ = C.run_checks(spec, model, roads=True)
    return {c.id: c for c in checks}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


def _roles(m: CityModel, name: str) -> set:
    did = next(d.id for d in m.districts if d.name == name)
    return {s.attrs.get("role") for s in m.road_segments if s.attrs.get("district") == did}


def test_new_checks_pass(small, small2):
    for b in (small, small2):
        failed = [f for c in b.checks for f in c.failures]
        assert not failed, failed
        ids = {c.id for c in b.checks}
        assert {"street_graph", "lane_graph", "walkway_graph", "lot_frontage",
                "lot_block_sizes", "lot_slivers", "sidewalk_clear_path", "crosswalks",
                "junction_placement", "junction_angles", "street_duplicates",
                "open_space_share", "places_built"} <= ids
        assert len(b.checks) == 82  # 31 to M2, 13 M3, 6 M6, 5 M7, 4 M9, 9 M11, 2 M12, 5 M13,
        #                              4 M17, 3 M16


# --- street patterns by archetype ------------------------------------------------------

def test_patterns_small(small):
    m = small.model
    assert {"grid_u", "grid_v"} & _roles(m, "Core")                      # corporate grid
    assert {"organic", "alley"} <= _roles(m, "Old Quarter")              # organic, alleys
    assert {"grid_u", "grid_v", "quay_road"} & _roles(m, "Harbor")       # port grid
    assert {"loop", "cul_de_sac"} <= _roles(m, "Uptown")                 # loops, cul-de-sacs
    assert "campus_loop" in _roles(m, "Test Isle")                       # campus loop
    assert any(o.name == "campus green" for o in m.open_spaces)


def test_patterns_small2(small2):
    m = small2.model
    assert "service_lane" in _roles(m, "Blocks")                         # superblocks
    mid = _roles(m, "Mid")
    assert {"grid_u", "grid_v"} & mid and ("reserve_ring" in mid or any(
        s.attrs.get("role") == "ring_road" for s in m.road_segments))   # grid, park ring
    assert {"organic", "alley"} <= _roles(m, "Lights")                   # market
    assert {"ring", "radial"} <= _roles(m, "Hub")                        # radial and rings
    pads = _roles(m, "Pads")
    assert {"reserve_ring", "quay_road"} & pads                          # service roads


def test_old_town_has_dead_ends_and_narrow_one_ways(small):
    m = small.model
    did = next(d.id for d in m.districts if d.name == "Old Quarter")
    deg: dict = {}
    for s in m.road_segments:
        for n in (s.start, s.end):
            deg[n] = deg.get(n, 0) + 1
    dead = [s for s in m.road_segments if s.attrs.get("district") == did and
            (deg[s.start] == 1 or deg[s.end] == 1)]
    assert dead
    assert all(s.cross_section.total_width_m <= 10.0 for s in m.road_segments
               if s.attrs.get("district") == did and s.road_class == "street")


def test_grid_angle_followed(small):
    """The corporate core grid runs at its grid angle (45 degrees by preset)."""
    m = small.model
    did = next(d.id for d in m.districts if d.name == "Core")
    angles = []
    for s in m.road_segments:
        if s.attrs.get("district") == did and s.attrs.get("role") in ("grid_u", "grid_v"):
            (x0, y0), (x1, y1) = s.centerline[0], s.centerline[-1]
            angles.append(M.degrees(M.atan2(y1 - y0, x1 - x0)) % 90.0)
    assert angles
    assert sum(1 for a in angles if abs(a - 45.0) < 3.0) >= 0.8 * len(angles)


# --- footbridges, junctions ----------------------------------------------------------------

def test_footbridge_spacing():
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    feet = [s for s in m.road_segments if s.road_class == "footbridge"]
    assert len(feet) >= 3
    br = {x.id: x for x in m.bridges}
    by_water: dict = {}
    for s in feet:
        bb = br[s.bridge_ids[0]]
        assert bb.bridge_class == "pedestrian" and bb.water_class == "canal"
        assert 3.0 <= bb.clearance_m <= 4.0 and bb.ramp_length_m is None
        mid = LineString(s.centerline).interpolate(0.5, normalized=True)
        by_water.setdefault(bb.crosses, []).append(mid)
    for pts in by_water.values():
        for i, a in enumerate(pts):
            for c in pts[i + 1:]:
                assert a.distance(c) >= 100.0


def test_junction_geometry(small):
    m = small.model
    assert m.junctions and all(j.legs >= 3 or j.shape in ("cul_de_sac", "bend")
                               for j in m.junctions)
    pos = {n.id: n.position[:2] for n in m.road_nodes}
    for j in m.junctions[:200]:
        poly = G.from_model_poly(j.polygon)
        assert poly.is_valid and poly.buffer(1.0).contains(Point(pos[j.node_id]))
    sig = [j for j in m.junctions if j.signalized]
    assert sig and all(j.crosswalk_ids for j in sig)
    assert all(sw.clear_path_m >= 1.8 for sw in m.sidewalks)


def _junction_model(angle_deg: float) -> CityModel:
    """Three streets at a node: east, at angle_deg, and west."""
    cs = ST.cross_section("street", "midtown_mixed")
    cs = {k: v for k, v in cs.items()}
    a = M.radians(angle_deg)
    ends = [(100.0, 0.0), (G.q(100.0 * M.cos(a)), G.q(100.0 * M.sin(a))), (-100.0, 0.0)]
    nodes = [{"id": "rn00001", "position": (0.0, 0.0, 0.0)}]
    segs = []
    for k, e in enumerate(ends):
        nodes.append({"id": f"rn{k + 2:05d}", "position": (e[0], e[1], 0.0)})
        segs.append({"id": f"rs{k + 1:05d}", "start": "rn00001", "end": f"rn{k + 2:05d}",
                     "road_class": "street", "lanes": 2, "width_m": cs["total_width_m"],
                     "centerline": [(0.0, 0.0), e], "cross_section": cs,
                     "attrs": {"role": "grid_u"}})
    return CityModel.model_validate({"name": "t", "seed": 1, "bounds": (-200, -200, 200, 200),
                                     "road_nodes": nodes, "road_segments": segs})


def test_check_junction_angles():
    ok = SC.check_junction_angles(_junction_model(90.0), SC._Net(_junction_model(90.0)))
    assert ok.passed
    m = _junction_model(25.0)
    bad = SC.check_junction_angles(m, SC._Net(m))
    assert not bad.passed and "minimum 60" in bad.failures[0]


def test_sample_junction_angles_and_placement(small):
    checks = {c.id: c for c in small.checks}
    assert checks["junction_angles"].passed
    assert checks["junction_placement"].passed


def test_no_junction_on_a_bridge(small):
    """A local street joined on a bridge approach fails `junction_placement`."""
    m = small.model
    seg = next(s for s in m.road_segments if s.bridge_ids and
               s.road_class in ("avenue", "highway"))
    br = next(b for b in m.bridges if b.id == seg.bridge_ids[0])
    # move the segment's start node next to the bridge: its first point becomes the
    # bridge's first point, so the node sits on the bridge, and add a local street there
    p = br.line[0][:2]

    def fn(d):
        s = next(x for x in d["road_segments"] if x["id"] == seg.id)
        s["centerline"][0] = list(p)
        for n in d["road_nodes"]:
            if n["id"] == s["start"]:
                n["position"] = [p[0], p[1], 0.0]
        tmpl = next(x for x in d["road_segments"] if x["road_class"] == "street")
        for k, e in enumerate(((p[0] + 40.0, p[1] + 40.0), (p[0] - 40.0, p[1] + 45.0))):
            new = copy.deepcopy(tmpl)
            new["id"] = f"rs9999{k}"
            new["start"] = s["start"]
            new["end"] = f"rn9999{k}"
            new["centerline"] = [list(p), list(e)]
            new["bridge_ids"] = []
            new["bridge"] = False
            d["road_nodes"].append({"id": f"rn9999{k}", "type": "road_node",
                                    "position": [e[0], e[1], 0.0], "level": 0, "attrs": {}})
            d["road_segments"].append(new)

    m2 = _mutate(m, fn)
    c = SC.check_junction_placement(m2, SC._Net(m2))
    assert not c.passed


# --- graphs -----------------------------------------------------------------------------

def test_lane_and_walkway_graphs_connected(small, small2):
    for b in (small, small2):
        c = {x.id: x for x in b.checks}
        assert c["lane_graph"].passed and c["walkway_graph"].passed
        m = b.model
        lanes = [x for x in m.lanes if x.kind == "lane"]
        assert lanes and all(x.successors for x in m.lanes)
        conn = {x.id for x in m.lanes if x.kind == "connector"}
        assert conn and all(set(x.successors) <= {y.id for y in m.lanes} for x in m.lanes)
        kinds = {w.kind for w in m.walkways}
        assert {"sidewalk", "crosswalk", "path"} <= kinds


def test_check_lane_graph_fails(small):
    m = small.model
    victim = next(x for x in m.lanes if x.kind == "connector")

    def fn(d):
        for x in d["lanes"]:
            if x["id"] == victim.successors[0]:
                x["successors"] = []
                x["adjacent_ids"] = []

    m2 = _mutate(m, fn)
    assert not SC.check_lane_graph(m2, SC._Net(m2)).passed


def test_check_walkway_graph_fails(small):
    m = small.model
    g = C._Geo(m)
    # a walkway joined to nothing, on a landmass with districts
    lm = next(x for x in m.landmasses if x.district_ids)
    p = G.from_model_poly(lm.polygon).representative_point()

    def fn(d):
        w = copy.deepcopy(d["walkways"][0])
        w["id"] = "wk999999"
        w["line"] = [[p.x + 0.37, p.y + 0.41, 0.0], [p.x + 3.37, p.y + 0.41, 0.0]]
        w["neighbors"] = []
        d["walkways"].append(w)

    m2 = _mutate(m, fn)
    assert not SC.check_walkway_graph(m2, SC._Net(m2), g).passed


# --- blocks, lots, open space ---------------------------------------------------------------

def test_every_lot_has_frontage(small, small2):
    for b in (small, small2):
        for lt in b.model.lots:
            front = sum(f.length_m for f in lt.frontage if f.road_class in SC.ACCESS)
            assert front >= 2.0, lt.id
            assert lt.district_id and lt.frontage_ids and lt.archetype
            assert lt.frontage[0].length_m == max(f.length_m for f in lt.frontage)


def test_check_lot_frontage_fails(small):
    m = small.model
    victim = m.lots[0].id

    def fn(d):
        for lt in d["lots"]:
            if lt["id"] == victim:
                lt["frontage"] = []
                lt["frontage_ids"] = []

    m2 = _mutate(m, fn)
    c = SC.check_lot_frontage(m2, SC._Net(m2))
    assert not c.passed and victim in c.failures[0]


def test_lot_sizes_by_archetype(small, small2):
    for b in (small, small2):
        st = b.stats["local"]["lot_area_m2_by_archetype"]
        for arch, r in st.items():
            lo, hi = ST.style_of(arch).lot_area
            assert r["median"] >= lo and r["median"] <= hi, (arch, r)
    # narrow shopfront lots in the old town, large lots in the corporate core and port
    a = small.stats["local"]["lot_area_m2_by_archetype"]
    assert a["old_town"]["median"] < a["corporate_core"]["median"] / 5
    assert a["old_town"]["median_frontage_m"] < 15.0


def test_check_lot_sizes_and_slivers_fail(small):
    m = small.model
    lt = next(x for x in m.lots if x.archetype == "old_town")
    big = G.to_model_poly(G.from_model_poly(lt.polygon).buffer(60.0, join_style="mitre"))
    thin = G.to_model_poly(shapely.box(0.0, 0.0, 40.0, 1.0))

    def fn(d):
        for x in d["lots"]:
            if x["id"] == lt.id:
                x["polygon"] = big
        d["lots"][-1]["polygon"] = thin

    m2 = _mutate(m, fn)
    n = SC._Net(m2)
    assert not SC.check_sizes(m2, n).passed
    assert not SC.check_slivers(m2, n).passed


def test_merged_groups_and_places(small2):
    m = small2.model
    names = {p.name for p in m.places}
    assert {"Lantern Plaza", "Night Lane"} <= names
    plaza = next(p for p in m.places if p.name == "Lantern Plaza")
    assert any(o.name == "Lantern Plaza" and o.kind == "plaza" for o in m.open_spaces)
    assert plaza.district_id == next(d.id for d in m.districts if d.name == "Lights")
    assert any(s.name == "Night Lane" for s in m.road_segments)
    groups = {lt.merged_group_id for lt in m.lots if lt.merged_group_id}
    assert groups  # transit hub and megablocks bring complexes by preset


def test_check_places_fails(small2):
    data = copy.deepcopy(SMALL2)
    data["districts"][3]["places"].append({"name": "Ghost Square", "kind": "plaza"})
    c = SC.check_places(validate_spec(data).filled, small2.model, SC._Net(small2.model))
    assert not c.passed and "Ghost Square" in c.failures[0]


def test_open_space_share_in_targets(small, small2):
    for b in (small, small2):
        for d in b.model.districts:
            share, _, _ = SC.open_shares(b.spec, b.model)[d.id]
            lo, hi = ST.style_of(d.archetype).open_share
            assert lo - 0.02 <= share <= hi + 0.02, (d.name, share)


def test_open_space_on_the_walkway_graph(small):
    m = small.model
    ends = {tuple(w.line[0][:2]) for w in m.walkways} | {tuple(w.line[-1][:2])
                                                       for w in m.walkways}
    parks = [o for o in m.open_spaces if o.kind in ("park", "plaza", "pocket_park")]
    reached = sum(1 for o in parks if any(
        G.from_model_poly(o.polygon).buffer(1.0).contains(Point(p)) for p in ends))
    assert reached >= 0.5 * len(parks)


# --- determinism ----------------------------------------------------------------------------

def test_scalar_dmath_matches_array():
    rng = np.random.default_rng(5)
    xs = np.concatenate([rng.uniform(-40, 40, 4000), [0.0, -0.0, M.PI, -M.HALF_PI, 1e4]])
    ys = rng.uniform(-40, 40, len(xs))
    s, c, a = M.sin(xs), M.cos(xs), M.atan2(ys, xs)
    for i in range(len(xs)):
        assert M.sin(float(xs[i])) == s[i] and M.cos(float(xs[i])) == c[i]
        assert M.atan2(float(ys[i]), float(xs[i])) == a[i]


def test_cross_exact_on_the_grid():
    p, t = ST._cross_exact((0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0))
    assert p == (5.0, 5.0) and t == 0.5
    p, _ = ST._cross_exact((0.0, 0.0), (3.0, 1.0), (1.0, -1.0), (1.0, 2.0))
    assert p == (1.0, 0.33)
    assert ST._cross_exact((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)) is None


def test_canonical_snapping():
    """In the M2 stages, snapped polygons start at their lowest vertex whatever the input
    order, and coordinates are rounded one by one."""
    a = shapely.Polygon([(1.004, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
    b = shapely.Polygon([(0.0, 1.0), (0.0, 0.0), (1.004, 0.0), (1.0, 1.0)])
    with G.canonical():
        qa, qb = G.qpoly(a), G.qpoly(b)
    assert qa.wkb == qb.wkb
    assert shapely.get_coordinates(qa).tolist()[0] == [0.0, 0.0]


def test_canonical_union_ignores_input_order():
    """Snap rounding is not associative, so a union of many pieces depends on the order they
    are merged in. GEOS's union_all takes that order from its STRtree, which sorts with the
    C++ standard library (tied envelopes come out differently on macOS and Linux): the M2
    union fixes the order itself, so a permuted input gives the same bytes."""
    rng = np.random.default_rng(5)
    pieces = []
    for k in range(60):
        x, y = rng.uniform(0.0, 300.0, 2)
        ang = rng.uniform(0.0, 180.0)
        pieces.append(shapely.affinity.rotate(
            shapely.box(x, y, x + rng.uniform(20.0, 90.0), y + rng.uniform(6.0, 14.0)), ang))
    with G.canonical():
        pieces = [G.qpoly(p) for p in pieces]
        ref = G.union(pieces).wkb
        for seed in range(4):
            perm = np.random.default_rng(seed).permutation(len(pieces)).tolist()
            assert G.union([pieces[i] for i in perm]).wkb == ref
    assert G.area(shapely.from_wkb(ref)) > 0


_ACTIVE = [False]


def _ulps(c: np.ndarray) -> np.ndarray:
    bits = np.ascontiguousarray(c, dtype=np.float64).view(np.uint64)
    h = (bits * np.uint64(0x9E3779B97F4A7C15)) >> np.uint64(59)
    return (h.astype(np.int64) % 9) - 4


def _perturb(c):
    c = np.asarray(c, dtype=np.float64)
    moved = c + _ulps(c) * np.spacing(np.abs(c))
    return np.where(np.abs(c * 1000.0 - np.rint(c * 1000.0)) < 1e-6, c, moved)


@pytest.fixture
def m2_noise(monkeypatch):
    """4-ULP noise on every coordinate and measure GEOS computes while the M2 stages run
    (grid values and fixed-precision overlays aside, as in test_determinism)."""
    geo = ["intersection", "difference", "union", "union_all", "symmetric_difference",
           "buffer", "make_valid", "centroid", "point_on_surface", "line_interpolate_point",
           "shortest_line", "offset_curve", "voronoi_polygons", "minimum_rotated_rectangle"]
    scal = ["area", "length", "distance", "line_locate_point", "hausdorff_distance"]

    def noisy_geom(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            out = fn(*a, **k)
            if not _ACTIVE[0] or k.get("grid_size"):
                return out
            return shapely.transform(out, _perturb)
        return w

    def noisy_scalar(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            out = fn(*a, **k)
            if not _ACTIVE[0]:
                return out
            r = _perturb(out)
            return float(r) if np.ndim(r) == 0 else r
        return w

    for name in geo:
        monkeypatch.setattr(shapely, name, noisy_geom(getattr(shapely, name)))
    for name in scal:
        monkeypatch.setattr(shapely, name, noisy_scalar(getattr(shapely, name)))
    real = LC.build_local
    enabled = [False]

    def noisy_local(*a, **k):
        _ACTIVE[0] = enabled[0]
        try:
            return real(*a, **k)
        finally:
            _ACTIVE[0] = False

    monkeypatch.setattr(LC, "build_local", noisy_local)
    yield enabled
    _ACTIVE[0] = False


def test_m2_stages_ignore_ulp_noise(m2_noise):
    """Greyhook built twice in one process, the second time with noise inside the street,
    junction and block stages: byte-identical models."""
    spec = ROOT / "docs" / "progress" / "M1a2" / "peninsula_city" / "city_spec.json"
    clean = build_city(load_spec(spec), workers=1).model.to_json()
    m2_noise[0] = True
    noisy = build_city(load_spec(spec), workers=1).model.to_json()
    assert hashlib.sha256(noisy.encode()).hexdigest() == \
        hashlib.sha256(clean.encode()).hexdigest()


def test_report_has_local_stats(small):
    st = small.stats["local"]
    for k in ("junctions", "junctions_by_type", "crosswalks", "lanes", "walkway_km", "blocks",
              "lots", "lot_area_m2_by_archetype", "open_share_by_district", "open_share"):
        assert k in st, k
    text = C.report_text(small.report())
    assert "lots by archetype" in text and "junctions by type" in text


def test_same_model_across_hash_seeds(tmp_path):
    """String hashing changes with every process (PYTHONHASHSEED): set order must never
    reach the model (junction classes once came out of a set)."""
    import os
    import subprocess
    import sys

    spec = tmp_path / "small.json"
    spec.write_text(json.dumps(SMALL))
    outs = []
    for seed in ("1", "777"):
        out = tmp_path / f"out{seed}"
        env = {**os.environ, "PYTHONHASHSEED": seed}
        proc = subprocess.run([sys.executable, "-m", "citygen", "build", str(spec), str(out)],
                              cwd=ROOT, env=env, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        outs.append((out / "city_model.json").read_bytes())
    assert outs[0] == outs[1]
