#!/usr/bin/env python3
"""Build the CyberGen gallery site for GitHub Pages.

    python site/build.py --out DIR

Reads site/gallery.json, resizes each entry's image from the repo (a file under
docs/progress/) into DIR/img/<id>.jpg (at most 2000 px wide) and DIR/thumb/<id>.jpg
(640 px wide), and writes two pages from their templates: DIR/index.html, the showcase
(gallery.json's "showcase": a curated few of the entries with titles and captions of
their own), and DIR/log.html, the build log (every entry), beside style.css, app.js and
gallery.json. Needs Pillow only.

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
TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")


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
    show = g.get("showcase", {})
    for f in ("heading",):
        if not isinstance(show.get(f), str) or not show[f].strip():
            errors.append(f"showcase: missing {f}")
    if not show.get("items"):
        errors.append("showcase: no items")
    for i, it in enumerate(show.get("items", [])):
        where = f"showcase item {i} ({it.get('title', '?')})"
        refs = it.get("entries") or ([it["entry"]] if it.get("entry") else [])
        if not refs or ("entries" in it and len(refs) != 2):
            errors.append(f"{where}: needs an entry, or entries as a pair")
        for r in refs:
            if r not in seen:
                errors.append(f"{where}: no entry {r!r}")
        if "labels" in it and len(it["labels"]) != len(refs):
            errors.append(f"{where}: one label per entry")
        for f in ("title", "caption"):
            if not isinstance(it.get(f), str) or not it[f].strip():
                errors.append(f"{where}: missing {f}")
            elif any(ch in it[f] for ch in BANNED):
                errors.append(f"{where}: {f} has an em or en dash")
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


def stage_labels(g: dict) -> dict[str, str]:
    return {s["key"]: s["label"] for s in g["stages"]}


def picture(e: dict, dims: tuple[int, int], sizes: str, cls: str = "") -> str:
    w, h = dims
    i = esc(e["id"])
    return (f'<img{cls} src="thumb/{i}.jpg" srcset="thumb/{i}.jpg {THUMB_W}w, img/{i}.jpg {w}w" sizes="{sizes}" '
            f'width="{w}" height="{h}" loading="lazy" decoding="async" alt="">')


def render_stage_keys(g: dict) -> str:
    by_id = {e["id"]: e for e in g["entries"]}
    shown = []
    for it in g["showcase"]["items"]:
        stage = by_id[(it.get("entries") or [it.get("entry")])[0]]["stage"]
        if stage not in shown:
            shown.append(stage)
    names = {s["key"]: s for s in g["stages"]}
    keys = "".join(f'<span class="key" data-stage="{esc(k)}"><i></i>{esc(names[k]["label"])} · {esc(names[k]["name"])}</span>'
                   for k in shown)
    return keys


def render_showcase(g: dict, dims: dict[str, tuple[int, int]]) -> str:
    """The showcase's cards: one picture each, or a pair (day and night) behind a slider."""
    by_id = {e["id"]: e for e in g["entries"]}
    labels = stage_labels(g)
    names = {s["key"]: s["name"] for s in g["stages"]}
    out = []
    stage = None
    for it in g["showcase"]["items"]:
        refs = it.get("entries") or [it["entry"]]
        first = by_id[refs[0]]
        wide = bool(it.get("wide"))
        sizes = "(max-width: 900px) calc(100vw - 58px), " + ("1130px" if wide else "560px")
        if len(refs) == 1:
            src_url = f"{g['repo']}/blob/{g['branch']}/{quote(first['image'])}"
            # Maps and charts (PNG) are shown whole in their frame; renders fill it.
            fit = " fit" if first["image"].lower().endswith(".png") else ""
            media = (f'<a class="shot frame{fit}" href="img/{esc(first["id"])}.jpg" data-src="{esc(src_url)}" '
                     f'aria-label="{esc(it["title"])}, full size">{picture(first, dims[first["id"]], sizes)}</a>')
        else:
            a, b = (by_id[r] for r in refs)
            la, lb = it.get("labels", ["Before", "After"])
            w, h = dims[a["id"]]
            under = picture(b, dims[b["id"]], sizes, ' class="cmp-b"')
            over = picture(a, dims[a["id"]], sizes, ' class="cmp-a"')
            media = (f'<div class="compare" style="--pos:50%;aspect-ratio:{w}/{h}">{under}{over}'
                     f'<span class="cmp-tag l">{esc(la)}</span><span class="cmp-tag r">{esc(lb)}</span>'
                     f'<span class="cmp-line" aria-hidden="true"></span>'
                     f'<span class="cmp-handle" role="slider" tabindex="0" aria-label="{esc(la)} and {esc(lb)}: '
                     f'drag or use the arrow keys" aria-valuemin="0" aria-valuemax="100" aria-valuenow="50"></span></div>')
        if first["stage"] != stage:
            if stage is not None:
                out.append("\n  </ul>")
            stage = first["stage"]
            out.append(f"""
  {section_head(labels[stage], names[stage], f"stage-{stage}")}
  <ul class="showcase">""")
        out.append(f"""
    <li class="entry{' wide' if wide else ''}{' pair' if len(refs) > 1 else ''}" id="show-{esc(refs[0])}" data-stage="{esc(first['stage'])}">
      <article class="card">
        {media}
        <div class="show-text">
          <header class="entry-head"><span class="chip ms">{esc(labels[first['stage']])}</span></header>
          <h3 class="entry-title">{esc(it['title'])}</h3>
          <p class="cap">{esc(it['caption'])}</p>
        </div>
      </article>
    </li>""")
    out.append("\n  </ul>")
    return "".join(out)


