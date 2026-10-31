"""The library's atlases (scope 5.2): window interiors by day and night, trim sheets per era,
the decal atlas, the road atlas and the macro variation map.

Atlases are stored the natural way (row 0 at the top of the content, as PIL draws): the
masters compute their own lookups into them. The tileable sets (`library.SETS`) are the ones
sampled straight by a mesh's UV0 and drawn with rows going up the surface (`pbr`).

- `interiors`: `interiors_day.png`, `interiors_night.png` (`interiors.atlas`), cell = half
  the density (256 px at 512 px/m).
- `trim_<era>`: 2 x 1 m at the street density, eight strips of 0.125 m (`TRIM_STRIPS`:
  window frame, stone sill, cornice molding, panel joint, railing, metal edge, rubber seal,
  louver), maps as a set's.
- `decals`: 4 x 4 cells of 1 m (`DECAL_CELLS`): grime, leaks, rust, cracks, graffiti,
  posters, stickers, moss; base color with coverage in alpha, normal, occlusion-roughness-
  metallic.
- `road`: 4 x 4 cells of 2 m (`ROAD_CELLS`): oil, cracks, patches, tar snakes, skid marks, a
  manhole, a drain, arrows, a puddle, sand, dust; as the decals.
- `macro`: 1024 px over 64 m: albedo and roughness variation, dirt and damp masks (RGBA),
  which the masters lay over every set so its tiling does not show.
- `water` (AG12): ripple normals, foam and caustics over 8 m
  (`water_surfaces.water_atlas`).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from . import glyphs as GL
from . import interiors as IN
from . import noise as N
from . import pbr as P
from . import surfaces as S

F = np.float32
TRIM_STRIPS = ("frame", "sill", "cornice", "joint", "railing", "edge", "seal", "louver")
DECAL_CELLS = ("grime_ground", "grime_patch", "leaks_a", "leaks_b", "rust_bleed", "rust_drip",
               "cracks_a", "cracks_b", "graffiti_a", "graffiti_b", "graffiti_c", "poster_a",
               "poster_b", "poster_c", "stickers", "moss")
ROAD_CELLS = ("oil_a", "oil_b", "cracks_a", "cracks_b", "patch_a", "patch_b", "tar_snakes",
              "skid", "manhole", "drain", "arrow_straight", "arrow_left", "arrow_right",
              "puddle", "sand", "dust")
MACRO_M = 64.0
ATLASES = ("interiors", "decals", "road", "macro", "water") + tuple(
    f"trim_{e}" for e in ("heritage", "neon_retro", "corporate_glass", "brutalist",
                          "industrial", "clean_tech", "suburban_modern", "transit_modern",
                          "mixed_modern", "aerospace"))
GRAFFITI_WORDS = ("KAOS", "VEXX", "ZERO", "NULL", "RIOT", "GHOST", "WIRED", "SYNC", "HEX",
                  "ROGUE", "FLUX", "NOVA", "STATIC", "GLITCH", "BURN", "ECHO")
POSTER_WORDS = ("LIVE", "TONIGHT", "NEON", "WAKE UP", "OBEY", "RAVE", "SALE", "VOTE",
                "MISSING", "JOBS", "NEW", "BLACK ICE", "DREAM", "CHROME")
COLORS = ("#ff3fb4", "#2fe0ff", "#9d4dff", "#ff8a1f", "#39ff8f", "#ffd23f", "#ff4040",
          "#f2f2f2", "#1a1a1a")


def _c(hexc):
    return tuple(int(hexc[1 + 2 * k:3 + 2 * k], 16) for k in range(3))


def _rng(seed):
    st = [seed & 0x7FFFFFFF]

    def r():
        st[0] = (st[0] * 1103515245 + 12345) & 0x7FFFFFFF
        return st[0] / 2147483648.0
    return r


def _down2(a: np.ndarray) -> np.ndarray:
    """Halve an image by 2 x 2 means, in integers (exact)."""
    b = a.astype(np.uint32)
    s = b[0::2, 0::2] + b[1::2, 0::2] + b[0::2, 1::2] + b[1::2, 1::2]
    return ((s + 2) // 4).astype(np.uint8)


def _layer(n: int, draw_fn) -> np.ndarray:
    """An RGBA layer (n x n) drawn by PIL at twice the size, halved: uint8."""
    img = Image.new("RGBA", (2 * n, 2 * n), (0, 0, 0, 0))
    draw_fn(img, 2 * n)
    return _down2(np.asarray(img))


# --- cells: (color 0..1 sRGB (n, n, 3), alpha, height, rough, metal) ------------------------

def _empty(n):
    return (np.zeros((n, n, 3), F), np.zeros((n, n), F), np.full((n, n), F(0.5)),
            np.full((n, n), F(0.8)), np.zeros((n, n), F))


def _flat(n, hexc, alpha, height=None, rough=0.85, metal=0.0, shade=None):
    c = S.rgb(hexc)
    col = np.broadcast_to(c[None, None, :], (n, n, 3)).astype(F)
    if shade is not None:
        col = np.clip(col * shade[:, :, None], 0, 1).astype(F)
    h = height if height is not None else np.full((n, n), F(0.5))
    return (col, np.clip(alpha, 0, 1).astype(F), h.astype(F), np.full((n, n), F(rough)),
            np.full((n, n), F(metal)))


def _y_down(n):
    """Rows from the top, 0..1 (natural orientation)."""
    _, py = N.grid(n)
    return py


def decal_cell(name: str, n: int, seed: int):
    px, py = N.grid(n)
    yd = py                                 # 0 at the top
    fb = N.fbm(n, 4, seed, 5)
    if name.startswith("grime_ground"):
        a = N.smooth(0.25, 1.0, yd) * N.smooth(0.3, 0.7, fb) * F(0.9)
        return _flat(n, "#2e2a24", a, rough=0.9)
    if name == "grime_patch":
        r2 = (px - F(0.5)) ** 2 + (py - F(0.5)) ** 2
        a = N.smooth(0.22, 0.05, r2) * N.smooth(0.35, 0.65, fb)
        return _flat(n, "#3a352d", a, rough=0.9)
    if name.startswith("leaks"):
        cols = N.value(n, 48 if name == "leaks_a" else 24, seed, px,
                       (py * F(0.02)).astype(F))
        length = N.value(n, 48 if name == "leaks_a" else 24, seed + 1, px,
                         (py * F(0.0)).astype(F))
        streak = N.smooth(0.55, 0.85, cols)
        fade = np.clip(F(1.0) - yd / np.maximum(length * F(1.2), F(0.15)), 0, 1)
        a = streak * fade * F(0.85) * (F(0.7) + F(0.3) * fb)
        return _flat(n, "#2b2925", a, rough=0.6)
    if name.startswith("rust"):
        k = 3 if name == "rust_bleed" else 7
        cols = N.value(n, k * 4, seed, px, (py * F(0.03)).astype(F))
        src = N.smooth(0.6, 0.85, cols)
        fade = np.clip(F(1.0) - yd * F(1.1 if name == "rust_bleed" else 1.6), 0, 1)
        a = src * fade * (F(0.6) + F(0.4) * fb)
        return _flat(n, "#7a3b1c", a, rough=0.85,
                     shade=(F(0.8) + F(0.4) * N.fbm(n, 32, seed + 2, 3)).astype(F))
    if name.startswith("cracks"):
        c = S.cracks(n, seed, 0.9 if name == "cracks_a" else 0.6)
        return _flat(n, "#1e1c1a", c, height=(F(0.5) - F(0.4) * c).astype(F), rough=0.9)
    if name.startswith("graffiti"):
        r = _rng(seed)
        word = GRAFFITI_WORDS[int(r() * len(GRAFFITI_WORDS))]
        fill = _c(COLORS[int(r() * 7)])
        line = _c(COLORS[int(r() * 9)])

        def draw(img, m):
            st, w = GL.layout(word, "latin")
            sc = (m * 0.85) / max(w, 1.0)
            sc = min(sc, m * 0.5 / 6.0)
            x0 = (m - w * sc) / 2
            y0 = m * 0.5 + 3 * sc
            wob = [[(x + 0.35 * (r() - 0.5), y + 0.5 * (r() - 0.5)) for x, y in s] for s in st]
            GL.draw(img, wob, x0, y0, sc, sc * 2.4, (20, 20, 20, 255))
            GL.draw(img, wob, x0, y0, sc, sc * 1.6, fill + (255,))
            GL.draw(img, wob, x0, y0, sc, sc * 0.35, line + (255,))
        lay = _layer(n, draw)
        col = (lay[:, :, :3].astype(F) / F(255.0)).astype(F)
        a = (lay[:, :, 3].astype(F) / F(255.0)) * (F(0.75) + F(0.25) * fb)
        return (col, a.astype(F), np.full((n, n), F(0.52)), np.full((n, n), F(0.55)),
                np.zeros((n, n), F))
    if name.startswith("poster") or name == "stickers":
        r = _rng(seed)

        def draw(img, m):
            from PIL import ImageDraw
            d = ImageDraw.Draw(img)
            count = 3 if name != "stickers" else 26
            for k in range(count):
                if name == "stickers":
                    w = int(m * (0.06 + 0.08 * r()))
                    h = int(w * (0.5 + r()))
                else:
                    w = int(m * (0.35 + 0.25 * r()))
                    h = int(w * 1.4)
                x = int((m - w) * r())
                y = int((m - h) * r())
                bg = _c(COLORS[int(r() * len(COLORS))])
                d.rectangle([x, y, x + w, y + h], fill=bg + (255,))
                if name != "stickers":
                    fg = _c(COLORS[int(r() * len(COLORS))])
                    d.rectangle([x + w // 8, y + h // 3, x + 7 * w // 8, y + 3 * h // 4],
                                fill=fg + (255,))
                    word = POSTER_WORDS[int(r() * len(POSTER_WORDS))]
                    st, tw = GL.layout(word, "latin")
                    sc = min((w * 0.8) / max(tw, 1.0), h * 0.18 / 6.0)
                    GL.draw(img, st, x + (w - tw * sc) / 2, y + h * 0.26, sc, max(2, sc * 0.9),
                            (240, 240, 240, 255) if sum(bg) < 380 else (20, 20, 20, 255))
        lay = _layer(n, draw)
        col = (lay[:, :, :3].astype(F) / F(255.0)).astype(F)
        tear = N.smooth(0.25, 0.4, N.fbm(n, 16, seed + 3, 4))
        fadec = F(0.75) + F(0.25) * fb
        col = (col * fadec[:, :, None]).astype(F)
        a = (lay[:, :, 3].astype(F) / F(255.0)) * tear
        return (col, a.astype(F), np.full((n, n), F(0.55)), np.full((n, n), F(0.7)),
                np.zeros((n, n), F))
    if name == "moss":
        a = N.smooth(0.5, 0.75, fb) * N.smooth(0.0, 0.6, yd)
        sh = (F(0.7) + F(0.6) * N.fbm(n, 64, seed + 2, 3)).astype(F)
        return _flat(n, "#3d5a2a", a, height=(F(0.5) + F(0.2) * a).astype(F), rough=0.95,
                     shade=sh)
    return _empty(n)


def road_cell(name: str, n: int, seed: int):
    px, py = N.grid(n)
    fb = N.fbm(n, 4, seed, 5)
    cx, cy = px - F(0.5), py - F(0.5)
    r2 = cx * cx + cy * cy
    if name.startswith("oil"):
        a = N.smooth(0.16, 0.02, r2 * (F(0.7) + F(0.6) * fb)) * F(0.8)
        return _flat(n, "#0c0c0e", a, rough=0.35)
    if name.startswith("cracks"):
        c = S.cracks(n, seed, 1.0 if name == "cracks_a" else 0.7)
        return _flat(n, "#141416", c, height=(F(0.5) - F(0.4) * c).astype(F))
    if name.startswith("patch"):
        w = F(0.38 if name == "patch_a" else 0.28)
        h = F(0.3 if name == "patch_a" else 0.42)
        inside = (np.abs(cx) < w) & (np.abs(cy) < h)
        edge = N.smooth(0.0, 0.01, np.minimum(w - np.abs(cx), h - np.abs(cy)))
        a = np.where(inside, edge, F(0.0)).astype(F)
        sh = (F(0.9) + F(0.25) * N.white(n, seed + 1)).astype(F)
        return _flat(n, "#1c1d20", a, height=(F(0.5) + F(0.05) * a).astype(F), rough=0.75,
                     shade=sh)
    if name == "tar_snakes":
        c = N.smooth(0.9, 0.96, N.ridged(n, 3, seed, 3))
        return _flat(n, "#08080a", c, height=(F(0.5) + F(0.15) * c).astype(F), rough=0.3)
    if name == "skid":
        band = (N.smooth(0.05, 0.02, np.abs(np.abs(cx) - F(0.16))) * N.smooth(0.0, 0.3, fb))
        return _flat(n, "#0a0a0a", band * F(0.7), rough=0.6)
    if name == "manhole":
        rr = np.sqrt(r2)
        disc = N.smooth(0.31, 0.3, rr)
        ring = N.smooth(0.31, 0.3, rr) * N.smooth(0.27, 0.28, rr)
        dx = (px * F(24.0) - np.floor(px * F(24.0)))
        dy = (py * F(24.0) - np.floor(py * F(24.0)))
        dia = (np.abs(dx - F(0.5)) + np.abs(dy - F(0.5)) < F(0.28)).astype(F)
        h = F(0.4) + F(0.3) * dia * (F(1.0) - ring) + F(0.2) * ring
        return _flat(n, "#3a3734", disc, height=h.astype(F), rough=0.55, metal=0.85,
                     shade=(F(0.85) + F(0.3) * dia).astype(F))
    if name == "drain":
        box = (np.abs(cx) < F(0.25)) & (np.abs(cy) < F(0.12))
        bars = (px * F(30.0) - np.floor(px * F(30.0))) < F(0.55)
        a = box.astype(F)
        h = np.where(box & ~bars, F(0.05), F(0.55)).astype(F)
        sh = np.where(box & ~bars, F(0.2), F(1.0)).astype(F)
        return _flat(n, "#2a2a2a", a, height=h, rough=0.6, metal=0.8, shade=sh)
    if name.startswith("arrow"):
        def draw(img, m):
            from PIL import ImageDraw
            d = ImageDraw.Draw(img)
            u = m / 20.0
            pts = [(9 * u, 18 * u), (11 * u, 18 * u), (11 * u, 8 * u), (13.5 * u, 8 * u),
                   (10 * u, 2 * u), (6.5 * u, 8 * u), (9 * u, 8 * u)]
            d.polygon([(int(x), int(y)) for x, y in pts], fill=(255, 255, 255, 255))
            if name != "arrow_straight":
                s = -1 if name == "arrow_left" else 1
                q = [(10 + s * 1 * x, y) for x, y in ((0, 12), (0, 10), (4, 10), (4, 8),
                                                      (7.5, 11), (4, 14), (4, 12))]
                d.polygon([(int(x * u), int(y * u)) for x, y in q],
                          fill=(255, 255, 255, 255))
        lay = _layer(n, draw)
        wear = N.smooth(0.25, 0.45, N.fbm(n, 16, seed + 2, 4))
        a = (lay[:, :, 3].astype(F) / F(255.0)) * wear
        return _flat(n, "#e4e4dc", a, height=(F(0.5) + F(0.1) * a).astype(F), rough=0.6)
    if name == "puddle":
        a = N.smooth(0.55, 0.62, fb * (F(1.0) - F(1.8) * r2))
        return _flat(n, "#101214", a, height=(F(0.5) - F(0.1) * a).astype(F), rough=0.05)
    if name == "sand":
        a = N.smooth(0.4, 0.8, fb) * F(0.6)
        return _flat(n, "#8a7a5e", a, rough=0.95)
    return _flat(n, "#4a4640", N.smooth(0.45, 0.75, fb) * F(0.5), rough=0.95)


def _atlas_maps(cells, n: int, grid: int, cell_m: float) -> dict[str, np.ndarray]:
    m = n * grid
    col = np.zeros((m, m, 3), F)
    alpha = np.zeros((m, m), F)
    h = np.zeros((m, m), F)
    rough = np.zeros((m, m), F)
    metal = np.zeros((m, m), F)
    for k, c in enumerate(cells):
        i, j = divmod(k, grid)
        sl = (slice(i * n, (i + 1) * n), slice(j * n, (j + 1) * n))
        col[sl], alpha[sl], h[sl], rough[sl], metal[sl] = c
    # rows run down here; the normal wants rows up a surface: flip, take it, flip back
    nrm = P.u8(P.normal(h[::-1], 2.0, cell_m * grid))[::-1]
    base = np.concatenate([P.u8(col), P.u8(alpha)[:, :, None]], axis=2)
    ao = P.occlusion(h, m)
    orm = np.stack([P.u8(ao), P.u8(rough), P.u8(metal)], axis=2)
    return {"base": base, "normal": np.ascontiguousarray(nrm), "orm": orm}


def trim_sheet(era: str, density: int) -> dict[str, np.ndarray]:
    from .library import ERA_LOOK
    look = ERA_LOOK[era]
    w = int(2 * density)
    hs = int(0.125 * density)
    seed = N.seed_of("ag6.trim", era)
    wear = look["wear"]
    rows = []
    for k, strip in enumerate(TRIM_STRIPS):
        n = w
        sub = {"frame": ("brushed", {"color": "#5d6166", "rough": 0.4}),
               "sill": ("stone", {"color": look["plaster"]["color"], "wear": wear}),
               "cornice": ("plaster", {"color": look["plaster"]["color"], "wear": wear}),
               "joint": ("smooth_paint", {"color": "#3a3a3a", "rough": 0.7, "wear": wear}),
               "railing": ("smooth_paint", {"color": "#2e3236", "metallic": 0.7,
                                            "wear": wear, "under": "#6b3b22"}),
               "edge": ("sheet", {"color": "#8a8f94", "wear": wear}),
               "seal": ("smooth_paint", {"color": "#151515", "rough": 0.85, "wear": 0.1}),
               "louver": ("louver", {"color": look["cladding"]["color"]})}[strip]
        s = S.make(sub[0], n, 2.0, {"seed": seed + k, **sub[1]})
        prof = np.linspace(0.0, 1.0, hs, dtype=F)
        shape = {"frame": N._fade(np.minimum(prof * F(3.0), F(1.0))),
                 "sill": F(1.0) - prof * F(0.3),
                 "cornice": np.where(prof < F(0.3), F(0.4), np.where(prof < F(0.6), F(0.8),
                                                                      F(1.0))),
                 "joint": np.where(np.abs(prof - F(0.5)) < F(0.15), F(0.1), F(0.7)),
                 "railing": np.where(np.abs(prof - F(0.5)) < F(0.3), F(1.0), F(0.0)),
                 "edge": F(0.5) + F(0.5) * N._fade(prof),
                 "seal": F(0.5) + F(0.2) * (F(1.0) - np.abs(prof * F(2.0) - F(1.0))),
                 "louver": prof}[strip].astype(F)
        rows.append((s, shape))
    col = np.concatenate([s.color[:hs] for s, _ in rows], axis=0)
    height = np.concatenate([np.clip(s.height[:hs] * F(0.3) + shape[:, None] * F(0.7), 0, 1)
                             for s, shape in rows], axis=0).astype(F)
    rough = np.concatenate([s.rough[:hs] for s, _ in rows], axis=0)
    metal = np.concatenate([s.metal[:hs] for s, _ in rows], axis=0)
    mask = np.concatenate([s.mask[:hs] for s, _ in rows], axis=0)
    nrm = P.u8(P.normal(height, 6.0, 2.0))
    base = np.concatenate([P.u8(col), P.u8(height)[:, :, None]], axis=2)
    orm = np.stack([P.u8(P.occlusion(height, w)), P.u8(rough), P.u8(metal), P.u8(mask)],
                   axis=2)
    return {"base": base, "normal": nrm, "orm": orm}


def macro() -> dict[str, np.ndarray]:
    n = 1024
    s = N.seed_of("ag6.macro")
    a = N.fbm(n, 4, s, 6)
    b = N.fbm(n, 8, s + 1, 5)
    c = N.smooth(0.5, 0.8, N.fbm(n, 6, s + 2, 5))
    d = N.smooth(0.55, 0.85, N.fbm(n, 3, s + 3, 5))
    return {"macro": np.stack([P.u8(a), P.u8(b), P.u8(c), P.u8(d)], axis=2)}


def make(name: str, out_dir: str, density: int) -> dict:
    """Make one atlas into out_dir/atlases/; its index record."""
    od = Path(out_dir)
    rec: dict = {"kind": "atlas", "files": {}}
    if name == "interiors":
        cell = max(32, density // 2)
        day, night = IN.atlas(cell)
        maps = {"day": P.u8(day), "night": P.u8(night)}
        rec.update(grid=[IN.VARIANTS, len(IN.USES)], cells=list(IN.USES), cell_px=cell,
                   back=IN.BACK)
    elif name == "decals":
        n = max(32, density)
        seed = N.seed_of("ag6.decals")
        cells = [decal_cell(c, n, seed + 17 * k) for k, c in enumerate(DECAL_CELLS)]
        maps = _atlas_maps(cells, n, 4, 1.0)
        rec.update(grid=[4, 4], cells=list(DECAL_CELLS), cell_m=1.0, cell_px=n)
    elif name == "road":
        n = max(32, density)
        seed = N.seed_of("ag6.road")
        cells = [road_cell(c, n, seed + 17 * k) for k, c in enumerate(ROAD_CELLS)]
        maps = _atlas_maps(cells, n, 4, 2.0)
        rec.update(grid=[4, 4], cells=list(ROAD_CELLS), cell_m=2.0, cell_px=n)
    elif name == "macro":
        maps = macro()
        rec.update(tile_m=MACRO_M)
    elif name.startswith("trim_"):
        maps = trim_sheet(name[5:], density)
        rec.update(strips=list(TRIM_STRIPS), tile_m=[2.0, 1.0])
    elif name == "water":
        # AG12: the water master's ripples and foam, the bed master's caustics
        from .water_surfaces import WATER_TILE_M, water_atlas
        maps = water_atlas(density)
        rec.update(tile_m=WATER_TILE_M)
    else:
        raise KeyError(name)
    for k, a in maps.items():
        f = f"atlases/{name}_{k}.png"
        P.save_png(od / f, a)
        rec["files"][k] = {"file": f, "size": [int(a.shape[1]), int(a.shape[0])],
                           "channels": int(a.shape[2]), "pixels_sha256": P.pixels_sha256(a)}
    return rec
