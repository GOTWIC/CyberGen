"""The atmos spec (scope section 5): a look preset plus art direction per district.

`atmos_spec.json` is written from the city prompt by a Claude Code session (an `atmosgen`
skill, AT6); it is never required: an empty spec is the `neon_rain` look with every
district's mood from its archetype, wealth and danger (decision 12.5: clean where wealthy
and safe, gritty in markets, old towns and poor districts). Structure lives here as pydantic
models; `fill` resolves every district's mood; `validate_spec` adds the checks that need a
built city (district and landmark names).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import presets as P

SPEC_VERSION = 1

Look = Literal[P.LOOKS]
Weather = Literal[P.WEATHERS]
Temp = Literal[tuple(P.TEMPS)]
LampClass = Literal[P.CLASSES]
Color = Annotated[str, Field(pattern=r"^#[0-9a-f]{6}$", description="#rrggbb, lowercase.")]
Weight = Annotated[float, Field(ge=0.0, le=100.0)]
Share = Annotated[float, Field(ge=0.0, le=1.0)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Palette(_Model):
    """The city's neon colors and their weights, and its light temperatures."""
    neon: dict[Color, Weight] = Field(default_factory=dict,
                                      description="Neon colors and weights (default AG15's "
                                                  "six accents, equal).")
    temps: dict[Temp, Weight] = Field(default_factory=dict,
                                      description="Weights of the light temperatures where "
                                                  "a mood leaves the choice open.")

    @model_validator(mode="after")
    def _check(self) -> Palette:
        for what, w in (("neon", self.neon), ("temps", self.temps)):
            if w and not any(v > 0 for v in w.values()):
                raise ValueError(f"{what}: at least one weight must be above 0")
        return self


class DistrictMood(_Model):
    """A district's mood, by its name in the city model. Every field left out comes from its
    archetype's mood (`presets.MOOD`) pulled by the district's wealth and danger."""
    lamp: LampClass | None = Field(None, description="The street lights' photometric class.")
    temp: Temp | None = Field(None, description="The street lights' temperature.")
    spill: Temp | None = Field(None, description="The shopfronts' light.")
    neon: Annotated[float, Field(ge=0.0, le=3.0)] | None = Field(
        None, description="Neon density: a multiplier of the signs that light.")
    palette: list[Color] = Field(default_factory=list, description="Neon colors here.")
    flicker: Share | None = Field(None, description="Share of lights that flicker.")
    broken: Share | None = Field(None, description="Share of lights that are out.")
    alleys: Share | None = Field(None, description="How dark the alleys are (0 lit as a "
                                                   "street, 1 as dark as allowed).")
    haze: Annotated[float, Field(ge=0.0, le=3.0)] | None = Field(
        None, description="A multiplier of the weather's fog here.")
    grit: Share | None = Field(None, description="0 clean, 1 gritty.")
    flood: Temp | None = Field(None, description="AT2: the white of its floods where a tower "
                                                 "has no crown LEDs (AG15).")
    floods: Share | None = Field(None, description="AT2: the share of its towers whose crowns "
                                                   "are flooded.")
    searchlights: Annotated[int, Field(ge=0, le=16)] | None = Field(
        None, description="AT2: searchlights on its tallest towers (two to a roof).")
    shadows: Color | None = Field(None, description="AT6: its post's shadow tint (default "
                                                    "its archetype's, `presets.DISTRICT_TINT`).")
    highlights: Color | None = Field(None, description="AT6: its post's highlight tint.")
    tint: Annotated[float, Field(ge=0.0, le=3.0)] | None = Field(
        None, description="AT6: a multiplier of its tints' strength (0: the look's alone).")


Mul = Annotated[float, Field(ge=0.0, le=3.0)]


class PostSpec(_Model):
    """AT6: art direction on the look's post (scope 6.5). Every field left out is the look's
    (`presets.POST`); the multipliers scale the night's and the day's values alike."""
    bloom: Mul | None = Field(None, description="A multiplier of the bloom.")
    flare: Mul | None = Field(None, description="A multiplier of the lens flares.")
    grain: Mul | None = Field(None, description="A multiplier of the film grain.")
    chromatic: Mul | None = Field(None, description="A multiplier of the chromatic "
                                                    "aberration.")
    vignette: Mul | None = Field(None, description="A multiplier of the vignette.")
    saturation: Mul | None = Field(None, description="A multiplier of the grade's saturation.")
    contrast: Mul | None = Field(None, description="A multiplier of the grade's contrast.")
    shadows: Color | None = Field(None, description="The grade's shadow tint (neon rain's "
                                                    "teal).")
    highlights: Color | None = Field(None, description="The grade's highlight tint (neon "
                                                       "rain's magenta).")
    tint: Mul | None = Field(None, description="A multiplier of the grade's tints' strength.")
    day_ev_bias: Annotated[float, Field(ge=-3.0, le=3.0)] | None = Field(
        None, description="EV added to the day's exposure (under 0 brighter).")
    overcast_comp: Share | None = Field(None, description="The share of the sun's light the "
                                                          "weather's clouds take that the "
                                                          "day's exposure gives back.")
    districts: bool = Field(True, description="A post per district (its mood: clean or "
                                              "gritty), blended by where the view stands.")


