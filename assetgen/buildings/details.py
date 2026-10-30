"""Facade details (scope 5.1.3, AG4): what a building's walls carry beyond its facade system
and street front, placed after the grammar on solid wall (`fronts._open_at`), off every
mount, inside the envelope:

- **corner downpipes**: AG3's downpipe (`frontparts.gen_pipe`) at the convex corners of
  every building up to 12 floors on the ground whose system is not a curtain wall, on the
  facades AG3 leaves (AG3 puts one on blind and fire walls);
- **fire escapes** (`roofparts.gen_escape`): on residential, mixed and hotel buildings and
  shopfront rows (flats over the shops) of three to eight floors in the eras that had them
  (heritage, neon, mixed modern, brutalist),
  on an alley, street, court or open facade with room for 1.2 m and no shop under it;
- **kitchen exhaust ducts** (`gen_duct`): for food and bar units, on a back facade of their
  mass (alley, blind, court or open), up past the roof;
- **wall vents** (`gen_wall_vent`): louvered grilles on blind and alley walls by grime;
- **cable conduits** (`gen_conduit`): bundles along a floor line where grime and low
  wealth run cables outside;
- **CCTV cameras** (`gen_camera`): over doors by the district's danger and the owner's
  security.

The line with AG3 and AG8: AG3 keeps its street fronts, mounts and blind-wall downpipes;
AG8 keeps the facade props M6 places (AC units, wall lights, signs, awnings, scaffolding,
overhead cables between buildings, ivy). Nothing here draws what either draws.
"""

from __future__ import annotations

from . import decks as DK
from . import fronts as FR
from . import genome as GN
from . import parts as PT
from . import systems as SY

ESCAPE_ERAS = {"heritage": 0.6, "neon_retro": 0.5, "mixed_modern": 0.25, "brutalist": 0.15}
ESCAPE_USES = ("residential", "mixed", "hotel")
ESCAPE_TYPES = ("building.shopfront_row",)      # (flats over the shops)
DUCT_USES = ("food", "bar")
BACK = ("alley", "blind", "courtyard", "atrium", "open")
MAX_PIPES = 4
MAX_VENTS = 6
MAX_CAMERAS = 4


def _u(key: str, purpose: str) -> float:
    return GN.u(key, purpose, "ag4.detail")


def _cls_share(fa) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in fa.regions:
        a = (r["s"][1] - r["s"][0]) * (r["z"][1] - r["z"][0])
        out[r["class"]] = out.get(r["class"], 0.0) + a
    tot = sum(out.values()) or 1.0
    return {k: v / tot for k, v in out.items()}


def _main_class(fa) -> str:
    sh = _cls_share(fa)
    if not sh:
        return fa.rec["class"] if fa.rec else "open"
    return max(sorted(sh), key=lambda k: sh[k])


def _mounted(sb, fa, s0: int, s1: int, z0: int, z1: int) -> bool:
    for m0, m1, za, zb in sb.mounts.get(fa.j, []):
        if m0 < s1 + fa.soff and m1 > s0 + fa.soff and za < z1 and zb > z0:
            return True
    for m0, m1, za, zb, kind in sb.marks.get(fa.j, []):
        if m0 - 300 < s1 + fa.soff and m1 + 300 > s0 + fa.soff and za < z1 and zb > z0:
            return True
    return False


def _free(sb, fa, s0: int, s1: int, z0: int, z1: int) -> bool:
    so = fa.soff
    return not FR._open_at(sb, fa.j, s0 + so, s1 + so, z0, z1) and \
        not _mounted(sb, fa, s0, s1, z0, z1)


def _on(sb, fa, family: str, p: dict, s: int, z: int) -> bool:
    """Place a detail at s along `fa`, height z, if it stays inside the envelope (a shanty
    stack's boxes and a podium's setbacks leave air beside a wall)."""
    from . import envelope as EN
    x, y, _ = fa.P(s, z)
    if not EN.fits(sb.br, family, p, x, y, z, fa.ux, fa.uy):
        sb.stats["details_refused"] = sb.stats.get("details_refused", 0) + 1
        return False
    sb.parts.on(fa, family, p, s, z)
    return True


def details(sb) -> None:
    br = sb.br
    b = br["building"]
    if b["landmark"]:
        return
    pipes(sb)
    escape(sb)
    ducts(sb)
    vents(sb)
    conduits(sb)
    cameras(sb)


