"""M7 preview: `preview_elevated.png`, the road levels. Left, the city: ground roads in muted
tones, every raised road colored by its deck height (viaducts drawn wide, ramps, bridge
approaches), interchanges labeled by template, road columns as dots, underpass streets.
Right, the interchange with the most ramps at street scale (a stack first, then a turbine, then
a trumpet with a flyover: ramps with the heights at their ends, flyover and tier crests,
columns, the roads under the deck), and the height profile of the longest viaduct with the
roads passing under it, or (M12) the profiles of a stack's ramps against its deck levels. Previews are for review only (not part of the model hash).
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
from shapely.geometry import LineString, Point  # noqa: E402

from . import geom as G  # noqa: E402
from .preview_massing import _ground  # noqa: E402
from .schematic import BG, INK, MUTED, SEA  # noqa: E402

HALO = [pe.withStroke(linewidth=2.5, foreground=BG)]
GROUND = "#4a505c"
FOOT = "#2b303a"
CMAP = plt.get_cmap("plasma")
ZMAX = 30.0
TEMPLATE = {"diamond": "D", "diamond_stub": "T", "direct": "B", "overpass": "O", "parclo": "P",
            "trumpet": "Tr", "stack": "S", "turbine": "Tb"}
SYSTEM = ("stack", "turbine")


def _z_at(prof, s: float) -> float:
    if not prof:
        return 0.0
    if s <= prof[0][0]:
        return prof[0][1]
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s <= s1:
            return max(z0, z1) if s1 <= s0 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return prof[-1][1]


def _pieces(s, step: float = 10.0):
    """(segments, heights) of a road in pieces of about `step` m, for coloring by height."""
    line = LineString(s.centerline)
    prof = [(z.s, z.z) for z in s.z_profile]
    L = line.length
    n = max(int(L / step), 1)
    segs, zs = [], []
    for k in range(n):
        a, b = L * k / n, L * (k + 1) / n
        pa, pb = line.interpolate(a), line.interpolate(b)
        segs.append([(pa.x, pa.y), (pb.x, pb.y)])
        zs.append(_z_at(prof, (a + b) / 2.0))
    return segs, zs


def _raised(s) -> bool:
    return bool(s.attrs.get("elevated")) or s.attrs.get("role") == "ramp" or \
        any(z.z > 0.5 for z in s.z_profile)


def _draw_roads(ax, m, lw_scale: float = 1.0, box=None) -> None:
    def inside(s):
        if box is None:
            return True
        x0, y0, x1, y1 = box
        xs = [p[0] for p in s.centerline]
        ys = [p[1] for p in s.centerline]
        return not (max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1)
    flat = [np.asarray(s.centerline) for s in m.road_segments
            if not _raised(s) and s.road_class in ("highway", "avenue", "street", "alley",
                                                   "service") and inside(s)]
    ax.add_collection(LineCollection(flat, colors=GROUND, linewidths=0.5 * lw_scale,
                                     zorder=2))
    under = [np.asarray(s.centerline) for s in m.road_segments
             if s.attrs.get("role") == "underpass" and inside(s)]
    ax.add_collection(LineCollection(under, colors="#7ee0c3", linewidths=1.6 * lw_scale,
                                     zorder=2.2))
    norm = Normalize(0.0, ZMAX)
    for s in sorted((s for s in m.road_segments if _raised(s) and inside(s)),
                    key=lambda s: max(z.z for z in s.z_profile)):
        segs, zs = _pieces(s)
        elev = bool(s.attrs.get("elevated"))
        ramp = s.attrs.get("role") == "ramp"
        fly = bool(s.attrs.get("flyover")) or (s.attrs.get("turn") == "left")
        w = (3.4 if elev else 2.4 if fly else 1.6 if ramp else 1.2) * lw_scale
        if fly:
            # a flyover passes over the deck: a dark casing keeps it readable on top
            ax.add_collection(LineCollection(segs, colors=BG, linewidths=w + 1.6 * lw_scale,
                                             zorder=3.6, capstyle="round"))
        ax.add_collection(LineCollection(segs, colors=CMAP(norm(np.asarray(zs))),
                                         linewidths=w, zorder=3.7 if fly else 3.5 if elev
                                         else 3.2, capstyle="round"))


def _columns(ax, m, size: float = 2.0, box=None) -> None:
    pts = []
    for s in m.structures:
        if not (s.attrs or {}).get("road_id") or s.footprint is None or s.kind != "column":
            continue
        c = G.from_model_poly(s.footprint).centroid
        if box is None or (box[0] <= c.x <= box[2] and box[1] <= c.y <= box[3]):
            pts.append((c.x, c.y))
    if pts:
        a = np.asarray(pts)
        ax.scatter(a[:, 0], a[:, 1], s=size, c="#e8e8f0", zorder=4, linewidths=0)


def _interchanges(m) -> list[tuple[str, str, list]]:
    """(interchange id, template, its ramps): stacks, turbines, those with a flyover first,
    then by number of ramps."""
    by: dict = {}
    for s in m.road_segments:
        if s.attrs.get("role") == "ramp":
            by.setdefault(s.attrs.get("interchange"), (s.attrs.get("template"), []))[1].append(s)
    return sorted(((k, t, rs) for k, (t, rs) in by.items()), key=lambda x: (
        x[1] != "stack", x[1] != "turbine", not any(s.attrs.get("flyover") for s in x[2]),
        -len(x[2]), x[0]))


EMBANK = "#8a7a62"       # M18: retained fill under the low raised roads


def _embankments(ax, m, box=None) -> None:
    """M18: the embankments' footprints (under the roads, drawn over by them)."""
    polys = []
    for s in m.structures:
        if s.kind != "embankment" or s.footprint is None:
            continue
        ring = np.asarray(s.footprint.exterior)
        if box is None or (box[0] <= ring[:, 0].max() and ring[:, 0].min() <= box[2] and
                           box[1] <= ring[:, 1].max() and ring[:, 1].min() <= box[3]):
            polys.append(ring)
    if polys:
        ax.add_collection(PolyCollection(polys, facecolors=EMBANK, edgecolors=EMBANK,
                                         linewidths=0.6, zorder=2.9))


