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
Tier = Literal["near", "mid", "high"]
# (AT2 adds `neon`, a neon band's spill, and `runway`, an airfield's ground lights; `flood`,
# `aviation`, `searchlight` and `high_mast` were set down in AT0)
LightKind = Literal["street_light", "wall_light", "sign", "shop_sign", "spill", "soffit",
                    "flood", "aviation", "searchlight", "tunnel", "station", "high_mast",
                    "signal", "corner", "road", "alley", "underpass", "neon", "runway"]
# what a light hangs on (AT1): the city's own fixture (an M6 prop, an M20 sign, an M3
# shopfront, AG10's soffit fixture, AG7's tunnel strip), or one the plan asks of stage 2
# (scope 4.1, `emitters.py`'s third ask): a pole at a junction corner, along a highway or a
# service road, a mast arm on a traffic signal, a wall pack over an alley, a platform
# downlight under a station's canopy
# AT2 asks four more of stage 2 (`emitters.py`'s fourth ask): `roof` (a flood or searchlight
# on a roof or setback, a flood's outrigger), `beacon` (an aviation light's lens on a roof
# corner or a mast's tip), `mast` (a port's or an apron's high mast, a crane boom's flood),
# `ground` (an airfield light in the pavement)
Mount = Literal["prop", "sign", "facade", "soffit", "tunnel", "pole", "mast_arm", "wall",
                "canopy", "roof", "beacon", "mast", "ground"]
ASKED = ("pole", "mast_arm", "wall", "canopy", "roof", "beacon", "mast", "ground")


class Anim(BaseModel):
    """AT2: how a light moves or blinks (the runtime animates it from the world's time)."""
    model_config = ConfigDict(extra="forbid")
    mode: Literal["blink", "sweep"] = Field(description="`blink` on for `amount` of each "
                                                        "period (an aviation light); `sweep` "
                                                        "its yaw swinging `amount` degrees "
                                                        "either way (a searchlight).")
    period_s: float
    amount: float
    phase: float = Field(ge=0.0, lt=1.0, description="Its share of a period at time 0 (a "
                                                     "building's lights blink together).")


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
                                             "(pole, mast_arm, wall, canopy; AT2 roof, "
                                             "beacon, mast, ground).")
    anim: Anim | None = Field(None, description="AT2: a blink or a sweep.")
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
    """AT4: a fog or smog volume (mist over water, smog over industry, haze under decks and
    in tunnels): an ellipsoid (Unreal's local fog volume), its half sizes along its yaw."""
    id: str = Field(description="`<owner id>.<kind><k>`.")
    owner_id: str = Field(description="Its water body, district, megasite, deck or tunnel.")
    kind: Literal["mist", "smog", "haze", "tunnel_haze", "steam_bank"]
    district_id: str | None = None
    tile: str
    center: Vec3 = Field(description="Its middle (m, absolute z).")
    extent: Vec3 = Field(description="Half sizes (m) of its ellipsoid: along its yaw, across, "
                                     "up.")
    yaw_deg: float = 0.0
    density: float = Field(description="Extinction at its middle (1/m, along its long axis).")
    floor: float = Field(0.0, ge=0.0, le=1.0, description="The share of it that is height "
                                                          "fog, dense at its foot.")
    phase_g: float = Field(0.4, ge=0.0, lt=1.0, description="Its scattering's direction.")
    glow: float = Field(0.0, ge=0.0, description="How much of the city's light it shows "
                                                 "where no live light reaches it (its "
                                                 "emissive, of its albedo).")
    albedo: RGB
    schedule: str
    hash: str


