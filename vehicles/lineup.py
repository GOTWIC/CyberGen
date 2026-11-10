"""Line-up: every car of vehicles/cars/ in one scene, at one scale, in one render.

    vehicles/blender.sh vehicles/lineup.py                 # docs/progress/AG18/lineup.jpg
    vehicles/blender.sh vehicles/lineup.py --test          # a quick small one, in the cache

A car script empties the scene when it imports the kit, so the cars cannot be built one
after another in one Blender. Each is built once, by its own script with --blend, into
CACHE/<car>/car.blend (CACHE: ~/.cache/cybergen/vehicles/lineup, never in the repo) and
built again only when its script or carkit.py is newer than that file. Those builds are
child Blenders of this one, run one at a time while this one waits, so the whole run is
one job under blender.sh's lock. Each file's CAR collection is then appended under an
empty of the car's name and placed.

Cars are found by listing vehicles/cars/*.py, brands and their order read from
vehicles/BRANDS.md (a car belongs to the brand whose table lists its model, else to the
brand its file name starts with, else to one of its own at the end). One column per brand,
its cars one behind another, lowest in front; rows are spaced so that no car hides the one
behind it from the camera, and every car is turned to show the camera the same
three-quarter view of its nose and left flank. A car that fails to build or append is
left out with a message, and the run goes on.

    --out FILE      the image (default docs/progress/AG18/lineup.jpg)
    --cache DIR     where the cars' .blend files are kept
    --width N       image width in pixels (3840); the height follows the layout, 16:9 at most
    --samples N     Cycles samples (128)
    --test          1920 px, 24 samples, written to CACHE/test.jpg
    --only a,b      only these cars (file names without .py)
    --rebuild       build every car again
    --blend         also save the scene as CACHE/lineup.blend
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time
from math import atan2, cos, pi, sin, tan
from math import radians as rad

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "cybergen", "vehicles", "lineup")


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="blender.sh lineup.py")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "progress", "AG18", "lineup.jpg"))
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--width", type=int, default=3840)
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--blend", action="store_true")
    a = ap.parse_args(argv)
    a.cache = os.path.abspath(a.cache)
    if a.test:
        a.width, a.samples = min(a.width, 1920), min(a.samples, 24)
        a.out = os.path.join(a.cache, "test.jpg")
    a.out = os.path.abspath(a.out)
    return a


A = _args()
# the kit reads its own arguments when imported: give it only what it knows
_argv = sys.argv
sys.argv = (_argv[:_argv.index("--")] if "--" in _argv else list(_argv)) + ["--", "--out", A.cache]
sys.path.insert(0, HERE)
import carkit as K                                  # noqa: E402
from carkit import Geo, V3                          # noqa: E402
from mathutils import Matrix                        # noqa: E402

sys.argv = _argv

TURN = 40.0             # degrees between a car's nose and the line from it to the camera
ELEV = 19.0             # the camera's height over the horizon, seen from the cars
LENS = 105.0
GAP_X = -0.4            # between the columns' boxes, meters: turned cars stand closer than
                        # their boxes (at 40 degrees a nose passes 1.5 m ahead of the next flank)
GAP_Y = 1.6             # the least gap between two rows' boxes
HIDE = 0.8              # share of a car's shadow (height / tan ELEV) kept free behind it
SHEAR = 2.0             # each row stands this far to the right of the one before
LABEL_M = 0.70          # the brand names' letter height
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 0.035, 0.08, 0.05
LINE = bpy.data.collections.new("LINEUP")
K.SCN.collection.children.link(LINE)


# ---------------------------------------------------------------------------------------
# the roster
# ---------------------------------------------------------------------------------------
def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def brands():
    """[key, title, model slugs] per brand of BRANDS.md, in its order."""
    out = []
    with open(os.path.join(HERE, "BRANDS.md")) as f:
        for line in f:
            m = re.match(r"## (.+?)\s*(\(|$)", line)
            if m:
                out.append([_slug(m.group(1).split()[0]), m.group(1), []])
            elif out and line.startswith("|"):
                cell = line.split("|")[1].strip()
                if cell and cell != "Model" and not set(cell) <= set("-: "):
                    out[-1][2].append(_slug(cell))
    return out


def roster():
    """[brand title, [car names]] per brand, in the brand book's order."""
    names = sorted(os.path.splitext(os.path.basename(p))[0]
                   for p in glob.glob(os.path.join(HERE, "cars", "*.py")))
    only = [n for n in A.only.split(",") if n]
    if only:
        names = [n for n in names if n in only]
    book = brands()
    groups = [[title, []] for _, title, _ in book]
    for n in names:
        k = next((i for i, (key, _, models) in enumerate(book)
                  if any(n == m or n == key + "_" + m for m in models)), None)
        if k is None:
            k = next((i for i, (key, _, _) in enumerate(book) if n.split("_")[0] == key), None)
        if k is None:
            title = n.split("_")[0].capitalize()
            k = next((i for i, g in enumerate(groups) if g[0] == title), None)
            if k is None:
                groups.append([title, []])
                k = len(groups) - 1
        groups[k][1].append(n)
    return [g for g in groups if g[1]]


