"""carcheck: the kit's checks on a car as built (Blender side: stdlib, bpy and mathutils).

    vehicles/blender.sh vehicles/cars/NAME.py --out DIR --check       # a table and DIR/check.json

carkit.check() runs them at the end of a car's script. Nothing here changes the car. Each
check gives a verdict: ok, look (worth a look at the place named; often meant) or fail.

  tires      every tire's clearance to the rest of the car, straight and steered (the front
             pair turned about its upright axis until it touches), and its foot on the ground
  ground     the lowest point of everything that is not a wheel
  symmetry   objects whose mirror image in y = 0 is not on the car (lettering, a driver's
             wheel and one-sided parts are meant; a stray part is not)
  panels     open edges of the body panels with nothing beside them (an open end is meant; a
             tear is not), holes a cutter leaves inside one panel (a wheel well under a low
             hood breaking through it), panels a cutter cut away altogether
  through    cabin parts (seats, tubs, screens) standing in the open: outside the skin
  triangles  the car against the budget for a design mesh, and where they are
"""
import json
import os
from math import cos, radians, sin

import bmesh
import bpy
from mathutils import Vector as V3
from mathutils.bvhtree import BVHTree

TRI_BUDGET = 400000         # a design mesh (the game pack's LOD0 is baked down to 150,000)
TIRE_TOUCH_M = 0.004        # a tire this close to anything else touches it
TIRE_NEAR_M = 0.025         # ... and this close is worth a look
STEER_STEPS = (5, 10, 15, 20, 25, 30, 35)
STEER_WANT = 20             # degrees a front wheel should turn each way before it touches
GROUND_FAIL_M = 0.0         # anything of the car under the floor
GROUND_LOW_M = 0.09         # a wheeled car this low is worth a look
TIRE_FOOT_M = 0.006         # a tire's lowest point this far off the ground
SYM_M = 0.003               # an object's mirror image this far off the car is not symmetric
SYM_TIRE_M = 0.02
SYM_SAMPLES = 500
EDGE_NEAR_M = 0.005         # a panel edge with nothing else within this and two gaps is open
EDGE_RUN_M = 0.03           # ... reported from this length of run
THROUGH_M = 0.004           # a cabin part this far from anything that would hide it
THROUGH_OPEN = 0.25         # ... at a point that sees the open air in this share of directions
THROUGH_RAYS = 40
THROUGH_SAMPLES = 400
CABIN_MATS = ("interior", "seat", "screen")
CABIN_NAMES = ("interior", "cabin", "seat", "dash")
CORE = ("tire", "rim", "hub", "ring", "disc", "drum", "caliper")


def is_meant(K, check, name):
    """Whether the car said this finding is meant (carkit.meant())."""
    for pat in K.MEANT.get(check, ()):
        if name == pat or (pat.endswith("*") and name.startswith(pat[:-1])):
            return True
    return False


def _mesh_objects(K):
    return [o for o in K.CAR.objects if o.type == 'MESH' and not o.hide_render]


