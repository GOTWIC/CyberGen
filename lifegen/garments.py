"""LG2: lifegen's clothing (scope 6.2): the garments' patterns, each character's looks and the
drafts the Blender stage builds them from.

The library (`lifegen/library.py`) gives each of its characters `LOOKS` looks, each a whole
outfit of one fashion group (`presets.GROUPS`, and `rain`, the weather's): a base layer (a
tee, long tee, shirt, hoodie or coveralls), an outer layer or none (bomber, jacket, trench,
raincoat), a bottom (cargo pants, trousers, a skirt; none under coveralls), shoes (sneakers,
boots, dress shoes) and accessories (visors, respirators, masks, headsets, caps, beanies, hard
hats, implants, arm plates, backpacks, bags), each garment in a textile of its group
(`lifegen/textiles.py`) with its trims (ribs, zips, reflective bands, LED lines, pockets).
`looks_of(character)` draws them (blake2b from the character's index and the look's), so the
library's spec and hash carry them.

A garment's pattern is a few parameters (`KINDS` and the look's draw: fit, length, sleeve,
neckline, flare, hood, collar, opening, trims); `draft` turns them into the cuts and eases of
the Blender stage (`lifegen/blender/garments.py`) by the body's own measurements
(`measure`: its landmarks from its bones), so every garment is cut for the body it dresses.
`blender_job` is one character's job.

The dye channels: a garment's color comes from the person (`plan.crowd_plan`), channel 0 the
base layer, 1 the outer layer (or a hood, a cap), 2 the bottom; a garment with channel -1
keeps its own color (`rgb`: shoes, a police uniform, rubber, metal).
"""

from __future__ import annotations

import hashlib
import json

from . import presets as P
from . import textiles as TX

LOOKS = 6                   # looks per character
# how many of the library's looks each group gets (24 characters x LOOKS); a character has at
# most one look of a group
GROUP_LOOKS = {"street": 24, "corporate": 22, "techwear": 20, "nightlife": 16, "market": 14,
               "industrial": 14, "punk": 10, "gang": 10, "police": 6, "rain": 8}
GROUPS = tuple(GROUP_LOOKS)
BONES = ("head", "spine_04", "spine_02")       # what accessories are held to
TOP_FIT_M = 0.02            # a top's fitted body ends this over the hips when its hem is lower
TOP_FLARE = 0.04            # ... and hangs from there this much wider at its hem
GLOW = ("led", "visor")                        # slots the mid tier draws emissive

# what a garment is: its layer, the body parts its pattern covers, its default eases (m) and
# thickness
KINDS = {
    "tee":         {"layer": "base", "parts": ["torso", "neck", "uarm", "thigh"],
                    "ease": (0.012, 0.010), "sleeve": 0.36},
    "longtee":     {"layer": "base", "parts": ["torso", "neck", "uarm", "farm", "thigh"],
                    "ease": (0.012, 0.010), "sleeve": 0.95},
    "shirt":       {"layer": "base", "parts": ["torso", "neck", "uarm", "farm", "thigh"],
                    "ease": (0.013, 0.011), "sleeve": 0.95, "collar": "fold"},
    "hoodie":      {"layer": "base", "parts": ["torso", "neck", "uarm", "farm", "thigh"],
                    "ease": (0.022, 0.018), "sleeve": 0.96},
    "coveralls":   {"layer": "base", "parts": ["torso", "neck", "uarm", "farm", "thigh", "calf"],
                    "ease": (0.022, 0.018, 0.022), "sleeve": 0.95, "collar": "stand"},
    "bomber":      {"layer": "outer", "parts": ["torso", "neck", "uarm", "farm", "thigh"],
                    "ease": (0.032, 0.026), "sleeve": 0.96, "collar": "stand"},
    "jacket":      {"layer": "outer", "parts": ["torso", "neck", "uarm", "farm", "thigh"],
                    "ease": (0.028, 0.022), "sleeve": 0.95, "collar": "fold"},
    "trench":      {"layer": "outer", "parts": ["torso", "neck", "uarm", "farm", "thigh"],
                    "ease": (0.032, 0.026), "sleeve": 0.95, "collar": "fold"},
    "raincoat":    {"layer": "outer", "parts": ["torso", "neck", "uarm", "farm", "thigh"],
                    "ease": (0.036, 0.03), "sleeve": 0.97},
    "cargo":       {"layer": "bottom", "parts": ["torso", "thigh", "calf"],
                    "ease": (0.008, 0.0, 0.022)},
    "trousers":    {"layer": "bottom", "parts": ["torso", "thigh", "calf"],
                    "ease": (0.008, 0.0, 0.016)},
    "skirt":       {"layer": "bottom", "parts": ["torso", "thigh"], "ease": (0.008,)},
    "sneakers":    {"layer": "shoes", "top": 0.10, "ease": 0.008},
    "boots":       {"layer": "shoes", "top": 0.24, "ease": 0.009},
    "dress_shoes": {"layer": "shoes", "top": 0.085, "ease": 0.006},
}
ACCESSORIES = {
    "visor": ["visor", "led"], "respirator": ["plastic", "metal"], "mask": ["knit"],
    "headset": ["plastic", "led"], "cap": ["canvas", "canvas"], "beanie": ["knit"],
    "hardhat": ["plastic"], "implant": ["metal", "led"], "armplates": ["metal", "led"],
    "backpack": ["nylon", "plastic"], "bag": ["leather"],
}
HIDES_HAIR = ("cap", "beanie", "hardhat")

