"""atmosgen's presets (scope sections 5 and 6): looks, weather states, light temperatures,
photometric classes, district moods by archetype, light levels, tiers and budgets.

Every value here is a default the atmos spec can override (`spec.py`). Light is in physical
units (candela, nits, kelvin, lux); a look's `reference_ev100` is the exposure its values are
set for, and the runtime scales every light by 2^(EV_scene - EV_ref) when the scene is shown
at another exposure (the play features' night is held at -3 EV100 today, decision 12.2 hands
that to AT3).
"""

from __future__ import annotations

PRESET_VERSION = 1

# --- looks and weather ------------------------------------------------------------------------

WEATHERS = ("clear", "drizzle", "rain", "fog", "smog")
LOOKS = ("neon_rain", "clear_night", "smog_dusk", "overcast_day")

# per weather state: rain rate (0 to 1), wetness the streets reach, height fog density and
# falloff, volumetric fog extinction scale, the fog's albedo (smog brown, mist blue-grey),
# wind (m/s), drops per m3 near the view
WEATHER = {
    "clear":   {"rain": 0.0, "wetness": 0.0, "fog_density": 0.004, "fog_falloff": 0.12,
                "volumetric": 0.4, "fog_albedo": "#9aa6b8", "wind_m_s": 3.0, "drops_m3": 0},
    "drizzle": {"rain": 0.3, "wetness": 0.6, "fog_density": 0.012, "fog_falloff": 0.1,
                "volumetric": 0.8, "fog_albedo": "#8f9bb0", "wind_m_s": 4.0, "drops_m3": 6},
    "rain":    {"rain": 0.8, "wetness": 1.0, "fog_density": 0.018, "fog_falloff": 0.08,
                "volumetric": 1.0, "fog_albedo": "#8a97ad", "wind_m_s": 6.0, "drops_m3": 18},
    "fog":     {"rain": 0.0, "wetness": 0.4, "fog_density": 0.06, "fog_falloff": 0.05,
                "volumetric": 1.6, "fog_albedo": "#a7b0bd", "wind_m_s": 1.5, "drops_m3": 0},
    "smog":    {"rain": 0.0, "wetness": 0.1, "fog_density": 0.04, "fog_falloff": 0.04,
                "volumetric": 1.3, "fog_albedo": "#9c8a6c", "wind_m_s": 1.0, "drops_m3": 0},
}

# a look: the start hour and weather, the exposure its light is set for (reference_ev100,
# by night; the day's comes from the sun), bloom, the grade (shadows and highlights tint),
# the night sky (moon share of the sun, cloud deck height and how much city light it takes).
# The night's reference exposure is the one its streets' light is exposed right at: a road
# at E lux (reflectance about 0.08) shows L = 0.08 E / pi cd/m2, middle gray at
# EV100 = log2(8 L); AT0 set 3 for its 52 lx streets, AT1's streets average 15 to 18 lx: 1.5
# (the runtime shows the scene at the play features' -3 and scales every light by
# 2^(-3 - reference) until AT3 moves the exposure)
LOOK = {
    "neon_rain": {"hour": 23.0, "weather": "rain", "reference_ev100": 1.5, "bloom": 0.9,
                  "grade_shadows": "#163a52", "grade_highlights": "#ff4fb4",
                  "saturation": 1.1, "contrast": 1.08, "grain": 0.15, "chromatic": 0.15,
                  "moon": 0.0, "stars": 0.0, "cloud_deck_m": 420.0, "cloud_glow": 1.0},
    "clear_night": {"hour": 22.0, "weather": "clear", "reference_ev100": 1.0, "bloom": 0.6,
                    "grade_shadows": "#101c33", "grade_highlights": "#ffd9a8",
                    "saturation": 1.0, "contrast": 1.05, "grain": 0.08, "chromatic": 0.05,
                    "moon": 0.03, "stars": 0.4, "cloud_deck_m": 0.0, "cloud_glow": 0.0},
    "smog_dusk": {"hour": 19.5, "weather": "smog", "reference_ev100": 7.0, "bloom": 0.7,
                  "grade_shadows": "#2a2035", "grade_highlights": "#ffb066",
                  "saturation": 0.95, "contrast": 1.0, "grain": 0.1, "chromatic": 0.08,
                  "moon": 0.0, "stars": 0.0, "cloud_deck_m": 600.0, "cloud_glow": 0.6},
    "overcast_day": {"hour": 13.0, "weather": "fog", "reference_ev100": 12.0, "bloom": 0.3,
                     "grade_shadows": "#2d3640", "grade_highlights": "#e8ecf0",
                     "saturation": 0.9, "contrast": 0.98, "grain": 0.04, "chromatic": 0.0,
                     "moon": 0.0, "stars": 0.0, "cloud_deck_m": 900.0, "cloud_glow": 0.0},
}

