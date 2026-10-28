"""M13 preview: `preview_terrain.png`, the ground. Left, the finished ground as a hillshade
with 5 m contours (10 m bold), the water at its levels, every road colored by its grade on
the ground (grade line plus z), retaining walls (red on cuts, orange on fills), bored tunnels,
the building footprints on their plinths. Right, a street-scale inset of the steepest built
slope and the long sections of the longest primary roads (grade line, natural ground, road
surface, bores). Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.colors import LightSource, Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from . import geom as G  # noqa: E402
from . import terrain as TR  # noqa: E402
from .schematic import BG, INK, MUTED, SEA  # noqa: E402

HALO = [pe.withStroke(linewidth=2.5, foreground=BG)]
PANEL = "#20242c"
CUT = "#ff5a5a"
FILL = "#ffb347"
BORE = "#22d3ee"
GRADE_CMAP = plt.get_cmap("turbo")


def _cmap():
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list("ground", ["#2f4a3a", "#56704d", "#8d8a5a",
                                                        "#a68a63", "#c9b79a", "#efe6d6"])


def _road_grades(m):
    """(segments [(xy, xy)], grade) on the ground for every road piece."""
    segs, vals = [], []
    for s in m.road_segments:
        if not s.ground:
            continue
        line = [tuple(p) for p in s.centerline]
        cum = TR._cum(line)
        zp = [(p.s, p.z) for p in s.z_profile]
        st = [(p.s, p.z) for p in s.ground]
        for (s0, g0), (s1, g1) in zip(st, st[1:]):
            if s1 - s0 < 0.5:
                continue
            a0 = g0 + TR.z_on(zp, s0)
            a1 = g1 + TR.z_on(zp, s1)
            segs.append([TR.point_at(line, cum, s0), TR.point_at(line, cum, s1)])
            vals.append(abs(a1 - a0) / (s1 - s0))
    return segs, np.array(vals)


def _shade(ax, t, arr, extent, vmax):
    ls = LightSource(azdeg=315, altdeg=40)
    rgb = ls.shade(arr, cmap=_cmap(), vert_exag=2.5, blend_mode="soft", vmin=0.0, vmax=vmax)
    ax.imshow(rgb, origin="lower", extent=extent, interpolation="bilinear", zorder=0)


def _water(ax, m):
    polys = []
    for s in m.seas:
        polys += [G.from_model_poly(p) for p in s.polygons]
    for e in list(m.rivers) + list(m.channels) + list(m.waterways):
        polys.append(G.from_model_poly(e.polygon))
    for p in polys:
        for part in G.parts(p):
            ax.fill(*part.exterior.xy, color=SEA, zorder=2, lw=0)


def render_terrain(b, out) -> None:
    m = b.model
    t = m.terrain
    nat = TR.Field.from_rows(t, t.natural)
    fin = TR.Field.from_rows(t, t.ground) if t.ground else nat
    x0, y0 = t.x0, t.y0
    extent = (x0, x0 + t.cell_m * (t.nx - 1), y0, y0 + t.cell_m * (t.ny - 1))
    vmax = max(float(fin.arr.max()), 10.0)
    fig = plt.figure(figsize=(22, 13), facecolor=BG)
    ax = fig.add_axes([0.01, 0.04, 0.58, 0.86])
    ax.set_facecolor(BG)
    _shade(ax, t, fin.arr, extent, vmax)
    X, Y = fin.grid()
    ax.contour(X, Y, fin.arr, levels=np.arange(5, vmax + 5, 5), colors="#1b1f26",
               linewidths=0.25, alpha=0.6, zorder=1)
    ax.contour(X, Y, fin.arr, levels=np.arange(10, vmax + 10, 10), colors="#1b1f26",
               linewidths=0.6, alpha=0.8, zorder=1)
    _water(ax, m)
    foot = [np.asarray(b_.footprint.exterior) for b_ in m.buildings if b_.footprint is not None]
    if foot:
        ax.add_collection(PolyCollection(foot, facecolor="#11141a", edgecolor="none",
                                         alpha=0.55, zorder=3))
    segs, vals = _road_grades(m)
    norm = Normalize(0.0, 0.15)
    if segs:
        lc = LineCollection(segs, colors=GRADE_CMAP(norm(vals)), linewidths=1.3, zorder=4)
        ax.add_collection(lc)
    walls = [s for s in m.structures if s.kind == "retaining_wall"]
    for w in walls:
        pts = np.asarray([p[:2] for p in w.line])
        ax.plot(pts[:, 0], pts[:, 1], color=CUT if w.attrs.get("cut") else FILL,
                lw=0.6 + min(w.z1_m, 12.0) * 0.12, zorder=5, solid_capstyle="butt")
    bores = [u for u in m.tunnels if u.kind == "bored"]
    for u in bores:
        pts = np.asarray([p[:2] for p in u.line])
        ax.plot(pts[:, 0], pts[:, 1], color=BORE, lw=3.2, ls=(0, (2, 1)), zorder=6)
        mid = pts[len(pts) // 2]
        ax.text(mid[0], mid[1], u.name or u.id, color=BORE, fontsize=8, zorder=7,
                path_effects=HALO, ha="center", va="bottom")
    for d in m.districts:
        p = G.from_model_poly(d.polygon)
        c = p.point_on_surface()
        ax.text(c.x, c.y, d.name, color=INK, fontsize=10, ha="center", zorder=8,
                path_effects=HALO, weight="bold")
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.axis("off")
    st = t.stats
    fig.text(0.01, 0.965, f"{m.name}: terrain (M13)", color=INK, fontsize=18, weight="bold")
    fig.text(0.01, 0.935,
             f"ground {float(nat.arr.min()):.0f} to {float(nat.arr.max()):.0f} m; "
             f"cuts to {st.get('max_cut_m', 0):.1f} m, fills to {st.get('max_fill_m', 0):.1f} m; "
             f"{len(walls)} retaining walls ({st.get('wall_km', 0)} km); {len(bores)} bored "
             f"tunnels; roads colored by grade on the ground (0 to 15%)", color=MUTED,
             fontsize=11)
    cax = fig.add_axes([0.02, 0.06, 0.18, 0.012])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=GRADE_CMAP), cax=cax,
                      orientation="horizontal")
    cb.set_ticks([0, 0.03, 0.06, 0.09, 0.12, 0.15])
    cb.set_ticklabels(["0", "3%", "6%", "9%", "12%", "15%"])
    cb.ax.tick_params(colors=INK, labelsize=8)
    cb.outline.set_edgecolor(MUTED)
    ax.legend(handles=[Line2D([], [], color=CUT, lw=2, label="retaining wall, cut"),
                       Line2D([], [], color=FILL, lw=2, label="retaining wall, fill"),
                       Line2D([], [], color=BORE, lw=3, ls="--", label="bored tunnel")],
              loc="lower right", facecolor=PANEL, edgecolor=MUTED, labelcolor=INK,
              fontsize=9)
    _inset(fig, m, fin, nat, vmax)
    _sections(fig, m, nat)
    fig.savefig(out, dpi=110, facecolor=BG)
    plt.close(fig)


def _inset(fig, m, fin, nat, vmax):
    """The 400 m square around the building on the steepest ground."""
    ax = fig.add_axes([0.61, 0.47, 0.37, 0.45])
    ax.set_facecolor(PANEL)
    best = None
    for b in m.buildings:
        if b.base_m is None or b.plinth_m is None:
            continue
        h = b.base_m - b.plinth_m
        if best is None or h > best[0]:
            best = (h, b)
    if best is None:
        segs, vals = _road_grades(m)
        if not len(vals):
            ax.axis("off")
            return
        k = int(np.argmax(vals))
        cx, cy = (segs[k][0][0] + segs[k][1][0]) / 2, (segs[k][0][1] + segs[k][1][1]) / 2
    else:
        c = G.from_model_poly(best[1].footprint).centroid
        cx, cy = c.x, c.y
    r = 200.0
    X, Y = fin.grid()
    js, iss = TR._window(fin, cx - r, cy - r, cx + r, cy + r)
    sub = fin.arr[js, iss]
    ext = (float(X[js, iss].min()), float(X[js, iss].max()), float(Y[js, iss].min()),
           float(Y[js, iss].max()))
    _shade(ax, None, sub, ext, vmax)
    ax.contour(X[js, iss], Y[js, iss], sub, levels=np.arange(1, vmax + 1, 1),
               colors="#1b1f26", linewidths=0.3, alpha=0.6)
    _water(ax, m)
    for s in m.road_segments:
        pts = np.asarray(s.centerline)
        if np.min(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)) > 2 * r:
            continue
        ax.plot(pts[:, 0], pts[:, 1], color="#cfd5df", lw=max(0.5, s.width_m * 0.18),
                alpha=0.35, solid_capstyle="butt")
    for b in m.buildings:
        if b.footprint is None:
            continue
        p = G.from_model_poly(b.footprint)
        if abs(p.centroid.x - cx) > r * 0.95 or abs(p.centroid.y - cy) > r * 0.95:
            continue
        step = (b.base_m or 0) - (b.plinth_m or 0)
        ax.fill(*p.exterior.xy, color="#11141a", alpha=0.8, lw=0.4, ec=MUTED)
        if step > 0.5:
            ax.text(p.centroid.x, p.centroid.y, f"{step:.0f}", color=FILL, fontsize=6,
                    ha="center", va="center")
    for w in m.structures:
        if w.kind != "retaining_wall":
            continue
        pts = np.asarray([p[:2] for p in w.line])
        if np.min(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)) > 2 * r:
            continue
        ax.plot(pts[:, 0], pts[:, 1], color=CUT if w.attrs.get("cut") else FILL, lw=1.6)
    ax.set_xlim(cx - r, cx + r)
    ax.set_ylim(cy - r, cy + r)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("street scale, 400 m: 1 m contours, walls, plinths (m over the ground)",
                 color=INK, fontsize=11)


def _sections(fig, m, nat):
    """Long sections of the two longest primary road chains."""
    prim = [s for s in m.road_segments if s.road_class in ("highway", "avenue") and s.ground]
    prim.sort(key=lambda s: (-s.ground[-1].s, s.id))
    for k, s in enumerate(prim[:2]):
        ax = fig.add_axes([0.63, 0.25 - k * 0.19, 0.35, 0.14])
        ax.set_facecolor(PANEL)
        line = [tuple(p) for p in s.centerline]
        cum = TR._cum(line)
        ss = np.linspace(0.0, cum[-1], 400)
        nz = [nat.at(*TR.point_at(line, cum, v)) for v in ss]
        st = [(p.s, p.z) for p in s.ground]
        zp = [(p.s, p.z) for p in s.z_profile]
        gz = [TR.z_on(st, v) for v in ss]
        rz = [g + TR.z_on(zp, v) for g, v in zip(gz, ss)]
        ax.fill_between(ss, min(nz + gz) - 5, nz, color="#56704d", alpha=0.5, lw=0)
        ax.plot(ss, nz, color="#a3c48a", lw=1, label="natural ground")
        ax.plot(ss, gz, color=INK, lw=1, ls="--", label="grade line")
        ax.plot(ss, rz, color="#ffd27a", lw=1.6, label="road surface")
        for u in m.tunnels:
            if u.kind == "bored" and s.id in u.segment_ids:
                a, b = u.attrs.get("s0", 0), u.attrs.get("s1", 0)
                ax.axvspan(a, b, color=BORE, alpha=0.18)
        ax.tick_params(colors=MUTED, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(MUTED)
        ax.set_title(f"{s.name or s.id} ({s.road_class}): long section, "
                     f"{cum[-1]:.0f} m", color=INK, fontsize=10)
        if k == 0:
            ax.legend(loc="upper right", fontsize=7, facecolor=PANEL, edgecolor=MUTED,
                      labelcolor=INK)
