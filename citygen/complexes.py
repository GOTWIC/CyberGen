"""Landmarks and complexes (M3).

Landmarks of the spec (megatower, spire, arcology, observation tower, ferris wheel, monument,
temple, or any other kind as a tapering tower) take a whole block near the district focus,
or for the open-air kinds (ferris wheel, monument, observation tower) a park, plaza or
promenade, with their own massing: the megatower is a three-armed plan (arms 120 degrees
apart) in setback tiers with a spire, a spire tower an octagon in tapering tiers, an
arcology a stepped ziggurat with an atrium. Several landmarks of one district spread around
its focus.

Complexes are built on M2's merged lot groups: twin towers (two mirrored towers on a shared
podium, a two-level skybridge between them), tower clusters (three or four towers of stepped
heights on a shared podium, bridges between neighbors), megabuilding campuses (a
megabuilding with satellite towers, linked by open decks and bridges), campuses (low
buildings around a lawn, joined by covered walkways), bridged pairs (two buildings on facing
lots, skybridges across the street) and straddle buildings (upper floors spanning the street,
or a canal and its quay roads, at least 5.5 m clear of the roads and at the navigable
clearance over the water). M2 tries its candidate groups with these builders (`probe`), so a
complex is built on its own group; the relocation below is the fallback.
"""

from __future__ import annotations

import dataclasses
import math

from shapely.geometry import LineString, Point, Polygon

from . import buildings as BL
from . import dmath as M
from . import forms as FM
from . import geom as G
from . import massing as MS
from . import streets as ST

q = G.q
OPEN_AIR = ("ferris_wheel", "monument", "observation_tower")
OPEN_HOSTS = ("park", "plaza", "promenade", "beach", "green", "pocket_park")
LANDMARK_SPREAD_M = 140.0
WHEEL_CLEAR_M = 6.5   # a wheel rim lower than this (5.5 m road clearance + 1 m) stays on its site


def _union(polys):
    if len(polys) == 1:
        return polys[0]
    ps = G.parts(G.union(polys))
    return ps[0] if ps else Polygon()


def _fronts(lots) -> list:
    out = []
    for lot in lots:
        out += lot["frontage"]
    return out


def _main_front(lots):
    return max(_fronts(lots), key=lambda f: (f["length_m"], f["segment_id"]))


def _lot_of(poly, lots) -> str:
    """The lot that holds most of a footprint."""
    best = None
    for lot in lots:
        a = G.area1(G.inter(poly, lot["polygon"])) if not G.apart(poly, lot["polygon"]) \
            else 0.0
        if best is None or a > best[0]:
            best = (a, lot["id"])
    return best[1]


def emit(cx, out, b, fronts, rng, bid: str, lot_ids: list, pid: str, shops=None,
         lots=None) -> dict:
    if cx.probe:
        rec = {"kind": b.kind, "fh": b.fh, "height": q(b.height), "masses": b.masses,
               "footprint": b.ground(), "attrs": dict(b.attrs)}
        rec.update({"id": bid, "lot_id": lot_ids[0], "property_id": pid,
                    "lot_ids": list(lot_ids)})
        out["buildings"].append(rec)
        return rec
    rec = BL.finish(b, cx, fronts, rng, shops)
    lot_id = _lot_of(rec["footprint"], lots) if lots and len(lots) > 1 else lot_ids[0]
    rec.update({"id": bid, "lot_id": lot_id, "property_id": pid, "lot_ids": list(lot_ids)})
    out["buildings"].append(rec)
    return rec


def prop(out, pid, kind, bids, lot_ids, owner, name=None):
    out["properties"].append({"id": pid, "complex": kind, "building_ids": bids,
                              "lot_ids": lot_ids, "owner": owner, "name": name})


def bridgeable(cx, ra: dict, rb: dict, z: float, kind: str = "enclosed",
               width: float = 5.0) -> bool:
    """Whether a skybridge fits between two new buildings (their own masses, the roads and
    the water as obstacles)."""
    from . import skybridges as SB

    space = SB.Space(cx, [ra, rb])
    return SB.connect(space, ra, rb, z, kind, 1, width) is not None or \
        SB.connect(space, ra, rb, z, "enclosed", 1, 3.5) is not None


def _drop(out, bids) -> None:
    out["buildings"] = [r for r in out["buildings"] if r["id"] not in bids]


def force(out, a: str, b: str, z: float, kind: str = "enclosed", levels: int = 1,
          width: float = 5.0, pid: str | None = None, why: str = "") -> None:
    out.setdefault("forced", []).append({"a": a, "b": b, "z": z, "kind": kind,
                                         "levels": levels, "width": width,
                                         "property_id": pid, "why": why})


# ---------------------------------------------------------------------------
# Landmarks
# ---------------------------------------------------------------------------

def _landmark_prog(cx):
    return dataclasses.replace(cx.prog, front=BL._front(6.0, 4.0, 2.0, 1.0), side=0.0)


def _y_shape(fr: MS.Frame, R: float, w: float) -> Polygon:
    """Three arms 120 degrees apart (one along +v), length R and width w, on a hexagonal
    core."""
    arms = []
    for k in range(3):
        a = M.HALF_PI + 2.0 * M.PI * k / 3.0
        f = fr.turned(a)
        arms.append(f.rect(0.0, -w / 2.0, R, w / 2.0))
    arms.append(MS.ngon(fr.ox, fr.oy, w * 0.75, 6, fr.angle))
    return _union(arms)


def megatower(cx, b: BL.Bld, region, H: float, rng) -> bool:
    fr = b.fr
    u0, v0, u1, v1 = fr.bounds(region)
    R0 = min(0.5 * min(u1 - u0, v1 - v0), 75.0)
    for cu, cv in MS.anchors_of(region, fr):
        R = R0
        while R >= 26.0:
            c = fr.moved(cu, cv)
            w = 0.42 * R
            y = _y_shape(c, R, w)
            if region.covers(y):
                return _megatower_tiers(b, c, R, w, H, region)
            R *= 0.94
    return False


