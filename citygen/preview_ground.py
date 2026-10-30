"""M16 preview: `preview_ground.png`, the ground cover. Left, the city: every piece of open
land colored by its cover kind, buildings dark, roads muted, desire lines white. Right, a
500 m window at street scale where a park's lawn is cut by the most desire lines, and two
small maps of the pieces' shade and maintenance.
Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PathCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from . import geom as G  # noqa: E402
from .cover import COVER_COLOR  # noqa: E402
from .preview_massing import _paths  # noqa: E402
from .schematic import BG, INK, LAND, MUTED, RIVER, SEA  # noqa: E402


def _ID(c):
    return c


FOOT = "#1a1e26"
ROAD = "#3a404c"


def _base(ax, m) -> None:
    P = G.from_model_poly
    land = [P(p) for x in m.land for p in x.polygons]
    ax.add_collection(PathCollection(_paths(land, _ID), facecolors=LAND, edgecolors="none",
                                     zorder=1))
    water = [P(r.polygon) for r in m.rivers] + [P(c.polygon) for c in m.channels] + \
        [P(w.polygon) for w in m.waterways]
    ax.add_collection(PathCollection(_paths(water, _ID), facecolors=RIVER, edgecolors="none",
                                     zorder=1.2))


def _cover(ax, m, colors=None, z: float = 2.0) -> None:
    P = G.from_model_poly
    by: dict[str, list] = {}
    for g in m.ground_cover:
        by.setdefault(colors(g) if colors else COVER_COLOR[g.kind], []).append(P(g.polygon))
    for col in sorted(by):
        ax.add_collection(PathCollection(_paths(by[col], _ID), facecolors=col, edgecolors="none",
                                         zorder=z))


def _hard(ax, m, lw: float) -> None:
    P = G.from_model_poly
    feet = [P(b.footprint) for b in m.buildings if b.footprint is not None and not b.level]
    ax.add_collection(PathCollection(_paths(feet, _ID), facecolors=FOOT, edgecolors="none",
                                     zorder=3))
    segs = [np.asarray(s.centerline) for s in m.road_segments if not s.tunnel and
            "deck" not in s.attrs]
    ax.add_collection(LineCollection(segs, colors=ROAD, linewidths=lw, zorder=2.5))


def _desire(ax, m, lw: float) -> None:
    segs = [np.asarray(d.line) for g in m.ground_cover for d in g.desire_lines]
    alpha = [0.35 + 0.65 * d.wear for g in m.ground_cover for d in g.desire_lines]
    if segs:
        ax.add_collection(LineCollection(segs, colors=[(1, 1, 1, a) for a in alpha],
                                         linewidths=lw, zorder=4))


def _window(m) -> tuple[float, float]:
    best = None
    for g in m.ground_cover:
        if g.kind not in ("park_lawn", "mown_lawn", "meadow") or not g.desire_lines:
            continue
        x, y = G.centroid(G.from_model_poly(g.polygon))
        key = (-len(g.desire_lines), -g.area_m2, round(x), round(y))
        if best is None or key < best[0]:
            best = (key, (x, y))
    if best is None and m.ground_cover:
        g = max(m.ground_cover, key=lambda g: (g.area_m2, g.id))
        return G.centroid(G.from_model_poly(g.polygon))
    return best[1] if best else (0.0, 0.0)


def _setup(ax, xs, ys) -> None:
    ax.set_facecolor(SEA)
    ax.set_xlim(*xs)
    ax.set_ylim(*ys)
    ax.set_aspect("equal")
    ax.axis("off")


def render_ground(b, out, dpi: int = 140) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    map_w, side_w = 10.0, 6.5
    fig_h = max(map_w * H / W, 9.0) + 1.3
    fig = plt.figure(figsize=(map_w + side_w, fig_h), facecolor=BG, dpi=dpi)
    st = b.stats.get("water", {})
    cov = st.get("cover", {})
    tot = sum(v["km2"] for v in cov.values()) or 1.0
    fig.text(0.012, 1 - 0.28 / fig_h, f"{b.spec.name}: ground cover (M16)", color=INK,
             fontsize=14, fontweight="bold", va="top")
    fig.text(0.012, 1 - 0.62 / fig_h,
             f"{sum(v['pieces'] for v in cov.values())} pieces, {tot:.2f} km2 of open land; "
             + ", ".join(f"{k.replace('_', ' ')} {v['km2'] / tot:.0%}"
                         for k, v in sorted(cov.items(), key=lambda t: -t[1]["km2"])[:5])
             + f"; {st.get('desire_lines', 0)} desire lines; "
             + ("checks PASS" if b.passed else "checks FAIL"), color=MUTED, fontsize=8.5,
             va="top")
    mh = map_w * H / W
    ax = fig.add_axes([0.0, 0.2 / fig_h, map_w / (map_w + side_w), mh / fig_h])
    _setup(ax, (x0, x1), (y0, y1))
    _base(ax, m)
    _cover(ax, m)
    _hard(ax, m, 0.4)
    _desire(ax, m, 0.4)
    hand = [Patch(facecolor=c, label=k.replace("_", " ")) for k, c in COVER_COLOR.items()
            if any(g.kind == k for g in m.ground_cover)]
    leg = ax.legend(handles=hand, loc="lower left", fontsize=7.5, facecolor=BG,
                    edgecolor=MUTED, labelcolor=INK, framealpha=0.85, ncol=2)
    leg.set_zorder(20)
    side_x = map_w / (map_w + side_w)
    sw = side_w / (map_w + side_w)
    cx, cy = _window(m)
    r = 250.0
    ax2 = fig.add_axes([side_x + 0.01, 0.42, sw - 0.02, 0.5])
    _setup(ax2, (cx - r, cx + r), (cy - r, cy + r))
    _base(ax2, m)
    _cover(ax2, m)
    _hard(ax2, m, 3.0)
    _desire(ax2, m, 1.6)
    ax2.set_title(f"500 m at ({cx:.0f}, {cy:.0f}): cover and desire lines", color=INK,
                  fontsize=9)
    cm = plt.get_cmap("magma")
    for k, (what, key) in enumerate((("shade", "shade"), ("maintenance", "maintenance"))):
        a = fig.add_axes([side_x + 0.01 + k * (sw / 2), 0.04, sw / 2 - 0.015, 0.33])
        _setup(a, (x0, x1), (y0, y1))
        _base(a, m)
        _cover(a, m, colors=lambda g, key=key: matplotlib.colors.to_hex(
            cm(0.15 + 0.85 * round(getattr(g, key), 1))))
        a.set_title(f"{what} (dark 0, light 1)", color=INK, fontsize=8)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