def pipes(sb) -> None:
    """Downpipes at convex corners (the start of every facade that turns from the one
    before it), on the facades AG3 leaves."""
    b = sb.br["building"]
    if b["floors"] > 12:
        return
    n = 0
    for fa, ms in sb.all_facades:
        if n >= MAX_PIPES or fa.j is None or ms.get("arcade") or ms.get("portal"):
            continue
        if ms["z0"] > sb.ground + 50 or ms["z1"] - ms["z0"] < 4000:
            continue
        sysname = sb.gm["genes"].get(f"{SY.role_group(ms['role'])}.system")
        if sysname in SY.CURTAIN or sysname is None:
            continue
        sh = _cls_share(fa)
        if sh.get("blind", 0) + sh.get("firewall", 0) + sh.get("party", 0) + \
                sh.get("hidden", 0) >= 0.5 or fa.L < 4000:
            continue
        if not FR_convex(fa):
            continue
        s = max(fa.c0 // 2, 180)
        if s > fa.L - 400 or not _free(sb, fa, s - 150, s + 150, ms["z0"], ms["z1"]):
            continue
        if _on(sb, fa, "pipe", {"h": PT.q(ms["z1"] - ms["z0"] - 200)}, s, ms["z0"]):
            n += 1
    if n:
        sb.stats["corner_pipes"] = sb.stats.get("corner_pipes", 0) + n
        sb.used["details"] = True


def FR_convex(fa) -> bool:
    """Whether the facade turns left from the one before it (a convex corner of a
    counterclockwise ring)."""
    d_in = fa.d_in
    return d_in[0] * fa.uy - d_in[1] * fa.ux > 0.34


def escape(sb) -> None:
    br = sb.br
    b = br["building"]
    era = sb.gm.get("era")
    if (b["use"] not in ESCAPE_USES and b["type"] not in ESCAPE_TYPES) or \
            not 3 <= b["floors"] <= 8 or _u(sb.bid, "escape") >= ESCAPE_ERAS.get(era, 0.0):
        return
    if sb.gm["genes"].get("body.balcony", "none") not in ("none", "balconette"):
        return
    cands = []
    for fa, ms in sb.all_facades:
        if fa.j is None or ms["z0"] > sb.ground + 50 or ms.get("portal") or \
                ms["floors"] < 3 or fa.L < 7000:
            continue
        cls = _main_class(fa)
        if cls == "alley":
            room = 1300
        elif cls in ("street", "front", "courtyard", "open", "upper"):
            room = fa.room(fa.L // 2, 4000, 1300, 1500)
        else:
            continue
        if room < 1200:
            continue
        rank = {"alley": 0, "courtyard": 1, "open": 2, "upper": 2}.get(cls, 3)
        cands.append((rank, -fa.L, len(cands), fa, ms))
    for _, _, _, fa, ms in sorted(cands, key=lambda c: c[:3]):
        n = ms["floors"]
        zs = [ms["z0"] + (ms["z1"] - ms["z0"]) * f // n for f in range(1, n)]
        zs = [z for z in zs if z >= 3200]
        if len(zs) < 2:
            continue
        w = PT.q(min(5000, fa.L * 4 // 10))
        s = fa.L // 2
        s0, s1 = s - w // 2 - 200, s + w // 2 + 200
        if s0 < fa.c0 + 300 or s1 > fa.L - fa.c1 - 300:
            continue
        if _mounted(sb, fa, s0, s1, 0, ms["z1"]):
            continue
        x, y, _ = fa.P(s, 0)
        if sb.clear.hits(x - w, y - w, x + w, y + w, 3000, zs[-1] + 1100):
            continue
        z0 = zs[0]
        p = {"w": w, "d": 1200, "zs": [z - z0 for z in zs], "ladder": PT.q(z0 - 3000)}
        if not _on(sb, fa, "escape", p, s, z0):
            continue
        sb.stats["fire_escapes"] = sb.stats.get("fire_escapes", 0) + 1
        sb.used["details"] = True
        return


def ducts(sb) -> None:
    br = sb.br
    units = [u for u in br["units"] if u.get("use") in DUCT_USES and u.get("at")]
    if not units:
        return
    made = 0
    for un in units:
        if made >= 2:
            break
        k = un["at"]["mass"]
        ux, uy = un["edge"][0]
        best = None
        for fa, ms in sb.all_facades:
            if fa.j is None or ms["k"] != k or ms["z0"] > sb.ground + 50 or \
                    ms["z1"] - ms["z0"] > 30000 or ms["z1"] - ms["z0"] < 6000:
                continue
            if _main_class(fa) not in BACK or fa.L < 2000:
                continue
            mx, my, _ = fa.P(fa.L // 2, 0)
            d = (mx - ux * 1000) ** 2 + (my - uy * 1000) ** 2
            if best is None or d < best[0]:
                best = (d, fa, ms)
        if best is None:
            continue
        _, fa, ms = best
        # (0.6 m over the roof; AG10: under an M14 deck, stopped under its soffit)
        top = ms["z1"] + 600
        ceil = DK.ceiling_mm(sb.br)
        if ceil is not None:
            top = min(top, ceil - int(DK.CEIL_GAP_M * 1000))
        for t in (0.5, 0.3, 0.7, 0.15, 0.85):
            s = int(fa.c0 + (fa.L - fa.c0 - fa.c1) * t)
            if _free(sb, fa, s - 300, s + 300, 3000, ms["z1"]) and \
                    _on(sb, fa, "duct", {"w": 400, "dd": 300,
                                         "h": PT.q(top - 3200)}, s, 3200):
                made += 1
                break
    if made:
        sb.stats["ducts"] = sb.stats.get("ducts", 0) + made
        sb.used["details"] = True


def vents(sb) -> None:
    grime = float((sb.br["building"].get("style") or {}).get("grime", 0.4))
    n = 0
    for fa, ms in sb.all_facades:
        if n >= MAX_VENTS or fa.j is None or fa.L < 3000:
            continue
        if _main_class(fa) not in ("blind", "alley", "courtyard"):
            continue
        key = f"{sb.bid}|{ms['k']}|{fa.j}|{fa.a}"
        for i in range(3):
            if n >= MAX_VENTS or _u(key, f"vent{i}") > 0.25 + 0.5 * grime:
                continue
            s = int(fa.c0 + 300 + (fa.L - fa.c0 - fa.c1 - 600) * _u(key, f"vs{i}"))
            z = int(ms["z0"] + 3000 + max(ms["z1"] - ms["z0"] - 4500, 0) * _u(key, f"vz{i}"))
            if z + 300 > ms["z1"] - 300 or not _free(sb, fa, s - 300, s + 300, z - 100,
                                                     z + 400):
                continue
            if _on(sb, fa, "wall_vent", {"w": 400, "h": 300}, s, z):
                n += 1
    if n:
        sb.stats["wall_vents"] = sb.stats.get("wall_vents", 0) + n
        sb.used["details"] = True


def conduits(sb) -> None:
    if sb.irr < 0.3:
        return
    n = 0
    for fa, ms in sb.all_facades:
        if n >= 2 or fa.j is None or fa.L < 6000 or ms["floors"] < 2:
            continue
        if _main_class(fa) not in ("street", "front", "alley"):
            continue
        key = f"{sb.bid}|{ms['k']}|{fa.j}|{fa.a}"
        if _u(key, "conduit") > sb.irr:
            continue
        f = 1 + int(_u(key, "cf") * max(ms["floors"] - 1, 1))
        zf = ms["z0"] + (ms["z1"] - ms["z0"]) * min(f, ms["floors"] - 1) // ms["floors"] - 150
        if zf < 3500:
            continue
        s0, s1 = fa.c0 + 200, fa.L - fa.c1 - 200
        if s1 - s0 < 3000 or _mounted(sb, fa, s0, s1, zf - 300, zf + 100):
            continue
        k = 1 + int(_u(key, "ck") * 3) % 3
        drop = PT.q(min(zf - 3200, 6000))
        if _on(sb, fa, "conduit", {"L": PT.q(s1 - s0), "k": k, "drop": drop}, s0, zf):
            n += 1
    if n:
        sb.stats["conduits"] = sb.stats.get("conduits", 0) + n
        sb.used["details"] = True


def cameras(sb) -> None:
    dist = sb.br.get("district") or {}
    danger = float(dist.get("danger") or 0.3)
    era = sb.gm.get("era")
    sec = 0.3 if era in ("corporate_glass", "clean_tech", "transit_modern") else 0.0
    facades = {}
    for fa, ms in sb.all_facades:
        if fa.j is not None:
            facades.setdefault(fa.j, []).append((fa, ms))
    n = 0
    for d in sorted(sb.doors, key=lambda d: d["id"]):
        if n >= MAX_CAMERAS or d.get("flush") or d["kind"] == "shop" or d.get("edge") is None:
            continue
        if _u(d["id"], "cam") > 0.15 + 0.5 * danger + sec:
            continue
        for fa, ms in facades.get(d["edge"], []):
            s = d["s"] - fa.soff + d["w"] // 2 + 450
            z = max(d["pos"][2] + d["h"] + 500, 3300)
            if not 200 < s < fa.L - 200 or not ms["z0"] <= z <= ms["z1"] - 300:
                continue
            if not _free(sb, fa, s - 150, s + 150, z - 200, z + 200):
                continue
            st = "dome" if _u(d["id"], "camst") < 0.4 else "bullet"
            if _on(sb, fa, "camera", {"style": st}, s, z):
                n += 1
                break
    if n:
        sb.stats["cameras"] = sb.stats.get("cameras", 0) + n
        sb.used["details"] = True
