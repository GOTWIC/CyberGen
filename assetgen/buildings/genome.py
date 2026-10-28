"""The genome (scope 5.1.1): three layers of draws, all blake2b of (salt, id, purpose).

- **District palette**: the era's style (preset, with the asset spec's fields over it), the
  district's additions (systems, wear) and, for a landmark, its own palette. All of it is in
  the brief's `spec` section, so a genome depends on the brief alone.
- **Property family**: buildings of one complex (twin towers, clusters, campuses, megasite
  groups) draw their discrete genes and colors from the property id, so they share one
  language; their continuous genes step from the family's by a building draw. An owner in
  the spec biases systems (`facade_bias`) and colors (`brand_colors`).
- **Building**: discrete genes (facade system per mass group, window type, rhythm, corner,
  cornice, parapet, slab bands, ground band, crown, finish, colors) and continuous ones (bay
  width, window share of the bay, sill and head heights, reveal depth, corner pier, cornice,
  parapet and band sizes, wear, dirt height, neon, lit windows, color shifts), each quantized
  to its step (`systems.STEP`).

Mass groups: `base` (podiums, docks, halls), `body` (towers, tiers, slabs, single masses),
`top` (crowns, roof tiers); each draws its own system genes, so a podium can differ from
its tower. `effective` keeps the genes a building's masses actually use, the vector the
uniqueness check compares.
"""

from __future__ import annotations

import hashlib

from . import systems as SY

GENOME_VERSION = 1
SALT = "ag1.genome"
GROUPS = ("base", "body", "top")
GROUP_GENES = ("system", "window", "rhythm", "cornice", "parapet", "bands", "bay_m", "wwr",
               "sill_m", "head_m", "reveal_m", "corner_m", "cornice_m", "parapet_m",
               "band_m")
BUILDING_GENES = ("ground", "crown", "corner", "finish", "wall", "trim", "glass", "roof",
                  "mech_every")
CONTINUOUS = ("bay_m", "wwr", "sill_m", "head_m", "reveal_m", "corner_m", "cornice_m",
              "parapet_m", "band_m", "open_p", "patch_w", "patch_h", "wear", "dirt_m",
              "wall_v", "wall_w", "trim_v")
# what one unit of genome distance is for a continuous gene (a clearly visible change)
SCALE = {"bay_m": 0.3, "wwr": 0.08, "sill_m": 0.15, "head_m": 0.15, "reveal_m": 0.05,
         "corner_m": 0.25, "cornice_m": 0.15, "parapet_m": 0.2, "band_m": 0.05,
         "open_p": 0.12, "patch_w": 0.35, "patch_h": 0.3,
         "wear": 0.25, "dirt_m": 2.0, "wall_v": 0.06, "wall_w": 0.04, "trim_v": 0.06}
LIT_BY_USE = {"residential": 0.35, "hotel": 0.45, "office": 0.6, "retail": 0.5,
              "civic": 0.4, "industrial": 0.15, "parking": 0.05}


def u(key: str, purpose: str, salt: str = SALT) -> float:
    """A uniform draw in [0, 1) from (salt, key, purpose)."""
    h = hashlib.blake2b(f"{salt}|{key}|{purpose}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little") / 2.0 ** 64


def pick(key: str, purpose: str, options, weights=None, salt: str = SALT):
    options = list(options)
    if weights is None:
        return options[min(int(u(key, purpose, salt) * len(options)), len(options) - 1)]
    total = 0.0
    for w in weights:
        total += w
    x = u(key, purpose, salt) * total
    acc = 0.0
    for o, w in zip(options, weights):
        acc += w
        if x < acc:
            return o
    return options[-1]


def quant(v: float, step: float) -> float:
    q = round(round(v / step) * step, 6)
    return 0.0 if q == 0.0 else q


def draw(key: str, purpose: str, lo: float, hi: float, step: float, salt: str = SALT) -> float:
    return quant(lo + (hi - lo) * u(key, purpose, salt), step)


