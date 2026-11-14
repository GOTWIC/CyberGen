"""The life plan's schema (scope sections 4.2 and 7): what `lifegen plan` writes to
`BUILD/life/`.

- `life_plan.json` (`LifePlan`): the filled spec, every district's people and vehicles by
  hour, the asks of citygen and their state, the spike, the checks, an index of the tiles.
- `spawns/<tile>.json` (`TileSpawns`): a 256 m tile's spawn and sink points (doors, station
  entrances, garages, taxi stands) with their rates by hour, and its place slots (benches,
  bus stops, kiosks, vending machines, stalls, taxi stands).
- `unreal_contribution.life.json` (`Contribution`): layer 4 of the exporter's manifest.

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


class TileSpawns(_Model):
    version: Literal[1] = PLAN_VERSION
    city: str
    tile: str
    bounds: Annotated[list[float], Field(min_length=4, max_length=4)]
    spawns: list[Spawn]
    slots: list[Slot]


class TileIndex(_Model):
    tile: str
    file: str = Field(description="`spawns/<tile>.json`, relative to the plan.")
    spawns: int
    slots: int
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
    people: int
    cars: int
    models: list[SpikeCar]
    walk_kinds: list[str]
    walk_speed: Annotated[list[float], Field(min_length=2, max_length=2)]
    drive_speed: Annotated[list[float], Field(min_length=2, max_length=2)]
    car_gap_m: float
    polygon: list[list[float]] = Field(description="The district's outline (exterior).")
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
           "contribution": (Contribution, "lifegen layer 4 contribution")}


def json_schema(model: type[BaseModel], title: str) -> dict:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = title
    return schema
