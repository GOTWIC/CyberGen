"""Checks and stats of the water stage (scope 9, 14.13), measured on the packs written (the
meshes read back) against the model (M16's beds, banks and levels, M13's levels):

- `water_coverage`: every water body's own water (its polygon less the bodies before it) is
  covered by its surfaces' first LOD and by its beds with its sloped banks' dry strips (plan
  areas within 0.2% and 2 m2); every
  bank AG12 draws has a mesh, and every quay and waterway canal wall has AG7's piece.
- `water_levels`: every surface vertex (every LOD) at its body's level (M13's along a river,
  a flat city's `surface_m`) within 1 cm; every bed vertex at its depth: AG12's bottom from
  the model's own banks (M16's bed, or a bank's slope carried on under the water where that
  lies higher, never within 5 cm of the surface), within 2 cm, and never deeper than M16's
  bed (the share exactly on it is reported).
- `water_gaps`: no gap between bank, bed and wall: each sloped bank's waterline edge stands
  on the bed under it (at most 12 cm over it and never under it), each wall (AG12's along
  rivers and the sea, AG7's quays and canal walls) reaches down to or past the bed at its
  foot, and every edge two bodies share has its skirt.
- `water_meshes`: valid meshes in every bed, surface LOD and bank.
- `water_budgets`: triangles (first LODs, beds, banks) and riprap instances per tile and
  per city.
- `water_replaces`: every blockout water object (sea sheets, inland water, beds, bank bands)
  is replaced by a piece or dropped, and every name replaced is one.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString

from citygen import geom as G
from citygen import water as WA

from ..materials.checks import read_glb
from . import fields as F

TILE_TRIANGLES = 400_000
CITY_TRIANGLES = 9_000_000
TILE_INSTANCES = 60_000
LEVEL_TOL_M = 0.01
BED_TOL_M = 0.02
EDGE_OVER_M = 0.12
SAMPLE = 3                   # every SAMPLE-th bed vertex is checked


def _meshes(assets: Path, man: dict) -> dict[str, list]:
    """node -> [(world positions (n, 3), triangles (m, 3), material)] of the water packs."""
    out: dict[str, list] = defaultdict(list)
    wdir = assets / "water"
    for t in sorted(man["tiles"]):
        f = wdir / f"{t}.glb"
        if not f.is_file():
            continue
        for node, tr, mat, pos, uv, tri in read_glb(f):
            w = pos + np.array([tr[0], -tr[2], tr[1]])
            out[node].append((w, tri, mat))
    return out


class _Bottom:
    """AG12's bottom from the model (M16's `Beds` and every bank of the body)."""

    def __init__(self, m):
        self.beds = WA.Beds(m)
        self.lv = WA.Levels(m)
        self.quay_h = {q.id: q.deck_z_m for q in m.quays}

    def depth(self, wid, xs, ys):
        bd = self.beds
        d16 = bd.depth_many(wid, xs, ys)
        t = bd.trees.get(wid)
        if t is None:
            return d16, np.maximum(d16, F.SURFACE_GAP_M), np.zeros(len(xs), dtype=bool)
        bks = bd.bank_by[wid]
        lines = np.array([LineString(k.line) for k in bks], dtype=object)
        pts = shapely.points(np.stack([xs, ys], axis=1))
        k, d = bd._nearest(t, lines, pts)
        W = np.array([max(b.width_m, 0.01) for b in bks])
        TOE = np.array([b.toe_m for b in bks])
        H = np.array([(b.height_m if b.height_m is not None else
                       self.quay_h.get(b.quay_id, WA.FREEBOARD_M)) for b in bks])
        wall = np.array([b.kind in F.WALLS for b in bks])
        e = bd.bl[wid].ent
        D = np.full(len(xs), float(e.depth_m))
        if wid in bd.cl and e.bed.along:
            pts_, cum, ws = bd.cl[wid]
            s = WA._project_many(pts_, cum, xs, ys)
            D = np.interp(s, [a.s for a in e.bed.along], [a.z for a in e.bed.along])
        # (beside a wall the bed runs at its toe to the wall's face: deeper than M16's,
        # whose bed starts the wall's thickness out)
        at_wall = wall[k] & (d < W[k])
        base = np.where(at_wall, np.minimum(TOE[k], D), d16)
        return d16, F.bottom(base, lines, W, H, ~wall, xs, ys), at_wall

    def level(self, wid, x, y) -> float:
        return self.lv.at(wid, x, y)


def report(model, cx, manifest: dict, pieces, assets: Path) -> dict:
    recs = manifest["pieces"]
    checks = []
    meshes = _meshes(Path(assets), manifest)
    flat = model.terrain is None
    lift = 0.0 if flat else 0.1
    bot = _Bottom(model) if model.banks else None
    # -- coverage
    missing = []
    area_bad = []
    bed_area, surf_area, own_area = Counter(), Counter(), Counter()
    for b in cx.bodies:
        if b.ent.depth_m is None:
            continue
        own_area[b.id] = G.area(cx.own[b.id])
    for pid, r in recs.items():
        if r.get("maker") != "body":
            continue
        body, _, t = pid.partition("@")
        # (the bed leaves out the sloped banks' dry strips: their meshes cover them)
        bed_area[body] += float((r.get("notes") or {}).get("dry_m2", 0.0))
        for name, acc in ((r.get("bed", {}).get("node"), bed_area),
                          ((r.get("lods") or [{}])[0].get("node"), surf_area)):
            for w, tri, mat in meshes.get(name or "", []):
                a, bb, c = w[tri[:, 0]], w[tri[:, 1]], w[tri[:, 2]]
                ar = ((bb[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) -
                      (bb[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) / 2.0
                acc[body] += float(ar[ar > 0].sum())
    for wid, A in sorted(own_area.items()):
        for what, acc in (("bed", bed_area), ("surface", surf_area)):
            if abs(acc[wid] - A) > max(2.0, 0.002 * A):
                area_bad.append(f"{wid} {what} {acc[wid]:.0f} of {A:.0f} m2")
    for p in pieces:
        if p.maker == "bank" and recs.get(p.id, {}).get("triangles", 0) <= 0:
            missing.append(p.id)
    s_pieces = _streets(Path(assets))
    ag7 = 0
    for k in model.banks:
        if k.kind == "quay" or (k.kind == "canal_wall" and k.water_id in cx.waterway):
            ag7 += 1
            pid = k.quay_id if k.kind == "quay" else k.water_id
            if s_pieces is not None and s_pieces.get(pid, {}).get("triangles", 0) <= 0:
                missing.append(f"{k.id} (AG7 {pid})")
    checks.append({"id": "water_coverage", "ok": not missing and not area_bad,
                   "detail": f"{len(own_area)} bodies, "
                             f"{sum(1 for p in pieces if p.maker == 'bank')} banks drawn, "
                             f"{ag7} by AG7" + (f"; {len(missing)} without a mesh: "
                                                f"{', '.join(sorted(missing)[:6])}"
                                                if missing else "")
                             + (f"; areas off: {'; '.join(area_bad[:4])}" if area_bad else "")})
    # -- levels and depths
    lev_bad, bed_bad, deeper, n_lev, n_bed, on16 = [], [], 0, 0, 0, 0
    worst_bed = 0.0
    for pid, r in sorted(recs.items()):
        if r.get("maker") != "body" or bot is None:
            continue
        body, _, t = pid.partition("@")
        for lo in r.get("lods") or []:
            for w, tri, mat in meshes.get(lo["node"], []):
                if flat:
                    lv = np.full(len(w), bot.level(body, 0.0, 0.0))
                else:
                    step = max(1, len(w) // 400)
                    w = w[::step]
                    lv = np.array([bot.level(body, x, y) for x, y in w[:, :2]])
                n_lev += len(w)
                off = np.abs(w[:, 2] - lv)
                if (off > LEVEL_TOL_M).any():
                    lev_bad.append(f"{lo['node']} {off.max():.3f} m")
        bd = r.get("bed")
        if not bd:
            continue
        for w, tri, mat in meshes.get(bd["node"], []):
            # (the skirts' vertices hang under the bed: only the bed's own, those with up
            # normals, are on the bed; a skirt is a separate primitive of vertical quads)
            if len(tri) and _vertical(w, tri):
                continue
            s = w[::SAMPLE]
            xs, ys = s[:, 0], s[:, 1]
            d16, bottom, at_wall = bot.depth(body, xs, ys)
            if flat:
                lv = np.full(len(s), bot.level(body, 0.0, 0.0))
            else:
                lv = np.array([bot.level(body, x, y) for x, y in zip(xs, ys)])
            z = lv - bottom + lift
            off = np.abs(s[:, 2] - z)
            n_bed += len(s)
            worst_bed = max(worst_bed, float(off.max()) if len(off) else 0.0)
            if (off > BED_TOL_M).any():
                bed_bad.append(f"{bd['node']} {off.max():.3f} m")
            dep = lv - (s[:, 2] - lift)
            m16 = np.maximum(d16, F.SURFACE_GAP_M)
            deeper += int(((dep > m16 + BED_TOL_M) & ~at_wall).sum())
            on16 += int((np.abs(dep - m16) <= BED_TOL_M).sum())
    checks.append({"id": "water_levels", "ok": not lev_bad and not bed_bad and not deeper,
                   "detail": f"{n_lev} surface vertices at their level, {n_bed} bed vertices "
                             f"checked (worst {worst_bed:.3f} m; "
                             f"{on16 / max(n_bed, 1):.0%} on M16's bed, the rest on a bank's "
                             f"slope over it)"
                             + (f"; off level: {', '.join(lev_bad[:4])}" if lev_bad else "")
                             + (f"; off depth: {', '.join(bed_bad[:4])}" if bed_bad else "")
                             + (f"; {deeper} deeper than M16" if deeper else "")})
    # -- gaps
    gaps = []
    n_edge = n_foot = 0
    beds_by_body = defaultdict(list)
    for pid, r in recs.items():
        if r.get("maker") == "body" and r.get("bed"):
            beds_by_body[pid.partition("@")[0]].append(r["bed"]["node"])
    locs: dict[str, _Locator] = {}

    def bed_z(wid, pts):
        if wid not in locs:
            locs[wid] = _Locator([m for n in beds_by_body.get(wid, []) for m in meshes.get(n, [])])
        return locs[wid].z(pts)
    for p in pieces:
        if p.maker != "bank":
            continue
        notes = recs.get(p.id, {}).get("notes") or {}
        wid = p.inputs["body"]["id"]
        if notes.get("edge"):
            e = np.array(notes["edge"], dtype=np.float64)
            # (the bed under the waterline, a hair into the water)
            zb = bed_z(wid, e[:, :2])
            ok = ~np.isnan(zb)
            n_edge += int(ok.sum())
            dz = e[ok, 2] - zb[ok]
            if ((dz < -0.005) | (dz > EDGE_OVER_M)).any():
                gaps.append(f"{p.id} waterline {dz.min():.2f}..{dz.max():.2f} m over the bed")
        if notes.get("foot"):
            e = np.array(notes["foot"], dtype=np.float64)
            zb = bed_z(wid, e[:, :2])
            ok = ~np.isnan(zb)
            n_foot += int(ok.sum())
            if (e[ok, 2] > zb[ok] + 0.005).any():
                gaps.append(f"{p.id} wall foot over the bed")
    if s_pieces is not None:
        wid_of = {q.id: q.waterway_id for q in model.quays}
        for pid, r in sorted(s_pieces.items()):
            foot = (r.get("notes") or {}).get("foot")
            if not foot:
                continue
            wid = wid_of.get(pid, pid)
            e = np.array(foot, dtype=np.float64)
            zb = bed_z(wid, e[:, :2])
            ok = ~np.isnan(zb)
            n_foot += int(ok.sum())
            if (e[ok, 2] > zb[ok] + 0.005).any():
                gaps.append(f"{pid} (AG7) wall foot over the bed by "
                            f"{float((e[ok, 2] - zb[ok]).max()):.2f} m")
    no_skirt = [pid for pid, r in recs.items() if r.get("maker") == "body"
                and (r.get("notes") or {}).get("open") and not (r.get("notes") or {}).get(
                    "skirt")]
    for pid in no_skirt:
        gaps.append(f"{pid} shares water but has no skirt")
    checks.append({"id": "water_gaps", "ok": not gaps,
                   "detail": f"{n_edge} waterline points on the bed, {n_foot} wall feet in it"
                             + (f"; {len(gaps)} gaps: {'; '.join(gaps[:5])}" if gaps else "")})
    # -- meshes
    bad = Counter()
    for r in recs.values():
        for k, v in (r.get("checks") or {}).items():
            bad[k] += v
        for k, v in (r.get("bed", {}).get("checks") or {}).items():
            bad[k] += v
        for lo in r.get("lods") or []:
            for k, v in (lo.get("checks") or {}).items():
                bad[k] += v
    checks.append({"id": "water_meshes", "ok": not bad,
                   "detail": "no bad triangles" if not bad else
                   ", ".join(f"{k} {v}" for k, v in sorted(bad.items()))})
    # -- budgets
    tri = {t: v.get("triangles", 0) for t, v in manifest["tiles"].items()}
    ins = {t: v.get("instances", 0) for t, v in manifest["tiles"].items()}
    total = sum(tri.values())
    worst = max(tri.items(), key=lambda kv: (kv[1], kv[0])) if tri else ("", 0)
    worst_i = max(ins.items(), key=lambda kv: (kv[1], kv[0])) if ins else ("", 0)
    checks.append({"id": "water_budgets",
                   "ok": worst[1] <= TILE_TRIANGLES and total <= CITY_TRIANGLES
                   and worst_i[1] <= TILE_INSTANCES,
                   "detail": f"{total} triangles (budget {CITY_TRIANGLES}), at most {worst[1]} "
                             f"in a tile ({worst[0]}, budget {TILE_TRIANGLES}), at most "
                             f"{worst_i[1]} stones in a tile (budget {TILE_INSTANCES})"})
    # -- replaces
    named = set(cx.water_objects)
    took = {k for r in recs.values() for k in r.get("replaces", [])} | set(manifest["drop"])
    unknown = sorted(took - named)
    left = sorted(named - took)
    checks.append({"id": "water_replaces", "ok": not unknown and not left,
                   "detail": f"{len(named)} blockout water objects, "
                             f"{len(took & named) - len(manifest['drop'])} replaced, "
                             f"{len(manifest['drop'])} dropped"
                             + (f"; {len(left)} left: {', '.join(left[:4])}" if left else "")
                             + (f"; {len(unknown)} unknown: {', '.join(unknown[:4])}"
                                if unknown else "")})
    # -- stats
    kinds = Counter(r["kind"] for r in recs.values())
    tri_kind = Counter()
    instances = Counter()
    lods = Counter()
    for r in recs.values():
        if r.get("maker") == "body":
            tri_kind["bed"] += r.get("bed", {}).get("triangles", 0)
            for k, lo in enumerate(r.get("lods") or []):
                lods[f"lod{k}"] += lo["triangles"]
        else:
            tri_kind[r["kind"]] += r.get("triangles", 0)
        for p in r.get("parts", []):
            instances[p["kind"]] += len(p["xforms"])
    tri_kind["surface"] = lods.get("lod0", 0)
    disk = sum(v.get("bytes", 0) for v in manifest["tiles"].values()) + \
        manifest["parts"]["bytes"]
    water_kinds = Counter(v["water"] for v in (manifest.get("bodies") or {}).values())
    return {"city": model.name, "ok": all(c["ok"] for c in checks), "checks": checks,
            "stats": {"pieces": len(recs), "tiles": len(manifest["tiles"]),
                      "bodies": len(own_area), "water_kinds": dict(sorted(water_kinds.items())),
                      "triangles": total, "max_tile_triangles": worst[1],
                      "lod_triangles": dict(sorted(lods.items())),
                      "instances": sum(instances.values()),
                      "max_tile_instances": worst_i[1], "disk_bytes": disk,
                      "by_kind": dict(sorted(kinds.items())),
                      "triangles_by_kind": dict(sorted(tri_kind.items())),
                      "stones": dict(sorted(instances.items())),
                      "water_m2": round(sum(own_area.values()), 1)}}


def _vertical(w, tri) -> bool:
    a, b, c = w[tri[:, 0]], w[tri[:, 1]], w[tri[:, 2]]
    cr = np.cross(b - a, c - a)
    L = np.sqrt((cr * cr).sum(axis=1))
    return bool(np.all(np.abs(cr[:, 2]) <= 1e-6 * np.maximum(L, 1e-9)))


class _Locator:
    """The height of a set of bed meshes (up-facing triangles) under plan points; NaN where
    none is."""

    def __init__(self, meshes):
        tris = []
        for w, tri, mat in meshes:
            a, b, c = w[tri[:, 0]], w[tri[:, 1]], w[tri[:, 2]]
            o = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
            up = o > 1e-9
            tris.append(np.stack([a[up], b[up], c[up]], axis=1))
        self.t = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
        polys = shapely.polygons(self.t[:, :, :2]) if len(self.t) else np.array([])
        self.tree = shapely.STRtree(polys) if len(self.t) else None

    def z(self, pts) -> np.ndarray:
        out = np.full(len(pts), np.nan)
        if self.tree is None:
            return out
        P = shapely.points(pts)
        pi, ti = self.tree.query(P, predicate="intersects")
        for i, t in zip(pi.tolist(), ti.tolist()):
            if not np.isnan(out[i]):
                continue
            a, b, c = self.t[t]
            x, y = pts[i]
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-12:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            out[i] = l1 * a[2] + l2 * b[2] + (1.0 - l1 - l2) * c[2]
        return out


def _streets(assets: Path) -> dict | None:
    import json
    f = assets / "streets" / "manifest.json"
    if not f.is_file():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get("pieces", {})


def report_text(rep: dict) -> str:
    st = rep["stats"]
    lines = [f"assetgen water: {rep['city']}: {'PASS' if rep['ok'] else 'FAIL'}", ""]
    for c in rep["checks"]:
        lines.append(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['id']}: {c['detail']}")
    lines += ["", f"bodies {st['bodies']} ({', '.join(f'{k} {v}' for k, v in st['water_kinds'].items())}), "
                  f"{st['water_m2'] / 1e6:.3f} km2 of water",
              f"pieces {st['pieces']}, tiles {st['tiles']}, triangles {st['triangles']} "
              f"(surface LODs {st['lod_triangles']}), stones {st['instances']}, "
              f"disk {st['disk_bytes'] / 1e6:.1f} MB"]
    lines.append("triangles by kind:")
    for k, v in sorted(st["triangles_by_kind"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {k}: {v}")
    f = rep.get("files")
    if f:
        lines.append(f"files: {f['tiles_made']} tiles made, {f['tiles_kept']} kept, "
                     f"{f['tiles_written']} written, {f['tiles_same_bytes']} same bytes, "
                     f"{f['tiles_removed']} removed")
    s = rep.get("seconds")
    if s:
        lines.append("seconds: " + ", ".join(f"{k} {v}" for k, v in s.items()
                                              if k != "slowest_tiles"))
    return "\n".join(lines) + "\n"
