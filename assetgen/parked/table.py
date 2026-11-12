"""Which hero vehicle parks where, and in what paint (AG18 step H).

**Models by district.** A parked car draws its model from its district's weights: the
archetype's row of `BASE` (relative weights, a row need not sum to anything), each weight
then scaled by the district's wealth and danger (M11's `wealth`, `danger`, from the district's
filled spec values; the archetype's preset where left out) through the model's `CLASS`:

| class | factor | models |
|---|---|---|
| luxury | $(0.2 + 1.6\\,w)(1.25 - d)$ | the three Aurels; Halcyon Sable, Vanta-R; Orrin Aria |
| upscale | $(0.5 + w)(1.2 - 0.5\\,d)$ | Halcyon Ridge; Orrin Lumen, Pebble |
| everyday | $1.5 - 0.8\\,w$ | Tanager Mino, Cab, Porter |
| work | $0.7 + 0.6\\,d$ | Brakk Hauler, Bastion, Mule |
| hover | $(0.3 + w)(1.1 - 0.5\\,d)$ | Kestrel Dart, Meridian, Atlas |

with $w$ the wealth and $d$ the danger, both 0 to 1. So Aurel and Halcyon gather where the
district is wealthy and safe, Tanager parks everywhere and most where it is poor, Brakk's
trucks in the industrial port (and its armored Bastion where it is dangerous), Orrin in the
clean modern districts (corporate core, research campus, residential heights), Kestrel's hover
cars sparingly (a few percent; most at the spaceport). The asset spec's `vehicles.weights`
multiplies a model's weight everywhere (0 leaves it out of the city).

**Paint.** Color is never part of a brand's language (`vehicles/BRANDS.md`), so a car's paint
is drawn per placement, from the palette of its role (`ROLE`: what the car is used for, not
who made it) with the district's own colors added (`DISTRICT_COLORS`: neon in the
entertainment market, faded tones in the old town, deep blues, wines and teals in the
corporate core), by a hash of its id: the primary color; the secondary (the car's second paint channel: a spine, a
roof, a lower body) the primary again, a dark trim or a second color of the palette; the
accent (calipers, small trims) from `ACCENTS`. Colors are given in sRGB and stored linear, as
the packs' show colors are.
"""

from __future__ import annotations

import hashlib

# the packs' models (vehicles/cars/<car>.py); the Vex cars are to be redesigned and are never
# placed (scope 14.19)
EXCLUDED = ("vex_wraith", "vex_halo", "vex_strix")

CLASS = {
    "aurel_prelate": "luxury", "aurel_regent": "luxury", "aurel_zenith": "luxury",
    "halcyon_sable": "luxury", "vanta_r": "luxury", "orrin_aria": "luxury",
    "halcyon_ridge": "upscale", "orrin_lumen": "upscale", "orrin_pebble": "upscale",
    "tanager_mino": "everyday", "tanager_cab": "everyday", "tanager_porter": "everyday",
    "brakk_hauler": "work", "brakk_bastion": "work", "brakk_mule": "work",
    "kestrel_dart": "hover", "kestrel_meridian": "hover", "kestrel_atlas": "hover",
}

# relative weights per archetype (columns as `MODELS`)
MODELS = ("aurel_prelate", "aurel_regent", "aurel_zenith",
          "vanta_r", "halcyon_sable", "halcyon_ridge",
          "orrin_lumen", "orrin_pebble", "orrin_aria",
          "tanager_mino", "tanager_cab", "tanager_porter",
          "brakk_hauler", "brakk_bastion", "brakk_mule",
          "kestrel_dart", "kestrel_meridian", "kestrel_atlas")
