"""AT1: streets at night (docs/atmosgen_scope.md 13): lights by photometric class, the
junctions' mast arms and corner poles, the roads M6 gives no lamps, alleys, tunnels and
stations, and the lux check with occlusion (scope 8), on small synthetic builds."""

import json
import math

import numpy as np
import pytest

from atmosgen import lux as LX
from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P


def _sq(x0, y0, x1, y1):
    return {"exterior": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []}


def _street(sid, a, b, rc="street", width=12.0, sidewalk=3.0, median=0.0, start=None,
            end=None, **kw):
    return {"id": sid, "road_class": rc, "centerline": [a, b], "width_m": width,
            "start": start, "end": end,
            "cross_section": {"sidewalk_m": [sidewalk, sidewalk], "median_m": median}, **kw}


def _model() -> dict:
    """A street east to a junction at x 100 with a traffic signal, a highway with a median
    to the north, an alley to the south between two buildings, a pedestrian underpass, an
    elevated station; its walkways and lanes for the check."""
    jpoly = _sq(92.0, -8.0, 108.0, 8.0)
    m = {
        "name": "Night Test", "bounds": [-50.0, -150.0, 350.0, 250.0],
        "districts": [{"id": "d01", "name": "Core", "archetype": "corporate_core",
                       "params": {"wealth": 0.9, "danger": 0.1},
                       "polygon": _sq(-50.0, -150.0, 350.0, 250.0)}],
        "road_nodes": [{"id": "rn.e0n0", "position": [0.0, 0.0, 0.0]},
                       {"id": "rn.e100n0", "position": [100.0, 0.0, 0.0]},
                       {"id": "rn.e100s60", "position": [100.0, -60.0, 0.0]}],
        "road_segments": [
            _street("rs.e50n0", [0.0, 0.0], [92.0, 0.0], start="rn.e0n0", end="rn.e100n0"),
            _street("rs.e100s34", [100.0, -8.0], [100.0, -60.0], start="rn.e100n0",
                    end="rn.e100s60"),
            _street("rs.e150n200", [0.0, 200.0], [300.0, 200.0], rc="highway", width=30.0,
                    sidewalk=0.0, median=3.0),
            _street("rs.e40s100", [0.0, -100.0], [80.0, -100.0], rc="alley", width=4.0,
                    sidewalk=0.0)],
        "sidewalks": [
            {"id": "rs.e50n0.swl", "segment_id": "rs.e50n0", "side": "left",
             "line": [[0.0, 5.0], [92.0, 5.0]], "width_m": 3.0},
            {"id": "rs.e50n0.swr", "segment_id": "rs.e50n0", "side": "right",
             "line": [[0.0, -5.0], [92.0, -5.0]], "width_m": 3.0},
            {"id": "rs.e100s34.swl", "segment_id": "rs.e100s34", "side": "left",
             "line": [[105.0, -8.0], [105.0, -60.0]], "width_m": 3.0}],
        "junctions": [{"id": "jn.e100n0", "node_id": "rn.e100n0", "polygon": jpoly,
                       "signalized": True}],
        "crosswalks": [{"id": "cw.e92n0", "junction_id": "jn.e100n0",
                        "line": [[92.0, -6.0], [92.0, 6.0]], "width_m": 3.0}],
        "props": [
            {"id": "d01.prop.street_light.e30s5", "type": "prop.street_light",
             "attrs": {"sidewalk": "rs.e50n0.swr"}, "position": [30.0, -5.5, 0.0],
             "yaw_deg": 90.0, "scale": [1.0, 1.0, 1.0]},
            {"id": "d01.prop.traffic_signal.e93s7", "type": "prop.traffic_signal",
             "attrs": {"junction": "jn.e100n0"}, "position": [93.0, -7.0, 0.0],
             "yaw_deg": 0.0, "scale": [1.0, 1.0, 1.0]}],
        "buildings": [
            {"id": "d01.lot.e40s92.bld", "district_id": "d01", "footprint": _sq(0, -97, 80, -88),
             "masses": [{"footprint": _sq(0, -97, 80, -88), "z0_m": 0.0, "z1_m": 20.0}]},
            {"id": "d01.lot.e40s108.bld", "district_id": "d01",
             "footprint": _sq(0, -112, 80, -103),
             "masses": [{"footprint": _sq(0, -112, 80, -103), "z0_m": 0.0, "z1_m": 20.0}]}],
        "walkways": [
            {"id": "wk.e46s5", "kind": "sidewalk", "attrs": {"segment": "rs.e50n0"},
             "line": [[0.0, -5.0, 0.0], [92.0, -5.0, 0.0]], "width_m": 3.0},
            {"id": "wk.e92n0", "kind": "crosswalk", "attrs": {"junction": "jn.e100n0"},
             "line": [[92.0, -6.0, 0.0], [92.0, 6.0, 0.0]], "width_m": 3.0},
            {"id": "wk.e40s100", "kind": "alley", "attrs": {"segment": "rs.e40s100"},
             "line": [[0.0, -100.0, 0.0], [80.0, -100.0, 0.0]], "width_m": 2.0}],
        "lanes": [
            {"id": "rs.e50n0.f0", "segment_id": "rs.e50n0", "node_id": None,
             "centerline": [[0.0, -1.8, 0.0], [92.0, -1.8, 0.0]]},
            {"id": "jn.e100n0.c0", "segment_id": None, "node_id": "rn.e100n0",
             "centerline": [[92.0, -1.8, 0.0], [108.0, -1.8, 0.0]]},
            {"id": "jn.e100n0.c1", "segment_id": None, "node_id": "rn.e100n0",
             "centerline": [[101.8, -8.0, 0.0], [101.8, 8.0, 0.0]]},
            {"id": "rs.e150n200.f0", "segment_id": "rs.e150n200", "node_id": None,
             "centerline": [[0.0, 196.0, 0.0], [300.0, 196.0, 0.0]]}],
        "tunnels": [{"id": "tp.e200s40", "kind": "pedestrian",
                     "line": [[200.0, -60.0, -4.0], [200.0, -20.0, -4.0]], "width_m": 4.0,
                     "clear_m": 3.0}],
        "stations": [{"id": "stn.night", "kind": "elevated", "attrs": {"track_z_m": 12.0},
                      "position": [250.0, 100.0, 12.0], "footprint": _sq(220, 96, 280, 104)}],
    }
    return m


