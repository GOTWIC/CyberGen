"""M16: water and ground detail; the stage on the small city, each M16 check with a failing
case, the bed at a point, a city without water or open land, the blockout's beds, banks,
cover and swim volumes, and a district regeneration's locality."""

import copy
import functools

import shapely
from shapely.geometry import LineString

from citygen import blockout as BO
from citygen import build as B
from citygen import cover as CV
from citygen import edit as E
from citygen import geom as G
from citygen import unreal as U
from citygen import water as WA
from citygen import water_checks as WC
from citygen.model import BANK_KINDS, COVER_KINDS, CityModel
from citygen.validate import validate_spec

from conftest import SMALL

M16_CHECKS = {"water_beds", "water_banks", "ground_cover"}


@functools.lru_cache(maxsize=1)
def city():
    result = validate_spec(copy.deepcopy(SMALL))
    assert result.ok, [str(i) for i in result.errors]
    return B.build_city(result)


def _check(fn, m) -> list:
    with G.canonical():
        return fn(m).failures


def test_city_passes_with_water_and_ground():
    b = city()
    failed = [(c.id, c.failures[:3]) for c in b.checks if not c.passed]
    assert not failed, failed
    assert M16_CHECKS <= {c.id for c in b.checks}
    assert b.stats["water"]["banks"] and b.stats["water"]["cover"]


def test_every_water_body_has_its_data():
    m = city().model
    flat = m.terrain is None
    for b in WA.bodies(m):
        e = b.ent
        assert e.depth_m is not None and e.bed is not None and e.flow is not None, b.id
        assert 0 < e.depth_m <= WA.max_depth(b.cls, flat) + 1e-9, b.id
        if b.kind in ("river", "delta_branch", "separation", "sea_channel"):
            assert e.bed.profile == "channel" and e.bed.along
            assert e.flow.kind in ("downstream", "tidal") and len(e.flow.line) >= 2
        if b.kind in ("basin", "marina", "ornamental"):
            assert e.flow.kind == "still" and e.flow.speed_m_s == 0.0
    sea = m.seas[0]
    assert sea.exposure and {x.kind for x in sea.exposure} <= {"open", "sheltered", "harbor"}
    assert sea.bed.surface_m == -WA.FREEBOARD_M


def test_rivers_flow_to_their_mouth():
    m = city().model
    for r in m.rivers:
        end = shapely.geometry.Point(r.flow.line[-1])
        start = shapely.geometry.Point(r.flow.line[0])
        if r.flows_into == "sea":
            sea = G.union([G.from_model_poly(p) for p in m.seas[0].polygons])
            assert sea.distance(end) <= sea.distance(start)


def test_banks_are_typed_and_cover_the_edges():
    m = city().model
    assert m.banks and {k.kind for k in m.banks} <= set(BANK_KINDS)
    for k in m.banks:
        assert k.type == f"bank.{k.kind}"
        assert (k.height_m is None) == (k.kind == "quay")
        assert k.id.startswith(k.water_id + ".bank.")
    quays = {q.id for q in m.quays}
    assert {k.quay_id for k in m.banks if k.kind == "quay"} <= quays
    assert not _check(WC.check_banks, m)


def test_bank_check_fails_on_a_gap_and_an_overlap():
    m = city().model
    gap = m.model_copy(update={"banks": m.banks[1:]})
    assert _check(WC.check_banks, gap)
    dup = m.model_copy(update={"banks": m.banks + [m.banks[0].model_copy(
        update={"id": m.banks[0].id + ".dup"})]})
    assert any("overlap" in f or "long" in f for f in _check(WC.check_banks, dup))
    k = next(k for k in m.banks if k.kind != "quay")
    bad = m.model_copy(update={"banks": [x.model_copy(update={"height_m": None})
                                         if x.id == k.id else x for x in m.banks]})
    assert any("no height" in f for f in _check(WC.check_banks, bad))


