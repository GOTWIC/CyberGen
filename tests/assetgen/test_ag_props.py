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
from assetgen.props import glyphs as GL
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
    """4 to 12 variants per prop kind and style, 6 to 10 per tree species, every one a
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


def test_glyphs():
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        assert GL.latin_glyph(ch), ch
    strokes, (w, h) = GL.layout("NOODLES 24", "latin")
    assert h == GL.CAP and 50 < w < 60 and strokes
    a, _ = GL.layout("xxx", "hanzi", ("A",))
    b, _ = GL.layout("xxx", "hanzi", ("B",))
    assert a != b and a == GL.layout("xxx", "hanzi", ("A",))[0]
    v, (vw, vh) = GL.layout("BAR", "latin", vertical=True)
    assert vw == 6.0 and vh > 3 * GL.CAP
    assert SG.shop_text("food", "Velvet Koi", "k") == "VELVET KOI"
    assert SG.shop_text("bar", None, "k") == SG.shop_text("bar", None, "k")


def test_golden():
    base, _ = _small()
    g = json.loads(GOLDEN.read_text())
    assert PB.outputs_digest(base / "assets")["all"] == g["small"]["all"]
