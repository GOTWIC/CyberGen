"""AT7: the far city (scope 6.6): the plan's lights as light cards past the live set.

The runtime keeps live only the lights near the view (the circle's 300 m, the high tier's
750 m, a walker's 1,200 m by sight); past them a light is no light at all, and the streets of
the far city went dark between their windows (the play features' light pools stood under the
nearest 768 lamps past the live range, AT1). Here every light the far view would see gets
cards of its own (`presets.FAR`, by photometric class):

- **glow**: the fixture itself, a soft dot at its lens turned to the eye: `glow` of the
  light's intensity seen sideways (a cobra head's lens, a high mast's cluster, an aviation
  light all of it, blinking as it does), at least `FAR_PX` pixels wide in the runtime.
- **pool**: where a light aimed down lands, a disc on the surface under it (the walkways and
  lanes within `FAR_SURFACE_M` of its middle, a raised road's deck too, else the ground),
  lit as the light lights it: at its middle the illuminance $E_0 = I \\cos^3\\tau / h^2$ (the
  aim tilted $\\tau$ off straight down), shown as the luminance $E_0 \\rho / \\pi$, falling off
  as a point light's illuminance does, $(1 + (r/h)^2)^{-3/2}$, to $h \\tan(70^\\circ)$ or its
  reach.
- **wash**: a crown flood's or facade uplight's lit patch on its facade: the class's design
  illuminance there (`PHOTOMETRY[...]["lux"]`) as $E \\rho / \\pi$, a flat card on the facade
  (facing back along the aim's heading, `FAR_WASH_OUT_M` off the wall) where the aim meets it
  ($d = \\sqrt{I \\cos\\theta / E}$ along it: `plan._flood` sets $I = E d^3 / d_h$), as wide
  as the cone there and as tall as the lit zone (from a meter over the light to the top its
  reach gives), soft at its edges.

Each card keeps its light's schedule, color and tier (where it fades in: `mid` past the
street's live range, `high` past the high tier's, `fixture` past the beacons' 832 m), and its
id is its light's with `.far` and its type. Broken lights have none. Signs, neon, shopfronts
and lit windows need none: the instanced HLODs past World Partition's loading range keep
their emissive surfaces (AG16's per-instance data).

Written per 256 m tile (`far/<tile>.json`, `planmodel.TileFar`) with the plan's `far`
summary; the check (`check`): every lamp that lights a street with its pool or a reason,
every aviation light with its glow, every card's numbers finite and positive, at most
`FAR_BUDGETS["cards_per_tile"]` cards a tile. `preview` draws the far city by night from above
and from 150 m over its edge (`preview_far.png`).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import planmodel as PM
from . import presets as P

FILE = "preview_far.png"
DIR = "far"
# the kinds whose pools the check asks for (the lamps that light a street)
POOL_KINDS = ("street_light", "wall_light", "road", "alley", "signal", "corner",
              "high_mast")


def _unit_aim(yaw: float, pitch: float) -> tuple[float, float, float]:
    a, p = math.radians(yaw), math.radians(pitch)
    return math.cos(p) * math.cos(a), math.cos(p) * math.sin(a), math.sin(p)


class Far:
    """The far cards of a plan's lights (`make`), by tile (`write`), and the check."""

    def __init__(self, lights: list[dict], points, ground):
        """`lights` the plan's, `points` the lux check's sample points (`lux.Points`,
        absolute xyz), `ground(x, y)` the finished ground."""
        from . import plan as PL      # (its helpers; plan imports this module late)
        self.PL = PL
        self.lights = lights
        self.points = points
        self.ground = ground
        self.cards: list[dict] = []
        self.skipped: dict[str, int] = {}
        self.pool_of: dict[str, bool] = {}

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1

    def _rec(self, L: dict, typ: str, pos, value: float, size: float, h: float = 0.0,
             yaw: float | None = None) -> dict:
        PL = self.PL
        tier = ("fixture" if L["kind"] == "aviation" else
                "high" if L["tier"] == "high" else "mid")
        rec = {"id": f"{L['id']}.far.{typ}", "light_id": L["id"], "type": typ, "tier": tier,
               "kind": L["kind"], "district_id": L.get("district_id"),
               "tile": PL.tile_of(pos[0], pos[1]),
               "pos": [PL.mm(pos[0]), PL.mm(pos[1]), PL.mm(pos[2])],
               "color": [PL.r3(c) for c in L["color"]], "value": round(float(value), 3),
               "size_m": PL.r3(size), "h_m": PL.r3(h), "schedule": L["schedule"]}
        if yaw is not None:
            rec["yaw"] = PL.mm(((yaw + 180.0) % 360.0) - 180.0)
        an = L.get("anim")
        if an and an.get("mode") == "blink":
            rec["anim"] = dict(an)
        rec = json.loads(PM.FarCard(**rec, hash="").model_dump_json(exclude_none=True))
        rec.pop("hash")
        rec["hash"] = PL.sha(PL.dumps(rec))[:16]
        return rec

    def _surface(self, x: float, y: float, z: float) -> float:
        """The surface a light at (x, y, z) lands on: the highest walkway or lane point within
        `FAR_SURFACE_M` of (x, y) under it, else the ground."""
        idx = self.points.near(x, y, P.FAR_SURFACE_M) if self.points is not None else []
        if len(idx):
            q = self.points.xyz[np.asarray(idx)]
            d2 = (q[:, 0] - x) ** 2 + (q[:, 1] - y) ** 2
            ok = (d2 <= P.FAR_SURFACE_M ** 2) & (q[:, 2] < z - 0.5)
            if ok.any():
                return float(q[ok, 2].max())
        return float(self.ground(x, y))

    def make(self) -> list[dict]:
        for L in self.lights:
            spec = P.FAR.get(L["cls"])
            if spec is None:
                continue
            if not L.get("on", True):
                self.skip(f"{L['kind']}: broken")
                continue
            x, y, z = L["pos"]
            yaw, pitch = L["aim"]
            cd = float(L["cd"])
            if spec.get("glow"):
                size = max(P.FAR_GLOW_MIN_M, 2.0 * float(L.get("source_m") or 0.0))
                self.cards.append(self._rec(L, "glow", (x, y, z), spec["glow"] * cd, size))
            if spec.get("pool"):
                self._pool(L, x, y, z, yaw, pitch, cd)
            if spec.get("wash"):
                self._wash(L, x, y, z, yaw, pitch, cd)
        self.cards.sort(key=lambda r: r["id"])
        if len({r["id"] for r in self.cards}) != len(self.cards):
            raise RuntimeError("atmos plan: duplicate far card ids")
        return self.cards

    def _pool(self, L, x, y, z, yaw, pitch, cd) -> None:
        if L["shape"] == "point":
            tilt = 0.0
        else:
            tilt = max(0.0, 90.0 + pitch)          # (off straight down)
        if tilt >= 60.0:
            self.skip(f"{L['kind']}: aimed too far from down for a pool")
            self.pool_of[L["id"]] = False
            return
        sz = self._surface(x, y, z)
        h = z - sz
        if h < P.FAR_POOL_MIN_H:
            self.skip(f"{L['kind']}: too low over its surface for a pool")
            self.pool_of[L["id"]] = False
            return
        off = h * math.tan(math.radians(tilt))
        a = math.radians(yaw)
        cx, cy = x + off * math.cos(a), y + off * math.sin(a)
        if off > 0.5:
            sz2 = self._surface(cx, cy, z)
            if z - sz2 >= P.FAR_POOL_MIN_H:
                sz, h = sz2, z - sz2
        ct = math.cos(math.radians(tilt))
        e0 = cd * ct ** 3 / (h * h)
        lum = e0 * P.FAR_ALBEDO["pool"] / math.pi
        r = min(float(L["reach_m"]), h * math.tan(math.radians(P.FAR_POOL_DEG)))
        self.cards.append(self._rec(L, "pool", (cx, cy, sz + P.FAR_POOL_UP_M), lum, r, h))
        self.pool_of[L["id"]] = True

    def _wash(self, L, x, y, z, yaw, pitch, cd) -> None:
        ph = P.PHOTOMETRY[L["cls"]]
        e = float(ph.get("lux") or 0.0)
        ct = math.cos(math.radians(pitch))
        if e <= 0.0 or ct <= 0.05:
            self.skip(f"{L['kind']}: no patch to wash")
            return
        reach = float(L["reach_m"])
        d = min(reach, math.sqrt(cd * ct / e))
        ux, uy, uz = _unit_aim(yaw, pitch)
        outer = float((L.get("cone") or [20.0, 36.0])[1])
        # the lit zone: from a meter over the light to its top, which `plan._flood`'s reach
        # gives (reach = 1.15 hypot(d_h + 1, z1 - z) + 2); as wide as the cone there
        dh = d * ct
        z0 = z + 1.0
        z1 = z + math.sqrt(max(0.0, ((reach - 2.0) / 1.15) ** 2 - (dh + 1.0) ** 2))
        half_h = max(2.0, (z1 - z0) / 2.0)
        half_w = min(P.FAR_WASH_MAX_M, max(3.0, d * math.tan(math.radians(0.8 * outer))))
        lum = e * P.FAR_ALBEDO["wash"] / math.pi
        # (a flat card on the facade, facing back along the aim's heading, stood
        # `FAR_WASH_OUT_M` off the wall: `size_m` its half width, `h_m` its half height)
        a = math.radians(yaw)
        o = P.FAR_WASH_OUT_M
        pos = (x + ux * d - math.cos(a) * o, y + uy * d - math.sin(a) * o, z0 + half_h)
        self.cards.append(self._rec(L, "wash", pos, lum, half_w, half_h, yaw=yaw + 180.0))

    # -- the tiles and the check --

    def write(self, od: Path, city: str) -> list[dict]:
        """`far/<tile>.json` per tile (only when its bytes change; tiles with none removed);
        the index ({tile, file, count, sha256})."""
        PL = self.PL
        by: dict[str, list] = {}
        for r in self.cards:
            by.setdefault(r["tile"], []).append(r)
        index = []
        for t in sorted(by):
            doc = PM.TileFar(city=city, tile=t, bounds=PL.tile_bounds(t),
                             cards=[PM.FarCard(**r) for r in by[t]])
            text = PL.dumps(json.loads(doc.model_dump_json(exclude_none=True))) + "\n"
            PL._write(od / DIR / f"{t}.json", text)
            index.append({"tile": t, "file": f"{DIR}/{t}.json", "count": len(by[t]),
                          "sha256": PL.sha(text)})
        if (od / DIR).is_dir():
            for f in sorted((od / DIR).glob("t*.json")):
                if f.stem not in by:
                    f.unlink()
        return index

    def counts(self) -> dict:
        out = {t: 0 for t in P.FAR_TYPES}
        for r in self.cards:
            out[r["type"]] += 1
        out["all"] = len(self.cards)
        return out

    def check(self) -> dict:
        """Coverage and budgets (scope 8): every street-lighting lamp on with its pool or a
        reason (`skipped`), every aviation light on with its glow; every card's numbers finite
        and positive; at most `FAR_BUDGETS` cards a tile."""
        glows = {r["light_id"] for r in self.cards if r["type"] == "glow"}
        missing = []
        for L in self.lights:
            if not L.get("on", True) or L["cls"] not in P.FAR:
                continue
            if L["kind"] in POOL_KINDS and P.FAR[L["cls"]].get("pool") and \
                    L["id"] not in self.pool_of:
                missing.append((L["id"], "no pool"))
            if L["kind"] == "aviation" and L["id"] not in glows:
                missing.append((L["id"], "no glow"))
        bad = [r["id"] for r in self.cards
               if not all(math.isfinite(v) for v in r["pos"] + [r["value"], r["size_m"]])
               or r["value"] <= 0.0 or r["size_m"] <= 0.0
               or (r["type"] == "pool" and r["h_m"] <= 0.0)]
        per: dict[str, int] = {}
        for r in self.cards:
            per[r["tile"]] = per.get(r["tile"], 0) + 1
        cap = P.FAR_BUDGETS["cards_per_tile"]
        over = sorted(t for t, n in per.items() if n > cap)
        return {"ok": not missing and not bad and not over, "cards": len(self.cards),
                "counts": self.counts(), "max_per_tile": max(per.values()) if per else 0,
                "budgets": dict(P.FAR_BUDGETS), "over_budget_tiles": over,
                "missing": len(missing), "bad": len(bad),
                "examples": [f"{i}: {w}" for i, w in missing[:5]] + bad[:5],
                "pools_skipped": sum(1 for v in self.pool_of.values() if not v),
                "skipped": dict(sorted(self.skipped.items()))}

    def settings(self, index: list[dict]) -> dict:
        return {"tiles": index, "counts": self.counts(), "gain": P.FAR_GAIN,
                "px": P.FAR_PX, "spread": P.FAR_SPREAD, "fade": P.FAR_FADE,
                "pool_up_m": P.FAR_POOL_UP_M, "albedo": dict(P.FAR_ALBEDO)}


