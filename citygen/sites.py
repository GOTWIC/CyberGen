"""Megasite generators (scope 5.7): fill the M1b reserves.

Each reserve gets a local frame along its long side (centered on it) and a generator by kind:

| Site | Contents |
|---|---|
| spaceport | launch pads with launch towers toward the flight cone, hangars, terminal, control tower, cargo yard, fuel tank farm, apron; everything under the height limit |
| transit_nexus | multi-level station hall, platform decks per mode (elevated rail and monorail beside the hall, maglev on it, sky tube on a station tower), metro entrances, bus bays under canopies, drop-off loop, plaza |
| freight_terminal | berths on the quay side, ship-to-shore gantry cranes, container stacks, rail yard, truck gates, admin building, warehouses |
| stadium | bowl of two stands with a roof ring, pitch, plaza, parking structures |
| central_park, grand_plaza | lawns, pond, radial and ring walkways, central plaza and fountain, pavilions; a grand plaza is paved with a monument and kiosks |
| arcology | stepped ziggurat with an atrium |
| temple_complex | perimeter wall with a gate, main hall with tiered roofs, side halls, pagoda, courtyard |
| attraction | ferris wheel on a platform, plaza, kiosks |
| skyport | raised deck with VTOL pads and a terminal |

Site paths (park walkways) and the entrances of site buildings join the walkway graph in the
driver. Transit platforms are placeholders until M5 routes the lines.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from . import buildings as BL
from . import complexes as CX
from . import dmath as M
from . import geom as G
from . import massing as MS
from . import presets

q = G.q
MARGIN_M = 4.0


class Lay:
    """Reserve layout frame: u along the long side, origin at the middle, half sizes a, b."""

    def __init__(self, poly, turn: float = 0.0, base_angle: float | None = None):
        self.poly = poly
        ang = MS.edge_angle(list(poly.exterior.coords)) if base_angle is None else base_angle
        ang += turn
        c = G.centroid(poly)
        fr = MS.Frame(c[0], c[1], ang)
        u0, v0, u1, v1 = fr.bounds(poly)
        self.fr = fr.moved((u0 + u1) / 2.0, (v0 + v1) / 2.0)
        self.a = (u1 - u0) / 2.0 - MARGIN_M
        self.b = (v1 - v0) / 2.0 - MARGIN_M
        self.inner = MS.prep(MS.inset(poly, MARGIN_M))
        self.base = ang - turn

    def rect(self, u0, v0, u1, v1):
        return self.fr.rect(min(u0, u1), min(v0, v1), max(u0, u1), max(v0, v1))

    def fits(self, p) -> bool:
        return p is not None and not p.is_empty and p.is_valid and self.inner.covers(p)

    def turned(self, turn: float) -> Lay:
        return Lay(self.poly, turn, self.base)

    def toward(self, p) -> Lay:
        """The layout turned so that +u points toward world point p."""
        u, v = self.fr.local(*p)
        if abs(v) > abs(u):
            return self.turned(M.HALF_PI if v > 0 else -M.HALF_PI)
        return self.turned(M.PI) if u < 0 else self


class Site:
    """Collects one site's buildings, elements, structures, walkway edges and links."""

    def __init__(self, rec, cx, gate):
        self.rec = rec
        self.cx = cx
        self.gate = gate
        self.buildings: list = []
        self.elements: list = []
        self.structures: list = []
        self.walks: list = []   # (kind, pts, width)
        self.links: list = []   # points to join to the ground walkways
        self.placed: list = []  # (poly, z0, z1) for overlap avoidance
        self.notes: list = []

    def free(self, poly, z0: float = 0.0, z1: float = 1e9) -> bool:
        for p, a, b in self.placed:
            if a < z1 and b > z0 and poly.intersects(p) and G.area1(G.inter(poly, p)) > 0.01:
                return False
        return True

    def building(self, kind: str, use: str, fh: float, fr, masses, name=None, attrs=None,
                 roof_items=(), lay: Lay | None = None) -> dict | None:
        b = BL.Bld(kind, use, fh, fr)
        for m in masses:
            b.add(*m)
        if not b.masses:
            return None
        if lay is not None and not all(lay.fits(m[0]) for m in b.masses):
            return None
        if not all(self.free(m[0], m[1], m[2]) for m in b.masses):
            return None
        foot = b.ground()
        k = len(self.buildings) + 1
        bid = f"{self.rec.id}.bld{k:02d}"
        ent = G.nearest(foot.exterior, Point(self.gate)) if not foot.is_empty else \
            G.centroid(b.masses[0][0])
        H = b.height
        body = max((z1 for _, _, z1, role, _ in b.masses if role not in ("spire", "antenna")),
                   default=H)
        rec = {"id": bid, "kind": kind, "use": use, "fh": fh,
               "floors": max(1, int(body / fh + 0.5)), "height": q(H), "masses": b.masses,
               "footprint": foot, "entrances": [{"position": ent, "kind": "main",
                                                 "segment_id": None}],
               "units": [], "roof_items": list(roof_items), "greens": [],
               "style": BL.style(self.cx, self.cx.rng(90, k)) if self.cx else {},
               "attrs": dict(attrs or {}), "name": name, "landmark": False,
               "lot_id": None, "lot_ids": [], "property_id": f"{self.rec.id}.prop",
               "megasite_id": self.rec.id, "district_id": self.rec.district_id}
        self.buildings.append(rec)
        for m in b.masses:
            self.placed.append((m[0], m[1], m[2]))
        return rec

    def element(self, kind: str, footprint=None, masses=(), line=None, z: float = 0.0,
                attrs=None, lay: Lay | None = None, check: bool = True) -> dict | None:
        if footprint is not None and lay is not None and not lay.fits(footprint):
            return None
        ms = [(p, q(z0), q(z1), role, shape) for p, z0, z1, role, shape in masses]
        if check and not all(self.free(m[0], m[1], m[2]) for m in ms):
            return None
        k = len(self.elements) + 1
        rec = {"id": f"{self.rec.id}.el{k:03d}", "kind": kind, "megasite_id": self.rec.id,
               "footprint": footprint, "masses": ms, "line": line or [], "z_m": q(z),
               "attrs": dict(attrs or {})}
        self.elements.append(rec)
        for m in ms:
            self.placed.append((m[0], m[1], m[2]))
        return rec

    def canopy(self, poly, z1: float, attrs=None) -> None:
        k = len(self.structures) + 1
        self.structures.append({"id": f"{self.rec.id}.st{k:02d}", "kind": "canopy",
                                "footprint": poly, "line": [], "z0_m": q(z1 - 0.5),
                                "z1_m": q(z1), "attrs": dict(attrs or {})})


