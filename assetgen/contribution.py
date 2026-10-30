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

AG3: a building's street front (its ground band: shopfronts, doors, docks, steps, the
parts that reach down to the pavement) is its own node (`<id>.front`) and its own entry,
keyed `<id>.front`: at the building's pivot with its Custom Primitive Data, complex
collision (its own triangles, so doorways, steps and posts collide as drawn; the shell's
hulls start at the front's top, `band_m`), Nanite with its fallback at every triangle (the
fallback is what complex collision uses), its building's id, and its doors (`doors`: id,
kind, entrance or unit index, use, walkway id, position in the building frame, outward
normal, size), which the exporter tags on the front's actor and gathers into the `doors`
graph for stage 4.

AG3 with AG6's library: a tile's decals (grime, leaks, rust, graffiti, posters, cracks and
moss on the street bands) are one mesh of quads in the tile's pack (`decals.<tile>`, at the
tile's middle), its own entry keyed `decals.<tile>`: no Nanite (mesh decals), no collision,
a slot per decal atlas cell (`decal.<cell>`, master `decal` with the cell's index).

AG4: roof equipment (AC units, water tanks, antennas, pads, access huts, dunnage, vents,
skylights: `roofparts.ROOF`, always instanced) leaves the buildings' entries for one entry
per tile, keyed `roofs.<tile>`, whose parts gather every building's placements of each
mesh in the tile (transforms in the city frame, pivot 0, one building id per transform);
their slots take no tint, so the instances need no building's Custom Primitive Data. A
building whose green roofs AG4 built replaces the blockout's green-roof objects that draw
nothing else (`green_replaces`; an object also drawing a lawn or another building's
unbuilt green roof stays). The skybridges are `unreal_contribution.connections.json`
(`skybridges.py`).
"""

from __future__ import annotations

import re

from . import __version__
from .buildings import systems as SY

FRAME = ("building frame: citygen x east, y north, z up, m; glTF y up; Unreal "
         "(100 x, -100 y, 100 z) cm, yaw -> -yaw")
# a patch slot's color is its own times this times the building's patch tint (as the
# Blender preview draws it, `blender/preview_assets.py`); other tinted slots take the tint
PATCH_TINT_SCALE = 3.1


def asset_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_+\-]", "_", key)


def materials() -> dict:
    out = {}
    for name, (master, hex_c, rough, metal, tint) in sorted(SY.SLOTS.items()):
        out[name] = {"master": master, "color": SY.srgb_linear(hex_c), "roughness": rough,
                     "metallic": metal,
                     "tint_cpd": SY.CPD_TINT.get(tint) if tint else None}
        if tint == "patch":
            out[name].update(tint_scale=PATCH_TINT_SCALE, tint_times_color=True)
    return out


GREEN_MIN_M2 = 4.0      # (as `asset_checks.GREEN_MIN_M2`: a smaller green roof is not built)


def green_replaces(model, records: dict) -> dict[str, list[str]]:
    """Building id -> the blockout's green-roof objects (`{district}.green_roof.{tile}`) its
    entry replaces: each object whose every green area is a green roof AG4 built (or one
    too small to build), given to the smallest id among their buildings."""
    from shapely.geometry import Polygon
    from citygen import blockout as BO
    from citygen import geom as G
    with G.canonical():
        P = BO._Plan(model)
        BO._open_space(P)
    built = {g for r in records.values() for g in r.get("green") or []}
    ga = {g.id: g for g in model.green_areas}
    out: dict[str, list[str]] = {}
    for o in sorted(P.objects, key=lambda o: o["name"]):
        if o["category"] != "green_roof":
            continue
        owners = []
        for gid in o["props"]["citygen_ids"]:
            g = ga.get(gid)
            if g is None or g.kind != "green_roof" or g.building_id not in records:
                owners = None
                break
            if gid not in built:
                ring = [(p[0], p[1]) for p in g.polygon.exterior]
                if len(ring) >= 3 and Polygon(ring, [[(p[0], p[1]) for p in h]
                                                     for h in g.polygon.holes]).area \
                        >= GREEN_MIN_M2:
                    owners = None
                    break
            owners.append(g.building_id)
        if owners:
            out.setdefault(min(owners), []).append(o["name"])
    return {k: sorted(v) for k, v in sorted(out.items())}


def _roof_entries(man: dict) -> list[dict]:
    """AG4: an entry per tile with every building's roof equipment as instanced parts."""
    by: dict[str, dict] = {}
    for key, r in sorted(man["buildings"].items()):
        px, py, pz = r["pivot"]
        for x in r.get("parts", []):
            if not x.get("roof"):
                continue
            t = by.setdefault(r["tile"], {"glb": r["parts_glb"], "parts": {}})
            p = t["parts"].setdefault(x["node"], {"type": x["type"], "triangles": x["triangles"],
                                                  "xforms": [], "ids": []})
            for a in x["xforms"]:
                p["xforms"].append([round(px + a[0], 3), round(py + a[1], 3),
                                    round(pz + a[2], 3), a[3]])
                p["ids"].append(key)
    out = []
    for t, v in sorted(by.items()):
        # no collision, as AG2's parts (a body per instance; the roof is the building's)
        parts = [{"kind": n, "type": p["type"], "glb": v["glb"], "node": n,
                  "asset": asset_name(n), "count": len(p["xforms"]),
                  "triangles": p["triangles"], "collision": {"none": True},
                  "xforms": p["xforms"], "ids": p["ids"]}
                 for n, p in sorted(v["parts"].items())]
        out.append({"key": f"roofs.{t}", "kind": "roof_equipment",
                    "hash": man["tiles"][t]["hash"][:16], "replaces": [],
                    "pivot": [0.0, 0.0, 0.0], "yaw_deg": 0.0, "nanite": True,
                    "distance_field": False, "lumen_cards": False, "triangles": 0,
                    "slots": [], "collision": {"none": True}, "cpd": [], "parts": parts,
                    "instances": sum(p["count"] for p in parts),
                    "tags": {"cg.type": "roof_equipment", "cg.district": "", "cg.tile": t}})
    return out


def buildings(man: dict, lib: dict | None = None) -> dict:
    """The buildings' contribution; with the material library `lib` (AG6), textured
    materials, per-building material maps and AG6's Custom Primitive Data
    (`materials/contrib.py`)."""
    entries = []
    green = man.get("green_replaces") or {}
    for key, r in sorted(man["buildings"].items()):
        own = [x for x in r.get("parts", []) if not x.get("roof")]
        entries.append({
            "key": key, "kind": "building", "hash": r["hash"][:16],
            "replaces": list(green.get(key, [])),
            "glb": r["glb"], "node": r["node"], "asset": asset_name(r["node"]),
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
                      for x in own],
            "instances": sum(x["count"] for x in own),
            "tags": {"cg.type": r["type"], "cg.district": r["district"] or "",
                     "cg.tile": r["tile"]},
        })
        fr = r.get("front") or {}
        if fr.get("node") and fr.get("triangles", 0) > 0:
            entries.append({
                "key": f"{key}.front", "kind": "building.front", "hash": r["hash"][:16],
                "replaces": [], "glb": r["glb"], "node": fr["node"],
                "asset": asset_name(fr["node"]), "pivot": r["pivot"], "yaw_deg": 0.0,
                "nanite": True, "fallback_full": True, "distance_field": False,
                "lumen_cards": False, "triangles": fr["triangles"],
                "slots": sorted(fr["slots"]), "collision": {"complex": True},
                "cpd": r["cpd"], "ids": [key], "band_m": fr.get("band_m"),
                "doors": [{"id": d["id"], "kind": d["kind"], "entrance": d["entrance"],
                           "unit": d["unit"], "use": d["use"],
                           "walkway_id": d.get("walkway_id"),
                           "walkway_from": d.get("walkway_from"),
                           "position": d["position"], "normal": d["normal"],
                           "width_m": d["width_m"], "height_m": d["height_m"],
                           "flush": d["flush"]} for d in r.get("doors", [])],
                "tags": {"cg.type": "building.front", "cg.district": r["district"] or "",
                         "cg.tile": r["tile"]},
            })
            if r.get("level"):
                entries[-1]["level"] = r["level"]          # (M14: a front on a deck)
    entries += _roof_entries(man)
    mats = materials()
    if lib is not None:
        from .materials.atlases import DECAL_CELLS
        for cell in DECAL_CELLS:
            mats[f"decal.{cell}"] = {"master": "decal", "color": [1.0, 1.0, 1.0],
                                     "roughness": 0.8, "metallic": 0.0, "tint_cpd": None}
        for t, tr in sorted(man["tiles"].items()):
            dc = tr.get("decals")
            if not dc:
                continue
            entries.append({
                "key": dc["node"], "kind": "decals", "hash": tr["hash"][:16],
                "replaces": [], "glb": f"tiles/{t}.glb", "node": dc["node"],
                "asset": asset_name(dc["node"]), "pivot": dc["translation"], "yaw_deg": 0.0,
                "nanite": False, "distance_field": False, "lumen_cards": False,
                "triangles": 2 * dc["count"], "slots": sorted(dc["slots"]),
                "collision": {"none": True}, "cpd": [], "decals": dc["count"],
                "tags": {"cg.type": "decals", "cg.district": "", "cg.tile": t}})
    con = {"version": 1, "stage": "assetgen", "part": "buildings", "layer": 2,
           "generator": f"assetgen {__version__} ({man['generator']})", "frame": FRAME,
           "city": man["city"], "model_sha256": man["model_sha256"],
           "masters": ["facade", "glass", "metal", "neon", "foliage"],
           "materials": mats, "cpd_layout": SY.CPD_LAYOUT, "entries": entries}
    from .materials import contrib as MC
    return MC.buildings(con, man, lib)