@pytest.fixture
def build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    return b


def _lights(build) -> dict:
    od = build / "atmos"
    plan = PM.AtmosPlan.model_validate_json((od / "atmos_plan.json").read_text())
    out = {}
    for t in plan.tiles:
        for L in json.loads((od / t.file).read_text())["lights"]:
            out[L["id"]] = L
    return out


def test_street_photometry_lights_between_the_lamps():
    """A cobra head's profile (Unreal's spot falloff) lights the carriageway 15 m along the
    street from it (half M6's staggered spacing) at a lux or more, and far less under it
    than AT0's 6000 cd did."""
    ph = P.PHOTOMETRY["cobra_head"]
    L = {"shape": "spot", "cd": ph["cd"], "cone": [ph["inner"], ph["outer"]],
         "reach_m": ph["reach_m"], "aim": [90.0, -90.0 + ph["tilt"]], "pos": [0.0, 0.0, 7.25]}
    under = LX.contribution(L, np.array([0.0]), np.array([1.8]), np.array([-7.25]))[0]
    along = LX.contribution(L, np.array([15.0]), np.array([1.8]), np.array([-7.25]))[0]
    assert 10.0 < under < 40.0                 # (AT0: 6000 cd, over 100 lx under it)
    assert along > 1.0
    # Unreal's spot falloff: t^2 between the cones
    ci, co = (math.cos(math.radians(a)) for a in (ph["inner"], ph["outer"]))
    g = math.radians(0.5 * (ph["inner"] + ph["outer"]))
    t = (math.cos(g) - co) / (ci - co)
    Ls = {**L, "aim": [0.0, -90.0], "cone": [ph["inner"], ph["outer"]]}
    h = 5.0
    r = h * math.tan(g)
    e = LX.contribution(Ls, np.array([r]), np.array([0.0]), np.array([-h]))[0]
    d = math.hypot(r, h)
    win = max(0.0, 1.0 - (d / ph["reach_m"]) ** 4) ** 2
    assert math.isclose(e, ph["cd"] * t * t * (h / d) / (d * d) * win, rel_tol=1e-9)


