"""Stage 11, buildings (M3): one building per M2 lot, by the district archetype's program.

For each lot: the facade sits on `frontage[0].line` (the longest road edge), whose direction
sets the building's local frame (u along the street, v into the lot). The buildable area is
the lot inset by the side setback, minus a strip along every frontage as deep as that road
class asks (avenues deeper than streets, alleys and pedestrian streets none in street-wall
districts). A program per archetype picks the building archetype (podium tower, slab,
courtyard block, megabuilding, terraced, shopfront row, shanty stack, warehouse, shed,
parking structure, villa, lab), its height from a height field (distance to the district
focus, smooth noise, lot size, frontage class: avenue lots rise higher), its floor height and
its podium. Masses are extruded footprints (z0, z1) on one floor grid per building.

Then the ground floor: street-facing facade edges are split into units of 4 to 12 m with use
tags (food, convenience, bar, clinic, cyberware, pawn, club, arcade, laundromat, lobby),
entrances, awnings and signs; the main entrance faces the best frontage, alleys and service
lanes get service entrances, warehouses loading docks. Rooftops get blockout primitives
(mechanical penthouses, AC units, water tanks, antennas, billboards, helipads, AV pads) and
podium and low roofs green roofs or roof plazas.

Determinism: every lot draws from its own generator (district seed, lot index), shapes are
built in local frames with `dmath` angles and grid-rounded points (`massing`), and every
decision uses exact predicates on grid geometry or plain Python arithmetic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import massing as MS
from . import streets as ST
from . import trace as T

q = G.q
MIN_FOOT_M2 = 25.0
RANK = {"avenue": 0, "street": 1, "pedestrian": 2, "highway": 3, "service": 4, "alley": 5,
        "footbridge": 6}
SHOP_CLASSES = ("avenue", "street", "pedestrian")
DOOR_RANK = {"avenue": 0, "street": 1, "pedestrian": 2, "alley": 3, "service": 4,
             "footbridge": 5, "highway": 9}
SERVICE_CLASSES = ("alley", "service")
ANCILLARY = ("parking_structure",)
ROAD_CLEARANCE_M = 5.5
UNIT_MIN_M, UNIT_MAX_M = 4.0, 12.0
FACADE_TOL_M = 4.6   # a facade faces a frontage up to setback + this (front fits step back 4 m)


@dataclass(frozen=True)
class Program:
    """Building program of a district archetype."""
    mix: tuple                       # ((building archetype, weight), ...)
    use: str
    fh: float                        # floor height
    front: dict                      # setback by frontage road class
    side: float                      # side and rear setback
    podium_floors: tuple[int, int] = (2, 4)
    tower_side: tuple[float, float] = (18.0, 44.0)
    coverage: float = 0.45           # tower (or box) share of the buildable area
    unit_w: tuple[float, float] | None = (6.0, 10.0)
    unit_uses: tuple = ()
    unit_share: float = 1.0          # share of buildings with ground-floor units
    awning: tuple[float, float, float] = (0.0, 0.0, 0.0)   # probability, depth lo, hi
    sign: float = 0.3
    lobby: bool = True
    field: tuple[float, float, float, float] = (0.45, 0.25, 0.2, 0.1)  # center, noise, size, avenue
    skew: float = 1.5                # f -> f ** skew (1, 1.5 or 2)
    green: float = 0.5               # green roof chance (times district greenery)
    roof: tuple = ()                 # roof item kinds this archetype uses
    axis: float = 0.0                # weight of the boulevard ridge in the height field


def _front(avenue, street, pedestrian, alley, service=None, highway=None) -> dict:
    return {"avenue": avenue, "street": street, "pedestrian": pedestrian, "alley": alley,
            "service": alley if service is None else service,
            "highway": max(avenue, 6.0) if highway is None else highway,
            "footbridge": pedestrian}


SHOP_USES = {
    "old_town": (("food", 3), ("convenience", 1.5), ("pawn", 1), ("laundromat", 1),
                 ("clinic", 0.5), ("cyberware", 1), ("bar", 1), ("arcade", 0.5), ("club", 0.3)),
    "entertainment_market": (("bar", 2.5), ("club", 2.5), ("arcade", 1.5), ("food", 2),
                             ("cyberware", 1), ("pawn", 0.5)),
    "midtown_mixed": (("food", 3), ("convenience", 1.5), ("bar", 1.5), ("clinic", 1),
                      ("cyberware", 1), ("laundromat", 1), ("arcade", 0.8)),
    "corporate_core": (("food", 4), ("convenience", 2), ("cyberware", 2), ("clinic", 1.5),
                       ("bar", 0.5)),
    "transit_hub": (("food", 3.5), ("convenience", 3), ("cyberware", 1.5), ("bar", 1),
                    ("pawn", 1)),
    "megablock_residential": (("convenience", 2.5), ("food", 2.5), ("laundromat", 1.5),
                              ("clinic", 1), ("pawn", 1), ("cyberware", 1), ("arcade", 0.5)),
    "residential_heights": (("convenience", 2), ("food", 2), ("clinic", 1)),
    "research_campus": (("food", 1), ("clinic", 1)),
    "industrial_port": (("food", 1), ("convenience", 1)),
    "spaceport": (("food", 1), ("convenience", 1)),
}

PROGRAMS: dict[str, Program] = {
    "corporate_core": Program(
        mix=(("podium_tower", 0.78), ("slab", 0.08), ("terraced", 0.08),
             ("parking_structure", 0.06)),
        use="office", fh=4.0, front=_front(5.0, 3.5, 2.0, 0.0), side=0.0,
        podium_floors=(3, 5), tower_side=(20.0, 46.0), coverage=0.42, unit_w=(8.0, 12.0),
        unit_uses=SHOP_USES["corporate_core"], awning=(0.2, 1.2, 2.0), sign=0.3,
        field=(0.55, 0.2, 0.15, 0.1), skew=1.6, green=0.9,
        axis=0.6,
        roof=("mechanical", "helipad", "av_pad", "antenna", "ac_unit")),
    "megablock_residential": Program(
        mix=(("megabuilding", 0.8), ("podium_tower", 0.2)),
        use="residential", fh=3.2, front=_front(5.0, 4.0, 2.0, 1.0), side=4.0,
        podium_floors=(2, 3), tower_side=(22.0, 40.0), coverage=0.45, unit_w=(6.0, 10.0),
        unit_uses=SHOP_USES["megablock_residential"], awning=(0.4, 1.0, 2.0), sign=0.4,
        field=(0.3, 0.5, 0.15, 0.05), skew=1.5, green=0.6,
        axis=0.4,
        roof=("mechanical", "water_tank", "antenna", "ac_unit", "billboard")),
    "midtown_mixed": Program(
        mix=(("perimeter", 0.5), ("podium_tower", 0.3), ("terraced", 0.2)),
        use="mixed", fh=3.5, front=_front(2.5, 1.5, 0.0, 0.0), side=0.0,
        podium_floors=(2, 3), tower_side=(16.0, 34.0), coverage=0.5, unit_w=(6.0, 10.0),
        unit_uses=SHOP_USES["midtown_mixed"], awning=(0.5, 1.0, 2.0), sign=0.5,
        field=(0.4, 0.3, 0.2, 0.12), skew=1.6, green=0.7,
        axis=0.4,
        roof=("mechanical", "ac_unit", "water_tank", "antenna", "billboard")),
    "entertainment_market": Program(
        mix=(("shopfront_row", 0.55), ("shanty_stack", 0.25), ("podium_tower", 0.2)),
        use="entertainment", fh=3.5, front=_front(1.0, 0.0, 0.0, 0.0), side=0.0,
        podium_floors=(2, 3), tower_side=(10.0, 24.0), coverage=0.55, unit_w=(4.0, 8.0),
        unit_uses=SHOP_USES["entertainment_market"], awning=(0.7, 1.2, 2.4), sign=0.9,
        field=(0.3, 0.4, 0.2, 0.1), skew=1.5, green=0.2,
        roof=("billboard", "ac_unit", "water_tank", "antenna")),
    "old_town": Program(
        mix=(("shopfront_row", 0.5), ("shanty_stack", 0.4), ("courtyard_block", 0.1)),
        use="mixed", fh=3.0, front=_front(1.0, 0.0, 0.0, 0.0), side=0.0,
        podium_floors=(1, 1), tower_side=(8.0, 16.0), coverage=0.6, unit_w=(4.0, 7.0),
        unit_uses=SHOP_USES["old_town"], awning=(0.75, 1.0, 2.2), sign=0.6,
        field=(0.15, 0.5, 0.25, 0.1), skew=1.0, green=0.3,
        roof=("water_tank", "ac_unit", "antenna", "billboard")),
    "industrial_port": Program(
        mix=(("warehouse", 0.6), ("shed", 0.2), ("yard", 0.2)),
        use="industrial", fh=5.0, front=_front(8.0, 8.0, 4.0, 3.0, 4.0, 10.0), side=5.0,
        coverage=0.62, unit_w=None, unit_uses=SHOP_USES["industrial_port"], unit_share=0.0,
        lobby=False, field=(0.0, 0.45, 0.45, 0.1), skew=1.0, green=0.0,
        roof=("ac_unit", "mechanical")),
    "residential_heights": Program(
        mix=(("villa", 0.45), ("terraced", 0.3), ("slab", 0.15), ("courtyard_block", 0.1)),
        use="residential", fh=3.4, front=_front(6.0, 5.0, 3.0, 2.0), side=3.0,
        tower_side=(14.0, 30.0), coverage=0.45, unit_w=(6.0, 10.0),
        unit_uses=SHOP_USES["residential_heights"], unit_share=0.25, sign=0.1,
        field=(0.25, 0.4, 0.25, 0.1), skew=1.6, green=1.0,
        roof=("ac_unit", "water_tank", "antenna")),
    "research_campus": Program(
        mix=(("lab", 0.6), ("terraced", 0.2), ("slab", 0.2)),
        use="civic", fh=4.0, front=_front(9.0, 8.0, 5.0, 3.0), side=6.0,
        tower_side=(20.0, 40.0), coverage=0.5, unit_w=None,
        unit_uses=SHOP_USES["research_campus"], unit_share=0.0, sign=0.1,
        field=(0.35, 0.35, 0.3, 0.0), skew=1.8, green=1.0,
        roof=("mechanical", "ac_unit", "antenna")),
    "transit_hub": Program(
        mix=(("podium_tower", 0.55), ("slab", 0.25), ("parking_structure", 0.1),
             ("perimeter", 0.1)),
        use="mixed", fh=3.5, front=_front(4.0, 2.5, 1.0, 0.0), side=0.0,
        podium_floors=(2, 4), tower_side=(16.0, 36.0), coverage=0.45, unit_w=(6.0, 10.0),
        unit_uses=SHOP_USES["transit_hub"], awning=(0.5, 1.2, 2.0), sign=0.7,
        field=(0.55, 0.25, 0.15, 0.1), skew=1.4, green=0.4,
        axis=0.3,
        roof=("av_pad", "mechanical", "antenna", "ac_unit", "billboard")),
    "spaceport": Program(
        mix=(("hangar", 0.5), ("slab", 0.3), ("parking_structure", 0.1), ("shed", 0.1)),
        use="transport", fh=4.0, front=_front(8.0, 8.0, 4.0, 3.0), side=5.0,
        tower_side=(18.0, 36.0), coverage=0.55, unit_w=None,
        unit_uses=SHOP_USES["spaceport"], unit_share=0.0,
        field=(0.0, 0.5, 0.5, 0.0), skew=1.0, green=0.0, roof=("ac_unit", "mechanical",
                                                                 "antenna")),
}

USE_OF = {"podium_tower": None, "slab": None, "courtyard_block": "residential",
          "megabuilding": "residential", "terraced": None, "shopfront_row": "retail",
          "shanty_stack": "residential", "warehouse": "industrial", "shed": "industrial",
          "yard": "industrial", "parking_structure": "parking", "villa": "residential",
          "lab": "civic", "hangar": "transport", "perimeter": None}
FH_OF = {"parking_structure": 3.0, "warehouse": None, "shed": None, "hangar": None,
         "yard": None}


def program(archetype: str) -> Program:
    return PROGRAMS.get(archetype, PROGRAMS["midtown_mixed"])


# ---------------------------------------------------------------------------
# District context
# ---------------------------------------------------------------------------

class Noise:
    """Smooth value noise on a lattice (seeded values, bilinear with a smoothstep), plain
    arithmetic."""

    def __init__(self, rng, bounds, step: float = 160.0):
        x0, y0, x1, y1 = bounds
        self.x0, self.y0, self.step = x0 - step, y0 - step, step
        self.nx = int((x1 - x0) / step) + 4
        self.ny = int((y1 - y0) / step) + 4
        self.v = [[float(rng.random()) for _ in range(self.ny)] for _ in range(self.nx)]

    def __call__(self, x: float, y: float) -> float:
        fx = (x - self.x0) / self.step
        fy = (y - self.y0) / self.step
        i = min(max(int(math.floor(fx)), 0), self.nx - 2)
        j = min(max(int(math.floor(fy)), 0), self.ny - 2)
        tx = min(max(fx - i, 0.0), 1.0)
        ty = min(max(fy - j, 0.0), 1.0)
        tx = tx * tx * (3.0 - 2.0 * tx)
        ty = ty * ty * (3.0 - 2.0 * ty)
        a = self.v[i][j] + (self.v[i + 1][j] - self.v[i][j]) * tx
        b = self.v[i][j + 1] + (self.v[i + 1][j + 1] - self.v[i][j + 1]) * tx
        return a + (b - a) * ty


class Clear:
    """Clear zones of a district (junction polygons, road rights of way) for buildable areas."""

    def __init__(self, roads, junctions):
        polys = [G.qpoly(LineString(line).buffer(w / 2.0, cap_style="flat", join_style="mitre"))
                 for _, _, line, w, _ in roads] + list(junctions)
        self.polys = [p for p in polys if not p.is_empty]
        self.tree = shapely.STRtree(self.polys) if self.polys else None

    def near(self, poly) -> list:
        """Clear zones whose interior meets the polygon's interior (an exact predicate)."""
        if self.tree is None:
            return []
        ks = sorted(int(i) for i in self.tree.query(poly, predicate="intersects"))
        if not ks:
            return []
        arr = np.array([self.polys[k] for k in ks], dtype=object)
        hit = shapely.relate_pattern(poly, arr, "T********")
        return [self.polys[k] for k, h in zip(ks, hit.tolist()) if h]


