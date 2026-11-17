"""lifegen's presets (scope sections 5, 6 and 9): who lives where, how busy each hour is,
what people wear, which vehicles drive, and the runtime's budgets.

Everything here is a default the life spec can override per district (`spec.py`). Values
are plain numbers, so a filled spec is canonical JSON.
"""

from __future__ import annotations

from citygen.model import HOUR_BANDS

HOURS = 24
BANDS = tuple(b[0] for b in HOUR_BANDS)


def band_of(hour: int) -> int:
    """The index of M11's hour band an hour falls in (night 0-6, morning 6-10, day 10-16,
    evening 16-20, late 20-24)."""
    h = int(hour) % HOURS
    for i, (_, a, b) in enumerate(HOUR_BANDS):
        if a <= h < b:
            return i
    return len(HOUR_BANDS) - 1


# --- population (scope 5: `population`) ------------------------------------------------------

# who is on a district's streets: residents, workers, visitors (shares, summing to 1)
MIX = {
    "corporate_core":        (0.10, 0.70, 0.20),
    "midtown_mixed":         (0.35, 0.35, 0.30),
    "transit_hub":           (0.15, 0.30, 0.55),
    "entertainment_market":  (0.20, 0.25, 0.55),
    "old_town":              (0.50, 0.20, 0.30),
    "megablock_residential": (0.70, 0.15, 0.15),
    "residential_heights":   (0.70, 0.15, 0.15),
    "research_campus":       (0.15, 0.70, 0.15),
    "industrial_port":       (0.10, 0.80, 0.10),
    "spaceport":             (0.05, 0.45, 0.50),
}
MIX_DEFAULT = "midtown_mixed"

# the shape of a day within M11's hour bands: a relative weight per hour, normalized by the
# plan so each band's mean is 1 (the band keeps M11's density; the hours inside it rise and
# fall). Office districts peak at the rushes, nightlife late, homes mornings and evenings.
_OFFICE = (0.5, 0.3, 0.2, 0.2, 0.3, 0.6, 0.9, 1.3, 1.6, 1.2, 1.0, 1.1, 1.3, 1.2, 1.0, 1.0,
           1.2, 1.6, 1.4, 1.0, 1.0, 0.9, 0.8, 0.6)
_NIGHT = (1.6, 1.3, 1.0, 0.7, 0.5, 0.4, 0.5, 0.7, 0.9, 1.1, 0.9, 1.0, 1.1, 1.0, 1.0, 1.0,
          0.9, 1.0, 1.0, 1.1, 0.8, 0.9, 1.1, 1.3)
_HOME = (0.8, 0.5, 0.3, 0.3, 0.5, 1.0, 0.8, 1.2, 1.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
         0.9, 1.0, 1.1, 1.1, 1.3, 1.1, 0.9, 0.7)
_SHIFT = (1.0, 1.0, 1.0, 1.0, 0.9, 1.1, 1.4, 1.0, 0.8, 0.8, 1.0, 1.0, 1.0, 1.0, 1.1, 1.0,
          0.9, 1.0, 1.1, 1.0, 1.0, 0.9, 1.1, 1.0)
DAY_SHAPE = {
    "corporate_core": _OFFICE, "research_campus": _OFFICE, "transit_hub": _OFFICE,
    "midtown_mixed": _HOME, "megablock_residential": _HOME, "residential_heights": _HOME,
    "entertainment_market": _NIGHT, "old_town": _NIGHT,
    "industrial_port": _SHIFT, "spaceport": _SHIFT,
}

# how long one person stays out on the street per trip (minutes): spawn rates are the
# people on the streets over this
TRIP_MIN = 15.0
# a door's weight among its district's spawn points, by what it is
SPAWN_WEIGHT = {"main": 4.0, "service": 0.5, "dock": 0.3, "garage": 1.0, "rollup": 0.2,
                "gate": 1.0, "unit": 1.5, "station": 25.0, "parking": 6.0, "taxi_stand": 4.0}
SPAWN_KINDS = ("door", "station", "garage", "taxi_stand")

# --- places (scope 6.4): props whose slots people use --------------------------------------

# prop type -> (slot kind, behavior, capacity)
SLOTS = {
    "prop.bench": ("bench", "sit", 2),
    "prop.bus_stop": ("bus_stop", "wait", 4),
    "prop.kiosk": ("kiosk", "buy", 2),
    "prop.vending_machine": ("vending", "buy", 1),
    "prop.food_stall": ("stall", "queue", 3),
}
TAXI_SLOT = ("taxi_stand", "queue", 3)

# --- styles (scope 5: `styles`, 6.2) ---------------------------------------------------------

GROUPS = ("corporate", "street", "market", "industrial", "nightlife", "techwear", "punk",
          "gang", "police")
# per archetype: fashion groups' weights, cyberware (0 none, 1 everyone heavily augmented),
# wear (0 new, 1 worn out)
STYLE = {
    "corporate_core":        ({"corporate": 6, "techwear": 3, "street": 1}, 0.45, 0.10),
    "midtown_mixed":         ({"street": 4, "techwear": 3, "corporate": 2, "nightlife": 1}, 0.35, 0.30),
    "transit_hub":           ({"street": 4, "corporate": 3, "techwear": 2, "market": 1}, 0.35, 0.30),
    "entertainment_market":  ({"nightlife": 5, "street": 3, "punk": 2, "gang": 1}, 0.50, 0.40),
    "old_town":              ({"market": 4, "street": 4, "punk": 1, "gang": 1}, 0.25, 0.60),
    "megablock_residential": ({"street": 5, "market": 2, "punk": 2, "gang": 1}, 0.30, 0.65),
    "residential_heights":   ({"street": 4, "corporate": 3, "techwear": 2}, 0.35, 0.25),
    "research_campus":       ({"techwear": 5, "corporate": 3, "street": 2}, 0.55, 0.15),
    "industrial_port":       ({"industrial": 7, "street": 2, "gang": 1}, 0.30, 0.80),
    "spaceport":             ({"industrial": 3, "techwear": 3, "corporate": 2, "street": 2}, 0.45, 0.40),
}

