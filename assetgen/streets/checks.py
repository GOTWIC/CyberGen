"""Checks and stats of the street stage (scope section 9): coverage of every street element,
mesh validity, the blockout objects the pieces replace, budgets, disk.

- `street_coverage`: every entity of the street collections has a piece with a mesh, or a
  declared reason it needs none (a segment wholly inside its junctions, a creek's natural
  banks); every transit line has guideway, tube or tunnel pieces; every megasite's elements
  are covered; stations are the building line's (their structures are covered here).
- `street_meshes`: no degenerate or duplicate triangles, winding that agrees with the
  normals, indices in range, finite UVs, unit normals, in every piece and LOD.
- `street_replaces`: every blockout object a piece replaces has all its members covered, so
  the exporter can drop it without losing anything.
- `street_budgets`: triangles per tile and per city within budget.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .build import CITY_TRIANGLE_BUDGET, COVERED, TILE_TRIANGLE_BUDGET

DECLARED = ("inside its junctions", "natural banks")


def report(model, cx, manifest: dict, pieces) -> dict:
    recs = manifest["pieces"]
    checks = []
    cov = {}
    missing = []
    # (pieces that stand for entities of other ids: M14's slab pieces, its deck)
    covers = defaultdict(list)
    for pid, r in sorted(recs.items()):
        for c in r.get("covers", ()):
            covers[c].append(pid)
    for name in COVERED:
        n = with_mesh = declared = 0
        for e in getattr(model, name):
            n += 1
            r = recs.get(e.id)
            if r is None and covers.get(e.id):
                # (a deck: covered when every piece standing for it has a mesh)
                if all(recs[p].get("triangles", 0) > 0 for p in covers[e.id]):
                    with_mesh += 1
                else:
                    missing.append(e.id)
                continue
            if r is None:
                missing.append(e.id)
                continue
            if r.get("triangles", 0) > 0 or r.get("parts"):
                with_mesh += 1
            elif r.get("empty") in DECLARED:
                declared += 1
            else:
                missing.append(e.id)
        cov[name] = {"entities": n, "assets": with_mesh, "declared": declared}
    # transit lines through their structures and tunnels
    lines = defaultdict(int)
    for p in pieces:
        st = p.inputs.get("st") or {}
        lid = (st.get("attrs") or {}).get("line_id")
        t = p.inputs.get("tunnel") or {}
        if p.maker == "tunnel":
            lid = lid or t.get("line_id")
        if lid and recs.get(p.id, {}).get("triangles", 0) > 0:
            lines[lid] += 1
    n_lines = len(model.transit_lines)
    miss_lines = [t.id for t in model.transit_lines if not lines.get(t.id)]
    missing += miss_lines
    cov["transit_lines"] = {"entities": n_lines, "assets": n_lines - len(miss_lines),
                            "declared": 0}
    by_site = defaultdict(list)
    for e in model.site_elements:
        if e.megasite_id:
            by_site[e.megasite_id].append(e.id)
    ok_sites = sum(1 for s in model.megasites
                   if all(recs.get(i, {}).get("triangles", 0) > 0 or recs.get(i, {}).get("parts")
                          for i in by_site.get(s.id, [])))
    cov["megasites"] = {"entities": len(model.megasites), "assets": ok_sites, "declared": 0}
    if ok_sites < len(model.megasites):
        missing += [s.id for s in model.megasites if not all(
            recs.get(i, {}).get("triangles", 0) > 0 or recs.get(i, {}).get("parts")
            for i in by_site.get(s.id, []))]
    st_parts = defaultdict(int)
    for s in model.structures:
        sid = (s.attrs or {}).get("station")
        if sid and recs.get(s.id, {}).get("triangles", 0) > 0:
            st_parts[sid] += 1
    cov["stations"] = {"entities": len(model.stations),
                       "structures_with_assets": sum(1 for s in model.stations
                                                     if st_parts.get(s.id)),
                       "note": "stations are buildings (the building line, AG5); their "
                               "platforms, canopies, skywalks, cores and concourses are here"}
    checks.append({"id": "street_coverage", "ok": not missing,
                   "detail": f"{len(missing)} without an asset" + (
                       f": {', '.join(sorted(missing)[:8])}" if missing else "")})
    # meshes
    bad = Counter()
    for pid, r in recs.items():
        for k, v in (r.get("checks") or {}).items():
            bad[k] += v
        for ex in r.get("extra", []):
            for lo in ex["lods"]:
                for k, v in (lo.get("checks") or {}).items():
                    bad[k] += v
    checks.append({"id": "street_meshes", "ok": not bad,
                   "detail": "no bad triangles" if not bad else
                   ", ".join(f"{k} {v}" for k, v in sorted(bad.items()))})
    # replaced blockout objects: every member covered
    members = defaultdict(list)
    for eid, names in cx.keys.items():
        for n in names:
            members[n].append(eid)
    replaced = sorted({k for r in recs.values() for k in r.get("replaces", [])})
    partial = []
    for n in replaced:
        for eid in members.get(n, []):
            r = recs.get(eid)
            if r is None and covers.get(eid) and n in covers[eid] and \
                    recs[n].get("triangles", 0) > 0:
                continue        # (M14: the slab piece of that name stands for its deck)
            if r is None or not (r.get("triangles", 0) > 0 or r.get("parts") or
                                 r.get("empty") in DECLARED or eid in _covered_by_parent(model, eid)):
                partial.append(n)
                break
    checks.append({"id": "street_replaces", "ok": not partial,
                   "detail": f"{len(replaced)} blockout objects replaced" + (
                       f", {len(partial)} not wholly covered: {', '.join(partial[:6])}"
                       if partial else "")})
    if model.decks:
        from .decks import check as deck_check
        checks.append(deck_check(model, cx, recs))
    # budgets
    tri_tile = {t: v.get("triangles", 0) for t, v in manifest["tiles"].items()}
    total = sum(tri_tile.values())
    worst = max(tri_tile.items(), key=lambda kv: (kv[1], kv[0])) if tri_tile else ("", 0)
    checks.append({"id": "street_budgets",
                   "ok": worst[1] <= TILE_TRIANGLE_BUDGET and total <= CITY_TRIANGLE_BUDGET,
                   "detail": f"{total} triangles in the city (budget {CITY_TRIANGLE_BUDGET}), "
                             f"at most {worst[1]} in a tile ({worst[0]}, budget "
                             f"{TILE_TRIANGLE_BUDGET})"})
    kinds = Counter()
    tri_kind = Counter()
    empties = Counter()
    pads = [0, 0]
    pad_why = Counter()
    bridges = Counter()
    instances = Counter()
    for r in recs.values():
        k = r["kind"]
        kinds[k] += 1
        tri_kind[k] += r.get("triangles", 0)
        for ex in r.get("extra", []):
            tri_kind[k + ex["suffix"]] += ex["lods"][0]["triangles"]
        if r.get("empty"):
            empties[r["empty"]] += 1
        n = r.get("notes") or {}
        if "corner_pads" in n:
            pads[0] += n["corner_pads"][0]
            pads[1] += n["corner_pads"][1]
            if len(n["corner_pads"]) > 2:
                pad_why.update(n["corner_pads"][2])
        if "bridge_kind" in n:
            bridges[n["bridge_kind"]] += 1
        for p in r.get("parts", []):
            instances[p["kind"]] += len(p["xforms"])
    disk = sum(v.get("bytes", 0) for v in manifest["tiles"].values()) + \
        manifest["parts"]["bytes"]
    return {"city": model.name, "ok": all(c["ok"] for c in checks), "checks": checks,
            "coverage": cov,
            "stats": {"pieces": len(recs), "tiles": len(manifest["tiles"]),
                      "triangles": total, "max_tile_triangles": worst[1],
                      "disk_bytes": disk, "by_kind": dict(sorted(kinds.items())),
                      "triangles_by_kind": dict(sorted(tri_kind.items())),
                      "empty": dict(sorted(empties.items())),
                      "corner_pads": {"made": pads[0], "skipped": pads[1],
                                      "why": dict(sorted(pad_why.items()))},
                      "bridges": dict(sorted(bridges.items())),
                      "instances": dict(sorted(instances.items())),
                      "walkways_on_decks": sum(len((r.get("notes") or {}).get("walkways") or {})
                                               for r in recs.values())}}


def _covered_by_parent(model, eid: str) -> set:
    return set()


def report_text(rep: dict) -> str:
    st = rep["stats"]
    lines = [f"assetgen streets: {rep['city']}: {'PASS' if rep['ok'] else 'FAIL'}", ""]
    for c in rep["checks"]:
        lines.append(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['id']}: {c['detail']}")
    lines += ["", "coverage:"]
    for k, v in rep["coverage"].items():
        if "assets" in v:
            lines.append(f"  {k}: {v['assets']} of {v['entities']}"
                         + (f" (+{v['declared']} declared)" if v.get("declared") else ""))
        else:
            lines.append(f"  {k}: {v['entities']} ({v['note']})")
    lines += ["", f"pieces {st['pieces']}, tiles {st['tiles']}, triangles {st['triangles']}, "
                  f"disk {st['disk_bytes'] / 1e6:.1f} MB"]
    lines.append("triangles by kind:")
    for k, v in sorted(st["triangles_by_kind"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {k}: {v} ({st['by_kind'].get(k, 0)} pieces)")
    if st["empty"]:
        lines.append("no mesh: " + ", ".join(f"{k} {v}" for k, v in st["empty"].items()))
    lines.append(f"corner pads: {st['corner_pads']['made']} made, "
                 f"{st['corner_pads']['skipped']} skipped "
                 f"({', '.join(f'{k} {v}' for k, v in st['corner_pads']['why'].items())})")
    if st["bridges"]:
        lines.append("bridges: " + ", ".join(f"{k} {v}" for k, v in st["bridges"].items()))
    if st["instances"]:
        lines.append("instances: " + ", ".join(f"{k} {v}" for k, v in st["instances"].items()))
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
