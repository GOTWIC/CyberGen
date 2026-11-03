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

AG2 adds per group the window frame style, sills and lintels, balconies (style, pattern,
depth) and the system's feature genes (fin angle and depth, sunshades, diagrid and
exoskeleton modules, egg crates, timber patterns, screen blades, capsule pods), and per
building the massing articulation (corner cut and size, setback ledge, podium canopy,
arcade under a cantilevered first floor) and an irregularity rate that scales what grime
and low wealth add (boarded and blocked windows, AC units, grilles, replaced frames,
closed-in balconies, dishes).

AG3 adds per building its street front (`front_*`, by the era's weights,
`systems.FRONT`): the shopfront frame (aluminum, painted, steel, timber), the riser, the
main door's leaves and recess, the steps up to it, the fascia over the shopfronts and how
often its shops have roll-up shutters; each unit then draws its own paint, glazing and door
side from its index (`fronts.py`).
"""

from __future__ import annotations

import hashlib

from citygen import dmath as DM

from . import systems as SY

GENOME_VERSION = 6
SALT = "ag1.genome"
GROUPS = ("base", "body", "top")
GROUP_GENES = ("system", "window", "rhythm", "cornice", "parapet", "bands", "bay_m", "wwr",
               "sill_m", "head_m", "reveal_m", "corner_m", "cornice_m", "parapet_m",
               "band_m", "frame", "sills", "balcony", "balcony_pat", "balcony_m", "fin_m",
               "member_m", "pod_m")
BUILDING_GENES = ("ground", "crown", "corner", "finish", "base", "wall", "trim", "glass",
                  "roof", "mech_every", "cut", "cut_m", "setback", "setback_at",
                  "setback_m", "canopy", "canopy_m", "arcade", "arcade_m", "irreg",
                  "front_frame", "front_riser", "front_door", "front_steps", "front_fascia",
                  "front_paint", "roof_form", "roof_finish", "coping")
CONTINUOUS = ("bay_m", "wwr", "sill_m", "head_m", "reveal_m", "corner_m", "cornice_m",
              "parapet_m", "band_m", "open_p", "patch_w", "patch_h", "wear", "dirt_m",
              "wall_v", "wall_w", "trim_v", "roof_v", "balcony_m", "fin_m", "member_m",
              "pod_m", "cut_m", "setback_at", "setback_m", "canopy_m", "arcade_m", "irreg",
              "front_recess_m", "front_shutter", "roof_pitch", "roof_mansard", "roof_eave_m")
# what one unit of genome distance is for a continuous gene (a clearly visible change)
SCALE = {"bay_m": 0.3, "wwr": 0.08, "sill_m": 0.15, "head_m": 0.15, "reveal_m": 0.05,
         "corner_m": 0.25, "cornice_m": 0.15, "parapet_m": 0.2, "band_m": 0.05,
         "open_p": 0.12, "patch_w": 0.35, "patch_h": 0.3,
         "wear": 0.25, "dirt_m": 2.0, "wall_v": 0.06, "wall_w": 0.04, "trim_v": 0.06,
         "roof_v": 0.06, "balcony_m": 0.25, "fin_m": 0.12, "member_m": 0.12, "pod_m": 0.1,
         "cut_m": 0.6, "setback_at": 0.1, "setback_m": 0.8, "canopy_m": 0.3,
         "arcade_m": 0.5, "irreg": 0.3, "front_recess_m": 0.2, "front_shutter": 0.3,
         "roof_pitch": 5.0, "roof_mansard": 4.0, "roof_eave_m": 0.1}
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


def reach_of(brief: dict) -> float:
    """AG15: how far a building's genome reaches past its era's systems and the grid (scope
    14.16: furthest in the corporate core and midtown), by its district's archetype."""
    arch = (brief.get("district") or {}).get("archetype") or ""
    return float(SY.REACH.get(arch, SY.REACH_DEFAULT))


