"""LG4: the people library's clips for life at places (stdlib and `unreal` only), run in the
project's editor after the library is in place (`citygen/unreal_people.py`,
`ensure_place_clips`):

    UnrealEditor PROJECT.uproject -ExecCmds="py citygen/ue/people_places.py" -RenderOffscreen
        (env CITYGEN_UE_JOB: {result, manifest, hash, lib_hash, content, gas_mesh, clips,
         groups, looks, bake})

Epic's Game Animation Sample clips the places need (a bench's sitting loop, a few standing
idle breaks for talking, smoking, eating; people_idles: the bench's sit-down from five sides
and its stand-up), copied into the project from the user's sample first (the library's
`migrate`), retargeted onto each clip group's body skeleton with the library's own retargeter
(`<content>/Anim/<group>/RTG_GasToBody_<library hash>`), their notifies stripped, made in
place as the library's walks and idles are (a loop), or in the seat's frame (a transition:
`seat_frame`, the root still at the seat, the pelvis carrying the clip's travel and turn);
written to the manifest (`Saved/CityGenPeople/places.json`): per group, per clip, its path.

people_idles also bakes, per look of the library, a second mid bake beside the library's
(`<content>/MidIdle/<look>`: the library's walk, then a standing idle and the bench's sitting
loop, each a stretch of its clip that loops best, `loop_window`) with material instances of
the library's mid ones reading it, and a second impostor sheet (`<content>/FarIdle`: 8 views of
the walk's 8 frames as the library's, then 4 sitting and 4 standing idle poses) on a card
material that holds a cell for a person sitting or standing (`card_material`, custom data 12
and 13: first cell, cells). The library's own assets and hash are untouched, so its cache
stays valid; every clip made keeps the places' hash as metadata (`cg.places`), and a run with
the same hash keeps it; the bakes keep the bake's key (`cg.idles`), so editing this script
does not bake again unless the bake's version (`unreal_people.IDLE_BAKE`) moves. A run makes at
most `per_run` looks' bakes and sheets, then asks for a restart (`restart`), as the library's
build does.
"""

import json
import math
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
HASH = JOB["hash"]
BAKE = JOB.get("bake") or {}
BKEY = BAKE.get("key", "")
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
ML = unreal.MathLibrary
R = {"ok": False, "hash": HASH, "groups": {}, "missing": [], "looks": {}}
T0 = time.time()


def log(msg):
    unreal.log(f"CITYGEN_PLACES {msg}")