# ---------------------------------------------------------------------------------------
# the cars
# ---------------------------------------------------------------------------------------
def build_car(name):
    """The car's cached .blend, built again when its script or the kit is newer; None
    when there is none to use."""
    script = os.path.join(HERE, "cars", name + ".py")
    out = os.path.join(A.cache, name)
    blend = os.path.join(out, "car.blend")
    newest = max(os.path.getmtime(script), os.path.getmtime(os.path.join(HERE, "carkit.py")))
    if os.path.exists(blend) and os.path.getmtime(blend) >= newest and not A.rebuild:
        return blend
    os.makedirs(out, exist_ok=True)
    t = time.time()
    logf = os.path.join(out, "build.log")
    cmd = [bpy.app.binary_path, "-b", "--python-exit-code", "1", "-P", script, "--",
           "--out", out, "--blend"]
    try:
        with open(logf, "w") as f:
            rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=1800).returncode
    except Exception as e:
        rc = "%s" % e
    if rc == 0 and os.path.exists(blend) and os.path.getmtime(blend) >= t - 1:
        K.log("built %s in %.0f s" % (name, time.time() - t))
        return blend
    if os.path.exists(blend):
        K.log("BUILD FAILED: %s (%s, see %s); its earlier build is used" % (name, rc, logf))
        return blend
    K.log("BUILD FAILED: %s (%s, see %s)" % (name, rc, logf))
    return None


class Car:
    """An appended car: its empty, its box in its own frame and its triangles."""

    def __init__(self, name, blend):
        with bpy.data.libraries.load(blend, link=False) as (src, dst):
            if "CAR" not in src.collections:
                raise RuntimeError("no CAR collection in " + blend)
            dst.collections = ["CAR"]
        coll = dst.collections[0]
        coll.name = "car." + name
        LINE.children.link(coll)
        self.name = name
        self.root = bpy.data.objects.new(name, None)
        LINE.objects.link(self.root)
        obs = list(coll.all_objects)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        lo, hi, self.tris = np.full(3, 1e9), np.full(3, -1e9), 0
        for ob in obs:
            if ob.type != 'MESH':
                continue
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            n = len(me.vertices)
            if n:
                co = np.empty(n * 3, dtype=np.float32)
                me.vertices.foreach_get("co", co)
                co = co.reshape(n, 3) @ np.array(ob.matrix_world.to_3x3()).T \
                    + np.array(ob.matrix_world.translation)
                lo, hi = np.minimum(lo, co.min(axis=0)), np.maximum(hi, co.max(axis=0))
                lt = np.empty(len(me.polygons), dtype=np.int32)
                me.polygons.foreach_get("loop_total", lt)
                self.tris += int(lt.sum()) - 2 * len(lt)
            ev.to_mesh_clear()
        if self.tris == 0:
            raise RuntimeError("no mesh in " + blend)
        for ob in obs:
            if ob.parent is None:
                ob.parent = self.root
        self.lo, self.hi = lo, hi
        self.size = hi - lo
        self.mid = (lo + hi) / 2
        self.yaw = 0.0
        self.at = (0.0, 0.0)

    def extent(self):
        """The box's size across (x) and in depth (y) as turned."""
        c, s = abs(cos(self.yaw)), abs(sin(self.yaw))
        return self.size[0] * c + self.size[1] * s, self.size[0] * s + self.size[1] * c

    def place(self):
        """The box's middle onto self.at, turned by self.yaw."""
        c, s = cos(self.yaw), sin(self.yaw)
        mx, my = self.mid[0], self.mid[1]
        self.root.location = (self.at[0] - (c * mx - s * my), self.at[1] - (s * mx + c * my), 0.0)
        self.root.rotation_euler = (0.0, 0.0, self.yaw)

    def corners(self):
        m = Matrix.Translation(self.root.location) @ Matrix.Rotation(self.yaw, 4, 'Z')
        return [m @ V3((x, y, z)) for x in (self.lo[0], self.hi[0])
                for y in (self.lo[1], self.hi[1]) for z in (self.lo[2], self.hi[2])]


