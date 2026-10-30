"""M16, water detail: every water body's bed, current and (the sea) exposure, and every water
edge as typed bank stretches, for stage 2's water (AG12). Runs on the finished city.

- **Vertical frame.** On a flat city the ground stands `FREEBOARD_M` over every water body
  (the quay deck height, `model.QUAY_DECK_M`: a quay's deck is the ground), so the water
  surface is at -1.5 and a bed at depth D lies at -(1.5 + D). The beds never go below the
  bed M9's tunnels assume (`tunnels.BED_M`: canal 3, river 7, sea 12 m under the ground
  datum), so the deepest water is canal 1.5, river 5.5 and sea 10.5 m. On a terrain city the
  water stands at M13's level and the ground meets it at the banks, so the depths are the
  full 3, 7 and 12 m.
- **Beds** (`model.WaterBed`): canals, basins and marinas flat between their walls; rivers and
  channels deepest along the centerline (depth by width along it, `along`); the sea shelving
  away from the coast over 250 m. The bed at a point comes from the nearest bank (its
  waterline and toe) and the body's depth there (`Beds.depth`).
- **Flow** (`model.Flow`): rivers and channels downstream toward `flows_into` or their mouth
  (the centerline oriented that way), canals and inlets a slow tide toward what they connect
  to, basins, marinas and ornamental pools still; the sea tidal, with no line.
- **Exposure** (`model.Exposure`): the sea's cells on a 32 m raster, each with its mean open
  water reach (fetch) over 16 integer directions (the map edge is the open sea): open, then
  sheltered under 1500 m, harbors under 400 m.
- **Banks** (`model.Bank`): the edge of the land against the water (`shore_lines`: the
  boundary of land minus water, without the map edge), sampled every 4 m and classed by what
  stands at it: a quay of the model, a canal wall (canals, basins, inlets, marinas, ornamental
  pools; a building at the water's edge), a road embankment (a road within 5 m), a beach or a
  marsh edge (those open spaces), riprap (port and spaceport shores, a building close
  behind) or a natural bank; runs of one kind under 12 m join their longer neighbor. Each
  bank keeps to one water body and one district, and is classed only on its own district's
  buildings, roads and open spaces, so a regenerated district changes only its own banks.

Every decision is an exact predicate or plain arithmetic on grid coordinates, in a fixed
order; ids come from the water body and the bank's anchor (`ids.anchor`).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient

from . import geom as G
from . import ids as ID
from .model import QUAY_DECK_M

FREEBOARD_M = QUAY_DECK_M
STEP_M = 4.0                 # shore samples
MIN_RUN_M = 12.0             # a shorter run of one kind joins its longer neighbor
EMBANK_M = 5.0               # a road this close to the edge makes it a road embankment
OPEN_NEAR_M = 3.0            # a beach or marsh open space this close sets the bank
WALL_NEAR_M = 2.0            # a building this close stands on a wall
RIPRAP_NEAR_M = 6.0          # ... this close on riprap
BEACH_CLEAR_M = 20.0         # a park or green on the sea this clear of buildings: a beach
CROSS_CAP = 0.3              # a sloped bank takes at most this share of the water's width
SHELF_REACH_M = 250.0        # the sea's bed falls to its depth over this
FLAT_REACH_M = 4.0           # a flat bed's depth this far past a sloped bank's waterline
WIDTH_FULL_M = 120.0         # a river this wide is at its full depth
EXPO_CELL_M = 32.0
MAX_FETCH_M = 3000.0
HARBOR_FETCH_M = 400.0
SHELTERED_FETCH_M = 1500.0
DIRS16 = ((1, 0), (2, 1), (1, 1), (1, 2), (0, 1), (-1, 2), (-1, 1), (-2, 1), (-1, 0),
          (-2, -1), (-1, -1), (-1, -2), (0, -1), (1, -2), (1, -1), (2, -1))

# a bank's slope (run per meter of height), toe depth (None: the bed's) by kind
SLOPE = {"quay": None, "canal_wall": None, "road_embankment": 1.5, "riprap": 2.0,
         "natural_bank": 3.0, "beach": 12.0, "marsh_edge": 20.0}
WALL_W = {"quay": 1.0, "canal_wall": 0.6}
TOE_M = {"road_embankment": 1.5, "riprap": 1.5, "natural_bank": 0.3, "beach": 0.0,
         "marsh_edge": 0.1}
STEEPER = {"beach": "natural_bank", "marsh_edge": "natural_bank", "natural_bank": "riprap",
           "riprap": "canal_wall", "road_embankment": "canal_wall"}
BANK_COLOR = {"quay": "#f2f4f8", "canal_wall": "#b9a27a", "road_embankment": "#ff9f43",
              "natural_bank": "#5fbf5a", "beach": "#f5d76e", "marsh_edge": "#3fb8a8",
              "riprap": "#9aa3b0"}
WALLED = ("canal", "basin", "inlet", "marina", "ornamental")
RIPRAP_ARCHETYPES = ("industrial_port", "spaceport")
SPEED = {"river": 0.8, "delta_branch": 0.5, "sea_channel": 0.4, "separation": 0.15,
         "canal": 0.05, "creek": 0.2, "inlet": 0.05}
MATERIAL = {"sea": "sand", "river": "mud", "delta_branch": "silt", "sea_channel": "sand",
            "separation": "silt", "canal": "silt", "creek": "gravel", "inlet": "mud",
            "basin": "mud", "marina": "mud", "ornamental": "stone"}


@dataclass
class Body:
    id: str
    coll: str            # seas, rivers, channels, waterways
    kind: str            # sea, river, delta_branch, sea_channel, separation, canal, creek, ...
    cls: str             # M9's class: sea, river, canal
    poly: object
    ent: object


def bodies(m) -> list[Body]:
    """Every water body, in model order (seas, rivers, channels, waterways)."""
    P = G.from_model_poly
    out = []
    for s in m.seas:
        out.append(Body(s.id, "seas", "sea", "sea", G.union([P(p) for p in s.polygons]), s))
    for r in m.rivers:
        out.append(Body(r.id, "rivers", "river", "river", P(r.polygon), r))
    for c in m.channels:
        cls = "sea" if c.kind == "sea_channel" else "canal" if c.kind == "separation" \
            else "river"
        out.append(Body(c.id, "channels", c.kind, cls, P(c.polygon), c))
    for w in m.waterways:
        out.append(Body(w.id, "waterways", "ornamental" if w.ornamental else w.kind,
                        "sea" if w.kind == "basin" else "canal", P(w.polygon), w))
    return out


def max_depth(cls: str, flat: bool) -> float:
    """The deepest water a body of M9's class may have: its bed at M9's bed or above."""
    from .tunnels import BED_M

    return BED_M[cls] - (FREEBOARD_M if flat else 0.0)


# --- beds and flow -------------------------------------------------------------------------

def _cum(pts) -> list[float]:
    out = [0.0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        out.append(out[-1] + math.hypot(bx - ax, by - ay))
    return out


def _median(vals: list[float]) -> float:
    v = sorted(vals)
    return v[len(v) // 2] if v else 0.0


def body_depth(b: Body, flat: bool) -> tuple[float, str, float, list]:
    """(depth_m, profile, reach_m, along) of a body."""
    D = max_depth(b.cls, flat)
    if b.kind == "sea":
        return D, "shelf", SHELF_REACH_M, []
    if b.kind in ("river", "delta_branch", "sea_channel", "separation"):
        line = [tuple(p) for p in b.ent.centerline]
        ws = list(b.ent.width_m)
        cum = _cum(line)
        lo = min(1.5, D)
        along = [{"s": G.q(s), "z": G.q(min(D, max(lo, D * w / WIDTH_FULL_M)))}
                 for s, w in zip(cum, ws)]
        return G.q(max(a["z"] for a in along)), "channel", G.q(_median(ws) / 2.0), along
    if b.kind in ("creek", "inlet"):
        return G.q(min(1.0 if b.kind == "creek" else D, D)), "channel", \
            G.q(max(2.0, _width_of(b) / 2.0)), []
    if b.kind == "ornamental":
        return G.q(min(0.6, D)), "flat", FLAT_REACH_M, []
    return G.q(D), "flat", FLAT_REACH_M, []


def _width_of(b: Body) -> float:
    """A waterway's typical width: twice its area over its outline."""
    P = G.length(b.poly)
    return 2.0 * G.area(b.poly) / P if P > 0 else 0.0


