"""The water stage: gather every water piece of a city, make the tiles whose pieces changed,
write one glTF pack per 256 m tile, the riprap parts pack, the water manifest, assetgen's
Unreal contribution for water and the report.

```
BUILD/assets/water/<tile>.glb          per body: <body>.bed.<tile>, <body>.water.<tile>.lod<k>;
                                       per bank: <bank id>
BUILD/assets/water/parts.glb           the riprap stones
BUILD/assets/water/manifest.json       per tile: hash, file sha256; per piece: its meshes,
                                       replaces, triangles, slots, bounds, parts, notes
BUILD/assets/unreal_contribution.water.json
BUILD/assets/water_report.json, .txt   checks and stats
```

As AG7's street stage: a tile is made again only when the hash of its pieces (ids, input
hashes, maker versions, the code's hash) differs from the last manifest or its file is gone
or changed; an unchanged city writes no file but the report (`report_always`). Tiles are
made in up to 4 worker processes; the result does not depend on how many.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .. import __version__
from .. import canon as C
from ..gltf import Gltf, Primitive
from . import materials as MT
from . import makers as MK
from .pieces import WCtx, gather

WATER_VERSION = 1
MAX_WORKERS = 4
DROP_KEY = "water.blockout"


def code_hash() -> str:
    """sha256 of the code that makes the packs (this package, AG7's mesh kit and paths it
    uses, the glTF writer, the triangulator), so a changed maker remakes its tiles."""
    here = Path(__file__).resolve().parent
    files = sorted(here.glob("*.py")) + [here.parent / "gltf.py",
                                         here.parent / "triangulate.py",
                                         here.parent / "canon.py",
                                         here.parent / "streets" / "kit.py",
                                         here.parent / "streets" / "path.py"]
    return C.digest([[f.name, C.sha256_bytes(f.read_bytes().replace(b"\r\n", b"\n"))]
                     for f in files])


def tile_hash(pieces, digests: dict[str, str], code: str) -> str:
    return C.digest({"v": WATER_VERSION, "code": code,
                     "pieces": [[p.id, digests[p.id]] for p in sorted(pieces, key=lambda p: p.id)]})


# ---------------------------------------------------------------------------
# Making a tile (in a worker)
# ---------------------------------------------------------------------------

def _prim(nm: MK.NMesh, mats: dict) -> Primitive:
    return Primitive(material=mats[nm.slot], positions=nm.pos, indices=nm.idx,
                     normals=nm.nrm, uv0=nm.uv0, uv1=nm.uv1, colors=nm.col)


def _bounds(meshes, origin) -> list | None:
    ps = [m.pos for m in meshes if len(m.pos)]
    if not ps:
        return None
    p = np.concatenate(ps)
    lo, hi = p.min(axis=0), p.max(axis=0)
    return [[C.m(origin[0] + lo[0] / 1000.0), C.m(origin[1] + lo[1] / 1000.0),
             C.m(lo[2] / 1000.0)],
            [C.m(origin[0] + hi[0] / 1000.0), C.m(origin[1] + hi[1] / 1000.0),
             C.m(hi[2] / 1000.0)]]


def check_nmesh(meshes) -> dict:
    """Mesh validity (scope section 9) of numpy meshes: degenerate and duplicate triangles,
    winding (no directed edge twice in a slot), indices in range, finite UVs, unit normals."""
    bad = {"degenerate": 0, "duplicate": 0, "winding": 0, "index": 0, "uv": 0, "normal": 0}
    for m in meshes:
        idx = m.idx.reshape(-1, 3)
        nv = len(m.pos)
        if len(idx) and (idx.min() < 0 or idx.max() >= nv):
            bad["index"] += 1
            continue
        p = m.pos
        a, b, c = p[idx[:, 0]], p[idx[:, 1]], p[idx[:, 2]]
        cr = np.cross(b - a, c - a)
        bad["degenerate"] += int((~np.any(cr != 0, axis=1)).sum())
        key = np.sort(np.stack([idx[:, 0], idx[:, 1], idx[:, 2]], axis=1), axis=1)
        _, cnt = np.unique(key, axis=0, return_counts=True)
        bad["duplicate"] += int((cnt > 1).sum())
        e = np.concatenate([idx[:, [0, 1]], idx[:, [1, 2]], idx[:, [2, 0]]])
        _, ecnt = np.unique(e, axis=0, return_counts=True)
        bad["winding"] += int((ecnt > 1).sum())
        if not np.all(np.isfinite(m.uv0)):
            bad["uv"] += 1
        L = (m.nrm * m.nrm).sum(axis=1)
        bad["normal"] += int((np.abs(L - 1.0) > 1e-6).sum())
    return {k: v for k, v in bad.items() if v}


def make_tile(tile: str, pieces: list[dict]) -> dict:
    """Make every piece of a tile; the tile's glTF bytes and a record per piece."""
    from ..streets.kit import check as kit_check
    t0 = time.perf_counter()
    made = []
    for pd in sorted(pieces, key=lambda p: p["id"]):
        made.append((pd, MK.MAKERS[pd["maker"]](pd["inputs"])))
    slots = set()
    for pd, out in made:
        slots |= {m.slot for m in out.bed} | {m.slot for lod in out.lods for m in lod}
        if out.mesh is not None and out.mesh.triangles:
            slots |= set(out.mesh.slots)
        slots |= {m.slot for m in out.nm}
    g = Gltf(generator=f"assetgen {__version__} water")
    mats = MT.gltf_materials(g, slots)
    recs = {}
    for pd, out in made:
        o = pd["inputs"]["origin"]
        trans = (C.mm(o[0]), C.mm(o[1]), 0)
        rec = {"kind": pd["kind"], "maker": pd["maker"], "origin": [C.m2(o[0]), C.m2(o[1])]}
        if pd["maker"] == "body":
            body, _, t = pd["id"].partition("@")
            if out.bed:
                name = f"{body}.bed.{t}"
                g.node(name, g.mesh(name, [_prim(m, mats) for m in out.bed]),
                       translation=trans, root=True, extras={"kind": "water.bed"})
                rec["bed"] = {"node": name, "triangles": sum(m.triangles for m in out.bed),
                              "slots": sorted({m.slot for m in out.bed}),
                              "bounds": _bounds(out.bed, o), "checks": check_nmesh(out.bed)}
            lods = []
            for k, lod in enumerate(out.lods):
                name = f"{body}.water.{t}.lod{k}"
                g.node(name, g.mesh(name, [_prim(m, mats) for m in lod]), translation=trans,
                       root=True, extras={"kind": pd["kind"], "lod": k})
                lods.append({"node": name, "triangles": sum(m.triangles for m in lod),
                             "screen_size": MK.LOD_SCREEN[k],
                             "slots": sorted({m.slot for m in lod}),
                             "checks": check_nmesh(lod)})
            if lods:
                rec["lods"] = lods
                rec["bounds"] = _bounds(out.lods[0], o)
            rec["triangles"] = rec.get("bed", {}).get("triangles", 0) + (
                lods[0]["triangles"] if lods else 0)
        else:
            prims, tris, bad = [], 0, {}
            kit = out.mesh is not None and out.mesh.triangles
            if kit:
                prims += out.mesh.finish(mats)
                tris += out.mesh.triangles
                bad.update({k: v for k, v in kit_check(out.mesh.slots).items() if v})
            nms = [m for m in out.nm if m.triangles]
            if nms:
                prims += [_prim(m, mats) for m in nms]
                tris += sum(m.triangles for m in nms)
                for k, v in check_nmesh(nms).items():
                    bad[k] = bad.get(k, 0) + v
            if prims:
                g.node(pd["id"], g.mesh(pd["id"], prims), translation=trans, root=True,
                       extras={"kind": pd["kind"]})
                b = _bounds(nms, o) or [[0, 0, 0], [0, 0, 0]]
                if kit:
                    lo, hi = out.mesh.bounds_mm()
                    kb = [[C.m(o[0] + lo[0] / 1000.0), C.m(o[1] + lo[1] / 1000.0),
                           C.m(lo[2] / 1000.0)],
                          [C.m(o[0] + hi[0] / 1000.0), C.m(o[1] + hi[1] / 1000.0),
                           C.m(hi[2] / 1000.0)]]
                    b = kb if not nms else [[min(u, v) for u, v in zip(b[0], kb[0])],
                                            [max(u, v) for u, v in zip(b[1], kb[1])]]
                rec.update(triangles=tris,
                           slots=sorted(({m.slot for m in nms}) |
                                        (set(out.mesh.slots) if kit else set())),
                           bounds=b, checks=bad)
            else:
                rec["triangles"] = 0
        if out.empty:
            rec["empty"] = out.empty
        if out.parts:
            rec["parts"] = out.parts
        if out.notes:
            rec["notes"] = out.notes
        recs[pd["id"]] = rec
    data = g.to_glb() if g.nodes else b""
    return {"tile": tile, "glb": data, "pieces": recs,
            "seconds": round(time.perf_counter() - t0, 3)}


