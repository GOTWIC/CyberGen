"""citygen M15 check, run inside the Unreal 5.8 editor (stdlib and the `unreal` module only):

    UnrealEditor PROJECT.uproject "-ExecCmds=py citygen/ue/check_city.py" -unattended
        -RenderOffscreen

with $CITYGEN_UE_JOB naming a job file ({"manifest", "build_dir", "result", "shots",
"width"}) that `citygen unreal --check` writes. On the imported level (citygen/ue/
import_city.py) it:

1. with `shots`, renders views of the city in the editor world (all actors loaded): the
   isometric view from the blockout's iso direction and its street views;
2. plays the level in the editor (the project's game mode and pawn) and checks:
   - streaming: the World Partition cells around the player load, those far away do not,
     and after a teleport across the city the new neighborhood loads;
   - collision: line traces down onto the ground, streets and sidewalks around several
     spots of the city, down onto building roofs and across onto their facades;
   - walking: the player walked along a sidewalk of the walkway graph from the player start,
     on the ground all the way.

The script runs as a generator on the editor's tick (play-in-editor needs frames), writes
the job's result file and quits the editor.
"""

import json
import math
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
T0 = time.time()
RES = {"ok": False, "lines": [], "checks": {}}
LOAD_WAIT_S = 60.0
WALK_M = 120.0
WALK_S = 60.0


def log(msg):
    unreal.log(f"citygen check: {msg} ({time.time() - T0:.1f} s)")