# a group's colors (sRGB): the stand-ins' clothing until LG2's garments; a gang's are its
# faction's color (M11), the police's its uniform blue
GROUP_COLORS = {
    "corporate": ("#22252b", "#2b3242", "#5a5f69", "#1b2433", "#8a8d93"),
    "street": ("#3f4a2f", "#2f4a6b", "#141414", "#8c2a25", "#6d6a60"),
    "market": ("#9a6a2a", "#5b3b25", "#8a3f1f", "#c2a46a", "#40382c"),
    "industrial": ("#e0681c", "#d9b21a", "#2a4a78", "#4c4c46", "#7a5a32"),
    "nightlife": ("#c21d8c", "#17b2c9", "#5e2a9e", "#0f0f12", "#e6e1ea"),
    "techwear": ("#101113", "#2a2c30", "#1d6f6b", "#4b5057", "#b8bcc2"),
    "punk": ("#b31d1d", "#0d0d0d", "#9bd11a", "#5d1a7a", "#d9d2c5"),
    "gang": ("#7a1414", "#141414", "#3a3a3a"),
    "police": ("#1d2f5c", "#24375f", "#0f1a33"),
}
SPIKE_PALETTE = 24             # colors in the spike's palette, drawn by the style's weights

# --- LG2: outfits (scope 6.2) ------------------------------------------------------------------

# a group's colors per district (the person's three dye channels drawn from them at spawn):
# its `GROUP_COLORS` shaded light and dark (`OUTFIT_SHADES`), a gang's its faction's color
# first; the rain looks wear the street's
OUTFIT_COLORS = 12
OUTFIT_SHADES = (1.0, 0.7, 1.25, 0.5)
# the weather's outfits (the hook LG8 drives with atmosgen's state; the plan's state is the
# crowd's `weather`, clear until then): the share of people in the rain looks (raincoats; an
# umbrella is a library item no one carries yet)
WEATHER_OUTFITS = {"clear": 0.0, "fog": 0.0, "smog": 0.0, "drizzle": 0.25, "rain": 0.5}
# the variety check (scope 8): at a district's busiest hour, the expected number of pairs of
# people within `VARIETY_M` of each other alike in body, face and outfit (character, look and
# colors) at most `VARIETY_PAIRS`; no look more than `LOOK_SHARE_MAX` of a district's people
VARIETY_M = 50.0
VARIETY_PAIRS = 1.0
LOOK_SHARE_MAX = 0.12

# --- the fleet (scope 6.5, decision 6) -------------------------------------------------------

# AG18's roster by what a vehicle is (the kinds lifegen drives); the kinds it lacks are
# designed on the Mac the same way, one Blender script each, and join it as packs
FLEET_KINDS = {
    "car": ("halcyon_sable", "halcyon_ridge", "vanta_r", "orrin_lumen", "orrin_pebble",
            "orrin_aria", "tanager_mino"),
    "taxi": ("tanager_cab",),
    "van": ("tanager_porter", "brakk_mule"),
    "pickup": ("brakk_hauler", "brakk_bastion"),
    "hover": ("kestrel_dart", "kestrel_meridian", "kestrel_atlas"),
}
MISSING_KINDS = ("bus", "truck", "motorbike", "bike", "flying_car", "drone", "boat")

# --- the runtime (scope 9, decision 7) -------------------------------------------------------

BUDGETS = {
    "frame_p95_ms": 20.0,          # decision 12.7 (2026-11-13): native 2560 x 1440 on the PC
    "people_view": 2000,           # simulated people within `view_m` (the goal)
    "vehicles_view": 500,
    "view_m": 300.0,
    "full_detail": [150, 250],     # people at full detail near the view
}

# decision 12.8: stepping aside and looking (LG3, LG8); fleeing and gathering (LG8, storygen's
# hook: a danger at a point, `CityGenLife.Panic`); the settings are LG8's `REACTION`
REACTIONS = {"step_aside": True, "look": True, "flee": True, "gather": True}

# --- the spike (LG0): plain stand-ins on one district ---------------------------------------

SPIKE = {
    "hour": 23,                    # the benchmark's night
    "people_max": 2000,            # at most the budget's people
    "radius_m": 450.0,             # round the district's middle (the benchmark's walk)
    "cars": 0,                     # (LG0's 40 cars on its lanes; LG5's traffic drives the city)
    "walk_speed": [1.15, 1.55],    # m/s, per person by hash
    "drive_speed": [7.0, 11.0],    # m/s (25 to 40 km/h)
    "car_gap_m": 9.0,              # a car keeps this far behind the one ahead on its lane
}
# cars_steam (Swagnik: slower on smaller roads): a lane's cruise speed by its road's class
# (m/s: 80, 50, 35, 25 and 15 km/h, a city's), each car's own a share of it
# (`DRIVE["vary"]`); through a junction its connector the slower of its roads' times
# `junction`; on a bend at most sqrt(`lateral` R) (m/s2 of sideways pull, comfortable), never
# under `crawl` (a dead end's turning bulb, whose hairpin connector is tighter than a car turns),
# braking before it at `brake`
DRIVE_SPEEDS = {"highway": 22.0, "avenue": 14.0, "street": 9.5, "service": 7.0, "alley": 4.5}
DRIVE = {"junction": 0.7, "lateral": 2.0, "brake": 2.5, "crawl": 2.0, "vary": [0.9, 1.08],
         "default": "street"}
# walkway kinds the stand-ins walk (not elevators, skybridges or stairs in LG0)
SPIKE_WALK_KINDS = ("sidewalk", "crossing", "crosswalk", "alley", "promenade",
                    "pedestrian_street", "path", "footbridge")

# --- LG3: crowds on the streets (scope 6.3) --------------------------------------------------

