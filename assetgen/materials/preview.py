"""`assetgen materials preview BUILD` and `assetgen materials board OUT` (AG6's shows):
textured Blender renders.

- **preview**: the blockout's `city.blend` with its building boxes, its skybridges, the
  green roofs AG4 builds and the street objects AG7 replaces taken out; per view the shells
  of its tiles with AG4's skybridges and their roof equipment, and the street pieces near it
  with AG6's materials (`assetgen/blender/ag6_materials.py`), the rest of the city from the
  far proxies; AG3's street fronts and decals with the shells, AG2's instanced parts on
  them; AG8's props and plants near a street view as instances of their variant
  families and its signs (their faces showing the sign pages), with AG6's materials (where
  AG8 has not run, the sign slots as quads showing their atlas cells); by night
  (`--night`) the windows lit by each building's lit ratio, the signs and neon, a point
  light at every street light near the camera. Views: the districts (`iso_<id>`), the
  street cameras (`street_<n>`), the city (from the proxies; `city_full`, AG4: every shell,
  part, skybridge and street piece at once; both with every water and ground tile, open sea
  and parks too), the section across the biggest M14 deck
  (`deck`, AG10: the blockout's deck camera, its near clip on the cut), AG12's water shows
  (`water`: a canal and a river bank up close, the harbor from above), or cameras of one's
  own (`--eye`, `--target`). AG12's water (surfaces, beds, banks, riprap stones) comes into
  every view near it, in place of the blockout's water.
- **board**: a material board per era (its wall sets, roof, trims, metals, a window with
  its rooms) and one of the street sets, each a slab of the material under a low sun.

Blender only draws: the job holds every path, parameter and transform.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

from .. import previews as PV
from . import catalog as CT
from . import library as LB

STREET_R = 600.0
SIGN_R = 260.0
PROPS_R = 320.0
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
        if len(e) >= 13:
            # AG15: the night (Custom Primitive Data 30 to 35)
            out[bid].update({"cg_ncol": list(e[7:10]), "cg_sched": e[10],
                             "cg_spread": e[11], "cg_band": e[12]})
    return out


def _near(p, c, r):
    return (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 <= r * r


class _Lift:
    """#90: what a model height is over on M13's terrain (nothing on a flat city): a sign
    slot's over its building's base, a street light's over the ground at its foot (as the
    blockout and AG8 lift them)."""

    def __init__(self, model):
        from ..streets.ctx import Ground
        self.gd = Ground(model)
        self.base = {} if self.gd.flat else {
            b.id: float(b.base_m) for b in model.buildings
            if getattr(b, "base_m", None) is not None}

    def slot(self, s) -> float:
        if self.gd.flat:
            return 0.0
        if s.building_id in self.base:
            return self.base[s.building_id]
        return self.gd.at(s.position[0], s.position[1])

    def ground(self, x, y) -> float:
        return 0.0 if self.gd.flat else self.gd.at(x, y)


def _signs(model, signs: dict, assets: Path, center, r, lift=None) -> list[dict]:
    out = []
    for s in model.sign_slots:
        if not _near(s.position, center, r):
            continue
        key = signs["slots"].get(s.id)
        cell = signs["cells"].get(key or "")
        if cell is None:
            continue
        f = signs["files"][cell["page"]]["file"]
        z = s.position[2] + (lift.slot(s) if lift is not None else 0.0)
        out.append({"id": s.id, "pos": [s.position[0], s.position[1], z], "yaw": s.yaw_deg,
                    "w": s.width_m,
                    "h": s.height_m, "two": bool(s.two_sided), "mount": s.mount,
                    "kind": s.kind, "file": str((assets / f).resolve()), "uv": cell["uv"]})
    return out


def _ag8(adir: Path, views: list) -> dict | None:
    """AG8's props, plants and signs for the views (its contributions): the family packs,
    the blockout keys they replace, and per perspective view the instances near its eye
    (by variant node, world transforms), the exact prop tiles and the signs."""
    pp, sp = adir / "unreal_contribution.props.json", adir / "unreal_contribution.signs.json"
    if not (pp.is_file() and sp.is_file()):
        return None
    cp = json.loads(pp.read_text(encoding="utf-8"))
    cs = json.loads(sp.read_text(encoding="utf-8"))
    fams = sorted({str((adir / q["glb"]).resolve()) for e in cp["entries"]
                   for q in e.get("parts", [])})
    removed = sorted({k for c in (cp, cs) for e in c["entries"]
                      for k in [e["key"]] + list(e.get("replaces", []))})
    for v in views:
        v["ag8"] = {"points": {}, "exact": [], "signs": []}
        if v["ortho"]:
            continue
        eye = v["eye"]
        pts: dict[str, list] = {}
        exact = set()
        for e in cp["entries"]:
            px, py, pz = e["pivot"]
            if e.get("glb") and _near(e["pivot"], eye, PROPS_R):
                exact.add(str((adir / e["glb"]).resolve()))
            for q in e.get("parts", []):
                for xf in q["xforms"]:
                    x, y = xf[0] + px, xf[1] + py
                    if _near((x, y), eye, PROPS_R):
                        pts.setdefault(q["node"], []).append(
                            [x, y, xf[2] + pz, xf[3]] + (list(xf[4:7]) if len(xf) > 4
                                                         else [1.0, 1.0, 1.0]))
        v["ag8"]["points"] = dict(sorted(pts.items()))
        v["ag8"]["exact"] = sorted(exact)
        v["ag8"]["signs"] = [{"key": e["key"], "node": e["node"],
                              "glb": str((adir / e["glb"]).resolve()), "pivot": e["pivot"],
                              "yaw": e["yaw_deg"], "slots": e.get("slots", [])}
                             for e in cs["entries"] if _near(e["pivot"], eye, SIGN_R)]
        v["signs"] = []                    # (AG8's signs show the cells: no quads)
    return {"families": fams, "removed": removed}


GRASS_R = 140.0         # AG13: clumps this near the eye (Unreal fades them out at 60 to 100 m)


def _ground(adir: Path, views: list) -> dict | None:
    """AG13's ground for the views (its contribution): per view the ground tiles (a street
    view's within STREET_R of its eye, else its shell tiles) and the clumps within GRASS_R of
    a perspective view's eye, by variant node (AG8's points, so the same instancer draws
    them); the clump pack, the blockout keys it replaces, its materials and textures."""
    cp = adir / "unreal_contribution.ground.json"
    if not cp.is_file():
        return None
    con = json.loads(cp.read_text(encoding="utf-8"))
    gtiles = sorted({e["tile"] for e in con["entries"] if e.get("glb")})
    grass = {e["tile"]: e for e in con["entries"] if e.get("parts")}
    for v in views:
        if v["ortho"] or v.get("section"):
            v["ground_tiles"] = (list(gtiles) if v.get("whole") else
                                 sorted(set(v["shell_tiles"]) & set(gtiles)))
            continue
        v["ground_tiles"] = [t for t in gtiles if _tile_near(t, v["eye"], STREET_R)]
        pts = v.setdefault("ag8", {}).setdefault("points", {})
        for t, e in sorted(grass.items()):
            if not _tile_near(t, v["eye"], GRASS_R):
                continue
            doc = json.loads((adir / e["parts"][0]["xforms_file"]).read_text(encoding="utf-8"))
            px, py, pz = doc["pivot"]
            for node, xf in doc["nodes"].items():
                for q in xf:
                    x, y = q[0] + px, q[1] + py
                    if _near((x, y), v["eye"], GRASS_R):
                        pts.setdefault(node, []).append([x, y, q[2] + pz, q[3]] + list(q[4:7]))
        v["ag8"]["points"] = dict(sorted(pts.items()))
    removed = sorted({k for e in con["entries"] for k in [e["key"]] + list(e.get("replaces", []))})
    return {"clumps": str((adir / "ground" / "clumps.glb").resolve()), "removed": removed,
            "materials": con.get("materials", {}), "textures": con.get("textures", {})}


def _lights(model, center, r, lift=None) -> list[list[float]]:
    """Street lights near a view: the lamp (8 m high, M6's prototype) over each pole (AG15:
    the preview hangs a spot light under it, pointing down; on M13's terrain over the ground
    at its foot)."""
    out = []
    for p in model.props:
        if p.type != "prop.street_light" or not _near(p.position, center, r):
            continue
        g = lift.ground(p.position[0], p.position[1]) if lift is not None else 0.0
        out.append([p.position[0], p.position[1], g + p.position[2] + 7.6 * p.scale[2]])
    out.sort(key=lambda q: ((q[0] - center[0]) ** 2 + (q[1] - center[1]) ** 2, q[0], q[1]))
    return out[:MAX_LIGHTS]


WASH_R = 260.0           # AG15: the large signs near a night view that wash their facade
WASH_KINDS = ("billboard", "banner", "holo_ad")
MAX_WASHES = 40


def _washes(model, center, r, lift=None) -> list[dict]:
    """AG15: M20's large facade signs near a view (billboards, banners, holo-boards in front
    of a facade): a light 1.5 m in front of each, in a neon color by its id, so it washes
    its facade by night (#90: over its building's base on M13's terrain)."""
    import hashlib
    from ..buildings import systems as SY
    out = []
    for s in model.sign_slots:
        if s.kind not in WASH_KINDS or s.mount not in ("facade", "front") or \
                not _near(s.position, center, r):
            continue
        a = math.radians(s.yaw_deg)
        h = int.from_bytes(hashlib.blake2b(s.id.encode("utf-8"), digest_size=4).digest(),
                           "little")
        c = SY.ACCENTS[h % len(SY.ACCENTS)]
        z = s.position[2] + (lift.slot(s) if lift is not None else 0.0)
        out.append({"pos": [s.position[0] + 1.5 * math.cos(a), s.position[1] +
                            1.5 * math.sin(a), z],
                    "color": [int(c[k:k + 2], 16) / 255.0 for k in (0, 2, 4)],
                    "size": max(s.width_m, s.height_m)})
    out.sort(key=lambda q: ((q["pos"][0] - center[0]) ** 2 + (q["pos"][1] - center[1]) ** 2,
                            q["pos"][0], q["pos"][1]))
    return out[:MAX_WASHES]


def core_views(model, man: dict, width: int) -> list[dict]:
    """AG15's shows (`--views core`): the corporate core (the district of most towers by
    archetype `corporate_core`, else by towers) from the air south of it (`core`), and a
    street through it at eye level (`core_street`: its longest avenue or street near the
    towers' middle, looking along it)."""
    from collections import Counter
    towers = [b for b in model.buildings if b.form is not None and b.form.tower]
    if not towers:
        return []
    arch = {d.id: d.archetype for d in model.districts}
    n = Counter(b.district_id for b in towers)
    did = max(n, key=lambda d: (arch.get(d) == "corporate_core", n[d], d))
    ts = [b for b in towers if b.district_id == did]
    from citygen import geom as G
    ts = [b for b in ts if b.footprint is not None]
    if not ts:
        return []
    cs = [G.from_model_poly(b.footprint).centroid for b in ts]
    cx = sum(p.x for p in cs) / len(cs)
    cy = sum(p.y for p in cs) / len(cs)
    hmax = max(b.height_m for b in ts)
    h = int(width * 9 / 16)

    def tiles(p, rr):
        return sorted(t for t in man["tiles"] if _tile_near(t, p, rr))
    d = max(380.0, 2.2 * hmax)
    out = [{"name": "core", "ortho": False, "lens": 32.0,
            "eye": [cx - 0.42 * d, cy - d, 0.75 * hmax + 120.0],
            "target": [cx, cy, 0.3 * hmax], "w": width, "h": h,
            "shell_tiles": tiles((cx, cy), 650.0), "far": True}]
    best = None
    for s in model.road_segments:
        if s.road_class not in ("avenue", "street") or s.level != 0 or s.bridge or s.tunnel:
            continue
        pts = [tuple(p) for p in s.centerline]
        L = _plen(pts)
        if L < 90.0:
            continue
        mx, my = _at(pts, L / 2.0)
        dd = math.hypot(mx - cx, my - cy)
        if dd > 450.0:
            continue
        k = (dd - 0.4 * min(L, 250.0), s.id)
        if best is None or k < best[0]:
            best = (k, s, pts, L)
    if best is not None:
        _, s, pts, L = best
        x0, y0 = _at(pts, min(12.0, L * 0.1))
        x1, y1 = _at(pts, min(L, 90.0))
        out.append({"name": "core_street", "ortho": False, "lens": 24.0,
                    "eye": [x0, y0, 1.8], "target": [x1, y1, 5.0], "w": width, "h": h,
                    "shell_tiles": tiles((x0, y0), 420.0)})
    return out


def run(args, progress=None) -> dict:
    from ..brief import load_model
    from ..progress import Progress
    P = progress if progress is not None else Progress(quiet=True)
    bdir = Path(args.build)
    adir = bdir / "assets"
    with P.stage("load"):
        man = json.loads((adir / "manifest.json").read_text())
        mats = json.loads((adir / "materials.json").read_text())
        signs = json.loads((adir / "signs.json").read_text())
        con = json.loads((adir / "unreal_contribution.streets.json").read_text())
        cp = adir / "unreal_contribution.connections.json"
        conn = json.loads(cp.read_text()) if cp.is_file() else {"entries": []}
        model, _, _ = load_model(bdir)
    od = Path(args.out) if args.out else adir / "previews_ag6"
    od.mkdir(parents=True, exist_ok=True)
    bo = Path(args.blockout) if args.blockout else bdir
    cams = PV.cameras(bdir, bo)
    which = set(args.views or ["districts", "street"])
    kinds = {"city", "city_full", "districts", "street", "deck", "water", "core"}
    views = PV.plan_views(man, cams, args.width, which & kinds)
    if "core" in which:
        views += core_views(model, man, args.width)          # (AG15)
    if "deck" in which and cams.get("deck"):
        from ..streets.ctx import Ground
        ox, oy = cams["deck"]["origin"]
        views.append(deck_view(man, cams["deck"], args.width, Ground(model).at(ox, oy)))
    if "water" in which:
        views += water_views(model, man, args.width)
    named = [v for v in (args.views or []) if v not in kinds]
    if named:
        allv = PV.plan_views(man, cams, args.width, {"districts", "street"})
        views = [v for v in allv if v["name"] in named] + \
            [v for v in water_views(model, man, args.width) if v["name"] in named] + \
            [v for v in core_views(model, man, args.width) if v["name"] in named]
    for k, (eye, tgt) in enumerate(zip(args.eye, args.target), 1):
        near = [t for t in man["tiles"] if _tile_near(t, tgt, PV.STREET_R)]
        views.append({"name": f"custom_{k}", "ortho": False, "lens": args.lens,
                      "eye": list(eye), "target": list(tgt), "w": args.width,
                      "h": int(args.width * 9 / 16), "shell_tiles": sorted(near)})
    stiles = sorted({e["tile"] for e in con["entries"]})
    ctiles = sorted(man.get("connections") or {})
    lift = _Lift(model)
    with P.stage("views", total=len(views)) as st:
        for v in views:
            tgt = v["target"]
            v["parts"] = PV.instances(man, v["shell_tiles"])
            # (AG4: the skybridges of the shells' tiles)
            v["connection_tiles"] = (list(ctiles) if v.get("whole") else
                                     sorted(set(v["shell_tiles"]) & set(ctiles)))
            if v["ortho"] or v.get("section"):
                v["street_tiles"] = (list(stiles) if v.get("whole") else
                                     sorted(set(v["shell_tiles"]) & set(stiles)))
                v["signs"], v["lights"], v["washes"] = [], [], []
            elif v.get("far") and v["name"] == "core":
                # (AG15: the core from the air: its streets, lamps and signs round the
                # middle it looks at)
                v["street_tiles"] = [t for t in stiles if _tile_near(t, tgt, 650.0)]
                v["signs"] = _signs(model, signs, adir, tgt, 450.0, lift)
                v["lights"] = _lights(model, tgt, 450.0, lift)
                v["washes"] = _washes(model, tgt, 450.0, lift)
            else:
                v["street_tiles"] = [t for t in stiles if _tile_near(t, v["eye"], STREET_R)]
                v["signs"] = _signs(model, signs, adir, v["eye"], SIGN_R, lift)
                v["lights"] = _lights(model, v["eye"], LIGHT_R, lift)
                v["washes"] = _washes(model, v["eye"], WASH_R, lift)
            st.advance()
        ag8 = _ag8(adir, views)
        wat = _water(adir, views)
        gr = _ground(adir, views)
    if gr is not None:
        mats["parts"]["ground"] = gr["materials"]
        mats["textures"] = {**mats.get("textures", {}), **gr["textures"]}
    modes = ["night"] if args.only_night else (["day", "night"] if args.night else ["day"])
    job = {"assets": str(adir), "out": str(od), "views": views, "modes": modes,
           "blend": str(bo / "city.blend"), "materials": mats["parts"],
           "files": _files(adir, mats["textures"]), "props": _props(man),
           "removed": sorted({e["key"] for e in con["entries"] + conn["entries"]} |
                             {r for e in con["entries"] for r in e.get("replaces", [])} |
                             {g for v in (man.get("green_replaces") or {}).values() for g in v}
                             | set((ag8 or {}).get("removed", []))
                             | set((wat or {}).get("removed", []))
                             | set((gr or {}).get("removed", []))),
           "water_parts": (wat or {}).get("parts"),
           "ag8_families": (ag8 or {}).get("families", []),
           "ground": {"clumps": gr["clumps"]} if gr is not None else {},
           "proxy_tiles": sorted(man["tiles"]), "samples": args.samples,
           "hour": float(getattr(args, "hour", 21.0) or 21.0),
           "era_slots": sorted(CT.ERA_SLOTS)}
    return _blender(job, "ag6_preview.py", args.blender, od, progress, len(views))


WATER_R = 700.0          # AG12: the water tiles of a view within this of its eye or target
STONES_R = 320.0         # ... and its riprap stones within this of its eye


def water_views(model, man: dict, width: int) -> list[dict]:
    """AG12's shows (`--views water`): `water_canal`, along the longest quayed canal from
    over its water; `water_bank`, a river's longest natural or riprap bank from over the
    water beside it; `water_harbor`, the biggest harbor basin (else the sea's harbor water) from
    above."""
    from citygen import geom as G
    from ..streets.ctx import Ground
    gd = Ground(model)
    h = int(width * 9 / 16)
    out = []

    def tiles(p):
        return sorted(t for t in man["tiles"] if _tile_near(t, p, 600.0))

    def level(wid, x, y):
        return gd.water_level(wid, 0.0) if not gd.flat else gd.surface.get(wid, -1.5)
    ww = {w.id: w for w in model.waterways}
    quays = [q for q in model.quays if ww.get(q.waterway_id) is not None and
             ww[q.waterway_id].kind == "canal" and len(ww[q.waterway_id].centerline) >= 2]
    if quays:
        q = max(quays, key=lambda q: (_plen(q.line), q.id))
        w = ww[q.waterway_id]
        cl = [tuple(p) for p in w.centerline]
        s = _straight(cl, 60.0)
        a = _at(cl, s)
        tx, ty = _dir(cl, s, 60.0)
        z = level(w.id, *a)
        out.append({"name": "water_canal", "ortho": False, "lens": 24.0,
                    "eye": [a[0], a[1], z + 2.6],
                    "target": [a[0] + tx * 60.0, a[1] + ty * 60.0, z + 0.6],
                    "w": width, "h": h, "shell_tiles": tiles(a)})
    rivers = {e.id for e in [*model.rivers, *model.channels]}
    bks = [k for k in model.banks if k.water_id in rivers and
           k.kind in ("natural_bank", "riprap") and _plen(k.line) > 80.0]
    if bks:
        k = max(bks, key=lambda k: (_plen(k.line), k.id))
        pts = [tuple(p) for p in k.line]
        s = _straight(pts, 50.0)
        x, y = _at(pts, s)
        tx, ty = _dir(pts, s, 50.0)
        lx, ly = -ty, tx                          # (the water's side, left of the line)
        z = level(k.water_id, x, y)
        # (from over the water beside it, looking along it: a hedge or a wall on the land side
        # would hide the slope)
        eye = [x + lx * (k.width_m + 7.0), y + ly * (k.width_m + 7.0), z + 2.2]
        tgt = [x + lx * (k.width_m * 0.4) + tx * 40.0, y + ly * (k.width_m * 0.4) + ty * 40.0,
               z + 0.2]
        out.append({"name": "water_bank", "ortho": False, "lens": 28.0, "eye": eye,
                    "target": tgt, "w": width, "h": h, "shell_tiles": tiles((x, y))})
    basins = [w for w in model.waterways if w.kind in ("basin", "marina")]
    c = None
    if basins:
        b = max(basins, key=lambda w: (G.area(G.from_model_poly(w.polygon)), w.id))
        p = G.from_model_poly(b.polygon).centroid
        c = (p.x, p.y)
    elif model.seas and model.seas[0].exposure:
        zs = [e for e in model.seas[0].exposure if e.kind == "harbor"] or \
            [e for e in model.seas[0].exposure if e.kind == "sheltered"]
        if zs:
            e = max(zs, key=lambda e: G.area(G.from_model_poly(e.polygon)))
            p = G.from_model_poly(e.polygon).centroid
            c = (p.x, p.y)
    if c is not None:
        out.append({"name": "water_harbor", "ortho": False, "lens": 35.0,
                    "eye": [c[0] - 160.0, c[1] - 420.0, 330.0], "target": [c[0], c[1], 0.0],
                    "w": width, "h": h, "shell_tiles": tiles(c), "far": True})
    return out


def _dir(pts, s: float, d: float) -> tuple[float, float]:
    """The unit direction from the point at s to the point at s + d along a polyline."""
    (x0, y0), (x1, y1) = _at(pts, s), _at(pts, min(s + d, _plen(pts)))
    n = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1e-6)
    return (x1 - x0) / n, (y1 - y0) / n


