"""Stage 5, the local street network: streets, alleys, pedestrian streets, service lanes,
waterfront promenades and footbridges, laid inside the primary network of M1b.

Each district is filled by its archetype (scope 4.4):

- rotated or plain grids at the district grid angle (corporate core 45 degrees), with block
  sizes from the archetype range and a few through alleys;
- superblocks with internal U-shaped service lanes (megablock residential);
- a grid plus a ring around the central park (midtown);
- dense organic networks grown from the district edge, with dead ends and alleys (old town,
  entertainment market): a growth process in the spirit of Parish and Mueller 2001, steered by
  a cross field that rotates slowly with noise and turns parallel to the banks near canals
  and rivers (Chen et al. 2008), so streets bend around the water;
- large grids with long, rail-ready blocks along the main axis (industrial port);
- curvilinear loops at lot depth inside each cell, with connectors and cul-de-sacs
  (residential heights);
- a campus loop around a landscaped core, with service drives (research campus);
- radial and ring streets around the station (transit hub);
- service roads around megasite reserves, joined to the M1b dead ends at the reserve gates.

Shared frame first: service rings around reserves, streets on the land boundaries between
districts, and waterfront promenades (pedestrian streets 5 m from the water along quays,
canals, rivers and the sea). Then every district is split into cells by the primary roads and
the frame; each cell is filled by its pattern; alleys and service lanes split large blocks;
footbridges cross canals and separation channels every 150 to 300 m.

Local streets meet the network only where a junction is allowed: never on a highway, never on
a bridge or within its approach ramps, never within 30 m of a primary junction, at least
`MIN_JUNCTION_GAP_M` from another junction (closer ones are merged), and at no less than the
district's minimum junction angle (60 degrees in grids, 35 in organic districts). Streets
never cross water; pedestrians do, on footbridges.

Determinism: every coordinate is on the 0.01 m grid, decisions use exact integer predicates
(noding) or plain IEEE arithmetic on grid values (no fused operations in Python), angles come
from `dmath`, the random numbers from per-district seeds (uniform draws only), and every GEOS
output is snapped before anything measures or compares it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import trace as T
from .spec import CitySpec

SCALE = 100  # grid units (cm) per meter

# ---------------------------------------------------------------------------
# Cross-sections (scope 5.1) and archetype styles (scope 4.4)
# ---------------------------------------------------------------------------

VEHICLE = ("highway", "avenue", "street", "alley", "service")
PEDESTRIAN = ("pedestrian", "footbridge")
LOCAL = ("street", "alley", "service", "pedestrian", "footbridge")
PRIMARY = ("highway", "avenue")
RANK = {"highway": 5, "avenue": 4, "street": 3, "service": 2, "alley": 1, "pedestrian": 0,
        "footbridge": 0}


def section(lanes=(1, 1), lane=3.2, parking=(False, False), sidewalk=0.0, furniture=0.0,
            median=0.0, park_w=2.3, curb=0.15, shared=False) -> dict:
    """A cross-section: total width from lanes, parking, median and sidewalks."""
    total = (lanes[0] + lanes[1]) * lane + sum(parking) * park_w + median + 2 * sidewalk
    return {"total_width_m": G.q(total), "lane_width_m": lane, "lanes_forward": lanes[0],
            "lanes_backward": lanes[1], "median_m": median,
            "sidewalk_m": (sidewalk, sidewalk), "parking": tuple(parking), "curb_m": curb,
            "furniture_m": furniture, "shared": shared}


@dataclass(frozen=True)
class Style:
    pattern: str
    organic: bool
    street: dict
    narrow: dict | None = None      # one-way variant of the street (same total width)
    alley_w: float = 5.0
    alley_rate: float = 0.0         # share of large blocks that get an alley
    promenade: bool = True
    radius: float = 6.0             # street corner (curb return) radius
    lot_area: tuple[float, float] = (300.0, 2000.0)
    frontage: tuple[float, float] = (10.0, 30.0)
    lot_depth: tuple[float, float] = (25.0, 45.0)
    perimeter: bool = False         # strip (perimeter block) lots with courtyards
    open_share: tuple[float, float] = (0.05, 0.2)
    ped_w: float = 8.0


STYLES: dict[str, Style] = {
    "corporate_core": Style(
        "rotated_grid", False,
        section((1, 1), 3.3, (True, True), 4.0, 1.2), alley_w=6.0, alley_rate=0.2, radius=8.0,
        lot_area=(1200.0, 9000.0), frontage=(30.0, 90.0), lot_depth=(40.0, 80.0),
        open_share=(0.06, 0.24), ped_w=12.0),
    "megablock_residential": Style(
        "superblocks", False,
        section((1, 1), 3.2, (False, True), 3.0, 0.8), alley_w=7.0, alley_rate=1.0, radius=7.0,
        lot_area=(2500.0, 22000.0), frontage=(40.0, 140.0), lot_depth=(45.0, 90.0),
        open_share=(0.04, 0.22), ped_w=10.0),
    "midtown_mixed": Style(
        "grid_ring_park", False,
        section((1, 1), 3.2, (True, True), 3.5, 1.0), alley_w=5.0, alley_rate=0.25,
        radius=7.0, lot_area=(350.0, 3200.0), frontage=(14.0, 45.0), lot_depth=(22.0, 45.0),
        perimeter=True, open_share=(0.06, 0.40), ped_w=10.0),
    "entertainment_market": Style(
        "organic", True,
        section((1, 1), 3.0, (False, False), 2.5, 0.5),
        narrow=section((1, 0), 3.5, (True, False), 2.5, 0.5, park_w=2.5),
        alley_w=4.5, alley_rate=0.75, radius=5.0, lot_area=(70.0, 900.0),
        frontage=(5.0, 16.0), lot_depth=(12.0, 30.0), perimeter=True,
        open_share=(0.02, 0.16), ped_w=8.0),
    "old_town": Style(
        "organic", True,
        section((1, 1), 2.9, (False, False), 2.1, 0.15),
        narrow=section((1, 0), 3.5, (True, False), 2.1, 0.15),
        alley_w=4.0, alley_rate=0.85, radius=4.0, lot_area=(45.0, 650.0),
        frontage=(4.0, 12.0), lot_depth=(10.0, 24.0), perimeter=True,
        open_share=(0.02, 0.16), ped_w=6.0),
    "industrial_port": Style(
        "large_grid", False,
        section((1, 1), 3.6, (False, True), 2.0, 0.0, park_w=2.5), alley_w=6.0,
        alley_rate=0.15, promenade=False, radius=15.0, lot_area=(2500.0, 36000.0),
        frontage=(40.0, 160.0), lot_depth=(50.0, 140.0), open_share=(0.0, 0.10)),
    "residential_heights": Style(
        "curvilinear", False,
        section((1, 1), 3.0, (False, True), 2.5, 0.5, park_w=2.2), alley_w=5.0, radius=7.0,
        lot_area=(350.0, 2600.0), frontage=(14.0, 40.0), lot_depth=(25.0, 50.0),
        open_share=(0.08, 0.40), ped_w=6.0),
    "research_campus": Style(
        "campus_loops", False,
        section((1, 1), 3.2, (False, False), 3.0, 0.8), alley_w=6.0, radius=7.0,
        lot_area=(1500.0, 20000.0), frontage=(30.0, 140.0), lot_depth=(40.0, 90.0),
        open_share=(0.15, 0.55), ped_w=8.0),
    "transit_hub": Style(
        "radial_ring", False,
        section((1, 1), 3.3, (True, True), 4.0, 1.2), alley_w=6.0, alley_rate=0.2, radius=8.0,
        lot_area=(500.0, 6500.0), frontage=(18.0, 70.0), lot_depth=(28.0, 60.0),
        open_share=(0.03, 0.25), ped_w=12.0),
    "spaceport": Style(
        "service_roads", False,
        section((1, 1), 3.6, (False, False), 2.0, 0.0), alley_w=7.0, promenade=False,
        radius=12.0, lot_area=(3000.0, 45000.0), frontage=(40.0, 220.0),
        lot_depth=(60.0, 160.0), open_share=(0.0, 0.5)),
}
ORGANIC_ANGLE_DEG = 35.0
GRID_ANGLE_DEG = 60.0
SERVICE = section((1, 1), 3.25, (False, False), 0.0, 0.0, median=0.5, curb=0.15)
PROMENADE_W = 10.0
PROMENADE_OFFSET_M = 5.0
FOOTBRIDGE_W = 4.0
FOOTBRIDGE_STEP_M = (150.0, 280.0)
FOOTBRIDGE_MAX_SPAN_M = 70.0
MIN_JUNCTION_GAP_M = 20.0     # local junctions along a road (closer ones are merged)
PRIMARY_NODE_GAP_M = 30.0     # no local junction this close to a primary node
RESERVE_RING_M = 12.0
QUAY_ROAD_OFFSET_M = 16.0
FRONTAGE_VERGE_M = 5.0        # landscaped strip between a highway and its frontage street     # port quay roads: an apron for cranes between road and water         # service ring centerline from a megasite reserve
CLOSED_PAD_M = 4.0


def street_class(seg) -> str:
    """The class a road has at street level: a traced highway is at grade (no ramps were
    drawn), with sidewalks, crosswalks and junctions like an avenue."""
    attrs = seg["attrs"] if isinstance(seg, dict) else seg.attrs
    cls = seg["road_class"] if isinstance(seg, dict) else seg.road_class
    return "avenue" if cls == "highway" and "pinned" in attrs else cls


def style_of(archetype: str) -> Style:
    return STYLES.get(archetype, STYLES["midtown_mixed"])


def min_angle(archetype: str) -> float:
    return ORGANIC_ANGLE_DEG if style_of(archetype).organic else GRID_ANGLE_DEG


def cross_section(cls: str, archetype: str | None, narrow: bool = False) -> dict:
    st = style_of(archetype or "midtown_mixed")
    if cls == "street":
        return dict(st.narrow if narrow and st.narrow else st.street)
    if cls == "alley":
        return section((1, 0), st.alley_w, curb=0.0, shared=True)
    if cls == "service":
        return dict(SERVICE)
    if cls == "pedestrian":
        w = st.ped_w
        return {**section((0, 0), 0.0, curb=0.0), "total_width_m": w,
                "sidewalk_m": (w / 2, w / 2)}
    if cls == "footbridge":
        return {**section((0, 0), 0.0, curb=0.0), "total_width_m": FOOTBRIDGE_W,
                "sidewalk_m": (FOOTBRIDGE_W / 2, FOOTBRIDGE_W / 2)}
    raise ValueError(cls)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class Line:
    pts: list[tuple[float, float]]
    cls: str
    width: float
    role: str
    district: str | None = None
    name: str | None = None
    section: dict | None = None
    primary: dict | None = None        # the M1b segment row of a primary road
    forbid: list[tuple[float, float]] = field(default_factory=list)  # no-junction (s0, s1)
    junctions: list[tuple[float, float]] = field(default_factory=list)
    nodes: list[tuple[float, float]] = field(default_factory=list)  # primary nodes on it
    inserts: list[tuple[float, float]] = field(default_factory=list)
    attached: list[bool] = field(default_factory=lambda: [False, False])
    crosses: str | None = None          # footbridges: the water id
    water_class: str | None = None
    dead: bool = False

    @property
    def line(self) -> LineString:
        return LineString(self.pts)

    @property
    def no_junction(self) -> bool:
        """A highway takes no local street (a traced one does: the tracing has no ramps, it
        is at grade); nor does a footbridge."""
        if self.cls == "footbridge":
            return True
        return self.cls == "highway" and not (self.primary is not None and
                                              "pinned" in self.primary["attrs"])


@dataclass
class StreetNet:
    lines: list[Line] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    bridges: list[dict] = field(default_factory=list)
    cells: dict[str, list] = field(default_factory=dict)       # district -> cell polygons
    cores: list[tuple[str, object]] = field(default_factory=list)  # (district, campus core)
    notes: list[str] = field(default_factory=list)
    angles: dict[str, float] = field(default_factory=dict)     # district grid angle (deg)
    builder: object = None
    held: int = 0      # M10: held segments found again (district regeneration)


# ---------------------------------------------------------------------------
# Small exact helpers
# ---------------------------------------------------------------------------

def _pt(x, y) -> tuple[float, float]:
    return (G.q(x), G.q(y))


def _dist(a, b) -> float:
    """Euclidean distance with separate IEEE operations (no library hypot, which a compiler
    may evaluate with fused multiply-adds)."""
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def _unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.sqrt(dx * dx + dy * dy)
    return (dx / n, dy / n) if n > 0 else (1.0, 0.0)


def _plen(pts) -> float:
    return math.fsum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _dedupe(pts) -> list[tuple[float, float]]:
    out = []
    for p in pts:
        p = _pt(*p)
        if not out or p != out[-1]:
            out.append(p)
    return out


def _seg_dist(p, a, b) -> tuple[float, tuple[float, float], float]:
    """(distance, nearest point, parameter t) from p to segment ab (plain IEEE arithmetic on
    grid values, the same on every machine)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    t = min(max(t, 0.0), 1.0)
    q = (a[0] + t * dx, a[1] + t * dy)
    return _dist(p, q), q, t