def system_weights(spec: dict, btype: str, floors: int, reach: float = 0.0) -> dict[str, float]:
    """The systems a building draws from, with weights: era, district additions and owner
    bias; curtain systems not on low types (`NO_CURTAIN`), and a system outside its floor
    range (`systems.FLOORS`) gives its weight to its stand-in. AG15: AG15's systems with
    `reach` times 0.8 of the era's weight between them."""
    w: dict[str, float] = {}

    def add(src: dict | None, scale: float = 1.0):
        for name in sorted(src or {}):
            s = SY.system(name)
            w[s] = w.get(s, 0.0) + scale * float(src[name])
    add((spec.get("era_style") or {}).get("systems"))
    add((spec.get("district") or {}).get("systems"))
    add((spec.get("owner") or {}).get("facade_bias"))
    if reach > 0 and w:
        tot = 0.0
        for k in sorted(w):
            tot += w[k]
        add({s: 1.0 for s in SY.AG15_SYSTEMS}, round(0.8 * reach * tot /
                                                       len(SY.AG15_SYSTEMS), 6))
    for name in sorted(SY.FLOORS):
        lo, hi, alt = SY.FLOORS[name]
        if name == "shanty_patchwork" and btype == "building.shanty_stack":
            continue
        if name in w and not lo <= floors <= hi:
            w[alt] = w.get(alt, 0.0) + w.pop(name)
    if btype in SY.NO_CURTAIN:
        for name in SY.CURTAIN:
            if name in w:
                v = w.pop(name)
                w["precast_panel"] = w.get("precast_panel", 0.0) + 0.5 * v
    if not any(v > 0 for v in w.values()):
        w = {"punched_concrete": 1.0}
    return {k: w[k] for k in SY.ALL_SYSTEMS if w.get(k, 0.0) > 0}


def _jitter(c: str, v: float, warm: float) -> str:
    """A palette color made lighter or darker by v and warmer (+) or cooler (-)."""
    r, g, b = (int(c[1 + 2 * k:3 + 2 * k], 16) for k in range(3))
    f = 1.0 + v
    r = r * f + 255.0 * warm
    g = g * f
    b = b * f - 255.0 * warm
    return "#" + "".join(f"{min(max(int(round(x)), 0), 255):02x}" for x in (r, g, b))


def _order(key: str, purpose: str, options, weights=None, salt: str = SALT) -> list:
    """AG15: options in a weighted random order (keys u^(1/w), largest first), every one
    once: the alternatives the neighbor rule walks."""
    options = list(options)
    ws = list(weights) if weights is not None else [1.0] * len(options)
    keyed = []
    for o, w in zip(options, ws):
        if w <= 0:
            continue
        x = max(u(key, f"{purpose}.{o}", salt), 1e-12)
        keyed.append((-float(DM.exp(DM.log(x) / w)), str(o), o))
    keyed.sort()
    return [o for _, _, o in keyed]


def _first(first, alts: list, bad) -> object:
    """`first` unless `bad(first)`, else the first of `alts` that is not, else `first`."""
    if not bad(first):
        return first
    for a in alts:
        if not bad(a):
            return a
    return first


def tower_pool(btype: str, floors: int) -> list[str]:
    """AG15: the systems a tower may take when its era's are all taken by its neighbors:
    glazed first, then AG15's and the panel walls (none outside its floor range)."""
    pool = []
    for s in SY.CURTAIN + SY.AG15_SYSTEMS + ("precast_panel", "punched_concrete",
                                             "board_marked_concrete", "capsule_stack",
                                             "standing_seam", "punched_brick"):
        if s in pool:
            continue
        lo, hi, _ = SY.FLOORS.get(s, (0, 9999, None))
        if lo <= floors <= hi and not (btype in SY.NO_CURTAIN and s in SY.CURTAIN):
            pool.append(s)
    return pool


