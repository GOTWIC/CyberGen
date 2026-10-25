"""Skybridges (M3): walkways between facing facades of two buildings.

A candidate joins two masses that both reach the bridge level, from a point on a facade edge
of one straight across to a facing (antiparallel) edge of the other: length 8 to 80 m,
within 14 degrees of perpendicular to both facades, deck level on the floor grid of both
buildings (a common multiple of their floor heights). The deck clears roads by 5.5 m (over a
road's highest point), water by its navigable clearance, and passes through no other
building mass. Complexes ask for their bridges first (twin towers, clusters, bridged pairs,
megabuilding campuses); then each district adds bridges between its tall buildings by its
`skybridge_density`, shortest first, at most two or three per building and never crossing
another bridge at the same level. Grimy districts get low catwalks and cable bridges, the
megablocks open decks, plus open decks between neighboring podiums below their roofs (the
street-scale deck network). Bridges join the walkway graph later (the driver adds the deck and
an elevator at each end).
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from . import geom as G
from . import massing as MS

q = G.q
MIN_LEN_M = 8.0
MAX_LEN_M = 80.0
PERP_COS = 0.97          # within about 14 degrees of perpendicular
DECK_M = 1.0             # structure depth under the deck level
ROAD_CLEAR_M = 5.5
EXCLUDE_ROLES = ("spire", "deck", "dock", "ramp", "platform", "leg_frame", "wheel", "shack",
                 "mechanical", "antenna", "span", "plinth", "obelisk", "shaft")
WIDTH_M = {"enclosed": 5.0, "open_deck": 7.0, "stack": 6.0, "catwalk": 1.6, "cable": 1.2}
LEVEL_M = {"enclosed": 4.0, "open_deck": 3.0, "stack": 4.0, "catwalk": 2.5, "cable": 2.5}

# (kind, minimum building height, target level as share of the lower building, max per
# building, max length)
DISTRICT_RULES = {
    "corporate_core": ("enclosed", 60.0, (0.35, 0.65), 3, 80.0),
    "megablock_residential": ("open_deck", 60.0, (0.3, 0.7), 3, 80.0),
    "midtown_mixed": ("enclosed", 30.0, (0.4, 0.75), 2, 60.0),
    "transit_hub": ("enclosed", 30.0, (0.3, 0.6), 2, 70.0),
    "entertainment_market": ("open_deck", 14.0, (0.45, 0.8), 2, 30.0),
    "old_town": ("catwalk", 9.0, (0.0, 0.0), 2, 22.0),
    "research_campus": ("enclosed", 15.0, (0.4, 0.7), 2, 60.0),
    "residential_heights": ("enclosed", 20.0, (0.4, 0.7), 1, 40.0),
}


def floor_step(fa: float, fb: float) -> float | None:
    """Smallest level step on both floor grids (cm arithmetic), None when over 40 m."""
    a, b = int(round(fa * 100)), int(round(fb * 100))
    if a <= 0 or b <= 0:
        return None
    lcm = a * b // math.gcd(a, b)
    return lcm / 100.0 if lcm <= 4000 else None


def _masses(rec) -> list:
    return [(i, m) for i, m in enumerate(rec["masses"])
            if m[4] == "prism" and m[3] not in EXCLUDE_ROLES]


def _facing(pa, pb, width: float, max_len: float) -> list:
    """(length, A, B) for facing edge pairs of two footprints."""
    out = []
    ea = MS.ring_edges(pa)
    eb = MS.ring_edges(pb)
    for a1, a2 in ea:
        dx, dy = a2[0] - a1[0], a2[1] - a1[1]
        La = math.sqrt(dx * dx + dy * dy)
        if La < width + 1.0:
            continue
        da = (dx / La, dy / La)
        na = (da[1], -da[0])
        for b1, b2 in eb:
            ex, ey = b2[0] - b1[0], b2[1] - b1[1]
            Lb = math.sqrt(ex * ex + ey * ey)
            if Lb < width + 1.0:
                continue
            db = (ex / Lb, ey / Lb)
            nb = (db[1], -db[0])
            if na[0] * nb[0] + na[1] * nb[1] > -PERP_COS:
                continue
            s1 = (b1[0] - a1[0]) * na[0] + (b1[1] - a1[1]) * na[1]
            s2 = (b2[0] - a1[0]) * na[0] + (b2[1] - a1[1]) * na[1]
            if s1 < MIN_LEN_M - 0.5 or s2 < MIN_LEN_M - 0.5 or min(s1, s2) > max_len:
                continue
            t1 = (b1[0] - a1[0]) * da[0] + (b1[1] - a1[1]) * da[1]
            t2 = (b2[0] - a1[0]) * da[0] + (b2[1] - a1[1]) * da[1]
            lo = max(0.0, min(t1, t2))
            hi = min(La, max(t1, t2))
            if hi - lo < width + 1.0:
                continue
            t = (lo + hi) / 2.0
            A = (a1[0] + da[0] * t, a1[1] + da[1] * t)
            cr = na[0] * db[1] - na[1] * db[0]
            if abs(cr) < 1e-9:
                continue
            s = ((b1[0] - A[0]) * db[1] - (b1[1] - A[1]) * db[0]) / cr
            if not (MIN_LEN_M <= s <= max_len):
                continue
            B = (A[0] + na[0] * s, A[1] + na[1] * s)
            out.append((s, (q(A[0]), q(A[1])), (q(B[0]), q(B[1])), na, da))
    out.sort(key=lambda c: (round(c[0], 6), c[1], c[2]))
    return out


def deck_poly(A, B, na, da, width: float, trim: float = 0.3) -> Polygon:
    """Plan of the deck between A and B, trimmed at the ends (so it does not touch the
    facades)."""
    h = width / 2.0
    ax, ay = A[0] + na[0] * trim, A[1] + na[1] * trim
    bx, by = B[0] - na[0] * trim, B[1] - na[1] * trim
    pts = [(ax - da[0] * h, ay - da[1] * h), (bx - da[0] * h, by - da[1] * h),
           (bx + da[0] * h, by + da[1] * h), (ax + da[0] * h, ay + da[1] * h)]
    return Polygon([(q(x), q(y)) for x, y in pts])


class Space:
    """Obstacles of a district: building masses, road rights of way, water, decks."""

    def __init__(self, cx, recs):
        self.masses = []
        for r in recs:
            for i, m in enumerate(r["masses"]):
                self.masses.append((r["id"], i, m))
        self.tree = shapely.STRtree([m[2][0] for m in self.masses]) if self.masses else None
        self.roads = [(rid, G.qpoly(LineString(line).buffer(w / 2.0, cap_style="flat",
                                                            join_style="mitre")), zmax)
                      for rid, cls, line, w, zmax in cx.roads]
        self.rtree = shapely.STRtree([r[1] for r in self.roads]) if self.roads else None
        self.water = list(cx.water)
        self.wtree = shapely.STRtree([w[1] for w in self.water]) if self.water else None
        self.decks: list = []

    def blocked(self, poly, z0: float, z1: float) -> bool:
        if self.tree is not None:
            for k in sorted(int(i) for i in self.tree.query(poly, predicate="intersects")):
                _, _, m = self.masses[k]
                if m[1] < z1 - 1e-6 and m[2] > z0 + 1e-6:
                    if G.area1(G.inter(poly, m[0])) > 0.01:
                        return True
        for dp, dz0, dz1 in self.decks:
            if dz0 < z1 and dz1 > z0 and poly.intersects(dp):
                return True
        return False

    def base(self, poly) -> tuple[float, list, float]:
        """(lowest deck level, ids crossed, base level below)."""
        need = 2.5 + DECK_M
        crosses = []
        under = 0.0
        if self.rtree is not None:
            for k in sorted(int(i) for i in self.rtree.query(poly, predicate="intersects")):
                rid, rp, zmax = self.roads[k]
                crosses.append(rid)
                need = max(need, zmax + ROAD_CLEAR_M + DECK_M)
                under = max(under, zmax)
        if self.wtree is not None:
            for k in sorted(int(i) for i in self.wtree.query(poly, predicate="intersects")):
                wid, wp, clear = self.water[k]
                crosses.append(wid)
                need = max(need, clear + DECK_M)
        return need, sorted(set(crosses)), under


def connect(space: Space, ra, rb, zt: float, kind: str, levels: int, width: float,
            max_len: float = MAX_LEN_M, z_any: bool = True) -> dict | None:
    """The bridge between buildings ra and rb nearest level zt, or None."""
    step = floor_step(ra["fh"], rb["fh"])
    if step is None:
        return None
    lh = LEVEL_M[kind] if levels == 1 else max(LEVEL_M[kind], step)
    span = levels * lh
    ma, mb = _masses(ra), _masses(rb)
    top = min(max((m[2] for _, m in ma), default=0.0), max((m[2] for _, m in mb), default=0.0))
    zs = []
    k = 1
    while k * step + span <= top - 1e-6 and k < 400:
        zs.append(q(k * step))
        k += 1
    if not zs:
        return None
    zs.sort(key=lambda z: (round(abs(z - zt), 6), z))
    if not z_any:
        zs = zs[:3]
    cache: dict = {}
    for z in zs[:12]:
        za = [(i, m) for i, m in ma if m[1] <= z + 1e-6 and m[2] >= z + span - 1e-6]
        zb = [(i, m) for i, m in mb if m[1] <= z + 1e-6 and m[2] >= z + span - 1e-6]
        cands = []
        for i, m in za:
            for j, n in zb:
                key = (i, j)
                if key not in cache:
                    cache[key] = _facing(m[0], n[0], width, max_len)
                cands += cache[key][:2]
        cands.sort(key=lambda c: (round(c[0], 6), c[1], c[2]))
        for L, A, B, na, da in cands[:4]:
            poly = deck_poly(A, B, na, da, width)
            if not poly.is_valid:
                continue
            need, crosses, under = space.base(poly)
            if z < need - 1e-6:
                continue
            if space.blocked(poly, z - DECK_M, z + span):
                continue
            return {"building_ids": (ra["id"], rb["id"]), "line": [A, B], "z_m": z,
                    "width_m": width, "levels": levels, "level_height_m": q(lh),
                    "kind": kind, "length_m": q(L), "clearance_m": q(z - DECK_M - under),
                    "crosses": crosses, "poly": poly, "span": (q(z - DECK_M), q(z + span))}
    return None


def district_skybridges(cx, out: dict) -> None:
    recs = [r for r in out["buildings"] if r["masses"]]
    by_id = {r["id"]: r for r in recs}
    space = Space(cx, recs)
    chosen = []
    deg: dict = {}
    for f in out.get("forced", []):
        ra, rb = by_id.get(f["a"]), by_id.get(f["b"])
        if ra is None or rb is None:
            continue
        sb = connect(space, ra, rb, f["z"], f["kind"], f["levels"], f["width"])
        if sb is None and f["levels"] > 1:
            sb = connect(space, ra, rb, f["z"], "enclosed", 1, f["width"])
        if sb is None:
            sb = connect(space, ra, rb, f["z"], "enclosed", 1, 3.5)
        if sb is None:
            cx.notes.append(f"{f['why']}: no skybridge fits between {f['a']} and {f['b']}")
            continue
        sb["property_id"] = f["property_id"]
        _accept(space, chosen, deg, sb)
    rule = DISTRICT_RULES.get(cx.archetype)
    dens = cx.skybridge_density
    if rule is not None and dens > 0:
        kind, h_min, (f0, f1), max_deg, max_len = rule
        if kind == "catwalk" and cx.grime < 0.5:
            kind = "enclosed"
        tall = [r for r in recs if r["height"] >= h_min and not r.get("landmark")]
        want = int(round(dens * len(tall) * 0.3))
        _density(cx, space, tall, by_id, chosen, deg, kind, f0, f1, max_deg, max_len, want)
    if cx.archetype in PODIUM_DECKS and dens > 0:
        _podium_decks(cx, space, recs, chosen, int(round(dens * len(recs) * 0.8)))
    for k, sb in enumerate(chosen):
        sb["id"] = f"{cx.did}.sb{k + 1:03d}"
    out["skybridges"] = chosen


PODIUM_DECKS = ("megablock_residential",)


def _podium_decks(cx, space, recs, chosen, want) -> None:
    """Open decks between the podium roofs of neighbors (across a street or a court), a
    level below the lower podium's top: the street-level deck network of the megablocks.
    At most two per building, shortest first."""
    pods = []
    for r in recs:
        ps = [m for m in r["masses"] if m[3] == "podium" and m[1] <= 0.0]
        if ps:
            pods.append((r, ps[0][0], ps[0][2]))
    if want <= 0 or len(pods) < 2:
        return
    arr = np.array([p[1] for p in pods], dtype=object)
    tree = shapely.STRtree(arr)
    ia, ib = tree.query(arr, predicate="dwithin", distance=40.0)
    pairs = sorted({(min(a, b), max(a, b)) for a, b in zip(ia.tolist(), ib.tolist()) if a != b})
    cands = []
    for a, b in pairs:
        d = G.dist(pods[a][1], pods[b][1])
        if d < MIN_LEN_M - 0.5:
            continue
        rng = cx.rng(81, a, b)
        cands.append((round(d + 8.0 * float(rng.random()), 6), a, b))
    cands.sort()
    pdeg: dict = {}
    n = 0
    for d, a, b in cands:
        if n >= want:
            break
        ra, rb = pods[a][0], pods[b][0]
        if pdeg.get(ra["id"], 0) >= 2 or pdeg.get(rb["id"], 0) >= 2:
            continue
        zt = min(pods[a][2], pods[b][2]) - LEVEL_M["open_deck"] - 1.0
        sb = connect(space, ra, rb, zt, "open_deck", 1, WIDTH_M["open_deck"], max_len=40.0,
                     z_any=False)
        if sb is None or sb["z_m"] + LEVEL_M["open_deck"] > min(pods[a][2], pods[b][2]):
            continue
        sb["property_id"] = None
        space.decks.append((sb["poly"], sb["span"][0], sb["span"][1]))
        chosen.append(sb)
        for x in (ra["id"], rb["id"]):
            pdeg[x] = pdeg.get(x, 0) + 1
        n += 1


def _accept(space, chosen, deg, sb) -> None:
    chosen.append(sb)
    space.decks.append((sb["poly"], sb["span"][0], sb["span"][1]))
    for b in sb["building_ids"]:
        deg[b] = deg.get(b, 0) + 1


def _density(cx, space, tall, by_id, chosen, deg, kind, f0, f1, max_deg, max_len, want):
    if want <= 0 or len(tall) < 2:
        return
    tops = []
    for r in tall:
        ms = _masses(r)
        if not ms:
            continue
        top = max(ms, key=lambda im: (im[1][2], G.area1(im[1][0])))
        tops.append((r, top[1][0]))
    if len(tops) < 2:
        return
    arr = np.array([t[1] for t in tops], dtype=object)
    tree = shapely.STRtree(arr)
    ia, ib = tree.query(arr, predicate="dwithin", distance=max_len)
    pairs = sorted({(min(a, b), max(a, b)) for a, b in zip(ia.tolist(), ib.tolist()) if a != b})
    cands = []
    for a, b in pairs:
        ra, rb = tops[a][0], tops[b][0]
        if ra.get("property_id") == rb.get("property_id"):
            continue
        d = G.dist(tops[a][1], tops[b][1])
        if d < MIN_LEN_M - 0.5:
            continue
        rng = cx.rng(80, a, b)
        h = min(ra["height"], rb["height"])
        if kind in ("catwalk", "cable"):
            zt = MS.uniform(rng, 6.5, 9.5)
            k = "cable" if float(rng.random()) < 0.3 else "catwalk"
        else:
            zt = h * MS.uniform(rng, f0, f1)
            k = kind
        cands.append((round(d + 12.0 * float(rng.random()), 6), a, b, zt, k))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    n = 0
    tries = 0
    for d, a, b, zt, k in cands:
        if n >= want or tries >= 3 * want + 30:
            break
        ra, rb = tops[a][0], tops[b][0]
        if deg.get(ra["id"], 0) >= max_deg or deg.get(rb["id"], 0) >= max_deg:
            continue
        tries += 1
        sb = connect(space, ra, rb, zt, k, 1, WIDTH_M[k], max_len=max_len, z_any=False)
        if sb is None:
            continue
        sb["property_id"] = None
        _accept(space, chosen, deg, sb)
        n += 1
