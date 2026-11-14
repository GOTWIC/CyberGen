"""The fixtures under the lights stage 2 draws none for (dlss_lamps_flicker, after Swagnik's
walk of Delta: "quite a few ghost lamps, ie the light is there but theres no lamppost").

AT1 and AT2 light what M6 leaves dark on fixtures they asked of stage 2 (`emitters.py`'s third
and fourth asks: `Light.mount` `pole`, `mast_arm`, `wall`, `mast`, `roof`), which stage 2
never drew: in Delta 9,841 lights hung in the air. The plan now draws each one from AG8's own
prop variants, so the style is the district's (`assetgen.props.styles`):

- **pole** (a junction's corner pole, a highway's or ramp's column, a service road's, a
  pedestrian street's or a footbridge's post, a fill light at a road or a sidewalk): an AG8
  street light standing at the pole's foot (`spot(..., foot=)`), turned so its arm reaches
  toward the light's head, scaled so its lens is at the head's height; the variant whose arm
  then reaches nearest the head (a post top's where the head is over its foot), a twin column
  in a median two back to back;
- **mast_arm** (a traffic signal's): an AG8 street light at the signal's own foot, its arm
  reaching over the junction (the signal itself AG8 draws already);
- **wall** (an alley's wall pack, a fill light in an alley): an AG8 wall light on the facade
  at the alley's edge (the nearest mass at the light's height within `WALL_REACH_M`, behind
  it), else a post just off the alley;
- **mast** (a port yard's or an apron's high mast): AG8's heavy street light's mast form,
  scaled to the mast's height;
- **roof** (a crown flood or an uplight): AG8's heavy wall light's flood form, tilted up, on
  the setback, podium or ground it stands on, or on an outrigger (AG8's bracket) from its
  facade where it stands out in the air.

Each light then moves onto its fixture's lens (at most a meter or two: the variant's own arm
and height), so the light comes out of the drawn head; the lux check runs on the moved
lights. A fixture stands clear of every vehicle carriageway, junction and crosswalk at its
height as AG8's props do (`assetgen.props.gather._Fit`: the variant's footprint 2 m up, the
pavement map's faces; a mast arm's at its signal's crosswalk, as the signal's), pushed back
from the road a quarter meter at a time; a light whose fixture finds no clear spot is left
out (`dropped`).

Which stage: atmosgen's (layer 3). The lights exist only in its plan (stage 3 reads stage 2,
not the other way), so the plan is what knows where a fixture goes; assetgen drawing them
would make stage 2 read stage 3's plan. The fixtures are only AG8's meshes placed again: the
plan writes `fixtures.json` and `unreal_contribution.fixtures.json` (an entry per 128 m cell,
`atmos.fixtures.<tile>.<quarter>`, instanced parts in AG8's `props` part, so the exporter
imports AG8's own meshes and materials once), which `citygen unreal` layers with stage 2's
contributions where the plan is delivered.

What needs none: lights on what stage 2 draws (an M6 lamp, a sign, a shopfront, AG10's
soffit, AG7's tunnel strips) and lights on structures (beacons and searchlights on roofs and
masts, a crane's boom floods, a launch tower's, an airfield's ground lights, a platform's
downlights under its station's roof or a deck's soffit). The check (`check`) holds every light
to something under or behind it at its height: its fixture's lens, or the structure.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import presets as P

STREET, WALL, BRACKET = "street_light", "wall_light", "bracket"
FAMILY_GLB = {k: f"props/variants/{k}.glb" for k in (STREET, WALL, BRACKET)}
STYLE_ORDER = ("civic", "heavy", "sleek", "old", "neon")
POST_A_M = 0.45              # a head this near its foot is a post top's
CLUSTER_MM = 600             # lens vertices this near one another are one head
POLE_SCALE = (0.55, 1.9)     # a street light scaled at most this far to reach its head
MAST_SCALE = (2.0, 5.5)      # ... a high mast
NEAR_M = 0.5                 # variants whose arm misses the head by this more than the best
                             # are left out of the hashed pick
PUSH_STEP_M = 0.25           # a fixture on a carriageway moves back this much at a time
PUSH_MAX_M = 3.0
WALL_REACH_M = 3.0           # a wall pack's facade at most this far behind it
WALL_REACH = 0.2             # AG8's wall light frame: the wall at x = -0.2
FLOOD_HEAD_S = 2.0           # a flood's head: AG8's heavy wall light's flood form, scaled
FLOOD_FORMS = (2, 4)         # ... its flood form's variants (`variants.WALL_FORMS["heavy"]`)
LENS_TOL_M = 0.02            # the check: a fixture's lens within this of its light
STAND_TOL_M = 2.0            # ... a light on a structure within this of it (a searchlight
                             # 1.5 m over its roof, a beacon 0.4 m off a corner)


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


class Kit:
    """AG8's variants measured once: each one's heads (the centroids of its `light.*` slots'
    vertices, grouped within `CLUSTER_MM`), in its own frame (m)."""

    def __init__(self):
        self._lens: dict = {}

    def lens(self, kind: str, style: str, k: int) -> list[tuple[float, float, float]]:
        key = (kind, style, k)
        if key not in self._lens:
            from assetgen.props.variants import make
            m = make(kind, style, k)
            pts = sorted(p for name, sl in sorted(m.slots.items()) if name.startswith("light.")
                         for p in sl.pos)
            cl: list[list] = []
            for p in pts:
                for c in cl:
                    s = c[4]
                    if (p[0] - s[0]) ** 2 + (p[1] - s[1]) ** 2 + (p[2] - s[2]) ** 2 < \
                            CLUSTER_MM ** 2:
                        c[0] += p[0]
                        c[1] += p[1]
                        c[2] += p[2]
                        c[3] += 1
                        break
                else:
                    cl.append([p[0], p[1], p[2], 1, p])
            self._lens[key] = [(c[0] / c[3] / 1000.0, c[1] / c[3] / 1000.0,
                                c[2] / c[3] / 1000.0) for c in cl]
        return self._lens[key]


class _RawFit:
    """`gather._Fit`'s carriageways where a model has no pavement map (a partial model): each
    vehicle road's carriageway (its width less its sidewalks, round its centerline), the
    junctions' polygons, the crosswalks; the same `tree`, `rows`, `hull` and rule."""

    def __init__(self, m: dict):
        import shapely
        from shapely.geometry import LineString, Polygon
        from assetgen.props.gather import FIT_CLEAR_M
        shapes, rows = [], []
        for s in sorted(m.get("road_segments", []) or [], key=lambda s: s["id"]):
            if s.get("road_class") in ("pedestrian", "footbridge") or \
                    len(s.get("centerline") or []) < 2:
                continue
            sw = (s.get("cross_section") or {}).get("sidewalk_m") or [0.0, 0.0]
            w = float(s.get("width_m", 8.0)) - sum(float(v) for v in sw)
            if w <= 0.2:
                continue
            ln = LineString([p[:2] for p in s["centerline"]])
            g = ln.buffer(w / 2.0, cap_style="flat")
            med = float((s.get("cross_section") or {}).get("median_m") or 0.0)
            if med > 0.2:
                g = g.difference(ln.buffer(med / 2.0, cap_style="flat"))
            shapes.append(g)
            rows.append(("face", [(p[0], p[1], p[2] if len(p) > 2 else 0.0)
                                  for p in s["centerline"]], None))
        for j in sorted(m.get("junctions", []) or [], key=lambda j: j["id"]):
            ring = (j.get("polygon") or {}).get("exterior") or []
            if len(ring) >= 3:
                shapes.append(Polygon(ring))
                rows.append(("face", [(p[0], p[1], 0.0) for p in ring], None))
        for c in sorted(m.get("crosswalks", []) or [], key=lambda c: c["id"]):
            ln = c.get("line") or []
            if len(ln) >= 2:
                cl = LineString([p[:2] for p in ln])
                shapes.append(cl.buffer(float(c.get("width_m", 3.0)) / 2.0, cap_style="flat"))
                rows.append(("xwalk", cl, [(0.0, 0.0), (1.0e9, 0.0)]))
        self.shapes = [g.buffer(-FIT_CLEAR_M) for g in shapes]
        self.rows = rows
        self.tree = shapely.STRtree(self.shapes) if shapes else None
        self.hulls: dict = {}

    def hull(self, kind: str, style: str, k: int):
        from assetgen.props.gather import _Fit
        return _Fit.hull(self, kind, style, k)


