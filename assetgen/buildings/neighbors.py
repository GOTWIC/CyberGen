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
"""

from __future__ import annotations

import math

from . import genome as GN

RADIUS_M = 150.0
KINDS = ("system", "pattern", "palette", "night")


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


def assign(briefs: dict, genomes: dict) -> dict[str, dict]:
    """Apply the rule to `genomes` (in place); {id: what it avoided} of every tower drawn
    again (lists, sorted, for hashing and the record)."""
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
    for k in order:
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
