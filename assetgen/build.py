"""`assetgen build BUILD [--spec S] [--overrides O] [--workers N] [--no-streets]
[--no-props]` (scope sections 3, 4.4, 6): the building assets of a citygen build into
`BUILD/assets/`, then its street packs, then its props, plants and signs.

1. Briefs (AG0's stage), reused from `briefs.json` when the model, spec and overrides are
   the ones it was made from; written only when they change.
2. Genomes, then per building its asset hash
   $h(b) = \\text{sha256}(\\text{brief}(b) \\Vert v_{\\text{gen}} \\Vert h_{\\text{lib}})$.
3. Buildings grouped by citygen's 256 m tiles (by their origin); a tile whose buildings and
   hashes are all as in the previous manifest keeps its files and records, the others are
   made in worker processes (each tile a pure function of its briefs, so the bytes do not
   depend on the worker count): `tiles/<tile>.glb` (a node per building, named by id, at
   its pivot, its shell with one primitive per material slot and the parts merged into
   it), `proxies/<tile>.glb`, `parts/<tile>.glb` (AG2: one mesh per instanced part of the
   tile's buildings, at the origin, named by the hash of its parameters, so buildings whose
   parts coincide share it; the placements are in each building's record).
4. AG4's skybridges (`skybridges.py`): every model skybridge a piece of its own in
   `connections/<tile>.glb`, its record in the manifest's `skybridges`.
5. Checks (`asset_checks`), `manifest.json`, `asset_report.json` and `.txt`,
   `unreal_contribution.buildings.json` and `.connections.json`; each written only if its
   bytes change, tiles no longer in the city removed.
6. The street stage (AG7's `assetgen streets`, `assetgen/streets/build.py`, the same
   bytes): `streets/<tile>.glb`, `streets/manifest.json`, `unreal_contribution.streets.json`,
   `streets_report.json` and `.txt` (the report only when another of its files changed).
7. AG6's sign pages (`materials/build.signage`: `textures/`, `signs.json`), then the props
   stage (AG8's `assetgen props`, `assetgen/props/build.py`, the same bytes): the variant
   families, exact props and signs (their faces showing those pages),
   `unreal_contribution.props.json` and `.signs.json`, `props_report.json` and `.txt`
   (likewise); then AG6's materials and checks over every contribution and pack
   (`materials/build.stage`).

An unchanged city's rebuild writes no file.
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
from .progress import Progress
from . import spec as S
from .buildings import collision as CO
from .buildings import envelope as EN
from .buildings import genome as GN
from .buildings import meshbuf as MB
from .buildings import proxy as PX
from .buildings import parts as PT
from .buildings import shell as SH
from .buildings import systems as SY
from .buildings import thumb as TH

GEN_VERSION = "ag4.0"          # bump whenever the packs' bytes change (they carry only this,
                               # not the package version, so a kept tile is a fresh one)
TILE_M = 256.0
OWNED = ("version", "assetgen", "generator", "library", "inputs", "city", "model_sha256",
         "spec_sha256", "briefs_sha256", "buildings", "tiles", "skybridges", "connections",
         "green_replaces")
MAX_WORKERS = 4
DECAL_OFF_MM = 10              # AG3: a decal quad stands this far off its wall (mesh decals)
DECAL_UV = (0.004, 0.996)      # its atlas cell's own UVs, inset so it never reads a neighbor
# the files a build delivers besides its packs (the report holds timings, so it is not one)
DELIVERED = ("briefs.json", "manifest.json", "unreal_contribution.buildings.json",
             "unreal_contribution.connections.json")


def tile_name(x: float, y: float) -> str:
    """citygen's tile name (`citygen.blockout.tile_name`) of the 256 m tile holding (x, y)."""
    import math
    ix, iy = math.floor(x / TILE_M), math.floor(y / TILE_M)
    return f"t{ix:+03d}{iy:+03d}"


def library() -> dict:
    """What the material library is today: the slots and the systems' tables."""
    return {"slots": {k: list(v) for k, v in sorted(SY.SLOTS.items())},
            "systems": SY.SYSTEMS, "fallback": SY.FALLBACK, "type_system": SY.TYPE_SYSTEM,
            "cpd": SY.CPD_TINT, "articulation": SY.ARTICULATION,
            "features": SY.FEATURE_GENES, "parts": PT.PARTS_VERSION}


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


