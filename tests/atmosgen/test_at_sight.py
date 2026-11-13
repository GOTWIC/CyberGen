"""Visible lights (after AT4): the plan's sight raster (atmosgen/sight.py), the occluders the
runtime marches a walker's line of sight through when it picks the lights to keep live. The
runtime's own test (`FCityGenSight::Visible` in CityGenAtmosActor.cpp) is the same walk; the
Delta check of docs/progress/atmos_visible_lights runs it in Unreal."""

import json

import numpy as np

from atmosgen import lux as LX
from atmosgen import sight as SI


class _Occ:
    """A lux.Occluders stand-in: a 1 m raster over [0, 100] x [0, 100]."""

    def __init__(self):
        self.x0, self.y0, self.cell = 0.0, 0.0, 1.0
        self.top = np.full((100, 100), -np.inf, dtype=np.float32)
        self.bot = np.full((100, 100), np.inf, dtype=np.float32)

    def put(self, x0, y0, x1, y1, z0, z1):
        self.top[y0:y1, x0:x1] = z1
        self.bot[y0:y1, x0:x1] = z0


def _raster():
    o = _Occ()
    o.put(40, 40, 60, 60, -0.5, 30.0)       # a block 20 m square, 30 m tall
    o.put(10, 70, 30, 90, 9.0, 10.0)        # a deck slab, its underside at 9 m
    return SI.raster(o)


def test_raster_channels_and_north_row():
    r = _raster()
    rgb = r["rgb"]
    assert rgb.shape == (50, 50, 3) and r["cell_m"] == 2.0 and r["bounds"] == [0, 0, 100, 100]
    # row 0 the north edge: the block's cells (y 40 to 60) are rows 20 to 29
    assert (rgb[20:30, 20:30, 0] == 15).all() and (rgb[20:30, 20:30, 1] == 0).all()
    assert rgb[:20, :, 0].max() <= 5 and (rgb[30:, 20:30, 0] == 0).all()
    # the deck: its top in 2 m steps rounded down, its underside in 1 m steps rounded up
    assert (rgb[5:15, 5:15, 0] == 5).all() and (rgb[5:15, 5:15, 1] == 9).all()
    assert (rgb[..., 2] == 0).all()        # a flat city's ground


def test_a_cell_blocks_what_all_its_four_block():
    o = _Occ()
    o.put(41, 40, 60, 60, -0.5, 30.0)        # the block's west edge at x 41: half a 2 m cell
    r = SI.raster(o)
    assert (r["rgb"][20:30, 20, 0] == 0).all() and (r["rgb"][20:30, 21, 0] == 15).all()


def test_lines_of_sight():
    r = _raster()
    eye = (20.0, 50.0, 1.7)
    assert not SI.visible(r, eye, (80.0, 50.0, 5.0))       # through the block
    assert SI.visible(r, eye, (80.0, 50.0, 120.0))         # over it
    assert not SI.visible(r, eye, (80.0, 50.0, 60.0))      # (at 21 m over its near edge)
    assert SI.visible(r, eye, (80.0, 10.0, 5.0))           # past its corner
    assert SI.visible(r, (20.0, 60.0, 1.7), (20.0, 95.0, 4.0))   # under the deck
    assert not SI.visible(r, (20.0, 60.0, 1.7), (20.0, 80.0, 12.0))  # onto it from under
    # a light on the block's facade, stood 0.9 m off it, along the street beside it
    assert SI.visible(r, (35.0, 10.0, 1.7), (39.1, 55.0, 6.0))
    # an eye in the block's own cell (a doorway) still sees out of it
    assert SI.visible(r, (41.0, 50.0, 1.7), (10.0, 50.0, 5.0))


def test_runs_cover_the_raster():
    r = _raster()
    runs = SI.runs(r["rgb"])
    counts, values = runs[0::2], runs[1::2]
    assert sum(counts) == 50 * 50 and all(c > 0 for c in counts)
    flat = np.repeat(np.array(values, dtype=np.int64), counts)
    rgb = r["rgb"].reshape(-1, 3).astype(np.int64)
    assert (flat == rgb[:, 0] | (rgb[:, 1] << 8) | (rgb[:, 2] << 16)).all()


def test_raster_from_the_lux_occluders(tmp_path):
    """The lux check's occluders (masses taken 0.5 m in, deck slabs) to the sight raster;
    the file and its record written only when its bytes change."""
    sq = lambda x0, y0, x1, y1: {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],  # noqa
                                 "holes": []}
    m = {"bounds": [0.0, 0.0, 100.0, 100.0],
         "buildings": [{"id": "b1", "base_m": 0.0, "footprint": sq(40, 40, 60, 60),
                        "masses": [{"footprint": sq(40, 40, 60, 60), "z0_m": 0.0,
                                    "z1_m": 30.0}]}]}
    occ = LX.Occluders(m)
    r = SI.raster(occ)
    rec = SI.write(r, tmp_path)
    assert rec["px"] == [50, 50] and 0.02 < rec["occupied"] <= 0.04
    f = tmp_path / SI.FILE
    t = f.stat().st_mtime_ns
    assert SI.write(SI.raster(occ), tmp_path) == rec and f.stat().st_mtime_ns == t
    back = SI.load(f, rec)
    assert (back["rgb"] == r["rgb"]).all()
    assert not SI.visible(back, (20.0, 50.0, 1.7), (80.0, 50.0, 5.0))
    assert json.loads(json.dumps(rec)) == rec
