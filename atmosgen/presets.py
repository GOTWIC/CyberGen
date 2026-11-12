"""atmosgen's presets (scope sections 5 and 6): looks, weather states, light temperatures,
photometric classes, district moods by archetype, light levels, tiers and budgets.

Every value here is a default the atmos spec can override (`spec.py`). Light is in physical
units (candela, nits, kelvin, lux); a look's `reference_ev100` is the exposure its values are
set for, and the runtime shows every light at 2^(SCENE_NIGHT_EV100 - EV_ref) in Unreal's frame
(AT3: the night held at -3 EV100, the day at DAY_EV100, dusk between them by the sun's
elevation, `SUN_CURVE`; the lights keep that scale at every hour, so they read dimmer at dusk).
"""

from __future__ import annotations

PRESET_VERSION = 3

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
# AT3: the sky's part of a look: the moon's light as a share of the sun's (a full moon's; its
# phase scales it), how many stars show where the sky is clear and dark, the cloud deck (its
# height, 0 none; `cloud_cover` the share of the sky it hides; `cloud_glow` a gain on the
# city's light it shows from below). neon_rain's deck is low and nearly closed, glowing over
# the city, with the moon and a few stars in its gaps; clear_night a few high wisps.
# (smog_dusk's 19.5 h is dusk at the default latitude and day of the year, `SKY`.)
LOOK = {
    "neon_rain": {"hour": 23.0, "weather": "rain", "reference_ev100": 1.5, "bloom": 0.9,
                  "grade_shadows": "#163a52", "grade_highlights": "#ff4fb4",
                  "saturation": 1.1, "contrast": 1.08, "grain": 0.15, "chromatic": 0.15,
                  "moon": 0.03, "stars": 0.25, "cloud_deck_m": 420.0, "cloud_glow": 1.0,
                  "cloud_cover": 0.8},
    "clear_night": {"hour": 22.0, "weather": "clear", "reference_ev100": 1.0, "bloom": 0.6,
                    "grade_shadows": "#101c33", "grade_highlights": "#ffd9a8",
                    "saturation": 1.0, "contrast": 1.05, "grain": 0.08, "chromatic": 0.05,
                    "moon": 0.03, "stars": 0.6, "cloud_deck_m": 2400.0, "cloud_glow": 0.5,
                    "cloud_cover": 0.12},
    "smog_dusk": {"hour": 19.5, "weather": "smog", "reference_ev100": 7.0, "bloom": 0.7,
                  "grade_shadows": "#2a2035", "grade_highlights": "#ffb066",
                  "saturation": 0.95, "contrast": 1.0, "grain": 0.1, "chromatic": 0.08,
                  "moon": 0.02, "stars": 0.05, "cloud_deck_m": 600.0, "cloud_glow": 0.6,
                  "cloud_cover": 0.55},
    "overcast_day": {"hour": 13.0, "weather": "fog", "reference_ev100": 12.0, "bloom": 0.3,
                     "grade_shadows": "#2d3640", "grade_highlights": "#e8ecf0",
                     "saturation": 0.9, "contrast": 0.98, "grain": 0.04, "chromatic": 0.0,
                     "moon": 0.02, "stars": 0.0, "cloud_deck_m": 900.0, "cloud_glow": 0.3,
                     "cloud_cover": 0.95},
}

# --- sky and time (AT3) -----------------------------------------------------------------------

# Where and when the sun and the moon stand: the city's latitude, the day of the year, the
# moon's phase (0 new, 0.5 full; a waning gibbous by default, up in the east-southeast by the
# night's hour) and the hours the play features' day and night buttons go to (the night's is
# the look's own hour when that is night). Solar time: the sun culminates at 12.
SKY = {"latitude_deg": 35.0, "day_of_year": 172, "moon_phase": 0.62, "day_hour": 16.0,
       "night_hour": 23.0, "dusk_elevation_deg": -3.0}

