"""AG18's vehicle check, run inside the Unreal 5.8 editor (stdlib and the `unreal` module
only), on a level `citygen unreal` imported with vehicle placements:

    UnrealEditor PROJECT.uproject "-ExecCmds=py citygen/ue/check_vehicles.py" -unattended

with $CITYGEN_UE_JOB naming a job file ({"manifest", "result", "shots", "width"}) that
`citygen unreal --check-vehicles` writes (`unreal_vehicles.check`). In the editor world, all
the level's actors loaded, it checks and, with `shots`, renders:

- the meshes: per car and part four LODs with the pack's triangles, no Nanite, the glass's
  dark slot from the pack's `opaque_from_lod`, the body's convex hulls as its collision;
- the placements: an actor per entry with a component per model and part, an instance per
  vehicle, each wheel's instance at its pivot (axle middle), the paint in its custom data;
- collision: traces down and across onto every placed body, none onto a wheel or glass;
- the wheels: one spun about its axle (local y) and steered (local z) by script, shot;
- views by day and by night (MPC_CityGen's Night, a dim sun, a fixed night exposure): the
  line-up (show colors and other paint), each car alone from its pack's hero camera (to set
  beside the pack's proof), one car at each LOD forced, the hulls of one in place of its body.
"""

import json
import math
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
T0 = time.time()
RES = {"ok": False, "checks": {}, "shots": []}
NIGHT_EV100 = -3.0          # the play features' night exposure (CityGenPlayActor)
VISIBILITY = getattr(unreal.TraceTypeQuery, "ECC_VISIBILITY", None) or \
    unreal.TraceTypeQuery.TRACE_TYPE_QUERY1


def log(msg):
    unreal.log(f"citygen vehicles: {msg} ({time.time() - T0:.1f} s)")