def check_text(c: dict) -> str:
    n = c["counts"]
    s = (f"far check: {'PASS' if c['ok'] else 'FAIL'}: {c['cards']} cards ({n['glow']} glows, "
         f"{n['pool']} pools, {n['wash']} washes), at most {c['max_per_tile']} in a tile "
         f"(budget {c['budgets']['cards_per_tile']})")
    if c["missing"] or c["bad"]:
        s += f"; {c['missing']} lights without their card, {c['bad']} cards bad: " + \
            "; ".join(c["examples"])
    if c["over_budget_tiles"]:
        s += "; over budget: " + ", ".join(c["over_budget_tiles"])
    if c["skipped"]:
        s += "; without a card: " + ", ".join(f"{k} {v}" for k, v in c["skipped"].items())
    return s + "\n"


# --- the preview ------------------------------------------------------------------------------

def _cards(pdir: Path, plan: dict) -> list[dict]:
    out = []
    for t in (plan.get("far") or {}).get("tiles") or []:
        f = pdir / t["file"]
        if f.is_file():
            out += json.loads(f.read_text(encoding="utf-8"))["cards"]
    return out


def _tone(img: np.ndarray, ev100: float) -> np.ndarray:
    """Scene luminance (nits) to display at the exposure `ev100` (the luminance 2^EV100 12.5 /
    100 shown as middle grey, 0.18), through a filmic curve."""
    k = 0.18 / (2.0 ** ev100 * 0.125)
    x = np.maximum(img * k, 0.0)
    y = x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14)
    return np.clip(y, 0.0, 1.0) ** (1.0 / 2.2)