# --- light color ------------------------------------------------------------------------------

# kelvin of each temperature class (agreeing with AG15's building light colors: WARM about
# 2700 K, COOL about 6000 K)
TEMPS = {"sodium": 2000, "warm": 2700, "neutral": 4000, "cool": 5600, "led_cool": 6500}

NEON = ("#ff2a6d", "#05d9e8", "#b967ff", "#ffb000", "#39ff8a", "#f2f6ff")   # AG15's ACCENTS

# --- photometric classes (the emitter ask of assetgen: a lamp's class by variant) ----------

# shape: spot (a cone along `aim`), point, rect (a lit face); intensity in candela (spot,
# point: the peak; rect: luminance times area, set from `nits` per face); reach the
# attenuation radius (m); cones in degrees; tilt the aim off straight down, toward the
# fixture's own forward (the arm's direction, over the carriageway); shadow: may cast
# shadows in the near tier; drop how far under the lamp head the light hangs (outside the
# head's mesh, scope 8's placement check).
#
# The profile (AT1) is Unreal's own, so the lux check (`lux.py`) and the runtime agree: a
# spot's intensity toward a direction gamma off its aim is
#   I(gamma) = cd * t^2,  t = clamp((cos gamma - cos outer) / (cos inner - cos outer), 0, 1)
# (flat to the inner cone, falling to 0 at the outer: `SpotAttenuation` in the engine's
# shaders), a point's cd all round, a face's cd * cos(gamma) in front of it; each times the
# window clamp(1 - (d / reach)^4, 0, 1)^2. AT1's street classes are wide (a batwing in the
# large): a cobra head 1200 cd to 62 degrees off its aim, so a carriageway lit from both
# sides between its poles (M6: every 25 to 35 m on each side, staggered) reads lit from
# lamp to lamp (#81) at about 10 to 15 lx, where AT0's 6000 cd in a 45 degree cone gave
# 52 lx under the heads and the junctions dark. Each reach is what its light needs (the
# window takes a light to 0 there): a live light's shading cost grows with the screen its
# reach covers, and AT1's first reaches (cobra 40, post top 28 with cube-map shadows, spill
# 16 m) cost 2 ms more of Delta's night than AT0's live set (docs/progress/AT1); a point
# light never casts shadows (six shadow maps).
PHOTOMETRY = {
    "cobra_head": {"shape": "spot", "cd": 1200.0, "reach_m": 30.0, "inner": 62.0,
                   "outer": 80.0, "tilt": 15.0, "source_m": 0.25, "shadow": True,
                   "drop_m": 0.3},
    "post_top":   {"shape": "point", "cd": 600.0, "reach_m": 18.0, "source_m": 0.3,
                   "shadow": False, "drop_m": 0.1},
    "wall_pack":  {"shape": "spot", "cd": 420.0, "reach_m": 18.0, "inner": 65.0,
                   "outer": 86.0, "tilt": 20.0, "source_m": 0.15, "shadow": True,
                   "drop_m": 0.2},
    "high_mast":  {"shape": "spot", "cd": 40000.0, "reach_m": 120.0, "inner": 55.0,
                   "outer": 78.0, "tilt": 0.0, "source_m": 0.8, "shadow": True,
                   "drop_m": 0.5},
    # a highway's columns: 12 m over the road, a twin arm in the median or one at the edge
    "highway":    {"shape": "spot", "cd": 2600.0, "reach_m": 45.0, "inner": 64.0,
                   "outer": 80.0, "tilt": 10.0, "source_m": 0.3, "shadow": False,
                   "drop_m": 0.3},
    "soffit":     {"shape": "spot", "cd": 140.0, "reach_m": 18.0, "inner": 60.0,
                   "outer": 82.0, "tilt": 0.0, "source_m": 0.3, "shadow": False,
                   "drop_m": 0.1},
    # a road tunnel's wall strips and an underpass's ceiling strip (AG7)
    "tunnel":     {"shape": "spot", "cd": 380.0, "reach_m": 16.0, "inner": 60.0,
                   "outer": 85.0, "tilt": 25.0, "source_m": 0.3, "shadow": False,
                   "drop_m": 0.05},
    # a station platform's downlights under its canopy
    "platform":   {"shape": "spot", "cd": 260.0, "reach_m": 14.0, "inner": 60.0,
                   "outer": 82.0, "tilt": 0.0, "source_m": 0.2, "shadow": False,
                   "drop_m": 0.05},
    "sign_face":  {"shape": "rect", "nits": 320.0, "reach_m": 35.0, "barn_deg": 80.0,
                   "out_m": 0.15, "shadow": False},
    "neon_band":  {"shape": "rect", "nits": 650.0, "reach_m": 18.0, "barn_deg": 85.0,
                   "out_m": 0.1, "shadow": False},
    "holo_face":  {"shape": "rect", "nits": 180.0, "reach_m": 30.0, "barn_deg": 85.0,
                   "out_m": 0.05, "shadow": False},
    "shop_sign":  {"shape": "rect", "nits": 450.0, "reach_m": 10.0, "barn_deg": 80.0,
                   "out_m": 0.1, "shadow": False},
    "shop_spill": {"shape": "rect", "nits": 110.0, "reach_m": 12.0, "barn_deg": 70.0,
                   "out_m": 0.25, "shadow": False, "height_m": 2.8, "sill_m": 0.3},
}
CLASSES = tuple(PHOTOMETRY)

