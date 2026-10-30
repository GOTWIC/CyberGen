"""Generators per M3 type (scope 5.1.5, 14.6: AG5) where the general grammar (AG1 to AG4)
falls short. Each type is the general shell with its own steps, at three points of the
shell builder (`shell.ShellBuilder.build`):

- `pre` (after the massing articulation, before portals and roof forms): masses reshaped or
  marked (a temple hall's colonnade set back behind its columns, a temple platform's stair
  cut, a hangar's door facade kept blank, roof forms a type asks for);
- `mass` (in the mass loop): a mass built by the type in place of the grammar (an open
  shed's roof on columns, a control tower's cab, a parking ramp's slope);
- `post` (after the masses, before the facade details): what the type adds (eaves,
  columns, finials, stairs, hangar doors, girders, stacks, monitors, canopies, tarps,
  lean-to roofs, fire escapes and ladders, risers, neon, chimneys, pergolas, terraces).

| type | generator |
|---|---|
| shanty_stack | lean-to sheet roofs over the top storeys, tarps on the flat roofs, rough fire escapes and ladders up the stacks, stilt balconies, water barrels |
| megabuilding | towers' antenna farms, service risers up their back walls, a neon band along the podium |
| warehouse | canopies over the loading doors, a ridge monitor on a flat roof |
| shed | open sides: a roof on steel columns, walls only where a neighbor stands; else a ridge monitor |
| yard | a canopy over the loading door, a ridge monitor |
| hangar | a sliding door across its apron facade (its leaves, ribs, header and track) |
| lab | fume stacks in a row on the roof |
| villa | a chimney, a pergola on a lower roof |
| terraced | planters along every terrace, balustrades |
| temple_hall | a colonnade of lacquered columns round the hall, eaves over every tier, a pagoda roof, stairs up the platform, a temple door |
| pagoda | eaves over every tier, a pagoda roof, a finial |
| gate_house | a canopy roof all round, a light on the roof |
| terminal | a vaulted roof, canopies over its doors |
| control_tower | the cab: a glazed band leaning out, mullions, a roof with a radome and antennas; a slot of lights up the shaft |
| station | a vaulted train-shed roof with a glazed ridge, canopies over its doors |
| parking_structure | its ramps as sloped decks with curbs |
| straddle_building | transfer girders along its span's underside, lamps under them |
| ferris_wheel | the hero wheel (`heroes.wheel`) |

The rest of M3's types (tower, podium_tower, slab, courtyard_block, perimeter,
shopfront_row, office, kiosk, pavilion, station_tower, skyport and the others) are the
general grammar's (`GENERATORS`: "general"); landmarks are the heroes' (`heroes.py`).
Everything a type adds is placed only where the envelope allows it (`envelope.fits`) and
counted (`stats["type_features"]`); the record's `generator` names it.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from ..triangulate import area2
from . import articulate as AR
from . import decks as DK
from . import genome as GN
from . import parts as PT
from . import rings as RG
from . import roofs as RF
from . import systems as SY
from . import typeparts as TP  # noqa: F401  (registers the families)

GENERAL = ("building.tower", "building.podium_tower", "building.slab",
           "building.courtyard_block", "building.perimeter", "building.shopfront_row",
           "building.office", "building.kiosk", "building.pavilion",
           "building.station_tower", "building.skyport")
GENERATORS = {**{t: "general" for t in GENERAL},
              "building.shanty_stack": "shanty", "building.megabuilding": "megablock",
              "building.warehouse": "warehouse", "building.shed": "shed",
              "building.yard": "yard", "building.hangar": "hangar", "building.lab": "lab",
              "building.villa": "villa", "building.terraced": "terraced",
              "building.temple_hall": "temple", "building.pagoda": "pagoda",
              "building.gate_house": "gatehouse", "building.terminal": "terminal",
              "building.control_tower": "control_tower", "building.station": "station",
              "building.parking_structure": "parking",
              "building.straddle_building": "straddle", "building.ferris_wheel": "wheel"}


def generator_of(btype: str) -> str:
    """The generator of a type: its own, a hero's for a landmark, else the general one."""
    if btype.startswith("building.landmark."):
        return "hero." + btype.rsplit(".", 1)[1]
    return GENERATORS.get(btype, "general")


def _u(key: str, purpose: str) -> float:
    return GN.u(key, purpose, "ag5.type")


def _count(sb, what: str, n: int = 1) -> None:
    if n <= 0:
        return
    sb.stats["type_features"] = sb.stats.get("type_features", 0) + n
    st = sb.stats.setdefault("type_feature_kinds", {})
    st[what] = st.get(what, 0) + n


def put(sb, family: str, p: dict, x: int, y: int, z: int, ux: float, uy: float,
        what: str | None = None) -> bool:
    """Place a part at (x, y, z) turned to (ux, uy) if it stays inside the envelope."""
    from . import envelope as EN
    if not EN.fits(sb.br, family, p, int(x), int(y), int(z), ux, uy) or \
            _in_corridor(sb, family, p, int(x), int(y), int(z), ux, uy):
        sb.stats["type_refused"] = sb.stats.get("type_refused", 0) + 1
        return False
    sb.parts.add(family, p, int(x), int(y), int(z), ux, uy)
    _count(sb, what or family)
    return True


def _in_corridor(sb, family: str, p: dict, x: int, y: int, z: int, ux: float,
                 uy: float) -> bool:
    """Whether a part placed so meets a skybridge's, guideway's or sky tube's corridor (its
    box, AG4's `roofs.Clear`)."""
    if not sb.clear.segs:
        return False
    _, arrs = PT.mesh(family, p)
    if not arrs:
        return False
    lo, hi = PT.bounds(arrs)
    xs, ys = [], []
    for cx in (lo[0], hi[0]):
        for cy in (lo[1], hi[1]):
            xs.append(x + cx * ux - cy * uy)
            ys.append(y + cx * uy + cy * ux)
    return sb.clear.hits(min(xs), min(ys), max(xs), max(ys), z + lo[2], z + hi[2])


def put_on(sb, fa, family: str, p: dict, s: int, z: int, what: str | None = None,
           y: int = 0) -> bool:
    x, y0, _ = fa.P(s, z)
    x -= int(round(fa.nx * y))
    y0 -= int(round(fa.ny * y))
    return put(sb, family, p, x, y0, z, fa.ux, fa.uy, what)


def facades(sb, ms) -> list:
    return [fa for fa, m in sb.all_facades if m is ms]


