"""`citygen model diff A B`: the entities two city models add, remove and change, by id and
grouped by collection (M10). With stable ids (`ids.py`) an entity that did not change keeps
its id, so a district regenerated or a spec field changed shows up here as exactly what it
touched."""

from __future__ import annotations

import json
from pathlib import Path

from .model import COLLECTIONS


def _load(src) -> dict:
    if isinstance(src, dict):
        return src
    if hasattr(src, "model_dump"):
        return src.model_dump(mode="json")
    return json.loads(Path(src).read_text(encoding="utf-8"))


def _canon(e: dict) -> str:
    return json.dumps(e, sort_keys=True, ensure_ascii=False, allow_nan=False)


def diff(a, b) -> dict:
    """{collection: {"added": [ids], "removed": [ids], "changed": {id: [fields]}}} for every
    collection that differs (ids sorted), plus "header": the top-level fields that differ."""
    A, B = _load(a), _load(b)
    out: dict = {}
    head = sorted(k for k in set(A) | set(B) if k not in COLLECTIONS and A.get(k) != B.get(k))
    if head:
        out["header"] = head
    for coll in COLLECTIONS:
        ia = {e["id"]: e for e in A.get(coll, [])}
        ib = {e["id"]: e for e in B.get(coll, [])}
        added = sorted(set(ib) - set(ia))
        removed = sorted(set(ia) - set(ib))
        changed = {}
        for k in sorted(set(ia) & set(ib)):
            ea, eb = ia[k], ib[k]
            if ea == eb or _canon(ea) == _canon(eb):
                continue
            changed[k] = sorted(f for f in set(ea) | set(eb) if ea.get(f) != eb.get(f))
        if added or removed or changed:
            out[coll] = {"added": added, "removed": removed, "changed": changed}
    return out


def counts(d: dict) -> dict[str, tuple[int, int, int]]:
    return {c: (len(v["added"]), len(v["removed"]), len(v["changed"]))
            for c, v in d.items() if c != "header"}


def text(d: dict, limit: int | None = 20) -> str:
    """The diff as text: a line per collection with the counts, then up to `limit` ids of each
    kind (None: all) with the fields that changed."""
    if not d:
        return "identical: no entity added, removed or changed"
    lines = []
    if d.get("header"):
        lines.append(f"model fields: {', '.join(d['header'])}")
    tot = [0, 0, 0]
    for coll, (na, nr, nc) in counts(d).items():
        tot = [tot[0] + na, tot[1] + nr, tot[2] + nc]
        lines.append(f"{coll}: {na} added, {nr} removed, {nc} changed")
        v = d[coll]
        for kind, sign in (("added", "+"), ("removed", "-")):
            ids = v[kind] if limit is None else v[kind][:limit]
            lines += [f"  {sign} {i}" for i in ids]
            if len(ids) < len(v[kind]):
                lines.append(f"  {sign} ... {len(v[kind]) - len(ids)} more")
        ch = list(v["changed"].items())
        shown = ch if limit is None else ch[:limit]
        lines += [f"  ~ {i} ({', '.join(f)})" for i, f in shown]
        if len(shown) < len(ch):
            lines.append(f"  ~ ... {len(ch) - len(shown)} more")
    lines.append(f"total: {tot[0]} added, {tot[1]} removed, {tot[2]} changed")
    return "\n".join(lines) + "\n"
