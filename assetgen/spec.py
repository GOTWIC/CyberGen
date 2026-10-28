"""Asset spec schema (scope 4.2): art direction per era, district, owner and landmark.

`asset_spec.json` is written by a Claude Code session through the `assetgen` skill from the
city prompt; it is never required (an empty spec is all era presets). Structure lives here
as pydantic models; `fill` merges the era presets in; `validate_spec` adds the checks that
need a built city (district, owner and landmark names).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import presets as P

SPEC_VERSION = 1

Era = Literal[P.ERAS]
FacadeSystem = Literal[P.FACADE_SYSTEMS]
Crown = Literal[P.CROWNS]
Script = Literal[P.SCRIPTS]
Color = Annotated[str, Field(pattern=r"^#[0-9a-f]{6}$", description="#rrggbb, lowercase.")]
Weight = Annotated[float, Field(ge=0.0, le=100.0)]
Range = Annotated[tuple[float, float], Field(description="[low, high]")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _weights_ok(w: dict | None, what: str) -> None:
    if w is not None and w and not any(v > 0 for v in w.values()):
        raise ValueError(f"{what}: at least one weight must be above 0")


def _range_ok(r, lo: float, hi: float, what: str) -> None:
    if r is not None and not (lo <= r[0] <= r[1] <= hi):
        raise ValueError(f"{what}: [low, high] within [{lo:g}, {hi:g}], low <= high")


class EraStyle(_Model):
    """One era's palette. Every field left out comes from the era preset."""
    systems: dict[FacadeSystem, Weight] | None = Field(
        None, description="Facade systems and their weights.")
    palette: Annotated[list[Color], Field(min_length=1, max_length=12)] | None = None
    crowns: Annotated[list[Crown], Field(min_length=1)] | None = None
    signage_scripts: dict[Script, Weight] | None = None
    window_to_wall: Range | None = Field(None, description="Window-to-wall ratio range.")
    bay_m: Range | None = Field(None, description="Bay width range, meters.")
    wear: Annotated[float, Field(ge=0.0, le=2.0)] | None = Field(
        None, description="Base wear (grime, stains, replaced panels), 0 to 2.")

    @model_validator(mode="after")
    def _check(self) -> EraStyle:
        _weights_ok(self.systems, "systems")
        _weights_ok(self.signage_scripts, "signage_scripts")
        _range_ok(self.window_to_wall, 0.0, 0.95, "window_to_wall")
        _range_ok(self.bay_m, 0.6, 12.0, "bay_m")
        return self


class DistrictStyle(_Model):
    """Art direction for one district, by its name in the city spec."""
    era: Era | None = Field(None, description="Era for every building of the district "
                                              "(default: each building's own).")
    wear: Annotated[float, Field(ge=0.0, le=3.0)] = Field(1.0, description="Wear multiplier.")
    ad_density: Annotated[float, Field(ge=0.0, le=3.0)] = Field(
        1.0, description="Signage and ad density multiplier.")
    neon_palette: list[Color] = Field(default_factory=list)
    systems: dict[FacadeSystem, Weight] = Field(
        default_factory=dict, description="Weights added to the era's systems here.")
    signage_scripts: dict[Script, Weight] | None = Field(
        None, description="Replaces the era's scripts in this district.")

    @model_validator(mode="after")
    def _check(self) -> DistrictStyle:
        _weights_ok(self.signage_scripts, "signage_scripts")
        return self


class OwnerStyle(_Model):
    """A property owner's brand (`Property.owner` in the city model)."""
    brand_colors: list[Color] = Field(default_factory=list)
    logo: str | None = Field(None, description="Repo path of an SVG logo (written by a "
                                               "session, never downloaded).")
    facade_bias: dict[FacadeSystem, Weight] = Field(
        default_factory=dict, description="Weights added to the era's systems for this "
                                          "owner's buildings.")


class LandmarkStyle(_Model):
    """A landmark by its name in the city model."""
    brief: str = Field("", description="Art direction in words, for the hero generator.")
    palette: list[Color] = Field(default_factory=list)
    crown: Crown | None = None


