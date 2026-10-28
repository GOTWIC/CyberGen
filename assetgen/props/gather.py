"""What the props stage reads from a city: every prop, plant and sign slot, with its
district's style, its variant, its instance transform, and for the meshes made per tile
(exact props, signs) the canonical inputs their makers read.

- **Props**: kind, district style (the id's district, else the district under it), variant
  by a hash of the id; awnings and scaffolding turned so their wall is on the side the
  frames in `variants.py` expect (the side nearer their building's footprint); AC units and
  wall lights the brief finds off their wall get a bracket of that length
  (`brief.mount_props`: `gap_m`); M6's highway median barriers are dropped where AG7's road
  piece has its continuous barrier (scope 5.3; AG7's notes).
- **Plants**: species (M6's, else its type's), variant by a hash of the id, scaled to the
  plant's crown and height; facade greenery split into patches of about 1.5 m along its
  length (awnings likewise into segments of about 2 m).
- **Signs**: per slot its text (the point of interest in its unit, else a generated shop
  name; corporations of the city on billboards and holo-ads), script, look, colors (the
  district's neon palette from the asset spec, else its era's) and the gap to its wall.
- **Ground** (M13): a model z is measured from the ground where it stands, so every
  placement is lifted by its building's `base_m` when it hangs on a building or stands on
  its roof (AG1's shells stand there), else by the finished ground at its point (as the
  blockout lifts M15's instances); nothing on a flat city.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import shapely

from citygen import dmath as M
from citygen import geom as G

from .. import canon as C
from ..streets.ctx import Ground
from . import materials as MT
from . import signs as SG
from . import styles as ST
from .build import tile_center, tile_of
from .trees import BASE
from .variants import REACH

IVY_PATCH_M = 1.5
AWNING_SEGMENT_M = 2.0
BRACKET_MIN_M = 0.02


@dataclass
class Gathered:
    families: list = field(default_factory=list)       # [(what, name)]
    groups: dict = field(default_factory=dict)         # blockout key -> group
    exact: dict = field(default_factory=dict)          # tile -> [(key, kind, items)]
    signs: dict = field(default_factory=dict)          # tile -> [sign]
    dropped: dict = field(default_factory=dict)        # prop id -> reason
    covered: dict = field(default_factory=dict)        # prop id -> how
    stats: dict = field(default_factory=dict)
    kinds: dict = field(default_factory=dict)          # prop kind -> count in the model
    species: dict = field(default_factory=dict)        # species -> count


class _Districts:
    def __init__(self, m):
        self.d = {d.id: d for d in m.districts}
        self.order = sorted(self.d)
        with G.canonical():
            self.polys = [G.from_model_poly(self.d[i].polygon) for i in self.order]
        self.tree = shapely.STRtree(self.polys) if self.polys else None

    def of(self, eid: str, x: float, y: float) -> str | None:
        head = eid.split(".", 1)[0]
        if head in self.d:
            return head
        if self.tree is None:
            return None
        hit = self.tree.query(shapely.points(x, y), predicate="intersects")
        return self.order[min(hit.tolist())] if len(hit) else None


def _wall_plus_y(poly, x: float, y: float, yaw: float, reach: float) -> bool:
    """Whether a facade thing's wall is on its local +y side: the point that far to its left
    is nearer the footprint than the point to its right."""
    a = M.radians(yaw)
    lx, ly = -M.sin(a), M.cos(a)
    if poly is None:
        return True
    dp = poly.distance(shapely.points(x + lx * reach, y + ly * reach))
    dm = poly.distance(shapely.points(x - lx * reach, y - ly * reach))
    return dp <= dm


def _seg_dist(px, py, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    qx, qy = ax + dx * t - px, ay + dy * t - py
    return math.sqrt(qx * qx + qy * qy)


def gather(model, spec, briefs: dict | None, out_dir: Path) -> Gathered:
    g = Gathered()
    ds = _Districts(model)
    blds = {b.id: b for b in model.buildings}
    foot = {}
    with G.canonical():
        for b in model.buildings:
            if b.footprint is not None:
                foot[b.id] = G.from_model_poly(b.footprint)
    fids = sorted(foot)
    ftree = shapely.STRtree([foot[i] for i in fids]) if fids else None
    gd = Ground(model)
    bases = {b.id: float(b.base_m) for b in model.buildings
             if getattr(b, "base_m", None) is not None}

    def lift(x, y, z, bid=None) -> float:
        """The height a placement's z is measured from (module docstring, Ground)."""
        if gd.flat:
            return 0.0
        if bid is None and z > 0.6 and ftree is not None:
            hit = ftree.query(shapely.points(x, y), predicate="intersects")
            if len(hit):
                bid = fids[min(hit.tolist())]
        if bid in bases:
            return bases[bid]
        return gd.at(x, y)

    def near_foot(x, y):
        if ftree is None:
            return None
        hit = ftree.query(shapely.points(x, y), predicate="dwithin", distance=4.0)
        if not len(hit):
            return None
        best = min(hit.tolist(), key=lambda i: (round(foot[fids[i]].distance(
            shapely.points(x, y)), 4), fids[i]))
        return foot[fids[best]]

    # the briefs' facade props: building, on the wall, gap
    mount: dict[str, dict] = {}
    for bid in sorted(briefs or {}):
        for e in (briefs[bid].get("props") or []):
            if e.get("end") is not None:
                continue
            mount.setdefault(e["id"], {"building": bid, "on_wall": e["on_wall"],
                                       "gap": float(e["gap_m"])})
    # AG7's road pieces with their median barrier
    roads = set()
    smf = Path(out_dir) / "streets" / "manifest.json"
    if smf.is_file():
        try:
            sm = json.loads(smf.read_text(encoding="utf-8"))
            for pid, r in sm.get("pieces", {}).items():
                if r.get("kind") == "street.road" and r.get("triangles", 0) > 0:
                    roads.add(pid)
        except (OSError, ValueError):
            roads = set()
    segs = {s.id: s for s in model.road_segments}

    def style_of(did):
        return ST.style_of(ds.d[did].archetype) if did in ds.d else "civic"

    # -- props
    groups: dict = {}
    exact: dict = defaultdict(lambda: defaultdict(list))
    kinds_used = set()

    def add(key, kind, cls, tile, part, xf, pid):
        gr = groups.setdefault(key, {"cls": cls, "kind": kind, "tile": tile, "parts": {}})
        p = gr["parts"].setdefault(part, {"xforms": [], "ids": []})
        p["xforms"].append(xf)
        p["ids"].append(pid)

    brackets = 0
    for p in sorted(model.props, key=lambda p: p.id):
        kind = p.type.split(".", 1)[1]
        g.kinds[kind] = g.kinds.get(kind, 0) + 1
        x, y, z = p.position
        t = tile_of(x, y)
        key = f"prop.{kind}.{t}"
        if kind in ST.SLOTTED:
            g.covered[p.id] = "sign slot"
            continue
        did = ds.of(p.id, x, y)
        st = style_of(did)
        mm = mount.get(p.id)
        z = z + lift(x, y, z, (mm or {}).get("building") or (p.attrs or {}).get("building"))
        if kind in ST.EXACT:
            item = {"prop": {"id": p.id, "position": [C.m2(x), C.m2(y), C.m2(z)],
                             "yaw_deg": C.deg(p.yaw_deg), "scale": [C.m2(v) for v in p.scale],
                             "attrs": {k: v for k, v in sorted((p.attrs or {}).items())
                                       if k in ("sag_m", "name")}},
                    "style": st}
            if kind == "scaffolding":
                b = (p.attrs or {}).get("building")
                item["wall"] = 1.0 if _wall_plus_y(foot.get(b) or near_foot(x, y), x, y,
                                                   p.yaw_deg, 0.8) else -1.0
            if kind == "gate":
                pal = _palette(spec, ds.d.get(did), did)
                item["color"] = ST.choice(pal, "ag8.gate", p.id)
            item["digest"] = C.digest(item)
            exact[t][key].append(item)
            g.covered[p.id] = "exact"
            continue
        if kind == "barrier":
            sid = (p.attrs or {}).get("segment")
            s = segs.get(sid)
            if sid in roads and s is not None and s.road_class == "highway" and \
                    s.cross_section.median_m > 0:
                g.dropped[p.id] = "the road piece's median barrier (AG7)"
                groups.setdefault(key, {"cls": "prop", "kind": kind, "tile": t, "parts": {}})
                continue
        kinds_used.add(kind)
        n = ST.PROP_VARIANTS[kind]
        if kind == "trash":
            item = (p.attrs or {}).get("item", "bag")
            base = {"bag": 0, "box": 4, "can": 8}.get(item, 0)
            k = base + ST.pick(4, "ag8.prop", p.id)
        else:
            k = ST.pick(n, "ag8.prop", p.id)
        yaw = p.yaw_deg
        if kind == "awning":
            poly = foot.get(mm["building"]) if mm else near_foot(x, y)
            if not _wall_plus_y(poly, x, y, yaw, p.scale[1] / 2.0 + 0.25):
                yaw = yaw + 180.0
        yaw = C.deg(((yaw + 180.0) % 360.0) - 180.0)
        cx, cy = tile_center(t)
        if kind == "awning":
            # in segments of about 2 m along the facade (arms, ribs and corrugation keep
            # their size), each a variant of the unit's own family member
            L = p.scale[0]
            n = max(1, int(round(L / AWNING_SEGMENT_M)))
            a = M.radians(yaw)
            c, s = M.cos(a), M.sin(a)
            for i in range(n):
                off = -L / 2.0 + L * (i + 0.5) / n
                add(key, kind, "prop", t, ST.variant_name(kind, st, k),
                    [C.m(x + c * off - cx), C.m(y + s * off - cy), C.m(z), yaw,
                     C.m(L / n), C.m(p.scale[1]), C.m(p.scale[2])], p.id)
        else:
            xf = [C.m(x - cx), C.m(y - cy), C.m(z), yaw] + [C.m(v) for v in p.scale]
            add(key, kind, "prop", t, ST.variant_name(kind, st, k), xf, p.id)
        if kind in REACH and mm and mm["gap"] > BRACKET_MIN_M and \
                (p.attrs or {}).get("mount") != "deck":
            a = M.radians(p.yaw_deg)
            bx = x - M.cos(a) * REACH[kind]
            by = y - M.sin(a) * REACH[kind]
            kb = ST.pick(ST.PROP_VARIANTS["bracket"], "ag8.bracket", p.id)
            add(key, kind, "prop", t, ST.variant_name("bracket", st, kb),
                [C.m(bx - cx), C.m(by - cy), C.m(z), C.deg(((p.yaw_deg + 180.0) % 360.0) - 180.0),
                 C.m(mm["gap"]), 1.0, 1.0], p.id)
            kinds_used.add("bracket")
            brackets += 1
    # -- plants
    species_used = set()
    for p in sorted(model.plants, key=lambda p: p.id):
        typ = p.type.split(".", 1)[1]
        sp = p.species if p.species in ST.PLANT_VARIANTS else ST.SPECIES_OF_TYPE.get(typ, "oak")
        g.species[sp] = g.species.get(sp, 0) + 1
        species_used.add(sp)
        x, y, z = p.position
        z = z + lift(x, y, z, (p.attrs or {}).get("building"))
        t = tile_of(x, y)
        key = f"plant.{typ}.{t}"
        cx, cy = tile_center(t)
        r0, h0 = BASE[sp]
        if typ == "facade_greenery":
            a = p.attrs or {}
            yaw = float(a.get("yaw_deg", 0.0))
            L = float(a.get("length_m", 1.0))
            n = max(1, int(round(L / IVY_PATCH_M)))
            c, s = M.cos(M.radians(yaw)), M.sin(M.radians(yaw))
            for i in range(n):
                off = -L / 2.0 + L * (i + 0.5) / n
                k = ST.pick(ST.PLANT_VARIANTS[sp], "ag8.plant", p.id, i)
                add(key, typ, "plant", t, ST.plant_name(sp, k),
                    [C.m(x + c * off - cx), C.m(y + s * off - cy), C.m(z), C.deg(yaw),
                     C.m(L / n / IVY_PATCH_M), 1.0, C.m(p.height_m / h0)], p.id)
            continue
        k = ST.pick(ST.PLANT_VARIANTS[sp], "ag8.plant", p.id)
        yaw = C.deg(360.0 * ST.u("ag8.yaw", p.id) - 180.0)
        add(key, typ, "plant", t, ST.plant_name(sp, k),
            [C.m(x - cx), C.m(y - cy), C.m(z), yaw, C.m(p.crown_radius_m / r0),
             C.m(p.crown_radius_m / r0), C.m(p.height_m / h0)], p.id)
    g.families = sorted([("prop", k) for k in kinds_used | {kk for kk in g.kinds
                                                             if kk in ST.PROP_VARIANTS}]) + \
        sorted(("plant", s) for s in species_used)
    g.families = sorted(set(g.families))
    g.groups = {k: groups[k] for k in sorted(groups)}
    g.exact = {t: [(k, k.split(".")[1], exact[t][k]) for k in sorted(exact[t])]
               for t in sorted(exact)}
    # -- signs
    g.signs = _signs(model, spec, ds, blds, mount, lift)
    n_inst = sum(len(p["xforms"]) for gr in g.groups.values() for p in gr["parts"].values())
    g.stats = {"props": len(model.props), "plants": len(model.plants),
               "sign_slots": len(model.sign_slots), "instances": n_inst,
               "brackets": brackets, "dropped": len(g.dropped),
               "exact": sum(len(items) for t in g.exact.values() for _, _, items in t),
               "signs": sum(len(v) for v in g.signs.values())}
    return g