# the city's crowd: people on every walkway at its street's density by hour (M11's per
# segment and band, on its sidewalks; the off-street walkways at their district's mean
# street density times `OFFSTREET`), simulated round the view only: every walkway within
# `live_m` of the view is live (past the far tier's 300 m and its fade, so a walkway coming
# alive or going is never seen), the rest a number per walkway and hour; at most `pool`
# people at once (the budget's 2,000 within 300 m: pool (300 / live_m)^2 of them); trips
# from and to doors, stations, garages and taxi stands lasting `trip_s` on average
CROWD = {
    "hour": 23,                    # the runtime's hour until LG8 reads atmosgen's
    "pool": 2400,                  # people simulated at once (the budget's 2,000 in 300 m)
    "live_m": 340.0,               # walkways within this of the view (3D) are live
    "trip_s": 600.0,               # a trip's mean length out of doors (s)
    # groups of 1 to 5 people walking together (shares)
    "groups": [0.56, 0.26, 0.11, 0.05, 0.02],
    "group_gap_m": 0.9,            # a group's members this far apart along the walkway
    # the share crossing a signalized crosswalk against the signal: at danger 0 and 1
    "jaywalk": [0.01, 0.30],
    # local avoidance: a person reacts to others within `reach_m` ahead on its walkway, keeps
    # `personal_m` from them, and steps aside from the player within `player_m`; people
    # farther than `avoid_m` from the view are not tested (too far to see it)
    "reach_m": 4.0, "personal_m": 0.75, "player_m": 2.5, "avoid_m": 90.0,
    # speeds: stairs (a share of the pace), an escalator (a share of the pace plus its own
    # m/s), an elevator (m/s along its shaft, the waiting folded in; hidden inside)
    "stairs": 0.6, "escalator": [0.3, 0.5], "elevator": 0.6,
}
# a walkway kind's people per meter relative to its district's mean sidewalk density (the
# walkways that belong to no road segment: a junction's corners and crossings, crosswalks,
# park and door paths, skybridges, platforms, stairs; people pass through a junction, so
# fewer stand in it; elevators carry people through, none stand in them)
OFFSTREET = {"crossing": 0.6, "crosswalk": 0.4, "path": 0.3, "skybridge": 0.25,
             "elevated": 0.6, "stairs": 0.4, "escalator": 0.4, "elevator": 0.0,
             "footbridge": 0.5, "underpass": 0.4, "concourse": 0.6}
OFFSTREET_DEFAULT = 0.3
# every walkway kind the runtime knows (its code: an index here; unknown kinds as "path")
WALK_KIND_CODES = ("sidewalk", "crossing", "crosswalk", "path", "alley", "promenade",
                   "pedestrian_street", "footbridge", "stairs", "escalator", "elevator",
                   "skybridge", "elevated", "underpass", "concourse")
# a door's weight among a district's spawn points by AG3's door kind (a shop's unit door,
# `shop.<use>`, as a unit); the rest as `SPAWN_WEIGHT`
DOOR_WEIGHT = {"shop.lobby": 3.0, "shop.bar": 2.0, "shop.club": 2.5, "shop.food": 1.8}

# lifegen_people_fixes: how often a character of the people library is drawn, by the
# MetaHuman preset it is made from (1 for a preset not named). The presets' own bodies carry
# their build: measured on the assembled characters (the creator's body constraints, waist
# over height, 2026-11-14), Bo 0.70, Bruce 0.65, Dominic 0.69, Jorge 0.86, Orlando 0.60 and
# Lani 0.57 against 0.37 to 0.53 for the other 18: a quarter of the library and five of its
# twelve men heavy (Swagnik: "too many fat people"). Drawn this rarely, heavy builds are about
# 5% of a crowd; the library itself is unchanged (its hash is the built assets').
BODY_WEIGHT = {"Bo": 0.15, "Bruce": 0.15, "Dominic": 0.15, "Jorge": 0.05, "Orlando": 0.2,
               "Lani": 0.3}

# --- LG5: traffic (scope 6.5) -----------------------------------------------------------------

# the city's traffic: cars on every lane of the lane graph at its road's density by hour (M11's
# vehicles per 100 m and band per segment, over its lanes by length; the district's day shapes
# the hours within a band), simulated round the view only: every lane within `live_m` of the
# view is live (cars come alive and go past it, a car driving onto a lane that is not live
# leaves there), the rest a number per lane and hour; at most `pool` cars at once (the
# budget's 500 vehicles within 300 m: pool (300 / live_m)^2 of them), each a pool slot of a
# fixed model (the slots shared out by the districts' fleets), painted by the district it comes
# out in. Lanes coming alive and the lanes far from the view (past `refill_m` of it) keep the
# live cars at their number as cars drive out of the live region.
TRAFFIC = {
    # (Delta at 23:00 at M11's densities: 0.7 cars per 100 m of lane, one car a block, and at
    # most 771 cars wanted within 800 m of any point, 1,156 at 18:00, the busiest hour. Read
    # from the street and from a flight that is empty roads (LG5's first shots), so the
    # traffic's `scale` is 2 by default: at most 1,542 within 800 m by night, within the pool's
    # 92%; the busiest hour's is scaled down evenly to it. From a flight at 150 m the roads
    # stay full to 800 m)
    "scale": 2.0,                  # times M11's vehicles per 100 m (the fleet's busy too)
    "pool": 1800,                  # cars simulated at once
    "live_m": 800.0,               # lanes within this of the view (3D) are live
    "margin_m": 60.0,              # a live lane goes this far past live_m
    "refill_m": 450.0,             # cars making up the number come in this far off the view
    # the car following model (the intelligent driver model): its acceleration and comfortable
    # braking (m/s2), the hardest it brakes, the gap it keeps standing (m) and its time
    # headway (s), the exponent of its free road term
    "accel": 1.8, "brake": 2.6, "brake_max": 8.0, "gap_m": 2.2, "headway_s": 1.2,
    "delta": 4.0,
    # signals: a car stops this far short of a crosswalk it would cross (m), and at amber only
    # where it can stop braking at most `amber_brake` (m/s2); it does not enter a signalized
    # junction without room past it for its length and gap
    "stop_margin_m": 1.2, "amber_brake": 3.5,
    # junctions: connectors whose lines come within `conflict_m` (and 3 m in height) of each
    # other are never driven at once; a car waiting `starve_s` claims its connector, so the
    # conflicting ones wait for it; past `force_s` it goes (a guard against a jam)
    "conflict_m": 2.2, "starve_s": 6.0, "force_s": 25.0,
    # people and the player in the way: cars within `yield_m` of the view look ahead along
    # their lanes (their stopping distance and `look_s` of their speed, at least `look_min_m`,
    # at most `look_max_m`) for anyone within `lateral_m` of their line, where they are and
    # `predict_s` on at their pace, and stop `margin_m` short of them
    "yield_m": 180.0, "look_s": 1.6, "look_min_m": 8.0, "look_max_m": 45.0,
    "lateral_m": 1.45, "predict_s": 1.0, "margin_m": 2.0,
    # paints per district and model (drawn as AG18's step H draws a parked car's)
    "paints": 6,
}