def _megatower_tiers(b, c, R, w, H, region) -> bool:
    fh = b.fh
    base = MS.inset(region, 3.0)
    P = 3 * fh
    if not base.is_empty and G.area1(base) > G.area1(_y_shape(c, R, w)) * 1.15:
        b.add(base, 0.0, P, "podium")
    else:
        P = 0.0
    tiers = ((0.40, 1.0, 1.0), (0.66, 0.84, 0.92), (0.84, 0.66, 0.82), (0.92, 0.42, 0.7))
    z = P
    spire = q(H * 0.06)
    body_top = H - spire
    for frac, fR, fw in tiers:
        z1 = max(z + fh, int(body_top * frac / fh) * fh)
        b.add(_y_shape(c, R * fR, w * fw), z, z1, "tier")
        z = z1
    core = MS.ngon(c.ox, c.oy, w * 0.75 * 0.7, 6, c.angle)
    b.add(core, z, body_top, "crown")
    b.add(MS.ngon(c.ox, c.oy, 2.2, 6, c.angle), body_top, H, "spire", roof=False)
    b.attrs["arms"] = 3
    b.attrs["arm_length_m"] = q(R)
    return True


def spire(cx, b: BL.Bld, region, H: float, rng) -> bool:
    fr = b.fr
    u0, v0, u1, v1 = fr.bounds(region)
    r0 = min(0.45 * min(u1 - u0, v1 - v0), 24.0)
    for cu, cv in MS.anchors_of(region, fr):
        r = r0
        while r >= 11.0:
            x, y = fr.world(cu, cv)
            o = MS.ngon(x, y, r, 8, fr.angle + M.PI / 8.0)
            if region.covers(o):
                fh = b.fh
                body = H * 0.9
                z = 0.0
                for frac, fr_r in ((0.48, 1.0), (0.72, 0.86), (0.88, 0.72), (1.0, 0.56)):
                    z1 = max(z + fh, int(body * frac / fh) * fh)
                    b.add(MS.ngon(x, y, r * fr_r, 8, fr.angle + M.PI / 8.0), z, z1, "tier")
                    z = z1
                b.add(MS.ngon(x, y, 1.6, 8, fr.angle), z, H, "spire", roof=False)
                return True
            r *= 0.92
    return False


def arcology(cx, b: BL.Bld, region, H: float, rng) -> bool:
    base = MS.inset(region, 4.0)
    if base.is_empty:
        return False
    u0, v0, u1, v1 = b.fr.bounds(base)
    if min(u1 - u0, v1 - v0) < 90.0:
        return False
    fh = b.fh
    n = 7
    step = min(u1 - u0, v1 - v0) / (2.0 * n + 2.0)
    z = 0.0
    body = H * 0.92
    atrium = MS.inset(base, step * 3.0 + 22.0)
    for i in range(n):
        t = MS.inset(base, step * i) if i else base
        if t.is_empty:
            break
        if not atrium.is_empty and i < 3 and t.covers(atrium):
            ps = G.parts(G.diff(t, atrium))
            t = ps[0] if ps else t
        z1 = max(z + fh, int(body * (i + 1) / n / fh) * fh)
        b.add(t, z, z1, "tier")
        z = z1
    c = G.centroid(base)
    b.add(MS.ngon(c[0], c[1], 6.0, 8, b.fr.angle), z, H, "crown")
    b.attrs["atrium"] = not atrium.is_empty
    return True


def observation_tower(cx, b: BL.Bld, region, H: float, rng) -> bool:
    for cu, cv in MS.anchors_of(region, b.fr):
        x, y = b.fr.world(cu, cv)
        pod = MS.circle(x, y, 15.0)
        if region.covers(pod):
            # (M21: true circles, their arcs in the model)
            def disc(r):
                return MS.Plate(MS.Frame(x, y, 0.0), r, r, r)
            FM.put(b, disc(13.0), 0.0, 8.0, "base")
            FM.put(b, disc(6.5), 8.0, q(H * 0.78), "shaft", shape="cylinder", roof=False)
            FM.put(b, disc(15.0), q(H * 0.78), q(H * 0.86), "pod", shape="cylinder")
            FM.put(b, disc(1.2), q(H * 0.86), H, "spire", shape="cylinder", roof=False)
            return True
    return False


def ferris_wheel(cx, b: BL.Bld, region, H: float, rng, D: float | None = None) -> bool:
    """A vertical wheel (its plan a thin rim D long) on legs and a boarding platform, tried
    along the region's long axis, across it and on its diagonals."""
    D = H - 4.0 if D is None else D
    fr = b.fr
    ang0 = MS.obb_angle(region)
    u0, v0, u1, v1 = MS.Frame(fr.ox, fr.oy, ang0).bounds(region)
    diag = float(M.atan2(v1 - v0, u1 - u0))
    turns = (0.0, M.HALF_PI, diag, -diag, M.PI / 4.0, -M.PI / 4.0)
    for cu, cv in MS.anchors_of(region, fr):
        x, y = fr.world(cu, cv)
        for turn in turns:
            f = MS.Frame(x, y, ang0 + turn)
            plat = f.rect(-16.0, -8.0, 16.0, 8.0)
            rim = f.rect(-D / 2.0, -2.0, D / 2.0, 2.0)
            low = MS.ring_ground(MS.ring_info(rim, H - D, H), rim, WHEEL_CLEAR_M)
            if not (region.covers(plat) and (low.is_empty or region.covers(low))):
                continue
            if any(rim.intersects(w[1]) for w in cx.water):
                continue
            b.fr = f
            b.add(plat, 0.0, 5.0, "platform")
            b.add(rim, H - D, H, "wheel", shape="ring", roof=False)
            for s_ in (-1.0, 1.0):
                leg = f.rect(-2.0 + s_ * 12.0, -6.5, 2.0 + s_ * 12.0, -4.5)
                b.add(leg, 0.0, q(H - D / 2.0), "leg", roof=False)
            b.attrs["diameter_m"] = q(D)
            cx.rings.append((MS.ring_info(rim, H - D, H), rim))
            return True
    return False


def monument(cx, b: BL.Bld, region, H: float, rng) -> bool:
    for cu, cv in MS.anchors_of(region, b.fr):
        plinth = b.fr.rect(cu - 7.0, cv - 7.0, cu + 7.0, cv + 7.0)
        if region.covers(plinth):
            b.add(plinth, 0.0, 3.0, "plinth")
            b.add(b.fr.rect(cu - 2.0, cv - 2.0, cu + 2.0, cv + 2.0), 3.0, H, "obelisk",
                  roof=False)
            return True
    return False