def _straight(pts, d: float) -> float:
    """Where along a polyline the straightest stretch of length d starts (every 5 m: the
    smallest turn between its first and last 5 m, ties to the first)."""
    L = _plen(pts)
    best, out = None, 0.0
    s = 0.0
    while s + d <= L or s == 0.0:
        a = _dir(pts, s, 5.0)
        b = _dir(pts, max(0.0, min(s + d, L) - 5.0), 5.0)
        turn = 1.0 - (a[0] * b[0] + a[1] * b[1])
        if best is None or turn < best - 1e-9:
            best, out = turn, s
        s += 5.0
        if s + d > L:
            break
    return out


def _plen(pts) -> float:
    return sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(pts, pts[1:]))


def _at(pts, s: float) -> tuple[float, float]:
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        if acc + d >= s and d > 0:
            f = (s - acc) / d
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        acc += d
    return tuple(pts[-1])


def _water(adir: Path, views: list) -> dict | None:
    """AG12's water for the views (its contribution): the parts pack, the blockout keys it
    replaces and drops, per view the water tiles near it and the riprap stones near its eye
    (world transforms)."""
    wp = adir / "unreal_contribution.water.json"
    if not wp.is_file():
        return None
    cw = json.loads(wp.read_text(encoding="utf-8"))
    removed = sorted({k for e in cw["entries"] for k in [e["key"]] + list(e.get("replaces", []))})
    wtiles = sorted({e["tile"] for e in cw["entries"] if e.get("tile")})
    for v in views:
        r = WATER_R * (2.0 if v.get("far") else 1.0)
        v["water_tiles"] = [t for t in wtiles if _tile_near(t, v["eye"], r) or
                            _tile_near(t, v["target"], r)]
        if v.get("whole"):
            v["water_tiles"] = list(wtiles)
        elif v["ortho"]:
            v["water_tiles"] = sorted(set(v["water_tiles"]) | (set(v["shell_tiles"]) &
                                                               set(wtiles)))
        pts: dict[str, list] = {}
        for e in cw["entries"]:
            px, py, pz = e.get("pivot", [0.0, 0.0, 0.0])
            for q in e.get("parts", []):
                for xf in q["xforms"]:
                    x, y = xf[0] + px, xf[1] + py
                    if not v["ortho"] and _near((x, y), v["eye"], STONES_R):
                        pts.setdefault(q["node"], []).append(
                            [x, y, xf[2] + pz, xf[3]] + list(xf[4:7]))
        v["water_points"] = dict(sorted(pts.items()))
    return {"parts": str((adir / "water" / "parts.glb").resolve()), "removed": removed}


