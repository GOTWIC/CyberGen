"""AG10, layered districts (scope 14.11): M14's decks as street pieces (a slab per deck and
tile, its columns, the light wells' stairs and elevators, each replacing its blockout
object), the deck's streets lying on the slab and its ramps solid with their walkways, the
buildings on, under and beside a slab kept to their side of it (`asset_decks`), and a city
without decks untouched (no deck record in a brief, no deck piece). On the small test city
with a deck over Core, as `tests/test_decks.py` builds it."""

import json

from assetgen.brief import load_model
from assetgen.buildings import decks as BD
from assetgen.buildings import genome as GN
from assetgen.buildings import shell as SH
from assetgen.buildings import envelope as EN
from assetgen.streets import build as SB
from assetgen.streets import decks as SD
from assetgen.streets import roads as RD
from assetgen.streets.ctx import Ctx

from agtools import deck_build, small_build

_DONE: dict = {}


def _deck_city():
    if "city" not in _DONE:
        base = deck_build()
        model, sha, bdir = load_model(base)
        _DONE["city"] = (base, model, sha)
    return _DONE["city"]


def _streets():
    if "streets" not in _DONE:
        base, model, sha = _deck_city()
        _DONE["streets"] = SB.build(model, sha, base / "assets", None, workers=2)
    return _DONE["streets"]


def _manifest() -> dict:
    _streets()
    base = _deck_city()[0]
    return json.loads((base / "assets" / "streets" / "manifest.json").read_text())


def _briefs() -> dict:
    base = _deck_city()[0]
    return json.loads((base / "assets" / "briefs.json").read_text())["briefs"]


def test_deck_pieces_replace_their_blockout_objects():
    base, model, _ = _deck_city()
    assert model.decks
    cx = Ctx(model)
    pieces = {p.id: p for p in SD.gather(cx)}
    dk = model.decks[0]
    slabs = [n for n in cx.keys[dk.id] if n.startswith(f"{dk.id}.slab.")]
    assert slabs and all(n in pieces and pieces[n].replaces == [n] for n in slabs)
    deck_st = [s for s in model.structures if SD.is_deck_structure(s)]
    assert {s.kind for s in deck_st} == {"column", "stair", "elevator"}
    for s in deck_st:
        p = pieces[s.id]
        assert p.replaces and set(p.replaces) == set(cx.keys[s.id])
        assert p.maker == {"column": "deck_column", "stair": "deck_stair",
                           "elevator": "deck_elevator"}[s.kind]


def test_deck_streets_pass_every_check():
    rep = _streets()
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    ids = {c["id"] for c in rep["checks"]}
    assert "street_decks" in ids
    assert rep["coverage"]["decks"]["assets"] == rep["coverage"]["decks"]["entities"] == 1


def test_deck_pieces_keep_a_full_fallback():
    """AG10's Unreal check: the slab's complex collision came from a Nanite fallback without
    its rail, so the deck's slab, stairs and elevators keep every triangle in it; other
    street pieces as before."""
    _streets()
    base = _deck_city()[0]
    con = json.loads((base / "assets" / "unreal_contribution.streets.json").read_text())
    kinds = {}
    for e in con["entries"]:
        kinds.setdefault(e["kind"], set()).add(bool(e.get("fallback_full")))
    for k in ("street.deck.slab", "street.deck.stair", "street.deck.elevator"):
        assert kinds.get(k) == {True}, k
    assert kinds["street.deck.column"] == {False} and kinds["street.road"] == {False}