def temple(cx, b: BL.Bld, region, H: float, rng) -> bool:
    """A hall on a platform under stacked roof tiers."""
    s = 15.0
    for cu, cv in MS.anchors_of(region, b.fr):
        hall = b.fr.rect(cu - s, cv - s * 0.7, cu + s, cv + s * 0.7)
        if not region.covers(hall):
            continue
        z = 0.0
        plat = b.fr.rect(cu - s - 3.0, cv - s * 0.7 - 3.0, cu + s + 3.0, cv + s * 0.7 + 3.0)
        if region.covers(plat):
            b.add(plat, 0.0, 1.5, "platform")
            z = 1.5
        tiers = 3
        for i in range(tiers):
            f = 1.0 - 0.22 * i
            z1 = q(z + (H - 1.5) * (0.45 if i == 0 else 0.55 / (tiers - 1)))
            if i == tiers - 1:
                z1 = H
            b.add(b.fr.rect(cu - s * f, cv - s * 0.7 * f, cu + s * f, cv + s * 0.7 * f), z, z1,
                  "roof_tier" if i else "hall")
            z = z1
        return True
    return False


def generic_tower(cx, b: BL.Bld, region, H: float, rng) -> bool:
    for cu, cv in MS.anchors_of(region, b.fr):
        s = 20.0
        while s >= 9.0:
            t = b.fr.rect(cu - s, cv - s, cu + s, cv + s)
            if region.covers(t):
                fh = b.fh
                z = 0.0
                for frac, f in ((0.55, 1.0), (0.8, 0.8), (1.0, 0.6)):
                    z1 = max(z + fh, int(H * 0.95 * frac / fh) * fh)
                    b.add(b.fr.rect(cu - s * f, cv - s * f, cu + s * f, cv + s * f), z, z1,
                          "tier")
                    z = z1
                b.add(b.fr.rect(cu - 1.5, cv - 1.5, cu + 1.5, cv + 1.5), z, H, "spire",
                      roof=False)
                return True
            s *= 0.9
    return False


LANDMARKS = {"megatower": megatower, "spire": spire, "arcology": arcology,
             "observation_tower": observation_tower, "ferris_wheel": ferris_wheel,
             "monument": monument, "temple": temple}
LANDMARK_USE = {"megatower": "office", "spire": "office", "arcology": "mixed",
                "observation_tower": "entertainment", "ferris_wheel": "entertainment",
                "monument": "civic", "temple": "religious"}


def _target(cx, i: int, n: int):
    if i == 0:
        return cx.focus
    a = M.PI / 6.0 + 2.0 * M.PI * (i - 1) / max(n - 1, 1)
    r = 0.45 * cx.radius
    return (cx.focus[0] + r * float(M.cos(a)), cx.focus[1] + r * float(M.sin(a)))


def landmarks(cx, lots, used: set, out: dict) -> None:
    if not cx.landmarks:
        return
    by_block: dict = {}
    for lot in lots:
        if lot.get("merged_group_id") or lot["id"] in used:
            continue
        by_block.setdefault(lot["block_id"], []).append(lot)
    sites = []
    for bid in sorted(by_block):
        ls = by_block[bid]
        inner = cx.block_opens.get(bid, [])
        poly = _union([lt["polygon"] for lt in ls] + [p for _, p in inner])
        if poly.is_empty:
            continue
        sites.append({"key": bid, "poly": poly, "lots": ls, "c": G.centroid(poly),
                      "a": G.area1(poly), "open": None, "inner": [o for o, _ in inner]})
    for oid, kind, poly in getattr(cx, "opens", []):
        sites.append({"key": oid, "poly": poly, "lots": [], "c": G.centroid(poly),
                      "a": G.area1(poly), "open": oid})
    placed: list = []
    taken: set = set()
    lprog = _landmark_prog(cx)
    n = len(cx.landmarks)
    for i, lm in enumerate(cx.landmarks):
        kind = lm["kind"]
        gen = LANDMARKS.get(kind, generic_tower)
        t = _target(cx, i, n)
        open_air = kind in OPEN_AIR

        def score(s):
            d = ST._dist(s["c"], t)
            bonus = 0.0 if s["open"] is None else (-80.0 if open_air else 1e9)
            return (round(d - 0.15 * math.sqrt(s["a"]) + bonus, 6), s["key"])

        cands = sorted((s for s in sites if s["key"] not in taken and
                        all(ST._dist(s["c"], p) >= LANDMARK_SPREAD_M for p in placed)),
                       key=score)
        H = float(lm["height_m"])
        cap = BL.height_cap(cx.cones, cx.focus)
        done = False
        for s in cands[:40]:
            if s["open"] is not None and not open_air:
                continue
            if s["open"] is None:
                region = BL.buildable(s["poly"], _fronts(s["lots"]), lprog, clear=cx.clear)
                front = _main_front(s["lots"])["line"]
            else:
                region = MS.inset(s["poly"], 3.0)
                front = [tuple(p) for p in list(s["poly"].exterior.coords)[:2]]
            if region.is_empty:
                continue
            MS.prep(region)
            capH = min(H, BL.height_cap(cx.cones, region))
            b = BL.Bld(f"landmark.{kind}", LANDMARK_USE.get(kind, "mixed"), 4.0,
                       MS.lot_frame(region, front))
            b.key, b.depart = (40, i), False
            b.landmark = True
            b.name = lm["name"]
            if not gen(cx, b, region, capH, cx.rng(40, i)):
                continue
            k = len(placed) + 1
            lid = f"{cx.did}.lm{k:02d}"
            pid = f"{lid}.prop"
            lot_ids = [lt["id"] for lt in s["lots"]]
            b.attrs["landmark_kind"] = kind
            if s["open"] is not None:
                b.attrs["open_space_id"] = s["open"]
            if s.get("inner"):
                b.attrs["open_space_ids"] = list(s["inner"])
            if capH < H - 0.01:
                cx.notes.append(f"landmark '{lm['name']}' capped at {capH:.0f} m by a flight "
                                f"cone (asked {H:.0f} m)")
                b.attrs["height_capped"] = True
                b.attrs["height_cap_m"] = G.q(capH)
            fronts = _fronts(s["lots"]) if s["lots"] else \
                [{"segment_id": None, "road_class": "pedestrian", "length_m": 0.0,
                  "line": front}]
            rec = emit(cx, out, b, fronts, cx.rng(41, i), f"{lid}.bld", lot_ids or [None],
                       pid, shops=False)
            rec["lot_id"] = lot_ids[0] if lot_ids else None
            prop(out, pid, "landmark", [rec["id"]], lot_ids, BL.owner(cx, 900 + i), lm["name"])
            used.update(lot_ids)
            taken.add(s["key"])
            placed.append(s["c"])
            if i == 0 and kind in ("megatower", "arcology", "spire"):
                cx.focus = G.centroid(rec["footprint"])
            done = True
            break
        if not done:
            cx.notes.append(f"landmark '{lm['name']}' ({kind}): no site fits in '{cx.name}'")


