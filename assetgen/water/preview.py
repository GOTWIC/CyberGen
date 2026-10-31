"""`preview_water.png` of the assets (BUILD/assets/water/preview.png): the water packs drawn
from above straight from their glTF files: the beds shaded by depth, the banks by kind, the
riprap stones, and in close insets the surfaces' foam mask and current arrows.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

_CT = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8, 5122: np.int16,
       5120: np.int8}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
BANK_COLORS = {"natural_bank": "#5fbf5a", "beach": "#f5d76e", "marsh_edge": "#3fb8a8",
               "riprap": "#9aa3b0", "road_embankment": "#ff9f43", "canal_wall": "#b9a27a"}


def read(path: Path) -> list[dict]:
    """Every primitive of a pack: node, material, world positions (citygen frame), triangles,
    and its UV1 and COLOR_0 (normalized) where it has them."""
    data = Path(path).read_bytes()
    if len(data) < 20:
        return []
    jl, = struct.unpack_from("<I", data, 12)
    doc = json.loads(data[20:20 + jl].decode("utf-8"))
    off = 20 + jl
    bl, = struct.unpack_from("<I", data, off)
    binary = data[off + 8:off + 8 + bl]

    def acc(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        dt = _CT[a["componentType"]]
        n = _NC[a["type"]]
        stride = v.get("byteStride")
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        size = np.dtype(dt).itemsize * n
        if stride and stride != size:
            raw = np.frombuffer(binary, dtype=np.uint8, count=stride * a["count"],
                                offset=start).reshape(a["count"], stride)
            arr = raw[:, :size].copy().view(dt).reshape(a["count"], n)
        else:
            arr = np.frombuffer(binary, dtype=dt, count=a["count"] * n,
                                offset=start).reshape(a["count"], n)
        if a.get("normalized"):
            arr = arr.astype(np.float64) / float(np.iinfo(dt).max)
        return arr
    mats = doc.get("materials", [])
    out = []
    for nd in doc.get("nodes", []):
        if "mesh" not in nd:
            continue
        t = np.array(nd.get("translation", [0.0, 0.0, 0.0]))
        for pr in doc["meshes"][nd["mesh"]]["primitives"]:
            at = pr["attributes"]
            pos = acc(at["POSITION"]).astype(np.float64) + t
            P = np.stack([pos[:, 0], -pos[:, 2], pos[:, 1]], axis=1)
            rec = {"node": nd["name"], "mat": mats[pr["material"]]["name"] if mats else "?",
                   "pos": P, "tri": acc(pr["indices"]).reshape(-1, 3).astype(np.int64)}
            if "TEXCOORD_1" in at:
                rec["uv1"] = acc(at["TEXCOORD_1"]).astype(np.float64)
            if "COLOR_0" in at:
                rec["col"] = acc(at["COLOR_0"]).astype(np.float64)
            out.append(rec)
    return out


def _views(model) -> list[tuple[str, tuple[float, float]]]:
    """Inset centers: the longest quay's middle, the longest natural or riprap bank's, the
    harbor (the biggest basin, else the sea's harbor zone)."""
    out = []
    if model.quays:
        q = max(model.quays, key=lambda q: (_len(q.line), q.id))
        out.append(("quay and canal", _mid(q.line)))
    bks = [k for k in model.banks if k.kind in ("natural_bank", "riprap", "beach")]
    if bks:
        k = max(bks, key=lambda k: (_len(k.line), k.id))
        out.append((f"{k.kind.replace('_', ' ')} of {k.water_id}", _mid(k.line)))
    basins = [w for w in model.waterways if w.kind in ("basin", "marina")]
    if basins:
        from citygen import geom as G
        b = max(basins, key=lambda w: (G.area(G.from_model_poly(w.polygon)), w.id))
        c = G.from_model_poly(b.polygon).centroid
        out.append(("harbor basin", (c.x, c.y)))
    return out[:3]


def _len(line) -> float:
    return float(sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:])))


def _mid(line) -> tuple[float, float]:
    L = _len(line) / 2.0
    acc = 0.0
    for a, b in zip(line, line[1:]):
        d = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        if acc + d >= L and d > 0:
            f = (L - acc) / d
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        acc += d
    return tuple(line[0])


