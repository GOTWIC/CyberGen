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
SlotKind = Literal["bench", "bus_stop", "kiosk", "vending", "stall", "taxi_stand", "bar_queue",
                   "smoke", "gang_spot"]
PerBand = Annotated[list[float], Field(min_length=5, max_length=5,
                                       description="A value per M11 hour band.")]


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
    """A place slot (scope 6.4): a Smart Object in the runtime (LG4) at a bench, a bus stop, a
    kiosk, a vending machine, a food stall, a taxi stand, a club's door (its queue), a bar's
    door (its smokers), a gang's spot; its use points, the walkway its users leave and come
    back to, how many use it by hour band."""
    id: str = Field(description="`slot.<owner id>` (a door's: `slot.<door>.<kind>`; a gang "
                                "spot's: `slot.<turf>.<hideout or corner>`).")
    owner_id: str
    kind: SlotKind
    behavior: Literal["sit", "wait", "buy", "eat", "queue", "smoke", "talk"]
    capacity: int = Field(description="Its use points (LG4: `len(points)`).")
    district_id: str | None = None
    tile: str
    pos: Vec3 = Field(description="The object (a door, a gang spot's middle).")
    yaw_deg: float = Field(description="The object's facing, degrees counterclockwise from east "
                                       "(LG0: the way its user faces).")
    level: int = 0
    walkway_id: str | None = Field(None, description="LG4: the walkway its users leave to use "
                                                     "it and come back to.")
    reach_m: float | None = Field(None, description="LG4: its first point to that walkway.")
    points: list[Annotated[list[float], Field(min_length=4, max_length=4)]] = Field(
        default_factory=list, description="LG4: its use points: x, y, z and the way its user "
                                          "faces (degrees counterclockwise from east).")
    use: PerBand | None = Field(None, description="LG4: its points in use per hour band.")
    dwell_s: Annotated[list[float], Field(min_length=2, max_length=2)] | None = Field(
        None, description="LG4: how long a user stays (s, from, to).")
    anim: str | None = Field(None, description="LG4: what its users play: sit, idle, talk.")
    role: Literal["crowd", "gang", "police"] = "crowd"
    place_id: str | None = Field(None, description="LG4: a door slot's place.")
    turf_id: str | None = Field(None, description="LG4: a gang spot's turf.")
    faction_id: str | None = None
    hash: str


