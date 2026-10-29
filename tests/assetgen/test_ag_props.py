"""AG8, props, plants and signs (scope 5.4, 5.5, 9, 14.9): every prop, plant and sign slot
of the small test city has an asset, every M15 prototype actor is replaced, the families
have their variants, meshes are valid, budgets hold, packs are kept by hash (a second build
writes nothing), the bytes do not depend on the worker count, placements pick their variant
from their id, and the golden holds (`tests/assetgen/props_goldens.py` writes it)."""

import json
import re
from pathlib import Path

from assetgen import canon as C
from assetgen.brief import load_model
from assetgen.props import build as PB
from assetgen.props import materials as MT
from assetgen.props import signs as SG
from assetgen.props import styles as ST
from assetgen.props import trees as TR
from assetgen.props import variants as V
from assetgen.props.shapes import check
from assetgen.streets import build as SB

from agtools import HERE, small_build

GOLDEN = HERE / "data" / "golden_props.json"
_DONE: dict = {}


def _props(build_dir: Path, out: Path | None = None, workers: int = 2) -> dict:
    model, sha, bdir = load_model(build_dir)
    return PB.build(model, sha, out or bdir / "assets", None, workers=workers)


def _small() -> tuple[Path, dict]:
    if "small" not in _DONE:
        base = small_build() / "base"
        model, sha, bdir = load_model(base)
        SB.build(model, sha, bdir / "assets", None, workers=2)
        _DONE["small"] = (base, _props(base))
    return _DONE["small"]


def test_small_city_props_pass():
    base, rep = _small()
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    st = rep["stats"]
    assert st["instances"] > 0 and st["signs"] == st["sign_slots"] > 0
    assert st["variants"] >= 4 * 5 * 4
    model = load_model(base)[0]
    assert st["props"] == len(model.props) and st["plants"] == len(model.plants)


def test_second_build_writes_nothing():
    base, _ = _small()
    pdir = base / "assets" / "props"
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in pdir.rglob("*.glb")}
    rep = _props(base)
    f = rep["files"]
    assert f["tiles_made"] == 0 and f["families_made"] == 0 and not f["written"]
    assert not f["manifest_written"] and not any(f["contribution_written"])
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in pdir.rglob("*.glb")}
    assert before == after


def test_bytes_do_not_depend_on_workers(tmp_path):
    base, _ = _small()
    model, sha, _ = load_model(base)
    out = tmp_path / "one"
    out.mkdir()
    (out / "streets").mkdir()
    (out / "streets" / "manifest.json").write_bytes(
        (base / "assets" / "streets" / "manifest.json").read_bytes())
    PB.build(model, sha, out, None, workers=1)
    assert PB.outputs_digest(out)["all"] == PB.outputs_digest(base / "assets")["all"]


def test_families_and_meshes():
    """4 to 12 variants per prop kind and style, 6 or 8 per plant species, every one a
    valid mesh within its budget; the same parameters give the same mesh."""
    for kind, n in ST.PROP_VARIANTS.items():
        assert 4 <= n <= 12, kind
        for st in ST.STYLES:
            for k in range(n):
                m = V.make(kind, st, k)
                assert m.triangles > 0, (kind, st, k)
                assert not any(check(m.slots).values()), (kind, st, k)
                assert m.triangles <= PB.VARIANT_TRIANGLES, (kind, st, k)
    for sp, n in ST.PLANT_VARIANTS.items():
        assert (6 if sp in TR.TREES else 4) <= n <= 10, sp
        m = TR.make(sp, 0)
        assert 0 < m.triangles <= PB.PLANT_TRIANGLES and not any(check(m.slots).values())
        # leaves on alpha-cut cards, each showing the whole leaf tile
        for name, sl in m.slots.items():
            if name.startswith("leaf."):
                assert set(sl.uv) <= set(TR.CARD_UV) and len(sl.pos) % 4 == 0, (sp, name)
    a, b = TR.make("oak", 3), TR.make("oak", 3)
    assert {k: (s.pos, s.idx) for k, s in a.slots.items()} == \
        {k: (s.pos, s.idx) for k, s in b.slots.items()}