def section_head(label: str, name: str, anchor: str) -> str:
    """A showcase section's heading: its label, its name if any, then a rule to the edge."""
    sub = f'<span class="sec-name">{esc(name)}</span>' if name else ""
    return f'<h2 class="sec-head" id="{esc(anchor)}"><span class="sec-label">{esc(label)}</span>{sub}</h2>'



DEVICE_ORDER = ("mac", "windows", "cloud")
# API prices in dollars per million tokens (Anthropic's first-party rates): input,
# output, cache read; cache writes are 1.25x input (5-minute) and 2x input (1-hour);
# fast mode (a model id ending ":fast") is 2x standard. A model not listed shows "no
# price" and adds nothing to the cost: add its rates here when it is used. The panel
# prices the billable tokens (each request once), never the Claude stats count.
PRICES = {
    "claude-fable-5-1": (10.00, 50.00, 0.25),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
}
KINDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")
KIND_NAMES = {"input": "Input", "output": "Output", "cache_write_5m": "Cache write 5m",
              "cache_write_1h": "Cache write 1h", "cache_read": "Cache read"}
MODEL_NAMES = {"claude-fable-5-1": "Fable 5.1", "claude-fable-5": "Fable 5", "claude-opus-5-5": "Opus 5.5",
               "claude-opus-5": "Opus 5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-sonnet-5": "Sonnet 5",
               "claude-haiku-5-5": "Haiku 5.5"}


def rates(model: str) -> dict[str, float] | None:
    base, _, speed = model.partition(":")
    p = PRICES.get(base)
    if not p:
        return None
    k = 2 if speed == "fast" else 1
    i, o, r = (k * v for v in p)
    return {"input": i, "output": o, "cache_write_5m": 1.25 * i, "cache_write_1h": 2 * i, "cache_read": r}


def cost(model: str, tokens: dict[str, int]) -> dict[str, float] | None:
    r = rates(model)
    return None if r is None else {k: tokens.get(k, 0) * r[k] / 1e6 for k in KINDS}


def usd(x: float) -> str:
    return f"${x:,.0f}" if x >= 100 else f"${x:,.2f}"


def device_cost(u: dict) -> float:
    """What a device's billable tokens would cost at API prices (a hand-entered device: its
    spend)."""
    if u.get("manual"):
        return float(u["cost_usd"])
    return sum(sum((cost(m, t) or {}).values()) for m, t in u.get("models", {}).items())


