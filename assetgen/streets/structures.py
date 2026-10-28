"""Bridges, road columns and tunnels.

- **Bridges** (the deck itself is its road segment's): girder bridges get wall piers with
  caps every 40 m over the water and abutments at the banks; named landmark crossings get
  a through arch (two parabolic ribs with hangers) or, over long spans, a cable-stayed main
  span (H pylons, fans of stays); footbridges get the canal's style: stone parapets and an
  arch ring in heritage districts, steel railings on girders elsewhere, and steps where
  their ramps are stairs.
- **Road columns** (M7, M8d, M12): the model's column footprint as the shaft, a pier cap
  across the road under the deck.
- **Tunnels** (M9): the covered stretch of a road tunnel (walls lined with tile, roof slab,
  light strips), each portal's headwall with its opening, each open approach's walls up to
  a parapet; metro tunnels and pedestrian underpasses as lined boxes with a track or a
  walkway and lights; underpass stair wells with steps; ventilation buildings.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from .. import canon as C
from . import materials as MT
from .ctx import Ctx, bbox_center, dump
from .kit import Mesh, ccw
from .path import Path, Profile, dist, unit
from .pieces import Out, Piece, maker
from .roads import DECK_D, ROAD_DZ, Road, street_class

WATER_Z = {"sea": -1.2}
WATER_DEFAULT = -0.9      # the blockout's canal and river surface


class Line3:
    """A 3D polyline: plan path plus z along it (z held at the ends)."""

    def __init__(self, pts, ground=None):
        self.path = Path([(p[0], p[1]) for p in pts])
        zs = [float(p[2]) for p in pts]
        if ground:
            zs = [z + g for z, g in zip(zs, ground)]
        # the path drops near-duplicate points: keep the z of the points it kept
        keep = []
        j = 0
        for p, z in zip(pts, zs):
            if j < len(self.path.p) and abs(p[0] - self.path.p[j][0]) < 0.006 and \
                    abs(p[1] - self.path.p[j][1]) < 0.006:
                keep.append(z)
                j += 1
        if len(keep) != len(self.path.p):
            keep = [zs[0]] * len(self.path.p)
        self.zp = Profile(list(zip(self.path.cum, keep)))
        self.L = self.path.L

    def z(self, s: float) -> float:
        return self.zp(s)

    def frames(self, s0: float, s1: float, step: float, tc: float = 0.0, dz: float = 0.0):
        out = []
        for s, vi in self.path.stations(s0, s1, step):
            x, y, nx, ny, k = self.path.frame(s, vi)
            out.append((x + nx * k * tc, y + ny * k * tc, self.z(s) + dz, nx, ny, k, s))
        return out


def box_prof(t0: float, t1: float, z0: float, z1: float):
    """An outward box section from t0 to t1 (t0 < t1), z0 to z1."""
    return [(t0, z0), (t0, z1), (t1, z1), (t1, z0)]


# ---------------------------------------------------------------------------
# Bridges
# ---------------------------------------------------------------------------

def bridge_kind(b: dict, style: dict) -> str:
    if b.get("name") and (b.get("span_m") or 0.0) >= 250.0:
        return "cable_stayed"
    if b["bridge_class"] == "pedestrian" or b.get("attrs", {}).get("footbridge"):
        return "footbridge.stone" if style["era"] == "heritage" else "footbridge.steel"
    if b.get("name"):
        return "arch"
    return "girder"


def own_deck(b: dict, inp: dict) -> dict:
    """Road inputs for a bridge that carries no road segment of its own (a named
    footbridge): its deck along its line, 6 m wide for people, 14 m for traffic."""
    from .roads import Road  # noqa: F401  (the same maker draws it)
    ped = b["bridge_class"] == "pedestrian"
    W = 6.0 if ped else 14.0
    pts = [(p[0], p[1]) for p in b["line"]]
    path = Path(pts)
    zs = [p[2] for p in b["line"]]
    keep = [z for p, z in zip(pts, zs)][:len(path.p)]
    seg = {"id": b["id"], "centerline": [list(p) for p in path.p],
           "z_profile": [{"s": s, "z": z} for s, z in zip(path.cum, keep)],
           "width_m": W, "road_class": "footbridge" if ped else "street", "bridge": True,
           "attrs": {}, "cross_section": {"sidewalk_m": [0.0, 0.0], "curb_m": 0.15,
                                          "median_m": 0.0, "shared": False}}
    g = inp.get("ground")
    if g and len(g) == len(path.p):
        seg["ground"] = [{"s": s, "z": z} for s, z in zip(path.cum, g)]
    return {"seg": seg, "cls": "footbridge" if ped else "street", "ends": [],
            "crossings": [], "lanes": [], "style": inp["style"], "start": "", "end": "",
            "origin": inp["origin"]}


def gather_bridge(cx: Ctx, b) -> Piece:
    segs = []
    for sid in b.segment_ids:
        s = cx.seg.get(sid)
        if s is not None:
            seg = dump(s)
            seg.pop("district_ids", None)
            segs.append({"seg": seg, "cls": street_class(s), "ends": [], "crossings": [],
                         "lanes": [], "start": s.start, "end": s.end, "origin": [0, 0]})
    pts = [(p[0], p[1]) for p in b.line]
    try:
        path = Path(pts)
        wet = []
        n = max(2, int(path.L / 5.0) + 1)
        for k in range(n):
            s = path.L * k / (n - 1)
            x, y = path.point(s)
            wet.append(1 if cx.wet_at(x, y) else 0)
    except ValueError:
        wet = []
    did = None
    if b.segment_ids and b.segment_ids[0] in cx.seg:
        s0 = cx.seg[b.segment_ids[0]]
        did = s0.district_ids[0] if s0.district_ids else s0.attrs.get("district")
    wl = cx.ground.water_level(b.crosses, WATER_Z.get(b.water_class or "", WATER_DEFAULT))
    inputs = {"bridge": dump(b), "segs": segs, "wet": wet, "water_z": C.m(wl),
              "ground": cx.ground.samples(b.line), "style": cx.style(did),
              "origin": list(bbox_center(pts))}
    return Piece(b.id, "street.bridge", "bridge", cx.tile_for(b.id, pts),
                 cx.keys.get(b.id, []), inputs)


def _wet_runs(wet, L: float) -> list[tuple[float, float]]:
    """Stretches of the bridge line over the water (s0, s1)."""
    n = len(wet)
    if n < 2:
        return []
    runs, start = [], None
    for k, w in enumerate(wet):
        s = L * k / (n - 1)
        if w and start is None:
            start = s
        if not w and start is not None:
            runs.append((start, s))
            start = None
    if start is not None:
        runs.append((start, L))
    return runs


@maker("bridge", 1)
def make_bridge(inp: dict) -> Out:
    b = inp["bridge"]
    try:
        ln = Line3(b["line"], inp.get("ground"))
    except ValueError:
        return Out(empty="degenerate line")
    style = inp["style"]
    kind = bridge_kind(b, style)
    segs = inp["segs"]
    mesh = Mesh(inp["origin"])
    if not segs:
        from .roads import make as make_road
        syn = own_deck(b, inp)
        segs = [syn]
        mesh = make_road(syn).mesh or mesh
    seg = segs[0]["seg"]
    W = seg["width_m"]
    cls = segs[0]["cls"]
    D = DECK_D.get(cls, 1.2)
    wz = inp["water_z"]
    out = Out(mesh=mesh)
    out.notes["bridge_kind"] = kind
    runs = _wet_runs(inp["wet"], ln.L)
    if kind.startswith("footbridge") or cls == "footbridge":
        _footbridge(mesh, ln, dict(inp, segs=segs), "footbridge.steel"
                    if kind == "cable_stayed" else kind, W, wz)
        if kind != "cable_stayed":
            return out
    main = None
    if runs:
        w0, w1 = max(runs, key=lambda r: (r[1] - r[0], -r[0]))
        main = (w0, w1)
    if kind == "arch" and main is not None:
        a0, a1 = main
        if a1 - a0 > 320.0:
            sm = (a0 + a1) / 2.0
            a0, a1 = sm - 160.0, sm + 160.0
        _arch(mesh, ln, a0, a1, W, D, wz)
        _piers(mesh, ln, runs, W, D, wz, skip=(a0 - 5.0, a1 + 5.0), step=40.0)
    elif kind == "cable_stayed" and main is not None:
        w0, w1 = main
        sm = (w0 + w1) / 2.0
        half = min((w1 - w0) * 0.3, 225.0)
        p0, p1 = sm - half, sm + half
        _cable_stayed(mesh, ln, p0, p1, W, D, wz)
        _piers(mesh, ln, runs, W, D, wz, skip=(p0 - 30.0, p1 + 30.0), step=50.0)
    else:
        _piers(mesh, ln, runs, W, D, wz, skip=None, step=40.0)
    # abutments where the bridge meets the banks
    gnd = inp.get("ground") or [0.0, 0.0]
    for s, g in ((min(4.0, ln.L / 4.0), gnd[0]), (max(ln.L - 4.0, ln.L * 0.75), gnd[-1])):
        x, y, nx, ny, _ = ln.path.frame(s)
        dx, dy = ln.path.tangent(s)
        zt = ln.z(s) - D
        gb = g - 1.0
        if zt - gb > 0.5:
            mesh.obox("concrete", x, y, gb, 2.0, W + 1.0, zt - gb, dx, dy)
    return out


def _piers(mesh: Mesh, ln: Line3, runs, W: float, D: float, wz: float, skip, step: float):
    for r0, r1 in runs:
        if r1 - r0 < 12.0:
            continue
        n = max(1, int((r1 - r0) / step))
        for k in range(1, n + 1):
            s = r0 + (r1 - r0) * k / (n + 1)
            if skip is not None and skip[0] <= s <= skip[1]:
                continue
            x, y, _, _, _ = ln.path.frame(s)
            dx, dy = ln.path.tangent(s)
            top = ln.z(s) - D
            if top - wz < 1.0:
                continue
            mesh.obox("concrete.column", x, y, wz - 4.0, 2.4, max(W - 4.0, 2.0),
                      top - 1.2 - (wz - 4.0), dx, dy)
            mesh.obox("concrete.column", x, y, top - 1.2, 3.0, W - 0.5, 1.2, dx, dy)


def _arch(mesh: Mesh, ln: Line3, a0: float, a1: float, W: float, D: float, wz: float):
    span = a1 - a0
    rise = min(0.2 * span, 70.0)
    sm = (a0 + a1) / 2.0
    zs0 = wz + 1.0
    n = 24
    for side in (-1.0, 1.0):
        t = side * (W / 2.0 + 0.9)
        pts = []
        for k in range(n + 1):
            s = a0 + span * k / n
            x, y, nx, ny, _ = ln.path.frame(s)
            u = (s - sm) / (span / 2.0)
            zd = ln.z(sm)
            z = zs0 + (zd + rise - zs0) * (1.0 - u * u)
            pts.append((x + nx * t, y + ny * t, z, s))
        for p, q in zip(pts, pts[1:]):
            mesh.beam("steel.painted", p[:3], q[:3], 1.6, 2.2)
        s = a0 + 4.0
        while s < a1 - 4.0:
            x, y, nx, ny, _ = ln.path.frame(s)
            u = (s - sm) / (span / 2.0)
            zr = zs0 + (ln.z(sm) + rise - zs0) * (1.0 - u * u) - 1.1
            zd = ln.z(s)
            if zr - zd > 1.5:
                mesh.beam("steel.cable", (x + nx * t, y + ny * t, zd),
                          (x + nx * t, y + ny * t, zr), 0.14, 0.14)
            s += 8.0
        for s in (a0, a1):
            x, y, nx, ny, _ = ln.path.frame(s)
            dx, dy = ln.path.tangent(s)
            mesh.obox("concrete.column", x + nx * t, y + ny * t, wz - 4.0, 5.0, 4.0, 6.0,
                      dx, dy)


def _cable_stayed(mesh: Mesh, ln: Line3, p0: float, p1: float, W: float, D: float,
                  wz: float):
    main = p1 - p0
    H = max(0.25 * main, 30.0)
    for sp in (p0, p1):
        x, y, nx, ny, _ = ln.path.frame(sp)
        dx, dy = ln.path.tangent(sp)
        zd = ln.z(sp)
        tops = []
        for side in (-1.0, 1.0):
            t = side * (W / 2.0 + 1.8)
            bx, by = x + nx * t, y + ny * t
            mesh.obox("concrete.column", bx, by, wz - 4.0, 3.2, 2.6, zd + H - (wz - 4.0),
                      dx, dy)
            tops.append((bx, by, zd + H - 1.0))
        mesh.beam("concrete.column", (tops[0][0], tops[0][1], zd - D - 0.8),
                  (tops[1][0], tops[1][1], zd - D - 0.8), 2.6, 1.6)
        mesh.beam("concrete.column", tops[0], tops[1], 2.4, 2.0)
        for side, top in zip((-1.0, 1.0), tops):
            t = side * (W / 2.0 - 0.3)
            for sgn in (-1.0, 1.0):
                d = 14.0
                while d < main / 2.0 - 4.0:
                    s = sp + sgn * d
                    if 0.0 < s < ln.L:
                        ax, ay, anx, any_, _ = ln.path.frame(s)
                        z_top = top[2] - (d / (main / 2.0)) * H * 0.35
                        mesh.beam("steel.cable", (top[0], top[1], z_top),
                                  (ax + anx * t, ay + any_ * t, ln.z(s) + 0.2), 0.16, 0.16)
                    d += 12.0


def _footbridge(mesh: Mesh, ln: Line3, inp: dict, kind: str, W: float, wz: float):
    seg = inp["segs"][0] if inp["segs"] else None
    rd = None
    if seg is not None:
        try:
            rd = Road(seg)
        except ValueError:
            rd = None
    if rd is None:
        return
    L = rd.L
    W2 = rd.W / 2.0
    if kind == "footbridge.stone":
        for side in (-1.0, 1.0):
            prof = box_prof(W2 - 0.3, W2, 0.0, 0.95) if side > 0 else \
                box_prof(-W2, -W2 + 0.3, 0.0, 0.95)
            rd.sweep(mesh, "stone.coping", 0.0, L, prof, base=-ROAD_DZ, step=1.5)
            # the arch ring under the deck, both faces
            t = side * W2
            pts = []
            n = 12
            zt = max(rd.zp(L / 2.0) + rd.gp(L / 2.0) - 0.6, wz + 1.0)
            for k in range(n + 1):
                s = L * k / n
                u = (s - L / 2.0) / (L / 2.0)
                z = wz + 0.3 + (zt - wz - 0.3) * math.sqrt(max(1.0 - u * u, 0.0))
                x, y = rd.xy(s, t - side * 0.4)
                pts.append((x, y, z))
            for p, q in zip(pts, pts[1:]):
                mesh.beam("stone.arch", p, q, 0.8, 0.7)
    else:
        for side in (-1.0, 1.0):
            t = side * (W2 - 0.05)
            s = 0.0
            while s <= L + 1e-6:
                x, y = rd.xy(min(s, L), t)
                z = rd.z(min(s, L))
                mesh.beam("steel.painted", (x, y, z), (x, y, z + 1.1), 0.06, 0.06)
                s += 1.5
            for zr, w in ((1.1, 0.07), (0.55, 0.04)):
                rd.sweep(mesh, "steel.painted", 0.0, L,
                         box_prof(-w / 2.0, w / 2.0, zr - w / 2.0, zr + w / 2.0), tc=t,
                         step=1.5)
            rd.sweep(mesh, "steel.painted", 0.0, L,
                     box_prof(-0.15, 0.15, -0.9, -0.1), tc=side * (W2 - 0.4), base=-ROAD_DZ,
                     step=2.0)
    # steps where the ramps are stairs (steeper than 15%)
    _steps(mesh, rd, "stone.coping" if kind == "footbridge.stone" else "concrete")


def _steps(mesh: Mesh, rd: Road, slot: str, riser: float = 0.17):
    zs = rd.zp
    for k in range(len(zs.s) - 1):
        s0, s1 = zs.s[k], zs.s[k + 1]
        dzv = zs.z[k + 1] - zs.z[k]
        if s1 - s0 < 0.3 or abs(dzv) / (s1 - s0) < 0.15:
            continue
        n = max(1, int(math.ceil(abs(dzv) / riser)))
        run = (s1 - s0) / n
        hs = abs(dzv) / n
        h = rd.W / 2.0 - 0.1
        for i in range(n):
            a = s0 + run * i
            bb = a + run
            base = rd.gp(a) + zs.z[k] + ROAD_DZ + 0.005
            # going up, each tread is at the top of its run and its riser at the run's
            # start; going down, at the run's start and its riser at the run's end: the
            # ramp's surface stays under the steps
            zt = base + dzv * ((i + 1) if dzv > 0 else i) / n
            ring = [(a, -h), (bb, -h), (bb, h), (a, h)]
            mesh.poly_map(slot, ring, (), lambda s, t, zt=zt: (*rd.xy(s, t), zt))
            edge = a if dzv > 0 else bb
            p, q = rd.xy(edge, -h), rd.xy(edge, h)
            if dzv > 0:
                mesh.wall(slot, q, p, zt - hs, zt, zt - hs, zt)
            else:
                mesh.wall(slot, p, q, zt - hs, zt, zt - hs, zt)


# ---------------------------------------------------------------------------
# Road columns
# ---------------------------------------------------------------------------

def gather_column(cx: Ctx, st) -> Piece:
    a = st.attrs or {}
    s = cx.seg.get(a.get("road_id"))
    ring = st.footprint.exterior
    c = bbox_center(ring)
    road = None
    if s is not None:
        road = {"line": [list(p) for p in s.centerline], "width": s.width_m,
                "s_m": a.get("s_m")}
    inputs = {"st": dump(st), "road": road, "ground": cx.ground.samples([c]),
              "origin": list(c)}
    return Piece(st.id, "street.column", "column", cx.tile_for(st.id, ring),
                 cx.keys.get(st.id, []), inputs)


@maker("column", 1)
def make_column(inp: dict) -> Out:
    st = inp["st"]
    ring = ccw(st["footprint"]["exterior"])
    g = inp["ground"][0] if inp.get("ground") else 0.0
    z0, z1 = st["z0_m"] + g, st["z1_m"] + g
    mesh = Mesh(inp["origin"])
    road = inp.get("road")
    cx_, cy_ = inp["origin"][0], inp["origin"][1]
    cap = 1.0 if z1 - z0 > 3.0 else 0.0
    mesh.prism("concrete.column", ring, z0, z1 - cap, top=cap == 0.0)
    if cap and road is not None:
        try:
            p = Path(road["line"])
            s, _ = p.project(cx_, cy_)
            dx, dy = p.tangent(s)
        except ValueError:
            dx, dy = 1.0, 0.0
        across = max(road["width"] - 1.5, 3.0)
        mesh.obox("concrete.column", cx_, cy_, z1 - cap, 2.4, across, cap, dx, dy)
    elif cap:
        mesh.prism("concrete.column", ring, z1 - cap, z1)
    return Out(mesh=mesh)


# ---------------------------------------------------------------------------
# Tunnels
# ---------------------------------------------------------------------------

def gather_tunnel(cx: Ctx, t) -> Piece:
    pts = [(p[0], p[1]) for p in t.line]
    inputs = {"tunnel": dump(t), "ground": cx.ground.samples(t.line),
              "origin": list(bbox_center(pts))}
    return Piece(t.id, f"street.tunnel.{t.kind}", "tunnel", cx.tile_for(t.id, pts),
                 cx.keys.get(t.id, []), inputs)


def _portal_s(ln: Line3, portals) -> list[float]:
    out = []
    for p in portals:
        s, _ = ln.path.project(p["position"][0], p["position"][1])
        out.append(s)
    return sorted(out)


def _lined_walls(mesh: Mesh, ln: Line3, s0: float, s1: float, w: float, z_bot: float,
                 top_of, inner_slot: str, outer_slot: str = "concrete", step: float = 6.0):
    """Both walls of a road tunnel or trench: 1 m thick, inner face toward the road; top_of(s)
    gives each station's top height."""
    if s1 - s0 < 0.05:
        return
    st = ln.path.stations(s0, s1, step, ln.zp.knots(s0, s1))
    for side in (-1.0, 1.0):
        ti, to = side * (w / 2.0 - 1.0), side * w / 2.0
        inner, top, outer = [], [], []
        ui, ut, uo, ei, eo = [], [], [], [], []
        for s, vi in st:
            x, y, nx, ny, k = ln.path.frame(s, vi)
            zb = ln.z(s) + z_bot
            zt = top_of(s)
            pi = (x + nx * k * ti, y + ny * k * ti)
            po = (x + nx * k * to, y + ny * k * to)
            if side > 0:
                inner.append([(*pi, zb), (*pi, zt)])
                ui.append([(s, zb), (s, zt)])
                top.append([(*pi, zt), (*po, zt)])
                outer.append([(*po, zt), (*po, zb)])
                uo.append([(s, zt), (s, zb)])
            else:
                inner.append([(*pi, zt), (*pi, zb)])
                ui.append([(s, zt), (s, zb)])
                top.append([(*po, zt), (*pi, zt)])
                outer.append([(*po, zb), (*po, zt)])
                uo.append([(s, zb), (s, zt)])
            ut.append([(s, 0.0), (s, 1.0)])
            ei.append((-side * nx, -side * ny, 0.0))
            eo.append((side * nx, side * ny, 0.0))
        # inner faces look at the road: the left wall's (side > 0) toward -t
        mesh.grid(inner_slot, inner, ui, expect=ei)
        mesh.grid(outer_slot, top, ut, expect=(0.0, 0.0, 1.0))
        mesh.grid(outer_slot, outer, uo, expect=eo)