def make(brief: dict, avoid: dict | None = None) -> dict:
    """The genome of one building, from its brief. AG15: `avoid` (the neighbor rule,
    `neighbors.assign`): the body systems, (window, pattern) pairs, (wall, glass) palettes
    and (light, accent) night looks its neighboring towers took; each is drawn again past
    them where it can be."""
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
    twins = bool(fam) and prop.get("complex") in SY.TWINS
    btype = b["type"]
    reach = reach_of(brief)
    av = avoid or {}
    weights = system_weights(spec, btype, int(b["floors"]), reach)
    names, ws = list(weights), [weights[k] for k in weights]
    fixed = SY.TYPE_SYSTEM.get(btype)
    if btype.startswith("building.landmark."):
        # AG5: a hero's system by its kind
        fixed = SY.LANDMARK_SYSTEM.get(btype.rsplit(".", 1)[1], fixed)
    if isinstance(fixed, dict):
        fixed = pick(fkey, "system.type", sorted(fixed), [fixed[k] for k in sorted(fixed)],
                     salt)
    genes: dict = {}
    cont: dict = {}
    body = fixed or pick(fkey, "system.body", names, ws, salt)
    if av.get("system") and not fixed:
        # AG15: past the systems the neighbors took, the era's first, then the tower pool
        alts = _order(fkey, "ag15.system", names, ws, salt)
        alts += [s for s in _order(fkey, "ag15.pool", tower_pool(btype, int(b["floors"])),
                                   None, salt) if s not in alts]
        def taken(s_):
            # (a system is taken where a neighbor has it, or where every window and pattern
            # it can draw is: a ribbon has one)
            if s_ in av["system"]:
                return True
            pv = av.get("pattern") or ()
            return bool(pv) and all(
                ((w_, "grid") if w_ in SY.PATTERN_FIXED or s_ == "shanty_patchwork"
                 else (w_, p_)) in pv for w_ in SY.SYSTEMS[s_]["windows"]
                for p_ in SY.PATTERNS)
        body = _first(body, alts, taken)
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
        # AG15: the window pattern over the bays, further past the grid the further the
        # district reaches (none on a window type that fills its bays or runs as a band)
        pw = [1.0 + 3.0 * (1.0 - reach)] + [reach] * (len(SY.PATTERNS) - 1)
        genes[f"{g}.wpattern"] = "grid" if genes[f"{g}.window"] in SY.PATTERN_FIXED or \
            s == "shanty_patchwork" else pick(fkey, f"{g}.wpattern", SY.PATTERNS, pw, salt)
        if g == "body" and av.get("pattern"):
            def _sig(w_, p_):
                return (w_, "grid" if w_ in SY.PATTERN_FIXED or s == "shanty_patchwork"
                        else p_)
            pairs = [(w_, p_) for w_ in _order(fkey, "ag15.window", T["windows"], None, salt)
                     for p_ in _order(fkey, "ag15.wpattern", SY.PATTERNS, pw, salt)]
            w0, p0 = _first((genes["body.window"], genes["body.wpattern"]), pairs,
                            lambda wp: _sig(*wp) in av["pattern"])
            genes["body.window"], genes["body.wpattern"] = _sig(w0, p0)
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
        wwr = T["wwr"]
        ew = era_style.get("window_to_wall")
        if ew and s != "unitized_curtain_wall" and max(wwr[0], ew[0]) <= min(wwr[1], ew[1]):
            wwr = (max(wwr[0], ew[0]), min(wwr[1], ew[1]))      # the era's share, if it fits
        for gene, rng, step in (("bay_m", (lo, hi), SY.STEP["bay_m"]),
                                ("wwr", wwr, SY.STEP["wwr"]),
                                ("sill_m", T["sill"], SY.STEP["sill_m"]),
                                ("head_m", T["head_gap"], SY.STEP["head_m"]),
                                ("reveal_m", T["reveal"], SY.STEP["reveal_m"]),
                                ("corner_m", T["corner"], SY.STEP["corner_m"]),
                                ("cornice_m", (0.25, 0.6), SY.STEP["cornice_m"]),
                                ("parapet_m", (0.5, 1.2), SY.STEP["parapet_m"]),
                                ("band_m", (0.06, 0.14), SY.STEP["band_m"])):
            base = draw(fkey, f"{g}.{gene}", rng[0], rng[1], step, salt)
            if fam and twins:
                pass                # (AG5: twin towers are one design to the last step)
            elif fam:
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
        # AG2: window frames, sills, balconies, the system's feature genes
        genes[f"{g}.frame"] = pick(fkey, f"{g}.frame", T["frames"], None, salt)
        genes[f"{g}.sills"] = pick(fkey, f"{g}.sills", T["sills"], None, salt)
        balc = T["balconies"]
        if b["use"] not in SY.BALCONY_USES or len(balc) == 1:
            genes[f"{g}.balcony"] = "none"
        else:
            genes[f"{g}.balcony"] = pick(fkey, f"{g}.balcony", balc,
                                         [1.2] + [1.0] * (len(balc) - 1), salt)
        genes[f"{g}.balcony_pat"] = pick(fkey, f"{g}.balcony_pat",
                                         ("every", "alternate", "columns", "ends"), None, salt)
        for name, opts in sorted(SY.FEATURE_GENES.get(T.get("feature"), {}).items()):
            genes[f"{g}.{name}"] = pick(fkey, f"{g}.{name}", opts, None, salt)
        for gene, rng, step in (("balcony_m", (0.9, 1.5), 0.05), ("fin_m", (0.25, 0.55), 0.05),
                                ("member_m", (0.3, 0.6), 0.05), ("pod_m", (0.3, 0.55), 0.05)):
            cont[f"{g}.{gene}"] = draw(fkey, f"{g}.{gene}", rng[0], rng[1], step, salt)
    T = SY.SYSTEMS[body]
    genes["ground"] = pick(fkey, "ground", T["ground"], None, salt)
    genes["crown"] = pick(fkey, "crown", era_style.get("crowns") or ["flat"], None, salt)
    genes["corner"] = pick(fkey, "corner", SY.CORNERS, None, salt)
    genes["finish"] = pick(fkey, "finish", T.get("finishes") or (T["wall"],), None, salt)
    genes["mech_every"] = pick(fkey, "mech_every", (15, 18, 20, 22, 25), None, salt)
    genes["base"] = pick(fkey, "base", ("wall", "structure", "trim"), None, salt)
    # AG2: an industrial wall's base band (a block or concrete dado under the cladding)
    genes["dado"] = pick(fkey, "dado", ("none", "dado", "structure"), (0.15, 0.5, 0.35), salt)
    cont["dado_m"] = draw(fkey, "dado_m", 1.2, 3.6, 0.3, salt)
    # AG2: massing articulation (scope pipeline stage 3) by the era's weights
    art = SY.ARTICULATION.get(spec.get("era") or "", SY.ARTICULATION_DEFAULT)
    genes["cut"] = pick(fkey, "cut", ("none", "chamfer", "round"), art["cut"], salt)
    genes["setback"] = "ledge" if u(fkey, "setback", salt) < art["setback"] else "none"
    genes["canopy"] = "podium" if u(fkey, "canopy", salt) < art["canopy"] else "none"
    genes["arcade"] = "arcade" if u(fkey, "arcade", salt) < art["arcade"] else "none"
    for gene, rng, step in (("cut_m", (0.8, 3.0), 0.1), ("setback_at", (0.55, 0.8), 0.05),
                            ("setback_m", (1.5, 4.0), 0.1), ("canopy_m", (1.0, 1.5), 0.1),
                            ("arcade_m", (1.5, 3.0), 0.1)):
        cont[gene] = draw(fkey, gene, rng[0], rng[1], step, salt)
    # AG3: the street front by the era's weights
    fr = SY.FRONT.get(spec.get("era") or "", SY.FRONT_DEFAULT)
    genes["front_frame"] = pick(fkey, "front.frame", SY.FRAMES_FRONT, fr["frame"], salt)
    genes["front_riser"] = pick(fkey, "front.riser", SY.RISERS, fr["riser"], salt)
    genes["front_door"] = pick(fkey, "front.door", ("glass", "panel"), (0.65, 0.35), salt)
    genes["front_steps"] = pick(fkey, "front.steps", (0, 1, 2), fr["steps"], salt)
    genes["front_fascia"] = pick(fkey, "front.fascia", ("plate", "none"), (0.75, 0.25), salt)
    genes["front_paint"] = pick(fkey, "front.paint", fr["paints"], None, salt)
    cont["front_recess_m"] = draw(fkey, "front.recess_m", 0.45, 0.9, 0.05, salt)
    # AG4: roofs (a shed's form, a flat roof's finish, copings, pitch and eaves), drawn
    # under purposes of their own
    era = spec.get("era") or ""
    sf = SY.SHED_FORMS.get(btype)
    genes["roof_form"] = pick(fkey, "roof.form", sf[0], sf[1], salt) if sf else "flat"
    genes["roof_finish"] = pick(fkey, "roof.finish", SY.ROOF_FINISH_NAMES,
                                SY.ROOF_FINISHES.get(era, SY.ROOF_FINISHES["mixed_modern"]),
                                salt)
    genes["coping"] = pick(fkey, "roof.coping", ("metal", "none"), (0.8, 0.2), salt)
    pr = SY.SHED_PITCH if sf else SY.PITCH.get(era, SY.PITCH["*"])
    cont["roof_pitch"] = draw(fkey, "roof.pitch", pr[0], pr[1], 1.0, salt)
    cont["roof_mansard"] = draw(fkey, "roof.mansard", 62.0, 72.0, 1.0, salt)
    ev = SY.EAVE.get(era, SY.EAVE["*"])
    cont["roof_eave_m"] = draw(fkey, "roof.eave", ev[0], ev[1], 0.05, salt)
    cont["front_shutter"] = quant(min(fr["shutter"] * (0.5 + u(fkey, "front.shutter", salt)),
                                      1.0), 0.05)
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
    lpal = list((spec.get("landmark") or {}).get("palette") or [])
    if lpal and b.get("landmark"):
        # AG5: a hero in its own palette: the darkest its walls and glass, the lightest its
        # trim (the most saturated is its accent, `heroes.accent`)
        def lum(c):
            return sum(int(c[1 + 2 * k:3 + 2 * k], 16) for k in range(3))
        wall = min(lpal, key=lambda c: (lum(c), c))
        trim = max(lpal, key=lambda c: (lum(c), c))
        dark = wall
    genes["wall"] = wall
    genes["trim"] = trim
    genes["glass"] = pick(fkey, "glass", SY.GLASS, None, salt)
    if u(fkey, "ag15.glass.colored", salt) < 0.6 * reach:
        # AG15: colored glass, the further the district reaches the likelier
        genes["glass"] = pick(fkey, "ag15.glass", SY.GLASS_COLORED, None, salt)
    if lpal and b.get("landmark"):
        genes["glass"] = wall
    elif av.get("palette"):
        # AG15: a palette (wall, glass) no neighboring tower has: another glass first, then
        # another wall of the era's palette
        glasses = _order(fkey, "ag15.glass.alt", SY.GLASS + SY.GLASS_COLORED, None, salt)
        walls = [genes["wall"]] + [c for c in _order(fkey, "ag15.wall.alt", sorted(set(pal)),
                                                       None, salt) if c != genes["wall"]]
        wg = _first((genes["wall"], genes["glass"]),
                    [(w_, g_) for w_ in walls for g_ in glasses],
                    lambda x: x in av["palette"])
        if wg[0] != genes["wall"]:
            wall = wg[0]
            genes["wall"] = wall
            if genes["trim"] == wall:
                genes["trim"] = next((c for c in pal if c != wall), genes["trim"])
        genes["glass"] = wg[1]
    genes["roof"] = pick(fkey, "roof", SY.ROOFS_INDUSTRIAL if body in SY.INDUSTRIAL else SY.ROOFS,
                         None, salt)
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
    cont["roof_v"] = draw(bid, "roof_v", -0.12, 0.12, SY.STEP["wall_v"], salt)
    # irregularity (scope 5.1.2): what grime and low wealth add, with a building's own rate
    wealth = (brief.get("district") or {}).get("wealth")
    wealth = 0.5 if wealth is None else float(wealth)
    cont["irreg"] = quant(min(max(grime * (1.15 - wealth) *
                                  (0.6 + 0.8 * u(bid, "irreg.k", salt)), 0.0), 1.0), 0.05)
    neon = float((b.get("style") or {}).get("neon", 0.3))
    extra = {"neon": quant(neon, SY.STEP["neon"]),
             "lit": draw(bid, "lit", 0.7, 1.3, 0.01, salt) * LIT_BY_USE.get(b["use"], 0.4),
             "seed": quant(u(bid, "seed", salt), SY.STEP["seed"])}
    extra["lit"] = quant(min(extra["lit"], 1.0), SY.STEP["lit"])
    _ag15(brief, genes, cont, extra, body, fkey, bid, reach, av, salt, wealth)
    if (brief.get("deck") or {}).get("role") == "under":
        # AG10: under an M14 deck, a covered street's grime from the ground up to the soffit,
        # its fronts and windows lit day and night
        cont["wear"] = draw(bid, "wear.deck", min(max(cont["wear"], 0.7), 0.95), 1.0,
                            SY.STEP["wear"], salt)
        h = float(b["height_m"])
        cont["dirt_m"] = draw(bid, "dirt_m.deck", 0.8 * h, h + 1.0, SY.STEP["dirt_m"], salt)
        extra["lit"] = quant(max(extra["lit"], draw(bid, "lit.deck", 0.75, 1.0, 0.01, salt)),
                             SY.STEP["lit"])
    for name, val in sorted((ov.get("style") or {}).items()):
        if name in genes:
            genes[name] = val
        elif name in cont:
            cont[name] = float(val)
    colors = {
        "wall": _jitter(genes["wall"], cont["wall_v"], cont["wall_w"]),
        "trim": _jitter(genes["trim"], cont["trim_v"], 0.0),
        "glass": genes["glass"], "roof": _jitter(genes["roof"], cont["roof_v"], 0.0),
        "spandrel": _jitter(dark, cont["wall_v"] * 0.5, 0.0),
        "patch": _jitter("#9a958c", cont["wall_v"], cont["wall_w"]),
    }
    return {"v": GENOME_VERSION, "family": fam, "era": spec.get("era"), "genes": genes,
            "cont": cont, "extra": extra, "colors": colors}