def _oriented(line: list, target) -> list:
    """The line oriented so it ends nearer the target polygon (downstream)."""
    if target is None or target.is_empty or len(line) < 2:
        return line
    d0 = G.dist(target, Point(line[0]))
    d1 = G.dist(target, Point(line[-1]))
    return line[::-1] if d0 < d1 else line


def body_flow(b: Body, polys: dict, sea) -> dict:
    if b.kind == "sea":
        return {"kind": "tidal", "speed_m_s": 0.1, "toward": None, "line": []}
    if b.kind in ("basin", "marina", "ornamental"):
        return {"kind": "still", "speed_m_s": 0.0, "toward": None, "line": []}
    e = b.ent
    line = [(G.q(x), G.q(y)) for x, y in (e.centerline or [])]
    if b.coll == "waterways":
        toward = e.connects_to
        kind = "downstream" if b.kind == "creek" else "tidal"
    else:
        toward = e.flows_into
        kind = "tidal" if b.kind == "sea_channel" else "downstream"
    if b.coll == "rivers" and e.mouth == "edge":
        pass          # rivers run from their entry edge to the mouth (hydro)
    else:
        tgt = sea if toward == "sea" else polys.get(toward)
        line = _oriented(line, tgt)
    return {"kind": kind, "speed_m_s": SPEED.get(b.kind, 0.1), "toward": toward,
            "line": line if len(line) >= 2 else []}


