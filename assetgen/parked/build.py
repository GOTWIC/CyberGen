"""The parked vehicles stage (`assetgen vehicles BUILD`, and in `assetgen build` after the
props): AG8's parked cars as AG18's hero vehicles.

```
BUILD/assets/unreal_contribution.vehicles.json   placement entries, one per tile
BUILD/assets/vehicles_report.json, .txt          checks and stats
```

One placement entry per tile that AG8 draws parked cars in (`vehicles.parked.<tile>`, kind
`vehicles`, the format of `docs/unreal_export.md`, "AG18's vehicles"), replacing AG8's entry of
that tile (`prop.parked_vehicle.<tile>`, which is also M15's prototype actor's key): a vehicle
per car placed, its pack, transform from the tile's middle, paint and id. The Unreal exporter
drops the entries a placement replaces from stage 2, so AG8's variants and the blockout's
prototypes go together.

Without a vehicle library (`library.py`), or with the asset spec's `vehicles.parked` set to
`variants`, the stage writes nothing and takes away the files an earlier run left: AG8's
variants stay, exactly as before AG18. A file is written only when its bytes change.

Checks (`vehicles_report.txt`): `vehicles_coverage` (every parked car placed or left out with a
reason), `vehicles_clear` (every footprint on its carriageway, off the crosswalks and its
neighbors, measured again from scratch), `vehicles_variety` (never three of one model in a
row along a curb, two running in under `place.MAX_PAIR_SHARE` of the curb neighbors, no two
neighbors of one model in one color, several models), `vehicles_replaces` (an entry per tile
replacing exactly AG8's), `vehicles_library` (every model placed is in the library, none of
the Vex or Aurels).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import shapely

from .. import __version__
from .. import canon as C
from . import library as LB
from . import place as PL
from . import table as T

VERSION = 1
PART = "vehicles"
CONTRIB = "unreal_contribution.vehicles.json"
REPORT = "vehicles_report"
KEY = "vehicles.parked.{tile}"
AG8_KIND = "prop.parked_vehicle"
MIN_MODELS = 4          # a city of `MIN_MODELS_AT` parked cars shows at least this many
MIN_MODELS_AT = 40
FRAME = ("citygen x east, y north, z up, m; vehicles [x, y, z, yaw] from the entry's pivot, "
         "the car's x forward; paint linear rgb (primary, secondary, accent)")


def code_hash() -> str:
    here = Path(__file__).resolve().parent
    return C.digest([[f.name, C.sha256_bytes(f.read_bytes().replace(b"\r\n", b"\n"))]
                     for f in sorted(here.glob("*.py"))])


def _write_if_changed(path: Path, data: bytes) -> bool:
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _dump(doc) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def ag8_entries(out_dir: Path) -> list[dict] | None:
    """AG8's parked car entries (`unreal_contribution.props.json`): key, tile, pivot, and the
    cars' transforms and ids; None when AG8 has not run."""
    p = Path(out_dir) / "unreal_contribution.props.json"
    if not p.is_file():
        return None
    con = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for e in con.get("entries", []):
        if e.get("kind") != AG8_KIND:
            continue
        xfs, ids = [], []
        for q in e.get("parts", []):
            xfs += q["xforms"]
            ids += q["ids"]
        out.append({"key": e["key"], "tile": e["tile"], "pivot": e["pivot"], "xforms": xfs,
                    "ids": ids})
    return sorted(out, key=lambda e: e["key"])


def mode(spec_doc: dict | None) -> str:
    return ((spec_doc or {}).get("vehicles") or {}).get("parked") or "packs"


