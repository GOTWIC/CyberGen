"""citygen M15 check, run inside the Unreal 5.8 editor (stdlib and the `unreal` module only):

    UnrealEditor PROJECT.uproject "-ExecCmds=py citygen/ue/check_city.py" -unattended
        -RenderOffscreen

with $CITYGEN_UE_JOB naming a job file ({"manifest", "build_dir", "result", "shots",
"width"}) that `citygen unreal --check` writes. On the imported level (citygen/ue/
import_city.py) it:

1. with `shots`, renders views of the city in the editor world (all actors loaded, or for
   a city with more meshes than `SHOT_MESHES`, those nearest its middle): the isometric
   view from the blockout's iso direction and its street views;
2. plays the level in the editor with the project's own game mode and pawn (whatever the
   level's Play is set to, `--play`) and checks:
   - streaming: the World Partition cells around the player load, those far away do not,
     and after a teleport across the city the new neighborhood loads;
   - collision: line traces down onto the ground, streets and sidewalks around several
     spots of the city, down onto building roofs and across onto their facades;
   - walking: the player walked along a sidewalk of the walkway graph from the player start,
     on the ground all the way;
   - the play features (when the import made them): the overlay, the map and the developer
     menu, night with lamps lit, the free camera and back, a teleport across the city that
     lands on the ground; with `shots` the minimap, map, menu and night as the play window
     shows them;
3. plays it again with the fly pawn's game mode: its speed in a straight flight through the
   buildings in its way, the city streamed in where it ends, and with `shots` two views from
   it (what streaming has loaded around it).

The script runs as a generator on the editor's tick (play-in-editor needs frames), writes
the job's result file and quits the editor.
"""

import json
import math
import os
import re
import time
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
T0 = time.time()
RES = {"ok": False, "lines": [], "checks": {}}
LOAD_WAIT_S = 180.0  # the longest wait for a spot to stream in
COUNT_EVERY_S = 2.0  # how often that wait lists the city's actors in the play world
WALK_M = 120.0
WALK_S = 60.0
MAX_GRADE = 0.3     # steepest leg the walk takes (a road's is at most 12%)
MAX_STEP_M = 0.6    # highest step where two walkways join
FLY_MODE = "/Game/CityGen/Core/GM_CityGenFly"     # the importer's (import_city.FLY_MODE)
WALK_MODE = "/Game/CityGen/Core/GM_CityGenWalk"   # the importer's (import_city.WALK_MODE)
FLY_S = 8.0         # the flight's straight run
FLY_Z_M = 40.0      # its height over the player start: through the buildings in its way
TRACE_RETRY_S = 30.0  # how long a trace down that missed is tried again after settling
WARM_S = 3.0        # after a view's warm-up render, for its Nanite pages to stream in
SHOT_MESHES = 42000  # distinct meshes a shot loads at most: every Nanite mesh in memory
                    # takes a root page, and they run out at 49,152 (the 2 GB pool on the
                    # Mac), which Cragmouth's 63,700 overrun (the editor stops on a fatal error)


def log(msg):
    unreal.log(f"citygen check: {msg} ({time.time() - T0:.1f} s)")


PROGRESS = "CYBERGEN_PROGRESS"     # progress lines `citygen unreal --check` draws


def say(op, **fields):
    print(PROGRESS + " " + json.dumps({"op": op, **fields}, separators=(",", ":")), flush=True)


