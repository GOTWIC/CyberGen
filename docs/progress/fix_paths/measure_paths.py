"""Park paths, open space access and entrance links in a city_model.json.

usage: python -I measure_paths.py CITY_MODEL_JSON
"""
import json
import sys
from collections import Counter

import shapely
import shapely.ops
from shapely.geometry import LineString, Point, Polygon

PATH_KINDS = ("park", "plaza", "pocket_park", "market", "garden", "promenade", "beach")
HEAD = 2.5


def poly(p):
    if p is None:
        return None
    if isinstance(p, dict):
        return Polygon(p["exterior"], p.get("holes") or [])
    return Polygon(p)


m = json.load(open(sys.argv[1], encoding="utf-8"))
blds = m["buildings"]
masses = []   # (geom, bid, level, z0, z1)
for b in blds:
    for ms in b["masses"]:
        g = poly(ms["footprint"])
        if g is None or g.is_empty:
            continue
        masses.append((g.buffer(-0.1), b["id"], b.get("level", 0), ms["z0_m"], ms["z1_m"]))
mtree = shapely.STRtree([x[0] for x in masses])
open_ids = {o["id"] for o in m["open_spaces"]}
lots = [(poly(l["polygon"]).buffer(-0.1), l["id"], l.get("level", 0)) for l in m["lots"]]
ltree = shapely.STRtree([x[0] for x in lots])
# which lots carry a building (the rest are yards, open)
built = {b.get("lot_id") for b in blds}


def through_mass(line, z, level, own=None, tol=0.1):
    hits = []
    for i in mtree.query(line, predicate="intersects").tolist():
        g, bid, lv, z0, z1 = masses[i]
        if lv != level or bid == own:
            continue
        if z0 >= z + HEAD or z1 <= z + 0.01:
            continue
        L = line.intersection(g).length
        if L > tol:
            hits.append(bid)
    return hits


def across_lot(line, level, tol=0.5):
    hits = []
    for i in ltree.query(line, predicate="intersects").tolist():
        g, lid, lv = lots[i]
        if lv != level:
            continue
        if line.intersection(g).length > tol:
            hits.append(lid)
    return hits


walks = m["walkways"]
park = [w for w in walks if (w.get("attrs") or {}).get("open_space")]
cross_lot = thru_bld = 0
for w in park:
    ln = LineString([p[:2] for p in w["line"]])
    lv = w.get("level", 0)
    z = w["line"][0][2]
    if across_lot(ln, lv):
        cross_lot += 1
    if through_mass(ln, z, lv):
        thru_bld += 1
print(f"park paths: {len(park)}; crossing a lot: {cross_lot}; through a building: {thru_bld}")

# open space access
wlines = [LineString([p[:2] for p in w["line"]]) if len(w["line"]) > 1 and
          w["line"][0][:2] != w["line"][-1][:2] else Point(w["line"][0][:2]) for w in walks]
wtree = shapely.STRtree(wlines)
has_path = Counter(w["attrs"]["open_space"] for w in park)
pk = [o for o in m["open_spaces"] if o["kind"] in PATH_KINDS]
no_path = [o for o in pk if o["id"] not in has_path]
no_walk = []
for o in pk:
    g = poly(o["polygon"]).buffer(0)
    hit = [i for i in wtree.query(g, predicate="dwithin", distance=3.5).tolist()
           if walks[i].get("level", 0) == o.get("level", 0)]
    if not hit and o["id"] not in has_path and not o.get("level"):
        no_walk.append(o)
print(f"open spaces with paths' kinds: {len(pk)}; with no park path: {len(no_path)}; "
      f"with no way in (no path, no walkway within 3.5 m): {len(no_walk)} {Counter(o['kind'] for o in no_walk)}")

# entrance links
wby = {w["id"]: w for w in walks}
n_e = bad_e = 0
bad_ids = []
for b in blds:
    for e in b["entrances"]:
        if not e.get("walkway_id") or e["walkway_id"] not in wby:
            continue
        n_e += 1
        w = wby[e["walkway_id"]]
        p = Point(e["position"])
        wl = LineString([q[:2] for q in w["line"]]) if len(w["line"]) > 1 else \
            Point(w["line"][0][:2])
        q = shapely.ops.nearest_points(wl, p)[0]
        if q.distance(p) < 0.05:
            continue
        seg = LineString([p, q])
        if through_mass(seg, 0.0, b.get("level", 0), own=b["id"]):
            bad_e += 1
            bad_ids.append(b["id"])
print(f"entrances with a walkway: {n_e}; linking through another building: {bad_e}")
# every walkway through a mass (the new check's measure, minus own-building links)
bad_w = Counter()
for w in walks:
    a = w.get("attrs") or {}
    if w["kind"] in ("elevator", "skybridge"):
        continue
    if len(w["line"]) < 2:
        continue
    ln = LineString([p[:2] for p in w["line"]])
    if ln.length < 1e-6:
        continue
    z = min(p[2] for p in w["line"])
    own = a.get("building")
    if through_mass(ln, z, w.get("level", 0), own=own):
        bad_w[(w["kind"], tuple(sorted(k for k in a if k != "split_of")))] += 1
print("walkways through a mass (not their own building):", sum(bad_w.values()),
      dict(bad_w))
st = {}
try:
    import os
    rep = json.load(open(os.path.join(os.path.dirname(sys.argv[1]), "report.json"),
                         encoding="utf-8"))
    s = rep.get("stats", {})
    def find(d, k):
        if isinstance(d, dict):
            if k in d:
                return d[k]
            for v in d.values():
                r = find(v, k)
                if r is not None:
                    return r
        return None
    for k in ("passages", "open_paths_bent", "open_no_access", "walkways_led_round_lots",
              "walkways_in_lots", "entrances_relinked", "entrances_moved", "entrances_blocked"):
        st[k] = find(s, k)
    st["checks"] = sum(1 for c in rep["checks"]), sum(1 for c in rep["checks"] if c["passed"])
except Exception as ex:
    st["err"] = str(ex)
print("JSON", json.dumps({"park_paths": len(park), "paths_cross_lot": cross_lot,
                          "paths_through_bld": thru_bld, "open_kinds": len(pk),
                          "open_no_way_in": len(no_walk), "entrances": n_e,
                          "entrances_through_bld": bad_e,
                          "walkways_through_bld": sum(bad_w.values()), **st}))
