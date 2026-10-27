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

def sidewalk_path(build, start, length_m, clear=None):
    """A walk of `length_m` from the sidewalk point nearest `start` (citygen meters): along
    that sidewalk, then on into its neighbors, preferring sidewalks. `clear(line)` rejects a
    walkway (one with no head room); the walkways it rejected are counted in `skipped`."""
    g = json.load(open(os.path.join(build, "unreal", "graphs.json"),
                       encoding="utf-8"))["walkways"]
    ps, pts = g["point_start"], g["points"]
    skipped = set()

    def line(i):
        return [(pts[3 * k], pts[3 * k + 1], pts[3 * k + 2]) for k in range(ps[i], ps[i + 1])]

    def usable(i):
        if clear is None or clear(line(i)):
            return True
        skipped.add(i)
        return False

    near = []
    for i, kind in enumerate(g["kinds"]):
        if kind != "sidewalk":
            continue
        d, k = min(((p[0] - start[0]) ** 2 + (p[1] - start[1]) ** 2, k)
                   for k, p in enumerate(line(i)))
        near.append((d, i, k))
    best = next((b for b in sorted(near)[:40] if usable(b[1])), None)
    if best is None:
        return [], len(skipped)
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
            if not ln or not usable(j):
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
    return path, len(skipped)


