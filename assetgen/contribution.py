"""assetgen's contribution to the Unreal exporter (`docs/unreal_export.md`, "assetgen's
contribution"): `BUILD/assets/unreal_contribution.<part>.json`, one file per part of stage 2
(`buildings` from AG1; AG7's `streets` beside it), each key in one file only, layered over
stage 1's blockout by key.

A building's entry replaces the blockout actor of the same name (its M10 id): the shell's
glTF node and asset, its pivot (the building's own origin, scope section 6), material slots
(one material instance each, parent by master), simple collision from the masses (boxes and
convex prisms, building frame, meters), Custom Primitive Data (`cpd_layout`), Nanite on with
distance fields and Lumen cards off (AG0's measurements), its far proxy (Nanite fallback and
HLOD input), and its parts (AG2): one per instanced part kind of the building, its mesh in
the tile's part pack (`parts/<tile>.glb`, the node named by the hash of the part's
parameters, so buildings whose parts coincide share one mesh), its count, triangles and
transforms (x, y, z in meters relative to the building's pivot, yaw in degrees
counterclockwise; a hierarchical instanced mesh in Unreal carrying the building's Custom
Primitive Data), and the building it belongs to. Parts a building places fewer than
`parts.INSTANCE_MIN` times are merged into its shell and not listed.
"""

from __future__ import annotations

import re

from . import __version__
from .buildings import systems as SY

FRAME = ("building frame: citygen x east, y north, z up, m; glTF y up; Unreal "
         "(100 x, -100 y, 100 z) cm, yaw -> -yaw")


def asset_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_+\-]", "_", key)


def materials() -> dict:
    out = {}
    for name, (master, hex_c, rough, metal, tint) in sorted(SY.SLOTS.items()):
        out[name] = {"master": master, "color": SY.srgb_linear(hex_c), "roughness": rough,
                     "metallic": metal,
                     "tint_cpd": SY.CPD_TINT.get(tint) if tint else None}
    return out


def buildings(man: dict) -> dict:
    entries = []
    for key, r in sorted(man["buildings"].items()):
        entries.append({
            "key": key, "kind": "building", "hash": r["hash"][:16], "replaces": [],
            "glb": r["glb"], "node": r["node"], "asset": asset_name(key),
            "pivot": r["pivot"], "yaw_deg": 0.0,
            "nanite": True, "distance_field": False, "lumen_cards": False,
            "triangles": r["triangles"], "slots": sorted(r["slots"]),
            "collision": {"simple": r["collision"]["boxes"],
                          "convex": r["collision"]["convex"]},
            "cpd": r["cpd"],
            "proxy": {"glb": r["proxy"]["glb"], "node": r["proxy"]["node"],
                      "asset": asset_name(key) + "_proxy",
                      "triangles": r["proxy"]["triangles"]},
            "parts": [{"kind": x["node"], "type": x["type"], "glb": r["parts_glb"],
                       "node": x["node"], "asset": asset_name(x["node"]),
                       "count": x["count"], "triangles": x["triangles"],
                       "xforms": x["xforms"], "building": key}
                      for x in r.get("parts", [])],
            "instances": r.get("instances", 0),
            "tags": {"cg.type": r["type"], "cg.district": r["district"] or "",
                     "cg.tile": r["tile"]},
        })
    return {"version": 1, "stage": "assetgen", "part": "buildings", "layer": 2,
            "generator": f"assetgen {__version__} ({man['generator']})", "frame": FRAME,
            "city": man["city"], "model_sha256": man["model_sha256"],
            "masters": ["facade", "glass", "metal", "neon", "foliage"],
            "materials": materials(), "cpd_layout": SY.CPD_LAYOUT, "entries": entries}
