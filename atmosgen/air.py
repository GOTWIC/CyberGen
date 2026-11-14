"""AT4: the air (scope 6.3): fog and smog volumes and steam and smoke emitters, keyed by what
they lie over or rise from, the height and volumetric fog of the look, light shafts.

- **Volumes** (`Air.volumes`): ellipsoids (Unreal's local fog volumes) of mist over the
  canals, basins and rivers at night (M16's water, pieces along its line as wide as it is
  there), smog over industry and the port (the industrial and spaceport districts and their
  megasites, a coarse grid of puffs), haze under M14's decks (from the ground to the soffit)
  and in road tunnels and underpasses (along their covered stretch); each as dense as its
  kind times its district's haze and danger (decision 12.5: thicker where danger is) and its
  schedule's share at the hour.
- **Emitters** (`Air.emitters`): steam from AG7's manholes and drains (read from the street
  packs: what stage 2 drew) and M9's tunnel ventilation buildings, exhaust from M3's roof
  mechanical units (AG4's roof equipment), cooking from M6's food stalls and kiosks, smoke
  from chimneys on industrial roofs and stove pipes on shanty stacks (a fixture asked of
  stage 2, `emitters.py`'s fifth ask); the share of each that steams from its district's grit.
- **Settings** (`settings`): the height fog and volumetric fog of the look and weather by the
  hour (thicker at night), each light kind's volumetric scattering (light shafts from the
  strong lights; none from the small ones), the live sets, the engine settings the runtime
  runs with.
- **The check** (`check`, scope 8): every emitter on its source and out of every building
  mass but its own roof's, every volume over its water or in its district or deck, the
  budgets per 256 m tile.

Deterministic as the rest of the plan: draws are blake2b hashes of ids, coordinates on the
millimeter grid, the packs read in sorted order.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np

from . import presets as P

PACK_MATERIALS = {"manhole": "manhole", "grate": "drain"}


# --- reading AG7's manholes and drains -------------------------------------------------------

def _quat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _local(n: dict) -> np.ndarray:
    if "matrix" in n:
        return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
    M = np.eye(4)
    M[:3, :3] = _quat(n.get("rotation", [0, 0, 0, 1])) @ np.diag(n.get("scale", [1, 1, 1]))
    M[:3, 3] = n.get("translation", [0.0, 0.0, 0.0])
    return M


_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32,
       5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
G2C = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0]])


def pack_details(path: Path, materials=tuple(PACK_MATERIALS)) -> list[tuple[str, str, list]]:
    """The details of one street pack drawn in `materials` (AG7's `manhole` and `grate`
    decals): [(piece id, material, (n, 3) world vertices in citygen's frame)] per primitive.
    Reads only those primitives' accessors (as AG14's `fit.glb`, filtered)."""
    data = Path(path).read_bytes()
    if len(data) < 20:
        return []
    jl, = struct.unpack_from("<I", data, 12)
    doc = json.loads(data[20:20 + jl].decode("utf-8"))
    off = 20 + jl
    binary = b""
    if off + 8 <= len(data):
        bl, = struct.unpack_from("<I", data, off)
        binary = data[off + 8:off + 8 + bl]
    mats = [m.get("name", "") for m in doc.get("materials", [])]
    want = {i for i, n in enumerate(mats) if n in materials}
    if not want:
        return []

    def acc(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        dt = np.dtype(_CT[a["componentType"]])
        n = _NC[a["type"]]
        stride = v.get("byteStride")
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        if stride and stride != dt.itemsize * n:
            raw = np.frombuffer(binary, dtype=np.uint8, count=stride * a["count"],
                                offset=start).reshape(a["count"], stride)
            arr = raw[:, :dt.itemsize * n].copy().view(dt).reshape(a["count"], n)
        else:
            arr = np.frombuffer(binary, dtype=dt, count=a["count"] * n,
                                offset=start).reshape(a["count"], n)
        arr = arr.astype(np.float64)
        if a.get("normalized") and dt != np.float32:
            arr = arr / float(np.iinfo(dt).max)
        return arr

    nodes = doc.get("nodes", [])
    children = set()
    for n in nodes:
        children.update(n.get("children", []))
    out = []
    stack = [(i, np.eye(4), nodes[i].get("name", "")) for i in range(len(nodes))
             if i not in children]
    while stack:
        i, parent, root = stack.pop()
        n = nodes[i]
        W = parent @ _local(n)
        if "mesh" in n and not (n.get("extensions") or {}).get("EXT_mesh_gpu_instancing"):
            for p in doc["meshes"][n["mesh"]]["primitives"]:
                if p.get("material") not in want or "POSITION" not in p["attributes"]:
                    continue
                pos = acc(p["attributes"]["POSITION"])
                Q = (np.c_[pos, np.ones(len(pos))] @ (G2C @ W).T)[:, :3]
                out.append((root, mats[p["material"]], Q))
        for c in n.get("children", []):
            stack.append((c, W, root))
    return out


def disks(Q: np.ndarray, reach: float = 1.2) -> list[tuple[float, float, float]]:
    """The separate small decals in one primitive's vertices (a manhole's 0.8 m 12-gon, a
    drain's 0.9 x 0.4 m grate; AG7 sets them metres apart): vertices grouped within `reach`
    (past a decal's own span) of a group's first, each group's middle and top, in (x, y)
    order."""
    order = np.lexsort((np.round(Q[:, 1], 3), np.round(Q[:, 0], 3)))
    groups: list[list] = []
    for k in order:
        x, y, z = Q[k]
        for g in groups:
            if (g[0] - x) ** 2 + (g[1] - y) ** 2 <= reach * reach:
                g[3].append((x, y, z))
                break
        else:
            groups.append([x, y, z, [(x, y, z)]])
    out = []
    for g in groups:
        a = np.array(g[3])
        out.append((float(a[:, 0].mean()), float(a[:, 1].mean()), float(a[:, 2].max())))
    return sorted(out, key=lambda p: (round(p[0], 3), round(p[1], 3)))


def street_details(build: Path) -> dict[str, list[tuple[str, tuple]]]:
    """AG7's manholes and drains of a build, from its street packs: {piece id: [(mount,
    (x, y, z)), ...]} (mount `manhole` or `drain`); {} without packs."""
    d = Path(build) / "assets" / "streets"
    out: dict[str, list] = {}
    for f in sorted(d.glob("t*.glb")) if d.is_dir() else []:
        for root, mat, Q in pack_details(f):
            for p in disks(Q):
                out.setdefault(root, []).append((PACK_MATERIALS[mat], p))
    for k in out:
        out[k].sort(key=lambda e: (e[0], round(e[1][0], 3), round(e[1][1], 3)))
    return out


# --- the air -------------------------------------------------------------------------------

def _strip(g):
    """A polygon's largest part (a GEOS result may be a collection)."""
    if g.is_empty:
        return g
    if g.geom_type == "Polygon":
        return g
    parts = [q for q in getattr(g, "geoms", []) if q.geom_type == "Polygon"]
    return max(parts, key=lambda q: q.area) if parts else g