@dataclass
class Ctx:
    did: str
    name: str
    archetype: str
    seed: int
    height: tuple[float, float]
    grime: float
    neon: float
    greenery: float
    skybridge_density: float
    polygon: object
    focus: tuple[float, float]
    radius: float
    lot_area: tuple[float, float]
    cones: list = field(default_factory=list)       # (polygon, height limit)
    complexes: tuple = ()
    landmarks: list = field(default_factory=list)
    roads: list = field(default_factory=list)       # (id, class, line, width, z max)
    junctions: list = field(default_factory=list)   # polygons
    water: list = field(default_factory=list)       # (id, polygon, clearance)
    opens: list = field(default_factory=list)       # (id, kind, polygon) landmark hosts
    block_opens: dict = field(default_factory=dict)  # block id -> [(open space id, polygon)]
    rings: list = field(default_factory=list)        # (ring info, rim plan) of wheels here
    notes: list = field(default_factory=list)
    noise: object = None
    clear: object = None
    axis: object = None      # boulevards (see `boulevards`)
    probe: bool = False      # M2 trying a merged group: masses only, no ground floor or roof

    @property
    def prog(self) -> Program:
        return program(self.archetype)

    def rng(self, *salt: int):
        return ST._rng(self.seed, 311, *salt)


AXIS_REACH_M = 90.0    # the boulevard ridge falls off to nothing this far from the boulevard
AXIS_NEAR = 0.35       # the boulevard passes within this share of the radius of the center
AXIS_LINE_M = 30.0     # its continuations stay this close to its line


def boulevards(cx: Ctx):
    """The district's boulevard: the avenue that passes nearest its center (within AXIS_NEAR
    of its radius) and the avenues that continue it in a straight line, as point lists, or
    None. Heights rise toward it (a skyline ridge along the axis)."""
    c = G.centroid(cx.polygon)
    aves = [list(line) for rid, cls, line, w, z in cx.roads
            if cls == "avenue" and len(line) >= 2 and LineString(line).intersects(cx.polygon)]
    if not aves:
        return None
    d0, k0 = min((MS.line_dist(c, pts)[0], k) for k, pts in enumerate(aves))
    if d0 > AXIS_NEAR * cx.radius:
        return None
    a, b = aves[k0][0], aves[k0][-1]
    L = ST._dist(a, b)
    if L < 1.0:
        return [aves[k0]]
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    out = []
    for pts in aves:
        # every vertex near the boulevard's line, and the piece running along it
        off = max(abs((x - a[0]) * uy - (y - a[1]) * ux) for x, y in pts)
        p, r = pts[0], pts[-1]
        Lp = ST._dist(p, r)
        along = Lp > 0 and abs(((r[0] - p[0]) * ux + (r[1] - p[1]) * uy) / Lp) >= 0.95
        if off <= AXIS_LINE_M and along:
            out.append(pts)
    return out or [aves[k0]]


CONE_SLOPE = 1.0   # clearance surface around a flight cone: 1 m up per 1 m away (45 degrees)


def height_cap(cones, p) -> float:
    """Height limit over p (a point or a polygon, measured at its nearest point) from the
    spaceport flight cones: the limit inside a cone's ground footprint, rising 1 m per 1 m
    away from it."""
    cap = math.inf
    g = Point(p) if isinstance(p, tuple) else p
    for poly, lim in cones:
        d = G.dist(poly, g)
        cap = min(cap, lim + d * CONE_SLOPE)
    return cap


def pick_height(cx: Ctx, p, area: float, front_cls: str, rng, lo_f: float = 0.0,
                hi_f: float = 1.0) -> float:
    """Height from the district height field, in the archetype range [lo, hi]."""
    lo, hi = cx.height
    wc, wn, ws, wa = cx.prog.field
    dx, dy = p[0] - cx.focus[0], p[1] - cx.focus[1]
    d = math.sqrt(dx * dx + dy * dy)
    fc = 1.0 - min(1.0, d / cx.radius) if cx.radius > 0 else 0.5
    fn = cx.noise(p[0], p[1])
    a0, a1 = cx.lot_area
    fs = min(1.0, max(0.0, (area - a0) / (a1 - a0))) if a1 > a0 else 0.5
    fa = 1.0 if front_cls == "avenue" else 0.4 if front_cls == "highway" else 0.0
    wx = cx.prog.axis
    fx = 0.0
    if wx > 0 and cx.axis is not None:
        d_ax = min(MS.line_dist(p, pts)[0] for pts in cx.axis)
        fx = max(0.0, 1.0 - d_ax / AXIS_REACH_M)
    f = wc * fc + wn * fn + ws * fs + wa * fa + wx * fx + 0.16 * (float(rng.random()) - 0.5)
    f = f / (wc + wn + ws + wa * 0.5 + wx * 0.4 + 0.02) if (wc + wn + ws + wa) > 0 else 0.5
    f = min(1.0, max(0.0, f))
    sk = cx.prog.skew
    if sk >= 1.95:
        f = f * f
    elif sk >= 1.45:
        f = f * math.sqrt(f)
    elif sk >= 1.15:
        f = math.sqrt(f * f * math.sqrt(f))  # about f ** 1.25
    f = lo_f + (hi_f - lo_f) * f
    return lo + (hi - lo) * f


