"""`assetgen preview BUILD [--blockout DIR] [--views ...] [--only NAME ...] [--width W]
[--out DIR]`: Blender
previews of a build's assets (scope 14.2), written to `BUILD/assets/previews/`:

- `city.jpg`: the whole city from its far proxies, isometric (the blockout's iso_city
  camera); `city_full.jpg` (only when asked for, `--views city_full`): every shell at once;
- `iso_<district>.jpg`: every district at full detail (its neighbors from proxies);
- `street_<n>.jpg`: the blockout's street cameras with the shells around them;
- `contact_<type>.jpg`: a contact sheet per building type (up to 12 buildings drawn by id
  hash, each framed alone), and `contact_sheet.jpg`, 64 buildings drawn across the city;
- `tower_<era>.jpg` (AG2, `--views towers`): the tallest building of every era up close,
  its neighbors at full detail.

AG2's instanced parts are drawn as Blender instances (geometry nodes on a point cloud per
part mesh and tile, the building's tints as instance attributes), the merged ones are in
the shells.

The cameras are the blockout's (`blockout_plan.json` when `--blockout` names a blockout
directory, else planned here from the model); with a blockout the scene is its city.blend
without the building boxes, so the shells stand on its ground, streets and props.
Blender only draws: everything it renders is the build's glTF.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from . import build as BD
from . import gltf as G
from .buildings import genome as GN
from .buildings import systems as SY

ISO_DIR = (0.280167, 0.769751, -0.573576)     # the blockout's isometric direction
STREET_R = 700.0
SHEET_N = 12
RANDOM_N = 64
CELL = 480


def _norm(v):
    L = math.sqrt(sum(c * c for c in v))
    return tuple(c / L for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def iso_frame(box, d, aspect):
    """Center and ortho width framing a box (x0, y0, z0, x1, y1, z1) seen along d (the
    blockout's `iso_frame`)."""
    x0, y0, z0, x1, y1, z1 = box
    side = _norm(_cross(d, (0.0, 0.0, 1.0)))
    up = _norm(_cross(side, d))
    corners = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 4)
    us = [_dot([p[k] - c[k] for k in range(3)], side) for p in corners]
    vs = [_dot([p[k] - c[k] for k in range(3)], up) for p in corners]
    du, dv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    c = tuple(c[k] + side[k] * du + up[k] * dv for k in range(3))
    return c, max(max(us) - min(us), (max(vs) - min(vs)) * aspect) * 1.06


def front_dir(brief: dict) -> tuple[float, float, float]:
    """The contact sheet's view onto a building's main front (`buildings.thumb.front_dir`)."""
    from .buildings import thumb as TH
    return TH.front_dir(brief)


def _ortho(box, w, aspect, back, d=ISO_DIR):
    d = _norm(d)
    c, scale = iso_frame(box, d, aspect)
    return {"ortho": True, "scale": scale, "eye": [c[k] - d[k] * back for k in range(3)],
            "target": list(c), "w": w, "h": int(w / aspect)}


def cameras(bdir: Path, blockout: Path | None) -> dict:
    if blockout is not None and (blockout / "blockout_plan.json").is_file():
        return json.loads((blockout / "blockout_plan.json").read_text())["cameras"]
    from citygen.blockout import make_plan
    from citygen.model import CityModel
    m = CityModel.model_validate_json((bdir / "city_model.json").read_bytes())
    return make_plan(m)["cameras"]


def _tile_box(name: str) -> tuple[float, float, float, float]:
    ix, iy = int(name[1:4]), int(name[4:7])
    return ix * BD.TILE_M, iy * BD.TILE_M, (ix + 1) * BD.TILE_M, (iy + 1) * BD.TILE_M