class Air:
    def __init__(self, plan):
        from . import plan as PL
        self.PL = PL
        self.p = plan
        self.c = plan.c
        self.volumes: list[dict] = []
        self.emitters: list[dict] = []
        self.sources: dict[str, tuple] = {}         # emitter id -> (kind, geometry) checked
        self.report: dict = {"skipped": {}}

    # -- records --

    def _density(self, kind: str, did: str | None) -> float:
        md = self.p.mood(did)
        a, b = P.HAZE_DANGER
        return P.VOLUMES[kind]["density"] * float(md.get("haze", 1.0)) * \
            (a + b * float(md.get("danger", 0.5)))

    def vol(self, *, owner: str, kind: str, k: int, did: str | None, center, extent,
            yaw: float, density: float | None = None) -> dict:
        PL = self.PL
        v = P.VOLUMES[kind]
        d = self._density(kind, did) if density is None else density
        rec = {"id": f"{owner}.{kind}{k:03d}", "owner_id": owner, "kind": kind,
               "district_id": did, "tile": PL.tile_of(center[0], center[1]),
               "center": [PL.mm(c) for c in center], "extent": [PL.mm(e) for e in extent],
               "yaw_deg": PL.mm(((yaw + 180.0) % 360.0) - 180.0),
               "density": round(max(0.0005, d), 4),
               "floor": v["floor"], "phase_g": v["phase_g"], "glow": v["glow"],
               "albedo": PL.hex_linear(v["albedo"]), "schedule": v["schedule"]}
        rec["hash"] = PL.sha(PL.dumps(rec))[:16]
        self.volumes.append(rec)
        return rec

    def emit(self, *, owner: str, mount: str, k: int | None, did: str | None, pos,
             source: str = "derived", rise: float | None = None,
             width: float | None = None) -> dict | None:
        PL = self.PL
        e = P.EMITTERS[mount]
        eid = f"{owner}.{mount}" if k is None else f"{owner}.{mount}{k:02d}"
        a, b = e["share"]
        grit = float(self.p.mood(did).get("grit", 0.5))
        if PL.u(eid, "air") >= a + b * grit:
            self.skip(f"{mount}: not steaming (its district's grit)")
            return None
        # (a plume whose foot another mass or a deck slab stands over: a roof unit under a
        # tower's overhang, a drain under a straddling building's floor)
        if bool(self.c.occluders().blocked(np.array([pos[0]]), np.array([pos[1]]),
                                           np.array([pos[2] + 0.3]))[0]):
            self.skip(f"{mount}: under a building")
            return None
        rec = {"id": eid, "owner_id": owner, "kind": e["kind"], "mount": mount,
               "district_id": did, "tile": PL.tile_of(pos[0], pos[1]),
               "pos": [PL.mm(c) for c in pos],
               "width_m": PL.r3(e["width_m"] if width is None else width),
               "rise_m": PL.r3((e["rise_m"] if rise is None else rise) *
                               (0.8 + 0.4 * PL.u(eid, "rise"))),
               "rate": PL.r3(e["rate"] * (0.75 + 0.25 * PL.u(eid, "rate"))),
               "color": PL.hex_linear(e["albedo"]), "schedule": e["schedule"],
               "source": source}
        rec["hash"] = PL.sha(PL.dumps(rec))[:16]
        self.emitters.append(rec)
        return rec

    def skip(self, why: str) -> None:
        s = self.report["skipped"]
        s[why] = s.get(why, 0) + 1

    # -- volumes --

    def mist(self) -> None:
        """Mist over the water at night: the rivers, the separation channels and delta
        branches, and the canals and basins (M16's bodies), in pieces `step_m` along each
        body's line, as wide as the body there (wider in pieces across), `height_m` thick over
        its surface."""
        from shapely import contains_xy
        from shapely.geometry import LineString, Polygon
        v = P.VOLUMES["mist"]
        bodies = []
        for key in ("rivers", "channels", "waterways"):
            for w in self.c.m.get(key, []) or []:
                if key == "waterways" and (w.get("kind") not in P.MIST_KINDS or
                                           w.get("ornamental")):
                    continue
                bodies.append(w)
        n_bodies = 0
        for w in sorted(bodies, key=lambda w: w["id"]):
            ext = (w.get("polygon") or {}).get("exterior") or []
            line = [q[:2] for q in (w.get("centerline") or [])]
            if len(ext) < 3 or len(line) < 2:
                continue
            g = Polygon(ext, [h for h in (w.get("polygon") or {}).get("holes") or []
                              if len(h) >= 3])
            if not g.is_valid:
                g = _strip(g.buffer(0))
            if g.is_empty or g.area < P.MIST_MIN_AREA_M2:
                continue
            surf = self._surface_of(w)
            ln = self.PL.Line(line)
            if ln.L < v["step_m"] * 0.5:
                continue
            n = max(1, int(round(ln.L / v["step_m"])))
            st = ln.L / n
            k = 0
            for i in range(n):
                x, y, _, tx, ty = ln.at(st * (i + 0.5))
                nx, ny = -ty, tx
                far = 2000.0
                cut = g.intersection(LineString([(x - nx * far, y - ny * far),
                                                 (x + nx * far, y + ny * far)]))
                segs = [s for s in getattr(cut, "geoms", [cut]) if s.geom_type == "LineString"
                        and not s.is_empty]
                if not segs:
                    continue
                from shapely.geometry import Point
                seg = min(segs, key=lambda s: s.distance(Point(x, y)))
                (ax, ay), (bx, by) = seg.coords[0], seg.coords[-1]
                width = math.hypot(bx - ax, by - ay)
                if width < v["min_w_m"]:
                    continue
                mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                parts = max(1, math.ceil(width / v["max_w_m"]))
                pw = width / parts
                yaw = math.degrees(math.atan2(ty, tx))
                for j in range(parts):
                    f = (j + 0.5) / parts - 0.5
                    cx, cy = mx + (bx - ax) * f, my + (by - ay) * f
                    if not contains_xy(g, cx, cy):
                        continue
                    did = self.c.district_at(cx, cy) or w.get("district_id")
                    self.vol(owner=w["id"], kind="mist", k=k, did=did,
                             center=(cx, cy, surf(st * (i + 0.5))),
                             extent=(0.75 * st, 0.55 * pw, v["height_m"]), yaw=yaw)
                    k += 1
            n_bodies += 1 if k else 0
        self.report["mist_bodies"] = n_bodies

    def _surface_of(self, w: dict):
        """A water body's surface along its centerline, s -> z: M16's `surface_m` on a flat
        city; on a terrain city (M13, where M16 leaves `surface_m` unset) the terrain's
        water level, along its profile where it has one (a river falling to its mouth). AT7:
        Cragmouth's plan failed on the unset surface."""
        s = (w.get("bed") or {}).get("surface_m")
        if s is not None:
            return lambda _s, z=float(s): z
        wl = next((r for r in (self.c.m.get("terrain") or {}).get("water_levels") or []
                   if r.get("water_id") == w["id"]), None)
        if wl is None:
            return lambda _s: 0.0
        prof = wl.get("profile") or []
        if len(prof) < 2:
            return lambda _s, z=float(wl.get("level_m", 0.0)): z
        ss = np.array([float(q["s"]) for q in prof])
        zz = np.array([float(q["z"]) for q in prof])
        return lambda _s: self.PL.mm(float(np.interp(_s, ss, zz)))

    def _grid(self, g, cell: float):
        """The cells of a `cell` grid (aligned on the city's origin) a polygon covers by a
        quarter or more: (middle x, y of the covered part, its share)."""
        from shapely.geometry import box
        x0, y0, x1, y1 = g.bounds
        out = []
        for i in range(math.floor(x0 / cell), math.ceil(x1 / cell)):
            for j in range(math.floor(y0 / cell), math.ceil(y1 / cell)):
                b = box(i * cell, j * cell, (i + 1) * cell, (j + 1) * cell)
                part = g.intersection(b)
                if part.is_empty or part.area < 0.25 * cell * cell:
                    continue
                c = part.centroid
                if not part.contains(c):
                    # (a concave piece's centroid outside it: a point inside instead)
                    c = part.representative_point()
                out.append((round(c.x, 3), round(c.y, 3), part.area / (cell * cell)))
        return out

    def smog(self) -> None:
        """Smog over industry and the port: the industrial and spaceport districts and the
        megasites that burn or ship (`presets.SMOG_SITES`), a grid of puffs `cell_m` wide."""
        from shapely.geometry import Polygon
        v = P.VOLUMES["smog"]
        areas = []
        for did in sorted(self.c.districts):
            d = self.c.districts[did]
            if d.get("archetype") in P.SMOG_ARCHETYPES:
                areas.append((did, did, (d.get("polygon") or {}).get("exterior") or []))
        for s in sorted(self.c.m.get("megasites", []) or [], key=lambda s: s["id"]):
            if s.get("kind") in P.SMOG_SITES and not any(
                    a[0] == s.get("district_id") for a in areas):
                areas.append((s["id"], s.get("district_id"),
                              (s.get("polygon") or {}).get("exterior") or []))
        for owner, did, ext in areas:
            if len(ext) < 3:
                continue
            g = Polygon(ext)
            if not g.is_valid:
                g = _strip(g.buffer(0))
            for k, (x, y, share) in enumerate(self._grid(g, v["cell_m"])):
                half = 0.5 * v["cell_m"] * (0.6 + 0.4 * share)
                z = self.c.ground(x, y) + 0.3 * v["height_m"]
                self.vol(owner=owner, kind="smog", k=k, did=did, center=(x, y, z),
                         extent=(1.25 * half, 1.25 * half, 0.5 * v["height_m"]),
                         yaw=360.0 * self.PL.u(owner, k, "smog.yaw"))

    def haze(self) -> None:
        """Haze under M14's decks: a grid of puffs over each slab, from the ground to its
        soffit."""
        from shapely.geometry import Polygon
        v = P.VOLUMES["haze"]
        for dk in sorted(self.c.m.get("decks", []) or [], key=lambda d: d["id"]):
            ext = (dk.get("polygon") or {}).get("exterior") or []
            if len(ext) < 3:
                continue
            g = Polygon(ext, [h for h in (dk.get("polygon") or {}).get("holes") or []
                              if len(h) >= 3])
            if not g.is_valid:
                g = _strip(g.buffer(0))
            under = float(dk.get("top_m", 9.0)) - float(dk.get("slab_m", 1.2))
            did = dk.get("district_id")
            for k, (x, y, share) in enumerate(self._grid(g, v["cell_m"])):
                half = 0.5 * v["cell_m"]
                self.vol(owner=dk["id"], kind="haze", k=k, did=did,
                         center=(x, y, self.c.ground(x, y) + 0.5 * under),
                         extent=(1.2 * half, 1.2 * half, 0.6 * under), yaw=0.0)

    def tunnel_haze(self) -> None:
        """Haze in the road tunnels and underpasses: pieces `step_m` along each one's covered
        stretch (its line less the open approaches past its portals), its clear height."""
        v = P.VOLUMES["tunnel_haze"]
        for t in sorted(self.c.m.get("tunnels", []) or [], key=lambda t: t["id"]):
            if t.get("kind") == "metro" or len(t.get("line") or []) < 2:
                continue
            ln = self.PL.Line(t["line"])
            s0, s1 = 0.0, ln.L
            for pt in t.get("portals") or []:
                # (each portal's open approach lies past it, toward the nearer end)
                s = self._s_of(ln, pt["position"])
                if s < ln.L / 2.0:
                    s0 = max(s0, s)
                else:
                    s1 = min(s1, s)
            if s1 - s0 < 10.0:
                continue
            n = max(1, int(round((s1 - s0) / v["step_m"])))
            st = (s1 - s0) / n
            clear = float(t.get("clear_m", 5.0))
            w = float(t.get("width_m", 8.0))
            did = self.p._district(t["id"], [q[:2] for q in t["line"]])
            for k in range(n):
                x, y, z, tx, ty = ln.at(s0 + st * (k + 0.5))
                self.vol(owner=t["id"], kind="tunnel_haze", k=k, did=did,
                         center=(x, y, self.c.ground(x, y) + z + 0.5 * clear),
                         extent=(0.7 * st, 0.5 * w, 0.6 * clear),
                         yaw=math.degrees(math.atan2(ty, tx)))

    @staticmethod
    def _s_of(ln, p) -> float:
        best, bs = 1e18, 0.0
        for i in range(len(ln.p) - 1):
            a, b = ln.p[i], ln.p[i + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1e-9
            f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            d = (a[0] + dx * f - p[0]) ** 2 + (a[1] + dy * f - p[1]) ** 2
            if d < best:
                best, bs = d, ln.cum[i] + f * math.sqrt(L2)
        return bs

    # -- emitters --

    def street(self) -> None:
        """Steam from AG7's manholes and drains, read from the street packs (what stage 2
        drew); a city without packs has none (they are AG7's)."""
        det = street_details(self.c.build)
        # (AT5's puddles read the drains again: kept on the city)
        self.c._street_details = det
        # (a road piece's: AG7 draws the manholes on its lanes and the drains at its curbs; a
        # sidewalk piece's grates are tree pits)
        det = {k: v for k, v in det.items() if k in self.c.segments}
        self.report["manholes"] = sum(1 for v in det.values() for e in v if e[0] == "manhole")
        self.report["drains"] = sum(1 for v in det.values() for e in v if e[0] == "drain")
        for piece in sorted(det):
            did = self.c.district_of(piece)
            kk = {"manhole": 0, "drain": 0}
            for mount, (x, y, z) in det[piece]:
                k = kk[mount]
                kk[mount] += 1
                d = did if did is not None else self.c.district_at(x, y)
                r = self.emit(owner=piece, mount=mount, k=k, did=d, pos=(x, y, z + 0.02),
                              source="assetgen")
                if r:
                    self.sources[r["id"]] = ("point", (x, y))

    def vents(self) -> None:
        """Steam from M9's tunnel ventilation buildings: from the middle of the roof."""
        from shapely.geometry import Polygon
        for s in sorted(self.c.m.get("structures", []) or [], key=lambda s: s["id"]):
            if s.get("kind") != "vent":
                continue
            ext = (s.get("footprint") or {}).get("exterior") or []
            if len(ext) < 3:
                continue
            g = Polygon(ext)
            c = g.centroid
            did = self.c.district_of(s["id"]) or self.c.district_at(c.x, c.y)
            w = min(4.0, 0.5 * math.sqrt(g.area))
            r = self.emit(owner=s["id"], mount="vent", k=None, did=did,
                          pos=(c.x, c.y, self.c.ground(c.x, c.y) + float(s.get("z1_m", 6.0))),
                          width=w)
            if r:
                self.sources[r["id"]] = ("poly", g)

    def roofs(self) -> None:
        """Exhaust from M3's roof mechanical units (AG4 draws them as roof equipment): from
        the middle of each unit's top."""
        from shapely.geometry import Polygon
        for bid in sorted(self.c.buildings):
            b = self.c.buildings[bid]
            items = [r for r in b.get("roof_items") or [] if r.get("kind") == "mechanical"]
            if not items:
                continue
            base = self.c.ground_at_base(b)
            did = b.get("district_id")
            for k, it in enumerate(items):
                x, y, z = (float(v) for v in it["position"])
                sx, sy, sz = (float(v) for v in it.get("size") or [2.0, 2.0, 2.0])
                r = self.emit(owner=bid, mount="roof", k=k, did=did,
                              pos=(x, y, base + z + sz), width=min(3.0, 0.4 * min(sx, sy)))
                if r:
                    a = math.radians(float(it.get("yaw_deg", 0.0)))
                    ca, sa = math.cos(a), math.sin(a)
                    ring = [(x + ca * u_ - sa * v_, y + sa * u_ + ca * v_)
                            for u_, v_ in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2),
                                           (sx / 2, sy / 2), (-sx / 2, sy / 2))]
                    self.sources[r["id"]] = ("poly", Polygon(ring))

    def stalls(self) -> None:
        """Cooking from M6's food stalls and kiosks: over the stall's counter."""
        for p in sorted(self.c.m.get("props", []), key=lambda p: p["id"]):
            kind = p["type"].split(".", 1)[1]
            if kind not in ("food_stall", "kiosk"):
                continue
            x, y, z = (float(v) for v in p["position"])
            did = self.c.district_of(p["id"])
            if kind == "kiosk" and self.PL.u(p["id"], "kiosk.food") >= 0.4:
                self.skip("kiosk: sells no food")
                continue
            r = self.emit(owner=p["id"], mount="stall", k=None, did=did,
                          pos=(x, y, self.c.ground(x, y) + z + 2.6))
            if r:
                self.sources[r["id"]] = ("point", (x, y))

    def chimneys(self) -> None:
        """Smoke from chimneys on industrial roofs (warehouses, sheds, yards and labs in the
        industrial, spaceport, megablock and old-town districts) and stove pipes on shanty
        stacks: a flue at a corner of the body's top, `CHIMNEY_M` over it, a fixture asked
        of stage 2."""
        PL = self.PL
        for bid in sorted(self.c.buildings):
            b = self.c.buildings[bid]
            t = b.get("type", "").split(".", 1)[-1]
            did = b.get("district_id")
            arch = (self.c.districts.get(did or "") or {}).get("archetype")
            if t in P.CHIMNEY_TYPES and arch in P.CHIMNEY_ARCHETYPES:
                mount, up = "chimney", P.CHIMNEY_M[1]
            elif t in P.STOVE_TYPES:
                mount, up = "stove", 1.2
            else:
                continue
            sh = PL.Shape(b, self.c.ground_at_base(b))
            if sh.crown is None:
                continue
            g = sh.crown[0]
            cs = PL.corners(g, 2.5 if mount == "chimney" else 1.0)
            if not cs:
                continue
            x, y = cs[int(PL.u(bid, mount, "corner") * len(cs)) % len(cs)]
            from shapely import contains_xy
            if not contains_xy(g, x, y):
                c = g.representative_point()
                x, y = c.x, c.y
            r = self.emit(owner=bid, mount=mount, k=None, did=did,
                          pos=(x, y, sh.base + sh.crown[2] + up),
                          width=P.CHIMNEY_M[0] if mount == "chimney" else None)
            if r:
                self.sources[r["id"]] = ("roof", (x, y, bid))

    # -- the settings, the check --

    def settings(self, filled: dict, sky: dict) -> dict:
        PL = self.PL
        ws = filled["weather_state"]
        al = P.AIR_LOOK[filled["preset"]]
        night = {int(r["hour"]): float(r["night"]) for r in sky.get("by_hour", [])}
        hours = [PL.r3(al["day_gain"] + (al["night_gain"] - al["day_gain"]) *
                       night.get(h, 1.0 if (h >= 20 or h < 6) else 0.0)) for h in range(24)]
        counts: dict[str, int] = {}
        for v in self.volumes:
            counts[f"volume.{v['kind']}"] = counts.get(f"volume.{v['kind']}", 0) + 1
        for e in self.emitters:
            counts[f"emitter.{e['mount']}"] = counts.get(f"emitter.{e['mount']}", 0) + 1
        counts["volumes"] = len(self.volumes)
        counts["emitters"] = len(self.emitters)
        return {"fog_density": PL.r3(float(ws["fog_density"]) * al["density"]),
                "fog_falloff": float(al.get("falloff", ws["fog_falloff"])),
                "fog_start_m": al["start_m"], "fog_albedo": PL.hex_linear(ws["fog_albedo"]),
                "fog_extinction": PL.r3(float(ws["volumetric"]) * al["extinction"]),
                "fog_view_m": al["view_m"],
                "phase_g": al["phase_g"], "fog_hours": hours,
                "scatter": dict(sorted(P.SCATTER.items())), "beam_fog_gain": P.BEAM_FOG_GAIN,
                "max_volumes": P.AIR_LIVE["volumes"], "volume_range_m": P.AIR_LIVE["volume_m"],
                "emitter_range_m": P.AIR_LIVE["emitter_m"], "puffs": dict(P.PUFFS),
                "steam_gain": P.STEAM_GAIN, "volume_glow": P.VOLUME_GLOW,
                # (cars_steam: the plumes shown at start, issue #223)
                "steam": bool(filled.get("steam", P.STEAM_ON)),
                "steam_glow": P.STEAM_GLOW, "steam_far": list(P.STEAM_FAR),
                "cvars": dict(sorted(P.AIR_CVARS.items())),
                "counts": dict(sorted(counts.items()))}

    def check(self) -> dict:
        """Scope 8's placement and budgets for the air: every emitter on its source (within
        `EMITTER_ON_M` of a manhole's or stall's middle, inside a roof unit's or vent's
        footprint, a chimney on its own roof) and out of every other building mass; every
        volume's middle over its water, in its district or megasite, on its deck or in its
        tunnel; at most `AIR_BUDGETS` per 256 m tile."""
        from shapely import contains_xy
        from shapely.geometry import Point, Polygon
        bad_e, bad_v = [], []
        occ = self.c.occluders()
        for e in self.emitters:
            x, y, z = e["pos"]
            src = self.sources.get(e["id"])
            if src is None:
                bad_e.append((e["id"], "no source"))
                continue
            kind, geo = src
            if kind == "point":
                if math.hypot(x - geo[0], y - geo[1]) > P.EMITTER_ON_M:
                    bad_e.append((e["id"], "off its source"))
                    continue
            elif kind == "poly":
                if geo.distance(Point(x, y)) > P.EMITTER_ON_M:
                    bad_e.append((e["id"], "off its source"))
                    continue
            # (the plume's foot inside a building mass or a deck slab: lux's occluders, the
            # masses eroded by half a meter)
            if bool(occ.blocked(np.array([x]), np.array([y]), np.array([z + 0.3]))[0]):
                bad_e.append((e["id"], "inside a building"))
        owners = {}
        for key in ("rivers", "channels", "waterways", "decks", "tunnels", "megasites"):
            for w in self.c.m.get(key, []) or []:
                owners[w["id"]] = w
        for v in self.volumes:
            x, y = v["center"][:2]
            o = owners.get(v["owner_id"])
            if v["kind"] in ("mist", "haze"):
                ext = ((o or {}).get("polygon") or {}).get("exterior") or []
                if len(ext) < 3 or not contains_xy(Polygon(ext).buffer(1.0), x, y):
                    bad_v.append((v["id"], "not over its water" if v["kind"] == "mist"
                                  else "not under its deck"))
            elif v["kind"] == "smog":
                ext = ((o or self.c.districts.get(v["owner_id"]) or {}).get("polygon")
                       or {}).get("exterior") or []
                if len(ext) < 3 or not contains_xy(Polygon(ext).buffer(1.0), x, y):
                    bad_v.append((v["id"], "not over its district"))
            elif v["kind"] == "tunnel_haze":
                from shapely.geometry import LineString
                ln = (o or {}).get("line") or []
                if len(ln) < 2 or Point(x, y).distance(LineString([q[:2] for q in ln])) > \
                        float((o or {}).get("width_m", 8.0)) / 2.0:
                    bad_v.append((v["id"], "not in its tunnel"))
        per_v: dict[str, int] = {}
        per_e: dict[str, int] = {}
        for v in self.volumes:
            per_v[v["tile"]] = per_v.get(v["tile"], 0) + 1
        for e in self.emitters:
            per_e[e["tile"]] = per_e.get(e["tile"], 0) + 1
        over = sorted([t for t, n in per_v.items() if n > P.AIR_BUDGETS["volumes_per_tile"]] +
                      [t for t, n in per_e.items() if n > P.AIR_BUDGETS["emitters_per_tile"]])
        ok = not bad_e and not bad_v and not over
        return {"ok": ok, "volumes": len(self.volumes), "emitters": len(self.emitters),
                "bad_emitters": len(bad_e), "bad_volumes": len(bad_v),
                "examples": [f"{i}: {w}" for i, w in (bad_e + bad_v)[:12]],
                "max_volumes_per_tile": max(per_v.values(), default=0),
                "max_emitters_per_tile": max(per_e.values(), default=0),
                "over_budget_tiles": over, "budgets": dict(P.AIR_BUDGETS)}