def save_result():
    R["wall_in_editor_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(R, f, indent=1, default=str)


def meta(asset, key="cg.places"):
    try:
        return EAL.get_metadata_tag(asset, key) or ""
    except Exception:                                               # noqa: BLE001
        return ""


def _keys(seq):
    AL = unreal.AnimationLibrary
    return AL.get_num_keys(seq) if hasattr(AL, "get_num_keys") else AL.get_num_frames(seq)


def _root_off(seq):
    for prop, v in (("force_root_lock", False), ("enable_root_motion", False)):
        try:
            seq.set_editor_property(prop, v)
        except Exception:                                           # noqa: BLE001
            pass


def in_place(seq):
    """The library's own rule (people_library.in_place): the root still at every key, the
    pelvis taking the root's height and turn, any travel dropped."""
    AL = unreal.AnimationLibrary
    n = _keys(seq)
    roots = [AL.get_bone_pose_for_frame(seq, "root", k, False) for k in range(n)]
    pelvis = [AL.get_bone_pose_for_frame(seq, "pelvis", k, False) for k in range(n)]
    x0, y0 = roots[0].translation.x, roots[0].translation.y
    xn, yn = roots[-1].translation.x, roots[-1].translation.y
    pos, rot = [], []
    for k in range(n):
        g = ML.compose_transforms(pelvis[k], roots[k])
        f = k / max(1, n - 1)
        t = g.translation
        pos.append(unreal.Vector(t.x - (x0 + (xn - x0) * f), t.y - (y0 + (yn - y0) * f), t.z))
        rot.append(g.rotation)
    ctrl = seq.get_editor_property("controller")
    ctrl.set_bone_track_keys("pelvis", pos, rot, [unreal.Vector(1, 1, 1)] * n, False)
    ctrl.set_bone_track_keys("root", [unreal.Vector(0, 0, 0)] * n, [unreal.Quat()] * n,
                             [unreal.Vector(1, 1, 1)] * n, False)
    _root_off(seq)
    log(f"in place {seq.get_name()}: {n} keys, travel {round(xn - x0, 1)}, {round(yn - y0, 1)} "
        f"cm, pelvis z {round(pos[0].z, 1)}")
    return {"keys": n, "travel_cm": [round(xn - x0, 1), round(yn - y0, 1)],
            "pelvis_z_cm": round(pos[0].z, 1)}


TRIM_CM = 130.0


def seat_frame(seq, ref):
    """people_idles: a transition made in the seat's frame: the root still at the seat (its
    pose at the clip's last key for a sit-down, `ref` "last", at its first for a stand-up,
    "first"; the bench's sitting loop has its root there), the pelvis carrying the clip's
    travel and turn about it. Where the clip's other end stands (its root there, in the
    seat's frame: cm in the mesh's frame and the turn in degrees about up) is what the walk
    processor walks a person to (a sit-down's start) or from (a stand-up's end)."""
    AL = unreal.AnimationLibrary
    n = _keys(seq)
    roots = [AL.get_bone_pose_for_frame(seq, "root", k, False) for k in range(n)]
    pelvis = [AL.get_bone_pose_for_frame(seq, "pelvis", k, False) for k in range(n)]
    ref_t = roots[-1] if ref == "last" else roots[0]
    # (the seat's frame on the ground: the root's place and turn in plan only; the sample's
    # bench clips lift the root onto the seat as the person sits, the sitting loop keeps it on
    # the ground with the pelvis 48 cm up)
    flat = unreal.Transform(location=unreal.Vector(ref_t.translation.x, ref_t.translation.y, 0.0),
                            rotation=unreal.Rotator(roll=0.0, pitch=0.0,
                                                    yaw=ref_t.rotation.rotator().yaw))
    inv = ML.invert_transform(flat)
    pos, rot = [], []
    for k in range(n):
        g = ML.compose_transforms(ML.compose_transforms(pelvis[k], roots[k]), inv)
        pos.append(g.translation)
        rot.append(g.rotation)
    # (the sample's sit-downs walk up to the bench from 3 to 4 m off and its stand-up walks 5 m
    # away: a person plays only the stretch within `TRIM_CM` of the seat, walking the rest
    # itself, so it never starts or ends in a road in front of the bench; `start_s` and
    # `end_s` bound that stretch, `other_cm` is the root at its far end)
    length = AL.get_sequence_length(seq)

    def plan_d(t):
        o = ML.compose_transforms(t, inv).translation
        return math.hypot(o.x, o.y)

    if ref == "last":
        k0 = next((k for k in range(n) if plan_d(roots[k]) <= TRIM_CM), n - 1)
        k1 = n - 1
    else:
        k0 = 0
        k1 = max((k for k in range(n) if plan_d(roots[k]) <= TRIM_CM), default=0)
    at = lambda k: length * k / max(1, n - 1)       # noqa: E731
    other = ML.compose_transforms(roots[k0] if ref == "last" else roots[k1], inv)
    yaw = other.rotation.rotator().yaw
    ctrl = seq.get_editor_property("controller")
    ctrl.set_bone_track_keys("pelvis", pos, rot, [unreal.Vector(1, 1, 1)] * n, False)
    ctrl.set_bone_track_keys("root", [unreal.Vector(0, 0, 0)] * n, [unreal.Quat()] * n,
                             [unreal.Vector(1, 1, 1)] * n, False)
    _root_off(seq)
    end = pos[-1] if ref == "last" else pos[0]
    out = {"keys": n, "ref": ref,
           "other_cm": [round(other.translation.x, 2), round(other.translation.y, 2)],
           "other_yaw": round(yaw, 2), "start_s": round(at(k0), 3), "end_s": round(at(k1), 3),
           "whole_cm": round(plan_d(roots[0] if ref == "last" else roots[-1]), 1),
           "pelvis_seat_cm": [round(end.x, 2), round(end.y, 2), round(end.z, 2)]}
    log(f"seat frame {seq.get_name()}: {out}")
    return out


def group_clips(key, rec):
    folder = f"{JOB['content']}/Anim/{key}"
    have = {k: f"{folder}/A_place_{k}" for k in JOB["clips"]}
    if all(EAL.does_asset_exist(p) and meta(unreal.load_asset(p)) == HASH for p in have.values()):
        log(f"{key}: kept")
        old = (JOB.get("old") or {}).get(key) or {}
        return {k: old.get(k) or {"anim": p} for k, p in have.items()}
    rtg = unreal.load_asset(rec["retargeter"])
    if rtg is None:
        raise RuntimeError(f"no retargeter {rec['retargeter']} (the library's)")
    src_mesh = unreal.load_asset(JOB["gas_mesh"])
    body = unreal.load_asset(rec["body"])
    if src_mesh is None or body is None:
        raise RuntimeError(f"the sample's mannequin {JOB['gas_mesh']} or the body {rec['body']} "
                           "is not in the project")
    out = {}
    for k, src in JOB["clips"].items():
        seq = unreal.load_asset(src)
        if seq is None:
            R["missing"].append(src)
            raise RuntimeError(f"no clip {src} in the project (the sample's, migrated first)")
        dst = have[k]
        if EAL.does_asset_exist(dst):
            EAL.delete_asset(dst)
        made = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
            [EAL.find_asset_data(src)], src_mesh, body, rtg, search="", replace="",
            prefix="", suffix=f"_{key}_place", target_path=folder)
        got = [str(x.get_editor_property("package_name")) for x in made]
        got = [g for g in got if unreal.load_asset(g) and
               isinstance(unreal.load_asset(g), unreal.AnimSequence)]
        if not got:
            raise RuntimeError(f"the retarget of {src} made nothing")
        EAL.rename_asset(got[0], dst)
        seq2 = unreal.load_asset(dst)
        try:
            unreal.AnimationLibrary.remove_all_animation_notify_tracks(seq2)
        except Exception as e:                                      # noqa: BLE001
            log(f"notifies of {k}: {e}")
        # (people_idles: a transition in the seat's frame, a loop in place)
        if k.startswith("sit_in"):
            info = seat_frame(seq2, "last")
        elif k.startswith("sit_out"):
            info = seat_frame(seq2, "first")
        else:
            info = in_place(seq2)
        info["length_s"] = round(unreal.AnimationLibrary.get_sequence_length(seq2), 3)
        EAL.set_metadata_tag(seq2, "cg.places", HASH)
        EAL.save_loaded_asset(seq2, only_if_is_dirty=False)
        out[k] = {"anim": dst, **info}
        log(f"{key} {k}: {dst} {info}")
        yield
    return out


