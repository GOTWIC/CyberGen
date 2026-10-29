"""The split grammar and the shell (scope 5.1.2, 14.2, 14.3).

$$\\text{mass} \\to \\text{edges} \\to \\text{floor rows} \\to \\text{bays} \\to \\lbrace
\\text{opening}, \\text{panel}, \\text{pier}, \\text{mount} \\rbrace$$

Per mass: its floor rows (sill and head of every floor, the same on all its facades: a
ground row by the ground gene, mechanical louver rows in towers, a glazed lantern at a
tower's top, dark open bays in parking structures, door rows where balconies go), then per
facade (a mass edge, with the brief's regions) the bays by the genome's module and rhythm
between corner piers wide enough for the reveals, an opening per bay by window type and the
region's class (none on party and hidden walls, few on blind ones), storefronts per
ground-floor unit, and a panel (a mount) wherever a sign slot, mounted prop, facade plant or
skybridge end would fall on glass.

AG2: before the grammar the masses are articulated (`articulate`: corner cuts, setback
ledges, stepped and screen crowns, arcades); every opening is filled with parts (`parts`:
a window frame by style with sills and lintels, louver panels, capsule pods, balconies and
door rows, spandrel panels, shutters, egg crates, screen blades, sunshades, and what grime
and low wealth add: boards, infills, replaced frames, AC units, grilles, dishes, add-on
boxes); every bay line gets the system's own parts (mullion caps, fins, exoskeleton and
diagrid members, timber frames); eaves and ribs run as strips, podium canopies over the
ground floor, masts and spires on the roof; industrial walls on the ground take a block or
concrete dado. A part placed fewer than `parts.INSTANCE_MIN`
times is merged into the shell; the others are the building's instances.

Geometry, on integer millimeters in the building frame, every part closed (the mesh
check):
- the mass envelope: each facade a grid welded on its plane (pier cells per row, zipper
  strips between rows, so no T-junction anywhere and corners match because every facade of
  a mass has the same rows), a reveal pocket per opening with the pane at its back, the
  roof and bottom caps on the ring's corners;
- ring strips (`rings.strip`) extruded: slab bands at floor lines, cornices at the tops of
  masses, parapets on roof edges no other mass covers, eaves and ribs; only above 3 m where
  they leave the footprint, never on party, hidden or blind stretches;
- AG4: roof forms in the attic, finishes, copings, green roofs, an asset for every
  roof item, access huts, vents and skylights (`roofs`);
- on M13's slopes, a plinth under each mass that stands on the base, down into the lowest
  ground under the footprint (`plinth_mm`; AG5 steps it).
"""

from __future__ import annotations

import bisect
import math

from citygen import dmath as M

from ..triangulate import TriangulationError, triangulate
from . import articulate as AR
from . import connections as CN
from . import details as DT
from . import fronts as FR
from . import genome as GN
from . import parts as PT
from . import rings as RG
from . import roofs as RF
from . import systems as SY
from .meshbuf import Buf

NO_WINDOW = ("party", "hidden", "firewall")
STRIP_MIN_Z = 3000           # strips that leave the footprint stay this high (sidewalks)
PIER_MIN = 75
GAP_MIN = 60                 # between openings
EDGE_CLEAR = 60              # an opening's pocket from the neighbor facade's plane
MOUNT_PAD = 100
THIN_MM = 2500               # masses thinner than this get no openings
MAX_WIN_MM = 4000            # window height cap outside curtain walls
DOOR_MIN_Z = 3200            # a balcony's floor line: its slab's underside 3 m up
SNAP = 50                    # punched opening widths (mm), so frames repeat across facades
SPREAD = {"irregular": (0.7, 0.6), "tight": (0.85, 0.3), "loose": (0.5, 1.0)}
# window frame styles: (face width, depth) mm (parts.gen_window)
FRAMES = {"unit": (50, 70), "fixed": (60, 70), "casement": (70, 80), "sash": (80, 90),
          "awning": (60, 70), "industrial": (50, 60), "lattice": (60, 60), "ribbon": (50, 70)}
ODD_FRAMES = ("fixed", "casement", "awning", "industrial")      # replaced windows
WAVE = (-30, -15, 0, 15, 30, 15, 0, -15)                       # screen blades, by position


def _u(bid: str, purpose: str) -> float:
    return GN.u(bid, purpose, "ag1.shell")


def ground_mm(brief: dict) -> int:
    """Where the building's street front stands, over its pivot: 0, or for a building on an
    M14 deck (`floor_grid.level`) the deck's top."""
    fg = brief["building"]["floor_grid"]
    return int(round(float(fg.get("deck_m") or 0.0) * 1000)) if fg.get("level") else 0


def plinth_mm(brief: dict) -> int:
    """How far a building on M13's slopes reaches under its base: from its base (mass z 0,
    the ground floor at the main entrance) down to the lowest ground under its footprint
    and 0.5 m into it, as the blockout's plinth; 0 on flat ground (scope 14.6: AG5 steps it)."""
    fg = brief["building"]["floor_grid"]
    base, low = fg.get("base_m"), fg.get("plinth_m")
    if base is None or low is None or base - low < 0.3:
        return 0
    return int(round((base - low + 0.5) * 1000))


