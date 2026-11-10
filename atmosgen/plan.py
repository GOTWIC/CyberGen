"""`atmosgen plan BUILD`: the atmos plan of a built city (scope 4.2, 7).

AT0 places the lights the spike measures: every street and wall light at its lamp head (a
light by photometric class: cobra heads that throw across the carriageway, post tops, wall
packs), every sign slot's lit face as a rect light in its sign's color (billboards, banners,
neon bands, holo-boards, shop signs), and every ground-floor unit's shopfront spilling onto
its sidewalk; each with its schedule for every hour (decision 12.3), its district's mood
(temperature, flicker, broken lights, neon density: clean where wealthy and safe, gritty in
markets, old towns and poor districts, decision 12.5), its tier and hash. AT1 and AT2 add
the rest of 6.1 and the lux check (scope 8); the volumes, emitters and masks follow in AT4
and AT5.

Deterministic: draws are blake2b hashes of ids, coordinates on the millimeter grid, colors
to 1/1000, canonical JSON; a file is written only when its bytes change.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from . import emitters as EM
from . import planmodel as PM
from . import presets as P
from . import spec as S

CODE_FILES = ("presets.py", "spec.py", "planmodel.py", "emitters.py", "plan.py")
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
    return f"at0.{h.hexdigest()[:12]}"


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
        self.base = {b["id"]: float(b["base_m"]) for b in self.m.get("buildings", [])
                     if b.get("base_m") is not None}
        self.signs = EM.SignColors(build / "assets")
        self._ground = None
        if self.m.get("terrain"):
            from assetgen.brief import load_model
            from assetgen.streets.ctx import Ground
            model, _, _ = load_model(build)
            self._ground = Ground(model)

    def ground(self, x: float, y: float) -> float:
        return float(self._ground.at(x, y)) if self._ground is not None else 0.0

    def district_of(self, pid: str) -> str | None:
        """A record's district from its id's prefix (M10's ids start with the district's)."""
        d = pid.split(".", 1)[0]
        return d if d in self.districts else None


# --- the lights -------------------------------------------------------------------------------

class Plan:
    def __init__(self, city: City, filled: dict):
        self.c = city
        self.f = filled
        self.moods = filled["moods"]
        self.lights: list[dict] = []
        self.skipped: dict[str, int] = {}

    def mood(self, did: str | None) -> dict:
        return self.moods.get(did or "", None) or S.mood(None, None, None)

    def add(self, *, owner: str, suffix: str, kind: str, cls: str, did: str | None,
            pos, aim, color, cd: float, schedule: str, temp_k: int | None = None,
            size=None, tier: str = "mid") -> None:
        ph = P.PHOTOMETRY[cls]
        md = self.mood(did)
        lid = f"{owner}.{suffix}"
        # (a shopfront's light seldom flickers: a tube in its window now and then)
        flick = md["flicker"] * (0.3 if kind == "spill" else 1.0)
        rec = {"id": lid, "owner_id": owner, "kind": kind, "cls": cls, "shape": ph["shape"],
               "district_id": did, "tile": tile_of(pos[0], pos[1]),
               "pos": [mm(pos[0]), mm(pos[1]), mm(pos[2])], "aim": _aim(*aim),
               "cd": round(cd, 1), "color": color, "reach_m": ph["reach_m"],
               "shadow": bool(ph.get("shadow", False)), "tier": tier, "schedule": schedule,
               "flicker": r3(0.35 + 0.5 * u(lid, "depth")) if u(lid, "flicker") < flick
               else 0.0,
               "on": not (u(lid, "broken") < md["broken"]), "source": "derived"}
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

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1

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
                         size=(w, h), tier=near)

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
                         schedule=P.USE_SCHEDULE.get(use, "shop"), size=(w, hh))


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
    pl.lamps()
    pl.signs()
    pl.spill()
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
                 "assetgen": sum(1 for L in pl.lights if L["source"] == "assetgen")})
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
           "sign_colors_from_pages": city.signs.from_pages,
           "districts": {k: {x: v[x] for x in ("name", "archetype", "lamp", "temp", "grit",
                                                "flicker", "broken", "neon")}
                         for k, v in filled["moods"].items()},
           "seconds": round(time.time() - t0, 1)}
    rtext = json.dumps(rep, indent=1, sort_keys=True) + "\n"
    rep_stable = {k: v for k, v in rep.items() if k != "seconds"}
    old = od / "atmos_report.json"
    if not old.is_file() or {k: v for k, v in json.loads(old.read_text(encoding="utf-8")).items()
                             if k != "seconds"} != rep_stable:
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
    lines.append("district moods:")
    for did, m in sorted(rep["districts"].items()):
        lines.append(f"  {did} {m['name']} ({m['archetype']}): {m['lamp']}, {m['temp']}, "
                     f"grit {m['grit']}, flicker {m['flicker']}, broken {m['broken']}, "
                     f"neon {m['neon']}")
    return "\n".join(lines) + "\n"
