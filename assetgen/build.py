"""`assetgen build BUILD [--spec S] [--overrides O] [--workers N]` (scope sections 3, 4.4, 6):
the building assets of a citygen build into `BUILD/assets/`.

1. Briefs (AG0's stage), reused from `briefs.json` when the model, spec and overrides are
   the ones it was made from; written only when they change.
2. Genomes, then per building its asset hash
   $h(b) = \\text{sha256}(\\text{brief}(b) \\Vert v_{\\text{gen}} \\Vert h_{\\text{lib}})$.
3. Buildings grouped by citygen's 256 m tiles (by their origin); a tile whose buildings and
   hashes are all as in the previous manifest keeps its files and records, the others are
   made in worker processes (each tile a pure function of its briefs, so the bytes do not
   depend on the worker count): `tiles/<tile>.glb` (a node per building, named by id, at
   its pivot, its shell with one primitive per material slot), `proxies/<tile>.glb`.
4. Checks (`asset_checks`), `manifest.json`, `asset_report.json` and `.txt`,
   `unreal_contribution.buildings.json`; each written only if its bytes change, tiles no
   longer in the city removed. An unchanged city's rebuild writes no file.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np

from . import __version__
from . import asset_checks as AC
from . import brief as B
from . import canon as C
from . import gltf as G
from . import manifest as MF
from . import spec as S
from .buildings import collision as CO
from .buildings import envelope as EN
from .buildings import genome as GN
from .buildings import meshbuf as MB
from .buildings import proxy as PX
from .buildings import shell as SH
from .buildings import systems as SY

GEN_VERSION = "ag1.10"          # bump whenever the packs' bytes change (they carry only this,
                               # not the package version, so a kept tile is a fresh one)
TILE_M = 256.0
OWNED = ("version", "assetgen", "generator", "library", "inputs", "city", "model_sha256",
         "spec_sha256", "briefs_sha256", "buildings", "tiles")
MAX_WORKERS = 4
# the files a build delivers besides its packs (the report holds timings, so it is not one)
DELIVERED = ("briefs.json", "manifest.json", "unreal_contribution.buildings.json")


def tile_name(x: float, y: float) -> str:
    """citygen's tile name (`citygen.blockout.tile_name`) of the 256 m tile holding (x, y)."""
    import math
    ix, iy = math.floor(x / TILE_M), math.floor(y / TILE_M)
    return f"t{ix:+03d}{iy:+03d}"


def library() -> dict:
    """What the material library is today: the slots and the systems' tables."""
    return {"slots": {k: list(v) for k, v in sorted(SY.SLOTS.items())},
            "systems": SY.SYSTEMS, "fallback": SY.FALLBACK, "type_system": SY.TYPE_SYSTEM,
            "cpd": SY.CPD_TINT}


def asset_hash(brief_hash: str, lib_hash: str) -> str:
    return C.sha256_text(f"{brief_hash}|{GEN_VERSION}|{lib_hash}")


# ---------------------------------------------------------------------------
# One tile (in a worker)
# ---------------------------------------------------------------------------

def _materials(g: G.Gltf, used: list[str]) -> dict[str, int]:
    out = {}
    for name in used:
        master, hex_c, rough, metal, tint = SY.SLOTS[name]
        out[name] = g.material(name, SY.srgb_linear(hex_c) + [1.0], metal, rough,
                               extras={"slot": name, "master": master, "tint": tint})
    return out


def _tints(gm: dict) -> dict[str, list[float]]:
    return {k: SY.srgb_linear(v) for k, v in sorted(gm["colors"].items())}


def _cpd(gm: dict, tints: dict) -> list[float]:
    v = [0.0] * SY.CPD_SIZE
    for ch, at in SY.CPD_TINT.items():
        v[at:at + 3] = tints[ch]
    v[3] = gm["cont"]["wear"]
    v[4] = gm["cont"]["dirt_m"]
    v[5] = gm["extra"]["neon"]
    v[6] = gm["extra"]["lit"]
    v[7] = gm["extra"]["seed"]
    return [round(float(x), 6) for x in v]


def _area_m2(arrs: dict, slot: str) -> float:
    a = arrs.get(slot)
    if a is None:
        return 0.0
    p = a["pos"]
    t = a["tri"]
    e1 = p[t[:, 1]] - p[t[:, 0]]
    e2 = p[t[:, 2]] - p[t[:, 0]]
    cz = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    return float(int(np.abs(cz).sum())) / 2.0e6


