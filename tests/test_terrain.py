"""M13 terrain: the height field, water levels, grade lines, finished ground, retaining walls,
bored tunnels and terrain viaducts, seated buildings, the terrain checks (and that they fail on
broken copies), the hilly sample Cragmouth (golden hashes, model and blockout plan), that a
flat city carries no terrain at all, and (with M10) stable ids and district regeneration on a
hilly city."""

import copy
import hashlib
import json
import math
import re

import pytest

from citygen import terrain as TE
from citygen import terrain_checks as TGC
from citygen.build import build_city
from citygen.model import CityModel, RoadNode, RoadSegment
from citygen.validate import validate_spec
from conftest import GOLDEN, ROOT, SMALL, built_sample

CRAGMOUTH = ROOT / "cities" / "cragmouth" / "city_spec.json"

HILLY = {"hills": [{"name": "Core Hill", "at": "Core", "height_m": 35, "radius_m": 500},
                   {"at": "north_west", "height_m": 30, "radius_m": 600}],
         "ridges": [{"from": "Uptown", "to": "north", "height_m": 25, "width_m": 500}],
         "cliffs": [{"district": "Uptown", "height_m": 12, "width_m": 80,
                     "facing": ["north"]}],
         "flat": ["Harbor"], "relief_m": 3.0}


def hilly_data() -> dict:
    d = copy.deepcopy(SMALL)
    d["terrain"] = HILLY
    d["highways"] = {"elevated_share": 0.0}
    return d


@pytest.fixture(scope="module")
def hilly():
    res = validate_spec(hilly_data())
    assert res.ok, res.issues
    return build_city(res)


def test_flat_models_carry_no_terrain():
    """The M13 fields are left out of a flat city's JSON (byte-identical to M12's)."""
    seg = RoadSegment.model_validate({
        "id": "rs1", "start": "a", "end": "b", "road_class": "street", "lanes": 2,
        "width_m": 10.0, "centerline": [[0, 0], [10, 0]],
        "cross_section": {"total_width_m": 10.0, "lane_width_m": 3.0, "lanes_forward": 1,
                          "lanes_backward": 1}})
    data = json.loads(seg.model_dump_json())
    assert "ground" not in data
    assert "ground_m" not in json.loads(RoadNode(id="n1", position=(0, 0, 0)).model_dump_json())
    m = CityModel(name="x", seed=1, bounds=(0, 0, 1, 1))
    assert '"terrain"' not in m.to_json()


def test_spec_terrain_references_are_checked():
    d = copy.deepcopy(SMALL)
    d["terrain"] = {"hills": [{"at": "Nowhere", "height_m": 20}], "flat": ["Harbour"],
                    "cliffs": [{"district": "Core", "height_m": 10}]}
    res = validate_spec(d)
    paths = {i.path for i in res.issues if i.level == "error"}
    assert {"terrain.hills[0].at", "terrain.flat[0]"} <= paths
    assert not any(p.startswith("terrain.cliffs") for p in paths)


