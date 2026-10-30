"""The street front (scope 5.1.3, 14.4: AG3): the ground band of every mass on the ground,
from its foot to its first floor line (at most `BAND_MAX`), built apart from the rest of
the shell and kept as the building's second mesh (layer 1, `<id>.front`), which Unreal
collides as drawn.

Per facade of the mass, the band's openings, each with its own height (sorted along the
facade, `GAP_MIN` apart):
- a shopfront per ground-floor unit (`frontparts.gen_shopfront`, by the unit's use), down
  to the pavement, its door at the unit's entrance;
- a door at every entrance the units do not take (`frontparts.gen_door`): a main entrance
  (one or two leaves in a recess of the genome's depth, steps up inside it, a canopy over
  it where the facade has room), a service door, a loading dock (its opening at the dock's
  height, bumpers and a seal round it) or a roll-up door, a garage mouth (deep, the dark
  garage behind), a gate; one that cannot be cut there (a thin wall, a corner) shifts along
  the facade, then into the corner piers, else hangs flush on the wall; a main entrance
  between units keeps room for its own door (the shopfronts either side stop short);
- the ground row's windows (AG1's grammar) where neither is.

A unit or entrance the model put on a wall a neighbor stands against, or on a facade too
short for its door, goes to the nearest facade of its mass that has room (`Band.rehome`, in
place of the ground windows there, `moved`), else flush on the nearest band facade of the
building (`leftovers`).

The wall round them is triangulated as a polygon per zone (`_pieces`: a lower zone under the
industrial dado line or the base strip, then the wall), the openings that reach the
pavement as notches, the rest as holes, so no T-junction is left: every facade's band has
only its corners at the band's foot and top, and every zone line is the mass's own. Each
opening has its pocket (head, jambs split at the zone line, sill unless it is a notch, the
pane at the back); the cap under the mass is notched at every opening that reaches the
pavement, so the band closes; the cap at its top is the interface with the shell above (or
the roof of a mass the band takes whole).

Doors are recorded (`doors`: id, kind, entrance or unit, walkway, position, outward normal,
size, steps) for the access check and stage 4; every band opening is recorded (`opened`,
in the brief edge's s) for the mounts check. After the bands: the hardware AG8's facade
props hang on (`hardware`), downpipes and murals on blind and fire walls (`walls`) and the
band's decals (`_decals`: cells of AG6's decal atlas, drawn by `build` as mesh decals).
"""

from __future__ import annotations

import math

from ..triangulate import TriangulationError, triangulate
from . import genome as GN
from . import parts as PT
from . import rings as RG
from . import slopes as SL
from . import systems as SY

BAND_MAX = 7500              # mm: the street front's height at most
PIER_U = 250                 # a shopfront stops this far inside its unit's ends
GAP_MIN = 60
EDGE_CLEAR = 60
INNER = ("courtyard", "atrium")  # a court's walls: no door moves there
MAIN_KEEP = 1300             # half the room a main entrance between shopfronts keeps
SHOP_MIN = 1500              # a unit narrower than this after its piers takes a door only
DOOR_SHIFT = 1200            # how far a door may move along the facade from its entrance
HEAD_GAP = 150               # wall left over every opening under the band's top
MOUNT_GAP = 50               # an opening's head under anything mounted over it
SHOP_R = {"food": 350, "bar": 250, "club": 300, "arcade": 450, "cyberware": 250,
          "clinic": 250, "pawn": 300, "convenience": 250, "laundromat": 250, "lobby": 350}
DOOR_W = {"service": 1000, "dock": 3000, "rollup": 3200, "garage": 5600, "gate": 3600}
DOOR_R = {"service": 120, "dock": 120, "rollup": 160, "garage": 1500, "gate": 200}
DOCK_Z = 1200                # a loading dock's floor over the pavement
FRAME_SLOT = {"alu": "mullion", "steel": "frame", "timber": None, "paint": None}
CLASS_DOOR_OK = ("front", "street", "alley", "plaza", "park", "open", "canal", "upper",
                 "courtyard", "atrium", "blind")


def band_top(ms: dict) -> int:
    """The street front's top on a mass on the ground: its first floor line (the whole mass
    when it has one floor), at most `BAND_MAX` over its foot."""
    n = max(int(ms.get("floors") or 0), 1)
    z0, z1 = ms["z0"], ms["z1"]
    if ms.get("f0", 0):
        return z0
    zf = z0 + (z1 - z0) // n
    if z1 - zf < 1000:
        zf = z1                  # (a sliver of a floor over it: the band takes the mass)
    return min(zf, z0 + BAND_MAX, z1)


def _u(key: str, purpose: str) -> float:
    return GN.u(key, purpose, "ag3.front")


def _pick(key, purpose, opts, weights=None):
    return GN.pick(key, purpose, opts, weights, "ag3.front")


class Op:
    """One opening of the band: a to b along the facade, lo to hi up, `depth` deep (0: a
    flush door or shopfront on the wall, no opening cut), its pane's slot."""
    __slots__ = ("a", "b", "lo", "hi", "kind", "back", "depth", "info")

    def __init__(self, a, b, lo, hi, kind, back, depth, info=None):
        self.a, self.b, self.lo, self.hi = int(a), int(b), int(lo), int(hi)
        self.kind, self.back, self.depth = kind, back, int(depth)
        self.info = info or {}


# ---------------------------------------------------------------------------
# Clearances
# ---------------------------------------------------------------------------

def _clear(fa, depth: int, end: int, pier: bool = True) -> int:
    """How far from its start (end 0) or its end (1) a pocket `depth` deep must keep (with
    `pier`, past the facade's corner pier too)."""
    from .shell import _convex, _corner_clear
    d_in, d_out = (fa.d_in, (fa.ux, fa.uy)) if end == 0 else ((fa.ux, fa.uy), fa.d_nx)
    base = (fa.c0 if end == 0 else fa.c1) if pier else EDGE_CLEAR
    return max(base, _corner_clear(d_in, d_out, depth),
               depth + EDGE_CLEAR if _convex(d_in, d_out) else 0)


def _blocked(fa, a: int, b: int, depth: int, edges) -> bool:
    """Whether another edge of the mass crosses the box behind the facade from a to b,
    `depth` deep (a sliver of solid there)."""
    ix, iy = -fa.nx * depth, -fa.ny * depth
    q0 = fa.P(a, 0)[:2]
    q1 = fa.P(b, 0)[:2]
    q2 = (int(round(q1[0] + ix)), int(round(q1[1] + iy)))
    q3 = (int(round(q0[0] + ix)), int(round(q0[1] + iy)))
    rect = [q0, q1, q2, q3]
    x0, x1 = min(p[0] for p in rect), max(p[0] for p in rect)
    y0, y1 = min(p[1] for p in rect), max(p[1] for p in rect)
    for p, q in edges:
        if (p, q) == (fa.a, fa.b):
            continue
        if max(p[0], q[0]) < x0 or min(p[0], q[0]) > x1 or max(p[1], q[1]) < y0 or \
                min(p[1], q[1]) > y1:
            continue
        for k in range(4):
            if RG.seg_hit(p, q, rect[k], rect[(k + 1) % 4]):
                return True
        if RG.inside(p, rect) == 1:
            return True
    return False


def _quad(fa, a: int, b: int, depth: int) -> list:
    """The plan of a pocket a to b along the facade, `depth` behind it."""
    o = (int(round(-fa.nx * depth)), int(round(-fa.ny * depth)))
    pa, pb = fa.P(a, 0)[:2], fa.P(b, 0)[:2]
    return [pa, pb, (pb[0] + o[0], pb[1] + o[1]), (pa[0] + o[0], pa[1] + o[1])]


def _meets(q: list, boxes: list) -> bool:
    """Whether a pocket's plan meets one already cut (two recesses either side of an
    acute corner would overlap inside the solid)."""
    for r in boxes:
        for i in range(4):
            for k in range(4):
                if RG.seg_hit(q[i], q[(i + 1) % 4], r[k], r[(k + 1) % 4]):
                    return True
        if RG.inside(q[0], r) >= 0 or RG.inside(r[0], q) >= 0:
            return True
    return False


def _fit(fa, want_a: int, want_b: int, depth: int, edges, taken, mounts, lo: int,
         hi: int, shift: int, shrink: int = 0, boxes=None, pier: bool = True):
    """(a, b, depth) of an opening wanted from want_a to want_b: moved along the facade by
    at most `shift` (or, with `shrink`, cut back to the corners' clearance but not under
    that width) to clear the corners and the openings already taken, as deep as the mass
    allows (`depth`, else the facade's reveal) and clear of the recesses `boxes` already
    cut down to the pavement on its other facades; without `pier`, into the corner piers."""
    w = want_b - want_a
    offs = [0]
    for k in range(100, shift + 1, 100):
        offs += [k, -k]
    for d in sorted({depth, min(depth, fa.reveal)}, reverse=True):
        if d <= 0:
            continue
        c0, c1 = _clear(fa, d, 0, pier), _clear(fa, d, 1, pier)
        for off in offs:
            if shrink:
                a, b = max(want_a, c0), min(want_b, fa.L - c1)
                if b - a < shrink:
                    break
            else:
                a, b = want_a + off, want_b + off
                if a < c0 or b > fa.L - c1:
                    continue
            if any(a < t.b + GAP_MIN and b > t.a - GAP_MIN for t in taken):
                continue
            if any(a < m1 and b > m0 and lo < z1 and hi > z0 for m0, m1, z0, z1 in mounts):
                continue
            if _blocked(fa, a, b, d + EDGE_CLEAR, edges):
                continue
            if boxes and _meets(_quad(fa, a - EDGE_CLEAR, b + EDGE_CLEAR, d + EDGE_CLEAR),
                                boxes):
                continue
            return a, b, d
    return None


