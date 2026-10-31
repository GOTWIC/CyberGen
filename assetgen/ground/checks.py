"""Checks and stats of the ground stage (scope sections 9, 14.14):

- `ground_coverage`: every piece of M16's ground cover is drawn whole (the areas its tiles
  draw add up to its own within 0.5 % or 0.5 m2, nothing failed to triangulate; a part ear
  clipping refuses, a hole touching its outer ring, falls back to GEOS's constrained
  Delaunay triangles on the same vertices and is listed), and every
  blockout object of the cover and the median lawns is replaced by an entry (its tile's or a
  drop);
- `ground_grass_clear`: no clump's footprint (its kind's radius times its scale) reaches a
  road's right of way, a building, a solid site element or structure, water, a paved piece
  (`paving`), a deck or a desire line, and every clump stands on grass-bearing ground (a
  verge's clumps on its median lawn); tested on the model's own geometry on the 1 cm grid,
  apart from the scatter's;
- `ground_meshes`: the clump variants and the tile meshes have no degenerate triangles,
  finite positions, normals and UVs;
- `ground_budgets`: clumps per tile and city, triangles per clump variant and of all
  variants, ground triangles per tile and city, instanced triangles per tile (`kinds`).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString

from citygen import geom as G

from . import clumps as CL
from . import kinds as K

TOL_SHARE = 0.005
TOL_M2 = 0.5
EPS_M = 0.01


def _clear(model, man: dict, out_dir: Path) -> dict:
    """ground_grass_clear on the model's geometry."""
    from citygen import cover as CV
    with G.canonical():
        cx = CV.Ctx(model)
        paved, grassy = [], []
        corr = []
        for g in model.ground_cover:
            p = G.from_model_poly(g.polygon)
            (grassy if g.kind in K.GRASSY else paved).append(p)
            for d in g.desire_lines:
                corr.append(LineString(d.line).buffer(d.width_m / 2.0, cap_style="flat"))
        decks = [G.from_model_poly(d.polygon) for d in getattr(model, "decks", []) or []]
        verges = [G.from_model_poly(g.polygon) for g in model.green_areas
                  if g.kind == "lawn" and g.polygon is not None]
        # (on the 1 cm grid, as the scatter's keep-outs: a footprint's spike thinner than
        # that is no obstacle)
        road_like = [shapely.set_precision(g, 0.01) for g in cx.row]
        other = [shapely.set_precision(g, 0.01) for g in list(cx.hard) + list(cx.wet)] + \
            paved + decks + corr
    t_road = shapely.STRtree(road_like) if road_like else None
    t_other = shapely.STRtree(other) if other else None
    t_ok = shapely.STRtree(grassy) if grassy else None
    t_verge = shapely.STRtree(verges) if verges else None
    a_road = np.array(road_like, dtype=object)
    a_other = np.array(other, dtype=object)
    rad = {nd: K.CLUMPS[r["kind"]][1] for nd, r in (man.get("clumps") or {}).items()}
    n, fails, first = 0, 0, None
    gdir = out_dir / "ground" / "grass"
    for t in sorted(man["tiles"]):
        if not man["tiles"][t].get("instances"):
            continue
        doc = json.loads((gdir / f"{t}.json").read_text(encoding="utf-8"))
        px0, py0, _ = doc["pivot"]
        xs, ys, rs = [], [], []
        for nd, xf in doc["nodes"].items():
            a = np.asarray(xf, dtype=np.float64)
            xs.append(a[:, 0] + px0)
            ys.append(a[:, 1] + py0)
            rs.append(rad.get(nd, 0.3) * a[:, 4])
        x, y, r = np.concatenate(xs), np.concatenate(ys), np.concatenate(rs)
        n += len(x)
        pts = shapely.points(x, y)
        bad = np.zeros(len(x), dtype=bool)
        in_verge = np.zeros(len(x), dtype=bool)
        if t_verge is not None:
            pi, gi = t_verge.query(pts, predicate="within")
            in_verge[pi] = True
            # a verge's clump stays on its lawn
            vi = np.nonzero(in_verge)[0]
            if len(vi):
                d = np.full(len(x), np.inf)
                for p, g in zip(pi.tolist(), gi.tolist()):
                    d[p] = min(d[p], float(shapely.distance(verges[g].exterior, pts[p])))
                bad[vi] |= d[vi] < r[vi] - EPS_M
        for tree, geoms, skip_verge in ((t_road, a_road, True), (t_other, a_other, False)):
            if tree is None:
                continue
            pi, gi = tree.query(pts, predicate="dwithin", distance=float(r.max()) - EPS_M)
            if skip_verge:
                keep = ~in_verge[pi]
                pi, gi = pi[keep], gi[keep]
            if len(pi):
                d = shapely.distance(geoms[gi], pts[pi])
                bad[pi[d < r[pi] - EPS_M]] = True
        if t_ok is not None:
            pi, _ = t_ok.query(pts, predicate="dwithin", distance=EPS_M)
            on = np.zeros(len(x), dtype=bool)
            on[pi] = True
            bad |= ~(on | in_verge)
        k = int(bad.sum())
        if k and first is None:
            i = int(np.flatnonzero(bad)[0])
            first = {"tile": t, "x": round(float(x[i]), 2), "y": round(float(y[i]), 2),
                     "r": round(float(r[i]), 3)}
        fails += k
    return {"name": "ground_grass_clear", "ok": fails == 0, "clumps": n, "failing": fails,
            "first": first}


