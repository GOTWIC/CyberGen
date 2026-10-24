"""Detail preview of a built city (`preview_detail.png`): four zoomed insets (400 m square) of
contrasting districts, drawn to scale: water and quays, blocks and lots, open space, the
asphalt of every road and junction, sidewalks, medians, lane markings, crosswalks,
footbridges and promenades, with street, place and district labels.

Insets: one district per archetype, in the order corporate core, old town, entertainment
market, industrial port, midtown, residential heights, transit hub, megablocks, research
campus, spaceport; each centered on the local junction nearest the middle of the district.
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from shapely.geometry import LineString, Point, box  # noqa: E402

from . import geom as G  # noqa: E402
from .preview import CANAL, OPEN_COLORS, QUAY, SEPARATION  # noqa: E402
from .schematic import ARCHETYPE_COLORS, BG, INK, LAND, MUTED, RIVER, SEA  # noqa: E402

ORDER = ("corporate_core", "old_town", "entertainment_market", "industrial_port",
         "midtown_mixed", "residential_heights", "transit_hub", "megablock_residential",
         "research_campus", "spaceport")
HALF_M = 200.0
ASPHALT = "#3b404b"
HIGHWAY_ASPHALT = "#4a4436"
SIDEWALK = "#a7adb8"
CURB = "#d9dde4"
MEDIAN = "#4f8a57"
MARK = "#f4f1e6"
MARK_YELLOW = "#f2c14e"
FOOT = "#c8a77a"
PROMENADE = "#b7c3b0"
ALLEY = "#5f6573"
LOT_EDGE = "#11151d"
HALO = [pe.withStroke(linewidth=2.5, foreground=BG)]


def pick_insets(m, n: int = 4) -> list[tuple[str, tuple[float, float]]]:
    """(district id, center) for up to n districts of different archetypes."""
    by_arch: dict = {}
    for d in m.districts:
        by_arch.setdefault(d.archetype, []).append(d)
    pos = {nd.id: nd.position[:2] for nd in m.road_nodes}
    deg: dict = {}
    local: set = set()
    for s in m.road_segments:
        for x in (s.start, s.end):
            deg[x] = deg.get(x, 0) + 1
            if s.road_class not in ("highway", "avenue"):
                local.add(x)
    out = []
    for arch in ORDER:
        if arch not in by_arch or len(out) >= n:
            continue
        d = max(by_arch[arch], key=lambda d: (G.area1(G.from_model_poly(d.polygon)), d.id))
        poly = G.from_model_poly(d.polygon)
        try:
            c = shapely.ops.polylabel(poly, tolerance=10.0)
        except Exception:  # noqa: BLE001
            c = poly.representative_point()
        cands = sorted(nid for nid in local if deg.get(nid, 0) >= 3 and
                       poly.contains(Point(pos[nid])))
        lots = np.array([G.centroid(G.from_model_poly(lt.polygon)) for lt in m.lots
                         if lt.district_id == d.id] or [(c.x, c.y)])
        if cands:
            # the busiest spot: most lots within the inset, then nearest the middle
            def score(k):
                x, y = pos[k]
                inside = int(((np.abs(lots[:, 0] - x) < 0.8 * HALF_M) &
                              (np.abs(lots[:, 1] - y) < 0.8 * HALF_M)).sum())
                return (-inside, round((x - c.x) ** 2 + (y - c.y) ** 2, 2), k)
            nid = min(cands[::max(1, len(cands) // 150)], key=score)
            center = pos[nid]
        else:
            center = (c.x, c.y)
        out.append((d.id, (float(center[0]), float(center[1]))))
    return out


def _clip_polys(geoms, win) -> list:
    out = []
    for g in geoms:
        if g.is_empty or G.apart(g, win, 1.0):
            continue
        for p in G.parts(g.intersection(win)):
            out.append(p)
    return out


def _poly_paths(polys):
    """Polygons with holes as one PolyCollection each (exterior and holes as separate paths
    would fill the holes); holes are rare here, so they are drawn on top in the background
    color by the caller when needed."""
    return [list(p.exterior.coords) for p in polys]


def _strip(line: LineString, a: float, b: float):
    """Polygon between offsets a and b (meters, + left) along a line."""
    if b <= a:
        return None
    la = shapely.offset_curve(line, a, join_style="mitre", mitre_limit=2.0) if a else line
    lb = shapely.offset_curve(line, b, join_style="mitre", mitre_limit=2.0)
    if la.is_empty or lb.is_empty or la.geom_type != "LineString" or \
            lb.geom_type != "LineString":
        mid = (a + b) / 2
        return line.offset_curve(mid).buffer((b - a) / 2, cap_style="flat") if mid else \
            line.buffer((b - a) / 2, cap_style="flat")
    coords = list(la.coords) + list(lb.coords)[::-1]
    return shapely.make_valid(shapely.Polygon(coords))


def draw_inset(ax, m, did: str, center, idx) -> None:
    cx, cy = center
    win = box(cx - HALF_M, cy - HALF_M, cx + HALF_M, cy + HALF_M)
    ax.set_xlim(cx - HALF_M, cx + HALF_M)
    ax.set_ylim(cy - HALF_M, cy + HALF_M)
    ax.set_aspect("equal")
    ax.set_facecolor(SEA)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color(MUTED)
    P = G.from_model_poly
    land = [P(p) for x in m.land for p in x.polygons]
    ax.add_collection(PolyCollection(_poly_paths(_clip_polys(land, win)), facecolors=LAND,
                                     edgecolors="none", zorder=1))
    water = [(P(r.polygon), RIVER) for r in m.rivers]
    water += [(P(c.polygon), SEPARATION if c.kind == "separation" else RIVER)
              for c in m.channels]
    water += [(P(w.polygon), CANAL) for w in m.waterways]
    for g, col in water:
        ps = _clip_polys([g], win)
        if ps:
            ax.add_collection(PolyCollection(_poly_paths(ps), facecolors=col,
                                             edgecolors="none", zorder=1.2))
    for q in m.quays:
        ln = LineString(q.line)
        if not G.apart(ln, win):
            ax.plot(*ln.xy, color=QUAY, lw=1.2, alpha=0.8, zorder=1.3)
    tint = {d.id: ARCHETYPE_COLORS.get(d.archetype, "#888888") for d in m.districts}
    blk = [(P(b.polygon), tint[b.district_id]) for b in m.blocks]
    blk = [(p, c) for p, c in blk if not G.apart(p, win, 1.0)]
    ax.add_collection(PolyCollection(_poly_paths([p for p, _ in blk]),
                                     facecolors=[c for _, c in blk], alpha=0.30,
                                     edgecolors="none", zorder=2))
    lots = [P(lt.polygon) for lt in m.lots]
    lots = [p for p in lots if not G.apart(p, win, 1.0)]
    lot_col = {lt.id: tint[lt.district_id] for lt in m.lots}
    lc = [lot_col[lt.id] for lt in m.lots if not G.apart(P(lt.polygon), win, 1.0)]
    ax.add_collection(PolyCollection(_poly_paths(lots), facecolors=lc, alpha=0.55,
                                     edgecolors=LOT_EDGE, linewidths=0.6, zorder=2.1))
    merged = [P(lt.polygon) for lt in m.lots if lt.merged_group_id and
              not G.apart(P(lt.polygon), win, 1.0)]
    if merged:
        ax.add_collection(PolyCollection(_poly_paths(merged), facecolors="none",
                                         edgecolors="#ffe08a", linewidths=1.0,
                                         linestyles=(0, (3, 2)), zorder=2.2))
    opens = [(P(o.polygon), OPEN_COLORS.get(o.kind, "#3f7a4a")) for o in m.open_spaces]
    opens = [(p, c) for p, c in opens if not G.apart(p, win, 1.0)]
    ax.add_collection(PolyCollection(_poly_paths([p for p, _ in opens]),
                                     facecolors=[c for _, c in opens], edgecolors="none",
                                     zorder=2.3))
    for s in m.megasites:
        p = P(s.polygon)
        if not G.apart(p, win):
            ax.add_collection(PolyCollection(_poly_paths(_clip_polys([p], win)),
                                             facecolors="#2c3140", edgecolors="#e8e8e8",
                                             hatch="xx", linewidths=0.6, zorder=2.4))
    # roads: sidewalks under asphalt, then medians and markings
    segs = [s for s in m.road_segments if not G.apart(LineString(s.centerline), win, 40.0)]
    sw_polys, asphalt, hw_asphalt, peds, foots, alleys = [], [], [], [], [], []
    medians, marks_w, marks_y, lane_lines = [], [], [], []
    for s in segs:
        ln = LineString(s.centerline)
        cs = s.cross_section
        half = s.width_m / 2
        side = cs.sidewalk_m[0]
        cls = s.road_class
        if cls == "footbridge":
            foots.append(ln.buffer(half, cap_style="flat"))
            continue
        if cls == "pedestrian":
            peds.append(ln.buffer(half, cap_style="flat"))
            continue
        if cls in ("alley", "service"):
            alleys.append(ln.buffer(half, cap_style="flat"))
            if cls == "service" and not cs.shared:
                marks_w.append(ln)
            continue
        carr = half - side
        if side > 0:
            sw_polys.append(ln.buffer(half, cap_style="flat"))
        (hw_asphalt if cls == "highway" else asphalt).append(ln.buffer(carr, cap_style="flat"))
        med = cs.median_m
        if med > 0.5:
            medians.append(ln.buffer(med / 2, cap_style="flat"))
        elif cls == "street" and not s.one_way:
            marks_y.append(ln)
        lw_ = cs.lane_width_m
        nf, nb = cs.lanes_forward, cs.lanes_backward
        for i in range(1, nf):
            lane_lines.append(ln.offset_curve(-(med / 2 + i * lw_)))
        for i in range(1, nb):
            lane_lines.append(ln.offset_curve(med / 2 + i * lw_))
    jpolys = [P(j.polygon) for j in m.junctions if not G.apart(P(j.polygon), win, 5.0)]

    def fill(geoms, color, z, **kw):
        ps = _clip_polys(geoms, win)
        if ps:
            ax.add_collection(PolyCollection(_poly_paths(ps), facecolors=color,
                                             edgecolors=kw.pop("ec", "none"),
                                             linewidths=kw.pop("lw", 0), zorder=z, **kw))

    fill(sw_polys, SIDEWALK, 3.0)
    fill(alleys, ALLEY, 3.1)
    fill(peds, PROMENADE, 3.1)
    fill(asphalt + jpolys, ASPHALT, 3.2, ec=CURB, lw=0.5)
    fill(asphalt + jpolys, ASPHALT, 3.25)
    fill(hw_asphalt, HIGHWAY_ASPHALT, 3.3)
    fill(medians, MEDIAN, 3.4)
    fill(foots, FOOT, 3.6, ec="#5b4630", lw=0.6)
    # markings stay out of junctions
    jz = shapely.union_all(jpolys) if jpolys else None

    def lines(ls, color, lw, dash, z):
        segs_ = []
        for ln in ls:
            if ln is None or ln.is_empty:
                continue
            g = ln.intersection(win)
            if jz is not None:
                g = g.difference(jz)
            for part in shapely.get_parts(g):
                if part.geom_type == "LineString" and len(part.coords) > 1:
                    segs_.append(list(part.coords))
        if segs_:
            ax.add_collection(LineCollection(segs_, colors=color, linewidths=lw,
                                             linestyles=dash, zorder=z))

    lines(marks_y, MARK_YELLOW, 0.7, (0, (4, 3)), 3.5)
    lines(marks_w, MARK, 0.5, (0, (3, 4)), 3.5)
    lines(lane_lines, MARK, 0.5, (0, (3, 4)), 3.5)
    # crosswalks: zebra stripes across the road
    for xw in m.crosswalks:
        ln = LineString(xw.line)
        if G.apart(ln, win):
            continue
        ax.plot(*ln.xy, color=MARK, lw=xw.width_m * _pt_per_m(ax) * 0.95,
                solid_capstyle="butt", linestyle=(0, (0.6, 0.6)), zorder=3.7)
    # lane graph hint: one-way arrows
    for s in segs:
        if not s.one_way:
            continue
        ln = LineString(s.centerline)
        if ln.length < 20:
            continue
        a = ln.interpolate(0.45, normalized=True)
        b = ln.interpolate(0.55, normalized=True)
        ax.annotate("", xy=(b.x, b.y), xytext=(a.x, a.y), zorder=3.8,
                    arrowprops=dict(arrowstyle="-|>", color=MARK, lw=0.8, mutation_scale=7))
    # labels: district, places, named streets
    d = next(x for x in m.districts if x.id == did)
    ax.text(0.03, 0.97, f"{idx}. {d.name}", transform=ax.transAxes, color=INK, fontsize=11,
            fontweight="bold", va="top", path_effects=HALO, zorder=20)
    ax.text(0.03, 0.925, d.archetype.replace("_", " "), transform=ax.transAxes,
            color=INK, fontsize=8, va="top",
            path_effects=HALO, zorder=20)
    for pl in m.places:
        x, y = pl.label_at
        if win.contains(Point(x, y)):
            ax.text(x, y, pl.name, color="#ffe9a8", fontsize=7.5, ha="center", va="center",
                    style="italic", path_effects=HALO, zorder=19)
    named = {}
    for s in segs:
        if s.name and s.name not in named:
            ln = LineString(s.centerline).intersection(win)
            if ln.geom_type == "LineString" and ln.length > 60:
                named[s.name] = ln
    for name, ln in named.items():
        p0 = ln.interpolate(0.45, normalized=True)
        p1 = ln.interpolate(0.55, normalized=True)
        ang = math.degrees(math.atan2(p1.y - p0.y, p1.x - p0.x))
        if ang > 90:
            ang -= 180
        if ang < -90:
            ang += 180
        mid = ln.interpolate(0.5, normalized=True)
        ax.text(mid.x, mid.y, name, color=INK, fontsize=6.5, rotation=ang, ha="center",
                va="center", rotation_mode="anchor", path_effects=HALO, zorder=19)
    # scale bar 100 m
    x0, y0 = cx - HALF_M + 18, cy - HALF_M + 16
    ax.plot([x0, x0 + 100], [y0, y0], color=INK, lw=2.5, solid_capstyle="butt", zorder=20)
    ax.text(x0 + 50, y0 + 6, "100 m", color=INK, fontsize=7, ha="center", va="bottom",
            path_effects=HALO, zorder=20)


def _pt_per_m(ax) -> float:
    bb = ax.get_window_extent()
    x0, x1 = ax.get_xlim()
    return (bb.width / ax.figure.dpi * 72.0) / (x1 - x0)


def render(b, out, dpi: int = 110) -> None:
    m = b.model
    picks = pick_insets(m)
    if not picks:
        return
    n = len(picks)
    cols = 2 if n > 1 else 1
    rows = int(math.ceil(n / cols))
    size = 7.6
    fig = plt.figure(figsize=(cols * size + 0.4, rows * size + 1.0), facecolor=BG, dpi=dpi)
    st = b.stats.get("local", {})
    fig.text(0.015, 1 - 0.25 / (rows * size + 1.0), f"{b.spec.name}: street level, "
             f"{int(2 * HALF_M)} m insets (M2)", color=INK, fontsize=14, fontweight="bold",
             va="top")
    fig.text(0.015, 1 - 0.55 / (rows * size + 1.0),
             "asphalt with curbs, sidewalks (gray), medians (green), lane and center markings, "
             "zebra crosswalks, one-way arrows, footbridges (wood), promenades (sage),\n"
             "lots (district tint; merged complex groups dashed gold), open space; "
             f"{st.get('junctions', 0)} junctions ({st.get('junctions_signalized', 0)} "
             f"signalized), {st.get('crosswalks', 0)} crosswalks, {st.get('lots', 0)} lots",
             color=MUTED, fontsize=8.5, va="top", linespacing=1.5)
    H = rows * size + 1.0
    W = cols * size + 0.4
    for k, (did, c) in enumerate(picks):
        r, q = divmod(k, cols)
        ax = fig.add_axes([(0.2 + q * size) / W, (0.1 + (rows - 1 - r) * size) / H,
                           (size - 0.2) / W, (size - 0.2) / H])
        draw_inset(ax, m, did, c, k + 1)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)
