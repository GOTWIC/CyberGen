"""cabin: full interiors for the hand-designed vehicles (Blender 5.2, stdlib, bpy and carkit).

A car script imports it after the kit (import carkit as K; import cabin as C: "C", since
some scripts already have a function named cabin), builds its body, glass and wheels as
before, then fits the cabin out. Everything is made as objects named interior.<part>.<what>
in the kit's seat, interior and screen materials and this module's own (materials()), so
the kit's checks and the game packs find the cabin as they did. Frame: x forward, y left,
z up, meters. Guide: vehicles/README.md, "Cabins".

The lining (Cabin.lining)
-------------------------
The body's panels are thin shells: from a seat one would see the back of the outer skin.
The lining is the inner tub that hides it, made from the car as built, for any car:

  - a spine runs along the cabin (the centerline, from x1 - cap to x0 + cap, at the height
    zs). Rays go out from it at the shell (every body piece's panels and wells, every glass
    and frit object): square to the spine along its length, over a half sphere about each
    end. Each ray stops gap short of the skin (the lining's thickness), or 2 mm short of
    clear glass, and is labelled by what it met: skin, well, open (glass) or none.
  - a frit border counts as skin: the lining covers it, so a pillar between two panes is
    lined whole. Where the label changes from solid to open (a window's edge) the place is
    found by bisection and a vertex moved onto it; a reveal runs from there to a knee just
    inside the skin's rolled edge and on to the glass, lap past the edge.
  - wheel wells: a ray that meets a well goes on to the skin behind it (or, out through the
    wheel arch, takes its distance from its neighbors), so the wall runs on smoothly behind
    the well; what of it stands in the well is cut away, and the well gets a cover of its
    own (interior.wells: the well's faces the spine sees, 12 mm in front of them).
  - the plain wall is smoothed (the grid leaves steps where rays graze the shell), then the
    left half is mirrored into one mesh and cut exactly on the cabin's planes: the floor,
    a firewall at x1 (front="wall") and a rear wall at x0 (rear="wall"; rear="body" lets
    the body's own tail close a hatchback or a van). Each cut is filled with a flat face,
    so the floor meets the walls on a straight crease; a rear window is a hole in the rear
    wall's face behind a smoked pane and a frame.
  - faces take a material by what they are: carpet on the floor, the firewall and the well
    covers, headliner over the belt (the side windows' sills) and on what looks down, hard
    trim below; every face looks into the cabin.

Every other part stands on that tub and is held inside the shell: before a part's objects
are made, each vertex that would stand outside the skin or the glass is pressed 4 mm under
it (keep()), and report() names every part that still cuts through it, with where.

The public names
----------------
materials(**colors)        the module's materials (called by Cabin() when a car did not)
SEATS, STYLES              seat kinds; the defaults by brand (seat, wheel, cluster, screen,
                           vents, pulls, grab handles, a seat back's shell, ...)
Cabin(x0, x1, floor, ...)  the cabin: its shell, spine and planes
  .lining(...)             the tub (above); then wall(), roof(), at(), on(), half() and
                           pad() find and dress its surface; room() and keep() measure and
                           hold a point inside the shell
  .seat(hip, kind, ...)    a seat or a bench: upholstery as one subdivided mesh with its
                           inserts and seams in it (cushion, back, bolsters, headrest),
                           base and rails, belts with buckle and reel; returns its hip and
                           eye points
  .dash(...)               the dash across the car from the windshield's base: top pad,
                           brow, fascia, inlay, vents, defrost slots, glovebox, light strip
  .cluster(...)            the driver's display with lit graphics, hooded or free, kept
                           under a raked windshield
  .screen(...)             a center screen with lit graphics
  .wheel(...)              the steering wheel: round, flat-bottomed or a yoke; column, stalks
  .pedals(...)             pedals and a dead pedal
  .console(...)            the tunnel between the seats: armrest, cupholders, selector
  .door(xa, xb, ...)       a door card each side: armrest, pull, release, speaker, switch
                           pack, map pocket, sill plate with lit lettering, light strip
  .sills(xa, xb, ...)      a raised sill each side (a tub car)
  .roof_kit(...)           dome light, sun visors, grab handles, inside mirror
  .mats(...)               floor mats in front of the seats
  .shelf(...)              a parcel shelf or a load floor across the car
  .views(...)              the interior views cab_fwd, cab_side, cab_back, cab_dash and
                           cab_in, with the cabin's own lights (a dome, daylight inside each
                           window) and exposure for them only
  .one_sided               names of what stands on one side only, for K.meant("symmetry")
  .report()                the cabin's triangles by part, and what cuts through the shell
loft(), pill(), rr(), rrd() the small solids the parts are made of, for a car's own parts
"""
import bpy
from mathutils.bvhtree import BVHTree

import carkit as K
from carkit import Geo, Matrix, V3, cos, pi, rad, sin
from math import atan2, ceil, exp, tan

# ---------------------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------------------
COLORS = dict(
    carpet=(0.020, 0.020, 0.022), head=(0.07, 0.07, 0.074), soft=None, trim=(0.10, 0.10, 0.11),
    trim_metal=0.0, trim_rough=0.35, metal=(0.55, 0.56, 0.58), gloss=(0.008, 0.008, 0.010),
    accent=None, piping=None, belt=(0.02, 0.02, 0.022), mat=(0.012, 0.012, 0.013),
    red=(0.55, 0.02, 0.015), light=(1.0, 0.93, 0.82), light_strength=30.0,
    ambient=None, ambient_strength=8.0, graphics=(0.92, 0.95, 1.0), graphics_strength=6.0,
    screen_strength=5.0, warn=(1.0, 0.16, 0.05), pane=(0.05, 0.055, 0.06))


def _weave(m, b, scale, strength):
    """A fine cloth grain: a noise bump."""
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 2.0
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = strength
    bp.inputs["Distance"].default_value = 0.001
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])


def materials(**colors):
    """The cabin's materials beside the kit's interior, seat and screen, in K.MAT; call it
    after K.materials(). Colors (COLORS): carpet, head (headliner and pillars), soft (the
    dash pad and the doors' upper pads; None: the kit's interior color, lighter), trim (the
    fascia inlay and accents), trim_metal, trim_rough, metal, gloss, accent (the seats'
    inserts; None: the seat color, darker), piping (None: the seat color, lighter), belt,
    mat (floor mats), red (buckle buttons), light and light_strength (dome), ambient (the
    light strips; None: the kit's screen color) and ambient_strength, graphics (the
    displays' white) and graphics_strength, screen_strength (the displays' color, the
    kit's screen color), warn, pane (a smoked pane in a rear wall).

    Names: interior.carpet, .head, .soft, .trim, .metal, .gloss, .mat, .light, .ambient;
    seat.accent, seat.piping, seat.belt, seat.red; screen.dark (a display's glass),
    screen.lit (the car's screen color), screen.white, screen.warn; glass.cabin."""
    unknown = set(colors) - set(COLORS)
    if unknown:
        raise KeyError("cabin.materials(): unknown colors %s" % sorted(unknown))
    c = dict(COLORS, **colors)
    used = K.USED or K.PALETTE
    base, seat, scr = used["interior"], used["seat"], used["screen"]
    soft = c["soft"] or tuple(min(1.0, v * 1.4 + 0.006) for v in base)
    accent = c["accent"] or tuple(v * 0.55 for v in seat)
    piping = c["piping"] or tuple(min(1.0, v * 1.6 + 0.02) for v in seat)
    m, b = K.pbr("interior.carpet", c["carpet"], 0.0, 0.95, **{"Specular IOR Level": 0.15})
    _weave(m, b, 900.0, 0.8)
    m, b = K.pbr("interior.head", c["head"], 0.0, 0.9, **{"Specular IOR Level": 0.2})
    _weave(m, b, 1400.0, 0.35)
    m, b = K.pbr("interior.soft", soft, 0.0, 0.62)
    _weave(m, b, 500.0, 0.25)
    K.pbr("interior.trim", c["trim"], c["trim_metal"], c["trim_rough"])
    K.pbr("interior.metal", c["metal"], 1.0, 0.32)
    K.pbr("interior.gloss", c["gloss"], 0.0, 0.08, **{"Coat Weight": 1.0})
    K.pbr("interior.mat", c["mat"], 0.0, 0.7)
    K.pbr("seat.accent", accent, 0.0, 0.6)
    K.pbr("seat.piping", piping, 0.0, 0.5)
    m, b = K.pbr("seat.belt", c["belt"], 0.0, 0.7)
    _weave(m, b, 2200.0, 0.4)
    K.pbr("seat.red", c["red"], 0.0, 0.35)
    K.pbr("screen.dark", (0.004, 0.004, 0.005), 0.0, 0.06, **{"Coat Weight": 1.0})
    K.emit("screen.lit", scr, c["screen_strength"])
    K.emit("screen.white", c["graphics"], c["graphics_strength"])
    K.emit("screen.warn", c["warn"], c["graphics_strength"])
    K.emit("interior.light", c["light"], c["light_strength"])
    K.emit("interior.ambient", c["ambient"] or scr, c["ambient_strength"])
    K.glass("glass.cabin", c["pane"], 1.2)
    return K.MAT


# ---------------------------------------------------------------------------------------
# styles: what a brand's cabin is by default (every call takes its own values over these)
# ---------------------------------------------------------------------------------------
SEATS = {       # width, cushion length, cushion thickness, back height, rake, bolster,
    #             headrest, quilt bars on the back
    "bucket": dict(width=0.47, cushion=0.47, thick=0.065, back=0.60, rake=26, bolster=1.0,
                   headrest="integrated", quilt=4),
    "comfort": dict(width=0.52, cushion=0.50, thick=0.11, back=0.58, rake=22, bolster=0.45,
                    headrest="post", quilt=0),
    "bench": dict(width=1.25, cushion=0.48, thick=0.11, back=0.56, rake=22, bolster=0.25,
                  headrest="post", quilt=0),
    "lounge": dict(width=0.58, cushion=0.54, thick=0.14, back=0.62, rake=29, bolster=0.3,
                   headrest="pillow", quilt=3),
    "jump": dict(width=0.42, cushion=0.36, thick=0.05, back=0.42, rake=12, bolster=0.0,
                 headrest=None, quilt=0),
}
STYLES = {
    "plain": dict(seat="comfort", wheel="round", spokes=3, emblem="ring", cluster="hood",
                  screen="landscape", selector="lever", vents="slat", wrap=0.0, brow=0.035,
                  crown=0.012, inlay=True, grab="loop", pull="bar"),
    # shell: what a seat's back is made of behind (the upholstery when not given)
    # a driver's cockpit: hard edges, the fascia wrapped toward the driver
    "halcyon": dict(seat="bucket", wheel="flat", spokes=3, emblem="hex", cluster="hood",
                    screen="driver", selector="toggle", vents="hex", wrap=0.10, brow=0.05,
                    crown=0.0, inlay=True, grab=None, pull="strap", shell="carbon"),
    # a lounge: soft, few parts
    "orrin": dict(seat="lounge", wheel="round", spokes=2, emblem="dot", cluster="free",
                  screen="float", selector=None, vents="slot", wrap=0.0, brow=0.012,
                  crown=0.02, inlay=False, grab=None, pull="cup"),
    # a truck's cab: steel, switches, grab bars
    "brakk": dict(seat="comfort", wheel="round", spokes=4, emblem="bar", cluster="hood",
                  screen="small", selector="lever", vents="slat", wrap=0.0, brow=0.045,
                  crown=0.0, inlay=True, grab="bar", pull="bar"),
    # a plastic box: cheerful, practical
    "tanager": dict(seat="comfort", wheel="round", spokes=2, emblem="dot", cluster="free",
                    screen="landscape", selector="dial", vents="round", wrap=0.0, brow=0.02,
                    crown=0.015, inlay=True, grab="loop", pull="cup"),
    # a flight deck
    "kestrel": dict(seat="comfort", wheel="yoke", spokes=2, emblem="tri", cluster="free",
                    screen="wide", selector="toggle", vents="slot", wrap=0.06, brow=0.03,
                    crown=0.0, inlay=True, grab="loop", pull="bar"),
    # a formal saloon
    "aurel": dict(seat="lounge", wheel="round", spokes=4, emblem="ring", cluster="hood",
                  screen="landscape", selector="dial", vents="slat", wrap=0.0, brow=0.03,
                  crown=0.01, inlay=True, grab="loop", pull="bar"),
}


# ---------------------------------------------------------------------------------------
# small solids
# ---------------------------------------------------------------------------------------
def rr(w, h, r, n=4):
    """A rounded rectangle's outline (w by h about the origin), counterclockwise from its
    right side: 4 (n + 1) points."""
    r = max(1e-4, min(r, w / 2 - 1e-4, h / 2 - 1e-4))
    out = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(n + 1):
            a = rad(a0 + 90.0 * k / n)
            out.append((cx + r * cos(a), cy + r * sin(a)))
    return out


def rrd(w, h, r, n=4, nu=1, nv=1):
    """rr() with its straight sides split: nu pieces along the top and bottom, nv along
    the left and right; every ring of the same n, nu and nv has as many points."""
    r = max(1e-4, min(r, w / 2 - 1e-4, h / 2 - 1e-4))
    seq = ((w / 2 - r, h / 2 - r, 0, nu), (-w / 2 + r, h / 2 - r, 90, nv),
           (-w / 2 + r, -h / 2 + r, 180, nu), (w / 2 - r, -h / 2 + r, 270, nv))
    out = []
    for i, (cx, cy, a0, ns) in enumerate(seq):
        for k in range(n + 1):
            a = rad(a0 + 90.0 * k / n)
            out.append((cx + r * cos(a), cy + r * sin(a)))
        nx, ny, na, _ = seq[(i + 1) % 4]
        a, b = out[-1], (nx + r * cos(rad(na)), ny + r * sin(rad(na)))
        for k in range(1, ns):
            out.append((a[0] + (b[0] - a[0]) * k / ns, a[1] + (b[1] - a[1]) * k / ns))
    return out


def loft(g, secs, caps=True):
    """A solid through closed sections (lists of points, one length), capped at its ends."""
    n, m = len(secs), len(secs[0])
    vs = [V3(p) for s in secs for p in s]
    fs = [(i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j)
          for i in range(n - 1) for j in range(m)]
    if caps:
        fs += [tuple(range(m)), tuple((n - 1) * m + j for j in range(m))]
    g.add(vs, fs)


def pill(g, c, U, V, w, h, t, r=None, soft=0.35, n=3):
    """A cushion-edged slab: w along U, h along V, t thick along U x V about c, its outline
    rounded by r and its faces' edges by soft (a share of the thickness)."""
    c, U, V = V3(c), V3(U).normalized(), V3(V).normalized()
    N = U.cross(V).normalized()
    r = min(w, h) * 0.25 if r is None else r
    e = min(soft * t / 2, r * 0.9, min(w, h) / 2 * 0.9)
    secs = []
    for z, ins in ((-t / 2, e), (-t / 2 + e, 0.0), (t / 2 - e, 0.0), (t / 2, e)):
        secs.append([c + U * a + V * b + N * z
                     for a, b in rr(w - 2 * ins, h - 2 * ins, max(r - ins, 1e-3), n)])
    loft(g, secs)


def _rot(X, Y, Z):
    return Matrix((V3(X), V3(Y), V3(Z))).transposed()


def _along(L, end=0.05, step=0.04):
    """Shares of a run L long: 0, end, then at most step apart, 1 - end, 1 (sections of a
    loft that follows a curved wall)."""
    n = max(1, int(ceil(L * (1 - 2 * end) / step)))
    return [0.0, end] + [end + (1 - 2 * end) * k / n for k in range(1, n)] + [1 - end, 1.0]


def _smooth(vals, rounds=1):
    v = list(vals)
    for _ in range(rounds):
        v = [v[0]] + [(a + 2 * b + c) / 4 for a, b, c in zip(v, v[1:], v[2:])] + [v[-1]]
    return v


class _Parts:
    """Geos by material for one part; Cabin._emit() makes the objects."""

    def __init__(self):
        self.g = {}

    def __getitem__(self, mat):
        return self.g.setdefault(mat, Geo())


OVERCUT = 0.05          # the lining is cast this far past its planes, then cut on them
PLANES = {"floor", "fire", "rear"}
MAX_REACH = 2.5         # a ray that meets no shell and only a plane this far out is lost

_ADD_CAMERA = [None]


