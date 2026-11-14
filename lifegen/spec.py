"""The life spec (scope section 5): who lives in each district, how busy its hours are, what
people wear, which vehicles drive, the budgets and the reactions.

`life_spec.json` is written from the city prompt by a Claude Code session (a `lifegen` skill,
from LG1 on); it is never required: an empty spec is every district by its archetype
(`presets.py`), wealth and danger. Structure lives here as pydantic models; `fill` resolves
every district; `validate_spec` adds the checks that need a built city (district names,
transit lines).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import presets as P

SPEC_VERSION = 1

Share = Annotated[float, Field(ge=0.0, le=1.0)]
Mul = Annotated[float, Field(ge=0.0, le=5.0)]
Weight = Annotated[float, Field(ge=0.0, le=100.0)]
Group = Literal[P.GROUPS]
Hour = Annotated[int, Field(ge=0, lt=24)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DistrictPopulation(_Model):
    """A district's people, by its name in the city model. Every field left out is its
    archetype's (`presets.MIX`, `DAY_SHAPE`)."""
    busy: Mul | None = Field(None, description="A multiplier of M11's crowd densities here.")
    mix: Annotated[list[float], Field(min_length=3, max_length=3)] | None = Field(
        None, description="Residents, workers, visitors (shares, normalized).")
    shape: Annotated[list[float], Field(min_length=24, max_length=24)] | None = Field(
        None, description="The day's shape, a weight per hour (normalized per hour band, so "
                          "every band keeps M11's density).")

    @model_validator(mode="after")
    def _check(self) -> DistrictPopulation:
        for what, v in (("mix", self.mix), ("shape", self.shape)):
            if v is not None and (min(v) < 0.0 or not any(x > 0 for x in v)):
                raise ValueError(f"{what}: weights at 0 or more, at least one above 0")
        return self


class DistrictStyle(_Model):
    """What people wear in a district (scope 6.2), by its name."""
    groups: dict[Group, Weight] = Field(default_factory=dict,
                                        description="Fashion groups and their weights.")
    cyberware: Share | None = Field(None, description="0 none, 1 everyone heavily augmented.")
    wear: Share | None = Field(None, description="0 new, 1 worn out.")


class Styles(_Model):
    palette: list[Annotated[str, Field(pattern=r"^#[0-9a-f]{6}$")]] = Field(
        default_factory=list, description="The city's clothing accents (default its neon).")
    districts: dict[str, DistrictStyle] = Field(default_factory=dict)


class Fleet(_Model):
    """AG18's vehicles (decision 6): a model's weight is its district's from the parked cars'
    table (`assetgen/parked/table.py`) times the multipliers here."""
    weights: dict[str, Annotated[float, Field(ge=0.0, le=10.0)]] = Field(
        default_factory=dict, description="Per model, a multiplier everywhere (0 leaves it "
                                          "out of the city).")
    districts: dict[str, dict[str, Annotated[float, Field(ge=0.0, le=10.0)]]] = Field(
        default_factory=dict, description="Per district name, per model multipliers.")
    busy: Mul = Field(1.0, description="A multiplier of M11's vehicle densities.")


class Transit(_Model):
    """Service per line by its name: headways by hour band (minutes)."""
    headway_min: dict[str, Annotated[list[float], Field(min_length=5, max_length=5)]] = Field(
        default_factory=dict)


class Busy(_Model):
    busy: Mul = Field(1.0, description="A multiplier of how busy (LG7).")


class Budgets(_Model):
    """Decision 12.7 (2026-11-13): 20 ms p95 at native 2560 x 1440 on the PC."""
    frame_p95_ms: float = P.BUDGETS["frame_p95_ms"]
    people_view: Annotated[int, Field(ge=0, le=20000)] = P.BUDGETS["people_view"]
    vehicles_view: Annotated[int, Field(ge=0, le=5000)] = P.BUDGETS["vehicles_view"]
    view_m: Annotated[float, Field(gt=0.0, le=2000.0)] = P.BUDGETS["view_m"]
    full_detail: Annotated[list[int], Field(min_length=2, max_length=2)] = \
        Field(default_factory=lambda: list(P.BUDGETS["full_detail"]))