def render_elevated(b, out, dpi: int = 140) -> None:
    m = b.model
    x0, y0, x1, y1 = m.bounds
    W, H = x1 - x0, y1 - y0
    map_w = 10.0
    side_w = 6.0
    fig_h = max(map_w * H / W, 9.0) + 1.3
    fig = plt.figure(figsize=(map_w + side_w, fig_h), facecolor=BG, dpi=dpi)
    st = b.stats.get("elevated", {})
    fig.text(0.012, 1 - 0.28 / fig_h, f"{b.spec.name}: road levels (M7)", color=INK,
             fontsize=14, fontweight="bold", va="top")
    tm = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in st.get("interchanges", {}).items())
    fig.text(0.012, 1 - 0.62 / fig_h,
             f"{st.get('elevated_km', 0)} km of viaduct in {st.get('elevated_runs', 0)} runs, "
             f"{st.get('ramps', 0)} ramps ({tm or 'no interchange'}), "
             f"{st.get('overpasses', 0)} roads under the decks, "
             f"{st.get('underpass_streets', 0)} underpass streets, "
             + (f"{st['flyovers']} flyover{'s' if st['flyovers'] > 1 else ''} up to "
                f"{st['max_flyover_m']} m, " if st.get("flyovers") else "")
             + (f"{st['stack_ramps']} stack and turbine ramps up to {st['max_stack_m']} m, "
                if st.get("stack_ramps") else "") +
             f"{st.get('road_columns', 0)} columns, {st.get('embankments', 0)} embankments; "
             f"deck up to {st.get('max_deck_m', 0)} m; "
             f"{'checks PASS' if b.passed else 'checks FAIL'}", color=MUTED, fontsize=9,
             va="top")
    mh = map_w * H / W
    ax = fig.add_axes([0.0, 0.2 / fig_h, map_w / (map_w + side_w), mh / fig_h])
    ax.set_facecolor(SEA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    _ground(ax, m)
    _embankments(ax, m)
    _draw_roads(ax, m)
    _columns(ax, m, 1.2)
    ics = _interchanges(m)
    for k, t, rs in ics:
        c = LineString(rs[0].centerline).interpolate(0.5, normalized=True)
        ax.text(c.x, c.y, TEMPLATE.get(t, "?"), color=INK, fontsize=8, fontweight="bold",
                ha="center", va="center", zorder=6, path_effects=HALO)
    for s in m.road_segments:
        for p in s.attrs.get("overpass_at", []) if s.attrs.get("elevated") else []:
            ax.plot([p[0]], [p[1]], marker="o", ms=4, mfc="none", mec="#e8e8f0", zorder=6)
    handles = [Line2D([], [], color=CMAP(0.15), lw=3.4, label="viaduct (color: deck height)"),
               Line2D([], [], color=CMAP(0.5), lw=1.6, label="ramp"),
               Line2D([], [], color=CMAP(0.55), lw=2.4, label="flyover (trumpet, stack)",
                      path_effects=[pe.withStroke(linewidth=4.0, foreground="#5a5f6b")]),
               Line2D([], [], color=CMAP(0.8), lw=1.2, label="raised approach"),
               Line2D([], [], color="#7ee0c3", lw=1.6, label="underpass street"),
               Line2D([], [], color="#e8e8f0", marker="o", lw=0, ms=4, mfc="none",
                      label="road under the deck"),
               Line2D([], [], color="#e8e8f0", marker=".", lw=0, label="column"),
               Line2D([], [], color=EMBANK, lw=4.0, label="embankment (raised road under 4.5 m)")]
    ax.legend(handles=handles, loc="lower left", fontsize=7.5, frameon=False, labelcolor=INK)
    sm = plt.cm.ScalarMappable(norm=Normalize(0.0, ZMAX), cmap=CMAP)
    cax = fig.add_axes([map_w / (map_w + side_w) + 0.05, 0.45, 0.2, 0.012])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("deck height (m)", color=INK, fontsize=7)
    cb.ax.tick_params(colors=INK, labelsize=7)
    # the interchange with the most ramps
    side = map_w / (map_w + side_w)
    ax2 = fig.add_axes([side + 0.01, 0.5, (side_w - 0.3) / (map_w + side_w), 0.42])
    ax2.set_facecolor("#20242c")
    ax2.set_aspect("equal")
    ax2.tick_params(colors=MUTED, labelsize=6)
    if ics:
        k, t, rs = ics[0]
        pts = np.asarray([p for s in rs for p in s.centerline])
        cx = (pts[:, 0].min() + pts[:, 0].max()) / 2.0
        cy = (pts[:, 1].min() + pts[:, 1].max()) / 2.0
        R = max(float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1])), 200.0) / 2.0 + 60.0
        box = (cx - R, cy - R, cx + R, cy + R)
        foot = [np.asarray(G.from_model_poly(b_.footprint).exterior.coords)
                for b_ in m.buildings if b_.footprint is not None and
                box[0] - 50 < b_.footprint.exterior[0][0] < box[2] + 50 and
                box[1] - 50 < b_.footprint.exterior[0][1] < box[3] + 50]
        ax2.add_collection(PolyCollection(foot, facecolors=FOOT, edgecolors="none", zorder=1))
        _embankments(ax2, m, box)
        _draw_roads(ax2, m, 3.0, box)
        _columns(ax2, m, 6.0, box)
        for s in rs:
            if s.attrs.get("turn") == "left":
                # a stack's or turbine's left ramp: its crest, written out along the arm it
                # comes down on (the four labels apart, not on the core)
                top = max(s.z_profile, key=lambda z: (z.z, -z.s))
                line = LineString(s.centerline)
                C = Point(s.attrs.get("crossing") or line.interpolate(top.s).coords[0])
                arm = [line.interpolate(d) for d in np.arange(top.s, line.length, 10.0)]
                c = next((q for q in arm if q.distance(C) >= 0.35 * R), arm[-1])
                tag = f"tier {s.attrs['tier']} " if s.attrs.get("tier") else ""
                ax2.text(c.x, c.y, f"{tag}{top.z:.1f} m", color=INK, fontsize=6.5,
                         fontweight="bold", path_effects=HALO, zorder=7, ha="center")
                continue
            if s.attrs.get("turn"):
                continue
            for end, at in ((s.centerline[0], s.z_profile[0].z),
                            (s.centerline[-1], s.z_profile[-1].z)):
                if box[0] <= end[0] <= box[2] and box[1] <= end[1] <= box[3]:
                    ax2.text(end[0], end[1], f"{at:.1f} m", color=INK, fontsize=6.5,
                             path_effects=HALO, zorder=6)
            if s.attrs.get("flyover"):
                # its crest, where it passes over the deck
                top = max(s.z_profile, key=lambda z: (z.z, -z.s))
                c = LineString(s.centerline).interpolate(top.s)
                ax2.text(c.x, c.y, f"flyover {top.z:.1f} m", color=INK, fontsize=7,
                         fontweight="bold", path_effects=HALO, zorder=7, ha="left",
                         va="bottom")
        ax2.set_xlim(box[0], box[2])
        ax2.set_ylim(box[1], box[3])
        ax2.set_title(f"{k}: {t.replace('_', ' ')}, {len(rs)} ramps", color=INK, fontsize=9)
    else:
        ax2.text(0.5, 0.5, "no interchange", color=MUTED, ha="center", va="center",
                 transform=ax2.transAxes)
    # the longest viaduct's profile (a stack's ramps where there is one)
    ax3 = fig.add_axes([side + 0.05, 0.08, (side_w - 0.9) / (map_w + side_w), 0.32])
    ax3.set_facecolor("#20242c")
    ax3.tick_params(colors=MUTED, labelsize=7)
    if ics and ics[0][1] in SYSTEM:
        _system_profiles(ax3, m, ics[0])
        fig.savefig(out, dpi=dpi, facecolor=BG)
        plt.close(fig)
        return
    runs: dict = {}
    for s in m.road_segments:
        if s.attrs.get("elevated") and not s.attrs.get("direct"):
            runs.setdefault(s.attrs.get("split_of"), []).append(s)
    if runs:
        # the one with the most roads under it and ramps on it, then the longest
        ramps_on = {}
        for s in m.road_segments:
            if s.attrs.get("role") == "ramp":
                for n in (s.start, s.end):
                    ramps_on[n] = ramps_on.get(n, 0) + 1
        key = max(sorted(runs), key=lambda r: (
            sum(len(s.attrs.get("overpass_at", [])) + ramps_on.get(s.start, 0)
                for s in runs[r]), sum(s.attrs["length_m"] for s in runs[r])))
        segs = runs[key]
        by_start = {s.start: s for s in segs}
        ends = {s.end for s in segs}
        cur = next((s for s in segs if s.start not in ends), segs[0])
        chain, acc, xs, zs, marks = [], 0.0, [], [], []
        while cur is not None and cur not in chain:
            chain.append(cur)
            for z in cur.z_profile:
                xs.append(acc + z.s)
                zs.append(z.z)
            line = LineString(cur.centerline)
            for p in cur.attrs.get("overpass_at", []):
                marks.append(acc + line.project(Point(p)))
            acc += cur.attrs["length_m"]
            cur = by_start.get(cur.end)
        ax3.fill_between(xs, 0, zs, color=CMAP(0.25), alpha=0.35)
        ax3.plot(xs, zs, color=CMAP(0.6), lw=1.8)
        for x in marks:
            ax3.axvline(x, color="#e8e8f0", lw=0.8, ls=":")
        ax3.set_xlabel("along the viaduct (m)", color=INK, fontsize=8)
        ax3.set_ylabel("deck height (m)", color=INK, fontsize=8)
        title = f"viaduct {key} ({acc / 1000:.2f} km); dotted: roads under it"
        top = max(zs)
        for s in m.road_segments:
            if s.attrs.get("flyover"):
                # a trumpet's flyover along its own length (deck end first), over the deck
                fx = [z.s for z in s.z_profile]
                fz = [z.z for z in s.z_profile]
                if fz[0] < fz[-1]:
                    L = s.attrs["length_m"]
                    fx, fz = [L - x for x in reversed(fx)], fz[::-1]
                ax3.plot(fx, fz, color=CMAP(0.75), lw=1.4, ls="--",
                         label=f"flyover of {s.attrs.get('interchange')} (along itself)")
                top = max(top, max(fz))
                ax3.legend(loc="upper right", fontsize=7, frameon=False, labelcolor=INK)
        ax3.set_title(title, color=INK, fontsize=9)
        ax3.set_ylim(0, max(top * 1.15, 12.0))
    else:
        ax3.text(0.5, 0.5, "no viaduct", color=MUTED, ha="center", va="center",
                 transform=ax3.transAxes)
    fig.savefig(out, dpi=dpi, facecolor=BG)
    plt.close(fig)