class Emitter(_Model):
    """AT4: a steam or smoke plume on its manhole, drain, vent, roof unit, stall or chimney
    (the runtime draws it as rising cards, scope 4.2)."""
    id: str = Field(description="`<owner id>.<mount>` (a fixture's k-th: `.<mount><k>`).")
    owner_id: str = Field(description="What it rises from: an AG7 road piece, an M3 "
                                      "building, an M6 prop, an M9 vent.")
    kind: Literal["steam", "smoke", "exhaust", "cooking"]
    mount: Literal["manhole", "drain", "vent", "roof", "stall", "chimney", "stove"] = "manhole"
    district_id: str | None = None
    tile: str
    pos: Vec3 = Field(description="Where it leaves its source (m, absolute z).")
    width_m: float = Field(1.0, description="The plume's width at its source.")
    rise_m: float = Field(5.0, description="How high it rises before it fades.")
    rate: float = Field(description="Its opacity, 0 to 1.")
    color: RGB = Field(default_factory=lambda: [0.8, 0.8, 0.8],
                       description="Its albedo (linear).")
    schedule: str
    source: Literal["derived", "assetgen"] = Field(
        "derived", description="assetgen: read from what stage 2 drew (AG7's manholes and "
                               "drains); derived: from citygen (a fixture asked of stage 2 "
                               "where it draws none: a chimney).")
    hash: str


class Air(_Model):
    """AT4: the air (scope 6.3): the height and volumetric fog of the look and weather, the
    light shafts (each light kind's share in the volumetric fog), the live sets and the
    engine settings the controller runs with."""
    fog_density: float = Field(description="The height fog's density (Unreal's).")
    fog_falloff: float
    fog_start_m: float
    fog_albedo: RGB = Field(description="The volumetric fog's albedo (linear).")
    fog_extinction: float = Field(description="The volumetric fog's extinction scale.")
    fog_view_m: float = Field(description="The volumetric fog's reach.")
    phase_g: float
    fog_hours: Hours = Field(description="The fog's density by hour, a share of "
                                         "`fog_density` (mist forms after dusk).")
    scatter: dict[str, float] = Field(description="Volumetric scattering by light kind "
                                                  "(light shafts; 0 none).")
    beam_fog_gain: float = Field(description="A searchlight beam's glow grows by this times "
                                             "the fog's share (AT2's beams kept).")
    max_volumes: int
    volume_range_m: float
    emitter_range_m: float
    puffs: dict[str, int] = Field(description="Cards per plume by emitter kind.")
    steam_gain: float = Field(10.0, description="The plumes' opacity gain.")
    volume_glow: float = Field(0.15, description="The fog volumes' glow by night (their "
                                                 "emissive's scale).")
    cvars: dict[str, str] = Field(default_factory=dict,
                                  description="Engine settings the controller applies while "
                                              "it runs (the budget's room, AT4).")
    counts: dict[str, int] = Field(default_factory=dict)


class Mask(_Model):
    """AT5: a tile's mask (`masks/<tile>.png`, 0.5 m texels, row 0 the north edge, RGBA): red
    the cover (the lowest underside over the texel of what shelters it, absolute: the plan's
    `weather.cover` datum plus red times its step; 0 open sky), green the puddles (0 none to
    255 the deepest), blue the drip band under a low cover's edge, alpha the surface's gloss
    when wet."""
    tile: str
    file: str
    px: int
    sha256: str


class Drip(_Model):
    """AT5: a piece of a low cover's dripping edge (`drips/<tile>.json`): the runtime's drip
    streaks fall from it to the ground."""
    id: str = Field(description="`<cover id>.drip<k>`.")
    owner_id: str = Field(description="Its cover: an M6 awning or bus shelter, an M14 deck, a "
                                      "raised road's piece, a canopy.")
    kind: Literal["awning", "deck", "road", "canopy", "shelter"]
    tile: str
    a: Vec2
    b: Vec2
    z_m: float = Field(description="The edge's height (absolute).")
    ground_m: float = Field(description="The ground under its middle (absolute).")
    rate: float = Field(description="How fast it drips, a share of the rain's.")
    hash: str


class TileDrips(_Model):
    """AT5: `drips/<tile>.json`: a tile's drip lines."""
    version: Literal[1] = 1
    city: str
    tile: str
    drips: list[Drip]


class DripTile(_Model):
    tile: str
    file: str
    count: int
    kinds: dict[str, int]
    sha256: str


