"""assetgen's Unreal contribution for the ground (`docs/unreal_export.md`, AG13):
`unreal_contribution.ground.json`, layer 2 over the blockout as the other stages' are.

- `ground.<tile>`: the tile's ground mesh (`ground/tiles/<tile>.glb`, its one node) at the
  tile's middle, Nanite, complex collision; it replaces the blockout's ground cover objects
  (`<district>.cover_<kind>.<tile>`) and median lawns (`<district>.lawn.<tile>`) of its
  tile. A blockout object whose tile draws nothing of AG13's (its pieces lie in the tiles
  beside it) gets a `drop` entry.
- `grass.<tile>`: per clump variant an instanced part (`ground/clumps.glb`), its transforms
  in `ground/grass/<tile>.json` (`xforms_file`, the variant's node its key there: millions
  of clumps stay out of the manifest), not Nanite (the master sways by world position
  offset), no collision, no shadow, culled between `FADE_M` (decision 13.9 (a)).
- Materials: per surface and tile a `ground` material (its three sets, the tile's mask
  `city.ground.<tile>` and where the mask lies, the surface's blend weights and tint); per
  clump slot a `grass` material (its color and dry color, how much the wind moves it).
"""

from __future__ import annotations

import re

from .. import __version__
from .. import canon as C
from . import clumps as CL
from . import gather as GA
from . import kinds as K

FRAME = ("citygen x east, y north, z up, m; parts from the entry's pivot; Unreal "
         "(100 x, -100 y, 100 z) cm, yaw -> -yaw")
WIND = {"grass.lawn": 0.35, "grass.clover": 0.25, "grass.clover_flower": 0.3,
        "grass.meadow": 1.0, "grass.straw": 1.0, "grass.seed": 1.1, "grass.reed": 1.3,
        "grass.plume": 1.4, "grass.cattail": 0.9, "grass.weed": 0.6, "grass.fern": 0.5,
        "grass.stem": 0.8, "grass.eye": 0.8, "grass.scrub": 0.35, "grass.scrub_dry": 0.35,
        "grass.sedum": 0.05, "grass.sedum_red": 0.05}
COLOR = {"ground_lawn": "#4f7a34", "ground_meadow": "#6b8a3a", "ground_wild": "#7d7a44",
         "ground_dirt": "#6a5038", "ground_mud": "#4a3a2b", "ground_gravel": "#8a8378",
         "ground_sand": "#d2bd8a", "ground_moss": "#4d6a2a", "ground_rubble": "#7f7c75"}


def asset_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_+\-]", "_", key)


def _lin(hexc: str) -> list[float]:
    out = []
    for k in range(3):
        x = int(hexc[1 + 2 * k:3 + 2 * k], 16) / 255.0
        out.append(round(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4, 6))
    return out


def _h(man: dict, data) -> str:
    return C.digest([man["code_sha256"], data])[:16]


def ground_material(slot: str, lib: dict | None, mask: str | None) -> dict:
    """A ground slot's material record: master `ground`, its surface's sets and weights."""
    from ..materials import catalog as CT
    sf = K.surface_of_slot(slot)
    base, worn, shade, tint, wk, mk, ek, xk = K.SURFACES[sf]
    tile = slot.rsplit(".", 1)[1]
    x0, y0, _, _ = GA.tile_box(tile)
    rec = {"master": "ground", "slot": slot,
           "color": _lin(tint) if tint else [1.0, 1.0, 1.0], "roughness": 0.95,
           "metallic": 0.0, "textures": {},
           "scalars": {"MaskX0": x0, "MaskY0": y0, "MaskSize": K.TILE_M, "WearK": wk,
                       "MossK": mk, "EdgeK": ek, "WetK": xk, "Tinted": 1.0 if tint else 0.0,
                       "Textured": 0.0},
           "vectors": {"BaseColor": _lin(COLOR.get(base, "#6a6a6a")),
                       "WornColor": _lin(COLOR.get(worn, "#6a5038")),
                       "ShadeColor": _lin(COLOR.get(shade, "#4d6a2a"))}}
    if lib is not None and all(s in lib["sets"] for s in (base, worn, shade)):
        for pre, s in (("", base), ("Worn", worn), ("Shade", shade)):
            for kind, name in (("base", "Base"), ("normal", "Normal"), ("orm", "Orm")):
                rec["textures"][f"{pre}{name}Tex"] = CT.tex_name(s, kind)
            rec["scalars"][f"{pre}TileM"] = lib["sets"][s]["tile_m"]
            rec["vectors"][f"{pre}RefColor"] = _lin("#" + "".join(
                f"{int(round(v * 255)):02x}" for v in lib["sets"][s]["ref"]))
        rec["textures"]["Macro"] = CT.atlas_tex("macro", "macro")
        rec["scalars"]["Textured"] = 1.0
        rec["set"] = base
    if mask is not None:
        rec["textures"]["Mask"] = mask
    return rec