def _system_profiles(ax, m, ic) -> None:
    """M12: a stack's (or turbine's) ramps along themselves, from where each leaves its highway:
    the right turns thin, the left turns by tier, over the deck levels."""
    from . import elevated as EL

    k, t, rs = ic
    norm = Normalize(0.0, ZMAX)
    top = 0.0
    for s in sorted(rs, key=lambda s: (s.attrs.get("turn") != "right",
                                       s.attrs.get("tier") or 0, s.id)):
        xs = [z.s for z in s.z_profile]
        zs = [z.z for z in s.z_profile]
        left = s.attrs.get("turn") == "left"
        ax.plot(xs, zs, color=CMAP(norm(max(zs))), lw=1.8 if left else 0.9,
                alpha=1.0 if left else 0.7)
        top = max(top, max(zs))
    for lv, z in sorted(EL.LEVEL_Z.items()):
        ax.axhline(z, color="#e8e8f0", lw=0.7, ls=":")
        ax.text(0.995, z, f"level {lv}: {z:g} m", color=MUTED, fontsize=6.5, ha="right",
                va="bottom", transform=ax.get_yaxis_transform())
    handles = [Line2D([], [], color=CMAP(norm(EL.LEVEL_Z[3])), lw=1.8,
                      label="left turns (flyovers)"),
               Line2D([], [], color=CMAP(norm(EL.LEVEL_Z[1])), lw=0.9, label="right turns")]
    ax.legend(handles=handles, loc="upper left", fontsize=7, frameon=False, labelcolor=INK)
    ax.set_xlabel("along each ramp (m)", color=INK, fontsize=8)
    ax.set_ylabel("deck height (m)", color=INK, fontsize=8)
    ax.set_title(f"{k}: {t} ramp profiles over the highway at grade and the {EL.LEVEL_Z[1]:g} m "
                 "deck", color=INK, fontsize=9)
    ax.set_ylim(0, max(top * 1.15, 12.0))
