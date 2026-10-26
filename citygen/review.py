"""The art-direction loop (scope 9): a Claude Code session reviews a build's previews against
the spec (and the concept image), changes spec parameters (never code) and builds again, a few
rounds at most. citygen makes no model call: this module only prepares each round's review
sheet and tells the rounds apart.

`citygen review <out_dir> --spec SPEC [--prev PREV_OUT_DIR]` writes `review.md` and
`review.json` into the build folder: the checks, the key numbers per district, what changed
in the spec and in the numbers since the previous round, the previews to open, and the spec
parameters that answer what the reviewer may see. `citygen spec diff A B` lists the parameter
changes between two specs.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

MAX_ROUNDS = 3
PREVIEWS = [
    ("preview_map.png", "water, districts and primary roads: placement, shares, bridges"),
    ("preview_detail.png", "four 400 m insets: street patterns, junctions, lots"),
    ("preview_heights.png", "footprints by height: skyline, landmarks, district grain"),
    ("preview_massing.png", "isometric massing: complexes, megasites, skybridges"),
    ("preview_transit.png", "transit lines, stations, supports, portals"),
    ("preview_props.png", "street level: lights, trees, parked cars, clutter"),
    ("preview_elevated.png", "road levels: viaducts, interchanges, columns"),
    ("render_top.jpg", "Blender blockout from above"),
]
# what a reviewer may see -> the spec parameters that change it
LEVERS = [
    ("a district on the wrong side of another or of the water",
     "districts[].placement (north_of, coast, along_river, on_island, separated_by)"),
    ("a district too big or too small",
     "districts[].area_share"),
    ("too much or too little water between districts",
     "water.district_separation, water.boundary_water_share, districts[].water_separation"),
    ("a river entering or leaving in the wrong place",
     "water.rivers[].from / to (with `at`), meander, width_m"),
    ("an island missing, too small or in the wrong spot",
     "water.islands[].position, setting, area_km2; water.coast.sea_share"),
    ("the wrong highway shape or exits",
     "highways.pattern, highways.exits"),
    ("not enough or too much viaduct",
     "highways.elevated_share"),
    ("the same street grid everywhere, or the wrong angle",
     "districts[].street_pattern, grid_angle_deg, block_size_m"),
    ("a skyline too flat or too uniform",
     "districts[].height_m, landmarks, complexes"),
    ("too few canals, or canals in the wrong district",
     "districts[].waterways (style, density, named)"),
    ("streets too clean or too gritty, too dark or too green",
     "districts[].grime, neon, greenery"),
    ("a transit line doubling back or missing a stop",
     "transit.lines[].route (order matters for fast modes), mode"),
    ("a megasite in the wrong place or the wrong size",
     "districts[].megasites[] (kind, area_km2, position)"),
    ("a traced district in the wrong spot or turned",
     "water.islands[].position, pinned.rotation_deg"),
]


# ---------------------------------------------------------------------------
# Spec diff
# ---------------------------------------------------------------------------

def _key(item) -> str | None:
    return item.get("name") if isinstance(item, dict) else None


def spec_diff(a, b, path: str = "") -> list[str]:
    """Parameter changes from spec a to spec b (lists of named items matched by name)."""
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append(f"{p}: added {json.dumps(b[k])}")
            elif k not in b:
                out.append(f"{p}: removed (was {json.dumps(a[k])})")
            else:
                out += spec_diff(a[k], b[k], p)
        return out
    if isinstance(a, list) and isinstance(b, list) and a and b and \
            all(_key(x) for x in a + b):
        ka = {_key(x): x for x in a}
        kb = {_key(x): x for x in b}
        for name in [_key(x) for x in a] + [_key(x) for x in b if _key(x) not in ka]:
            p = f"{path}[{name}]"
            if name not in kb:
                out.append(f"{p}: removed")
            elif name not in ka:
                out.append(f"{p}: added")
            else:
                out += spec_diff(ka[name], kb[name], p)
        if [_key(x) for x in a if _key(x) in kb] != [_key(x) for x in b if _key(x) in ka]:
            out.append(f"{path}: order changed")
        return out
    if a != b:
        out.append(f"{path}: {json.dumps(a)} -> {json.dumps(b)}")
    return out


# ---------------------------------------------------------------------------
# Review sheet
# ---------------------------------------------------------------------------

def numbers(rep: dict) -> dict:
    """The key numbers of a build report, per city and per district."""
    st = rep["stats"]
    city = {
        "water_share": st.get("water_share"),
        "boundary_on_water": st.get("boundary_on_water"),
        "road_km": round(sum(st.get("road_km", {}).values()), 2),
        "bridges": st.get("bridges"),
    }
    el = st.get("elevated") or {}
    if el:
        city.update({"elevated_km": el.get("elevated_km"),
                     "interchanges": sum(el.get("interchanges", {}).values())})
    if st.get("buildings"):
        city.update({"buildings": st["buildings"]["count"],
                     "tallest_m": st["buildings"]["tallest_m"]})
    if st.get("transit"):
        city["transit_km"] = st["transit"]["km"]
    if st.get("props"):
        city["instances"] = st["props"]["instances"]
    by_b = (st.get("buildings") or {}).get("by_district", {})
    opens = (st.get("local") or {}).get("open_share_by_district", {})
    districts = {}
    for d in st["districts"]:
        b = by_b.get(d["name"], {})
        districts[d["name"]] = {
            "archetype": d["archetype"], "share": d["share"], "target": d["target"],
            "median_m": b.get("median"), "max_m": b.get("max"), "far": b.get("far"),
            "open_share": opens.get(d["name"])}
    return {"city": city, "districts": districts}


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 10 else f"{v:.1f}"
    return str(v)


def review(out_dir: str | Path, spec_path: str | Path | None = None,
           prev: str | Path | None = None) -> dict:
    """Write review.md and review.json into out_dir; returns the review record."""
    out = Path(out_dir)
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    nums = numbers(rep)
    prev_rec = None
    if prev is not None and (Path(prev) / "review.json").is_file():
        prev_rec = json.loads((Path(prev) / "review.json").read_text(encoding="utf-8"))
    rnd = (prev_rec["round"] + 1) if prev_rec else 1
    spec = None
    if spec_path is not None:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        if Path(spec_path).resolve() != (out / "review_spec.json").resolve():
            shutil.copyfile(spec_path, out / "review_spec.json")
    changes = spec_diff(prev_rec["spec"], spec) if prev_rec and spec is not None and \
        prev_rec.get("spec") is not None else []
    failed = [{"id": c["id"], "failures": c["failures"][:3]} for c in rep["checks"]
              if not c["passed"]]
    rec = {"round": rnd, "max_rounds": MAX_ROUNDS, "name": rep["name"],
           "passed": rep["passed"], "failed": failed, "numbers": nums, "spec": spec,
           "spec_changes": changes,
           "previews": [p for p, _ in PREVIEWS if (out / p).is_file()]}
    (out / "review.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    (out / "review.md").write_text(_markdown(rec, prev_rec), encoding="utf-8")
    return rec


def _markdown(rec: dict, prev: dict | None) -> str:
    L = [f"# Art direction: {rec['name']}, round {rec['round']} of at most "
         f"{rec['max_rounds']}", ""]
    L.append("Checks: " + ("all passed." if rec["passed"] else
                           f"{len(rec['failed'])} failed (fix these first)."))
    for f in rec["failed"]:
        L.append(f"- `{f['id']}`: " + "; ".join(f["failures"]))
    L += ["", "## Spec changes since the last round", ""]
    L += [f"- `{c}`" for c in rec["spec_changes"]] or (
        ["- (first round)"] if prev is None else ["- none"])
    L += ["", "## City", "", "| Number | This round | Last round |", "|---|---|---|"]
    pc = prev["numbers"]["city"] if prev else {}
    for k, v in rec["numbers"]["city"].items():
        L.append(f"| {k} | {_fmt(v)} | {_fmt(pc.get(k))} |")
    L += ["", "## Districts", "",
          "| District | Archetype | Share (target) | Median / max height m | FAR | Open share |",
          "|---|---|---|---|---|---|"]
    pd = prev["numbers"]["districts"] if prev else {}
    for name, d in rec["numbers"]["districts"].items():
        was = pd.get(name, {})
        dh = ""
        if was.get("median_m") is not None and d.get("median_m") is not None and \
                was["median_m"] != d["median_m"]:
            dh = f" (was {_fmt(was['median_m'])})"
        L.append(f"| {name} | {d['archetype']} | {_fmt(d['share'])} ({_fmt(d['target'])}) | "
                 f"{_fmt(d['median_m'])}{dh} / {_fmt(d['max_m'])} | {_fmt(d['far'])} | "
                 f"{_fmt(d['open_share'])} |")
    L += ["", "## Previews to open", ""]
    for p, what in PREVIEWS:
        if p in rec["previews"]:
            L.append(f"- `{p}`: {what}")
    L += ["", "## If something reads wrong, change the spec (never the code)", "",
          "| What you see | Spec parameters |", "|---|---|"]
    L += [f"| {a} | `{b}` |" for a, b in LEVERS]
    L += ["", "Stop when the checks pass and the previews match the prompt (and the concept "
              "image), or after the last round; say what is still off."]
    return "\n".join(L) + "\n"