class WeatherState(_Model):
    """AT5: one weather state as the runtime blends to it."""
    rain: float = Field(description="The rain's rate (0 to 1).")
    streak: float = Field(description="A streak's length, a share of the rain's (drizzle's "
                                      "short).")
    drops: float = Field(description="The share of the rain cards that fall.")
    wetness: float = Field(description="How wet the open surfaces get.")
    puddles: float = Field(description="How full the puddles get (a share of their depth).")
    cover: float = Field(description="The cloud deck's cover.")
    volumes: float = Field(description="A gain on the fog volumes (mist, smog).")
    gust: float = Field(description="The wind's gusts, a share of its speed.")
    wind_m_s: float
    fog_density: float = Field(description="The height fog's density (the look's).")
    fog_falloff: float
    fog_extinction: float = Field(description="The volumetric fog's extinction scale.")
    fog_albedo: RGB


class Weather(_Model):
    """AT5: the weather (scope 6.4, `weather.py`): the states, the rain's age, the wind, the
    masks' frame and the drips."""
    start: Literal[P.WEATHERS]
    states: dict[str, WeatherState]
    times: dict[str, float] = Field(description="transition_s (a state change), wet_s and "
                                                "dry_s (the open surfaces), fill_s and "
                                                "drain_s (the puddles): the runtime's "
                                                "seconds.")
    wind: dict[str, float] = Field(description="heading_deg (counterclockwise from east, the "
                                               "way it blows), lean (the rain's drift over "
                                               "its fall), shift_max_m, cover_max_m, "
                                               "gale_m_s (MPC_CityGen's Wind 1).")
    texel_m: float
    extent: Annotated[list[float], Field(min_length=4, max_length=4,
                                         description="[x0, y0, x1, y1]: the masks' tiles.")]
    cover: dict[str, float] = Field(description="The cover channel's datum (z0_m) and step "
                                                "(step_m).")
    gloss: dict[str, float] = Field(description="The gloss when wet by surface class.")
    drip_tiles: list[DripTile]
    live: dict[str, float] = Field(description="What the runtime keeps near the view.")
    counts: dict[str, int]
    stats: dict


class Moon(_Model):
    """AT3: the moon (`sky.moon_at`): it trails the sun by `lag_h`, its declination mirrored
    by its phase."""
    phase: float = Field(description="0 new, 0.5 full.")
    lag_h: float = Field(description="How far it trails the sun (hours): 24 times the phase.")
    declination_deg: float
    lit: float = Field(description="Its lit fraction (its light scales by it).")
    share: float = Field(description="A full moon's light as a share of the sun's (the look's).")
    color: str = Field(description="Its light's color (#rrggbb).")
    disk_nits: float = Field(description="Its disk's luminance in the scene's frame (cd/m2 at "
                                         "the night's exposure).")
    disk_deg: float = Field(description="Its disk's angular diameter.")
    rise: Vec2 = Field(description="Its light fades in between these elevations (degrees).")
    cloud: float = Field(description="The share of its light the deck's cover takes.")


class Glow(_Model):
    """AT3: the cloud deck's underside lit by the city (`sky.glow`): a raster of its
    luminance, linear RGB, square-root encoded in an 8-bit PNG (row 0 the north edge)."""
    file: str = Field(description="`sky_glow.png`, relative to the plan.")
    bounds: Annotated[list[float], Field(min_length=4, max_length=4,
                                         description="[x0, y0, x1, y1], citygen m.")]
    cell_m: float
    px: Annotated[list[int], Field(min_length=2, max_length=2, description="[width, height].")]
    max_nits: float = Field(description="A channel's value at 255 (cd/m2, physical): the "
                                        "runtime squares the texel and scales by it.")
    max_luma_nits: float = Field(description="The brightest cell's luminance (cd/m2).")
    mean_nits: float = Field(description="The mean over the city's extent (cd/m2).")
    peak_at: Vec2 = Field(description="Where the deck glows brightest (citygen m).")
    sha256: str


class SkyHour(_Model):
    """AT3: a row of the plan's day (the report; the runtime computes any hour itself)."""
    hour: int
    sun_elev: float
    sun_az: float = Field(description="Clockwise from north (degrees).")
    moon_elev: float
    moon_az: float
    ev100: float = Field(description="The scene's exposure (EV100, Unreal's frame).")
    night: float = Field(description="MPC_CityGen's Night.")