# ---------------------------------------------------------------------------
# Complexes on merged lot groups
# ---------------------------------------------------------------------------

def complexes(cx, lots, used: set, out: dict) -> None:
    """Each merged group as its complex; when it does not fit there, on the nearest block of
    free lots (or, for a straddle building or bridged pair, the nearest other pair of lots
    facing each other across a street)."""
    groups: dict = {}
    index = {lot["id"]: k for k, lot in enumerate(lots)}
    for k, lot in enumerate(lots):
        g = lot.get("merged_group_id")
        if g and lot["id"] not in used:
            groups.setdefault(g, []).append((k, lot))
    for gid in sorted(groups):
        members = groups[gid]
        kind = members[0][1].get("attrs", {}).get("complex", "tower_cluster")
        fn = COMPLEXES.get(kind)
        if fn is None:
            continue
        idx = members[0][0]
        if fn(cx, gid, members, out, idx):
            used.update(lot["id"] for _, lot in members)
            continue
        c0 = G.centroid(_union([lot["polygon"] for _, lot in members]))
        placed = False
        for cand in _relocations(cx, lots, used, kind, c0):
            mem = [(index[lot["id"]], lot) for lot in cand]
            if fn(cx, gid, mem, out, mem[0][0]):
                used.update(lot["id"] for lot in cand)
                cx.notes.append(f"complex {kind} {gid}: built on lots "
                                f"{', '.join(lot['id'] for lot in cand[:2])}"
                                f"{' ...' if len(cand) > 2 else ''} (the merged group did not "
                                f"fit)")
                placed = True
                break
        if not placed:
            cx.notes.append(f"complex {kind} {gid}: did not fit; lots built one by one")


def probe(cx, kind: str, lots: list, idx: int) -> bool:
    """Whether M3 builds this merged group as its complex (M2 asks while it picks groups):
    the builder runs on a throwaway record, masses only."""
    fn = COMPLEXES.get(kind)
    if fn is None:
        return True
    notes = list(cx.notes)
    out = {"buildings": [], "properties": [], "structures": [], "elements": [], "forced": []}
    cx.probe = True
    try:
        return bool(fn(cx, "probe", list(enumerate(lots, idx)), out, idx))
    finally:
        cx.probe = False
        cx.notes[:] = notes


def _relocations(cx, lots, used, kind, c0, limit: int = 12):
    free = [lot for lot in lots if lot["id"] not in used and not lot.get("merged_group_id")]
    if kind in ("straddle_building", "bridged_pair"):
        ok = ("street", "alley", "pedestrian", "service") if kind == "straddle_building" \
            else ("street", "avenue", "alley", "pedestrian", "service")
        by_seg: dict = {}
        for lot in free:
            if lot["area_m2"] < 250.0:
                continue
            for f in lot["frontage"][:2]:
                if f["road_class"] in ok and f["length_m"] >= 12.0:
                    by_seg.setdefault(f["segment_id"], []).append(lot)
        pairs = []
        for sid in sorted(by_seg):
            ls = by_seg[sid]
            for i, a in enumerate(ls):
                ca = G.centroid(a["polygon"])
                for b in ls[i + 1:]:
                    if a["block_id"] == b["block_id"]:
                        continue
                    cb = G.centroid(b["polygon"])
                    if ST._dist(ca, cb) > 70.0:
                        continue
                    mid = ((ca[0] + cb[0]) / 2.0, (ca[1] + cb[1]) / 2.0)
                    pairs.append((round(ST._dist(mid, c0), 6), a["id"], b["id"], [a, b]))
        pairs.sort(key=lambda t: t[:3])
        return [p[3] for p in pairs[:limit * 3]]
    by_block: dict = {}
    for lot in free:
        by_block.setdefault(lot["block_id"], []).append(lot)
    cands = []
    for bid in sorted(by_block):
        ls = by_block[bid]
        if len(ls) < 2:
            continue
        a = math.fsum(lot["area_m2"] for lot in ls)
        c = G.centroid(_union([lot["polygon"] for lot in ls]))
        cands.append((round(ST._dist(c, c0) - 0.2 * math.sqrt(a), 6), bid, ls))
    cands.sort(key=lambda t: t[:2])
    return [c[2] for c in cands[:limit]]


def _towers_row(region, fr, n: int, s_max: float, s_min: float, gap_f: float = 0.45):
    """n square-ish towers in a row along u inside region (inset): rects or None."""
    u0, v0, u1, v1 = fr.bounds(region)
    W, D = u1 - u0, v1 - v0
    for cu, cv in MS.anchors_of(region, fr):
        s = min(s_max, D * 0.9)
        while s >= s_min:
            g = min(26.0, max(12.0, gap_f * s))
            total = n * s + (n - 1) * g
            if total <= W:
                rs = []
                for i in range(n):
                    c = cu - total / 2.0 + s / 2.0 + i * (s + g)
                    r = fr.rect(c - s / 2.0, cv - s / 2.0, c + s / 2.0, cv + s / 2.0)
                    if not region.covers(r):
                        break
                    rs.append((r, c))
                if len(rs) == n:
                    return rs, s, g
            s *= 0.92
    return None