SCHEDULE_OF = {"office": "office", "civic": "office", "residential": "home",
               "hotel": "hotel", "retail": "shop", "station": "shop",
               "industrial": "industrial", "parking": "industrial"}
LIGHT_W = {  # a schedule's color temperatures (weights over systems.LIGHT_COLORS' order)
    "office": {"cool": 0.4, "daylight": 0.25, "neutral": 0.35},
    "home": {"warm": 0.45, "soft": 0.35, "neutral": 0.2},
    "hotel": {"warm": 0.6, "soft": 0.4},
    "shop": {"neutral": 0.4, "cool": 0.3, "magenta": 0.15, "cyan": 0.15},
    "industrial": {"daylight": 0.5, "cool": 0.5},
}


def is_tower(brief: dict) -> bool:
    """AG15: a tower for the neighbor rule and the crown lights: M21's (podium towers,
    towers and landmarks 40 m and taller); a building with no form (the brief leaves it out)
    by the same rule on its type and height."""
    b = brief["building"]
    if b.get("form"):
        return bool(b["form"].get("tower"))
    t = b.get("type") or ""
    return (t in ("building.podium_tower", "building.tower") or
            t.startswith("building.landmark.")) and float(b.get("height_m") or 0.0) >= 40.0


def _ag15(brief, genes, cont, extra, body, fkey, bid, reach, av, salt, wealth) -> None:
    """AG15's genes: the skin over a glazed system (LED strips, fritted glass), the accent
    of its LEDs, crown lights and logo, and the night: its schedule by use (a share of
    towers vacant, by the district's danger and wealth), its light's color temperature,
    how much the rooms' temperatures spread, an office's band of floors."""
    b = brief["building"]
    T = SY.SYSTEMS[body]
    glazed = body in SY.CURTAIN or T["wwr"][1] >= 0.6
    genes["skin"] = "none"
    if glazed and T.get("feature") not in ("led", "media"):
        genes["skin"] = pick(fkey, "ag15.skin", SY.SKINS,
                             (1.0, 0.6 * reach, 0.4 * reach), salt)
    accents = list(SY.ACCENTS)
    genes["accent"] = pick(fkey, "ag15.accent", accents, None, salt)
    tower = is_tower(brief)
    genes["crown_light"] = pick(fkey, "ag15.crown", SY.CROWN_LIGHTS,
                                (1.2 - 0.6 * reach, 0.1 + 0.5 * reach, 0.1 + 0.4 * reach,
                                 0.4 * reach), salt) if tower else "none"
    genes["logo"] = "logo" if tower and b["use"] in ("office", "mixed", "retail", "hotel",
                                                     "civic") and \
        u(fkey, "ag15.logo", salt) < 0.15 + 0.45 * reach else "none"
    use = b["use"]
    sched = SCHEDULE_OF.get(use)
    if sched is None:
        sched = pick(bid, "ag15.night.mixed", ("office", "home", "shop"), (0.4, 0.4, 0.2),
                     salt)
    dist = brief.get("district") or {}
    danger = float(dist.get("danger") if dist.get("danger") is not None else 0.3)
    pv = (0.02 + 0.15 * danger * (1.15 - wealth)) * (1.5 if tower else 1.0)
    vacant = not b.get("landmark") and u(bid, "ag15.vacant", salt) < pv
    lw = LIGHT_W[sched]
    light = pick(fkey, "ag15.light", sorted(lw), [lw[k] for k in sorted(lw)], salt)
    if av.get("night"):
        lights = _order(fkey, "ag15.light.alt", sorted(SY.LIGHT_COLORS), None, salt)
        acc = _order(fkey, "ag15.accent.alt", accents, None, salt)
        la = _first((light, genes["accent"]), [(l_, a_) for a_ in acc for l_ in
                                               [light] + [x for x in lights if x != light]],
                    lambda x: x in av["night"])
        light, genes["accent"] = la
    genes["light"] = light
    extra["night"] = {"schedule": "vacant" if vacant else sched,
                      "color": [round(v, 4) for v in SY.LIGHT_COLORS[light]],
                      "spread": draw(bid, "ag15.spread", 0.1, 0.6, 0.05, salt),
                      "band": int(pick(bid, "ag15.band", (2, 3, 4, 5, 6), None, salt))}
    if vacant:
        extra["lit"] = quant(min(extra["lit"], 0.06), SY.STEP["lit"])