@maker("tunnel", 1)
def make_tunnel(inp: dict) -> Out:
    t = inp["tunnel"]
    try:
        ln = Line3(t["line"], inp.get("ground"))
    except ValueError:
        return Out(empty="degenerate line")
    mesh = Mesh(inp["origin"])
    w, clear, roof = t["width_m"], t["clear_m"], t["roof_m"]
    if t["kind"] in ("metro", "pedestrian"):
        _tube(mesh, ln, t)
        return Out(mesh=mesh)
    ps = _portal_s(ln, t.get("portals", []))
    a, b = (ps[0], ps[-1]) if len(ps) >= 2 else (0.0, ln.L)
    if b - a < 1.0:
        return Out(empty="no covered stretch")
    _lined_walls(mesh, ln, a, b, w, -0.3, lambda s: ln.z(s) + clear, "tile.tunnel")
    hi = w / 2.0 - 1.0
    ln_ = ln
    fr = ln_.frames(a, b, 6.0)
    mesh.sweep("concrete", fr, [(hi, clear), (-hi, clear)])          # soffit, facing down
    mesh.sweep("concrete", fr, [(-w / 2.0, clear + roof), (w / 2.0, clear + roof)])
    for side in (-1.0, 1.0):
        tl = side * (hi - 0.03)
        prof = [(tl, clear - 0.85), (tl, clear - 0.7)] if side > 0 else \
            [(tl, clear - 0.7), (tl, clear - 0.85)]
        mesh.sweep("light", fr, prof)
    return Out(mesh=mesh)