def head_room(world, ignore, step_m=5.0):
    """A test for a walkway: nothing between 0.45 m and 2.3 m above it, every `step_m` along
    it (a trace up and one down, so a deck is found from below and from above)."""
    def clear(ln):
        for a, b in zip(ln, ln[1:]):
            n = max(1, int(math.dist(a[:2], b[:2]) // step_m))
            for s in range(n + 1):
                f = s / n
                x, y = (a[0] + (b[0] - a[0]) * f) * 100.0, -(a[1] + (b[1] - a[1]) * f) * 100.0
                z = (a[2] + (b[2] - a[2]) * f) * 100.0
                lo, hi = unreal.Vector(x, y, z + 45.0), unreal.Vector(x, y, z + 230.0)
                if trace(world, lo, hi, ignore) or trace(world, hi, lo, ignore):
                    return False
        return True
    return clear


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


def streamed(world, at=None, radius_m=150.0):
    """World Partition has finished streaming, within `radius_m` of `at` (an Unreal
    location) when given; None where the query is not available."""
    try:
        wps = next((s for s in unreal.ObjectIterator(unreal.WorldPartitionSubsystem)
                    if s.get_world() == world), None)
        if wps is None:
            if "streamed" not in RES:
                RES["streamed"] = "no WorldPartitionSubsystem in the play world"
                log(RES["streamed"])
            return None
        if at is None:
            return bool(wps.is_all_streaming_completed())
        q = unreal.WorldPartitionStreamingQuerySource()
        q.set_editor_property("location", at)
        q.set_editor_property("radius", radius_m * 100.0)
        q.set_editor_property("spatial_query", True)
        q.set_editor_property("include_any_data_layer", True)
        return bool(wps.is_streaming_completed(
            unreal.WorldPartitionRuntimeCellState.ACTIVATED, [q], False))
    except Exception as e:      # noqa: BLE001 (an engine without the query)
        if "streamed" not in RES:
            RES["streamed"] = str(e)
            log(f"no streaming query: {e}")
        return None


def settle(world, slug, timeout=LOAD_WAIT_S, at=None):
    """Wait until World Partition has finished streaming (around `at` when given) and the
    number of city actors in the game world stops changing."""
    t, last, stable = time.time(), -1, 0
    while time.time() - t < timeout:
        n = len(city_actors(world, slug))
        stable = stable + 1 if n == last else 0
        last = n
        if n > 0 and stable >= 30 and streamed(world, at) is not False:
            break
        yield
    return last


def teleport(pawn, x, y, z):
    pawn.set_actor_location(ue(x, y, z), False, True)


def streaming(world, pawn, man, slug):
    # the blockout objects, the instance actors, the player start and the three lights
    total = man["counts"]["objects"] + man["counts"]["instance_actors"] + 4
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
    yield from settle(world, slug, at=ue(fx, fy, 0.0))
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
    """Traces down on a 16 m grid within 100 m of three spots (the start and the middles of
    the two busiest tiles 300 m or more from it and from each other; traces outside the
    city's bounds do not count), down onto roofs and across onto facades."""
    sx, sy, sz = man["player_start"]["position"]
    spots = [(sx, sy)]

    def mid(t):
        b = t["bounds"]
        return (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0

    for t in sorted(man["tiles"], key=lambda t: (-len(t["objects"]), t["name"])):
        if len(spots) < 3 and all(math.dist(mid(t), s) >= 300.0 for s in spots):
            spots.append(mid(t))
    bx = man["bounds"]
    roof_at = {o["key"]: o.get("roof") for t in man["tiles"] for o in t["objects"]}
    down = {"traces": 0, "hits": 0, "by_category": {}}
    roofs = {"tried": 0, "hit": 0}
    facades = {"tried": 0, "hit": 0}
    for x0, y0 in spots:
        teleport(pawn, x0, y0, 300.0)
        yield from wait(0.5)
        yield from settle(world, slug, at=ue(x0, y0, 0.0))
        for i in range(-6, 7):
            for j in range(-6, 7):
                x, y = x0 + 16.0 * i, y0 + 16.0 * j
                if not (bx[0] < x < bx[2] and bx[1] < y < bx[3]):
                    continue
                h = trace(world, ue(x, y, 600.0), ue(x, y, -3.0), [pawn])
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
            roofs["tried"] += 1
            # stopped on the building or on what stands on it (a green roof, a skybridge),
            # well above the ground: at the manifest's point inside its highest footprint,
            # else at the middle of its bounds or one of the four quarter points
            pts = [(o.x + qx * e.x, o.y + qy * e.y) for qx, qy in
                   ((0.0, 0.0), (-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5))]
            r = roof_at.get(tag(a, "cg.key"))
            if r:
                pts.insert(0, (r[0] * 100.0, -r[1] * 100.0))
            for x, y in pts:
                h = trace(world, unreal.Vector(x, y, top + 500.0),
                          unreal.Vector(x, y, o.z - e.z - 100.0), [pawn])
                if h is not None and h["point"].z > o.z - e.z + 300.0:
                    roofs["hit"] += 1
                    break
            else:
                roofs.setdefault("missed", []).append(tag(a, "cg.key"))
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
            else:
                facades.setdefault("missed", []).append(tag(a, "cg.key"))
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


def blocker(world, pawn, loc, fx, fy):
    """What stands in front of the player: a 25 cm sphere swept 1.2 m forward at four
    heights from above the step height (the capsule's middle is 96 cm up) to the head; its
    category or class."""
    for dz in (-45.0, -15.0, 25.0, 65.0):
        a = unreal.Vector(loc.x, loc.y, loc.z + dz)
        b = unreal.Vector(loc.x + fx * 120.0, loc.y + fy * 120.0, loc.z + dz)
        hit = unreal.SystemLibrary.sphere_trace_single(
            world, a, b, 25.0, VISIBILITY, True, [pawn], unreal.DrawDebugTrace.NONE, True)
        if hit is not None and hit.to_tuple()[0]:
            act = hit.to_tuple()[9]
            return (tag(act, "cg.category") or act.get_class().get_name()) + f"@{dz:+.0f}"
    return "nothing found"


def walk(world, pawn, man):
    """The player along a sidewalk from the start: movement input toward each next point of
    the path every frame, on the ground all the way. The path keeps to walkways with head
    room (not an at-grade sidewalk under a ramp's deck, see the M15 README). Where something
    stops the player (a bench, a planter), it steps aside, as a player would, and the blocker
    is noted."""
    sx, sy, sz = man["player_start"]["position"]
    path, skipped = sidewalk_path(JOB["build_dir"], (sx, sy), WALK_M,
                                  head_room(world, [pawn]))
    if len(path) < 2:
        RES["checks"]["walk"] = {"ok": False, "error": "no sidewalk near the start"}
        return
    teleport(pawn, path[0][0], path[0][1], path[0][2] + 1.2)
    yield from wait(1.5)
    mc = pawn.get_movement_component()
    start = pawn.get_actor_location()
    k, t, on_ground, frames, low = 1, time.time(), 0, 0, 1e9
    travelled, last = 0.0, start
    mark, mark_t, side_until, side, blockers, stops = start, time.time(), 0.0, 1.0, {}, []
    while k < len(path) and time.time() - t < WALK_S:
        loc = pawn.get_actor_location()
        tx, ty = path[k][0] * 100.0, -path[k][1] * 100.0
        dx, dy = tx - loc.x, ty - loc.y
        if math.hypot(dx, dy) < 150.0:
            k += 1
            continue
        n = math.hypot(dx, dy)
        fx, fy = dx / n, dy / n
        now = time.time()
        if now - mark_t > 0.6:
            if math.hypot(loc.x - mark.x, loc.y - mark.y) < 30.0 and now > side_until:
                c = blocker(world, pawn, loc, fx, fy)
                blockers[c] = blockers.get(c, 0) + 1
                if len(stops) < 8:
                    stops.append([round(loc.x / 100.0, 2), round(-loc.y / 100.0, 2),
                                  round(loc.z / 100.0, 2), c])
                side_until, side = now + 0.7, -side
            mark, mark_t = loc, now
        if now < side_until:      # step aside (to the left, then the right), still forward
            fx, fy = 0.4 * fx - side * fy, 0.4 * fy + side * fx
        pawn.add_movement_input(unreal.Vector(fx, fy, 0.0), 1.0, False)
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
                             "seconds": round(time.time() - t, 1), "stopped_by": blockers,
                             "stops": stops, "skipped_low_walkways": skipped}
    stops = (", stepped round " + ", ".join(f"{v} x {k_}" for k_, v in sorted(
        blockers.items()))) if blockers else ""
    RES["lines"].append(f"walk: {travelled / 100.0:.0f} m along a {length:.0f} m sidewalk "
                        f"path in {time.time() - t:.0f} s, {100 * share:.0f}% of frames on "
                        f"the ground, {'reached its end' if reached else 'did not reach its end'}"
                        + stops)


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
    dist = 2.3 * size        # the whole city in a 30 degree field of view
    views = [("iso_city", (cx - d[0] * dist, cy - d[1] * dist, -d[2] * dist), (cx, cy, 0.0),
              30.0)]
    for v in man["cameras"].get("street", [])[:3]:
        views.append((v["name"], tuple(v["eye"]), tuple(v["target"]),
                      2.0 * math.degrees(math.atan(18.0 / v.get("lens_mm", 28)))))
    files = []
    w = int(JOB.get("width") or 3840)
    for name, eye, target, fov in views:
        cam = eas.spawn_actor_from_class(unreal.CameraActor, ue(*eye), transient=True)
        e, tg = ue(*eye), ue(*target)
        rot = unreal.MathLibrary.find_look_at_rotation(e, tg)
        cam.set_actor_rotation(rot, False)
        cam.camera_component.set_editor_property("field_of_view", fov)
        path = os.path.join(out, f"unreal_{name}.png")
        if os.path.exists(path):
            os.remove(path)
        unreal.AutomationLibrary.finish_loading_before_screenshot()   # shaders, streaming
        yield from wait(2.0)
        unreal.AutomationLibrary.take_high_res_screenshot(w, w * 9 // 16, path, cam)
        t = time.time()
        while not os.path.exists(path) and time.time() - t < 300:
            yield
        yield from wait(1.0)
        eas.destroy_actor(cam)
        if os.path.exists(path):
            files.append(path)
            log(f"wrote {path}")
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


BUSY = [False]


def tick(dt):
    if BUSY[0]:     # a screenshot pumps the editor's tick from inside the generator
        return
    BUSY[0] = True
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
    finally:
        BUSY[0] = False


HANDLE = unreal.register_slate_post_tick_callback(tick)