# the lit face of each M20 / M6 sign kind (the second emitter ask: a sign's lit face as a
# rectangle), and whether its light is near-tier only (small, many)
SIGN_CLASS = {"billboard": "sign_face", "banner": "neon_band", "neon": "neon_band",
              "holo_ad": "holo_face", "shop_sign": "shop_sign"}
SIGN_NEAR_ONLY = ("shop_sign",)

# --- district moods (scope 5: palette, haze, neon density, flicker, alleys, grit) -----------

# per citygen archetype: the street lights' class and temperature, the shopfronts' light,
# neon density (a multiplier of the signs that light), flicker and broken shares at danger 1,
# alley darkness (0 lit as a street, 1 as dark as the floor allows), haze (a multiplier of
# the weather's fog), grit (0 clean, 1 gritty: wet grime, broken lights, steam), the
# undercity's light under decks
MOOD = {
    "corporate_core":        {"lamp": "cobra_head", "temp": "cool", "spill": "neutral",
                              "neon": 0.6, "flicker": 0.0, "broken": 0.0, "alleys": 0.3,
                              "haze": 0.8, "grit": 0.1, "crowns": True},
    "residential_heights":   {"lamp": "post_top", "temp": "warm", "spill": "warm",
                              "neon": 0.3, "flicker": 0.0, "broken": 0.0, "alleys": 0.4,
                              "haze": 0.7, "grit": 0.15, "crowns": True},
    "research_campus":       {"lamp": "post_top", "temp": "neutral", "spill": "cool",
                              "neon": 0.3, "flicker": 0.0, "broken": 0.0, "alleys": 0.4,
                              "haze": 0.8, "grit": 0.1, "crowns": True},
    "midtown_mixed":         {"lamp": "cobra_head", "temp": "neutral", "spill": "warm",
                              "neon": 0.8, "flicker": 0.05, "broken": 0.02, "alleys": 0.6,
                              "haze": 1.0, "grit": 0.35, "crowns": True},
    "transit_hub":           {"lamp": "cobra_head", "temp": "led_cool", "spill": "neutral",
                              "neon": 0.9, "flicker": 0.05, "broken": 0.02, "alleys": 0.6,
                              "haze": 1.0, "grit": 0.35, "crowns": True},
    "spaceport":             {"lamp": "high_mast", "temp": "neutral", "spill": "cool",
                              "neon": 0.4, "flicker": 0.0, "broken": 0.0, "alleys": 0.5,
                              "haze": 1.1, "grit": 0.3, "crowns": False},
    "entertainment_market":  {"lamp": "cobra_head", "temp": "warm", "spill": "warm",
                              "neon": 1.3, "flicker": 0.25, "broken": 0.08, "alleys": 0.8,
                              "haze": 1.2, "grit": 0.7, "crowns": False},
    "old_town":              {"lamp": "wall_pack", "temp": "sodium", "spill": "warm",
                              "neon": 1.1, "flicker": 0.3, "broken": 0.1, "alleys": 0.9,
                              "haze": 1.25, "grit": 0.8, "crowns": False},
    "megablock_residential": {"lamp": "cobra_head", "temp": "sodium", "spill": "warm",
                              "neon": 0.7, "flicker": 0.35, "broken": 0.12, "alleys": 0.9,
                              "haze": 1.2, "grit": 0.75, "crowns": False},
    "industrial_port":       {"lamp": "high_mast", "temp": "sodium", "spill": "neutral",
                              "neon": 0.3, "flicker": 0.2, "broken": 0.1, "alleys": 0.9,
                              "haze": 1.4, "grit": 0.9, "crowns": False},
}
MOOD_DEFAULT = "midtown_mixed"

# --- light levels (scope 8) and the tiers (6.1) -----------------------------------------------

# lux by walkway class: (average, minimum)
LIGHT_LEVELS = {"sidewalk": (10.0, 2.0), "crosswalk": (10.0, 2.0), "carriageway": (7.0, 1.0),
                "under_deck": (5.0, 1.0), "alley": (2.0, 0.5)}