class Facade:
    """One mass edge: a -> b (mm), outward to the right; s along it in mm, 0..L; `soff` the
    s of its start along the brief edge it lies on (a cut or a setback moves it)."""
    __slots__ = ("a", "b", "L", "ux", "uy", "nx", "ny", "j", "u0", "rec", "c0", "c1",
                 "regions", "soff", "d_in", "d_nx", "reveal", "podium")

    def __init__(self, a, b, u0: float):
        self.a, self.b = a, b
        dx, dy = b[0] - a[0], b[1] - a[1]
        Lf = math.sqrt(dx * dx + dy * dy)
        self.L = max(int(round(Lf)), 1)
        self.ux, self.uy = dx / Lf, dy / Lf
        self.nx, self.ny = self.uy, -self.ux
        self.u0 = u0
        self.soff = 0
        self.podium = False
        self.reveal = 0

    def P(self, s: int, z: int) -> tuple[int, int, int]:
        L2 = 2 * self.L
        a, b = self.a, self.b
        return (a[0] + (2 * (b[0] - a[0]) * s + self.L) // L2,
                a[1] + (2 * (b[1] - a[1]) * s + self.L) // L2, z)

    def reg(self, s: int, z: int) -> dict | None:
        sm, zm = (s + self.soff) / 1000.0, z / 1000.0
        for r in self.regions:
            if r["s"][0] <= sm <= r["s"][1] and r["z"][0] <= zm <= r["z"][1]:
                return r
        return None

    def cls(self, s: int, z: int) -> str:
        r = self.reg(s, z)
        if r is not None:
            return r["class"]
        return self.rec["class"] if self.rec else "open"

    def room(self, s: int, z: int, street: int, other: int) -> int:
        """How far out (mm) something may reach here at least 3 m up: over a street or an
        avenue's sidewalk (2 m at least) `street`, over open ground, a park, a plaza, a
        court or water `other`, never over an alley, a service road or a highway's lanes,
        nor in front of a party, blind or hidden wall."""
        r = self.reg(s, z)
        cls = r["class"] if r is not None else (self.rec["class"] if self.rec else "open")
        if cls in ("street", "front"):
            rc = r.get("road_class") if r is not None else None
            return street if rc in ("street", "avenue") else 0
        if cls in ("open", "park", "plaza", "courtyard", "atrium", "canal", "upper"):
            return other
        return 0


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


def _convex(d_in, d_out) -> bool:
    """A real corner turning toward the solid (the solid lies left of every facade)."""
    return _turned(d_in, d_out) and d_in[0] * d_out[1] - d_in[1] * d_out[0] > 0


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
              tall_building: bool, parking: bool, cornice_h: int,
              doors: bool = False, door_floors=frozenset()) -> list[tuple]:
    """(lo, hi, kind, floor, sill, floor line) of every window row of a mass, ascending;
    `sill` is where the opening would start without a door row (the spandrel panel's top
    in a door row's bays without a balcony), else lo."""
    z0, z1 = ms["z0"], ms["z1"]
    n = ms["floors"]
    f0 = ms.get("f0", 0)
    n_all = ms.get("n0", n)
    if n <= 0 or g == "structure":
        return []
    genes, cont = gm["genes"], gm["cont"]
    sysname = genes[f"{g}.system"]
    win = genes[f"{g}.window"]
    sill0 = int(round(cont[f"{g}.sill_m"] * 1000))
    gap0 = int(round(cont[f"{g}.head_m"] * 1000))
    if win in ("tall", "slot"):
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
        elif f + f0 == 0 and z0 <= 50 and ground is not None:
            if ground == "blank":
                if n_all > 1 or H < 5000:
                    continue
                # a shed of one tall floor: a clerestory under its eaves
                head = H - gap0
                sill = head - (900 if win != "strip" else 1400)
            if ground == "storefront":
                kind, sill, head = "shop", 300, H - max(500, H // 6)
            elif ground == "lobby":
                kind, sill, head = "shop", 150, H - 400
        elif win in ("clerestory", "strip") and sysname in SY.INDUSTRIAL:
            hgt = 900 if win == "clerestory" else 1400
            head = H - gap0
            sill = head - hgt
        elif win in ("slit", "square") and sysname == "shanty_patchwork":
            sill = head - (500 if win == "slit" else 800)
        elif win == "louver":
            kind = "louver"
        elif win == "pod":
            kind = "pod"
        if not parking and kind == "win" and g == "body" and n_all >= 24 and \
                0 < f + f0 < n_all - 2 and (f + f0 + 1) % mech == 0 and f not in door_floors:
            kind = "louver"          # (a mechanical floor, unless a skybridge lands on it)
        if is_top and f == n - 1 and tall_building and genes["crown"] == "lantern" and \
                kind == "win":
            kind, sill, head = "lantern", 150, H - 150
        if kind in ("win", "louver") and sysname not in SY.CURTAIN and \
                head - sill > MAX_WIN_MM:
            sill = head - MAX_WIN_MM
        if f == n - 1 and cornice_h:
            head = min(head, H - cornice_h - 80)
        sill = max(sill, 100)
        head = min(head, H - 100)
        if head - sill < 400:
            continue
        full = zf + sill
        if doors and kind == "win" and zf >= DOOR_MIN_Z and head - 150 >= 1800:
            sill = 150
        elif f in door_floors and kind == "win" and head - 150 >= 1800:
            sill = 150             # (AG4: a skybridge lands on this floor)
        rows.append((zf + sill, zf + head, kind, f, full, zf))
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
                 sysname: str, key: str, open_p: float = 0.55,
                 nominal: int = 0) -> list[tuple[int, int]]:
    """The openings of bay j (b0 to b1). A punched window's width comes from the genome's
    bay (`nominal`), fitted into the bay, so a building repeats one window size across its
    facades (scope principle 5); curtain walls, ribbons and patchwork fill their bays."""
    wb = b1 - b0
    nb = nominal or wb
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
    if sysname in SY.CURTAIN and win in ("full", "split", "banded"):
        mull = max(60, int(wb * (1.0 - wwr)))
        if win == "split" and wb > 1800:
            half = (wb - 2 * mull) // 2
            return [(b0 + mull // 2, b0 + mull // 2 + half),
                    (b1 - mull // 2 - half, b1 - mull // 2)]
        return [(b0 + mull // 2, b1 - mull // 2)]
    if win in ("ribbon", "strip"):
        ow = wb - 200
    elif win in ("louver", "pod"):
        ow = wb - max(160, int(wb * (1.0 - wwr)))
    elif win == "slot":
        ow = int(nb * wwr * 0.55)
    elif win == "wide":
        ow = int(nb * wwr * 1.4)
    elif win == "square":
        ow = int(nb * wwr * 1.2)
    elif win == "paired":
        tot = min(int(nb * min(wwr * 1.3, 0.85)), int(wb * 0.85))
        gap = max(120, tot // 6)
        each = (tot - gap) // 2 // SNAP * SNAP
        if each < 350:
            return []
        return [(mid - gap // 2 - each, mid - gap // 2), (mid + gap // 2, mid + gap // 2 + each)]
    else:
        ow = int(nb * wwr)
    ow = min(ow, wb - 2 * PIER_MIN)
    if win not in ("ribbon", "strip"):
        ow = ow // SNAP * SNAP           # punched openings in 5 cm steps: their frames repeat
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
                     "base": False, "parts": {}, "articulation": [], "crown": False,
                     "irregular": False, "dado": False}
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
        self.mounts_raw = self._mounts(0)
        # AG3: the street fronts' doors, every opening cut (per brief edge, for the mounts
        # check), the entrances and units given a door, the facades per brief edge
        self.doors: list[dict] = []
        self.decals: list[dict] = []
        # (the ground the street front stands on: an M14 deck's top for a building on one)
        self.ground = ground_mm(brief)
        self.opened: dict[int, list] = {}
        self.done_units: set[int] = set()
        self.done_ents: set[int] = set()
        self.band_facades: list[tuple] = []
        self.all_facades: list[tuple] = []
        self.checks: dict = {}
        self.band_z: int | None = None
        self.used["front"] = {}
        # AG2
        self.parts = PT.PartSet()
        self.marks = AR.marks(brief, self.units_by_edge)
        self.arcades: list[dict] = []
        self.plinth = plinth_mm(brief)
        self.irr = float(gm["cont"].get("irreg", 0.0))
        self.res = b["use"] in SY.BALCONY_USES
        self.inst: list[dict] = []
        # AG4: what the asset keeps out of, roof forms, the roof items' assets, green roofs
        self.clear = RF.Clear(brief)
        self.bridges = RF.Clear(brief, ("skybridge",))
        self.landings = CN.landings_of(self)
        self.landed: dict[str, dict] = {}
        self.portal_recs: list[dict] = []
        self.roof_forms: list[dict] = []
        self.roof_items: list[dict] = []
        self.green_done: list[str] = []

    # -- what must fall on a panel -------------------------------------------------------

    def _mounts(self, pad: int = MOUNT_PAD) -> dict[int, list[tuple]]:
        """Per brief edge, (s0, s1, z0, z1) mm of everything that must hang on solid wall:
        sign slots, mounted props (AG3: awnings too), facade plants, skybridge ends; `pad`
        round each."""
        out: dict[int, list] = {}
        br = self.br

        def add(at, z, w, h):
            if at is None:
                return
            s = int(round(at["s"] * 1000))
            out.setdefault(at["edge"], []).append(
                (s - w // 2 - pad, s + w // 2 + pad,
                 int(round(z * 1000)) - h // 2 - pad, int(round(z * 1000)) + h // 2 + pad))
        for s in br["sign_slots"]:
            if s["mount"] == "roof":
                continue
            w = 300 if s["mount"] == "blade" else int(s["width_m"] * 1000)
            add(s["at"], s["position"][2], w, int(s["height_m"] * 1000))
        size = {"ac_unit": (1000, 800), "wall_light": (400, 400), "sign": (300, 1500),
                "overhead_cable": (300, 300)}
        for p in br["props"]:
            if not p["on_wall"]:
                continue
            if p["kind"] == "awning":
                # (AG3) the awning's rail along its unit, on the fascia over the shopfront
                add(p["at"], p["position"][2], int(p["scale"][0] * 1000), 300)
                continue
            if p["kind"] not in size:
                continue
            w, h = size[p["kind"]]
            add(p["at"], p["position"][2], w, h)
        for p in br["plants"]:
            add(p["at"], p["position"][2], 1500, int(max(p["height_m"], 1.0) * 1000))
        for s in br["skybridges"]:
            # (AG4: the bridge's corridor and a margin: its deck structure 1 m under the
            # landing, 0.5 m beside it, so no sill, shutter or shade enters it)
            h = int(max(s["levels"], 1) * s["level_height_m"] * 1000) + 1600
            add(s["at"], s["z_m"] + (h - 2400) / 2000.0, int(s["width_m"] * 1000) + 1000, h)
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
            rings = [tidied[r][0] for r in keep]
            masses.append({"k": k, "role": m["role"], "shape": m["shape"],
                           "z0": int(round(m["z"][0] * 1000)), "z1": int(round(m["z"][1] * 1000)),
                           "rings": rings,
                           "eidx": [tidied[r][1] for r in keep], "rid": keep,
                           "deriv": [[False] * len(r) for r in rings],
                           "floors": int(m["floors"]["count"]),
                           "n0": int(m["floors"]["count"]), "f0": 0})
        self.masses = masses
        edge_of = {}
        for j, e in enumerate(br["edges"]):
            edge_of[(e["mass"], e["ring"], e["i"])] = j
        self.edge_of = edge_of
        # what of each brief edge the tidied rings keep (s spans in mm, before articulation):
        # a mount off them stood on a stretch the tidying took away (`fronts.mount_check`)
        kept: dict[int, list[tuple[float, float]]] = {}
        for ms in masses:
            for ring, eidx, rid in zip(ms["rings"], ms["eidx"], ms["rid"]):
                for i in range(len(ring)):
                    j = edge_of.get((ms["k"], rid, eidx[i]))
                    if j is None:
                        continue
                    a0, ux, uy, _ = AR._edge_geom(br, j)
                    s = [(p[0] - a0[0]) * ux + (p[1] - a0[1]) * uy
                         for p in (ring[i], ring[(i + 1) % len(ring)])]
                    kept.setdefault(j, []).append((min(s), max(s)))
        self.kept = kept
        AR.articulate(self)
        CN.portals(self)
        RF.plan(self)
        masses = self.masses
        groups = set()
        for ms in masses:
            if ms.get("roof") and ms["roof"]["zb"] <= ms["z0"] + 50:
                # (AG4: a roof storey, all roof)
                RF.build_form(self, ms, self._wall_slot(ms, SY.role_group(ms["role"])))
                continue
            if ms["z1"] - ms["z0"] < 50 or len(RG.clean(ms["rings"][0])) < 3:
                continue
            self.stats["masses"] += 1
            g = SY.role_group(ms["role"])
            if ms["shape"] == "ring":
                self._wheel(ms)
                continue
            if ms.get("screen"):
                self._screen(ms)
                continue
            if g != "structure":
                groups.add(g)
            self._mass(ms, g)
        depth = plinth_mm(br)
        if depth:
            for ms in masses:
                if ms["z0"] <= 50 and ms["z1"] - ms["z0"] >= 50 and ms["shape"] != "ring" and \
                        len(RG.clean(ms["rings"][0])) >= 3:
                    self.buf.layer = 1
                    self.buf.new_part()
                    if self._extrude(ms["rings"][0], None, -depth, 0, "structure"):
                        self.stats["plinths"] = self.stats.get("plinths", 0) + 1
                    self.buf.layer = 0
        # AG4: sky stations and portal mouths; an asset for every roof item, green roofs,
        # the access hut, vents, skylights
        CN.station(self)
        CN.mouth_frames(self)
        RF.items(self)
        RF.green_roofs(self)
        RF.extras(self)
        self._mast()
        self._columns()
        # AG3: doors for what no band could take, the mounts' hardware, blind and fire walls
        FR.leftovers(self)
        FR.hardware(self)
        FR.walls(self)
        DT.details(self)          # AG4: downpipes, fire escapes, ducts, vents, cables, cameras
        self.checks = {"mounts": FR.mount_check(self), "access": FR.door_check(self)}
        self._finish_parts()
        self.used["groups"] = [g for g in GN.GROUPS if g in groups]
        self.used["trim"] = self.stats["strips"] > 0
        self.used["glass"] = self.stats["openings"] > 0
        arrs = self.buf.arrays()
        return {"buf": self.buf, "arrays": arrs, "stats": self.stats, "used": self.used,
                "masses": self.mass_info, "parts": self.inst, "doors": self.doors,
                "decals": self.decals,
                "band_m": None if self.band_z is None else self.band_z / 1000.0,
                "checks": self.checks,
                # AG4: every roof item's asset, the green roofs built, skybridge landings,
                # portals and sky stations
                "roof_items": self.roof_items, "green": list(self.green_done),
                "landings": CN.landing_records(self), "portals": self.portal_recs}

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

    def _j(self, ms: dict, r: int, i: int):
        """The brief edge of a mass's ring edge (AG4: a portal's pieces carry theirs)."""
        if "ej" in ms:
            return ms["ej"][r][i]
        return self.edge_of.get((ms["k"], ms["rid"][r], ms["eidx"][r][i]))

    def _bridge_free(self, fa: Facade, s0: int, s1: int, z0: int, z1: int, depth: int
                     ) -> bool:
        """AG4: whether a part of a facade (s0..s1, z0..z1, `depth` out) keeps out of every
        skybridge's corridor."""
        if not self.bridges.segs:
            return True
        a, b = fa.P(s0, 0), fa.P(s1, 0)
        ox, oy = fa.nx * depth, fa.ny * depth
        xs = (a[0], b[0], a[0] + ox, b[0] + ox)
        ys = (a[1], b[1], a[1] + oy, b[1] + oy)
        return not self.bridges.hits(min(xs), min(ys), max(xs), max(ys), z0, z1)

    def _wall_slot(self, ms: dict, g: str) -> str:
        """The slot of a mass's walls (as `_mass` picks it)."""
        if g == "structure":
            return "structure"
        sysname = self.gm["genes"][f"{g}.system"]
        if sysname == "punched_concrete":
            return self.gm["genes"]["finish"]
        return SY.SYSTEMS[sysname]["wall"]

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
        ms["thick"] = thick
        is_top = not any(o is not ms and o["z0"] >= ms["z1"] - 50 and
                         RG.in_poly(_centroid(o["rings"][0]), [rings[0]]) >= 0
                         for o in self.masses)
        feats = self.used["features"].setdefault(g, [])
        # cornice and bands decided first: they bound the rows
        cornice = genes.get(f"{g}.cornice", "none") if sysname and not ms.get("roof") \
            else "none"
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
        doors = sysname is not None and self.res and \
            genes.get(f"{g}.balcony", "none") not in ("none", "balconette") and \
            g in ("base", "body") and ms["floors"] >= 3
        rows = mass_rows(ms, g, gm, is_top, ground, self.tall, self.parking, cornice_h,
                         doors, CN.door_floors(self, ms))
        # AG3: a mass on the ground has its street front (`fronts`) up to its first floor
        # line; the rows above it are the shell's
        band = FR.band_top(ms) if ms["z0"] <= self.ground + 50 and ms["shape"] == "prism" \
            else None
        ground_row = None
        if band is not None:
            # (a floor taller than the band keeps what lies over the band in the shell: a
            # shed's clerestory)
            ground_row = next((r for r in rows if r[5] < band and r[0] < band - 400), None)
            rows = [r for r in rows if r[5] >= band or r[0] >= band]
            ms["band"] = band
            self.band_z = band if self.band_z is None else min(self.band_z, band)
        reveal = int(round(cont[f"{g}.reveal_m"] * 1000)) if sysname else 0
        corner = int(round(cont[f"{g}.corner_m"] * 1000)) if sysname else 0
        corner = {"heavy": corner * 2, "tight": max(corner // 2, 100)}.get(genes["corner"],
                                                                         corner)
        bay = int(round(cont[f"{g}.bay_m"] * 1000)) if sysname else 0
        allow = sysname is not None and thick >= THIN_MM
        info = {"mass": k, "group": g, "system": sysname, "rows": len(rows), "openings": 0}
        self.buf.new_part()
        up_part = self.buf.part
        facades = []
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
                j = self._j(ms, r, i)
                fa.rec = br["edges"][j] if j is not None else None
                if ms["deriv"][r][i]:
                    # a cut's or an offset's own edge: its neighbor's class, nothing mounted
                    fa.j = None
                    fa.regions = []
                else:
                    fa.j = j
                    fa.regions = _fire(fa.rec["regions"]) if fa.rec else []
                    if fa.rec is not None:
                        a0, ux, uy, _ = AR._edge_geom(br, j)
                        fa.soff = int(round((a[0] - a0[0]) * ux + (a[1] - a0[1]) * uy))
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
                # straight (a front split in two), just the reveal's clearance; at a convex
                # corner at least the reveal, so the pockets of the two facades never meet
                fa.c0 = max(corner if _turned(d_in, d_out) else 0,
                            _corner_clear(d_in, d_out, reveal),
                            reveal + EDGE_CLEAR if _convex(d_in, d_out) else 0)
                fa.c1 = max(corner if _turned(d_out, d_nx) else 0,
                            _corner_clear(d_out, d_nx, reveal),
                            reveal + EDGE_CLEAR if _convex(d_out, d_nx) else 0)
                ok = allow and not _blocked(fa, reveal + EDGE_CLEAR, all_edges)
                fwall = wall
                if ms.get("portal") and ms["deriv"][r][i] and fa.j is None:
                    # (AG4: a portal's corridor wall: a metal lining, glazed at a station)
                    fwall = "portal_lining"
                    ok = ok and bool(ms.get("station"))
                fa.d_in, fa.d_nx, fa.reveal = d_in, d_nx, max(reveal, 60)
                facades.append((fa, r, i, ok))
                self.all_facades.append((fa, ms))
                if band is None or band < ms["z1"]:
                    info["openings"] += self._facade(ms, g, fa, rows, fwall, sysname, reveal,
                                                     bay, ok)
        if band is not None:
            self.buf.layer = 1
            self.buf.new_part()
            fb = FR.Band(self, ms, g, wall, sysname, reveal, bay, band, ground_row, facades)
            plans = [(fa, r, i, fb.plan(fa, ok)) for fa, r, i, ok in facades]
            fb.rehome(plans)
            for fa, r, i, ops in plans:
                fb.emit(fa, r, i, ops)
                self.band_facades.append((fa, ms))
            FR.caps(fb, roof=band >= ms["z1"])
            self.buf.layer = 0
            self.buf.part = up_part
        self._caps(ms, wall, band)
        if ms.get("roof"):
            RF.build_form(self, ms, wall)       # AG4: the roof form in the attic
        self.mass_info.append(info)
        if sysname is None:
            if ms["role"] == "deck":
                CN.deck(self, ms)               # AG4: paving, balustrades, planters
            return
        CN.courts(self, ms)                     # AG4: court floors and galleries
        # strips: parapet on open roof edges, cornice, slab bands
        top_open = [[not self._covered_above(ms, ring[i], ring[(i + 1) % len(ring)])
                     for i in range(len(ring))] for ring in rings]
        if ms.get("portal_floor"):
            top_open = [[False] * len(ring) for ring in rings]     # (AG4: a portal's floor)
        par = genes.get(f"{g}.parapet", "none")
        if is_top and genes["crown"] == "flat" and g != "base":
            par = "none"
        if is_top and genes["crown"] == "parapet":
            par = "high"
        if not is_top and par == "none" and any(any(r) for r in top_open):
            par = "low"                # a ledge or a terrace on a lower mass: a railing
        if ms.get("roof"):
            par = "none"               # (AG4: eaves instead)
        if par != "none":
            hp = int(round(cont[f"{g}.parapet_m"] * 1000))
            if par == "low":
                hp = max(300, hp // 2)
            t = max(200, reveal + 80)
            # AG4: a coping on the parapet's top (metal flashing, or stone)
            cop = RF.coping_slot(self)
            hz = hp - 50 if cop else hp
            if self._strips(ms, top_open, 0, -t, ms["z1"], ms["z1"] + hz, "trim", t,
                            need_out=False):
                feats.append("parapet")
                if cop and self._strips(ms, top_open, 30, -(t + 30), ms["z1"] + hz,
                                        ms["z1"] + hp, cop, t + 30, need_out=False):
                    self.stats["copings"] = self.stats.get("copings", 0) + 1
        if cornice_h:
            ok = self._edge_ok(ms, ms["z1"] - cornice_h, ms["z1"])
            mask = [[o and q for o, q in zip(r1, r2)] for r1, r2 in zip(top_open, ok)]
            if self._strips(ms, mask, cornice_d, 0, ms["z1"] - cornice_h, ms["z1"], "trim",
                            cornice_d, need_out=True):
                feats.append("cornice")
        bands = genes.get(f"{g}.bands", "none")
        feature = SY.SYSTEMS[sysname].get("feature")
        if (bands != "none" and ms["floors"] >= 2) or feature == "ribs":
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
            if feature == "ribs":
                # hangar cladding: a rib every 3.5 m up the wall, whatever the floors
                bd, bh = 120, 220
                levels = list(range(ms["z0"] + 3500, ms["z1"] - 1499, 3500))
            done = False
            for zf in levels:
                za, zb = zf - bh // 2, zf + bh // 2
                if za < STRIP_MIN_Z or any(lo < zb + 20 and hi > za - 20 for lo, hi, *_ in
                                           rows):
                    continue
                ok = self._edge_ok(ms, za, zb)
                if self._strips(ms, ok, bd, 0, za, zb, "trim", bd, need_out=True):
                    done = True
            if done:
                feats.append("bands")
                if feature == "ribs":
                    self.used["parts"].setdefault(g, set()).add("ribs")
        if feature == "eaves":
            self._eaves(ms, g, rows)
        RF.finish(self, ms, top_open)        # AG4: a flat roof's finish

    def _edge_ok(self, ms: dict, za: int, zb: int) -> list[list[bool]]:
        """Per ring edge: whether a strip may leave the footprint there between za and zb
        (no party, hidden or blind stretch in that height)."""
        out = []
        k = ms["k"]
        for r, ring in enumerate(ms["rings"]):
            row = []
            for i in range(len(ring)):
                j = self._j(ms, r, i)
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
                self.buf.layer = 1 if z1 <= ms.get("band", -1) else 0
                self.buf.new_part()
                if self._extrude(outer, hole, z0, z1, slot):
                    made = True
                    self.stats["strips"] += 1
                self.buf.layer = 0
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
        so = fa.soff
        mounts = [(m0 - so, m1 - so, z0, z1) for m0, m1, z0, z1 in
                  (self.mounts.get(fa.j, []) if fa.j is not None else [])]
        balc = []
        for lo, hi, kind, f, full, zf in rows:
            ops = []
            balc.append(self._balcony_bays(fa, ms, g, cuts, lo, full, zf, mounts)
                        if allow and full > lo + 200 else {})
            if allow:
                zm = (lo + hi) // 2
                if kind == "shop" and units:
                    for un in units:
                        s = int(round(un["at"]["s"] * 1000)) - so
                        w = int(round(un["width_m"] * 1000))
                        a_, b_ = max(s - w // 2 + 250, fa.c0), min(s + w // 2 - 250, L - fa.c1)
                        if b_ - a_ >= 800 and fa.cls((a_ + b_) // 2, zm) not in NO_WINDOW:
                            ops.append((a_, b_, "storefront", -1))
                            self.stats["storefronts"] += 1
                else:
                    back = {"win": "glass", "shop": "storefront", "louver": "louver",
                            "void": "void", "lantern": "glass", "pod": "void"}[kind]
                    w_ = "full" if kind == "lantern" and sysname in SY.CURTAIN \
                        else ("ribbon" if kind == "lantern" else win)
                    if kind == "shop" and win in ("sparse", "clerestory", "strip", "louver",
                                                  "pod", "slot") or \
                            kind == "shop" and sysname == "shanty_patchwork":
                        w_ = "single"
                    if kind == "louver" and win in ("clerestory", "strip", "sparse", "slit",
                                                    "patch", "square", "pod"):
                        w_ = "single"
                    for jb, (b0, b1) in enumerate(cuts):
                        self.stats["bays"] += 1
                        for a_, b_ in bay_openings(b0, b1, jb, len(cuts), w_, rhythm, wwr,
                                                   sysname, f"{key}|{f}", open_p, bay):
                            c = fa.cls((a_ + b_) // 2, zm)
                            if c in NO_WINDOW:
                                continue
                            if c == "blind":
                                if _u(key, f"blind{f}.{jb}") > 0.3:
                                    continue
                                cw = (b_ - a_) * 3 // 10
                                a_, b_ = (a_ + b_) // 2 - cw, (a_ + b_) // 2 + cw
                            ops.append((a_, b_, back, jb))
                kept = []
                for op in ops:
                    if any(op[0] < m1 and op[1] > m0 and lo < z1 and hi > z0
                           for m0, m1, z0, z1 in mounts):
                        self.stats["mount_panels"] += 1
                        continue
                    kept.append(op)
                # AG4: a skybridge's landing door where its deck is this row's floor
                kept = CN.landing_ops(self, fa, (lo, hi, kind, f, full, zf), kept)
                ops = _merge_ok(kept, fa.c0, fa.c1, L)
                if sysname == "spandrel_ribbon" and kind == "win":
                    # a ribbon: the bays' openings one long opening, the mullions parts
                    merged: list[tuple] = []
                    for op in ops:
                        if merged and op[0] - merged[-1][1] <= 260:
                            merged[-1] = (merged[-1][0], op[1], op[2], -1)
                        else:
                            merged.append(op)
                    ops = merged
            elif sysname and fa.j in self.landings and ms["thick"] >= CN.LANDING_THIN:
                # AG4: a skybridge landing on a mass too thin for windows: its door alone
                ops = CN.landing_ops(self, fa, (lo, hi, kind, f, full, zf), [])
            c = [0]
            for a_, b_, *_ in ops:
                c += [a_, b_]
            c.append(L)
            if patch_cols is not None:
                # the facade's patch columns, except inside an opening or within 50 mm of a
                # column this row has (two columns a millimeter apart could round to one point)
                extra = [x for x in patch_cols if not any(a_ < x < b_ for a_, b_, *_ in ops)
                         and all(abs(x - y) >= 50 for y in c)]
                c = sorted(set(c) | set(extra))
            cols.append(c)
            row_ops = {}
            for k_, (a_, b_, back, jb) in enumerate(ops):
                # the wall beside the opening, halved where a neighbor shares the pier
                pl = a_ - (ops[k_ - 1][1] if k_ else 0)
                pr = (ops[k_ + 1][0] if k_ + 1 < len(ops) else L) - b_
                pl = pl // 2 if k_ else pl - fa.c0 // 2
                pr = pr // 2 if k_ + 1 < len(ops) else pr - fa.c1 // 2
                row_ops[a_] = (b_, back, jb, pl, pr)
            ops_by_row.append(row_ops)
            n_open += len(ops)
            if fa.j is not None:
                rec = self.opened.setdefault(fa.j, [])
                for a_, b_, *_ in ops:
                    rec.append((a_ + so, b_ + so, lo, hi))
        self.stats["openings"] += n_open
        self._wall(ms, fa, rows, cols, ops_by_row, wall, reveal, key, g, sysname, cuts, balc)
        if allow and sysname:
            self._lines(fa, ms, g, sysname, cuts, rows, reveal, mounts)
        if sysname and ms["z0"] <= 50 and not ms.get("arcade"):
            self._canopy(fa, ms, mounts)
        return n_open

    def _wall(self, ms: dict, fa: Facade, rows: list, cols: list, ops_by_row: list,
              wall: str, reveal: int, key: str, g: str = "body", sysname=None,
              cuts=(), balc=()) -> None:
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

        z0, z1 = ms.get("band", ms["z0"]), ms["z1"]
        prev, pz = [0, L], z0
        o = (int(round(-fa.nx * reveal)), int(round(-fa.ny * reveal)))
        base = self.gm["genes"]["base"]
        # an industrial wall on the ground: its dado line (the same on every facade of the
        # mass, so the corners stay welded) where the first row starts 0.3 m above it
        dado = 0
        if sysname in SY.INDUSTRIAL and z0 <= 50 and self.gm["genes"]["dado"] != "none" and \
                "band" not in ms:
            dz = int(round(self.gm["cont"]["dado_m"] * 1000))
            if (rows[0][0] if rows else z1) >= z0 + dz + 300:
                dado = dz
                self.used["dado"] = True
        plinth = base if rows and z0 <= 50 and base != "wall" and wall != "structure" and \
            not dado and "band" not in ms else None
        if plinth:
            self.used["base"] = True        # the strip under the ground row in its finish
        if dado:
            zipper(prev, pz, [0, L], z0 + dado, self.gm["genes"]["dado"])
            prev, pz = [0, L], z0 + dado
        for row, c, ops, bset in zip(rows, cols, ops_by_row, balc or [{}] * len(rows)):
            lo, hi, kind, f = row[:4]
            zipper(prev, pz, c, lo, plinth if pz == z0 else None)
            for i in range(len(c) - 1):
                a_, b_ = c[i], c[i + 1]
                if a_ in ops and ops[a_][0] == b_:
                    self._pocket(fa, a_, b_, lo, hi, o, ops[a_][1], wall, key, f, i)
                    if sysname:
                        self._fill(fa, ms, g, sysname, row, a_, b_, ops[a_], reveal, wall,
                                   key, i, cuts, bset)
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

    # -- AG2: what fills an opening -----------------------------------------------------

    def _frame(self, fa: Facade, style: str, w: int, h: int, r: int, s: int, z: int,
               sill=None, lintel=None) -> None:
        fw, fd = FRAMES[style]
        p = {"style": style, "w": PT.q(w), "h": PT.q(h), "r": r, "fw": fw, "fd": fd}
        if sill:
            p["sill"] = sill
        if lintel:
            p["lintel"] = lintel
        self.parts.on(fa, "window", p, s, z)

    def _balcony_bays(self, fa: Facade, ms: dict, g: str, cuts, lo: int, full: int, zf: int,
                      mounts) -> dict:
        """{bay: (b0, b1, depth)} of a door row's balconies: by the pattern gene, on bays
        wide enough, as deep as the facade's room allows (`Facade.room`), off every mount."""
        genes, cont = self.gm["genes"], self.gm["cont"]
        style = genes.get(f"{g}.balcony", "none")
        if style in ("none", "balconette") or zf < DOOR_MIN_Z or not cuts:
            return {}
        pat = genes[f"{g}.balcony_pat"]
        n = len(cuts)
        want = int(round(cont[f"{g}.balcony_m"] * 1000))
        out = {}
        for jb, (b0, b1) in enumerate(cuts):
            if pat == "alternate" and jb % 2:
                continue
            if pat == "columns" and (jb % 3 != 1 if n >= 3 else jb != n // 2):
                continue
            if pat == "ends" and jb not in (0, n - 1):
                continue
            if b1 - b0 - 160 < 900:
                continue
            d = PT.q(min(want, fa.room((b0 + b1) // 2, zf + 1000, 1200, 1500)))
            if d < 600:
                continue
            if any(b0 < m1 and b1 > m0 and zf - 300 < z1 and zf + 1300 > z0
                   for m0, m1, z0, z1 in mounts):
                continue
            if not self._bridge_free(fa, b0, b1, zf - 300, zf + 1300, d):
                continue                       # (AG4: off every skybridge's corridor)
            out[jb] = (b0, b1, d)
        return out

    def _fill(self, fa: Facade, ms: dict, g: str, sysname: str, row: tuple, a_: int,
              b_: int, op: tuple, reveal: int, wall: str, key: str, i: int, cuts,
              bset: dict) -> None:
        """The parts of one opening: its frame (or louver panel, pod, board, infill), door
        row balcony or spandrel panel, the system's own (shutters, egg crate, screen blades,
        ribbon units and sunshades, balconettes) and what grime and low wealth add."""
        lo, hi, kind, f, full, zf = row
        _, back, jb, pl, pr = op
        w, h = b_ - a_, hi - lo
        if jb == -2:
            CN.landing_door(self, fa, a_, b_, lo, hi, reveal)      # (AG4)
            return
        if w < 300 or h < 300 or kind == "void":
            return
        genes, cont = self.gm["genes"], self.gm["cont"]
        feat = SY.SYSTEMS[sysname].get("feature")
        used = self.used["parts"].setdefault(g, set())
        P = self.parts
        mid = (a_ + b_) // 2
        r = reveal
        qw, qh = PT.q(w), PT.q(h)
        if kind == "louver":
            P.on(fa, "louver", {"w": qw, "h": qh, "r": r, "n": max(3, min(16, h // 220)),
                                "bd": 140, "tilt": 30}, mid, lo)
            if feat == "louvers":
                used.add("louvers")
            return
        if kind == "pod":
            if lo >= STRIP_MIN_Z:
                # one capsule for the whole building (as a capsule tower's are), centered
                # in its bay; a bay narrower than it takes a capsule of its own width
                pw = min(PT.q(cont[f"{g}.bay_m"] * 800), qw)
                ph = PT.q(min(h, 2800))
                P.on(fa, "pod", {"w": pw, "h": ph, "r": r,
                                 "d": PT.q(cont[f"{g}.pod_m"] * 1000),
                                 "pr": PT.q(min(pw, ph) * 3 // 10)}, mid, lo)
                used.add("capsules")
            else:
                self._frame(fa, "fixed", w, h, r, mid, lo)
            return
        if kind in ("shop", "lantern"):
            self._frame(fa, "unit", w, h, r, mid, lo)
            return
        curtain = sysname in SY.CURTAIN
        irr = self.irr
        u1 = _u(key, f"irr{f}.{i}")
        if not curtain and irr > 0:
            if u1 < 0.10 * irr:
                P.on(fa, "panel", {"style": "board", "w": qw, "h": qh}, mid, lo)
                self.used["irregular"] = True
                return
            if u1 < 0.14 * irr:
                P.on(fa, "panel", {"style": "infill", "w": qw, "h": qh, "r": r,
                                   "slot": wall if not wall.startswith("patch") else
                                   "patch_panel"}, mid, lo)
                self.used["irregular"] = True
                return
            if feat == "addons" and lo - 150 >= STRIP_MIN_Z and u1 < 0.14 * irr + 0.10 and \
                    self._bridge_free(fa, a_ - 200, b_ + 200, lo - 150, hi + 150, 500):
                P.on(fa, "panel", {"style": "addon", "w": PT.q(w + 400),
                                   "h": PT.q(min(h + 300, 2400)), "d": 500}, mid, lo - 150)
                used.add("addons")
                self.used["irregular"] = True
                return
        style = genes[f"{g}.frame"]
        if irr > 0 and _u(key, f"odd{f}.{i}") < 0.12 * irr:
            style = GN.pick(key, f"oddk{f}.{i}", [x for x in ODD_FRAMES if x != style], None,
                            "ag2.shell")
            self.used["irregular"] = True
        door = full > lo + 200
        sills = genes[f"{g}.sills"] == "stone"
        if feat == "ribbon":
            self._ribbon(fa, g, a_, b_, lo, hi, r, cuts)
        else:
            self._frame(fa, style, w, h, r, mid, lo,
                        (50, 70, 60) if sills and not door else None,
                        (25, 220, 90) if sysname == "punched_brick" else None)
            used.add("frame")
            if sills:
                used.add("sills")
        if door:
            if jb in bset and a_ < (bset[jb][0] + bset[jb][1]) // 2:
                # the bay's balcony, once (by its first opening, where a bay has two)
                b0, b1, d = bset[jb]
                st = genes[f"{g}.balcony"]
                p = {"style": st, "w": PT.q(b1 - b0 - 160), "d": d, "t": 200, "rh": 1050}
                if irr > 0 and _u(key, f"encl{f}.{jb}") < 0.6 * irr:
                    hf = (ms["z1"] - ms["z0"]) // max(ms["floors"], 1)
                    p.update(style="enclosed", eh=PT.q(hf - 250))
                    self.used["irregular"] = True
                P.on(fa, "balcony", p, (b0 + b1) // 2, zf)
                used.add("balcony")
            elif jb not in bset:
                P.on(fa, "spandrel", {"w": qw, "h": PT.q(full - lo), "r": r}, mid, lo)
        if feat == "shutters" and h >= 900:
            sw = PT.q(w // 2)
            if pl >= sw + 80 and pr >= sw + 80:
                P.on(fa, "shutter", {"w": sw, "h": qh}, a_ - 40 - sw // 2, lo)
                P.on(fa, "shutter", {"w": sw, "h": qh}, b_ + 40 + sw // 2, lo)
                used.add("shutters")
        if feat == "eggcrate" and genes.get(f"{g}.crate") == "eggcrate" and \
                lo - 150 >= STRIP_MIN_Z and pl >= 170 and pr >= 170:
            P.on(fa, "panel", {"style": "eggcrate", "w": qw, "h": qh, "d": 400, "t": 150,
                               "slot": wall}, mid, lo)
            used.add("eggcrate")
        if feat == "screen" and lo - 150 >= STRIP_MIN_Z:
            nb = 3 if w >= 1800 else 2
            pat = genes.get(f"{g}.blades", "flat")
            for k in range(nb):
                s = a_ + w * (2 * k + 1) // (2 * nb)
                ang = 0 if pat == "flat" else ((15 if (k + f) % 2 else -15)
                                               if pat == "alternate" else WAVE[(k + jb + f) % 8])
                P.on(fa, "panel", {"style": "screen", "w": PT.q(min(w // nb, 600)),
                                   "h": PT.q(h + 300), "t": 30, "off": 330}, s, lo - 150,
                     extra_deg=ang)
            used.add("screen")
        if genes.get(f"{g}.balcony") == "balconette" and genes[f"{g}.window"] == "tall" and \
                lo >= STRIP_MIN_Z:
            P.on(fa, "balconette", {"w": qw, "rh": 900}, mid, lo)
            used.add("balcony")
        if curtain or irr <= 0:
            return
        use = self.br["building"]["use"]
        if lo >= STRIP_MIN_Z and use in ("residential", "hotel", "office", "retail") and \
                w >= 800 and jb not in bset and _u(key, f"ac{f}.{i}") < 0.25 * irr and \
                self._bridge_free(fa, a_, b_, lo - 100, lo + 600, 400):
            P.on(fa, "ac", {"w": 660, "h": 420, "do": 350, "di": min(250, max(r - 30, 20))},
                 mid, full if door else lo)
            self.used["irregular"] = True
        if f + ms.get("f0", 0) <= 1 and lo < 6000 and jb not in bset and \
                _u(key, f"gr{f}.{i}") < 0.9 * irr:
            P.on(fa, "grille", {"w": qw, "h": qh}, mid, lo)
            self.used["irregular"] = True
        if self.res and lo >= STRIP_MIN_Z and pr >= 900 and _u(key, f"dish{f}.{i}") < 0.06 * irr:
            P.on(fa, "dish", {"rd": 400}, b_ + 450, lo + h // 2 - 400)
            self.used["irregular"] = True

    def _ribbon(self, fa: Facade, g: str, a_: int, b_: int, lo: int, hi: int, r: int,
                cuts) -> None:
        """A ribbon window's units, one per bay it spans, and their sunshades."""
        shade = self.gm["genes"].get(f"{g}.shade") == "blade" and hi + 140 >= STRIP_MIN_Z
        for b0, b1 in cuts:
            x0, x1 = max(b0, a_), min(b1, b_)
            if x1 - x0 < 400:
                continue
            self._frame(fa, "ribbon", x1 - x0, hi - lo, r, (x0 + x1) // 2, lo)
            if shade and fa.room((x0 + x1) // 2, hi + 140, 450, 450) >= 450:
                self.parts.on(fa, "shade", {"L": PT.q(x1 - x0 - 60), "d": 450, "t": 60},
                              (x0 + x1) // 2, hi + 200)
        self.used["parts"].setdefault(g, set()).add("ribbon")

    # -- AG2: the bay lines --------------------------------------------------------------

    def _lines(self, fa: Facade, ms: dict, g: str, sysname: str, cuts, rows, reveal: int,
               mounts) -> None:
        """The system's parts on a facade's bay lines: mullion caps, fins, exoskeleton and
        diagrid members, timber frames."""
        feat = SY.SYSTEMS[sysname].get("feature")
        if feat not in ("caps", "fins", "exo", "diagrid", "timber") or not cuts or not rows:
            return
        genes, cont = self.gm["genes"], self.gm["cont"]
        P = self.parts
        used = self.used["parts"].setdefault(g, set())
        lines = [cuts[0][0]] + [b1 for _, b1 in cuts]
        zb = max(ms["z0"], rows[0][0] - 150)
        zt = min(ms["z1"], rows[-1][1] + 150)

        def free(s, half, za, zz):
            return not any(s - half < m1 and s + half > m0 and za < z1 and zz > z0
                           for m0, m1, z0, z1 in mounts)
        if feat == "caps":
            h = PT.q(zt - zb)
            if h >= 1000:
                for s in lines:
                    if free(s, 60, zb, zb + h):
                        P.on(fa, "cap", {"dir": "v", "w": 70, "p": 90, "h": h}, s, zb)
                used.add("caps")
        elif feat == "fins":
            z0f = max(zb, STRIP_MIN_Z)
            h = PT.q(zt - z0f)
            if h >= 2000:
                d = PT.q(cont[f"{g}.fin_m"] * 1000)
                ang = int(genes.get(f"{g}.fin_deg", 0))
                for s in lines:
                    if free(s, d, z0f, z0f + h):
                        P.on(fa, "fin", {"t": 100, "d": d, "h": h}, s, z0f, extra_deg=ang)
                used.add("fins")
        elif feat in ("exo", "diagrid"):
            if self._members(fa, ms, g, feat, lines, reveal, mounts):
                used.add(feat)
        elif feat == "timber":
            if self._timber(fa, ms, g, cuts, rows):
                used.add("timber")

    def _members(self, fa: Facade, ms: dict, g: str, feat: str, lines, reveal: int,
                 mounts) -> bool:
        """An exoskeleton (columns on every other bay line, beams every few floors, braces
        by the brace gene) or a diagrid (diagonals over modules of two bays and a few
        floors, edge columns, ring beams), in front of a deep-set curtain wall."""
        genes, cont = self.gm["genes"], self.gm["cont"]
        P = self.parts
        L = fa.L
        w = PT.q(cont[f"{g}.member_m"] * 1000)
        y0, y1 = -120, max(reveal - 40, 60)
        e = w * 6 // 10 + 100              # a sheared diagonal's half width at its node
        lo_s, hi_s = max(lines[0], e), min(lines[-1], L - e)
        if hi_s - lo_s < 3000 or any(m0 < hi_s and m1 > lo_s for m0, m1, _, _ in mounts):
            return False
        z0, z1, n = ms["z0"], ms["z1"], max(ms["floors"], 1)
        nf = int(genes.get(f"{g}.node_f", 3))
        lev = [z0 + (z1 - z0) * f // n for f in range(0, n, nf)]
        if z1 - lev[-1] < (z1 - z0) // n and len(lev) > 1:
            lev.pop()
        lev.append(z1)

        def mem(dx, dz, ww, s, z):
            P.on(fa, "member", {"dx": dx, "dz": dz, "w": ww, "y0": y0, "y1": y1}, s, z)
        if feat == "exo":
            cols = sorted({min(max(x, lo_s), hi_s) for x in lines[::2]} | {lo_s, hi_s})
            cols = [x for k, x in enumerate(cols) if k == 0 or x - cols[k - 1] >= 1500]
            brace = genes.get(f"{g}.brace", "none")
            for x in cols:
                mem(0, PT.q(z1 - z0), w, x, z0)
            for j, z in enumerate(lev[1:], 1):
                for k in range(len(cols) - 1):
                    sa, sb = cols[k], cols[k + 1]
                    mem(PT.q(sb - sa), 0, PT.q(w * 6 // 10), sa, z)
                    if brace == "x" or (brace == "alternate" and (k + j) % 2 == 0):
                        dz = PT.q(z - lev[j - 1])
                        mem(PT.q(sb - sa), dz, PT.q(w // 2), sa, lev[j - 1])
                        mem(-PT.q(sb - sa), dz, PT.q(w // 2), sb, lev[j - 1])
            return True
        bay = int(round(cont[f"{g}.bay_m"] * 1000))
        m = max(1, int(round((hi_s - lo_s) / max(2 * bay, 2000))))
        xs = [lo_s + (hi_s - lo_s) * k // m for k in range(m + 1)]
        for x in (lo_s, hi_s):
            mem(0, PT.q(z1 - z0), w, x, z0)
        for j in range(len(lev) - 1):
            dz = PT.q(lev[j + 1] - lev[j])
            for k in range(m):
                dx = PT.q(xs[k + 1] - xs[k])
                mem(dx, dz, PT.q(w * 7 // 10), xs[k], lev[j])
                mem(-dx, dz, PT.q(w * 7 // 10), xs[k + 1], lev[j])
            if j > 0:
                mem(PT.q(hi_s - lo_s), 0, PT.q(w // 2), lo_s, lev[j])
        return True

    def _timber(self, fa: Facade, ms: dict, g: str, cuts, rows) -> bool:
        """A timber frame over the upper floors: posts on the bay lines, beams at the floor
        lines and over the openings, crosses under the sills (`pattern`)."""
        pat = self.gm["genes"].get(f"{g}.pattern", "posts")
        P = self.parts
        z0, z1, n = ms["z0"], ms["z1"], max(ms["floors"], 1)
        lines = [cuts[0][0]] + [b1 for _, b1 in cuts]
        made = False

        def mem(dx, dz, ww, s, z):
            P.on(fa, "member", {"dx": dx, "dz": dz, "w": ww, "y0": -40, "y1": 0,
                                "slot": "timber"}, s, z)
        for lo, hi, kind, f, full, zf in rows:
            if f + ms.get("f0", 0) == 0 or kind != "win":
                continue
            zn = z0 + (z1 - z0) * (f + 1) // n
            for s in lines:
                mem(0, PT.q(zn - zf), 160, s, zf)
            for jb, (b0, b1) in enumerate(cuts):
                mem(PT.q(b1 - b0), 0, 180, b0, zf + 90)
                mem(PT.q(b1 - b0), 0, 160, b0, hi + 90)
                if lo - zf >= 700 and (pat == "cross" or
                                       (pat == "braced" and jb in (0, len(cuts) - 1))):
                    dz = PT.q(lo - 90 - zf - 180)
                    mem(PT.q(b1 - b0), dz, 120, b0, zf + 180)
                    mem(-PT.q(b1 - b0), dz, 120, b1, zf + 180)
            made = True
        return made

    # -- AG2: canopies, eaves, crowns, arcade columns ------------------------------------

    def _canopy(self, fa: Facade, ms: dict, mounts) -> None:
        """A podium canopy over a ground floor's front, street or plaza edge (towers of six
        floors or more), 3 m up at least, as deep as the room allows, where nothing hangs
        near its height."""
        genes, cont = self.gm["genes"], self.gm["cont"]
        if genes.get("canopy") != "podium" or self.br["building"]["floors"] < 6 or \
                fa.j is None:
            return
        n = max(ms["floors"], 1)
        zc = ms["z0"] + (ms["z1"] - ms["z0"]) // n if n >= 2 else ms["z1"]
        if not 3300 <= zc - ms["z0"] <= 7000:
            return
        L = fa.L
        s0, s1 = fa.c0 + 300, L - fa.c1 - 300
        if s1 - s0 < 5000:
            return
        d = PT.q(min(cont["canopy_m"] * 1000, fa.room((s0 + s1) // 2, 1500, 1500, 2000)))
        if d < 800:
            return
        so = fa.soff
        for m0, m1, za, zb, kind in self.marks.get(fa.j, []):
            if m0 - so < s1 and m1 - so > s0 and za < zc + 800 and zb > zc - 1700:
                return
        if any(m0 < s1 and m1 > s0 and z0 < zc + 800 and z1 > zc - 1700
               for m0, m1, z0, z1 in mounts):
            return
        self.parts.on(fa, "canopy", {"L": PT.q(s1 - s0), "d": d, "t": 300}, (s0 + s1) // 2,
                      zc - 150)
        fa.podium = True
        if "canopy" not in self.used["articulation"]:
            self.used["articulation"].append("canopy")

    def _eaves(self, ms: dict, g: str, rows) -> None:
        """Tiled eaves: a pent roof round the mass at every floor line 3 m up or more,
        between the rows' openings."""
        n = ms["floors"]
        made = False
        for f in range(1, n):
            zf = ms["z0"] + (ms["z1"] - ms["z0"]) * f // n
            zt = zf - 60
            zl, zbot = zt - 300, zt - 380
            if zbot < STRIP_MIN_Z or any(lo < zt + 20 and hi > zbot - 20
                                         for lo, hi, *_ in rows):
                continue
            ok = self._edge_ok(ms, zbot, zt)
            for r, ring0 in enumerate(ms["rings"]):
                n0 = len(ring0)
                keep = [i for i in range(n0) if ring0[i] != ring0[(i + 1) % n0]]
                ring = [ring0[i] for i in keep]
                m = [ok[r][i] for i in keep]
                if len(ring) < 3 or not all(m):
                    continue
                res = RG.strip(ring, 0, len(ring), 550, 0, 0)
                if res is None:
                    continue
                self.buf.layer = 1 if zt <= ms.get("band", -1) else 0
                if self._sloped(ring, res[0], res[1], zt, zl, zbot, "tile"):
                    made = True
                self.buf.layer = 0
        if made:
            self.used["parts"].setdefault(g, set()).add("eaves")
            self.stats["eaves"] = self.stats.get("eaves", 0) + 1

    def _sloped(self, ring, outer, hole, zt: int, zl: int, zb: int, slot: str) -> bool:
        """A closed sloped strip: flat underneath at zb, its top falling from zt on the
        ring (the wall) to zl on the outer edge."""
        holes = [hole] if hole is not None else []
        try:
            tris = triangulate(outer, holes, keep_straight=True)
        except TriangulationError:
            return False
        if not tris:
            return False
        pts = list(outer) + [p for h in holes for p in h]
        top = [zt if RG.inside(p, ring) == 0 else zl for p in pts]
        buf = self.buf
        buf.new_part()
        PT.face(buf, slot, [(p[0], p[1], zb) for p in pts], (0.0, 0.0, -1.0),
                [(t[0], t[2], t[1]) for t in tris])
        for t in tris:
            a, b, c = ((pts[k][0], pts[k][1], top[k]) for k in t)
            nn = PT._cross(PT._sub(b, a), PT._sub(c, a))
            ln = math.sqrt(nn[0] * nn[0] + nn[1] * nn[1] + nn[2] * nn[2])
            if ln == 0:
                continue
            PT.face(buf, slot, [a, b, c], (nn[0] / ln, nn[1] / ln, nn[2] / ln))
        base = 0
        for rg in [outer] + holes:
            k = len(rg)
            for i in range(k):
                p, q = rg[i], rg[(i + 1) % k]
                tp, tq = top[base + i], top[base + (i + 1) % k]
                dx, dy = q[0] - p[0], q[1] - p[1]
                L = math.sqrt(dx * dx + dy * dy)
                if L == 0:
                    continue
                PT.face(buf, slot, [(p[0], p[1], zb), (q[0], q[1], zb), (q[0], q[1], tq),
                                    (p[0], p[1], tp)], (dy / L, -dx / L, 0.0))
            base += k
        return True

    def _screen(self, ms: dict) -> None:
        """A halo crown: the top floor a screen of fins inside the mass round an open roof,
        tied by a ring beam, a penthouse in the middle."""
        ring = RG.clean(ms["rings"][0])
        n = len(ring)
        h = PT.q(ms["z1"] - ms["z0"] + 900)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            fa = Facade(a, b, 0.0)
            if fa.L < 2400:
                continue
            m = max(1, (fa.L - 1200) // 1100)
            for k in range(m + 1):
                self.parts.on(fa, "fin", {"t": 100, "d": 700, "h": h, "inward": True},
                              600 + (fa.L - 1200) * k // m, ms["z0"])
        res = RG.strip(ring, 0, n, 0, -700, 0)
        if res is not None:
            self.buf.new_part()
            self._extrude(res[0], res[1], ms["z0"] + h - 300, ms["z0"] + h, "fin")
        inner = RG.offset_ring(ring, [-4000] * n)
        if inner is not None and RG.is_simple(inner) and len(inner) >= 3 and \
                _thickness(inner) >= 3000:
            self.buf.new_part()
            self._extrude(inner, None, ms["z0"], ms["z1"] - 600, "structure")
        self.mass_info.append({"mass": ms["k"], "group": "top", "system": None, "rows": 0,
                               "openings": 0, "crown": "halo"})

    def _mast(self) -> None:
        """A mast or a spire on the highest roof (the crown gene), its middle clear of roof
        items."""
        crown = self.gm["genes"].get("crown")
        if crown not in ("mast", "spire") or not self.tall or self.br["building"]["landmark"]:
            return
        cand = [ms for ms in self.masses if ms["shape"] == "prism" and not ms.get("screen")
                and ms["z1"] - ms["z0"] >= 50]
        if not cand:
            return
        top = max(cand, key=lambda ms: (ms["z1"], -ms["k"]))
        ring = RG.clean(top["rings"][0])
        c = _centroid(ring)
        if len(ring) < 3 or RG.in_poly(c, top["rings"]) != 1 or _thickness(ring) < 8000:
            return
        for it in self.br["roof_items"]:
            x, y = it["position"][0] * 1000, it["position"][1] * 1000
            if (x - c[0]) ** 2 + (y - c[1]) ** 2 < 3000 ** 2:
                return
        H = int(round(float(self.br["building"]["height_m"]) * 1000))
        if crown == "mast":
            p = {"style": "mast", "h": PT.q(min(max(H // 10, 8000), 30000))}
        else:
            p = {"style": "spire", "h": PT.q(min(max(H * 18 // 100, 12000), 45000))}
        self.parts.add("mast", p, c[0], c[1], top["z1"], 1.0, 0.0)
        self.used["crown"] = True

    def _columns(self) -> None:
        """The columns of every arcade, on the facade line of the floors above."""
        if not self.arcades:
            return
        bay = int(round(self.gm["cont"]["body.bay_m"] * 1000))
        spacing = max(4000, 2 * bay)
        for ar in self.arcades:
            ring = ar["ring"]
            n = len(ring)
            for i in range(n):
                if not ar["ok"][i]:
                    continue
                a, b = ring[i], ring[(i + 1) % n]
                ux, uy, L = AR._unit(a, b)
                e = 450
                m = max(1, -(-(int(L) - 2 * e) // spacing))
                for k in range(m + 1):
                    s = e + (int(L) - 2 * e) * k // m
                    self.parts.add("column", {"w": 500, "h": PT.q(ar["z1"])},
                                   int(round(a[0] + ux * s)), int(round(a[1] + uy * s)),
                                   ar["z0"], ux, uy)

    def _finish_parts(self) -> None:
        """Parts placed fewer than `parts.INSTANCE_MIN` times merged into the shell; the
        others are the building's instances."""
        inst = []
        merged = 0
        for k in sorted(self.parts.defs):
            fam, p = self.parts.defs[k]
            at = self.parts.at[k]
            b, arrs = PT.mesh(fam, p)
            if not arrs:
                continue
            if self.bridges.segs and PT.REACH.get(fam) in ("strip", "deep"):
                # AG4: no part that stands out of a wall enters a skybridge's corridor
                lo, hi = PT.bounds(arrs)
                keep = []
                for a in at:
                    xs, ys = [], []
                    for cx in (lo[0], hi[0]):
                        for cy in (lo[1], hi[1]):
                            xs.append(a[0] + cx * a[3] - cy * a[4])
                            ys.append(a[1] + cx * a[4] + cy * a[3])
                    if self.bridges.hits(min(xs), min(ys), max(xs), max(ys), a[2] + lo[2],
                                         a[2] + hi[2]):
                        self.stats["parts_off_bridges"] = \
                            self.stats.get("parts_off_bridges", 0) + 1
                        continue
                    keep.append(a)
                at = keep
                if not at:
                    continue
            if len(at) < PT.INSTANCE_MIN and fam not in PT.INSTANCE_ALWAYS and \
                    all(PT.survives(arrs, a) for a in at):
                zlo = PT.bounds(arrs)[0][2]
                for a in at:
                    # (AG3) a part reaching down into the street band is the front's
                    self.buf.layer = 1 if self.band_z is not None and \
                        a[2] + zlo < self.band_z - 1 else 0
                    PT.merge_into(self.buf, b, arrs, a)
                self.buf.layer = 0
                merged += len(at)
                continue
            inst.append({"family": fam, "params": p, "type": PT.type_of(fam, p),
                         "node": PT.node_name(fam, p), "at": at,
                         "triangles": int(sum(len(a["tri"]) for a in arrs.values()))})
        self.inst = inst
        self.stats["parts_merged"] = merged
        self.stats["parts_instanced"] = sum(len(x["at"]) for x in inst)
        self.stats["part_kinds"] = len(inst)

    def _caps(self, ms: dict, wall: str, band: int | None = None) -> None:
        """The roof and the cap under the mass; on a mass with a street front, under the
        shell's part from the band's top (none where the band takes the whole mass)."""
        if band is not None and band >= ms["z1"]:
            return
        rings = [RG.clean(r) for r in ms["rings"]]
        outer, holes = rings[0], [h for h in rings[1:] if len(h) >= 3]
        try:
            tris = triangulate(outer, holes, keep_straight=True)
        except TriangulationError:
            self.stats.setdefault("cap_failures", 0)
            self.stats["cap_failures"] += 1
            return
        pts = list(outer) + [p for h in holes for p in h]
        z0, z1 = (ms["z0"] if band is None else band), ms["z1"]
        buf = self.buf
        top = buf.plane((0.0, 0.0, 1.0), (0, 0, z1), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        bot = buf.plane((0.0, 0.0, -1.0), (0, 0, z0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0))
        roof = "roof" if wall != "structure" else "structure"
        if ms.get("portal_floor"):
            roof = "portal_floor"           # (AG4: under a sky tube portal)
        under = "portal_lining" if ms.get("portal_top") else "structure"
        buf.add(roof, top, [(p[0], p[1], z1) for p in pts], [i for t in tris for i in t])
        buf.add(under, bot, [(p[0], p[1], z0) for p in pts],
                [i for t in tris for i in (t[0], t[2], t[1])])

    # -- wheels -------------------------------------------------------------------------

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


def _fire(regions: list[dict]) -> list[dict]:
    """A facade's regions with every `upper` stretch that stands on a party wall (the wall
    over a lower neighbor built against it) made a fire wall: blank, as lot-line walls are
    (AG3)."""
    party = [r for r in regions if r["class"] == "party"]
    if not party:
        return regions
    out = []
    for r in regions:
        if r["class"] == "upper" and any(
                q["s"][0] < r["s"][1] - 0.01 and q["s"][1] > r["s"][0] + 0.01 and
                abs(q["z"][1] - r["z"][0]) <= 0.05 for q in party):
            r = dict(r, **{"class": "firewall"})
        out.append(r)
    return out


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
