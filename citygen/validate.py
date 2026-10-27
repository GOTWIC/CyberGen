"""Spec validation: structure (pydantic), cross-references and consistency, then defaults.

`validate_spec(data)` returns a `Result` with the parsed spec, the filled spec and a list of
issues. Errors make the spec invalid; warnings are reported but do not fail validation.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from . import presets, spec as S
from .defaults import fill_defaults


@dataclass
class Issue:
    level: str  # "error" or "warning"
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.path}: {self.message}" if self.path else \
            f"{self.level}: {self.message}"


@dataclass
class Result:
    spec: S.CitySpec | None = None
    filled: S.CitySpec | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return self.filled is not None and not self.errors


class SpecError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))


# ---------------------------------------------------------------------------
# Structural errors (pydantic) -> readable messages
# ---------------------------------------------------------------------------

def _all_field_names() -> list[str]:
    names: set[str] = set()
    for obj in vars(S).values():
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == S.__name__:
            for fname, f in obj.model_fields.items():
                names.add(f.alias or fname)
    return sorted(names)


FIELD_NAMES = _all_field_names()


def _suggest(word: str, options: Iterable[str]) -> str:
    opts = list(options)
    lower = {o.lower(): o for o in opts}
    hit = difflib.get_close_matches(str(word).lower(), list(lower), n=1, cutoff=0.7)
    return f" (did you mean '{lower[hit[0]]}'?)" if hit else ""


def _path(loc: tuple, data: Any) -> str:
    """('districts', 2, 'placement') -> 'districts[2] "Old Town".placement'."""
    out = ""
    node = data
    for part in loc:
        if isinstance(part, str) and ("[" in part or part.startswith("function-")):
            continue  # pydantic union / validator markers
        if isinstance(part, int):
            out += f"[{part}]"
            node = node[part] if isinstance(node, list) and part < len(node) else None
            if isinstance(node, dict) and isinstance(node.get("name"), str):
                out += f' "{node["name"]}"'
        else:
            out += ("." if out else "") + part
            node = node.get(part) if isinstance(node, dict) else None
    return out


def structural_issues(err: ValidationError, data: Any) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for e in err.errors():
        loc = tuple(e["loc"])
        kind = e["type"]
        if kind == "extra_forbidden":
            key = str(loc[-1])
            path = _path(loc[:-1], data)
            msg = f"unknown field '{key}'" + _suggest(key, FIELD_NAMES)
        elif kind == "missing":
            path = _path(loc[:-1], data)
            msg = f"missing required field '{loc[-1]}'"
        else:
            path = _path(loc, data)
            msg = e["msg"]
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            if kind == "literal_error" and isinstance(e.get("input"), str):
                expected = (e.get("ctx") or {}).get("expected", "")
                options = [o.strip(" '") for o in expected.replace(" or ", ", ").split(",")]
                msg = f"'{e['input']}' is not allowed; expected one of {expected}" + \
                    _suggest(e["input"], options)
        if (path, msg) not in seen:
            seen.add((path, msg))
            issues.append(Issue("error", path, msg))
    # Union members each report a literal error; keep one message per path when merged.
    return _merge_literal_unions(issues)


def _merge_literal_unions(issues: list[Issue]) -> list[Issue]:
    by_path: dict[str, list[Issue]] = {}
    for i in issues:
        by_path.setdefault(i.path, []).append(i)
    out = []
    for path, group in by_path.items():
        lit = [i for i in group if "is not allowed; expected one of" in i.message]
        if len(lit) > 1:
            word = lit[0].message.split("'")[1]
            options: list[str] = []
            for i in lit:
                body = i.message.split("expected one of ", 1)[1].split(" (did you mean")[0]
                options += [o.strip(" '") for o in body.replace(" or ", ", ").split(",")]
            msg = f"'{word}' is not allowed; expected one of " + \
                ", ".join(f"'{o}'" for o in options) + _suggest(word, options)
            out.append(Issue("error", path, msg))
            out += [i for i in group if i not in lit]
        else:
            out += group
    return out


# ---------------------------------------------------------------------------
# Semantic checks
# ---------------------------------------------------------------------------

def _dpath(i: int, d: S.District) -> str:
    return f'districts[{i}] "{d.name}"'


class Names:
    """Every name the spec defines, by category, plus a lookup to the owning district."""

    def __init__(self, spec: S.CitySpec):
        self.districts = {d.name: i for i, d in enumerate(spec.districts)}
        self.places: dict[str, int] = {}
        self.megasites: dict[str, int] = {}
        for i, d in enumerate(spec.districts):
            for p in d.places:
                self.places.setdefault(p.name, i)
            for m in d.megasites or []:
                if m.name:
                    self.megasites.setdefault(m.name, i)
        self.islands = {isl.name for isl in spec.water.islands}
        self.rivers = {r.name for r in spec.water.rivers or []}
        self.branches = {b for r in spec.water.rivers or [] for b in r.branch_names}
        self.hubs = set(spec.transit.hubs or [])

    def locatable(self) -> set[str]:
        return set(self.districts) | set(self.places) | set(self.megasites) | self.islands

    def district_of(self, ref: str) -> int | None:
        for table in (self.districts, self.places, self.megasites):
            if ref in table:
                return table[ref]
        return None


def _ref_issue(path: str, ref: str, what: str, options: Iterable[str]) -> Issue:
    return Issue("error", path, f"'{ref}' is not {what}" + _suggest(ref, options))


def check_names(spec: S.CitySpec) -> list[Issue]:
    issues = []
    seen: dict[str, str] = {}

    def claim(name: str, path: str, allow_same: str | None = None) -> None:
        key = name.lower()
        if key in seen and not (allow_same and seen[key] == allow_same):
            issues.append(Issue("error", path, f"name '{name}' is already used by {seen[key]}"))
        else:
            seen.setdefault(key, path)

    for i, d in enumerate(spec.districts):
        claim(d.name, _dpath(i, d))
    for i, d in enumerate(spec.districts):
        for j, p in enumerate(d.places):
            claim(p.name, f"{_dpath(i, d)}.places[{j}]")
        for j, m in enumerate(d.megasites or []):
            # A megasite may share its own district's name (the site is the district).
            if m.name and m.name != d.name:
                claim(m.name, f"{_dpath(i, d)}.megasites[{j}]")
        for j, lm in enumerate(d.landmarks):
            if lm.name:
                claim(lm.name, f"{_dpath(i, d)}.landmarks[{j}]")
    for j, isl in enumerate(spec.water.islands):
        # A district may be named after the island it sits on.
        same = next((_dpath(i, d) for i, d in enumerate(spec.districts)
                     if d.name == isl.name and d.placement.on_island == isl.name), None)
        claim(isl.name, f"water.islands[{j}]", allow_same=same)
    for j, r in enumerate(spec.water.rivers or []):
        claim(r.name, f"water.rivers[{j}]")
        for b in r.branch_names:
            claim(b, f"water.rivers[{j}].branch_names")
    for j, b in enumerate(spec.water.bridges.named):
        claim(b.name, f"water.bridges.named[{j}]")
    for j, h in enumerate(spec.highways.named):
        claim(h.name, f"highways.named[{j}]")
    for j, line in enumerate(spec.transit.lines):
        claim(line.name, f"transit.lines[{j}]")
    return issues


def check_water(spec: S.CitySpec, n: Names) -> list[Issue]:
    issues = []
    w = spec.water
    rivers = {r.name: r for r in w.rivers or []}
    for j, r in enumerate(w.rivers or []):
        path = f"water.rivers[{j}]"
        if r.to in ("sea", "bay"):
            if r.to == "bay" and w.coast and w.coast.form not in ("bay", "crescent"):
                issues.append(Issue("warning", path + ".to",
                                    f"'bay' with coast form '{w.coast.form}'; treated as 'sea'"))
        elif r.to in S.DIRECTIONS:
            if r.to == r.from_:
                issues.append(Issue("error", path + ".to",
                                    f"river enters and leaves on the same edge '{r.to}'"))
        elif r.to == r.name:
            issues.append(Issue("error", path + ".to", "a river cannot flow into itself"))
        elif r.to not in rivers:
            issues.append(_ref_issue(path + ".to", r.to,
                                     "'sea', 'bay', a map edge or a river name", rivers))
    # Tributary cycles.
    for r in w.rivers or []:
        seen = {r.name}
        cur = r
        while cur.to in rivers:
            cur = rivers[cur.to]
            if cur.name in seen:
                issues.append(Issue("error", "water.rivers",
                                    f"tributary loop through '{r.name}' and '{cur.name}'; "
                                    "one river must reach the sea or a map edge"))
                break
            seen.add(cur.name)
    for j, isl in enumerate(w.islands):
        if isl.river and isl.river not in rivers:
            issues.append(_ref_issue(f"water.islands[{j}].river", isl.river, "a river", rivers))
        if isl.setting == "delta" and isl.river in rivers and rivers[isl.river].delta_branches < 1:
            issues.append(Issue("error", f"water.islands[{j}]",
                                f"delta island needs river '{isl.river}' to have delta_branches"))
    ends = n.locatable() | {f"{d}_exit" for d in S.DIRECTIONS}
    for j, b in enumerate(w.bridges.named):
        for ref in b.connects:
            if ref not in ends:
                issues.append(_ref_issue(f"water.bridges.named[{j}].connects", ref,
                                         "a district, place, megasite, island or exit", ends))
        if b.connects[0] == b.connects[1]:
            issues.append(Issue("error", f"water.bridges.named[{j}].connects",
                                "a bridge must connect two different ends"))
        if b.crosses and b.crosses not in rivers and b.crosses not in n.branches \
                and b.crosses not in ("sea", "bay"):
            issues.append(_ref_issue(f"water.bridges.named[{j}].crosses", b.crosses,
                                     "a river, delta branch, 'sea' or 'bay'", rivers))
    return issues


def check_districts(spec: S.CitySpec, n: Names) -> list[Issue]:
    issues = []
    loc = n.locatable()
    sea_side = spec.water.coast.side if spec.water.coast else None
    islands = {i.name: i for i in spec.water.islands}
    for i, d in enumerate(spec.districts):
        dp = _dpath(i, d)
        pl = d.placement
        for direction, ref in pl.relations():
            path = f"{dp}.placement.{direction}_of"
            if ref == d.name:
                issues.append(Issue("error", path, "a district cannot be placed relative to itself"))
            elif ref not in loc:
                issues.append(_ref_issue(path, ref, "a district, place, megasite or island", loc))
            elif n.district_of(ref) == i:
                issues.append(Issue("error", path,
                                    f"'{ref}' is inside this district; place districts relative "
                                    "to other districts"))
        for ref in pl.adjacent_to:
            if ref not in loc or ref == d.name:
                issues.append(_ref_issue(f"{dp}.placement.adjacent_to", ref,
                                         "another district, place, megasite or island", loc))
        if pl.along_river and pl.along_river not in n.rivers:
            issues.append(_ref_issue(f"{dp}.placement.along_river", pl.along_river, "a river",
                                     n.rivers))
        if pl.on_island:
            if pl.on_island not in islands:
                issues.append(_ref_issue(f"{dp}.placement.on_island", pl.on_island, "an island",
                                         islands))
            if pl.coast is False:
                issues.append(Issue("error", f"{dp}.placement",
                                    "on_island contradicts coast: false (islands are coastal)"))
            if pl.edge == "center":
                issues.append(Issue("error", f"{dp}.placement",
                                    "on_island contradicts edge: 'center'"))
        if pl.separated_by and pl.separated_by not in S.BoundaryKind.__args__ \
                and pl.separated_by not in n.rivers:
            issues.append(_ref_issue(f"{dp}.placement.separated_by", pl.separated_by,
                                     "a boundary kind or river name",
                                     list(S.BoundaryKind.__args__) + sorted(n.rivers)))
        if pl.coast is False and pl.edge == sea_side and sea_side:
            issues.append(Issue("error", f"{dp}.placement",
                                f"edge '{pl.edge}' is the sea side but coast is false"))
        for j, site in enumerate(d.megasites or []):
            mp = presets.MEGASITES[site.kind]
            if (site.coast or mp.coast) and pl.coast is False:
                issues.append(Issue("error", f"{dp}.megasites[{j}]",
                                    f"{site.kind} needs the coast but the district has coast: false"))
            if mp.edge_or_coast and pl.coast is False and pl.edge in (None, "center"):
                issues.append(Issue("error", f"{dp}.megasites[{j}]",
                                    f"{site.kind} must be on the coast or a city edge; set "
                                    "placement.coast or placement.edge"))
        if d.water_separation == "water_required" and not any(
                r for r in spec.water.rivers or []) and not pl.on_island:
            issues.append(Issue("error", f"{dp}.water_separation",
                                "water_required but the city has no rivers and the district "
                                "is not on an island"))
    issues += _placement_cycles(spec, n)
    return issues


def _placement_cycles(spec: S.CitySpec, n: Names) -> list[Issue]:
    """A north_of B north_of A (directly or through a chain) cannot be laid out."""
    issues = []
    for axis, comp in (("north-south", 1), ("east-west", 0)):
        edges: dict[int, set[int]] = {}
        for i, d in enumerate(spec.districts):
            for direction, ref in d.placement.relations():
                v = presets.DIRECTION_VECTORS[direction][comp]
                j = n.district_of(ref)
                if j is None or j == i or abs(v) < 1e-6:
                    continue
                a, b = (i, j) if v > 0 else (j, i)  # a is further north/east than b
                edges.setdefault(a, set()).add(b)
        cycle = _find_cycle(edges)
        if cycle:
            names = " > ".join(spec.districts[k].name for k in cycle)
            issues.append(Issue("error", "districts",
                                f"placement relations form a loop on the {axis} axis: {names}"))
    return issues


def _find_cycle(edges: dict[int, set[int]]) -> list[int] | None:
    state: dict[int, int] = {}
    stack: list[int] = []

    def visit(u: int) -> list[int] | None:
        state[u] = 1
        stack.append(u)
        for v in sorted(edges.get(u, ())):
            if state.get(v) == 1:
                return stack[stack.index(v):] + [v]
            if v not in state:
                found = visit(v)
                if found:
                    return found
        stack.pop()
        state[u] = 2
        return None

    for u in sorted(edges):
        if u not in state:
            found = visit(u)
            if found:
                return found
    return None


def check_shares(spec: S.CitySpec) -> list[Issue]:
    given = [d.area_share for d in spec.districts if d.area_share is not None]
    missing = len(spec.districts) - len(given)
    total = sum(given)
    if total > 1.01:
        return [Issue("error", "districts",
                      f"area_share values sum to {total:.3f}; they are fractions of the land area "
                      "and must sum to at most 1")]
    if missing and total > 0.97:
        return [Issue("error", "districts",
                      f"area_share values already sum to {total:.3f}, leaving no land for the "
                      f"{missing} district(s) without a share")]
    if not missing and total < 0.95:
        return [Issue("error", "districts",
                      f"area_share values sum to {total:.3f}; when every district has a share "
                      "they must sum to 1 (0.95 to 1.01 is normalized)")]
    return []


def check_transit(spec: S.CitySpec, n: Names) -> list[Issue]:
    issues = []
    stops = n.locatable() | n.hubs
    for j, hub in enumerate(spec.transit.hubs or []):
        if hub not in n.locatable():
            issues.append(_ref_issue(f"transit.hubs[{j}]", hub,
                                     "a district, place or megasite (add it as a place or "
                                     "megasite in a district)", n.locatable()))
    for j, line in enumerate(spec.transit.lines):
        path = f'transit.lines[{j}] "{line.name}"'
        for ref in line.route:
            if S.EXIT_RE.match(ref):
                continue
            if ref not in stops:
                issues.append(_ref_issue(path + ".route", ref,
                                         "a district, place, megasite, island, hub or exit", stops))
    for j, h in enumerate(spec.highways.named):
        for ref in h.route:
            if not S.EXIT_RE.match(ref) and ref not in n.locatable():
                issues.append(_ref_issue(f"highways.named[{j}].route", ref,
                                         "a district, place, megasite, island or exit",
                                         n.locatable()))
    for j, ref in enumerate(spec.highways.tunnels.under):
        if ref not in n.districts:
            issues.append(_ref_issue(f"highways.tunnels.under[{j}]", ref, "a district",
                                     n.districts))
    for j, b in enumerate(spec.water.bridges.named):
        if b.tunnel and b.kind == "pedestrian":
            issues.append(Issue("error", f"water.bridges.named[{j}].tunnel",
                                "a pedestrian crossing has no tunnel (tubes carry roads)"))
    tr = spec.terrain
    if tr is not None:
        from .terrain import DIRS

        places = set(n.districts) | set(DIRS)
        for j, h in enumerate(tr.hills):
            if h.at not in places:
                issues.append(_ref_issue(f"terrain.hills[{j}].at", h.at,
                                         "a district, a direction or 'center'", places))
        for j, r in enumerate(tr.ridges):
            for key, ref in (("from", r.from_), ("to", r.to)):
                if ref not in places:
                    issues.append(_ref_issue(f"terrain.ridges[{j}].{key}", ref,
                                             "a district, a direction or 'center'", places))
        for j, c in enumerate(tr.cliffs):
            if c.district not in n.districts:
                issues.append(_ref_issue(f"terrain.cliffs[{j}].district", c.district,
                                         "a district", n.districts))
        for j, ref in enumerate(tr.flat):
            if ref not in n.districts:
                issues.append(_ref_issue(f"terrain.flat[{j}]", ref, "a district", n.districts))
    return issues


def _district_area_km2(spec: S.CitySpec, d: S.District) -> float:
    w, h = spec.size_km
    sea = spec.water.coast.sea_share or presets.COAST_SEA_SHARE[spec.water.coast.form]
    islands = sum(i.area_km2 for i in spec.water.islands if i.setting in ("offshore", "nearshore"))
    return (w * h * (1 - sea) + islands) * (d.area_share or 0)


def check_filled(spec: S.CitySpec, n: Names) -> list[Issue]:
    """Consistency checks that need defaults filled (areas, heights, links)."""
    issues = []
    stops_by_mode: dict[str, set[int | None]] = {}
    for line in spec.transit.lines:
        for ref in line.route:
            stops_by_mode.setdefault(line.mode, set()).add(n.district_of(ref))
    for i, d in enumerate(spec.districts):
        dp = _dpath(i, d)
        area = _district_area_km2(spec, d)
        site_area = sum(s.area_km2 or 0 for s in d.megasites or [])
        if site_area > 0.9 * area:
            issues.append(Issue("error", f"{dp}.megasites",
                                f"megasites need {site_area:.2f} km2 but the district gets about "
                                f"{area:.2f} km2 (share {d.area_share:.3f} of the land); raise "
                                "area_share or shrink the sites"))
        elif site_area > 0.6 * area:
            issues.append(Issue("warning", f"{dp}.megasites",
                                f"megasites fill {site_area / area:.0%} of the district"))
        if d.placement.on_island:
            isl = next((x for x in spec.water.islands if x.name == d.placement.on_island), None)
            if isl and not (0.5 * isl.area_km2 <= area <= 2.0 * isl.area_km2):
                issues.append(Issue("warning", f"{dp}.area_share",
                                    f"district area is about {area:.2f} km2 but island "
                                    f"'{isl.name}' is {isl.area_km2:g} km2"))
        p = presets.ARCHETYPES[d.archetype]
        lo, hi = d.height_m
        if hi > 1.5 * p.height_m[1] or lo < 0.5 * p.height_m[0]:
            issues.append(Issue("warning", f"{dp}.height_m",
                                f"[{lo:g}, {hi:g}] is far from the {d.archetype} preset "
                                f"{p.height_m[0]:g} to {p.height_m[1]:g} m"))
        for site in d.megasites or []:
            mp = presets.MEGASITES[site.kind]
            if mp.needs_transit and not any(
                    i in stops_by_mode.get(m, ()) for m in mp.needs_transit):
                issues.append(Issue("warning", f"{dp}.megasites",
                                    f"{site.kind} '{site.name}' should be served by a "
                                    f"{' or '.join(mp.needs_transit)} line (scope 5.7)"))
            if site.height_limit_m and hi > site.height_limit_m:
                issues.append(Issue("warning", f"{dp}.height_m",
                                    f"max height {hi:g} m exceeds the {site.kind} height limit "
                                    f"{site.height_limit_m:g} m; buildings near it will be capped"))
    for hub in spec.transit.hubs or []:
        count = sum(1 for line in spec.transit.lines
                    if hub in line.route or n.district_of(hub) in
                    {n.district_of(r) for r in line.route})
        if spec.transit.lines and count < 2:
            issues.append(Issue("warning", "transit.hubs",
                                f"hub '{hub}' is served by {count} line(s); hubs are interchanges"))
    if not spec.transit.lines:
        issues.append(Issue("warning", "transit.lines", "no transit lines; only roads will be built"))
    return issues


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def validate_spec(data: Any) -> Result:
    result = Result()
    try:
        spec = S.CitySpec.model_validate(data)
    except ValidationError as err:
        result.issues = structural_issues(err, data)
        return result
    result.spec = spec
    result.issues += check_shares(spec)
    filled = fill_defaults(spec)
    names = Names(filled)
    result.issues += check_names(filled)
    result.issues += check_water(filled, names)
    result.issues += check_districts(filled, names)
    result.issues += check_transit(filled, names)
    if not result.errors:
        result.issues += check_filled(filled, names)
    result.filled = filled
    return result


def load_json(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SpecError([Issue("error", str(path),
                               f"not valid JSON: {e.msg} at line {e.lineno} column {e.colno}")])


def load_spec(path: str | Path) -> Result:
    return validate_spec(load_json(path))


def dump_spec(spec: S.CitySpec) -> str:
    data = spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
