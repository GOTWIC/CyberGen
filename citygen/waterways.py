"""Stage 3, inner waterways: canals, creeks, inlets, harbor basins and marinas, with quays.

Waterways are generated per district from its `waterways` style and density, inside the district
polygon and away from its land boundaries (so they never run along a neighbor). Every waterway
starts at the district's water frontage (sea, river, channel) or at another waterway, so all of
them connect to the network; anything that would end up floating is dropped. District polygons
keep covering their inner waterways: subtract the waterways for buildable land.

- canal_grid: straight canals on the district grid angle, spacing from density.
- organic_canals: meandering canals from the frontage inward, some running through to another
  frontage point, with side branches.
- creeks: narrower, more meandering dead-end channels with small branches.
- inlets: tapering arms of water reaching in from the frontage.
- harbor_basins: rectangular basins cut into the shore, perpendicular to it.
- marina: rounded basins at the shore.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from . import geom as G
from . import hydro as H
from .defaults import derive_seed
from .spec import CitySpec

LAND_MARGIN_M = 45.0
KIND = {"canal_grid": "canal", "organic_canals": "canal", "creeks": "creek", "inlets": "inlet",
        "harbor_basins": "basin", "marina": "marina"}
WIDTH_M = {"canal_grid": 18.0, "organic_canals": 14.0, "creeks": 9.0}
QUAY_WIDTH_M = {"canal": 5.0, "creek": 3.0, "inlet": 6.0, "basin": 15.0, "marina": 8.0}


@dataclass
class WaterwayRec:
    id: str
    kind: str
    style: str
    district: str
    centerline: LineString | None
    polygon: object
    name: str | None = None
    connects_to: str | None = None
    ornamental: bool = False


@dataclass
class QuayRec:
    id: str
    waterway_id: str
    line: LineString
    width_m: float


@dataclass
class Waterways:
    items: list[WaterwayRec] = field(default_factory=list)
    quays: list[QuayRec] = field(default_factory=list)


def _lines(g) -> list[LineString]:
    if g.is_empty:
        return []
    g = shapely.line_merge(g) if not isinstance(g, LineString) else g
    if isinstance(g, LineString):
        return [g]
    out = []
    for x in getattr(g, "geoms", []):
        out += _lines(x) if not isinstance(x, LineString) else [x]
    return out


def _inward(poly, p: Point, depth: float = 80.0) -> np.ndarray:
    inner = poly.buffer(-depth)
    if inner.is_empty:
        inner = poly.buffer(-depth / 4)
    q = nearest_points(inner if not inner.is_empty else poly.centroid, p)[0]
    v = np.array([q.x - p.x, q.y - p.y])
    n = np.linalg.norm(v)
    return v / n if n > 1e-6 else np.array([0.0, 1.0])


def _entries(frontage: list[LineString], n: int, rng, avoid, min_len: float = 80.0):
    usable = [f for f in frontage if f.length >= min_len]
    total = sum(f.length for f in usable)
    if not usable or n <= 0:
        return []
    out = []
    for k in range(n):
        s = (k + 0.5 + rng.uniform(-0.25, 0.25)) / n * total
        for f in usable:
            if s <= f.length:
                p = f.interpolate(min(max(s, 30.0), f.length - 30.0))
                if avoid.is_empty or p.distance(avoid) > 70:
                    out.append(p)
                break
            s -= f.length
    return out


def _piece_from(geom, start: Point):
    """Part of a clipped line that starts nearest to `start`."""
    ls = _lines(geom)
    if not ls:
        return None
    best = min(ls, key=lambda g: g.distance(start))
    if best.distance(start) > 25:
        return None
    if Point(best.coords[-1]).distance(start) < Point(best.coords[0]).distance(start):
        best = LineString(best.coords[::-1])
    return best


def _canal_grid(d, poly, allowed, density, rng):
    theta = math.radians(d.grid_angle_deg or 0.0)
    spacing = 600.0 - 380.0 * density
    c = poly.centroid
    minx, miny, maxx, maxy = poly.bounds
    reach = math.hypot(maxx - minx, maxy - miny)
    out = []
    for k, (ang, sp) in enumerate(((theta, spacing), (theta + math.pi / 2, 2 * spacing))):
        ux, uy = math.cos(ang), math.sin(ang)
        nx, ny = -uy, ux
        phase = rng.uniform(0, sp)
        m = int(reach / sp) + 2
        for i in range(-m, m + 1):
            off = i * sp + phase
            a = (c.x + nx * off - ux * reach, c.y + ny * off - uy * reach)
            b = (c.x + nx * off + ux * reach, c.y + ny * off + uy * reach)
            for seg in _lines(LineString([a, b]).intersection(allowed)):
                if seg.length >= 120:
                    out.append(("canal_grid", seg, seg.buffer(WIDTH_M["canal_grid"] / 2,
                                                              cap_style="flat")))
    return out


def _meander_to(a: Point, b: Point, amp_frac: float, lam: float, rng) -> LineString:
    length = a.distance(b)
    nz = G.noise1d(rng, lam, octaves=2)

    def off(ts):
        ts = np.asarray(ts)
        return amp_frac * length * nz(ts * length) * np.sin(math.pi * ts)

    return G.wiggle_path((a.x, a.y), (b.x, b.y), off, step=10.0)


def _organic(style, d, poly, allowed, frontage, density, rng, avoid):
    creek = style == "creeks"
    width = WIDTH_M[style]
    total = sum(f.length for f in frontage)
    n = int(np.clip(round(density * total / (350.0 if creek else 450.0)), 1, 7 if creek else 6))
    entries = _entries(frontage, n, rng, avoid)
    inner = poly.buffer(-120)
    if inner.is_empty:
        inner = poly.buffer(-40)
    if inner.is_empty:
        return []
    out = []
    minx, miny, maxx, maxy = inner.bounds
    for k, p in enumerate(entries):
        v = _inward(poly, p)
        start = Point(p.x - v[0] * 12, p.y - v[1] * 12)
        length = rng.uniform(220, 520) if creek else rng.uniform(350, 900)
        target = Point(p.x + v[0] * length, p.y + v[1] * length)
        if not inner.contains(target):
            target = nearest_points(inner, target)[0]
        through = (not creek) and len(entries) > 1 and rng.uniform() < density
        if through:
            other = entries[(k + 1) % len(entries)]
            line = _meander_to(start, target, 0.12, 260.0, rng)
            back = _meander_to(target, other, 0.12, 260.0, rng)
            line = LineString(list(line.coords) + list(back.coords)[1:])
        else:
            line = _meander_to(start, target, 0.22 if creek else 0.14, 180.0 if creek else 260.0,
                               rng)
        main = _piece_from(line.intersection(allowed.union(start.buffer(14))), start)
        if main is None or main.length < 100:
            continue
        out.append((style, main, main.buffer(width / 2, cap_style="round")))
        branches = 2 if creek else 1
        for j in range(branches):
            if rng.uniform() > density + 0.2 or main.length < 220:
                continue
            at = main.interpolate(rng.uniform(0.35, 0.75), normalized=True)
            nxt = main.interpolate(min(main.project(at) + 10, main.length))
            tx, ty = nxt.x - at.x, nxt.y - at.y
            sgn = 1 if (j + k) % 2 == 0 else -1
            ang = math.atan2(ty, tx) + sgn * math.radians(rng.uniform(45, 75))
            blen = rng.uniform(120, 260) if creek else rng.uniform(150, 320)
            end = Point(at.x + math.cos(ang) * blen, at.y + math.sin(ang) * blen)
            br = _meander_to(at, end, 0.18, 160.0, rng)
            br = _piece_from(br.intersection(allowed.union(at.buffer(width))), at)
            if br is not None and br.length >= 80:
                bw = width * 0.8
                out.append((style, br, br.buffer(bw / 2, cap_style="round")))
    return out


def _inlets(d, poly, allowed, frontage, density, rng, avoid):
    total = sum(f.length for f in frontage)
    n = int(np.clip(round(density * total / 700.0), 1, 4))
    out = []
    for p in _entries(frontage, n, rng, avoid):
        v = _inward(poly, p)
        length = rng.uniform(180, 380)
        start = Point(p.x - v[0] * 20, p.y - v[1] * 20)
        end = Point(p.x + v[0] * length, p.y + v[1] * length)
        line = _meander_to(start, end, 0.08, 300.0, rng)
        w0, w1 = rng.uniform(55, 85), rng.uniform(14, 22)
        poly_i = G.variable_buffer(line, lambda ts: w0 + (w1 - w0) * np.asarray(ts) ** 0.8)
        poly_i = G.polygonal(poly_i.intersection(allowed.union(start.buffer(w0))))
        main = G.parts(poly_i)[0] if G.parts(poly_i) else None
        if main is None or main.area < 4000:
            continue
        out.append(("inlets", line.intersection(main.buffer(1)), main))
    return out


def _basins(style, d, poly, allowed, frontage, density, rng, avoid):
    total = sum(f.length for f in frontage)
    marina = style == "marina"
    n = int(np.clip(round(density * total / (900.0 if marina else 600.0)), 1, 2 if marina else 4))
    out = []
    taken = Polygon()
    for p in _entries(frontage, n, rng, avoid, min_len=200.0):
        v = _inward(poly, p, 120.0)
        ang = math.atan2(v[1], v[0])
        if marina:
            w, depth = rng.uniform(140, 200), rng.uniform(100, 150)
            shape = affinity.scale(Point(0, 0).buffer(1.0, quad_segs=24), depth, w / 2)
            shape = shape.intersection(Polygon([(-20, -w), (2 * depth, -w), (2 * depth, w),
                                                (-20, w)]))
        else:
            w, depth = rng.uniform(120, 200), rng.uniform(220, 380)
            shape = Polygon([(-20, -w / 2), (depth, -w / 2), (depth, w / 2), (-20, w / 2)])
        for _ in range(4):
            cand = affinity.translate(affinity.rotate(shape, ang, origin=(0, 0),
                                                      use_radians=True), p.x, p.y)
            land_part = cand.intersection(poly)
            if land_part.area > 0 and \
                    cand.intersection(allowed).area >= 0.85 * land_part.area and \
                    (taken.is_empty or cand.distance(taken) > 60):
                break
            shape = affinity.scale(shape, 0.8, 0.85, origin=(0, 0))
        else:
            continue
        cand = G.polygonal(cand.intersection(poly.union(p.buffer(25))))
        main = G.parts(cand)[0] if G.parts(cand) else None
        if main is None or main.area < 6000:
            continue
        taken = taken.union(main)
        line = LineString([(p.x, p.y), (p.x + v[0] * depth * 0.9, p.y + v[1] * depth * 0.9)])
        out.append((style, line, main))
    return out


def _body_at(h: H.Hydro, geom) -> str | None:
    for b in h.bodies:
        if b.polygon.distance(geom) <= 1.0:
            return b.id
    if not h.sea.is_empty and h.sea.distance(geom) <= 1.0:
        return "sea"
    return None


def build_waterways(spec: CitySpec, h: H.Hydro, polygons: dict[str, object],
                    district_ids: dict[str, str]) -> Waterways:
    out = Waterways()
    net = h.water
    shapely.prepare(net)
    wide_water = unary_union([h.sea] + [b.polygon for b in h.bodies if b.kind != "separation"])
    for d in spec.districts:
        poly = polygons.get(d.name)
        ww = d.waterways
        if poly is None or poly.is_empty or ww is None or not ww.style or ww.density <= 0:
            continue
        rng = np.random.default_rng(derive_seed(d.seed, "waterways"))
        wet = net.buffer(2.0)
        frontage = [f for f in _lines(poly.boundary.intersection(wet)) if f.length > 20]
        land_edge = poly.boundary.difference(wet)
        allowed = G.polygonal(poly.difference(land_edge.buffer(LAND_MARGIN_M))) \
            if not land_edge.is_empty else poly
        if not frontage or allowed.is_empty:
            continue
        density = ww.density / math.sqrt(len(ww.style))
        # Basins and marinas open onto wide water only (sea, rivers, branches), not canals.
        wide = wide_water.buffer(2.0)
        wide_front = [f for f in _lines(poly.boundary.intersection(wide)) if f.length > 20]
        cands = []
        for style in ww.style:
            if style == "canal_grid":
                cands += _canal_grid(d, poly, allowed, density, rng)
            elif style in ("organic_canals", "creeks"):
                cands += _organic(style, d, poly, allowed, frontage, density, rng, land_edge)
            elif style == "inlets":
                cands += _inlets(d, poly, allowed, frontage, density, rng, land_edge)
            else:
                cands += _basins(style, d, poly, allowed, wide_front, density, rng, land_edge)
        cands = [(s, line, G.clean(G.polygonal(p.intersection(poly.buffer(30)))))
                 for s, line, p in cands]
        cands = [c for c in cands if not c[2].is_empty]
        # Connectivity: keep what reaches the network directly or through kept waterways.
        did = district_ids[d.name]
        recs: list[WaterwayRec] = []
        pending = list(range(len(cands)))
        connected: list[tuple[int, str]] = []
        for i in pending:
            body = _body_at(h, cands[i][2])
            if body is not None:
                connected.append((i, body))
        done = {i for i, _ in connected}
        frontier = [i for i, _ in connected]
        parent: dict[int, str] = {i: b for i, b in connected}
        while frontier:
            nxt = []
            for i in pending:
                if i in done:
                    continue
                for j in frontier:
                    if cands[i][2].distance(cands[j][2]) <= 1.0:
                        parent[i] = f"#{j}"
                        done.add(i)
                        nxt.append(i)
                        break
            frontier = nxt
        kept = sorted(done)
        ids = {i: f"{did}.ww{k + 1:02d}" for k, i in enumerate(kept)}
        names = list(ww.named)
        by_len = sorted(kept, key=lambda i: (-(cands[i][1].length if cands[i][1] is not None
                                                else 0.0), i))
        name_of = {i: names[k] for k, i in enumerate(by_len[:len(names)])}
        for i in kept:
            style, line, p = cands[i]
            conn = parent[i]
            if conn.startswith("#"):
                conn = ids[int(conn[1:])]
            cl = line if isinstance(line, LineString) else (_lines(line)[0] if _lines(line)
                                                           else None)
            recs.append(WaterwayRec(ids[i], KIND[style], style, d.name, cl, p,
                                    name_of.get(i), conn))
        out.items += recs
    _quays(h, out)
    return out


def _quays(h: H.Hydro, ww: Waterways) -> None:
    net = h.water.buffer(1.0)
    for w in ww.items:
        others = unary_union([x.polygon for x in ww.items if x is not w and
                              x.polygon.distance(w.polygon) < 1.0])
        bank = w.polygon.boundary.difference(net)
        if not others.is_empty:
            bank = bank.difference(others.buffer(1.0))
        k = 0
        for line in _lines(bank):
            if line.length < 25:
                continue
            k += 1
            ww.quays.append(QuayRec(f"{w.id}.q{k}", w.id, line, QUAY_WIDTH_M[w.kind]))

