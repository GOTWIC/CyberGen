"""AG15: the neighbor rule (scope 14.16): towers within `RADIUS_M` of each other, outside one
complex family, differ in facade system, window pattern, palette and night look.

A tower (`genome.is_tower`) is taken with its complex family as one unit (a family shares
its discrete genes, so its members change together). Units go tallest first (then by key);
each takes the signatures of the units within `RADIUS_M` that went before it (any two
members' footprint middles that near) and, where its own genome shares one, is drawn again
with them to avoid (`genome.make(brief, avoid)`): another system of its era, then of the
tower pool; another window type and pattern; another glass, then another wall; another
light color and accent. What each tower avoided goes into its asset hash, so a tower whose
neighbors changed is made again.

Signatures: system the body's; pattern (body window, body pattern); palette (wall, glass);
night (light color, accent).

With M10 (a district regeneration, `held_towers`): in a city its build state says a district
regeneration made, every tower outside the district the last regeneration made whose brief
is as its record has it keeps the genome it had (drawn again past what its record says it
avoided, so the same genome and asset hash): those go first and the district's towers, and
any other whose brief changed, take what they took to avoid, as M21's forms
(`Frame.old_towers`) keep the city outside the district as it was.
"""

from __future__ import annotations

import math

from . import genome as GN

RADIUS_M = 150.0
KINDS = ("system", "pattern", "palette", "night")
TUPLE_KINDS = ("pattern", "palette", "night")


def signature(gm: dict) -> dict:
    g = gm["genes"]
    n = (gm.get("extra") or {}).get("night") or {}
    return {"system": g["body.system"], "pattern": (g["body.window"], g["body.wpattern"]),
            "palette": (g["wall"], g["glass"]), "night": (g.get("light"), g["accent"]),
            "schedule": n.get("schedule")}


def _vacant(sig: dict) -> bool:
    return sig.get("schedule") == "vacant"


def _family(brief: dict) -> str | None:
    prop = brief.get("property") or {}
    if prop and prop.get("complex") not in (None, "single") and \
            len(prop.get("building_ids") or []) > 1:
        return prop.get("id")
    return None


def units(briefs: dict) -> dict[str, list[str]]:
    """{unit key: member ids} of the towers: a complex family, else the tower alone."""
    out: dict[str, list[str]] = {}
    for bid in sorted(briefs):
        br = briefs[bid]
        if not GN.is_tower(br):
            continue
        out.setdefault(_family(br) or bid, []).append(bid)
    return out


def avoid_sets(rec: dict) -> dict:
    """A record's `avoided` (lists, as `assign` writes them) as `genome.make` takes it."""
    out = {}
    for kind in KINDS:
        vals = rec.get(kind) or []
        out[kind] = {tuple(v) if kind in TUPLE_KINDS else v for v in vals}
    out["vacant"] = bool(rec.get("vacant"))
    return out


def held_towers(briefs: dict, hashes: dict, old_records: dict, state: dict | None,
                districts: dict[str, str]) -> dict[str, dict | None]:
    """The towers a district regeneration holds (M10): {id: what its genome avoided, None
    where it was drawn as made}. Only in a city its build state (`city_state.json`) says a
    regeneration made (its `edits`); a tower is held when it stands outside the district of
    the last edit, its record is a tower's with AG15's `avoided` (a record written before
    this rule has none: it is drawn anew) and its brief hash is its record's. `districts`:
    {district name: id}."""
    edits = (state or {}).get("edits") or []
    if not edits or not old_records:
        return {}
    last = districts.get(edits[-1].get("district"))
    out: dict[str, dict | None] = {}
    for bid in sorted(briefs):
        rec = old_records.get(bid) or {}
        ag = rec.get("ag15") or {}
        if not ag.get("tower") or "avoided" not in ag or rec.get("brief") != hashes.get(bid):
            continue
        if briefs[bid]["building"].get("district_id") == last or not GN.is_tower(briefs[bid]):
            continue
        out[bid] = ag["avoided"]
    return out