def load_usage() -> list[dict]:
    """The per-device usage files site/usage.py writes (site/usage/<device>.json), and
    hand-entered ones ("manual": a spend in dollars, "cost_usd", with no logs behind it:
    cloud sessions, whose logs stay on Anthropic's servers)."""
    out = []
    for p in sorted((SITE / "usage").glob("*.json")):
        u = json.loads(p.read_text(encoding="utf-8"))
        need = ("device", "label", "updated") + (("cost_usd",) if u.get("manual") else
                                                 ("sessions", "subagents", "totals", "days"))
        for f in need:
            if f not in u:
                fail([f"usage/{p.name}: missing {f}"])
        if u.get("manual"):
            u.update(sessions=0, subagents=0, totals=dict.fromkeys(("total",) + KINDS, 0), days={}, models={})
        out.append(u)
    rank = {d: i for i, d in enumerate(DEVICE_ORDER)}
    return sorted(out, key=lambda u: (rank.get(u["device"], len(rank)), u["device"]))


def big(n: int) -> str:
    for size, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= size:
            v = n / size
            return f"{v:.{2 if v < 10 else 1 if v < 100 else 0}f}{unit}"
    return str(n)


def stamp(iso: str) -> str:
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f'<time datetime="{esc(iso)}">{t:%Y-%m-%d %H:%M} UTC</time>'


def counts(u: dict, view: str) -> dict:
    """A device's tokens in one count: "stats" (as Claude Code's own usage statistics count
    them: every log line, a response once per content block) or "billed" (each API
    response once, as Anthropic bills it). A device file from before the stats count falls
    back to its billed figures (`stats_pending`)."""
    if view == "stats" and "stats" in u:
        return u["stats"]
    return {"totals": u["totals"], "models": u.get("models", {}), "days": u["days"]}


def stats_pending(u: dict) -> bool:
    """A device whose stats count is not complete yet: its file predates the count, or
    some of its older ledger rows have no line count."""
    return not u.get("manual") and not u.get("stats", {}).get("complete", False)


def model_table(us: list[dict], view: str) -> dict[str, dict[str, int]]:
    """Every device's tokens by model and type, added up, in one count."""
    out: dict[str, dict[str, int]] = {}
    for u in us:
        for m, t in counts(u, view)["models"].items():
            row = out.setdefault(m, dict.fromkeys(KINDS, 0))
            for k in KINDS:
                row[k] += int(t.get(k, 0))
    return out