class AssetSpec(_Model):
    schema_ref: str | None = Field(None, alias="$schema")
    version: Literal[1] = SPEC_VERSION
    city: str | None = Field(None, description="City name (checked against the model).")
    uniqueness: Literal["U0", "U1", "U2", "U3"] = Field(
        P.DEFAULTS["uniqueness"], description="Section 11 levels; decision 13.2.")
    hero_uniqueness: Literal["U1", "U2", "U3"] = Field(
        P.DEFAULTS["hero_uniqueness"], description="Landmarks and hero buildings.")
    min_gene_distance: Annotated[int, Field(ge=1, le=12)] = Field(
        P.DEFAULTS["min_gene_distance"],
        description="k: discrete genes two buildings outside one complex differ in (5.1.1).")
    share_parts: bool = Field(P.DEFAULTS["share_parts"],
                              description="Share a part between buildings when their "
                                          "quantized parameters coincide (5.1.4).")
    texel_density_px_m: Annotated[int, Field(ge=64, le=2048)] = Field(
        P.DEFAULTS["texel_density_px_m"], description="Within reach of the street.")
    texel_density_upper_px_m: Annotated[int, Field(ge=32, le=2048)] = Field(
        P.DEFAULTS["texel_density_upper_px_m"], description="Above the street band.")
    eras: dict[Era, EraStyle] = Field(default_factory=dict)
    districts: dict[str, DistrictStyle] = Field(default_factory=dict)
    owners: dict[str, OwnerStyle] = Field(default_factory=dict)
    landmarks: dict[str, LandmarkStyle] = Field(default_factory=dict)
    notes: str | None = Field(None, description="What the session inferred from the prompt.")


def fill(spec: AssetSpec) -> AssetSpec:
    """Every era complete: the preset with the spec's fields over it."""
    eras = {}
    for name in P.ERAS:
        base = dict(P.ERA_PRESETS[name])
        given = spec.eras.get(name)
        if given is not None:
            for k, v in given.model_dump(exclude_none=True).items():
                base[k] = v
        eras[name] = EraStyle.model_validate(base)
    return spec.model_copy(update={"eras": eras})


def dump(spec: AssetSpec) -> dict:
    """JSON data of a spec (defaults kept, `$schema` left out), sorted for hashing."""
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
    spec: AssetSpec | None = None
    filled: AssetSpec | None = None
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


def _loc(loc) -> str:
    out = ""
    for part in loc:
        if part == "[key]":
            out += " (key)"
        else:
            out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def validate_spec(data: Any, model=None) -> Result:
    """Structure, then (with a city model) names: districts, owners, landmarks, city."""
    res = Result()
    if not isinstance(data, dict):
        res.issues.append(Issue("error", "", "the asset spec must be a JSON object"))
        return res
    try:
        spec = AssetSpec.model_validate(data)
    except ValidationError as e:
        for err in e.errors():
            res.issues.append(Issue("error", _loc(err["loc"]), err["msg"]))
        return res
    res.spec = spec
    if model is not None:
        _check_names(spec, model, res)
    res.filled = fill(spec)
    return res


def _check_names(spec: AssetSpec, model, res: Result) -> None:
    import difflib
    if spec.city is not None and spec.city != model.name:
        res.issues.append(Issue("warning", "city",
                                f"'{spec.city}' is not the model's city '{model.name}'"))
    districts = sorted(d.name for d in model.districts)
    owners = sorted({p.owner for p in model.properties})
    landmarks = sorted(b.name for b in model.buildings if b.landmark and b.name)
    for what, given, known in (("districts", spec.districts, districts),
                               ("owners", spec.owners, owners),
                               ("landmarks", spec.landmarks, landmarks)):
        for name in sorted(given):
            if name not in known:
                near = difflib.get_close_matches(name, known, n=1)
                hint = f" (did you mean '{near[0]}'?)" if near else ""
                res.issues.append(Issue("error", f"{what}.{name}",
                                        f"no such name in the city model{hint}"))


def load_spec(path: str | Path, model=None) -> Result:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        res = Result()
        res.issues.append(Issue("error", "", f"not valid JSON: {e}"))
        return res
    return validate_spec(data, model)


def json_schema() -> dict:
    schema = AssetSpec.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "assetgen asset spec"
    return schema


# ---------------------------------------------------------------------------
# Overrides (scope 4.3)
# ---------------------------------------------------------------------------

class AssetOverrides(_Model):
    """`asset_overrides.json` beside the spec, on M10 stable ids."""
    schema_ref: str | None = Field(None, alias="$schema")
    version: Literal[1] = 1
    pin: list[str] = Field(default_factory=list, description="Keep these assets as they are "
                                                             "even if their briefs change.")
    style: dict[str, dict[str, Any]] = Field(default_factory=dict,
                                             description="Genome genes forced per id.")
    replace: dict[str, str] = Field(default_factory=dict,
                                    description="A hand-made model (repo path) per id.")
    regenerate: dict[str, int] = Field(default_factory=dict, description="A new seed per id.")


def overrides_by_id(ov: AssetOverrides | None) -> dict[str, dict]:
    """{id: {pin, style, replace, regenerate}} for every id an override names."""
    if ov is None:
        return {}
    out: dict[str, dict] = {}
    for i in ov.pin:
        out.setdefault(i, {})["pin"] = True
    for what in ("style", "replace", "regenerate"):
        for i, v in getattr(ov, what).items():
            out.setdefault(i, {})[what] = v
    return out


def load_overrides(path: str | Path) -> AssetOverrides:
    return AssetOverrides.model_validate_json(Path(path).read_text(encoding="utf-8"))
