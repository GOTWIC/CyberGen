"""Top-down plans of a build's street pieces round points (issue #95): asphalt grey, paving
tan, barriers red (as AG14's check takes them), junction outlines blue, crosswalks green,
connector lanes magenta.

    .venv/bin/python docs/progress/barriers/plot_plan.py BUILD OUT_DIR NAME:X:Y:R [...]

writes OUT_DIR/plan_<NAME>.png, a square of 2R metres round (X, Y).
"""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from assetgen import brief as B
from assetgen.fit.build import Packs
from assetgen.fit.barriers import barrier_mask
bdir = Path(sys.argv[1]); out = Path(sys.argv[2])
m, _, bdir = B.load_model(bdir)
pk = Packs(bdir / "assets", m); pk.load()
bridge_seg = {b.id: b.segment_ids[0] for b in m.bridges if b.segment_ids}
segs = {s.id: s for s in m.road_segments}
import shapely
for spec in sys.argv[3:]:
    name, x, y, r = spec.split(":")
    x, y, r = float(x), float(y), float(r)
    fig, ax = plt.subplots(figsize=(12, 12))
    polys = {"asphalt": [], "paving": [], "barrier": [], "marking": [], "other": []}
    for pid in pk.street_ids():
        T, mats = pk.street_tris(pid)
        if not len(T):
            continue
        c = T.mean(axis=1)
        near = (np.abs(c[:, 0] - x) < r) & (np.abs(c[:, 1] - y) < r)
        if not near.any():
            continue
        k = pk.street_kind(pid)
        rail = None
        sid = bridge_seg.get(pid)
        if k == "street.bridge" and sid in segs:
            rail = (shapely.LineString([(p[0], p[1]) for p in segs[sid].centerline]), segs[sid].width_m / 2)
        bm = barrier_mask(k, mats, T, rail)
        for i in np.nonzero(near)[0]:
            mt = mats[i]
            key = "barrier" if bm[i] else ("asphalt" if mt.startswith("asphalt") else "paving" if mt.startswith("paving") else "marking" if mt.startswith("marking") else "other")
            polys[key].append(T[i, :, :2])
    for key, col, z in (("other", "#cccccc", 1), ("paving", "#e8d9b0", 2), ("asphalt", "#7a7a7a", 3), ("marking", "#ffffff", 4), ("barrier", "#d01010", 5)):
        if polys[key]:
            ax.add_collection(PolyCollection(polys[key], facecolors=col, edgecolors=col if key != "barrier" else "#800000", linewidths=0.2, zorder=z))
    for j in m.junctions:
        ext = np.array(j.polygon.exterior)
        if np.abs(ext.mean(axis=0) - [x, y]).max() < r + 30:
            ax.plot(np.r_[ext[:, 0], ext[:1, 0]], np.r_[ext[:, 1], ext[:1, 1]], color="#0050ff", lw=0.6, zorder=6)
    for c in m.crosswalks:
        a, b = c.line[0], c.line[-1]
        if abs(a[0] - x) < r and abs(a[1] - y) < r:
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#00b000", lw=1.0, zorder=7)
    for ln in m.lanes:
        if ln.kind != "connector":
            continue
        c = np.array([q[:2] for q in ln.centerline])
        if np.abs(c.mean(axis=0) - [x, y]).max() < r:
            ax.plot(c[:, 0], c[:, 1], color="#ff00ff", lw=0.5, zorder=8)
    ax.set_xlim(x - r, x + r); ax.set_ylim(y - r, y + r); ax.set_aspect("equal")
    ax.set_title(name)
    fig.savefig(out / f"plan_{name}.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
