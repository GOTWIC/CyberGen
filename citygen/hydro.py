"""Stage 1, coast and hydrology: sea, rivers, sea channels, delta branches, islands, landmasses.

Everything is built in meters on the canvas (origin at the city center). The sea comes from the
coast form, solved by bisection so it covers `sea_share` of the map; a river with a delta
builds a lobe of land into the sea, so it ends at the coast, not at the map center. Rivers run
from their entry edge to their mouth as sine-generated curves (meanders of varying size and
spacing, about 11 widths apart) that widen downstream. Tributaries join their parent downstream
of their entry at 45 degrees to its flow (or where `to.at` pins it). Deltas split well inland:
curved distributaries fan out to mouths spread along the coast, the main channel narrowing
below the split, so the land between channels becomes separate landmasses. Islands are smooth
blobs of exact area: offshore and nearshore islands in the sea (inside their bearing sector
when there is room), mid-river islands on the river with a ring of water around them upstream
of the delta, delta islands are the land between two channels (the delta is scaled by
bisection so that land has the asked area).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points, substring, unary_union

from . import dmath as M
from . import trace as T
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
    return M.exp(-x * x)


def _sea_canonical(form: str, s: float, A: float, Bh: float, noise, b0: float,
                   lobe: float = 0.0) -> Polygon:
    """Sea {a > c(b)} in the frame a = toward the sea, b = along the coast. `lobe` (fraction
    of the span) pushes the coast seaward around b0: the land a delta builds into the sea."""
    span = 2 * A
    bs = np.arange(-1.6 * Bh, 1.6 * Bh + 10, 10.0)
    n = noise(bs)
    if form == "peninsula":
        raise ValueError("peninsula is built by _peninsula")
    if form == "bay":
        c = A - s * span * (0.3 + 0.3 * M.exp(-np.square(np.square(bs / (0.55 * Bh)))))
    elif form == "crescent":
        c = A - s * span * (0.12 + 0.6 * np.clip(1 - (bs / (1.05 * Bh)) ** 2, 0, 1))
    elif form == "delta":
        c = A - s * span * (0.6 - 0.42 * _gauss((bs - b0) / (0.6 * Bh)))
    else:  # straight, archipelago
        c = A - s * span * 0.5
    c = c + n + lobe * span * M.exp(-((bs - b0) / (0.3 * Bh)) ** 2)
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


def build_sea(spec: CitySpec, canvas: Polygon, b0_world: tuple[float, float] | None,
              lobe: float = 0.0) -> object:
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
            g = _sea_canonical(coast.form, param, A, Bh, noise, b0, lobe)
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
    edge = G.qpoly(canvas.exterior.buffer(0.5))
    return G.snap(sea.boundary.difference(edge))


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


def _meander_params(width: float, meander: float) -> tuple[float, float]:
    """(wavelength m, peak deflection rad): bends about 11 widths apart, as in real rivers."""
    lam = min(max(11.0 * width, 520.0), 1400.0)
    return lam, 0.25 + 1.4 * meander


def _width_fn(wmin: float, wmax: float, rng):
    """Width along the course: gradual widening downstream with a little slow variation."""
    nz = G.noise1d(rng, 0.3, octaves=1)

    def f(ts):
        ts = np.asarray(ts, dtype=float)
        return (wmin + (wmax - wmin) * M.power(ts, 1.3)) * (1 + 0.07 * nz(ts))

    return f


def _widths_at(line: LineString, fn) -> list[float]:
    cs = np.asarray(line.coords)
    d = np.concatenate([[0.0], np.cumsum(M.hypot(*np.diff(cs, axis=0).T))])
    return [float(round(w, 1)) for w in fn(d / (d[-1] or 1.0))]


def _keep_inside(make, canvas: Polygon, margin: float) -> LineString:
    """Build the path; damp the meander until it stays on the map."""
    inner = canvas.buffer(-margin)
    scale = 1.0
    line = make(scale)
    for _ in range(8):
        pts = G.resample(line, 25.0)
        k = int(math.ceil(2.5 * margin / 25.0)) + 1  # the ends sit on or past the map edge
        mid = pts[k:-k] if len(pts) > 2 * k + 2 else pts[len(pts) // 2:len(pts) // 2 + 1]
        if shapely.contains_xy(inner, mid[:, 0], mid[:, 1]).all():
            return line
        scale *= 0.7
        line = make(scale)
    return line


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(M.hypot(*v))
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def _rot(v, ang: float) -> np.ndarray:
    c, s = M.cos(ang), M.sin(ang)
    return np.array([v[0] * c - v[1] * s, v[0] * s + v[1] * c])


def _tangent(line: LineString, d: float) -> np.ndarray:
    a = line.interpolate(max(d - 25.0, 0.0))
    b = line.interpolate(min(d + 25.0, line.length))
    return _unit((b.x - a.x, b.y - a.y))


def width_at(body: WaterBody, d: float) -> float:
    """Width of a water body `d` meters along its centerline."""
    cs = np.asarray(body.centerline.coords)
    cum = np.concatenate([[0.0], np.cumsum(M.hypot(*np.diff(cs, axis=0).T))])
    return float(np.interp(d, cum, body.widths[:len(cum)]))


def lobe_mouth(canvas: Polygon, sea, side: str, b0: float) -> tuple[float, float]:
    """Coast point at the tip of a delta lobe centered at b0 (along-coast coordinate)."""
    ux, uy, vx, vy = G.frame(side)
    corners = list(canvas.exterior.coords)[:4]
    A = max(x * ux + y * uy for x, y in corners)
    inland = (vx * b0 - ux * A, vy * b0 - uy * A)
    seaward = (vx * b0 + ux * 2 * A, vy * b0 + uy * 2 * A)
    return _first_sea_hit(inland, seaward, sea, coastline_of(sea, canvas))


def build_rivers(spec: CitySpec, canvas: Polygon, sea, variant: Variant,
                 lobe_b0: float | None = None) -> list[WaterBody]:
    """Main rivers, sea channels and tributaries (deltas are added by `build_deltas`)."""
    w = spec.water
    coast = coastline_of(sea, canvas)
    ux, uy, vx, vy = G.frame(w.coast.side)
    corners = list(canvas.exterior.coords)[:4]
    A = max(x * ux + y * uy for x, y in corners)
    Bh = max(abs(x * vx + y * vy) for x, y in corners)
    bodies: list[WaterBody] = []
    by_name: dict[str, WaterBody] = {}
    same_edge: dict[str, list[str]] = {}
    for r in w.rivers:
        if r.from_at is None:
            same_edge.setdefault(r.from_, []).append(r.name)
    lobe_river = next((r.name for r in w.rivers if r.to in ("sea", "bay") and r.delta_branches),
                      None)
    for r in _order_rivers(w.rivers):
        idx = w.rivers.index(r) + 1
        rid = f"r{idx:02d}" if r.kind == "river" else f"ch{idx:02d}"
        seed = derive_seed(spec.seed, "hydro.river", r.name)
        wmin, wmax = r.width_m
        wmean = (wmin + wmax) / 2
        parent = by_name.get(r.to)
        if r.from_at is not None:
            at = r.from_at
        else:
            group = same_edge[r.from_]
            base_at = 0.5 if "_" not in r.from_ else 0.3  # diagonal: beside the corner
            at = base_at + (group.index(r.name) - (len(group) - 1) / 2) * 0.28
            shift = variant.at_shift.get(r.name, 0.0) * (0.4 if parent is not None else 1.0)
            at = min(max(at + shift, 0.12), 0.88)
        start = G.edge_point(canvas, r.from_, at)
        if r.from_at is None:
            start = _onto_land(canvas, sea, r.from_, at)
        inward = np.array(G.edge_tangent_inward(canvas, start))
        s_out = (start[0] - inward[0] * wmax, start[1] - inward[1] * wmax)
        mouth_kind, flows_into, base, ramp = "sea", "sea", None, (0.08, 0.08)
        if parent is not None:
            # Join the parent downstream of the entry point, arriving at 45 degrees to the
            # parent's flow (an acute downstream angle), unless `to.at` pins the junction.
            pl = parent.centerline
            if r.to_at is not None:
                t = r.to_at
            else:
                t = min(max(pl.project(Point(start), normalized=True) + 0.15, 0.2), 0.85)
            dj = t * pl.length
            jp = pl.interpolate(dj)
            tau = _tangent(pl, dj)
            rel = np.array([start[0] - jp.x, start[1] - jp.y])
            side = 1.0 if tau[0] * rel[1] - tau[1] * rel[0] >= 0 else -1.0
            d_end = _rot(tau, -side * M.radians(45))
            pw = width_at(parent, dj)
            end = (jp.x + d_end[0] * 0.5 * pw, jp.y + d_end[1] * 0.5 * pw)
            ln = M.hypot(end[0] - s_out[0], end[1] - s_out[1])
            base = G.bezier(s_out, np.array(s_out) + inward * 0.35 * ln,
                            np.array(end) - d_end * 0.4 * ln, end)
            ramp = (0.08, 0.18)
            mouth_kind, flows_into = "river", parent.id
        elif r.to in presets.DIRECTIONS or sea.is_empty or coast.is_empty:
            edge = r.to if r.to in presets.DIRECTIONS else presets.opposite(r.from_)
            e = (G.edge_point(canvas, edge, r.to_at) if r.to_at is not None
                 else _onto_land(canvas, sea, edge, 0.5))
            out = G.edge_tangent_inward(canvas, e)
            end = (e[0] - out[0] * wmax, e[1] - out[1] * wmax)
            mouth_kind, flows_into = "edge", None
        else:
            if r.name == lobe_river and lobe_b0 is not None:
                m = lobe_mouth(canvas, sea, w.coast.side, lobe_b0)
            elif r.to_at is not None:
                aim = G.edge_point(canvas, w.coast.side, r.to_at)
                m = nearest_points(coast, Point(aim))[0].coords[0]
            elif r.to == "bay" and w.coast.form in ("bay", "crescent"):
                m = _bay_head(coast, ux, uy, vx, vy, Bh)
            else:
                aim = (start[0] + ux * 2 * A * 1.2, start[1] + uy * 2 * A * 1.2)
                m = _first_sea_hit(start, aim, sea, coast)
            end = (m[0] + ux * wmax * 2.5, m[1] + uy * wmax * 2.5)
        lam, om = _meander_params(wmean, r.meander)
        bulge = variant.bulge.get(r.name, 0.0)

        def make(scale, a=s_out, b=end, base=base, lam=lam, om=om, bulge=bulge, seed=seed,
                 ramp=ramp):
            return G.course(a, b, np.random.default_rng(seed), wavelength=lam, omega=om,
                            base=base, bulge=bulge, scale=scale, ramp=ramp)

        line = _keep_inside(make, canvas, wmax)
        if mouth_kind == "sea":
            line, _ = _trim_at(line, sea, 2.0 * wmax, skip=wmax * 3)
        elif mouth_kind == "river":
            line, _ = _trim_at(line, parent.polygon, 0.6 * wmax, skip=wmax * 3)
        widths_fn = _width_fn(wmin, wmax, np.random.default_rng(seed + 1))
        poly = G.polygonal(G.variable_buffer(line, widths_fn).intersection(canvas))
        body = WaterBody(rid, "river" if r.kind == "river" else "sea_channel", r.name, line,
                         _widths_at(line, widths_fn), poly, mouth_kind, flows_into)
        bodies.append(body)
        by_name[r.name] = body
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


def _coast_hit(line: LineString, sea) -> float:
    """Distance along `line` where it first enters the sea (its length if it never does)."""
    pts = G.resample(line, 8.0)
    ds = np.linspace(0, line.length, len(pts))
    inside = shapely.contains_xy(sea, pts[:, 0], pts[:, 1])
    return float(ds[int(np.argmax(inside))]) if inside.any() else line.length


def _seaward(cl: LineString, s: float, sea) -> np.ndarray:
    """Unit normal of the coastline at `s` meters along it, pointing into the sea."""
    a = cl.interpolate(max(s - 40.0, 0.0))
    b = cl.interpolate(min(s + 40.0, cl.length))
    t = _unit((b.x - a.x, b.y - a.y))
    n = np.array([-t[1], t[0]])
    p = cl.interpolate(s)
    if not sea.contains(Point(p.x + n[0] * 30, p.y + n[1] * 30)):
        n = -n
    return n


def delta_plan(span: float, s_mouth: float, r, variant: Variant, scale: float = 1.0,
               upstream_limit: float = 0.0) -> tuple[float, float]:
    """(split distance upstream of the mouth, fan width along the coast) of a delta."""
    d = min(max(0.3 * span, 500.0), 1300.0) * scale * (1 + variant.split.get(r.name, 0.0))
    d = max(min(d, 0.65 * s_mouth, s_mouth - upstream_limit - 150.0), 200.0)
    f = min(max(0.42 * span, 700.0), 1900.0) * scale * (1 + variant.spread.get(r.name, 0.0))
    return d, f


def build_delta(spec: CitySpec, main: WaterBody, sea, canvas: Polygon, variant: Variant,
                scale: float = 1.0, upstream_limit: float = 0.0) -> list[WaterBody]:
    """Distributaries of `main`: a fan of curved channels that split well upstream of the
    mouth. The first branch on each side leaves the main channel `D` meters upstream of the
    coast; each further branch on a side leaves the previous one part way down. Mouths are
    spread over a fan of width `F` along the coast and channels arrive roughly square to it.
    The main channel narrows below the first split (the flow divides)."""
    r = spec.water.rivers[[x.name for x in spec.water.rivers].index(main.name)]
    coast = coastline_of(sea, canvas)
    span = max(canvas.bounds[2] - canvas.bounds[0], canvas.bounds[3] - canvas.bounds[1])
    line = main.centerline
    s_m = _coast_hit(line, sea)
    mouth = line.interpolate(s_m)
    cl = main_coast(coast, mouth)
    if cl is None:
        return []
    d_split, fan = delta_plan(span, s_m, r, variant, scale, upstream_limit)
    gap = min(fan / max(r.delta_branches, 1), 1.1 * d_split)
    s0 = cl.project(mouth)
    ux, uy, _, _ = G.frame(spec.water.coast.side)
    rng = np.random.default_rng(derive_seed(spec.seed, "hydro.delta", r.name))
    names = list(r.branch_names)
    out: list[WaterBody] = []
    last: dict[int, WaterBody] = {}
    taken = [s0]
    for j in range(r.delta_branches):
        side = 1 if j % 2 == 0 else -1
        rank = j // 2 + 1
        s_want = s0 + side * rank * gap * (1 + rng.uniform(-0.12, 0.12))
        if rank == 1 or side not in last:
            parent = main
            d_fork = s_m - d_split * (1.0 if side == 1 else 0.82)
            # Split inland of the mouth, so the branch runs toward the sea, not along it.
            q = cl.interpolate(min(max(s_want, 0.04 * cl.length), 0.96 * cl.length))
            n_q = _seaward(cl, cl.project(q), sea)
            while d_fork > upstream_limit + 250.0:
                fp = line.interpolate(d_fork)
                v = np.array([q.x - fp.x, q.y - fp.y])
                if M.dot(v, n_q) >= 0.45 * float(M.hypot(*v)):
                    break
                d_fork -= 50.0
        else:
            parent = last[side]
            d_fork = _coast_hit(parent.centerline, sea) * (0.38 + 0.06 * (rank - 2))
        fp = parent.centerline.interpolate(d_fork)
        # Pull the mouth toward the main mouth until it lies seaward of the split (a fan on
        # the delta lobe, not a branch that runs along the coast).
        s = s_want
        for _ in range(10 if parent is main else 0):
            s = min(max(s, 0.04 * cl.length), 0.96 * cl.length)
            q = cl.interpolate(s)
            v = np.array([q.x - fp.x, q.y - fp.y])
            if M.dot(v, (ux, uy)) >= 0.25 * float(M.hypot(*v)):
                break
            s = s0 + (s - s0) * 0.85
        s = min(max(s, 0.04 * cl.length), 0.96 * cl.length)
        if min(abs(s - t) for t in taken) < 0.4 * gap:
            continue  # no room left on this side of the mouth
        taken.append(s)
        q = cl.interpolate(s)
        pl = parent.centerline
        p = pl.interpolate(d_fork)
        tau = _tangent(pl, d_fork)
        n_sea = _seaward(cl, s, sea)
        bw = max(0.62 * width_at(parent, d_fork), 24.0)
        end = (q.x + n_sea[0] * 2.5 * bw, q.y + n_sea[1] * 2.5 * bw)
        ln = M.hypot(end[0] - p.x, end[1] - p.y)
        base = G.bezier((p.x, p.y), np.array([p.x, p.y]) + tau * 0.4 * ln,
                        np.array(end) - n_sea * 0.45 * ln, end)
        lam = min(max(12.0 * bw, 300.0), 900.0)
        others = [b.centerline for b in [main, *out] if b is not parent]
        seed = derive_seed(spec.seed, "hydro.branch", main.name, j)
        for om in (0.1 + 0.5 * r.meander, 0.0):
            cand = G.course((p.x, p.y), end, np.random.default_rng(seed), wavelength=lam,
                            omega=om, base=base, ramp=(0.2, 0.15))
            cand, _ = _trim_at(cand, sea, 2.0 * bw, skip=bw * 2)
            if not any(cand.crosses(o) for o in others):
                break
        wfn = lambda ts, bw=bw: bw * (1 + 0.35 * M.power(np.asarray(ts), 1.5))  # noqa: E731
        poly = G.polygonal(G.variable_buffer(cand, wfn).intersection(canvas))
        body = WaterBody(f"{main.id}.b{j + 1}", "delta_branch",
                         names[j] if j < len(names) else None, cand, _widths_at(cand, wfn),
                         poly, "sea", "sea", parent_id=main.id,
                         attrs={"side": side, "rank": rank, "leaves": parent.id,
                                "split_t": round(d_fork / line.length, 4)
                                if parent is main else 1.0,
                                "coast_s": round(s, 2)})
        out.append(body)
        last[side] = body
    if out:
        _narrow_below(main, s_m - d_split, canvas)
    return out


def _narrow_below(main: WaterBody, d0: float, canvas: Polygon) -> None:
    """Main channel width x0.75 below distance d0 (eased over 200 m): the flow has split."""
    cs = np.asarray(main.centerline.coords)
    cum = np.concatenate([[0.0], np.cumsum(M.hypot(*np.diff(cs, axis=0).T))])
    base = np.asarray(main.attrs.get("_widths_full", main.widths), dtype=float)
    main.attrs["_widths_full"] = [float(x) for x in base]
    k = 1 - 0.25 * G.smoothstep((cum - d0) / 200.0)
    w = base[:len(cum)] * k
    main.widths = [float(round(x, 1)) for x in w]
    fn = lambda ts: np.interp(np.asarray(ts) * cum[-1], cum, w)  # noqa: E731
    main.polygon = G.polygonal(G.variable_buffer(main.centerline, fn).intersection(canvas))


def build_deltas(spec: CitySpec, canvas: Polygon, sea, bodies: list[WaterBody],
                 variant: Variant, limits: dict[str, float]) -> None:
    for r in spec.water.rivers:
        main = next((b for b in bodies if b.name == r.name and b.kind != "delta_branch"), None)
        if main is None or not r.delta_branches or main.mouth != "sea":
            continue
        bodies += build_delta(spec, main, sea, canvas, variant, 1.0, limits.get(main.id, 0.0))


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
              beyond, sector=None, strict: bool = False) -> Polygon | None:
    """Island blob nearest to `aim` that stays `gap` meters clear of everything but `free`.

    `sector` = (center, unit direction): spots whose bearing from the center is within 35
    degrees of the direction are tried first, so an island asked for the south west does not
    slide north round an island placed before it."""
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
    key = M.hypot(gx - aim.x, gy - aim.y)
    if sector is not None:
        (cx, cy), (dx, dy) = sector
        rx, ry = gx - cx, gy - cy
        cosang = (rx * dx + ry * dy) / (M.hypot(rx, ry) + 1e-9)
        outside = cosang < M.cos(M.radians(35))
        if strict:
            gx, gy, key = gx[~outside], gy[~outside], key[~outside]
        else:
            key = key + outside * 1e7
    order = np.argsort(key, kind="stable")
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
    jobs = [(i.name, i.area_km2 * 1e6, i.position, i.setting, False) for i in todo]
    jobs += [(n, a * 1e6, p, "offshore", True) for n, a, p in fillers]
    jobs.sort(key=lambda j: -j[1])
    c = _sea_aim(canvas, sea, "center", 0.0)

    def place(order):
        out: list[IslandRec] = []
        msgs, misses = [], []
        taken = Polygon()
        for name, area, position, setting, filler in order:
            rng = np.random.default_rng(derive_seed(spec.seed, "hydro.island", name))
            elong = float(rng.uniform(1.0, 1.25))
            free = sea.difference(river_keepout).difference(taken)
            aim = _sea_aim(canvas, sea, position, 0.5 if setting == "nearshore" else 0.7)
            sector = None
            if position != "center":
                sector = ((c.x, c.y), presets.DIRECTION_VECTORS[position])
            poly = None
            gaps = [60.0, 45.0, 30.0] if setting == "nearshore" else [220.0, 150.0, 100.0, 70.0]
            # Every gap inside the bearing sector first, then anywhere.
            tries = [(g, True) for g in gaps] if sector is not None else []
            for gap, strict in tries + [(g, False) for g in gaps]:
                poly = _fit_blob(free, aim, area, rng, elong, gap, canvas, beyond, sector,
                                 strict)
                if poly is not None:
                    break
            if poly is None:
                msgs.append(f"island '{name}' does not fit in the sea; raise sea_share or "
                            "shrink it")
                misses.append(name)
                continue
            if sector is not None and not filler:
                q = poly.centroid
                v = np.array([q.x - c.x, q.y - c.y])
                if M.dot(v, sector[1]) < M.cos(M.radians(45)) * M.hypot(*v):
                    misses.append(name)
                    bearing = (90 - M.degrees(M.atan2(v[1], v[0]))) % 360
                    msgs.append(f"island '{name}' has no room toward '{position}'; it sits at "
                                f"bearing {bearing:.0f} deg from the middle of the sea")
            taken = taken.union(poly.buffer(60))
            out.append(IslandRec(name, setting, area, poly, filler=filler))
        return out, msgs, misses

    out, msgs, misses = place(jobs)
    if misses:
        # An island that did not land toward its position goes first on a second try (a big
        # island may have taken the only room there); keep the try with fewer misses.
        retry = [j for j in jobs if j[0] in misses] + [j for j in jobs if j[0] not in misses]
        out2, msgs2, misses2 = place(retry)
        if len(misses2) < len(misses):
            out, msgs = out2, msgs2
    notes += msgs
    return out


def place_river_islands(spec: CitySpec, canvas: Polygon, sea, bodies: list[WaterBody],
                        notes: list[str], variant: Variant
                        ) -> tuple[list[IslandRec], object, dict[str, float]]:
    """Mid-river islands, upstream of the planned delta split. Returns the islands, the water
    ring around them and, per river id, how far down the river the rings reach (the delta must
    split below that)."""
    out, rings = [], []
    limits: dict[str, float] = {}
    span = max(canvas.bounds[2] - canvas.bounds[0], canvas.bounds[3] - canvas.bounds[1])
    specs = {r.name: r for r in spec.water.rivers}
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
        split = line.length
        r = specs.get(body.name)
        if r is not None and r.delta_branches and body.mouth == "sea" and not sea.is_empty:
            s_m = _coast_hit(line, sea)
            d_plan = delta_plan(span, s_m, r, variant)[0]
            split = s_m - d_plan
            # Leave more room when a delta island has to fit between the channels.
            room = 0.95 if any(i.setting == "delta" and i.river == r.name
                               for i in spec.water.islands) else 0.55
            while split > 0 and sea.distance(line.interpolate(split)) < room * d_plan:
                split -= 50.0  # the delta splits well inland, not on its own lobe
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
        angle = M.atan2(b.y - a.y, b.x - a.x)
        poly = G.blob((c.x, c.y), area, rng, 1.35, angle)
        i = min(int(d / line.length * (len(body.widths) - 1)), len(body.widths) - 1)
        arm = max(0.6 * body.widths[i], 30.0)
        ring = poly.buffer(arm)
        rings.append(ring)
        cut = line.intersection(ring)
        pts = [c for g in getattr(cut, "geoms", [cut]) for c in getattr(g, "coords", [])]
        reach = max((line.project(Point(p)) for p in pts), default=d + half)
        limits[body.id] = max(limits.get(body.id, 0.0), reach)
        out.append(IslandRec(isl.name, "mid_river", area, poly))
    return out, (unary_union(rings) if rings else Polygon()), limits


def _wedge(canvas, sea, bodies, rings, probe: Point):
    water = unary_union([sea, rings] + [b.polygon for b in bodies])
    land = G.polygonal(canvas.difference(water))
    ps = G.parts(land)
    if not ps:
        return Polygon()
    return min(ps, key=lambda p: (p.distance(probe), -p.area))


def _wedge_probe(cl: LineString, s_a: float, s_b: float, sea) -> Point:
    """A point on the land between two mouths, a little inland of the coast."""
    s = (s_a + s_b) / 2
    p = cl.interpolate(s)
    n = _seaward(cl, s, sea)
    return Point(p.x - n[0] * 60, p.y - n[1] * 60)


def solve_delta_islands(spec: CitySpec, canvas: Polygon, sea, bodies: list[WaterBody],
                        rings, notes: list[str], variant: Variant,
                        limits: dict[str, float]) -> list[IslandRec]:
    """A delta island is the land between two neighboring mouths of a delta. The pair nearest
    the island's `position` is chosen and the whole delta is scaled (split distance and fan
    width together) by bisection until that land has the asked area."""
    out = []
    coast = coastline_of(sea, canvas)
    for isl in spec.water.islands:
        if isl.setting != "delta":
            continue
        main = next((b for b in bodies if b.name == isl.river and b.kind != "delta_branch"),
                    None)
        if main is None or not any(b.parent_id == main.id for b in bodies):
            notes.append(f"delta island '{isl.name}': river '{isl.river}' has no delta branches")
            continue
        aim = _aim(canvas, isl.position, 0.5, spec.water.coast.side)
        mouth = main.centerline.interpolate(_coast_hit(main.centerline, sea))
        cl = main_coast(coast, mouth)
        s_main = cl.project(mouth)
        rest = [b for b in bodies if b.parent_id != main.id]

        def pair_of(branches):
            mouths = sorted([(s_main, main.id)] + [(b.attrs["coast_s"], b.id) for b in branches])
            return [(mouths[i], mouths[i + 1]) for i in range(len(mouths) - 1)]

        first = [b for b in bodies if b.parent_id == main.id]
        pairs = pair_of(first)
        key = min(pairs, key=lambda pr: (_wedge_probe(cl, pr[0][0], pr[1][0], sea).distance(aim),
                                         pr[0][1]))
        ids = (key[0][1], key[1][1])
        target = isl.area_km2 * 1e6

        def trial(scale: float):
            br = build_delta(spec, main, sea, canvas, variant, scale, limits.get(main.id, 0.0))
            pr = next((p for p in pair_of(br) if (p[0][1], p[1][1]) == ids), None)
            if pr is None:
                return 0.0, br, None
            probe = _wedge_probe(cl, pr[0][0], pr[1][0], sea)
            return _wedge(canvas, sea, rest + [main] + br, rings, probe).area, br, probe

        best = None
        lo, hi = 0.35, 3.0
        for _ in range(14):
            mid = (lo + hi) / 2
            area, br, probe = trial(mid)
            if probe is not None and (best is None or abs(area - target) < abs(best[0] - target)):
                best = (area, br, probe, mid)
            if area > target:
                hi = mid
            else:
                lo = mid
        if best is None:
            notes.append(f"delta island '{isl.name}': no land between the delta channels")
            continue
        _, _, probe, scale = best
        br = build_delta(spec, main, sea, canvas, variant, scale, limits.get(main.id, 0.0))
        bodies[:] = [b for b in bodies if b.parent_id != main.id] + br
        out.append(IslandRec(isl.name, "delta", target, None, probe=(probe.x, probe.y)))
    return out


# ---------------------------------------------------------------------------
# Quantization (stage boundaries, see geom.qpoly)
# ---------------------------------------------------------------------------

def quantize_bodies(bodies: list[WaterBody]) -> list[WaterBody]:
    for b in bodies:
        b.centerline = G.qline(b.centerline, dedupe=False)
        b.widths = [G.q(w) for w in b.widths]
        b.polygon = G.qpoly(b.polygon)
    return bodies


def quantize_islands(islands: list[IslandRec]) -> list[IslandRec]:
    for i in islands:
        i.polygon = G.qpoly(i.polygon)
        if i.probe is not None:
            i.probe = G.qpoint(i.probe)
    return islands


def quantize(h: Hydro) -> Hydro:
    h.sea = G.qpoly(h.sea)
    quantize_bodies(h.bodies)
    quantize_islands(h.islands)
    h.rings = G.qpoly(h.rings)
    h.water, h.land = G.qpoly(h.water), G.qpoly(h.land)
    h.landmasses = [G.qpoly(p) for p in h.landmasses]
    return h


# ---------------------------------------------------------------------------
# Land
# ---------------------------------------------------------------------------

def rebuild_land(h: Hydro) -> None:
    """water = sea + every water body + island rings - islands; land = map - water. Every
    overlay is snapped to the grid and every measure exact (see `geom.area`)."""
    sea_isl = [i.polygon for i in h.islands if i.setting in ("offshore", "nearshore")]
    river_isl = [i.polygon for i in h.islands if i.setting == "mid_river"]
    sea = G.diff(h.sea, G.union(sea_isl)) if sea_isl else h.sea
    water = G.union([sea, h.rings] + [b.polygon for b in h.bodies])
    if river_isl:
        water = G.diff(water, G.union(river_isl))
    water = G.inter(water, h.canvas)
    land = G.diff(h.canvas, water)
    land = G.opening(land, MIN_LAND_WIDTH_M / 2)
    land = G.drop_small(land, MIN_LANDMASS_M2)
    land = G.clean(land)
    h.land = land
    h.water = G.clean(G.diff(h.canvas, land))
    h.landmasses = G.parts(land)
    ch = [b.polygon for b in h.bodies if b.kind == "sea_channel"]
    h.coastline = coastline_of(G.union([sea, *ch]) if ch else sea, h.canvas)
    # Island polygons follow the final land.
    for isl in h.islands:
        ref = isl.polygon if isl.polygon is not None else G.qpoly(Point(isl.probe).buffer(5))
        best = max(h.landmasses, key=lambda p: (G.area(G.inter(p, ref)), -G.dist(p, ref)),
                   default=None)
        if best is not None and (G.area(G.inter(best, ref)) > 0 or isl.polygon is None):
            isl.polygon = best


def build_hydro(spec: CitySpec, canvas: Polygon, variant: Variant) -> Hydro:
    w = spec.water
    notes: list[str] = []
    b0, lobe, lobe_b0 = None, 0.0, None
    first_sea = next((r for r in w.rivers if r.to in ("sea", "bay")), None)
    if w.coast.form == "delta" and first_sea is not None:
        at = first_sea.to_at
        b0 = (G.edge_point(canvas, w.coast.side, at) if at is not None
              else G.edge_point(canvas, first_sea.from_, first_sea.from_at))
    elif first_sea is not None and first_sea.delta_branches and \
            w.coast.form in ("bay", "crescent", "straight"):
        # The delta builds a lobe of land into the sea, so the river crosses most of the
        # city and the distributaries fan out at the coast instead of at the map center.
        if first_sea.to_at is not None:
            b0 = G.edge_point(canvas, w.coast.side, first_sea.to_at)
        elif w.coast.form == "straight":
            b0 = G.edge_point(canvas, first_sea.from_, first_sea.from_at)
        else:
            b0 = (0.0, 0.0)
        lobe = 0.1 if w.coast.form == "straight" else 0.17
        _, _, vx, vy = G.frame(w.coast.side)
        bh = max(abs(x * vx + y * vy) for x, y in list(canvas.exterior.coords)[:4])
        lobe_b0 = float(np.clip(b0[0] * vx + b0[1] * vy, -0.5 * bh, 0.5 * bh))
    # Every sub-stage hands on coordinates on the 0.01 m grid (determinism across machines).
    sea = G.qpoly(build_sea(spec, canvas, b0, lobe))
    T.stage("coast", sea)
    bodies = quantize_bodies(build_rivers(spec, canvas, sea, variant, lobe_b0))
    T.stage("rivers", bodies)
    river_isl, rings, limits = place_river_islands(spec, canvas, sea, bodies, notes, variant)
    river_isl, rings = quantize_islands(river_isl), G.qpoly(rings)
    limits = {k: G.q(v) for k, v in limits.items()}
    T.stage("river_islands", [river_isl, rings, limits])
    build_deltas(spec, canvas, sea, bodies, variant, limits)
    quantize_bodies(bodies)
    T.stage("deltas", bodies)
    delta_isl = quantize_islands(
        solve_delta_islands(spec, canvas, sea, bodies, rings, notes, variant, limits))
    quantize_bodies(bodies)
    T.stage("delta_islands", [delta_isl, bodies])
    sea_isl = quantize_islands(place_sea_islands(spec, canvas, sea, bodies, notes))
    T.stage("sea_islands", sea_isl)
    h = Hydro(canvas, sea, bodies, sea_isl + river_isl + delta_isl, rings, notes=notes)
    # Keep the spec order for islands (fillers last).
    order = {i.name: k for k, i in enumerate(w.islands)}
    h.islands.sort(key=lambda i: (i.filler, order.get(i.name, 99), i.name))
    rebuild_land(h)
    quantize(h)
    T.stage("landmasses", [h.land, h.water, h.landmasses, h.islands])
    return h
