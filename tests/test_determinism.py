"""Cross-machine determinism of the district search.

Different machines round some floating point results differently in the last bits (ARM
compilers fuse a * b + c into one rounding inside GEOS and compiled contouring code, x86
baseline builds do not; libm and SIMD paths differ). The district stage must not let such
bits reach a decision. This test perturbs every float the geometry library returns while the
district search runs (new vertices, areas, lengths, distances, centroids, interpolated and
nearest points), and the raster field the marching squares sees, by up to 4 ULP, and asserts
the city model is byte-identical.

Coordinates on the 0.001 m grid are not moved: grid vertices that GEOS copies from its
(snapped) inputs, and points such as midpoints or crossings with axis-parallel edges that
land exactly between two grid values. GEOS computes overlay intersection points in
double-double precision, so every machine gets the correctly rounded value of such an exact
point and rounds it to the grid the same way; noise there would only test a tie no machine
can break differently.
"""

import copy
import functools
import hashlib
import json

import numpy as np
import pytest
import shapely

from citygen import build as B
from citygen import districts as D
from citygen import marching
from citygen import trace as T
from citygen.cli import main
from citygen.validate import load_spec, validate_spec

from conftest import ROOT, SMALL, write

PENINSULA = ROOT / "docs" / "progress" / "M1a2" / "peninsula_city" / "city_spec.json"
# shapely functions that compute new coordinates or measures, which a machine could round
# differently (geometry methods such as .buffer, .area, .centroid and
# shapely.ops.nearest_points call these). Every computed (off-grid) coordinate of their
# output moves.
NOISY_GEOMETRY = ["intersection", "difference", "union", "union_all", "symmetric_difference",
                  "buffer", "make_valid", "centroid", "point_on_surface",
                  "line_interpolate_point", "shortest_line", "offset_curve",
                  "voronoi_polygons"]
NOISY_SCALAR = ["area", "length", "distance", "line_locate_point", "hausdorff_distance"]
MAX_ULP = 4

_enabled = [False]  # noise during the district stage
_active = [False]   # inside the district stage now


def _ulps(c: np.ndarray) -> np.ndarray:
    """A pseudo-random whole number in [-4, 4] per value, from the value's own bits."""
    bits = np.ascontiguousarray(c, dtype=np.float64).view(np.uint64)
    h = (bits * np.uint64(0x9E3779B97F4A7C15)) >> np.uint64(59)
    return (h.astype(np.int64) % (2 * MAX_ULP + 1)) - MAX_ULP


def _perturb(c, keep_grid: bool = False):
    c = np.asarray(c, dtype=np.float64)
    moved = c + _ulps(c) * np.spacing(np.abs(c))
    if keep_grid:
        return np.where(np.abs(c * 1000.0 - np.rint(c * 1000.0)) < 1e-6, c, moved)
    return moved


