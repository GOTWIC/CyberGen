"""`atmosgen plan BUILD`: the atmos plan of a built city (scope 4.2, 7).

AT0 placed the lights the spike measured: every street and wall light at its lamp head,
every sign slot's lit face as a rect light in its sign's color (billboards, banners, neon
bands, holo-boards, shop signs), and every ground-floor unit's shopfront spilling onto its
sidewalk. AT1 (streets at night) lights the streets by photometric class and checks them:

- **Street and wall lights** by class (`presets.PHOTOMETRY`: cobra heads, post tops, wall
  packs, in Unreal's own profile), wide enough that the carriageway between the lamps is
  lit (#81), at about a fifth of AT0's intensity.
- **Junctions**: a mast arm light on every traffic signal, reaching over the junction
  (`signals`); then corner poles at the junctions the lux check finds dark (`corners`: at
  the ends of their legs' sidewalks and crosswalks, the darkest first, at most
  `presets.CORNER_MAX`).
- **Roads M6 gives no lamps**: highway and ramp columns (a twin arm in a median, else one
  at the edge, staggered), service roads, footbridges (`roads`), wall packs along alleys
  (`alleys`, spaced by the mood's alley darkness).
- **Structures**: soffit lights under M14's decks where AG10 draws its fixtures (`decks`),
  road tunnel and underpass strips where AG7 draws them (`tunnels`), platform downlights
  under the stations' canopies (`stations`).
- **Shop spill** and **signs** as AT0 placed them (AT2 takes the signs further).
- **The lux check** (`lux.py`, scope 8): every walkway and lane against its class's
  targets, with occlusion; the plan's `checks.lux`; a plan that fails it is written but not
  delivered (`atmosgen plan` exits 1, the exporter leaves it out).

Each light keeps its schedule for every hour (decision 12.3), its district's mood
(temperature, flicker, broken lights, neon density: clean where wealthy and safe, gritty in
markets, old towns and poor districts, decision 12.5), its tier, what it hangs on (`mount`:
the city's own fixture, or one asked of stage 2) and hash. The volumes, emitters and masks
follow in AT4 and AT5.

Deterministic: draws are blake2b hashes of ids, coordinates on the millimeter grid, colors
to 1/1000, canonical JSON; a file is written only when its bytes change.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import emitters as EM
from . import planmodel as PM
from . import presets as P
from . import sky as SK
from . import spec as S

CODE_FILES = ("presets.py", "spec.py", "planmodel.py", "emitters.py", "plan.py", "lux.py",
              "sky.py", "air.py", "sight.py", "weather.py", "look.py", "far.py")
OUT = "atmos"
TILE_M = 256.0


# --- small helpers ----------------------------------------------------------------------------

def dumps(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_hash() -> str:
    h = hashlib.sha256()
    here = Path(__file__).parent
    for name in CODE_FILES:
        h.update(name.encode() + b"\0" + (here / name).read_bytes().replace(b"\r\n", b"\n"))
    return f"at7.{h.hexdigest()[:12]}"


def u(*key) -> float:
    """A draw in [0, 1) from the key (blake2b, as citygen's props._u)."""
    d = hashlib.blake2b("|".join(map(str, key)).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(d, "little") / 2.0 ** 64


def mm(v: float) -> float:
    r = round(v * 1000.0) / 1000.0
    return 0.0 if r == 0.0 else r


def r3(v: float) -> float:
    r = round(v * 1000.0) / 1000.0
    return 0.0 if r == 0.0 else r


def tile_of(x: float, y: float) -> str:
    """citygen's tile name (`blockout.tile_name(*tile_key(x, y))`)."""
    ix, iy = math.floor(x / TILE_M), math.floor(y / TILE_M)
    return f"t{ix:+03d}{iy:+03d}"


def tile_bounds(name: str) -> list[float]:
    ix, iy = int(name[1:4]), int(name[4:7])
    return [ix * TILE_M, iy * TILE_M, (ix + 1) * TILE_M, (iy + 1) * TILE_M]


def srgb_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_linear(h: str) -> list[float]:
    return [r3(srgb_linear(int(h[1 + 2 * k:3 + 2 * k], 16) / 255.0)) for k in range(3)]


def unit(rgb) -> list[float]:
    """A linear color scaled to its brightest channel at 1 (a light's color; its strength is
    its intensity): black is white."""
    top = max(rgb)
    if top < 1e-3:
        return [1.0, 1.0, 1.0]
    return [r3(c / top) for c in rgb]


def kelvin_linear(k: float) -> list[float]:
    """A blackbody's color at `k` kelvin, linear RGB normalized to its brightest channel
    (Helland's fit of the CIE 1964 data, in sRGB, then linearized)."""
    t = k / 100.0
    if t <= 66.0:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19.0 else 138.5177312231 * math.log(t - 10.0) - 305.0447927307
    else:
        r = 329.698727446 * (t - 60.0) ** -0.1332047592
        g = 288.1221695283 * (t - 60.0) ** -0.0755148492
        b = 255.0
    rgb = [srgb_linear(max(0.0, min(255.0, c)) / 255.0) for c in (r, g, b)]
    top = max(rgb) or 1.0
    return [r3(c / top) for c in rgb]


def _aim(yaw: float, pitch: float) -> list[float]:
    return [mm(((yaw + 180.0) % 360.0) - 180.0), mm(pitch)]


# --- the city ---------------------------------------------------------------------------------

class City:
    """What the plan reads of a build: the model's JSON (raw, for speed), assetgen's signs
    and the ground (M13's, on a terrain city; 0 on a flat one)."""

    def __init__(self, build: Path):
        self.build = build
        text = (build / "city_model.json").read_text(encoding="utf-8")
        self.model_sha256 = sha(text)
        self.m = json.loads(text)
        self.name = self.m["name"]
        self.segments = {s["id"]: s for s in self.m.get("road_segments", [])}
        self.districts = {d["id"]: d for d in self.m.get("districts", [])}
        self.buildings = {b["id"]: b for b in self.m.get("buildings", [])}
        self.nodes = {n["id"]: n for n in self.m.get("road_nodes", [])}
        self.base = {b["id"]: float(b["base_m"]) for b in self.m.get("buildings", [])
                     if b.get("base_m") is not None}
        self.signs = EM.SignColors(build / "assets")
        self._occ = None
        self._model = None
        self._dpolys = None
        t = self.m.get("terrain")
        self._grid = None
        if t:
            rows = t.get("ground") or t.get("natural")
            self._grid = (float(t["x0"]), float(t["y0"]), float(t["cell_m"]),
                          np.array(rows, dtype=np.float64))

    def ground(self, x: float, y: float) -> float:
        return float(self.ground_many([x], [y])[0])

    def ground_many(self, xs, ys) -> np.ndarray:
        """The finished ground under points (M13's grid bilinear, as assetgen's `Ground.at`);
        0 on a flat city."""
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        if self._grid is None:
            return np.zeros(xs.shape)
        x0, y0, cell, a = self._grid
        ny, nx = a.shape
        fx = np.clip((xs - x0) / cell, 0.0, nx - 1.000001)
        fy = np.clip((ys - y0) / cell, 0.0, ny - 1.000001)
        i = fx.astype(np.int64)
        j = fy.astype(np.int64)
        tx, ty = fx - i, fy - j
        h0 = a[j, i] * (1.0 - tx) + a[j, i + 1] * tx
        h1 = a[j + 1, i] * (1.0 - tx) + a[j + 1, i + 1] * tx
        return h0 * (1.0 - ty) + h1 * ty

    def occluders(self):
        if self._occ is None:
            from .lux import Occluders
            self._occ = Occluders(self.m, self.ground)
        return self._occ

    def model(self):
        """The pydantic model (AG10's deck code reads it), loaded once when needed."""
        if self._model is None:
            from assetgen.brief import load_model
            self._model, _, _ = load_model(self.build)
        return self._model

    def ag15(self) -> dict:
        """AG15's night of every building from assetgen's manifest (`assets/manifest.json`):
        {id: {accent: '#rrggbb', crown_light: none|edges|band|both, vacant: bool}}; {} without
        assets (the plan then floods by the mood alone). Read once, keeping only these."""
        if getattr(self, "_ag15", None) is None:
            self._ag15 = {}
            p = self.build / "assets" / "manifest.json"
            if p.is_file():
                man = json.loads(p.read_text(encoding="utf-8"))
                for bid, r in (man.get("buildings") or {}).items():
                    g = r.get("genes") or {}
                    night = (r.get("ag15") or {}).get("night") or {}
                    acc = g.get("accent")
                    self._ag15[bid] = {
                        "accent": f"#{acc}" if acc and not acc.startswith("#") else acc,
                        "crown_light": g.get("crown_light") or "none",
                        "vacant": night.get("schedule") == "vacant"}
                del man
        return self._ag15

    def ground_at_base(self, b: dict) -> float:
        """A building's base (M13's `base_m`, else the ground under its footprint's first
        point)."""
        if b["id"] in self.base:
            return self.base[b["id"]]
        fp = (b.get("footprint") or {}).get("exterior") or [[0.0, 0.0]]
        return self.ground(fp[0][0], fp[0][1])

    def district_of(self, pid: str) -> str | None:
        """A record's district from its id's prefix (M10's ids start with the district's)."""
        d = pid.split(".", 1)[0]
        return d if d in self.districts else None

    def district_at(self, x: float, y: float) -> str | None:
        """The district whose polygon holds a point (the first by id)."""
        from shapely import contains_xy
        from shapely.geometry import Polygon
        if self._dpolys is None:
            self._dpolys = []
            for did in sorted(self.districts):
                poly = self.districts[did].get("polygon") or {}
                if len(poly.get("exterior") or []) >= 3:
                    self._dpolys.append((did, Polygon(poly["exterior"])))
        for did, g in self._dpolys:
            if contains_xy(g, x, y):
                return did
        return None


class Line:
    """A polyline with arc length: points (z where its points carry one) and tangents at
    any s."""

    def __init__(self, pts):
        self.p = []
        for q in pts:
            if not self.p or math.dist(self.p[-1][:2], q[:2]) > 1e-6:
                self.p.append(q)
        self.cum = [0.0]
        for a, b in zip(self.p, self.p[1:]):
            self.cum.append(self.cum[-1] + math.dist(a[:2], b[:2]))
        self.L = self.cum[-1]

    def at(self, s: float):
        """(x, y, z, tx, ty) at s."""
        n = len(self.p)
        s = min(max(s, 0.0), self.L)
        i = 0
        while i < n - 2 and self.cum[i + 1] < s:
            i += 1
        a, b = self.p[i], self.p[i + 1]
        seg = max(self.cum[i + 1] - self.cum[i], 1e-9)
        f = (s - self.cum[i]) / seg
        tx, ty = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
        za = a[2] if len(a) > 2 else 0.0
        zb = b[2] if len(b) > 2 else 0.0
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, za + (zb - za) * f,
                tx, ty)


def seg_z(seg: dict, s: float) -> float:
    """A road's own height at s along its centerline (M7's z profile; 0 where none)."""
    prof = seg.get("z_profile") or []
    if not prof:
        return 0.0
    if s <= prof[0]["s"]:
        return float(prof[0]["z"])
    for a, b in zip(prof, prof[1:]):
        if s <= b["s"]:
            f = (s - a["s"]) / max(b["s"] - a["s"], 1e-9)
            return float(a["z"]) + (float(b["z"]) - float(a["z"])) * f
    return float(prof[-1]["z"])


def _center(ring) -> tuple[float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def sides(g) -> list[tuple]:
    """The four sides of a footprint's oriented box (M3's `massing.obb_angle`), each as
    (outward normal, tangent, middle, extent along the normal from the middle, tangent
    from, tangent to): a flood's side of any shape, round or odd."""
    from citygen import massing as MS
    try:
        ang = float(MS.obb_angle(g))
    except Exception:
        ang = 0.0
    c = g.centroid
    pts = list(g.exterior.coords)
    out = []
    for k in range(4):
        a = ang + k * math.pi / 2.0
        n = (math.cos(a), math.sin(a))
        t = (-n[1], n[0])
        e_n = max((p[0] - c.x) * n[0] + (p[1] - c.y) * n[1] for p in pts)
        ts = [(p[0] - c.x) * t[0] + (p[1] - c.y) * t[1] for p in pts]
        out.append((n, t, (c.x, c.y), e_n, min(ts), max(ts)))
    return out


def corners(g, inset: float) -> list[tuple[float, float]]:
    """The corners of a footprint's oriented box, `inset` in (counterclockwise from the long
    axis' end)."""
    sd = sides(g)
    out = []
    for k in range(4):
        n, t, c, e_n, t0, t1 = sd[k]
        m = sd[(k + 1) % 4]
        e_m = m[3]
        x = c[0] + n[0] * (e_n - inset) + m[0][0] * (e_m - inset)
        y = c[1] + n[1] * (e_n - inset) + m[0][1] * (e_m - inset)
        out.append((x, y))
    return out


class Shape:
    """A building's (or a megasite structure's) masses for its night lights (AT2): their
    footprints with their spans over its base, its body's top (M21's thin parts, masts,
    spires, halos, left out), its top and its tip, its crown (the largest body mass at the
    body's top)."""

    def __init__(self, rec: dict, base: float):
        from shapely.geometry import Polygon
        self.base = float(base)
        self.ms = []
        for m in rec.get("masses") or []:
            fp = m.get("footprint") or {}
            ext = fp.get("exterior") or []
            if len(ext) < 3:
                continue
            g = Polygon(ext, [h for h in fp.get("holes") or [] if len(h) >= 3])
            if not g.is_valid:
                g = g.buffer(0)
            if g.is_empty or g.geom_type != "Polygon":
                g = max(getattr(g, "geoms", []), key=lambda q: q.area, default=None)
                if g is None or g.is_empty:
                    continue
            self.ms.append((g, float(m.get("z0_m", 0.0)), float(m.get("z1_m", 0.0)),
                            m.get("role") or ""))
        body = [x for x in self.ms if x[3] not in P.FLOOD_THIN_ROLES]
        self.top = max((x[2] for x in self.ms), default=0.0)
        self.body_top = max((x[2] for x in body), default=self.top)
        crown = [x for x in body if x[2] >= self.body_top - 0.5]
        self.crown = max(crown, key=lambda x: x[0].area) if crown else None
        tips = [x for x in self.ms if x[2] >= self.top - 0.01]
        self.tip = min(tips, key=lambda x: x[0].area) if tips else None

    def at(self, z: float):
        """The largest body mass spanning z (over the base)."""
        ms = [x for x in self.ms if x[1] <= z <= x[2] and x[3] not in P.FLOOD_THIN_ROLES]
        return max(ms, key=lambda x: x[0].area) if ms else None

    def shaft(self):
        """The body mass at half the body's height (the shaft a facade uplight lights)."""
        return self.at(0.5 * self.body_top)

    def inside(self, x: float, y: float, z: float, pad: float = 0.5):
        """The mass a point (z absolute) stands in (within `pad` in plan), else None."""
        from shapely import contains_xy
        zr = z - self.base
        for m in self.ms:
            if m[1] - 0.05 < zr < m[2] + 0.05 and (contains_xy(m[0], x, y) or
                                                  m[0].distance(_pt(x, y)) < pad):
                return m
        return None

    def top_under(self, x: float, y: float, below: float) -> float | None:
        """The highest top (over the base) under `below` of the masses over a point (a
        podium's roof), else None."""
        from shapely import contains_xy
        tops = [m[2] for m in self.ms if m[2] < below and contains_xy(m[0], x, y)]
        return max(tops) if tops else None


def _pt(x, y):
    from shapely.geometry import Point
    return Point(x, y)


# --- the lights -------------------------------------------------------------------------------

class Plan:
    def __init__(self, city: City, filled: dict):
        self.c = city
        self.f = filled
        self.moods = filled["moods"]
        self.lights: list[dict] = []
        self.skipped: dict[str, int] = {}
        self.corner_report: dict = {}
        self.fill_report: dict = {}
        self._jc = None
        # (AT3: the schedules, `dusk_dawn` and `tunnel` set by the sun, `sky.schedules`)
        self.schedules = {k: list(v) for k, v in P.SCHEDULES.items()}

    def mood(self, did: str | None) -> dict:
        return self.moods.get(did or "", None) or S.mood(None, None, None)

    def add(self, *, owner: str, suffix: str, kind: str, cls: str, did: str | None,
            pos, aim, color, cd: float, schedule: str, temp_k: int | None = None,
            size=None, tier: str | None = None, mount: str = "prop", reach: float | None = None,
            cone=None, anim: dict | None = None, source: str = "derived") -> dict:
        ph = P.PHOTOMETRY[cls]
        md = self.mood(did)
        lid = f"{owner}.{suffix}"
        if tier is None:
            tier = "high" if kind in P.HIGH_KINDS else (
                "near" if kind in P.NEAR_KINDS else "mid")
        # flicker and broken lights by the mood and the kind (AT2: neon fails more than an LED
        # billboard or a lamp; a shopfront's tube now and then; tunnels, stations, deck
        # soffits, safety lights and the check's corner poles and fill lights are kept)
        kept = kind in P.KEPT_KINDS or ".fill" in owner
        flick = 0.0 if kept else md["flicker"] * P.FLICKER_BY_KIND.get(kind, 1.0)
        broken = False if kept else \
            u(lid, "broken") < md["broken"] * P.BROKEN_BY_KIND.get(kind, 1.0)
        depth = r3(0.35 + 0.5 * u(lid, "depth")) if u(lid, "flicker") < flick else 0.0
        if broken and kind in P.DYING_KINDS:
            # (a sign's face stays lit as assetgen draws it: its light dies flickering)
            lo, hi = P.DYING_DEPTH
            depth, broken = r3(lo + (hi - lo) * u(lid, "dying")), False
        # grit (decision 12.5): a gritty district's lamps of mixed temperatures and aged
        # output; a clean one's uniform (AT2)
        past = max(0.0, float(md.get("grit", 0.0)) - P.MIX_FROM)
        if kind in P.MIX_KINDS and past > 0.0 and ".fill" not in owner:
            cd *= 1.0 - P.MIX_DIM * past * u(lid, "age")
            if u(lid, "mix") < P.MIX_SHARE * past:
                names = sorted(P.MIX_COLORS)
                color = hex_linear(P.MIX_COLORS[names[int(u(lid, "mixc") * len(names))
                                                     % len(names)]])
                temp_k = None
        rec = {"id": lid, "owner_id": owner, "kind": kind, "cls": cls, "shape": ph["shape"],
               "district_id": did, "tile": tile_of(pos[0], pos[1]),
               "pos": [mm(pos[0]), mm(pos[1]), mm(pos[2])], "aim": _aim(*aim),
               "cd": round(cd, 1), "color": color,
               "reach_m": r3(reach) if reach is not None else ph["reach_m"],
               "shadow": bool(ph.get("shadow", False)) and tier != "high", "tier": tier,
               "schedule": schedule, "flicker": depth, "on": not broken,
               "source": source,
               "mount": mount,
               "specular": 0.0 if kind in P.NO_SPECULAR_KINDS else 1.0}
        if temp_k is not None:
            rec["temp_k"] = int(temp_k)
        if anim is not None:
            rec["anim"] = {k: (r3(v) if isinstance(v, float) else v) for k, v in anim.items()}
        if ph["shape"] == "rect":
            rec["size"] = [mm(size[0]), mm(size[1])]
            rec["barn_deg"] = ph["barn_deg"]
        else:
            rec["source_m"] = ph.get("source_m", 0.0)
        if ph["shape"] == "spot":
            rec["cone"] = [r3(c) for c in cone] if cone is not None else \
                [ph["inner"], ph["outer"]]
        # (the hash of the record as the tile file writes it: the schema's defaults in)
        rec = json.loads(PM.Light(**rec, hash="").model_dump_json(exclude_none=True))
        rec.pop("hash")
        rec["hash"] = sha(dumps(rec))[:16]
        self.lights.append(rec)
        return rec

    def mood_color(self, did: str | None, key: str, salt: str) -> list[float]:
        """A color of the district's palette, drawn by `key` (AT2's district palettes)."""
        pal = self.mood(did).get("palette") or list(P.NEON)
        return unit(hex_linear(pal[int(u(key, salt) * len(pal)) % len(pal)]))

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1

    def spot(self, cls: str, *, owner: str, suffix: str, kind: str, did: str | None, x: float,
             y: float, z: float, yaw: float, mount: str, schedule: str = "dusk_dawn",
             tilt: float | None = None, cd_scale: float = 1.0, temp_key: str = "temp",
             commit: bool = True) -> dict:
        """A light of class `cls` (spot or point) whose fixture's lens is at (x, y, z), its
        aim turned `tilt` (default its class's) off straight down toward the heading `yaw`;
        `commit` False makes the record without adding it (a corner pole tried)."""
        ph = P.PHOTOMETRY[cls]
        t = ph.get("tilt", 0.0) if tilt is None else tilt
        temp = P.TEMPS[self.mood(did)[temp_key]]
        kw = dict(owner=owner, suffix=suffix, kind=kind, cls=cls, did=did,
                  pos=(x, y, z - ph["drop_m"]),
                  aim=(yaw, -90.0 + t if ph["shape"] == "spot" else -90.0),
                  color=kelvin_linear(temp), temp_k=temp, cd=ph["cd"] * cd_scale,
                  schedule=schedule, mount=mount)
        rec = self.add(**kw)
        if not commit:
            self.lights.pop()
        return rec

    # -- street and wall lights (M6) --

    def lamps(self) -> None:
        for p in self.c.m.get("props", []):
            kind = p["type"].split(".", 1)[1]
            if kind not in EM.LAMP_HEAD:
                continue
            did = self.c.district_of(p["id"])
            md = self.mood(did)
            if kind == "street_light":
                sid = (p.get("attrs") or {}).get("sidewalk", "").rsplit(".", 1)[0]
                rc = (self.c.segments.get(sid) or {}).get("road_class")
                cls = md["lamp"] if md["lamp"] in ("cobra_head", "post_top") else "cobra_head"
                if rc in ("pedestrian", "path", "promenade", "plaza"):
                    cls = "post_top"
                elif rc in ("highway", "avenue") and cls == "post_top":
                    cls = "cobra_head"
            else:
                cls = "wall_pack"
            ph = P.PHOTOMETRY[cls]
            hx, hy, hz = EM.lamp_head(kind, p["position"], float(p.get("yaw_deg", 0.0)),
                                      p.get("scale") or [1.0, 1.0, 1.0])
            z = self.c.ground(p["position"][0], p["position"][1]) + hz - ph["drop_m"]
            temp = P.TEMPS[md["temp"]]
            pitch = -90.0 + ph.get("tilt", 0.0) if ph["shape"] == "spot" else -90.0
            self.add(owner=p["id"], suffix="light", kind=kind, cls=cls, did=did,
                     pos=(hx, hy, z), aim=(float(p.get("yaw_deg", 0.0)), pitch),
                     color=kelvin_linear(temp), temp_k=temp, cd=ph["cd"],
                     schedule="dusk_dawn")

    # -- junctions: mast arms on the traffic signals (M6, M18) --

    def junction_centers(self) -> dict:
        """Every junction's middle (its polygon's box) and its node's height."""
        if self._jc is None:
            self._jc = {}
            for j in self.c.m.get("junctions", []):
                ring = (j.get("polygon") or {}).get("exterior") or []
                if len(ring) < 3:
                    continue
                n = self.c.nodes.get(j.get("node_id") or "")
                z = float(n["position"][2]) if n and len(n.get("position", [])) > 2 else 0.0
                self._jc[j["id"]] = (*_center(ring), z)
        return self._jc

    def signals(self) -> None:
        jc = self.junction_centers()
        arm_max, arm_share = P.SIGNAL_ARM_M
        for p in self.c.m.get("props", []):
            if p["type"] != "prop.traffic_signal":
                continue
            j = jc.get((p.get("attrs") or {}).get("junction") or "")
            if j is None:
                self.skip("signal: no junction")
                continue
            px, py, pz = (float(v) for v in p["position"])
            dx, dy = j[0] - px, j[1] - py
            d = math.hypot(dx, dy)
            if d < 1.0:
                self.skip("signal: in its junction's middle")
                continue
            ux, uy = dx / d, dy / d
            arm = min(arm_max, arm_share * d)
            did = self.c.district_of(p["id"])
            self.spot("cobra_head", owner=p["id"], suffix="light", kind="signal", did=did,
                      x=px + ux * arm, y=py + uy * arm,
                      z=self.c.ground(px, py) + pz + P.SIGNAL_HEAD_Z_M,
                      yaw=math.degrees(math.atan2(uy, ux)), mount="mast_arm")

    # -- roads M6 gives no lamps: highways and ramps, service roads, footbridges --

    def _district(self, rid: str, ring) -> str | None:
        did = self.c.district_of(rid)
        return did if did is not None else self.c.district_at(*_center(ring))

    def roads(self) -> None:
        for sid in sorted(self.c.segments):
            s = self.c.segments[sid]
            rc = s.get("road_class")
            line = s.get("centerline") or []
            if s.get("tunnel") or len(line) < 2:
                continue
            if rc == "footbridge":
                self._rail_posts(s)
                continue
            if rc == "pedestrian":
                self._posts(s)
                continue
            cs = s.get("cross_section") or {}
            sw = cs.get("sidewalk_m") or [0.0, 0.0]
            if rc in P.ROAD_LIGHTS:
                key = rc
            elif rc in ("avenue", "street") and not any(w > 0 for w in sw):
                key = "service"
            else:
                continue
            cls, step, h, arm = P.ROAD_LIGHTS[key]
            ln = Line(line)
            if ln.L < 8.0:
                continue
            did = self._district(sid, line)
            half = float(s.get("width_m", 8.0)) / 2.0
            med = float(cs.get("median_m") or 0.0)
            n = max(1, int(round(ln.L / step)))
            st = ln.L / n
            s0 = st * (0.25 + 0.5 * u(sid, "road.phase"))
            k = 0
            while s0 + k * st <= ln.L - 2.0:
                sv = s0 + k * st
                x, y, _, tx, ty = ln.at(sv)
                nx, ny = -ty, tx                          # (left)
                z = self.c.ground(x, y) + seg_z(s, sv) + h
                if key == "highway" and med >= 1.5:
                    # a twin arm column in the median, a head over each carriageway
                    for side, sfx in ((1.0, "a"), (-1.0, "b")):
                        o = side * (med / 2.0 + arm)
                        self.spot(cls, owner=sid, suffix=f"light{k:03d}{sfx}", kind="road",
                                  did=did, x=x + nx * o, y=y + ny * o, z=z,
                                  yaw=math.degrees(math.atan2(ny * side, nx * side)),
                                  mount="pole")
                else:
                    # one column at an edge, its arm over the road, from side to side
                    side = 1.0 if k % 2 == 0 else -1.0
                    o = side * max(0.0, half - arm)
                    self.spot(cls, owner=sid, suffix=f"light{k:03d}", kind="road", did=did,
                              x=x + nx * o, y=y + ny * o, z=z,
                              yaw=math.degrees(math.atan2(-ny * side, -nx * side)),
                              mount="pole")
                k += 1

    def _posts(self, s: dict) -> None:
        """A pedestrian street's or promenade's lights (M6 gives them none): post tops
        `PED_POST_Z_M` high inside both its edges, every `PED_STEP_M`, from side to side."""
        ln = Line(s["centerline"])
        if ln.L < 4.0:
            return
        did = self._district(s["id"], s["centerline"])
        half = max(0.0, float(s.get("width_m", 4.0)) / 2.0 - 0.6)
        n = max(1, int(round(ln.L / P.PED_STEP_M)))
        flip = int(2 * u(s["id"], "post.side"))
        for k in range(n):
            sv = ln.L * (k + 0.5) / n
            x, y, _, tx, ty = ln.at(sv)
            side = 1.0 if (k + flip) % 2 == 0 else -1.0
            z = self.c.ground(x, y) + seg_z(s, sv) + P.PED_POST_Z_M
            self.spot("post_top", owner=s["id"], suffix=f"light{k:02d}", kind="road", did=did,
                      x=x - ty * side * half, y=y + tx * side * half, z=z, yaw=0.0,
                      mount="pole")

    def _rail_posts(self, s: dict) -> None:
        """A footbridge's lights: posts on its railings every 12 m, from side to side."""
        ln = Line(s["centerline"])
        if ln.L < 4.0:
            return
        did = self._district(s["id"], s["centerline"])
        half = float(s.get("width_m", 4.0)) / 2.0 - 0.2
        n = max(1, int(round(ln.L / 12.0)))
        for k in range(n):
            sv = ln.L * (k + 0.5) / n
            x, y, _, tx, ty = ln.at(sv)
            side = 1.0 if k % 2 == 0 else -1.0
            z = self.c.ground(x, y) + seg_z(s, sv) + 3.2
            self.spot("post_top", owner=s["id"], suffix=f"light{k:02d}", kind="road", did=did,
                      x=x - ty * side * half, y=y + tx * side * half, z=z, yaw=0.0,
                      mount="pole", cd_scale=0.5)

    # -- alleys: wall packs over them --

    def alleys(self) -> None:
        a, b = P.ALLEY_STEP_M
        for sid in sorted(self.c.segments):
            s = self.c.segments[sid]
            if s.get("road_class") != "alley" or s.get("tunnel"):
                continue
            ln = Line(s.get("centerline") or [])
            if len(ln.p) < 2 or ln.L < 6.0:
                continue
            did = self._district(sid, ln.p)
            step = a + b * float(self.mood(did).get("alleys", 0.5))
            n = max(1, int(round(ln.L / step)))
            # (on the facade at the alley's edge: just inside it)
            half = max(0.3, float(s.get("width_m", 4.0)) / 2.0 - 0.2)
            flip = int(2 * u(sid, "alley.side"))
            for k in range(n):
                sv = ln.L * (k + 0.5) / n
                x, y, _, tx, ty = ln.at(sv)
                side = 1.0 if (k + flip) % 2 == 0 else -1.0
                nx, ny = -ty * side, tx * side
                z = self.c.ground(x, y) + seg_z(s, sv) + P.ALLEY_PACK_Z_M
                self.spot("wall_pack", owner=sid, suffix=f"light{k:02d}", kind="alley",
                          did=did, x=x + nx * half, y=y + ny * half, z=z,
                          yaw=math.degrees(math.atan2(-ny, -nx)), mount="wall")

    # -- under the decks: AG10's soffit lights (M14) --

    def decks(self) -> None:
        if not self.c.m.get("decks"):
            return
        from assetgen.streets import decks as AD
        from assetgen.streets.ctx import Ground

        class _Ctx:                     # (what AG10's helpers read of AG7's context)
            pass

        class _Deck:
            pass

        m = self.c.model()
        cx = _Ctx()
        cx.m = m
        cx.ground = Ground(m)
        for dk in sorted(m.decks, key=lambda d: d.id):
            poly, _ = AD.slab_of(m, dk)
            D = _Deck()
            D.poly = poly
            lines, jcs = AD._ground_streets(cx, D)
            ref = AD.Ref(AD._ref_rec(cx, poly, [], *poly.bounds))
            top, slab = float(dk.top_m), float(dk.slab_m)
            for k, (x, y, hd) in enumerate(AD._lights(lines, jcs)):
                # (the fixture's lens: under the soffit's ribs, as AG10's `make_slab` draws)
                z = ref(x, y) + top - slab - AD.RIB_D - 0.125
                self.spot("soffit", owner=dk.id, suffix=f"soffit{k:04d}", kind="soffit",
                          did=dk.district_id, x=x, y=y, z=z, yaw=float(hd), mount="soffit",
                          schedule="always", temp_key="spill")

    # -- road tunnels and underpasses (M9; AG7's light strips) --

    def tunnels(self) -> None:
        for t in sorted(self.c.m.get("tunnels", []) or [], key=lambda t: t["id"]):
            kind = t.get("kind")
            line = t.get("line") or []
            if kind == "metro" or len(line) < 2:
                continue
            ln = Line(line)
            if ln.L < 2.0:
                continue
            did = self._district(t["id"], line)
            clear = float(t.get("clear_m", 5.0))
            w = float(t.get("width_m", 10.0))
            if kind == "pedestrian":
                # (AG7's strip down the middle of the ceiling)
                n = max(1, int(round(ln.L / P.UNDERPASS_STEP_M)))
                for k in range(n):
                    x, y, z, _, _ = ln.at(ln.L * (k + 0.5) / n)
                    self.spot("tunnel", owner=t["id"], suffix=f"light{k:02d}",
                              kind="underpass", did=did, x=x, y=y,
                              z=self.c.ground(x, y) + z + clear, yaw=0.0, tilt=0.0,
                              mount="tunnel", schedule="always", cd_scale=0.4,
                              temp_key="spill")
                continue
            # (a road tunnel: AG7's strips on both walls under the soffit, staggered)
            hi = w / 2.0 - 1.03
            n = max(1, int(round(ln.L / P.TUNNEL_STEP_M)))
            for k in range(n):
                for side, sfx, off in ((1.0, "a", 0.0), (-1.0, "b", 0.5)):
                    sv = min(ln.L, ln.L * (k + 0.25 + off) / n)
                    x, y, z, tx, ty = ln.at(sv)
                    nx, ny = -ty * side, tx * side
                    self.spot("tunnel", owner=t["id"], suffix=f"light{k:03d}{sfx}",
                              kind="tunnel", did=did, x=x + nx * hi, y=y + ny * hi,
                              z=self.c.ground(x, y) + z + clear - 0.7,
                              yaw=math.degrees(math.atan2(-ny, -nx)), mount="tunnel",
                              schedule="tunnel", temp_key="spill")

    # -- stations (M5): platform downlights under the canopy --

    def stations(self) -> None:
        from shapely import contains_xy
        from shapely.geometry import Polygon

        from citygen import massing as MS
        for st in sorted(self.c.m.get("stations", []) or [], key=lambda s: s["id"]):
            kind = st.get("kind")
            fp = (st.get("footprint") or {}).get("exterior") or []
            # (AT2: a sky station's platform, in or beside its tower, lit as an elevated one's)
            if kind not in ("elevated", "underground", "sky") or len(fp) < 3:
                continue
            g = Polygon(fp)
            if not g.is_valid:
                g = g.buffer(0)
            ang = float(MS.obb_angle(g))
            ux, uy = math.cos(ang), math.sin(ang)
            vx, vy = -uy, ux
            cx, cy = _center(fp)
            pts = [((x - cx) * ux + (y - cy) * uy, (x - cx) * vx + (y - cy) * vy)
                   for x, y in fp]
            a0, a1 = min(p[0] for p in pts), max(p[0] for p in pts)
            b0, b1 = min(p[1] for p in pts), max(p[1] for p in pts)
            width = b1 - b0
            rows = [0.0] if width < 10.0 else [-width / 4.0, width / 4.0]
            track = float((st.get("attrs") or {}).get("track_z_m", st["position"][2]))
            levels = [track + 1.0] if kind in ("elevated", "sky") else \
                [float(st["position"][2]), track + 1.0]
            did = self.c.district_at(cx, cy)
            n = max(1, int(round((a1 - a0) / P.PLATFORM_STEP_M)))
            k = 0
            for lv in levels:
                for r in rows:
                    for i in range(n):
                        a = a0 + (a1 - a0) * (i + 0.5) / n
                        bm = (b0 + b1) / 2.0 + r
                        x = cx + a * ux + bm * vx
                        y = cy + a * uy + bm * vy
                        if not contains_xy(g, x, y):
                            continue
                        self.spot("platform", owner=st["id"], suffix=f"light{k:03d}",
                                  kind="station", did=did, x=x, y=y,
                                  z=self.c.ground(x, y) + lv + P.PLATFORM_Z_M,
                                  yaw=math.degrees(ang), mount="canopy", schedule="always",
                                  temp_key="spill")
                        k += 1

    # -- signs as light (M11, M20; the second ask) --

    def signs(self) -> None:
        """AT2: every lit sign slot as light (scope 6.1). Billboards, banners and holo-boards
        are lit faces: a rect light the size of the face, stood off it (`out_m`) so its own
        wall and what stands out of the wall stay behind the light's plane, a share of the
        face's luminance as light (`light`), times its page cell's brightness, in the page's
        color; a holo-board in front of a facade lights only away from it. Neon bands and shop
        signs are neon spill: a small colored spot off the sign aimed out and down at the
        sidewalk (a blade sign a point at its middle), near tier only. Each lit face's wall is
        kept for the faces check (`face_walls`)."""
        self.face_walls: list[dict] = []
        self.dimmed = 0
        for s in self.c.m.get("sign_slots", []):
            kind, mount = s.get("kind"), s.get("mount")
            cls = P.SIGN_CLASS.get((kind, mount)) or P.SIGN_CLASS.get(kind)
            if cls is None or not s.get("emitter", True):
                self.skip(f"sign {kind}: not lit")
                continue
            did = self.c.district_of(s["id"]) or (self.c.buildings.get(
                s.get("building_id") or "") or {}).get("district_id")
            md = self.mood(did)
            # neon density: the share of the district's signs that light (all at 1 or more)
            if kind != "shop_sign" and u(s["id"], "neon") >= min(1.0, 0.4 + 0.6 * md["neon"]):
                self.skip("sign: neon density")
                continue
            col, luma, from_ag = self.c.signs.emit(s["id"])
            color = unit(hex_linear(col)) if col else self.mood_color(did, s["id"], "color")
            ph = P.PHOTOMETRY[cls]
            if from_ag and luma is not None:
                nits = float(luma)                   # (the ask's own nits)
            else:
                lo, hi = P.SIGN_LUMA_SCALE
                k = 1.0 if luma is None else min(hi, max(lo, luma / P.SIGN_LUMA_REF))
                nits = ph["nits"] * k
            nits *= ph.get("light", 1.0)
            base = self.c.base.get(s.get("building_id") or "", 0.0)
            near = "near" if kind in P.SIGN_NEAR_ONLY else "mid"
            sched = "late" if kind in ("neon", "banner") else (
                "sign" if kind != "shop_sign" else "late")
            drawn = self.c.signs.face(s["id"])
            faces = EM.faces_of(drawn) if drawn else EM.sign_face(s)
            source = "assetgen" if drawn and from_ag else "derived"
            lkind = P.SIGN_KIND[kind]
            if cls in P.LIT_FACES:
                for k, face in enumerate(faces):
                    if face.get("back") and mount == "front":
                        # (a holo-board in front of a facade: its back looks at the wall)
                        self.skip("sign: a front holo-board's back (its wall)")
                        continue
                    w, h = face["size"]
                    a = math.radians(face["yaw"])
                    cx = face["c"][0] + ph["out_m"] * math.cos(a)
                    cy = face["c"][1] + ph["out_m"] * math.sin(a)
                    cz = face["c"][2] + base
                    cd = nits * w * h
                    # (a big face close across a narrow street: no more than OPPOSITE_MAX_LX on
                    # the facade it faces, as a face's light falls off over the street)
                    from .lux import opposite
                    e = opposite({"pos": [cx, cy, cz], "aim": [face["yaw"], 0.0],
                                  "shape": "rect", "cd": cd, "barn_deg": ph["barn_deg"],
                                  "reach_m": ph["reach_m"]}, face["yaw"], self.c.occluders())
                    if e is not None and e > P.OPPOSITE_MAX_LX:
                        cd *= max(P.OPPOSITE_MIN_SCALE, P.OPPOSITE_MAX_LX / e)
                        self.dimmed += 1
                    rec = self.add(owner=s["id"], suffix=f"light{k}" if k else "light",
                                   kind=lkind, cls=cls, did=did, pos=(cx, cy, cz),
                                   aim=(face["yaw"], 0.0), color=color, cd=cd,
                                   schedule=sched, size=(w, h), tier=near, mount="sign",
                                   source=source)
                    if mount in ("facade", "front") and not face.get("back"):
                        off = float((s.get("attrs") or {}).get("off_m", 3.0)) \
                            if mount == "front" else 0.0
                        x, y, z = (float(v) for v in s["position"])
                        self.face_walls.append(
                            {"light": rec, "yaw": face["yaw"], "size": [w, h],
                             "wall": [x - off * math.cos(a), y - off * math.sin(a), z + base]})
                continue
            face = faces[0]
            w, h = face["size"]
            a = math.radians(face["yaw"])
            if cls == "blade_neon":
                # (a blade sign square off its wall, lit both ways: a point at its middle)
                x, y, z = (float(v) for v in s["position"])
                pos, aim = (x, y, z + base), (face["yaw"], -90.0)
            else:
                pos = (face["c"][0] + ph["out_m"] * math.cos(a),
                       face["c"][1] + ph["out_m"] * math.sin(a), face["c"][2] + base)
                aim = (face["yaw"], ph["pitch"])
            self.add(owner=s["id"], suffix="light", kind=lkind, cls=cls, did=did, pos=pos,
                     aim=aim, color=color, cd=nits * w * h, schedule=sched, tier=near,
                     mount="sign", source=source)

    # -- shopfronts spilling onto the sidewalk (M3's units) --

    def spill(self) -> None:
        from shapely.geometry import Point, Polygon
        for b in self.c.m.get("buildings", []):
            units = b.get("units") or []
            fp = b.get("footprint")
            if not units or not fp or len(fp.get("exterior") or []) < 3:
                continue
            poly = Polygon(fp["exterior"], [h for h in fp.get("holes") or [] if len(h) >= 3])
            if not poly.is_valid:
                poly = poly.buffer(0)
            did = b.get("district_id")
            md = self.mood(did)
            ph = P.PHOTOMETRY["shop_spill"]
            base = self.c.base.get(b["id"], 0.0)
            for k, un in enumerate(units):
                (ax, ay), (bx, by) = un["edge"]
                L = math.hypot(bx - ax, by - ay)
                if L < 1.0:
                    self.skip("spill: unit edge under 1 m")
                    continue
                mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                nx, ny = (by - ay) / L, -(bx - ax) / L
                if poly.contains(Point(mx + 0.6 * nx, my + 0.6 * ny)):
                    nx, ny = -nx, -ny
                use = un.get("use") or "shop"
                temp = P.TEMPS[md["spill"]]
                col = kelvin_linear(temp)
                # (a few uses tint their spill: bars and clubs magenta, cyberware and
                # clinics cool cyan; the rest the mood's white)
                tint = {"bar": "#ff4fb4", "club": "#b967ff", "arcade": "#05d9e8",
                        "cyberware": "#05d9e8", "clinic": "#c8f0ff"}.get(use)
                if tint is not None:
                    tl = hex_linear(tint)
                    col = [r3(0.45 * c + 0.55 * t) for c, t in zip(col, tl)]
                w = max(1.0, min(0.85 * L, float(un.get("width_m") or L)))
                hh = ph["height_m"]
                # (the unit's floor: its building's base on M13's terrain, else the ground)
                floor = base if b["id"] in self.c.base else self.c.ground(mx, my)
                self.add(owner=f"{b['id']}.u{k:02d}", suffix="spill", kind="spill",
                         cls="shop_spill", did=did,
                         pos=(mx + ph["out_m"] * nx, my + ph["out_m"] * ny,
                              floor + ph["sill_m"] + hh / 2),
                         aim=(math.degrees(math.atan2(ny, nx)), 0.0), color=col,
                         temp_k=temp, cd=ph["nits"] * w * hh,
                         schedule=P.USE_SCHEDULE.get(use, "shop"), size=(w, hh),
                         mount="facade")

    # -- AT2: buildings at night (floods, aviation lights, searchlights) --

    def _towers(self) -> list[tuple[dict, Shape]]:
        """Every tower (M21's `form.tower`) and landmark with its shape, by id."""
        if getattr(self, "_tw", None) is None:
            self._tw = []
            for bid in sorted(self.c.buildings):
                b = self.c.buildings[bid]
                if not ((b.get("form") or {}).get("tower") or b.get("landmark")):
                    continue
                sh = Shape(b, self.c.ground_at_base(b))
                if sh.crown is not None and sh.body_top >= 30.0:
                    self._tw.append((b, sh))
        return self._tw

    def _landmark(self, b: dict) -> dict:
        """The spec's lights of a landmark (`LandmarkLights`), by its name; defaults else."""
        lm = (self.f.get("landmarks") or {}).get(b.get("name") or "") or {}
        kind = ((b.get("attrs") or {}).get("landmark_kind") or
                (b.get("type") or "").rsplit(".", 1)[-1])
        n = lm.get("searchlights")
        return {"floods": lm.get("floods", True), "crown": lm.get("crown", True),
                "searchlights": P.LANDMARK_SEARCHLIGHTS.get(kind, 2) if n is None else int(n),
                "color": lm.get("color")}

    def _flood_color(self, b: dict, did: str | None) -> tuple[list[float], int | None, bool]:
        """A tower's floods' color: the spec's for a landmark, else its crown LEDs' accent
        (AG15: matching what they show), else its district's white. (rgb, kelvin, matched)."""
        if b.get("landmark") and self._landmark(b)["color"]:
            return unit(hex_linear(self._landmark(b)["color"])), None, False
        ag = self.c.ag15().get(b["id"]) or {}
        if ag.get("crown_light", "none") != "none" and ag.get("accent"):
            return unit(hex_linear(ag["accent"])), None, True
        k = P.TEMPS[self.mood(did).get("flood", "neutral")]
        return kelvin_linear(k), k, False

    def _flood(self, *, b, sh, did, owner, suffix, cls, g, side, tl, z_light, z0, z1, color,
               temp_k, out: float) -> dict | None:
        """One flood: a spot `out` off the side `side` of footprint `g` (at `tl` along it), at
        `z_light`, aimed up into the facade's zone [z0, z1] (absolute); its cone covers the
        zone's width, its intensity gives the class's `lux` at the zone's upper middle (a
        grazing light: I = E d^3 / out), its reach the zone's top. Raised onto a setback's roof
        or moved out where the building stands in the way; None where it cannot stand."""
        ph = P.PHOTOMETRY[cls]
        n, t, c, e_n, t0, t1 = side
        width = (t1 - t0) if tl is None else (t1 - t0) / 2.0
        tl = (t0 + t1) / 2.0 if tl is None else tl
        o = out
        x = y = 0.0
        for _ in range(6):
            x = c[0] + n[0] * (e_n + o) + t[0] * tl
            y = c[1] + n[1] * (e_n + o) + t[1] * tl
            hit = sh.inside(x, y, z_light)
            if hit is None:
                break
            if hit[2] + sh.base < z0 - 3.0:
                z_light = hit[2] + sh.base + 0.5          # (on the setback's roof)
            else:
                o += 3.0
        else:
            return None
        if self.c.occluders().blocked(np.array([x]), np.array([y]), np.array([z_light]))[0]:
            self.skip("flood: inside another building")
            return None
        fx = c[0] + n[0] * e_n + t[0] * tl
        fy = c[1] + n[1] * e_n + t[1] * tl
        zt = z0 + 0.6 * (z1 - z0)
        dh = math.hypot(fx - x, fy - y)
        dz = zt - z_light
        d = math.hypot(dh, dz)
        if d < 2.0 or dz <= 0.0:
            return None
        lat = math.degrees(math.atan2(0.55 * width, d))
        vert = 0.5 * (math.degrees(math.atan2(z1 - z_light, max(dh, 0.5))) -
                      math.degrees(math.atan2(max(0.5, z0 - z_light), max(dh, 0.5))))
        outer = min(60.0, max(14.0, max(lat, vert) + 4.0))
        cd = min(4.0e5, ph["lux"] * d ** 3 / max(dh, 0.5))
        reach = 1.15 * math.hypot(dh + 1.0, z1 - z_light) + 2.0
        return self.add(owner=owner, suffix=suffix, kind="flood", cls=cls, did=did,
                        pos=(x, y, z_light), aim=(math.degrees(math.atan2(fy - y, fx - x)),
                                                  math.degrees(math.atan2(dz, dh))),
                        color=color, temp_k=temp_k, cd=cd, schedule="late", mount="roof",
                        reach=reach, cone=(0.6 * outer, outer))

    def floods(self) -> None:
        """Crown floods on towers and landmarks, facade uplights on landmarks and some
        towers (scope 6.1). A tower's crown is flooded where AG15 gave it crown LEDs (in their
        accent: what they show), on every landmark, and on a share of its district's other
        towers (`floods`, by the mood: clean and wealthy districts more); never a vacant one
        (AG15). A flood per side of the crown's box (two on a wide one), below its lit zone
        (`presets.CROWN_ZONE`), 4 m off the facade or on the setback under it."""
        zs, zmin, zmax = P.CROWN_ZONE
        self.flood_report = {"towers": 0, "crowns": 0, "matched_leds": 0, "uplit": 0,
                             "vacant": 0}
        for b, sh in self._towers():
            did = b.get("district_id")
            md = self.mood(did)
            ag = self.c.ag15().get(b["id"]) or {}
            self.flood_report["towers"] += 1
            if ag.get("vacant") and not b.get("landmark"):
                self.flood_report["vacant"] += 1
                continue
            lm = self._landmark(b) if b.get("landmark") else None
            leds = ag.get("crown_light", "none") != "none"
            crown = (lm["crown"] if lm else
                     (leds or (md.get("crowns", True) and
                               u(b["id"], "flood") < float(md.get("floods", 0.0)))))
            uplit = (lm["floods"] if lm else
                     md.get("crowns", True) and u(b["id"], "uplight") <
                     0.4 * float(md.get("floods", 0.0)) * float(md.get("wealth", 0.5)))
            if not crown and not uplit:
                continue
            color, temp_k, matched = self._flood_color(b, did)
            top = sh.base + sh.body_top
            if crown:
                hc = min(zmax, max(zmin, zs * sh.body_top))
                g = sh.crown[0]
                k = 0
                for side in sides(g):
                    if side[5] - side[4] < P.CROWN_SIDE_MIN_M:
                        continue
                    lats = [None] if side[5] - side[4] <= P.CROWN_SPLIT_M else \
                        [side[4] + 0.25 * (side[5] - side[4]),
                         side[4] + 0.75 * (side[5] - side[4])]
                    for tl in lats:
                        rec = self._flood(b=b, sh=sh, did=did, owner=b["id"],
                                          suffix=f"crown{k}", cls="crown_flood", g=g,
                                          side=side, tl=tl, z_light=top - hc - 1.0,
                                          z0=top - hc, z1=top, color=color, temp_k=temp_k,
                                          out=P.PHOTOMETRY["crown_flood"]["out_m"])
                        k += rec is not None
                if k:
                    self.flood_report["crowns"] += 1
                    self.flood_report["matched_leds"] += int(matched)
            if uplit:
                shaft = sh.shaft()
                if shaft is None:
                    continue
                up = min(P.FLOOD_UP_M[1], P.FLOOD_UP_M[0] * sh.body_top)
                k = 0
                for side in sides(shaft[0]):
                    if side[5] - side[4] < P.CROWN_SIDE_MIN_M:
                        continue
                    n, t, c, e_n, t0, t1 = side
                    tl = (t0 + t1) / 2.0
                    o = P.PHOTOMETRY["facade_flood"]["out_m"]
                    x = c[0] + n[0] * (e_n + o) + t[0] * tl
                    y = c[1] + n[1] * (e_n + o) + t[1] * tl
                    # (on the podium's roof under it, else the ground)
                    under = sh.top_under(x, y, 0.5 * sh.body_top)
                    zl = (sh.base + under if under is not None else self.c.ground(x, y)) + 0.5
                    rec = self._flood(b=b, sh=sh, did=did, owner=b["id"], suffix=f"up{k}",
                                      cls="facade_flood", g=shaft[0], side=side, tl=None,
                                      z_light=zl, z0=zl + 1.0, z1=zl + up,
                                      color=kelvin_linear(P.TEMPS[md.get("flood", "neutral")])
                                      if not lm or not lm["color"] else color,
                                      temp_k=None, out=o)
                    k += rec is not None
                self.flood_report["uplit"] += int(k > 0)

    def aviation(self) -> None:
        """Aviation warning lights (scope 6.1): on every building and megasite structure as
        tall as `AVIATION_MIN_M` over its base (`AVIATION_PORT_MIN_M` in a spaceport's
        district or megasite), red: flashing at its top (a mast's or spire's tip, else its
        roof's corners), all of a building's together, `AVIATION_BLINK`; steady at its
        corners every `AVIATION_STEP_M` under the top down to 45 m."""
        red = unit(hex_linear(P.AVIATION_COLOR))
        port_d = {did for did, md in self.moods.items() if md.get("archetype") == "spaceport"}
        port_s = {s["id"] for s in self.c.m.get("megasites", []) or []
                  if s.get("kind") == "spaceport"}
        per, duty = P.AVIATION_BLINK
        items = []
        for bid in sorted(self.c.buildings):
            b = self.c.buildings[bid]
            items.append((bid, b.get("district_id"), b.get("megasite_id"), b,
                          self.c.ground_at_base(b)))
        for e in sorted(self.c.m.get("site_elements", []) or [], key=lambda e: e["id"]):
            if e.get("masses"):
                fp = (e.get("footprint") or {}).get("exterior") or [[0.0, 0.0]]
                items.append((e["id"], self.c.district_of(e["id"]), e.get("megasite_id"),
                              e, self.c.ground(fp[0][0], fp[0][1]) + float(e.get("z_m", 0.0))))
        self.aviation_report = {"structures": 0, "flashing": 0, "steady": 0}
        for oid, did, msid, rec, base in items:
            tops = [float(m.get("z1_m", 0.0)) for m in rec.get("masses") or []]
            if not tops:
                continue
            need = P.AVIATION_PORT_MIN_M if (did in port_d or msid in port_s) else \
                P.AVIATION_MIN_M
            if max(tops) < need:
                continue
            sh = Shape(rec, base)
            if sh.tip is None:
                continue
            self.aviation_report["structures"] += 1
            anim = {"mode": "blink", "period_s": per, "amount": duty,
                    "phase": r3(math.floor(u(oid, "aviation") * 1000.0) / 1000.0)}
            k = 0
            g, _, z1, role = sh.tip
            pts = []
            if role in P.FLOOD_THIN_ROLES or g.area < 64.0:
                c = g.representative_point()
                pts.append((c.x, c.y, sh.base + z1 + 0.3))
            else:
                pts += [(x, y, sh.base + z1 + 0.4) for x, y in corners(g, 0.4)]
            for x, y, z in pts:
                self.add(owner=oid, suffix=f"aviation{k}", kind="aviation", cls="aviation",
                         did=did, pos=(x, y, z), aim=(0.0, -90.0), color=red,
                         cd=P.PHOTOMETRY["aviation"]["cd"], schedule="always",
                         mount="beacon", anim=anim)
                k += 1
                self.aviation_report["flashing"] += 1
            # the steady levels under the top, at the body's corners
            zl = sh.body_top - (P.AVIATION_STEP_M if sh.body_top >= z1 - 0.5 else 0.0)
            while zl >= 45.0:
                lv = sh.at(zl)
                if lv is not None:
                    for x, y in corners(lv[0], -0.4):
                        self.add(owner=oid, suffix=f"aviation{k}", kind="aviation",
                                 cls="aviation", did=did, pos=(x, y, sh.base + zl),
                                 aim=(0.0, -90.0), color=red,
                                 cd=P.PHOTOMETRY["aviation"]["cd"] * P.AVIATION_STEADY,
                                 schedule="always", mount="beacon")
                        k += 1
                        self.aviation_report["steady"] += 1
                zl -= P.AVIATION_STEP_M

    def searchlights(self) -> None:
        """Searchlights sweeping the sky from roofs (scope 6.1): every landmark's
        (`LandmarkLights.searchlights`, by its kind), and per district its mood's number on
        its tallest towers (else its tallest buildings over 30 m: a spaceport's control
        tower), two to a roof, from its corners; a sweep by hash (period, reach, phase), white
        or (in a district whose palette is its signs') a neon tint now and then."""
        jobs: list[tuple[dict, Shape, int]] = []
        tw = self._towers()
        for b, sh in tw:
            if b.get("landmark"):
                n = self._landmark(b)["searchlights"]
                if n:
                    jobs.append((b, sh, n))
        by_d: dict[str, list] = {}
        for b, sh in tw:
            if not b.get("landmark") and not (self.c.ag15().get(b["id"]) or {}).get("vacant"):
                by_d.setdefault(b.get("district_id") or "", []).append((b, sh))
        for did in sorted(self.moods):
            n = int(self.mood(did).get("searchlights", 0))
            if n <= 0:
                continue
            cands = sorted(by_d.get(did, []), key=lambda r: (-r[1].top, r[0]["id"]))
            if not cands:
                tall = [b for b in self.c.buildings.values() if b.get("district_id") == did
                        and float(b.get("height_m") or 0.0) >= 30.0 and not b.get("landmark")
                        and not (self.c.ag15().get(b["id"]) or {}).get("vacant")]
                cands = sorted(((b, Shape(b, self.c.ground_at_base(b))) for b in tall),
                               key=lambda r: (-r[1].top, r[0]["id"]))
            for b, sh in cands[: (n + 1) // 2]:
                if sh.crown is None:
                    continue
                jobs.append((b, sh, min(2, n)))
                n -= 2
        white = kelvin_linear(6500)
        lo_p, hi_p = P.SEARCHLIGHT_PITCH
        lo_a, hi_a = P.SEARCHLIGHT_SWEEP
        lo_t, hi_t = P.SEARCHLIGHT_PERIOD
        for b, sh, n in jobs:
            did = b.get("district_id")
            cs = corners(sh.crown[0], 2.0)
            if not cs:
                continue
            g = sh.crown[0].centroid
            z = sh.base + sh.body_top + 1.5
            for k in range(n):
                x, y = cs[(k * max(1, len(cs) // max(1, n))) % len(cs)]
                key = f"{b['id']}.search{k}"
                yaw = math.degrees(math.atan2(y - g.y, x - g.x)) + 60.0 * (u(key, "yaw") - 0.5)
                col = white
                if self.mood(did).get("archetype") == "entertainment_market" and \
                        u(key, "tint") < 0.5:
                    col = self.mood_color(did, key, "tint.c")
                self.add(owner=b["id"], suffix=f"search{k}", kind="searchlight",
                         cls="searchlight", did=did, pos=(x, y, z),
                         aim=(yaw, lo_p + (hi_p - lo_p) * u(key, "pitch")), color=col,
                         temp_k=6500 if col is white else None,
                         cd=P.PHOTOMETRY["searchlight"]["cd"], schedule="late", mount="roof",
                         anim={"mode": "sweep",
                               "period_s": r3(lo_t + (hi_t - lo_t) * u(key, "period")),
                               "amount": r3(lo_a + (hi_a - lo_a) * u(key, "amp")),
                               "phase": r3(math.floor(u(key, "phase") * 1000.0) / 1000.0)})

    # -- AT2: megasites (a port's yard and cranes, a spaceport's apron and pads) --

    def megasites(self) -> None:
        """A freight terminal's yard under high masts every `HIGH_MAST_STEP_M` (off its
        buildings and stacks) and its cranes' boom floods; a spaceport's apron with high masts
        along its long sides and blue edge lights round it, its launch pads' rims in green and
        white, each pad flooded from its launch tower (scope 6.1)."""
        from shapely.geometry import Point, Polygon
        els: dict[str, list] = {}
        for e in self.c.m.get("site_elements", []) or []:
            els.setdefault(e.get("megasite_id") or "", []).append(e)
        self.site_report: dict[str, int] = {}

        def count(k):
            self.site_report[k] = self.site_report.get(k, 0) + 1

        for ms in sorted(self.c.m.get("megasites", []) or [], key=lambda s: s["id"]):
            kind = ms.get("kind")
            ring = (ms.get("polygon") or {}).get("exterior") or []
            if kind not in ("freight_terminal", "spaceport") or len(ring) < 3:
                continue
            did = ms.get("district_id")
            md = self.mood(did)
            temp = P.TEMPS[md.get("temp", "neutral") if kind == "freight_terminal" else
                           md.get("flood", "neutral")]
            col = kelvin_linear(temp)
            site = Polygon(ring)
            if not site.is_valid:
                site = site.buffer(0)
            mine = sorted(els.get(ms["id"], []), key=lambda e: e["id"])
            solid = []
            for e in mine:
                for m_ in e.get("masses") or []:
                    ext = (m_.get("footprint") or {}).get("exterior") or []
                    if len(ext) >= 3:
                        solid.append(Polygon(ext).buffer(3.0))
            for b in self.c.buildings.values():
                if b.get("megasite_id") == ms["id"]:
                    ext = (b.get("footprint") or {}).get("exterior") or []
                    if len(ext) >= 3:
                        solid.append(Polygon(ext).buffer(3.0))
            from shapely import union_all
            blocked = union_all(solid) if solid else None

            def free(x, y):
                p = Point(x, y)
                return site.buffer(-4.0).contains(p) and \
                    (blocked is None or not blocked.contains(p))

            def mast(x, y, k, owner, cls="high_mast", aim=(0.0, -90.0), mount="mast",
                     kind_="high_mast"):
                z = self.c.ground(x, y) + P.HIGH_MAST_Z_M
                self.add(owner=owner, suffix=f"mast{k:03d}", kind=kind_, cls=cls, did=did,
                         pos=(x, y, z - P.PHOTOMETRY[cls]["drop_m"]), aim=aim, color=col,
                         temp_k=temp, cd=P.PHOTOMETRY[cls]["cd"], schedule="dusk_dawn",
                         mount=mount)
                count(kind_)

            if kind == "freight_terminal":
                x0, y0, x1, y1 = site.bounds
                st = P.HIGH_MAST_STEP_M
                k = 0
                nx = max(1, int(math.floor((x1 - x0) / st)))
                ny = max(1, int(math.floor((y1 - y0) / st)))
                for i in range(nx):
                    for j in range(ny):
                        x = x0 + (x1 - x0) * (i + 0.5) / nx
                        y = y0 + (y1 - y0) * (j + 0.5) / ny
                        # (off a stack or a building: the nearest free spot within 15 m)
                        for dx, dy in ((0, 0), (8, 0), (-8, 0), (0, 8), (0, -8), (15, 0),
                                       (-15, 0), (0, 15), (0, -15)):
                            if free(x + dx, y + dy):
                                mast(x + dx, y + dy, k, ms["id"])
                                k += 1
                                break
                for e in mine:
                    if e.get("kind") != "gantry_crane":
                        continue
                    boom = [m_ for m_ in e.get("masses") or [] if m_.get("role") == "boom"]
                    if not boom:
                        continue
                    g = Polygon(boom[0]["footprint"]["exterior"])
                    sd = sides(g)
                    if not sd:
                        continue
                    n_, t_, c_, e_n, t0, t1 = sd[0]
                    zb = self.c.ground(c_[0], c_[1]) + float(boom[0].get("z0_m", 42.0))
                    # (two floods under the boom's long axis, a quarter in from each end)
                    long_ = max(sd[:2], key=lambda s_: s_[5] - s_[4])
                    n_, t_, c_, e_n, t0, t1 = long_
                    for k2, f in enumerate((0.25, 0.75)):
                        tl = t0 + (t1 - t0) * f
                        self.add(owner=e["id"], suffix=f"boom{k2}", kind="flood",
                                 cls="boom_flood", did=did,
                                 pos=(c_[0] + t_[0] * tl, c_[1] + t_[1] * tl,
                                      zb - P.PHOTOMETRY["boom_flood"]["drop_m"]),
                                 aim=(0.0, -90.0), color=col, temp_k=temp,
                                 cd=P.PHOTOMETRY["boom_flood"]["cd"], schedule="dusk_dawn",
                                 mount="mast")
                        count("boom_flood")
                continue
            # a spaceport: its apron and pads
            blue = unit(hex_linear(P.GROUND_COLORS["apron"]))
            towers = [e for e in mine if e.get("kind") == "launch_tower"]
            for e in mine:
                ext = (e.get("footprint") or {}).get("exterior") or []
                if len(ext) < 3:
                    continue
                g = Polygon(ext)
                if e.get("kind") == "apron":
                    sd = sides(g)
                    k = 0
                    for side in sd:
                        n_, t_, c_, e_n, t0, t1 = side
                        if t1 - t0 < 0.6 * max(s_[5] - s_[4] for s_ in sd):
                            continue                         # (the long sides only)
                        m = max(1, int(round((t1 - t0) / P.APRON_MAST_STEP_M)))
                        for i in range(m):
                            tl = t0 + (t1 - t0) * (i + 0.5) / m
                            x = c_[0] + n_[0] * (e_n - 2.0) + t_[0] * tl
                            y = c_[1] + n_[1] * (e_n - 2.0) + t_[1] * tl
                            mast(x, y, k, e["id"])
                            k += 1
                    ring_ = list(g.exterior.coords)
                    ln = Line([(p[0], p[1]) for p in ring_])
                    m = max(4, int(round(ln.L / P.APRON_EDGE_STEP_M)))
                    for i in range(m):
                        x, y, _, tx, ty = ln.at(ln.L * i / m)
                        # (0.5 m in from the edge: the ring runs counterclockwise, in is left)
                        side_ = 1.0 if g.exterior.is_ccw else -1.0
                        x, y = x - ty * 0.5 * side_, y + tx * 0.5 * side_
                        self.add(owner=e["id"], suffix=f"edge{i:03d}", kind="runway",
                                 cls="ground_light", did=did,
                                 pos=(x, y, self.c.ground(x, y) + 0.15), aim=(0.0, -90.0),
                                 color=blue, cd=P.PHOTOMETRY["ground_light"]["cd"],
                                 schedule="dusk_dawn", mount="ground")
                        count("runway")
                elif e.get("kind") == "launch_pad":
                    c = g.centroid
                    r = float((e.get("attrs") or {}).get("radius_m") or
                              math.sqrt(g.area / math.pi)) + 0.5
                    top = max((float(m_.get("z1_m", 0.0)) for m_ in e.get("masses") or []),
                              default=0.0)
                    zg = self.c.ground(c.x, c.y)
                    m = max(8, int(round(2.0 * math.pi * r / P.PAD_RIM_STEP_M)))
                    for i in range(m):
                        a = 2.0 * math.pi * i / m
                        x, y = c.x + r * math.cos(a), c.y + r * math.sin(a)
                        tint = P.GROUND_COLORS["rim" if i % 2 == 0 else "rim_alt"]
                        self.add(owner=e["id"], suffix=f"rim{i:03d}", kind="runway",
                                 cls="ground_light", did=did, pos=(x, y, zg + top + 0.1),
                                 aim=(0.0, -90.0), color=unit(hex_linear(tint)),
                                 cd=P.PHOTOMETRY["ground_light"]["cd"], schedule="dusk_dawn",
                                 mount="ground")
                        count("runway")
                    # (flooded from the nearest launch tower's top)
                    if towers:
                        tw = min(towers, key=lambda t: (Polygon(
                            t["footprint"]["exterior"]).centroid.distance(c), t["id"]))
                        tc = Polygon(tw["footprint"]["exterior"]).centroid
                        tz = zg + max(float(m_.get("z1_m", 0.0)) for m_ in tw["masses"]) + 1.0
                        dh = math.hypot(c.x - tc.x, c.y - tc.y)
                        self.add(owner=e["id"], suffix="flood", kind="flood",
                                 cls="high_mast", did=did, pos=(tc.x, tc.y, tz),
                                 aim=(math.degrees(math.atan2(c.y - tc.y, c.x - tc.x)),
                                      -math.degrees(math.atan2(tz - zg, max(dh, 1.0)))),
                                 color=col, temp_k=temp, cd=P.PHOTOMETRY["high_mast"]["cd"],
                                 schedule="dusk_dawn", mount="roof")
                        count("pad_flood")

    # -- junction corners the lux check finds dark --

    def _corner_spots(self, j: dict, center) -> list[tuple[float, float, float]]:
        """Where a corner pole may stand at a junction: the junction ends of its legs'
        sidewalks and its crosswalks' ends (3 m apart at least), in order round its middle;
        else (a junction of roads without sidewalks) its outline's corners."""
        node = self.c.nodes.get(j.get("node_id") or "")
        if node is None:
            return []
        nx, ny = float(node["position"][0]), float(node["position"][1])
        spots = []
        for sid in self._legs.get(node["id"], []):
            for w in self._walks.get(sid, []):
                line = w.get("line") or []
                if len(line) < 2:
                    continue
                a, b = line[0], line[-1]
                e = a if math.dist(a[:2], (nx, ny)) <= math.dist(b[:2], (nx, ny)) else b
                spots.append((float(e[0]), float(e[1])))
        for cw in self._xwalks.get(j["id"], []):
            for e in (cw.get("line") or [])[:1] + (cw.get("line") or [])[-1:]:
                spots.append((float(e[0]), float(e[1])))
        if not spots:
            # (a junction of roads without sidewalks, alleys or service roads: its outline's
            # corners)
            ring = (j.get("polygon") or {}).get("exterior") or []
            spots = [(float(q[0]), float(q[1])) for q in ring]
        cx, cy = center[0], center[1]
        spots.sort(key=lambda p: (math.atan2(p[1] - cy, p[0] - cx), p[0], p[1]))
        out = []
        for p in spots:
            if all(math.dist(p, q) >= 3.0 for q in out):
                out.append(p)
        return out

    def corners(self, S, E: np.ndarray, levels: dict) -> np.ndarray:
        """Corner poles where the lights so far leave a junction dark: a junction whose lane
        points under the carriageway's minimum or crosswalk points under the crosswalk's
        exceed `UNDER_MIN_SHARE` gets, one at a time, the pole (at `_corner_spots`, its head
        `CORNER_POLE_Z_M` up on an arm toward the middle, a cobra head aimed into it) that
        leaves fewest of its points dark, until it passes or has `CORNER_MAX`. Returns E with
        their light added (the check's points)."""
        from . import lux as LX
        m = self.c.m
        occ = self.c.occluders()
        jc = self.junction_centers()
        self._legs: dict[str, list[str]] = {}
        for sid in sorted(self.c.segments):
            s = self.c.segments[sid]
            for nid in (s.get("start"), s.get("end")):
                if nid:
                    self._legs.setdefault(nid, []).append(sid)
        self._walks: dict[str, list] = {}
        for w in m.get("sidewalks", []):
            self._walks.setdefault(w.get("segment_id"), []).append(w)
        self._xwalks: dict[str, list] = {}
        for cw in m.get("crosswalks", []):
            self._xwalks.setdefault(cw.get("junction_id"), []).append(cw)
        lane_c = LX.CLASSES.index("carriageway")
        xw_c = LX.CLASSES.index("crosswalk")
        lane_min = float(levels["carriageway"][1])
        xw_min = float(levels["crosswalk"][1])
        jidx = np.flatnonzero(S.junction >= 0)
        order = jidx[np.argsort(S.junction[jidx], kind="stable")]
        keys = S.junction[order]
        starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]]) if keys.size else []
        ends = list(starts[1:]) + [keys.size] if keys.size else []
        jrec = {j["id"]: j for j in m.get("junctions", [])}
        rep = {"junctions": 0, "dark": 0, "lit": 0, "still_dark": 0, "poles": 0,
               "no_spot": 0}
        for a, b in zip(starts, ends):
            idx = order[a:b]
            jid = S.junction_ids[int(keys[a])]
            j = jrec.get(jid)
            if j is None or jid not in jc:
                continue
            rep["junctions"] += 1
            cls = S.cls[idx]
            lim = np.where(cls == lane_c, lane_min, np.where(cls == xw_c, xw_min, 0.0))
            cur = E[idx].copy()
            bad = int((cur < lim).sum())
            if bad <= P.UNDER_MIN_SHARE * idx.size:
                continue
            rep["dark"] += 1
            spots = self._corner_spots(j, jc[jid])
            if not spots:
                rep["no_spot"] += 1
                rep["still_dark"] += 1
                continue
            node = self.c.nodes[j["node_id"]]
            nz = float(node["position"][2]) if len(node["position"]) > 2 else 0.0
            did = self.c.district_of(jid) or self.c.district_at(jc[jid][0], jc[jid][1])
            xyz = S.xyz[idx]
            used: list[int] = []
            k = 0
            while k < P.CORNER_MAX and bad > P.UNDER_MIN_SHARE * idx.size:
                best = None
                for si, (x, y) in enumerate(spots):
                    if si in used:
                        continue
                    dx, dy = jc[jid][0] - x, jc[jid][1] - y
                    d = math.hypot(dx, dy) or 1.0
                    arm = min(P.CORNER_ARM_M, 0.5 * d)
                    rec = self.spot("cobra_head", owner=jid, suffix=f"corner{k}",
                                    kind="corner", did=did, x=x + dx / d * arm,
                                    y=y + dy / d * arm,
                                    z=self.c.ground(x, y) + nz + P.CORNER_POLE_Z_M,
                                    yaw=math.degrees(math.atan2(dy, dx)), mount="pole",
                                    commit=False)
                    e = LX.light_at(rec, xyz, occ, self.schedules)
                    left = int((cur + e < lim).sum())
                    if best is None or left < best[0]:
                        best = (left, si, rec, e)
                if best is None or best[0] >= bad:
                    break
                bad, si, rec, e = best
                used.append(si)
                self.lights.append(rec)
                cur += e
                ii, ee = LX.light_on(rec, S.points, occ, self.schedules)
                if ii.size:
                    np.add.at(E, ii, ee)
                rep["poles"] += 1
                k += 1
            if bad <= P.UNDER_MIN_SHARE * idx.size:
                rep["lit"] += 1
            else:
                rep["still_dark"] += 1
        self.corner_report = rep
        return E



    # -- the walkways and lanes the lights so far leave dark --

    def fill(self, S, E: np.ndarray, levels: dict) -> np.ndarray:
        """A light at the darkest point of every walkway or road (outside the junctions,
        which have their corners) the check still finds dark: `FILL_MIN_POINTS` of its points
        under its class's minimum, or an alley point dark; a round at a time, at most
        `FILL_ROUNDS`. By class: a wall pack on an alley's edge, a post top at a sidewalk's
        curb, a pole at a road's edge (a soffit light under a deck). Returns E with their
        light added; `fill_report` counts them by class."""
        from . import lux as LX
        occ = self.c.occluders()
        rep: dict[str, int] = {}
        n_own = len(S.owners)
        for rnd in range(P.FILL_ROUNDS):
            added = 0
            for c in ("alley", "under_deck", "sidewalk", "carriageway"):
                ci = LX.CLASSES.index(c)
                lim = float(levels[c][1])
                dark = (S.cls == ci) & (E < lim) & (S.junction < 0)
                if not dark.any():
                    continue
                idx = np.flatnonzero(dark)
                cnt = np.bincount(S.owner[idx], minlength=n_own)
                zero = np.bincount(S.owner[idx[E[idx] < P.ZERO_LX]], minlength=n_own)
                want = np.flatnonzero((cnt >= P.FILL_MIN_POINTS) |
                                      ((zero > 0) if c == "alley" else (cnt < 0)))
                for o in want.tolist():
                    pts = idx[S.owner[idx] == o]
                    k = int(pts[np.lexsort((pts, E[pts]))[0]])
                    if E[k] >= lim:
                        continue               # (lit by a fill light placed this round)
                    rec = self._fill_light(S, k, c, rnd)
                    if rec is None:
                        continue
                    ii, ee = LX.light_on(rec, S.points, occ, self.schedules)
                    if ii.size:
                        np.add.at(E, ii, ee)
                    rep[c] = rep.get(c, 0) + 1
                    added += 1
            if not added:
                break
        self.fill_report = dict(sorted(rep.items()))
        return E

    def _fill_light(self, S, k: int, c: str, rnd: int) -> dict | None:
        x, y, z = (float(v) for v in S.xyz[k])
        kind_, oid, sid, width = S.owners[int(S.owner[k])]
        seg = self.c.segments.get(sid or "")
        did = self.c.district_at(x, y)
        # the way to the road's middle (from the point to its segment's centerline)
        tx = ty = 0.0
        if seg is not None and len(seg.get("centerline") or []) >= 2:
            from shapely.geometry import LineString, Point
            ln = LineString([q[:2] for q in seg["centerline"]])
            q = ln.interpolate(ln.project(Point(x, y)))
            dx, dy = q.x - x, q.y - y
            d = math.hypot(dx, dy)
            if d > 0.05:
                tx, ty = dx / d, dy / d
        owner = f"{oid}.fill{rnd}"
        while any(L["id"].startswith(owner) for L in self.lights[-8:]):
            owner += "x"
        yaw = math.degrees(math.atan2(ty, tx)) if (tx or ty) else 0.0
        if c == "alley":
            # a wall pack on the facade at the alley's edge, across from its middle
            half = max(0.3, (float(seg.get("width_m", 4.0)) if seg else width) / 2.0 - 0.2)
            return self.spot("wall_pack", owner=owner, suffix="light", kind="alley", did=did,
                             x=x - tx * half, y=y - ty * half, z=z + P.ALLEY_PACK_Z_M, yaw=yaw,
                             mount="wall")
        if c == "under_deck":
            return self.spot("soffit", owner=owner, suffix="light", kind="soffit", did=did,
                             x=x, y=y, z=z + P.FILL_SOFFIT_Z_M, yaw=yaw, mount="canopy",
                             schedule="always", temp_key="spill")
        if c == "sidewalk":
            # a post top at the curb side of the walkway
            o = max(0.0, width / 2.0 - 0.4)
            return self.spot("post_top", owner=owner, suffix="light", kind="road", did=did,
                             x=x + tx * o, y=y + ty * o, z=z + P.PED_POST_Z_M, yaw=yaw,
                             mount="pole")
        # a carriageway: a pole at the road's edge on the point's side, its arm over the road
        if seg is not None:
            sw = max((seg.get("cross_section") or {}).get("sidewalk_m") or [0.0])
            half = float(seg.get("width_m", 8.0)) / 2.0
            from shapely.geometry import LineString, Point
            ln = LineString([q[:2] for q in seg["centerline"]])
            q = ln.interpolate(ln.project(Point(x, y)))
            o = half - sw + (0.6 if sw > 0 else 0.0) - P.ROAD_LIGHTS["service"][3]
            x, y = q.x - tx * max(0.0, o), q.y - ty * max(0.0, o)
        return self.spot("cobra_head", owner=owner, suffix="light", kind="road", did=did,
                         x=x, y=y, z=z + P.ROAD_LIGHTS["service"][2], yaw=yaw, mount="pole")


# --- the plan's files -------------------------------------------------------------------------

def _write(path: Path, text: str) -> bool:
    """Write only when the bytes change; True if written."""
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def build_plan(build: str | Path, spec_path: str | Path | None = None,
               out: str | Path | None = None, say=None) -> dict:
    """Write BUILD/atmos (or `out`): atmos_plan.json, lights/<tile>.json,
    unreal_contribution.atmos.json, atmos_report.json and .txt. Returns the report."""
    import time
    t0 = time.time()
    build = Path(build)
    od = Path(out) if out else build / OUT
    city = City(build)
    res = S.load_spec(spec_path, city.m)
    if not res.ok:
        raise ValueError("atmos spec: " + "; ".join(str(i) for i in res.issues))
    spec_text = dumps(S.dump(res.spec))
    filled = S.fill(res.spec, list(city.districts.values()))
    pl = Plan(city, filled)
    # AT3: the sun and the moon, the curves, the named hours; the schedules the sun sets
    sky = SK.make(filled, filled.get("sky"))
    pl.schedules.update(SK.schedules(sky))
    # AT4: the air's schedules (mist after dusk, smog, steam in the cool night)
    pl.schedules.update({k: list(v) for k, v in P.AIR_SCHEDULES.items()})
    tm = {}

    def timed(name, fn, *a):
        t = time.time()
        r = fn(*a)
        tm[name] = round(time.time() - t, 2)
        return r

    for name in ("lamps", "signals", "roads", "alleys", "decks", "tunnels", "stations",
                 "signs", "spill", "megasites", "floods", "aviation", "searchlights"):
        timed(name, getattr(pl, name))
    # the lux check (scope 8): the dark junctions' corner poles first, then every class
    from . import lux as LX
    levels = {k: tuple(v) for k, v in filled["light_levels"].items()}
    smp = timed("samples", LX.Samples, city)
    occ = timed("occluders", city.occluders)
    E = timed("lux", LX.illuminance_points, pl.lights, smp.points, occ, pl.schedules)
    E = timed("corners", pl.corners, smp, E, levels)
    E = timed("fill", pl.fill, smp, E, levels)
    lux = timed("check", LX.check, smp, E, levels)
    lux["corners"] = pl.corner_report
    lux["fill"] = pl.fill_report
    # AT2: the lit faces against their own walls, and what they throw across the street
    faces = timed("faces", LX.face_check, pl.face_walls, occ)
    faces["dimmed_for_opposite"] = pl.dimmed
    # AT3: the cloud deck lit from below by the plan's upward light
    ext = city.m.get("bounds") or (
        [min(L["pos"][0] for L in pl.lights), min(L["pos"][1] for L in pl.lights),
         max(L["pos"][0] for L in pl.lights), max(L["pos"][1] for L in pl.lights)]
        if pl.lights else [0.0, 0.0, 0.0, 0.0])
    g = timed("glow", SK.glow, sky, pl.lights, pl.schedules, ext)
    if g is not None:
        sky["glow"] = SK.write_glow(g, od)
        sky["upward_lm"] = round(g["upward_lm"])
    elif (od / SK.GLOW_FILE).is_file():
        (od / SK.GLOW_FILE).unlink()
    # AT6: the look's post and grade, a post per district and the raster that blends them
    from . import look as LK
    post, ras = timed("post", LK.make, filled, sky, city.m)
    if ras is not None:
        post["raster"] = LK.write(ras, od)
    elif (od / LK.RASTER_FILE).is_file():
        (od / LK.RASTER_FILE).unlink()
    # visible lights: the occluders the runtime marches a walker's line of sight through
    from . import sight as SI
    gm = city.ground_many if city._grid is not None else None
    sight = timed("sight", lambda: SI.write(
        SI.raster(occ, gm, decks=SI.road_decks(city.m, gm)), od))
    # AT4: the air: fog and smog volumes, steam and smoke emitters, their check
    from . import air as AR
    air = AR.Air(pl)
    for name in ("mist", "smog", "haze", "tunnel_haze", "street", "vents", "roofs", "stalls",
                 "chimneys"):
        timed(f"air.{name}", getattr(air, name))
    air.volumes.sort(key=lambda r: r["id"])
    air.emitters.sort(key=lambda r: r["id"])
    for what, rows in (("volume", air.volumes), ("emitter", air.emitters)):
        if len({r["id"] for r in rows}) != len(rows):
            raise RuntimeError(f"atmos plan: duplicate {what} ids")
    air_check = timed("air.check", air.check)
    air_set = air.settings(filled, sky)
    # AT5: the weather: the rain shadow, wetness and puddles (the masks), the drips, the states
    from . import weather as WE
    we = WE.Weather(pl, filled)
    timed("weather.covers", we.covers)
    timed("weather.surfaces", we.surfaces)
    timed("weather.spots", we.spots)
    timed("weather.masks", we.masks_of, od)
    timed("weather.drips", we.drips_of, od)
    we_check = timed("weather.check", we.check, od)
    we_set = we.settings()
    # AT7: the far city: every light the far view sees as cards past the live set
    from . import far as FA
    fa = FA.Far(pl.lights, smp.points, city.ground)
    timed("far", fa.make)
    far_index = timed("far.write", fa.write, od, city.name)
    far_check = timed("far.check", fa.check)
    far_set = fa.settings(far_index)
    by_tile: dict[str, list[dict]] = {}
    for L in sorted(pl.lights, key=lambda r: r["id"]):
        by_tile.setdefault(L["tile"], []).append(L)
    ids = [L["id"] for L in pl.lights]
    if len(ids) != len(set(ids)):
        raise RuntimeError("atmos plan: duplicate light ids")
    wrote, index = [], []
    for t in sorted(by_tile):
        doc = PM.TileLights(city=city.name, tile=t, bounds=tile_bounds(t),
                            lights=[PM.Light(**L) for L in by_tile[t]])
        text = dumps(json.loads(doc.model_dump_json(exclude_none=True))) + "\n"
        f = od / "lights" / f"{t}.json"
        if _write(f, text):
            wrote.append(str(f))
        kinds: dict[str, int] = {}
        for L in by_tile[t]:
            kinds[L["kind"]] = kinds.get(L["kind"], 0) + 1
        index.append(PM.TileIndex(tile=t, file=f"lights/{t}.json", count=len(by_tile[t]),
                                  kinds=dict(sorted(kinds.items())), sha256=sha(text)))
    # tiles that hold no light any more
    if (od / "lights").is_dir():
        for f in sorted((od / "lights").glob("t*.json")):
            if f.stem not in by_tile:
                f.unlink()
    counts: dict[str, int] = {}
    for L in pl.lights:
        counts[L["kind"]] = counts.get(L["kind"], 0) + 1
    counts["all"] = len(pl.lights)
    counts["broken"] = sum(1 for L in pl.lights if not L["on"])
    counts["flicker"] = sum(1 for L in pl.lights if L["flicker"] > 0)
    tiers = P.TIERS
    look = filled["look"]
    mounts: dict[str, int] = {}
    for L in pl.lights:
        mounts[L["mount"]] = mounts.get(L["mount"], 0) + 1
    plan = PM.AtmosPlan(
        city=city.name, model_sha256=city.model_sha256, spec_sha256=sha(spec_text),
        code=code_hash(), preset=filled["preset"], hour=filled["hour"],
        weather=filled["weather"], night_ev100=filled["night_ev100"], look=look,
        weather_state=filled["weather_state"],
        sky=PM.Sky(**sky),
        schedules={k: list(v) for k, v in sorted(pl.schedules.items())},
        districts=filled["moods"],
        tiers=PM.Tiers(near_m=tiers["near"]["radius_m"],
                       near_max=min(tiers["near"]["max"], filled["budgets"]["shadowed"]),
                       mid_m=tiers["mid"]["radius_m"],
                       mid_max=min(tiers["mid"]["max"], filled["budgets"]["live"]),
                       high_m=tiers["high"]["radius_m"],
                       high_max=min(tiers["high"]["max"], filled["budgets"].get("high", 48)),
                       far_m=tiers["far"]["radius_m"],
                       sight_m=tiers["sight"]["radius_m"],
                       sight_max=min(tiers["sight"]["max"], filled["budgets"]["live"])),
        budgets=filled["budgets"], tiles=index, counts=dict(sorted(counts.items())),
        sources={"derived": sum(1 for L in pl.lights if L["source"] == "derived"),
                 "assetgen": sum(1 for L in pl.lights if L["source"] == "assetgen")},
        air=PM.Air(**air_set),
        volumes=[PM.FogVolume(**v) for v in air.volumes],
        emitters=[PM.Emitter(**e) for e in air.emitters],
        sight=PM.Sight(**sight),
        post=PM.Post(**post),
        far=PM.Far(**far_set),
        masks=[PM.Mask(**mk) for mk in we.masks],
        weather_plan=PM.Weather(**we_set),
        checks={"lux": lux, "faces": faces, "air": air_check, "weather": we_check,
                "far": far_check})
    ptext = json.dumps(json.loads(plan.model_dump_json(by_alias=True, exclude={"schema_ref"})),
                       indent=1, sort_keys=True) + "\n"
    if _write(od / "atmos_plan.json", ptext):
        wrote.append(str(od / "atmos_plan.json"))
    contrib = PM.Contribution(
        city=city.name, plan="atmos_plan.json", plan_sha256=sha(ptext),
        entries=[PM.ContributionEntry(key="atmos", kind="controller", file="atmos_plan.json",
                                      hash=sha(ptext)[:16])] +
        [PM.ContributionEntry(key=f"atmos.lights.{i.tile}", kind="tile_lights", tile=i.tile,
                              file=i.file, hash=i.sha256[:16], count=i.count)
         for i in index] +
        [PM.ContributionEntry(key=f"atmos.weather.{mk['tile']}", kind="weather",
                              tile=mk["tile"], file=mk["file"], hash=mk["sha256"][:16],
                              count=next((d["count"] for d in we.drip_tiles
                                          if d["tile"] == mk["tile"]), 0))
         for mk in we.masks])
    ctext = json.dumps(json.loads(contrib.model_dump_json()), indent=1, sort_keys=True) + "\n"
    if _write(od / "unreal_contribution.atmos.json", ctext):
        wrote.append(str(od / "unreal_contribution.atmos.json"))
    per_tile = sorted((i.count for i in index), reverse=True)
    rep = {"city": city.name, "code": code_hash(), "preset": filled["preset"],
           "counts": plan.counts, "sources": plan.sources, "tiles": len(index),
           "max_per_tile": per_tile[0] if per_tile else 0,
           "budget_lights_per_cell": filled["budgets"]["lights_per_cell"],
           "over_budget_tiles": [i.tile for i in index
                                 if i.count > filled["budgets"]["lights_per_cell"]],
           "skipped": dict(sorted(pl.skipped.items())),
           "mounts": dict(sorted(mounts.items())),
           "asked": sum(v for k, v in mounts.items() if k in PM.ASKED),
           "lux": lux, "faces": faces, "air": air_check,
           "air_counts": air_set["counts"],
           "air_sources": {k: v for k, v in air.report.items() if k != "skipped"},
           "air_skipped": dict(sorted(air.report["skipped"].items())),
           "ok": lux["ok"] and faces["ok"] and air_check["ok"] and we_check["ok"] and
           far_check["ok"],
           "far": far_check,
           "weather": we_check, "weather_counts": we_set["counts"],
           "weather_stats": we_set["stats"],
           "weather_covers": dict(sorted(we.report["covers"].items())),
           "weather_skipped": dict(sorted(we.report["skipped"].items())),
           "floods": pl.flood_report, "aviation": pl.aviation_report,
           "megasites": dict(sorted(pl.site_report.items())),
           "tiers": {k: sum(1 for L in pl.lights if L["tier"] == k)
                     for k in ("near", "mid", "high")},
           "sight": {k: sight[k] for k in ("cell_m", "px", "occupied")},
           "timings": tm,
           "sky": {"hours": sky["hours"], "ev_day": sky["ev_day"], "ev_night": sky["ev_night"],
                   "moon": {k: sky["moon"][k] for k in ("phase", "lit", "share")},
                   "cloud_deck_m": sky["cloud_deck_m"], "cloud_cover": sky["cloud_cover"],
                   "upward_lm": sky["upward_lm"],
                   "glow": {k: v for k, v in (sky["glow"] or {}).items()
                            if k in ("max_luma_nits", "mean_nits", "peak_at", "px")}},
           "post": post_summary(post),
           "sign_colors_from_pages": city.signs.from_pages,
           "districts": {k: {x: v[x] for x in ("name", "archetype", "lamp", "temp", "grit",
                                                "flicker", "broken", "neon", "flood",
                                                "floods", "searchlights", "palette")}
                         for k, v in filled["moods"].items()},
           "seconds": round(time.time() - t0, 1)}
    rtext = json.dumps(rep, indent=1, sort_keys=True) + "\n"
    rep_stable = {k: v for k, v in rep.items() if k not in ("seconds", "timings")}
    old = od / "atmos_report.json"
    if not old.is_file() or {k: v for k, v in json.loads(old.read_text(encoding="utf-8")).items()
                             if k not in ("seconds", "timings")} != rep_stable:
        _write(old, rtext)
        _write(od / "atmos_report.txt", report_text(rep))
    rep["wrote"] = wrote
    rep["out"] = str(od)
    return rep


POST_REPORT = ("bloom", "flare", "grain", "chromatic", "vignette", "sharpen", "saturation",
               "contrast", "lift")


def post_summary(post: dict) -> dict:
    """AT6: the post's numbers for the report and the review: the exposure, the look's night
    and day, each district's night by name."""
    def few(s):
        out = {k: s[k] for k in POST_REPORT}
        out["shadows"] = s["shadows_gain"]
        out["highlights"] = s["highlights_gain"]
        return out
    return {"exposure": post["exposure"],
            "look": {w: few(post["base"][w]) for w in ("night", "day")},
            "districts": {d["name"] or did: {"grit": d["grit"], "night": few(d["night"]),
                                             "day": few(d["day"])}
                          for did, d in sorted(post["districts"].items())},
            "raster": ({k: post["raster"][k] for k in ("px", "cell_m")}
                       if post.get("raster") else None)}


def report_text(rep: dict) -> str:
    lines = [f"atmos plan: {rep['city']} ({rep['preset']}, {rep['code']})",
             f"lights: {rep['counts'].get('all', 0)} in {rep['tiles']} tiles (at most "
             f"{rep['max_per_tile']} in a tile; budget {rep['budget_lights_per_cell']})"]
    for k, v in sorted(rep["counts"].items()):
        if k != "all":
            lines.append(f"  {k}: {v}")
    lines.append("sources: " + ", ".join(f"{k} {v}" for k, v in sorted(rep["sources"].items()))
                 + " (derived until assetgen records lamp lenses and sign faces, section 4.1)")
    if rep["skipped"]:
        lines.append("without a light: " + "; ".join(f"{k} {v}" for k, v in
                                                     rep["skipped"].items()))
    if rep["over_budget_tiles"]:
        lines.append("tiles over budget: " + ", ".join(rep["over_budget_tiles"]))
    if rep.get("mounts"):
        lines.append("mounted on: " + ", ".join(f"{k} {v}" for k, v in rep["mounts"].items())
                     + f" ({rep.get('asked', 0)} on fixtures asked of stage 2: scope 4.1)")
    if rep.get("lux"):
        from .lux import check_text
        c = rep["lux"].get("corners") or {}
        lines.append(f"junctions: {c.get('dark', 0)} of {c.get('junctions', 0)} dark before "
                     f"their corner poles, {c.get('poles', 0)} poles, {c.get('still_dark', 0)} "
                     f"still dark")
        f = rep["lux"].get("fill") or {}
        if f:
            lines.append("filled dark stretches: " + ", ".join(f"{k} {v}" for k, v in f.items()))
        lines.append(check_text(rep["lux"]).rstrip())
    if rep.get("faces"):
        from .lux import face_text
        lines.append(face_text(rep["faces"]).rstrip())
    if rep.get("air"):
        from .air import check_text as air_text
        lines.append("air: " + ", ".join(f"{k} {v}" for k, v in
                                         sorted((rep.get("air_counts") or {}).items())))
        if rep.get("air_sources"):
            lines.append("  from: " + ", ".join(f"{k} {v}" for k, v in
                                                sorted(rep["air_sources"].items())))
        lines.append(air_text(rep["air"]).rstrip())
    if rep.get("weather"):
        from .weather import check_text as we_text
        lines.append("weather: covers " + ", ".join(
            f"{k} {v}" for k, v in sorted((rep.get("weather_covers") or {}).items())) +
            "; " + ", ".join(f"{k} {v}" for k, v in sorted((rep.get("weather_stats") or {})
                                                           .items())))
        lines.append(we_text(rep["weather"]).rstrip())
    if rep.get("far"):
        from .far import check_text as far_text
        lines.append(far_text(rep["far"]).rstrip())
    if rep.get("floods"):
        f = rep["floods"]
        lines.append(f"towers and landmarks: {f['towers']}, crowns flooded {f['crowns']} "
                     f"({f['matched_leds']} in their crown LEDs' accent, AG15), uplit "
                     f"{f['uplit']}, vacant {f['vacant']}")
    if rep.get("aviation"):
        a = rep["aviation"]
        lines.append(f"aviation lights: {a['flashing']} flashing, {a['steady']} steady, on "
                     f"{a['structures']} structures")
    if rep.get("megasites"):
        lines.append("megasites: " + ", ".join(f"{k} {v}" for k, v in rep["megasites"].items()))
    if rep.get("tiers"):
        lines.append("tiers: " + ", ".join(f"{k} {v}" for k, v in rep["tiers"].items()))
    if rep.get("sight"):
        s = rep["sight"]
        lines.append(f"sight raster (a walker's visible lights): {s['px'][0]} x {s['px'][1]} "
                     f"cells of {s['cell_m']:g} m, {100.0 * s['occupied']:.1f}% occupied")
    if rep.get("sky"):
        s = rep["sky"]
        g = s.get("glow") or {}
        lines.append(f"sky: day {s['hours']['day']:g} h, dusk {s['hours']['dusk']:g} h, night "
                     f"{s['hours']['night']:g} h; exposure {s['ev_day']:g} EV100 by day, "
                     f"{s['ev_night']:g} by night; moon phase {s['moon']['phase']:g} "
                     f"({s['moon']['lit']:g} lit); deck {s['cloud_deck_m']:g} m, cover "
                     f"{s['cloud_cover']:g}" + (
                         f", its glow up to {g['max_luma_nits']:g} cd/m2 ({g['mean_nits']:g} "
                         f"over the city) from {s['upward_lm'] / 1e6:.2f} Mlm up" if g else ""))
    if rep.get("post"):
        p = rep["post"]
        ex = p["exposure"]
        lines.append(f"post: exposure {ex['night_ev100']:g} EV100 by night, "
                     f"{ex['day_ev100']:g} by day (overcast given back "
                     f"{ex['overcast_comp']:g})")
        for name, s in [("the look", p["look"])] + list(p["districts"].items()):
            n = s["night"]
            lines.append(f"  {name}" + (f" (grit {s['grit']:g})" if "grit" in s else "") +
                         f": bloom {n['bloom']:g}, flare {n['flare']:g}, grain "
                         f"{n['grain']:g}, fringe {n['chromatic']:g}, vignette "
                         f"{n['vignette']:g}, sharpen {n['sharpen']:g}, saturation "
                         f"{n['saturation']:g}, contrast {n['contrast']:g}, lift {n['lift']:g}, "
                         f"shadows x{n['shadows']}, highlights x{n['highlights']} (night)")
    lines.append("district moods:")
    for did, m in sorted(rep["districts"].items()):
        lines.append(f"  {did} {m['name']} ({m['archetype']}): {m['lamp']}, {m['temp']}, "
                     f"grit {m['grit']}, flicker {m['flicker']}, broken {m['broken']}, "
                     f"neon {m['neon']}, floods {m['flood']} {m['floods']}, searchlights "
                     f"{m['searchlights']}, palette {' '.join(m['palette'])}")
    return "\n".join(lines) + "\n"