def _bays_s11(brief: dict) -> float:
    fh = float(brief["building"]["floor_grid"]["floor_height_m"]) or 3.5
    side = 0.0
    for m in brief["masses"]:
        h = m["z"][1] - m["z"][0]
        for ring in [m["footprint"]["exterior"]] + m["footprint"]["holes"]:
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                side += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 * h
    return side / (3.0 * fh)


def building_asset(brief: dict, gm: dict) -> tuple[dict, dict, dict]:
    """(shell result, proxy result, record) of one building."""
    sh = SH.build(brief, gm)
    arrs = sh["arrays"]
    px = PX.build(brief)
    ck = MB.check(arrs)
    ck["uv0"] = True
    env = EN.check(brief, arrs)
    tints = _tints(gm)
    lo = np.min(np.concatenate([a["pos"] for a in arrs.values()]), axis=0) if arrs else \
        np.zeros(3, dtype=np.int64)
    hi = np.max(np.concatenate([a["pos"] for a in arrs.values()]), axis=0) if arrs else \
        np.zeros(3, dtype=np.int64)
    st = dict(sh["stats"])
    st["roof_m2"] = round(_area_m2(arrs, "roof"), 2)
    st["bays_s11"] = round(_bays_s11(brief), 2)
    rec = {
        "kind": "building", "type": brief["building"]["type"],
        "district": (brief.get("district") or {}).get("id"),
        "pivot": [C.m2(brief["origin"][0]), C.m2(brief["origin"][1]), _base_m(brief)],
        "bounds": [[C.m(v / 1000.0) for v in lo.tolist()],
                   [C.m(v / 1000.0) for v in hi.tolist()]],
        "triangles": int(sum(len(a["tri"]) for a in arrs.values())),
        "slots": {k: int(len(a["tri"])) for k, a in arrs.items()},
        "proxy": {"triangles": int(px["triangles"])},
        "collision": CO.build(brief),
        "tints": tints, "cpd": _cpd(gm, tints),
        "family": gm["family"], "genes": GN.effective(gm, sh["used"]),
        "bay_m": gm["cont"]["body.bay_m"],
        "floor_m": float(brief["building"]["floor_grid"]["floor_height_m"]),
        "stats": st, "masses": sh["masses"],
        "checks": {"mesh": ck, "envelope": env},
    }
    return sh, px, rec


def _base_m(brief: dict) -> float:
    """The pivot's height: M13's base (the ground floor at the main entrance), else 0."""
    base = brief["building"]["floor_grid"].get("base_m")
    return C.m(base) if base is not None else 0.0


def _node_extras(bid: str, rec: dict) -> dict:
    ex = {"cg_key": bid, "cg_bay": rec["bay_m"], "cg_floor": rec["floor_m"]}
    for k, v in rec["tints"].items():
        ex[f"cg_{k}"] = v
    return ex


def building_glb(bid: str, brief: dict, gm: dict | None = None) -> bytes:
    """One building's shell alone as a GLB at its own origin (goldens, contact sheets)."""
    sh, _, rec = building_asset(brief, gm or GN.make(brief))
    g = G.Gltf(generator=f"assetgen ({GEN_VERSION})")
    mats = _materials(g, sorted(sh["arrays"]))
    mesh = g.mesh(f"{bid}.shell", sh["buf"].primitives(sh["arrays"], mats))
    child = g.node(f"{bid}.shell", mesh=mesh, extras=_node_extras(bid, rec))
    g.node(bid, children=[child], root=True)
    return g.to_glb()


