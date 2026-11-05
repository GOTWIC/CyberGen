"""Plot an area of a built city (the access fixes' plan views): water, megasite reserves
(dashed), roads by class (raised ones hatched), junctions, lots, open spaces (labelled by
id; one with no way in red), building masses on the ground (those over it dotted), ground
structures, walkways (park paths red, door paths magenta, stairs and underpasses blue,
bridges cyan), entrances (a walled-in one a red cross).
usage: plot_access.py CITY_MODEL X Y R OUT.png [TITLE]"""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402

m = json.load(open(sys.argv[1], encoding="utf-8"))
x, y, r = map(float, sys.argv[2:5])
win = box(x - r, y - r, x + r, y + r)
COL = {"highway": "#f5d08a", "avenue": "#e0d0a0", "street": "#dddddd", "alley": "#e8e8e8",
       "service": "#e8e8e8", "pedestrian": "#f0e8d8", "footbridge": "#a0d8e8"}


def poly(p):
    return Polygon(p["exterior"], p.get("holes") or [])


fig, ax = plt.subplots(figsize=(10, 10))


def fill(g, **kw):
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path

    if g.is_empty or not g.intersects(win):
        return
    g = g.intersection(win.buffer(5))
    for part in getattr(g, "geoms", [g]):
        if part.geom_type != "Polygon" or part.is_empty:
            continue
        verts, codes = [], []
        for ring in [part.exterior, *part.interiors]:
            cs = list(ring.coords)
            verts += cs
            codes += [Path.MOVETO] + [Path.LINETO] * (len(cs) - 2) + [Path.CLOSEPOLY]
        kw2 = dict(kw)
        lw = kw2.pop("lw", 0)
        color = kw2.pop("color", None)
        ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, lw=lw, **kw2))


for e in m.get("seas", []):
    for p in e["polygons"]:
        fill(poly(p), color="#bfe0f5", lw=0)
for key in ("rivers", "channels", "waterways"):
    for e in m.get(key, []):
        fill(poly(e["polygon"]), color="#bfe0f5", lw=0)
for ms_ in m.get("megasites", []):
    if ms_.get("polygon"):
        g = poly(ms_["polygon"])
        if g.intersects(win):
            xs, ys = g.exterior.xy
            ax.plot(xs, ys, color="#a0a", lw=1.0, ls="--")
for s in sorted(m["road_segments"], key=lambda s: max(abs(z["z"]) for z in s["z_profile"])
                if s.get("z_profile") else 0.0):
    ln = LineString([p[:2] for p in s["centerline"]])
    if not ln.intersects(win.buffer(40)):
        continue
    zmax = max((abs(z["z"]) for z in s.get("z_profile") or []), default=0.0)
    kw = {"color": COL.get(s["road_class"], "#ddd"), "lw": 0}
    if zmax > 4.0:
        kw.update(hatch="///", edgecolor="#a66", alpha=0.7)
    fill(ln.buffer(s["width_m"] / 2, cap_style="flat"), **kw)
for j in m["junctions"]:
    if j.get("polygon") and not j.get("level"):
        fill(poly(j["polygon"]), color="#ccc", lw=0)
for lt in m["lots"]:
    if lt.get("level"):
        continue
    g = poly(lt["polygon"])
    if g.intersects(win):
        xs, ys = g.exterior.xy
        ax.plot(xs, ys, color="#c80", lw=0.7)
for o in m["open_spaces"]:
    g = poly(o["polygon"])
    if not g.intersects(win) or o.get("level"):
        continue
    a = o.get("attrs") or {}
    fill(g, color="#f44" if a.get("access") == "none" else "#9d9", alpha=0.6, lw=0)
    c = g.representative_point()
    if win.contains(c):
        ax.text(c.x, c.y, o["id"].split(".", 1)[-1], fontsize=6, ha="center")
for b in m["buildings"]:
    if b.get("level"):
        continue
    floor = float((b.get("attrs") or {}).get("deck_top_m", 0.0)) if b.get("level") else 0.0
    for ms in b["masses"]:
        g = poly(ms["footprint"])
        if ms["z0_m"] - floor < 2.5:
            fill(g, color="#55a", alpha=0.35, lw=0)
        elif g.intersects(win):          # (a mass over the ground: its outline)
            xs, ys = g.exterior.xy
            ax.plot(xs, ys, color="#55a", lw=0.6, ls=":")
for st in m["structures"]:
    if st.get("footprint") and st["kind"] in ("trench", "column", "pylon", "canopy"):
        fill(poly(st["footprint"]), color="#444", alpha=0.6, lw=0)
for w in m["walkways"]:
    if w.get("level") or len(w["line"]) < 2:
        continue
    ln = LineString([p[:2] for p in w["line"]])
    if not ln.intersects(win):
        continue
    a = w.get("attrs") or {}
    c = "r" if a.get("open_space") else "m" if a.get("door") or a.get("lobby") else \
        "b" if w["kind"] in ("stairs", "underpass", "escalator") else \
        "c" if w["kind"] in ("bridge", "footbridge", "elevated") else "k"
    xs, ys = ln.xy
    ax.plot(xs, ys, color=c, lw=1.4 if c != "k" else 0.8)
for b in m["buildings"]:
    wi = set((b.get("attrs") or {}).get("walled_in") or ())
    for k, e in enumerate(b["entrances"]):
        if win.contains(Point(e["position"][:2])):
            ax.plot(e["position"][0], e["position"][1], "rX" if k in wi else "m^",
                    ms=9 if k in wi else 4)
ax.set_xlim(x - r, x + r)
ax.set_ylim(y - r, y + r)
ax.set_aspect("equal")
if len(sys.argv) > 6:
    ax.set_title(sys.argv[6])
fig.savefig(sys.argv[5], dpi=90, bbox_inches="tight")
print("ok", sys.argv[5])
