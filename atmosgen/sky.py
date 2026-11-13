"""AT3: the sky and the time of day (scope 6.2).

- **The sun and the moon** by the hour: the sun's elevation and azimuth from the city's
  latitude and the day of the year (solar time, the sun culminating at 12); the moon's
  from its phase (it trails the sun by `phase` of a day, its declination mirrored by its
  phase, its light by its lit fraction). Directions in citygen's frame (x east, y north, z
  up), toward the body.
- **Curves over the sun's elevation** (`presets.SUN_CURVE`): the exposure (locked per look
  and hour, from the night's held -3 EV100 to the day's), MPC_CityGen's `Night`, the sun's
  light, the sky light, the stars. The runtime interpolates the same keys at any hour, so the
  plan's report and the game agree.
- **The schedules the sun sets** (`schedules`): `dusk_dawn` (street lights on from the sun
  at +3 degrees in the evening to +3 in the morning) and `tunnel`.
- **The sky glow** (`glow`): the plan's upward light flux per area, lit onto the cloud deck's
  underside, as a raster (`sky_glow.png`, linear RGB, square-root encoded, row 0 the north)
  the runtime's sky shows from below by night: bright over the core and the port.

Deterministic: plain arithmetic and numpy elementwise sums in a fixed order.
"""

from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path

import numpy as np

from . import presets as P

GLOW_FILE = "sky_glow.png"


def r3(v: float) -> float:
    r = round(v * 1000.0) / 1000.0
    return 0.0 if r == 0.0 else r


def r4(v: float) -> float:
    r = round(v * 10000.0) / 10000.0
    return 0.0 if r == 0.0 else r


def g6(v: float) -> float:
    """Six significant figures (a luminance of any size)."""
    return float(f"{v:.6g}")


# --- the sun and the moon -----------------------------------------------------------------------

def declination(day_of_year: float) -> float:
    """The sun's declination (degrees) on a day of the year (Cooper's approximation)."""
    return -23.44 * math.cos(2.0 * math.pi * (day_of_year + 10.0) / 365.0)


def body(lat_deg: float, dec_deg: float, hour_angle_deg: float) -> tuple[float, float, list]:
    """A body's elevation and azimuth (degrees, azimuth clockwise from north) and its
    direction [x east, y north, z up] at an hour angle (0 when it culminates)."""
    la, de, ha = (math.radians(v) for v in (lat_deg, dec_deg, hour_angle_deg))
    se = math.sin(la) * math.sin(de) + math.cos(la) * math.cos(de) * math.cos(ha)
    e = math.asin(max(-1.0, min(1.0, se)))
    az = math.atan2(-math.sin(ha) * math.cos(de),
                    math.cos(la) * math.sin(de) - math.sin(la) * math.cos(de) * math.cos(ha))
    ce = math.cos(e)
    d = [ce * math.sin(az), ce * math.cos(az), math.sin(e)]
    return math.degrees(e), (math.degrees(az) + 360.0) % 360.0, d


def sun_at(sky: dict, hour: float):
    return body(sky["latitude_deg"], sky["declination_deg"], 15.0 * (hour - 12.0))


def moon_at(sky: dict, hour: float):
    m = sky["moon"]
    return body(sky["latitude_deg"], m["declination_deg"], 15.0 * (hour - 12.0 - m["lag_h"]))


def curve(name: str, elev: float, cv: dict | None = None) -> float:
    """A curve of `presets.SUN_CURVE` (or `cv`) at a sun elevation, piecewise linear."""
    cv = cv or P.SUN_CURVE
    xs, ys = cv["elev"], cv[name]
    if elev <= xs[0]:
        return ys[0]
    for k in range(1, len(xs)):
        if elev <= xs[k]:
            t = (elev - xs[k - 1]) / (xs[k] - xs[k - 1])
            return ys[k - 1] + t * (ys[k] - ys[k - 1])
    return ys[-1]