# signal phases (the ask `signal_phases`, derived until citygen records them): two phases per
# signalized junction from its legs' angles (legs within 45 degrees of the first leg's line
# move in phase 0, the rest in phase 1), each crosswalk walking in the phase its crossed leg
# is stopped; the cycle, its amber and all-red; people start crossing in the first `walk_s`
# of their phase and not after (the flashing hand); a junction's offset by its id's hash
SIGNAL = {"cycle_s": 60.0, "amber_s": 3.0, "all_red_s": 2.0, "walk_s": 12.0}

# --- LG4: life at places (scope 6.4) ------------------------------------------------------------

# the place slots people use (Smart Objects in the runtime): per kind its behavior, the clip
# family its users play (`sit` the sample's bench loop, `idle` a standing idle, `talk` the
# idle breaks), its use points in the object's own frame (x along its yaw, y to its left, m;
# each with the way its user faces, degrees from the object's yaw: a bench's sitter faces away
# from its back, at local -y), how long a user stays (s), and per hour band the share of its
# points in use where its walkway has `SLOT_REF_PER_M` people a meter (fewer where quieter,
# never under `SLOT_USE_MIN` of it)
SLOT_KINDS = {
    "bench": {"behavior": "sit", "anim": "sit", "dwell_s": [60.0, 300.0],
              "points": [[-0.45, -0.1, -90.0], [0.45, -0.1, -90.0]],
              "use": [0.15, 0.35, 0.6, 0.6, 0.35]},
    "bus_stop": {"behavior": "wait", "anim": "idle", "dwell_s": [30.0, 180.0],
                 "points": [[-1.0, 0.0, -90.0], [0.0, 0.05, -90.0], [1.0, 0.0, -90.0]],
                 "use": [0.1, 0.5, 0.4, 0.5, 0.25]},
    "kiosk": {"behavior": "buy", "anim": "idle", "dwell_s": [15.0, 60.0],
              "points": [[1.75, 0.0, 180.0], [2.6, 0.15, 180.0], [3.4, -0.1, 180.0]],
              "use": [0.15, 0.5, 0.6, 0.6, 0.4]},
    "vending": {"behavior": "buy", "anim": "idle", "dwell_s": [10.0, 30.0],
                "points": [[0.85, 0.0, 180.0], [1.7, 0.1, 180.0]],
                "use": [0.15, 0.3, 0.35, 0.35, 0.3]},
    "stall": {"behavior": "eat", "anim": "talk", "dwell_s": [40.0, 240.0],
              "points": [[2.05, -0.6, 180.0], [2.05, 0.6, 180.0], [2.9, 0.0, 180.0]],
              "use": [0.3, 0.4, 0.7, 0.8, 0.7]},
    "taxi_stand": {"behavior": "queue", "anim": "idle", "dwell_s": [30.0, 120.0],
                   "points": [[0.0, 0.0, 0.0], [-0.9, 0.0, 0.0], [-1.8, 0.0, 0.0]],
                   "use": [0.2, 0.3, 0.3, 0.4, 0.5]},
    # (a club's door at night: a queue out of the door along the facade; a bar's smokers
    # beside its door)
    "bar_queue": {"behavior": "queue", "anim": "idle", "dwell_s": [20.0, 120.0],
                  "points": [[1.2, 0.0, 180.0], [1.2, -0.85, 180.0], [1.2, -1.7, 180.0],
                             [1.2, -2.55, 180.0], [1.2, -3.4, 180.0]],
                  "use": [0.35, 0.0, 0.0, 0.1, 0.45]},
    "smoke": {"behavior": "smoke", "anim": "talk", "dwell_s": [120.0, 420.0],
              "points": [[0.6, 1.5, 15.0], [1.5, 1.9, 205.0], [0.6, -1.6, -20.0]],
              "use": [0.3, 0.05, 0.1, 0.25, 0.4]},
    # (a gang's corner or hideout door: its members in a ring, talking, facing its middle;
    # its use is the turf's loiterers, `GANG`)
    "gang_spot": {"behavior": "talk", "anim": "talk", "dwell_s": [120.0, 600.0],
                  "points": [[0.9, 0.0, 180.0], [0.0, 0.9, -90.0], [-0.9, 0.0, 0.0],
                             [0.0, -0.9, 90.0]],
                  "use": [0.0, 0.0, 0.0, 0.0, 0.0]},
}
SLOT_PROPS = {"prop.bench": "bench", "prop.bus_stop": "bus_stop", "prop.kiosk": "kiosk",
              "prop.vending_machine": "vending", "prop.food_stall": "stall"}
SLOT_BEHAVIORS = ("sit", "wait", "buy", "eat", "queue", "smoke", "talk")
SLOT_ANIMS = ("idle", "sit", "talk")
SLOT_REF_PER_M = 0.06          # people a meter on a walkway at which a slot is used fully
SLOT_USE_MIN = 0.15
SLOT_REACH_M = 15.0            # a slot's use point at most this far from its walkway
# walkway kinds people come to a slot from (and gang corners and patrols walk)
ACCESS_KINDS = ("sidewalk", "path", "promenade", "pedestrian_street", "alley", "footbridge",
                "skybridge", "elevated", "concourse")

