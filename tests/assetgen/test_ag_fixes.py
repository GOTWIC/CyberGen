"""The fixes after AG10 (`docs/assetgen_milestones.md`, "Fixes after AG10") on made-up inputs:
a door moved off a wall too short for it takes the place of ground windows; a sidewalk corner
keeps no vertex the overlay's grid put inside an earlier corner; a quay's UVs stay in meters
round a sharp corner of its line; a sky station out of its building's reach is counted
apart."""

import inspect
import textwrap

from assetgen import asset_checks as AC
from assetgen import presets as PR
from assetgen.buildings import fronts as FR
from assetgen.buildings import genome as GN
from assetgen.buildings import shell as SH
from assetgen.streets import kit as K
from assetgen.streets import walks as W
from assetgen.streets import water as WA

from test_ag_shell import brief_of, mass


def _villa():
    """Vesper Bay Pinned's villa (`d03.lot.e1743n544.bld`): a pointed front, its main
    entrance on the 0.78 m tip, windows along every other wall."""
    ext = [[-4.0, -5.02], [-0.39, -8.63], [0.39, -8.63], [4.0, -5.02], [4.0, 8.63],
           [-4.0, 8.63]]
    br = brief_of([mass(ext, 0.0, 17.0, 5)], btype="building.villa", bid="d03.lot.e1743n544.bld",
                  classes={(0, 0, 0): "front", (0, 0, 1): "front", (0, 0, 2): "front",
                           (0, 0, 3): "open", (0, 0, 4): "park", (0, 0, 5): "open"})
    br["building"]["floor_grid"]["floor_height_m"] = 3.4
    br["building"]["style"] = {"era": "suburban_modern", "grime": 0.12, "neon": 0.08}
    br["spec"].update(era="suburban_modern", era_style=PR.ERA_PRESETS["suburban_modern"])
    br["entrances"] = [{"at": {"d": 0.0, "edge": 1, "mass": 0, "s": 0.39}, "kind": "main",
                        "position": [0.0, -8.63], "segment_id": None, "walkway_id": None}]
    return br


def test_a_moved_door_takes_the_place_of_ground_windows():
    br = _villa()
    gm = GN.make(br)
    sh = SH.build(br, gm)
    assert sh["checks"]["access"]["missing"] == 0
    (d,) = sh["doors"]
    assert d["moved"] and d["edge"] in (0, 2)
    # (with the old filter, which named the ground windows `window`, no door fitted)
    old = textwrap.dedent(inspect.getsource(FR.Band.rehome)).replace('"win"', '"window"')
    ns = {}
    exec(old, FR.__dict__, ns)
    keep = FR.Band.rehome
    FR.Band.rehome = ns["rehome"]
    try:
        assert SH.build(br, gm)["checks"]["access"]["missing"] == 1
    finally:
        FR.Band.rehome = keep


def test_a_corner_keeps_no_vertex_inside_an_earlier_one():
    """Nexus City's `jn.e383n933`: the overlay put the point where a corner leaves an earlier
    corner's edge 4.4 mm inside it."""
    earlier = [(424.83, 923.65), (423.96, 923.84), (423.84, 921.66)]
    ring = [(423.96, 923.84), (424.81, 923.65), (424.83, 923.65), (425.99, 925.99),
            (424.1, 926.3)]
    assert W._onto(ring, [earlier]) == [(423.96, 923.84), (424.83, 923.65), (425.99, 925.99),
                                        (424.1, 926.3)]
    assert W._onto(ring, []) == ring


def test_quay_uvs_stay_in_meters_round_a_sharp_corner():
    """A 15 m quay round a basin's corner with a 0.2 m jog in its line: u runs along each
    edge line's own length, so the paving meets the texel density's tolerance (three
    quarters of its texels per meter) over all but a sliver of its area."""
    line = [[0.0, 0.0], [60.0, 0.0], [60.2, 0.05], [60.2, 60.0]]
    inp = {"quay": {"id": "q", "line": line, "width_m": 15.0, "deck_z_m": 1.5,
                    "waterway_id": "w"},
           "side": 1, "ground": None, "water_z": -1.5,
           "style": {"archetype": "corporate_core"}, "origin": [30.0, 30.0]}
    out = WA.make_quay(inp)
    assert not any(K.check(out.mesh.slots).values())
    for name, sl in out.mesh.slots.items():
        if not name.startswith("paving"):
            continue
        low = area = 0.0
        for t in range(0, len(sl.idx), 3):
            a, b, c = (sl.pos[i] for i in sl.idx[t:t + 3])
            ua, ub, uc = (sl.uv[i] for i in sl.idx[t:t + 3])
            axyz = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2e6
            auv = abs((ub[0] - ua[0]) * (uc[1] - ua[1]) - (ub[1] - ua[1]) * (uc[0] - ua[0])) / 2
            area += axyz
            if axyz > 0 and (auv / axyz) ** 0.5 < 0.75:
                low += axyz
        assert area > 0 and low / area < 0.005


def _portal(**kw):
    return {"cut": False, "line_id": "tl.crown_line", "platform": False, "station": True,
            "station_id": "stn.the_stacks.2", "through": 0, **kw}


def test_a_station_out_of_reach_is_counted_apart():
    recs = {"b": {"roof_items": [], "green": [], "portals": [_portal(out_of_reach=True,
                                                                     gap_m=14.39)]}}
    rep = AC.roofs(recs, {"b": {}})
    assert rep["ok"] and rep["stations_out_of_reach"] == 1 and rep["portals_closed"] == 0
    rep = AC.roofs({"b": {"roof_items": [], "green": [], "portals": [_portal()]}}, {"b": {}})
    assert not rep["ok"] and rep["portals_closed"] == 1