def render(assets: Path, model, out_png: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    wdir = Path(assets) / "water"
    man = json.loads((wdir / "manifest.json").read_text(encoding="utf-8"))
    beds, banks, lods = [], [], []
    for t in sorted(man["tiles"]):
        f = wdir / f"{t}.glb"
        if not f.is_file():
            continue
        for r in read(f):
            if ".bed." in r["node"]:
                beds.append(r)
            elif ".water." in r["node"]:
                lods.append(r)
            else:
                banks.append(r)
    kind_of = {pid: rec["kind"].rsplit(".", 1)[-1] for pid, rec in man["pieces"].items()}
    stones = []
    for pid, rec in man["pieces"].items():
        for p in rec.get("parts", []):
            o = rec["origin"]
            stones += [(o[0] + x[0], o[1] + x[1]) for x in p["xforms"]]
    stones = np.array(stones) if stones else np.zeros((0, 2))
    views = _views(model)
    fig = plt.figure(figsize=(22, 11), facecolor="#05080d")
    gs = fig.add_gridspec(2, 3, width_ratios=[2.0, 1.0, 1.0])
    cmap = plt.get_cmap("Blues")

    def draw(ax, lod_k, box=None):
        ax.set_facecolor("#20242c")
        for r in beds:
            T = r["pos"][r["tri"]]
            if box is not None:
                c = T[:, :, :2].mean(axis=1)
                sel = (c[:, 0] > box[0]) & (c[:, 0] < box[2]) & (c[:, 1] > box[1]) & \
                    (c[:, 1] < box[3])
                T = T[sel]
            up = ((T[:, 1, 0] - T[:, 0, 0]) * (T[:, 2, 1] - T[:, 0, 1]) -
                  (T[:, 1, 1] - T[:, 0, 1]) * (T[:, 2, 0] - T[:, 0, 0])) > 0
            T = T[up]
            if not len(T):
                continue
            z = T[:, :, 2].mean(axis=1)
            dep = np.clip((-1.5 - z) / 12.0 if model.terrain is None else -z / 12.0, 0, 1)
            ax.add_collection(PolyCollection(T[:, :, :2], facecolors=cmap(0.25 + 0.75 * dep),
                                             edgecolors="none", zorder=1))
        for r in banks:
            T = r["pos"][r["tri"]]
            k = kind_of.get(r["node"], "")
            if box is not None:
                c = T[:, :, :2].mean(axis=1)
                sel = (c[:, 0] > box[0]) & (c[:, 0] < box[2]) & (c[:, 1] > box[1]) & \
                    (c[:, 1] < box[3])
                T = T[sel]
            if len(T):
                ax.add_collection(PolyCollection(T[:, :, :2], facecolors=BANK_COLORS.get(k, "#ccc"),
                                                 edgecolors="none", zorder=2))
        if box is not None:
            for r in lods:
                if not r["node"].endswith(f".lod{lod_k}") or "col" not in r:
                    continue
                P, C = r["pos"], r["col"]
                sel = (P[:, 0] > box[0]) & (P[:, 0] < box[2]) & (P[:, 1] > box[1]) & \
                    (P[:, 1] < box[3])
                f = sel & (C[:, 0] > 0.05)
                if not f.any():
                    continue
                ax.scatter(P[f, 0], P[f, 1], s=2.0, c="white", alpha=np.clip(C[f, 0], 0, 1),
                           zorder=3, linewidths=0)
                if "uv1" in r:
                    sp = np.hypot(r["uv1"][:, 0], r["uv1"][:, 1])
                    g = sel & (sp > 0.02)
                    idx = np.flatnonzero(g)[::9]
                    ax.quiver(P[idx, 0], P[idx, 1], r["uv1"][idx, 0], r["uv1"][idx, 1],
                              color="#ffcc66", scale=12, width=0.0025, zorder=4)
            if len(stones):
                s = stones[(stones[:, 0] > box[0]) & (stones[:, 0] < box[2]) &
                           (stones[:, 1] > box[1]) & (stones[:, 1] < box[3])]
                ax.scatter(s[:, 0], s[:, 1], s=3, c="#d8d4cc", zorder=5, linewidths=0)
        x0, y0, x1, y1 = box if box is not None else model.bounds
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    ax = fig.add_subplot(gs[:, 0])
    draw(ax, 2)
    ax.set_title(f"{model.name}: water beds by depth, banks by kind", color="white",
                 fontsize=14)
    spots = [(0, 1), (0, 2), (1, 1), (1, 2)]
    for (name, (cx, cy)), (r, c) in zip(views, spots):
        a = fig.add_subplot(gs[r, c])
        draw(a, 0, (cx - 150, cy - 150, cx + 150, cy + 150))
        a.set_title(f"{name}: 300 m (foam, current, stones)", color="white", fontsize=10)
        ax.add_patch(matplotlib.patches.Rectangle((cx - 150, cy - 150), 300, 300, fill=False,
                                                  edgecolor="#ff5050", lw=1.2, zorder=6))
    handles = [matplotlib.patches.Patch(color=v, label=k.replace("_", " "))
               for k, v in BANK_COLORS.items()]
    fig.legend(handles=handles, loc="lower right", facecolor="#11151c", labelcolor="white",
               fontsize=9, ncol=2)
    fig.tight_layout()
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_png