# the lux check (AT1, scope 8): a class passes when its average over the city is at its
# target and at most UNDER_MIN_SHARE of its points fall under its minimum (broken lights
# and the dark stretches a gritty district's mood asks for: decision 12.5); in every
# district at least DISTRICT_AVG_SHARE of the average and at most DISTRICT_UNDER_SHARE
# under the minimum; an alley point never at 0 (ZERO_LX)
UNDER_MIN_SHARE = 0.05
DISTRICT_AVG_SHARE = 0.5
DISTRICT_UNDER_SHARE = 0.15
DISTRICT_MIN_POINTS = 50          # (a district with fewer points of a class is not judged)
ZERO_LX = 0.05
SAMPLE_M = 2.0                    # the check's points along every walkway and lane

# AT1's lights on fixtures the city does not have yet (scope 4.1's asks, `emitters.py`):
# poles along the roads M6 gives no street lights (highways and ramps, service roads), wall
# packs along the alleys, poles at the junction corners the lux check finds dark
ROAD_LIGHTS = {
    # class: (light class, spacing m, mounting height over the road m, arm m)
    "highway": ("highway", 42.0, 12.0, 2.5),
    "service": ("cobra_head", 30.0, 8.0, 1.5),
}
ALLEY_STEP_M = (9.0, 10.0)        # wall packs every a + b * the mood's alley darkness (m)
ALLEY_PACK_Z_M = 4.0
CORNER_POLE_Z_M = 8.0             # a corner pole's head over the ground
CORNER_ARM_M = 1.5
CORNER_MAX = 6                    # corner lights a junction gets at most
SIGNAL_ARM_M = (6.0, 0.55)        # a signal's mast arm: at most 6 m, 0.55 of the way in
SIGNAL_HEAD_Z_M = 7.0
FILL_MIN_POINTS = 3               # a walkway or road with this many points dark gets a fill
FILL_ROUNDS = 4                   # ... light at its darkest, a round at a time
FILL_SOFFIT_Z_M = 7.5             # a fill light under a deck: under its soffit
PED_STEP_M = 16.0                 # a pedestrian street's posts (M6 gives it no lamps)
PED_POST_Z_M = 4.5
TUNNEL_STEP_M = 10.0
UNDERPASS_STEP_M = 6.0
PLATFORM_STEP_M = 7.0
PLATFORM_Z_M = 3.6                # a platform's downlights over its floor

# the tiers the runtime keeps live near the view: near (shadowed), mid (unshadowed), far
# (no light: emissive points or light cards, AT7)
TIERS = {"near": {"radius_m": 60.0, "max": 16},
         "mid": {"radius_m": 300.0, "max": 512},
         "far": {"radius_m": 1500.0, "max": 0}}

# budgets: lights per 256 m cell in the plan, live and shadowed near the view, the night's
# frame time at p95, native 1440p on the PC by AG16's benchmark (decision 12.6)
BUDGETS = {"lights_per_cell": 6000, "live": 512, "shadowed": 16, "night_p95_ms": 16.7}

# --- schedules (decision 12.3: data for every hour) -------------------------------------------

def _hours(on: float, off: float, level: float = 1.0, rest: float = 0.0) -> tuple:
    """24 values: `level` from hour `on` to hour `off` (across midnight when off < on),
    `rest` otherwise."""
    out = []
    for h in range(24):
        inside = (on <= h < off) if on <= off else (h >= on or h < off)
        out.append(level if inside else rest)
    return tuple(out)


SCHEDULES = {
    "dusk_dawn": _hours(18, 7),                    # street lights: on from dusk to dawn
    "tunnel": _hours(18, 7, 1.0, 0.6),             # tunnels: always, brighter by night
    "always": _hours(0, 24),                       # tunnels, decks, stations
    "shop": _hours(9, 22, 1.0, 0.15),              # a shop's spill (its security light after)
    "food": _hours(7, 24, 1.0, 0.1),
    "bar": _hours(17, 4, 1.0, 0.05),
    "late": _hours(18, 3, 1.0, 0.1),               # clubs, arcades, neon bands
    "office": _hours(7, 20, 1.0, 0.1),
    "sign": _hours(17, 2, 1.0, 0.3),               # ads: lit through the evening, a few on
    "clinic": _hours(0, 24),
}
# a unit use to its spill schedule
USE_SCHEDULE = {"food": "food", "bar": "bar", "club": "late", "arcade": "late",
                "hotel": "always", "clinic": "clinic", "pharmacy": "late", "office": "office",
                "bank": "office"}

DEFAULTS = {"preset": "neon_rain", "tile_m": 256.0}