def grass_material(slot: str) -> dict:
    col, dry = CL.slot_colors(slot)
    return {"master": "grass", "slot": slot, "color": _lin(col), "roughness": CL.ROUGHNESS,
            "metallic": 0.0, "textures": {},
            "scalars": {"Wind": WIND.get(slot, 0.8 if slot.startswith(CL.FLOWER_PREFIX)
                                         else 0.6)},
            "vectors": {"DryColor": _lin(dry)}}


def contribution(man: dict, lib: dict | None) -> dict:
    from ..materials import catalog as CT
    entries, mats, tex = [], {}, {}
    tiles = man["tiles"]
    keys = man.get("keys") or {}
    # each blockout object goes with its tile's entry; one whose tile draws nothing, a drop
    by_tile: dict[str, list[str]] = {}
    for k, r in sorted(keys.items()):
        by_tile.setdefault(r["tile"], []).append(k)
    clumps = man.get("clumps") or {}
    used_tex: set[str] = set()
    for t in sorted(tiles):
        tr = tiles[t]
        cx, cy = [(a + b) / 2.0 for a, b in zip(GA.tile_box(t)[:2], GA.tile_box(t)[2:])]
        pivot = [cx, cy, 0.0]
        rep = by_tile.pop(t, [])
        node = tr.get("node") or {}
        if node.get("triangles"):
            mname = f"city.ground.{t}"
            tex[mname] = {"file": f"ground/masks/{t}.png",
                          "pixels_sha256": tr["mask"]["pixels_sha256"],
                          "size": [K.MASK_PX, K.MASK_PX], "srgb": False, "kind": "mask"}
            for s in node["slots"]:
                mats[s] = ground_material(s, lib, mname)
                used_tex.update(v for k2, v in mats[s]["textures"].items() if k2 != "Mask")
            entries.append({"key": f"ground.{t}", "kind": "ground.cover",
                            "hash": _h(man, [tr["hash"], tr["glb"]["sha256"], rep]),
                            "replaces": rep, "glb": f"ground/tiles/{t}.glb",
                            "node": node["node"], "asset": asset_name(node["node"]),
                            "pivot": pivot, "yaw_deg": 0.0, "nanite": True,
                            "triangles": node["triangles"], "slots": node["slots"],
                            "tile": t,
                            "tags": {"cg.type": "ground_cover", "cg.tile": t}})
            rep = []
        if tr.get("instances"):
            parts, tri = [], 0
            for nd, n in sorted(tr["instances"].items()):
                rec = clumps.get(nd, {})
                for s in rec.get("slots", []):
                    if s not in mats:
                        mats[s] = grass_material(s)
                parts.append({"kind": nd, "glb": "ground/clumps.glb", "node": nd,
                              "asset": asset_name(nd), "count": n,
                              "triangles": rec.get("triangles", 0),
                              "xforms_file": f"ground/grass/{t}.json",
                              "nanite": False, "collision": {"none": True},
                              "cull_m": list(K.FADE_M), "shadow": False})
                tri += rec.get("triangles", 0) * n
            entries.append({"key": f"grass.{t}", "kind": "ground.grass",
                            "hash": _h(man, [tr["hash"], tr["grass"]["sha256"], rep]),
                            "replaces": rep, "pivot": pivot, "yaw_deg": 0.0, "tile": t,
                            "parts": parts, "instanced_triangles": tri,
                            "tags": {"cg.type": "ground_grass", "cg.tile": t}})
            rep = []
        if rep:
            by_tile[t] = rep
    for t, rep in sorted(by_tile.items()):
        for k in rep:
            entries.append({"key": k, "kind": "ground.drop", "hash": _h(man, ["drop", k]),
                            "drop": True, "replaces": [], "tile": t})
    if lib is not None:
        tex.update(CT.texture_table(used_tex, lib))
    entries.sort(key=lambda e: e["key"])
    return {"version": 1, "stage": "assetgen", "part": "ground", "layer": 2,
            "generator": f"assetgen {__version__} (AG13)", "frame": FRAME, "city": man["city"],
            "model_sha256": man["model_sha256"],
            "masters": sorted({m["master"] for m in mats.values()}),
            "materials": dict(sorted(mats.items())), "textures": dict(sorted(tex.items())),
            "entries": entries,
            "library": ({"version": lib["version"], "hash": lib["hash"],
                         "density_px_m": lib["density_px_m"]} if lib is not None else None)}