def system_weights(spec: dict, btype: str, floors: int) -> dict[str, float]:
    """The AG1 systems a building draws from, with weights: era, district additions and
    owner bias, each mapped onto the six AG1 systems."""
    w: dict[str, float] = {}

    def add(src: dict | None, scale: float = 1.0):
        for name in sorted(src or {}):
            s = SY.ag1_system(name)
            w[s] = w.get(s, 0.0) + scale * float(src[name])
    add((spec.get("era_style") or {}).get("systems"))
    add((spec.get("district") or {}).get("systems"))
    add((spec.get("owner") or {}).get("facade_bias"))
    if btype in SY.NO_CURTAIN:
        w.pop("unitized_curtain_wall", None)
    if btype != "building.shanty_stack" and floors > SY.SHANTY_MAX_FLOORS \
            and "shanty_patchwork" in w:
        w["precast_panel"] = w.get("precast_panel", 0.0) + w.pop("shanty_patchwork")
    if not any(v > 0 for v in w.values()):
        w = {"punched_concrete": 1.0}
    return {k: w[k] for k in SY.AG1_SYSTEMS if w.get(k, 0.0) > 0}


def _jitter(c: str, v: float, warm: float) -> str:
    """A palette color made lighter or darker by v and warmer (+) or cooler (-)."""
    r, g, b = (int(c[1 + 2 * k:3 + 2 * k], 16) for k in range(3))
    f = 1.0 + v
    r = r * f + 255.0 * warm
    g = g * f
    b = b * f - 255.0 * warm
    return "#" + "".join(f"{min(max(int(round(x)), 0), 255):02x}" for x in (r, g, b))


