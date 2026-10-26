"""Stage 3, inner waterways: canals, creeks, inlets, harbor basins and marinas, with quays.

Waterways are generated per district from its `waterways` style and density, inside the district
polygon and away from its land boundaries (so they never run along a neighbor). Every waterway
starts at the district's water frontage (sea, river, channel) or at another waterway, so all of
them connect to the network; anything that would end up floating is dropped. District polygons
keep covering their inner waterways: subtract the waterways for buildable land.

- canal_grid: straight canals on the district grid angle, spacing from density; every canal
  ends at open water or at a cross canal (no frayed dead ends).
- organic_canals: smooth meandering canals from the frontage inward with a few side branches,
  a mostly tree-like network: a canal stops before it comes within 70 m of another one, unless
  it meets it at 50 degrees or more and closes one of at most two loops per district.
- creeks: narrower, more meandering dead-end channels with small branches, same spacing rule.
- inlets: tapering arms of water reaching in from the frontage.
- harbor_basins: a row of parallel rectangular slips cut into the longest straight stretch of
  deep-water frontage, separated by piers (a port layout).
- marina: rounded basins just behind the shore, each with a short entrance channel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, substring, unary_union

from . import dmath as M
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
    n = M.norm(v)
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


def _canal_grid(d, poly, allowed, density, rng, wet):
    """Straight canals on the district grid angle. Every canal ends at open water or at a
    cross canal: dead ends at the land margin are trimmed back to the last junction, so the
    grid stops cleanly at its quays instead of fraying out."""
    theta = M.radians(d.grid_angle_deg or 0.0)
    spacing = 600.0 - 380.0 * density
    c = poly.centroid
    minx, miny, maxx, maxy = poly.bounds
    reach = M.hypot(maxx - minx, maxy - miny)
    fams: list[list[LineString]] = []
    for ang, sp in ((theta, spacing), (theta + math.pi / 2, 2 * spacing)):
        ux, uy = M.cos(ang), M.sin(ang)
        nx, ny = -uy, ux
        phase = rng.uniform(0, sp)
        m = int(reach / sp) + 2
        fam = []
        for i in range(-m, m + 1):
            off = i * sp + phase
            a = (c.x + nx * off - ux * reach, c.y + ny * off - uy * reach)
            b = (c.x + nx * off + ux * reach, c.y + ny * off + uy * reach)
            fam += [s for s in _lines(LineString([a, b]).intersection(allowed)) if s.length >= 60]
        fams.append(fam)
    for _ in range(3):
        new = []
        for k, fam in enumerate(fams):
            cross = unary_union(fams[1 - k]) if fams[1 - k] else LineString()
            kept = []
            for seg in fam:
                anchors = []
                for end in (0.0, seg.length):
                    if wet.distance(seg.interpolate(end)) <= 3.0:
                        anchors.append(end)
                hit = seg.intersection(cross)
                anchors += [seg.project(Point(p)) for g in getattr(hit, "geoms", [hit])
                            for p in getattr(g, "coords", [])]
                if len(anchors) < 2 and not (anchors and anchors[0] in (0.0, seg.length)
                                             and wet.distance(seg.interpolate(anchors[0])) <= 3):
                    continue
                lo, hi = (min(anchors), max(anchors)) if len(anchors) >= 2 else (0.0, seg.length)
                if hi - lo >= 100:
                    kept.append(substring(seg, lo, hi))
            new.append(kept)
        fams = new
    out = []
    for fam in fams:
        for seg in fam:
            seg = _extend_into(seg, wet, 10.0)
            out.append(("canal_grid", seg, seg.buffer(WIDTH_M["canal_grid"] / 2, cap_style="flat",
                                                      join_style="mitre")))
    return out


def _extend_into(seg: LineString, wet, by: float) -> LineString:
    """Extend the ends of a straight segment that touch water a little into it."""
    cs = list(seg.coords)
    (x0, y0), (x1, y1) = cs[0], cs[-1]
    ln = seg.length or 1.0
    ux, uy = (x1 - x0) / ln, (y1 - y0) / ln
    if wet.distance(Point(cs[0])) <= 3.0:
        cs[0] = (x0 - ux * by, y0 - uy * by)
    if wet.distance(Point(cs[-1])) <= 3.0:
        cs[-1] = (x1 + ux * by, y1 + uy * by)
    return LineString(cs)


def _meander_to(a: Point, b: Point, amp_frac: float, lam: float, rng) -> LineString:
    return G.course((a.x, a.y), (b.x, b.y), rng, wavelength=lam,
                    omega=min(0.25 + 3.0 * amp_frac, 1.0), step=8.0, ramp=(0.15, 0.15))


def _angle_at(a: LineString, b: LineString, p: Point) -> float:
    """Acute angle (degrees) between two lines where they meet at p."""
    def tan(line):
        d = line.project(p)
        q0 = line.interpolate(max(d - 15.0, 0.0))
        q1 = line.interpolate(min(d + 15.0, line.length))
        return np.array([q1.x - q0.x, q1.y - q0.y])
    u, v = tan(a), tan(b)
    nu, nv = M.hypot(*u), M.hypot(*v)
    if nu < 1e-6 or nv < 1e-6:
        return 90.0
    c = abs(M.dot(u, v)) / (nu * nv)
    return M.degrees(M.acos(min(c, 1.0)))


class _Net:
    """Accepted canal centerlines of one district: a new canal stops before it comes within
    `gap` of the network (no near duplicates), unless it meets it steeply enough to close a
    loop (a few per district)."""

    def __init__(self, gap: float, loops: int):
        self.lines: list[LineString] = []
        self.gap = gap
        self.loops = loops
        self.shore = None  # the district's water frontage: canals do not run along it

    def fit(self, line: LineString, skip: float, allowed) -> LineString | None:
        pts = G.resample(line, 8.0)
        ds = np.linspace(0, line.length, len(pts))
        sp = shapely.points(pts)
        if self.shore is not None and not self.shore.is_empty:
            near_shore = (shapely.distance(self.shore, sp) < 0.8 * self.gap) & (ds > 90.0)
            if near_shore.any():
                d = max(float(ds[int(np.argmax(near_shore))]) - 20.0, 0.0)
                if d < 100.0:
                    return None
                line = substring(line, 0, d)
                pts, ds, sp = pts[ds <= d], ds[ds <= d], sp[ds <= d]
        if not self.lines:
            return line
        net = unary_union(self.lines)
        dist = shapely.distance(net, sp)
        close = (dist < self.gap) & (ds > skip)
        if not close.any():
            return line
        i = int(np.argmax(close))
        if self.loops > 0 and i > 0:
            # Close a loop if the canal heads into the network steeply.
            j = min(i + int(self.gap / 8.0) + 2, len(pts) - 1)
            probe = LineString(pts[:j + 1])
            hit = probe.intersection(net)
            if not hit.is_empty:
                p = nearest_points(hit, Point(pts[0]))[0]
                d = probe.project(p)
                other = min(self.lines, key=lambda g: g.distance(p))
                if _angle_at(probe, other, p) >= 50.0 and d > skip:
                    self.loops -= 1
                    return substring(probe, 0, d + 4.0)
        d = max(float(ds[i]) - self.gap * 0.6, 0.0)
        return substring(line, 0, d) if d > 0 else None

    def add(self, line: LineString) -> None:
        self.lines.append(line)


def _organic(style, d, poly, allowed, frontage, density, rng, avoid, net: _Net):
    """A sparse, smooth, mostly tree-like canal network: main canals from the water frontage
    inward, a few side branches at 50 to 75 degrees, spacing kept by `net`."""
    creek = style == "creeks"
    width = WIDTH_M[style]
    total = sum(f.length for f in frontage)
    n = int(np.clip(round(density * total / (380.0 if creek else 420.0)), 1, 6 if creek else 5))
    entries = _entries(frontage, n, rng, avoid)
    inner = poly.buffer(-120)
    if inner.is_empty:
        inner = poly.buffer(-40)
    if inner.is_empty:
        return []
    out = []
    for k, p in enumerate(entries):
        v = _inward(poly, p)
        start = Point(p.x - v[0] * 12, p.y - v[1] * 12)
        length = rng.uniform(260, 520) if creek else rng.uniform(400, 850)
        target = Point(p.x + v[0] * length, p.y + v[1] * length)
        if not inner.contains(target):
            target = nearest_points(inner, target)[0]
        if start.distance(target) < 80:
            continue
        line = _meander_to(start, target, 0.16 if creek else 0.1, 200.0 if creek else 320.0,
                           rng)
        main = _piece_from(line.intersection(allowed.union(start.buffer(14))), start)
        if main is None:
            continue
        main = net.fit(main, 40.0, allowed)
        if main is None or main.length < 100:
            continue
        net.add(main)
        out.append((style, main, main.buffer(width / 2, cap_style="round")))
        for j in range(2):
            if rng.uniform() > density + 0.25 or main.length < 260:
                continue
            at = main.interpolate(rng.uniform(0.4, 0.75), normalized=True)
            nxt = main.interpolate(min(main.project(at) + 10, main.length))
            tx, ty = nxt.x - at.x, nxt.y - at.y
            sgn = 1 if (j + k) % 2 == 0 else -1
            ang = M.atan2(ty, tx) + sgn * M.radians(rng.uniform(50, 75))
            blen = rng.uniform(140, 260) if creek else rng.uniform(180, 340)
            end = Point(at.x + M.cos(ang) * blen, at.y + M.sin(ang) * blen)
            br = _meander_to(at, end, 0.12, 180.0, rng)
            br = _piece_from(br.intersection(allowed.union(at.buffer(width))), at)
            if br is None:
                continue
            br = net.fit(br, 45.0, allowed)
            if br is not None and br.length >= 90:
                net.add(br)
                out.append((style, br, br.buffer(width * 0.4, cap_style="round")))
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
        poly_i = G.variable_buffer(
            line, lambda ts: w0 + (w1 - w0) * M.power(np.asarray(ts), 0.8))
        poly_i = G.polygonal(poly_i.intersection(allowed.union(start.buffer(w0))))
        main = G.parts(poly_i)[0] if G.parts(poly_i) else None
        if main is None or main.area < 4000:
            continue
        out.append(("inlets", line.intersection(main.buffer(1)), main))
    return out


def _shore_frame(f: LineString, s: float, poly) -> tuple[Point, np.ndarray, np.ndarray]:
    """Point, unit tangent and unit inland normal of a frontage line at s."""
    p = f.interpolate(s)
    a = f.interpolate(max(s - 60.0, 0.0))
    b = f.interpolate(min(s + 60.0, f.length))
    t = np.array([b.x - a.x, b.y - a.y])
    t = t / (M.hypot(*t) or 1.0)
    n = np.array([-t[1], t[0]])
    if not poly.contains(Point(p.x + n[0] * 25, p.y + n[1] * 25)):
        n = -n
    return p, t, n


def _rect(p: Point, axis: np.ndarray, width: float, back: float, depth: float) -> Polygon:
    """Rectangle across `width`, from `back` meters behind p to `depth` meters along axis."""
    q = np.array([-axis[1], axis[0]]) * width / 2
    o = np.array([p.x, p.y])
    return Polygon([o - axis * back - q, o + axis * depth - q, o + axis * depth + q,
                    o - axis * back + q])


def _harbor(d, poly, allowed, frontage, density, rng, avoid):
    """Port docks: a row of parallel rectangular slips cut square (or at a common angle) into
    the longest straight stretch of deep-water frontage, separated by piers, like a real
    container or break-bulk port."""
    fronts = sorted([f for f in frontage if f.length >= 300], key=lambda f: -f.length)
    out = []
    taken = Polygon()
    budget = int(np.clip(round(1 + density * 4), 2, 6))
    for f in fronts[:2]:
        if budget <= 0:
            break
        f = f.simplify(15.0)
        mid = f.length / 2
        p, t, n = _shore_frame(f, mid, poly)
        tilt = M.radians(float(rng.choice([0.0, 0.0, 20.0, -20.0])))
        axis = np.array([n[0] * M.cos(tilt) - n[1] * M.sin(tilt),
                         n[0] * M.sin(tilt) + n[1] * M.cos(tilt)])
        ws, wp = float(rng.uniform(70, 95)), float(rng.uniform(110, 150))
        depth = float(rng.uniform(240, 360))
        pitch = ws + wp
        k = int(min(budget, max(1, (f.length - 2 * 80) // pitch)))
        s0 = mid - (k - 1) * pitch / 2
        for i in range(k):
            s = s0 + i * pitch
            if s < 40 or s > f.length - 40:
                continue
            q, _, nq = _shore_frame(f, s, poly)
            if M.dot(nq, n) < 0.8:
                continue  # the shore turns here; keep the row on the straight stretch
            dep = depth
            slip = None
            for _ in range(5):
                cand = _rect(q, axis, ws, 30.0, dep)
                land = cand.intersection(poly)
                if land.area > 0 and cand.intersection(allowed).area >= 0.97 * land.area and \
                        (taken.is_empty or cand.distance(taken) > 0.9 * wp):
                    slip = cand
                    break
                dep *= 0.8
            if slip is None or dep < 120:
                continue
            main = G.polygonal(slip.intersection(poly.union(q.buffer(35))))
            main = G.parts(main)[0] if G.parts(main) else None
            if main is None or main.area < 6000:
                continue
            taken = taken.union(main)
            line = LineString([(q.x, q.y), (q.x + axis[0] * dep, q.y + axis[1] * dep)])
            out.append(("harbor_basins", line, main))
            budget -= 1
    return out


def _marinas(d, poly, allowed, frontage, density, rng, avoid):
    """Rounded marina basins set just behind the shore, each opening onto the water through
    a short entrance channel."""
    fronts = [f for f in frontage if f.length >= 250]
    total = sum(f.length for f in fronts)
    n = int(np.clip(round(density * total / 1200.0), 1, 2))
    out = []
    taken = Polygon()
    for p in _entries(fronts, n, rng, avoid, min_len=250.0):
        f = min(fronts, key=lambda g: g.distance(p))
        q, t, nrm = _shore_frame(f, f.project(p), poly)
        for scale in (1.0, 0.8, 0.65):
            w = float(rng.uniform(170, 230)) * scale
            dep = float(rng.uniform(120, 160)) * scale
            c = Point(q.x + nrm[0] * (dep / 2 + 25), q.y + nrm[1] * (dep / 2 + 25))
            ell = affinity.scale(Point(0, 0).buffer(1.0, quad_segs=24), w / 2, dep / 2)
            ang = M.degrees(M.atan2(t[1], t[0]))
            ell = affinity.translate(affinity.rotate(ell, ang, origin=(0, 0)), c.x, c.y)
            mouth = _rect(q, nrm, 45.0 * scale, 30.0, 40.0)
            cand = unary_union([ell, mouth])
            land = cand.intersection(poly)
            if land.area > 0 and cand.intersection(allowed).area >= 0.95 * land.area and \
                    (taken.is_empty or cand.distance(taken) > 80):
                break
        else:
            continue
        main = G.polygonal(cand.intersection(poly.union(q.buffer(35))))
        main = G.parts(main)[0] if G.parts(main) else None
        if main is None or main.area < 6000:
            continue
        taken = taken.union(main)
        out.append(("marina", LineString([(q.x, q.y), (c.x, c.y)]), main))
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
        canals = _Net(70.0, 2)
        canals.shore = unary_union(frontage)
        for style in ww.style:
            if style == "canal_grid":
                # The map border is not a quay: a canal stopping there is a dead end.
                grid = _canal_grid(d, poly, allowed, density, rng,
                                   wet.difference(h.canvas.exterior.buffer(8.0)))
                cands += grid
                for _, line, _ in grid:
                    canals.add(line)
            elif style in ("organic_canals", "creeks"):
                cands += _organic(style, d, poly, allowed, frontage, density, rng, land_edge,
                                  canals)
            elif style == "inlets":
                cands += _inlets(d, poly, allowed, frontage, density, rng, land_edge)
            elif style == "marina":
                cands += _marinas(d, poly, allowed, wide_front, density, rng, land_edge)
            else:
                cands += _harbor(d, poly, allowed, wide_front, density, rng, land_edge)
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
    _pinned_pools(spec, h, district_ids, out)
    _quays(h, out)
    for w in out.items:  # stage boundary: hand on grid coordinates
        w.polygon = G.qpoly(w.polygon)
        w.centerline = G.qline(w.centerline)
    for qy in out.quays:
        qy.line = G.qline(qy.line)
    return out


def _pinned_pools(spec: CitySpec, h: H.Hydro, district_ids: dict[str, str],
                  out: Waterways) -> None:
    """The water pockets of a traced island (holes in its coast, polygons on its water layer):
    ornamental basins at sea level in the district on it."""
    from . import pinned as PN

    pins = PN.placed_islands(spec, h)
    for name in sorted(pins):
        pin, dist = pins[name]
        if dist is None or dist not in district_ids:
            continue
        did = district_ids[dist]
        polys = [Polygon(r) for r in pin.land.interiors] + \
            [a.polygon for a in pin.areas if a.kind == "water"]
        k0 = sum(1 for w in out.items if w.district == dist)
        for k, pg in enumerate(polys):
            out.items.append(WaterwayRec(f"{did}.ww{k0 + k + 1:02d}", "basin", "pinned", dist,
                                         None, G.qpoly(pg), None, None, ornamental=True))


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

