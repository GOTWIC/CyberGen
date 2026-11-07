"""AG15: facades that are not rows of rectangles, and the lights a building wears at night
(scope 14.16).

- **Patterns** (`pattern_ops`, the genome's `{g}.wpattern`): a row's openings moved, sized or
  left out by the row's floor and the bay, so the windows stop lining up in a grid: staggered
  by floor, mixed sizes, stepped (each floor's openings a step further along: diagonal runs),
  a checkerboard, a scatter, wide and narrow floors alternating. A curtain wall's bays stay
  full (a pattern then swaps glass for spandrel or narrows a pane); ribbons, louvers, pods,
  clerestories and patchwork keep theirs (`systems.PATTERN_FIXED`).
- **AG15's systems' parts** (`opening`, `lines`): honeycomb panels over the panes (`hex`),
  folded glass bays (`fold`, a V of glass out of the wall), perforated mesh screens on
  brackets (`mesh`), a media facade's screen over a block of floors (`media`), diagonal
  glazing (diagonal mullions over every cell, `diag`), LED-strip mullions on the bay lines
  (`led`, emissive in the building's accent); the building-wide skin (`skin`) adds LED
  strips or fritted glass (`frit`) to any glazed system.
- **Night** (`lights`): crown and edge lighting on towers (`crown_light`: LED strips up the
  convex corners, a band round the top), a lit logo sign near the top of the main front
  (`logo`).

Every part is a closed solid in the part frame (`parts.py`'s rules: x along the facade, y
into the wall, z up, mm) and registered with `parts.GEN`, `REACH` and its type; the LED,
media and logo faces are emissive slots (`led_<accent>`, `screen_media_*`), lit by the masters
with `MPC_CityGen`'s Night. Nothing goes where a mount, a skybridge or a corridor is.
"""

from __future__ import annotations

import hashlib

from . import parts as PT
from . import systems as SY

LED_T = 60            # an LED strip's width and how far it stands out (mm)
HEX_D = 120           # a honeycomb panel's depth out of the wall
HEX_T = 70            # its members' width
FOLD_D = (300, 450)   # how far a folded glass bay's apex stands out
MESH_OFF = 300        # a mesh screen's distance from the wall
LOGO_MAX = 9000       # a logo's largest width
MEDIA_MIN_W = 6000    # a media screen's least width


def _u(key: str, purpose: str) -> float:
    h = hashlib.blake2b(f"ag15.skin|{key}|{purpose}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little") / 2.0 ** 64


# ---------------------------------------------------------------------------
# Part generators
# ---------------------------------------------------------------------------