# --- people_idles: the mid tier's idles (a second AnimToTexture bake per look) ----------------

LOOP_BONES = ("pelvis", "spine_03", "spine_05", "neck_01", "head", "clavicle_l", "clavicle_r",
              "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r",
              "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r")


def _qang(a, b):
    d = abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w)
    return 2.0 * math.acos(min(1.0, d))


def loop_window(seq, fps, lo_s, hi_s):
    """The stretch of a clip that loops best at the bake's rate: its first sample frame and
    its samples, from `lo_s` to `hi_s` long (the whole clip where it is no longer), where the
    pose at its start and the one a sample past its end differ least (the summed turn of the
    body's main bones and the pelvis's move; a longer stretch preferred a little). The clip's
    own frame of its start, for AnimToTexture's custom range (`clip_frame`)."""
    AL = unreal.AnimationLibrary
    length = AL.get_sequence_length(seq)
    n_keys = _keys(seq)
    clip_fps = (n_keys - 1) / max(1e-3, length)
    n = int(length * fps)
    sk = seq.get_editor_property("skeleton")
    names = [b for b in LOOP_BONES]
    poses = []
    for s in range(n + 1):
        fr = min(n_keys - 1, int(round(s / fps * clip_fps)))
        row = []
        for b in names:
            try:
                row.append(AL.get_bone_pose_for_frame(seq, b, fr, False))
            except Exception:                                       # noqa: BLE001
                row.append(None)
        poses.append(row)

    def diff(i, j):
        d = 0.0
        for a, b in zip(poses[i], poses[j]):
            if a is None or b is None:
                continue
            d += _qang(a.rotation, b.rotation)
        pa, pb = poses[i][0], poses[j][0]
        if pa is not None and pb is not None:
            d += 0.05 * (pa.translation - pb.translation).length()
        return d

    lo, hi = max(2, int(lo_s * fps)), int(hi_s * fps)
    if n <= hi:
        return {"start": 0, "samples": n, "clip_frame": 0, "error": round(diff(0, n), 4),
                "whole": True, "length_s": round(length, 3), "clip_fps": round(clip_fps, 3)}
    best = None
    for L in range(lo, hi + 1):
        for i in range(0, n - L + 1):
            e = diff(i, i + L) - 0.002 * L
            if best is None or e < best[0]:
                best = (e, i, L)
    _, i, L = best
    return {"start": i, "samples": L, "clip_frame": int(round(i / fps * clip_fps)),
            "error": round(diff(i, i + L), 4), "whole": False, "length_s": round(length, 3),
            "clip_fps": round(clip_fps, 3)}


def _asset(path, cls, factory):
    a = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
    if a is None:
        a = AT.create_asset(path.rsplit("/", 1)[1], path.rsplit("/", 1)[0], cls, factory)
    if a is None:
        raise RuntimeError(f"could not make {path}")
    return a


def _info(anim, start, end):
    info = unreal.AnimToTextureAnimSequenceInfo()
    info.set_editor_property("anim_sequence", anim)
    info.set_editor_property("use_custom_range", True)
    info.set_editor_property("start_frame", int(start))
    info.set_editor_property("end_frame", int(end))
    return info


