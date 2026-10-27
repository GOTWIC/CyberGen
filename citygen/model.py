"""City model schema (scope section 6): the canonical output, types and serialization only.

Generation fills these in from M1 on. Coordinates are meters, x east, y north, z up, origin at
the city center (same frame as the legacy plan.json). Every entity has a stable readable `id`
(e.g. `d03.blk017.lot004.bld`), a semantic `type` (e.g. `building.podium_tower`, `road.avenue`)
whose first segment is fixed per entity class, and free-form `attrs` for stage 2 and 3.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_VERSION = 1
TILE_SIZE_M = 256.0

ID_PATTERN = r"^[a-z0-9_]+(\.[a-z0-9_]+)*$"
TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$"

Point2 = tuple[float, float]
Point3 = tuple[float, float, float]
Line2 = Annotated[list[Point2], Field(min_length=2)]
Line3 = Annotated[list[Point3], Field(min_length=2)]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Polygon(_Model):
    exterior: Annotated[list[Point2], Field(min_length=3)]
    holes: list[Annotated[list[Point2], Field(min_length=3)]] = Field(default_factory=list)


class ZSample(_Model):
    """Height z at distance s (meters) along a polyline."""
    s: float
    z: float


class Entity(_Model):
    TYPE_PREFIX: ClassVar[str] = ""
    id: Annotated[str, Field(pattern=ID_PATTERN)]
    type: Annotated[str, Field(pattern=TYPE_PATTERN)] | None = Field(
        None, description="Semantic type; left out it becomes the class prefix.")
    attrs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _type_prefix(self) -> Entity:
        prefix = self.TYPE_PREFIX
        if self.type is None:
            self.type = prefix
        elif self.type != prefix and not self.type.startswith(prefix + "."):
            raise ValueError(f"type '{self.type}' must be '{prefix}' or start with '{prefix}.'")
        return self


# --- water and land --------------------------------------------------------

class Land(Entity):
    TYPE_PREFIX: ClassVar[str] = "land"
    polygons: list[Polygon]


class Landmass(Entity):
    TYPE_PREFIX: ClassVar[str] = "landmass"
    polygon: Polygon
    district_ids: list[str] = Field(default_factory=list)


class Island(Entity):
    TYPE_PREFIX: ClassVar[str] = "island"
    name: str
    polygon: Polygon
    setting: Literal["offshore", "nearshore", "mid_river", "delta"]
    landmass_id: str | None = None


class Sea(Entity):
    TYPE_PREFIX: ClassVar[str] = "sea"
    name: str | None = None
    polygons: list[Polygon]


class River(Entity):
    TYPE_PREFIX: ClassVar[str] = "river"
    name: str
    centerline: Line2
    width_m: list[float] = Field(description="Width at each centerline vertex.")
    polygon: Polygon
    mouth: Literal["sea", "edge", "river"]
    flows_into: str | None = None


class Channel(Entity):
    TYPE_PREFIX: ClassVar[str] = "channel"
    name: str | None = None
    kind: Literal["delta_branch", "sea_channel", "separation"] = Field(
        description="delta_branch: distributary of a river or sea channel; sea_channel: wide "
                    "channel or strait; separation: canal-scale channel the generator adds "
                    "between districts.")
    river_id: str | None = Field(None, description="River or sea channel a delta branch leaves.")
    flows_into: str | None = Field(None, description="Water entity id it joins (or 'sea').")
    centerline: Line2
    width_m: list[float]
    polygon: Polygon


class Waterway(Entity):
    TYPE_PREFIX: ClassVar[str] = "waterway"
    kind: Literal["canal", "creek", "inlet", "basin", "marina"]
    name: str | None = None
    district_id: str
    centerline: list[Point2] = Field(default_factory=list)
    polygon: Polygon
    connects_to: str | None = Field(None, description="River, channel, sea or waterway id.")
    ornamental: bool = False


class Quay(Entity):
    TYPE_PREFIX: ClassVar[str] = "quay"
    waterway_id: str
    line: Line2
    width_m: float = 6.0
    deck_z_m: float = 1.5


class Bridge(Entity):
    TYPE_PREFIX: ClassVar[str] = "bridge"
    name: str | None = None
    bridge_class: Literal["road", "rail", "road_rail", "pedestrian"]
    crosses: str = Field(description="Water entity id (the highest class crossed).")
    water_class: Literal["sea", "river", "canal"] | None = Field(
        None, description="Navigable class of the water crossed (scope 5.4): sea channel and "
                          "port approach 25 m+, river 10 to 15 m, canal 3 to 4 m.")
    clearance_m: float
    span_m: float | None = Field(None, description="Length over water.")
    ramp_length_m: float | None = Field(
        None, description="Approach ramp per side, L = (clearance + deck) / 0.06.")
    deck_levels: list[int] = Field(default_factory=lambda: [0])
    line: Line3 = Field(description="Deck line from bank to bank (z = deck top).")
    segment_ids: list[str] = Field(default_factory=list)


# --- districts and places --------------------------------------------------

class District(Entity):
    TYPE_PREFIX: ClassVar[str] = "district"
    name: str
    archetype: str
    polygon: Polygon = Field(description="District territory, inner waterways included.")
    landmass_id: str | None = None
    seed: int
    params: dict[str, Any] = Field(default_factory=dict, description="Filled spec values.")


class Place(Entity):
    """A named place of the spec, built as a labeled sub-area (M2): a plaza, park, garden or
    market carved out of lots; a named promenade, waterfront or street; a waterway; a shore
    strip (pier, docks, beach); a gate where an avenue enters; a neighborhood of blocks; or
    a megasite."""
    TYPE_PREFIX: ClassVar[str] = "place"
    name: str
    kind: str
    district_id: str
    polygon: Polygon | None = None
    label_at: Point2
    feature_ids: list[str] = Field(default_factory=list,
                                   description="Road segments, waterways, blocks or megasites "
                                               "that make it.")


# --- roads -----------------------------------------------------------------

class CrossSection(_Model):
    total_width_m: float
    lane_width_m: float
    lanes_forward: int
    lanes_backward: int
    median_m: float = 0.0
    sidewalk_m: tuple[float, float] = (0.0, 0.0)
    parking: tuple[bool, bool] = (False, False)
    curb_m: float = 0.15
    furniture_m: float = Field(1.5, description="Furniture zone of each sidewalk (trees, "
                                                "lights); clear path = sidewalk - furniture - "
                                                "curb.")
    shared: bool = Field(False, description="One lane shared by both directions (alleys).")


class RoadNode(Entity):
    TYPE_PREFIX: ClassVar[str] = "road_node"
    position: Point3
    level: int = 0


RoadClass = Literal["highway", "avenue", "street", "alley", "service", "pedestrian",
                    "footbridge"]


class RoadSegment(Entity):
    """A road between two nodes (junctions, ends, exits). `type` is `road.<road_class>`."""
    TYPE_PREFIX: ClassVar[str] = "road"
    start: str
    end: str
    road_class: RoadClass
    lanes: int = Field(description="Total lanes, both directions.")
    width_m: float = Field(description="Total cross-section width.")
    centerline: Line2
    level: int = 0
    z_profile: list[ZSample] = Field(
        default_factory=list, description="Road surface height (top of the deck) along the "
                                          "centerline: viaducts, ramps, bridge approaches at "
                                          "5.5%, streets ramping to raised junctions; at most "
                                          "6% steep.")
    cross_section: CrossSection
    one_way: bool = False
    bridge: bool = False
    bridge_ids: list[str] = Field(default_factory=list)
    clearance_m: float | None = Field(None, description="Highest bridge clearance on it.")
    tunnel: bool = Field(False, description="Runs through a tunnel (M9; level -1, the z "
                                            "profile below the ground).")
    tunnel_ids: list[str] = Field(default_factory=list)
    district_ids: list[str] = Field(default_factory=list, description="Districts it serves.")
    name: str | None = None

    @model_validator(mode="after")
    def _class_type(self) -> RoadSegment:
        want = f"road.{self.road_class}"
        if self.type == "road":
            self.type = want
        elif self.type != want and not self.type.startswith(want + "."):
            raise ValueError(f"type '{self.type}' does not match road_class '{self.road_class}'")
        return self


class Junction(Entity):
    """Intersection area of a node where three or more roads meet (curb lines with corner
    fillets), or a cul-de-sac turning bulb. `type` is `junction.<class pair>`, e.g.
    `junction.avenue_street`."""
    TYPE_PREFIX: ClassVar[str] = "junction"
    node_id: str
    polygon: Polygon
    shape: Literal["T", "X", "multi", "cul_de_sac"]
    legs: int
    signalized: bool = False
    corner_radius_m: float
    crosswalk_ids: list[str] = Field(default_factory=list)


class Crosswalk(Entity):
    TYPE_PREFIX: ClassVar[str] = "crosswalk"
    junction_id: str
    segment_id: str = Field(description="The road it crosses.")
    line: Line2 = Field(description="Curb to curb.")
    width_m: float
    signalized: bool = False


class Sidewalk(Entity):
    TYPE_PREFIX: ClassVar[str] = "sidewalk"
    segment_id: str
    side: Literal["left", "right"] = Field(description="Seen along the segment, start to end.")
    line: Line2 = Field(description="Sidewalk center line, between the junction corners.")
    width_m: float = Field(description="Curb to property line.")
    clear_path_m: float
    curb_m: float = 0.15
    furniture_m: float = 0.0


class Lane(Entity):
    """Lane graph (for ZoneGraph and Mass traffic): driving lanes of each road (index 0 next to
    the center line or median) and connector lanes through each node."""
    TYPE_PREFIX: ClassVar[str] = "lane"
    kind: Literal["lane", "connector"] = "lane"
    segment_id: str | None = None
    node_id: str | None = Field(None, description="Connectors: the node they cross.")
    index: int
    forward: bool = Field(description="Lanes: travels start to end of its segment.")
    centerline: Line3
    width_m: float
    successors: list[str] = Field(default_factory=list)
    adjacent_ids: list[str] = Field(default_factory=list,
                                    description="Lanes of the same road and direction next to "
                                                "this one (lane changes).")


class Walkway(Entity):
    """Pedestrian graph edge (for crowds); edges meet at shared end points."""
    TYPE_PREFIX: ClassVar[str] = "walkway"
    kind: Literal["sidewalk", "crosswalk", "crossing", "pedestrian_street", "promenade",
                  "footbridge", "alley", "skybridge", "elevated", "stairs", "escalator",
                  "elevator", "path", "underpass"]
    line: Line3
    width_m: float
    neighbors: list[str] = Field(default_factory=list)


class Structure(Entity):
    TYPE_PREFIX: ClassVar[str] = "structure"
    kind: Literal["deck", "ramp", "column", "pylon", "tube", "canopy", "portal", "trench",
                  "vent"]
    footprint: Polygon | None = None
    line: list[Point3] = Field(default_factory=list)
    z0_m: float
    z1_m: float
    supports: list[str] = Field(default_factory=list, description="Ids carried by this structure.")


# --- tunnels (M9) -------------------------------------------------------------

class TunnelPortal(_Model):
    """Where a tunnel's roof meets the ground: the open approach ramp (a walled trench) runs
    on from here to the ground."""
    position: Point3 = Field(description="Road (or track) center at the portal.")
    heading_deg: float = Field(description="Into the tunnel, degrees counterclockwise from "
                                           "east.")
    open_m: float = Field(description="Length of the open approach outside the portal.")


class Tunnel(Entity):
    """A road tunnel (immersed tube under water, cut-and-cover box under the ground), a metro
    tunnel between station boxes, or a pedestrian underpass. `line` is the road surface or
    track along the whole sunk stretch (open approaches included); the structure is a box
    `width_m` wide from `floor_m` under the line to `roof_m` over its clear height."""
    TYPE_PREFIX: ClassVar[str] = "tunnel"
    kind: Literal["immersed_tube", "cut_and_cover", "metro", "pedestrian"]
    name: str | None = None
    segment_ids: list[str] = Field(default_factory=list, description="Roads through it.")
    line_id: str | None = Field(None, description="Metro: its transit line.")
    walkway_ids: list[str] = Field(default_factory=list, description="Underpasses.")
    crosses: list[str] = Field(default_factory=list,
                               description="Water, districts and roads it passes under.")
    line: Line3
    width_m: float
    clear_m: float = Field(description="Clear height over the road, track or walkway.")
    roof_m: float = Field(description="Roof slab thickness.")
    floor_m: float = Field(1.0, description="Floor slab under the road or track.")
    portals: list[TunnelPortal] = Field(default_factory=list)
    vent_ids: list[str] = Field(default_factory=list, description="Ventilation buildings.")


# --- transit -----------------------------------------------------------------

class TransitLine(Entity):
    TYPE_PREFIX: ClassVar[str] = "transit_line"
    name: str
    mode: Literal["metro", "elevated_rail", "monorail", "maglev", "sky_tube"]
    color: str
    path: Line3 = Field(description="Track centerline with altitude.")
    station_ids: list[str] = Field(default_factory=list)
    loop: bool = False


class Station(Entity):
    TYPE_PREFIX: ClassVar[str] = "station"
    name: str
    kind: Literal["ground", "elevated", "sky", "underground"]
    line_ids: list[str]
    position: Point3
    footprint: Polygon | None = None
    building_id: str | None = Field(None, description="Host tower for sky stations.")
    access_ids: list[str] = Field(default_factory=list, description="Walkway ids to the street.")


class Megasite(Entity):
    TYPE_PREFIX: ClassVar[str] = "megasite"
    kind: str
    name: str
    district_id: str
    polygon: Polygon = Field(description="Reserved ground (M1b); the site generator fills it.")
    height_limit_m: float | None = None
    flight_cone: Polygon | None = Field(
        None, description="Spaceports: ground footprint of the flight cone (kept free of roads).")
    member_ids: list[str] = Field(default_factory=list)


# --- blocks, lots, buildings -------------------------------------------------

class Block(Entity):
    TYPE_PREFIX: ClassVar[str] = "block"
    district_id: str
    archetype: str
    polygon: Polygon
    area_m2: float
    frontage_ids: list[str] = Field(default_factory=list, description="Road segment ids.")


class Frontage(_Model):
    segment_id: str
    road_class: str
    length_m: float
    line: Line2 = Field(description="The lot edge along the road.")


class Lot(Entity):
    TYPE_PREFIX: ClassVar[str] = "lot"
    block_id: str
    district_id: str
    archetype: str
    polygon: Polygon
    area_m2: float
    frontage: list[Frontage] = Field(default_factory=list, description="Longest first.")
    frontage_ids: list[str] = Field(default_factory=list, description="Road segment ids.")
    merged_group_id: str | None = Field(
        None, description="Lots that M3 builds as one complex (twin towers, cluster, ...).")


class OpenSpace(Entity):
    TYPE_PREFIX: ClassVar[str] = "open_space"
    kind: Literal["park", "plaza", "pocket_park", "promenade", "courtyard", "podium_roof",
                  "marsh", "market", "garden", "green", "beach"]
    polygon: Polygon
    z_m: float = 0.0
    name: str | None = None
    district_id: str | None = None


class Property(Entity):
    """One owner's buildings: a single building on a lot, a complex on merged lots (twin
    towers, tower cluster, ...), a landmark, or the buildings of a megasite."""
    TYPE_PREFIX: ClassVar[str] = "property"
    owner: str
    complex: Literal["twin_towers", "tower_cluster", "megabuilding_campus", "bridged_pair",
                     "straddle_building", "campus", "single", "landmark", "megasite"] = "single"
    building_ids: list[str]
    district_id: str | None = None
    lot_ids: list[str] = Field(default_factory=list)
    name: str | None = None


class Mass(_Model):
    """An extruded footprint from z0 to z1. `shape` tells the blockout builder how to read it:
    prism (the footprint extruded), cylinder (footprint is a circle), dome and cone (rise
    from the footprint to a point or cap), ring (a vertical wheel whose diameter is z1 - z0,
    its footprint the thin plan of the rim)."""
    footprint: Polygon
    z0_m: float
    z1_m: float
    role: str = Field("body", description="podium, tower, tier, crown, spire, mechanical, "
                                          "body, void, deck, span, leg, dock, ramp, roof, ...")
    shape: Literal["prism", "cylinder", "dome", "cone", "ring"] = "prism"


class Unit(_Model):
    """A ground-floor unit along a street facade (4 to 12 m wide)."""
    edge: tuple[Point2, Point2]
    use: str
    entrance: Point2 | None = None
    width_m: float = 0.0
    segment_id: str | None = Field(None, description="Road segment the unit faces.")
    awning_m: float = Field(0.0, description="Awning depth over the sidewalk (0: none).")
    sign: bool = False


class Entrance(_Model):
    position: Point2 = Field(description="On the facade, ground level.")
    kind: Literal["main", "service", "loading", "garage", "gate"] = "main"
    segment_id: str | None = Field(None, description="Road segment it faces.")
    walkway_id: str | None = Field(None, description="Nearest ground walkway (crowds enter "
                                                     "and leave here).")
    link_m: float | None = Field(None, description="Distance from the entrance to that "
                                                   "walkway.")


class RoofItem(_Model):
    kind: str  # ac_unit, water_tank, antenna, billboard, helipad, av_pad, mechanical, ...
    position: Point3 = Field(description="Center of the item's base (z = the roof it sits on).")
    size: Point3 = Field(description="Extent along the building axis, across it, and up.")
    yaw_deg: float = Field(0.0, description="Building axis, degrees counterclockwise from east.")


class Portal(_Model):
    line_id: str
    z0_m: float
    z1_m: float
    station: bool = False


class Building(Entity):
    """`type` is `building.<archetype>` (podium_tower, slab, courtyard_block, megabuilding,
    terraced, shopfront_row, shanty_stack, warehouse, shed, parking_structure, lab, station,
    terminal, hangar, ...), or `building.landmark.<kind>` for landmarks."""
    TYPE_PREFIX: ClassVar[str] = "building"
    name: str | None = None
    lot_id: str | None = None
    property_id: str | None = None
    district_id: str | None = None
    megasite_id: str | None = None
    use: Literal["office", "residential", "retail", "hotel", "industrial", "parking", "civic",
                 "mixed", "station", "transport", "entertainment", "religious"]
    floor_height_m: float = 3.5
    floors: int = Field(1, description="Floors of the tallest mass.")
    height_m: float = Field(0.0, description="Top of the tallest mass (spires included).")
    footprint: Polygon | None = Field(None, description="Ground footprint (masses from z 0).")
    masses: Annotated[list[Mass], Field(min_length=1)]
    entrances: list[Entrance] = Field(default_factory=list)
    units: list[Unit] = Field(default_factory=list)
    roof_items: list[RoofItem] = Field(default_factory=list)
    portals: list[Portal] = Field(default_factory=list)
    landmark: bool = False
    style: dict[str, float | str] = Field(default_factory=dict, description="grime, neon, era.")


class Skybridge(Entity):
    TYPE_PREFIX: ClassVar[str] = "skybridge"
    building_ids: tuple[str, str]
    line: Line2 = Field(description="Facade to facade.")
    z_m: float = Field(description="Deck level (a floor of both buildings).")
    width_m: float
    levels: int = 1
    level_height_m: float = 4.0
    kind: Literal["enclosed", "open_deck", "stack", "catwalk", "cable"] = "enclosed"
    length_m: float = 0.0
    clearance_m: float | None = Field(None, description="Deck underside over what it "
                                                        "crosses (road or water level).")
    crosses: list[str] = Field(default_factory=list, description="Road segments, water and "
                                                                "open space below.")
    walkway_ids: list[str] = Field(default_factory=list)
    property_id: str | None = None


class SiteElement(Entity):
    """A part of a megasite or a lot that is not a building: launch pads, fuel tanks, cranes,
    container stacks, berths, rail tracks, platforms, bus bays, lawns, ponds, paths, walls,
    gates. Flat ones carry a footprint (or line) at z_m; raised ones carry masses."""
    TYPE_PREFIX: ClassVar[str] = "site_element"
    kind: str
    megasite_id: str | None = None
    lot_id: str | None = None
    footprint: Polygon | None = None
    line: list[Point2] = Field(default_factory=list)
    z_m: float = 0.0
    masses: list[Mass] = Field(default_factory=list)


class Plant(Entity):
    TYPE_PREFIX: ClassVar[str] = "plant"
    position: Point3
    height_m: float
    crown_radius_m: float
    species: str | None = None


class GreenArea(Entity):
    TYPE_PREFIX: ClassVar[str] = "green_area"
    kind: Literal["lawn", "hedge_line", "green_roof", "ground_cover"]
    polygon: Polygon | None = None
    line: list[Point2] = Field(default_factory=list)
    z_m: float = 0.0
    building_id: str | None = Field(None, description="Green roofs: the building it tops.")


class Prop(Entity):
    TYPE_PREFIX: ClassVar[str] = "prop"
    position: Point3
    yaw_deg: float = 0.0
    scale: Point3 = (1.0, 1.0, 1.0)


class Tile(Entity):
    TYPE_PREFIX: ClassVar[str] = "tile"
    ix: int
    iy: int
    bounds: tuple[float, float, float, float]


# --- the document ----------------------------------------------------------------

COLLECTIONS: dict[str, type[Entity]] = {
    "land": Land, "landmasses": Landmass, "islands": Island, "seas": Sea, "rivers": River,
    "channels": Channel, "waterways": Waterway, "quays": Quay, "bridges": Bridge,
    "districts": District, "places": Place, "road_nodes": RoadNode, "road_segments": RoadSegment,
    "junctions": Junction, "crosswalks": Crosswalk, "sidewalks": Sidewalk, "lanes": Lane,
    "walkways": Walkway, "structures": Structure, "tunnels": Tunnel,
    "transit_lines": TransitLine, "stations": Station, "megasites": Megasite, "blocks": Block,
    "lots": Lot, "open_spaces": OpenSpace, "properties": Property, "buildings": Building,
    "skybridges": Skybridge, "site_elements": SiteElement, "plants": Plant, "green_areas": GreenArea, "props": Prop,
    "tiles": Tile,
}


class CityModel(_Model):
    version: Literal[1] = MODEL_VERSION
    name: str
    seed: int
    spec_sha256: str | None = None
    frame: Literal["x_east_y_north_z_up_m_origin_center"] = "x_east_y_north_z_up_m_origin_center"
    bounds: tuple[float, float, float, float]
    tile_size_m: float = TILE_SIZE_M

    land: list[Land] = Field(default_factory=list)
    landmasses: list[Landmass] = Field(default_factory=list)
    islands: list[Island] = Field(default_factory=list)
    seas: list[Sea] = Field(default_factory=list)
    rivers: list[River] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=list)
    waterways: list[Waterway] = Field(default_factory=list)
    quays: list[Quay] = Field(default_factory=list)
    bridges: list[Bridge] = Field(default_factory=list)
    districts: list[District] = Field(default_factory=list)
    places: list[Place] = Field(default_factory=list)
    road_nodes: list[RoadNode] = Field(default_factory=list)
    road_segments: list[RoadSegment] = Field(default_factory=list)
    junctions: list[Junction] = Field(default_factory=list)
    crosswalks: list[Crosswalk] = Field(default_factory=list)
    sidewalks: list[Sidewalk] = Field(default_factory=list)
    lanes: list[Lane] = Field(default_factory=list)
    walkways: list[Walkway] = Field(default_factory=list)
    structures: list[Structure] = Field(default_factory=list)
    tunnels: list[Tunnel] = Field(default_factory=list)
    transit_lines: list[TransitLine] = Field(default_factory=list)
    stations: list[Station] = Field(default_factory=list)
    megasites: list[Megasite] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    lots: list[Lot] = Field(default_factory=list)
    open_spaces: list[OpenSpace] = Field(default_factory=list)
    properties: list[Property] = Field(default_factory=list)
    buildings: list[Building] = Field(default_factory=list)
    skybridges: list[Skybridge] = Field(default_factory=list)
    site_elements: list[SiteElement] = Field(default_factory=list)
    plants: list[Plant] = Field(default_factory=list)
    green_areas: list[GreenArea] = Field(default_factory=list)
    props: list[Prop] = Field(default_factory=list)
    tiles: list[Tile] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> CityModel:
        seen: set[str] = set()
        for name in COLLECTIONS:
            for e in getattr(self, name):
                if e.id in seen:
                    raise ValueError(f"duplicate id '{e.id}' (in {name})")
                seen.add(e.id)
        return self

    def entities(self):
        for name in COLLECTIONS:
            yield from getattr(self, name)

    def index(self) -> dict[str, Entity]:
        return {e.id: e for e in self.entities()}

    def to_json(self, indent: int | None = None) -> str:
        """Deterministic JSON: fixed field order, defaults kept, no NaN."""
        data = self.model_dump(mode="json")
        return json.dumps(data, indent=indent, ensure_ascii=False, allow_nan=False,
                          separators=None if indent else (",", ":"))

    @classmethod
    def from_json(cls, text: str) -> CityModel:
        return cls.model_validate_json(text)


def json_schema() -> dict:
    schema = CityModel.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "citygen city model"
    return schema