def test_placements_pick_their_variant_from_their_id():
    """A prop's variant is the hash of its id within its kind and style's family, not its
    order: the contribution's parts hold every prop id once, under the variant the hash
    names."""
    base, _ = _small()
    con = json.loads((base / "assets" / "unreal_contribution.props.json").read_text())
    model = load_model(base)[0]
    kind_of = {p.id: p.type.split(".", 1)[1] for p in model.props}
    seen = {}
    for e in con["entries"]:
        for part in e.get("parts", []):
            for pid in part["ids"]:
                if pid in kind_of and kind_of[pid] not in ("awning", "trash", "ac_unit",
                                                           "wall_light"):
                    seen.setdefault(pid, part["kind"])
    assert seen
    for pid, part in seen.items():
        kind = kind_of[pid]
        k = int(part.rsplit(".v", 1)[1])
        assert k == ST.pick(ST.PROP_VARIANTS[kind], "ag8.prop", pid)


def test_m13_lifts_placements_by_base_or_ground(tmp_path):
    """On a terrain city a placement stands on its building's base when it hangs on a
    building, else on the finished ground at its point; on a flat city nothing moves."""
    from types import SimpleNamespace

    from assetgen.props.gather import gather
    base, _ = _small()
    flat = load_model(base)[0]
    t = SimpleNamespace(x0=-1e4, y0=-1e4, cell_m=1e4, natural=[[5.0] * 3] * 3,
                        ground=[[5.0] * 3] * 3, water_levels=[])
    hilly = flat.model_copy(update={
        "terrain": t, "buildings": [b.model_copy(update={"base_m": 9.0})
                                    for b in flat.buildings]})

    def zs(g):
        out = {}
        for gr in g.groups.values():
            for p in gr["parts"].values():
                for i, xf in zip(p["ids"], p["xforms"]):
                    out.setdefault(i, xf[2])
        return out

    a, b = gather(flat, None, None, tmp_path), gather(hilly, None, None, tmp_path)
    za, zb = zs(a), zs(b)
    assert za.keys() == zb.keys()
    lifts = {round(zb[i] - za[i], 3) for i in za}
    assert lifts == {5.0, 9.0}
    on_bld = {p.id for p in flat.plants if (p.attrs or {}).get("building")}
    assert on_bld and all(round(zb[i] - za[i], 3) == 9.0 for i in on_bld)
    sa = {s["id"]: s["pivot"][2] for v in a.signs.values() for s in v}
    sb = {s["id"]: s["pivot"][2] for v in b.signs.values() for s in v}
    bid = {s.id: s.building_id for s in flat.sign_slots}
    assert sa and all(round(sb[i] - sa[i], 3) == (9.0 if bid[i] else 5.0) for i in sa)


def test_contributions():
    """Props replace M15's prototype actors by their keys; signs are one actor per slot at
    its position and yaw, shop signs replacing the sign prototypes of their tile; a holo-ad's
    image is a non-Nanite LOD chain; no node name ends in a dot and digits (Blender's glTF
    import reads that as a counter)."""
    base, _ = _small()
    cp = json.loads((base / "assets" / "unreal_contribution.props.json").read_text())
    cs = json.loads((base / "assets" / "unreal_contribution.signs.json").read_text())
    model = load_model(base)[0]
    keys = {e["key"] for e in cp["entries"]}
    assert all(re.match(r"^(prop|plant)\.[a-z_]+\.t[+-]\d\d[+-]\d\d$", k) for k in keys)
    for e in cp["entries"]:
        for p in e.get("parts", []):
            assert len(p["xforms"]) == len(p["ids"]) == p["count"]
            assert all(len(x) == 7 for x in p["xforms"])
            if p["kind"].startswith("plant."):
                assert p["shape_preservation"] == "voxelize" and p["collision"] == {"none": True}
    slots = {s.id: s for s in model.sign_slots}
    assert {e["key"] for e in cs["entries"] if not e["key"].endswith(".holo")} == set(slots)
    for e in cs["entries"]:
        s = slots.get(e["key"])
        if s is not None:
            assert e["pivot"] == [C.m2(v) for v in s.position]
            if s.kind == "shop_sign":
                assert e["replaces"] == [f"prop.sign.{e['tile']}"]
        if e.get("lods"):
            assert not e["nanite"] and len(e["lods"]) == 3
    for e in cp["entries"] + cs["entries"]:
        for n in [e.get("node") or ""] + [p["node"] for p in e.get("parts", [])]:
            assert not re.search(r"\.\d+$", n), n


