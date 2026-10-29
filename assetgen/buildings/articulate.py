"""Massing articulation (scope pipeline stage 3, AG2): what a building's masses become
before the facade grammar runs, always inside the envelope (scope 9).

- **Corner cuts**: a convex corner of 60 to 120 degrees between two free facades (no party,
  hidden or blind stretch, nothing mounted within the cut and 1.5 m of it, no roof item
  near it) is chamfered or rounded (`cut`, `cut_m`); every mass with a vertex there must
  qualify, and all of them are cut alike, so stacked masses keep their corners in line.
- **Setback ledges**: a tower's top body mass (14 floors or more) steps in by `setback_m`
  at `setback_at` of its height on the edges with nothing above that line (a parapet runs
  round the ledge, as round any open roof edge).
- **Crowns**: `stepped` (the top floors in tiers stepping in), `halo` (the top floor a
  screen of fins inside the mass round an open roof with a penthouse), `mast` and `spire`
  (on the highest roof, within the roof rule of the envelope check); the lantern and parapet
  crowns are the shell's (AG1).
- **Arcades**: a building's ground floor set back by `arcade_m` behind columns on its
  front, street and plaza edges (none with a unit, sign, mounted prop, plant or skybridge
  at that height), the floors above cantilevered over it: the cantilever stays inside the
  lot because the floor under it moves in.

Masses are the shell builder's dicts; a split keeps the brief's mass index `k` (edge
lookups) and counts floors from `f0`. Rings are counterclockwise exteriors (articulated
masses have no courts); `eidx` gives each ring edge's brief edge index, `deriv` marks the
edges a cut or offset made (they take the class of the edge they came from, but nothing
mounted on it).
"""

from __future__ import annotations

import math

from citygen import dmath as M

from ..triangulate import area2, orient
from . import rings as RG
from . import systems as SY

NO_CUT = ("party", "hidden", "blind")
MARK_PAD = 1500


def _u(bid: str, purpose: str) -> float:
    from . import genome as GN
    return GN.u(bid, purpose, "ag2.articulate")


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.sqrt(dx * dx + dy * dy) or 1.0
    return dx / L, dy / L, L


def _edge_geom(br: dict, j: int):
    e = br["edges"][j]
    a = (int(round(e["a"][0] * 1000)), int(round(e["a"][1] * 1000)))
    b = (int(round(e["b"][0] * 1000)), int(round(e["b"][1] * 1000)))
    ux, uy, L = _unit(a, b)
    return a, ux, uy, L


def marks(br: dict, units_by_edge: dict) -> dict[int, list[tuple]]:
    """Per brief edge: (s, z_lo, z_hi) in mm of everything at a spot of it (units,
    entrances, sign slots, mounted props, plants, skybridge ends)."""
    out: dict[int, list] = {}

    def add(at, zlo, zhi, kind, half=0):
        if at is None:
            return
        s = int(round(at["s"] * 1000))
        out.setdefault(at["edge"], []).append((s - half, s + half, int(zlo), int(zhi), kind))
    for e in sorted(units_by_edge):
        for un in units_by_edge[e]:
            w = int(round(un["width_m"] * 500))
            add(un["at"], 0, 5000 if un.get("awning_m", 0) else 4000, "unit", w)
    for en in br["entrances"]:
        add(en.get("at"), 0, 3500, "entrance")
    for s in br["sign_slots"]:
        if s["mount"] == "roof":
            continue
        z = s["position"][2] * 1000
        h = s["height_m"] * 500
        add(s["at"], z - h, z + h, "sign", int(s["width_m"] * 500))
    for p in br["props"]:
        if p.get("at") is not None:
            z = p["position"][2] * 1000
            add(p["at"], z - 1000, z + 1000, "prop")
    for p in br["plants"]:
        z = p["position"][2] * 1000
        add(p["at"], z - 500, z + max(p["height_m"], 1.0) * 1000, "plant")
    for s in br["skybridges"]:
        h = max(s["levels"], 1) * s["level_height_m"] * 1000
        add(s["at"], s["z_m"] * 1000 - 500, s["z_m"] * 1000 + h + 500, "skybridge",
            int(s["width_m"] * 500) + 300)
    return out