def render_top(cards: list[dict], bounds, cell_m: float, schedules: dict, hour: float):
    """The cards seen from above (scene nits per cell, rgb): pools as their falloff, glows and
    washes as gaussian dots of their intensity over the cell's area."""
    x0, y0, x1, y1 = bounds
    w = max(1, int(math.ceil((x1 - x0) / cell_m)))
    h = max(1, int(math.ceil((y1 - y0) / cell_m)))
    img = np.zeros((h, w, 3), dtype=np.float64)
    hi = int(hour) % 24
    for r in cards:
        lvl = float((schedules.get(r["schedule"]) or [1.0] * 24)[hi])
        if lvl <= 0.0:
            continue
        col = np.array(r["color"], dtype=np.float64) * lvl
        x, y = r["pos"][0], r["pos"][1]
        if r["type"] == "wash":
            continue                                  # (on a facade: unseen from above)
        if r["type"] == "pool":
            rad, hh = r["size_m"], max(0.5, r["h_m"])
            i0 = max(0, int((x - rad - x0) / cell_m))
            i1 = min(w - 1, int((x + rad - x0) / cell_m))
            j0 = max(0, int((y1 - (y + rad)) / cell_m))
            j1 = min(h - 1, int((y1 - (y - rad)) / cell_m))
            if i1 < i0 or j1 < j0:
                continue
            xs = x0 + (np.arange(i0, i1 + 1) + 0.5) * cell_m
            ys = y1 - (np.arange(j0, j1 + 1) + 0.5) * cell_m
            dx, dy = np.meshgrid(xs - x, ys - y)
            rr = np.hypot(dx, dy)
            f = (1.0 + (rr / hh) ** 2) ** -1.5 * np.clip(1.0 - (rr / rad) ** 4, 0.0, 1.0) ** 2
            img[j0:j1 + 1, i0:i1 + 1] += f[..., None] * (r["value"] * col)
        else:
            i = int((x - x0) / cell_m)
            j = int((y1 - y) / cell_m)
            if 0 <= i < w and 0 <= j < h:
                img[j, i] += col * r["value"] / (cell_m * cell_m)
    return img


