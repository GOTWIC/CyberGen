"""assetgen's Unreal contributions for props and signs (`docs/unreal_export.md`, AG8):
`unreal_contribution.props.json` and `unreal_contribution.signs.json`, layer 2 over the
blockout as AG1's and AG7's are.

- **props**: one entry per M15 prototype actor (`prop.<kind>.<tile>`, `plant.<type>.<tile>`,
  the key of the blockout actor it replaces) holding its variants as instanced parts: per
  part kind the family pack's node, transforms `[x, y, z, yaw, sx, sy, sz]` from the tile's
  middle (the entry's pivot) and the citygen id of each instance; plants with Nanite foliage
  (`shape_preservation: voxelize`, AG0) and no collision. The exact props of a tile (cables,
  scaffolding, gates) are one mesh per kind and tile in place of their prototype actor. A
  prototype actor whose every instance is left out (M6 highway barriers on AG7's median
  barrier) gets a `drop` entry.
- **signs**: one actor per sign slot at its position and yaw (a mesh per distinct sign of a
  tile, shared by the slots that draw the same), replacing M15's shop sign prototypes of its
  tile; a holo-ad's image a second entry (`<slot>.holo`), non-Nanite with its LOD chain.
"""

from __future__ import annotations

import re

from .. import __version__
from . import materials as MT
from .build import tile_center

FRAME = ("citygen x east, y north, z up, m; parts from the entry's pivot; Unreal "
         "(100 x, -100 y, 100 z) cm, yaw -> -yaw")


def asset_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_+\-]", "_", key)


def props(man: dict, g) -> dict:
    entries, slots = [], set()
    fams = man["families"]
    for key, gr in g.groups.items():
        t = gr["tile"]
        cx, cy = tile_center(t)
        parts = []
        tri = 0
        for part in sorted(gr["parts"]):
            what, name = part.split(".")[:2]
            f = fams[f"{what}.{name}"]
            rec = f["meshes"][part]
            slots |= set(rec.get("slots", []))
            p = gr["parts"][part]
            pe = {"kind": part, "glb": f["glb"], "node": part, "asset": asset_name(part),
                  "count": len(p["xforms"]), "triangles": rec["triangles"],
                  "xforms": p["xforms"], "ids": p["ids"]}
            if what == "plant":
                pe.update(nanite=True, shape_preservation="voxelize",
                          collision={"none": True})
            tri += rec["triangles"] * len(p["xforms"])
            parts.append(pe)
        e = {"key": key, "kind": f"{gr['cls']}.{gr['kind']}", "replaces": [],
             "pivot": [cx, cy, 0.0], "yaw_deg": 0.0, "tile": t,
             "tags": {"cg.type": f"{gr['cls']}.{gr['kind']}", "cg.tile": t}}
        if parts:
            e.update(hash=_h(man, [[p["kind"], p["xforms"], p["ids"]] for p in parts]),
                     parts=parts, instanced_triangles=tri)
        else:
            e.update(hash=_h(man, ["drop", key]), drop=True)
        entries.append(e)
    for t in sorted(man["tiles"]):
        tr = man["tiles"][t]
        nodes = tr.get("props_nodes") or {}
        cx, cy = tile_center(t)
        for node in sorted(nodes):
            rec = nodes[node]
            if not rec.get("triangles"):
                continue
            slots |= set(rec["slots"])
            entries.append({"key": node, "kind": "prop." + node.split(".")[1],
                            "hash": _h(man, [tr["hash"], node]), "replaces": [],
                            "glb": f"props/tiles/{t}.glb", "node": node,
                            "asset": asset_name(node), "pivot": [cx, cy, 0.0], "yaw_deg": 0.0,
                            "nanite": True, "triangles": rec["triangles"],
                            "slots": rec["slots"], "collision": {"none": True}, "tile": t,
                            "tags": {"cg.type": "prop." + node.split(".")[1], "cg.tile": t}})
    for f in fams.values():
        for rec in f["meshes"].values():
            slots |= set(rec.get("slots", []))
    entries.sort(key=lambda e: e["key"])
    return {"version": 1, "stage": "assetgen", "part": "props", "layer": 2,
            "generator": f"assetgen {__version__} (AG8)", "frame": FRAME, "city": man["city"],
            "model_sha256": man["model_sha256"], "masters": list(MT.MASTERS),
            "materials": MT.contribution_materials(slots), "entries": entries}


BIG_SIGNS = {("billboard", "facade"): "billboard", ("banner", "facade"): "banner",
             ("holo_ad", "front"): "holo", ("holo_ad", "roof"): "holo"}


def signs(man: dict, g) -> dict:
    entries, slots = [], set()
    for t, items in g.signs.items():
        tr = man["tiles"][t]
        nodes = tr.get("signs_nodes") or {}
        lods = tr.get("lods") or {}
        for s in items:
            rec = nodes.get(s["node"], {})
            slots |= set(rec.get("slots", []))
            kind = s["kind"]
            # (shop signs replace M6's sign prototype; M20's large ads the blockout's
            # prototypes of their kind, `blockout.SIGN_PROTO`)
            big = BIG_SIGNS.get((kind, s["inputs"]["mount"]))
            e = {"key": s["id"], "kind": f"sign.{kind}", "hash": s["digest"][:16],
                 "replaces": [f"prop.sign.{t}"] if kind == "shop_sign" and s["prop_id"] else
                 [f"sign.{big}.{t}"] if big else [],
                 "glb": f"props/signs/{t}.glb", "node": s["node"], "asset": asset_name(s["node"]),
                 "pivot": s["pivot"], "yaw_deg": s["yaw"], "nanite": True,
                 "triangles": rec.get("triangles", 0), "slots": rec.get("slots", []),
                 "collision": {"none": True}, "tile": t,
                 "tags": {"cg.type": f"sign_slot.{kind}", "cg.tile": t}}
            entries.append(e)
            ex = lods.get(s["node"])
            if ex:
                chain = []
                for k, node in enumerate(ex["nodes"]):
                    r = nodes.get(node, {})
                    slots |= set(r.get("slots", []))
                    chain.append({"node": node, "screen_size": ex["screen"][k],
                                  "triangles": r.get("triangles", 0)})
                entries.append({"key": s["id"] + ex["suffix"], "kind": f"sign.{kind}{ex['suffix']}",
                                "hash": s["digest"][:16], "replaces": [],
                                "glb": f"props/signs/{t}.glb", "node": chain[0]["node"],
                                "asset": asset_name(s["id"] + ex["suffix"]), "pivot": s["pivot"],
                                "yaw_deg": s["yaw"], "nanite": ex["nanite"],
                                "triangles": chain[0]["triangles"],
                                "slots": nodes.get(chain[0]["node"], {}).get("slots", []),
                                "collision": {"none": True}, "tile": t, "lods": chain,
                                "tags": {"cg.type": f"sign_slot.{kind}", "cg.tile": t}})
    entries.sort(key=lambda e: e["key"])
    return {"version": 1, "stage": "assetgen", "part": "signs", "layer": 2,
            "generator": f"assetgen {__version__} (AG8)", "frame": FRAME, "city": man["city"],
            "model_sha256": man["model_sha256"], "masters": list(MT.MASTERS),
            "materials": MT.contribution_materials(slots), "entries": entries}


def _h(man: dict, data) -> str:
    from .. import canon as C
    return C.digest([man["code_sha256"], data])[:16]
