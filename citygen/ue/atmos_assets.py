"""AT0: atmosgen's runtime assets, made in the editor from code (stdlib and `unreal` only;
run headless by `citygen.unreal_atmos.make_assets`, the job in $CITYGEN_UE_JOB):

- `/Game/CityGen/Core/Atmos/MPC_CityGenAtmos`: `Rain`, `Wetness`, `FogDensity`, `WindMS`,
  driven by the CityGenAtmos actor. A collection of its own, so adding it recompiles none of
  the city's materials (MPC_CityGen's layout is untouched until AT5 gives the masters their
  wetness input).
- `M_CgRain`: rain streaks, translucent and lit by the translucency volume (so the drops take
  the neon's colors), falling by world position offset with a phase per instance, drifting
  with the wind; the actor draws them as instanced cards round the view.
- AT0's `M_CgWet` (a single DBuffer decal, puddles by a value noise) is gone since AT5: the
  wet streets are `M_CgWetColor` and `M_CgWetGloss` (below).
- AT2: `M_CgBeacon`, an aviation light's red glow (unlit, on the instanced spheres the
  controller places per cell), blinking from its per-instance data as the light does; and
  `M_CgBeam`, a searchlight's beam (additive and unlit on a cone along its aim, its color,
  glow and half length in the component's custom primitive data), fading along it, soft at
  its silhouette and where it meets a surface.
- AT3: `M_CgSky`, the sky dome's material (`is_sky`, unlit): the sky atmosphere in the view
  direction with the sun's disk, the stars, the moon with its phase, and the cloud deck at
  its height lit by the sun or the moon and from below by the city's glow (the plan's
  raster, a texture per city the controller hands its dynamic instance); the sky light's
  real-time capture takes it too, so the city under a glowing deck takes its color.

- AT4: `M_CgSteam`, a plume's puff (steam, exhaust, cooking, smoke): translucent and lit by
  the translucency volume (so the steam takes the street's and the neon's colors), each card
  of a cell's instanced plume turned to face the eye and rising from its foot by world
  position offset, its life, size, opacity and albedo from its per-instance data. The fog
  volumes are the engine's local fog volumes (no asset).

- AT5: the weather. `M_CgWetColor` and `M_CgWetGloss`, two DBuffer decals round the view
  reading the plan's masks (the city's cover and surface textures, set on their instances by
  the controller): the wet surfaces darker (the color at an opacity, the markings kept), then
  glossy with puddles as mirrors and the rain's rings in them (roughness and a world-space
  normal); `M_CgRain` cut where the pixel is under its texel's cover, leaning and drifting with
  the wind, drizzle's streaks short; `M_CgSplash` (a crown of droplets where a trace from the
  sky lands) and `M_CgDrip` (a streak falling from a low cover's edge), both instanced cards
  the controller places; `MPC_CityGenAtmos` gains `Puddles`, `WindX`, `WindY`, `Streak` and
  `Drops`.

Niagara is not used: UE 5.8 exposes no API to author a Niagara emitter from code (its
editor library builds nothing; only an engine template could be duplicated and fed user
parameters), so the effects are C++ components and these materials (decision for AT4, AT5).
"""

import json
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
FOLDER = "/Game/CityGen/Core/Atmos"
VERSION = "18"  # 2: fewer, smaller puddles (1 blotched big paved yards seen from the air);
                # 3 (AT2): M_CgBeacon and M_CgBeam; 4 to 8 (AT3): M_CgSky; 9 to 12 (AT4):
                # M_CgSteam, MPC_CityGenAtmos's SteamGain; 13 (AT5): the weather (M_CgWet
                # gone: M_CgWetColor and M_CgWetGloss, M_CgRain cut by the covers and leaning
                # in the wind, M_CgSplash, M_CgDrip, the steam drifting with the wind's heading);
                # 14: a drizzle's streets glossy too (the gloss and darkening by the wetness's
                # square root); 15: every material rebuilt from nothing (clear_material: the
                # old nodes were left beside the new), the collection's parameters kept (ids);
                # 16 (AT6): M_CgSteam lit by the city by night (SteamGlow) and kept opaque far
                # off (SteamFar, SteamFarM); 17 (AT6): the wet decals' face normal from fine
                # derivatives (a pixel's own neighbor, not its 2 x 2 quad's: a curb's edge
                # read as half floor, half wall in quads, AT5's white sawtooth along it);
                # 18 (AT7): M_CgFarGlow and M_CgFarFlat, the far city's cards, and their
                # parameters in MPC_CityGenAtmos (FarScale, FarMidM, FarHighM, FarFixM,
                # FarFade, FarPx, FarSpread)
# AT5: MPC_CityGenAtmos: the weather now (the controller blends its states): the rain's rate,
# how wet the open surfaces are and how full the puddles, the fog, the wind (its speed with
# its gusts, its heading as a unit vector), the plumes' gain, the streaks' length and the
# share of the rain cards that fall
COLLECTION = (("Rain", 0.0), ("Wetness", 0.0), ("Puddles", 0.0), ("FogDensity", 0.0),
              ("WindMS", 4.0), ("WindX", 0.77), ("WindY", -0.64), ("SteamGain", 10.0),
              ("Streak", 1.0), ("Drops", 1.0), ("SteamGlow", 0.0), ("SteamFar", 0.0),
              ("SteamFarM", 150.0),
              # AT7: the far city's cards: the lights' scale while they show (0 by day),
              # where each tier's cards fade in (m), over what share of it, a few pixels'
              # width per distance, a glow's gaussian over its square
              ("FarScale", 0.0), ("FarMidM", 300.0), ("FarHighM", 750.0), ("FarFixM", 832.0),
              ("FarFade", 0.2), ("FarPx", 0.002), ("FarSpread", 0.0982))
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty
T0 = time.time()


def meta(asset, key):
    return EAL.get_metadata_tag(asset, key) or ""


def clear_material(m):
    """Every expression of a material deleted, so it is rebuilt from nothing. (AT5:
    `delete_all_material_expressions` alone leaves about half of them: a rebuilt material
    kept its old nodes beside its new ones. Called again until none is left.)"""
    for _ in range(16):
        MEL.delete_all_material_expressions(m)
        if MEL.get_num_material_expressions(m) == 0:
            return
    raise RuntimeError(f"{m.get_name()}: its expressions could not all be deleted")


def expr(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, out, b, inp):
    if MEL.connect_material_expressions(a, out, b, inp):
        return
    names = [str(n) for n in MEL.get_material_expression_input_names(b)]
    if len(names) <= 1 and MEL.connect_material_expressions(a, out, b, ""):
        return
    want = inp.replace(" ", "").lower()
    for name in names:
        if name.replace(" ", "").lower() == want and MEL.connect_material_expressions(a, out, b, name):
            return
    raise RuntimeError(f"cannot connect {a.get_class().get_name()} to {b.get_class().get_name()}.{inp}")


def custom(m, x, y, code, inputs, out_type, name):
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    return expr(m, unreal.MaterialExpressionCustom, x, y, code=code,
                output_type=getattr(unreal.CustomMaterialOutputType, out_type),
                description=name, inputs=ins)


def collection():
    path = f"{FOLDER}/MPC_CityGenAtmos"
    c = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
    if c is not None and meta(c, "cg.atmos") == VERSION:
        return c, False
    if c is None:
        c = AT.create_asset("MPC_CityGenAtmos", FOLDER, unreal.MaterialParameterCollection,
                            unreal.MaterialParameterCollectionFactoryNew())
    # (the parameters it has kept as they are, with their ids, the missing ones added: a
    # material made by another script, AT5's rain rings in the stage 2 water master, keeps
    # finding its parameter; a list made afresh gave every parameter a new id and that
    # master's reference went stale)
    have = list(c.get_editor_property("scalar_parameters"))
    names = {str(q.get_editor_property("parameter_name")) for q in have}
    for name, v in COLLECTION:
        if name in names:
            continue
        q = unreal.CollectionScalarParameter()
        q.set_editor_property("parameter_name", name)
        q.set_editor_property("default_value", v)
        have.append(q)
    c.set_editor_property("scalar_parameters", have)
    EAL.set_metadata_tag(c, "cg.atmos", VERSION)
    EAL.save_loaded_asset(c, only_if_is_dirty=False)
    return c, True


