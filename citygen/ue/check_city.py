"""citygen M15 check, run inside the Unreal 5.8 editor (stdlib and the `unreal` module only):

    UnrealEditor PROJECT.uproject "-ExecCmds=py citygen/ue/check_city.py" -unattended
        -RenderOffscreen

with $CITYGEN_UE_JOB naming a job file ({"manifest", "build_dir", "result", "shots",
"width"}) that `citygen unreal --check` writes. On the imported level (citygen/ue/
import_city.py) it:

1. with `shots`, renders views of the city in the editor world (all actors loaded): the
   isometric view from the blockout's iso direction and its street views;
2. plays the level in the editor with the project's own game mode and pawn (whatever the
   level's Play is set to, `--play`) and checks:
   - streaming: the World Partition cells around the player load, those far away do not,
     and after a teleport across the city the new neighborhood loads;
   - collision: line traces down onto the ground, streets and sidewalks around several
     spots of the city, down onto building roofs and across onto their facades;
   - walking: the player walked along a sidewalk of the walkway graph from the player start,
     on the ground all the way;
3. plays it again with the fly pawn's game mode: its speed in a straight flight through the
   buildings in its way, the city streamed in where it ends, and with `shots` two views from
   it (what streaming has loaded around it).

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
MAX_GRADE = 0.3     # steepest leg the walk takes (a road's is at most 12%)
MAX_STEP_M = 0.6    # highest step where two walkways join
FLY_MODE = "/Game/CityGen/Core/GM_CityGenFly"     # the importer's (import_city.FLY_MODE)
FLY_S = 8.0         # the flight's straight run
FLY_Z_M = 40.0      # its height over the player start: through the buildings in its way
TRACE_RETRY_S = 30.0  # how long a trace down that missed is tried again after settling


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

def sidewalk_path(build, start, length_m, clear=None, tries=8):
    """A walk of `length_m` from the sidewalk point nearest `start` (citygen meters): along
    that sidewalk, then on into its neighbors, preferring sidewalks; where it cannot go on
    that far, from the next sidewalk near the start, the longest of `tries` kept (M13: on a
    slope a junction's corners can be under the hill). `clear(line)` rejects a walkway (one
    with no head room); the walkways it rejected are counted in `skipped`."""
    g = json.load(open(os.path.join(build, "unreal", "graphs.json"),
                       encoding="utf-8"))["walkways"]
    ps, pts = g["point_start"], g["points"]
    skipped, known = set(), {}

    def line(i):
        return [(pts[3 * k], pts[3 * k + 1], pts[3 * k + 2]) for k in range(ps[i], ps[i + 1])]

    def usable(i):
        if i not in known:
            known[i] = clear is None or clear(line(i))
            if not known[i]:
                skipped.add(i)
        return known[i]

    near = []
    for i, kind in enumerate(g["kinds"]):
        if kind != "sidewalk":
            continue
        d, k = min(((p[0] - start[0]) ** 2 + (p[1] - start[1]) ** 2, k)
                   for k, p in enumerate(line(i)))
        near.append((d, i, k))

    def walk_from(i, k):
        return _walk_on(g, line, usable, skipped, i, k, length_m)

    best, n = ([], 0.0), 0
    for _, i, k in sorted(near)[:40]:
        if not usable(i):
            continue
        path, total = walk_from(i, k)
        if total > best[1]:
            best = (path, total)
        n += 1
        if total >= length_m or n >= tries:
            break
    return best[0], len(skipped)


def _walk_on(g, line, usable, skipped, i, k, length_m):
    """sidewalk_path's walk from point k of walkway i: (path, length)."""
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
            if j in seen or g["kinds"][j] == "elevator":    # (M14: a lift is not walked)
                continue
            ln = line(j)
            if not ln or not usable(j):
                continue
            if math.dist(ln[0][:2], path[-1][:2]) > math.dist(ln[-1][:2], path[-1][:2]):
                ln = ln[::-1]
            if abs(ln[0][2] - path[-1][2]) > MAX_STEP_M:
                # (a joint the graph gives two heights: M13's crosswalk ends can keep the
                # height of the slope beside their curb)
                skipped.add(j)
                continue
            nxt = (j, ln)
            break
        if nxt is None:
            break
        cur, ln = nxt
        seen.add(cur)
        for p in ln:
            total += math.dist(path[-1][:2], p[:2])
            path.append(p)
    return path, total