def exposure(sky: dict, elev: float) -> float:
    """The scene's exposure (EV100, Unreal's frame) at a sun elevation."""
    return sky["ev_night"] + (sky["ev_day"] - sky["ev_night"]) * curve("ev", elev, sky["curve"])


def _crossing(sky: dict, target: float, h0: float, h1: float) -> float | None:
    """The first hour in [h0, h1) (minutes) the sun's elevation crosses `target`."""
    prev = sun_at(sky, h0)[0]
    for k in range(1, int(round((h1 - h0) * 60.0)) + 1):
        h = h0 + k / 60.0
        e = sun_at(sky, h)[0]
        if (prev - target) * (e - target) <= 0.0 and prev != e:
            return h
        prev = e
    return None


def day_ev(filled: dict, cover: float) -> float:
    """AT6: the day's exposure (EV100) under a cloud cover: a clear day's (`DAY_EV100` plus the
    spec's `post.day_ev_bias`) moved by `overcast_comp` of the light the clouds take."""
    from .look import overcast_shift
    sp = filled.get("post") or {}
    ex = P.POST_EXPOSURE.get(filled.get("preset"), {"day_bias": 0.0, "overcast_comp": 0.5})
    bias = ex["day_bias"] if sp.get("day_ev_bias") is None else float(sp["day_ev_bias"])
    comp = ex["overcast_comp"] if sp.get("overcast_comp") is None else float(sp["overcast_comp"])
    return P.DAY_EV100 + bias + overcast_shift(comp, cover)


def make(filled: dict, spec_sky: dict | None = None) -> dict:
    """The sky's settings for a city: where and when, the moon, the exposure, the curves,
    the cloud deck, the named hours (day, dusk, night) and a row per hour (the report)."""
    look = filled["look"]
    s = dict(P.SKY)
    for k, v in (spec_sky or {}).items():
        if v is not None:
            s[k] = v
    dec = declination(float(s["day_of_year"]))
    phase = float(s["moon_phase"]) % 1.0
    deck = float(look["cloud_deck_m"])
    cover = float(look["cloud_cover"]) if deck > 0.0 else 0.0
    sky = {"latitude_deg": r3(s["latitude_deg"]), "day_of_year": int(s["day_of_year"]),
           "declination_deg": r3(dec),
           "moon": {"phase": r3(phase), "lag_h": r3(24.0 * phase),
                    "declination_deg": r3(dec * math.cos(2.0 * math.pi * phase)),
                    "lit": r3(0.5 * (1.0 - math.cos(2.0 * math.pi * phase))),
                    "share": r4(float(look["moon"])), "color": P.MOON_COLOR,
                    "disk_nits": P.MOON_DISK_NITS, "disk_deg": P.MOON_DEG,
                    "rise": list(P.MOON_RISE), "cloud": P.MOON_CLOUD},
           "sun_lux": P.SUN_LUX, "ev_night": P.SCENE_NIGHT_EV100,
           # (AT6: the day's exposure at the look's own cover, as the runtime holds it: a
           # clear day's, `DAY_EV100` and the spec's bias, moved by the clouds,
           # `look.overcast_shift`)
           "ev_day": r3(day_ev(filled, cover)),
           "curve": {k: list(v) for k, v in P.SUN_CURVE.items()},
           "stars": r3(float(look["stars"])),
           "cloud_deck_m": deck, "cloud_cover": r3(cover),
           "cloud_glow": r3(float(look["cloud_glow"])), "upward_lm": 0.0, "glow": None}
    dusk = _crossing(sky, float(s["dusk_elevation_deg"]), 12.0, 24.0)
    night = float(filled["hour"]) if curve("night", sun_at(sky, filled["hour"])[0]) > 0.99 \
        else float(s["night_hour"])
    sky["hours"] = {"day": r3(s["day_hour"]), "dusk": r3(dusk if dusk is not None else 19.5),
                    "night": r3(night)}
    rows = []
    for h in range(24):
        e, az, _ = sun_at(sky, float(h))
        me, maz, _ = moon_at(sky, float(h))
        rows.append({"hour": h, "sun_elev": r3(e), "sun_az": r3(az), "moon_elev": r3(me),
                     "moon_az": r3(maz), "ev100": r3(exposure(sky, e)),
                     "night": r3(curve("night", e))})
    sky["by_hour"] = rows
    return sky