def ue(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def wait(seconds):
    t = time.time()
    while time.time() - t < seconds:
        yield


def tags_of(o, comp=False):
    return [str(t) for t in (o.component_tags if comp else o.tags)]


def tag(o, key, comp=False):
    p = key + "="
    return next((t[len(p):] for t in tags_of(o, comp) if t.startswith(p)), "")


def car_frame(pivot, xf, p):
    """A point p of a car's frame (x forward, y left, z up) in citygen meters, the car at
    xf from its entry's pivot."""
    a = math.radians(xf[3])
    ca, sa = math.cos(a), math.sin(a)
    return (pivot[0] + xf[0] + ca * p[0] - sa * p[1],
            pivot[1] + xf[1] + sa * p[0] + ca * p[1],
            pivot[2] + xf[2] + p[2])


def trace(world, a, b):
    hit = unreal.SystemLibrary.line_trace_single(
        world, a, b, VISIBILITY, False, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    t = hit.to_tuple()
    if not t[0]:
        return None
    return {"actor": t[9], "comp": t[10], "point": t[5]}


# --- the checks ---------------------------------------------------------------------------------

def check_meshes(man):
    sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem) or \
        unreal.get_default_object(unreal.StaticMeshEditorSubsystem)
    out, bad = {}, []
    for car, rec in sorted(man["vehicles"]["cars"].items()):
        opaque_from = int((rec.get("glass") or {}).get("opaque_from_lod", 99))
        row = {}
        for p in rec["parts"]:
            sm = unreal.load_asset(f"{rec['folder']}/SM_{car}_{p['name']}")
            if sm is None:
                bad.append(f"{car}.{p['name']}: no mesh")
                continue
            n = sms.get_lod_count(sm)
            tris = [sm.get_num_triangles(k) for k in range(n)]
            want = [lo["parts"].get(p["name"]) for lo in rec["lods"]]
            nanite = bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
            slots = [sms.get_lod_material_slot(sm, k, 0) for k in range(n)]
            bb = sm.get_bounding_box()
            mid = [(bb.min.x + bb.max.x) / 200.0, -(bb.min.y + bb.max.y) / 200.0,
                   (bb.min.z + bb.max.z) / 200.0]
            r = {"lods": n, "triangles": tris, "pack": want, "nanite": nanite, "slots": slots,
                 "mid_m": [round(v, 3) for v in mid]}
            if p["kind"] == "body":
                r["hulls"] = sms.get_convex_collision_count(sm)
                if r["hulls"] != len(rec.get("hulls") or []):
                    bad.append(f"{car}.body: {r['hulls']} hulls, the pack has "
                               f"{len(rec.get('hulls') or [])}")
            if n != len(rec["lods"]):
                bad.append(f"{car}.{p['name']}: {n} LODs")
            if nanite:
                bad.append(f"{car}.{p['name']}: Nanite on")
            for k, (a, b) in enumerate(zip(tris, want)):
                if b and abs(a - b) > max(2, 0.02 * b):
                    bad.append(f"{car}.{p['name']} LOD{k}: {a} triangles, the pack {b}")
            if p["kind"] == "glass":
                dark = [k for k in range(n) if slots[k] != slots[0]]
                if dark != list(range(opaque_from, n)):
                    bad.append(f"{car}.glass: dark slot on LODs {dark}")
            if p["kind"] in ("wheel", "brake"):
                # (a wheel's mesh about its own origin, the axle's middle: its box's middle
                # within 2 cm of it along x and z; a brake sits off-center by design)
                if p["kind"] == "wheel" and (abs(mid[0]) > 0.02 or abs(mid[2]) > 0.02):
                    bad.append(f"{car}.{p['name']}: mesh middle {r['mid_m']} off its pivot")
            row[p["name"]] = r
        out[car] = row
    RES["checks"]["meshes"] = {"ok": not bad, "bad": bad[:40], "cars": out}
    log(f"meshes: {len(bad)} faults")


def vehicle_actors(world, slug):
    out = {}
    for a in unreal.GameplayStatics.get_all_actors_with_tag(world, f"cg.city={slug}"):
        if tag(a, "cg.type") == "vehicles":
            out[tag(a, "cg.key")] = a
    return out


def components(a):
    out = {}
    for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
        if "cg.member" in tags_of(c, True):
            out[(tag(c, "cg.vehicle", True), tag(c, "cg.part", True))] = c
    return out


def check_placements(man, actors):
    bad, n = [], 0
    cars = man["vehicles"]["cars"]
    for r in man["vehicles"]["placements"]:
        a = actors.get(r["key"])
        if a is None:
            bad.append(f"{r['key']}: no actor")
            continue
        comps = components(a)
        for car, m in r["models"].items():
            for p in cars[car]["parts"]:
                c = comps.get((car, p["name"]))
                if c is None:
                    bad.append(f"{r['key']}: no component {car}.{p['name']}")
                    continue
                if c.get_instance_count() != len(m["ids"]):
                    bad.append(f"{r['key']} {car}.{p['name']}: {c.get_instance_count()} "
                               f"instances, {len(m['ids'])} placed")
                if tag(c, "cg.id", True) != m["ids"][0]:
                    bad.append(f"{r['key']} {car}.{p['name']}: ids out of order")
                for i, xf in enumerate(m["xforms"]):
                    t = c.get_instance_transform(i, True)
                    want = ue(*car_frame(r["pivot"], xf, p["pivot"]))
                    d = (t.translation - want).length()
                    if d > 1.0:              # (cm)
                        bad.append(f"{r['key']} {car}.{p['name']}[{i}]: {d:.1f} cm off "
                                   "its pivot")
                n += 1
    RES["checks"]["placements"] = {"ok": not bad, "bad": bad[:40], "components": n}
    log(f"placements: {n} components, {len(bad)} faults")


def check_collision(world, man, actors):
    """Traces down onto every placed body (a grid over its footprint inside its box) and
    across it at its middle height from both sides; a hit counts on the vehicle's body
    component (never a wheel's or the glass's)."""
    cars = man["vehicles"]["cars"]
    rows = {}
    bad = []
    for r in man["vehicles"]["placements"]:
        a = actors.get(r["key"])
        if a is None:
            continue
        for car, m in r["models"].items():
            d = cars[car]["dimensions"]
            lo, hi = d["min"], d["max"]
            for xf in m["xforms"]:
                down, hit_down, side, hit_side, wrong = 0, 0, 0, 0, 0
                for fx in (0.25, 0.5, 0.75):
                    for fy in (0.3, 0.5, 0.7):
                        p = (lo[0] + fx * (hi[0] - lo[0]), lo[1] + fy * (hi[1] - lo[1]))
                        top = car_frame(r["pivot"], xf, (p[0], p[1], hi[2] + 2.0))
                        bot = car_frame(r["pivot"], xf, (p[0], p[1], -0.5))
                        h = trace(world, ue(*top), ue(*bot))
                        down += 1
                        if h and h["actor"] == a:
                            part = tag(h["comp"], "cg.part", True) if h["comp"] else ""
                            if part == "body":
                                hit_down += 1
                            else:
                                wrong += 1
                zc = lo[2] + 0.5 * (hi[2] - lo[2])
                for fx in (0.3, 0.5, 0.7):
                    x = lo[0] + fx * (hi[0] - lo[0])
                    for sgn in (1, -1):
                        a0 = car_frame(r["pivot"], xf, (x, sgn * (hi[1] + 2.0), zc))
                        a1 = car_frame(r["pivot"], xf, (x, 0.0, zc))
                        h = trace(world, ue(*a0), ue(*a1))
                        side += 1
                        if h and h["actor"] == a and \
                                tag(h["comp"], "cg.part", True) == "body":
                            hit_side += 1
                row = rows.setdefault(car, {"down": 0, "hit_down": 0, "side": 0,
                                            "hit_side": 0, "other_part": 0})
                for k, v in (("down", down), ("hit_down", hit_down), ("side", side),
                             ("hit_side", hit_side), ("other_part", wrong)):
                    row[k] += v
    for car, row in rows.items():
        if row["hit_down"] < 0.8 * row["down"] or row["hit_side"] < 0.8 * row["side"] or \
                row["other_part"]:
            bad.append(f"{car}: {row}")
    RES["checks"]["collision"] = {"ok": not bad, "bad": bad, "cars": rows}
    log(f"collision: {rows}")


# --- views ---------------------------------------------------------------------------------------

def shot(name, eye, target, fov_deg, w=None):
    """A render from a camera at eye looking at target (Unreal centimeters)."""
    out = JOB["shots"]
    w = int(w or JOB.get("width") or 1920)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    cam = eas.spawn_actor_from_class(unreal.CameraActor, eye, transient=True)
    cam.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(eye, target), False)
    cam.camera_component.set_editor_property("field_of_view", fov_deg)
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    warm = os.path.join(out, f"warm_{name}.png")
    unreal.AutomationLibrary.take_high_res_screenshot(640, 360, warm, cam)
    t = time.time()
    while not os.path.exists(warm) and time.time() - t < 120:
        yield
    yield from wait(1.5)
    if os.path.exists(warm):
        os.remove(warm)
    path = os.path.join(out, f"{name}.png")
    if os.path.exists(path):
        os.remove(path)
    unreal.AutomationLibrary.take_high_res_screenshot(w, w * 9 // 16, path, cam)
    t = time.time()
    while not os.path.exists(path) and time.time() - t < 300:
        yield
    yield from wait(0.5)
    eas.destroy_actor(cam)
    if os.path.exists(path):
        RES["shots"].append(path)
        log(f"wrote {path}")


def hero_camera(rec, pivot, xf):
    """The pack's hero camera (Blender's: looking down its -z, a 36 mm sensor) placed with
    the car: (eye, target) in Unreal cm and the horizontal field of view."""
    cam = rec.get("hero_camera")
    if not cam:
        return None
    m = cam["matrix"]
    pos = (m[0][3], m[1][3], m[2][3])
    fwd = (-m[0][2], -m[1][2], -m[2][2])
    tgt = tuple(pos[i] + fwd[i] * 8.0 for i in range(3))
    fov = 2.0 * math.degrees(math.atan(cam.get("sensor", 36.0) / 2.0 / cam["lens"]))
    return ue(*car_frame(pivot, xf, pos)), ue(*car_frame(pivot, xf, tgt)), fov


def set_hidden(actors, keep):
    for k, a in actors.items():
        a.set_is_temporarily_hidden_in_editor(k not in keep)


def night(on, world):
    """MPC_CityGen's Night, the sun dimmed to a moon, the sky light dimmed, and an unbound
    post process volume holding the play features' night exposure."""
    mpc = unreal.load_asset("/Game/CityGen/Core/MPC_CityGen")
    if mpc is not None:
        unreal.MaterialLibrary.set_scalar_parameter_value(world, mpc, "Night",
                                                          1.0 if on else 0.0)
    for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.DirectionalLight):
        c = a.get_component_by_class(unreal.DirectionalLightComponent)
        base = NIGHT.setdefault(("sun", a.get_name()), c.intensity)
        c.set_intensity(base * (0.03 if on else 1.0))
    for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkyLight):
        c = a.get_component_by_class(unreal.SkyLightComponent)
        base = NIGHT.setdefault(("sky", a.get_name()), c.intensity)
        c.set_intensity(base * (0.05 if on else 1.0))
    vol = NIGHT.get("volume")
    if on and vol is None:
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        vol = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0),
                                         transient=True)
        vol.set_editor_property("unbound", True)
        s = vol.get_editor_property("settings")
        for k, v in (("override_auto_exposure_min_brightness", True),
                     ("override_auto_exposure_max_brightness", True),
                     ("auto_exposure_min_brightness", NIGHT_EV100),
                     ("auto_exposure_max_brightness", NIGHT_EV100)):
            s.set_editor_property(k, v)
        vol.set_editor_property("settings", s)
        NIGHT["volume"] = vol
    if vol is not None:
        vol.set_editor_property("enabled", bool(on))


