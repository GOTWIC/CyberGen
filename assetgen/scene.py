"""AG16: the city's scene as the Unreal exporter makes it, counted per 256 m tile and for the
whole city, and held to the budgets AG16's benchmark showed fit (scope 14.17, `asset_budget`).

The counts are the exporter's own: `citygen.unreal.build_manifest` layers every stage 2
contribution over the blockout as an import would (meshes shared across tiles, an entry's
parts grouped into one actor), so they are what a level of this city holds:

- **actors**: every actor the import places (`citygen.unreal.actor_hashes`), by its tile;
- **components**: the actors' mesh and instanced components (an entry's parts one each);
- **meshes**: the distinct Nanite meshes the tile's actors and parts use (the city's: the
  distinct ones in all; `citygen.unreal.nanite_meshes`);
- **instances**: the instanced placements (parts, props, plants, grass);
- **root pages**: Nanite's root pages for the city's distinct meshes, at
  `ROOT_PAGES_PER_MESH` (measured on Delta: the root allocation over the meshes loaded),
  against what a streaming pool of the exporter's size leaves (`citygen.unreal`).

Run at the end of `assetgen build` (it needs the blockout's plan: a build without one gets
no scene section). Venv side only.
"""

from __future__ import annotations

import json
from pathlib import Path

# The budgets (AG16, Delta Megacity on the Windows PC, decision 13.4's target; see
# docs/assetgen_milestones.md, AG16): a city and a tile within these keep the benchmark's
# frame times. Set from what the benchmark showed fits.
CITY = {"actors": 60000, "components": 90000, "meshes": 52000, "instances": 3500000}
TILE = {"actors": 2000, "components": 3000, "meshes": 2500, "instances": 120000}
ROOT_PAGES_PER_MESH = 1.0
ROOT_PAGE_MB = 32768 / 1048576.0       # NANITE_ROOT_PAGE_GPU_SIZE, 32 KB


def _tile_of(man: dict) -> dict[str, str]:
    """Every actor key's tile (blockout objects, prototype instancers and swim boxes by
    theirs; stage 2's actors, groups and underwater volumes by theirs)."""
    out = {o["key"]: t["name"] for t in man["tiles"] for o in t["objects"]}
    out.update({i["key"]: i["tile"] for i in man["instances"]})
    out.update({s["key"]: s.get("tile", "") for s in man.get("swim", [])})
    s2 = man.get("stage2") or {}
    for a in s2.get("actors", []) + s2.get("groups", []) + s2.get("instances", []) + \
            s2.get("underwater", []):
        out[a["key"]] = a.get("tile", "")
    return out


def count(man: dict) -> dict:
    """The scene of an exporter manifest, per tile and in all."""
    from citygen import unreal as U
    hashes = U.actor_hashes(man)
    kinds = U.actor_kinds(man)
    tile_of = _tile_of(man)
    s2 = man.get("stage2") or {}
    grouped = "groups" in s2
    lod = {c["mesh"] for c in s2.get("lod_chains", [])}
    nanite = {f"{p['folder']}/{m['asset']}": bool(m["nanite"])
              for p in s2.get("packs", []) for m in p["meshes"]}
    replaced = set(s2.get("replaced", []))
    tiles: dict[str, dict] = {}

    def t(name):
        return tiles.setdefault(name or "-", {"actors": 0, "components": 0, "meshes": set(),
                                              "instances": 0})

    for k in hashes:
        t(tile_of.get(k, ""))["actors"] += 1
    for tl in man["tiles"]:
        for o in tl["objects"]:
            if o["key"] in hashes and kinds.get(o["key"]) == "mesh" and o["key"] not in \
                    replaced:
                e = t(tl["name"])
                e["components"] += 1
                e["meshes"].add(f"Meshes/{tl['name']}/{o['asset']}")
    for i in man["instances"]:
        if i["key"] in hashes and i["key"] not in replaced:
            e = t(i["tile"])
            e["components"] += 1
            e["instances"] += i["count"]
    for a in s2.get("actors", []):
        e = t(a["tile"])
        e["components"] += 1
        if a["mesh"] not in lod and nanite.get(a["mesh"], True):
            e["meshes"].add(a["mesh"])
    for r in s2.get("instances", []):
        e = t(r["tile"])
        e["components"] += 1
        e["instances"] += r["count"] if "count" in r else len(r["xforms"])
        if nanite.get(r["mesh"], True) and r["mesh"] not in lod:
            e["meshes"].add(r["mesh"])
    city_meshes = set()
    for e in tiles.values():
        city_meshes |= e["meshes"]
    out_tiles = {k: {**v, "meshes": len(v["meshes"])} for k, v in sorted(tiles.items())}
    city = {"actors": len(hashes), "components": sum(v["components"] for v in tiles.values()),
            "meshes": len(city_meshes),
            "instances": sum(v["instances"] for v in tiles.values()),
            "grouped": grouped}
    city["root_pages"] = int(round(city["meshes"] * ROOT_PAGES_PER_MESH))
    pool = U.nanite_pool_mb(man)
    city["root_pages_max"] = int((U.NANITE_BUFFER_MB - pool) / ROOT_PAGE_MB)
    city["nanite_pool_mb"] = pool
    return {"city": city, "tiles": out_tiles}


def check(build_dir: str | Path) -> dict | None:
    """The scene section of `asset_budget` for the build: the counts against `CITY` and
    `TILE`, the tiles over budget, and whether the root pages fit; None without the
    blockout's plan."""
    build = Path(build_dir)
    if not (build / "blockout_plan.json").is_file():
        return None
    from citygen import unreal as U
    man, _, _ = U.build_manifest(build, assets=True, play=False)
    c = count(man)
    city = c["city"]
    over_city = sorted(k for k, v in CITY.items() if city[k] > v)
    over = {}
    for name, v in c["tiles"].items():
        bad = sorted(k for k, lim in TILE.items() if v[k] > lim)
        if bad:
            over[name] = bad
    worst = {k: max(((v[k], n) for n, v in c["tiles"].items()), default=(0, ""))
             for k in TILE}
    ok = not over_city and not over and city["root_pages"] <= city["root_pages_max"]
    return {"ok": ok, "city": city, "budget_city": CITY, "budget_tile": TILE,
            "over_city": over_city, "tiles_over": len(over),
            "first_over": dict(list(sorted(over.items()))[:5]),
            "max_tile": {k: {"tile": n, "count": v} for k, (v, n) in worst.items()},
            "tiles": len(c["tiles"])}


def write(build_dir: str | Path, res: dict) -> int:
    """`assets/scene_budget.json`, written only when its bytes change; 1 when written."""
    p = Path(build_dir) / "assets" / "scene_budget.json"
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    if p.is_file() and p.read_text(encoding="utf-8") == text:
        return 0
    p.write_text(text, encoding="utf-8", newline="\n")
    return 1
