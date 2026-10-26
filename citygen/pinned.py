"""Pinned geometry (scope 4.3): a traced district (an Inkscape SVG in the hand-traced map
conventions of `maps/corporate_core_v*.svg`) imported as fixed; the generator builds around it.

Layers are matched by name (case and spaces ignored): `coast` (one closed path, the island;
extra subpaths are water pockets), `highway`, `avenue`, `street`, `elevated road` (centerlines,
stroke width = road width), `building`, `landmark` (footprints; an open 3-point path is two base
edges of a rectangle; the numeric object label is the height), `water`, `park`, `plaza`, `pier`
(areas). 1 SVG unit = 1 m, y down.

The path parser is our own (absolute and relative M L H V C S Q T A Z): curves are sampled with
plain arithmetic and arcs with `dmath`, so the import is the same bytes on every machine.
"""

from __future__ import annotations

import functools
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import LineString, Polygon

from . import dmath as M
from . import geom as G

ROOT = Path(__file__).resolve().parents[1]      # the repository (maps/ lives there)
SVG_NS = "{http://www.w3.org/2000/svg}"
INK = "{http://www.inkscape.org/namespaces/inkscape}"
LAYERS = {"coast": "coast", "highway": "highway", "avenue": "avenue", "street": "street",
          "elevatedroad": "elevated", "elevated": "elevated", "building": "building",
          "landmark": "landmark", "water": "water", "park": "park", "plaza": "plaza",
          "pier": "pier"}
ROAD_LAYERS = ("highway", "avenue", "street", "elevated")
DEFAULT_WIDTH_M = {"highway": 24.0, "avenue": 18.0, "street": 11.0, "elevated": 20.0}
CURVE_PIECES = 8                # a Bezier segment becomes this many chords
ARC_STEP_RAD = math.pi / 36     # an arc: a chord every 5 degrees at most
SQUARE_TOL_DEG = 12.0           # an open 3-point footprint within this of square is squared


@dataclass
class PinRoad:
    id: str
    road_class: str              # highway | avenue | street (elevated -> highway, elevated)
    line: LineString
    width_m: float
    elevated: bool = False
    closed: bool = False


@dataclass
class PinBuilding:
    id: str
    kind: str                    # building | landmark
    footprint: Polygon
    height_m: float | None


@dataclass
class PinArea:
    id: str
    kind: str                    # water | park | plaza | pier
    polygon: Polygon


@dataclass
class Pinned:
    """A traced district in its own frame: meters, x east, y north, origin at the center of
    the land's bounding box."""
    source: str
    land: Polygon
    roads: list[PinRoad] = field(default_factory=list)
    buildings: list[PinBuilding] = field(default_factory=list)
    areas: list[PinArea] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def placed(self, center: tuple[float, float], rotation_deg: float = 0.0) -> Pinned:
        """The same district moved to `center` (city coordinates) and turned by
        `rotation_deg` counterclockwise, on the 0.01 m grid."""
        a = M.radians(rotation_deg)
        c, s = M.cos(a), M.sin(a)
        cx, cy = center

        def tf(p):
            return (G.q(cx + c * p[0] - s * p[1]), G.q(cy + s * p[0] + c * p[1]))

        def poly(pg: Polygon) -> Polygon:
            out = Polygon([tf(p) for p in pg.exterior.coords[:-1]],
                          [[tf(p) for p in r.coords[:-1]] for r in pg.interiors])
            return G.qpoly(out.buffer(0)) if not out.is_valid else out

        return Pinned(
            source=self.source, land=poly(self.land),
            roads=[PinRoad(r.id, r.road_class, LineString([tf(p) for p in r.line.coords]),
                           r.width_m, r.elevated, r.closed) for r in self.roads],
            buildings=[PinBuilding(b.id, b.kind, poly(b.footprint), b.height_m)
                       for b in self.buildings],
            areas=[PinArea(x.id, x.kind, poly(x.polygon)) for x in self.areas],
            warnings=list(self.warnings))