def _tube(mesh: Mesh, ln: Line3, t: dict):
    """A metro tunnel or an underpass: a lined box (outer shell, inner lining facing in), a
    track or a walkway, a light strip."""
    w, clear, roof, floor = t["width_m"], t["clear_m"], t["roof_m"], t.get("floor_m", 1.0)
    fr = ln.frames(0.0, ln.L, 8.0)
    hw = w / 2.0
    hi = hw - 0.5
    mesh.sweep("concrete.dark", fr, box_prof(-hw, hw, -floor, clear + roof))
    # the lining, facing in: the profile run the other way round
    lining = "tile.tunnel"
    mesh.sweep(lining, fr, [(hi, 0.0), (hi, clear), (-hi, clear), (-hi, 0.0)])
    if t["kind"] == "metro":
        mesh.sweep("concrete", fr, [(-hi, 0.0), (hi, 0.0)])
        for c in (-1.6, 1.6):
            for g in (-0.7175, 0.7175):
                mesh.sweep("rail", fr, box_prof(c + g - 0.04, c + g + 0.04, 0.0, 0.17))
    else:
        mesh.sweep("paving.tile", fr, [(-hi, 0.0), (hi, 0.0)])
    mesh.sweep("light.cool", fr, [(-0.3, clear - 0.02), (0.3, clear - 0.02)][::-1])