NIGHT = {}


def hull_actor(rec, pivot, xf):
    """The pack's hulls as a mesh of their own (a dynamic mesh actor, GeometryScript), placed
    where the car is."""
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    a = eas.spawn_actor_from_class(unreal.DynamicMeshActor,
                                   ue(*car_frame(pivot, xf, (0, 0, 0))),
                                   unreal.Rotator(0.0, 0.0, -xf[3]), transient=True)
    comp = a.get_component_by_class(unreal.DynamicMeshComponent)
    dm = comp.get_dynamic_mesh()
    ME = unreal.GeometryScript_MeshEdits
    for h in rec["hulls"]:
        ids = []
        for x, y, z in h["vertices"]:
            r = ME.add_vertex_to_mesh(dm, unreal.Vector(x * 100.0, -y * 100.0, z * 100.0))
            ids.append(r[1] if isinstance(r, tuple) else r)
        for i, j, k in h["triangles"]:
            # (y flipped: the triangle turns the other way round)
            ME.add_triangle_to_mesh(dm, unreal.IntVector(ids[i], ids[k], ids[j]), 0)
    N = getattr(unreal, "GeometryScript_Normals", None)
    if N is not None:
        try:
            N.set_per_face_normals(dm)
        except Exception as e:
            log(f"hull normals: {e}")
    mat = unreal.load_asset("/Game/CityGen/Core/M_CityGen")
    if mat is not None:
        comp.set_material(0, mat)
    return a