def mid_bake(look, windows):
    """A look's mid mesh baked again (`<content>/MidIdle/<look>`): the library's walk as it
    baked it (its first sequence, its range), then the group's standing idle and the bench's
    sitting loop over their best loops; the library's data asset's settings (its mesh, LOD,
    UV channel, driver triangles, precision), the mesh itself not saved (the bake writes the
    UV channel the library's bake wrote, the same values); a material instance per slot,
    a child of the library's mid instance there, reading the new bone textures. Kept while
    its data asset carries the bake's key."""
    lid = look["id"]
    folder = f"{JOB['content']}/MidIdle/{lid}"
    da_path = f"{folder}/DA_{lid}_MidIdle"
    mesh = unreal.load_asset(look["mid"]["mesh"])
    if mesh is None:
        raise RuntimeError(f"{lid}: no mid mesh {look['mid']['mesh']}")
    nslots = len(mesh.get_editor_property("static_materials"))
    mats = [f"{folder}/MI_{lid}_MidIdle_{i}" for i in range(nslots)]
    if EAL.does_asset_exist(da_path) and meta(unreal.load_asset(da_path), "cg.idles") == BKEY \
            and all(EAL.does_asset_exist(p) for p in mats):
        da = unreal.load_asset(da_path)
        return _mid_record(da, mats, da_path, kept=True)
    lib = unreal.load_asset(look["mid"]["data"])
    if lib is None:
        raise RuntimeError(f"{lid}: no mid data asset {look['mid']['data']}")
    w0 = lib.get_editor_property("anim_sequences")[0]
    idle = unreal.load_asset(windows["idle"]["anim"])
    sit = unreal.load_asset(windows["sit"]["anim"])
    fac = unreal.DataAssetFactory()
    fac.set_editor_property("data_asset_class", unreal.AnimToTextureDataAsset)
    da = _asset(da_path, unreal.AnimToTextureDataAsset, fac)
    texs = {}
    for k in ("bone_position_texture", "bone_rotation_texture", "bone_weight_texture"):
        texs[k] = _asset(f"{folder}/T_{lid}_idle_{k.replace('_texture', '')}", unreal.Texture2D,
                         unreal.Texture2DFactoryNew())
    seqs = [_info(w0.get_editor_property("anim_sequence"), w0.get_editor_property("start_frame"),
                  w0.get_editor_property("end_frame"))]
    for w, a in ((windows["idle"], idle), (windows["sit"], sit)):
        seqs.append(_info(a, w["clip_frame"], w["clip_frame"] + w["samples"] - 1))
    for k in ("skeletal_mesh", "skeletal_lod_index", "static_mesh", "static_lod_index",
              "uv_channel", "mode", "precision", "num_bone_influences", "sample_rate",
              "num_driver_triangles", "sigma", "max_height", "max_width"):
        try:
            da.set_editor_property(k, lib.get_editor_property(k))
        except Exception as e:                                      # noqa: BLE001
            log(f"{lid}: the bake's {k}: {e}")
    for k, v in (("anim_sequences", seqs), ("auto_play", True), *texs.items()):
        da.set_editor_property(k, v)
    if not unreal.AnimToTextureBPLibrary.animation_to_texture(da):
        raise RuntimeError(f"{lid}: AnimToTexture's bake failed")
    for k, t in texs.items():
        if not EAL.save_loaded_asset(t, False):
            raise RuntimeError(f"{lid}: the bake's {k} was not saved")
    for i, sm_mat in enumerate(mesh.get_editor_property("static_materials")):
        parent = sm_mat.get_editor_property("material_interface")
        mi = _asset(mats[i], unreal.MaterialInstanceConstant,
                    unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, parent)
        unreal.AnimToTextureBPLibrary.update_material_instance_from_data_asset(
            da, mi, unreal.MaterialParameterAssociation.GLOBAL_PARAMETER)
        EAL.save_loaded_asset(mi, False)
    EAL.set_metadata_tag(da, "cg.idles", BKEY)
    EAL.save_loaded_asset(da, False)
    rec = _mid_record(da, mats, da_path, kept=False)
    log(f"mid idle {lid}: {rec}")
    return rec


def _mid_record(da, mats, da_path, kept):
    anims = da.get_editor_property("animations")
    rng = [[int(a.get_editor_property("start_frame")), int(a.get_editor_property("end_frame"))]
           for a in anims]
    if len(rng) < 3:
        raise RuntimeError(f"{da_path}: {len(rng)} animations baked, 3 wanted")
    return {"data": da_path, "materials": mats, "walk": rng[0], "idle": rng[1], "sit": rng[2],
            "frames": int(da.get_editor_property("num_frames")),
            "fps": float(da.get_editor_property("sample_rate")), "kept": kept}


# --- people_idles: the far cards' still poses (a second impostor sheet per look) --------------

def _sampled(tex):
    srgb = True
    try:
        srgb = bool(tex.get_editor_property("srgb"))
    except Exception:                                               # noqa: BLE001
        pass
    return (unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if srgb
            else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)


def _link(a, out, b, inp):
    for name in dict.fromkeys((inp, "", "Input", "VectorInput", "A")):
        if MEL.connect_material_expressions(a, out, b, name):
            return
    raise RuntimeError(f"could not link {a.get_name()}.{out} to {b.get_name()}.{inp}")