def _make_job(args):
    return make_tile(*args)


def parts_glb() -> tuple[bytes, dict]:
    g = Gltf(generator=f"assetgen {__version__} water parts")
    meshes = [(f"part.riprap.r{k}", MK.stone_part(k)) for k in range(MK.RIPRAP_VARIANTS)]
    slots = set()
    for _, m in meshes:
        slots |= set(m.slots)
    mats = MT.gltf_materials(g, slots)
    info = {}
    for name, m in meshes:
        g.node(name, g.mesh(name, m.finish(mats)), root=True)
        info[name] = {"triangles": m.triangles, "slots": sorted(m.slots)}
    return g.to_glb(), info


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------

def _write_if_changed(path: Path, data: bytes) -> bool:
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def build(model, model_sha: str, out_dir: Path, spec=None, workers: int | None = None,
          force: bool = False, report_always: bool = True, lib: dict | None = None,
          progress=None) -> dict:
    """Make the water packs of a city into out_dir (BUILD/assets); returns the report."""
    t0 = time.perf_counter()
    out_dir = Path(out_dir)
    wdir = out_dir / "water"
    cx = WCtx(model, out_dir)
    t_ctx = time.perf_counter()
    pieces, drop = gather(cx)
    t_gather = time.perf_counter()
    ids = set()
    for p in pieces:
        if p.id in ids:
            raise ValueError(f"two water pieces with id {p.id}")
        ids.add(p.id)
    digests = {p.id: p.digest() for p in pieces}
    by_tile: dict[str, list] = {}
    for p in pieces:
        by_tile.setdefault(p.tile, []).append(p)
    code = code_hash()
    hashes = {t: tile_hash(ps, digests, code) for t, ps in by_tile.items()}
    prev = {}
    mf = wdir / "manifest.json"
    if mf.is_file() and not force:
        try:
            prev = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
    prev_tiles = prev.get("tiles", {}) if prev.get("version") == WATER_VERSION else {}
    prev_pieces = prev.get("pieces", {}) if prev_tiles else {}
    todo, keep = [], []
    for t in sorted(by_tile):
        pt = prev_tiles.get(t)
        f = wdir / f"{t}.glb"
        ok = pt is not None and pt.get("hash") == hashes[t] and (
            (pt.get("bytes", 0) == 0 and not f.exists()) or
            (f.is_file() and f.stat().st_size == pt.get("bytes") and
             C.sha256_bytes(f.read_bytes()) == pt.get("sha256")))
        (keep if ok else todo).append(t)
    jobs = [(t, [{"id": p.id, "kind": p.kind, "maker": p.maker, "inputs": p.inputs}
                 for p in by_tile[t]]) for t in todo]
    n_workers = max(1, min(workers or MAX_WORKERS, MAX_WORKERS, len(jobs) or 1))
    results = {}
    t_make0 = time.perf_counter()
    from contextlib import nullcontext
    cm = progress.stage("water tiles", total=len(jobs)) if progress is not None else         nullcontext()
    with cm as st:
        if n_workers == 1 or len(jobs) <= 1:
            for j in jobs:
                r = _make_job(j)
                results[r["tile"]] = r
                if st is not None:
                    st.advance()
        else:
            jobs.sort(key=lambda j: (-sum(len(json.dumps(p["inputs"])) for p in j[1]), j[0]))
            with ProcessPoolExecutor(max_workers=n_workers) as ex:
                for r in ex.map(_make_job, jobs, chunksize=1):
                    results[r["tile"]] = r
                    if st is not None:
                        st.advance()
    t_make = time.perf_counter()
    written, unchanged_files = [], 0
    tiles_out, pieces_out, tile_seconds = {}, {}, {}
    for t in sorted(by_tile):
        if t in results:
            r = results[t]
            f = wdir / f"{t}.glb"
            if r["glb"]:
                if _write_if_changed(f, r["glb"]):
                    written.append(t)
                else:
                    unchanged_files += 1
            elif f.exists():
                f.unlink()
                written.append(t)
            tile_seconds[t] = r["seconds"]
            tiles_out[t] = {"hash": hashes[t], "bytes": len(r["glb"]),
                            "sha256": C.sha256_bytes(r["glb"]) if r["glb"] else "",
                            "pieces": len(by_tile[t]),
                            "triangles": sum(v.get("triangles", 0) for v in r["pieces"].values()),
                            "instances": sum(len(p["xforms"]) for v in r["pieces"].values()
                                             for p in v.get("parts", []))}
            recs = r["pieces"]
        else:
            tiles_out[t] = dict(prev_tiles[t])
            recs = {p.id: prev_pieces[p.id] for p in by_tile[t] if p.id in prev_pieces}
        for p in by_tile[t]:
            rec = dict(recs.get(p.id, {"triangles": 0, "empty": "missing"}))
            for k in ("hash", "tile", "replaces", "kind"):
                rec.pop(k, None)
            rec.update({"kind": p.kind, "hash": digests[p.id], "tile": t,
                        "replaces": list(p.replaces)})
            pieces_out[p.id] = rec
    stale = []
    if wdir.is_dir():
        for f in sorted(wdir.glob("t*.glb")):
            if f.stem not in by_tile:
                f.unlink()
                stale.append(f.stem)
    pdata, pinfo = parts_glb()
    parts_written = _write_if_changed(wdir / "parts.glb", pdata)
    manifest = {"version": WATER_VERSION, "assetgen": __version__, "code_sha256": code,
                "city": model.name, "model_sha256": model_sha,
                "parts": {"glb": "water/parts.glb", "sha256": C.sha256_bytes(pdata),
                          "bytes": len(pdata), "meshes": pinfo},
                "tiles": tiles_out, "pieces": pieces_out, "drop": drop,
                "bodies": {b.id: {"water": cx.water_kind(b), "kind": b.kind}
                           for b in cx.bodies}}
    man_text = json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    man_written = _write_if_changed(mf, man_text.encode("utf-8"))
    contrib = contribution(manifest, lib)
    con_text = json.dumps(contrib, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    con_written = _write_if_changed(out_dir / "unreal_contribution.water.json",
                                    con_text.encode("utf-8"))
    t_write = time.perf_counter()
    from .checks import report, report_text
    rep = report(model, cx, manifest, pieces, out_dir)
    rep["files"] = {"tiles_made": len(todo), "tiles_kept": len(keep),
                    "tiles_written": len(written), "tiles_same_bytes": unchanged_files,
                    "tiles_removed": len(stale), "parts_written": parts_written,
                    "manifest_written": man_written, "contribution_written": con_written,
                    "written": sorted(written)}
    rep["seconds"] = {"context": round(t_ctx - t0, 2), "gather": round(t_gather - t_ctx, 2),
                      "make": round(t_make - t_make0, 2), "write": round(t_write - t_make, 2),
                      "total": round(time.perf_counter() - t0, 2), "workers": n_workers,
                      "slowest_tiles": sorted(tile_seconds.items(),
                                              key=lambda kv: (-kv[1], kv[0]))[:5]}
    changed = bool(written or stale or parts_written or man_written or con_written)
    rep["files"]["report_written"] = False
    if report_always or changed or not (out_dir / "water_report.json").is_file():
        rep_text = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
        rep["files"]["report_written"] = _write_if_changed(out_dir / "water_report.json",
                                                           rep_text.encode("utf-8"))
        _write_if_changed(out_dir / "water_report.txt", report_text(rep).encode("utf-8"))
    return rep


# ---------------------------------------------------------------------------
# Unreal
# ---------------------------------------------------------------------------

UNDERWATER = {   # per water kind: the post-process tint (linear) and fog density per meter
    "sea": {"tint": [0.35, 0.62, 0.7], "fog": 0.06},
    "river": {"tint": [0.42, 0.55, 0.42], "fog": 0.14},
    "canal": {"tint": [0.4, 0.52, 0.45], "fog": 0.12},
    "ornamental": {"tint": [0.5, 0.72, 0.76], "fog": 0.05},
    "marsh": {"tint": [0.45, 0.45, 0.3], "fog": 0.3},
}


def contribution(manifest: dict, lib: dict | None = None) -> dict:
    """assetgen's Unreal entries for the water (AG0's format, `docs/unreal_export.md`, AG12):
    per body and tile a bed (Nanite, complex collision) and a surface (non-Nanite, a LOD
    chain, no collision: M16's swim volumes are the water), per bank a piece with its riprap
    stones as instanced parts, the drop of the blockout water objects no piece replaces, and
    per body the underwater post-process settings (a volume beside each of its swim boxes)."""
    entries = []
    slots = set()
    for pid in sorted(manifest["pieces"]):
        r = manifest["pieces"][pid]
        tile = r["tile"]
        glb = f"water/{tile}.glb"
        piv = [r["origin"][0], r["origin"][1], 0.0]
        if r.get("maker") == "body":
            body = pid.partition("@")[0]
            rep_s = [x for x in r["replaces"] if not x.startswith("city.bed.")]
            rep_b = [x for x in r["replaces"] if x.startswith("city.bed.")]
            bd = r.get("bed")
            if bd and bd["triangles"] > 0:
                entries.append({"key": bd["node"], "kind": "water.bed", "hash": r["hash"][:16],
                                "replaces": rep_b, "glb": glb, "node": bd["node"],
                                "asset": bd["node"].replace(".", "_"), "pivot": piv,
                                "yaw_deg": 0.0, "nanite": True, "triangles": bd["triangles"],
                                "slots": bd["slots"], "collision": {"complex": True},
                                "tile": tile, "ids": [body]})
                slots |= set(bd["slots"])
            lods = r.get("lods") or []
            if lods and lods[0]["triangles"] > 0:
                key = f"{body}.water.{tile}"
                entries.append({"key": key, "kind": r["kind"].replace("water.body.",
                                                                      "water.surface."),
                                "hash": r["hash"][:16], "replaces": rep_s, "glb": glb,
                                "node": lods[0]["node"], "asset": key.replace(".", "_"),
                                "pivot": piv, "yaw_deg": 0.0, "nanite": False,
                                "triangles": lods[0]["triangles"], "slots": lods[0]["slots"],
                                "collision": {"none": True}, "tile": tile, "ids": [body],
                                "lods": [{"node": lo["node"], "screen_size": lo["screen_size"],
                                          "triangles": lo["triangles"]} for lo in lods]})
                for lo in lods:
                    slots |= set(lo["slots"])
            continue
        if r.get("triangles", 0) > 0 or r.get("parts"):
            e = {"key": pid, "kind": r["kind"], "hash": r["hash"][:16],
                 "replaces": r["replaces"], "glb": glb, "node": pid,
                 "asset": pid.replace(".", "_"), "pivot": piv, "yaw_deg": 0.0,
                 "nanite": True, "triangles": r.get("triangles", 0),
                 "slots": r.get("slots", []), "collision": {"complex": True}, "tile": tile}
            slots |= set(r.get("slots", []))
            if r.get("parts"):
                e["parts"] = [{"kind": p["kind"], "glb": "water/parts.glb", "node": p["kind"],
                               "asset": p["kind"].replace(".", "_"),
                               "count": len(p["xforms"]),
                               "triangles": manifest["parts"]["meshes"][p["kind"]]["triangles"],
                               "collision": {"none": True},
                               "xforms": p["xforms"]} for p in r["parts"]]
                for p in r["parts"]:
                    slots |= set(manifest["parts"]["meshes"][p["kind"]]["slots"])
            entries.append(e)
    if manifest.get("drop"):
        entries.append({"key": DROP_KEY, "kind": "water.drop", "drop": True,
                        "replaces": list(manifest["drop"])})
    entries.sort(key=lambda e: e["key"])
    under = {b: {"water": v["water"], **UNDERWATER[v["water"]]}
             for b, v in sorted((manifest.get("bodies") or {}).items())}
    con = {"version": 1, "stage": "assetgen", "part": "water", "layer": 2,
           "masters": list(MT.MASTERS), "materials": MT.contribution_materials(slots),
           "entries": entries, "underwater": under}
    from ..materials import contrib as MC      # AG6: textures and the water parameters
    return MC.water(con, lib)


def default_workers() -> int:
    try:
        return max(1, min(MAX_WORKERS, int(os.environ.get("ASSETGEN_WORKERS", MAX_WORKERS))))
    except ValueError:
        return MAX_WORKERS


def outputs_digest(out_dir: Path) -> dict:
    """sha256 of what the stage wrote (tile packs, parts, contribution): the goldens'."""
    out_dir = Path(out_dir)
    wdir = out_dir / "water"
    tiles = {f.stem: C.sha256_bytes(f.read_bytes()) for f in sorted(wdir.glob("t*.glb"))}
    parts = C.sha256_bytes((wdir / "parts.glb").read_bytes())
    con = C.sha256_bytes((out_dir / "unreal_contribution.water.json").read_bytes())
    return {"tiles": tiles, "parts": parts, "contribution": con,
            "all": C.digest({"tiles": tiles, "parts": parts, "contribution": con})}
