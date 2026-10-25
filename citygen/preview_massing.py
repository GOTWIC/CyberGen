"""M3 previews: `preview_heights.png` (plan, footprints shaded by building height) and
`preview_massing.png` (isometric massing of the whole city plus four district close-ups).

The height map uses one blue ramp, dark for low buildings and light for tall ones (on the
dark map ground), on a square-root scale so that the low districts still separate. The
massing views extrude every mass (buildings, skybridges, megasite elements) and draw them
back to front from a camera in the south-south-west, 35 degrees up; walls are shaded by their
orientation and tinted by district archetype, roofs are lighter, landmarks are labeled.
Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import math
import zlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PathCollection, PolyCollection  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, to_rgb  # noqa: E402
from shapely.geometry import LineString, Polygon, box  # noqa: E402

from . import geom as G  # noqa: E402
from .preview import CANAL, OPEN_COLORS  # noqa: E402
from .schematic import ARCHETYPE_COLORS, BG, INK, LAND, MUTED, RIVER, SEA  # noqa: E402

RAMP = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5",
        "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4", "#b7d3f6", "#cde2fb"]
HEIGHT_CMAP = LinearSegmentedColormap.from_list("height", RAMP)
ROAD = "#3b404b"
ROAD_LIGHT = "#555b67"
SKYBRIDGE = "#ffd166"
HALO = [pe.withStroke(linewidth=2.5, foreground=BG)]
PHI = math.radians(20.0)     # camera azimuth: looking north, 20 degrees east
ELEV = math.radians(35.0)
LIGHT = (-0.75, -0.35)       # from the west-south-west
ELEMENT_COLORS = {"container_stack": "#c96f3b", "gantry_crane": "#e0c040",
                  "launch_pad": "#9aa3b0", "launch_tower": "#d8dce4", "fuel_tank": "#e8e8e8",
                  "platform": "#7fd4ff", "wall": "#b99a72", "gate": "#d0453a",
                  "fountain": "#7ec8e3", "metro_entrance": "#2f7bff"}
FLAT_COLORS = {"lawn": "#3f7a4a", "pond": "#2a74a8", "plaza": "#8c8572", "pitch": "#4f9a58",
               "apron": "#4a4f5a", "berth": "#5a5f6a", "courtyard": "#7a6f5a",
               "bus_bay": "#6a6f7a", "drop_off": "#4a4f5a", "truck_gate": "#5a5f6a",
               "rail_track": "#8a7a6a"}


def _sqrt_norm(h, hmax):
    return np.sqrt(np.clip(np.asarray(h, dtype=float), 0, hmax) / hmax)


def _paths(polys, xf):
    """Matplotlib paths of polygons with their holes (xf maps an (n, 2) array)."""
    out = []
    for poly in polys:
        verts, codes = [], []
        for ring in [poly.exterior, *poly.interiors]:
            c = xf(np.asarray(ring.coords)[:, :2])
            verts.append(c)
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(c) - 2) + [MPath.CLOSEPOLY]
        out.append(MPath(np.concatenate(verts), codes))
    return out


def _ground(ax, m, xf=lambda c: c, z: float = 1.0) -> None:
    P = G.from_model_poly
    land = [P(p) for x in m.land for p in x.polygons]
    ax.add_collection(PathCollection(_paths(land, xf), facecolors=LAND, edgecolors="none",
                                     zorder=z))
    water = [P(r.polygon) for r in m.rivers] + [P(c.polygon) for c in m.channels] + \
        [P(w.polygon) for w in m.waterways]
    ax.add_collection(PathCollection(_paths(water, xf), facecolors=RIVER, edgecolors="none",
                                     zorder=z + 0.2))


def render_heights(b, out, dpi: int = 150) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    fig_w = 12.0
    head = 1.1
    fig = plt.figure(figsize=(fig_w, fig_w * H / W + head), facecolor=BG, dpi=dpi)
    ax = fig.add_axes([0.0, 0.0, 1.0, (fig_w * H / W) / (fig_w * H / W + head)])
    ax.set_facecolor(SEA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    _ground(ax, m)
    P = G.from_model_poly
    roads = []
    for s in m.road_segments:
        if s.road_class in ("highway", "avenue", "street"):
            roads.append(np.asarray(s.centerline))
    ax.add_collection(LineCollection(roads, colors=ROAD_LIGHT, linewidths=0.35, zorder=2))
    opens = [np.asarray(P(o.polygon).exterior.coords) for o in m.open_spaces if o.district_id]
    ax.add_collection(PolyCollection(opens, facecolors="#24402c", edgecolors="none",
                                     zorder=1.5))
    hmax = max([x.height_m for x in m.buildings] + [1.0])
    polys, hs = [], []
    order = sorted(m.buildings, key=lambda x: x.height_m)
    for x in order:
        for mass in x.masses:
            if mass.z0_m > 0.0 and mass.role not in ("span",):
                continue
            polys.append(np.asarray(P(mass.footprint).exterior.coords))
            hs.append(x.height_m)
    for e in m.site_elements:
        for mass in e.masses:
            polys.append(np.asarray(P(mass.footprint).exterior.coords))
            hs.append(mass.z1_m)
    cols = HEIGHT_CMAP(_sqrt_norm(hs, hmax))
    ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors=BG, linewidths=0.08,
                                     zorder=3))
    sb = [np.asarray(s.line) for s in m.skybridges]
    ax.add_collection(LineCollection(sb, colors=SKYBRIDGE, linewidths=0.6, zorder=4))
    for d in m.districts:
        p = P(d.polygon)
        ax.plot(*p.exterior.xy, color=MUTED, lw=0.5, alpha=0.6, zorder=4)
        c = p.representative_point()
        ax.text(c.x, c.y, d.name.upper(), color=INK, fontsize=7.5, fontweight="bold",
                ha="center", va="center", zorder=6, path_effects=HALO)
    for x in m.buildings:
        if x.landmark and x.name:
            c = P(x.footprint).centroid if x.footprint else None
            if c is not None:
                ax.text(c.x, c.y, f"  {x.name} {x.height_m:.0f} m", color=INK, fontsize=6.5,
                        zorder=7, path_effects=HALO, va="center")
    # color scale
    fh_in = fig_w * H / W + head
    cax = fig.add_axes([0.06, 1.0 - 0.78 / fh_in, 0.4, 0.1 / fh_in])
    ticks = [t for t in (10, 30, 60, 120, 250, 480) if t <= hmax] + [round(hmax)]
    grad = np.linspace(0, 1, 256)[None, :]
    cax.imshow(grad, aspect="auto", cmap=HEIGHT_CMAP, extent=(0, 1, 0, 1))
    cax.set_yticks([])
    cax.set_xticks([math.sqrt(t / hmax) for t in ticks])
    cax.set_xticklabels([f"{t:g}" for t in ticks], color=MUTED, fontsize=7)
    cax.tick_params(colors=MUTED, length=2)
    for s in cax.spines.values():
        s.set_visible(False)
    st = b.stats.get("buildings", {})
    fig.text(0.06, 1.0 - 0.12 / fh_in,
             f"{b.spec.name}: building heights (M3)", color=INK, fontsize=13,
             fontweight="bold", va="top")
    fig.text(0.06, 1.0 - 0.42 / fh_in,
             f"{st.get('count', len(m.buildings))} buildings, {len(m.skybridges)} skybridges "
             f"(gold), height scale in m (square root); tallest {hmax:.0f} m",
             color=MUTED, fontsize=8.5, va="top")
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Isometric massing
# ---------------------------------------------------------------------------

_C, _S = math.cos(PHI), math.sin(PHI)
_SE, _CE = math.sin(ELEV), math.cos(ELEV)
_VIEW = (math.sin(PHI), math.cos(PHI))   # ground direction the camera looks along


def _proj(x, y, z):
    sx = x * _C - y * _S
    depth = x * _S + y * _C
    return sx, depth * _SE + z * _CE


def _proj_ring(coords, z):
    c = np.asarray(coords, dtype=float)
    sx = c[:, 0] * _C - c[:, 1] * _S
    sy = (c[:, 0] * _S + c[:, 1] * _C) * _SE + z * _CE
    return np.column_stack([sx, sy])


def _shade(rgb, k):
    return tuple(min(1.0, max(0.0, v * k)) for v in rgb)


def _no_holes(poly):
    """Pieces of a polygon without holes (cut through each hole)."""
    if not poly.interiors:
        return [poly]
    h = Polygon(poly.interiors[0])
    c = h.centroid
    x0, y0, x1, y1 = poly.bounds
    left = box(x0 - 1, y0 - 1, c.x, y1 + 1)
    right = box(c.x, y0 - 1, x1 + 1, y1 + 1)
    out = []
    for half in (left, right):
        g = poly.intersection(half)
        for p in getattr(g, "geoms", [g]):
            if p.geom_type == "Polygon" and not p.is_empty:
                out += _no_holes(p)
    return out


def _prism_faces(poly, z0, z1, rgb, faces):
    """Visible walls and the roof of an extruded polygon, appended as (poly, color)."""
    p = shapely.geometry.polygon.orient(poly, 1.0)
    rings = [p.exterior] + list(p.interiors)
    for r in rings:
        c = np.asarray(r.coords)
        for i in range(len(c) - 1):
            ax_, ay_ = c[i]
            bx_, by_ = c[i + 1]
            dx, dy = bx_ - ax_, by_ - ay_
            L = math.hypot(dx, dy)
            if L < 0.05:
                continue
            nx, ny = dy / L, -dx / L
            if nx * -_VIEW[0] + ny * -_VIEW[1] <= 0:
                continue
            lam = 0.62 + 0.3 * max(0.0, -(nx * LIGHT[0] + ny * LIGHT[1]))
            q = [_proj(ax_, ay_, z0), _proj(bx_, by_, z0), _proj(bx_, by_, z1),
                 _proj(ax_, ay_, z1)]
            faces.append((q, _shade(rgb, lam)))
    for piece in _no_holes(p):
        faces.append((_proj_ring(piece.exterior.coords, z1), _shade(rgb, 1.08)))


def _is_ring(poly, h) -> bool:
    """A thin plan as long as the mass is tall: a vertical wheel (shape ring)."""
    r = poly.minimum_rotated_rectangle
    c = list(r.exterior.coords)
    a = math.dist(c[0], c[1])
    b = math.dist(c[1], c[2])
    return min(a, b) < 6.0 and abs(max(a, b) - h) < 2.0


def _ring_faces(poly, z0, z1, rgb, faces):
    """A vertical wheel: rim, spokes and hub as thin quads in its plane."""
    r = poly.minimum_rotated_rectangle
    c = list(r.exterior.coords)
    if math.dist(c[0], c[1]) < math.dist(c[1], c[2]):
        c = c[1:] + c[1:2]
    (x0, y0), (x1, y1) = c[0], c[1]
    L = math.dist(c[0], c[1])
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    cx, cy = poly.centroid.x, poly.centroid.y
    R = (z1 - z0) / 2.0
    zc = z0 + R
    n = 36
    pts = [(cx + ux * R * math.cos(2 * math.pi * k / n), cy + uy * R * math.cos(2 * math.pi * k / n),
            zc + R * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
    col = _shade(rgb, 1.05)
    for a, b in zip(pts, pts[1:]):
        q = [_proj(*a), _proj(*b), _proj(b[0], b[1], b[2] - 3.0), _proj(a[0], a[1], a[2] - 3.0)]
        faces.append((q, col))
    for k in range(0, n, 3):
        a = pts[k]
        q = [_proj(cx, cy, zc), _proj(*a), _proj(a[0], a[1], a[2] + 1.0), _proj(cx, cy, zc + 1.0)]
        faces.append((q, _shade(rgb, 0.8)))


def _solids(m, window=None):
    """(depth key, z0, polygon, z0, z1, rgb) of every mass to draw."""
    P = G.from_model_poly
    arch = {d.id: d.archetype for d in m.districts}
    out = []

    def add(poly, z0, z1, rgb):
        if window is not None and not poly.intersects(window):
            return
        c = poly.centroid
        out.append((c.x * _S + c.y * _C, z0, poly, z0, z1, rgb))

    for x in m.buildings:
        base = ARCHETYPE_COLORS.get(arch.get(x.district_id), "#888888")
        rgb = to_rgb(base)
        rgb = tuple(0.35 + 0.55 * v for v in rgb)
        # a slight shade per building, so that neighbors read as separate masses
        k = 0.9 + 0.2 * (zlib.crc32(x.id.encode()) % 1000) / 999.0
        rgb = _shade(rgb, k)
        if x.landmark:
            rgb = (0.93, 0.93, 0.97)
        for mass in x.masses:
            add(P(mass.footprint), mass.z0_m, mass.z1_m, rgb)
        for it in x.roof_items:
            px, py, pz = it.position
            su, sv, sz = it.size
            if su * sv < 1.0 and window is None:
                continue
            a = math.radians(it.yaw_deg)
            ca, sa = math.cos(a), math.sin(a)
            pts = [(px + u * ca - v * sa, py + u * sa + v * ca)
                   for u, v in ((-su / 2, -sv / 2), (su / 2, -sv / 2), (su / 2, sv / 2),
                                (-su / 2, sv / 2))]
            col = (0.95, 0.75, 0.2) if it.kind in ("helipad", "av_pad") else \
                (1.0, 0.3, 0.75) if it.kind == "billboard" else (0.6, 0.62, 0.66)
            add(Polygon(pts), pz, pz + max(sz, 0.3), col)
    for e in m.site_elements:
        rgb = to_rgb(ELEMENT_COLORS.get(e.kind, "#b0b6c0"))
        for mass in e.masses:
            add(P(mass.footprint), mass.z0_m, mass.z1_m, rgb)
    for s in m.skybridges:
        (ax_, ay_), (bx_, by_) = s.line
        L = math.hypot(bx_ - ax_, by_ - ay_)
        if L <= 0:
            continue
        nx, ny = -(by_ - ay_) / L * s.width_m / 2, (bx_ - ax_) / L * s.width_m / 2
        poly = Polygon([(ax_ + nx, ay_ + ny), (bx_ + nx, by_ + ny), (bx_ - nx, by_ - ny),
                        (ax_ - nx, ay_ - ny)])
        add(poly, s.z_m - 1.0, s.z_m + s.levels * s.level_height_m, to_rgb(SKYBRIDGE))
    out.sort(key=lambda t: (-t[0], t[1]))
    return out


def _draw_massing(ax, m, window=None, lw=0.0):
    P = G.from_model_poly
    _ground(ax, m, xf=lambda c: _proj_ring(c, 0.0), z=0.8)
    ground = []
    for o in m.open_spaces:
        if o.district_id:
            ground.append((_proj_ring(P(o.polygon).exterior.coords, 0.0),
                           OPEN_COLORS.get(o.kind, "#3f7a4a")))
    for e in m.site_elements:
        if e.footprint is not None and not e.masses and e.kind in FLAT_COLORS:
            ground.append((_proj_ring(P(e.footprint).exterior.coords, 0.0),
                           FLAT_COLORS[e.kind]))
    ax.add_collection(PolyCollection([g[0] for g in ground], facecolors=[g[1] for g in ground],
                                     edgecolors="none", zorder=1))
    rl = []
    for s in m.road_segments:
        if window is not None and not LineString(s.centerline).intersects(window):
            continue
        rl.append((_proj_ring(s.centerline, 0.0), s.width_m))
    if rl:
        ax.add_collection(LineCollection([r[0] for r in rl], colors=ROAD,
                                         linewidths=[max(0.2, r[1] * lw) for r in rl]
                                         if lw else 0.4, zorder=1.5, capstyle="butt"))
    faces = []
    for _, _, poly, z0, z1, rgb in _solids(m, window):
        if z1 - z0 > 20.0 and _is_ring(poly, z1 - z0):
            _ring_faces(poly, z0, z1, rgb, faces)
            continue
        _prism_faces(poly, z0, z1, rgb, faces)
    ax.add_collection(PolyCollection([f[0] for f in faces], facecolors=[f[1] for f in faces],
                                     edgecolors=(0, 0, 0, 0.3), linewidths=0.08 if not lw
                                     else 0.15, zorder=2))


def _bounds_proj(x0, y0, x1, y1, zmax=0.0):
    pts = [_proj(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (0.0, zmax)]
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def render_massing(b, out, dpi: int = 150) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    hmax = max([x.height_m for x in m.buildings] + [10.0])
    bx0, by0, bx1, by1 = _bounds_proj(x0, y0, x1, y1, hmax)
    picks = _close_ups(m)
    fig_w = 16.0
    main_h = fig_w * (by1 - by0) / (bx1 - bx0)
    row_h = fig_w / 4.0 * 0.95
    fig_h = main_h + row_h + 1.0
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG, dpi=dpi)
    ax = fig.add_axes([0.0, (row_h + 0.2) / fig_h, 1.0, main_h / fig_h])
    ax.set_facecolor(SEA)
    ax.set_xlim(bx0, bx1)
    ax.set_ylim(by0, by1)
    ax.set_aspect("equal")
    ax.axis("off")
    _draw_massing(ax, m)
    for x in m.buildings:
        if x.landmark and x.name and x.footprint is not None:
            c = G.from_model_poly(x.footprint).centroid
            sx, sy = _proj(c.x, c.y, x.height_m)
            ax.text(sx, sy + 8, x.name, color=INK, fontsize=7, ha="center", va="bottom",
                    zorder=5, path_effects=HALO)
    st = b.stats.get("buildings", {})
    fig.text(0.012, 1 - 0.12 / fig_h, f"{b.spec.name}: massing (M3), isometric from the "
             f"south-south-west", color=INK, fontsize=14, fontweight="bold", va="top")
    fig.text(0.012, 1 - 0.42 / fig_h,
             f"{st.get('count', len(m.buildings))} buildings, "
             f"{st.get('floor_area_km2', 0):.2f} km2 floor area, {len(m.skybridges)} skybridges"
             f" (gold), {len(m.megasites)} megasites; walls tinted by district archetype, "
             "landmarks white", color=MUTED, fontsize=9, va="top")
    for k, (did, name, arch, win) in enumerate(picks):
        cax = fig.add_axes([k / 4.0 + 0.004, 0.1 / fig_h, 0.25 - 0.008, row_h / fig_h])
        cax.set_facecolor(SEA)
        wx0, wy0, wx1, wy1 = win.bounds
        hm = max([x.height_m for x in m.buildings if x.district_id == did] + [10.0])
        px0, py0, px1, py1 = _bounds_proj(wx0, wy0, wx1, wy1, 0.0)
        top = _proj(0, 0, min(hm, 300.0))[1] - _proj(0, 0, 0)[1]
        cax.set_xlim(px0, px1)
        cax.set_ylim(py0, max(py1 + top * 0.6, py0 + (px1 - px0) * 0.95))
        cax.set_aspect("equal")
        cax.axis("off")
        _draw_massing(cax, m, window=win)
        cax.text(0.02, 0.98, f"{name} ({arch.replace('_', ' ')})", transform=cax.transAxes,
                 color=INK, fontsize=8.5, fontweight="bold", va="top", path_effects=HALO)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)


CLOSE_ORDER = ("corporate_core", "old_town", "industrial_port", "megablock_residential",
               "entertainment_market", "spaceport", "transit_hub", "residential_heights",
               "midtown_mixed", "research_campus")


def _close_ups(m, n: int = 4, half: float = 260.0):
    """(district id, name, archetype, window) for up to n districts of different archetypes,
    each window around the middle of the district's buildings."""
    by_arch: dict = {}
    for d in m.districts:
        by_arch.setdefault(d.archetype, []).append(d)
    out = []
    for arch in CLOSE_ORDER:
        for d in by_arch.get(arch, [])[:1]:
            bs = [x for x in m.buildings if x.district_id == d.id and x.footprint is not None]
            if not bs:
                continue
            cs = [G.from_model_poly(x.footprint).centroid for x in bs]
            mx = sum(c.x for c in cs) / len(cs)
            my = sum(c.y for c in cs) / len(cs)
            # the building nearest the middle of the district's buildings, else the tallest
            # one when the district is a ring (its middle empty)
            k = min(range(len(bs)), key=lambda i: ((cs[i].x - mx) ** 2 + (cs[i].y - my) ** 2,
                                                   bs[i].id))
            c = cs[k]
            out.append((d.id, d.name, arch, box(c.x - half, c.y - half, c.x + half,
                                                c.y + half)))
        if len(out) >= n:
            break
    return out