def _limit(site) -> float:
    return float(site.rec.height_limit_m) if site.rec.height_limit_m else math.inf


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def spaceport(site: Site, lay: Lay) -> None:
    cone = site.rec_cone
    if cone is not None:
        c = G.centroid(G.diff(cone, site.poly)) if not G.diff(cone, site.poly).is_empty \
            else G.centroid(cone)
        lay = lay.toward(c)
    a, b = lay.a, lay.b
    lim = min(_limit(site), 60.0)
    zone = 2 * a * 0.42
    n = max(1, min(4, int(2 * b / 120.0)))
    r = min(42.0, zone * 0.38, (2 * b / n) * 0.36)
    up = a - zone / 2.0
    site.element("apron", footprint=lay.rect(a - zone, -b, a, b), lay=lay,
                 attrs={"surface": "concrete"})
    for i in range(n):
        vp = -b + (2 * b) * (i + 0.5) / n
        x, y = lay.fr.world(up, vp)
        pad = MS.circle(x, y, r)
        if not lay.fits(pad):
            continue
        site.element("launch_pad", footprint=pad, masses=[(pad, 0.0, 1.2, "pad", "cylinder")],
                     attrs={"radius_m": q(r)})
        tw = lay.rect(up - r - 14.0, vp - 4.0, up - r - 6.0, vp + 4.0)
        if lay.fits(tw):
            site.element("launch_tower", footprint=tw,
                         masses=[(tw, 0.0, q(min(lim - 2.0, 55.0)), "tower", "prism")])
    # hangars
    h0, h1 = a - zone - 10.0, a - zone - 10.0 - 2 * a * 0.2
    nh = max(1, min(3, int(2 * b / 110.0)))
    for i in range(nh):
        v0 = -b + (2 * b) * i / nh + 5.0
        v1 = -b + (2 * b) * (i + 1) / nh - 5.0
        p = lay.rect(h1, v0, h0, v1)
        site.building("hangar", "transport", q(min(lim - 4.0, 30.0)), lay.fr,
                      [(p, 0.0, q(min(lim - 4.0, 30.0)), "body", "prism")], lay=lay,
                      attrs={"doors": 1})
    # terminal and control tower
    t1 = h1 - 12.0
    t0 = t1 - 2 * a * 0.16
    term = lay.rect(t0, -b * 0.75, t1, b * 0.55)
    site.building("terminal", "transport", 6.0, lay.fr,
                  [(term, 0.0, 18.0, "body", "prism")], name=f"{site.rec.name} Terminal",
                  lay=lay, roof_items=[])
    ct = lay.rect(t0, b * 0.65, t0 + 12.0, b * 0.65 + 12.0)
    cab = lay.rect(t0 - 2.0, b * 0.65 - 2.0, t0 + 14.0, b * 0.65 + 14.0)
    ztop = q(min(lim - 1.0, 55.0))
    site.building("control_tower", "transport", 4.0, lay.fr,
                  [(ct, 0.0, q(ztop - 7.0), "shaft", "prism"),
                   (cab, q(ztop - 7.0), ztop, "cab", "prism")], lay=lay)
    # cargo yard and fuel farm at the far end
    y1 = t0 - 14.0
    y0 = -a
    u = y0 + 2.0
    k = 0
    while u + 12.2 <= y1 and k < 60:
        v = -b + 2.0
        while v + 7.5 <= b * 0.2 and k < 60:
            p = lay.rect(u, v, u + 12.2, v + 7.5)
            if lay.fits(p):
                k += 1
                h = 2.6 * (1 + (k * 7) % 4)
                site.element("container_stack", footprint=p,
                             masses=[(p, 0.0, q(h), "stack", "prism")])
            v += 7.5 + 5.0
        u += 12.2 + 4.0
    for i in range(6):
        x, y = lay.fr.world(y0 + 14.0 + (i % 3) * 22.0, b - 14.0 - (i // 3) * 22.0)
        tank = MS.circle(x, y, 8.5)
        if lay.fits(tank):
            site.element("fuel_tank", footprint=tank,
                         masses=[(tank, 0.0, 16.0, "tank", "cylinder")])


def _hub_modes(spec, rec) -> list[str]:
    names = {rec.name}
    d = next((x for x in spec.districts if x.name == site_district_name(spec, rec)), None)
    if d is not None:
        names.add(d.name)
    hubs = set(spec.transit.hubs or [])
    modes = []
    for ln in spec.transit.lines:
        if names & set(ln.route) or (hubs & set(ln.route) and names & hubs):
            if ln.mode not in modes:
                modes.append(ln.mode)
    if not modes:
        modes = list(presets.MEGASITES["transit_nexus"].needs_transit)
    return sorted(modes)


def site_district_name(spec, rec) -> str | None:
    k = int(rec.district_id[1:]) - 1
    return spec.districts[k].name if 0 <= k < len(spec.districts) else None


def _alt(spec, mode: str, names) -> tuple[float, float]:
    for ln in spec.transit.lines:
        if ln.mode == mode and ln.altitude_m and names & set(ln.route):
            return ln.altitude_m
    return presets.TRANSIT_MODES[mode].default_altitude_m


def transit_nexus(site: Site, lay: Lay) -> None:
    spec = site.spec
    a, b = lay.a, lay.b
    modes = _hub_modes(spec, site.rec)
    names = {site.rec.name, site_district_name(spec, site.rec)}
    hall = lay.rect(-a * 0.55, -b * 0.35, a * 0.55, b * 0.35)
    hall_rec = site.building("station", "station", 6.0, lay.fr,
                             [(hall, 0.0, 24.0, "hall", "prism")], name=site.rec.name,
                             lay=lay, attrs={"modes": modes})
    if hall_rec is None:
        hall = lay.rect(-a * 0.45, -b * 0.3, a * 0.45, b * 0.3)
        site.building("station", "station", 6.0, lay.fr, [(hall, 0.0, 24.0, "hall", "prism")],
                      name=site.rec.name, lay=lay, attrs={"modes": modes})
    side = 1.0
    for mode in modes:
        lo, hi = _alt(spec, mode, names)
        if mode == "metro":
            for su in (-1.0, 1.0):
                p = lay.rect(su * a * 0.75 - 4.0, -b * 0.62, su * a * 0.75 + 4.0, -b * 0.62 + 5.0)
                site.element("metro_entrance", footprint=p, masses=[(p, 0.0, 3.5, "kiosk",
                                                                    "prism")],
                             attrs={"mode": "metro", "track_z_m": q(lo)}, lay=lay)
        elif mode in ("elevated_rail", "monorail"):
            z = q(max(lo, 10.0))
            p = lay.rect(-a * 0.9, side * b * 0.42, a * 0.9, side * (b * 0.42 + 12.0))
            site.element("platform", footprint=p, masses=[(p, z, q(z + 1.5), "deck", "prism")],
                         attrs={"mode": mode}, lay=lay)
            side = -side
        elif mode == "maglev":
            z = q(max(lo, 28.0))
            p = lay.rect(-a * 0.6, -6.0, a * 0.6, 6.0)
            site.element("platform", footprint=p, masses=[(p, z, q(z + 1.5), "deck", "prism")],
                         attrs={"mode": mode})
        elif mode == "sky_tube":
            z = q(max(lo, 70.0))
            tw = lay.rect(a * 0.62, -12.0, a * 0.62 + 24.0, 12.0)
            rec = site.building("station_tower", "station", 6.0, lay.fr,
                                [(tw, 0.0, q(z + 12.0), "tower", "prism")],
                                name=f"{site.rec.name} Sky Station", lay=lay,
                                attrs={"mode": mode, "sky_platform_z_m": z})
            if rec is None:
                tw = lay.rect(-a * 0.62 - 24.0, -12.0, -a * 0.62, 12.0)
                rec = site.building("station_tower", "station", 6.0, lay.fr,
                                    [(tw, 0.0, q(z + 12.0), "tower", "prism")],
                                    name=f"{site.rec.name} Sky Station", lay=lay,
                                    attrs={"mode": mode, "sky_platform_z_m": z})
            if rec is not None:
                u0, v0, u1, v1 = lay.fr.bounds(tw)
                p = lay.rect(u0, v1, u1, v1 + 8.0)
                site.element("platform", footprint=p, masses=[(p, z, q(z + 1.5), "deck",
                                                               "prism")],
                             attrs={"mode": mode})
    # bus bays along the -v side, under a canopy
    nb = max(2, min(10, int(2 * a * 0.8 / 18.0)))
    v1 = -b * 0.58
    for i in range(nb):
        u = -a * 0.8 + (2 * a * 0.8) * (i + 0.5) / nb
        p = lay.rect(u - 7.0, v1 - 4.0, u + 7.0, v1)
        if lay.fits(p):
            site.element("bus_bay", footprint=p, attrs={"bay": i + 1})
    cp = lay.rect(-a * 0.8, v1 - 4.0, a * 0.8, v1 + 1.0)
    if lay.fits(cp):
        site.canopy(cp, 5.0, {"over": "bus_bays"})
    loop = G.diff(lay.rect(-a * 0.95, b * 0.55, a * 0.95, b * 0.92),
                  lay.rect(-a * 0.7, b * 0.65, a * 0.7, b * 0.82))
    ps = G.parts(G.inter(loop, lay.inner))
    if ps:
        site.element("drop_off", footprint=ps[0], attrs={"one_way": True})
    taken = G.union([r["footprint"] for r in site.buildings])
    for su in (-1.0, 1.0):
        p = lay.rect(su * a * 0.58, -b * 0.3, su * a * 0.95, b * 0.3)
        ps = G.parts(G.diff(G.inter(p, lay.inner), taken))
        if ps and G.area1(ps[0]) > 100.0:
            site.element("plaza", footprint=ps[0])


def _quay_lay(site: Site, lay: Lay) -> Lay:
    """Turned so that +v faces the nearest water (the quay side)."""
    water = site.water
    if water is None or water.is_empty:
        return lay
    best = None
    for turn in (0.0, M.HALF_PI, M.PI, -M.HALF_PI):
        L = lay.turned(turn)
        p = Point(L.fr.world(0.0, L.b + MARGIN_M))
        d = G.dist(water, p)
        if best is None or d < best[0]:
            best = (d, turn)
    return lay.turned(best[1]) if best[1] else lay


def freight_terminal(site: Site, lay: Lay) -> None:
    lay = _quay_lay(site, lay)
    a, b = lay.a, lay.b
    quay = 24.0
    nb = max(1, min(4, int(2 * a / 300.0)))
    for i in range(nb):
        u0 = -a + 2 * a * i / nb + 4.0
        u1 = -a + 2 * a * (i + 1) / nb - 4.0
        p = lay.rect(u0, b - quay, u1, b)
        ps = G.parts(G.inter(p, lay.inner))
        if not ps:
            continue
        site.element("berth", footprint=ps[0], line=[lay.fr.world(u0, b), lay.fr.world(u1, b)],
                     attrs={"berth": i + 1, "depth_m": 14.0})
        nc = max(2, min(4, int((u1 - u0) / 90.0)))
        for j in range(nc):
            cu = u0 + (u1 - u0) * (j + 0.5) / nc
            legs = [lay.rect(cu - 9.0, b - quay + 2.0 + k * 16.0, cu - 7.0, b - quay + 4.0 + k * 16.0)
                    for k in range(2)]
            legs += [lay.rect(cu + 7.0, b - quay + 2.0 + k * 16.0, cu + 9.0, b - quay + 4.0 + k * 16.0)
                     for k in range(2)]
            boom = lay.rect(cu - 9.0, b - quay - 30.0, cu + 9.0, b - 0.5)
            ms = [(p_, 0.0, 42.0, "leg", "prism") for p_ in legs]
            ms.append((boom, 42.0, 48.0, "boom", "prism"))
            if all(lay.fits(p_) for p_, *_ in ms):
                site.element("gantry_crane", footprint=lay.rect(cu - 9.0, b - quay + 2.0, cu + 9.0,
                                                                b - quay + 20.0),
                             masses=ms, attrs={"type": "ship_to_shore"})
    # container stacks behind the berths
    v_top = b - quay - 34.0
    v_bot = -b + 70.0
    u = -a + 4.0
    k = 0
    while u + 40.0 <= a - 4.0:
        v = v_top
        while v - 12.0 >= v_bot:
            p = lay.rect(u, v - 12.0, u + 40.0, v)
            if lay.fits(p):
                k += 1
                h = 2.6 * (2 + (k * 5) % 4)
                site.element("container_stack", footprint=p,
                             masses=[(p, 0.0, q(h), "stack", "prism")])
            v -= 12.0 + 6.0
        u += 40.0 + 8.0
    # rail yard and truck gates on the land side; a reserve whose land side is cut back
    # gets a shorter yard where it fits
    for f0, f1 in ((-0.9, 0.5), (-0.7, 0.7), (-0.75, 0.25), (-0.25, 0.75), (-0.5, 0.5),
                   (-0.35, 0.35)):
        laid = 0
        for t in range(4):
            v = -b + 10.0 + t * 6.0
            line = [lay.fr.world(a * f0, v), lay.fr.world(a * f1, v)]
            fp = lay.rect(a * f0, v - 1.0, a * f1, v + 1.0)
            if lay.fits(fp):
                site.element("rail_track", footprint=fp, line=line, attrs={"gauge_m": 1.435})
                laid += 1
        if laid:
            break
    # truck gate with its gate house, then the office, where they fit along the land side
    for f in (0.58, 0.4, 0.2, 0.0, -0.2, -0.4, -0.6, 0.7):
        g0 = a * f
        gate = lay.rect(g0, -b, g0 + 30.0, -b + 22.0)
        gh = lay.rect(g0 + 34.0, -b + 2.0, g0 + 44.0, -b + 10.0)
        if lay.fits(gate) and site.free(gate) and lay.fits(gh) and site.free(gh):
            site.element("truck_gate", footprint=gate, attrs={"lanes": 4})
            site.canopy(gate, 6.5, {"over": "truck_gate"})
            site.building("gate_house", "industrial", 3.5, lay.fr,
                          [(gh, 0.0, 3.5, "body", "prism")], lay=lay)
            break
    for f in (0.62, 0.3, 0.0, -0.3, -0.62):
        adm = lay.rect(a * f, -b + 30.0, a * f + min(40.0, a * 0.38), -b + 50.0)
        if site.building("office", "office", 4.0, lay.fr, [(adm, 0.0, 16.0, "body", "prism")],
                         name=f"{site.rec.name} Office", lay=lay) is not None:
            break
    for i in range(2):
        w = lay.rect(-a * 0.9 + i * 120.0, -b + 36.0, -a * 0.9 + i * 120.0 + 100.0, -b + 64.0)
        site.building("warehouse", "industrial", 14.0, lay.fr,
                      [(w, 0.0, 14.0, "body", "prism")], lay=lay)


def stadium(site: Site, lay: Lay) -> None:
    a, b = lay.a, lay.b
    A = min(a, b * 1.35) * 0.82
    B = b * 0.82
    fr = lay.fr
    pitch = MS.ellipse(fr, A * 0.56, B * 0.52)
    lower = MS.ellipse_ring(fr, A * 0.8, B * 0.78, A * 0.6, B * 0.57)
    upper = MS.ellipse_ring(fr, A, B, A * 0.8, B * 0.78)
    roof = MS.ellipse_ring(fr, A, B, A * 0.7, B * 0.68)
    site.building("stadium", "entertainment", 4.0, fr,
                  [(lower, 0.0, 14.0, "stand", "prism"), (upper, 0.0, 30.0, "stand", "prism"),
                   (roof, 30.0, 36.0, "roof", "prism")], name=site.rec.name, lay=lay)
    site.element("pitch", footprint=pitch, attrs={"surface": "turf"})
    plaza = G.diff(lay.inner, MS.ellipse(fr, A + 1.0, B + 1.0))
    ps = G.parts(plaza)
    if ps:
        site.element("plaza", footprint=ps[0], check=False)
    for su in (-1.0, 1.0):
        u0 = su * (A + 8.0)
        u1 = su * a
        if abs(u1 - u0) >= 30.0:
            p = lay.rect(u0, -b * 0.6, u1, b * 0.6)
            site.building("parking_structure", "parking", 3.0, fr,
                          [(p, 0.0, 15.0, "parking_deck", "prism")], lay=lay)


def _ring_pts(fr, ra: float, rb: float, t0: float, t1: float, n: int = 6) -> list:
    return [fr.world(ra * float(M.cos(t0 + (t1 - t0) * k / n)),
                     rb * float(M.sin(t0 + (t1 - t0) * k / n))) for k in range(n + 1)]


def _park_paths(site: Site, lay: Lay, n: int, ring_r: float) -> None:
    """A central plaza, a ring path and n radial paths to the reserve edge; arcs and spokes
    meet at their end points (the walkway graph joins edges there)."""
    a, b = lay.a, lay.b
    fr = lay.fr
    cr = min(22.0, 0.25 * min(a, b))
    ts = [2.0 * M.PI * k / n for k in range(n + 1)]
    for k in range(n):
        site.walks.append(("path", _ring_pts(fr, a * ring_r, b * ring_r, ts[k], ts[k + 1]),
                           4.0))
        site.walks.append(("path", _ring_pts(fr, cr, cr, ts[k], ts[k + 1], 3), 4.0))
    for k in range(n):
        t = ts[k]
        c, s_ = float(M.cos(t)), float(M.sin(t))
        inner = fr.world(cr * c, cr * s_)
        mid = fr.world(a * ring_r * c, b * ring_r * s_)
        far = fr.world((a + MARGIN_M + 40.0) * c, (b + MARGIN_M + 40.0) * s_)
        hit = LineString([mid, far]).intersection(site.poly.exterior)
        pts = [G.qpoint(x) for x in shapely.get_parts(hit) if x.geom_type == "Point"]
        site.walks.append(("path", [inner, mid], 5.0))
        if not pts:
            continue
        edge = min(pts, key=lambda p_: (round(ST_dist(p_, mid), 6), p_))
        site.walks.append(("path", [mid, edge], 5.0))
        site.links.append(edge)
    site.element("plaza", footprint=MS.circle(fr.ox, fr.oy, cr), check=False)


def ST_dist(a, b) -> float:
    dx, dy = a[0] - b[0], a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def _paths_area(site: Site):
    return G.union([G.qpoly(LineString(w[1]).buffer(w[2] / 2.0, cap_style="flat",
                                                    join_style="mitre"))
                    for w in site.walks if len(w[1]) >= 2])


def central_park(site: Site, lay: Lay) -> None:
    a, b = lay.a, lay.b
    fr = lay.fr
    _park_paths(site, lay, 6, 0.62)
    t = M.PI / 6.0
    pf = fr.moved(a * 0.38 * float(M.cos(t)), b * 0.38 * float(M.sin(t)))
    pond = MS.ellipse(pf, a * 0.12, b * 0.12)
    if lay.fits(pond):
        site.element("pond", footprint=pond, attrs={"water": True})
    fountain = MS.circle(fr.ox, fr.oy, 4.0)
    site.element("fountain", footprint=fountain, masses=[(fountain, 0.0, 1.2, "basin",
                                                          "cylinder")])
    for su in (-1.0, 1.0):
        pv = fr.moved(su * a * 0.8, su * b * 0.35)
        site.building("pavilion", "civic", 6.0, pv, [(pv.rect(-6.0, -6.0, 6.0, 6.0), 0.0, 6.0,
                                                      "body", "prism")], lay=lay)
    taken = G.union([_paths_area(site)] + [e["footprint"] for e in site.elements
                                           if e["footprint"] is not None] +
                    [r["footprint"] for r in site.buildings])
    lawn = G.diff(lay.inner, taken)
    for p in G.parts(lawn)[:16]:
        if G.area1(p) >= 100.0:
            site.element("lawn", footprint=p, check=False)


def grand_plaza(site: Site, lay: Lay) -> None:
    fr = lay.fr
    _park_paths(site, lay, 8, 0.7)
    site.element("plaza", footprint=G.parts(lay.inner)[0], check=False,
                 attrs={"surface": "paving"})
    fountain = MS.circle(fr.ox + 0.0, fr.oy, 6.0)
    site.element("fountain", footprint=fountain, masses=[(fountain, 0.0, 1.5, "basin",
                                                          "cylinder")])
    mf = fr.moved(lay.a * 0.45, 0.0)
    site.building("monument", "civic", 4.0, mf,
                  [(mf.rect(-6.0, -6.0, 6.0, 6.0), 0.0, 3.0, "plinth", "prism"),
                   (mf.rect(-2.0, -2.0, 2.0, 2.0), 3.0, 30.0, "obelisk", "prism")], lay=lay)
    for su in (-1.0, 1.0):
        kf = fr.moved(-lay.a * 0.5, su * lay.b * 0.5)
        site.building("kiosk", "retail", 3.5, kf, [(kf.rect(-3.0, -2.0, 3.0, 2.0), 0.0, 3.5,
                                                    "body", "prism")], lay=lay)


def arcology(site: Site, lay: Lay) -> None:
    H = float(site.height or presets.LANDMARK_HEIGHTS_M["arcology"])
    b = BL.Bld("arcology", "mixed", 4.0, lay.fr)
    region = MS.prep(MS.inset(site.poly, MARGIN_M))
    if CX.arcology(site.cx, b, region, H, None):
        site.building("arcology", "mixed", 4.0, lay.fr, b.masses, name=site.rec.name, lay=lay)


def temple_complex(site: Site, lay: Lay) -> None:
    a, b = lay.a, lay.b
    fr = lay.fr
    outer = MS.inset(site.poly, MARGIN_M)
    inner = MS.inset(outer, 1.2)
    gate = lay.rect(-10.0, -b - MARGIN_M - 10.0, 10.0, -b + 12.0)
    wall = G.diff(G.diff(outer, inner), gate) if not inner.is_empty else Polygon()
    for p in G.parts(wall):
        site.element("wall", footprint=p, masses=[(p, 0.0, 4.0, "wall", "prism")], check=False)
    gp = lay.rect(-9.0, -b - 1.0, 9.0, -b + 3.0)
    gp = G.parts(G.inter(gp, outer))
    if gp:
        site.element("gate", footprint=gp[0],
                     masses=[(p_, 0.0, 9.0, "post", "prism") for p_ in
                             (lay.rect(-9.0, -b - 1.0, -6.0, -b + 2.0),
                              lay.rect(6.0, -b - 1.0, 9.0, -b + 2.0))] +
                     [(lay.rect(-10.0, -b - 1.0, 10.0, -b + 2.0), 9.0, 11.0, "lintel",
                       "prism")], check=False)
    hall = [(lay.rect(-a * 0.32, -b * 0.1, a * 0.32, b * 0.42), 0.0, 1.5, "platform", "prism"),
            (lay.rect(-a * 0.28, -b * 0.05, a * 0.28, b * 0.37), 1.5, 11.0, "hall", "prism"),
            (lay.rect(-a * 0.22, 0.0, a * 0.22, b * 0.32), 11.0, 17.0, "roof_tier", "prism"),
            (lay.rect(-a * 0.14, b * 0.05, a * 0.14, b * 0.27), 17.0, 22.0, "roof_tier",
             "prism")]
    site.building("temple_hall", "religious", 4.0, fr, hall, name=site.rec.name, lay=lay)
    for su in (-1.0, 1.0):
        p = lay.rect(su * a * 0.62, -b * 0.55, su * a * 0.9, -b * 0.1)
        site.building("temple_hall", "religious", 4.0, fr,
                      [(p, 0.0, 9.0, "hall", "prism"),
                       (MS.inset(p, 1.5), 9.0, 12.0, "roof_tier", "prism")], lay=lay)
    px, py = fr.world(a * 0.72, b * 0.62)
    pf = MS.Frame(px, py, fr.angle)
    tiers = [(pf.rect(-6.0 * (1 - 0.13 * i), -6.0 * (1 - 0.13 * i), 6.0 * (1 - 0.13 * i),
                      6.0 * (1 - 0.13 * i)), 6.0 * i, 6.0 * (i + 1), "tier", "prism")
             for i in range(5)]
    site.building("pagoda", "religious", 6.0, fr, tiers, lay=lay)
    taken = G.union([r["footprint"] for r in site.buildings] +
                    [e["footprint"] for e in site.elements if e["footprint"] is not None])
    court = G.diff(inner, taken) if not inner.is_empty else Polygon()
    ps = G.parts(court)
    if ps:
        site.element("courtyard", footprint=ps[0], check=False)


def attraction(site: Site, lay: Lay) -> None:
    D = min(110.0, 2 * lay.a - 12.0)
    b = BL.Bld("ferris_wheel", "entertainment", 4.0, lay.fr)
    if D >= 40.0 and CX.ferris_wheel(site.cx, b, lay.inner, D + 4.0, None, D=D):
        site.building("ferris_wheel", "entertainment", 4.0, b.fr, b.masses, name=site.rec.name,
                      lay=lay)
    taken = G.union([r["footprint"] for r in site.buildings])
    plaza = G.diff(lay.inner, G.qpoly(taken.buffer(2.0, join_style="mitre"))) \
        if not taken.is_empty else lay.inner
    ps = G.parts(plaza)
    if ps:
        site.element("plaza", footprint=ps[0], check=False)
    for su in (-1.0, 1.0):
        kf = lay.fr.moved(su * lay.a * 0.6, -lay.b * 0.65)
        site.building("kiosk", "retail", 3.5, kf, [(kf.rect(-3.0, -2.0, 3.0, 2.0), 0.0, 3.5,
                                                    "body", "prism")], lay=lay)


def skyport(site: Site, lay: Lay) -> None:
    a, b = lay.a, lay.b
    deck = lay.rect(-a, -b * 0.9, a, b * 0.9)
    if not lay.fits(deck):
        deck = lay.rect(-a * 0.85, -b * 0.75, a * 0.85, b * 0.75)
    term = lay.rect(-a * 0.95, -b * 0.4, -a * 0.35, b * 0.4)
    pads = []
    u0, v0, u1, v1 = lay.fr.bounds(deck)
    for i in range(2):
        for j in range(2):
            cu = -a * 0.15 + i * (a * 0.55)
            cv = -b * 0.4 + j * (b * 0.8)
            if lay.fits(lay.rect(cu - 8.0, cv - 8.0, cu + 8.0, cv + 8.0)):
                x, y = lay.fr.world(cu, cv)
                pads.append({"kind": "av_pad", "position": (x, y, 32.0),
                             "size": (16.0, 16.0, 0.5), "yaw_deg": lay.fr.yaw_deg()})
    site.building("skyport", "transport", 4.0, lay.fr,
                  [(deck, 0.0, 32.0, "deck", "prism"), (term, 32.0, 42.0, "terminal", "prism")],
                  name=site.rec.name, lay=lay, roof_items=pads)


GENERATORS = {"spaceport": spaceport, "transit_nexus": transit_nexus,
              "freight_terminal": freight_terminal, "stadium": stadium,
              "central_park": central_park, "grand_plaza": grand_plaza, "arcology": arcology,
              "temple_complex": temple_complex, "attraction": attraction, "skyport": skyport}

REQUIRED = {
    "spaceport": ("launch_pad", "launch_tower", "hangar", "terminal", "control_tower",
                  "fuel_tank", "container_stack"),
    "transit_nexus": ("station", "platform", "bus_bay"),
    "freight_terminal": ("berth", "gantry_crane", "container_stack", "rail_track",
                         "truck_gate"),
    "stadium": ("stadium", "pitch"),
    "central_park": ("lawn", "plaza"),
    "grand_plaza": ("plaza", "monument"),
    "arcology": ("arcology",),
    "temple_complex": ("wall", "gate", "temple_hall", "pagoda"),
    "attraction": ("ferris_wheel",),
    "skyport": ("skyport",),
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def build_sites(spec, m, out) -> list[dict]:
    """Fill every megasite reserve; appends to out (buildings, elements, structures) and
    returns the megasite rows with members."""
    seg_lines = [LineString(s.centerline) for s in m.road_segments
                 if s.road_class in ("avenue", "street", "service", "highway", "alley")]
    tree = shapely.STRtree(seg_lines) if seg_lines else None
    water_polys = [G.from_model_poly(p) for s in m.seas for p in s.polygons] + \
        [G.from_model_poly(r.polygon) for r in m.rivers] + \
        [G.from_model_poly(c.polygon) for c in m.channels] + \
        [G.from_model_poly(w.polygon) for w in m.waterways]
    wtree = shapely.STRtree(water_polys) if water_polys else None
    by_did = {d.id: d for d in m.districts}
    sd_by = {d.name: d for d in spec.districts}
    row_polys = list(G.snap_many(shapely.buffer(
        np.array([LineString(s.centerline) for s in m.road_segments], dtype=object),
        np.array([s.width_m / 2.0 for s in m.road_segments]), cap_style="flat",
        join_style="mitre"))) + G.from_model_polys([j.polygon for j in m.junctions])
    rtree = shapely.STRtree(row_polys) if row_polys else None
    rows = []
    for rec in m.megasites:
        poly = G.from_model_poly(rec.polygon)
        d = by_did[rec.district_id]
        sd = sd_by[d.name]
        cx = BL.Ctx(did=d.id, name=d.name, archetype=d.archetype, seed=int(d.seed) + 7919,
                    height=tuple(sd.height_m), grime=float(sd.grime), neon=float(sd.neon),
                    greenery=float(sd.greenery), skybridge_density=0.0, polygon=poly,
                    focus=G.centroid(poly), radius=1.0, lot_area=(1.0, 2.0))
        gate = G.centroid(poly)
        if tree is not None:
            hits = tree.query_nearest(poly, all_matches=True).tolist()
            k = min(hits, key=lambda h: (G.dist(seg_lines[h], poly), h))
            gate = G.nearest(poly.exterior, seg_lines[k].interpolate(
                seg_lines[k].project(Point(G.centroid(poly)))))
        site = Site(rec, cx, gate)
        site.poly = poly
        if rtree is not None:
            for k in sorted(int(i) for i in rtree.query(poly, predicate="intersects")):
                site.placed.append((row_polys[k], -1.0, 1e9))
        site.spec = spec
        site.rec_cone = G.from_model_poly(rec.flight_cone) if rec.flight_cone else None
        near = [water_polys[int(i)] for i in sorted(wtree.query(poly.buffer(120.0),
                                                                 predicate="intersects"))] \
            if wtree is not None else []
        site.water = G.union(near) if near else None
        site.height = next((lm.height_m for lm in sd.landmarks if lm.kind == rec.kind), None)
        gen = GENERATORS.get(rec.kind)
        if gen is not None:
            gen(site, Lay(poly))
        if site.buildings:
            out.properties.append({"id": f"{rec.id}.prop", "complex": "megasite",
                                   "building_ids": [r["id"] for r in site.buildings],
                                   "lot_ids": [], "owner": f"{rec.kind}_authority",
                                   "name": rec.name, "district_id": rec.district_id})
        out.buildings += site.buildings
        out.site_elements += site.elements
        out.structures += site.structures
        out.site_walks += [(rec.id, w) for w in site.walks]
        out.site_links += [(rec.id, p) for p in site.links]
        counts: dict = {}
        for r in site.buildings:
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        for e in site.elements:
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        row = rec.model_dump(mode="python")
        row["member_ids"] = [r["id"] for r in site.buildings] + \
            [e["id"] for e in site.elements] + [s["id"] for s in site.structures]
        row["attrs"] = {**row["attrs"], "filled": bool(counts),
                        "contents": dict(sorted(counts.items())), "gate": list(gate)}
        out.notes += site.notes
        rows.append(row)
    return rows