def floors_in(h: float, fh: float, lo: float, hi: float, cap: float = math.inf,
              min_floors: int = 1) -> int:
    """Floor count for height h, kept within [lo, hi] and under cap."""
    top = min(hi, cap)
    n_hi = max(1, int(math.floor(top / fh + 1e-9)))
    n_lo = max(min_floors, int(math.ceil(lo / fh - 1e-9)))
    n = MS.floors_for(h, fh)
    return max(1, min(n_hi, max(n_lo, n)))


# ---------------------------------------------------------------------------
# Buildable area
# ---------------------------------------------------------------------------

def width_est(area: float, perim: float) -> float:
    """Width of a strip with this area and perimeter (exact measures in, plain arithmetic)."""
    if perim <= 0:
        return 0.0
    h = perim / 2.0
    disc = h * h - 4.0 * area
    return math.sqrt(area) if disc < 0 else (h - math.sqrt(disc)) / 2.0


def _street_part(r, fronts: list, prog: Program):
    """The largest part of r that lies on the street (within its setback + 3 m of a
    non-highway frontage), else the largest part."""
    ps = G.parts(r)
    if not ps:
        return None
    if len(ps) == 1:
        return ps[0]
    lines = [(LineString(f["line"]), prog.front.get(f["road_class"], 2.0))
             for f in fronts if len(f["line"]) >= 2 and f["road_class"] != "highway"]
    for p in ps:
        if any(G.dist(ln, p) <= sb + 3.0 for ln, sb in lines):
            return p
    return ps[0]


def buildable(lot_poly, fronts: list, prog: Program, side: float | None = None,
              extra: float = 0.0, clear=None):
    """Lot minus side setback and minus the frontage setback strips (largest part); minus the
    clear zones (junctions, rights of way) that M2 lots graze at some corners."""
    side = prog.side if side is None else side
    base = lot_poly
    if len(lot_poly.exterior.coords) > 9:
        base = MS.simplified(lot_poly, 0.25)
        base = G.inter(base, lot_poly) if not base.is_empty else lot_poly
        ps = G.parts(base)
        base = ps[0] if ps else lot_poly
    if clear is not None:
        hits = clear.near(base)
        if hits:
            base = G.diff(base, G.union(hits))
            ps = G.parts(base)
            if not ps:
                return Polygon()
            base = ps[0]
    cut = False
    if side > 0:
        w_est = width_est(G.area1(base), G.length1(base.exterior))
        if w_est - 2.0 * side < 8.0:
            side = max(0.0, (w_est - 8.0) / 2.0)
    r = MS.inset(base, side + extra) if side + extra > 0 else base
    if r.is_empty:
        return Polygon()
    cuts = []
    for f in fronts:
        sb = prog.front.get(f["road_class"], 2.0) + extra
        if sb > side + extra + 0.05 and len(f["line"]) >= 2:
            cuts.append(MS.strip_along(f["line"], sb))
    if cuts:
        r = G.diff(r, G.union(cuts))
        cut = True
    r = _street_part(r, fronts, prog)
    if r is None:
        return Polygon()
    if (not cut and side + extra <= 0) or len(r.exterior.coords) <= 7:
        return r   # the lot itself (M2 opened its blocks already), or a simple polygon
    # drop necks thinner than 2 m
    r2 = _street_part(G.opening(r, 1.0), fronts, prog)
    return r2 if r2 is not None else Polygon()


# ---------------------------------------------------------------------------
# Building record helpers
# ---------------------------------------------------------------------------

class Bld:
    """A building under construction."""

    def __init__(self, kind: str, use: str, fh: float, fr: MS.Frame):
        self.kind = kind
        self.use = use
        self.fh = fh
        self.fr = fr
        self.masses: list = []    # (poly, z0, z1, role, shape)
        self.roofs: list = []     # (poly, z, role) flat roofs for items and gardens
        self.attrs: dict = {}
        self.name = None
        self.landmark = False
        self.front_v = None       # local v of the street front (frontage line + setback)
        self.front_u = None       # local u range of the main frontage (plus a margin)
        self.front_line = None    # (line points, setback) of the main frontage

    def add(self, poly, z0: float, z1: float, role: str = "body", shape: str = "prism",
            roof: bool = True):
        if poly is None or poly.is_empty or z1 <= z0:
            return
        poly = G.parts(poly)[0] if poly.geom_type != "Polygon" else poly
        self.masses.append((poly, q(z0), q(z1), role, shape))
        if roof and shape == "prism":
            self.roofs.append((poly, q(z1), role))

    @property
    def height(self) -> float:
        return max(z1 for _, _, z1, _, _ in self.masses)

    def ground(self):
        key = tuple((id(p), z0) for p, z0, _, _, _ in self.masses)
        if getattr(self, "_gkey", None) == key:
            return self._ground
        self._gkey = key
        self._ground = self._ground_calc()
        return self._ground

    def _ground_calc(self):
        polys = [p for p, z0, _, _, _ in self.masses if z0 <= 0.0]
        if not polys:
            return Polygon()
        if len(polys) == 1:
            return polys[0]
        ps = G.parts(G.union(polys))
        return ps[0] if ps else Polygon()

    def top(self):
        """Roof of the tallest prism mass: (polygon, z)."""
        best = None
        for poly, z, role in self.roofs:
            if best is None or z > best[1]:
                best = (poly, z, role)
        return best


def _tier(fr, poly, d):
    """Polygon inset by d, or a smaller rectangle of it."""
    p = MS.inset(poly, d)
    return p if not p.is_empty and G.area1(p) > 30.0 else None


# ---------------------------------------------------------------------------
# Building archetypes (each fills a Bld inside `region`)
# ---------------------------------------------------------------------------

def podium_tower(b: Bld, region, H: float, cx: Ctx, rng, podium_floors: int | None = None,
                 front_cls: str = "street"):
    prog = cx.prog
    fh = b.fh
    lo_p, hi_p = prog.podium_floors
    npod = podium_floors if podium_floors is not None else \
        lo_p + int(float(rng.random()) * (hi_p - lo_p + 1))
    if front_cls == "avenue":
        npod += 1
    npod = max(1, min(npod, int(H / fh) - 3))
    P = npod * fh
    b.add(region, 0.0, P, "podium")
    t = tower_rect(b, region, cx, rng, 4.0)
    if t is None or H - P < 2 * fh:
        b.masses.clear()
        b.roofs.clear()
        if cx.archetype == "megablock_residential" and H - P >= 2 * fh:
            b.kind = "megabuilding"
            megabuilding(b, region, H, cx, rng)
            return
        b.add(region, 0.0, H, "body")
        b.kind = "tower" if H >= 40.0 else b.kind
        return
    tower_body(b, t, P, H, cx, rng)


def tower_rect(b: Bld, region, cx: Ctx, rng, setback: float):
    prog = cx.prog
    inner = MS.inset(region, setback)
    if inner.is_empty:
        return None
    MS.prep(inner)
    u0, v0, u1, v1 = b.fr.bounds(inner)
    W, D = u1 - u0, v1 - v0
    lo_s, hi_s = prog.tower_side
    target = math.sqrt(max(G.area1(region), 1.0) * prog.coverage)
    side = min(hi_s, max(lo_s, target * MS.uniform(rng, 0.85, 1.15)))
    w = min(W, side * MS.uniform(rng, 1.0, 1.45))
    d = min(D, side)
    if w < lo_s * 0.7 or d < lo_s * 0.7:
        return None
    found = MS.fit_rect_any(inner, b.fr, w, d, MS.anchors_of(inner, b.fr),
                            min_w=lo_s * 0.7, min_d=lo_s * 0.7)
    return found[0] if found else None


def tower_body(b: Bld, t, z0: float, H: float, cx: Ctx, rng, crown: float | None = None,
               spire: bool | None = None):
    """Tower shaft on `t` from z0 to H: setback crown tiers and a spire on some."""
    fh = b.fh
    lo, hi = cx.height
    u = float(rng.random())
    crown = (0.45 if cx.archetype in ("corporate_core", "transit_hub") else 0.25) \
        if crown is None else crown
    spire = (H > 0.75 * hi and H > 120.0 and float(rng.random()) < 0.5) if spire is None \
        else spire
    top = H
    sp_h = 0.0
    if spire:
        sp_h = q(min(H * 0.12, 40.0))
        top = H - sp_h
        top = z0 + max(2, int((top - z0) / fh)) * fh
        sp_h = H - top
    if u < crown and top - z0 > 10 * fh:
        n_cr = max(2, int((top - z0) / fh * MS.uniform(rng, 0.08, 0.16)))
        zc = top - n_cr * fh
        b.add(t, z0, zc, "tower")
        c = _tier(b.fr, t, MS.uniform(rng, 2.5, 4.5))
        if c is not None:
            b.add(c, zc, top, "crown")
        else:
            b.add(t, zc, top, "tower")
    else:
        b.add(t, z0, top, "tower")
    if sp_h > 2.0:
        cu, cv = b.fr.local(*G.centroid(t))
        s = b.fr.rect(cu - 1.5, cv - 1.5, cu + 1.5, cv + 1.5)
        b.add(s, top, top + sp_h, "spire", roof=False)


