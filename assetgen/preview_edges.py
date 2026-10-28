"""Edge preview (`preview_edges.png`): every facade edge of every building colored by its
class (scope 5.1.2), the whole city and four 300 m insets of contrasting districts, with
water, roads and open space underneath.

An edge is drawn in the class with the largest facade area in its regions; a hidden edge
(behind another mass of the same building) is drawn faint.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from . import planar as PL  # noqa: E402

COLORS = {
    "front": "#e6194b", "street": "#f58231", "alley": "#d4b106", "canal": "#2f6fdf",
    "plaza": "#911eb4", "park": "#2e9e3e", "courtyard": "#13b5b5", "atrium": "#006d6d",
    "party": "#111111", "blind": "#7d7d7d", "open": "#f2a6c8", "upper": "#8b5a2b",
    "hidden": "#e3e3e3",
}
ORDER = ("corporate_core", "old_town", "entertainment_market", "industrial_port",
         "midtown_mixed", "megablock_residential", "residential_heights", "transit_hub",
         "research_campus", "spaceport")
BG, WATER, ROAD, OPEN, FOOT = "#fbfaf7", "#cfe0f3", "#d4d6db", "#e3efd9", "#f0ede6"
HALF_M = 150.0


def _segments(briefs: dict):
    """Per class: the world segments of the edges of that class."""
    out: dict[str, list] = {c: [] for c in COLORS}
    for br in briefs.values():
        ox, oy = br["origin"]
        for e in br["edges"]:
            a, b = e["a"], e["b"]
            out[e["class"]].append(((a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy)))
    return out


def _insets(model, briefs: dict, n: int = 4) -> list[tuple[str, tuple[float, float]]]:
    """(district name, center) for up to n districts of different archetypes: the middle
    building (by origin, sorted) of the district's busiest 300 m cell."""
    by_d: dict[str, list] = {}
    for br in briefs.values():
        d = br["district"]
        if d is not None:
            by_d.setdefault(d["id"], []).append(tuple(br["origin"]))
    arch = {d.id: d for d in model.districts}
    out = []
    used = set()
    for a in ORDER:
        if len(out) >= n:
            break
        cands = sorted((d for d in model.districts if d.archetype == a and d.id in by_d),
                       key=lambda d: (-len(by_d[d.id]), d.id))
        if not cands or a in used:
            continue
        d = cands[0]
        cells: dict[tuple[int, int], list] = {}
        for x, y in by_d[d.id]:
            cells.setdefault((int(x // (2 * HALF_M)), int(y // (2 * HALF_M))), []).append((x, y))
        cell = min(cells, key=lambda c: (-len(cells[c]), c))
        pts = sorted(cells[cell])
        out.append((arch[d.id].name, pts[len(pts) // 2]))
        used.add(a)
    return out


def _base(ax, model, box=None) -> None:
    def keep(pts):
        if box is None:
            return True
        x0, y0, x1, y1 = PL.bbox(pts)
        return not (x1 < box[0] or x0 > box[2] or y1 < box[1] or y0 > box[3])

    polys = []
    for coll in (model.waterways, model.rivers, model.channels):
        for w in coll:
            polys.append(PL.ring(w.polygon.exterior))
    for s in model.seas:
        for pg in s.polygons:
            polys.append(PL.ring(pg.exterior))
    ax.add_collection(PolyCollection([p for p in polys if keep(p)], facecolors=WATER,
                                     edgecolors="none", zorder=1))
    opens = [PL.ring(o.polygon.exterior) for o in model.open_spaces if o.z_m <= 0.5]
    ax.add_collection(PolyCollection([p for p in opens if keep(p)], facecolors=OPEN,
                                     edgecolors="none", zorder=2))
    lines, widths = [], []
    for s in model.road_segments:
        if s.tunnel or len(s.centerline) < 2 or not keep(s.centerline):
            continue
        lines.append(s.centerline)
        widths.append(s.width_m)
    scale = 1.0 if box is None else 1.0
    ax.add_collection(LineCollection(lines, colors=ROAD, zorder=3, capstyle="butt",
                                     linewidths=[w * scale * (0.05 if box is None else 0.45)
                                                 for w in widths]))
    foots = []
    for b in model.buildings:
        for mm in b.masses:
            if mm.z0_m <= 0.5:
                pts = PL.ring(mm.footprint.exterior)
                if keep(pts):
                    foots.append(pts)
    ax.add_collection(PolyCollection(foots, facecolors=FOOT, edgecolors="none", zorder=4))


def render(model, briefs: dict, out_path, dpi: int = 110) -> None:
    segs = _segments(briefs)
    insets = _insets(model, briefs)
    fig = plt.figure(figsize=(22, 13), facecolor=BG)
    big = fig.add_axes([0.01, 0.06, 0.52, 0.88])
    x0, y0, x1, y1 = model.bounds
    _draw(big, model, segs, None, 0.35)
    big.set_xlim(x0, x1)
    big.set_ylim(y0, y1)
    big.set_title(f"{model.name}: facade edges by class", fontsize=15, loc="left")
    for i, (name, (cx, cy)) in enumerate(insets):
        r, c = divmod(i, 2)
        ax = fig.add_axes([0.545 + c * 0.228, 0.50 - r * 0.44, 0.215, 0.42])
        box = (cx - HALF_M, cy - HALF_M, cx + HALF_M, cy + HALF_M)
        _draw(ax, model, segs, box, 1.6)
        ax.set_xlim(box[0], box[2])
        ax.set_ylim(box[1], box[3])
        ax.set_title(f"{name} ({2 * HALF_M:.0f} m)", fontsize=11, loc="left")
    counts = {c: len(v) for c, v in segs.items()}
    handles = [Line2D([0], [0], color=COLORS[c], lw=4,
                      label=f"{c} ({counts[c]})") for c in COLORS if counts[c]]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=10,
               frameon=False)
    fig.savefig(out_path, dpi=dpi, facecolor=BG)
    plt.close(fig)


def _draw(ax, model, segs: dict, box, lw: float) -> None:
    ax.set_aspect("equal")
    ax.set_facecolor(BG)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    _base(ax, model, box)
    for z, cls in enumerate(COLORS):
        lines = segs[cls]
        if box is not None:
            lines = [s for s in lines if not (max(s[0][0], s[1][0]) < box[0] or
                                              min(s[0][0], s[1][0]) > box[2] or
                                              max(s[0][1], s[1][1]) < box[1] or
                                              min(s[0][1], s[1][1]) > box[3])]
        if not lines:
            continue
        w = lw * (0.5 if cls == "hidden" else 1.0)
        ax.add_collection(LineCollection(lines, colors=COLORS[cls], linewidths=w,
                                         zorder=10 if cls == "hidden" else 11))