def ue(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def ed():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def wait(seconds):
    t = time.time()
    while time.time() - t < seconds:
        yield


def tags_of(a):
    return [str(t) for t in a.tags]


def tag(a, key):
    p = key + "="
    return next((t[len(p):] for t in tags_of(a) if t.startswith(p)), "")


def city_actors(world, slug):
    return list(unreal.GameplayStatics.get_all_actors_with_tag(world, f"cg.city={slug}"))


VISIBILITY = getattr(unreal.TraceTypeQuery, "ECC_VISIBILITY", None) or \
    unreal.TraceTypeQuery.TRACE_TYPE_QUERY1


def trace(world, a, b, ignore=()):
    hit = unreal.SystemLibrary.line_trace_single(
        world, a, b, VISIBILITY, True, list(ignore),
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    t = hit.to_tuple()
    if not t[0]:
        return None
    return {"actor": t[9], "point": t[5]}


# --- the walkway graph (the importer's flat graphs) ------------------------------------------

def sidewalk_path(build, start, length_m):
    """A walk of `length_m` from the sidewalk point nearest `start` (citygen meters): along
    that sidewalk, then on into its neighbors, preferring sidewalks."""
    g = json.load(open(os.path.join(build, "unreal", "graphs.json"),
                       encoding="utf-8"))["walkways"]
    ps, pts = g["point_start"], g["points"]

    def line(i):
        return [(pts[3 * k], pts[3 * k + 1], pts[3 * k + 2]) for k in range(ps[i], ps[i + 1])]

    best = None
    for i, kind in enumerate(g["kinds"]):
        if kind != "sidewalk":
            continue
        for k, p in enumerate(line(i)):
            d = (p[0] - start[0]) ** 2 + (p[1] - start[1]) ** 2
            if best is None or d < best[0]:
                best = (d, i, k)
    if best is None:
        return []
    _, i, k = best
    path = line(i)[k:]
    if len(path) < 2:
        path = line(i)[::-1][len(line(i)) - 1 - k:]
    seen = {i}
    total = sum(math.dist(path[j][:2], path[j + 1][:2]) for j in range(len(path) - 1))
    cur = i
    while total < length_m:
        links = g["links"][g["link_start"][cur]:g["link_start"][cur + 1]]
        nxt = None
        for j in sorted(links, key=lambda j: (g["kinds"][j] != "sidewalk", j)):
            if j in seen:
                continue
            ln = line(j)
            if not ln:
                continue
            if math.dist(ln[0][:2], path[-1][:2]) <= math.dist(ln[-1][:2], path[-1][:2]):
                nxt = (j, ln)
            else:
                nxt = (j, ln[::-1])
            break
        if nxt is None:
            break
        cur, ln = nxt
        seen.add(cur)
        for p in ln:
            total += math.dist(path[-1][:2], p[:2])
            path.append(p)
    return path


# --- the check ----------------------------------------------------------------------------

def run():
    # Slate throttles the play world's tick while the editor is not the foreground app
    unreal.SystemLibrary.execute_console_command(None, "Slate.bAllowThrottling 0")
    man = json.load(open(JOB["manifest"], encoding="utf-8"))
    slug = man["slug"]
    RES["city"] = man["city"]
    path = f"{man['content_root']}/Maps/{man['folder']}"
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.load_level(path):
        raise RuntimeError(f"cannot load {path} (import the city first)")
    yield from wait(2.0)
    if JOB.get("shots"):
        yield from shots(man)
    log("play in editor")
    les.editor_request_begin_play()
    world = None
    t = time.time()
    while world is None or unreal.GameplayStatics.get_player_pawn(world, 0) is None:
        if time.time() - t > 120:
            raise RuntimeError("play-in-editor did not start")
        yield
        world = ed().get_game_world()
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    RES["pawn"] = pawn.get_class().get_name()
    yield from streaming(world, pawn, man, slug)
    yield from collision(world, pawn, man, slug)
    yield from walk(world, pawn, man)
    les.editor_request_end_play()
    yield from wait(2.0)
    RES["ok"] = all(c.get("ok") for c in RES["checks"].values())


def settle(world, slug, timeout=LOAD_WAIT_S):
    """Wait until the number of city actors in the game world stops changing."""
    t, last, stable = time.time(), -1, 0
    while time.time() - t < timeout:
        n = len(city_actors(world, slug))
        stable = stable + 1 if n == last else 0
        last = n
        if n > 0 and stable >= 30:
            break
        yield
    return last


def teleport(pawn, x, y, z):
    pawn.set_actor_location(ue(x, y, z), False, True)


def streaming(world, pawn, man, slug):
    total = man["counts"]["objects"] + man["counts"]["instance_actors"] + 1
    yield from settle(world, slug)
    at_start = city_actors(world, slug)
    # the busiest tile at least 600 m from the start
    sx, sy, _ = man["player_start"]["position"]

    def mid(t):
        b = t["bounds"]
        return (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0

    far = [t for t in man["tiles"] if math.dist(mid(t), (sx, sy)) >= 600.0] or man["tiles"]
    fx, fy = mid(max(far, key=lambda t: (len(t["objects"]), t["name"])))
    near_start = {tag(a, "cg.key") for a in at_start}
    teleport(pawn, fx, fy, 400.0)       # high up: nothing to stand on until it loads
    yield from wait(1.0)
    yield from settle(world, slug)
    at_far = city_actors(world, slug)
    near_far = {tag(a, "cg.key") for a in at_far}
    tiles = {tag(a, "cg.tile") for a in at_far} - {""}
    far_tile = f"t{math.floor(fx / man['tile_size_m']):+03d}{math.floor(fy / man['tile_size_m']):+03d}"
    ok = (0 < len(at_start) < total and 0 < len(at_far) < total
          and near_far != near_start and (far_tile in tiles or not any(
              t["name"] == far_tile for t in man["tiles"])))
    RES["checks"]["streaming"] = {
        "ok": ok, "actors": total, "loaded_at_start": len(at_start),
        "loaded_far": len(at_far), "only_far": len(near_far - near_start),
        "far_spot_m": [round(fx, 1), round(fy, 1)], "far_tile_loaded": far_tile in tiles}
    RES["lines"].append(f"streaming: {len(at_start)} of {total} actors loaded at the start, "
                        f"{len(at_far)} after a teleport to ({fx:.0f}, {fy:.0f}) "
                        f"({len(near_far - near_start)} new)")
    teleport(pawn, sx, sy, man["player_start"]["position"][2])
    yield from wait(1.0)
    yield from settle(world, slug)


def collision(world, pawn, man, slug):
    """Traces down on a 16 m grid within 100 m of three spots (the start, the middle of the
    city's tiles and one more), down onto roofs and across onto facades."""
    sx, sy, sz = man["player_start"]["position"]
    spots = [(sx, sy)]
    tiles = man["tiles"]
    mid = tiles[len(tiles) // 2]["bounds"]
    spots.append(((mid[0] + mid[2]) / 2, (mid[1] + mid[3]) / 2))
    q = tiles[len(tiles) // 4]["bounds"]
    spots.append(((q[0] + q[2]) / 2, (q[1] + q[3]) / 2))
    down = {"traces": 0, "hits": 0, "by_category": {}}
    roofs = {"tried": 0, "hit": 0}
    facades = {"tried": 0, "hit": 0}
    for x0, y0 in spots:
        teleport(pawn, x0, y0, 300.0)
        yield from wait(0.5)
        yield from settle(world, slug)
        for i in range(-6, 7):
            for j in range(-6, 7):
                x, y = x0 + 16.0 * i, y0 + 16.0 * j
                h = trace(world, ue(x, y, 600.0), ue(x, y, -60.0), [pawn])
                down["traces"] += 1
                if h is not None:
                    down["hits"] += 1
                    c = tag(h["actor"], "cg.category") or h["actor"].get_class().get_name()
                    down["by_category"][c] = down["by_category"].get(c, 0) + 1
        here = ue(x0, y0, 0.0)
        blds = [a for a in city_actors(world, slug) if tag(a, "cg.category") == "building"]
        blds.sort(key=lambda a: (a.get_actor_bounds(False)[0] - here).length())
        for a in blds[:12]:
            o, e = a.get_actor_bounds(False)
            top = o.z + e.z
            h = trace(world, unreal.Vector(o.x, o.y, top + 500.0),
                      unreal.Vector(o.x, o.y, o.z - e.z - 100.0), [pawn])
            roofs["tried"] += 1
            # stopped on the building or on what stands on it (a green roof, a skybridge),
            # well above the ground
            if h is not None and h["point"].z > o.z - e.z + 300.0:
                roofs["hit"] += 1
            # across onto a facade at 2 m, from 40 m out on the side nearest the start
            z = o.z - e.z + 200.0
            d = unreal.Vector(o.x - here.x, o.y - here.y, 0.0)
            ln = math.hypot(d.x, d.y) or 1.0
            start = unreal.Vector(o.x - d.x / ln * (max(e.x, e.y) + 4000.0),
                                  o.y - d.y / ln * (max(e.x, e.y) + 4000.0), z)
            h = trace(world, start, unreal.Vector(o.x, o.y, z), [pawn])
            facades["tried"] += 1
            if h is not None:
                facades["hit"] += 1
    land = down["hits"] / max(down["traces"], 1)
    ok = land >= 0.95 and roofs["hit"] >= 0.9 * roofs["tried"] and \
        facades["hit"] >= 0.9 * facades["tried"] and roofs["tried"] > 0
    RES["checks"]["collision"] = {"ok": ok, "down": down, "roofs": roofs,
                                  "facades": facades, "spots": spots}
    RES["lines"].append(
        f"collision: {down['hits']} of {down['traces']} traces down hit (" +
        ", ".join(f"{k} {v}" for k, v in sorted(down["by_category"].items(),
                                                key=lambda kv: -kv[1])[:6]) +
        f"), {roofs['hit']} of {roofs['tried']} roofs, {facades['hit']} of "
        f"{facades['tried']} facades")
    teleport(pawn, sx, sy, sz)
    yield from wait(1.0)
    yield from settle(world, slug)


def walk(world, pawn, man):
    """The player along a sidewalk from the start: movement input toward each next point of
    the path every frame, on the ground all the way."""
    sx, sy, sz = man["player_start"]["position"]
    path = sidewalk_path(JOB["build_dir"], (sx, sy), WALK_M)
    if len(path) < 2:
        RES["checks"]["walk"] = {"ok": False, "error": "no sidewalk near the start"}
        return
    teleport(pawn, path[0][0], path[0][1], path[0][2] + 1.2)
    yield from wait(1.5)
    mc = pawn.get_movement_component()
    start = pawn.get_actor_location()
    k, t, on_ground, frames, low = 1, time.time(), 0, 0, 1e9
    travelled, last = 0.0, start
    while k < len(path) and time.time() - t < WALK_S:
        loc = pawn.get_actor_location()
        tx, ty = path[k][0] * 100.0, -path[k][1] * 100.0
        dx, dy = tx - loc.x, ty - loc.y
        if math.hypot(dx, dy) < 150.0:
            k += 1
            continue
        n = math.hypot(dx, dy)
        pawn.add_movement_input(unreal.Vector(dx / n, dy / n, 0.0), 1.0, False)
        frames += 1
        if mc is not None and mc.is_moving_on_ground():
            on_ground += 1
        low = min(low, loc.z)
        travelled += math.hypot(loc.x - last.x, loc.y - last.y)
        last = loc
        yield
    length = sum(math.dist(path[j][:2], path[j + 1][:2]) for j in range(len(path) - 1))
    reached = k >= len(path)
    share = on_ground / max(frames, 1)
    z_drop = (start.z - low) / 100.0
    ok = (reached or travelled / 100.0 >= 0.9 * length) and share >= 0.9 and z_drop < 3.0
    RES["checks"]["walk"] = {"ok": ok, "path_m": round(length, 1), "points": len(path),
                             "reached": reached, "travelled_m": round(travelled / 100.0, 1),
                             "on_ground": round(share, 3), "max_drop_m": round(z_drop, 2),
                             "seconds": round(time.time() - t, 1)}
    RES["lines"].append(f"walk: {travelled / 100.0:.0f} m along a {length:.0f} m sidewalk "
                        f"path in {time.time() - t:.0f} s, {100 * share:.0f}% of frames on "
                        f"the ground, {'reached its end' if reached else 'did not reach its end'}")


# --- shots ------------------------------------------------------------------------------------

def shots(man):
    """Renders of the city in the editor world, every actor loaded: the isometric view and
    the blockout's street views."""
    out = JOB["shots"]
    os.makedirs(out, exist_ok=True)
    WPL = unreal.WorldPartitionBlueprintLibrary
    guids = [d.guid for d in WPL.get_actor_descs()]
    WPL.load_actors(guids)
    log(f"loaded {len(guids)} actors for the shots")
    yield from wait(5.0)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    b = man["bounds"]
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    size = max(b[2] - b[0], b[3] - b[1])
    d = man["cameras"].get("iso_dir") or [0.28, 0.77, -0.57]
    dist = 1.25 * size
    views = [("iso_city", (cx - d[0] * dist, cy - d[1] * dist, -d[2] * dist), (cx, cy, 0.0),
              30.0)]
    for v in man["cameras"].get("street", [])[:3]:
        views.append((v["name"], tuple(v["eye"]), tuple(v["target"]),
                      2.0 * math.degrees(math.atan(18.0 / v.get("lens_mm", 28)))))
    sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 50000))
    sun.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=-40.0, yaw=-60.0), False)
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 50000))
    atm = eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    files = []
    w = int(JOB.get("width") or 3840)
    for name, eye, target, fov in views:
        cam = eas.spawn_actor_from_class(unreal.CameraActor, ue(*eye))
        e, tg = ue(*eye), ue(*target)
        rot = unreal.MathLibrary.find_look_at_rotation(e, tg)
        cam.set_actor_rotation(rot, False)
        cam.camera_component.set_editor_property("field_of_view", fov)
        path = os.path.join(out, f"unreal_{name}.png")
        if os.path.exists(path):
            os.remove(path)
        unreal.AutomationLibrary.take_high_res_screenshot(w, w * 9 // 16, path, cam)
        t = time.time()
        while not os.path.exists(path) and time.time() - t < 300:
            yield
        yield from wait(1.0)
        eas.destroy_actor(cam)
        if os.path.exists(path):
            files.append(path)
            log(f"wrote {path}")
    for a in (sun, sky, atm):
        eas.destroy_actor(a)
    RES["shots"] = files


# --- the tick loop ----------------------------------------------------------------------------

GEN = run()
HANDLE = None


def finish():
    RES["total_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(RES, f, indent=1, default=str)
    print("CITYGEN_UE_DONE " + json.dumps({"ok": RES["ok"], "total_s": RES["total_s"]}))
    unreal.unregister_slate_post_tick_callback(HANDLE)
    unreal.SystemLibrary.quit_editor()


def tick(dt):
    try:
        next(GEN)
    except StopIteration:
        finish()
    except Exception:
        RES["error"] = traceback.format_exc()
        unreal.log_error(RES["error"])
        try:
            unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
        except Exception:
            pass
        finish()


HANDLE = unreal.register_slate_post_tick_callback(tick)