# ---------------------------------------------------------------------------------------
# layout and camera
# ---------------------------------------------------------------------------------------
def lay_out(cols):
    """Columns left to right, rows front (y low) to back; returns the label spots."""
    rows = max(len(c) for c in cols)
    depth = [max(c[r].extent()[1] for c in cols if r < len(c)) for r in range(rows)]
    tall = [max(c[r].size[2] for c in cols if r < len(c)) for r in range(rows)]
    ys, y = [], 0.0
    for r in range(rows):
        if r:
            y += max(GAP_Y, HIDE * tall[r - 1] / tan(rad(ELEV)))
        ys.append(y + depth[r] / 2)
        y += depth[r]
    x, spots = 0.0, []
    for c in cols:
        w = max(car.extent()[0] for car in c)
        for r, car in enumerate(c):
            car.at = (x + w / 2 + SHEAR * r, ys[r])
            car.place()
        spots.append((x + w / 2, ys[0] - c[0].extent()[1] / 2 - 0.5 - LABEL_M / 2))
        x += w + GAP_X
    return spots


class Shot:
    """The camera: far off along one direction, fitted to the points."""

    def __init__(self, width):
        cd = bpy.data.cameras.new("lineup")
        cd.lens, cd.sensor_width, cd.sensor_fit = LENS, 36, 'HORIZONTAL'
        cd.clip_start, cd.clip_end = 1.0, 4000
        self.ob = bpy.data.objects.new("cam.lineup", cd)
        K.STUDIO.objects.link(self.ob)
        e = rad(ELEV)
        self.d = V3((0.0, -cos(e), sin(e)))             # from the target to the camera
        quat = self.d.to_track_quat('Z', 'Y')
        self.ob.rotation_euler = quat.to_euler()
        rm = quat.to_matrix()
        self.right, self.up = rm.col[0].copy(), rm.col[1].copy()
        self.w, self.h = width, width * 9 // 16
        self.tgt, self.dist = V3((0, 0, 0)), 150.0

    def _ranges(self, pts):
        loc = self.tgt + self.d * self.dist
        uv = [((p - loc).dot(self.right) / -(p - loc).dot(self.d),
               (p - loc).dot(self.up) / -(p - loc).dot(self.d)) for p in pts]
        us, vs = [u for u, _ in uv], [v for _, v in uv]
        return min(us), max(us), min(vs), max(vs)

    def fit(self, pts):
        hw = 18.0 / LENS                                 # the frame's half width at distance 1
        for step in range(24):
            u0, u1, v0, v1 = self._ranges(pts)
            if step == 8:       # the frame's shape from the layout's, between 2.7:1 and 16:9
                need = (v1 - v0) / (1 - MARGIN_TOP - MARGIN_BOTTOM) \
                    * (1 - 2 * MARGIN_X) / (u1 - u0)
                self.h = int(self.w * min(max(need, 1 / 2.7), 9 / 16) / 2 + 0.5) * 2
            hh = hw * self.h / self.w
            self.tgt += (self.right * ((u0 + u1) / 2)
                         + self.up * ((v0 + v1) / 2 - hh * (MARGIN_BOTTOM - MARGIN_TOP))) * self.dist
            s = (u1 - u0) / (2 * hw * (1 - 2 * MARGIN_X))
            if step >= 8:
                s = max(s, (v1 - v0) / (2 * hh * (1 - MARGIN_TOP - MARGIN_BOTTOM)))
            self.dist *= s
        self.ob.location = self.tgt + self.d * self.dist
        return self.ob.location


