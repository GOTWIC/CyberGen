"""AT7: the far city (atmosgen/far.py, scope 6.6): every light the far view sees as cards past
the live set (a glow at its lens, a pool on the surface it lights, a wash on the facade it
floods), their check and preview, and the budget table across plans (atmosgen/budgets.py),
on test_at_plan's small build."""

import json
import math

import numpy as np
import pytest

from atmosgen import budgets as BG
from atmosgen import far as FA
from atmosgen import plan as PL
from atmosgen import planmodel as PM
from atmosgen import presets as P

from test_at_plan import _model    # (pytest puts this folder on the path: no package)


@pytest.fixture
def build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    (b / "city_model.json").write_text(json.dumps(_model()), encoding="utf-8")
    return b


def _cards(od, plan):
    out = {}
    for t in plan.far.tiles:
        doc = PM.TileFar.model_validate_json((od / t["file"]).read_text())
        assert all(c.tile == t["tile"] for c in doc.cards) and len(doc.cards) == t["count"]
        out.update({c.id: c for c in doc.cards})
    return out


def test_far_cards_of_the_plan(build):
    rep = PL.build_plan(build)
    od = build / "atmos"
    plan = PM.AtmosPlan.model_validate_json((od / "atmos_plan.json").read_text())
    cards = _cards(od, plan)
    assert plan.far.counts["all"] == len(cards) and rep["far"]["ok"]
    lights = {}
    for t in plan.tiles:
        lights.update({L.id: L for L in PM.TileLights.model_validate_json(
            (od / t.file).read_text()).lights})
    # a cobra head: a glow at its lens (a share of its intensity) and a pool on the street
    # under it, moved along its aim by its tilt, lit as it lights it
    lid = "d01.prop.street_light.e10s5.light"
    L = lights[lid]
    g, p = cards[f"{lid}.far.glow"], cards[f"{lid}.far.pool"]
    assert g.pos == L.pos and math.isclose(g.value, P.FAR["cobra_head"]["glow"] * L.cd)
    assert g.tier == "mid" and g.schedule == L.schedule and g.color == L.color
    h = L.pos[2]                                  # (a flat city: the ground at 0)
    tilt = 90.0 + L.aim[1]
    assert math.isclose(p.h_m, h, abs_tol=1e-3)
    assert math.isclose(p.pos[1], L.pos[1] + h * math.tan(math.radians(tilt)), abs_tol=1e-3)
    assert math.isclose(p.pos[2], P.FAR_POOL_UP_M, abs_tol=1e-3)
    e0 = L.cd * math.cos(math.radians(tilt)) ** 3 / h ** 2
    assert math.isclose(p.value, e0 * P.FAR_ALBEDO["pool"] / math.pi, rel_tol=1e-3)
    assert math.isclose(p.size_m, min(L.reach_m, h * math.tan(math.radians(P.FAR_POOL_DEG))),
                        abs_tol=1e-3)
    # a wall pack and a post top: their pools straight under (a point) or along the wall's
    # normal; a sign, a shopfront's spill or a shop sign none (their faces are emissive)
    assert {c.light_id for c in cards.values()} == {
        "d01.prop.street_light.e10s5.light", "d02.prop.street_light.e300n5.light",
        "d02.prop.wall_light.e310n12.light"} - {i for i, Lx in lights.items() if not Lx.on}
    post = "d02.prop.street_light.e300n5.light"
    if lights[post].on:
        pp = cards[f"{post}.far.pool"]
        assert pp.pos[:2] == lights[post].pos[:2]
    # every card's hash is its record's
    for c in cards.values():
        rec = json.loads(c.model_dump_json(exclude_none=True))
        hh = rec.pop("hash")
        assert hh == PL.sha(PL.dumps(rec))[:16]
    # the far check in the plan, the report and its text
    assert plan.checks["far"]["ok"] and "far check: PASS" in \
        (od / "atmos_report.txt").read_text()


def test_far_unchanged_writes_nothing(build):
    PL.build_plan(build)
    rep = PL.build_plan(build)
    assert rep["wrote"] == [] and (build / "atmos" / "far").is_dir()


def _light(**kw):
    rec = {"id": "b1.crown0", "kind": "flood", "cls": "crown_flood", "shape": "spot",
           "tier": "high", "tile": "t+00+00", "pos": [10.0, 10.0, 80.0], "aim": [0.0, 70.0],
           "cd": 0.0, "color": [1.0, 0.8, 0.6], "reach_m": 40.0, "cone": [12.0, 20.0],
           "schedule": "late", "on": True, "district_id": "d01"}
    rec.update(kw)
    return rec


def test_a_flood_washes_its_facade():
    """A crown flood 4 m off its facade, aimed up into the crown: its wash a flat card on the
    facade where the aim meets it, facing back toward the flood, the class's illuminance as
    luminance, as tall as the lit zone its reach gives."""
    ph = P.PHOTOMETRY["crown_flood"]
    dh, dz = 4.0, 20.0
    d = math.hypot(dh, dz)
    cd = ph["lux"] * d ** 3 / dh                  # (plan._flood's)
    reach = 1.15 * math.hypot(dh + 1.0, 30.0) + 2.0
    L = _light(cd=cd, reach_m=reach, aim=[0.0, math.degrees(math.atan2(dz, dh))])
    fa = FA.Far([L], None, lambda x, y: 0.0)
    fa.make()
    (w,) = fa.cards
    assert w["type"] == "wash" and w["tier"] == "high" and abs(w["yaw"]) == 180.0
    assert math.isclose(w["value"], ph["lux"] * P.FAR_ALBEDO["wash"] / math.pi, rel_tol=1e-3)
    # on the facade (4 m east of the flood), stood off it toward the flood
    assert math.isclose(w["pos"][0], 10.0 + dh - P.FAR_WASH_OUT_M, abs_tol=0.01)
    # the lit zone from a meter over the light to 30 m over it: its middle and half height
    assert math.isclose(w["h_m"], (30.0 - 1.0) / 2.0, abs_tol=0.01)
    assert math.isclose(w["pos"][2], 80.0 + 1.0 + w["h_m"], abs_tol=0.01)


