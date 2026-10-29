"""`assetgen materials preview BUILD` and `assetgen materials board OUT` (AG6's shows):
textured Blender renders.

- **preview**: the blockout's `city.blend` with its building boxes and the street objects
  AG7 replaces taken out; per view the shells of its tiles and the street pieces near it
  with AG6's materials (`assetgen/blender/ag6_materials.py`), the rest of the city from the
  far proxies; the sign slots near a street view as quads showing their atlas cells; by
  night (`--night`) the windows lit by each building's lit ratio, the signs and neon, a
  point light at every street light near the camera. Views: the districts (`iso_<id>`), the
  street cameras (`street_<n>`), the city, or cameras of one's own (`--eye`, `--target`).
- **board**: a material board per era (its wall sets, roof, trims, metals, a window with
  its rooms) and one of the street sets, each a slab of the material under a low sun.

Blender only draws: the job holds every path, parameter and transform.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from .. import previews as PV
from . import catalog as CT
from . import library as LB

STREET_R = 600.0
SIGN_R = 260.0
LIGHT_R = 220.0
MAX_LIGHTS = 160


def _files(assets: Path, textures: dict) -> dict[str, str]:
    return {k: str((assets / v["file"]).resolve()) for k, v in textures.items()}


def _props(man: dict) -> dict[str, dict]:
    out = {}
    for bid, r in man["buildings"].items():
        mat = r.get("material")
        if mat is None:
            continue
        c = r["cpd"]
        e = mat["cpd"]
        out[bid] = {"era": mat["era"], "cg_wear": c[3], "cg_dirt": c[4], "cg_neon": c[5],
                    "cg_lit": c[6], "cg_seed": c[7], "cg_room": e[0], "cg_floorh": e[1],
                    "cg_row": e[2], "cg_streaks": e[3], "cg_top": e[4], "cg_blinds": e[5]}
    return out


def _near(p, c, r):
    return (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 <= r * r


def _signs(model, signs: dict, assets: Path, center, r) -> list[dict]:
    out = []
    for s in model.sign_slots:
        if not _near(s.position, center, r):
            continue
        key = signs["slots"].get(s.id)
        cell = signs["cells"].get(key or "")
        if cell is None:
            continue
        f = signs["files"][cell["page"]]["file"]
        out.append({"id": s.id, "pos": list(s.position), "yaw": s.yaw_deg, "w": s.width_m,
                    "h": s.height_m, "two": bool(s.two_sided), "mount": s.mount,
                    "kind": s.kind, "file": str((assets / f).resolve()), "uv": cell["uv"]})
    return out


def _lights(model, center, r) -> list[list[float]]:
    """Street lights near a view: the lamp (8 m high, M6's prototype) over each pole."""
    out = []
    for p in model.props:
        if p.type != "prop.street_light" or not _near(p.position, center, r):
            continue
        out.append([p.position[0], p.position[1], p.position[2] + 7.6 * p.scale[2]])
    out.sort(key=lambda q: ((q[0] - center[0]) ** 2 + (q[1] - center[1]) ** 2, q[0], q[1]))
    return out[:MAX_LIGHTS]


def run(args) -> dict:
    from ..brief import load_model
    bdir = Path(args.build)
    adir = bdir / "assets"
    man = json.loads((adir / "manifest.json").read_text())
    mats = json.loads((adir / "materials.json").read_text())
    signs = json.loads((adir / "signs.json").read_text())
    con = json.loads((adir / "unreal_contribution.streets.json").read_text())
    model, _, _ = load_model(bdir)
    od = Path(args.out) if args.out else adir / "previews_ag6"
    od.mkdir(parents=True, exist_ok=True)
    bo = Path(args.blockout) if args.blockout else bdir
    cams = PV.cameras(bdir, bo)
    which = set(args.views or ["districts", "street"])
    views = PV.plan_views(man, cams, args.width, which & {"city", "districts", "street"})
    named = [v for v in (args.views or []) if v not in ("city", "districts", "street")]
    if named:
        allv = PV.plan_views(man, cams, args.width, {"districts", "street"})
        views = [v for v in allv if v["name"] in named]
    for k, (eye, tgt) in enumerate(zip(args.eye, args.target), 1):
        near = [t for t in man["tiles"] if _tile_near(t, tgt, PV.STREET_R)]
        views.append({"name": f"custom_{k}", "ortho": False, "lens": args.lens,
                      "eye": list(eye), "target": list(tgt), "w": args.width,
                      "h": int(args.width * 9 / 16), "shell_tiles": sorted(near)})
    stiles = sorted({e["tile"] for e in con["entries"]})
    for v in views:
        tgt = v["target"]
        if v["ortho"]:
            v["street_tiles"] = sorted(set(v["shell_tiles"]) & set(stiles))
            v["signs"], v["lights"] = [], []
        else:
            v["street_tiles"] = [t for t in stiles if _tile_near(t, v["eye"], STREET_R)]
            v["signs"] = _signs(model, signs, adir, v["eye"], SIGN_R)
            v["lights"] = _lights(model, v["eye"], LIGHT_R)
    modes = ["night"] if args.only_night else (["day", "night"] if args.night else ["day"])
    job = {"assets": str(adir), "out": str(od), "views": views, "modes": modes,
           "blend": str(bo / "city.blend"), "materials": mats["parts"],
           "files": _files(adir, mats["textures"]), "props": _props(man),
           "removed": sorted({e["key"] for e in con["entries"]} |
                             {r for e in con["entries"] for r in e.get("replaces", [])}),
           "proxy_tiles": sorted(man["tiles"]), "samples": args.samples,
           "era_slots": sorted(CT.ERA_SLOTS)}
    return _blender(job, "ag6_preview.py", args.blender, od)


def _tile_near(name: str, p, r) -> bool:
    x0, y0, x1, y1 = PV._tile_box(name)
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return dx * dx + dy * dy <= r * r


def _blender(job: dict, script: str, blender: str | None, od: Path) -> dict:
    from citygen.blockout import find_blender
    exe = find_blender(blender)
    if exe is None:
        raise RuntimeError("no Blender (set BLENDER or --blender)")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(job, f)
        jp = f.name
    sp = Path(__file__).resolve().parent.parent / "blender" / script
    proc = subprocess.run([exe, "-b", "--factory-startup", "-P", str(sp), "--", jp],
                          capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if line.startswith("[ag6"):
            print(line, flush=True)
    rep_p = od / "ag6_report.json"
    if proc.returncode != 0 or not rep_p.is_file():
        sys.stderr.write(proc.stdout[-4000:] + proc.stderr[-4000:])
        raise RuntimeError(f"Blender failed ({proc.returncode})")
    return json.loads(rep_p.read_text())


def board_job(args) -> dict:
    lib = LB.load(None, args.density) or LB.generate(None, args.density)
    od = Path(args.out)
    od.mkdir(parents=True, exist_ok=True)
    boards = []
    for era in LB.ERAS:
        mats = []
        for slot in ("concrete", "plaster", "brick", "panel", "cladding", "roof"):
            mats.append((slot, CT.material(slot, era, lib), slot))
        for slot in ("spandrel", "trim", "structure", "equipment", "louver", "glass"):
            mats.append((slot, CT.material(slot, era, lib), slot))
        boards.append({"name": era, "title": f"{era.replace('_', ' ')} era: its walls and "
                       "roof (top), shared surfaces (bottom)", "materials": mats})
    shared = [(s, CT.material(s, None, lib), s) for s in
              ("patch_sheet", "patch_rust", "patch_tarp", "patch_panel", "patch_ply",
               "board_concrete", "stucco", "timber", "shutter", "perforated", "seam",
               "hangar", "tile", "mullion",
               "pod", "sill")]
    boards.append({"name": "building_parts", "title": "building parts and patches",
                   "materials": shared})
    street = [(s, CT.material(s, None, lib, "streets"), s) for s in
              ("asphalt.highway", "asphalt.avenue", "asphalt.street", "asphalt.alley",
               "marking.white", "marking.yellow", "paving.cobble", "paving.tile",
               "paving.granite", "paving.concrete_slab", "paving.concrete_cast",
               "paving.concrete_tile", "paving.resin", "paving.brick", "paving.timber",
               "curb.granite", "concrete.deck", "stone.quay", "tile.tunnel", "steel.painted",
               "ballast", "container.c1", "manhole", "lawn")]
    boards.append({"name": "streets", "title": "street surfaces", "materials": street})
    if args.only:
        boards = [b for b in boards if b["name"] in args.only]
    names = set()
    for b in boards:
        for _, m, _ in b["materials"]:
            names.update(m["textures"].values())
    tex = CT.texture_table(names, lib)
    files = {k: str((Path(lib["dir"]) / v["file"].split("/", 1)[1]).resolve())
             for k, v in tex.items()}
    from ..streets import materials as SM
    for b in boards:
        out = []
        for label, m, slot in b["materials"]:
            if b["name"] == "streets":
                c = SM.SLOTS[slot][1]
                m["color"] = [int(c[1 + 2 * k:3 + 2 * k], 16) / 255.0 for k in range(3)]
                m["part"] = "streets"
            else:
                from ..buildings import systems as SY
                spec = SY.SLOTS.get(slot, ("facade", "#8c8a86", 0.8, 0.0, None))
                pal = LB.ERA_LOOK.get(b["name"], {}).get(slot, {}).get("color") or spec[1]
                m["color"] = SY.srgb_linear(pal)
                m["part"] = "board"
            out.append({"label": label, "rec": m})
        b["materials"] = out
    return {"out": str(od), "boards": boards, "files": files, "width": args.width}


def main(args) -> int:
    try:
        if args.command == "board":
            job = board_job(args)
            rep = _blender(job, "ag6_board.py", args.blender, Path(args.out))
        else:
            rep = run(args)
    except (OSError, RuntimeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"rendered {len(rep.get('files', []))} images")
    return 0