def slab(b: Bld, region, H: float, cx: Ctx, rng):
    MS.prep(region)
    u0, v0, u1, v1 = b.fr.bounds(region)
    D = v1 - v0
    depth = min(D, MS.uniform(rng, 14.0, 22.0))
    bar = MS.front_rect(region, b.fr, depth, min_w=8.0, min_d=8.0, v_front=b.front_v,
                        u_lim=b.front_u)
    if bar is None:
        bar = front_poly(b, region, depth)
    if bar is None:
        b.add(region, 0.0, H, "body")
        return
    b.add(bar, 0.0, H, "slab")
    # a second, lower bar at the back of deep lots
    if D > 2 * depth + 18.0:
        bu0, bv0, bu1, bv1 = b.fr.bounds(bar)
        back = G.inter(region, MS.halfplane(b.fr, v_min=bv1 + 16.0))
        ps = G.parts(back)
        if ps:
            r2 = MS.prep(ps[0])
            pu0, pv0, pu1, pv1 = b.fr.bounds(r2)
            found2 = MS.fit_rect(r2, b.fr, (pu1 - pu0) * 0.9, depth, (pu0 + pu1) / 2.0,
                                 pv1 - depth / 2.0 - 0.5, min_w=12.0, min_d=8.0)
            if found2 is not None:
                H2 = max(b.fh * 2, min(H, int(H * 0.75 / b.fh) * b.fh))
                fu0, fv0, fu1, fv1 = b.fr.bounds(found2)
                cu = (max(bu0, fu0) + min(bu1, fu1)) / 2.0
                wing = b.fr.rect(cu - 4.0, bv1 - 0.5, cu + 4.0, fv0 + 0.5)
                if min(bu1, fu1) - max(bu0, fu0) >= 10.0 and region.covers(wing):
                    b.add(found2, 0.0, H2, "slab")
                    b.add(wing, 0.0, 2 * b.fh, "wing")


def courtyard_block(b: Bld, region, H: float, cx: Ctx, rng, depth: float | None = None):
    depth = MS.uniform(rng, 11.0, 16.0) if depth is None else depth
    inner = MS.inset(region, depth)
    if inner.is_empty or G.area1(inner) < 80.0:
        b.add(region, 0.0, H, "body")
        return
    ring_ = G.diff(region, inner)
    ps = G.parts(ring_)
    if not ps or len(ps[0].interiors) == 0:
        b.add(region, 0.0, H, "body")
        return
    b.add(ps[0], 0.0, H, "body")
    b.attrs["courtyard_m2"] = q(G.area1(inner))


MEGA_GAP_M = 16.0        # least clear gap between two towers of a megabuilding
MEGA_SIDE_M = (30.0, 64.0)
MEGA_BAND_M = (24.0, 32.0)
MEGA_STEPS = (0.88, 0.72, 0.8, 0.64, 0.94)


def megabuilding(b: Bld, region, H: float, cx: Ctx, rng):
    """A podium (five to eight floors) with a court through it that opens to the sky, and
    separate towers on it at its corners and along its edges, at least 16 m apart: the
    tallest reaches H, the others step down (64 to 94% of it), each with a mid setback and
    a crown; open decks join neighboring towers across the gaps and the court."""
    fh = b.fh
    MS.prep(region)
    g = MEGA_GAP_M + 6.0 * float(rng.random())
    band = MS.uniform(rng, *MEGA_BAND_M)
    sv1 = MS.uniform(rng, 26.0, 36.0)
    front_row = float(rng.random()) < 0.6
    npod = 5 + int(float(rng.random()) * 4)
    npod = max(2, min(npod, int(H / fh) - 12))
    P = npod * fh
    lay = None
    # the lot frame first, then the frame of the region's own long side (curved lots)
    frames = (b.fr, MS.Frame(b.fr.ox, b.fr.oy, MS.obb_angle(region)))
    for single in (False, True):
        for fr in frames:
            lay = _mega_layout(fr, region, g, band, sv1, front_row, single)
            if lay is not None:
                break
        if lay is not None:
            break
    if lay is None:
        b.add(region, 0.0, H, "body")
        return
    fr, podium, court, towers = lay
    if len(towers) >= 4 and float(rng.random()) < 0.3:
        towers.pop(1 + int(float(rng.random()) * (len(towers) - 1)))   # a gap in the ring
    main = int(float(rng.random()) * len(towers))
    steps = list(MEGA_STEPS)
    k0 = int(float(rng.random()) * len(steps))
    steps = steps[k0:] + steps[:k0]
    b.add(podium, 0.0, P, "podium")
    tops = []
    for i, (t, _) in enumerate(towers):
        f = 1.0 if i == main else steps[(i - (i > main)) % len(steps)]
        n = max(npod + 10, int(H * f / fh + 1e-9))
        Hi = min(H, n * fh)
        _mega_tower(b, fr, t, P, Hi, rng)
        tops.append(Hi)
    _mega_decks(b, fr, region, towers, tops, P)
    b.attrs["towers"] = len(towers)
    if not court.is_empty:
        b.attrs["atrium_m2"] = q(G.area1(court))


def _mega_layout(fr, region, g: float, band: float, sv1: float, front_row: bool,
                 single: bool):
    """(frame, podium, court, towers) of a megabuilding in frame fr, or None when no tower
    fits: towers in one or two rows (front and back) of one to three, spread to the ends."""
    u0, v0, u1, v1 = fr.bounds(region)
    W, D = u1 - u0, v1 - v0
    s_lo, s_hi = MEGA_SIDE_M
    n_u = 1 if W < 2 * s_lo + g else 2 if W < 2 * s_hi + g + 0.6 * s_lo else 3
    n_v = 1 if D < 2 * band + g else 2
    # the court: what lies deeper than the tower band from every edge
    court = MS.inset(region, band + 2.0) if n_v == 2 else Polygon()
    podium = region
    if not court.is_empty and G.area1(court) >= 250.0:
        ps = G.parts(G.diff(region, court))
        if ps and len(ps[0].interiors) == 1:
            podium = ps[0]
        else:
            court = Polygon()
    else:
        court = Polygon()
    base = MS.inset(podium, 1.5)
    if base.is_empty:
        return None
    MS.prep(base)
    su = min(s_hi, (W - 3.0 - (n_u - 1) * g) / n_u)
    sv = min(band, D - 3.0) if n_v == 2 else min(sv1, D - 3.0)
    rows = (v0 + 1.5 + sv / 2.0, v1 - 1.5 - sv / 2.0) if n_v == 2 else \
        ((v0 + 1.5 + sv / 2.0) if front_row else (v1 - 1.5 - sv / 2.0),)
    cols = [(u0 + u1) / 2.0] if n_u == 1 else \
        [u0 + 1.5 + su / 2.0 + i * (W - 3.0 - su) / (n_u - 1) for i in range(n_u)]
    towers = []
    if su >= 16.0 and sv >= 14.0:
        for cv in rows:
            for cu in cols:
                t = MS.fit_rect(base, fr, su, sv, cu, cv, min_w=16.0, min_d=14.0)
                if t is None:
                    continue
                a = fr.bounds(t)
                if any(max(c[0] - a[2], a[0] - c[2], c[1] - a[3], a[1] - c[3]) < g - 0.5
                       for c in (fr.bounds(o) for o, _ in towers)):
                    continue
                towers.append((t, (cu, cv)))
    if not towers:
        if not single:
            return None
        found = MS.fit_rect_any(base, fr, min(W - 3.0, 40.0), min(D - 3.0, 26.0),
                                MS.anchors_of(base, fr), min_w=16.0, min_d=14.0)
        if found is None:
            return None
        towers = [found]
    return fr, podium, court, towers


def _mega_tower(b: Bld, fr, t, P: float, Hi: float, rng) -> None:
    """A tower on the podium with a mid setback (one or two sides) and a crown tier."""
    fh = b.fh
    rise = Hi - P
    zm = P + max(4, int(rise * MS.uniform(rng, 0.42, 0.66) / fh)) * fh
    zc = Hi - max(2, int(rise * MS.uniform(rng, 0.07, 0.14) / fh)) * fh
    tu0, tv0, tu1, tv1 = fr.bounds(t)
    d = MS.uniform(rng, 3.0, 6.0)
    k = int(float(rng.random()) * 4)
    cut = ((tu0 + d, tv0, tu1, tv1), (tu0, tv0 + d, tu1, tv1), (tu0, tv0, tu1 - d, tv1),
           (tu0 + d, tv0, tu1 - d, tv1))[k]
    upper = fr.rect(*cut) if (cut[2] - cut[0]) >= 12.0 and (cut[3] - cut[1]) >= 10.0 \
        else t
    if zm >= zc - fh:
        zm = zc
    b.add(t, P, zm, "tower")
    if zm < zc:
        b.add(upper, zm, zc, "tower")
    c = _tier(fr, upper, MS.uniform(rng, 2.5, 4.0))
    b.add(c if c is not None else upper, zc, Hi, "crown")


def _mega_decks(b: Bld, fr, region, towers, tops, P: float) -> None:
    """Open decks (6 m wide) across the gaps between neighboring towers, at one or two
    levels within the lower one's height."""
    fh = b.fh
    bx = [fr.bounds(t) for t, _ in towers]
    n = 0
    for i in range(len(towers)):
        for j in range(i + 1, len(towers)):
            a, c = bx[i], bx[j]
            lo_v, hi_v = max(a[1], c[1]), min(a[3], c[3])
            lo_u, hi_u = max(a[0], c[0]), min(a[2], c[2])
            if hi_v - lo_v >= 8.0 and (c[0] > a[2] or a[0] > c[2]):
                ua, ub = (a[2], c[0]) if c[0] > a[2] else (c[2], a[0])
                m = (lo_v + hi_v) / 2.0
                deck = fr.rect(ua - 0.3, m - 3.0, ub + 0.3, m + 3.0)
            elif hi_u - lo_u >= 8.0 and (c[1] > a[3] or a[1] > c[3]):
                va, vb = (a[3], c[1]) if c[1] > a[3] else (c[3], a[1])
                m = (lo_u + hi_u) / 2.0
                deck = fr.rect(m - 3.0, va - 0.3, m + 3.0, vb + 0.3)
            else:
                continue
            if not region.covers(deck) or any(
                    k not in (i, j) and G.area1(G.inter(deck, towers[k][0])) > 0.01
                    for k in range(len(towers))):
                continue
            top = min(tops[i], tops[j])
            levels = (0.38, 0.72) if top - P > 24 * fh else (0.5,)
            for f in levels:
                z = P + max(3, int((top - P) * f / fh)) * fh
                if z + 2.0 < top - fh:
                    b.add(deck, z, z + 2.0, "deck", roof=False)
                    n += 1
    if n:
        b.attrs["decks"] = n