# per group: the choices (weight, base, outer or None, bottom, shoes), the textiles by kind,
# and its accessories (kind, probability); a look draws one of each
RECIPES = {
    "corporate": {
        "outfits": [(4, "shirt", "jacket", "trousers", "dress_shoes"),
                    (2, "shirt", None, "trousers", "dress_shoes"),
                    (2, "shirt", "jacket", "skirt", "dress_shoes"),
                    (2, "longtee", "trench", "trousers", "dress_shoes"),
                    (1, "tee", "jacket", "trousers", "sneakers")],
        "textiles": {"shirt": ["canvas"], "longtee": ["knit"], "tee": ["knit"],
                     "jacket": ["wool"], "trench": ["canvas", "wool"],
                     "trousers": ["wool"], "skirt": ["wool"]},
        "acc": [("headset", 0.15), ("visor", 0.08), ("implant", 0.2), ("bag", 0.2)],
        "tucked": 0.7},
    "street": {
        "outfits": [(3, "hoodie", None, "cargo", "sneakers"),
                    (3, "tee", "bomber", "trousers", "sneakers"),
                    (2, "tee", None, "cargo", "sneakers"),
                    (2, "longtee", None, "trousers", "boots"),
                    (1, "tee", None, "skirt", "sneakers"),
                    (1, "hoodie", None, "trousers", "boots")],
        "textiles": {"hoodie": ["knit"], "tee": ["knit"], "longtee": ["knit"],
                     "bomber": ["nylon", "leather"], "cargo": ["canvas", "denim"],
                     "trousers": ["denim"], "skirt": ["denim"]},
        "acc": [("cap", 0.2), ("beanie", 0.15), ("mask", 0.12), ("backpack", 0.25),
                ("implant", 0.15), ("armplates", 0.1)],
        "hood": 0.45},
    "market": {
        "outfits": [(3, "tee", None, "trousers", "sneakers"),
                    (2, "shirt", None, "trousers", "boots"),
                    (2, "longtee", None, "skirt", "sneakers"),
                    (2, "tee", "jacket", "cargo", "boots")],
        "textiles": {"tee": ["knit", "canvas"], "shirt": ["canvas"], "longtee": ["knit"],
                     "jacket": ["canvas", "denim"], "trousers": ["canvas", "denim"],
                     "skirt": ["canvas"], "cargo": ["canvas"]},
        "acc": [("bag", 0.3), ("beanie", 0.15), ("mask", 0.1), ("implant", 0.08)]},
    "industrial": {
        "outfits": [(4, "coveralls", None, None, "boots"),
                    (3, "tee", "jacket", "cargo", "boots"),
                    (2, "longtee", None, "cargo", "boots")],
        "textiles": {"coveralls": ["canvas", "nylon"], "tee": ["knit"], "longtee": ["knit"],
                     "jacket": ["nylon", "canvas"], "cargo": ["canvas"]},
        "acc": [("hardhat", 0.35), ("respirator", 0.3), ("headset", 0.1), ("armplates", 0.1)],
        "reflective": 0.8},
    "nightlife": {
        "outfits": [(3, "tee", "jacket", "trousers", "boots"),
                    (3, "tee", None, "skirt", "boots"),
                    (2, "shirt", None, "trousers", "boots"),
                    (2, "longtee", "bomber", "skirt", "boots")],
        "textiles": {"tee": ["mesh", "vinyl", "knit"], "shirt": ["vinyl"],
                     "longtee": ["mesh", "knit"], "jacket": ["leather", "vinyl"],
                     "bomber": ["vinyl", "nylon"], "trousers": ["vinyl", "leather"],
                     "skirt": ["vinyl", "leather"]},
        "acc": [("visor", 0.3), ("implant", 0.35), ("armplates", 0.15), ("headset", 0.1)],
        "led": 0.7},
    "techwear": {
        "outfits": [(3, "hoodie", "jacket", "cargo", "sneakers"),
                    (3, "longtee", "bomber", "cargo", "boots"),
                    (2, "hoodie", None, "cargo", "sneakers"),
                    (2, "tee", "trench", "trousers", "boots")],
        "textiles": {"hoodie": ["nylon", "knit"], "longtee": ["knit"], "tee": ["knit"],
                     "jacket": ["nylon"], "bomber": ["nylon"], "trench": ["nylon"],
                     "cargo": ["nylon"], "trousers": ["nylon"]},
        "acc": [("visor", 0.3), ("respirator", 0.25), ("backpack", 0.35), ("implant", 0.3),
                ("armplates", 0.15)],
        "hood": 0.5, "reflective": 0.5, "led": 0.4},
    "punk": {
        "outfits": [(4, "tee", "jacket", "trousers", "boots"),
                    (2, "tee", "jacket", "skirt", "boots"),
                    (2, "hoodie", None, "trousers", "boots")],
        "textiles": {"tee": ["knit", "mesh"], "hoodie": ["knit"], "jacket": ["leather", "denim"],
                     "trousers": ["denim", "leather"], "skirt": ["leather", "denim"]},
        "acc": [("implant", 0.4), ("mask", 0.2), ("armplates", 0.2), ("beanie", 0.15)],
        "hood": 0.3, "open": 0.8},
    "gang": {
        "outfits": [(3, "hoodie", None, "cargo", "sneakers"),
                    (3, "tee", "bomber", "cargo", "sneakers"),
                    (2, "longtee", "jacket", "trousers", "boots")],
        "textiles": {"hoodie": ["knit", "nylon"], "tee": ["knit"], "longtee": ["knit"],
                     "bomber": ["nylon", "leather"], "jacket": ["leather"],
                     "cargo": ["canvas", "nylon"], "trousers": ["denim"]},
        "acc": [("mask", 0.35), ("armplates", 0.25), ("implant", 0.3), ("cap", 0.15)],
        "hood": 0.6},
    "police": {
        "outfits": [(1, "shirt", "jacket", "trousers", "boots")],
        "textiles": {"shirt": ["canvas"], "jacket": ["nylon"], "trousers": ["wool"]},
        "acc": [("cap", 0.6), ("headset", 0.5)],
        "fixed": {"shirt": [0.08, 0.1, 0.16], "jacket": [0.035, 0.05, 0.1],
                  "trousers": [0.03, 0.04, 0.08], "cap": [0.03, 0.04, 0.08]},
        "reflective": 1.0, "tucked": 1.0},
    "rain": {
        "outfits": [(2, "longtee", "raincoat", "trousers", "boots"),
                    (1, "hoodie", "raincoat", "cargo", "boots")],
        "textiles": {"longtee": ["knit"], "hoodie": ["knit"], "raincoat": ["vinyl"],
                     "trousers": ["denim", "canvas"], "cargo": ["canvas"]},
        "acc": [("backpack", 0.2)]},
}
SHOE_COLORS = {"sneakers": ([0.92, 0.92, 0.9], [0.06, 0.06, 0.07], [0.5, 0.52, 0.55]),
               "boots": ([0.05, 0.045, 0.04], [0.22, 0.13, 0.07], [0.12, 0.12, 0.1]),
               "dress_shoes": ([0.03, 0.03, 0.03], [0.18, 0.09, 0.05])}