def tower_views(man: dict, briefs: dict, width: int) -> list[dict]:
    """The tallest building of every era (landmarks aside: theirs are AG5's), framed with
    room round it, from its front; its own and its neighbors' tiles at full detail."""
    best: dict[str, tuple] = {}
    for bid, r in man["buildings"].items():
        era = (briefs.get(bid) or {}).get("spec", {}).get("era")
        if not era or r["type"].startswith("building.landmark") or \
                not (r.get("genes") or {}).get("body.system"):
            continue                # landmarks, and megasite structures without a facade
        h = r["bounds"][1][2]
        if era not in best or (h, bid) > best[era][:2]:
            best[era] = (h, bid)
    views = []
    for era in sorted(best):
        h, bid = best[era]
        r = man["buildings"][bid]
        px, py = r["pivot"][0], r["pivot"][1]
        (x0, y0, _), (x1, y1, z1) = r["bounds"]
        pad = max(8.0, 0.25 * max(x1 - x0, y1 - y0))
        box = [px + x0 - pad, py + y0 - pad, 0.0, px + x1 + pad, py + y1 + pad, z1 * 1.04 + 4]
        v = _ortho(box, width, 0.8 if z1 > 1.2 * max(x1 - x0, y1 - y0) else 1.4, 3000.0,
                   front_dir(briefs[bid]))
        near = []
        for t in man["tiles"]:
            tx0, ty0, tx1, ty1 = _tile_box(t)
            dx = max(tx0 - px, 0.0, px - tx1)
            dy = max(ty0 - py, 0.0, py - ty1)
            if dx * dx + dy * dy <= 300.0 ** 2:
                near.append(t)
        views.append({"name": f"tower_{era}", **v, "shell_tiles": sorted(near),
                      "key": bid, "height": round(z1, 1)})
    return views


def instances(man: dict, tiles: list[str], local: dict | None = None) -> dict:
    """Per tile, its buildings' tints and every instanced part's placements in the world
    (x, y, z, yaw in radians, the building's index in the tints); with `local` ({key:
    index}), those buildings at their own origin instead (contact sheets)."""
    out = {}
    want = set(tiles)
    chans = ("wall", "trim", "glass", "roof", "spandrel", "patch")
    if local is not None:
        order = sorted(local, key=lambda k: local[k])
        out["sheet"] = {"tints": [[man["buildings"][k]["tints"][c] for c in chans]
                                  for k in order], "parts": {}}
    for bid in sorted(man["buildings"]):
        r = man["buildings"][bid]
        if local is None and r["tile"] not in want or local is not None and bid not in local:
            continue
        if not r.get("parts"):
            continue
        if local is None:
            t = out.setdefault(r["tile"], {"tints": [], "parts": {}})
            bi = len(t["tints"])
            t["tints"].append([r["tints"][c] for c in chans])
        else:
            t = out["sheet"]
            bi = local[bid]
        px, py, pz = (0.0, 0.0, 0.0) if local is not None else r["pivot"]
        for x in r["parts"]:
            pl = t["parts"].setdefault(x["node"], [])
            for a in x["xforms"]:
                pl.append([round(px + a[0], 3), round(py + a[1], 3), round(pz + a[2], 3),
                           round(math.radians(a[3]), 6), bi])
    return out


def plan_views(man: dict, cams: dict, width: int, which: set[str]) -> list[dict]:
    views = []
    boxes = [d["box"] for d in cams["districts"]]
    tall = max((r["bounds"][1][2] for r in man["buildings"].values()), default=30.0)
    if boxes:
        box = [min(b[i] for b in boxes) for i in range(3)] + \
            [max(b[i] for b in boxes) for i in range(3, 5)] + [tall]
        if "city" in which:
            views.append({"name": "city", **_ortho(box, width, 1.6, 8000.0),
                          "shell_tiles": []})
        if "city_full" in which:
            # every shell and part at once (AG2: 26 to 28 M unique triangles, about a
            # million part instances); 16 samples, since EEVEE redraws the whole city each
            # sample and the view is meant to be seen scaled down
            views.append({"name": "city_full", **_ortho(box, width, 1.6, 8000.0),
                          "shell_tiles": sorted(man["tiles"]), "samples": 16})
    by_d: dict[str, set] = {}
    for r in man["buildings"].values():
        if r["district"]:
            by_d.setdefault(r["district"], set()).add(r["tile"])
    if "districts" in which:
        for d in cams["districts"]:
            if d["id"] not in by_d:
                continue
            views.append({"name": f"iso_{d['id']}", **_ortho(d["box"], width, 1.6, 4000.0),
                          "shell_tiles": sorted(by_d[d["id"]])})
    if "street" in which:
        for k, v in enumerate(cams["street"], 1):
            ex, ey = v["eye"][0], v["eye"][1]
            near = []
            for t in man["tiles"]:
                x0, y0, x1, y1 = _tile_box(t)
                dx = max(x0 - ex, 0.0, ex - x1)
                dy = max(y0 - ey, 0.0, ey - y1)
                if dx * dx + dy * dy <= STREET_R * STREET_R:
                    near.append(t)
            views.append({"name": f"street_{k}", "ortho": False, "lens": v["lens_mm"],
                          "eye": v["eye"], "target": v["target"], "w": width,
                          "h": int(width * 9 / 16), "shell_tiles": sorted(near)})
    return views