def schedules(sky: dict) -> dict:
    """The schedules the sun sets (24 values, the share at each hour's start): `dusk_dawn`
    on from the sun at +3 degrees to -3 in the evening, the reverse in the morning;
    `tunnel` brighter by night (0.6 by day)."""
    dd = []
    for h in range(24):
        e = sun_at(sky, float(h))[0]
        dd.append(r3(min(1.0, max(0.0, (3.0 - e) / 6.0))))
    return {"dusk_dawn": dd, "tunnel": [r3(0.6 + 0.4 * v) for v in dd]}


# --- the sky glow -------------------------------------------------------------------------------

def flux(L: dict) -> float:
    """A light's luminous flux (lm): a spot's peak over its cone (flat to the mean of its
    inner and outer angles), a point's all round, a lit face's pi times its luminance and
    area (the plan's `cd` for a rect)."""
    cd = float(L["cd"])
    if L["shape"] == "rect":
        return math.pi * cd
    if L["shape"] == "point":
        return 4.0 * math.pi * cd
    inner, outer = L.get("cone") or [40.0, 60.0]
    th = math.radians(0.5 * (inner + outer))
    return cd * 2.0 * math.pi * (1.0 - math.cos(th))


def up_share(L: dict) -> float:
    """The share of a light's flux going up, directly."""
    pitch = float(L["aim"][1])
    if L["shape"] == "rect":
        return 0.5 + 0.5 * math.sin(math.radians(pitch))
    if L["shape"] == "point":
        return 0.5
    inner, outer = L.get("cone") or [40.0, 60.0]
    th = 0.5 * (inner + outer)
    lo, hi = pitch - th, pitch + th
    if lo >= 0.0:
        return 1.0
    if hi <= 0.0:
        return 0.0
    return hi / (hi - lo)


def upward(L: dict) -> float:
    """What of a light reaches the sky (lm): its direct upward flux and what bounces off
    the ground, each the share that leaves the street canyons (`presets.ESCAPE`)."""
    f, u = flux(L), up_share(L)
    return f * (u * P.ESCAPE[0] + (1.0 - u) * P.GROUND_REFLECT * P.ESCAPE[1])