# ---------------------------------------------------------------------------
# SVG paths
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _arc(p0, rx, ry, phi_deg, large, sweep, p1) -> list[tuple[float, float]]:
    """Points after p0 along an SVG elliptical arc to p1 (endpoint to center
    parameterization, SVG 1.1 appendix F.6)."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    phi = M.radians(phi_deg)
    cp, sp = M.cos(phi), M.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2.0, (p0[1] - p1[1]) / 2.0
    x1 = cp * dx + sp * dy
    y1 = -sp * dx + cp * dy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1.0:
        k = math.sqrt(lam)
        rx, ry = rx * k, ry * k
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    co = math.sqrt(max(0.0, num / den)) if den > 0 else 0.0
    if large == sweep:
        co = -co
    cx1 = co * rx * y1 / ry
    cy1 = -co * ry * x1 / rx
    cx = cp * cx1 - sp * cy1 + (p0[0] + p1[0]) / 2.0
    cy = sp * cx1 + cp * cy1 + (p0[1] + p1[1]) / 2.0
    t0 = M.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    t1 = M.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx)
    dt = t1 - t0
    if sweep and dt < 0:
        dt += 2 * math.pi
    elif not sweep and dt > 0:
        dt -= 2 * math.pi
    n = max(1, int(math.ceil(abs(dt) / ARC_STEP_RAD)))
    out = []
    for i in range(1, n):
        t = t0 + dt * i / n
        ex, ey = rx * M.cos(t), ry * M.sin(t)
        out.append((cp * ex - sp * ey + cx, sp * ex + cp * ey + cy))
    return out + [p1]


def _cubic(p0, c1, c2, p1) -> list[tuple[float, float]]:
    out = []
    for i in range(1, CURVE_PIECES + 1):
        t = i / CURVE_PIECES
        u = 1.0 - t
        a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append((a * p0[0] + b * c1[0] + c * c2[0] + d * p1[0],
                    a * p0[1] + b * c1[1] + c * c2[1] + d * p1[1]))
    out[-1] = p1
    return out


def _quad(p0, c, p1) -> list[tuple[float, float]]:
    return _cubic(p0, (p0[0] + 2 * (c[0] - p0[0]) / 3, p0[1] + 2 * (c[1] - p0[1]) / 3),
                  (p1[0] + 2 * (c[0] - p1[0]) / 3, p1[1] + 2 * (c[1] - p1[1]) / 3), p1)


def subpaths(d: str) -> list[tuple[list[tuple[float, float]], bool]]:
    """(points in SVG coordinates, closed) for every subpath of a path's `d`."""
    toks = _TOKEN.findall(d)
    out: list = []
    pts: list = []
    closed = False
    cur = (0.0, 0.0)
    start = cur
    last_c = None           # last control point (S, T reflect it)
    cmd = None
    i = 0

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def flush():
        nonlocal pts, closed
        if len(pts) >= 2 or (pts and closed):
            out.append((pts, closed))
        pts, closed = [], False

    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                closed = True
                cur = start
                flush()
                last_c = None
                continue
        elif cmd is None:
            raise ValueError(f"path data starts with a number: {d[:40]}")
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        if c == "M":
            flush()
            cur = (ox + num(), oy + num())
            start = cur
            pts = [cur]
            cmd = "l" if rel else "L"     # further pairs are line-to
            last_c = None
        elif c == "L":
            cur = (ox + num(), oy + num())
            pts.append(cur)
            last_c = None
        elif c == "H":
            cur = ((cur[0] if rel else 0.0) + num(), cur[1])
            pts.append(cur)
            last_c = None
        elif c == "V":
            cur = (cur[0], (cur[1] if rel else 0.0) + num())
            pts.append(cur)
            last_c = None
        elif c == "C":
            c1 = (ox + num(), oy + num())
            c2 = (ox + num(), oy + num())
            p1 = (ox + num(), oy + num())
            pts += _cubic(cur, c1, c2, p1)
            cur, last_c = p1, c2
        elif c == "S":
            c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
            c2 = (ox + num(), oy + num())
            p1 = (ox + num(), oy + num())
            pts += _cubic(cur, c1, c2, p1)
            cur, last_c = p1, c2
        elif c == "Q":
            cq = (ox + num(), oy + num())
            p1 = (ox + num(), oy + num())
            pts += _quad(cur, cq, p1)
            cur, last_c = p1, cq
        elif c == "T":
            cq = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
            p1 = (ox + num(), oy + num())
            pts += _quad(cur, cq, p1)
            cur, last_c = p1, cq
        elif c == "A":
            rx, ry, phi = num(), num(), num()
            large, sweep = num() != 0, num() != 0
            p1 = (ox + num(), oy + num())
            pts += _arc(cur, rx, ry, phi, large, sweep, p1)
            cur, last_c = p1, None
        else:
            raise ValueError(f"unsupported path command {cmd}")
    flush()
    # drop repeated points (and the closing repeat of a closed ring)
    clean = []
    for p, cl in out:
        dd = [p[0]]
        for x in p[1:]:
            if math.hypot(x[0] - dd[-1][0], x[1] - dd[-1][1]) > 1e-6:
                dd.append(x)
        if cl and len(dd) > 2 and math.hypot(dd[0][0] - dd[-1][0], dd[0][1] - dd[-1][1]) < 1e-6:
            dd.pop()
        clean.append((dd, cl))
    return clean