def check_text(c: dict) -> str:
    s = (f"air check: {'PASS' if c['ok'] else 'FAIL'}: {c['volumes']} volumes, "
         f"{c['emitters']} emitters; at most {c['max_volumes_per_tile']} volumes and "
         f"{c['max_emitters_per_tile']} emitters in a tile (budgets "
         f"{c['budgets']['volumes_per_tile']}, {c['budgets']['emitters_per_tile']})")
    if c["bad_emitters"] or c["bad_volumes"]:
        s += f"; {c['bad_emitters']} emitters and {c['bad_volumes']} volumes misplaced: " + \
            "; ".join(c["examples"])
    if c["over_budget_tiles"]:
        s += "; over budget: " + ", ".join(c["over_budget_tiles"])
    return s + "\n"


KIND_COLORS = {"mist": "#7fb2ff", "smog": "#c8a06a", "haze": "#9fe0b0", "tunnel_haze": "#e0d090",
               "steam": "#f2f6ff", "exhaust": "#a0b8d0", "cooking": "#ffb35c",
               "smoke": "#ff5a1f"}


def air_map(build, plan=None, out=None) -> dict:
    """`preview_air.png`: the plan's fog and smog volumes (their ellipses) and its steam and
    smoke emitters over the districts and the water."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse
    build = Path(build)
    pdir = Path(plan) if plan else build / "atmos"
    pl = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    m = json.loads((build / "city_model.json").read_text(encoding="utf-8"))
    x0, y0, x1, y1 = m["bounds"]
    fig = plt.figure(figsize=(10, 10.4), dpi=200)
    ax = fig.add_axes([0.02, 0.05, 0.96, 0.9])
    ax.set_facecolor("#05070d")
    for d in m["districts"]:
        ex = d["polygon"]["exterior"]
        ax.fill([p[0] for p in ex], [p[1] for p in ex], color="#111827", lw=0.4, ec="#2a3550")
    for key in ("rivers", "channels", "waterways"):
        for w in m.get(key, []) or []:
            ex = (w.get("polygon") or {}).get("exterior") or []
            if len(ex) >= 3:
                ax.fill([p[0] for p in ex], [p[1] for p in ex], color="#0b2a44", lw=0)
    n: dict[str, int] = {}
    for v in pl.get("volumes", []):
        k = v["kind"]
        n[k] = n.get(k, 0) + 1
        ax.add_patch(Ellipse(v["center"][:2], 2 * v["extent"][0], 2 * v["extent"][1],
                             angle=v["yaw_deg"], fc=KIND_COLORS[k], ec="none",
                             alpha=min(0.55, 8.0 * v["density"] + 0.08)))
    pts: dict[str, list] = {}
    for e in pl.get("emitters", []):
        pts.setdefault(e["kind"], []).append(e["pos"][:2])
    for k in ("steam", "exhaust", "cooking", "smoke"):
        if k in pts:
            a = np.array(pts[k])
            ax.scatter(a[:, 0], a[:, 1], s=1.2 if k == "steam" else 3.0, c=KIND_COLORS[k],
                       lw=0, label=f"{k} ({len(a)})")
    for k, c in sorted(n.items()):
        ax.scatter([], [], s=30, c=KIND_COLORS[k], alpha=0.6,
                   label=f"{k.replace('_', ' ')} ({c})")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    leg = ax.legend(loc="lower left", fontsize=7, markerscale=3, facecolor="#0b0f1a",
                    labelcolor="#d8deea", framealpha=0.9)
    leg.get_frame().set_edgecolor("#2a3550")
    ax.set_title(f"{pl['city']}: the air: {len(pl.get('volumes', []))} fog and smog volumes, "
                 f"{len(pl.get('emitters', []))} steam and smoke plumes ({pl['preset']})",
                 fontsize=9, color="#d8deea")
    dest = Path(out) if out else pdir / "preview_air.png"
    fig.savefig(dest, facecolor="#05070d")
    plt.close(fig)
    return {"image": str(dest), "volumes": n, "emitters": {k: len(v) for k, v in pts.items()}}