class Reactions(_Model):
    """Decision 12.8: stepping aside and looking; fleeing and gathering are a later hook."""
    step_aside: bool = P.REACTIONS["step_aside"]
    look: bool = P.REACTIONS["look"]
    flee: bool = P.REACTIONS["flee"]
    gather: bool = P.REACTIONS["gather"]


class Spike(_Model):
    """LG0's spike: plain stand-ins on one district's walkways and a few cars on its lanes."""
    district: str | None = Field(None, description="The district by name (default the one "
                                                   "with the most buildings: the "
                                                   "benchmark's walk).")
    hour: Hour = P.SPIKE["hour"]
    people: Annotated[int, Field(ge=0, le=20000)] | None = Field(
        None, description="Default the plan's people on its streets at the hour, at most "
                          "the budget's.")
    cars: Annotated[int, Field(ge=0, le=2000)] = P.SPIKE["cars"]


class LifeSpec(_Model):
    schema_ref: str | None = Field(None, alias="$schema")
    version: Literal[1] = SPEC_VERSION
    city: str | None = Field(None, description="City name (checked against the model).")
    population: dict[str, DistrictPopulation] = Field(default_factory=dict)
    styles: Styles = Field(default_factory=Styles)
    fleet: Fleet = Field(default_factory=Fleet)
    transit: Transit = Field(default_factory=Transit)
    air: Busy = Field(default_factory=Busy)
    water: Busy = Field(default_factory=Busy)
    budgets: Budgets = Field(default_factory=Budgets)
    reactions: Reactions = Field(default_factory=Reactions)
    spike: Spike = Field(default_factory=Spike)
    notes: str | None = Field(None, description="What the session inferred from the prompt.")


# ---------------------------------------------------------------------------
# Filling: every district resolved
# ---------------------------------------------------------------------------

def _r(v: float, k: int = 4) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def shape(raw) -> list[float]:
    """A day's shape normalized per hour band: each band's hours average 1."""
    out = [0.0] * P.HOURS
    for _, a, b in P.HOUR_BANDS:
        vals = [max(0.0, float(raw[h])) for h in range(a, b)]
        mean = sum(vals) / len(vals)
        for h, v in zip(range(a, b), vals):
            out[h] = _r(v / mean) if mean > 0 else 0.0
    return out


def _arch(a: str | None, table: dict) -> str:
    return a if a in table else P.MIX_DEFAULT


def district(d: dict, spec: LifeSpec, cars: list[str]) -> dict:
    """A district resolved: its population mix and day, its style, its fleet's weights."""
    from assetgen.parked import table as T
    name = d.get("name") or ""
    arch = _arch(d.get("archetype"), P.MIX)
    prm = d.get("params") or {}
    from citygen.presets import ARCHETYPES
    pre = ARCHETYPES.get(d.get("archetype") or "")
    wealth = float(prm.get("wealth", getattr(pre, "wealth", 0.5)))
    danger = float(prm.get("danger", getattr(pre, "danger", 0.5)))
    pop = spec.population.get(name) or DistrictPopulation()
    mix = list(pop.mix) if pop.mix else list(P.MIX[arch])
    tot = sum(mix)
    groups, cyber, wear = P.STYLE[_arch(d.get("archetype"), P.STYLE)]
    ds = spec.styles.districts.get(name) or DistrictStyle()
    g = dict(ds.groups) if ds.groups else dict(groups)
    gt = sum(g.values()) or 1.0
    # (wear up with danger, down with wealth; cyberware up with wealth)
    wear_v = ds.wear if ds.wear is not None else \
        min(1.0, max(0.0, wear + 0.3 * (danger - 0.5) - 0.3 * (wealth - 0.5)))
    cyber_v = ds.cyberware if ds.cyberware is not None else \
        min(1.0, max(0.0, cyber + 0.2 * (wealth - 0.5)))
    w = T.weights(d.get("archetype"), wealth, danger, cars, spec.fleet.weights or None)
    for m, k in (spec.fleet.districts.get(name) or {}).items():
        if m in w:
            w[m] = w[m] * k
    w = {m: _r(v) for m, v in sorted(w.items()) if v > 0}
    return {"name": name, "archetype": d.get("archetype"), "wealth": _r(wealth),
            "danger": _r(danger), "busy": _r(pop.busy if pop.busy is not None else 1.0),
            "mix": {"residents": _r(mix[0] / tot), "workers": _r(mix[1] / tot),
                    "visitors": _r(mix[2] / tot)},
            "shape": shape(pop.shape if pop.shape else P.DAY_SHAPE.get(arch, P.DAY_SHAPE[
                P.MIX_DEFAULT])),
            "style": {"groups": {k: _r(v / gt) for k, v in sorted(g.items()) if v > 0},
                      "cyberware": _r(cyber_v), "wear": _r(wear_v)},
            "fleet": w}