def terraced(b: Bld, region, H: float, cx: Ctx, rng):
    """Stacked tiers stepping back from the street."""
    fh = b.fh
    n = 3 if H < 40 else 4 if H < 120 else 5
    u0, v0, u1, v1 = b.fr.bounds(region)
    D = v1 - v0
    step = min(D / (n + 1.5), MS.uniform(rng, 5.0, 9.0))
    floors = max(n, int(H / fh + 0.5))
    z = 0.0
    prev = None
    for i in range(n):
        cut = MS.halfplane(b.fr, v_min=v0 + i * step) if i else None
        p = region if cut is None else G.inter(region, cut)
        if i:
            p = MS.inset(p, 0.8 * i) if not MS.inset(p, 0.8 * i).is_empty else p
        ps = G.parts(p)
        if not ps or G.area1(ps[0]) < 40.0:
            break
        p = ps[0]
        if prev is not None and not prev.covers(p):
            p = G.parts(G.inter(p, prev))[0] if G.parts(G.inter(p, prev)) else None
            if p is None:
                break
        nf = floors // n + (1 if i < floors % n else 0)
        z1 = z + nf * fh
        if i == n - 1:
            z1 = floors * fh
        b.add(p, z, z1, "tier")
        prev = p
        z = z1
    if z < floors * fh and prev is not None:
        b.add(prev, z, floors * fh, "tier")


def perimeter(b: Bld, region, H: float, cx: Ctx, rng, fronts):
    """Perimeter-block building: the street wall to a depth of 14 to 20 m."""
    depth = MS.uniform(rng, 14.0, 20.0)
    strips = [MS.strip_along(f["line"], cx.prog.front.get(f["road_class"], 0.0) + depth)
              for f in fronts if f["road_class"] in ("avenue", "street", "pedestrian")]
    p = G.inter(region, G.union(strips)) if strips else region
    ps = G.parts(p)
    p = ps[0] if ps and G.area1(ps[0]) > 0.5 * G.area1(region) - 1e-9 or \
        (ps and G.area1(ps[0]) >= 60.0) else region
    if float(rng.random()) < 0.35 and H > 6 * b.fh:
        n_top = 2
        zt = H - n_top * b.fh
        b.add(p, 0.0, zt, "body")
        t = _top_setback(b, p, fronts, 2.5)
        b.add(t if t is not None else p, zt, H, "tier")
    else:
        b.add(p, 0.0, H, "body")


def _top_setback(b: Bld, p, fronts, d: float):
    cuts = [MS.strip_along(f["line"], d + 30.0) for f in fronts[:1]]
    if not cuts:
        return None
    # the top floors step back d from the frontage-side face of p
    u0, v0, u1, v1 = b.fr.bounds(p)
    t = G.inter(p, MS.halfplane(b.fr, v_min=v0 + d))
    ps = G.parts(t)
    return ps[0] if ps and G.area1(ps[0]) > 30.0 else None


def shopfront_row(b: Bld, region, H: float, cx: Ctx, rng, fronts):
    if float(rng.random()) < 0.3 and H >= 3 * b.fh:
        zt = H - b.fh
        b.add(region, 0.0, zt, "body")
        t = _top_setback(b, region, fronts, 1.5)
        b.add(t if t is not None else region, zt, H, "tier")
    else:
        b.add(region, 0.0, H, "body")


def shanty_stack(b: Bld, region, H: float, cx: Ctx, rng, fronts):
    """Irregular stacked boxes: a recessed ground floor (arcade), upper floors to the lot
    line, two or three blocks of different heights and a rooftop shack."""
    fh = b.fh
    u0, v0, u1, v1 = b.fr.bounds(region)
    W = u1 - u0
    ground = G.inter(region, MS.halfplane(b.fr, v_min=v0 + 1.2))
    gps = G.parts(ground)
    g = gps[0] if gps and G.area1(gps[0]) > 20.0 else region
    b.add(g, 0.0, fh, "body", roof=False)
    floors = max(2, int(H / fh + 0.5))
    hi = cx.height[1]
    k = 3 if W > 14.0 else 2
    cuts = sorted(u0 + W * (i + MS.uniform(rng, 0.3, 0.7)) / k for i in range(k - 1))
    edges = [u0 - 50.0] + cuts + [u1 + 50.0]
    parts = []
    for i in range(k):
        part = G.inter(region, MS.halfplane(b.fr, u_min=edges[i], u_max=edges[i + 1]))
        ps = G.parts(part)
        if ps and G.area1(ps[0]) >= 12.0:
            parts.append(ps[0])
    if not parts:
        parts = [region]
    big = max(range(len(parts)), key=lambda i: (G.area1(parts[i]), -i))
    tops = []
    for i, part in enumerate(parts):
        nf = floors if i == big else max(2, floors - int(float(rng.random()) * 3))
        b.add(part, fh, nf * fh, "stack")
        tops.append((part, nf * fh))
    p, z = max(tops, key=lambda t: (t[1], G.area1(t[0])))
    shack = MS.fit_rect(MS.prep(MS.inset(p, 0.8)) if not MS.inset(p, 0.8).is_empty else p,
                        b.fr, 4.0, 3.5, *b.fr.local(*G.centroid(p)))
    if shack is not None and float(rng.random()) < 0.6 and z + 2.6 <= hi:
        b.add(shack, z, z + 2.6, "shack")


REFIT_KINDS = ("warehouse", "hangar", "shed", "villa", "lab", "yard", "parking_structure",
               "slab", "terraced")
BOX_MAX = {"warehouse": (150.0, 100.0), "hangar": (120.0, 80.0), "shed": (80.0, 50.0),
           "villa": (30.0, 26.0), "lab": (90.0, 70.0), "yard": (30.0, 20.0),
           "parking_structure": (90.0, 60.0)}


def box(b: Bld, region, H: float, cx: Ctx, rng, cover: float, role: str = "body",
        front_gap: float = 0.0):
    """One rectangular volume covering about `cover` of the region (front aligned)."""
    MS.prep(region)
    u0, v0, u1, v1 = b.fr.bounds(region)
    D = v1 - v0
    s = math.sqrt(cover)
    wmax, dmax = BOX_MAX.get(b.kind, (1e9, 1e9))
    band = G.inter(region, MS.halfplane(b.fr, v_max=v0 + front_gap + D * s + 1.0))
    bp = G.parts(band)
    W = (b.fr.bounds(bp[0])[2] - b.fr.bounds(bp[0])[0]) if bp else u1 - u0
    r = MS.front_rect(region, b.fr, min(D * s, dmax), w_max=min(W * s * 1.05, wmax),
                      gaps=(front_gap + 0.1, front_gap + 1.0, front_gap + 3.0),
                      v_front=b.front_v, u_lim=b.front_u)
    if r is None:
        r = front_poly(b, region, max(min(D * s, dmax), 8.0))
    if r is None:
        b.add(region, 0.0, H, role)
        return region
    b.add(r, 0.0, H, role)
    return r


def warehouse(b: Bld, region, H: float, cx: Ctx, rng):
    r = box(b, region, H, cx, rng, MS.uniform(rng, 0.6, 0.85))
    b.attrs["docks"] = docks(b, r, region, rng)


def docks(b: Bld, body, region, rng) -> int:
    """Loading docks on the street face of a warehouse."""
    u0, v0, u1, v1 = b.fr.bounds(body)
    n = max(1, min(8, int((u1 - u0) / 12.0)))
    k = 0
    for i in range(n):
        cu = u0 + (u1 - u0) * (i + 0.5) / n
        d = b.fr.rect(cu - 2.0, v0 - 3.0, cu + 2.0, v0 + 0.0)
        if region.covers(d):
            b.add(d, 0.0, 1.2, "dock", roof=False)
            k += 1
    return k


def parking_structure(b: Bld, region, H: float, cx: Ctx, rng):
    r = box(b, region, H, cx, rng, 0.85, role="parking_deck")
    u0, v0, u1, v1 = b.fr.bounds(r)
    if u1 - u0 > 30.0:
        ps = G.parts(G.inter(b.fr.rect(u1 - 7.0, v0 + 1.0, u1 - 1.0, v1 - 1.0), r))
        if ps and G.area1(ps[0]) > 20.0:
            b.add(ps[0], 0.0, b.fh, "ramp", roof=False)
    b.attrs["levels"] = int(H / b.fh + 0.5)


def villa(b: Bld, region, H: float, cx: Ctx, rng):
    r = box(b, region, H, cx, rng, MS.uniform(rng, 0.45, 0.65), front_gap=1.0)
    if float(rng.random()) < 0.5 and H > 2 * b.fh:
        t = _tier(b.fr, r, 3.0)
        if t is not None:
            b.masses[-1] = (r, 0.0, q(H - b.fh), "body", "prism")
            b.roofs[-1] = (r, q(H - b.fh), "body")
            b.add(t, H - b.fh, H, "tier")


