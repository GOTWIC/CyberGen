"""M5 preview: `preview_transit.png`, the transit map. The city plan in muted tones (land,
water, roads, building footprints) under every transit line in its color (metro dashed,
elevated solid, sky tubes with a light casing), stations as rings with their names, supports
as dots, removed buildings outlined in red and tower portals marked; M8b: a red cross where a
line meets itself at the same level (`transit_self_crossing`) and stop numbers in route order
on the stations of a loop. Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from . import geom as G  # noqa: E402
from . import transit as TR  # noqa: E402
from .preview_massing import _ground  # noqa: E402
from .schematic import BG, INK, MUTED, SEA  # noqa: E402

HALO = [pe.withStroke(linewidth=2.5, foreground=BG)]
ROAD = "#3b404b"
FOOT = "#2b303a"
MODE_STYLE = {"metro": ("--", 2.0), "elevated_rail": ("-", 2.4), "monorail": ("-", 1.8),
              "maglev": ("-", 2.8), "sky_tube": ("-", 2.4)}
MODE_NAME = {"metro": "metro", "elevated_rail": "elevated rail", "monorail": "monorail",
             "maglev": "maglev", "sky_tube": "sky tube"}


def render_transit(b, out, dpi: int = 150) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    fig_w, head = 12.0, 1.2
    fig = plt.figure(figsize=(fig_w, fig_w * H / W + head), facecolor=BG, dpi=dpi)
    fh = fig_w * H / W + head
    ax = fig.add_axes([0.0, 0.0, 1.0, (fig_w * H / W) / fh])
    ax.set_facecolor(SEA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    _ground(ax, m)
    P = G.from_model_poly
    roads = [np.asarray(s.centerline) for s in m.road_segments
             if s.road_class in ("highway", "avenue", "street")]
    ax.add_collection(LineCollection(roads, colors=ROAD, linewidths=0.4, zorder=2))
    foot = [np.asarray(P(b_.footprint).exterior.coords) for b_ in m.buildings
            if b_.footprint is not None]
    ax.add_collection(PolyCollection(foot, facecolors=FOOT, edgecolors="none", zorder=2.5))
    portals = [b_ for b_ in m.buildings if b_.portals and b_.footprint is not None]
    ax.add_collection(PolyCollection([np.asarray(P(b_.footprint).exterior.coords)
                                      for b_ in portals], facecolors="none",
                                     edgecolors="#e8e8f0", linewidths=0.5, zorder=2.6))
    removed = {}
    for t in m.transit_lines:
        for bid in t.attrs.get("removed_buildings", []):
            removed.setdefault(bid, t.color)
    rm_polys = [np.asarray(P(lt.polygon).exterior.coords) for lt in m.lots
                if (lt.attrs or {}).get("transit_corridor")]
    ax.add_collection(PolyCollection(rm_polys, facecolors="none", edgecolors="#d0453a",
                                     linewidths=0.4, linestyles=":", zorder=2.7))
    sup = [s for s in m.structures if s.kind in ("column", "pylon") and
           (s.attrs or {}).get("line_id") and s.footprint is not None]
    if sup:
        c = np.array([[P(s.footprint).centroid.x, P(s.footprint).centroid.y] for s in sup])
        ax.scatter(c[:, 0], c[:, 1], s=1.2, c="#9aa0aa", zorder=3, linewidths=0)
        # M19: piers in the water and the sky tubes' masts stand out
        big = [s for s in sup if (s.attrs or {}).get("form") in ("pier", "mast")]
        if big:
            c = np.array([[P(s.footprint).centroid.x, P(s.footprint).centroid.y] for s in big])
            ax.scatter(c[:, 0], c[:, 1], s=9, marker="s", c="#c8ccd4", zorder=3.1,
                       linewidths=0)
    beams = [np.asarray([p[:2] for p in s.line]) for s in m.structures
             if s.kind == "beam" and len(s.line) >= 2]
    if beams:
        ax.add_collection(LineCollection(beams, colors="#9aa0aa", linewidths=0.7, zorder=3))
    handles = []
    for t in sorted(m.transit_lines, key=lambda t: (t.mode == "metro", t.id)):
        ls, lw = MODE_STYLE.get(t.mode, ("-", 2.0))
        xy = np.asarray([p[:2] for p in t.path])
        if t.mode == "sky_tube":
            ax.plot(xy[:, 0], xy[:, 1], color="#e8f6ff", lw=lw + 2.2, alpha=0.5, zorder=4,
                    solid_capstyle="round")
        ax.plot(xy[:, 0], xy[:, 1], color=t.color, lw=lw, ls=ls, zorder=4.5 if
                t.mode != "metro" else 4.2, solid_capstyle="round")
        a = t.attrs
        r = a.get("min_radius_m")
        handles.append(Line2D([], [], color=t.color, lw=lw, ls=ls, label=(
            f"{t.name} ({MODE_NAME.get(t.mode, t.mode)}{', loop' if t.loop else ''}): "
            f"{a.get('length_m', 0) / 1000:.1f} km, {len(t.station_ids)} stations, z "
            f"{min(p[2] for p in t.path):g} to {max(p[2] for p in t.path):g} m"
            + (f", radius {r:g} m" if r else ""))))
    meet = []
    for t in m.transit_lines:
        pts = [(p[0], p[1]) for p in t.path]
        zs = [p[2] for p in t.path]
        meet += [(x, y) for _, x, y in TR.self_meets(pts, t.loop, TR.WIDTH_M[t.mode], zs,
                                                      TR.self_clear_m(t.mode))]
    if meet:
        c = np.asarray(meet)
        ax.scatter(c[:, 0], c[:, 1], s=140, marker="x", c="#ff3b30", linewidths=2.2, zorder=8)
    labeled: dict = {}
    order: dict = {}
    for t in m.transit_lines:
        if t.loop:
            stops = t.attrs.get("stops", [])
            for k, name in enumerate(stops[:-1] if len(stops) > 1 else stops):
                order.setdefault((t.id, name), k + 1)
    for s in m.stations:
        x, y = s.position[0], s.position[1]
        col = next((t.color for t in m.transit_lines if t.id in s.line_ids), INK)
        ax.scatter([x], [y], s=26, facecolors=BG, edgecolors=col, linewidths=1.6, zorder=6)
        # one label for the stations of a stop (an interchange)
        if any(math.dist((x, y), p) < 400.0 for p in labeled.get(s.name, [])):
            continue
        labeled.setdefault(s.name, []).append((x, y))
        k = next((order[(lid, s.attrs.get("stop"))] for lid in s.line_ids
                  if (lid, s.attrs.get("stop")) in order), None)
        ax.text(x + 22, y + 22, f"{k}. {s.name}" if k else s.name, fontsize=5.5, color=INK,
                zorder=7, path_effects=HALO)
    handles += [Line2D([], [], marker="o", ls="", markerfacecolor=BG, markeredgecolor=INK,
                       label="station"),
                Line2D([], [], marker=".", ls="", color="#9aa0aa", label="column, pylon"),
                Line2D([], [], color="#e8e8f0", lw=1, label="tower with a portal"),
                Line2D([], [], color="#d0453a", lw=1, ls=":",
                       label="lot cleared for a line")] + \
        ([Line2D([], [], marker="x", ls="", color="#ff3b30", label="line meets itself")]
         if meet else [])
    ax.legend(handles=handles, loc="lower left", fontsize=6.5, frameon=True, facecolor=BG,
              edgecolor=MUTED, labelcolor=INK, framealpha=0.85)
    st = b.stats.get("transit", {})
    fig.text(0.04, 1.0 - 0.15 / fh, f"{b.spec.name}: transit (M5, M8b loops, M19 structures)",
             color=INK, fontsize=13, fontweight="bold", va="top")
    stations = ", ".join(f"{k} {v}" for k, v in st.get("stations", {}).items())
    forms = ", ".join(f"{v} {k}{'s' if v != 1 else ''}"
                      for k, v in st.get("support_forms", {}).items())
    fig.text(0.04, 1.0 - 0.48 / fh,
             f"{len(m.transit_lines)} lines, {st.get('km', 0):g} km; stations {stations}; "
             f"{st.get('portals', 0)} tower portals, {st.get('buildings_removed', 0)} "
             f"buildings removed for the lines; {'checks PASS' if b.passed else 'checks FAIL'}"
             f"\nsupports: {forms or st.get('supports', 0)}",
             color=MUTED, fontsize=8.5, va="top", linespacing=1.5)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)