def _style(el, key: str) -> str | None:
    m = re.search(key + r"\s*:\s*([^;]+)", el.get("style", "") or "")
    return m.group(1).strip() if m else el.get(key)


def _layers(path: Path) -> dict[str, list[dict]]:
    root = ET.parse(path).getroot()
    out: dict = {}
    for g in root.iter(SVG_NS + "g"):
        if g.get(INK + "groupmode") != "layer":
            continue
        key = LAYERS.get(re.sub(r"[^a-z]", "", (g.get(INK + "label") or "").lower()))
        if key is None:
            continue
        if g.get("transform"):
            raise ValueError(f"layer {key}: transforms are not supported (apply them first)")
        items = out.setdefault(key, [])
        for el in g.iter():
            tag = el.tag.replace(SVG_NS, "")
            if el.get("transform") and tag != "g":
                raise ValueError(f"{el.get('id')}: transforms are not supported")
            d = None
            if tag == "path":
                d = el.get("d")
            elif tag == "rect":
                x, y, w, h = (float(el.get(k, 0)) for k in ("x", "y", "width", "height"))
                d = f"M {x},{y} h {w} v {h} h {-w} Z"
            elif tag in ("circle", "ellipse"):
                cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
                rx = float(el.get("r", el.get("rx", 0)))
                ry = float(el.get("r", el.get("ry", rx)))
                d = (f"M {cx - rx},{cy} A {rx},{ry} 0 1 0 {cx + rx},{cy} "
                     f"A {rx},{ry} 0 1 0 {cx - rx},{cy} Z")
            if not d:
                continue
            sw = _style(el, "stroke-width")
            items.append({"id": el.get("id"), "label": el.get(INK + "label"), "d": d,
                          "stroke_width": float(sw) if sw else None})
    return out


def complete_rect(p1, p2, p3) -> list[tuple[float, float]]:
    """Two traced base edges p2-p1 and p2-p3 (p2 the corner): the four corners, squared when
    within SQUARE_TOL_DEG of a right angle (the legacy pipeline's rule)."""
    ux, uy = p1[0] - p2[0], p1[1] - p2[1]
    vx, vy = p3[0] - p2[0], p3[1] - p2[1]
    L1, L2 = math.hypot(ux, uy), math.hypot(vx, vy)
    a1, a2 = M.atan2(uy, ux), M.atan2(vy, vx)
    diff = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    err = abs(diff) - math.pi / 2
    if abs(M.degrees(err)) <= SQUARE_TOL_DEG:
        sg = 1 if diff > 0 else -1
        b1 = a1 + sg * err / 2
        b2 = b1 + sg * math.pi / 2
        ux, uy = M.cos(b1) * L1, M.sin(b1) * L1
        vx, vy = M.cos(b2) * L2, M.sin(b2) * L2
    return [p2, (p2[0] + ux, p2[1] + uy), (p2[0] + ux + vx, p2[1] + uy + vy),
            (p2[0] + vx, p2[1] + vy)]


def _height(label) -> float | None:
    if not label:
        return None
    m = re.fullmatch(r"\s*(\d+(\.\d+)?)\s*m?\s*", label)
    return float(m.group(1)) if m else None