def ue(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def ed():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def wait(seconds):
    t = time.time()
    while time.time() - t < seconds:
        yield


def frame_times(ts):
    """Wall-clock seconds per frame (`ts`: the time at each frame) as the median, the 95th
    percentile and the longest, so a slow play session shows in the result."""
    dt = sorted(b - a for a, b in zip(ts, ts[1:]))
    if not dt:
        return {"frames": 0}
    return {"frames": len(dt), "median_s": round(dt[len(dt) // 2], 3),
            "p95_s": round(dt[(len(dt) * 19) // 20], 3), "max_s": round(dt[-1], 3)}


def frame_line(ts):
    f = frame_times(ts)
    return (f", frames {f['median_s']:.3f} s (median), {f['p95_s']:.3f} s (95%), "
            f"{f['max_s']:.2f} s at most" if f["frames"] else "")


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
    say("begin", label="check_load")
    if not les.load_level(path):
        raise RuntimeError(f"cannot load {path} (import the city first)")
    yield from wait(2.0)
    # CITYGEN_UE_PLAY_SHOTS_ONLY=1 leaves out the editor's views (only the play window's and
    # the `pday_`/`night_` views): the meshes the editor views load keep their Nanite root
    # pages, and with the play world's on top a big city (Delta Megacity with AG15, 53,790
    # meshes) runs out of them (49,152) in the walk
    if JOB.get("shots") and os.environ.get("CITYGEN_UE_PLAY_SHOTS_ONLY") != "1":
        yield from shots(man)
    # the walk with the walker (`--play walk`'s game mode; the project's own game mode and
    # pawn where the importer made none), whatever the level's Play is (its game mode
    # override, `--play`), then a flight with the fly pawn; the level is not saved
    own = game_mode(WALK_MODE if unreal.EditorAssetLibrary.does_asset_exist(WALK_MODE)
                    else None)
    log("play in editor: walking")
    say("begin", label="check_walk")
    world, pawn = yield from begin_play(les)
    RES["pawn"] = pawn.get_class().get_name()
    if os.environ.get("CITYGEN_UE_LAMP_DEBUG") != "1":
        say("note", text="the player's spawn and body")
        yield from spawn_and_body(world, pawn, man, slug)
        say("note", text="streaming around the player")
        yield from streaming(world, pawn, man, slug)
        say("note", text="traces onto the ground, roofs and facades")
        yield from collision(world, pawn, man, slug)
        say("note", text="walking the sidewalks")
        yield from walk(world, pawn, man)
        say("note", text="off a curb and back up")
        yield from curb(world, pawn, man)
        yield from cheats(world, pawn)
    else:
        yield from settle(world, slug)
    yield from play_features(world, man, slug)
    les.editor_request_end_play()
    yield from wait(2.0)
    if unreal.EditorAssetLibrary.does_asset_exist(FLY_MODE):
        game_mode(FLY_MODE)
        log("play in editor: flying")
        say("begin", label="check_fly")
        world, pawn = yield from begin_play(les)
        yield from fly(world, pawn, man, slug)
        les.editor_request_end_play()
        yield from wait(2.0)
    else:
        RES["checks"]["fly"] = {"ok": False,
                                "error": f"no {FLY_MODE} (import the city again)"}
    game_mode(own)
    say("end")
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
    number of city actors in the game world stops changing. The actors are listed once the
    streaming query says done and then every COUNT_EVERY_S, not every frame: a list of 45,000
    takes the game thread seconds, and listed every frame Vesper Bay's play ran at 6.5 s a
    frame, too few frames for the cells around a teleport to stream in before the wait ended."""
    t, last, stable, due = time.time(), -1, 0, 0.0
    while time.time() - t < timeout:
        if time.time() >= due and streamed(world, at) is not False:
            n = len(city_actors(world, slug))
            stable = stable + 1 if n == last else 0
            last = n
            if n > 0 and stable >= 2:
                break
            due = time.time() + COUNT_EVERY_S
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
        # (the buildings' shells: not their part instancers, which have no collision, nor
        # their street fronts, AG3's ground bands)
        blds = [a for a in city_actors(world, slug) if tag(a, "cg.category") == "building"
                and not tag(a, "cg.type").startswith("part.")
                and tag(a, "cg.type") != "building.front"]
        blds.sort(key=lambda a: (a.get_actor_bounds(False)[0] - here).length())
        for a in blds[:12]:
            o, e = a.get_actor_bounds(False)
            top = o.z + e.z
            # (#83: a stage 2 shell stands over its street front, AG3's own actor, so its
            # bounds start at the band's top, 7.5 m up on a one-storey shed or yard, or are an
            # open shed's roof slab alone: the ground it stands on is its pivot, the base its
            # ground floor stands at; a blockout box starts on the ground)
            floor = o.z - e.z
            if "cg.stage=2" in tags_of(a):
                floor = min(floor, a.get_actor_location().z)
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
                          unreal.Vector(x, y, floor - 100.0), [pawn])
                if h is not None and h["point"].z > floor + 300.0:
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
    ticks = []
    # (as long as the path takes at the pawn's walking speed, half again, at least WALK_S:
    # the walker walks at 4.2 m/s, the template's character ran at 6)
    length = sum(math.dist(path[j][:2], path[j + 1][:2]) for j in range(len(path) - 1))
    try:
        speed = float(mc.get_editor_property("max_walk_speed")) / 100.0
    except Exception:           # noqa: BLE001 (a pawn without a character's movement)
        speed = 6.0
    limit = max(WALK_S, 1.5 * length / max(speed, 1.0))
    while k < len(path) and time.time() - t < limit:
        ticks.append(time.time())
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
    ticks.append(time.time())     # (the last frame's end: a long one shows)
    length = sum(math.dist(path[j][:2], path[j + 1][:2]) for j in range(len(path) - 1))
    reached = k >= len(path)
    share = on_ground / max(frames, 1)
    z_drop = (lift0 - low) / 100.0     # fallen below the path, not walked downhill
    ok = (reached or travelled / 100.0 >= 0.9 * length) and share >= 0.9 and z_drop < 3.0
    RES["checks"]["walk"] = {"ok": ok, "path_m": round(length, 1), "points": len(path),
                             "reached": reached, "travelled_m": round(travelled / 100.0, 1),
                             "on_ground": round(share, 3), "max_drop_m": round(z_drop, 2),
                             "seconds": round(time.time() - t, 1), "stopped_by": blockers,
                             "stops": stops, "skipped_low_walkways": skipped,
                             "frame_time": frame_times(ticks)}
    stops = (", stepped round " + ", ".join(f"{v} x {k_}" for k_, v in sorted(
        blockers.items()))) if blockers else ""
    RES["lines"].append(f"walk: {travelled / 100.0:.0f} m along a {length:.0f} m sidewalk "
                        f"path in {time.time() - t:.0f} s, {100 * share:.0f}% of frames on "
                        f"the ground, {'reached its end' if reached else 'did not reach its end'}"
                        + stops + frame_line(ticks))


def spawn_and_body(world, pawn, man, slug):
    """Where Play put the player (on its feet beside the player start, which the manifest
    sets on a sidewalk, and what it stands on) and whether it has a body it sees itself (the
    walker's `has_visible_body`); with --shots, the walker looking down at itself and ahead
    (`unreal_walk_body.png`, `unreal_walk_ahead.png`)."""
    yield from settle(world, slug)
    mc = pawn.get_movement_component()
    t = time.time()
    while time.time() - t < 8.0 and not (mc is not None and mc.is_moving_on_ground()):
        yield
    loc = pawn.get_actor_location()
    sx, sy, sz = man["player_start"]["position"]
    off = math.hypot(loc.x / 100.0 - sx, -loc.y / 100.0 - sy)
    down = trace(world, loc, unreal.Vector(loc.x, loc.y, loc.z - 400.0), [pawn])
    under = ""
    if down is not None:
        a = down["actor"]
        under = (tag(a, "cg.category") or tag(a, "cg.type") or a.get_class().get_name())
    body = None
    if hasattr(pawn, "has_visible_body"):
        body = bool(pawn.has_visible_body())
        mesh = pawn.get_editor_property("mesh").get_editor_property("skeletal_mesh_asset")
        RES["body_mesh"] = mesh.get_path_name() if mesh else ""
    grounded = bool(mc is not None and mc.is_moving_on_ground())
    ok = grounded and off < 2.0 and body is not False
    RES["checks"]["spawn"] = {"ok": ok, "pawn": pawn.get_class().get_name(),
                              "on_ground": grounded, "from_start_m": round(off, 2),
                              "stands_on": under, "visible_body": body}
    RES["lines"].append(f"spawn: {pawn.get_class().get_name()} {off:.1f} m from the player "
                        f"start, {'on its feet' if grounded else 'NOT on the ground'} on "
                        f"{under or 'nothing'}; "
                        + ("a body it sees" if body else "no body it sees" if body is False
                           else "the project's pawn"))
    if JOB.get("shots") and body:
        # by day (the play features' Night 0), from the player start or from the eye of a
        # `--view walk_spot ...` (the player stood there, facing its target)
        pc = unreal.GameplayStatics.get_player_controller(world, 0)
        yaw = -float(man["player_start"].get("yaw_deg", 0.0))
        # (`--view walk_spot__<state> ...`: in that weather state, settled, as the play views)
        spot = next((v for v in JOB.get("views", []) if v["name"] == "walk_spot"
                     or v["name"].startswith("walk_spot__")), None)
        state = spot["name"].split("__", 1)[1] if spot and "__" in spot["name"] else None
        here = pawn.get_actor_location()
        if spot is not None:
            ex, ey, ez = spot["eye"]
            # (held in the air until the city there has streamed in, then let down)
            if mc is not None:
                mc.disable_movement()
            teleport(pawn, ex, ey, ez + 1.2)
            yield from settle(world, slug, at=ue(ex, ey, ez))
            yield from wait(3.0)
            if mc is not None:
                mc.set_movement_mode(unreal.MovementMode.MOVE_FALLING)
            yield from wait(2.0)
            yaw = unreal.MathLibrary.find_look_at_rotation(ue(*spot["eye"]),
                                                           ue(*spot["target"])).yaw
        unreal.SystemLibrary.execute_console_command(world, "CityGen.Night 0")
        st0w = None
        if state:
            st0w = (atmos_status(world) or {}).get("weather_target") or "rain"
            unreal.SystemLibrary.execute_console_command(
                world, f"CityGenAtmos.Weather {state} now")
            yield from wait(4.0)
        # (CITYGEN_UE_VIEW_RES: a HighResShot of that size, as the play views; else the
        # play window as drawn)
        res = os.environ.get("CITYGEN_UE_VIEW_RES")
        for name, pitch in (("walk_body", -68.0), ("walk_ahead", -8.0)):
            pc.set_control_rotation(unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw))
            yield from wait(2.0)
            yield from ui_shot(world, name, cmd=f"HighResShot {res}" if res else "shot",
                               timeout=600 if res else 30)
        if st0w:
            unreal.SystemLibrary.execute_console_command(
                world, f"CityGenAtmos.Weather {st0w} now")
        if spot is not None:
            pawn.set_actor_location(here, False, True)
            yield from wait(1.0)


def curb(world, pawn, man):
    """Off a sidewalk's curb onto the road beside it and back up (the walker's step height
    climbs it): from the sidewalk points nearest the player start, toward the nearest lane
    point, until the player has stepped down, then back to where it started. Passes when the
    player came back up onto the sidewalk on its feet."""
    g = json.load(open(os.path.join(JOB["build_dir"], "unreal", "graphs.json"),
                       encoding="utf-8"))
    sx, sy, _ = man["player_start"]["position"]
    lanes = g["lanes"]["points"]
    lane_pts = [(lanes[k], lanes[k + 1], lanes[k + 2]) for k in range(0, len(lanes), 3)]
    path, _ = sidewalk_path(JOB["build_dir"], (sx, sy), 60.0)
    mc = pawn.get_movement_component()
    tries = []
    for p in path[::4][:6]:
        near = min(lane_pts, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2)
        d = math.dist(near[:2], p[:2])
        if d > 15.0 or d < 1.0:
            continue
        teleport(pawn, p[0], p[1], p[2] + 1.2)
        yield from wait(1.5)
        z0 = pawn.get_actor_location().z
        start = pawn.get_actor_location()
        fx, fy = (near[0] - p[0]) / d, -(near[1] - p[1]) / d
        low, t, stepped = z0, time.time(), False
        while time.time() - t < 4.0:
            loc = pawn.get_actor_location()
            low = min(low, loc.z)
            if z0 - low > 5.0 and math.hypot(loc.x - start.x, loc.y - start.y) > 150.0:
                stepped = True
                break
            pawn.add_movement_input(unreal.Vector(fx, fy, 0.0), 1.0, False)
            yield
        t, back, ground = time.time(), False, 0
        frames = 0
        while time.time() - t < 5.0:
            loc = pawn.get_actor_location()
            dx, dy = start.x - loc.x, start.y - loc.y
            n = math.hypot(dx, dy)
            if n < 40.0:
                back = True
                break
            pawn.add_movement_input(unreal.Vector(dx / n, dy / n, 0.0), 1.0, False)
            frames += 1
            ground += bool(mc is not None and mc.is_moving_on_ground())
            yield
        yield from wait(0.5)
        z1 = pawn.get_actor_location().z
        rec = {"at": [round(p[0], 2), round(p[1], 2)], "down_m": round((z0 - low) / 100.0, 3),
               "stepped_down": stepped, "back": back,
               "back_up_m": round((z1 - low) / 100.0, 3),
               "on_ground": round(ground / max(frames, 1), 2)}
        tries.append(rec)
        rec["climbed"] = stepped and back and abs(z1 - z0) < 3.0
        if rec["climbed"] and rec["down_m"] >= 0.12:
            break             # (a full curb; a lower one, a curb ramp's, tries on)
    # back up on the sidewalk at its height, after stepping down off it
    ok = any(r["climbed"] for r in tries)
    RES["checks"]["curb"] = {"ok": ok, "tries": tries}
    best = max((r for r in tries if r["climbed"]), key=lambda r: r["down_m"], default=None)
    RES["lines"].append(
        f"curb: stepped {best['down_m']:.2f} m down onto the road and back up" if best and ok
        else f"curb: no curb climbed in {len(tries)} tries")


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


def status(actor):
    return json.loads(actor.get_status())


def play_features(world, man, slug):
    """The play features (the CityGenPlay plugin's actor), when the import made them: the
    overlay on screen, the map and the developer menu open and close, night and day (AT1:
    atmosgen's lights nearest the player live by night, its cells registered, when the
    import placed its controller; else the light pools under the lamps), the free camera
    there and back, and a teleport across the city onto a walkway, the player held until the
    city streamed in there and on the ground after. With `shots`: the minimap, the map and
    the street by night."""
    if not man.get("play"):
        return
    cls = getattr(unreal, "CityGenPlay", None)
    found = unreal.GameplayStatics.get_all_actors_of_class(world, cls) if cls else []
    if not found:
        RES["checks"]["play_features"] = {"ok": False, "error": "no CityGenPlay actor playing"
                                          if cls else "no CityGenPlay class (plugin not built)"}
        return
    a = found[0]
    got = {"start": status(a)}
    pawn0 = got["start"]["pawn"]
    # (the engine's own on-screen debug text, a big city's texture pool notice among it,
    # would be drawn over the minimap in the shots)
    unreal.SystemLibrary.execute_console_command(world, "DisableAllScreenMessages")
    if JOB.get("shots"):
        yield from ui_shot(world, "play_minimap")
    a.set_map_open(True)
    yield from wait(1.0)
    got["map"] = status(a)["map"]
    if JOB.get("shots"):
        yield from ui_shot(world, "play_map")
    a.set_map_open(False)
    a.set_dev_menu_open(True)
    yield from wait(0.5)
    got["menu"] = status(a)["menu"]
    if JOB.get("shots"):
        yield from ui_shot(world, "play_menu")
    a.set_dev_menu_open(False)
    # (AT4: art direction: console commands for this check's views, `;` between them, from
    # $CITYGEN_UE_ATMOS_CMDS, e.g. "CityGenAtmos.VolumeGain 2;CityGenAtmos.FogSet 0.03 0.08 2")
    for c in (os.environ.get("CITYGEN_UE_ATMOS_CMDS") or "").split(";"):
        if c.strip():
            unreal.SystemLibrary.execute_console_command(world, c.strip())
            log(f"atmos command: {c.strip()}")
    a.set_night(True)
    yield from wait(2.0)
    got["night"] = status(a)
    at = atmos_status(world)
    if at is not None:
        got["atmos_night"] = at
    if JOB.get("shots"):
        yield from ui_shot(world, "play_night")
    a.set_free_cam(True)
    yield from wait(1.0)
    got["free_cam"] = status(a)
    # AT3: atmosgen's sky and time by day and at dusk (the controller's status)
    if at is not None and at.get("sky"):
        a.set_night(False)
        yield from wait(2.0)
        got["atmos_day"] = atmos_status(world)
        a.click_menu_row("hour=dusk")
        yield from wait(2.0)
        got["atmos_dusk"] = atmos_status(world)
        a.set_night(True)
        yield from wait(2.0)
    if JOB.get("shots"):
        # the `--view`s named `pday_*` from the free camera by day, `night_*` by night; AT3:
        # `dusk_*` at the plan's dusk, `t<HHMM>_*` at that hour (atmosgen's time of day)
        a.set_night(False)
        yield from play_views(world, a, slug, "pday_")
        if at is not None and at.get("sky"):
            a.click_menu_row("hour=dusk")
            yield from wait(2.0)
            yield from play_views(world, a, slug, "dusk_")
            for hh in sorted({v["name"][1:5] for v in JOB.get("views", [])
                              if re.match(r"^t\d{4}_", v["name"])}):
                a.click_menu_row(f"hour={int(hh[:2]) + int(hh[2:]) / 60.0:g}")
                yield from wait(2.0)
                yield from play_views(world, a, slug, f"t{hh}_")
        a.set_night(True)
        yield from wait(2.0)
        # the free camera 120 m over the player, looking at the city's middle by night
        cam = unreal.GameplayStatics.get_player_pawn(world, 0)
        pc = unreal.GameplayStatics.get_player_controller(world, 0)
        b = man["bounds"]
        here = cam.get_actor_location()
        eye = unreal.Vector(here.x, here.y, here.z + 12000.0)
        cam.set_actor_location(eye, False, True)
        pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(
            eye, ue((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0, 0.0)))
        yield from wait(3.0)
        yield from ui_shot(world, "play_free_cam_night")
        yield from play_views(world, a, slug, "night_")
    a.set_free_cam(False)
    yield from wait(1.0)
    got["back"] = status(a)
    a.set_night(False)
    unreal.SystemLibrary.execute_console_command(world, "EnableAllScreenMessages")
    # a teleport to the walkway nearest the far corner of the city from the start
    sx, sy, _ = man["player_start"]["position"]
    b = man["bounds"]
    tx = b[0] + 0.2 * (b[2] - b[0]) if sx > (b[0] + b[2]) / 2.0 else b[2] - 0.2 * (b[2] - b[0])
    ty = b[1] + 0.2 * (b[3] - b[1]) if sy > (b[1] + b[3]) / 2.0 else b[3] - 0.2 * (b[3] - b[1])
    a.teleport_player_to_citygen(tx, ty)
    t = time.time()
    yield from wait(1.0)
    while status(a)["waiting"] and time.time() - t < 120:
        yield
    yield from wait(2.0)
    got["teleport"] = status(a)
    p = unreal.GameplayStatics.get_player_pawn(world, 0)
    loc = p.get_actor_location()
    down = trace(world, loc, unreal.Vector(loc.x, loc.y, loc.z - 1000.0), [p])
    tp = got["teleport"]
    moved = math.hypot(tp["x"] - sx, tp["y"] - sy)
    an = got.get("atmos_night")
    # (AT1: by night atmosgen's live set lights the street; without its controller the light
    # pools under the lamps do)
    lit = (an["showing"] and an["cells"] > 0 and an["live"] > 0) if an is not None and \
        man.get("atmos", {}).get("cells") else \
        (got["night"].get("light_pools", 0) > 0 or got["night"]["lamp_points"] == 0)
    # AT3: the night held dark (Night 1, the night's exposure), the day lit by the sun with no
    # light live, dusk between them with its lights coming on
    ad, ak = got.get("atmos_day"), got.get("atmos_dusk")
    sky_ok = True
    if an is not None and an.get("sky"):
        sky_ok = (an["night_now"] > 0.99 and an["dome"] and ad is not None and ak is not None
                  and ad["night_now"] < 0.01 and not ad["showing"] and ad["sun_elev"] > 5.0
                  and 0.01 < ak["night_now"] < 0.99 and ak["sun_elev"] < 0.0
                  and ad["ev100"] > ak["ev100"] > an["ev100"])
        lit = lit and sky_ok
    # AT4: with the plan's air, its fog on by night, fog volumes registered and live near the
    # player where the plan has some, and its plumes' cards made
    air_ok = True
    if an is not None and an.get("air") is not None and (man.get("atmos") or {}).get("volumes"):
        air_ok = bool(an["fog"]) and an["air"] and an["volumes"] > 0 and an["plume_cards"] >= 0
        lit = lit and air_ok
    # AT5: with the plan's weather, the start state by night: its textures set, its rain
    # falling and its streets wet where the state rains (neon rain's), the menu's weather row
    weather_ok = True
    if an is not None and an.get("weather"):
        raining = an.get("rain_now", 0.0) > 0.01
        weather_ok = bool(an.get("wet_textures")) and (
            not raining or (an.get("rain_shown") and an.get("wet_shown")))
        lit = lit and weather_ok
    # AT6: with the plan's look, its post applied by night (a district under the view where
    # the plan has some), the day's exposure brighter than the night's still
    post_ok = True
    if an is not None and an.get("post") is not None and \
            (man.get("atmos") or {}).get("post"):
        post_ok = bool(an["post"]) and an.get("post_bloom", 0.0) > 0.0 and (
            not (man["atmos"]["post"] or {}).get("districts") or bool(an.get("post_where")))
        lit = lit and post_ok
    # AT7: with the plan's far cards, every one of them drawn and shown by night (the play
    # features' light pools gone), none by day
    far_ok = True
    if an is not None and an.get("far") is not None and \
            ((man.get("atmos") or {}).get("far") or {}).get("cards"):
        far_ok = bool(an["far"]) and bool(an.get("far_shown")) and \
            an.get("far_glows", 0) + an.get("far_flats", 0) == an.get("far_cards", -1) and \
            (ad is None or not ad.get("far_shown"))
        lit = lit and far_ok
    ok = (got["start"]["ready"] and got["start"]["overlay"] and got["start"]["map_texture"]
          and got["map"] and got["menu"] and got["night"]["night"] and lit
          and got["free_cam"]["free_cam"] and got["free_cam"]["pawn"].startswith("CityGenFreeCam")
          and not got["back"]["free_cam"] and got["back"]["pawn"] == pawn0
          and not tp["waiting"] and moved > 100.0 and down is not None)
    RES["checks"]["play_features"] = {
        "ok": ok, "pawn": pawn0, "walk_points": got["start"]["walk_points"],
        "lamp_points": got["start"]["lamp_points"],
        # (AT1: atmosgen's live set by night, the play features' light pools past it)
        "atmos_night": an, "light_pools": got["night"].get("light_pools"),
        "sky": {"ok": sky_ok, "night": _sky(an), "dusk": _sky(ak), "day": _sky(ad)},
        "teleport_to": [round(tx, 1), round(ty, 1)],
        "teleported_m": round(moved, 1), "landed": down is not None, "states": got}
    # (AT2: of them in the high tier, and the aviation beacons and searchlight beams loaded)
    night = (f"{an['live']} atmos lights live of {an['lights']} in {an['cells']} cells, "
             f"{an['shadowed']} shadowed, {an.get('high', 0)} high, {an.get('beacons', 0)} "
             f"beacons, {an.get('beams', 0)} beams" if an else "no atmos controller")
    if an is not None and an.get("sky"):
        RES["lines"].append("sky and time (AT3): " + "; ".join(
            f"{n} {s['hour']:g} h, sun {s['sun_elev']:.1f} deg, Night {s['night_now']:.2f}, "
            f"{s['ev100']:.2f} EV100, {s['live']} lights live"
            for n, s in (("night", an), ("dusk", ak), ("day", ad)) if s)
            + (" (ok)" if sky_ok else " (FAIL)"))
    if an is not None and an.get("air") is not None:
        RES["lines"].append(
            f"air (AT4): fog {an.get('fog')} (its share {an.get('fog_share', 0):.2f}, volumetric "
            f"to {an.get('fog_view_m', 0):.0f} m), {an.get('volumes', 0)} fog volumes registered, "
            f"{an.get('volumes_live', 0)} live, {an.get('emitters', 0)} plumes "
            f"({an.get('plume_cards', 0)} cards), engine settings tuned {an.get('tuned')} "
            + ("(ok)" if air_ok else "(FAIL)"))
    if an is not None and an.get("weather"):
        RES["lines"].append(
            f"weather (AT5): {an.get('weather_now')} (rain {an.get('rain_now', 0):.2f}, wetness "
            f"{an.get('wetness', 0):.2f}, puddles {an.get('puddles', 0):.2f}, wind "
            f"{an.get('wind_ms', 0):.1f} m/s, cover {an.get('cloud_cover', 0):.2f}), rain shown "
            f"{an.get('rain_shown')}, wet streets {an.get('wet_shown')}, "
            f"{an.get('splashes_live', 0)} splashes, {an.get('drips', 0)} drips of "
            f"{an.get('drip_lines', 0)} lines, textures {an.get('wet_textures')} "
            + ("(ok)" if weather_ok else "(FAIL)"))
    if an is not None and an.get("post") is not None:
        RES["lines"].append(
            f"look (AT6): post {an.get('post')}, by the player {an.get('post_where') or '-'} "
            f"(bloom {an.get('post_bloom', 0):.2f}, grain {an.get('post_grain', 0):.2f}, fringe "
            f"{an.get('post_fringe', 0):.2f}, saturation {an.get('post_saturation', 0):.2f}, "
            f"contrast {an.get('post_contrast', 0):.2f}, sharpen {an.get('post_sharpen', 0):.2f}) "
            + ("(ok)" if post_ok else "(FAIL)"))
    if an is not None and an.get("far") is not None:
        RES["lines"].append(
            f"far city (AT7): {an.get('far_glows', 0)} glows and {an.get('far_flats', 0)} "
            f"pools and washes of {an.get('far_cards', 0)} cards in {an.get('far_blocks', 0)} "
            f"blocks (built in {an.get('far_build_ms', 0):.0f} ms), shown {an.get('far_shown')} "
            f"by night, past {an.get('far_mid_m', 0):.0f} m (high {an.get('far_high_m', 0):.0f}, "
            f"beacons {an.get('far_fix_m', 0):.0f}) " + ("(ok)" if far_ok else "(FAIL)"))
    RES["lines"].append(
        f"play features: map, menu, night ({night}, "
        f"{got['night'].get('light_pools', 0)} light pools), free camera "
        f"and back, teleport {moved:.0f} m "
        + ("onto the ground" if down is not None else "with nothing under the player"))


def _sky(st):
    """AT3: a status's sky and time (or None)."""
    if not st or not st.get("sky"):
        return None
    return {k: st.get(k) for k in ("hour", "night_now", "ev100", "sun_elev", "moon_elev",
                                     "moon_lux", "showing", "live", "dome", "cover", "glow")}


def atmos_status(world):
    """The atmos controller's state (AT1), or None when the level has none."""
    cls = getattr(unreal, "CityGenAtmos", None)
    found = unreal.GameplayStatics.get_all_actors_of_class(world, cls) if cls else []
    return json.loads(found[0].get_status()) if found else None


def play_views(world, a, slug, prefix):
    """The `--view`s named `<prefix>*` from the free camera in the play world (by night
    atmosgen's lights and the light pools live only there; streaming loads the
    city around each view, where the editor's shots load at most `SHOT_MESHES` meshes near
    the city's middle): the camera moved to each eye, the city streamed in around it, the
    minimap hidden, a 1920 x 1080 HighResShot (no overlay)."""
    views = [v for v in JOB.get("views", []) if v["name"].startswith(prefix)]
    if not views:
        return
    cam = unreal.GameplayStatics.get_player_pawn(world, 0)
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    try:
        a.set_editor_property("b_show_minimap", False)
    except Exception:           # noqa: BLE001 (a plugin without the property)
        pass
    for v in views:
        # (AT3: a view named `*_clear` with the cloud deck opened to a few clouds, for the
        # moon and the stars; the plan's cover again after it)
        clear = v["name"].endswith("_clear")
        if clear:
            cover = (atmos_status(world) or {}).get("cover", 0.8)
            unreal.SystemLibrary.execute_console_command(world, "CityGenAtmos.Cover 0.2")
        # (AT4: a view named `*_noair` without the fog, the fog volumes and the plumes, the
        # same view's before for AT4's pairs; the level's air again after it)
        noair = v["name"].endswith("_noair")
        if noair:
            st0 = atmos_status(world) or {}
            for c in ("CityGenAtmos.Fog 0", "CityGenAtmos.Air 0"):
                unreal.SystemLibrary.execute_console_command(world, c)
        # (AT6: a view named `*_nopost` without the look's post, the same view's before for
        # AT6's pairs; the look again after it)
        nopost = "_nopost" in v["name"]
        if nopost:
            unreal.SystemLibrary.execute_console_command(world, "CityGenAtmos.Post 0")
        # (AT7: a view named `*_nofar` without the far city's cards, the play features' light
        # pools past the live range instead: the same view's before; the cards again after it)
        nofar = "_nofar" in v["name"]
        if nofar:
            unreal.SystemLibrary.execute_console_command(world, "CityGenAtmos.Far 0")
        # (visible lights: a view named `*_sight` with the live set picked by sight, as round
        # a walker, `*_circle` by the circle, the same view's before; by the pawn after it)
        mode = 1 if v["name"].endswith("_sight") else 0 if v["name"].endswith("_circle") else None
        if mode is not None:
            unreal.SystemLibrary.execute_console_command(world, f"CityGenAtmos.Sight {mode}")
        # (AT5: a view named `*__<state>` in that weather state, settled; `*__<a>2<b>_<n>s` in
        # state a, then turning to b for n seconds when the view has streamed in (a frame of
        # the transition); the plan's start state again after it)
        wm = re.search(r"__([a-z]+?)(?:2([a-z]+)_(\d+(?:\.\d+)?)s)?$", v["name"])
        st0w = None
        if wm:
            st0w = (atmos_status(world) or {}).get("weather_target") or "rain"
            unreal.SystemLibrary.execute_console_command(
                world, f"CityGenAtmos.Weather {wm.group(1)} now")
        eye, tg = ue(*v["eye"]), ue(*v["target"])
        cam.set_actor_location(eye, False, True)
        pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(eye, tg))
        try:
            pc.player_camera_manager.set_fov(2.0 * math.degrees(
                math.atan(18.0 / v.get("lens_mm", 28))))
        except Exception:       # noqa: BLE001
            pass
        yield from settle(world, slug, at=eye)
        yield from wait(4.0)
        if wm and wm.group(2):
            unreal.SystemLibrary.execute_console_command(
                world, f"CityGenAtmos.Weather {wm.group(2)}")
            yield from wait(float(wm.group(3)))
        # (AT7: CITYGEN_UE_VIEW_RES sets the views' size, 7680x4320 for an 8K shot)
        res = os.environ.get("CITYGEN_UE_VIEW_RES") or "1920x1080"
        yield from ui_shot(world, v["name"], f"HighResShot {res}", 600)
        at = atmos_status(world)
        # (AT6: what the look showed at each view: the district, the exposure, the post)
        if at and "post" in at:
            RES.setdefault("post_views", {})[v["name"]] = {
                k: at.get(k) for k in ("post", "post_where", "ev100", "night_now",
                                       "overcast_shift", "post_bloom", "post_grain",
                                       "post_fringe", "post_saturation", "post_contrast",
                                       "post_sharpen")}
        if nopost:
            unreal.SystemLibrary.execute_console_command(world, "CityGenAtmos.Post 1")
        # (AT7: what the far city showed at each view)
        if at and "far" in at:
            RES.setdefault("far_views", {})[v["name"]] = {
                k: at.get(k) for k in ("far", "far_shown", "far_glows", "far_flats",
                                       "far_mid_m", "far_high_m", "far_fix_m", "far_px",
                                       "live", "sight", "ev100")}
        if nofar:
            unreal.SystemLibrary.execute_console_command(world, "CityGenAtmos.Far 1")
        if wm:
            if at:
                RES.setdefault("weather_views", {})[v["name"]] = {
                    k: at.get(k) for k in ("weather_now", "transition", "rain_now", "wetness",
                                           "puddles", "wind_ms", "cloud_cover", "fog_density",
                                           "rain_shown", "wet_shown", "splashes_live", "drips")}
            unreal.SystemLibrary.execute_console_command(
                world, f"CityGenAtmos.Weather {st0w} now")
        if mode is not None:
            unreal.SystemLibrary.execute_console_command(world, "CityGenAtmos.Sight -1")
            if at:
                RES.setdefault("sight_views", {})[v["name"]] = {
                    k: at.get(k) for k in ("sight", "live", "live_kinds", "candidates",
                                           "sight_seen", "sight_tested", "sight_rays",
                                           "sight_ms", "high", "shadowed", "fading")}
        if clear:
            unreal.SystemLibrary.execute_console_command(world, f"CityGenAtmos.Cover {cover:g}")
        if noair:
            for c in (f"CityGenAtmos.Fog {int(bool(st0.get('fog')))}",
                      f"CityGenAtmos.Air {int(bool(st0.get('air')))}"):
                unreal.SystemLibrary.execute_console_command(world, c)
        log(f"play view {v['name']}" + (f": atmos {at['live']} live"
                                         + (" by sight" if at.get("sight") else "")
                                         + f" ({at['live_kinds']}), "
                                         f"{at['shadowed']} shadowed, {at.get('high', 0)} high"
                                         + (f", fog {at.get('fog')}, {at.get('volumes_live', 0)} "
                                            f"fog volumes live, {at.get('plume_cards', 0)} plume "
                                            f"cards" if "air" in at else "")
                                         if at else ""))
    try:
        pc.player_camera_manager.unlock_fov()
        a.set_editor_property("b_show_minimap", True)
    except Exception:           # noqa: BLE001
        pass


def ui_shot(world, name, cmd="shot showui", timeout=30):
    """A screenshot of the play window with its overlay (HighResShot leaves the UI out)."""
    out = JOB["shots"]
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"unreal_{name}.png").replace("\\", "/")
    if os.path.exists(path):
        os.remove(path)
    shots_dir = os.path.join(unreal.Paths.project_saved_dir(), "Screenshots")

    def pngs():
        found = {}
        for root, _, files in os.walk(shots_dir):
            for f in files:
                if f.lower().endswith(".png"):
                    p = os.path.join(root, f)
                    found[p] = os.path.getmtime(p)
        return found

    before = pngs()
    yield from wait(1.0)
    # `shot showui`: the play window as drawn, overlay included, into Saved/Screenshots
    unreal.SystemLibrary.execute_console_command(world, cmd)
    t, new = time.time(), []
    while not new and time.time() - t < timeout:
        yield
        new = [p for p, m in pngs().items() if p not in before or m > before[p]]
    # (until the file stops growing: an 8K PNG takes a few seconds to write)
    size, t = -1, time.time()
    while new and time.time() - t < 120:
        yield from wait(1.0)
        s = os.path.getsize(max(new, key=os.path.getmtime))
        if s == size:
            break
        size = s
    if new:
        import shutil
        shutil.copyfile(max(new, key=os.path.getmtime), path)
        RES.setdefault("play_shots", []).append(path)
        log(f"wrote {path}")


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
    ticks = []
    while time.time() - t < FLY_S:
        ticks.append(time.time())
        pawn.add_movement_input(unreal.Vector(dx, -dy, 0.0), 1.0, False)
        yield
    ticks.append(time.time())
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
                            "end_tile_loaded": tile in tiles,
                            "frame_time": frame_times(ticks)}
    RES["lines"].append(
        f"fly: {RES['fly_pawn']} at {speed:g} m/s flew {dist:.0f} m in {secs:.1f} s"
        + (f" through {through}" if through else "") + f", {len(here)} actors loaded where it "
        "ended" + frame_line(ticks))
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

def view_load(rows, target, cap=SHOT_MESHES):
    """The actor descs a view loads, from (guid, kind, x, y, meshes) rows (kind `hlod` for the
    HLOD actors, never loaded; x and y the middle of its bounds; meshes the actor's Nanite
    meshes, its own and its parts' (AG16's groups), empty for one whose meshes are shared or
    have no Nanite): every other row when their distinct meshes fit in `cap`, else the rows
    nearest the target (plan x, y) up to `cap` meshes."""
    rows = [r for r in rows if r[1] != "hlod"]
    if len({m for r in rows for m in r[4]}) <= cap:
        return [r[0] for r in rows]
    tx, ty = target
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: ((r[2] - tx) ** 2 + (r[3] - ty) ** 2, str(r[0]))):
        new = [m for m in r[4] if m not in seen]
        if new:
            if len(seen) + len(new) > cap:
                continue
            seen.update(new)
        out.append(r[0])
    return out


def mesh_of(man):
    """Each actor key's Nanite meshes from the manifest: a blockout object's own, a stage 2
    actor's and its parts' (AG16: an entry's parts are components of its actor or group
    actor, `holder`; before, each part instancer an actor of its own); none for a prop or
    plant instancer (shared prototypes) and the LOD chains (no Nanite)."""
    s2 = man.get("stage2") or {}
    lod = {c["mesh"] for c in s2.get("lod_chains", [])}
    out = {}
    for t in man.get("tiles", []):
        for o in t.get("objects", []):
            out[o["key"]] = [f"Meshes/{t['name']}/{o['asset']}"]
    for r in s2.get("actors", []) + s2.get("instances", []):
        key = r.get("holder") or r["key"]
        if r.get("mesh") and r["mesh"] not in lod:
            out.setdefault(key, []).append(r["mesh"])
        else:
            out.setdefault(key, [])
    return out


def desc_rows(WPL, meshes):
    rows = []
    for d in WPL.get_actor_descs():
        hlod = "HLOD" in str(getattr(d, "native_class", ""))
        bd = getattr(d, "bounds", None)
        x = y = 0.0
        if bd is not None:
            x = (bd.min.x + bd.max.x) / 200.0
            y = -(bd.min.y + bd.max.y) / 200.0
        rows.append((d.guid, "hlod" if hlod else "actor", x, y,
                     tuple(meshes.get(str(getattr(d, "label", ""))) or ())))
    return rows


def shots(man):
    """Renders of the city in the editor world, every actor loaded (or, past `SHOT_MESHES`
    meshes, those nearest the city's middle): the isometric view and the blockout's street
    views."""
    out = JOB["shots"]
    os.makedirs(out, exist_ok=True)
    WPL = unreal.WorldPartitionBlueprintLibrary
    rows = desc_rows(WPL, mesh_of(man))
    n_mesh = len({r[4] for r in rows if r[1] != "hlod" and r[4] is not None})
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    b = man["bounds"]
    cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    size = max(b[2] - b[0], b[3] - b[1])
    d = man["cameras"].get("iso_dir") or [0.28, 0.77, -0.57]
    dist = 2.3 * size        # the whole city in a 30 degree field of view
    views = [("iso_city", (cx - d[0] * dist, cy - d[1] * dist, -d[2] * dist), (cx, cy, 0.0),
              30.0)]
    for v in man["cameras"].get("street", [])[:3] + [
            v for v in JOB.get("views", [])
            if not v["name"].startswith(("night_", "pday_"))]:
        views.append((v["name"], tuple(v["eye"]), tuple(v["target"]),
                      2.0 * math.degrees(math.atan(18.0 / v.get("lens_mm", 28)))))
    files = []
    w = int(JOB.get("width") or 3840)
    # one set for every view: an actor unloaded between views keeps its meshes' root pages
    # (Cragmouth stopped at its fourth view, each of 42,000 meshes)
    loaded = view_load(rows, (cx, cy))
    WPL.load_actors(loaded)
    log(f"loaded {len(loaded)} actors for the shots" + (
        f" ({SHOT_MESHES} of {n_mesh} meshes, the nearest to the city's middle)"
        if n_mesh > SHOT_MESHES else ""))
    yield from wait(5.0)
    say("begin", label="check_shots", total=len(views))
    for k, (name, eye, target, fov) in enumerate(views):
        cam = eas.spawn_actor_from_class(unreal.CameraActor, ue(*eye), transient=True)
        e, tg = ue(*eye), ue(*target)
        rot = unreal.MathLibrary.find_look_at_rotation(e, tg)
        cam.set_actor_rotation(rot, False)
        cam.camera_component.set_editor_property("field_of_view", fov)
        path = os.path.join(out, f"unreal_{name}.png")
        if os.path.exists(path):
            os.remove(path)
        unreal.AutomationLibrary.finish_loading_before_screenshot()   # shaders, streaming
        # a small render from the camera first: Nanite streams the pages a view needs from
        # what that view drew, so a first render of a new view shows coarse clusters (big
        # flat triangles over the walls) where its pages had not come in yet
        warm = os.path.join(out, f"warm_{name}.png")
        unreal.AutomationLibrary.take_high_res_screenshot(960, 540, warm, cam)
        t = time.time()
        while not os.path.exists(warm) and time.time() - t < 120:
            yield
        yield from wait(WARM_S)
        if os.path.exists(warm):
            os.remove(warm)
        unreal.AutomationLibrary.take_high_res_screenshot(w, w * 9 // 16, path, cam)
        t = time.time()
        while not os.path.exists(path) and time.time() - t < 300:
            yield
        yield from wait(1.0)
        eas.destroy_actor(cam)
        if os.path.exists(path):
            files.append(path)
            log(f"wrote {path}")
        say("update", done=k + 1)
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