def groups_of(brief: dict) -> list[str]:
    """The mass groups a building has (base, body, top), in that order."""
    have = {SY.role_group(m["role"]) for m in brief["masses"]}
    return [g for g in GROUPS if g in have]


def effective(genome: dict, used: dict) -> dict:
    """The genes a building's shell used (the generator's report `used`: groups present,
    and which features it built), as {gene: value}; the vector of the uniqueness check."""
    genes, cont = genome["genes"], genome["cont"]
    out: dict = {}
    for g in used.get("open", []):
        # (AG5: an open shed's columns: their bay and section)
        out[f"{g}.bay_m"] = cont[f"{g}.bay_m"]
        out[f"{g}.corner_m"] = cont[f"{g}.corner_m"]
    for g in used.get("groups", []):
        s = genes[f"{g}.system"]
        out[f"{g}.system"] = s
        for gene in ("window", "rhythm"):
            out[f"{g}.{gene}"] = genes[f"{g}.{gene}"]
        if genes.get(f"{g}.wpattern", "grid") != "grid":
            out[f"{g}.wpattern"] = genes[f"{g}.wpattern"]     # (AG15)
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
        for gene in ("frame", "sills"):
            if gene in used.get("parts", {}).get(g, ()):
                out[f"{g}.{gene}"] = genes[f"{g}.{gene}"]
        if "balcony" in used.get("parts", {}).get(g, ()):
            for gene in ("balcony", "balcony_pat"):
                out[f"{g}.{gene}"] = genes[f"{g}.{gene}"]
            out[f"{g}.balcony_m"] = cont[f"{g}.balcony_m"]
        feat = SY.SYSTEMS[s].get("feature")
        if feat in used.get("parts", {}).get(g, ()):
            for name in sorted(SY.FEATURE_GENES.get(feat, {})):
                out[f"{g}.{name}"] = genes[f"{g}.{name}"]
            for gene in {"fins": ("fin_m",), "diagrid": ("member_m",),
                         "exo": ("member_m",), "capsules": ("pod_m",)}.get(feat, ()):
                out[f"{g}.{gene}"] = cont[f"{g}.{gene}"]
    for gene in ("corner", "wall", "roof"):
        out[gene] = genes[gene]
    for gene, size in (("cut", "cut_m"), ("setback", "setback_m"), ("canopy", "canopy_m"),
                       ("arcade", "arcade_m")):
        if gene in used.get("articulation", ()):
            out[gene] = genes[gene]
            out[size] = cont[size]
    if used.get("crown"):
        out["crown"] = genes["crown"]
    if used.get("irregular"):
        out["irreg"] = cont["irreg"]
    if used.get("trim"):
        out["trim"] = genes["trim"]
        out["trim_v"] = cont["trim_v"]
    if used.get("glass"):
        out["glass"] = genes["glass"]
    if used.get("ground"):
        out["ground"] = genes["ground"]
    if used.get("finish"):
        out["finish"] = genes["finish"]
    if used.get("base"):
        out["base"] = genes["base"]
    if used.get("dado"):
        out["dado"] = genes["dado"]
        out["dado_m"] = cont["dado_m"]
    fr = used.get("front") or {}
    for gene in ("front_frame", "front_riser", "front_paint", "front_fascia"):
        if fr.get("shops"):
            out[gene] = genes[gene]
    if fr.get("shops"):
        out["front_shutter"] = cont["front_shutter"]
    if fr.get("main"):
        out["front_door"] = genes["front_door"]
        out["front_steps"] = genes["front_steps"]
        out["front_recess_m"] = cont["front_recess_m"]
    for gene in ("wear", "dirt_m", "wall_v", "wall_w", "roof_v"):
        out[gene] = cont[gene]
    # AG4: the roof form a building built (its kind, pitch and eaves) and a flat roof's
    # finish
    form = used.get("roof")
    if form and form != "flat":
        out["roof_shape"] = form
        out["roof_pitch" if form != "mansard" else "roof_mansard"] = \
            cont["roof_pitch" if form != "mansard" else "roof_mansard"]
        if form not in ("sawtooth",):
            out["roof_eave_m"] = cont["roof_eave_m"]
    if used.get("roof_finish"):
        out["roof_finish"] = genes["roof_finish"]
    # AG15: the skin, the crown lights and logo a building built, their accent, its light
    for gene in ("skin", "crown_light", "logo"):
        if used.get(gene):
            out[gene] = genes[gene]
    if used.get("accent"):
        out["accent"] = genes["accent"]
    if genes.get("light"):
        out["light"] = genes["light"]
    return out
