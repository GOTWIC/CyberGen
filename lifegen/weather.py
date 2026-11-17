"""LG8: the crowd and the traffic by the hour and the weather, and reactions (scope 6.8,
docs/lifegen_scope.md section 13's LG8).

The runtime follows atmosgen's hour and weather state (its controller's `Hour`, rain rate and
state); the plan gives it what it reads them by:

- **the weather's table** (`weather_record`, `presets.WEATHER_LIFE`): per state the share of
  people out, their pace, the rain looks' share, umbrellas, the chance to shelter, the cars'
  share, speed and headway; the umbrellas' colors, the reactions' settings;
- **shelter** (`walk_cover`): each walkway's stretches under a cover, read from atmosgen's
  rain shadow (AT5's masks, `atmos_plan.json`'s `weather_plan.cover`): where people stop out of
  the rain, and fold their umbrellas;
- **nightlife** (`nightlife`): people round the open bars, clubs and arcades by night (LG4's
  places, their busy per band), on their door walkways, on top of M11's density;
- **checks** (`checks`): `weather`, `shelter`, `nightlife`.

Without an atmos plan the walkways have no stretches under a cover (said in the record); the
runtime still takes the hour and weather from atmosgen's controller where the level has one.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import presets as P


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def _lin(h: str) -> list[float]:
    def c(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return [round(c(int(h[1 + 2 * k:3 + 2 * k], 16)), 4) for k in range(3)]


# ---------------------------------------------------------------------------
# atmosgen's plan and its rain shadow
# ---------------------------------------------------------------------------

def atmos_dir(build: str | Path, given: str | Path | None = None) -> Path | None:
    """The atmos plan's folder: `given`, else BUILD/atmos; None without an `atmos_plan.json`."""
    for d in ([Path(given)] if given else []) + [Path(build) / "atmos"]:
        if (d / "atmos_plan.json").is_file():
            return d
    return None