def _bad_class(br: dict, j: int, za: int, zb: int, bad=NO_CUT) -> bool:
    for reg in br["edges"][j]["regions"]:
        if reg["z"][0] * 1000 < zb and reg["z"][1] * 1000 > za and reg["class"] in bad:
            return True
    return False


def _class_at(br: dict, j: int, z: int) -> dict | None:
    for reg in br["edges"][j]["regions"]:
        if reg["z"][0] * 1000 <= z <= reg["z"][1] * 1000:
            return reg
    return None


# ---------------------------------------------------------------------------
# Corner cuts
# ---------------------------------------------------------------------------

def _corner_ok(sb, ms, ring, eidx, i, c) -> bool:
    br = sb.br
    n = len(ring)
    a, v, b = ring[i - 1], ring[i], ring[(i + 1) % n]
    ax, ay, La = _unit(a, v)
    bx, by, Lb = _unit(v, b)
    if orient(a, v, b) <= 0:
        return False
    dot = ax * bx + ay * by
    if dot < -0.5 or dot > 0.5:
        return False
    if La < c + 3000 or Lb < c + 3000:
        return False
    k = ms["k"]
    for e_in, end in ((eidx[i - 1], True), (eidx[i], False)):
        j = sb.edge_of.get((k, ms["rid"][0], e_in))
        if j is None or _bad_class(br, j, ms["z0"], ms["z1"]):
            return False
        a0, ux, uy, L = _edge_geom(br, j)
        sv = (v[0] - a0[0]) * ux + (v[1] - a0[1]) * uy
        lo, hi = (sv - c - MARK_PAD, sv + 500) if end else (sv - 500, sv + c + MARK_PAD)
        for m0, m1, z0, z1, _ in sb.marks.get(j, []):
            if m0 < hi and m1 > lo and z0 < ms["z1"] and z1 > ms["z0"] - 100:
                return False
    for it in br["roof_items"]:
        x, y = it["position"][0] * 1000, it["position"][1] * 1000
        if (x - v[0]) ** 2 + (y - v[1]) ** 2 < (c + 2000) ** 2:
            return False
    return True


def _arc(p1, p2, d_in, d_out, c):
    """Points from p1 to p2 (both kept) on the fillet tangent to both edges, c from the
    corner along each."""
    cr = d_in[0] * d_out[1] - d_in[1] * d_out[0]
    dt = d_in[0] * d_out[0] + d_in[1] * d_out[1]
    th = float(M.atan2(cr, dt))
    r = c / float(M.tan(th / 2.0))
    cx, cy = p1[0] - d_in[1] * r, p1[1] + d_in[0] * r
    f1 = float(M.atan2(p1[1] - cy, p1[0] - cx))
    k = max(2, int(round(math.degrees(th) / 22.5)))
    pts = [p1]
    for j in range(1, k):
        t = f1 + th * j / k
        pts.append((int(round(cx + r * float(M.cos(t)))), int(round(cy + r * float(M.sin(t))))))
    pts.append(p2)
    return pts


