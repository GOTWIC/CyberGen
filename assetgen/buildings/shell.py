"""The split grammar and the shell (scope 5.1.2, 14.2).

$$\\text{mass} \\to \\text{edges} \\to \\text{floor rows} \\to \\text{bays} \\to \\lbrace
\\text{opening}, \\text{panel}, \\text{pier}, \\text{mount} \\rbrace$$

Per mass: its floor rows (sill and head of every floor, the same on all its facades: a
ground row by the ground gene, mechanical louver rows in towers, a glazed lantern at a
tower's top, dark open bays in parking structures), then per facade (a mass edge, with the
brief's regions) the bays by the genome's module and rhythm between corner piers wide
enough for the reveals, an opening per bay by window type and the region's class (none on
party and hidden walls, few on blind ones), storefronts per ground-floor unit, and a panel
(a mount) wherever a sign slot, mounted prop, facade plant or skybridge end would fall on
glass.

Geometry, on integer millimeters in the building frame, every part closed (the mesh
check):
- the mass envelope: each facade a grid welded on its plane (pier cells per row, zipper
  strips between rows, so no T-junction anywhere and corners match because every facade of
  a mass has the same rows), a reveal pocket per opening with the pane at its back, the
  roof and bottom caps on the ring's corners;
- ring strips (`rings.strip`) extruded: slab bands at floor lines, cornices at the tops of
  masses, parapets on roof edges no other mass covers; only above 3 m where they leave the
  footprint, never on party, hidden or blind stretches;
- roof equipment blocks for the brief's roof items (AG4 replaces them).
"""

from __future__ import annotations

import bisect
import math

from citygen import dmath as M

from ..triangulate import TriangulationError, triangulate
from . import genome as GN
from . import rings as RG
from . import systems as SY
from .meshbuf import Buf

NO_WINDOW = ("party", "hidden")
STRIP_MIN_Z = 3000           # strips that leave the footprint stay this high (sidewalks)
PIER_MIN = 75
GAP_MIN = 60                 # between openings
EDGE_CLEAR = 60              # an opening's pocket from the neighbor facade's plane
MOUNT_PAD = 100
THIN_MM = 2500               # masses thinner than this get no openings
MAX_WIN_MM = 4000            # window height cap outside curtain walls
SPREAD = {"irregular": (0.7, 0.6), "tight": (0.85, 0.3), "loose": (0.5, 1.0)}


def _u(bid: str, purpose: str) -> float:
    return GN.u(bid, purpose, "ag1.shell")