def assign(briefs: dict, genomes: dict, held: dict | None = None) -> dict[str, dict]:
    """Apply the rule to `genomes` (in place); {id: what it avoided} of every tower drawn
    again (lists, sorted, for hashing and the record). `held` (`held_towers`): towers that
    keep the genome they had; a unit (a family or a tower) whose members are all held goes
    first, drawn past what it avoided before, and the rest avoid it."""
    us = units(briefs)
    pos = {k: [(float(briefs[b]["origin"][0]), float(briefs[b]["origin"][1])) for b in m]
           for k, m in us.items()}
    height = {k: max(float(briefs[b]["building"]["height_m"]) for b in m)
              for k, m in us.items()}
    order = sorted(us, key=lambda k: (-height[k], k))
    cell = RADIUS_M
    grid: dict[tuple[int, int], list[str]] = {}
    done: dict[str, dict] = {}
    out: dict[str, dict] = {}
    held = held or {}
    kept = [k for k in order if all(b in held for b in us[k])]
    for k in kept:
        for b in us[k]:
            if held[b] is not None:
                genomes[b] = GN.make(briefs[b], avoid_sets(held[b]))
                out[b] = held[b]
        done[k] = signature(genomes[us[k][0]])
        for x, y in pos[k]:
            key = (math.floor(x / cell), math.floor(y / cell))
            if k not in grid.setdefault(key, []):
                grid[key].append(k)
    kept_set = set(kept)
    for k in order:
        if k in kept_set:
            continue
        near: set[str] = set()
        for x, y in pos[k]:
            cx, cy = math.floor(x / cell), math.floor(y / cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for o in grid.get((cx + dx, cy + dy), ()):
                        if o not in near and any(math.dist((x, y), q) <= RADIUS_M
                                                 for q in pos[o]):
                            near.add(o)
        avoid = {kind: {done[o][kind] for o in sorted(near)} for kind in KINDS}
        # (no two vacant towers side by side: two dark towers light alike)
        avoid["vacant"] = any(_vacant(done[o]) for o in near)
        first = us[k][0]
        sig = signature(genomes[first])
        if any(sig[kind] in avoid[kind] for kind in KINDS) or \
                (avoid["vacant"] and _vacant(sig)):
            for b in us[k]:
                genomes[b] = GN.make(briefs[b], avoid)
                out[b] = {kind: sorted([list(v) if isinstance(v, tuple) else v
                                        for v in avoid[kind]], key=str) for kind in KINDS}
                out[b]["vacant"] = avoid["vacant"]
            sig = signature(genomes[first])
        done[k] = sig
        for x, y in pos[k]:
            key = (math.floor(x / cell), math.floor(y / cell))
            if k not in grid.setdefault(key, []):
                grid[key].append(k)
    return out


def pairs(records: dict, radius: float = RADIUS_M) -> list[tuple[str, str]]:
    """The pairs of towers (records with `ag15.tower`) within `radius` of each other by
    their footprint middles, outside one family, each pair once (sorted)."""
    ts = sorted(b for b, r in records.items() if (r.get("ag15") or {}).get("tower"))
    grid: dict[tuple[int, int], list[str]] = {}
    for b in ts:
        x, y = records[b]["ag15"]["xy"]
        grid.setdefault((math.floor(x / radius), math.floor(y / radius)), []).append(b)
    out = []
    for b in ts:
        x, y = records[b]["ag15"]["xy"]
        fb = records[b].get("family")
        cx, cy = math.floor(x / radius), math.floor(y / radius)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in grid.get((cx + dx, cy + dy), ()):
                    if o <= b:
                        continue
                    if fb and records[o].get("family") == fb:
                        continue
                    if math.dist((x, y), records[o]["ag15"]["xy"]) <= radius:
                        out.append((b, o))
    return sorted(out)