def views(world, man, actors):
    veh = man["vehicles"]
    by_key = {r["key"]: r for r in veh["placements"]}
    cars = veh["cars"]
    lineup = [k for k in actors if k.startswith(("lineup.", "parking."))]
    # (by day first, the details by day too, the night last: the scene lit again after the
    # night took seconds to converge, and the first view after it was dark in its shadows)
    yield from passes(world, actors, by_key, cars, lineup, "day")
    yield from details(world, actors, by_key, cars)
    yield from passes(world, actors, by_key, cars, lineup, "night")
    night(False, world)
    set_hidden(actors, set(actors))


def hero_of(by_key, car):
    """The placement to look at a car in: its own (`hero.<car>`, the line-up's), else the
    first that places it (its first vehicle of that model)."""
    r = by_key.get(f"hero.{car}")
    if r is None:
        r = next((x for k, x in sorted(by_key.items()) if car in x["models"]), None)
    return r


def passes(world, actors, by_key, cars, lineup, when):
    if True:
        night(when == "night", world)
        yield from wait(3.0 if when == "night" else 1.0)
        if lineup:
            # (the check's own line-up: docs/progress/AG18/unreal)
            set_hidden(actors, set(lineup))
            yield from shot(f"lineup_{when}", ue(0, -24, 7), ue(0, 12, 0.5), 50.0)
            yield from shot(f"lineup_high_{when}", ue(-30, -26, 22), ue(0, 12, 0), 45.0)
        set_hidden(actors, {"parking.row"})
        if "parking.row" in by_key:
            r = by_key["parking.row"]
            c = r["pivot"]
            yield from shot(f"parking_{when}", ue(c[0] + 6.8, c[1] - 13.0, 3.5),
                            ue(c[0] + 6.8, c[1], 0.6), 50.0)
        for car, rec in sorted(cars.items()):
            r = hero_of(by_key, car)
            if r is None:
                continue
            set_hidden(actors, {r["key"]})
            xf = r["models"][car]["xforms"][0]
            cam = hero_camera(rec, r["pivot"], xf)
            if cam:
                yield from shot(f"hero_{car}_{when}", cam[0], cam[1], cam[2], 1600)