def _part_rec(x: dict) -> dict:
    rec = {"node": x["node"], "type": x["type"], "family": x["family"],
           "count": len(x["at"]), "triangles": x["triangles"],
           "xforms": [[C.m(a[0] / 1000.0), C.m(a[1] / 1000.0), C.m(a[2] / 1000.0),
                       PT.yaw_deg(a[3], a[4])] for a in x["at"]]}
    if x["family"] in PT.INSTANCE_ALWAYS:
        rec["roof"] = True            # (AG4: roof equipment, instanced per tile in Unreal)
    return rec


def _doors(sh: dict) -> list[dict]:
    """A building's doors in meters (its frame): AG3's records for the access check, the
    contribution and stage 4."""
    out = []
    for d in sh["doors"]:
        out.append({"id": d["id"], "kind": d["kind"], "entrance": d["entrance"],
                    "unit": d["unit"], "use": d["use"], "walkway_id": d["walkway_id"],
                    "position": [C.m(d["pos"][0] / 1000.0), C.m(d["pos"][1] / 1000.0),
                                 C.m(d["pos"][2] / 1000.0)],
                    "normal": d["normal"], "width_m": C.m(d["w"] / 1000.0),
                    "height_m": C.m(d["h"] / 1000.0), "depth_m": C.m(d["depth"] / 1000.0),
                    "steps": d["steps"], "flush": d["flush"], "moved": bool(d.get("moved")),
                    "class": d["class"]})
    return sorted(out, key=lambda d: d["id"])


def building_asset(brief: dict, gm: dict) -> tuple[dict, dict, dict]:
    """(shell result, proxy result, record) of one building. AG3: the shell result's
    `shell` and `front` are its two meshes' arrays (the ground band, layer 1, apart)."""
    sh = SH.build(brief, gm)
    arrs = sh["arrays"]
    sh["shell"], sh["front"] = MB.split(arrs)
    px = PX.build(brief)
    ck = MB.check(sh["shell"])
    ckf = MB.check(sh["front"])
    for key in ("triangles", "degenerate", "duplicate", "open_edges", "bad_edges", "parts"):
        ck[key] += ckf[key]
    ck["uv0"] = True
    inst = sh["parts"]
    pp = EN.part_points(inst)
    env = EN.check(brief, arrs, pp)
    clr = EN.clearances(brief, arrs, pp)
    tints = _tints(gm)
    lo = np.min(np.concatenate([a["pos"] for a in arrs.values()]), axis=0) if arrs else \
        np.zeros(3, dtype=np.int64)
    hi = np.max(np.concatenate([a["pos"] for a in arrs.values()]), axis=0) if arrs else \
        np.zeros(3, dtype=np.int64)
    st = dict(sh["stats"])
    st["roof_m2"] = round(_area_m2(arrs, "roof"), 2)
    st["bays_s11"] = round(_bays_s11(brief), 2)
    st["units"] = len(brief["units"])
    st["decals"] = len(sh.get("decals", []))
    rec = {
        "kind": "building", "type": brief["building"]["type"],
        "district": (brief.get("district") or {}).get("id"),
        "pivot": [C.m2(brief["origin"][0]), C.m2(brief["origin"][1]), _base_m(brief)],
        "bounds": [[C.m(v / 1000.0) for v in lo.tolist()],
                   [C.m(v / 1000.0) for v in hi.tolist()]],
        "triangles": int(sum(len(a["tri"]) for a in arrs.values())),
        "slots": {k: int(len(a["tri"])) for k, a in arrs.items()},
        "proxy": {"triangles": int(px["triangles"])},
        "collision": CO.build(brief, sh["band_m"]),
        "front": {"triangles": int(sum(len(a["tri"]) for a in sh["front"].values())),
                  "slots": {k: int(len(a["tri"])) for k, a in sh["front"].items()},
                  "band_m": sh["band_m"]},
        "doors": _doors(sh),
        "tints": tints, "cpd": _cpd(gm, tints),
        "family": gm["family"], "genes": GN.effective(gm, sh["used"]),
        "bay_m": gm["cont"]["body.bay_m"],
        "floor_m": float(brief["building"]["floor_grid"]["floor_height_m"]),
        "stats": st, "masses": sh["masses"],
        "checks": {"mesh": ck, "envelope": env, "mounts": sh["checks"]["mounts"],
                   "doors": sh["checks"]["access"], "clearance": clr},
        # AG4: every roof item's asset, green roofs, skybridge landings, portals
        "roof_items": sh["roof_items"], "green": sh["green"], "landings": sh["landings"],
        "portals": sh["portals"],
        "parts": [_part_rec(x) for x in inst],
        "instances": int(sum(len(x["at"]) for x in inst)),
        "part_triangles": int(sum(x["triangles"] for x in inst)),
    }
    if brief["building"]["floor_grid"].get("level"):
        rec["level"] = int(brief["building"]["floor_grid"]["level"])     # (M14: on a deck)
    rec["thumb"], rec["thumb_fill"] = TH.hash_of(brief, arrs, inst, tints)
    rec["class"] = AC.budget_class(rec)
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
    """One building alone as a GLB at its own origin (goldens): its shell and every
    placement of its instanced parts as a node of its own."""
    sh, _, rec = building_asset(brief, gm or GN.make(brief))
    pm = [(x, PT.mesh(x["family"], x["params"])) for x in sh["parts"]]
    g = G.Gltf(generator=f"assetgen ({GEN_VERSION})")
    mats = _materials(g, sorted(set(sh["arrays"]) | {s for _, (_, a) in pm for s in a}))
    mesh = g.mesh(f"{bid}.shell", sh["buf"].primitives(sh["shell"], mats))
    kids = [g.node(f"{bid}.shell", mesh=mesh, extras=_node_extras(bid, rec))]
    if sh["front"]:
        fm = g.mesh(f"{bid}.front", sh["buf"].primitives(sh["front"], mats))
        kids.append(g.node(f"{bid}.front", mesh=fm, extras=_node_extras(bid, rec)))
    for x, (b, arrs) in pm:
        m = g.mesh(x["node"], b.primitives(arrs, mats))
        for k, a in enumerate(x["at"]):
            kids.append(g.node(f"{x['node']}.i{k}", mesh=m, translation=a[:3],
                               rotation=G.quat_z(PT.yaw_deg(a[3], a[4]))))
    g.node(bid, children=kids, root=True)
    return g.to_glb()