def _shared_podium(cx, gid, members, out, idx, n: int, steps, kind: str) -> bool:
    lots = [lt for _, lt in members]
    union = _union([lt["polygon"] for lt in lots])
    fronts = _fronts(lots)
    front = _main_front(lots)
    prog = cx.prog
    region = BL.buildable(union, fronts, prog, clear=cx.clear)
    if region.is_empty:
        return False
    rng = cx.rng(50, idx)
    lo, hi = cx.height
    lo_s, hi_s = prog.tower_side
    found = None
    inner = MS.inset(region, 4.0)
    if inner.is_empty:
        return False
    MS.prep(inner)
    lf = MS.lot_frame(region, front["line"])
    ob = MS.Frame(lf.ox, lf.oy, MS.obb_angle(region))
    for fr in (lf, lf.turned(M.HALF_PI), ob, ob.turned(M.HALF_PI)):
        found = _towers_row(inner, fr, n, hi_s * 1.05, max(12.0, lo_s * 0.7))
        if found:
            break
    if not found:
        return False
    rects, s, g = found
    fh = prog.fh
    p = G.centroid(region)
    H0 = BL.pick_height(cx, p, G.area1(union), front["road_class"], rng, lo_f=0.75,
                        hi_f=1.0)
    cap = BL.height_cap(cx.cones, region)
    npod = prog.podium_floors[1] + (1 if front["road_class"] == "avenue" else 0)
    P = npod * fh
    pid = f"{gid}.prop"
    bids = []
    cuts = [(rects[i][1] + rects[i + 1][1]) / 2.0 for i in range(n - 1)]
    edges = [None] + cuts + [None]
    crown_u = float(rng.random())
    recs = []
    for i, (t, c) in enumerate(rects):
        part = G.inter(region, MS.halfplane(fr, u_min=edges[i], u_max=edges[i + 1]))
        # (M21: the piece of the podium under its tower, not just the largest piece: a tower
        # stood in the air over a podium cut in two)
        ps = sorted(G.parts(part), key=lambda p: -G.area1(G.inter(p, t)))
        if not ps:
            return False
        Hi = BL.floors_in(H0 * steps[i], fh, lo, hi, cap) * fh
        b = BL.Bld("podium_tower", prog.use, fh, fr)
        b.key, b.depart = (51, idx, 0 if kind == "twin_towers" else i), False
        b.add(ps[0], 0.0, P, "podium")
        b.avoid = BL.taken_near(cx, G.centroid(ps[0]), pid, Hi)
        trng = cx.rng(51, idx, 0 if kind == "twin_towers" else i)
        BL.tower_body(b, t, P, Hi, cx, trng, ps[0], crown=0.6 if crown_u < 0.6 else 0.0,
                      spire=kind == "twin_towers" or i == 0)
        BL.placed(cx, b, pid)
        bid = f"{gid}.bld{i + 1}"
        rec = emit(cx, out, b, fronts, cx.rng(52, idx, i), bid, [lt["id"] for lt in lots],
                   pid, lots=lots)
        recs.append(rec)
        bids.append(bid)
    prop(out, pid, kind, bids, [lt["id"] for lt in lots], BL.owner(cx, 700 + idx))
    for i in range(n - 1):
        hmin = min(recs[i]["height"], recs[i + 1]["height"])
        if kind == "twin_towers":
            force(out, bids[i], bids[i + 1], hmin * 0.45, "stack", 2, 6.0, pid, kind)
        else:
            force(out, bids[i], bids[i + 1], hmin * 0.5, "enclosed", 1, 5.0, pid, kind)
    return True


def twin_towers(cx, gid, members, out, idx) -> bool:
    return _shared_podium(cx, gid, members, out, idx, 2, (1.0, 1.0), "twin_towers")


def tower_cluster(cx, gid, members, out, idx) -> bool:
    n = 4 if len(members) >= 4 else 3
    steps = (1.0, 0.84, 0.7, 0.58)[:n]
    if _shared_podium(cx, gid, members, out, idx, n, steps, "tower_cluster"):
        return True
    return n == 4 and _shared_podium(cx, gid, members, out, idx, 3, steps[:3],
                                     "tower_cluster")


def megabuilding_campus(cx, gid, members, out, idx) -> bool:
    lots = sorted((lt for _, lt in members), key=lambda lt: (-lt["area_m2"], lt["id"]))
    if len(lots) < 2:
        return False
    prog = cx.prog
    pid = f"{gid}.prop"
    lo, hi = cx.height
    bids, recs = [], []
    main_fr = None
    for i, lot in enumerate(lots):
        fronts = lot["frontage"]
        fr = MS.lot_frame(lot["polygon"], BL.main_front(fronts)["line"])
        region = BL.buildable(lot["polygon"], fronts, prog, clear=cx.clear)
        if region.is_empty or G.area1(region) < 400.0:
            continue
        MS.prep(region)
        rng = cx.rng(55, idx, i)
        p = G.centroid(region)
        cap = BL.height_cap(cx.cones, region)
        front_cls = fronts[0]["road_class"]
        if i == 0:
            H = BL.floors_in(BL.pick_height(cx, p, lot["area_m2"], front_cls, rng, 0.7, 1.0),
                             prog.fh, lo, hi, cap) * prog.fh
            kind = "megabuilding" if G.area1(region) >= 2500.0 else "slab"
        else:
            H = BL.floors_in(recs[0]["height"] * MS.uniform(rng, 0.75, 0.9), prog.fh, lo, hi,
                             cap) * prog.fh
            kind = "podium_tower"
        b = BL.Bld(kind, prog.use, prog.fh, fr)
        b.key, b.depart = (55, idx, i), False
        b.avoid = BL.taken_near(cx, G.centroid(region), pid, H)
        BL.set_front(b, BL.main_front(fronts), prog)
        if i == 0 or not recs:
            BL.fill(b, kind, region, H, cx, rng, fronts, front_cls)
        elif not _satellite(cx, b, region, H, recs[0], main_fr, rng):
            BL.fill(b, kind, region, H, cx, rng, fronts, front_cls)
        if not b.masses:
            continue
        BL.placed(cx, b, pid)
        if i == 0:
            main_fr = b.fr
        bid = f"{gid}.bld{len(bids) + 1}"
        recs.append(emit(cx, out, b, fronts, cx.rng(56, idx, i), bid,
                         [lt["id"] for lt in lots], pid, lots=lots))
        recs[-1]["lot_id"] = lot["id"]
        bids.append(bid)
    if len(bids) < 2 or not all(
            bridgeable(cx, recs[0], recs[j], min(recs[0]["height"], recs[j]["height"]) * 0.33,
                       "open_deck", 8.0) for j in range(1, len(recs))):
        _drop(out, bids)
        cx.placed[:] = [p for p in cx.placed if p[1] != pid]
        return False
    prop(out, pid, "megabuilding_campus", bids, [lt["id"] for lt in lots],
         BL.owner(cx, 800 + idx))
    for j in range(1, len(bids)):
        h = min(recs[0]["height"], recs[j]["height"])
        force(out, bids[0], bids[j], h * 0.33, "open_deck", 1, 8.0, pid, "megabuilding_campus")
        force(out, bids[0], bids[j], h * 0.66, "enclosed", 1, 5.0, pid, "megabuilding_campus")
    return True