# places (scope 6.4: points of interest by their hours): every shop door of AG3 (a unit's use)
# and M11's POIs, open from hour to hour (`hours`, to < from runs past midnight; M11's own on a
# POI), how busy by hour band (`busy`: bars fill at night); a door's people out of and into it
# are its rate times `busy` while open, none while closed (the district's people kept by its
# other doors); a passer-by goes in for a visit (and comes back out after `dwell_s`) at
# `VISIT_P` times `busy`; a bar's or club's slot at its door (`slot`)
PLACE_KINDS = {
    "bar": {"hours": [18, 4], "busy": [0.7, 0.0, 0.1, 0.5, 1.0], "dwell_s": [300.0, 900.0],
            "slot": "smoke"},
    "club": {"hours": [21, 6], "busy": [1.0, 0.0, 0.0, 0.1, 0.9], "dwell_s": [300.0, 900.0],
             "slot": "bar_queue"},
    "arcade": {"hours": [12, 2], "busy": [0.4, 0.0, 0.5, 0.8, 1.0], "dwell_s": [120.0, 600.0]},
    "food": {"hours": [6, 22], "hours_any": [[6, 22], [0, 24], [10, 2], [7, 23]],
             "busy": [0.3, 0.6, 1.0, 0.8, 0.6], "dwell_s": [60.0, 300.0]},
    "convenience": {"hours": [0, 24], "busy": [0.3, 0.6, 0.7, 0.8, 0.6],
                    "dwell_s": [40.0, 180.0]},
    "pawn": {"hours": [9, 21], "busy": [0.0, 0.3, 0.6, 0.5, 0.2], "dwell_s": [90.0, 400.0]},
    "clinic": {"hours": [8, 20], "busy": [0.05, 0.5, 0.7, 0.5, 0.2], "dwell_s": [300.0, 900.0]},
    "ripperdoc": {"hours": [10, 22], "busy": [0.3, 0.3, 0.6, 0.8, 0.7],
                  "dwell_s": [300.0, 900.0]},
    "cyberware": {"hours": [10, 22], "busy": [0.1, 0.4, 0.8, 0.9, 0.6], "dwell_s": [90.0, 500.0]},
    "laundromat": {"hours": [7, 23], "busy": [0.0, 0.5, 0.6, 0.8, 0.5], "dwell_s": [120.0, 600.0]},
    "lobby": {"hours": [0, 24], "busy": [1.0, 1.0, 1.0, 1.0, 1.0], "dwell_s": [0.0, 0.0]},
}
PLACE_DEFAULT = {"hours": [8, 22], "busy": [0.1, 0.5, 0.8, 0.8, 0.4], "dwell_s": [90.0, 400.0]}
VISIT_P = 0.12                 # a passer-by's chance to go in at an open shop it passes
BAR_SLOT_SHARE = 0.3           # of the bars that are no POI, those with a smokers' slot

# gangs on their turf (scope 6.4, M11's factions and territories): the gang members M11 puts
# on a gang turf's streets (its segments' gang members per 100 m on their walkways in the turf)
# walk only its walkways, in groups (`groups`: shares of 1 to 4), in their gang's colors (LG2's
# gang looks, dyed in the faction's colors); a share of them by hour band (`loiter`) stands at
# its spots (hideout doors and corners: `gang_spot` slots, one per `per_spot` loiterers at the
# late band, at least one, at most `spots_max` a turf); members M11 puts outside every gang
# turf are left out (said so)
GANG = {"loiter": [0.5, 0.3, 0.35, 0.55, 0.6], "per_spot": 3.5, "spots_max": 40,
        "groups": [0.15, 0.45, 0.3, 0.1], "corner_m": 14.0}
# a faction's colors: its own first, then shades of it and dark neutrals
GANG_NEUTRALS = ("#141414", "#2a2a2a", "#3d3a36", "#1c1f26")

# police patrols (scope 6.4, M11's police field and precincts): a district's police (its
# segments' police per 100 m) walk in pairs on its patrol walkways (the police field at least
# `patrol_min` there, weighted by the field squared, so they keep near the stations) and drive
# (`car_share` of them, `per_car` a car) on its main lanes by the same weights; the precinct's
# station doors send the pairs out; patrol cars are AG18 cars in the police livery (`livery`:
# three sRGB colors, AG18's paint channels: no model of their own), the first of `car_models`
# the traffic has
POLICE = {"patrol_min": 0.25, "car_share": 0.35, "per_car": 2.0,
          "livery": ["#e8ecf2", "#0d1220", "#1f4fff"],
          "car_models": ["halcyon_sable", "orrin_lumen", "vanta_r", "halcyon_ridge"]}
# the pool's people kept for gangs and police (their looks): enough for the most wanted within
# the crowd's live radius of any tile at the crowd's hour, times `margin`, at most the share of
# the pool; the traffic's pool likewise for patrol cars
ROLES = {"margin": 1.25, "gang_max_share": 0.12, "police_max_share": 0.08,
         "car_max_share": 0.06, "min": 8}
ROLE_CODES = ("crowd", "gang", "police")

# the clips life at places plays (Epic's Game Animation Sample, the user's, copied into the
# project and retargeted by `citygen/unreal_people.py`'s `ensure_place_clips`; kept apart from
# the library's own spec, so its hash and cache stay as they are): a bench's sitting loop and
# standing idle breaks (talking, smoking, eating at a stall: the sample has no clip of any of
# these, its idle breaks stand in, an open item)
GAS_ANIM = "/Game/Characters/UEFN_Mannequin/Animations"
PLACE_CLIPS = {
    "sit": f"{GAS_ANIM}/Interactions/Bench/M_interaction_bench_idle_loop",
    "talk_a": f"{GAS_ANIM}/Idle/M_Relaxed_Stand_Idle_Break_v02",
    "talk_b": f"{GAS_ANIM}/Idle/M_Relaxed_Stand_Idle_Break_v05",
    "talk_c": f"{GAS_ANIM}/Idle/M_Neutral_Stand_Idle_Break_v03",
    # (LG8: running from a danger near the view)
    "run": f"{GAS_ANIM}/Run/M_Neutral_Run_Loop_F",
}

# --- LG6: transit (scope 6.6) ------------------------------------------------------------------