def details(world, actors, by_key, cars):
    # LODs forced in turn: the pack's LOD views (from opaque_from_lod the glass dark)
    for car in JOB.get("lod_cars") or []:
        r = hero_of(by_key, car)
        if r is None:
            continue
        a = actors[r["key"]]
        set_hidden(actors, {r["key"]})
        xf = r["models"][car]["xforms"][0]
        cam = hero_camera(cars[car], r["pivot"], xf)
        for k in range(len(cars[car]["lods"])):
            for c in components(a).values():
                c.set_forced_lod_model(k + 1)
            yield from wait(0.5)
            yield from shot(f"lod{k}_{car}", cam[0], cam[1], cam[2], 1280)
        for c in components(a).values():
            c.set_forced_lod_model(0)
    # the wheels: one spun about its axle and one steered, in place
    car = JOB.get("wheel_car")
    r = hero_of(by_key, car) if car else None
    if r is not None:
        a = actors[r["key"]]
        set_hidden(actors, {r["key"], f"steer.{car}"})
        comps = components(a)
        rec = cars[car]
        xf = r["models"][car]["xforms"][0]
        fl = next(p for p in rec["parts"] if p["name"] == "wheel_fl")
        eye = ue(*car_frame(r["pivot"], xf, (fl["pivot"][0], fl["pivot"][1] + 2.6,
                                             fl["pivot"][2] + 0.3)))
        tgt = ue(*car_frame(r["pivot"], xf, fl["pivot"]))
        yield from shot(f"wheel_rest_{car}", eye, tgt, 40.0, 1280)
        spun = []
        for part in ("wheel_fl", "brake_fl"):
            c = comps.get((car, part))
            if c is None:
                continue
            t = c.get_instance_transform(0, False)
            rot = t.rotation.rotator()
            # spin about local y (Unreal's pitch), steer about local z (yaw)
            nr = unreal.Rotator(roll=rot.roll, pitch=rot.pitch + (40.0 if part.startswith(
                "wheel") else 0.0), yaw=rot.yaw - 25.0)
            c.update_instance_transform(0, unreal.Transform(t.translation, nr, t.scale3d),
                                        False, True, True)
            after = c.get_instance_transform(0, False)
            spun.append({"part": part, "before": [round(rot.pitch, 2), round(rot.yaw, 2)],
                         "after": [round(after.rotation.rotator().pitch, 2),
                                   round(after.rotation.rotator().yaw, 2)],
                         "moved_cm": round((after.translation - t.translation).length(), 3)})
        RES["checks"]["wheels"] = {"ok": all(s["moved_cm"] < 0.01 for s in spun),
                                   "turned": spun}
        yield from wait(0.5)
        yield from shot(f"wheel_spun_steered_{car}", eye, tgt, 40.0, 1280)
        s = by_key.get(f"steer.{car}")
        if s is not None:
            set_hidden(actors, {s["key"]})
            p0 = s["pivot"]
            yield from shot(f"steer_{car}", ue(p0[0] + 7, p0[1] + 1.5, 4.0),
                            ue(p0[0] + 1.0, p0[1], 0.3), 45.0, 1280)
    # the hulls in place of a car's body
    car = JOB.get("hull_car")
    r = hero_of(by_key, car) if car else None
    if r is not None:
        a = actors[r["key"]]
        set_hidden(actors, {r["key"]})
        xf = r["models"][car]["xforms"][0]
        cam = hero_camera(cars[car], r["pivot"], xf)
        yield from shot(f"hulls_car_{car}", cam[0], cam[1], cam[2], 1280)
        a.set_is_temporarily_hidden_in_editor(True)
        h = hull_actor(cars[car], r["pivot"], xf)
        yield from wait(1.0)
        yield from shot(f"hulls_{car}", cam[0], cam[1], cam[2], 1280)
        unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(h)
    set_hidden(actors, set(actors))


