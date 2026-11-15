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

# decision 12.8: stepping aside and looking now; fleeing and gathering later (storygen's hook)
REACTIONS = {"step_aside": True, "look": True, "flee": False, "gather": False}

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
    # (Delta at 23:00: at most 771 cars wanted within 800 m of any point, 1,156 at 18:00, the
    # busiest hour; the pool holds the busiest hour's within its 92%, and from a flight at
    # 150 m the roads stay full to 800 m)
    "pool": 1400,                  # cars simulated at once
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