# a line's service by mode when the spec gives none (`transit.headway_min` by line name):
# minutes between trains each way per M11's hour band (night, morning, day, evening, late)
TRANSIT_HEADWAY_MIN = {
    "metro": [8.0, 3.0, 4.0, 3.0, 5.0],
    "elevated_rail": [8.0, 3.0, 4.0, 3.0, 5.0],
    "monorail": [8.0, 4.0, 5.0, 4.0, 6.0],
    "maglev": [12.0, 5.0, 6.0, 5.0, 8.0],
    "sky_tube": [5.0, 2.0, 2.5, 2.0, 3.0],
}
# how each mode runs and what its trains are (stand-ins until the Mac's designs: decision 6;
# the exporter's `unreal_life.TRANSIT_MODELS` draws them): its cruise speed (m/s), acceleration
# and braking (m/s2), the sideways pull it takes in a curve (m/s2: at most sqrt(lateral R) there,
# R the track's radius over the train's length), its dwell at a station (s), its cars, each
# car's length, gap, width and height (m), the car's floor over its body's bottom (m), its
# body's bottom over the line's z (`base_m`: the model's line is the rails' level, a monorail's
# beam top, a sky tube's axis: its tube 7 m across, M19), how far each way's track is off the line (m: two ways on the
# drawn deck's two tracks, a maglev's and a sky tube's two cars side by side on their deck or in
# their tube, a monorail's cars beside its one beam: `loop_m` a loop's one way), the platform's
# floor under its walkway (`platform_dz`, m: a sky station's platforms flank the tube at its
# floor, AG4), whether people board from the walkway's own level (a metro's concourse is 8 m
# over the track, M5: people go down at the point over a door), its doors a side per car and
# their width (m), the most people boarding or leaving a train at a station
TRANSIT_MODES = {
    "metro": {"cruise": 22.0, "accel": 1.1, "brake": 1.1, "lateral": 1.0, "dwell_s": 25.0,
              "cars": 5, "car_m": 19.0, "gap_m": 1.0, "width_m": 2.9, "height_m": 3.6,
              "floor_m": 0.3, "base_m": 0.85, "track_m": 1.6, "loop_m": 1.6,
              "platform_dz": 0.0, "board_level": False, "doors": 3, "door_m": 1.4,
              "board_max": 60},
    "elevated_rail": {"cruise": 20.0, "accel": 1.0, "brake": 1.0, "lateral": 1.0,
                      "dwell_s": 25.0, "cars": 4, "car_m": 20.0, "gap_m": 1.0,
                      "width_m": 3.0, "height_m": 3.6, "floor_m": 0.3, "base_m": 0.85,
                      "track_m": 2.15, "loop_m": 2.15, "platform_dz": 0.0,
                      "board_level": True, "doors": 3, "door_m": 1.4, "board_max": 50},
    "monorail": {"cruise": 16.0, "accel": 1.0, "brake": 1.0, "lateral": 1.0, "dwell_s": 20.0,
                 "cars": 4, "car_m": 11.5, "gap_m": 0.6, "width_m": 2.6, "height_m": 3.1,
                 "floor_m": 0.3, "base_m": -0.3, "track_m": 1.8, "loop_m": 1.8,
                 "platform_dz": 0.0, "board_level": True, "doors": 2, "door_m": 1.2,
                 "board_max": 30},
    "maglev": {"cruise": 70.0, "accel": 1.0, "brake": 1.0, "lateral": 1.0, "dwell_s": 40.0,
               "cars": 4, "car_m": 25.0, "gap_m": 0.5, "width_m": 2.9, "height_m": 3.6,
               "floor_m": 0.3, "base_m": 0.45, "track_m": 1.6, "loop_m": 0.0,
               "platform_dz": 0.0, "board_level": True, "doors": 2, "door_m": 1.4,
               "board_max": 50},
    "sky_tube": {"cruise": 30.0, "accel": 1.2, "brake": 1.2, "lateral": 1.2, "dwell_s": 20.0,
                 "cars": 3, "car_m": 9.0, "gap_m": 0.5, "width_m": 2.4, "height_m": 2.7,
                 "floor_m": 0.05, "base_m": -2.45, "track_m": 1.25, "loop_m": 0.0,
                 "platform_dz": -2.5, "board_level": True, "doors": 1, "door_m": 1.4,
                 "board_max": 20},
}
TRANSIT = {
    "turnback_s": 60.0,            # an open line's layover where it turns back
    "cross_m": 90.0,               # it crosses to the other track over this before turning
    "safety_m": 60.0,              # a train keeps this far behind the one ahead, past its length
    "step_m": 2.0,                 # the speed profile's grid along the track
    "sample_s": 0.5,               # the timetable's samples (the runtime interpolates them)
    "stop_tol_m": 25.0,            # a platform's middle at most this far off its track (plan)
    "stop_dz_m": 12.0,             # ... and this far in height
    "board_min": [2, 6, 5, 6, 4],  # people boarding (and leaving) a train at a stop at least
    "budget_trains": 120,          # trains at once over the city, at the busiest band
    "budget_cars": 600,            # cars at once
}
TRANSIT_MODE_CODES = ("metro", "elevated_rail", "monorail", "maglev", "sky_tube")

# --- LG7: air and water (scope 6.7) ----------------------------------------------------------