class Fixtures:
    """Places a fixture under every light of the plan whose mount stage 2 does not draw
    (module docstring), moves each light onto its fixture's lens, and drops a light whose
    fixture finds no clear spot."""

    def __init__(self, pl):
        from shapely import STRtree
        from shapely.geometry import Polygon
        from assetgen.props import styles as ST
        from assetgen.props.gather import _Fit
        from assetgen.streets import pave as PV
        from assetgen.streets.ctx import Ground
        self.pl = pl
        self.c = pl.c
        self.ST = ST
        self.kit = Kit()
        try:
            model = self.c.model()
        except Exception:                   # noqa: BLE001 (a partial model: a test's)
            model = None
        if model is not None and getattr(model, "pavement", None):
            gd = Ground(model)
            PI = PV.Index(model, gd)
            self.fit = _Fit(model, PI)
            self.clear_from = "pavement map"
        else:
            # (no pavement map: the carriageways from the segments' cross-sections)
            self.fit = _RawFit(self.c.m)
            self.clear_from = "segments"
        # the building masses at their heights (absolute), for wall packs and the check
        self.masses: list[tuple] = []
        for b in sorted(self.c.buildings.values(), key=lambda b: b["id"]):
            base = self.c.ground_at_base(b)
            for m in b.get("masses") or []:
                ext = (m.get("footprint") or {}).get("exterior") or []
                if len(ext) < 3:
                    continue
                g = Polygon(ext, [h for h in (m.get("footprint") or {}).get("holes") or []
                                  if len(h) >= 3])
                if not g.is_valid:
                    g = g.buffer(0)
                if g.is_empty:
                    continue
                self.masses.append((g, base + float(m.get("z0_m", 0.0)),
                                    base + float(m.get("z1_m", 0.0)), b["id"]))
        for e in sorted(self.c.m.get("site_elements", []) or [], key=lambda e: e["id"]):
            fp = (e.get("footprint") or {}).get("exterior") or [[0.0, 0.0]]
            base = self.c.ground(fp[0][0], fp[0][1]) + float(e.get("z_m", 0.0))
            for m in e.get("masses") or []:
                ext = (m.get("footprint") or {}).get("exterior") or []
                if len(ext) < 3:
                    continue
                g = Polygon(ext)
                if not g.is_valid:
                    g = g.buffer(0)
                if g.is_empty:
                    continue
                self.masses.append((g, base + float(m.get("z0_m", 0.0)),
                                    base + float(m.get("z1_m", 0.0)), e["id"]))
        self.mtree = STRtree([m[0] for m in self.masses]) if self.masses else None
        self.stations = {}
        for st in self.c.m.get("stations", []) or []:
            ext = (st.get("footprint") or {}).get("exterior") or []
            if len(ext) >= 3:
                g = Polygon(ext)
                self.stations[st["id"]] = g if g.is_valid else g.buffer(0)
        self.out: list[dict] = []
        self.dropped: dict[str, int] = {}
        self.moved: list[float] = []
        self.report: dict = {}

    # -- helpers -------------------------------------------------------------------------

    def style(self, did: str | None) -> str:
        arch = (self.c.districts.get(did or "") or {}).get("archetype")
        return self.ST.style_of(arch) if arch else "civic"

    def clear(self, kind: str, style: str, k: int, x: float, y: float, z: float, yaw: float,
              s: float, xwalk: bool = True) -> bool:
        """AG8's rule (`gather._Fit.clear`): the variant's footprint 2 m up, turned and
        scaled as placed, reaches at most 5 cm onto a vehicle carriageway, junction or (unless
        `xwalk` is False: a mast arm at its signal's crosswalk) a crosswalk at its height."""
        import shapely
        from assetgen.props.gather import FIT_Z_M, _z_along
        f = self.fit
        if f.tree is None:
            return True
        ring = f.hull(kind, style, k)
        if ring is None:
            return True
        a = math.radians(yaw)
        c, sn = math.cos(a), math.sin(a)
        poly = shapely.Polygon([(x + c * u * s - sn * v * s, y + sn * u * s + c * v * s)
                                for u, v in ring])
        for gi in sorted(f.tree.query(poly, predicate="intersects").tolist()):
            kind_, ln, zp = f.rows[gi]
            if kind_ == "xwalk" and not xwalk:
                continue
            if kind_ == "face":
                zt = min(ln, key=lambda q: ((q[0] - x) ** 2 + (q[1] - y) ** 2, q))[2]
            else:
                zt = _z_along(zp, ln.project(shapely.points(x, y)))
            if abs(zt - z) <= FIT_Z_M:
                return False
        return True

    def pick_pole(self, style: str, A: float, H: float, key: str, mast: bool = False):
        """The street light variant whose arm reaches nearest `A` from its foot with its lens
        `H` over it: (style, k, scale, (lx, ly, lz)) or None. Its own style first, the others
        only where it has none that fits."""
        from .plan import u
        order = ([style] + [s for s in STYLE_ORDER if s != style]) if not mast else \
            ["heavy"] + [s for s in STYLE_ORDER if s != "heavy"]
        lo, hi = MAST_SCALE if mast else POLE_SCALE
        for st in order:
            cands = []
            for k in range(self.ST.PROP_VARIANTS[STREET]):
                cl = self.kit.lens(STREET, st, k)
                if not cl:
                    continue
                cx = sum(c[0] for c in cl) / len(cl)
                cy = sum(c[1] for c in cl) / len(cl)
                cz = sum(c[2] for c in cl) / len(cl)
                post = all(math.hypot(c[0], c[1]) < 0.65 for c in cl)
                if mast or A < POST_A_M:
                    if not post:
                        continue
                elif len(cl) != 1 or cx < 0.5 or abs(cy) > 0.25:
                    continue
                if cz <= 0.5:
                    continue
                s = H / cz
                if not lo <= s <= hi:
                    continue
                miss = abs(s * math.hypot(cx, cy) - (0.0 if (mast or A < POST_A_M) else A))
                cands.append((round(miss, 3), k, s, (cx, cy, cz)))
            if cands:
                cands.sort()
                near = [c for c in cands if c[0] <= cands[0][0] + NEAR_M]
                miss, k, s, lens = near[min(int(u(key, "fixture") * len(near)), len(near) - 1)]
                return st, k, s, lens
        return None

    def add(self, L: dict, kind: str, style: str, k: int, pos, yaw: float, scale,
            role: str) -> dict:
        from .plan import tile_of
        node = self.ST.variant_name(kind, style, k)
        rec = {"id": f"{L['id']}.fixture{'' if role == 'main' else '.' + role}",
               "light_id": L["id"], "mount": L["mount"], "kind": kind, "role": role,
               "node": node, "glb": FAMILY_GLB[kind],
               "pos": [_r(pos[0]), _r(pos[1]), _r(pos[2])], "yaw": _r(yaw, 2),
               "scale": [_r(v, 4) for v in scale], "tile": tile_of(pos[0], pos[1])}
        self.out.append(rec)
        return rec

    def move(self, L: dict, lens) -> None:
        """The light onto its fixture's lens (its class's drop under it)."""
        drop = float(P.PHOTOMETRY[L["cls"]].get("drop_m", 0.0))
        nx, ny, nz = lens[0], lens[1], lens[2] - drop
        self.moved.append(math.dist((nx, ny, nz), L["pos"]))
        L["pos"] = [_r(nx), _r(ny), _r(nz)]
        L["_lens"] = [nx, ny, lens[2]]

    def lens_of(self, f: dict) -> tuple[float, float, float]:
        """A fixture's lens where it stands (its variant's heads' middle, turned, scaled and
        moved as the record places it), measured again from the variant."""
        _, kind, st, v = f["node"].split(".")
        cl = self.kit.lens(kind, st, int(v[1:]))
        lx = sum(c[0] for c in cl) / len(cl)
        ly = sum(c[1] for c in cl) / len(cl)
        lz = sum(c[2] for c in cl) / len(cl)
        sx, sy, sz = f["scale"]
        a = math.radians(f["yaw"])
        c, s = math.cos(a), math.sin(a)
        return (f["pos"][0] + c * lx * sx - s * ly * sy, f["pos"][1] + s * lx * sx + c * ly * sy,
                f["pos"][2] + lz * sz)

    def drop(self, L: dict, why: str) -> None:
        L["_drop"] = why
        self.dropped[why] = self.dropped.get(why, 0) + 1

    # -- by mount --------------------------------------------------------------------------

    def pole(self, L: dict, foot, mast: bool = False, arm: bool = False,
             deck: bool = False) -> None:
        """A street light standing at `foot` under the light (`deck`: on a raised road's
        parapet line, where it stands on the deck's edge: no carriageway test)."""
        drop = float(P.PHOTOMETRY[L["cls"]].get("drop_m", 0.0))
        hx, hy, hz = L["pos"][0], L["pos"][1], L["pos"][2] + drop
        fx, fy, fz = foot
        A = math.hypot(hx - fx, hy - fy)
        H = hz - fz
        st0 = "heavy" if mast else self.style(L.get("district_id"))
        if A >= POST_A_M and not mast:
            yaw = math.degrees(math.atan2(hy - fy, hx - fx))
            tries = [(-PUSH_STEP_M * i, 0.0) for i in range(int(PUSH_MAX_M / PUSH_STEP_M) + 1)]
        else:
            yaw = float(L["aim"][0])
            tries = [(0.0, 0.0)] + [(d * math.cos(math.radians(a)), d * math.sin(math.radians(a)))
                                    for d in (0.3, 0.6, 1.0, 1.5, 2.0)
                                    for a in range(0, 360, 45)]
        ux, uy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        for dx, dy in tries:
            if A >= POST_A_M and not mast:
                px, py = fx + ux * dx, fy + uy * dx         # (back from the road, along the arm)
                reach = A - dx
            else:
                px, py = fx + dx, fy + dy
                reach = 0.0
            ch = self.pick_pole(st0, reach, H, L["id"], mast)
            if ch is None:
                break
            st, k, s, (lx, ly, lz) = ch
            if deck or (arm and dx == 0.0):
                # (on a deck's parapet line; a mast arm's pole on its signal's own, which AG8
                # stands where its signal stands)
                ok = True
            else:
                ok = self.clear(STREET, st, k, px, py, fz, yaw, s)
            if ok:
                f = self.add(L, STREET, st, k, (px, py, fz), yaw, (s, s, s), "main")
                if deck:
                    f["deck"] = True
                if arm and dx == 0.0:
                    f["at_signal"] = True
                c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
                self.move(L, (px + c * lx * s - sn * ly * s, py + sn * lx * s + c * ly * s,
                              fz + lz * s))
                return
        self.drop(L, "mast: no fitting variant" if mast else
                  ("pole: no clear spot" if self.pick_pole(st0, A, H, L["id"], mast)
                   else "pole: no fitting variant"))

    def wall(self, L: dict) -> None:
        from shapely.geometry import Point
        from .plan import u
        drop = float(P.PHOTOMETRY[L["cls"]].get("drop_m", 0.0))
        hx, hy, hz = L["pos"][0], L["pos"][1], L["pos"][2] + drop
        yaw = float(L["aim"][0])                 # (into the alley: away from its wall)
        ax, ay = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        best = None
        if self.mtree is not None:
            p = Point(hx, hy)
            for i in sorted(self.mtree.query(p, predicate="dwithin",
                                             distance=WALL_REACH_M).tolist()):
                g, z0, z1, _ = self.masses[i]
                if not (z0 - 0.05 <= hz - 0.3 and hz + 0.3 <= z1 + 0.05):
                    continue
                d = g.exterior.distance(p) if not g.contains(p) else 0.0
                if best is None or (round(d, 4), i) < best[:2]:
                    best = (round(d, 4), i, g)
        if best is not None and not best[2].contains(Point(hx, hy)):
            from shapely.ops import nearest_points
            q = nearest_points(best[2].exterior, Point(hx, hy))[0]
            nx, ny = hx - q.x, hy - q.y
            d = math.hypot(nx, ny)
            if d > 0.05 and (nx * ax + ny * ay) / d > -0.2:
                nx, ny = nx / d, ny / d
                st = self.style(L.get("district_id"))
                k = min(int(u(L["id"], "fixture") * self.ST.PROP_VARIANTS[WALL]),
                        self.ST.PROP_VARIANTS[WALL] - 1)
                cl = self.kit.lens(WALL, st, k)
                if cl:
                    lx = sum(c[0] for c in cl) / len(cl)
                    ly = sum(c[1] for c in cl) / len(cl)
                    lz = sum(c[2] for c in cl) / len(cl)
                    wy = math.degrees(math.atan2(ny, nx))
                    ox, oy = q.x + nx * WALL_REACH, q.y + ny * WALL_REACH
                    oz = hz - lz
                    self.add(L, WALL, st, k, (ox, oy, oz), wy, (1.0, 1.0, 1.0), "main")
                    self.move(L, (ox + nx * lx - ny * ly, oy + ny * lx + nx * ly, hz))
                    return
        # no facade behind it: a post just off the alley, behind the light
        g = self.c.ground(hx, hy)
        for d in (0.6, 1.0, 1.5, 2.0, 2.5, 3.0):
            fx, fy = hx - ax * d, hy - ay * d
            ch = self.pick_pole(self.style(L.get("district_id")), 0.0, hz - g, L["id"])
            if ch is None:
                break
            st, k, s, (lx, ly, lz) = ch
            if self.clear(STREET, st, k, fx, fy, g, yaw, s):
                self.add(L, STREET, st, k, (fx, fy, g), yaw, (s, s, s), "main")
                c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
                self.move(L, (fx + c * lx * s - sn * ly * s, fy + sn * lx * s + c * ly * s,
                              g + lz * s))
                self.report["wall_posts"] = self.report.get("wall_posts", 0) + 1
                return
        self.drop(L, "wall: no facade and no clear spot")

    def flood(self, L: dict, hint: dict) -> None:
        """A flood's head (AG8's heavy wall light, flood form, tilted up toward its facade),
        on what it stands on or on an outrigger from its facade."""
        from .plan import u
        k = FLOOD_FORMS[min(int(u(L["id"], "fixture") * len(FLOOD_FORMS)),
                            len(FLOOD_FORMS) - 1)]
        cl = self.kit.lens(WALL, "heavy", k)
        lx = sum(c[0] for c in cl) / len(cl)
        ly = sum(c[1] for c in cl) / len(cl)
        lz = sum(c[2] for c in cl) / len(cl)
        s = FLOOD_HEAD_S
        x, y, z = L["pos"]
        yaw = float(L["aim"][0])                         # (+x toward its facade)
        c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        # (flipped upside down, sz -s: the lens tilts up; the lens on the light)
        ox = x - (c * lx * s - sn * ly * s)
        oy = y - (sn * lx * s + c * ly * s)
        oz = z + lz * s
        self.add(L, WALL, "heavy", k, (ox, oy, oz), yaw, (s, s, -s), "main")
        if hint.get("wall"):
            wx, wy = hint["wall"]
            d = math.hypot(ox - wx, oy - wy)
            if d > 0.3:
                st = self.style(L.get("district_id"))
                kb = min(int(u(L["id"], "bracket") * self.ST.PROP_VARIANTS[BRACKET]),
                         self.ST.PROP_VARIANTS[BRACKET] - 1)
                # (its wall plate on the facade, its arms out to the head; at the head's
                # middle height)
                self.add(L, BRACKET, st, kb, (ox, oy, oz - 0.15 * s),
                         math.degrees(math.atan2(oy - wy, ox - wx)), (d, s, s), "arm")
        self.move(L, (x, y, z))

    # -- the plan ----------------------------------------------------------------------------

    def place(self) -> dict:
        lights = self.pl.lights
        for L in lights:
            fx = L.get("_fx")
            mount = L["mount"]
            if mount in ("pole", "mast_arm") and fx and fx.get("foot"):
                self.pole(L, fx["foot"], arm=mount == "mast_arm", deck=bool(fx.get("deck")))
            elif mount == "mast" and fx and fx.get("mast"):
                self.pole(L, fx["foot"], mast=True)
            elif mount == "wall":
                self.wall(L)
            elif mount == "roof" and fx and fx.get("flood"):
                self.flood(L, fx)
        gone = {L["id"] for L in lights if L.get("_drop")}
        if gone:
            self.pl.lights[:] = [L for L in lights if L["id"] not in gone]
            self.out = [f for f in self.out if f["light_id"] not in gone]
        self.out.sort(key=lambda f: f["id"])
        mv = sorted(self.moved)
        self.report.update({
            "fixtures": len(self.out),
            "by_kind": {k: sum(1 for f in self.out if f["kind"] == k)
                        for k in (STREET, WALL, BRACKET)},
            "by_mount": {m: sum(1 for f in self.out if f["mount"] == m and f["role"] == "main")
                         for m in sorted({f["mount"] for f in self.out})},
            "styles": {s: sum(1 for f in self.out if f["node"].split(".")[2] == s)
                       for s in sorted({f["node"].split(".")[2] for f in self.out})},
            "dropped": dict(sorted(self.dropped.items())),
            "moved_m": ({"median": _r(mv[len(mv) // 2], 2),
                         "p95": _r(mv[int(0.95 * (len(mv) - 1))], 2), "max": _r(mv[-1], 2)}
                        if mv else None)})
        return self.report

    # -- the check -------------------------------------------------------------------------

    def check(self) -> dict:
        """Every light on something at its height (scope 4.1's asks met; dlss_lamps_flicker):
        a light on stage 2's own fixture (an M6 lamp, a sign, a shopfront, AG10's soffit,
        AG7's tunnel strip) as drawn; one on an asked mount on its fixture's lens (within
        `LENS_TOL_M`); a beacon or a searchlight on its structure (a mass's roof or facade
        within `STAND_TOL_M` at its height), a crane's or a launch tower's floods on it, an
        airfield's ground lights on the ground; a platform's or deck's downlight under a roof
        or slab (or underground); and every fixture clear of the carriageways."""
        from shapely.geometry import Point
        lens = {f["light_id"] for f in self.out if f["role"] == "main"}
        by_light = {f["light_id"]: f for f in self.out if f["role"] == "main"}
        occ = self.c.occluders()
        ok_mounts = ("prop", "sign", "facade", "soffit", "tunnel")
        bad: dict[str, list[str]] = {}
        held: dict[str, int] = {}

        def on_mass(x, y, z, owner=None, pad=STAND_TOL_M) -> bool:
            if self.mtree is None:
                return False
            p = Point(x, y)
            for i in self.mtree.query(p, predicate="dwithin", distance=pad).tolist():
                g, z0, z1, oid = self.masses[i]
                if owner is not None and oid != owner:
                    continue
                if z0 - pad <= z <= z1 + pad:
                    return True
            return False

        for L in self.pl.lights:
            m = L["mount"]
            x, y, z = L["pos"]
            why = None
            if m in ok_mounts:
                how = "stage 2"
            elif L["id"] in lens:
                drop = float(P.PHOTOMETRY[L["cls"]].get("drop_m", 0.0))
                how = "fixture"
                if math.dist(self.lens_of(by_light[L["id"]]), (x, y, z + drop)) > LENS_TOL_M:
                    why = f"{m}: off its fixture's lens"
            elif m in ("beacon", "roof"):
                how = "structure"
                if not on_mass(x, y, z):
                    why = f"{m}: no roof or facade at its height"
            elif m == "mast":
                how = "structure"
                if not on_mass(x, y, z, owner=L["owner_id"], pad=3.0):
                    why = "mast: not on its crane"
            elif m == "ground":
                how = "ground"
                if abs(z - self.c.ground(x, y)) > 2.0 and not on_mass(x, y, z):
                    why = "ground: off the ground"
            elif m == "canopy" and L["owner_id"] in self.stations and \
                    self.stations[L["owner_id"]].distance(Point(x, y)) < 0.5:
                how = "stage 2"                  # (its station's roof: AG5 draws stations)
            elif m == "canopy":
                how = "structure"
                b = None
                i = int(math.floor((x - occ.x0) / occ.cell))
                j = int(math.floor((y - occ.y0) / occ.cell))
                if 0 <= i < occ.nx and 0 <= j < occ.ny and math.isfinite(occ.bot[j, i]):
                    b = float(occ.bot[j, i])
                under = z < self.c.ground(x, y) - 0.5
                covered = (b is not None and z - 0.5 <= b <= z + 3.5) or under or \
                    on_mass(x, y, z, pad=0.5)
                if not covered:
                    why = "canopy: nothing over it"
            else:
                how = "none"
                why = f"{m}: no fixture"
            held[how] = held.get(how, 0) + 1
            if why:
                bad.setdefault(why, []).append(L["id"])
        # every fixture clear of the carriageways (re-measured where it stands)
        blocked = []
        for f in self.out:
            if f["kind"] != STREET:
                continue
            if f.get("deck") or f.get("at_signal"):
                continue
            _, _, st, v = f["node"].split(".")
            if not self.clear(STREET, st, int(v[1:]), f["pos"][0], f["pos"][1], f["pos"][2],
                              f["yaw"], f["scale"][0], xwalk=not f.get("at_signal")):
                blocked.append(f["id"])
        n_bad = sum(len(v) for v in bad.values())
        return {"ok": n_bad == 0 and not blocked, "lights": len(self.pl.lights),
                "held_by": dict(sorted(held.items())),
                "unsupported": n_bad,
                "why": {k: {"count": len(v), "first": sorted(v)[:5]}
                        for k, v in sorted(bad.items())},
                "fixtures": len(self.out), "blocked": len(blocked),
                "blocked_first": sorted(blocked)[:5],
                "dropped": dict(sorted(self.dropped.items()))}

    # -- outputs -----------------------------------------------------------------------------

    def contribution(self, city: str, assets: Path | None) -> dict:
        """The fixtures as a contribution in stage 2's form (an entry per 128 m cell, its
        instanced parts by variant node, transforms from the cell's middle; AG8's `props`
        part, so its meshes and materials are AG8's), layer 3."""
        cells: dict[tuple[int, int], list[dict]] = {}
        for f in self.out:
            ix, iy = int(math.floor(f["pos"][0] / 128.0)), int(math.floor(f["pos"][1] / 128.0))
            cells.setdefault((ix, iy), []).append(f)
        tris = {}
        if assets is not None and (assets / "props" / "manifest.json").is_file():
            man = json.loads((assets / "props" / "manifest.json").read_text(encoding="utf-8"))
            for fam in (man.get("families") or {}).values():
                for node, r in (fam.get("meshes") or {}).items():
                    tris[node] = int(r.get("triangles", 0))
        quarters = {(0, 0): "sw", (1, 0): "se", (0, 1): "nw", (1, 1): "ne"}
        entries = []
        for (ix, iy) in sorted(cells):
            tx, ty = ix // 2, iy // 2
            tile = f"t{tx:+03d}{ty:+03d}"
            name = f"{tile}.{quarters[(ix - 2 * tx, iy - 2 * ty)]}"
            cx, cy = (ix + 0.5) * 128.0, (iy + 0.5) * 128.0
            parts: dict[str, dict] = {}
            for f in sorted(cells[(ix, iy)], key=lambda f: f["id"]):
                p = parts.setdefault(f["node"], {
                    "asset": f["node"].replace(".", "_"), "glb": f["glb"], "kind": f["node"],
                    "node": f["node"], "nanite": True, "ids": [], "xforms": [],
                    "triangles": tris.get(f["node"], 0)})
                if f["kind"] != STREET:
                    p["collision"] = {"none": True}
                p["ids"].append(f["id"])
                p["xforms"].append([_r(f["pos"][0] - cx, 2), _r(f["pos"][1] - cy, 2),
                                    _r(f["pos"][2], 2), _r(f["yaw"], 2)] +
                                   [_r(v, 3) for v in f["scale"]])
            plist = []
            for node in sorted(parts):
                p = parts[node]
                p["count"] = len(p["xforms"])
                plist.append(p)
            e = {"key": f"atmos.fixtures.{name}", "kind": "prop.fixture", "tile": tile,
                 "pivot": [cx, cy, 0.0], "yaw_deg": 0.0, "replaces": [],
                 "tags": {"cg.tile": tile, "cg.type": "prop.fixture"},
                 "instanced_triangles": sum(p["triangles"] * p["count"] for p in plist),
                 "parts": plist}
            e["hash"] = _sha16(e)
            entries.append(e)
        return {"version": 1, "layer": 3, "stage": "atmosgen", "part": "props",
                "generator": "atmosgen fixtures (dlss_lamps_flicker)", "city": city,
                "frame": "citygen x east, y north, z up, m; parts from the entry's pivot; "
                         "Unreal (100 x, -100 y, 100 z) cm, yaw -> -yaw",
                "entries": entries}


def _sha16(data) -> str:
    import hashlib
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def finish(lights: list[dict]) -> None:
    """Every light's record as written: its private keys gone, its tile and hash again (a
    light moved onto its fixture)."""
    from .plan import dumps, sha, tile_of
    for L in lights:
        moved = "_lens" in L
        for k in ("_fx", "_lens", "_drop"):
            L.pop(k, None)
        if moved:
            L.pop("hash", None)
            L["tile"] = tile_of(L["pos"][0], L["pos"][1])
            L["hash"] = sha(dumps(L))[:16]
