"""The props stage: variant families for every M6 prop kind and plant species the city uses,
the exact props (cables, scaffolding, gates) and the signs per 256 m tile, the manifest,
assetgen's Unreal contributions for props and signs, and the report.

```
BUILD/assets/props/variants/<kind>.glb   a prop kind's variants, every style
BUILD/assets/props/plants/<species>.glb  a species' variants
BUILD/assets/props/tiles/<tile>.glb      the exact props of a tile, a node per kind
BUILD/assets/props/signs/<tile>.glb      the sign meshes of a tile (one per distinct sign)
BUILD/assets/props/manifest.json         families, tiles, per sign its node and text
BUILD/assets/unreal_contribution.props.json, unreal_contribution.signs.json
BUILD/assets/props_report.json, .txt     checks and stats
```

Placements: every prop picks its variant from its kind, its district's style and a hash of
its id; every plant from its species and a hash of its id, scaled to its crown and height.
Instances are grouped as M15 groups its prototypes (one blockout actor per kind and tile:
`prop.<kind>.<tile>`, `plant.<type>.<tile>`), so each group's entry replaces exactly that
actor. A tile pack is made again only when the hash of its inputs (the signs' and exact
props' inputs and the code) changes, and a file is written only when its bytes do: an
unchanged city writes nothing. Families and tiles are made in up to 4 worker processes; the
bytes do not depend on how many.
"""

from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .. import __version__
from .. import canon as C

PROPS_VERSION = 1
MAX_WORKERS = 4
TILE_M = 256.0

# budgets (scope 9 and 11: props and plants "a few million" unique triangles, instanced)
VARIANT_TRIANGLES = 3_000          # a prop variant
PLANT_TRIANGLES = 16_000           # a plant variant
SIGN_TRIANGLES = 6_000             # one sign (and LOD0 of a holo-ad)
CITY_UNIQUE_TRIANGLES = 10_000_000
TILE_INSTANCES = 15_000
CITY_INSTANCES = 300_000
CITY_DRAWN_TRIANGLES = 2_000_000_000   # instances times their variant's triangles


def tile_key(x: float, y: float) -> tuple[int, int]:
    return math.floor(x / TILE_M), math.floor(y / TILE_M)


def tile_name(ix: int, iy: int) -> str:
    """The blockout's tile names (`citygen/blockout.py`)."""
    return f"t{ix:+03d}{iy:+03d}"


def tile_of(x: float, y: float) -> str:
    return tile_name(*tile_key(x, y))


def tile_center(t: str) -> tuple[float, float]:
    ix, iy = int(t[1:4]), int(t[4:7])
    return (ix * TILE_M + TILE_M / 2.0, iy * TILE_M + TILE_M / 2.0)


def code_hash() -> str:
    here = Path(__file__).resolve().parent
    files = sorted(here.glob("*.py")) + [here.parent / f for f in
                                         ("gltf.py", "triangulate.py", "canon.py")] + \
        [here.parent / "streets" / "kit.py"]
    return C.digest([[f.name, C.sha256_bytes(f.read_bytes().replace(b"\r\n", b"\n"))]
                     for f in files])


# ---------------------------------------------------------------------------------------
# making (in workers)
# ---------------------------------------------------------------------------------------

def _family_job(args):
    from .packs import family_job
    return family_job(args)


def make_tile(job: dict) -> dict:
    """A tile's exact props and signs: the two packs' bytes and a record per node."""
    from . import signs as SG
    from . import variants as V
    from .packs import pack
    from .shapes import Mesh
    t0 = time.perf_counter()
    tile = job["tile"]
    cx, cy = tile_center(tile)
    exact = []
    for key, kind, items in job["exact"]:
        m = Mesh((cx, cy))
        for it in items:
            if kind == "overhead_cable":
                V.cable(m, it["prop"], it["style"])
            elif kind == "scaffolding":
                V.scaffold(m, it["prop"], it["wall"])
            elif kind == "gate":
                V.gate(m, it["prop"], it["style"], _gate_words(it))
        exact.append((key, m, (int(round(cx * 1000)), int(round(cy * 1000)), 0)))
    pdata, pinfo = pack(exact, f"tile {tile}") if exact else (b"", {})
    meshes, lods_out = [], {}
    seen = set()
    for node, inp, extra_name in job["signs"]:
        if node in seen:
            continue
        seen.add(node)
        m, extra = SG.make(inp)
        meshes.append((node, m, None))
        for ex in extra:
            names = []
            for k, lod in enumerate(ex["lods"]):
                nm = f"{extra_name}{ex['suffix']}.lod{k}"
                meshes.append((nm, lod, None))
                names.append(nm)
            lods_out[node] = {"suffix": ex["suffix"], "nodes": names, "screen": ex["screen"],
                              "nanite": ex["nanite"]}
    sdata, sinfo = pack(meshes, f"signs {tile}") if meshes else (b"", {})
    return {"tile": tile, "props_glb": pdata, "props_nodes": pinfo, "signs_glb": sdata,
            "signs_nodes": sinfo, "lods": lods_out,
            "seconds": round(time.perf_counter() - t0, 3)}