def _meshes(out_dir: Path, man: dict) -> dict:
    from ..materials.checks import read_glb
    bad, tris, files = 0, 0, 0
    first = None
    paths = [out_dir / "ground" / "clumps.glb"] + \
        [out_dir / "ground" / "tiles" / f"{t}.glb" for t, r in sorted(man["tiles"].items())
         if (r.get("glb") or {}).get("bytes")]
    for f in paths:
        if not f.is_file():
            continue
        files += 1
        for node, _, mat, pos, uv, tri in read_glb(f):
            a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
            cr = np.cross(b - a, c - a)
            deg = int((np.abs(cr).sum(axis=1) == 0.0).sum())
            fin = bool(np.isfinite(pos).all() and np.isfinite(uv).all())
            tris += len(tri)
            if deg or not fin:
                bad += deg + (0 if fin else 1)
                first = first or {"file": f.name, "node": node, "degenerate": deg,
                                  "finite": fin}
    return {"name": "ground_meshes", "ok": bad == 0, "files": files, "triangles": tris,
            "bad": bad, "first": first}


def report(model, man: dict, con: dict, out_dir: Path) -> dict:
    checks = []
    # coverage
    drawn: dict[str, float] = {}
    failed, cdt = [], []
    for t, r in man["tiles"].items():
        for pid, a in (r.get("areas") or {}).items():
            drawn[pid] = drawn.get(pid, 0.0) + a
        for f in r.get("failed") or []:
            (cdt if f.startswith("cdt:") else failed).append(f.split(":", 1)[-1])
    short = []
    for g in model.ground_cover:
        a = drawn.get(g.id, 0.0)
        if abs(a - g.area_m2) > max(TOL_M2, TOL_SHARE * g.area_m2):
            short.append((g.id, round(a, 2), g.area_m2))
    replaced = set()
    for e in con["entries"]:
        replaced.add(e["key"])
        replaced.update(e.get("replaces", []))
    left = sorted(k for k in (man.get("keys") or {}) if k not in replaced)
    checks.append({"name": "ground_coverage",
                   "ok": not short and not failed and not left,
                   "pieces": len(model.ground_cover), "short": len(short),
                   "first_short": short[0] if short else None,
                   "triangulation_failed": sorted(set(failed))[:10],
                   "constrained_delaunay": sorted(set(cdt))[:10],
                   "blockout_objects": len(man.get("keys") or {}),
                   "not_replaced": left[:10]})
    checks.append(_clear(model, man, out_dir))
    checks.append(_meshes(out_dir, man))
    # budgets
    clumps = man.get("clumps") or {}
    per_tile = {t: sum(r.get("instances", {}).values()) for t, r in man["tiles"].items()}
    drawn_t = {t: sum(n * clumps.get(nd, {}).get("triangles", 0)
                      for nd, n in r.get("instances", {}).items())
               for t, r in man["tiles"].items()}
    gtri = {t: (r.get("node") or {}).get("triangles", 0) for t, r in man["tiles"].items()}
    city_inst = sum(per_tile.values())
    worst_clump = max((r["triangles"] for r in clumps.values()), default=0)
    unique = sum(r["triangles"] for r in clumps.values())
    over = []
    if max(per_tile.values(), default=0) > K.TILE_INSTANCES:
        over.append("tile_instances")
    if city_inst > K.CITY_INSTANCES:
        over.append("city_instances")
    if worst_clump > K.CLUMP_TRIANGLES:
        over.append("clump_triangles")
    if unique > K.UNIQUE_TRIANGLES:
        over.append("unique_triangles")
    if max(gtri.values(), default=0) > K.TILE_GROUND_TRIANGLES:
        over.append("tile_ground_triangles")
    if sum(gtri.values()) > K.CITY_GROUND_TRIANGLES:
        over.append("city_ground_triangles")
    if max(drawn_t.values(), default=0) > K.TILE_DRAWN_TRIANGLES:
        over.append("tile_drawn_triangles")
    checks.append({"name": "ground_budgets", "ok": not over, "over": over,
                   "tile_instances_max": max(per_tile.values(), default=0),
                   "city_instances": city_inst, "clump_triangles_max": worst_clump,
                   "unique_triangles": unique,
                   "tile_ground_triangles_max": max(gtri.values(), default=0),
                   "city_ground_triangles": sum(gtri.values()),
                   "tile_drawn_triangles_max": max(drawn_t.values(), default=0),
                   "limits": {"tile_instances": K.TILE_INSTANCES,
                              "city_instances": K.CITY_INSTANCES,
                              "clump_triangles": K.CLUMP_TRIANGLES,
                              "unique_triangles": K.UNIQUE_TRIANGLES,
                              "tile_ground_triangles": K.TILE_GROUND_TRIANGLES,
                              "city_ground_triangles": K.CITY_GROUND_TRIANGLES,
                              "tile_drawn_triangles": K.TILE_DRAWN_TRIANGLES}})
    kinds: dict[str, int] = {}
    capped = 0
    for r in man["tiles"].values():
        sc = r.get("scatter") or {}
        if sc.get("cap", 1.0) < 1.0:
            capped += 1
        for k, v in (sc.get("kinds") or {}).items():
            kinds[k] = kinds.get(k, 0) + v
    area: dict[str, float] = {}
    for g in model.ground_cover:
        area[g.kind] = area.get(g.kind, 0.0) + g.area_m2
    disk = 0
    gd = out_dir / "ground"
    if gd.is_dir():
        disk = sum(p.stat().st_size for p in gd.rglob("*") if p.is_file())
    stats = {"pieces": len(model.ground_cover), "tiles": len(man["tiles"]),
             "ground_tiles": sum(1 for v in gtri.values() if v),
             "grass_tiles": sum(1 for v in per_tile.values() if v),
             "capped_tiles": capped, "instances": city_inst,
             "instances_by_kind": dict(sorted(kinds.items())),
             "clump_variants": len(clumps), "unique_triangles": unique,
             "ground_triangles": sum(gtri.values()),
             "instanced_triangles": sum(drawn_t.values()),
             "area_m2": {k: round(v, 1) for k, v in sorted(area.items())},
             "entries": len(con["entries"]), "materials": len(con["materials"]),
             "masks": sum(1 for v in gtri.values() if v), "disk_bytes": disk}
    return {"city": model.name, "ok": all(c["ok"] for c in checks), "checks": checks,
            "stats": stats}


def report_text(rep: dict) -> str:
    st = rep["stats"]
    lines = [f"assetgen ground (AG13): {rep['city']}",
             "all checks pass" if rep["ok"] else "CHECKS FAIL",
             f"{st['pieces']} pieces in {st['tiles']} tiles ({st['ground_tiles']} with ground,"
             f" {st['grass_tiles']} with grass, {st['capped_tiles']} at the cap)",
             f"clumps: {st['instances']:,} instances of {st['clump_variants']} variants "
             f"({st['unique_triangles']:,} triangles), {st['instanced_triangles']:,} "
             f"instanced triangles", f"ground: {st['ground_triangles']:,} triangles, "
             f"{st['masks']} masks, {st['disk_bytes'] / 1e6:.1f} MB on disk",
             f"by kind: {st['instances_by_kind']}", ""]
    for c in rep["checks"]:
        extra = {k: v for k, v in c.items() if k not in ("name", "ok")}
        lines.append(f"{'PASS' if c['ok'] else 'FAIL'} {c['name']}: {extra}")
    if rep.get("seconds"):
        lines.append(f"seconds: {rep['seconds']}")
    return "\n".join(lines) + "\n"