def lab(b: Bld, region, H: float, cx: Ctx, rng):
    r = box(b, region, H, cx, rng, MS.uniform(rng, 0.45, 0.7), front_gap=2.0)
    u0, v0, u1, v1 = b.fr.bounds(r)
    if u1 - u0 > 60.0 and v1 - v0 > 50.0:
        b.masses.pop()
        b.roofs.pop()
        courtyard_block(b, r, H, cx, rng, depth=14.0)


def hangar(b: Bld, region, H: float, cx: Ctx, rng):
    r = box(b, region, H, cx, rng, MS.uniform(rng, 0.6, 0.8))
    b.attrs["doors"] = 1 + int((b.fr.bounds(r)[2] - b.fr.bounds(r)[0]) / 40.0)


def shed(b: Bld, region, H: float, cx: Ctx, rng):
    box(b, region, H, cx, rng, MS.uniform(rng, 0.45, 0.7))
    b.attrs["open_sides"] = True


SHAPES = {"slab": slab, "courtyard_block": courtyard_block, "megabuilding": megabuilding,
          "terraced": terraced, "warehouse": warehouse, "parking_structure": parking_structure,
          "villa": villa, "lab": lab, "hangar": hangar, "shed": shed}


# ---------------------------------------------------------------------------
# One lot
# ---------------------------------------------------------------------------

def choose_kind(cx: Ctx, region, area: float, front_cls: str, rng) -> str:
    prog = cx.prog
    mix = list(prog.mix)
    a = G.area1(region)
    if cx.archetype == "megablock_residential" and a < 1800.0:
        mix = [(k, w) for k, w in mix if k != "megabuilding"]
    if cx.archetype == "corporate_core" and front_cls == "avenue":
        mix = [(k, w) for k, w in mix if k != "parking_structure"]
    if cx.archetype in ("entertainment_market",) and a < 350.0:
        mix = [(k, w) for k, w in mix if k != "podium_tower"]
    if cx.archetype == "old_town" and a < 220.0:
        mix = [(k, w) for k, w in mix if k != "courtyard_block"]
    if cx.archetype == "residential_heights" and a < 900.0:
        mix = [("villa", 1.0)]
    if cx.archetype == "midtown_mixed" and a < 900.0:
        mix = [(k, w) for k, w in mix if k != "podium_tower"]
    return MS.pick(rng, mix or prog.mix)


def heights_for(cx: Ctx, kind: str, p, area: float, front_cls: str, rng,
                region=None) -> tuple[float, float]:
    """(height, floor height) for a lot building."""
    prog = cx.prog
    lo, hi = cx.height
    fh = FH_OF.get(kind, prog.fh) if kind in FH_OF else prog.fh
    h = pick_height(cx, p, area, front_cls, rng)
    if kind == "parking_structure":
        h = min(h, MS.uniform(rng, 12.0, 24.0))
        lo = min(lo, 9.0)
    elif kind in ("slab", "courtyard_block") and cx.archetype == "corporate_core":
        h = lo + (h - lo) * 0.5
    elif kind == "terraced" and cx.archetype == "corporate_core":
        h = lo + (h - lo) * 0.7
    elif kind == "perimeter":
        h = lo + (h - lo) * 0.35
    elif kind in ("warehouse", "hangar", "shed", "yard"):
        top = {"warehouse": 16.0, "hangar": 30.0, "shed": 11.0, "yard": 10.0}[kind]
        h = min(max(lo, h), top) if kind != "hangar" else max(lo, min(h, top))
        if kind == "hangar" and hi >= 30.0:
            h = MS.uniform(rng, 16.0, 30.0)
        fh = q(h)
    elif kind == "villa":
        h = min(h, lo + (hi - lo) * 0.25)
    cap = height_cap(cx.cones, region) if region is not None else height_cap(cx.cones, p)
    if fh >= h - 1e-9 or kind in ("warehouse", "hangar", "shed", "yard"):
        hh = q(min(max(h, lo), hi, cap))
        return hh, hh
    n = floors_in(h, fh, lo, hi, cap)
    return q(n * fh), fh


def main_front(fronts: list) -> dict:
    """The frontage the facade sits on: frontage[0] (the longest), unless a frontage of a
    better road class (avenue, street, pedestrian street over alleys and service lanes) is at
    least half as long."""
    best = fronts[0]
    for f in fronts[1:]:
        if len(f["line"]) < 2:
            continue
        better = DOOR_RANK.get(f["road_class"], 9) < DOOR_RANK.get(best["road_class"], 9)
        if better and (f["length_m"] >= 0.5 * fronts[0]["length_m"] or
                       (best["road_class"] == "highway" and f["length_m"] >= 6.0)):
            best = f
    return best


def set_front(b: Bld, f: dict, prog: Program) -> None:
    """The street front of a building: the local v of its frontage's longest edge plus the
    setback."""
    line = f["line"]
    best = None
    for a, c in zip(line, line[1:]):
        dx, dy = c[0] - a[0], c[1] - a[1]
        L2 = dx * dx + dy * dy
        if best is None or L2 > best[0]:
            best = (L2, ((a[0] + c[0]) / 2.0, (a[1] + c[1]) / 2.0))
    sb = prog.front.get(f["road_class"], 2.0)
    if best is not None:
        b.front_v = b.fr.local(*best[1])[1] + max(sb, prog.side)
        us = [b.fr.local(x, y)[0] for x, y in line]
        b.front_u = (min(us) - 6.0, max(us) + 6.0)
    b.front_line = (line, max(sb, prog.side))


def front_poly(b: Bld, region, depth: float):
    """The region within `depth` of the street front (following the lot), or None."""
    if b.front_line is None:
        return None
    line, sb = b.front_line
    p = G.inter(region, MS.strip_along(line, sb + depth))
    ps = G.parts(p)
    return ps[0] if ps and G.area1(ps[0]) >= 40.0 else None


def lot_building(cx: Ctx, lot: dict, k: int, notes: list) -> Bld | None:
    rng = cx.rng(1, k)
    fronts = lot["frontage"]
    if not fronts:
        notes.append("lot without frontage left empty")
        return None
    prog = cx.prog
    poly = lot["polygon"]
    fr = MS.lot_frame(poly, main_front(fronts)["line"])
    front_cls = min((f["road_class"] for f in fronts), key=lambda c: RANK.get(c, 9))
    region = buildable(poly, fronts, prog, clear=cx.clear)
    if region.is_empty or G.area1(region) < MIN_FOOT_M2:
        region = buildable(poly, fronts, prog, side=0.0, extra=-100.0, clear=cx.clear)
        if region.is_empty or G.area1(region) < MIN_FOOT_M2:
            notes.append("lot too small or narrow for a building")
            return None
    kind = choose_kind(cx, region, lot["area_m2"], front_cls, rng)
    p = G.centroid(region)
    H, fh = heights_for(cx, kind, p, lot["area_m2"], front_cls, rng, region)
    for info, rim in cx.rings:
        ip = G.inter(region, rim) if region.intersects(rim) else Polygon()
        if not ip.is_empty:
            zb = MS.ring_zband(info, ip)
            if zb is not None and H > zb[0] - 2.0:
                notes.append("lot under a wheel rim left open")
                return None
    use = USE_OF.get(kind) or prog.use
    b = Bld(kind, use, fh, fr)
    set_front(b, main_front(fronts), prog)
    fill(b, kind, region, H, cx, rng, fronts, front_cls)
    if not b.masses:
        return None
    street = [f for f in fronts if f["road_class"] != "highway"]
    if kind in REFIT_KINDS and street and not any(
            r["road_class"] != "highway" for r in facades(b.ground(), fronts, prog)):
        # no facade on a street (curved frontage, a deep or odd lot): follow the frontage
        u0, v0, u1, v1 = fr.bounds(region)
        dmax = BOX_MAX.get(kind, (1e9, 30.0))[1]
        body = front_poly(b, region, min(max((v1 - v0) * 0.5, 10.0), dmax, 40.0))
        if body is not None:
            top = b.height
            b.masses.clear()
            b.roofs.clear()
            b.add(body, 0.0, top, "body")
    if kind == "yard":
        b.attrs["yard"] = True
    return b


def fill(b: Bld, kind: str, region, H: float, cx: Ctx, rng, fronts, front_cls: str):
    MS.prep(region)
    if kind == "podium_tower":
        podium_tower(b, region, H, cx, rng, front_cls=front_cls)
    elif kind == "perimeter":
        perimeter(b, region, H, cx, rng, fronts)
    elif kind == "shopfront_row":
        shopfront_row(b, region, H, cx, rng, fronts)
    elif kind == "shanty_stack":
        shanty_stack(b, region, H, cx, rng, fronts)
    elif kind == "yard":
        box(b, region, H, cx, rng, 0.12, role="office")
    else:
        SHAPES[kind](b, region, H, cx, rng)


# ---------------------------------------------------------------------------
# Facades, ground-floor units, entrances
# ---------------------------------------------------------------------------

def facades(foot, fronts: list, prog: Program) -> list[dict]:
    """Runs of footprint edges that face a frontage road (within its setback + 1.5 m and
    parallel to it): {pts, length, segment_id, road_class}."""
    if foot.is_empty:
        return []
    edges = MS.ring_edges(foot)
    tags = []
    for a, b in edges:
        L = ST._dist(a, b)
        tag = None
        if L >= 1.0:
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            ex, ey = MS.unit(b[0] - a[0], b[1] - a[1])
            best = None
            for f in fronts:
                line = f["line"]
                if len(line) < 2:
                    continue
                d, i = MS.line_dist(mid, line)
                sb = prog.front.get(f["road_class"], 2.0)
                if d > max(sb, prog.side) + FACADE_TOL_M:
                    continue
                ux, uy = MS.unit(line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1])
                if abs(ux * ey - uy * ex) > 0.26:
                    continue
                key = (RANK.get(f["road_class"], 9), round(d, 6), f["segment_id"])
                if best is None or key < best[0]:
                    best = (key, f)
            if best is not None:
                tag = best[1]
        tags.append(tag)
    # runs of consecutive edges with the same frontage (the ring wraps around)
    n = len(edges)
    if n == 0:
        return []
    start = 0
    for i in range(n):
        if tags[i] is None or tags[i - 1] is None or \
                tags[i]["segment_id"] != tags[i - 1]["segment_id"]:
            start = i
            break
    out = []
    run = None
    for k in range(n):
        i = (start + k) % n
        t = tags[i]
        a, b = edges[i]
        if t is not None and run is not None and run["segment_id"] == t["segment_id"]:
            run["pts"].append(b)
        else:
            if run is not None:
                out.append(run)
            run = None if t is None else {"pts": [a, b], "segment_id": t["segment_id"],
                                          "road_class": t["road_class"]}
    if run is not None:
        out.append(run)
    for r in out:
        r["length"] = ST._plen(r["pts"])
    return [r for r in out if r["length"] >= 2.0]