def _noisy_geometry(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        out = fn(*args, **kwargs)
        if not _active[0] or kwargs.get("grid_size"):
            return out  # snap-rounded output is computed exactly the same everywhere
        return shapely.transform(out, lambda c: _perturb(c, keep_grid=True))
    return wrapped


def _noisy_scalar(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        out = fn(*args, **kwargs)
        if not _active[0]:
            return out
        res = _perturb(out)
        return float(res) if np.ndim(res) == 0 else res
    return wrapped


def _noisy_stage(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        _active[0] = _enabled[0]
        try:
            return fn(*args, **kwargs)
        finally:
            _active[0] = False
    return wrapped


@pytest.fixture
def noise(monkeypatch):
    for name in NOISY_GEOMETRY:
        monkeypatch.setattr(shapely, name, _noisy_geometry(getattr(shapely, name)))
    for name in NOISY_SCALAR:
        monkeypatch.setattr(shapely, name, _noisy_scalar(getattr(shapely, name)))
    rings = marching.rings

    def noisy_rings(xs, ys, z):
        return rings(xs, ys, _perturb(z) if _active[0] else z)

    monkeypatch.setattr(marching, "rings", noisy_rings)
    # The district search: positions, landmass assignment, partition, separation channels,
    # the land rebuilt around them, and the final clip.
    monkeypatch.setattr(D, "layout_districts", _noisy_stage(D.layout_districts))
    monkeypatch.setattr(D, "finalize", _noisy_stage(D.finalize))
    yield _enabled
    _enabled[0] = False


def _model(result):
    # One process: the noise is patched into this one.
    return (B.build_city(result, workers=1).model.to_json() + "\n").encode()


def test_perturb_moves_values():
    c = np.array([1234.56, -0.01, 5000.0, 3.0e-7])
    moved = _perturb(c)
    assert np.all(np.abs(moved - c) <= MAX_ULP * np.spacing(np.abs(c)))
    assert np.any(moved != c)


def test_district_search_ignores_ulp_noise(noise):
    clean = _model(load_spec(PENINSULA))
    D._GRIDS.clear()
    noise[0] = True
    noisy = _model(load_spec(PENINSULA))
    assert hashlib.sha256(noisy).hexdigest() == hashlib.sha256(clean).hexdigest()


def test_workers_do_not_change_the_model():
    """Variants and road attempts in worker processes: the same bytes as one process."""
    one = B.build_city(validate_spec(copy.deepcopy(SMALL)), workers=1)
    two = B.build_city(validate_spec(copy.deepcopy(SMALL)), workers=3)
    assert one.model.to_json() == two.model.to_json()
    assert one.variant == two.variant


def test_marching_squares_square():
    xs = np.arange(0.0, 50.0, 10.0)
    ys = np.arange(0.0, 50.0, 10.0)
    gx, gy = np.meshgrid(xs, ys)
    z = 15.0 - np.maximum(np.abs(gx - 20.0), np.abs(gy - 20.0))  # square |x|, |y| < 15
    poly = marching.filled(xs, ys, z)
    assert poly.geom_type == "Polygon"
    assert abs(poly.area - (900.0 - 4 * 12.5)) < 1e-9  # 30 m square, corners cut at 45 degrees
    assert poly.contains(shapely.Point(20.0, 20.0))


def test_marching_squares_hole_and_island():
    xs = np.arange(-60.0, 61.0, 2.0)
    gx, gy = np.meshgrid(xs, xs)
    r = np.sqrt(gx * gx + gy * gy)
    z = np.where(r < 50.0, 1.0, -1.0) * np.where((r > 20.0) | (r < 10.0), 1.0, -1.0)
    poly = marching.filled(xs, xs, z)
    assert poly.contains(shapely.Point(0.0, 0.0))       # island in the hole
    assert not poly.contains(shapely.Point(15.0, 0.0))  # the hole
    assert poly.contains(shapely.Point(35.0, 0.0))      # the ring
    assert not poly.contains(shapely.Point(55.0, 0.0))  # outside
    coords = shapely.get_coordinates(poly)
    assert np.all(np.rint(coords * 100) / 100 == coords)


def test_trace_written(tmp_path):
    spec = write(tmp_path, SMALL)
    out, tr = tmp_path / "out", tmp_path / "trace.json"
    assert main(["build", str(spec), str(out), "--trace", str(tr)]) == 0
    data = json.loads(tr.read_text())
    names = [e[0] for e in data["entries"]]
    for stage in ("v0/coast", "v0/rivers", "v0/landmasses", "v0/ideal_positions",
                  "v0/districts", "v0/separation_lines", "v0/districts_after_channels",
                  "v0/waterways"):
        assert stage in names, stage
    assert any(n.endswith("/megasites") for n in names)
    assert any(n.endswith("/roads0") for n in names)
    assert any("/it0/weights" in n for n in names)
    assert any("/contour" in n for n in names)
    assert any("/areas" in n for n in names)
    model = (out / "city_model.json").read_bytes()
    assert data["model_sha256"] == hashlib.sha256(model).hexdigest()
    assert main(["trace", "diff", str(tr), str(tr)]) == 0
    other = copy.deepcopy(data)
    other["entries"][5][1] = "0" * 64
    alt = tmp_path / "alt.json"
    alt.write_text(json.dumps(other))
    assert main(["trace", "diff", str(tr), str(alt)]) == 1
    assert not T.on()