class Masks:
    """AT5's rain shadow (atmosgen's `masks/<tile>.png`: red the lowest underside over a texel
    of what shelters it, `cover.z0_m` plus its value times `cover.step_m`, 0 open sky; row 0 the
    tile's north edge, `texel_m` texels over its 256 m)."""

    def __init__(self, adir: Path):
        plan = json.loads((adir / "atmos_plan.json").read_text(encoding="utf-8"))
        wp = plan.get("weather_plan") or {}
        cov = wp.get("cover") or {}
        self.z0 = float(cov.get("z0_m", -8.0))
        self.step = float(cov.get("step_m", 0.5))
        self.texel = float(wp.get("texel_m", 0.5))
        self.files = {m["tile"]: adir / m["file"] for m in plan.get("masks") or []}
        self.cache: dict[str, np.ndarray | None] = {}
        self.ok = bool(self.files)

    def _tile(self, t: str) -> np.ndarray | None:
        if t not in self.cache:
            f = self.files.get(t)
            if f is None or not f.is_file():
                self.cache[t] = None
            else:
                from PIL import Image
                with Image.open(f) as im:
                    self.cache[t] = np.asarray(im.convert("RGBA"))[:, :, 0].copy()
        return self.cache[t]

    def under(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """The cover's underside (absolute m) over each point; NaN under the open sky."""
        from .plan import TILE_M
        out = np.full(len(xs), np.nan)
        ix = np.floor(xs / TILE_M).astype(int)
        iy = np.floor(ys / TILE_M).astype(int)
        for k in range(len(xs)):
            a = self._tile(f"t{ix[k]:+03d}{iy[k]:+03d}")
            if a is None:
                continue
            n = a.shape[0]
            col = int((xs[k] - ix[k] * TILE_M) / self.texel)
            row = int(((iy[k] + 1) * TILE_M - ys[k]) / self.texel)
            col, row = min(max(col, 0), n - 1), min(max(row, 0), n - 1)
            v = int(a[row, col])
            if v > 0:
                out[k] = self.z0 + v * self.step
        return out


def _cum(line) -> list[float]:
    s = [0.0]
    for a, b in zip(line, line[1:]):
        s.append(s[-1] + math.dist(tuple(a[:3]) if len(a) > 2 else (a[0], a[1], 0.0),
                                   tuple(b[:3]) if len(b) > 2 else (b[0], b[1], 0.0)))
    return s


def _samples(line, step: float):
    """Points every `step` along a polyline (3D) with their distance along it."""
    cum = _cum(line)
    L = cum[-1]
    n = max(1, int(math.ceil(L / step)))
    out = []
    j = 0
    for k in range(n + 1):
        s = min(L, k * L / n)
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        a, b = line[j], line[j + 1]
        seg = cum[j + 1] - cum[j]
        t = (s - cum[j]) / seg if seg > 1e-9 else 0.0
        z0 = float(a[2]) if len(a) > 2 else 0.0
        z1 = float(b[2]) if len(b) > 2 else 0.0
        out.append((s, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, z0 + (z1 - z0) * t))
    return out, L


# (walkways people walk indoors or in the dry whatever the weather)
ENCLOSED = ("skybridge", "elevator", "escalator", "concourse")


def walk_cover(model: dict, masks: Masks | None, ground=None) -> tuple[dict, dict]:
    """Each walkway's stretches out of the rain ([from, to] m along it, 3D): under a cover of
    AT5's rain shadow at least `SHELTER["head_m"]` over it, or underground (under the ground
    datum by a meter), or enclosed (skybridges, elevators, escalators, concourses: whole).
    Returns the stretches by walkway and the stats."""
    sh = P.SHELTER
    out: dict[str, list[list[float]]] = {}
    stats = {"walkways": 0, "covered_m": 0.0, "shelter_m": 0.0, "enclosed": 0,
             "underground": 0, "masks": bool(masks and masks.ok)}
    for w in model.get("walkways", []):
        line = w.get("line") or []
        if len(line) < 2:
            continue
        kind = w.get("kind") or "path"
        level = int(w.get("level") or (w.get("attrs") or {}).get("level") or 0)
        if kind in ENCLOSED:
            L = _cum(line)[-1]
            out[w["id"]] = [[0.0, _r(L, 2)]]
            stats["enclosed"] += 1
            stats["covered_m"] += L
            continue
        pts, L = _samples(line, sh["step_m"])
        ss = np.array([p[0] for p in pts])
        xs = np.array([p[1] for p in pts])
        ys = np.array([p[2] for p in pts])
        zs = np.array([p[3] for p in pts])
        g = ground.at(xs, ys) if ground is not None and not ground.flat else np.zeros(len(xs))
        cov = zs < -1.0
        if cov.any():
            stats["underground"] += 1
        if masks is not None and masks.ok and level == 0:
            u = masks.under(xs, ys)
            with np.errstate(invalid="ignore"):
                cov |= np.nan_to_num(u, nan=-1e9) >= g + zs + sh["head_m"]
        if not cov.any():
            continue
        runs = []
        k = 0
        n = len(ss)
        while k < n:
            if not cov[k]:
                k += 1
                continue
            j = k
            while j + 1 < n and cov[j + 1]:
                j += 1
            a = max(0.0, ss[k] - 0.5 * sh["step_m"])
            b = min(L, ss[j] + 0.5 * sh["step_m"])
            if runs and a - runs[-1][1] < sh["join_m"]:
                runs[-1][1] = b
            else:
                runs.append([a, b])
            k = j + 1
        runs = [[_r(a, 2), _r(b, 2)] for a, b in runs if b - a >= sh["min_m"]]
        if runs:
            out[w["id"]] = runs
            m = sum(b - a for a, b in runs)
            stats["covered_m"] += m
            if kind in sh["kinds"]:
                stats["shelter_m"] += m
    stats["walkways"] = len(out)
    stats["covered_m"] = _r(stats["covered_m"], 1)
    stats["shelter_m"] = _r(stats["shelter_m"], 1)
    return out, stats


# ---------------------------------------------------------------------------
# nightlife
# ---------------------------------------------------------------------------

def night_places(model: dict, places: list[dict]) -> list[dict]:
    """The bars, clubs and arcades: LG4's places of those kinds (AG3's doors), and M11's POIs of
    those subs that are no place (a city without assetgen's doors): each its door walkway, kind,
    hours open (24) and busy per band (`presets.PLACE_KINDS`)."""
    from .places import open_hours
    out = [{"walkway_id": pl["walkway_id"], "kind": pl["kind"], "open": list(pl["open"]),
            "busy": list(pl["busy"])} for pl in places
           if pl.get("kind") in P.NIGHTLIFE["kinds"]]
    have = {pl.get("poi_id") for pl in places if pl.get("poi_id")}
    for poi in sorted(model.get("pois", []), key=lambda p: p["id"]):
        sub = poi.get("sub")
        if sub not in P.NIGHTLIFE["kinds"] or poi["id"] in have:
            continue
        e = (poi.get("entrances") or [{}])[0]
        if not e.get("walkway_id"):
            continue
        hrs = poi.get("hours") or P.PLACE_KINDS[sub]["hours"]
        out.append({"walkway_id": e["walkway_id"], "kind": sub, "open": open_hours(hrs),
                    "busy": list(P.PLACE_KINDS[sub]["busy"])})
    return out


def nightlife(model: dict, places: list[dict]) -> dict[str, list[float]]:
    """People round the open bars, clubs and arcades per band (`presets.NIGHTLIFE`) on their
    door walkways: `kinds[kind]` times the place's busy and its share of the band's hours open."""
    from .places import open_share
    out: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(P.BANDS))
    for pl in night_places(model, places):
        per = P.NIGHTLIFE["kinds"][pl["kind"]]
        sh = open_share(pl["open"])
        for b in range(len(P.BANDS)):
            out[pl["walkway_id"]][b] += per * float(pl["busy"][b]) * sh[b]
    return {k: [_r(v, 3) for v in vs] for k, vs in sorted(out.items()) if any(v > 0 for v in vs)}


