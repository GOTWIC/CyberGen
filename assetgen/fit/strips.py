"""Strips over a carriageway (issue #82): part of AG14's `asset_clash`, on the packs as
written.

A *strip* is what is walked on or planted beside a carriageway, never driven over: a
sidewalk piece (its slab, curb stone, tree grates), a junction's sidewalk corners (its
paving and curbs, on a junction whose carriageway is asphalt) and a road's median (its
curbs, its lawn or concrete top). What it may not cross:

- **strip on junction**: a strip's points over a junction's carriageway (its asphalt) in
  plan, more than `INSET_M` in from that carriageway's outline, between `BELOW_M` under and
  `ABOVE_M` over its surface there (a strip under a raised junction with headroom, or a
  deck street over one, is not on it);
- **strip on road**: the same over another road's carriageway (a road's own median and
  sidewalks run on and beside it; a junction's corners beside its legs).

Points are the strips' up-facing triangles' vertices, middles and points along their edges
(`barriers._samples`). Plain numpy and shapely on the triangles as read (as `index.py`).
"""

from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
import shapely

from .. import canon as C
from .barriers import INSET_M, Targets, _samples

BELOW_M = 1.0           # a strip point under a carriageway by this still crosses it
ABOVE_M = 4.5           # ... and over it by this (AG14's headroom)
MEDIAN_SLOTS = ("lawn", "concrete")
LIST_MAX = 40
KEYS = ("strip_on_junction", "strip_on_road")


def _up(T: np.ndarray, min_nz: float = 0.5) -> np.ndarray:
    if not len(T):
        return np.zeros(0, dtype=bool)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    L = np.linalg.norm(n, axis=1)
    return (L > 1e-9) & (n[:, 2] > min_nz * np.maximum(L, 1e-12))


def strips(pk, model) -> list[tuple[str, str, np.ndarray, set]]:
    """[(piece id, what, up-facing triangles, the roads it belongs to)] of every strip."""
    segs = {s.id: s for s in model.road_segments}
    walk_seg = {w.id: w.segment_id for w in model.sidewalks}
    legs: dict[str, set] = defaultdict(set)
    jnode = {n: j.id for j in model.junctions for n in j.attrs.get("nodes") or [j.node_id]}
    for s in model.road_segments:
        for n in (s.start, s.end):
            if n in jnode:
                legs[jnode[n]].add(s.id)
    out = []
    for pid in pk.street_ids():
        k = pk.street_kind(pid)
        if k not in ("street.sidewalk", "street.junction", "street.road"):
            continue
        T, mats = pk.street_tris(pid)
        if not len(T):
            continue
        up = _up(T)
        if k == "street.sidewalk":
            keep = up & np.array([m.split(".")[0] in ("paving", "curb", "grate")
                                  for m in mats], dtype=bool)
            what, own = "sidewalk", {walk_seg.get(pid, pid)}
        elif k == "street.junction":
            if not any(m.startswith("asphalt") for m in mats):
                continue        # (a pedestrian junction: its paving is its surface)
            keep = up & np.array([m.split(".")[0] in ("paving", "curb") for m in mats],
                                 dtype=bool)
            what, own = "junction corner", set(legs.get(pid, ()))
        else:
            s = segs.get(pid)
            if s is None:
                continue
            hm = (s.cross_section.median_m or 0.0) / 2.0
            if hm < 0.5 or s.road_class == "highway":
                continue        # (a highway's median is its barrier: #95's check)
            keep = up & np.array([m.split(".")[0] == "curb" or m in MEDIAN_SLOTS
                                  for m in mats], dtype=bool)
            if keep.any():
                c = T[keep].mean(axis=1)
                ln = shapely.LineString([(p[0], p[1]) for p in s.centerline])
                near = shapely.distance(ln, shapely.points(c[:, 0], c[:, 1])) <= hm + 0.05
                idx = np.nonzero(keep)[0]
                keep[idx[~near]] = False
            what, own = "median", {pid}
        if keep.any():
            out.append((pid, what, T[keep], own))
    return out


def strip_clash(pk, model, tg: Targets | None = None) -> dict:
    """{"counts", "by_kind" (what on what), "worst"} of the module docstring."""
    tg = tg if tg is not None else Targets(pk, model)
    jown = {o for o, k in tg.kind_of.items() if k == "street.junction"}
    rown = {o for o, k in tg.kind_of.items() if k == "street.road"}
    counts = {k: 0 for k in KEYS}
    rows: dict[str, list] = {k: [] for k in KEYS}
    by_kind: dict[str, int] = defaultdict(int)
    for pid, what, T, own in strips(pk, model):
        P = _samples(T)
        mine = {pk.oid[x] for x in own if x in pk.oid}
        hits = tg.on_pavement(P, mine | rown, BELOW_M, ABOVE_M, vehicle=True)
        hits += [h for h in tg.on_pavement(P, mine | jown, BELOW_M, ABOVE_M, vehicle=True)
                 if h[1] in rown]
        per: dict[int, list] = {}
        for a, o, d in hits:
            r = per.setdefault(o, [0, 0.0, a])
            r[0] += 1
            if d > r[1]:
                r[1], r[2] = d, a
        for o, (n, d, a) in sorted(per.items()):
            key = "strip_on_junction" if o in jown else "strip_on_road"
            counts[key] += 1
            by_kind[f"{key}: {what}"] += 1
            rows[key].append({"strip": pid, "what": what, "on": pk.names[o], "points": n,
                              "depth_m": C.m(d), "at": [C.m2(v) for v in P[a]]})
    for k in rows:
        rows[k] = sorted(rows[k], key=lambda r: (-r["depth_m"], json.dumps(r, sort_keys=True))
                         )[:LIST_MAX]
    return {"counts": counts, "by_kind": dict(sorted(by_kind.items())), "worst": rows}