def tile_job(job: dict) -> dict:
    """Make one tile's packs; write them where their bytes changed; the records."""
    out = Path(job["out"])
    items = sorted(job["items"], key=lambda t: t[0])
    made = []
    for bid, brief, gm in items:
        sh, px, rec = building_asset(brief, gm)
        made.append((bid, brief, sh, px, rec))
    used = sorted({s for _, _, sh, _, _ in made for s in sh["arrays"]})
    g = G.Gltf(generator=f"assetgen ({GEN_VERSION})")
    mats = _materials(g, used)
    gp = G.Gltf(generator=f"assetgen ({GEN_VERSION})")
    pmats = _materials(gp, ["proxy", "proxy_roof"])
    for bid, brief, sh, px, rec in made:
        piv = (int(round(brief["origin"][0] * 1000)), int(round(brief["origin"][1] * 1000)),
               int(round(_base_m(brief) * 1000)))
        ex = _node_extras(bid, rec)
        mesh = g.mesh(f"{bid}.shell", sh["buf"].primitives(sh["arrays"], mats),
                      extras={"kind": "shell"})
        child = g.node(f"{bid}.shell", mesh=mesh, extras=ex)
        g.node(bid, translation=piv, children=[child], root=True,
               extras={"cg": {"key": bid, "kind": "building", "type": rec["type"]}})
        pm = gp.mesh(f"{bid}.proxy", px["buf"].primitives(px["arrays"], pmats),
                     extras={"kind": "proxy"})
        gp.node(f"{bid}.proxy", mesh=pm, translation=piv, root=True, extras=ex)
        rec["glb"] = f"tiles/{job['tile']}.glb"
        rec["node"] = f"{bid}.shell"
        rec["proxy"].update({"glb": f"proxies/{job['tile']}.glb", "node": f"{bid}.proxy"})
        rec["tile"] = job["tile"]
    shells = g.to_glb()
    proxies = gp.to_glb()
    wrote = 0
    wrote += MF.write_if_changed(out / "tiles" / f"{job['tile']}.glb", shells)
    wrote += MF.write_if_changed(out / "proxies" / f"{job['tile']}.glb", proxies)
    records = {}
    for bid, brief, sh, px, rec in made:
        records[bid] = rec
    return {"tile": job["tile"], "records": records, "wrote": wrote,
            "files": {"tiles": {"bytes": len(shells), "sha256": C.sha256_bytes(shells)},
                      "proxies": {"bytes": len(proxies), "sha256": C.sha256_bytes(proxies)}}}


# ---------------------------------------------------------------------------
# The city
# ---------------------------------------------------------------------------

def _briefs(model, sha: str, bdir: Path, out: Path, spec, ov: dict | None,
            inputs: dict, old: dict | None, log) -> tuple[dict, dict, int]:
    """{id: brief}, {id: brief hash}, files written."""
    path = out / "briefs.json"
    if old and old.get("inputs") == inputs and path.is_file():
        import json
        doc = json.loads(path.read_text(encoding="utf-8"))
        if C.sha256_bytes(path.read_bytes()) == old.get("briefs_sha256"):
            log(f"briefs: kept ({doc['count']})")
            return doc["briefs"], doc["hashes"], 0
    t = time.perf_counter()
    res = B.build_briefs(model, spec, ov)
    hashes = {bid: B.brief_hash(br) for bid, br in res["briefs"].items()}
    doc = {"assetgen": __version__, "brief_version": B.BRIEF_VERSION, "city": model.name,
           "model_sha256": sha, "spec_sha256": C.digest(res["spec"]),
           "count": len(hashes), "hashes": hashes, "briefs": res["briefs"]}
    wrote = MF.write_if_changed(path, C.dumps(doc) + "\n")
    log(f"briefs: {len(hashes)} in {time.perf_counter() - t:.1f} s"
        f"{' (written)' if wrote else ' (unchanged)'}")
    return res["briefs"], hashes, int(wrote)