def walkable(ln):
    """No leg of 2 m or more steeper than MAX_GRADE and no shorter one rising more than
    MAX_STEP_M: a sidewalk or crosswalk follows its road (on a terrain city a crosswalk's end
    can keep the height of the cut slope beside its curb, which no one walks)."""
    for a, b in zip(ln, ln[1:]):
        d, dz = math.dist(a[:2], b[:2]), abs(b[2] - a[2])
        if (d >= 2.0 and dz > MAX_GRADE * d) or (d < 2.0 and dz > MAX_STEP_M):
            return False
    return True


def above_ground(world, ignore, step_m=5.0):
    """A test for a walkway: the terrain's surface is not over it, every `step_m` along it
    (M13: on a slope the ground mesh can stand over a junction's corners, where a walkway
    ends under the hill)."""
    def clear(ln):
        for a, b in zip(ln, ln[1:]):
            n = max(1, int(math.dist(a[:2], b[:2]) // step_m))
            for s in range(n + 1):
                f = s / n
                x, y, z = (a[k] + (b[k] - a[k]) * f for k in range(3))
                h = trace(world, ue(x, y, z + 12.0), ue(x, y, z - 1.0), ignore)
                if h is not None and tag(h["actor"], "cg.category") == "ground" and \
                        h["point"].z > (z + 0.6) * 100.0:
                    return False
        return True
    return clear


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
    # the walk with the project's own game mode and pawn, whatever the level's Play is (its
    # game mode override, `--play`), then a flight with the fly pawn; the level is not saved
    own = game_mode(None)
    log("play in editor: walking")
    world, pawn = yield from begin_play(les)
    RES["pawn"] = pawn.get_class().get_name()
    yield from streaming(world, pawn, man, slug)
    yield from collision(world, pawn, man, slug)
    yield from walk(world, pawn, man)
    yield from cheats(world, pawn)
    les.editor_request_end_play()
    yield from wait(2.0)
    if unreal.EditorAssetLibrary.does_asset_exist(FLY_MODE):
        game_mode(FLY_MODE)
        log("play in editor: flying")
        world, pawn = yield from begin_play(les)
        yield from fly(world, pawn, man, slug)
        les.editor_request_end_play()
        yield from wait(2.0)
    else:
        RES["checks"]["fly"] = {"ok": False,
                                "error": f"no {FLY_MODE} (import the city again)"}
    game_mode(own)
    RES["ok"] = all(c.get("ok") for c in RES["checks"].values())


def game_mode(mode):
    """Set the level's game mode override (in memory) to `mode`: a Blueprint's path, a class,
    or None for the project's own; returns the one it had."""
    ws = ed().get_editor_world().get_world_settings()
    old = ws.get_editor_property("default_game_mode")
    if isinstance(mode, str):
        bp = unreal.load_asset(mode) if unreal.EditorAssetLibrary.does_asset_exist(mode) \
            else None
        if bp is None:
            raise RuntimeError(f"{mode}: no such game mode (import the city again)")
        mode = unreal.BlueprintEditorLibrary.generated_class(bp)
    ws.set_editor_property("default_game_mode", mode)
    return old


def begin_play(les):
    """Play in the editor; the play world and the player's pawn, once it has one."""
    les.editor_request_begin_play()
    world = None
    t = time.time()
    while world is None or unreal.GameplayStatics.get_player_pawn(world, 0) is None:
        if time.time() - t > 120:
            raise RuntimeError("play-in-editor did not start")
        yield
        world = ed().get_game_world()
    return world, unreal.GameplayStatics.get_player_pawn(world, 0)


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
    # the blockout objects, the instance actors, the player start and the three lights (with
    # stage 2: the manifest counts its actors over the blockout's)
    total = man["counts"].get("actors") or \
        man["counts"]["objects"] + man["counts"]["instance_actors"] + 4
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
    # (read before the teleport: actors the start no longer needs stream out after it)
    stage2_start = sum(1 for a in at_start if "cg.stage=2" in tags_of(a))
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
        "stage2_at_start": stage2_start,
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
    city's bounds do not count), and one on each deck (M14), down onto roofs and across
    onto facades."""
    sx, sy, sz = man["player_start"]["position"]
    spots = [(sx, sy)]

    def mid(t):
        b = t["bounds"]
        return (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0

    for t in sorted(man["tiles"], key=lambda t: (-len(t["objects"]), t["name"])):
        if len(spots) < 3 and all(math.dist(mid(t), s) >= 300.0 for s in spots):
            spots.append(mid(t))
    # M14: and the middle of each deck's busiest slab tile, so traces land on the deck
    tile_of = {o["key"]: t for t in man["tiles"] for o in t["objects"]}
    for dk in man.get("decks", []):
        ts = sorted((tile_of[k] for k in dk["keys"] if k in tile_of),
                    key=lambda t: (-len(t["objects"]), t["name"]))
        if ts and mid(ts[0]) not in spots:
            spots.append(mid(ts[0]))
    bx = man["bounds"]
    roof_at = {o["key"]: o.get("roof") for t in man["tiles"] for o in t["objects"]}
    down = {"traces": 0, "hits": 0, "by_category": {}, "late": 0}
    roofs = {"tried": 0, "hit": 0}
    facades = {"tried": 0, "hit": 0}
    for x0, y0 in spots:
        teleport(pawn, x0, y0, 300.0)
        yield from wait(0.5)
        yield from settle(world, slug, at=ue(x0, y0, 0.0))
        todo = []
        for i in range(-6, 7):
            for j in range(-6, 7):
                x, y = x0 + 16.0 * i, y0 + 16.0 * j
                if not (bx[0] < x < bx[2] and bx[1] < y < bx[3]):
                    continue
                down["traces"] += 1
                todo.append((x, y))
        # a cell reported streamed in still registers its components over a few frames (with
        # stage 2's props, twice the actors per cell): a trace that misses is tried again for
        # up to TRACE_RETRY_S, and the hits only after the first try are counted as late
        t, first = time.time(), True
        while todo and (first or time.time() - t < TRACE_RETRY_S):
            if not first:
                yield from wait(0.5)
            left = []
            for x, y in todo:
                h = trace(world, ue(x, y, 600.0), ue(x, y, -3.0), [pawn])
                if h is None:
                    left.append((x, y))
                    continue
                down["hits"] += 1
                down["late"] += 0 if first else 1
                c = tag(h["actor"], "cg.category") or h["actor"].get_class().get_name()
                down["by_category"][c] = down["by_category"].get(c, 0) + 1
            todo, first = left, False
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
            # across onto a facade, from 40 m out on the side nearest the start, 2 m over the
            # actor's bottom, else 2 m over what a trace down finds there, under the roof (M13:
            # on a slope the actor's bottom, a plinth's foot, can lie deep under the ground the
            # trace starts from, and a house downhill can stand lower than that ground; on flat
            # ground the trace down can end on a roof or a deck over the street)
            d = unreal.Vector(o.x - here.x, o.y - here.y, 0.0)
            ln = math.hypot(d.x, d.y) or 1.0
            sx_ = o.x - d.x / ln * (max(e.x, e.y) + 4000.0)
            sy_ = o.y - d.y / ln * (max(e.x, e.y) + 4000.0)
            zs = [o.z - e.z + 200.0]
            g = trace(world, unreal.Vector(sx_, sy_, top + 500.0),
                      unreal.Vector(sx_, sy_, o.z - e.z - 100.0), [pawn])
            if g is not None and g["point"].z > o.z - e.z:
                zs.append(g["point"].z + 200.0)
            facades["tried"] += 1
            for z in zs:
                z = min(z, top - 100.0)
                if trace(world, unreal.Vector(sx_, sy_, z), unreal.Vector(o.x, o.y, z),
                         [pawn]) is not None:
                    facades["hit"] += 1
                    break
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
        (f"; {down['late']} after a wait" if down["late"] else "") +
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


def path_z(path, k, loc):
    """The height of the path (Unreal cm) at the player's place along its leg to point k."""
    a, b = path[k - 1], path[k]
    px, py = loc.x / 100.0, -loc.y / 100.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    f = min(1.0, max(0.0, ((px - a[0]) * dx + (py - a[1]) * dy) / n)) if n > 0 else 0.0
    return (a[2] + f * (b[2] - a[2])) * 100.0


def walk(world, pawn, man):
    """The player along a sidewalk from the start: movement input toward each next point of
    the path every frame, on the ground all the way. The path keeps to walkways with head
    room (not an at-grade sidewalk under a ramp's deck, see the M15 README) that a player can
    walk (`walkable`, steps at the joints) and the terrain does not cover. Where something
    stops the player (a bench, a planter), it steps aside, as a player would, and the blocker
    is noted."""
    sx, sy, sz = man["player_start"]["position"]
    room, ground = head_room(world, [pawn]), above_ground(world, [pawn])
    path, skipped = sidewalk_path(JOB["build_dir"], (sx, sy), WALK_M,
                                  lambda ln: walkable(ln) and ground(ln) and room(ln))
    if len(path) < 2:
        RES["checks"]["walk"] = {"ok": False, "error": "no sidewalk near the start"}
        return
    teleport(pawn, path[0][0], path[0][1], path[0][2] + 1.2)
    yield from wait(1.5)
    mc = pawn.get_movement_component()
    start = pawn.get_actor_location()
    k, t, on_ground, frames, low = 1, time.time(), 0, 0, 1e9
    lift0 = start.z - path[0][2] * 100.0      # the player's height over the path at the start
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
        # how far the player is over the path where it is (M13: the path climbs and falls
        # with the ground)
        low = min(low, loc.z - path_z(path, k, loc))
        travelled += math.hypot(loc.x - last.x, loc.y - last.y)
        last = loc
        yield
    length = sum(math.dist(path[j][:2], path[j + 1][:2]) for j in range(len(path) - 1))
    reached = k >= len(path)
    share = on_ground / max(frames, 1)
    z_drop = (lift0 - low) / 100.0     # fallen below the path, not walked downhill
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


def cheats(world, pawn):
    """The console's ghost, fly and walk on the walking pawn (the cheat manager's, which
    play-in-editor allows): flying without collision, flying with it, back on its feet."""
    mc = pawn.get_movement_component()
    got = {}
    for cmd in ("ghost", "fly", "walk"):
        unreal.SystemLibrary.execute_console_command(world, cmd)
        yield from wait(0.5)
        mode = str(mc.get_editor_property("movement_mode")) if mc is not None else ""
        got[cmd] = {"mode": mode.split("MOVE_")[-1].split(":")[0].lower(),
                    "collision": bool(pawn.get_actor_enable_collision())}
    ok = (got["ghost"]["mode"] == "flying" and not got["ghost"]["collision"]
          and got["fly"]["mode"] == "flying" and got["fly"]["collision"]
          and got["walk"]["mode"] in ("walking", "falling") and got["walk"]["collision"])
    RES["checks"]["cheats"] = {"ok": ok, **got}
    RES["lines"].append("console: " + ", ".join(
        f"{c} {v['mode']}{'' if v['collision'] else ' without collision'}"
        for c, v in got.items()))


def fly(world, pawn, man, slug):
    """The fly pawn: its class and top speed; a straight run of FLY_S seconds at full input
    from FLY_Z_M over the player start toward the city's middle, through whatever stands in
    its way (no collision); the city streamed in where it ends; with `shots`, two views from
    it. The speed is measured on the game's clock (a long frame is clamped there)."""
    RES["fly_pawn"] = pawn.get_class().get_name()
    mc = pawn.get_movement_component()
    speed = mc.get_editor_property("max_speed") / 100.0
    sx, sy, sz = man["player_start"]["position"]
    b = man["bounds"]
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    dx, dy = cx - sx, cy - sy
    n = math.hypot(dx, dy)
    dx, dy = (dx / n, dy / n) if n > 50.0 else (1.0, 0.0)
    teleport(pawn, sx, sy, sz + FLY_Z_M)
    yield from wait(1.0)
    a = pawn.get_actor_location()
    t, g = time.time(), unreal.GameplayStatics.get_time_seconds(world)
    while time.time() - t < FLY_S:
        pawn.add_movement_input(unreal.Vector(dx, -dy, 0.0), 1.0, False)
        yield
    secs = unreal.GameplayStatics.get_time_seconds(world) - g
    e = pawn.get_actor_location()
    dist = math.hypot(e.x - a.x, e.y - a.y) / 100.0
    # what stands in the line it flew (the pawn would have stopped there with collision)
    hit = trace(world, a, e, [pawn])
    through = (tag(hit["actor"], "cg.key") or hit["actor"].get_name()) if hit else None
    ex, ey = e.x / 100.0, -e.y / 100.0
    yield from settle(world, slug, at=ue(ex, ey, 0.0))
    here = city_actors(world, slug)
    tile = f"t{math.floor(ex / man['tile_size_m']):+03d}{math.floor(ey / man['tile_size_m']):+03d}"
    tiles = {tag(x, "cg.tile") for x in here}
    ok = (RES["fly_pawn"].startswith("BP_CityGenFlyPawn") and dist >= 0.8 * speed * secs
          and (tile in tiles or not any(t_["name"] == tile for t_ in man["tiles"])))
    RES["checks"]["fly"] = {"ok": ok, "pawn": RES["fly_pawn"], "speed_m_s": round(speed, 1),
                            "flew_m": round(dist, 1), "seconds": round(secs, 1),
                            "through": through, "loaded_at_end": len(here),
                            "end_tile_loaded": tile in tiles}
    RES["lines"].append(
        f"fly: {RES['fly_pawn']} at {speed:g} m/s flew {dist:.0f} m in {secs:.1f} s"
        + (f" through {through}" if through else "") + f", {len(here)} actors loaded where it "
        "ended")
    if JOB.get("shots"):
        yield from fly_shots(world, pawn, man, slug)


def fly_shots(world, pawn, man, slug):
    """Views from the fly pawn while playing, what the streaming has loaded around it: over
    the city toward its middle, and low over the first street view's street."""
    out = JOB["shots"]
    os.makedirs(out, exist_ok=True)
    b = man["bounds"]
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    d = man["cameras"].get("iso_dir") or [0.28, 0.77, -0.57]
    h = math.hypot(d[0], d[1]) or 1.0
    views = [("fly_over", (cx - d[0] / h * 700.0, cy - d[1] / h * 700.0, 220.0), (cx, cy, 0.0))]
    st = man["cameras"].get("street", [])
    if st:
        ex, ey, ez = st[0]["eye"]
        views.append(("fly_low", (ex, ey, ez + 25.0), tuple(st[0]["target"])))
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    w = int(JOB.get("width") or 3840)
    files = []
    for name, eye, target in views:
        teleport(pawn, *eye)
        pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(ue(*eye), ue(*target)))
        yield from wait(1.0)
        yield from settle(world, slug, at=ue(eye[0], eye[1], 0.0))
        yield from wait(3.0)
        path = os.path.join(out, f"unreal_{name}.png").replace("\\", "/")
        if os.path.exists(path):
            os.remove(path)
        unreal.SystemLibrary.execute_console_command(
            world, f'HighResShot {w}x{w * 9 // 16} filename="{path}"')
        t = time.time()
        while not os.path.exists(path) and time.time() - t < 120:
            yield
        yield from wait(1.0)
        if os.path.exists(path):
            files.append(path)
            log(f"wrote {path}")
    RES["fly_shots"] = files


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
    for v in man["cameras"].get("street", [])[:3] + JOB.get("views", []):
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
