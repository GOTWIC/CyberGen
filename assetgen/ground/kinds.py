"""What each of M16's cover kinds looks like (scope 14.14): its surface (texture sets and how
they blend), its grass (clumps per square meter and their mix), and the stage's budgets.

**Surfaces.** A ground piece is drawn with its surface's three AG6 sets: `base` (the cover
itself), `worn` (what wear and edges bare: soil, mud) and `shade` (what grows in deep damp
shade: moss). The ground master blends them per pixel by the tile's mask (`tile.py`: R wear,
G shade, B edge, A moisture): worn over base by the wear (desire lines, the piece's own wear)
and the edges, the shade set over both where shade and moisture meet, darker and smoother
where it is wet. The paving kinds take AG7's paving sets by what they pave (a plaza's
granite, a market's cobbles, a yard's slabs); overgrown paving the same set, moss and soil in
its joints.

**Grass.** Per cover kind a density $D$ (clumps per m2) and a mix of clump kinds. A
candidate point every `CELL_M` (one per 0.5 m pixel of the mask, jittered in it by a hash of
its world cell) is kept with probability

$$p = D\\, a\\, (1 - w)^2\\, f_s\\, (1 + 0.6\\, m)\\, f_g\\, k_t$$

($a$ the cell's area, $w$ the wear, $f_s = 1$ up to shade 0.5 falling to 0.3 at full
shade, $m$ the moisture, $f_g$ 0.6 on slopes over 30 degrees, $k_t$ the tile's cap: at most
`TILE_INSTANCES` per tile, the kept clumps then scaled up by $k_t^{-1/2}$, at most 1.5).
Deep shade turns the mix to ferns, wet ground near water to reeds, neglect to weeds.
"""

from __future__ import annotations

CELL_M = 0.5                    # candidate grid, the mask's pixel
TILE_M = 256.0
MASK_PX = int(TILE_M / CELL_M)  # 512: the mask texture per tile
Z_LIFT_M = 0.10                 # ground pieces this far over the ground (the blockout's Z_OPEN)
FADE_M = (60.0, 100.0)          # grass instances fade out between these distances (13.9 a)
MAX_SCALE_UP = 1.5

# budgets (decision 13.9 (a): baked per tile with a cap per tile)
TILE_INSTANCES = 40_000         # grass clumps per 256 m tile
CITY_INSTANCES = 3_000_000      # per city
CLUMP_TRIANGLES = 400           # one clump variant
UNIQUE_TRIANGLES = 60_000       # every clump variant of a city together
TILE_GROUND_TRIANGLES = 250_000
CITY_GROUND_TRIANGLES = 12_000_000
TILE_DRAWN_TRIANGLES = 8_000_000    # instances times their variant's triangles, one tile

# surface: (base set, worn set, shade set, tint or None, wear, moss, edge, wet)
SURFACES: dict[str, tuple] = {
    "lawn": ("ground_lawn", "ground_dirt", "ground_moss", "#527c36", 1.0, 0.6, 0.5, 0.6),
    "park_lawn": ("ground_lawn", "ground_dirt", "ground_moss", "#4a7531", 1.0, 0.6, 0.45,
                  0.6),
    "meadow": ("ground_meadow", "ground_dirt", "ground_moss", None, 0.9, 0.5, 0.4, 0.7),
    "marsh": ("ground_meadow", "ground_mud", "ground_moss", "#4e6e36", 0.9, 0.7, 0.5, 1.0),
    "wild": ("ground_wild", "ground_dirt", "ground_rubble", None, 1.0, 0.35, 0.7, 0.5),
    "dirt": ("ground_dirt", "ground_mud", "ground_rubble", None, 0.8, 0.3, 0.5, 0.8),
    "gravel": ("ground_gravel", "ground_dirt", "ground_moss", None, 0.7, 0.35, 0.6, 0.5),
    "sand": ("ground_sand", "ground_sand", "ground_dirt", None, 0.4, 0.15, 0.3, 0.9),
    "bed": ("ground_dirt", "ground_dirt", "ground_moss", None, 0.6, 0.5, 0.3, 0.6),
}
PAVING_SETS = ("paving_granite", "paving_cobble", "paving_tile", "paving_concrete_slab",
               "paving_concrete_cast", "paving_concrete_tile", "pad_concrete")
for _s in PAVING_SETS:
    SURFACES[f"paving.{_s}"] = (_s, "ground_dirt", "ground_moss", None, 0.4, 0.15, 0.2, 0.4)
    SURFACES[f"overgrown.{_s}"] = (_s, "ground_dirt", "ground_moss", None, 0.9, 0.9, 0.6,
                                   0.6)
# what a paved piece is paved with, by what it is the open land of (M16's sources)
PAVE_OPEN = {"plaza": "paving_granite", "market": "paving_cobble",
             "promenade": "paving_tile", "courtyard": "paving_cobble",
             "podium_roof": "paving_concrete_tile"}
PAVE_ELEMENT = {"plaza": "paving_granite", "courtyard": "paving_cobble"}
PAVE_WHAT = {"open": "paving_granite", "lot": "paving_concrete_slab",
             "site": "paving_concrete_cast", "element": "pad_concrete",
             "rest": "paving_concrete_slab"}

