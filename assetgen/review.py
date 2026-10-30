"""The art-direction loop for the assets (scope 14.6, AG5; as citygen's `review`): a Claude
Code session, through the `assetgen` skill, looks at a build's previews against the prompt
and the asset spec, changes spec parameters (never code), builds again, a few rounds at
most. assetgen makes no model call: this module only prepares each round's review sheet and
tells the rounds apart.

`assetgen review BUILD --spec SPEC [--prev PREV_BUILD]` writes `review.md` and `review.json`
into `BUILD/assets/`: the checks of every assetgen stage, the key numbers of the city and of
every district (eras, facade systems, generators, heroes, wear, triangles), what changed in
the spec and in the numbers since the previous round, the previews to open, and the spec
parameters that answer what the reviewer may see. `assetgen spec diff A B` lists the
parameter changes between two asset specs.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

MAX_ROUNDS = 3
REPORTS = ("asset_report.json", "streets_report.json", "props_report.json",
           "materials_report.json")
# previews (under BUILD/assets) by prefix: what each shows
PREVIEWS = [
    ("previews_ag6/iso_", "a district textured by day: eras, systems, colours, signs"),
    ("previews_ag6/street_", "street level, textured: fronts, signs, props, wear"),
    ("previews_ag6/custom_", "views of the round's own (landmarks, slopes)"),
    ("previews/contact_", "a contact sheet per type: the generators side by side"),
    ("previews/tower_", "the tallest building of each era up close"),
    ("previews/city_full", "the whole city with every shell"),
    ("preview_edges.png", "the briefs' facade classes (front, street, party, blind ...)"),
]
# what a reviewer may see -> the asset spec parameters that change it
LEVERS = [
    ("a district in the wrong era (heritage where it should be corporate glass ...)",
     "districts.<name>.era"),
    ("a district's facades too uniform, or the wrong facade systems",
     "districts.<name>.systems, eras.<era>.systems"),
    ("too clean or too worn, too little or too much grime",
     "districts.<name>.wear, eras.<era>.wear"),
    ("too many or too few signs and ads", "districts.<name>.ad_density"),
    ("the neon colours of a district", "districts.<name>.neon_palette"),
    ("signs in the wrong scripts", "districts.<name>.signage_scripts, "
                                   "eras.<era>.signage_scripts"),
    ("too much or too little glass", "eras.<era>.window_to_wall"),
    ("bays too wide or too narrow", "eras.<era>.bay_m"),
    ("wall and trim colours off for an era", "eras.<era>.palette"),
    ("the wrong crowns on the towers (flat, stepped, spire, halo ...)", "eras.<era>.crowns"),
    ("an owner's buildings not reading as one brand",
     "owners.<owner>.brand_colors, owners.<owner>.facade_bias"),
    ("a landmark off its brief (colours, crown)",
     "landmarks.<name>.palette, landmarks.<name>.crown, landmarks.<name>.brief"),
    ("neighbours too alike", "min_gene_distance"),
]


# ---------------------------------------------------------------------------
# Spec diff
# ---------------------------------------------------------------------------

def spec_diff(a, b, path: str = "") -> list[str]:
    """Parameter changes from asset spec a to b (dicts by key, everything else by value)."""
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k == "$schema":
                continue
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append(f"{p}: added {json.dumps(b[k])}")
            elif k not in b:
                out.append(f"{p}: removed (was {json.dumps(a[k])})")
            else:
                out += spec_diff(a[k], b[k], p)
        return out
    if a != b:
        out.append(f"{path}: {json.dumps(a)} -> {json.dumps(b)}")
    return out


# ---------------------------------------------------------------------------
# Review sheet
# ---------------------------------------------------------------------------

def _top(counts: dict, n: int = 3) -> str:
    tot = sum(counts.values()) or 1
    return ", ".join(f"{k} {round(100 * v / tot)}%" for k, v in
                     sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n])


def _counts(counts: dict, n: int = 4) -> str:
    return ", ".join(f"{k} {v}" for k, v in
                     sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n])


def numbers(man: dict, rep: dict, names: dict | None = None) -> dict:
    """The key numbers of a build, per city and per district (`names`: district id ->
    name)."""
    recs = man["buildings"]
    city = {"buildings": rep.get("buildings"),
            "triangles_m": round(rep["triangles"]["unique"] / 1e6, 2),
            "instances_m": round(rep["parts"]["instances"] / 1e6, 2),
            "heroes": sum(1 for r in recs.values() if r.get("hero")),
            "type_features": int(rep["stats"].get("type_features", 0)),
            "on_slopes": sum(1 for r in recs.values() if r.get("plinth_m", 0) >= 0.3)}
    by: dict[str, dict] = {}
    for r in recs.values():
        dn = (names or {}).get(r.get("district"), r.get("district")) or "-"
        d = by.setdefault(dn, {"n": 0, "era": {}, "system": {},
                                                     "generator": {}, "wear": 0.0})
        d["n"] += 1
        era = (r.get("material") or {}).get("era") or "-"
        d["era"][era] = d["era"].get(era, 0) + 1
        s = r["genes"].get("body.system") or "-"
        d["system"][s] = d["system"].get(s, 0) + 1
        g = r.get("generator") or "general"
        if g != "general":
            d["generator"][g] = d["generator"].get(g, 0) + 1
        d["wear"] += float(r["cpd"][3]) if len(r["cpd"]) > 3 else 0.0
    districts = {k: {"buildings": v["n"], "eras": _top(v["era"], 2),
                     "systems": _top(v["system"]), "generators": _counts(v["generator"]),
                     "wear": round(v["wear"] / max(v["n"], 1), 2)}
                 for k, v in sorted(by.items())}
    return {"city": city, "districts": districts}


def _checks(adir: Path) -> list[dict]:
    out = []
    for f in REPORTS:
        p = adir / f
        if not p.is_file():
            continue
        rep = json.loads(p.read_text(encoding="utf-8"))
        cks = rep.get("checks") or {}
        for c in (cks.values() if isinstance(cks, dict) else cks):
            if not c.get("ok", True):
                out.append({"report": f, "name": c.get("name"),
                            "first": [str(x) for x in (c.get("first") or [])[:3]]})
    return out


def _previews(adir: Path) -> list[tuple[str, str]]:
    out = []
    for pre, what in PREVIEWS:
        d = adir / pre
        if pre.endswith((".png", ".jpg")):
            if d.is_file():
                out.append((pre, what))
            continue
        for f in sorted(d.parent.glob(d.name + "*")) if d.parent.is_dir() else []:
            if f.suffix in (".jpg", ".png"):
                out.append((str(f.relative_to(adir)), what))
    return out


def review(build: str | Path, spec_path: str | Path | None = None,
           prev: str | Path | None = None) -> dict:
    """Write review.md and review.json into BUILD/assets; returns the review record."""
    bdir = Path(build)
    adir = bdir / "assets" if (bdir / "assets").is_dir() else bdir
    man = json.loads((adir / "manifest.json").read_text(encoding="utf-8"))
    rep = json.loads((adir / "asset_report.json").read_text(encoding="utf-8"))
    names = {}
    mp = adir.parent / "city_model.json"
    if mp.is_file():
        names = {d["id"]: d["name"] for d in
                 json.loads(mp.read_text(encoding="utf-8")).get("districts", [])}
    nums = numbers(man, rep, names)
    prev_rec = None
    if prev is not None:
        pd = Path(prev)
        pd = pd / "assets" if (pd / "assets").is_dir() else pd
        if (pd / "review.json").is_file():
            prev_rec = json.loads((pd / "review.json").read_text(encoding="utf-8"))
    rnd = (prev_rec["round"] + 1) if prev_rec else 1
    spec = None
    if spec_path is not None:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        if Path(spec_path).resolve() != (adir / "review_spec.json").resolve():
            shutil.copyfile(spec_path, adir / "review_spec.json")
    changes = spec_diff(prev_rec["spec"], spec) if prev_rec and spec is not None and \
        prev_rec.get("spec") is not None else []
    failed = _checks(adir)
    rec = {"round": rnd, "max_rounds": MAX_ROUNDS, "city": man["city"],
           "passed": not failed, "failed": failed, "numbers": nums, "spec": spec,
           "spec_changes": changes, "previews": [p for p, _ in _previews(adir)]}
    (adir / "review.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8",
                                      newline="\n")
    (adir / "review.md").write_text(_markdown(rec, prev_rec, _previews(adir)),
                                    encoding="utf-8", newline="\n")
    return rec


def _fmt(v) -> str:
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 10 else f"{v:.1f}"
    return str(v)


def _markdown(rec: dict, prev: dict | None, previews: list) -> str:
    L = [f"# Art direction (assets): {rec['city']}, round {rec['round']} of at most "
         f"{rec['max_rounds']}", ""]
    L.append("Checks: " + ("all passed." if rec["passed"] else
                           f"{len(rec['failed'])} failed (fix these first)."))
    for f in rec["failed"]:
        L.append(f"- `{f['name']}` ({f['report']}): " + "; ".join(f["first"]))
    L += ["", "## Spec changes since the last round", ""]
    L += [f"- `{c}`" for c in rec["spec_changes"]] or (
        ["- (first round)"] if prev is None else ["- none"])
    L += ["", "## City", "", "| Number | This round | Last round |", "|---|---|---|"]
    pc = prev["numbers"]["city"] if prev else {}
    for k, v in rec["numbers"]["city"].items():
        L.append(f"| {k} | {_fmt(v)} | {_fmt(pc.get(k))} |")
    L += ["", "## Districts", "",
          "| District | Buildings | Eras | Facade systems (body) | Type generators (buildings) "
          "| Wear |",
          "|---|---|---|---|---|---|"]
    pd = prev["numbers"]["districts"] if prev else {}
    for name, d in rec["numbers"]["districts"].items():
        was = pd.get(name, {})
        sy = d["systems"] + (f" (was {was['systems']})" if was.get("systems") not in
                             (None, d["systems"]) else "")
        we = _fmt(d["wear"]) + (f" (was {_fmt(was['wear'])})" if was.get("wear") not in
                                (None, d["wear"]) else "")
        L.append(f"| {name} | {d['buildings']} | {_fmt(d['eras'])} | {sy} | "
                 f"{_fmt(d['generators'])} | {we} |")
    L += ["", "## Previews to open", ""]
    for p, what in previews:
        L.append(f"- `{p}`: {what}")
    if not previews:
        L.append("- none yet: run `assetgen materials preview BUILD` (and `--eye/--target` "
                 "views of the landmarks and slopes)")
    L += ["", "## If something reads wrong, change the asset spec (never the code)", "",
          "| What you see | Spec parameters |", "|---|---|"]
    L += [f"| {a} | `{b}` |" for a, b in LEVERS]
    L += ["", "Stop when the checks pass and the previews match the prompt (and the concept "
              "image), or after the last round; say what is still off."]
    return "\n".join(L) + "\n"