def frame_of(ring):
    """(center, u, v, W, D) of a ring's oriented box: x along its longest edge's direction,
    the extents of the ring in that frame."""
    ring = RG.clean(ring)
    n = len(ring)
    k = max(range(n), key=lambda i: ((ring[(i + 1) % n][0] - ring[i][0]) ** 2 +
                                     (ring[(i + 1) % n][1] - ring[i][1]) ** 2, -i))
    ux, uy, _ = AR._unit(ring[k], ring[(k + 1) % n])
    vx, vy = -uy, ux
    us = [p[0] * ux + p[1] * uy for p in ring]
    vs = [p[0] * vx + p[1] * vy for p in ring]
    a0, a1, b0, b1 = min(us), max(us), min(vs), max(vs)
    cu, cv = (a0 + a1) / 2.0, (b0 + b1) / 2.0
    c = (int(round(cu * ux + cv * vx)), int(round(cu * uy + cv * vy)))
    return c, (ux, uy), (vx, vy), int(a1 - a0), int(b1 - b0)


def _rectish(ring) -> bool:
    """A ring close to its oriented box (90% of its area or more)."""
    _, _, _, W, D = frame_of(ring)
    a = area2(RG.clean(ring)) / 2.0
    return W > 0 and D > 0 and a >= 0.9 * W * D


def _is_top(sb, ms) -> bool:
    return AR._is_top(sb, ms)


def _free_roof(sb, ms, w: int, d: int, ux: float, uy: float, inset: int = 600,
               step: int = 1500, taken=None):
    """Free spots for a w x d box on a mass's roof (off roof items, masses over it, green
    roofs and what was placed before, `taken`)."""
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3:
        return []
    holes = [RG.clean(h) for h in ms["rings"][1:]]
    tk = RF._taken(sb, ms) + list(taken or [])
    out = []
    for x, y in RF._spots(ring, holes, ux, uy, w, d, inset, step):
        bb = RF._bbox(x, y, ux, uy, w + 400, d + 400)
        if RF._free(bb, tk):
            out.append((x, y))
    return out


def _wall_free(sb, fa, s0: int, s1: int, z0: int, z1: int) -> bool:
    from .details import _free
    return fa.j is not None and _free(sb, fa, s0, s1, z0, z1)


def _main_class(fa) -> str:
    from .details import _main_class as mc
    return mc(fa)


# ---------------------------------------------------------------------------
# The three steps
# ---------------------------------------------------------------------------

def pre(sb) -> None:
    g = generator_of(sb.br["building"]["type"])
    sb.generator = g
    fn = PRE.get(g)
    if fn is not None:
        fn(sb)


def mass(sb, ms) -> bool:
    fn = MASS.get(getattr(sb, "generator", "general"))
    return bool(fn is not None and fn(sb, ms))


def post(sb) -> None:
    fo = getattr(sb, "form_override", None)
    if fo and any((ms.get("roof") or {}).get("kind") == fo for ms in sb.roof_forms):
        _count(sb, f"roof_{fo}")          # (a type's own roof form, as AG4 built it)
    dormers(sb)
    fn = POST.get(getattr(sb, "generator", "general"))
    if fn is not None:
        fn(sb)


# ---------------------------------------------------------------------------
# Dormers (AG4's open item: the pitched roofs had none)
# ---------------------------------------------------------------------------

DORMER_ERAS = {"heritage": 0.75, "suburban_modern": 0.5, "neon_retro": 0.3}
DORMER_H = 1800          # a dormer's face, base to eaves
DORMER_BAY = 4200        # one per this along a slope
DORMER_SET = 450         # its face set back from the wall line below
DORMER_END = 900         # kept this from a gable end or a hip's slope


