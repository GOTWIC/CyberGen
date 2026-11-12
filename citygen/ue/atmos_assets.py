"""AT0: atmosgen's runtime assets, made in the editor from code (stdlib and `unreal` only;
run headless by `citygen.unreal_atmos.make_assets`, the job in $CITYGEN_UE_JOB):

- `/Game/CityGen/Core/Atmos/MPC_CityGenAtmos`: `Rain`, `Wetness`, `FogDensity`, `WindMS`,
  driven by the CityGenAtmos actor. A collection of its own, so adding it recompiles none of
  the city's materials (MPC_CityGen's layout is untouched until AT5 gives the masters their
  wetness input).
- `M_CgRain`: rain streaks, translucent and lit by the translucency volume (so the drops take
  the neon's colors), falling by world position offset with a phase per instance, drifting
  with the wind; the actor draws them as instanced cards round the view.
- `M_CgWet`: wet streets, a deferred (DBuffer) decal darkening the surfaces it covers and
  making them glossy, with puddles by a value noise on the world's plan.
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
VERSION = "8"   # 2: fewer, smaller puddles (1 blotched big paved yards seen from the air);
                # 3 (AT2): M_CgBeacon and M_CgBeam; 4 to 8 (AT3): M_CgSky
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty
T0 = time.time()


def meta(asset, key):
    return EAL.get_metadata_tag(asset, key) or ""


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
    have = []
    for name, v in (("Rain", 0.0), ("Wetness", 0.0), ("FogDensity", 0.0), ("WindMS", 4.0)):
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
        MEL.delete_all_material_expressions(m)
    return m, True


RAIN_MASK = """
float across = saturate(1.0 - abs(UV.y * 2.0 - 1.0));
float along = saturate((1.0 - abs(UV.x * 2.0 - 1.0)) * 1.6);
return across * across * along;
"""
# the card falls `Fall` cm at `Speed` cm/s from its place over the view, its phase per
# instance, drifting along world X with the wind
RAIN_WPO = """
float ph = frac(Time * Speed / Fall + Rnd);
float drift = Wind * 100.0 * ph * Fall / Speed * 0.35;
return float3(drift, 0.0, -ph * Fall);
"""


def rain(c):
    m, made = material("M_CgRain")
    if not made:
        return m, False
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("translucency_lighting_mode",
                          unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -900, 0, coordinate_index=0)
    mask = custom(m, -650, 0, RAIN_MASK, ["UV"], "CMOT_FLOAT1", "CgRainMask")
    link(uv, "", mask, "UV")
    r = mpc_param(m, c, "Rain", -650, 150)
    op = custom(m, -400, 100, "return Mask * 0.4 * saturate(Rain * 1.25);", ["Mask", "Rain"],
                "CMOT_FLOAT1", "CgRainOpacity")
    link(mask, "", op, "Mask")
    link(r, "", op, "Rain")
    col = expr(m, unreal.MaterialExpressionConstant3Vector, -400, -150,
               constant=unreal.LinearColor(0.62, 0.66, 0.72, 1.0))
    em = custom(m, -400, 250, "return float3(0.55, 0.6, 0.7) * Mask * 0.004;", ["Mask"],
                "CMOT_FLOAT3", "CgRainGlow")
    link(mask, "", em, "Mask")
    rough = expr(m, unreal.MaterialExpressionConstant, -400, 350, r=0.1)
    tm = expr(m, unreal.MaterialExpressionTime, -900, 500)
    rnd = expr(m, unreal.MaterialExpressionPerInstanceRandom, -900, 600)
    fall = expr(m, unreal.MaterialExpressionScalarParameter, -900, 700, parameter_name="Fall",
                default_value=2400.0)
    speed = expr(m, unreal.MaterialExpressionScalarParameter, -900, 800, parameter_name="Speed",
                 default_value=900.0)
    wind = mpc_param(m, c, "WindMS", -900, 900)
    wpo = custom(m, -600, 650, RAIN_WPO, ["Time", "Rnd", "Fall", "Speed", "Wind"],
                 "CMOT_FLOAT3", "CgRainFall")
    for a, n in ((tm, "Time"), (rnd, "Rnd"), (fall, "Fall"), (speed, "Speed"), (wind, "Wind")):
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


# puddles: a value noise on the plan (4 m and 1.3 m octaves), a puddle where it is high
WET_PUDDLE = """
float2 p = WP.xy / 100.0;
float n = 0.0;
float amp = 0.65;
float sc = 0.25;
for (int k = 0; k < 2; k++) {
  float2 q = p * sc;
  float2 i = floor(q);
  float2 f = frac(q);
  f = f * f * (3.0 - 2.0 * f);
  float a = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
  float b = frac(sin(dot(i + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
  float c = frac(sin(dot(i + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
  float d = frac(sin(dot(i + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
  n += amp * lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
  amp *= 0.55;
  sc *= 3.1;
}
return smoothstep(0.7, 0.76, n);
"""


def wet(c):
    m, made = material("M_CgWet")
    if not made:
        return m, False
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -900, 0)
    pud = custom(m, -650, 0, WET_PUDDLE, ["WP"], "CMOT_FLOAT1", "CgPuddle")
    link(wp, "", pud, "WP")
    w = mpc_param(m, c, "Wetness", -650, 200)
    col = custom(m, -400, -100, "return lerp(0.06, 0.02, Pud).xxx;", ["Pud"], "CMOT_FLOAT3",
                 "CgWetColor")
    link(pud, "", col, "Pud")
    rough = custom(m, -400, 50, "return lerp(0.02, 0.0, Pud);", ["Pud"], "CMOT_FLOAT1",
                   "CgWetRough")
    link(pud, "", rough, "Pud")
    op = custom(m, -400, 200, "return saturate(Wet) * lerp(0.62, 0.95, Pud);", ["Pud", "Wet"],
                "CMOT_FLOAT1", "CgWetOpacity")
    link(pud, "", op, "Pud")
    link(w, "", op, "Wet")
    MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(op, "", MP.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.atmos", VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m, True


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


def main():
    res = {"ok": False, "version": VERSION}
    try:
        if not EAL.does_directory_exist(FOLDER):
            EAL.make_directory(FOLDER)
        c, res["collection_made"] = collection()
        _, res["rain_made"] = rain(c)
        _, res["wet_made"] = wet(c)
        _, res["beacon_made"] = beacon()
        _, res["beam_made"] = beam()
        _, res["sky_made"] = sky_material()
        res["ok"] = True
    except Exception:
        res["error"] = traceback.format_exc()
        unreal.log_error(res["error"])
    res["total_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("CITYGEN_UE_DONE " + json.dumps({"ok": res["ok"], "total_s": res["total_s"]}))


main()