def mpc_param(m, c, name, x, y):
    return expr(m, unreal.MaterialExpressionCollectionParameter, x, y, collection=c,
                parameter_name=name)


def material(name):
    path = f"{FOLDER}/{name}"
    m = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
    if m is not None and meta(m, "cg.atmos") == VERSION:
        return m, False
    if m is None:
        m = AT.create_asset(name, FOLDER, unreal.Material, unreal.MaterialFactoryNew())
    else:
        clear_material(m)
    return m, True


RAIN_MASK = """
float across = saturate(1.0 - abs(UV.y * 2.0 - 1.0));
float s = saturate(Streak);
float a = abs(UV.x * 2.0 - 1.0);
float along = saturate((1.0 - a / max(s, 0.05)) * 1.6);
return across * across * along;
"""
# AT5: the card falls `Fall` cm from its place over the view at its speed (drizzle slower:
# `Streak`), its phase per instance, drifting downwind as it falls (`WindX`, `WindY`, the
# wind's speed) and leaning with it: each vertex moved downwind by its height on the card
# (the card's length is its mesh's X, stood down by the instance's pitch) times the drop's
# drift over its fall
RAIN_WPO = """
float speed = Speed * (0.35 + 0.65 * saturate(Streak));
float ph = frac(Time * speed / Fall + Rnd);
float2 dir = float2(WindX, WindY);
float lean = Wind * 100.0 / speed;
float drift = Wind * 100.0 * ph * Fall / speed;
float h = -LP.x * 0.9;
return float3(dir * (drift + h * lean), -ph * Fall);
"""
# AT5: the rain kept out of what is covered: the pixel under its texel's cover (the plan's
# masks, city-wide: `Cov`, its bounds `B` = min X, min Y, size in cm; `Z` the cover's datum
# and step in cm), and the share of the cards that fall (`Drops`)
RAIN_OPACITY = """
float2 uv = (WP.xy - B.xy) / max(B.z, 1.0);
float c = 0.0;
if (all(uv > 0.0) && all(uv < 1.0)) { c = Texture2DSampleLevel(Cov, CovSampler, uv, 0).r * 255.0; }
float cz = Z.x + floor(c + 0.5) * Z.y;
float dry = (c > 0.5) ? saturate((cz - WP.z) / 30.0) : 0.0;
float on = step(Rnd, Drops);
float near_ = saturate((Depth - 30.0) / 120.0);
return Mask * Gain * saturate(Rain * 1.25) * (1.0 - dry) * on * near_;
"""


def cover_inputs(m, x, y):
    """AT5: the city-wide cover texture (its bounds and datum the controller sets on each
    instance) as a custom node's inputs: (Cov, B, Z)."""
    black = unreal.load_asset("/Engine/EngineResources/Black.Black")
    cov = expr(m, unreal.MaterialExpressionTextureObjectParameter, x, y,
               parameter_name="WetCover", texture=black)
    b = expr(m, unreal.MaterialExpressionVectorParameter, x, y + 120, parameter_name="WetBounds",
             default_value=unreal.LinearColor(0.0, 0.0, 1.0, 0.0))
    z = expr(m, unreal.MaterialExpressionVectorParameter, x, y + 240, parameter_name="CoverZ",
             default_value=unreal.LinearColor(-800.0, 50.0, 0.0, 0.0))
    return cov, b, z


def rain(c):
    m, made = material("M_CgRain")
    if not made:
        return m, False
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("translucency_lighting_mode",
                          unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1300, 0, coordinate_index=0)
    streak = mpc_param(m, c, "Streak", -1300, 100)
    mask = custom(m, -1000, 0, RAIN_MASK, ["UV", "Streak"], "CMOT_FLOAT1", "CgRainMask")
    link(uv, "", mask, "UV")
    link(streak, "", mask, "Streak")
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1300, 250)
    rnd = expr(m, unreal.MaterialExpressionPerInstanceRandom, -1300, 350)
    cov, b, z = cover_inputs(m, -1300, 450)
    gain = expr(m, unreal.MaterialExpressionScalarParameter, -1300, 850,
                parameter_name="RainOpacity", default_value=0.55)
    depth = expr(m, unreal.MaterialExpressionPixelDepth, -1300, 950)
    op = custom(m, -700, 300, RAIN_OPACITY,
                ["Mask", "WP", "Cov", "B", "Z", "Rnd", "Drops", "Rain", "Gain", "Depth"],
                "CMOT_FLOAT1", "CgRainOpacity")
    for a, n in ((mask, "Mask"), (wp, "WP"), (cov, "Cov"), (b, "B"), (z, "Z"), (rnd, "Rnd"),
                 (mpc_param(m, c, "Drops", -1300, 1050), "Drops"),
                 (mpc_param(m, c, "Rain", -1300, 1150), "Rain"), (gain, "Gain"),
                 (depth, "Depth")):
        link(a, "", op, n)
    col = expr(m, unreal.MaterialExpressionConstant3Vector, -700, -150,
               constant=unreal.LinearColor(0.7, 0.74, 0.8, 1.0))
    em = custom(m, -700, 100, "return float3(0.55, 0.6, 0.7) * Mask * G;", ["Mask", "G"],
                "CMOT_FLOAT3", "CgRainGlow")
    link(mask, "", em, "Mask")
    link(expr(m, unreal.MaterialExpressionScalarParameter, -1000, 150,
              parameter_name="RainGlow", default_value=0.006), "", em, "G")
    rough = expr(m, unreal.MaterialExpressionConstant, -700, 200, r=0.1)
    tm = expr(m, unreal.MaterialExpressionTime, -1300, 1300)
    fall = expr(m, unreal.MaterialExpressionScalarParameter, -1300, 1400, parameter_name="Fall",
                default_value=2400.0)
    speed = expr(m, unreal.MaterialExpressionScalarParameter, -1300, 1500,
                 parameter_name="Speed", default_value=900.0)
    lp = expr(m, unreal.MaterialExpressionPreSkinnedPosition, -1300, 1600)
    wpo = custom(m, -700, 1300, RAIN_WPO,
                 ["Time", "Rnd", "Fall", "Speed", "Wind", "WindX", "WindY", "Streak", "LP"],
                 "CMOT_FLOAT3", "CgRainFall")
    for a, n in ((tm, "Time"), (rnd, "Rnd"), (fall, "Fall"), (speed, "Speed"),
                 (mpc_param(m, c, "WindMS", -1300, 1700), "Wind"),
                 (mpc_param(m, c, "WindX", -1300, 1800), "WindX"),
                 (mpc_param(m, c, "WindY", -1300, 1900), "WindY"), (streak, "Streak"),
                 (lp, "LP")):
        link(a, "", wpo, n)
    MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(op, "", MP.MP_OPACITY)
    MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(wpo, "", MP.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


# AT5: the wet streets, two deferred decals round the view reading the plan's masks (the
# city-wide cover and surface textures): `WET` gives, for the pixel under the decal, how wet
# it is (the controller's Wetness where the rain reaches it: under its texel's cover dry, on
# a wall a share, the drip band under a cover's edge wetter), its puddle (the texel's depth
# against the puddles' fill now, broken up by a fine noise at its edge), its gloss when wet
# and how much it faces up. The face's normal comes from the depth (the derivatives of the
# pixel's camera-relative position), turned to the eye. Past the textures, `Far` gloss and no
# shelter or puddle.
WET = """
float2 uv = (WP.xy - B.xy) / max(B.z, 1.0);
float c = 0.0;
float3 s = float3(Far, 0.0, 0.0);
if (all(uv > 0.0) && all(uv < 1.0)) {
  c = Texture2DSampleLevel(Cov, CovSampler, uv, 0).r * 255.0;
  s = Texture2DSample(Srf, SrfSampler, uv).rgb;
}
float cz = Z.x + floor(c + 0.5) * Z.y;
float dry = (c > 0.5) ? saturate((cz - 20.0 - WP.z) / 40.0) : 0.0;
float3 n = normalize(cross(ddx_fine(RP), ddy_fine(RP)));
if (dot(n, CV) < 0.0) { n = -n; }
float up = saturate((n.z - 0.62) / 0.3);
float down = saturate((-n.z - 0.3) / 0.3);
float wall = (1.0 - up) * (1.0 - down);
float2 p = WP.xy / 45.0;
float2 i = floor(p);
float2 f = frac(p);
f = f * f * (3.0 - 2.0 * f);
float h00 = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
float h10 = frac(sin(dot(i + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
float h01 = frac(sin(dot(i + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
float h11 = frac(sin(dot(i + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
float fine = lerp(lerp(h00, h10, f.x), lerp(h01, h11, f.x), f.y);
float open_ = (1.0 - dry) * step(0.01, s.r);   // (the water: gloss 0, its own master)
float wet = saturate(Wet * open_ * (up + wall * WallShare) + s.b * up * open_ * saturate(Wet * 2.0) * 0.4);
float depth = s.g + (fine - 0.5) * 0.18;
float pud = up * open_ * step(0.004, s.g) * saturate((depth - (1.0 - Pud)) * 9.0);
return float4(wet, pud, s.r, up);
"""


def wet_inputs(m, c, x, y):
    """AT5: the wet decals' common inputs and their WET node."""
    black = unreal.load_asset("/Engine/EngineResources/Black.Black")
    cov, b, z = cover_inputs(m, x, y)
    srf = expr(m, unreal.MaterialExpressionTextureObjectParameter, x, y + 360,
               parameter_name="WetSurface", texture=black)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, x, y + 480)
    rp = expr(m, unreal.MaterialExpressionWorldPosition, x, y + 580,
              world_position_shader_offset=unreal.WorldPositionIncludedOffsets
              .WPT_CAMERA_RELATIVE)
    cv = expr(m, unreal.MaterialExpressionCameraVectorWS, x, y + 680)
    far = expr(m, unreal.MaterialExpressionScalarParameter, x, y + 780, parameter_name="FarGloss",
               default_value=0.7)
    ws = expr(m, unreal.MaterialExpressionScalarParameter, x, y + 860,
              parameter_name="WallShare", default_value=0.35)
    w = custom(m, x + 400, y + 300, WET,
               ["WP", "RP", "CV", "Cov", "Srf", "B", "Z", "Far", "Wet", "Pud", "WallShare"],
               "CMOT_FLOAT4", "CgWet")
    for a, n in ((wp, "WP"), (rp, "RP"), (cv, "CV"), (cov, "Cov"), (srf, "Srf"), (b, "B"),
                 (z, "Z"), (far, "Far"), (mpc_param(m, c, "Wetness", x, y + 940), "Wet"),
                 (mpc_param(m, c, "Puddles", x, y + 1020), "Pud"), (ws, "WallShare")):
        link(a, "", w, n)
    return w, wp