DECK_R = 420.0          # the deck section's tiles: within this of its plane's middle
DECK_LENS = 35.0        # its lens (the blockout's 22 mm shows mostly sky and nothing)
DECK_ASPECT = 2.4       # and its frame's width over its height (a section is wide and low)
DECK_FOOT_M = 3.0       # the ground this far over the frame's bottom


def deck_view(man: dict, cut: dict, width: int, ground: float = 0.0) -> dict:
    """AG10: the section across the biggest M14 deck (the blockout's `deck` view), looking
    level along its plane's normal from the blockout's eye; the camera's near clip on the
    plane cuts everything on its side (Blender hides what lies wholly there), its frame
    shifted up so the ground at the cut (`ground`) sits `DECK_FOOT_M` over its bottom."""
    ox, oy = cut["origin"]
    nx, ny = cut["n"]
    ex, ey, ez = cut["eye"]
    ez += ground                               # (the blockout's eye is over flat ground)
    d = (ex - ox) * nx + (ey - oy) * ny
    lens = DECK_LENS
    w_at = 2.0 * d * 18.0 / lens               # (the frame's width at the cut: 36 mm sensor)
    bottom = ez - w_at / (2.0 * DECK_ASPECT)   # (half its height under the eye)
    shift = (ground - DECK_FOOT_M - bottom) / w_at
    tiles = sorted(t for t in man["tiles"] if _tile_near(t, (ox, oy), DECK_R))
    return {"name": "deck", "ortho": False, "lens": lens, "eye": [ex, ey, ez],
            "target": [ex - nx * d, ey - ny * d, ez], "w": width, "h": int(width / DECK_ASPECT),
            "shell_tiles": tiles, "section": {"origin": [ox, oy], "n": [nx, ny],
                                              "clip": round(d, 3),
                                              "shift_y": round(shift, 4)}}