class Sky(_Model):
    """AT3: the sky and the time of day (scope 6.2, `sky.make`)."""
    latitude_deg: float
    day_of_year: int
    declination_deg: float = Field(description="The sun's, that day.")
    moon: Moon
    sun_lux: float = Field(description="The sun's light by day in the scene's frame (lux; "
                                       "the importer's sun).")
    ev_night: float = Field(description="The night's exposure in the scene's frame (EV100), "
                                        "held: the plan's lights are shown at "
                                        "2^(ev_night - night_ev100) at every hour.")
    ev_day: float = Field(description="The day's exposure (EV100), darker under a closed "
                                      "deck.")
    curve: dict[str, list[float]] = Field(description="Curves over the sun's elevation "
                                                      "(`elev`): ev (night 0 to day 1), "
                                                      "night, sun, sky, stars "
                                                      "(`presets.SUN_CURVE`).")
    stars: float = Field(description="How many stars the clear dark sky shows (0 to 1).")
    cloud_deck_m: float = Field(description="The cloud deck's height (0: none).")
    cloud_cover: float = Field(description="The share of the sky the deck hides.")
    cloud_glow: float = Field(description="A gain on the city's light the deck shows.")
    upward_lm: float = Field(0.0, description="The plan's upward luminous flux (lm) at the "
                                              "glow's hour, the deck's glow.")
    glow: Glow | None = None
    hours: dict[str, float] = Field(description="The named hours: day, dusk (the sun at "
                                                "`presets.SKY` dusk elevation), night.")
    by_hour: list[SkyHour]


class Tiers(_Model):
    near_m: float
    near_max: int
    mid_m: float
    mid_max: int
    high_m: float = Field(750.0, description="AT2: the high tier's range (m) ...")
    high_max: int = Field(48, description="... and how many of its lights live at most.")
    far_m: float
    sight_m: float = Field(1200.0, description="Visible lights: round a walker the runtime "
                                               "keeps live the lights it sees (a line of "
                                               "sight through the plan's `sight` raster) "
                                               "within this (m) ...")
    sight_max: int = Field(512, description="... at most this many (the high tier's pool "
                                            "keeps `high_max`).")


class Sight(_Model):
    """What a walker sees: the occluders the runtime marches a line of sight through
    (`sight.py`: the lux check's, on `cell_m` cells, every rounding toward seeing)."""
    file: str = Field(description="`sight.png` beside the plan, row 0 the north edge: red "
                                  "the top (absolute, `top_step_m` steps, 0 none), green the "
                                  "bottom over the ground (`bottom_step_m` steps, 0 on the "
                                  "ground), blue the ground (`ground_step_m` steps).")
    bounds: list[float] = Field(description="[x0, y0, x1, y1] (m).")
    cell_m: float
    px: list[int] = Field(description="[width, height].")
    top_step_m: float
    bottom_step_m: float
    ground_step_m: float
    skip_eye_m: float = Field(description="The march leaves out this much from the eye ...")
    skip_light_m: float = Field(description="... and this much to the light.")
    occupied: float = Field(description="The share of the cells something stands in.")
    sha256: str


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
    air: Air | None = Field(None, description="AT4: the fog, light shafts and live sets.")
    volumes: list[FogVolume] = Field(default_factory=list)
    emitters: list[Emitter] = Field(default_factory=list)
    masks: list[Mask] = Field(default_factory=list)
    weather_plan: Weather | None = Field(None, description="AT5: the weather states, the rain's "
                                                      "age, the wind, the masks' frame, the "
                                                      "drips.")
    sight: Sight | None = Field(None, description="Visible lights: the sight raster the "
                                                  "runtime picks a walker's lights by.")
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
    key: str = Field(description="`atmos` (the controller, which AT3 has drive the "
                                 "importer's `lighting.sun`, `lighting.sky` and the sky by "
                                 "the hour), `atmos.lights.<tile>` (a tile's lights).")
    kind: Literal["controller", "tile_lights", "volume", "emitter", "weather"]
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
           "tile_drips": (TileDrips, "atmosgen tile drips"),
           "contribution": (Contribution, "atmosgen unreal contribution")}