def test_plan_lights_junctions_roads_alleys_and_structures(build):
    rep = PL.build_plan(build)
    L = _lights(build)
    kinds = rep["counts"]
    # a mast arm over the junction from its signal: 7 m up, reaching in, aimed at its middle
    sig = L["d01.prop.traffic_signal.e93s7.light"]
    assert sig["kind"] == "signal" and sig["mount"] == "mast_arm" and sig["cls"] == "cobra_head"
    assert sig["pos"][0] > 93.0 and sig["pos"][1] > -7.0
    assert math.isclose(sig["pos"][2], P.SIGNAL_HEAD_Z_M - P.PHOTOMETRY["cobra_head"]["drop_m"])
    # the highway: twin arm columns in its median, 12 m up, a head over each carriageway
    hw = sorted(k for k in L if k.startswith("rs.e150n200."))
    assert hw and all(L[k]["mount"] == "pole" and L[k]["kind"] == "road" for k in hw)
    a, b = L[hw[0]], L[hw[1]]
    assert a["id"].endswith("a") and b["id"].endswith("b")
    assert a["pos"][1] > 200.0 > b["pos"][1]
    assert math.isclose(a["pos"][2], 12.0 - P.PHOTOMETRY["highway"]["drop_m"])
    # the alley: wall packs over it, from side to side
    al = [v for k, v in L.items() if k.startswith("rs.e40s100.")]
    assert len(al) >= 4 and {v["mount"] for v in al} == {"wall"}
    assert {v["pos"][1] > -100.0 for v in al} == {True, False}
    # the underpass's ceiling strip and the station's platform downlights
    up = [v for v in L.values() if v["kind"] == "underpass"]
    assert up and all(math.isclose(v["pos"][2], -1.0 - P.PHOTOMETRY["tunnel"]["drop_m"])
                      for v in up)
    st = [v for v in L.values() if v["kind"] == "station"]
    assert st and all(v["pos"][2] > 12.0 and v["on"] and not v["flicker"] for v in st)
    assert kinds["station"] == len(st)
    # every light names what it hangs on; the ones asked of stage 2 are counted
    assert rep["asked"] == sum(1 for v in L.values() if v["mount"] in PM.ASKED)
    assert rep["mounts"]["prop"] == 1                  # (the one street light)


def test_occlusion_against_masses():
    m = {"bounds": [0.0, 0.0, 40.0, 40.0],
         "buildings": [{"id": "b", "masses": [{"footprint": _sq(18.0, 0.0, 22.0, 40.0),
                                               "z0_m": 0.0, "z1_m": 10.0}]}]}
    occ = LX.Occluders(m)
    px = np.array([30.0, 30.0, 10.0])
    py = np.array([20.0, 20.0, 20.0])
    pz = np.array([0.0, 20.0, 0.0])
    vis = occ.visible(10.0, 20.0, 6.0, px, py, pz)
    # behind the wall on the ground: hidden; over it (the ray above 10 m) or on this side: seen
    assert vis.tolist() == [False, True, True]
    # a light 0.35 m off the wall sees the ground in front of it (its own facade skipped)
    assert occ.visible(17.65, 20.0, 4.0, np.array([12.0]), np.array([20.0]),
                       np.array([0.0])).tolist() == [True]


def test_lux_check_passes_and_fails_by_class(build):
    city = PL.City(build)
    S = LX.Samples(city)
    assert S.xyz.shape[1] == 3 and len(S.xyz) == len(S.cls)
    present = {LX.CLASSES[c] for c in set(S.cls.tolist())}
    assert {"sidewalk", "crosswalk", "carriageway", "alley"} <= present
    # the junction's lanes and crosswalk carry its id
    js = {S.junction_ids[j] for j in set(S.junction.tolist()) if j >= 0}
    assert js == {"jn.e100n0"}
    E = np.full(len(S.xyz), 20.0)
    assert LX.check(S, E)["ok"]
    dark = E.copy()
    dark[S.cls == LX.CLASSES.index("carriageway")] = 0.5
    res = LX.check(S, dark)
    assert not res["ok"] and any(f.startswith("carriageway") for f in res["failures"])
    # an alley may be dim, never dark
    dim = E.copy()
    al = S.cls == LX.CLASSES.index("alley")
    dim[al] = 2.5
    assert LX.check(S, dim)["ok"]
    dim[np.flatnonzero(al)[0]] = 0.0
    assert not LX.check(S, dim)["ok"]


def test_dark_junction_gets_corner_poles(build):
    """With the signal's mast arm gone the junction is dark: the plan stands corner poles at
    its sidewalks' and crosswalk's ends until its lanes and crosswalk read lit."""
    m = _model()
    m["props"] = [p for p in m["props"] if "traffic_signal" not in p["id"]]
    (build / "city_model.json").write_text(json.dumps(m), encoding="utf-8")
    rep = PL.build_plan(build)
    L = _lights(build)
    corners = [v for v in L.values() if v["kind"] == "corner"]
    c = rep["lux"]["corners"]
    assert corners and c["dark"] == 1 and c["poles"] == len(corners) <= P.CORNER_MAX
    assert all(v["owner_id"] == "jn.e100n0" and v["mount"] == "pole" for v in corners)
    assert c["lit"] == 1 and c["still_dark"] == 0
    j = rep["lux"]["junctions"]
    assert j["lanes"]["under_min"] <= P.UNDER_MIN_SHARE


def test_plan_records_its_check(build):
    rep = PL.build_plan(build)
    plan = json.loads((build / "atmos" / "atmos_plan.json").read_text())
    lux = plan["checks"]["lux"]
    assert lux["ok"] == rep["ok"] and set(lux["classes"]) <= set(LX.CLASSES)
    assert "lux check" in (build / "atmos" / "atmos_report.txt").read_text()