def make(brief: dict) -> dict:
    """The genome of one building, from its brief."""
    bid = brief["id"]
    b = brief["building"]
    spec = brief["spec"]
    ov = brief.get("override") or {}
    salt = SALT if "regenerate" not in ov else f"{SALT}.r{int(ov['regenerate'])}"
    era_style = spec.get("era_style") or {}
    prop = brief.get("property") or {}
    fam = prop.get("id") if prop and prop.get("complex") not in (None, "single") and \
        len(prop.get("building_ids") or []) > 1 else None
    fkey = fam or bid             # discrete genes and colors: the family's
    btype = b["type"]
    weights = system_weights(spec, btype, int(b["floors"]))
    names, ws = list(weights), [weights[k] for k in weights]
    fixed = SY.TYPE_SYSTEM.get(btype)
    genes: dict = {}
    cont: dict = {}
    body = fixed or pick(fkey, "system.body", names, ws, salt)
    sysg = {"body": body}
    sysg["base"] = fixed or (body if u(fkey, "system.base.same", salt) < 0.55 else
                             pick(fkey, "system.base", names, ws, salt))
    sysg["top"] = fixed or (body if u(fkey, "system.top.same", salt) < 0.7 else
                            pick(fkey, "system.top", names, ws, salt))
    bay = era_style.get("bay_m") or [2.4, 3.6]
    for g in GROUPS:
        s = sysg[g]
        T = SY.SYSTEMS[s]
        genes[f"{g}.system"] = s
        genes[f"{g}.window"] = pick(fkey, f"{g}.window", T["windows"], None, salt)
        genes[f"{g}.rhythm"] = pick(fkey, f"{g}.rhythm", T["rhythms"], None, salt)
        genes[f"{g}.cornice"] = pick(fkey, f"{g}.cornice", T["cornices"], None, salt)
        genes[f"{g}.parapet"] = pick(fkey, f"{g}.parapet", T["parapets"], None, salt)
        genes[f"{g}.bands"] = pick(fkey, f"{g}.bands", T["bands"], None, salt)
        sc = T["bay_scale"]
        lo, hi = bay[0] * sc[0], bay[1] * sc[1]
        if s == "corrugated":
            lo, hi = max(lo, 4.0), max(hi, 6.0)
        if s == "shanty_patchwork":
            lo, hi = 1.4, 2.6
        for gene, rng, step in (("bay_m", (lo, hi), SY.STEP["bay_m"]),
                                ("wwr", T["wwr"], SY.STEP["wwr"]),
                                ("sill_m", T["sill"], SY.STEP["sill_m"]),
                                ("head_m", T["head_gap"], SY.STEP["head_m"]),
                                ("reveal_m", T["reveal"], SY.STEP["reveal_m"]),
                                ("corner_m", T["corner"], SY.STEP["corner_m"]),
                                ("cornice_m", (0.25, 0.6), SY.STEP["cornice_m"]),
                                ("parapet_m", (0.5, 1.2), SY.STEP["parapet_m"]),
                                ("band_m", (0.06, 0.14), SY.STEP["band_m"])):
            base = draw(fkey, f"{g}.{gene}", rng[0], rng[1], step, salt)
            if fam:
                # a family member steps one or two quantization steps off the family's value
                k = pick(bid, f"{g}.{gene}.step", (-2, -1, 0, 1, 2), None, salt)
                base = quant(min(max(base + k * step, rng[0]), rng[1]), step)
            cont[f"{g}.{gene}"] = base
        if s == "shanty_patchwork":
            genes[f"{g}.patch"] = pick(fkey, f"{g}.patch", sorted(SY.PATCH_MIXES), None, salt)
            for gene, rng in (("open_p", (0.3, 0.75)), ("patch_w", (1.2, 2.6)),
                              ("patch_h", (1.0, 2.2))):
                cont[f"{g}.{gene}"] = draw(fkey, f"{g}.{gene}", rng[0], rng[1],
                                           SY.STEP[gene], salt)
    T = SY.SYSTEMS[body]
    genes["ground"] = pick(fkey, "ground", T["ground"], None, salt)
    genes["crown"] = pick(fkey, "crown", era_style.get("crowns") or ["flat"], None, salt)
    genes["corner"] = pick(fkey, "corner", SY.CORNERS, None, salt)
    genes["finish"] = pick(fkey, "finish", T.get("finishes") or (T["wall"],), None, salt)
    genes["mech_every"] = pick(fkey, "mech_every", (15, 18, 20, 22, 25), None, salt)
    # colors: the era's palette (a landmark's own), an owner's brand colors over it
    pal = list((spec.get("landmark") or {}).get("palette") or era_style.get("palette") or
               ["#8c8a86"])
    brand = list((spec.get("owner") or {}).get("brand_colors") or [])
    wi = pick(fkey, "wall", range(len(pal)), None, salt)
    wall = pal[wi]
    if brand and u(fkey, "wall.brand", salt) < 0.5:
        wall = pick(fkey, "wall.brand.pick", brand[:2], None, salt)
    trims = [c for j, c in enumerate(pal) if j != wi] or pal
    trim = pick(fkey, "trim", trims, None, salt)
    if brand and u(fkey, "trim.brand", salt) < 0.7:
        trim = pick(fkey, "trim.brand.pick", brand, None, salt)
    dark = min(pal, key=lambda c: (sum(int(c[1 + 2 * k:3 + 2 * k], 16) for k in range(3)), c))
    genes["wall"] = wall
    genes["trim"] = trim
    genes["glass"] = pick(fkey, "glass", SY.GLASS, None, salt)
    genes["roof"] = pick(fkey, "roof", SY.ROOFS, None, salt)
    dist = spec.get("district") or {}
    wear0 = float(era_style.get("wear", 0.4)) * float(dist.get("wear", 1.0))
    grime = float((b.get("style") or {}).get("grime", 0.4))
    cont["wear"] = draw(bid, "wear", 0.6 * wear0 + 0.3 * grime, 0.9 * wear0 + 0.5 * grime + 0.05,
                        SY.STEP["wear"], salt)
    cont["dirt_m"] = draw(bid, "dirt_m", 1.5, 3.0 + 6.0 * min(cont["wear"], 1.0),
                          SY.STEP["dirt_m"], salt)
    cont["wall_v"] = draw(bid, "wall_v", -0.12, 0.12, SY.STEP["wall_v"], salt)
    cont["wall_w"] = draw(bid, "wall_w", -0.06, 0.06, SY.STEP["wall_w"], salt)
    cont["trim_v"] = draw(bid, "trim_v", -0.1, 0.1, SY.STEP["trim_v"], salt)
    neon = float((b.get("style") or {}).get("neon", 0.3))
    extra = {"neon": quant(neon, SY.STEP["neon"]),
             "lit": draw(bid, "lit", 0.7, 1.3, 0.01, salt) * LIT_BY_USE.get(b["use"], 0.4),
             "seed": quant(u(bid, "seed", salt), SY.STEP["seed"])}
    extra["lit"] = quant(min(extra["lit"], 1.0), SY.STEP["lit"])
    for name, val in sorted((ov.get("style") or {}).items()):
        if name in genes:
            genes[name] = val
        elif name in cont:
            cont[name] = float(val)
    colors = {
        "wall": _jitter(genes["wall"], cont["wall_v"], cont["wall_w"]),
        "trim": _jitter(genes["trim"], cont["trim_v"], 0.0),
        "glass": genes["glass"], "roof": genes["roof"],
        "spandrel": _jitter(dark, cont["wall_v"] * 0.5, 0.0),
        "patch": _jitter("#9a958c", cont["wall_v"], cont["wall_w"]),
    }
    return {"v": GENOME_VERSION, "family": fam, "era": spec.get("era"), "genes": genes,
            "cont": cont, "extra": extra, "colors": colors}


