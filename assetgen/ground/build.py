"""The ground stage (`assetgen ground BUILD`; the last stage of `assetgen build`, after AG8's
props and before AG6's materials): every piece of M16's open land drawn and its grass
scattered, per 256 m tile.

```
BUILD/assets/ground/clumps.glb        every clump variant the city uses (a node each)
BUILD/assets/ground/tiles/<tile>.glb  the tile's ground (one node, a primitive per surface)
BUILD/assets/ground/masks/<tile>.png  the tile's mask (wear, shade, edge, moisture)
BUILD/assets/ground/grass/<tile>.json the tile's clumps: per variant node its transforms
                                      [x, y, z, yaw, sx, sy, sz] from the tile's middle
BUILD/assets/ground/manifest.json     clumps, tiles (hashes, files, counts), placements
BUILD/assets/unreal_contribution.ground.json
BUILD/assets/ground_report.json, .txt checks and stats
BUILD/assets/ground/preview.png       the city's ground from above (2 m a pixel)
```

A tile is made again only when its job's hash (its inputs and the code) changes, and a file
is written only when its bytes do: an unchanged city writes nothing, a regenerated district
rewrites only the tiles its pieces, decks, trees, water or shade reach. Tiles are made in up
to 4 worker processes; the bytes do not depend on how many.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .. import __version__
from .. import canon as C
from . import kinds as K

GROUND_VERSION = 1
MAX_WORKERS = 4


def code_hash() -> str:
    here = Path(__file__).resolve().parent
    root = here.parent
    files = sorted(here.glob("*.py")) + [root / f for f in
                                         ("gltf.py", "triangulate.py", "canon.py")] + \
        [root / "props" / "trees.py", root / "props" / "styles.py",
         root / "props" / "shapes.py", root / "streets" / "kit.py"]
    return C.digest([[f.name, C.sha256_bytes(f.read_bytes().replace(b"\r\n", b"\n"))]
                     for f in files])


def default_workers() -> int:
    try:
        return max(1, min(MAX_WORKERS, int(os.environ.get("ASSETGEN_WORKERS", MAX_WORKERS))))
    except ValueError:
        return MAX_WORKERS


def _write_if_changed(path: Path, data: bytes) -> bool:
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _dump(doc) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def _compact(doc) -> bytes:
    return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _file_ok(path: Path, info: dict | None) -> bool:
    if not info:
        return False
    if info.get("bytes", 0) == 0:
        return not path.exists()
    return path.is_file() and path.stat().st_size == info["bytes"] and \
        C.sha256_bytes(path.read_bytes()) == info["sha256"]


def _rec(data: bytes) -> dict:
    return {"bytes": len(data), "sha256": C.sha256_bytes(data) if data else ""}


def clumps_glb(families: list[tuple[str, str | None]], palettes: dict) -> tuple[bytes, dict]:
    """The clump pack: every variant of every family, at the origin."""
    from ..gltf import Gltf
    from . import clumps as CL
    g = Gltf(generator=f"assetgen {__version__} AG13 clumps")
    made = []
    slots = set()
    for kind, pk in families:
        for k in range(K.CLUMPS[kind][0]):
            c = CL.make(kind, k, palettes.get(pk) if pk else None)
            made.append((CL.node(CL.family(kind, pk), k), kind, c))
            slots |= set(c.slots)
    mats = {}
    for s in sorted(slots):
        col, _ = CL.slot_colors(s)
        rgb = [int(col[1 + 2 * k:3 + 2 * k], 16) / 255.0 for k in range(3)]
        mats[s] = g.material(s, (*rgb, 1.0), 0.0, CL.ROUGHNESS,
                             extras={"slot": s, "master": "grass"})
    info = {}
    for name, kind, c in made:
        prims = c.primitives(mats)
        mi = g.mesh(name, prims)
        g.node(name, mi, root=True, extras={"clump": kind})
        info[name] = {"kind": kind, "triangles": sum(len(p.indices) // 3 for p in prims),
                      "slots": sorted(c.slots), "bounds": c.bounds()}
    return g.to_glb(), info


def _run(fn, jobs, nw):
    if nw <= 1 or len(jobs) <= 1:
        for j in jobs:
            yield fn(j)
        return
    with ProcessPoolExecutor(max_workers=nw) as ex:
        yield from ex.map(fn, jobs, chunksize=1)


def build(model, model_sha: str, out_dir: Path, spec_doc: dict | None = None,
          workers: int | None = None, force: bool = False, report_always: bool = True,
          lib: dict | None = None, progress=None) -> dict:
    """Make the ground and grass of a city into out_dir (BUILD/assets); the report.
    `report_always=False` (`assetgen build`) writes the report only when another file
    changed or it is missing. With AG6's library `lib` the contribution's ground materials
    are textured. `progress`: a stage (`assetgen/progress.py`) advanced per tile."""
    from . import gather as GA
    from .tile import make_tile
    t0 = time.perf_counter()
    out_dir = Path(out_dir)
    gdir = out_dir / "ground"
    g = GA.gather(model, spec_doc)
    t_gather = time.perf_counter()
    code = code_hash()
    nw = max(1, min(workers or MAX_WORKERS, MAX_WORKERS))
    prev = {}
    mf = gdir / "manifest.json"
    if mf.is_file() and not force:
        try:
            prev = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
    fresh = prev.get("version") == GROUND_VERSION and prev.get("code_sha256") == code
    prev_t = prev.get("tiles", {}) if fresh else {}
    written, removed = [], []
    # -- the clumps
    fam_key = C.digest([code, g.families, g.palettes])
    old_c = prev.get("clumps_file") if fresh else None
    if old_c and old_c.get("key") == fam_key and _file_ok(gdir / "clumps.glb", old_c) and \
            prev.get("clumps"):
        clumps, cfile = prev["clumps"], old_c
    else:
        data, clumps = clumps_glb(g.families, g.palettes) if g.tiles else (b"", {})
        if data:
            if _write_if_changed(gdir / "clumps.glb", data):
                written.append("ground/clumps.glb")
        elif (gdir / "clumps.glb").exists():
            (gdir / "clumps.glb").unlink()
            removed.append("ground/clumps.glb")
        cfile = {**_rec(data), "key": fam_key}
    t_clumps = time.perf_counter()
    # -- the tiles
    hashes = {t: C.digest({"v": GROUND_VERSION, "code": code, "job": j})
              for t, j in g.tiles.items()}
    jobs, tiles_out = [], {}
    for t in sorted(g.tiles):
        old = prev_t.get(t)
        ok = old is not None and old.get("hash") == hashes[t] and \
            _file_ok(gdir / "tiles" / f"{t}.glb", old.get("glb")) and \
            _file_ok(gdir / "masks" / f"{t}.png", old.get("mask")) and \
            _file_ok(gdir / "grass" / f"{t}.json", old.get("grass"))
        if ok:
            tiles_out[t] = old
        else:
            jobs.append(g.tiles[t])
    jobs.sort(key=lambda j: (-sum(len(p["rings"][0]) for p in j["pieces"]), j["tile"]))
    tile_secs = {}
    st = progress.stage("ground tiles", total=len(jobs)) if progress is not None else None
    ctx = st.__enter__() if st is not None else None
    try:
        for r in _run(make_tile, jobs, min(nw, len(jobs)) if jobs else 1):
            t = r["tile"]
            cx, cy = [(a + b) / 2.0 for a, b in zip(GA.tile_box(t)[:2], GA.tile_box(t)[2:])]
            grass = _compact({"tile": t, "pivot": [cx, cy, 0.0], "nodes": r["instances"]}) \
                if r["instances"] else b""
            for sub, data, ext in (("tiles", r["glb"], "glb"), ("masks", r["mask"] if r["glb"]
                                                               else b"", "png"),
                                   ("grass", grass, "json")):
                path = gdir / sub / f"{t}.{ext}"
                if data:
                    if _write_if_changed(path, data):
                        written.append(f"ground/{sub}/{t}.{ext}")
                elif path.exists():
                    path.unlink()
                    removed.append(f"ground/{sub}/{t}.{ext}")
            tiles_out[t] = {"hash": hashes[t], "glb": _rec(r["glb"]),
                            "mask": {**_rec(r["mask"] if r["glb"] else b""),
                                     "pixels_sha256": r["mask_pixels_sha256"]
                                     if r["glb"] else ""},
                            "grass": _rec(grass), "node": r["node"],
                            "instances": {k: len(v) for k, v in r["instances"].items()},
                            "scatter": r["scatter"], "areas": r["areas"],
                            "failed": r["failed"], "surfaces": r["surfaces"]}
            tile_secs[t] = r["seconds"]
            if ctx is not None:
                ctx.advance()
    finally:
        if st is not None:
            st.__exit__(None, None, None)
    for sub, ext in (("tiles", "glb"), ("masks", "png"), ("grass", "json")):
        d = gdir / sub
        if d.is_dir():
            for f in sorted(d.glob(f"t*.{ext}")):
                rec = tiles_out.get(f.stem)
                key = {"tiles": "glb", "masks": "mask", "grass": "grass"}[sub]
                if rec is None or not rec.get(key, {}).get("bytes"):
                    f.unlink()
                    removed.append(f"ground/{sub}/{f.name}")
    t_tiles = time.perf_counter()
    manifest = {"version": GROUND_VERSION, "assetgen": __version__, "code_sha256": code,
                "city": model.name, "model_sha256": model_sha,
                "clumps_file": cfile, "clumps": clumps, "palettes": g.palettes,
                "tiles": {t: tiles_out[t] for t in sorted(tiles_out)},
                "keys": g.keys, "stats": g.stats}
    man_written = _write_if_changed(mf, _dump(manifest))
    from . import contribution as CB
    con = CB.contribution(manifest, lib)
    c_written = _write_if_changed(out_dir / "unreal_contribution.ground.json", _dump(con))
    t_write = time.perf_counter()
    from .checks import report, report_text
    rep = report(model, manifest, con, out_dir)
    pv_written = False
    if written or removed or man_written or not (gdir / "preview.png").is_file():
        from .preview import preview
        pv_written = preview(model, manifest, out_dir, gdir / "preview.png")
    rep["files"] = {"tiles_made": len(jobs), "tiles_kept": len(g.tiles) - len(jobs),
                    "written": sorted(written), "removed": sorted(removed),
                    "manifest_written": man_written, "contribution_written": c_written,
                    "preview_written": pv_written}
    rep["seconds"] = {"gather": round(t_gather - t0, 2), "clumps": round(t_clumps - t_gather, 2),
                      "tiles": round(t_tiles - t_clumps, 2),
                      "write": round(t_write - t_tiles, 2),
                      "total": round(time.perf_counter() - t0, 2), "workers": nw,
                      "slowest_tiles": sorted(tile_secs.items(),
                                              key=lambda kv: (-kv[1], kv[0]))[:5]}
    changed = bool(written or removed or man_written or c_written)
    rep["files"]["report_written"] = False
    if report_always or changed or not (out_dir / "ground_report.json").is_file():
        rep["files"]["report_written"] = _write_if_changed(out_dir / "ground_report.json",
                                                           _dump(rep))
        _write_if_changed(out_dir / "ground_report.txt", report_text(rep).encode("utf-8"))
    return rep


def outputs_digest(out_dir: Path) -> dict:
    """sha256 of what the stage wrote (packs, grass, mask pixels and the contribution; not
    the manifest, report or preview): the goldens' measure."""
    out_dir = Path(out_dir)
    gdir = out_dir / "ground"
    d = {}
    for p in sorted(gdir.rglob("*")):
        if p.is_file() and p.suffix in (".glb", ".json") and p.name != "manifest.json":
            d[p.relative_to(out_dir).as_posix()] = C.sha256_bytes(p.read_bytes())
    man = json.loads((gdir / "manifest.json").read_text(encoding="utf-8"))
    for t, r in sorted(man["tiles"].items()):
        if r["mask"].get("pixels_sha256"):
            d[f"ground/masks/{t}.png#pixels"] = r["mask"]["pixels_sha256"]
    n = "unreal_contribution.ground.json"
    d[n] = C.sha256_bytes((out_dir / n).read_bytes())
    return {"files": d, "all": C.digest(d)}
