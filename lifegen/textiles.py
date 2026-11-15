"""LG2: lifegen's textiles (scope 6.2), tileable PBR sets in AG6's library style.

Every textile is drawn from integer-hash noise (`assetgen.materials.noise`, read only) with
elementwise float32 arithmetic, packed by AG6's `pbr.pack` into three images (base color with
height in alpha, OpenGL normal, occlusion-roughness-metallic with the wear mask in alpha), the
same bytes everywhere. A dyed textile's base color is its weave's light and shade on white
(the person's color multiplies it in the garment material); a fixed one (rubber, metal, a
visor, the LED trim) carries its own color.

The textiles: denim (a 3/1 twill), leather (grain cells), vinyl (a smooth gloss with an orange
peel), nylon (a ripstop grid), knit (jersey stitches), rib (a knit's ribs, for cuffs and
hems), canvas (a plain weave), wool (suiting), mesh (an open grid), reflective (retroreflective
tape), LED trim (an emissive strip), and the accessories' rubber, metal, plastic and visor.
`TEXTILES` gives each its tile (m), roughness, sheen, thickness (mm, the garment's rim) and how
the material treats it (`kind`: cloth, glossy, emissive, metal, glass); `mean_rgb` the color the
mid tier's vertex colors take.

`build(out_dir, n)` writes `<name>_base.png`, `_normal.png`, `_orm.png` per textile and
`textiles.json` (the record, with each image's pixel hash); kept by the library build in the
people cache, never the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from assetgen.materials import noise as N
from assetgen.materials import pbr as P
from assetgen.materials.surfaces import Surface

F = np.float32
VERSION = "lg2.2"
SIZE = 512

# name: tile (m), kind, roughness, metal, sheen, thickness (mm), dyed, base rgb (sRGB) for
# the fixed ones, bump (mm)
TEXTILES = {
    "denim":      {"tile": 0.30, "kind": "cloth", "rough": 0.85, "metal": 0.0, "thick": 4.0,
                   "dyed": True, "bump": 0.6},
    "leather":    {"tile": 0.40, "kind": "glossy", "rough": 0.42, "metal": 0.0, "thick": 3.0,
                   "dyed": True, "bump": 0.5},
    "vinyl":      {"tile": 0.60, "kind": "glossy", "rough": 0.14, "metal": 0.0, "thick": 2.5,
                   "dyed": True, "bump": 0.2},
    "nylon":      {"tile": 0.30, "kind": "cloth", "rough": 0.48, "metal": 0.0, "thick": 3.0,
                   "dyed": True, "bump": 0.4},
    "knit":       {"tile": 0.20, "kind": "cloth", "rough": 0.9, "metal": 0.0, "thick": 3.0,
                   "dyed": True, "bump": 0.7},
    "rib":        {"tile": 0.15, "kind": "cloth", "rough": 0.9, "metal": 0.0, "thick": 4.0,
                   "dyed": True, "bump": 1.0},
    "canvas":     {"tile": 0.25, "kind": "cloth", "rough": 0.88, "metal": 0.0, "thick": 4.0,
                   "dyed": True, "bump": 0.6},
    "wool":       {"tile": 0.30, "kind": "cloth", "rough": 0.82, "metal": 0.0, "thick": 3.5,
                   "dyed": True, "bump": 0.3},
    "mesh":       {"tile": 0.12, "kind": "cloth", "rough": 0.6, "metal": 0.0, "thick": 2.0,
                   "dyed": True, "bump": 1.2},
    "reflective": {"tile": 0.10, "kind": "reflective", "rough": 0.25, "metal": 0.4,
                   "thick": 1.0, "dyed": False, "rgb": "#c8ccd0", "bump": 0.2},
    "led":        {"tile": 0.10, "kind": "emissive", "rough": 0.3, "metal": 0.0, "thick": 1.0,
                   "dyed": True, "bump": 0.1},
    "rubber":     {"tile": 0.20, "kind": "cloth", "rough": 0.62, "metal": 0.0, "thick": 4.0,
                   "dyed": False, "rgb": "#e8e6e0", "bump": 0.4},
    "metal":      {"tile": 0.20, "kind": "metal", "rough": 0.32, "metal": 1.0, "thick": 2.0,
                   "dyed": False, "rgb": "#9a9ca2", "bump": 0.2},
    "plastic":    {"tile": 0.30, "kind": "glossy", "rough": 0.3, "metal": 0.0, "thick": 2.0,
                   "dyed": False, "rgb": "#1c1d21", "bump": 0.1},
    "visor":      {"tile": 0.30, "kind": "glass", "rough": 0.05, "metal": 0.6, "thick": 2.0,
                   "dyed": False, "rgb": "#0d1418", "bump": 0.0},
}


def _rgb(h: str) -> np.ndarray:
    return np.array([int(h[1 + 2 * k:3 + 2 * k], 16) / 255.0 for k in range(3)], dtype=F)


def _rows(n: int) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:n, 0:n]
    return xx.astype(np.int64), yy.astype(np.int64)


def weave(name: str, n: int = SIZE) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A textile's shade (around 1, what the dye or color is multiplied by), height (0..1)
    and wear mask (0..1: where it fades and frays first), tileable."""
    s = N.seed_of("lg2.textile", name)
    xx, yy = _rows(n)
    slub = N.fbm(n, 8, s, 4)
    wear = N.smooth(0.45, 0.8, N.fbm(n, 4, s + 9, 4))
    if name == "denim":
        tw = ((xx + yy) % 8).astype(F) / F(8.0)                 # a 3/1 twill's diagonal
        h = N.smooth(0.0, 0.75, tw) * F(0.8) + slub * F(0.2)
        shade = F(0.72) + F(0.22) * h + F(0.12) * (slub - F(0.5))
        shade = shade + wear * F(0.25)                           # faded where worn
    elif name == "knit":
        col = (xx % 8).astype(F) / F(8.0)
        row = (yy % 8).astype(F) / F(8.0)
        v = np.abs(col - F(0.5)) * F(2.0)
        h = F(1.0) - np.abs(v - row) * F(1.2)
        h = np.clip(h, 0, 1).astype(F) * F(0.85) + slub * F(0.15)
        shade = F(0.8) + F(0.18) * h
    elif name == "rib":
        r = (xx % 8).astype(F) / F(8.0)
        h = (F(1.0) - np.abs(r - F(0.5)) * F(2.0)) * F(0.9) + slub * F(0.1)
        shade = F(0.74) + F(0.24) * h
    elif name == "canvas":
        chk = (((xx // 4) + (yy // 4)) % 2).astype(F)
        h = chk * F(0.6) + slub * F(0.4)
        shade = F(0.8) + F(0.12) * chk + F(0.1) * (slub - F(0.5))
    elif name == "wool":
        h = N.fbm(n, 64, s + 3, 3) * F(0.7) + slub * F(0.3)
        stripe = ((xx % 64) < 2).astype(F) * F(0.06)
        shade = F(0.84) + F(0.12) * (h - F(0.5)) + stripe
    elif name == "nylon":
        grid = (((xx % 32) < 2) | ((yy % 32) < 2)).astype(F)
        fine = (((xx + yy) % 3) == 0).astype(F)
        h = grid * F(0.8) + fine * F(0.15) + slub * F(0.05)
        shade = F(0.86) + F(0.08) * grid + F(0.04) * fine
    elif name == "leather":
        d, cid = N.cells(n, 48, s, 0.9)
        h = np.clip(d * F(1.6), 0, 1).astype(F) * F(0.7) + slub * F(0.3)
        shade = F(0.82) + F(0.14) * h + F(0.06) * (cid - F(0.5))
    elif name == "vinyl":
        h = N.fbm(n, 32, s + 5, 3)
        shade = F(0.92) + F(0.06) * (h - F(0.5))
    elif name == "mesh":
        hole = (((xx % 16) > 3) & ((yy % 16) > 3)).astype(F)
        h = F(1.0) - hole
        shade = F(0.95) - hole * F(0.6)
    elif name == "reflective":
        d, _ = N.cells(n, 64, s, 0.2)
        h = np.clip(F(1.0) - d * F(2.0), 0, 1).astype(F)
        shade = F(0.85) + F(0.15) * h
    elif name == "led":
        band = np.abs((yy.astype(F) + F(0.5)) / F(n) - F(0.5)) * F(2.0)
        h = (F(1.0) - band).astype(F)
        shade = F(0.85) + F(0.15) * h
    elif name == "metal":
        h = N.fbm(n, 4, s, 2) * F(0.2) + ((yy % 3) == 0).astype(F) * F(0.05)
        shade = F(0.9) + F(0.1) * h
    elif name == "rubber":
        h = N.fbm(n, 64, s, 3)
        shade = F(0.9) + F(0.08) * (h - F(0.5))
    else:                               # plastic, visor
        h = N.fbm(n, 16, s, 2) * F(0.3)
        shade = np.full((n, n), F(0.96), dtype=F) + F(0.04) * h
    return np.clip(shade, 0, 1.2).astype(F), np.clip(h, 0, 1).astype(F), wear.astype(F)


def surface(name: str, n: int = SIZE) -> Surface:
    t = TEXTILES[name]
    shade, h, wear = weave(name, n)
    base = np.ones(3, dtype=F) if t["dyed"] else _rgb(t["rgb"])
    color = np.clip(base[None, None, :] * shade[:, :, None], 0, 1).astype(F)
    rough = np.clip(F(t["rough"]) + F(0.08) * (h - F(0.5)) + F(0.1) * wear, 0, 1).astype(F)
    metal = np.full((n, n), F(t["metal"]), dtype=F)
    return Surface(color=color, height=h, rough=rough, metal=metal, mask=wear,
                   bump=float(t["bump"]))


def mean_rgb(name: str, n: int = 128) -> list[float]:
    """The textile's mean base color (linear-ish sRGB, 0..1) at a small size: what the mid
    tier's vertex colors carry for it."""
    s = surface(name, n)
    return [round(float(s.color[:, :, k].astype(np.float64).mean()), 4) for k in range(3)]


def record() -> dict:
    """What the library's hash and the garment material need: every textile's settings."""
    return {"version": VERSION, "size": SIZE,
            "textiles": {k: {**v, "mean": mean_rgb(k)} for k, v in sorted(TEXTILES.items())}}


def build(out_dir: Path, n: int = SIZE) -> dict:
    """Every textile's three images in `out_dir` and `textiles.json`; the record."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = record()
    for name, t in sorted(TEXTILES.items()):
        maps = P.pack(surface(name, n), float(t["tile"]))
        hashes = {}
        for k, a in maps.items():
            P.save_png(out_dir / f"{name}_{k}.png", a)
            hashes[k] = P.pixels_sha256(a)
        rec["textiles"][name]["images"] = hashes
    (out_dir / "textiles.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")
    return rec