class Shapes:
    """Every mesh object of the car as built, in the car's frame."""

    def __init__(self, K):
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        self.obs = _mesh_objects(K)
        self.verts, self.polys, self.tris = {}, {}, {}
        for ob in self.obs:
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            mw = ob.matrix_world
            self.verts[ob.name] = [mw @ v.co for v in me.vertices]
            self.polys[ob.name] = [tuple(p.vertices) for p in me.polygons]
            self.tris[ob.name] = sum(len(p.vertices) - 2 for p in me.polygons)
            ev.to_mesh_clear()

    def tree(self, names):
        """A BVH of those objects and, by polygon, the object it belongs to."""
        vs, ps, own = [], [], []
        for n in names:
            o = len(vs)
            vs += self.verts[n]
            ps += [tuple(o + i for i in p) for p in self.polys[n]]
            own += [n] * len(self.polys[n])
        return (BVHTree.FromPolygons(vs, ps) if ps else None), own

    def sample(self, name, n):
        vs = self.verts[name]
        return vs[::max(1, len(vs) // n)]


def wheels_of(K, S):
    """As the game packs find them: tire.<tag> standing on the ground on a sideways axle,
    with every object named <kind>.<tag> about the same middle."""
    out = []
    for t in S.obs:
        if not t.name.startswith("tire."):
            continue
        tag = t.name[5:]
        piv = t.matrix_world.translation.copy()
        axle = (t.matrix_world.to_3x3() @ V3((0, 1, 0))).normalized()
        zs = [p.z for p in S.verts[t.name]]
        if abs(axle.y) < 0.98 or not zs or min(zs) > 0.03:
            continue
        mem = [o.name for o in S.obs if o.name.endswith("." + tag)
               and (o.matrix_world.translation - piv).length < 1e-3]
        out.append(dict(tag=tag, pivot=piv, members=mem, tire=t.name))
    return out


def check_tires(K, S, wheels):
    rows, verdict = [], "ok"
    if not wheels:
        return dict(verdict="ok", note="no wheels on the ground (a hover car)", wheels=[])
    front_x = max(w["pivot"].x for w in wheels)
    for w in wheels:
        rest = [o.name for o in S.obs if o.name not in w["members"]]
        tree, own = S.tree(rest)
        pts = S.sample(w["tire"], 4000)
        piv = w["pivot"]

        def nearest(ps):
            best = (1e9, None, None)
            for p in ps:
                loc, _, idx, d = tree.find_nearest(p, 0.3)
                if loc is not None and d < best[0]:
                    best = (d, own[idx], loc)
            return best

        d0, who, where = nearest(pts)
        row = dict(tag=w["tag"], clearance_mm=round(d0 * 1000, 1) if who else None,
                   nearest=who, at=[round(c, 3) for c in where] if where else None,
                   foot_mm=round(min(p.z for p in S.verts[w["tire"]]) * 1000, 1))
        v = "ok"
        if who and d0 < TIRE_TOUCH_M:
            v = "fail"
        elif who and d0 < TIRE_NEAR_M:
            v = "look"
        if abs(row["foot_mm"]) > TIRE_FOOT_M * 1000:
            v = "fail" if row["foot_mm"] < -TIRE_FOOT_M * 1000 else max(v, "look", key=RANK.get)
        if abs(piv.x - front_x) < 0.05:            # the steered pair
            free = 0
            for a in STEER_STEPS:
                hit = False
                for sg in (1, -1):
                    c, s = cos(radians(sg * a)), sin(radians(sg * a))
                    turned = [V3((piv.x + c * (p.x - piv.x) - s * (p.y - piv.y),
                                  piv.y + s * (p.x - piv.x) + c * (p.y - piv.y), p.z))
                              for p in pts[::2]]
                    d, by, _ = nearest(turned)
                    if by and d < TIRE_TOUCH_M:
                        hit = True
                        row.setdefault("steer_hits", by)
                if hit:
                    break
                free = a
            row["steer_deg"] = free
            if free < STEER_WANT and v == "ok":
                v = "look"
        row["verdict"] = v
        if is_meant(K, "tires", w["tag"]):
            row["meant"] = True
        else:
            verdict = max(verdict, v, key=RANK.get)
        rows.append(row)
    return dict(verdict=verdict, wheels=rows)


RANK = {"ok": 0, "look": 1, "fail": 2}


def check_ground(K, S, wheels):
    member = {n for w in wheels for n in w["members"]}
    low = (1e9, None)
    under = []
    for ob in S.obs:
        if ob.name in member or not S.verts[ob.name]:
            continue
        z = min(p.z for p in S.verts[ob.name])
        if z < low[0]:
            low = (z, ob.name)
        if z < -0.002:
            under.append((round(z, 4), ob.name))
    v = "ok"
    if low[1] is not None and is_meant(K, "ground", low[1]):
        pass
    elif low[0] < GROUND_FAIL_M - 0.002:
        v = "fail"
    elif wheels and low[0] < GROUND_LOW_M:
        v = "look"
    out = dict(verdict=v, clearance_mm=round(low[0] * 1000, 1), lowest=low[1],
               under_floor=sorted(under)[:8])
    if not wheels:
        out["note"] = ("stands on the ground on %s" % low[1]) if abs(low[0]) < 0.01 else \
            "floats %.0f mm over the ground" % (low[0] * 1000)
    return out


def check_symmetry(K, S):
    """Objects whose mirror image is off the car, worst first."""
    tree, own = S.tree([o.name for o in S.obs])
    rows = []
    ys = [p.y for vs in S.verts.values() for p in vs]
    off = (min(ys) + max(ys)) / 2
    for ob in S.obs:
        worst, where = 0.0, None
        for p in S.sample(ob.name, SYM_SAMPLES):
            loc, _, _, d = tree.find_nearest(V3((p.x, -p.y, p.z)), 0.5)
            d = 0.5 if loc is None else d
            if d > worst:
                worst, where = d, p
        # a tire's tread and sidewall marks run the same way round on both sides
        if worst > (SYM_TIRE_M if ob.name.startswith("tire") else SYM_M):
            rows.append(dict(object=ob.name, off_mm=round(worst * 1000, 1),
                             at=[round(c, 3) for c in where]))
            if is_meant(K, "symmetry", ob.name):
                rows[-1]["meant"] = True
    rows.sort(key=lambda r: -r["off_mm"])
    real = [r for r in rows if not r.get("meant")]
    v = "ok" if not real and abs(off) < 0.002 else "look"
    return dict(verdict=v, center_off_mm=round(off * 1000, 1), objects=len(real),
                asymmetric=rows[:40])


def _loops(bm, edges):
    """Chains of boundary edges: [[edge, ...]] (each connected run)."""
    left, out = set(edges), []
    by_vert = {}
    for e in edges:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    while left:
        e = left.pop()
        run, stack = [e], [e]
        while stack:
            cur = stack.pop()
            for v in cur.verts:
                for e2 in by_vert[v]:
                    if e2 in left:
                        left.discard(e2)
                        run.append(e2)
                        stack.append(e2)
        out.append(run)
    return out


def check_panels(K, S):
    """Open edges, cutter holes and lost panels of the body pieces build_body made."""
    names = [o.name for o in S.obs]
    tree, own = S.tree(names)
    open_runs, holes, gone = [], [], []
    for piece in K.PIECES.values():
        raw_names = set()
        for pn in piece.raw:
            try:
                raw_names.add(piece.parts[pn].name)
            except (KeyError, ReferenceError):
                pass
        for pn, ob in piece.parts.items():
            try:
                name = ob.name
            except ReferenceError:                  # the car removed it after the build
                continue
            if name not in S.verts or pn in piece.raw:
                continue
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bm.transform(ob.matrix_world)
            bnd = [e for e in bm.edges if len(e.link_faces) == 1]
            # per connected part of the panel, its longest boundary loop is the outline
            for run in _loops(bm, bnd):
                length = sum(e.calc_length() for e in run)
                near_raw, lone = 0.0, []
                near = EDGE_NEAR_M + 2 * piece.gap
                for e in run:
                    mid = (e.verts[0].co + e.verts[1].co) / 2
                    hits = [own[i] for (_, _, i, _) in tree.find_nearest_range(mid, near)
                            if own[i] != name]
                    if not hits:
                        lone.append(e)
                    elif all(h in raw_names for h in hits):
                        near_raw += e.calc_length()
                if lone:
                    # runs of open edges inside this loop
                    for part in _loops(bm, lone):
                        ln = sum(e.calc_length() for e in part)
                        if ln < EDGE_RUN_M:
                            continue
                        c = sum(((e.verts[0].co + e.verts[1].co) / 2 for e in part), V3()) \
                            / len(part)
                        open_runs.append(dict(panel=name, length_mm=round(ln * 1000),
                                              at=[round(x, 3) for x in c],
                                              meant=not piece.closed
                                              or is_meant(K, "panels", name)))
                if near_raw > 0.9 * length and length > 0.05 and _is_inner(bm, run, bnd):
                    c = sum(((e.verts[0].co + e.verts[1].co) / 2 for e in run), V3()) / len(run)
                    holes.append(dict(panel=name, length_mm=round(length * 1000),
                                      at=[round(x, 3) for x in c],
                                      meant=is_meant(K, "panels", name)))
            bm.free()
    open_runs.sort(key=lambda r: -r["length_mm"])
    real = [r for r in open_runs if not r["meant"]]
    v = "fail" if real else ("look" if [h for h in holes if not h["meant"]] else "ok")
    return dict(verdict=v, open_edges=open_runs[:30], open_mm=sum(r["length_mm"] for r in real),
                cutter_holes=holes[:20], pieces={n: dict(closed=p.closed, panels=len(p.parts))
                                                 for n, p in K.PIECES.items()})


def _is_inner(bm, run, bnd):
    """Whether a boundary loop is a hole inside its panel: its connected part of the panel
    has a longer boundary loop (the outline)."""
    seen, stack = set(), [run[0].link_faces[0]]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        for e in f.edges:
            for g in e.link_faces:
                if g not in seen:
                    stack.append(g)
    mine = set(run)
    others = [e for e in bnd if e not in mine and e.link_faces[0] in seen]
    if not others:
        return False
    longest = max(sum(e.calc_length() for e in lp) for lp in _loops(bm, others))
    return longest > sum(e.calc_length() for e in run)


def _dirs(n):
    """n directions spread evenly over the sphere."""
    out = []
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        r = (1 - z * z) ** 0.5
        a = i * 2.399963229728653
        out.append(V3((r * cos(a), r * sin(a), z)))
    return out


def check_through(K, S, wheels):
    """Cabin parts that stand outside the car: points of them from which the open air is
    seen in THROUGH_OPEN of all directions with everything that is not cabin (the skin, the
    glass, the wheels) in the way. A seat under a roof sees none; a tub in a wheel well, a
    liner through a brow or a seat by an open doorway does. Judged by what hides the point,
    so a hull with window holes, a panel built inside out or an open shell does not fool
    it."""
    def cabin(ob):
        mats = [m.name.split(".")[0] for m in ob.data.materials if m]
        return any(m in CABIN_MATS for m in mats) or ob.name.split(".")[0] in CABIN_NAMES

    parts = [ob for ob in S.obs if cabin(ob)]
    rest = [ob.name for ob in S.obs if not cabin(ob)]
    if not parts or not rest:
        return dict(verdict="ok", parts=[], count=0)
    tree, own = S.tree(rest)
    dirs = _dirs(THROUGH_RAYS)
    rows = []
    for ob in parts:
        pts = S.sample(ob.name, THROUGH_SAMPLES)
        n_out, worst, where = 0, 0.0, None
        for p in pts:
            free = sum(1 for d in dirs if tree.ray_cast(p, d)[0] is None)
            if free < THROUGH_OPEN * len(dirs):
                continue
            n_out += 1
            loc, _, _, d = tree.find_nearest(p, 1.0)
            d = 1.0 if loc is None else d
            if d > worst:
                worst, where = d, p
        if n_out >= max(2, 0.01 * len(pts)) and worst >= THROUGH_M:
            rows.append(dict(object=ob.name, out_mm=round(worst * 1000, 1),
                             share=round(n_out / len(pts), 2), at=[round(c, 3) for c in where],
                             meant=is_meant(K, "through", ob.name)))
    rows.sort(key=lambda r: -r["out_mm"])
    real = [r for r in rows if not r["meant"]]
    return dict(verdict="ok" if not real else "look", parts=rows[:30], count=len(real))


def check_triangles(K, S):
    total = sum(S.tris.values())
    top = sorted(S.tris.items(), key=lambda kv: -kv[1])[:8]
    heads = {}
    for n, t in S.tris.items():
        heads[n.split(".")[0]] = heads.get(n.split(".")[0], 0) + t
    groups = sorted(heads.items(), key=lambda kv: -kv[1])[:8]
    return dict(verdict="ok" if total <= TRI_BUDGET else "look", total=total, budget=TRI_BUDGET,
                top=[[n, t] for n, t in top], groups=[[n, t] for n, t in groups])


def run(K, write=True):
    S = Shapes(K)
    wheels = wheels_of(K, S)
    lo, hi = K.car_size()
    car = os.path.splitext(os.path.basename(K._script()))[0]
    out = dict(car=car, size=[round(hi[i] - lo[i], 3) for i in range(3)],
               top_z=round(hi[2], 3), objects=len(S.obs),
               palette={k: (list(v) if isinstance(v, tuple) else v)
                        for k, v in K.USED.items()
                        if k in ("paint", "paint_finish", "paint2", "paint2_finish")},
               tires=check_tires(K, S, wheels), ground=check_ground(K, S, wheels),
               symmetry=check_symmetry(K, S), panels=check_panels(K, S),
               through=check_through(K, S, wheels), triangles=check_triangles(K, S))
    names = ("tires", "ground", "symmetry", "panels", "through", "triangles")
    out["verdict"] = max((out[n]["verdict"] for n in names), key=RANK.get)
    report(out)
    if write:
        os.makedirs(K.ARGS.out, exist_ok=True)
        with open(os.path.join(K.ARGS.out, "check.json"), "w") as f:
            json.dump(out, f, indent=1)
        K.log("wrote " + os.path.join(K.ARGS.out, "check.json"))
    return out


def report(c):
    def line(name, v, text):
        print("CHECK %-9s %-4s  %s" % (name, v, text))

    t = c["tires"]
    if t["wheels"]:
        text = ", ".join("%s %s mm to %s%s" % (
            w["tag"], w["clearance_mm"], w["nearest"],
            (", steers %d deg" % w["steer_deg"]) if "steer_deg" in w else "") for w in t["wheels"])
    else:
        text = t.get("note", "")
    line("tires", t["verdict"], text)
    g = c["ground"]
    line("ground", g["verdict"], "%s mm under %s%s" % (
        g["clearance_mm"], g["lowest"], ("; " + g["note"]) if g.get("note") else ""))
    s = c["symmetry"]
    line("symmetry", s["verdict"], "%d objects not mirrored%s" % (
        s["objects"], (": " + ", ".join("%s %s mm" % (r["object"], r["off_mm"])
                                         for r in s["asymmetric"][:6])) if s["objects"] else ""))
    p = c["panels"]
    real = [r for r in p["open_edges"] if not r["meant"]]
    meant = [r for r in p["open_edges"] if r["meant"]]
    line("panels", p["verdict"], "%d open runs (%d mm)%s, %d on open pieces, %d cutter holes%s" % (
        len(real), p["open_mm"],
        (": " + ", ".join("%s %d mm" % (r["panel"], r["length_mm"]) for r in real[:5]))
        if real else "", len(meant), len(p["cutter_holes"]),
        (": " + ", ".join("%s %d mm" % (r["panel"], r["length_mm"])
                          for r in p["cutter_holes"][:5])) if p["cutter_holes"] else ""))
    th = c["through"]
    line("through", th["verdict"], "%d cabin parts in the open%s" % (
        th.get("count", 0), (": " + ", ".join("%s %s mm" % (r["object"], r["out_mm"])
                                             for r in th["parts"][:6])) if th["parts"] else ""))
    tr = c["triangles"]
    line("triangles", tr["verdict"], "%d of %d; most in %s" % (
        tr["total"], tr["budget"], ", ".join("%s %d" % (n, k) for n, k in tr["groups"][:4])))
    print("CHECK verdict   %s" % c["verdict"])