def test_aviation_glows_blink_and_broken_lights_have_none():
    av = _light(id="b1.av0", kind="aviation", cls="aviation", shape="point", tier="near",
                aim=[0.0, -90.0], cd=300.0, color=[1.0, 0.05, 0.02], reach_m=14.0,
                anim={"mode": "blink", "period_s": 1.5, "amount": 0.3, "phase": 0.25},
                source_m=0.15)
    broken = _light(id="b1.av1", kind="aviation", cls="aviation", shape="point",
                    tier="near", aim=[0.0, -90.0], cd=300.0, reach_m=14.0, on=False)
    fa = FA.Far([av, broken], None, lambda x, y: 0.0)
    fa.make()
    (g,) = fa.cards
    assert g["type"] == "glow" and g["tier"] == "fixture" and g["value"] == 300.0
    assert g["anim"]["mode"] == "blink" and g["size_m"] == P.FAR_GLOW_MIN_M
    ck = fa.check()
    assert ck["ok"] and ck["skipped"] == {"aviation: broken": 1}


def test_a_pool_lands_on_the_deck_under_it():
    """A lamp on a raised road: its pool on the road's deck (the walkway and lane points
    under it), not the ground under the viaduct."""
    from atmosgen.lux import Points
    pts = Points(np.array([[0.0, 0.0, 9.0], [2.0, 0.0, 9.0], [0.0, 1.0, 0.0]]))
    L = _light(id="r.l", kind="road", cls="highway", pos=[0.0, 0.0, 21.0], aim=[0.0, -90.0],
               cd=2600.0, reach_m=45.0, tier="mid", schedule="dusk_dawn")
    fa = FA.Far([L], pts, lambda x, y: 0.0)
    fa.make()
    pool = [c for c in fa.cards if c["type"] == "pool"][0]
    assert math.isclose(pool["h_m"], 12.0) and math.isclose(pool["pos"][2],
                                                           9.0 + P.FAR_POOL_UP_M)
    # a lamp under 1.5 m over its surface: no pool, said why
    low = _light(id="r.low", kind="road", cls="highway", pos=[0.0, 0.0, 10.0],
                 aim=[0.0, -90.0], cd=2600.0, reach_m=45.0, tier="mid")
    fb = FA.Far([low], pts, lambda x, y: 0.0)
    fb.make()
    assert [c["type"] for c in fb.cards] == ["glow"] and fb.check()["ok"]


def test_the_check_fails_a_tile_over_budget(monkeypatch):
    ls = [_light(id=f"a{k}", kind="aviation", cls="aviation", shape="point", tier="near",
                 pos=[float(k % 50), float(k // 50), 30.0], aim=[0.0, -90.0], cd=300.0,
                 reach_m=14.0) for k in range(120)]
    fa = FA.Far(ls, None, lambda x, y: 0.0)
    fa.make()
    monkeypatch.setitem(P.FAR_BUDGETS, "cards_per_tile", 100)
    ck = fa.check()
    assert not ck["ok"] and ck["over_budget_tiles"] == ["t+00+00"]


def test_preview_and_renders(build):
    PL.build_plan(build)
    od = build / "atmos"
    plan = json.loads((od / "atmos_plan.json").read_text())
    model = json.loads((build / "city_model.json").read_text())
    model["bounds"] = [-50.0, -50.0, 350.0, 350.0]
    out = FA.preview(od, plan, model)
    assert (od / FA.FILE).is_file() and out["cards"] == plan["far"]["counts"]["all"]
    cards = FA._cards(od, plan)
    top = FA.render_top(cards, model["bounds"], 2.0, plan["schedules"], 23.0)
    assert top.max() > 0.0 and np.isfinite(top).all()
    # a glow seen from afar holds its intensity: the image's sum over its pixels (luminance
    # times each pixel's area there) is its intensity, whatever its size on screen
    c = {"type": "glow", "pos": [0.0, 1000.0, 0.0], "value": 100.0, "size_m": 0.5,
         "color": [1.0, 1.0, 1.0], "schedule": "x"}
    img = FA.render_view([c], (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), {"x": [1.0] * 24}, 23.0,
                         w=400, h=300, fov_deg=60.0, min_d=10.0)
    fl = 200.0 / math.tan(math.radians(30.0))
    a_px = (1000.0 / fl) ** 2
    assert math.isclose(img[..., 0].sum() * a_px, 100.0, rel_tol=0.05)


def test_budgets_table(build, tmp_path):
    PL.build_plan(build)
    rep = BG.write([build / "atmos"], tmp_path / "b")
    (r,) = rep["rows"]
    assert r["city"] == "Test Bay" and all(r["checks"].values()) and r["post"]
    assert r["per_tile"]["lights"][1] == P.BUDGETS["lights_per_cell"]
    assert r["near_view"]["mid"]["cap"] == 512 and r["near_view"]["mid"]["max"] >= 1
    assert "| Test Bay |" in (tmp_path / "b" / "budgets.md").read_text()


def test_disc_counts_count_within_the_range():
    xy = np.array([[0.0, 0.0], [100.0, 0.0], [400.0, 0.0]])
    c = BG._disc_counts(xy, -500.0, -500.0, 40, 40, 300.0)
    j = i = int(500.0 / BG.GRID_M)
    assert c[j, i] == 2                          # (from the origin's cell: 0 and 100 m)
