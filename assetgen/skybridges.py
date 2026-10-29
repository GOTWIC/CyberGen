"""The skybridges' stage of `assetgen build` (scope 5.1.3, AG4): every model skybridge a
piece of its own (`buildings/connections.skybridge`), in packs per 256 m tile
(`BUILD/assets/connections/<tile>.glb`, a node per skybridge named by its id at its pivot,
turned to its line), their records in the manifest's `skybridges` and
`unreal_contribution.connections.json`: an entry per skybridge keyed by its id (the
blockout's skybridge object of that name is replaced), complex collision (its floor is
walked), its two buildings and walkways as links for stage 4.

A pack is written only when its bytes change; packs of tiles with no skybridge left are
removed. The bridges carry no building's Custom Primitive Data, so their slots are
untinted (`systems.SLOTS`: `bridge_*`, planters, lamps).
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from . import canon as C
from . import gltf as G
from . import manifest as MF
from .buildings import connections as CN
from .buildings import systems as SY

SKY_VERSION = 1
DIR = "connections"


def tile_of(cx: float, cy: float) -> str:
    from .build import tile_name
    return tile_name(cx, cy)


def _mats(g: G.Gltf, used) -> dict[str, int]:
    out = {}
    for name in sorted(used):
        master, hex_c, rough, metal, tint = SY.SLOTS[name]
        out[name] = g.material(name, SY.srgb_linear(hex_c) + [1.0], metal, rough,
                               extras={"slot": name, "master": master, "tint": None})
    return out


def build(model, out: Path, log=print) -> dict:
    """Make every skybridge; write the packs whose bytes changed. Returns the records (by
    id), the files per tile, the number of files written and the check."""
    recs: dict[str, dict] = {}
    by_tile: dict[str, list] = {}
    for s in sorted(model.skybridges, key=lambda s: s.id):
        d = s.model_dump(mode="json")
        (cx, cy), L, yaw = CN._frame_of(d)
        if L < 100:
            continue
        b, arrs, info = CN.skybridge(d)
        base = float(getattr(s, "base_m", None) or 0.0)
        t = tile_of(cx, cy)
        rec = {"kind": s.kind, "tile": t, "glb": f"{DIR}/{t}.glb", "node": s.id,
               "pivot": [C.m2(cx), C.m2(cy), C.m(base)], "yaw_deg": yaw,
               "length_m": C.m(L / 1000.0), "width_m": C.m(s.width_m),
               "z_m": C.m(s.z_m), "levels": int(s.levels),
               "buildings": list(s.building_ids), "walkways": sorted(s.walkway_ids),
               "triangles": info["triangles"],
               "slots": {k: int(len(a["tri"])) for k, a in arrs.items()},
               "check": info["check"],
               "hash": C.digest([SKY_VERSION, d])[:16]}
        recs[s.id] = rec
        by_tile.setdefault(t, []).append((s.id, b, arrs, rec))
    files: dict[str, dict] = {}
    wrote = 0
    d = out / DIR
    for t in sorted(by_tile):
        g = G.Gltf(generator=f"assetgen ({SKY_VERSION})")
        used = sorted({k for _, _, arrs, _ in by_tile[t] for k in arrs})
        mats = _mats(g, used)
        for sid, b, arrs, rec in by_tile[t]:
            m = g.mesh(sid, b.primitives(arrs, mats), extras={"kind": "skybridge"})
            piv = (int(round(rec["pivot"][0] * 1000)), int(round(rec["pivot"][1] * 1000)),
                   int(round(rec["pivot"][2] * 1000)))
            g.node(sid, mesh=m, translation=piv, rotation=G.quat_z(rec["yaw_deg"]), root=True,
                   extras={"cg": {"key": sid, "kind": "skybridge", "type": rec["kind"]}})
        data = g.to_glb()
        wrote += MF.write_if_changed(d / f"{t}.glb", data)
        files[t] = {"bytes": len(data), "sha256": C.sha256_bytes(data),
                    "skybridges": len(by_tile[t])}
    if d.is_dir():
        for p in sorted(d.glob("*.glb")):
            if p.stem not in files:
                p.unlink()
                wrote += 1
    bad = [k for k, r in sorted(recs.items())
           if r["check"]["degenerate"] or r["check"]["duplicate"] or r["check"]["open_edges"]
           or r["check"]["bad_edges"]]
    missing = sorted({s.id for s in model.skybridges} - set(recs))
    log(f"skybridges: {len(recs)} in {len(files)} tiles, {wrote} files written")
    return {"records": recs, "files": files, "wrote": wrote,
            "check": {"name": "asset_skybridges", "ok": not bad and not missing,
                      "skybridges": len(recs), "bad_meshes": len(bad), "missing": len(missing),
                      "by_kind": _count(recs), "first": (bad + missing)[:5]}}


def _count(recs: dict) -> dict:
    out: dict[str, int] = {}
    for r in recs.values():
        out[r["kind"]] = out.get(r["kind"], 0) + 1
    return dict(sorted(out.items()))


def contribution(man: dict, lib: dict | None) -> dict:
    """`unreal_contribution.connections.json`: an entry per skybridge."""
    from .contribution import FRAME, asset_name
    entries = []
    for key, r in sorted((man.get("skybridges") or {}).items()):
        entries.append({
            "key": key, "kind": "skybridge", "hash": r["hash"], "replaces": [],
            "glb": r["glb"], "node": r["node"], "asset": asset_name(r["node"]),
            "pivot": r["pivot"], "yaw_deg": r["yaw_deg"],
            "nanite": True, "distance_field": False, "lumen_cards": False,
            "triangles": r["triangles"], "slots": sorted(r["slots"]),
            "collision": {"complex": True}, "cpd": [], "ids": [key],
            "links": [f"building:{b}" for b in r["buildings"]] +
                     [f"walkway:{w}" for w in r["walkways"]],
            "tags": {"cg.type": f"skybridge.{r['kind']}", "cg.district": "",
                     "cg.tile": r["tile"]}})
    used = sorted({s for r in (man.get("skybridges") or {}).values() for s in r["slots"]})
    mats = {}
    for name in used:
        master, hex_c, rough, metal, _ = SY.SLOTS[name]
        mats[name] = {"master": master, "color": SY.srgb_linear(hex_c), "roughness": rough,
                      "metallic": metal, "tint_cpd": None}
    con = {"version": 1, "stage": "assetgen", "part": "connections", "layer": 2,
           "generator": f"assetgen {__version__} (skybridges {SKY_VERSION})", "frame": FRAME,
           "city": man["city"], "model_sha256": man["model_sha256"],
           "masters": sorted({m["master"] for m in mats.values()}), "materials": mats,
           "entries": entries}
    from .materials import contrib as MC
    return MC.streets(con, lib, "connections") if lib is not None else con