# what flies and what floats (the exporter's `unreal_life.AIRWATER_MODELS` draws each kind:
# AG18's hover cars where the project has them, stand-ins of the engine's basic shapes for the
# rest until the Mac's designs: decision 6)
AIR_KINDS = ("car", "drone", "police", "media", "aircraft", "shuttle")
WATER_KINDS = ("boat", "taxi", "ferry", "ship")
AW_KINDS = AIR_KINDS + WATER_KINDS
# how each kind moves: cruise (m/s), acceleration and braking (m/s2), the sideways pull it
# takes in a turn (m/s2: at most sqrt(lateral R) there), its climb and descent (m/s), its dwell
# where it lands or berths (s), its size (length, beam, height: m), how far behind the one ahead
# on its route it keeps at least (m), its draft (boats: m), how far it keeps off what it passes
# (m: a flier's margin in plan from masses, towers, tubes and signs; a boat's off banks, quays
# and moored boats), the radius it turns round in at a route's end (m, 0: a double-ended boat
# that runs back stern first), how far it banks at most (degrees)
AW_VEHICLES = {
    "car": {"cruise": 26.0, "accel": 3.0, "brake": 3.5, "lateral": 3.0, "vert": 4.0,
            "dwell_s": 45.0, "size": [4.8, 2.0, 1.5], "spacing_m": 140.0, "margin_m": 8.0,
            "turn_m": 40.0, "bank": 22.0},
    "drone": {"cruise": 14.0, "accel": 3.0, "brake": 3.0, "lateral": 3.0, "vert": 3.0,
              "dwell_s": 15.0, "size": [0.9, 0.9, 0.35], "spacing_m": 60.0, "margin_m": 3.0,
              "turn_m": 12.0, "bank": 12.0},
    "police": {"cruise": 22.0, "accel": 3.0, "brake": 3.5, "lateral": 2.5, "vert": 4.0,
               "dwell_s": 0.0, "size": [4.8, 2.0, 1.5], "spacing_m": 300.0, "margin_m": 10.0,
               "turn_m": 120.0, "bank": 18.0},
    "media": {"cruise": 12.0, "accel": 2.0, "brake": 2.0, "lateral": 1.5, "vert": 3.0,
              "dwell_s": 0.0, "size": [6.0, 6.0, 2.0], "spacing_m": 300.0, "margin_m": 12.0,
              "turn_m": 160.0, "bank": 10.0},
    "aircraft": {"cruise": 80.0, "accel": 2.0, "brake": 2.0, "lateral": 2.5, "vert": 8.0,
                 "dwell_s": 0.0, "size": [42.0, 36.0, 12.0], "spacing_m": 3000.0,
                 "margin_m": 0.0, "turn_m": 2600.0, "bank": 25.0},
    "shuttle": {"cruise": 70.0, "accel": 2.5, "brake": 2.5, "lateral": 2.5, "vert": 6.0,
                "dwell_s": 240.0, "size": [38.0, 22.0, 9.0], "spacing_m": 3000.0,
                "margin_m": 0.0, "turn_m": 2000.0, "bank": 20.0},
    "boat": {"cruise": 4.0, "accel": 0.4, "brake": 0.5, "lateral": 0.4, "vert": 0.0,
             "dwell_s": 0.0, "size": [7.0, 2.2, 1.6], "spacing_m": 80.0, "draft": 0.5,
             "margin_m": 0.4, "turn_m": 6.0, "bank": 0.0},
    "taxi": {"cruise": 6.0, "accel": 0.5, "brake": 0.6, "lateral": 0.5, "vert": 0.0,
             "dwell_s": 30.0, "size": [9.0, 2.8, 2.4], "spacing_m": 120.0, "draft": 0.7,
             "margin_m": 0.6, "turn_m": 8.0, "bank": 0.0},
    "ferry": {"cruise": 4.5, "accel": 0.3, "brake": 0.35, "lateral": 0.3, "vert": 0.0,
              "dwell_s": 60.0, "size": [26.0, 9.0, 5.5], "spacing_m": 300.0, "draft": 1.6,
              "margin_m": 3.0, "turn_m": 0.0, "bank": 0.0},
    "ship": {"cruise": 5.0, "accel": 0.08, "brake": 0.1, "lateral": 0.15, "vert": 0.0,
             "dwell_s": 1500.0, "size": [120.0, 20.0, 22.0], "spacing_m": 3000.0,
             "draft": 6.0, "margin_m": 8.0, "turn_m": 0.0, "bank": 0.0},
}
# how many: cars and drones airborne per km2 of land per M11 hour band (night, morning, day,
# evening, late), times the district's `busy`, the spec's `air.busy` and the kind's multiplier,
# cars also by wealth (0.5 + wealth); police fliers per district by its danger; media fliers
# and overflying aircraft per city; a shuttle per launch pad
AIR = {
    "cell_m": 4.0,                 # the airspace raster (drones on it; cars on 8 m cells)
    "coarse": 2,
    "slab_m": 8.0,                 # the airspace's heights in slabs of this (63 of them)
    "vmargin_m": 3.0,              # every obstacle's top and underside this much more
    "car_layers": [48.0, 60.0, 72.0, 84.0, 100.0, 116.0, 132.0, 150.0, 170.0, 190.0, 215.0,
                   240.0, 270.0, 300.0, 335.0, 370.0, 410.0, 450.0],
    "drone_layers": [26.0, 32.0, 38.0, 44.0, 52.0, 60.0, 70.0, 80.0, 92.0, 104.0],
    "police_m": [110.0, 130.0, 150.0, 175.0, 200.0, 240.0, 290.0, 330.0],
    "police_r_m": [260.0, 200.0, 150.0],
    "media_m": [180.0, 210.0, 240.0, 280.0],
    "media_r_m": [300.0, 240.0, 180.0],
    "aircraft_m": [760.0, 820.0],
    "aircraft_out_m": 2600.0,      # an overflight runs on this far past the map's edge
    "shuttle_cruise_m": 900.0,
    "shuttle_hover_m": 140.0,
    "road_cost": 1.0,              # the A*'s cost a meter over an avenue or highway ...
    "open_cost": 2.2,              # ... and elsewhere (between the towers, over lower roofs)
    "pad_over_m": 14.0,            # a flight to or from a pad cruises this far over its roof
    "ramp_m": 120.0,               # a change of layer along this much of a leg at most
    "car_density": [12.0, 28.0, 24.0, 32.0, 22.0],
    "drone_density": [1.5, 6.0, 7.0, 6.0, 3.0],
    "police": {"base": 0.5, "danger": 2.5, "band": [1.0, 0.6, 0.6, 0.8, 1.0]},
    "media": 2,
    "aircraft": 2,
    "lane_triangle_m": [700.0, 2200.0],   # a circuit's sides
    "per_circuit": 8,              # cars a circuit at most per band (the rest more circuits)
    "drone_reach_m": [150.0, 650.0],
    "drone_drop_h_m": [12.0, 45.0],
    "drone_hub_h_m": [15.0, 70.0],
    "drone_hubs_km2": 1.2,
    "routes_max": {"car": 220, "drone": 160, "police": 30, "media": 4, "aircraft": 4,
                   "shuttle": 8},
}
# boats on a river or channel per km of it per band, a canal's boat, water taxis on a tour per
# band, ferry crossings, ships at a berth
WATER = {
    "cell_m": 4.0,
    "boat_per_km": [0.6, 1.0, 1.3, 1.3, 0.9],
    "taxi_band": [1, 2, 2, 2, 1],
    "ferry_spacing_m": 450.0,      # crossings at least this far apart along a river
    "ferry_max": 4,
    "ferry_walk_m": 45.0,          # a ferry pier's shore within this of a walkway
    "ferry_min_m": 50.0,           # crossings at least this wide
    "taxi_tour": 4,                # piers a water taxi calls at, at most
    "out_m": 600.0,                # a ship comes in from this far past the map's edge
    "canal_min_m": 120.0,          # a canal's route at least this long
    "bridge_pad_m": 0.4,           # under a bridge, the boat's top this far under its deck
    "berths": 2,                   # ships at a berth line (one each)
}
AW_BUDGET = {"fliers": 500, "drones": 300, "boats": 160}
AW_SAMPLE_S = 1.0                  # the routes' cycles sampled every this many s
AW_STEP_M = 4.0                    # the speed profile's grid along a route