def _along(pts, s: float) -> tuple[float, float]:
    p, _ = ST._along(pts, s)
    return (q(p[0]), q(p[1]))


def ground_floor(b: Bld, cx: Ctx, fronts: list, rng, shops: bool | None = None) -> tuple:
    """(units, entrances) on the ground footprint."""
    prog = cx.prog
    foot = b.ground()
    runs = facades(foot, fronts, prog)
    units, ents = [], []
    shop_ok = prog.unit_w is not None and (float(rng.random()) < prog.unit_share
                                           if shops is None else shops)
    main = None
    if runs:
        main = min(runs, key=lambda r: (DOOR_RANK.get(r["road_class"], 9), -r["length"],
                                        r["segment_id"]))
    if main is not None:
        ents.append({"position": _along(main["pts"], main["length"] / 2.0), "kind": "main",
                     "segment_id": main["segment_id"]})
    else:
        f = main_front(fronts)
        line = LineString(f["line"])
        p = G.nearest(foot.exterior, line.interpolate(0.5, normalized=True))
        ents.append({"position": p, "kind": "main", "segment_id": f["segment_id"]})
    for r in runs:
        if r["road_class"] in SERVICE_CLASSES and r is not main:
            ents.append({"position": _along(r["pts"], r["length"] / 2.0), "kind": "service",
                         "segment_id": r["segment_id"]})
            break
    if b.kind in ("warehouse", "hangar", "shed", "yard") and main is not None:
        ents.append({"position": _along(main["pts"], main["length"] * 0.25),
                     "kind": "loading", "segment_id": main["segment_id"]})
    if b.kind == "parking_structure" and main is not None:
        ents.append({"position": _along(main["pts"], main["length"] * 0.8),
                     "kind": "garage", "segment_id": main["segment_id"]})
    if not shop_ok or b.kind in ("parking_structure", "villa", "warehouse", "shed", "hangar",
                                 "yard", "lab"):
        return units, ents
    w_lo, w_hi = prog.unit_w
    p_aw, aw_lo, aw_hi = prog.awning
    for r in runs:
        if r["road_class"] not in SHOP_CLASSES:
            continue
        L = r["length"]
        if L < w_lo:
            continue
        n = int(math.ceil(L / w_hi - 1e-9))
        if L / n < w_lo:
            n2 = int(math.floor(L / w_lo))
            if n2 >= 1 and L / n2 <= UNIT_MAX_M:
                n = n2
        w = L / n
        if w < UNIT_MIN_M:
            continue
        mid_i = n // 2 if r is main else -1
        for i in range(n):
            a = _along(r["pts"], i * w)
            c = _along(r["pts"], (i + 1) * w)
            e = _along(r["pts"], (i + 0.5) * w)
            use = "lobby" if (i == mid_i and prog.lobby and b.kind not in
                              ("shopfront_row", "shanty_stack")) else MS.pick(rng,
                                                                             prog.unit_uses)
            aw = q(MS.uniform(rng, aw_lo, aw_hi)) if float(rng.random()) < p_aw else 0.0
            sign = float(rng.random()) < prog.sign * (0.5 + cx.neon)
            units.append({"edge": (a, c), "use": use, "entrance": e, "width_m": q(w),
                          "segment_id": r["segment_id"], "awning_m": aw, "sign": sign})
    return units, ents


# ---------------------------------------------------------------------------
# Rooftops
# ---------------------------------------------------------------------------

def _item(b: Bld, roof, z: float, kind: str, cu: float, cv: float, su: float, sv: float,
          sz: float, fr: MS.Frame | None = None) -> dict | None:
    fr = fr or b.fr
    r = fr.rect(cu - su / 2.0, cv - sv / 2.0, cu + su / 2.0, cv + sv / 2.0)
    if not roof.covers(r):
        return None
    x, y = fr.world(cu, cv)
    return {"kind": kind, "position": (x, y, q(z)), "size": (q(su), q(sv), q(sz)),
            "yaw_deg": fr.yaw_deg()}


def rooftop(b: Bld, cx: Ctx, rng) -> list[dict]:
    prog = cx.prog
    items = []
    top = b.top()
    if top is None:
        return items
    roof, z, role = top
    MS.prep(roof)
    u0, v0, u1, v1 = b.fr.bounds(roof)
    W, D = u1 - u0, v1 - v0
    cu, cv = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    kinds = prog.roof
    H = b.height
    pad = None
    if "helipad" in kinds and z >= 150.0 and W >= 24.0 and D >= 24.0 and \
            float(rng.random()) < 0.7:
        pad = _item(b, roof, z, "helipad", cu, cv, 20.0, 20.0, 0.6)
    elif "av_pad" in kinds and z >= 50.0 and W >= 18.0 and D >= 18.0 and \
            float(rng.random()) < 0.45:
        pad = _item(b, roof, z, "av_pad", cu, cv, 14.0, 14.0, 0.5)
    if pad is not None:
        items.append(pad)
    elif "mechanical" in kinds and z >= 25.0 and W >= 10.0 and D >= 10.0:
        it = _item(b, roof, z, "mechanical", cu, cv + D * 0.1, W * 0.4, D * 0.35,
                   4.0 if z < 100 else 6.0)
        if it:
            items.append(it)
    if "antenna" in kinds and (H >= 40.0 or cx.archetype == "old_town") and \
            float(rng.random()) < 0.35:
        it = _item(b, roof, z, "antenna", u1 - 2.0, v1 - 2.0, 0.6, 0.6,
                   q(MS.uniform(rng, 4.0, 14.0)))
        if it:
            items.append(it)
    if "water_tank" in kinds and float(rng.random()) < 0.5:
        it = _item(b, roof, z, "water_tank", u0 + 2.2, v1 - 2.2, 3.0, 3.0, 3.5)
        if it:
            items.append(it)
    if "billboard" in kinds and H <= 90.0 and float(rng.random()) < cx.neon * 0.7:
        bw = min(W * 0.7, 16.0)
        if bw >= 4.0:
            it = _item(b, roof, z, "billboard", cu, v0 + 1.0, bw, 0.6,
                       q(MS.uniform(rng, 3.0, 7.0)))
            if it:
                items.append(it)
    if "ac_unit" in kinds:
        n = int(MS.uniform(rng, 1.0, 5.0))
        for i in range(n):
            au = u0 + 2.0 + (W - 4.0) * (i + 0.5) / max(n, 1)
            it = _item(b, roof, z, "ac_unit", au, v1 - 2.0, 1.6, 1.2, 1.2)
            if it:
                items.append(it)
    # podium roof: AC units in front of the tower
    pods = [(p, zz) for p, zz, rl in b.roofs if rl == "podium"]
    if pods and "ac_unit" in kinds:
        p, zz = pods[0]
        pu0, pv0, pu1, pv1 = b.fr.bounds(p)
        for i in range(2):
            it = _item(b, MS.prep(p), zz, "ac_unit", pu0 + 3.0 + i * 3.0, pv0 + 2.5, 1.6,
                       1.2, 1.2)
            if it and not any(_overlap(it, m, b) for m in b.masses if m[1] >= zz):
                items.append(it)
    return items


def _overlap(it, mass, b) -> bool:
    poly = mass[0]
    x, y, _ = it["position"]
    return poly.intersects(shapely.box(x - 1.5, y - 1.5, x + 1.5, y + 1.5))


def green_roofs(b: Bld, cx: Ctx, rng) -> list[dict]:
    """Podium roofs and low flat roofs as green roofs or roof plazas."""
    out = []
    chance = cx.prog.green * cx.greenery
    pods = [(p, z) for p, z, rl in b.roofs if rl == "podium"]
    for p, z in pods[:1]:
        above = [m[0] for m in b.masses if m[1] >= z - 1e-9 and m[3] != "podium"]
        free = G.diff(p, G.union([G.qpoly(a.buffer(1.5, join_style="mitre"))
                                  for a in above])) if above else p
        ps = G.parts(free)
        if ps and G.area1(ps[0]) >= 150.0 and float(rng.random()) < chance + 0.25:
            use = "roof_plaza" if cx.archetype in ("corporate_core", "transit_hub") else \
                "roof_garden"
            out.append({"polygon": ps[0], "z_m": z, "use": use})
    if not pods and b.kind in ("villa", "lab", "courtyard_block", "terraced", "perimeter",
                               "slab") and b.height <= 60.0 and float(rng.random()) < chance:
        top = b.top()
        if top is not None:
            g = MS.inset(top[0], 1.0)
            if not g.is_empty and G.area1(g) >= 60.0:
                out.append({"polygon": g, "z_m": top[1], "use": "roof_garden"})
    return out