def render_usage(us: list[dict]) -> str:
    """The showcase's usage panel: Claude stats tokens (as Claude Code's own `/usage` stats
    count them) and billable tokens (each request once), every device added up; the chart
    in the stats count; by model and by device behind toggles."""
    if not us:
        return ""
    stats_total = sum(counts(u, "stats")["totals"]["total"] for u in us)
    billed_total = sum(counts(u, "billed")["totals"]["total"] for u in us)
    days = sorted(set().union(*(u["days"] for u in us)))
    more = ('<button class="btn mini" type="button" id="usage-more" aria-expanded="false" '
            'aria-controls="usage-models">By model</button>')
    total_cost = sum(device_cost(u) for u in us)
    kpis = "".join(f'<div><dt class="lbl">{k}</dt><dd class="mono">{v}</dd></div>' for k, v in (
        ("Claude stats tokens", big(stats_total) + more), ("Billable tokens", big(billed_total)),
        ("API cost", usd(total_cost)),
        ("Sessions", f'{sum(u["sessions"] for u in us):,}'), ("Active days", str(len(days)))))
    # Tokens by model and type, every device added up: the stats count, and under it the
    # billable count with its cost at API prices.
    st, bt = model_table(us, "stats"), model_table(us, "billed")
    order = sorted(st, key=lambda m: -sum(st[m].values()))

    def cell(s: int, b: int, c: float | None) -> str:
        return (f'<td class="mono">{big(s)}<small>{big(b)} · '
                f'{usd(c) if c is not None else "no price"}</small></td>')

    head = "".join(f'<th scope="col">{KIND_NAMES[k]}</th>' for k in KINDS)
    body = []
    sum_cost = dict.fromkeys(KINDS, 0.0)
    for m in order:
        s, b = st[m], bt.get(m, dict.fromkeys(KINDS, 0))
        c = cost(m, b)
        if c:
            for k in KINDS:
                sum_cost[k] += c[k]
        base, _, speed = m.partition(":")
        name = MODEL_NAMES.get(base, base) + (" (fast)" if speed else "")
        body.append(f'<tr><th scope="row">{esc(name)}</th>'
                    f'{"".join(cell(s[k], b[k], c[k] if c else None) for k in KINDS)}'
                    f'{cell(sum(s.values()), sum(b.values()), sum(c.values()) if c else None)}</tr>')
    foot = "".join(cell(sum(st[m][k] for m in st), sum(bt[m][k] for m in bt), sum_cost[k]) for k in KINDS)
    models = (f'<div class="usage-models" id="usage-models" hidden><table>'
              f'<thead><tr><th scope="col">Model</th>{head}<th scope="col">All</th></tr></thead>'
              f'<tbody>{"".join(body)}</tbody>'
              f'<tfoot><tr><th scope="row">All models</th>{foot}'
              f'{cell(stats_total, billed_total, sum(sum_cost.values()))}</tr></tfoot>'
              f'</table><p class="usage-note mono">Each cell: Claude stats tokens; under them, billable tokens '
              f'and their API cost.</p></div>')
    # A column a day, first to last, stacked by device, in the stats count.
    cols = []
    if days:
        first, last = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
        peak = max(sum(counts(u, "stats")["days"].get(d, {}).get("total", 0) for u in us) for d in days) or 1
        d = first
        while d <= last:
            key = d.isoformat()
            parts = [(u, counts(u, "stats")["days"].get(key, {}).get("total", 0)) for u in us]
            n = sum(v for _, v in parts)
            segs = "".join(f'<i data-device="{esc(u["device"])}" style="height:{100 * v / peak:.2f}%"></i>'
                           for u, v in parts if v)
            tip = f"{key}: {big(n)} Claude stats tokens" + "".join(
                f" · {u['label']} {big(v)}" for u, v in parts if v)
            label = f"{d.day:02d}" if d in (first, last) or d.day == 1 else ""
            cols.append(f'<div class="ucol" title="{esc(tip)}"><div class="ubar">{segs}</div>'
                        f'<span class="mono">{label}</span></div>')
            d += dt.timedelta(days=1)

    def row(u: dict) -> str:
        if u.get("manual"):
            note = f'<small>{esc(u.get("note", "entered by hand"))}, tokens unknown</small>'
            cells = ('<td class="mono na">n/a</td>' * 2 + f'<td class="mono">{usd(device_cost(u))}</td>'
                     + '<td class="mono na">n/a</td>' * 2)
        else:
            note = ("<small>stats count once per request until its next usage update</small>"
                    if stats_pending(u) else "")
            cells = (f'<td class="mono">{big(counts(u, "stats")["totals"]["total"])}</td>'
                     f'<td class="mono">{big(counts(u, "billed")["totals"]["total"])}</td>'
                     f'<td class="mono">{usd(device_cost(u))}</td>'
                     f'<td class="mono">{u["sessions"]:,}</td><td class="mono">{len(u["days"])}</td>')
        return (f'<tr data-device="{esc(u["device"])}"><th scope="row"><i></i>{esc(u["label"])}{note}</th>'
                f'{cells}<td class="mono">{stamp(u["updated"])}</td></tr>')

    pending = [u["label"] for u in us if stats_pending(u)]
    text = ("Claude stats tokens are counted as Claude Code's own usage statistics count them (/usage, "
            "stats): every line of the session logs, and Claude Code logs a response once per part (its "
            "thinking, text and each tool call), so most responses count about twice. Billable tokens count "
            "each API request once, as Anthropic bills it. Both include cache reads and writes. API cost is "
            "what the billable tokens would cost at Anthropic's published API prices. Each device records "
            "its own sessions, worktree sessions and subagents included.")
    text += "".join(f" {u['label']}: {u.get('note', 'entered by hand')}, in the cost only, its tokens and "
                    f"sessions unknown." for u in us if u.get("manual"))
    if pending:
        text += (f" {' and '.join(pending)}: Claude stats tokens counted once per request until "
                 f"{'its' if len(pending) == 1 else 'their'} next usage update.")
    newest = max(u["updated"] for u in us)
    return f"""
  {section_head("Usage", "", "usage-head")}
  <section class="usage glass" id="usage" data-view="all" aria-label="Claude Code usage">
    <div class="usage-head">
      <span class="lbl"><span class="dot"></span>Claude Code usage on CyberGen</span>
      <span class="spacer"></span>
      <span class="usage-note mono">{len(us)} device{'s' if len(us) != 1 else ''} · updated {stamp(newest)}</span>
      <button class="btn" type="button" id="usage-toggle" aria-pressed="false" aria-controls="usage-devices">By device</button>
    </div>
    <div class="usage-body">
      <dl class="usage-kpis">{kpis}</dl>
      <div class="usage-chart" aria-hidden="true">{''.join(cols)}</div>
    </div>{models}
    <div class="usage-devices" id="usage-devices" hidden>
      <table>
        <thead><tr><th scope="col">Device</th><th scope="col">Claude stats tokens</th><th scope="col">Billable tokens</th><th scope="col">API cost</th><th scope="col">Sessions</th><th scope="col">Days</th><th scope="col">Last updated</th></tr></thead>
        <tbody>{''.join(row(u) for u in us)}</tbody>
      </table>
    </div>
    <p class="usage-foot">{esc(text)}</p>
  </section>"""