def _satellite(cx, b, region, H, main, main_fr, rng) -> bool:
    """A satellite tower in the main building's frame, on the side of its lot that faces the
    main building (so a bridge can reach straight across)."""
    prog = cx.prog
    fh = b.fh
    b.fr = MS.Frame(b.fr.ox, b.fr.oy, main_fr.angle)
    inner = MS.inset(region, 4.0)
    if inner.is_empty:
        return False
    MS.prep(inner)
    mp = main["footprint"]
    lo_s, hi_s = prog.tower_side
    side = min(hi_s, max(lo_s, math.sqrt(G.area1(region) * prog.coverage)))
    mu0, mv0, mu1, mv1 = b.fr.bounds(mp)
    su0, sv0, su1, sv1 = b.fr.bounds(inner)
    # the satellite lies beside the main building along u or along v: face it from there,
    # centered on the overlap of their extents across that direction
    gaps = {"e": su0 - mu1, "w": mu0 - su1, "n": sv0 - mv1, "s": mv0 - sv1}
    d = max(sorted(gaps), key=lambda k: gaps[k])
    for f in (1.0, 0.85, 0.7, 0.55):
        sz = side * f
        if sz < lo_s * 0.7:
            break
        if d in ("e", "w"):
            lo_, hi_ = max(mv0, sv0), min(mv1, sv1)
            cv = (lo_ + hi_) / 2.0 if hi_ > lo_ else (sv0 + sv1) / 2.0
            cu = max(su0 + sz / 2.0, mu1 + 10.0 + sz / 2.0) if d == "e" else \
                min(su1 - sz / 2.0, mu0 - 10.0 - sz / 2.0)
        else:
            lo_, hi_ = max(mu0, su0), min(mu1, su1)
            cu = (lo_ + hi_) / 2.0 if hi_ > lo_ else (su0 + su1) / 2.0
            cv = max(sv0 + sz / 2.0, mv1 + 10.0 + sz / 2.0) if d == "n" else \
                min(sv1 - sz / 2.0, mv0 - 10.0 - sz / 2.0)
        t = MS.fit_rect(inner, b.fr, sz, sz, cu, cv, min_w=lo_s * 0.7, min_d=lo_s * 0.7,
                        shrink=((1.0, 1.0), (1.0, 0.8), (0.8, 1.0), (0.8, 0.8)))
        if t is not None:
            P = 3 * fh
            b.add(region, 0.0, P, "podium")
            BL.tower_body(b, t, P, H, cx, rng, region, crown=0.0, spire=False)
            return True
    return False


def campus(cx, gid, members, out, idx) -> bool:
    lots = [lt for _, lt in members]
    union = _union([lt["polygon"] for lt in lots])
    fronts = _fronts(lots)
    front = _main_front(lots)
    prog = cx.prog
    region = BL.buildable(union, fronts, prog, clear=cx.clear)
    if region.is_empty:
        return False
    fr = MS.lot_frame(region, front["line"])
    u0, v0, u1, v1 = fr.bounds(region)
    W, D = u1 - u0, v1 - v0
    if min(W, D) < 34.0:
        return False
    d = min(24.0, max(10.0, 0.22 * min(W, D)))
    if min(W, D) >= 60.0:     # four labs around the lawn
        bars = [(u0, v0, u1, v0 + d), (u0, v1 - d, u1, v1),
                (u0, v0 + d + 8.0, u0 + d, v1 - d - 8.0),
                (u1 - d, v0 + d + 8.0, u1, v1 - d - 8.0)]
    elif W >= 70.0:           # three labs in a U, the lawn open to the street
        bars = [(u0, v1 - d, u1, v1), (u0, v0, u0 + d, v1 - d - 6.0),
                (u1 - d, v0, u1, v1 - d - 6.0)]
    else:                     # three labs in a row behind a front lawn
        w3 = (W - 12.0) / 3.0
        bars = [(u0 + k * (w3 + 6.0), v0 + D * 0.35, u0 + k * (w3 + 6.0) + w3, v1)
                for k in range(3)]
    rng = cx.rng(60, idx)
    lo, hi = cx.height
    pid = f"{gid}.prop"
    bids, polys = [], []
    for i, (a0, b0, a1, b1) in enumerate(bars):
        ps = G.parts(G.inter(region, fr.rect(a0, b0, a1, b1)))
        if not ps or G.area1(ps[0]) < 150.0:
            continue
        p = ps[0]
        H = lo + (hi - lo) * (MS.uniform(rng, 0.1, 0.35) if i else MS.uniform(rng, 0.45, 0.8))
        n = BL.floors_in(H, prog.fh, lo, hi, BL.height_cap(cx.cones, p))
        b = BL.Bld("lab", "civic", prog.fh, fr)
        b.add(p, 0.0, n * prog.fh, "body")
        bid = f"{gid}.bld{len(bids) + 1}"
        emit(cx, out, b, fronts, cx.rng(61, idx, i), bid, [lt["id"] for lt in lots], pid,
             shops=False, lots=lots)
        bids.append(bid)
        polys.append(p)
    if len(bids) < 3:
        out["buildings"] = [r for r in out["buildings"] if r["id"] not in bids]
        return False
    prop(out, pid, "campus", bids, [lt["id"] for lt in lots], BL.owner(cx, 600 + idx))
    lawn = G.diff(region, G.union([G.qpoly(p.buffer(3.0, join_style="mitre"))
                                   for p in polys]))
    ps = G.parts(lawn)
    if ps and G.area1(ps[0]) > 200.0:
        out["elements"].append({"id": f"{gid}.el01", "kind": "lawn", "lot_id": lots[0]["id"],
                                "footprint": ps[0], "z_m": 0.0, "masses": [],
                                "attrs": {"campus": gid}})
    # covered walkway: a loop through the building faces that look onto the lawn
    cs = [G.nearest(p.exterior, G.centroid(region)) for p in polys]
    loop = cs + [cs[0]]
    out["structures"].append({"id": f"{gid}.st01", "kind": "canopy", "line": loop,
                              "z0_m": 0.0, "z1_m": 3.5, "attrs": {"covered_walkway": True,
                                                                   "campus": gid,
                                                                   "width_m": 3.0}})
    return True