def decal_material(name):
    m, made = material(name)
    if made:
        m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    return m, made


def wet_color(c):
    """AT5: `M_CgWetColor`: the wet surfaces darker (the DBuffer's color, black at an opacity:
    the surface's own color times one less it, so markings stay, darker)."""
    m, made = decal_material("M_CgWetColor")
    if not made:
        return m, False
    w, _ = wet_inputs(m, c, -1600, 0)
    dark = expr(m, unreal.MaterialExpressionScalarParameter, -1000, 1200,
                parameter_name="Darken", default_value=0.55)
    op = custom(m, -600, 300, "return saturate(sqrt(W.x) * (0.25 + D * W.z) + W.y * 0.42);",
                ["W", "D"], "CMOT_FLOAT1", "CgWetDarken")
    link(w, "", op, "W")
    link(dark, "", op, "D")
    black = expr(m, unreal.MaterialExpressionConstant3Vector, -600, 0,
                 constant=unreal.LinearColor(0.0, 0.0, 0.0, 1.0))
    MEL.connect_material_property(black, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(op, "", MP.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


# AT5: the gloss decal's normal (world space): a puddle flat, rippled by the rain's drops
# (rings spreading from hashed points in two layers of 28 cm cells), a wet floor a little
# uneven (the fine noise's slope) with fainter rings, a wall its own face; near the eye only
# (`RingM`), past it flat
GLOSS_N = """
float3 n = normalize(cross(ddx_fine(RP), ddy_fine(RP)));
if (dot(n, CV) < 0.0) { n = -n; }
float2 g = float2(0.0, 0.0);
float dist = length(RP);
float near_ = saturate(1.0 - dist / (RingM * 100.0));
if (near_ > 0.0 && Rain > 0.01) {
  for (int L = 0; L < 2; L++) {
    float2 q = WP.xy / 28.0 + float2(L * 17.31, L * 9.13);
    float2 id = floor(q);
    float2 f = frac(q) - 0.5;
    float h = frac(sin(dot(id, float2(127.1, 311.7))) * 43758.5453);
    float h2 = frac(sin(dot(id, float2(269.5, 183.3))) * 43758.5453);
    f -= (float2(h, h2) - 0.5) * 0.5;
    float life = frac(Time * (0.9 + 0.5 * h2) + h);
    float r = length(f);
    float x = (r - life * 0.42) * 26.0;
    float ring = (abs(x) < 3.1416) ? sin(x) * (1.0 - life) : 0.0;
    g += (f / max(r, 1e-3)) * ring * step(h2, 0.35 + 0.6 * Rain);
  }
}
float amp = near_ * Rain * lerp(0.08, 0.55, W.y);
float3 fl = normalize(float3(-g * amp, 1.0));
return (W.w > 0.5) ? fl : n;
"""


def wet_gloss(c):
    """AT5: `M_CgWetGloss`: the wet surfaces glossy (the DBuffer's roughness and normal, at an
    opacity by how wet they are and their gloss when wet; a puddle a mirror with the rain's
    rings on it)."""
    m, made = decal_material("M_CgWetGloss")
    if not made:
        return m, False
    m.set_editor_property("tangent_space_normal", False)
    w, wp = wet_inputs(m, c, -1600, 0)
    rp = expr(m, unreal.MaterialExpressionWorldPosition, -1000, 1300,
              world_position_shader_offset=unreal.WorldPositionIncludedOffsets
              .WPT_CAMERA_RELATIVE)
    cv = expr(m, unreal.MaterialExpressionCameraVectorWS, -1000, 1400)
    tm = expr(m, unreal.MaterialExpressionTime, -1000, 1500)
    ring = expr(m, unreal.MaterialExpressionScalarParameter, -1000, 1600,
                parameter_name="RingM", default_value=30.0)
    nn = custom(m, -600, 900, GLOSS_N, ["W", "WP", "RP", "CV", "Time", "Rain", "RingM"],
                "CMOT_FLOAT3", "CgWetNormal")
    for a, n in ((w, "W"), (wp, "WP"), (rp, "RP"), (cv, "CV"), (tm, "Time"),
                 (mpc_param(m, c, "Rain", -1000, 1700), "Rain"), (ring, "RingM")):
        link(a, "", nn, n)
    rough = custom(m, -600, 300, "return lerp(0.16, 0.03, W.y);", ["W"], "CMOT_FLOAT1",
                   "CgWetRough")
    link(w, "", rough, "W")
    op = custom(m, -600, 500, "return saturate(sqrt(W.x) * W.z * 0.85 + W.y);", ["W"], "CMOT_FLOAT1",
                "CgWetGlossOpacity")
    link(w, "", op, "W")
    MEL.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(nn, "", MP.MP_NORMAL)
    MEL.connect_material_property(op, "", MP.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


# AT5: a splash, a card the controller sets where a trace down from the sky lands near the
# view (the rain's own landing spots, roofs and awnings too): turned to the eye, a crown of
# droplets thrown up and falling back over a short life, then nothing until its next drop
# (per-instance data: phase, size in cm)
SPLASH_WPO = """
float3 dir = normalize(C - Cam);
float3 right = normalize(cross(float3(0.0, 0.0, 1.0), dir) + float3(1e-4, 0.0, 0.0));
float2 q = LP.xy / 50.0;
float t = frac(Time * 2.3 + Phase);
float live = step(t, 0.28) * step(Rnd, Rain * Drops);
float s = Size * (0.4 + 2.2 * t) * live;
return C + right * q.x * s + float3(0.0, 0.0, (q.y * 0.5 + 0.5) * s * 0.75) - WP;
"""
SPLASH_OP = """
float t = frac(Time * 2.3 + Phase) / 0.28;
float2 p = UV * 2.0 - 1.0;
p.y = -p.y;
float arc = saturate(1.0 - abs(length(float2(p.x, (p.y + 1.0) * 1.3)) - 0.75) * 5.0);
float rim = saturate(1.0 - abs(p.y + 0.85) * 6.0) * saturate(1.0 - abs(p.x) * 1.1);
float drops = saturate(1.0 - length(frac(p * 2.6 + Phase * 7.0) - 0.5) * 3.0) * step(0.0, p.y) * 0.7;
float a = max(max(arc, rim), drops) * saturate(1.0 - t) * saturate(t * 8.0);
float near_ = saturate((Depth - 40.0) / 100.0);
return saturate(a * Gain * near_);
"""


def splash(c):
    m, made = material("M_CgSplash")
    if not made:
        return m, False
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("translucency_lighting_mode",
                          unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    names, ins = [], []
    for k, n in enumerate(("CX", "CY", "CZ", "Phase", "Size")):
        ins.append(expr(m, unreal.MaterialExpressionPerInstanceCustomData, -1300, 90 * k,
                        data_index=k, const_default_value=(0, 0, 0, 0, 12)[k]))
        names.append(n)
    cpos = custom(m, -1000, 0, "return float3(X, Y, Z);", ["X", "Y", "Z"], "CMOT_FLOAT3",
                  "CgSplashAt")
    for k, n in enumerate(("X", "Y", "Z")):
        link(ins[k], "", cpos, n)
    tm = expr(m, unreal.MaterialExpressionTime, -1300, 600)
    lp = expr(m, unreal.MaterialExpressionPreSkinnedPosition, -1300, 700)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1300, 800)
    cam = expr(m, unreal.MaterialExpressionCameraPositionWS, -1300, 900)
    rnd = expr(m, unreal.MaterialExpressionPerInstanceRandom, -1300, 1000)
    wpo = custom(m, -700, 600, SPLASH_WPO,
                 ["C", "Phase", "Size", "Time", "LP", "WP", "Cam", "Rnd", "Rain", "Drops"],
                 "CMOT_FLOAT3", "CgSplashWPO")
    for a, n in ((cpos, "C"), (ins[3], "Phase"), (ins[4], "Size"), (tm, "Time"), (lp, "LP"),
                 (wp, "WP"), (cam, "Cam"), (rnd, "Rnd"),
                 (mpc_param(m, c, "Rain", -1300, 1100), "Rain"),
                 (mpc_param(m, c, "Drops", -1300, 1200), "Drops")):
        link(a, "", wpo, n)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1300, 1300, coordinate_index=0)
    depth = expr(m, unreal.MaterialExpressionPixelDepth, -1300, 1400)
    gain = expr(m, unreal.MaterialExpressionScalarParameter, -1300, 1500,
                parameter_name="SplashOpacity", default_value=0.6)
    op = custom(m, -700, 1200, SPLASH_OP, ["UV", "Phase", "Time", "Depth", "Gain"],
                "CMOT_FLOAT1", "CgSplashOpacity")
    for a, n in ((uv, "UV"), (ins[3], "Phase"), (tm, "Time"), (depth, "Depth"), (gain, "Gain")):
        link(a, "", op, n)
    col = expr(m, unreal.MaterialExpressionConstant3Vector, -700, 0,
               constant=unreal.LinearColor(0.75, 0.8, 0.86, 1.0))
    em = custom(m, -700, 200, "return float3(0.5, 0.55, 0.6) * G;", ["G"], "CMOT_FLOAT3",
                "CgSplashGlow")
    link(expr(m, unreal.MaterialExpressionScalarParameter, -1000, 300,
              parameter_name="SplashGlow", default_value=0.004), "", em, "G")
    MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(op, "", MP.MP_OPACITY)
    MEL.connect_material_property(expr(m, unreal.MaterialExpressionConstant, -700, 400, r=0.1),
                                  "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(wpo, "", MP.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


# AT5: a drip, a card the controller sets along a low cover's dripping edge near the view
# (per-instance data: its top x, y, z, the fall to the ground in cm, its phase, its rate):
# turned to the eye about the vertical, a streak falling from the edge to the ground (faster
# as it falls), drifting downwind, again each period; dripping while the rain falls and a
# while after (the surfaces' wetness)
DRIP_WPO = """
float period = 0.55 + 0.9 / max(Rate, 0.2);
float t = frac(Time / period + Phase);
float fallT = sqrt(2.0 * max(Fall, 1.0) / 980.0);
float tf = t * period;
float on = step(tf, fallT);
float d = 0.5 * 980.0 * tf * tf;
float3 top = float3(X, Y, Z);
float3 c = top + float3(float2(WindX, WindY) * Wind * 18.0 * tf, -min(d, Fall));
float3 dir = normalize(c - Cam);
float3 right = normalize(cross(float3(0.0, 0.0, 1.0), dir) + float3(1e-4, 0.0, 0.0));
float2 q = LP.xy / 50.0;
float len_ = clamp(980.0 * tf * 0.035, 3.0, 24.0) * on;
return c + right * q.x * 0.9 * on + float3(0.0, 0.0, q.y * len_) - WP;
"""
DRIP_OP = """
float across = saturate(1.0 - abs(UV.x * 2.0 - 1.0));
float along = saturate((1.0 - abs(UV.y * 2.0 - 1.0)) * 2.0);
float on = saturate(max(Rain * 1.5, Wet - 0.25));
float near_ = saturate((Depth - 30.0) / 80.0);
return saturate(across * along * on * Gain * near_);
"""


def drip(c):
    m, made = material("M_CgDrip")
    if not made:
        return m, False
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("translucency_lighting_mode",
                          unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    names, ins = [], []
    for k, n in enumerate(("X", "Y", "Z", "Fall", "Phase", "Rate")):
        ins.append(expr(m, unreal.MaterialExpressionPerInstanceCustomData, -1300, 90 * k,
                        data_index=k, const_default_value=(0, 0, 0, 300, 0, 1)[k]))
        names.append(n)
    tm = expr(m, unreal.MaterialExpressionTime, -1300, 600)
    lp = expr(m, unreal.MaterialExpressionPreSkinnedPosition, -1300, 700)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1300, 800)
    cam = expr(m, unreal.MaterialExpressionCameraPositionWS, -1300, 900)
    wpo = custom(m, -700, 600, DRIP_WPO,
                 names + ["Time", "LP", "WP", "Cam", "Wind", "WindX", "WindY"],
                 "CMOT_FLOAT3", "CgDripWPO")
    for a, n in list(zip(ins, names)) + [
            (tm, "Time"), (lp, "LP"), (wp, "WP"), (cam, "Cam"),
            (mpc_param(m, c, "WindMS", -1300, 1000), "Wind"),
            (mpc_param(m, c, "WindX", -1300, 1100), "WindX"),
            (mpc_param(m, c, "WindY", -1300, 1200), "WindY")]:
        link(a, "", wpo, n)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1300, 1300, coordinate_index=0)
    depth = expr(m, unreal.MaterialExpressionPixelDepth, -1300, 1400)
    gain = expr(m, unreal.MaterialExpressionScalarParameter, -1300, 1500,
                parameter_name="DripOpacity", default_value=0.7)
    op = custom(m, -700, 1200, DRIP_OP, ["UV", "Rain", "Wet", "Depth", "Gain"], "CMOT_FLOAT1",
                "CgDripOpacity")
    for a, n in ((uv, "UV"), (mpc_param(m, c, "Rain", -1300, 1600), "Rain"),
                 (mpc_param(m, c, "Wetness", -1300, 1700), "Wet"), (depth, "Depth"),
                 (gain, "Gain")):
        link(a, "", op, n)
    col = expr(m, unreal.MaterialExpressionConstant3Vector, -700, 0,
               constant=unreal.LinearColor(0.75, 0.8, 0.86, 1.0))
    em = custom(m, -700, 200, "return float3(0.5, 0.55, 0.6) * G;", ["G"], "CMOT_FLOAT3",
                "CgDripGlow")
    link(expr(m, unreal.MaterialExpressionScalarParameter, -1000, 300,
              parameter_name="DripGlow", default_value=0.005), "", em, "G")
    MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(op, "", MP.MP_OPACITY)
    MEL.connect_material_property(expr(m, unreal.MaterialExpressionConstant, -700, 400, r=0.1),
                                  "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(wpo, "", MP.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


def drop_old():
    """AT5: AT0's wet decal (M_CgWet) is gone: M_CgWetColor and M_CgWetGloss took its place."""
    path = f"{FOLDER}/M_CgWet"
    if EAL.does_asset_exist(path):
        return bool(EAL.delete_asset(path))
    return False

# AT2: an aviation light's red glow blinks as its light does (CityGenAtmos's AnimGain: on for
# the first `Duty` of each `Period`, from `Phase`), from the per-instance data the controller
# sets (phase, period, on share, glow)
BEACON = """
float on = frac(Time / max(Period, 0.01) + Phase) < Duty ? 1.0 : 0.012;
return float3(1.0, 0.07, 0.02) * Glow * on;
"""
# a searchlight's beam: a cone from the light (its apex, the mesh's +Z) along its aim, lit in
# the haze: brightest near the light and fading along it, soft at its silhouette, faded near
# the eye and where it meets a surface (depth fade)
BEAM = """
float3 up = normalize(Up);
float z = dot(WP - OP, up);
float t = saturate((H - z) / max(2.0 * H, 1.0));
float along = (1.0 - t) * (1.0 - t) * saturate(t * 60.0);
float edge = saturate(abs(dot(normalize(CV), normalize(N))));
float near_ = saturate((Depth - 300.0) / 3000.0);
return float3(R, G, B) * Glow * along * edge * edge * near_ * Fade;
"""


def beacon():
    m, made = material("M_CgBeacon")
    if not made:
        return m, False
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    tm = expr(m, unreal.MaterialExpressionTime, -900, 0)
    ins = [tm]
    names = ["Time"]
    for k, n in enumerate(("Phase", "Period", "Duty", "Glow")):
        ins.append(expr(m, unreal.MaterialExpressionPerInstanceCustomData, -900, 120 + 110 * k,
                        data_index=k, const_default_value=(0.0, 2.0, 0.3, 20.0)[k]))
        names.append(n)
    em = custom(m, -500, 100, BEACON, names, "CMOT_FLOAT3", "CgBeacon")
    for a, n in zip(ins, names):
        link(a, "", em, n)
    MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


def beam():
    m, made = material("M_CgBeam")
    if not made:
        return m, False
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    names, ins = [], []
    for k, n in enumerate(("R", "G", "B", "Glow", "H")):
        ins.append(expr(m, unreal.MaterialExpressionScalarParameter, -1000, 110 * k,
                        parameter_name=f"Beam{n}", use_custom_primitive_data=True,
                        primitive_data_index=k,
                        default_value=(1.0, 1.0, 1.0, 0.08, 20000.0)[k]))
        names.append(n)
    for cls, n in ((unreal.MaterialExpressionWorldPosition, "WP"),
                   (unreal.MaterialExpressionObjectPositionWS, "OP"),
                   (unreal.MaterialExpressionObjectOrientation, "Up"),
                   (unreal.MaterialExpressionCameraVectorWS, "CV"),
                   (unreal.MaterialExpressionVertexNormalWS, "N"),
                   (unreal.MaterialExpressionPixelDepth, "Depth")):
        ins.append(expr(m, cls, -1000, 600 + 100 * len(names)))
        names.append(n)
    fade = expr(m, unreal.MaterialExpressionDepthFade, -1000, 1400, fade_distance_default=400.0)
    one = expr(m, unreal.MaterialExpressionConstant, -1200, 1400, r=1.0)
    link(one, "", fade, "Opacity")
    ins.append(fade)
    names.append("Fade")
    em = custom(m, -500, 300, BEAM, names, "CMOT_FLOAT3", "CgBeam")
    for a, n in zip(ins, names):
        link(a, "", em, n)
    MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


# AT3: the sky dome's material. The engine's sky atmosphere in the view direction (its sky,
# and the sun's disk while the light is the sun), the stars (a hashed lattice on the view
# direction, a point per lit cell, twinkling), the moon (a disk at MoonDir lit from SunDir:
# its phase, a little mottling for its maria, a halo), and the cloud deck: a plane DeckCm up,
# met along the view ray (so it has parallax as the camera moves), its cover a value-noise
# fbm drifting with the wind, lit by the atmosphere's light at the deck (the sun by day, the
# moon by night), the sky under it, and from below by the city's glow (the plan's raster in
# world X and Y, squared, times GlowMax and GlowScale), fading into the sky's haze with
# distance. Luminance in the scene's frame; the controller sets the parameters each hour.
SKY = """
float3 d = normalize(-CV);
float3 col = SkyLum + SunDisk * SunDiskOn;
float above = saturate(d.z * 12.0 + 0.05);
// the cloud deck (worked out first: the stars only where it leaves the sky open)
float dens = 0.0;
float3 cl = 0.0;
if (DeckCm > 0.0 && d.z > 0.003 && CamPos.z < DeckCm) {
  float t = (DeckCm - CamPos.z) / d.z;
  float2 p = (CamPos.xy + d.xy * t) * 0.01;
  float2 w = p + float2(1.0, 0.35) * Time * Wind;
  float nsum = 0.0;
  float amp = 0.55;
  float2 sc = w / 1600.0;
  for (int k = 0; k < 4; k++) {
    float2 i0 = floor(sc);
    float2 f0 = frac(sc);
    f0 = f0 * f0 * (3.0 - 2.0 * f0);
    float a0 = frac(sin(dot(i0, float2(127.1, 311.7))) * 43758.5453);
    float b0 = frac(sin(dot(i0 + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
    float c0 = frac(sin(dot(i0 + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
    float e0 = frac(sin(dot(i0 + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
    nsum += amp * lerp(lerp(a0, b0, f0.x), lerp(c0, e0, f0.x), f0.y);
    amp *= 0.5;
    sc = sc * 2.03 + float2(17.3, 5.1);
  }
  nsum /= 0.92;
  float cov = smoothstep(1.0 - Cover - 0.2, 1.0 - Cover + 0.2, nsum);
  // (the deck's own texture: thicker and thinner, so a closed deck is not one flat sheet)
  float tex = saturate(0.35 + 1.3 * (nsum - 0.5) + 0.4 * cov);
  dens = cov * saturate(1.0 - t / 4.0e6);
  float2 uv = (CamPos.xy + d.xy * t - GlowLo.xy) / max(GlowHi.xy - GlowLo.xy, 1.0);
  float3 gl = Texture2DSampleLevel(Glow, GlowSampler, saturate(uv), 0).rgb;
  float inside = step(0.0, uv.x) * step(uv.x, 1.0) * step(0.0, uv.y) * step(uv.y, 1.0);
  gl = gl * gl * GlowMax * GlowScale * inside;
  float thin = 1.0 - cov;
  cl = (LightIllum * CloudLit * (0.5 + 0.9 * thin) + SkyLum * 0.45) * (0.55 + 0.7 * tex)
    + gl * (0.25 + 0.75 * tex);
  float haze = 1.0 - exp(-t / 1.4e6);
  cl = lerp(cl, SkyLum + gl * 0.3, haze * 0.85);
}
// stars (none where the deck is closed or none show)
if (Stars > 0.0 && dens < 0.98) {
float3 sd = d * 620.0;
float3 cell = floor(sd);
float hs = frac(sin(dot(cell, float3(12.9898, 78.233, 37.719))) * 43758.5453);
float3 off = frac(sin(cell * float3(127.1, 311.7, 74.7) + hs) * 43758.5453);
float dist = length(sd - (cell + 0.25 + 0.5 * off));
float star = hs > 1.0 - 0.012 * Stars ? saturate(1.0 - dist * 3.0) : 0.0;
float tw = 0.7 + 0.3 * sin(Time * (1.5 + 5.0 * hs) + hs * 91.0);
col += star * star * tw * StarLum * (0.3 + 2.5 * pow(frac(hs * 977.0), 4.0)) * above;
}
// the moon
float3 m = normalize(MoonDir);
float md = dot(d, m);
float rad = MoonRad;
if (MoonVis > 0.0 && md > 0.85) {           // (its disk and halo: within 32 degrees of it)
  float3 u = normalize(cross(m, float3(0.0, 0.0, 1.0)) + float3(1e-5, 0.0, 0.0));
  float3 v = cross(u, m);
  float2 q = float2(dot(d, u), dot(d, v)) / sin(rad);
  float rr = dot(q, q);
  float disk = saturate((1.0 - sqrt(rr)) * 30.0) * step(0.0, md);
  float3 n = q.x * u + q.y * v - sqrt(saturate(1.0 - rr)) * m;
  float lit = saturate(dot(n, normalize(SunDir)) * 8.0 + 0.015);
  float2 g = q * 2.3 + 7.0;
  float2 gi = floor(g);
  float2 gf = frac(g);
  gf = gf * gf * (3.0 - 2.0 * gf);
  float a = frac(sin(dot(gi, float2(127.1, 311.7))) * 43758.5453);
  float b = frac(sin(dot(gi + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
  float c = frac(sin(dot(gi + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
  float e = frac(sin(dot(gi + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
  float mar = 0.72 + 0.28 * lerp(lerp(a, b, gf.x), lerp(c, e, gf.x), gf.y);
  float limb = 0.75 + 0.25 * sqrt(saturate(1.0 - rr));
  col += MoonTint * MoonLum * disk * lit * mar * limb * MoonVis * above;
  float ang = acos(clamp(md, -1.0, 1.0));
  col += MoonTint * MoonLum * MoonVis * above * 0.004 * exp(-ang * 14.0);
}
col = lerp(col, cl, dens);
return col;
"""

SKY_SCALARS = (("DeckCm", 42000.0), ("Cover", 0.8), ("Stars", 0.0), ("StarLum", 0.6),
               ("MoonLum", 0.5), ("MoonRad", 0.0046), ("MoonVis", 0.0), ("SunDiskOn", 1.0),
               ("GlowMax", 1.0), ("GlowScale", 0.0), ("CloudLit", 0.03), ("Wind", 2.0))
SKY_VECTORS = (("SunDir", (0.0, 0.0, 1.0, 0.0)), ("MoonDir", (0.0, 0.5, 0.5, 0.0)),
               ("MoonTint", (0.8, 0.86, 1.0, 1.0)),
               # (a vector parameter reaches a custom node as its RGB: the glow's corners as
               # two, each its X and Y)
               ("GlowLo", (-1.0e6, -1.0e6, 0.0, 0.0)), ("GlowHi", (1.0e6, 1.0e6, 0.0, 0.0)))


def sky_material():
    m, made = material("M_CgSky")
    if not made:
        return m, False
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("is_sky", True)
    m.set_editor_property("two_sided", True)
    names, ins = [], []
    for cls, n in ((unreal.MaterialExpressionCameraVectorWS, "CV"),
                   (unreal.MaterialExpressionCameraPositionWS, "CamPos"),
                   (unreal.MaterialExpressionSkyAtmosphereViewLuminance, "SkyLum"),
                   (unreal.MaterialExpressionTime, "Time")):
        ins.append(expr(m, cls, -1400, 100 * len(names)))
        names.append(n)
    disk = expr(m, unreal.MaterialExpressionSkyAtmosphereLightDiskLuminance, -1400, 500)
    ins.append(disk)
    names.append("SunDisk")
    for k, (n, v) in enumerate(SKY_SCALARS):
        ins.append(expr(m, unreal.MaterialExpressionScalarParameter, -1400, 700 + 80 * k,
                        parameter_name=n, default_value=v))
        names.append(n)
    for k, (n, v) in enumerate(SKY_VECTORS):
        ins.append(expr(m, unreal.MaterialExpressionVectorParameter, -1400, 1800 + 120 * k,
                        parameter_name=n, default_value=unreal.LinearColor(*v)))
        names.append(n)
    # the atmosphere's light (the sun, else the moon) at the deck over the camera
    deckpos = custom(m, -1700, 2400, "return CamPos + float3(0.0, 0.0, max(DeckCm, 100.0));",
                     ["CamPos", "DeckCm"], "CMOT_FLOAT3", "CgDeckPos")
    link(ins[names.index("CamPos")], "", deckpos, "CamPos")
    link(ins[names.index("DeckCm")], "", deckpos, "DeckCm")
    illum = expr(m, unreal.MaterialExpressionSkyAtmosphereLightIlluminance, -1400, 2500)
    link(deckpos, "", illum, "WorldPosition")
    ins.append(illum)
    names.append("LightIllum")
    black = unreal.load_asset("/Engine/EngineResources/Black.Black")
    glow = expr(m, unreal.MaterialExpressionTextureObjectParameter, -1400, 2650,
                parameter_name="Glow", texture=black)
    ins.append(glow)
    names.append("Glow")
    sk = custom(m, -600, 600, SKY, names, "CMOT_FLOAT3", "CgSky")
    for a, n in zip(ins, names):
        link(a, "", sk, n)
    MEL.connect_material_property(sk, "", MP.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


# AT4: a plume's puff (steam, exhaust, cooking, smoke): a card of the cell's instanced plume,
# turned to face the eye about its own middle and rising from the plume's foot by world
# position offset; its life a phase of the plume's period (rising fast, slowing, widening,
# drifting with the wind); from its per-instance data: the foot (cm), phase, period (s),
# rise and width (cm), opacity, albedo
STEAM_WPO = """
float t = frac(Time / max(Period, 0.1) + Phase);
float up = 1.0 - (1.0 - t) * (1.0 - t);
float3 c = Foot + float3(0.0, 0.0, Rise * up);
c.xy += float2(WindX, WindY) * Wind * 100.0 * t * Period * 0.25;
float half_ = Width * (0.45 + 1.1 * t) + Rise * 0.05 * t;
float3 dir = normalize(c - Cam);
float3 right = normalize(cross(float3(0.0, 0.0, 1.0), dir) + float3(1e-4, 0.0, 0.0));
float3 upv = cross(dir, right);
float2 q = LP.xy / 50.0;
return c + (q.x * right + q.y * upv) * half_ - WP;
"""
# its opacity: a soft round puff broken up by a value noise moved by its phase, faded in and
# out over its life and near the eye
STEAM_OP = """
float t = frac(Time / max(Period, 0.1) + Phase);
float2 p = UV * 2.0 - 1.0;
float r = length(p);
float2 g = UV * 3.0 + Phase * 17.0 + float2(0.0, -t * 1.5);
float2 i = floor(g);
float2 f = frac(g);
f = f * f * (3.0 - 2.0 * f);
float a = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
float b = frac(sin(dot(i + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
float c = frac(sin(dot(i + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
float d = frac(sin(dot(i + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
float n = lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
float2 g2 = g * 2.7 + 5.3;
float2 i2 = floor(g2);
float2 f2 = frac(g2);
f2 = f2 * f2 * (3.0 - 2.0 * f2);
float a2 = frac(sin(dot(i2, float2(127.1, 311.7))) * 43758.5453);
float b2 = frac(sin(dot(i2 + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
float c2 = frac(sin(dot(i2 + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
float d2 = frac(sin(dot(i2 + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
n = 0.65 * n + 0.35 * lerp(lerp(a2, b2, f2.x), lerp(c2, d2, f2.x), f2.y);
float soft = pow(saturate(1.0 - r), 1.4) * saturate(n * 1.6 - 0.3);
float life = sin(3.14159 * t) * saturate(t * 6.0);
float near_ = saturate((Depth - 80.0) / 300.0);
float far_ = 1.0 + Far * saturate((Depth - 3000.0) / max(100.0, FarM * 100.0 - 3000.0));
return saturate(soft * life * Rate * Gain * near_ * Fade * far_);
"""


def steam(c):
    m, made = material("M_CgSteam")
    if not made:
        return m, False
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("translucency_lighting_mode",
                          unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    names, ins = [], []
    for k, n in enumerate(("FootX", "FootY", "FootZ", "Phase", "Period", "Rise", "Width",
                           "Rate", "AlbR", "AlbG", "AlbB")):
        ins.append(expr(m, unreal.MaterialExpressionPerInstanceCustomData, -1300, 90 * k,
                        data_index=k,
                        const_default_value=(0, 0, 0, 0, 4, 450, 80, 0.8, 0.8, 0.8, 0.8)[k]))
        names.append(n)
    foot = custom(m, -1000, 0, "return float3(X, Y, Z);", ["X", "Y", "Z"], "CMOT_FLOAT3",
                  "CgFoot")
    for k, n in enumerate(("X", "Y", "Z")):
        link(ins[k], "", foot, n)
    alb = custom(m, -1000, 800, "return float3(R, G, B);", ["R", "G", "B"], "CMOT_FLOAT3",
                 "CgAlbedo")
    for k, n in enumerate(("R", "G", "B")):
        link(ins[8 + k], "", alb, n)
    tm = expr(m, unreal.MaterialExpressionTime, -1300, 1100)
    lp = expr(m, unreal.MaterialExpressionPreSkinnedPosition, -1300, 1200)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1300, 1300)
    cam = expr(m, unreal.MaterialExpressionCameraPositionWS, -1300, 1400)
    wind = mpc_param(m, c, "WindMS", -1300, 1500)
    wpo = custom(m, -700, 900, STEAM_WPO,
                 ["Foot", "Phase", "Period", "Rise", "Width", "Time", "LP", "WP", "Cam", "Wind",
                  "WindX", "WindY"],
                 "CMOT_FLOAT3", "CgSteamRise")
    for a, n in ((foot, "Foot"), (ins[3], "Phase"), (ins[4], "Period"), (ins[5], "Rise"),
                 (ins[6], "Width"), (tm, "Time"), (lp, "LP"), (wp, "WP"), (cam, "Cam"),
                 (wind, "Wind"), (mpc_param(m, c, "WindX", -1300, 1600), "WindX"),
                 (mpc_param(m, c, "WindY", -1300, 1650), "WindY")):
        link(a, "", wpo, n)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1300, 1700, coordinate_index=0)
    depth = expr(m, unreal.MaterialExpressionPixelDepth, -1300, 1800)
    fade = expr(m, unreal.MaterialExpressionDepthFade, -1300, 1900, fade_distance_default=120.0)
    one = expr(m, unreal.MaterialExpressionConstant, -1500, 1900, r=1.0)
    link(one, "", fade, "Opacity")
    gain = mpc_param(m, c, "SteamGain", -1300, 2000)
    op = custom(m, -700, 1500, STEAM_OP,
                ["UV", "Phase", "Period", "Rate", "Time", "Depth", "Fade", "Gain", "Far",
                 "FarM"],
                "CMOT_FLOAT1", "CgSteamOpacity")
    for a, n in ((uv, "UV"), (ins[3], "Phase"), (ins[4], "Period"), (ins[7], "Rate"),
                 (tm, "Time"), (depth, "Depth"), (fade, "Fade"), (gain, "Gain"),
                 (mpc_param(m, c, "SteamFar", -1300, 2100), "Far"),
                 (mpc_param(m, c, "SteamFarM", -1300, 2200), "FarM")):
        link(a, "", op, n)
    rough = expr(m, unreal.MaterialExpressionConstant, -700, 1900, r=1.0)
    # (AT6: lit by the city round it by night: its albedo times SteamGlow, which the controller
    # sets to the plan's glow times Night)
    glow = custom(m, -700, 2100, "return Alb * Glow;", ["Alb", "Glow"], "CMOT_FLOAT3",
                  "CgSteamGlow")
    link(alb, "", glow, "Alb")
    link(mpc_param(m, c, "SteamGlow", -1300, 2300), "", glow, "Glow")
    MEL.connect_material_property(glow, "", MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(alb, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(op, "", MP.MP_OPACITY)
    MEL.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(wpo, "", MP.MP_WORLD_POSITION_OFFSET)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


# AT7: the far city's cards (the plan's `far`, the controller instancing them on the engine's
# plane per 1 km block). Each fades in past its tier's live range (FarMidM, FarHighM, FarFixM:
# the farthest FarFade of it, as the live lights fade out there); faded out, or off by its
# schedule or by day (FarScale 0), its quad collapses to a point by world position offset, so
# it costs no pixel. A glow: turned to the eye, at least FarPx of the distance wide (a few
# pixels), pulled toward the eye by half its size (clear of its own fixture and wall), a
# gaussian whose intensity holds as it grows: its peak luminance its intensity over FarSpread
# times its size squared; blinking from its per-instance data as its light does.
FAR_WHERE = """
float S = Tier < 0.5 ? Mid : (Tier < 1.5 ? High : Fix);
float d = length(C - Cam) * 0.01;
return saturate((d - S * (1.0 - Fade)) / max(S * Fade, 1.0));
"""
FAR_GLOW_WPO = """
float3 toC = C - Cam;
float d = max(length(toC), 1.0);
float3 dir = toC / d;
float s = max(Size, d * Px);
float on = (Where > 0.0 && Level * Scale > 0.0) ? 1.0 : 0.0;
float3 right = normalize(cross(float3(0.0, 0.0, 1.0), dir) + float3(1e-4, 0.0, 0.0));
float3 up = cross(dir, right);
float3 c = C - dir * min(s * 0.5 + 50.0, d * 0.25);
float2 q = LP.xy / 50.0;
return c + (q.x * right + q.y * up) * s * 0.5 * on - WP;
"""
FAR_GLOW_EM = """
float d = max(length(C - Cam), 1.0);
float s = max(Size, d * Px) * 0.01;
float2 p = UV * 2.0 - 1.0;
float r2 = dot(p, p);
float g = exp(-8.0 * r2) * saturate(1.0 - r2);
float blink = Period > 0.0 ? (frac(Time / Period + Phase) < Duty ? 1.0 : 0.0) : 1.0;
return float3(R, G, B) * (Level * Scale * Where * blink * g / (Spread * s * s));
"""
# a pool lying on its surface (the luminance at its middle falling as a point light's
# illuminance does over its falloff, H, to its radius) or a wash standing on its facade (soft
# at its edges); its quad collapsed to its middle where it does not show
FAR_FLAT_WPO = """
float on = (Where > 0.0 && Level * Scale > 0.0) ? 1.0 : 0.0;
return on > 0.5 ? float3(0.0, 0.0, 0.0) : C - WP;
"""
FAR_FLAT_EM = """
float2 p = UV * 2.0 - 1.0;
float prof;
if (Type < 1.5)
{
    float r = length(p);
    float rm = r * Rad / max(H, 1.0);
    float w = saturate(1.0 - r * r * r * r);
    prof = pow(1.0 + rm * rm, -1.5) * w * w;
}
else
{
    float2 a = saturate(1.0 - p * p * p * p);
    prof = a.x * a.x * a.y * a.y;
}
return float3(R, G, B) * (Level * Scale * Where * prof);
"""


def _far_inputs(m, c, names, defaults):
    ins = {}
    for k, n in enumerate(names):
        ins[n] = expr(m, unreal.MaterialExpressionPerInstanceCustomData, -1500, 90 * k,
                      data_index=k, const_default_value=defaults[k])
    cpos = custom(m, -1200, 0, "return float3(X, Y, Z);", ["X", "Y", "Z"], "CMOT_FLOAT3",
                  "CgFarAt")
    for n in ("X", "Y", "Z"):
        link(ins[n], "", cpos, n)
    cam = expr(m, unreal.MaterialExpressionCameraPositionWS, -1500, 1200)
    where = custom(m, -1000, 1200, FAR_WHERE,
                   ["C", "Cam", "Tier", "Mid", "High", "Fix", "Fade"], "CMOT_FLOAT1",
                   "CgFarWhere")
    for a, n in ((cpos, "C"), (cam, "Cam"), (ins["Tier"], "Tier"),
                 (mpc_param(m, c, "FarMidM", -1500, 1300), "Mid"),
                 (mpc_param(m, c, "FarHighM", -1500, 1350), "High"),
                 (mpc_param(m, c, "FarFixM", -1500, 1400), "Fix"),
                 (mpc_param(m, c, "FarFade", -1500, 1450), "Fade")):
        link(a, "", where, n)
    return ins, cpos, cam, where


def far_material(m):
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("used_with_instanced_static_meshes", True)


def far_glow(c):
    m, made = material("M_CgFarGlow")
    if not made:
        return m, False
    far_material(m)
    names = ("X", "Y", "Z", "R", "G", "B", "Size", "Tier", "Period", "Duty", "Phase", "Level")
    ins, cpos, cam, where = _far_inputs(m, c, names,
                                        (0, 0, 0, 1, 1, 1, 30, 0, 0, 1, 0, 1))
    lp = expr(m, unreal.MaterialExpressionPreSkinnedPosition, -1500, 1600)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1500, 1700)
    px = mpc_param(m, c, "FarPx", -1500, 1800)
    scale = mpc_param(m, c, "FarScale", -1500, 1900)
    wpo = custom(m, -700, 900, FAR_GLOW_WPO,
                 ["C", "Cam", "Size", "Px", "Where", "Level", "Scale", "LP", "WP"],
                 "CMOT_FLOAT3", "CgFarGlowWPO")
    for a, n in ((cpos, "C"), (cam, "Cam"), (ins["Size"], "Size"), (px, "Px"),
                 (where, "Where"), (ins["Level"], "Level"), (scale, "Scale"), (lp, "LP"),
                 (wp, "WP")):
        link(a, "", wpo, n)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1500, 2000, coordinate_index=0)
    tm = expr(m, unreal.MaterialExpressionTime, -1500, 2100)
    em = custom(m, -700, 200, FAR_GLOW_EM,
                ["C", "Cam", "Size", "Px", "UV", "R", "G", "B", "Period", "Duty", "Phase",
                 "Time", "Level", "Scale", "Where", "Spread"], "CMOT_FLOAT3", "CgFarGlow")
    for a, n in ((cpos, "C"), (cam, "Cam"), (ins["Size"], "Size"), (px, "Px"), (uv, "UV"),
                 (ins["R"], "R"), (ins["G"], "G"), (ins["B"], "B"), (ins["Period"], "Period"),
                 (ins["Duty"], "Duty"), (ins["Phase"], "Phase"), (tm, "Time"),
                 (ins["Level"], "Level"), (scale, "Scale"), (where, "Where"),
                 (mpc_param(m, c, "FarSpread", -1500, 2200), "Spread")):
        link(a, "", em, n)
    MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(wpo, "", MP.MP_WORLD_POSITION_OFFSET)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


def far_flat(c):
    m, made = material("M_CgFarFlat")
    if not made:
        return m, False
    far_material(m)
    names = ("X", "Y", "Z", "R", "G", "B", "Type", "Rad", "H", "Tier", "Level")
    ins, cpos, cam, where = _far_inputs(m, c, names, (0, 0, 0, 1, 1, 1, 1, 1500, 700, 0, 1))
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1500, 1600)
    scale = mpc_param(m, c, "FarScale", -1500, 1700)
    wpo = custom(m, -700, 900, FAR_FLAT_WPO, ["C", "Where", "Level", "Scale", "WP"],
                 "CMOT_FLOAT3", "CgFarFlatWPO")
    for a, n in ((cpos, "C"), (where, "Where"), (ins["Level"], "Level"), (scale, "Scale"),
                 (wp, "WP")):
        link(a, "", wpo, n)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1500, 1800, coordinate_index=0)
    em = custom(m, -700, 200, FAR_FLAT_EM,
                ["UV", "Type", "Rad", "H", "R", "G", "B", "Level", "Scale", "Where"],
                "CMOT_FLOAT3", "CgFarFlat")
    for a, n in ((uv, "UV"), (ins["Type"], "Type"), (ins["Rad"], "Rad"), (ins["H"], "H"),
                 (ins["R"], "R"), (ins["G"], "G"), (ins["B"], "B"), (ins["Level"], "Level"),
                 (scale, "Scale"), (where, "Where")):
        link(a, "", em, n)
    MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(wpo, "", MP.MP_WORLD_POSITION_OFFSET)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


def main():
    res = {"ok": False, "version": VERSION}
    try:
        if not EAL.does_directory_exist(FOLDER):
            EAL.make_directory(FOLDER)
        c, res["collection_made"] = collection()
        _, res["rain_made"] = rain(c)
        _, res["wet_color_made"] = wet_color(c)
        _, res["wet_gloss_made"] = wet_gloss(c)
        _, res["splash_made"] = splash(c)
        _, res["drip_made"] = drip(c)
        res["wet_dropped"] = drop_old()
        _, res["beacon_made"] = beacon()
        _, res["beam_made"] = beam()
        _, res["sky_made"] = sky_material()
        _, res["steam_made"] = steam(c)
        _, res["far_glow_made"] = far_glow(c)
        _, res["far_flat_made"] = far_flat(c)
        res["ok"] = True
    except Exception:
        res["error"] = traceback.format_exc()
        unreal.log_error(res["error"])
    res["total_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("CITYGEN_UE_DONE " + json.dumps({"ok": res["ok"], "total_s": res["total_s"]}))


main()
