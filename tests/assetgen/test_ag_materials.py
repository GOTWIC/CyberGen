"""AG6 (materials and textures): the library generator (tileable sets per era, trim sheets,
decal, road, interior and macro atlases), its index and cache, the glyphs and the city's
signage, the material catalog, per-building parameters, AG6's parts of the contributions,
the texel density check and `assetgen build`'s materials stage on the small test city;
decoded-pixel goldens for a few maps (scope section 10)."""

import json

import numpy as np
from PIL import Image

from assetgen.buildings import systems as SY
from assetgen.materials import atlases as AT
from assetgen.materials import catalog as CT
from assetgen.materials import checks as CK
from assetgen.materials import glyphs as GL
from assetgen.materials import interiors as IN
from assetgen.materials import library as LB
from assetgen.materials import noise as N
from assetgen.materials import params as MP
from assetgen.materials import pbr as P
from assetgen.materials import surfaces as S
from assetgen.streets import materials as SM

from agtools import HERE, golden, small_assets, small_assets_report

DENSITY = 32
_LIB: dict = {}


def small_library(tmp_path_factory=None):
    """A 32 px/m library, made once per process."""
    if "lib" not in _LIB:
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp(prefix="ag6_lib_"))
        _LIB["lib"] = LB.generate(d, DENSITY, workers=2, log=lambda *a: None)
        _LIB["dir"] = d
    return _LIB["lib"]


def test_noise_tiles_and_is_exact():
    """A lattice of period p wraps at the image edge (the first column continues the last);
    the same seed gives the same bits."""
    a = N.fbm(64, 4, 7, 4)
    b = N.fbm(64, 4, 7, 4)
    assert a.dtype == np.float32 and np.array_equal(a, b)
    edge = np.abs(a[:, 0] - a[:, -1]).max()
    inner = np.abs(np.diff(a, axis=1)).max()
    assert edge <= inner * 1.01
    d, i = N.cells(64, 8, 3)
    assert d.min() >= 0 and 0 <= i.min() and i.max() < 1


def test_every_surface_generator():
    for gen in S.GENERATORS:
        s = S.make(gen, 64, 2.0, {"seed": 5})
        assert s.color.shape == (64, 64, 3), gen
        for a in (s.color, s.height, s.rough, s.metal, s.mask):
            assert a.dtype == np.float32 and np.isfinite(a).all(), gen
            assert a.min() >= 0.0 and a.max() <= 1.0, gen
        maps = P.pack(s, 2.0)
        assert maps["base"].shape == (64, 64, 4) and maps["normal"].shape == (64, 64, 3)
        assert maps["orm"].shape == (64, 64, 4)


def test_normal_map_convention():
    """OpenGL normals from a height that rises along +v (rows going up the surface): green
    above the middle, red at the middle."""
    h = np.tile(np.linspace(0.0, 1.0, 32, dtype=np.float32)[:, None], (1, 32))
    n = P.normal(h, 50.0, 1.0)
    assert abs(float(n[16, 16, 0]) - 0.5) < 1e-3 and float(n[16, 16, 1]) > 0.5


def test_library_index_cache_and_budget():
    lib = small_library()
    assert set(lib["sets"]) == set(LB.sets()) and set(lib["atlases"]) == set(AT.ATLASES)
    eras = {k.rsplit("_", 1)[0] for k in lib["sets"] for e in LB.ERAS if k.endswith(e)}
    assert {"concrete", "plaster", "brick", "panel", "cladding", "roof"} <= eras
    for name, r in lib["sets"].items():
        size = r["files"]["base"]["size"][0]
        want = DENSITY if r["band"] == "street" else DENSITY // 2
        assert size == round(r["tile_m"] * want) and size & (size - 1) == 0, name
        assert len(r["ref"]) == 3
    # the files are what the index says (decoded pixels)
    d = _LIB["dir"]
    for r in list(lib["sets"].values())[:5] + list(lib["atlases"].values()):
        for f in r["files"].values():
            a = np.asarray(Image.open(d / f["file"]))
            assert P.pixels_sha256(a if a.ndim == 3 else a[:, :, None]) == \
                f["pixels_sha256"], f["file"]
    # a second run keeps everything
    again = LB.generate(d, DENSITY, workers=2, log=lambda *a: None)
    assert again["hash"] == lib["hash"] and again["sets"] == lib["sets"]
    disk = LB.disk(lib)
    assert disk["cooked_bytes"] < CK.LIB_COOKED