class Facade:
    """One mass edge: a -> b (mm), outward to the right; s along it in mm, 0..L."""
    __slots__ = ("a", "b", "L", "ux", "uy", "nx", "ny", "j", "u0", "rec", "c0", "c1",
                 "regions")

    def __init__(self, a, b, u0: float):
        self.a, self.b = a, b
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lf = math.sqrt(dx * dx + dy * dy)
        self.L = max(int(round(Lf)), 1)
        self.ux, self.uy = dx / Lf, dy / Lf
        self.nx, self.ny = self.uy, -self.ux
        self.u0 = u0

    def P(self, s: int, z: int) -> tuple[int, int, int]:
        L2 = 2 * self.L
        a, b = self.a, self.b
        return (a[0] + (2 * (b[0] - a[0]) * s + self.L) // L2,
                a[1] + (2 * (b[1] - a[1]) * s + self.L) // L2, z)

    def cls(self, s: int, z: int) -> str:
        sm, zm = s / 1000.0, z / 1000.0
        for r in self.regions:
            if r["s"][0] <= sm <= r["s"][1] and r["z"][0] <= zm <= r["z"][1]:
                return r["class"]
        return self.rec["class"] if self.rec else "open"


def _corner_clear(d_in, d_out, r: int) -> int:
    """How far from a corner an opening's pocket (r deep) must start so it stays EDGE_CLEAR
    inside the solid next to the other facade (interior angle from the two directions)."""
    sin_t = d_in[0] * d_out[1] - d_in[1] * d_out[0]
    cos_t = -(d_in[0] * d_out[0] + d_in[1] * d_out[1])
    if sin_t <= 1e-3:
        return EDGE_CLEAR
    return max(EDGE_CLEAR, int(math.ceil((EDGE_CLEAR + r * cos_t) / sin_t)))


TURN_COS = 0.9397            # cos 20 degrees: less turn than this is no corner


def _turned(d_in, d_out) -> bool:
    return d_in[0] * d_out[0] + d_in[1] * d_out[1] < TURN_COS


def _thickness(ring) -> int:
    """The footprint's least width: over its edges, the most any vertex lies inside the
    edge's line (exact for convex rings, a fair measure otherwise)."""
    n = len(ring)
    best = None
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.sqrt(dx * dx + dy * dy)
        if L < 500:
            continue
        far = 0.0
        for p in ring:
            far = max(far, ((p[0] - a[0]) * -dy + (p[1] - a[1]) * dx) / L)
        best = far if best is None else min(best, far)
    return int(best if best is not None else 0)


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def mass_rows(ms: dict, g: str, gm: dict, is_top: bool, ground: str | None,
              tall_building: bool, parking: bool, cornice_h: int) -> list[tuple]:
    """(lo, hi, kind, floor) of every window row of a mass, ascending."""
    z0, z1 = ms["z0"], ms["z1"]
    n = ms["floors"]
    if n <= 0 or g == "structure":
        return []
    genes, cont = gm["genes"], gm["cont"]
    sysname = genes[f"{g}.system"]
    win = genes[f"{g}.window"]
    sill0 = int(round(cont[f"{g}.sill_m"] * 1000))
    gap0 = int(round(cont[f"{g}.head_m"] * 1000))
    if win == "tall":
        sill0, gap0 = max(300, sill0 - 350), max(250, gap0 - 200)
    if win == "banded":
        sill0 += 300
    mech = int(genes["mech_every"])
    rows = []
    for f in range(n):
        zf = z0 + (z1 - z0) * f // n
        H = z0 + (z1 - z0) * (f + 1) // n - zf
        kind, sill, head = "win", sill0, H - gap0
        if parking:
            kind, sill, head = "void", 1000, H - 300
        elif f == 0 and z0 <= 50 and ground is not None:
            if ground == "blank":
                continue
            if ground == "storefront":
                kind, sill, head = "shop", 300, H - max(500, H // 6)
            elif ground == "lobby":
                kind, sill, head = "shop", 150, H - 400
        elif win in ("clerestory", "strip") and sysname == "corrugated":
            hgt = 900 if win == "clerestory" else 1400
            head = H - gap0
            sill = head - hgt
        elif win in ("slit", "square") and sysname == "shanty_patchwork":
            sill = head - (500 if win == "slit" else 800)
        if not parking and kind == "win" and g == "body" and n >= 24 and 0 < f < n - 2 and \
                (f + 1) % mech == 0:
            kind = "louver"
        if is_top and f == n - 1 and tall_building and genes["crown"] == "lantern" and \
                kind == "win":
            kind, sill, head = "lantern", 150, H - 150
        if kind in ("win", "louver") and sysname != "unitized_curtain_wall" and \
                head - sill > MAX_WIN_MM:
            sill = head - MAX_WIN_MM
        if f == n - 1 and cornice_h:
            head = min(head, H - cornice_h - 80)
        sill = max(sill, 100)
        head = min(head, H - 100)
        if head - sill < 400:
            continue
        rows.append((zf + sill, zf + head, kind, f))
    return rows


# ---------------------------------------------------------------------------
# Bays and openings
# ---------------------------------------------------------------------------

def bay_cuts(L: int, c0: int, c1: int, bay: int, rhythm: str, key: str) -> list[tuple]:
    usable = L - c0 - c1
    if usable < max(int(0.45 * bay), 900):
        return []
    n = max(1, int(round(usable / bay)))
    if rhythm == "aba" and n >= 3:
        w = [1.25 if j % 2 == 0 else 0.75 for j in range(n)]
    elif rhythm in SPREAD:
        lo, span = SPREAD[rhythm]
        w = [lo + span * _u(key, f"bay{j}") for j in range(n)]
    else:
        w = [1.0] * n
    tot = 0.0
    for x in w:
        tot += x
    cuts = [c0]
    acc = 0.0
    for j in range(n):
        acc += w[j]
        cuts.append(c0 + int(round(usable * acc / tot)))
    cuts[-1] = L - c1
    return [(cuts[j], cuts[j + 1]) for j in range(n)]


def bay_openings(b0: int, b1: int, j: int, n: int, win: str, rhythm: str, wwr: float,
                 sysname: str, key: str, open_p: float = 0.55) -> list[tuple[int, int]]:
    wb = b1 - b0
    mid = (b0 + b1) // 2
    if win == "sparse" and j % 3 != 1:
        return []
    if sysname == "shanty_patchwork":
        # the opening's place in its bay is the facade's (`key` without the row), whether it
        # is there in a row is the row's: every row then has the same columns
        if open_p < 1.0 and _u(key, f"p{j}") > open_p:
            return []
        fkey = key.rsplit("|", 1)[0]
        k = {"patch": 1.0, "slit": 1.5, "square": 0.8}.get(win, 1.0)
        ow = min(int(wb * wwr * k * (0.75 + 0.4 * _u(fkey, f"w{j}"))), wb - 2 * PIER_MIN)
        off = int((wb - ow) * (_u(fkey, f"o{j}") - 0.5) * 0.6)
        return [(mid - ow // 2 + off, mid - ow // 2 + off + ow)]
    if sysname == "unitized_curtain_wall":
        mull = max(60, int(wb * (1.0 - wwr)))
        if win == "split" and wb > 1800:
            half = (wb - 2 * mull) // 2
            return [(b0 + mull // 2, b0 + mull // 2 + half),
                    (b1 - mull // 2 - half, b1 - mull // 2)]
        return [(b0 + mull // 2, b1 - mull // 2)]
    if win in ("ribbon", "strip"):
        ow = wb - 200
    elif win == "wide":
        ow = int(wb * wwr * 1.4)
    elif win == "square":
        ow = int(wb * wwr * 1.2)
    elif win == "paired":
        tot = int(wb * min(wwr * 1.3, 0.85))
        gap = max(120, tot // 6)
        each = (tot - gap) // 2
        if each < 350:
            return []
        return [(mid - gap // 2 - each, mid - gap // 2), (mid + gap // 2, mid + gap // 2 + each)]
    else:
        ow = int(wb * wwr)
    ow = min(ow, wb - 2 * PIER_MIN)
    if ow < 350:
        return []
    off = 0
    if rhythm == "grouped" and n >= 2:
        # pairs of bays lean together, leaving wider piers between the pairs
        side = 1 if j % 2 == 0 else -1
        if j % 2 == 0 and j == n - 1:
            side = 0
        off = side * (wb - ow) // 3
    return [(mid - ow // 2 + off, mid - ow // 2 + off + ow)]


def _merge_ok(ops: list[tuple], c0: int, c1: int, L: int) -> list[tuple]:
    """Openings sorted, inside the corner clearances, GAP_MIN apart (a later one that would
    touch an earlier one is dropped)."""
    out: list[tuple] = []
    for op in sorted(ops):
        a, b = op[0], op[1]
        if a < c0 or b > L - c1 or b - a < 300:
            continue
        if out and a < out[-1][1] + GAP_MIN:
            continue
        out.append(op)
    return out


# ---------------------------------------------------------------------------
# The shell of one building
# ---------------------------------------------------------------------------

class ShellBuilder:
    def __init__(self, brief: dict, gm: dict):
        self.br = brief
        self.gm = gm
        self.bid = brief["id"]
        self.buf = Buf()
        self.stats = {"bays": 0, "openings": 0, "mount_panels": 0, "storefronts": 0,
                      "strips": 0, "strips_refused": 0, "roof_items": 0, "masses": 0}
        self.used = {"groups": [], "features": {}, "ground": False, "finish": False,
                     "base": False}
        self.mass_info: list[dict] = []
        b = brief["building"]
        self.parking = b["type"] == "building.parking_structure"
        self.tall = float(b["height_m"]) >= 60.0
        self.units_by_edge: dict[int, list] = {}
        for un in brief["units"]:
            at = un.get("at")
            if at is not None:
                self.units_by_edge.setdefault(at["edge"], []).append(un)
        self.mounts = self._mounts()

    # -- what must fall on a panel -------------------------------------------------------

    def _mounts(self) -> dict[int, list[tuple]]:
        out: dict[int, list] = {}
        br = self.br

        def add(at, z, w, h):
            if at is None:
                return
            s = int(round(at["s"] * 1000))
            out.setdefault(at["edge"], []).append(
                (s - w // 2 - MOUNT_PAD, s + w // 2 + MOUNT_PAD,
                 int(round(z * 1000)) - h // 2 - MOUNT_PAD, int(round(z * 1000)) + h // 2 +
                 MOUNT_PAD))
        for s in br["sign_slots"]:
            if s["mount"] == "roof":
                continue
            w = 300 if s["mount"] == "blade" else int(s["width_m"] * 1000)
            add(s["at"], s["position"][2], w, int(s["height_m"] * 1000))
        size = {"ac_unit": (1000, 800), "wall_light": (400, 400), "sign": (300, 1500),
                "overhead_cable": (300, 300)}
        for p in br["props"]:
            if not p["on_wall"] or p["kind"] not in size:
                continue
            w, h = size[p["kind"]]
            add(p["at"], p["position"][2], w, h)
        for p in br["plants"]:
            add(p["at"], p["position"][2], 1500, int(max(p["height_m"], 1.0) * 1000))
        for s in br["skybridges"]:
            h = int(max(s["levels"], 1) * s["level_height_m"] * 1000)
            add(s["at"], s["z_m"] + h / 2000.0, int(s["width_m"] * 1000) + 600, h + 400)
        return out

    # -- build ---------------------------------------------------------------------------

    def build(self) -> dict:
        br = self.br
        masses = []
        for k, m in enumerate(br["masses"]):
            raw = [[(int(round(p[0] * 1000)), int(round(p[1] * 1000))) for p in ring]
                   for ring in [m["footprint"]["exterior"]] + m["footprint"]["holes"]]
            tidied = [RG.tidy(ring) for ring in raw]
            if any(len(t[0]) != len(RG.clean(r)) for t, r in zip(tidied, raw)):
                self.stats["rings_tidied"] = self.stats.get("rings_tidied", 0) + 1
            keep = [0] + self._unpinched(tidied[0][0], [t[0] for t in tidied[1:]])
            masses.append({"k": k, "role": m["role"], "shape": m["shape"],
                           "z0": int(round(m["z"][0] * 1000)), "z1": int(round(m["z"][1] * 1000)),
                           "rings": [tidied[r][0] for r in keep],
                           "eidx": [tidied[r][1] for r in keep], "rid": keep,
                           "floors": int(m["floors"]["count"])})
        self.masses = masses
        edge_of = {}
        for j, e in enumerate(br["edges"]):
            edge_of[(e["mass"], e["ring"], e["i"])] = j
        self.edge_of = edge_of
        groups = set()
        for ms in masses:
            if ms["z1"] - ms["z0"] < 50 or len(RG.clean(ms["rings"][0])) < 3:
                continue
            self.stats["masses"] += 1
            g = SY.role_group(ms["role"])
            if ms["shape"] == "ring":
                self._wheel(ms)
                continue
            if g != "structure":
                groups.add(g)
            self._mass(ms, g)
        for it in br["roof_items"]:
            self._roof_item(it)
        self.used["groups"] = [g for g in GN.GROUPS if g in groups]
        self.used["trim"] = self.stats["strips"] > 0
        self.used["glass"] = self.stats["openings"] > 0
        arrs = self.buf.arrays()
        return {"buf": self.buf, "arrays": arrs, "stats": self.stats, "used": self.used,
                "masses": self.mass_info}

    def _unpinched(self, ext, holes) -> list[int]:
        """The ring numbers (1 on) of the courts that touch neither the exterior nor another
        court (a court pinched onto the exterior at a point would make that corner's walls
        meet four ways): those that do are filled."""
        keep = []
        for j, h in enumerate(holes):
            others = [ext] + [o for i, o in enumerate(holes) if i != j]
            touch = len(h) < 3 or len(set(h)) != len(h) or any(
                RG.inside(p, o) == 0 for o in others for p in h) or any(
                RG.inside(p, h) == 0 for o in others for p in o)
            if touch:
                self.stats["courts_filled"] = self.stats.get("courts_filled", 0) + 1
            else:
                keep.append(j + 1)
        return keep

    def _covered_above(self, ms: dict, a, b) -> bool:
        """Whether another mass of the building stands on this mass's edge a-b (just above
        its top): then no parapet or cornice there."""
        z1 = ms["z1"]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.sqrt(dx * dx + dy * dy)
        if L < 1:
            return True
        nx, ny = -dy / L, dx / L               # inward
        pts = []
        for f in (0.1, 0.5, 0.9):
            pts.append((int(round(a[0] + dx * f + nx * 400)), int(round(a[1] + dy * f + ny * 400))))
            pts.append((int(round(a[0] + dx * f)), int(round(a[1] + dy * f))))
        for o in self.masses:
            if o is ms or o["z0"] > z1 + 50 or o["z1"] <= z1 + 50:
                continue
            for p in pts:
                if RG.in_poly(p, o["rings"]) >= 0:
                    return True
        return False

    def _mass(self, ms: dict, g: str) -> None:
        br, gm = self.br, self.gm
        genes, cont = gm["genes"], gm["cont"]
        k = ms["k"]
        if g == "structure":
            sysname, wall = None, "structure"
        else:
            sysname = genes[f"{g}.system"]
            T = SY.SYSTEMS[sysname]
            wall = T["wall"]
            if sysname == "punched_concrete":
                wall = genes["finish"]
                self.used["finish"] = True
        rings = ms["rings"]
        thick = _thickness(RG.clean(rings[0]))
        is_top = not any(o is not ms and o["z0"] >= ms["z1"] - 50 and
                         RG.in_poly(_centroid(o["rings"][0]), [rings[0]]) >= 0
                         for o in self.masses)
        feats = self.used["features"].setdefault(g, [])
        # cornice and bands decided first: they bound the rows
        cornice = genes.get(f"{g}.cornice", "none") if sysname else "none"
        cornice_d = int(round(cont.get(f"{g}.cornice_m", 0.3) * 1000)) if cornice != "none" \
            else 0
        if cornice == "thin":
            cornice_d = max(150, cornice_d // 2)
        cornice_h = 0
        if cornice_d and ms["z1"] - cornice_d * 2 >= STRIP_MIN_Z:
            cornice_h = max(250, int(cornice_d * 1.4))
        ground = None
        if ms["z0"] <= 50 and g != "structure":
            ground = genes["ground"]
            if br["units"] and ground not in ("storefront", "lobby"):
                ground = "storefront"
            self.used["ground"] = True
        rows = mass_rows(ms, g, gm, is_top, ground, self.tall, self.parking, cornice_h)
        reveal = int(round(cont[f"{g}.reveal_m"] * 1000)) if sysname else 0
        corner = int(round(cont[f"{g}.corner_m"] * 1000)) if sysname else 0
        corner = {"heavy": corner * 2, "tight": max(corner // 2, 100)}.get(genes["corner"],
                                                                         corner)
        bay = int(round(cont[f"{g}.bay_m"] * 1000)) if sysname else 0
        allow = sysname is not None and thick >= THIN_MM
        info = {"mass": k, "group": g, "system": sysname, "rows": len(rows), "openings": 0}
        self.buf.new_part()
        u_run = 0.0
        all_edges = [(ring[i], ring[(i + 1) % len(ring)]) for ring in rings
                     for i in range(len(ring)) if ring[i] != ring[(i + 1) % len(ring)]]
        for r, ring in enumerate(rings):
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                if a == b:
                    continue
                fa = Facade(a, b, u_run)
                u_run += fa.L / 1000.0
                j = self.edge_of.get((k, ms["rid"][r], ms["eidx"][r][i]))
                fa.j = j
                fa.rec = br["edges"][j] if j is not None else None
                fa.regions = fa.rec["regions"] if fa.rec else []
                prev = ring[(i - 1) % n]
                pi = 2
                while prev == a and pi <= n:
                    prev = ring[(i - pi) % n]
                    pi += 1
                nxt = ring[(i + 2) % n]
                ni = 3
                while nxt == b and ni <= n + 1:
                    nxt = ring[(i + ni) % n]
                    ni += 1
                d_in = _unit(prev, a)
                d_out = (fa.ux, fa.uy)
                d_nx = _unit(b, nxt)
                # the corner pier only at a real corner; where the ring runs on nearly
                # straight (a front split in two), just the reveal's clearance
                fa.c0 = max(corner if _turned(d_in, d_out) else 0,
                            _corner_clear(d_in, d_out, reveal))
                fa.c1 = max(corner if _turned(d_out, d_nx) else 0,
                            _corner_clear(d_out, d_nx, reveal))
                ok = allow and not _blocked(fa, reveal + EDGE_CLEAR, all_edges)
                info["openings"] += self._facade(ms, g, fa, rows, wall, sysname, reveal, bay,
                                                 ok)
        self._caps(ms, wall)
        self.mass_info.append(info)
        if sysname is None:
            return
        # strips: parapet on open roof edges, cornice, slab bands
        top_open = [[not self._covered_above(ms, ring[i], ring[(i + 1) % len(ring)])
                     for i in range(len(ring))] for ring in rings]
        par = genes.get(f"{g}.parapet", "none")
        if is_top and genes["crown"] == "flat" and g != "base":
            par = "none"
        if is_top and genes["crown"] == "parapet":
            par = "high"
        if par != "none":
            hp = int(round(cont[f"{g}.parapet_m"] * 1000))
            if par == "low":
                hp = max(300, hp // 2)
            t = max(200, reveal + 80)
            if self._strips(ms, top_open, 0, -t, ms["z1"], ms["z1"] + hp, "trim", t,
                            need_out=False):
                feats.append("parapet")
        if cornice_h:
            ok = self._edge_ok(ms, ms["z1"] - cornice_h, ms["z1"])
            mask = [[o and q for o, q in zip(r1, r2)] for r1, r2 in zip(top_open, ok)]
            if self._strips(ms, mask, cornice_d, 0, ms["z1"] - cornice_h, ms["z1"], "trim",
                            cornice_d, need_out=True):
                feats.append("cornice")
        bands = genes.get(f"{g}.bands", "none")
        if bands != "none" and ms["floors"] >= 2:
            bd = int(round(cont[f"{g}.band_m"] * 1000))
            bh = int(2.5 * bd + 100)
            n = ms["floors"]
            levels = []
            for f in range(1, n):
                if bands == "alternate" and f % 2:
                    continue
                if bands == "podium":
                    continue
                levels.append(ms["z0"] + (ms["z1"] - ms["z0"]) * f // n)
            if bands == "podium" and g == "base":
                levels = [ms["z1"] - bh // 2 - 1] if not cornice_h else []
            done = False
            for zf in levels:
                za, zb = zf - bh // 2, zf + bh // 2
                if za < STRIP_MIN_Z or any(lo < zb + 20 and hi > za - 20 for lo, hi, _, _ in
                                           rows):
                    continue
                ok = self._edge_ok(ms, za, zb)
                if self._strips(ms, ok, bd, 0, za, zb, "trim", bd, need_out=True):
                    done = True
            if done:
                feats.append("bands")

    def _edge_ok(self, ms: dict, za: int, zb: int) -> list[list[bool]]:
        """Per ring edge: whether a strip may leave the footprint there between za and zb
        (no party, hidden or blind stretch in that height)."""
        out = []
        k = ms["k"]
        for r, ring in enumerate(ms["rings"]):
            row = []
            for i in range(len(ring)):
                j = self.edge_of.get((k, ms["rid"][r], ms["eidx"][r][i]))
                ok = j is not None
                if ok:
                    for reg in self.br["edges"][j]["regions"]:
                        if reg["z"][0] * 1000 < zb and reg["z"][1] * 1000 > za and \
                                reg["class"] in ("party", "hidden", "blind"):
                            ok = False
                            break
                row.append(ok)
            out.append(row)
        return out

    def _strips(self, ms: dict, mask: list[list[bool]], d_out: int, d_in: int, z0: int,
                z1: int, slot: str, setback: int, need_out: bool) -> bool:
        """Extrude the ring strips of every run of edges the mask allows."""
        made = False
        for r, ring0 in enumerate(ms["rings"]):
            # the ring without zero-length edges, the mask carried along
            n0 = len(ring0)
            keep = [i for i in range(n0) if ring0[i] != ring0[(i + 1) % n0]]
            ring = [ring0[i] for i in keep]
            m = [mask[r][i] for i in keep]
            n = len(ring)
            if n < 3:
                continue
            runs = []
            if all(m):
                runs.append((0, n))
            elif any(m):
                start = next(i for i in range(n) if not m[i])
                i = (start + 1) % n
                cnt = 0
                while cnt < n:
                    if m[i]:
                        i0, length = i, 0
                        while m[i] and length < n:
                            length += 1
                            i = (i + 1) % n
                            cnt += 1
                        runs.append((i0, length))
                    else:
                        i = (i + 1) % n
                        cnt += 1
            for i0, length in runs:
                sb = 0 if length >= n else setback
                res = RG.strip(ring, i0, length, d_out, d_in, sb)
                if res is None:
                    self.stats["strips_refused"] += 1
                    continue
                outer, hole = res
                self.buf.new_part()
                if self._extrude(outer, hole, z0, z1, slot):
                    made = True
                    self.stats["strips"] += 1
        return made

    def _extrude(self, outer, hole, z0: int, z1: int, slot: str) -> bool:
        holes = [hole] if hole is not None else []
        try:
            tris = triangulate(outer, holes, keep_straight=True)
        except TriangulationError:
            return False
        if not tris:
            return False
        buf = self.buf
        pts = list(outer) + (list(hole) if hole is not None else [])
        top = buf.plane((0.0, 0.0, 1.0), (0, 0, z1), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        bot = buf.plane((0.0, 0.0, -1.0), (0, 0, z0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0))
        buf.add(slot, top, [(p[0], p[1], z1) for p in pts], [i for t in tris for i in t])
        buf.add(slot, bot, [(p[0], p[1], z0) for p in pts],
                [i for t in tris for i in (t[0], t[2], t[1])])
        for rg in [outer] + holes:
            n = len(rg)
            for i in range(n):
                p, q = rg[i], rg[(i + 1) % n]
                self._vquad(slot, p, q, z0, z1)
        return True

    def _vquad(self, slot: str, p, q, z0: int, z1: int) -> None:
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.sqrt(dx * dx + dy * dy)
        ux, uy = dx / L, dy / L
        pl = self.buf.plane((uy, -ux, 0.0), (p[0], p[1], 0), (ux, uy, 0.0), (0.0, 0.0, 1.0))
        self.buf.quad(slot, pl, (p[0], p[1], z0), (q[0], q[1], z0), (q[0], q[1], z1),
                      (p[0], p[1], z1))

    # -- one facade ----------------------------------------------------------------------

    def _facade(self, ms: dict, g: str, fa: Facade, rows: list, wall: str, sysname,
                reveal: int, bay: int, allow: bool) -> int:
        genes, cont = self.gm["genes"], self.gm["cont"]
        L = fa.L
        key = f"{self.bid}|{ms['k']}|{fa.j}|{fa.a}"
        cols: list[list[int]] = []
        ops_by_row: list[dict] = []
        n_open = 0
        win = genes.get(f"{g}.window") if sysname else None
        rhythm = genes.get(f"{g}.rhythm") if sysname else None
        wwr = cont.get(f"{g}.wwr", 0.4) if sysname else 0.0
        open_p = cont.get(f"{g}.open_p", 0.55)
        cuts = bay_cuts(L, fa.c0, fa.c1, bay, rhythm, key) if allow and bay else []
        patch_cols = None
        if sysname == "shanty_patchwork":
            pot = [(a_, b_, "glass") for jb, (b0, b1) in enumerate(cuts)
                   for a_, b_ in bay_openings(b0, b1, jb, len(cuts), win, rhythm, wwr,
                                              sysname, f"{key}|x", 1.0)]
            patch_cols = [x for a_, b_, _ in _merge_ok(pot, fa.c0, fa.c1, L) for x in (a_, b_)]
        units = self.units_by_edge.get(fa.j, []) if fa.j is not None else []
        mounts = self.mounts.get(fa.j, []) if fa.j is not None else []
        for lo, hi, kind, f in rows:
            ops = []
            if allow:
                zm = (lo + hi) // 2
                if kind == "shop" and units:
                    for un in units:
                        s = int(round(un["at"]["s"] * 1000))
                        w = int(round(un["width_m"] * 1000))
                        a_, b_ = max(s - w // 2 + 250, fa.c0), min(s + w // 2 - 250, L - fa.c1)
                        if b_ - a_ >= 800 and fa.cls((a_ + b_) // 2, zm) not in NO_WINDOW:
                            ops.append((a_, b_, "storefront"))
                            self.stats["storefronts"] += 1
                else:
                    back = {"win": "glass", "shop": "storefront", "louver": "louver",
                            "void": "void", "lantern": "glass"}[kind]
                    w_ = "full" if kind == "lantern" and sysname == "unitized_curtain_wall" \
                        else ("ribbon" if kind == "lantern" else win)
                    if kind == "shop" and win in ("sparse", "clerestory", "strip") or \
                            kind == "shop" and sysname == "shanty_patchwork":
                        w_ = "single"
                    for jb, (b0, b1) in enumerate(cuts):
                        self.stats["bays"] += 1
                        for a_, b_ in bay_openings(b0, b1, jb, len(cuts), w_, rhythm, wwr,
                                                   sysname, f"{key}|{f}", open_p):
                            c = fa.cls((a_ + b_) // 2, zm)
                            if c in NO_WINDOW:
                                continue
                            if c == "blind":
                                if _u(key, f"blind{f}.{jb}") > 0.3:
                                    continue
                                cw = (b_ - a_) * 3 // 10
                                a_, b_ = (a_ + b_) // 2 - cw, (a_ + b_) // 2 + cw
                            ops.append((a_, b_, back))
                kept = []
                for op in ops:
                    if any(op[0] < m1 and op[1] > m0 and lo < z1 and hi > z0
                           for m0, m1, z0, z1 in mounts):
                        self.stats["mount_panels"] += 1
                        continue
                    kept.append(op)
                ops = _merge_ok(kept, fa.c0, fa.c1, L)
            c = [0]
            for a_, b_, _ in ops:
                c += [a_, b_]
            c.append(L)
            if patch_cols is not None:
                # the facade's patch columns, except inside an opening or within 50 mm of a
                # column this row has (two columns a millimeter apart could round to one point)
                extra = [x for x in patch_cols if not any(a_ < x < b_ for a_, b_, _ in ops)
                         and all(abs(x - y) >= 50 for y in c)]
                c = sorted(set(c) | set(extra))
            cols.append(c)
            ops_by_row.append({a_: (b_, back) for a_, b_, back in ops})
            n_open += len(ops)
        self.stats["openings"] += n_open
        self._wall(ms, fa, rows, cols, ops_by_row, wall, reveal, key)
        return n_open

    def _wall(self, ms: dict, fa: Facade, rows: list, cols: list, ops_by_row: list,
              wall: str, reveal: int, key: str) -> None:
        buf = self.buf
        pl = buf.plane((fa.nx, fa.ny, 0.0), (fa.a[0], fa.a[1], 0), (fa.ux, fa.uy, 0.0),
                       (0.0, 0.0, 1.0), fa.u0, 0.0)
        patch = wall == "patch_sheet"
        if patch:
            g = SY.role_group(ms["role"])
            mix = SY.PATCH_MIXES[self.gm["genes"][f"{g}.patch"]]
            pw = int(self.gm["cont"][f"{g}.patch_w"] * 1000)
            ph = int(self.gm["cont"][f"{g}.patch_h"] * 1000)
        L = fa.L
        P = fa.P
        # vertex indices per slot, keyed by (s, z): the facade's grid, welded on its plane
        cache: dict[str, dict] = {}

        def vid(slot, s, z, store):
            d = cache.setdefault(slot, {})
            v = d.get((s, z))
            if v is None:
                v = len(store)
                d[(s, z)] = v
                store.append(P(s, z))
            return v

        tri_by: dict[str, tuple[list, list]] = {}

        def tri(slot, p, q, r):
            st = tri_by.get(slot)
            if st is None:
                st = ([], [])
                tri_by[slot] = st
            pts, ix = st
            ix += [vid(slot, p[0], p[1], pts), vid(slot, q[0], q[1], pts),
                   vid(slot, r[0], r[1], pts)]

        def slot_at(s, z, chain=None):
            """The wall's slot; on patchwork, a patch per column of the chain (so strips
            and piers of one column match) and band of patch height."""
            if not patch:
                return wall
            c0 = 0
            if chain is not None:
                c0 = chain[max(bisect.bisect_right(chain, s) - 1, 0)]
            else:
                c0 = s // pw
            return GN.pick(key, f"patch{c0 // pw}.{z // ph}", SY.PATCH_SLOTS, mix, "ag1.shell")

        def zipper(B, zb, T, zt, fixed=None):
            """The strip between chain B at zb and chain T at zt (sorted s, both from 0 to
            L), every triangle spanning both chains. On patchwork the strips between rows
            have the rows' columns on both chains (a patch per column); the strips at the
            bottom and top, whose triangles fan to the corners, are one patch each."""
            if patch and fixed is None and B != T:
                fixed = slot_at(0, (zb + zt) // 2)
            i = j = 0
            while i < len(B) - 1 or j < len(T) - 1:
                if j == len(T) - 1 or (i < len(B) - 1 and B[i + 1] <= T[j + 1]):
                    s = fixed or slot_at((B[i] + B[i + 1] + T[j]) // 3, (zb + zt) // 2, B)
                    tri(s, (B[i], zb), (B[i + 1], zb), (T[j], zt))
                    i += 1
                else:
                    s = fixed or slot_at((B[i] + T[j + 1] + T[j]) // 3, (zb + zt) // 2, B)
                    tri(s, (B[i], zb), (T[j + 1], zt), (T[j], zt))
                    j += 1

        z0, z1 = ms["z0"], ms["z1"]
        prev, pz = [0, L], z0
        o = (int(round(-fa.nx * reveal)), int(round(-fa.ny * reveal)))
        base = self.gm["genes"]["base"]
        plinth = base if rows and z0 <= 50 and base != "wall" and wall != "structure" else None
        if plinth:
            self.used["base"] = True        # the strip under the ground row in its finish
        for (lo, hi, kind, f), c, ops in zip(rows, cols, ops_by_row):
            zipper(prev, pz, c, lo, plinth if pz == z0 else None)
            for i in range(len(c) - 1):
                a_, b_ = c[i], c[i + 1]
                if a_ in ops and ops[a_][0] == b_:
                    self._pocket(fa, a_, b_, lo, hi, o, ops[a_][1], wall, key, f, i)
                    continue
                s = slot_at((a_ + b_) // 2, (lo + hi) // 2, c)
                tri(s, (a_, lo), (b_, lo), (b_, hi))
                tri(s, (a_, lo), (b_, hi), (a_, hi))
            prev, pz = c, hi
        zipper(prev, pz, [0, L], z1)
        for slot in sorted(tri_by):
            pts, ix = tri_by[slot]
            buf.add(slot, pl, pts, ix)

    def _pocket(self, fa: Facade, sa: int, sb: int, lo: int, hi: int, o, back: str,
                wall: str, key: str, f: int, i: int) -> None:
        """The opening's reveal (sill, head, jambs in the wall's slot) and its pane at the
        back, `o` (the inward reveal vector) behind the facade."""
        buf = self.buf
        P = fa.P
        Fl0, Fr0, Fl1, Fr1 = P(sa, lo), P(sb, lo), P(sa, hi), P(sb, hi)

        def bk(p):
            return (p[0] + o[0], p[1] + o[1], p[2])
        Bl0, Br0, Bl1, Br1 = bk(Fl0), bk(Fr0), bk(Fl1), bk(Fr1)
        ix, iy = -fa.nx, -fa.ny                      # into the wall
        rv = wall if not wall.startswith("patch") else "patch_sheet"
        u = (fa.ux, fa.uy, 0.0)
        into = (ix, iy, 0.0)
        up = (0.0, 0.0, 1.0)
        us = fa.u0 + sa / 1000.0
        sill = buf.plane((0.0, 0.0, 1.0), Fl0, u, into, us)
        head = buf.plane((0.0, 0.0, -1.0), Fl1, u, into, us)
        left = buf.plane(u, Fl0, into, up, 0.0, lo / 1000.0)
        right = buf.plane((-fa.ux, -fa.uy, 0.0), Fr0, into, up, 0.0, lo / 1000.0)
        buf.quad(rv, sill, Fl0, Fr0, Br0, Bl0)
        buf.quad(rv, head, Fr1, Fl1, Bl1, Br1)
        buf.quad(rv, left, Fl0, Bl0, Bl1, Fl1)
        buf.quad(rv, right, Fr0, Fr1, Br1, Br0)
        pane = buf.plane((fa.nx, fa.ny, 0.0), (fa.a[0] + o[0], fa.a[1] + o[1], 0),
                         (fa.ux, fa.uy, 0.0), (0.0, 0.0, 1.0), fa.u0, 0.0)
        win = int(_u(key, f"win{f}.{i}") * 256) & 255
        buf.quad(back, pane, Bl0, Br0, Br1, Bl1,
                 uv1=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], win=win)

    def _caps(self, ms: dict, wall: str) -> None:
        rings = [RG.clean(r) for r in ms["rings"]]
        outer, holes = rings[0], [h for h in rings[1:] if len(h) >= 3]
        try:
            tris = triangulate(outer, holes, keep_straight=True)
        except TriangulationError:
            self.stats.setdefault("cap_failures", 0)
            self.stats["cap_failures"] += 1
            return
        pts = list(outer) + [p for h in holes for p in h]
        z0, z1 = ms["z0"], ms["z1"]
        buf = self.buf
        top = buf.plane((0.0, 0.0, 1.0), (0, 0, z1), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        bot = buf.plane((0.0, 0.0, -1.0), (0, 0, z0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0))
        roof = "roof" if wall != "structure" else "structure"
        buf.add(roof, top, [(p[0], p[1], z1) for p in pts], [i for t in tris for i in t])
        buf.add("structure", bot, [(p[0], p[1], z0) for p in pts],
                [i for t in tris for i in (t[0], t[2], t[1])])

    # -- roof items and wheels -----------------------------------------------------------

    def _roof_item(self, it: dict) -> None:
        x, y, z = (int(round(v * 1000)) for v in it["position"])
        sa, sc, sz = (max(int(round(v * 1000)), 100) for v in it["size"])
        a = M.radians(float(it["yaw_deg"]))
        ux, uy = float(M.cos(a)), float(M.sin(a))
        vx, vy = -uy, ux
        ha, hc = sa / 2.0, sc / 2.0
        ring = [(int(round(x - ux * ha - vx * hc)), int(round(y - uy * ha - vy * hc))),
                (int(round(x + ux * ha - vx * hc)), int(round(y + uy * ha - vy * hc))),
                (int(round(x + ux * ha + vx * hc)), int(round(y + uy * ha + vy * hc))),
                (int(round(x - ux * ha + vx * hc)), int(round(y - uy * ha + vy * hc)))]
        ring = RG.clean(ring)
        if len(ring) < 3 or not RG.is_simple(ring):
            return
        self.buf.new_part()
        if self._extrude(ring, None, z, z + sz, "equipment"):
            self.stats["roof_items"] += 1

    def _wheel(self, ms: dict) -> None:
        """A vertical wheel (as the blockout draws it): rim and spokes as closed beams in the
        plane of the footprint's long axis."""
        ring = RG.clean(ms["rings"][0])
        n0 = len(ring)
        cx = sum(p[0] for p in ring) / n0
        cy = sum(p[1] for p in ring) / n0
        # the wheel's plane along the footprint's longest edge (the blockout aims at its
        # farthest corner, which tilts a thin footprint's wheel out of it)
        k = max(range(n0), key=lambda i: ((ring[(i + 1) % n0][0] - ring[i][0]) ** 2 +
                                          (ring[(i + 1) % n0][1] - ring[i][1]) ** 2, -i))
        ux, uy = _unit(ring[k], ring[(k + 1) % n0])
        zc = ms["z0"] + (ms["z1"] - ms["z0"]) / 2.0
        r = (ms["z1"] - ms["z0"]) / 2.0 - 1000.0      # the rim beams' outer faces on the mass
        n = 32
        pts = []
        for kk in range(n):
            t = 2.0 * M.PI * kk / n
            c, s = float(M.cos(t)), float(M.sin(t))
            pts.append((cx + ux * r * c, cy + uy * r * c, zc + r * s))
        for kk in range(n):
            self._beam(pts[kk], pts[(kk + 1) % n], 2000, 2000, ux, uy)
        for kk in range(0, n, 4):
            self._beam((cx, cy, zc), pts[kk], 800, 800, ux, uy)
        self.mass_info.append({"mass": ms["k"], "group": "structure", "system": None,
                               "rows": 0, "openings": 0})

    def _beam(self, a, b, w: int, h: int, ux: float, uy: float) -> None:
        """A closed box from a to b (mm), w across (horizontal, normal to the wheel's plane)
        and h in the wheel's plane."""
        d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        if L < 10:
            return
        e = (d[0] / L, d[1] / L, d[2] / L)
        p = (-uy, ux, 0.0)                              # across the wheel's plane
        q = (e[1] * p[2] - e[2] * p[1], e[2] * p[0] - e[0] * p[2], e[0] * p[1] - e[1] * p[0])
        hw, hh = w / 2.0, h / 2.0

        def corner(base, sp, sq):
            return tuple(int(round(base[k] + p[k] * sp + q[k] * sq)) for k in range(3))
        A = [corner(a, -hw, -hh), corner(a, hw, -hh), corner(a, hw, hh), corner(a, -hw, hh)]
        B = [corner(b, -hw, -hh), corner(b, hw, -hh), corner(b, hw, hh), corner(b, -hw, hh)]
        buf = self.buf
        buf.new_part()
        faces = [(A[0], A[3], A[2], A[1]), (B[0], B[1], B[2], B[3]),
                 (A[0], A[1], B[1], B[0]), (A[1], A[2], B[2], B[1]),
                 (A[2], A[3], B[3], B[2]), (A[3], A[0], B[0], B[3])]
        for f in faces:
            nrm = _normal(f)
            if nrm is None:
                continue
            ax_ = _unit3(f[0], f[1])
            bx_ = (nrm[1] * ax_[2] - nrm[2] * ax_[1], nrm[2] * ax_[0] - nrm[0] * ax_[2],
                   nrm[0] * ax_[1] - nrm[1] * ax_[0])
            pl = buf.plane(nrm, f[0], ax_, bx_)
            buf.quad("structure", pl, *f)


def _blocked(fa: Facade, depth: int, edges) -> bool:
    """Whether another edge of the mass crosses the strip behind the facade where its
    pockets would go (between the corner clearances, `depth` deep): a sliver of solid, as
    where a court lies a few centimeters inside the exterior."""
    if fa.L - fa.c0 - fa.c1 < 300:
        return False
    ix, iy = -fa.nx * depth, -fa.ny * depth
    q0 = fa.P(fa.c0, 0)[:2]
    q1 = fa.P(fa.L - fa.c1, 0)[:2]
    q2 = (int(round(q1[0] + ix)), int(round(q1[1] + iy)))
    q3 = (int(round(q0[0] + ix)), int(round(q0[1] + iy)))
    rect = [q0, q1, q2, q3]
    x0, x1 = min(p[0] for p in rect), max(p[0] for p in rect)
    y0, y1 = min(p[1] for p in rect), max(p[1] for p in rect)
    for a, b in edges:
        if (a, b) == (fa.a, fa.b):
            continue
        if max(a[0], b[0]) < x0 or min(a[0], b[0]) > x1 or max(a[1], b[1]) < y0 or \
                min(a[1], b[1]) > y1:
            continue
        for k in range(4):
            if RG.seg_hit(a, b, rect[k], rect[(k + 1) % 4]):
                return True
        if RG.inside(a, rect) == 1:
            return True
    return False


def _centroid(ring):
    n = len(ring)
    return (sum(p[0] for p in ring) // n, sum(p[1] for p in ring) // n)


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.sqrt(dx * dx + dy * dy) or 1.0
    return dx / L, dy / L


def _unit3(a, b):
    d = [b[k] - a[k] for k in range(3)]
    L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) or 1.0
    return (d[0] / L, d[1] / L, d[2] / L)


def _normal(f):
    e1 = [f[1][k] - f[0][k] for k in range(3)]
    e2 = [f[3][k] - f[0][k] for k in range(3)]
    n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
         e1[0] * e2[1] - e1[1] * e2[0])
    L = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    if L == 0:
        return None
    return (n[0] / L, n[1] / L, n[2] / L)


def build(brief: dict, gm: dict) -> dict:
    return ShellBuilder(brief, gm).build()