def _camera_hook():
    """A view's own near clip (a cut-away view from outside): carkit's add_camera() is
    wrapped once, for views that carry clip=; every other view is made as before."""
    if _ADD_CAMERA[0] is not None:
        return
    _ADD_CAMERA[0] = K.add_camera

    def add_camera(name, v):
        ob = _ADD_CAMERA[0](name, v)
        if v.get("clip"):
            ob.data.clip_start = v["clip"]
        return ob
    K.add_camera = add_camera


# ---------------------------------------------------------------------------------------
# the cabin
# ---------------------------------------------------------------------------------------
class Cabin:
    """A car's cabin: where it is, and what bounds it.

    x0, x1      the cabin's rear and front ends. With rear="wall" (front="wall") a wall
                stands there (a bulkhead before an engine bay or a boot, a firewall); with
                "body" the body's own end closes the cabin (a hatchback's tail) and x0 (x1)
                is only about where that is.
    floor       the height of the floor's top.
    gap         the lining's thickness: how far inside the skin it stands (0.03). Whatever
                reaches further into the cabin than that under the skin (a deep pocket)
                belongs in shell, or the lining is laid through it.
    detail      0, 1 or 2: the lining's grid (55, 40, 30 mm) and the parts' fineness. A car
                near its triangle budget takes 0.
    style       a name of STYLES (the brand's defaults) or a dict over "plain".
    lhd         the driver sits on the left (y > 0).
    shell       more of the car that bounds the cabin, by object name (names may end in *):
                the body pieces' panels, their wheel wells and every glass and frit object
                are found without it. ignore takes names out.
    open_mats   the materials one sees through (their names' beginnings): the windows. A
                frit border (frit*) counts as skin: the lining covers it, as a car's trim
                covers the black band printed on its glass, so a pillar between two panes
                is lined whole.
    zs, cap     the spine's height and how far its ends stand inside x0 and x1.
    rear_window (half width, z0, z1): a smoked pane in the rear wall.
    name        the objects' prefix; keep "interior" (the checks and the packs read it).
    """

    def __init__(self, x0, x1, floor, front="wall", rear="wall", gap=0.03, detail=1,
                 style="plain", lhd=True, shell=(), ignore=(), open_mats=("glass",),
                 zs=None, cap=None, rear_window=None, name="interior"):
        if "interior.carpet" not in K.MAT:
            materials()
        self.x0, self.x1, self.floor = float(x0), float(x1), float(floor)
        self.front, self.rear = front, rear
        self.gap, self.detail = gap, detail
        self.step = (0.055, 0.04, 0.03)[max(0, min(2, detail))]
        st = style if isinstance(style, dict) else STYLES[style]
        self.st = dict(STYLES["plain"], **st)
        self.lhd, self.sg = lhd, (1.0 if lhd else -1.0)
        self.name = name
        self.open_mats = tuple(open_mats)
        self.rear_window = rear_window
        self.covers = False
        self.one_sided = []
        self.objects = []
        self.seats = []
        self.driver = None
        self.lin = None
        self.dashd = None
        self._shell(shell, ignore)
        self.cap = cap if cap is not None else min(0.45, 0.3 * (self.x1 - self.x0))
        if zs is None:
            xm = (self.x0 + self.x1) / 2
            hit = self.tree.ray_cast(V3((xm, 0, self.floor + 0.25)), V3((0, 0, 1)))
            top = hit[0].z if hit[0] is not None else self.floor + 1.0
            zs = self.floor + 0.52 * (top - self.floor)
        self.zs = zs
        self.A = V3((self.x1 - self.cap, 0, zs))
        self.B = V3((self.x0 + self.cap, 0, zs))
        self.planes = [("floor", V3((0, 0, self.floor)), V3((0, 0, -1)))]
        if front == "wall":
            self.planes.append(("fire", V3((self.x1, 0, 0)), V3((1, 0, 0))))
        if rear == "wall":
            self.planes.append(("rear", V3((self.x0, 0, 0)), V3((-1, 0, 0))))
        self.belt = self.floor + 0.6 * (zs - self.floor) * 2
        _camera_hook()

    # ---- the shell --------------------------------------------------------------------
    def _shell(self, shell, ignore):
        def match(name, pats):
            return any(name == p or (p.endswith("*") and name.startswith(p[:-1])) for p in pats)
        objs, seen = [], set()
        for piece in K.PIECES.values():
            for pn, ob in piece.parts.items():
                try:
                    nm = ob.name
                except ReferenceError:
                    continue
                if pn in piece.raw and "well" not in pn:
                    continue
                objs.append(ob)
                seen.add(nm)
        for ob in K.CAR.objects:
            if ob.type != 'MESH' or ob.name in seen or ob.name.startswith(self.name + "."):
                continue
            mats = [m.name for m in ob.data.materials if m]
            if any(m.startswith(self.open_mats + ("frit",)) for m in mats) or match(ob.name, shell):
                objs.append(ob)
        objs = [o for o in objs if not match(o.name, ignore)]
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        vs, ps, lab = [], [], []
        for ob in objs:
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            o = len(vs)
            mw = ob.matrix_world
            vs += [mw @ v.co for v in me.vertices]
            names = [(m.name if m else "") for m in me.materials] or [""]
            well = "well" in ob.name.split(".")[-1]
            for p in me.polygons:
                mn = names[min(p.material_index, len(names) - 1)]
                ps.append(tuple(o + i for i in p.vertices))
                lab.append("open" if mn.startswith(self.open_mats) else
                           "well" if (well or mn == "well") else "skin")
            ev.to_mesh_clear()
        self.tree = BVHTree.FromPolygons(vs, ps)
        self.flab = lab
        # the shell less its wheel wells (what the lining is cast on: its wall runs on
        # behind a well that comes up into the cabin, which gets a cover of its own)
        keep = [k for k, lb in enumerate(lab) if lb != "well"]
        self.tree_nw = BVHTree.FromPolygons(vs, [ps[k] for k in keep])
        self.flab_nw = [lab[k] for k in keep]
        self.well_vs, self.well_ps = vs, [ps[k] for k, lb in enumerate(lab) if lb == "well"]
        self.shell_names = [o.name for o in objs]

    def _raw(self, o, d, wells=True):
        """The shell along a ray: (point, normal toward the ray's origin, label, distance),
        or None. A ray that slips through a shut line looks again beside it. wells=False:
        the shell without its wheel wells."""
        tree, flab = (self.tree, self.flab) if wells else (self.tree_nw, self.flab_nw)
        loc, n, idx, dist = tree.ray_cast(o, d)
        if loc is None:
            e1 = d.cross(V3((0, 0, 1)) if abs(d.z) < 0.9 else V3((1, 0, 0))).normalized()
            e2 = d.cross(e1)
            for r in (0.008, 0.02):
                for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    loc, n, idx, dist = tree.ray_cast(o, (d + e1 * (a * r) + e2 * (b * r)))
                    if loc is not None:
                        break
                if loc is not None:
                    break
        if loc is None:
            return None
        if n.dot(d) > 0:
            n = -n
        return loc, n, flab[idx], dist

    def _cast(self, o, d):
        """What the lining is along a ray: (distance, label, the point met, its normal)."""
        t, lab, p, nn = 1e9, "none", None, None
        hit = self._raw(o, d)
        if hit is not None and hit[2] == "well" and self.covers:
            # a wheel well in the way: the wall behind it, or (out through the wheel
            # arch) a point lining() fills in from its neighbors
            behind = self._raw(o, d, wells=False)
            if behind is not None and behind[2] != "open":
                hit = behind
            else:
                return max(hit[3] - self.gap, 0.02), "fill", None, None
        if hit is not None:
            loc, n, lb, dist = hit
            if lb == "open":
                t = dist - 0.002
            else:
                g = self.gap * (0.4 if lb == "well" else 1.0)
                t = dist - g / max(abs(n.dot(d)), 0.7)
            lab, p, nn = lb, loc, n
        for name, pp, pn in self.planes:
            dn = d.dot(pn)
            if dn > 1e-6:
                tp = (pp + pn * OVERCUT - o).dot(pn) / dn
                if 0 < tp < t:
                    t, lab, p, nn = tp, name, o + d * tp, -pn
        if lab == "none" or (hit is None and t > MAX_REACH):
            t, lab, p, nn = 0.5, "none", None, None  # out through an opening: no lining
        return max(t, 0.02), lab, p, nn

    def _ray(self, u, v):
        """The lining's parameters: u along the spine (0 the front pole, nc the front end,
        nc + nt the rear end, 2 nc + nt the rear pole), v the angle round it from the top."""
        rd = V3((0, sin(v), cos(v)))
        nc, nt = self.nc, self.nt
        if u <= nc:
            ph = (pi / 2) * (1 - u / nc)
            return self.A, (rd * cos(ph) + V3((sin(ph), 0, 0))).normalized()
        if u >= nc + nt:
            ph = (pi / 2) * min(1.0, (u - nc - nt) / nc)
            return self.B, (rd * cos(ph) - V3((sin(ph), 0, 0))).normalized()
        return self.A.lerp(self.B, (u - nc) / nt), rd

    def _probe(self, u, v):
        o, d = self._ray(u, v)
        t, lab, p, n = self._cast(o, d)
        return o + d * t, lab, p, n, t

    # ---- the lining -------------------------------------------------------------------
    def lining(self, lap=0.008, zone=None, sharp=38, trim="interior", carpet="interior.carpet",
               head="interior.head", wall=None, reveal=None, belt=None, crisp=True,
               wells="cover", smooth=3):
        """The tub (the module's docstring): the object interior.lining, and the wells'
        covers, interior.wells. lap: how far a window's reveal reaches onto its glass
        past the edge. zone(label, point, normal) -> a material name, for a car's own
        choice (None from it: the default). Defaults: carpet on the floor, the firewall
        and the well covers; head on what looks down and over the belt; trim below it;
        wall (else carpet) on a rear wall; reveal (else head or trim by height) round the
        windows. belt: the height where trim gives way to head (the side windows' sills
        when not given). crisp: vertices moved onto the creases between skin and well.
        wells: "cover" (the wall runs on behind a well, which gets a cover) or "line" (the
        lining follows the well as the rays see it, with steps where it hides the wall).
        smooth: rounds of smoothing on the plain wall (0 for none)."""
        step = self.step
        R = 0.7
        self.nt = nt = max(4, int(round((self.A.x - self.B.x) / step)))
        self.nc = nc = max(5, int(round(pi / 2 * R * 0.75 / step)))
        NV = max(12, int(round(pi * R / step)))
        NU = 2 * nc + nt
        P = [[None] * (NV + 1) for _ in range(NU + 1)]
        L = [[None] * (NV + 1) for _ in range(NU + 1)]
        Wp = {}                         # a snapped vertex on an opening: its point on the glass
        Mp = {}                         # ... and the reveal's knee inside the skin's edge
        fixed = set()

        def uv(i, j):
            return float(i), pi * j / NV

        self.covers = wells == "cover"
        T = [[None] * (NV + 1) for _ in range(NU + 1)]
        for i in range(NU + 1):
            for j in range(NV + 1):
                q = self._probe(*uv(i, j))
                P[i][j], L[i][j], T[i][j] = q[0], q[1], q[4]
        # rays that left through a wheel arch: their distance from their neighbors'
        # (the wall goes on behind the well as if the arch were not cut there)
        holes = [(i, j) for i in range(NU + 1) for j in range(NV + 1) if L[i][j] == "fill"]
        if holes:
            for _ in range(200):
                for i, j in holes:
                    nb = [T[a][b] for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                          if 0 <= a <= NU and 0 <= b <= NV and L[a][b] != "none"]
                    if not nb:
                        continue
                    T[i][j] = sum(nb) / len(nb)
            for i, j in holes:
                o, d = self._ray(*uv(i, j))
                P[i][j], L[i][j] = o + d * T[i][j], "skin"
        K.log("cabin: %d x %d rays, %d filled in behind the wheel wells" % (
            NU + 1, NV + 1, len(holes)))

        def is_open(lb):
            return lb in ("open", "none")

        def cross(a, b, same):
            """The share of the way from a to b (parameters) where same() stops holding."""
            lo, hi = 0.0, 1.0
            for _ in range(11):
                mid = (lo + hi) / 2
                if same(self._probe(a[0] + (b[0] - a[0]) * mid, a[1] + (b[1] - a[1]) * mid)[1]):
                    lo = mid
                else:
                    hi = mid
            return lo, hi

        def at(a, b, t):
            return self._probe(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

        def edges():
            for i in range(NU + 1):
                for j in range(NV + 1):
                    if i < NU:
                        yield (i, j), (i + 1, j), True
                    if j < NV and 0 < i < NU:
                        yield (i, j), (i, j + 1), False

        def free(ij, along_u):
            # the poles stay; the centerline's vertices move along it only
            i, j = ij
            if i in (0, NU):
                return False
            return along_u or j not in (0, NV)

        # pass 1: the openings' edges; pass 2: the creases between labels
        for opening in ((True, False) if crisp else (True,)):
            cand = {}
            for a, b, along in edges():
                la, lb = L[a[0]][a[1]], L[b[0]][b[1]]
                if la == lb or a in fixed and b in fixed:
                    continue
                if opening != (is_open(la) != is_open(lb)):
                    continue
                if not opening and ({la, lb} & (PLANES | {"fill"})):
                    continue                    # the planes' creases are cut exactly
                if opening:
                    s, o = (a, b) if not is_open(la) else (b, a)    # solid, open
                    ps, po = uv(*s), uv(*o)
                    lo, hi = cross(ps, po, lambda lb_: not is_open(lb_))
                    ln = max((P[s[0]][s[1]] - P[o[0]][o[1]]).length, 0.012)
                    org, d = self._ray(ps[0] + (po[0] - ps[0]) * lo, ps[1] + (po[1] - ps[1]) * lo)
                    lb_ = max(0.0, lo - 0.006 / ln)
                    back = at(ps, po, lb_)
                    t = back[4] if not is_open(back[1]) else at(ps, po, lo)[4]
                    pos = org + d * t
                    # the reveal's knee: just inside the skin's rolled edge (a panel's rim
                    # reaches 14 mm in), so the reveal hugs it out to the glass
                    mp = None
                    if back[1] in ("skin", "well") and back[2] is not None:
                        ob_, db_ = self._ray(ps[0] + (po[0] - ps[0]) * lb_,
                                             ps[1] + (po[1] - ps[1]) * lb_)
                        mp = back[2] - db_ * min(0.02, self.gap * 0.7)
                    w = at(ps, po, min(1.0, hi + lap / ln))
                    if not is_open(w[1]):
                        w = at(ps, po, hi)
                    wp = None
                    if w[2] is not None and is_open(w[1]):
                        o2, d2 = self._ray(ps[0] + (po[0] - ps[0]) * min(1.0, hi + lap / ln),
                                           ps[1] + (po[1] - ps[1]) * min(1.0, hi + lap / ln))
                        wp = w[2] - d2 * 0.002
                    data = (pos, wp, back[1] if not is_open(back[1]) else L[s[0]][s[1]], mp)
                    fs, fo = lo, 1 - lo
                    first, second = ((s, fs), (o, fo)) if fs <= fo else ((o, fo), (s, fs))
                else:
                    pa, pb = uv(*a), uv(*b)
                    lo, hi = cross(pa, pb, lambda lb_: lb_ == la)
                    qa, qb = at(pa, pb, lo), at(pa, pb, hi)
                    org, d = self._ray(pa[0] + (pb[0] - pa[0]) * lo, pa[1] + (pb[1] - pa[1]) * lo)
                    data = (org + d * min(qa[4], qb[4]), None, la if qa[4] <= qb[4] else lb, None)
                    first, second = ((a, lo), (b, 1 - lo)) if lo <= 0.5 else ((b, 1 - lo), (a, lo))
                for ij, fr in (first, second):
                    if ij in fixed or not free(ij, along):
                        continue
                    if (data[0] - P[ij[0]][ij[1]]).length > 2.5 * step:
                        continue                # a grazing ray: the move would be a spike
                    if ij not in cand or fr < cand[ij][0]:
                        cand[ij] = (fr, data)
                    break
            for ij, (fr, (pos, wp, lb, mp)) in cand.items():
                P[ij[0]][ij[1]] = pos
                fixed.add(ij)
                if opening:
                    Wp[ij] = wp
                    Mp[ij] = mp
                    L[ij[0]][ij[1]] = "edge:" + lb
                else:
                    L[ij[0]][ij[1]] = lb

        # the belt: where the side windows' sills are
        if belt is None:
            zs = sorted(P[i][j].z for (i, j) in Wp
                        if nc <= i <= nc + nt and abs(P[i][j].y) > 0.3 and P[i][j].z > self.floor + 0.3)
            belt = zs[len(zs) // 8] if len(zs) > 8 else self.belt
        self.belt = belt
        self.windows = self._windows([w for w in Wp.values() if w is not None])

        def material(lb, p, n):
            m = zone(lb, p, n) if zone is not None else None
            if m:
                return m
            if lb in ("floor", "well"):
                return carpet
            if lb == "fire":
                return trim
            if lb == "rear":
                return wall or carpet
            if p is None or n is None:
                return trim
            if n.z < -0.5 and p.z > self.belt - 0.05:
                return head
            return head if p.z > self.belt + 0.015 else trim

        idx, verts = {}, []

        def vid(i, j):
            key = (0, 0) if i == 0 else (NU, 0) if i == NU else (i, j)
            if key not in idx:
                idx[key] = len(verts)
                verts.append(P[key[0]][key[1]])
            return idx[key]

        faces, fmat, mats = [], [], []

        def mat_index(name):
            if name not in mats:
                mats.append(name)
            return mats.index(name)

        used = {}
        for i in range(NU):
            for j in range(NV):
                cs = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                solid = [c for c in cs if not is_open(L[c[0]][c[1]])]
                if len(solid) < 3:
                    continue
                f = []
                for c in solid:
                    k = vid(*c)
                    if k not in f:
                        f.append(k)
                if len(f) < 3:
                    continue
                q = self._probe(i + 0.5, pi * (j + 0.5) / NV)
                lb = q[1]
                if is_open(lb):
                    lb = next((L[c[0]][c[1]] for c in solid if not L[c[0]][c[1]].startswith("edge")),
                              L[solid[0][0]][solid[0][1]])
                    lb = lb.split(":")[-1]
                faces.append(tuple(f))
                fmat.append(mat_index(material(lb, q[2], q[3])))
                for a, b in zip(f, f[1:] + f[:1]):
                    used[(min(a, b), max(a, b))] = used.get((min(a, b), max(a, b)), 0) + 1
        # the reveals: from the lining's open edges out to the glass
        n_lin = len(faces)
        back = {v: k for k, v in idx.items()}
        wv = {}
        mid = (self.A + self.B) / 2
        n_rev = 0
        for (a, b), cnt in used.items():
            ka, kb = back[a], back[b]
            if cnt != 1 or Wp.get(ka) is None or Wp.get(kb) is None:
                continue
            for k, key in ((a, ka), (b, kb)):
                if k not in wv:
                    wv[k] = len(verts)
                    verts.append(Wp[key])
            knee = Mp.get(ka) is not None and Mp.get(kb) is not None
            if knee:
                for k, key in ((a, ka), (b, kb)):
                    if ("m", k) not in wv:
                        wv[("m", k)] = len(verts)
                        verts.append(Mp[key])
                quads = [[a, b, wv[("m", b)], wv[("m", a)]],
                         [wv[("m", a)], wv[("m", b)], wv[b], wv[a]]]
            else:
                quads = [[a, b, wv[b], wv[a]]]
            for f in quads:
                c = sum((verts[k] for k in f), V3()) / 4
                nrm = (verts[f[1]] - verts[f[0]]).cross(verts[f[3]] - verts[f[0]])
                if nrm.dot(V3((mid.x if abs(c.x - mid.x) < (self.A.x - self.B.x) / 2 else c.x,
                               0, mid.z)) - c) < 0:
                    f.reverse()
                faces.append(tuple(f))
                fmat.append(mat_index(reveal if reveal else head if c.z > belt - 0.01 else trim))
            n_rev += 1
        ob = self._assemble(verts, faces, fmat, mats, sharp, carpet, trim, wall, n_lin, smooth)
        if self.covers:
            self._well_covers(carpet)
        if self.rear == "wall" and self.rear_window:
            # a smoked pane in the rear wall, behind a frame that covers the hole's edge
            hw, z0, z1 = self.rear_window
            zm = (z0 + z1) / 2
            g = Geo()
            pill(g, (self.x0 - 0.006, 0, zm), (0, 1, 0), (0, 0, 1),
                 2 * hw + 0.03, z1 - z0 + 0.03, 0.005, r=0.02, soft=0.0)
            self._obj(g, "pane", "glass.cabin")
            g = Geo()
            W, Hh = 2 * hw, z1 - z0
            outer = [V3((self.x0 + 0.004, a, zm + b)) for a, b in rr(W + 0.07, Hh + 0.07, 0.045, 4)]
            inner = [V3((self.x0 + 0.004, a, zm + b)) for a, b in rr(W - 0.03, Hh - 0.03, 0.02, 4)]
            m = len(outer)
            lip = [p + V3((0.012, 0, 0)) for p in outer]
            ilip = [p + V3((0.012, 0, 0)) for p in inner]
            back_ = [p + V3((-0.012, 0, 0)) for p in inner]
            vs = outer + lip + ilip + inner + back_
            fs = []
            for a_, b_ in ((0, 1), (1, 2), (2, 3), (3, 4)):
                fs += [(a_ * m + j, a_ * m + (j + 1) % m, b_ * m + (j + 1) % m, b_ * m + j)
                       for j in range(m)]
            g.add(vs, fs)
            self._obj(g, "pane_frame", trim)
        K.log("cabin: lining %d faces a side, %d of them reveals, belt at %.2f" % (
            len(faces), n_rev, self.belt))
        return ob

    def _assemble(self, verts, faces, fmat, mats, sharp, carpet, trim, wall, n_lin=None,
                  smooth=3):
        """The lining object from the left half as cast: mirrored into one mesh, cut on
        each plane (the floor, a firewall, a rear wall) and every cut filled with a flat
        face, so the floor meets the walls on a straight crease, not on the rays' steps;
        a rear window is a hole in the rear wall's face. Faces turned into the cabin."""
        import bmesh
        bm = bmesh.new()
        L = [bm.verts.new(p) for p in verts]
        R = [v if abs(v.co.y) < 1e-7 else bm.verts.new((v.co.x, -v.co.y, v.co.z)) for v in L]
        revs = set()
        for n, (f, k) in enumerate(zip(faces, fmat)):
            for half, rev in ((L, False), (R, True)):
                vs = [half[i] for i in f]
                if rev:
                    vs.reverse()
                if len(set(vs)) < 3:
                    continue
                try:
                    bf = bm.faces.new(vs)
                except ValueError:
                    continue
                bf.material_index = k
                if n_lin is not None and n >= n_lin:
                    revs.add(bf)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0002)
        # smoothed where it is plain wall (not at an opening's edge or its reveal): the
        # rays' grid leaves steps where they graze the shell, and fans round the poles
        if smooth:
            soft = [v for v in bm.verts if not v.is_boundary and v.link_faces
                    and not any(f in revs for f in v.link_faces)]
            for _ in range(smooth):
                bmesh.ops.smooth_vert(bm, verts=soft, factor=0.5, use_axis_x=True,
                                      use_axis_y=True, use_axis_z=True)
            for v in soft:
                v.co = self.keep(v.co, self.gap * 0.5, wells=not self.covers)
        if self.covers:
            # the wall behind a well's cover would run through the wheel: what of it
            # stands half or more inside the well goes (the cover hides the rest)
            inside = {v for v in bm.verts if self.room(v.co) < -0.003}
            gone = [f for f in bm.faces if 2 * sum(v in inside for v in f.verts) >= len(f.verts)]
            if gone:
                bmesh.ops.delete(bm, geom=gone, context='FACES')
        mats = list(mats)

        def mi(name):
            if name not in mats:
                mats.append(name)
            return mats.index(name)
        cuts = []
        for name, pp, pn in self.planes:
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                   plane_co=pp, plane_no=pn, clear_outer=True, dist=1e-6)
            cuts.append((name, pp, pn))
        fills = dict(floor=carpet, fire=carpet, rear=wall or carpet)
        for name, pp, pn in cuts:
            def on(v):
                return abs((v.co - pp).dot(pn)) < 2e-5
            es = [e for e in bm.edges if e.is_boundary and on(e.verts[0]) and on(e.verts[1])]
            if not es:
                continue
            deg = {}
            for e in es:
                for v in e.verts:
                    deg[v] = deg.get(v, 0) + 1
            ends = [v for v, d in deg.items() if d == 1]
            for v in ends:                      # each end joined to its mirror twin
                if v.co.y <= 1e-6:
                    continue
                tw = min(ends, key=lambda u: (u.co - V3((v.co.x, -v.co.y, v.co.z))).length)
                if tw is not v and (tw.co - V3((v.co.x, -v.co.y, v.co.z))).length < 1e-3:
                    e = bm.edges.get((v, tw)) or bm.edges.new((v, tw))
                    es.append(e)
            if name == "rear" and self.rear_window:
                hw, z0, z1 = self.rear_window
                zm = (z0 + z1) / 2
                ring = [bm.verts.new((pp.x, a, zm + b)) for a, b in rr(2 * hw, z1 - z0, 0.03, 3)]
                es += [bm.edges.new((a, b)) for a, b in zip(ring, ring[1:] + ring[:1])]
            r = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=es)
            new = [f for f in r["geom"] if isinstance(f, bmesh.types.BMFace)]
            if name == "rear" and self.rear_window:
                inner = set(ring)               # what scanfill laid over the hole
                hole = [f for f in new if all(v in inner for v in f.verts)]
                bmesh.ops.delete(bm, geom=hole, context='FACES')
                new = [f for f in new if f.is_valid]
            k = mi(fills[name])
            for f in bm.faces:
                c = f.calc_center_median()
                if abs((c - pp).dot(pn)) < 1e-4 and abs(f.normal.dot(pn)) > 0.999:
                    f.material_index = k
        bm.normal_update()
        for f in bm.faces:                       # every face looks into the cabin
            c = f.calc_center_median()
            if f.normal.dot(self._from(c) - c) < 0:
                f.normal_flip()
        me = bpy.data.meshes.new(self.name + ".lining")
        bm.to_mesh(me)
        bm.free()
        for m in mats:
            me.materials.append(K.need(m))
        ob = bpy.data.objects.new(self.name + ".lining", me)
        K.CAR.objects.link(ob)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=rad(sharp))
        self.objects.append(ob)
        vs = [ob.matrix_world @ v.co for v in me.vertices]
        self.lin = BVHTree.FromPolygons(vs, [tuple(p.vertices) for p in me.polygons])
        return ob

    def _well_covers(self, mat, off=0.012):
        """A cover over each wheel well that comes up into the cabin: the well's faces
        the spine sees, 12 mm in front of them, cut on the cabin's planes (the lining's
        wall runs on behind it): interior.wells."""
        import bmesh
        vs, ps = self.well_vs, self.well_ps
        seen = []
        for f in ps:
            c = sum((vs[i] for i in f), V3()) / len(f)
            o = self._from(c)
            d = c - o
            L = d.length
            if L < 1e-6:
                continue
            hit = self.tree.ray_cast(o, d / L)
            wall = self.tree_nw.ray_cast(o, d / L)
            if hit[0] is not None and hit[3] > L - 0.004 and (
                    wall[0] is None or wall[3] - L > self.gap * 0.8):
                seen.append(f)                  # seen, and in front of the lining's wall
        if not seen:
            return None
        bm = bmesh.new()
        idx = {}
        for f in seen:
            for i in f:
                if i not in idx:
                    idx[i] = bm.verts.new(vs[i])
            try:
                bm.faces.new([idx[i] for i in f])
            except ValueError:
                pass
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0005)
        bm.normal_update()
        for f in bm.faces:
            c = f.calc_center_median()
            if f.normal.dot(self._from(c) - c) < 0:
                f.normal_flip()
        bm.normal_update()
        moved = {v: v.normal.normalized() * off for v in bm.verts if v.link_faces}
        for v, dv in moved.items():
            v.co += dv
        for name, pp, pn in self.planes:
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                   plane_co=pp, plane_no=pn, clear_outer=True, dist=1e-6)
        if not bm.faces:
            bm.free()
            return None
        me = bpy.data.meshes.new(self.name + ".wells")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(K.need(mat))
        ob = bpy.data.objects.new(me.name, me)
        K.CAR.objects.link(ob)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=rad(35))
        self.objects.append(ob)
        return ob

    def _windows(self, pts):
        """The openings as the lining found them (points on the glass round each, the left
        half): [(name, middle, normal into the cabin, its long axis, length, height)], one
        each for the windshield ("front"), the rear glass, a glass roof and each side."""
        groups = {}
        for w in pts:
            o = self._from(w)
            d = w - o
            if d.length < 1e-6:
                continue
            d.normalize()
            k = ("front" if d.x > 0.55 else "rear" if d.x < -0.55 else "roof" if d.z > 0.85
                 else "left")
            groups.setdefault(k, []).append(w)
        out = []
        for k, ws in groups.items():
            if len(ws) < 4:
                continue
            if k == "left":
                sides = [("left", ws), ("right", [V3((p.x, -p.y, p.z)) for p in ws])]
            else:
                sides = [(k, ws + [V3((p.x, -p.y, p.z)) for p in ws])]
            for name, ps in sides:
                c = sum(ps, V3()) / len(ps)
                nrm = sum(((self._from(p) - p).normalized() for p in ps), V3()).normalized()
                u = V3((1, 0, 0)) if name in ("left", "right", "roof") else V3((0, 1, 0))
                u = (u - nrm * u.dot(nrm)).normalized()
                v = nrm.cross(u)
                su = 2 * max(abs((p - c).dot(u)) for p in ps) * 0.85
                sv = 2 * max(abs((p - c).dot(v)) for p in ps) * 0.85
                out.append((name, c, nrm, u, max(su, 0.1), max(sv, 0.1)))
        return out

    # ---- the lining's surface, for what stands on it ------------------------------------
    def at(self, o, d):
        """The lining (else the shell: a window) along a ray: (point, normal toward the
        ray's origin), or (None, None)."""
        o, d = V3(o), V3(d).normalized()
        loc, n = None, None
        if self.lin is not None:
            loc, n, _, _ = self.lin.ray_cast(o, d)
        if loc is None:
            hit = self._raw(o, d)
            if hit is None:
                return None, None
            loc, n = hit[0] - d * 0.012, hit[1]
        if n.dot(d) > 0:
            n = -n
        return loc, n

    def wall(self, x, z, side=1):
        """The lining's side wall at (x, z): (point, normal into the cabin); side 1 left."""
        p, n = self.at((x, 0, z), (0, side, 0))
        if p is None:
            p, n = V3((x, side * 0.7, z)), V3((0, -side, 0))
        return p, n

    def roof(self, x, y=0.0):
        """The headliner over (x, y): (point, normal down into the cabin)."""
        p, n = self.at((x, y, self.zs), (0, 0, 1))
        if p is None:
            p, n = V3((x, y, self.zs + 0.5)), V3((0, 0, -1))
        return p, n

    def half(self, x, z):
        """The cabin's half width at (x, z)."""
        return abs(self.wall(x, z, 1)[0].y)

    def on(self, proj, a, b):
        """A point of the lining and its normal by projection: 'y' the left wall at
        (x, z) = (a, b), 'Y' the right; 'z' the roof over (x, y); 'f' the floor under
        (x, y); 'x' the front wall at (y, z); 'X' the rear wall at (y, z)."""
        zs = self.zs
        if proj in ("y", "Y"):
            return self.wall(a, b, 1 if proj == "y" else -1)
        if proj == "z":
            return self.roof(a, b)
        if proj == "f":
            return self.at((a, b, zs), (0, 0, -1))
        xm = (self.x0 + self.x1) / 2
        return self.at((xm, a, b), (1 if proj == "x" else -1, 0, 0))

    def pad(self, g, proj, c, w, h, r=0.02, lift=0.01, edge=0.005, sink=0.006, n=4,
            rings=None, crown=0.0, step=0.04):
        """A raised panel lying on the lining: a rounded rectangle w by h about c in the
        projection proj (on()'s), standing lift over the surface it follows, its rim edge
        wide, its foot sunk sink into the lining; crown lifts its middle more. Every ring of
        it is sampled on the lining at least every step, with rings toward its middle at
        most 6 cm apart (rings: their sizes as shares, to choose them), so a long card
        follows a wall that curves in plan and never cuts across the skin. Its back is
        open, sunk in the lining. The pieces of a door card, a mat, a grille, a plate on the
        headliner. Returns its middle (lifted) and the lining's normal there."""
        c0, n0 = self.on(proj, *c)
        if c0 is None:
            return None
        nu = max(1, int(ceil((w - 2 * r) / step)))
        nv = max(1, int(ceil((h - 2 * r) / step)))
        if rings is None:
            nk = max(1, int(ceil((min(w, h) / 2 - edge) / 0.06)))
            rings = [1 - (i + 1) / (nk + 1) for i in range(nk)]

        def ring(ww, hh, rad_, lf):
            out = []
            for a, b in rrd(ww, hh, rad_, n, nu, nv):
                p, _ = self.on(proj, c[0] + a, c[1] + b)
                if p is None:
                    p = c0
                out.append(p + n0 * lf)
            return out
        R = [ring(w, h, r, -sink), ring(w, h, r, lift - edge * 0.6),
             ring(w - 2 * edge, h - 2 * edge, max(r - edge, 1e-3), lift)]
        for k in rings:
            R.append(ring((w - 2 * edge) * k, (h - 2 * edge) * k, max((r - edge) * k, 1e-3),
                          lift + crown * (1 - k)))
        m = len(R[0])
        vs = [p for rg in R for p in rg]
        fs = [(i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j)
              for i in range(len(R) - 1) for j in range(m)]
        fs.append(tuple((len(R) - 1) * m + j for j in range(m)))
        g.add(vs, fs)
        return c0 + n0 * lift, n0

    # ---- keeping parts inside -----------------------------------------------------------
    def _from(self, p):
        """The spine's nearest point to p: where a ray to p starts, inside the cabin."""
        ab = self.A - self.B
        t = max(0.0, min(1.0, (p - self.B).dot(ab) / max(ab.length_squared, 1e-9)))
        return self.B + ab * t

    def room(self, p, wells=True):
        """How far p stands inside the shell (the skin, the wells, the glass), measured
        on the ray from the spine through it: negative when it is outside. wells=False:
        the shell less its wheel wells."""
        p = V3(p)
        o = self._from(p)
        d = p - o
        L = d.length
        if L < 1e-6:
            return 1.0
        loc, _, _, dist = (self.tree if wells else self.tree_nw).ray_cast(o, d / L)
        return 1.0 if loc is None else dist - L

    def keep(self, p, margin=0.004, wells=True):
        """p, or the point margin inside the shell on the ray from the spine through it
        when p stands closer to it (or outside it). wells=False: the shell less its
        wheel wells (the lining runs on behind them)."""
        p = V3(p)
        o = self._from(p)
        d = p - o
        L = d.length
        if L < 1e-6:
            return p
        d = d / L
        loc, _, _, dist = (self.tree if wells else self.tree_nw).ray_cast(o, d)
        if loc is not None and dist < L + margin:
            return o + d * max(0.0, dist - margin)
        return p

    # ---- objects ----------------------------------------------------------------------
    def _obj(self, g, tag, mat, mirror=False, sharp=40, bevel=0.0, one_sided=False):
        if not g.v:
            return None
        name = "%s.%s" % (self.name, tag)
        ob = g.obj(name, mat, bevel=bevel, mirror=mirror, sharp=None if bevel else sharp)
        self.objects.append(ob)
        if one_sided:
            self.one_sided.append(ob.name)
        return ob

    def _mesh(self, tag, verts, faces, fmat, mats, mirror=False, one_sided=False, keep=True):
        """One object of several materials (fmat: each face's index in mats), its normals
        made consistent and outward as Geo's: interior.<tag>."""
        import bmesh
        vs = [tuple(self.keep(p) if keep else p) for p in verts]
        me = bpy.data.meshes.new("%s.%s" % (self.name, tag))
        me.from_pydata(vs, [], faces)
        for mn in mats:
            me.materials.append(K.need(mn))
        for p, k in zip(me.polygons, fmat):
            p.material_index = k
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(me.name, me)
        K.CAR.objects.link(ob)
        K.finish(ob, mirror=mirror, sharp=40)
        self.objects.append(ob)
        if one_sided:
            self.one_sided.append(ob.name)
        return ob

    def _emit(self, tag, parts, mirror=False, sharp=40, one_sided=False, bevel=None, keep=True):
        """The objects of one part: interior.<tag>.<material's last word>. With keep, every
        vertex is first held inside the shell (keep()): a corner of a part that would
        poke through the skin or the glass is pressed flat under it."""
        out = []
        for mat, g in parts.g.items():
            if keep:
                g.v = [self.keep(p) for p in g.v]
            bv = (bevel or {}).get(mat, 0.0)
            out.append(self._obj(g, "%s.%s" % (tag, mat.split(".")[-1]), mat, mirror, sharp,
                                 bv, one_sided))
        return [o for o in out if o is not None]

    def report(self):
        """The cabin's triangles, by part, and every part that cuts through the shell (the
        skin, the wells, the glass), with where, in the log; returns the triangles."""
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        by, total, clash = {}, 0, []
        for ob in K.CAR.objects:
            if not ob.name.startswith(self.name + ".") or ob.type != 'MESH':
                continue
            me = ob.evaluated_get(dg).to_mesh()
            n = sum(len(p.vertices) - 2 for p in me.polygons)
            mw = ob.matrix_world
            vs = [mw @ v.co for v in me.vertices]
            ps = [tuple(p.vertices) for p in me.polygons]
            # the lining and the well covers run on behind the wells: measured without them
            behind = self.covers and ob.name in (self.name + ".lining", self.name + ".wells")
            hits = (self.tree_nw if behind else self.tree).overlap(
                BVHTree.FromPolygons(vs, ps)) if ps else []
            # a face that meets the shell counts when a point of it (a corner, an edge's
            # middle, its middle) stands outside: one that only grazes a panel's rolled
            # edge at a window does not
            out, worst = set(), (0.0, None)
            for j in sorted({j for _, j in hits}):
                f = [vs[i] for i in ps[j]]
                c = sum(f, V3()) / len(f)
                for p in f + [c] + [a.lerp(b, 0.5) for a, b in zip(f, f[1:] + f[:1])]:
                    rm = self.room(p, wells=not behind)
                    if rm < -0.002:
                        out.add(j)
                        if rm < worst[0]:
                            worst = (rm, p)
            if out:
                p = worst[1]
                clash.append("%s (%d faces, %.0f mm out at %.2f %.2f %.2f)" % (
                    ob.name, len(out), -worst[0] * 1000, p.x, p.y, p.z))
            ob.evaluated_get(dg).to_mesh_clear()
            key = ob.name.split(".")[1]
            by[key] = by.get(key, 0) + n
            total += n
        K.log("cabin: %d triangles: %s" % (total, ", ".join(
            "%s %d" % kv for kv in sorted(by.items(), key=lambda kv: -kv[1]))))
        K.log("cabin: through the shell: %s" % ("; ".join(clash) if clash else "nothing"))
        self.clashes = clash
        return total

    # ---- seats ------------------------------------------------------------------------
    def seat(self, hip, kind=None, places=1, driver=False, tag=None, width=None, cushion=None,
             thick=None, back=None, rake=None, bolster=None, headrest="kind", quilt=None,
             belt="pillar", rails=True, face=1, drop=0.075, tilt=9.0):
        """A seat, from its hip point (the middle of the sitter's hips: about 75 mm over
        the cushion; 0.13 to 0.16 m over the floor in a low car, 0.30 to 0.40 in a tall
        one). kind: "bucket", "comfort", "bench", "lounge" or "jump" (SEATS), each a set of
        the sizes below, which a call may give itself: width, cushion (its length), thick
        (the cushion's), back (its height over the hip, to the shoulders), rake (degrees
        from upright), bolster (0 to 1), headrest ("post", "integrated", "pillow", None),
        quilt (bars across the back's insert). places: sitters across a bench (hip is its
        middle). belt: "pillar" (down the lining beside the seat, where there is lining),
        "seat" (down the back's outer edge) or None. rails: a base and rails to the floor.
        face -1 turns it to look backward. driver=True makes it the driver's (the views'
        eye point, the wheel's and the pedals' place). Returns dict(hip, eye, rake, ...)."""
        kd = dict(SEATS[kind or ("bench" if places > 1 else self.st["seat"])])
        W = width or kd["width"]
        Lc = cushion or kd["cushion"]
        th = thick or kd["thick"]
        bh = back or kd["back"]
        r = rad(kd["rake"] if rake is None else rake)
        bo = kd["bolster"] if bolster is None else bolster
        hr = kd["headrest"] if headrest == "kind" else headrest
        qn = kd["quilt"] if quilt is None else quilt
        if places > 1 and hr == "integrated":
            hr = "post"
        H = V3(hip)
        X, Y, Z = V3((face, 0, 0)), V3((0, face, 0)), V3((0, 0, 1))
        A = X * -sin(r) + Z * cos(r)            # up the back
        N = X * cos(r) + Z * sin(r)             # out of the back
        n = places
        tag = tag or ("seat%d" % len(self.seats))
        bw = min(0.095, 0.2 * W / n)
        hc, hb = 0.010 + 0.040 * bo, 0.012 + 0.07 * bo
        # across the seat: samples, a seam each side of every place's insert (a groove
        # 8 mm wide, 5 mm deep), the bolsters outside them
        pw = W / n
        wi = max(0.06, pw / 2 - bw - 0.004)          # an insert's half width
        mids = [-W / 2 + pw * (k + 0.5) for k in range(n)]
        seams = [c + s * wi for c in mids for s in (-1, 1)]
        GR, DIP = 0.004, 0.005
        m = max(8, int(round(W / (0.05 if self.detail == 0 else 0.032))))
        cross = [-W / 2 + W * i / m for i in range(m + 1)]
        cross = [y for y in cross if all(abs(y - sy) > 0.011 for sy in seams)]
        cross = sorted(set(cross + [sy + d for sy in seams for d in (-GR, 0.0, GR)]))
        grooves = [round(sy, 6) for sy in seams]

        def inside(y, w=W):
            k = w / W
            return any(abs(y - c * k) < wi * k for c in mids)

        def dip(y, w=W):
            return -DIP if round(y * W / w, 6) in grooves else 0.0

        def bump(y, w, h):
            k = w / W
            e = w / 2 - abs(y)
            v = 0.0
            if e < bw * k:
                v = h * sin(pi * max(0.0, e / (bw * k)) ** 0.75)
            for j in range(1, n):
                d = abs(y - (-w / 2 + w * j / n))
                if d < bw * 0.7:
                    v = max(v, h * 0.35 * 0.5 * (1 + cos(pi * d / (bw * 0.7))))
            return v

        tt = tan(rad(tilt))
        xr, xf = -0.15, Lc - 0.15
        xi0, xi1 = xr + 0.09, xf - 0.11              # the cushion's insert, front to back

        def ctop(x, y, w=W):
            z = -drop + tt * x
            if x > xf - 0.07:
                z -= 0.05 * ((x - xf + 0.07) / 0.07) ** 2
            z += bump(y, w, hc) * (1.0 if x < xf - 0.12 else 0.7)
            if xi0 <= x <= xi1:
                z += dip(y, w)
            return z

        def cpt(x, y, z):
            return H + X * x + Y * y + Z * z
        parts = _Parts()
        g = parts["seat"]
        cover = dict(v=[], f=[], m=[])              # the upholstery: one mesh, inserts in it
        mats = ["seat", "seat.accent", self.st.get("shell") or "seat"]

        def lof(secs, mat_of):
            """Quads between closed sections; mat_of(i, j) their material's index; caps."""
            o, ns, nl = len(cover["v"]), len(secs), len(secs[0])
            cover["v"] += [p for s in secs for p in s]
            for i in range(ns - 1):
                for j in range(nl):
                    j2 = (j + 1) % nl
                    cover["f"].append((o + i * nl + j, o + i * nl + j2, o + (i + 1) * nl + j2,
                                       o + (i + 1) * nl + j))
                    cover["m"].append(mat_of(i, j))
            for i in (0, ns - 1):
                cover["f"].append(tuple(o + i * nl + j for j in range(nl)))
                cover["m"].append(0)
        # the cushion: its sections along it, a groove across at each end of the insert
        cx = [xr, xr + 0.035, xr + 0.07] + [xi0 - GR, xi0, xi0 + GR]
        nmid = max(2, int(round((xi1 - xi0) / 0.07)))
        cx += [xi0 + (xi1 - xi0) * k / nmid for k in range(1, nmid)]
        cx += [xi1 - GR, xi1, xi1 + GR, xf - 0.07, xf - 0.035, xf - 0.012, xf]
        cx = sorted(set(round(x, 6) for x in cx))
        secs, ycross = [], []
        for k, x in enumerate(cx):
            w = W * (1.0 if x < xf - 0.03 else 0.985 if x < xf - 0.005 else 0.93)
            zb = -drop - th + tt * min(x, 0.1) + (0.35 * th if k == len(cx) - 1 else 0.0)
            top = [(y * w / W, ctop(x, y * w / W, w)) for y in cross]
            across = x in (round(xi0, 6), round(xi1, 6))
            if across:
                top = [(y, z - (DIP if inside(y, w) else 0.0)) for y, z in top]
            top[0] = (top[0][0], top[0][1] - 0.024)
            top[-1] = (top[-1][0], top[-1][1] - 0.024)
            top[1] = (top[1][0], top[1][1] - 0.006)
            top[-2] = (top[-2][0], top[-2][1] - 0.006)
            loop = top + [(w / 2, zb + 0.02), (w / 2 - 0.025, zb), (-w / 2 + 0.025, zb),
                          (-w / 2, zb + 0.02)]
            secs.append([cpt(x, y, z) for y, z in loop])
        nt = len(cross)

        def cmat(i, j):
            if j >= nt - 1:
                return 0
            xm_ = (cx[i] + cx[i + 1]) / 2
            ym_ = (cross[j] + cross[j + 1]) / 2
            return 1 if xi0 < xm_ < xi1 and inside(ym_) else 0
        lof(secs, cmat)
        # the back: up from under the cushion's rear to the shoulders (and a headrest of
        # its own, integrated), a groove across at each end of the insert and per quilt bar
        Pf = H + X * -0.115
        tb0, tb1 = (0.075, 0.045) if th < 0.08 else (0.12, 0.065)
        sb = -(drop + 0.03) / cos(r)
        integ = hr == "integrated"
        wide = 1.0 if (bo > 0.8 or n > 1) else 0.9
        knots = [(sb, 0.94), (sb + 0.06, 0.97), (0.10, 1.0), (0.22, 1.0), (0.36, (1 + wide) / 2),
                 (bh - 0.09, wide), (bh - 0.025, wide * (0.97 if not integ else 0.92)),
                 (bh, wide * (0.86 if not integ else 0.80))]
        if integ:                                   # a neck, then the head's pad
            knots += [(bh + 0.045, 0.235 / W), (bh + 0.085, 0.275 / W), (bh + 0.20, 0.28 / W),
                      (bh + 0.245, 0.25 / W), (bh + 0.265, 0.19 / W)]

        def wb(s):
            for (s0, w0), (s1, w1) in zip(knots, knots[1:]):
                if s <= s1:
                    t = max(0.0, min(1.0, (s - s0) / max(s1 - s0, 1e-6)))
                    return w0 + (w1 - w0) * t
            return knots[-1][1]
        si0, si1 = 0.03, bh - 0.12                  # the back's insert, bottom to top
        qs = [si0 + (si1 - si0) * (i + 1) / (qn + 1) for i in range(qn)]
        st = [sb, sb + 0.06] + [s for s, _ in knots[2:]]
        nb = max(3, int(round((si1 - si0) / 0.07)))
        st += [si0 + (si1 - si0) * k / nb for k in range(1, nb)]
        for s0 in [si0, si1] + qs:
            st = [s for s in st if abs(s - s0) > GR * 2.5]
            st += [s0 - GR, s0, s0 + GR]
        st = sorted(set(round(s, 6) for s in st))
        across_s = {round(s, 6) for s in [si0, si1] + qs}

        def bfront(s, y, w):
            fade = 1.0 if s < bh - 0.14 else max(0.0, (bh + 0.02 - s) / 0.16) * (1.0 if wide == 1.0 else 0.7)
            v = bump(y, w, hb) * fade + 0.012 * exp(-((s - 0.16) / 0.13) ** 2)
            if si0 <= s <= si1:
                v += dip(y, w)
            return v

        def bpt(s, y, f):
            return Pf + A * s + Y * y + N * f
        secs = []
        for k, s in enumerate(st):
            w = W * wb(s)
            tb = tb0 + (tb1 - tb0) * min(1.0, max(0.0, s / bh))
            if integ and s > bh:
                tb = tb1 * (1.05 if k < len(st) - 1 else 0.6)
            elif k == len(st) - 1:
                tb *= 0.7
            front = [(y * w / W, bfront(s, y * w / W, w)) for y in cross]
            if s in across_s:
                front = [(y, f - (DIP if inside(y, w) else 0.0)) for y, f in front]
            front[0] = (front[0][0], front[0][1] - 0.022)
            front[-1] = (front[-1][0], front[-1][1] - 0.022)
            front[1] = (front[1][0], front[1][1] - 0.006)
            front[-2] = (front[-2][0], front[-2][1] - 0.006)
            loop = front + [(w / 2, -tb * 0.4), (w / 2 - 0.025, -tb), (-w / 2 + 0.025, -tb),
                            (-w / 2, -tb * 0.4)]
            secs.append([bpt(s, y, f) for y, f in loop])

        def bmat(i, j):
            if j >= nt - 1:
                return 2 if nt <= j <= nt + 2 else 0    # its back: the shell
            sm_ = (st[i] + st[i + 1]) / 2
            ym_ = (cross[j] + cross[j + 1]) / 2
            return 1 if si0 < sm_ < si1 and inside(ym_, W * wb(sm_)) else 0
        lof(secs, bmat)
        top_s = st[-1]
        for k in range(n):
            yc = mids[k]
            if hr in ("post", "pillow"):
                hw, hh, ht = (0.27, 0.17, 0.10) if hr == "post" else (0.34, 0.20, 0.12)
                pc = bpt(bh + 0.05 + hh / 2, yc, -0.01)
                pill(g, pc, Y, A, hw, hh, ht, r=0.055, soft=0.8, n=3)
                gm = parts["interior.metal"]
                for sy in (-0.06, 0.06):
                    gm.tube(bpt(bh - 0.04, yc + sy, -tb1 * 0.5), bpt(bh + 0.08, yc + sy, -0.02), 0.006, 8)
            top_s = max(top_s, bh + 0.05 + (0.17 if hr == "post" else 0.2 if hr == "pillow" else 0))
        # base and rails
        gi, gm = parts["interior"], parts["interior.metal"]
        zb = H.z - drop - th
        room = zb - self.floor
        xm = (xr + xf) / 2 + 0.02
        if rails and room > 0.012:
            for sy in ((-0.36, 0.36) if n == 1 else (-0.42, -0.14, 0.14, 0.42)):
                gm.box(V3((H.x + face * xm, H.y + face * sy * W, self.floor + 0.012)),
                       (Lc + 0.08, 0.036, 0.024))
            if room > 0.04:
                gi.box(V3((H.x + face * xm, H.y, self.floor + 0.024 + (room - 0.02) / 2)),
                       (Lc * 0.72, W * 0.8, room - 0.012))
        for sy in (-1, 1):                       # the recliners' covers
            pill(gi, bpt(sb + 0.05, sy * (W / 2 + 0.006), -tb0 * 0.55), X, Z, 0.12, 0.07, 0.02,
                 r=0.03, soft=0.6, n=2)
        # belts
        gb = parts["seat.belt"]
        gr = parts["seat.red"]
        strap = [(-0.023, -0.0012), (0.023, -0.0012), (0.023, 0.0012), (-0.023, 0.0012)]
        places_y = [-W / 2 + W * (k + 0.5) / n for k in range(n)]
        for k, yc in enumerate(places_y):
            wy = H.y + face * yc                 # the place's middle, across the car
            out = 0.0
            if n == 1:
                out = 1.0 if wy > 0.02 else -1.0 if wy < -0.02 else 0.0
            elif k in (0, n - 1):
                out = 1.0 if wy > 0 else -1.0
            pw = W / n
            if belt and out:
                done = False
                xa = H.x - face * (0.20 + 0.52 * sin(r))
                if belt == "pillar" and self.lin is not None:
                    up, nu = self.lin.ray_cast(V3((xa, 0, H.z + 0.56)), V3((0, out, 0)))[:2]
                    lo, nl = self.lin.ray_cast(V3((xa, 0, self.floor + 0.13)), V3((0, out, 0)))[:2]
                    if up is not None and lo is not None and abs(up.y) > abs(wy) + pw / 2 - 0.04:
                        inw = V3((0, -out, 0))
                        pu, pl = up + inw * 0.02, lo + inw * 0.035
                        gb.sweep([pu, pu.lerp(pl, 0.5), pl], strap, up=tuple(inw))
                        gm.ring(pu + inw * 0.004 + Z * 0.012, (0, 1, 0), 0.026, r=0.004, n=16, m=6)
                        gm.box(pu.lerp(pl, 0.42) + inw * 0.004, (0.048, 0.005, 0.05))
                        gi.box(pl + inw * -0.01, (0.075, 0.04, 0.075))
                        done = True
                if not done:                     # down the back's outer edge
                    yo = yc + face * out * (pw / 2 - 0.055) * (1 if face > 0 else 1)
                    path = [bpt(s, yo, bfront(s, yo, W) + 0.006) for s in
                            (bh - 0.03, bh * 0.6, bh * 0.25, 0.02)]
                    gb.sweep(path, strap, up=tuple(N))
                    gm.box(bpt(bh * 0.3, yo, bfront(bh * 0.3, yo, W) + 0.009), (0.005, 0.048, 0.05),
                           rot=_rot(N, Y, A))
            if belt and (out or n > 1):
                # the buckle, inboard of the place
                si = -out if out else 1.0
                yb_ = yc - face * (out if out else -1.0) * (pw / 2 + (0.014 if n == 1 else -0.02))
                b0 = cpt(-0.085, yb_, -drop - 0.03 if n == 1 else ctop(-0.085, yb_) - 0.01)
                tl = _rot(X * cos(rad(25)) + Z * sin(rad(25)), Y, Z * cos(rad(25)) - X * sin(rad(25)))
                gi.box(b0 + Z * 0.035, (0.035, 0.022, 0.085), rot=tl)
                gr.box(b0 + Z * 0.079 + X * -0.018, (0.016, 0.014, 0.004), rot=tl)
                del si
        one = abs(H.y) > 0.02 or driver
        obs = self._emit(tag, parts, one_sided=one)
        obs.append(self._mesh(tag + ".cover", cover["v"], cover["f"], cover["m"], mats,
                              one_sided=one))
        lv = (1, 1, 2)[max(0, min(2, self.detail))]
        for ob in obs:
            if ob.name.endswith((".seat", ".cover")):   # upholstery: its facets rounded off
                md = ob.modifiers.new("soft", 'SUBSURF')
                md.levels = md.render_levels = lv
                ob.data.set_sharp_from_angle(angle=rad(80))
        eye = H + X * (-0.64 * sin(r) + 0.08) + Z * (0.64 * cos(r))
        rec = dict(hip=H, eye=eye, rake=kd["rake"] if rake is None else rake, width=W,
                   places=n, tag=tag, top=(Pf + A * top_s).z, face=face, kind=kind,
                   front=H.x + face * xf, back=(Pf + A * bh).x)
        self.seats.append(rec)
        if driver:
            self.driver = rec
        return rec

    def _drv(self):
        if self.driver is None:
            raise ValueError("cabin: no driver's seat yet: seat(..., driver=True) comes first")
        return self.driver

    # ---- the dash ---------------------------------------------------------------------
    def cowl(self, y, x=None):
        """The windshield's base at y as built: the lowest point of the glass seen from
        inside (None beside the glass)."""
        o = V3((x if x is not None else self.x1 - 0.6, y, self.zs))
        prev = None
        for k in range(-30, 44):
            a = rad(k * 2.0)
            hit = self._raw(o, V3((cos(a), 0, sin(a))))
            if hit is not None and hit[2] == "open" and hit[0].x > o.x:
                if prev is None:
                    return hit[0]
                lo, hi, best = prev, a, hit[0]
                for _ in range(12):
                    mid = (lo + hi) / 2
                    h = self._raw(o, V3((cos(mid), 0, sin(mid))))
                    if h is not None and h[2] == "open":
                        hi, best = mid, h[0]
                    else:
                        lo = mid
                return best
            prev = a
        return None

    def header(self, y, x=None):
        """The windshield's top edge at y as built (None beside the glass)."""
        o = V3((x if x is not None else self.x1 - 0.6, y, self.zs))
        last = None
        for k in range(-10, 88):
            a = rad(k * 2.0)
            hit = self._raw(o, V3((cos(a), 0, sin(a))))
            if hit is not None and hit[2] == "open":
                last = (a, hit[0])
            elif last is not None:
                lo, hi, best = last[0], a, last[1]
                for _ in range(12):
                    mid = (lo + hi) / 2
                    h = self._raw(o, V3((cos(mid), 0, sin(mid))))
                    if h is not None and h[2] == "open":
                        lo, best = mid, h[0]
                    else:
                        hi = mid
                return best
        return last[1] if last else None

    def dash(self, depth=0.40, top=None, fascia=0.13, knee=0.14, brow=None, crown=None,
             wrap=None, vents=None, vent_y=None, inlay=None, glovebox=True, defrost=True,
             strip=True, mat="interior.soft", low_mat="interior", n=None, tuck=0.035):
        """The dash, lofted across the car from the windshield's base as built to the
        lining at each side. depth: from the glass's base at the middle back to the brow;
        top: the brow's height (the glass's base at the middle when not given); fascia: the
        fascia's height under the brow; knee: the lower dash's height under that; brow: how
        far the brow overhangs the fascia; crown: the top pad's rise between glass and
        brow; wrap: how far the fascia comes back toward the sitters at the sides (a
        cockpit). vents: "slat", "round", "hex", "slot" or None, at vent_y (the ys of
        their middles; the outer ends and beside the middle when not given); inlay: a trim
        band on the fascia; glovebox, defrost (slots along the glass), strip (a line of
        light under the brow). Returns and keeps (self.dashd) what the cluster, the screen
        and the console stand on: xd(y) the brow's x, zt its height, face(y, t) a point
        and the outward normal on the fascia (t 0 its top, 1 its foot)."""
        st = self.st
        brow = st["brow"] if brow is None else brow
        crown = st["crown"] if crown is None else crown
        wrap = st["wrap"] if wrap is None else wrap
        vents = st["vents"] if vents is None else vents
        inlay = st["inlay"] if inlay is None else inlay
        b0 = self.cowl(0.0)
        if b0 is None:
            raise ValueError("cabin.dash(): no windshield found from inside")
        zt = b0.z - 0.01 if top is None else top
        xd0 = b0.x - depth
        zf, zl = zt - 0.05 - fascia, zt - 0.05 - fascia - knee
        # the half width the dash must reach: the lining at the brow's height
        ye = max(self.half(xd0 + 0.1, zt - 0.03), self.half(xd0 + 0.25, zt - 0.03),
                 self.half(xd0 + 0.05, zf)) + 0.02
        n = n or (13, 21, 29)[self.detail]
        ys = [-ye + 2 * ye * k / (n - 1) for k in range(n)]
        base, lastb = {}, None
        for y in sorted(ys, key=abs):
            b = self.cowl(y)
            if b is None:
                near = min(base, key=lambda q: abs(q - y)) if base else None
                b = V3((base[near].x, y, base[near].z)) if near is not None else V3((b0.x, y, b0.z))
            base[y] = b
            lastb = b
        del lastb
        bx = _smooth([base[y].x for y in ys], 2)
        bz = _smooth([base[y].z for y in ys], 2)
        xw = (self.x1 - 0.004) if self.front == "wall" else max(bx) + 0.02

        def xd(y):
            return xd0 - wrap * (abs(y) / ye) ** 2

        def profile(k):
            y, x_, z_ = ys[k], bx[k], bz[k]
            d = xd(y)
            zt_ = zt
            return [(x_ + 0.0, z_ - tuck - 0.03), (x_ - 0.004, z_ - tuck),
                    (x_ - 0.02, z_ - 0.014),
                    ((x_ + d) / 2 + 0.03, (z_ - 0.014 + zt_) / 2 + crown),
                    (d + 0.06, zt_ + 0.002), (d + 0.012, zt_ - 0.003), (d, zt_ - 0.018),
                    (d + 0.006, zt_ - 0.034), (d + brow, zt_ - 0.05),
                    (d + brow - 0.012, zf), (d + brow + 0.03, zf - 0.03),
                    (d + brow + 0.085, zl), (min(xw, x_ + 0.02), zl + 0.02)]
        secs, P = [], []
        for k, y in enumerate(ys):
            pr = profile(k)
            sec = []
            for (x, z) in pr:
                yy = y
                if abs(y) > 0.3:
                    lim = self.half(min(x, self.x1 - 0.02), max(z, self.floor + 0.05)) + 0.012
                    yy = max(-lim, min(lim, y))
                sec.append(V3((x, yy, z)))
            secs.append(sec)
            P.append(pr)
        parts = _Parts()
        loft(parts[mat], secs)
        self._emit("dash", parts)

        def at_y(y):
            y = max(ys[0], min(ys[-1], y))
            k = min(n - 2, int((y - ys[0]) / (ys[1] - ys[0])))
            return k, (y - ys[k]) / (ys[1] - ys[0])

        def pt(y, i):
            k, t = at_y(y)
            a, b = P[k][i], P[k + 1][i]
            return V3((a[0] + (b[0] - a[0]) * t, y, a[1] + (b[1] - a[1]) * t))

        def face(y, t):
            """A point of the fascia at y (t 0 under the brow, 1 at its foot), and the
            normal out of it toward the sitters."""
            a, b = pt(y, 8), pt(y, 9)
            up = (a - b).normalized()
            nrm = V3((0, 1, 0)).cross(up)
            if nrm.x > 0:
                nrm = -nrm
            return a.lerp(b, t), nrm, up

        def top_at(y, t):
            """A point of the top pad at y: t 0 at the glass, 1 at the brow."""
            a, m, b = pt(y, 2), pt(y, 3), pt(y, 4)
            return a.lerp(m, t * 2) if t < 0.5 else m.lerp(b, t * 2 - 1)
        self.dashd = dict(xd=xd, zt=zt, zf=zf, zl=zl, ye=ye, face=face, top=top_at, pt=pt,
                          brow=brow, base=b0)
        d = self.dashd
        det = _Parts()
        dy = self._drv()["hip"].y if self.driver else self.sg * 0.36
        # the lower dash in the hard trim: a sheet over the knee roll
        yl = ye - 0.05
        m = 9
        gl = det[low_mat]
        rows = []
        for k in range(m):
            y = -yl + 2 * yl * k / (m - 1)
            rows.append([pt(y, 9) + V3((-0.002, 0, 0)), pt(y, 10) + V3((-0.003, 0, -0.001)),
                         pt(y, 11) + V3((-0.002, 0, -0.003))])
        gl.add([p for r_ in rows for p in r_],
               [(i * 3 + j, i * 3 + j + 1, (i + 1) * 3 + j + 1, (i + 1) * 3 + j)
                for i in range(m - 1) for j in range(2)])
        if inlay:
            gt = det["interior.trim"]
            yi = ye - 0.10
            rows = []
            for k in range(m):
                y = -yi + 2 * yi * k / (m - 1)
                p0, nrm, up = face(y, 0.16)
                p1 = face(y, 0.84)[0]
                rows.append([p0 + nrm * 0.003, p1 + nrm * 0.003])
            gt.add([p for r_ in rows for p in r_],
                   [(i * 2, i * 2 + 1, (i + 1) * 2 + 1, (i + 1) * 2) for i in range(m - 1)])
        if strip:
            det["interior.ambient"].pipe(
                [pt(-ye + 0.06 + 2 * (ye - 0.06) * k / 12, 7) + V3((-0.002, 0, -0.004))
                 for k in range(13)], 0.0025, n=4, up=(1, 0, 0))
        if vents:
            vy = vent_y if vent_y is not None else (-(ye - 0.13), -0.16, 0.16, ye - 0.13)
            gg, gk, gm = det["interior.gloss"], det["interior"], det["interior.metal"]
            for y in vy:
                c, nrm, up = face(y, 0.5)
                sd = up.cross(nrm).normalized()
                R3 = _rot(sd, up, nrm)
                h = min(0.07, fascia * 0.62)
                if vents == "slat":
                    gg.box(c + nrm * 0.004, (0.13, h, 0.006), rot=R3)
                    for i in range(4):
                        gk.box(c + nrm * 0.009 + up * (h * (i - 1.5) / 4.4), (0.122, 0.006, 0.014),
                               rot=_rot(sd, (up + nrm * 0.5).normalized(), nrm))
                    gm.box(c + nrm * 0.012, (0.008, h * 0.9, 0.008), rot=R3)
                elif vents == "slot":
                    gg.box(c + nrm * 0.004, (0.20, 0.022, 0.006), rot=R3)
                    gk.box(c + nrm * 0.008, (0.19, 0.004, 0.01), rot=R3)
                else:
                    seg = 6 if vents == "hex" else 20
                    xf = Matrix.Translation(c + nrm * 0.002) @ _rot(sd, nrm, up).to_4x4()
                    rr_ = h * 0.56
                    gm.lathe([(0.0, rr_ - 0.008), (0.0, rr_), (0.012, rr_ - 0.002), (0.012, rr_ - 0.008)],
                             seg, xf=xf)
                    gg.lathe([(0.0, 0.002), (0.0, rr_ - 0.008), (0.004, rr_ - 0.008), (0.004, 0.002)],
                             seg, xf=xf)
                    for i in range(3):
                        gk.box(c + nrm * 0.008 + up * (rr_ * 0.5 * (i - 1)),
                               (rr_ * (1.5 if i == 1 else 1.15), 0.004, 0.01), rot=R3)
        if defrost:
            gg = det["interior.gloss"]
            for sgn in (-1, 1):
                ya, yb = sgn * 0.08, sgn * (ye - 0.22)
                rows = []
                for k in range(7):
                    y = ya + (yb - ya) * k / 6
                    a, b = top_at(y, 0.12), top_at(y, 0.20)
                    rows.append([a + V3((0, 0, 0.0025)), b + V3((0, 0, 0.0025))])
                gg.add([p for r_ in rows for p in r_],
                       [(i * 2, i * 2 + 1, (i + 1) * 2 + 1, (i + 1) * 2) for i in range(6)])
        if glovebox:
            gg, gm = det["interior.gloss"], det["interior.metal"]
            yc = -dy
            hw = min(0.20, ye - abs(yc) - 0.10)
            if hw > 0.08:
                loop = []
                for k in range(9):
                    y = yc - hw + 2 * hw * k / 8
                    loop.append(pt(y, 10) + V3((-0.005, 0, 0.0)))
                for k in range(9):
                    y = yc + hw - 2 * hw * k / 8
                    loop.append(pt(y, 11) + V3((-0.004, 0, 0.012)))
                gg.pipe(loop, 0.0018, n=4, closed=True, up=(1, 0, 0))
                c = pt(yc, 10).lerp(pt(yc, 11), 0.22)
                gm.box(c + V3((-0.008, 0, 0)), (0.012, 0.09, 0.014))
        self._emit("dash", det, one_sided=True)
        return d

    def _need_dash(self):
        if self.dashd is None:
            raise ValueError("cabin: dash() comes first")
        return self.dashd

    # ---- displays ---------------------------------------------------------------------
    def _display(self, parts, c, right, up, w, h, kind, bezel=0.008, thick=0.014):
        """A display: a bezel, a dark glass and lit graphics on it. kind: "gauges",
        "map", "media" or "bars"."""
        c, right, up = V3(c), V3(right).normalized(), V3(up).normalized()
        nrm = right.cross(up).normalized()
        pill(parts["interior.gloss"], c - nrm * (thick / 2), right, up, w + 2 * bezel,
             h + 2 * bezel, thick, r=0.012, soft=0.3, n=2)
        gd = parts["screen.dark"]
        gd.add([c + right * a + up * b + nrm * 0.0006 for a, b in
                ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))], [(0, 1, 2, 3)])
        lit, white, warn = parts["screen.lit"], parts["screen.white"], parts["screen.warn"]
        o = c + nrm * 0.0012

        def quad(g, a0, b0, a1, b1):
            g.add([o + right * a + up * b for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))],
                  [(0, 1, 2, 3)])

        def arc(g, cx, cy, r0, r1, a0, a1, n):
            for k in range(n):
                p, q = a0 + (a1 - a0) * (k + 0.12) / n, a0 + (a1 - a0) * (k + 0.88) / n
                g.add([o + right * (cx + r_ * cos(rad(a))) + up * (cy + r_ * sin(rad(a)))
                       for a, r_ in ((p, r0), (q, r0), (q, r1), (p, r1))], [(0, 1, 2, 3)])

        def text(g, s, size, x, y):
            K.text_flat(g, s, size, o + right * x + up * y, right, up)
        if kind == "gauges":
            r_ = h * 0.40
            cx = -w * 0.27
            arc(lit, cx, -h * 0.04, r_ * 0.86, r_, 215, 60, 14)
            arc(white, cx, -h * 0.04, r_ * 0.86, r_, 60, -35, 8)
            text(white, "64", h * 0.30, cx, -h * 0.02)
            text(lit, "KM/H", h * 0.075, cx, -h * 0.27)
            cx = w * 0.27
            arc(lit, cx, -h * 0.04, r_ * 0.86, r_, 215, 100, 10)
            arc(warn, cx, -h * 0.04, r_ * 0.86, r_, -5, -35, 3)
            text(white, "71", h * 0.22, cx, 0.0)
            text(lit, "% CELL", h * 0.07, cx, -h * 0.24)
            for k in range(5):                       # the middle: a lane of chevrons
                a = h * (0.26 - 0.11 * k)
                wv = w * (0.018 + 0.006 * k)
                lit.add([o + right * x + up * y for x, y in
                         ((-wv, a - h * 0.035), (0, a), (wv, a - h * 0.035), (0, a - h * 0.02))],
                        [(0, 1, 3), (1, 2, 3)])
            quad(white, -w * 0.07, -h * 0.40, w * 0.07, -h * 0.385)
            text(white, "D", h * 0.11, 0.0, -h * 0.31)
            warn.add([o + right * (w * 0.43 + a) + up * (h * 0.36 + b) for a, b in
                      ((-h * 0.045, -h * 0.04), (h * 0.045, -h * 0.04), (0, h * 0.04))], [(0, 1, 2)])
        elif kind == "bars":
            for k in range(10):
                g = lit if k < 7 else white
                quad(g, -w * 0.42 + k * w * 0.07, -h * 0.30, -w * 0.42 + k * w * 0.07 + w * 0.05,
                     -h * 0.30 + h * (0.14 + 0.03 * k))
            text(white, "64", h * 0.36, w * 0.32, h * 0.12)
            text(lit, "KM/H", h * 0.09, w * 0.32, -h * 0.20)
            quad(white, -w * 0.44, -h * 0.40, w * 0.44, -h * 0.385)
        else:
            # a map: streets, a route, a marker; a strip of tiles and a clock
            mx0, mx1, my0, my1 = -w * 0.46, w * (0.46 if kind == "map" else 0.10), -h * 0.26, h * 0.42
            th = max(0.0012, h * 0.008)
            for k in range(1, 6):
                x = mx0 + (mx1 - mx0) * k / 6
                quad(white, x - th / 2, my0, x + th / 2, my1)
            for k in range(1, 4):
                y = my0 + (my1 - my0) * k / 4
                quad(white, mx0, y - th / 2, mx1, y + th / 2)
            xa, xb = mx0 + (mx1 - mx0) * 2 / 6, mx0 + (mx1 - mx0) * 4 / 6
            ya, yb = my0 + (my1 - my0) / 4, my0 + (my1 - my0) * 3 / 4
            quad(lit, xa - th * 1.6, my0, xa + th * 1.6, yb)
            quad(lit, xa, yb - th * 1.6, xb, yb + th * 1.6)
            quad(lit, xb - th * 1.6, yb, xb + th * 1.6, my1)
            warn.add([o + right * (xa + a) + up * (ya + b) for a, b in
                      ((-h * 0.03, -h * 0.03), (h * 0.03, -h * 0.03), (0, h * 0.045))], [(0, 1, 2)])
            if kind != "map":
                x0 = w * 0.16
                text(white, "18:42", h * 0.15, x0 + w * 0.15, h * 0.30)
                for k in range(3):
                    quad(lit if k == 0 else white, x0, h * (0.10 - 0.13 * k), x0 + w * (0.26 - 0.05 * k),
                         h * (0.10 - 0.13 * k) + h * 0.045)
            for k in range(6):
                x = -w * 0.44 + k * w * 0.155
                g = lit if k == 1 else white
                quad(g, x, -h * 0.43, x + w * 0.10, -h * 0.43 + h * 0.022)
                quad(g, x + w * 0.03, -h * 0.37, x + w * 0.07, -h * 0.33)
        return nrm

    def cluster(self, kind=None, w=0.30, h=0.105, y=None, set_back=0.07, lift=0.0, lean=None,
                graphics="gauges"):
        """The driver's display. kind: "hood" (in a binnacle on the dash's top), "free" (a
        slim panel standing on the dash) or None. w, h: the display's size; y: its middle
        (the driver's); set_back: how far ahead of the brow it stands; lift: higher; lean:
        degrees back from upright (toward the driver's eye when not given). graphics:
        "gauges" or "bars"."""
        kind = self.st["cluster"] if kind is None else kind
        if not kind:
            return None
        d = self._need_dash()
        drv = self._drv()
        y = drv["hip"].y if y is None else y
        base = d["top"](y, 1.0 - min(0.9, set_back / 0.4) * 0.6)
        c = V3((d["xd"](y) + set_back, y, max(base.z, d["zt"]) + h / 2 + 0.014 + lift))
        if lean is None:
            v = drv["eye"] - c
            lean = max(4.0, min(35.0, 90.0 - abs(atan2(v.x, v.z)) * 180 / pi + 0.0))
            lean = 90.0 - (atan2(-v.x, v.z) * 180 / pi) if False else lean
            lean = max(6.0, min(32.0, atan2(v.z, -v.x) * 180 / pi))
        a = rad(lean)
        up = V3((sin(a), 0, cos(a)))                # leaning back, away from the driver
        right = V3((0, -1, 0))
        nr = right.cross(up).normalized()
        # under a raked windshield: back toward the driver and down until its hood's top
        # clears the glass by 15 mm
        for _ in range(40):
            tops = [c + up * (h / 2 + 0.03) + right * (s * (w / 2 + 0.03)) + nr * dn
                    for s in (-1, 1) for dn in (-0.035, 0.06)]
            if min(self.room(p) for p in tops) >= 0.015:
                break
            c = c + V3((-0.012, 0, -0.005))
        parts = _Parts()
        nrm = self._display(parts, c, right, up, w, h, graphics)
        gi = parts["interior.soft"]
        if kind == "hood":
            # a binnacle: a roof and two cheeks reaching toward the driver
            rt = 0.016
            reach = 0.075
            top = c + up * (h / 2 + 0.008 + rt / 2) + nrm * (reach / 2 - 0.02)
            gi.box(top, (w + 0.06, reach + 0.03, rt), rot=_rot(right, nrm, up))
            for sgn in (-1, 1):
                gi.box(c + right * (sgn * (w / 2 + 0.022)) + nrm * (reach / 2 - 0.03) - up * 0.004,
                       (0.016, reach + 0.01, h + 0.03), rot=_rot(right, nrm, up))
            gi.box(c - nrm * 0.03 - up * 0.004, (w + 0.06, 0.03, h + 0.03), rot=_rot(right, nrm, up))
        else:
            parts["interior"].box(c - up * (h / 2 + 0.012) - nrm * 0.012, (0.10, 0.03, 0.03),
                                  rot=_rot(right, nrm, up))
        self._emit("cluster", parts, one_sided=True)
        return c

    def screen(self, kind=None, w=None, h=None, y=0.0, t=0.35, turn=0.0, lean=12.0, out=0.02,
               graphics=None):
        """The center screen. kind: "landscape" (on the fascia), "float" (standing on the
        dash's top), "driver" (on the fascia, turned to the driver), "wide" (a long panel
        under the brow), "small", "portrait" (reaching down to the console) or None. w, h
        its size; y its middle; t where on the fascia (0 top, 1 foot); turn: degrees toward
        the driver; lean: back from upright; out: how far it stands off the fascia."""
        kind = self.st["screen"] if kind is None else kind
        if not kind:
            return None
        d = self._need_dash()
        sizes = dict(landscape=(0.26, 0.15), float=(0.30, 0.17), driver=(0.24, 0.14),
                     wide=(0.56, 0.11), small=(0.16, 0.10), portrait=(0.20, 0.30))
        w0, h0 = sizes[kind]
        w, h = w or w0, h or h0
        if kind == "driver" and not turn:
            turn = 14.0
        p, nrm, up = d["face"](y, t)
        if kind == "float":
            c = V3((d["xd"](y) + 0.05, y, d["zt"] + h / 2 + 0.02))
        elif kind == "portrait":
            c = p + nrm * out - V3((0, 0, h * 0.25))
        else:
            c = p + nrm * out
            c.z = max(c.z, d["zf"] + h / 2 - 0.02)
        a, b = rad(lean), rad(turn) * self.sg
        up = V3((sin(a), 0, cos(a)))
        right = V3((sin(b), -cos(b), 0))
        up = (up - right * up.dot(right)).normalized()
        parts = _Parts()
        nr = self._display(parts, c, right, up, w, h, graphics or ("map" if kind in ("small", "portrait") else "media"))
        parts["interior"].box(c - nr * (0.014 + (out + 0.03) / 2), (min(w * 0.4, 0.12), 0.06, out + 0.05),
                              rot=_rot(right, up, nr))
        self._emit("screen", parts, one_sided=abs(y) > 1e-4 or bool(turn) or True)
        return c

    # ---- controls ---------------------------------------------------------------------
    def wheel(self, at=None, kind=None, r=0.178, tilt=24.0, spokes=None, emblem=None,
              column=0.30, stalks=True, grip="interior.soft"):
        """The steering wheel. at: its middle (0.44 m ahead of the driver's hip and 0.33
        over it when not given); kind: "round", "flat" (a flat bottom) or "yoke"; r its
        radius; tilt: the column's angle from level (20 a sports car, 35 to 45 a van);
        spokes 2, 3 or 4; emblem: "hex", "ring", "dot", "bar", "tri", or a function
        (g, center, right, up, normal) drawing the car's own on the hub in g; column: its
        length toward the dash; stalks behind the rim."""
        st = self.st
        kind = kind or st["wheel"]
        spokes = spokes or st["spokes"]
        emblem = emblem or st["emblem"]
        drv = self._drv()
        H = drv["hip"]
        c = V3(at) if at is not None else H + V3((0.44, 0, 0.33))
        a = rad(tilt)
        ax = V3((-cos(a), 0, sin(a)))               # from the wheel toward the driver
        Yv = V3((0, 1, 0))
        U = Yv.cross(ax).normalized()               # up in the wheel's plane
        parts = _Parts()
        gr, gi, gm = parts[grip], parts["interior"], parts["interior.metal"]
        nseg = (20, 32, 40)[self.detail]
        sec = [(0.016 * cos(2 * pi * k / 10), 0.013 * sin(2 * pi * k / 10)) for k in range(10)]

        def rim_pt(ph):
            rr_ = r
            if kind == "flat":
                d = abs(((ph - pi + pi) % (2 * pi)) - pi)
                if d < rad(42):
                    rr_ = r * cos(rad(42)) / cos(d)
            return c + (Yv * sin(ph) + U * cos(ph)) * rr_
        if kind == "yoke":
            pts = [(-r, 0.075), (-r, -0.03), (-r + 0.035, -0.085), (r - 0.035, -0.085),
                   (r, -0.03), (r, 0.075)]
            pts = K.chaikin([V3((p[0], p[1], 0)) for p in pts], 2)
            path = [c + Yv * p.x + U * p.y for p in pts]
            gr.sweep(path, sec, up=tuple(ax))
            for p in (path[0], path[-1]):
                gr.lathe([(-0.016, 0.0005), (-0.016, 0.014), (0.016, 0.014), (0.016, 0.0005)], 8,
                         axis=tuple(U), at=tuple(p))
        else:
            gr.sweep([rim_pt(2 * pi * k / nseg) for k in range(nseg)], sec, up=tuple(ax), closed=True)
        hub = c - ax * 0.035
        hw, hh = (0.15, 0.10) if kind != "yoke" else (0.17, 0.085)
        pill(gi, hub + ax * 0.012, Yv, U, hw, hh, 0.05, r=0.03, soft=0.5, n=3)
        angs = {2: (90, 270), 3: (90, 270, 180), 4: (62, 118, 242, 298)}[spokes]
        if kind == "yoke":
            angs = (90, 270)
        for ang in angs:
            ph = rad(ang)
            tip = rim_pt(ph) if kind != "yoke" else c + Yv * (sin(ph) * r) + U * -0.01
            root = hub + ax * 0.012 + (Yv * sin(ph) + U * cos(ph)) * (hw * 0.36 if abs(sin(ph)) > 0.5 else hh * 0.36)
            dirn = (tip - root).normalized()
            sdv = ax.cross(dirn).normalized()
            w0, w1 = (0.05, 0.034) if abs(sin(ph)) > 0.5 else (0.04, 0.03)
            sq = [[p + sdv * (sx * wd) + ax * (sz * 0.007) for sx, sz in
                   ((-1, -1), (1, -1), (1, 1), (-1, 1))] for p, wd in ((root, w0 / 2), (tip, w1 / 2))]
            loft(gi, sq)
            if abs(sin(ph)) > 0.5:                   # a switch pod on a side spoke
                pc = root.lerp(tip, 0.42) + ax * 0.009
                parts["interior.gloss"].box(pc, (0.03, 0.03, 0.006), rot=_rot(dirn, sdv, ax))
                parts["screen.lit"].box(pc + ax * 0.0035, (0.006, 0.014, 0.001), rot=_rot(dirn, sdv, ax))
        # the emblem on the hub
        ec = hub + ax * 0.0385
        if callable(emblem):
            emblem(gm, ec, -Yv, U, ax)
        elif emblem == "hex" or emblem == "ring":
            xf = Matrix.Translation(ec) @ _rot(Yv.cross(ax) * -1, ax, Yv).to_4x4()
            seg = 6 if emblem == "hex" else 20
            gm.lathe([(0.0, 0.013), (0.0, 0.019), (0.003, 0.018), (0.003, 0.014)], seg, xf=xf)
            gm.lathe([(0.0, 0.001), (0.0, 0.006), (0.003, 0.005), (0.003, 0.001)], seg, xf=xf)
        elif emblem == "dot":
            xf = Matrix.Translation(ec) @ _rot(Yv.cross(ax) * -1, ax, Yv).to_4x4()
            gm.lathe([(0.0, 0.001), (0.0, 0.016), (0.004, 0.012), (0.004, 0.001)], 20, xf=xf)
        elif emblem == "bar":
            for k in (-1, 0, 1):
                gm.box(ec + U * (k * 0.011), (0.004, 0.05 - abs(k) * 0.014, 0.005), rot=_rot(ax, Yv, U))
        elif emblem == "tri":
            pts = [ec + Yv * (0.02 * sin(rad(t))) + U * (0.02 * cos(rad(t))) for t in (0, 120, 240)]
            gm.prism(pts, tuple(ax * 0.003))
        # the column, its shroud and stalks
        gi.tube(hub, hub - ax * column, 0.028, 12)
        pill(gi, hub - ax * 0.11, Yv, ax, 0.10, 0.13, 0.085, r=0.03, soft=0.5, n=2)
        if stalks:
            for sgn in (-1, 1):
                p0 = hub - ax * 0.085 + Yv * (sgn * 0.045)
                p1 = hub - ax * 0.05 + Yv * (sgn * 0.165) + U * 0.012
                gi.tube(p0, p1, 0.007, 8)
                gi.tube(p1 - (p1 - p0).normalized() * 0.035, p1, 0.011, 8)
        self._emit("wheel", parts, one_sided=True, sharp=62)    # the rim round, not an octagon
        self.wheeld = dict(center=c, axis=ax, r=r)
        return c

    def pedals(self, x=None, n=2, y=None, dead=True):
        """Pedals at the firewall: n 2 (brake, accelerator) or 3 (a clutch), about the
        driver's middle y, their faces at x (0.86 m ahead of the hip, held inside the
        firewall); dead: a dead pedal toward the door."""
        drv = self._drv()
        H = drv["hip"]
        x = min(self.x1 - 0.09, H.x + 0.86) if x is None else x
        y = H.y if y is None else y
        sg = 1.0 if y >= 0 else -1.0
        parts = _Parts()
        gm, gi, gr = parts["interior.metal"], parts["interior"], parts["interior.mat"]
        fz = self.floor
        a = rad(52)
        R3 = _rot((0, 1, 0), (cos(a), 0, sin(a)), (-sin(a), 0, cos(a)))
        up = V3((cos(a), 0, sin(a)))
        nr = V3((-sin(a), 0, cos(a)))
        # (offset across from the driver's middle, toward the car's middle negative; width; height; center height)
        spec = [(-0.105, 0.05, 0.16, 0.115), (0.0, 0.085, 0.065, 0.16)]
        if n > 2:
            spec.append((0.12, 0.07, 0.06, 0.16))
        for dyv, w, h, cz in spec:
            c = V3((x, y - sg * dyv * -1 if False else y + sg * dyv, fz + cz))
            gm.box(c, (w, h, 0.01), rot=R3)
            for k in range(3):
                gr.box(c + nr * 0.006 + up * (h * (k - 1) * 0.3), (w * 0.86, 0.008, 0.004), rot=R3)
            if h < 0.1:
                gi.tube(c - nr * 0.004, V3((min(self.x1 - 0.02, x + 0.07), c.y, fz + cz + 0.20)), 0.008, 6)
            else:
                gi.box(V3((x + 0.02, c.y, fz + 0.012)), (0.05, w * 0.8, 0.024))
        if dead:
            yd = y + sg * 0.215
            lim = self.half(x - 0.02, fz + 0.12) - 0.05
            yd = sg * min(abs(yd), lim)
            c = V3((x + 0.01, yd, fz + 0.12))
            gm.box(c, (0.075, 0.20, 0.008), rot=R3)
            for k in range(4):
                gr.box(c + nr * 0.005 + up * (0.2 * (k - 1.5) * 0.22), (0.065, 0.008, 0.004), rot=R3)
        self._emit("pedals", parts, one_sided=True)
        return x

    def console(self, x0=None, x1=None, w=0.20, h=0.20, rise=None, armrest=True, cups=2,
                selector="style", switches=4, mat="interior", top="interior.trim", y=0.0):
        """The console between the front seats: a tunnel from the dash back to x0 (behind
        the front hips when not given), w wide, its top h over the floor, rising to the
        fascia's foot at the dash (rise: the height it meets the dash at). armrest: a pad
        at its rear; cups: cupholders; selector: "lever", "dial", "toggle" or None;
        switches: a row of them. top: the material of its top plate."""
        d = self._need_dash()
        selector = self.st["selector"] if selector == "style" else selector
        hx = self.driver["hip"].x if self.driver else (self.x0 + self.x1) / 2
        x0 = hx - 0.30 if x0 is None else x0
        x1 = d["xd"](y) + d["brow"] + 0.05 if x1 is None else x1
        fz = self.floor
        zt = fz + h
        zr = (d["zf"] + 0.02) if rise is None else rise
        parts = _Parts()
        g = parts[mat]
        L = x1 - x0
        secs = []
        for t in (0.0, 0.03, 0.2, 0.45, 0.62, 0.8, 0.93, 1.0):
            x = x0 + L * t
            z = zt if t < 0.62 else zt + (zr - zt) * ((t - 0.62) / 0.38) ** 1.4
            ww = w * (0.9 if t == 0 else 1.0) * (1.0 if t < 0.8 else 1.0 + 0.25 * (t - 0.8) / 0.2)
            zz = z - (0.02 if t == 0 else 0.0)
            secs.append([V3((x, y + a, fz - 0.01 + (b + 0.5) * (zz - fz + 0.01)))
                         for a, b in rr(ww, 1.0, 0.12, 3)])
        loft(g, secs)
        # the top plate
        gt = parts[top]
        xa, xb = x0 + L * 0.30, x0 + L * 0.62
        pill(gt, (((xa + xb) / 2), y, zt + 0.002), (1, 0, 0), (0, 1, 0), xb - xa, w * 0.82, 0.006,
             r=0.02, soft=0.3, n=2)
        gm, gg = parts["interior.metal"], parts["interior.gloss"]
        if armrest:
            pill(parts["seat"], (x0 + L * 0.15, y, zt + 0.03), (1, 0, 0), (0, 1, 0), L * 0.28, w * 0.9,
                 0.06, r=0.035, soft=0.7, n=3)
        xc = xa + 0.055
        for k in range(cups):
            cy = y + (k - (cups - 1) / 2) * 0.092
            gm.ring((xc, cy, zt + 0.006), 'z', 0.038, sec=(0.006, 0.005), n=20)
            gg.cyl((xc, cy, zt + 0.0045), 0.002, 0.0355, n=20)
        xs = xb - 0.07
        if selector == "lever":
            pill(parts["interior.soft"], (xs, y, zt + 0.02), (1, 0, 0), (0, 1, 0), 0.10, 0.08, 0.04,
                 r=0.03, soft=0.9, n=3)
            gm.tube((xs, y, zt + 0.03), (xs - 0.012, y, zt + 0.105), 0.007, 8)
            pill(parts["interior.soft"], (xs - 0.014, y, zt + 0.125), (1, 0, 0), (0, 1, 0), 0.05, 0.045, 0.05,
                 r=0.02, soft=0.9, n=3)
        elif selector == "dial":
            gm.lathe([(0.0, 0.002), (0.0, 0.034), (0.022, 0.03), (0.026, 0.024), (0.026, 0.002)], 24,
                     axis='z', at=(xs, y, zt + 0.004))
            parts["interior.ambient"].ring((xs, y, zt + 0.0065), 'z', 0.038, sec=(0.003, 0.004), n=24)
        elif selector == "toggle":
            gg.box((xs, y, zt + 0.008), (0.085, 0.06, 0.008))
            gm.box((xs, y, zt + 0.03), (0.022, 0.04, 0.045), rot=Matrix.Rotation(rad(-14), 3, 'Y'))
            parts["screen.lit"].box((xs + 0.031, y, zt + 0.0125), (0.012, 0.03, 0.001))
        if switches:
            xw = xb - 0.155 if selector else xb - 0.05
            for k in range(switches):
                cy = y + (k - (switches - 1) / 2) * 0.034
                gg.box((xw, cy, zt + 0.009), (0.03, 0.024, 0.01))
                parts["screen.white" if k else "screen.warn"].box((xw + 0.006, cy, zt + 0.0145),
                                                                 (0.004, 0.012, 0.001))
        self._emit("console", parts, one_sided=abs(y) > 1e-4)
        return dict(x0=x0, x1=x1, top=zt, w=w)

    # ---- doors and sills --------------------------------------------------------------
    def door(self, xa, xb, tag="door", z0=None, arm=None, pull=None, speaker=True, pocket=True,
             switches=True, sill=True, sill_text=None, strip=True, upper="interior.soft",
             card="interior", release=True, lift=0.012):
        """A door card on each side between xa (rear) and xb (front): a raised card from
        z0 (just over the floor) to the belt, a soft upper pad, an armrest at the height
        arm (0.24 under the belt when not given) with a pull (pull: "bar", "strap", "cup"
        or None), a release lever, a speaker grille, a switch pack on the armrest, a map
        pocket, a sill plate with lit lettering (sill_text) and a light strip under the
        upper pad. Built on the left wall and mirrored."""
        pull = self.st["pull"] if pull is None else pull
        xa, xb = min(xa, xb), max(xa, xb)
        L = xb - xa
        z0 = self.floor + 0.05 if z0 is None else z0
        zt = self.belt - 0.03
        arm = max(z0 + 0.14, self.belt - 0.24) if arm is None else arm
        parts = _Parts()
        xm = (xa + xb) / 2
        # the card and its soft upper pad
        self.pad(parts[card], 'y', (xm, (z0 + zt) / 2), L - 0.04, zt - z0, r=0.03, lift=lift,
                 n=3, rings=(0.72, 0.4))
        zu = arm + 0.045
        if zt - zu > 0.06:
            self.pad(parts[upper], 'y', (xm, (zu + zt) / 2 - 0.004), L - 0.10, zt - zu - 0.025,
                     r=0.025, lift=lift + 0.012, n=3, rings=(0.6,), crown=0.004)

        def wall(x, z, off):
            p, n = self.wall(x, z, 1)
            return p + n * off
        # the armrest
        g = parts[upper]
        x_a, x_b = xa + L * 0.16, xb - L * 0.10
        secs = []
        for t in _along(x_b - x_a):
            x = x_a + (x_b - x_a) * t
            dd = 0.06 * (0.25 if t in (0.0, 1.0) else 0.8 if t in (0.05, 0.95) else 1.0)
            p, n = self.wall(x, arm, 1)
            up = V3((0, 0, 1))
            secs.append([p + n * a + up * b for a, b in
                         ((lift - 0.004, -0.045), (lift + dd * 0.75, -0.04), (lift + dd, -0.012),
                          (lift + dd, 0.012), (lift + dd * 0.7, 0.024), (lift - 0.004, 0.026))])
        loft(g, secs)
        gm, gg = parts["interior.metal"], parts["interior.gloss"]
        if pull == "bar":
            pa, pb = wall(x_a + (x_b - x_a) * 0.42, arm + 0.05, lift + 0.035), wall(x_a + (x_b - x_a) * 0.78, arm + 0.085, lift + 0.035)
            gm.tube(pa, pb, 0.009, 8)
            for p_, x_, z_ in ((pa, x_a + (x_b - x_a) * 0.42, arm + 0.05), (pb, x_a + (x_b - x_a) * 0.78, arm + 0.085)):
                gm.tube(p_, wall(x_, z_, lift), 0.007, 6)
        elif pull == "strap":
            pa, pb = wall(x_a + (x_b - x_a) * 0.45, arm + 0.055, lift + 0.012), wall(x_a + (x_b - x_a) * 0.75, arm + 0.075, lift + 0.012)
            pm = wall(x_a + (x_b - x_a) * 0.6, arm + 0.062, lift + 0.035)
            parts["seat.piping"].sweep([pa, pm, pb], [(-0.012, -0.002), (0.012, -0.002), (0.012, 0.002), (-0.012, 0.002)],
                                       up=(0, -1, 0))
            for p_ in (pa, pb):
                gm.box(p_, (0.02, 0.008, 0.03))
        elif pull == "cup":
            self.pad(gg, 'y', (x_a + (x_b - x_a) * 0.6, arm + 0.075), 0.14, 0.05, r=0.022, lift=lift + 0.014,
                     n=3, rings=())
        if release:
            xr_ = x_a + (x_b - x_a) * 0.88
            self.pad(gg, 'y', (xr_, arm + 0.105), 0.10, 0.045, r=0.018, lift=lift + 0.014, n=3, rings=())
            gm.box(wall(xr_, arm + 0.105, lift + 0.02), (0.07, 0.008, 0.02))
        if switches:
            xs = x_a + (x_b - x_a) * 0.62
            p, n = self.wall(xs, arm, 1)
            c = p + n * (lift + 0.036) + V3((0, 0, 0.027))
            gg.box(c, (0.11, 0.04, 0.006))
            for k in range(4):
                parts["interior.metal"].box(c + V3(((k - 1.5) * 0.024, 0, 0.004)), (0.016, 0.022, 0.004))
            parts["screen.lit"].box(c + V3((0.05, 0, 0.0034)), (0.004, 0.02, 0.001))
        if speaker:
            zs_ = (z0 + arm) / 2 - 0.01
            sz = min(0.15, arm - z0 - 0.09)
            if sz > 0.06:
                self.pad(parts["grille"], 'y', (xb - L * 0.2, zs_), sz, sz, r=sz / 2, lift=lift + 0.008,
                         n=5, rings=(0.6,), crown=0.006)
        if pocket:
            x_p, x_q = xa + L * 0.12, xb - L * (0.42 if speaker else 0.12)
            zp = z0 + 0.03
            secs = []
            for t in _along(x_q - x_p, 0.06):
                x = x_p + (x_q - x_p) * t
                dd = 0.05 * (0.2 if t in (0.0, 1.0) else 1.0)
                p, n = self.wall(x, zp + 0.04, 1)
                up = V3((0, 0, 1))
                secs.append([p + n * a + up * b for a, b in
                             ((lift - 0.004, -0.04), (lift + dd, -0.04), (lift + dd + 0.006, 0.05),
                              (lift + dd - 0.004, 0.05), (lift + dd - 0.008, -0.026), (lift - 0.004, -0.026))])
            loft(parts[card], secs)
        if strip and zt - zu > 0.06:
            parts["interior.ambient"].pipe([wall(xa + 0.07 + (L - 0.14) * k / 8, zu + 0.004, lift + 0.013)
                                            for k in range(9)], 0.0025, n=4, up=(0, 1, 0))
        if sill:
            ys_ = min(self.half(xa + L * 0.3, self.floor + 0.03), self.half(xb - L * 0.3, self.floor + 0.03))
            c = V3((xm, ys_ - 0.05, self.floor + 0.004))
            gm.box(c, (L - 0.12, 0.075, 0.008))
            if sill_text:
                # read by whoever steps in: on each side its own way round, not mirrored
                tx = _Parts()
                for s in (1, -1):
                    K.text_flat(tx["interior.ambient"], sill_text, 0.028,
                                V3((c.x, s * c.y, c.z + 0.0046)), (-s, 0, 0), (0, -s, 0),
                                spacing=1.25)
                self._emit(tag + "_text", tx, one_sided=True)
        self._emit(tag, parts, mirror=True)

    def sills(self, xa, xb, h=0.12, w=0.18, mat="interior", top="interior.carpet", tag="sill"):
        """A raised sill each side between xa and xb: a ledge h over the floor reaching w
        in from the wall (a tub car's wide sill, a step by a sliding door)."""
        xa, xb = min(xa, xb), max(xa, xb)
        parts = _Parts()
        fz = self.floor
        secs, tops = [], []
        n = 8
        for k in range(n + 1):
            x = xa + (xb - xa) * k / n
            yw = self.half(x, fz + h * 0.6) + 0.012
            yi = yw - w * (0.6 if k in (0, n) else 1.0)
            secs.append([V3((x, yw, fz - 0.01)), V3((x, yi - 0.012, fz - 0.01)), V3((x, yi, fz + h - 0.02)),
                         V3((x, yi + 0.02, fz + h)), V3((x, yw, fz + h))])
            tops.append([V3((x, yi + 0.03, fz + h + 0.002)), V3((x, yw - 0.02, fz + h + 0.002))])
        loft(parts[mat], secs)
        parts[top].add([p for r_ in tops for p in r_],
                       [(i * 2, i * 2 + 1, (i + 1) * 2 + 1, (i + 1) * 2) for i in range(n)])
        self._emit(tag, parts, mirror=True)

    # ---- the roof ---------------------------------------------------------------------
    def roof_kit(self, dome=True, visors=True, grabs="style", mirror=True, dome_x=None,
                 grab_x=None, visor_w=0.30):
        """What hangs from the headliner: a dome light (at dome_x; over the front seats'
        backs when not given), two sun visors behind the windshield's header, grab handles
        over the doors (grabs: "loop", "bar" or None; at grab_x, a list of x), an inside
        mirror on the header. Each is left out where there is no headliner to hang it on
        (a glass roof)."""
        grabs = self.st["grab"] if grabs == "style" else grabs
        parts = _Parts()
        hx = self.driver["hip"].x if self.driver else (self.x0 + self.x1) / 2
        gi, gm = parts["interior"], parts["interior.metal"]

        def lined(x, y):
            if self.lin is None:
                return None
            p, n, _, _ = self.lin.ray_cast(V3((x, y, self.zs)), V3((0, 0, 1)))
            return p
        if dome:
            x = hx - 0.15 if dome_x is None else dome_x
            p = lined(x, 0.0)
            if p is not None:
                pill(gi, p + V3((0, 0, -0.004)), (1, 0, 0), (0, 1, 0), 0.20, 0.11, 0.016, r=0.03, soft=0.5, n=2)
                pill(parts["interior.light"], p + V3((0, 0, -0.0105)), (1, 0, 0), (0, 1, 0), 0.13, 0.06, 0.006,
                     r=0.02, soft=0.5, n=2)
        hd = self.header(0.0)
        dy = abs(self.driver["hip"].y) if self.driver else 0.36
        if visors and hd is not None:
            for sgn in (-1, 1):
                h1 = self.header(sgn * dy) or hd
                a, b = lined(h1.x - 0.05, sgn * dy), lined(h1.x - 0.19, sgn * dy)
                if a is None or b is None:
                    continue
                along = (b - a).normalized()
                c = a.lerp(b, 0.5) + V3((0, 0, -0.016))
                pill(parts["interior.head"], c, along, (0, 1, 0), 0.15, visor_w, 0.014, r=0.03, soft=0.6, n=2)
                gi.tube(a + V3((0, sgn * (visor_w / 2 - 0.02), -0.012)), a + V3((0, sgn * (visor_w / 2 + 0.02), -0.004)), 0.006, 6)
        if mirror and hd is not None:
            root = hd + V3((-0.03, 0, -0.012))
            c = hd + V3((-0.075, 0, -0.07))
            gi.tube(root, c + V3((0.012, 0, 0.01)), 0.008, 8)
            a = rad(-12)
            up = V3((sin(a), 0, cos(a)))
            pill(gi, c + V3((0.006, 0, 0)), (0, 1, 0), up, 0.23, 0.065, 0.02, r=0.02, soft=0.5, n=3)
            pill(parts["mirror"], c + V3((-0.005, 0, 0)), (0, 1, 0), up, 0.215, 0.052, 0.003, r=0.016, soft=0.0, n=3)
        if grabs:
            xs = grab_x if grab_x is not None else [s["hip"].x + 0.05 for s in self.seats
                                                     if abs(s["hip"].y) > 0.1 or s["places"] > 1]
            done = set()
            for x in xs:
                key = round(x, 2)
                if key in done:
                    continue
                done.add(key)
                for sgn in (-1, 1):
                    o = V3((x, 0, self.zs))
                    d = V3((0, sgn * sin(rad(48)), cos(rad(48))))
                    if self.lin is None:
                        continue
                    p, n, _, _ = self.lin.ray_cast(o, d)
                    if p is None or p.z < self.belt + 0.05:
                        continue
                    if n.dot(d) > 0:
                        n = -n
                    if grabs == "bar":
                        gm.tube(p + n * 0.035 + V3((-0.11, 0, 0)), p + n * 0.035 + V3((0.11, 0, 0)), 0.011, 8)
                        for dx in (-0.09, 0.09):
                            gm.tube(p + V3((dx, 0, 0)), p + n * 0.035 + V3((dx, 0, 0)), 0.008, 6)
                    else:
                        gi.pipe([p + V3((-0.085, 0, 0)), p + n * 0.032 + V3((-0.06, 0, 0)),
                                 p + n * 0.032 + V3((0.06, 0, 0)), p + V3((0.085, 0, 0))], 0.009, n=6,
                                up=tuple(n))
        self._emit("roof", parts)

    # ---- the floor --------------------------------------------------------------------
    def mats(self, rear=True, w=None, ribs=6, mat="interior.mat"):
        """A floor mat ahead of each front seat (and each rear place with rear): a slab with
        a raised rim and ribs, held inside the lining and the firewall."""
        parts = _Parts()
        g = parts[mat]
        fz = self.floor
        fronts = sorted(self.seats, key=lambda s: -s["hip"].x)
        if not fronts:
            return
        xmax = fronts[0]["hip"].x
        for s in self.seats:
            H = s["hip"]
            front = abs(H.x - xmax) < 0.3
            if not front and not rear:
                continue
            n = s["places"]
            for k in range(n):
                yc = H.y + s["face"] * (-s["width"] / 2 + s["width"] * (k + 0.5) / n)
                xa = s["front"] + 0.03
                if front:
                    xb = min(self.x1 - 0.05, H.x + 0.80)
                else:
                    ahead = [t["back"] for t in self.seats if t["back"] > H.x + 0.2]
                    xb = min(min(ahead) - 0.10 if ahead else xa + 0.4, xa + 0.42)
                if xb - xa < 0.14:
                    continue
                ww = w or min(0.40, s["width"] / n - 0.06)
                lim = min(self.half(xa + 0.05, fz + 0.03), self.half(xb - 0.05, fz + 0.03)) - 0.03
                if abs(yc) + ww / 2 > lim:
                    ww = max(0.2, 2 * (lim - abs(yc)))
                c = V3(((xa + xb) / 2, yc, fz + 0.004))
                pill(g, c, (1, 0, 0), (0, 1, 0), xb - xa, ww, 0.008, r=0.04, soft=0.3, n=3)
                for i in range(ribs):
                    x = xa + 0.05 + (xb - xa - 0.10) * (i + 0.5) / ribs
                    g.box((x, yc, fz + 0.0095), (0.012, ww - 0.09, 0.003))
        self._emit("mats", parts)

    def shelf(self, xa, xb, z, thick=0.02, mat="interior.head", tag="shelf", inset=0.004,
              lip=0.0):
        """A board across the car between xa and xb at the height z (its top), cut to the
        lining at each side: a parcel shelf, a load floor, a boot's cover. lip: a raised
        edge along its front."""
        xa, xb = min(xa, xb), max(xa, xb)
        parts = _Parts()
        n = 6
        secs = []
        for k in range(n + 1):
            x = xa + (xb - xa) * k / n
            yw = self.half(x, z - thick / 2) + 0.012 - inset
            zz = z + (lip if k == n else 0.0)
            secs.append([V3((x, -yw, z - thick)), V3((x, yw, z - thick)), V3((x, yw, zz)), V3((x, -yw, zz))])
        loft(parts[mat], secs)
        self._emit(tag, parts)

    # ---- views and lights -------------------------------------------------------------
    @staticmethod
    def _background():
        w = K.SCN.world
        if w is None or w.node_tree is None:
            return None
        bg = next((n for n in w.node_tree.nodes if n.type == 'BACKGROUND'), None)
        return bg.inputs["Strength"] if bg is not None else None

    def views(self, eye=None, lens=17.0, exposure=0.8, lamps=None, power=5.0, daylight=15.0,
              outside=3.0, cut=0.16):
        """The interior views, added to K.VIEWS (render them with --views cab_fwd,...):

          cab_fwd   from the driver's eye, ahead and a little down and inboard
          cab_side  from the driver's eye at the far door
          cab_back  from the driver's eye over the inboard shoulder to the rear
          cab_dash  from the driver's eye down at the wheel, the cluster and the console
          cab_in    from outside the driver's door, the near side cut away by the
                    camera's near clip (cut: how far inside the lining it cuts)

        eye: the eye point (the driver's seat's when not given). In these views only, the
        cabin's own lamps are lit (lamps: [(x, y, z), ...]; a dome under the headliner and
        one low at the dash when not given; power in watts) and the exposure is raised by
        exposure stops; every other view renders as it did."""
        drv = self._drv()
        e = V3(eye) if eye is not None else V3(drv["eye"])
        self.eye = e
        sg = 1.0 if drv["hip"].y >= 0 else -1.0

        def look(name, d, ln):
            d = V3(d).normalized()
            K.VIEWS[name] = dict(dir=tuple(-d), target=tuple(e + d * 0.45), dist=0.45, lens=ln,
                                 clip=0.03, cabin=True)
        look("cab_fwd", (1.0, -0.16 * sg, -0.14), lens)
        look("cab_side", (0.42, -1.0 * sg, -0.20), lens)
        look("cab_dash", (1.0, -0.30 * sg, -0.62), lens + 5)
        # over the shoulder: the head turned, so the eye stands forward of the seat's back
        # and inboard of the headrest, looking back across the cabin
        eb = V3((e.x + 0.30, e.y * 0.1, e.z + 0.06))
        d = V3((-1.0, -0.3 * sg, -0.33)).normalized()
        K.VIEWS["cab_back"] = dict(dir=tuple(-d), target=tuple(eb + d * 0.45), dist=0.45,
                                   lens=lens - 2, clip=0.03, cabin=True)
        H = drv["hip"]
        yw = self.half(H.x, H.z + 0.2)
        # square to the side, so the near clip cuts the near side along its length
        xs = [s_["hip"].x for s_ in self.seats]
        xc = (max(xs) + 0.35 + min(xs) - 0.25) / 2
        span = max(1.4, max(xs) - min(xs) + 1.3)
        dist = yw + max(1.3, span * 0.95)
        tgt = V3((xc, 0.0, H.z + 0.12))
        d = V3((0.0, sg, 0.22)).normalized()
        K.VIEWS["cab_in"] = dict(dir=tuple(d), target=tuple(tgt), dist=dist / d.y * sg,
                                 lens=20.0, clip=(dist - (yw - cut)) / abs(d.y), cabin=True)
        if lamps is None:
            # a dome under the headliner, a low fill at the dash, and daylight: a soft panel
            # just inside every window, facing in (the studio's own light reaches a cabin
            # only through the glass, as noise)
            xm = H.x - 0.1
            top = self.roof(xm, 0.0)[0].z
            lamps = [dict(at=(xm, 0.0, top - 0.05), size=(0.3, 0.3), watts=power),
                     dict(at=(H.x + 0.45, 0.0, H.z + 0.08), size=(0.3, 0.3), watts=power * 0.35)]
            for name, c, nrm, u, su, sv in getattr(self, "windows", []):
                lamps.append(dict(at=tuple(c + nrm * 0.35), aim=nrm, u=u,
                                  size=(su * 0.7, sv * 0.7), watts=daylight * su * sv,
                                  color=(0.92, 0.96, 1.0)))
        made = []

        def studio():
            for k, lp in enumerate(lamps):
                if not isinstance(lp, dict):
                    lp = dict(at=lp, size=(0.3, 0.3), watts=power if k == 0 else power * 0.35)
                L = bpy.data.lights.new("cab%d" % k, 'AREA')
                L.shape = 'RECTANGLE'
                L.size, L.size_y = lp["size"]
                L.energy = 0.0
                L.color = lp.get("color", (1.0, 0.95, 0.88) if not lp.get("glossy") else (0.92, 0.96, 1.0))
                o = bpy.data.objects.new("cab%d" % k, L)
                K.STUDIO.objects.link(o)
                o.location = lp["at"]
                if lp.get("aim") is not None:
                    zl = -V3(lp["aim"]).normalized()
                    xl = V3(lp.get("u", (1, 0, 0)))
                    xl = (xl - zl * xl.dot(zl)).normalized()
                    o.rotation_euler = Matrix((xl, zl.cross(xl), zl)).transposed().to_euler()
                else:
                    K.aim(o, (lp["at"][0], lp["at"][1], lp["at"][2] - 1.0))
                o.visible_camera = False
                o.visible_transmission = False
                o.visible_glossy = bool(lp.get("glossy"))  # no square of light in the glass
                made.append((L, lp["watts"]))
        K.after_studio(studio)
        keep = {}

        def hook(name, before):
            if not K.VIEWS.get(name, {}).get("cabin"):
                return
            vs = K.SCN.view_settings
            if before:
                keep["e"] = vs.exposure
                vs.exposure = keep["e"] + exposure
                # the world outside brighter, as day is to a cabin: the glass shows it
                # more than the cabin mirrored in it
                bg = self._background()
                if bg is not None:
                    keep["bg"] = bg.default_value
                    bg.default_value = keep["bg"] * outside
                # the studio's soft boxes seen through the glass would be white panes
                # (seen straight, or through the glass: a transmission ray)
                keep["cam"] = {o.name: (o.visible_camera, o.visible_transmission)
                               for o in K.STUDIO.objects if o.type == 'LIGHT'
                               and not o.name.startswith("cab")}
                for n in keep["cam"]:
                    K.STUDIO.objects[n].visible_camera = False
                    K.STUDIO.objects[n].visible_transmission = False
            else:
                vs.exposure = keep.get("e", 0.0)
                bg = self._background()
                if bg is not None and "bg" in keep:
                    bg.default_value = keep.pop("bg")
                for n, (v, t) in keep.pop("cam", {}).items():
                    K.STUDIO.objects[n].visible_camera = v
                    K.STUDIO.objects[n].visible_transmission = t
            for L, pw in made:
                L.energy = pw if before else 0.0
        K.on_view(hook)
        return e