class LightLevels(_Model):
    """Illuminance targets by walkway class, lux (scope 8): [average, minimum]."""
    sidewalk: tuple[float, float] = P.LIGHT_LEVELS["sidewalk"]
    crosswalk: tuple[float, float] = P.LIGHT_LEVELS["crosswalk"]
    carriageway: tuple[float, float] = P.LIGHT_LEVELS["carriageway"]
    under_deck: tuple[float, float] = P.LIGHT_LEVELS["under_deck"]
    alley: tuple[float, float] = P.LIGHT_LEVELS["alley"]
    night_ev100: float | None = Field(None, description="The night's exposure (default the "
                                                        "look's reference_ev100).")


class LandmarkLights(_Model):
    """A landmark by its name in the city model: floods, crown and edge lights, searchlights."""
    floods: bool = Field(True, description="Uplights from its base up its shaft.")
    crown: bool = Field(True, description="Crown floods.")
    edges: bool = True
    searchlights: Annotated[int, Field(ge=0, le=8)] | None = Field(
        None, description="Searchlights on its roof (default by its kind: "
                          "`presets.LANDMARK_SEARCHLIGHTS`).")
    color: Color | None = Field(None, description="Its floods' color (default its crown "
                                                  "LEDs' accent, AG15).")


class Budgets(_Model):
    """Decision 12.6: the night pass at or under 16.7 ms p95, native 1440p on the PC."""
    night_p95_ms: float = P.BUDGETS["night_p95_ms"]
    live: Annotated[int, Field(ge=0, le=8192)] = P.BUDGETS["live"]
    shadowed: Annotated[int, Field(ge=0, le=256)] = P.BUDGETS["shadowed"]
    lights_per_cell: Annotated[int, Field(ge=0)] = P.BUDGETS["lights_per_cell"]


class SkySpec(_Model):
    """AT3: the sky and the time of day (scope 6.2). Every field left out is the look's or
    `presets.SKY`'s."""
    latitude_deg: Annotated[float, Field(ge=-66.0, le=66.0)] | None = Field(
        None, description="The city's latitude (default 35).")
    day_of_year: Annotated[int, Field(ge=1, le=365)] | None = Field(
        None, description="The day the sun and the moon stand for (default 172, midsummer "
                          "in the north).")
    moon_phase: Share | None = Field(None, description="0 new, 0.5 full (default 0.62).")
    day_hour: Annotated[float, Field(ge=0.0, lt=24.0)] | None = Field(
        None, description="The hour the play features' day goes to (default 16).")
    moon: Annotated[float, Field(ge=0.0, le=0.2)] | None = Field(
        None, description="A full moon's light as a share of the sun's (default the look's).")
    stars: Share | None = Field(None, description="How many stars a clear dark sky shows.")
    cloud_deck_m: Annotated[float, Field(ge=0.0, le=6000.0)] | None = Field(
        None, description="The cloud deck's height (0: none).")
    cloud_cover: Share | None = Field(None, description="The share of the sky it hides.")
    cloud_glow: Annotated[float, Field(ge=0.0, le=4.0)] | None = Field(
        None, description="A gain on the city's light it shows from below.")


class AtmosSpec(_Model):
    schema_ref: str | None = Field(None, alias="$schema")
    version: Literal[1] = SPEC_VERSION
    city: str | None = Field(None, description="City name (checked against the model).")
    preset: Look = Field(P.DEFAULTS["preset"], description="The look (decision 12.4: "
                                                           "neon_rain).")
    hour: Annotated[float, Field(ge=0.0, lt=24.0)] | None = Field(
        None, description="The start hour (default the look's).")
    weather: Weather | None = Field(None, description="The start weather (default the "
                                                      "look's).")
    wind_deg: Annotated[float, Field(ge=-360.0, le=360.0)] | None = Field(
        None, description="AT5: the wind's heading, degrees counterclockwise from east, the "
                          "way it blows (default 40: from the south-west); the rain leans "
                          "with it and its shadow lies downwind of every cover.")
    palette: Palette = Field(default_factory=Palette)
    districts: dict[str, DistrictMood] = Field(default_factory=dict)
    light_levels: LightLevels = Field(default_factory=LightLevels)
    landmarks: dict[str, LandmarkLights] = Field(default_factory=dict)
    budgets: Budgets = Field(default_factory=Budgets)
    sky: SkySpec = Field(default_factory=SkySpec, description="AT3: the sky and the time "
                                                              "of day.")
    post: PostSpec = Field(default_factory=PostSpec, description="AT6: the look's post and "
                                                                 "grade.")
    notes: str | None = Field(None, description="What the session inferred from the prompt.")


def dump(spec: AtmosSpec) -> dict:
    """JSON data of a spec (defaults kept, `$schema` left out)."""
    return json.loads(spec.model_dump_json(exclude={"schema_ref"}))


# ---------------------------------------------------------------------------
# Moods: a district's from its archetype, wealth and danger (decision 12.5)
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _r(v: float) -> float:
    r = round(v * 1000.0) / 1000.0
    return 0.0 if r == 0.0 else r