def _pick(ids: list[str], n: int, purpose: str) -> list[str]:
    return sorted(ids, key=lambda i: (GN.u(i, purpose, "ag1.preview"), i))[:n]


def sheet_jobs(bdir: Path, man: dict, out: Path, cell: int = CELL,
               only: list[str] | None = None) -> list[dict]:
    """A glTF per sheet with its buildings each at the origin, and a framed view per cell
    (`only`: just the sheets of these names, `random` or a type without `building.`)."""
    briefs = json.loads((bdir / "assets" / "briefs.json").read_text())["briefs"]
    by_type: dict[str, list[str]] = {}
    for bid, r in sorted(man["buildings"].items()):
        by_type.setdefault(r["type"], []).append(bid)
    sheets = [(t.split(".", 1)[1], _pick(ids, SHEET_N, t)) for t, ids in sorted(by_type.items())]
    sheets.append(("random", _pick(sorted(man["buildings"]), RANDOM_N, "random")))
    if only:
        sheets = [sh for sh in sheets if sh[0] in only]
    jobs = []
    sd = out / "sheets"
    sd.mkdir(parents=True, exist_ok=True)
    for name, ids in sheets:
        g = G.Gltf(generator="assetgen preview")
        made = []
        for bid in ids:
            br = briefs[bid]
            sh, _, rec = BD.building_asset(br, GN.make(br))
            made.append((bid, sh, rec))
        mats = BD._materials(g, sorted({s for _, sh, _ in made for s in sh["arrays"]}))
        # the sheet's instanced parts: one mesh each in a pack of their own
        pdefs = {}
        for _, sh, _ in made:
            for x in sh["parts"]:
                pdefs.setdefault(x["node"], (x["family"], x["params"]))
        pglb = None
        if pdefs:
            from .buildings import parts as PT
            gq = G.Gltf(generator="assetgen preview")
            pm = {nd: PT.mesh(*pdefs[nd]) for nd in sorted(pdefs)}
            qm = BD._materials(gq, sorted({s for _, a in pm.values() for s in a}))
            for nd in sorted(pm):
                gq.node(nd, mesh=gq.mesh(nd, pm[nd][0].primitives(pm[nd][1], qm)), root=True)
            pglb = sd / f"{name}_parts.glb"
            pglb.write_bytes(gq.to_glb())
        sheet_man = {"buildings": {bid: rec for bid, sh, rec in made}}
        sheet_inst = instances(sheet_man, [], {bid: k for k, (bid, _, _) in enumerate(made)})
        cells = []
        for k, (bid, sh, rec) in enumerate(made):
            mesh = g.mesh(f"{bid}.shell", sh["buf"].primitives(sh["arrays"], mats))
            child = g.node(f"{bid}.shell", mesh=mesh, extras=BD._node_extras(bid, rec))
            g.node(bid, children=[child], root=True)
            (x0, y0, z0), (x1, y1, z1) = rec["bounds"]
            v = _ortho([x0, y0, 0.0, x1, y1, z1], cell, 1.0, 2000.0, front_dir(briefs[bid]))
            v["scale"] *= 1.04
            cells.append({"key": bid, "file": f"sheets/{name}_{k:02d}.jpg", "view": v,
                          "type": rec["type"], "height": round(z1, 1),
                          "district": rec["district"]})
        path = sd / f"{name}.glb"
        path.write_bytes(g.to_glb())
        jobs.append({"name": name, "glb": str(path), "cells": cells,
                     "parts_glb": str(pglb) if pglb else None,
                     "instances": sheet_inst.get("sheet")})
    return jobs