def decal_slot(cell: str) -> str:
    return f"decal.{cell}"


def _decal_mesh(g: G.Gltf, tile: str, made: list) -> dict | None:
    """AG3's decals of a tile's buildings (grime, leaks, rust, graffiti, posters, cracks,
    moss on their street bands) as one mesh of quads at the tile's middle, a primitive per
    decal atlas cell (slot `decal.<cell>`, UV0 0 to 1 over the quad, v down): mesh decals
    in Unreal, alpha quads in Blender. Its record: node, count, slots, translation."""
    by: dict[str, list] = {}
    for bid, brief, sh, _, _ in made:
        piv = (int(round(brief["origin"][0] * 1000)), int(round(brief["origin"][1] * 1000)),
               int(round(_base_m(brief) * 1000)))
        for d in sh.get("decals", []):
            by.setdefault(d["cell"], []).append((piv, d))
    if not by:
        return None
    ix, iy = int(tile[1:4]), int(tile[4:7])
    o = (int((ix + 0.5) * TILE_M * 1000), int((iy + 0.5) * TILE_M * 1000), 0)
    a0, a1 = DECAL_UV
    prims, slots, n = [], {}, 0
    for cell in sorted(by):
        pos, nrm, uv, idx = [], [], [], []
        for piv, d in by[cell]:
            nx, ny = d["normal"]
            tx, ty = -ny, nx                     # along the wall, left to right seen from out
            cx = piv[0] + d["pos"][0] + nx * DECAL_OFF_MM - o[0]
            cy = piv[1] + d["pos"][1] + ny * DECAL_OFF_MM - o[1]
            cz = piv[2] + d["pos"][2]
            hw, hh = d["w"] / 2.0, d["h"] / 2.0
            k = len(pos)
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                pos.append((int(round(cx + su * hw * tx)), int(round(cy + su * hw * ty)),
                            int(round(cz + sv * hh))))
                nrm.append((nx, ny, 0.0))
                uv.append((a0 if su < 0 else a1, a1 if sv < 0 else a0))
            idx += [k, k + 1, k + 2, k, k + 2, k + 3]
            n += 1
        name = decal_slot(cell)
        mi = g.material(name, (1.0, 1.0, 1.0, 1.0), 0.0, 0.8,
                        extras={"slot": name, "master": "decal", "cell": cell})
        prims.append(G.Primitive(material=mi, positions=np.array(pos, dtype=np.int64),
                                 indices=np.array(idx, dtype=np.int64),
                                 normals=np.array(nrm, dtype=np.float64),
                                 uv0=np.array(uv, dtype=np.float64)))
        slots[name] = len(by[cell])
    node = f"decals.{tile}"
    m = g.mesh(node, prims, extras={"kind": "decals"})
    g.node(node, mesh=m, translation=o, root=True,
           extras={"cg": {"key": node, "kind": "decals", "tile": tile}})
    return {"node": node, "count": n, "slots": slots,
            "translation": [C.m(o[0] / 1000.0), C.m(o[1] / 1000.0), 0.0]}


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
    # the tile's instanced parts, one mesh each (buildings whose parts coincide share it)
    pdefs = {}
    for _, _, sh, _, _ in made:
        for x in sh["parts"]:
            pdefs.setdefault(x["node"], (x["family"], x["params"]))
    part_checks = {"parts": 0, "bad": []}
    parts_glb = None
    if pdefs:
        gq = G.Gltf(generator=f"assetgen ({GEN_VERSION})")
        pm = {node: PT.mesh(*pdefs[node]) for node in sorted(pdefs)}
        qmats = _materials(gq, sorted({s for _, a in pm.values() for s in a}))
        for node in sorted(pm):
            b, arrs = pm[node]
            ck = MB.check(arrs)
            part_checks["parts"] += 1
            if ck["degenerate"] or ck["duplicate"] or ck["open_edges"] or ck["bad_edges"]:
                part_checks["bad"].append(node)
            mesh = gq.mesh(node, b.primitives(arrs, qmats), extras={"kind": "part"})
            gq.node(node, mesh=mesh, root=True,
                    extras={"cg": {"part": PT.type_of(*pdefs[node]), "kind": "part"}})
        parts_glb = gq.to_glb()
    for bid, brief, sh, px, rec in made:
        piv = (int(round(brief["origin"][0] * 1000)), int(round(brief["origin"][1] * 1000)),
               int(round(_base_m(brief) * 1000)))
        ex = _node_extras(bid, rec)
        mesh = g.mesh(f"{bid}.shell", sh["buf"].primitives(sh["shell"], mats),
                      extras={"kind": "shell"})
        kids = [g.node(f"{bid}.shell", mesh=mesh, extras=ex)]
        if sh["front"]:
            # AG3: the street front, its own mesh (Unreal collides it as drawn)
            fm = g.mesh(f"{bid}.front", sh["buf"].primitives(sh["front"], mats),
                        extras={"kind": "front"})
            kids.append(g.node(f"{bid}.front", mesh=fm, extras=ex))
            rec["front"]["node"] = f"{bid}.front"
        g.node(bid, translation=piv, children=kids, root=True,
               extras={"cg": {"key": bid, "kind": "building", "type": rec["type"]}})
        pm = gp.mesh(f"{bid}.proxy", px["buf"].primitives(px["arrays"], pmats),
                     extras={"kind": "proxy"})
        gp.node(f"{bid}.proxy", mesh=pm, translation=piv, root=True, extras=ex)
        rec["glb"] = f"tiles/{job['tile']}.glb"
        rec["node"] = f"{bid}.shell"
        rec["proxy"].update({"glb": f"proxies/{job['tile']}.glb", "node": f"{bid}.proxy"})
        rec["tile"] = job["tile"]
        if rec["parts"]:
            rec["parts_glb"] = f"parts/{job['tile']}.glb"
    decals = _decal_mesh(g, job["tile"], made)
    shells = g.to_glb()
    proxies = gp.to_glb()
    wrote = 0
    wrote += MF.write_if_changed(out / "tiles" / f"{job['tile']}.glb", shells)
    wrote += MF.write_if_changed(out / "proxies" / f"{job['tile']}.glb", proxies)
    ppath = out / "parts" / f"{job['tile']}.glb"
    if parts_glb is not None:
        wrote += MF.write_if_changed(ppath, parts_glb)
    elif ppath.is_file():
        ppath.unlink()
        wrote += 1
    records = {}
    for bid, brief, sh, px, rec in made:
        records[bid] = rec
    files = {"tiles": {"bytes": len(shells), "sha256": C.sha256_bytes(shells)},
             "proxies": {"bytes": len(proxies), "sha256": C.sha256_bytes(proxies)}}
    if decals is not None:
        files["decals"] = decals
    if parts_glb is not None:
        files["parts"] = {"bytes": len(parts_glb), "sha256": C.sha256_bytes(parts_glb),
                          "meshes": part_checks["parts"],
                          "triangles": int(sum(len(a["tri"]) for _, arrs in
                                               (PT.mesh(*pdefs[n]) for n in sorted(pdefs))
                                               for a in arrs.values())),
                          "bad": part_checks["bad"]}
    return {"tile": job["tile"], "records": records, "wrote": wrote, "files": files}


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
          log=print, streets: bool = True, textures: bool = True,
          props: bool = True, progress: Progress | None = None) -> dict:
    """`progress`: stage lines and bars on stderr (`assetgen/progress.py`); the log lines go
    to its notes then, else to `log`."""
    t0 = time.perf_counter()
    P = progress if progress is not None else Progress(quiet=True)
    with P.stage("load") as st:
        model, sha, bdir = B.load_model(build_dir)
        st.note(f"{model.name}: {len(model.buildings)} buildings")
    out = bdir / "assets"
    spec = filled = None
    spec_doc = None
    if spec_path:
        res = S.load_spec(spec_path, model)
        if not res.ok:
            raise ValueError("; ".join(str(i) for i in res.errors))
        spec, filled = res.spec, res.filled
    spec_doc = S.dump(S.fill(spec or S.AssetSpec()))
    ov = S.overrides_by_id(S.load_overrides(overrides_path)) if overrides_path else None
    lib = library()
    lib_hash = C.digest(lib)
    inputs = {"model_sha256": sha, "spec": C.digest(spec_doc), "overrides": C.digest(ov or {}),
              "brief_version": B.BRIEF_VERSION, "assetgen": __version__,
              "generator": GEN_VERSION}
    old = MF.load(out)
    t1 = time.perf_counter()
    with P.stage("briefs") as st:
        briefs, bh, wrote = _briefs(model, sha, bdir, out, spec, ov, inputs, old,
                                    log if progress is None else st.note)
    t2 = time.perf_counter()
    genomes = {}
    with P.stage("genomes", total=len(briefs)) as st:
        for bid in sorted(briefs):
            genomes[bid] = GN.make(briefs[bid])
            st.advance()
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
            _file_ok(out / "proxies" / f"{t}.glb", ot.get("proxies")) and \
            (ot.get("parts") is None or _file_ok(out / "parts" / f"{t}.glb", ot.get("parts")))
        (keep if fresh else todo).append(t)
    t3 = time.perf_counter()
    records: dict[str, dict] = {}
    files: dict[str, dict] = {}
    for t in keep:
        for bid in tiles[t]:
            records[bid] = old_b[bid]
        files[t] = {k: old_tiles[t][k] for k in ("tiles", "proxies", "parts", "decals")
                    if old_tiles[t].get(k) is not None}
    jobs = [{"tile": t, "out": str(out),
             "items": [(bid, briefs[bid], genomes[bid]) for bid in tiles[t]]} for t in todo]
    # biggest first, so the pool ends together (results do not depend on the order)
    jobs.sort(key=lambda j: (-sum(len(b["edges"]) * max(1, b["building"]["floors"])
                                  for _, b, _ in j["items"]), j["tile"]))
    nw = _workers(workers, len(jobs))
    with P.stage("shells and parts", total=len(jobs)) as st:
        (log if progress is None else st.note)(
            f"tiles: {len(tiles)} ({len(todo)} to make, {len(keep)} kept), {nw} workers")
        for r in _run(jobs, nw, log if progress is None else (lambda *a: None)):
            for bid, rec in r["records"].items():
                rec["hash"] = hashes[bid]
                rec["brief"] = bh[bid]
                records[bid] = rec
            files[r["tile"]] = r["files"]
            wrote += r["wrote"]
            st.advance()
    t4 = time.perf_counter()
    from .materials import build as MS
    from .materials import params as MP
    MP.annotate(records, briefs, genomes)          # AG6: era, interior, extra CPD
    lib = MS.library_for(spec_doc, out, log=log, progress=progress) if textures else None
    k = int(spec_doc["min_gene_distance"])
    tile_parts = {t: files[t].get("parts") for t in sorted(files)}
    from . import skybridges as SK
    with P.stage("skybridges") as st:            # AG4: every skybridge an asset of its own
        sky = SK.build(model, out, log if progress is None else st.note)
    wrote += sky["wrote"]
    with P.stage("building checks"):
        acc = AC.access(model, records, briefs)
        checks = [AC.coverage(model, records), AC.envelope(records),
                  AC.meshes(records, tile_parts), AC.unique(records, k),
                  AC.budget(records, tile_parts), acc, AC.mounts(records),
                  AC.clearance(records), AC.roofs(records, briefs),
                  AC.landings(records, sky["records"]), sky["check"]]
    t5 = time.perf_counter()
    man = {"version": MF.MANIFEST_VERSION, "assetgen": __version__, "generator": GEN_VERSION,
           "library": lib_hash, "inputs": inputs, "city": model.name, "model_sha256": sha,
           "spec_sha256": C.digest(spec_doc),
           "briefs_sha256": C.sha256_bytes((out / "briefs.json").read_bytes()),
           "tiles": {t: {"hash": tile_hash[t], "buildings": tiles[t], **files[t]}
                     for t in sorted(tiles)},
           "buildings": {bid: records[bid] for bid in sorted(records)},
           "skybridges": sky["records"], "connections": sky["files"]}
    from . import contribution as UC
    man["green_replaces"] = UC.green_replaces(model, records)
    man = MF.merge(old, man, OWNED)
    text = MF.dumps(man)
    changed = MF.write_if_changed(out / MF.MANIFEST, text)
    wrote += changed
    # tiles no longer in the city
    for t in sorted(set(old_tiles) - set(tiles)):
        for sub in ("tiles", "proxies", "parts"):
            p = out / sub / f"{t}.glb"
            if p.is_file():
                p.unlink()
                wrote += 1
    wrote += MF.write_if_changed(out / "unreal_contribution.buildings.json",
                                 MF.dumps(UC.buildings(man, lib)))
    wrote += MF.write_if_changed(out / "unreal_contribution.connections.json",
                                 MF.dumps(SK.contribution(man, lib)))
    secs = {"load": round(t1 - t0, 2), "briefs": round(t2 - t1, 2),
            "genomes": round(t3 - t2, 2), "tiles": round(t4 - t3, 2),
            "checks": round(t5 - t4, 2), "total": round(time.perf_counter() - t0, 2)}
    rep = report(man, checks, secs, nw, len(todo), len(keep))
    if changed or not (out / "asset_report.json").is_file():
        wrote += MF.write_if_changed(out / "asset_report.json", MF.dumps(rep))
        wrote += MF.write_if_changed(out / "asset_report.txt", report_text(rep))
    if streets:
        from .streets.build import build as street_build, default_workers
        with P.stage("streets") as sst:
            srep = street_build(model, sha, out, filled,
                                workers=workers or default_workers(), report_always=False,
                                lib=lib)
            sst.note(f"{srep['stats']['pieces']} pieces in {srep['stats']['tiles']} tiles, "
                     f"{srep['files']['tiles_made']} made")
        f = srep["files"]
        n = len(f["written"]) + f["tiles_removed"] + sum(
            int(bool(f[k])) for k in ("parts_written", "manifest_written",
                                      "contribution_written", "report_written"))
        wrote += n
        st = srep["stats"]
        rep["streets"] = {"ok": srep["ok"], "pieces": st["pieces"], "tiles": st["tiles"],
                          "triangles": st["triangles"], "disk_bytes": st["disk_bytes"],
                          "failed": [c["id"] for c in srep["checks"] if not c["ok"]],
                          "tiles_made": f["tiles_made"], "files_written": n,
                          "seconds": srep["seconds"]["total"]}
        rep["ok"] = rep["ok"] and srep["ok"]
        if progress is None:
            log(f"streets: {st['pieces']} pieces in {st['tiles']} tiles, {f['tiles_made']} "
                f"made, {n} files written")
    # AG6's sign pages before AG8's signs show them; its materials and checks after them
    signs = None
    if lib is not None:
        with P.stage("signage") as st:
            signs = MS.signage(model, out, spec_doc, log if progress is None else st.note)
    if props:
        from .props.build import build as props_build, default_workers as props_workers
        with P.stage("props") as pst:
            prep = props_build(model, sha, out, filled, briefs=briefs,
                               workers=workers or props_workers(), report_always=False,
                               lib=lib)
            pst.note(f"{prep['stats']['variants']} variants, {prep['stats']['instances']} "
                     f"instances, {prep['files']['tiles_made']} tiles made")
        f = prep["files"]
        n = len(f["written"]) + len(f["removed"]) + int(bool(f["manifest_written"])) + \
            sum(int(bool(x)) for x in f["contribution_written"]) + int(f["report_written"])
        wrote += n
        st = prep["stats"]
        rep["props"] = {"ok": prep["ok"], "variants": st["variants"],
                        "instances": st["instances"], "signs": st["signs"],
                        "unique_triangles": st["unique_triangles"],
                        "disk_bytes": st["disk_bytes"],
                        "failed": [c["id"] for c in prep["checks"] if not c["ok"]],
                        "tiles_made": f["tiles_made"], "files_written": n,
                        "seconds": prep["seconds"]["total"]}
        rep["ok"] = rep["ok"] and prep["ok"]
        if progress is None:
            log(f"props: {st['variants']} variants, {st['instances']} instances, "
                f"{st['signs']} signs, {f['tiles_made']} tiles made, {n} files written")
    if lib is not None:
        mrep = MS.stage(model, sha, out, spec_doc, lib, log, signs=signs, progress=progress)
        wrote += mrep["files_written"]
        rep["materials"] = {"ok": mrep["ok"], "textures": mrep["textures"],
                            "failed": [c for c, v in mrep["checks"].items() if not v["ok"]],
                            "seconds": mrep["seconds"]["total"]}
        rep["ok"] = rep["ok"] and mrep["ok"]
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
            if isinstance(v, dict):          # (AG4: counts by kind, e.g. roof_form_kinds)
                d = stats.setdefault(s, {})
                for kk, vv in v.items():
                    d[kk] = d.get(kk, 0) + vv
            else:
                stats[s] = stats.get(s, 0) + v
    tri = sum(r["triangles"] for r in recs.values())
    ptri = sum(r["proxy"]["triangles"] for r in recs.values())
    pt = sorted(r["proxy"]["triangles"] for r in recs.values())
    disk_t = sum(t["tiles"]["bytes"] for t in man["tiles"].values())
    disk_p = sum(t["proxies"]["bytes"] for t in man["tiles"].values())
    tparts = [t["parts"] for t in man["tiles"].values() if t.get("parts")]
    disk_q = sum(t["bytes"] for t in tparts)
    by_part: dict[str, list] = {}
    drawn = 0
    for r in recs.values():
        for x in r.get("parts", []):
            v = by_part.setdefault(x["type"], [0, 0])
            v[0] += x["count"]
            v[1] += x["count"] * x["triangles"]
            drawn += x["count"] * x["triangles"]
    meshes = sum(t["meshes"] for t in tparts)
    mesh_tri = sum(t["triangles"] for t in tparts)
    sk = man.get("skybridges") or {}
    kinds: dict[str, int] = {}
    for r in sk.values():
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    return {
        "city": man["city"], "assetgen": man["assetgen"], "generator": man["generator"],
        "buildings": len(recs), "tiles": len(man["tiles"]),
        "triangles": {"shells": tri, "proxies": ptri,
                      "per_building": round(tri / max(len(recs), 1), 1),
                      "proxy": {"min": pt[0] if pt else 0, "median": pt[len(pt) // 2] if pt
                                else 0, "max": pt[-1] if pt else 0},
                      "by_slot": dict(sorted(by_slot.items())),
                      "by_type": dict(sorted(by_type.items())),
                      "part_meshes": mesh_tri, "unique": tri + mesh_tri,
                      "drawn": tri + drawn},
        "parts": {"meshes": meshes, "instances": sum(v[0] for v in by_part.values()),
                  "merged": int(stats.get("parts_merged", 0)),
                  "by_type": {k: {"instances": v[0], "triangles": v[1]}
                              for k, v in sorted(by_part.items())}},
        "disk": {"tiles_bytes": disk_t, "proxies_bytes": disk_p, "parts_bytes": disk_q,
                 "bytes_per_triangle": round(disk_t / max(tri, 1), 1)},
        "stats": {k: round(v, 2) if isinstance(v, float) else
                  (dict(sorted(v.items())) if isinstance(v, dict) else v)
                  for k, v in sorted(stats.items())},
        "skybridges": {"count": len(sk), "by_kind": dict(sorted(kinds.items())),
                       "triangles": sum(r["triangles"] for r in sk.values()),
                       "bytes": sum(f["bytes"] for f in (man.get("connections") or {}).values())},
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
             f"parts: {rep['parts']['meshes']:,} meshes ({t['part_meshes']:,} triangles), "
             f"{rep['parts']['instances']:,} instances, {rep['parts']['merged']:,} merged "
             f"into shells; unique triangles {t['unique']:,}, drawn {t['drawn']:,}",
             f"disk: tiles {rep['disk']['tiles_bytes'] / 1e6:.1f} MB "
             f"({rep['disk']['bytes_per_triangle']} B per triangle), proxies "
             f"{rep['disk']['proxies_bytes'] / 1e6:.1f} MB, parts "
             f"{rep['disk']['parts_bytes'] / 1e6:.1f} MB",
             f"skybridges: {rep['skybridges']['count']} {rep['skybridges']['by_kind']}, "
             f"{rep['skybridges']['triangles']:,} triangles, "
             f"{rep['skybridges']['bytes'] / 1e6:.1f} MB", ""]
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
    lines.append("instances by part: " + ", ".join(
        f"{k} {v['instances']:,}" for k, v in rep["parts"]["by_type"].items()))
    lines.append("stats: " + ", ".join(f"{k} {v}" for k, v in rep["stats"].items()))
    s = rep["seconds"]
    lines.append(f"seconds: {s} with {rep['workers']} workers "
                 f"({rep['tiles_made']} tiles made, {rep['tiles_kept']} kept)")
    st = rep.get("streets")
    if st is not None:
        lines.append(f"streets: {st['pieces']} pieces in {st['tiles']} tiles, "
                     f"{st['triangles']:,} triangles, {st['disk_bytes'] / 1e6:.1f} MB; "
                     f"{'all checks pass' if st['ok'] else 'FAIL ' + ', '.join(st['failed'])}"
                     f" ({st['tiles_made']} tiles made, {st['seconds']} s; streets_report.txt)")
    pr = rep.get("props")
    if pr is not None:
        lines.append(f"props: {pr['variants']} variants, {pr['instances']:,} instances, "
                     f"{pr['signs']:,} signs, {pr['unique_triangles']:,} triangles, "
                     f"{pr['disk_bytes'] / 1e6:.1f} MB; "
                     f"{'all checks pass' if pr['ok'] else 'FAIL ' + ', '.join(pr['failed'])}"
                     f" ({pr['tiles_made']} tiles made, {pr['seconds']} s; props_report.txt)")
    ma = rep.get("materials")
    if ma is not None:
        lines.append(f"materials: {ma['textures']} textures; "
                     f"{'all checks pass' if ma['ok'] else 'FAIL ' + ', '.join(ma['failed'])}"
                     f" ({ma['seconds']} s; materials_report.txt)")
    return "\n".join(lines) + "\n"
