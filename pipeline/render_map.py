import json, re, base64, io, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Polygon as MPoly
from matplotlib.path import Path as MPath
from matplotlib import colors
from shapely.geometry import LineString
from shapely.ops import unary_union
from PIL import Image

geo = json.load(open("geometry.json"))
import xml.etree.ElementTree as ET
ref = None
for el in ET.parse(sys.argv[1]).getroot().iter("{http://www.w3.org/2000/svg}image"):
    href = el.get("{http://www.w3.org/1999/xlink}href") or el.get("href") or ""
    if href.startswith("data:image"):
        ref = Image.open(io.BytesIO(base64.b64decode(re.sub(r"\s", "", href.split(",", 1)[1])))).convert("RGB")

WATER, LAND = "#16384f", "#d8d4cb"
ROAD = {"highway": "#2f3238", "avenue": "#45484f", "street": "#5d6068", "elevated": "#7a4fb5"}
hs = [b["height"] for b in geo["buildings"]]
norm = colors.Normalize(vmin=min(hs), vmax=max(hs))
cmap = colors.LinearSegmentedColormap.from_list("h", ["#c9ccd3", "#3b4252"])

def poly_patch(p, **kw):
    verts, codes = [], []
    for ring in [p["exterior"]] + p["holes"]:
        verts += ring + [ring[0]]
        codes += [MPath.MOVETO] + [MPath.LINETO] * (len(ring) - 1) + [MPath.CLOSEPOLY]
    return PathPatch(MPath(verts, codes), **kw)

def draw(ax, overlay):
    ax.set_facecolor(WATER)
    if overlay and ref is not None:
        ax.imshow(ref, extent=(-600, 600, -600, 600), zorder=0)
    a = 0.55 if overlay else 1.0
    for p in geo["land"]:
        ax.add_patch(poly_patch(p, fc=LAND, ec="#8a8576", lw=0.6, alpha=a * 0.8, zorder=1))
    for cat in ("street", "avenue", "highway", "elevated"):
        geoms = [LineString(r["points"]).buffer(r["width"] / 2, cap_style="flat", join_style="round")
                 for r in geo["roads"] if r["cat"] == cat]
        if not geoms:
            continue
        u = unary_union(geoms)
        for g in ([u] if u.geom_type == "Polygon" else u.geoms):
            ax.add_patch(poly_patch(dict(exterior=list(g.exterior.coords)[:-1],
                                         holes=[list(r.coords)[:-1] for r in g.interiors]),
                                    fc=ROAD[cat], ec="none", alpha=a, zorder=2))
    for b in geo["buildings"]:
        fc = "#c9a45c" if b["cat"] == "landmark" else cmap(norm(b["height"]))
        ax.add_patch(MPoly(b["footprint"], closed=True, fc=fc, ec="#1b1e24", lw=0.7, alpha=min(1, a + 0.25), zorder=3))
    ax.set_xlim(-600, 600); ax.set_ylim(-600, 600); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    if not overlay:
        ax.plot([-540, -340], [-560, -560], color="white", lw=3, zorder=5)
        ax.text(-440, -545, "200 m", color="white", ha="center", fontsize=9, zorder=5)
        ax.annotate("N", xy=(540, 560), xytext=(540, 505), color="white", ha="center", fontsize=11,
                    arrowprops=dict(arrowstyle="-|>", color="white"), zorder=5)

fig, axes = plt.subplots(1, 2, figsize=(16, 8.4), dpi=110)
draw(axes[0], False); axes[0].set_title("Traced plan", color="white", fontsize=12)
draw(axes[1], True); axes[1].set_title("Traced plan over reference", color="white", fontsize=12)
sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
cb = fig.colorbar(sm, ax=axes, fraction=0.02, pad=0.01)
cb.set_label("building height (m, auto)", color="white"); cb.ax.tick_params(colors="white")
fig.patch.set_facecolor("#111418")
plt.savefig("map_2d.png", facecolor=fig.get_facecolor(), bbox_inches="tight")