def build(build_dir: str | Path, spec_path: str | None = None,
          overrides_path: str | None = None, workers: int | None = None,
          log=print) -> dict:
    t0 = time.perf_counter()
    model, sha, bdir = B.load_model(build_dir)
    out = bdir / "assets"
    spec = None
    spec_doc = None
    if spec_path:
        res = S.load_spec(spec_path, model)
        if not res.ok:
            raise ValueError("; ".join(str(i) for i in res.errors))
        spec = res.spec
    spec_doc = S.dump(S.fill(spec or S.AssetSpec()))
    ov = S.overrides_by_id(S.load_overrides(overrides_path)) if overrides_path else None
    lib = library()
    lib_hash = C.digest(lib)
    inputs = {"model_sha256": sha, "spec": C.digest(spec_doc), "overrides": C.digest(ov or {}),
              "brief_version": B.BRIEF_VERSION, "assetgen": __version__,
              "generator": GEN_VERSION}
    old = MF.load(out)
    t1 = time.perf_counter()
    briefs, bh, wrote = _briefs(model, sha, bdir, out, spec, ov, inputs, old, log)
    t2 = time.perf_counter()
    genomes = {bid: GN.make(briefs[bid]) for bid in sorted(briefs)}
    hashes = {bid: asset_hash(bh[bid], lib_hash) for bid in sorted(briefs)}
    tiles: dict[str, list[str]] = {}
    for bid in sorted(briefs):
        o = briefs[bid]["origin"]
        tiles.setdefault(tile_name(o[0], o[1]), []).append(bid)
    tile_hash = {t: C.digest([t, [[bid, hashes[bid]] for bid in ids]])
                 for t, ids in sorted(tiles.items())}
    old_tiles = (old or {}).get("tiles", {})
    old_b = (old or {}).get("buildings", {})
    todo, keep = [], []
    for t in sorted(tiles):
        ot = old_tiles.get(t)
        fresh = ot is not None and ot.get("hash") == tile_hash[t] and \
            all(bid in old_b for bid in tiles[t]) and \
            _file_ok(out / "tiles" / f"{t}.glb", ot.get("tiles")) and \
            _file_ok(out / "proxies" / f"{t}.glb", ot.get("proxies"))
        (keep if fresh else todo).append(t)
    t3 = time.perf_counter()
    records: dict[str, dict] = {}
    files: dict[str, dict] = {}
    for t in keep:
        for bid in tiles[t]:
            records[bid] = old_b[bid]
        files[t] = {"tiles": old_tiles[t]["tiles"], "proxies": old_tiles[t]["proxies"]}
    jobs = [{"tile": t, "out": str(out),
             "items": [(bid, briefs[bid], genomes[bid]) for bid in tiles[t]]} for t in todo]
    # biggest first, so the pool ends together (results do not depend on the order)
    jobs.sort(key=lambda j: (-sum(len(b["edges"]) * max(1, b["building"]["floors"])
                                  for _, b, _ in j["items"]), j["tile"]))
    nw = _workers(workers, len(jobs))
    log(f"tiles: {len(tiles)} ({len(todo)} to make, {len(keep)} kept), {nw} workers")
    for r in _run(jobs, nw, log):
        for bid, rec in r["records"].items():
            rec["hash"] = hashes[bid]
            rec["brief"] = bh[bid]
            records[bid] = rec
        files[r["tile"]] = r["files"]
        wrote += r["wrote"]
    t4 = time.perf_counter()
    k = int(spec_doc["min_gene_distance"])
    checks = [AC.coverage(model, records), AC.envelope(records), AC.meshes(records),
              AC.unique(records, k), AC.budget(records)]
    t5 = time.perf_counter()
    man = {"version": MF.MANIFEST_VERSION, "assetgen": __version__, "generator": GEN_VERSION,
           "library": lib_hash, "inputs": inputs, "city": model.name, "model_sha256": sha,
           "spec_sha256": C.digest(spec_doc),
           "briefs_sha256": C.sha256_bytes((out / "briefs.json").read_bytes()),
           "tiles": {t: {"hash": tile_hash[t], "buildings": tiles[t], **files[t]}
                     for t in sorted(tiles)},
           "buildings": {bid: records[bid] for bid in sorted(records)}}
    man = MF.merge(old, man, OWNED)
    text = MF.dumps(man)
    changed = MF.write_if_changed(out / MF.MANIFEST, text)
    wrote += changed
    # tiles no longer in the city
    for t in sorted(set(old_tiles) - set(tiles)):
        for sub in ("tiles", "proxies"):
            p = out / sub / f"{t}.glb"
            if p.is_file():
                p.unlink()
                wrote += 1
    from . import contribution as UC
    wrote += MF.write_if_changed(out / "unreal_contribution.buildings.json",
                                 MF.dumps(UC.buildings(man)))
    secs = {"load": round(t1 - t0, 2), "briefs": round(t2 - t1, 2),
            "genomes": round(t3 - t2, 2), "tiles": round(t4 - t3, 2),
            "checks": round(t5 - t4, 2), "total": round(time.perf_counter() - t0, 2)}
    rep = report(man, checks, secs, nw, len(todo), len(keep))
    if changed or not (out / "asset_report.json").is_file():
        wrote += MF.write_if_changed(out / "asset_report.json", MF.dumps(rep))
        wrote += MF.write_if_changed(out / "asset_report.txt", report_text(rep))
    rep["files_written"] = wrote
    return rep


def _file_ok(p: Path, info: dict | None) -> bool:
    return info is not None and p.is_file() and p.stat().st_size == info.get("bytes")


def _workers(n: int | None, jobs: int) -> int:
    if n is None:
        env = os.environ.get("ASSETGEN_WORKERS")
        n = int(env) if env else min(MAX_WORKERS, os.cpu_count() or 1)
    return max(1, min(n, jobs or 1))