# ---------------------------------------------------------------------------
# The band of one mass
# ---------------------------------------------------------------------------

class Band:
    def __init__(self, sb, ms: dict, g: str, wall: str, sysname, reveal: int, bay: int,
                 zb: int, ground_row, facades: list):
        self.sb, self.ms, self.g = sb, ms, g
        self.wall, self.sysname, self.reveal, self.bay = wall, sysname, reveal, bay
        self.z0, self.zb = ms["z0"], zb
        self.row = ground_row
        self.facades = facades                 # [(fa, r, i, ok)]
        self.edges = [(ring[i], ring[(i + 1) % len(ring)]) for ring in ms["rings"]
                      for i in range(len(ring)) if ring[i] != ring[(i + 1) % len(ring)]]
        self.notches: dict[tuple[int, int], list] = {}
        self.boxes: list[list] = []
        gm = sb.gm
        self.genes, self.cont = gm["genes"], gm["cont"]
        self.era = gm.get("era") or ""
        self.fr = SY.FRONT.get(self.era, SY.FRONT_DEFAULT)
        dist = sb.br.get("district") or {}
        self.danger = float(dist.get("danger") or 0.3)
        self.grime = float((sb.br["building"].get("style") or {}).get("grime", 0.4))
        self.neon = float(gm["extra"].get("neon", 0.3))
        self.zones = self._zones()

    # -- zones -----------------------------------------------------------------------------

    def _zones(self) -> list[tuple[int, int, str | None]]:
        """(za, zz, slot) up the band: the dado or base strip under the wall, as AG1's
        `_wall` draws them (the same line on every facade of the mass), else the wall."""
        sb, z0, zb = self.sb, self.z0, self.zb
        genes, cont = self.genes, self.cont
        row = self.row
        if self.sysname in SY.INDUSTRIAL and genes["dado"] != "none":
            dz = int(round(cont["dado_m"] * 1000))
            dz = min(dz, zb - z0 - 400)
            if dz >= 900 and (row is None or row[0] >= z0 + dz + 300):
                sb.used["dado"] = True
                return [(z0, z0 + dz, genes["dado"]), (z0 + dz, zb, None)]
        base = genes["base"]
        if row is not None and base != "wall" and self.wall != "structure" and \
                row[0] - z0 >= 150:
            sb.used["base"] = True
            return [(z0, row[0], base), (row[0], zb, None)]
        return [(z0, zb, None)]

    def slot(self, fa, zi: int) -> str:
        s = self.zones[zi][2]
        if s is not None:
            return s
        if self.wall == "patch_sheet":
            g = SY.role_group(self.ms["role"])
            mix = SY.PATCH_MIXES[self.genes[f"{g}.patch"]]
            return GN.pick(f"{self.sb.bid}|{self.ms['k']}|{fa.j}|{fa.a}", f"band{zi}",
                           SY.PATCH_SLOTS, mix, "ag1.shell")
        return self.wall

    # -- planning ----------------------------------------------------------------------------

    def plan(self, fa, ok: bool) -> list[Op]:
        """The band's openings on one facade (doors, shopfronts, windows), sorted."""
        sb, br = self.sb, self.sb.br
        L = fa.L
        so = fa.soff
        z0 = self.z0
        mounts = self._mounts(fa)
        taken: list[Op] = []
        units = []
        if fa.j is not None:
            for k, un in enumerate(br["units"]):
                at = un.get("at")
                if at is None or at["edge"] != fa.j or k in sb.done_units:
                    continue
                s = int(round(at["s"] * 1000)) - so
                if -500 <= s <= L + 500:
                    units.append((k, un, s))
        ents = []
        if fa.j is not None:
            # (AG5: behind a temple's colonnade the hall's walls are its depth shorter; an
            # entrance at the old corner comes onto the wall's end)
            col = int(self.ms.get("colonnade_mm", 0))
            for k, en in enumerate(br["entrances"]):
                at = en.get("at")
                if at is None or at["edge"] != fa.j or k in sb.done_ents:
                    continue
                s = int(round(at["s"] * 1000)) - so
                if -500 <= s <= L + 500:
                    ents.append((k, en, s))
                elif col and -500 - col <= s <= L + 500 + col and L > 4000:
                    ents.append((k, en, min(max(s, 2000), L - 2000)))
        # a main entrance not well inside a unit keeps room for its own door: the shopfronts
        # either side of it stop short (a lobby between the shops)
        spans = [(su - wu // 2 + PIER_U, su + wu // 2 - PIER_U) for _, un, su in units
                 for wu in (int(round(un["width_m"] * 1000)),)]
        keep = [se for _, en, se in ents if en["kind"] == "main" and
                not any(a <= se <= b for a, b in spans)]
        # shopfronts, each taking an entrance that falls inside it
        for k, un, s in units:
            w = int(round(un["width_m"] * 1000))
            use = un["use"]
            want_a, want_b = s - w // 2 + PIER_U, s + w // 2 - PIER_U
            for se in keep:
                if want_a < se + MAIN_KEEP and want_b > se - MAIN_KEEP:
                    if se < s:
                        want_a = max(want_a, se + MAIN_KEEP)
                    else:
                        want_b = min(want_b, se - MAIN_KEEP)
            inside = [(ke, en, se) for ke, en, se in ents
                      if s - w // 2 <= se <= s + w // 2]
            head = self._head(fa, want_a, want_b, mounts, "shop", un)
            # (no shopfront behind a neighbor built against the wall: its door only)
            behind = fa.cls(min(max(s, 0), L), z0 + 1200) in ("party", "hidden")
            if want_b - want_a >= SHOP_MIN and head is not None and not behind:
                got = _fit(fa, want_a, want_b, max(SHOP_R.get(use, 250), self.reveal),
                           self.edges, taken, mounts, z0, head, 0, SHOP_MIN, self.boxes)
                if got is not None:
                    a, b, d = got
                    info = {"unit": k, "use": use, "entrance_s": s, "un": un}
                    if inside:
                        ke, en, se = inside[0]
                        info.update(entrance=ke, en=en, entrance_s=se)
                        sb.done_ents.add(ke)
                        ents = [x for x in ents if x[0] != ke]
                    back = {"bar": "storefront_dark", "arcade": "void"}.get(use, "storefront")
                    taken.append(Op(a, b, z0, head, "shop", back, d, info))
                    sb.done_units.add(k)
                    continue
            # too narrow, or no room for its recess: a door at its entrance
            ents.append((None, {"kind": "unit", "unit": k, "un": un}, s))
        # doors at the entrances
        for k, en, s in sorted(ents, key=lambda t: (t[2], -1 if t[0] is None else t[0])):
            op = self._door(fa, k, en, s, taken, mounts, ok)
            if op is not None:
                taken.append(op)
                taken.sort(key=lambda o: o.a)
                if k is not None:
                    sb.done_ents.add(k)
                else:
                    sb.done_units.add(en["unit"])
                continue
            # a facade full of shopfronts: the nearest shop's door serves the entrance too
            shops = [t for t in taken if t.kind == "shop" and "entrance" not in t.info]
            if k is not None and shops:
                t = min(shops, key=lambda t: (abs((t.a + t.b) // 2 - s), t.a))
                t.info.update(entrance=k, en=en, moved=True)
                sb.done_ents.add(k)
        taken.sort(key=lambda o: o.a)
        if sb.slope is not None and z0 <= 50:
            taken = SL.adjust(self, fa, taken)      # (AG5: doors and shopfronts at grade)
        # the ground row's windows where nothing else is
        if ok and self.row is not None:
            wins = self._windows(fa, taken, mounts)
            if sb.slope is not None and z0 <= 50:
                wins = SL.windows_clear(self, fa, wins)
            for op in wins:
                taken.append(op)
        taken.sort(key=lambda o: o.a)
        for op in taken:
            if op.depth > 0 and op.lo <= z0:
                self.boxes.append(_quad(fa, op.a, op.b, op.depth))
        return taken

    def rehome(self, plans: list) -> None:
        """Entrances and units of the mass no facade took (on a wall a neighbor stands
        against, or a facade too short for their door): a door on the band's nearest facade
        that has room, in place of the ground windows there (`moved`)."""
        sb, br, k_ms = self.sb, self.sb.br, self.ms["k"]
        want = [(k, en, en["position"]) for k, en in enumerate(br["entrances"])
                if k not in sb.done_ents and (en.get("at") or {}).get("mass") == k_ms]
        want += [(None, {"kind": "unit", "unit": k, "un": un}, un["entrance"] or un["edge"][0])
                 for k, un in enumerate(br["units"])
                 if k not in sb.done_units and (un.get("at") or {}).get("mass") == k_ms]
        for k, en, pos in want:
            x, y = int(round(pos[0] * 1000)), int(round(pos[1] * 1000))
            cand = []
            for n, (fa, r, i, ops) in enumerate(plans):
                if fa.L < 1600:
                    continue
                t = int(min(max((x - fa.a[0]) * fa.ux + (y - fa.a[1]) * fa.uy, 0), fa.L))
                q = fa.P(t, 0)
                cand.append((round(math.hypot(q[0] - x, q[1] - y)), n, t))
            for _, n, t in sorted(cand)[:6]:
                fa, r, i, ops = plans[n]
                if fa.cls(t, self.z0 + 1200) in INNER:
                    continue                   # (not into a court: the street is outside)
                own = [_quad(fa, o.a, o.b, o.depth) for o in ops
                       if o.depth > 0 and o.lo <= self.z0]
                keep, self.boxes = self.boxes, [b for b in self.boxes if b not in own]
                taken = [o for o in ops if o.kind != "window"]
                op = self._door(fa, k, en, t, taken, self._mounts(fa), True)
                self.boxes = keep
                if op is None or fa.cls((op.a + op.b) // 2, self.z0 + 1200) in INNER:
                    continue                   # (nor slid along the facade into one)
                op.info["moved"] = True
                ops[:] = sorted([o for o in ops if o.kind != "window" or not (
                    o.a < op.b + GAP_MIN and o.b > op.a - GAP_MIN)] + [op], key=lambda o: o.a)
                if op.depth > 0 and op.lo <= self.z0:
                    self.boxes.append(_quad(fa, op.a, op.b, op.depth))
                if k is not None:
                    sb.done_ents.add(k)
                else:
                    sb.done_units.add(en["unit"])
                break

    def _mounts(self, fa) -> list:
        so = fa.soff
        return [(m0 - so, m1 - so, a, b) for m0, m1, a, b in
                (self.sb.mounts_raw.get(fa.j, []) if fa.j is not None else [])]

    def _head(self, fa, a: int, b: int, mounts, kind: str, un=None) -> int | None:
        """An opening's head: under the band's top and under anything mounted over it."""
        H = self.zb - self.z0
        if kind == "shop":
            fz = max(450, min(900, H // 5))
            head = self.z0 + H - fz
            if un is not None and un.get("awning_m", 0) > 0:
                head = min(head, self.z0 + 3200 - 200)
            head = min(head, self.z0 + 4800)
        else:
            head = self.zb - HEAD_GAP
        for m0, m1, za, zz in mounts:
            if m0 < b and m1 > a and za > self.z0 + 1800:
                head = min(head, za - MOUNT_GAP)
        head = min(head, self.zb - HEAD_GAP)
        if head - self.z0 < 2100:
            return None
        return head

    def _door(self, fa, k, en, s: int, taken, mounts, ok: bool) -> Op | None:
        """The door of an entrance (or of a unit too narrow for a shopfront)."""
        sb = self.sb
        bt = sb.br["building"]["type"]
        z0 = self.z0
        kind = en["kind"]
        if kind == "unit":
            dk = "unit"
        elif kind == "main" and bt == "building.yard":
            dk = "gate"
        elif kind == "loading":
            dk = "dock" if self.zb - z0 >= DOCK_Z + 3200 + HEAD_GAP and \
                _u(sb.bid, f"dock{k}") < 0.7 else "rollup"
        else:
            dk = kind
        H = self.zb - z0
        if dk in ("main", "unit"):
            big = float(sb.br["building"]["height_m"]) >= 30.0 or dk == "main" and \
                sb.br["building"]["floors"] >= 8
            w = 2000 if (dk == "main" and big) else (1800 if dk == "main" else 1100)
            if dk == "main" and self.genes["front_door"] == "panel" and not big:
                w = 1200
            hh = min(2700 if dk == "main" else 2400, H - HEAD_GAP - 50)
            d = int(round(self.cont["front_recess_m"] * 1000)) if dk == "main" else 200
            d = max(d, self.reveal)
        elif dk == "dock":
            w, hh, d = DOOR_W["dock"], 3200, DOOR_R["dock"]
        elif dk == "rollup":
            w, hh, d = DOOR_W["rollup"], min(3600, H - HEAD_GAP - 100), DOOR_R["rollup"]
        elif dk == "garage":
            w, hh, d = DOOR_W["garage"], min(2800, H - HEAD_GAP - 100), DOOR_R["garage"]
        elif dk == "gate":
            w, hh, d = DOOR_W["gate"], min(3200, H - HEAD_GAP - 100), DOOR_R["gate"]
        else:
            w, hh, d = DOOR_W["service"], min(2300, H - HEAD_GAP - 50), \
                max(DOOR_R["service"], self.reveal)
        if hh < 1950:
            hh = H - HEAD_GAP
            if hh < 1500:
                return None                # (a band too low for a door: a platform, a dock)
        lo = z0 + (DOCK_Z if dk == "dock" else 0)
        for m0, m1, za, _ in mounts:
            # (a sign or awning low over it: the door's head stops under it)
            if m0 < s + w // 2 + DOOR_SHIFT and m1 > s - w // 2 - DOOR_SHIFT and \
                    lo + 1950 + MOUNT_GAP <= za < lo + hh + MOUNT_GAP:
                hh = za - MOUNT_GAP - lo
        hi = lo + hh
        cls = fa.cls(min(max(s, 0), fa.L), z0 + 1200)
        info = {"door": dk, "entrance": k, "en": en, "entrance_s": s}
        if kind == "unit":
            info.update(unit=en["unit"], un=en["un"], use=en["un"]["use"])
            info.pop("entrance")
        if cls not in ("party", "hidden"):
            got = _fit(fa, s - w // 2, s + w // 2, d, self.edges, taken, mounts, lo, hi,
                       DOOR_SHIFT, 0, self.boxes if lo <= z0 else None)
            if got is None and dk in ("garage", "dock", "rollup", "gate", "main"):
                # a narrower door of the same kind before a flush one
                w2 = {"garage": 3000, "dock": 2400, "rollup": 2400, "gate": 2400,
                      "main": 1100}[dk]
                if w2 < w:
                    w = w2
                    got = _fit(fa, s - w // 2, s + w // 2, d, self.edges, taken, mounts, lo,
                               hi, DOOR_SHIFT, 0, self.boxes if lo <= z0 else None)
            if got is None:
                # (a short facade: into its corner piers, as far as the corner allows)
                got = _fit(fa, s - w // 2, s + w // 2, d, self.edges, taken, mounts, lo, hi,
                           DOOR_SHIFT, 0, self.boxes if lo <= z0 else None, pier=False)
            if got is not None:
                a, b, dd = got
                back = "void" if dk in ("garage", "gate") else "storefront" if dk in (
                    "main", "unit") else "structure"
                return Op(a, b, lo, hi, "door", back, dd, info)
        else:
            return None                    # (a neighbor against it: `leftovers` moves it)
        # flush: a door on the wall at the entrance (within the facade; a facade too short
        # for one leaves it to the nearest that has room, `leftovers`)
        w = min(w, 1200)
        hh = min(hh, 2300, H - HEAD_GAP)
        if fa.L < 1000 or hh < 1800:
            return None
        w = min(w, fa.L - 200)
        a = min(max(s - w // 2, 100), fa.L - w - 100)
        if any(a < t.b + 20 and a + w > t.a - 20 for t in taken):
            # (beside a shopfront or another door: on the nearer free stretch)
            for t in sorted(taken, key=lambda t: t.a):
                if a < t.b + 20 and a + w > t.a - 20:
                    a = t.b + 40
            if a + w > fa.L - 50:
                return None
        info["flush"] = True
        if dk == "dock":
            info["door"] = "rollup"
            lo = z0
        return Op(a, a + w, lo, lo + hh, "door", None, 0, info)

    def _windows(self, fa, taken, mounts) -> list[Op]:
        """The ground row's openings (AG1's bays, by the row's kind) clear of the doors,
        shopfronts and mounts."""
        from .shell import NO_WINDOW, bay_cuts, bay_openings
        sb = self.sb
        genes, cont = self.genes, self.cont
        g = self.g
        lo, hi, kind, f, full, zf = self.row
        if kind == "shop" and sb.units_by_edge.get(fa.j):
            return []
        sysname = self.sysname
        if sysname is None:
            return []
        win = genes.get(f"{g}.window")
        rhythm = genes.get(f"{g}.rhythm")
        wwr = cont.get(f"{g}.wwr", 0.4)
        open_p = cont.get(f"{g}.open_p", 0.55)
        key = f"{sb.bid}|{self.ms['k']}|{fa.j}|{fa.a}"
        cuts = bay_cuts(fa.L, fa.c0, fa.c1, self.bay, rhythm, key) if self.bay else []
        back = {"win": "glass", "shop": "storefront", "louver": "louver", "void": "void",
                "lantern": "glass", "pod": "void"}[kind]
        w_ = win
        if kind == "shop" and (win in ("sparse", "clerestory", "strip", "louver", "pod",
                                       "slot") or sysname == "shanty_patchwork"):
            w_ = "single"
        if kind == "louver" and win in ("clerestory", "strip", "sparse", "slit", "patch",
                                        "square", "pod"):
            w_ = "single"
        hi = min(hi, self.zb - HEAD_GAP)
        if hi - lo < 400:
            return []
        out = []
        zm = (lo + hi) // 2
        for jb, (b0, b1) in enumerate(cuts):
            sb.stats["bays"] += 1
            for a_, b_ in bay_openings(b0, b1, jb, len(cuts), w_, rhythm, wwr, sysname,
                                       f"{key}|{f}", open_p, self.bay):
                c = fa.cls((a_ + b_) // 2, zm)
                if c in NO_WINDOW:
                    continue
                if c == "blind":
                    if GN.u(key, f"blind{f}.{jb}", "ag1.shell") > 0.3:
                        continue
                    cw = (b_ - a_) * 3 // 10
                    a_, b_ = (a_ + b_) // 2 - cw, (a_ + b_) // 2 + cw
                if b_ - a_ < 300 or a_ < fa.c0 or b_ > fa.L - fa.c1:
                    continue
                if any(a_ < t.b + GAP_MIN and b_ > t.a - GAP_MIN for t in taken + out):
                    continue
                if any(a_ < m1 and b_ > m0 and lo < z1 and hi > z0
                       for m0, m1, z0, z1 in mounts):
                    sb.stats["mount_panels"] += 1
                    continue
                out.append(Op(a_, b_, lo, hi, "win", back, self.reveal,
                              {"jb": jb, "cuts": cuts}))
        if sysname == "spandrel_ribbon" and kind == "win":
            merged: list[Op] = []
            for op in out:
                if merged and op.a - merged[-1].b <= 260:
                    merged[-1].b = op.b
                    merged[-1].info["jb"] = -1
                else:
                    merged.append(op)
            out = merged
        return out

    # -- geometry ----------------------------------------------------------------------------

    def emit(self, fa, r: int, i: int, ops: list[Op]) -> None:
        """The facade's band: its wall pieces, pockets, parts, door records."""
        sb = self.sb
        buf = sb.buf
        pl = buf.plane((fa.nx, fa.ny, 0.0), (fa.a[0], fa.a[1], 0), (fa.ux, fa.uy, 0.0),
                       (0.0, 0.0, 1.0), fa.u0, 0.0)
        cut = [op for op in ops if op.depth > 0]
        fa.band_ops = [op for op in ops if op.depth > 0 or op.kind in ("door", "shop")]
        for zi, (za, zz, _) in enumerate(self.zones):
            slot = self.slot(fa, zi)
            for outer, holes in _pieces(fa.L, za, zz, cut):
                try:
                    tris = triangulate(outer, holes, keep_straight=True)
                except TriangulationError:
                    sb.stats["band_failures"] = sb.stats.get("band_failures", 0) + 1
                    continue
                pts2 = list(outer) + [p for h in holes for p in h]
                pts = [fa.P(s, z) for s, z in pts2]
                buf.add(slot, pl, pts, [k for t in tris for k in t])
        key = f"{sb.bid}|{self.ms['k']}|{fa.j}|{fa.a}"
        for k, op in enumerate(cut):
            self._pocket(fa, op, key, k)
            if op.lo <= self.z0:
                self.notches.setdefault((r, i), []).append(op)
        for k, op in enumerate(ops):
            pl = (op.a - (ops[k - 1].b if k else 0)) // (2 if k else 1)
            pr = ((ops[k + 1].a if k + 1 < len(ops) else fa.L) - op.b) // \
                (2 if k + 1 < len(ops) else 1)
            self._fill(fa, op, key, k, pl, pr)
            if op.depth > 0 and fa.j is not None:
                sb.opened.setdefault(fa.j, []).append(
                    (op.a + fa.soff, op.b + fa.soff, op.lo, op.hi))
        sb.stats["band_openings"] = sb.stats.get("band_openings", 0) + len(cut)

    def _pocket(self, fa, op: Op, key: str, k: int) -> None:
        """An opening's pocket: head, jambs and pane split at the zone lines it crosses, a
        sill unless it reaches the pavement (the cap is notched there instead)."""
        buf = self.sb.buf
        P = fa.P
        o = (int(round(-fa.nx * op.depth)), int(round(-fa.ny * op.depth)))

        def bk(p):
            return (p[0] + o[0], p[1] + o[1], p[2])
        sa, sb_ = op.a, op.b
        zs = [op.lo] + [za for za, _, _ in self.zones if op.lo < za < op.hi] + [op.hi]
        u = (fa.ux, fa.uy, 0.0)
        into = (-fa.nx, -fa.ny, 0.0)
        up = (0.0, 0.0, 1.0)
        us = fa.u0 + sa / 1000.0

        def rv(z):
            zi = max(n for n, (za, _, _) in enumerate(self.zones) if za <= z)
            s = self.slot(fa, zi)
            return s if not s.startswith("patch") else "patch_sheet"
        Fl1, Fr1 = P(sa, op.hi), P(sb_, op.hi)
        head = buf.plane((0.0, 0.0, -1.0), Fl1, u, into, us)
        buf.quad(rv(op.hi - 1), head, Fr1, Fl1, bk(Fl1), bk(Fr1))
        if op.lo > self.z0:
            Fl0, Fr0 = P(sa, op.lo), P(sb_, op.lo)
            sill = buf.plane((0.0, 0.0, 1.0), Fl0, u, into, us)
            buf.quad(rv(op.lo), sill, Fl0, Fr0, bk(Fr0), bk(Fl0))
        left = buf.plane(u, P(sa, op.lo), into, up, 0.0, op.lo / 1000.0)
        right = buf.plane((-fa.ux, -fa.uy, 0.0), P(sb_, op.lo), into, up, 0.0, op.lo / 1000.0)
        pane = buf.plane((fa.nx, fa.ny, 0.0), (fa.a[0] + o[0], fa.a[1] + o[1], 0),
                         (fa.ux, fa.uy, 0.0), (0.0, 0.0, 1.0), fa.u0, 0.0)
        win = int(GN.u(key, f"band{k}", "ag3.front") * 256) & 255
        span = max(op.hi - op.lo, 1)
        for za, zz in zip(zs, zs[1:]):
            l0, l1, r0, r1 = P(sa, za), P(sa, zz), P(sb_, za), P(sb_, zz)
            s = rv(za)
            buf.quad(s, left, l0, bk(l0), bk(l1), l1)
            buf.quad(s, right, r0, r1, bk(r1), bk(r0))
            v0, v1 = (za - op.lo) / span, (zz - op.lo) / span
            buf.quad(op.back, pane, bk(l0), bk(r0), bk(r1), bk(l1),
                     uv1=[(0.0, v0), (1.0, v0), (1.0, v1), (0.0, v1)], win=win)

    # -- what fills an opening ---------------------------------------------------------------

    def _fill(self, fa, op: Op, key: str, k: int, pl: int, pr: int) -> None:
        if op.kind == "shop":
            self._shopfront(fa, op, key, k)
        elif op.kind == "door":
            self._doorway(fa, op, key, k)
        else:
            row = (op.lo, op.hi) + tuple(self.row[2:])
            self.sb._fill(fa, self.ms, self.g, self.sysname, row, op.a, op.b,
                          (op.b, op.back, op.info.get("jb", -1), pl, pr), op.depth,
                          self.wall, key, 1000 + k, op.info.get("cuts", ()), {})

    def _paint(self, ukey: str) -> str:
        """A unit's own paint: mostly its era's list, now and then the building's."""
        if _u(ukey, "paint.own") < 0.3:
            return self.genes["front_paint"]
        return _pick(ukey, "paint", self.fr["paints"])

    def _shopfront(self, fa, op: Op, key: str, k: int) -> None:
        sb = self.sb
        info = op.info
        use = info["use"]
        ukey = f"{sb.bid}|u{info['unit']}"
        zp = info.get("zf", op.lo)            # (AG5: on a slope, at the ground there)
        w, h, r = op.b - op.a, op.hi - zp, op.depth
        paint = self._paint(ukey)
        frame = FRAME_SLOT[self.genes["front_frame"]] or paint
        if use in ("clinic", "cyberware"):
            frame = "paint_white" if _u(ukey, "white") < 0.8 else "mullion"
        riser_g = self.genes["front_riser"]
        rslot = {"paint": paint, "wall": self.wall if not self.wall.startswith("patch")
                 else "patch_sheet"}.get(riser_g, riser_g)
        rh = {"convenience": 200, "laundromat": 450, "lobby": 0, "arcade": 0,
              "club": 0}.get(use, PT.q(300 + 300 * _u(ukey, "riser")))
        if use in ("cyberware", "clinic"):
            rh = 450
            rslot = "lit_white"
        fw = 60 if frame == "mullion" else 80
        # the door: at the unit's entrance (the entrance itself when one falls in it), a
        # side door now and then where the counter or the window wants the middle
        dw = 1900 if use == "lobby" and w >= 4200 else (1000 if w < 3000 else 1100)
        dh = min(2350, h - fw - 250)
        mid = (op.a + op.b) // 2
        se = info["entrance_s"]
        if "entrance" not in info and use in ("food", "pawn", "laundromat", "convenience") \
                and w >= 3500:
            side = _pick(ukey, "door.side", (0, -1, 1), (0.4, 0.3, 0.3))
            se = mid + side * (w // 2 - dw // 2 - fw - 400)
        dx = min(max(se - mid, -w // 2 + fw + dw // 2 + 100), w // 2 - fw - dw // 2 - 100)
        dx = PT.q(dx)
        door = "glass"
        if use == "pawn":
            door = "barred"
        elif use in ("club", "bar") and _u(ukey, "door.solid") < 0.6:
            door = "panel"
        dslot = "door_metal" if door == "panel" and use == "club" else (
            paint if door == "panel" else frame)
        if use == "lobby" and r >= 2000 and w >= 4400:
            door, dw = "revolve", 2000
            dx = 0
        tr = 0
        if h - dh >= 450:
            tr = dh + fw
        mull = _pick(ukey, "mull", (0, 1, 2), (0.3, 0.45, 0.25)) if use not in (
            "laundromat", "lobby") else (0 if use == "laundromat" else 1)
        p = {"use": use, "w": PT.q(w), "h": PT.q(h), "r": r, "fw": fw, "frame": frame,
             "riser": rh, "rslot": rslot, "dx": dx, "dw": dw, "dh": PT.q(dh), "door": door,
             "dslot": dslot, "mull": mull, "tr": PT.q(tr)}
        dang = self.danger
        shut_p = self.cont["front_shutter"] * (0.6 + dang)
        if use == "pawn" or (use in ("convenience", "food", "cyberware", "arcade") and
                             _u(ukey, "shutter") < shut_p):
            p["shutter"] = "half" if use == "pawn" else ("box" if use != "arcade" or
                                                       _u(ukey, "half") < 0.5 else "half")
        if use == "pawn" or (use in ("convenience", "cyberware", "laundromat") and
                             _u(ukey, "grille") < 0.6 * dang):
            p["grille"] = 1
        if use == "food" and r >= 300:
            p["counter"] = 1 if dx >= 0 else 2
        if use == "bar":
            p["neon"] = f"neon_{_pick(ukey, 'neon', SY.NEONS)}"
        if use == "club":
            p["panel"] = "club"
            p["neon"] = f"neon_{_pick(ukey, 'neon', SY.NEONS)}"
        if use == "arcade":
            p["screens"] = 3
            p["screen"] = _pick(ukey, "screen", sorted(SY.SCREENS))
        if use in ("cyberware", "clinic"):
            p["lightbox"] = 1
        if use == "clinic":
            p["frost"] = PT.q(rh + (h - rh) * 6 // 10)
        if use == "convenience":
            posters = []
            n = int(1 + 3 * _u(ukey, "posters"))
            for j in range(n):
                px = PT.q(-w // 2 + 300 + (w - 600) * _u(ukey, f"px{j}"))
                if abs(px - dx) < dw // 2 + 400:
                    continue
                pw, ph = PT.q(500 + 400 * _u(ukey, f"pw{j}")), PT.q(700 + 400 * _u(ukey, f"ph{j}"))
                posters.append((px, PT.q(rh + 400), pw, ph,
                                _pick(ukey, f"poster{j}", sorted(SY.POSTERS))))
            p["posters"] = tuple(posters)
        if self.genes["front_fascia"] == "plate" and self.zb - op.hi >= 350:
            fz = PT.q(min(self.zb - op.hi - 140, 900))
            p.update(fz=fz, fx=min(PIER_U - 60, 180), fd=40,
                     fslot="fascia" if _u(ukey, "fascia.trim") < 0.4 else paint)
        if use == "lobby" and r < 2000:
            p["door"] = "glass"
        sb.parts.on(fa, "shopfront", p, mid, zp)
        sb.used["front"]["shops"] = True
        sb.stats["storefronts"] += 1
        self._record_door(fa, op, mid + dx, dw, dh, info, kind="shop")
        if use == "club" and not info["un"].get("awning_m"):
            self._club_extras(fa, op, mid + dx, dw, ukey)

    def _club_extras(self, fa, op: Op, sd: int, dw: int, ukey: str) -> None:
        """A club's entrance canopy (3 m up at least, where the facade has room) and a
        queue rail beside its door on a street or avenue sidewalk."""
        sb = self.sb
        if self.zb - self.z0 >= 3500 and fa.room(sd, 3200, 1400, 1400) >= 900:
            L = PT.q(dw + 1600)
            if sd - L // 2 > 100 and sd + L // 2 < fa.L - 100 and \
                    not self._mounted(fa, sd - L // 2, sd + L // 2, 2800, 3600):
                d = PT.q(min(fa.room(sd, 3200, 1400, 1400), 1400))
                sb.parts.on(fa, "canopy", {"style": "entrance", "L": L, "d": d, "t": 260},
                            sd, max(self.z0 + 3000, op.hi + 60))
        if fa.room(sd, 1000, 1, 0) > 0 and _u(ukey, "rail") < 0.7:
            L = PT.q(min(4800, op.b - sd - dw // 2 - 200))
            if L >= 1200:
                sb.parts.on(fa, "rail", {"L": L, "out": 600}, sd + dw // 2 + 200, self.z0)

    def _mounted(self, fa, a, b, za, zz) -> bool:
        so = fa.soff
        for m0, m1, z0, z1 in self.sb.mounts_raw.get(fa.j, []) if fa.j is not None else []:
            if m0 - so < b and m1 - so > a and z0 < zz and z1 > za:
                return True
        return False

    def _doorway(self, fa, op: Op, key: str, k: int) -> None:
        sb = self.sb
        info = op.info
        dk = info["door"]
        zp = info.get("zf", op.lo)            # (AG5: on a slope, at the ground there)
        w, h, r = op.b - op.a, op.hi - zp, op.depth
        flush = bool(info.get("flush"))
        mid = (op.a + op.b) // 2
        p = {"w": PT.q(w), "h": PT.q(h), "r": r}
        if flush:
            p["flush"] = 1
        lift = 0
        if dk in ("main", "unit"):
            steps = int(self.genes["front_steps"]) if dk == "main" else 0
            if r < 300 * steps + 300 or flush:
                steps = 0
            style = self.genes["front_door"] if dk == "main" else "glass"
            lw = 2 if w >= 1500 else 1
            dh = PT.q(min(2400, h - 70 - (300 if h >= 2900 else 0)))
            slot = "door_wood" if style == "panel" and self.era in ("heritage",
                                                                    "suburban_modern") \
                else ("door_metal" if style == "panel" else "frame")
            p.update(kind="main", steps=steps, sh=150, sd=300, dh=dh, style=style,
                     leaves=lw, slot=slot)
            lift = 150 * steps
            sb.used["front"]["main"] = sb.used["front"].get("main") or dk == "main"
        elif dk == "service":
            p.update(kind="service", slot="door_metal")
        elif dk in ("dock", "rollup"):
            p.update(kind=dk)
        elif dk == "garage":
            p.update(kind="garage")
        elif dk == "gate":
            p.update(kind="gate", slot="door_metal")
        if flush:
            p["r"] = 0
        sb.parts.on(fa, "door", p, mid, zp)
        dh = p.get("dh", h)
        self._record_door(fa, op, mid, w, dh, info, kind=dk, lift=lift)
        if dk == "main" and not flush:
            self._entrance_canopy(fa, op, mid)

    def _entrance_canopy(self, fa, op: Op, mid: int) -> None:
        """A canopy over a main entrance, 3 m up at least, as deep as the facade allows,
        where no awning, sign or podium canopy is near."""
        sb = self.sb
        if getattr(fa, "podium", False) or self.zb - self.z0 < 3500:
            return
        z = max(self.z0 + 3000, op.hi + 100)
        if z + 300 > self.zb + 600:
            return
        L = PT.q(op.b - op.a + 1200)
        if mid - L // 2 < 100 or mid + L // 2 > fa.L - 100:
            return
        room = fa.room(mid, z, 1500, 1800)
        if room < 900 or self._mounted(fa, mid - L // 2, mid + L // 2, z - 600, z + 900):
            return
        if _u(f"{sb.bid}|{fa.j}|{op.a}", "canopy") > 0.65:
            return
        sb.parts.on(fa, "canopy", {"style": "entrance", "L": L, "d": PT.q(min(room, 1600)),
                                   "t": 300}, mid, z)
        if "canopy.entrance" not in sb.used["articulation"]:
            sb.used["articulation"].append("canopy.entrance")

    def _record_door(self, fa, op: Op, s: int, w: int, h: int, info: dict, kind: str,
                     lift: int = 0) -> None:
        sb = self.sb
        en = info.get("en") if "entrance" in info else None
        ids = []
        if "entrance" in info:
            ids.append(f"e{info['entrance']}")
        if "unit" in info:
            ids.append(f"u{info['unit']}")
        zp = info.get("zf", op.lo)
        x, y, _ = fa.P(s, zp)
        rec = {"id": f"{sb.bid}.door.{ids[0]}", "kind": kind if kind != "unit" else "shop",
               "entrance": info.get("entrance"), "unit": info.get("unit"),
               "use": (info.get("un") or {}).get("use"),
               "walkway_id": (en or {}).get("walkway_id"),
               "pos": [x, y, zp + lift], "normal": [round(fa.nx, 6), round(fa.ny, 6)],
               "w": int(w), "h": int(h), "depth": op.depth, "steps": lift // 150,
               "flush": bool(info.get("flush")), "moved": bool(info.get("moved")),
               "edge": fa.j,
               "s": int(s + fa.soff), "class": fa.cls(min(max(s, 0), fa.L),
                                                     op.lo + 1200)}
        if self.ms.get("colonnade_mm"):
            rec["under"] = int(self.ms["colonnade_mm"])    # (AG5: behind a colonnade)
        sb.doors.append(rec)


# ---------------------------------------------------------------------------
# Wall pieces: a zone of the facade minus its openings
# ---------------------------------------------------------------------------

def _pieces(L: int, za: int, zz: int, ops: list[Op]) -> list[tuple[list, list]]:
    """The wall of one zone (0 to L along the facade, za to zz up) without the openings:
    (outer ring, holes) in (s, z), counterclockwise seen from outside. An opening through
    the whole zone splits it; one reaching its foot or top notches it; the rest are holes.
    Its foot and top carry a vertex wherever an opening of the zone below or above meets
    the line, so the zones weld."""
    out = []
    start = 0
    bottom: list[tuple] = []
    top: list[tuple] = []
    holes: list[list] = []
    xb = sorted({x for op in ops if op.hi == za or op.lo == za for x in (op.a, op.b)})
    xt = sorted({x for op in ops if op.lo == zz or op.hi == zz for x in (op.a, op.b)})
    for op in ops:
        lo, hi = max(op.lo, za), min(op.hi, zz)
        if lo >= hi:
            continue
        if lo <= za and hi >= zz:
            out.append(_piece(start, op.a, za, zz, bottom, top, holes, xb, xt))
            start, bottom, top, holes = op.b, [], [], []
        elif lo <= za:
            bottom.append((op.a, op.b, hi))
        elif hi >= zz:
            top.append((op.a, op.b, lo))
        else:
            holes.append([(op.a, lo), (op.a, hi), (op.b, hi), (op.b, lo)])
    out.append(_piece(start, L, za, zz, bottom, top, holes, xb, xt))
    return [p for p in out if p is not None]


def _piece(s0: int, s1: int, za: int, zz: int, bottom, top, holes, xb=(), xt=()):
    if s1 - s0 <= 0:
        return None
    ring = [(s0, za)]
    x = s0
    for a, b, h in bottom:
        ring += [(v, za) for v in xb if x < v < a]
        ring += [(a, za), (a, h), (b, h), (b, za)]
        x = b
    ring += [(v, za) for v in xb if x < v < s1]
    ring += [(s1, za), (s1, zz)]
    x = s1
    for a, b, lo in reversed(top):
        ring += [(v, zz) for v in reversed(xt) if b < v < x]
        ring += [(b, zz), (b, lo), (a, lo), (a, zz)]
        x = a
    ring += [(v, zz) for v in reversed(xt) if s0 < v < x]
    ring.append((s0, zz))
    ring = RG.clean(ring)
    return ring, holes


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------

def caps(band: Band, roof: bool) -> None:
    """The cap under the mass (notched at every opening that reaches the pavement) and the
    one at the band's top (the interface with the shell above, or the mass's roof)."""
    sb, ms = band.sb, band.ms
    buf = sb.buf
    rings = []
    for r, ring in enumerate(ms["rings"]):
        n = len(ring)
        pts = []
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            pts.append(a)
            if a == b:
                continue
            ops = band.notches.get((r, i))
            if not ops:
                continue
            fa = next(f for f, rr, ii, _ in band.facades if rr == r and ii == i)
            for op in sorted(ops, key=lambda o: o.a):
                o = (int(round(-fa.nx * op.depth)), int(round(-fa.ny * op.depth)))
                pa, pb = fa.P(op.a, 0)[:2], fa.P(op.b, 0)[:2]
                pts += [pa, (pa[0] + o[0], pa[1] + o[1]), (pb[0] + o[0], pb[1] + o[1]), pb]
        rings.append(RG.clean(pts))
    plain = [RG.clean(r) for r in ms["rings"]]
    z0, zb = band.z0, band.zb
    bot = buf.plane((0.0, 0.0, -1.0), (0, 0, z0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0))
    top = buf.plane((0.0, 0.0, 1.0), (0, 0, zb), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    for rr, pl, z, flip, slot in ((rings, bot, z0, True, "structure"),
                                  (plain, top, zb, False, "roof" if roof else "structure")):
        outer, holes = rr[0], [h for h in rr[1:] if len(h) >= 3]
        try:
            tris = triangulate(outer, holes, keep_straight=True)
        except TriangulationError:
            sb.stats["cap_failures"] = sb.stats.get("cap_failures", 0) + 1
            continue
        pts = list(outer) + [p for h in holes for p in h]
        idx = [k for t in tris for k in ((t[0], t[2], t[1]) if flip else t)]
        buf.add(slot, pl, [(p[0], p[1], z) for p in pts], idx)


# ---------------------------------------------------------------------------
# After the masses: leftover doors, mount hardware, blind and fire walls, checks
# ---------------------------------------------------------------------------

def _facade_at(sb, j, s: int, z: int):
    """(facade, its mass) of brief edge j holding s (mm along the edge) at height z, else
    the edge's nearest facade within 1.5 m of s."""
    best = None
    for fa, ms in sb.all_facades:
        if fa.j != j or not ms["z0"] - 500 <= z <= ms["z1"] + 500:
            continue
        if fa.soff - 1 <= s <= fa.soff + fa.L + 1:
            return fa, ms
        d = min(abs(s - fa.soff), abs(s - fa.soff - fa.L))
        if best is None or d < best[0]:
            best = (d, fa, ms)
    # (an edge tidying or an articulation shortened: its nearest facade within 1.5 m)
    if best is not None and best[0] <= 1500:
        return best[1], best[2]
    return None


def _open_at(sb, j, s0: int, s1: int, z0: int, z1: int) -> bool:
    return any(a < s1 and b > s0 and lo < z1 and hi > z0 for a, b, lo, hi in sb.opened.get(j, ()))


def leftovers(sb) -> None:
    """A flush door for every entrance and unit no band took (its facade cut away by an
    articulation, or on a mass without a front): on the band facade nearest to it."""
    br = sb.br
    want = [("e", k, en, en["position"]) for k, en in enumerate(br["entrances"])
            if k not in sb.done_ents]
    want += [("u", k, un, un["entrance"] or un["edge"][0]) for k, un in enumerate(br["units"])
             if k not in sb.done_units]
    for tag, k, item, pos in want:
        x, y = int(round(pos[0] * 1000)), int(round(pos[1] * 1000))
        best = None
        for fa, ms in sb.band_facades:
            if fa.L < 1600:
                continue
            hh = min(2200, FR_band(ms) - ms["z0"] - HEAD_GAP)
            ax, ay = fa.a
            t = ((x - ax) * fa.ux + (y - ay) * fa.uy)
            t = _free_spot(sb, fa, int(min(max(t, 800), fa.L - 800)), 1000, ms["z0"], hh)
            if t is None:
                continue
            px, py = ax + fa.ux * t, ay + fa.uy * t
            d = math.hypot(px - x, py - y)
            # (a wall a door fits under and open first: a door against a neighbor, into a
            # court or on a low platform only where there is no other)
            wall = fa.cls(t, ms["z0"] + 1200) in ("party", "hidden", "blind") + INNER
            key = (hh < 1800, wall, round(d), fa.j if fa.j is not None else -1, t)
            if best is None or key < best[0]:
                best = (key, fa, ms, t)
        if best is None:
            continue
        _, fa, ms, t = best
        w = 1000
        hh = min(2200, FR_band(ms) - ms["z0"] - HEAD_GAP)
        p = {"kind": "service" if tag == "e" and item["kind"] != "main" else "main",
             "w": w, "h": PT.q(hh), "r": 0, "flush": 1, "steps": 0, "sh": 150, "sd": 300,
             "dh": PT.q(hh - 70), "style": "panel", "leaves": 1, "slot": "door_metal"}
        if p["kind"] == "service":
            p = {"kind": "service", "w": w, "h": PT.q(hh), "r": 0, "flush": 1,
                 "slot": "door_metal"}
        sb.parts.on(fa, "door", p, t, ms["z0"])
        x0, y0, _ = fa.P(t, ms["z0"])
        sb.doors.append({
            "id": f"{sb.bid}.door.{tag}{k}", "kind": item.get("kind", "shop")
            if tag == "e" else "shop", "entrance": k if tag == "e" else None,
            "unit": k if tag == "u" else None, "use": item.get("use"),
            "walkway_id": item.get("walkway_id") if tag == "e" else None,
            "pos": [x0, y0, ms["z0"]], "normal": [round(fa.nx, 6), round(fa.ny, 6)],
            "w": w, "h": int(hh), "depth": 0, "steps": 0, "flush": True, "edge": fa.j,
            "s": int(t + fa.soff), "class": fa.cls(t, ms["z0"] + 1200), "moved": True})
        (sb.done_ents if tag == "e" else sb.done_units).add(k)
        sb.stats["doors_moved"] = sb.stats.get("doors_moved", 0) + 1


def _free_spot(sb, fa, t: int, w: int, z0: int, hh: int) -> int | None:
    """The nearest point to t (in steps of 0.2 m, at most 6 m off) where a flush door w
    wide is clear of the facade's openings and doors, 0.8 m in from its ends."""
    if fa.j is None:
        return t if not any(d["edge"] is None and abs(d["s"] - t) < w + 200
                            for d in sb.doors) else None
    for k in range(61):
        for u in ((t + 200 * (k // 2 + 1)) if k % 2 else (t - 200 * (k // 2)),):
            if u < 800 or u > fa.L - 800:
                continue
            s0, s1 = u - w // 2 - 100 + fa.soff, u + w // 2 + 100 + fa.soff
            if _open_at(sb, fa.j, s0, s1, z0, z0 + hh):
                continue
            if any(d["edge"] == fa.j and abs(d["s"] - u - fa.soff) < w + 200
                   for d in sb.doors):
                continue
            return u
    return None


def FR_band(ms) -> int:
    return ms.get("band", band_top(ms))


def hardware(sb) -> None:
    """What AG8's facade props hang on: a plate behind every wall light and cable end on
    the wall, a trellis under facade greenery, scaffold ties on the piers behind
    scaffolding."""
    br = sb.br
    for p in br["props"]:
        at = p.get("at")
        # (a scaffold stands its depth off the wall, about 0.8 m)
        if at is None or not p["on_wall"] or \
                at["d"] > (1.5 if p["kind"] == "scaffolding" else 0.5):
            continue
        kind = p["kind"]
        if kind not in ("wall_light", "overhead_cable", "scaffolding"):
            continue
        s = int(round(at["s"] * 1000))
        z = int(round(p["position"][2] * 1000))
        if kind == "scaffolding":
            _ties(sb, p, at)
            continue
        got = _facade_at(sb, at["edge"], s, z)
        if got is None:
            continue
        fa, ms = got
        w, h = (300, 300) if kind == "wall_light" else (200, 200)
        if fa.L < 3 * w:
            continue
        sl = min(max(s - fa.soff, w), fa.L - w)
        if _open_at(sb, at["edge"], s - w // 2, s + w // 2, z - h, z + h):
            continue
        sb.parts.on(fa, "mount", {"style": "plate", "w": w, "h": h}, sl, z - h // 2)
        sb.stats["mount_plates"] = sb.stats.get("mount_plates", 0) + 1
    for pl in br["plants"]:
        at = pl.get("at")
        if at is None or at["d"] > 0.5 or not pl["type"].endswith("facade_greenery"):
            continue
        s = int(round(at["s"] * 1000))
        z = int(round(pl["position"][2] * 1000))
        got = _facade_at(sb, at["edge"], s, z)
        if got is None:
            continue
        fa, ms = got
        L = int(round(float((pl.get("attrs") or {}).get("length_m", 1.5)) * 1000))
        w = PT.q(min(max(L, 800), 6000, fa.L - 200))
        h = PT.q(min(max(pl["height_m"] * 1000, 1000), ms["z1"] - z - 100))
        if h < 800 or w < 600:
            continue
        sl = min(max(s - fa.soff, w // 2 + 50), fa.L - w // 2 - 50)
        if _open_at(sb, at["edge"], s - w // 2, s + w // 2, z, z + h):
            continue
        sb.parts.on(fa, "mount", {"style": "trellis", "w": w, "h": h}, sl, z)
        sb.stats["trellises"] = sb.stats.get("trellises", 0) + 1


def _ties(sb, p, at) -> None:
    """Ties on the piers behind a scaffold: every 3 m along it, every other floor."""
    s_mid = int(round(at["s"] * 1000))
    L = int(round(p["scale"][0] * 1000))
    H = int(round(p["scale"][2] * 1000))
    fh = int(round(float(sb.br["building"]["floor_grid"]["floor_height_m"]) * 1000)) or 3500
    for k in range(max(1, L // 3000)):
        s = s_mid - L // 2 + 1500 + k * 3000
        for z in range(fh + 1000, H, 2 * fh):
            got = _facade_at(sb, at["edge"], s, z)
            if got is None:
                continue
            fa, ms = got
            if fa.L < 800:
                continue
            for ds in (0, 400, -400, 800, -800):
                if not _open_at(sb, at["edge"], s + ds - 150, s + ds + 150, z - 150, z + 150):
                    sl = min(max(s + ds - fa.soff, 200), fa.L - 200)
                    sb.parts.on(fa, "mount", {"style": "tie", "w": 200, "h": 200}, sl, z - 100)
                    sb.stats["scaffold_ties"] = sb.stats.get("scaffold_ties", 0) + 1
                    break


def walls(sb) -> None:
    """Blind and fire walls (scope 5.1.2): a downpipe down a blind or fire wall on the
    ground, a mural painted on a fire wall now and then, graffiti on blank stretches of the
    band by grime and danger."""
    br = sb.br
    dist = br.get("district") or {}
    danger = float(dist.get("danger") or 0.3)
    grime = float((br["building"].get("style") or {}).get("grime", 0.4))
    neon = float(sb.gm["extra"].get("neon", 0.3))
    for n, (fa, ms) in enumerate(sb.all_facades):
        if fa.j is None or fa.L < 3000:
            continue
        key = f"{sb.bid}|{ms['k']}|{fa.j}|{fa.a}"
        cls_area: dict[str, float] = {}
        for r in fa.regions:
            a = (r["s"][1] - r["s"][0]) * (r["z"][1] - r["z"][0])
            cls_area[r["class"]] = cls_area.get(r["class"], 0.0) + a
        tot = sum(cls_area.values()) or 1.0
        blank = (cls_area.get("blind", 0.0) + cls_area.get("firewall", 0.0)) / tot
        # a downpipe on a blind or fire wall standing on the ground
        if ms["z0"] <= sb.ground + 50 and blank >= 0.5 and fa.L >= 5000 and \
                ms["z1"] - ms["z0"] >= 6000:
            for sl in (fa.c0 + 250, fa.L - fa.c1 - 250, fa.L // 2):
                s = sl + fa.soff
                if sl < 200 or sl > fa.L - 200:
                    continue
                if not _open_at(sb, fa.j, s - 120, s + 120, ms["z0"], ms["z1"]):
                    sb.parts.on(fa, "pipe", {"h": PT.q(ms["z1"] - ms["z0"] - 300)}, sl,
                                ms["z0"])
                    sb.stats["pipes"] = sb.stats.get("pipes", 0) + 1
                    break
        # murals on fire walls
        for r in fa.regions:
            if r["class"] != "firewall":
                continue
            s0, s1 = int(r["s"][0] * 1000) - fa.soff, int(r["s"][1] * 1000) - fa.soff
            z0, z1 = int(r["z"][0] * 1000), min(int(r["z"][1] * 1000), ms["z1"])
            s0, s1 = max(s0, fa.c0), min(s1, fa.L - fa.c1)
            w, h = s1 - s0 - 1200, z1 - z0 - 1200
            if w < 5000 or h < 5000 or GN.u(key, f"mural{r['s'][0]}", "ag3.front") > \
                    0.2 + 0.5 * neon:
                continue
            w, h = PT.q(min(w, 18000)), PT.q(min(h, 12000))
            sm = (s0 + s1) // 2
            zm = z0 + 600 + (z1 - z0 - 1200 - h) // 2
            if _open_at(sb, fa.j, sm - w // 2 + fa.soff, sm + w // 2 + fa.soff, zm, zm + h):
                continue
            slot = GN.pick(key, f"mural.slot{r['s'][0]}", sorted(SY.MURALS), None,
                           "ag3.front")
            sb.parts.on(fa, "surface", {"style": "mural", "w": w, "h": h, "slot": slot}, sm,
                        zm)
            sb.stats["murals"] = sb.stats.get("murals", 0) + 1
        # decals on the street band (AG6's atlas): grime, leaks, rust, graffiti, posters,
        # cracks and moss
        if ms["z0"] <= sb.ground + 50 and "band" in ms:
            _decals(sb, fa, ms, key, grime, danger, neon)


DECALS_MAX = 14              # a building's decals at most
GREEN = ("moss",)


def _free(sb, fa, ms, z0: int, z1: int, pad: int = 150) -> list[tuple[int, int]]:
    """Stretches of a facade (its own s) with no opening cut between z0 and z1."""
    spans = sorted((a - fa.soff, b - fa.soff) for a, b, lo, hi in sb.opened.get(fa.j, ())
                   if lo < z1 and hi > z0)
    out, x = [], fa.c0 + pad
    for a, b in spans + [(fa.L - fa.c1 - pad, fa.L)]:
        if a - x >= 600:
            out.append((x, a - pad))
        x = max(x, b + pad)
    return out


def _decal(sb, fa, ms, cell: str, s: int, z: int, w: int, h: int) -> None:
    if len(sb.decals) >= DECALS_MAX:
        return
    x, y, _ = fa.P(s, ms["z0"])
    sb.decals.append({"cell": cell, "pos": [x, y, z], "normal": [round(fa.nx, 6),
                                                                  round(fa.ny, 6)],
                      "w": PT.q(w), "h": PT.q(h)})


def _decals(sb, fa, ms, key: str, grime: float, danger: float, neon: float) -> None:
    """Decals on a facade's street band, by its class, the building's wear and grime and
    the district's danger: grime at the wall's foot, leaks under the band's windows, rust
    beside its metal doors, graffiti on blank stretches, posters on the piers between
    shopfronts, cracks and moss on blind walls."""
    zb = ms["band"]
    z0 = ms["z0"]
    wear = float(sb.gm["cont"]["wear"])
    green = float((sb.br.get("district") or {}).get("greenery") or 0.3)
    cls = fa.cls(fa.L // 2, z0 + 1200)
    if cls in ("party", "hidden"):
        return

    def u(p):
        return GN.u(key, p, "ag3.decal")
    # grime along the foot of the wall
    for m, (a, b) in enumerate(_free(sb, fa, ms, z0, z0 + 1200)[:3]):
        if u(f"grime{m}") > 0.25 + 0.6 * wear:
            continue
        w = min(b - a, int(1500 + 1500 * u(f"gw{m}")))
        h = int(700 + 600 * u(f"gh{m}"))
        sc = a + (b - a - w) // 2 + w // 2
        _decal(sb, fa, ms, "grime_ground", sc, z0 + h // 2, w, h)
    # leaks under the band's windows, rust beside metal doors
    for a, b, lo, hi in sb.opened.get(fa.j, ()):
        sa, sbb = a - fa.soff, b - fa.soff
        if not (0 <= sa and sbb <= fa.L) or hi > zb:
            continue
        if lo >= z0 + 1500 and u(f"leak{a}") < 0.15 + 0.45 * wear:
            h = min(int(800 + 700 * u(f"lh{a}")), lo - z0 - 300)
            if h >= 500:
                _decal(sb, fa, ms, "leaks_a" if u(f"lk{a}") < 0.5 else "leaks_b",
                       (sa + sbb) // 2, lo - h // 2 - 20, int((sbb - sa) * 0.8), h)
    for d in sb.doors:
        if d["edge"] != fa.j or d["kind"] not in ("service", "dock", "rollup", "garage") or \
                d["flush"]:
            continue
        if u(f"rust{d['id']}") < 0.2 + 0.6 * grime:
            s = d["s"] - fa.soff + d["w"] // 2 + 300
            if s + 300 < fa.L - fa.c1:
                _decal(sb, fa, ms, "rust_drip" if u(f"rk{d['id']}") < 0.5 else "rust_bleed",
                       s, z0 + 900, 500, 1500)
    # graffiti on blank stretches, the more where it is grimy and dangerous
    k_cls = 1.6 if cls in ("alley", "blind", "firewall") else 0.6
    if u("graffiti") < grime * (0.3 + danger) * k_cls:
        for m, (a, b) in enumerate(_free(sb, fa, ms, z0, min(zb, z0 + 2800))[:2]):
            if b - a < 2000:
                continue
            gw = int(min(b - a - 200, 1500 + 2500 * u(f"gw{m}")))
            gh = int(min(900 + 1100 * u(f"gh{m}"), zb - z0 - 700))
            cell = ("graffiti_a", "graffiti_b", "graffiti_c")[int(3 * u(f"gc{m}")) % 3]
            _decal(sb, fa, ms, cell, (a + b) // 2, z0 + 300 + gh // 2, gw, gh)
            sb.stats["graffiti"] = sb.stats.get("graffiti", 0) + 1
    # posters and stickers on the piers between shopfronts
    shops = sorted((a - fa.soff, b - fa.soff) for a, b, lo, hi in sb.opened.get(fa.j, ())
                   if lo <= z0 and hi > z0 + 2000)
    for m in range(len(shops) - 1):
        gap = shops[m + 1][0] - shops[m][1]
        if 380 <= gap <= 2400 and u(f"post{m}") < 0.2 + 0.4 * neon + 0.3 * grime:
            cell = ("poster_a", "poster_b", "poster_c", "stickers")[int(4 * u(f"pc{m}")) % 4]
            pw = min(gap - 120, 600)
            _decal(sb, fa, ms, cell, (shops[m][1] + shops[m + 1][0]) // 2,
                   z0 + 1500, pw, int(pw * 1.4))
    # cracks and moss on blind walls at street level
    if cls in ("blind", "firewall", "alley"):
        for m, (a, b) in enumerate(_free(sb, fa, ms, z0, min(zb, z0 + 2500))[:2]):
            if u(f"crack{m}") < 0.3 + 0.4 * wear and b - a >= 1200:
                _decal(sb, fa, ms, "cracks_a" if u(f"ck{m}") < 0.5 else "cracks_b",
                       a + (b - a) // 3, z0 + 1400, 1000, 1000)
            if u(f"moss{m}") < green * 0.8 and b - a >= 1500:
                _decal(sb, fa, ms, "moss", b - (b - a) // 3, z0 + 450, 1300, 900)


MOUNT_KINDS = ("ac_unit", "wall_light", "sign", "awning", "overhead_cable")


def mount_check(sb) -> dict:
    """Every mount on a panel or pier, never on glass (scope 9): each sign slot on a facade,
    each mounted prop on the wall (`on_wall`) and each facade plant, at its point (s, z) on
    its brief edge, outside every opening cut there. A mount on a stretch of its edge the
    shell tidied away (a spike of the ring, all of the edge or all but a stub of it) or over
    or under every wall of its edge (a shop sign over a low building under an M14 deck, a
    street's sign under a building on the deck) is counted apart (`tidied`, `off`), and so
    is one in a skybridge's landing door (AG4: M6 does not know where the bridges land;
    `in_landing`)."""
    br = sb.br
    items = []
    for sl in br["sign_slots"]:
        if sl["mount"] == "roof" or sl.get("at") is None or sl["at"]["d"] > 0.5:
            continue
        items.append(("sign_slot", sl["id"], sl["at"], sl["position"][2]))
    for p in br["props"]:
        at = p.get("at")
        if p["kind"] in MOUNT_KINDS and p["on_wall"] and at is not None and at["d"] <= 0.5:
            items.append((p["kind"], p["id"], at, p["position"][2]))
    for pl in br["plants"]:
        at = pl.get("at")
        if at is not None and at["d"] <= 0.5 and pl["type"].endswith("facade_greenery"):
            items.append(("greenery", pl["id"], at, pl["position"][2] + 0.5))
    bad, nowall, tidied, off, landing = [], 0, 0, 0, 0
    doors: dict[int, list] = {}
    for sk in br["skybridges"]:
        ld = sb.landed.get(sk["id"])
        if ld and sk.get("at") is not None:
            doors.setdefault(sk["at"]["edge"], []).append(ld)
    span: dict[int, tuple[int, int]] = {}
    for fa, ms in sb.all_facades:
        lo, hi = span.get(fa.j, (ms["z0"], ms["z1"]))
        span[fa.j] = (min(lo, ms["z0"]), max(hi, ms["z1"]))
    for kind, iid, at, z in items:
        s = int(round(at["s"] * 1000))
        zz = int(round(z * 1000))
        if at["edge"] not in span:
            tidied += 1                     # (a spike of the ring: no wall stands there)
            continue
        lo, hi = span[at["edge"]]
        if not lo - 500 <= zz <= hi + 500:
            off += 1                        # (over or under every wall of its edge)
            continue
        if _facade_at(sb, at["edge"], s, zz) is None:
            if not any(a - 1 <= s <= b + 1 for a, b in sb.kept.get(at["edge"], ())):
                tidied += 1                 # (off the stretch of its edge the tidying kept)
                continue
            nowall += 1
            bad.append(f"{kind} {iid} (no wall)")
            continue
        if any(abs(s - ld["s"]) < ld["w"] // 2 + 300 and ld["z"] <= zz <= ld["z"] + ld["h"]
               for ld in doors.get(at["edge"], ())):
            landing += 1
            continue
        if any(a + 1 < s < b - 1 and lo + 1 < zz < hi - 1
               for a, b, lo, hi in sb.opened.get(at["edge"], ())):
            bad.append(f"{kind} {iid}")
    return {"mounts": len(items), "on_glass": len(bad) - nowall, "no_wall": nowall,
            "tidied": tidied, "off": off, "in_landing": landing, "first": bad[:3]}


def door_check(sb) -> dict:
    """The building's half of the access check (scope 9): a door for every entrance and
    every unit's entrance, facing out; the city's half (each door open to its walkway) is
    `asset_checks.access`."""
    br = sb.br
    ents = {d["entrance"] for d in sb.doors if d["entrance"] is not None}
    units = {d["unit"] for d in sb.doors if d["unit"] is not None}
    miss = [f"e{k}" for k in range(len(br["entrances"])) if k not in ents]
    miss += [f"u{k}" for k, un in enumerate(br["units"])
             if un.get("entrance") is not None and k not in units]
    return {"entrances": len(br["entrances"]),
            "units": sum(1 for un in br["units"] if un.get("entrance") is not None),
            "doors": len(sb.doors), "missing": len(miss), "first": miss[:3],
            "flush": sum(1 for d in sb.doors if d["flush"]),
            "moved": sum(1 for d in sb.doors if d.get("moved"))}