def exposure(m, ground, sea_poly) -> list[dict]:
    """The sea split by its fetch (see the module docstring)."""
    if sea_poly.is_empty:
        return []
    x0, y0, x1, y1 = m.bounds
    c = EXPO_CELL_M
    nx = int(math.ceil((x1 - x0) / c))
    ny = int(math.ceil((y1 - y0) / c))
    xs = x0 + (np.arange(nx) + 0.5) * c
    ys = y0 + (np.arange(ny) + 0.5) * c
    X, Y = np.meshgrid(xs, ys)
    shapely.prepare(ground)
    shapely.prepare(sea_poly)
    land = shapely.contains_xy(ground, X, Y)
    # every cell the sea reaches into (its fetch from the cell's middle)
    seam = np.zeros(X.shape, dtype=bool)
    sx0, sy0, sx1, sy1 = sea_poly.bounds
    i0, i1 = max(0, int((sx0 - x0) // c)), min(nx - 1, int((sx1 - x0) // c))
    j0, j1 = max(0, int((sy0 - y0) // c)), min(ny - 1, int((sy1 - y0) // c))
    for j in range(j0, j1 + 1):
        row = shapely.box(x0 + np.arange(i0, i1 + 1) * c, y0 + j * c,
                          x0 + np.arange(i0 + 1, i1 + 2) * c, y0 + (j + 1) * c)
        seam[j, i0:i1 + 1] = shapely.intersects(sea_poly, row)
    J, I = np.nonzero(seam)
    if not len(J):
        return []
    tot = np.zeros(len(J))
    for dx, dy in DIRS16:
        L = c * math.hypot(dx, dy)
        kmax = int(MAX_FETCH_M // L)
        f = np.full(len(J), MAX_FETCH_M)
        alive = np.ones(len(J), dtype=bool)
        for k in range(1, kmax + 1):
            ii, jj = I + k * dx, J + k * dy
            out = (ii < 0) | (ii >= nx) | (jj < 0) | (jj >= ny)
            alive &= ~out          # off the map: open sea, the full reach
            hit = alive.copy()
            ok = np.nonzero(alive)[0]
            hit[ok] = land[jj[ok], ii[ok]]
            f = np.where(hit, k * L, f)
            alive &= ~hit
            if not alive.any():
                break
        tot += f
    fetch = tot / len(DIRS16)
    cls = np.where(fetch < HARBOR_FETCH_M, 2, np.where(fetch < SHELTERED_FETCH_M, 1, 0))
    out = []
    for k, kind in enumerate(("open", "sheltered", "harbor")):
        sel = np.nonzero(cls == k)[0]
        if not len(sel):
            continue
        cells = [box(x0 + I[n] * c, y0 + J[n] * c, x0 + (I[n] + 1) * c, y0 + (J[n] + 1) * c)
                 for n in sel.tolist()]
        zone = G.inter(G.union_local(cells), sea_poly)
        pts_f = {(int(I[n]), int(J[n])): float(fetch[n]) for n in sel.tolist()}
        for p in G.parts(zone):
            if G.area(p) < 100.0:
                continue
            bx0, by0, bx1, by1 = p.bounds
            fs = [v for (i, j), v in pts_f.items()
                  if bx0 - c <= x0 + (i + 0.5) * c <= bx1 + c and
                  by0 - c <= y0 + (j + 0.5) * c <= by1 + c and
                  p.intersects(box(x0 + i * c, y0 + j * c, x0 + (i + 1) * c, y0 + (j + 1) * c))]
            out.append({"kind": kind, "polygon": G.to_model_poly(p),
                        "fetch_m": G.q(math.fsum(fs) / len(fs)) if fs else MAX_FETCH_M})
    out.sort(key=lambda e: (("open", "sheltered", "harbor").index(e["kind"]),
                            e["polygon"]["exterior"][0]))
    return out


# --- shore lines --------------------------------------------------------------------------

def ground_of(m):
    """Land minus every water body (grid coordinates)."""
    P = G.from_model_poly
    land = G.union([P(p) for lnd in m.land for p in lnd.polygons])
    wet = G.union([b.poly for b in bodies(m)])
    return (G.diff(land, wet) if not wet.is_empty else land), wet


def shore_lines(m, ground) -> list[list[tuple[float, float]]]:
    """The edge of the land against the water, with the water on the left: each ring of the
    ground in runs without the map edge (a whole ring stays closed: first point repeated)."""
    x0, y0, x1, y1 = m.bounds

    def border(a, b) -> bool:
        return (a[0] == b[0] and (abs(a[0] - x0) < 1e-6 or abs(a[0] - x1) < 1e-6)) or \
               (a[1] == b[1] and (abs(a[1] - y0) < 1e-6 or abs(a[1] - y1) < 1e-6))

    out = []
    for part in G.parts(ground):
        part = orient(part, sign=-1.0)     # land on the right of every ring
        for ring in [part.exterior, *part.interiors]:
            pts = [(G.q(x), G.q(y)) for x, y in ring.coords]
            n = len(pts) - 1
            on = [border(pts[k], pts[k + 1]) for k in range(n)]
            if not any(on):
                # (a whole ring: start at its lowest point, for a fixed start)
                k0 = min(range(n), key=lambda k: pts[k])
                out.append(pts[k0:n] + pts[:k0] + [pts[k0]])
                continue
            k0 = next(k for k in range(n) if on[k])
            cur = []
            for t in range(1, n + 1):
                k = (k0 + t) % n
                if on[k]:
                    if len(cur) >= 2:
                        out.append(cur)
                    cur = []
                else:
                    if not cur:
                        cur = [pts[k]]
                    cur.append(pts[k + 1])
            if len(cur) >= 2:
                out.append(cur)
    return [ln for ln in out if _cum(ln)[-1] > 0.05]


def _point_at(pts, cum, s) -> tuple[float, float, float, float]:
    """(x, y, unit tangent x, y) at arc length s."""
    k = 0
    while k < len(pts) - 2 and cum[k + 1] < s:
        k += 1
    L = cum[k + 1] - cum[k]
    t = 0.0 if L <= 0 else min(max((s - cum[k]) / L, 0.0), 1.0)
    (ax, ay), (bx, by) = pts[k], pts[k + 1]
    tx, ty = (bx - ax, by - ay)
    n = math.hypot(tx, ty) or 1.0
    return ax + (bx - ax) * t, ay + (by - ay) * t, tx / n, ty / n


def _cut(pts, cum, a, b) -> list[tuple[float, float]]:
    """The piece of a polyline from arc length a to b."""
    out = []
    x, y, _, _ = _point_at(pts, cum, a)
    out.append((G.q(x), G.q(y)))
    for k in range(1, len(pts) - 1):
        if a < cum[k] < b:
            out.append(pts[k])
    x, y, _, _ = _point_at(pts, cum, b)
    out.append((G.q(x), G.q(y)))
    ded = [out[0]]
    for p in out[1:]:
        if p != ded[-1]:
            ded.append(p)
    return ded


# --- banks --------------------------------------------------------------------------------

class _Near:
    """Per district: what stands near the shore (its buildings, roads, open spaces)."""

    def __init__(self, m, ground):
        P = G.from_model_poly
        self.archetype = {d.id: d.archetype for d in m.districts}
        self.dpolys = [(d.id, P(d.polygon)) for d in m.districts]
        for _, p in self.dpolys:
            shapely.prepare(p)
        self.dtree = shapely.STRtree([p for _, p in self.dpolys]) if self.dpolys else None
        by: dict = {}
        for b in m.buildings:
            if b.level or b.footprint is None:
                continue
            by.setdefault(("b", b.district_id), []).append((b.id, P(b.footprint)))
        for s in m.road_segments:
            if s.tunnel or "deck" in s.attrs or s.attrs.get("elevated") or s.level > 0:
                continue
            line = LineString(s.centerline)
            for did in (s.district_ids or [None]):
                by.setdefault(("r", did), []).append((s.id, line, s.width_m / 2.0))
        for o in m.open_spaces:
            if o.level:
                continue
            if o.kind in ("beach", "marsh"):
                by.setdefault(("o", o.district_id), []).append((o.kind, P(o.polygon)))
            elif o.kind in ("park", "green", "pocket_park"):
                by.setdefault(("g", o.district_id), []).append((o.kind, P(o.polygon)))
        for s in m.megasites:
            by.setdefault(("s", s.district_id), []).append((s.kind, P(s.polygon)))
        self.by = by
        self.trees: dict = {}
        self.quays = [(q.id, q.waterway_id, LineString(q.line)) for q in m.quays]
        self.qtree = shapely.STRtree([x[2] for x in self.quays]) if self.quays else None

    def district(self, x: float, y: float) -> str | None:
        if self.dtree is None:
            return None
        pt = Point(x, y)
        for k in sorted(int(i) for i in self.dtree.query(pt)):
            if self.dpolys[k][1].contains(pt):
                return self.dpolys[k][0]
        return None

    def tree(self, key):
        if key not in self.trees:
            items = self.by.get(key, [])
            geoms = [it[1] for it in items]
            self.trees[key] = (items, shapely.STRtree(geoms) if geoms else None)
        return self.trees[key]

    def near_items(self, key, pt, r: float):
        items, t = self.tree(key)
        if t is None:
            return []
        return [items[k] for k in sorted(int(i) for i in t.query(pt, predicate="dwithin",
                                                                distance=r))]


def _cross(poly, x, y, nx, ny, far: float = 400.0) -> float:
    """How far the water reaches from (x, y) along the normal (n into the water): from 1 m
    out (the land's edge and the body's outline can differ by a snapped hair) to where the
    ray first leaves the body."""
    sx, sy = x + nx * 1.0, y + ny * 1.0
    if not poly.covers(Point(sx, sy)):
        return 1.0
    ray = LineString([(sx, sy), (sx + nx * far, sy + ny * far)])
    hit = ray.intersection(poly.boundary)
    if hit.is_empty:
        return far
    return 1.0 + max(0.1, G.dist(Point(sx, sy), hit))


def _classify(near: _Near, b: Body, did, x, y) -> tuple:
    """(kind, quay id, segment id, clear land behind) of a shore sample at (x, y)."""
    pt = Point(x, y)
    if near.qtree is not None:
        for k in sorted(int(i) for i in near.qtree.query(pt, predicate="dwithin",
                                                          distance=1.0)):
            qid, wid, _ = near.quays[k]
            if wid == b.id:
                return "quay", qid, None, 0.0
    hard = 1e9
    for _, foot in near.near_items(("b", did), pt, BEACH_CLEAR_M + 1.0):
        hard = min(hard, G.dist(foot, pt))
    road, rd = None, 1e9
    for sid, line, hw in near.near_items(("r", did), pt, EMBANK_M + 30.0):
        d = G.dist(line, pt) - hw
        if d < rd or (d == rd and road is not None and sid < road):
            road, rd = sid, d
    if b.kind in WALLED:
        return "canal_wall", None, None, hard
    if road is not None and rd <= EMBANK_M:
        return "road_embankment", None, road, min(hard, max(rd, 0.0))
    kind = None
    for k, poly in near.near_items(("o", did), pt, OPEN_NEAR_M):
        kind = "beach" if k == "beach" else "marsh_edge"
        if k == "beach":
            break
    if kind is None:
        if hard < WALL_NEAR_M:
            kind = "canal_wall"
        elif hard < RIPRAP_NEAR_M:
            kind = "riprap"
        elif b.kind in ("sea", "river", "delta_branch", "sea_channel") and (
                near.archetype.get(did) in RIPRAP_ARCHETYPES or
                near.near_items(("s", did), pt, 0.0)):
            kind = "riprap"
        elif (b.kind == "sea" and hard >= BEACH_CLEAR_M and
              near.near_items(("g", did), pt, OPEN_NEAR_M)):
            kind = "beach"
        else:
            kind = "natural_bank"
    return kind, None, None, hard


class Levels:
    """The water surface of a body at a point (absolute on a terrain city)."""

    def __init__(self, m):
        self.flat = m.terrain is None
        self.lv = {}
        if not self.flat:
            for w in m.terrain.water_levels:
                self.lv[w.water_id] = w
        self.cl = {}
        for e in [*m.rivers, *m.channels]:
            pts = [tuple(p) for p in e.centerline]
            self.cl[e.id] = (pts, _cum(pts))

    def at(self, wid: str, x: float, y: float) -> float:
        if self.flat:
            return -FREEBOARD_M
        w = self.lv.get(wid)
        if w is None:
            return 0.0
        if not w.profile or wid not in self.cl:
            return float(w.level_m)
        from .elevated import _project
        from .terrain import z_on

        pts, cum = self.cl[wid]
        return float(z_on([(p.s, p.z) for p in w.profile], _project(pts, cum, (x, y))[0]))


def banks(m, bodies_: list[Body], beds: dict, ground) -> list[dict]:
    """Every shore line in typed banks (see the module docstring)."""
    near = _Near(m, ground)
    lv = Levels(m)
    gf = None
    if m.terrain is not None:
        from .terrain import ground_of as tground

        gf = tground(m)
    polys = [b.poly for b in bodies_]
    for p in polys:
        shapely.prepare(p)
    btree = shapely.STRtree(polys)
    rows = []
    for pts in shore_lines(m, ground):
        cum = _cum(pts)
        L = cum[-1]
        n = max(1, int(round(L / STEP_M)))
        step = L / n
        samples = []
        for k in range(n):
            s = (k + 0.5) * step
            x, y, tx, ty = _point_at(pts, cum, s)
            nx, ny = -ty, tx                  # left: the water
            wx, wy = x + nx * 1.0, y + ny * 1.0
            wp = Point(wx, wy)
            hits = sorted(int(i) for i in btree.query(wp))
            bi = next((i for i in hits if polys[i].contains(wp)), None)
            if bi is None:
                cand = sorted(int(i) for i in btree.query(Point(x, y), predicate="dwithin",
                                                          distance=5.0))
                bi = min(cand, key=lambda i: (G.dist(polys[i], Point(x, y)), i)) \
                    if cand else None
            if bi is None:
                bi = min(range(len(polys)), key=lambda i: (G.dist(polys[i], Point(x, y)), i))
            b = bodies_[bi]
            did = near.district(x - nx * 1.0, y - ny * 1.0)
            kind, qid, sid, hard = _classify(near, b, did, x, y)
            samples.append([s, x, y, nx, ny, b, did, kind, qid, sid, hard])
        runs = _runs(samples)
        closed = pts[0] == pts[-1] and len(runs) > 1 and _key(runs[0]) == _key(runs[-1])
        if closed:
            runs[0] = runs[-1] + runs[0]
            runs.pop()
        for i, r in enumerate(runs):
            a = 0.0 if i == 0 and not closed else r[0][0] - step / 2.0
            bnd = L if i == len(runs) - 1 and not closed else r[-1][0] + step / 2.0
            if len(runs) == 1:
                line = list(pts)
            elif a > bnd:
                # (the run across a ring's start)
                line = _cut(pts, cum, a, L) + _cut(pts, cum, 0.0, bnd)[1:]
            else:
                line = _cut(pts, cum, a, bnd)
            if len(line) < 2:
                continue
            rows.append(_bank_row(r, line, beds, lv, gf, polys, bodies_))
    return _named(rows)


def _key(run) -> tuple:
    s = run[0]
    return (s[5].id, s[6], s[7], s[8])


def _runs(samples: list) -> list[list]:
    runs: list[list] = []
    for smp in samples:
        if runs and _key(runs[-1]) == (smp[5].id, smp[6], smp[7], smp[8]):
            runs[-1].append(smp)
        else:
            runs.append([smp])
    # a short run joins its longer neighbor of the same body and district (never a quay)
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, r in enumerate(runs):
            if r[0][7] == "quay" or len(r) * STEP_M >= MIN_RUN_M:
                continue
            nbs = [j for j in (i - 1, i + 1) if 0 <= j < len(runs) and
                   runs[j][0][5].id == r[0][5].id and runs[j][0][6] == r[0][6] and
                   runs[j][0][7] != "quay"]
            if not nbs:
                continue
            j = max(nbs, key=lambda j: (len(runs[j]), -j))
            for smp in r:
                smp[7], smp[8], smp[9] = runs[j][0][7], runs[j][0][8], runs[j][0][9]
            if j < i:
                runs[j] = runs[j] + r
            else:
                runs[j] = r + runs[j]
            runs.pop(i)
            changed = True
            break
    return runs


def _bank_row(run, line, beds, lv, gf, polys, bodies_) -> dict:
    b = run[0][5]
    kind = run[0][7]
    did = run[0][6]
    bed = beds[b.id]
    D = bed["depth_m"]
    sids = sorted({smp[9] for smp in run if smp[9] is not None})
    sid = None
    if sids:
        cnt = {}
        for smp in run:
            if smp[9] is not None:
                cnt[smp[9]] = cnt.get(smp[9], 0) + 1
        sid = min(sids, key=lambda k: (-cnt[k], k))
    # height over the water (flat: the freeboard; terrain: the ground behind the edge)
    if gf is None:
        h = FREEBOARD_M
    else:
        hs = [gf.at(x - nx * 2.0, y - ny * 2.0) - lv.at(b.id, x, y)
              for _, x, y, nx, ny, *_ in run]
        h = max(0.2, _median(hs))
    widths = []
    for _, x, y, nx, ny, *_ in run:
        widths.append(_cross(polys[bodies_.index(b)], x, y, nx, ny))
    # (the lower quartile: a corner where the body meets another does not wall the bank)
    cross = sorted(widths)[len(widths) // 4] if widths else 100.0
    while True:
        if SLOPE[kind] is None:
            w = WALL_W[kind]
            break
        w = SLOPE[kind] * h
        cap = CROSS_CAP * cross
        if w <= cap or kind not in STEEPER:
            w = min(w, max(cap, 0.3))
            break
        if SLOPE[kind] * h * 0.5 <= cap:
            w = cap      # (up to twice as steep keeps its kind)
            break
        kind = STEEPER[kind]
    toe = D if SLOPE[kind] is None else min(D, TOE_M[kind])
    if kind != "quay" and SLOPE[kind] is None and bed["profile"] != "flat":
        toe = min(D, 3.0)
    return {"kind": kind, "type": f"bank.{kind}", "water_id": b.id, "line": line,
            "height_m": None if kind == "quay" else G.q(h), "width_m": G.q(w),
            "toe_m": G.q(toe), "district_id": did,
            "quay_id": run[0][8] if kind == "quay" else None,
            "segment_id": sid if kind == "road_embankment" else None, "attrs": {}}


def _named(rows: list[dict]) -> list[dict]:
    """Ids from the water body and the anchor; equal ids told apart by content."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(f"{r['water_id']}.bank.{ID.anchor({'line': r['line']})}",
                          []).append(r)
    out = []
    for base in sorted(groups):
        rs = sorted(groups[base], key=lambda r: json.dumps(r, sort_keys=True))
        for k, r in enumerate(rs):
            r["id"] = base if k == 0 else f"{base}.{k + 1}"
            out.append(r)
    return out


# --- the stage --------------------------------------------------------------------------

@dataclass
class Out:
    rows: dict           # collection -> rows (the water bodies with their M16 fields, banks)
    info: dict


def build(m) -> Out:
    """M16's water data on a finished city model."""
    flat = m.terrain is None
    with G.canonical():
        bl = bodies(m)
        if not bl:
            return Out({}, {"bodies": 0})
        ground, wet = ground_of(m)
        polys = {b.id: b.poly for b in bl}
        sea = polys.get("sea", Polygon())
        beds = {}
        upd: dict[str, dict] = {}
        for b in bl:
            D, prof, reach, along = body_depth(b, flat)
            bed = {"profile": prof, "reach_m": G.q(reach), "material": MATERIAL[b.kind],
                   "surface_m": -FREEBOARD_M if flat else None, "along": along}
            beds[b.id] = {"depth_m": G.q(D), **bed}
            upd[b.id] = {"depth_m": G.q(D), "bed": bed, "flow": body_flow(b, polys, sea)}
        expo = exposure(m, ground, sea)
        bank_rows = banks(m, bl, beds, ground)
    rows: dict = {}
    for coll in ("seas", "rivers", "channels", "waterways"):
        ents = getattr(m, coll)
        if not ents:
            continue
        new = []
        for e in ents:
            d = e.model_dump(mode="json")
            d.update(upd[e.id])
            if coll == "seas":
                d["exposure"] = expo
            new.append(d)
        rows[coll] = new
    rows["banks"] = bank_rows
    kinds: dict[str, float] = {}
    for r in bank_rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0.0) + _cum(r["line"])[-1]
    info = {"bodies": len(bl), "banks": len(bank_rows),
            "bank_m": {k: round(v, 1) for k, v in sorted(kinds.items())},
            "exposure": {k: sum(1 for e in expo if e["kind"] == k)
                         for k in ("open", "sheltered", "harbor")}}
    return Out(rows, info)


# --- the bed at a point -------------------------------------------------------------------

class Beds:
    """The bed of every water body at a point (`depth`), from the model's banks."""

    def __init__(self, m):
        self.m = m
        self.flat = m.terrain is None
        self.bl = {b.id: b for b in bodies(m)}
        self.bank_by: dict[str, list] = {}
        for k in m.banks:
            self.bank_by.setdefault(k.water_id, []).append(k)
        self.trees = {}
        for wid, bs in self.bank_by.items():
            self.trees[wid] = shapely.STRtree([LineString(k.line) for k in bs])
        self.polys = [b.poly for b in self.bl.values()]
        self.ids = list(self.bl)
        for p in self.polys:
            shapely.prepare(p)
        self.btree = shapely.STRtree(self.polys) if self.polys else None
        self.cl = {}
        for wid, b in self.bl.items():
            e = b.ent
            if b.coll in ("rivers", "channels"):
                pts = [tuple(p) for p in e.centerline]
                self.cl[wid] = (pts, _cum(pts), list(e.width_m))

    def body_at(self, x: float, y: float) -> str | None:
        if self.btree is None:
            return None
        pt = Point(x, y)
        for k in sorted(int(i) for i in self.btree.query(pt)):
            if self.polys[k].covers(pt):
                return self.ids[k]
        return None

    def depth(self, wid: str, x: float, y: float) -> float:
        """Water depth under the surface of body `wid` at (x, y); 0 over a bank's slope."""
        return float(self.depth_many(wid, [x], [y])[0])

    def bed_z(self, wid: str, x: float, y: float) -> float:
        """The bed's height in the frame M9's tunnels measure from (the ground datum on a
        flat city, the water's level on a terrain city)."""
        surf = -FREEBOARD_M if self.flat else 0.0
        return surf - self.depth(wid, x, y)

    def depth_many(self, wid: str, xs, ys) -> np.ndarray:
        """`depth` at many points of body `wid` (vectorized, the same arithmetic)."""
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        b = self.bl[wid]
        e = b.ent
        out = np.zeros(len(xs))
        if e.bed is None or e.depth_m is None or not len(xs):
            return out
        bed = e.bed
        D = np.full(len(xs), float(e.depth_m))
        reach = np.full(len(xs), float(bed.reach_m))
        if wid in self.cl and bed.along:
            pts, cum, ws = self.cl[wid]
            s = _project_many(pts, cum, xs, ys)
            D = np.interp(s, [a.s for a in bed.along], [a.z for a in bed.along])
            reach = np.maximum(1.0, np.interp(s, cum, ws) / 2.0)
        t = self.trees.get(wid)
        if t is None:
            return D
        pts_ = shapely.points(np.stack([xs, ys], axis=1))
        bks = self.bank_by[wid]
        lines = np.array([LineString(bk.line) for bk in bks], dtype=object)
        k, d = self._nearest(t, lines, pts_)
        w = np.array([bk.width_m for bk in bks])[k]
        toe = np.minimum(np.array([bk.toe_m for bk in bks])[k], D)
        if bed.profile == "flat":
            span = np.maximum(1.0, np.full(len(xs), FLAT_REACH_M))
        else:
            span = np.maximum(1.0, reach - w)
        u = np.minimum(1.0, np.maximum(0.0, d - w) / span)
        ramp = u * (2.0 - u) if bed.profile == "channel" else u
        return np.where(d < w, 0.0, toe + (D - toe) * ramp)


    @staticmethod
    def _nearest(tree, lines, pts_):
        """(index, distance) of the nearest bank line to each point: distances rounded to
        1e-6 m, ties to the first bank (GEOS's own pick among equidistant lines, common by a
        joint between two banks, follows its sort, which differs between machines)."""
        _, d0 = tree.query_nearest(pts_, all_matches=False, return_distance=True)
        pi, li = tree.query(pts_, predicate="dwithin", distance=d0 + 1e-3)
        dd = np.round(shapely.distance(lines[li], pts_[pi]), G.DIST_DIGITS)
        order = np.lexsort((li, dd, pi))
        first = np.r_[True, pi[order][1:] != pi[order][:-1]]
        k = np.zeros(len(pts_), dtype=np.int64)
        d = np.zeros(len(pts_))
        k[pi[order][first]] = li[order][first]
        d[pi[order][first]] = dd[order][first]
        return k, d


def _project_many(pts, cum, xs, ys, chunk: int = 4000) -> np.ndarray:
    """Arc length of the nearest point of a polyline to each point."""
    A = np.asarray(pts[:-1], dtype=np.float64)
    B = np.asarray(pts[1:], dtype=np.float64)
    AB = B - A
    L2 = np.maximum((AB * AB).sum(axis=1), 1e-12)
    c0 = np.asarray(cum[:-1])
    out = np.zeros(len(xs))
    for i in range(0, len(xs), chunk):
        X = xs[i:i + chunk, None]
        Y = ys[i:i + chunk, None]
        t = np.clip(((X - A[:, 0]) * AB[:, 0] + (Y - A[:, 1]) * AB[:, 1]) / L2, 0.0, 1.0)
        px = A[:, 0] + t * AB[:, 0]
        py = A[:, 1] + t * AB[:, 1]
        d2 = (X - px) ** 2 + (Y - py) ** 2
        j = np.argmin(d2, axis=1)
        r = np.arange(len(j))
        out[i:i + chunk] = c0[j] + t[r, j] * np.sqrt(L2[j])
    return out
