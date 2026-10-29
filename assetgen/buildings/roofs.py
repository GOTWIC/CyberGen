"""Roofs (scope 5.1.3, AG4): roof forms, finishes, copings, green roofs, the equipment of
every roof item, access huts, vents and skylights.

**Roof forms** (the crown gene of eras that have them, `systems.AG4_CROWNS`; sheds by their
own gene, `systems.SHED_FORMS`): a pitched roof stands inside the building's envelope, in its top floor (the
attic: the mass's walls stop a floor lower, `plan`), or for a one-floor shed in the top of
its tall floor, so it never rises over the model's mass:

| form | where | what |
|---|---|---|
| hip, gable | heritage and suburban crowns `pitched`, a rectangular top | slopes to a ridge at the era's pitch; gable ends flush with the facades below (in the wall's slot), hips where the ends are free |
| pagoda | heritage crown `pagoda_roof`, a rectangle | a hip whose four corners curl up |
| mansard | the same crowns on any other top, or roof items need a flat top | slopes from the eave to a flat top inset by the run (a hip with a flat top when the slope is low) |
| sawtooth | industrial crown `sawtooth`, sheds and warehouses by gene | teeth with their glazing facing north |
| barrel | aerospace crown `dome`, hangars, some sheds | a segmental vault across the short side |

A gable or hip whose ridge would rise past the attic is flattened to fit, down to 8 degrees
(`FLATTEST`); a shed's own form needs a rectangle (else its roof stays flat). Eaves overhang
by the era's eave on edges no neighbor or own mass stands against (none on
party, hidden and blind stretches), always under 0.6 m. A one-floor storey set on another mass (a villa's
top tier) is all roof, its eaves on the mass below. A form needs its mass on top of the
building (nothing over it), one ring (no court), nothing mounted above the eave line, and no
pad, penthouse, billboard or green roof on it; AC units, water tanks and antennas stand at
the roof's top on steel frames (`dunnage`) down to the slope under them.

**Finishes** on every flat roof open to the sky (gene `roof_finish` by era): the era's roof
surface (AG6's set) with a gravel field inset from the parapet, a paver terrace or a
membrane with a walkway; **copings** on the parapets (metal, or stone in heritage, brutalist
and suburban eras).

**Green roofs** (M3's green areas on the building): the planted bed 0.5 m in from the
area's edge on a soil build-up, a gravel border, a paver path through larger ones; the
blockout's green roof objects are replaced (`green`).

**Roof items** (every one has an asset, `items`): AC units, water tanks, antennas and
helipads and AV pads as instanced equipment (`roofparts`), mechanical penthouses merged into
the shell, billboards left to AG8 (its sign asset has the frame). An item whose asset would
enter a clearance (a transit line or skybridge over the roof, the brief's `clearances`) is
made lower (an antenna shortened, a tank squat).

**Access huts** on roofs of three floors or more with no penthouse; **vents and skylights**
by roof area; the neon era's empty billboard frame crown where no billboard stands.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from ..triangulate import TriangulationError, area2, triangulate
from . import genome as GN
from . import parts as PT
from . import rings as RG
from . import roofparts as RP
from . import systems as SY

FASCIA = 200                    # eave fascia (mm)
EAVE_MAX = 550                  # an eave's overhang at most (its corner under 0.8 m out)
EAVE_CORNER = 850               # a mitred eave corner at most this far out (the envelope: 0.9)
GREEN_BASE = 80                 # a green roof's gravel border and the bed's foot (mm)
MIN_ATTIC = 1200                # a form needs at least this rise
SHED_WALL = 4000                # a one-floor shed keeps this much wall under its roof form
ROOF_STOREY = 4600              # a one-floor storey on another mass this low is all roof
PITCHED_FLOORS = 12             # pitched forms on buildings up to this many floors
FLATTEST = 0.14                 # a gable or hip flattened to its attic: at least 8 degrees
LEG_MIN = 150                   # an item stands on dunnage where the roof is this far under it
ITEM_KEEP = ("ac_unit", "water_tank", "antenna")      # items a roof form can carry
HUT = (2400, 3000, 2700)        # access hut (along, across, up) mm
CURL = 350                      # a pagoda roof's corner curl


def _u(key: str, purpose: str) -> float:
    return GN.u(key, purpose, "ag4.roof")


def _centroid(ring):
    n = len(ring)
    return (sum(p[0] for p in ring) // n, sum(p[1] for p in ring) // n)


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.sqrt(dx * dx + dy * dy) or 1.0
    return dx / L, dy / L, L


def _ccw(ring):
    ring = [(int(p[0]), int(p[1])) for p in ring]
    return ring if area2(ring) > 0 else ring[::-1]


# ---------------------------------------------------------------------------
# Faces on the shell's buffer
# ---------------------------------------------------------------------------

def _newell(pts):
    nx = ny = nz = 0.0
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    L = math.sqrt(nx * nx + ny * ny + nz * nz)
    return None if L == 0 else (nx / L, ny / L, nz / L)


def pface(buf, slot: str, pts, hint) -> bool:
    """A planar polygon of integer points facing the side of `hint`, triangulated in the
    plane it is most square to (straight runs kept, so no T-junction)."""
    pts = [tuple(int(v) for v in p) for p in pts]
    n = _newell(pts)
    if n is None:
        return False
    if n[0] * hint[0] + n[1] * hint[1] + n[2] * hint[2] < 0:
        n = (-n[0], -n[1], -n[2])
    ax = max(range(3), key=lambda k: abs(n[k]))
    keep = [k for k in range(3) if k != ax]
    p2 = [(p[keep[0]], p[keep[1]]) for p in pts]
    if len(set(p2)) != len(p2):
        return False
    flip = area2(p2) < 0
    q2 = p2[::-1] if flip else p2
    try:
        tris = triangulate(q2, [], keep_straight=True)
    except TriangulationError:
        return False
    if not tris:
        return False
    m = len(pts)
    if flip:
        tris = [tuple(m - 1 - i for i in t) for t in tris]
    PT.face(buf, slot, pts, n, tris)
    return True


def tri(buf, slot: str, a, b, c, hint) -> None:
    pface(buf, slot, [a, b, c], hint)


def slab(buf, ring, holes, z0: int, z1: int, top: str, side: str, bottom: str | None = None
         ) -> bool:
    """A closed slab of a plan ring (with holes) from z0 to z1: its top in `top`, sides and
    bottom in `side` (or `bottom`)."""
    ring = _ccw(ring)
    holes = [h if area2(h) < 0 else h[::-1] for h in (_ccw(x) for x in holes)]
    try:
        tris = triangulate(ring, holes, keep_straight=True)
    except TriangulationError:
        return False
    if not tris or z1 <= z0:
        return False
    pts = ring + [p for h in holes for p in h]
    buf.new_part()
    PT.face(buf, top, [(p[0], p[1], z1) for p in pts], (0.0, 0.0, 1.0), tris)
    PT.face(buf, bottom or side, [(p[0], p[1], z0) for p in pts], (0.0, 0.0, -1.0),
            [(t[0], t[2], t[1]) for t in tris])
    for rg in [ring] + holes:
        k = len(rg)
        for i in range(k):
            p, q = rg[i], rg[(i + 1) % k]
            if p == q:
                continue
            dx, dy = q[0] - p[0], q[1] - p[1]
            L = math.sqrt(dx * dx + dy * dy)
            PT.face(buf, side, [(p[0], p[1], z0), (q[0], q[1], z0), (q[0], q[1], z1),
                                (p[0], p[1], z1)], (dy / L, -dx / L, 0.0))
    return True


def miter(ring, d):
    """The ring with edge i moved out by d[i] (mm, negative in), every corner a miter;
    None where an edge turns round, parallel neighbors part, or it stops being simple."""
    n = len(ring)
    us = [_unit(ring[i], ring[(i + 1) % n])[:2] for i in range(n)]
    out = []
    for i in range(n):
        u0, u1 = us[i - 1], us[i]
        d0, d1 = d[i - 1], d[i]
        p = ring[i]
        q1 = (p[0] + u0[1] * d0, p[1] - u0[0] * d0)
        q2 = (p[0] + u1[1] * d1, p[1] - u1[0] * d1)
        cr = u0[0] * u1[1] - u0[1] * u1[0]
        if abs(cr) < 1e-6:
            if abs(d0 - d1) > 0.5:
                return None
            out.append((int(round(q1[0])), int(round(q1[1]))))
            continue
        t = (u1[0] * (q2[1] - q1[1]) - u1[1] * (q2[0] - q1[0])) / -cr
        x, y = q1[0] + t * u0[0], q1[1] + t * u0[1]
        if math.hypot(x - p[0], y - p[1]) > 4.0 * max(abs(d0), abs(d1)) + 2.0:
            return None
        out.append((int(round(x)), int(round(y))))
    if len(set(out)) != n or not RG.is_simple(out) or area2(out) <= 0:
        return None
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        p, q = out[i], out[(i + 1) % n]
        if (b[0] - a[0]) * (q[0] - p[0]) + (b[1] - a[1]) * (q[1] - p[1]) <= 0:
            return None
    return out


# ---------------------------------------------------------------------------
# Clearances (the brief's corridors) as a test on boxes
# ---------------------------------------------------------------------------

class Clear:
    """The brief's clearance corridors (AG4) in millimeters: `hits` tests a box."""

    def __init__(self, brief: dict, kinds=("skybridge", "guideway", "sky_tube")):
        self.segs = []
        for c in brief.get("clearances") or []:
            if c["kind"] not in kinds:
                continue
            h = c["half_m"] * 1000.0
            ln = [[v * 1000.0 for v in p] for p in c["line"]]
            for p, q in zip(ln, ln[1:]):
                self.segs.append((p, q, h, c["kind"], c["id"]))

    def lowest(self, x0, y0, x1, y1, z0) -> float | None:
        """The lowest corridor floor over the plan box (x0..x1, y0..y1) that reaches above z0
        (None: none)."""
        best = None
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        r = math.hypot(x1 - x0, y1 - y0) / 2.0
        for p, q, h, *_ in self.segs:
            dx, dy = q[0] - p[0], q[1] - p[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else min(max(((cx - p[0]) * dx + (cy - p[1]) * dy) / L2, 0.0),
                                        1.0)
            d = math.hypot(cx - (p[0] + dx * t), cy - (p[1] + dy * t))
            if d > h + r:
                continue
            zlo = p[2] + (q[2] - p[2]) * t
            zhi = p[3] + (q[3] - p[3]) * t
            if zhi <= z0:
                continue
            if best is None or zlo < best:
                best = zlo
        return best

    def hits(self, x0, y0, x1, y1, z0, z1) -> bool:
        lo = self.lowest(x0, y0, x1, y1, z0)
        return lo is not None and lo < z1


# ---------------------------------------------------------------------------
# Plan: which masses take a roof form (before the masses are built)
# ---------------------------------------------------------------------------

def _rect(ring):
    """A clean 4-corner ring whose corners are right angles (within 1.5 degrees): its
    (start index of the longer edge pair)."""
    if len(ring) != 4:
        return None
    us = [_unit(ring[i], ring[(i + 1) % 4]) for i in range(4)]
    for i in range(4):
        a, b = us[i], us[(i + 1) % 4]
        if abs(a[0] * b[0] + a[1] * b[1]) > 0.026:
            return None
    if abs(us[0][2] - us[2][2]) > 30 or abs(us[1][2] - us[3][2]) > 30:
        return None
    return 0 if us[0][2] >= us[1][2] else 1


def _overlaps(r1, r2) -> bool:
    if any(RG.inside(p, r2) == 1 for p in r1) or any(RG.inside(p, r1) == 1 for p in r2):
        return True
    return not RG.rings_apart(r1, r2) and any(RG.inside(p, r2) >= 0 for p in r1[:1])


def _items_on(br: dict, ms: dict) -> list[int]:
    """Indices of the roof items standing on this shell mass's top."""
    out = []
    ring = ms["rings"]
    for k, it in enumerate(br["roof_items"]):
        x, y, z = (int(round(v * 1000)) for v in it["position"])
        if abs(z - ms["z1"]) <= 60 and RG.in_poly((x, y), ring) >= 0:
            out.append(k)
    return out


def _marked_above(sb, ms: dict, z: int) -> bool:
    k = ms["k"]
    edges = {j for j, e in enumerate(sb.br["edges"]) if e["mass"] == k}
    for j in edges:
        for m0, m1, za, zb, kind in sb.marks.get(j, []):
            if zb > z - 200:
                return True
    for s in sb.br["sign_slots"]:
        if s["mount"] == "roof":
            x, y = int(round(s["position"][0] * 1000)), int(round(s["position"][1] * 1000))
            if RG.in_poly((x, y), ms["rings"]) >= 0:
                return True
    return False


def _green_on(br: dict, ms: dict) -> bool:
    for g in br["green_roofs"]:
        if abs(int(round(g["z_m"] * 1000)) - ms["z1"]) <= 60 and g.get("polygon"):
            ext = RG.mm_ring(g["polygon"]["exterior"])
            if ext and RG.in_poly(_centroid(ext), ms["rings"]) >= 0:
                return True
    return False


def form_of(sb) -> str | None:
    """The roof form a building draws (by its crown and type), or None."""
    br = sb.br
    b = br["building"]
    genes = sb.gm["genes"]
    crown = genes.get("crown", "flat")
    era = sb.gm.get("era")
    shed = b["type"] in SY.SHED_TYPES and genes["body.system"] in SY.INDUSTRIAL
    if shed:
        f = genes.get("roof_form", "flat")
        if crown == "sawtooth":
            f = "sawtooth"
        if b["type"] == "building.hangar" and crown == "dome":
            f = "barrel"
        return None if f == "flat" else f
    if crown == "pitched" and b["floors"] <= PITCHED_FLOORS:
        return "pitched"
    if crown == "pagoda_roof" and b["floors"] <= PITCHED_FLOORS:
        return "pagoda"
    if crown == "dome" and era == "aerospace" and b["floors"] <= 6:
        return "barrel"
    return None


def plan(sb) -> None:
    """Decide the roof forms (before the masses are built): a mass that takes one is cut a
    floor lower (its attic is the roof) or, a one-floor shed, at its wall height; its record
    `ms["roof"]` says what to build on it."""
    br = sb.br
    sb.roof_forms = []
    if br["building"]["landmark"] or br["portals"]:
        return
    form = form_of(sb)
    if form is None:
        return
    genes, cont = sb.gm["genes"], sb.gm["cont"]
    era = sb.gm.get("era") or "mixed_modern"
    for ms in sb.masses:
        g = SY.role_group(ms["role"])
        if ms["shape"] != "prism" or len(ms["rings"]) != 1 or g == "structure" or \
                ms.get("screen") or ms["floors"] < 1:
            continue
        ring = RG.clean(ms["rings"][0])
        if len(ring) < 3 or area2(ring) <= 0:
            continue
        zt = ms["z1"]
        n = ms["floors"]
        H = ms["z1"] - ms["z0"]
        if n >= 2:
            zb = ms["z0"] + (ms["z1"] - ms["z0"]) * (n - 1) // n
        elif ms["z0"] > 50 and H <= ROOF_STOREY:
            zb = ms["z0"]            # a one-floor storey on another mass: all roof
        else:
            if H < SHED_WALL + MIN_ATTIC:
                continue
            zb = ms["z1"] - min(max(MIN_ATTIC, H // 4), H - SHED_WALL)
        if zt - zb < MIN_ATTIC:
            continue
        if any(o is not ms and o["z1"] > zb + 50 and o["z0"] < zt - 50 and
               _overlaps(RG.clean(o["rings"][0]), ring) for o in sb.masses):
            continue
        if any(o is not ms and o["z0"] >= zt - 50 and
               _overlaps(RG.clean(o["rings"][0]), ring) for o in sb.masses):
            continue
        if _marked_above(sb, ms, zb) or _green_on(br, ms):
            continue
        items = _items_on(br, ms)
        if any(br["roof_items"][k]["kind"] not in ITEM_KEEP for k in items):
            continue
        kind = form
        rect = _rect(ring)
        if kind in ("sawtooth", "barrel", "gable") and rect is None:
            continue             # (a shed's own form needs a rectangle; else it stays flat)
        if kind == "pagoda" and (rect is None or items):
            kind = "pitched"
        if kind == "pitched":
            if rect is not None and not items:
                kind = "gable" if _u(sb.bid, "gable") < SY.GABLE_SHARE.get(era, 0.4) else "hip"
            else:
                kind = "mansard"
        eave = int(round(cont.get("roof_eave_m", 0.4) * 1000))
        eave = min(eave, EAVE_MAX)
        if kind in ("sawtooth",):
            eave = 0
        ok = sb._edge_ok(ms, zb - 400, zb + 100)
        # (edge_ok is per the mass's ring edges, with its zero-length edges)
        keep = [i for i in range(len(ms["rings"][0]))
                if ms["rings"][0][i] != ms["rings"][0][(i + 1) % len(ms["rings"][0])]]
        e = [eave if ok[0][i] else 0 for i in keep]
        if len(e) != len(ring):
            continue
        pitch = float(cont.get("roof_pitch", 32.0))
        if kind == "mansard":
            pitch = float(cont.get("roof_mansard", 68.0))
        rf = {"kind": kind, "zb": zb, "zt": zt, "eave": e, "pitch": pitch,
              "rect": rect, "items": items, "ring": ring}
        ms["roof"] = rf
        ms["z1"] = zb
        ms["floors"] = n - 1 if n >= 2 else (0 if zb <= ms["z0"] else n)
        sb.roof_forms.append(ms)


# ---------------------------------------------------------------------------
# Roof forms
# ---------------------------------------------------------------------------

def _rect_frame(ring, k: int, e):
    """(center, u, v, W, D, eaves [s, e, n, w]) of a rectangle ring, x along its longer
    edges (edge k), y inward from it."""
    r = ring[k:] + ring[:k]
    ee = e[k:] + e[:k]
    ux, uy, W = _unit(r[0], r[1])
    _, _, D = _unit(r[1], r[2])
    vx, vy = -uy, ux
    cx = r[0][0] + ux * W / 2.0 + vx * D / 2.0
    cy = r[0][1] + uy * W / 2.0 + vy * D / 2.0
    return (cx, cy), (ux, uy), (vx, vy), W, D, ee


def _to(c, u, v):
    def f(x, y, z):
        return (int(round(c[0] + u[0] * x + v[0] * y)), int(round(c[1] + u[1] * x + v[1] * y)),
                int(z))
    return f


def build_form(sb, ms: dict, wall: str) -> bool:
    rf = ms["roof"]
    kind = rf["kind"]
    sb.buf.new_part()
    ok = False
    if kind in ("hip", "gable", "pagoda", "barrel", "sawtooth"):
        ok = _rect_form(sb, ms, rf, wall)
    if not ok:
        rf["kind"] = "mansard" if kind not in ("sawtooth", "barrel") else kind
        if rf["kind"] == "mansard":
            sb.buf.new_part()
            ok = _ring_form(sb, rf)
    if ok:
        sb.stats["roof_forms"] = sb.stats.get("roof_forms", 0) + 1
        st = sb.stats.setdefault("roof_form_kinds", {})
        st[rf["kind"]] = st.get(rf["kind"], 0) + 1
        sb.used["roof"] = rf["kind"]
    else:
        # nothing fits after all: the attic floor as a plain flat-topped storey
        sb.buf.new_part()
        sb._extrude(rf["ring"], None, rf["zb"], rf["zt"], wall)
        rf["kind"] = "flat"
    return ok


def slope_slot(sb) -> str:
    era = sb.gm.get("era")
    if sb.br["building"]["type"] in SY.SHED_TYPES or era in ("industrial", "aerospace"):
        return "roof_metal"
    return "tile" if era in ("heritage", "suburban_modern") else \
        ("tile" if sb.gm["genes"].get("roof_finish") == "tile" else "roof_metal")


def _ring_form(sb, rf: dict) -> bool:
    """A mansard or hip with a flat top on any ring: slopes from the eave ring to the top
    ring inset by the run, the top flat."""
    ring, e = rf["ring"], rf["eave"]
    zb, zt = rf["zb"], rf["zt"]
    zf = zb + FASCIA
    h = zt - zf
    if h < 600:
        return False
    B = None
    for k in range(3):
        # (an eave mitred at an acute corner reaches further out: halved, then none, so
        # every corner stays within the cornice allowance, `EAVE_CORNER`)
        B = miter(ring, e)
        if B is not None and all(math.hypot(B[i][0] - ring[i][0], B[i][1] - ring[i][1]) <=
                                 EAVE_CORNER for i in range(len(ring))):
            break
        B = None
        e = [ei // 2 for ei in e] if k == 0 else [0] * len(e)
    if B is None:
        return False
    rf["eave"] = e
    tanp = float(M.tan(M.radians(rf["pitch"])))
    run0 = h / max(tanp, 0.2)
    I = None
    for run in (run0, run0 * 0.75, run0 * 0.55, h / float(M.tan(M.radians(76.0)))):
        cand = miter(ring, [ei - run for ei in e])
        if cand is None:
            continue
        n = len(cand)
        if any(math.hypot(cand[(i + 1) % n][0] - cand[i][0], cand[(i + 1) % n][1] -
                          cand[i][1]) < 200 for i in range(n)):
            continue
        if not RG.rings_apart(cand, B) or RG.inside(cand[0], B) != 1:
            continue
        I = cand
        rf["run"] = int(round(run))
        rf["pitch"] = round(math.degrees(math.atan2(h, run)), 1)
        break
    if I is None:
        return False
    buf = sb.buf
    slope = slope_slot(sb)
    n = len(ring)
    pface(buf, "soffit", [(p[0], p[1], zb) for p in B], (0.0, 0.0, -1.0))
    for i in range(n):
        a, b = B[i], B[(i + 1) % n]
        ux, uy, _ = _unit(a, b)
        out = (uy, -ux, 0.0)
        pface(buf, "trim", [(a[0], a[1], zb), (b[0], b[1], zb), (b[0], b[1], zf),
                            (a[0], a[1], zf)], out)
        p, q = I[i], I[(i + 1) % n]
        pface(buf, slope, [(a[0], a[1], zf), (b[0], b[1], zf), (q[0], q[1], zt),
                           (p[0], p[1], zt)], (uy, -ux, 0.7))
    pface(buf, "roof", [(p[0], p[1], zt) for p in I], (0.0, 0.0, 1.0))
    rf["B"], rf["I"], rf["zf"] = B, I, zf
    rf["tan"] = h / rf["run"]
    return True


def _rect_form(sb, ms: dict, rf: dict, wall: str) -> bool:
    ring, e = rf["ring"], rf["eave"]
    kind = rf["kind"]
    c, u, v, W, D, ee = _rect_frame(ring, rf["rect"], e)
    zb, zt = rf["zb"], rf["zt"]
    zf = zb + FASCIA
    h = zt - zf
    if h < 500:
        return False
    P = _to(c, u, v)
    buf = sb.buf
    slope = slope_slot(sb)
    es, eo, en, ew = ee            # south (edge k), east, north, west in the frame
    if kind == "gable" or kind == "barrel":
        eo = ew = 0
    if kind == "sawtooth":
        es = eo = en = ew = 0
    x0, x1 = -W / 2.0 - ew, W / 2.0 + eo
    y0, y1 = -D / 2.0 - es, D / 2.0 + en
    rf.update(frame=(c, u, v), box=(x0, x1, y0, y1), zf=zf, slope=slope)
    outs = {"s": (-v[0], -v[1], 0.0), "n": (v[0], v[1], 0.0), "e": (u[0], u[1], 0.0),
            "w": (-u[0], -u[1], 0.0)}

    def up(o, k=0.7):
        return (o[0], o[1], k)
    if kind in ("hip", "pagoda"):
        hd = (y1 - y0) / 2.0
        ym = (y0 + y1) / 2.0
        tanp = float(M.tan(M.radians(rf["pitch"])))
        rise = hd * tanp
        if rise > h:
            # (an attic lower than the pitch asks: a flatter roof, down to FLATTEST)
            tanp = h / hd
            if tanp < FLATTEST:
                return False
            rise = h
            rf["pitch"] = round(math.degrees(math.atan(tanp)), 1)
        zr = zf + int(round(rise))
        rx0, rx1 = x0 + hd, x1 - hd
        if rx1 - rx0 < 300:
            rx0 = rx1 = (x0 + x1) / 2.0
        c0, c1, c2, c3 = P(x0, y0, zf), P(x1, y0, zf), P(x1, y1, zf), P(x0, y1, zf)
        R0, R1 = P(rx0, ym, zr), P(rx1, ym, zr)
        pface(buf, "soffit", [P(x0, y0, zb), P(x1, y0, zb), P(x1, y1, zb), P(x0, y1, zb)],
              (0.0, 0.0, -1.0))
        if kind == "hip":
            for a, b, o in ((P(x0, y0, zb), P(x1, y0, zb), "s"),
                            (P(x1, y0, zb), P(x1, y1, zb), "e"),
                            (P(x1, y1, zb), P(x0, y1, zb), "n"),
                            (P(x0, y1, zb), P(x0, y0, zb), "w")):
                pface(buf, "trim", [a, b, (b[0], b[1], zf), (a[0], a[1], zf)], outs[o])
            same = R0 == R1
            pface(buf, slope, [c0, c1, R1] if same else [c0, c1, R1, R0], up(outs["s"]))
            pface(buf, slope, [c1, c2, R1], up(outs["e"]))
            pface(buf, slope, [c2, c3, R0] if same else [c2, c3, R0, R1], up(outs["n"]))
            pface(buf, slope, [c3, c0, R0], up(outs["w"]))
        else:
            # pagoda: the corners curl up, the eave's midpoints stay
            k0, k1, k2, k3 = (P(x0, y0, zf + CURL), P(x1, y0, zf + CURL), P(x1, y1, zf + CURL),
                              P(x0, y1, zf + CURL))
            mid = [P((x0 + x1) / 2.0, y0, zf), P(x1, ym, zf), P((x0 + x1) / 2.0, y1, zf),
                   P(x0, ym, zf)]
            cs = [k0, k1, k2, k3]
            bot = [P(x0, y0, zb), P(x1, y0, zb), P(x1, y1, zb), P(x0, y1, zb)]
            mb = [(m_[0], m_[1], zb) for m_ in mid]
            for i, o in enumerate("senw"):
                a, b = bot[i], bot[(i + 1) % 4]
                pface(buf, "trim", [a, mb[i], mid[i], cs[i]], outs[o])
                pface(buf, "trim", [mb[i], b, cs[(i + 1) % 4], mid[i]], outs[o])
            # (the soffit holds the eave's midpoints too, so its edges match the fascia)
            pface(buf, "soffit", [bot[0], mb[0], bot[1], mb[1], bot[2], mb[2], bot[3], mb[3]],
                  (0.0, 0.0, -1.0))
            ridge = [(R0, R1), (R1, R1), (R1, R0), (R0, R0)]
            for i, o in enumerate("senw"):
                ra, rb = ridge[i]
                a, b, m_ = cs[i], cs[(i + 1) % 4], mid[i]
                tri(buf, slope, a, m_, ra, up(outs[o]))
                tri(buf, slope, m_, b, rb, up(outs[o]))
                if ra != rb:
                    tri(buf, slope, m_, rb, ra, up(outs[o]))
        rf["ridge"] = (rx0, rx1, ym, zr)
        rf["tan"] = tanp
        return True
    if kind == "gable":
        hd = (y1 - y0) / 2.0
        ym = (y0 + y1) / 2.0
        tanp = float(M.tan(M.radians(rf["pitch"])))
        rise = hd * tanp
        if rise > h:
            # (an attic lower than the pitch asks: a flatter roof, down to FLATTEST)
            tanp = h / hd
            if tanp < FLATTEST:
                return False
            rise = h
            rf["pitch"] = round(math.degrees(math.atan(tanp)), 1)
        zr = zf + int(round(rise))
        pface(buf, "soffit", [P(x0, y0, zb), P(x1, y0, zb), P(x1, y1, zb), P(x0, y1, zb)],
              (0.0, 0.0, -1.0))
        pface(buf, "trim", [P(x0, y0, zb), P(x1, y0, zb), P(x1, y0, zf), P(x0, y0, zf)],
              outs["s"])
        pface(buf, "trim", [P(x1, y1, zb), P(x0, y1, zb), P(x0, y1, zf), P(x1, y1, zf)],
              outs["n"])
        pface(buf, slope, [P(x0, y0, zf), P(x1, y0, zf), P(x1, ym, zr), P(x0, ym, zr)],
              up(outs["s"]))
        pface(buf, slope, [P(x1, y1, zf), P(x0, y1, zf), P(x0, ym, zr), P(x1, ym, zr)],
              up(outs["n"]))
        for x, o in ((x0, "w"), (x1, "e")):
            pface(buf, wall, [P(x, y0, zb), P(x, y0, zf), P(x, ym, zr), P(x, y1, zf),
                              P(x, y1, zb)], outs[o])
        rf["ridge"] = (x0, x1, ym, zr)
        rf["tan"] = tanp
        return True
    if kind == "barrel":
        half = (y1 - y0) / 2.0
        ym = (y0 + y1) / 2.0
        rise = min(h, half * 0.35)
        if rise < 600:
            return False
        R = (half * half + rise * rise) / (2.0 * rise)
        N = 12
        prof = []
        for k in range(N + 1):
            y = y0 + (y1 - y0) * k / N
            z = zf + math.sqrt(max(R * R - (y - ym) * (y - ym), 0.0)) - (R - rise)
            prof.append((y, int(round(z))))
        prof[0] = (y0, zf)
        prof[-1] = (y1, zf)
        pface(buf, "soffit", [P(x0, y0, zb), P(x1, y0, zb), P(x1, y1, zb), P(x0, y1, zb)],
              (0.0, 0.0, -1.0))
        pface(buf, "trim", [P(x0, y0, zb), P(x1, y0, zb), P(x1, y0, zf), P(x0, y0, zf)],
              outs["s"])
        pface(buf, "trim", [P(x1, y1, zb), P(x0, y1, zb), P(x0, y1, zf), P(x1, y1, zf)],
              outs["n"])
        for k in range(N):
            (ya, za), (yb, zb_) = prof[k], prof[k + 1]
            nz = (yb - ya)
            ny = -(zb_ - za)
            L = math.hypot(ny, nz) or 1.0
            hint = (v[0] * ny / L, v[1] * ny / L, nz / L)
            pface(buf, slope, [P(x0, ya, za), P(x0, yb, zb_), P(x1, yb, zb_), P(x1, ya, za)],
                  hint)
        for x, o in ((x0, "w"), (x1, "e")):
            pts = [P(x, y0, zb)] + [P(x, y, z) for y, z in prof] + [P(x, y1, zb)]
            pface(buf, wall, pts, outs[o])
        rf["arc"] = (y0, y1, ym, R, rise)
        return True
    if kind == "sawtooth":
        north = v[1] >= 0          # the frame's +y faces north: glazing on the +y side
        n = max(2, int(round((y1 - y0) / 7000.0)))
        rise = min(h + FASCIA, 2500)
        zt_ = zb + rise
        teeth = []
        for k in range(n):
            ya = y0 + (y1 - y0) * k / n
            yb = y0 + (y1 - y0) * (k + 1) / n
            lo, hi = (ya, yb) if north else (yb, ya)       # slope up from lo to hi
            buf.new_part()
            g = (v[0], v[1], 0.0) if north else (-v[0], -v[1], 0.0)
            pface(buf, "soffit", [P(x0, ya, zb), P(x1, ya, zb), P(x1, yb, zb), P(x0, yb, zb)],
                  (0.0, 0.0, -1.0))
            pface(buf, slope, [P(x0, lo, zb), P(x1, lo, zb), P(x1, hi, zt_), P(x0, hi, zt_)],
                  (-g[0], -g[1], 1.0))
            pface(buf, "skylight", [P(x0, hi, zb), P(x1, hi, zb), P(x1, hi, zt_),
                                    P(x0, hi, zt_)], g)
            for x, o in ((x0, "w"), (x1, "e")):
                pface(buf, wall, [P(x, lo, zb), P(x, hi, zb), P(x, hi, zt_)], outs[o])
            teeth.append((min(lo, hi), max(lo, hi), lo))
        rf["teeth"] = (teeth, rise, north)
        return True
    return False


def surface(rf: dict, x: float, y: float) -> float:
    """The roof form's height (mm) at a point of the building frame."""
    kind = rf["kind"]
    zt = rf["zt"]
    if kind == "mansard":
        B = rf["B"]
        n = len(B)
        d = math.inf
        for i in range(n):
            a, b = B[i], B[(i + 1) % n]
            ux, uy, L = _unit(a, b)
            d = min(d, (x - a[0]) * -uy + (y - a[1]) * ux)       # inward of edge i
        return min(zt, rf["zf"] + max(d, 0.0) * rf["tan"])
    if "frame" not in rf:
        return zt
    c, u, v = rf["frame"]
    lx = (x - c[0]) * u[0] + (y - c[1]) * u[1]
    ly = (x - c[0]) * v[0] + (y - c[1]) * v[1]
    x0, x1, y0, y1 = rf["box"]
    zf = rf["zf"]
    if kind in ("hip", "pagoda"):
        d = min(lx - x0, x1 - lx, ly - y0, y1 - ly)
        return min(rf["ridge"][3], zf + max(d, 0.0) * rf["tan"])
    if kind == "gable":
        d = min(ly - y0, y1 - ly)
        return min(rf["ridge"][3], zf + max(d, 0.0) * rf["tan"])
    if kind == "barrel":
        y0_, y1_, ym, R, rise = rf["arc"]
        yy = min(max(ly, y0_), y1_)
        return zf + math.sqrt(max(R * R - (yy - ym) ** 2, 0.0)) - (R - rise)
    if kind == "sawtooth":
        teeth, rise, north = rf["teeth"]
        for a, b, lo in teeth:
            if a <= ly <= b:
                f = (ly - lo) / ((b - a) or 1.0)
                return rf["zb"] + abs(f) * rise
        return rf["zb"]
    return zt


# ---------------------------------------------------------------------------
# Copings, finishes, green roofs
# ---------------------------------------------------------------------------

def coping_slot(sb) -> str | None:
    era = sb.gm.get("era")
    if sb.gm["genes"].get("coping", "metal") == "none":
        return None
    return "coping_stone" if era in SY.STONE_COPING else "coping"


def finish(sb, ms: dict, top_open) -> None:
    """A flat roof's finish over the era's roof surface: a gravel field, a paver terrace or
    a membrane's walkway, inset from the parapet."""
    if ms.get("roof") or not any(any(r) for r in top_open) or _green_on(sb.br, ms):
        return
    fin = sb.gm["genes"].get("roof_finish", "membrane")
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3 or ms["z1"] - ms["z0"] < 1000:
        return
    holes = [RG.clean(h) for h in ms["rings"][1:]]
    z = ms["z1"]
    if fin in ("gravel", "pavers"):
        inset = 600 if fin == "gravel" else 400
        f = miter(ring, [-inset] * len(ring))
        if f is None or abs(area2(f)) < 2 * 4_000_000:
            return
        hs = []
        for h in holes:
            hh = miter(_ccw(h), [inset] * len(h))
            if hh is None or not RG.rings_apart(hh, f) or RG.inside(hh[0], f) != 1:
                return
            hs.append(hh)
        slot = "roof_gravel" if fin == "gravel" else "roof_paver"
        if slab(sb.buf, f, hs, z, z + (40 if fin == "gravel" else 60), slot, slot):
            sb.stats["roof_finishes"] = sb.stats.get("roof_finishes", 0) + 1
            sb.used["roof_finish"] = fin
        return
    # a membrane: a walkway of pavers along the roof's longest edge's direction, through
    # its middle, where it runs 10 m or more
    n = len(ring)
    k = max(range(n), key=lambda i: (_unit(ring[i], ring[(i + 1) % n])[2], -i))
    ux, uy, _ = _unit(ring[k], ring[(k + 1) % n])
    c = _centroid(ring)
    if RG.in_poly(c, [ring] + holes) != 1:
        return
    lo = hi = 0.0
    for p in ring:
        t = (p[0] - c[0]) * ux + (p[1] - c[1]) * uy
        lo, hi = min(lo, t), max(hi, t)
    lo, hi = lo + 1500, hi - 1500
    if hi - lo < 8000:
        return
    w = 400
    pts = [(c[0] + ux * lo - uy * w, c[1] + uy * lo + ux * w),
           (c[0] + ux * lo + uy * w, c[1] + uy * lo - ux * w),
           (c[0] + ux * hi + uy * w, c[1] + uy * hi - ux * w),
           (c[0] + ux * hi - uy * w, c[1] + uy * hi + ux * w)]
    pts = [(int(round(p[0])), int(round(p[1]))) for p in pts]
    if not all(RG.in_poly(p, [ring] + holes) == 1 for p in pts):
        return
    if slab(sb.buf, pts, [], z, z + 40, "roof_walkway", "roof_walkway"):
        sb.stats["roof_finishes"] = sb.stats.get("roof_finishes", 0) + 1
        sb.used["roof_finish"] = fin


def shapes(pg: dict, d_m: float) -> list[tuple[list, list]]:
    """A brief polygon (meters) shrunk by d_m on citygen's grid (canonical geometry, its
    parts largest first) as (exterior, holes) rings in millimeters that the triangulator
    takes: a hole that touches the outline, or another hole, is left out."""
    from shapely.geometry import Polygon
    from citygen import geom as G
    with G.canonical():
        poly = G.qpoly(Polygon(pg["exterior"], pg["holes"]))
        if d_m:
            poly = G.qpoly(poly.buffer(-d_m, join_style="mitre", mitre_limit=2.0))
        polys = G.to_model_polys(poly) if poly is not None and not poly.is_empty else []
    out = []
    for pm in polys:
        ext = _ccw(RG.mm_ring(pm["exterior"]))
        if len(ext) < 3 or not RG.is_simple(ext):
            continue
        holes = []
        for h in pm["holes"]:
            hh = RG.mm_ring(h)
            if len(hh) >= 3 and RG.is_simple(hh) and RG.rings_apart(hh, ext) and \
                    RG.inside(hh[0], ext) == 1 and all(RG.rings_apart(hh, o) for o in holes):
                holes.append(hh)
        out.append((ext, holes))
    return out


def green_roofs(sb) -> None:
    """M3's green roofs on the building: a gravel border, the planted bed on its soil build
    up 0.5 m in, a paver path through the larger ones; their ids, for the blockout objects
    they replace."""
    sb.green_done = []
    buf = sb.buf
    for g in sb.br["green_roofs"]:
        pg = g.get("polygon")
        if not pg:
            continue
        z = int(round(g["z_m"] * 1000))
        made = False
        for ext, holes in shapes(pg, 0.0):
            # (0.08 m: over the blockout's flat green plate at 0.05, which stays where its
            # joined object also draws a lawn)
            made |= slab(buf, ext, holes, z, z + GREEN_BASE, "roof_gravel", "roof_gravel")
        if not made:
            continue
        for bed, bh in shapes(pg, 0.5):
            if abs(area2(bed)) < 2 * 4_000_000 or not slab(
                    buf, bed, bh, z + GREEN_BASE, z + GREEN_BASE + 200, "green_roof", "soil"):
                continue
            if abs(area2(bed)) / 2.0e6 < 150.0 or bh:
                continue
            n = len(bed)
            k = max(range(n), key=lambda i: (_unit(bed[i], bed[(i + 1) % n])[2], -i))
            ux, uy, _ = _unit(bed[k], bed[(k + 1) % n])
            c = _centroid(bed)
            lo = hi = 0.0
            for p in bed:
                t = (p[0] - c[0]) * ux + (p[1] - c[1]) * uy
                lo, hi = min(lo, t), max(hi, t)
            w = 600
            pts = [(int(round(c[0] + ux * t - uy * s_)), int(round(c[1] + uy * t + ux * s_)))
                   for t, s_ in ((lo + 300, w), (lo + 300, -w), (hi - 300, -w), (hi - 300, w))]
            if all(RG.inside(p, bed) == 1 for p in pts) and RG.is_simple(pts):
                slab(buf, pts, [], z + GREEN_BASE + 200, z + GREEN_BASE + 240, "roof_paver",
                     "roof_paver")
        sb.green_done.append(g["id"])
        sb.stats["green_roofs"] = sb.stats.get("green_roofs", 0) + 1


# ---------------------------------------------------------------------------
# Roof items, huts, vents, skylights, the billboard frame crown
# ---------------------------------------------------------------------------

def _style(sb, what: str) -> str:
    era = sb.gm.get("era") or "mixed_modern"
    opts, w = SY.EQUIP_STYLES[what].get(era, SY.EQUIP_STYLES[what]["*"])
    return GN.pick(sb.gm.get("family") or sb.bid, f"equip.{what}", opts, w, "ag4.roof")


def _place(sb, family: str, p: dict, x: int, y: int, z: int, ux: float, uy: float) -> str:
    sb.parts.add(family, p, x, y, z, ux, uy)
    return PT.node_name(family, p)


def _legs(sb, rf: dict, x: int, y: int, ux: float, uy: float, w: int, d: int, z: int) -> int:
    """Dunnage under an item of w x d at (x, y) whose base is at z over a roof form: the
    frame's leg (0: none needed)."""
    lo = math.inf
    for sx in (-1, 1):
        for sy in (-1, 1):
            px = x + ux * sx * w / 2.0 - uy * sy * d / 2.0
            py = y + uy * sx * w / 2.0 + ux * sy * d / 2.0
            lo = min(lo, surface(rf, px, py))
    leg = z - lo
    if leg < LEG_MIN:
        return 0
    leg = int(math.ceil(leg / 100.0)) * 100
    # the frame 0.1 m past the item, else as big as it or smaller where its box (the
    # envelope checks an instanced part's box) would reach past the roof's edge under it
    ring = rf["ring"]
    for grow in (200, 0, -200, -400):
        fw, fd = max(w + grow, 400), max(d + grow, 400)
        hx, hy = fw / 2 + 20, fd / 2 + 20
        if all(RG.in_poly((int(round(x + ux * sx * hx - uy * sy * hy)),
                           int(round(y + uy * sx * hx + ux * sy * hy))), [ring]) == 1
               for sx in (-1, 1) for sy in (-1, 1)):
            break
    _place(sb, "dunnage", {"w": PT.q(fw), "d": PT.q(fd), "leg": leg}, x, y, z - leg, ux, uy)
    return leg


def items(sb) -> None:
    """An asset for every roof item of the brief (`sb.roof_items`: per item, its family and
    node, `merged`, or `sign` for AG8's billboards)."""
    br = sb.br
    clear = sb.clear
    out = []
    form_of_item = {}
    for ms in sb.roof_forms:
        rf = ms.get("roof")
        if rf and rf["kind"] != "flat":
            for k in rf["items"]:
                form_of_item[k] = rf
    for k, it in enumerate(br["roof_items"]):
        x, y, z = (int(round(v * 1000)) for v in it["position"])
        sa, sc, sz = (max(int(round(v * 1000)), 100) for v in it["size"])
        a = M.radians(float(it["yaw_deg"]))
        ux, uy = float(M.cos(a)), float(M.sin(a))
        kind = it["kind"]
        rec = {"kind": kind, "asset": None}
        hx = abs(ux) * sa / 2 + abs(uy) * sc / 2
        hy = abs(uy) * sa / 2 + abs(ux) * sc / 2
        room = clear.lowest(x - hx, y - hy, x + hx, y + hy, z) if clear.segs else None
        top = (room - z - 300) if room is not None else None
        rf = form_of_item.get(k)
        if kind == "billboard":
            rec["asset"] = "sign"            # AG8's billboard (frame, truss, legs)
        elif kind == "ac_unit":
            if rf is not None:
                _legs(sb, rf, x, y, ux, uy, sa, sc, z)
            p = {"w": PT.q(sa), "d": PT.q(sc), "h": PT.q(sz), "style": _style(sb, "ac")}
            rec["asset"] = _place(sb, "ac_unit", p, x, y, z, ux, uy)
        elif kind == "water_tank":
            h = PT.q(sz)
            st = _style(sb, "tank")
            if top is not None and top < h:
                h, st = PT.q(max(1200, top)), "panel"
                sb.stats["roof_items_lowered"] = sb.stats.get("roof_items_lowered", 0) + 1
            if rf is not None:
                _legs(sb, rf, x, y, ux, uy, sa, sc, z)
            p = {"r": PT.q(min(sa, sc) / 2), "h": h, "style": st}
            rec["asset"] = _place(sb, "water_tank", p, x, y, z, ux, uy)
        elif kind == "antenna":
            h = int(round(sz / 500.0)) * 500
            if top is not None and top < h:
                h = max(2000, int(top // 500) * 500)
                sb.stats["roof_items_lowered"] = sb.stats.get("roof_items_lowered", 0) + 1
            st = "lattice" if h >= 9000 else ("whip" if _u(f"{sb.bid}|{k}", "ant") < 0.6
                                               else "dish")
            if rf is not None:
                _legs(sb, rf, x, y, ux, uy, 800, 800, z)
            rec["asset"] = _place(sb, "antenna", {"h": h, "style": st}, x, y, z, ux, uy)
        elif kind in ("helipad", "av_pad"):
            p = {"s": PT.q(min(sa, sc)), "h": PT.q(sz), "kind": kind}
            rec["asset"] = _place(sb, "pad", p, x, y, z, ux, uy)
            sb.used["pads"] = True
        elif kind == "mechanical":
            h = sz
            up = RP.STACK_UP + 100
            stacks = True
            if top is not None and top < h + up:
                h = max(2500, top - up)
                if top < h + up:
                    h, stacks = max(2500, min(sz, top)), False
                sb.stats["roof_items_lowered"] = sb.stats.get("roof_items_lowered", 0) + 1
            p = {"w": PT.q(sa), "d": PT.q(sc), "h": PT.q(h)}
            if not stacks:
                p["stacks"] = 0
            rec["asset"] = _place(sb, "penthouse", p, x, y, z, ux, uy)
        else:
            # anything else M3 may put on a roof: a plain equipment casing of its size
            p = {"w": PT.q(sa), "d": PT.q(sc), "h": PT.q(sz), "style": "box"}
            rec["asset"] = _place(sb, "ac_unit", p, x, y, z, ux, uy)
        out.append(rec)
    sb.roof_items = out
    sb.stats["roof_items"] = len(out)


def _top_flat(sb) -> dict | None:
    """The highest flat roof of the building open to the sky (a mass with nothing over its
    middle), or None."""
    best = None
    for ms in sb.masses:
        if ms.get("roof") and ms["roof"]["kind"] != "flat":
            continue
        if ms["shape"] != "prism" or ms.get("screen") or SY.role_group(ms["role"]) == \
                "structure" or ms["z1"] - ms["z0"] < 1000:
            continue
        ring = RG.clean(ms["rings"][0])
        if len(ring) < 3:
            continue
        c = _centroid(ring)
        if any(o is not ms and o["z0"] >= ms["z1"] - 50 and RG.in_poly(c, o["rings"]) >= 0
               for o in sb.masses):
            continue
        if best is None or (ms["z1"], -ms["k"]) > (best["z1"], -best["k"]):
            best = ms
    return best


def _taken(sb, ms: dict) -> list[tuple]:
    """Plan boxes (x0, y0, x1, y1, mm) already used on a roof: roof items (1 m round),
    masses standing on it, green roofs, the crown mast."""
    out = []
    for it in sb.br["roof_items"]:
        x, y = int(round(it["position"][0] * 1000)), int(round(it["position"][1] * 1000))
        r = int(max(it["size"][0], it["size"][1]) * 500) + 1000
        out.append((x - r, y - r, x + r, y + r))
    for o in sb.masses:
        if o is not ms and o["z1"] > ms["z1"] + 50 and o["z0"] <= ms["z1"] + 50:
            ring = RG.clean(o["rings"][0])
            if ring:
                out.append((min(p[0] for p in ring) - 800, min(p[1] for p in ring) - 800,
                            max(p[0] for p in ring) + 800, max(p[1] for p in ring) + 800))
    for g in sb.br["green_roofs"]:
        if g.get("polygon"):
            ext = RG.mm_ring(g["polygon"]["exterior"])
            if ext:
                out.append((min(p[0] for p in ext), min(p[1] for p in ext),
                            max(p[0] for p in ext), max(p[1] for p in ext)))
    return out


def _free(box, taken) -> bool:
    x0, y0, x1, y1 = box
    return not any(x0 < b[2] and x1 > b[0] and y0 < b[3] and y1 > b[1] for b in taken)


def _spots(ring, holes, ux, uy, w, d, inset, step):
    """Candidate centers for a w x d box turned to (ux, uy) inside the ring (inset from its
    edges), on a grid of `step` along the ring's frame, in a fixed order."""
    c = _centroid(ring)
    us = [(p[0] - c[0]) * ux + (p[1] - c[1]) * uy for p in ring]
    vs = [-(p[0] - c[0]) * uy + (p[1] - c[1]) * ux for p in ring]
    out = []
    a0, a1 = min(us) + w / 2 + inset, max(us) - w / 2 - inset
    b0, b1 = min(vs) + d / 2 + inset, max(vs) - d / 2 - inset
    if a1 < a0 or b1 < b0:
        return out
    na = max(1, int((a1 - a0) // step) + 1)
    nb = max(1, int((b1 - b0) // step) + 1)
    for i in range(na):
        for j in range(nb):
            a = a0 + (a1 - a0) * (i / (na - 1) if na > 1 else 0.5)
            b = b0 + (b1 - b0) * (j / (nb - 1) if nb > 1 else 0.5)
            x, y = c[0] + ux * a - uy * b, c[1] + uy * a + ux * b
            corners = [(int(round(x + ux * sa * w / 2 - uy * sb_ * (d / 2 + inset))),
                        int(round(y + uy * sa * w / 2 + ux * sb_ * (d / 2 + inset))))
                       for sa in (-1, 1) for sb_ in (-1, 1)]
            if all(RG.in_poly(q, [ring] + holes) == 1 for q in corners):
                out.append((int(round(x)), int(round(y))))
    return out


def _bbox(x, y, ux, uy, w, d):
    hx = abs(ux) * w / 2 + abs(uy) * d / 2
    hy = abs(uy) * w / 2 + abs(ux) * d / 2
    return (x - hx, y - hy, x + hx, y + hy)


def extras(sb) -> None:
    """The access hut, vents, skylights and the billboard frame crown."""
    br = sb.br
    b = br["building"]
    if b["landmark"] or b.get("megasite_id"):
        return
    ms = _top_flat(sb)
    if ms is None:
        return
    ring = RG.clean(ms["rings"][0])
    holes = [RG.clean(h) for h in ms["rings"][1:]]
    n = len(ring)
    k = max(range(n), key=lambda i: (_unit(ring[i], ring[(i + 1) % n])[2], -i))
    ux, uy, _ = _unit(ring[k], ring[(k + 1) % n])
    taken = _taken(sb, ms)
    z = ms["z1"]
    kinds = {it["kind"] for it in br["roof_items"]}
    clear = sb.clear
    if b["floors"] >= 3 and "mechanical" not in kinds and b["type"] not in SY.SHED_TYPES:
        w, d, h = HUT
        for x, y in _spots(ring, holes, ux, uy, w, d, 900, 2500):
            bx = _bbox(x, y, ux, uy, w, d + 400)
            if not _free(bx, taken) or clear.hits(*bx, z, z + h + 700):
                continue
            _place(sb, "hut", {"w": w, "d": d, "h": h}, x, y, z, ux, uy)
            taken.append((bx[0] - 1500, bx[1] - 1500, bx[2] + 1500, bx[3] + 1500))
            sb.stats["huts"] = sb.stats.get("huts", 0) + 1
            sb.used["hut"] = True
            break
    genes = sb.gm["genes"]
    if genes.get("crown") == "billboard_frame" and "billboard" not in kinds and \
            not any(s["mount"] == "roof" for s in br["sign_slots"]) and b["height_m"] <= 50:
        a, bb, L = _unit(ring[k], ring[(k + 1) % n])
        if L >= 8000:
            w = PT.q(min(0.6 * L, 12000))
            # along the longest edge, 1.2 m in, struts inward
            mx = (ring[k][0] + ring[(k + 1) % n][0]) / 2.0
            my = (ring[k][1] + ring[(k + 1) % n][1]) / 2.0
            x, y = int(round(mx - uy * 1200)), int(round(my + ux * 1200))
            # (the part's y axis is the edge's inward normal: its struts lean in, its
            # catwalk faces out)
            bx = _bbox(x, y, ux, uy, w, 4000)
            p = {"w": w, "h": 3500, "back": 1800}
            from . import envelope as EN
            if RG.in_poly((x, y), [ring] + holes) == 1 and _free(bx, taken) and \
                    not clear.hits(*bx, z, z + 6000) and \
                    EN.fits(sb.br, "billboard_frame", p, x, y, z, ux, uy):
                _place(sb, "billboard_frame", p, x, y, z, ux, uy)
                taken.append(bx)
                sb.used["crown"] = True
                sb.stats["billboard_frames"] = sb.stats.get("billboard_frames", 0) + 1
    # vents and skylights by roof area, on a grid, in a fixed order (by hash)
    area = abs(area2(ring)) / 2.0e6
    if area < 40:
        return
    nv = min(6, int(area // 120) + 1)
    use = b["use"]
    nsk = min(4, int(area // 200)) if b["floors"] <= 6 and use in (
        "residential", "retail", "civic", "industrial", "mixed") else 0
    cand = _spots(ring, holes, ux, uy, 1200, 1200, 800, 3000)
    cand.sort(key=lambda p: _u(f"{sb.bid}|{p[0]}|{p[1]}", "vent"))
    styles = ("stack", "mushroom", "box")
    for x, y in cand:
        if nv <= 0 and nsk <= 0:
            break
        bx = _bbox(x, y, ux, uy, 1400, 1400)
        if not _free(bx, taken) or clear.hits(*bx, z, z + 800):
            continue
        if nsk > 0 and _u(f"{sb.bid}|{x}|{y}", "sky") < 0.5:
            st = "dome" if sb.gm.get("era") not in ("industrial",) else "flat"
            _place(sb, "skylight", {"w": 1800, "d": 1200, "style": st}, x, y, z, ux, uy)
            nsk -= 1
            sb.stats["skylights"] = sb.stats.get("skylights", 0) + 1
        elif nv > 0:
            st = styles[int(_u(f"{sb.bid}|{x}|{y}", "vst") * 3) % 3]
            _place(sb, "roof_vent", {"style": st}, x, y, z, ux, uy)
            nv -= 1
            sb.stats["roof_vents"] = sb.stats.get("roof_vents", 0) + 1
        else:
            continue
        taken.append((bx[0] - 400, bx[1] - 400, bx[2] + 400, bx[3] + 400))