def fill(name: str, out: Path, values: dict[str, str]) -> None:
    page = (SITE / name).read_text(encoding="utf-8")
    missing = sorted(set(TOKEN_RE.findall(page)) - values.keys())
    if missing:
        fail([f"{name}: no value for {missing}"])
    (out / name).write_text(TOKEN_RE.sub(lambda m: values[m.group(1)], page), encoding="utf-8")


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
    show = g["showcase"]
    common = {
        "DESCRIPTION": esc(g["lede"]),
        "OG_IMAGE": esc(f"{g['site']}img/{og}.jpg"),
        "REPO": esc(g["repo"]),
        "NEXT": esc(g.get("next", "")),
        "BUILT": esc(dt.date.today().isoformat()),
    }
    fill("index.html", out, {
        **common,
        "TITLE": esc(f"{g['title']}: {show['heading'].lower()}"),
        "PAGE_URL": esc(g["site"]),
        "NAME": esc(g["title"]),
        "HEADING": esc(show["heading"]),
        "LEDE": esc(g["lede"]),
        "STAGE_KEYS": render_stage_keys(g),
        "USAGE": render_usage(load_usage()),
        "ITEMS": render_showcase(g, dims),
    })
    fill("log.html", out, {
        **common,
        "TITLE": esc(f"{g['title']}: {g['subtitle'].lower()}"),
        "PAGE_URL": esc(f"{g['site']}log.html"),
        "FILTERS": render_filters(g),
        "RAIL": render_rail(g),
        "KICKER": esc(f"{g['subtitle']} · {dates[0]} to {dates[-1]}"),
        "STATS": render_stats(g),
        "STRIP": render_strip(g),
        "STAGES": render_stages(g, dims, latest),
    })
    for name in ("style.css", "app.js", "gallery.json"):
        shutil.copyfile(SITE / name, out / name)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"{len(g['entries'])} entries, {len(show['items'])} on the showcase, {made} images made, "
          f"site {total / 1e6:.1f} MB in {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="output folder (outside the repo when run locally)")
    args = ap.parse_args()
    build(args.out.resolve())


if __name__ == "__main__":
    main()
