"""The life plan's schema (scope sections 4.2 and 7): what `lifegen plan` writes to
`BUILD/life/`.

- `life_plan.json` (`LifePlan`): the filled spec, every district's people and vehicles by
  hour, the asks of citygen and their state, the spike, the checks, an index of the tiles.
- `spawns/<tile>.json` (`TileSpawns`): a 256 m tile's spawn and sink points (doors, station
  entrances, garages, taxi stands) with their rates by hour, and its place slots (benches,
  bus stops, kiosks, vending machines, stalls, taxi stands).
- `unreal_contribution.life.json` (`Contribution`): layer 4 of the exporter's manifest.
- LG3: the plan's `crowd` (`CrowdPlan`), each tile's `walks` (`Walk`: a walkway's people per
  hour band and its signal) and `signals.json` (`Signals`: every signalized junction's
  phases).

Frames: citygen's (x east, y north, z up, meters, z over the ground as the model has it).
Every entry carries the hash of its own record (`hash`, the sha256 of its canonical JSON
without the hash, first 16 hex digits), so a district regeneration changes only its own and
its seam's entries.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PLAN_VERSION = 1

Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Hours = Annotated[list[float], Field(min_length=24, max_length=24,
                                     description="A value per hour, 0 to 23.")]
SpawnKind = Literal["door", "station", "garage", "taxi_stand"]
SlotKind = Literal["bench", "bus_stop", "kiosk", "vending", "stall", "taxi_stand"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Spawn(_Model):
    """A spawn and sink point (scope 6.3): where people come out and go back in, so a crowd
    is never conjured out of nowhere in view."""
    id: str = Field(description="`spawn.<owner id>.<k>` (the owner's k-th entrance).")
    owner_id: str = Field(description="A building, station, parking or taxi stand.")
    kind: SpawnKind
    sub: str = Field(description="What the entrance is: main, service, unit, garage, ...")
    district_id: str | None = None
    tile: str
    pos: Vec3
    level: int = 0
    walkway_id: str | None = Field(None, description="The walkway it opens to.")
    lane_id: str | None = Field(None, description="A garage's or taxi stand's drive lane.")
    rates: Hours = Field(description="People a hour coming out (and as many going in).")
    seed: int | None = Field(None, description="LG1: the seed the people it sends out are "
                                               "drawn from (its k-th person: "
                                               "`library.person((seed, k), ...)`).")
    yaw_deg: float | None = Field(None, description="LG3: an AG3 door's outward facing "
                                                    "(degrees counterclockwise from east).")
    hash: str


class Slot(_Model):
    """A place slot (scope 6.4): a Smart Object to be (LG4) at a bench, a stop, a stall."""
    id: str = Field(description="`slot.<owner id>`.")
    owner_id: str
    kind: SlotKind
    behavior: Literal["sit", "wait", "buy", "queue"]
    capacity: int
    district_id: str | None = None
    tile: str
    pos: Vec3
    yaw_deg: float = Field(description="The way its user faces, degrees counterclockwise "
                                       "from east.")
    hash: str


class Walk(_Model):
    """LG3: a walkway's crowd (scope 6.3): how many people are on it in each of M11's hour
    bands (the district's day shapes the hours within a band), and the signal it waits for."""
    id: str = Field(description="The walkway's id (M2's walkway graph).")
    kind: str
    district_id: str | None = None
    level: int = 0
    length_m: float
    street: bool = Field(description="On a road segment with M11's density (its sidewalks, "
                                     "alleys, promenades, pedestrian streets), else "
                                     "off-street (`presets.OFFSTREET`).")
    people: Annotated[list[float], Field(min_length=5, max_length=5,
                                         description="People on it per hour band (M11's "
                                                     "bands, the district's busy and the "
                                                     "crowd's scale in).")]
    signal: str | None = Field(None, description="A signalized crosswalk's signal "
                                                 "(`sig.<junction id>`).")
    phase: int | None = Field(None, description="The phase it walks in.")
    hash: str


class Drive(_Model):
    """LG5: a lane's traffic (scope 6.5): how many cars drive on it in each of M11's hour bands
    (the district's day shapes the hours within a band), its road's class, and the signal it
    stops at."""
    id: str = Field(description="The lane's id (M2's lane graph; a lane, not a junction's "
                                "connector).")
    segment_id: str
    district_id: str | None = None
    road_class: str = Field(description="Its cruise speed's class (`presets.DRIVE_SPEEDS`).")
    length_m: float
    main: bool = Field(description="On the lane graph's largest strongly connected part "
                                   "(cars drive only there; a lane off it is left empty).")
    vehicles: Annotated[list[float], Field(min_length=5, max_length=5,
                                           description="Cars on it per hour band (M11's bands, "
                                                       "the fleet's busy and the traffic's "
                                                       "scale in).")]
    signal: str | None = Field(None, description="The signal its end stops at "
                                                 "(`sig.<junction id>`).")
    phase: int | None = Field(None, description="The phase it moves in.")
    stop_back_m: float | None = Field(None, description="Where a car's front stops on red: "
                                                        "this far back from the lane's end "
                                                        "(short of the crosswalk it crosses).")
    hash: str


class TileSpawns(_Model):
    version: Literal[1] = PLAN_VERSION
    city: str
    tile: str
    bounds: Annotated[list[float], Field(min_length=4, max_length=4)]
    spawns: list[Spawn]
    slots: list[Slot]
    walks: list[Walk] = Field(default_factory=list, description="LG3: the walkways whose "
                                                                "middle is in the tile.")
    drives: list[Drive] = Field(default_factory=list, description="LG5: the lanes whose "
                                                                  "middle is in the tile.")


class Phase(_Model):
    index: int
    legs: list[str] = Field(description="Road segments moving (the junction's legs).")
    crosswalks: list[str] = Field(description="Crosswalks walking (M18's ids).")
    walkways: list[str] = Field(description="Their walkways (the walkway graph's).")
    start_s: float = Field(description="Its start in the cycle (s).")
    green_s: float
    amber_s: float
    all_red_s: float
    walk_s: float = Field(description="People start crossing in its first walk_s.")


class Signal(_Model):
    """LG3: a signalized junction's phases (the ask `signal_phases`, derived)."""
    id: str = Field(description="`sig.<junction id>`.")
    junction_id: str
    cycle_s: float
    offset_s: float
    phases: list[Phase]
    hash: str


class Signals(_Model):
    version: Literal[1] = PLAN_VERSION
    city: str
    derived: bool = Field(description="True while citygen records no phases (the ask).")
    signals: list[Signal]


class CrowdPlan(_Model):
    """LG3: the city's crowd (scope 6.3): who walks (a pool of people the runtime simulates
    round the view, each drawn from the library by their seed), how it lives (the hour, the
    live radius, trips, groups, jaywalking, avoidance, speeds), the districts' palettes."""
    hour: int
    pool: int
    live_m: float
    trip_s: float
    scale: float
    groups: list[float]
    group_gap_m: float
    jaywalk: list[float]
    avoid: dict[str, float]
    speeds: dict[str, float | list[float]]
    kinds: list[str] = Field(description="Walkway kinds by the runtime's code.")
    palettes: dict[str, list[str]] = Field(description="Per district its clothes' colors "
                                                       "(sRGB, by its style).")
    library: dict = Field(default_factory=dict)
    persons: dict[str, list[float]] = Field(
        default_factory=dict, description="Per pool slot its draws (seed, character, scale, "
                                          "gait, pace, tint: an index into the district's "
                                          "palette where it comes out).")
    totals: dict
    hash: str


class TrafficPlan(_Model):
    """LG5: the city's traffic (scope 6.5): the pool of cars the runtime simulates round the
    view (each slot a model of AG18's fleet, shared out by the districts' fleets), how they
    drive (the car following model, signals, junctions, yielding), the districts' fleets and
    paints, its totals by hour."""
    hour: int
    pool: int
    live_m: float
    scale: float
    models: list[str] = Field(description="AG18's models the traffic draws from (no Vex or "
                                          "Aurel: `assetgen.parked.table.EXCLUDED`).")
    slots: list[int] = Field(description="Per pool slot its model (an index into `models`).")
    weights: dict[str, list[float]] = Field(description="Per district its fleet: a weight per "
                                                        "model (in `models`' order).")
    paints: dict[str, list[list[float]]] = Field(
        description="Per district, per model, `paints` paints of 9 floats (three linear "
                    "colors, AG18's step H's draw by the district's archetype).")
    drive: dict[str, float | str | list[float]] = Field(
        description="cars_steam's speeds: `junction`, `lateral`, `brake`, `crawl`, `vary`, "
                    "`default`.")
    drive_speeds: dict[str, float]
    follow: dict[str, float] = Field(description="The car following model and the signals, "
                                                 "junctions and yielding (`presets.TRAFFIC`).")
    totals: dict
    hash: str


class TileIndex(_Model):
    tile: str
    file: str = Field(description="`spawns/<tile>.json`, relative to the plan.")
    spawns: int
    slots: int
    walks: int = 0
    drives: int = 0
    sha256: str = Field(description="sha256 of the tile file's bytes.")


class DistrictLife(_Model):
    """A district's people and vehicles by hour, from M11's densities and its filled spec."""
    id: str
    name: str | None = None
    archetype: str | None = None
    wealth: float
    danger: float
    busy: float
    mix: dict[str, float]
    shape: Hours
    style: dict
    fleet: dict[str, float] = Field(description="AG18's models by weight (decision 6).")
    street_m: float = Field(description="Length of its road segments with a density row.")
    people: Hours = Field(description="People on its streets at each hour.")
    vehicles: Hours = Field(description="Vehicles on its roads at each hour.")
    gangs: Hours
    police: Hours
    spawns: int
    slots: int
    hash: str


class Ask(_Model):
    """An ask of another stage (scope 4.1): what lifegen needs that the model does not record
    yet, and what the plan derives meanwhile."""
    id: str
    of: Literal["citygen", "assetgen"]
    what: str
    record: dict = Field(description="The record asked for: field -> meaning.")
    status: Literal["missing", "derived", "met"]
    meanwhile: str
    needed_by: str = Field(description="The milestone that first needs it.")


class SpikeCar(_Model):
    model: str
    weight: float


class SpikePlan(_Model):
    """LG0's spike: plain stand-ins on one district's walkways, a few cars on its lanes."""
    district_id: str
    name: str | None = None
    hour: int
    center: Annotated[list[float], Field(min_length=2, max_length=2,
                                         description="The district's middle (x, y).")]
    radius_m: float = Field(description="The stand-ins live within this of its middle.")
    palette: list[str] = Field(description="The stand-ins' clothes: sRGB colors drawn by "
                                           "the district's style.")
    people: int
    cars: int
    models: list[SpikeCar]
    walk_kinds: list[str]
    walk_speed: Annotated[list[float], Field(min_length=2, max_length=2)]
    drive_speed: Annotated[list[float], Field(min_length=2, max_length=2)]
    car_gap_m: float
    drive_speeds: dict[str, float] = Field(
        default_factory=dict, description="cars_steam: a lane's cruise speed (m/s) by its "
                                          "road's class.")
    drive: dict[str, float | str | list[float]] = Field(
        default_factory=dict, description="cars_steam: `junction` (a connector's share of its "
                                          "roads' slower speed), `lateral` and `brake` "
                                          "(m/s2: a bend's speed sqrt(lateral R), braking "
                                          "before it), `vary` (a car's share), `default`.")
    road_classes: dict[str, str] = Field(
        default_factory=dict, description="cars_steam: the road class of the segments near "
                                          "the spike.")
    polygon: list[list[float]] = Field(description="The district's outline (exterior).")
    library: dict = Field(default_factory=dict, description="LG1: the people library the "
                                                            "persons are drawn from (version, "
                                                            "characters, walks, tiers).")
    persons: dict[str, list[float]] = Field(
        default_factory=dict, description="LG1: each person's draws by their seed, as columns "
                                          "(seed, character, scale, gait, pace, tint: an index "
                                          "into the palette).")
    hash: str


class Check(_Model):
    ok: bool
    detail: str


class LifePlan(_Model):
    version: Literal[1] = PLAN_VERSION
    city: str
    plan_hash: str = Field(description="Hash of the plan's content (every tile's and "
                                       "district's hash, the spike, the spec).")
    model_sha256: str | None = None
    spec: dict = Field(description="The filled spec (budgets, reactions, ...).")
    bands: list[str]
    districts: list[DistrictLife]
    tiles: list[TileIndex]
    asks: list[Ask]
    spike: SpikePlan | None = None
    crowd: CrowdPlan | None = Field(None, description="LG3: the city's crowd.")
    traffic: TrafficPlan | None = Field(None, description="LG5: the city's traffic.")
    checks: dict[str, Check]
    totals: dict


class Entry(_Model):
    """A layer 4 entry, keyed by what it belongs to."""
    key: str
    kind: Literal["life_controller", "spawner", "slots"]
    hash: str
    tile: str | None = None
    count: int = 0


class Contribution(_Model):
    version: Literal[1] = PLAN_VERSION
    stage: Literal["lifegen"] = "lifegen"
    layer: Literal[4] = 4
    city: str
    plan_hash: str
    entries: list[Entry]


SCHEMAS = {"life_plan": (LifePlan, "lifegen life plan"),
           "tile_spawns": (TileSpawns, "lifegen tile spawns"),
           "signals": (Signals, "lifegen signal phases"),
           "contribution": (Contribution, "lifegen layer 4 contribution")}


def json_schema(model: type[BaseModel], title: str) -> dict:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = title
    return schema
