"""City spec schema (scope sections 4 and 5).

The spec is what the prompt-to-spec session writes. Structural rules (types, enums, ranges,
unknown keys) live here as pydantic models; cross-references and consistency rules live in
`validate.py`; preset expansion lives in `defaults.py`.

Conventions:
- Optional fields left out (null) are filled from presets by `fill_defaults`.
- An explicit empty list means "none", which is different from leaving the field out.
- Some fields accept a shorthand (a bare string instead of an object); the shorthand is
  normalized on load, and the exported JSON Schema lists both forms.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    WithJsonSchema,
    model_serializer,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from . import presets

SPEC_VERSION = 1

Direction = Literal[
    "north", "north_east", "east", "south_east", "south", "south_west", "west", "north_west"
]
Edge = Literal[
    "north", "north_east", "east", "south_east", "south", "south_west", "west", "north_west",
    "center",
]
Archetype = Literal[
    "corporate_core", "megablock_residential", "midtown_mixed", "entertainment_market",
    "old_town", "industrial_port", "residential_heights", "research_campus", "transit_hub",
    "spaceport",
]
StreetPattern = Literal[
    "rotated_grid", "grid", "large_grid", "superblocks", "grid_ring_park", "organic",
    "curvilinear", "campus_loops", "radial_ring", "service_roads",
]
CoastForm = Literal["bay", "peninsula", "delta", "archipelago", "crescent", "straight"]
Separation = Literal["water_preferred", "water_required", "none"]
BoundaryKind = Literal[
    "water", "river", "channel", "canal", "sea", "highway", "ring_road", "rail", "wall"
]
WaterwayStyle = Literal[
    "canal_grid", "organic_canals", "creeks", "inlets", "harbor_basins", "marina"
]
IslandSetting = Literal["offshore", "nearshore", "mid_river", "delta"]
TransitMode = Literal["metro", "elevated_rail", "monorail", "maglev", "sky_tube"]
MegasiteKind = Literal[
    "spaceport", "skyport", "transit_nexus", "freight_terminal", "stadium", "arcology",
    "temple_complex", "central_park", "grand_plaza", "attraction",
]
ComplexKind = Literal[
    "twin_towers", "tower_cluster", "megabuilding_campus", "bridged_pair", "straddle_building",
    "campus",
]
PlaceKind = Literal[
    "plaza", "park", "garden", "street", "pedestrian_street", "market", "canal", "creek",
    "waterfront", "promenade", "pier", "docks", "marina", "beach", "gate", "neighborhood",
    "monument", "station",
]
HighwayPattern = Literal["ring", "ring_plus_spine", "spine", "grid", "radial", "coastal", "none"]
BridgeKind = Literal["road", "rail", "road_rail", "pedestrian"]
TransitCrossing = Literal["own_bridge", "shared_deck", "auto"]
TunnelWater = Literal["never", "auto", "prefer"]

MEGASITE_KINDS: tuple[str, ...] = MegasiteKind.__args__  # type: ignore[attr-defined]
DIRECTIONS: tuple[str, ...] = Direction.__args__  # type: ignore[attr-defined]
TRANSIT_MODES: tuple[str, ...] = TransitMode.__args__  # type: ignore[attr-defined]

# Reserved route / reference tokens that are not names.
EXIT_RE = re.compile(r"^(north|north_east|east|south_east|south|south_west|west|north_west)_exit$")
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _name(v: str) -> str:
    if not v:
        raise ValueError("must not be empty")
    if len(v) > 60:
        raise ValueError("must be at most 60 characters")
    if EXIT_RE.match(v) or v in ("sea", "bay"):
        raise ValueError(f"'{v}' is reserved (exits and 'sea'/'bay' are route tokens, not names)")
    return v


Name = Annotated[str, AfterValidator(_name)]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]


def _range(lo: float, hi: float, unit: str = "m"):
    def check(v: tuple[float, float]) -> tuple[float, float]:
        a, b = v
        if a > b:
            raise ValueError(f"must be [min, max] with min <= max, got [{a:g}, {b:g}]")
        if a < lo or b > hi:
            raise ValueError(f"must lie within {lo:g} to {hi:g} {unit}, got [{a:g}, {b:g}]")
        return (float(a), float(b))

    return AfterValidator(check)


def _size(lo: float, hi: float):
    """[width, height]: two independent extents, not a [min, max] range."""
    def check(v: tuple[float, float]) -> tuple[float, float]:
        if not all(lo <= x <= hi for x in v):
            raise ValueError(f"each side must lie within {lo:g} to {hi:g} km, got [{v[0]:g}, {v[1]:g}]")
        return (float(v[0]), float(v[1]))

    return AfterValidator(check)


def _to_list(v: Any) -> Any:
    return [v] if isinstance(v, str) else v


def _kind_shorthand(v: Any) -> Any:
    """'megatower' -> {'kind': 'megatower'}."""
    return {"kind": v} if isinstance(v, str) else v


StrOrList = Annotated[
    list[str], BeforeValidator(_to_list, json_schema_input_type=str | list[str])
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------

class Coast(_Model):
    form: CoastForm = Field(description="Overall shape of the coast.")
    side: Direction = Field(description="Side of the map where the open sea is.")
    name: Name | None = Field(None, description="Name of the sea or bay, e.g. 'West Bay'.")
    sea_share: Annotated[float, Field(ge=0.05, le=0.8)] | None = Field(
        None, description="Fraction of the map that is sea, offshore islands included (they "
                          "are carved out of it). Default by form.")
    headlands: Annotated[int, Field(ge=2, le=5)] | None = Field(
        None, description="Peninsula only: the land widens from a neck toward the sea and fans "
                          "out into this many headlands with coves between them, instead of "
                          "ending in one rounded tip.")

    @model_validator(mode="after")
    def _headlands_on_peninsula(self) -> Coast:
        if self.headlands is not None and self.form != "peninsula":
            raise ValueError("'headlands' needs coast form 'peninsula'")
        return self


_DIRECTION_LIST = ["north", "north_east", "east", "south_east", "south", "south_west", "west",
                   "north_west"]
_AT_SCHEMA = {"type": "number", "minimum": 0, "maximum": 1,
              "description": "Position along the edge, 0 to 1: west to east on the north and "
                             "south edges, south to north on the east and west edges; on a "
                             "diagonal edge 0 is the middle of the first-named side, 0.5 the "
                             "corner, 1 the middle of the second side. Default 0.5."}


def _end_schema(edges: list[str] | None, plain: dict) -> dict:
    edge = {"enum": edges} if edges else {"type": "string"}
    return {"anyOf": [plain, {
        "type": "object", "additionalProperties": False, "required": ["edge"],
        "properties": {"edge": edge, "at": _AT_SCHEMA}}]}


class River(_Model):
    name: Name
    kind: Literal["river", "channel"] = Field(
        "river", description="'channel' is a wide sea channel or strait (sea-class clearance).")
    from_: Annotated[Direction, WithJsonSchema(_end_schema(_DIRECTION_LIST,
                                                           {"enum": _DIRECTION_LIST}))] = Field(
        alias="from", description="Map edge where the river enters, or {edge, at} to pin where "
                                  "along that edge.")
    to: Annotated[str, WithJsonSchema(_end_schema(None, {"type": "string"}))] = Field(
        "sea",
        description="Mouth: 'sea', 'bay', a map edge direction, or the name of another river "
                    "(tributary). {edge, at} pins the mouth along a map edge (for 'sea' and "
                    "'bay': along the sea-side edge; for a tributary: along the parent, 0 = "
                    "where the parent enters, 1 = its mouth).")
    # Filled from the {edge, at} forms of `from` and `to`; serialized back into them.
    from_at: SkipJsonSchema[float | None] = Field(None, exclude=True)
    to_at: SkipJsonSchema[float | None] = Field(None, exclude=True)
    width_m: Annotated[tuple[float, float], _range(10, 600)] | None = Field(
        None, description="[min, max] width. Default 60 to 120 for rivers, 150 to 300 for channels.")
    meander: Fraction | None = Field(None, description="0 straight, 1 strongly meandering.")
    delta_branches: Annotated[int, Field(ge=0, le=6)] = Field(
        0, description="Extra distributary channels near the mouth, besides the main channel "
                       "(four channels in total = 3).")
    branch_names: list[Name] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _ends(cls, v: Any) -> Any:
        """{"edge": "east", "at": 0.3} -> from/to = "east" plus from_at/to_at = 0.3."""
        if not isinstance(v, dict):
            return v
        v = dict(v)
        for key in ("from", "to"):
            end = v.get(key)
            if not isinstance(end, dict):
                continue
            unknown = sorted(set(end) - {"edge", "at"})
            if unknown:
                raise ValueError(f"{key}: unknown field '{unknown[0]}' (expected 'edge' and 'at')")
            if "edge" not in end:
                raise ValueError(f"{key}: missing required field 'edge'")
            at = end.get("at")
            if at is not None:
                if isinstance(at, bool) or not isinstance(at, (int, float)) or not 0 <= at <= 1:
                    raise ValueError(f"{key}.at must be a number from 0 to 1, got {at!r}")
                v[f"{key}_at"] = float(at)
            v[key] = end["edge"]
        return v

    @model_serializer(mode="wrap")
    def _nest_ends(self, handler: SerializerFunctionWrapHandler,
                   info: SerializationInfo) -> dict[str, Any]:
        data = handler(self)
        key = "from" if info.by_alias else "from_"
        if self.from_at is not None and key in data:
            data[key] = {"edge": data[key], "at": self.from_at}
        if self.to_at is not None and "to" in data:
            data["to"] = {"edge": data["to"], "at": self.to_at}
        return data

    @model_validator(mode="after")
    def _branches(self) -> River:
        if len(self.branch_names) > self.delta_branches:
            raise ValueError(
                f"{len(self.branch_names)} branch_names given but delta_branches is "
                f"{self.delta_branches}")
        return self


def _island_position(v: Any) -> Any:
    """Accept 'south_west_offshore' as position + setting."""
    if isinstance(v, dict) and isinstance(v.get("position"), str) and "setting" not in v:
        pos = v["position"]
        for setting in ("offshore", "nearshore", "mid_river", "delta"):
            if pos.endswith("_" + setting):
                v = {**v, "position": pos[: -len(setting) - 1], "setting": setting}
                break
    return v


class Pinned(_Model):
    """A traced district imported as fixed (scope 4.3)."""
    source: str = Field(description="Repo path of the traced SVG, in the conventions of "
                                    "maps/corporate_core_v*.svg (coast, highway, building, "
                                    "landmark layers).")
    rotation_deg: Annotated[float, Field(ge=-360.0, le=360.0)] = Field(
        0.0, description="Counterclockwise turn of the traced map.")


class Island(_Model):
    name: Name
    position: Annotated[Direction | Literal["center"], WithJsonSchema({
        "type": "string",
        "pattern": "^(north|north_east|east|south_east|south|south_west|west|north_west|center)"
                   "(_(offshore|nearshore|mid_river|delta))?$",
    })] = Field(
        description="Where on the map, relative to the center. Shorthand "
                    "'south_west_offshore' sets position and setting together.")
    setting: IslandSetting = "offshore"
    river: Name | None = Field(None, description="River for mid_river and delta islands.")
    area_km2: Annotated[float, Field(gt=0.0, le=20.0)] = 0.5
    pinned: Pinned | None = Field(
        None, description="The island is a traced district (its coast, roads and buildings "
                          "kept as drawn); area_km2 then comes from the tracing.")

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, v: Any) -> Any:
        return _island_position(v)

    @model_validator(mode="after")
    def _pinned_at_sea(self) -> Island:
        if self.pinned is not None and self.setting not in ("offshore", "nearshore"):
            raise ValueError("a pinned island sits in the sea (offshore or nearshore)")
        return self

    @model_validator(mode="after")
    def _river_needed(self) -> Island:
        if self.setting in ("mid_river", "delta") and not self.river:
            raise ValueError(f"setting '{self.setting}' needs 'river' (the river it sits in)")
        if self.setting in ("offshore", "nearshore") and self.river:
            raise ValueError(f"'river' only applies to mid_river and delta islands, "
                             f"not '{self.setting}'")
        return self


class NamedBridge(_Model):
    name: Name
    kind: BridgeKind = "road"
    connects: Annotated[list[str], Field(min_length=2, max_length=2)] = Field(
        description="Two districts, islands, places or exits ('west_exit') it joins.")
    crosses: str | None = Field(None, description="River, channel or 'sea'/'bay' it spans.")
    landmark: bool = True
    tunnel: bool | None = Field(
        None, description="True: an immersed tube instead of a bridge where one fits (M9); "
                          "false: always a bridge; left out: as highways.tunnels.water "
                          "decides.")


class Bridges(_Model):
    density: Fraction = Field(0.5, description="Road bridges per crossing opportunity.")
    footbridge_density: Fraction = Field(0.5, description="Low footbridges over canals.")
    transit_crossing: TransitCrossing = Field(
        "auto", description="Transit lines on their own bridges or as a second deck.")
    named: list[NamedBridge] = Field(default_factory=list)


class Water(_Model):
    coast: Coast | None = None
    rivers: list[River] | None = Field(None, description="Left out: one default river.")
    islands: list[Island] = Field(default_factory=list)
    district_separation: Separation = "water_preferred"
    boundary_water_share: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        0.6, description="water_preferred: target share of the boundary between neighboring "
                         "districts that runs along water (rivers, channels, separation "
                         "canals). The build adds separation channels, preferring boundaries "
                         "that already run near water, until the share is reached.")
    bridges: Bridges = Field(default_factory=Bridges)


# ---------------------------------------------------------------------------
# Highways and transit
# ---------------------------------------------------------------------------

class NamedHighway(_Model):
    name: Name
    route: Annotated[list[str], Field(min_length=2)]
    reuse: bool = Field(True, description="False: the route keeps to its own line and crosses "
                                          "the highways it meets instead of running along "
                                          "them (a crosstown; M12 builds a stack where it "
                                          "crosses one with room).")


class Tunnels(_Model):
    water: TunnelWater = Field(
        "auto", description="Immersed tubes under rivers, channels and the bay for highway "
                            "crossings (M9): 'auto' where a bridge does not fit (a sea crossing "
                            "over 600 m of water); 'prefer' every river and sea crossing where a "
                            "tube fits; 'never' bridges only. A named crossing stays a bridge "
                            "unless its 'tunnel' asks for a tube. A tube needs a straight "
                            "approach on both banks with no junction but avenues that cross "
                            "over it or end beside it.")
    under: StrOrList = Field(
        default_factory=list,
        description="Districts a highway passes under in a cut-and-cover tunnel, with a green "
                    "lid over it, where the tunnel fits between its interchanges.")
    underpasses: Fraction = Field(
        0.5, description="Pedestrian underpasses under at-grade highways, between the "
                         "frontage streets on both sides (share of the spots that fit).")


class Highways(_Model):
    pattern: HighwayPattern = "ring_plus_spine"
    exits: list[Direction] | None = Field(None, description="Off-map exits. Default: land edges.")
    elevated_share: Fraction = Field(0.2, description="Share of highway length on viaducts.")
    named: list[NamedHighway] = Field(default_factory=list)
    tunnels: Tunnels = Field(default_factory=Tunnels)
    crossings: Literal["stack", "turbine"] = Field(
        "stack", description="Interchange where two highways cross with room for it: a "
                             "four-level stack or a turbine (each the other's fallback).")


class TransitLine(_Model):
    mode: TransitMode
    name: Name
    route: Annotated[list[str], Field(min_length=2)] = Field(
        description="Stops in order: districts, hubs, places, megasites, islands or "
                    "'<direction>_exit'. Repeat the first stop at the end for a loop.")
    altitude_m: tuple[float, float] | None = Field(
        None, description="[min, max] track altitude; default by mode, checked against mode limits.")
    through_towers: bool = Field(False, description="sky_tube only: passes through tower portals.")
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None

    @property
    def loop(self) -> bool:
        return len(self.route) > 2 and self.route[0] == self.route[-1]

    @model_validator(mode="after")
    def _mode_rules(self) -> TransitLine:
        if self.through_towers and self.mode != "sky_tube":
            raise ValueError(f"through_towers only applies to sky_tube lines, not {self.mode}")
        if self.altitude_m is not None:
            lo, hi = self.altitude_m
            mlo, mhi = presets.TRANSIT_MODES[self.mode].altitude_m
            if lo > hi:
                raise ValueError(f"altitude_m must be [min, max] with min <= max, got [{lo:g}, {hi:g}]")
            if lo < mlo or hi > mhi:
                raise ValueError(
                    f"altitude_m [{lo:g}, {hi:g}] is outside the {self.mode} range "
                    f"{mlo:g} to {mhi:g} m (scope 5.3)")
        for a, b in zip(self.route, self.route[1:]):
            if a == b:
                raise ValueError(f"route visits '{a}' twice in a row")
        return self


class Transit(_Model):
    hubs: list[str] | None = Field(
        None, description="Interchange names (districts, places or megasites). Default: transit "
                          "hub districts and transit_nexus sites.")
    lines: list[TransitLine] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Districts
# ---------------------------------------------------------------------------

RELATIONS = tuple(f"{d}_of" for d in DIRECTIONS)


class Placement(_Model):
    north_of: StrOrList = Field(default_factory=list)
    north_east_of: StrOrList = Field(default_factory=list)
    east_of: StrOrList = Field(default_factory=list)
    south_east_of: StrOrList = Field(default_factory=list)
    south_of: StrOrList = Field(default_factory=list)
    south_west_of: StrOrList = Field(default_factory=list)
    west_of: StrOrList = Field(default_factory=list)
    north_west_of: StrOrList = Field(default_factory=list)
    adjacent_to: StrOrList = Field(default_factory=list)
    edge: Edge | None = Field(None, description="Map edge or 'center'.")
    coast: bool | None = Field(None, description="True: on the sea coast. False: inland.")
    along_river: Name | None = None
    on_island: Name | None = None
    separated_by: str | None = Field(
        None, description="Boundary kind (water, river, channel, canal, sea, highway, ring_road, "
                          "rail, wall) or the name of a river.")

    def relations(self) -> list[tuple[str, str]]:
        """(direction, ref) for every directional relation."""
        out = []
        for d in DIRECTIONS:
            for ref in getattr(self, f"{d}_of"):
                out.append((d, ref))
        return out

    @model_validator(mode="after")
    def _contradictions(self) -> Placement:
        if self.edge == "center" and self.coast:
            raise ValueError("edge 'center' contradicts coast: true")
        for d in DIRECTIONS:
            opp = presets.opposite(d)
            both = set(getattr(self, f"{d}_of")) & set(getattr(self, f"{opp}_of"))
            if both and DIRECTIONS.index(d) < 4:
                raise ValueError(f"'{sorted(both)[0]}' is in both {d}_of and {opp}_of")
        return self


class Landmark(_Model):
    kind: Annotated[str, Field(pattern=SLUG_RE.pattern)] = Field(
        description="snake_case generator kind, e.g. megatower, spire, arcology, ferris_wheel.")
    name: Name | None = None
    height_m: Annotated[float, Field(gt=0, le=1500)] | None = None


class Place(_Model):
    name: Name
    kind: PlaceKind | MegasiteKind = Field(
        description="Place kind. A megasite kind (e.g. temple_complex) turns the place into a "
                    "named megasite when defaults are filled.")
    position: Edge | Literal["waterfront"] | None = Field(
        None, description="Where in the district.")


class Complex(_Model):
    kind: ComplexKind
    count: Annotated[int, Field(ge=1, le=20)] = 1


class Waterways(_Model):
    style: Annotated[
        list[WaterwayStyle],
        BeforeValidator(_to_list, json_schema_input_type=WaterwayStyle | list[WaterwayStyle]),
    ] = Field(default_factory=list, description="One style or a list.")
    density: Fraction = 0.5
    named: list[Name] = Field(default_factory=list, description="Named canals or basins.")


class Megasite(_Model):
    kind: MegasiteKind
    name: Name | None = Field(None, description="Default: '<District> <Kind>'.")
    area_km2: Annotated[float, Field(gt=0, le=10)] | None = None
    edge: Edge | None = Field(None, description="Where in the district.")
    coast: bool | None = None
    height_limit_m: Annotated[float, Field(gt=0, le=1000)] | None = Field(
        None, description="Building height cap around the site (spaceport flight cone).")


class Decks(_Model):
    """M14: an upper deck city over part of the district: a slab on columns over a cluster of
    its blocks and the local streets between them, with streets, lots and buildings of its own,
    ramps down to the ground streets, light wells with stairs and elevators."""
    height_m: Annotated[float, Field(ge=7.5, le=16)] = Field(
        9.0, description="Deck top over the ground under it (the lower level keeps 5.5 m of "
                         "clear height for traffic under the slab).")
    cover: Annotated[float, Field(ge=0.1, le=0.8)] = Field(
        0.45, description="Target share of the district's land under the deck.")
    column_m: Annotated[float, Field(ge=10, le=30)] = Field(
        18.0, description="Column grid: no point of the slab farther than about this from a "
                          "column.")
    light_m: Annotated[float, Field(ge=30, le=150)] = Field(
        70.0, description="No walkway under the deck farther than this from open sky (light "
                          "wells and the deck edge).")
    ramps: Annotated[int, Field(ge=1, le=6)] = Field(
        2, description="Two-way street ramps between the deck and the ground streets.")
    upper: Archetype | None = Field(
        None, description="Program of the buildings on the deck (default: the district's); "
                          "under the deck the lots get low buildings that fit the clear height.")
    upper_height_m: Annotated[tuple[float, float], _range(3, 600)] | None = Field(
        None, description="Height range of the buildings on the deck, over its top (default: "
                          "the district's).")


SignageKind = Literal["billboard", "banner", "holo"]


class Signage(_Model):
    """M20: the large ads on the sides and tops of the district's buildings (the shop signs
    and the neon bands over shops come with the shops, by `neon`)."""
    density: Fraction | None = Field(
        None, description="How many: 0 none, 1 the most (a neon billboard at every level of "
                          "most facades of the mid-rises and towers that face a road or "
                          "plaza); default by archetype (dense in the corporate core, "
                          "midtown, transit hubs, markets and entertainment districts, sparse "
                          "in residential and industrial ones).")
    kinds: list[SignageKind] | None = Field(
        None, description="billboard (landscape and portrait neon billboards on the "
                          "facades), banner (vertical neon banners spanning floors at a "
                          "corner, some wrapping it), holo (holo-boards over tower roofs and "
                          "projected in front of their facades); default by archetype.")


class District(_Model):
    name: Name
    archetype: Archetype
    area_share: Annotated[float, Field(gt=0.0, le=1.0)] | None = Field(
        None, description="Fraction of the land area. Missing shares split the remainder by "
                          "archetype weight.")
    placement: Placement = Field(default_factory=Placement)
    seed: Annotated[int, Field(ge=0, lt=2**31)] | None = Field(
        None, description="Per-district seed; default derived from the city seed and the name.")
    street_pattern: StreetPattern | None = None
    grid_angle_deg: Annotated[float, Field(ge=0, lt=90)] | None = None
    block_size_m: Annotated[tuple[float, float], _range(10, 600)] | None = None
    height_m: Annotated[tuple[float, float], _range(3, 1000)] | None = None
    water_separation: Separation | None = Field(None, description="Default: the city setting.")
    waterways: Waterways | None = None
    landmarks: list[
        Annotated[Landmark, BeforeValidator(_kind_shorthand, json_schema_input_type=Landmark | str)]
    ] = Field(default_factory=list)
    places: list[Place] = Field(default_factory=list)
    complexes: list[
        Annotated[Complex, BeforeValidator(_kind_shorthand, json_schema_input_type=Complex | ComplexKind)]
    ] | None = None
    megasites: list[
        Annotated[Megasite, BeforeValidator(_kind_shorthand,
                                            json_schema_input_type=Megasite | MegasiteKind)]
    ] | None = None
    skybridge_density: Fraction | None = None
    grime: Fraction | None = None
    neon: Fraction | None = None
    greenery: Fraction | None = None
    variety: Fraction | None = Field(
        None, description="M21: how far the district's towers depart from boxes (0: boxes and "
                          "mild forms, rounded or cut corners, setbacks; 1: twisted, leaning, "
                          "stacked, split, cantilevered, framed and podded towers, the twist and "
                          "lean at their most); default by archetype.")
    wealth: Fraction | None = Field(None, description="M11: base of the wealth field.")
    danger: Fraction | None = Field(None, description="M11: base of the danger field.")
    police: Fraction | None = Field(None, description="M11: base of the police presence "
                                                      "field.")
    faction: Name | None = Field(
        None, description="M11: the faction that holds the district (districts with the same "
                          "faction share it); default: a generated gang where the district is "
                          "dangerous, a corporation in corporate districts, else the police.")
    decks: Decks | None = Field(None, description="M14: a layered district: an upper deck "
                                                   "city over the ground streets.")
    signage: Signage | None = Field(None, description="M20: its buildings' large ads "
                                                      "(default by archetype).")


# ---------------------------------------------------------------------------
# City
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Terrain (M13)
# ---------------------------------------------------------------------------

At = Annotated[str, Field(description="A district name, a map direction or 'center'.")]


class Hill(_Model):
    name: Name | None = None
    at: At = Field(description="Where its top stands: a district (its middle), a direction or "
                               "'center'.")
    height_m: Annotated[float, Field(gt=0, le=400)] = Field(description="Rise of the top.")
    radius_m: Annotated[float, Field(ge=100, le=5000)] = Field(
        600.0, description="Where the slope ends; the steepest slope is about 1.5 times "
                           "height / radius.")


class Ridge(_Model):
    name: Name | None = None
    from_: At = Field(alias="from", description="One end: a district, a direction or 'center'.")
    to: At = Field(description="The other end.")
    height_m: Annotated[float, Field(gt=0, le=400)]
    width_m: Annotated[float, Field(ge=100, le=3000)] = 500.0


class Cliff(_Model):
    """A district standing on a plateau: its edges rise `height_m` over `width_m` (a cliff
    where narrow, an escarpment where wide); at the sea it is a sea cliff."""
    district: Name
    height_m: Annotated[float, Field(gt=0, le=200)]
    width_m: Annotated[float, Field(ge=10, le=600)] = 60.0
    facing: list[Direction] = Field(default_factory=list, description="Sides where the edge "
                                    "is a cliff; on the other sides the plateau rises over a "
                                    "broad slope (`slope_m`). Left out: a cliff all round.")
    slope_m: Annotated[float, Field(ge=50, le=2000)] = 400.0


class Terrain(_Model):
    """The ground (M13). Left out, the city is flat at sea level, as before M13."""
    shore_m: Annotated[float, Field(ge=0.5, le=20)] = Field(
        2.0, description="Ground over the water at a low shore.")
    inland_grade: Annotated[float, Field(ge=0, le=0.08)] = Field(
        0.0, description="How the land rises away from the sea (a fraction, 0.01 = 1%).")
    relief_m: Annotated[float, Field(ge=0, le=60)] = Field(
        0.0, description="Rolling ground: amplitude of a smooth random relief.")
    relief_scale_m: Annotated[float, Field(ge=150, le=3000)] = 600.0
    hills: list[Hill] = Field(default_factory=list)
    ridges: list[Ridge] = Field(default_factory=list)
    cliffs: list[Cliff] = Field(default_factory=list)
    flat: StrOrList = Field(default_factory=list, description="Districts levelled flat "
                                                             "(megasites always are).")


class Source(_Model):
    prompt: str | None = None
    image: str | None = Field(None, description="Repo path of the concept image, if any.")
    notes: str | None = None


class CitySpec(_Model):
    schema_ref: str | None = Field(None, alias="$schema")
    version: Literal[1] = SPEC_VERSION
    name: Name
    seed: Annotated[int, Field(ge=0, lt=2**31)] | None = Field(
        None, description="Default: derived from the name.")
    size_km: Annotated[tuple[float, float], _size(0.5, 20)] = Field(
        (3.0, 3.0), description="[width east-west, height north-south] in km.")
    source: Source | None = None
    water: Water = Field(default_factory=Water)
    highways: Highways = Field(default_factory=Highways)
    transit: Transit = Field(default_factory=Transit)
    districts: Annotated[list[District], Field(min_length=1, max_length=24)]
    terrain: Terrain | None = Field(None, description="M13: hills, ridges, cliffs, flat "
                                                      "districts. Left out: flat ground.")

    def district(self, name: str) -> District | None:
        return next((d for d in self.districts if d.name == name), None)


def json_schema() -> dict:
    schema = CitySpec.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "citygen city spec"
    return schema
