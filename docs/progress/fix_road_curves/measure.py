"""Facet measures of a built city's roads: centerline vertices by role, and the pavement map's
edges (chord sag per vertex: (min adjacent chord / 2) tan(turn / 4), the sag of the chord of a
circle sampled at that turn)."""
import json
import math
import sys
from collections import defaultdict


def turn(a, b, c):
    ux, uy = b[0] - a[0], b[1] - a[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    nu, nv = math.hypot(ux, uy), math.hypot(vx, vy)
    if nu < 1e-9 or nv < 1e-9:
        return 0.0, nu, nv
    cs = max(-1.0, min(1.0, (ux * vx + uy * vy) / (nu * nv)))
    return math.acos(cs), nu, nv


def merged(pts, tol=math.radians(0.05)):
    """The polyline without vertices on a straight run (the map's 4 m stations)."""
    out = [pts[0]]
    for b, c in zip(pts[1:], pts[2:]):
        if turn(out[-1], b, c)[0] >= tol:
            out.append(b)
    out.append(pts[-1])
    return out


def sags(pts, wmax=0.0, lim=math.radians(45.0)):
    pts = merged(pts) if len(pts) > 2 else pts
    out = []
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        th, l1, l2 = turn(a, b, c)
        if th < math.radians(0.25) or th > lim:
            continue
        L = min(l1, l2)
        R = L / (2.0 * math.sin(th / 2.0)) if th > 0 else 1e9
        s = (L / 2.0) * math.tan(th / 4.0)
        out.append((s * (R + wmax) / R if R > 0 else s, th, L))
    return out


def pct(v, q):
    if not v:
        return 0.0
    v = sorted(v)
    return v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))]


def main(path):
    m = json.load(open(path))
    by = defaultdict(list)
    nv = defaultdict(int)
    for s in m["road_segments"]:
        role = s["attrs"].get("role", "?")
        key = f"{s['road_class']}/{role}"
        w = s["width_m"] / 2.0
        for sg, th, L in sags(s["centerline"], w):
            by[key].append(sg)
        nv[key] += len(s["centerline"])
    allv = [x for v in by.values() for x in v]
    print(f"centerlines: {sum(nv.values())} vertices, {len(allv)} curve vertices; outer-edge sag "
          f"p50 {pct(allv, .5)*100:.1f} p95 {pct(allv, .95)*100:.1f} p99 {pct(allv, .99)*100:.1f} "
          f"max {max(allv)*100:.1f} cm; over 2 cm {sum(1 for x in allv if x > .02)}")
    rows = sorted(by.items(), key=lambda kv: -sum(1 for x in kv[1] if x > .02))
    for k, v in rows[:25]:
        print(f"  {k:32s} vtx {nv[k]:6d} curve {len(v):6d} >2cm {sum(1 for x in v if x > .02):6d} "
              f"p95 {pct(v, .95)*100:6.1f} max {max(v)*100:7.1f}")
    pn = m["pavement_net"]
    P = {v["id"]: v["p"] for v in pn["vertices"]}
    owner = {}
    for f in m["pavement"]:
        for r in f["rings"]:
            for e in r:
                owner.setdefault(e.lstrip("-"), set()).add(f["kind"])
    ek = defaultdict(list)
    for e in pn["edges"]:
        kinds = owner.get(e["id"], set())
        who = "junction" if kinds & {"junction", "corner", "bulb"} else \
            ("bend" if "bend" in kinds else "road")
        pts = [P[v] for v in e["v"]]
        for sg, th, L in sags(pts):
            ek[(e["kind"], who)].append(sg)
    print(f"pavement: {len(pn['vertices'])} vertices, {len(pn['edges'])} edges, "
          f"{len(m['pavement'])} faces")
    for k in sorted(ek):
        v = ek[k]
        print(f"  {k[0]:6s} {k[1]:9s} curve vtx {len(v):7d} >2cm {sum(1 for x in v if x > .02):6d} "
              f">10cm {sum(1 for x in v if x > .10):5d} "
              f"p50 {pct(v, .5)*100:5.1f} p95 {pct(v, .95)*100:6.1f} p99 {pct(v, .99)*100:6.1f} "
              f"max {max(v)*100:7.1f} cm")


if __name__ == "__main__":
    main(sys.argv[1])