KIND_SURFACE = {"mown_lawn": "lawn", "park_lawn": "park_lawn", "meadow": "meadow",
                "marsh": "marsh", "wasteland": "wild", "bare_dirt": "dirt",
                "gravel": "gravel", "sand": "sand", "planted_bed": "bed"}

# clump kinds: variants, footprint radius (m: where its blades root), nominal height (m)
CLUMPS: dict[str, tuple[int, float, float]] = {
    "lawn": (4, 0.17, 0.12), "clover": (4, 0.16, 0.08), "flowers": (3, 0.15, 0.32),
    "meadow": (4, 0.24, 0.55), "meadow_dry": (4, 0.24, 0.5), "reeds": (4, 0.2, 1.4),
    "cattails": (4, 0.2, 1.6), "weeds": (4, 0.16, 0.35), "fern": (4, 0.24, 0.45),
    "scrub": (4, 0.3, 0.5), "sedum": (4, 0.2, 0.1)}
MAX_FOOT_M = max(v[1] for v in CLUMPS.values()) * MAX_SCALE_UP * 1.15

# per cover kind: clumps per m2 and the clump mix
GRASS: dict[str, tuple[float, dict[str, float]]] = {
    "mown_lawn": (1.1, {"lawn": 0.8, "clover": 0.14, "flowers": 0.06}),
    "park_lawn": (1.0, {"lawn": 0.72, "clover": 0.12, "flowers": 0.1, "weeds": 0.06}),
    "meadow": (0.9, {"meadow": 0.7, "flowers": 0.14, "weeds": 0.1, "fern": 0.06}),
    "marsh": (1.0, {"reeds": 0.45, "cattails": 0.2, "meadow": 0.3, "fern": 0.05}),
    "wasteland": (0.6, {"weeds": 0.4, "meadow_dry": 0.3, "scrub": 0.22, "flowers": 0.08}),
    "bare_dirt": (0.08, {"weeds": 0.75, "scrub": 0.25}),
    "gravel": (0.05, {"weeds": 0.65, "sedum": 0.35}),
    "sand": (0.04, {"meadow_dry": 1.0}),
    "planted_bed": (1.8, {"flowers": 0.55, "fern": 0.15, "sedum": 0.15, "clover": 0.15}),
    "overgrown_paving": (0.2, {"weeds": 0.7, "meadow_dry": 0.2, "scrub": 0.1}),
    "paving": (0.0, {}),
}
GRASSY = tuple(k for k, (d, _) in GRASS.items() if d > 0)

FLOWER_FALLBACK = ("#f2efe6", "#e8c23a", "#c43c8a")


def surface_of(kind: str, what: str | None, src_kind: str | None) -> str:
    """The surface of a cover piece: its kind's, or for paving the set of what it paves."""
    if kind in KIND_SURFACE:
        return KIND_SURFACE[kind]
    if what == "open":
        s = PAVE_OPEN.get(src_kind or "", PAVE_WHAT["open"])
    elif what == "element":
        s = PAVE_ELEMENT.get(src_kind or "", PAVE_WHAT["element"])
    else:
        s = PAVE_WHAT.get(what or "rest", PAVE_WHAT["rest"])
    return f"{'overgrown' if kind == 'overgrown_paving' else 'paving'}.{s}"


def slot_of(surface: str, tile: str) -> str:
    """A ground piece's material slot: one per surface and tile (the tile's mask)."""
    return f"ground.{surface}.{tile}"


def surface_of_slot(slot: str) -> str:
    return slot.split(".", 1)[1].rsplit(".", 1)[0]


def slot_set(slot: str) -> tuple[str, str | None]:
    """(master, base set) of a ground or grass slot (the texel density check's)."""
    if slot.startswith("ground."):
        sf = SURFACES.get(surface_of_slot(slot))
        return "ground", sf[0] if sf else None
    return "grass", None


def flower_colors(palette: list[str] | None) -> list[str]:
    """Petal colors from a district's palette: its colors pushed to petal saturation and
    brightness (greys left out), else white, yellow and magenta."""
    out = []
    for h in palette or []:
        r, g, b = (int(h[1 + 2 * k:3 + 2 * k], 16) / 255.0 for k in range(3))
        mx, mn = max(r, g, b), min(r, g, b)
        if mx - mn < 0.12:
            continue
        s = (mx - mn) / mx
        if mx == r:
            hue = ((g - b) / (mx - mn)) % 6.0
        elif mx == g:
            hue = (b - r) / (mx - mn) + 2.0
        else:
            hue = (r - g) / (mx - mn) + 4.0
        s, v = max(s, 0.6), max(mx, 0.82)
        c = v * s
        x = c * (1.0 - abs(hue % 2.0 - 1.0))
        k = int(hue) % 6
        rr, gg, bb = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][k]
        m = v - c
        out.append("#" + "".join(f"{int(round((u + m) * 255)):02x}" for u in (rr, gg, bb)))
    out = sorted(set(out))[:3]
    while len(out) < 3:
        out.append(FLOWER_FALLBACK[len(out)])
    return out
