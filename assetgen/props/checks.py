"""Checks and stats of the props stage (scope section 9, 14.9):

- `props_coverage`: every M6 prop has an asset (an instance of a variant, an exact mesh, its
  sign slot's sign, or a declared reason it needs none: AG7's median barrier); every plant
  has instances; every sign slot has a sign with a mesh;
- `props_families`: every prop kind the city uses has 4 to 12 variants in each style, every
  plant species 6 to 10 (trees) or 4 to 10 (shrubs, sedum, scrub, ivy), each with a mesh;
- `props_replaces`: every M15 prototype actor of props and plants (one per kind and tile) is
  replaced by an entry of the contributions, so no blockout prototype is left;
- `props_meshes`: no degenerate or duplicate triangles, normals that agree with their faces,
  finite UVs, in every variant, exact mesh, sign and LOD;
- `props_budgets`: triangles per variant, plant and sign; instances per tile and city;
  triangles drawn through instances; unique triangles per city.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from . import build as BD
from . import styles as ST

TREES = ("plane", "maple", "ginkgo", "birch", "linden", "elm", "oak", "ficus", "pine",
         "fan_palm", "date_palm")


def _blockout_keys(model) -> set[str]:
    """The prototype actors M15 makes for props and plants (`citygen/blockout.py`
    `_dressing`): one per kind and tile, for the kinds it has prototypes of."""
    from citygen.blockout import PROTOTYPES
    keys = set()
    for p in model.props:
        kind = p.type.split(".", 1)[1]
        if kind in PROTOTYPES:
            keys.add(f"prop.{kind}.{BD.tile_of(p.position[0], p.position[1])}")
    for p in model.plants:
        kind = p.type.split(".", 1)[1]
        if kind in PROTOTYPES:
            keys.add(f"plant.{kind}.{BD.tile_of(p.position[0], p.position[1])}")
    return keys


def report(model, g, man: dict, con_p: dict, con_s: dict) -> dict:
    checks = []
    # coverage
    have = set()
    for gr in g.groups.values():
        for p in gr["parts"].values():
            have.update(p["ids"])
    missing = []
    for p in model.props:
        if p.id in have or p.id in g.dropped:
            continue
        how = g.covered.get(p.id)
        if how == "exact" or how == "sign slot":
            continue
        missing.append(p.id)
    signs_ok = set()
    for t, items in g.signs.items():
        nodes = (man["tiles"].get(t) or {}).get("signs_nodes") or {}
        for s in items:
            if nodes.get(s["node"], {}).get("triangles", 0) > 0:
                signs_ok.add(s["id"])
    slot_ids = {s.id for s in model.sign_slots}
    plants_missing = [p.id for p in model.plants if p.id not in have]
    signs_missing = sorted(slot_ids - signs_ok)
    sign_props = {s.prop_id for s in model.sign_slots if s.prop_id}
    unslotted = sorted(pid for pid, how in g.covered.items()
                       if how == "sign slot" and pid not in sign_props)
    bad = missing + plants_missing + signs_missing + unslotted
    checks.append({"id": "props_coverage", "ok": not bad,
                   "detail": f"{len(model.props)} props ({len(g.dropped)} on AG7's barriers), "
                             f"{len(model.plants)} plants, {len(slot_ids)} sign slots; "
                             f"{len(bad)} without an asset"
                             + (f": {', '.join(sorted(bad)[:6])}" if bad else "")})
    # families
    fam_bad = []
    for what, name in g.families:
        f = man["families"].get(f"{what}.{name}")
        if f is None:
            fam_bad.append(f"{what}.{name}")
            continue
        if what == "prop":
            n = ST.PROP_VARIANTS[name]
            if not 4 <= n <= 12:
                fam_bad.append(f"{name}: {n} variants")
            for st in ST.STYLES:
                for k in range(n):
                    if f["meshes"].get(ST.variant_name(name, st, k), {}).get("triangles", 0) <= 0:
                        fam_bad.append(ST.variant_name(name, st, k))
        else:
            n = ST.PLANT_VARIANTS[name]
            lo = 6 if name in TREES else 4
            if not lo <= n <= 10:
                fam_bad.append(f"{name}: {n} variants")
            for k in range(n):
                if f["meshes"].get(ST.plant_name(name, k), {}).get("triangles", 0) <= 0:
                    fam_bad.append(ST.plant_name(name, k))
    kinds = sorted(k for k in g.kinds if k not in ST.SLOTTED and k not in ST.EXACT)
    no_family = [k for k in kinds if ("prop", k) not in g.families]
    fam_bad += no_family
    species = sorted(g.species)
    checks.append({"id": "props_families", "ok": not fam_bad,
                   "detail": f"{len(kinds)} prop kinds in {len(ST.STYLES)} styles, "
                             f"{len(species)} plant species" +
                             (f"; {len(fam_bad)} wrong: {', '.join(fam_bad[:6])}" if fam_bad
                              else "")})
    # replaces
    keys = _blockout_keys(model)
    got = {e["key"] for e in con_p["entries"]}
    for e in con_s["entries"]:
        got.update(e.get("replaces", []))
    left = sorted(keys - got)
    checks.append({"id": "props_replaces", "ok": not left,
                   "detail": f"{len(keys)} prototype actors, {len(keys) - len(left)} replaced"
                             + (f"; left: {', '.join(left[:6])}" if left else "")})
    # meshes
    badm = Counter()
    for f in man["families"].values():
        for r in f["meshes"].values():
            badm.update(r.get("checks") or {})
    for tr in man["tiles"].values():
        for part in ("props_nodes", "signs_nodes"):
            for r in (tr.get(part) or {}).values():
                badm.update(r.get("checks") or {})
    checks.append({"id": "props_meshes", "ok": not badm,
                   "detail": "no bad triangles" if not badm else
                   ", ".join(f"{k} {v}" for k, v in sorted(badm.items()))})
    # budgets
    over = []
    unique = 0
    variant_tri = {}
    for key, f in man["families"].items():
        lim = BD.PLANT_TRIANGLES if key.startswith("plant.") else BD.VARIANT_TRIANGLES
        for node, r in f["meshes"].items():
            unique += r["triangles"]
            variant_tri[node] = r["triangles"]
            if r["triangles"] > lim:
                over.append(f"{node} {r['triangles']}")
    sign_tri = exact_tri = 0
    for tr in man["tiles"].values():
        for node, r in (tr.get("signs_nodes") or {}).items():
            sign_tri += r["triangles"]
            if r["triangles"] > BD.SIGN_TRIANGLES:
                over.append(f"{node} {r['triangles']}")
        for r in (tr.get("props_nodes") or {}).values():
            exact_tri += r["triangles"]
    unique += sign_tri + exact_tri
    per_tile = Counter()
    drawn = 0
    for gr in g.groups.values():
        for part, p in gr["parts"].items():
            per_tile[gr["tile"]] += len(p["xforms"])
            drawn += len(p["xforms"]) * variant_tri.get(part, 0)
    n_inst = sum(per_tile.values())
    worst = max(per_tile.items(), key=lambda kv: (kv[1], kv[0])) if per_tile else ("", 0)
    if worst[1] > BD.TILE_INSTANCES:
        over.append(f"{worst[0]}: {worst[1]} instances")
    if n_inst > BD.CITY_INSTANCES:
        over.append(f"{n_inst} instances")
    if drawn > BD.CITY_DRAWN_TRIANGLES:
        over.append(f"{drawn} drawn triangles")
    if unique > BD.CITY_UNIQUE_TRIANGLES:
        over.append(f"{unique} unique triangles")
    checks.append({"id": "props_budgets", "ok": not over,
                   "detail": f"{n_inst} instances (at most {worst[1]} in a tile, budgets "
                             f"{BD.TILE_INSTANCES} and {BD.CITY_INSTANCES}), {drawn} triangles "
                             f"drawn through them, {unique} unique triangles (budget "
                             f"{BD.CITY_UNIQUE_TRIANGLES})" +
                             (f"; over: {', '.join(over[:6])}" if over else "")})
    # stats
    by_kind = Counter()
    by_style = defaultdict(Counter)
    by_species = Counter()
    for gr in g.groups.values():
        for part, p in gr["parts"].items():
            bits = part.split(".")
            if bits[0] == "prop":
                by_kind[bits[1]] += len(p["xforms"])
                by_style[bits[2]][bits[1]] += len(p["xforms"])
            else:
                by_species[bits[1]] += len(p["xforms"])
    sign_kinds = Counter()
    looks = Counter()
    scripts = Counter()
    nodes = 0
    for t in g.signs.values():
        seen = set()
        for s in t:
            sign_kinds[s["kind"]] += 1
            looks[f"{s['kind']}.{s['inputs'].get('look', s['inputs']['mount'])}"] += 1
            scripts[s["inputs"].get("script", "latin")] += 1
            seen.add(s["node"])
        nodes += len(seen)
    disk = sum(f["bytes"] for f in man["families"].values()) + sum(
        tr.get("props", {}).get("bytes", 0) + tr.get("signs", {}).get("bytes", 0)
        for tr in man["tiles"].values())
    fam_tri = {k: sum(r["triangles"] for r in f["meshes"].values())
               for k, f in man["families"].items()}
    return {"city": model.name, "ok": all(c["ok"] for c in checks), "checks": checks,
            "stats": {"instances": n_inst, "instances_by_kind": dict(sorted(by_kind.items())),
                      "instances_by_style": {k: dict(sorted(v.items()))
                                             for k, v in sorted(by_style.items())},
                      "instances_by_species": dict(sorted(by_species.items())),
                      "variants": sum(len(f["meshes"]) for f in man["families"].values()),
                      "families": len(man["families"]),
                      "family_triangles": dict(sorted(fam_tri.items())),
                      "drawn_triangles": drawn, "unique_triangles": unique,
                      "sign_triangles": sign_tri, "exact_triangles": exact_tri,
                      "signs": dict(sorted(sign_kinds.items())), "sign_meshes": nodes,
                      "sign_looks": dict(sorted(looks.items())),
                      "sign_scripts": dict(sorted(scripts.items())),
                      "max_tile_instances": worst[1], "tiles": len(man["tiles"]),
                      "disk_bytes": disk, **g.stats}}


def report_text(rep: dict) -> str:
    st = rep["stats"]
    lines = [f"assetgen props: {rep['city']}: {'PASS' if rep['ok'] else 'FAIL'}", ""]
    for c in rep["checks"]:
        lines.append(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['id']}: {c['detail']}")
    lines += ["", f"variants {st['variants']} in {st['families']} families, instances "
                  f"{st['instances']} ({st['brackets']} brackets), exact props {st['exact']}, "
                  f"signs {st['signs']} ({st['sign_meshes']} meshes)",
              f"unique triangles {st['unique_triangles']} (signs {st['sign_triangles']}, "
              f"exact {st['exact_triangles']}), drawn through instances "
              f"{st['drawn_triangles']}, disk {st['disk_bytes'] / 1e6:.1f} MB", "",
              "instances by kind:"]
    for k, v in sorted(st["instances_by_kind"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {k}: {v}")
    lines.append("instances by species:")
    for k, v in sorted(st["instances_by_species"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {k}: {v}")
    lines.append("signs: " + ", ".join(f"{k} {v}" for k, v in st["sign_looks"].items()))
    lines.append("scripts: " + ", ".join(f"{k} {v}" for k, v in st["sign_scripts"].items()))
    f = rep.get("files")
    if f:
        lines.append(f"files: {f['families_made']} families made, {f['tiles_made']} tiles made, "
                     f"{f['tiles_kept']} kept, {len(f['written'])} written, "
                     f"{len(f['removed'])} removed")
    s = rep.get("seconds")
    if s:
        lines.append("seconds: " + ", ".join(f"{k} {v}" for k, v in s.items()
                                              if k != "slowest_tiles"))
    return "\n".join(lines) + "\n"
