"""AG17's `street_watertight`: the street pieces drawn from M22's pavement map meet with no
gap, no step and no T-junction, checked exactly on the packs as written (docs/
assetgen_scope.md 14.18).

Every interior edge of the map (one two faces share) is a polyline of stored vertices. For
each of its segments, on integer millimeters of the packs read back (world positions):

- each face beside it is drawn along it: the mesh edge between the segment's two vertices
  at the heights that face's piece draws them (`pave.Index.top`) is in that piece;
- every such mesh edge lies in exactly two triangles of all the street surfaces: the two
  faces' where they are drawn at one height, or a face's and its curb's (the wall between
  two faces at different heights: its top on the higher face's edge, its foot on the
  lower's).

A segment drawn by neither side, or by one only, is a gap; a mesh edge in one triangle is
open (a step or a T-junction); in three or more, drawn twice. Where a segment is missing,
the plan gap is measured to the nearest edge its piece does draw within a meter.

Surfaces are a road, junction or sidewalk piece's triangles in their pavement and curb
slots (asphalt, paving, curb stone, a median's lawn or concrete top, a deck's fascia and
slab); marks, grates, barriers and girders lie on them and are left out.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

PIECE_KINDS = ("street.road", "street.junction", "street.sidewalk")
SKIP = ("marking.", "manhole", "grate", "asphalt.patch", "steel.joint", "light", "tactile",
        "concrete.barrier", "steel.", "stone.", "glass.")
LIST_MAX = 40


def _surface_slot(name: str) -> bool:
    return not any(name == s or (s.endswith(".") and name.startswith(s)) for s in SKIP)


def owner_piece(model, PI) -> dict:
    """{face id: the piece that draws it} (a road's faces its road piece, a side's bands its
    sidewalk piece where it has one, a junction's its junction piece)."""
    from .pave import side_of
    walks = defaultdict(dict)
    for w in model.sidewalks:
        walks[w.segment_id][w.side[0]] = w.id
    out = {}
    for fid, f in PI.F.items():
        sd = side_of(f.band)
        if sd is not None and sd in walks.get(f.owner_id, {}):
            out[fid] = walks[f.owner_id][sd]
        else:
            out[fid] = f.owner_id
    return out


def check(model, PI, out_dir: Path, manifest: dict) -> dict:
    """{"ok", "detail", "stats": {...}, "worst": [...]} of the module docstring."""
    from ..fit import glb as GL
    if not PI.on:
        return {"id": "street_watertight", "ok": True, "detail": "no pavement map",
                "stats": {}}
    owner = owner_piece(model, PI)
    want_pieces = {pid for pid, r in manifest["pieces"].items() if r["kind"] in PIECE_KINDS}
    sdir = Path(out_dir) / "streets"
    tris_all = []
    piece_of = []
    names = sorted(want_pieces)
    pidx = {p: i for i, p in enumerate(names)}
    tiles = sorted({manifest["pieces"][p]["tile"] for p in want_pieces})
    for t in tiles:
        f = sdir / f"{t}.glb"
        if not f.is_file():
            continue
        for nd in GL.read(f):
            if nd.name not in want_pieces:
                continue
            T = nd.triangles(_surface_slot)
            if not len(T):
                continue
            tris_all.append(np.rint(T * 1000.0).astype(np.int64))
            piece_of.append(np.full(len(T), pidx[nd.name], dtype=np.int64))
    if tris_all:
        T = np.concatenate(tris_all)
        P_ = np.concatenate(piece_of)
    else:
        T = np.zeros((0, 3, 3), dtype=np.int64)
        P_ = np.zeros(0, dtype=np.int64)
    # every triangle's three edges, each with its ends in a fixed order
    E = np.concatenate([np.concatenate([T[:, a], T[:, b]], axis=1)
                        for a, b in ((0, 1), (1, 2), (2, 0))])
    EP = np.concatenate([P_, P_, P_])
    swap = (E[:, 0] > E[:, 3]) | ((E[:, 0] == E[:, 3]) & (
        (E[:, 1] > E[:, 4]) | ((E[:, 1] == E[:, 4]) & (E[:, 2] > E[:, 5]))))
    E[swap] = np.concatenate([E[swap][:, 3:], E[swap][:, :3]], axis=1)
    count: dict = defaultdict(int)
    pieces_at: dict = defaultdict(set)
    for row, p in zip(map(tuple, E.tolist()), EP.tolist()):
        count[row] += 1
        pieces_at[row].add(p)

    def key(a, b):
        return (a + b) if a <= b else (b + a)
    stats = {"edges": 0, "segments": 0, "missing": 0, "open": 0, "twice": 0, "walls": 0}
    worst = []
    near_cache: dict = {}
    max_gap = 0.0
    for eid in sorted(PI.E):
        fs = PI.edge_faces.get(eid, ())
        if len(fs) < 2:
            continue
        stats["edges"] += 1
        vs = PI.E[eid][1]
        for va, vb in zip(vs, vs[1:]):
            stats["segments"] += 1
            pa, pb = PI.V[va], PI.V[vb]
            tops = []
            for f in fs:
                ta, tb = PI.top(f, va), PI.top(f, vb)
                tops.append((f, ta, tb))
            if len({(ta, tb) for _, ta, tb in tops}) > 1:
                stats["walls"] += 1
            for f, ta, tb in tops:
                k = key((pa[0], pa[1], ta), (pb[0], pb[1], tb))
                n = count.get(k, 0)
                mine = pidx.get(owner.get(f))
                bad = None
                if n == 0 or mine not in pieces_at.get(k, ()):
                    stats["missing"] += 1
                    bad = "missing"
                    g = _gap(E, EP, mine, pa, pb, near_cache)
                    max_gap = max(max_gap, g)
                elif n == 1:
                    stats["open"] += 1
                    bad = "open"
                elif n > 2:
                    stats["twice"] += 1
                    bad = "twice"
                if bad and len(worst) < LIST_MAX:
                    worst.append({"edge": eid, "face": f, "what": bad, "triangles": n,
                                  "at": [pa[0] / 1000.0, pa[1] / 1000.0, ta / 1000.0]})
    stats["max_gap_m"] = round(max_gap, 3)
    bad = stats["missing"] + stats["open"] + stats["twice"]
    detail = (f"{stats['edges']} shared edges ({stats['segments']} segments, "
              f"{stats['walls']} with a curb): {stats['missing']} not drawn, "
              f"{stats['open']} open, {stats['twice']} drawn twice, largest plan gap "
              f"{stats['max_gap_m']} m")
    return {"id": "street_watertight", "ok": bad == 0, "detail": detail, "stats": stats,
            "worst": worst}


def _gap(E, EP, piece, pa, pb, cache) -> float:
    """The plan distance from a segment's ends to the nearest mesh edge its piece draws
    within a meter (0 where it draws none near)."""
    if piece is None:
        return 0.0
    if piece not in cache:
        sel = EP == piece
        cache[piece] = E[sel]
    Ep = cache[piece]
    if not len(Ep):
        return 0.0
    best = None
    for p in (pa, pb):
        d0 = np.hypot(Ep[:, 0] - p[0], Ep[:, 1] - p[1])
        d1 = np.hypot(Ep[:, 3] - p[0], Ep[:, 4] - p[1])
        d = float(min(d0.min(), d1.min())) / 1000.0
        if d <= 1.0:
            best = d if best is None else max(best, d)
    return best or 0.0
