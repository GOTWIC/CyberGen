"""`assetgen brief diff A B`: the briefs two builds add, remove and change (scope 4.4), and the
seam check of a district regeneration.

A brief changes exactly when an asset must be made again (its hash is part of the asset's).
For a regenerated district (M10's `citygen build --district`), `seam` sorts every changed
brief into the district's own, the seam's (its building, or an entity its brief names in
either build, was added, removed or changed in the model) and the rest, which must be none.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from citygen.model import COLLECTIONS

from . import canon as C
from . import planar as PL


def load_briefs(src) -> dict:
    """A briefs document from a briefs.json, a build dir (its assets/briefs.json) or a dict."""
    if isinstance(src, dict):
        return src
    p = Path(src)
    if p.is_dir():
        p = p / "assets" / "briefs.json" if (p / "assets").is_dir() else p / "briefs.json"
    return json.loads(p.read_text(encoding="utf-8"))


def diff(a, b) -> dict:
    """{"added": [ids], "removed": [ids], "changed": {id: [top-level brief fields]},
    "same": n} (ids sorted)."""
    A, B = load_briefs(a), load_briefs(b)
    ha, hb = A["hashes"], B["hashes"]
    added = sorted(set(hb) - set(ha))
    removed = sorted(set(ha) - set(hb))
    changed = {}
    same = 0
    for k in sorted(set(ha) & set(hb)):
        if ha[k] == hb[k]:
            same += 1
            continue
        ba, bb = A["briefs"][k], B["briefs"][k]
        changed[k] = sorted(f for f in set(ba) | set(bb)
                            if C.dumps(ba.get(f)) != C.dumps(bb.get(f)))
    return {"added": added, "removed": removed, "changed": changed, "same": same}


def text(d: dict, limit: int | None = 20) -> str:
    lines = [f"briefs: {len(d['added'])} added, {len(d['removed'])} removed, "
             f"{len(d['changed'])} changed, {d['same']} the same"]
    fields: dict[str, int] = {}
    for fs in d["changed"].values():
        for f in fs:
            fields[f] = fields.get(f, 0) + 1
    if fields:
        lines.append("changed fields: " + ", ".join(
            f"{f} {n}" for f, n in sorted(fields.items(), key=lambda t: (-t[1], t[0]))))
    for what in ("added", "removed"):
        ids = d[what]
        if ids:
            shown = ids if limit is None else ids[:limit]
            more = "" if len(shown) == len(ids) else f" ... ({len(ids) - len(shown)} more)"
            lines.append(f"{what}: " + ", ".join(shown) + more)
    ch = sorted(d["changed"])
    if ch:
        shown = ch if limit is None else ch[:limit]
        more = "" if len(shown) == len(ch) else f"\n  ... ({len(ch) - len(shown)} more)"
        lines.append("changed:\n" + "\n".join(f"  {k}: {', '.join(d['changed'][k])}"
                                              for k in shown) + more)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Seam of a district regeneration
# ---------------------------------------------------------------------------

def entity_changes(model_a: dict, model_b: dict) -> set[str]:
    """Ids added, removed or changed between two city models (raw JSON)."""
    out: set[str] = set()
    for coll in COLLECTIONS:
        ia = {e["id"]: e for e in model_a.get(coll, [])}
        ib = {e["id"]: e for e in model_b.get(coll, [])}
        out |= set(ia) ^ set(ib)
        for k in set(ia) & set(ib):
            if C.dumps(ia[k]) != C.dumps(ib[k]):
                out.add(k)
    return out


def _strings(v, acc: set) -> set:
    if isinstance(v, str):
        acc.add(v)
    elif isinstance(v, dict):
        for x in v.values():
            _strings(x, acc)
    elif isinstance(v, list):
        for x in v:
            _strings(x, acc)
    return acc


def seam(model_a: dict, model_b: dict, briefs_a, briefs_b, district_id: str) -> dict:
    """Sort the changed briefs of a district regeneration: in the district, on the seam
    (the building or something its brief names changed in the model), or unexplained.
    Distances are from the district outline to the building's origin, in meters."""
    A, B = load_briefs(briefs_a), load_briefs(briefs_b)
    d = diff(A, B)
    changed_ids = entity_changes(model_a, model_b)
    poly = next(x for x in model_b["districts"] if x["id"] == district_id)["polygon"]
    ring = PL.ring(poly["exterior"])
    own, seam_ids, unexplained = [], [], []
    far = 0.0
    for bid in d["added"] + d["removed"] + sorted(d["changed"]):
        br = B["briefs"].get(bid) or A["briefs"][bid]
        if br["building"]["district_id"] == district_id:
            own.append(bid)
            continue
        names = _strings(A["briefs"].get(bid), set()) | _strings(B["briefs"].get(bid), set())
        names.add(bid)
        if names & changed_ids:
            seam_ids.append(bid)
            far = max(far, _dist_out(ring, br["origin"]))
        else:
            unexplained.append(bid)
    return {"district": district_id, "added": len(d["added"]), "removed": len(d["removed"]),
            "changed": len(d["changed"]), "same": d["same"], "own": len(own),
            "seam": len(seam_ids), "seam_ids": seam_ids, "unexplained": unexplained,
            "seam_farthest_m": round(far, 1)}


def _dist_out(ring, p) -> float:
    best = math.inf
    n = len(ring)
    for i in range(n):
        dd, _ = PL.point_seg_dist(p, ring[i - 1], ring[i])
        best = min(best, dd)
    return best
