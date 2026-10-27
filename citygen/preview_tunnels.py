"""M9 preview: `preview_tunnels.png`, the city under the ground. Left, the city: roads in
muted tones, road tunnels as wide strips (immersed tubes, cut-and-cover tunnels; their open
approaches lighter, portals, ventilation buildings), metro tunnels colored by track depth
between their station boxes, pedestrian underpasses. Right, the longest road tunnel at
street scale (the roads over it, the buildings beside it) and the long sections of the road
tunnels and the metro (road or track, roof, ground, water and its bed, roads over).
Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402

from . import geom as G  # noqa: E402
from . import tunnels as TN  # noqa: E402
from .preview_massing import _ground  # noqa: E402
from .schematic import BG, INK, MUTED, SEA  # noqa: E402

HALO = [pe.withStroke(linewidth=2.5, foreground=BG)]
GROUND = "#4a505c"
FOOT = "#2b303a"
PANEL = "#20242c"
KIND_COLOR = {"immersed_tube": "#22d3ee", "cut_and_cover": "#f59e0b"}
OPEN_COLOR = {"immersed_tube": "#8ff3ff", "cut_and_cover": "#ffd27a"}
VENT = "#ff4fd8"
UNDER = "#7ee0c3"
CMAP = plt.get_cmap("Blues_r")
ZMIN = -40.0
ROAD = ("immersed_tube", "cut_and_cover")


def _cum(pts):
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + float(np.hypot(b[0] - a[0], b[1] - a[1])))
    return out


def _portal_s(t) -> tuple[float, float]:
    from .elevated import _project

    pts = [(p[0], p[1]) for p in t.line]
    cum = _cum(pts)
    sp = sorted(_project(pts, cum, p.position[:2])[0] for p in t.portals) or [0.0, cum[-1]]
    return sp[0], sp[-1]


def _strip(pts, w):
    return LineString(pts).buffer(w / 2.0, cap_style="flat", join_style="mitre")


def _poly_xy(poly):
    return [np.asarray(p.exterior.coords) for p in G.parts(poly)]


def _road_tunnel(ax, t, lw_scale: float = 1.0, label: bool = True) -> None:
    from .elevated import _sub

    pts = [(p[0], p[1]) for p in t.line]
    cum = _cum(pts)
    a, b = _portal_s(t)
    col, light = KIND_COLOR.get(t.kind, "#cccccc"), OPEN_COLOR.get(t.kind, "#eeeeee")
    w = max(t.width_m, 8.0)
    covered = _strip(_sub(pts, cum, a, b), w)
    ax.add_collection(PolyCollection(_poly_xy(covered), facecolors=col, edgecolors="none",
                                     zorder=4))
    for x0, x1 in ((0.0, a), (b, cum[-1])):
        if x1 - x0 > 0.5:
            ax.add_collection(PolyCollection(_poly_xy(_strip(_sub(pts, cum, x0, x1), w)),
                                             facecolors=light, edgecolors=col,
                                             linewidths=0.4 * lw_scale, hatch="////",
                                             zorder=4))
    for p in t.portals:
        ax.plot([p.position[0]], [p.position[1]], marker="s", ms=3.0 * lw_scale, mfc=BG,
                mec="#ffffff", mew=0.8, zorder=6)
    if label:
        mid = LineString(pts).interpolate(0.5, normalized=True)
        name = t.name or t.id
        ax.text(mid.x, mid.y, f" {name}", color=INK, fontsize=7.5, fontweight="bold",
                path_effects=HALO, zorder=7, ha="left", va="bottom")


def _vents(ax, m, ms: float = 3.0, box=None) -> None:
    for s in m.structures:
        if s.kind != "vent" or s.footprint is None:
            continue
        c = G.from_model_poly(s.footprint)
        if box is not None and not (box[0] <= c.centroid.x <= box[2] and
                                    box[1] <= c.centroid.y <= box[3]):
            continue
        ax.add_collection(PolyCollection(_poly_xy(c), facecolors=VENT, edgecolors="#ffffff",
                                         linewidths=0.4, zorder=6))


def _metro(ax, m, lw: float = 2.0) -> None:
    norm = Normalize(ZMIN, 0.0)
    for t in m.tunnels:
        if t.kind != "metro":
            continue
        pts = [(p[0], p[1]) for p in t.line]
        segs = [[pts[k], pts[k + 1]] for k in range(len(pts) - 1)]
        zs = [(t.line[k][2] + t.line[k + 1][2]) / 2.0 for k in range(len(pts) - 1)]
        ax.add_collection(LineCollection(segs, colors=CMAP(norm(np.asarray(zs)) * 0.75),
                                         linewidths=lw, zorder=3.4, capstyle="round"))
    for st in m.stations:
        if st.kind == "underground" and st.footprint is not None:
            ax.add_collection(PolyCollection(_poly_xy(G.from_model_poly(st.footprint)),
                                             facecolors="#2f7bff", edgecolors="#ffffff",
                                             linewidths=0.5, zorder=3.6))


def _underpasses(ax, m, lw: float = 2.4, box=None) -> None:
    for t in m.tunnels:
        if t.kind != "pedestrian":
            continue
        a, b = t.line[0], t.line[-1]
        if box is not None and not (box[0] <= a[0] <= box[2] and box[1] <= a[1] <= box[3]):
            continue
        ax.plot([a[0], b[0]], [a[1], b[1]], color=UNDER, lw=lw, zorder=5.5,
                solid_capstyle="butt")
    for s in m.structures:
        if (s.attrs or {}).get("role") == "underpass_stair" and s.footprint is not None:
            ax.add_collection(PolyCollection(_poly_xy(G.from_model_poly(s.footprint)),
                                             facecolors=UNDER, edgecolors="none", zorder=5.6))


def _roads(ax, m, lw_scale: float = 1.0, box=None) -> None:
    def inside(s):
        if box is None:
            return True
        xs = [p[0] for p in s.centerline]
        ys = [p[1] for p in s.centerline]
        return not (max(xs) < box[0] or min(xs) > box[2] or max(ys) < box[1] or
                    min(ys) > box[3])
    rows = [s for s in m.road_segments if s.road_class in ("highway", "avenue", "street",
                                                          "alley", "service") and inside(s)]
    lines = [np.asarray(s.centerline) for s in rows if not s.tunnel]
    ws = [(1.0 if s.road_class == "highway" else 0.7 if s.road_class == "avenue" else 0.45)
          * lw_scale for s in rows if not s.tunnel]
    ax.add_collection(LineCollection(lines, colors=GROUND, linewidths=ws, zorder=2))
    over = [np.asarray(s.centerline) for s in rows if s.attrs.get("over_tunnel_at")]
    ax.add_collection(LineCollection(over, colors="#e8e8f0", linewidths=1.2 * lw_scale,
                                     zorder=5))


def _section(ax, m, t, water) -> None:
    """Long section of a road tunnel: road, roof, ground, water and its bed, roads over."""
    pts = [(p[0], p[1]) for p in t.line]
    cum = _cum(pts)
    zs = [p[2] for p in t.line]
    roof = [z + t.clear_m + t.roof_m for z in zs]
    bot = [z - t.floor_m for z in zs]
    ax.fill_between(cum, bot, roof, color=KIND_COLOR.get(t.kind, "#cccccc"), alpha=0.25,
                    lw=0)
    ax.plot(cum, zs, color=KIND_COLOR.get(t.kind, "#cccccc"), lw=1.8, label="road")
    a_, b_ = _portal_s(t)
    rx = [x for x in cum if a_ - 0.01 <= x <= b_ + 0.01]
    ax.plot(rx, [r for x, r in zip(cum, roof) if a_ - 0.01 <= x <= b_ + 0.01], color=INK,
            lw=0.8, ls="--", label="roof")
    # ground and water along it
    line = LineString(pts)
    wet = [(LineString(pts).intersection(poly), cls) for poly, cls, _ in water
           if line.intersects(poly)]
    ax.axhline(0.0, color="#8a8f99", lw=0.8)
    for g, cls in wet:
        from .roads import G_lines

        for part in G_lines(g):
            if part.length < 1.0:
                continue
            s0 = line.project(Point(part.coords[0]))
            s1 = line.project(Point(part.coords[-1]))
            s0, s1 = min(s0, s1), max(s0, s1)
            ax.fill_between([s0, s1], [-TN.BED_M[cls]] * 2, [0.0, 0.0], color="#3a7ca5",
                            alpha=0.55, lw=0)
            ax.fill_between([s0, s1], [-TN.BED_M[cls] - TN.BED_COVER_M] * 2,
                            [-TN.BED_M[cls]] * 2, color="#7a6a55", alpha=0.6, lw=0)
    a, b = _portal_s(t)
    for x in (a, b):
        ax.axvline(x, color="#ffffff", lw=0.8)
    for s in m.road_segments:
        for p in s.attrs.get("over_tunnel_at", []):
            d = line.distance(Point(p))
            if d < 1.0:
                ax.plot([line.project(Point(p))], [0.6], marker="v", color="#e8e8f0", ms=5)
    ax.set_xlim(0, cum[-1])
    ax.set_ylim(min(min(bot) - 3.0, -12.0), 6.0)
    ax.tick_params(colors=MUTED, labelsize=6.5)
    ax.set_facecolor(PANEL)
    kind = t.kind.replace("_", " ")
    ax.set_title(f"{t.name or t.id}: {kind}, {cum[-1]:.0f} m (covered {b - a:.0f} m), "
                 f"down to {min(zs):.1f} m", color=INK, fontsize=8)


def render_tunnels(b, out, dpi: int = 140) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    map_w, side_w = 10.0, 6.5
    fig_h = max(map_w * H / W, 9.0) + 1.3
    fig = plt.figure(figsize=(map_w + side_w, fig_h), facecolor=BG, dpi=dpi)
    st = b.stats.get("tunnels", {})
    by = st.get("by_kind", {})
    fig.text(0.012, 1 - 0.28 / fig_h, f"{b.spec.name}: tunnels (M9)", color=INK,
             fontsize=14, fontweight="bold", va="top")
    summary = ", ".join(f"{r['count']} {k.replace('_', ' ')} ({r['km']} km)"
                        for k, r in by.items()) or "no tunnels"
    fig.text(0.012, 1 - 0.62 / fig_h,
             f"{summary}; {st.get('vents', 0)} ventilation buildings, "
             f"{st.get('over_tunnel_roads', 0)} roads over road tunnels; deepest road "
             f"{st.get('deepest_road_m', 0)} m, metro "
             f"{st.get('deepest_metro_m') if st.get('deepest_metro_m') is not None else '-'} m;"
             f" {'checks PASS' if b.passed else 'checks FAIL'}", color=MUTED, fontsize=9,
             va="top")
    mh = map_w * H / W
    ax = fig.add_axes([0.0, 0.2 / fig_h, map_w / (map_w + side_w), mh / fig_h])
    ax.set_facecolor(SEA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    _ground(ax, m)
    _roads(ax, m)
    _metro(ax, m)
    road_t = [t for t in m.tunnels if t.kind in ROAD]
    for t in road_t:
        _road_tunnel(ax, t)
    _vents(ax, m)
    _underpasses(ax, m, 3.0)
    handles = [Patch(facecolor=KIND_COLOR["immersed_tube"], label="immersed tube"),
               Patch(facecolor=KIND_COLOR["cut_and_cover"], label="cut-and-cover tunnel"),
               Patch(facecolor=OPEN_COLOR["cut_and_cover"], hatch="////",
                     edgecolor=KIND_COLOR["cut_and_cover"], label="open approach"),
               Line2D([], [], color="#ffffff", marker="s", lw=0, ms=4, mfc=BG,
                      label="portal"),
               Patch(facecolor=VENT, label="ventilation building"),
               Line2D([], [], color="#e8e8f0", lw=1.2, label="road over a tunnel"),
               Line2D([], [], color=CMAP(0.35), lw=2.0, label="metro tunnel (shade: depth)"),
               Patch(facecolor="#2f7bff", edgecolor="#ffffff", label="metro station box"),
               Line2D([], [], color=UNDER, lw=2.4, label="pedestrian underpass")]
    ax.legend(handles=handles, loc="lower left", fontsize=7.5, frameon=False, labelcolor=INK)
    side = map_w / (map_w + side_w)
    # the longest road tunnel at street scale
    ax2 = fig.add_axes([side + 0.01, 0.53, (side_w - 0.3) / (map_w + side_w), 0.39])
    ax2.set_facecolor(PANEL)
    ax2.set_aspect("equal")
    ax2.tick_params(colors=MUTED, labelsize=6)
    if road_t:
        t = max(road_t, key=lambda t: (t.attrs.get("length_m", 0.0), t.id))
        pts = np.asarray([p[:2] for p in t.line])
        cx = (pts[:, 0].min() + pts[:, 0].max()) / 2.0
        cy = (pts[:, 1].min() + pts[:, 1].max()) / 2.0
        R = max(float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1])), 250.0) / 2.0 + 60.0
        box = (cx - R, cy - R, cx + R, cy + R)
        _ground(ax2, m)
        foot = [np.asarray(G.from_model_poly(b_.footprint).exterior.coords)
                for b_ in m.buildings if b_.footprint is not None and
                box[0] - 50 < b_.footprint.exterior[0][0] < box[2] + 50 and
                box[1] - 50 < b_.footprint.exterior[0][1] < box[3] + 50]
        ax2.add_collection(PolyCollection(foot, facecolors=FOOT, edgecolors="none", zorder=1.5))
        _roads(ax2, m, 2.5, box)
        _metro(ax2, m, 4.0)
        for u in road_t:
            _road_tunnel(ax2, u, 2.0, label=False)
        _vents(ax2, m, 6.0, box)
        _underpasses(ax2, m, 5.0, box)
        for p in t.portals:
            ax2.text(p.position[0], p.position[1], f" portal {p.position[2]:g} m, open "
                     f"{p.open_m:.0f} m", color=INK, fontsize=6.5, path_effects=HALO,
                     zorder=8)
        ax2.set_xlim(box[0], box[2])
        ax2.set_ylim(box[1], box[3])
        ax2.set_title(f"{t.name or t.id}: {t.kind.replace('_', ' ')} at street scale",
                      color=INK, fontsize=9)
    else:
        ax2.text(0.5, 0.5, "no road tunnel", color=MUTED, ha="center", va="center",
                 transform=ax2.transAxes)
    # long sections: up to two road tunnels and the deepest metro line
    water = [(poly, cls, wid) for poly, cls, wid in TN.water_bodies(m)]
    secs = sorted(road_t, key=lambda t: (-t.attrs.get("length_m", 0.0), t.id))[:2]
    metro = [ln for ln in m.transit_lines if ln.mode == "metro"]
    n = len(secs) + (1 if metro else 0)
    if n == 0:
        ax3 = fig.add_axes([side + 0.05, 0.08, (side_w - 0.9) / (map_w + side_w), 0.36])
        ax3.set_facecolor(PANEL)
        ax3.text(0.5, 0.5, "nothing under the ground", color=MUTED, ha="center",
                 va="center", transform=ax3.transAxes)
    h = 0.40 / max(n, 1)
    for i, t in enumerate(secs):
        axs = fig.add_axes([side + 0.05, 0.06 + (n - 1 - i) * h + 0.035,
                            (side_w - 0.9) / (map_w + side_w), h - 0.05])
        _section(axs, m, t, water)
        if i == 0:
            axs.legend(loc="lower right", fontsize=6.5, frameon=False, labelcolor=INK)
    if metro:
        ln = min(metro, key=lambda ln: (min(p[2] for p in ln.path), ln.id))
        axm = fig.add_axes([side + 0.05, 0.06 + 0.035, (side_w - 0.9) / (map_w + side_w),
                            h - 0.05])
        pts = [(p[0], p[1]) for p in ln.path]
        cum = _cum(pts)
        zs = [p[2] for p in ln.path]
        axm.set_facecolor(PANEL)
        axm.fill_between(cum, [z - 1.0 for z in zs], [z + TN.METRO_H for z in zs],
                         color="#2f7bff", alpha=0.3, lw=0)
        axm.plot(cum, zs, color="#5aa0ff", lw=1.6)
        axm.axhline(0.0, color="#8a8f99", lw=0.8)
        line = LineString(pts)
        for sid in ln.station_ids:
            stt = next((x for x in m.stations if x.id == sid), None)
            if stt is not None:
                axm.axvline(line.project(Point(stt.position[:2])), color="#ffffff", lw=0.6,
                            ls=":")
        axm.set_xlim(0, cum[-1])
        axm.set_ylim(min(zs) - 6.0, 4.0)
        axm.tick_params(colors=MUTED, labelsize=6.5)
        axm.set_xlabel("along the line (m); dotted: stations", color=INK, fontsize=7)
        axm.set_title(f"metro {ln.name}: track down to {min(zs):g} m (lowered under "
                      f"{', '.join(ln.attrs.get('lowered_for', [])) or 'nothing'})",
                      color=INK, fontsize=8)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)