def arrange(cols):
    """Layout and camera settled together: every car turned TURN degrees from its own
    line to the camera, toward the camera's left."""
    shot = Shot(A.width)
    for c in cols:
        for car in c:
            car.yaw = atan2(-cos(rad(TURN)), -sin(rad(TURN)))
    for _ in range(4):
        spots = lay_out(cols)
        pts = [p for c in cols for car in c for p in car.corners()]
        pts += [V3((x + dx, y, 0.0)) for x, y in spots for dx in (-2.5, 2.5)]
        cam = shot.fit(pts)
        for c in cols:
            for car in c:
                to = atan2(cam.y - car.at[1], cam.x - car.at[0])
                car.yaw = to - rad(TURN)
    return shot, spots, pts


# ---------------------------------------------------------------------------------------
# the studio
# ---------------------------------------------------------------------------------------
def studio(shot, pts):
    """A floor and cove wide enough for the cars and the camera, a ceiling of soft light,
    a key from the camera's side, a rim from behind and a low strip for the flanks."""
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    mid = V3(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0.0))
    sx, sy = max(xs) - min(xs), max(ys) - min(ys)
    cam = shot.ob.location
    flat = max((V3((cam.x, cam.y, 0)) - mid).length + 25.0, (sx ** 2 + sy ** 2) ** 0.5 / 2 + 60.0)
    cove, top = 40.0, 90.0
    m, b = K.pbr("lineup_floor", (0.085, 0.085, 0.095), 0.0, 0.45)
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange')
    for k, v in (("From Min", 0.3), ("From Max", 14.0), ("To Min", 0.0), ("To Max", 0.22)):
        mr.inputs[k].default_value = v
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    b.inputs["Emission Color"].default_value = (0.5, 0.5, 0.54, 1)
    nt.links.new(mr.outputs["Result"], b.inputs["Emission Strength"])
    g = Geo()
    prof = [(0.0, 0.01), (0.0, flat)]
    for k in range(1, 13):
        a = (pi / 2) * k / 12
        prof.append((cove * (1 - cos(a)), flat + cove * sin(a)))
    prof.append((top, flat + cove))
    g.lathe(prof, 160, xf=Matrix.Rotation(pi / 2, 4, 'X'), closed=False)
    ob = g.obj("cyc", "lineup_floor", coll=K.STUDIO, loc=mid)
    ob.data.shade_smooth()

    w = bpy.data.worlds.new("world")
    K.SCN.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs["Color"].default_value = (0.5, 0.5, 0.55, 1.0)
    bg.inputs["Strength"].default_value = 0.10

    def area(name, loc, size, e, color=(1, 1, 1), seen=False):
        """A soft box at mid + loc aimed at the middle; e: about the light it gives there
        (the kit's studio gives a car 9 from its top box, 3.6 from its key)."""
        L = bpy.data.lights.new(name, 'AREA')
        L.shape = 'RECTANGLE'
        L.size, L.size_y = size
        d2 = V3(loc).length_squared
        L.energy = e * pi * d2 * max(1.0, size[0] * size[1] / (2.2 * d2))
        L.color = color
        o = bpy.data.objects.new(name, L)
        K.STUDIO.objects.link(o)
        o.location = mid + V3(loc)
        K.aim(o, mid + V3((0, 0, 0.6)))
        o.visible_camera = seen
        return o

    o = area("top", (0.0, 0.0, 14.0), (sx + 2.0, sy + 2.0), 8.0)
    o.data.spread = rad(110.0)          # a pool of light on the cars, the floor dark beyond
    area("key", (-0.30 * sx, -(sy / 2 + 34.0), 30.0), (46.0, 18.0), 5.0, (1.0, 0.97, 0.93))
    area("rim", (0.5 * sx + 30.0, sy / 2 + 22.0, 24.0), (sy + 30.0, 9.0), 3.4, (0.85, 0.92, 1.0))
    o = area("strip", (sx / 2 + 16.0, -(sy / 2 + 10.0), 4.0), (sy + 30.0, 3.0), 2.0)
    o.visible_transmission = False


