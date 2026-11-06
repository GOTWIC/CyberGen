"""M22 preview: `preview_pavement.png`, the pavement map. Left, the city: every face colored
by its kind (carriageway, median, curb, sidewalk, junction, corner pad, bulb, bend), the
junctions the height fit keeps as M18 left them outlined. Right, four 120 m windows at
street scale, each face drawn with its edges: the largest cluster, a cul-de-sac's bulb, the
largest bend face and the highest junction, that one colored by height.
Previews are for review only (not part of the model hash).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PathCollection  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from .preview_ground import _base, _setup  # noqa: E402
from .preview_massing import _paths  # noqa: E402
from .schematic import BG, INK, MUTED  # noqa: E402

KIND_COLOR = {
    "carriageway": "#4a505c", "median": "#8c8f5a", "curb": "#9aa0a8", "sidewalk": "#b9bcc2",
    "walk": "#a89f8a", "bend": "#5d6f9a", "junction": "#b0484f", "corner": "#d7a0a4",
    "bulb": "#a35da6",
}
HELD = "#ffd23f"
WINDOW_M = 60.0         # half width of a street-scale window


def _ID(c):
    return c


def _faces(N, m) -> list:
    out = []
    for f in N.faces:
        if f.id in N.bad or not N.rings.get(f.id):
            continue
        g = N.poly(f.id)
        if not g.is_empty:
            out.append((f, g))
    return out


def _draw(ax, faces, edges: bool, color=None) -> None:
    by: dict[str, list] = {}
    for f, g in faces:
        by.setdefault(color(f) if color else KIND_COLOR.get(f.kind, "#777777"), []).append(g)
    for col in sorted(by):
        ax.add_collection(PathCollection(_paths(by[col], _ID), facecolors=col,
                                         edgecolors="#14161b" if edges else "none",
                                         linewidths=0.35 if edges else 0.0, zorder=3))


def _held(ax, faces, held: set, lw: float) -> None:
    gs = [g for f, g in faces if f.owner_id in held]
    if gs:
        ax.add_collection(PathCollection(_paths(gs, _ID), facecolors="none", edgecolors=HELD,
                                         linewidths=lw, zorder=5))


def _windows(m, faces) -> list:
    """(title, center, by height) of the four windows."""
    out = []
    jn = {j.id: j for j in m.junctions}
    clusters = [j for j in m.junctions if len(j.attrs.get("nodes") or []) > 1]
    if clusters:
        j = max(clusters, key=lambda j: (len(j.attrs["nodes"]), j.id))
        gs = [g for f, g in faces if f.owner_id == j.id and f.kind == "junction"]
        if gs:
            out.append((f"cluster {j.id} ({len(j.attrs['nodes'])} nodes)",
                        max(gs, key=lambda g: g.area), False))
    bulbs = [(g.area, f.owner_id, g) for f, g in faces if f.kind == "bulb"]
    if bulbs:
        _, oid, g = max(bulbs, key=lambda t: (t[0], t[1]))
        out.append((f"cul-de-sac {oid}", g, False))
    bends = [(g.area, f.id, g) for f, g in faces if f.kind == "bend"]
    if bends:
        _, fid, g = max(bends, key=lambda t: (t[0], t[1]))
        out.append((f"bend {fid}", g, False))
    tops = {}
    for f, g in faces:
        if f.owner_id in jn and f.kind == "junction":
            tops[f.owner_id] = g
    if tops:
        zs = {j.id: max(j.edge_z or [0.0]) for j in m.junctions if j.id in tops}
        jid = max(zs, key=lambda k: (zs[k], k))
        out.append((f"highest junction {jid} ({zs[jid]:.1f} m), by height", tops[jid], True))
    res = []
    for title, g, hz in out:
        c = g.representative_point()
        res.append((title, (c.x, c.y), hz))
    return res[:4]


def render_pavement(b, out, dpi: int = 140) -> None:
    from .pavement_checks import Net

    m = b.model
    N = Net(m)
    faces = _faces(N, m)
    held = {j.id for j in m.junctions if j.attrs.get("unbuildable")}
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    map_w, side_w = 10.0, 8.0
    fig_h = max(map_w * H / W, 9.0) + 1.3
    fig = plt.figure(figsize=(map_w + side_w, fig_h), facecolor=BG, dpi=dpi)
    st = b.stats.get("local", {}).get("generator", {}).get("pavement") or {}
    fig.text(0.012, 1 - 0.28 / fig_h, f"{b.spec.name}: pavement map (M22)", color=INK,
             fontsize=14, fontweight="bold", va="top")
    fig.text(0.012, 1 - 0.62 / fig_h,
             f"{len(faces)} faces, {st.get('vertices', len(N.vert))} vertices, "
             f"{st.get('edges', len(N.edge))} edges, {st.get('clusters', 0)} clusters, "
             f"{st.get('bends', 0)} bends; {len(held)} junctions kept as M18 left them "
             f"(outlined); " + ("checks PASS" if b.passed else "checks FAIL"),
             color=MUTED, fontsize=8.5, va="top")
    mh = map_w * H / W
    ax = fig.add_axes([0.0, 0.2 / fig_h, map_w / (map_w + side_w), mh / fig_h])
    _setup(ax, (x0, x1), (y0, y1))
    _base(ax, m)
    _draw(ax, faces, False)
    _held(ax, faces, held, 1.2)
    hand = [Patch(facecolor=c, label=k) for k, c in KIND_COLOR.items()
            if any(f.kind == k for f, _ in faces)]
    hand.append(Patch(facecolor="none", edgecolor=HELD, label="kept as M18 left it"))
    leg = ax.legend(handles=hand, loc="lower left", fontsize=7.5, facecolor=BG,
                    edgecolor=MUTED, labelcolor=INK, framealpha=0.85, ncol=2)
    leg.set_zorder(20)
    side_x = map_w / (map_w + side_w)
    sw = side_w / (map_w + side_w)
    cm = plt.get_cmap("viridis")
    for k, (title, (cx, cy), by_z) in enumerate(_windows(m, faces)):
        col, row = k % 2, k // 2
        a = fig.add_axes([side_x + 0.01 + col * sw / 2, 0.52 - row * 0.47, sw / 2 - 0.02,
                          0.42])
        r = WINDOW_M
        _setup(a, (cx - r, cx + r), (cy - r, cy + r))
        _base(a, m)
        near = [(f, g) for f, g in faces if g.distance(_pt(cx, cy)) <= r * 1.5]
        if by_z:
            zs = [N.z(v) for f, _ in near for v in N.rings[f.id][0]]
            lo, hi = (min(zs), max(zs)) if zs else (0.0, 1.0)

            def color(f, lo=lo, hi=hi):
                vs = N.rings[f.id][0]
                z = sum(N.z(v) for v in vs) / len(vs)
                return matplotlib.colors.to_hex(cm((z - lo) / (hi - lo) if hi > lo else 0.5))
            _draw(a, near, True, color)
            title += f" {lo:.1f} to {hi:.1f} m"
        else:
            _draw(a, near, True)
        _held(a, near, held, 2.0)
        a.set_title(title, color=INK, fontsize=8)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)


def _pt(x, y):
    from shapely.geometry import Point

    return Point(x, y)
