"""Connections (scope 5.1.3, AG4): skybridges by kind with their landing doors, sky tube
portals cut through towers with sky station platforms, podium and tower decks, atrium and
court interiors.

**Skybridges** (`skybridge`): every model skybridge is a piece of its own, keyed by its id,
in its own frame (x along its line, from facade to facade and 0.15 m into each, y to its
left, z from its base), by kind:

| kind | what |
|---|---|
| enclosed | a deck slab on a box girder, glazed walls between mullions, a roof slab, a lit soffit strip, collars at the facades |
| stack | the same with a floor and a spandrel band at every level |
| open_deck | a paved deck on its girder, glass balustrades with a top rail, planters (the podium decks between megablocks) |
| catwalk | a steel grating on two Warren trusses whose top chords are the handrails |
| cable | a light deck hung from two catenary cables, hangers every 1.5 m, handrails |

Its shell side (`landings`, in the shell's facade grammar): the floor a skybridge lands on
is a door row on its mass (as AG2's balcony rows: sill at 150 mm, the other bays' lower
panes behind spandrel panels), the landing an opening of the bridge's width with a frame
and two glazed leaves (`roofparts.gen_landing`); the window rows over it within the
bridge's height stay a solid panel (AG1's mounts); a mass too thin for windows still takes
the door, and a mechanical floor a bridge lands on keeps its windows. A landing that finds
no door row (its deck off the floor lines) hangs on the panel and is reported, as is one
that lands straight into an open portal (a sky station's own bridge).

**Portals** (`portals`): where a sky tube passes through a tower, every mass across the
portal's floors is split there and its portal storey cut by the tube's corridor (the
tube's line, 1 m clear round its 7 m section, and a sky station's platform footprint): the
corridor's walls are a metal lining (no windows, unless a station's glazing), the storey
over it a lined soffit, the one under it the portal floor; a frame with a light strip rings
each mouth (its jamb narrowed where the mouth is near the facade's corner). A sky station's
platforms flank the tube at the level of its floor. A tube that meets no mass at the
portal's height (between a megabuilding's towers) has nothing to cut.

**Decks** (masses of role `deck`, M3p's open decks between towers): paving on top, glass
balustrades on the edges that are not inside a tower, planters.

**Courts** (holes of a mass on the ground, `atrium` or `courtyard` edges): the court floor
paved, planters at its corners, galleries along its walls at every floor line of the
podium, a glass rail at their edge.
"""

from __future__ import annotations

import math

from ..triangulate import area2
from . import genome as GN
from . import meshbuf as MB
from . import parts as PT
from . import rings as RG
from . import roofs as RF
from .meshbuf import Buf
from .parts import box
from .roofparts import bar

BRIDGE_IN = 150              # a bridge reaches this far into each facade
DECK_T = 600                 # deck slab
GIRDER_T = 400               # box girder under it (the deck structure: 1.0 m in all)
COLLAR = 250
LANDING_TOL = 400            # a landing's deck within this of a floor line: a door row
LANDING_THIN = 1000          # a mass too thin for windows still takes a landing door
DOOR_MIN = 900               # a landing door at least this wide
LANDING_CORNER = 400         # and at least this far from a corner (a reveal and 6 cm)
FRAME_JAMB = 600             # a portal frame's jambs, beside its mouth
FRAME_DEPTH = 340            # and how far it stands out of the facade, with its light strip
PORTAL_CLEAR = 1000          # the corridor round a sky tube's section
PLATFORM_GAP = 2750          # a sky station's platform edge from the tube's axis
TUBE_FLOOR = 2520            # the tube's floor (AG7) under its axis
GALLERY = 1200               # a court gallery's depth
SLIVER = 1500                # a portal storey's piece thinner than this is left out


def _u(key: str, purpose: str) -> float:
    return GN.u(key, purpose, "ag4.connect")


# ---------------------------------------------------------------------------
# Skybridges (pieces of their own)
# ---------------------------------------------------------------------------

def _frame_of(s: dict):
    (ax, ay), (bx, by) = s["line"][0], s["line"][-1]
    cx, cy = round((ax + bx) / 2.0, 2) + 0.0, round((ay + by) / 2.0, 2) + 0.0
    L = math.hypot(bx - ax, by - ay)
    yaw = math.degrees(math.atan2(by - ay, bx - ax))
    return (cx, cy), int(round(L * 1000)), round(yaw, 2) + 0.0


