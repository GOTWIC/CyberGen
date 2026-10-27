"""M10: `citygen model diff A B --png FILE`, a map of what changed between two city models:
everything that is the same in grey, what B removed in red, what B added in green and what
it changed in yellow (roads, blocks, buildings, open space; props and plants as dots),
with the districts outlined and, beside it, the same for a close-up of the area that
changed. Previews are for review only."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .schematic import BG, INK, LAND, MUTED, SEA  # noqa: E402

SAME, GONE, NEW, CHANGED = "#5d6470", "#e2493a", "#5fd068", "#f2c94c"
AREAS = ("blocks", "open_spaces")
SOLIDS = ("buildings",)
LINES = ("road_segments", "transit_lines")
DOTS = ("props", "plants")
# a change drawn as one: where it is or its shape (a renamed road or a transit line with a
# new station id is drawn as it was)
GEOMETRY = {"centerline", "path", "line", "polygon", "footprint", "masses", "position",
            "z_profile", "zs"}


def _poly(e):
    fp = e.get("footprint") or e.get("polygon") or (e.get("masses") or [{}])[0].get("footprint")
    return fp["exterior"] if fp else None


def _line(e):
    pts = e.get("centerline") or e.get("path") or e.get("line")
    return [p[:2] for p in pts] if pts else None


def render(a: dict, b: dict, d: dict, out, title: str = "") -> None:
    ia = {c: {e["id"]: e for e in a.get(c, [])} for c in AREAS + SOLIDS + LINES + DOTS}
    ib = {c: {e["id"]: e for e in b.get(c, [])} for c in AREAS + SOLIDS + LINES + DOTS}

    def state(c, i):
        v = d.get(c, {})
        if i in v.get("removed", ()):
            return GONE
        if i in v.get("added", ()):
            return NEW
        if GEOMETRY & set(v.get("changed", {}).get(i, ())):
            return CHANGED
        return SAME

    touched = []
    for c in AREAS + SOLIDS + ("road_segments",):   # (a transit line spans the city)
        for i in list(ia[c]) + [k for k in ib[c] if k not in ia[c]]:
            if state(c, i) != SAME:
                e = ib[c].get(i) or ia[c][i]
                pts = _poly(e) if c not in LINES else _line(e)
                if pts:
                    touched += pts
    bx = a["bounds"]
    if touched:
        xs, ys = [p[0] for p in touched], [p[1] for p in touched]
        pad = 120.0
        zoom = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    else:
        zoom = bx
    fig, axes = plt.subplots(1, 2, figsize=(18, 9), facecolor=BG)
    for ax, (x0, y0, x1, y1), dot in zip(axes, (bx, zoom), (0.6, 2.5)):
        ax.set_facecolor(SEA)
        land = [p["exterior"] for lnd in b.get("land", []) for p in lnd["polygons"]]
        ax.add_collection(PolyCollection(land, facecolors=LAND, edgecolors="none", zorder=0))
        for c, z in (("blocks", 1), ("open_spaces", 2), ("buildings", 4)):
            for side, idx in (("a", ia[c]), ("b", ib[c])):
                polys, cols = [], []
                for i, e in idx.items():
                    s = state(c, i)
                    if (side == "a") != (s == GONE):
                        continue
                    p = _poly(e)
                    if p:
                        polys.append(p)
                        cols.append(s if s != SAME else ("#2b2f37" if c == "blocks" else
                                                         "#3a4d3a" if c == "open_spaces"
                                                         else SAME))
                ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors="none",
                                                 alpha=0.9 if c == "buildings" else 0.7,
                                                 zorder=z))
        for c in LINES:
            for side, idx in (("a", ia[c]), ("b", ib[c])):
                segs, cols = [], []
                for i, e in idx.items():
                    s = state(c, i)
                    if (side == "a") != (s == GONE):
                        continue
                    ln = _line(e)
                    if ln:
                        segs.append(ln)
                        cols.append(s if s != SAME else "#8a909c")
                ax.add_collection(LineCollection(segs, colors=cols, linewidths=0.6 if
                                                 c == "road_segments" else 1.2, zorder=3))
        for c in DOTS:
            for side, idx in (("a", ia[c]), ("b", ib[c])):
                pts = [(e["position"][0], e["position"][1], state(c, i))
                       for i, e in idx.items() if (side == "a") == (state(c, i) == GONE)
                       and state(c, i) != SAME]
                if pts:
                    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=dot,
                               c=[p[2] for p in pts], linewidths=0, zorder=5)
        for dd in b.get("districts", []):
            ex = dd["polygon"]["exterior"]
            ax.plot([p[0] for p in ex] + [ex[0][0]], [p[1] for p in ex] + [ex[0][1]],
                    color=INK, lw=0.8, alpha=0.6, zorder=6)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color(MUTED)
    n = {k: sum(len(v[k]) for c, v in d.items() if c != "header") for k in
         ("added", "removed", "changed")}
    axes[0].set_title(title or f"{a.get('name')}: model diff", color=INK, fontsize=13)
    axes[1].set_title(f"{n['added']} added, {n['removed']} removed, {n['changed']} changed "
                      "entities", color=INK, fontsize=11)
    handles = [Line2D([], [], color=c, lw=6, label=lab) for c, lab in
               ((SAME, "the same"), (GONE, "removed"), (NEW, "added"), (CHANGED, "changed"))]
    axes[1].legend(handles=handles, loc="lower right", facecolor=BG, edgecolor=MUTED,
                   labelcolor=INK, fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=110, facecolor=BG)
    plt.close(fig)