def _tunnel_of(cx: Ctx, st):
    return cx.tunnel.get((st.attrs or {}).get("tunnel"))


def gather_trench(cx: Ctx, st) -> Piece:
    t = _tunnel_of(cx, st)
    ring = st.footprint.exterior
    c = bbox_center(ring)
    inputs = {"st": dump(st), "tunnel": dump(t) if t is not None else None,
              "ground": cx.ground.samples(t.line) if t is not None else None,
              "ground_c": cx.ground.samples([c]), "origin": list(c)}
    return Piece(st.id, f"street.{(st.attrs or {}).get('role', 'trench')}", "trench",
                 cx.tile_for(st.id, ring), cx.keys.get(st.id, []), inputs)


@maker("trench", 1)
def make_trench(inp: dict) -> Out:
    st, t = inp["st"], inp["tunnel"]
    mesh = Mesh(inp["origin"])
    role = st.get("attrs", {}).get("role")
    if role == "underpass_stair" or t is None:
        _stair_well(mesh, inp)
        return Out(mesh=mesh)
    try:
        ln = Line3(t["line"], inp.get("ground"))
    except ValueError:
        return Out(empty="degenerate tunnel line")
    ps = _portal_s(ln, t.get("portals", []))
    c = inp["origin"]
    s_c, _ = ln.path.project(c[0], c[1])
    if not ps:
        return Out(empty="no portal")
    p = min(ps, key=lambda v: abs(v - s_c))
    s0, s1 = (0.0, p) if s_c < p else (p, ln.L)
    gnd = inp["ground"]
    gl = Line3([(q[0], q[1], 0.0) for q in t["line"]], gnd) if gnd else None

    def top(s):
        g = gl.z(s) if gl is not None else 0.0
        return max(g + 1.0, ln.z(s) + 1.0)
    _lined_walls(mesh, ln, s0, s1, t["width_m"], -0.3, top, "concrete")
    return Out(mesh=mesh)


