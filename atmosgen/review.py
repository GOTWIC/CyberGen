"""The art-direction loop for the light and air (AT6; as citygen's and assetgen's `review`): a
Claude Code session, through the `atmosgen` skill, looks at a round's shots and previews
against the prompt and the atmos spec, changes spec parameters (never code), plans again,
imports and shoots again, a few rounds at most. atmosgen makes no model call: this module
only prepares each round's review sheet and tells the rounds apart.

`atmosgen review BUILD [--plan DIR] [--spec S] [--prev PREV_PLAN] [--shots DIR]
[--prev-shots DIR]` writes `review.md`, `review.json` and, with shots, `review_shots.jpg`
(a contact sheet, the previous round's beside each where it has one) into the plan's folder:

- the plan's checks (lux, faces, air, weather: a failed one is fixed first);
- the city's numbers: the look, the hour and weather, lights and tiers, the light on each
  walkway class, the exposure by night and by day, the deck's glow, the air and the weather,
  the look's post by night and by day;
- every district's: its mood (lamp, temperature, grit, flicker, broken lights, neon), the
  light on its sidewalks and carriageways, its post by night (bloom, grain, fringes,
  saturation, contrast, tints);
- every shot's: its exposure as the eye reads it (the mean log luminance in stops from
  middle grey, the median), the share clipped and crushed, the mean saturation; with the
  previous round's shots, what moved;
- what changed in the spec since the previous round, the previews to open, and the spec
  parameters that answer what the reviewer may see (`LEVERS`).

`atmosgen spec diff A B` lists the parameter changes between two atmos specs.
"""

from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path

MAX_ROUNDS = 3
# previews (in the plan's folder) and what each shows
PREVIEWS = [
    ("preview_post.png", "the districts' post by grit and each district's grade on a chart"),
    ("preview_lux.png", "the light on the ground round the core, by night"),
    ("preview_plan.png", "every light by kind over the city"),
    ("preview_sky.png", "the deck's glow; the sun, the moon and the exposure by the hour"),
    ("preview_air.png", "the fog volumes and the plumes"),
    ("preview_weather.png", "the rain shadow, puddles and drip bands"),
]
SHOT_EXT = (".png", ".jpg", ".jpeg")
# what a reviewer may see -> the atmos spec parameters that change it
LEVERS = [
    ("the whole city too wet, too clear, the wrong hour or season", "preset, weather, hour, "
     "sky.day_of_year, sky.latitude_deg"),
    ("a street too dark or too bright by night", "light_levels.<class>, "
     "light_levels.night_ev100"),
    ("the day too dark or too bright (under rain most of all)", "post.day_ev_bias, "
     "post.overcast_comp"),
    ("the grade's color off (neon rain: teal shadows, magenta highlights)", "post.shadows, "
     "post.highlights, post.tint, post.saturation, post.contrast"),
    ("too much or too little glow round the lights", "post.bloom, post.flare"),
    ("too much or too little film grain or fringing", "post.grain, post.chromatic, "
     "post.vignette"),
    ("a district too clean or too gritty for its place", "districts.<name>.grit"),
    ("a district's tint (cool core, sodium old town, magenta market)",
     "districts.<name>.shadows, districts.<name>.highlights, districts.<name>.tint"),
    ("the wrong lamps or light colour in a district", "districts.<name>.lamp, .temp, .spill"),
    ("too few or too many lit signs, too much flicker or too many dead lights",
     "districts.<name>.neon, .flicker, .broken"),
    ("alleys too lit or too dark", "districts.<name>.alleys"),
    ("haze too thick or too thin in a district", "districts.<name>.haze"),
    ("towers' crowns unlit or too many searchlights", "districts.<name>.floods, "
     ".searchlights, landmarks.<name>"),
    ("the moon, the stars or the cloud deck", "sky.moon, sky.stars, sky.cloud_deck_m, "
     "sky.cloud_cover, sky.cloud_glow"),
    ("the rain leaning the wrong way", "wind_deg"),
    ("a district's neon colours", "districts.<name>.palette, palette.neon"),
]


# ---------------------------------------------------------------------------
# Spec diff
# ---------------------------------------------------------------------------

