"""Preview map of a built city (`preview_map.png`): water, landmasses, districts, waterways."""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import PathPatch, Patch  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from shapely.geometry import Point  # noqa: E402

from . import geom as G  # noqa: E402
from .schematic import ARCHETYPE_COLORS, BG, INK, LAND, MUTED, RIVER, SEA  # noqa: E402

CANAL = "#3f8fc4"
QUAY = "#d8dde6"
SEPARATION = "#2a74a8"
HALO = [pe.withStroke(linewidth=3, foreground=BG)]


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


def render(b, out, dpi: int = 110) -> None:
    m, spec, st = b.model, b.spec, b.stats
    minx, miny, maxx, maxy = m.bounds
    w, h = maxx - minx, maxy - miny
    fig_w, ax_w = 12.0, 8.4
    ax_h = ax_w * h / w
    fig_h = max(ax_h + 1.1, 7.5)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG)
    ax = fig.add_axes([0.02, 0.3 / fig_h, ax_w / fig_w, ax_h / fig_h])
    top = 1 - 0.25 / fig_h
    ax.set_facecolor(SEA)
    P = G.from_model_poly
    for x in m.land:
        for p in x.polygons:
            ax.add_patch(_patch(P(p), facecolor=LAND, edgecolor="none", zorder=1))
    arche = {}
    for d in m.districts:
        poly = P(d.polygon)
        col = ARCHETYPE_COLORS.get(d.archetype, "#888888")
        arche[d.archetype] = col
        ax.add_patch(_patch(poly, facecolor=col, alpha=0.55, edgecolor=col, lw=1.2, zorder=2))
    for r in m.rivers:
        ax.add_patch(_patch(P(r.polygon), facecolor=RIVER, edgecolor="none", zorder=3))
    for c in m.channels:
        col = SEPARATION if c.kind == "separation" else RIVER
        ax.add_patch(_patch(P(c.polygon), facecolor=col, edgecolor="none", zorder=3))
    for wv in m.waterways:
        ax.add_patch(_patch(P(wv.polygon), facecolor=CANAL, edgecolor="none", zorder=4))
    for q in m.quays:
        xs, ys = zip(*q.line)
        ax.plot(xs, ys, color=QUAY, lw=0.5, alpha=0.8, zorder=5)
    for isl in m.islands:
        ax.add_patch(_patch(P(isl.polygon), facecolor="none", edgecolor=INK, lw=0.8,
                            linestyle=(0, (4, 3)), zorder=6))
    for lm in m.landmasses:
        ax.add_patch(_patch(P(lm.polygon), facecolor="none", edgecolor="#000000", lw=0.6,
                            alpha=0.6, zorder=6))
        if not lm.district_ids:
            poly = P(lm.polygon)
            ax.add_patch(_patch(poly, facecolor="none", edgecolor=MUTED, hatch="///", lw=0,
                                zorder=6))
    for d in m.districts:
        poly = P(d.polygon)
        c = poly.representative_point() if not poly.contains(poly.centroid) else poly.centroid
        size = 9 if poly.area > 4e5 else 7
        ax.text(c.x, c.y, d.name, color=INK, ha="center", va="center", fontsize=size,
                fontweight="bold", path_effects=HALO, zorder=10)
    labeled = set()
    isl_polys = [P(i.polygon) for i in m.islands]
    for r in list(m.rivers) + [c for c in m.channels if c.kind == "sea_channel"]:
        if r.name in labeled or len(r.centerline) < 2:
            continue
        labeled.add(r.name)
        n = len(r.centerline)
        k = n // 3
        for frac in (0.33, 0.2, 0.5, 0.66, 0.1, 0.8):  # first spot not under an island label
            j = min(int(frac * n), n - 1)
            if not any(ip.buffer(150).contains(Point(r.centerline[j])) for ip in isl_polys):
                k = j
                break
        (x0, y0), (x1, y1) = r.centerline[k], r.centerline[min(k + 3, n - 1)]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
        ax.text(x0, y0, r.name, color="#9fd4ff", fontsize=7, rotation=ang, ha="center",
                va="center", style="italic", path_effects=HALO, zorder=9)
    for isl in m.islands:
        poly = P(isl.polygon)
        if any(d.name == isl.name for d in m.districts):
            continue
        c = poly.representative_point()
        ax.text(c.x, c.y, isl.name, color=MUTED, fontsize=7, ha="center", va="center",
                style="italic", path_effects=HALO, zorder=9)
    if m.seas and m.seas[0].name:
        big = max((P(p) for p in m.seas[0].polygons), key=lambda g: g.area)
        c = big.representative_point()
        ax.text(c.x, c.y, m.seas[0].name, color="#7fa6c9", fontsize=10, style="italic",
                ha="center", va="center", path_effects=HALO, zorder=9)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(MUTED)
    _scale_bar(ax, m.bounds)
    ax.text(maxx - 0.03 * w, miny + 0.04 * h, "N\n^", color=INK, ha="center", fontsize=9,
            path_effects=HALO, zorder=20)
    status = "checks PASS" if b.passed else "checks FAIL"
    fig.text(0.02, top, f"{spec.name}: water, districts and waterways (M1a)",
             color=INK, fontsize=14, fontweight="bold", va="top")
    fig.text(0.02, top - 0.3 / fig_h, f"seed {spec.seed}, {w / 1000:g} x {h / 1000:g} km, "
             f"land {st['land_km2']} km2, water {st['water_share']:.0%}, "
             f"{st['landmasses']} landmasses, waterways {st['waterway_km']} km, {status}",
             color=MUTED, fontsize=9, va="top")
    handles = [Patch(facecolor=col, alpha=0.55, edgecolor=col, label=a.replace("_", " "))
               for a, col in sorted(arche.items())]
    handles += [Patch(facecolor=SEA, label="sea"), Patch(facecolor=RIVER, label="river / branch"),
                Patch(facecolor=SEPARATION, label="separation channel"),
                Patch(facecolor=CANAL, label="inner waterway"),
                Line2D([], [], color=QUAY, lw=1, label="quay"),
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
    fig.text(x_side + 0.005, (0.3 + ax_h - 4.6) / fig_h,
             "district share / target\n" + "\n".join(rows), color=INK,
             fontsize=7, family="monospace", va="top")
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)