_ROWS = {
    #                        Aurel        Halcyon      Orrin     Tanager     Brakk      Kestrel
    "corporate_core":        (5, 6, 3,     2, 5, 4,     9, 5, 2,  6, 10, 3,   1, 2, 1,   1, 1.5, 0),
    "midtown_mixed":         (2, 2, 1,     1, 3, 4,     7, 6, 1,  12, 9, 6,   2, 1, 1,   .5, 1, .5),
    "transit_hub":           (1, 2, 1,     1, 2, 2,     6, 5, 1,  10, 14, 7,  2, 1, 2,   .5, 1, .5),
    "residential_heights":   (3, 2, 1,     1, 4, 6,     8, 7, 1,  11, 3, 3,   2, 1, 0,   .5, 1, 0),
    "research_campus":       (2, 1, 1,     1, 3, 5,     10, 9, 2, 8, 3, 4,    2, 1, 1,   1, 1, .5),
    "entertainment_market":  (1, 2, 1,     3, 3, 2,     3, 3, 2,  12, 10, 6,  2, 2, 1,   1, .5, 0),
    "old_town":              (1, 1, 0,     .5, 1, 1,    2, 4, 0,  16, 6, 8,   4, 2, 2,   0, 0, 0),
    "megablock_residential": (.5, .5, 0,   .5, 1, 1,    2, 4, 0,  16, 7, 7,   4, 3, 2,   0, .5, 0),
    "industrial_port":       (0, 0, 0,     0, .5, 2,    1, 1, 0,  8, 2, 10,   12, 4, 12, 0, 0, 1.5),
    "spaceport":             (1, 1, 2,     1, 1, 3,     3, 2, 1,  6, 6, 6,    6, 3, 5,   3, 3, 4),
}
BASE = {a: dict(zip(MODELS, row)) for a, row in _ROWS.items()}
DEFAULT_ARCHETYPE = "midtown_mixed"


def class_factor(cls: str, wealth: float, danger: float) -> float:
    w = min(1.0, max(0.0, wealth))
    d = min(1.0, max(0.0, danger))
    if cls == "luxury":
        return (0.2 + 1.6 * w) * (1.25 - d)
    if cls == "upscale":
        return (0.5 + w) * (1.2 - 0.5 * d)
    if cls == "everyday":
        return 1.5 - 0.8 * w
    if cls == "work":
        return 0.7 + 0.6 * d
    return (0.3 + w) * (1.1 - 0.5 * d)              # hover


def weights(archetype: str | None, wealth: float, danger: float, cars,
            spec_weights: dict | None = None) -> dict[str, float]:
    """A district's weight per model, for the models `cars` offers (the library's); models with
    no weight left out."""
    row = BASE.get(archetype or "", BASE[DEFAULT_ARCHETYPE])
    out = {}
    for c in sorted(cars):
        if c in EXCLUDED or c not in CLASS:
            continue
        v = row.get(c, 0.0) * class_factor(CLASS[c], wealth, danger)
        v *= float((spec_weights or {}).get(c, 1.0))
        if v > 0.0:
            out[c] = round(v, 6)
    return out


# ---------------------------------------------------------------------------------------
# paint
# ---------------------------------------------------------------------------------------

ROLE = {
    "aurel_prelate": "luxury", "aurel_regent": "luxury", "aurel_zenith": "luxury",
    "halcyon_sable": "luxury",
    "vanta_r": "sport", "orrin_aria": "sport", "halcyon_ridge": "sport",
    "orrin_lumen": "private", "orrin_pebble": "private", "tanager_mino": "private",
    "tanager_cab": "fleet", "tanager_porter": "fleet",
    "brakk_hauler": "work", "brakk_bastion": "work", "brakk_mule": "work",
    "kestrel_dart": "sport", "kestrel_meridian": "private", "kestrel_atlas": "work",
}