def spec_diff(a, b, path: str = "") -> list[str]:
    """Every parameter that differs between two specs, as `path: old -> new`."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k == "$schema":
                continue
            p = f"{path}.{k}" if path else str(k)
            if k not in a:
                out.append(f"{p}: (none) -> {json.dumps(b[k], sort_keys=True)}")
            elif k not in b:
                out.append(f"{p}: {json.dumps(a[k], sort_keys=True)} -> (none)")
            else:
                out += spec_diff(a[k], b[k], p)
        return out
    if a != b:
        return [f"{path}: {json.dumps(a, sort_keys=True)} -> {json.dumps(b, sort_keys=True)}"]
    return []


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def _avg(lux: dict, cls: str):
    c = (lux or {}).get(cls) or {}
    return c.get("average_lx")


def numbers(plan: dict, rep: dict) -> dict:
    """The city's and every district's numbers for the sheet."""
    lux = (rep.get("lux") or {})
    cls = lux.get("classes") or {}
    sky = rep.get("sky") or {}
    post = rep.get("post") or {}
    look_n = (post.get("look") or {}).get("night") or {}
    look_d = (post.get("look") or {}).get("day") or {}
    ex = post.get("exposure") or {}
    ws = rep.get("weather_stats") or {}
    ac = rep.get("air_counts") or {}
    city = {"look": plan.get("preset"), "hour": plan.get("hour"), "weather": plan.get("weather"),
            "lights": (rep.get("counts") or {}).get("all"),
            "live (sight max)": (plan.get("tiers") or {}).get("sight_max"),
            "sidewalk lx (avg)": _avg(cls, "sidewalk"),
            "crosswalk lx": _avg(cls, "crosswalk"),
            "carriageway lx": _avg(cls, "carriageway"),
            "alley lx": _avg(cls, "alley"),
            "under deck lx": _avg(cls, "under_deck"),
            "exposure night (EV100)": ex.get("night_ev100", sky.get("ev_night")),
            "exposure day (EV100)": ex.get("day_ev100", sky.get("ev_day")),
            "overcast given back": ex.get("overcast_comp"),
            "deck glow (cd/m2, max)": (sky.get("glow") or {}).get("max_luma_nits"),
            "fog volumes": ac.get("volumes"), "plumes": ac.get("emitters"),
            "puddled share": ws.get("puddled"), "covered share": ws.get("covered")}
    for k in ("bloom", "flare", "grain", "chromatic", "vignette", "saturation", "contrast"):
        city[f"post {k} (night / day)"] = (f"{look_n.get(k, '-')} / {look_d.get(k, '-')}"
                                           if look_n else None)
    dists = {}
    moods = rep.get("districts") or {}
    dl = lux.get("districts") or {}
    pd = post.get("districts") or {}
    for did, m in sorted(moods.items()):
        name = m.get("name") or did
        p = (pd.get(name) or {}).get("night") or {}
        dists[name] = {"archetype": m.get("archetype"), "grit": m.get("grit"),
                       "lamp": f"{m.get('lamp')} {m.get('temp')}",
                       "neon": m.get("neon"), "flicker": m.get("flicker"),
                       "broken": m.get("broken"),
                       "sidewalk lx": _avg(dl.get(did), "sidewalk"),
                       "carriageway lx": _avg(dl.get(did), "carriageway"),
                       "post (night)": (f"bloom {p['bloom']:g}, grain {p['grain']:g}, fringe "
                                        f"{p['chromatic']:g}, sat {p['saturation']:g}, "
                                        f"contrast {p['contrast']:g}, lift {p['lift']:g}"
                                        if p else None),
                       "tints (shadows, highlights)": (f"{_rgb(p['shadows'])}, "
                                                       f"{_rgb(p['highlights'])}" if p else None)}
    return {"city": city, "districts": dists}


def _rgb(v) -> str:
    return "x(" + " ".join(f"{float(c):.2f}" for c in v) + ")"


def shot_numbers(path: Path) -> dict:
    """A shot's exposure as the eye reads it: the mean log luminance in stops from middle
    grey (its display value, sRGB decoded), the median luminance, the share clipped (over
    0.98) and crushed (under 0.02), the mean saturation (HSV's)."""
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((480, 480))
        a = np.asarray(im, dtype=np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    y = lin @ np.array([0.2126, 0.7152, 0.0722])
    mx, mn = a.max(-1), a.min(-1)
    sat = np.where(mx > 0.0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return {"stops": round(float(np.mean(np.log2(np.maximum(y, 1e-4) / 0.18))), 2),
            "median": round(float(np.median(y)), 4),
            "clipped": round(float(np.mean(y > 0.96)), 4),
            "crushed": round(float(np.mean(y < 0.0016)), 4),
            "saturation": round(float(np.mean(sat)), 3)}


def _shots(d: Path | None) -> dict[str, Path]:
    if d is None or not Path(d).is_dir():
        return {}
    out = {}
    for f in sorted(Path(d).iterdir()):
        if f.suffix.lower() in SHOT_EXT:
            out[f.stem.replace("unreal_", "")] = f
    return out


def contact_sheet(shots: dict[str, Path], prev: dict[str, Path], out: Path,
                  width: int = 640) -> Path | None:
    """The round's shots in a grid (the previous round's beside each where it has one,
    labeled), one JPEG."""
    from PIL import Image, ImageDraw
    if not shots:
        return None
    pairs = [(n, prev.get(n), f) for n, f in shots.items()]
    cols = 2 if any(p for _, p, _ in pairs) else 3
    cells = []
    for name, p, f in pairs:
        row = []
        for g, tag in ((p, "before"), (f, "after" if p else "")):
            if g is None and cols == 2 and tag == "before":
                row.append((None, name + " (no previous)"))
                continue
            if g is None:
                continue
            row.append((g, f"{name} {tag}".strip()))
        cells += row if cols == 2 else row[-1:]
    hgt = int(width * 9 / 16)
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * (hgt + 18)), (16, 16, 20))
    dr = ImageDraw.Draw(sheet)
    for k, (g, label) in enumerate(cells):
        x, y = (k % cols) * width, (k // cols) * (hgt + 18)
        if g is not None:
            with Image.open(g) as im:
                im = im.convert("RGB")
                im.thumbnail((width, hgt))
                sheet.paste(im, (x, y + 18))
        dr.text((x + 4, y + 3), label, fill=(230, 230, 230))
    sheet.save(out, quality=86)
    return out


def review(build: str | Path, spec_path: str | Path | None = None,
           prev: str | Path | None = None, plan: str | Path | None = None,
           shots: str | Path | None = None, prev_shots: str | Path | None = None) -> dict:
    """Write review.md, review.json (and review_shots.jpg) into the plan's folder; returns
    the review record (with `out`, the sheet's path)."""
    pdir = Path(plan) if plan else Path(build) / "atmos"
    pl = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    rep = json.loads((pdir / "atmos_report.json").read_text(encoding="utf-8"))
    nums = numbers(pl, rep)
    prev_rec = None
    if prev is not None and (Path(prev) / "review.json").is_file():
        prev_rec = json.loads((Path(prev) / "review.json").read_text(encoding="utf-8"))
    rnd = (prev_rec["round"] + 1) if prev_rec else 1
    spec = None
    if spec_path is not None:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        if Path(spec_path).resolve() != (pdir / "review_spec.json").resolve():
            shutil.copyfile(spec_path, pdir / "review_spec.json")
    changes = spec_diff(prev_rec["spec"], spec) if prev_rec and spec is not None and \
        prev_rec.get("spec") is not None else []
    checks = pl.get("checks") or {}
    failed = [k for k in ("lux", "faces", "air", "weather")
              if checks.get(k) is not None and not checks[k].get("ok")]
    sh, psh = _shots(Path(shots) if shots else None), _shots(Path(prev_shots) if prev_shots
                                                             else None)
    shot_nums = {n: shot_numbers(f) for n, f in sh.items()}
    prev_nums = {n: shot_numbers(f) for n, f in psh.items() if n in sh}
    sheet = contact_sheet(sh, psh, pdir / "review_shots.jpg") if sh else None
    rec = {"round": rnd, "max_rounds": MAX_ROUNDS, "city": pl["city"], "preset": pl["preset"],
           "passed": not failed, "failed": failed, "numbers": nums, "spec": spec,
           "spec_changes": changes, "shots": {n: str(f) for n, f in sh.items()},
           "shot_numbers": shot_nums, "prev_shot_numbers": prev_nums,
           "sheet": str(sheet) if sheet else None,
           "previews": [p for p, _ in PREVIEWS if (pdir / p).is_file()]}
    (pdir / "review.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8",
                                      newline="\n")
    md = _markdown(rec, prev_rec, pdir)
    (pdir / "review.md").write_text(md, encoding="utf-8", newline="\n")
    rec["out"] = str(pdir / "review.md")
    return rec


def _fmt(v) -> str:
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 10 else f"{v:.1f}"
    return str(v)


def _rel(p: str, base: Path) -> str:
    try:
        return Path(os.path.relpath(p, base)).as_posix()
    except ValueError:          # (another drive)
        return Path(p).as_posix()


def _markdown(rec: dict, prev: dict | None, pdir: Path) -> str:
    L = [f"# Art direction (light and air): {rec['city']}, {rec['preset']}, round "
         f"{rec['round']} of at most {rec['max_rounds']}", ""]
    L.append("Checks: " + ("all passed (lux, faces, air, weather)." if rec["passed"] else
                           "failed: " + ", ".join(rec["failed"]) + " (fix these first: the "
                           "exporter does not deliver the plan)."))
    L += ["", "## Spec changes since the last round", ""]
    L += [f"- `{c}`" for c in rec["spec_changes"]] or (
        ["- (first round)"] if prev is None else ["- none"])
    L += ["", "## City", "", "| Number | This round | Last round |", "|---|---|---|"]
    pc = prev["numbers"]["city"] if prev else {}
    for k, v in rec["numbers"]["city"].items():
        L.append(f"| {k} | {_fmt(v)} | {_fmt(pc.get(k))} |")
    L += ["", "## Districts", "",
          "| District | Archetype | Grit | Lamps | Neon | Flicker | Broken | Sidewalk lx | "
          "Carriageway lx | Post (night) | Tints |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, d in rec["numbers"]["districts"].items():
        L.append(f"| {name} | {d['archetype']} | {_fmt(d['grit'])} | {d['lamp']} | "
                 f"{_fmt(d['neon'])} | {_fmt(d['flicker'])} | {_fmt(d['broken'])} | "
                 f"{_fmt(d['sidewalk lx'])} | {_fmt(d['carriageway lx'])} | "
                 f"{_fmt(d['post (night)'])} | {_fmt(d['tints (shadows, highlights)'])} |")
    if rec["shot_numbers"]:
        L += ["", "## Shots", "",
              "Exposure as the eye reads it: the mean log luminance in stops from middle grey "
              "(a night street sits near -4 to -2.5, a day street near -2 to -1), the share "
              "clipped and crushed, the mean saturation.", "",
              "| Shot | Stops | Median | Clipped | Crushed | Saturation | Last round (stops) |",
              "|---|---|---|---|---|---|---|"]
        for n, s in rec["shot_numbers"].items():
            p = rec["prev_shot_numbers"].get(n)
            was = f"{p['stops']:+.2f}" if p else "-"
            L.append(f"| {n} | {s['stops']:+.2f} | {s['median']:.4f} | {s['clipped']:.3f} | "
                     f"{s['crushed']:.3f} | {s['saturation']:.3f} | {was} |")
        if rec.get("sheet"):
            L += ["", f"![The round's shots]({_rel(rec['sheet'], pdir)})"]
        L += [""] + [f"![{n}]({_rel(f, pdir)})" for n, f in rec["shots"].items()]
    L += ["", "## Previews to open", ""]
    for p, what in PREVIEWS:
        if p in rec["previews"]:
            L.append(f"- `{p}`: {what}")
    L += ["", "## If something reads wrong, change the atmos spec (never the code)", "",
          "| What you see | Spec parameters |", "|---|---|"]
    L += [f"| {a} | `{b}` |" for a, b in LEVERS]
    L += ["", "Then `atmosgen plan` again, import the plan (`citygen unreal BUILD UPROJECT "
              "--atmos DIR`), shoot the same views (`--check-only --shots`) and review with "
              "`--prev` and `--prev-shots`. Stop when the checks pass and the shots match the "
              "prompt, or after the last round; say what is still off."]
    return "\n".join(L) + "\n"