def test_lipschitz_fit_keeps_the_grade():
    """On a chain of stations 10 m apart (a 6% cap: 60 cm per edge), a 20 m cliff in the
    target: the fit stays within the cap everywhere, at most half the unclimbable step off."""
    n = 40
    adj = [[] for _ in range(n)]
    for i in range(n - 1):
        adj[i].append((i + 1, 60))
        adj[i + 1].append((i, 60))
    tgt = [0] * 20 + [2000] * 20
    hi = TE._lipschitz(n, adj, tgt)
    lo = TE._lipschitz(n, adj, [-v for v in tgt])
    e = [(h - lw) // 2 for h, lw in zip(hi, lo)]
    assert all(abs(a - b) <= 61 for a, b in zip(e, e[1:]))
    # the fit is the closest in the largest deviation: half of the step the cap cannot climb
    assert max(abs(a - b) for a, b in zip(e, tgt)) <= (2000 - 60) // 2 + 1
    # away from the cliff it meets the target
    assert e[0] == 0 or abs(e[0]) <= (2000 - 60) // 2 + 1


def test_hilly_city_passes_and_is_on_the_ground(hilly):
    b = hilly
    failed = [f for c in b.checks for f in c.failures]
    assert b.passed, failed[:10]
    ids = {c.id for c in b.checks}
    assert {"ground_grades", "cut_fill", "retaining_walls", "building_seats",
            "water_levels"} <= ids
    m = b.model
    t = m.terrain
    assert t is not None and t.ground and t.natural
    assert t.nx * t.cell_m >= m.bounds[2] - m.bounds[0]
    # every road on a grade line; every value on the 1 cm grid
    for s in m.road_segments:
        assert s.ground and abs(s.ground[0].s) < 1e-9
        assert all(round(p.z, 2) == p.z for p in s.ground)
    nodes = {n.id: n for n in m.road_nodes}
    for s in m.road_segments[:200]:
        assert abs(s.ground[0].z - nodes[s.start].ground_m) < 0.011
        assert abs(s.ground[-1].z - nodes[s.end].ground_m) < 0.011
    # buildings seated, the sea at 0
    assert all(b_.base_m is not None for b_ in m.buildings if b_.footprint is not None)
    lv = {w.water_id: w for w in t.water_levels}
    assert lv["sea"].level_m == 0.0
    assert float(TE.Field.from_rows(t, t.natural).arr.max()) > 30.0


def test_hilly_city_ground_rises_where_asked(hilly):
    m = hilly.model
    nat = TE.Field.from_rows(m.terrain, m.terrain.natural)
    core = TE.place(m, "Core")
    harbor = TE._district_poly(m, "Harbor").representative_point()
    assert nat.at(*core) > nat.at(harbor.x, harbor.y) + 20.0
    # the harbor levelled: one level all over it
    flat = next(f for f in m.terrain.stats["flat"] if f["name"] == "Harbor")
    poly = TE._district_poly(m, "Harbor")
    inner = poly.buffer(-30.0).representative_point()
    assert abs(nat.at(inner.x, inner.y) - flat["level_m"]) < 0.05


def test_terrain_checks_fail_on_broken_copies(hilly):
    m = hilly.model
    # a building lifted off its entrance ground
    b0 = next(b for b in m.buildings if b.base_m is not None and b.entrances)
    bad = m.model_copy(update={"buildings": [
        b.model_copy(update={"base_m": b.base_m + 9.0}) if b.id == b0.id else b
        for b in m.buildings]})
    assert not TGC.check_seats(bad).passed
    # a road grade line with a step
    s0 = next(s for s in m.road_segments if len(s.ground) > 3)
    g = [p.model_copy(update={"z": p.z + (6.0 if k == 2 else 0.0)})
         for k, p in enumerate(s0.ground)]
    bad = m.model_copy(update={"road_segments": [
        s.model_copy(update={"ground": g}) if s.id == s0.id else s for s in m.road_segments]})
    assert not TGC.check_grades(bad).passed
    # the retaining walls taken away (the steps they hold stay)
    if any(s.kind == "retaining_wall" and s.z1_m > 3.0 for s in m.structures):
        bad = m.model_copy(update={"structures": [s for s in m.structures
                                                  if s.kind != "retaining_wall"]})
        assert not TGC.check_walls(bad).passed
    # the sea off its level
    t = m.terrain
    wl = [w.model_copy(update={"level_m": 1.0}) if w.water_id == "sea" else w
          for w in t.water_levels]
    bad = m.model_copy(update={"terrain": t.model_copy(update={"water_levels": wl})})
    assert not TGC.check_water(bad).passed


def test_held_vertices_bound_the_fit():
    """M10: vertices held at a grade line bound the rest both ways, so the fit keeps the
    grade on the edges beside them even where the free target would pull it away."""
    n = 30
    adj = [[] for _ in range(n)]
    for i in range(n - 1):
        adj[i].append((i + 1, 60))
        adj[i + 1].append((i, 60))
    tgt = [0] * n
    frozen = frozenset(range(10))
    for v in frozen:
        tgt[v] = 1500          # held 15 m over a flat target
    hi = TE._lipschitz(n, adj, tgt, frozen)
    lo = TE._lipschitz(n, adj, [-v for v in tgt], frozen)
    big = 1 << 60
    up = TE._lipschitz(n, adj, [t if v in frozen else big for v, t in enumerate(tgt)])
    dn = TE._lipschitz(n, adj, [-t if v in frozen else big for v, t in enumerate(tgt)])
    hi = [max(h, -d) for h, d in zip(hi, dn)]
    lo = [max(lw, -u) for lw, u in zip(lo, up)]
    e = [(h - lw) // 2 for h, lw in zip(hi, lo)]
    assert e[:10] == [1500] * 10
    assert all(abs(a - b) <= 60 for a, b in zip(e, e[1:]))
    # down from the held stretch at the full grade, as far as it can come in 20 edges
    assert e[-1] == 1500 - 20 * 60


EXTRA_COUNTER = re.compile(r"(^|\.)(rw|tb|tv|wall|bore|viaduct|tvcol|slope)\d+(\.|$)")


def test_hilly_ids_come_from_what_and_where(hilly):
    """M10 on M13: retaining walls, terrain viaducts and their columns, bored tunnels and
    hillside greens are named from what and where they are; every reference (the terrain's
    water levels too) names an entity."""
    from test_edit import BUILD_ORDER

    from citygen import edit as E
    from citygen.model import COLLECTIONS

    d = hilly.model.model_dump(mode="json")
    ids = [e["id"] for c in COLLECTIONS for e in d.get(c, [])]
    assert len(ids) == len(set(ids))
    assert not [i for i in ids if BUILD_ORDER.search(i) or EXTRA_COUNTER.search(i)]
    walls = [e["id"] for e in d["structures"] if e["kind"] == "retaining_wall"]
    assert walls and all(re.fullmatch(r"(rs\.[ew]\d+[ns]\d+(\.\d+)?\.)?wall\.[ew]\d+[ns]\d+"
                                      r"(\.\d+)?", i) for i in walls)
    have = set(ids)
    missing = [(e["id"], r) for c in COLLECTIONS for e in d.get(c, []) for r in E._refs(c, e)
               if r not in have and not (c == "rivers" and r == "sea")]
    assert not missing, missing[:10]
    assert all(w.water_id in have or w.water_id == "sea"
               for w in hilly.model.terrain.water_levels)


def test_hilly_regeneration_holds_every_road(hilly):
    """M10 on M13: a district regenerated on a hilly city holds every road outside it (its
    grade line too: the new streets are fitted to the held ones), and every check passes."""
    from citygen import edit as E

    st = E.new_state(hilly_data(), hilly)
    out, _ = E.regenerate(st, hilly.model, "Old Quarter")
    info = out.stats["regenerated"]
    assert info["held_unchanged"] == info["held_segments"] > 0
    assert all(c.passed for c in out.checks), [(c.id, c.failures[:2]) for c in out.checks
                                              if not c.passed]
    from citygen import geom as G
    from citygen import streets as ST

    old = {s.id: s for s in hilly.model.road_segments}
    dd = next(x for x in hilly.model.districts if x.name == "Old Quarter")
    frame = ST.Frame(hilly.model, dd.name, dd.id, G.from_model_poly(dd.polygon), {})
    held = [s for s in old.values() if not frame.inside_row(s)]
    new = {s.id: s for s in out.model.road_segments}
    assert held and all(new.get(s.id) == s for s in held)
    assert out.model.terrain is not None and out.model.terrain.ground


def test_flat_city_terrain_checks_have_nothing_to_check():
    m = CityModel(name="x", seed=1, bounds=(0, 0, 1, 1))
    cs = TGC.run(None, m)
    assert [c.id for c in cs] == ["ground_grades", "cut_fill", "retaining_walls",
                                  "building_seats", "water_levels"]
    assert all(c.passed for c in cs)


def test_cragmouth_builds_on_its_ground():
    b, took, data = built_sample(CRAGMOUTH)
    failed = [f for c in b.checks for f in c.failures]
    assert b.passed, failed[:10]
    m = b.model
    st = b.stats["terrain"]
    assert st["bored_tunnels"] >= 1 and st["retaining_walls"] > 100
    assert st["slope_greens"] > 0
    names = [t.name for t in m.tunnels if t.kind == "bored"]
    assert all(names) and len(set(names)) == len(names)
    # the Crown plateau stands over the harbor; its tallest tower stands highest
    nat = TE.Field.from_rows(m.terrain, m.terrain.natural)
    crown = TE.place(m, "Crown Heights")
    harbor = TE.place(m, "Low Harbor")
    assert nat.at(*crown) > nat.at(*harbor) + 25.0
    top = max(m.buildings, key=lambda b_: (b_.base_m or 0.0) + b_.height_m)
    did = {d.id: d.name for d in m.districts}
    assert did.get(top.district_id) == "Crown Heights"


def test_cragmouth_golden_hashes():
    from citygen import blockout as BO

    golden = json.loads(GOLDEN.read_text())
    b, _, data = built_sample(CRAGMOUTH)
    assert hashlib.sha256(data).hexdigest() == golden["terrain_cities"]["cragmouth"]
    plan = BO.make_plan(b.model)
    assert BO.plan_sha256(plan) == golden["blockout_plans"]["cragmouth"]
    kinds = {p["k"] for o in plan["objects"] for p in o["parts"]}
    assert {"grid", "drape"} <= kinds
    ground = [o for o in plan["objects"] if o["category"] == "ground"]
    assert ground and all(o["parts"][0]["k"] == "grid" for o in ground)
    walls = [o for o in plan["objects"] if o["category"] == "retaining_wall"]
    assert walls


def test_road_grades_on_the_ground_within_class(hilly):
    for s in hilly.model.road_segments:
        if s.road_class == "footbridge":
            continue
        g = TE.MAX_GRADE.get(s.road_class, 0.12)
        if s.type.endswith(".ramp"):
            g = TE.MAX_GRADE["highway"]
        zp = [(p.s, p.z) for p in s.z_profile]
        st = [(p.s, p.z) for p in s.ground]
        for (s0, g0), (s1, g1) in zip(st, st[1:]):
            if s1 - s0 >= 0.5:
                dz = abs(g1 + TE.z_on(zp, s1) - g0 - TE.z_on(zp, s0))
                # (M18: as steep as its own z profile where that climbs more, as
                # `ground_grades`: a ramp at 8%, a levelled leg catching up)
                own = (abs(TE.z_on(zp, s1) - TE.z_on(zp, s0)) - 0.01) / (s1 - s0)
                assert (dz - 0.02) / (s1 - s0) <= max(g, own) + TGC.GRADE_TOL, (s.id, s0)
    assert math.isfinite(hilly.model.terrain.stats["max_m"])


def test_junction_legs_meet_at_one_height(hilly):
    """Every road of a junction of local roads holds its node's height through the junction
    (to its curb and sidewalk corners), so its legs meet at one height at the corners, not a
    step (a primary road keeps its grade through its junctions)."""
    from shapely.geometry import LineString, Point

    from citygen import geom as G

    segs = {s.id: s for s in hilly.model.road_segments}
    nodes = {n.id: n for n in hilly.model.road_nodes}
    at: dict = {}
    for s in segs.values():
        for n in (s.start, s.end):
            at.setdefault(n, []).append(s)
    n_legs = 0
    for j in hilly.model.junctions:
        nd = nodes.get(j.node_id)
        if nd is None or nd.ground_m is None or len(at.get(j.node_id, [])) < 3 or any(
                s.road_class in TE.PRIMARY or s.type.endswith(".ramp") for s in at[j.node_id]):
            continue
        poly = G.from_model_poly(j.polygon)
        for s in at[j.node_id]:
            if not s.ground:
                continue
            line = LineString(s.centerline)
            at_start = line.project(Point(nd.position[:2])) < line.length / 2
            # the run from the node to where the centerline leaves the junction
            inside = line.intersection(poly.buffer(-0.05))
            pieces = [g for g in getattr(inside, "geoms", [inside]) if g.length > 0 and
                      g.distance(Point(nd.position[:2])) < 0.05]
            if not pieces:
                continue
            # (at most 0.45 of the leg: a short leg between two junctions keeps the rest to
            # climb from one to the other)
            run = min(pieces[0].length, 0.45 * line.length)
            prof = [(p.s, p.z) for p in s.ground]
            for k in range(11):
                sv = run * k / 10 if at_start else line.length - run * k / 10
                assert abs(TE.z_on(prof, sv) - nd.ground_m) <= 0.011, (j.id, s.id, sv)
            n_legs += 1
    assert n_legs > 100