def test_the_slab_and_its_parts():
    man = _manifest()
    _, model, _ = _deck_city()
    dk = model.decks[0]
    top, under = dk.top_m, dk.top_m - dk.slab_m
    slabs = {k: r for k, r in man["pieces"].items() if r["kind"] == "street.deck.slab"}
    assert slabs
    for k, r in slabs.items():
        assert {"concrete.soffit", "concrete.fascia", "stain"} <= set(r["slots"])
        lo, hi = r["bounds"]
        # (nothing of the slab's own under its fascia's drip edge or a light's housing, but
        # the colonnade's columns, which stand on the ground)
        assert hi[2] <= top + 0.15 + 1.11 + 1e-6
    assert sum(r["notes"]["deck"]["ribs"] for r in slabs.values()) > 0
    assert any(r["notes"]["deck"].get("clear_m") for r in slabs.values())
    # (lights in two rows along the ground streets under it, not only over its junctions)
    lines, jcs = SD._ground_streets(Ctx(model), SD.deck_of(Ctx(model), dk))
    assert lines and sum(r["notes"]["deck"]["lights"] for r in slabs.values()) > 2 * len(jcs)
    # the deck's streets lie on it (no girder under them); its ramps are solid
    for s in model.road_segments:
        if s.attrs.get("deck") != dk.id:
            continue
        r = man["pieces"][s.id]
        if s.attrs.get("role") == "deck_ramp":
            assert r["bounds"][0][2] < 0.0 and r["notes"]["walkways"]
            assert RD.deck_kind(s.model_dump(mode="json")) == "ramp"
        elif r.get("triangles"):
            assert r["bounds"][0][2] >= top - 0.01, s.id
            assert "concrete.deck" not in r["slots"], s.id
    # columns from the ground to the soffit, stairs and elevators from the ground to the top
    for s in model.structures:
        if not SD.is_deck_structure(s):
            continue
        r = man["pieces"][s.id]
        if s.kind == "column":
            assert abs(r["bounds"][0][2] - (-0.1)) < 0.02 or r["bounds"][0][2] == 0.0
            assert abs(r["bounds"][1][2] - under) < 0.01
        else:
            k = r["notes"]["link"]
            assert k["edge"] and k["low"] <= 0.05 and abs(k["high"] - top) < 0.01


def test_spans_and_ground():
    sq = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(4.0, 4.0), (4.0, 6.0), (6.0, 6.0), (6.0, 4.0)]
    assert SD.spans([sq], -5.0, 5.0, 1.0, 0.0) == [(5.0, 15.0)]
    assert SD.spans([sq, hole], -5.0, 5.0, 1.0, 0.0) == [(5.0, 9.0), (11.0, 15.0)]
    assert SD.spans([sq], -5.0, 20.0, 1.0, 0.0) == []
    flat = SD.Ref({"level": 3.5})
    assert flat(1.0, 2.0) == 3.5
    g = SD.Ref({"grid": {"x0": 0.0, "y0": 0.0, "cell": 4.0, "rows": [[0.0, 4.0], [0.0, 4.0]]},
                "bases": [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], 9.0]]})
    assert abs(g(2.0, 2.0) - 2.0) < 1e-9 and g(0.5, 0.5) == 9.0
    assert abs(g.ground(0.5, 0.5) - 0.5) < 1e-9


def test_buildings_keep_their_side_of_the_slab():
    briefs = _briefs()
    _, model, _ = _deck_city()
    dk = model.decks[0]
    roles: dict = {}
    for bid, br in briefs.items():
        d = br.get("deck")
        if d:
            roles.setdefault(d["role"], []).append(bid)
            assert d["id"] == dk.id and d["slab"]
    assert roles.get("on") and roles.get("under")
    for b in model.buildings:
        if b.attrs.get("deck_under") == dk.id:
            assert briefs[b.id]["deck"]["role"] == "under"
            assert abs(briefs[b.id]["deck"]["underside_m"] - (dk.top_m - dk.slab_m)) < 1e-6
        elif b.level:
            assert briefs[b.id]["deck"]["role"] == "on"
    plenums = 0
    for bid in sorted(roles["under"])[:12] + sorted(roles["on"])[:6]:
        br = briefs[bid]
        gm = GN.make(br)
        sh = SH.build(br, gm)
        pp = EN.part_points(sh["parts"])
        c = BD.check(br, sh["arrays"], pp)
        assert c["ok"], (bid, c)
        if br["deck"]["role"] == "under":
            plenums += sh["stats"].get("plenums", 0)
            assert not sh["roof_items"] and not sh["green"]
            # a covered street's grime and light
            assert gm["cont"]["wear"] >= 0.7 and gm["extra"]["lit"] >= 0.75
    assert plenums > 0


def test_a_city_without_decks_carries_none():
    base = small_build() / "base"
    briefs = json.loads((base / "assets" / "briefs.json").read_text())["briefs"]
    assert not any("deck" in br for br in briefs.values())
    model, _, _ = load_model(base)
    assert not model.decks and SD.gather(Ctx(model)) == []