# sRGB hex, (name, weight)
PALETTES = {
    "luxury": {"#0b0c0e": 4, "#f1efe8": 4, "#a9adb2": 3, "#2b2e33": 3, "#121c33": 3,
               "#4a1219": 3, "#b8a27c": 2, "#5a4632": 1, "#16301f": 2, "#3d2a5c": 1},
    "sport": {"#c1121b": 4, "#f2c40c": 3, "#ef6c11": 2, "#7ccf1c": 1, "#11b2c9": 2,
              "#c71d8b": 1, "#f4f4f2": 4, "#0d0d0f": 4, "#3c4147": 3, "#4b2a8a": 1,
              "#1a4fd0": 2},
    "private": {"#f2f2ef": 6, "#b5b8bb": 5, "#6c7075": 4, "#151618": 4, "#1d3557": 3,
                "#8e1b1b": 2, "#cbbf9f": 2, "#1f6f6a": 2, "#c99a2e": 1, "#7fa7c9": 2,
                "#5b6b3a": 1, "#d86a4a": 1},
    "fleet": {"#f5c518": 6, "#f4f4f1": 4, "#121314": 3, "#11847e": 2, "#ec6a1c": 2,
              "#2e6fd1": 1, "#b51e2e": 1},
    "work": {"#f2b705": 4, "#e8641b": 3, "#55603a": 3, "#c2a878": 2, "#e8e6df": 3,
             "#7c8288": 3, "#1c1d1f": 2, "#8a3324": 2, "#3c5878": 2},
}
DISTRICT_COLORS = {
    "entertainment_market": {"#ff1f8e": 4, "#12e6ff": 4, "#8c2bff": 3, "#a6ff00": 2,
                             "#ff7a00": 2},
    "old_town": {"#7a6a4f": 2, "#556b2f": 2, "#8c5a3c": 2, "#5f7f8a": 2},
    "megablock_residential": {"#6e7f5a": 1, "#8a7d6b": 1},
    "corporate_core": {"#9aa0a6": 1, "#123a6b": 2, "#6b0f1a": 2, "#0f5257": 2, "#b0892f": 1},
    "research_campus": {"#e9eef2": 2, "#9ec9d6": 1},
    "spaceport": {"#e9eaec": 2, "#ff5a1f": 1},
    "industrial_port": {"#f2b705": 2, "#e8641b": 1},
}
TRIMS = ("#141517", "#26282b", "#3a3d41", "#8d9196")
ACCENTS = {"#c1121b": 3, "#f2c40c": 2, "#11b2c9": 1, "#f4f4f2": 2, "#1c1d1f": 3,
           "#d4af37": 1, "#ef6c11": 1}


def lin(hexcol: str) -> list[float]:
    """An sRGB hex color as linear RGB, rounded to 4 decimals."""
    out = []
    for i in (1, 3, 5):
        c = int(hexcol[i:i + 2], 16) / 255.0
        v = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        out.append(round(v, 4))
    return out


def u(*parts) -> float:
    """A uniform draw in [0, 1) from a blake2b hash of the parts (`props.styles.pick`'s)."""
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big") / float(1 << 64)


def pick_weighted(items: dict, *salt) -> str:
    keys = sorted(items)
    tot = sum(items[k] for k in keys)
    x = u(*salt) * tot
    for k in keys:
        x -= items[k]
        if x < 0.0:
            return k
    return keys[-1]


def palette(car: str, archetype: str | None) -> dict[str, float]:
    pal = dict(PALETTES[ROLE.get(car, "private")])
    for k, v in DISTRICT_COLORS.get(archetype or "", {}).items():
        pal[k] = pal.get(k, 0) + v
    return pal


def paint(car: str, archetype: str | None, pid: str, turn: int = 0) -> tuple[list, str]:
    """A placement's three paint colors (linear) and its primary's hex. `turn` draws again
    (the variety rule: a curb neighbor of the same model in the same color)."""
    pal = palette(car, archetype)
    p1 = pick_weighted(pal, "ag18.paint.p1", pid, turn)
    r = u("ag18.paint.p2", pid)
    if r < 0.45:
        p2 = p1
    elif r < 0.8:
        p2 = TRIMS[int(u("ag18.paint.trim", pid) * len(TRIMS))]
    else:
        p2 = pick_weighted(pal, "ag18.paint.p2c", pid)
    p3 = pick_weighted(ACCENTS, "ag18.paint.p3", pid)
    return [lin(p1), lin(p2), lin(p3)], p1