def _palette(spec, d, did) -> list[str]:
    era = ST.era_of(d.archetype if d is not None else None)
    if spec is not None and d is not None:
        sd = (getattr(spec, "districts", None) or {}).get(d.name)
        pal = getattr(sd, "neon_palette", None) if sd is not None else None
        if pal:
            return list(pal)
    return list(MT.NEON_ERA.get(era, MT.NEON))


def _scripts(spec, d) -> dict | None:
    if spec is None or d is None:
        return None
    sd = (getattr(spec, "districts", None) or {}).get(d.name)
    if sd is not None and getattr(sd, "signage_scripts", None):
        return dict(sd.signage_scripts)
    es = (getattr(spec, "eras", None) or {}).get(ST.era_of(d.archetype))
    if es is not None and getattr(es, "signage_scripts", None):
        return dict(es.signage_scripts)
    return None


def _unit_of(b, x: float, y: float) -> int | None:
    if b is None or not b.units:
        return None
    best = None
    for i, u in enumerate(b.units):
        d = _seg_dist(x, y, u.edge[0], u.edge[1])
        if best is None or d < best[0] - 1e-9:
            best = (d, i)
    return best[1]


def _signs(model, spec, ds: _Districts, blds: dict, mount: dict, lift) -> dict:
    poi = {}
    for p in sorted(model.pois, key=lambda p: p.id):
        if p.building_id and p.unit_index is not None and p.kind in ("bar", "clinic", "vendor"):
            poi.setdefault((p.building_id, p.unit_index), p.name)
    corps_by_d = defaultdict(list)
    corps = []
    for f in sorted(model.factions, key=lambda f: f.id):
        if f.kind == "corporate":
            corps.append(f.name)
            if f.home_district_id:
                corps_by_d[f.home_district_id].append(f.name)
    from citygen.gameplay import CORP_A
    out: dict = defaultdict(list)
    for s in sorted(model.sign_slots, key=lambda s: s.id):
        x, y, z = s.position
        t = tile_of(x, y)
        b = blds.get(s.building_id) if s.building_id else None
        did = b.district_id if b is not None and b.district_id in ds.d else ds.of(s.id, x, y)
        d = ds.d.get(did)
        era = ST.era_of(d.archetype if d is not None else None)
        st = ST.style_of(d.archetype if d is not None else None)
        pal = _palette(spec, d, did)
        c1 = ST.choice(pal, "ag8.c1", s.id)
        rest = [c for c in pal if c != c1] or pal
        c2 = ST.choice(rest, "ag8.c2", s.id)
        script = SG.script_of(era, _scripts(spec, d), "ag8.sign", s.id)
        inp = {"kind": s.kind, "mount": s.mount, "w": C.m2(round(s.width_m * 20) / 20.0),
               "h": C.m2(round(s.height_m * 20) / 20.0), "colors": [c1, c2],
               "face": (c2 if ST.u("ag8.fsat", s.id) < 0.55 else
                        ST.choice(SG.FACE_COLORS, "ag8.face", s.id)), "style": st}
        if s.kind == "shop_sign":
            unit = _unit_of(b, x, y)
            name = poi.get((s.building_id, unit)) if unit is not None else None
            text = SG.shop_text(s.content, name, "ag8.shop", s.id)
            blade = s.mount == "blade"
            # a name too long for its sign keeps only its use word
            limit = int(s.height_m / 0.32) if blade else int(s.width_m / 0.3)
            if len(text) > max(limit, 3):
                words = text.split()
                text = words[-1] if len(words[-1]) <= max(limit, 3) else words[-1][:max(limit, 3)]
            inp.update(text=text, script=script,
                       glyphs=(2 + ST.pick(3, "ag8.gl", s.id)) if script != "latin" else 0,
                       look=ST.choice((SG.LOOKS_BLADE if blade else SG.LOOKS_FACADE)[st],
                                      "ag8.look", s.id))
            mm = mount.get(s.prop_id) if s.prop_id else None
            if mm and mm["gap"] > BRACKET_MIN_M:
                inp["gap"] = C.m2(mm["gap"])
            if script == "latin":
                inp["script"] = "latin"
        elif s.kind in ("billboard", "holo_ad"):
            names = corps_by_d.get(did) or corps
            if s.content == "corporate" and names:
                brand = ST.choice(names, "ag8.brand", s.id).split()[0]
            else:
                brand = ST.choice(CORP_A, "ag8.brand", s.id)
            prod = ST.choice(SG.PRODUCTS, "ag8.prod", s.id)
            inp.update(text=brand.upper() if ST.u("ag8.bt", s.id) < 0.5 else f"{brand} {prod}".upper(),
                       sub=f"{ST.choice(SG.AD_WORDS, 'ag8.ad', s.id)} {prod}",
                       two_sided=bool(s.two_sided), script=script,
                       dark_text=ST.u("ag8.dt", s.id) < 0.3,
                       logo_right=ST.u("ag8.lr", s.id) < 0.5)
        else:
            if script in ("latin", "cyrillic"):
                text = ST.choice(SG.BAND_WORDS, "ag8.band", s.id)
            else:
                text = "x" * (3 + ST.pick(3, "ag8.bn", s.id))
                inp["seed"] = C.digest(["ag8.band", s.id])[:8]
            inp.update(text=text, script=script)
        dg = C.digest(inp)
        # (an "h": Blender's glTF import reads a name ending in a dot and digits as a
        # counter, and a long one overflows it)
        out[t].append({"id": s.id, "node": "sign.h" + dg[:16], "inputs": inp, "digest": dg,
                       "extra_name": s.id,
                       "pivot": [C.m2(x), C.m2(y), C.m2(z + lift(x, y, z, s.building_id))],
                       "yaw": C.deg(s.yaw_deg), "kind": s.kind,
                       "prop_id": s.prop_id})
    for t in out:
        # holo-ads keep their own nodes (their LOD chain is named by the slot)
        for e in out[t]:
            if e["kind"] == "holo_ad":
                e["node"] = e["id"]
    return {t: out[t] for t in sorted(out)}