def run():
    unreal.SystemLibrary.execute_console_command(None, "Slate.bAllowThrottling 0")
    man = json.load(open(JOB["manifest"], encoding="utf-8"))
    if not man.get("vehicles"):
        raise RuntimeError("the manifest has no vehicles")
    # (the hero cameras of the packs, read here: the manifest keeps what the importer needs)
    for car, rec in man["vehicles"]["cars"].items():
        try:
            pk = json.load(open(os.path.join(rec["dir"], "pack.json"), encoding="utf-8"))
            rec["hero_camera"] = (pk.get("cameras") or {}).get("hero")
        except OSError:
            pass
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    path = f"{man['content_root']}/Maps/{man['folder']}"
    if not les.load_level(path):
        raise RuntimeError(f"cannot load {path}")
    yield from wait(2.0)
    WPL = unreal.WorldPartitionBlueprintLibrary
    WPL.load_actors([d.guid for d in WPL.get_actor_descs()])
    yield from wait(3.0)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    actors = vehicle_actors(world, man["slug"])
    RES["actors"] = len(actors)
    check_meshes(man)
    check_placements(man, actors)
    check_collision(world, man, actors)
    if JOB.get("shots"):
        os.makedirs(JOB["shots"], exist_ok=True)
        yield from views(world, man, actors)
    RES["ok"] = all(c.get("ok") for c in RES["checks"].values())


GEN = run()
HANDLE = None
BUSY = [False]


def finish():
    RES["total_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(RES, f, indent=1, default=str)
    print("CITYGEN_UE_DONE " + json.dumps({"ok": RES["ok"], "total_s": RES["total_s"]}))
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
    except Exception:
        RES["error"] = traceback.format_exc()
        unreal.log_error(RES["error"])
        finish()
    finally:
        BUSY[0] = False


HANDLE = unreal.register_slate_post_tick_callback(tick)