def corners(sb) -> None:
    genes, cont = sb.gm["genes"], sb.gm["cont"]
    kind = genes.get("cut", "none")
    if kind == "none" or sb.br["portals"] or sb.br["building"]["landmark"]:
        return
    c = int(round(cont["cut_m"] * 1000))
    masses = [ms for ms in sb.masses if ms["shape"] == "prism" and len(ms["rings"]) == 1 and
              SY.role_group(ms["role"]) != "structure" and len(ms["rings"][0]) >= 4]
    if not masses:
        return
    at: dict[tuple, list] = {}
    for mi, ms in enumerate(masses):
        for i, v in enumerate(ms["rings"][0]):
            at.setdefault(v, []).append((mi, i))
    cut: dict[int, set] = {}
    for v in sorted(at):
        occ = at[v]
        if not all(_corner_ok(sb, masses[mi], masses[mi]["rings"][0], masses[mi]["eidx"][0],
                              i, c) for mi, i in occ):
            continue
        # no other mass touches the corner (an edge through it, or a vertex near it)
        mine = {mi for mi, _ in occ}
        clash = False
        for mj, o in enumerate(sb.masses):
            if any(o is masses[mi] for mi in mine):
                continue
            for ring in o["rings"]:
                for p in ring:
                    if (p[0] - v[0]) ** 2 + (p[1] - v[1]) ** 2 < (2 * c) ** 2:
                        clash = True
                if not clash and RG.inside(v, ring) == 0:
                    clash = True
            if clash:
                break
        if clash:
            continue
        for mi, i in occ:
            cut.setdefault(mi, set()).add(i)
    done = False
    for mi, idx in cut.items():
        ms = masses[mi]
        ring, eidx, der = ms["rings"][0], ms["eidx"][0], ms["deriv"][0]
        n = len(ring)
        pts, ei, dv = [], [], []
        for i in range(n):
            if i not in idx:
                pts.append(ring[i])
                ei.append(eidx[i])
                dv.append(der[i])
                continue
            a, v, b = ring[i - 1], ring[i], ring[(i + 1) % n]
            ax, ay, _ = _unit(a, v)
            bx, by, _ = _unit(v, b)
            p1 = (int(round(v[0] - ax * c)), int(round(v[1] - ay * c)))
            p2 = (int(round(v[0] + bx * c)), int(round(v[1] + by * c)))
            seq = [p1, p2] if kind == "chamfer" else _arc(p1, p2, (ax, ay), (bx, by), c)
            for j, p in enumerate(seq[:-1]):
                pts.append(p)
                first = j < (len(seq) - 1) / 2.0
                ei.append(eidx[i - 1] if first else eidx[i])
                dv.append(True)
            pts.append(p2)
            ei.append(eidx[i])
            dv.append(der[i])
        clean_pts, clean_ei, clean_dv = [], [], []
        for p, e, d in zip(pts, ei, dv):
            if clean_pts and clean_pts[-1] == p:
                continue
            clean_pts.append(p)
            clean_ei.append(e)
            clean_dv.append(d)
        if len(clean_pts) >= 3 and clean_pts[0] == clean_pts[-1]:
            clean_pts.pop()
            clean_ei.pop()
            clean_dv.pop()
        if not RG.is_simple(clean_pts) or area2(clean_pts) <= 0:
            continue
        ms["rings"][0], ms["eidx"][0], ms["deriv"][0] = clean_pts, clean_ei, clean_dv
        done = True
    if done:
        sb.used["articulation"].append("cut")


# ---------------------------------------------------------------------------
# Offsets and splits
# ---------------------------------------------------------------------------

def offset(ring, eidx, deriv, d: list[int]):
    """The ring with edge i moved by d[i] (mm, negative inward): (points, eidx, deriv) with
    a beveled corner's new edge marked derived; None where it folds."""
    n = len(ring)
    us = [RG._dir(ring[i], ring[(i + 1) % n]) for i in range(n)]
    ends, starts = [None] * n, [None] * n
    for i in range(n):
        c = RG._corner(ring[i], us[i - 1], d[i - 1], us[i], d[i])
        if c is None:
            return None
        ends[i - 1], starts[i] = RG._ipt(c[0]), RG._ipt(c[1])
    pts, ei, dv = [], [], []
    for i in range(n):
        if ends[i - 1] != starts[i]:
            pts.append(ends[i - 1])
            ei.append(eidx[i - 1])
            dv.append(True)
        pts.append(starts[i])
        ei.append(eidx[i])
        dv.append(deriv[i])
    for i in range(n):
        if not RG._same_dir(ring[i], ring[(i + 1) % n], starts[i], ends[i]):
            return None
    out, oe, od = [], [], []
    for p, e, dd in zip(pts, ei, dv):
        if out and out[-1] == p:
            out[-1] = p
            oe[-1], od[-1] = e, dd
            continue
        out.append(p)
        oe.append(e)
        od.append(dd)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
        oe.pop()
        od.pop()
    if len(out) < 3 or not RG.is_simple(out) or area2(out) <= 0:
        return None
    return out, oe, od