def test_library_goldens():
    """Decoded pixels of a few maps at 32 px/m (the determinism goldens of AG6)."""
    lib = small_library()
    want = golden()["ag6"]["library"]
    got = {f"{g}.{k}.{m}": lib[g][k]["files"][m]["pixels_sha256"]
           for g, k, m in (("sets", "brick_heritage", "base"), ("sets", "panel_brutalist", "orm"),
                           ("sets", "asphalt_street", "normal"),
                           ("atlases", "interiors", "night"), ("atlases", "decals", "base"),
                           ("atlases", "road", "base"), ("atlases", "trim_heritage", "base"))}
    assert got == want


def test_materials_golden():
    """The small city's material, sign and contribution files (on the 512 px/m library)."""
    from assetgen import canon as C
    import goldens as GD
    a = small_assets() / "assets"
    assert C.digest({f: C.sha256_bytes((a / f).read_bytes()) for f in GD.AG6_FILES}) == \
        golden()["ag6"]["testport_materials"]


def test_interior_projection():
    """The one-point image of a room: the back wall drawn at BACK of the window, centered;
    rooms of every use, day and night."""
    cell = 32
    day, night = IN.atlas(cell)
    assert day.shape == (len(IN.USES) * cell, IN.VARIANTS * cell, 3)
    # the formula the masters use: the back wall's corner (x, y, z) = (0, 0, 1)
    s = IN.BACK
    k = s / (s + (1 - s) * 1.0)
    assert abs((0.5 + (0.0 - 0.5) * k) - (1 - s) / 2) < 1e-9
    # night rooms are brighter than day rooms where lamps are
    assert night.max() > 0.9 and day.mean() > 0.05
    assert IN.use_row("residential") == IN.USES.index("apartment")
    assert IN.use_row("office", "building.warehouse") == IN.USES.index("warehouse")


def test_glyphs_every_script():
    for sc in GL.SCRIPTS:
        st, w = GL.layout("Jade Koi Ramen", sc)
        assert st and w > 0, sc
        assert GL.layout("Jade Koi Ramen", sc) == (st, w)
        assert GL.units("Jade Koi", sc)
    st, w = GL.layout("ABC 123", "latin")
    assert all(len(p) >= 2 for p in st)


def test_catalog_covers_every_slot():
    """Every building slot (AG1's and AG2's, `systems.SLOTS`) has its own catalog entry (none
    falls back untextured) and every street slot maps to a master; every set named is in the
    library."""
    lib = small_library()
    for slot in SY.SLOTS:
        assert slot in CT.BUILDING or slot in CT.ERA_SLOTS, slot
        for era in (None,) + LB.ERAS:
            master, s = CT.set_for(slot, era)
            assert master in CT.MASTERS, slot
            assert s is None or s in lib["sets"], (slot, era, s)
    for slot in SM.SLOTS:
        master, s = CT.set_for(slot, None, "streets")
        assert master in CT.MASTERS and (s is None or s in lib["sets"]), slot
    m = CT.material("brick", "heritage", lib)
    assert m["master"] == "facade" and m["set"] == "brick_heritage"
    assert set(m["textures"]) >= {"BaseTex", "NormalTex", "OrmTex", "Macro", "Decals"}
    g = CT.material("glass", None, lib)
    assert g["master"] == "glass" and g["scalars"]["Interior"] == 1.0
    assert CT.material("storefront", None, lib)["scalars"]["RowOverride"] == CT.INTERIOR_SHOP
    tt = CT.texture_table(set(m["textures"].values()), lib)
    assert tt["set.brick_heritage.normal"]["kind"] == "normal"
    assert tt["set.brick_heritage.base"]["srgb"] and not tt["set.brick_heritage.orm"]["srgb"]