def _run(jobs: list[dict], nw: int, log):
    if nw <= 1 or len(jobs) <= 1:
        for k, j in enumerate(jobs):
            yield tile_job(j)
        return
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=nw, mp_context=mp.get_context("spawn")) as ex:
        futs = [ex.submit(tile_job, j) for j in jobs]
        done = 0
        for f in as_completed(futs):
            done += 1
            if done % 50 == 0:
                log(f"  {done}/{len(jobs)} tiles")
            yield f.result()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report(man: dict, checks: list[dict], secs: dict, workers: int, made: int,
           kept: int) -> dict:
    recs = man["buildings"]
    by_type: dict[str, dict] = {}
    by_slot: dict[str, int] = {}
    stats: dict[str, float] = {}
    for r in recs.values():
        t = by_type.setdefault(r["type"], {"buildings": 0, "triangles": 0, "max": 0,
                                           "proxy_max": 0})
        t["buildings"] += 1
        t["triangles"] += r["triangles"]
        t["max"] = max(t["max"], r["triangles"])
        t["proxy_max"] = max(t["proxy_max"], r["proxy"]["triangles"])
        for s, n in r["slots"].items():
            by_slot[s] = by_slot.get(s, 0) + n
        for s, v in r["stats"].items():
            stats[s] = stats.get(s, 0) + v
    tri = sum(r["triangles"] for r in recs.values())
    ptri = sum(r["proxy"]["triangles"] for r in recs.values())
    pt = sorted(r["proxy"]["triangles"] for r in recs.values())
    disk_t = sum(t["tiles"]["bytes"] for t in man["tiles"].values())
    disk_p = sum(t["proxies"]["bytes"] for t in man["tiles"].values())
    return {
        "city": man["city"], "assetgen": man["assetgen"], "generator": man["generator"],
        "buildings": len(recs), "tiles": len(man["tiles"]),
        "triangles": {"shells": tri, "proxies": ptri,
                      "per_building": round(tri / max(len(recs), 1), 1),
                      "proxy": {"min": pt[0] if pt else 0, "median": pt[len(pt) // 2] if pt
                                else 0, "max": pt[-1] if pt else 0},
                      "by_slot": dict(sorted(by_slot.items())),
                      "by_type": dict(sorted(by_type.items()))},
        "disk": {"tiles_bytes": disk_t, "proxies_bytes": disk_p,
                 "bytes_per_triangle": round(disk_t / max(tri, 1), 1)},
        "stats": {k: round(v, 2) if isinstance(v, float) else v
                  for k, v in sorted(stats.items())},
        "checks": {c["name"]: c for c in checks},
        "ok": all(c["ok"] for c in checks),
        "seconds": secs, "workers": workers, "tiles_made": made, "tiles_kept": kept,
    }


def report_text(rep: dict) -> str:
    t = rep["triangles"]
    lines = [f"assetgen {rep['assetgen']} ({rep['generator']}): {rep['city']}",
             f"buildings {rep['buildings']} in {rep['tiles']} tiles; "
             f"{'all checks pass' if rep['ok'] else 'CHECKS FAIL'}",
             f"shell triangles {t['shells']:,} ({t['per_building']} per building), "
             f"proxies {t['proxies']:,} (min {t['proxy']['min']}, median "
             f"{t['proxy']['median']}, max {t['proxy']['max']})",
             f"disk: tiles {rep['disk']['tiles_bytes'] / 1e6:.1f} MB "
             f"({rep['disk']['bytes_per_triangle']} B per triangle), proxies "
             f"{rep['disk']['proxies_bytes'] / 1e6:.1f} MB", ""]
    for name, c in rep["checks"].items():
        extra = {k: v for k, v in c.items() if k not in ("name", "ok", "first")}
        lines.append(f"{'PASS' if c['ok'] else 'FAIL'} {name}: {extra}")
        if not c["ok"] and c.get("first"):
            lines.append(f"     first: {c['first']}")
    lines.append("")
    lines.append("triangles by type:")
    for k, v in t["by_type"].items():
        lines.append(f"  {k}: {v['buildings']} buildings, {v['triangles']:,} triangles, "
                     f"max {v['max']:,}, proxy max {v['proxy_max']}")
    lines.append("triangles by slot: " + ", ".join(f"{k} {v:,}" for k, v in
                                                    t["by_slot"].items()))
    lines.append("stats: " + ", ".join(f"{k} {v}" for k, v in rep["stats"].items()))
    s = rep["seconds"]
    lines.append(f"seconds: {s} with {rep['workers']} workers "
                 f"({rep['tiles_made']} tiles made, {rep['tiles_kept']} kept)")
    return "\n".join(lines) + "\n"