# ---------------------------------------------------------------------------
# the record and the checks
# ---------------------------------------------------------------------------

def weather_record(filled: dict, cover_stats: dict, night: dict, adir: Path | None) -> dict:
    """The plan's `weather`: the table the runtime reads atmosgen's state by, the plan's own
    state (the crowd's `weather`: the previews' and the runtime's without an atmos controller),
    umbrellas, shelter, nightlife and the reactions."""
    u = P.UMBRELLA
    state = filled["crowd"].get("weather", "clear")
    return {"state": state, "keys": list(P.WEATHER_KEYS),
            "states": {s: {k: float(v[k]) for k in P.WEATHER_KEYS}
                       for s, v in P.WEATHER_LIFE.items()},
            "rain": {s: float(v) for s, v in P.WEATHER_RAIN.items()},
            "umbrella": {"colors": [_lin(c) for c in u["colors"]],
                         "lit": [_lin(c) for c in u["lit"]], "lit_share": u["lit_share"],
                         **{k: float(u[k]) for k in ("canopy_m", "canopy_h_m", "height",
                                                     "side_m", "fwd_m", "tilt_deg",
                                                     "shaft_m")}},
            "shelter": {"dwell_s": list(P.SHELTER["dwell_s"]), "head_m": P.SHELTER["head_m"],
                        "kinds": list(P.SHELTER["kinds"]), **cover_stats,
                        "atmos": str(adir).replace("\\", "/") if adir else None},
            "nightlife": {"kinds": dict(P.NIGHTLIFE["kinds"]), "walkways": len(night),
                          "people": [_r(sum(v[b] for v in night.values()), 1)
                                     for b in range(len(P.BANDS))]},
            "reactions": {**{k: bool(v) for k, v in filled.get("reactions", {}).items()},
                          **{k: (list(v) if isinstance(v, (list, tuple)) else float(v))
                             for k, v in P.REACTION.items()}},
            "traffic": dict(P.TRAFFIC_STUCK)}