def _along(pts, s: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Point and unit tangent at distance s along a polyline."""
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        L = _dist(a, b)
        if L > 0 and (acc + L >= s or i == len(pts) - 2):
            f = min(max((s - acc) / L, 0.0), 1.0)
            return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])), _unit(b[0] - a[0],
                                                                                 b[1] - a[1])
        acc += L
    return pts[-1], (1.0, 0.0)


def _project(pts, p) -> tuple[float, float, tuple[float, float], int]:
    """(distance along, distance to, nearest point, segment index) of p on a polyline."""
    best = None
    acc = 0.0
    for i in range(len(pts) - 1):
        d, q, t = _seg_dist(p, pts[i], pts[i + 1])
        L = _dist(pts[i], pts[i + 1])
        if best is None or d < best[1] - 1e-9:
            best = (acc + t * L, d, q, i)
        acc += L
    return best


def _angle_between(u, v) -> float:
    """Angle in degrees between two undirected directions (0 to 90)."""
    c = abs(u[0] * v[0] + u[1] * v[1])
    s = abs(u[0] * v[1] - u[1] * v[0])
    return M.degrees(M.atan2(s, c))


def _chaikin(pts, n: int, closed: bool):
    """Corner cutting (Chaikin); a closed ring keeps its closing point."""
    for _ in range(n):
        out = [] if closed else [pts[0]]
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out.append(out[0] if closed else pts[-1])
        pts = out
    return pts


def _ccw(ring):
    """A closed ring (first point repeated or not) turned counterclockwise (exact sign)."""
    pts = list(ring)
    a = 0
    for i in range(len(pts) - 1):
        x0, y0 = _icoord(pts[i])
        x1, y1 = _icoord(pts[i + 1])
        a += x0 * y1 - x1 * y0
    if pts[0] != pts[-1]:
        x0, y0 = _icoord(pts[-1])
        x1, y1 = _icoord(pts[0])
        a += x0 * y1 - x1 * y0
    return pts if a >= 0 else pts[::-1]


def _lines_of(g) -> list[list[tuple[float, float]]]:
    """Grid point lists of the line parts of a geometry (snapped)."""
    out = []
    if g is None or g.is_empty:
        return out
    for p in shapely.get_parts(g):
        if p.geom_type in ("LineString", "LinearRing"):
            pts = _dedupe(p.coords)
            if len(pts) >= 2:
                out.append(pts)
        elif hasattr(p, "geoms"):
            out += _lines_of(p)
    return out


def _merged_lines(g) -> list[list[tuple[float, float]]]:
    if g is None or g.is_empty:
        return []
    if g.geom_type == "MultiLineString":
        g = shapely.line_merge(g)
    return _lines_of(g)


def _clip(pts, poly) -> list[list[tuple[float, float]]]:
    """Pieces of a polyline inside a polygon, in order along the line."""
    if len(pts) < 2:
        return []
    ln = LineString(pts)
    out = _lines_of(G.line_inter(ln, poly))
    keyed = []
    for piece in out:
        s, _, _, _ = _project(pts, piece[0])
        s2, _, _, _ = _project(pts, piece[-1])
        if s2 < s:
            piece = piece[::-1]
            s = s2
        keyed.append((G.q(s), piece))
    keyed.sort(key=lambda t: (t[0], t[1][0]))
    return [p for _, p in keyed]


def _buffer(pts_list, widths, extra: float = 0.0):
    """Right-of-way polygons (flat ends, mitre joins), snapped."""
    geoms = []
    for pts, w in zip(pts_list, widths):
        if len(pts) < 2:
            continue
        geoms.append(LineString(pts).buffer(w / 2 + extra, cap_style="flat", join_style="mitre",
                                            mitre_limit=2.0))
    # snapped before the union: flat caps of roads that meet coincide exactly, and GEOS
    # would resolve unsnapped near-coincident edges by their last bits
    return G.union(list(G.snap_many(geoms))) if geoms else Polygon()


# ---------------------------------------------------------------------------
# Segment index (a bucket grid over grid points, plain Python)
# ---------------------------------------------------------------------------

class SegIndex:
    def __init__(self, cell: float = 40.0):
        self.cell = cell
        self.buckets: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.keys_of: dict[int, set] = {}

    def _keys(self, a, b, pad: float = 0.0):
        c = self.cell
        x0, x1 = min(a[0], b[0]) - pad, max(a[0], b[0]) + pad
        y0, y1 = min(a[1], b[1]) - pad, max(a[1], b[1]) + pad
        for i in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for j in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                yield (i, j)

    def add(self, li: int, pts) -> None:
        ks = self.keys_of.setdefault(li, set())
        for k in range(len(pts) - 1):
            for key in self._keys(pts[k], pts[k + 1]):
                self.buckets.setdefault(key, []).append((li, k))
                ks.add(key)

    def remove_line(self, li: int) -> None:
        for key in self.keys_of.pop(li, ()):
            v = [e for e in self.buckets[key] if e[0] != li]
            if v:
                self.buckets[key] = v
            else:
                del self.buckets[key]

    def near(self, a, b=None, pad: float = 0.0) -> list[tuple[int, int]]:
        b = a if b is None else b
        out = set()
        for key in self._keys(a, b, pad):
            out.update(self.buckets.get(key, ()))
        return sorted(out)


FRAME_SNAP_M = 25.0   # M10: a street of a regenerated district meets a held road at an old
                      # node at most this far from where it would have met it


def _ckey(pts) -> tuple:
    """A centerline as a key, the same either way along."""
    a = tuple((float(x), float(y)) for x, y in pts)
    return min(a, a[::-1])


def _ekey(pts) -> tuple:
    a, b = (float(pts[0][0]), float(pts[0][1])), (float(pts[-1][0]), float(pts[-1][1]))
    return (a, b) if a <= b else (b, a)


class Frame:
    """M10, `citygen build --district`: the roads a district regeneration holds. Every road
    segment of the old city that is not inside the district (its border roads, the roads
    outside it, the primary roads that leave it) is held: built again as it was, with all its
    nodes, and the district's new streets meet it only at one of those nodes. Inside the
    district are its own local streets (not its boundary streets) and the pieces of primary
    roads that lie in it more than 1 m from its edge; those are built anew."""

    def __init__(self, model, name: str, did: str, polygon, base_arch: dict,
                 pins=(), keep_out=None, pin_buildings=()):
        self.name, self.did = name, did
        self.base_arch = base_arch
        self.pins = set(pins)          # pinned roads are held too (`overrides.py`)
        self.keep_out = keep_out       # pinned buildings and open spaces: no new streets
        # pinned buildings of the district: a lot of their own (`blocks._frame_lots`), M3
        # builds nothing on it, the old building goes back on it (`buildout.frame_pins`)
        self.pin_buildings = list(pin_buildings)
        self.zone = G.qpoly(polygon.buffer(2.0, join_style="mitre"))
        self.core = G.qpoly(polygon.buffer(-1.0, join_style="mitre"))
        shapely.prepare(self.zone)
        shapely.prepare(self.core)
        pos = {n.id: (G.q(n.position[0]), G.q(n.position[1])) for n in model.road_nodes}
        self.rows: dict[tuple, object] = {}       # held segments by centerline
        self.m1b: dict[str, list[tuple]] = {}     # M1b id -> centerlines of its held pieces
        self.pinned_local = []                    # pinned streets of the district itself
        self.foot = []                            # held footbridges
        self.foot_done: set[int] = set()
        nodes = set()
        held_foot_nodes = set()
        for s in model.road_segments:
            if self.inside_row(s):
                continue
            if s.id in self.pins and "m1b_segment" not in s.attrs and \
                    s.attrs.get("district") == did:
                self.pinned_local.append(s)
            if s.attrs.get("role") == "footbridge":
                self.foot.append(s)
                held_foot_nodes |= {s.start, s.end}
            self.rows[_ckey(s.centerline)] = s
            if "m1b_segment" in s.attrs:
                self.m1b.setdefault(s.attrs["m1b_segment"], []).append(
                    tuple((G.q(x), G.q(y)) for x, y in s.centerline))
            nodes.add(pos[s.start])
            nodes.add(pos[s.end])
        # and the district's approaches of a footbridge across its border (its new streets
        # are joined to them)
        for s in model.road_segments:
            if s.attrs.get("role") == "footbridge" and self.inside_row(s) and \
                    ({s.start, s.end} & held_foot_nodes):
                self.foot.append(s)
        self.ends: dict[tuple, list] = {}       # held segments by their end points
        for k, r in self.rows.items():
            self.ends.setdefault(_ekey(k), []).append(r)
        # gates: old nodes where the district's streets met a held road
        inner = set()
        for s in model.road_segments:
            if self.inside_row(s):
                inner.add(pos[s.start])
                inner.add(pos[s.end])
        self.gates = sorted(inner & nodes)
        self.gate_set = set(self.gates)
        self.nodes = nodes
        self.node_list = sorted(nodes)
        self.tree = shapely.STRtree(shapely.points(np.array(self.node_list, dtype=np.float64))
                                    ) if nodes else None
        self._spans: dict[str, list] = {}
        self.local = sorted(k for k, r in self.rows.items() if "m1b_segment" not in r.attrs)
        self.ltree = shapely.STRtree([LineString(k) for k in self.local]) if self.local else None

    def inside_row(self, s) -> bool:
        a = s.attrs
        if a.get("role") == "district_boundary" or s.id in self.pins:
            return False
        line = LineString(s.centerline)
        if "m1b_segment" in a:
            return self.core.contains(line)
        if a.get("role") == "footbridge":
            return a.get("district") == self.did and self.zone.contains(line)
        return a.get("district") == self.did

    def free_local(self, t: "Line") -> bool:
        if t.district != self.name or t.role in ("district_boundary", "pinned_road"):
            return False
        return t.role != "footbridge" or self.zone.contains(LineString(t.pts))

    def match(self, pts, row: dict | None = None):
        """The held segment that a new edge is (the same ends and course; the old one may
        keep a vertex where a street of the district met it once), else None. With `row`
        (the new segment), also the same road: class and M1b segment (a highway and an
        avenue can share a centerline, one over the other)."""
        cands = self.ends.get(_ekey(pts))
        if not cands:
            return None
        line = LineString(pts)
        for r in cands:
            if row is not None and (r.road_class != row["road_class"] or r.attrs.get(
                    "m1b_segment") != row["attrs"].get("m1b_segment")):
                continue
            o = LineString(r.centerline)
            if abs(o.length - line.length) < 0.05 and o.hausdorff_distance(line) < 0.03:
                return r
        return None

    def spans(self, t: "Line") -> list[tuple[float, float]]:
        key = t.primary["id"]
        if key not in self._spans:
            out = []
            for c in self.m1b.get(key, []):
                s0, s1 = _project(t.pts, c[0])[0], _project(t.pts, c[-1])[0]
                out.append((min(s0, s1), max(s0, s1)))
            self._spans[key] = sorted(out)
        return self._spans[key]

    def holds(self, t: "Line", q) -> bool:
        """Whether road t is held where a street would meet it at q."""
        if t.primary is not None:
            s = _project(t.pts, q)[0]
            return any(s0 - 0.5 <= s <= s1 + 0.5 for s0, s1 in self.spans(t))
        return not self.free_local(t)

    def node_on(self, t: "Line", q) -> tuple | None:
        """The old node on road t nearest q (within FRAME_SNAP_M), else None."""
        if self.tree is None:
            return None
        ks = sorted(int(k) for k in self.tree.query(Point(q), predicate="dwithin",
                                                     distance=FRAME_SNAP_M))
        best = None
        for k in ks:
            p = self.node_list[k]
            if _locate(t.pts, p) is None:
                continue
            d = _dist(p, q)
            if best is None or (d, p) < best:
                best = (d, p)
        return best[1] if best else None

    def inject(self, B: "Builder") -> None:
        """The district's pinned streets as they were, before its new streets are laid."""
        self.foot_done = set()
        for r in self.pinned_local:
            pts = [(G.q(x), G.q(y)) for x, y in r.centerline]
            li = B.add(Line(pts, r.road_class, r.width_m, "pinned_road", self.name,
                            name=r.name, section=r.cross_section.model_dump(mode="json")))
            B.lines[li].attached = [True, True]

    def touches(self, cl) -> bool:
        """Whether a footbridge across the water body along cl can reach the district."""
        return LineString(cl).distance(self.zone) <= FOOTBRIDGE_MAX_SPAN_M

    def inject_footbridges(self, B: "Builder", wid: str, cl) -> list[tuple]:
        """The held footbridges across a water body that reaches the district (and the
        district's approaches to them), as they were, joined as they were when placed
        (footbridges are placed one after another along the body: a new one in the
        district would move those beyond it). Returns where they cross its centerline."""
        mid = LineString(cl)
        # the pieces that cross it, and those joined to them
        group = {k for k, r in enumerate(self.foot)
                 if k not in self.foot_done and LineString(r.centerline).intersects(mid)}
        while True:
            nodes = {n for k in group for n in (self.foot[k].start, self.foot[k].end)}
            more = {k for k, r in enumerate(self.foot) if k not in self.foot_done and
                    k not in group and {r.start, r.end} & nodes}
            if not more:
                break
            group |= more
        self.foot_done |= group
        pieces = [self.foot[k] for k in sorted(group)]
        ends: dict = {}
        for r in pieces:
            for p in (r.centerline[0], r.centerline[-1]):
                k = (G.q(p[0]), G.q(p[1]))
                ends[k] = ends.get(k, 0) + 1
        out = []
        for r in pieces:
            pts = [(G.q(x), G.q(y)) for x, y in r.centerline]
            dist = next((n for n, d in B.did.items() if d == r.attrs.get("district")), None)
            li = B.add(Line(pts, r.road_class, r.width_m, "footbridge", dist,
                            section=r.cross_section.model_dump(mode="json"), crosses=wid,
                            water_class="canal"))
            B.lines[li].attached = [ends[p] > 1 for p in (pts[0], pts[-1])]
            for k, end in ((0, 0), (1, -1)):
                if not B.lines[li].attached[k] and not B.attach(li, end, reach=3.0,
                                                              angle=ORGANIC_ANGLE_DEG):
                    B.attach(li, end, reach=22.0, angle=ORGANIC_ANGLE_DEG)
            x = shapely.intersection(LineString(pts), mid)
            if not x.is_empty:
                out.append(_pt(*min(c for g in getattr(x, "geoms", [x]) for c in g.coords)))
        return out

    def border_nodes(self, t: "Line") -> list[tuple]:
        """The ends of the held segments along road t at a gate or in the district's zone."""
        return [p for p in self.on_line(t) if p in self.gate_set or
                self.zone.contains(Point(p))]

    def meet(self, t: "Line", q):
        """Where a new street of the district meets road t near q: an old node where t is
        held (None if there is none within FRAME_SNAP_M); where t is free, q, or the old node
        of a held stretch of t closer than MIN_JUNCTION_GAP_M."""
        if self.holds(t, q):
            return self.node_on(t, q)
        if t.primary is not None:
            olds = [p for p in self.on_line(t) if _dist(p, q) < MIN_JUNCTION_GAP_M]
            if olds:
                return min(olds, key=lambda p: (_dist(p, q), p))
        return q

    def on_line(self, t: "Line") -> list[tuple]:
        """The ends of the held segments that run along road t (they stay nodes)."""
        if len(t.pts) < 2:
            return []
        if t.primary is not None:
            pieces = self.m1b.get(t.primary["id"], [])
        elif self.free_local(t) or self.ltree is None:
            return []
        else:
            ks = sorted(int(k) for k in self.ltree.query(LineString(t.pts), predicate="dwithin",
                                                          distance=0.05))
            pieces = [self.local[k] for k in ks]
        out = []
        for c in pieces:
            if all(_locate(t.pts, p) is not None for p in c):
                out += [c[0], c[-1]]
        return out

    def restore(self, segments: list[dict]) -> int:
        """Held segments as they were (direction, one-way state, cross-section, profile,
        attributes): the regeneration must not change them. Returns how many it found."""
        found = 0
        for s in segments:
            old = self.match(s["centerline"], s)
            if old is None:
                continue
            found += 1
            o = old.model_dump(mode="json")
            fwd = tuple(s["centerline"][0]) == tuple(o["centerline"][0])
            a, b = (s["start"], s["end"]) if fwd else (s["end"], s["start"])
            for k in RESTORED:
                s[k] = o[k]
            if "role" in o["attrs"]:
                s["attrs"] = {**s["attrs"], "role": o["attrs"]["role"]}
            s["start"], s["end"] = a, b
        return found


# the fields `Frame.restore` copies (not the ids and references, which the new build names)
RESTORED = ("type", "road_class", "lanes", "width_m", "centerline", "level", "z_profile",
            "cross_section", "one_way", "clearance_m", "name")


def _cross_exact(a, b, c, d):
    """Intersection of segments ab and cd on the cm grid (exact); None when they do not meet
    in a single point. Returns (point, t on ab as a Fraction)."""
    A = (round(a[0] * SCALE), round(a[1] * SCALE))
    B = (round(b[0] * SCALE), round(b[1] * SCALE))
    C = (round(c[0] * SCALE), round(c[1] * SCALE))
    D = (round(d[0] * SCALE), round(d[1] * SCALE))
    r = (B[0] - A[0], B[1] - A[1])
    s = (D[0] - C[0], D[1] - C[1])
    den = r[0] * s[1] - r[1] * s[0]
    if den == 0:
        return None
    qp = (C[0] - A[0], C[1] - A[1])
    tn = qp[0] * s[1] - qp[1] * s[0]
    un = qp[0] * r[1] - qp[1] * r[0]
    if den < 0:
        den, tn, un = -den, -tn, -un
    if not (0 <= tn <= den and 0 <= un <= den):
        return None
    x = A[0] + _rdiv(tn * r[0], den)
    y = A[1] + _rdiv(tn * r[1], den)
    return (x / SCALE, y / SCALE), Fraction(tn, den)


def _rdiv(n: int, d: int) -> int:
    """n / d rounded half away from zero (exact, d > 0)."""
    q, r = divmod(abs(n), d)
    if 2 * r >= d:
        q += 1
    return q if n >= 0 else -q


# ---------------------------------------------------------------------------
# The builder
# ---------------------------------------------------------------------------

class Builder:
    def __init__(self, spec: CitySpec, h, polygons: dict, district_ids: dict, waterways, sites,
                 roads, open_polys: list, frame: Frame | None = None):
        self.spec = spec
        self.frame = frame
        self.h = h
        self.polygons = polygons
        self.did = district_ids
        self.ww = waterways
        self.sites = sites
        self.roads = roads
        self.notes: list[str] = []
        self.arch = {d.name: d.archetype for d in spec.districts}
        self.dspec = {d.name: d for d in spec.districts}
        ww_polys = [w.polygon for w in waterways.items]
        self.wet = G.union([h.water] + ww_polys)
        shapely.prepare(self.wet)
        self.reserves = G.union([s.polygon for s in sites]) if sites else Polygon()
        cones = [s.flight_cone for s in sites if s.flight_cone is not None]
        self.cones = G.union(cones) if cones else Polygon()
        self.open_land = G.union(open_polys) if open_polys else Polygon()
        from . import pinned as PN

        # traced buildings stand as drawn: local streets keep PIN_CLEAR_M from them
        pins = PN.placed_islands(spec, h)
        feet = [b.footprint for k in sorted(pins) for b in pins[k][0].buildings]
        self.pin_feet = G.union(feet) if feet else Polygon()
        self.pinned = G.qpoly(G.union(feet).buffer(PIN_CLEAR_M, join_style="mitre")) \
            if feet else Polygon()
        if frame is not None and frame.keep_out is not None and not frame.keep_out.is_empty:
            # M10: pinned buildings and open spaces of a regenerated district keep their ground
            self.pin_feet = G.union([self.pin_feet, frame.keep_out])
            self.pinned = G.union([self.pinned, G.qpoly(frame.keep_out.buffer(
                PIN_CLEAR_M, join_style="mitre"))])
        self.closed = G.union([G.qpoly(self.reserves.buffer(CLOSED_PAD_M, join_style="mitre")),
                               self.cones, self.open_land, self.pinned])
        shapely.prepare(self.closed)
        self.lines: list[Line] = []
        self.index = SegIndex()
        self.net = StreetNet()
        self._primary_lines()

    # --- lines -----------------------------------------------------------------------

    def add(self, ln: Line) -> int:
        ln.pts = _dedupe(ln.pts)
        self.lines.append(ln)
        li = len(self.lines) - 1
        self.index.add(li, ln.pts)
        return li

    def replace_pts(self, li: int, pts) -> None:
        self.index.remove_line(li)
        self.lines[li].pts = _dedupe(pts)
        self.index.add(li, self.lines[li].pts)

    def _primary_lines(self) -> None:
        segs = self.roads.segments
        nodes = {n["id"]: n for n in self.roads.nodes}
        bridges = {b["id"]: b for b in self.roads.bridges}
        for s in segs:
            pts = [(G.q(x), G.q(y)) for x, y in s["centerline"]]
            # no local junction on a bridge or where the road is more than 3 m up (its
            # approach; M7: lower, the street ramps up to it)
            forbid = []
            for bid in s["bridge_ids"]:
                b = bridges[bid]
                forbid.append((b["s0"], b["s1"]))
            forbid += _raised_spans(s["z_profile"], LOCAL_JUNCTION_Z_M)
            ln = Line(pts, s["road_class"], s["width_m"], s["attrs"].get("role", "primary"),
                      name=s.get("name"), section=s["cross_section"], primary=s, forbid=forbid)
            for end in (s["start"], s["end"]):
                p = nodes[end]["position"]
                ln.junctions.append((p[0], p[1]))
                ln.nodes.append((p[0], p[1]))
            ln.attached = [True, True]
            self.add(ln)
        self.n_primary = len(self.lines)

    # --- areas ---------------------------------------------------------------------------

    def primary_row(self):
        if not hasattr(self, "_prow"):
            prim = self.lines[:self.n_primary]
            self._prow = _buffer([ln.pts for ln in prim], [ln.width for ln in prim], 1.0)
        return self._prow

    def free_area(self, name: str):
        """District land a local street may use: no water, primary right of way, reserves,
        flight cones or open land."""
        poly = self.polygons[name]
        out = G.diff(poly, self.wet)
        out = G.diff(out, self.primary_row())
        out = G.diff(out, self.closed)
        return G.drop_small(G.opening(out, 3.0), 200.0)

    # --- attaching ends ----------------------------------------------------------------

    def attach(self, li: int, end: int, reach: float = 3.0, allow_highway: bool = False,
               angle: float | None = None, exclude: set | None = None,
               targets: set | None = None) -> bool:
        """Join an end of line li to a road whose right of way it touches (within `reach` of
        the road edge), nearest first: a T-junction where junctions are allowed, merged with
        an existing junction closer than MIN_JUNCTION_GAP_M."""
        ln = self.lines[li]
        if len(ln.pts) < 2:
            return False
        pts = ln.pts if end == -1 else ln.pts[::-1]
        p = pts[-1]
        angle = angle if angle is not None else (
            min_angle(self.arch[ln.district]) if ln.district else GRID_ANGLE_DEG)
        best: dict[int, float] = {}
        for tj, k in self.index.near(p, pad=reach + 40.0):
            if tj == li or (exclude and tj in exclude) or (targets is not None and
                                                          tj not in targets):
                continue
            t = self.lines[tj]
            if t.dead:
                continue
            d, _, _ = _seg_dist(p, t.pts[k], t.pts[k + 1])
            gap = d - t.width / 2
            if gap <= reach and gap < best.get(tj, math.inf):
                best[tj] = gap
        for tj in sorted(best, key=lambda j: (best[j], j)):
            t = self.lines[tj]
            if t.no_junction and not (allow_highway and t.cls == "highway"):
                continue
            new = self._attach_to(pts, t, angle, reach, ln.inserts, self._renewed(ln))
            if new is None:
                continue
            q = new[-1]
            if end == 0:
                new = new[::-1]
            self.replace_pts(li, new)
            if q not in t.junctions:
                t.junctions.append(q)
            t.inserts.append(q)
            ln.attached[0 if end == 0 else 1] = True
            return True
        return False

    def extend_ray(self, li: int, end: int, max_len: float) -> bool:
        """A dead end continues straight ahead to the first road it meets (up to max_len),
        where a junction is allowed and nothing (water, reserves, open land) is in between."""
        ln = self.lines[li]
        pts = ln.pts if end == -1 else ln.pts[::-1]
        p = pts[-1]
        back, _ = _along(pts[::-1], min(8.0, _plen(pts) / 2))
        d0 = _unit(p[0] - back[0], p[1] - back[1])
        tip = _pt(p[0] + d0[0] * max_len, p[1] + d0[1] * max_len)
        hit = None
        for tj, k in self.index.near(p, tip, pad=1.0):
            if tj == li or self.lines[tj].dead:
                continue
            t = self.lines[tj]
            r = _cross_exact(p, tip, t.pts[k], t.pts[k + 1])
            if r is None or r[0] == p:
                continue
            if hit is None or r[1] < hit[1] or (r[1] == hit[1] and tj < hit[2]):
                hit = (r[0], r[1], tj)
        if hit is None:
            return False
        q, _, tj = hit
        t = self.lines[tj]
        if t.no_junction:
            return False
        if not self._legal(t, q, _project(t.pts, q)[0]):
            return False
        near = [j for j in t.junctions if _dist(j, q) < MIN_JUNCTION_GAP_M]
        if near:
            q = min(near, key=lambda j: (_dist(j, q), j))
        if self._renewed(ln):
            q = self.frame.meet(t, q)
            if q is None:
                return False
        angle = min_angle(self.arch[ln.district]) if ln.district else GRID_ANGLE_DEG
        if _angle_between(_unit(q[0] - p[0], q[1] - p[1]), self._tangent(t.pts, q)) < angle:
            return False
        link = LineString([p, q])
        if self.wet.intersects(link) or (self.closed.intersects(link) and
                                         link.intersection(self.closed).length > 0.5):
            return False
        new = list(pts) + [q]
        self.replace_pts(li, new if end == -1 else new[::-1])
        if q not in t.junctions:
            t.junctions.append(q)
        t.inserts.append(q)
        ln.attached[1 if end == -1 else 0] = True
        return True

    def _legal(self, t: Line, q, s: float) -> bool:
        if any(s0 - 5.0 <= s <= s1 + 5.0 for s0, s1 in t.forbid):
            return False
        return not any(_dist(j, q) < PRIMARY_NODE_GAP_M for j in t.nodes)

    def _renewed(self, ln: Line) -> bool:
        """M10: a street of the district being regenerated (it meets held roads only at
        their nodes; every other street is built as it was)."""
        return self.frame is not None and self.frame.free_local(ln)

    def _attach_to(self, pts, t: Line, angle: float, reach: float, keep=(),
                   renewed: bool = False):
        """The polyline extended onto road t, or None where no junction is allowed."""
        p = pts[-1]
        back, _ = _along(pts[::-1], min(8.0, _plen(pts) / 2))
        d0 = _unit(p[0] - back[0], p[1] - back[1])
        # straight on along the street's own direction, else the nearest point
        far = t.width / 2 + reach + 20.0
        ray = (p, _pt(p[0] + d0[0] * far, p[1] + d0[1] * far))
        q = None
        for k in range(len(t.pts) - 1):
            r = _cross_exact(ray[0], ray[1], t.pts[k], t.pts[k + 1])
            if r is not None and (q is None or r[1] < q[1]):
                q = r
        q = q[0] if q is not None else _pt(*_project(t.pts, p)[2])
        s = _project(t.pts, q)[0]
        if not self._legal(t, q, s):
            return None
        near = [j for j in t.junctions if _dist(j, q) < MIN_JUNCTION_GAP_M]
        if near:
            q = min(near, key=lambda j: (_dist(j, q), j))
            if not self._legal(t, q, _project(t.pts, q)[0]):
                return None
        else:
            for e in (t.pts[0], t.pts[-1]):
                if q != e and _dist(e, q) < 8.0:
                    q = e  # join at the end of the target instead of leaving a stub
        if renewed:
            q = self.frame.meet(t, q)  # M10: a held road is met at one of its nodes
            if q is None:
                return None
        tang = self._tangent(t.pts, q)
        a = _unit(q[0] - back[0], q[1] - back[1])
        if _dist(q, back) >= 1.0 and _angle_between(a, tang) >= angle:
            if _dist(p, q) > 3.0:
                d1 = _unit(q[0] - p[0], q[1] - p[1])
                if d0[0] * d1[0] + d0[1] * d1[1] < 0.64:  # a hook of over 50 degrees
                    return None
            new = list(pts) + [q]
        else:
            # bend the approach: from a point a little back, square onto the road
            pb, _ = _along(pts[::-1], min(14.0, _plen(pts) * 0.6))
            pb = _pt(*pb)
            s2, _, q2, _ = _project(t.pts, pb)
            q2 = _pt(*q2)
            if not self._legal(t, q2, s2):
                return None
            if renewed:
                q2 = self.frame.meet(t, q2)
                if q2 is None:
                    return None
            a2 = _unit(q2[0] - pb[0], q2[1] - pb[1])
            prev, _ = _along(pts[::-1], min(30.0, _plen(pts)))
            a_prev = _unit(pb[0] - prev[0], pb[1] - prev[1])
            turn = M.degrees(M.acos(max(-1.0, min(1.0, a_prev[0] * a2[0] + a_prev[1] * a2[1]))))
            if _angle_between(a2, self._tangent(t.pts, q2)) < angle or turn > 65.0 or \
                    _dist(q2, pb) > 40.0:
                return None
            sb = _project(pts, pb)[0]
            if any(_project(pts, x)[0] >= sb - 0.5 and _project(pts, x)[1] < 0.05
                   for x in keep):
                return None  # another road joins the stretch the bend would drop
            new = [x for x in pts if _project(pts, x)[0] < sb - 0.5] + [pb, q2]
        link = LineString([new[-2], new[-1]]) if new[-2] != new[-1] else None
        if link is not None:
            if self.wet.intersects(link) and link.intersection(self.wet).length > 0.5:
                return None
            if self.closed.intersects(link) and link.intersection(self.closed).length > 0.5:
                return None
        return _dedupe(new)

    @staticmethod
    def _tangent(pts, q):
        s, _, _, i = _project(pts, q)
        a, b = pts[i], pts[i + 1]
        return _unit(b[0] - a[0], b[1] - a[1])

    # --- distance filters ------------------------------------------------------------------

    def parallel_runs(self, pts, width: float, clearance: float, skip: set,
                      min_len: float) -> list[list[tuple[float, float]]]:
        """Parts of a polyline that do not run alongside an existing road closer than the two
        half widths plus `clearance` (near-parallel only, so crossings and approaches stay)."""
        L = _plen(pts)
        if L < min_len:
            return []
        n = max(int(L / 5.0), 1)
        ok = []
        for k in range(n + 1):
            s = L * k / n
            p, tan = _along(pts, s)
            bad = False
            for tj, i in self.index.near(p, pad=clearance + 30.0):
                if tj in skip or self.lines[tj].dead:
                    continue
                t = self.lines[tj]
                d, _, _ = _seg_dist(p, t.pts[i], t.pts[i + 1])
                if d < (width + t.width) / 2 + clearance:
                    tt = _unit(t.pts[i + 1][0] - t.pts[i][0], t.pts[i + 1][1] - t.pts[i][1])
                    if _angle_between(tan, tt) < 30.0:
                        bad = True
                        break
            ok.append((s, bad))
        runs, cur = [], None
        for s, bad in ok:
            if not bad:
                cur = [s, s] if cur is None else [cur[0], s]
            else:
                if cur is not None:
                    runs.append(cur)
                cur = None
        if cur is not None:
            runs.append(cur)
        out = []
        for a, b in runs:
            if b - a < min_len:
                continue
            out.append(_substring(pts, a, b))
        return out


def _substring(pts, a: float, b: float) -> list[tuple[float, float]]:
    """The part of a polyline between distances a and b along it."""
    if a <= 0.0 and b >= _plen(pts) - 1e-9:
        return list(pts)
    pa, _ = _along(pts, a)
    out = [_pt(*pa)]
    acc = 0.0
    for i in range(1, len(pts) - 1):
        acc += _dist(pts[i - 1], pts[i])
        if a + 1e-9 < acc < b - 1e-9:
            out.append(pts[i])
    pb, _ = _along(pts, b)
    out.append(_pt(*pb))
    return _dedupe(out)


# ---------------------------------------------------------------------------
# District parameters
# ---------------------------------------------------------------------------

def _rng(seed: int, *salt: int) -> np.random.Generator:
    return np.random.default_rng([int(seed) % (2 ** 32)] + [int(x) % (2 ** 32) for x in salt])


def uniform(rng: np.random.Generator, lo: float, hi: float) -> float:
    """A uniform draw in [lo, hi) as `uniform(rng, lo, hi)` makes it, but in separate Python
    operations: numpy evaluates lo + (hi - lo) * u in compiled code, which clang (macOS)
    contracts into one fused multiply-add and gcc (Linux) does not. rng.random() is exact
    (53 random bits times 2**-53) and consumes the same bits."""
    lo, hi = float(lo), float(hi)
    return lo + (hi - lo) * float(rng.random())


def _block_range(d) -> tuple[float, float]:
    lo, hi = d.block_size_m if d.block_size_m else (80.0, 140.0)
    return float(lo), float(hi)


def district_angle(B: Builder, name: str) -> float:
    """Grid angle (degrees, 0 to 90): the spec value when it is set (not 0), else the
    dominant direction of the primary roads in and around the district, so grids line up
    with the avenues that frame them."""
    d = B.dspec[name]
    if d.grid_angle_deg:
        return float(d.grid_angle_deg)
    zone = G.qpoly(B.polygons[name].buffer(60.0, join_style="mitre"))
    shapely.prepare(zone)
    bins = [0.0] * 18
    for ln in B.lines[:B.n_primary]:
        pts = ln.pts
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if not zone.contains(Point(a)):
                continue
            L = _dist(a, b)
            if L <= 0:
                continue
            ang = M.degrees(M.atan2(b[1] - a[1], b[0] - a[0])) % 90.0
            bins[int(ang // 5.0) % 18] += L
    if not any(bins):
        return 0.0
    k = max(range(18), key=lambda i: (round(bins[i], 3), -i))
    return k * 5.0 + 2.5


# ---------------------------------------------------------------------------
# Frame: reserve rings, district boundary streets, waterfront promenades
# ---------------------------------------------------------------------------

UNDERPASS_STEP_M = 200.0       # M7: a street under a viaduct about this often
UNDERPASS_CLEAR_M = 7.8        # deck top over it: 5.5 m clear, 1.8 m deck, a margin


def _z_on(prof, s: float) -> float:
    pts = [(p["s"], p["z"]) for p in prof] if isinstance(prof, list) else []
    if not pts:
        return 0.0
    if s <= pts[0][0]:
        return pts[0][1]
    for (s0, z0), (s1, z1) in zip(pts, pts[1:]):
        if s <= s1:
            return max(z0, z1) if s1 <= s0 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return pts[-1][1]


def under_deck(ln: "Line", p) -> bool:
    """A primary road whose deck at p (on it) clears a street passing under it."""
    if ln.primary is None:
        return False
    return _z_on(ln.primary["z_profile"], _project(ln.pts, p)[0]) >= UNDERPASS_CLEAR_M - 0.5


def underpasses(B: Builder, frontage: dict, free_all) -> list[int]:
    """Streets straight across under the elevated highways, every 200 m or so, where the
    deck is high enough, joined to the frontage streets on both sides (scope 5.2: covered
    sections); none within 60 m of a road passing under it or 40 m of a ramp."""
    added: list[int] = []
    why: dict = {}

    def no(k):
        why[k] = why.get(k, 0) + 1
    prim = B.lines[:B.n_primary]
    ramps = [ln.line for ln in prim if ln.role == "ramp"]
    for hi_ in sorted(frontage):
        hw = B.lines[hi_]
        if not (hw.primary or {}).get("attrs", {}).get("elevated"):
            continue
        fr = set(frontage[hi_])
        over = [tuple(p) for p in hw.primary["attrs"].get("overpass_at", [])]
        L = _plen(hw.pts)
        s = UNDERPASS_STEP_M / 2.0
        while s < L - 40.0:
            here = s
            s += UNDERPASS_STEP_M
            if here < 40.0 or _z_on(hw.primary["z_profile"], here) < UNDERPASS_CLEAR_M:
                no("deck too low")
                continue
            c, u = _along(hw.pts, here)
            if any(_dist(c, p) < 60.0 for p in over):
                no("near a road under the deck")
                continue
            pc = Point(c)
            if any(G.dist(r, pc) < 40.0 for r in ramps):
                no("near a ramp")
                continue
            sides = []
            for sg in (1.0, -1.0):
                # to just inside the nearest frontage street on this side
                best = None
                for li in sorted(fr):
                    t = B.lines[li]
                    if t.dead:
                        continue
                    d, q_, _ = _seg_dist(c, *min(
                        ((t.pts[k], t.pts[k + 1]) for k in range(len(t.pts) - 1)),
                        key=lambda ab: _seg_dist(c, ab[0], ab[1])[0]))
                    side = (q_[0] - c[0]) * -u[1] + (q_[1] - c[1]) * u[0]
                    if side * sg <= 0 or d > hw.width / 2 + FRONTAGE_VERGE_M + t.width + 2.0:
                        continue
                    if best is None or (d, li) < best[:2]:
                        best = (d, li, t)
                if best is None:
                    break
                d, li, t = best
                o = d - t.width / 2 + 1.0
                sides.append(_pt(c[0] - u[1] * o * sg, c[1] + u[0] * o * sg))
            if len(sides) < 2:
                no("no frontage street on both sides")
                continue
            a, b = sides
            seg = LineString([a, b])
            if not (free_all.contains(Point(a)) and free_all.contains(Point(b))):
                no("ends off the free land")
                continue
            if B.wet.intersects(seg):
                no("water")
                continue
            if any(t is not hw and G.dist(t.line, seg) < t.width / 2 + 6.0 for t in prim):
                no("another primary road")
                continue
            # the district of either end (the middle is under the highway)
            n = next((d for d in sorted(B.free, key=lambda d: B.did[d])
                      for e in (a, b) if B.free[d].buffer(1.0).contains(Point(e))), None)
            if n is None:
                no("no district")
                continue
            sec = cross_section("street", B.arch[n])
            li = B.add(Line([a, b], "street", sec["total_width_m"], "underpass", n,
                            section=sec))
            if B.attach(li, 0, 3.0, targets=fr) and B.attach(li, -1, 3.0, targets=fr):
                added.append(li)
            else:
                no("no junction allowed")
                B.lines[li].dead = True
                B.index.remove_line(li)
    if added or why:
        B.notes.append(f"{len(added)} underpass streets under the viaducts" + (
            " (not built: " + ", ".join(f"{v} {k}" for k, v in sorted(why.items())) + ")"
            if why else ""))
    return added


def build_frame(B: Builder) -> None:
    free = {n: B.free_area(n) for n in sorted(B.polygons, key=lambda n: B.did[n])}
    B.free = free
    free_all = G.union(list(free.values()))
    B.free_all = free_all
    added: list[int] = []
    # service rings around megasite reserves
    rings_avenue = [ln for ln in B.lines[:B.n_primary] if ln.role == "ring_road"]
    for s in B.sites:
        if s.district not in free:
            continue
        if s.kind == "central_park" and any(
                G.dist(s.polygon, ln.line) < 70.0 for ln in rings_avenue):
            continue
        poly = G.qpoly(s.polygon.buffer(RESERVE_RING_M, join_style="mitre", mitre_limit=2.0))
        ring = _ccw(_dedupe(G.parts(poly)[0].exterior.coords))
        cls = "service" if s.kind in ("spaceport", "freight_terminal") else "street"
        arch = B.arch[s.district]
        w = cross_section(cls, arch)["total_width_m"]
        # (the 0.5 m margin never reaches over the water: a ring grazing a bank is cut there)
        for piece in _clip(ring, G.diff(G.qpoly(free_all.buffer(0.5, join_style="mitre")),
                                        B.wet)):
            for run in B.parallel_runs(piece, w, 6.0, set(), 40.0):
                added.append(B.add(Line(run, cls, w, "reserve_ring", s.district,
                                        section=cross_section(cls, arch))))
    # frontage streets along highways (local streets never join a highway)
    frontage: dict[int, list[int]] = {}
    for hi_, hw in enumerate(B.lines[:B.n_primary]):
        if not hw.no_junction or hw.cls != "highway" or hw.role == "ramp":
            continue
        for n in sorted(free, key=lambda n: B.did[n]):
            if G.apart(hw.line, free[n], hw.width + 40.0):
                continue
            sec = cross_section("street", B.arch[n])
            w = sec["total_width_m"]
            for side in (1.0, -1.0):
                # a 5 m verge between the highway and the frontage street
                for pts in _offset_sides(hw.pts, side, hw.width / 2 + FRONTAGE_VERGE_M + w / 2):
                    for piece in _clip(pts, free[n]):
                        for run in B.parallel_runs(piece, w, 10.0, {hi_}, 60.0):
                            added.append(B.add(Line(run, "street", w, "frontage", n,
                                                    section=sec)))
                            frontage.setdefault(hi_, []).append(added[-1])
    # M7: streets under the viaducts, from frontage street to frontage street
    added += underpasses(B, frontage, free_all)
    # streets on the land boundaries between districts without a primary road
    names = sorted(free, key=lambda n: B.did[n])
    wet15_ = G.qpoly(B.wet.buffer(15.0, join_style="mitre"))
    free_all1 = G.qpoly(free_all.buffer(1.0, join_style="mitre"))
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pa, pb = B.polygons[a], B.polygons[b]
            if G.apart(pa, pb, 1.0):
                continue
            shared = shapely.intersection(pa.boundary, G.qpoly(pb.buffer(0.5, join_style="mitre")))
            shared = shapely.difference(G.snap(shared), wet15_)
            # (M10: a regenerated district's boundary streets keep their old archetype)
            ar = B.frame.base_arch if B.frame is not None else B.arch
            arch = a if cross_section("street", ar[a])["total_width_m"] >= \
                cross_section("street", ar[b])["total_width_m"] else b
            sec = cross_section("street", ar[arch])
            for pts in _merged_lines(G.snap(shapely.simplify(shared, 2.0))
                                     if not shared.is_empty else shared):
                for piece in _clip(pts, free_all1):
                    for run in B.parallel_runs(piece, sec["total_width_m"], 12.0, set(), 80.0):
                        added.append(B.add(Line(run, "street", sec["total_width_m"],
                                                "district_boundary", arch, section=sec)))
    # waterfront promenades (pedestrian streets 5 m from the water)
    wet5 = G.qpoly(B.wet.buffer(PROMENADE_OFFSET_M, join_style="mitre", mitre_limit=2.0))
    edge = G.snap(shapely.simplify(wet5.boundary, 1.0))
    for n in names:
        if not style_of(B.arch[n]).promenade:
            continue
        for pts in _merged_lines(G.line_inter(edge, free[n])):
            for run in B.parallel_runs(pts, PROMENADE_W, 3.0, set(), 50.0):
                sec = {**cross_section("pedestrian", B.arch[n]), "total_width_m": PROMENADE_W,
                       "sidewalk_m": (PROMENADE_W / 2, PROMENADE_W / 2)}
                added.append(B.add(Line(run, "pedestrian", PROMENADE_W, "promenade", n,
                                        section=sec)))
    # quay roads along the water in ports and spaceports (berths and aprons)
    wet15 = G.qpoly(B.wet.buffer(QUAY_ROAD_OFFSET_M, join_style="mitre", mitre_limit=2.0))
    edge15 = G.snap(shapely.simplify(wet15.boundary, 1.0))
    for n in names:
        if B.arch[n] not in ("industrial_port", "spaceport"):
            continue
        sec = cross_section("service", B.arch[n])
        for pts in _merged_lines(G.line_inter(edge15, free[n])):
            for run in B.parallel_runs(pts, sec["total_width_m"], 8.0, set(), 60.0):
                added.append(B.add(Line(run, "service", sec["total_width_m"], "quay_road", n,
                                        section=sec)))
    for li in added:
        for end in (0, -1):
            B.attach(li, end, reach=3.0)
    T.detail("streets/frame", [B.lines[li].pts for li in added])


def _offset_sides(pts, side: float, d: float) -> list[list[tuple[float, float]]]:
    """A polyline offset by d to its left (side 1) or right (side -1), snapped."""
    ln = LineString(pts)
    off = shapely.offset_curve(ln, side * d, join_style="mitre", mitre_limit=2.0)
    return _lines_of(off)


def _owner(B: Builder, pts) -> str | None:
    """District holding the middle of a polyline."""
    m, _ = _along(pts, _plen(pts) / 2)
    for n in sorted(B.free, key=lambda n: B.did[n]):
        if G.qpoly(B.free[n].buffer(1.0, join_style="mitre")).contains(Point(m)):
            return n
    return None


def district_cells(B: Builder, name: str) -> list:
    free = B.free[name]
    frame = [ln for ln in B.lines[B.n_primary:] if not ln.dead and
             not G.apart(ln.line, free, ln.width)]
    row = _buffer([ln.pts for ln in frame], [ln.width for ln in frame])
    cells = [p for p in G.parts(G.diff(free, row)) if G.area(p) >= 400.0]
    return [G.qpoly(G.oriented(c)) for c in cells]


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def _offsets(rng, lo: float, hi: float, span: float) -> list[float]:
    out = [-span + float(uniform(rng, 0.0, hi))]
    while out[-1] < span:
        out.append(out[-1] + float(uniform(rng, lo, hi)))
    return out


class GridFamily:
    """Grid lines of a district in its own frame: u lines along the grid angle at offsets
    `uo`, v lines across them (full lines, or staggered between consecutive u lines)."""

    def __init__(self, B: Builder, name: str, angle: float, su, sv, stagger: bool, rng):
        poly = B.polygons[name]
        c = G.centroid(poly)
        x0, y0, x1, y1 = poly.bounds
        R = 0.5 * _dist((x0, y0), (x1, y1)) + 50.0
        a = M.radians(angle)
        self.u = (M.cos(a), M.sin(a))
        self.n = (-self.u[1], self.u[0])
        self.c, self.R = c, R
        self.uo = _offsets(rng, su[0], su[1], R)
        self.vo = _offsets(rng, sv[0], sv[1], R)
        self.stagger = stagger
        self.strips = []
        if stagger:
            for k in range(len(self.uo) - 1):
                self.strips.append(_offsets(_rng(int(rng.integers(0, 2 ** 31)), k),
                                            sv[0], sv[1], R))

    def _p(self, along_u: float, along_n: float):
        return _pt(self.c[0] + self.u[0] * along_u + self.n[0] * along_n,
                   self.c[1] + self.u[1] * along_u + self.n[1] * along_n)

    def lines(self) -> list[tuple[str, list]]:
        out = [("u", [self._p(-self.R, o), self._p(self.R, o)]) for o in self.uo]
        if not self.stagger:
            out += [("v", [self._p(o, -self.R), self._p(o, self.R)]) for o in self.vo]
        else:
            for k, offs in enumerate(self.strips):
                a, b = self.uo[k], self.uo[k + 1]
                out += [("v", [self._p(o, a), self._p(o, b)]) for o in offs]
        return out


def _add_pieces(B: Builder, cell, cands, name: str, clearance: float, min_len: float,
                cls_default: str = "street") -> list[int]:
    """Clip candidate polylines to the cell, drop the parts that run alongside a road, add
    them and join their ends on the cell edge to the frame."""
    arch = B.arch[name]
    out = []
    edge = cell.exterior
    for item in cands:
        role, pts = item[0], item[1]
        cls = item[2] if len(item) > 2 else cls_default
        sec = cross_section(cls, arch)
        w = sec["total_width_m"]
        for piece in _clip(pts, cell):
            if _plen(piece) < min_len:
                continue
            for run in B.parallel_runs(piece, w, clearance, set(), min_len):
                li = B.add(Line(run, cls, w, role, name, section=sec))
                out.append(li)
    for li in out:
        ln = B.lines[li]
        for end in (0, -1):
            p = ln.pts[end]
            if G.dist(edge, Point(p)) <= 0.6 or not cell.contains(Point(p)):
                B.attach(li, end, reach=3.0)
    del edge
    return out


def pattern_grid(B: Builder, name: str, cell, fam: GridFamily, clearance: float,
                 min_len: float) -> list[int]:
    return _add_pieces(B, cell, [(f"grid_{k}", pts) for k, pts in fam.lines()], name,
                       clearance, min_len)


def _ring_pts(c, r: float, step: float = 14.0):
    n = max(24, int(2 * math.pi * r / step))
    k = np.arange(n + 1, dtype=np.float64) * (2.0 * M.PI / n)
    xs = c[0] + r * M.cos(k)
    ys = c[1] + r * M.sin(k)
    pts = [_pt(x, y) for x, y in zip(xs, ys)]
    pts[-1] = pts[0]
    return pts


def pattern_radial(B: Builder, name: str, cell, center, r0: float, lo: float, hi: float,
                   rng, clearance: float) -> list[int]:
    poly = B.polygons[name]
    x0, y0, x1, y1 = poly.bounds
    far = max(_dist(center, (x, y)) for x in (x0, x1) for y in (y0, y1)) + 20.0
    radii = [r0 + float(uniform(rng, lo, hi))]
    while radii[-1] < far:
        radii.append(radii[-1] + float(uniform(rng, lo, hi)))
    a0 = float(uniform(rng, 0.0, 45.0))
    cands = [("ring", _ring_pts(center, r)) for r in radii]
    # radials: eight spokes, doubled wherever the arc between them grows past ~1.8 rings
    level = [(a0 + 45.0 * j + float(uniform(rng, -5.0, 5.0)), r0 - 2.0) for j in range(8)]
    n = 8
    for k, r in enumerate(radii):
        if 2 * math.pi * r / n > 1.8 * (hi + lo) / 2 and k + 1 < len(radii):
            step = 360.0 / n
            level += [(a0 + step * (j + 0.5) + float(uniform(rng, -4.0, 4.0)), r)
                      for j in range(n)]
            n *= 2
    for ang, rs in level:
        a = M.radians(ang)
        u = (M.cos(a), M.sin(a))
        cands.append(("radial", [_pt(center[0] + u[0] * rs, center[1] + u[1] * rs),
                                 _pt(center[0] + u[0] * far, center[1] + u[1] * far)]))
    return _add_pieces(B, cell, cands, name, clearance, 30.0)


def _wobble(pts, rng, amp: float, wavelength: float):
    """Closed ring displaced along its normals by smooth noise (meters)."""
    if amp <= 0:
        return pts
    f = G.noise1d(rng, wavelength, octaves=2)
    L = _plen(pts)
    out = []
    acc = 0.0
    n = len(pts) - 1
    for i in range(n):
        a, b = pts[i - 1] if i else pts[n - 1], pts[i + 1]
        t = _unit(b[0] - a[0], b[1] - a[1])
        o = amp * float(f(np.array([acc]))[0])
        out.append((pts[i][0] - t[1] * o, pts[i][1] + t[0] * o))
        acc += _dist(pts[i], pts[i + 1])
    out.append(out[0])
    del L
    return out


def _attachable(B: Builder, p, reach: float = 3.0) -> bool:
    for tj, k in B.index.near(p, pad=reach + 40.0):
        t = B.lines[tj]
        if t.dead or t.no_junction:
            continue
        d, _, _ = _seg_dist(p, t.pts[k], t.pts[k + 1])
        if d - t.width / 2 <= reach:
            return True
    return False


def pattern_loops(B: Builder, name: str, cell, rng, offset: float, smooth: int, amp: float,
                  culs: bool, campus: bool, depth: int = 0, core_k: float = 0.8) -> list[int]:
    """Curvilinear loop streets at lot depth inside the cell, connectors to the frame, and
    cul-de-sacs (residential) or service drives and a landscaped core (campus), inset
    `core_k * offset` inside the loop."""
    arch = B.arch[name]
    sec = cross_section("street", arch)
    w = sec["total_width_m"]
    out: list[int] = []
    inner = G.qpoly(cell.buffer(-offset, join_style="mitre", mitre_limit=2.0))
    for part in G.parts(inner):
        if G.area(part) < (9000.0 if campus else 5000.0):
            continue
        ring = _ccw(_dedupe(G.qpoly(shapely.simplify(part, 4.0)).exterior.coords))
        if len(ring) < 4:
            continue
        ring = ring + [ring[0]]
        ring = _chaikin(ring, smooth, True)
        ring = _dedupe(_wobble(ring, rng, amp, 260.0))
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        ring = _ccw(ring)
        pieces = _clip(ring, cell)
        loop_ids = []
        for piece in pieces:
            if _plen(piece) < 60.0:
                continue
            li = B.add(Line(piece, "street", w, "campus_loop" if campus else "loop", name,
                            section=sec))
            loop_ids.append(li)
            out.append(li)
        if not loop_ids:
            continue
        # connectors from the loop to the frame
        for li in loop_ids:
            ln = B.lines[li]
            L = _plen(ln.pts)
            want = max(2 if L > 300 else 1, int(L // 260.0))
            got = 0
            tries = sorted(range(int(L // 35.0) + 1),
                           key=lambda k: abs(((k * 35.0) / L * want) % 1.0 - 0.5))
            used: list = []
            for k in tries:
                if got >= want:
                    break
                s = min(k * 35.0 + 10.0, L - 10.0)
                a, _ = _along(ln.pts, s)
                a = _pt(*a)
                if any(_dist(a, u) < 140.0 for u in used):
                    continue
                b = G.nearest(cell.exterior, Point(a))
                if _dist(a, b) > offset + 25.0 or not _attachable(B, b):
                    continue
                cj = B.add(Line([a, b], "street", w, "connector", name, section=sec))
                if B.attach(cj, -1, reach=3.0):
                    ln.inserts.append(a)
                    ln.junctions.append(a)
                    B.lines[cj].attached[0] = True
                    used.append(a)
                    got += 1
                    out.append(cj)
                else:
                    B.lines[cj].dead = True
            if not got:
                B.notes.append(f"'{name}': a loop street found no connector")
        core = G.qpoly(part.buffer(-offset * (core_k if campus else 1.0), join_style="mitre"))
        if campus:
            for c in G.parts(core):
                if G.area(c) > 3000.0:
                    B.net.cores.append((name, c))
        if G.area(core) > 60000.0 and depth < 1 and not campus:
            out += pattern_loops(B, name, G.qpoly(G.parts(core)[0].buffer(offset * 0.1)), rng,
                                 offset, smooth, amp, culs, campus, depth + 1)
            continue
        if not (culs or campus) or core.is_empty or G.area(core) < 2500.0:
            continue
        # cul-de-sacs (residential) or service drives (campus) into the core
        for li in loop_ids:
            ln = B.lines[li]
            L = _plen(ln.pts)
            s = float(uniform(rng, 40.0, 90.0))
            n_spur = 0
            while s < L - 40.0 and (not campus or n_spur < 2):
                a, t = _along(ln.pts, s)
                a = _pt(*a)
                nrm = (-t[1], t[0])  # loops run counterclockwise: left is inside
                length = float(uniform(rng, 55.0, 110.0)) if not campus else \
                    float(uniform(rng, 50.0, 90.0))
                b = _pt(a[0] + nrm[0] * length, a[1] + nrm[1] * length)
                spur = [a, b]
                okd = G.qpoly(part.buffer(-10.0, join_style="mitre"))
                good = okd.contains(LineString(spur).interpolate(0.3, normalized=True)) and \
                    okd.contains(Point(b))
                if good:
                    cls = "service" if campus else "street"
                    sec2 = cross_section(cls, arch)
                    runs = B.parallel_runs(spur, sec2["total_width_m"], 20.0, {li}, 40.0)
                    if runs and runs[0][0] == a:
                        cj = B.add(Line(runs[0], cls, sec2["total_width_m"],
                                        "drive" if campus else "cul_de_sac", name,
                                        section=sec2))
                        ln.inserts.append(a)
                        ln.junctions.append(a)
                        B.lines[cj].attached[0] = True
                        out.append(cj)
                        n_spur += 1
                s += float(uniform(rng, 95.0, 150.0)) if not campus else \
                    float(uniform(rng, L / 3, L / 2))
    return out


# ---------------------------------------------------------------------------
# Organic growth (old town, entertainment market)
# ---------------------------------------------------------------------------

class CrossField:
    """Street direction field of a district (an angle modulo 90 degrees): a base angle
    turned slowly by smooth noise, and parallel to the bank within 60 m of water."""

    STEP = 12.0
    NEAR = 60.0

    def __init__(self, B: Builder, name: str, base_deg: float, rng):
        poly = B.polygons[name]
        x0, y0, x1, y1 = poly.bounds
        s = self.STEP
        self.x0, self.y0 = x0 - s, y0 - s
        self.nx = int((x1 - x0) / s) + 3
        self.ny = int((y1 - y0) / s) + 3
        ii, jj = np.meshgrid(np.arange(self.nx), np.arange(self.ny))
        xs = self.x0 + ii.ravel() * s
        ys = self.y0 + jj.ravel() * s
        noise = G.noise2d(rng, 380.0, octaves=2)
        ang = M.radians(base_deg) + 0.55 * noise(xs, ys)
        cx, cy = M.cos(4.0 * ang), M.sin(4.0 * ang)
        bank = B.wet.boundary
        zone = G.qpoly(poly.buffer(self.NEAR, join_style="mitre"))
        near = shapely.contains_xy(G.qpoly(B.wet.buffer(self.NEAR)), xs, ys) & \
            shapely.contains_xy(zone, xs, ys)
        idx = np.nonzero(near)[0]
        if len(idx):
            pts = shapely.points(xs[idx], ys[idx])
            sl = shapely.shortest_line(bank, pts)
            cc = shapely.get_coordinates(sl).reshape(-1, 2, 2)
            # grid-snapped nearest points (machine noise stays below the snap)
            qx = np.round(cc[:, 1, 0] * 100.0) / 100.0
            qy = np.round(cc[:, 1, 1] * 100.0) / 100.0
            dx, dy = qx - xs[idx], qy - ys[idx]
            dist = np.sqrt(dx * dx + dy * dy)
            tang = M.atan2(dy, dx) + M.HALF_PI
            wgt = G.smoothstep(1.0 - dist / self.NEAR)
            tx, ty = M.cos(4.0 * tang), M.sin(4.0 * tang)
            cx[idx] = cx[idx] * (1 - wgt) + tx * wgt
            cy[idx] = cy[idx] * (1 - wgt) + ty * wgt
        a4 = M.atan2(cy, cx) / 4.0
        self.ang = np.round(a4 * 1e6) / 1e6

    def at(self, p) -> float:
        i = min(max(int(round((p[0] - self.x0) / self.STEP)), 0), self.nx - 1)
        j = min(max(int(round((p[1] - self.y0) / self.STEP)), 0), self.ny - 1)
        return float(self.ang[j * self.nx + i])


def _wrap(a: float) -> float:
    """Angle in (-180, 180] degrees."""
    a = a % 360.0
    return a - 360.0 if a > 180.0 else a


def pattern_organic(B: Builder, name: str, cell, field: CrossField, rng,
                    market: bool) -> list[int]:
    lo, hi = _block_range(B.dspec[name])
    st = style_of(B.arch[name])
    arch = B.arch[name]
    step = 8.0
    snap = 6.0
    spacing = max(0.6 * lo, 14.0)
    p_branch = 0.8 if market else 0.72
    p_alley = 0.38 if market else 0.42
    wobble = 5.0 if market else 6.5
    shapely.prepare(cell)
    # agents: [pts, heading_deg, cls, since_branch, next_branch, max_len, parent, inserts, edge]
    agents: list[dict] = []
    local = SegIndex(30.0)

    def new_agent(p, head, cls, parent):
        ml = float(uniform(rng, 2.5 * lo, 7.0 * hi)) if cls == "street" else \
            float(uniform(rng, 0.6 * lo, 1.6 * hi))
        agents.append({"pts": [p], "head": head, "cls": cls, "since": 0.0,
                       "next": float(uniform(rng, lo, hi)), "max": ml, "parent": parent,
                       "inserts": [], "end": None, "alive": True, "len": 0.0})
        return len(agents) - 1

    ring = _ccw(_dedupe(cell.exterior.coords))
    L = _plen(ring)
    s = float(uniform(rng, 0.0, hi))
    while s < L - 5.0:
        p, t = _along(ring, s)
        p = _pt(*p)
        if _attachable(B, p):
            inward = M.degrees(M.atan2(t[0], -t[1]))  # left normal of a ccw ring
            fa = M.degrees(field.at(p))
            k = round((_wrap(inward - fa)) / 90.0)
            head = fa + 90.0 * k
            if abs(_wrap(head - inward)) > 35.0:
                head = inward
            new_agent(p, head + float(uniform(rng, -8.0, 8.0)), "street", None)
        s += float(uniform(rng, 1.0 * lo, 1.9 * hi))
    budget = 40000
    qi = 0
    while qi < len(agents) and budget > 0:
        ai = qi
        a = agents[ai]
        while a["alive"] and budget > 0:
            budget -= 1
            p = a["pts"][-1]
            fa = M.degrees(field.at(p))
            k = round(_wrap(a["head"] - fa) / 90.0)
            want = fa + 90.0 * k
            diff = _wrap(want - a["head"])
            a["head"] = a["head"] + max(-10.0, min(10.0, 0.35 * diff)) + \
                float(uniform(rng, -wobble, wobble))
            h = M.radians(a["head"])
            q = _pt(p[0] + step * M.cos(h), p[1] + step * M.sin(h))
            dirv = _unit(q[0] - p[0], q[1] - p[1])
            own_last = (ai, len(a["pts"]) - 2)
            if not cell.contains(Point(q)):
                x = None
                cut = shapely.intersection(LineString([p, q]), cell.exterior)
                cands = [c for c in _points_of(cut)]
                if cands:
                    x = min(cands, key=lambda c: (_dist(c, p), c))
                if x is not None and x != p:
                    a["pts"].append(x)
                    a["end"] = "edge"
                a["alive"] = False
                break
            # crossing an existing street: end there (a junction)
            hit = None
            for aj, kk in local.near(p, q, pad=snap):
                if (aj, kk) == own_last or (aj == ai and kk >= len(a["pts"]) - 2):
                    continue
                o = agents[aj]["pts"]
                r = _cross_exact(p, q, o[kk], o[kk + 1])
                if r is None:
                    continue
                x, t = r
                if x == p:
                    continue
                if hit is None or t < hit[1]:
                    hit = (x, t, aj, kk)
            if hit is None:
                # snap onto a street that passes close by
                best = None
                for aj, kk in local.near(q, pad=snap):
                    if aj == ai and kk >= len(a["pts"]) - 4:
                        continue
                    if a["parent"] is not None and aj == a["parent"][0] and \
                            abs(kk - a["parent"][1]) <= 2 and len(a["pts"]) < 4:
                        continue
                    o = agents[aj]["pts"]
                    d, xq, _ = _seg_dist(q, o[kk], o[kk + 1])
                    if d < snap and (best is None or d < best[0] - 1e-9):
                        best = (d, _pt(*xq), aj, kk)
                if best is not None:
                    hit = (best[1], None, best[2], best[3])
            if hit is not None:
                x, _, aj, kk = hit
                o = agents[aj]["pts"]
                tdir = _unit(o[kk + 1][0] - o[kk][0], o[kk + 1][1] - o[kk][1])
                if _angle_between(dirv, tdir) >= ORGANIC_ANGLE_DEG + 5.0 and x != p:
                    # merge with a junction close by on that street
                    for y in agents[aj]["inserts"]:
                        if _dist(x, y) < 10.0:
                            x = y
                            break
                    a["pts"].append(x)
                    agents[aj]["inserts"].append(x)
                    a["end"] = "junction"
                a["alive"] = False
                break
            # running alongside another street: stop here (a dead end)
            close = False
            for aj, kk in local.near(q, pad=spacing):
                if aj == ai and kk >= len(a["pts"]) - 6:
                    continue
                if a["parent"] is not None and aj == a["parent"][0] and len(a["pts"]) < 5:
                    continue
                o = agents[aj]["pts"]
                d, _, _ = _seg_dist(q, o[kk], o[kk + 1])
                if d < spacing:
                    tdir = _unit(o[kk + 1][0] - o[kk][0], o[kk + 1][1] - o[kk][1])
                    if _angle_between(dirv, tdir) < 30.0:
                        close = True
                        break
            if close or _too_close_frame(B, q, a["cls"], spacing * 0.6, dirv):
                a["alive"] = False
                break
            a["pts"].append(q)
            k_new = len(a["pts"]) - 2
            for key in local._keys(p, q):
                local.buckets.setdefault(key, []).append((ai, k_new))
            a["len"] += step
            a["since"] += step
            if a["len"] >= a["max"]:
                a["alive"] = False
                break
            if a["since"] >= a["next"]:
                a["since"] = 0.0
                a["next"] = float(uniform(rng, lo, hi))
                for side in (1.0, -1.0):
                    if rng.uniform() < p_branch:
                        cls = "alley" if rng.uniform() < p_alley else "street"
                        if a["cls"] == "alley":
                            cls = "alley"
                        new_agent(q, a["head"] + side * (90.0 + float(uniform(rng, -24.0, 24.0))),
                                  cls, (ai, k_new))
                        agents[-1]["inserts"] = []
                        a["inserts"].append(q)
        qi += 1
    # agents -> lines
    out = []
    ids: dict[int, int] = {}
    for ai, a in enumerate(agents):
        pts = _dedupe(a["pts"])
        if len(pts) < 2:
            continue
        L = _plen(pts)
        if L < (10.0 if a["cls"] == "alley" else 16.0) and a["end"] != "junction":
            continue
        sec = cross_section(a["cls"], arch)
        li = B.add(Line(pts, a["cls"], sec["total_width_m"],
                        "organic" if a["cls"] == "street" else "alley", name, section=sec))
        ids[ai] = li
        out.append(li)
    for ai, li in ids.items():
        a = agents[ai]
        ln = B.lines[li]
        ln.inserts += [x for x in a["inserts"]]
        ln.junctions += [x for x in a["inserts"]]
        if a["parent"] is None:
            B.attach(li, 0, reach=3.0)
        else:
            ln.attached[0] = True
        if a["end"] == "edge":
            B.attach(li, -1, reach=3.0)
        elif a["end"] == "junction":
            ln.attached[1] = True
    # branches whose parent was dropped start on nothing: drop their first link
    for ai, li in ids.items():
        par = agents[ai]["parent"]
        if par is not None and par[0] not in ids:
            B.lines[li].attached[0] = False
    del st
    return out


def _points_of(g) -> list[tuple[float, float]]:
    out = []
    for p in shapely.get_parts(g):
        if p.geom_type == "Point":
            out.append(_pt(p.x, p.y))
        elif p.geom_type in ("LineString", "MultiPoint", "MultiLineString"):
            out += [_pt(x, y) for x, y in shapely.get_coordinates(p)]
    return out


def _too_close_frame(B: Builder, q, cls: str, gap: float, dirv) -> bool:
    """A growing street runs alongside a frame road (inside the cell, near its edge)."""
    w = 4.0 if cls == "alley" else 10.0
    for tj, k in B.index.near(q, pad=gap + 30.0):
        t = B.lines[tj]
        if t.dead:
            continue
        d, _, _ = _seg_dist(q, t.pts[k], t.pts[k + 1])
        if d < (t.width + w) / 2 + gap:
            tdir = _unit(t.pts[k + 1][0] - t.pts[k][0], t.pts[k + 1][1] - t.pts[k][1])
            if _angle_between(dirv, tdir) < 25.0:
                return True
    return False


# ---------------------------------------------------------------------------
# Alleys and service lanes inside large blocks
# ---------------------------------------------------------------------------

def _obb(poly):
    """(center, long axis unit u, short axis unit v, length, width) of the minimum rotated
    rectangle (snapped)."""
    # GEOS's rotating calipers divide by zero and compare a NaN for a degenerate caliper
    # (the result does not use either); arm64 raises the IEEE flags there and numpy turns
    # them into RuntimeWarnings, hundreds per build on the M4 Mac
    with np.errstate(divide="ignore", invalid="ignore"):
        r = G.qpoly(shapely.minimum_rotated_rectangle(poly))
    c = _dedupe(r.exterior.coords) if not r.is_empty and r.geom_type == "Polygon" else []
    if len(c) < 4:
        x0, y0, x1, y1 = poly.bounds
        c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    c = c[:4]
    e0 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e1 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l0 = math.sqrt(e0[0] * e0[0] + e0[1] * e0[1])
    l1 = math.sqrt(e1[0] * e1[0] + e1[1] * e1[1])
    cx = (c[0][0] + c[2][0]) / 2
    cy = (c[0][1] + c[2][1]) / 2
    if l0 >= l1:
        u, L, W = _unit(*e0), l0, l1
    else:
        u, L, W = _unit(*e1), l1, l0
    if u[0] < 0 or (u[0] == 0 and u[1] < 0):
        u = (-u[0], -u[1])
    return (cx, cy), u, (-u[1], u[0]), L, W


def block_alleys(B: Builder, name: str, cell, ids: list[int], rng) -> list[int]:
    arch = B.arch[name]
    st = style_of(arch)
    pat = B.dspec[name].street_pattern or st.pattern
    lo, hi = _block_range(B.dspec[name])
    if st.alley_rate <= 0:
        return []
    lines = [B.lines[i] for i in ids if not B.lines[i].dead]
    if not lines:
        return []
    cache = getattr(B, "_row_cache", None)
    if cache is not None and cache[0] is cell and cache[1] == list(ids):
        row = cache[2]  # the infill pass just built it
    else:
        row = _buffer([ln.pts for ln in lines], [ln.width for ln in lines])
    subs = [p for p in G.parts(G.diff(cell, row)) if G.area(p) > 0]
    out = []
    amax = st.lot_area[1]
    for sb in subs:
        A = G.area(sb)
        (cx, cy), u, v, L, W = _obb(sb)
        cands = []
        if st.organic:
            if A < 3.0 * amax or rng.uniform() > st.alley_rate:
                continue
            off = float(uniform(rng, -0.15, 0.15)) * W
            if L > 1.9 * W:
                cands.append(("alley", [_pt(cx - u[0] * (L / 2 + 8) + v[0] * off,
                                            cy - u[1] * (L / 2 + 8) + v[1] * off),
                                        _pt(cx + u[0] * (L / 2 + 8) + v[0] * off,
                                            cy + u[1] * (L / 2 + 8) + v[1] * off)]))
            else:
                side = 1.0 if rng.uniform() < 0.5 else -1.0
                du = float(uniform(rng, -0.2, 0.2)) * L
                a = (cx + u[0] * du - side * v[0] * (W / 2 + 8),
                     cy + u[1] * du - side * v[1] * (W / 2 + 8))
                b = (cx + u[0] * du + side * v[0] * W * 0.08,
                     cy + u[1] * du + side * v[1] * W * 0.08)
                cands.append(("alley", [_pt(*a), _pt(*b)]))
            if A > 8.0 * amax and L > 1.2 * W:
                du = (0.3 if rng.uniform() < 0.5 else -0.3) * L
                a = (cx + u[0] * du + v[0] * (W / 2 + 8), cy + u[1] * du + v[1] * (W / 2 + 8))
                b = (cx + u[0] * du - v[0] * W * 0.05, cy + u[1] * du - v[1] * W * 0.05)
                cands.append(("alley", [_pt(*a), _pt(*b)]))
        elif pat == "superblocks":
            if A < 15000.0:
                continue
            d = 0.55 * W
            a0 = (cx - u[0] * L / 4 - v[0] * (W / 2 + 8), cy - u[1] * L / 4 - v[1] * (W / 2 + 8))
            b0 = (cx + u[0] * L / 4 - v[0] * (W / 2 + 8), cy + u[1] * L / 4 - v[1] * (W / 2 + 8))
            a1 = (cx - u[0] * L / 4 + v[0] * (d - W / 2), cy - u[1] * L / 4 + v[1] * (d - W / 2))
            b1 = (cx + u[0] * L / 4 + v[0] * (d - W / 2), cy + u[1] * L / 4 + v[1] * (d - W / 2))
            cands.append(("service_lane", [_pt(*a0), _pt(*a1), _pt(*b1), _pt(*b0)], "service"))
        else:
            limit = {"large_grid": 230.0, "service_roads": 300.0}.get(pat, 1.1 * hi)
            if L < limit or W < 0.7 * lo or rng.uniform() > st.alley_rate:
                continue
            off = float(uniform(rng, -0.1, 0.1)) * W
            cls = "service" if pat in ("large_grid", "service_roads") else "alley"
            cands.append(("service_lane" if cls == "service" else "alley",
                          [_pt(cx - u[0] * (L / 2 + 8) + v[0] * off,
                               cy - u[1] * (L / 2 + 8) + v[1] * off),
                           _pt(cx + u[0] * (L / 2 + 8) + v[0] * off,
                               cy + u[1] * (L / 2 + 8) + v[1] * off)], cls))
        for cand in cands:
            role, pts = cand[0], cand[1]
            cls = cand[2] if len(cand) > 2 else "alley"
            sec = cross_section(cls, arch)
            w = sec["total_width_m"]
            for piece in _clip(pts, sb):
                if _plen(piece) < 12.0:
                    continue
                for run in B.parallel_runs(piece, w, max(6.0, 0.18 * W), set(), 12.0):
                    li = B.add(Line(run, cls, w, role, name, section=sec))
                    ok = False
                    for end in (0, -1):
                        p = B.lines[li].pts[end]
                        if G.dist(sb.exterior, Point(p)) <= 0.6:
                            ok = B.attach(li, end, reach=3.0, angle=ORGANIC_ANGLE_DEG
                                          if st.organic else GRID_ANGLE_DEG) or ok
                    if not ok:
                        B.lines[li].dead = True
                        B.index.remove_line(li)
                        continue
                    out.append(li)
    return out


def block_limits(arch: str, lo: float, hi: float) -> tuple[float, float]:
    """(width, length) beyond which a block gets an infill street: wider than two lots deep
    (interior lots would have no frontage), or much longer than the archetype block."""
    st = style_of(arch)
    w = max(2.3 * st.lot_depth[1], hi) if st.perimeter else 2.3 * st.lot_depth[1]
    return w, max(1.6 * hi, w)


def infill(B: Builder, name: str, cell, ids: list[int], rng) -> list[int]:
    """Through streets across blocks that the pattern left too wide or too long (a loop that
    found no connector, grid lines dropped beside an avenue), until every block is within
    the archetype limits: each cut runs across the long side through the middle."""
    arch = B.arch[name]
    lo, hi = _block_range(B.dspec[name])
    w_lim, l_lim = block_limits(arch, lo, hi)
    organic = style_of(arch).organic
    cls = "alley" if organic else "street"  # organic districts: crooked alleys, not streets
    sec = cross_section(cls, arch)
    w = sec["total_width_m"]
    out: list[int] = []
    lines = [B.lines[i] for i in ids if not B.lines[i].dead]
    row = _buffer([ln.pts for ln in lines], [ln.width for ln in lines]) if lines \
        else Polygon()
    for _ in range(10):
        subs = sorted((p for p in G.parts(G.diff(cell, row)) if G.area1(p) > 0),
                      key=lambda p: (-G.area1(p), G.qbounds(p)))
        added = 0
        new: list[int] = []
        for sb in subs:
            (cx, cy), u, v, L, W = _obb(sb)
            if L > l_lim or (W > w_lim and L > 1.2 * w_lim):
                d, span = u, W        # cut across the long side
            elif W > w_lim:
                d, span = v, L        # a long, wide block: cut along it
            else:
                continue
            t = float(uniform(rng, -0.1, 0.1)) * (L if d is u else W)
            ax = (-d[1], d[0])
            if organic:  # turned and bent a little
                tw = M.radians(float(uniform(rng, -18.0, 18.0)))
                ax = (ax[0] * M.cos(tw) - ax[1] * M.sin(tw), ax[0] * M.sin(tw) + ax[1] * M.cos(tw))
            ext = span / 2 + w + 10.0
            mx, my = cx + d[0] * t, cy + d[1] * t
            bend = float(uniform(rng, -0.12, 0.12)) * span if organic else 0.0
            pts = [_pt(mx - ax[0] * ext, my - ax[1] * ext),
                   _pt(mx + d[0] * bend, my + d[1] * bend),
                   _pt(mx + ax[0] * ext, my + ax[1] * ext)]
            for piece in _clip(pts, sb):
                if _plen(piece) < 30.0:
                    continue
                li = B.add(Line(piece, cls, w, "infill", name, section=sec))
                for end in (0, -1):
                    if G.dist(sb.exterior, Point(B.lines[li].pts[end])) <= 0.6:
                        B.attach(li, end, reach=3.0)
                out.append(li)
                added += 1
                new.append(li)
        if not added:
            break
        news = [B.lines[i] for i in new if not B.lines[i].dead]
        row = G.union([row, _buffer([ln.pts for ln in news], [ln.width for ln in news])])
    B._row_cache = (cell, list(ids) + out, row)
    return out


# ---------------------------------------------------------------------------
# Districts
# ---------------------------------------------------------------------------

GRID_PATTERNS = ("rotated_grid", "grid", "grid_ring_park", "superblocks", "large_grid",
                 "service_roads")


def fill_district(B: Builder, name: str) -> list[int]:
    d = B.dspec[name]
    arch = d.archetype
    st = style_of(arch)
    pat = d.street_pattern or st.pattern
    lo, hi = _block_range(d)
    angle = district_angle(B, name)
    B.net.angles[name] = angle
    cells = district_cells(B, name)
    B.net.cells[name] = cells
    out: list[int] = []
    clearance = max(12.0, 0.4 * lo)
    fam = None
    if pat in GRID_PATTERNS:
        su, sv, stagger = {
            "rotated_grid": ((lo + 10.0, hi), (lo, 0.9 * hi), False),
            "grid": ((lo + 10.0, hi), (lo, hi), False),
            "grid_ring_park": ((lo + 10.0, hi), (lo + 10.0, hi), False),
            "superblocks": ((lo + 30.0, hi), (lo + 30.0, hi), False),
            "large_grid": ((lo, lo + 60.0), (max(hi - 60.0, lo), hi), True),
            "service_roads": ((lo, hi), (lo, hi), True),
        }[pat]
        fam = GridFamily(B, name, angle, su, sv, stagger, _rng(d.seed, 11))
    field_ = CrossField(B, name, angle, _rng(d.seed, 12)) if pat == "organic" else None
    center = None
    if pat == "radial_ring":
        hub = [s for s in B.sites if s.district == name and s.kind == "transit_nexus"]
        if hub:
            center = G.centroid(hub[0].polygon)
            r0 = max(_dist(center, c) for c in hub[0].polygon.exterior.coords) + RESERVE_RING_M
        else:
            land = B.free[name]
            p = shapely.ops.polylabel(G.parts(land)[0], 5.0) if not land.is_empty else \
                Point(G.centroid(B.polygons[name]))
            center, r0 = _pt(p.x, p.y), 30.0
    for ci, cell in enumerate(cells):
        crng = _rng(d.seed, 13, ci)
        if pat in GRID_PATTERNS:
            ids = pattern_grid(B, name, cell, fam, clearance, max(25.0, 0.3 * lo))
        elif pat == "organic":
            ids = pattern_organic(B, name, cell, field_, crng, arch == "entertainment_market")
        elif pat == "curvilinear":
            ids = pattern_loops(B, name, cell, crng, sum(st.lot_depth) / 2 + 8.0, 2, 7.0,
                                True, False)
        elif pat == "campus_loops":
            ids = pattern_loops(B, name, cell, crng, 62.0, 3, 12.0, False, True)
            if not ids:  # a small cell: a tighter loop
                ids = pattern_loops(B, name, cell, crng, 40.0, 3, 8.0, False, True, core_k=0.5)
        elif pat == "radial_ring":
            ids = pattern_radial(B, name, cell, center, r0, max(lo + 25.0, 80.0),
                                 max(hi, lo + 50.0), _rng(d.seed, 14), clearance)
        else:
            ids = []
        if not (pat == "campus_loops" and ids):  # campus grounds around a loop stay open
            ids += infill(B, name, cell, ids, crng)
        ids += block_alleys(B, name, cell, ids, crng)
        out += ids
    T.detail(f"streets/{B.did[name]}", [B.lines[i].pts for i in out])
    return out


# ---------------------------------------------------------------------------
# Footbridges
# ---------------------------------------------------------------------------

def footbridges(B: Builder) -> list[int]:
    bodies = []
    for w in B.ww.items:
        if w.kind in ("canal", "creek", "inlet", "marina") and w.centerline is not None:
            bodies.append((w.id, _dedupe(w.centerline.coords)))
    for b in B.h.bodies:
        if b.kind == "separation":
            bodies.append((b.id, _dedupe(b.centerline.coords)))
    bridges = [LineString([(x, y) for x, y, _ in b["line"]]) for b in B.roads.bridges]
    road_br = G.line_union(bridges) if bridges else LineString()
    placed: list[tuple[float, float]] = []
    out = []
    shapely.prepare(B.free_all)
    for bi, (wid, cl) in enumerate(bodies):
        if len(cl) < 2:
            continue
        # M10: a body that reaches a regenerated district keeps its held footbridges and
        # gets new ones in the district only
        held = B.frame is not None and B.frame.touches(cl)
        if held:
            placed += B.frame.inject_footbridges(B, wid, cl)
        rng = _rng(B.spec.seed or 0, 17, bi)
        L = _plen(cl)
        s = float(uniform(rng, 60.0, 140.0))
        while s < L - 30.0:
            p, t = _along(cl, s)
            p = _pt(*p)
            nrm = (-t[1], t[0])
            m = FOOTBRIDGE_MAX_SPAN_M
            ray = LineString([_pt(p[0] - nrm[0] * m, p[1] - nrm[1] * m),
                              _pt(p[0] + nrm[0] * m, p[1] + nrm[1] * m)])
            runs = _lines_of(shapely.intersection(ray, B.wet))
            run = None
            for r in runs:
                if LineString(r).distance(Point(p)) < 0.5:
                    run = r
            if run is None or (not road_br.is_empty and road_br.distance(Point(p)) < 120.0) \
                    or any(_dist(p, x) < 110.0 for x in placed):
                s += 30.0
                continue
            a, b = run[0], run[-1]
            span = _dist(a, b)
            if span < 4.0 or span > m - 2.0:
                s += 30.0
                continue
            ab = _unit(b[0] - a[0], b[1] - a[1])
            a2 = _pt(a[0] - ab[0] * 3.0, a[1] - ab[1] * 3.0)
            b2 = _pt(b[0] + ab[0] * 3.0, b[1] + ab[1] * 3.0)
            if not (B.free_all.contains(Point(a2)) and B.free_all.contains(Point(b2))):
                s += 30.0
                continue
            seg = LineString([a2, b2])
            if B.closed.intersects(seg) or seg.intersection(B.wet).length > span + 1.0 or (
                    held and not B.frame.zone.contains(seg)):
                s += 30.0
                continue
            dist_name = next((n for n in sorted(B.free, key=lambda n: B.did[n])
                              if B.free[n].contains(Point(a2))), None)
            li = B.add(Line([a2, b2], "footbridge", FOOTBRIDGE_W, "footbridge", dist_name,
                            section=cross_section("footbridge", None), crosses=wid,
                            water_class="canal"))
            for k, end in ((0, 0), (1, -1)):
                if not B.attach(li, end, reach=3.0, angle=ORGANIC_ANGLE_DEG):
                    B.attach(li, end, reach=22.0, angle=ORGANIC_ANGLE_DEG)
            ok = all(B.lines[li].attached)
            if not ok:
                B.lines[li].dead = True
                B.index.remove_line(li)
                s += 30.0
                continue
            placed.append(p)
            out.append(li)
            s += float(uniform(rng, *FOOTBRIDGE_STEP_M))
    T.detail("streets/footbridges", [B.lines[i].pts for i in out])
    return out


# ---------------------------------------------------------------------------
# Dead ends, gates
# ---------------------------------------------------------------------------

def link_dead_ends(B: Builder) -> None:
    """Free ends of local streets close to another road join it (within 25 m, at a legal
    junction); the M1b avenues that stop at a megasite gate join the service ring."""
    for li in range(B.n_primary, len(B.lines)):
        ln = B.lines[li]
        if ln.dead or ln.cls == "footbridge":
            continue
        # grid dead ends run on to the next road; port and spaceport stubs stay as yard spurs
        grid = ln.district is not None and not style_of(B.arch[ln.district]).organic and \
            B.arch[ln.district] not in ("industrial_port", "spaceport") and \
            ln.role.startswith(("grid", "infill"))
        for k, end in ((0, 0), (1, -1)):
            if not ln.attached[k]:
                if not B.attach(li, end, reach=22.0) and grid:
                    B.extend_ray(li, end, 150.0)
    deg: dict = {}
    for n in B.roads.nodes:
        if n["attrs"].get("kind") == "end":
            deg[(G.q(n["position"][0]), G.q(n["position"][1]))] = n
    for p in sorted(deg):
        best = None
        for tj, k in B.index.near(p, pad=40.0):
            t = B.lines[tj]
            if tj < B.n_primary or t.dead or t.cls in ("footbridge", "pedestrian"):
                continue
            d, q, _ = _seg_dist(p, t.pts[k], t.pts[k + 1])
            if d <= 35.0 and (best is None or d < best[0] - 1e-9):
                best = (d, tj, _pt(*q))
        if best is None or best[0] < 0.5:
            continue
        _, tj, q = best
        t = B.lines[tj]
        near = [j for j in t.junctions if _dist(j, q) < MIN_JUNCTION_GAP_M]
        if near:
            q = min(near, key=lambda j: (_dist(j, q), j))
        if B.frame is not None and t.district == B.frame.name and B.frame.holds(t, q):
            q = B.frame.node_on(t, q)  # M10: a gate link onto a held road of the district
            if q is None:
                continue
        link = LineString([p, q])
        if B.closed.intersects(link) and link.intersection(B.closed).length > 0.5:
            continue
        if link.intersection(B.wet).length > 0.5:
            continue
        cls = "service" if t.cls == "service" else "street"
        sec = cross_section(cls, B.arch.get(t.district) if t.district else None)
        li = B.add(Line([p, q], cls, sec["total_width_m"], "gate_link", t.district,
                        section=sec))
        B.lines[li].attached = [True, True]
        t.inserts.append(q)
        if q not in t.junctions:
            t.junctions.append(q)


def _pairs(idx):
    """STRtree query pairs in index order: the tree returns each input's hits in tree order,
    which follows a C++ std::sort of the envelopes and so the standard library's tie order
    (libc++ on macOS, libstdc++ on Linux)."""
    a, b = idx
    k = np.lexsort((b, a))
    return a[k], b[k]


def _components(B: Builder) -> tuple[list[int], dict[int, int]]:
    """Connected groups of lines (by their shared points, before noding): the line indices
    of the group that holds the primary network, and every line's group root."""
    live = [i for i, ln in enumerate(B.lines) if not ln.dead and len(ln.pts) >= 2]
    parent = {i: i for i in live}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict = {}
    for i in live:
        for p in [B.lines[i].pts[0], B.lines[i].pts[-1]] + B.lines[i].inserts:
            owner.setdefault(p, []).append(i)
    for p, ids in owner.items():
        for j in ids[1:]:
            parent[find(j)] = find(ids[0])
    # crossings (grid lines cross without either one ending on the other)
    seg_line, coords = [], []
    for i in live:
        pts = B.lines[i].pts
        for k in range(len(pts) - 1):
            seg_line.append(i)
            coords.append([pts[k], pts[k + 1]])
    geoms = shapely.linestrings(np.array(coords, dtype=np.float64))
    a_idx, b_idx = _pairs(shapely.STRtree(geoms).query(geoms, predicate="intersects"))
    for x, y in zip(a_idx.tolist(), b_idx.tolist()):
        li, lj = seg_line[x], seg_line[y]
        if li != lj and not (li < B.n_primary and lj < B.n_primary):
            parent[find(li)] = find(lj)
    roots = {i: find(i) for i in live}
    main = roots[0] if 0 in roots else None
    return [i for i in live if roots[i] == main], roots


def join_islands(B: Builder) -> bool:
    """Groups of local streets that reach nothing (a seed street that found no junction, a
    loop without a connector) join the main network from their free ends (within 25 m),
    else from any point within 40 m by a short link."""
    main, roots = _components(B)
    main_set = set(main)
    groups: dict[int, list[int]] = {}
    for i, r in roots.items():
        if i not in main_set:
            groups.setdefault(r, []).append(i)
    if not groups:
        return False
    changed = False
    for r in sorted(groups, key=lambda r: min(groups[r])):
        done = False
        for li in sorted(groups[r]):
            ln = B.lines[li]
            if ln.cls == "footbridge":
                continue
            for k, end in ((0, 0), (1, -1)):
                if not ln.attached[k] and B.attach(li, end, reach=25.0, targets=main_set):
                    done = True
                    break
            if done:
                break
        if not done:
            done = _link_group(B, groups[r], main_set)
        if not done:
            # last resort: a right-in, right-out access onto a highway
            for li in sorted(groups[r]):
                ln = B.lines[li]
                if ln.cls in PEDESTRIAN:
                    continue
                for k, end in ((0, 0), (1, -1)):
                    if not ln.attached[k] and B.attach(li, end, reach=25.0, targets=main_set,
                                                       allow_highway=True):
                        done = True
                        B.notes.append(f"'{ln.district}': streets reach the network only "
                                       "by a highway access")
                        break
                if done:
                    break
        changed = changed or done
    return changed


def _link_group(B: Builder, group: list[int], main_set: set) -> bool:
    """A short perpendicular link (up to 40 m) from a group's road to the main network."""
    for li in sorted(group):
        ln = B.lines[li]
        if ln.cls in PEDESTRIAN:
            continue
        L = _plen(ln.pts)
        n = max(int(L / 15.0), 1)
        for k in range(n + 1):
            a, _ = _along(ln.pts, L * k / n)
            a = _pt(*a)
            best = None
            for tj, kk in B.index.near(a, pad=55.0):
                if tj not in main_set:
                    continue
                t = B.lines[tj]
                if t.dead or t.no_junction:
                    continue
                d, q, _ = _seg_dist(a, t.pts[kk], t.pts[kk + 1])
                if d - t.width / 2 <= 40.0 and (best is None or d < best[0] - 1e-9):
                    best = (d, tj, _pt(*q))
            if best is None:
                continue
            d, tj, q = best
            t = B.lines[tj]
            if not B._legal(t, q, _project(t.pts, q)[0]):
                continue
            near = [j for j in t.junctions if _dist(j, q) < MIN_JUNCTION_GAP_M]
            if near:
                q = min(near, key=lambda j: (_dist(j, q), j))
            if B._renewed(ln) and B.frame.holds(t, q):
                continue  # M10: no new link from the district onto a held road
            link = LineString([a, q])
            if _dist(a, q) < 1.0 or link.intersection(B.wet).length > 0.5 or (
                    B.closed.intersects(link) and link.intersection(B.closed).length > 0.5):
                continue
            ta = _unit(*(lambda u: (u[0], u[1]))(_along(ln.pts, L * k / n)[1]))
            if _angle_between(ta, _unit(q[0] - a[0], q[1] - a[1])) < GRID_ANGLE_DEG or \
                    _angle_between(B._tangent(t.pts, q), _unit(q[0] - a[0], q[1] - a[1])) < \
                    GRID_ANGLE_DEG:
                continue
            sec = ln.section if ln.cls in ("street", "service") else \
                cross_section("street", B.arch.get(ln.district))
            cj = B.add(Line([a, q], "street" if ln.cls != "service" else "service",
                            sec["total_width_m"], "connector", ln.district, section=sec))
            B.lines[cj].attached = [True, True]
            ln.inserts.append(a)
            ln.junctions.append(a)
            t.inserts.append(q)
            if q not in t.junctions:
                t.junctions.append(q)
            return True
    return False


# ---------------------------------------------------------------------------
# Noding: one planar graph of every road (exact integer predicates)
# ---------------------------------------------------------------------------

def _icoord(p) -> tuple[int, int]:
    return (round(p[0] * SCALE), round(p[1] * SCALE))


def _locate(pts, P) -> tuple[int, Fraction] | None:
    """Segment index and exact parameter of grid point P on a polyline (within 2 cm)."""
    Pi = _icoord(P)
    for k in range(len(pts) - 1):
        A, Bq = _icoord(pts[k]), _icoord(pts[k + 1])
        dx, dy = Bq[0] - A[0], Bq[1] - A[1]
        L2 = dx * dx + dy * dy
        if L2 == 0:
            continue
        ex, ey = Pi[0] - A[0], Pi[1] - A[1]
        dot = ex * dx + ey * dy
        if dot < 0 or dot > L2:
            continue
        cross = ex * dy - ey * dx
        if cross * cross <= 4 * L2:
            return k, Fraction(dot, L2)
    return None


def node_lines(B: Builder) -> tuple[list[tuple[list, int]], list[str]]:
    """Split every line where another line meets or crosses it. Returns edges as (points,
    line index)."""
    notes: list[str] = []
    live = [i for i, ln in enumerate(B.lines) if not ln.dead and len(ln.pts) >= 2]
    if B.frame is not None:
        # M10: a held road keeps every node it had on the district's border, used or not
        # (elsewhere its nodes come back as they came)
        for i in live:
            B.lines[i].inserts += B.frame.border_nodes(B.lines[i])
    seg_line, seg_k, coords = [], [], []
    for i in live:
        pts = B.lines[i].pts
        for k in range(len(pts) - 1):
            seg_line.append(i)
            seg_k.append(k)
            coords.append([pts[k], pts[k + 1]])
    geoms = shapely.linestrings(np.array(coords, dtype=np.float64))
    tree = shapely.STRtree(geoms)
    a_idx, b_idx = _pairs(tree.query(geoms, predicate="intersects"))
    crossings = 0
    cuts: dict[int, list] = {}
    self_cuts: dict[int, list] = {}
    for x, y in zip(a_idx.tolist(), b_idx.tolist()):
        if x >= y:
            continue
        li, lj = seg_line[x], seg_line[y]
        if li < B.n_primary and lj < B.n_primary:
            continue  # primary roads are noded already (and cross over water unnoded)
        if li == lj:
            n = len(B.lines[li].pts) - 1
            closed = B.lines[li].pts[0] == B.lines[li].pts[-1]
            if abs(seg_k[x] - seg_k[y]) <= 1 or (closed and {seg_k[x], seg_k[y]} == {0, n - 1}):
                continue
        r = _cross_exact(coords[x][0], coords[x][1], coords[y][0], coords[y][1])
        if r is None:
            continue
        p = r[0]
        # a road that ends on another (a T) meets it at its own end point, not 1 cm off
        snapped = False
        for e in (B.lines[li].pts[0], B.lines[li].pts[-1], B.lines[lj].pts[0],
                  B.lines[lj].pts[-1]):
            if abs(e[0] - p[0]) <= 0.03 and abs(e[1] - p[1]) <= 0.03:
                p = e
                snapped = True
                break
        if not snapped and (li < B.n_primary) != (lj < B.n_primary):
            # a local road crossing a primary road where no junction was allowed: it stops
            # on both sides instead (cut below), no node; under a viaduct it passes under
            loc, prim = (lj, li) if li < B.n_primary else (li, lj)
            if under_deck(B.lines[prim], p):
                continue
            cuts.setdefault(loc, []).append((p, B.lines[prim].width / 2 + 3.0))
            crossings += 1
            continue
        if B.frame is not None and not snapped and li != lj and p not in B.frame.nodes:
            hi_, hj = B.frame.holds(B.lines[li], p), B.frame.holds(B.lines[lj], p)
            if hi_ != hj:
                # M10: a new street crossing a held road stops on both sides of it
                held, new = (li, lj) if hi_ else (lj, li)
                cuts.setdefault(new, []).append((p, B.lines[held].width / 2 + 3.0))
                crossings += 1
                continue
        if li == lj and not snapped:
            # a line crossing itself is cut at both places (an insert is found only once)
            self_cuts.setdefault(li, []).append((seg_k[x], p))
            self_cuts.setdefault(li, []).append((seg_k[y], p))
            continue
        B.lines[li].inserts.append(p)
        B.lines[lj].inserts.append(p)
    if crossings:
        notes.append(f"{crossings} local roads stopped short of a primary road they crossed "
                     "where no junction is allowed")
    edges = []
    for i in live:
        ln = B.lines[i]
        pts = ln.pts
        marks: dict[int, list] = {}
        cuts_at_vertex = set()
        for P in sorted(set(ln.inserts)):
            if P in pts:
                cuts_at_vertex.add(pts.index(P))
                if P == pts[-1]:
                    cuts_at_vertex.add(len(pts) - 1)
                continue
            loc = _locate(pts, P)
            if loc is None:
                notes.append(f"junction point {P} is not on its road; skipped")
                continue
            marks.setdefault(loc[0], []).append((loc[1], P))
        for k, P in sorted(self_cuts.get(i, [])):
            if P in pts:
                cuts_at_vertex.add(pts.index(P))
                continue
            A, Bq, Pi = _icoord(pts[k]), _icoord(pts[k + 1]), _icoord(P)
            dx, dy = Bq[0] - A[0], Bq[1] - A[1]
            L2 = dx * dx + dy * dy
            if L2 == 0:
                continue
            t = Fraction((Pi[0] - A[0]) * dx + (Pi[1] - A[1]) * dy, L2)
            marks.setdefault(k, []).append((min(max(t, Fraction(0)), Fraction(1)), P))
        new: list = []
        cut_idx = []
        for k in range(len(pts)):
            if k in cuts_at_vertex:
                cut_idx.append(len(new))
            new.append(pts[k])
            for _, P in sorted(marks.get(k, [])):
                if P != new[-1]:
                    cut_idx.append(len(new))
                    new.append(P)
        idx = sorted(set([0, len(new) - 1] + cut_idx))
        for a, b in zip(idx[:-1], idx[1:]):
            piece = _dedupe(new[a:b + 1])
            if len(piece) < 2:
                continue
            for part in _cut_out(piece, cuts.get(i, [])):
                edges.append((part, i))
    return edges, notes


def _cut_out(pts, cuts) -> list:
    """The polyline without the stretches within d of each cut point (p, d) on it."""
    parts = [pts]
    for p, d in cuts:
        nxt = []
        for q in parts:
            s, dist, _, _ = _project(q, p)
            if dist > 0.05:
                nxt.append(q)
                continue
            L = _plen(q)
            if s - d > 1.0:
                nxt.append(_substring(q, 0.0, s - d))
            if s + d < L - 1.0:
                nxt.append(_substring(q, s + d, L))
        parts = [x for x in nxt if len(x) >= 2]
    return parts


# ---------------------------------------------------------------------------
# Graph cleanup and output
# ---------------------------------------------------------------------------

def _mergeable(B: Builder, i: int, j: int) -> bool:
    if i == j:
        return True
    a, b = B.lines[i], B.lines[j]
    if a.primary is not None or b.primary is not None:
        return False
    return (a.cls == b.cls and a.district == b.district and a.width == b.width and
            a.name == b.name and a.crosses is None and b.crosses is None)


def _merge_and_trim(B: Builder, edges):
    """Degree-2 joints merged (same road), tiny dangling local stubs removed."""
    for _ in range(6):
        changed = False
        # merge degree-2 nodes
        ends: dict = {}
        for e, (pts, li) in enumerate(edges):
            ends.setdefault(pts[0], []).append(e)
            ends.setdefault(pts[-1], []).append(e)
        alive = [True] * len(edges)
        for p in sorted(ends):
            es = [e for e in ends[p] if alive[e]]
            if len(es) != 2 or es[0] == es[1]:
                continue
            if B.frame is not None and p in B.frame.nodes:
                continue  # M10: a held node stays
            e1, e2 = es
            (p1, l1), (p2, l2) = edges[e1], edges[e2]
            if not _mergeable(B, l1, l2):
                continue
            if p1[0] == p1[-1] or p2[0] == p2[-1]:
                continue
            a = p1 if p1[-1] == p else p1[::-1]
            b = p2 if p2[0] == p else p2[::-1]
            merged = a + b[1:]
            if merged[0] == merged[-1]:
                continue
            edges[e1] = (merged, l1)
            alive[e2] = False
            for q in (merged[0], merged[-1]):
                ends[q] = [e1 if x == e2 else x for x in ends[q]]
            changed = True
        edges = [e for k, e in enumerate(edges) if alive[k]]
        # drop tiny dead-end stubs of local roads
        deg: dict = {}
        for pts, li in edges:
            for q in (pts[0], pts[-1]):
                deg[q] = deg.get(q, 0) + 1
        keep = []
        for pts, li in edges:
            ln = B.lines[li]
            short = _plen(pts) < 6.0
            dangling = deg[pts[0]] == 1 or deg[pts[-1]] == 1
            if ln.primary is None and short and dangling and not _held(B, pts):
                changed = True
                continue
            keep.append((pts, li))
        edges = keep
        if not changed:
            break
    return edges


def _leg_dir(pts, at_start: bool):
    q = pts if at_start else pts[::-1]
    p, _ = _along(q, min(10.0, _plen(q) / 2))
    return _unit(p[0] - q[0][0], p[1] - q[0][1])


def _district_at(B: Builder, p) -> str | None:
    if not hasattr(B, "_dzones"):
        B._dzones = []
        for n in sorted(B.polygons, key=lambda n: B.did[n]):
            z = G.qpoly(B.polygons[n].buffer(5.0, join_style="mitre"))
            shapely.prepare(z)
            B._dzones.append((n, z))
    pt = Point(p)
    for n, z in B._dzones:
        if z.contains(pt):
            return n
    return None


def _trimmed(pts, at_start: bool, cut: float):
    L = _plen(pts)
    return _substring(pts, cut, L) if at_start else _substring(pts, 0.0, L - cut)


def fix_angles(B: Builder, edges) -> tuple[list, int]:
    """Where a local road meets others at less than the district's minimum angle, the local
    leg is cut back from that junction (a short one, or one that dead-ends anyway, goes)."""
    n_fix = 0
    for _ in range(4):
        at: dict = {}
        for e, (pts, li) in enumerate(edges):
            at.setdefault(pts[0], []).append((e, True))
            at.setdefault(pts[-1], []).append((e, False))
        deg = {p: len(v) for p, v in at.items()}
        drop: set = set()
        trim: dict = {}
        for p in sorted(at):
            legs = at[p]
            if len(legs) < 3 or any(e in drop or e in trim for e, _ in legs):
                continue
            if all(B.lines[edges[e][1]].primary is not None for e, _ in legs):
                continue
            n = _district_at(B, p)
            want = min_angle(B.arch[n]) if n else GRID_ANGLE_DEG
            dirs = sorted((M.atan2(d[1], d[0]), e, a) for e, a in legs
                          for d in [_leg_dir(edges[e][0], a)])
            k = len(dirs)
            prim = [B.lines[edges[e][1]].primary is not None for _, e, _ in dirs]
            gaps = [(M.degrees((dirs[(i + 1) % k][0] - dirs[i][0]) % (2 * M.PI)), i)
                    for i in range(k) if not (prim[i] and prim[(i + 1) % k])]
            if not gaps:
                continue
            g, i = min(gaps)
            if g >= want - 1.0:
                continue
            pair = [dirs[i], dirs[(i + 1) % k]]
            local = [(e, a) for _, e, a in pair if B.lines[edges[e][1]].primary is None]
            if not local:
                continue
            new = [(e, a) for e, a in local if B._renewed(B.lines[edges[e][1]])]
            if new and len(new) < len(local):
                local = new  # M10: the new street gives way, not the held one
            e, a = min(local, key=lambda t: (RANK[B.lines[edges[t[0]][1]].cls],
                                            _plen(edges[t[0]][0]), t[0]))
            pts = edges[e][0]
            other = pts[-1] if a else pts[0]
            if _plen(pts) < 60.0 or deg.get(other, 0) == 1:
                drop.add(e)
            else:
                trim[e] = a
            n_fix += 1
        if not drop and not trim:
            break
        new = []
        for e, (pts, li) in enumerate(edges):
            if e in drop:
                continue
            if e in trim:
                pts = _trimmed(pts, trim[e], 18.0)
            new.append((pts, li))
        edges = _merge_and_trim(B, new)
    return edges, n_fix


DUP_GAP_M = 4.0     # right-of-way edges closer than this ...
DUP_LEN_M = 50.0    # ... over more than this (30 m around shared points aside) duplicate


def side_by_side_many(a: LineString, wa: float, others: list, widths: list) -> list[float]:
    """`side_by_side` of road a against many roads, both ways, with one vectorized first
    pass (only pairs with over DUP_LEN_M - 1 m within the gap are measured exactly)."""
    if not others:
        return []
    arr = np.array(others, dtype=object)
    gaps = np.array([(wa + w) / 2 + DUP_GAP_M for w in widths])
    zones_b = shapely.buffer(arr, gaps, cap_style="flat", join_style="mitre", mitre_limit=2.0)
    fwd = shapely.length(shapely.intersection(a, zones_b))
    zones_a = shapely.buffer(a, gaps, cap_style="flat", join_style="mitre", mitre_limit=2.0)
    back = shapely.length(shapely.intersection(arr, zones_a))
    out = []
    for k, (b, w) in enumerate(zip(others, widths)):
        L = 0.0
        if fwd[k] > DUP_LEN_M - 1.0:
            L = side_by_side(a, b, wa, w)
        if L <= DUP_LEN_M and back[k] > DUP_LEN_M - 1.0:
            L = max(L, side_by_side(b, a, w, wa))
        out.append(L)
    return out


def side_by_side(a: LineString, b: LineString, wa: float, wb: float) -> float:
    """Length of road a whose right of way runs within DUP_GAP_M of road b's, outside 30 m
    around the points where they meet or end near each other (exact length; the check
    `street_duplicates` uses the same measure)."""
    gap = (wa + wb) / 2 + DUP_GAP_M
    if not shapely.dwithin(a, b, gap):
        return 0.0  # no point of a within the gap: nothing alongside
    zone = b.buffer(gap, cap_style="flat", join_style="mitre")
    if a.intersection(zone).length <= DUP_LEN_M - 1.0:
        return 0.0  # a quick first pass on the raw zone (the snapped one differs by < 1 cm)
    near = a.intersection(G.snap(zone))
    if near.is_empty or near.length <= DUP_LEN_M - 1.0:
        return 0.0
    spots = [Point(q) for q in (a.coords[0], a.coords[-1]) if b.distance(Point(q)) < gap]
    spots += [Point(q) for q in (b.coords[0], b.coords[-1]) if a.distance(Point(q)) < gap]
    meet = a.intersection(b)
    if not meet.is_empty:
        spots += [Point(q) for q in _points_of(meet)]
    if spots:
        near = near.difference(shapely.union_all([_disc(q, 30.0) for q in spots]))
    return G.length1(near)


_DISC = [(M.cos(k * M.PI / 12), M.sin(k * M.PI / 12)) for k in range(24)]


def _disc(p: Point, r: float) -> Polygon:
    """A 24-gon around p (vertices from dmath, the same on every machine)."""
    return Polygon([(p.x + r * c, p.y + r * s_) for c, s_ in _DISC])


def fix_duplicates(B: Builder, edges) -> tuple[list, int]:
    """A local road whose right of way runs alongside another road's (edges within 4 m) for
    over 50 m is removed (the lesser class, else the shorter one)."""
    lines = [LineString(p) for p, _ in edges]
    tree = shapely.STRtree(lines)
    drop: set = set()
    for i, (pts, li) in enumerate(edges):
        if i in drop:
            continue
        a = lines[i]
        wa = B.lines[li].width
        pa = B.lines[li].primary is not None
        js = [j for j in sorted(int(x) for x in tree.query(a, predicate="dwithin",
                                                           distance=wa / 2 + 24.0))
              if j != i and j not in drop and not (pa and B.lines[edges[j][1]].primary)]
        lens = side_by_side_many(a, wa, [lines[j] for j in js],
                                 [B.lines[edges[j][1]].width for j in js])
        for j, L in zip(js, lens):
            if L <= DUP_LEN_M or j in drop:
                continue
            lj = edges[j][1]
            pb = B.lines[lj].primary is not None
            cand = [k for k, prim in ((i, pa), (j, pb)) if not prim]
            new = [k for k in cand if B._renewed(B.lines[edges[k][1]])]
            if new and len(new) < len(cand):
                cand = new  # M10: the new street goes, not the held one
            k = min(cand, key=lambda k: (RANK[B.lines[edges[k][1]].cls],
                                         _plen(edges[k][0]), k))
            drop.add(k)
            if k == i:
                break
    if not drop:
        return edges, 0
    return _merge_and_trim(B, [e for k, e in enumerate(edges) if k not in drop]), len(drop)


def pedestrianize_islands(B: Builder, edges) -> int:
    """Vehicle roads that reach the vehicle network only over pedestrian streets (a lane off
    a promenade) become pedestrian streets themselves."""
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    veh = [(pts, li) for pts, li in edges if B.lines[li].cls in VEHICLE]
    for pts, li in veh:
        parent[find(pts[0])] = find(pts[-1])
    size: dict = {}
    for pts, li in veh:
        r = find(pts[0])
        size[r] = size.get(r, 0.0) + (1e6 if li < B.n_primary else _plen(pts))
    if not size:
        return 0
    main = max(sorted(size), key=lambda r: size[r])
    n = 0
    for pts, li in veh:
        if find(pts[0]) != main:
            ln = B.lines[li]
            if ln.primary is not None or ln.cls == "pedestrian":
                continue
            arch = B.arch.get(ln.district) if ln.district else None
            ln.section = {**cross_section("pedestrian", arch), "total_width_m": ln.width,
                          "sidewalk_m": (ln.width / 2, ln.width / 2)}
            ln.cls = "pedestrian"
            ln.role = "lane_" + ln.role
            n += 1
    return n


def drop_unnoded_crossings(B: Builder, edges) -> tuple[list, int]:
    """A local road that still crosses another local road without a junction (two nearly
    collinear streets that cross again a centimeter off a vertex) is a leftover of the
    cleanup: the shorter of the two goes, until none is left."""
    n = 0
    for _ in range(20):
        idx = [k for k, (pts, li) in enumerate(edges) if li >= B.n_primary]
        new = {k for k in idx if B._renewed(B.lines[edges[k][1]])}
        if len(idx) < 2:
            break
        lines = [LineString(edges[k][0]) for k in idx]
        tree = shapely.STRtree(lines)
        worst = None
        for a, la in enumerate(lines):
            for b in sorted(int(x) for x in tree.query(la, predicate="crosses")):
                if b <= a:
                    continue
                pa, pb = edges[idx[a]][0], edges[idx[b]][0]
                k = idx[a] if (_plen(pa), idx[a]) < (_plen(pb), idx[b]) else idx[b]
                other = idx[b] if k == idx[a] else idx[a]
                if k not in new and other in new:
                    k = other  # M10: the new street goes, not the held one
                if worst is None or k < worst:
                    worst = k
        if worst is None:
            break
        edges = [e for k, e in enumerate(edges) if k != worst]
        n += 1
    return edges, n


def clean_graph(B: Builder, edges):
    notes = []
    edges = _merge_and_trim(B, edges)
    edges, n_ang = fix_angles(B, edges)
    edges, n_dup = fix_duplicates(B, edges)
    edges, n_ang2 = fix_angles(B, edges)
    if n_ang + n_ang2:
        notes.append(f"{n_ang + n_ang2} local roads cut back at junctions sharper than the "
                     "district minimum")
    if n_dup:
        notes.append(f"{n_dup} local roads running alongside another road removed")
    n_ped = pedestrianize_islands(B, edges)
    if n_ped:
        notes.append(f"{n_ped} lanes reached only over pedestrian streets became pedestrian")
        edges = _merge_and_trim(B, edges)
    edges, n_dup2 = fix_duplicates(B, edges)  # merged roads are measured whole again
    if n_dup2:
        notes.append(f"{n_dup2} more local roads running alongside another road removed")

    # a lane whose way onto the network ran along a road removed or cut back since
    n_ped2 = pedestrianize_islands(B, edges)
    if n_ped2:
        notes.append(f"{n_ped2} more lanes became pedestrian")
        edges = _merge_and_trim(B, edges)
    edges, n_x = drop_unnoded_crossings(B, edges)
    if n_x:
        notes.append(f"{n_x} local roads crossing another without a junction removed")
    # split self loops (a closed street with one junction) at their far vertex
    out = []
    for pts, li in edges:
        if pts[0] == pts[-1]:
            if len(pts) < 4:
                continue
            m = len(pts) // 2
            out += [(pts[:m + 1], li), (pts[m:], li)]
        else:
            out.append((pts, li))
    edges = out
    # keep the component that holds the primary network
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for pts, li in edges:
        parent[find(pts[0])] = find(pts[-1])
    weight: dict = {}
    for pts, li in edges:
        r = find(pts[0])
        weight[r] = weight.get(r, 0.0) + (1e6 if li < B.n_primary else _plen(pts))
    if weight and B.frame is not None:
        n_link, edges = _reconnect(B, edges, find, weight)
        if n_link:
            notes.append(f"{n_link} held roads cut off from the network joined to the "
                         "regenerated district")
            parent.clear()
            for pts, li in edges:
                parent[find(pts[0])] = find(pts[-1])
            weight = {}
            for pts, li in edges:
                r = find(pts[0])
                weight[r] = weight.get(r, 0.0) + (1e6 if li < B.n_primary else _plen(pts))
    if weight:
        main = max(sorted(weight), key=lambda r: weight[r])
        lost = math.fsum(_plen(p) for p, li in edges if find(p[0]) != main)
        if lost > 0:
            n_lost = sum(1 for p, li in edges if find(p[0]) != main)
            notes.append(f"{n_lost} local segments ({lost / 1000:.2f} km) not connected to the "
                         "network were dropped")
        edges = [(p, li) for p, li in edges if find(p[0]) == main or _held(B, p)]
    return edges, notes


RECONNECT_M = 60.0


def _reconnect(B: Builder, edges, find, weight):
    """M10: a group of held roads that reached the network only through the district's
    old streets (a promenade, a lane) is joined to its new streets: a link from the group's
    node nearest a new street of the district (within RECONNECT_M) to that street, which is
    split there. Returns (links, edges)."""
    main = max(sorted(weight), key=lambda r: weight[r])
    fr = B.frame
    free = [k for k, (pts, li) in enumerate(edges)
            if find(pts[0]) == main and fr.free_local(B.lines[li]) and
            B.lines[li].cls not in ("footbridge",)]
    if not free:
        return 0, edges
    lines = [LineString(edges[k][0]) for k in free]
    tree = shapely.STRtree(lines)
    groups: dict = {}
    for k, (pts, li) in enumerate(edges):
        r = find(pts[0])
        if r != main and _held(B, pts):
            groups.setdefault(r, []).append(k)
    n = 0
    for r in sorted(groups):
        nodes = sorted({q for k in groups[r] for q in (edges[k][0][0], edges[k][0][-1])})
        ped = all(B.lines[edges[k][1]].cls in PEDESTRIAN for k in groups[r])
        best = None
        for p in nodes:
            for j in sorted(int(x) for x in tree.query(Point(p), predicate="dwithin",
                                                         distance=RECONNECT_M)):
                d = lines[j].distance(Point(p))
                if best is None or (round(d, 6), p, j) < best[:3]:
                    best = (round(d, 6), p, j)
        if best is None or best[0] < 1.0:
            continue
        _, p, j = best
        k = free[j]
        pts, li = edges[k]
        s, _, q, i = _project(pts, p)
        q = _pt(*q)
        if _dist(q, pts[0]) < 8.0:
            q = pts[0]
        elif _dist(q, pts[-1]) < 8.0:
            q = pts[-1]
        link = LineString([p, q])
        if link.length < 1.0 or link.intersection(B.wet).length > 0.5 or (
                B.closed.intersects(link) and link.intersection(B.closed).length > 0.5):
            continue
        if q not in (pts[0], pts[-1]):
            a_, b_ = _dedupe(list(pts[:i + 1]) + [q]), _dedupe([q] + list(pts[i + 1:]))
            if len(a_) < 2 or len(b_) < 2:
                continue
            edges[k] = (a_, li)
            edges.append((b_, li))
        cls = "pedestrian" if ped else "street"
        sec = cross_section(cls, B.arch[fr.name])
        lk = B.add(Line([p, q], cls, sec["total_width_m"], "link", fr.name, section=sec))
        edges.append(([p, q], lk))
        n += 1
        # (the next group may join this one's link)
        lines = [LineString(edges[k2][0]) for k2 in free]
    return n, edges


def _held(B: Builder, pts) -> bool:
    """M10: an edge that is a held segment of the old city (never dropped)."""
    return B.frame is not None and B.frame.match(pts) is not None


PIN_CLEAR_M = 15.0              # street centerline to a traced building (a 20 m street keeps 5 m)
LOCAL_JUNCTION_Z_M = 3.0      # M7: highest primary road a local street ramps up to
LOCAL_GRADE = 0.05            # M7: local streets ramping to a raised junction


def _raised_spans(prof, z_min: float = 0.05) -> list[tuple[float, float]]:
    """Stretches of a z profile more than z_min above the ground (M7: approaches,
    viaducts, ramps)."""
    out = []
    pts = [(p["s"], p["z"]) for p in prof] if prof and isinstance(prof, list) else []
    for (s0, z0), (s1, z1) in zip(pts, pts[1:]):
        if max(z0, z1) <= z_min or s1 <= s0:
            continue
        a = s0 if z0 > z_min else s0 + (s1 - s0) * (z_min - z0) / (z1 - z0)
        b = s1 if z1 > z_min else s0 + (s1 - s0) * (z0 - z_min) / (z0 - z1)
        if out and a <= out[-1][1] + 0.01:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def _slice_profile(prof: list[dict], a: float, b: float) -> list[dict]:
    def z_at(s):
        for p0, p1 in zip(prof[:-1], prof[1:]):
            if p0["s"] <= s <= p1["s"]:
                if p1["s"] == p0["s"]:
                    return max(p0["z"], p1["z"])
                f = (s - p0["s"]) / (p1["s"] - p0["s"])
                return p0["z"] + f * (p1["z"] - p0["z"])
        return prof[-1]["z"] if prof else 0.0

    out = [{"s": 0.0, "z": G.q(z_at(a))}]
    for p in prof:
        if a < p["s"] < b:
            out.append({"s": G.q(p["s"] - a), "z": p["z"]})
    out.append({"s": G.q(b - a), "z": G.q(z_at(b))})
    return out


def build_output(B: Builder, edges) -> None:
    net = B.net
    old_nodes = {(G.q(n["position"][0]), G.q(n["position"][1])): n for n in B.roads.nodes}
    deg: dict = {}
    prim_deg: dict = {}
    for pts, li in edges:
        for q in (pts[0], pts[-1]):
            deg[q] = deg.get(q, 0) + 1
            if li < B.n_primary:
                prim_deg[q] = prim_deg.get(q, 0) + 1
    order = sorted(deg)
    node_id = {c: f"rn{i + 1:05d}" for i, c in enumerate(order)}
    for c in order:
        old = old_nodes.get(c)
        kind = old["attrs"]["kind"] if old and old["attrs"].get("kind") in ("exit", "edge") \
            else ("end" if deg[c] == 1 else ("junction" if deg[c] >= 3 else "bend"))
        attrs = {"kind": kind, "degree": deg[c], "primary_degree": prim_deg.get(c, 0)}
        if old and old["attrs"].get("exit"):
            attrs["exit"] = old["attrs"]["exit"]
        z = old["position"][2] if old else 0.0
        net.nodes.append({"id": node_id[c], "position": (c[0], c[1], z),
                          "level": old.get("level", 0) if old else 0, "attrs": attrs})
    rows = []
    for pts, li in edges:
        ln = B.lines[li]
        rows.append((ln.cls not in PRIMARY, -RANK[ln.cls], pts[0], pts[-1],
                     G.q(_plen(pts)), pts, li))
    rows.sort(key=lambda r: r[:5])
    bridges = {b["id"]: dict(b) for b in B.roads.bridges}
    for b in bridges.values():
        b["segment_ids"] = []
    seg_out = []
    foot = []
    for k, (_, _, a, b, L, pts, li) in enumerate(rows):
        ln = B.lines[li]
        sid = f"rs{k + 1:05d}"
        if ln.primary is not None:
            par = ln.primary
            s0 = _project(ln.pts, pts[0])[0]
            s1 = _project(ln.pts, pts[-1])[0]
            Lp = _plen(ln.pts)
            if tuple(ln.pts[0]) == tuple(ln.pts[-1]) and abs(s1 - s0) > L + 1.0:
                # a loop road: the piece's end at the seam is at 0 or at the loop length,
                # whichever keeps the piece its own length
                if min(s0, Lp - s0) < 0.01:
                    s0 = Lp - s0 if abs(s1 - (Lp - s0)) < abs(s1 - s0) else s0
                elif min(s1, Lp - s1) < 0.01:
                    s1 = Lp - s1 if abs(s0 - (Lp - s1)) < abs(s0 - s1) else s1
            lo, hi = min(s0, s1), max(s0, s1)
            b_ids = []
            for bid in par["bridge_ids"]:
                br = bridges[bid]
                if lo - 1.0 <= br["s0"] and br["s1"] <= hi + 1.0:
                    b_ids.append(bid)
                    br["segment_ids"].append(sid)
            row = {k2: v for k2, v in par.items()}
            row.update({"id": sid, "start": node_id[a], "end": node_id[b],
                        "centerline": [(x, y) for x, y in pts], "bridge": bool(b_ids),
                        "bridge_ids": b_ids,
                        "clearance_m": max((bridges[x]["clearance_m"] for x in b_ids),
                                           default=None),
                        "z_profile": _slice_profile(par["z_profile"], lo, hi)})
            attrs = {k2: v for k2, v in par["attrs"].items() if k2 != "grade_separated_with"}
            attrs["length_m"] = L
            attrs["m1b_segment"] = par["id"]
            row["attrs"] = attrs
        else:
            sec = dict(ln.section)
            cls = ln.cls
            if cls == "footbridge" and \
                    LineString(pts).intersection(B.wet).length < 1.0:
                cls = "pedestrian"  # the land approach of a footbridge
            row = {
                "id": sid, "type": f"road.{cls}", "start": node_id[a], "end": node_id[b],
                "centerline": [(x, y) for x, y in pts], "level": 0,
                "z_profile": [{"s": 0.0, "z": 0.0}, {"s": L, "z": 0.0}],
                "cross_section": sec, "name": ln.name, "road_class": cls,
                "lanes": (0 if cls in PEDESTRIAN else
                          sec["lanes_forward"] + sec["lanes_backward"]),
                "width_m": ln.width, "one_way": False, "bridge": False, "bridge_ids": [],
                "clearance_m": None, "district_ids": [],
                "attrs": {"role": ln.role, "length_m": L,
                          "district": B.did.get(ln.district) if ln.district else None},
            }
            if cls == "footbridge":
                row["bridge"] = True
                foot.append((row, li))
        seg_out.append(row)
    # footbridge bridge records
    n_br = len(bridges)
    for row, li in foot:
        ln_pts = row["centerline"]
        ln = B.lines[li]
        wet = shapely.intersection(LineString(ln_pts), B.wet)
        wl = G.length(G.qline(wet)) if wet.geom_type == "LineString" else \
            math.fsum(G.length(G.qline(g)) for g in shapely.get_parts(wet)
                      if g.geom_type == "LineString")
        n_br += 1
        bid = f"br{n_br:03d}"
        clear = 3.0
        deck = G.q(clear + 0.8)
        row["bridge_ids"] = [bid]
        row["clearance_m"] = clear
        Lr = row["attrs"]["length_m"]
        s_in = _first_wet(ln_pts, B.wet)
        row["z_profile"] = _foot_profile(Lr, s_in, wl, deck)
        bridges[bid] = {
            "id": bid, "type": "bridge.pedestrian", "name": None, "bridge_class": "pedestrian",
            "crosses": ln.crosses, "clearance_m": clear, "deck_levels": [0],
            "line": [(x, y, deck) for x, y in ln_pts], "segment_ids": [row["id"]],
            "attrs": {"water_class": "canal", "span_m": G.q(wl), "ramp_length_m": None,
                      "major": False, "named": False, "causeway": False, "footbridge": True,
                      "access": "stairs"}}
    net.segments = seg_out
    net.bridges = [bridges[k] for k in sorted(bridges)]
    _local_grades(net)
    _grade_separations(net)
    if B.frame is not None:
        net.held = B.frame.restore(net.segments)


def _local_grades(net: StreetNet) -> None:
    """M7: a local street that meets a raised primary road (at most 3 m up) ramps up to it
    at 5%: node heights from the primary roads, carried along the local streets by a
    max-plus envelope (a short street lifts its far end too), then each local profile."""
    import heapq

    z: dict = {}
    for sg in net.segments:
        if sg["road_class"] in PRIMARY:
            prof = sg["z_profile"]
            for nid, zz in ((sg["start"], prof[0]["z"]), (sg["end"], prof[-1]["z"])):
                z[nid] = max(z.get(nid, 0.0), zz)
    fixed = {n for n, v in z.items()}
    local = [sg for sg in net.segments if sg["road_class"] not in PRIMARY and
             sg["road_class"] != "footbridge"]
    adj: dict = {}
    for sg in local:
        L = sg["attrs"]["length_m"]
        adj.setdefault(sg["start"], []).append((sg["end"], L))
        adj.setdefault(sg["end"], []).append((sg["start"], L))
    heap = [(-v, n) for n, v in sorted(z.items()) if v > 0.0]
    heapq.heapify(heap)
    while heap:
        v, n = heapq.heappop(heap)
        v = -v
        if v < z.get(n, 0.0):
            continue
        for m_, L in sorted(adj.get(n, [])):
            w = v - LOCAL_GRADE * L
            if w > z.get(m_, 0.0) + 1e-9 and m_ not in fixed:
                z[m_] = w
                heapq.heappush(heap, (-w, m_))
    for sg in local:
        za, zb = G.q(z.get(sg["start"], 0.0)), G.q(z.get(sg["end"], 0.0))
        if za <= 0.0 and zb <= 0.0:
            continue
        L = sg["attrs"]["length_m"]
        pts = {0.0, L}
        if za > 0.0:
            pts.add(min(za / LOCAL_GRADE, L))
        if zb > 0.0:
            pts.add(max(L - zb / LOCAL_GRADE, 0.0))
        prof = []
        for x in sorted(pts):
            zz = max(0.0, za - LOCAL_GRADE * x, zb - LOCAL_GRADE * (L - x))
            prof.append({"s": G.q(x), "z": G.q(zz)})
        sg["z_profile"] = prof
    # a footbridge (stairs up to its deck) starts where its node now stands
    for sg in net.segments:
        if sg["road_class"] != "footbridge":
            continue
        prof = [dict(p) for p in sg["z_profile"]]
        for k, nid in ((0, sg["start"]), (-1, sg["end"])):
            zz = G.q(z.get(nid, 0.0))
            if zz > prof[k]["z"]:
                prof[k]["z"] = zz
        sg["z_profile"] = prof
    for n in net.nodes:
        if n["id"] in z and z[n["id"]] > 0.0:
            x, y, _ = n["position"]
            n["position"] = (x, y, G.q(z[n["id"]]))


def _first_wet(pts, wet) -> float:
    L = _plen(pts)
    n = max(int(L / 1.0), 1)
    for k in range(n + 1):
        p, _ = _along(pts, L * k / n)
        if wet.contains(Point(p)):
            return G.q(L * k / n)
    return 0.0


def _foot_profile(L: float, s_in: float, wet_len: float, deck: float) -> list[dict]:
    """Stairs up to the deck just before the water, down just after (1:2 stairs)."""
    run = deck * 2.0
    a = max(s_in - 1.0, 0.0)
    b = min(s_in + wet_len + 1.0, L)
    inner = [(max(a - run, 0.0), 0.0), (a, deck), (b, deck), (min(b + run, L), 0.0)]
    # both ends stand on the ground (steeper stairs where the water reaches an end)
    pts = [(0.0, 0.0)] + [(min(max(s, 0.01), L - 0.01), z) for s, z in inner] + [(L, 0.0)]
    out = []
    for s, z in pts:
        s, z = G.q(s), G.q(z)
        if out and abs(out[-1]["s"] - s) < 0.01:
            out[-1] = {"s": s, "z": max(out[-1]["z"], z)}
        else:
            out.append({"s": s, "z": z})
    return out


def _grade_separations(net: StreetNet) -> None:
    lines = [LineString(sg["centerline"]) for sg in net.segments]
    tree = shapely.STRtree(lines)
    for i, a in enumerate(lines):
        si = net.segments[i]
        si["attrs"].pop("grade_separated_with", None)
    for i, a in enumerate(lines):
        for j in sorted(int(x) for x in tree.query(a, predicate="crosses")):
            if j <= i:
                continue
            si, sj = net.segments[i], net.segments[j]
            if {si["start"], si["end"]} & {sj["start"], sj["end"]}:
                continue
            si["attrs"].setdefault("grade_separated_with", []).append(sj["id"])
            sj["attrs"].setdefault("grade_separated_with", []).append(si["id"])


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def build_streets(spec: CitySpec, h, polygons: dict, district_ids: dict, waterways, sites,
                  roads, open_polys: list, frame: Frame | None = None) -> StreetNet:
    B = Builder(spec, h, polygons, district_ids, waterways, sites, roads, open_polys, frame)
    build_frame(B)
    if frame is not None:
        frame.inject(B)
    for d in spec.districts:
        if d.name in B.free and not B.free[d.name].is_empty:
            fill_district(B, d.name)
    footbridges(B)
    link_dead_ends(B)
    for _ in range(3):
        if not join_islands(B):
            break
    edges, n1 = node_lines(B)
    edges, n2 = clean_graph(B, edges)
    build_output(B, edges)
    net = B.net
    net.lines = B.lines
    net.builder = B
    net.notes = B.notes + n1 + n2
    T.stage("streets", [net.nodes, net.segments, net.bridges])
    return net
