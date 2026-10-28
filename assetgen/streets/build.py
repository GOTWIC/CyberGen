"""The street stage: gather every street piece of a city, make the tiles whose pieces
changed, write one glTF pack per 256 m tile, the parts pack, the streets manifest, assetgen's
Unreal contribution for streets and the report.

```
BUILD/assets/streets/<tile>.glb        a node per piece, named by its citygen id
BUILD/assets/streets/parts.glb         instanced parts (containers)
BUILD/assets/streets/manifest.json     per tile: hash, file sha256; per piece: kind, hash,
                                       tile, replaces, triangles, slots, bounds, parts
BUILD/assets/unreal_contribution.streets.json
BUILD/assets/streets_report.json, .txt checks and stats
```

A tile is made again only when the hash of its pieces (ids, input hashes, generator
versions) differs from the last manifest or its file is gone or changed; an unchanged city
does no work and writes no file. Tiles are made in up to 4 worker processes; the result
does not depend on how many.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .. import __version__
from .. import canon as C
from ..gltf import Gltf
from . import materials as MT
from . import pieces as PC
from .ctx import Ctx
from .kit import check

STREETS_VERSION = 1
MAX_WORKERS = 4
TILE_TRIANGLE_BUDGET = 2_500_000
CITY_TRIANGLE_BUDGET = 20_000_000

# collections whose every entity is a street element (scope 5.3), and those covered through
# other pieces
COVERED = ("road_segments", "junctions", "crosswalks", "sidewalks", "bridges", "structures",
           "tunnels", "quays", "waterways", "site_elements")


def _import_makers():
    from . import roads, sites, structures, transit, walks, water  # noqa: F401


def gather(cx: Ctx) -> list[PC.Piece]:
    from . import roads, sites, structures, transit, walks, water
    m = cx.m
    out: list[PC.Piece] = []
    for s in m.road_segments:
        out.append(roads.gather(cx, s))
    for j in m.junctions:
        out.append(walks.gather_junction(cx, j))
    for c in m.crosswalks:
        out.append(walks.gather_crosswalk(cx, c))
    for w in m.sidewalks:
        out.append(walks.gather_sidewalk(cx, w))
    for b in m.bridges:
        out.append(structures.gather_bridge(cx, b))
    for st in m.structures:
        mk = transit.maker_for(st)
        if mk == "column":
            out.append(structures.gather_column(cx, st))
        elif mk == "trench":
            out.append(structures.gather_trench(cx, st))
        elif mk == "portal":
            out.append(structures.gather_portal(cx, st))
        elif mk == "vent":
            out.append(structures.gather_vent(cx, st))
        else:
            out.append(transit.gather_structure(cx, st, mk))
    for t in m.tunnels:
        out.append(structures.gather_tunnel(cx, t))
    for q in m.quays:
        out.append(water.gather_quay(cx, q))
    for w in m.waterways:
        out.append(water.gather_canal(cx, w))
    for e in m.site_elements:
        out.append(sites.gather_site(cx, e))
    return out


def code_hash() -> str:
    """sha256 of the code that makes the packs (this package, the mesh writer and the
    triangulator), so a changed generator remakes its tiles even where no version was
    bumped."""
    here = Path(__file__).resolve().parent
    files = sorted(here.glob("*.py")) + [here.parent / "gltf.py", here.parent / "triangulate.py",
                                         here.parent / "canon.py"]
    h = []
    for f in files:
        h.append([f.name, C.sha256_bytes(f.read_bytes().replace(b"\r\n", b"\n"))])
    return C.digest(h)


def tile_hash(pieces: list[PC.Piece], digests: dict[str, str], code: str) -> str:
    return C.digest({"v": STREETS_VERSION, "code": code,
                     "pieces": [[p.id, digests[p.id]] for p in sorted(pieces, key=lambda p: p.id)]})


# ---------------------------------------------------------------------------
# Making a tile (in a worker)
# ---------------------------------------------------------------------------

def _mesh_record(mesh, origin) -> dict:
    lo, hi = mesh.bounds_mm()
    if lo[0] is None:
        return {"triangles": 0}
    return {"triangles": mesh.triangles, "slots": sorted(mesh.slots),
            "bounds": [[C.m(origin[0] + lo[0] / 1000.0), C.m(origin[1] + lo[1] / 1000.0),
                        C.m(lo[2] / 1000.0)],
                       [C.m(origin[0] + hi[0] / 1000.0), C.m(origin[1] + hi[1] / 1000.0),
                        C.m(hi[2] / 1000.0)]],
            "checks": {k: v for k, v in check(mesh.slots).items() if v}}


def make_tile(tile: str, pieces: list[dict]) -> dict:
    """Make every piece of a tile; the tile's glTF bytes and a record per piece."""
    _import_makers()
    t0 = time.perf_counter()
    made = []
    for pd in sorted(pieces, key=lambda p: p["id"]):
        fn = PC.MAKERS[pd["maker"]]
        out = fn(pd["inputs"])
        made.append((pd, out))
    slots = set()
    for pd, out in made:
        if out.mesh is not None and out.mesh.triangles:
            slots |= set(out.mesh.slots)
        for ex in out.extra:
            for lod in ex["lods"]:
                slots |= set(lod.slots)
    g = Gltf(generator=f"assetgen {__version__} streets")
    mats = MT.gltf_materials(g, slots)
    for name, i in mats.items():
        if MT.SLOTS[name][0] == "translucent":
            g.materials[i]["alphaMode"] = "BLEND"
            g.materials[i]["doubleSided"] = True
            g.materials[i]["pbrMetallicRoughness"]["baseColorFactor"][3] = 0.35
    recs = {}
    for pd, out in made:
        o = pd["inputs"]["origin"]
        trans = (int(round(o[0] * 1000)), int(round(o[1] * 1000)), 0)
        rec = {"kind": pd["kind"], "maker": pd["maker"], "origin": [C.m2(o[0]), C.m2(o[1])]}
        if out.mesh is not None and out.mesh.triangles:
            mi = g.mesh(pd["id"], out.mesh.finish(mats))
            g.node(pd["id"], mi, translation=trans, root=True, extras={"kind": pd["kind"]})
            rec.update(_mesh_record(out.mesh, o))
            rec["dropped"] = out.mesh.dropped
        else:
            rec["triangles"] = 0
            rec["empty"] = out.empty or "no mesh"
        rec["nanite"] = out.nanite
        extras = []
        for ex in out.extra:
            lods = []
            for k, lod in enumerate(ex["lods"]):
                name = f"{pd['id']}{ex['suffix']}.lod{k}"
                mi = g.mesh(name, lod.finish(mats))
                g.node(name, mi, translation=trans, root=True,
                       extras={"kind": pd["kind"] + ex["suffix"], "lod": k})
                r = _mesh_record(lod, o)
                lods.append({"node": name, "triangles": r["triangles"],
                             "screen_size": ex["screen"][k], "slots": r.get("slots", []),
                             "checks": r.get("checks", {})})
            extras.append({"suffix": ex["suffix"], "nanite": ex["nanite"], "lods": lods})
        if extras:
            rec["extra"] = extras
        if out.parts:
            rec["parts"] = out.parts
        if out.notes:
            rec["notes"] = out.notes
        recs[pd["id"]] = rec
    data = g.to_glb() if g.nodes else b""
    return {"tile": tile, "glb": data, "pieces": recs,
            "seconds": round(time.perf_counter() - t0, 3)}