def skybridge(s: dict) -> tuple[Buf, dict, dict]:
    """One skybridge (the model's record as a dict): its buffer, arrays and record (frame,
    kind, triangles)."""
    b = Buf()
    kind = s["kind"]
    _, L, _ = _frame_of(s)
    x0, x1 = -L // 2 - BRIDGE_IN, L // 2 + BRIDGE_IN
    w = int(round(s["width_m"] * 1000))
    hw = w // 2
    z = int(round(s["z_m"] * 1000))
    levels = max(int(s.get("levels") or 1), 1)
    lh = int(round(float(s.get("level_height_m") or 4.0) * 1000))
    if kind in ("enclosed", "stack"):
        h = levels * lh
        box(b, "bridge_deck", x0, x1, -hw, hw, z - DECK_T, z)
        box(b, "bridge_deck", x0 + 300, x1 - 300, -hw * 6 // 10, hw * 6 // 10,
            z - DECK_T - GIRDER_T, z - DECK_T)
        box(b, "bridge_floor", x0 + 100, x1 - 100, -hw + 150, hw - 150, z, z + 30)
        for k in range(levels):
            zl = z + k * lh
            top = zl + lh - (400 if k == levels - 1 else 300)
            for y0, y1 in ((-hw, -hw + 40), (hw - 40, hw)):
                box(b, "bridge_glass", x0 + 300, x1 - 300, y0, y1, zl + 30, top)
            n = max(2, (x1 - x0 - 600) // 1500)
            for j in range(n + 1):
                x = x0 + 300 + (x1 - x0 - 600) * j // n
                for y0, y1 in ((-hw - 80, -hw + 60), (hw - 60, hw + 80)):
                    box(b, "bridge_frame", x - 40, x + 40, y0, y1, zl + 30, top)
            if k < levels - 1:
                box(b, "bridge_deck", x0, x1, -hw, hw, top, zl + lh)
                for y0, y1 in ((-hw - 60, -hw), (hw, hw + 60)):
                    box(b, "bridge_frame", x0 + 300, x1 - 300, y0, y1, top, zl + lh)
        box(b, "bridge_roof", x0, x1, -hw - 200, hw + 200, z + h - 400, z + h)
        box(b, "lamp_white", x0 + 600, x1 - 600, -150, 150, z + h - 440, z + h - 400)
        for xa, xb in ((x0, x0 + 300), (x1 - 300, x1)):
            box(b, "bridge_frame", xa, xb, -hw - COLLAR, hw + COLLAR, z - DECK_T - COLLAR,
                z - DECK_T)
            box(b, "bridge_frame", xa, xb, -hw - COLLAR, hw + COLLAR, z + h, z + h + COLLAR)
            box(b, "bridge_frame", xa, xb, -hw - COLLAR, -hw, z - DECK_T, z + h)
            box(b, "bridge_frame", xa, xb, hw, hw + COLLAR, z - DECK_T, z + h)
    elif kind == "open_deck":
        box(b, "bridge_deck", x0, x1, -hw, hw, z - DECK_T, z - 60)
        box(b, "bridge_deck", x0 + 300, x1 - 300, -hw * 6 // 10, hw * 6 // 10,
            z - DECK_T - GIRDER_T, z - DECK_T)
        box(b, "bridge_floor", x0, x1, -hw, hw, z - 60, z)
        for y0, y1 in ((-hw + 60, -hw + 80), (hw - 80, hw - 60)):
            box(b, "bridge_glass", x0 + 200, x1 - 200, y0, y1, z, z + 1050)
        for y0, y1 in ((-hw + 40, -hw + 100), (hw - 100, hw - 40)):
            box(b, "bridge_rail", x0 + 150, x1 - 150, y0, y1, z + 1050, z + 1110)
            box(b, "bridge_rail", x0 + 150, x1 - 150, y0, y1, z, z + 60)
        if w >= 5000 and x1 - x0 >= 8000:
            n = max(1, (x1 - x0 - 4000) // 8000)
            for j in range(n):
                x = x0 + 2000 + (x1 - x0 - 4000) * (2 * j + 1) // (2 * n)
                box(b, "planter", x - 1200, x + 1200, hw - 1100, hw - 300, z, z + 550)
                box(b, "green_roof", x - 1100, x + 1100, hw - 1000, hw - 400, z + 550,
                    z + 600)
    elif kind == "catwalk":
        box(b, "bridge_steel", x0, x1, -hw, hw, z - 100, z)
        for y in (-hw + 50, hw - 50):
            zb, zt = z - 900, z + 1100
            bar(b, "bridge_steel", (x0, y, zb), (x1, y, zb), 120)
            bar(b, "bridge_steel", (x0, y, zt), (x1, y, zt), 80)
            n = max(2, (x1 - x0) // 1500)
            for j in range(n + 1):
                x = x0 + (x1 - x0) * j // n
                bar(b, "bridge_steel", (x, y, zb), (x, y, zt), 70)
                if j < n:
                    xa, xb = (x, x0 + (x1 - x0) * (j + 1) // n)
                    if j % 2:
                        xa, xb = xb, xa
                    bar(b, "bridge_steel", (xa, y, zb), (xb, y, zt), 50)
        for j in range(max(2, (x1 - x0) // 3000) + 1):
            x = x0 + 100 + (x1 - x0 - 200) * j // max(2, (x1 - x0) // 3000)
            box(b, "bridge_steel", x - 40, x + 40, -hw + 50, hw - 50, z - 900, z - 820)
    else:   # cable
        box(b, "bridge_steel", x0, x1, -hw, hw, z - 150, z)
        n = max(2, (x1 - x0) // 1500)
        sag = min(2500, max(800, (x1 - x0) // 10))
        top = z + 3200
        for y in (-hw - 60, hw + 60):
            pts = []
            for j in range(n + 1):
                x = x0 + (x1 - x0) * j // n
                t = (2.0 * j / n) - 1.0
                pts.append((x, y, int(round(top - sag * (1.0 - t * t)))))
            for p, q in zip(pts, pts[1:]):
                bar(b, "bridge_steel", p, q, 60)
            for p in pts[1:-1]:
                bar(b, "bridge_steel", (p[0], y, z), p, 25)
        for y in (-hw + 30, hw - 30):
            box(b, "bridge_rail", x0, x1, y - 20, y + 20, z + 1000, z + 1040)
            for j in range(n + 1):
                x = x0 + 50 + (x1 - x0 - 100) * j // n
                box(b, "bridge_rail", x - 20, x + 20, y - 20, y + 20, z, z + 1000)
    arrs = b.arrays()
    return b, arrs, {"kind": kind, "triangles": int(sum(len(a["tri"]) for a in arrs.values())),
                     "check": MB.check(arrs)}


# ---------------------------------------------------------------------------
# Landings (in the shell's facade grammar)
# ---------------------------------------------------------------------------

def landings_of(sb) -> dict[int, list[dict]]:
    """Per brief edge, the skybridge ends landing on it: s (mm along the edge), deck z,
    width, height, id."""
    out: dict[int, list] = {}
    for s in sb.br["skybridges"]:
        at = s.get("at")
        if at is None:
            continue
        h = int(max(s["levels"], 1) * s["level_height_m"] * 1000)
        out.setdefault(at["edge"], []).append({
            "id": s["id"], "s": int(round(at["s"] * 1000)), "z": int(round(s["z_m"] * 1000)),
            "w": int(round(s["width_m"] * 1000)), "h": h, "kind": s["kind"]})
    return out


def door_floors(sb, ms: dict) -> set[int]:
    """The floors of a mass a skybridge lands on (door rows)."""
    out = set()
    n = ms["floors"]
    if n <= 0:
        return out
    k = ms["k"]
    for j, lst in sb.landings.items():
        if sb.br["edges"][j]["mass"] != k:
            continue
        for ld in lst:
            for f in range(n):
                zf = ms["z0"] + (ms["z1"] - ms["z0"]) * f // n
                if abs(zf - ld["z"]) <= LANDING_TOL:
                    out.add(f)
    return out


def landing_ops(sb, fa, row: tuple, ops: list) -> list:
    """A row's openings with the skybridge landings on this facade cut in (a door of the
    bridge's width where its deck is the row's floor line; marked bay -2)."""
    if fa.j is None or fa.j not in sb.landings:
        return ops
    lo, hi, kind, f, full, zf = row
    for ld in sb.landings[fa.j]:
        if abs(zf - ld["z"]) > LANDING_TOL or hi - lo < 1900:
            continue
        s = ld["s"] - fa.soff
        # (the bridge's width less its collars; at least DOOR_MIN for a catwalk or a cable
        # bridge's narrow deck)
        hw = max(ld["w"] // 2 - 300, DOOR_MIN // 2)
        # (into a corner pier if the bridge lands there, LANDING_CORNER from the corner)
        a_ = max(s - hw, min(fa.c0, LANDING_CORNER))
        b_ = min(s + hw, fa.L - min(fa.c1, LANDING_CORNER))
        if b_ - a_ < DOOR_MIN - 100:
            continue
        ops = [op for op in ops if op[1] < a_ - 200 or op[0] > b_ + 200]
        ops.append((a_, b_, "storefront", -2))
        sb.landed[ld["id"]] = {"s": ld["s"], "z": zf, "w": b_ - a_, "h": hi - lo,
                               "door": True}
    return ops


def landing_door(sb, fa, a_: int, b_: int, lo: int, hi: int, reveal: int) -> None:
    sb.parts.on(fa, "landing", {"w": PT.q(b_ - a_), "h": PT.q(hi - lo), "r": max(reveal, 60)},
                (a_ + b_) // 2, lo)


def _into_portal(sb, s: dict) -> bool:
    """A skybridge whose end lands in a cut portal's storey, inside its corridor (it walks
    straight in: the sky station's own bridge)."""
    from shapely.geometry import Point
    for p, rec in zip(sb.br["portals"], sb.portal_recs):
        if not rec["cut"] or not rec.get("z"):
            continue
        z = s["z_m"] * 1000
        if not rec["z"][0] - LANDING_TOL <= z <= rec["z"][1]:
            continue
        cor = _corridor(p)
        if cor is not None and cor.buffer(1.5).covers(Point(s["end"][0], s["end"][1])):
            return True
    return False


def landing_records(sb) -> list[dict]:
    """Per skybridge of the brief: its landing door, else why none (`no_edge`: its end
    meets none of the building's walls; `portal`: it lands in an open portal; `off_floor`:
    its deck is on no floor line of the mass it meets, M3's floor grids apart; `no_room`:
    the wall leaves no door's width)."""
    out = []
    for s in sb.br["skybridges"]:
        rec = sb.landed.get(s["id"])
        r = {"id": s["id"], "door": bool(rec), "z_m": round(s["z_m"], 3)}
        if not rec:
            at = s.get("at")
            if at is None:
                r["why"] = "no_edge"
            elif _into_portal(sb, s):
                r["why"] = "portal"
            else:
                z = int(round(s["z_m"] * 1000))
                k = sb.br["edges"][at["edge"]]["mass"]
                on = False
                for ms in sb.masses:
                    if ms["k"] != k or ms["floors"] <= 0:
                        continue
                    n = ms["floors"]
                    on |= any(abs(ms["z0"] + (ms["z1"] - ms["z0"]) * f // n - z) <= LANDING_TOL
                              for f in range(n))
                r["why"] = "no_room" if on else "off_floor"
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Portals and sky stations
# ---------------------------------------------------------------------------

def _poly_m(rings_mm):
    from shapely.geometry import Polygon
    return Polygon([(p[0] / 1000.0, p[1] / 1000.0) for p in rings_mm[0]],
                   [[(p[0] / 1000.0, p[1] / 1000.0) for p in h] for h in rings_mm[1:]])


def _corridor(p: dict):
    """A portal's corridor in plan (meters, building frame): the tube's line buffered by
    half its section and the clearance, with a sky station's platform footprint."""
    from shapely.geometry import LineString, Polygon
    from citygen import geom as G
    lines = [[(q[0], q[1]) for q in ln] for ln in p["lines"] if len(ln) >= 2]
    if not lines:
        return None
    half = p["diameter_m"] / 2.0 + PORTAL_CLEAR / 1000.0
    with G.canonical():
        c = G.union([G.qpoly(LineString(ln).buffer(half, cap_style="flat", join_style="mitre",
                                                   mitre_limit=2.0)) for ln in lines])
        pf = p.get("platform")
        if pf:
            c = G.union([c, G.qpoly(Polygon(pf["exterior"], pf["holes"]).buffer(
                0.5, join_style="mitre", mitre_limit=2.0))])
    return c


def _thin(ring) -> float:
    """Twice the area over the perimeter: about the width of a long thin ring (mm)."""
    per = 0.0
    n = len(ring)
    for i in range(n):
        per += math.hypot(ring[(i + 1) % n][0] - ring[i][0], ring[(i + 1) % n][1] - ring[i][1])
    return abs(area2(ring)) / max(per, 1.0)


def _on_edge(p, q, ring) -> int:
    """The index of the ring edge segment p-q lies on (both ends within 8 mm: the cut is on
    the 1 cm grid), else -1."""
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 == 0:
            continue
        ok = True
        for r in (p, q):
            t = ((r[0] - a[0]) * dx + (r[1] - a[1]) * dy) / L2
            if t < -1e-6 or t > 1 + 1e-6:
                ok = False
                break
            ex, ey = a[0] + dx * t - r[0], a[1] + dy * t - r[1]
            if ex * ex + ey * ey > 64.0:
                ok = False
                break
        if ok:
            return i
    return -1


def portals(sb) -> None:
    """Cut every portal through the masses (before the roofs and the grammar): each mass
    across a portal's floors split at them, its portal storey's footprint less the
    corridor; the pieces keep their brief edges where they run on the old ones. A portal
    whose tube meets no mass at its height (between a megabuilding's towers, over its
    podium) has nothing to cut (`through` 0)."""
    br = sb.br
    sb.portal_recs = []
    if not br["portals"]:
        return
    from citygen import geom as G
    for p in br["portals"]:
        cor = _corridor(p)
        rec = {"line_id": p["line_id"], "station": bool(p.get("station")),
               "station_id": p.get("station_id"), "cut": False, "platform": False,
               "through": 0}
        sb.portal_recs.append(rec)
        if cor is None or cor.is_empty:
            continue
        pz0, pz1 = int(round(p["z"][0] * 1000)), int(round(p["z"][1] * 1000))
        out = []
        for ms in sb.masses:
            n = ms["floors"]
            if ms["shape"] != "prism" or ms["z1"] <= pz0 or ms["z0"] >= pz1 or n <= 0:
                out.append(ms)
                continue
            lines = [ms["z0"] + (ms["z1"] - ms["z0"]) * f // n for f in range(n + 1)]
            fa = max([f for f in range(n + 1) if lines[f] <= pz0] or [0])
            fb = min([f for f in range(n + 1) if lines[f] >= pz1] or [n])
            za, zb = lines[fa], lines[fb]
            with G.canonical():
                left = G.diff(_poly_m(ms["rings"]), cor)
            if abs(G.area1(left) - G.area1(_poly_m(ms["rings"]))) < 1.0:
                out.append(ms)
                continue
            rec["through"] += 1
            pieces = G.to_model_polys(left)
            below = dict(ms, z1=za, floors=fa, n0=ms.get("n0", n), portal_floor=True)
            above = dict(ms, z0=zb, floors=n - fb, f0=ms.get("f0", 0) + fb,
                         n0=ms.get("n0", n), portal_top=True)
            if fa > 0:
                out.append(below)
            for pc in pieces:
                rings = [RF._ccw(RG.mm_ring(pc["exterior"]))] + \
                    [RG.mm_ring(h) for h in pc["holes"]]
                if len(rings[0]) < 3 or not RG.is_simple(rings[0]) or \
                        abs(area2(rings[0])) < 2 * 4_000_000 or \
                        _thin(rings[0]) < SLIVER:
                    continue           # (a sliver left beside the corridor goes)
                # each edge keeps the brief edge it runs on (`ej`, as `ShellBuilder._j`
                # reads it: a piece's ring may run on the exterior and a court at once)
                eidx, deriv, ej = [], [], []
                for ring in rings:
                    ei, dv, jj = [], [], []
                    for i in range(len(ring)):
                        q0, q1 = ring[i], ring[(i + 1) % len(ring)]
                        hit = False
                        for r0, old in enumerate(ms["rings"]):
                            k = _on_edge(q0, q1, old)
                            if k >= 0:
                                ei.append(ms["eidx"][r0][k])
                                dv.append(ms["deriv"][r0][k])
                                jj.append(sb._j(ms, r0, k))
                                hit = True
                                break
                        if not hit:
                            ei.append(-1)
                            dv.append(True)
                            jj.append(None)
                    eidx.append(ei)
                    deriv.append(dv)
                    ej.append(jj)
                out.append(dict(ms, rings=rings, eidx=eidx, deriv=deriv, ej=ej,
                                rid=[0] * len(rings), z0=za,
                                z1=zb, floors=fb - fa, f0=ms.get("f0", 0) + fa,
                                n0=ms.get("n0", n), portal=True,
                                outline=ms.get("outline", ms["rings"][0]),
                                station=rec["station"]))
            if fb < n:
                out.append(above)
            rec["cut"] = True
            z_ = rec.get("z") or [za, zb]
            rec["z"] = [min(z_[0], za), max(z_[1], zb)]
        sb.masses = out
        sb.stats["portals"] = sb.stats.get("portals", 0) + int(rec["cut"])


def station(sb) -> None:
    """A sky station's platforms in its portal (both sides of the tube at its floor's
    level, a tactile strip along their edge)."""
    from shapely.geometry import LineString, Polygon
    from citygen import geom as G
    for p, rec in zip(sb.br["portals"], sb.portal_recs):
        if not p.get("station") or not p.get("platform") or not rec.get("cut"):
            continue
        lines = [[(q[0], q[1]) for q in ln] for ln in p["lines"] if len(ln) >= 2]
        if not lines:
            continue
        axis = int(round((p["lines"][0][0][2] - p["diameter_m"] / 2.0) * 1000))
        floor = axis - TUBE_FLOOR
        z0 = rec["z"][0]
        if floor - z0 < 300:
            continue
        pf = p["platform"]
        # (inside the tower: the outlines of the masses across the platform's floor)
        outl = [_poly_m([ms["outline"]]) for ms in sb.masses
                if ms.get("portal") and ms["z0"] <= floor < ms["z1"] + 50]
        with G.canonical():
            cor = _corridor(p)
            plat = G.inter(G.qpoly(Polygon(pf["exterior"], pf["holes"])), cor)
            if outl:
                plat = G.inter(plat, G.union([G.qpoly(o) for o in outl]))
            tube = G.union([G.qpoly(LineString(ln).buffer(PLATFORM_GAP / 1000.0,
                                                           cap_style="flat"))
                            for ln in lines])
            plat = G.diff(plat, tube)
            pcs = G.to_model_polys(plat)
        made = 0
        for pc in pcs:
            ring = RF._ccw(RG.mm_ring(pc["exterior"]))
            if len(ring) < 3 or not RG.is_simple(ring) or abs(area2(ring)) < 2 * 4_000_000:
                continue
            if RF.slab(sb.buf, ring, [], z0, floor, "platform", "portal_lining"):
                made += 1
        if made:
            rec["platform"] = True
            rec["floor_m"] = round(floor / 1000.0, 3)
            sb.stats["sky_platforms"] = sb.stats.get("sky_platforms", 0) + made


def mouth_frames(sb) -> None:
    """A frame with a light strip round each portal mouth, on the facades it opens."""
    _frames_on_rings(sb)


def _frames_on_rings(sb) -> None:
    from shapely.geometry import LineString
    for p, rec in zip(sb.br["portals"], sb.portal_recs):
        if not rec.get("cut"):
            continue
        za, zb = rec["z"]
        half = int(round((p["diameter_m"] / 2.0) * 1000)) + PORTAL_CLEAR
        seen = set()
        for pl in p["lines"]:
            line = [(int(round(q[0] * 1000)), int(round(q[1] * 1000))) for q in pl]
            if len(line) >= 2:
                _mouths(sb, line, za, zb, half, seen)


def _mouths(sb, line, za: int, zb: int, half: int, seen: set) -> None:
    """The frames where one tube polyline crosses the outlines of the masses over the
    portal (their walls run on down round the mouth)."""
    from shapely.geometry import LineString
    ls = LineString(line)
    for ms in sb.masses:
        if not ms.get("portal_top"):
            continue
        ring = RG.clean(ms["rings"][0])
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            hit = ls.intersection(LineString([a, b]))
            if hit.is_empty or hit.geom_type != "Point":
                continue
            key = (int(round(hit.x)) // 500, int(round(hit.y)) // 500)
            if key in seen:
                continue
            seen.add(key)
            ux, uy, L = RF._unit(a, b)
            # the mouth's width along the facade (the tube may cross it at a slant)
            k = len(line) - 2
            for j in range(len(line) - 1):
                if LineString([line[j], line[j + 1]]).distance(hit) < 1.0:
                    k = j
                    break
            tx, ty, _ = RF._unit(line[k], line[k + 1])
            sn = abs(tx * uy - ty * ux)
            if sn < 0.3:
                continue
            # (the mouth's width along the facade, and on a slanted tube room for the
            # frame's depth, so no jamb stands in the tube's corridor)
            cs = abs(tx * ux + ty * uy)
            w = PT.q(min(2 * (half + FRAME_DEPTH * cs) / sn, L - 600))
            s_ = (hit.x - a[0]) * ux + (hit.y - a[1]) * uy
            room = (s_ - w / 2, L - s_ - w / 2)
            if min(room) < 0:
                continue           # (the mouth runs round the facade's corner)
            pr = {"w": w, "h": PT.q(zb - za)}
            # (a mouth near the facade's corner: the jamb on that side as wide as fits)
            for key_, r_ in zip(("jl", "jr"), room):
                if r_ < FRAME_JAMB:
                    pr[key_] = int(r_ // 100) * 100 if r_ >= 200 else 0
            sb.parts.add("portal_frame", pr, int(round(hit.x)),
                         int(round(hit.y)), za, ux, uy)
            sb.stats["portal_frames"] = sb.stats.get("portal_frames", 0) + 1


def gen_portal_frame(p: dict, b) -> None:
    """The frame round a portal mouth w wide and h tall (x along the facade, y into it):
    jambs and a head 0.6 m wide standing 0.3 m proud, a light strip on their inner edge;
    near a corner a jamb as wide as the facade leaves (`jl`, `jr`, 0: none)."""
    w, h = p["w"], p["h"]
    hw = w // 2
    j = FRAME_JAMB
    jl, jr = p.get("jl", j), p.get("jr", j)
    if jl:
        box(b, "portal_lining", -hw - jl, -hw, -300, 0, 0, h + j)
        box(b, "lamp_white", -hw - 60, -hw, -320, -260, 200, h - 200)
    if jr:
        box(b, "portal_lining", hw, hw + jr, -300, 0, 0, h + j)
        box(b, "lamp_white", hw, hw + 60, -320, -260, 200, h - 200)
    box(b, "portal_lining", -hw, hw, -300, 0, h, h + j)
    box(b, "lamp_white", -hw + 200, hw - 200, -320, -260, h, h + 60)


def gen_balustrade(p: dict, b) -> None:
    """A glass balustrade L long (x 0 to L) h tall, its top rail and shoe."""
    L, h = p["L"], p["h"]
    box(b, "steel", 0, L, -60, 60, 0, 80)
    box(b, "glazing", 20, L - 20, -12, 12, 80, h - 40)
    box(b, "railing", 0, L, -40, 40, h - 40, h)


def gen_planter(p: dict, b) -> None:
    w, d, h = p["w"], p["d"], p["h"]
    box(b, "planter", -w // 2, w // 2, -d // 2, d // 2, 0, h)
    box(b, "green_roof", -w // 2 + 80, w // 2 - 80, -d // 2 + 80, d // 2 - 80, h, h + 60)


FAMILIES = ("portal_frame", "balustrade", "planter")
PT.GEN.update({"portal_frame": gen_portal_frame, "balustrade": gen_balustrade,
               "planter": gen_planter})
PT.REACH.update({"portal_frame": "strip", "balustrade": "flush", "planter": "court"})
PT.TYPE_SUB.update({"portal_frame": "mouth", "balustrade": "glass", "planter": "box"})


# ---------------------------------------------------------------------------
# Decks and courts
# ---------------------------------------------------------------------------

def deck(sb, ms: dict) -> None:
    """A deck mass's top: paving, glass balustrades on its free edges, planters."""
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3:
        return
    z = ms["z1"]
    pav = RF.miter(ring, [-100] * len(ring))
    if pav is not None:
        RF.slab(sb.buf, pav, [], z, z + 50, "roof_paver", "roof_paver")
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        ux, uy, L = RF._unit(a, b)
        if L < 2000:
            continue
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        out = (int(round(mx + uy * 600)), int(round(my - ux * 600)))
        if any(o is not ms and o["z0"] < z + 500 and o["z1"] > z + 500 and
               RG.in_poly(out, o["rings"]) >= 0 for o in sb.masses):
            continue          # this edge runs into a tower
        s0, s1 = 300, int(L) - 300
        x = int(round(a[0] + ux * s0 - uy * 150))
        y = int(round(a[1] + uy * s0 + ux * 150))
        sb.parts.add("balustrade", {"L": PT.q(s1 - s0), "h": 1100}, x, y, z + 50, ux, uy)
    # planters along the deck's length
    k = max(range(n), key=lambda i: (RF._unit(ring[i], ring[(i + 1) % n])[2], -i))
    ux, uy, L = RF._unit(ring[k], ring[(k + 1) % n])
    c = RF._centroid(ring)
    lo = hi = 0.0
    for p in ring:
        t = (p[0] - c[0]) * ux + (p[1] - c[1]) * uy
        lo, hi = min(lo, t), max(hi, t)
    m = int((hi - lo - 4000) // 9000)
    for j in range(max(m, 0)):
        t = lo + 2000 + (hi - lo - 4000) * (2 * j + 1) / (2 * m)
        x, y = int(round(c[0] + ux * t)), int(round(c[1] + uy * t))
        if RG.in_poly((x, y), ms["rings"]) == 1:
            sb.parts.add("planter", {"w": 2400, "d": 1200, "h": 550}, x, y, z + 50, ux, uy)
    sb.stats["decks"] = sb.stats.get("decks", 0) + 1
    sb.used["deck"] = True


def courts(sb, ms: dict) -> None:
    """A mass on the ground with courts: each court's floor paved, planters at its corners,
    galleries at every floor line of the mass along its walls with a glass rail."""
    if ms["z0"] > 50 or len(ms["rings"]) < 2:
        return
    n = ms["floors"]
    for h in ms["rings"][1:]:
        hole = RG.clean(h)
        if len(hole) < 3:
            continue
        court = RF._ccw(hole)
        if abs(area2(court)) < 2 * 60_000_000:
            continue
        RF.slab(sb.buf, court, [], ms["z0"], ms["z0"] + 100, "court_paving", "court_paving")
        inner = RF.miter(court, [-2500] * len(court))
        if inner is not None:
            for q in inner:
                sb.parts.add("planter", {"w": 1600, "d": 1600, "h": 600}, q[0], q[1],
                             ms["z0"] + 100, 1.0, 0.0)
        # galleries (outward of the solid is into the court)
        res = RG.strip(hole, 0, len(hole), GALLERY, 0, 0)
        rail = RG.strip(hole, 0, len(hole), GALLERY, GALLERY - 40, 0)
        if res is None or rail is None:
            continue
        made = 0
        for f in range(1, n):
            zf = ms["z0"] + (ms["z1"] - ms["z0"]) * f // n
            if zf < 3200:
                continue
            sb.buf.new_part()
            if sb._extrude(res[0], res[1], zf - 200, zf, "balcony"):
                sb.buf.new_part()
                sb._extrude(rail[0], rail[1], zf, zf + 1100, "glazing")
                made += 1
        if made:
            sb.stats["galleries"] = sb.stats.get("galleries", 0) + made
            sb.used["court"] = True
        sb.stats["courts"] = sb.stats.get("courts", 0) + 1