def gen_led(p: dict, b) -> None:
    """An LED strip: vertical (`dir` v, L tall from z 0) or horizontal (h, L long centered,
    on z 0), t wide and t out of the wall, in its emissive slot."""
    t, slot = p["t"], p["slot"]
    if p["dir"] == "v":
        PT.box(b, slot, -t // 2, t // 2, -t, 0, 0, p["L"])
    else:
        PT.box(b, slot, -p["L"] // 2, p["L"] // 2, -t, 0, -t // 2, t // 2)


def _hexes(w: int, h: int, c: int, t: int) -> list[list[tuple[int, int]]]:
    """Flat-topped hexagons of width c on a honeycomb grid inside (-w/2..w/2, 0..h) with t
    of member round each (the holes of a honeycomb panel)."""
    r = c // 2
    dx = 3 * r // 2 + t
    dz = int(round(0.866 * c)) + t
    out = []
    j = 0
    x = -w // 2 + t + r
    while x + r + t <= w // 2:
        z = t + dz // 2 + (dz // 2 if j % 2 else 0)
        while z + dz // 2 <= h - t // 2 + 1:
            hz = int(round(0.866 * r))
            out.append([(x + r, z), (x + r // 2, z + hz), (x - r // 2, z + hz), (x - r, z),
                        (x - r // 2, z - hz), (x + r // 2, z - hz)])
            z += dz
        x += dx
        j += 1
    return out


def gen_hex(p: dict, b) -> None:
    """A honeycomb panel in front of an opening (w x h from z 0): a plate d deep with
    hexagonal holes, its back on the wall plane."""
    w, h, d = p["w"], p["h"], p["d"]
    holes = _hexes(w, h, p["c"], p["t"])
    PT.prism(b, "hex", [(-w // 2, 0), (w // 2, 0), (w // 2, h), (-w // 2, h)], holes,
             -d, 0, "y")


def gen_fold(p: dict, b) -> None:
    """A folded glass bay: a V of glass d out of the wall over the opening (w x h from z 0),
    its apex off the middle by `off`; a mullion down the apex."""
    w, h, d, off = p["w"], p["h"], p["d"], p["off"]
    PT.prism(b, "fold_glass", [(-w // 2, 0), (off, -d), (w // 2, 0)], [], 0, h, "z")
    PT.box(b, "mullion", off - 25, off + 25, -d - 30, -d + 30, 0, h)


def gen_mesh(p: dict, b) -> None:
    """A perforated mesh screen w x h (from z 0) `off` out of the wall, on two brackets."""
    w, h, off = p["w"], p["h"], p["off"]
    PT.box(b, "mesh", -w // 2, w // 2, -off - 30, -off, 0, h)
    for z in (h // 5, 4 * h // 5):
        for x in (-w // 2 + 60, w // 2 - 60):
            PT.box(b, "mesh", x - 15, x + 15, -off, 0, z - 40, z + 40)


def gen_media(p: dict, b) -> None:
    """A media facade's screen (w x h from z 0) in a dark frame 0.2 m out of the wall."""
    w, h = p["w"], p["h"]
    PT.frame_y(b, "media_frame", -w // 2 - 150, w // 2 + 150, -150, h + 150, 150, -200, 0)
    PT.box(b, p["slot"], -w // 2, w // 2, -180, -20, 0, h)


def gen_frit(p: dict, b) -> None:
    """Fritted glass: a light panel over the lower share of an opening's pane (w x h from
    z 0, in front of the pane at the reveal r)."""
    w, h, r = p["w"], p["h"], p["r"]
    y1 = r - 4
    PT.box(b, "frit", -w // 2 - PT.OVERLAP, w // 2 + PT.OVERLAP, max(y1 - 40, 2), y1,
           -PT.OVERLAP, h)


def gen_logo(p: dict, b) -> None:
    """A logo sign w x h (from z 0): a dark backboard 0.25 m out with an emblem in LED tubes:
    a ring and a bar through it, by `style` (ring, bars, chevron)."""
    w, h, slot = p["w"], p["h"], p["slot"]
    PT.box(b, "logo_back", -w // 2, w // 2, -250, 0, 0, h)
    cz = h // 2
    r = min(w, h) * 4 // 10
    t = max(80, r // 7)
    st = p["style"]
    if st == "ring":
        PT.prism(b, slot, PT.ngon(0, cz, r, 24, 0.5), [PT.ngon(0, cz, r - t, 24, 0.5)],
                 -320, -250, "y")
        PT.box(b, slot, -t // 2, t // 2, -320, -250, cz - r + t, cz + r - t)
    elif st == "bars":
        for k in (-2, -1, 0, 1, 2):
            x = k * (w // 6)
            hh = r * (5 - abs(k)) // 5
            PT.box(b, slot, x - t // 2, x + t // 2, -320, -250, cz - hh, cz + hh)
    else:
        for k in (-1, 1):
            x0 = k * r // 2
            PT.prism(b, slot, [(x0 - r // 2, cz - r // 2), (x0 - r // 2 + t, cz - r // 2),
                               (x0 + t, cz + r // 2), (x0, cz + r // 2)], [], -320, -250, "y")
            PT.prism(b, slot, [(x0, cz + r // 2), (x0 + t, cz + r // 2),
                               (x0 + r // 2 + t, cz - r // 2), (x0 + r // 2, cz - r // 2)],
                     [], -320, -250, "y")


FAMILIES = {"led": gen_led, "hex": gen_hex, "fold": gen_fold, "mesh": gen_mesh,
            "media": gen_media, "frit": gen_frit, "logo": gen_logo}
PT.GEN.update(FAMILIES)
PT.REACH.update({"led": "flush", "hex": "flush", "fold": "strip", "mesh": "strip",
                 "media": "strip", "frit": "flush", "logo": "strip"})
PT.TYPE_SUB.update({"hex": "honeycomb", "fold": "glass", "mesh": "screen", "media": "screen",
                    "frit": "glass"})
PT.TYPE_KEY.update({"led": "dir", "logo": "style"})


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def pattern_ops(pattern: str, ops: list[tuple], f: int, cuts, key: str, curtain: bool,
                win: str) -> list[tuple]:
    """A window row's openings (a, b, back, bay) after the pattern, for row f: each stays in
    its bay (`cuts`) with `shell.PIER_MIN` of pier, widths in 5 cm steps."""
    if pattern == "grid" or win in SY.PATTERN_FIXED or not ops:
        return ops
    out = []
    for op in ops:
        a, b, back, jb = op[0], op[1], op[2], op[3]
        if jb is None or jb < 0 or jb >= len(cuts) or back != "glass":
            out.append(op)
            continue
        b0, b1 = cuts[jb]
        w = b - a
        lo_s, hi_s = b0 + 75, b1 - 75
        if pattern == "checker":
            if (f + jb) % 2:
                continue
        elif pattern == "scatter":
            if _u(key, f"sc{f}.{jb}") < 0.28:
                continue
        elif pattern == "mixed":
            k = (0.55, 1.0, 1.0, 1.35)[int(_u(key, f"mx{f}.{jb}") * 4) % 4]
            nw = min(int(w * k) // 50 * 50, hi_s - lo_s)
            if curtain:
                nw = min(nw, w)
            m = (a + b) // 2
            a, b = m - nw // 2, m - nw // 2 + nw
        elif pattern == "alternate":
            k = 1.25 if f % 2 else 0.65
            nw = min(int(w * k) // 50 * 50, hi_s - lo_s)
            if curtain:
                nw = min(nw, w)
            m = (a + b) // 2
            a, b = m - nw // 2, m - nw // 2 + nw
        elif pattern in ("stagger", "stepped") and not curtain:
            room = min(a - lo_s, hi_s - b)
            if pattern == "stagger":
                sh = (1 if f % 2 else -1) * room * 4 // 5
            else:
                sh = ((f + jb) % 3 - 1) * room * 4 // 5
            a, b = a + sh, b + sh
        elif pattern in ("stagger", "stepped"):
            # (a curtain wall's full bays: the pane narrowed to one side by floor)
            nw = (w * 7 // 10) // 50 * 50
            side = (f % 2) if pattern == "stagger" else (f + jb) % 2
            a, b = (a, a + nw) if side else (b - nw, b)
        if b - a >= 350 and a >= lo_s - 75 and b <= hi_s + 75:
            out.append((a, b, back, jb))
    return out


# ---------------------------------------------------------------------------
# Per opening and per facade
# ---------------------------------------------------------------------------

def _free(mounts, s0, s1, z0, z1) -> bool:
    return not any(s0 < m1 and s1 > m0 and z0 < mz1 and z1 > mz0
                   for m0, m1, mz0, mz1 in mounts)


def opening(sb, fa, ms: dict, g: str, sysname: str, row: tuple, a_: int, b_: int,
            reveal: int, key: str, i: int, mounts) -> None:
    """The AG15 parts of one window opening: a honeycomb panel, a folded glass bay, a mesh
    screen (on the system's floors by pattern), fritted glass (the building's skin)."""
    lo, hi, kind, f, full, zf = row
    if kind != "win":
        return
    genes, cont = sb.gm["genes"], sb.gm["cont"]
    feat = SY.SYSTEMS[sysname].get("feature")
    w, h = b_ - a_, hi - lo
    if w < 600 or h < 900:
        return
    P = sb.parts
    mid = (a_ + b_) // 2
    used = sb.used["parts"].setdefault(g, set())
    qw, qh = PT.q(w), PT.q(h)
    if feat == "hex" and _free(mounts, a_ - 50, b_ + 50, lo - 50, hi + 50):
        c = PT.q(min(900, max(450, min(w, h) // 3)))
        P.on(fa, "hex", {"w": PT.q(w + 100), "h": PT.q(h + 100), "c": c, "t": HEX_T,
                         "d": HEX_D}, mid, lo - 50)
        used.add("hex")
    elif feat == "fold" and lo >= sb._low(fa, mid) and \
            _free(mounts, a_ - 50, b_ + 50, lo, hi):
        d = FOLD_D[0] if int(cont.get(f"{g}.fin_m", 0.3) * 1000) < 400 else FOLD_D[1]
        off = 0 if genes.get(f"{g}.rhythm") == "even" else PT.q(w // 4)
        fp = {"w": qw, "h": qh, "d": d, "off": off}
        # (AG14's rule for what leaves a wall near a lane under its headroom: M22's
        # layouts put a lane 0.3 m off a front)
        if sb._clear_of_lanes(fa, "fold", fp, mid, lo):
            P.on(fa, "fold", fp, mid, lo)
            used.add("fold")
    elif feat == "mesh" and lo - 150 >= sb._low(fa, mid) and \
            (f + (0 if _u(key, "mesh.par") < 0.5 else 1)) % 2 == 0 and \
            _free(mounts, a_ - 100, b_ + 100, lo - 150, hi + 150):
        mp = {"w": PT.q(w + 200), "h": PT.q(h + 300), "off": MESH_OFF}
        if sb._clear_of_lanes(fa, "mesh", mp, mid, lo - 150):
            P.on(fa, "mesh", mp, mid, lo - 150)
            used.add("mesh")
    if genes.get("skin") == "frit" and g == "body" and full <= lo + 200:
        P.on(fa, "frit", {"w": qw, "h": PT.q(h * 4 // 10), "r": reveal}, mid, lo)
        sb.used["skin"] = True


def lines(sb, fa, ms: dict, g: str, sysname: str, cuts, rows, reveal: int, mounts) -> None:
    """AG15's parts on a facade's bay lines and cells: LED-strip mullions (the led system,
    or the led skin on every other line of the body), diagonal glazing's mullions, a media
    facade's screen."""
    if not cuts or not rows:
        return
    genes = sb.gm["genes"]
    feat = SY.SYSTEMS[sysname].get("feature")
    P = sb.parts
    used = sb.used["parts"].setdefault(g, set())
    lines_ = [cuts[0][0]] + [b1 for _, b1 in cuts]
    zb = max(ms["z0"], rows[0][0] - 150)
    zt = min(ms["z1"], rows[-1][1] + 150)
    slot = f"led_{genes['accent']}"
    skin_led = genes.get("skin") == "led" and g == "body"
    if feat == "led" or skin_led:
        h = PT.q(zt - zb)
        n = 0
        if h >= 2000:
            for k, s in enumerate(lines_):
                if skin_led and feat != "led" and k % 2:
                    continue
                if _free(mounts, s - 60, s + 60, zb, zb + h):
                    P.on(fa, "led", {"dir": "v", "L": h, "t": LED_T, "slot": slot}, s, zb)
                    n += 1
        if n:
            used.add("led")
            sb.used["accent"] = True
            if skin_led and feat != "led":
                sb.used["skin"] = True
    if feat == "diag":
        k = 0
        for lo, hi, kind, f, full, zf in rows:
            if kind != "win" or hi - lo < 900:
                continue
            for jb, (b0, b1) in enumerate(cuts):
                if b1 - b0 < 900 or not _free(mounts, b0, b1, lo, hi):
                    continue
                dx, dz = PT.q(b1 - b0 - 120), PT.q(hi - lo - 60)
                if (f + jb) % 2:
                    P.on(fa, "member", {"dx": dx, "dz": dz, "w": 90, "y0": -90, "y1": 0,
                                        "slot": "mullion"}, b0 + 60, lo + 30)
                else:
                    P.on(fa, "member", {"dx": -dx, "dz": dz, "w": 90, "y0": -90, "y1": 0,
                                        "slot": "mullion"}, b1 - 60, lo + 30)
                k += 1
        if k:
            used.add("diag")
    if feat == "media":
        _media(sb, fa, ms, g, cuts, rows, mounts)


def _media(sb, fa, ms: dict, g: str, cuts, rows, mounts) -> None:
    """A media facade's screen: on the mass's widest street-facing facade, the bays clear of
    mounts over a block of floors (a third to two thirds of its rows, from 6 m up)."""
    if fa.rec is None or fa.rec.get("class") not in ("front", "street", "plaza", "park",
                                                     "open", "canal"):
        return
    if getattr(sb, "media_on", None) is not None and sb.media_on != (ms["k"], fa.j):
        return
    win = [r for r in rows if r[2] == "win" and r[0] >= max(6000, sb._low(fa, fa.L // 2))]
    if len(win) < 3:
        return
    s0, s1 = cuts[0][0], cuts[-1][1]
    if s1 - s0 < MEDIA_MIN_W:
        return
    n = len(win)
    k0 = n // 6
    k1 = max(k0 + 2, n * 2 // 3)
    z0, z1 = win[k0][0] - 200, win[min(k1, n - 1)][1] + 200
    if not _free(mounts, s0 - 200, s1 + 200, z0 - 200, z1 + 200):
        return
    w, h = PT.q(s1 - s0 - 300), PT.q(z1 - z0)
    x, y, _ = fa.P((s0 + s1) // 2, z0)
    if sb.clear.hits(x - w // 2 - 500, y - w // 2 - 500, x + w // 2 + 500, y + w // 2 + 500,
                     z0, z1):
        return
    slot = sorted(SY.MEDIA)[int(_u(sb.bid, "media") * len(SY.MEDIA)) % len(SY.MEDIA)]
    sb.parts.on(fa, "media", {"w": w, "h": h, "slot": slot}, (s0 + s1) // 2, z0)
    sb.used["parts"].setdefault(g, set()).add("media")
    sb.media_on = (ms["k"], fa.j)
    sb.stats["media_screens"] = sb.stats.get("media_screens", 0) + 1


# ---------------------------------------------------------------------------
# Crown and edge lights, logos
# ---------------------------------------------------------------------------

def _mounts_of(sb, fa) -> list[tuple]:
    if fa.j is None:
        return []
    so = fa.soff
    return [(m0 - so, m1 - so, z0, z1) for m0, m1, z0, z1 in sb.mounts.get(fa.j, [])]


def _runs(mounts, s: int, half: int, z0: int, z1: int, gap: int = 200) -> list[tuple]:
    """The stretches of z0..z1 at s clear of every mount (with `gap`)."""
    cuts = sorted((max(mz0 - gap, z0), min(mz1 + gap, z1)) for m0, m1, mz0, mz1 in mounts
                  if s - half < m1 and s + half > m0 and mz0 - gap < z1 and mz1 + gap > z0)
    out, z = [], z0
    for a, b in cuts:
        if a > z:
            out.append((z, a))
        z = max(z, b)
    if z < z1:
        out.append((z, z1))
    return [(a, b) for a, b in out if b - a >= 2000]


def lights(sb) -> None:
    """Crown and edge lights (towers: `crown_light` edges, band, both) and the logo, on the
    facades the shell built; `used` notes what was placed."""
    genes = sb.gm["genes"]
    cl = genes.get("crown_light", "none")
    logo = genes.get("logo", "none")
    if cl == "none" and logo == "none":
        return
    slot = f"led_{genes['accent']}"
    P = sb.parts
    top = max((ms["z1"] for _, ms in (sb.all_facades + sb.simple_facades)), default=0)
    n = 0
    if cl in ("edges", "both"):
        for fa, ms in (sb.all_facades + sb.simple_facades):
            if SY.role_group(ms["role"]) not in ("body", "top"):
                continue
            d_in = getattr(fa, "d_in", None)
            if d_in is None or not _corner(d_in, (fa.ux, fa.uy)):
                continue
            z0 = max(ms["z0"], ms.get("band") or 0, 3000)
            for a, b in _runs(_mounts_of(sb, fa), 0, 400, z0, ms["z1"] - 100):
                P.on(fa, "led", {"dir": "v", "L": PT.q(b - a), "t": LED_T, "slot": slot},
                     0, a)
                n += 1
    if cl in ("band", "both"):
        for fa, ms in (sb.all_facades + sb.simple_facades):
            if ms["z1"] < top - 50 or fa.L < 3000:
                continue
            z = ms["z1"] - 450
            L = PT.q(fa.L - 600)
            if z < 3000 or not _free(_mounts_of(sb, fa), 0, fa.L, z - 300, z + 300):
                continue
            P.on(fa, "led", {"dir": "h", "L": L, "t": LED_T, "slot": slot}, fa.L // 2, z)
            n += 1
    if n:
        sb.used["crown_light"] = True
        sb.used["accent"] = True
        sb.stats["crown_lights"] = sb.stats.get("crown_lights", 0) + n
    if logo != "none":
        _logo(sb, slot, top)


def _corner(d_in, d_out) -> bool:
    """A convex corner of the ring turning more than 20 degrees (`shell._convex`: the solid
    lies left of every facade)."""
    cos = d_in[0] * d_out[0] + d_in[1] * d_out[1]
    cross = d_in[0] * d_out[1] - d_in[1] * d_out[0]
    return cos < 0.9397 and cross > 0


def _logo(sb, slot: str, top: int) -> None:
    """The logo on the widest front or street facade of the topmost masses, under its
    top: free of mounts and corridors, 6 m up at least."""
    best = None
    for fa, ms in (sb.all_facades + sb.simple_facades):
        if ms["z1"] < top - 50 or fa.rec is None or fa.L < 6000:
            continue
        if fa.rec.get("class") not in ("front", "street", "plaza", "park", "open", "canal",
                                       "upper"):
            continue
        k = (fa.L, fa.j or 0)
        if best is None or k > best[0]:
            best = (k, fa, ms)
    if best is None:
        return
    _, fa, ms = best
    w = PT.q(min(LOGO_MAX, fa.L * 35 // 100))
    h = PT.q(w * 55 // 100)
    z = ms["z1"] - h - 1500
    if z < max(6000, ms["z0"] + 1000):
        return
    s = fa.L // 2
    if not _free(_mounts_of(sb, fa), s - w // 2 - 200, s + w // 2 + 200, z - 200, z + h + 200):
        return
    x, y, _ = fa.P(s, z)
    if sb.clear.hits(x - w, y - w, x + w, y + w, z - 500, z + h + 500):
        return
    style = ("ring", "bars", "chevron")[int(_u(sb.bid, "logo.style") * 3) % 3]
    sb.parts.on(fa, "logo", {"w": w, "h": h, "slot": slot, "style": style}, s, z)
    sb.used["logo"] = True
    sb.used["accent"] = True
    sb.stats["logos"] = sb.stats.get("logos", 0) + 1