def build(model, model_sha: str, out_dir: Path, spec_doc: dict | None = None,
          report_always: bool = True) -> dict:
    """The stage; its report (also when it is off: `on` False and why)."""
    import time
    t0 = time.perf_counter()
    out_dir = Path(out_dir)
    lib, cars = LB.load(spec_doc)
    ag8 = ag8_entries(out_dir)
    why_off = None
    if mode(spec_doc) == "variants":
        why_off = "the asset spec's vehicles.parked is variants"
    elif lib is None:
        why_off = f"no vehicle library ({LB.ENV} is off)"
    elif not cars:
        why_off = f"no vehicle library at {lib}"
    elif ag8 is None:
        why_off = "AG8's props contribution is missing (run the props stage first)"
    con_path = out_dir / CONTRIB
    if why_off is not None:
        # (nothing written: a build without the library is as it was before AG18; what an
        # earlier run with it left is taken away)
        removed = []
        for name in (CONTRIB, f"{REPORT}.json", f"{REPORT}.txt"):
            if (out_dir / name).is_file():
                (out_dir / name).unlink()
                removed.append(name)
        return {"city": model.name, "on": False, "why_off": why_off, "ok": True,
                "checks": [], "stats": {}, "files": {"written": [], "removed": removed},
                "seconds": {"total": round(time.perf_counter() - t0, 2)}}
    sw = ((spec_doc or {}).get("vehicles") or {}).get("weights") or {}
    res = PL.place(model, cars, ag8, sw)
    t_place = time.perf_counter()
    code = code_hash()
    con = contribution(model, model_sha, lib, cars, ag8, res, code)
    written = []
    if _write_if_changed(con_path, _dump(con)):
        written.append(CONTRIB)
    rep = {"city": model.name, "on": True, "library": str(lib), "files": {"written": written,
                                                                           "removed": []}}
    rep.update(report(model, cars, ag8, res, con))
    rep["seconds"] = {"place": round(t_place - t0, 2),
                      "total": round(time.perf_counter() - t0, 2)}
    _report(out_dir, rep, report_always or bool(written))
    return rep


def contribution(model, model_sha, lib, cars, ag8, res, code) -> dict:
    placed = res["placed"]
    entries = []
    used = set()
    for e in ag8:
        px, py, pz = e["pivot"]
        vs = []
        for pid in sorted(e["ids"]):
            r = placed.get(pid)
            if r is None:
                continue
            used.add(r["car"])
            vs.append({"car": r["car"], "id": pid,
                       "xform": [C.m(r["x"] - px), C.m(r["y"] - py), C.m(r["z"] - pz),
                                 r["yaw"]],
                       "paint": r["paint"], "steer_deg": 0.0})
        body = {"vehicles": vs, "replaces": [e["key"]], "tile": e["tile"],
                "pivot": [px, py, pz]}
        entries.append({"key": KEY.format(tile=e["tile"]), "kind": "vehicles",
                        "hash": C.digest([code, body, sorted({v["car"] for v in vs}),
                                          [cars[c]["pack_sha256"] for c in
                                           sorted({v["car"] for v in vs})]])[:16],
                        "yaw_deg": 0.0,
                        "tags": {"cg.type": "vehicles.parked", "cg.tile": e["tile"]},
                        **body})
    entries.sort(key=lambda e: e["key"])
    return {"version": VERSION, "stage": "assetgen", "part": PART, "layer": 2,
            "generator": f"assetgen {__version__} (AG18 step H)", "frame": FRAME,
            "city": model.name, "model_sha256": model_sha, "code_sha256": code,
            "library": str(Path(lib).resolve()),
            "cars": {c: {"title": cars[c]["title"], "kind": cars[c]["kind"],
                         "pack_sha256": cars[c]["pack_sha256"]} for c in sorted(used)},
            "entries": entries}


# ---------------------------------------------------------------------------------------
# checks and stats
# ---------------------------------------------------------------------------------------

def _check(cid: str, ok: bool, detail: str, bad=None) -> dict:
    c = {"id": cid, "ok": bool(ok), "detail": detail}
    if bad:
        c["bad"] = list(bad)[:20]
    return c


