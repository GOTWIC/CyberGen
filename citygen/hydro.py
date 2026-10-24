"""Stage 1, coast and hydrology: sea, rivers, sea channels, delta branches, islands, landmasses.

Everything is built in meters on the canvas (origin at the city center). The sea comes from the
coast form, solved by bisection so it covers `sea_share` of the map. Rivers run from their entry
edge to their mouth along a straight base line displaced sideways by a bulge and fractal noise
(the meander); a sideways displacement of a straight line never crosses itself. Tributaries end
in their parent, delta branches split from the main channel and fan out along the coast, so the
land between channels becomes separate landmasses. Islands are smooth blobs of exact area:
offshore and nearshore islands in the sea, mid-river islands on the river with a ring of water
around them, delta islands are the land between two channels (the split point is bisected so
the wedge has the asked area).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points, substring, unary_union

from . import geom as G
from . import presets
from .defaults import derive_seed
from .spec import CitySpec

MIN_LAND_WIDTH_M = 40.0      # narrower land is a sliver and becomes water
MIN_LANDMASS_M2 = 50_000.0   # smaller pieces of land become water
COAST_SMOOTH_M = 40.0


@dataclass
class WaterBody:
    id: str
    kind: str  # river, sea_channel, delta_branch, separation
    name: str | None
    centerline: LineString
    widths: list[float]
    polygon: object
    mouth: str = "sea"            # sea, edge, river
    flows_into: str | None = None
    parent_id: str | None = None
    attrs: dict = field(default_factory=dict)


@dataclass
class IslandRec:
    name: str
    setting: str
    target_m2: float
    polygon: object
    filler: bool = False
    probe: tuple[float, float] | None = None  # for delta wedges: a point on the wedge's coast


@dataclass
class Hydro:
    canvas: Polygon
    sea: object
    bodies: list[WaterBody]
    islands: list[IslandRec]
    rings: object  # water around mid-river islands
    water: object = None
    land: object = None
    landmasses: list[Polygon] = field(default_factory=list)
    coastline: object = None
    notes: list[str] = field(default_factory=list)

    @property
    def coastal(self):
        """Sea plus sea channels: the water that counts as coast."""
        ch = [b.polygon for b in self.bodies if b.kind == "sea_channel"]
        return unary_union([self.sea, *ch]) if ch else self.sea

    def body(self, ident: str) -> WaterBody | None:
        return next((b for b in self.bodies if b.id == ident), None)

    def by_name(self, name: str) -> list[WaterBody]:
        """The river or channel with this name plus its delta branches."""
        main = [b for b in self.bodies if b.name == name and b.kind in ("river", "sea_channel")]
        ids = {b.id for b in main}
        return main + [b for b in self.bodies if b.parent_id in ids]


@dataclass
class Variant:
    """Free hydrology parameters the build may vary to fit the districts (index 0 = default)."""
    index: int = 0
    at_shift: dict[str, float] = field(default_factory=dict)
    bulge: dict[str, float] = field(default_factory=dict)
    split: dict[str, float] = field(default_factory=dict)
    spread: dict[str, float] = field(default_factory=dict)

    @classmethod
    def make(cls, spec: CitySpec, index: int) -> Variant:
        v = cls(index=index)
        if index == 0:
            return v
        rng = np.random.default_rng(derive_seed(spec.seed, "hydro.variant", index))
        # The first variants step the entry point and the bulge both ways; later ones mix.
        steps = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]
        for j, r in enumerate(spec.water.rivers):
            if index <= len(steps) and j == 0:
                a, b = steps[index - 1]
                v.at_shift[r.name] = 0.2 * a
                v.bulge[r.name] = 0.12 * b
            else:
                v.at_shift[r.name] = float(rng.uniform(-0.25, 0.25))
                v.bulge[r.name] = float(rng.uniform(-0.15, 0.15))
            v.split[r.name] = float(rng.uniform(-0.25, 0.2))
            v.spread[r.name] = float(rng.uniform(-0.3, 0.6))
        return v


# ---------------------------------------------------------------------------
# Coast
# ---------------------------------------------------------------------------

def _gauss(x):
    return np.exp(-x * x)


def _sea_canonical(form: str, s: float, A: float, Bh: float, noise, b0: float) -> Polygon:
    """Sea {a > c(b)} in the frame a = toward the sea, b = along the coast."""
    span = 2 * A
    bs = np.arange(-1.6 * Bh, 1.6 * Bh + 10, 10.0)
    n = noise(bs)
    if form == "peninsula":
        raise ValueError("peninsula is built by _peninsula")
    if form == "bay":
        c = A - s * span * (0.3 + 0.3 * np.exp(-(bs / (0.55 * Bh)) ** 4))
    elif form == "crescent":
        c = A - s * span * (0.12 + 0.6 * np.clip(1 - (bs / (1.05 * Bh)) ** 2, 0, 1))
    elif form == "delta":
        c = A - s * span * (0.55 - 0.32 * _gauss((bs - b0) / (0.38 * Bh)))
    else:  # straight, archipelago
        c = A - s * span * 0.5
    c = c + n
    pts = list(zip(c, bs)) + [(4 * A, bs[-1]), (4 * A, bs[0])]
    return Polygon(pts)


def _peninsula(w0: float, neck_frac: float, A: float, Bh: float, noise, noise2) -> object:
    span = 2 * A
    a_n = A - neck_frac * span
    bs = np.arange(-1.6 * Bh, 1.6 * Bh + 10, 10.0)
    band = Polygon(list(zip(a_n + noise(bs), bs)) + [(4 * A, bs[-1]), (4 * A, bs[0])])
    a_tip = A - 0.07 * span
    a_s = np.arange(a_n - 80, a_tip + 1, 10.0)
    t = np.clip((a_s - a_n) / (a_tip - a_n), 0, 1)
    w = w0 * (1 - 0.3 * t)
    tip = t > 0.8
    w[tip] *= np.sqrt(np.clip(1 - ((t[tip] - 0.8) / 0.2) ** 2, 0, 1))
    left = np.column_stack([a_s, w + 0.6 * noise2(a_s)])
    right = np.column_stack([a_s, -w + 0.6 * noise2(a_s + 9000)])
    tongue = shapely.make_valid(Polygon(np.vstack([left, right[::-1]])))
    return band.difference(tongue)


def build_sea(spec: CitySpec, canvas: Polygon, b0_world: tuple[float, float] | None) -> object:
    coast = spec.water.coast
    ux, uy, vx, vy = G.frame(coast.side)
    corners = list(canvas.exterior.coords)[:4]
    A = max(x * ux + y * uy for x, y in corners)
    Bh = max(abs(x * vx + y * vy) for x, y in corners)
    rng = np.random.default_rng(derive_seed(spec.seed, "hydro.coast"))
    amp = min(max(0.022 * 2 * A, 30.0), 90.0)
    base = G.noise1d(rng, 700.0)
    noise = lambda b: amp * base(b)  # noqa: E731
    base2 = G.noise1d(rng, 500.0)
    noise2 = lambda a: amp * base2(a)  # noqa: E731
    b0 = 0.0
    if b0_world is not None:
        b0 = float(np.clip(b0_world[0] * vx + b0_world[1] * vy, -0.5 * Bh, 0.5 * Bh))
    target = coast.sea_share * canvas.area
    to_world = [ux, vx, uy, vy, 0, 0]

    def sea_for(param: float, neck: float = 0.0):
        if coast.form == "peninsula":
            g = _peninsula(param, neck, A, Bh, noise, noise2)
        else:
            g = _sea_canonical(coast.form, param, A, Bh, noise, b0)
        g = affinity.affine_transform(g, to_world)
        g = g.buffer(COAST_SMOOTH_M).buffer(-2 * COAST_SMOOTH_M).buffer(COAST_SMOOTH_M)
        return G.polygonal(g.intersection(canvas))

    if coast.form == "peninsula":
        neck = min(max(coast.sea_share + 0.22, 0.4), 0.85)
        lo, hi = 0.0, 1.2 * Bh  # tongue half-width: wider tongue, less sea
        for _ in range(26):
            mid = (lo + hi) / 2
            if sea_for(mid, neck).area > target:
                lo = mid
            else:
                hi = mid
        return sea_for((lo + hi) / 2, neck)
    lo, hi = 0.0, 2.0
    for _ in range(26):
        mid = (lo + hi) / 2
        if sea_for(mid).area < target:
            lo = mid
        else:
            hi = mid
    return sea_for((lo + hi) / 2)


def coastline_of(sea, canvas: Polygon):
    """Sea boundary minus the map edge, as (Multi)LineString."""
    if sea.is_empty:
        return LineString()
    edge = canvas.exterior.buffer(0.5)
    return sea.boundary.difference(edge)


def _lines(g) -> list[LineString]:
    if g.is_empty:
        return []
    if isinstance(g, LineString):
        return [g]
    out = [x for x in getattr(g, "geoms", []) if isinstance(x, LineString)]
    out += [y for x in getattr(g, "geoms", []) if isinstance(x, MultiLineString) for y in x.geoms]
    return out


def main_coast(coastline, near: Point) -> LineString | None:
    merged = shapely.line_merge(coastline) if not coastline.is_empty else coastline
    ls = _lines(merged)
    if not ls:
        return None
    return min(ls, key=lambda line: (line.distance(near), -line.length))


# ---------------------------------------------------------------------------
# Rivers
# ---------------------------------------------------------------------------

def _order_rivers(rivers):
    names = {r.name for r in rivers}
    done: list = []
    pending = list(rivers)
    while pending:
        for r in list(pending):
            if r.to not in names or r.to in {d.name for d in done}:
                done.append(r)
                pending.remove(r)
                break
        else:
            done += pending
            break
    return done


def _trim_at(line: LineString, region, extra: float, skip: float = 0.0) -> tuple[LineString, bool]:
    """Cut `line` where it first enters `region` (after `skip` meters), plus `extra` meters."""
    pts = G.resample(line, 8.0)
    ds = np.linspace(0, line.length, len(pts))
    inside = shapely.contains_xy(region, pts[:, 0], pts[:, 1]) & (ds > skip)
    if not inside.any():
        return line, False
    d = float(ds[int(np.argmax(inside))]) + extra
    return substring(line, 0, min(d, line.length)), True


def _first_sea_hit(start, aim, sea, coast) -> tuple[float, float]:
    seg = LineString([start, aim])
    hit = seg.intersection(sea)
    if hit.is_empty:
        return nearest_points(coast, Point(aim))[0].coords[0]
    q = nearest_points(hit, Point(start))[0]
    return (q.x, q.y)


def _offset_fn(rng, length: float, meander: float, width: float, bulge: float):
    lam = min(max(12 * width, 600.0), 1500.0)
    amp = meander * 0.6 * lam
    nz = G.noise1d(rng, lam, octaves=2, persistence=0.35)

    def f(ts):
        ts = np.asarray(ts)
        ramp = np.clip(np.minimum(ts, 1 - ts) * 6, 0, 1)
        return bulge * length * np.sin(math.pi * ts) + amp * nz(ts * length) * ramp

    return f


def _keep_inside(make, canvas: Polygon, margin: float) -> LineString:
    """Build the path; damp the sideways displacement until it stays on the map."""
    inner = canvas.buffer(-margin)
    scale = 1.0
    line = make(scale)
    for _ in range(8):
        pts = G.resample(line, 25.0)
        mid = pts[2:-2] if len(pts) > 6 else pts
        if shapely.contains_xy(inner, mid[:, 0], mid[:, 1]).all():
            return line
        scale *= 0.7
        line = make(scale)
    return line


def build_rivers(spec: CitySpec, canvas: Polygon, sea, variant: Variant) -> list[WaterBody]:
    w = spec.water
    coast = coastline_of(sea, canvas)
    ux, uy, vx, vy = G.frame(w.coast.side)
    corners = list(canvas.exterior.coords)[:4]
    A = max(x * ux + y * uy for x, y in corners)
    Bh = max(abs(x * vx + y * vy) for x, y in corners)
    span = max(canvas.bounds[2] - canvas.bounds[0], canvas.bounds[3] - canvas.bounds[1])
    bodies: list[WaterBody] = []
    by_name: dict[str, WaterBody] = {}
    same_edge: dict[str, list[str]] = {}
    for r in w.rivers:
        if r.from_at is None:
            same_edge.setdefault(r.from_, []).append(r.name)
    order = _order_rivers(w.rivers)
    for k, r in enumerate(order):
        idx = w.rivers.index(r) + 1
        rid = f"r{idx:02d}" if r.kind == "river" else f"ch{idx:02d}"
        rng = np.random.default_rng(derive_seed(spec.seed, "hydro.river", r.name))
        wmin, wmax = r.width_m
        wmean = (wmin + wmax) / 2
        if r.from_at is not None:
            at = r.from_at
        else:
            group = same_edge[r.from_]
            base = 0.5 if "_" not in r.from_ else 0.3  # diagonal: beside the corner, not in it
            at = base + (group.index(r.name) - (len(group) - 1) / 2) * 0.28
            at = min(max(at + variant.at_shift.get(r.name, 0.0), 0.12), 0.88)
        start = G.edge_point(canvas, r.from_, at)
        if r.from_at is None:
            start = _onto_land(canvas, sea, r.from_, at)
        inward = G.edge_tangent_inward(canvas, start)
        s_out = (start[0] - inward[0] * wmax, start[1] - inward[1] * wmax)
        parent = by_name.get(r.to)
        mouth_kind = "sea"
        flows_into = "sea"
        if parent is not None:
            pl = parent.centerline
            # Head for the map center from the entry point and join where that meets the
            # parent, so tributaries cross the land instead of hugging the parent or an edge.
            cx, cy = -presets.DIRECTION_VECTORS[r.from_][0], -presets.DIRECTION_VECTORS[r.from_][1]
            aim = Point(start[0] + cx * 0.6 * span, start[1] + cy * 0.6 * span)
            t = min(max(pl.project(aim, normalized=True), 0.35), 0.85)
            end = pl.interpolate(t, normalized=True).coords[0]
            mouth_kind, flows_into = "river", parent.id
        elif r.to in presets.DIRECTIONS or sea.is_empty or coast.is_empty:
            edge = r.to if r.to in presets.DIRECTIONS else presets.opposite(r.from_)
            e = (G.edge_point(canvas, edge, r.to_at) if r.to_at is not None
                 else _onto_land(canvas, sea, edge, 0.5))
            out = G.edge_tangent_inward(canvas, e)
            end = (e[0] - out[0] * wmax, e[1] - out[1] * wmax)
            mouth_kind, flows_into = "edge", None
        else:
            if r.to_at is not None:
                aim = G.edge_point(canvas, w.coast.side, r.to_at)
                m = nearest_points(coast, Point(aim))[0].coords[0]
            elif r.to == "bay" and w.coast.form in ("bay", "crescent"):
                m = _bay_head(coast, ux, uy, vx, vy, Bh)
            else:
                aim = (start[0] + ux * 2 * A * 1.2, start[1] + uy * 2 * A * 1.2)
                m = _first_sea_hit(start, aim, sea, coast)
            end = (m[0] + ux * wmax * 2.5, m[1] + uy * wmax * 2.5)
        length = math.hypot(end[0] - s_out[0], end[1] - s_out[1])
        off = _offset_fn(rng, length, r.meander, wmean, variant.bulge.get(r.name, 0.0))

        def make(scale, a=s_out, b=end, f=off):
            return G.wiggle_path(a, b, lambda ts: scale * f(ts))

        line = _keep_inside(make, canvas, wmax)
        if mouth_kind == "sea":
            line, _ = _trim_at(line, sea, 2.0 * wmax, skip=wmax * 3)
        elif mouth_kind == "river":
            line, _ = _trim_at(line, parent.polygon, 0.6 * wmax, skip=wmax * 3)
        widths_fn = lambda ts, a=wmin, b=wmax: a + (b - a) * np.asarray(ts)  # noqa: E731
        poly = G.polygonal(G.variable_buffer(line, widths_fn).intersection(canvas))
        n = len(line.coords)
        widths = [float(round(wmin + (wmax - wmin) * i / max(n - 1, 1), 1)) for i in range(n)]
        body = WaterBody(rid, "river" if r.kind == "river" else "sea_channel", r.name, line,
                         widths, poly, mouth_kind, flows_into)
        bodies.append(body)
        by_name[r.name] = body
        if r.delta_branches and mouth_kind == "sea":
            bodies += _delta_branches(spec, r, body, sea, coast, span, variant, rng)
    return bodies


def _onto_land(canvas: Polygon, sea, edge: str, at: float) -> tuple[float, float]:
    """Point at `at` along the land part of an edge (the longest run of the edge that stays
    at least 150 m from the sea); the plain edge point when the whole edge is land."""
    ks = np.linspace(0, 1, 201)
    pts = [G.edge_point(canvas, edge, float(k)) for k in ks]
    if sea.is_empty:
        return G.edge_point(canvas, edge, at)
    dry = [sea.distance(Point(p)) >= 150 for p in pts]
    if all(dry) or not any(dry):
        return G.edge_point(canvas, edge, at)
    runs, start = [], None
    for i, ok in enumerate(dry + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            runs.append((i - 1 - start, start, i - 1))
            start = None
    _, i0, i1 = max(runs)
    k = ks[i0] + (ks[i1] - ks[i0]) * min(max(at, 0.0), 1.0)
    return G.edge_point(canvas, edge, float(k))


def _bay_head(coast, ux, uy, vx, vy, Bh) -> tuple[float, float]:
    """Most inland coast point near the middle of the bay."""
    best, best_a = None, None
    for line in _lines(coast):
        for x, y in G.resample(line, 20.0):
            b = x * vx + y * vy
            if abs(b) > 0.5 * Bh:
                continue
            a = x * ux + y * uy
            if best_a is None or a < best_a:
                best, best_a = (float(x), float(y)), a
    if best is None:
        line = max(_lines(coast), key=lambda g: g.length)
        q = line.interpolate(0.5, normalized=True)
        best = (q.x, q.y)
    return best


def _delta_branches(spec, r, main: WaterBody, sea, coast, span, variant, rng) -> list[WaterBody]:
    ux, uy, _, _ = G.frame(spec.water.coast.side)
    mouth = Point(main.centerline.coords[-1])
    cl = main_coast(coast, mouth)
    if cl is None:
        return []
    s0 = cl.project(mouth)
    t_split = 0.62 + variant.split.get(r.name, 0.0)
    split_dist = main.centerline.length * (1 - t_split)
    spacing = min(max(0.13 * span, 0.5 * split_dist, 300.0), 1000.0)
    wmin, wmax = r.width_m
    t_base = 0.62 + variant.split.get(r.name, 0.0)
    spacing *= 1.0 + variant.spread.get(r.name, 0.0)
    land_len = main.centerline.length
    out = []
    names = list(r.branch_names)
    for j in range(r.delta_branches):
        side = 1 if j % 2 == 0 else -1
        rank = j // 2 + 1
        s = s0 + side * rank * spacing
        s = min(max(s, 0.08 * cl.length), 0.92 * cl.length)
        q = cl.interpolate(s).coords[0]
        t = max(t_base - 0.07 * (rank - 1), 0.25)
        bw = max(0.55 * (wmin + (wmax - wmin) * t), 24.0)
        out.append(_branch(spec, main, j, side, rank, t, q, bw, sea, ux, uy, rng,
                           names[j] if j < len(names) else None, land_len))
    return out


def _branch(spec, main, j, side, rank, t, q, bw, sea, ux, uy, rng, name, land_len,
            ) -> WaterBody:
    p = main.centerline.interpolate(t * land_len).coords[0]
    end = (q[0] + ux * bw * 2.5, q[1] + uy * bw * 2.5)
    length = math.hypot(end[0] - p[0], end[1] - p[1])
    meander = spec.water.rivers[[x.name for x in spec.water.rivers].index(main.name)].meander
    brng = np.random.default_rng(derive_seed(spec.seed, "hydro.branch", main.name, j))
    off = _offset_fn(brng, length, 0.5 * meander, bw, 0.0)
    line = G.wiggle_path(p, end, off)
    line, _ = _trim_at(line, sea, 2.0 * bw, skip=bw * 2)
    poly = G.variable_buffer(line, lambda ts: bw * (0.9 + 0.2 * np.asarray(ts)))
    n = len(line.coords)
    widths = [float(round(bw * (0.9 + 0.2 * i / max(n - 1, 1)), 1)) for i in range(n)]
    return WaterBody(f"{main.id}.b{j + 1}", "delta_branch", name, line, widths, poly, "sea",
                     "sea", parent_id=main.id,
                     attrs={"side": side, "rank": rank, "split_t": round(t, 4),
                            "coast_target": (round(q[0], 2), round(q[1], 2))})


def _rebranch(spec, b: WaterBody, main: WaterBody, t: float, sea, q=None) -> WaterBody:
    ux, uy, _, _ = G.frame(spec.water.coast.side)
    q = q or b.attrs["coast_target"]
    bw = b.widths[0] / 0.9
    j = int(b.id.rsplit(".b", 1)[1]) - 1
    return _branch(spec, main, j, b.attrs["side"], b.attrs["rank"], t, q, bw, sea, ux, uy,
                   None, b.name, main.centerline.length)


# ---------------------------------------------------------------------------
# Islands
# ---------------------------------------------------------------------------

def _aim(canvas: Polygon, position: str, frac: float, sea_side: str) -> Point:
    if position == "center":
        ux, uy = presets.DIRECTION_VECTORS[sea_side]
        d = position_reach(canvas, sea_side)
        return Point(ux * d * frac * 0.8, uy * d * frac * 0.8)
    ux, uy = presets.DIRECTION_VECTORS[position]
    d = position_reach(canvas, position)
    return Point(ux * d * frac, uy * d * frac)


def position_reach(canvas: Polygon, direction: str) -> float:
    """Distance from the center to the map edge along `direction`."""
    ux, uy = presets.DIRECTION_VECTORS[direction]
    minx, miny, maxx, maxy = canvas.bounds
    tx = maxx / abs(ux) if abs(ux) > 1e-9 else math.inf
    ty = maxy / abs(uy) if abs(uy) > 1e-9 else math.inf
    return min(tx, ty)


def _fit_blob(free, aim: Point, area: float, rng, elong: float, gap: float, canvas: Polygon,
              beyond) -> Polygon | None:
    """Island blob nearest to `aim` that stays `gap` meters clear of everything but `free`."""
    shapes = [G.blob((0.0, 0.0), area, np.random.default_rng(rng.integers(1 << 31)), elong, ang)
              for ang in (0.0, math.pi / 4, math.pi / 2, 3 * math.pi / 4)]
    rmin = min(math.sqrt(area / math.pi) * 0.8, min(
        Point(0, 0).distance(sh.exterior) for sh in shapes))
    room = free.union(beyond).buffer(-gap)
    region = room.buffer(-rmin).intersection(canvas.buffer(-rmin))
    if region.is_empty:
        return None
    minx, miny, maxx, maxy = region.bounds
    step = max(25.0, math.sqrt(area) / 12)
    xs = np.arange(minx, maxx + step, step)
    ys = np.arange(miny, maxy + step, step)
    gx, gy = np.meshgrid(xs, ys)
    gx, gy = gx.ravel(), gy.ravel()
    ok = shapely.contains_xy(region, gx, gy)
    gx, gy = gx[ok], gy[ok]
    if not len(gx):
        return None
    order = np.argsort(np.hypot(gx - aim.x, gy - aim.y), kind="stable")
    fits = room.intersection(canvas)
    shapely.prepare(fits)
    for i in order[:4000]:
        for sh in shapes:
            cand = affinity.translate(sh, float(gx[i]), float(gy[i]))
            if fits.contains(cand):
                return cand
    return None


def _sea_aim(canvas: Polygon, sea, position: str, frac: float) -> Point:
    """Aim point for a sea island: from the middle of the sea toward `position`."""
    c = sea.representative_point() if not sea.contains(sea.centroid) else sea.centroid
    if position == "center":
        return c
    ux, uy = presets.DIRECTION_VECTORS[position]
    minx, miny, maxx, maxy = canvas.bounds
    tx = ((maxx if ux > 0 else minx) - c.x) / ux if abs(ux) > 1e-9 else math.inf
    ty = ((maxy if uy > 0 else miny) - c.y) / uy if abs(uy) > 1e-9 else math.inf
    d = min(tx, ty)
    return Point(c.x + ux * d * frac, c.y + uy * d * frac)


def place_sea_islands(spec: CitySpec, canvas: Polygon, sea, bodies: list[WaterBody],
                      notes: list[str]) -> list[IslandRec]:
    out: list[IslandRec] = []
    todo = [i for i in spec.water.islands if i.setting in ("offshore", "nearshore")]
    fillers = []
    if spec.water.coast.form == "archipelago" and len(todo) < 3:
        rng = np.random.default_rng(derive_seed(spec.seed, "hydro.fillers"))
        for k in range(3 - len(todo)):
            fillers.append((f"Islet {chr(65 + k)}", float(rng.uniform(0.08, 0.2)),
                            presets.DIRECTIONS[int(rng.integers(0, 8))]))
    river_keepout = unary_union([b.polygon.buffer(100) for b in bodies]) if bodies else Polygon()
    beyond = canvas.buffer(4000, join_style="mitre").difference(canvas)
    taken = Polygon()
    jobs = [(i.name, i.area_km2 * 1e6, i.position, i.setting, False) for i in todo]
    jobs += [(n, a * 1e6, p, "offshore", True) for n, a, p in fillers]
    jobs.sort(key=lambda j: -j[1])
    for name, area, position, setting, filler in jobs:
        rng = np.random.default_rng(derive_seed(spec.seed, "hydro.island", name))
        elong = float(rng.uniform(1.0, 1.25))
        free = sea.difference(river_keepout).difference(taken)
        aim = _sea_aim(canvas, sea, position, 0.5 if setting == "nearshore" else 0.7)
        poly = None
        gaps = [60.0, 45.0, 30.0] if setting == "nearshore" else [220.0, 150.0, 100.0, 70.0]
        for gap in gaps:
            poly = _fit_blob(free, aim, area, rng, elong, gap, canvas, beyond)
            if poly is not None:
                break
        if poly is None:
            notes.append(f"island '{name}' does not fit in the sea; raise sea_share or shrink it")
            continue
        taken = taken.union(poly.buffer(60))
        out.append(IslandRec(name, setting, area, poly, filler=filler))
    return out


def place_river_islands(spec: CitySpec, canvas: Polygon, bodies: list[WaterBody],
                        notes: list[str]) -> tuple[list[IslandRec], object]:
    out, rings = [], []
    for isl in spec.water.islands:
        if isl.setting != "mid_river":
            continue
        body = next((b for b in bodies if b.name == isl.river and b.kind != "delta_branch"),
                    None)
        if body is None:
            notes.append(f"island '{isl.name}': river '{isl.river}' was not built")
            continue
        rng = np.random.default_rng(derive_seed(spec.seed, "hydro.island", isl.name))
        line = body.centerline
        area = isl.area_km2 * 1e6
        half = 1.35 * math.sqrt(area / math.pi) * 1.15
        split = min([b.attrs.get("split_t", 1.0) for b in bodies if b.parent_id == body.id],
                    default=1.0) * line.length
        lo = min(half + 150, line.length * 0.4)
        hi = max(min(split - half - 200, line.length - half - 150), lo)
        if isl.position == "center":
            d = line.project(Point(0, 0))
        else:
            d = line.project(_aim(canvas, isl.position, 0.5, spec.water.coast.side))
        d = min(max(d, lo), hi)
        c = line.interpolate(d)
        a = line.interpolate(max(d - 60, 0))
        b = line.interpolate(min(d + 60, line.length))
        angle = math.atan2(b.y - a.y, b.x - a.x)
        poly = G.blob((c.x, c.y), area, rng, 1.35, angle)
        i = min(int(d / line.length * (len(body.widths) - 1)), len(body.widths) - 1)
        arm = max(0.6 * body.widths[i], 30.0)
        rings.append(poly.buffer(arm))
        out.append(IslandRec(isl.name, "mid_river", area, poly))
    return out, unary_union(rings) if rings else Polygon()


def _wedge(canvas, sea, bodies, rings, probe: Point):
    water = unary_union([sea, rings] + [b.polygon for b in bodies])
    land = G.polygonal(canvas.difference(water))
    ps = G.parts(land)
    if not ps:
        return Polygon()
    return min(ps, key=lambda p: (p.distance(probe), -p.area))


def solve_delta_islands(spec: CitySpec, canvas: Polygon, sea, bodies: list[WaterBody],
                        rings, notes: list[str]) -> list[IslandRec]:
    out = []
    coast = coastline_of(sea, canvas)
    used: dict[tuple[str, int], int] = {}
    for isl in spec.water.islands:
        if isl.setting != "delta":
            continue
        main = next((b for b in bodies if b.name == isl.river and b.kind != "delta_branch"),
                    None)
        branches = [b for b in bodies if main is not None and b.parent_id == main.id]
        if not branches:
            notes.append(f"delta island '{isl.name}': river '{isl.river}' has no delta branches")
            continue
        aim = _aim(canvas, isl.position, 0.5, spec.water.coast.side)
        mouth = Point(main.centerline.coords[-1])
        choices = []
        for side in (1, -1):
            rank = used.get((main.id, side), 0) + 1
            b = next((x for x in branches if x.attrs["side"] == side and x.attrs["rank"] == rank),
                     None)
            if b is None:
                continue
            prev = mouth if rank == 1 else Point(next(
                x for x in branches if x.attrs["side"] == side and x.attrs["rank"] == rank - 1
            ).centerline.coords[-1])
            mid = LineString([prev, Point(b.centerline.coords[-1])]).interpolate(0.5,
                                                                                normalized=True)
            choices.append((mid.distance(aim), side, rank, b, prev))
        if not choices:
            notes.append(f"delta island '{isl.name}': no free wedge between channels")
            continue
        _, side, rank, b, prev = min(choices, key=lambda c: (c[0], -c[1]))
        used[(main.id, side)] = rank
        cl = main_coast(coast, mouth)
        s_a = cl.project(prev)
        s_b0 = cl.project(Point(b.attrs["coast_target"]))
        target = isl.area_km2 * 1e6
        t_hi = 0.92 if rank == 1 else next(
            x for x in branches if x.attrs["side"] == side and x.attrs["rank"] == rank - 1
        ).attrs["split_t"] - 0.03
        # Keep upstream of mid-river islands (their rings) on this river.
        ring_d = [main.centerline.project(Point(c.coords[0])) / main.centerline.length
                  for c in ([rings.centroid] if not rings.is_empty else [])]
        t_lo = max([0.2] + [d + 0.15 for d in ring_d if d < t_hi])
        t_lo = min(t_lo, t_hi - 0.05)
        k = bodies.index(b)
        sign = 1 if s_b0 >= s_a else -1
        gap0 = abs(s_b0 - s_a)
        best = None

        def trial_for(p: float):
            """p in [0, 1]: 0 = small wedge, 1 = split far upstream and a wide fan."""
            t = t_hi - (t_hi - t_lo) * p
            g = gap0 * (0.6 + 2.2 * p)
            sb = min(max(s_a + sign * g, 0.04 * cl.length), 0.96 * cl.length)
            q = cl.interpolate(sb).coords[0]
            nb = _rebranch(spec, b, main, t, sea, q)
            probe = cl.interpolate((s_a + sb) / 2)
            trial = bodies[:k] + [nb] + bodies[k + 1:]
            return _wedge(canvas, sea, trial, rings, probe).area, nb, probe

        lo, hi = 0.0, 1.0
        for _ in range(16):
            mid = (lo + hi) / 2
            area, nb, probe = trial_for(mid)
            if best is None or abs(area - target) < abs(best[0] - target):
                best = (area, nb, probe)
            if area > target:
                hi = mid
            else:
                lo = mid
        bodies[k] = best[1]
        probe = best[2]
        out.append(IslandRec(isl.name, "delta", target, None, probe=(probe.x, probe.y)))
    return out


# ---------------------------------------------------------------------------
# Land
# ---------------------------------------------------------------------------

def rebuild_land(h: Hydro) -> None:
    """water = sea + every water body + island rings - islands; land = map - water."""
    sea_isl = [i.polygon for i in h.islands if i.setting in ("offshore", "nearshore")]
    river_isl = [i.polygon for i in h.islands if i.setting == "mid_river"]
    sea = h.sea.difference(unary_union(sea_isl)) if sea_isl else h.sea
    water = unary_union([sea, h.rings] + [b.polygon for b in h.bodies])
    if river_isl:
        water = water.difference(unary_union(river_isl))
    water = G.polygonal(water.intersection(h.canvas))
    land = G.polygonal(h.canvas.difference(water))
    land = G.opening(land, MIN_LAND_WIDTH_M / 2)
    land = G.drop_small(land, MIN_LANDMASS_M2)
    land = G.clean(land)
    h.land = land
    h.water = G.clean(G.polygonal(h.canvas.difference(land)))
    h.landmasses = G.parts(land)
    ch = [b.polygon for b in h.bodies if b.kind == "sea_channel"]
    h.coastline = coastline_of(unary_union([sea, *ch]) if ch else sea, h.canvas)
    # Island polygons follow the final land.
    for isl in h.islands:
        ref = isl.polygon if isl.polygon is not None else Point(isl.probe).buffer(5)
        best = max(h.landmasses, key=lambda p: (p.intersection(ref).area, -p.distance(ref)),
                   default=None)
        if best is not None and (best.intersection(ref).area > 0 or isl.polygon is None):
            isl.polygon = best


def build_hydro(spec: CitySpec, canvas: Polygon, variant: Variant) -> Hydro:
    w = spec.water
    notes: list[str] = []
    b0 = None
    first_sea = next((r for r in w.rivers if r.to in ("sea", "bay")), None)
    if w.coast.form == "delta" and first_sea is not None:
        at = first_sea.to_at
        b0 = (G.edge_point(canvas, w.coast.side, at) if at is not None
              else G.edge_point(canvas, first_sea.from_, first_sea.from_at))
    sea = build_sea(spec, canvas, b0)
    bodies = build_rivers(spec, canvas, sea, variant)
    river_isl, rings = place_river_islands(spec, canvas, bodies, notes)
    delta_isl = solve_delta_islands(spec, canvas, sea, bodies, rings, notes)
    sea_isl = place_sea_islands(spec, canvas, sea, bodies, notes)
    h = Hydro(canvas, sea, bodies, sea_isl + river_isl + delta_isl, rings, notes=notes)
    # Keep the spec order for islands (fillers last).
    order = {i.name: k for k, i in enumerate(w.islands)}
    h.islands.sort(key=lambda i: (i.filler, order.get(i.name, 99), i.name))
    rebuild_land(h)
    return h