def render_view(cards: list[dict], eye, target, schedules: dict, hour: float, w: int = 1600,
                h: int = 600, fov_deg: float = 70.0, min_d: float = 300.0):
    """The cards from a camera (eye, target; a pinhole, `fov_deg` across), past `min_d`: each
    glow and wash a gaussian of its intensity at least `FAR_PX` pixels wide (as the runtime
    draws them), each pool as its disc seen from the eye (its width across, its depth
    foreshortened). Scene nits per pixel, rgb."""
    e = np.array(eye, dtype=np.float64)
    f = np.array(target, dtype=np.float64) - e
    f /= np.linalg.norm(f)
    rt = np.cross(f, [0.0, 0.0, 1.0])
    rt /= np.linalg.norm(rt)
    up = np.cross(rt, f)
    fl = (w / 2.0) / math.tan(math.radians(fov_deg) / 2.0)   # pixels per unit at depth 1
    img = np.zeros((h, w, 3), dtype=np.float64)
    hi = int(hour) % 24
    yy, xx = np.mgrid[0:h, 0:w]
    for r in cards:
        lvl = float((schedules.get(r["schedule"]) or [1.0] * 24)[hi])
        if lvl <= 0.0:
            continue
        p = np.array(r["pos"], dtype=np.float64) - e
        d = float(np.linalg.norm(p))
        zc = float(p @ f)
        if zc < 1.0 or d < min_d:
            continue
        u = w / 2.0 + fl * float(p @ rt) / zc
        v = h / 2.0 - fl * float(p @ up) / zc
        col = np.array(r["color"], dtype=np.float64) * lvl
        if r["type"] in ("pool", "wash"):
            # (its disc as a gaussian of half its radius, foreshortened by the view's slant:
            # a pool's by its height under the eye, a wash's by its facing, unseen behind)
            r0 = fl * r["size_m"] / zc * 0.5
            if r["type"] == "pool":
                rx = max(0.7, r0)
                ry = max(0.7, r0 * abs(float(p[2])) / max(d, 1.0))
                peak = r["value"] * min(1.0, r0 * r0 / (rx * ry))
            else:
                a = math.radians(float(r.get("yaw") or 0.0))
                facing = -(math.cos(a) * p[0] + math.sin(a) * p[1]) / max(d, 1.0)
                if facing <= 0.0:
                    continue
                r1 = fl * r["h_m"] / zc * 0.6
                rx = max(0.7, r0 * 1.2 * facing)
                ry = max(0.7, r1)
                peak = r["value"] * min(1.0, (r0 * 1.2 * facing) * r1 / (rx * ry))
        else:
            # (the card's gaussian, exp(-8 r^2) on its half size: sigma an eighth of its
            # size; at least FAR_PX pixels wide; under a pixel's width spread over 0.7 px,
            # its intensity kept: peak = I / (2 pi sigma^2 a_px), a_px a pixel's area there)
            s_px = max(P.FAR_PX, fl * r["size_m"] / zc)
            rx = ry = max(0.7, s_px / 8.0)
            a_px = (zc / fl) ** 2
            peak = r["value"] / (2.0 * math.pi * rx * rx * a_px)
        if u < -4 * rx or u > w + 4 * rx or v < -4 * ry or v > h + 4 * ry:
            continue
        i0, i1 = max(0, int(u - 3 * rx)), min(w - 1, int(u + 3 * rx) + 1)
        j0, j1 = max(0, int(v - 3 * ry)), min(h - 1, int(v + 3 * ry) + 1)
        if i1 < i0 or j1 < j0:
            continue
        gx = (xx[j0:j1 + 1, i0:i1 + 1] - u) / rx
        gy = (yy[j0:j1 + 1, i0:i1 + 1] - v) / ry
        g = np.exp(-0.5 * (gx * gx + gy * gy))
        img[j0:j1 + 1, i0:i1 + 1] += g[..., None] * (peak * col)
    return img


