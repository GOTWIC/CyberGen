"""The brief as a schema (scope 4.1): the contract between the brief stage and every
generator after it. `brief.py` writes plain dicts for speed; the tests validate them
against these models, and `assetgen brief schema` exports the JSON Schema.

Coordinates are the building's own frame: x east, y north, z up, meters to the millimeter,
origin `origin` (world, on the 0.01 m grid). An `At` locates a thing on a facade: the mass,
the edge (index into `edges`), the distance along the edge from its start and the distance
from it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

P2 = tuple[float, float]
P3 = tuple[float, float, float]
EdgeClass = Literal["front", "street", "alley", "canal", "plaza", "park", "courtyard", "atrium",
                    "party", "blind", "open", "upper", "hidden"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class At(_M):
    mass: int
    edge: int
    s: float
    d: float


class Polygon(_M):
    exterior: list[P2]
    holes: list[list[P2]]


class Floors(_M):
    first: int | None = Field(description="Floor index of the mass's base on the building's "
                                          "grid (None: off the grid).")
    count: int = Field(description="Floors in the mass (0: none, a spire or thin deck).")
    height_m: float | None


class Arc(_M):
    """M21: a curved stretch of the footprint (in the building frame)."""
    center: tuple[float, float]
    radius_m: float
    start_deg: float
    sweep_deg: float


class Plate(_M):
    """M21: a band's plate against its form's base plate (turned and scaled about the form's
    pivot, then moved)."""
    turn_deg: float
    scale: float
    shift_m: tuple[float, float]


class Mass(_M):
    role: str
    shape: str
    z: tuple[float, float]
    footprint: Polygon
    floors: Floors
    arcs: list[Arc] | None = Field(None, description="M21: its curved stretches (absent: none).")
    plate: Plate | None = Field(None, description="M21: a band of a twisted, tapered or leaning "
                                                  "shaft (absent: none).")


class Region(_M):
    """A rectangle of an edge's facade: s along the edge, z up."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    s: tuple[float, float]
    z: tuple[float, float]
    class_: EdgeClass = Field(alias="class")
    ref: str | None = Field(None, description="party, blind: the neighbor; hidden: the own "
                                              "mass (m<k>); facing: the road, water, open "
                                              "space or building it faces.")
    road_class: str | None = None
    kind: str | None = Field(None, description="Open space kind faced.")


class Edge(_M):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    mass: int
    ring: int = Field(description="0: the exterior; k: the k-th hole (a court).")
    i: int
    a: P2
    b: P2
    length_m: float
    normal_deg: float = Field(description="Outward normal, degrees counterclockwise from east.")
    class_: EdgeClass = Field(alias="class", description="The class with the most facade "
                                                         "area (hidden: all hidden).")
    regions: list[Region]


class Neighbor(_M):
    id: str
    d_m: float
    relation: Literal["party", "blind"]
    height_m: float
    type: str


class Unit(_M):
    edge: tuple[P2, P2]
    use: str
    width_m: float
    segment_id: str | None
    awning_m: float
    sign: bool
    entrance: P2 | None
    at: At | None


class Entrance(_M):
    position: P2
    kind: str
    segment_id: str | None
    walkway_id: str | None
    at: At | None


class RoofItem(_M):
    kind: str
    position: P3
    size: P3
    yaw_deg: float
    mass: int | None = Field(description="The mass whose roof it sits on.")


class Portal(_M):
    line_id: str
    z: tuple[float, float]
    station: bool
    lines: list[list[P3]] = Field(description="AG4: the sky tube's top line near the tower, "
                                               "a polyline per tube piece (building frame, z "
                                               "from its base).")
    diameter_m: float
    station_id: str | None = None
    station_name: str | None = None
    track_z_m: float | None = Field(None, description="The sky station's track (the tube's "
                                                      "axis), building frame.")
    platform: Polygon | None = Field(None, description="The sky station's platform "
                                                       "footprint (M5), building frame.")


class Clearance(_M):
    """AG4: a corridor the asset keeps out of (a skybridge, a transit guideway and its
    trains, a sky tube), near the building: a line of (x, y, z floor, z top) in the building
    frame and a half width."""
    kind: Literal["skybridge", "guideway", "sky_tube"]
    id: str
    mode: str
    half_m: float
    line: list[tuple[float, float, float, float]]


class SkybridgeEnd(_M):
    id: str
    kind: str
    z_m: float
    width_m: float
    levels: int
    level_height_m: float
    other: str
    end: P2
    at: At | None