class Place(_Model):
    """LG4: a place by its hours (scope 6.4): an AG3 shop door (a unit's use, M11's POI where it
    is one), open per hour, how busy by hour band, how long a visit lasts and its chance, its
    occupancy (people inside on a visit) by band."""
    id: str = Field(description="`place.<door>`.")
    spawn_id: str = Field(description="Its door's spawn point.")
    building_id: str
    poi_id: str | None = None
    name: str | None = None
    kind: str = Field(description="The POI's sub (bar, club, arcade, food, clinic, ...) else the "
                                  "unit's use.")
    use: str
    district_id: str | None = None
    tile: str
    pos: Vec3
    yaw_deg: float
    level: int = 0
    walkway_id: str
    hours: Annotated[list[int], Field(min_length=2, max_length=2,
                                      description="Open from, to (to < from runs past "
                                                  "midnight; 0, 24 always).")]
    open: Annotated[list[int], Field(min_length=24, max_length=24)]
    busy: PerBand = Field(description="How busy by band (its door's share while open).")
    visit: PerBand = Field(description="A passer-by's chance to go in by band.")
    dwell_s: Annotated[list[float], Field(min_length=2, max_length=2)]
    occupancy: PerBand = Field(description="People inside on a visit by band.")
    slot: str | None = Field(None, description="Its door's slot kind (a club's queue, a bar's "
                                               "smokers).")
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
    turf: str | None = Field(None, description="LG4: the gang turf its middle is in (its gang "
                                               "members walk only their turf's walkways).")
    gang: PerBand | None = Field(None, description="LG4: gang members walking on it per band.")
    patrol: bool = Field(False, description="LG4: police patrol it (the police field at least "
                                            "the patrol minimum, on the ground).")
    field: float | None = Field(None, description="LG4: M11's police field at its middle.")
    police: PerBand | None = Field(None, description="LG4: police on foot on it per band.")
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
    police: PerBand | None = Field(None, description="LG4: patrol cars on it per band.")
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
    places: list[Place] = Field(default_factory=list, description="LG4: the places (shop "
                                                                  "doors by their hours) in "
                                                                  "the tile.")


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
    outfits: dict = Field(default_factory=dict, description=(
        "LG2: the look groups, each district's people by group, per district and group the "
        "colors a person's three dye channels draw from (sRGB), each district's wear, the "
        "weather the outfits are drawn for, the looks per character."))
    library: dict = Field(default_factory=dict)
    persons: dict[str, list[float]] = Field(
        default_factory=dict, description="Per pool slot its draws (seed, character, scale, "
                                          "gait, pace, tint: an index into the district's "
                                          "palette where it comes out; LG2: look, the "
                                          "library's look it wears, and group, its group; "
                                          "LG4: role, its index in `roles`' names: 0 the "
                                          "crowd, 1 a gang member, 2 police).")
    roles: dict = Field(default_factory=dict, description=(
        "LG4: the role names (`presets.ROLE_CODES`) and how many pool slots each keeps (gang "
        "members and police wear their group's looks)."))
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
    police_slots: list[int] = Field(default_factory=list, description=(
        "LG4: the pool slots kept for patrol cars (of `police_model`, in `police_paint`)."))
    police_model: str | None = None
    police_paint: list[float] = Field(default_factory=list, description=(
        "LG4: the patrol cars' livery, 9 floats (three linear colors, AG18's paint channels)."))
    totals: dict
    hash: str


class TileIndex(_Model):
    tile: str
    file: str = Field(description="`spawns/<tile>.json`, relative to the plan.")
    spawns: int
    slots: int
    walks: int = 0
    drives: int = 0
    places: int = 0
    sha256: str = Field(description="sha256 of the tile file's bytes.")


class PlacesPlan(_Model):
    """LG4: life at places (scope 6.4): the slot kinds (behavior, clip, points, dwell, use by
    band), the place kinds by their hours, a visit's chance; totals (slots and their users by
    kind and band, places open by hour by kind) and what was left out."""
    hour: int
    slot_kinds: dict = Field(description="`presets.SLOT_KINDS`, and each kind's code.")
    kinds: list[str] = Field(description="Slot kinds by the runtime's code.")
    behaviors: list[str]
    anims: list[str]
    place_kinds: dict
    visit_p: float
    totals: dict
    hash: str


class Turf(_Model):
    """LG4: a gang's turf (M11's territory of a gang faction)."""
    id: str
    name: str | None = None
    district_id: str
    faction_id: str
    faction: str
    colors: list[str] = Field(description="Its members' dye colors (sRGB), its own first.")
    walkways: int = Field(description="Walkways whose middle is in it (its members walk only "
                                      "these).")
    walking: PerBand = Field(description="Its members walking per band.")
    loitering: PerBand = Field(description="Its members at its spots per band.")
    spots: list[str]
    hideouts: list[str]


class GangPlan(_Model):
    """LG4: gangs on their turf: each turf, its members' groups, the loitering share, the pool's
    slots kept for gang members, what was left out (M11's gang members outside every gang
    turf)."""
    turfs: list[Turf]
    groups: list[float] = Field(description="Shares of groups of 1 to 4.")
    loiter: PerBand
    pool: int = Field(description="The crowd's pool slots kept for gang members.")
    want_near: float = Field(description="The most gang members wanted within the live radius "
                                         "of any tile (any band).")
    left_out: dict
    hash: str


