"""Megasite elements (citygen's `sites.py`): container stacks as instances of generated
containers, gantry cranes, fuel tanks, launch pads and towers, berths, rail tracks, walls,
gates, truck gates, aprons, plazas, lawns, pitches, ponds and fountains; anything else as
its masses and footprint.

Containers (40 ft, six liveries) are parts in `streets/parts.glb`, placed by the stack's
instance transforms (scope 5.3: "container stacks (instanced)"), as AG0 found instances
must come from the manifest, not glTF instancing.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from .. import canon as C
from .ctx import Ctx, bbox_center, dump
from .kit import Mesh, ccw
from .path import Path, dist, unit
from .pieces import Out, Piece, maker, rnd
from .structures import box_prof

CONTAINER = (12.19, 2.44, 2.59)
LIVERIES = 6
FLAT_SLOT = {"apron": "concrete", "plaza": "paving.granite", "courtyard": "paving.cobble",
             "drop_off": "concrete", "bus_bay": "concrete", "platform": "concrete.deck",
             "metro_entrance": "paving.granite_dark", "lawn": "lawn", "pitch": "pitch",
             "pond": "water.pond", "fountain": "water.pond"}


def gather_site(cx: Ctx, e) -> Piece:
    pts = []
    for ms in e.masses:
        pts += list(ms.footprint.exterior)
    if e.footprint is not None:
        pts += list(e.footprint.exterior)
    pts += [(p[0], p[1]) for p in e.line]
    if not pts:
        pts = [(0.0, 0.0)]
    c = bbox_center(pts)
    did = None
    ms = cx.megasite.get(e.megasite_id) if e.megasite_id else None
    if ms is not None:
        did = ms.district_id
    inputs = {"el": dump(e), "ground_c": cx.ground.samples([c]),
              "site": ms.kind if ms is not None else None, "style": cx.style(did),
              "origin": list(c)}
    if e.line:
        inputs["ground"] = cx.ground.samples(e.line)
    return Piece(e.id, f"street.site.{e.kind}", "site", cx.tile_for(e.id, pts),
                 cx.keys.get(e.id, []), inputs)


def _obb(ring):
    """(center, unit along the longest edge, length along, width across)."""
    r = ccw(ring)
    best = max(range(len(r)), key=lambda i: (dist(r[i], r[(i + 1) % len(r)]), -i))
    a, b = r[best], r[(best + 1) % len(r)]
    ux, uy = unit(b[0] - a[0], b[1] - a[1])
    us = [p[0] * ux + p[1] * uy for p in r]
    vs = [-p[0] * uy + p[1] * ux for p in r]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    uc, vc = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    cxy = (uc * ux - vc * uy, uc * uy + vc * ux)
    return cxy, (ux, uy), u1 - u0, v1 - v0


@maker("site", 1)
def make_site(inp: dict) -> Out:
    e = inp["el"]
    kind = e["kind"]
    g = inp["ground_c"][0] if inp.get("ground_c") else 0.0
    mesh = Mesh(inp["origin"])
    out = Out(mesh=mesh)
    fp = e.get("footprint")
    masses = e.get("masses", [])
    z0 = e.get("z_m", 0.0) + g
    if kind == "container_stack" and masses:
        ring = masses[0]["footprint"]["exterior"]
        mesh.poly("concrete", ccw(ring), z=z0 + 0.03)
        out.parts = _containers(e, ring, masses[0]["z1_m"], z0 + 0.03, inp["origin"])
        return out
    if kind == "gantry_crane" and masses:
        _crane(mesh, masses, z0)
        return out
    if kind == "fuel_tank" and masses:
        for ms in masses:
            (cx_, cy_), _, a, b = _obb(ms["footprint"]["exterior"])
            r = min(a, b) / 2.0
            z1 = ms["z1_m"] + g
            mesh.cylinder("tank", cx_, cy_, r, z0 + ms["z0_m"], z1, n=24, top=False)
            mesh.cylinder("tank", cx_, cy_, r, z1, z1 + r * 0.25, n=24, r1=r * 0.25)
            mesh.cylinder("steel", cx_, cy_, r + 0.6, z1 - 0.15, z1, n=24, top=False)
        return out
    if kind == "launch_pad" and masses:
        ms = masses[0]
        (cx_, cy_), _, a, b = _obb(ms["footprint"]["exterior"])
        r = e.get("attrs", {}).get("radius_m", min(a, b) / 2.0)
        z1 = ms["z1_m"] + g
        mesh.cylinder("pad", cx_, cy_, r, z0, z1, n=48)
        ring_o = [(cx_ + (r - 2.0) * M.cos(2 * M.PI * k / 48),
                   cy_ + (r - 2.0) * M.sin(2 * M.PI * k / 48)) for k in range(48)]
        ring_i = [(cx_ + (r - 3.0) * M.cos(2 * M.PI * k / 48),
                   cy_ + (r - 3.0) * M.sin(2 * M.PI * k / 48)) for k in range(48)][::-1]
        mesh.poly("marking.yellow", ring_o, [ring_i], z=z1 + 0.01)
        mesh.box("concrete.dark", cx_, cy_, z1 + 0.005, r * 0.9, 6.0, 0.01)
        return out
    if kind == "launch_tower" and masses:
        _lattice(mesh, masses[0], g)
        return out
    if kind == "berth" and fp is not None:
        mesh.poly("concrete", ccw(fp["exterior"]), z=z0 + 0.04)
        line = e.get("line") or []
        if len(line) >= 2:
            try:
                P = Path(line)
            except ValueError:
                return out
            s = 6.0
            while s < P.L:
                x, y, nx, ny, _ = P.frame(s)
                mesh.cylinder("steel.painted", x + nx * 1.0, y + ny * 1.0, 0.25, z0 + 0.04,
                              z0 + 0.7, n=10)
                mesh.box("rubber", x, y, z0 - 1.6, 2.0, 0.5, 1.5, M.degrees(M.atan2(ny, nx)) + 90.0)
                s += 12.0
        return out
    if kind == "rail_track" and len(e.get("line") or []) >= 2:
        _track(mesh, e, inp)
        return out
    if kind == "truck_gate" and fp is not None:
        (cx_, cy_), (ux, uy), a, b = _obb(fp["exterior"])
        mesh.poly("concrete", ccw(fp["exterior"]), z=z0 + 0.04)
        lanes = max(int(e.get("attrs", {}).get("lanes", 2)), 1)
        for k in range(lanes + 1):
            v = -b / 2.0 + b * k / lanes
            px, py = cx_ - uy * v, cy_ + ux * v
            mesh.obox("concrete.barrier", px, py, z0, 3.0, 1.2, 2.6, ux, uy)
            if k < lanes:
                q = (px - uy * 0.6, py + ux * 0.6, z0 + 1.0)
                r_ = (px - uy * (b / lanes - 0.6), py + ux * (b / lanes - 0.6), z0 + 1.0)
                mesh.beam("steel.red", q, r_, 0.1, 0.1)
        return out
    if kind in FLAT_SLOT and fp is not None and not masses:
        slot = FLAT_SLOT[kind]
        ring = ccw(fp["exterior"])
        holes = [ccw(h)[::-1] for h in fp.get("holes", [])]
        if kind in ("pond", "fountain"):
            mesh.prism("stone.coping", ring, z0, z0 + 0.45, top=False)
            mesh.poly(slot, ring, holes, z=z0 + 0.3)
        else:
            mesh.poly(slot, ring, holes, z=z0 + 0.05)
        return out
    # masses and footprint as they are
    slot = {"wall": "stone.quay", "gate": "steel.red"}.get(kind, "pad")
    for ms in masses:
        if ms["z1_m"] <= ms["z0_m"]:
            continue
        r = ccw(ms["footprint"]["exterior"])
        if ms.get("shape") == "cylinder":
            (cx_, cy_), _, a, b = _obb(r)
            mesh.cylinder(slot, cx_, cy_, min(a, b) / 2.0, ms["z0_m"] + g, ms["z1_m"] + g, n=20)
        else:
            mesh.prism(slot, r, ms["z0_m"] + g, ms["z1_m"] + g)
    if fp is not None and not masses:
        mesh.poly(FLAT_SLOT.get(kind, "concrete"), ccw(fp["exterior"]), z=z0 + 0.06)
    if not mesh.triangles and len(e.get("line") or []) >= 2:
        try:
            P = Path(e["line"])
            for k in range(len(P.p) - 1):
                a, b = P.p[k], P.p[k + 1]
                mesh.obox("concrete", (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, z0,
                          dist(a, b), 3.0, 0.1, *unit(b[0] - a[0], b[1] - a[1]))
        except ValueError:
            pass
    if not mesh.triangles:
        return Out(empty="nothing to draw")
    return out


def _containers(e: dict, ring, height: float, zb: float, origin) -> list[dict]:
    (cx_, cy_), (ux, uy), a, b = _obb(ring)
    cl, cw, ch = CONTAINER
    na = max(1, int(a / (cl + 0.2)))
    nb = max(1, int(b / (cw + 0.1)))
    tiers = max(1, int(round(height / ch)))
    yaw = round(M.degrees(M.atan2(uy, ux)), 2)
    by: dict[int, list] = {}
    for t in range(tiers):
        for i in range(na):
            for j in range(nb):
                # the top tier is not always full
                if t == tiers - 1 and tiers > 1 and rnd(e["id"], "top", i, j) < 0.25:
                    continue
                u = -a / 2.0 + (a / na) * (i + 0.5)
                v = -b / 2.0 + (b / nb) * (j + 0.5)
                x = cx_ + ux * u - uy * v - origin[0]
                y = cy_ + uy * u + ux * v - origin[1]
                c = int(rnd(e["id"], "livery", t, i, j) * LIVERIES) % LIVERIES
                by.setdefault(c, []).append([C.m(x), C.m(y), C.m(zb + ch * t), yaw])
    return [{"kind": f"part.container.c{c}", "xforms": by[c]} for c in sorted(by)]


def container_part(livery: int) -> Mesh:
    """A 40 ft container, its pivot at the middle of its base: walls with corrugation ribs,
    door end frames, roof."""
    m = Mesh((0.0, 0.0, 0.0))
    cl, cw, ch = CONTAINER
    slot = f"container.c{livery}"
    m.obox(slot, 0.0, 0.0, 0.0, cl, cw, ch, 1.0, 0.0, bottom=True)
    x = -cl / 2.0 + 0.3
    while x < cl / 2.0 - 0.3:
        for side in (-1.0, 1.0):
            m.obox(slot, x, side * (cw / 2.0 + 0.02), 0.15, 0.12, 0.04, ch - 0.3, 1.0, 0.0)
        x += 0.6
    for ex in (-1.0, 1.0):
        m.obox("steel", ex * (cl / 2.0 - 0.08), 0.0, 0.0, 0.18, cw + 0.04, 0.15, 1.0, 0.0)
        m.obox("steel", ex * (cl / 2.0 - 0.08), 0.0, ch - 0.15, 0.18, cw + 0.04, 0.15, 1.0, 0.0)
    return m


def _crane(mesh: Mesh, masses, z0: float):
    legs = [m for m in masses if m.get("role") == "leg"]
    others = [m for m in masses if m.get("role") != "leg"]
    tops = []
    for m in legs:
        r = ccw(m["footprint"]["exterior"])
        mesh.prism("crane", r, z0 + m["z0_m"], z0 + m["z1_m"])
        c = (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))
        tops.append((c, z0 + m["z1_m"]))
    for i in range(len(tops)):
        for k in range(i + 1, len(tops)):
            (a, za), (b, zb) = tops[i], tops[k]
            d = dist(a, b)
            if d < 25.0:
                mesh.beam("crane", (a[0], a[1], za - 1.0), (b[0], b[1], zb - 1.0), 1.2, 1.4)
                mesh.beam("crane", (a[0], a[1], z0 + 1.0), (b[0], b[1], z0 + 1.0), 1.0, 1.2)
                mesh.beam("crane", (a[0], a[1], z0 + 1.0), (b[0], b[1], zb - 1.0), 0.6, 0.6)
    for m in others:
        r = ccw(m["footprint"]["exterior"])
        mesh.prism("crane", r, z0 + m["z0_m"] + 2.5, z0 + m["z1_m"], bottom=True)
        (cx_, cy_), (ux, uy), a, b = _obb(r)
        mesh.obox("steel.painted", cx_ - ux * a * 0.3, cy_ - uy * a * 0.3, z0 + m["z1_m"],
                  8.0, max(b - 1.0, 2.0), 4.0, ux, uy)


def _lattice(mesh: Mesh, ms: dict, g: float):
    (cx_, cy_), (ux, uy), a, b = _obb(ms["footprint"]["exterior"])
    vx, vy = -uy, ux
    z0, z1 = ms["z0_m"] + g, ms["z1_m"] + g
    ha, hb = a / 2.0 - 0.3, b / 2.0 - 0.3
    corners = [(cx_ + ux * sa * ha + vx * sb * hb, cy_ + uy * sa * ha + vy * sb * hb)
               for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for c in corners:
        mesh.box("steel.red", c[0], c[1], z0, 0.6, 0.6, z1 - z0)
    n = max(1, int((z1 - z0) / 5.0))
    for k in range(n + 1):
        z = z0 + (z1 - z0) * k / n
        for i in range(4):
            p, q = corners[i], corners[(i + 1) % 4]
            mesh.beam("steel.red", (p[0], p[1], z), (q[0], q[1], z), 0.3, 0.3)
            if k < n:
                zn = z0 + (z1 - z0) * (k + 1) / n
                if k % 2 == 0:
                    mesh.beam("steel.red", (p[0], p[1], z), (q[0], q[1], zn), 0.2, 0.2)
                else:
                    mesh.beam("steel.red", (q[0], q[1], z), (p[0], p[1], zn), 0.2, 0.2)
    mesh.obox("steel.painted", cx_, cy_, z1, a + 1.0, b + 1.0, 0.4, ux, uy)
    arm0 = (cx_ - ux * ha, cy_ - uy * ha, z1 - 8.0)
    arm1 = (cx_ - ux * (ha + 14.0), cy_ - uy * (ha + 14.0), z1 - 8.0)
    mesh.beam("steel.painted", arm0, arm1, 1.5, 1.2)


def _track(mesh: Mesh, e: dict, inp: dict):
    from .structures import Line3
    line = [(p[0], p[1], e.get("z_m", 0.0)) for p in e["line"]]
    try:
        ln = Line3(line, inp.get("ground"))
    except ValueError:
        return
    fr = ln.frames(0.0, ln.L, 8.0)
    mesh.sweep("ballast", fr, [(-1.6, 0.0), (-1.2, 0.35), (1.2, 0.35), (1.6, 0.0)])
    gauge = e.get("attrs", {}).get("gauge_m", 1.435) / 2.0
    for gsgn in (-1.0, 1.0):
        c = gsgn * gauge
        mesh.sweep("rail", fr, box_prof(c - 0.035, c + 0.035, 0.5, 0.65))
    s = 0.4
    while s < ln.L:
        x, y, _, _, _ = ln.path.frame(s)
        dx, dy = ln.path.tangent(s)
        mesh.obox("sleeper", x, y, ln.z(s) + 0.35, 0.25, 2.6, 0.15, dx, dy)
        s += 1.3


__all__ = ["gather_site", "container_part", "math"]
