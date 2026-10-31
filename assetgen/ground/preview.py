"""The ground stage's preview (`ground/preview.png`, PIL only): the city's open land from
above at 2 m a pixel, each piece in its surface's color, its desire lines worn, the decks
dark, and every clump a dot in its kind's color; beside it the tile with the most clumps at
0.25 m a pixel, its mask's wear and shade over the surfaces and each clump drawn to its
footprint."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from . import clumps as CL
from . import gather as GA
from . import kinds as K

SURF = {"lawn": "#5f8a3e", "park_lawn": "#4f8040", "meadow": "#8ba04e", "marsh": "#4e7a5a",
        "wild": "#9a9050", "dirt": "#7a5a3c", "gravel": "#9c968c", "sand": "#d8c48e",
        "bed": "#6a4a30"}
PAVE = "#8a8a8e"
OVERGROWN = "#76806a"
CLUMP = {"lawn": "#2f5a1c", "clover": "#3f7a2a", "meadow": "#6a8a2a", "meadow_dry": "#b09a50",
         "reeds": "#4a6a3a", "cattails": "#6a4a2a", "weeds": "#4a6a20", "fern": "#1f5a28",
         "scrub": "#5a5a28", "sedum": "#8a7a30"}
BG = (34, 36, 40)
SCALE = 0.5            # pixels a meter, the city
DETAIL = 4.0           # pixels a meter, the detail tile


def _color(surface: str) -> str:
    if surface in SURF:
        return SURF[surface]
    return OVERGROWN if surface.startswith("overgrown.") else PAVE


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[1 + 2 * k:3 + 2 * k], 16) for k in range(3))


def _kind_of(node: str) -> str:
    return node.split(".")[1]


def _flower(node: str) -> str | None:
    if node.startswith("clump.flowers."):
        return "#" + node.split(".")[2].split("_")[0]
    return None


def preview(model, man: dict, out_dir: Path, path: Path) -> bool:
    from . import kinds as KK
    from .gather import _sources
    x0, y0, x1, y1 = model.bounds
    W, H = int((x1 - x0) * SCALE) + 1, int((y1 - y0) * SCALE) + 1

    def P(x, y, s=SCALE, ox=x0, oy=y1):
        return ((x - ox) * s, (oy - y) * s)
    src = _sources(model)
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)
    surf_of = {}
    for g in model.ground_cover:
        what, sk = src.get(g.source_id, ("rest", None)) if g.source_id else ("rest", None)
        sf = KK.surface_of(g.kind, what, sk)
        surf_of[g.id] = sf
        dr.polygon([P(x, y) for x, y in g.polygon.exterior], fill=_rgb(_color(sf)))
        for h in g.polygon.holes:
            dr.polygon([P(x, y) for x, y in h], fill=BG)
    for d in getattr(model, "decks", []) or []:
        dr.polygon([P(x, y) for x, y in d.polygon.exterior], outline=(20, 20, 24))
    for g in model.ground_cover:
        for d in g.desire_lines:
            dr.line([P(x, y) for x, y in d.line], fill=(140, 110, 70),
                    width=max(1, int(d.width_m * SCALE)))
    gdir = out_dir / "ground" / "grass"
    best = (0, None)
    for t, r in sorted(man["tiles"].items()):
        n = sum((r.get("instances") or {}).values())
        if not n:
            continue
        if n > best[0]:
            best = (n, t)
        doc = json.loads((gdir / f"{t}.json").read_text(encoding="utf-8"))
        px, py, _ = doc["pivot"]
        for nd, xf in doc["nodes"].items():
            col = _rgb(_flower(nd) or CLUMP.get(_kind_of(nd), "#406020"))
            for q in xf[::2]:
                dr.point(P(q[0] + px, q[1] + py), fill=col)
    panels = [img]
    if best[1] is not None:
        t = best[1]
        bx0, by0, bx1, by1 = GA.tile_box(t)
        S = int(K.TILE_M * DETAIL)
        det = Image.new("RGB", (S, S), BG)
        dd = ImageDraw.Draw(det)

        def Q(x, y):
            return ((x - bx0) * DETAIL, (by1 - y) * DETAIL)
        for g in model.ground_cover:
            bb = [min(p[0] for p in g.polygon.exterior), min(p[1] for p in g.polygon.exterior),
                  max(p[0] for p in g.polygon.exterior), max(p[1] for p in g.polygon.exterior)]
            if bb[2] < bx0 or bb[0] > bx1 or bb[3] < by0 or bb[1] > by1:
                continue
            dd.polygon([Q(x, y) for x, y in g.polygon.exterior],
                       fill=_rgb(_color(surf_of[g.id])))
            for h in g.polygon.holes:
                dd.polygon([Q(x, y) for x, y in h], fill=BG)
        mp = out_dir / "ground" / "masks" / f"{t}.png"
        if mp.is_file():
            mk = Image.open(mp).convert("RGBA").resize((S, S), Image.BILINEAR)
            mk = mk.transpose(Image.FLIP_TOP_BOTTOM)        # (row 0 is the south edge)
            r_, g_, b_, a_ = mk.split()
            worn = Image.new("RGB", (S, S), (120, 92, 60))
            det = Image.composite(worn, det, r_.point(lambda v: int(v * 0.9)))
            dark = Image.new("RGB", (S, S), (10, 12, 10))
            det = Image.composite(dark, det, g_.point(lambda v: int(max(0, v - 60) * 0.6)))
            dd = ImageDraw.Draw(det)
        doc = json.loads((gdir / f"{t}.json").read_text(encoding="utf-8"))
        px, py, _ = doc["pivot"]
        for nd, xf in doc["nodes"].items():
            kind = _kind_of(nd)
            col = _rgb(_flower(nd) or CLUMP.get(kind, "#406020"))
            rad = K.CLUMPS[kind][1]
            for q in xf:
                cx_, cy_ = Q(q[0] + px, q[1] + py)
                rr = max(1.0, rad * q[4] * DETAIL)
                dd.ellipse([cx_ - rr, cy_ - rr, cx_ + rr, cy_ + rr], outline=col)
        dd.rectangle([0, 0, S - 1, S - 1], outline=(240, 240, 240))
        dd.text((8, 8), f"{t}: {best[0]:,} clumps", fill=(240, 240, 240))
        panels.append(det)
    Hh = max(p.size[1] for p in panels)
    out = Image.new("RGB", (sum(p.size[0] for p in panels) + 16 * (len(panels) - 1), Hh), BG)
    xo = 0
    for p in panels:
        out.paste(p, (xo, 0))
        xo += p.size[0] + 16
    path.parent.mkdir(parents=True, exist_ok=True)
    import io
    bio = io.BytesIO()
    out.save(bio, "PNG", optimize=False)
    data = bio.getvalue()
    if path.is_file() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


__all__ = ["preview", "CL"]
