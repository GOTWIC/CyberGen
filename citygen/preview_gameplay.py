"""M11 preview: `preview_gameplay.png`, the gameplay layer in six panels. Territories in their
faction's color (contested turfs hatched) with every point of interest, taxi stand and
fast-travel point; the wealth and danger fields; evening traffic and late-night crowds per
street; and a 300 m street-level inset at the busiest cluster of points of interest with their
names, doors, walkway links and curb points, parking, taxi stands and the sign and ad slots on
the facades. Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
import shapely.ops  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from . import geom as G  # noqa: E402
from .preview_massing import _ground  # noqa: E402
from .schematic import BG, INK, MUTED, SEA  # noqa: E402

HALO = [pe.withStroke(linewidth=2.2, foreground=BG)]
POI_COLORS = {"bar": "#ff4fd8", "clinic": "#4fe0ff", "vendor": "#ffd24f", "fixer": "#ffffff",
              "hideout": "#ff3b30", "apartment": "#7ad94f"}
POI_MARK = {"bar": "o", "clinic": "P", "vendor": "s", "fixer": "*", "hideout": "X",
            "apartment": "^"}
SLOT_COLORS = {"shop_sign": "#ff7ad9", "billboard": "#ffe27a", "holo_ad": "#5ef2ff",
               "neon": "#b06bff"}
ROAD = "#3b404b"
POLICE_C = "#5b8cff"
HALF = 150.0


def _frame(ax, m, title: str) -> None:
    x0, y0, x1, y1 = m.bounds
    ax.set_facecolor(SEA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=4)


def _roads(ax, m, color=ROAD, lw=0.35, z=2.0) -> None:
    lines = [np.asarray(s.centerline) for s in m.road_segments
             if s.road_class in ("highway", "avenue", "street")]
    ax.add_collection(LineCollection(lines, colors=color, linewidths=lw, zorder=z))


def _field(ax, m, kind: str, cmap) -> None:
    f = next((x for x in m.fields if x.kind == kind), None)
    if f is None:
        return
    a = np.asarray(f.values, dtype=float).reshape(f.ny, f.nx)
    land = np.zeros_like(a, dtype=bool)
    xs = f.origin[0] + (np.arange(f.nx) + 0.5) * f.cell_m
    ys = f.origin[1] + (np.arange(f.ny) + 0.5) * f.cell_m
    X, Y = np.meshgrid(xs, ys)
    for d in m.districts:
        land |= shapely.contains_xy(G.from_model_poly(d.polygon), X, Y)
    a = np.ma.masked_where(~land, a)
    ax.imshow(a, origin="lower", cmap=cmap, vmin=0.0, vmax=1.0, zorder=1.5,
              extent=(f.origin[0], f.origin[0] + f.nx * f.cell_m, f.origin[1],
                      f.origin[1] + f.ny * f.cell_m), interpolation="bilinear", alpha=0.9)


def _busiest(m) -> tuple[float, float]:
    pts = np.array([p.position[:2] for p in m.pois if p.kind in ("bar", "vendor", "clinic")]
                   or [[0.0, 0.0]], dtype=float)
    best = None
    for x, y in pts:
        n = int(((np.abs(pts[:, 0] - x) < HALF * 0.8) & (np.abs(pts[:, 1] - y) < HALF * 0.8))
                .sum())
        key = (n, -round(x, 2), -round(y, 2))
        if best is None or key > best[0]:
            best = (key, (float(x), float(y)))
    return best[1]


def _inset(ax, m) -> None:
    cx, cy = _busiest(m)
    x0, y0, x1, y1 = cx - HALF, cy - HALF, cx + HALF, cy + HALF
    ax.set_facecolor("#11151d")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("street level, 300 m: doors, walk links, curbs, parking, taxis, sign slots",
                 color=INK, fontsize=11, loc="left", pad=4)

    def near(p, pad=10.0):
        return x0 - pad <= p[0] <= x1 + pad and y0 - pad <= p[1] <= y1 + pad
    side = [np.asarray(w.line)[:, :2] for w in m.walkways
            if any(near(p) for p in w.line) and all(abs(p[2]) < 1e-9 for p in w.line)]
    ax.add_collection(LineCollection(side, colors="#2e3542", linewidths=1.6, zorder=1))
    lanes = [np.asarray(ln.centerline)[:, :2] for ln in m.lanes if ln.kind == "lane" and
             any(near(p) for p in ln.centerline)]
    ax.add_collection(LineCollection(lanes, colors="#404857", linewidths=0.7, zorder=1.2))
    foot = [np.asarray(b.footprint.exterior) for b in m.buildings
            if b.footprint is not None and any(near(p, 40) for p in b.footprint.exterior)]
    ax.add_collection(PolyCollection(foot, facecolors="#262c38", edgecolors="#4a5262",
                                     linewidths=0.5, zorder=2))
    lots = [np.asarray(p.polygon.exterior) for p in m.parking
            if p.kind == "lot" and p.polygon is not None and
            any(near(q) for q in p.polygon.exterior)]
    ax.add_collection(PolyCollection(lots, facecolors="#3b5bdb55", edgecolors="#5b7cff",
                                     linewidths=0.8, zorder=2.2))
    curb = [np.asarray(p.line) for p in m.parking if p.kind == "street" and
            any(near(q) for q in p.line)]
    ax.add_collection(LineCollection(curb, colors="#5b7cff", linewidths=0.6,
                                     linestyles=(0, (2, 2)), zorder=1.3))
    for p in m.parking:
        if p.kind == "garage" and p.polygon is not None and \
                any(near(q) for q in p.polygon.exterior):
            ax.add_collection(PolyCollection([np.asarray(p.polygon.exterior)],
                                             facecolors="none", edgecolors="#5b7cff",
                                             linewidths=1.2, zorder=2.3))
            e = p.entrances[0].position if p.entrances else p.polygon.exterior[0]
            ax.text(e[0], e[1], "P", color="#8fa8ff", fontsize=8, weight="bold",
                    ha="center", va="center", zorder=6, path_effects=HALO)
    # sign slots as ticks on the facades
    for s in m.sign_slots:
        if not near(s.position, 0):
            continue
        col = SLOT_COLORS.get(s.kind, INK)
        a = np.radians(s.yaw_deg)
        tx, ty = -np.sin(a), np.cos(a)
        w = max(s.width_m, 1.0) / 2.0
        x, y = s.position[0], s.position[1]
        ax.plot([x - tx * w, x + tx * w], [y - ty * w, y + ty * w], color=col,
                lw=2.4 if s.kind != "shop_sign" else 1.2, zorder=3.5, solid_capstyle="butt")
    for p in m.pois:
        x, y = p.position[:2]
        if not near((x, y), 0):
            continue
        col = POI_COLORS[p.kind]
        for a in p.entrances:
            ax.plot([a.position[0], a.curb[0]], [a.position[1], a.curb[1]], color=col,
                    lw=0.6, ls=":", zorder=3.6)
            ax.plot([a.curb[0]], [a.curb[1]], marker="o", ms=2.5, mfc="none", mec=col,
                    zorder=3.7)
        ax.plot([x], [y], marker=POI_MARK[p.kind], ms=8 if p.kind == "fixer" else 6, color=col,
                mec=BG, mew=0.6, zorder=5)
        if p.kind != "fixer":
            ax.text(x + 3, y + 3, p.name, color=col, fontsize=6.5, zorder=6,
                    path_effects=HALO)
    for t in m.travel_points:
        x, y = t.position
        if near((x, y), 0):
            ax.plot([x], [y], marker="D" if t.kind == "taxi_stand" else "*",
                    ms=7 if t.kind == "taxi_stand" else 11,
                    color="#ffcc00" if t.kind == "taxi_stand" else "#00ffa6", mec=BG,
                    zorder=5.5)
            ax.text(x + 3, y - 6, t.name, color=INK, fontsize=6.5, zorder=6, path_effects=HALO)
    ax.add_patch(plt.Rectangle((x0 + 10, y0 + 10), 50, 2.5, color=INK, zorder=7))
    ax.text(x0 + 35, y0 + 16, "50 m", color=INK, fontsize=7, ha="center", zorder=7)


def render_gameplay(b, out, dpi: int = 110) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    pw = 7.0
    ph = pw * H / W
    fig = plt.figure(figsize=(pw * 3, ph * 2 + 1.4), facecolor=BG, dpi=dpi)
    fh = ph * 2 + 1.4
    fig.text(0.01, 1 - 0.35 / fh, f"{m.name}: gameplay layer (M11)", color=INK, fontsize=16,
             weight="bold", va="top")
    gs = b.stats.get("gameplay", {}) if getattr(b, "stats", None) else {}
    if gs:
        fig.text(0.01, 1 - 0.85 / fh,
                 f"{gs['pois']} points of interest, {gs['factions']} factions, "
                 f"{gs['territories']} territories ({gs['contested']} contested), "
                 f"{gs['taxi_stands']} taxi stands, {gs['fast_travel']} fast-travel points, "
                 f"{gs['parking_capacity']} parking spaces, "
                 f"{sum(gs['sign_slots'].values())} sign slots",
                 color=MUTED, fontsize=10, va="top")
    axes = []
    for r in range(2):
        for k in range(3):
            axes.append(fig.add_axes([k / 3 + 0.004, (1 - r) * ph / fh + 0.004,
                                      1 / 3 - 0.008, ph / fh - 0.03]))
    P = G.from_model_poly
    fac = {f.id: f for f in m.factions}

    # 1: territories and places
    ax = axes[0]
    _frame(ax, m, "territories, points of interest, taxis and fast travel")
    _ground(ax, m)
    for z in m.zones:
        if z.kind != "territory":
            continue
        col = fac[z.faction_id].color if z.faction_id in fac else MUTED
        polys = [np.asarray(p.exterior) for p in z.polygons]
        ax.add_collection(PolyCollection(polys, facecolors=col, alpha=0.28,
                                         edgecolors="none", zorder=1.6,
                                         hatch="///" if z.attrs.get("contested") else None))
        ax.add_collection(PolyCollection(polys, facecolors="none", edgecolors=col,
                                         linewidths=0.9, zorder=1.7))
    _roads(ax, m)
    for kind, col in POI_COLORS.items():
        pts = np.array([p.position[:2] for p in m.pois if p.kind == kind] or
                       np.zeros((0, 2)))
        if len(pts):
            ax.scatter(pts[:, 0], pts[:, 1], s=14 if kind != "fixer" else 60,
                       marker=POI_MARK[kind], c=col, edgecolors=BG, linewidths=0.4, zorder=5)
    for t in m.travel_points:
        x, y = t.position
        if t.kind == "fast_travel":
            ax.scatter([x], [y], s=110, marker="*", c="#00ffa6", edgecolors=BG, zorder=6)
            ax.text(x + 25, y + 20, t.name, color="#00ffa6", fontsize=6, zorder=7,
                    path_effects=HALO)
        else:
            ax.scatter([x], [y], s=16, marker="D", c="#ffcc00", edgecolors=BG, zorder=5.5)
    for f in m.factions:
        if f.kind == "police" or not f.zone_ids:
            continue
        zs = [z for z in m.zones if z.id in set(f.zone_ids) and not z.attrs.get("contested")]
        if not zs:
            continue
        poly = max((P(p) for z in zs for p in z.polygons), key=lambda g: g.area)
        lab = shapely.ops.polylabel(poly, tolerance=10.0)
        x, y = lab.x, lab.y
        ax.text(x, y, f.name, color=f.color, fontsize=8, weight="bold", ha="center",
                zorder=8, path_effects=HALO)
    handles = [Line2D([], [], ls="", marker=POI_MARK[k], color=c, label=k)
               for k, c in POI_COLORS.items()] + [
        Line2D([], [], ls="", marker="D", color="#ffcc00", label="taxi stand"),
        Line2D([], [], ls="", marker="*", color="#00ffa6", ms=10, label="fast travel")]
    fig.legend(handles=handles, loc="upper right", fontsize=8, facecolor=BG, edgecolor=MUTED,
               labelcolor=INK, framealpha=0.85, ncol=4, bbox_to_anchor=(0.995, 0.995))

    # 2, 3: fields
    wealth = LinearSegmentedColormap.from_list("w", ["#1b1f2a", "#3f6f5a", "#d8c56a",
                                                     "#fff3c4"])
    danger = LinearSegmentedColormap.from_list("d", ["#16202e", "#5a3a6b", "#d2453a",
                                                     "#ffb36b"])
    for ax, kind, cmap in ((axes[1], "wealth", wealth), (axes[2], "danger", danger)):
        _frame(ax, m, f"{kind} field (32 m cells; police presence lowers danger)"
               if kind == "danger" else "wealth field (32 m cells)")
        _ground(ax, m)
        _field(ax, m, kind, cmap)
        _roads(ax, m, color="#0c0f16", lw=0.3, z=2)
        if kind == "danger":
            hid = np.array([p.position[:2] for p in m.pois if p.kind == "hideout"] or
                           np.zeros((0, 2)))
            if len(hid):
                ax.scatter(hid[:, 0], hid[:, 1], s=30, marker="X", c="#ff3b30",
                           edgecolors=BG, zorder=5)
            pre = [z.attrs.get("station_building_id") for z in m.zones if z.kind == "police"]
            bld = {x.id: x for x in m.buildings}
            pts = np.array([bld[i].entrances[0].position for i in pre if i in bld] or
                           np.zeros((0, 2)))
            if len(pts):
                ax.scatter(pts[:, 0], pts[:, 1], s=40, marker="p", c=POLICE_C,
                           edgecolors=BG, zorder=5)

    # 4, 5: densities
    seg = {s.id: s for s in m.road_segments}
    for ax, band, key, cmap, title in (
            (axes[3], 3, "traffic_vph", "plasma", "traffic, evening 16-20 (vehicles per hour)"),
            (axes[4], 4, "crowd_per_100m", "viridis",
             "crowds, late 20-24 (pedestrians per 100 m)")):
        _frame(ax, m, title)
        _ground(ax, m)
        rows = [(seg[d.segment_id], getattr(d, key)[band]) for d in m.densities
                if d.segment_id in seg]
        vals = np.array([v for _, v in rows] or [0.0])
        top = max(float(np.percentile(vals, 98)), 1.0)
        lines = [np.asarray(s.centerline) for s, _ in rows]
        lc = LineCollection(lines, cmap=cmap, linewidths=[0.3 + 2.4 * min(v / top, 1.0)
                                                          for _, v in rows], zorder=3)
        lc.set_array(np.minimum(vals / top, 1.0))
        lc.set_clim(0.0, 1.0)
        ax.add_collection(lc)
        ax.text(x0 + 0.02 * W, y0 + 0.03 * H, f"full color at {top:,.0f}", color=MUTED,
                fontsize=8, zorder=8)
    # 6: street level
    _inset(axes[5], m)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)