def _thick(ring) -> int:
    from .shell import _thickness
    return _thickness(ring)


def _free_above(sb, ms, i: int, z: int) -> bool:
    """Whether ring edge i of a mass may step in above z: a real edge with no party, hidden
    or blind stretch up there and nothing mounted on it from 0.5 m under z up."""
    j = sb.edge_of.get((ms["k"], ms["rid"][0], ms["eidx"][0][i]))
    if j is None:
        return False
    if _bad_class(sb.br, j, z, ms["z1"] + 1):
        return False
    for m0, m1, z0, z1, _ in sb.marks.get(j, []):
        if z1 > z - 500:
            return False
    return True


def _roof_items_in(sb, ms, ring) -> bool:
    for it in sb.br["roof_items"]:
        if it.get("mass") is not None and it["mass"] != ms["k"]:
            continue
        x, y = int(round(it["position"][0] * 1000)), int(round(it["position"][1] * 1000))
        h = int(max(it["size"][0], it["size"][1]) * 600) + 300
        for p in ((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)):
            if RG.inside(p, ring) != 1:
                return False
    return True


def _split(ms, z: int, f: int, upper_rings=None) -> tuple[dict, dict]:
    lo = dict(ms, z1=z, floors=f)
    hi = dict(ms, z0=z, floors=ms["floors"] - f, f0=ms.get("f0", 0) + f)
    if upper_rings is not None:
        hi["rings"], hi["eidx"], hi["deriv"] = upper_rings
    for d in (lo, hi):
        d["rings"] = [list(r) for r in d["rings"]]
        d["eidx"] = [list(r) for r in d["eidx"]]
        d["deriv"] = [list(r) for r in d["deriv"]]
    return lo, hi


def _is_top(sb, ms) -> bool:
    from .shell import _centroid
    return not any(o is not ms and o["z0"] >= ms["z1"] - 50 and
                   RG.in_poly(_centroid(o["rings"][0]), [ms["rings"][0]]) >= 0
                   for o in sb.masses)


def _step_in(sb, ms, z: int, d: int):
    ring = ms["rings"][0]
    n = len(ring)
    ok = [_free_above(sb, ms, i, z) for i in range(n)]
    if sum(ok) < 2:
        return None
    res = offset(ring, ms["eidx"][0], ms["deriv"][0], [-d if o else 0 for o in ok])
    if res is None:
        return None
    pts = res[0]
    if _thick(pts) < 6000 or 3 * area2(pts) < area2(ring) or not _roof_items_in(sb, ms, pts):
        return None
    return [pts], [res[1]], [res[2]]