def report(model, cars, ag8, res, con) -> dict:
    placed, left = res["placed"], res["left_out"]
    checks = []
    # coverage: every M6 parked car (AG8 draws them all) placed or left out with a reason
    parked = sorted(p.id for p in model.props if p.type.split(".", 1)[1] == PL.KIND)
    ag8_ids = {pid for e in ag8 for pid in e["ids"]}
    missing = [pid for pid in parked if pid not in placed and pid not in left]
    extra = sorted(ag8_ids - set(parked))
    no_reason = [pid for pid, why in left.items() if not why]
    checks.append(_check("vehicles_coverage", not missing and not extra and not no_reason,
                         f"{len(parked)} parked cars: {len(placed)} placed, {len(left)} left "
                         f"out with a reason, {len(missing)} missing",
                         missing + extra + no_reason))
    # clear: measured again, from scratch
    fit = res["fit"]
    curb = {pid: key for key, ids in res["curbs"].items() for pid in ids}
    bad = []
    fps, ids = [], []
    for pid in sorted(placed):
        r = placed[pid]
        fp = PL.footprint(cars[r["car"]], r["x"], r["y"], r["yaw"])
        if not fit.lane_ok(curb.get(pid, ("",))[0], fp.buffer(-PL.INSET_M, join_style="mitre")):
            bad.append(f"{pid}: {r['car']} off its parking lane")
        if not fit.xwalk_ok(fp):
            bad.append(f"{pid}: {r['car']} on a crosswalk")
        fps.append(fp)
        ids.append(pid)
    if fps:
        tree = shapely.STRtree(fps)
        a, b = tree.query(fps, predicate="dwithin", distance=PL.GAP_M - 1e-3)
        for i, j in zip(a.tolist(), b.tolist()):
            if i < j:
                bad.append(f"{ids[i]} and {ids[j]} closer than {PL.GAP_M} m")
    checks.append(_check("vehicles_clear", not bad,
                         f"{len(placed)} footprints on their carriageway (pavement map "
                         f"{'on' if fit.on else 'absent'}), off {len(fit.xwalks)} crosswalks, "
                         f"{PL.GAP_M} m apart; {len(bad)} faults", bad))
    # variety
    worst_run, worst_at, same_pairs, runs = 0, None, [], []
    pairs = model_pairs = 0
    for key, cids in sorted(res["curbs"].items()):
        n, prev = 0, None
        for pid in cids:
            r = placed[pid]
            n = n + 1 if prev is not None and prev[0] == r["car"] else 1
            if n > worst_run:
                worst_run, worst_at = n, pid
            if n > PL.MAX_RUN:
                runs.append(f"{pid}: {n} of {r['car']} in a row")
            if prev is not None:
                pairs += 1
                model_pairs += prev[0] == r["car"]
            if prev is not None and prev == (r["car"], r["primary"]):
                same_pairs.append(pid)
            prev = (r["car"], r["primary"])
    share = model_pairs / pairs if pairs else 0.0
    models = Counter(r["car"] for r in placed.values())
    want = min(MIN_MODELS, len(cars)) if len(placed) >= MIN_MODELS_AT else 1
    # (the pair share only where the curbs have a choice: a city whose spots one model alone
    # fits, the test's, has nothing but pairs and runs cut short)
    many = len(models) >= 4 and pairs >= 20
    ok = (worst_run <= PL.MAX_RUN and not same_pairs
          and (share < PL.MAX_PAIR_SHARE or not many)
          and len(models) >= min(want, len(placed)))
    checks.append(_check("vehicles_variety", ok,
                         f"{len(models)} models; longest run of one model along a curb "
                         f"{worst_run} (at most {PL.MAX_RUN}, at {worst_at}); "
                         f"{model_pairs} of {pairs} curb neighbors of one model "
                         f"({100 * share:.2f}%, under {100 * PL.MAX_PAIR_SHARE:.0f}%); "
                         f"{len(same_pairs)} neighbors of one model in one color",
                         runs + same_pairs))
    # replaces: one entry per AG8 tile entry, replacing exactly it
    want_keys = {e["tile"]: e["key"] for e in ag8}
    got = {e["tile"]: e["replaces"] for e in con["entries"]}
    bad = sorted(t for t in want_keys if got.get(t) != [want_keys[t]]) + \
        sorted(t for t in got if t not in want_keys)
    checks.append(_check("vehicles_replaces", not bad,
                         f"{len(con['entries'])} entries for {len(want_keys)} tiles of AG8's "
                         "parked cars", bad))
    # library
    bad = sorted({r["car"] for r in placed.values() if r["car"] not in cars or
                  r["car"] in T.EXCLUDED})
    checks.append(_check("vehicles_library", not bad,
                         f"{len(cars)} cars offered, {len(models)} placed", bad))
    # stats
    reasons = Counter(left.values())
    by_district: dict = defaultdict(Counter)
    for r in placed.values():
        by_district[r["district"] or "-"][r["car"]] += 1
    tiles = Counter(r["tile"] for r in placed.values())
    comps = sum(len(cars[c]["parts"]) for e in con["entries"]
                for c in {v["car"] for v in e["vehicles"]})
    inst = sum(len(cars[r["car"]]["parts"]) for r in placed.values())
    stats = {"parked": len(parked), "placed": len(placed), "left_out": len(left),
             "left_out_by_reason": dict(sorted(reasons.items())),
             "by_model": dict(sorted(models.items())),
             "by_district": {d: dict(sorted(c.items())) for d, c in sorted(by_district.items())},
             "hover_set_down": sum(1 for r in placed.values()
                                   if cars[r["car"]]["kind"] == "hover"),
             "colors": len({r["primary"] for r in placed.values()}),
             "entries": len(con["entries"]), "max_tile_vehicles": max(tiles.values() or [0]),
             "components": comps, "part_instances": inst,
             "meshes": sum(len(cars[c]["parts"]) for c in models),
             "triangles_lod0": sum(cars[r["car"]]["lods"][0]["triangles"]
                                   for r in placed.values()),
             "triangles_lod3": sum(cars[r["car"]]["lods"][3]["triangles"]
                                   for r in placed.values()),
             "longest_model_run": worst_run, "curb_neighbors": pairs,
             "same_model_neighbors": model_pairs,
             "same_model_neighbor_share": round(share, 4)}
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "stats": stats}


