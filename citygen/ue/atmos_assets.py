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
VERSION = "1"
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
return smoothstep(0.62, 0.7, n);
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


def main():
    res = {"ok": False, "version": VERSION}
    try:
        if not EAL.does_directory_exist(FOLDER):
            EAL.make_directory(FOLDER)
        c, res["collection_made"] = collection()
        _, res["rain_made"] = rain(c)
        _, res["wet_made"] = wet(c)
        res["ok"] = True
    except Exception:
        res["error"] = traceback.format_exc()
        unreal.log_error(res["error"])
    res["total_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("CITYGEN_UE_DONE " + json.dumps({"ok": res["ok"], "total_s": res["total_s"]}))


main()
