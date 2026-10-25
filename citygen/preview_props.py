"""M6 preview: `preview_props.png`, four 180 m insets at street level (the districts of
`preview_detail.png`) with the M2 street drawing under the building footprints, every prop
drawn to its size and yaw (street lights with a glow, parked cars, bus shelters, benches,
stalls, dumpsters, trash, boats, cables across the street), and the plants: tree crowns in
their true radius, palms, conifers, shrubs, hedges and median lawns. Previews are for review
only (not part of the model hash).
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PatchCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Patch  # noqa: E402

from .preview_detail import _SHAPES, draw_inset, pick_insets  # noqa: E402
from .props import KINDS  # noqa: E402
from .schematic import BG, INK, MUTED  # noqa: E402

HALO = [pe.withStroke(linewidth=2.5, foreground=BG)]
HALF = 90.0
PROP_COLORS = {
    "street_light": "#ffe27a", "wall_light": "#ffe27a", "traffic_signal": "#ff5a4e",
    "trash_can": "#8a9099", "bus_stop": "#5ec8ff", "hydrant": "#e2493a", "bollard": "#c9ccd2",
    "bench": "#b8875a", "kiosk": "#ff7ad9", "vending_machine": "#ff7ad9",
    "food_stall": "#ffb347", "planter": "#6aa86f", "parked_vehicle": "#d7dbe3",
    "boat": "#f2f2f2", "barrier": "#9aa0aa", "railing": "#c9ccd2", "sign": "#ff4fd8",
    "awning": "#e8a23a", "ac_unit": "#9aa3ad", "scaffolding": "#d9b25a", "gate": "#d0453a",
    "dumpster": "#4f8a57", "trash": "#b0a48a", "overhead_cable": "#111317"}
PLANT_COLORS = {"street_tree": "#4e9a52", "median_tree": "#4e9a52", "park_tree": "#3f8a47",
                "conifer": "#2f6e45", "palm": "#8fbf4a", "shrub": "#5aa060",
                "roof_tree": "#5aa060", "overgrowth": "#7a8a4a", "facade_greenery": "#6fbf5a"}


def _box(x, y, yaw, sx, sy):
    a = math.radians(yaw)
    ca, sa = math.cos(a), math.sin(a)
    return [(x + ca * u - sa * v, y + sa * u + ca * v)
            for u, v in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2),
                         (-sx / 2, sy / 2))]


def _kind(e) -> str:
    return (e.type or "").split(".", 1)[-1]


def draw_dressing(ax, m, center) -> None:
    cx, cy = center
    x0, y0, x1, y1 = cx - HALF - 10, cy - HALF - 10, cx + HALF + 10, cy + HALF + 10

    def inside(p):
        return x0 <= p[0] <= x1 and y0 <= p[1] <= y1
    bld = []
    for b in m.buildings:
        if b.footprint is None:
            continue
        ext = b.footprint.exterior
        if any(inside(p) for p in ext):
            bld.append(np.asarray(ext))
    ax.add_collection(PolyCollection(bld, facecolors="#2a2f3a", edgecolors="#565d6b",
                                     linewidths=0.6, zorder=4))
    lawns = [np.asarray(g.polygon.exterior) for g in m.green_areas
             if g.kind == "lawn" and g.polygon is not None and
             any(inside(p) for p in g.polygon.exterior)]
    ax.add_collection(PolyCollection(lawns, facecolors="#4f8a57", edgecolors="none",
                                     zorder=3.95))
    hedges = [np.asarray(g.line) for g in m.green_areas if g.kind == "hedge_line" and
              any(inside(p) for p in g.line)]
    ax.add_collection(LineCollection(hedges, colors="#2f6e45", linewidths=2.6, zorder=4.1))
    boxes, cols, glow, cables = [], [], [], []
    for p in m.props:
        pos = p.position
        if not inside(pos):
            continue
        k = _kind(p)
        sx, sy, _ = KINDS.get(k, (None, (1.0, 1.0, 1.0)))[1]
        if k == "overhead_cable":
            a = math.radians(p.yaw_deg)
            h = p.scale[0] / 2.0
            cables.append([(pos[0] - math.cos(a) * h, pos[1] - math.sin(a) * h),
                           (pos[0] + math.cos(a) * h, pos[1] + math.sin(a) * h)])
            continue
        if k in ("street_light", "wall_light"):
            glow.append(Circle((pos[0], pos[1]), 6.0))
        boxes.append(_box(pos[0], pos[1], p.yaw_deg, sx * p.scale[0], sy * p.scale[1]))
        cols.append(PROP_COLORS.get(k, "#cccccc"))
    ax.add_collection(PatchCollection(glow, facecolors="#ffe27a", edgecolors="none",
                                      alpha=0.10, zorder=4.2))
    ax.add_collection(LineCollection(cables, colors="#0b0d10", linewidths=0.7, alpha=0.9,
                                     zorder=6.5))
    crowns, ccols = [], []
    for p in sorted(m.plants, key=lambda p: (p.height_m, p.id)):
        if not inside(p.position) or _kind(p) == "facade_greenery":
            continue
        crowns.append(Circle((p.position[0], p.position[1]), p.crown_radius_m))
        ccols.append(PLANT_COLORS.get(_kind(p), "#4e9a52"))
    ax.add_collection(PatchCollection(crowns, facecolors=ccols, edgecolors="#1f3d25",
                                      linewidths=0.3, alpha=0.85, zorder=6))
    ax.add_collection(PolyCollection(boxes, facecolors=cols, edgecolors="#111317",
                                     linewidths=0.25, zorder=5))
    ax.set_xlim(cx - HALF, cx + HALF)
    ax.set_ylim(cy - HALF, cy + HALF)


def render_props(b, out, dpi: int = 130) -> None:
    m = b.model
    _SHAPES.clear()
    picks = pick_insets(m)
    if not picks:
        return
    n = len(picks)
    cols = 2 if n > 1 else 1
    rows = int(math.ceil(n / cols))
    size = 7.6
    H, W = rows * size + 1.5, cols * size + 0.4
    fig = plt.figure(figsize=(W, H), facecolor=BG, dpi=dpi)
    st = b.stats.get("props", {})
    fig.text(0.015, 1 - 0.25 / H, f"{b.spec.name}: props and vegetation, "
             f"{int(2 * HALF)} m insets (M6)", color=INK, fontsize=14, fontweight="bold",
             va="top")
    fig.text(0.015, 1 - 0.55 / H,
             f"{st.get('props', 0)} props, {st.get('plants', 0)} plants "
             f"({st.get('trees', 0)} trees), lawns {st.get('lawn_m2', 0)} m2, hedges "
             f"{st.get('hedge_km', 0)} km; {'checks PASS' if b.passed else 'checks FAIL'}",
             color=MUTED, fontsize=9, va="top")
    for k, (did, c) in enumerate(picks):
        r, qq = divmod(k, cols)
        ax = fig.add_axes([(0.2 + qq * size) / W, (0.6 + (rows - 1 - r) * size) / H,
                           (size - 0.2) / W, (size - 0.2) / H])
        draw_inset(ax, m, did, c, k + 1)
        draw_dressing(ax, m, c)
    handles = [Patch(facecolor=PROP_COLORS[k], label=k.replace("_", " ")) for k in
               ("street_light", "traffic_signal", "parked_vehicle", "bus_stop", "bench",
                "food_stall", "dumpster", "trash", "sign", "awning", "bollard", "boat")]
    handles += [Patch(facecolor=PLANT_COLORS[k], label=k.replace("_", " ")) for k in
                ("street_tree", "park_tree", "conifer", "palm", "shrub")]
    handles += [Line2D([], [], color="#2f6e45", lw=2.6, label="hedge"),
                Line2D([], [], color="#0b0d10", lw=1, label="overhead cable"),
                Patch(facecolor="#2a2f3a", edgecolor="#565d6b", label="building")]
    fig.legend(handles=handles, loc="lower center", ncol=11, frameon=False, fontsize=7.5,
               labelcolor=INK, bbox_to_anchor=(0.5, 0.0))
    _SHAPES.clear()
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)