def _make_job(args):
    tile, pieces = args
    return make_tile(tile, pieces)


def parts_glb() -> tuple[bytes, dict]:
    from .sites import LIVERIES, container_part
    g = Gltf(generator=f"assetgen {__version__} streets parts")
    meshes = [(f"part.container.c{k}", container_part(k)) for k in range(LIVERIES)]
    slots = set()
    for _, m in meshes:
        slots |= set(m.slots)
    mats = MT.gltf_materials(g, slots)
    info = {}
    for name, m in meshes:
        mi = g.mesh(name, m.finish(mats))
        g.node(name, mi, root=True)
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


def _write_text(path: Path, text: str) -> bool:
    return _write_if_changed(path, text.encode("utf-8"))


def build(model, model_sha: str, out_dir: Path, spec=None, workers: int | None = None,
          force: bool = False) -> dict:
    """Make the street packs of a city into out_dir (BUILD/assets); returns the report."""
    t0 = time.perf_counter()
    out_dir = Path(out_dir)
    sdir = out_dir / "streets"
    cx = Ctx(model, spec)
    t_ctx = time.perf_counter()
    pieces = gather(cx)
    t_gather = time.perf_counter()
    ids = {}
    for p in pieces:
        if p.id in ids:
            raise ValueError(f"two street pieces with id {p.id}")
        ids[p.id] = p
    digests = {p.id: p.digest() for p in pieces}
    by_tile: dict[str, list[PC.Piece]] = {}
    for p in pieces:
        by_tile.setdefault(p.tile, []).append(p)
    code = code_hash()
    hashes = {t: tile_hash(ps, digests, code) for t, ps in by_tile.items()}
    prev = {}
    mf = sdir / "manifest.json"
    if mf.is_file() and not force:
        try:
            prev = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
    prev_tiles = prev.get("tiles", {}) if prev.get("version") == STREETS_VERSION else {}
    prev_pieces = prev.get("pieces", {}) if prev_tiles else {}
    todo, keep = [], []
    for t in sorted(by_tile):
        pt = prev_tiles.get(t)
        f = sdir / f"{t}.glb"
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
    if n_workers == 1 or len(jobs) <= 1:
        for j in jobs:
            r = _make_job(j)
            results[r["tile"]] = r
    else:
        # big tiles first, so the workers finish together
        jobs.sort(key=lambda j: (-len(j[1]), j[0]))
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            for r in ex.map(_make_job, jobs, chunksize=1):
                results[r["tile"]] = r
    t_make = time.perf_counter()
    written, unchanged_files = [], 0
    tiles_out, pieces_out, tile_seconds = {}, {}, {}
    for t in sorted(by_tile):
        if t in results:
            r = results[t]
            f = sdir / f"{t}.glb"
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
                            "triangles": sum(v["triangles"] + sum(
                                ex["lods"][0]["triangles"] for ex in v.get("extra", []))
                                for v in r["pieces"].values())}
            recs = r["pieces"]
        else:
            tiles_out[t] = dict(prev_tiles[t])
            recs = {p.id: prev_pieces[p.id] for p in by_tile[t] if p.id in prev_pieces}
        for p in by_tile[t]:
            rec = dict(recs.get(p.id, {"triangles": 0, "empty": "missing"}))
            for k in ("hash", "tile", "replaces", "kind", "covers"):
                rec.pop(k, None)
            rec.update({"kind": p.kind, "hash": digests[p.id], "tile": t,
                        "replaces": list(p.replaces)})
            if p.covers:
                rec["covers"] = list(p.covers)
            pieces_out[p.id] = rec
    # tiles no longer in the city
    stale = []
    if sdir.is_dir():
        for f in sorted(sdir.glob("t*.glb")):
            if f.stem not in by_tile:
                f.unlink()
                stale.append(f.stem)
    pdata, pinfo = parts_glb()
    parts_written = _write_if_changed(sdir / "parts.glb", pdata)
    manifest = {"version": STREETS_VERSION, "assetgen": __version__, "code_sha256": code,
                "city": model.name, "model_sha256": model_sha,
                "parts": {"glb": "streets/parts.glb", "sha256": C.sha256_bytes(pdata),
                          "bytes": len(pdata), "meshes": pinfo},
                "tiles": tiles_out, "pieces": pieces_out}
    man_text = json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    man_written = _write_text(mf, man_text)
    contrib = contribution(manifest)
    con_text = json.dumps(contrib, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    con_written = _write_text(out_dir / "unreal_contribution.streets.json", con_text)
    t_write = time.perf_counter()
    from .checks import report
    rep = report(model, cx, manifest, pieces)
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
    rep_text = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    from .checks import report_text
    # the report carries timings: it is rewritten on every run (the packs, the manifest and
    # the contribution are not, when nothing changed)
    _write_text(out_dir / "streets_report.json", rep_text)
    _write_text(out_dir / "streets_report.txt", report_text(rep))
    return rep


def contribution(manifest: dict) -> dict:
    """assetgen's Unreal entries for the street pieces (AG0's format, `docs/unreal_export.md`):
    one static mesh actor per piece at its own pivot, `replaces` naming the blockout objects
    it supersedes; sky tube glass as non-Nanite meshes with a LOD chain; container stacks as
    instanced parts; the walkways of raised roads put on their decks."""
    entries = []
    slots = set()
    walkways = {}
    for pid in sorted(manifest["pieces"]):
        r = manifest["pieces"][pid]
        tile = r["tile"]
        if r.get("triangles", 0) > 0 or r.get("parts"):
            e = {"key": pid, "kind": r["kind"], "hash": r["hash"][:16],
                 "replaces": r["replaces"], "glb": f"streets/{tile}.glb", "node": pid,
                 "asset": pid.replace(".", "_"), "pivot": _pivot(r), "yaw_deg": 0.0,
                 "nanite": r.get("nanite", True), "triangles": r.get("triangles", 0),
                 "slots": r.get("slots", []), "collision": {"complex": True},
                 "tile": tile}
            slots |= set(r.get("slots", []))
            if r.get("parts"):
                e["parts"] = [{"kind": p["kind"], "glb": "streets/parts.glb",
                               "node": p["kind"], "asset": p["kind"].replace(".", "_"),
                               "count": len(p["xforms"]),
                               "triangles": manifest["parts"]["meshes"][p["kind"]]["triangles"],
                               "xforms": p["xforms"]} for p in r["parts"]]
                for p in r["parts"]:
                    slots |= set(manifest["parts"]["meshes"][p["kind"]]["slots"])
            entries.append(e)
        for ex in r.get("extra", []):
            lods = ex["lods"]
            entries.append({"key": pid + ex["suffix"], "kind": r["kind"] + ex["suffix"],
                            "hash": r["hash"][:16], "replaces": [],
                            "glb": f"streets/{tile}.glb", "node": lods[0]["node"],
                            "asset": (pid + ex["suffix"]).replace(".", "_"),
                            "pivot": _pivot(r), "yaw_deg": 0.0, "nanite": ex["nanite"],
                            "triangles": lods[0]["triangles"], "slots": lods[0]["slots"],
                            "collision": {"none": True}, "tile": tile,
                            "lods": [{"node": lo["node"], "screen_size": lo["screen_size"],
                                      "triangles": lo["triangles"]} for lo in lods]})
            for lo in lods:
                slots |= set(lo["slots"])
        for k, v in (r.get("notes", {}).get("walkways") or {}).items():
            walkways[k] = v
    return {"version": 1, "stage": "assetgen", "part": "streets", "layer": 2,
            "masters": list(MT.MASTERS), "materials": MT.contribution_materials(slots),
            "entries": entries, "graphs": {"walkways": walkways}}


def _pivot(r: dict) -> list[float]:
    """A piece's pivot: its node's translation (the middle of what it covers, z 0)."""
    o = r.get("origin")
    if o is not None:
        return [o[0], o[1], 0.0]
    b = r.get("bounds")
    if not b:
        return [0.0, 0.0, 0.0]
    return [C.m2((b[0][0] + b[1][0]) / 2.0), C.m2((b[0][1] + b[1][1]) / 2.0), 0.0]


def default_workers() -> int:
    try:
        return max(1, min(MAX_WORKERS, int(os.environ.get("ASSETGEN_WORKERS", MAX_WORKERS))))
    except ValueError:
        return MAX_WORKERS


def outputs_digest(out_dir: Path) -> dict:
    """sha256 of what the stage wrote (tile packs, parts, contribution; not the manifest,
    which also records the code's hash): the goldens' measure."""
    out_dir = Path(out_dir)
    sdir = out_dir / "streets"
    tiles = {f.stem: C.sha256_bytes(f.read_bytes()) for f in sorted(sdir.glob("t*.glb"))}
    return {"tiles": tiles, "parts": C.sha256_bytes((sdir / "parts.glb").read_bytes()),
            "contribution": C.sha256_bytes(
                (out_dir / "unreal_contribution.streets.json").read_bytes()),
            "all": C.digest({"tiles": tiles,
                             "parts": C.sha256_bytes((sdir / "parts.glb").read_bytes()),
                             "contribution": C.sha256_bytes(
                                 (out_dir / "unreal_contribution.streets.json").read_bytes())})}