def _gate_words(it: dict):
    """The market's name on a gate's lintel, both faces, in neon (a builder for
    `variants.gate`)."""
    from . import materials as MT
    from . import signs as SG
    name = (it["prop"].get("attrs") or {}).get("name") or "MARKET"
    col = MT.neon_slot(it["color"])

    def words(m, P, W):
        strokes, wh = SG.layout(name.upper(), "latin", False)
        u = min((W - 1.6) / wh[0], 0.6 / wh[1])
        if u <= 0:
            return
        # the board between the beams, and the name on both faces
        q = [P(-W / 2.0 + 0.6, -0.12, 4.35), P(W / 2.0 - 0.6, -0.12, 4.35),
             P(W / 2.0 - 0.6, -0.12, 5.05), P(-W / 2.0 + 0.6, -0.12, 5.05)]
        from .shapes import quad_out
        a = (P(1.0, 0.0, 0.0)[0] - P(0.0, 0.0, 0.0)[0], P(1.0, 0.0, 0.0)[1] - P(0.0, 0.0, 0.0)[1])
        nrm = (-a[1], a[0], 0.0)
        quad_out(m, "sign.back", *q, (-nrm[0], -nrm[1], 0.0))
        q2 = [P(-W / 2.0 + 0.6, 0.12, 4.35), P(W / 2.0 - 0.6, 0.12, 4.35),
              P(W / 2.0 - 0.6, 0.12, 5.05), P(-W / 2.0 + 0.6, 0.12, 5.05)]
        quad_out(m, "sign.back", *q2, nrm)
        for side in (-1.0, 1.0):
            o = P(-side * wh[0] * u / 2.0, side * 0.14, 4.7 - wh[1] * u / 2.0)
            right = (a[0] * -side, a[1] * -side, 0.0)
            SG.put_text(m, col, strokes, o, right, (0.0, 0.0, 1.0), u, "tube",
                        (nrm[0] * side, nrm[1] * side, 0.0))
    return words