def preview(pdir: Path, plan: dict, model: dict, out: Path | None = None) -> dict:
    """`preview_far.png`: the far cards over the city by night, from above (left: the pools
    lighting the streets, the glows and washes) and from 150 m over its south-west corner
    looking across it (right: the cards past 300 m, as the runtime draws them there), both at
    the night's exposure (the plan's `night_ev100`: the lights' own frame)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cards = _cards(pdir, plan)
    b = model.get("bounds") or [0.0, 0.0, 1000.0, 1000.0]
    span = max(b[2] - b[0], b[3] - b[1])
    cell = max(2.0, span / 1400.0)
    sch = plan["schedules"]
    hour = float(plan.get("hour", 23.0))
    ev = float(plan.get("night_ev100", 1.5))
    top = _tone(render_top(cards, b, cell, sch, hour), ev)
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    eye = (b[0] + 0.08 * (b[2] - b[0]), b[1] + 0.08 * (b[3] - b[1]), 150.0)
    view = _tone(render_view(cards, eye, (cx, cy, 0.0), sch, hour), ev)
    fig = plt.figure(figsize=(18, 8), dpi=100, facecolor="black")
    a1 = fig.add_axes([0.01, 0.06, 0.40, 0.88])
    a1.imshow(top, extent=(b[0], b[0] + top.shape[1] * cell, b[3] - top.shape[0] * cell, b[3]),
              interpolation="bilinear")
    a1.plot([eye[0]], [eye[1]], "o", color="#30d0ff", ms=6)
    a1.set_axis_off()
    a1.set_title("far cards from above", color="white", fontsize=11)
    a2 = fig.add_axes([0.43, 0.20, 0.56, 0.60])
    a2.imshow(view, interpolation="bilinear")
    a2.set_axis_off()
    a2.set_title("from 150 m over the corner (blue), past 300 m", color="white", fontsize=11)
    c = (plan.get("far") or {}).get("counts") or {}
    fig.text(0.01, 0.01, f"{plan['city']}: {c.get('all', 0)} far cards ({c.get('glow', 0)} "
             f"glows, {c.get('pool', 0)} pools, {c.get('wash', 0)} washes) at {hour:g} h, "
             f"exposure {ev:g} EV100 (the plan's)", color="#bbbbbb", fontsize=10)
    out = Path(out) if out else pdir / FILE
    fig.savefig(out, facecolor="black")
    plt.close(fig)
    return {"image": str(out), "cards": len(cards)}
