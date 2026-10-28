"""assetgen's checks (scope section 9), run on every build; a failing check means the assets
are not delivered (`assetgen build` exits 1).

AG1's: `asset_coverage` (every building of the model has a shell and a proxy, every key of
the manifest is in the model), `asset_envelope` (every shell inside its masses and allowed
overhangs), `asset_meshes` (no degenerate or duplicate triangles, every part closed and
consistently wound, so no crack along any shell), `asset_unique` (genome distance between
any two buildings outside one complex family, scope 5.1.1) and `asset_budget` (shell
triangles of the city within section 11's estimate for its bays and roofs).
"""

from __future__ import annotations

import numpy as np

from .buildings import genome as GN

T_BAY = 24          # section 11: shell triangles per bay
RHO_ROOF = 1.0      # and per m2 of roof


def coverage(model, records: dict) -> dict:
    ids = sorted(b.id for b in model.buildings)
    missing = [i for i in ids if i not in records or records[i]["triangles"] <= 0 or
               records[i]["proxy"]["triangles"] <= 0]
    extra = sorted(set(records) - set(ids))
    return {"name": "asset_coverage", "ok": not missing and not extra,
            "buildings": len(ids), "missing": len(missing), "extra": len(extra),
            "first": (missing + extra)[:5]}


def envelope(records: dict) -> dict:
    bad = [k for k in sorted(records) if not records[k]["checks"]["envelope"]["ok"]]
    tot = {}
    for r in records.values():
        for k, v in r["checks"]["envelope"].items():
            if k != "ok":
                tot[k] = tot.get(k, 0) + v
    return {"name": "asset_envelope", "ok": not bad, "failures": len(bad), "first": bad[:5],
            "totals": tot}


def meshes(records: dict) -> dict:
    bad = []
    tot = {"degenerate": 0, "duplicate": 0, "open_edges": 0, "bad_edges": 0, "parts": 0}
    for k in sorted(records):
        m = records[k]["checks"]["mesh"]
        for f in tot:
            tot[f] += m.get(f, 0)
        if m["degenerate"] or m["duplicate"] or m["open_edges"] or m["bad_edges"] or \
                not m.get("uv0", True):
            bad.append(k)
    return {"name": "asset_meshes", "ok": not bad, "failures": len(bad), "first": bad[:5],
            "totals": tot}


def unique(records: dict, k: int) -> dict:
    """Every two buildings outside one complex family differ in at least k discrete genes or
    by a genome distance of at least k (a discrete gene counts 1; a continuous one
    min(|delta| / scale, 1)), in hundredths so the sums are exact integers."""
    ids = sorted(records)
    n = len(ids)
    names = sorted({g for i in ids for g in records[i]["genes"]})
    disc = [g for g in names if any(isinstance(records[i]["genes"].get(g), str) for i in ids)]
    cont = [g for g in names if g not in disc]
    D = np.full((n, len(disc)), -1, dtype=np.int64)
    for c, g in enumerate(disc):
        vals = sorted({records[i]["genes"][g] for i in ids if g in records[i]["genes"]})
        code = {v: j for j, v in enumerate(vals)}
        for r, i in enumerate(ids):
            v = records[i]["genes"].get(g)
            if v is not None:
                D[r, c] = code[v]
    X = np.full((n, len(cont)), np.nan)
    S = np.array([GN.SCALE.get(g.split(".")[-1], 1.0) for g in cont], dtype=np.float64)
    for c, g in enumerate(cont):
        for r, i in enumerate(ids):
            v = records[i]["genes"].get(g)
            if v is not None:
                X[r, c] = float(v)
    fam = np.array([hash_family(records[i].get("family")) for i in ids], dtype=np.int64)
    fails = 0
    first = []
    nearest = np.full(n, 10 ** 9, dtype=np.int64)
    for r in range(n - 1):
        dd = (D[r + 1:] != D[r]).sum(axis=1).astype(np.int64)
        a, b = X[r + 1:], X[r]
        both = ~np.isnan(a) & ~np.isnan(b)
        one = np.isnan(a) != np.isnan(b)
        diff = np.where(both, np.abs(np.where(both, a, 0.0) - np.where(both, b, 0.0)), 0.0)
        part = np.minimum(np.floor(diff / S * 100.0), 100.0).astype(np.int64)
        cc = np.where(both, part, 0).sum(axis=1) + 100 * one.sum(axis=1)
        dist = 100 * dd + cc
        same = (fam[r + 1:] == fam[r]) & (fam[r] != 0)
        dist = np.where(same, 10 ** 9, dist)
        nearest[r] = min(nearest[r], int(dist.min()) if len(dist) else 10 ** 9)
        nearest[r + 1:] = np.minimum(nearest[r + 1:], dist)
        bad = (dd < k) & (dist < 100 * k) & ~same
        if bad.any():
            js = np.nonzero(bad)[0]
            fails += len(js)
            for j in js[:3]:
                if len(first) < 8:
                    first.append([ids[r], ids[r + 1 + j], int(dd[j]),
                                  round(int(dist[j]) / 100.0, 2)])
    finite = nearest[nearest < 10 ** 9]
    return {"name": "asset_unique", "ok": fails == 0, "k": k, "pairs": n * (n - 1) // 2,
            "failures": int(fails), "first": first,
            "nearest": {"min": round(int(finite.min()) / 100.0, 2) if len(finite) else None,
                        "median": round(int(np.sort(finite)[len(finite) // 2]) / 100.0, 2)
                        if len(finite) else None},
            "genes": {"discrete": len(disc), "continuous": len(cont)}}


def hash_family(f: str | None) -> int:
    if not f:
        return 0
    import hashlib
    return int.from_bytes(hashlib.blake2b(f.encode("utf-8"), digest_size=7).digest(), "little")


def budget(records: dict) -> dict:
    """Section 11's shell estimate for this city: its bays (mass side area over 3 m by one
    floor, party walls and hidden faces included, as section 11 counts them) times 24 plus
    one triangle per m2 of roof."""
    bays = sum(r["stats"]["bays_s11"] for r in records.values())
    roof = sum(r["stats"]["roof_m2"] for r in records.values())
    tris = sum(r["triangles"] for r in records.values())
    est = int(bays * T_BAY + roof * RHO_ROOF)
    return {"name": "asset_budget", "ok": tris <= est, "triangles": tris,
            "budget": est, "bays": int(bays), "roof_m2": int(roof),
            "ratio": round(tris / est, 3) if est else None}