def groups_of(brief: dict) -> list[str]:
    """The mass groups a building has (base, body, top), in that order."""
    have = {SY.role_group(m["role"]) for m in brief["masses"]}
    return [g for g in GROUPS if g in have]


def effective(genome: dict, used: dict) -> dict:
    """The genes a building's shell used (the generator's report `used`: groups present,
    and which features it built), as {gene: value}; the vector of the uniqueness check."""
    genes, cont = genome["genes"], genome["cont"]
    out: dict = {}
    for g in used.get("groups", []):
        s = genes[f"{g}.system"]
        out[f"{g}.system"] = s
        for gene in ("window", "rhythm"):
            out[f"{g}.{gene}"] = genes[f"{g}.{gene}"]
        for gene in ("bay_m", "wwr", "sill_m", "head_m", "reveal_m", "corner_m"):
            out[f"{g}.{gene}"] = cont[f"{g}.{gene}"]
        if s == "shanty_patchwork":
            out[f"{g}.patch"] = genes[f"{g}.patch"]
            for gene in ("open_p", "patch_w", "patch_h"):
                out[f"{g}.{gene}"] = cont[f"{g}.{gene}"]
        for feat, size in (("cornice", "cornice_m"), ("parapet", "parapet_m"),
                           ("bands", "band_m")):
            v = genes[f"{g}.{feat}"]
            out[f"{g}.{feat}"] = v
            if v != "none" and feat in used.get("features", {}).get(g, ()):
                out[f"{g}.{size}"] = cont[f"{g}.{size}"]
    for gene in ("corner", "wall", "roof"):
        out[gene] = genes[gene]
    if used.get("trim"):
        out["trim"] = genes["trim"]
        out["trim_v"] = cont["trim_v"]
    if used.get("glass"):
        out["glass"] = genes["glass"]
    if used.get("ground"):
        out["ground"] = genes["ground"]
    if used.get("finish"):
        out["finish"] = genes["finish"]
    for gene in ("wear", "dirt_m", "wall_v", "wall_w"):
        out[gene] = cont[gene]
    return out