def labels(titles, spots):
    """The brands' names flat on the floor in front of their columns, quiet."""
    K.pbr("lineup_label", (0.25, 0.25, 0.27), 0.0, 0.45)
    g = Geo()
    for title, (x, y) in zip(titles, spots):
        K.text_flat(g, title.split()[0].upper(), LABEL_M, (x, y, 0.004), (1, 0, 0), (0, 1, 0),
                    spacing=1.35)
    if g.v:
        g.obj("labels", "lineup_label", coll=K.STUDIO)


# ---------------------------------------------------------------------------------------
def main():
    os.makedirs(A.cache, exist_ok=True)
    groups = roster()
    K.log("line-up: %d cars of %d brands" % (sum(len(g[1]) for g in groups), len(groups)))
    cols, titles, skipped = [], [], []
    for title, names in groups:
        col = []
        for n in names:
            blend = build_car(n)
            if blend is None:
                skipped.append(n + " (did not build)")
                continue
            try:
                col.append(Car(n, blend))
            except Exception as e:
                K.log("SKIPPED %s: %s" % (n, e))
                skipped.append("%s (%s)" % (n, e))
        if col:
            col.sort(key=lambda c: (round(float(c.size[2]), 2), c.name))
            cols.append(col)
            titles.append(title)
    if not cols:
        sys.exit("line-up: no car to show")
    cars = [car for c in cols for car in c]
    K.log("appended %d cars, %.2f million triangles" % (len(cars), sum(c.tris for c in cars) / 1e6))
    shot, spots, pts = arrange(cols)
    for t, c in zip(titles, cols):
        K.log("  %-18s %s" % (t, ", ".join("%s %.2f x %.2f x %.2f" % (
            car.name, car.size[0], car.size[1], car.size[2]) for car in c)))
    studio(shot, pts)
    labels(titles, spots)
    K.setup_render()
    K.SCN.render.use_persistent_data = False
    K.SCN.render.resolution_x, K.SCN.render.resolution_y = shot.w, shot.h
    K.SCN.cycles.samples = A.samples
    K.SCN.camera = shot.ob
    K.SCN.render.image_settings.file_format = 'PNG'
    raw = os.path.join(A.cache, "raw_test.png" if A.test else "raw.png")
    K.SCN.render.filepath = raw
    K.log("camera %.0f m away, %d x %d, %d samples" % (shot.dist, shot.w, shot.h, A.samples))
    if A.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(A.cache, "lineup.blend"))
    bpy.ops.render.render(write_still=True)
    K.log("rendered")
    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    py = K._python()
    if py is None:
        K.log("NO PYTHON WITH PIL FOUND (set CYBERGEN_PYTHON): the render without bloom is " + raw)
    else:
        subprocess.run([py, os.path.join(HERE, "post.py"), "bloom", raw, A.out, "0.45", "0.86"],
                       check=True)
        K.log("wrote " + A.out)
    for s in skipped:
        K.log("LEFT OUT: " + s)
    K.log("done: %d cars, %d left out" % (len(cars), len(skipped)))


main()