def _tile_near(name: str, p, r) -> bool:
    x0, y0, x1, y1 = PV._tile_box(name)
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return dx * dx + dy * dy <= r * r


def _blender(job: dict, script: str, blender: str | None, od: Path, progress=None,
             total: int | None = None) -> dict:
    """Run a script on the job; `progress`: a bar over its views or boards (each script's
    `CGPROGRESS` lines, `assetgen/blenderrun.py`); without it Blender's log lines print."""
    from citygen.blockout import find_blender
    from ..blenderrun import run as run_blender
    from ..progress import Progress
    P = progress if progress is not None else Progress(quiet=True)
    exe = find_blender(blender)
    if exe is None:
        raise RuntimeError("no Blender (set BLENDER or --blender)")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(job, f)
        jp = f.name
    sp = Path(__file__).resolve().parent.parent / "blender" / script
    try:
        with P.stage("blender", total=total) as st:
            code, sout, serr = run_blender(
                [exe, "-b", "--factory-startup", "-P", str(sp), "--", jp], st, keep="[ag6",
                log=(lambda m: print(m, flush=True)) if progress is None else None)
    finally:
        Path(jp).unlink(missing_ok=True)        # (a whole city's job is ~90 MB)
    rep_p = od / "ag6_report.json"
    if code != 0 or not rep_p.is_file():
        sys.stderr.write(sout[-4000:] + serr[-4000:])
        raise RuntimeError(f"Blender failed ({code})")
    return json.loads(rep_p.read_text())


def board_job(args, progress=None) -> dict:
    from .build import generate
    lib = LB.load(None, args.density) or generate(None, args.density, progress=progress)
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
    from ..progress import Progress
    prog = Progress(quiet=True if getattr(args, "quiet", False) else None)
    try:
        if args.command == "board":
            job = board_job(args, prog)
            rep = _blender(job, "ag6_board.py", args.blender, Path(args.out), prog,
                           len(job["boards"]))
        else:
            rep = run(args, prog)
    except (OSError, RuntimeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    prog.summary()
    print(f"rendered {len(rep.get('files', []))} images")
    return 0
