"""Transit structures (M5, M8) and the other structures of the model.

- **Guideways** (the model's deck structures of a line): elevated rail as a U trough with
  two slab tracks and their rails, monorail as a concrete beam with a running strip, maglev
  as a T guideway with its guide rails.
- **Sky tubes**: a glass tube (translucent, non-Nanite) with a LOD chain of 24, 12 and 6
  sides, and, Nanite, the floor inside and steel ribs every 10 m.
- **Columns and pylons** of a line: the model's footprint as the shaft and a cap across the
  guideway (a cradle under a sky tube).
- **Stations' structures** (stations themselves are buildings, the building line's):
  platforms, skywalks (glazed, roofed), canopies on posts, covered walkways, elevator cores,
  underground concourses.
- Anything else in `structures` falls back to its footprint as a prism or its line as a
  slab.
"""

from __future__ import annotations

from citygen import dmath as M

from .. import canon as C
from .ctx import Ctx, bbox_center, dump
from .kit import Mesh, ccw
from .path import Path, dist, unit
from .pieces import Out, Piece, maker
from .structures import Line3, box_prof

GUIDEWAY_W = {"elevated_rail": 9.0, "monorail": 2.5, "maglev": 7.0, "sky_tube": 7.0,
              "metro": 9.0}
TUBE_LODS = ((24, 6.0), (12, 12.0), (6, 24.0))
TUBE_SCREEN = (1.0, 0.25, 0.06)


