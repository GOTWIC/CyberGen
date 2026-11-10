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
from . import spec as S

CODE_FILES = ("presets.py", "spec.py", "planmodel.py", "emitters.py", "plan.py", "lux.py")
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
    return f"at1.{h.hexdigest()[:12]}"


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

    def mood(self, did: str | None) -> dict:
        return self.moods.get(did or "", None) or S.mood(None, None, None)

    def add(self, *, owner: str, suffix: str, kind: str, cls: str, did: str | None,
            pos, aim, color, cd: float, schedule: str, temp_k: int | None = None,
            size=None, tier: str = "mid", mount: str = "prop") -> dict:
        ph = P.PHOTOMETRY[cls]
        md = self.mood(did)
        lid = f"{owner}.{suffix}"
        # (a shopfront's light seldom flickers: a tube in its window now and then; tunnels,
        # stations and deck soffits are kept)
        flick = md["flicker"] * (0.3 if kind == "spill" else 1.0)
        kept = kind in ("tunnel", "underpass", "station", "soffit")
        rec = {"id": lid, "owner_id": owner, "kind": kind, "cls": cls, "shape": ph["shape"],
               "district_id": did, "tile": tile_of(pos[0], pos[1]),
               "pos": [mm(pos[0]), mm(pos[1]), mm(pos[2])], "aim": _aim(*aim),
               "cd": round(cd, 1), "color": color, "reach_m": ph["reach_m"],
               "shadow": bool(ph.get("shadow", False)), "tier": tier, "schedule": schedule,
               "flicker": r3(0.35 + 0.5 * u(lid, "depth"))
               if not kept and u(lid, "flicker") < flick else 0.0,
               # (a corner pole or a fill light is the check's own answer: never broken)
               "on": kept or kind == "corner" or ".fill" in owner or
               not (u(lid, "broken") < md["broken"]),
               "source": "derived",
               "mount": mount,
               "specular": 0.0 if kind in P.NO_SPECULAR_KINDS else 1.0}
        if temp_k is not None:
            rec["temp_k"] = int(temp_k)
        if ph["shape"] == "rect":
            rec["size"] = [mm(size[0]), mm(size[1])]
            rec["barn_deg"] = ph["barn_deg"]
        else:
            rec["source_m"] = ph.get("source_m", 0.0)
        if ph["shape"] == "spot":
            rec["cone"] = [ph["inner"], ph["outer"]]
        # (the hash of the record as the tile file writes it: the schema's defaults in)
        rec = json.loads(PM.Light(**rec, hash="").model_dump_json(exclude_none=True))
        rec.pop("hash")
        rec["hash"] = sha(dumps(rec))[:16]
        self.lights.append(rec)
        return rec

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
            if kind not in ("elevated", "underground") or len(fp) < 3:
                if kind == "sky":
                    self.skip("station: a sky station's platform is in its tower (AT2)")
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
            levels = [track + 1.0] if kind == "elevated" else \
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
        for s in self.c.m.get("sign_slots", []):
            kind = s.get("kind")
            cls = P.SIGN_CLASS.get(kind)
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
            col = self.c.signs.color(s["id"])
            if col is None:
                pal = md.get("palette") or list(P.NEON)
                col = pal[int(u(s["id"], "color") * len(pal)) % len(pal)]
            ph = P.PHOTOMETRY[cls]
            base = self.c.base.get(s.get("building_id") or "", 0.0)
            near = "near" if kind in P.SIGN_NEAR_ONLY else "mid"
            sched = "late" if kind in ("neon", "banner") else (
                "sign" if kind != "shop_sign" else "late")
            for k, face in enumerate(EM.sign_face(s)):
                w, h = face["size"]
                a = math.radians(face["yaw"])
                cx = face["c"][0] + ph["out_m"] * math.cos(a)
                cy = face["c"][1] + ph["out_m"] * math.sin(a)
                cz = face["c"][2] + base
                self.add(owner=s["id"], suffix=f"light{k}" if k else "light",
                         kind="shop_sign" if kind == "shop_sign" else "sign", cls=cls,
                         did=did, pos=(cx, cy, cz), aim=(face["yaw"], 0.0),
                         color=hex_linear(col), cd=ph["nits"] * w * h, schedule=sched,
                         size=(w, h), tier=near, mount="sign")

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
                    e = LX.light_at(rec, xyz, occ, P.SCHEDULES)
                    left = int((cur + e < lim).sum())
                    if best is None or left < best[0]:
                        best = (left, si, rec, e)
                if best is None or best[0] >= bad:
                    break
                bad, si, rec, e = best
                used.append(si)
                self.lights.append(rec)
                cur += e
                ii, ee = LX.light_on(rec, S.points, occ, P.SCHEDULES)
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
                    ii, ee = LX.light_on(rec, S.points, occ, P.SCHEDULES)
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
    tm = {}

    def timed(name, fn, *a):
        t = time.time()
        r = fn(*a)
        tm[name] = round(time.time() - t, 2)
        return r

    for name in ("lamps", "signals", "roads", "alleys", "decks", "tunnels", "stations",
                 "signs", "spill"):
        timed(name, getattr(pl, name))
    # the lux check (scope 8): the dark junctions' corner poles first, then every class
    from . import lux as LX
    levels = {k: tuple(v) for k, v in filled["light_levels"].items()}
    smp = timed("samples", LX.Samples, city)
    occ = timed("occluders", city.occluders)
    E = timed("lux", LX.illuminance_points, pl.lights, smp.points, occ, P.SCHEDULES)
    E = timed("corners", pl.corners, smp, E, levels)
    E = timed("fill", pl.fill, smp, E, levels)
    lux = timed("check", LX.check, smp, E, levels)
    lux["corners"] = pl.corner_report
    lux["fill"] = pl.fill_report
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
        sky=PM.Sky(moon=look["moon"], stars=look["stars"], cloud_deck_m=look["cloud_deck_m"],
                   cloud_glow=look["cloud_glow"]),
        schedules={k: list(v) for k, v in sorted(P.SCHEDULES.items())},
        districts=filled["moods"],
        tiers=PM.Tiers(near_m=tiers["near"]["radius_m"],
                       near_max=min(tiers["near"]["max"], filled["budgets"]["shadowed"]),
                       mid_m=tiers["mid"]["radius_m"],
                       mid_max=min(tiers["mid"]["max"], filled["budgets"]["live"]),
                       far_m=tiers["far"]["radius_m"]),
        budgets=filled["budgets"], tiles=index, counts=dict(sorted(counts.items())),
        sources={"derived": sum(1 for L in pl.lights if L["source"] == "derived"),
                 "assetgen": sum(1 for L in pl.lights if L["source"] == "assetgen")},
        checks={"lux": lux})
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
         for i in index])
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
           "lux": lux, "ok": lux["ok"],
           "timings": tm,
           "sign_colors_from_pages": city.signs.from_pages,
           "districts": {k: {x: v[x] for x in ("name", "archetype", "lamp", "temp", "grit",
                                                "flicker", "broken", "neon")}
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
    lines.append("district moods:")
    for did, m in sorted(rep["districts"].items()):
        lines.append(f"  {did} {m['name']} ({m['archetype']}): {m['lamp']}, {m['temp']}, "
                     f"grit {m['grit']}, flicker {m['flicker']}, broken {m['broken']}, "
                     f"neon {m['neon']}")
    return "\n".join(lines) + "\n"