def bridged_pair(cx, gid, members, out, idx) -> bool:
    """Two slabs facing each other across the street the two lots share, joined by
    skybridges over it."""
    lots = [lt for _, lt in members]
    if len(lots) != 2:
        return False
    sh = _shared_segment(lots)
    if sh is None:
        return False
    _, fa, fb = sh
    prog = cx.prog
    pid = f"{gid}.prop"
    lo, hi = cx.height
    bids, recs = [], []
    for i, (lot, f) in enumerate(((lots[0], fa), (lots[1], fb))):
        fronts = lot["frontage"]
        fr = MS.lot_frame(lot["polygon"], f["line"])
        region = BL.buildable(lot["polygon"], fronts, prog, clear=cx.clear)
        if region.is_empty or G.area1(region) < 150.0:
            return False
        rng = cx.rng(65, idx, i)
        H = BL.floors_in(BL.pick_height(cx, G.centroid(region), lot["area_m2"],
                                        f["road_class"], rng, 0.4, 1.0), prog.fh, lo, hi,
                         BL.height_cap(cx.cones, region)) * prog.fh
        b = BL.Bld("slab", prog.use, prog.fh, fr)
        b.depart = False
        BL.set_front(b, f, prog)
        if recs:
            # the second slab opposite the first: along the street where the first one is
            us = [fr.local(x, y)[0] for x, y in recs[0][0].ground().exterior.coords]
            lo_u, hi_u = max(min(us), b.front_u[0]), min(max(us), b.front_u[1])
            if hi_u - lo_u < 12.0:
                return False
            b.front_u = (lo_u, hi_u)
        BL.fill(b, "slab", MS.prep(region), H, cx, rng, fronts, f["road_class"])
        if not b.masses:
            return False
        recs.append((b, fronts, lot))
    for i, (b, fronts, lot) in enumerate(recs):
        bid = f"{gid}.bld{i + 1}"
        rec = emit(cx, out, b, fronts, cx.rng(66, idx, i), bid, [lt["id"] for lt in lots],
                   pid)
        rec["lot_id"] = lot["id"]
        bids.append(bid)
    h = min(b.height for b, _, _ in recs)
    if not bridgeable(cx, out["buildings"][-2], out["buildings"][-1], h * 0.4):
        _drop(out, bids)
        return False
    prop(out, pid, "bridged_pair", bids, [lt["id"] for lt in lots], BL.owner(cx, 500 + idx))
    force(out, bids[0], bids[1], h * 0.4, "enclosed", 1, 5.0, pid, "bridged_pair")
    if h >= 40.0:
        force(out, bids[0], bids[1], h * 0.7, "enclosed", 1, 5.0, pid, "bridged_pair")
    return True


def _shared_segment(lots):
    a = {f["segment_id"]: f for f in lots[0]["frontage"]}
    best = None
    for f in lots[1]["frontage"]:
        if f["segment_id"] in a:
            L = min(f["length_m"], a[f["segment_id"]]["length_m"])
            if best is None or (L, f["segment_id"]) > best[0]:
                best = ((L, f["segment_id"]), a[f["segment_id"]], f)
    return best


STRADDLE_ROADS = ("street", "alley", "pedestrian", "service")
SPAN_MAX_M = 50.0