def _stair_well(mesh: Mesh, inp: dict):
    st = inp["st"]
    ring = ccw(st["footprint"]["exterior"])
    g = inp["ground_c"][0] if inp.get("ground_c") else 0.0
    # the long axis: the stair runs along it, down toward the tunnel
    best = max(range(len(ring)), key=lambda i: (dist(ring[i], ring[(i + 1) % len(ring)]), -i))
    a, b = ring[best], ring[(best + 1) % len(ring)]
    ux, uy = unit(b[0] - a[0], b[1] - a[1])
    L = dist(a, b)
    c = inp["origin"]
    xs = [((p[0] - c[0]) * -uy + (p[1] - c[1]) * ux) for p in ring]
    W = max(xs) - min(xs)
    z_low, z_top = st["z0_m"] + g, g
    t = inp.get("tunnel")
    low_at = 1.0
    if t is not None:
        ends = [t["line"][0], t["line"][-1]]
        e = min(ends, key=lambda q: dist(q, c))
        low_at = 1.0 if (e[0] - c[0]) * ux + (e[1] - c[1]) * uy > 0 else -1.0
    ux, uy = ux * low_at, uy * low_at
    vx, vy = -uy, ux
    depth = z_top - z_low
    n = max(1, int(math.ceil(depth / 0.17)))
    run = L / n
    hw = W / 2.0 - 0.3
    for i in range(n):
        a0 = -L / 2.0 + run * i
        zt = z_top - depth * (i + 1) / n
        quad = [(a0, -hw), (a0 + run, -hw), (a0 + run, hw), (a0, hw)]
        mesh.poly_map("concrete", quad, (), lambda u, v, zt=zt: (
            c[0] + ux * u + vx * v, c[1] + uy * u + vy * v, zt))
        p = (c[0] + ux * a0 + vx * -hw, c[1] + uy * a0 + vy * -hw)
        q = (c[0] + ux * a0 + vx * hw, c[1] + uy * a0 + vy * hw)
        mesh.wall("concrete", p, q, zt, zt + depth / n, zt, zt + depth / n)
    for side in (-1.0, 1.0):
        cxs, cys = c[0] + vx * side * (W / 2.0 - 0.15), c[1] + vy * side * (W / 2.0 - 0.15)
        mesh.obox("concrete", cxs, cys, z_low - 0.3, L, 0.3, z_top + 1.1 - (z_low - 0.3),
                  ux, uy)