def luma(c) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def glow(sky: dict, lights: list[dict], scheds: dict, extent) -> dict | None:
    """The cloud deck's underside lit by the city: per GLOW_CELL_M cell, every light's
    upward flux (by its schedule at GLOW_HOUR, broken lights left out) in its color, summed
    over the deck by a Lambertian emitter's footprint at its height; the underside's
    luminance CLOUD_ALBEDO E / pi times the look's glow (cd/m2, linear RGB). None without a
    deck. Returns {rgb (rows north to south), bounds, cell_m, upward_lm, max, mean, peak_at}."""
    h = float(sky["cloud_deck_m"])
    if h <= 0.0 or not lights:
        return None
    cell = P.GLOW_CELL_M
    reach = int(math.ceil(P.GLOW_REACH * h / cell))
    x0, y0, x1, y1 = extent
    pad = reach * cell
    gx0 = math.floor((x0 - pad) / cell) * cell
    gy0 = math.floor((y0 - pad) / cell) * cell
    nx = int(math.ceil((x1 + pad - gx0) / cell))
    ny = int(math.ceil((y1 + pad - gy0) / cell))
    F = np.zeros((ny, nx, 3))
    hr = int(P.GLOW_HOUR) % 24
    total = 0.0
    for L in sorted(lights, key=lambda r: r["id"]):
        if not L.get("on", True):
            continue
        k = float(scheds.get(L["schedule"], [1.0] * 24)[hr])
        if k <= 0.0:
            continue
        phi = upward(L) * k
        if phi <= 0.0:
            continue
        c = L["color"]
        y = luma(c)
        if y <= 1e-4:
            continue
        i = int((L["pos"][1] - gy0) // cell)
        j = int((L["pos"][0] - gx0) // cell)
        if 0 <= i < ny and 0 <= j < nx:
            F[i, j, 0] += phi * c[0] / y
            F[i, j, 1] += phi * c[1] / y
            F[i, j, 2] += phi * c[2] / y
            total += phi
    # E = sum of F K(r), K(r) = h^2 / (pi (h^2 + r^2)^2), over the cells within reach
    E = np.zeros_like(F)
    Fp = np.zeros((ny + 2 * reach, nx + 2 * reach, 3))
    Fp[reach:reach + ny, reach:reach + nx] = F
    h2 = h * h
    for di in range(-reach, reach + 1):
        for dj in range(-reach, reach + 1):
            r2 = (di * di + dj * dj) * cell * cell
            if r2 > (P.GLOW_REACH * h) ** 2:
                continue
            kk = h2 / (math.pi * (h2 + r2) ** 2)
            E += kk * Fp[reach + di:reach + di + ny, reach + dj:reach + dj + nx]
    Lum = E * (P.CLOUD_ALBEDO / math.pi) * float(sky["cloud_glow"])
    Lum = np.round(Lum * 1e6) / 1e6
    top = float(Lum.max())
    Y = 0.2126 * Lum[..., 0] + 0.7152 * Lum[..., 1] + 0.0722 * Lum[..., 2]
    pk = np.unravel_index(int(np.argmax(Y)), Y.shape)
    # the city's own cells (inside its extent): the mean the deck shows over it
    i0, i1 = int((y0 - gy0) // cell), int(math.ceil((y1 - gy0) / cell))
    j0, j1 = int((x0 - gx0) // cell), int(math.ceil((x1 - gx0) / cell))
    mean = float(Y[i0:i1, j0:j1].mean()) if i1 > i0 and j1 > j0 else 0.0
    return {"rgb": Lum[::-1].copy(), "bounds": [gx0, gy0, gx0 + nx * cell, gy0 + ny * cell],
            "cell_m": cell, "upward_lm": total, "max": top, "max_luma": float(Y.max()),
            "mean": mean,
            "peak_at": [r3(gx0 + (pk[1] + 0.5) * cell), r3(gy0 + (pk[0] + 0.5) * cell)]}


def glow_png(g: dict) -> bytes:
    """The glow as an 8-bit RGB PNG: sqrt(rgb / max), row 0 the north edge (the runtime
    squares it and scales by the plan's `max_nits`)."""
    from PIL import Image
    top = max(g["max"], 1e-9)
    a = np.sqrt(np.clip(g["rgb"] / top, 0.0, 1.0))
    img = Image.fromarray(np.round(a * 255.0).astype(np.uint8), "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def write_glow(g: dict, od: Path) -> dict:
    """Write `sky_glow.png` (only when its bytes change) and return the plan's record."""
    data = glow_png(g)
    f = od / GLOW_FILE
    if not f.is_file() or f.read_bytes() != data:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    h, w = g["rgb"].shape[:2]
    return {"file": GLOW_FILE, "bounds": [r3(v) for v in g["bounds"]], "cell_m": g["cell_m"],
            "px": [w, h], "max_nits": g6(g["max"]), "max_luma_nits": g6(g["max_luma"]),
            "mean_nits": g6(g["mean"]), "peak_at": g["peak_at"],
            "sha256": hashlib.sha256(data).hexdigest()}


# --- the preview --------------------------------------------------------------------------------

def preview(pl: dict, pdir: Path, model: dict, out: Path | None = None) -> dict:
    """`preview_sky.png`: the deck's glow over the city (the plan's raster, its districts
    outlined), and the day: the sun's and the moon's elevation by the hour with the exposure
    and Night the runtime follows."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sky = pl["sky"]
    fig = plt.figure(figsize=(14, 7), dpi=150, facecolor="#05070d")
    ax = fig.add_axes([0.03, 0.08, 0.45, 0.84])
    ax.set_facecolor("#05070d")
    g = sky.get("glow")
    if g:
        from PIL import Image
        img = np.asarray(Image.open(pdir / g["file"]).convert("RGB"), dtype=float) / 255.0
        lin = img ** 2
        disp = np.clip(lin / max(lin.max(), 1e-6), 0, 1) ** (1 / 2.2)
        b = g["bounds"]
        ax.imshow(disp, extent=[b[0], b[2], b[1], b[3]], origin="upper")
        for d in model.get("districts", []):
            ex = d["polygon"]["exterior"]
            ax.plot([p[0] for p in ex] + [ex[0][0]], [p[1] for p in ex] + [ex[0][1]],
                    color="#7f8fb0", lw=0.4, alpha=0.6)
        ax.plot(*g["peak_at"], "+", color="white", ms=8)
        ax.set_title(f"the cloud deck at {sky['cloud_deck_m']:g} m lit by the city: up to "
                     f"{g['max_luma_nits']:.3g} cd/m2, {g['mean_nits']:.3g} over the city "
                     f"({sky['upward_lm'] / 1e6:.2f} Mlm up)", fontsize=8, color="#d8deea")
    else:
        ax.text(0.5, 0.5, "no cloud deck", color="#d8deea", ha="center",
                transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    a2 = fig.add_axes([0.56, 0.12, 0.4, 0.78])
    a2.set_facecolor("#0b0f1a")
    hs = np.arange(0, 24.01, 0.25)
    se = [sun_at(sky, h)[0] for h in hs]
    me = [moon_at(sky, h)[0] for h in hs]
    a2.plot(hs, se, color="#ffd27a", label="sun elevation")
    a2.plot(hs, me, color="#8fa8ff", label=f"moon elevation (phase {sky['moon']['phase']:g})")
    a2.axhline(0, color="#445", lw=0.6)
    a2.set_ylabel("degrees", color="#d8deea")
    a2.set_xlabel("hour", color="#d8deea")
    a2.tick_params(colors="#d8deea")
    a3 = a2.twinx()
    a3.plot(hs, [exposure(sky, e) for e in se], color="#05d9e8", ls="--",
            label="exposure (EV100)")
    a3.plot(hs, [curve("night", e, sky["curve"]) * 4.0 - 4.0 for e in se], color="#ff2a6d",
            ls=":", label="Night (0 to 1, as -4 to 0)")
    a3.tick_params(colors="#d8deea")
    for name, hv in sky["hours"].items():
        a2.axvline(hv, color="#666", lw=0.5)
        a2.text(hv, 80, name, color="#aab", fontsize=7, rotation=90, va="top")
    lines = a2.get_legend_handles_labels()[0] + a3.get_legend_handles_labels()[0]
    labels = a2.get_legend_handles_labels()[1] + a3.get_legend_handles_labels()[1]
    a2.legend(lines, labels, loc="lower center", fontsize=7, facecolor="#0b0f1a",
              labelcolor="#d8deea")
    a2.set_xlim(0, 24)
    a2.set_title(f"latitude {sky['latitude_deg']:g}, day {sky['day_of_year']}: the sun, the "
                 f"moon, the exposure and Night by the hour", fontsize=8, color="#d8deea")
    fig.suptitle(f"{pl['city']}: sky and time ({pl['preset']})", color="#d8deea", fontsize=10)
    dest = Path(out) if out else pdir / "preview_sky.png"
    fig.savefig(dest, facecolor="#05070d")
    plt.close(fig)
    return {"image": str(dest)}