def style(cx: Ctx, rng) -> dict:
    era = {"old_town": "heritage", "entertainment_market": "neon_retro",
           "industrial_port": "industrial", "corporate_core": "corporate_glass",
           "megablock_residential": "brutalist", "research_campus": "clean_tech",
           "residential_heights": "suburban_modern", "transit_hub": "transit_modern",
           "midtown_mixed": "mixed_modern", "spaceport": "aerospace"}.get(cx.archetype,
                                                                       "modern")
    j = 0.12
    g = min(1.0, max(0.0, cx.grime + j * (float(rng.random()) - 0.5) * 2))
    n = min(1.0, max(0.0, cx.neon + j * (float(rng.random()) - 0.5) * 2))
    return {"grime": q(g), "neon": q(n), "era": era}


def finish(b: Bld, cx: Ctx, fronts: list, rng, shops: bool | None = None) -> dict:
    """Ground floor, rooftop and style of a finished building (record without ids)."""
    units, ents = ground_floor(b, cx, fronts, rng, shops)
    items = rooftop(b, cx, rng)
    greens = green_roofs(b, cx, rng)
    H = b.height
    body_top = max((z1 for _, _, z1, role, _ in b.masses if role != "spire"), default=H)
    return {"kind": b.kind, "use": b.use, "fh": b.fh, "floors": max(1, int(body_top / b.fh +
                                                                           0.5)),
            "height": q(H), "masses": b.masses, "footprint": b.ground(), "entrances": ents,
            "units": units, "roof_items": items, "greens": greens, "style": style(cx, rng),
            "attrs": dict(b.attrs), "frame": (b.fr.ox, b.fr.oy, b.fr.angle),
            "name": b.name, "landmark": b.landmark}


# ---------------------------------------------------------------------------
# District job (runs in a worker process)
# ---------------------------------------------------------------------------

def _prepare(cx: Ctx) -> Ctx:
    cx.noise = Noise(cx.rng(0), cx.polygon.bounds)
    cx.clear = Clear(cx.roads, cx.junctions)
    cx.axis = boulevards(cx) if cx.prog.axis > 0 else None
    return cx


def phase_a(job: dict) -> dict:
    """Landmarks (whole blocks near the district focus) and complexes (merged lot groups)."""
    from . import complexes as CX

    with G.canonical():
        cx = _prepare(job["ctx"])
        out = {"buildings": [], "properties": [], "structures": [], "elements": [],
               "forced": []}
        used: set = set()
        CX.landmarks(cx, job["lots"], used, out)
        CX.complexes(cx, job["lots"], used, out)
        res = _rows_and_sky(out, cx.did)
        res.update({"used": sorted(used), "notes": list(cx.notes), "rings": cx.rings,
                    "focus": cx.focus, "forced": out["forced"]})
        return res


def phase_b(job: dict) -> dict:
    """One building per remaining lot of a chunk (lot k of the district draws from its own
    generator, so chunks do not change the result)."""
    import time

    from . import complexes as CX

    t0 = time.perf_counter()
    with G.canonical():
        cx = _prepare(job["ctx"])
        used = set(job["used"])
        notes: list = []
        out = {"buildings": [], "properties": [], "elements": [], "notes": notes}
        for k, lot in job["lots"]:
            if lot["id"] in used:
                continue
            b = lot_building(cx, lot, k, notes)
            if b is None:
                continue
            rec = finish(b, cx, lot["frontage"], cx.rng(2, k))
            bid = f"{lot['id']}.bld"
            rec.update({"id": bid, "lot_id": lot["id"], "property_id": f"{lot['id']}.prop",
                        "lot_ids": [lot["id"]]})
            out["buildings"].append(rec)
            out["properties"].append({"id": f"{lot['id']}.prop", "complex": "single",
                                      "building_ids": [bid], "lot_ids": [lot["id"]],
                                      "owner": owner(cx, k)})
            if b.kind == "yard":
                out["elements"] += CX.yard_stacks(cx, lot, b, cx.rng(3, k))
        res = _rows_and_sky(out, cx.did)
        res["notes"] = notes + cx.notes
        res["seconds"] = time.perf_counter() - t0
        return res


def _rows_and_sky(out: dict, did: str) -> dict:
    """Model rows of a job's buildings, plus what the skybridge phase needs of them."""
    from .model import COLLECTIONS

    for rec in out["buildings"]:
        rec["district_id"] = did
    res = to_rows(out, did)
    for key in ("buildings", "properties", "site_elements", "structures", "green_areas"):
        res[key] = [COLLECTIONS[key].model_validate(r) for r in res[key]]
    res["sky"] = [{"id": r["id"], "fh": r["fh"], "height": r["height"],
                   "masses": r["masses"], "property_id": r.get("property_id"),
                   "landmark": r.get("landmark", False)} for r in out["buildings"]]
    res["trace"] = [[x["id"], x["kind"], x["height"], [(m[0], m[1], m[2]) for m in x["masses"]]]
                    for x in out["buildings"]]
    return res


def phase_c(job: dict) -> dict:
    """Skybridges of a district (rows)."""
    from . import skybridges as SB

    with G.canonical():
        cx = _prepare(job["ctx"])
        out = {"buildings": sorted(job["sky"], key=lambda r: r["id"]),
               "forced": job["forced"]}
        SB.district_skybridges(cx, out)
        rows = to_rows({"buildings": [], "properties": [],
                        "skybridges": out["skybridges"]}, cx.did)
        return {"skybridges": rows["skybridges"], "notes": list(cx.notes),
                "trace": [[x["id"], x["line"], x["z_m"]] for x in out["skybridges"]]}


# ---------------------------------------------------------------------------
# Model rows (shapely to model dicts; workers do this for their districts)
# ---------------------------------------------------------------------------

def _mass_rows(masses) -> list:
    P = G.to_model_poly
    return [{"footprint": P(p), "z0_m": z0, "z1_m": z1, "role": role, "shape": shape}
            for p, z0, z1, role, shape in masses]


def building_row(r: dict) -> dict:
    return {
        "id": r["id"], "type": f"building.{r['kind']}", "name": r.get("name"),
        "lot_id": r.get("lot_id"), "property_id": r.get("property_id"),
        "district_id": r.get("district_id"), "megasite_id": r.get("megasite_id"),
        "use": r["use"], "floor_height_m": G.q(r["fh"]), "floors": r["floors"],
        "height_m": r["height"],
        "footprint": G.to_model_poly(r["footprint"]) if not r["footprint"].is_empty else None,
        "masses": _mass_rows(r["masses"]), "entrances": r["entrances"], "units": r["units"],
        "roof_items": r["roof_items"], "landmark": bool(r.get("landmark")),
        "style": r["style"], "attrs": {k: v for k, v in r["attrs"].items() if v is not None}}


def to_rows(out: dict, did: str | None) -> dict:
    P = G.to_model_poly
    blds = [building_row(r) for r in sorted(out["buildings"], key=lambda r: r["id"])]
    props = [{"id": p["id"], "type": f"property.{p['complex']}", "owner": p["owner"],
              "complex": p["complex"], "building_ids": p["building_ids"],
              "district_id": p.get("district_id", did), "lot_ids": p["lot_ids"],
              "name": p.get("name")} for p in sorted(out["properties"], key=lambda p: p["id"])]
    sbs = [{"id": s["id"], "type": f"skybridge.{s['kind']}", "building_ids": s["building_ids"],
            "line": s["line"], "z_m": s["z_m"], "width_m": s["width_m"], "levels": s["levels"],
            "level_height_m": s["level_height_m"], "kind": s["kind"],
            "length_m": s["length_m"], "clearance_m": s["clearance_m"],
            "crosses": s["crosses"], "walkway_ids": [], "property_id": s.get("property_id")}
           for s in out.get("skybridges", [])]
    els = [{"id": e["id"], "type": f"site_element.{e['kind']}", "kind": e["kind"],
            "megasite_id": e.get("megasite_id"), "lot_id": e.get("lot_id"),
            "footprint": P(e["footprint"]) if e.get("footprint") is not None else None,
            "line": e.get("line", []), "z_m": e.get("z_m", 0.0),
            "masses": _mass_rows(e.get("masses", [])), "attrs": e.get("attrs", {})}
           for e in sorted(out.get("elements", []), key=lambda e: e["id"])]
    sts = []
    for s in sorted(out.get("structures", []), key=lambda s: s["id"]):
        sts.append({"id": s["id"], "type": f"structure.{s['kind']}", "kind": s["kind"],
                    "footprint": P(s["footprint"]) if s.get("footprint") is not None else None,
                    "line": [(x, y, s["z1_m"]) for x, y in s.get("line", [])],
                    "z0_m": s["z0_m"], "z1_m": s["z1_m"], "supports": s.get("supports", []),
                    "attrs": s.get("attrs", {})})
    gas = []
    for r in sorted(out["buildings"], key=lambda r: r["id"]):
        for i, g in enumerate(r.get("greens", [])):
            gas.append({"id": f"{r['id']}.gr{i + 1}", "type": "green_area.green_roof",
                        "kind": "green_roof", "polygon": P(g["polygon"]), "z_m": g["z_m"],
                        "building_id": r["id"],
                        "attrs": {"use": g["use"], "area_m2": G.q(G.area1(g["polygon"]))}})
    return {"buildings": blds, "properties": props, "skybridges": sbs, "site_elements": els,
            "structures": sts, "green_areas": gas}


OWNERS = ("kaze_holdings", "mirai_dynamics", "helios_group", "sable_systems", "tessera",
          "aurum_bank", "nyx_mutual", "lumen_bio", "halcyon", "zenith_aero", "orbis_logistics",
          "vanta_media")


def owner(cx: Ctx, k: int) -> str:
    if cx.archetype in ("corporate_core", "research_campus", "spaceport", "transit_hub"):
        rng = cx.rng(9, k)
        return OWNERS[int(float(rng.random()) * len(OWNERS))]
    return f"{cx.did}_private_{k:04d}"