def mood(archetype: str | None, wealth: float | None, danger: float | None,
         given: DistrictMood | None = None, city_palette: list[str] | None = None) -> dict:
    """A district's resolved mood: its archetype's (`presets.MOOD`), grit, flicker, broken
    lights and alley darkness pulled up by danger and down by wealth (a wealthy safe district
    is clean whatever its kind; a poor dangerous one gritty), the spec's fields over it.
    AT2: its palette (the spec's district palette, else the city's, else its archetype's,
    `presets.PALETTES`), its floods (their white, the share of its towers flooded: up with
    wealth, down with grit) and its searchlights (`presets.FLOODS`)."""
    arch = archetype if archetype in P.MOOD else P.MOOD_DEFAULT
    base = dict(P.MOOD[arch])
    w = 0.5 if wealth is None else float(wealth)
    d = 0.5 if danger is None else float(danger)
    pull = 0.5 * (d - 0.5) - 0.4 * (w - 0.5)          # +0.45 poor and dangerous, -0.45 rich
    base["grit"] = _r(_clamp(base["grit"] + pull))
    # (dlss_lamps_flicker: ten times fewer flicker, `presets.FLICKER_SCALE`; to 0.0001)
    base["flicker"] = round(_clamp(base["flicker"] * P.FLICKER_SCALE * (0.5 + d)), 4) + 0.0
    base["broken"] = _r(_clamp(base["broken"] * (0.5 + d)))
    base["alleys"] = _r(_clamp(base["alleys"] + 0.3 * pull))
    base["haze"] = _r(base["haze"] * (1.0 + 0.3 * pull))
    base["palette"] = list(city_palette) if city_palette else list(P.PALETTES[arch])
    fl = P.FLOODS[arch]
    base["flood"] = fl["flood"]
    base["floods"] = _r(_clamp(fl["floods"] + 0.4 * (w - 0.5) - 0.3 * max(0.0, pull)))
    base["searchlights"] = int(fl["searchlights"])
    base["wealth"], base["danger"] = _r(w), _r(d)
    if given is not None:
        for k, v in given.model_dump(exclude_none=True).items():
            if k == "palette" and not v:
                continue
            base[k] = v
    return base


def fill(spec: AtmosSpec, districts: list[dict]) -> dict:
    """The spec resolved for a city: the look and weather, every district's mood by id
    (`districts`: the model's district rows), the palette's neon list."""
    look = dict(P.LOOK[spec.preset])
    # (AT3: the spec's sky over the look's: the moon, the stars, the cloud deck)
    for k in ("moon", "stars", "cloud_deck_m", "cloud_cover", "cloud_glow"):
        v = getattr(spec.sky, k)
        if v is not None:
            look[k] = float(v)
    hour = spec.hour if spec.hour is not None else look["hour"]
    weather = spec.weather or look["weather"]
    neon = spec.palette.neon or {c: 1.0 for c in P.NEON}
    # (the city's palette, when the spec gives one, for every district without its own: its
    # colors by weight, heaviest first, those weighted 0 left out)
    city_pal = [c for c, v in sorted(spec.palette.neon.items(), key=lambda kv: (-kv[1], kv[0]))
                if v > 0] if spec.palette.neon else None
    moods = {}
    for d in sorted(districts, key=lambda d: d["id"]):
        prm = d.get("params") or {}
        moods[d["id"]] = {"name": d.get("name"), "archetype": d.get("archetype"),
                          **mood(d.get("archetype"), prm.get("wealth"), prm.get("danger"),
                                 spec.districts.get(d.get("name") or ""), city_pal)}
    ev = spec.light_levels.night_ev100
    return {"preset": spec.preset, "hour": float(hour), "weather": weather,
            "look": look, "weather_state": dict(P.WEATHER[weather]),
            "night_ev100": float(look["reference_ev100"] if ev is None else ev),
            "neon": {k: float(v) for k, v in sorted(neon.items())},
            "moods": moods, "budgets": spec.budgets.model_dump(),
            "light_levels": spec.light_levels.model_dump(exclude={"night_ev100"}),
            "landmarks": {k: v.model_dump() for k, v in sorted(spec.landmarks.items())},
            "sky": {k: getattr(spec.sky, k) for k in ("latitude_deg", "day_of_year",
                                                       "moon_phase", "day_hour")},
            "wind_deg": spec.wind_deg, "post": spec.post.model_dump()}


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
    spec: AtmosSpec | None = None
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
    """Structure, then (with the city model's JSON) names: districts, landmarks, city."""
    res = Result()
    if not isinstance(data, dict):
        res.issues.append(Issue("error", "", "the atmos spec must be a JSON object"))
        return res
    try:
        spec = AtmosSpec.model_validate(data)
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
        landmarks = sorted(b.get("name") for b in model.get("buildings", [])
                           if b.get("landmark") and b.get("name"))
        for what, given, known in (("districts", spec.districts, districts),
                                   ("landmarks", spec.landmarks, landmarks)):
            for name in sorted(given):
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
    schema = AtmosSpec.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "atmosgen atmos spec"
    return schema
