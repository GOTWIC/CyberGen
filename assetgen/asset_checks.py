"""assetgen's checks (scope section 9), run on every build; a failing check means the assets
are not delivered (`assetgen build` exits 1).

AG1's: `asset_coverage` (every building of the model has a shell and a proxy, every key of
the manifest is in the model), `asset_envelope` (every shell inside its masses and allowed
overhangs), `asset_meshes` (no degenerate or duplicate triangles, every part closed and
consistently wound, so no crack along any shell), `asset_unique` (genome distance between
any two buildings outside one complex family, scope 5.1.1) and `asset_budget` (shell
triangles of the city within section 11's estimate for its bays and roofs).

AG2: the meshes check covers every part mesh of every tile; the envelope check every
instanced part's box; `asset_unique` also asks that the two buildings' contact-sheet
thumbnails differ by `THUMB_MIN` bits of their difference hash (`buildings/thumb.py`); and
`asset_budget` holds every building to the budget of its class (`CLASSES`: unique
triangles, its shell and its own part meshes, per section 11 bay, and instances per bay)
and the city to section 11's estimate with 40% more for parts (`PARTS_SHARE`) and
`I_CITY` instances per bay.
"""

from __future__ import annotations

import numpy as np

from .buildings import genome as GN

T_BAY = 24          # section 11: shell triangles per bay
RHO_ROOF = 1.0      # and per m2 of roof
PARTS_SHARE = 0.4   # AG2's parts: 40% of section 11's shell estimate on top of it
I_CITY = 3.0        # section 11: 2 to 3 M part instances for 1.4 M bays
THUMB_MIN = 8       # bits of 1,504 two thumbnails must differ by
THUMB_FILL = 0.1    # a building filling less of its thumbnail (a sliver) is told by genes
# per building class: unique triangles at most k times section 11's estimate for its bays and
# roof plus a base, and instances at most i per bay plus a base
CLASSES = {
    "low": {"k": 3.0, "base": 4000, "i": 8.0, "ibase": 60},
    "mid": {"k": 2.4, "base": 6000, "i": 8.0, "ibase": 100},
    "high": {"k": 2.0, "base": 10000, "i": 7.0, "ibase": 200},
    "tower": {"k": 2.0, "base": 20000, "i": 6.0, "ibase": 400},
    "mega": {"k": 2.0, "base": 20000, "i": 6.0, "ibase": 400},
}
MEGA = ("building.megabuilding", "building.straddle_building")


def budget_class(rec: dict) -> str:
    """A building's budget class: mega (megabuildings, straddle buildings, landmarks), else by
    height: tower (100 m or more), high (40 m), mid (12 m), low."""
    t = rec["type"]
    if t in MEGA or t.startswith("building.landmark"):
        return "mega"
    h = rec["bounds"][1][2]
    return "tower" if h >= 100.0 else ("high" if h >= 40.0 else ("mid" if h >= 12.0 else "low"))


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