def fill(spec: LifeSpec, districts: list[dict], cars: list[str]) -> dict:
    """The spec resolved for a city: every district by id, the budgets, reactions, fleet
    multiplier, transit headways."""
    return {"districts": {d["id"]: district(d, spec, cars)
                          for d in sorted(districts, key=lambda d: d["id"])},
            "budgets": spec.budgets.model_dump(), "reactions": spec.reactions.model_dump(),
            "fleet_busy": _r(spec.fleet.busy), "air_busy": _r(spec.air.busy),
            "water_busy": _r(spec.water.busy),
            "transit": {k: [_r(x) for x in v] for k, v in sorted(spec.transit.headway_min
                                                                   .items())},
            "palette": list(spec.styles.palette), "spike": spec.spike.model_dump()}


def dump(spec: LifeSpec) -> dict:
    return json.loads(spec.model_dump_json(exclude={"schema_ref"}))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    level: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.path}: {self.message}" if self.path else \
            f"{self.level}: {self.message}"


@dataclass
class Result:
    spec: LifeSpec | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def ok(self) -> bool:
        return self.spec is not None and not self.errors


def _loc(loc) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def validate_spec(data: Any, model: dict | None = None) -> Result:
    """Structure, then (with the city model's JSON) names: districts, transit lines, city."""
    res = Result()
    if not isinstance(data, dict):
        res.issues.append(Issue("error", "", "the life spec must be a JSON object"))
        return res
    try:
        spec = LifeSpec.model_validate(data)
    except ValidationError as e:
        for err in e.errors():
            res.issues.append(Issue("error", _loc(err["loc"]), err["msg"]))
        return res
    res.spec = spec
    if model is not None:
        import difflib
        if spec.city is not None and spec.city != model.get("name"):
            res.issues.append(Issue("warning", "city", f"'{spec.city}' is not the model's "
                                                       f"city '{model.get('name')}'"))
        districts = sorted(d.get("name") or "" for d in model.get("districts", []))
        lines = sorted(t.get("name") or "" for t in model.get("transit_lines", []))
        named = [("population", sorted(spec.population), districts),
                 ("styles.districts", sorted(spec.styles.districts), districts),
                 ("fleet.districts", sorted(spec.fleet.districts), districts),
                 ("transit.headway_min", sorted(spec.transit.headway_min), lines)]
        if spec.spike.district is not None:
            named.append(("spike.district", [spec.spike.district], districts))
        for what, given, known in named:
            for name in given:
                if name not in known:
                    near = difflib.get_close_matches(name, known, n=1)
                    hint = f" (did you mean '{near[0]}'?)" if near else ""
                    res.issues.append(Issue("error", f"{what}.{name}",
                                            f"no such name in the city model{hint}"))
    return res


def load_spec(path: str | Path | None, model: dict | None = None) -> Result:
    """A spec file (None: the empty spec, every default)."""
    if path is None:
        return validate_spec({}, model)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        res = Result()
        res.issues.append(Issue("error", "", f"not valid JSON: {e}"))
        return res
    return validate_spec(data, model)


def json_schema() -> dict:
    schema = LifeSpec.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "lifegen life spec"
    return schema
