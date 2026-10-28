"""M14 preview: `preview_decks.png`, a layered district level by level. Left, the ground under
the biggest deck: its streets, the low buildings under the slab, the light wells with their
stairs and elevators, the columns, the ramps and the slab's outline. Middle, the deck: the
slab, its streets, sidewalks and lots, the buildings standing on it, the stair heads. Right, a
section across the deck square to its longest street (the ground street, the buildings under
the slab, the slab on its columns, the deck street and the buildings on it). Previews are for
review only (not part of the model hash).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402

from . import geom as G  # noqa: E402
from .schematic import BG, INK, MUTED  # noqa: E402

PANEL = "#20242c"
STREET = "#3b404b"
SIDEWALK = "#6d727c"
LOT = "#2c3140"
UNDER = "#c2334d"
UPPER = "#5b8def"
SLAB = "#8c9099"
WELL = "#f5d76e"
RAMP = "#ff4fd8"
COLUMN = "#e8e8e8"
STAIR = "#ff6b6b"
LIFT = "#8fd3ff"


def _xy(poly):
    return [np.asarray(p.exterior.coords) for p in G.parts(poly)]


def _fill(ax, polys, color, z=2, alpha=1.0, edge="none", lw=0.0):
    rings = [r for p in polys for r in _xy(p)]
    if rings:
        ax.add_collection(PolyCollection(rings, facecolors=color, edgecolors=edge,
                                         linewidths=lw, alpha=alpha, zorder=z))


def _strips(ax, segs, color, z=3, scale=1.0):
    polys = [LineString(s.centerline).buffer(s.width_m / 2.0 * scale, cap_style="flat")
             for s in segs]
    _fill(ax, polys, color, z)


def _frame(ax, box):
    x0, y0, x1, y1 = box
    ax.set_facecolor(PANEL)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#3a3f4a")


def _section(m, dk):
    from .blockout import _deck_cut, _Plan

    return _deck_cut(_Plan(m))


def render_decks(b, out, dpi: int = 130) -> None:
    m = b.model
    if not m.decks:
        return
    dk = max(m.decks, key=lambda d: (d.area_m2, d.id))
    P = G.from_model_poly(dk.polygon)
    x0, y0, x1, y1 = P.bounds
    pad = 60.0
    box = (x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    w = box[2] - box[0]
    h = box[3] - box[1]
    pw = 6.4
    ph = pw * h / w
    FH = ph + 2.0
    fig = plt.figure(figsize=(3 * pw + 0.6, FH), facecolor=BG, dpi=dpi)
    st = (b.stats.get("decks") or {}).get(dk.id, {})
    dname = next((d.name for d in m.districts if d.id == dk.district_id), dk.district_id)
    fig.text(0.008, 1 - 0.25 / FH, f"{b.spec.name}: layered districts (M14)",
             color=INK, fontsize=14, fontweight="bold", va="top")
    fig.text(0.008, 1 - 0.62 / FH,
             f"{len(m.decks)} deck{'s' if len(m.decks) != 1 else ''}; {dname}: "
             f"{dk.area_m2 / 1e4:.1f} ha at {dk.top_m:g} m (slab {dk.slab_m:g} m), "
             f"{st.get('streets', 0)} deck streets and ramps, {st.get('upper_lots', 0)} deck "
             f"lots, {st.get('upper_buildings', 0)} buildings on the deck, "
             f"{len(dk.well_ids)} light wells, {len(dk.column_ids)} columns; "
             f"{'checks PASS' if b.passed else 'checks FAIL'}", color=MUTED, fontsize=9,
             va="top")
    near = P.buffer(pad * 1.5)
    segs = [s for s in m.road_segments if LineString(s.centerline).intersects(near)]
    ground = [s for s in segs if "deck" not in s.attrs]
    upper = [s for s in segs if s.attrs.get("deck") and s.attrs.get("role") != "deck_ramp"]
    ramps = [s for s in segs if s.attrs.get("role") == "deck_ramp"]
    lots = [lt for lt in m.lots if G.from_model_poly(lt.polygon).intersects(near)]
    blds = [x for x in m.buildings if x.footprint is not None and
            G.from_model_poly(x.footprint).intersects(near)]
    wells = [o for o in m.open_spaces if o.id in set(dk.well_ids)]
    cols = [s for s in m.structures if (s.attrs or {}).get("deck") == dk.id]
    bot = 0.75 / FH
    hh = ph / FH
    W = 3 * pw + 0.6
    # --- the ground
    ax = fig.add_axes([0.2 / W, bot, pw / W, hh])
    _frame(ax, box)
    ax.set_title("level 0: the ground under the deck", color=INK, fontsize=10, loc="left")
    _fill(ax, [G.from_model_poly(lt.polygon) for lt in lots if not lt.level], LOT, 1)
    _strips(ax, ground, STREET, 2)
    _fill(ax, [G.from_model_poly(j.polygon) for j in m.junctions if not j.level and
               G.from_model_poly(j.polygon).intersects(near)], STREET, 2)
    _fill(ax, [G.from_model_poly(x.footprint) for x in blds if not x.level and
               not x.attrs.get("deck_under")], "#4a505c", 3)
    _fill(ax, [G.from_model_poly(x.footprint) for x in blds if x.attrs.get("deck_under")],
          UNDER, 3)
    _fill(ax, [G.from_model_poly(o.polygon) for o in wells], WELL, 4)
    _strips(ax, ramps, RAMP, 5)
    _fill(ax, [P], "none", 6, edge=SLAB, lw=1.4)
    xs = [G.centroid(G.from_model_poly(c.footprint)) for c in cols if c.kind == "column"]
    if xs:
        ax.scatter([p[0] for p in xs], [p[1] for p in xs], s=2.5, c=COLUMN, zorder=7,
                   linewidths=0)
    for c in cols:
        if c.kind in ("stair", "elevator"):
            _fill(ax, [G.from_model_poly(c.footprint)], STAIR if c.kind == "stair" else LIFT,
                  8)
    ax.legend(handles=[Patch(facecolor=UNDER, label="buildings under the deck"),
                       Patch(facecolor=WELL, label="light well"),
                       Patch(facecolor=RAMP, label="ramp"),
                       Line2D([], [], color=COLUMN, marker="o", lw=0, ms=3, label="column"),
                       Patch(facecolor=STAIR, label="stair"),
                       Patch(facecolor=LIFT, label="elevator"),
                       Patch(facecolor="none", edgecolor=SLAB, label="deck outline")],
              loc="lower left", fontsize=7, facecolor=PANEL, edgecolor="#3a3f4a",
              labelcolor=INK)
    # --- the deck
    ax = fig.add_axes([(0.4 + pw) / W, bot, pw / W, hh])
    _frame(ax, box)
    ax.set_title(f"level 1: the deck ({dk.top_m:g} m)", color=INK, fontsize=10, loc="left")
    _fill(ax, [P], SLAB, 1)
    _fill(ax, [G.from_model_poly(lt.polygon) for lt in lots if lt.level], LOT, 2)
    _strips(ax, upper, STREET, 3)
    _fill(ax, [G.from_model_poly(j.polygon) for j in m.junctions if j.level and
               G.from_model_poly(j.polygon).intersects(near)], STREET, 3)
    sw = [w for w in m.sidewalks if w.level]
    if sw:
        _fill(ax, [LineString(w.line).buffer(w.width_m / 2, cap_style="flat") for w in sw],
              SIDEWALK, 4)
    _fill(ax, [G.from_model_poly(x.footprint) for x in blds if x.level], UPPER, 5)
    _strips(ax, ramps, RAMP, 6)
    for c in cols:
        if c.kind in ("stair", "elevator"):
            _fill(ax, [G.from_model_poly(c.footprint)], STAIR if c.kind == "stair" else LIFT,
                  8)
    walks = [w for w in m.walkways if w.level and len(w.line) >= 2]
    ax.add_collection(LineCollection([np.asarray(w.line)[:, :2] for w in walks],
                                     colors="#7ee0c3", linewidths=0.4, zorder=7))
    ax.legend(handles=[Patch(facecolor=SLAB, label="slab"),
                       Patch(facecolor=STREET, label="deck streets"),
                       Patch(facecolor=UPPER, label="buildings on the deck"),
                       Line2D([], [], color="#7ee0c3", lw=1, label="deck walkways")],
              loc="lower left", fontsize=7, facecolor=PANEL, edgecolor="#3a3f4a",
              labelcolor=INK)
    # --- the section
    ax = fig.add_axes([(0.6 + 2 * pw) / W, bot, pw / W, hh])
    ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_color("#3a3f4a")
    ax.tick_params(colors=MUTED, labelsize=7)
    cut = _section(m, dk)
    if cut is not None:
        ox, oy = cut["origin"]
        ux, uy = cut["u"]
        half = cut["half_len"]
        line = LineString([(ox - ux * half, oy - uy * half), (ox + ux * half, oy + uy * half)])
        top_h = 0.0

        def span(geom):
            g = geom.intersection(line)
            if g.is_empty:
                return []
            out = []
            for part in getattr(g, "geoms", [g]):
                cs = list(part.coords)
                if len(cs) >= 2:
                    a = (cs[0][0] - ox) * ux + (cs[0][1] - oy) * uy
                    c = (cs[-1][0] - ox) * ux + (cs[-1][1] - oy) * uy
                    out.append((min(a, c), max(a, c)))
            return out

        for x in blds:
            for ms in x.masses:
                for a, c in span(G.from_model_poly(ms.footprint)):
                    col = UPPER if x.level else UNDER if x.attrs.get("deck_under") else \
                        "#4a505c"
                    ax.add_patch(plt.Rectangle((a, ms.z0_m), c - a, ms.z1_m - ms.z0_m,
                                               color=col, zorder=3, lw=0))
                    top_h = max(top_h, ms.z1_m)
        for a, c in span(P):
            ax.add_patch(plt.Rectangle((a, dk.top_m - dk.slab_m), c - a, dk.slab_m,
                                       color=SLAB, zorder=4, lw=0))
        for c in cols:
            if c.kind != "column":
                continue
            fp = G.from_model_poly(c.footprint)
            if fp.distance(line) < 4.0:
                d = (fp.centroid.x - ox) * ux + (fp.centroid.y - oy) * uy
                ax.add_patch(plt.Rectangle((d - 0.5, 0.0), 1.0, c.z1_m, color=COLUMN,
                                           zorder=2, lw=0))
        for s in ground + upper:
            for a, c in span(LineString(s.centerline).buffer(s.width_m / 2, cap_style="flat")):
                z = s.z_profile[0].z if s.attrs.get("deck") else 0.0
                ax.add_patch(plt.Rectangle((a, z - 0.3), c - a, 0.6, color="#9aa0aa",
                                           zorder=5, lw=0))
        ax.axhline(0.0, color="#6b5a45", lw=2, zorder=1)
        ax.set_xlim(-half, half)
        ax.set_ylim(-4.0, min(max(top_h, dk.top_m + 30.0) + 10.0, 260.0))
        ax.set_xlabel("m across the deck", color=MUTED, fontsize=8)
        ax.set_ylabel("m", color=MUTED, fontsize=8)
    ax.set_title("section across the deck", color=INK, fontsize=10, loc="left")
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