def test_materials_stage_on_the_small_city():
    """`assetgen build`: the library linked from the assets, every texture a contribution
    names on disk, AG6's Custom Primitive Data and era materials on every building entry,
    a sign cell for every sign slot, the materials contribution, the checks pass."""
    base = small_assets()
    rep = small_assets_report()
    assert rep["materials"]["ok"], rep["materials"]
    a = base / "assets"
    assert (a / "library").is_symlink() and (a / "library" / "library.json").is_file()
    man = json.loads((a / "manifest.json").read_text())
    con = json.loads((a / "unreal_contribution.buildings.json").read_text())
    for name, t in con["textures"].items():
        assert (a / t["file"]).is_file(), name
    for e in con["entries"]:
        r = man["buildings"][e["key"]]
        assert len(e["cpd"]) == SY.CPD_SIZE + 7 and e["cpd"][SY.CPD_SIZE:] == \
            r["material"]["cpd"]
        for slot, key in (e.get("materials") or {}).items():
            assert slot in CT.ERA_SLOTS and key == f"{slot}@{r['material']['era']}"
            assert set(con["materials"][key]["textures"].values()) <= set(con["textures"])
    st = json.loads((a / "unreal_contribution.streets.json").read_text())
    assert st["textures"] and all(st["materials"][k]["master"] in CT.MASTERS
                                  for k in st["materials"])
    signs = json.loads((a / "signs.json").read_text())
    from assetgen.brief import load_model
    model = load_model(base)[0]
    assert set(signs["slots"]) == {s.id for s in model.sign_slots}
    for sid, key in signs["slots"].items():
        cell = signs["cells"][key]
        u0, v0, u1, v1 = cell["uv"]
        assert 0 <= u0 < u1 <= 1 and 0 <= v0 < v1 <= 1, sid
        assert (a / signs["files"][cell["page"]]["file"]).is_file()
    mc = json.loads((a / "unreal_contribution.materials.json").read_text())
    assert mc["entries"] == [] and "decals" in mc["materials"]
    assert all(m["master"] in ("sign", "decal") for m in mc["materials"].values())
    mr = json.loads((a / "materials_report.json").read_text())
    assert mr["checks"]["texel_density"]["ok"] and mr["checks"]["texture_budget"]["ok"]
    assert mr["checks"]["texel_density"]["triangles"] > 0


def test_params_per_building():
    base = small_assets()
    man = json.loads((base / "assets" / "manifest.json").read_text())
    briefs = json.loads((base / "assets" / "briefs.json").read_text())["briefs"]
    for bid, r in list(man["buildings"].items())[:40]:
        mat = r["material"]
        assert mat["era"] in LB.ERAS and mat["interior"] in IN.USES
        room, floor, row, streaks, top, blinds, era = mat["cpd"]
        assert 2.4 <= room <= 6.0 and floor > 2.0 and 0 <= streaks <= 1 and top > 0
        assert IN.USES[int(row)] == mat["interior"] and LB.ERAS[int(era)] == mat["era"]
        assert mat["era"] == CT.era_of_building(briefs[bid])
    assert MP.slot_materials(["brick", "glass", "roof"], "heritage") == {
        "brick": "brick@heritage", "roof": "roof@heritage"}


def test_texel_density_check_fails_when_the_library_is_too_coarse():
    """The small city's packs measured against a library whose sets are 4 times coarser
    than the 512 px/m the spec asks: the check fails and names the slots."""
    lib = small_library()
    base = small_assets()
    res = CK.texel_density(base / "assets", lib, 128, 64)
    assert not res["ok"] and res["flagged"]
    ok = CK.texel_density(base / "assets", lib, DENSITY, DENSITY // 2)
    assert ok["ok"], ok["meets_share"]
