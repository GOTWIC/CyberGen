"""The atmos plan's schema (scope sections 4.2 and 7): what `atmosgen plan` writes to
`BUILD/atmos/`.

- `atmos_plan.json` (`AtmosPlan`): the look, the start hour and weather, the sky, the
  schedules (every hour, decision 12.3), every district's mood, the tiers and budgets, an
  index of the light tiles, and the volumes, emitters and masks (AT4, AT5: their schemas are
  set here, their lists empty until then).
- `lights/<tile>.json` (`TileLights`): every light of a 256 m tile (citygen's `t+00+00`
  tiles), keyed by the id of what it hangs on.
- `unreal_contribution.atmos.json` (`Contribution`): layer 3 of the exporter's manifest.

Frames: citygen's (x east, y north, z up, meters); every z is absolute (over the ground
datum, M13's ground included). Every entry carries the hash of its own record (`hash`, the
sha256 of its canonical JSON without the hash, first 16 hex digits).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import presets as P

PLAN_VERSION = 1

Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Vec2 = Annotated[list[float], Field(min_length=2, max_length=2)]
RGB = Annotated[list[float], Field(min_length=3, max_length=3,
                                   description="Linear RGB, 0 to 1.")]
Hours = Annotated[list[float], Field(min_length=24, max_length=24,
                                     description="On share by hour, 0 to 23.")]
Shape = Literal["spot", "point", "rect"]
Tier = Literal["near", "mid"]
LightKind = Literal["street_light", "wall_light", "sign", "shop_sign", "spill", "soffit",
                    "flood", "aviation", "searchlight", "tunnel", "station", "high_mast",
                    "signal", "corner", "road", "alley", "underpass"]
# what a light hangs on (AT1): the city's own fixture (an M6 prop, an M20 sign, an M3
# shopfront, AG10's soffit fixture, AG7's tunnel strip), or one the plan asks of stage 2
# (scope 4.1, `emitters.py`'s third ask): a pole at a junction corner, along a highway or a
# service road, a mast arm on a traffic signal, a wall pack over an alley, a platform
# downlight under a station's canopy
Mount = Literal["prop", "sign", "facade", "soffit", "tunnel", "pole", "mast_arm", "wall",
                "canopy"]
ASKED = ("pole", "mast_arm", "wall", "canopy")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Light(_Model):
    """One light that casts light (scope 6.1)."""
    id: str = Field(description="`<owner id>.light` (a fixture's k-th light: `.light<k>`).")
    owner_id: str = Field(description="What it hangs on: an M6 prop, an M20 sign slot, an "
                                      "M3 building's unit, an M14 deck, ...")
    kind: LightKind
    cls: Literal[P.CLASSES] = Field(description="Its photometric class (`presets."
                                                "PHOTOMETRY`).")
    shape: Shape
    district_id: str | None = None
    tile: str
    pos: Vec3 = Field(description="Where the light is (m, absolute z): outside its fixture's "
                                  "mesh (a lamp's light hangs `drop_m` under its head, a "
                                  "face's `out_m` in front of it).")
    aim: Vec2 = Field(description="[yaw, pitch] degrees: yaw counterclockwise from east, "
                                  "pitch from the horizontal (-90 straight down).")
    size: Vec2 | None = Field(None, description="A rect light's [width, height] (m).")
    source_m: float = Field(0.0, description="A spot or point light's source radius (m).")
    cd: float = Field(description="Intensity (candela): a spot's or point's peak, a rect's "
                                  "luminance times its area.")
    color: RGB
    temp_k: int | None = Field(None, description="Its color temperature, when white.")
    reach_m: float = Field(description="Its attenuation radius (m).")
    cone: Vec2 | None = Field(None, description="A spot's [inner, outer] half angles (deg).")
    barn_deg: float | None = Field(None, description="A rect light's barn door angle.")
    shadow: bool = Field(False, description="May cast shadows in the near tier.")
    tier: Tier = Field("mid", description="The farthest tier it is live in: `near` lights "
                                          "only near the view (small, many), `mid` out "
                                          "to the mid radius.")
    schedule: str = Field(description="A name in the plan's `schedules`.")
    flicker: float = Field(0.0, ge=0.0, le=1.0, description="0 steady; else how deep it "
                                                            "flickers.")
    on: bool = Field(True, description="False: broken (kept in the plan, never lit).")
    source: Literal["derived", "assetgen"] = Field(
        "derived", description="Where its fixture's light came from: assetgen's emitter "
                               "record (the asks, section 4.1) or derived from citygen.")
    specular: float = Field(1.0, ge=0.0, le=1.0,
                            description="Its specular scale (AT1): 0 for a light standing in "
                                        "for a lit face (a sign's, a shopfront's), which a "
                                        "glossy surface reflects already.")
    mount: Mount = Field("prop", description="What it hangs on (AT1): the city's own "
                                             "fixture, or one the plan asks of stage 2 "
                                             "(pole, mast_arm, wall, canopy).")
    hash: str


class TileLights(_Model):
    version: Literal[1] = PLAN_VERSION
    city: str
    tile: str
    bounds: Annotated[list[float], Field(min_length=4, max_length=4)]
    lights: list[Light]


class TileIndex(_Model):
    tile: str
    file: str = Field(description="`lights/<tile>.json`, relative to the plan.")
    count: int
    kinds: dict[str, int]
    sha256: str = Field(description="sha256 of the tile file's bytes.")


class FogVolume(_Model):
    """AT4: a fog or smog volume (mist over water, smog over industry, haze under decks)."""
    id: str
    owner_id: str
    kind: Literal["mist", "smog", "haze", "tunnel_haze", "steam_bank"]
    tile: str
    center: Vec3
    extent: Vec3 = Field(description="Half sizes (m) of its box, along its yaw.")
    yaw_deg: float = 0.0
    density: float
    albedo: RGB
    schedule: str
    hash: str


class Emitter(_Model):
    """AT4: a steam or smoke emitter on its manhole, drain, vent, stall or chimney."""
    id: str
    owner_id: str
    kind: Literal["steam", "smoke", "exhaust", "cooking"]
    tile: str
    pos: Vec3
    rate: float
    schedule: str
    hash: str


class Mask(_Model):
    """AT5: a tile's rain shadow, wetness and puddle mask (0.5 m texels)."""
    tile: str
    file: str
    px: int
    sha256: str