def load(source: str | Path, root: Path | None = None) -> Pinned:
    """Read a traced SVG. `source` is relative to `root` (the repository) unless absolute."""
    path = Path(source)
    if not path.is_absolute() and root is not None:
        path = root / path
    layers = _layers(path)
    warn: list[str] = []
    coast = layers.get("coast", [])
    rings = []
    for item in coast:
        for p, _ in subpaths(item["d"]):
            if len(p) >= 3:
                pg = Polygon(p)
                rings.append(pg if pg.is_valid else pg.buffer(0))
    if not rings:
        raise ValueError(f"{source}: no closed path on the coast layer")
    rings.sort(key=lambda g: (-g.area, g.bounds))
    land = rings[0]
    if land.geom_type != "Polygon":
        land = max(G.parts(land), key=lambda g: g.area)
    for r in rings[1:]:
        if land.contains(r):
            land = land.difference(r)
        else:
            warn.append("a coast subpath outside the land, ignored")
    if land.geom_type != "Polygon":
        land = max(G.parts(land), key=lambda g: g.area)
    x0, y0, x1, y1 = land.bounds
    ox, oy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def loc(p):     # SVG (y down) -> district frame (y north, origin at the land center)
        return (p[0] - ox, oy - p[1])

    def lpoly(pts) -> Polygon:
        pg = Polygon([loc(p) for p in pts])
        return pg if pg.is_valid else max(G.parts(pg.buffer(0)), key=lambda g: g.area)

    pin = Pinned(source=str(source), land=G.qpoly(
        Polygon([loc(p) for p in land.exterior.coords[:-1]],
                [[loc(p) for p in r.coords[:-1]] for r in land.interiors])), warnings=warn)
    for cat in ROAD_LAYERS:
        for item in layers.get(cat, []):
            for k, (p, closed) in enumerate(subpaths(item["d"])):
                if len(p) < 2:
                    continue
                pts = [loc(x) for x in p] + ([loc(p[0])] if closed else [])
                rid = item["id"] if k == 0 else f"{item['id']}_{k}"
                pin.roads.append(PinRoad(
                    rid, "highway" if cat == "elevated" else cat, G.qline(LineString(pts)),
                    float(item["stroke_width"] or DEFAULT_WIDTH_M[cat]),
                    elevated=cat == "elevated", closed=closed))
    for cat in ("building", "landmark"):
        for item in layers.get(cat, []):
            for k, (p, closed) in enumerate(subpaths(item["d"])):
                if len(p) == 3 and not closed:
                    corners = complete_rect(*p)
                elif len(p) >= 3:
                    corners = p
                else:
                    warn.append(f"{item['id']}: fewer than 3 points, skipped")
                    continue
                pg = lpoly(corners)
                if pg.is_empty or pg.area < 4.0:
                    warn.append(f"{item['id']}: degenerate footprint, skipped")
                    continue
                bid = item["id"] if k == 0 else f"{item['id']}_{k}"
                pin.buildings.append(PinBuilding(bid, cat, G.qpoly(pg), _height(item["label"])))
    # traced footprints that overlap: the later one gives way (the blockout and the checks
    # need disjoint buildings)
    for j in range(len(pin.buildings)):
        bj = pin.buildings[j]
        for i in range(j):
            bi = pin.buildings[i]
            if bi.footprint.intersects(bj.footprint) and \
                    bi.footprint.intersection(bj.footprint).area > 0.01:
                rest = G.diff(bj.footprint, bi.footprint)
                parts = sorted(G.parts(rest), key=lambda g: (-g.area, g.bounds))
                warn.append(f"{bj.id} overlaps {bi.id}: it gives way "
                            f"({bi.footprint.intersection(bj.footprint).area:.1f} m2)")
                bj.footprint = parts[0] if parts else bj.footprint
    for cat in ("water", "park", "plaza", "pier"):
        for item in layers.get(cat, []):
            for k, (p, _) in enumerate(subpaths(item["d"])):
                if len(p) >= 3:
                    pg = lpoly(p)
                    if pg.area >= 1.0:
                        aid = item["id"] if k == 0 else f"{item['id']}_{k}"
                        pin.areas.append(PinArea(aid, cat, G.qpoly(pg)))
    return pin


@functools.lru_cache(maxsize=8)
def load_cached(source: str) -> Pinned:
    """`load` relative to the repository, once per process (treat the result as read-only)."""
    return load(source, ROOT)


def placed_islands(spec, h) -> dict[str, tuple[Pinned, str | None]]:
    """Per pinned island name: the traced district placed where the island went, and the name
    of the district on it (None when no district names the island)."""
    out = {}
    recs = {i.name: i for i in h.islands}
    for isl in spec.water.islands:
        rec = recs.get(isl.name)
        if isl.pinned is None or rec is None or rec.pin_at is None:
            continue
        dist = next((d.name for d in spec.districts if d.placement.on_island == isl.name),
                    None)
        out[isl.name] = (load_cached(isl.pinned.source).placed(rec.pin_at,
                                                               isl.pinned.rotation_deg), dist)
    return out
