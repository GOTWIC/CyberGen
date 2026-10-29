"""AG6's part of the Unreal contributions (`docs/unreal_export.md`, AG6): textured materials
for the buildings', streets' and AG8's props' and signs' slots, the textures they read,
per-building material maps and Custom Primitive Data, and a third file,
`unreal_contribution.materials.json`, with the sign, ad and logo pages (masters `sign`) and
the decal material for AG3's placements.

Every material record keeps AG1's and AG7's fields (master, color, roughness, metallic,
tint rule) and adds `textures` (parameter -> texture name), `scalars` and `vectors`; the
contribution's `textures` table gives each texture's file (from `BUILD/assets/`: the
library through the `library` link, the city's pages under `textures/`), pixel hash, color
space and kind (`color`, `normal`: OpenGL green, flipped on import, `mask`), so a re-import
by hash reimports a texture only when its pixels change.
"""

from __future__ import annotations

from ..buildings import systems as SY
from . import catalog as CT
from . import params as MP

CPD_SIZE = SY.CPD_SIZE + 7


def _decorate(mats: dict, key: str, slot: str, era: str | None, lib: dict, part: str,
              tex: set) -> None:
    m = CT.material(slot, era, lib, part)
    rec = mats[key]
    rec["master"] = m["master"]
    rec["textures"] = m["textures"]
    rec["scalars"] = m["scalars"]
    rec["vectors"] = m["vectors"]
    if m.get("set"):
        rec["set"] = m["set"]
    tex.update(m["textures"].values())


def buildings(con: dict, man: dict, lib: dict | None) -> dict:
    """The buildings' contribution with AG6's materials (in place; returned)."""
    if lib is None:
        return con
    tex: set[str] = set()
    base = con["materials"]
    used: set[tuple[str, str]] = set()
    for e in con["entries"]:
        # (AG3: a street front takes its building's materials and parameters)
        bid = e["ids"][0] if e.get("kind") == "building.front" else e["key"]
        r = man["buildings"].get(bid) or {}
        mat = r.get("material")
        if mat is None:
            continue
        era = mat["era"]
        e["cpd"] = list(e["cpd"]) + list(mat["cpd"])
        mp = MP.slot_materials(e["slots"], era)
        if mp:
            e["materials"] = mp
            used.update((s, era) for s in mp)
    for slot in sorted(base):
        _decorate(base, slot, slot, None, lib, "buildings", tex)
    for slot, era in sorted(used):
        key = f"{slot}@{era}"
        base[key] = {k: v for k, v in base[slot].items()
                     if k not in ("textures", "scalars", "vectors", "set")}
        base[key]["slot"] = slot
        _decorate(base, key, slot, era, lib, "buildings", tex)
    con["masters"] = sorted({m["master"] for m in base.values()})
    con["cpd_layout"] = {**con.get("cpd_layout", {}), **MP.CPD_EXT}
    con["textures"] = CT.texture_table(tex, lib)
    con["library"] = {"version": lib["version"], "hash": lib["hash"],
                      "density_px_m": lib["density_px_m"]}
    return con


def streets(con: dict, lib: dict | None) -> dict:
    if lib is None:
        return con
    tex: set[str] = set()
    for slot in sorted(con["materials"]):
        _decorate(con["materials"], slot, slot, None, lib, "streets", tex)
    con["masters"] = sorted({m["master"] for m in con["materials"].values()})
    con["textures"] = CT.texture_table(tex, lib)
    con["library"] = {"version": lib["version"], "hash": lib["hash"],
                      "density_px_m": lib["density_px_m"]}
    return con


SIGN_STRENGTH = 4.0            # a sign page's emissive strength (the holo ads' page: 2)
HOLO = {"Opacity": 0.6, "Emissive": 3.0}


def page_texture(page: str, signs: dict) -> tuple[str, dict]:
    """A sign page's texture name and record (the same in every contribution naming it)."""
    f = signs["files"][page]
    return f"city.{page}", {"file": f["file"], "pixels_sha256": f["pixels_sha256"],
                            "size": f["size"], "srgb": True, "kind": "color"}


def props(con: dict, lib: dict | None, signs: dict | None = None) -> dict:
    """AG8's props or signs contribution with AG6's materials (in place; returned): every
    slot its catalog master and set (`catalog.PROP`, tinted by the slot's color), a sign
    face its page (`page.<page>`, master `sign`), a holo-ad screen its holo page
    (`holopage.<page>`, master `holo`, translucent)."""
    if lib is None:
        return con
    tex: set[str] = set()
    city: dict[str, dict] = {}
    mats = con["materials"]
    for slot in sorted(mats):
        pre, _, page = slot.partition(".")
        if pre in ("page", "holopage"):
            if signs is None or page not in signs["files"]:
                continue
            name, rec = page_texture(page, signs)
            city[name] = rec
            mats[slot].update(
                master="sign" if pre == "page" else "holo", textures={"SignTex": name},
                scalars=({"SignStrength": 2.0 if page.startswith("ads_1") else SIGN_STRENGTH,
                          "Masked": 0.0} if pre == "page" else {**HOLO, "Textured": 1.0}),
                vectors={})
            continue
        _decorate(mats, slot, slot, None, lib, con["part"], tex)
    con["masters"] = sorted({m["master"] for m in mats.values()})
    con["textures"] = dict(sorted({**CT.texture_table(tex, lib), **city}.items()))
    con["library"] = {"version": lib["version"], "hash": lib["hash"],
                      "density_px_m": lib["density_px_m"]}
    return con


def materials_part(city: str, model_sha: str, lib: dict, signs: dict) -> dict:
    """`unreal_contribution.materials.json`: no actors; a sign material per page (ads and
    holo-ads, logos with their alpha), the decal material, and their textures."""
    mats: dict[str, dict] = {}
    tex: dict[str, dict] = {}
    for name in sorted(signs["files"]):
        tname, tex[tname] = page_texture(name, signs)
        mats[name] = {"master": "sign", "color": [1.0, 1.0, 1.0], "roughness": 0.4,
                      "metallic": 0.0, "textures": {"SignTex": tname},
                      "scalars": {"SignStrength": 2.0 if name.startswith("ads_1")
                                  else SIGN_STRENGTH,
                                  "Masked": 1.0 if name == "logos" else 0.0},
                      "vectors": {}}
    dt = CT.texture_table({CT.atlas_tex("decals", k) for k in ("base", "normal", "orm")}, lib)
    tex.update(dt)
    mats["decals"] = {"master": "decal", "color": [1.0, 1.0, 1.0], "roughness": 0.8,
                      "metallic": 0.0,
                      "textures": {"BaseTex": CT.atlas_tex("decals", "base"),
                                   "NormalTex": CT.atlas_tex("decals", "normal"),
                                   "OrmTex": CT.atlas_tex("decals", "orm")},
                      "scalars": {"Cols": 4.0, "Rows": 4.0}, "vectors": {}}
    return {"version": 1, "stage": "assetgen", "part": "materials", "layer": 2,
            "city": city, "model_sha256": model_sha,
            "masters": sorted({m["master"] for m in mats.values()}), "materials": mats,
            "textures": dict(sorted(tex.items())), "entries": [],
            "library": {"version": lib["version"], "hash": lib["hash"],
                        "density_px_m": lib["density_px_m"]},
            "signs": {"file": "signs.json", "counts": signs["counts"]}}