def straddle_building(cx, gid, members, out, idx) -> bool:
    """Two legs facing each other and a span (three floors) over what lies between them: the
    street the two lots share, or a canal with the quay roads on both sides of it. The span
    clears every road it crosses by 5.5 m and the water by its navigable clearance (both
    plus a 1 m structure), and no junction or other road lies under it."""
    lots = [lt for _, lt in members]
    if len(lots) != 2:
        return False
    sh = _shared_segment(lots)
    if sh is not None:
        (_, sid), fa, fb = sh
        allowed = {sid}
    else:
        cp = _canal_fronts(cx, lots)
        if cp is None:
            return False
        fa, fb = cp
        allowed = {fa["segment_id"], fb["segment_id"]}
    roads = {r[0]: r for r in cx.roads}
    if any(roads.get(x) is None or roads[x][1] not in STRADDLE_ROADS for x in allowed):
        return False
    prog = cx.prog
    fh = prog.fh
    lo, hi = cx.height
    regions = []
    for lot, f in ((lots[0], fa), (lots[1], fb)):
        fr = MS.lot_frame(lot["polygon"], f["line"])
        region = BL.buildable(lot["polygon"], lot["frontage"], prog, clear=cx.clear)
        if region.is_empty:
            return False
        regions.append((lot, fr, MS.prep(region)))
    frA = regions[0][1]
    # the legs face each other: both along the stretch where the two lots overlap
    ra, rb = frA.bounds(regions[0][2]), frA.bounds(regions[1][2])
    ov = (max(ra[0], rb[0]), min(ra[2], rb[2]))
    legs = []
    for i, (lot, fr, region) in enumerate(regions):
        u0, v0, u1, v1 = fr.bounds(region)
        w = min(36.0, (u1 - u0) * 0.9)
        dd = min(16.0, (v1 - v0) * 0.9)
        if i == 0:
            lim = (ov[0], ov[1]) if ov[1] - ov[0] >= 10.0 else None
        else:
            au0, _, au1, _ = fr.bounds(legs[0][3])
            lim = (au0 - 2.0, au1 + 2.0)
        r = MS.front_rect(region, fr, dd, w_max=w, min_w=8.0, min_d=6.0, u_lim=lim) \
            if lim is not None else None
        if r is None:
            r = MS.front_rect(region, fr, dd, w_max=w, min_w=8.0, min_d=6.0)
        if r is None:
            return False
        legs.append((lot, fr, region, r))
    A, B = legs[0][3], legs[1][3]
    au0, av0, au1, av1 = frA.bounds(A)
    bu0, bv0, bu1, bv1 = frA.bounds(B)
    us0, us1 = max(au0, bu0) + 1.0, min(au1, bu1) - 1.0
    if us1 - us0 < 6.0 or bv1 >= av0 or av0 - bv1 > SPAN_MAX_M:
        return False
    span = G.parts(G.diff(frA.rect(us0, bv1 - 0.5, us1, av0 + 0.5), G.union([A, B])))
    if not span:
        return False
    span = span[0]
    if any(span.intersects(j) for j in cx.junctions):
        return False
    own = {lots[0]["id"], lots[1]["id"]}
    if any(lid not in own and not G.apart(span, lp) and G.area1(G.inter(span, lp)) > 0.5
           for lid, lp in cx.lots):
        return False   # the span passes over another lot
    crosses, need, zroad = [], 0.0, 0.0
    for rid, cls, line, width, prof in cx.roads:
        if span.intersects(LineString(line)):
            if rid not in allowed:
                return False
            crosses.append(rid)
            zr = G.road_z_over(line, prof, span)
            need = max(need, zr + BL.ROAD_CLEARANCE_M + 1.0)
            zroad = max(zroad, zr)
    over_water = None
    for wid, wp, clear in cx.water:
        if span.intersects(wp):
            if not G.area1(G.inter(span, wp)) > 0.01:
                continue
            crosses.append(wid)
            need = max(need, clear + 1.0)
            over_water = over_water or wid
    if sh is None and over_water is None:
        return False
    n0 = int(math.ceil(need / fh - 1e-9))
    z0 = n0 * fh
    z1 = z0 + 3 * fh
    rng = cx.rng(70, idx)
    pid = f"{gid}.prop"
    bids = []
    cap = min(BL.height_cap(cx.cones, legs[0][2]), BL.height_cap(cx.cones, legs[1][2]))
    H = BL.pick_height(cx, G.centroid(span), lots[0]["area_m2"], "street", rng, 0.3, 0.8)
    H = max(H, z1 + 2 * fh)
    n = BL.floors_in(H, fh, lo, hi, cap)
    if n * fh < z1 + fh:
        return False
    for i, (lot, fr, region, r) in enumerate(legs):
        b = BL.Bld("straddle_building", prog.use, fh, fr)
        Hi = n * fh if i == 0 else BL.floors_in(n * fh * MS.uniform(rng, 0.8, 1.0), fh,
                                                  max(lo, z1 + fh), hi, cap) * fh
        b.add(r, 0.0, Hi, "leg")
        if i == 0:
            b.add(span, z0, z1, "span")
            b.attrs["span_over"] = over_water if sh is None else sid
            b.attrs["span_crosses"] = sorted(crosses)
            b.attrs["span_clearance_m"] = q(z0 - 1.0 - zroad)
        bid = f"{gid}.bld{i + 1}"
        emit(cx, out, b, lot["frontage"], cx.rng(71, idx, i), bid, [lt["id"] for lt in lots],
             pid)
        out["buildings"][-1]["lot_id"] = lot["id"]
        bids.append(bid)
    prop(out, pid, "straddle_building", bids, [lt["id"] for lt in lots],
         BL.owner(cx, 400 + idx))
    return True


CANAL_REACH_M = 60.0


def _canal_fronts(cx, lots):
    """(front of lot 0, front of lot 1) when the two lots face each other across a canal: the
    frontage of each nearest the other lot, the segment between their midpoints crossing a
    canal (an inner waterway) and no farther than CANAL_REACH_M."""
    canals = [(wid, wp) for wid, wp, clear in cx.water if clear <= 4.0 + 1e-9]
    if not canals:
        return None
    best = []
    for k in (0, 1):
        other = G.centroid(lots[1 - k]["polygon"])
        fs = [f for f in lots[k]["frontage"] if len(f["line"]) >= 2]
        if not fs:
            return None
        best.append(min(fs, key=lambda f: (round(MS.line_dist(other, f["line"])[0], 6),
                                           f["segment_id"])))
    ma = MS.lerp(best[0]["line"][0], best[0]["line"][-1], 0.5)
    mb = MS.lerp(best[1]["line"][0], best[1]["line"][-1], 0.5)
    if ST._dist(ma, mb) > CANAL_REACH_M or best[0]["segment_id"] == best[1]["segment_id"]:
        return None
    link = LineString([ma, mb])
    if not any(link.intersects(wp) for _, wp in canals):
        return None
    return best[0], best[1]


COMPLEXES = {"twin_towers": twin_towers, "tower_cluster": tower_cluster,
             "megabuilding_campus": megabuilding_campus, "campus": campus,
             "bridged_pair": bridged_pair, "straddle_building": straddle_building}


# ---------------------------------------------------------------------------
# Container yards on port lots
# ---------------------------------------------------------------------------

def yard_stacks(cx, lot, b: BL.Bld, rng) -> list[dict]:
    region = BL.buildable(lot["polygon"], lot["frontage"], cx.prog, clear=cx.clear)
    if region.is_empty:
        return []
    office = b.ground()
    free = G.diff(region, G.qpoly(office.buffer(6.0, join_style="mitre")))
    ps = G.parts(free)
    if not ps:
        return []
    free = MS.prep(ps[0])
    fr = b.fr
    u0, v0, u1, v1 = fr.bounds(free)
    out = []
    su, sv = 12.2, 7.5
    v = v0 + 2.0
    n = 0
    while v + sv <= v1 and n < 40:
        u = u0 + 2.0
        while u + su <= u1 and n < 40:
            r = fr.rect(u, v, u + su, v + sv)
            if free.covers(r):
                n += 1
                h = 2.6 * (1 + int(float(rng.random()) * 5))
                out.append({"id": f"{lot['id']}.el{n:02d}", "kind": "container_stack",
                            "lot_id": lot["id"], "footprint": r, "z_m": 0.0,
                            "masses": [(r, 0.0, q(h), "stack", "prism")], "attrs": {}})
            u += su + 4.0
        v += sv + 6.0
    return out
