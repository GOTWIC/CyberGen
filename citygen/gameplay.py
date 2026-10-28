"""M11: the gameplay layer. Runs last, on the city with its props and plants.

| collection | what |
|---|---|
| factions | gangs (one per dangerous district, or as the spec names them), corporations (their security holds corporate, campus and port districts), the city police |
| zones | territories: each district split into 1 to 4 turfs (straight bisectors between seed blocks), held by its faction, a rival gang on the turf nearest the rival's home; police precincts (a district with its presence level and station building) |
| fields | wealth, danger and police presence on a 32 m raster: the district values (`wealth`, `danger`, `police` in the spec, archetype defaults) blended across borders, raised or lowered near parks and water, landmarks, alleys, raised road decks, stations and precinct stations |
| pois | bars, clinics and vendors (ground-floor units, by district budget and spacing), apartments (a floor of a residential building), hideouts (a building of each gang turf), fixers (a table in a bar); each named, with its doors |
| densities | per road segment and hour band: traffic, vehicles, pedestrians, gang members and police per 100 m |
| parking | parking structures and underground garages, surface lots in front setbacks, curb parking |
| travel_points | taxi stands at stations, hotels, landmarks and bars; fast-travel points per district |
| sign_slots | the M6 shop signs and M3 roof billboards as slots, plus facade billboards facing highways and avenues, holo-ads over tower roofs and neon bands on mid-rise facades |

Every place carries an `Access`: its door, the ground walkway the door opens on (in the
walkway component of its landmass) and the drive lane where a car stops (in the lane graph's
largest strongly connected part), with the curb on the door's walkway component; a candidate
without one is not placed, so the reachability checks (`gameplay_checks.py`) hold by
construction. Choices are hashes of ids (`props._u`) or exact arithmetic on grid
coordinates; STRtree hits are sorted and ties go to the lower index; names come from fixed
word lists by hash and are kept unique in a fixed order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from . import presets
from .buildout import GROUND_WALKS
from .model import HOUR_BANDS
from .props import _u
from .decks import on_ground, walk_ends
from .street_checks import walk_components

q = G.q
BANDS = tuple(b[0] for b in HOUR_BANDS)
CELL_M = 32.0
BLUR_CELLS = 3
WALK_REACH_M = 40.0     # door to its ground walkway
CURB_REACH_M = 60.0     # door to a lane of the road it faces
DRIVE_REACH_M = 150.0   # door to any drive lane (pedestrian streets, deep lots)
DRIVE_CLASSES = ("avenue", "street", "service", "alley")
GANG_DANGER = 0.45
CORP_ARCH = ("corporate_core", "research_campus", "spaceport", "industrial_port")

# --- what the city is made of, by archetype ---------------------------------------------

# POIs per km2 of district: bar, clinic, vendor, apartment
RATES = {
    "corporate_core": (4, 4, 8, 2), "megablock_residential": (8, 6, 12, 10),
    "midtown_mixed": (12, 6, 15, 6), "entertainment_market": (30, 6, 20, 3),
    "old_town": (15, 8, 25, 5), "industrial_port": (4, 2, 4, 1),
    "residential_heights": (3, 3, 5, 6), "research_campus": (2, 6, 3, 1),
    "transit_hub": (10, 5, 15, 2), "spaceport": (3, 2, 4, 0.5),
}
UNIT_POI = {"bar": ("bar", "bar"), "club": ("bar", "club"), "arcade": ("bar", "arcade"),
            "clinic": ("clinic", "clinic"), "cyberware": ("clinic", "ripperdoc"),
            "food": ("vendor", "food"), "convenience": ("vendor", "convenience"),
            "pawn": ("vendor", "pawn")}
SPACING_M = {"bar": 60.0, "clinic": 120.0, "vendor": 50.0, "apartment": 90.0,
             "hideout": 150.0}
POI_GAP_M = 12.0
FRONT_W = {"pedestrian": 1.15, "avenue": 1.0, "street": 0.9, "alley": 0.6, "service": 0.5}
HOURS = {"bar": (18, 4), "club": (21, 6), "arcade": (12, 2), "clinic": (8, 20),
         "ripperdoc": (10, 22), "convenience": (0, 24), "pawn": (9, 21), "fixer": (20, 4)}
FOOD_HOURS = ((6, 22), (0, 24), (10, 2), (7, 23))

# traffic and crowd by hour band (night, morning, day, evening, late)
TRAFFIC = {
    "corporate_core": (0.15, 1.0, 0.7, 0.95, 0.35),
    "megablock_residential": (0.2, 0.9, 0.5, 0.85, 0.5),
    "midtown_mixed": (0.2, 0.8, 0.75, 0.9, 0.6),
    "entertainment_market": (0.5, 0.35, 0.55, 0.8, 1.0),
    "old_town": (0.25, 0.6, 0.8, 0.85, 0.6),
    "industrial_port": (0.4, 0.9, 1.0, 0.7, 0.4),
    "residential_heights": (0.1, 0.8, 0.4, 0.8, 0.3),
    "research_campus": (0.1, 0.85, 0.6, 0.8, 0.2),
    "transit_hub": (0.35, 1.0, 0.8, 1.0, 0.6),
    "spaceport": (0.5, 0.8, 0.8, 0.8, 0.6),
}
CROWD = {
    "corporate_core": (0.1, 0.9, 0.8, 0.9, 0.3),
    "megablock_residential": (0.2, 0.7, 0.6, 0.85, 0.6),
    "midtown_mixed": (0.15, 0.6, 0.8, 0.9, 0.7),
    "entertainment_market": (0.55, 0.25, 0.6, 0.9, 1.0),
    "old_town": (0.25, 0.7, 1.0, 0.9, 0.6),
    "industrial_port": (0.1, 0.6, 0.7, 0.4, 0.15),
    "residential_heights": (0.05, 0.4, 0.35, 0.5, 0.2),
    "research_campus": (0.05, 0.6, 0.7, 0.5, 0.1),
    "transit_hub": (0.3, 1.0, 0.8, 1.0, 0.6),
    "spaceport": (0.3, 0.6, 0.6, 0.6, 0.4),
}
GANG_HOURS = (0.6, 0.3, 0.4, 0.8, 1.0)
# per lane capacity (vehicles per hour), peak use, speed (km/h), pedestrians per 100 m
LANE_CAP = {"highway": 1900.0, "avenue": 900.0, "street": 600.0, "service": 300.0,
            "alley": 150.0}
PEAK_USE = {"highway": 0.85, "avenue": 0.75, "street": 0.6, "service": 0.4, "alley": 0.4}
SPEED = {"highway": 90.0, "avenue": 50.0, "street": 40.0, "service": 25.0, "alley": 20.0}
WALKERS = {"pedestrian": 120.0, "footbridge": 60.0, "avenue": 60.0, "street": 35.0,
           "alley": 12.0, "service": 5.0, "highway": 0.0}

# --- names ---------------------------------------------------------------------------------

ADJ = ("Neon", "Chrome", "Rusty", "Velvet", "Static", "Broken", "Golden", "Silver", "Black",
       "Red", "Blue", "Lucky", "Electric", "Midnight", "Copper", "Glass", "Iron", "Paper",
       "Jade", "Crimson", "Hollow", "Drowned", "Burning", "Sleepless", "Wired", "Pale")
NOUN = ("Lantern", "Coil", "Mantis", "Anchor", "Circuit", "Oyster", "Fox", "Crow", "Tiger",
        "Moth", "Signal", "Socket", "Harbor", "Engine", "Dragon", "Koi", "Ghost", "Relay",
        "Needle", "Monsoon", "Orchid", "Piston", "Lotus", "Comet", "Rabbit", "Heron")
SURNAME = ("Okafor", "Tanaka", "Novak", "Reyes", "Kowalski", "Haddad", "Lindqvist", "Mbeki",
           "Sato", "Petrov", "Moreau", "Chen", "Iyer", "Castillo", "Abara", "Vance", "Kim",
           "Duarte", "Oyelaran", "Fitzroy", "Nakamura", "Varga", "Quist", "Ruiz", "Adeyemi",
           "Morozov", "Halloran", "Esposito", "Takeda", "Brandt")
FIRST = ("Mara", "Dex", "Ivo", "Rhea", "Tomas", "Yuki", "Kofi", "Lena", "Sol", "Nadia",
         "Oskar", "Priya", "Rook", "Juno", "Cass", "Emeka", "Bianca", "Hiro", "Vera", "Anton")
HANDLE = ("Wire", "Lucky", "Mother", "Saint", "Ghost", "Ledger", "Switch", "Velvet", "Patch",
          "Hex", "Needle", "Echo", "Halo", "Crank", "Doc", "Tally")
GANG_A = ("Chrome", "Red", "Black", "Iron", "Ghost", "Neon", "Rust", "Static", "Jade", "Ash",
          "Blood", "Glass", "Hollow", "Silver", "Burning", "Night", "Gutter", "Voltage")
GANG_B = ("Jackals", "Wraiths", "Saints", "Vipers", "Hounds", "Kites", "Sharks", "Ravens",
          "Mambas", "Dragons", "Rats", "Wolves", "Lotus", "Tide", "Choir", "Syndicate",
          "Tigers", "Crows")
CORP_A = ("Helix", "Vantor", "Orison", "Kessel", "Arclight", "Sable", "Nimbus", "Halcyon",
          "Tessar", "Quorra", "Obelis", "Caldera", "Veritan", "Solenne", "Ironvale", "Kuroda")
CORP_B = {"corporate_core": ("Group", "Holdings", "Dynamics", "Capital"),
          "research_campus": ("Biotech", "Labs", "Genomics", "Medical"),
          "spaceport": ("Aerospace", "Orbital", "Launch Systems", "Skyways"),
          "industrial_port": ("Logistics", "Freight", "Maritime", "Shipping"),
          "transit_hub": ("Transit", "Logistics", "Mobility", "Lines")}
LAIR = ("Den", "Nest", "Kiln", "Vault", "Hole", "Garage", "Pit", "Roost", "Hive", "Bunker")
GANG_COLORS = ("#e2493a", "#f2a33a", "#c94fe0", "#3ad6c4", "#e8e04a", "#ff6fae", "#7ad94f",
               "#4fa3ff", "#ff8a4f", "#b07aff")
CORP_COLORS = ("#9fb3c8", "#c8b89f", "#8fc8b0", "#c89fbf", "#b0c88f", "#9fa8c8")
POLICE_COLOR = "#5b8cff"


def _pick(seq, *key):
    return seq[int(_u(*key) * len(seq))]


class Names:
    """Unique names: a generator called with try numbers 0, 1, ... until one is free."""

    def __init__(self):
        self.used: set[str] = set()

    def take(self, gen, tries: int = 12, ok=None) -> str:
        """The first free name the generator makes (and `ok` accepts, while it can)."""
        name = None
        first = None
        for k in range(tries):
            name = gen(k)
            if name in self.used:
                continue
            if first is None:
                first = name
            if ok is None or ok(name):
                break
        else:
            name = first if first is not None else name
        n = 2
        base = name
        while name in self.used:
            name = f"{base} {n}"
            n += 1
        self.used.add(name)
        return name


def _slug(name: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "_" for ch in name)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_") or "x"


# --- exact helpers -------------------------------------------------------------------------

def _center(coords) -> tuple[float, float]:
    """Area centroid of a ring from its grid coordinates (integer shoelace, exact)."""
    pts = [(int(round(x * 100)), int(round(y * 100))) for x, y in coords]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    a = cx = cy = 0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if a == 0:
        return (q(sum(p[0] for p in pts) / len(pts) / 100.0),
                q(sum(p[1] for p in pts) / len(pts) / 100.0))
    return q(cx / (3.0 * a) / 100.0), q(cy / (3.0 * a) / 100.0)


def _d2(a, b) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def compass(dx: float, dy: float) -> str:
    """One of eight compass words for a direction (exact comparisons, no trigonometry)."""
    t = 0.41421356  # tan 22.5 degrees
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return "Central"
    if abs(dy) <= t * abs(dx):
        return "East" if dx > 0 else "West"
    if abs(dx) <= t * abs(dy):
        return "North" if dy > 0 else "South"
    return ("North" if dy > 0 else "South") + ("east" if dx > 0 else "west")


def _half(line) -> tuple[float, float]:
    """The point halfway along a polyline."""
    pts = [(float(p[0]), float(p[1])) for p in line]
    seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    s = sum(seg) / 2.0
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if s <= L and L > 0:
            f = s / L
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        s -= L
    return pts[-1]


def largest_scc(succ: dict[str, list[str]]) -> set[str]:
    """Members of the largest strongly connected component (ties: the one with the lowest
    member id), iterative Tarjan."""
    index: dict = {}
    low: dict = {}
    on: set = set()
    stack: list = []
    counter = 0
    best: list = []
    for root in sorted(succ):
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on.add(v)
            nxt = succ.get(v, [])
            if i < len(nxt):
                work.append((v, i + 1))
                w = nxt[i]
                if w not in index:
                    work.append((w, 0))
                elif w in on:
                    low[v] = min(low[v], index[w])
                continue
            for w in nxt:
                if w in on:
                    low[v] = min(low[v], low[w])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > len(best) or (len(comp) == len(best) and
                                             min(comp) < min(best)):
                    best = comp
    return set(best)


def lane_graph(m) -> dict[str, list[str]]:
    return {ln.id: sorted(set(ln.successors) | set(ln.adjacent_ids)) for ln in m.lanes}


def foot_roots(m) -> tuple[dict, set]:
    """(root of every walk node, the main root of each landmass with districts: the walkway
    component with most nodes on it)."""
    roots = walk_components(m)
    pts = sorted(roots)
    main: set = set()
    if not pts:
        return roots, main
    xy = np.array([p[:2] for p in pts], dtype=np.float64)
    for lm in m.landmasses:
        if not lm.district_ids:
            continue
        poly = G.from_model_poly(lm.polygon)
        inside = shapely.contains_xy(poly, xy[:, 0], xy[:, 1])
        count: dict = {}
        for i in np.nonzero(inside)[0].tolist():
            r = roots[pts[i]]
            count[r] = count.get(r, 0) + 1
        if count:
            main.add(max(count, key=lambda r: (count[r], r)))
    return roots, main


def _nearest(tree, geoms, pt, reach: float, ok=None):
    """(distance, index) of the geometry nearest pt within reach (ties: lower index)."""
    if tree is None:
        return None
    idx = tree.query(pt, predicate="dwithin", distance=reach)
    if not len(idx):
        return None
    idx = np.sort(idx)
    if ok is not None:
        idx = np.array([i for i in idx.tolist() if ok(i)], dtype=np.int64)
        if not len(idx):
            return None
    d = np.round(shapely.distance(geoms[idx], pt), G.DIST_DIGITS)
    k = int(np.argmin(d))  # first minimum: the lowest index
    return float(d[k]), int(idx[k])


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

class Ctx:
    def __init__(self, spec, m):
        self.spec, self.m = spec, m
        P = G.from_model_poly
        self.dist = list(m.districts)
        self.dpoly = {d.id: P(d.polygon) for d in self.dist}
        self.arch = {d.id: d.archetype for d in self.dist}
        self.vals = {}
        for d in self.dist:
            pre = presets.ARCHETYPES.get(d.archetype)
            v = {}
            for k in ("wealth", "danger", "police", "neon", "grime"):
                x = (d.params or {}).get(k)
                v[k] = float(x) if x is not None else float(getattr(pre, k, 0.4))
            self.vals[d.id] = v
        self.center = {d.id: _center(d.polygon.exterior) for d in self.dist}
        self.area_km2 = {d.id: G.area(self.dpoly[d.id]) / 1e6 for d in self.dist}
        self.seg = {s.id: s for s in m.road_segments}
        self.bld = {b.id: b for b in m.buildings}
        self.lot = {lt.id: lt for lt in m.lots}
        # on foot: ground walkways in the main component of their landmass
        roots, main = foot_roots(m)
        self.walk, self.walk_lines, self.walk_root, self.walk_lev = [], [], [], []
        for w in m.walkways:
            if not on_ground(w):
                continue
            r = roots.get(walk_ends(w)[0])
            if r not in main:
                continue
            self.walk.append(w)
            self.walk_lines.append(LineString([p[:2] for p in w.line]))
            self.walk_root.append(r)
            self.walk_lev.append(w.level)
        self.walk_geoms = np.array(self.walk_lines, dtype=object)
        self.walk_ix = {w.id: i for i, w in enumerate(self.walk)}
        self.walk_tree = shapely.STRtree(self.walk_lines) if self.walk_lines else None
        # by car: ground drive lanes of local roads in the lane graph's largest part
        scc = largest_scc(lane_graph(m))
        self.lanes, self.lane_lines, self.lane_seg, self.lane_lev = [], [], {}, []
        tops = {dk.id: dk.top_m for dk in m.decks}
        for ln in m.lanes:
            s = self.seg.get(ln.segment_id)
            if ln.kind != "lane" or s is None or s.road_class not in DRIVE_CLASSES or \
                    ln.id not in scc:
                continue
            # (M14: a deck's lanes at its top; never a ramp's)
            z0 = tops.get(s.attrs.get("deck"), 0.0) if ln.level and \
                s.attrs.get("role") != "deck_ramp" else 0.0
            if any(abs(p[2] - z0) > 0.5 for p in ln.centerline):
                continue
            self.lane_seg.setdefault(s.id, []).append(len(self.lanes))
            self.lanes.append(ln)
            self.lane_lines.append(LineString([p[:2] for p in ln.centerline]))
            self.lane_lev.append(ln.level)
        self.lane_geoms = np.array(self.lane_lines, dtype=object)
        self.lane_ix = {ln.id: i for i, ln in enumerate(self.lanes)}
        self.lane_tree = shapely.STRtree(self.lane_lines) if self.lane_lines else None
        self.decks = bool(m.decks)
        self.names = Names()        # factions and places
        self.zone_names = Names()   # territories and precincts (named after their district)
        self.fields: dict = {}

    # -- places ---------------------------------------------------------------------------

    def district_at(self, p) -> str | None:
        for d in self.dist:
            if shapely.contains_xy(self.dpoly[d.id], p[0], p[1]):
                return d.id
        return None

    def level_of(self, seg_id: str | None) -> int:
        """M14: the level of a door facing this road (a deck's street: the deck)."""
        s = self.seg.get(seg_id) if seg_id else None
        if s is None or "deck" not in s.attrs or s.attrs.get("role") == "deck_ramp":
            return 0
        return s.level

    def access(self, pos, kind: str = "main", seg_id: str | None = None,
               drive_reach: float = DRIVE_REACH_M, level: int | None = None) -> dict | None:
        """Door -> its ground walkway and the drive lane a car stops on (M14: on the door's
        level), or None."""
        pt = Point(float(pos[0]), float(pos[1]))
        lv = self.level_of(seg_id) if level is None else level
        wok = (lambda i: self.walk_lev[i] == lv) if self.decks else None
        lok = (lambda i: self.lane_lev[i] == lv) if self.decks else None
        w = _nearest(self.walk_tree, self.walk_geoms, pt, WALK_REACH_M, ok=wok)
        if w is None or self.lane_tree is None:
            return None
        lane = None
        own = self.lane_seg.get(seg_id) if seg_id else None
        if own:
            own_set = set(own)
            lane = _nearest(self.lane_tree, self.lane_geoms, pt, CURB_REACH_M,
                            ok=lambda i: i in own_set)
        if lane is None:
            lane = _nearest(self.lane_tree, self.lane_geoms, pt, drive_reach, ok=lok)
        if lane is None:
            return None
        curb = G.nearest(self.lane_lines[lane[1]], pt)
        cw = _nearest(self.walk_tree, self.walk_geoms, Point(curb), WALK_REACH_M, ok=wok)
        if cw is None or self.walk_root[cw[1]] != self.walk_root[w[1]]:
            return None
        return {"position": (q(pos[0]), q(pos[1])), "kind": kind,
                "walkway_id": self.walk[w[1]].id, "walk_link_m": q(w[0]),
                "lane_id": self.lanes[lane[1]].id, "curb": curb,
                "curb_m": q(math.hypot(curb[0] - pos[0], curb[1] - pos[1]))}

    def on_walk(self, acc: dict, toward) -> tuple[float, float]:
        """The point of the access walkway nearest `toward` (a stand on the sidewalk)."""
        i = self.walk_ix[acc["walkway_id"]]
        return G.nearest(self.walk_lines[i], Point(*toward))

    def field_at(self, kind: str, x: float, y: float) -> float:
        f = self.fields.get(kind)
        if f is None:
            return 0.0
        i = min(max(int(math.floor((x - f["origin"][0]) / f["cell_m"])), 0), f["nx"] - 1)
        j = min(max(int(math.floor((y - f["origin"][1]) / f["cell_m"])), 0), f["ny"] - 1)
        return f["values"][j * f["nx"] + i]


# ---------------------------------------------------------------------------
# Factions and zones
# ---------------------------------------------------------------------------

def _halfplane(a, b, far: float = 40000.0):
    """The half plane of points nearer a than b, as a big polygon on the grid."""
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    dx, dy = a[0] - b[0], a[1] - b[1]
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L          # toward a
    tx, ty = -uy, ux
    pts = [(mx + tx * far, my + ty * far), (mx + tx * far + ux * far, my + ty * far + uy * far),
           (mx - tx * far + ux * far, my - ty * far + uy * far), (mx - tx * far, my - ty * far)]
    return shapely.Polygon([(q(x), q(y)) for x, y in pts])


def factions_and_zones(c: Ctx) -> tuple[list, list, dict]:
    m = c.m
    city = m.name
    factions: dict[str, dict] = {}
    order: list[str] = []

    def faction(name: str, kind: str, home: str | None, color: str) -> dict:
        fid = "fac." + _slug(name)
        if fid not in factions:
            factions[fid] = {"id": fid, "type": f"faction.{kind}", "name": name, "kind": kind,
                             "color": color, "home_district_id": home, "zone_ids": [],
                             "attrs": {}}
            order.append(fid)
        return factions[fid]

    police = faction(f"{city} Police", "police", None, POLICE_COLOR)
    owner: dict[str, dict] = {}
    words: set[str] = set()     # no two generated factions share a word
    gang_n = corp_n = 0
    spec_d = {d.name: d for d in c.spec.districts} if c.spec is not None else {}
    for d in c.dist:
        v = c.vals[d.id]
        sd = spec_d.get(d.name)
        named = getattr(sd, "faction", None) if sd is not None else None
        if v["danger"] >= GANG_DANGER:
            kind = "gang"
        elif d.archetype in CORP_ARCH or d.archetype == "transit_hub":
            kind = "corporate"
        else:
            kind = "police"
        if named:
            f = factions.get("fac." + _slug(named))
            if f is None:
                color = GANG_COLORS[gang_n % len(GANG_COLORS)] if kind == "gang" else \
                    CORP_COLORS[corp_n % len(CORP_COLORS)] if kind == "corporate" else \
                    POLICE_COLOR
                gang_n += kind == "gang"
                corp_n += kind == "corporate"
                f = faction(named, kind, d.id, color)
        elif kind == "gang":
            name = c.names.take(lambda k: f"{_pick(GANG_A, 'gang', d.id, k)} "
                                          f"{_pick(GANG_B, 'gang_b', d.id, k)}", tries=40,
                                ok=lambda n: not set(n.split()) & words)
            words.update(name.split())
            f = faction(name, "gang", d.id, GANG_COLORS[gang_n % len(GANG_COLORS)])
            gang_n += 1
        elif kind == "corporate":
            tail = CORP_B.get(d.archetype, CORP_B["corporate_core"])
            name = c.names.take(lambda k: f"{_pick(CORP_A, 'corp', d.id, k)} "
                                          f"{_pick(tail, 'corp_b', d.id, k)}", tries=40,
                                ok=lambda n: n.split()[0] not in words)
            words.update(name.split()[:1])
            f = faction(name, "corporate", d.id, CORP_COLORS[corp_n % len(CORP_COLORS)])
            corp_n += 1
        else:
            f = police
        owner[d.id] = f
    gangs = [factions[fid] for fid in order if factions[fid]["kind"] == "gang"]

    blocks_of: dict[str, list] = {}
    for b in m.blocks:
        blocks_of.setdefault(b.district_id, []).append(b)
    zones: list[dict] = []
    turf_of_block: dict[str, str] = {}
    precinct: dict[str, str | None] = {}
    for d in c.dist:
        blks = blocks_of.get(d.id, [])
        poly = c.dpoly[d.id]
        cen = c.center[d.id]
        k = max(1, min(4, int(c.area_km2[d.id] / 0.6 + 0.5), len(blks)))
        bc = [(_center(b.polygon.exterior), b.id) for b in blks]
        seeds: list = []
        if bc:
            first = max(bc, key=lambda t: (round(_d2(t[0], cen), 4), t[1]))
            seeds.append(first)
            while len(seeds) < k:
                nxt = max((t for t in bc if t not in seeds),
                          key=lambda t: (round(min(_d2(t[0], s[0]) for s in seeds), 4), t[1]))
                seeds.append(nxt)
        else:
            seeds.append((cen, d.id))
        # seed order by id of the seed block (the turf numbers do not follow the search)
        seeds.sort(key=lambda t: t[1])
        cells = []
        for i, (s, _) in enumerate(seeds):
            cell = poly
            for j, (t, _) in enumerate(seeds):
                if j != i and _d2(s, t) > 0:
                    cell = G.inter(cell, _halfplane(s, t))
            cells.append(cell)
        assign: list[list[str]] = [[] for _ in seeds]
        for p, bid in bc:
            best = min(range(len(seeds)), key=lambda i: (round(_d2(p, seeds[i][0]), 4), i))
            assign[best].append(bid)
        own = owner[d.id]
        rival = None
        if own["kind"] == "gang" and len(seeds) >= 2:
            others = [g for g in gangs if g["id"] != own["id"] and g["home_district_id"]]
            if others:
                rival = min(others, key=lambda g: (round(_d2(c.center[g["home_district_id"]],
                                                              cen), 4), g["id"]))
                if _d2(c.center[rival["home_district_id"]], cen) > 3000.0 ** 2:
                    rival = None
        rival_turf = None
        if rival is not None:
            rc = c.center[rival["home_district_id"]]
            rival_turf = min(range(len(seeds)),
                             key=lambda i: (round(_d2(seeds[i][0], rc), 4), i))
        v = c.vals[d.id]
        for i, ((s, _), cell) in enumerate(zip(seeds, cells)):
            f = rival if i == rival_turf else own
            zid = f"{d.id}.turf{i + 1}"
            where = compass(s[0] - cen[0], s[1] - cen[1]) if len(seeds) > 1 else None
            base = f"{d.name} {where}" if where else d.name
            level = 0.4 if i == rival_turf else (0.5 + 0.5 * v["danger"]) if \
                f["kind"] == "gang" else 0.9 if f["kind"] == "corporate" else v["police"]
            zones.append({"id": zid, "type": "zone.territory", "kind": "territory",
                          "name": c.zone_names.take(lambda k: base if k == 0 else
                                               f"{base} {k + 1}"),
                          "district_id": d.id, "faction_id": f["id"],
                          "polygons": G.to_model_polys(cell) if not cell.is_empty else
                          [G.to_model_poly(poly)],
                          "level": q(min(1.0, level)), "block_ids": sorted(assign[i]),
                          "attrs": {"seed": [q(s[0]), q(s[1])],
                                    "contested": i == rival_turf}})
            f["zone_ids"].append(zid)
            for bid in assign[i]:
                turf_of_block[bid] = zid
        # the precinct station: the civic building nearest the district's middle, else an
        # office or mixed building
        best = None
        for b in m.buildings:
            if b.district_id != d.id or not b.entrances or b.megasite_id:
                continue
            rank = 0 if b.use == "civic" and not b.landmark else 1 if b.use in (
                "office", "mixed") else None
            if rank is None:
                continue
            key = (rank, round(_d2(b.entrances[0].position, cen), 4), b.id)
            if best is None or key < best:
                best = key
        precinct[d.id] = best[2] if best else None
        pz = f"{d.id}.police"
        zones.append({"id": pz, "type": "zone.police", "kind": "police",
                      "name": c.zone_names.take(lambda k: f"{d.name} Precinct" if k == 0 else
                                           f"{d.name} Precinct {k + 1}"),
                      "district_id": d.id, "faction_id": police["id"],
                      "polygons": G.to_model_polys(poly), "level": q(v["police"]),
                      "block_ids": [], "attrs": {"station_building_id": precinct[d.id]}})
        police["zone_ids"].append(pz)
    for f in factions.values():
        f["zone_ids"] = sorted(f["zone_ids"])
    c.turf_of_block = turf_of_block
    c.zone_poly = {z["id"]: shapely.MultiPolygon([G.from_model_poly(p) for p in z["polygons"]])
                   for z in zones if z["kind"] == "territory"}
    c.zone_faction = {z["id"]: z["faction_id"] for z in zones}
    c.factions = factions
    return [factions[fid] for fid in order], zones, precinct


def zone_at(c: Ctx, building, pos) -> str | None:
    if building is not None and building.lot_id in c.lot:
        z = c.turf_of_block.get(c.lot[building.lot_id].block_id)
        if z:
            return z
    for zid in sorted(c.zone_poly):
        if shapely.contains_xy(c.zone_poly[zid], pos[0], pos[1]):
            return zid
    return None


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    """Sum over a (2r+1)^2 window, integer arrays (exact)."""
    p = np.pad(a, r)
    cs = np.cumsum(p, axis=0)
    cs = np.vstack([np.zeros((1, cs.shape[1]), dtype=cs.dtype), cs])
    rows = cs[2 * r + 1:] - cs[:-2 * r - 1]
    cs = np.cumsum(rows, axis=1)
    cs = np.hstack([np.zeros((cs.shape[0], 1), dtype=cs.dtype), cs])
    return cs[:, 2 * r + 1:] - cs[:, :-2 * r - 1]


def _falloff(geoms: list, pts, reach: float) -> np.ndarray:
    """max(0, 1 - d / reach) for the distance d from each point to the nearest geometry."""
    out = np.zeros(len(pts))
    if not geoms:
        return out
    tree = shapely.STRtree(geoms)
    ip, d = tree.query_nearest(pts, max_distance=reach, return_distance=True,
                               all_matches=False)
    d = np.round(d, 3)
    out[ip] = np.maximum(0.0, 1.0 - d / reach)
    return out


def build_fields(c: Ctx, precinct: dict) -> list[dict]:
    m = c.m
    x0, y0, x1, y1 = m.bounds
    nx = int(math.ceil((x1 - x0) / CELL_M - 1e-9))
    ny = int(math.ceil((y1 - y0) / CELL_M - 1e-9))
    xs = x0 + (np.arange(nx) + 0.5) * CELL_M
    ys = y0 + (np.arange(ny) + 0.5) * CELL_M
    X, Y = np.meshgrid(xs, ys)
    owner = np.full(X.shape, -1, dtype=np.int64)
    for k, d in enumerate(c.dist):
        inside = shapely.contains_xy(c.dpoly[d.id], X, Y) & (owner < 0)
        owner[inside] = k
    land = owner >= 0
    base = {}
    for key in ("wealth", "danger", "police"):
        v = np.zeros(X.shape, dtype=np.int64)
        for k, d in enumerate(c.dist):
            v[owner == k] = int(round(c.vals[d.id][key] * 1000))
        s = _box_blur(v, BLUR_CELLS)
        n = _box_blur(land.astype(np.int64), BLUR_CELLS)
        base[key] = np.where(n > 0, s / np.maximum(n, 1) / 1000.0, 0.0)
    pts = shapely.points(np.column_stack([X.ravel(), Y.ravel()]))
    P = G.from_model_poly
    amen = [P(o.polygon) for o in m.open_spaces if o.kind in (
        "park", "pocket_park", "green", "garden", "plaza", "promenade", "beach")] + \
        [P(e.polygon) for e in m.waterways] + [P(e.polygon) for e in m.rivers] + \
        [P(e.polygon) for e in m.channels] + [P(p) for e in m.seas for p in e.polygons]
    land_mark = [P(b.footprint) for b in m.buildings if b.landmark and b.footprint is not None]
    alley = [LineString(s.centerline) for s in m.road_segments if s.road_class == "alley"]
    raised = [LineString(s.centerline) for s in m.road_segments
              if s.road_class == "highway" and (s.level > 0 or s.attrs.get("elevated"))]
    avenue = [LineString(s.centerline) for s in m.road_segments
              if s.road_class == "avenue" and s.level == 0]
    stations = [Point(s.position[0], s.position[1]) for s in m.stations]
    pre = [Point(*c.bld[b].entrances[0].position) for b in
           sorted(x for x in precinct.values() if x)]
    sh = X.shape
    f = {}
    pol = base["police"] + (0.25 * _falloff(stations, pts, 250.0) +
                            0.3 * _falloff(pre, pts, 350.0) +
                            0.05 * _falloff(avenue, pts, 40.0)).reshape(sh)
    f["police"] = np.where(land, pol, base["police"])
    elev = _falloff(raised, pts, 80.0).reshape(sh)
    al = _falloff(alley, pts, 40.0).reshape(sh)
    w = base["wealth"] + (0.12 * _falloff(amen, pts, 150.0) +
                          0.08 * _falloff(land_mark, pts, 400.0)).reshape(sh) - \
        0.15 * elev - 0.05 * al
    f["wealth"] = np.where(land, w, base["wealth"])
    dg = base["danger"] + 0.15 * al + 0.15 * elev - 0.3 * (f["police"] - base["police"]) - \
        0.1 * (f["wealth"] - base["wealth"])
    f["danger"] = np.where(land, dg, base["danger"])
    out = []
    for key in ("wealth", "danger", "police"):
        vals = np.clip(f[key], 0.0, 1.0).ravel()
        values = [round(float(x), 2) + 0.0 for x in vals]
        rec = {"id": f"field.{key}", "type": f"field.{key}", "kind": key,
               "origin": (q(x0), q(y0)), "cell_m": CELL_M, "nx": nx, "ny": ny,
               "values": values, "attrs": {}}
        c.fields[key] = rec
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Points of interest
# ---------------------------------------------------------------------------

class _Spacer:
    """Minimum spacing between accepted points, by group."""

    def __init__(self, cell: float = 50.0):
        self.cell = cell
        self.grid: dict = {}

    def free(self, group: str, p, gap: float) -> bool:
        k = (int(math.floor(p[0] / self.cell)), int(math.floor(p[1] / self.cell)))
        r = int(math.ceil(gap / self.cell))
        for i in range(k[0] - r, k[0] + r + 1):
            for j in range(k[1] - r, k[1] + r + 1):
                for x, y in self.grid.get((group, i, j), ()):
                    if _d2((x, y), p) < gap * gap - 1e-9:
                        return False
        return True

    def add(self, group: str, p) -> None:
        k = (group, int(math.floor(p[0] / self.cell)), int(math.floor(p[1] / self.cell)))
        self.grid.setdefault(k, []).append((p[0], p[1]))


def _bar_name(sub: str, key: str, k: int) -> str:
    a, n, s = _pick(ADJ, "na", key, k), _pick(NOUN, "nn", key, k), _pick(SURNAME, "ns", key, k)
    form = int(_u("nf", key, k) * 4)
    if sub == "club":
        return (f"Club {n}", f"{a} {n} Club", f"The {n} Room", f"{a}{n.lower()}")[form]
    if sub == "arcade":
        return (f"{a} Arcade", f"{n} Arcade", f"Pixel {n}", f"{a} {n} Games")[form]
    return (f"The {a} {n}", f"{n} & {_pick(NOUN, 'n2', key, k)}", f"{s}'s Bar",
            f"{a} {n} Lounge")[form]


def _clinic_name(sub: str, key: str, k: int, district: str) -> str:
    a, n, s = _pick(ADJ, "na", key, k), _pick(NOUN, "nn", key, k), _pick(SURNAME, "ns", key, k)
    form = int(_u("nf", key, k) * 4)
    if sub == "ripperdoc":
        return (f"{s}'s Chrome Shop", f"{a} Augments", f"{n} Cybernetics",
                f"Doc {s}'s Ripper Clinic")[form]
    return (f"{district} Medical", f"{a} Cross Clinic", f"Dr. {s}'s Clinic",
            f"{n} Health")[form]


def _vendor_name(sub: str, key: str, k: int) -> str:
    a, n, s = _pick(ADJ, "na", key, k), _pick(NOUN, "nn", key, k), _pick(SURNAME, "ns", key, k)
    form = int(_u("nf", key, k) * 4)
    if sub == "food":
        return (f"{s}'s Noodles", f"{a} Wok", f"{n} Ramen", f"{a} {n} Diner")[form]
    if sub == "pawn":
        return (f"{s} Pawn & Loan", f"{a} Exchange", f"{n} Trading", f"{s}'s Salvage")[form]
    return (f"{a}Mart", f"24/7 {n}", f"{s} General Store", f"{n} Corner Shop")[form]


def _tier(w: float) -> str:
    return "capsule" if w < 0.3 else "studio" if w < 0.55 else "apartment" if w < 0.8 else \
        "penthouse"


def _building_label(b, k: int) -> str:
    a, n, s = _pick(ADJ, "ba", b.id, k), _pick(NOUN, "bn", b.id, k), _pick(SURNAME, "bs", b.id, k)
    t = (b.type or "").split(".")[-1]
    if t == "megabuilding":
        return f"Megabuilding {n}" if k % 2 == 0 else f"{n} Block"
    if t in ("shanty_stack", "terraced"):
        return f"{n} Stacks"
    if t == "villa":
        return f"{s} House"
    if t == "courtyard_block":
        return f"{a} Court"
    if b.height_m >= 60.0:
        return f"{s} Tower"
    return f"{a} {n} Residences"


def _main_entrance(b, prefer=("main", "gate")):
    for kind in prefer:
        for e in b.entrances:
            if e.kind == kind:
                return e
    return b.entrances[0] if b.entrances else None


def build_pois(c: Ctx) -> list[dict]:
    m = c.m
    sp = _Spacer()
    pois: list[dict] = []

    def accept(rec: dict, group: str, gap: float) -> None:
        p = rec["position"]
        sp.add(group, p)
        sp.add("any", p)
        pois.append(rec)

    def common(b, pos, did):
        return {"zone_id": zone_at(c, b, pos),
                "wealth": q(c.field_at("wealth", pos[0], pos[1])),
                "danger": q(c.field_at("danger", pos[0], pos[1]))}

    # ground-floor units: bars, clinics, vendors
    cands: dict[tuple, list] = {}
    for b in m.buildings:
        did = b.district_id
        if did is None or did not in c.vals:
            continue
        for k, u in enumerate(b.units):
            if u.use not in UNIT_POI or u.entrance is None:
                continue
            kind, sub = UNIT_POI[u.use]
            s = c.seg.get(u.segment_id)
            w = FRONT_W.get(s.road_class if s else "", 0.8)
            dz = c.field_at("danger", *u.entrance)
            wl = c.field_at("wealth", *u.entrance)
            if sub in ("ripperdoc", "pawn"):
                w *= 0.6 + 0.8 * dz
            elif sub == "clinic":
                w *= 0.6 + 0.8 * wl
            score = round(_u("poi", b.id, k) * w, 9)
            cands.setdefault((did, kind), []).append((-score, b.id, k, u, sub))
    for d in c.dist:
        rates = RATES.get(d.archetype, RATES["midtown_mixed"])
        for ki, kind in enumerate(("bar", "clinic", "vendor")):
            pool = sorted(cands.get((d.id, kind), []), key=lambda t: t[:3])
            want = int(rates[ki] * c.area_km2[d.id] + 0.5)
            if rates[ki] > 0 and pool:
                want = max(want, 1)
            got = 0
            for _, bid, k, u, sub in pool:
                if got >= want:
                    break
                p = (q(u.entrance[0]), q(u.entrance[1]))
                if not sp.free(kind, p, SPACING_M[kind]) or not sp.free("any", p, POI_GAP_M):
                    continue
                acc = c.access(p, "unit", u.segment_id)
                if acc is None:
                    continue
                b = c.bld[bid]
                pid = f"{bid}.u{k:02d}.{kind}"
                if kind == "bar":
                    name = c.names.take(lambda t: _bar_name(sub, pid, t))
                elif kind == "clinic":
                    name = c.names.take(lambda t: _clinic_name(sub, pid, t, d.name))
                else:
                    name = c.names.take(lambda t: _vendor_name(sub, pid, t))
                hours = HOURS.get(sub)
                if sub == "food":
                    hours = _pick(FOOD_HOURS, "hours", pid)
                if sub == "ripperdoc" and c.field_at("danger", *p) >= 0.5:
                    hours = (0, 24)
                accept({"id": pid, "type": f"poi.{kind}", "kind": kind, "sub": sub,
                        "name": name, "district_id": d.id, "building_id": bid,
                        "unit_index": k, "host_id": None, "position": (p[0], p[1], 0.0),
                        "floor": 0, "entrances": [acc], "hours": hours,
                        **common(b, p, d.id), "faction_id": None,
                        "attrs": {"unit_use": u.use, "unit_width_m": u.width_m}},
                       kind, SPACING_M[kind])
                got += 1

    # apartments
    apt: dict[str, list] = {}
    for b in m.buildings:
        if b.district_id not in c.vals or b.landmark or b.megasite_id or b.floors < 2 or \
                b.use not in ("residential", "mixed", "hotel"):
            continue
        e = _main_entrance(b)
        if e is None:
            continue
        apt.setdefault(b.district_id, []).append((-round(_u("apt", b.id), 9), b.id, e))
    for d in c.dist:
        rate = RATES.get(d.archetype, RATES["midtown_mixed"])[3]
        want = int(rate * c.area_km2[d.id] + 0.5)
        got = 0
        for _, bid, e in sorted(apt.get(d.id, []), key=lambda t: t[:2]):
            if got >= want:
                break
            p = (q(e.position[0]), q(e.position[1]))
            if not sp.free("apartment", p, SPACING_M["apartment"]) or \
                    not sp.free("any", p, POI_GAP_M):
                continue
            acc = c.access(p, e.kind, e.segment_id)
            if acc is None:
                continue
            b = c.bld[bid]
            tier = _tier(c.field_at("wealth", *p))
            floor = b.floors - 1 if tier == "penthouse" else \
                1 + int(_u("aptf", bid) * max(1, b.floors - 1))
            floor = max(1, min(floor, b.floors - 1)) if b.floors > 1 else 0
            nn = 1 + int(_u("aptn", bid) * 12)
            pid = f"{bid}.apt{floor:03d}"
            label = c.names.take(lambda t: f"{_building_label(b, t)}, Apt {floor}-{nn:02d}")
            accept({"id": pid, "type": "poi.apartment", "kind": "apartment", "sub": tier,
                    "name": label, "district_id": d.id, "building_id": bid,
                    "unit_index": None, "host_id": None,
                    "position": (p[0], p[1], q(floor * b.floor_height_m)), "floor": floor,
                    "entrances": [acc], "hours": (0, 24), **common(b, p, d.id),
                    "faction_id": None, "attrs": {"building_floors": b.floors}},
                   "apartment", SPACING_M["apartment"])
            got += 1

    # hideouts: in each gang turf
    lots_by_block: dict[str, list] = {}
    for b in m.buildings:
        if b.lot_id in c.lot and not b.landmark and not b.megasite_id and b.entrances:
            lots_by_block.setdefault(c.lot[b.lot_id].block_id, []).append(b)
    HIDE_W = {"warehouse": 1.0, "shed": 1.0, "yard": 0.8, "hangar": 0.8, "shanty_stack": 0.8,
              "terraced": 0.6, "shopfront_row": 0.5, "courtyard_block": 0.5}
    HIDE_ANY = 0.15
    for zid in sorted(c.zone_poly):
        fid = c.zone_faction[zid]
        if c.factions[fid]["kind"] != "gang":
            continue
        z_blocks = [bid for bid, z in c.turf_of_block.items() if z == zid]
        pool = []
        for blk in sorted(z_blocks):
            for b in lots_by_block.get(blk, []):
                t = (b.type or "").split(".")[-1]
                e = _main_entrance(b, ("loading", "service", "main"))
                dz = c.field_at("danger", *e.position)
                pool.append((-round(_u("hide", b.id) * HIDE_W.get(t, HIDE_ANY) * (0.5 + dz), 9),
                             b.id, e, t))
        area = c.zone_poly[zid].area / 1e6
        want = 1 + (area > 0.8)
        got = 0
        for _, bid, e, t in sorted(pool, key=lambda x: x[:2]):
            if got >= want:
                break
            p = (q(e.position[0]), q(e.position[1]))
            if not sp.free("hideout", p, SPACING_M["hideout"]) or not sp.free("any", p,
                                                                               POI_GAP_M):
                continue
            acc = c.access(p, e.kind, e.segment_id)
            if acc is None:
                continue
            b = c.bld[bid]
            sub = "warehouse" if t in ("warehouse", "shed", "yard", "hangar") else \
                "squat" if t in ("shanty_stack", "terraced") else "back_room"
            gang = c.factions[fid]["name"]
            pid = f"{bid}.hideout"
            name = c.names.take(lambda k: f"{gang} {_pick(LAIR, 'lair', pid, k)}")
            accept({"id": pid, "type": "poi.hideout", "kind": "hideout", "sub": sub,
                    "name": name, "district_id": b.district_id, "building_id": bid,
                    "unit_index": None, "host_id": None, "position": (p[0], p[1], 0.0),
                    "floor": 0, "entrances": [acc], "hours": (0, 24),
                    **common(b, p, b.district_id), "faction_id": fid,
                    "attrs": {"building_type": t}}, "hideout", SPACING_M["hideout"])
            got += 1

    # fixers: a table in a bar of the district (the most dangerous first)
    for d in c.dist:
        v = c.vals[d.id]
        want = 1 + (v["danger"] >= 0.5 and c.area_km2[d.id] >= 1.0)
        hosts = [p for p in pois if p["district_id"] == d.id and p["kind"] == "bar" and
                 p["sub"] in ("bar", "club")]
        if not hosts:
            hosts = [p for p in pois if p["district_id"] == d.id and p["kind"] in (
                "vendor", "clinic")]
        hosts.sort(key=lambda p: (-round(p["danger"] + 0.3 * _u("fixer", p["id"]), 9),
                                  p["id"]))
        for h in hosts[:want]:
            pid = f"{h['id']}.fixer"
            name = c.names.take(lambda k: (
                f"{_pick(FIRST, 'ff', pid, k)} '{_pick(HANDLE, 'fh', pid, k)}' "
                f"{_pick(SURNAME, 'fs', pid, k)}") if _u("fform", pid, k) < 0.6 else
                f"{_pick(HANDLE, 'fh', pid, k)} {_pick(SURNAME, 'fs', pid, k)}")
            pois.append({**h, "id": pid, "type": "poi.fixer", "kind": "fixer", "sub": "fixer",
                         "name": name, "host_id": h["id"], "hours": HOURS["fixer"],
                         "entrances": [dict(a) for a in h["entrances"]],
                         "attrs": {"venue": h["name"]}})
    pois.sort(key=lambda p: p["id"])
    return pois


# ---------------------------------------------------------------------------
# Parking
# ---------------------------------------------------------------------------

UNDER_ARCH = ("corporate_core", "megablock_residential", "midtown_mixed", "transit_hub",
              "research_campus")
LOT_ARCH = ("industrial_port", "spaceport", "research_campus")
LOT_KINDS = ("warehouse", "shed", "hangar", "lab", "terminal")
STALL_M2 = 25.0


def _ground_foot(b):
    polys = [G.from_model_poly(ms.footprint) for ms in b.masses
             if ms.z0_m <= 0.5 and ms.role != "void"]
    if b.footprint is not None:
        polys.append(G.from_model_poly(b.footprint))
    return G.union(polys) if len(polys) > 1 else (polys[0] if polys else None)


def lot_obstacles(m):
    """What a surface lot must keep clear of: building footprints and the carriageways of
    ground roads, with an STRtree over them."""
    geoms = [G.from_model_poly(b.footprint) for b in m.buildings if b.footprint is not None]
    for s in m.road_segments:
        if s.bridge or s.road_class in ("pedestrian", "footbridge") or s.level > 0:
            continue
        cs = s.cross_section
        half = (cs.total_width_m - cs.sidewalk_m[0] - cs.sidewalk_m[1]) / 2.0
        geoms.append(G.snap(LineString(s.centerline).buffer(max(half, 0.5), cap_style="flat")))
    return geoms, (shapely.STRtree(geoms) if geoms else None)


def lot_clash(poly, obstacles) -> float:
    """Largest overlap (m2) of a lot polygon with one obstacle."""
    geoms, tree = obstacles
    if tree is None:
        return 0.0
    worst = 0.0
    for i in sorted(tree.query(poly, predicate="intersects").tolist()):
        worst = max(worst, G.area(G.inter(poly, geoms[i])))
    return worst


def build_parking(c: Ctx) -> list[dict]:
    m = c.m
    out: list[dict] = []
    for b in m.buildings:
        t = (b.type or "").split(".")[-1]
        did = b.district_id or (c.district_at(b.entrances[0].position) if b.entrances else
                                None)
        if b.footprint is None or not b.entrances:
            continue
        area = G.area(G.from_model_poly(b.footprint))
        if t == "parking_structure" or b.use == "parking":
            e = _main_entrance(b, ("garage", "main", "service"))
            acc = c.access(e.position, "garage", e.segment_id)
            if acc is None:
                continue
            levels = max(1, b.floors)
            out.append({"id": f"{b.id}.garage", "type": "parking.garage", "kind": "garage",
                        "district_id": did, "building_id": b.id, "lot_id": b.lot_id,
                        "segment_id": e.segment_id, "polygon": b.footprint.model_dump(),
                        "line": [], "levels": levels, "underground": False,
                        "capacity": int(levels * area / 28.0), "entrances": [acc],
                        "attrs": {}})
            continue
        if did not in c.arch or c.arch[did] not in UNDER_ARCH or b.landmark or \
                area < 1500.0 or b.use not in ("office", "residential", "mixed", "hotel") or \
                _u("garage", b.id) >= 0.4:
            continue
        e = next((x for x in b.entrances if x.kind == "service"), None)
        if e is None:
            continue
        acc = c.access(e.position, "garage", e.segment_id, drive_reach=CURB_REACH_M)
        if acc is None:
            continue
        levels = 3 if b.height_m > 100.0 else 2
        out.append({"id": f"{b.id}.garage", "type": "parking.garage", "kind": "garage",
                    "district_id": did, "building_id": b.id, "lot_id": b.lot_id,
                    "segment_id": e.segment_id, "polygon": b.footprint.model_dump(),
                    "line": [], "levels": levels, "underground": True,
                    "capacity": min(600, int(levels * area / 30.0)), "entrances": [acc],
                    "attrs": {}})
    # surface lots in deep front setbacks
    by_lot: dict[str, list] = {}
    for b in m.buildings:
        if b.lot_id:
            by_lot.setdefault(b.lot_id, []).append(b)
    trunks = [Point(p.position[0], p.position[1]) for p in m.plants if p.position[2] <= 0.5] + \
        [Point(p.position[0], p.position[1]) for p in m.props if p.position[2] <= 0.5]
    ttree = shapely.STRtree(trunks) if trunks else None
    obstacles = None
    for lt in m.lots:
        bs = by_lot.get(lt.id, [])
        if lt.archetype not in LOT_ARCH or len(bs) != 1 or not lt.frontage:
            continue
        b = bs[0]
        if (b.type or "").split(".")[-1] not in LOT_KINDS:
            continue
        foot = _ground_foot(b)
        if foot is None:
            continue
        f = lt.frontage[0]
        fl = LineString(f.line)
        depth = G.dist(fl, foot) - 2.0
        if depth < 11.0 or f.length_m < 20.0:
            continue
        lp = G.from_model_poly(lt.polygon)
        strip = G.inter(lp, G.snap(fl.buffer(depth, cap_style="flat", join_style="mitre")))
        strip = G.diff(strip, G.snap(foot.buffer(2.0, join_style="mitre")))
        parts = sorted(G.parts(strip), key=lambda p: (-G.area(p), G.qbounds(p)))
        if not parts or G.area(parts[0]) < 400.0:
            continue
        lot_poly = parts[0]
        if ttree is not None and len(ttree.query(lot_poly, predicate="intersects")):
            continue
        if obstacles is None:
            obstacles = lot_obstacles(m)
        if lot_clash(lot_poly, obstacles) > 0.5:
            continue
        mid = fl.interpolate(0.5, normalized=True)
        door = G.nearest(lot_poly.exterior, mid)
        acc = c.access(door, "gate", f.segment_id, drive_reach=CURB_REACH_M)
        if acc is None:
            continue
        out.append({"id": f"{lt.id}.parking", "type": "parking.lot", "kind": "lot",
                    "district_id": lt.district_id, "building_id": b.id, "lot_id": lt.id,
                    "segment_id": f.segment_id, "polygon": G.to_model_poly(lot_poly),
                    "line": [], "levels": 1, "underground": False,
                    "capacity": int(G.area(lot_poly) / STALL_M2), "entrances": [acc],
                    "attrs": {"area_m2": q(G.area(lot_poly))}})
    # curb parking
    for s in m.road_segments:
        cs = s.cross_section
        sides = int(cs.parking[0]) + int(cs.parking[1])
        if not sides or s.id not in c.lane_seg:
            continue
        L = G.length(LineString(s.centerline))
        cap = int(sides * max(0.0, L - 20.0) / 6.5)
        if cap <= 0:
            continue
        out.append({"id": f"{s.id}.parking", "type": "parking.street", "kind": "street",
                    "district_id": s.district_ids[0] if s.district_ids else None,
                    "building_id": None, "lot_id": None, "segment_id": s.id, "polygon": None,
                    "line": [tuple(p) for p in s.centerline], "levels": 1,
                    "underground": False, "capacity": cap, "entrances": [],
                    "attrs": {"sides": sides}})
    out.sort(key=lambda r: r["id"])
    return out


# ---------------------------------------------------------------------------
# Taxi stands and fast travel
# ---------------------------------------------------------------------------

TAXI_GAP_M = 250.0
FAST_GAP_M = 350.0


def build_travel(c: Ctx, pois: list[dict]) -> list[dict]:
    m = c.m
    out: list[dict] = []
    sp = _Spacer(cell=100.0)

    dname = {d.id: d.name for d in c.dist}
    taken: set[str] = set()     # one stand per road segment (its id)

    cands = []
    for s in m.stations:
        cands.append((0, s.id, (s.position[0], s.position[1]), f"{s.name} Station"))
    for b in m.buildings:
        if (b.use == "hotel" or b.landmark) and b.entrances:
            e = _main_entrance(b)
            cands.append((1, b.id, tuple(e.position), b.name))
    for p in pois:
        if p["kind"] == "bar" and c.arch.get(p["district_id"]) in (
                "entertainment_market", "midtown_mixed", "old_town"):
            cands.append((2, p["id"], p["position"][:2], p["name"]))
    for rank, nid, pos, label in cands:
        did = c.district_at(pos)
        if did is None:
            continue
        acc = c.access(pos, "curb", None, drive_reach=120.0)
        if acc is None:
            continue
        p = c.on_walk(acc, acc["curb"])
        seg = c.lanes[c.lane_ix[acc["lane_id"]]].segment_id
        if not sp.free("taxi", p, TAXI_GAP_M) or seg in taken:
            continue
        sp.add("taxi", p)
        taken.add(seg)
        cen = c.center[did]
        base = label or f"{dname[did]} {compass(p[0] - cen[0], p[1] - cen[1])}"
        out.append({"id": f"{seg}.taxi", "type": "travel.taxi_stand", "kind": "taxi_stand",
                    "name": c.names.take(lambda k: f"{base} Taxi" if k == 0 else
                                         f"{base} Taxi {k + 1}"),
                    "district_id": did, "position": p, "access": acc, "near_id": nid,
                    "attrs": {"rank": rank}})
    # fast travel
    for d in c.dist:
        n = max(1, min(4, int(c.area_km2[d.id] / 0.7 + 0.5)))
        cen = c.center[d.id]
        cand = []
        for s in m.stations:
            if shapely.contains_xy(c.dpoly[d.id], s.position[0], s.position[1]):
                cand.append((1.0, s.id, (s.position[0], s.position[1]), f"{s.name} Station"))
        for pl in m.places:
            if pl.district_id == d.id:
                cand.append((0.9, pl.id, tuple(pl.label_at), pl.name))
        for b in m.buildings:
            if b.landmark and b.district_id == d.id and b.entrances:
                cand.append((0.9, b.id, tuple(_main_entrance(b).position), b.name))
        pos = {nd.id: nd.position for nd in m.road_nodes}
        for j in m.junctions:
            if j.signalized and j.node_id in pos:
                x, y = pos[j.node_id][:2]
                if shapely.contains_xy(c.dpoly[d.id], x, y):
                    cand.append((0.7, j.node_id, (x, y), None))
        chosen: list = []
        if not cand:
            cand = fast_fallback(c, d.id)
        while len(chosen) < n and cand:
            def score(t):
                if not chosen:
                    return (t[0], -round(_d2(t[2], cen), 4), t[1])
                return (round(t[0] * min(_d2(t[2], ch[2]) for ch in chosen), 4), 0.0, t[1])
            best = max(cand, key=score)
            cand.remove(best)
            if chosen and min(_d2(best[2], ch[2]) for ch in chosen) < FAST_GAP_M ** 2:
                continue
            acc = c.access(best[2], "curb", None, drive_reach=120.0)
            if acc is None:
                if not cand and not chosen and best[0] > 0.5:
                    cand = fast_fallback(c, d.id)
                continue
            p = c.on_walk(acc, best[2])
            chosen.append(best)
            where = best[3] or f"{d.name} {compass(best[2][0] - cen[0], best[2][1] - cen[1])}"
            out.append({"id": f"{best[1]}.fast_travel", "type": "travel.fast_travel",
                        "kind": "fast_travel",
                        "name": c.names.take(lambda k: where if k == 0 else f"{where} {k + 1}"),
                        "district_id": d.id, "position": p, "access": acc, "near_id": best[1],
                        "attrs": {}})
    out.sort(key=lambda r: r["id"])
    return out


def fast_fallback(c: Ctx, did: str) -> list:
    """Fast-travel candidates for a district without a station, place, landmark or signalized
    junction that serves: its other junctions, then the middle of each of its drive lanes."""
    pos = {nd.id: nd.position for nd in c.m.road_nodes}
    out = []
    for j in c.m.junctions:
        if not j.signalized and j.node_id in pos:
            x, y = pos[j.node_id][:2]
            if shapely.contains_xy(c.dpoly[did], x, y):
                out.append((0.5, j.node_id, (x, y), None))
    for ln, mid in lane_points(c, did):
        out.append((0.3, ln.id, mid, None))
    return out


def lane_points(c: Ctx, did: str) -> list:
    """(lane, its middle) for the drive lanes of the district's roads."""
    out = []
    for i, ln in enumerate(c.lanes):
        s = c.seg[ln.segment_id]
        if (s.district_ids[0] if s.district_ids else None) == did:
            x, y = _half(ln.centerline)
            out.append((ln, (q(x), q(y))))
    return out


# ---------------------------------------------------------------------------
# Densities
# ---------------------------------------------------------------------------

def build_densities(c: Ctx, pois: list[dict]) -> list[dict]:
    m = c.m
    units: dict[str, int] = {}
    for b in m.buildings:
        for u in b.units:
            if u.segment_id:
                units[u.segment_id] = units.get(u.segment_id, 0) + 1
    st = [Point(s.position[0], s.position[1]) for s in m.stations]
    stree = shapely.STRtree(st) if st else None
    out = []
    for s in m.road_segments:
        L = max(G.length(LineString(s.centerline)), 1.0)
        mid = _half(s.centerline)
        did = s.district_ids[0] if s.district_ids else c.district_at(mid)
        arch = c.arch.get(did, "midtown_mixed")
        act = min(1.0, units.get(s.id, 0) / (L / 100.0) / 8.0)
        boost = 1.0
        if stree is not None and len(stree.query(Point(mid), predicate="dwithin",
                                                 distance=150.0)):
            boost = 1.4
        cls = s.road_class
        tp = TRAFFIC.get(arch, TRAFFIC["midtown_mixed"])
        cp = CROWD.get(arch, CROWD["midtown_mixed"])
        lanes = s.lanes if cls in LANE_CAP else 0
        cap = lanes * LANE_CAP.get(cls, 0.0) * PEAK_USE.get(cls, 0.0)
        speed = SPEED.get(cls, 0.0)
        walk = WALKERS.get(cls, 0.0)
        if cls not in ("pedestrian", "footbridge") and not any(s.cross_section.sidewalk_m):
            walk = 0.0 if cls in ("highway", "avenue", "street") or s.level > 0 else walk
        dz = c.field_at("danger", *mid)
        pz = c.field_at("police", *mid)
        zid = None
        for z in sorted(c.zone_poly):
            if shapely.contains_xy(c.zone_poly[z], mid[0], mid[1]):
                zid = z
                break
        gang = zid is not None and c.factions[c.zone_faction[zid]]["kind"] == "gang"
        tr, veh, cr, gg, po = [], [], [], [], []
        for k in range(len(BANDS)):
            t = cap * tp[k] * (0.6 + 0.4 * act) if cls != "highway" else cap * tp[k]
            tr.append(q(t))
            veh.append(q(t / speed / 10.0) if speed > 0 else 0.0)
            crowd = walk * cp[k] * (0.3 + 0.7 * act) * boost
            cr.append(q(crowd))
            gg.append(q(1.5 * dz * GANG_HOURS[k] * (1.0 if gang else 0.3)) if walk > 0 else
                      0.0)
            po.append(q(0.8 * pz * (1.2 if cls == "avenue" else 1.0) * (0.5 + 0.5 * cp[k])))
        out.append({"id": f"{s.id}.density", "type": "density", "segment_id": s.id,
                    "district_id": did, "speed_kmh": speed, "traffic_vph": tr,
                    "vehicles_per_100m": veh, "crowd_per_100m": cr, "gang_per_100m": gg,
                    "police_per_100m": po,
                    "attrs": {"zone_id": zid, "activity": q(act)}})
    return out


# ---------------------------------------------------------------------------
# Sign and ad slots
# ---------------------------------------------------------------------------

def _audience(dens: dict | None) -> float:
    if dens is None:
        return 0.0
    return q(dens["traffic_vph"][3] * 1.3 + dens["crowd_per_100m"][3] * 47.0)


def _edges(fp):
    """Exterior edges of a footprint, counterclockwise: (a, b, length, outward normal)."""
    ring = [(float(x), float(y)) for x, y in fp.exterior]
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    area2 = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1]))
    if area2 < 0:
        ring = ring[::-1]
    out = []
    for a, b in zip(ring, ring[1:] + ring[:1]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > 1e-6:
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            out.append((a, b, L, (uy, -ux)))
    return out


def _yaw(nx: float, ny: float) -> float:
    from . import dmath as M

    return round(M.degrees(M.atan2(ny, nx)), 1) + 0.0


def build_sign_slots(c: Ctx, dens: dict) -> list[dict]:
    m = c.m
    out: list[dict] = []
    segs = [s for s in m.road_segments]
    slines = [LineString(s.centerline) for s in segs]
    sgeo = np.array(slines, dtype=object)
    stree = shapely.STRtree(slines) if slines else None
    foots, fids = [], []
    for b in m.buildings:
        if b.footprint is not None:
            foots.append(G.from_model_poly(b.footprint))
            fids.append(b.id)
    fgeo = np.array(foots, dtype=object)
    ftree = shapely.STRtree(foots) if foots else None

    def facing(px, py):
        hit = _nearest(stree, sgeo, Point(px, py), 60.0)
        return segs[hit[1]].id if hit else None

    # shop signs: the M6 sign props
    sign_top: dict[str, float] = {}
    for p in m.props:
        if p.type != "prop.sign":
            continue
        x, y, z = p.position
        blade = bool(p.attrs.get("blade"))
        w = q(1.2 * p.scale[1])
        h = q(1.8 * p.scale[2])
        bid = None
        hit = _nearest(ftree, fgeo, Point(x, y), 3.0)
        yaw = p.yaw_deg
        if hit is not None:
            bid = fids[hit[1]]
            if not blade:
                a = math.radians(p.yaw_deg)
                nx, ny = math.sin(a), -math.cos(a)
                if shapely.contains_xy(foots[hit[1]], x + nx * 0.5, y + ny * 0.5):
                    nx, ny = -nx, -ny
                yaw = _yaw(nx, ny)
        sid = facing(x, y)
        if bid is not None:
            sign_top[bid] = max(sign_top.get(bid, 0.0), z + h)
        out.append({"id": f"{p.id}.slot", "type": "sign_slot.shop_sign", "kind": "shop_sign",
                    "mount": "blade" if blade else "facade", "building_id": bid,
                    "prop_id": p.id, "roof_item": None, "position": (x, y, q(z + h / 2.0)),
                    "yaw_deg": yaw, "width_m": w, "height_m": h, "emitter": True,
                    "two_sided": blade, "content": p.attrs.get("use") or "shop",
                    "segment_id": sid, "audience": _audience(dens.get(sid)), "attrs": {}})
    # roof billboards (M3) and the new slots
    sky_ends: dict[str, list] = {}
    for sb in m.skybridges:
        for bid, pt in zip(sb.building_ids, sb.line):
            sky_ends.setdefault(bid, []).append((pt, sb.z_m))
    for b in m.buildings:
        did = b.district_id
        neon = c.vals[did]["neon"] if did in c.vals else 0.3
        for k, it in enumerate(b.roof_items):
            if it.kind != "billboard":
                continue
            x, y, z = it.position
            yaw = it.yaw_deg + 90.0
            sid = facing(x, y)
            out.append({"id": f"{b.id}.roof{k:02d}.billboard", "type": "sign_slot.billboard",
                        "kind": "billboard", "mount": "roof", "building_id": b.id,
                        "prop_id": None, "roof_item": k,
                        "position": (q(x), q(y), q(z + it.size[2] / 2.0)),
                        "yaw_deg": round(((yaw + 180.0) % 360.0) - 180.0, 1) + 0.0,
                        "width_m": q(it.size[0]), "height_m": q(it.size[2]), "emitter": True,
                        "two_sided": True, "content": "ad", "segment_id": sid,
                        "audience": _audience(dens.get(sid)), "attrs": {}})
        if b.footprint is None or b.landmark or b.portals or b.megasite_id:
            continue
        H = b.height_m
        prisms = [ms for ms in b.masses if ms.shape == "prism" and ms.role != "void"]
        if not prisms:
            continue
        top = max(b.masses, key=lambda ms: (ms.z1_m, -ms.z0_m))
        fp = top.footprint
        edges = _edges(fp)
        # the main body: the prism with most volume
        body = max(prisms, key=lambda ms: (round((ms.z1_m - ms.z0_m) *
                                                 G.area(G.from_model_poly(ms.footprint)), 2),
                                           ms.z1_m))
        bedges = _edges(body.footprint)
        ends = sky_ends.get(b.id, [])

        def clear(a, bb, z0, z1):
            for pt, zs in ends:
                if z0 - 4.0 <= zs <= z1 + 4.0 and \
                        LineString([a, bb]).distance(Point(pt)) < 3.0:
                    return False
            return True

        def best_edge(edges, classes, min_len):
            best = None
            for i, (a, bb, L, (nx, ny)) in enumerate(edges):
                if L < min_len:
                    continue
                mx, my = (a[0] + bb[0]) / 2.0, (a[1] + bb[1]) / 2.0
                hit = _nearest(stree, sgeo, Point(mx + nx * 6.0, my + ny * 6.0), 45.0,
                               ok=lambda j: segs[j].road_class in classes)
                if hit is None:
                    continue
                sid = segs[hit[1]].id
                aud = _audience(dens.get(sid))
                key = (aud, round(L, 4), -i)
                if best is None or key > best[0]:
                    best = (key, i, sid, aud)
            return best
        # facade billboard facing a highway or avenue
        if H >= 25.0 and _u("bb", b.id) < 0.3 + 0.5 * neon:
            be = best_edge(bedges, ("highway", "avenue"), 12.0)
            if be is not None:
                _, i, sid, aud = be
                a, bb, L, (nx, ny) = bedges[i]
                w = q(min(0.7 * L, 30.0))
                h = q(w * 0.45)
                z0, z1 = body.z0_m, body.z1_m
                zc = q(min(max(z0 + 0.65 * (z1 - z0), z0 + h / 2.0 + 2.0, h / 2.0 + 12.0),
                           z1 - h / 2.0 - 2.0))
                if w >= 8.0 and zc - h / 2.0 >= max(10.0, z0 + 1.0,
                                                    sign_top.get(b.id, 0.0) + 0.5) and \
                        clear(a, bb, zc - h / 2, zc + h / 2):
                    mx, my = (a[0] + bb[0]) / 2.0, (a[1] + bb[1]) / 2.0
                    out.append({"id": f"{b.id}.slot.billboard", "type": "sign_slot.billboard",
                                "kind": "billboard", "mount": "facade", "building_id": b.id,
                                "prop_id": None, "roof_item": None,
                                "position": (q(mx), q(my), zc), "yaw_deg": _yaw(nx, ny),
                                "width_m": w, "height_m": h, "emitter": True,
                                "two_sided": False, "content": "ad", "segment_id": sid,
                                "audience": aud, "attrs": {"edge": i}})
        # holo-ad over a tower roof
        pads = any(it.kind in ("helipad", "av_pad") for it in b.roof_items)
        if H >= 80.0 and not pads and top.shape == "prism" and edges and \
                _u("holo", b.id) < neon * 0.6:
            cx, cy = _center(fp.exterior)
            short = min(L for *_, L, _n in edges)
            w = q(min(max(short * 0.8, 8.0), 30.0))
            h = q(min(max(0.15 * H, 12.0), 40.0))
            if shapely.contains_xy(G.from_model_poly(fp), cx, cy):
                sid = facing(cx, cy)
                out.append({"id": f"{b.id}.slot.holo_ad", "type": "sign_slot.holo_ad",
                            "kind": "holo_ad", "mount": "roof", "building_id": b.id,
                            "prop_id": None, "roof_item": None,
                            "position": (cx, cy, q(top.z1_m + 4.0 + h / 2.0)),
                            "yaw_deg": _yaw(*edges[0][3]), "width_m": w, "height_m": h,
                            "emitter": True, "two_sided": True,
                            "content": "corporate" if c.arch.get(did) in CORP_ARCH else "ad",
                            "segment_id": sid, "audience": _audience(dens.get(sid)),
                            "attrs": {}})
        # neon band at a corner of a mid-rise facade over a shopping street
        if 3 <= b.floors <= 15 and b.units and neon >= 0.4 and _u("neon", b.id) < neon * 0.5:
            # (M14: on a deck, its floors and the band's 8 m count from the deck top)
            floor = float(b.attrs.get("deck_top_m", 0.0)) if b.level else 0.0
            low = [ms for ms in b.masses if ms.z0_m <= floor + 0.5 and ms.role != "void"]
            base = max(low, key=lambda ms: (ms.z1_m, -ms.z0_m)) if low else top
            lo = max(floor + 8.0, sign_top.get(b.id, 0.0) + 0.5)
            h = q(min(base.z1_m - lo - 1.0, 18.0))
            if h >= 4.0:
                es = _edges(base.footprint)
                be = None
                for i, (a, bb, L, (nx, ny)) in enumerate(es):
                    if L < 6.0:
                        continue
                    mx, my = (a[0] + bb[0]) / 2.0, (a[1] + bb[1]) / 2.0
                    hit = _nearest(stree, sgeo, Point(mx + nx * 6.0, my + ny * 6.0), 30.0,
                                   ok=lambda j: segs[j].road_class in (
                                       "street", "avenue", "pedestrian", "alley"))
                    if hit is None:
                        continue
                    sid = segs[hit[1]].id
                    key = (_audience(dens.get(sid)), round(L, 4), -i)
                    if be is None or key > be[0]:
                        be = (key, i, sid)
                if be is not None:
                    _, i, sid = be
                    a, bb, L, (nx, ny) = es[i]
                    ux, uy = (bb[0] - a[0]) / L, (bb[1] - a[1]) / L
                    x, y = a[0] + ux * 1.0, a[1] + uy * 1.0
                    zc = q(lo + h / 2.0)
                    if clear(a, bb, lo, lo + h):
                        out.append({"id": f"{b.id}.slot.neon", "type": "sign_slot.neon",
                                    "kind": "neon", "mount": "facade", "building_id": b.id,
                                    "prop_id": None, "roof_item": None,
                                    "position": (q(x), q(y), zc), "yaw_deg": _yaw(nx, ny),
                                    "width_m": 1.2, "height_m": h, "emitter": True,
                                    "two_sided": False, "content": "district",
                                    "segment_id": sid, "audience": _audience(dens.get(sid)),
                                    "attrs": {"edge": i}})
    out.sort(key=lambda r: r["id"])
    return out


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------

@dataclass
class Out:
    rows: dict
    info: dict
    notes: list


def build(spec, m) -> Out:
    with G.canonical():
        return _build(spec, m)


def _build(spec, m) -> Out:
    c = Ctx(spec, m)
    factions, zones, precinct = factions_and_zones(c)
    fields = build_fields(c, precinct)
    pois = build_pois(c)
    parking = build_parking(c)
    travel = build_travel(c, pois)
    dens = build_densities(c, pois)
    slots = build_sign_slots(c, {d["segment_id"]: d for d in dens})
    info = {"factions": len(factions), "zones": len(zones), "pois": len(pois),
            "parking": len(parking), "travel_points": len(travel), "densities": len(dens),
            "sign_slots": len(slots)}
    return Out({"factions": factions, "zones": zones, "pois": pois, "fields": fields,
                "densities": dens, "parking": parking, "travel_points": travel,
                "sign_slots": slots}, info, [])