def dormers(sb) -> None:
    """Dormers along the long slopes of a gable or hip roof, on the eras that pitch their
    roofs, one per DORMER_BAY, each a face DORMER_SET in from the wall under it and cheeks
    back into the roof until its own roof meets the slope."""
    share = DORMER_ERAS.get(sb.gm.get("era"), 0.0)
    if not share or _u(sb.bid, "dormers") >= share or getattr(sb, "hero", None):
        return
    for ms in sb.roof_forms:
        rf = ms.get("roof") or {}
        if rf.get("kind") == "mansard" and rf.get("tan") and rf.get("B"):
            _mansard_dormers(sb, ms, rf)
            continue
        if rf.get("kind") not in ("gable", "hip") or "ridge" not in rf or not rf.get("tan"):
            continue
        c, u, v = rf["frame"]
        x0, x1, y0, y1 = rf["box"]
        rx0, rx1, ym, zr = rf["ridge"]
        tanp, zf = rf["tan"], rf["zf"]
        _, _, _, W, D, _ = RF._rect_frame(rf["ring"], rf["rect"], rf["eave"])
        w = 1400 if _u(f"{sb.bid}|{ms['k']}", "dw") < 0.5 else 1800
        st = "gable" if _u(f"{sb.bid}|{ms['k']}", "dst") < 0.65 else "shed"
        rise = w * 45 // 100 if st == "gable" else 400
        slot = RF.slope_slot(sb)
        for side in (-1, 1):
            yf = side * (D / 2.0 - DORMER_SET)        # the face, in the roof's frame
            run = abs(yf - (y0 if side < 0 else y1))  # from the eave line in
            zs = zf + int(run * tanp)
            if zs + DORMER_H + rise > zr - 300:
                continue
            d = int((DORMER_H + rise) / tanp) + 300
            if run + d > abs(ym - (y0 if side < 0 else y1)) - 600:
                continue
            sh = run + d if rf["kind"] == "hip" else 0     # a hip's ends close in at 45 degrees
            xa = x0 + sh + DORMER_END + w / 2.0
            xb = x1 - sh - DORMER_END - w / 2.0
            if xb < xa:
                continue
            n = int((xb - xa) // DORMER_BAY) + 1
            ux, uy = (u[0], u[1]) if side < 0 else (-u[0], -u[1])
            for i in range(n):
                xc = (xa + xb) / 2.0 if n == 1 else xa + (xb - xa) * i / (n - 1)
                px = c[0] + u[0] * xc + v[0] * yf
                py = c[1] + u[1] * xc + v[1] * yf
                put(sb, "dormer", {"w": w, "h": DORMER_H, "d": PT.q(d), "style": st,
                                   "slot": slot},
                    int(round(px)), int(round(py)), zs - 150, ux, uy, "dormer")


MANSARD_SET = 100        # a mansard dormer's face this in from the wall line
MANSARD_W = 1200


def _mansard_dormers(sb, ms, rf) -> None:
    """Small gabled dormers on a mansard's steep slopes, along every edge with an eave (a
    wall open to the street, not a party wall), as tall as the attic leaves over the slope
    where it crosses the wall line."""
    ring, e, tanp = rf["ring"], rf["eave"], rf["tan"]
    zf, zt = rf["zf"], rf["zt"]
    n = len(ring)
    w = MANSARD_W
    rise = w * 35 // 100
    slot = RF.slope_slot(sb)
    for i in range(n):
        if e[i] <= 0:
            continue
        a, b = ring[i], ring[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        zs = zf + int((e[i] + MANSARD_SET) * tanp)
        hd = min(DORMER_H, zt - zs - rise - 150)
        if hd < 1000:
            continue
        d = min(int((hd + rise) / tanp) + 300, 2500)
        end = e[i] + MANSARD_SET + d + 300 + w / 2.0
        if L - 2 * end < 0:
            continue
        k = int((L - 2 * end) // DORMER_BAY) + 1
        for j in range(k):
            s_ = L / 2.0 if k == 1 else end + (L - 2 * end) * j / (k - 1)
            px = a[0] + ux * s_ - uy * MANSARD_SET
            py = a[1] + uy * s_ + ux * MANSARD_SET
            put(sb, "dormer", {"w": w, "h": PT.q(hd), "d": PT.q(d), "style": "gable",
                               "slot": slot},
                int(round(px)), int(round(py)), zs - 150, ux, uy, "dormer")


# ---------------------------------------------------------------------------
# Shanty stacks
# ---------------------------------------------------------------------------

def shanty_post(sb) -> None:
    key = sb.bid
    taken: list[tuple] = []
    for ms in sb.masses:
        if ms["shape"] != "prism" or ms["z1"] - ms["z0"] < 2000 or ms.get("roof"):
            continue
        ring = RG.clean(ms["rings"][0])
        if len(ring) < 3:
            continue
        top = _is_top(sb, ms)
        items = RF._items_on(sb.br, ms)
        c, u, v, W, D = frame_of(ring)
        # a lean-to sheet over a top storey with nothing on its roof
        if top and not items and ms["z0"] >= 2500 and W >= 2500 and D >= 2500 and \
                _rectish(ring) and _u(f"{key}|{ms['k']}", "leanto") < 0.75:
            rise = PT.q(min(800, max(300, D * 8 // 100)))
            p = {"W": PT.q(W), "D": PT.q(D), "rise": rise, "over": 300}
            flip = _u(f"{key}|{ms['k']}", "leanto.side") < 0.5
            ux, uy = (u if not flip else (-u[0], -u[1]))
            if put(sb, "shack_roof", p, c[0], c[1], ms["z1"], ux, uy, "lean_to"):
                continue
        # a tarp or two on a flat roof
        if not ms.get("roof") and W >= 3000 and D >= 3000:
            for k in range(2 if W * D > 60e6 else 1):
                if _u(f"{key}|{ms['k']}", f"tarp{k}") > 0.55:
                    continue
                tw, td = PT.q(2400 + 1200 * _u(key, f"tw{k}")), PT.q(2000 + 800 *
                                                                      _u(key, f"td{k}"))
                spots = _free_roof(sb, ms, tw, td, u[0], u[1], 400, 1200, taken)
                if not spots:
                    continue
                x, y = spots[int(_u(key, f"tarp.at{k}") * len(spots)) % len(spots)]
                p = {"w": tw, "d": td, "h": 1100, "tilt": 300}
                if put(sb, "tarp", p, x, y, ms["z1"], u[0], u[1], "tarp"):
                    taken.append(RF._bbox(x, y, u[0], u[1], tw + 600, td + 600))
        # a water barrel on a flat roof
        if not ms.get("roof") and _u(f"{key}|{ms['k']}", "barrel") < 0.35:
            spots = _free_roof(sb, ms, 900, 900, u[0], u[1], 300, 800, taken)
            if spots:
                x, y = spots[int(_u(key, f"barrel.at{ms['k']}") * len(spots)) % len(spots)]
                ceil = DK.ceiling_mm(sb.br)
                if ceil is not None and ms["z1"] + 1100 > ceil - DK.CEIL_GAP_M * 1000:
                    continue        # (AG10: no room under an M14 deck's soffit)
                RF._place(sb, "water_tank", {"r": 400, "h": 1000, "style": "panel"}, x, y,
                          ms["z1"], u[0], u[1])
                taken.append(RF._bbox(x, y, u[0], u[1], 1400, 1400))
                _count(sb, "barrel")
    _shanty_escapes(sb)


def _shanty_escapes(sb) -> None:
    """Rough fire escapes up the stacks (AG4 left them to the shanty's clutter), ladders
    from a stack's roof to the next, stilt balconies."""
    key = sb.bid
    made = 0
    for fa, ms in sb.all_facades:
        if made >= 2 or fa.j is None or ms["floors"] < 2 or fa.L < 3600:
            continue
        cls = _main_class(fa)
        if cls not in ("alley", "open", "street", "front", "upper"):
            continue
        room = 1300 if cls == "alley" else fa.room(fa.L // 2, 4000, 1300, 1500)
        if room < 1000:
            continue
        n = ms["floors"]
        zs = [ms["z0"] + (ms["z1"] - ms["z0"]) * f // n for f in range(0 if ms["z0"] else 1,
                                                                        n)]
        zs = [z for z in zs if z >= 3000]
        if len(zs) < 2 and not (zs and ms["z0"] >= 2500):
            continue
        w = PT.q(min(3600, fa.L * 6 // 10))
        s = fa.c0 + (fa.L - fa.c0 - fa.c1) // 2
        if s - w // 2 < fa.c0 or s + w // 2 > fa.L - fa.c1:
            continue
        if not _wall_free(sb, fa, s - w // 2 - 150, s + w // 2 + 150, zs[0] - 200, zs[-1] +
                          1100):
            continue
        z0 = zs[0]
        p = {"w": w, "d": PT.q(min(room, 1100)), "zs": [z - z0 for z in zs] or [0],
             "ladder": PT.q(max(z0 - 2600, 0)), "slot": "escape_rust"}
        if put_on(sb, fa, "escape", p, s, z0, "fire_escape"):
            made += 1
            sb.stats["fire_escapes"] = sb.stats.get("fire_escapes", 0) + 1
    # ladders from a lower roof up a stack's wall
    for ms in sb.masses:
        if ms["z0"] < 2500 or ms["floors"] < 1:
            continue
        for fa in facades(sb, ms):
            if fa.j is None or fa.L < 1500 or _u(f"{key}|{fa.j}|{fa.a}", "ladder") > 0.25:
                continue
            s = fa.L // 2
            h = PT.q(min(ms["z1"] - ms["z0"] + 900, 6000))
            if _wall_free(sb, fa, s - 400, s + 400, ms["z0"], ms["z0"] + h) and \
                    put_on(sb, fa, "ladder", {"h": h, "w": 500, "slot": "escape_rust"}, s,
                           ms["z0"], "ladder"):
                break
    # stilt balconies on a stack's floors over an alley or open ground
    n = 0
    for fa, ms in sb.all_facades:
        if n >= 3 or fa.j is None or ms["z0"] < 2500 or fa.L < 2600:
            continue
        if _u(f"{key}|{fa.j}|{fa.a}", "stilt") > 0.4:
            continue
        z = ms["z0"]
        room = fa.room(fa.L // 2, z, 1200, 1200)
        if room < 900:
            continue
        w = PT.q(min(2400, fa.L - 800))
        s = fa.L // 2
        if not _wall_free(sb, fa, s - w // 2, s + w // 2, z, z + 1200):
            continue
        p = {"w": w, "d": PT.q(min(room, 1100)), "t": 150, "rh": 1000, "style": "rail"}
        if put_on(sb, fa, "balcony", p, s, z, "stilt_balcony"):
            n += 1


# ---------------------------------------------------------------------------
# Megablocks, warehouses, sheds, yards, hangars, labs
# ---------------------------------------------------------------------------

def megablock_post(sb) -> None:
    key = sb.bid
    neon = f"neon_{GN.pick(key, 'mega.neon', SY.NEONS, None, 'ag5.type')}"
    for ms in sb.masses:
        ring = RG.clean(ms["rings"][0])
        if len(ring) < 3 or ms["shape"] != "prism":
            continue
        role = ms["role"]
        c, u, v, W, D = frame_of(ring)
        if role == "tower" and _is_top(sb, ms) and not ms.get("roof"):
            # an antenna farm on the tower's roof
            spots = _free_roof(sb, ms, 1200, 1200, u[0], u[1], 1200, 2400)
            for k, (x, y) in enumerate(spots[:: max(1, len(spots) // 3)][:3]):
                h = 6000 + 3000 * (k % 2)
                st = ("lattice", "whip", "dish")[k % 3]
                if st == "lattice" and h < 9000:
                    st = "whip"
                RF._place(sb, "antenna", {"h": h, "style": st}, x, y, ms["z1"], u[0], u[1])
                _count(sb, "antenna_farm")
        if role == "tower" and ms["floors"] >= 8:
            # service risers up a back wall
            for fa in facades(sb, ms):
                if fa.j is None or fa.L < 6000 or _main_class(fa) not in (
                        "alley", "courtyard", "blind", "upper", "open"):
                    continue
                h = PT.q(ms["z1"] - ms["z0"] - 600)
                s = fa.c0 + 600
                if not _wall_free(sb, fa, s - 200, s + 700, ms["z0"], ms["z1"]):
                    continue
                for dx in (0, 260, 520):
                    put_on(sb, fa, "pipe", {"h": h}, s + dx, ms["z0"] + 300, "riser")
                break
        if role == "podium":
            # a neon band along its street facades, under its top
            z = ms["z1"] - 900
            if z < 3500:
                continue
            for fa in facades(sb, ms):
                if fa.j is None or fa.L < 8000 or _main_class(fa) not in ("street", "front",
                                                                          "plaza"):
                    continue
                L = PT.q(fa.L - fa.c0 - fa.c1 - 1200)
                s = fa.c0 + 600
                if L >= 4000 and _wall_free(sb, fa, s, s + L, z, z + 400):
                    put_on(sb, fa, "neon_strip", {"L": L, "h": 400, "d": 120, "slot": neon},
                           s, z, "podium_neon")


def _flat_top(sb):
    cand = [ms for ms in sb.masses if ms["shape"] == "prism" and not ms.get("roof") and
            _is_top(sb, ms) and ms["z1"] - ms["z0"] >= 2500]
    return max(cand, key=lambda m: (area2(RG.clean(m["rings"][0])), -m["k"])) if cand else None


def _monitor(sb, ms) -> None:
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3 or RF._items_on(sb.br, ms) and len(RF._items_on(sb.br, ms)) > 6:
        return
    c, u, v, W, D = frame_of(ring)
    if W < 12000 or D < 6000 or not _rectish(ring):
        return
    L = PT.q(W * 6 // 10)
    p = {"L": L, "w": PT.q(min(2400, D // 4)), "h": 1000}
    tk = RF._taken(sb, ms)
    if RF._free(RF._bbox(c[0], c[1], u[0], u[1], L + 600, p["w"] + 600), tk):
        put(sb, "monitor", p, c[0], c[1], ms["z1"], u[0], u[1], "ridge_monitor")


def _door_canopies(sb, kinds=("dock", "rollup", "garage", "main"), depth=1800) -> None:
    for d in sb.doors:
        if d["kind"] not in kinds or d["flush"]:
            continue
        hit = next(((fa, ms) for fa, ms in sb.band_facades if fa.j == d["edge"] and
                    fa.soff - 1 <= d["s"] <= fa.soff + fa.L + 1), None)
        if hit is None:
            continue
        fa, ms = hit
        s = d["s"] - fa.soff
        z = max(d["pos"][2] + d["h"] + 400, 3000)
        if z + 300 > ms["z1"]:
            continue
        L = PT.q(d["w"] + 1600)
        if s - L // 2 < 200 or s + L // 2 > fa.L - 200:
            continue
        room = fa.room(s, z, depth, depth)
        if room < 900 or not _wall_free(sb, fa, s - L // 2, s + L // 2, z - 50, z + 350):
            continue
        put_on(sb, fa, "canopy", {"L": L, "d": PT.q(min(room, depth)), "t": 300}, s, z,
               "door_canopy")


def warehouse_post(sb) -> None:
    _door_canopies(sb, ("dock", "rollup"))
    top = _flat_top(sb)
    if top is not None:
        _monitor(sb, top)


def yard_post(sb) -> None:
    _door_canopies(sb, ("dock", "rollup", "gate"))
    top = _flat_top(sb)
    if top is not None:
        _monitor(sb, top)


def shed_mass(sb, ms) -> bool:
    """An open shed: its roof on steel columns, walls only where a neighbor stands (party,
    blind or hidden edges), its roof form as AG4 built it."""
    if not sb.br["building"]["attrs"].get("open_sides") or ms["shape"] != "prism" or \
            len(ms["rings"]) != 1 or ms["z0"] > 50:
        return False
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3:
        return False
    top = ms["z1"]
    slab = 600
    if top - ms["z0"] < 3500:
        return False
    sb.buf.new_part()
    if not sb._extrude(ring, None, top - slab, top, "roof_metal"):
        return False
    n = len(ring)
    walls = 0
    cols = 0
    # (its columns from the genome: two bays apart, their size from the corner pier)
    bay = int(round(float(sb.gm["cont"]["body.bay_m"]) * 2000))
    r = 100 + 50 * int(float(sb.gm["cont"]["body.corner_m"]) * 4)
    sb.used.setdefault("open", [])
    if "body" not in sb.used["open"]:
        sb.used["open"].append("body")
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        ux, uy, L = AR._unit(a, b)
        j = sb._j(ms, 0, i)
        cls = sb.br["edges"][j]["class"] if j is not None else "open"
        if cls in ("party", "blind", "hidden"):
            # a wall where a neighbor stands against it: a 0.25 m slab inside the edge
            nx, ny = uy, -ux
            q = [a, b, (int(round(b[0] - nx * 250)), int(round(b[1] - ny * 250))),
                 (int(round(a[0] - nx * 250)), int(round(a[1] - ny * 250)))]
            sb.buf.new_part()
            if sb._extrude(q, None, ms["z0"], top - slab, "hangar"):
                walls += 1
            continue
        k = max(1, int(L // bay))
        for m in range(k + 1):
            s = 300 + (L - 600) * m / k
            x = int(round(a[0] + ux * s - uy * (r + 100)))
            y = int(round(a[1] + uy * s + ux * (r + 100)))
            z0 = ms["z0"]
            g = sb.slope.at(x, y) if getattr(sb, "slope", None) is not None else None
            if g is not None and g < -50:
                # (on M13's slopes: down to the ground at its foot, 0.3 m into it)
                z0 = min(z0, int(g) - 300)
                sb.stats["columns_to_grade"] = sb.stats.get("columns_to_grade", 0) + 1
            if put(sb, "pillar", {"r": r, "h": PT.q(top - slab - z0),
                                  "style": "steel"}, x, y, z0, ux, uy, "open_column"):
                cols += 1
    if ms.get("roof"):
        RF.build_form(sb, ms, "hangar")
    sb.mass_info.append({"mass": ms["k"], "group": "body", "system": None, "rows": 0,
                         "openings": 0, "open": True})
    # its doors are open sides: a record at every entrance, for the access check
    for k, en in enumerate(sb.br["entrances"]):
        at = en.get("at")
        if at is None or at.get("mass") != ms["k"]:
            continue
        x, y = int(round(en["position"][0] * 1000)), int(round(en["position"][1] * 1000))
        e = sb.br["edges"][at["edge"]]
        nrm = M.radians(float(e["normal_deg"]))
        sb.doors.append({"id": f"{sb.bid}.door.e{k}", "kind": "open", "entrance": k,
                         "unit": None, "use": None, "walkway_id": en.get("walkway_id"),
                         "pos": [x, y, ms["z0"]], "normal": [round(float(M.cos(nrm)), 6),
                                                           round(float(M.sin(nrm)), 6)],
                         "w": 3000, "h": top - slab - ms["z0"], "depth": 0, "steps": 0,
                         "flush": False, "moved": False, "edge": at["edge"],
                         "s": int(round(at["s"] * 1000)), "class": e["class"]})
        sb.done_ents.add(k)
    _count(sb, "open_shed")
    sb.stats["open_walls"] = sb.stats.get("open_walls", 0) + walls
    return True


def shed_post(sb) -> None:
    if not sb.br["building"]["attrs"].get("open_sides"):
        top = _flat_top(sb)
        if top is not None:
            _monitor(sb, top)


def hangar_pre(sb) -> None:
    """The facade the hangar's door takes (its longest on open ground, a street or the
    apron), kept blank under the door's head (a mount over it, so the grammar puts panels
    there)."""
    best = None
    for k, ms in enumerate(sb.masses):
        if ms["shape"] != "prism" or ms["z0"] > 50 or ms["z1"] - ms["z0"] < 8000:
            continue
        ring = ms["rings"][0]
        for i in range(len(ring)):
            j = sb._j(ms, 0, i)
            if j is None or ms["deriv"][0][i]:
                continue
            e = sb.br["edges"][j]
            if e["class"] not in ("open", "street", "front", "plaza") or e["length_m"] < 20:
                continue
            if best is None or e["length_m"] > best[0]:
                best = (e["length_m"], j, ms)
    if best is None:
        return
    L, j, ms = best
    Lm = int(L * 1000)
    w = PT.q(min(Lm * 8 // 10, Lm - 6000))
    h = PT.q(min((ms["z1"] - ms["z0"]) * 75 // 100, ms["z1"] - ms["z0"] - 3500))
    if w < 12000 or h < 6000:
        return
    s0 = (Lm - w) // 2
    box = (s0 - 300, s0 + w + 300, -100, h + 400)
    sb.mounts.setdefault(j, []).append(box)
    sb.mounts_raw.setdefault(j, []).append(box)
    sb.hangar_door = (j, s0 + w // 2, w, h, ms)


def hangar_post(sb) -> None:
    hd = getattr(sb, "hangar_door", None)
    if hd is None:
        return
    j, s, w, h, ms = hd
    fa = next((f for f, m in sb.all_facades if f.j == j and m is ms and
               f.soff - 1 <= s <= f.soff + f.L + 1), None)
    if fa is None:
        return
    leaves = int(sb.br["building"]["attrs"].get("doors") or 0) * 2 or 6
    leaves = max(4, min(leaves, 10))
    put_on(sb, fa, "hangar_door", {"w": w, "h": h, "leaves": leaves}, s - fa.soff, ms["z0"],
           "hangar_door")


def lab_post(sb) -> None:
    top = _flat_top(sb)
    if top is None:
        return
    ring = RG.clean(top["rings"][0])
    c, u, v, W, D = frame_of(ring)
    n = 3 + int(_u(sb.bid, "stacks") * 4)
    spots = _free_roof(sb, top, 900, 900, u[0], u[1], 1500, 2400)
    if not spots:
        return
    # in a row along the roof's long axis (the spots nearest its middle line)
    spots.sort(key=lambda p: (abs((p[0] - c[0]) * v[0] + (p[1] - c[1]) * v[1]) // 1000,
                              (p[0] - c[0]) * u[0] + (p[1] - c[1]) * u[1]))
    made, taken = 0, []
    h = PT.q(4000 + 2500 * _u(sb.bid, "stack.h"))
    for x, y in spots:
        if made >= n:
            break
        if not RF._free(RF._bbox(x, y, u[0], u[1], 1400, 1400), taken):
            continue
        if put(sb, "stack", {"r": 300, "h": h}, x, y, top["z1"], u[0], u[1], "fume_stack"):
            taken.append(RF._bbox(x, y, u[0], u[1], 2200, 2200))
            made += 1


# ---------------------------------------------------------------------------
# Villas, terraced rows
# ---------------------------------------------------------------------------

def villa_post(sb) -> None:
    key = sb.bid
    # a chimney on the highest roof (through a pitched roof's attic)
    for ms in sorted(sb.masses, key=lambda m: (-m["z1"], m["k"])):
        if ms["shape"] != "prism" or len(RG.clean(ms["rings"][0])) < 3:
            continue
        rf = ms.get("roof")
        c, u, v, W, D = frame_of(ms["rings"][0])
        if rf and rf.get("kind") not in (None, "flat"):
            z0 = rf["zb"]
            h = PT.q(rf["zt"] - rf["zb"] + 900)
            x = int(round(c[0] + u[0] * W * 0.25))
            y = int(round(c[1] + u[1] * W * 0.25))
        else:
            spots = _free_roof(sb, ms, 900, 700, u[0], u[1], 500, 1200)
            if not spots:
                break
            x, y = spots[0]
            z0, h = ms["z1"], 1500
        put(sb, "chimney", {"w": 900, "d": 700, "h": h}, x, y, z0, u[0], u[1], "chimney")
        break
    # a pergola on a lower roof terrace
    for ms in sb.masses:
        if _is_top(sb, ms) or ms.get("roof") or ms["shape"] != "prism" or \
                _u(f"{key}|{ms['k']}", "pergola") > 0.6:
            continue
        c, u, v, W, D = frame_of(ms["rings"][0])
        spots = _free_roof(sb, ms, 3000, 2600, u[0], u[1], 400, 1000)
        if spots:
            x, y = spots[len(spots) // 2]
            if put(sb, "pergola", {"w": 3000, "d": 2600, "h": 2500}, x, y, ms["z1"], u[0], u[1],
                   "pergola"):
                break


def terraced_post(sb) -> None:
    """Planters along every terrace (a tier's roof edge with no tier over it)."""
    made = 0
    for ms in sb.masses:
        if _is_top(sb, ms) or ms["shape"] != "prism" or ms.get("roof"):
            continue
        ring = RG.clean(ms["rings"][0])
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            if sb._covered_above(ms, a, b):
                continue
            ux, uy, L = AR._unit(a, b)
            if L < 3000:
                continue
            k = int((L - 1200) // 3200)
            for m in range(k):
                s = 900 + 3200 * m + 800
                x = int(round(a[0] + ux * s - uy * 900))
                y = int(round(a[1] + uy * s + ux * 900))
                if not RF._free(RF._bbox(x, y, ux, uy, 1800, 800), RF._taken(sb, ms)):
                    continue
                if put(sb, "garden", {"w": 1400, "d": 600, "h": 500, "g": 450}, x, y,
                       ms["z1"], ux, uy, "terrace_planter"):
                    made += 1
                if made >= 24:
                    return


# ---------------------------------------------------------------------------
# Temple halls, pagodas
# ---------------------------------------------------------------------------

COLONNADE = 1800          # a temple hall's walls set back behind its columns


def temple_pre(sb) -> None:
    """A colonnade round the hall: its wall set back behind columns on the old line; the
    top tier a pagoda roof; the platform cut for its stairs."""
    sb.form_override = "pagoda"
    sb.colonnade = []
    for ms in sb.masses:
        if ms["role"] != "hall" or ms["shape"] != "prism" or len(ms["rings"]) != 1:
            continue
        ring = ms["rings"][0]
        n = len(ring)
        res = AR.offset(ring, ms["eidx"][0], ms["deriv"][0], [-COLONNADE] * n)
        if res is None or AR._thick(res[0]) < 6000:
            continue
        sb.colonnade.append({"ring": list(ring), "z0": ms["z0"], "z1": ms["z1"], "ms": ms})
        ms["outer_ring"] = list(ring)
        ms["colonnade_mm"] = COLONNADE
        ms["rings"], ms["eidx"], ms["deriv"] = [res[0]], [res[1]], [res[2]]
        sb.used["articulation"].append("colonnade")
    _platform_stairs(sb)


def _platform_stairs(sb) -> None:
    """A stair cut into a temple platform at its main entrance: the platform's ring
    notched there, the flight placed after the masses."""
    br = sb.br
    main = next((e for e in br["entrances"] if e["kind"] == "main" and e.get("at")), None)
    if main is None:
        return
    for ms in sb.masses:
        if ms["role"] != "platform" or ms["z0"] > 50 or len(ms["rings"]) != 1:
            continue
        H = ms["z1"] - ms["z0"]
        if H < 600 or H > 3000:
            continue
        ring = ms["rings"][0]
        at = main["at"]
        x, y = int(round(main["position"][0] * 1000)), int(round(main["position"][1] * 1000))
        n = len(ring)
        best = None
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            ux, uy, L = AR._unit(a, b)
            if L < 8000:
                continue
            s = (x - a[0]) * ux + (y - a[1]) * uy
            d = abs((x - a[0]) * uy - (y - a[1]) * ux)
            if 3000 <= s <= L - 3000 and (best is None or d < best[0]):
                best = (d, i, s, ux, uy, L)
        if best is None:
            continue
        _, i, s, ux, uy, L = best
        steps = max(3, -(-H // 160))
        run = steps * 300
        w = 4000
        a = ring[i]
        nx, ny = uy, -ux
        p0 = (int(round(a[0] + ux * (s - w / 2))), int(round(a[1] + uy * (s - w / 2))))
        p1 = (int(round(a[0] + ux * (s + w / 2))), int(round(a[1] + uy * (s + w / 2))))
        q1 = (int(round(p1[0] - nx * run)), int(round(p1[1] - ny * run)))
        q0 = (int(round(p0[0] - nx * run)), int(round(p0[1] - ny * run)))
        new = ring[:i + 1] + [p0, q0, q1, p1] + ring[i + 1:]
        if not RG.is_simple(new):
            continue
        ei = ms["eidx"][0]
        dv = ms["deriv"][0]
        ms["rings"] = [new]
        ms["eidx"] = [ei[:i + 1] + [ei[i], ei[i], ei[i], ei[i]] + ei[i + 1:]]
        ms["deriv"] = [dv[:i + 1] + [True, True, True, False] + dv[i + 1:]]
        mid = ((p0[0] + p1[0]) // 2, (p0[1] + p1[1]) // 2)
        sb.temple_stairs = {"x": mid[0], "y": mid[1], "ux": -nx, "uy": -ny, "w": w,
                            "n": steps, "rise": H // steps, "run": 300, "H": H,
                            "fx": ux, "fy": uy}
        return


def _eaves(sb, tiers: list, out: int, rise: int, drop: int, curl: int) -> int:
    """Eaves between stacked tiers: on every tier with a smaller one on it (both close to
    rectangles), a skirt from the upper's wall down past the lower's."""
    made = 0
    tiers = sorted(tiers, key=lambda m: (m["z0"], m["k"]))
    for lo, hi in zip(tiers, tiers[1:]):
        if abs(hi["z0"] - lo["z1"]) > 60:
            continue
        rl = RG.clean(lo.get("outer_ring") or lo["rings"][0])
        rh = RG.clean(hi["rings"][0])
        if len(rl) < 3 or len(rh) < 3 or not (_rectish(rl) and _rectish(rh)):
            continue
        c, u, v, W, D = frame_of(rl)
        c2, u2, v2, w2, d2 = frame_of(rh)
        if abs(u[0] * u2[0] + u[1] * u2[1]) < 0.99:
            if abs(u[0] * v2[0] + u[1] * v2[1]) > 0.99:
                w2, d2 = d2, w2
            else:
                continue
        if w2 >= W or d2 >= D or abs(c[0] - c2[0]) + abs(c[1] - c2[1]) > 400:
            continue          # (an eave needs the upper tier centred on the lower)
        p = {"W": PT.q(W), "D": PT.q(D), "w": PT.q(w2), "d": PT.q(d2), "out": out,
             "rise": rise, "drop": drop, "curl": curl, "t": 220}
        if put(sb, "eave", p, c[0], c[1], lo["z1"], u[0], u[1], "eave"):
            made += 1
    return made


def temple_post(sb) -> None:
    tiers = [ms for ms in sb.masses if ms["role"] in ("hall", "roof_tier") and
             ms["shape"] == "prism"]
    _eaves(sb, tiers, 1200, 900, 450, 350)
    # columns on the hall's old line, round its colonnade
    for col in getattr(sb, "colonnade", []):
        ring = col["ring"]
        n = len(ring)
        h = PT.q(col["z1"] - col["z0"])
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            ux, uy, L = AR._unit(a, b)
            if L < 3000:
                continue
            k = max(1, int(round((L - 1200) / 3600)))
            for m in range(k + 1):
                s = 600 + (L - 1200) * m / k
                x = int(round(a[0] + ux * s - uy * 450))
                y = int(round(a[1] + uy * s + ux * 450))
                put(sb, "pillar", {"r": 280, "h": h, "style": "temple"}, x, y, col["z0"],
                    ux, uy, "temple_column")
    st = getattr(sb, "temple_stairs", None)
    if st is not None:
        p = {"w": st["w"], "n": st["n"], "rise": st["rise"], "run": st["run"],
             "slot": "stone"}
        # (the flight's frame: x across the stair, y up it into the platform)
        if put(sb, "stairs", p, st["x"], st["y"], 0, st["fx"], st["fy"], "temple_stairs"):
            sb.stats["stairs"] = sb.stats.get("stairs", 0) + 1
    top = max(tiers, key=lambda m: (m["z1"], -m["k"])) if tiers else None
    if top is not None and not (top.get("roof") and top["roof"].get("kind") == "pagoda"):
        _finial(sb, top, 3500)


def _finial(sb, top, h: int) -> None:
    ring = RG.clean(top["rings"][0])
    if len(ring) < 3:
        return
    c, u, v, W, D = frame_of(ring)
    rf = top.get("roof")
    z = top["z1"] if not rf else rf.get("ridge", (0, 0, 0, rf["zt"]))[3]
    put(sb, "finial", {"h": h, "r": 400}, c[0], c[1], z, u[0], u[1], "finial")


def pagoda_pre(sb) -> None:
    sb.form_override = "pagoda"


def pagoda_post(sb) -> None:
    tiers = [ms for ms in sb.masses if ms["shape"] == "prism" and ms["z1"] - ms["z0"] >= 2000]
    _eaves(sb, tiers, 1100, 900, 450, 380)
    top = max(tiers, key=lambda m: (m["z1"], -m["k"])) if tiers else None
    if top is not None:
        _finial(sb, top, 4500)


# ---------------------------------------------------------------------------
# Gate houses, terminals, control towers, stations
# ---------------------------------------------------------------------------

def gatehouse_post(sb) -> None:
    for ms in sb.masses:
        if ms["shape"] != "prism" or ms["z1"] - ms["z0"] < 3000:
            continue
        z = max(ms["z1"] - 350, 3000)
        if z + 300 > ms["z1"] + 1200:
            continue
        for fa in facades(sb, ms):
            if fa.L < 2500 or fa.j is None:
                continue
            room = fa.room(fa.L // 2, z, 1500, 1500)
            if room < 900:
                continue
            put_on(sb, fa, "canopy", {"L": PT.q(fa.L - 200), "d": PT.q(min(room, 1500)),
                                      "t": 350}, fa.L // 2, z, "booth_canopy")
        c, u, v, W, D = frame_of(ms["rings"][0])
        put(sb, "beacon", {"s": 200}, c[0], c[1], ms["z1"], u[0], u[1], "booth_light")


def vault_pre(sb) -> None:
    sb.form_override = "barrel"


def terminal_post(sb) -> None:
    _door_canopies(sb, ("main", "unit"), 1800)


def control_tower_mass(sb, ms) -> bool:
    """The cab: a floor band, a glazed band leaning out from its foot to its head, mullions,
    a roof with its overhang (`typeparts.gen_cab`); a radome and antennas on its roof."""
    if ms["role"] != "cab" or ms["shape"] != "prism":
        return False
    ring = RG.clean(ms["rings"][0])
    if len(ring) < 3:
        return False
    c, u, v, W, D = frame_of(ring)
    H = ms["z1"] - ms["z0"]
    if H < 3500 or W < 6000 or D < 6000:
        return False
    h = PT.q(H - 600 - 450 - 650)
    p = {"W": PT.q(W), "D": PT.q(D), "h": h, "lean": 500, "over": 500}
    if not put(sb, "cab", p, c[0], c[1], ms["z0"], u[0], u[1], "cab"):
        return False
    top = ms["z0"] + 600 + h + 1100
    put(sb, "radar", {"r": 1200}, c[0], c[1], top, u[0], u[1], "radar")
    for sx in (-1, 1):
        x = int(round(c[0] + u[0] * sx * (W // 2 - 1500) + v[0] * (D // 2 - 1500)))
        y = int(round(c[1] + u[1] * sx * (W // 2 - 1500) + v[1] * (D // 2 - 1500)))
        RF._place(sb, "antenna", {"h": 4000, "style": "whip"}, x, y, top, u[0], u[1])
    sb.mass_info.append({"mass": ms["k"], "group": "top", "system": None, "rows": 0,
                         "openings": 0, "cab": True})
    sb.used["glass"] = True
    return True


def control_tower_post(sb) -> None:
    for ms in sb.masses:
        if ms["role"] != "shaft":
            continue
        for fa in facades(sb, ms):
            if fa.L < 4000 or fa.j is None:
                continue
            h = PT.q(ms["z1"] - ms["z0"] - 4000)
            if h < 4000:
                continue
            put_on(sb, fa, "neon_strip", {"L": 400, "h": h, "d": 60, "slot": "glazing"},
                   fa.L // 2 - 200, ms["z0"] + 3000, "shaft_slot")


def station_post(sb) -> None:
    _door_canopies(sb, ("main", "unit"), 1800)


# ---------------------------------------------------------------------------
# Parking structures, straddle buildings
# ---------------------------------------------------------------------------

def parking_mass(sb, ms) -> bool:
    """A ramp as a sloped deck: a slab rising along its long axis from its foot to its top,
    curbs either side."""
    if ms["role"] != "ramp" or ms["shape"] != "prism":
        return False
    ring = RG.clean(ms["rings"][0])
    if len(ring) != 4 or not _rectish(ring):
        return False
    c, u, v, W, D = frame_of(ring)
    H = ms["z1"] - ms["z0"]
    if W < 6000 or H < 1000:
        return False
    from .typeparts import quad
    buf = sb.buf
    t = 300

    def P(x, y, z):
        return (int(round(c[0] + u[0] * x + v[0] * y)), int(round(c[1] + u[1] * x + v[1] * y)),
                int(z))
    x0, x1, y0, y1 = -W // 2, W // 2, -D // 2 + 200, D // 2 - 200
    z0, z1 = ms["z0"], ms["z1"]
    # the deck: a wedge from z0 at x0 up to z1 at x1 (its underside t lower, down to z0)
    top = [P(x0, y0, z0 + t), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z0 + t)]
    bot = [P(x0, y0, z0), P(x1, y0, z1 - t), P(x1, y1, z1 - t), P(x0, y1, z0)]
    buf.new_part()
    upn = (-u[0] * 0.1, -u[1] * 0.1, 1.0)
    quad(buf, "structure", *top, upn)
    quad(buf, "structure", bot[0], bot[3], bot[2], bot[1], (u[0] * 0.1, u[1] * 0.1, -1.0))
    quad(buf, "structure", bot[0], bot[1], top[1], top[0], (-v[0], -v[1], 0.0))
    quad(buf, "structure", bot[3], top[3], top[2], bot[2], (v[0], v[1], 0.0))
    quad(buf, "structure", bot[0], top[0], top[3], bot[3], (-u[0], -u[1], 0.0))
    quad(buf, "structure", bot[1], bot[2], top[2], top[1], (u[0], u[1], 0.0))
    for yy in (-D // 2, D // 2 - 200):
        ct = [P(x0, yy, z0 + t + 400), P(x1, yy, z1 + 400), P(x1, yy + 200, z1 + 400),
              P(x0, yy + 200, z0 + t + 400)]
        cb = [P(x0, yy, z0), P(x1, yy, z1 - t), P(x1, yy + 200, z1 - t), P(x0, yy + 200, z0)]
        buf.new_part()
        quad(buf, "structure", *ct, upn)
        quad(buf, "structure", cb[0], cb[3], cb[2], cb[1], (0.0, 0.0, -1.0))
        quad(buf, "structure", cb[0], cb[1], ct[1], ct[0], (-v[0], -v[1], 0.0))
        quad(buf, "structure", cb[3], ct[3], ct[2], cb[2], (v[0], v[1], 0.0))
        quad(buf, "structure", cb[0], ct[0], ct[3], cb[3], (-u[0], -u[1], 0.0))
        quad(buf, "structure", cb[1], cb[2], ct[2], ct[1], (u[0], u[1], 0.0))
    sb.mass_info.append({"mass": ms["k"], "group": "structure", "system": None, "rows": 0,
                         "openings": 0, "ramp": True})
    _count(sb, "ramp")
    return True


def straddle_post(sb) -> None:
    for ms in sb.masses:
        if ms["role"] != "span" or ms["z0"] < 3000:
            continue
        for fa in facades(sb, ms):
            if fa.L < 8000 or fa.j is None:
                continue
            L = PT.q(fa.L - 400)
            put_on(sb, fa, "girder", {"L": L, "h": 1200, "w": 150}, 200, ms["z0"] + 1200,
                   "transfer_girder")


def wheel_mass(sb, ms) -> bool:
    from . import heroes as HE
    return HE.wheel_mass(sb, ms)


PRE = {"temple": temple_pre, "pagoda": pagoda_pre, "hangar": hangar_pre,
       "terminal": vault_pre, "station": vault_pre}
MASS = {"shed": shed_mass, "control_tower": control_tower_mass, "parking": parking_mass,
        "wheel": wheel_mass}
POST = {"shanty": shanty_post, "megablock": megablock_post, "warehouse": warehouse_post,
        "shed": shed_post, "yard": yard_post, "hangar": hangar_post, "lab": lab_post,
        "villa": villa_post, "terraced": terraced_post, "temple": temple_post,
        "pagoda": pagoda_post, "gatehouse": gatehouse_post, "terminal": terminal_post,
        "control_tower": control_tower_post, "station": station_post,
        "straddle": straddle_post}