def gather_portal(cx: Ctx, st) -> Piece:
    t = _tunnel_of(cx, st)
    ring = st.footprint.exterior
    c = bbox_center(ring)
    inputs = {"st": dump(st), "tunnel": dump(t) if t is not None else None,
              "ground_c": cx.ground.samples([c]), "origin": list(c)}
    return Piece(st.id, "street.portal", "portal", cx.tile_for(st.id, ring),
                 cx.keys.get(st.id, []), inputs)


@maker("portal", 1)
def make_portal(inp: dict) -> Out:
    st, t = inp["st"], inp["tunnel"]
    mesh = Mesh(inp["origin"])
    c = inp["origin"]
    g = inp["ground_c"][0] if inp.get("ground_c") else 0.0
    if t is None or not t.get("portals"):
        mesh.prism("concrete", st["footprint"]["exterior"], st["z0_m"] + g, st["z1_m"] + g)
        return Out(mesh=mesh)
    p = min(t["portals"], key=lambda q: dist(q["position"], c))
    h = M.radians(p["heading_deg"])
    dx, dy = M.cos(h), M.sin(h)            # into the tunnel
    nx, ny = -dy, dx
    w, clear, roof = t["width_m"], t["clear_m"], t["roof_m"]
    zr = p["position"][2] + g
    zt = max(g + 1.0, zr + clear + roof + 0.5)
    zb = zr - 0.3
    hw = w / 2.0 + 1.0
    ho = w / 2.0 - 1.0
    px, py = p["position"][0], p["position"][1]
    # front face, 1 m out from the portal, facing out of the tunnel (U x V = -d), with the
    # opening
    o = (px - dx * 1.0, py - dy * 1.0, zb)
    U = (-nx, -ny, 0.0)
    V = (0.0, 0.0, 1.0)
    outer = [(-hw, 0.0), (hw, 0.0), (hw, zt - zb), (-hw, zt - zb)]
    hole = [(-ho, 0.3), (ho, 0.3), (ho, 0.3 + clear), (-ho, 0.3 + clear)]
    mesh.face("concrete", o, U, V, outer, [hole])
    # the reveals through the 1 m wall and the coping
    for a_, b_, z0, z1 in (((-ho, 1), (-ho, 0), zb + 0.3, zb + 0.3 + clear),
                           ((ho, 0), (ho, 1), zb + 0.3, zb + 0.3 + clear)):
        pa = (px + nx * a_[0] - dx * (1 - a_[1]), py + ny * a_[0] - dy * (1 - a_[1]))
        pb = (px + nx * b_[0] - dx * (1 - b_[1]), py + ny * b_[0] - dy * (1 - b_[1]))
        mesh.wall("concrete", pa, pb, z0, z1, z0, z1)
    mesh.quad("concrete", (px + nx * ho - dx, py + ny * ho - dy, zb + 0.3 + clear),
              (px + nx * ho, py + ny * ho, zb + 0.3 + clear),
              (px - nx * ho, py - ny * ho, zb + 0.3 + clear),
              (px - nx * ho - dx, py - ny * ho - dy, zb + 0.3 + clear))
    mesh.obox("stone.coping", px - dx * 0.5, py - dy * 0.5, zt, 1.3, 2 * hw + 0.3, 0.25, dx, dy)
    return Out(mesh=mesh)