class Precinct(_Model):
    id: str
    name: str | None = None
    district_id: str
    level: float
    station_building_id: str | None = None
    station_doors: list[str] = Field(description="The station's doors: its pairs go out and "
                                                 "come back in there.")
    police: PerBand = Field(description="M11's police in the district per band.")
    foot: PerBand
    cars: PerBand


class PolicePlan(_Model):
    """LG4: police patrols by the police field: per precinct its police on foot (in pairs) and in
    patrol cars, the patrol minimum, the pool slots kept (crowd and traffic), the livery."""
    precincts: list[Precinct]
    patrol_min: float
    car_share: float
    per_car: float
    pair: int = 2
    pool: int = Field(description="The crowd's pool slots kept for police on foot.")
    cars: int = Field(description="The traffic's pool slots kept for patrol cars.")
    want_near: dict = Field(description="The most police on foot and patrol cars wanted within "
                                        "the live radii of any tile (any band).")
    left_out: dict
    hash: str


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


class TransitPlan(_Model):
    """LG6: transit (scope 6.6): the modes' runs and trains, the settings, per line its
    summary (its cycle, trains and headways by band, stops, train ids); the timetables
    themselves in `timetables.json` (`Timetables`)."""
    hour: int
    modes: dict = Field(description="`presets.TRANSIT_MODES`: speeds, dwells, cars, tracks.")
    settings: dict = Field(description="`presets.TRANSIT`.")
    lines: list[dict]
    file: str = Field(description="`timetables.json`, relative to the plan.")
    sha256: str = Field(description="sha256 of its bytes.")
    totals: dict
    hash: str


class Stop(_Model):
    """LG6: a station's stop on a line: where along the track (m) its platform's middle is, how
    far off and to which side (+1 left of the track's way), the walkway people board from and
    the height they stand at, the people leaving and boarding a train calling there per band."""
    station_id: str
    name: str | None = None
    kind: str | None = None
    s: float
    off_m: float
    dz_m: float
    side: float
    walkway_id: str | None = None
    platform_m: float
    point: Vec3
    board_z: float
    board_level: bool = Field(description="People board at the doors' level (else at the "
                                          "point over a door: a concourse, a pylon sky "
                                          "station's platforms over the tube).")
    half_m: float = Field(description="The platform deck's half width across the track (0: a "
                                      "concourse over it).")
    clear_m: float = Field(description="People on the platform keep this far off the line's "
                                       "middle (its trains), 0 none.")
    riders_h: PerBand = Field(description="The station's street accesses' people a hour.")
    calls_h: PerBand = Field(description="Trains calling there a hour (every line and way).")
    board: PerBand
    alight: PerBand


class Timetable(_Model):
    """LG6: a line's timetable. Its track (`points`, its length along them in 3D), the turn
    points (an open line runs between them there and back; a loop's start and its end round),
    the cycle (`cycle_s`) sampled every `sample_s` s (`samples`: the cycle's coordinate c, along
    the track from the first turn point, out and then back for an open line), the stop events
    on it ([arrive, depart, stop index or -1 for a turn without a station, way]), the trains
    round the cycle per band (evenly spaced), their ids."""
    id: str
    name: str
    mode: str
    color: str
    loop: bool
    length_m: float
    closing_gap_m: float
    turn: Annotated[list[float], Field(min_length=2, max_length=2)]
    D: float = Field(description="One way's length between the turn points (m).")
    cycle_s: float
    train_m: float
    cars: int
    car: dict = Field(description="The train as drawn and run (`presets.TRANSIT_MODES`): its "
                                  "cars' size, floor, base over the line, its track off the "
                                  "line's middle, its doors, which sides open (1 its right, 2 "
                                  "both), whether people board from the walkway's level.")
    points: list[Vec3]
    stops: list[Stop]
    headway_asked_min: PerBand
    trains: Annotated[list[int], Field(min_length=5, max_length=5)]
    headway_min: PerBand
    notes: list[str]
    train_ids: list[str]
    sample_s: float
    samples: list[float]
    events: list[list[float]]
    runs: dict


