"""AT6: the look (`docs/atmosgen_scope.md` 6.5): post and grading per preset and per district.

The plan's `post` holds what the runtime's post-process volume shows (`citygen/ue/
CityGenAtmos`, `ApplyPost`):

- **The look's post** (`presets.POST`): a set by night and a set by day (bloom, lens flares,
  film grain, chromatic aberration, vignette, sharpening, the grade's saturation and contrast,
  its shadow and highlight tints as gains, the highlights' saturation, a black lift, local
  exposure), blended by the sky's Night (dusk between them), with the spec's art direction
  over it (`spec.PostSpec`). Neon rain's grade is teal in the shadows and magenta in the
  highlights.
- **A post per district** (decision 12.5: near-photorealistic, clean or gritty by place): the
  look's sets pulled by the district's grit (`spec.mood`: its archetype's, up with danger and
  down with wealth; `presets.DISTRICT_POST`) and tinted by its archetype
  (`presets.DISTRICT_TINT`): the clean corporate core crisp and cool, old towns and markets
  and the port grainy, fringed, flared, with lifted blacks and their own tints. The runtime
  blends the districts by where the view stands, through the plan's district raster
  (`post_districts.png`: each `POST_CELL_M` cell's district, water and the map's edge the
  nearest's), weighted over a disc of `POST_BLEND_M` round the view and eased in time.
- **The exposure** (locked per preset and hour, no adaptation pumping; AT3 holds it by the
  sun's curve): the day's bias, and how much of the sun's light the weather's clouds take the
  day's exposure gives back (`overcast_comp`; AT5's rain by day was very dark).

`grade` is the runtime's grade in numpy (Unreal's `ColorCorrectAll` over linear rgb, then a
filmic curve), for the previews (`preview_post.png`: the districts' map and each district's
grade on a test chart, by night and by day) and `atmosgen review`.

Deterministic: shapely's exact predicates on the model's grid geometry, canonical rounding.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

from . import presets as P

RASTER_FILE = "post_districts.png"
NONE = 255                                  # (a cell no district reaches: none; the look's own)
SHADOWS_MAX = 0.09                          # Unreal's ColorCorrectionShadowsMax ...
HIGHLIGHTS_MIN = 0.5                        # ... HighlightsMin and HighlightsMax (defaults)
HIGHLIGHTS_MAX = 1.0
LUMA = (0.2126, 0.7152, 0.0722)


def r4(v: float) -> float:
    r = round(float(v) * 10000.0) / 10000.0
    return 0.0 if r == 0.0 else r


def _lin(h: str) -> list[float]:
    out = []
    for k in range(3):
        c = int(h[1 + 2 * k:3 + 2 * k], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def tint_gain(color: str, strength: float) -> list[float]:
    """A tint as a gain: its linear rgb over their mean (its hue, at the mean's brightness),
    `strength` of the way from white: 0.16 of neon rain's dark teal takes 13% off the red and
    adds 14% to the blue."""
    lin = _lin(color)
    m = sum(lin) / 3.0
    if m <= 0.0 or strength <= 0.0:
        return [1.0, 1.0, 1.0]
    return [r4(max(0.0, 1.0 + strength * (c / m - 1.0))) for c in lin]


def _mulv(a: list[float], b: list[float]) -> list[float]:
    return [r4(x * y) for x, y in zip(a, b)]


def look_sets(preset: str, spec_post: dict | None = None) -> dict:
    """The look's night and day sets with the spec's art direction over them: every
    `POST_KEYS` value, `shadows_gain` and `highlights_gain` (rgb), and the tints they come
    from (`shadows`, `highlights`: [color, strength])."""
    sp = spec_post or {}
    out = {}
    for when in ("night", "day"):
        src = P.POST[preset][when]
        s = {k: float(src[k]) for k in P.POST_KEYS}
        for k in ("bloom", "flare", "grain", "chromatic", "vignette", "saturation",
                  "contrast"):
            if sp.get(k) is not None:
                s[k] = s[k] * float(sp[k])
        tm = 1.0 if sp.get("tint") is None else float(sp["tint"])
        for side in ("shadows", "highlights"):
            col, k = src[side]
            col = sp.get(side) or col
            s[side] = [col, r4(k * tm)]
            s[f"{side}_gain"] = tint_gain(col, k * tm)
        out[when] = _clamped(s)
    return out


def _clamped(s: dict) -> dict:
    lim = {"grain": (0.0, 1.0), "chromatic": (0.0, 5.0), "vignette": (0.0, 1.0),
           "sharpen": (0.0, 2.0), "lift": (0.0, 0.05), "saturation": (0.0, 2.0),
           "contrast": (0.5, 1.5), "highlight_sat": (0.0, 2.0), "bloom": (0.0, 8.0),
           "flare": (0.0, 8.0), "local_shadows": (0.0, 1.0), "local_highlights": (0.0, 1.0)}
    out = dict(s)
    for k, (lo, hi) in lim.items():
        out[k] = r4(min(hi, max(lo, float(s[k]))))
    for k in ("flare_threshold", "chromatic_start"):
        out[k] = r4(s[k])
    return out


def district_sets(base: dict, mood: dict) -> dict:
    """A district's night and day sets: the look's pulled by its grit (`DISTRICT_POST`) and
    tinted by its archetype (`DISTRICT_TINT`, or the spec's district tints)."""
    g = float(mood.get("grit", 0.35))
    arch = mood.get("archetype") if mood.get("archetype") in P.DISTRICT_TINT else \
        P.MOOD_DEFAULT
    tint = P.DISTRICT_TINT[arch]
    ta, tb = P.DISTRICT_POST["mul"]["tint"]
    tm = (ta + tb * g) * (1.0 if mood.get("tint") is None else float(mood["tint"]))
    out = {}
    for when in ("night", "day"):
        s = dict(base[when])
        for k, (a, b) in P.DISTRICT_POST["mul"].items():
            if k != "tint":
                s[k] = s[k] * (a + b * g)
        for k, (a, b) in P.DISTRICT_POST["add"].items():
            s[k] = s[k] + a + b * g
        for side in ("shadows", "highlights"):
            col, k = tint[side]
            col = mood.get(side) or col
            s[f"{side}_tint"] = [col, r4(k * tm)]
            s[f"{side}_gain"] = _mulv(base[when][f"{side}_gain"], tint_gain(col, k * tm))
        out[when] = _clamped(s)
    return out


def raster(city_m: dict, order: list[str], cell_m: float = P.POST_CELL_M) -> dict:
    """Each `cell_m` cell's district (its index in `order`), the cell's middle in its
    polygon, else the nearest district (water, the map's edge: by distance, ties by id);
    rows from the north edge. Returns {idx (uint8, rows north to south), bounds, cell_m}."""
    from shapely import contains_xy, distance, points
    from shapely.geometry import Polygon
    b = city_m.get("bounds") or [0.0, 0.0, 0.0, 0.0]
    x0 = math.floor(b[0] / cell_m) * cell_m
    y0 = math.floor(b[1] / cell_m) * cell_m
    nx = max(1, int(math.ceil((b[2] - x0) / cell_m)))
    ny = max(1, int(math.ceil((b[3] - y0) / cell_m)))
    polys = []
    by_id = {d["id"]: d for d in city_m.get("districts", [])}
    for i, did in enumerate(order):
        ring = ((by_id.get(did) or {}).get("polygon") or {}).get("exterior") or []
        if len(ring) >= 3:
            holes = ((by_id[did].get("polygon") or {}).get("holes") or [])
            polys.append((i, Polygon(ring, holes)))
    xs = x0 + (np.arange(nx) + 0.5) * cell_m
    ys = y0 + (np.arange(ny) + 0.5) * cell_m
    gx, gy = np.meshgrid(xs, ys)                        # (rows from the south)
    idx = np.full(gx.shape, NONE, dtype=np.uint8)
    for i, g in polys:
        inside = contains_xy(g, gx, gy) & (idx == NONE)
        idx[inside] = i
    left = np.argwhere(idx == NONE)
    if len(left) and polys:
        geoms = [g for _, g in polys]
        pts = points(gx[left[:, 0], left[:, 1]], gy[left[:, 0], left[:, 1]])
        # (the nearest by exact distance, rounded to the millimetre, ties to the first)
        d = np.stack([np.round(distance(g, pts), 3) for g in geoms])
        near = np.argmin(d, axis=0)
        idx[left[:, 0], left[:, 1]] = np.array([polys[k][0] for k in near], dtype=np.uint8)
    return {"idx": idx[::-1].copy(), "bounds": [r4(x0), r4(y0), r4(x0 + nx * cell_m),
                                                r4(y0 + ny * cell_m)], "cell_m": cell_m}


def runs(idx: np.ndarray) -> list[int]:
    """The raster as runs over its rows from the north edge: [count, index] pairs."""
    flat = idx.reshape(-1)
    out: list[int] = []
    if flat.size == 0:
        return out
    cuts = np.flatnonzero(np.diff(flat.astype(np.int16))) + 1
    starts = np.concatenate([[0], cuts])
    ends = np.concatenate([cuts, [flat.size]])
    for s, e in zip(starts, ends):
        out += [int(e - s), int(flat[s])]
    return out


def overcast_shift(comp: float, cover: float, ref: float = 0.0) -> float:
    """The runtime's (`ACityGenAtmos::OvercastShift`): the stops the day's exposure moves by
    under a cloud cover against `ref`'s: `comp` of the log of the light it leaves (the sun's
    share less the overcast's take, `OVERCAST_TAKE`, the sky's `SKY_SHARE` kept); under 0 a
    brighter exposure."""
    c0, take = P.OVERCAST_TAKE

    def light(c):
        sun = 1.0 - take * min(1.0, max(0.0, (c - c0) / max(1e-3, 1.0 - c0)))
        return (1.0 - P.SKY_SHARE) * sun + P.SKY_SHARE
    return comp * math.log2(max(1e-3, light(cover)) / max(1e-3, light(ref)))


def make(filled: dict, sky: dict, city_m: dict) -> tuple[dict, dict | None]:
    """The plan's `post` and its district raster (None without districts)."""
    preset = filled["preset"]
    sp = filled.get("post") or {}
    base = look_sets(preset, sp)
    ex = dict(P.POST_EXPOSURE[preset])
    if sp.get("day_ev_bias") is not None:
        ex["day_bias"] = float(sp["day_ev_bias"])
    if sp.get("overcast_comp") is not None:
        ex["overcast_comp"] = float(sp["overcast_comp"])
    order = sorted(filled["moods"])
    dists = {}
    if sp.get("districts", True):
        for did in order:
            md = filled["moods"][did]
            dists[did] = {"name": md.get("name"), "archetype": md.get("archetype"),
                          "grit": md.get("grit"), **district_sets(base, md)}
    ras = raster(city_m, order) if dists else None
    post = {"keys": list(P.POST_KEYS), "base": base, "districts": dists,
            "order": order if dists else [],
            # (the day's exposure is a clear day's, under no cover; the runtime moves it by
            # the clouds the weather has now, `overcast_comp` of the light they take)
            "exposure": {"night_ev100": r4(sky["ev_night"]),
                         "day_ev100": r4(P.DAY_EV100 + ex["day_bias"]),
                         "day_bias": r4(ex["day_bias"]),
                         "overcast_comp": r4(ex["overcast_comp"]),
                         "overcast_take": [r4(v) for v in P.OVERCAST_TAKE],
                         "sky_share": r4(P.SKY_SHARE), "ref_cover": 0.0,
                         "look_cover_shift": r4(overcast_shift(ex["overcast_comp"],
                                                               sky["cloud_cover"]))},
            "blend_m": P.POST_BLEND_M, "ease_s": P.POST_EASE_S, "raster": None}
    return post, ras


def write(ras: dict, od: Path) -> dict:
    """`post_districts.png` (an index a pixel; 255 none) and its record."""
    from PIL import Image
    od.mkdir(parents=True, exist_ok=True)
    f = od / RASTER_FILE
    im = Image.fromarray(ras["idx"], mode="L")
    import io
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False, compress_level=9)
    data = buf.getvalue()
    if not f.is_file() or f.read_bytes() != data:
        f.write_bytes(data)
    h, w = ras["idx"].shape
    return {"file": RASTER_FILE, "bounds": ras["bounds"], "cell_m": ras["cell_m"],
            "px": [int(w), int(h)], "sha256": hashlib.sha256(data).hexdigest()}


def read(pdir: Path, rec: dict) -> np.ndarray:
    from PIL import Image
    with Image.open(Path(pdir) / rec["file"]) as im:
        return np.asarray(im.convert("L"), dtype=np.uint8)


# --- the grade in numpy (the previews) -----------------------------------------------------------

def _cc(c, sat, con, gain, off):
    luma = (c * np.asarray(LUMA)).sum(-1, keepdims=True)
    c = np.maximum(0.0, luma + (c - luma) * sat)
    c = np.power(np.maximum(c, 0.0) / 0.18, con) * 0.18
    return c * gain + off


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / max(1e-6, e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def grade(rgb: np.ndarray, s: dict) -> np.ndarray:
    """Unreal's ColorCorrectAll over scene-linear rgb (`...x3`) with a set's grade: global
    saturation and contrast, the shadows' and highlights' gains, the highlights' saturation,
    the shadows' lift; weights by luma (shadows under 0.09, highlights from 0.5 to 1)."""
    c = np.asarray(rgb, dtype=np.float64)
    luma = (c * np.asarray(LUMA)).sum(-1, keepdims=True)
    sat, con = float(s["saturation"]), float(s["contrast"])
    sh = _cc(c, sat, con, np.asarray(s["shadows_gain"]), float(s["lift"]))
    mi = _cc(c, sat, con, 1.0, 0.0)
    hi = _cc(c, sat * float(s["highlight_sat"]), con, np.asarray(s["highlights_gain"]), 0.0)
    ws = 1.0 - _smooth(0.0, SHADOWS_MAX, luma)
    wh = _smooth(HIGHLIGHTS_MIN, HIGHLIGHTS_MAX, luma)
    return sh * ws + mi * (1.0 - ws - wh) + hi * wh


def filmic(c: np.ndarray) -> np.ndarray:
    """A filmic curve to display sRGB (the ACES fit; Unreal's own is near it), 0 to 1."""
    c = np.maximum(c, 0.0) * 0.8
    x = (c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14)
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def chart(w: int = 240, h: int = 60) -> np.ndarray:
    """A test chart in scene-linear rgb: a grey ramp (0.002 to 3, logarithmic) over the top
    half, the neon accents and a sodium lamp, wet asphalt, concrete and skin under it."""
    out = np.zeros((h, w, 3))
    ramp = np.exp(np.linspace(math.log(0.002), math.log(3.0), w))
    out[: h // 2] = ramp[None, :, None]
    patches = [(c, 0.5) for c in P.NEON[:5]] + [("#ffb35c", 0.6), ("#2b2d30", 0.4),
                                                ("#8a8780", 0.25), ("#c99b7f", 0.3)]
    pw = w // len(patches)
    for k, (col, scale) in enumerate(patches):
        out[h // 2:, k * pw:(k + 1) * pw] = np.asarray(_lin(col)) * scale
    return out


def swatch(s: dict) -> np.ndarray:
    """The chart graded by a set and shown (uint8 rgb)."""
    return (filmic(grade(chart(), s)) * 255.0 + 0.5).astype(np.uint8)


def preview(plan: dict, pdir: Path, model: dict) -> dict:
    """`preview_post.png`: the districts' map by grit (each cell its district's, the map's
    edge and the water the nearest's) and every district's grade on the test chart by night
    and by day, beside the look's own."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    post = plan.get("post") or {}
    rows = [("look: " + plan["preset"], post["base"])]
    for did in post.get("order", []):
        d = post["districts"][did]
        rows.append((f"{d['name']} ({d['archetype']}, grit {d['grit']:g})", d))
    fig = plt.figure(figsize=(16, 2.2 + 1.0 * len(rows)), dpi=100)
    gs = fig.add_gridspec(len(rows), 3, width_ratios=[1.5, 1, 1])
    ax = fig.add_subplot(gs[:, 0])
    rec = post.get("raster")
    if rec:
        idx = read(pdir, rec)
        grit = np.array([float(post["districts"][d]["grit"]) for d in post["order"]] + [0.0])
        img = grit[np.minimum(idx, len(grit) - 1)]
        x0, y0, x1, y1 = rec["bounds"]
        ax.imshow(img, extent=(x0, x1, y0, y1), cmap="magma", vmin=0.0, vmax=1.0)
        for did in post["order"]:
            d = next((q for q in model.get("districts", []) if q["id"] == did), None)
            ring = ((d or {}).get("polygon") or {}).get("exterior") or []
            if ring:
                xs, ys = zip(*ring)
                ax.plot(list(xs) + [xs[0]], list(ys) + [ys[0]], color="w", lw=0.6)
                ax.text(sum(xs) / len(xs), sum(ys) / len(ys), post["districts"][did]["name"],
                        color="w", fontsize=7, ha="center")
        ax.set_title("districts' post by grit (dark clean, bright gritty)", fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])
    for r, (name, s) in enumerate(rows):
        for c, when in enumerate(("night", "day")):
            a = fig.add_subplot(gs[r, 1 + c])
            a.imshow(swatch(s[when]))
            a.set_xticks([])
            a.set_yticks([])
            if r == 0:
                a.set_title(when, fontsize=9)
            if c == 0:
                a.set_ylabel(name, fontsize=7, rotation=0, ha="right", va="center")
    fig.tight_layout()
    out = Path(pdir) / "preview_post.png"
    fig.savefig(out)
    plt.close(fig)
    return {"image": str(out)}