def gather_vent(cx: Ctx, st) -> Piece:
    ring = st.footprint.exterior
    c = bbox_center(ring)
    inputs = {"st": dump(st), "ground_c": cx.ground.samples([c]), "origin": list(c)}
    return Piece(st.id, "street.vent", "vent", cx.tile_for(st.id, ring),
                 cx.keys.get(st.id, []), inputs)


@maker("vent", 1)
def make_vent(inp: dict) -> Out:
    st = inp["st"]
    g = inp["ground_c"][0] if inp.get("ground_c") else 0.0
    ring = ccw(st["footprint"]["exterior"])
    z0, z1 = st["z0_m"] + g, st["z1_m"] + g
    mesh = Mesh(inp["origin"])
    mesh.prism("concrete.dark", ring, z0, z1)
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        L = dist(a, b)
        if L < 2.0:
            continue
        ux, uy = unit(b[0] - a[0], b[1] - a[1])
        ox, oy = uy * 0.08, -ux * 0.08          # out of the wall
        z = z0 + 2.5
        while z < z1 - 1.0:
            p = (a[0] + ux * 0.6 + ox, a[1] + uy * 0.6 + oy, z)
            q = (b[0] - ux * 0.6 + ox, b[1] - uy * 0.6 + oy, z)
            mesh.beam("steel.painted", p, q, 0.12, 0.08)
            z += 0.6
    c = inp["origin"]
    xs = [p[0] for p in ring]
    r = max(min((max(xs) - min(xs)) / 5.0, 2.2), 0.8)
    for k in (-1.0, 1.0):
        mesh.cylinder("steel", c[0] + k * r * 1.2, c[1], r, z1, z1 + 1.2, n=12)
    return Out(mesh=mesh)