def _u(*parts) -> float:
    h = hashlib.blake2b(".".join(str(p) for p in parts).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big") / 2.0 ** 64


def _pick(items, *salt):
    return items[int(_u(*salt) * len(items))]


def _weighted(choices, *salt):
    tot = sum(c[0] for c in choices)
    x = _u(*salt) * tot
    for c in choices:
        if x < c[0]:
            return c
        x -= c[0]
    return choices[-1]


def look_groups(n: int) -> list[list[str]]:
    """Each of the `n` characters' looks' groups: every group's count of looks (`GROUP_LOOKS`,
    scaled to n x LOOKS) shared out, a character at most one look of a group, the characters
    with the fewest looks first (ties by hash)."""
    total = n * LOOKS
    base = sum(GROUP_LOOKS.values())
    want = {g: max(1, round(c * total / base)) for g, c in GROUP_LOOKS.items()}
    while sum(want.values()) > total:
        g = max(want, key=lambda k: (want[k], k))
        want[g] -= 1
    while sum(want.values()) < total:
        g = min(want, key=lambda k: (want[k], k))
        want[g] += 1
    out = [[] for _ in range(n)]
    for g in sorted(want, key=lambda k: (-want[k], k)):
        for _ in range(want[g]):
            free = [k for k in range(n) if g not in out[k] and len(out[k]) < LOOKS]
            if not free:
                break
            k = min(free, key=lambda k: (len(out[k]), _u("lg2.groups", g, k)))
            out[k].append(g)
    return out


def look(character: dict, k: int, group: str) -> dict:
    """The k-th look of a character (`library.character`): its garments (kind, textile, the
    pattern's draws) and accessories."""
    cid = character["id"]
    lid = f"{cid}_l{k}"
    R = RECIPES[group]
    s = ("lg2.look", cid, k)
    _, base, outer, bottom, shoes = _weighted(R["outfits"], *s, "outfit")
    if bottom == "skirt" and character.get("body") == "m" and group != "nightlife":
        bottom = "trousers"
    fixed = R.get("fixed", {})
    garments = []

    def g(kind, layer_channel):
        tex = _pick(R["textiles"].get(kind, ["knit"]), *s, "tex", kind)
        rec = {"kind": kind, "textile": tex, "channel": layer_channel}
        if kind in fixed:
            rec["channel"], rec["rgb"] = -1, fixed[kind]
        # the pattern's own draws (fit, length)
        rec["fit"] = round(_u(*s, "fit", kind), 3)
        rec["length"] = round(_u(*s, "len", kind), 3)
        if kind == "hoodie":
            rec["hood"] = "up" if _u(*s, "hood") < R.get("hood", 0.3) else "down"
        if kind in ("jacket", "bomber", "trench") and _u(*s, "open") < R.get("open", 0.5):
            rec["open"] = True
        if kind == "raincoat":
            rec["hood"] = "up"
        trims = []
        if kind in ("bomber", "jacket", "coveralls", "trench") and \
                _u(*s, "refl", kind) < R.get("reflective", 0.0):
            trims.append("reflective")
        if kind in ("bomber", "jacket", "tee", "hoodie", "trousers", "skirt", "longtee") and \
                _u(*s, "led", kind) < R.get("led", 0.0):
            trims.append("led")
        rec["trims"] = trims
        garments.append(rec)

    g(base, 0)
    if outer:
        g(outer, 1)
    if bottom:
        g(bottom, 2)
    sc = _pick(SHOE_COLORS[shoes], *s, "shoe")
    garments.append({"kind": shoes, "textile": "leather" if shoes != "sneakers" else "nylon",
                     "channel": -1, "rgb": sc, "fit": 0.5, "length": 0.5, "trims": []})
    acc = []
    has_long = any(x["kind"] in ("longtee", "shirt", "hoodie", "coveralls") for x in garments) \
        or outer is not None
    hood_up = any(x.get("hood") == "up" for x in garments)
    for kind, pr in R.get("acc", []):
        if _u(*s, "acc", kind) >= pr:
            continue
        if kind == "armplates" and has_long:
            continue
        if kind in HIDES_HAIR + ("headset",) and (hood_up or any(a["kind"] in HIDES_HAIR
                                                                for a in acc)):
            continue
        if kind == "mask" and any(a["kind"] == "respirator" for a in acc):
            continue
        a = {"kind": kind, "slots": list(ACCESSORIES[kind])}
        if kind in ("cap", "beanie"):
            a["channel"] = 1
        if kind in fixed:
            a["channel"], a["rgb"] = -1, fixed[kind]
        if kind in ("implant", "armplates"):
            a["side"] = "l" if _u(*s, "side", kind) < 0.5 else "r"
        if kind == "hardhat":
            a["rgb"] = _pick(([0.9, 0.7, 0.05], [0.9, 0.35, 0.05], [0.85, 0.85, 0.82]), *s, "hh")
        acc.append(a)
    tucked = base == "shirt" and bottom in ("trousers", "skirt") and \
        _u(*s, "tucked") < R.get("tucked", 0.2)
    return {"id": lid, "character": cid, "group": group, "garments": garments,
            "accessories": acc, "tucked": tucked,
            "hide_hair": hood_up or any(a["kind"] in HIDES_HAIR for a in acc)}


def looks_of(character: dict, groups: list[str]) -> list[dict]:
    return [look(character, k, g) for k, g in enumerate(groups)]


def garment_key(rec: dict) -> str:
    """A garment's id within a character: what it is (the same garment in two looks is draped
    once)."""
    h = hashlib.blake2b(json.dumps(rec, sort_keys=True).encode("utf-8"), digest_size=5)
    return f"{rec['kind']}_{h.hexdigest()}"


# ------------------------------------------------------------------------------------------
# the body's measurements and the drafts
# ------------------------------------------------------------------------------------------

def measure(body: dict) -> dict:
    """A body's landmarks (m over the floor, Blender's frame as the Blender stage takes it)
    from the exported bones (`people_library` step `bodies`)."""
    B = {b["name"]: (b["t"][0] / 100.0, -b["t"][1] / 100.0, b["t"][2] / 100.0)
         for b in body["body"]["bones"]}

    def z(*names):
        return sum(B[n][2] for n in names) / len(names)
    return {"ankle": z("foot_l", "foot_r"), "knee": z("calf_l", "calf_r"),
            "hip": z("thigh_l", "thigh_r"), "waist": z("spine_02"), "chest": z("spine_04"),
            "shoulder": z("upperarm_l", "upperarm_r"), "neck": z("neck_01"),
            "head": z("head"), "height": max(v[2] for v in B.values())}


def draft(rec: dict, m: dict, gid: str) -> dict:
    """A garment's draft for the Blender stage: its parts, eases (by its fit), cuts (by its
    length and the body's landmarks), flare, hood, collar, trims, textile, thickness."""
    kind = rec["kind"]
    K = KINDS[kind]
    fit = float(rec.get("fit", 0.5))
    ln = float(rec.get("length", 0.5))
    tx = TX.TEXTILES[rec["textile"]]
    d = {"id": gid, "kind": kind, "layer": K["layer"], "textile": rec["textile"],
         "channel": rec.get("channel", -1), "thick": tx["thick"] / 1000.0,
         "z": {"waist": m["waist"]}, "trims": []}
    if "rgb" in rec:
        d["rgb"] = rec["rgb"]
    if K["layer"] == "shoes":
        d["top_z"] = m["ankle"] + K["top"] - 0.07
        d["ease"] = {"leg": K["ease"], "torso": K["ease"]}
        d["trims"] = [{"where": "sole", "z": 0.022, "textile": "rubber",
                       "rgb": 0.95 if kind == "sneakers" else 0.15}]
        return d
    e = K["ease"]
    grow = 0.75 + 0.45 * fit                     # fitted to loose
    d["parts"] = list(K["parts"])
    d["ease"] = {"torso": round(e[0] * grow, 4)}
    if len(e) > 1 and e[1]:
        d["ease"]["arm"] = round(e[1] * grow, 4)
    if len(e) > 2:
        d["ease"]["leg"] = round(e[2] * grow, 4)
    cuts = []
    if K["layer"] in ("base", "outer"):
        if kind == "coveralls":
            cuts.append({"kind": "z", "z": round(m["ankle"] + 0.05, 4), "keep": "above"})
        else:
            # (a coat's fitted body ends at the hips, above the crotch, where its skirt flares
            # out: cut lower, the body's offset folded between the legs; the clothing fixes)
            hem = {"tee": m["hip"] - 0.05, "longtee": m["hip"] - 0.06, "shirt": m["hip"] - 0.07,
                   "hoodie": m["hip"] - 0.06, "bomber": m["waist"] - 0.07,
                   "jacket": m["hip"] - 0.08, "trench": m["hip"] + 0.04,
                   "raincoat": m["hip"] + 0.04}[kind] - 0.04 * ln
            # (a top whose hem is below the hips has its fitted body cut at the hips and hangs
            # straight from there (a flare of `TOP_FLARE`): its body offset round the crotch
            # folded at the hem; not a tucked shirt, which the trousers close over)
            low = hem < m["hip"] + TOP_FIT_M and kind not in ("trench", "raincoat") and \
                not rec.get("tucked")
            cut_z = m["hip"] + TOP_FIT_M if low else hem
            cuts.append({"kind": "z", "z": round(cut_z, 4), "keep": "above",
                         "parts": ["torso", "thigh"]})
            d["z"]["hem"] = round(hem, 4)
            if low:
                d["flare"] = {"from_z": round(cut_z, 4), "to_z": round(hem, 4),
                              "scale": TOP_FLARE}
        sleeve = K["sleeve"] - (0.06 * ln if K["sleeve"] < 0.5 else 0.0)
        cuts.append({"kind": "limb", "limb": "arm", "t": round(sleeve, 3)})
        cuts.append({"kind": "neck", "scale": 1.08 if K["layer"] == "outer" else 0.96})
        if rec.get("open"):
            cuts.append({"kind": "front", "width": 0.07 + 0.05 * fit,
                         "z_max": round(m["neck"] + 0.1, 4)})
            d["open"] = True
        elif K["layer"] == "outer" or kind in ("shirt", "coveralls"):
            # (a zip of metal, or a placket of the garment's own textile in its own color,
            # darker: LG2's undyed placket read as a white line; the clothing fixes)
            zip_ = kind in ("bomber", "raincoat", "coveralls")
            d["trims"].append({"where": "front", "width": 0.008 if zip_ else 0.012,
                               "textile": "metal" if zip_ else rec["textile"],
                               "rgb": 0.75 if zip_ else 0.72, "dyed": not zip_})
        if kind in ("trench", "raincoat"):
            d["flare"] = {"from_z": round(d["z"]["hem"], 4),
                          "to_z": round(m["knee"] - 0.05 - 0.12 * ln, 4),
                          "scale": round(0.15 + 0.1 * fit, 3)}
            d["loose"] = ["skirt"]
            d["bend"] = 2.0
            d["trims"].append({"where": "band_torso", "z": round(m["waist"], 4),
                               "width": 0.04, "textile": rec["textile"], "rgb": 0.7,
                               "dyed": True})
        if kind in ("hoodie", "bomber"):
            d["trims"].append({"where": "hem", "z": d["z"]["hem"], "width": 0.05,
                               "textile": "rib", "dyed": True})
            d["trims"].append({"where": "cuff", "t": round(sleeve, 3), "width": 0.05,
                               "textile": "rib", "dyed": True})
        if kind == "hoodie":
            d["hood"] = rec.get("hood", "down")
            d["trims"].append({"where": "pocket", "x0": -1.0, "x1": 0.09,
                               "z0": round(m["hip"] + 0.0, 4), "z1": round(m["hip"] + 0.14, 4),
                               "textile": rec["textile"], "rgb": 0.82, "dyed": True})
        if kind == "raincoat":
            d["hood"] = "up"
        if kind == "jacket":
            d["trims"].append({"where": "pocket", "x0": 0.05, "x1": 0.14,
                               "z0": round(m["chest"] + 0.0, 4), "z1": round(m["chest"] + 0.08, 4),
                               "textile": rec["textile"], "rgb": 0.8, "dyed": True})
        if kind == "coveralls":
            d["parts"] = list(K["parts"])
            d["trims"].append({"where": "band_torso", "z": round(m["waist"], 4),
                               "width": 0.045, "textile": rec["textile"], "rgb": 0.65,
                               "dyed": True})
        if "collar" in K and not (kind == "jacket" and rec.get("open") is False):
            d["collar"] = K["collar"]
        if kind == "shirt" and rec.get("tucked"):
            d["ease"]["low"] = 0.003
    else:                                        # bottoms
        top = m["waist"] + 0.015 + 0.02 * (1 - ln) if kind != "skirt" else m["waist"] + 0.02
        cuts.append({"kind": "z", "z": round(top, 4), "keep": "below",
                     "parts": ["torso", "thigh"]})
        d["trims"].append({"where": "band_torso", "z": round(top - 0.02, 4), "width": 0.035,
                           "textile": rec["textile"], "rgb": 0.75, "dyed": True})
        if kind == "skirt":
            # (from the hips, above the crotch: the clothing fixes)
            cuts.append({"kind": "z", "z": round(m["hip"] + TOP_FIT_M, 4), "keep": "above",
                         "parts": ["torso", "thigh"]})
            d["flare"] = {"from_z": round(m["hip"] + TOP_FIT_M, 4),
                          "to_z": round(m["knee"] + 0.08 - 0.25 * ln, 4),
                          "scale": round(0.12 + 0.3 * fit, 3)}
            d["loose"] = ["skirt"]
        else:
            cuts.append({"kind": "z", "z": round(m["ankle"] + 0.045 + 0.02 * (1 - ln), 4),
                         "keep": "above"})
        if kind == "cargo":
            d["trims"].append({"where": "side_pocket", "z0": round(m["knee"] + 0.07, 4),
                               "z1": round(m["knee"] + 0.22, 4), "x0": 0.13,
                               "textile": rec["textile"], "rgb": 0.8, "dyed": True})
    for t in rec.get("trims", []):
        if t == "reflective":
            d["trims"].insert(0, {"where": "band_arm", "t": 0.72, "width": 0.035,
                                  "textile": "reflective"})
            d["trims"].insert(0, {"where": "band_torso", "z": round(m["chest"] - 0.06, 4),
                                  "width": 0.035, "textile": "reflective"})
            if "calf" in d["parts"]:
                d["trims"].insert(0, {"where": "band_leg", "z": round(m["knee"] - 0.1, 4),
                                      "width": 0.035, "textile": "reflective"})
        elif t == "led":
            if K["layer"] == "bottom":
                d["trims"].insert(0, {"where": "band_torso", "z": round(m["hip"] - 0.02, 4),
                                      "width": 0.008, "textile": "led"})
            else:
                d["trims"].insert(0, {"where": "band_arm", "t": 0.55, "width": 0.008,
                                      "textile": "led"})
                d["trims"].insert(0, {"where": "band_torso", "z": round(m["chest"] - 0.1, 4),
                                      "width": 0.008, "textile": "led"})
    d["cuts"] = cuts
    return d


def blender_job(character: dict, looks: list[dict], body_path: str, out_dir: str,
                body: dict, render: bool = False, render_garments: bool = False) -> dict:
    """One character's Blender job: its garments (each once, drafted for its body), its
    accessories, its looks."""
    m = measure(body)
    garments, accs, out_looks = {}, {}, []
    for lk in looks:
        gids, aids = [], []
        for rec in lk["garments"]:
            r = dict(rec)
            if lk.get("tucked") and r["kind"] == "shirt":
                r["tucked"] = True
            gid = garment_key(r)
            if gid not in garments:
                garments[gid] = draft(r, m, gid)
            gids.append(gid)
        for a in lk["accessories"]:
            aid = "acc_" + hashlib.blake2b(json.dumps(a, sort_keys=True).encode("utf-8"),
                                           digest_size=4).hexdigest()
            if aid not in accs:
                accs[aid] = {**a, "id": aid}
            aids.append(aid)
        # (the renders' colors: three of its group's, as a person of it might wear)
        cols = P.GROUP_COLORS.get("street" if lk["group"] == "rain" else lk["group"],
                                  ("#808080",))
        dyes = []
        for k in range(3):
            h = cols[int(_u("lg2.dye", lk["id"], k) * len(cols))]
            dyes.append([round((int(h[1 + 2 * j:3 + 2 * j], 16) / 255.0) ** 2.2, 4)
                         for j in range(3)])
        out_looks.append({"id": lk["id"], "garments": gids, "accessories": aids,
                          "tucked": lk.get("tucked", False), "hide_hair": lk["hide_hair"],
                          "dyes": dyes})
    colors = {k: {"rgb": v["mean"], "rough": v["rough"],
                  "emit": 4.0 if v["kind"] == "emissive" else 0.0}
              for k, v in TX.record()["textiles"].items()}
    return {"character": character["id"], "body": body_path, "out": out_dir,
            "render": render, "render_garments": render_garments, "bones": list(BONES),
            "glow": list(GLOW), "colors": colors, "garments": list(garments.values()),
            "accessories": list(accs.values()), "looks": out_looks}


def spec(characters: list[dict]) -> dict:
    """The clothing part of the library's spec: every character's looks."""
    groups = look_groups(len(characters))
    return {"looks_per": LOOKS, "groups": list(GROUPS),
            "looks": [looks_of(c, groups[c["index"]]) for c in characters]}


def group_of_style(group: str) -> str:
    """A fashion group as the looks know it (`presets.GROUPS` and `rain`)."""
    return group if group in RECIPES else "street"


assert set(P.GROUPS) <= set(RECIPES), "every style group has looks"