def test_signs_follow_ag6():
    """One sign path: every sign says what AG6's signage gives its slot (text, script; the
    style decides the body), a face shows its page cell on UV0 (read upright: the cell's
    top on the face's top), and the text is laid out in AG6's strokes."""
    from assetgen import spec as S
    from assetgen.materials import signage as SG6
    base, _ = _small()
    model = load_model(base)[0]
    doc = S.dump(S.fill(S.AssetSpec()))
    slots, texts = SG6.slot_texts(model, SG6.district_styles(model, doc))
    man = json.loads((base / "assets" / "props" / "manifest.json").read_text())
    shop = [s for s in model.sign_slots if s.kind in ("shop_sign", "neon")]
    assert shop
    for s in shop:
        rec = man["signs"][s.id]
        assert rec["text"] == texts[slots[s.id]]["text"]
        assert rec["script"] == texts[slots[s.id]]["script"]
    st, (w, h) = SG.layout("NOODLES 24", "latin", False)
    assert h == 6.0 and 45 < w < 55 and st
    _, (vw, vh) = SG.layout("BAR", "latin", True)
    assert vw <= 6.0 and vh > 3 * 6.0
    inp = {"kind": "shop_sign", "mount": "facade", "w": 3.0, "h": 0.8, "look": "lightbox",
           "text": "JADE KOI", "script": "latin", "colors": ["#ff3fb4", "#2fe0ff"],
           "cell": {"slot": "page.signs_wide_0", "uv": [0.25, 0.5, 0.375, 0.53125]}}
    m, _ = SG.make(inp)
    f = m.slots["page.signs_wide_0"]
    assert len(f.pos) == 4 and "sign.back" not in m.slots       # the text is the page's
    top = max(p[2] for p in f.pos)
    assert {uv for p, uv in zip(f.pos, f.uv) if p[2] == top} == {(0.25, 0.5), (0.375, 0.5)}
    flat, _ = SG.make({k: v for k, v in inp.items() if k != "cell"})
    assert "sign.back" in flat.slots                            # no pages: the strokes


def test_every_slot_has_a_catalog_entry():
    """Every material slot of the props, plants and signs maps to one of AG6's masters and
    a library set (or none for what glows), and every leaf card slot to a leaf clump set."""
    from assetgen.materials import catalog as CT
    from assetgen.materials import library as LB
    sets = LB.sets()
    names = set(MT.SLOTS) | {n + ".d" for n in MT.SLOTS} | {
        MT.neon_slot("#ff2a6d"), MT.face_slot("#ff2a6d"), MT.holo_slot("#ff2a6d"),
        "page.signs_wide_0", "holopage.ads_1"}
    for n in sorted(names):
        master, st = CT.prop_set(n)
        assert master in CT.MASTERS, n
        assert st is None or st in sets, n
        if n.startswith("leaf."):
            assert master == "leaves" and st.startswith("leaves_"), n
        if n.startswith(("bark.", "metal.", "car.", "fabric.", "plastic.")):
            assert st is not None, n


def test_golden():
    base, _ = _small()
    g = json.loads(GOLDEN.read_text())
    assert PB.outputs_digest(base / "assets")["all"] == g["small"]["all"]