def meshes(records: dict, tile_parts: dict | None = None) -> dict:
    bad = []
    tot = {"degenerate": 0, "duplicate": 0, "open_edges": 0, "bad_edges": 0, "parts": 0}
    for k in sorted(records):
        m = records[k]["checks"]["mesh"]
        for f in tot:
            tot[f] += m.get(f, 0)
        if m["degenerate"] or m["duplicate"] or m["open_edges"] or m["bad_edges"] or \
                not m.get("uv0", True):
            bad.append(k)
    pm = 0
    for t in sorted(tile_parts or {}):
        info = (tile_parts or {})[t]
        if info:
            pm += info["meshes"]
            bad += [f"{t}:{n}" for n in info["bad"]]
    return {"name": "asset_meshes", "ok": not bad, "failures": len(bad), "first": bad[:5],
            "totals": tot, "part_meshes": pm}


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
    from .buildings import thumb as TH
    thumbs = [records[i].get("thumb") for i in ids]
    Hb = TH.distances([t or "00" * (TH.BITS // 8) for t in thumbs]) if n else None
    has_t = np.array([t is not None and records[i].get("thumb_fill", 1.0) >= THUMB_FILL
                      for t, i in zip(thumbs, ids)], dtype=bool)
    fails = 0
    tfails = 0
    first = []
    tfirst = []
    nearest = np.full(n, 10 ** 9, dtype=np.int64)
    tnear = np.full(n, 10 ** 9, dtype=np.int64)
    for r in range(n - 1):
        if Hb is not None and has_t[r]:
            hd = np.bitwise_count(Hb[r + 1:] ^ Hb[r]).astype(np.int64).sum(axis=1)
            same_f = (fam[r + 1:] == fam[r]) & (fam[r] != 0) | ~has_t[r + 1:]
            hd = np.where(same_f, 10 ** 9, hd)
            if len(hd):
                tnear[r] = min(tnear[r], int(hd.min()))
                tnear[r + 1:] = np.minimum(tnear[r + 1:], hd)
            tb = hd < THUMB_MIN
            if tb.any():
                js = np.nonzero(tb)[0]
                tfails += len(js)
                for j in js[:3]:
                    if len(tfirst) < 8:
                        tfirst.append([ids[r], ids[r + 1 + j], int(hd[j])])
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
    tfin = tnear[tnear < 10 ** 9]
    return {"name": "asset_unique", "ok": fails == 0 and tfails == 0, "k": k,
            "pairs": n * (n - 1) // 2,
            "failures": int(fails), "first": first + tfirst,
            "nearest": {"min": round(int(finite.min()) / 100.0, 2) if len(finite) else None,
                        "median": round(int(np.sort(finite)[len(finite) // 2]) / 100.0, 2)
                        if len(finite) else None},
            "thumbs": {"min_bits": THUMB_MIN, "failures": int(tfails),
                       "slivers": int((~has_t).sum()),
                       "nearest_min": int(tfin.min()) if len(tfin) else None,
                       "nearest_median": int(np.sort(tfin)[len(tfin) // 2]) if len(tfin)
                       else None},
            "genes": {"discrete": len(disc), "continuous": len(cont)}}


def hash_family(f: str | None) -> int:
    if not f:
        return 0
    import hashlib
    return int.from_bytes(hashlib.blake2b(f.encode("utf-8"), digest_size=7).digest(), "little")


def budget(records: dict, tile_parts: dict | None = None) -> dict:
    """Section 11's estimate for this city: its bays (mass side area over 3 m by one floor,
    party walls and hidden faces included, as section 11 counts them) times 24 plus one
    triangle per m2 of roof for the shells, 40% more for the parts (AG2); the unique
    triangles (shells with their merged parts, and each tile's part meshes once) within it,
    and the instances within `I_CITY` per bay. Every building within its class's budget."""
    bays = sum(r["stats"]["bays_s11"] for r in records.values())
    roof = sum(r["stats"]["roof_m2"] for r in records.values())
    tris = sum(r["triangles"] for r in records.values())
    ptris = sum(t["triangles"] for t in (tile_parts or {}).values() if t)
    inst = sum(r.get("instances", 0) for r in records.values())
    est = int(bays * T_BAY + roof * RHO_ROOF)
    city = int(est * (1.0 + PARTS_SHARE))
    over = []
    by: dict[str, dict] = {}
    for k in sorted(records):
        r = records[k]
        c = CLASSES[r.get("class") or budget_class(r)]
        own = r["stats"]["bays_s11"] * T_BAY + r["stats"]["roof_m2"] * RHO_ROOF
        tb = int(c["k"] * own + c["base"])
        ib = int(c["i"] * r["stats"]["bays_s11"] + c["ibase"])
        u = r["triangles"] + r.get("part_triangles", 0)
        i = r.get("instances", 0)
        b = by.setdefault(r.get("class") or budget_class(r),
                          {"buildings": 0, "unique": 0, "instances": 0, "max_ratio": 0.0,
                           "max_inst_ratio": 0.0})
        b["buildings"] += 1
        b["unique"] += u
        b["instances"] += i
        b["max_ratio"] = max(b["max_ratio"], round(u / tb, 3))
        b["max_inst_ratio"] = max(b["max_inst_ratio"], round(i / ib, 3))
        if u > tb or i > ib:
            over.append(k)
    ok = tris + ptris <= city and inst <= I_CITY * bays and not over
    return {"name": "asset_budget", "ok": ok, "triangles": tris, "part_meshes": ptris,
            "unique": tris + ptris, "budget": city, "shell_estimate": est,
            "instances": inst, "instance_budget": int(I_CITY * bays), "bays": int(bays),
            "roof_m2": int(roof), "ratio": round((tris + ptris) / city, 3) if city else None,
            "over": len(over), "first": over[:5], "classes": by}
