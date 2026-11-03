"""Plot lots, buildings, open spaces, road ROW and walkways around a point.
usage: plot_area.py CITY_MODEL X Y R OUT.png"""
import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString, box

m = json.load(open(sys.argv[1], encoding="utf-8"))
x, y, r = map(float, sys.argv[2:5])
win = box(x - r, y - r, x + r, y + r)
def poly(p): return Polygon(p["exterior"], p.get("holes") or [])
fig, ax = plt.subplots(figsize=(10, 10))
def fill(g, **kw):
    if g.is_empty or not g.intersects(win): return
    xs, ys = g.exterior.xy
    ax.fill(xs, ys, **kw)
for s in m["road_segments"]:
    l = LineString(s["centerline"])
    if l.intersects(win.buffer(30)):
        fill(l.buffer(s["width_m"] / 2, cap_style="flat"), color="#ddd", lw=0)
for j in m["junctions"]:
    if j.get("polygon"): fill(poly(j["polygon"]), color="#ccc", lw=0)
for l in m["lots"]:
    if l.get("level"): continue
    g = poly(l["polygon"])
    if g.intersects(win):
        xs, ys = g.exterior.xy
        ax.plot(xs, ys, color="#c80", lw=0.8)
for o in m["open_spaces"]:
    fill(poly(o["polygon"]), color="#9d9", alpha=0.6, lw=0)
for b in m["buildings"]:
    if b.get("level"): continue
    for ms in b["masses"]:
        if ms["z0_m"] < 2.5:
            fill(poly(ms["footprint"]), color="#55a", alpha=0.5, lw=0)
for w in m["walkways"]:
    if w.get("level"): continue
    l = LineString([p[:2] for p in w["line"]]) if len(w["line"]) > 1 else None
    if l is None or not l.intersects(win): continue
    a = w.get("attrs") or {}
    c = "r" if a.get("open_space") else ("m" if a.get("building") else "k")
    xs, ys = l.xy
    ax.plot(xs, ys, color=c, lw=1.2)
for b in m["buildings"]:
    for e in b["entrances"]:
        if win.contains(Polygon([(e["position"][0]-.1,e["position"][1]-.1),(e["position"][0]+.1,e["position"][1]-.1),(e["position"][0],e["position"][1]+.1)])):
            ax.plot(*e["position"], "m^", ms=4)
ax.set_xlim(x - r, x + r); ax.set_ylim(y - r, y + r); ax.set_aspect("equal")
fig.savefig(sys.argv[5], dpi=90); print("ok")