# --- LG8: the hour, the weather and reactions (scope 6.8) ---------------------------------------

# the crowd and the traffic by atmosgen's weather state (the runtime reads the state and the rain
# from atmosgen's controller; the plan's own state is the crowd's `weather`): per state the
# share of the hour's people out (`out`: the rest stay in, their trips ending at doors), their
# pace (`pace`), the share in the rain looks (`rain_looks`, LG2's `WEATHER_OUTFITS`), the share
# of the others holding an umbrella (`umbrella`), a passer-by's chance to stop under a cover
# its walkway passes (`shelter`), the cars' share (`cars`), speed (`speed`) and the time
# headway they add (`headway_s`); a rain state's values are reached by its rain (atmosgen's
# rain rate over the state's, `WEATHER_RAIN`), so they follow a change as the rain does
WEATHER_LIFE = {
    "clear": {"out": 1.0, "pace": 1.0, "rain_looks": 0.0, "umbrella": 0.0, "shelter": 0.0,
              "cars": 1.0, "speed": 1.0, "headway_s": 0.0},
    "drizzle": {"out": 0.88, "pace": 1.06, "rain_looks": 0.25, "umbrella": 0.3,
                "shelter": 0.06, "cars": 1.0, "speed": 0.95, "headway_s": 0.2},
    "rain": {"out": 0.6, "pace": 1.15, "rain_looks": 0.5, "umbrella": 0.6, "shelter": 0.22,
             "cars": 1.05, "speed": 0.88, "headway_s": 0.45},
    "fog": {"out": 0.9, "pace": 1.0, "rain_looks": 0.0, "umbrella": 0.0, "shelter": 0.0,
            "cars": 0.95, "speed": 0.82, "headway_s": 0.6},
    "smog": {"out": 0.8, "pace": 1.04, "rain_looks": 0.0, "umbrella": 0.0, "shelter": 0.0,
             "cars": 1.0, "speed": 0.95, "headway_s": 0.2},
}
WEATHER_KEYS = ("out", "pace", "rain_looks", "umbrella", "shelter", "cars", "speed",
                "headway_s")
WEATHER_RAIN = {"clear": 0.0, "drizzle": 0.3, "rain": 0.8, "fog": 0.0, "smog": 0.0}
# umbrellas (scope 6.1, 6.2): a canopy and a shaft (the engine's basic shapes, as LG6's
# stand-ins: a library item until the Mac designs one) over the right shoulder, drawn near and
# mid; their canopies' colors (sRGB), the share of them with a lit shaft (the city's LED
# umbrellas) and its colors; folded (not drawn) under a cover
UMBRELLA = {"colors": ("#0e0f12", "#15171c", "#1b2433", "#2a2c30", "#4a1020", "#10302e",
                       "#d8dde6", "#c21d8c", "#17b2c9", "#e0681c"),
            "lit_share": 0.3, "lit": ("#ff2fb4", "#28e6ff", "#b8ff3a", "#ffd23a"),
            "canopy_m": 1.0, "canopy_h_m": 0.3, "height": 1.2, "side_m": 0.16,
            "fwd_m": 0.08, "tilt_deg": 8.0, "shaft_m": 0.95}
# shelter (scope 6.8: under awnings and decks in rain, atmosgen's rain shadow): a walkway's
# stretches under a cover (AT5's masks: something at least `head_m` over it, on the ground
# level, of the kinds people walk outdoors), sampled every `step_m`, gaps under `join_m`
# joined, stretches under `min_m` left out; in rain a passer-by stops under one by the
# state's `shelter` chance and stands at its side for `dwell_s`, facing out
SHELTER = {"step_m": 1.0, "join_m": 1.5, "min_m": 3.0, "head_m": 2.1,
           "kinds": ("sidewalk", "path", "alley", "promenade", "pedestrian_street",
                     "crossing", "underpass", "concourse"),
           "dwell_s": [25.0, 140.0]}
# nightlife (scope 6.8): people round the open bars, clubs and arcades by night, on each one's
# door walkway, `kinds` people at its busy (LG4's, per band), on top of M11's density (the
# plan's `night` per walkway; the densities check measures M11's alone)
NIGHTLIFE = {"kinds": {"bar": 3.0, "club": 7.0, "arcade": 2.0}}
# reactions to the player and to danger (decision 12.8): people within `look_m` of the player
# standing still (waiting, queueing, sheltering) turn to look at it; a danger at a point
# (storygen's hook, `CityGenLife.Panic`) sends everyone within `flee_m` running away along
# their walkways at `flee_pace` times their pace for `flee_s`, leaving their places (police
# hold their ground); then for `gather_s` a `gather_share` of the people within `gather_m`
# come back and stand `ring_m` off it looking at it for `stay_s`; cars stopped for the player
# on foot wait (no sound in lifegen: no horn, scope 11)
REACTION = {"look_m": 6.0, "flee_m": 35.0, "flee_s": 14.0, "flee_pace": 2.4,
            "gather_m": 60.0, "gather_s": 90.0, "gather_share": 0.35, "ring_m": [9.0, 22.0],
            "stay_s": [15.0, 60.0]}
# the traffic: a car stuck this long (s) far from the view (past `stuck_far_m`) leaves, so no
# jam lasts where nobody looks (its lane refilled as any)
TRAFFIC_STUCK = {"stuck_s": 75.0, "stuck_far_m": 150.0}
