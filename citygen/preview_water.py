"""M16 preview: `preview_water.png`, the water in detail. Left, the city: every water body's
bed shaded by depth (16 m samples), the sea's exposure outlined (open, sheltered, harbor),
the banks drawn by kind along the water's edge, flow arrows along the rivers, channels and
canals. Right, a 600 m window at street scale where the most bank kinds meet (the banks'
widths out over the water drawn true), and the cross-section of the widest river or channel.
Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PathCollection, PolyCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

from . import geom as G  # noqa: E402
from . import water as WA  # noqa: E402
from .water import BANK_COLOR  # noqa: E402
from .preview_massing import _paths  # noqa: E402
from .schematic import BG, INK, LAND, MUTED, SEA  # noqa: E402


def _ID(c):
    return c


EXPO_COLOR = {"open": "#ff6b6b", "sheltered": "#ffd166", "harbor": "#8be9fd"}
CMAP = plt.get_cmap("Blues")
SAMPLE_M = 16.0
FOOT = "#3a404c"
ROAD = "#4a505c"


def _depth_image(m, beds: WA.Beds, x0, y0, x1, y1, step: float):
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    X, Y = np.meshgrid(xs, ys)
    img = np.full(X.shape, np.nan)
    import shapely

    for wid, b in beds.bl.items():
        inside = shapely.contains_xy(b.poly, X, Y)
        if not inside.any():
            continue
        img[inside] = beds.depth_many(wid, X[inside], Y[inside])
    return img


def _water_base(ax, m, z: float = 1.0) -> None:
    P = G.from_model_poly
    land = [P(p) for x in m.land for p in x.polygons]
    ax.add_collection(PathCollection(_paths(land, _ID), facecolors=LAND, edgecolors="none",
                                     zorder=z))


def _banks(ax, m, lw: float, true_width: bool = False) -> None:
    for kind, col in BANK_COLOR.items():
        ks = [k for k in m.banks if k.kind == kind]
        if not ks:
            continue
        if true_width:
            polys = []
            for k in ks:
                g = LineString(k.line).buffer(max(k.width_m, 0.6), single_sided=True,
                                              cap_style="flat")
                polys += [np.asarray(p.exterior.coords) for p in G.parts(g)]
            ax.add_collection(PolyCollection(polys, facecolors=col, edgecolors="none",
                                             alpha=0.85, zorder=6))
        segs = [np.asarray(k.line) for k in ks]
        ax.add_collection(LineCollection(segs, colors=col, linewidths=lw, zorder=7,
                                         capstyle="butt"))


def _arrows(ax, m, step: float, scale: float) -> None:
    for e in [*m.rivers, *m.channels, *m.waterways]:
        f = e.flow
        if f is None or not f.line or f.speed_m_s <= 0:
            continue
        pts = [tuple(p) for p in f.line]
        cum = WA._cum(pts)
        s = step / 2
        while s < cum[-1]:
            x, y, tx, ty = WA._point_at(pts, cum, s)
            L = scale * (0.6 + f.speed_m_s)
            ax.annotate("", xy=(x + tx * L, y + ty * L), xytext=(x - tx * L, y - ty * L),
                        arrowprops=dict(arrowstyle="-|>", color="#e8f6ff", lw=0.9,
                                        mutation_scale=7), zorder=8)
            s += step


def _window(m) -> tuple[float, float]:
    """The middle of the 600 m window where the most bank kinds meet."""
    best = None
    for k in m.banks:
        x, y = k.line[len(k.line) // 2]
        kinds = {b.kind for b in m.banks
                 if any(abs(px - x) < 300 and abs(py - y) < 300 for px, py in b.line[::4])}
        key = (-len(kinds), round(x), round(y))
        if best is None or key < best[0]:
            best = (key, (x, y))
    return best[1] if best else (0.0, 0.0)


def render_water(b, out, dpi: int = 140) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    map_w, side_w = 10.0, 6.5
    fig_h = max(map_w * H / W, 9.0) + 1.3
    fig = plt.figure(figsize=(map_w + side_w, fig_h), facecolor=BG, dpi=dpi)
    st = b.stats.get("water", {})
    fig.text(0.012, 1 - 0.28 / fig_h, f"{b.spec.name}: water and banks (M16)", color=INK,
             fontsize=14, fontweight="bold", va="top")
    bk = st.get("banks", {})
    fig.text(0.012, 1 - 0.62 / fig_h,
             f"{st.get('water_bodies', 0)} water bodies; banks "
             + ", ".join(f"{k.replace('_', ' ')} {v['km']} km" for k, v in bk.items())
             + f"; {'checks PASS' if b.passed else 'checks FAIL'}", color=MUTED, fontsize=9,
             va="top")
    beds = WA.Beds(m)
    mh = map_w * H / W
    ax = fig.add_axes([0.0, 0.2 / fig_h, map_w / (map_w + side_w), mh / fig_h])
    ax.set_facecolor(SEA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    dmax = max([e.depth_m for e in [*m.seas, *m.rivers, *m.channels, *m.waterways]
                if e.depth_m is not None] or [1.0])
    norm = Normalize(-0.25 * dmax, dmax)     # (shallow water a light blue, not white)
    img = _depth_image(m, beds, x0, y0, x1, y1, SAMPLE_M)
    ax.imshow(img, extent=(x0, x1, y0, y1), origin="lower", cmap=CMAP, norm=norm,
              interpolation="nearest", zorder=1.5)
    _water_base(ax, m)
    for s in m.seas:
        for e in s.exposure:
            p = G.from_model_poly(e.polygon)
            ax.add_collection(PolyCollection([np.asarray(p.exterior.coords)],
                                             facecolors="none", edgecolors=EXPO_COLOR[e.kind],
                                             linewidths=0.7, linestyles="--", zorder=3))
    _banks(ax, m, 1.6)
    _arrows(ax, m, 260.0, 30.0)
    hand = [Line2D([], [], color=c, lw=3, label=k.replace("_", " "))
            for k, c in BANK_COLOR.items() if any(x.kind == k for x in m.banks)]
    hand += [Line2D([], [], color=c, lw=1, ls="--", label=f"{k} sea")
             for k, c in EXPO_COLOR.items() if any(e.kind == k for s in m.seas
                                                   for e in s.exposure)]
    leg = ax.legend(handles=hand, loc="lower left", fontsize=7.5, facecolor=BG,
                    edgecolor=MUTED, labelcolor=INK, framealpha=0.85, ncol=2)
    leg.set_zorder(20)
    side_x = map_w / (map_w + side_w)
    cax = fig.add_axes([side_x + 0.06, 0.375, side_w / (map_w + side_w) - 0.12, 0.012])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=CMAP), cax=cax,
                      orientation="horizontal")
    cb.set_label("water depth m", color=MUTED, fontsize=7)
    cb.ax.tick_params(colors=MUTED, labelsize=6)
    # the window
    cx, cy = _window(m)
    r = 300.0
    cx = min(max(cx, x0 + r), x1 - r)
    cy = min(max(cy, y0 + r), y1 - r)
    ax2 = fig.add_axes([side_x + 0.01, 0.42, side_w / (map_w + side_w) - 0.02, 0.5])
    ax2.set_facecolor(SEA)
    ax2.set_xlim(cx - r, cx + r)
    ax2.set_ylim(cy - r, cy + r)
    ax2.set_aspect("equal")
    ax2.axis("off")
    img2 = _depth_image(m, beds, cx - r, cy - r, cx + r, cy + r, 4.0)
    ax2.imshow(img2, extent=(cx - r, cx + r, cy - r, cy + r), origin="lower", cmap=CMAP,
               norm=norm, interpolation="nearest", zorder=1.5)
    _water_base(ax2, m)
    P = G.from_model_poly
    feet = [np.asarray(P(x.footprint).exterior.coords) for x in m.buildings
            if x.footprint is not None and abs(x.footprint.exterior[0][0] - cx) < r + 200
            and abs(x.footprint.exterior[0][1] - cy) < r + 200]
    ax2.add_collection(PolyCollection(feet, facecolors=FOOT, edgecolors="none", zorder=2))
    roads = [np.asarray(s.centerline) for s in m.road_segments
             if not s.tunnel and abs(s.centerline[0][0] - cx) < r + 400
             and abs(s.centerline[0][1] - cy) < r + 400]
    ax2.add_collection(LineCollection(roads, colors=ROAD, linewidths=2.0, zorder=2))
    _banks(ax2, m, 2.0, true_width=True)
    _arrows(ax2, m, 90.0, 12.0)
    ax2.set_title(f"600 m at ({cx:.0f}, {cy:.0f}): banks to their waterline", color=INK,
                  fontsize=9)
    # the cross-section of the widest river or channel
    ax3 = fig.add_axes([side_x + 0.05, 0.08, side_w / (map_w + side_w) - 0.08, 0.25])
    ax3.set_facecolor(BG)
    for sp in ax3.spines.values():
        sp.set_color(MUTED)
    ax3.tick_params(colors=MUTED, labelsize=7)
    wide = max([e for e in [*m.rivers, *m.channels] if e.depth_m is not None],
               key=lambda e: (max(e.width_m), e.id), default=None)
    if wide is not None:
        pts = [tuple(p) for p in wide.centerline]
        cum = WA._cum(pts)
        n = len(pts)
        k = max(range(n // 4, max(n // 4 + 1, 3 * n // 4)), key=lambda i: (wide.width_m[i], -i))
        x, y, tx, ty = WA._point_at(pts, cum, cum[k])
        hw = wide.width_m[k] * 0.75
        ts = np.linspace(-hw, hw, 241)
        X, Y = x - ty * ts, y + tx * ts
        import shapely

        inside = shapely.contains_xy(beds.bl[wide.id].poly, X, Y)
        d = np.where(inside, beds.depth_many(wide.id, X, Y), np.nan)
        surf = -WA.FREEBOARD_M if m.terrain is None else 0.0
        ax3.fill_between(ts, surf - np.nan_to_num(d, nan=0.0), surf, where=inside,
                         color="#1d5a85", zorder=1)
        ax3.plot(ts, np.where(inside, surf - d, np.nan), color="#c8a46a", lw=1.5, zorder=2)
        ax3.axhline(0.0 if m.terrain is None else surf, color=MUTED, lw=0.6, ls=":")
        ax3.set_title(f"{wide.name or wide.id}: cross-section ({wide.width_m[k]:.0f} m "
                      f"wide), flow {wide.flow.speed_m_s:g} m/s toward "
                      f"{wide.flow.toward or 'the map edge'}", color=INK, fontsize=8)
        ax3.set_xlabel("m across", color=MUTED, fontsize=7)
        ax3.set_ylabel("m (ground 0)" if m.terrain is None else "m over the water",
                       color=MUTED, fontsize=7)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