def test_bed_check_fails_on_a_bed_too_deep():
    m = city().model
    r = m.rivers[0]
    deep = m.model_copy(update={"rivers": [r.model_copy(update={"depth_m": 30.0})]})
    assert any("deeper" in f for f in _check(WC.check_beds, deep))
    still = m.model_copy(update={"seas": [m.seas[0].model_copy(update={"exposure": []})]})
    assert any("exposure" in f for f in _check(WC.check_beds, still))


def test_bed_depth_follows_the_profile():
    m = city().model
    beds = WA.Beds(m)
    r = m.rivers[0]
    pts = [tuple(p) for p in r.centerline]
    mid = pts[len(pts) // 2]
    d_mid = beds.depth(r.id, *mid)
    assert 0 < d_mid <= r.depth_m + 1e-9
    # toward a bank the bed rises
    k = min((k for k in m.banks if k.water_id == r.id),
            key=lambda k: LineString(k.line).distance(shapely.geometry.Point(mid)))
    near = LineString(k.line).interpolate(LineString(k.line).project(
        shapely.geometry.Point(mid)))
    t = 0.85
    x, y = mid[0] + (near.x - mid[0]) * t, mid[1] + (near.y - mid[1]) * t
    assert beds.depth(r.id, x, y) < d_mid
    # the vectorized and the single evaluation agree
    assert abs(beds.depth_many(r.id, [x], [y])[0] - beds.depth(r.id, x, y)) < 1e-9
    assert beds.bed_z(r.id, *mid) == -WA.FREEBOARD_M - d_mid


def test_cover_tiles_the_open_land():
    m = city().model
    assert m.ground_cover and {g.kind for g in m.ground_cover} <= set(COVER_KINDS)
    for g in m.ground_cover:
        assert g.type == f"ground_cover.{g.kind}"
        assert 0 <= g.maintenance <= 1 and 0 <= g.wear <= 1 and 0 <= g.shade <= 1
        assert g.area_m2 > 0
    kinds = {g.kind for g in m.ground_cover}
    assert {"paving", "park_lawn", "mown_lawn"} & kinds
    assert any(g.desire_lines for g in m.ground_cover)
    assert not _check(WC.check_cover, m)


def test_cover_check_fails_on_overlaps_and_gaps():
    m = city().model
    g = max(m.ground_cover, key=lambda g: g.area_m2)
    dup = m.model_copy(update={"ground_cover": m.ground_cover + [g.model_copy(
        update={"id": g.id + ".dup"})]})
    assert any("overlap" in f for f in _check(WC.check_cover, dup))
    gap = m.model_copy(update={"ground_cover": [x for x in m.ground_cover if x.id != g.id]})
    assert any("uncovered" in f for f in _check(WC.check_cover, gap))
    b = next(b for b in m.buildings if b.footprint is not None and not b.level)
    over = m.model_copy(update={"ground_cover": m.ground_cover + [g.model_copy(
        update={"id": g.id + ".over", "polygon": b.footprint})]})
    assert any("building" in f for f in _check(WC.check_cover, over))


def test_the_stage_is_a_function_of_the_city():
    """Run again on the finished city, the stage gives the same rows (the build's own run
    saw the same city, its props and plants named later only)."""
    m = city().model
    again, rows = B.water_ground(m)
    assert again.to_json() == m.to_json()


def test_a_city_without_water_or_open_land_is_unchanged():
    m = city().model
    bare = m.model_copy(update={
        "seas": [], "rivers": [], "channels": [], "waterways": [], "quays": [], "banks": [],
        "ground_cover": [], "lots": [], "open_spaces": [], "megasites": [], "districts": [],
        "land": []})
    out, rows = B.water_ground(CityModel.model_validate(bare.model_dump(mode="json")))
    assert not rows
    assert out.to_json() == CityModel.model_validate(bare.model_dump(mode="json")).to_json()
    assert '"banks"' not in out.to_json() and '"ground_cover"' not in out.to_json()


def test_blockout_draws_beds_banks_cover_and_swim_volumes():
    m = city().model
    plan = BO.make_plan(m)
    cats = {o["category"] for o in plan["objects"]}
    assert "bed" in cats
    assert {f"bank_{k.kind}" for k in m.banks} <= cats
    assert {f"cover_{g.kind}" for g in m.ground_cover} <= cats
    # the open spaces at the ground are drawn as their cover
    assert not any(c.startswith("open_") for c in cats if c != "open_podium_roof")
    water = [o for o in plan["objects"] if o["category"] == "water"]
    assert water and all(p["z"] == -WA.FREEBOARD_M for o in water for p in o["parts"])
    swim = plan["swim"]
    assert swim and {s["water_id"] for s in swim} == {b.id for b in WA.bodies(m)}
    for s in swim:
        x0, y0, x1, y1 = s["box"]
        assert x1 > x0 and y1 > y0 and s["z"][1] == -WA.FREEBOARD_M and s["z"][0] < s["z"][1]


def test_unreal_manifest_has_the_swim_volumes(tmp_path):
    import json

    m = city().model
    plan = BO.make_plan(m)
    (tmp_path / "blockout_plan.json").write_text(BO.plan_json(plan), encoding="utf-8")
    man, _, _ = U.build_manifest(tmp_path, assets=False)
    assert len(man["swim"]) == len(plan["swim"]) == man["counts"]["swim_volumes"]
    hashes = U.actor_hashes(man)
    assert all(s["key"] in hashes for s in man["swim"])
    assert {f"cover_{g.kind}" for g in m.ground_cover} <= set(man["materials"])
    # an import over the same manifest changes nothing
    ch = U.manifest_changes(man, json.loads(json.dumps(man)))
    assert not any(ch.values())


def test_regeneration_keeps_water_and_ground_outside_the_district():
    b = city()
    data = copy.deepcopy(SMALL)
    st = E.new_state(data, b)
    r, rec = E.regenerate(st, b.model, "Old Quarter")
    loc = next(c for c in r.checks if c.id == "regen_locality")
    assert loc.passed, loc.failures
    failed = [(c.id, c.failures[:2]) for c in r.checks if not c.passed]
    assert not failed, failed
    did = next(d.id for d in b.model.districts if d.name == "Old Quarter")
    # the district's own cover is new, nearly all of the rest far from it as it was (what
    # changes there follows a change under it that the splice made, a crowd density say)
    old = {g.id: g for g in b.model.ground_cover}
    new = {g.id: g for g in r.model.ground_cover}
    poly = G.from_model_poly(next(d for d in b.model.districts if d.id == did).polygon)
    far = [i for i, g in old.items() if g.district_id != did and
           G.from_model_poly(g.polygon).distance(poly) > WC.SEAM_M]
    kept = [i for i in far if new.get(i) == old[i]]
    assert far and len(kept) >= 0.95 * len(far)
    # a change with nothing under it changed fails the check (the piece farthest away)
    g = old[max(kept, key=lambda i: (G.from_model_poly(old[i].polygon).distance(poly), i))]
    moved = r.model.model_copy(update={"ground_cover": [
        x.model_copy(update={"wear": round(1.0 - x.wear, 2)}) if x.id == g.id else x
        for x in r.model.ground_cover]})
    with G.canonical():
        assert not WC.check_locality(b.model, moved, did, poly).passed


def test_cover_pieces_keep_to_their_district():
    m = city().model
    P = G.from_model_poly
    dpoly = {d.id: G.qpoly(P(d.polygon).buffer(0.05)) for d in m.districts}
    for g in m.ground_cover:
        if g.district_id is not None:
            assert dpoly[g.district_id].covers(P(g.polygon)), g.id
    assert CV.SLIVER_M > 0