def splits(sb) -> None:
    genes, cont = sb.gm["genes"], sb.gm["cont"]
    br = sb.br
    b = br["building"]
    if b["landmark"] or br["portals"]:
        return
    crown = genes.get("crown", "flat")
    out = []
    for ms in sb.masses:
        g = SY.role_group(ms["role"])
        n = ms["floors"]
        if ms["shape"] != "prism" or len(ms["rings"]) != 1 or g != "body" or n < 1:
            out.append(ms)
            continue
        parts = [ms]
        top = _is_top(sb, ms)
        # an arcade under the first floor
        if genes.get("arcade") == "arcade" and ms["z0"] <= 50 and n >= 3 and \
                sb.plinth == 0:
            res = _arcade(sb, ms)
            if res is not None:
                parts = list(res)
        # setback ledge, then the crown tiers, on the top part
        hi = parts[-1]
        if top and genes.get("setback") == "ledge" and n >= 14 and \
                ms["z1"] - ms["z0"] >= 45000:
            nn = hi["floors"]
            f = min(max(int(round(nn * cont["setback_at"])), 4), nn - 3)
            z = hi["z0"] + (hi["z1"] - hi["z0"]) * f // nn
            up = _step_in(sb, hi, z, int(round(cont["setback_m"] * 1000)))
            if up is not None:
                lo, h2 = _split(hi, z, f, up)
                parts[-1:] = [lo, h2]
                sb.used["articulation"].append("setback")
        hi = parts[-1]
        if top and crown == "stepped" and n >= 8 and hi["floors"] >= 4:
            tiers = 3 if n >= 15 else 2
            each = max(1, n // 14)
            step = 1500
            for t in range(tiers):
                hi = parts[-1]
                nn = hi["floors"]
                f = nn - each
                if f < 2:
                    break
                z = hi["z0"] + (hi["z1"] - hi["z0"]) * f // nn
                up = _step_in(sb, hi, z, step)
                if up is None:
                    break
                lo, h2 = _split(hi, z, f, up)
                parts[-1:] = [lo, h2]
                sb.used["crown"] = True
        elif top and crown == "halo" and n >= 10 and hi["floors"] >= 3:
            nn = hi["floors"]
            each = 2 if n >= 30 else 1
            f = nn - each
            z = hi["z0"] + (hi["z1"] - hi["z0"]) * f // nn
            lo, h2 = _split(hi, z, f)
            h2["screen"] = True
            parts[-1:] = [lo, h2]
            sb.used["crown"] = True
        out.extend(parts)
    sb.masses = out


def _arcade(sb, ms):
    br = sb.br
    n = ms["floors"]
    z1 = ms["z0"] + (ms["z1"] - ms["z0"]) // n
    if not 3500 <= z1 - ms["z0"] <= 7000:
        return None
    ring = ms["rings"][0]
    nr = len(ring)
    d = int(round(sb.gm["cont"]["arcade_m"] * 1000))
    ok = []
    for i in range(nr):
        good = False
        j = sb.edge_of.get((ms["k"], ms["rid"][0], ms["eidx"][0][i]))
        if j is not None and not ms["deriv"][0][i]:
            e = br["edges"][j]
            reg = _class_at(br, j, 1500)
            cls = reg["class"] if reg else e["class"]
            good = cls in ("front", "street", "plaza") and e["length_m"] >= 8.0 and \
                not sb.units_by_edge.get(j) and \
                not _bad_class(br, j, 0, z1 + 500, NO_CUT + ("alley",))
            if good:
                for m0, m1, za, zb, kind in sb.marks.get(j, []):
                    if za < z1 + 500 and kind != "entrance":
                        good = False
                        break
        ok.append(good)
    if not any(ok):
        return None
    res = offset(ring, ms["eidx"][0], ms["deriv"][0], [-d if o else 0 for o in ok])
    if res is None or _thick(res[0]) < 6000 or 2 * area2(res[0]) < area2(ring):
        return None
    lo, hi = _split(ms, z1, 1)
    lo["rings"], lo["eidx"], lo["deriv"] = [res[0]], [res[1]], [res[2]]
    lo["arcade"] = True
    # the columns, on the facade line of the floors above (placed by the shell)
    sb.arcades.append({"ring": list(ring), "ok": ok, "z1": z1 - ms["z0"], "z0": ms["z0"],
                       "d": d})
    sb.used["articulation"].append("arcade")
    return lo, hi


def articulate(sb) -> None:
    corners(sb)
    splits(sb)
