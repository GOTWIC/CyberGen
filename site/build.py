#!/usr/bin/env python3
"""Build the CyberGen gallery site for GitHub Pages.

    python site/build.py --out DIR

Reads site/gallery.json, resizes each entry's image from the repo (a file under
docs/progress/) into DIR/img/<id>.jpg (at most 2000 px wide) and DIR/thumb/<id>.jpg
(640 px wide), and writes DIR/index.html from the template site/index.html with the
entries filled in, beside style.css, app.js and gallery.json. Needs Pillow only.

The resized images are build output: never commit them. The Pages workflow
(.github/workflows/pages.yml) runs this on every change to site/. Run it locally into
a folder outside the repo to preview; images already made and newer than their source
and this script are kept, so a second run is quick.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageFilter

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent

FULL = (2000, 2400)   # max width, max height of the full-size image
THUMB_W = 640
QUALITY = 85
BACKDROP_W = 96       # the page backdrop: a tiny blurred image the browser stretches

FIELDS = ("id", "date", "stage", "milestone", "milestone_name", "title", "image", "caption")
TEXT_FIELDS = ("title", "caption", "milestone_name")
BANNED = {chr(0x2014): "an em dash", chr(0x2013): "an en dash"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MILESTONE_RE = re.compile(r"^(M|AG)(\d+)")
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
TEMPLATE_KEYS = ("TITLE", "DESCRIPTION", "SITE", "OG_IMAGE", "REPO", "FILTERS", "RAIL",
                 "KICKER", "LEDE", "STATS", "STRIP", "STAGES", "NEXT", "BUILT")


def fail(errors: list[str]) -> None:
    for e in errors:
        print(f"gallery.json: {e}", file=sys.stderr)
    sys.exit(1)


def load(path: Path) -> dict:
    g = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    stages = [s["key"] for s in g.get("stages", [])]
    seen: set[str] = set()
    for i, e in enumerate(g.get("entries", [])):
        where = f"entry {i} ({e.get('id', '?')})"
        for f in FIELDS:
            if not isinstance(e.get(f), str) or not e[f].strip():
                errors.append(f"{where}: missing {f}")
        if errors:
            continue
        if not ID_RE.match(e["id"]):
            errors.append(f"{where}: id must be lowercase letters, digits and dashes")
        if e["id"] in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(e["id"])
        if e["stage"] not in stages:
            errors.append(f"{where}: stage {e['stage']!r} is not one of {stages}")
        try:
            dt.date.fromisoformat(e["date"])
        except ValueError:
            errors.append(f"{where}: date {e['date']!r} is not YYYY-MM-DD")
        for f in TEXT_FIELDS:
            for ch, name in BANNED.items():
                if ch in e[f]:
                    errors.append(f"{where}: {f} has {name}")
        if not (ROOT / e["image"]).is_file():
            errors.append(f"{where}: no file {e['image']}")
    for key in g.get("backdrop", {}).values():
        if key not in seen:
            errors.append(f"backdrop: no entry {key!r}")
    if not g.get("entries"):
        errors.append("no entries")
    if errors:
        fail(errors)
    return g


def flatten(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (10, 12, 16))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def fresh(dst: Path, *srcs: Path) -> bool:
    return dst.is_file() and all(dst.stat().st_mtime >= s.stat().st_mtime for s in srcs)


def save_jpeg(im: Image.Image, dst: Path, sharp: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    # 4:4:4 chroma for maps and charts (PNG sources), whose thin colored lines and
    # labels smear under the default 4:2:0
    im.save(tmp, "JPEG", quality=QUALITY, optimize=True, progressive=True,
            subsampling=0 if sharp else 2)
    tmp.replace(dst)


def make_images(e: dict, out: Path, cache: dict) -> tuple[int, int, bool]:
    """The entry's full-size and thumbnail JPEGs; returns the full size and whether made.

    `cache` maps an id to the source it was made from, so an entry pointed at another
    image is made again even when the old output is newer than the new source."""
    src = ROOT / e["image"]
    full = out / "img" / f"{e['id']}.jpg"
    thumb = out / "thumb" / f"{e['id']}.jpg"
    me = Path(__file__)
    stamp = [e["image"], src.stat().st_size, int(src.stat().st_mtime)]
    if cache.get(e["id"]) == stamp and fresh(full, src, me) and fresh(thumb, src, me):
        with Image.open(full) as im:
            return im.size[0], im.size[1], False
    cache[e["id"]] = stamp
    sharp = src.suffix.lower() == ".png"
    with Image.open(src) as im:
        im = flatten(im)
        im.thumbnail(FULL, Image.LANCZOS)
        save_jpeg(im, full, sharp)
        w, h = im.size
        t = im.copy()
        t.thumbnail((THUMB_W, THUMB_W * 4), Image.LANCZOS)
        save_jpeg(t, thumb, sharp)
    return w, h, True


def make_backdrop(src: Path, dst: Path) -> None:
    if fresh(dst, src, Path(__file__)):
        return
    with Image.open(src) as im:
        im = flatten(im)
        im.thumbnail((BACKDROP_W, BACKDROP_W), Image.LANCZOS)
        im = im.filter(ImageFilter.GaussianBlur(2.5))
        save_jpeg(im, dst, False)


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def day_label(d: dt.date) -> str:
    return f"{DAYS[d.weekday()]} {d.day:02d} {MONTHS[d.month - 1]} {d.year}"


def milestone_count(entries: list[dict]) -> int:
    found = set()
    for e in entries:
        m = MILESTONE_RE.match(e["milestone"])
        if m:
            found.add((m.group(1), int(m.group(2))))
    return len(found)


def grouped(g: dict) -> list[tuple[dict, list[dict]]]:
    by = {s["key"]: [] for s in g["stages"]}
    for e in g["entries"]:
        by[e["stage"]].append(e)
    return [(s, sorted(by[s["key"]], key=lambda e: e["date"])) for s in g["stages"] if by[s["key"]]]


def render_entry(e: dict, dims: tuple[int, int], g: dict, latest: str) -> str:
    w, h = dims
    src_url = f"{g['repo']}/blob/{g['branch']}/{quote(e['image'])}"
    is_latest = e["date"] == latest
    chips = [
        f'<time class="chip" datetime="{esc(e["date"])}">{esc(e["date"])}</time>',
        f'<span class="chip ms">{esc(e["milestone"])}</span>',
    ]
    if is_latest:
        chips.append('<span class="chip live"><span class="dot"></span>Latest</span>')
    return f"""
      <li class="entry{' latest' if is_latest else ''}" id="{esc(e['id'])}" data-stage="{esc(e['stage'])}">
        <span class="node" aria-hidden="true"></span>
        <article class="card">
          <header class="entry-head">{''.join(chips)}<span class="ms-name">{esc(e['milestone_name'])}</span></header>
          <h3 class="entry-title"><a href="#{esc(e['id'])}">{esc(e['title'])}</a></h3>
          <figure>
            <a class="shot" href="img/{esc(e['id'])}.jpg" data-src="{esc(src_url)}" style="aspect-ratio:{w}/{h}">
              <img src="thumb/{esc(e['id'])}.jpg" srcset="thumb/{esc(e['id'])}.jpg {THUMB_W}w, img/{esc(e['id'])}.jpg {w}w"
                   sizes="(max-width: 900px) calc(100vw - 72px), 860px" width="{w}" height="{h}"
                   loading="lazy" decoding="async" alt="{esc(e['title'])}">
            </a>
            <figcaption>{esc(e['caption'])}</figcaption>
          </figure>
          <footer class="entry-foot"><a href="{esc(src_url)}" target="_blank" rel="noopener">Original image</a><span>{esc(e['image'])}</span></footer>
        </article>
      </li>"""


def render_stages(g: dict, dims: dict[str, tuple[int, int]], latest: str) -> str:
    parts = []
    for n, (stage, entries) in enumerate(grouped(g), 1):
        items = []
        day = None
        for e in entries:
            if e["date"] != day:
                day = e["date"]
                items.append(f'\n      <li class="day"><span class="lbl">{day_label(dt.date.fromisoformat(day))}</span></li>')
            items.append(render_entry(e, dims[e["id"]], g, latest))
        parts.append(f"""
  <section class="stage" id="stage-{esc(stage['key'])}" data-stage="{esc(stage['key'])}">
    <div class="sec-head">
      <span class="num">{n:02d}</span>
      <h2>{esc(stage['label'])} <span>// {esc(stage['name'])}</span></h2>
      <span class="count mono">{len(entries)} entries</span>
    </div>
    <p class="lede">{esc(stage['blurb'])}</p>
    <ol class="timeline">{''.join(items)}
    </ol>
  </section>""")
    return "".join(parts)


def render_rail(g: dict) -> str:
    out = ['<h4 class="lbl">Stages</h4>', '<nav id="rail">']
    for n, (stage, entries) in enumerate(grouped(g), 1):
        out.append(f'<a href="#stage-{esc(stage["key"])}" data-stage="{esc(stage["key"])}">'
                   f'<i>{n:02d}</i>{esc(stage["label"])}<em>{len(entries)}</em></a>')
        firsts: dict[str, str] = {}
        for e in entries:
            firsts.setdefault(e["milestone"], e["id"])
        ms = "".join(f'<a href="#{esc(i)}">{esc(m)}</a>' for m, i in firsts.items())
        out.append(f'<div class="ms-list">{ms}</div>')
    out.append("</nav>")
    return "\n".join(out)


def render_filters(g: dict) -> str:
    return "".join(f'<button class="btn" type="button" data-filter="{esc(s["key"])}" data-stage="{esc(s["key"])}" aria-pressed="false">'
                   f'{esc(s["label"])}</button>' for s, _ in grouped(g))


def render_stats(g: dict) -> str:
    dates = sorted(e["date"] for e in g["entries"])
    first, last = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
    items = [("Days", str((last - first).days + 1)),
             ("Milestones", str(milestone_count(g["entries"]))),
             ("Stages built", f"{len([s for s in g['stages'] if s['key'].isdigit()])} of 5")]
    return "".join(f'<div><dt class="lbl">{esc(k)}</dt><dd class="mono">{esc(v)}</dd></div>' for k, v in items)


def render_strip(g: dict) -> str:
    dates = sorted({e["date"] for e in g["entries"]})
    first, last = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
    by_day: dict[str, list[dict]] = {}
    for stage, entries in grouped(g):
        for e in entries:
            by_day.setdefault(e["date"], []).append(e)
    cols = []
    d = first
    while d <= last:
        key = d.isoformat()
        cells = "".join(f'<a href="#{esc(e["id"])}" data-stage="{esc(e["stage"])}" title="{esc(key + " · " + e["milestone"] + " · " + e["title"])}"></a>'
                        for e in by_day.get(key, []))
        month = f"<b>{MONTHS[d.month - 1]}</b>" if d == first or d.day == 1 else ""
        cols.append(f'<div class="col"><div class="cells">{cells}</div><span class="mono">{d.day:02d}</span>{month}</div>')
        d += dt.timedelta(days=1)
    legend = "".join(f'<span class="key" data-stage="{esc(s["key"])}"><i></i>{esc(s["label"])}</span>' for s, _ in grouped(g))
    return f'<div class="strip-cols">{"".join(cols)}</div><div class="strip-legend">{legend}</div>'


def build(out: Path) -> None:
    g = load(SITE / "gallery.json")
    out.mkdir(parents=True, exist_ok=True)
    dims: dict[str, tuple[int, int]] = {}
    made = 0
    cache_file = out / ".sources.json"
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    for k, e in enumerate(g["entries"], 1):
        w, h, did = make_images(e, out, cache)
        dims[e["id"]] = (w, h)
        made += did
        print(f"[{k:2d}/{len(g['entries'])}] {'made' if did else 'kept'} {e['id']}", flush=True)
    cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    # Images of entries no longer in the gallery
    ids = {e["id"] for e in g["entries"]}
    for folder in ("img", "thumb"):
        for p in (out / folder).glob("*.jpg"):
            if p.stem not in ids:
                p.unlink()
    by_id = {e["id"]: e for e in g["entries"]}
    for theme, key in g.get("backdrop", {}).items():
        make_backdrop(ROOT / by_id[key]["image"], out / f"bg-{theme}.jpg")

    latest = max(e["date"] for e in g["entries"])
    dates = sorted(e["date"] for e in g["entries"])
    og = g.get("backdrop", {}).get("dark") or g["entries"][-1]["id"]
    values = {
        "TITLE": esc(f"{g['title']}: {g['subtitle'].lower()}"),
        "DESCRIPTION": esc(g["lede"]),
        "SITE": esc(g["site"]),
        "OG_IMAGE": esc(f"{g['site']}img/{og}.jpg"),
        "REPO": esc(g["repo"]),
        "FILTERS": render_filters(g),
        "RAIL": render_rail(g),
        "KICKER": esc(f"{g['subtitle']} · {dates[0]} to {dates[-1]}"),
        "LEDE": esc(g["lede"]),
        "STATS": render_stats(g),
        "STRIP": render_strip(g),
        "STAGES": render_stages(g, dims, latest),
        "NEXT": esc(g.get("next", "")),
        "BUILT": esc(dt.date.today().isoformat()),
    }
    page = (SITE / "index.html").read_text(encoding="utf-8")
    for key in TEMPLATE_KEYS:
        token = "{{" + key + "}}"
        if token not in page:
            fail([f"index.html has no {token}"])
        page = page.replace(token, values[key])
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", page)
    if leftover:
        fail([f"index.html has unknown tokens {sorted(set(leftover))}"])
    (out / "index.html").write_text(page, encoding="utf-8")
    for name in ("style.css", "app.js", "gallery.json"):
        shutil.copyfile(SITE / name, out / name)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"{len(g['entries'])} entries, {made} images made, site {total / 1e6:.1f} MB in {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="output folder (outside the repo when run locally)")
    args = ap.parse_args()
    build(args.out.resolve())


if __name__ == "__main__":
    main()