class SignSlot(_M):
    id: str
    kind: str
    mount: str
    position: P3
    yaw_deg: float
    width_m: float
    height_m: float
    content: str
    prop_id: str | None
    roof_item: int | None
    emitter: bool
    two_sided: bool
    at: At | None


class MountedProp(_M):
    id: str
    kind: str
    position: P3
    yaw_deg: float
    scale: P3
    attrs: dict[str, Any]
    at: At | None
    on_wall: bool = Field(description="Mount point within 0.5 m of a facade spanning its "
                                      "height.")
    gap_m: float
    end: int | None = Field(None, description="Overhead cables: which end (0, 1).")


class Plant(_M):
    id: str
    type: str
    species: str | None
    position: P3
    height_m: float
    attrs: dict[str, Any]
    at: At | None


class GreenRoof(_M):
    id: str
    z_m: float
    polygon: Polygon | None


class Poi(_M):
    id: str
    kind: str
    sub: str
    name: str
    unit_index: int | None
    floor: int
    hours: tuple[int, int]
    host_id: str | None


class Frontage(_M):
    segment_id: str
    road_class: str
    length_m: float
    line: list[P2]


class Lot(_M):
    id: str
    polygon: Polygon
    frontage: list[Frontage]
    main_segment_id: str | None


class Property(_M):
    id: str
    owner: str
    complex: str
    name: str | None
    building_ids: list[str]


class District(_M):
    id: str
    name: str
    archetype: str
    grime: float | None
    neon: float | None
    greenery: float | None
    wealth: float | None
    danger: float | None


class FloorGrid(_M):
    floor_height_m: float
    base_m: float | None = Field(description="M13: the ground floor over sea level.")
    plinth_m: float | None = Field(description="M13: the lowest ground under the footprint.")
    level: int = Field(0, description="M14: the street level its ground floor is on (1: a "
                                      "deck; absent on the ground).")
    deck_m: float | None = Field(None, description="M14: the deck top its ground floor stands "
                                                   "on (absent on the ground).")


class Form(_M):
    """M21: how the building departs from a box (citygen's `Building.form`)."""
    kind: str
    crown: str
    tower: bool
    band: int
    pivot: tuple[float, float] | None
    masses: list[int]
    params: dict[str, Any]


class BuildingRec(_M):
    type: str
    use: str
    name: str | None
    landmark: bool
    attrs: dict[str, Any]
    lot_id: str | None
    property_id: str | None
    district_id: str | None
    megasite_id: str | None
    floors: int
    height_m: float
    style: dict[str, Any]
    floor_grid: FloorGrid
    form: Form | None = Field(None, description="M21: the building's form (absent: none).")


class SpecSection(_M):
    uniqueness: str
    hero_uniqueness: str
    min_gene_distance: int
    share_parts: bool
    texel_density_px_m: int
    texel_density_upper_px_m: int
    era: str | None
    era_style: dict[str, Any] | None
    district: dict[str, Any] | None
    owner: dict[str, Any] | None
    landmark: dict[str, Any] | None


class Terrain(_M):
    """AG5: on M13's slopes, the ground along each edge of a mass on the base (None for the
    others), from its start every `step_m` and at its end, `out_m` outside it, in meters
    over the building's base."""
    step_m: float
    out_m: float
    grade: list[list[float] | None]


class Deck(_M):
    """AG10: the M14 deck slab a building stands on, under, beside or in: its top and
    soffit over the building's pivot, and the slab's plan within 3 m of the building's box
    (its frame)."""
    id: str
    role: Literal["on", "under", "near", "through"]
    top_m: float
    underside_m: float
    slab: list[Polygon]


class Brief(_M):
    brief_version: Literal[2]
    id: str
    origin: P2
    building: BuildingRec
    masses: list[Mass]
    edges: list[Edge]
    neighbors: list[Neighbor]
    units: list[Unit]
    entrances: list[Entrance]
    roof_items: list[RoofItem]
    portals: list[Portal]
    skybridges: list[SkybridgeEnd]
    sign_slots: list[SignSlot]
    props: list[MountedProp]
    plants: list[Plant]
    green_roofs: list[GreenRoof]
    pois: list[Poi]
    lot: Lot | None
    property: Property | None
    district: District | None
    spec: SpecSection
    override: dict[str, Any] | None
    clearances: list[Clearance] = Field(default_factory=list)
    terrain: Terrain | None = Field(None, description="AG5: the ground along the base's "
                                                      "edges (M13's slopes only).")
    deck: Deck | None = Field(None, description="AG10: an M14 deck's slab it stands on, "
                                                "under, beside or in (decks only).")


def json_schema() -> dict:
    schema = Brief.model_json_schema(mode="validation", by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "assetgen building brief"
    return schema