def report_text(rep: dict) -> str:
    lines = [f"assetgen vehicles: {rep['city']}: {'PASS' if rep['ok'] else 'FAIL'}", ""]
    if not rep.get("on"):
        lines.append(f"off: {rep['why_off']}; AG8's parked car variants stay")
        return "\n".join(lines) + "\n"
    lines.append(f"library: {rep['library']}")
    for c in rep["checks"]:
        lines.append(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['id']}: {c['detail']}")
        for b in c.get("bad", [])[:5]:
            lines.append(f"      {b}")
    st = rep["stats"]
    lines += ["", f"parked cars {st['parked']}: placed {st['placed']}, left out "
                  f"{st['left_out']} ({st['hover_set_down']} hover cars set down; "
                  f"{st['colors']} primary colors)",
              f"curb neighbors {st['curb_neighbors']}: {st['same_model_neighbors']} of one "
              f"model ({100 * st['same_model_neighbor_share']:.2f}%), longest run "
              f"{st['longest_model_run']}",
              f"in Unreal: {st['entries']} placement actors, {st['components']} instanced "
              f"components, {st['part_instances']} part instances, {st['meshes']} meshes "
              f"(not Nanite), {st['triangles_lod0']:,} triangles at LOD0 "
              f"({st['triangles_lod3']:,} at LOD3); at most {st['max_tile_vehicles']} cars "
              "a tile", "", "by model:"]
    for k, v in sorted(st["by_model"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {k}: {v}")
    if st["left_out_by_reason"]:
        lines.append("left out:")
        for k, v in sorted(st["left_out_by_reason"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {v}: {k}")
    lines.append("by district:")
    for d, c in st["by_district"].items():
        lines.append(f"  {d}: " + ", ".join(f"{k} {v}" for k, v in
                                           sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))))
    s = rep.get("seconds")
    if s:
        lines.append("seconds: " + ", ".join(f"{k} {v}" for k, v in s.items()))
    return "\n".join(lines) + "\n"


def _report(out_dir: Path, rep: dict, write: bool) -> None:
    if not write and (out_dir / f"{REPORT}.json").is_file():
        return
    _write_if_changed(out_dir / f"{REPORT}.json", _dump(rep))
    _write_if_changed(out_dir / f"{REPORT}.txt", report_text(rep).encode("utf-8"))