def compose(out: Path, sheets: list[dict], man: dict, cell: int = CELL) -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=max(12, cell // 30))
    made = []
    for sh in sheets:
        n = len(sh["cells"])
        if not n:
            continue
        cols = 8 if n > 16 else 4
        rows = (n + cols - 1) // cols
        pad = max(26, cell // 18)
        im = Image.new("RGB", (cols * cell, rows * (cell + pad) + 2 * pad), (24, 25, 28))
        dr = ImageDraw.Draw(im)
        total = sum(1 for r in man["buildings"].values()
                    if r["type"] == "building." + sh["name"])
        title = "64 buildings drawn across the city" if sh["name"] == "random" else \
            f"{sh['name']}: {n} of {total}"
        dr.text((10, 12), f"{man['city']}, {title}", fill=(230, 230, 230), font=font)
        for k, c in enumerate(sh["cells"]):
            p = out / c["file"]
            if not p.is_file():
                continue
            x, y = (k % cols) * cell, 2 * pad + (k // cols) * (cell + pad)
            im.paste(Image.open(p).convert("RGB").resize((cell, cell)), (x, y))
            label = c["key"] if sh["name"] != "random" else \
                f"{c['type'].split('.', 1)[1]}, {c['height']} m"
            dr.text((x + 6, y + cell + 6), label, fill=(200, 200, 200), font=font)
        f = out / ("contact_sheet.jpg" if sh["name"] == "random" else
                   f"contact_{sh['name']}.jpg")
        im.save(f, quality=90)
        made.append(f)
    return made


def run(build_dir: str | Path, blockout: str | None = None, out: str | None = None,
        which: list[str] | None = None, width: int = 2400, blender: str | None = None,
        only: list[str] | None = None, cell: int = CELL, log=print,
        parts: bool = True) -> dict:
    bdir = Path(build_dir)
    adir = bdir / "assets"
    man = json.loads((adir / "manifest.json").read_text())
    od = Path(out) if out else adir / "previews"
    od.mkdir(parents=True, exist_ok=True)
    bo = Path(blockout) if blockout else (bdir / "blockout" if (bdir / "blockout").is_dir()
                                          else None)
    which = set(which or ("city", "districts", "street", "sheets", "towers"))
    cams = cameras(bdir, bo)
    views = plan_views(man, cams, width, which)
    if "towers" in which:
        briefs = json.loads((adir / "briefs.json").read_text())["briefs"]
        views += tower_views(man, briefs, width)
    if only:
        views = [v for v in views if v["name"] in only]
    sheets = sheet_jobs(bdir, man, od, cell, only) if "sheets" in which else []
    need = sorted({t for v in views for t in v.get("shell_tiles", [])})
    inst_path = od / "instances.json"
    inst_path.write_text(json.dumps(instances(man, need)))
    lit = 0.03
    # AG4: the skybridges of the tiles each view draws in full, in place of the blockout's
    conn = set(man.get("connections") or {})
    for v in views:
        v["connection_tiles"] = sorted(set(v.get("shell_tiles", [])) & conn)
    removed = sorted(set(man.get("skybridges") or {}) |
                     {g for x in (man.get("green_replaces") or {}).values() for g in x})
    job = {"assets": str(adir), "out": str(od), "views": views, "sheets": sheets,
           "instances": str(inst_path), "parts_on": parts, "removed": removed,
           # proxies only where some view does not draw the tile at full detail
           "proxy_tiles": sorted(set(man["tiles"]) - set.intersection(
               *(set(v.get("shell_tiles", [])) for v in views))) if views else [],
           "blend": str(bo / "city.blend") if bo and (bo / "city.blend").is_file() else None,
           "slots": {k: [v[0], SY.srgb_linear(v[1]), v[2], v[3], v[4]]
                     for k, v in SY.SLOTS.items()}, "lit": lit, "samples": 32}
    from citygen.blockout import find_blender
    exe = find_blender(blender)
    if exe is None:
        raise RuntimeError("no Blender (set BLENDER or --blender)")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(job, f)
        jp = f.name
    script = Path(__file__).resolve().parent / "blender" / "preview_assets.py"
    log(f"blender: {len(views)} views, {sum(len(s['cells']) for s in sheets)} sheet cells")
    proc = subprocess.run([exe, "-b", "--factory-startup", "-P", str(script), "--", jp],
                          capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if line.startswith("[ag preview"):
            log(line)
    if proc.returncode != 0 or not (od / "preview_report.json").is_file():
        sys.stderr.write(proc.stdout[-4000:] + proc.stderr[-4000:])
        raise RuntimeError(f"Blender failed ({proc.returncode})")
    made = compose(od, sheets, man, cell) if sheets else []
    if inst_path.is_file():
        inst_path.unlink()
    rep = json.loads((od / "preview_report.json").read_text())
    rep["contact_sheets"] = [p.name for p in made]
    (od / "preview_report.json").write_text(json.dumps(rep, indent=1) + "\n")
    return rep


def main(args) -> int:
    try:
        rep = run(args.build, args.blockout, args.out, args.views, args.width, args.blender,
                  args.only, args.cell, parts=not getattr(args, "no_parts", False))
    except (OSError, RuntimeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"previews: {len(rep['views'])} views, {len(rep['contact_sheets'])} contact sheets")
    return 0