def _line_dir(cx: Ctx, line_id: str | None, x: float, y: float):
    tl = cx.lines.get(line_id) if line_id else None
    if tl is None or len(tl.path) < 2:
        return None
    best = None
    for a, b in zip(tl.path, tl.path[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 == 0.0:
            continue
        f = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
        qx, qy = a[0] + f * dx, a[1] + f * dy
        d2 = (x - qx) ** 2 + (y - qy) ** 2
        if best is None or d2 < best[0]:
            best = (d2, dx, dy)
    ux, uy = unit(best[1], best[2])
    return [round(ux, 6), round(uy, 6)]


def gather_structure(cx: Ctx, st, maker_name: str) -> Piece:
    a = st.attrs or {}
    if st.footprint is not None:
        pts = st.footprint.exterior
    elif st.line:
        pts = [(p[0], p[1]) for p in st.line]
    else:
        pts = [(0.0, 0.0)]
    c = bbox_center(pts)
    inputs = {"st": dump(st), "origin": list(c),
              "ground_c": cx.ground.samples([c])}
    if st.line:
        inputs["ground"] = cx.ground.samples(st.line)
    if maker_name == "transit_column":
        inputs["dir"] = _line_dir(cx, a.get("line_id"), c[0], c[1])
    kind = f"street.transit.{st.kind}" if a.get("line_id") or a.get("station") \
        else f"street.structure.{st.kind}"
    return Piece(st.id, kind, maker_name, cx.tile_for(st.id, pts), cx.keys.get(st.id, []),
                 inputs)


def _g(inp: dict) -> float:
    return inp["ground_c"][0] if inp.get("ground_c") else 0.0


@maker("guideway", 1)
def make_guideway(inp: dict) -> Out:
    st = inp["st"]
    a = st.get("attrs", {})
    try:
        ln = Line3(st["line"], inp.get("ground"))
    except ValueError:
        return Out(empty="degenerate line")
    mode = a.get("mode", "elevated_rail")
    W = a.get("width_m", GUIDEWAY_W.get(mode, 6.0))
    dm = a.get("deck_m", max(st["z1_m"] - st["z0_m"], 0.8))
    mesh = Mesh(inp["origin"])
    fr = ln.frames(0.0, ln.L, 6.0)
    h = W / 2.0
    if mode == "monorail":
        mesh.sweep("concrete.column", fr, box_prof(-0.45, 0.45, -dm, 0.0))
        mesh.sweep("steel", fr, [(-0.4, 0.01), (0.4, 0.01)])
    elif mode == "maglev":
        mesh.sweep("concrete.column", fr, box_prof(-1.3, 1.3, -dm, -0.55))
        mesh.sweep("concrete.deck", fr, [(-h, -0.55), (-h, 0.0), (h, 0.0), (h, -0.55)],
                   closed=True)
        for c in (-h + 0.2, h - 0.2):
            mesh.sweep("steel", fr, box_prof(c - 0.18, c + 0.18, 0.0, 0.4))
    else:
        prof = [(h, 1.0), (h, -0.4), (h - 1.0, -dm), (-(h - 1.0), -dm), (-h, -0.4), (-h, 1.0),
                (-h + 0.3, 1.0), (-h + 0.3, 0.0), (h - 0.3, 0.0), (h - 0.3, 1.0)]
        mesh.sweep("concrete.deck", fr, prof, closed=True)
        tracks = (-h / 2.0 + 0.1, h / 2.0 - 0.1) if W >= 6.0 else (0.0,)
        for c in tracks:
            for g in (-0.7175, 0.7175):
                mesh.sweep("concrete", fr, box_prof(c + g - 0.25, c + g + 0.25, 0.0, 0.12))
                mesh.sweep("rail", fr, box_prof(c + g - 0.04, c + g + 0.04, 0.12, 0.29))
    return Out(mesh=mesh)


def _ring(R: float, zc: float, n: int):
    """A circle in the section plane, clockwise in (t, dz) for an outward surface."""
    return [(R * M.cos(-2.0 * M.PI * k / n), zc + R * M.sin(-2.0 * M.PI * k / n))
            for k in range(n)]


@maker("sky_tube", 1)
def make_sky_tube(inp: dict) -> Out:
    st = inp["st"]
    a = st.get("attrs", {})
    try:
        ln = Line3(st["line"], inp.get("ground"))
    except ValueError:
        return Out(empty="degenerate line")
    D = a.get("deck_m", 7.0)
    R = D / 2.0
    zc = -R                       # the line is the tube's top
    mesh = Mesh(inp["origin"])
    fr = ln.frames(0.0, ln.L, 6.0)
    mesh.sweep("concrete.deck", fr, box_prof(-2.2, 2.2, zc - R * 0.72 - 0.3,
                                             zc - R * 0.72), )
    s = 5.0
    while s < ln.L:
        x, y, nx, ny, _ = ln.path.frame(s)
        z = ln.z(s) + zc
        n = 12
        pts = [(x + nx * (R + 0.12) * M.cos(2 * M.PI * k / n),
                y + ny * (R + 0.12) * M.cos(2 * M.PI * k / n),
                z + (R + 0.12) * M.sin(2 * M.PI * k / n)) for k in range(n)]
        for k in range(n):
            mesh.beam("steel.painted", pts[k], pts[(k + 1) % n], 0.3, 0.22)
        s += 10.0
    lods = []
    for n, step in TUBE_LODS:
        g = Mesh(inp["origin"])
        g.sweep("glass.tube", ln.frames(0.0, ln.L, step), _ring(R, zc, n), closed=True)
        lods.append(g)
    return Out(mesh=mesh, extra=[{"suffix": ".glass", "lods": lods, "nanite": False,
                                  "screen": list(TUBE_SCREEN)}])


@maker("transit_column", 1)
def make_transit_column(inp: dict) -> Out:
    st = inp["st"]
    a = st.get("attrs", {})
    g = _g(inp)
    ring = ccw(st["footprint"]["exterior"])
    z0, z1 = st["z0_m"] + g, st["z1_m"] + g
    mesh = Mesh(inp["origin"])
    mode = a.get("mode", "elevated_rail")
    cap = 0.0 if mode == "monorail" else (1.6 if mode == "sky_tube" else 1.2)
    cap = min(cap, max((z1 - z0) * 0.3, 0.0))
    mesh.prism("concrete.column", ring, z0, z1 - cap, top=cap == 0.0)
    if cap > 0.0:
        d = inp.get("dir") or [1.0, 0.0]
        c = inp["origin"]
        across = GUIDEWAY_W.get(mode, 6.0) - (1.0 if mode != "sky_tube" else 0.0)
        mesh.obox("concrete.column", c[0], c[1], z1 - cap, 2.2, across, cap, d[0], d[1])
    return Out(mesh=mesh)


@maker("station_part", 1)
def make_station_part(inp: dict) -> Out:
    st = inp["st"]
    a = st.get("attrs", {})
    g = _g(inp)
    mesh = Mesh(inp["origin"])
    role = a.get("role")
    z0, z1 = st["z0_m"] + g, st["z1_m"] + g
    fp = st.get("footprint")
    if st["kind"] == "canopy":
        if fp is not None:
            ring = ccw(fp["exterior"])
            mesh.prism("steel.painted", ring, max(z0, z1 - 0.3), z1, bottom=True)
            for p in _posts(ring):
                mesh.box("steel", p[0], p[1], g, 0.2, 0.2, max(z1 - 0.3 - g, 0.1))
        elif st.get("line"):
            try:
                ln = Line3(st["line"], inp.get("ground"))
            except ValueError:
                return Out(empty="degenerate line")
            w = a.get("width_m", 3.0)
            mesh.sweep("steel.painted", ln.frames(0.0, ln.L, 6.0),
                       [(w / 2.0, -0.25), (w / 2.0, 0.0), (-w / 2.0, 0.0), (-w / 2.0, -0.25)],
                       closed=True)
            s = 0.0
            while s <= ln.L:
                x, y, nx, ny, _ = ln.path.frame(min(s, ln.L))
                zt = ln.z(min(s, ln.L)) - 0.25
                gp = (inp.get("ground") or [0.0])[0]
                for side in (-1.0, 1.0):
                    px, py = x + nx * side * (w / 2.0 - 0.2), y + ny * side * (w / 2.0 - 0.2)
                    mesh.box("steel", px, py, gp, 0.15, 0.15, max(zt - gp, 0.1))
                s += 6.0
        return Out(mesh=mesh)
    if st["kind"] == "deck" and role == "skywalk" and st.get("line"):
        try:
            ln = Line3(st["line"], inp.get("ground"))
        except ValueError:
            return Out(empty="degenerate line")
        w = a.get("width_m", 4.0)
        h = w / 2.0
        fr = ln.frames(0.0, ln.L, 6.0)
        mesh.sweep("concrete.deck", fr, [(h, 0.0), (h, -0.6), (-h, -0.6), (-h, 0.0)],
                   closed=True)
        mesh.sweep("glass.opaque", fr, [(-h, 0.0), (-h, 2.8)])
        mesh.sweep("glass.opaque", fr, [(h, 2.8), (h, 0.0)])
        mesh.sweep("steel.painted", fr, [(-h - 0.2, 2.8), (-h - 0.2, 3.1), (h + 0.2, 3.1),
                                         (h + 0.2, 2.8)], closed=True)
        return Out(mesh=mesh)
    if fp is not None:
        ring = ccw(fp["exterior"])
        holes = fp.get("holes", [])
        if role == "platform":
            mesh.prism("concrete.deck", ring, z0, z1 - 0.05, top=False, bottom=True,
                       holes=holes)
            mesh.prism("paving.granite_dark", ring, z1 - 0.05, z1, holes=holes)
        elif role == "concourse" or z1 <= g:
            mesh.prism("concrete.dark", ring, z0, z1, bottom=True, holes=holes)
        elif role == "elevator_core":
            mesh.prism("concrete.column", ring, z0, z1)
        else:
            slot = "concrete.column" if st["kind"] in ("column", "pylon") else "concrete.deck"
            mesh.prism(slot, ring, z0, max(z1, z0 + 0.3), bottom=z0 > g + 0.5, holes=holes)
        return Out(mesh=mesh)
    if st.get("line"):
        try:
            ln = Line3(st["line"], inp.get("ground"))
        except ValueError:
            return Out(empty="degenerate line")
        w = a.get("width_m", 4.0)
        t = a.get("deck_m", max(st["z1_m"] - st["z0_m"], 0.5))
        mesh.sweep("concrete.deck", ln.frames(0.0, ln.L, 6.0),
                   [(w / 2.0, 0.0), (w / 2.0, -t), (-w / 2.0, -t), (-w / 2.0, 0.0)],
                   closed=True)
        return Out(mesh=mesh)
    return Out(empty="no footprint or line")


def _posts(ring) -> list[tuple[float, float]]:
    """Posts under a canopy: its corners pulled 0.3 m in."""
    cx_ = sum(p[0] for p in ring) / len(ring)
    cy_ = sum(p[1] for p in ring) / len(ring)
    out = []
    for p in ring:
        d = dist(p, (cx_, cy_))
        if d < 0.5:
            continue
        f = (d - 0.3) / d
        out.append((cx_ + (p[0] - cx_) * f, cy_ + (p[1] - cy_) * f))
    return out[:8]


def maker_for(st) -> str | None:
    """Which generator a model structure takes."""
    a = st.attrs or {}
    if st.kind == "column" and a.get("road_id") and not a.get("line_id"):
        return "column"
    if st.kind in ("column", "pylon") and a.get("line_id"):
        return "transit_column"
    if st.kind == "deck" and a.get("line_id") and not a.get("station"):
        return "guideway"
    if st.kind == "tube":
        return "sky_tube"
    if st.kind == "trench":
        return "trench"
    if st.kind == "portal":
        return "portal"
    if st.kind == "vent":
        return "vent"
    if st.kind == "retaining_wall":
        return "retaining_wall"
    return "station_part"


@maker("retaining_wall", 1)
def make_retaining_wall(inp: dict) -> Out:
    """M13's retaining walls: line z is the wall's height over its lower side; the ground
    at the line is about halfway up, so the wall runs from under the lower ground to a
    0.3 m parapet over the upper (as M13's blockout draws it)."""
    st = inp["st"]
    line = st.get("line") or []
    if len(line) < 2:
        return Out(empty="no line")
    mesh = Mesh(inp["origin"])
    gnd = inp.get("ground") or [0.0] * len(line)
    try:
        Path([(p[0], p[1]) for p in line])
    except ValueError:
        return Out(empty="degenerate line")
    for k in range(len(line) - 1):
        p, q = line[k], line[k + 1]
        if dist(p, q) < 0.01:
            continue
        ux, uy = unit(q[0] - p[0], q[1] - p[1])
        ox, oy = -uy * 0.2, ux * 0.2
        ha, hb = max(p[2], 0.3), max(q[2], 0.3)
        ta, tb = gnd[k] + ha / 2.0 + 0.3, gnd[k + 1] + hb / 2.0 + 0.3
        ba, bb = gnd[k] - ha / 2.0 - 0.7, gnd[k + 1] - hb / 2.0 - 0.7
        for s in (1.0, -1.0):
            a_ = (p[0] + ox * s, p[1] + oy * s)
            b_ = (q[0] + ox * s, q[1] + oy * s)
            if s > 0:
                mesh.wall("concrete", b_, a_, bb, tb, ba, ta)
            else:
                mesh.wall("concrete", a_, b_, ba, ta, bb, tb)
        mesh.quad("stone.coping", (p[0] - ox, p[1] - oy, ta), (q[0] - ox, q[1] - oy, tb),
                  (q[0] + ox, q[1] + oy, tb), (p[0] + ox, p[1] + oy, ta))
    return Out(mesh=mesh)


__all__ = ["gather_structure", "maker_for", "C"]