class Timetables(_Model):
    city: str
    lines: list[Timetable]


class AirWaterPlan(_Model):
    """LG7: air and water (scope 6.7): the kinds' runs and sizes, the settings, per kind its
    routes and vehicles by band; the routes themselves in `airwater.json` (`AirWater`)."""
    hour: int
    vehicles: dict = Field(description="`presets.AW_VEHICLES`: speeds, rates, dwells, sizes.")
    settings: dict = Field(description="`presets.AIR` and `presets.WATER`.")
    kinds: dict
    file: str = Field(description="`airwater.json`, relative to the plan.")
    sha256: str = Field(description="sha256 of its bytes.")
    totals: dict
    hash: str


class AwRoute(_Model):
    """LG7: a route something flies or sails, a closed path run to a timetable: its points (x,
    y, z absolute: over the ground datum on a flat city, over sea level on a terrain one; and
    the heading the vehicle faces there, degrees counterclockwise from east), its length (3D),
    its cycle sampled every `sample_s` s (`samples`: m along the path), its dwells
    ([arrive, depart, what (`airwater.EVENT_CODES`), the pad, roof, pier or berth]), its
    vehicles per hour band, evenly round the cycle."""
    id: str
    kind: Literal["car", "drone", "police", "media", "aircraft", "shuttle", "boat", "taxi",
                  "ferry", "ship"]
    district_id: str | None = None
    model: str = Field(description="AG18's hover car (a car's, a police flier's) or the kind's "
                                   "stand-in (the exporter's `AIRWATER_MODELS`).")
    color: str
    serves: list[str]
    water_id: str | None = None
    points: list[Annotated[list[float], Field(min_length=4, max_length=4)]]
    length_m: float
    cycle_s: float
    sample_s: float
    samples: list[float]
    events: list[list]
    counts: Annotated[list[int], Field(min_length=5, max_length=5)]
    top_mps: float
    vehicle_ids: list[str]
    moored: bool = False
    cut: str | None = Field(None, description="A body's route cut short (why).")


class AwPad(_Model):
    """LG7: a pad (M3's av pads and helipads, a spaceport's launch pads): its top."""
    id: str
    kind: str
    building_id: str | None = None
    district_id: str | None = None
    megasite_id: str | None = None
    pos: Vec3
    size_m: float
    served: bool


class AwPier(_Model):
    """LG7: a pier (the ask `piers`, derived): where a water taxi or ferry berths, the quay or
    bank it is at, its walkway, the water and its depth there."""
    id: str
    kind: Literal["taxi", "ferry"]
    quay_id: str | None = None
    bank_id: str | None = None
    pos: Vec3
    yaw_deg: float
    berth_m: float
    walkway_id: str | None = None
    water_id: str | None = None
    depth_m: float
    pair: str | None = None


class AirWater(_Model):
    city: str
    routes: list[AwRoute]
    pads: list[AwPad]
    piers: list[AwPier]


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
    places: PlacesPlan | None = Field(None, description="LG4: slots and places by their hours.")
    gangs: GangPlan | None = Field(None, description="LG4: gangs on their turf.")
    police: PolicePlan | None = Field(None, description="LG4: police patrols.")
    transit: TransitPlan | None = Field(None, description="LG6: transit's timetables.")
    airwater: AirWaterPlan | None = Field(None, description="LG7: air and water routes.")
    checks: dict[str, Check]
    totals: dict


class Entry(_Model):
    """A layer 4 entry, keyed by what it belongs to."""
    key: str
    kind: Literal["life_controller", "spawner", "slots", "train", "air_route", "water_route"]
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
           "timetables": (Timetables, "lifegen transit timetables"),
           "airwater": (AirWater, "lifegen air and water routes"),
           "contribution": (Contribution, "lifegen layer 4 contribution")}


def json_schema(model: type[BaseModel], title: str) -> dict:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = title
    return schema
