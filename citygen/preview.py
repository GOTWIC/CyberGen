"""Preview map of a built city (`preview_map.png`): water, landmasses, districts, waterways,
megasite reserves, highways, avenues, bridges and exits.

Sea with a shallow-water band along the shore, rivers and channels, thin district borders,
open land (marsh, park), and labels placed so that none overlap (each label tries a few spots
inside its feature, shrinks, and is dropped only when nothing fits). An inset bar shows the
share of the district-to-district boundary that runs along water.
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import PathPatch, Patch, Rectangle  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from shapely.geometry import Point  # noqa: E402
from shapely.ops import polylabel, unary_union  # noqa: E402

from . import geom as G  # noqa: E402
from .schematic import ARCHETYPE_COLORS, BG, INK, LAND, MUTED, RIVER, SEA  # noqa: E402

CANAL = "#3f8fc4"
QUAY = "#d8dde6"
SEPARATION = "#2a74a8"
SHALLOW = "#10294a"
SHALLOW_2 = "#0c2039"
MARSH = "#4d6b4a"
PARK = "#3f7a4a"
HALO = [pe.withStroke(linewidth=3, foreground=BG)]
HIGHWAY = "#f2c14e"
AVENUE = "#dfe3ea"
CASING = "#11141b"
BRIDGE = {"sea": "#ff6b8a", "river": "#ff9f43", "canal": "#7ee0c3"}
RESERVE = "#e8e8e8"


def _patch(poly, **kw) -> PathPatch:
    verts, codes = [], []
    for ring in [poly.exterior, *poly.interiors]:
        xs = list(ring.coords)
        verts += xs
        codes += [MPath.MOVETO] + [MPath.LINETO] * (len(xs) - 2) + [MPath.CLOSEPOLY]
    return PathPatch(MPath(verts, codes), **kw)


def _fill(ax, geom, **kw) -> None:
    for p in G.parts(geom):
        ax.add_patch(_patch(p, **kw))


def _scale_bar(ax, bounds) -> None:
    minx, miny, maxx, maxy = bounds
    span = maxx - minx
    length = 1000.0 if span > 2500 else 500.0
    x0, y0 = minx + 0.04 * span, miny + 0.04 * (maxy - miny)
    ax.plot([x0, x0 + length], [y0, y0], color=INK, lw=3, solid_capstyle="butt", zorder=20)
    for x in (x0, x0 + length / 2, x0 + length):
        ax.plot([x, x], [y0 - 25, y0 + 25], color=INK, lw=1.5, zorder=20)
    ax.text(x0 + length / 2, y0 + 50, f"{length / 1000:g} km", color=INK, ha="center",
            va="bottom", fontsize=8, path_effects=HALO, zorder=20)


class _Labels:
    """Greedy label placement without overlaps (in display coordinates)."""

    def __init__(self, fig, ax):
        self.fig, self.ax = fig, ax
        self.renderer = fig.canvas.get_renderer()
        self.boxes = []

    def reserve(self, artist) -> None:
        self.boxes.append(artist.get_window_extent(self.renderer).expanded(1.02, 1.05))

    def place(self, spots, text: str, sizes, **kw):
        """Try each spot (x, y) at each font size; keep the first that overlaps nothing."""
        ax_box = self.ax.get_window_extent(self.renderer)
        for size in sizes:
            for x, y in spots:
                t = self.ax.text(x, y, text, fontsize=size, **kw)
                bb = t.get_window_extent(self.renderer).expanded(1.06, 1.12)
                inside = (bb.x0 >= ax_box.x0 and bb.x1 <= ax_box.x1 and bb.y0 >= ax_box.y0
                          and bb.y1 <= ax_box.y1)
                if inside and not any(bb.overlaps(o) for o in self.boxes):
                    self.boxes.append(bb)
                    return t
                t.remove()
        return None


def _spots(poly, n: int = 9) -> list[tuple[float, float]]:
    """Candidate label points inside a polygon: the pole of inaccessibility first, then
    points around it (still inside)."""
    try:
        c = polylabel(poly, tolerance=10.0)
    except Exception:  # noqa: BLE001 (degenerate polygon)
        c = poly.representative_point()
    out = [(c.x, c.y)]
    r = max(math.sqrt(poly.area) * 0.18, 40.0)
    for k in range(n - 1):
        ang = 2 * math.pi * k / (n - 1) + math.pi / 2
        for f in (1.0, 0.5):
            q = Point(c.x + math.cos(ang) * r * f, c.y + math.sin(ang) * r * f)
            if poly.contains(q):
                out.append((q.x, q.y))
                break
    return out


def _line_spots(cl, avoid) -> list[tuple[float, float, float]]:
    """(x, y, angle) spots along a centerline, away from `avoid`."""
    out = []
    n = len(cl)
    for frac in (0.33, 0.2, 0.5, 0.66, 0.1, 0.8, 0.42, 0.58):
        j = min(int(frac * n), n - 2)
        p = Point(cl[j])
        if avoid is not None and avoid.contains(p):
            continue
        (x0, y0), (x1, y1) = cl[max(j - 2, 0)], cl[min(j + 2, n - 1)]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
        out.append((p.x, p.y, ang))
    return out


def render(b, out, dpi: int = 110) -> None:
    m, spec, st = b.model, b.spec, b.stats
    minx, miny, maxx, maxy = m.bounds
    w, h = maxx - minx, maxy - miny
    fig_w, ax_w = 12.0, 8.4
    ax_h = ax_w * h / w
    fig_h = max(ax_h + 1.1, 7.5)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG, dpi=dpi)
    ax = fig.add_axes([0.02, 0.3 / fig_h, ax_w / fig_w, ax_h / fig_h])
    top = 1 - 0.25 / fig_h
    ax.set_facecolor(SEA)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    P = G.from_model_poly
    land = unary_union([P(p) for x in m.land for p in x.polygons])
    sea = unary_union([P(p) for s in m.seas for p in s.polygons])
    # Shallow water: two bands along the shore, lighter near the land.
    if not sea.is_empty:
        _fill(ax, sea.intersection(land.buffer(110)), facecolor=SHALLOW_2, edgecolor="none",
              zorder=0.5)
        _fill(ax, sea.intersection(land.buffer(40)), facecolor=SHALLOW, edgecolor="none",
              zorder=0.6)
    _fill(ax, land, facecolor=LAND, edgecolor="none", zorder=1)
    arche = {}
    for d in m.districts:
        poly = P(d.polygon)
        col = ARCHETYPE_COLORS.get(d.archetype, "#888888")
        arche[d.archetype] = col
        ax.add_patch(_patch(poly, facecolor=col, alpha=0.55, edgecolor="none", zorder=2))
        ax.add_patch(_patch(poly, facecolor="none", edgecolor=col, lw=0.5, alpha=0.9,
                            zorder=2.1))
    for o in m.open_spaces:
        poly = P(o.polygon)
        col = MARSH if o.kind == "marsh" else PARK
        ax.add_patch(_patch(poly, facecolor=col, alpha=0.55, edgecolor="none", zorder=2))
        ax.add_patch(_patch(poly, facecolor="none", edgecolor="#9fbf8f", hatch="...", lw=0,
                            alpha=0.5, zorder=2.1))
    for r in m.rivers:
        ax.add_patch(_patch(P(r.polygon), facecolor=RIVER, edgecolor="none", zorder=3))
    for c in m.channels:
        col = SEPARATION if c.kind == "separation" else RIVER
        ax.add_patch(_patch(P(c.polygon), facecolor=col, edgecolor="none", zorder=3))
    for wv in m.waterways:
        ax.add_patch(_patch(P(wv.polygon), facecolor=CANAL, edgecolor="none", zorder=4))
    for q in m.quays:
        xs, ys = zip(*q.line)
        ax.plot(xs, ys, color=QUAY, lw=0.4, alpha=0.7, zorder=5)
    _draw_roads(ax, m)
    for isl in m.islands:
        ax.add_patch(_patch(P(isl.polygon), facecolor="none", edgecolor=INK, lw=0.6,
                            alpha=0.7, linestyle=(0, (4, 3)), zorder=6))
    open_lm = {o.attrs.get("landmass_id") for o in m.open_spaces}
    for lm in m.landmasses:
        ax.add_patch(_patch(P(lm.polygon), facecolor="none", edgecolor="#000000", lw=0.5,
                            alpha=0.5, zorder=6))
        if not lm.district_ids and lm.id not in open_lm:
            ax.add_patch(_patch(P(lm.polygon), facecolor="none", edgecolor=MUTED, hatch="///",
                                lw=0, zorder=6))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(MUTED)
    _scale_bar(ax, m.bounds)
    north = ax.text(maxx - 0.03 * w, miny + 0.04 * h, "N\n^", color=INK, ha="center",
                    fontsize=9, path_effects=HALO, zorder=20)
    fig.canvas.draw()
    lab = _Labels(fig, ax)
    lab.reserve(north)
    for t in ax.texts:
        if t is not north:
            lab.reserve(t)
    # Labels, most important first: districts (big first), islands, open land, water.
    for d in sorted(m.districts, key=lambda d: -P(d.polygon).area):
        poly = P(d.polygon)
        big = poly.area > 4e5
        lab.place(_spots(poly), d.name, (9, 8, 7, 6) if big else (8, 7, 6), color=INK,
                  ha="center", va="center", fontweight="bold", path_effects=HALO, zorder=10)
    named = {d.name for d in m.districts}
    for isl in m.islands:
        if isl.name in named:
            continue
        lab.place(_spots(P(isl.polygon)), isl.name, (7, 6), color=MUTED, ha="center",
                  va="center", style="italic", path_effects=HALO, zorder=9)
    for o in m.open_spaces:
        lab.place(_spots(P(o.polygon)), o.name or o.kind, (7, 6, 5), color="#b9d4a8",
                  ha="center", va="center", style="italic", path_effects=HALO, zorder=9)
    _road_labels(lab, m)
    isl_zone = unary_union([P(i.polygon).buffer(150) for i in m.islands]) if m.islands else None
    labeled = set()
    waters = list(m.rivers) + [c for c in m.channels if c.kind != "separation" and c.name]
    for r in waters:
        if r.name in labeled or len(r.centerline) < 4:
            continue
        labeled.add(r.name)
        for x, y, ang in _line_spots(r.centerline, isl_zone):
            if lab.place([(x, y)], r.name, (7, 6), color="#9fd4ff", rotation=ang,
                         rotation_mode="anchor", ha="center", va="center", style="italic",
                         path_effects=HALO, zorder=9) is not None:
                break
    if m.seas and m.seas[0].name:
        big = max((P(p) for p in m.seas[0].polygons), key=lambda g: g.area)
        lab.place(_spots(big.buffer(-150) if not big.buffer(-150).is_empty else big, 13),
                  m.seas[0].name, (10, 9, 8), color="#7fa6c9", style="italic", ha="center",
                  va="center", path_effects=HALO, zorder=9)
    status = "checks PASS" if b.passed else "checks FAIL"
    fig.text(0.02, top, f"{spec.name}: water, districts and primary roads (M1b)",
             color=INK, fontsize=14, fontweight="bold", va="top")
    rk = st.get("road_km", {})
    bc = st.get("bridges_by_class", {})
    fig.text(0.02, top - 0.3 / fig_h, f"seed {spec.seed}, {w / 1000:g} x {h / 1000:g} km, "
             f"land {st['land_km2']} km2, water {st['water_share']:.0%}, "
             f"{st['landmasses']} landmasses, highways {rk.get('highway', 0)} km, avenues "
             f"{rk.get('avenue', 0)} km, bridges {sum(bc.values())}, {status}",
             color=MUTED, fontsize=9, va="top")
    handles = [Patch(facecolor=col, alpha=0.55, edgecolor=col, label=a.replace("_", " "))
               for a, col in sorted(arche.items())]
    handles += [Patch(facecolor=SEA, label="sea"), Patch(facecolor=SHALLOW, label="shallows"),
                Patch(facecolor=RIVER, label="river / branch"),
                Patch(facecolor=SEPARATION, label="separation channel"),
                Patch(facecolor=CANAL, label="inner waterway"),
                Line2D([], [], color=QUAY, lw=1, label="quay"),
                Patch(facecolor=MARSH, alpha=0.55, label="marsh / park (open land)"),
                Line2D([], [], color=HIGHWAY, lw=2.4, label="highway"),
                Line2D([], [], color=AVENUE, lw=1.2, label="avenue"),
                Line2D([], [], color=BRIDGE["sea"], lw=3.2, label="bridge, sea class (25 m)"),
                Line2D([], [], color=BRIDGE["river"], lw=3.2,
                       label="bridge, river class (10 to 15 m)"),
                Line2D([], [], color=BRIDGE["canal"], lw=3.2,
                       label="bridge, canal class (3 to 4 m)"),
                Patch(facecolor="none", edgecolor=RESERVE, hatch="xx", label="megasite reserve"),
                Line2D([], [], color=INK, lw=0.8, linestyle=(0, (4, 3)), label="island"),
                Line2D([], [], color="#000000", lw=0.8, label="landmass edge"),
                Patch(facecolor=LAND, edgecolor=MUTED, hatch="///", label="no district")]
    x_side = 0.03 + ax_w / fig_w
    leg = fig.legend(handles=handles, loc="upper left",
                     bbox_to_anchor=(x_side, (0.3 + ax_h) / fig_h),
                     frameon=False, fontsize=8, labelcolor=INK, title="legend",
                     title_fontsize=9)
    leg.get_title().set_color(INK)
    rows = [f"{r['name'][:22]:<22} {r['share']:.3f} / {r['target']:.3f}"
            for r in st["districts"]]
    y_tab = (0.3 + ax_h - 6.3) / fig_h
    fig.text(x_side + 0.005, y_tab, "district share / target\n" + "\n".join(rows), color=INK,
             fontsize=7, family="monospace", va="top")
    _water_inset(fig, st, x_side + 0.005, y_tab - (len(rows) + 3) * 0.155 / fig_h, fig_h)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)


def _water_inset(fig, st, x: float, y: float, fig_h: float) -> None:
    """Small bar: share of the district-to-district boundary on water (and the target)."""
    share = st.get("boundary_on_water")
    if share is None:
        return
    target = st.get("boundary_on_water_target")
    h = 0.16 / fig_h
    ax = fig.add_axes([x, y - h, 0.2, h])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, facecolor="#4a3b2a", edgecolor="none"))
    ax.add_patch(Rectangle((0, 0), share, 1, facecolor=SEPARATION, edgecolor="none"))
    if target is not None:
        ax.plot([target, target], [-0.25, 1.25], color=INK, lw=1, clip_on=False)
    km = st.get("boundary_km", {})
    txt = f"boundary between districts: {share:.0%} on water"
    if target is not None:
        txt += f" (target {target:.0%})"
    fig.text(x, y + 0.03 / fig_h, txt, color=INK, fontsize=7, va="bottom")
    fig.text(x, y - h - 0.05 / fig_h, f"water {km.get('water', 0)} km, land "
             f"{km.get('land', 0)} km", color=MUTED, fontsize=7, va="top")


def _draw_roads(ax, m) -> None:
    P = G.from_model_poly
    for site in m.megasites:
        if site.flight_cone is not None:
            ax.add_patch(_patch(P(site.flight_cone), facecolor="none", edgecolor=RESERVE,
                                lw=0.5, alpha=0.5, linestyle=(0, (2, 2)), zorder=6.2))
        ax.add_patch(_patch(P(site.polygon), facecolor="none", edgecolor=RESERVE, hatch="xx",
                            lw=0.6, alpha=0.55, zorder=6.2))
    order = sorted(m.road_segments, key=lambda s: (s.road_class == "highway", s.id))
    for s in order:
        hw = s.road_class == "highway"
        xs, ys = zip(*s.centerline)
        lw = 2.4 if hw else (1.5 if s.attrs.get("role") == "axis_boulevard" else 1.1)
        ax.plot(xs, ys, color=CASING, lw=lw + 1.2, solid_capstyle="round", zorder=7 + hw)
        ax.plot(xs, ys, color=HIGHWAY if hw else AVENUE, lw=lw, solid_capstyle="round",
                zorder=7.1 + hw)
    for b in m.bridges:
        xs, ys = [p[0] for p in b.line], [p[1] for p in b.line]
        col = BRIDGE.get(b.water_class or "sea", BRIDGE["sea"])
        lw = 3.8 if b.water_class == "sea" else 3.2
        if b.bridge_class == "pedestrian":
            ax.plot(xs, ys, color=col, lw=1.2, linestyle=(0, (2, 1)), zorder=9.2)
            continue
        ax.plot(xs, ys, color=CASING, lw=lw + 1.4, solid_capstyle="butt", zorder=9)
        ax.plot(xs, ys, color=col, lw=lw, solid_capstyle="butt", zorder=9.1)
    for n in m.road_nodes:
        if n.attrs.get("kind") == "exit":
            ax.plot([n.position[0]], [n.position[1]], marker="o", ms=7, color=HIGHWAY,
                    mec=CASING, mew=1.2, zorder=11)


def _road_labels(lab, m) -> None:
    """Exit and named-bridge labels (most important first), then highway names."""
    minx, miny, maxx, maxy = m.bounds
    for n in m.road_nodes:
        ex = n.attrs.get("exit")
        if not ex:
            continue
        x, y = n.position[0], n.position[1]
        dx = 0.0 if abs(x - minx) > 1 and abs(x - maxx) > 1 else (1 if abs(x - minx) <= 1 else -1)
        dy = 0.0 if abs(y - miny) > 1 and abs(y - maxy) > 1 else (1 if abs(y - miny) <= 1 else -1)
        text = ex.replace("_", " ").replace(" exit", " exit")
        spots = [(x + dx * 140 + (60 if not dx else 0), y + dy * 90), (x + dx * 220, y + dy * 160),
                 (x + dx * 140 - (220 if not dx else 0), y + dy * 90)]
        lab.place(spots, text, (8, 7), color=HIGHWAY, ha="center", va="center",
                  fontweight="bold", path_effects=HALO, zorder=12)
    for b in m.bridges:
        if not b.name:
            continue
        xs, ys = [p[0] for p in b.line], [p[1] for p in b.line]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        spots = [(mx, my + 70), (mx, my - 70), (mx + 160, my), (mx - 160, my),
                 (mx + 120, my + 120), (mx - 120, my - 120)]
        lab.place(spots, b.name, (7, 6), color=BRIDGE.get(b.water_class or "sea"),
                  ha="center", va="center", style="italic", fontweight="bold",
                  path_effects=HALO, zorder=12)