# the card material's own version (a new material when it moves; the sheets are kept): 2, its
# cells read upright (the library's card, and 1, drew the sheet's cells upside down: the
# plane's v runs against the card's height; a far person seen close stood on its head)
CARD_V = "2"


def card_material(sheet_tex, mask_tex):
    """M_CgPersonCardIdle_<key>: the library's card (people_library.card_material: a card
    turned to the view, the cell of its sheet for the view's side of the person, masked by the
    sheet's coverage, tinted by its dye mask) over a sheet of `rows` cells down: a person
    walking steps through the walk's cells (per-instance custom data 0 and 1: time offset,
    strides a second; 12 and 13 its first cell and cells, 0 the walk's), a person sitting or
    standing holds one cell (12 that cell, 13 one)."""
    path = f"{JOB['content']}/Materials/M_CgPersonCardIdle_{BKEY[:8]}_{CARD_V}"
    if EAL.does_asset_exist(path) and meta(unreal.load_asset(path), "cg.idles") == BKEY + CARD_V:
        return unreal.load_asset(path)
    m = _asset(path, unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(m)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("tangent_space_normal", False)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    V, F, WF = int(BAKE["views"]), int(BAKE["rows"]), int(BAKE["walk_frames"])
    W_CM, H_CM = float(BAKE["card_cm"][0]), float(BAKE["card_cm"][1])

    def e(cls, x, y, **kw):
        n = MEL.create_material_expression(m, cls, x, y)
        for k, v in kw.items():
            n.set_editor_property(k, v)
        return n

    def custom(code, ins, out_type, x, y):
        n = e(unreal.MaterialExpressionCustom, x, y, code=code, output_type=out_type)
        cis = []
        for k, _ in ins:
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", k)
            cis.append(ci)
        n.set_editor_property("inputs", cis)
        for k, src in ins:
            _link(src, "", n, k)
        return n

    cam = e(unreal.MaterialExpressionCameraPositionWS, -1600, 0)
    obj = e(unreal.MaterialExpressionObjectPositionWS, -1600, 150)
    wpos = e(unreal.MaterialExpressionWorldPosition, -1600, 300)
    to_cam = e(unreal.MaterialExpressionSubtract, -1350, 50)
    _link(cam, "", to_cam, "A")
    _link(obj, "", to_cam, "B")
    rel = e(unreal.MaterialExpressionSubtract, -1350, 250)
    _link(wpos, "", rel, "A")
    _link(obj, "", rel, "B")
    up = e(unreal.MaterialExpressionConstant3Vector, -1600, 450,
           constant=unreal.LinearColor(0, 0, 1, 0))
    up_w = e(unreal.MaterialExpressionTransform, -1350, 450)
    up_w.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL)
    up_w.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    _link(up, "", up_w, "")
    cam_l = e(unreal.MaterialExpressionTransform, -1100, 50)
    cam_l.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD)
    cam_l.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
    _link(to_cam, "", cam_l, "")
    lp = e(unreal.MaterialExpressionPreSkinnedPosition, -1600, 600)
    t0 = e(unreal.MaterialExpressionPerInstanceCustomData, -1600, 750, data_index=0)
    cps = e(unreal.MaterialExpressionPerInstanceCustomData, -1600, 850, data_index=1)
    first = e(unreal.MaterialExpressionPerInstanceCustomData, -1600, 1150, data_index=12)
    cnt = e(unreal.MaterialExpressionPerInstanceCustomData, -1600, 1250, data_index=13)
    tm = e(unreal.MaterialExpressionTime, -1600, 950)
    wpo_code = (
        "float2 d = ToCam.xy; float l = max(length(d), 1e-3); d /= l;\n"
        "float3 right = float3(d.y, -d.x, 0.0);\n"
        "float s = length(UpW);\n"
        "float u = LP.x / 100.0; float v = LP.y / 100.0 + 0.5;\n"
        f"float3 want = right * (u * {W_CM} * s) + float3(0,0,1) * (v * {H_CM} * s);\n"
        "return want - Rel;")
    wpo = custom(wpo_code, [("ToCam", to_cam), ("Rel", rel), ("UpW", up_w), ("LP", lp)],
                 unreal.CustomMaterialOutputType.CMOT_FLOAT3, -800, 300)
    MEL.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    uv_code = (
        f"float V = {V}.0; float F = {F}.0;\n"
        "float a = atan2(CamL.y, CamL.x); if (a < 0) a += 6.2831853;\n"
        "float view = fmod(floor(a / (6.2831853 / V) + 0.5), V);\n"
        f"float n = Cnt > 0.5 ? Cnt : {WF}.0;\n"
        "float fr = clamp(First + floor(frac((T + T0) * Cps) * n), 0.0, F - 1.0);\n"
        "float x = UV.x; float y = UV.y;\n"
        "return float2((view + x) / V, (fr + 1.0 - saturate(y)) / F);")
    tc = e(unreal.MaterialExpressionTextureCoordinate, -1600, 1050)
    uv = custom(uv_code, [("CamL", cam_l), ("T", tm), ("T0", t0), ("Cps", cps), ("UV", tc),
                          ("First", first), ("Cnt", cnt)],
                unreal.CustomMaterialOutputType.CMOT_FLOAT2, -800, 700)
    sheet = e(unreal.MaterialExpressionTextureSampleParameter2D, -500, 700,
              parameter_name="Sheet", sampler_type=_sampled(sheet_tex), texture=sheet_tex)
    _link(uv, "", sheet, "UVs")
    pt = [e(unreal.MaterialExpressionPerInstanceCustomData3Vector, -800, 1350 + 150 * k,
            data_index=2 + 3 * k, const_default_value=unreal.LinearColor(1, 1, 1, 1))
          for k in range(3)]
    cover = e(unreal.MaterialExpressionTextureSampleParameter2D, -500, 950,
              parameter_name="Mask", sampler_type=_sampled(mask_tex), texture=mask_tex)
    _link(uv, "", cover, "UVs")
    tinted = custom("float3 m = saturate(M);\n"
                    "return C * (1.0 + m.r * (T0 - 1.0) + m.g * (T1 - 1.0) + m.b * (T2 - 1.0));",
                    [("C", sheet), ("M", cover), ("T0", pt[0]), ("T1", pt[1]), ("T2", pt[2])],
                    unreal.CustomMaterialOutputType.CMOT_FLOAT3, -250, 650)
    MEL.connect_material_property(tinted, "", unreal.MaterialProperty.MP_BASE_COLOR)
    inv = e(unreal.MaterialExpressionOneMinus, -250, 850)
    _link(cover, "A", inv, "")
    MEL.connect_material_property(inv, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    nrm = e(unreal.MaterialExpressionNormalize, -250, 1000)
    _link(to_cam, "", nrm, "VectorInput")
    MEL.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    rough = e(unreal.MaterialExpressionConstant, -250, 1150, r=0.8)
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.idles", BKEY + CARD_V)
    EAL.save_loaded_asset(m, False)
    return m


def capture_sheet(look, mid):
    """A look's still sheet: its mid mesh (the new bake's instances, auto play off, a frame
    set by hand) from `views` sides, rows down: the walk's frames as the library's sheet has
    them (one stride), then `sit_cells` frames spread over the sitting loop and `idle_cells`
    over the standing idle; a color pass and the dye mask's (the library's capture,
    people_library.capture_sheet). Kept while its card instance carries the bake's key."""
    lid = look["id"]
    folder = f"{JOB['content']}/FarIdle"
    mip = f"{folder}/MI_{lid}_CardIdle"
    if EAL.does_asset_exist(mip) and meta(unreal.load_asset(mip), "cg.idles") == BKEY:
        # (a kept sheet's card on the card material of this version)
        mi = unreal.load_asset(mip)
        sheet_tex = MEL.get_material_instance_texture_parameter_value(mi, "Sheet")
        mask_tex = MEL.get_material_instance_texture_parameter_value(mi, "Mask")
        want = card_material(sheet_tex, mask_tex)
        if mi.get_editor_property("parent") != want:
            MEL.set_material_instance_parent(mi, want)
            MEL.set_material_instance_texture_parameter_value(mi, "Sheet", sheet_tex)
            MEL.set_material_instance_texture_parameter_value(mi, "Mask", mask_tex)
            EAL.save_loaded_asset(mi, False)
        return {"material": mip, "kept": True}
    V, F = int(BAKE["views"]), int(BAKE["rows"])
    WF, SC, IC = int(BAKE["walk_frames"]), int(BAKE["sit_cells"]), int(BAKE["idle_cells"])
    cw, ch = [int(v) for v in BAKE["cell"]]
    W_CM, H_CM = float(BAKE["card_cm"][0]), float(BAKE["card_cm"][1])
    tex_path = f"{folder}/T_{lid}_SheetIdle"
    mask_path = f"{folder}/T_{lid}_MaskIdle"
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    RL = unreal.RenderingLibrary
    origin = unreal.Vector(0.0, 0.0, 200000.0)
    mesh = unreal.load_asset(look["mid"]["mesh"])
    holder = eas.spawn_actor_from_class(unreal.StaticMeshActor, origin,
                                        unreal.Rotator(0.0, 0.0, -90.0), transient=True)
    smc = holder.static_mesh_component
    smc.set_mobility(unreal.ComponentMobility.MOVABLE)
    smc.set_static_mesh(mesh)
    caps = []
    for i, path in enumerate(mid["materials"]):
        parent = unreal.load_asset(path)
        pp = f"{folder}/{lid}/MI_{lid}_IdlePose_{i}"
        if EAL.does_asset_exist(pp):
            EAL.delete_asset(pp)
        mi = AT.create_asset(pp.rsplit("/", 1)[1], pp.rsplit("/", 1)[0],
                             unreal.MaterialInstanceConstant,
                             unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, parent)
        MEL.set_material_instance_static_switch_parameter_value(mi, "AutoPlay", False)
        MEL.set_material_instance_scalar_parameter_value(mi, "Frame", 0.0)
        MEL.update_material_instance(mi)
        smc.set_material(i, mi)
        caps.append(mi)
    actors = [holder]

    def capturer(source, flags_off):
        cam = eas.spawn_actor_from_class(unreal.SceneCapture2D, origin, transient=True)
        cap = cam.capture_component2d
        cap.set_editor_property("projection_type", unreal.CameraProjectionMode.ORTHOGRAPHIC)
        cap.set_editor_property("ortho_width", W_CM)
        cap.set_editor_property("capture_source", source)
        cap.set_editor_property("capture_every_frame", False)
        cap.set_editor_property("capture_on_movement", False)
        cap.set_editor_property("primitive_render_mode",
                                unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
        for act in actors:
            cap.show_only_actor_components(act, True)
        flags = []
        for name in flags_off:
            fl = unreal.EngineShowFlagsSetting()
            fl.set_editor_property("show_flag_name", name)
            fl.set_editor_property("enabled", False)
            flags.append(fl)
        cap.set_editor_property("show_flag_settings", flags)
        cell = RL.create_render_target2d(world, cw, ch, unreal.TextureRenderTargetFormat.RTF_RGBA16F,
                                         unreal.LinearColor(0, 0, 0, 1), False)
        cap.set_editor_property("texture_target", cell)
        return cam, cap, cell

    cam_c, cap_c, cell_c = capturer(unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
                                    ("Atmosphere", "Fog", "Bloom", "LensFlares"))
    cam_m, cap_m, cell_m = capturer(unreal.SceneCaptureSource.SCS_SCENE_COLOR_HDR,
                                    ("Lighting", "PostProcessing", "Atmosphere", "Fog"))
    light = eas.spawn_actor_from_class(unreal.DirectionalLight, origin, transient=True)
    sheet = RL.create_render_target2d(world, cw * V, ch * F,
                                      unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                      unreal.LinearColor(0, 0, 0, 1), False)
    mask = RL.create_render_target2d(world, cw * V, ch * F,
                                     unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                     unreal.LinearColor(0, 0, 0, 1), False)
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    # (the rows' frames in the new bake: the walk's as the library's sheet (its first frame
    # and one stride over WF cells), then the sitting and the idle cells spread over their
    # loops)
    w0 = float(mid["walk"][0])
    cyc = float(look["mid"].get("cycle_s", 1.0)) * float(mid["fps"])
    frames = [w0 + cyc * f / WF for f in range(WF)]
    for (a, b), n in ((mid["sit"], SC), (mid["idle"], IC)):
        frames += [float(a) + (b - a + 1) * k / n for k in range(n)]
    for cam, cap, cell, target, dye in ((cam_c, cap_c, cell_c, sheet, 0.0),
                                        (cam_m, cap_m, cell_m, mask, 1.0)):
        for f, frame in enumerate(frames):
            for mi in caps:
                MEL.set_material_instance_scalar_parameter_value(mi, "Frame", frame)
                MEL.set_material_instance_scalar_parameter_value(mi, "DyeMode", dye)
                MEL.update_material_instance(mi)
            unreal.AutomationLibrary.finish_loading_before_screenshot()
            for _ in range(2):
                yield
            for v in range(V):
                a = 2.0 * math.pi * v / V
                eye = unreal.Vector(origin.x + 600.0 * math.cos(a), origin.y + 600.0 * math.sin(a),
                                    origin.z + H_CM / 2.0)
                look_at = unreal.Rotator(0.0, 0.0, math.degrees(a) + 180.0)
                light.set_actor_rotation(unreal.Rotator(0.0, -35.0, math.degrees(a) + 200.0), False)
                cam.set_actor_location(eye, False, False)
                cam.set_actor_rotation(look_at, False)
                cap.capture_scene()
                canvas, size, ctx = RL.begin_draw_canvas_to_render_target(world, target)
                canvas.draw_texture(cell, unreal.Vector2D(v * cw, f * ch), unreal.Vector2D(cw, ch),
                                    unreal.Vector2D(0, 0), unreal.Vector2D(1, 1),
                                    unreal.LinearColor(1, 1, 1, 1), unreal.BlendMode.BLEND_OPAQUE)
                RL.end_draw_canvas_to_render_target(world, ctx)
            yield
    for rt, path, srgb in ((sheet, tex_path, True), (mask, mask_path, False)):
        if EAL.does_asset_exist(path):
            EAL.delete_asset(path)
        tex = RL.render_target_create_static_texture2d_editor_only(rt, path)
        if tex is None:
            raise RuntimeError(f"{lid}: the sheet's texture {path} was not made")
        EAL.save_loaded_asset(tex)
        if JOB.get("sheets_dir") and lid in (JOB.get("export_sheets") or []):
            try:
                RL.export_render_target(world, rt, JOB["sheets_dir"],
                                        f"{'sheet' if srgb else 'mask'}_idle_{lid}.png")
            except Exception as e:                                  # noqa: BLE001
                log(f"sheet export: {e}")
    for act in [cam_c, cam_m, light] + actors:
        eas.destroy_actor(act)
    sheet_tex = unreal.load_asset(tex_path)
    mask_tex = unreal.load_asset(mask_path)
    if EAL.does_asset_exist(mip):
        EAL.delete_asset(mip)
    mi = AT.create_asset(mip.rsplit("/", 1)[1], folder, unreal.MaterialInstanceConstant,
                         unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, card_material(sheet_tex, mask_tex))
    MEL.set_material_instance_texture_parameter_value(mi, "Sheet", sheet_tex)
    MEL.set_material_instance_texture_parameter_value(mi, "Mask", mask_tex)
    EAL.set_metadata_tag(mi, "cg.idles", BKEY)
    EAL.save_loaded_asset(mi, False)
    return {"material": mip, "sheet": tex_path, "kept": False}


def step_idles(groups):
    """people_idles: per group the idle's and the sitting loop's best loops; per look its mid
    bake and its still sheet (at most `per_run` made a run)."""
    if not BAKE or not JOB.get("looks"):
        return {}
    fps = float(BAKE["fps"])
    windows = {}
    for key, g in sorted(JOB["groups"].items()):
        idle = unreal.load_asset(g["idle"])
        sit = unreal.load_asset(groups[key]["sit"]["anim"])
        if idle is None or sit is None:
            raise RuntimeError(f"{key}: no idle {g['idle']} or sitting loop to bake")
        windows[key] = {
            "idle": {"anim": g["idle"], **loop_window(idle, fps, *BAKE["idle_s"])},
            "sit": {"anim": groups[key]["sit"]["anim"], **loop_window(sit, fps, *BAKE["sit_s"])}}
        log(f"{key} loops: {windows[key]}")
        yield
    R["windows"] = windows
    made = 0
    per_run = int(JOB.get("per_run", 48))
    for look in JOB["looks"]:
        lid = look["id"]
        if made >= per_run:
            R["restart"] = True
            log(f"restart after {made} looks")
            return windows
        mid = mid_bake(look, windows[look["skeleton"]])
        yield
        far = {"material": None}
        gen = capture_sheet(look, mid)
        while True:
            try:
                next(gen)
                yield
            except StopIteration as s:
                far = s.value
                break
        R["looks"][lid] = {"mid": {k: v for k, v in mid.items() if k != "kept"},
                           "far": {k: v for k, v in far.items() if k != "kept"}}
        if not (mid.get("kept") and far.get("kept")):
            made += 1
            save_result()
    return windows


def run():
    yield
    unreal.AssetRegistryHelpers.get_asset_registry().wait_for_completion()
    try:
        for key, rec in sorted(JOB["groups"].items()):
            res = yield from group_clips(key, rec)
            R["groups"][key] = res
        windows = yield from step_idles(R["groups"])
        if R.get("restart"):
            save_result()
            return
        man = {"hash": HASH, "lib_hash": JOB["lib_hash"], "clips": list(JOB["clips"]),
               "groups": R["groups"]}
        if BAKE and JOB.get("looks"):
            man["idles"] = {"key": BKEY, "windows": windows,
                            "card": {"views": int(BAKE["views"]), "rows": int(BAKE["rows"]),
                                     "walk": [0, int(BAKE["walk_frames"])],
                                     "sit": [int(BAKE["walk_frames"]), int(BAKE["sit_cells"])],
                                     "idle": [int(BAKE["walk_frames"]) + int(BAKE["sit_cells"]),
                                              int(BAKE["idle_cells"])]},
                            "looks": R["looks"]}
        os.makedirs(os.path.dirname(JOB["manifest"]), exist_ok=True)
        with open(JOB["manifest"], "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1)
        R["ok"] = True
    except Exception as e:                                          # noqa: BLE001
        R["error"] = f"{type(e).__name__}: {e}"
        R["trace"] = traceback.format_exc()[-3000:]
        log(f"FAILED: {e}")
    save_result()


GEN = run()
HANDLE = None
BUSY = [False]


def finish():
    save_result()
    print("CITYGEN_UE_DONE " + json.dumps({"ok": R["ok"]}))
    unreal.unregister_slate_post_tick_callback(HANDLE)
    unreal.SystemLibrary.quit_editor()


def tick(dt):
    if BUSY[0]:
        return
    BUSY[0] = True
    try:
        next(GEN)
    except StopIteration:
        finish()
    except Exception:                                               # noqa: BLE001
        R["error"] = traceback.format_exc()
        unreal.log_error(R["error"])
        finish()
    finally:
        BUSY[0] = False


HANDLE = unreal.register_slate_post_tick_callback(tick)
