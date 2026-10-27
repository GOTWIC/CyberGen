"""M4 exports beside the Blender blockout (scope section 8).

- `map_svg`: layered 2D map, one Inkscape layer per kind with the layer names of the hand
  traced maps (coast, highway, avenue, street, elevated road, building, landmark, water, park,
  plaza, pier; stroke width = road width, building height as the object label), plus district,
  megasite, transit, label and legend layers. 1 SVG unit = 1 m.
- `map_png`: the same map drawn with matplotlib, with district and place labels and a legend.
- `legacy_plan`: the box/cylinder primitives of `corporate_core_plan.json`, for
  `unreal/build_greybox_unreal.py` (unchanged).
- `graphs`: lane graph, pedestrian graph and transit lines as JSON (ZoneGraph and Mass later).
- `props_csv`: prop and plant instances (M6), one row each, for instanced meshes in an engine.
- `gameplay`: the gameplay layer (M11) for lifegen, assetgen and the engine: hour bands,
  factions, zones, points of interest, the wealth, danger and police fields, street densities,
  parking, travel points, sign slots, and an index of what stands in each 256 m tile.
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

from . import massing as MS
from . import geom as G
from .blockout import MATERIALS, ROAD_COLORS
from .model import CityModel
from .schematic import ARCHETYPE_COLORS, BG, INK, LAND, MUTED, RIVER, SEA

INK_NS = "http://www.inkscape.org/namespaces/inkscape"
PARK_KINDS = {"park", "pocket_park", "green", "garden", "marsh", "beach"}
ROAD_LAYER = {"highway": "highway", "avenue": "avenue", "street": "street", "alley": "alley",
              "service": "alley", "pedestrian": "pedestrian", "footbridge": "pedestrian"}


def _f(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


class _Frame:
    def __init__(self, bounds):
        self.x0, self.y0, self.x1, self.y1 = bounds

    def p(self, x, y) -> str:
        return f"{_f(x - self.x0)},{_f(self.y1 - y)}"

    def ring(self, pts) -> str:
        return "M" + " L".join(self.p(x, y) for x, y in pts) + " Z"

    def poly(self, poly) -> str:
        return " ".join(self.ring(r) for r in [poly.exterior, *poly.holes])

    def line(self, pts) -> str:
        return "M" + " L".join(self.p(x, y) for x, y in pts)


def _layer(lid: str, label: str, body: list[str], locked: bool = False) -> str:
    lock = ' sodipodi:insensitive="true"' if locked else ""
    return (f'<g inkscape:groupmode="layer" id="layer_{lid}" inkscape:label="{label}"{lock}>\n'
            + "\n".join(body) + "\n</g>")


def map_svg(m: CityModel, path: Path) -> Path:
    F = _Frame(m.bounds)
    W, H = m.bounds[2] - m.bounds[0], m.bounds[3] - m.bounds[1]
    layers = []
    layers.append(_layer("sea", "sea", [
        f'<rect x="0" y="0" width="{_f(W)}" height="{_f(H)}" fill="{SEA}"/>'], locked=True))
    coast = " ".join(F.poly(p) for lnd in m.land for p in lnd.polygons)
    layers.append(_layer("coast", "coast", [
        f'<path id="coast" d="{coast}" fill="{LAND}" fill-rule="evenodd"/>']))
    water = [f'<path id="{e.id}" d="{F.poly(e.polygon)}" fill="{RIVER}" fill-rule="evenodd"/>'
             for e in [*m.rivers, *m.channels, *m.waterways]]
    layers.append(_layer("water", "water", water))
    layers.append(_layer("district", "district", [
        f'<path id="{d.id}" inkscape:label="{escape(d.name)}" d="{F.poly(d.polygon)}" '
        f'fill="{ARCHETYPE_COLORS.get(d.archetype, "#888888")}" fill-opacity="0.10" '
        f'stroke="{ARCHETYPE_COLORS.get(d.archetype, "#888888")}" stroke-width="3" '
        f'stroke-dasharray="12 8" fill-rule="evenodd"/>' for d in m.districts]))
    parks, plazas = [], []
    for o in m.open_spaces:
        el = (f'<path id="{o.id}" inkscape:label="{escape(o.name or o.kind)}" '
              f'd="{F.poly(o.polygon)}" fill="{MATERIALS.get("open_" + o.kind, "#3f7a4a")}" '
              f'fill-rule="evenodd"/>')
        (parks if o.kind in PARK_KINDS else plazas).append(el)
    layers.append(_layer("park", "park", parks))
    layers.append(_layer("plaza", "plaza", plazas))
    layers.append(_layer("pier", "pier", [
        f'<path id="{qy.id}" d="{F.line(qy.line)}" fill="none" stroke="#9a9384" '
        f'stroke-width="{_f(qy.width_m)}"/>' for qy in m.quays]))
    layers.append(_layer("megasite", "megasite", [
        f'<path id="{s.id}" inkscape:label="{escape(s.name)}" d="{F.poly(s.polygon)}" '
        f'fill="none" stroke="#e0c040" stroke-width="4" stroke-dasharray="20 10" '
        f'fill-rule="evenodd"/>' for s in m.megasites] + [
        f'<path id="{_svg_id(e.id)}" inkscape:label="{e.kind}" d="{F.poly(p)}" '
        f'fill="{c}" fill-rule="evenodd"/>' for e, p, c in _site_polys(m)]))
    roads: dict[str, list[str]] = {k: [] for k in ("alley", "pedestrian", "street", "avenue",
                                                   "highway", "elevated road")}
    for s in sorted(m.road_segments, key=lambda s: (s.road_class == "highway", s.id)):
        raised = s.bridge or any(z.z > 0.5 for z in s.z_profile)
        key = "elevated road" if raised else ROAD_LAYER[s.road_class]
        roads[key].append(
            f'<path id="{s.id}" inkscape:label="{escape(s.name or s.road_class)}" '
            f'd="{F.line(s.centerline)}" fill="none" stroke="{ROAD_COLORS[s.road_class]}" '
            f'stroke-width="{_f(s.width_m)}" stroke-linejoin="round"/>')
    for key, body in roads.items():
        layers.append(_layer(key.replace(" ", "_"), key, body))
    blds, lms = [], []
    for b in m.buildings:
        if b.footprint is None:
            continue
        color = "#eef0f4" if b.landmark else MATERIALS.get(
            "bld_" + (_arch(m, b.district_id) or ""), "#b0b6c0")
        el = (f'<path id="{_svg_id(b.id)}" inkscape:label="{_f(b.height_m)}" '
              f'd="{F.poly(b.footprint)}" fill="{color}" fill-rule="evenodd"/>')
        (lms if b.landmark else blds).append(el)
    layers.append(_layer("building", "building", blds))
    layers.append(_layer("landmark", "landmark", lms))
    layers.append(_layer("transit", "transit", [
        f'<path id="{t.id}" d="{F.line([(p[0], p[1]) for p in t.path])}" fill="none" '
        f'stroke="#2f7bff" stroke-width="6"/>' for t in m.transit_lines
        if getattr(t, "path", None)]))
    labels = []
    for d in m.districts:
        x, y = _label_at(d)
        labels.append(f'<text x="{F.p(x, y).split(",")[0]}" y="{F.p(x, y).split(",")[1]}" '
                      f'font-family="Inter, Helvetica, sans-serif" font-size="46" '
                      f'font-weight="700" fill="{INK}" text-anchor="middle" stroke="{BG}" '
                      f'stroke-width="6" paint-order="stroke">{escape(d.name)}</text>')
    for p in m.places:
        if p.label_at is None:
            continue
        x, y = p.label_at
        labels.append(f'<text x="{F.p(x, y).split(",")[0]}" y="{F.p(x, y).split(",")[1]}" '
                      f'font-family="Inter, Helvetica, sans-serif" font-size="26" '
                      f'fill="{INK}" text-anchor="middle" stroke="{BG}" stroke-width="5" '
                      f'paint-order="stroke">{escape(p.name)}</text>')
    layers.append(_layer("labels", "labels", labels))
    layers.append(_layer("legend", "legend", _legend_svg(m, W)))
    svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'xmlns:inkscape="{INK_NS}" '
           f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
           f'width="{_f(W)}" height="{_f(H)}" viewBox="0 0 {_f(W)} {_f(H)}">\n'
           f'<title>{escape(m.name)}: citygen map (1 unit = 1 m, origin at '
           f'{_f(-m.bounds[0])},{_f(m.bounds[3])})</title>\n'
           + "\n".join(layers) + "\n</svg>\n")
    path.write_text(svg, encoding="utf-8")
    return path


def _site_polys(m: CityModel) -> list:
    """(element, model polygon, color) of every megasite element with a footprint, flat
    ground first."""
    flat, raised = [], []
    for e in m.site_elements:
        c = MATERIALS.get("site_" + e.kind, MATERIALS["site_default"])
        if e.footprint is not None and not e.masses:
            flat.append((e, e.footprint, c))
        for ms in e.masses:
            raised.append((e, ms.footprint, c))
    return flat + raised


def _svg_id(eid: str) -> str:
    return eid.replace(".", "_")


def _arch(m: CityModel, did: str | None) -> str | None:
    for d in m.districts:
        if d.id == did:
            return d.archetype
    return None


def _label_at(d) -> tuple[float, float]:
    la = d.attrs.get("label_at") if d.attrs else None
    if la:
        return float(la[0]), float(la[1])
    with G.canonical():
        p = G.from_model_poly(d.polygon)
        pt = p.representative_point()
    return round(pt.x, 2), round(pt.y, 2)


def _legend_items(m: CityModel) -> list[tuple[str, str]]:
    archs = sorted({d.archetype for d in m.districts})
    items = [(ARCHETYPE_COLORS.get(a, "#888888"), a.replace("_", " ")) for a in archs]
    items += [("#eef0f4", "landmark"), (ROAD_COLORS["highway"], "highway"),
              (ROAD_COLORS["avenue"], "avenue"), (ROAD_COLORS["street"], "street"),
              (RIVER, "river, canal"), (MATERIALS["open_park"], "park"),
              (MATERIALS["open_plaza"], "plaza"), ("#e0c040", "megasite reserve")]
    return items


def _legend_svg(m: CityModel, W: float) -> list[str]:
    items = _legend_items(m)
    x, y = 30, 30
    out = [f'<rect x="{x - 15}" y="{y - 15}" width="380" height="{len(items) * 34 + 60}" '
           f'fill="{BG}" fill-opacity="0.85" rx="8"/>',
           f'<text x="{x}" y="{y + 22}" font-family="Inter, Helvetica, sans-serif" '
           f'font-size="26" font-weight="700" fill="{INK}">{escape(m.name)}</text>']
    for k, (color, label) in enumerate(items):
        yy = y + 50 + k * 34
        out.append(f'<rect x="{x}" y="{yy}" width="40" height="22" fill="{color}"/>')
        out.append(f'<text x="{x + 54}" y="{yy + 18}" font-family="Inter, Helvetica, '
                   f'sans-serif" font-size="20" fill="{MUTED}">{escape(label)}</text>')
    return out


def map_png(m: CityModel, path: Path, dpi: int = 150) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PatchCollection
    from matplotlib.patches import Patch, PathPatch
    from matplotlib.path import Path as MPath

    def patch(poly, **kw):
        verts, codes = [], []
        for ring in [poly.exterior, *poly.holes]:
            verts += [tuple(p) for p in ring] + [tuple(ring[0])]
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(ring) - 1) + [MPath.CLOSEPOLY]
        return PathPatch(MPath(verts, codes), **kw)

    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    fig = plt.figure(figsize=(14, 14 * H / W), facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(SEA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    for lnd in m.land:
        for p in lnd.polygons:
            ax.add_patch(patch(p, facecolor=LAND, edgecolor="none", zorder=1))
    for e in [*m.rivers, *m.channels, *m.waterways]:
        ax.add_patch(patch(e.polygon, facecolor=RIVER, edgecolor="none", zorder=2))
    for o in m.open_spaces:
        ax.add_patch(patch(o.polygon, facecolor=MATERIALS.get("open_" + o.kind, "#3f7a4a"),
                           edgecolor="none", zorder=3))
    order = {"highway": 4, "avenue": 3, "street": 2}
    for s in sorted(m.road_segments, key=lambda s: (order.get(s.road_class, 1), s.id)):
        lw = s.width_m * 72 / (W / 14)  # meters to points at this figure scale
        ax.add_collection(LineCollection([s.centerline], colors=ROAD_COLORS[s.road_class],
                                         linewidths=lw, capstyle="round", zorder=4 +
                                         order.get(s.road_class, 1) * 0.1))
    arch = {d.id: d.archetype for d in m.districts}
    bp = []
    for b in m.buildings:
        if b.footprint is None:
            continue
        color = "#eef0f4" if b.landmark else MATERIALS.get(
            "bld_" + arch.get(b.district_id, ""), "#b0b6c0")
        bp.append(patch(b.footprint, facecolor=color, edgecolor="none"))
    ax.add_collection(PatchCollection(bp, match_original=True, zorder=6))
    ax.add_collection(PatchCollection([patch(p, facecolor=c, edgecolor="none")
                                       for _, p, c in _site_polys(m)], match_original=True,
                                      zorder=5.5))
    for s in m.megasites:
        ax.add_patch(patch(s.polygon, facecolor="none", edgecolor="#e0c040", lw=1.2,
                           ls=(0, (6, 3)), zorder=7))
    halo = [pe.withStroke(linewidth=4, foreground=BG)]
    for d in m.districts:
        x, y = _label_at(d)
        ax.text(x, y, d.name, color=INK, fontsize=15, fontweight="bold", ha="center",
                va="center", zorder=9, path_effects=halo)
    for p in m.places:
        if p.label_at is not None:
            ax.text(p.label_at[0], p.label_at[1], p.name, color=INK, fontsize=9,
                    ha="center", va="center", zorder=9, path_effects=halo)
    handles = [Patch(facecolor=c, label=lab) for c, lab in _legend_items(m)]
    leg = ax.legend(handles=handles, loc="upper left", frameon=True, fontsize=10,
                    title=m.name, title_fontsize=13, labelcolor=MUTED)
    leg.get_frame().set_facecolor(BG)
    leg.get_frame().set_alpha(0.85)
    leg.get_title().set_color(INK)
    # scale bar, 500 m
    sx, sy = x1 - 0.06 * W - 500, y0 + 0.04 * H
    ax.plot([sx, sx + 500], [sy, sy], color=INK, lw=3, zorder=9)
    ax.text(sx + 250, sy + 0.012 * H, "500 m", color=INK, ha="center", fontsize=10, zorder=9)
    fig.savefig(path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return path


# --- legacy Unreal greybox plan -------------------------------------------------------------

def legacy_plan(m: CityModel, player_start=None) -> dict:
    """Primitives in the format of `corporate_core_plan.json` (boxes and cylinders, meters,
    yaw counterclockwise from east), read unchanged by `unreal/build_greybox_unreal.py`."""
    prims = []

    def add(kind, cat, c, s, yaw=0.0):
        prims.append({"kind": kind, "cat": cat, "center": [round(v, 3) for v in c],
                      "size": [round(v, 3) for v in s], "yaw": round(yaw, 2)})

    x0, y0, x1, y1 = m.bounds
    add("box", "water", ((x0 + x1) / 2, (y0 + y1) / 2, -3.0), (x1 - x0, y1 - y0, 1.0))
    strip = 8.0
    with G.canonical():
        land = G.union([G.from_model_poly(p) for lnd in m.land for p in lnd.polygons])
        y = math.floor(y0 / strip) * strip
        while y < y1:
            band = G.inter(land, G.box(x0, y, x1, y + strip))
            for part in G.parts(band):
                bx0, _, bx1, _ = part.bounds
                add("box", "ground", ((bx0 + bx1) / 2, y + strip / 2, -1.0),
                    (bx1 - bx0, strip, 2.0))
            y += strip
        for s in m.road_segments:
            raised = s.bridge or any(z.z > 0.5 for z in s.z_profile)
            cat = "bridge" if raised else {"highway": "highway", "avenue": "avenue"}.get(
                s.road_class, "street")
            zs = _zs(s)
            pts = s.centerline
            for i, ((ax_, ay), (bx, by)) in enumerate(zip(pts, pts[1:])):
                L = math.hypot(bx - ax_, by - ay)
                if L < 0.05:
                    continue
                th = 1.5 if raised else 0.1
                z = (zs[i] + zs[i + 1]) / 2 if zs else 0.0
                add("box", cat, ((ax_ + bx) / 2, (ay + by) / 2, z + 0.05 - th / 2),
                    (L, s.width_m, th), math.degrees(math.atan2(by - ay, bx - ax_)))
        for o in m.open_spaces:
            p = G.from_model_poly(o.polygon)
            _obb_box(add, p, "green" if o.kind in PARK_KINDS else "plaza", o.z_m, 0.2)
        for w in m.waterways:
            _obb_box(add, G.from_model_poly(w.polygon), "canal", -1.0, 0.5)
        for b in m.buildings:
            for ms in b.masses:
                if ms.z1_m <= ms.z0_m or ms.role == "void":
                    continue
                cat = ("landmark" if b.landmark else "podium" if ms.role == "podium" else
                       "tower" if ms.z1_m >= 60 else "lowrise")
                _obb_box(add, G.from_model_poly(ms.footprint), cat, ms.z0_m,
                         ms.z1_m - ms.z0_m, cyl=ms.shape == "cylinder")
    ps = list(player_start) if player_start else [0.0, 0.0, 1.2]
    return {"meta": {"name": m.name, "units": "meters", "axes": "x=east, y=north, z=up",
                     "source": "citygen city_model.json", "player_start": ps,
                     "player_start_facing": "north"},
            "primitives": prims}


def _zs(s) -> list[float]:
    from .blockout import _z_along

    return _z_along([(x, y) for x, y in s.centerline], s.z_profile) if s.z_profile else []


def _obb_box(add, poly, cat, z0, h, cyl=False):
    if poly.is_empty:
        return
    ang = MS.obb_angle(poly)
    ux, uy = math.cos(ang), math.sin(ang)
    pts = list(poly.exterior.coords)
    us = [x * ux + y * uy for x, y in pts]
    vs = [y * ux - x * uy for x, y in pts]
    cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    cx, cy = cu * ux - cv * uy, cu * uy + cv * ux
    add("cyl" if cyl else "box", cat, (cx, cy, z0 + h / 2),
        (max(us) - min(us), max(vs) - min(vs), h), math.degrees(ang))


# --- graphs, tiles, props -------------------------------------------------------------------

def graphs(m: CityModel) -> dict:
    return {
        "city": m.name, "frame": m.frame,
        "lanes": [{"id": x.id, "kind": x.kind, "segment_id": x.segment_id,
                   "node_id": x.node_id, "index": x.index, "forward": x.forward,
                   "width_m": x.width_m, "centerline": [list(p) for p in x.centerline],
                   "successors": x.successors, "adjacent_ids": x.adjacent_ids}
                  for x in m.lanes],
        "walkways": [{"id": w.id, "kind": w.kind, "width_m": w.width_m,
                      "line": [list(p) for p in w.line], "neighbors": w.neighbors}
                     for w in m.walkways],
        "transit_lines": [json.loads(t.model_dump_json()) for t in m.transit_lines],
        "stations": [json.loads(s.model_dump_json()) for s in m.stations],
    }


PROP_FIELDS = ["id", "type", "x", "y", "z", "yaw_deg", "sx", "sy", "sz", "tile", "height_m",
               "crown_radius_m", "species"]


def props_csv(m: CityModel) -> str:
    from .blockout import tile_key, tile_name

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(PROP_FIELDS)
    for p in m.props:
        x, y, z = p.position
        w.writerow([p.id, p.type, x, y, z, p.yaw_deg, *p.scale, tile_name(*tile_key(x, y)),
                    "", "", ""])
    for p in m.plants:
        x, y, z = p.position
        a = p.attrs or {}
        w.writerow([p.id, p.type, x, y, z, a.get("yaw_deg", 0.0), a.get("length_m", 1.0), 1.0,
                    1.0, tile_name(*tile_key(x, y)), p.height_m, p.crown_radius_m,
                    p.species or ""])
    return buf.getvalue()


GAMEPLAY = ("factions", "zones", "pois", "fields", "densities", "parking", "travel_points",
            "sign_slots")


def gameplay(m: CityModel) -> dict:
    """The gameplay layer as one document, with a per-tile index (the blockout's tile names)
    of the points of interest, parking, travel points and sign slots in each tile."""
    from .blockout import tile_key, tile_name
    from .model import HOUR_BANDS

    out: dict = {"city": m.name, "frame": m.frame,
                 "hour_bands": [{"name": n, "from": a, "to": b} for n, a, b in HOUR_BANDS]}
    for key in GAMEPLAY:
        out[key] = [json.loads(e.model_dump_json()) for e in getattr(m, key)]
    tiles: dict = {}

    def put(kind, eid, x, y):
        t = tiles.setdefault(tile_name(*tile_key(x, y)), {})
        t.setdefault(kind, []).append(eid)
    for p in m.pois:
        put("pois", p.id, *p.position[:2])
    for p in m.parking:
        x, y = (p.entrances[0].position if p.entrances else
                (p.line[len(p.line) // 2] if p.line else p.polygon.exterior[0]))
        put("parking", p.id, x, y)
    for t in m.travel_points:
        put("travel_points", t.id, *t.position)
    for s in m.sign_slots:
        put("sign_slots", s.id, *s.position[:2])
    out["tiles"] = dict(sorted(tiles.items()))
    return out