class Sky(_Model):
    moon: float = Field(description="The moon's share of the sun's intensity.")
    stars: float
    cloud_deck_m: float = Field(description="The cloud deck's height (0: none).")
    cloud_glow: float = Field(description="How much of the city's upward light the deck "
                                          "shows.")
    upward_lm: float = Field(0.0, description="The plan's upward luminous flux (lm), for the "
                                              "deck's glow (AT3).")


class Tiers(_Model):
    near_m: float
    near_max: int
    mid_m: float
    mid_max: int
    far_m: float


class AtmosPlan(_Model):
    schema_ref: str | None = Field(None, alias="$schema")
    version: Literal[1] = PLAN_VERSION
    city: str
    model_sha256: str
    spec_sha256: str
    code: str = Field(description="atmosgen's version and code hash.")
    preset: Literal[P.LOOKS]
    hour: float
    weather: Literal[P.WEATHERS]
    night_ev100: float = Field(description="The exposure the lights are set for; a scene "
                                           "shown at another scales them by "
                                           "2^(EV_scene - night_ev100).")
    look: dict
    weather_state: dict
    sky: Sky
    schedules: dict[str, Hours]
    districts: dict[str, dict] = Field(description="Every district's resolved mood by id.")
    tiers: Tiers
    budgets: dict
    tiles: list[TileIndex]
    volumes: list[FogVolume] = Field(default_factory=list)
    emitters: list[Emitter] = Field(default_factory=list)
    masks: list[Mask] = Field(default_factory=list)
    counts: dict[str, int]
    sources: dict[str, int] = Field(description="Lights by source: derived or assetgen "
                                                "(the asks met).")
    checks: dict = Field(default_factory=dict,
                         description="AT1: the lux check's result (`lux.check`): `ok` and per "
                                     "walkway class its points, average, share under the "
                                     "minimum and targets. The exporter imports a plan "
                                     "only when it passed (scope 8: not delivered "
                                     "otherwise).")


class ContributionEntry(_Model):
    key: str = Field(description="`atmos` (the controller), `atmos.lights.<tile>` (a tile's "
                                 "light spawner); AT3 adds entries that replace "
                                 "`lighting.sun`, `lighting.sky` and `lighting.atmosphere`.")
    kind: Literal["controller", "tile_lights", "volume", "emitter"]
    tile: str | None = None
    file: str
    hash: str
    count: int = 0
    replaces: list[str] = Field(default_factory=list)


class Contribution(_Model):
    """`BUILD/atmos/unreal_contribution.atmos.json`: layer 3 of the manifest (keys by M10's
    ids; a later stage's entry replaces an earlier one's for the same key)."""
    version: Literal[1] = 1
    stage: Literal[3] = 3
    city: str
    plan: str
    plan_sha256: str
    plugin: Literal["CityGenAtmos"] = "CityGenAtmos"
    entries: list[ContributionEntry]


def json_schema(model=AtmosPlan, title: str = "atmosgen atmos plan") -> dict:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = title
    return schema


SCHEMAS = {"atmos_plan": (AtmosPlan, "atmosgen atmos plan"),
           "tile_lights": (TileLights, "atmosgen tile lights"),
           "contribution": (Contribution, "atmosgen unreal contribution")}