def _run(fn, jobs, nw):
    if nw <= 1 or len(jobs) <= 1:
        return [fn(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=nw) as ex:
        return list(ex.map(fn, jobs, chunksize=1))


# ---------------------------------------------------------------------------------------
# the stage
# ---------------------------------------------------------------------------------------

def _write_if_changed(path: Path, data: bytes) -> bool:
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _dump(doc) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def _file_ok(path: Path, info: dict | None) -> bool:
    if not info:
        return False
    if info.get("bytes", 0) == 0:
        return not path.exists()
    return path.is_file() and path.stat().st_size == info["bytes"] and \
        C.sha256_bytes(path.read_bytes()) == info["sha256"]


def default_workers() -> int:
    try:
        return max(1, min(MAX_WORKERS, int(os.environ.get("ASSETGEN_WORKERS", MAX_WORKERS))))
    except ValueError:
        return MAX_WORKERS


def build(model, model_sha: str, out_dir: Path, spec=None, briefs: dict | None = None,
          workers: int | None = None, force: bool = False,
          report_always: bool = True, lib: dict | None = None) -> dict:
    """Make the props, plants and signs of a city into out_dir (BUILD/assets); the report.
    `briefs` (by building id) give the facade props their gaps to the wall; without them
    they are read from out_dir/briefs.json, or made. `report_always=False` (`assetgen
    build`) writes the report only when another file changed or it is missing. With AG6's
    library `lib` the contributions' materials are textured (`materials/contrib.props`) and
    the sign faces show the city's sign pages (out_dir/signs.json, AG6's signage, made
    before this stage)."""
    from . import gather as GA
    t0 = time.perf_counter()
    out_dir = Path(out_dir)
    pdir = out_dir / "props"
    if briefs is None:
        briefs = _load_briefs(model, model_sha, out_dir, spec)
    g = GA.gather(model, spec, briefs, out_dir, pages=lib is not None)
    t_gather = time.perf_counter()
    code = code_hash()
    nw_max = max(1, min(workers or MAX_WORKERS, MAX_WORKERS))
    # -- the families
    prev = {}
    mf = pdir / "manifest.json"
    if mf.is_file() and not force:
        try:
            prev = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
    if prev.get("version") != PROPS_VERSION or prev.get("code_sha256") != code:
        prev_f, prev_t = {}, {}
    else:
        prev_f, prev_t = prev.get("families", {}), prev.get("tiles", {})
    fam_jobs, families, written = [], {}, []
    for what, name in g.families:
        sub = "variants" if what == "prop" else "plants"
        rel = f"props/{sub}/{name}.glb"
        key = f"{what}.{name}"
        old = prev_f.get(key)
        if old and _file_ok(out_dir / rel, old):
            families[key] = old
        else:
            fam_jobs.append((what, name))
    fam_jobs.sort(key=lambda j: (j[0] != "plant", j[1]))
    for r in _run(_family_job, fam_jobs, min(nw_max, len(fam_jobs)) if fam_jobs else 1):
        sub = "variants" if r["what"] == "prop" else "plants"
        rel = f"props/{sub}/{r['name']}.glb"
        if _write_if_changed(out_dir / rel, r["glb"]):
            written.append(rel)
        families[f"{r['what']}.{r['name']}"] = {
            "glb": rel, "bytes": len(r["glb"]), "sha256": C.sha256_bytes(r["glb"]),
            "meshes": r["meshes"]}
    t_fam = time.perf_counter()
    # -- the tiles (exact props and signs)
    tiles = sorted(set(g.exact) | set(g.signs))
    hashes = {t: C.digest({"v": PROPS_VERSION, "code": code,
                           "exact": [[k, kind, [it["digest"] for it in items]]
                                     for k, kind, items in g.exact.get(t, [])],
                           "signs": [[s["id"], s["digest"]] for s in g.signs.get(t, [])]})
              for t in tiles}
    jobs, tiles_out = [], {}
    for t in tiles:
        old = prev_t.get(t)
        ok = old is not None and old.get("hash") == hashes[t] and \
            _file_ok(out_dir / f"props/tiles/{t}.glb", old.get("props")) and \
            _file_ok(out_dir / f"props/signs/{t}.glb", old.get("signs"))
        if ok:
            tiles_out[t] = old
            continue
        jobs.append({"tile": t, "exact": g.exact.get(t, []),
                     "signs": [(s["node"], s["inputs"], s["extra_name"])
                               for s in g.signs.get(t, [])]})
    jobs.sort(key=lambda j: (-(len(j["signs"]) + 4 * len(j["exact"])), j["tile"]))
    tile_secs = {}
    for r in _run(make_tile, jobs, min(nw_max, len(jobs)) if jobs else 1):
        t = r["tile"]
        rec = {"hash": hashes[t]}
        for part, data in (("props", r["props_glb"]), ("signs", r["signs_glb"])):
            path = out_dir / f"props/{'tiles' if part == 'props' else 'signs'}/{t}.glb"
            if data:
                if _write_if_changed(path, data):
                    written.append(str(path.relative_to(out_dir)))
            elif path.exists():
                path.unlink()
                written.append(str(path.relative_to(out_dir)))
            rec[part] = {"bytes": len(data), "sha256": C.sha256_bytes(data) if data else ""}
        rec["props_nodes"] = r["props_nodes"]
        rec["signs_nodes"] = r["signs_nodes"]
        rec["lods"] = r["lods"]
        tiles_out[t] = rec
        tile_secs[t] = r["seconds"]
    removed = []
    for sub in ("tiles", "signs"):
        d = pdir / sub
        if d.is_dir():
            for f in sorted(d.glob("t*.glb")):
                if f.stem not in tiles_out or not tiles_out[f.stem].get(
                        "props" if sub == "tiles" else "signs", {}).get("bytes"):
                    f.unlink()
                    removed.append(f"props/{sub}/{f.name}")
    for sub, what in (("variants", "prop"), ("plants", "plant")):
        d = pdir / sub
        if d.is_dir():
            for f in sorted(d.glob("*.glb")):
                if f"{what}.{f.stem}" not in families:
                    f.unlink()
                    removed.append(f"props/{sub}/{f.name}")
    t_tiles = time.perf_counter()
    manifest = {"version": PROPS_VERSION, "assetgen": __version__, "code_sha256": code,
                "city": model.name, "model_sha256": model_sha,
                "families": {k: families[k] for k in sorted(families)},
                "tiles": {t: tiles_out[t] for t in sorted(tiles_out)},
                "signs": {s["id"]: {"node": s["node"], "tile": t, "kind": s["inputs"]["kind"],
                                    "look": s["inputs"].get("look"),
                                    "text": s["inputs"].get("text"),
                                    "script": s["inputs"].get("script", "latin")}
                          for t in sorted(g.signs) for s in g.signs[t]},
                "placements": g.stats}
    man_written = _write_if_changed(mf, _dump(manifest))
    from ..materials import contrib as AC6
    from . import contribution as CB
    signs_doc = None
    if lib is not None and (out_dir / "signs.json").is_file():
        signs_doc = json.loads((out_dir / "signs.json").read_text(encoding="utf-8"))
    con_p = AC6.props(CB.props(manifest, g), lib)
    con_s = AC6.props(CB.signs(manifest, g), lib, signs_doc)
    p_written = _write_if_changed(out_dir / "unreal_contribution.props.json", _dump(con_p))
    s_written = _write_if_changed(out_dir / "unreal_contribution.signs.json", _dump(con_s))
    t_write = time.perf_counter()
    from .checks import report, report_text
    rep = report(model, g, manifest, con_p, con_s)
    rep["files"] = {"families_made": len(fam_jobs), "tiles_made": len(jobs),
                    "tiles_kept": len(tiles) - len(jobs), "written": sorted(written),
                    "removed": removed, "manifest_written": man_written,
                    "contribution_written": [p_written, s_written]}
    rep["seconds"] = {"gather": round(t_gather - t0, 2), "families": round(t_fam - t_gather, 2),
                      "tiles": round(t_tiles - t_fam, 2), "write": round(t_write - t_tiles, 2),
                      "total": round(time.perf_counter() - t0, 2), "workers": nw_max,
                      "slowest_tiles": sorted(tile_secs.items(),
                                              key=lambda kv: (-kv[1], kv[0]))[:5]}
    changed = bool(written or removed or man_written or p_written or s_written)
    rep["files"]["report_written"] = False
    if report_always or changed or not (out_dir / "props_report.json").is_file():
        rep["files"]["report_written"] = _write_if_changed(out_dir / "props_report.json",
                                                           _dump(rep))
        _write_if_changed(out_dir / "props_report.txt", report_text(rep).encode("utf-8"))
    return rep


def _load_briefs(model, model_sha: str, out_dir: Path, spec) -> dict:
    """The briefs of the build when they are of this model (briefs.json), else made."""
    p = out_dir / "briefs.json"
    if p.is_file():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if doc.get("model_sha256") == model_sha:
                return doc["briefs"]
        except (OSError, ValueError, KeyError):
            pass
    from .. import brief as B
    return B.build_briefs(model, spec, None)["briefs"]


def outputs_digest(out_dir: Path) -> dict:
    """sha256 of what the stage wrote (packs and contributions; not the manifest or the
    report): the goldens' measure."""
    out_dir = Path(out_dir)
    files = sorted(p for p in (out_dir / "props").rglob("*.glb"))
    d = {str(p.relative_to(out_dir)): C.sha256_bytes(p.read_bytes()) for p in files}
    for n in ("unreal_contribution.props.json", "unreal_contribution.signs.json"):
        d[n] = C.sha256_bytes((out_dir / n).read_bytes())
    return {"files": d, "all": C.digest(d)}