def checks(model: dict, rows: list[dict], places: list[dict], rec: dict) -> dict:
    """`weather` (every state's shares within [0, 1], paces and speeds in reason, the rain looks
    in the pool's groups), `shelter` (every stretch within its walkway, sorted, apart, at least
    the minimum; the stats), `nightlife` (people only on an open nightlife place's door walkway,
    and only by night)."""
    out = {}
    bad = []
    for s, v in rec["states"].items():
        for k in ("out", "rain_looks", "umbrella", "shelter", "cars"):
            if not 0.0 <= v[k] <= 1.2:
                bad.append(f"{s}: {k} {v[k]}")
        if not 0.8 <= v["pace"] <= 1.4 or not 0.5 <= v["speed"] <= 1.1:
            bad.append(f"{s}: pace {v['pace']} or speed {v['speed']}")
    for s in rec["rain"]:
        if s not in rec["states"]:
            bad.append(f"{s}: no row")
    rx = rec["reactions"]
    if rx.get("flee") and not (rx["flee_m"] > 0 and rx["flee_s"] > 0 and rx["flee_pace"] >= 1):
        bad.append("flee settings")
    out["weather"] = {"ok": not bad, "detail": "; ".join(bad) if bad else (
        f"{len(rec['states'])} states (out of doors {min(v['out'] for v in rec['states'].values()):.2f}"
        f" to 1, umbrellas to {max(v['umbrella'] for v in rec['states'].values()):.2f}, rain "
        f"looks to {max(v['rain_looks'] for v in rec['states'].values()):.2f}); the plan's own "
        f"state {rec['state']}; reactions "
        + ", ".join(k for k in ("step_aside", "look", "flee", "gather") if rx.get(k)))}
    # shelter
    sbad = []
    walks = {w["id"]: w for w in model.get("walkways", [])}
    n = m = 0
    for r in rows:
        cv = r.get("cover")
        if not cv:
            continue
        w = walks.get(r["id"])
        L = _cum(w["line"])[-1] if w else 0.0
        prev = -1.0
        for a, b in cv:
            if a < -0.01 or b > L + 0.01 or b - a < P.SHELTER["min_m"] - 0.01 and \
                    (w or {}).get("kind") not in ENCLOSED and b - a < L - 0.01:
                sbad.append(f"{r['id']}: [{a}, {b}] of {L:.2f} m")
            if a <= prev:
                sbad.append(f"{r['id']}: stretches out of order")
            prev = b
            m += b - a
        n += 1
    sh = rec["shelter"]
    out["shelter"] = {"ok": not sbad, "detail": "; ".join(sbad[:4]) if sbad else (
        f"{n} walkways with {m / 1000.0:.1f} km out of the rain ({sh['shelter_m'] / 1000.0:.1f}"
        f" km where people shelter, {sh['enclosed']} enclosed, {sh['underground']} underground)"
        + ("" if sh.get("masks") else "; no atmos plan: no covers read"))}
    # nightlife
    nbad = []
    openb = defaultdict(lambda: [0.0] * len(P.BANDS))
    from .places import open_share
    for pl in night_places(model, places):
        sh2 = open_share(pl["open"])
        for b in range(len(P.BANDS)):
            openb[pl["walkway_id"]][b] += sh2[b] * float(pl["busy"][b])
    tot = [0.0] * len(P.BANDS)
    for r in rows:
        nv = r.get("night")
        if not nv:
            continue
        for b, v in enumerate(nv):
            tot[b] += v
            if v > 0 and openb[r["id"]][b] <= 0:
                nbad.append(f"{r['id']}: {v} people in band {P.BANDS[b]} with no place open")
    out["nightlife"] = {"ok": not nbad, "detail": "; ".join(nbad[:4]) if nbad else (
        f"{sum(1 for r in rows if r.get('night'))} door walkways of bars, clubs and arcades, "
        "people by band " + ", ".join(f"{b} {v:.0f}" for b, v in zip(P.BANDS, tot)))}
    return out