# The scene's frame (Unreal's, where the plan's light is shown): the importer's sun gives 10 lux
# by day, the night is held at -3 EV100 (the play features' night, AT0 to AT2), the day at
# DAY_EV100 (what Unreal's eye adaptation reached on Delta by day, AG16's look, now locked).
# The plan's lights are in physical units and shown at 2^(SCENE_NIGHT_EV100 - reference_ev100)
# at every hour, so at dusk, under a brighter exposure, they read dimmer as real lamps do.
SUN_LUX = 10.0
SCENE_NIGHT_EV100 = -3.0
DAY_EV100 = 1.6
OVERCAST_EV = 1.0                 # a closed deck darkens the day's exposure by this much
# Curves over the sun's elevation (degrees), piecewise linear between their keys, the same in
# the plan's report, the runtime and the Blender preview:
#   ev:    the exposure, as a blend from the night's (0) to the day's (1);
#   night: MPC_CityGen's Night (the windows, neon, signs and the plan's lights by night);
#   sun:   the sun's light as a share of SUN_LUX (the sky atmosphere reddens and dims it at
#          the horizon itself; under it, it still lights the twilight sky, not the ground);
#   sky:   the sky light's intensity (its real-time capture of the sky follows the sun);
#   stars: how many of the look's stars show.
SUN_CURVE = {
    "elev":  [-90.0, -18.0, -12.0, -8.0, -5.0, -3.0, -1.0, 0.0, 2.0, 5.0, 10.0, 20.0, 90.0],
    "ev":    [0.0, 0.0, 0.0, 0.08, 0.2, 0.32, 0.48, 0.56, 0.68, 0.8, 0.92, 1.0, 1.0],
    "night": [1.0, 1.0, 1.0, 1.0, 0.95, 0.8, 0.55, 0.42, 0.22, 0.05, 0.0, 0.0, 0.0],
    "sun":   [0.0, 0.0, 0.0, 0.2, 0.55, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "sky":   [0.8, 0.8, 0.8, 0.85, 0.9, 0.95, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "stars": [1.0, 1.0, 1.0, 0.6, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
}
# the moon: its light the look's `moon` share of SUN_LUX times its lit fraction, faded in as
# it clears the horizon (MOON_RISE degrees) and as the sun's light goes, and dimmed by the
# cloud deck (MOON_CLOUD of its cover); its color; its disk's luminance in the scene
# (cd/m2 at the night's exposure: some 30 times middle grey, its maria still reading)
MOON_RISE = (-1.0, 6.0)
MOON_CLOUD = 0.75
MOON_COLOR = "#8fa8ff"
MOON_DISK_NITS = 0.5
MOON_DEG = 0.53                   # its disk's angular diameter
# the sky glow (scope 6.2): the plan's upward light flux, lit onto the cloud deck's underside.
# A light's flux (lm) from its intensity and cone; the share going up: a spot's cone above
# the horizontal, half a point's or a vertical face's; the rest lands and GROUND_REFLECT of
# it bounces; of either, ESCAPE leaves the street canyons (direct, reflected: most of the
# upward light is crown floods and the upper halves of sign faces, and most of it lands on the
# facades they are aimed at or face). The deck's illuminance is the flux convolved with a
# Lambertian emitter's footprint at its height,
#   E(r) = Phi h^2 / (pi (h^2 + r^2)^2),
# and its underside shows CLOUD_ALBEDO E / pi (cd/m2, a rain deck's dark base), times the
# look's cloud_glow. Delta's core then glows at about 0.6 cd/m2, a brightly lit city's overcast
# sky (some 13 mag/arcsec2), 0.12 on average over the city.
GROUND_REFLECT = 0.12
ESCAPE = (0.04, 0.07)
CLOUD_ALBEDO = 0.45
GLOW_CELL_M = 64.0
GLOW_REACH = 3.0                  # the footprint summed out to this times the deck's height
GLOW_HOUR = 23.0                  # the glow is the city's at this hour (scaled by Night)

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
    # AT2: the lit faces (billboards, banners, holo-boards) are rect lights the size of their
    # face, stood off `out_m` in front of the face as drawn (a facade sign's face is on its
    # 0.3 m frame, emitters.FRAME_M), so the light's plane is 0.95 m out of the wall: a rect
    # light lights only what is in front of its plane, so its own wall and what stands out of
    # it (stage 2's cornices, fins and panels reach 0.91 m, `envelope.OVERHANG_MM`) stay out
    # of it, where AT0's light 0.15 m in front of the face lit them grazing; `nits` the face's
    # luminance, `light` the share of it the light stands in for (AT0: "less of a band's
    # luminance as light"), times the sign page's own brightness (`emitters.SignColors.emit`).
    "sign_face":  {"shape": "rect", "nits": 320.0, "light": 0.6, "reach_m": 35.0,
                   "barn_deg": 80.0, "out_m": 0.65, "shadow": False},
    "banner_face": {"shape": "rect", "nits": 400.0, "light": 0.35, "reach_m": 25.0,
                    "barn_deg": 80.0, "out_m": 0.65, "shadow": False},
    "holo_face":  {"shape": "rect", "nits": 180.0, "light": 0.5, "reach_m": 30.0,
                   "barn_deg": 85.0, "out_m": 0.3, "shadow": False},
    # AT2's neon spill: neon bands and shop signs as small colored lights near them (scope
    # 6.1), near tier only: a spot stood off the sign and aimed out and down onto the
    # sidewalk (its cone short of 90 degrees, so the wall it hangs on, behind its plane, stays
    # dark), a blade sign (hung square off its wall, lit both ways) a point at its middle
    "neon_spill": {"shape": "spot", "nits": 650.0, "light": 0.3, "reach_m": 10.0,
                   "inner": 45.0, "outer": 76.0, "pitch": -35.0, "out_m": 0.5,
                   "source_m": 0.2, "shadow": False, "drop_m": 0.0},
    "shop_neon":  {"shape": "spot", "nits": 450.0, "light": 0.3, "reach_m": 8.0,
                   "inner": 45.0, "outer": 76.0, "pitch": -40.0, "out_m": 0.4,
                   "source_m": 0.15, "shadow": False, "drop_m": 0.0},
    "blade_neon": {"shape": "point", "nits": 450.0, "light": 0.2, "reach_m": 6.0,
                   "source_m": 0.3, "shadow": False, "drop_m": 0.0},
    "shop_spill": {"shape": "rect", "nits": 110.0, "reach_m": 12.0, "barn_deg": 70.0,
                   "out_m": 0.25, "shadow": False, "height_m": 2.8, "sill_m": 0.3},
    # AT2's buildings at night: crown floods (a spot below a tower's crown, `out_m` off its
    # facade, aimed up into it; its cone, intensity and reach from the geometry, `plan.floods`)
    # and facade uplights (from the podium or the ground up the shaft), in the high tier
    "crown_flood": {"shape": "spot", "cd": 0.0, "reach_m": 60.0, "inner": 20.0,
                    "outer": 36.0, "source_m": 0.3, "shadow": False, "drop_m": 0.0,
                    "out_m": 4.0, "lux": 70.0},
    "facade_flood": {"shape": "spot", "cd": 0.0, "reach_m": 60.0, "inner": 20.0,
                     "outer": 36.0, "source_m": 0.3, "shadow": False, "drop_m": 0.0,
                     "out_m": 3.0, "lux": 45.0},
    # an aviation warning light (red, ICAO and FAA obstruction lights: flashing at the top,
    # steady at the levels under it); a small light on its roof or mast, its glow the
    # runtime's beacon
    "aviation":   {"shape": "point", "cd": 300.0, "reach_m": 14.0, "source_m": 0.15,
                   "shadow": False, "drop_m": 0.0},
    # a searchlight on a roof sweeping the sky (its beam the runtime's, through the haze)
    "searchlight": {"shape": "spot", "cd": 2.0e6, "reach_m": 300.0, "inner": 1.2,
                    "outer": 2.6, "source_m": 0.4, "shadow": False, "drop_m": 0.0},
    # a crane's boom floods, straight down onto its quay and the ship
    "boom_flood": {"shape": "spot", "cd": 12000.0, "reach_m": 70.0, "inner": 48.0,
                   "outer": 72.0, "tilt": 0.0, "source_m": 0.4, "shadow": False,
                   "drop_m": 0.3},
    # an airfield's ground lights (the apron's edges, a launch pad's rim): small lights in
    # the pavement, seen more than they light
    "ground_light": {"shape": "point", "cd": 40.0, "reach_m": 5.0, "source_m": 0.1,
                     "shadow": False, "drop_m": 0.0},
}
CLASSES = tuple(PHOTOMETRY)

# the lit face of each M20 / M6 sign kind (the second emitter ask: a sign's lit face as a
# rectangle), and whether its light is near-tier only (small, many)
# AT1: the lights standing in for a lit face (a sign's, a shopfront's) cast no specular
# highlight: a glossy surface already reflects the face itself (its emissive, through Lumen),
# and a light's highlight on it is a bright ball (the play features' sign washes put one in
# every billboard). The same holds for AT2's sign lights.
NO_SPECULAR_KINDS = ("sign", "shop_sign", "spill", "neon")

# (kind, mount) -> class; a kind alone for any mount
SIGN_CLASS = {"billboard": "sign_face", "banner": "banner_face", "neon": "neon_spill",
              "holo_ad": "holo_face", "shop_sign": "shop_neon",
              ("shop_sign", "blade"): "blade_neon"}
SIGN_NEAR_ONLY = ("shop_sign", "neon")
# the plan's light kind of each sign kind: a lit face (`sign`), neon spill (`neon`, `shop_sign`)
SIGN_KIND = {"billboard": "sign", "banner": "sign", "holo_ad": "sign", "neon": "neon",
             "shop_sign": "shop_sign"}
LIT_FACES = ("sign_face", "banner_face", "holo_face")
# a sign page cell's brightness scales its light: its mean luminance over SIGN_LUMA_REF
# (a page's typical lit share), within SIGN_LUMA_SCALE
SIGN_LUMA_REF = 0.22
SIGN_LUMA_SCALE = (0.4, 1.4)
# the faces check (AT2, `lux.face_check`): a lit face's light on its own wall and on what
# stands out of it up to FACE_WALL_OUT_M (stage 2's facade parts: 0.91 m), FACE_WALL_RING_M
# round the face, at most FACE_WALL_MAX_LX; and what it throws on the facade opposite
# (reported)
FACE_WALL_OUT_M = 0.9
FACE_WALL_RING_M = 1.0
FACE_WALL_MAX_LX = 1.0
# a big face close across a narrow street is dimmed so the facade it faces gets at most
# OPPOSITE_MAX_LX (about three stops over the streets' 15 to 25 lx), never under
# OPPOSITE_MIN_SCALE of its light (the plan's first Delta run: 90th percentile 1,700 lx)
OPPOSITE_MAX_LX = 150.0
OPPOSITE_MIN_SCALE = 0.15

# --- flicker and broken lights by kind (AT2) ---------------------------------------------------

# a mood's flicker and broken shares (at danger 1) times these by kind: neon fails more often
# than an LED billboard or a street lamp; a shopfront's tube now and then; safety lights
# (aviation, an airfield's ground lights, searchlights) and the structures' lights never
FLICKER_BY_KIND = {"spill": 0.3, "sign": 0.5, "neon": 1.6, "shop_sign": 1.3, "flood": 0.25,
                   "high_mast": 0.3}
BROKEN_BY_KIND = {"flood": 0.5}
KEPT_KINDS = ("tunnel", "underpass", "station", "soffit", "aviation", "runway",
              "searchlight", "corner")
# a sign never goes dark while its face glows (assetgen draws the face lit): a broken one
# flickers deep instead, a dying tube
DYING_KINDS = ("sign", "neon", "shop_sign")
DYING_DEPTH = (0.8, 0.95)

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

# AT2's district palettes (scope 5: clean or gritty by place, decision 12.5): the neon colors
# a district's signs take where their page names none, its floods' accents where AG15 names
# none, its searchlights' tints; the corporate core cool cyan, white and violet, markets
# magenta, violet and amber, old towns red, amber and green, the port sodium amber
PALETTES = {
    "corporate_core":        ("#05d9e8", "#f2f6ff", "#b967ff", "#4d7cff"),
    "residential_heights":   ("#ffb000", "#f2f6ff", "#ff7a5c", "#05d9e8"),
    "research_campus":       ("#05d9e8", "#f2f6ff", "#39ff8a"),
    "midtown_mixed":         NEON,
    "transit_hub":           ("#05d9e8", "#ff2a6d", "#f2f6ff", "#ffb000"),
    "spaceport":             ("#f2f6ff", "#05d9e8", "#ff3b30"),
    "entertainment_market":  ("#ff2a6d", "#b967ff", "#ffb000", "#05d9e8", "#39ff8a"),
    "old_town":              ("#ff3b30", "#ffb000", "#39ff8a", "#ff2a6d"),
    "megablock_residential": ("#ffb000", "#ff2a6d", "#39ff8a", "#ff5a1f"),
    "industrial_port":       ("#ffb000", "#ff5a1f", "#39ff8a"),
}
# per archetype: the floods' white (where AG15 gives a tower no crown LEDs), the share of its
# towers whose crowns are flooded (pulled by wealth and grit, `spec.mood`), its searchlights
# (on its tallest towers, two to a roof)
FLOODS = {
    "corporate_core":        {"flood": "led_cool", "floods": 0.75, "searchlights": 0},
    "residential_heights":   {"flood": "warm", "floods": 0.3, "searchlights": 0},
    "research_campus":       {"flood": "neutral", "floods": 0.35, "searchlights": 0},
    "midtown_mixed":         {"flood": "neutral", "floods": 0.45, "searchlights": 2},
    "transit_hub":           {"flood": "led_cool", "floods": 0.5, "searchlights": 2},
    "spaceport":             {"flood": "neutral", "floods": 0.3, "searchlights": 2},
    "entertainment_market":  {"flood": "warm", "floods": 0.55, "searchlights": 4},
    "old_town":              {"flood": "sodium", "floods": 0.1, "searchlights": 0},
    "megablock_residential": {"flood": "sodium", "floods": 0.1, "searchlights": 0},
    "industrial_port":       {"flood": "sodium", "floods": 0.05, "searchlights": 0},
}
# grit (decision 12.5): in a gritty district a share of the lamps burn another temperature
# (mixed sodium, old mercury and fluorescent, new LED) and their output varies (aged lamps
# and dirty lenses); a clean one is uniform. Share and dimming grow past MIX_FROM grit.
MIX_FROM = 0.3
MIX_SHARE = 0.6                   # (of the grit past MIX_FROM)
MIX_DIM = 0.45                    # (lamps dimmer by up to this times the grit past MIX_FROM)
MIX_COLORS = {"sodium": "#ffb35c", "mercury": "#c9f0dc", "fluoro": "#e8fff4",
              "led": "#dfe8ff"}
MIX_KINDS = ("street_light", "wall_light", "alley", "road", "signal")
# searchlights a landmark gets by its kind when the spec names none (LandmarkLights)
LANDMARK_SEARCHLIGHTS = {"megatower": 4, "arcology": 3, "spire": 2, "wheel": 0}

# --- buildings and megasites at night (AT2) ---------------------------------------------------

CROWN_ZONE = (0.18, 8.0, 40.0)    # a crown's lit zone: this share of the height, within
CROWN_SIDE_MIN_M = 6.0            # a facade side narrower gets no flood
CROWN_SPLIT_M = 45.0              # a side wider gets two floods
FLOOD_UP_M = (0.3, 60.0)          # an uplight lights this share of the shaft, at most
FLOOD_THIN_ROLES = ("mast", "spire", "halo", "strut", "frame", "column", "antenna", "link",
                    "pod", "band")
AVIATION_MIN_M = 60.0             # obstruction lights on anything this tall (FAA: 200 ft) ...
AVIATION_PORT_MIN_M = 40.0        # ... this tall in a spaceport's district or megasite
AVIATION_STEP_M = 90.0            # steady levels under the flashing top, every this far down
AVIATION_COLOR = "#ff200a"
AVIATION_BLINK = (2.0, 0.3)       # (period s, on share): 30 flashes a minute
AVIATION_STEADY = 0.4             # a steady level's intensity, of the top's
SEARCHLIGHT_PITCH = (62.0, 80.0)
SEARCHLIGHT_SWEEP = (22.0, 40.0)  # sweep amplitude (deg)
SEARCHLIGHT_PERIOD = (14.0, 26.0)
HIGH_MAST_STEP_M = 90.0           # a port's yard: a high mast every this far
HIGH_MAST_Z_M = 30.0
APRON_MAST_STEP_M = 80.0          # an apron's masts along its long sides
APRON_EDGE_STEP_M = 30.0          # its blue edge lights
PAD_RIM_STEP_M = 6.0              # a launch pad's rim lights
GROUND_COLORS = {"apron": "#2a5cff", "rim": "#39ff8a", "rim_alt": "#f2f6ff"}

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
# (no light: emissive points or light cards, AT7). AT2's `high` tier: the lights seen from
# afar (crown floods and uplights, searchlights, a port's high masts), a pool of their own
# within World Partition's loading range (768 m), so they never take the street's place in
# the mid set nor it theirs
TIERS = {"near": {"radius_m": 60.0, "max": 16},
         "mid": {"radius_m": 300.0, "max": 512},
         "high": {"radius_m": 750.0, "max": 48},
         "far": {"radius_m": 1500.0, "max": 0}}
HIGH_KINDS = ("flood", "searchlight", "high_mast")
# an aviation light is live only near the view (its red glow, the runtime's beacon, is what
# shows from afar): from the air, 228 of the 512 mid lights were aviation lights at first
NEAR_KINDS = ("aviation",)

# budgets: lights per 256 m cell in the plan, live and shadowed near the view, the night's
# frame time at p95, native 1440p on the PC by AG16's benchmark (decision 12.6)
BUDGETS = {"lights_per_cell": 6000, "live": 512, "shadowed": 16, "high": 48,
           "night_p95_ms": 16.7}

# --- schedules (decision 12.3: data for every hour) -------------------------------------------

def _hours(on: float, off: float, level: float = 1.0, rest: float = 0.0) -> tuple:
    """24 values: `level` from hour `on` to hour `off` (across midnight when off < on),
    `rest` otherwise."""
    out = []
    for h in range(24):
        inside = (on <= h < off) if on <= off else (h >= on or h < off)
        out.append(level if inside else rest)
    return tuple(out)


# (AT3: the plan derives `dusk_dawn` and `tunnel` from the sun, `sky.schedules`: on from the
# sun at +3 degrees in the evening to +3 in the morning; these are their defaults)
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
