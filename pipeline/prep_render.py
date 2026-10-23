import json
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union

geo = json.load(open("geometry.json"))
land = unary_union([Polygon(p["exterior"], p["holes"]) for p in geo["land"]])

def polys(g):
    if g.is_empty: return []
    gs = [g] if g.geom_type == "Polygon" else [x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon"]
    return [dict(exterior=[list(c) for c in p.simplify(0.05).exterior.coords[:-1]],
                 holes=[[list(c) for c in r.coords[:-1]] for r in p.simplify(0.05).interiors]) for p in gs if p.area > 1]

out = dict(land=polys(land), roads={}, bridges=[], buildings=geo["buildings"])
all_bridge = []
for cat in ("highway", "avenue", "street", "elevated"):
    gs = [LineString(r["points"]).buffer(r["width"] / 2, cap_style="flat", join_style="round")
          for r in geo["roads"] if r["cat"] == cat]
    if not gs: continue
    u = unary_union(gs)
    out["roads"][cat] = polys(u.intersection(land))
    all_bridge.append(u.difference(land))
if all_bridge:
    out["bridges"] = polys(unary_union(all_bridge))
json.dump(out, open("render_geo.json", "w"))
print({k: (len(v) if isinstance(v, list) else {c: len(x) for c, x in v.items()}) for k, v in out.items()})
