"""LG2: lifegen's garments, cut, built and draped on one character's own body in Blender
(headless; stdlib, bpy, bmesh and mathutils only, as citygen's Blender scripts).

    blender -b --factory-startup -P lifegen/blender/garments.py -- JOB.json

The job (`lifegen/garments.py`, `blender_job`) carries one character of the people library:
its body as the project's editor exported it (`citygen/ue/people_library.py`, step `bodies`:
the assembled body, its plain outfit and face at LOD 0, in the skeletal mesh's reference pose,
centimeters in Unreal's frame, and its bones), the garments drafted for it from its own
measurements (`lifegen.garments.draft`: each a sewing pattern's parameters, the parts it
covers, its cuts, ease per region, neckline, sleeve, flare, hood, collar, trims, its textile,
layer and dye channel), the accessories, the looks (which garments and accessories each wears)
and the textiles' mean colors. It writes per look the near mesh (LOD 0 and LOD 1) and the mid
mesh as JSON in Unreal's frame (`<out>/<look>.near.json`, `.lod1.json`, `.mid.json`), the
report (`report.json`) and, when asked, renders of each garment and each look on the body.

How a garment is made (scope 6.2, adapted: a garment is built on the body it dresses rather
than sewn from flat panels hung round it, since a flat panel sewn shut by springs crumples
where its cut and the body disagree, as LG0's tee did in the armpits):

1. **The mannequin**: the body, its plain outfit (which fills the body's holes under it: the
   creator's assembly took the skin out there) and the face's skin as one closed surface (a
   voxel remesh at `VOXEL_M`), decimated; every vertex labelled with the part of the body it
   belongs to (its nearest bone segment, less the part's own radius) and its place along it.
2. **The panels**: the faces of the parts the pattern covers, offset outward by the pattern's
   ease for each part (at most `ROOM` of the free space to the next part, so legs and arms keep
   apart), smoothed so the cloth spans the body's hollows and pushed back outside it, cut by
   the pattern's planes (hem, cuffs, ankles, neckline, the front opening) on the parts each
   belongs to; skirts and coat skirts flared down from the hip line, hoods and collars added.
   The panel coordinates (round each part and along it, in meters) are the UVs, so a textile
   lies on the garment as on its pattern piece.
3. **The drape**: Blender's cloth solver lets it settle on the mannequin (a collision object)
   under gravity, its fitted parts held by goal springs, the loose ones (skirts, coat tails,
   hoods) free; the last frame is kept (a vertex the solver threw past `MAX_MOVE` goes back).
4. **The finish**: a rim of the textile's thickness at every open edge (hems, cuffs, the front
   opening), trims as their own slots, the vertex colors (rgb a multiplier, alpha the dye
   channel the person's colors go on).

A look joins its garments and accessories, takes out the faces of a layer another covers (no
hidden faces drawn, no inner layer through an outer one), checks that it covers the plain
outfit's region (where the body has no skin) and is written out.

Coordinates: Unreal's component space (cm, x to the body's left, y forward, z up) becomes
Blender's (m) with y negated (`ue_to_bl`), so the body faces -Y as Blender's front view
expects; a triangle keeps its corners' order both ways (the mirror and Unreal's clockwise
front faces cancel: the normals point out).
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

VOXEL_M = 0.009          # the mannequin's voxel size
MANNEQUIN_FACES = 15000  # its faces after decimation (about 2 cm edges)
FRAMES = 28              # the drape's frames
ROOM = 0.45              # a vertex's ease at most this share of the free space before it
MAX_MOVE = {"fit": 0.05, "loose": 0.3}
LOD1_RATIO = 0.45        # the near mesh's LOD 1 (of LOD 0's triangles)
MID_TRIS = 4500          # the mid mesh's triangles (all the look's garments)
COVER_M = 0.07           # an outer face within this along a face's normal covers it

PARTS = ("torso", "neck", "head", "uarm", "farm", "hand", "thigh", "calf", "foot", "skirt",
         "hood", "collar", "acc")
SIDES = ("", "l", "r")
PART_R = {"torso": 0.13, "neck": 0.055, "head": 0.085, "uarm": 0.045, "farm": 0.035,
          "hand": 0.03, "thigh": 0.075, "calf": 0.05, "foot": 0.04}
LIMB = {"uarm": "arm", "farm": "arm", "hand": "arm", "thigh": "leg", "calf": "leg",
        "foot": "leg"}
LAYER_ORDER = {"skin": 0, "shoes": 1, "bottom": 2, "base": 3, "outer": 4, "acc": 5}


def log(msg):
    print(f"CGGARMENT {msg}", flush=True)


def ue_to_bl(x, y, z):
    return Vector((x / 100.0, -y / 100.0, z / 100.0))


def bl_to_ue(v):
    return [round(v[0] * 100.0, 3), round(-v[1] * 100.0, 3), round(v[2] * 100.0, 3)]


def select_only(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


# ------------------------------------------------------------------------------------------
# the body
# ------------------------------------------------------------------------------------------

def mesh_from(name, rec, keep_mats=None):
    p = rec["positions"]
    verts = [ue_to_bl(p[3 * i], p[3 * i + 1], p[3 * i + 2]) for i in range(len(p) // 3)]
    t = rec["triangles"]
    mids = rec.get("material_ids") or [0] * (len(t) // 3)
    faces = [(t[3 * k], t[3 * k + 1], t[3 * k + 2]) for k in range(len(t) // 3)
             if keep_mats is None or mids[k] in keep_mats]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def skin_material_id(face):
    cnt = {}
    for m in face.get("material_ids") or []:
        cnt[m] = cnt.get(m, 0) + 1
    return max(cnt, key=lambda k: cnt[k]) if cnt else 0


class Body:
    """A character's body: its bones (Blender's frame), its parts' segments, its landmarks."""

    def __init__(self, data):
        self.bones = {b["name"]: ue_to_bl(*b["t"]) for b in data["body"]["bones"]}
        B = self.bones
        self.segments = []      # (part, side, a, b)

        def chain(part, side, names, extend=0.0):
            pts = [B[n] for n in names if n in B]
            if extend and len(pts) >= 2:
                pts.append(pts[-1] + (pts[-1] - pts[-2]).normalized() * extend)
            for a, b in zip(pts, pts[1:]):
                self.segments.append((part, side, a, b))

        chain("torso", "", ["pelvis", "spine_01", "spine_02", "spine_03", "spine_04",
                            "spine_05", "neck_01"])
        for s in ("l", "r"):
            self.segments.append(("torso", "", B["spine_05"], B[f"clavicle_{s}"]))
            self.segments.append(("torso", "", B[f"clavicle_{s}"], B[f"upperarm_{s}"]))
            chain("uarm", s, [f"upperarm_{s}", f"lowerarm_{s}"])
            chain("farm", s, [f"lowerarm_{s}", f"hand_{s}"])
            chain("hand", s, [f"hand_{s}", f"middle_01_{s}"], extend=0.06)
            chain("thigh", s, [f"thigh_{s}", f"calf_{s}"])
            chain("calf", s, [f"calf_{s}", f"foot_{s}"])
            chain("foot", s, [f"foot_{s}", f"ball_{s}"], extend=0.05)
        chain("neck", "", ["neck_01", "neck_02", "head"])
        self.segments.append(("head", "", B["head"], B["head"] + Vector((0, 0, 0.16))))
        self.radius = dict(PART_R)
        self.z = {"ankle": (B["foot_l"].z + B["foot_r"].z) / 2.0,
                  "knee": (B["calf_l"].z + B["calf_r"].z) / 2.0,
                  "hip": (B["thigh_l"].z + B["thigh_r"].z) / 2.0,
                  "waist": B["spine_02"].z, "chest": B["spine_04"].z,
                  "shoulder": (B["upperarm_l"].z + B["upperarm_r"].z) / 2.0,
                  "neck": B["neck_01"].z, "head": B["head"].z}
        self.center = Vector((0.0, (B["pelvis"].y + B["spine_04"].y) / 2.0, 0.0))
        self.head = {}
        self.outfit = None

    def limb(self, which, side):
        B = self.bones
        if which == "arm":
            return B[f"upperarm_{side}"], B[f"lowerarm_{side}"], B[f"hand_{side}"]
        return B[f"thigh_{side}"], B[f"calf_{side}"], B[f"foot_{side}"]


def seg_dist(p, a, b):
    ab = b - a
    L2 = ab.length_squared
    t = 0.0 if L2 <= 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / L2))
    return (p - (a + ab * t)).length, t


def limb_t(body, part, side, p):
    """The place along a limb: 0 at the shoulder or hip, 1 at the wrist or ankle; the torso's
    and head's: the height."""
    if part not in LIMB or not side:
        return p.z
    a, b, c = body.limb(LIMB[part], side)
    L1, L2 = (b - a).length, (c - b).length
    d1, t1 = seg_dist(p, a, b)
    d2, t2 = seg_dist(p, b, c)
    return (t1 * L1) / (L1 + L2) if d1 <= d2 else (L1 + t2 * L2) / (L1 + L2)


def label_points(body, pts, measure=True):
    """Each point's (part, side, t): its nearest segment less its part's radius (the radii
    measured on the points in a second pass when `measure`)."""
    def run(radius):
        out = []
        for p in pts:
            best = None
            for part, side, a, b in body.segments:
                d, _ = seg_dist(p, a, b)
                s = d - radius[part]
                if best is None or s < best[0]:
                    best = (s, part, side, d)
            out.append(best)
        return out
    first = run(body.radius)
    if measure:
        meas = {}
        for _, part, _, d in first:
            meas.setdefault(part, []).append(d)
        for part, ds in meas.items():
            ds.sort()
            body.radius[part] = 0.5 * (body.radius[part] + ds[len(ds) // 2])
        first = run(body.radius)
    return [(part, side, limb_t(body, part, side, p)) for p, (_, part, side, _) in zip(pts, first)]


def mannequin(data):
    """The body, its plain outfit and the face's skin as one closed surface."""
    obs = [mesh_from("body", data["body"]), mesh_from("outfit", data["outfit"]),
           mesh_from("face", data["face"], keep_mats={skin_material_id(data["face"])})]
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.join()
    m = bpy.context.view_layer.objects.active
    m.name = "mannequin"
    m.data.remesh_voxel_size = VOXEL_M
    bpy.ops.object.voxel_remesh()
    dec = m.modifiers.new("dec", "DECIMATE")
    dec.ratio = min(1.0, MANNEQUIN_FACES / max(1, len(m.data.polygons)))
    bpy.ops.object.modifier_apply(modifier="dec")
    sm = m.modifiers.new("smooth", "SMOOTH")
    sm.factor, sm.iterations = 0.5, 4
    bpy.ops.object.modifier_apply(modifier="smooth")
    bpy.ops.object.shade_smooth()
    m.hide_render = True
    return m


class Space:
    """The mannequin as a BVH with its vertices' labels: what a garment is built on."""

    def __init__(self, body, man):
        self.body = body
        self.ob = man
        me = man.data
        self.co = [v.co.copy() for v in me.vertices]
        self.no = [v.normal.copy() for v in me.vertices]
        self.tris = [tuple(p.vertices) for p in me.polygons]
        self.bvh = BVHTree.FromPolygons(self.co, self.tris)
        self.lab = label_points(body, self.co)
        hv = [p for p, lb in zip(self.co, self.lab) if lb[0] == "head"]
        top = max(p.z for p in hv)
        H = body.head
        H["top"] = top
        H["eye"] = top - 0.115
        H["cy"] = sum(p.y for p in hv) / len(hv)
        ring = [p for p in hv if abs(p.z - H["eye"]) < 0.015]
        H["rx"] = max(abs(p.x) for p in ring) if ring else 0.075
        H["front"] = min(p.y for p in ring) if ring else H["cy"] - 0.1
        H["back"] = max(p.y for p in ring) if ring else H["cy"] + 0.1

    def measure_outfit(self, data):
        """Where the plain outfit's openings are (the body's skin ends under them, so a look
        must reach past each): its neck opening (an ellipse round the neck, its height at the
        front and back), each sleeve's end (along the arm) and the legs' hem (its height)."""
        body = self.body
        ob = mesh_from("_outfit", data["outfit"])
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        loops = [lp for lp in boundary_loops(bm) if len(lp) > 8]
        out = {"sleeve": {"l": 0.0, "r": 0.0}, "hem_z": body.z["knee"] + 0.15}
        neck = max(loops, key=lambda lp: sum(v.co.z for v in lp) / len(lp))
        pts = [v.co.copy() for v in neck]
        cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2.0
        fr = min(pts, key=lambda p: p.y)
        bk = max(pts, key=lambda p: p.y)
        out["neck"] = {"cy": cy, "rx": max(abs(p.x) for p in pts), "ryf": cy - fr.y,
                       "ryb": bk.y - cy, "zf": fr.z, "zb": bk.z}
        legs = []
        for lp in loops:
            if lp is neck:
                continue
            c = sum((v.co for v in lp), Vector()) / len(lp)
            if c.z > body.z["waist"] and abs(c.x) > 0.1:
                side = "l" if c.x > 0 else "r"
                t = max(limb_t(body, "uarm", side, v.co) for v in lp)
                out["sleeve"][side] = max(out["sleeve"][side], t)
            elif c.z < body.z["hip"]:
                legs.append(max(v.co.z for v in lp))
        if legs:
            out["hem_z"] = max(legs)
        bm.free()
        bpy.data.objects.remove(ob)
        body.outfit = out
        return out

    def outside(self, p, clear):
        """`p` pushed out to `clear` over the mannequin where it lies closer or inside."""
        q, n, _, _ = self.bvh.find_nearest(p)
        if q is None:
            return p
        d = (p - q).dot(n)
        return q + n * clear if d < clear else p


# ------------------------------------------------------------------------------------------
# labels on a bmesh (custom layers: they follow every cut and join)
# ------------------------------------------------------------------------------------------

def layers(bm):
    li = bm.verts.layers.int
    lf = bm.verts.layers.float
    return (li.get("part") or li.new("part"), li.get("side") or li.new("side"),
            lf.get("t") or lf.new("t"), li.get("src") or li.new("src"))


def put(v, L, lab, src=-1):
    v[L[0]] = PARTS.index(lab[0])
    v[L[1]] = SIDES.index(lab[1])
    v[L[2]] = lab[2]
    v[L[3]] = src


def get(v, L):
    return PARTS[v[L[0]]], SIDES[v[L[1]]], v[L[2]]


def in_parts(lb, parts):
    return lb[0] in parts or (lb[0] + "_" + lb[1]) in parts


# ------------------------------------------------------------------------------------------
# panels
# ------------------------------------------------------------------------------------------

def region(space, draft):
    """A bmesh of the mannequin's faces in the pattern's parts."""
    keep = set(draft["parts"])
    bm = bmesh.new()
    L = layers(bm)
    vm = {}
    for tri in space.tris:
        if sum(1 for i in tri if in_parts(space.lab[i], keep)) < 2:
            continue
        vs = []
        for i in tri:
            if i not in vm:
                v = bm.verts.new(space.co[i])
                put(v, L, space.lab[i], i)
                vm[i] = v
            vs.append(vm[i])
        try:
            bm.faces.new(vs)
        except ValueError:
            pass
    return bm


def ease_of(draft, lb):
    part = lb[0]
    e = draft["ease"]
    if LIMB.get(part) == "arm":
        return e.get("arm", e["torso"])
    if LIMB.get(part) == "leg":
        return e.get("leg", e["torso"])
    if part in ("head", "neck"):
        return e.get("head", e["torso"])
    # (a tucked shirt is closer under the trousers from the waist down)
    if "low" in e and lb[2] < draft["z"]["waist"] + 0.03:
        return e["low"]
    return e["torso"]


def offset(bm, space, draft):
    """Each vertex out along the mannequin's normal by its part's ease, at most `ROOM` of the
    free space there, then smoothed over the body's hollows and kept outside it."""
    L = layers(bm)
    clear = draft.get("clear", 0.006)
    for v in bm.verts:
        n = space.no[v[L[3]]]
        e = max(clear, ease_of(draft, get(v, L)))
        hit = space.bvh.ray_cast(v.co + n * 0.003, n, 0.5)
        if hit[0] is not None:
            e = min(e, max(clear, ROOM * (hit[3] + 0.003)))
        v.co = v.co + n * e
    smooth(bm, space, draft, rounds=draft.get("smooth", 3))


def smooth(bm, space, draft, rounds=3, its=6, fac=0.5, only=None):
    L = layers(bm)
    clear = draft.get("clear", 0.006)
    vs = [v for v in bm.verts if only is None or get(v, L)[0] in only]
    target = [max(clear, ease_of(draft, get(v, L)) * 0.6) for v in vs]
    for _ in range(rounds):
        for _ in range(its):
            new = []
            for v in vs:
                if not v.link_edges:
                    new.append(v.co.copy())
                    continue
                nb = [e.other_vert(v).co for e in v.link_edges
                      if not v.is_boundary or e.is_boundary]
                if not nb:
                    new.append(v.co.copy())
                    continue
                c = sum(nb, Vector()) / len(nb)
                new.append(v.co.lerp(c, fac))
            for v, c in zip(vs, new):
                v.co = c
        for v, t in zip(vs, target):
            v.co = space.outside(v.co, t)


def cut(bm, co, no, parts=None):
    """Bisects the panels by a plane, keeping the side `no` points away from, only on the
    faces with a vertex in `parts` (all when None)."""
    L = layers(bm)
    if parts is None:
        geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    else:
        parts = set(parts)
        fs = [f for f in bm.faces if any(in_parts(get(v, L), parts) for v in f.verts)]
        geom = list({v for f in fs for v in f.verts}) + list({e for f in fs for e in f.edges}) + fs
    if geom:
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True,
                               dist=1e-5)


def drop_small(bm, keep_min=40):
    """Takes out pieces of fewer than `keep_min` faces (crumbs the cuts leave)."""
    seen, drop = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        comp, stack = [], [f]
        seen.add(f)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
        if len(comp) < keep_min:
            drop += comp
    if drop:
        bmesh.ops.delete(bm, geom=drop, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")


def neck_cut(bm, body, c, ease=0.015):
    """A neckline at the plain outfit's neck opening (`scale` of it, `raise` m higher): the
    faces inside its ellipse above its line taken out, the open edge there put on the
    ellipse."""
    L = layers(bm)
    o = body.outfit["neck"]
    sc = c.get("scale", 0.95)
    rx, ryf, ryb = o["rx"] * sc + ease, o["ryf"] * sc + ease, o["ryb"] * sc + ease

    def ratio(p):
        dy = p.y - o["cy"]
        return math.sqrt((p.x / rx) ** 2 + (dy / (ryf if dy < 0 else ryb)) ** 2)

    def zline(p):
        f = max(0.0, min(1.0, (p.y - (o["cy"] - ryf)) / max(1e-6, ryf + ryb)))
        return o["zf"] + (o["zb"] - o["zf"]) * f + c.get("raise", 0.0)

    dele = []
    for f in bm.faces:
        m = f.calc_center_median()
        part = get(f.verts[0], L)[0]
        # (the neck's own tube above the neckline goes, however far out the ease put it)
        if (part == "neck" and m.z > zline(m) - 0.01) or \
                (ratio(m) < 1.0 and m.z > zline(m) - 0.04 and part in ("torso", "neck")) or \
                (ratio(m) < 1.7 and m.z > zline(m) + 0.005 and part in ("torso", "neck")):
            dele.append(f)
    if dele:
        bmesh.ops.delete(bm, geom=dele, context="FACES")
    for v in bm.verts:
        if v.is_boundary and v.co.z > zline(v.co) - 0.07:
            r = ratio(v.co)
            if 0.0 < r < 1.45:
                dy = v.co.y - o["cy"]
                v.co.x /= r
                v.co.y = o["cy"] + dy / r
                # (the neckline level along its line, not the faces' steps)
                v.co.z = zline(v.co) - 0.015
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")


def apply_cuts(bm, body, draft):
    L = layers(bm)
    for c in draft["cuts"]:
        kind = c["kind"]
        if kind == "z":
            up = Vector((0, 0, 1)) if c.get("keep", "below") == "below" else Vector((0, 0, -1))
            cut(bm, Vector((0, 0, c["z"])), up, c.get("parts"))
        elif kind == "tilt":            # through (0, y, z), its front lower by `deg`
            a = math.radians(c.get("deg", 0.0))
            no = Vector((0, -math.sin(a), math.cos(a)))
            cut(bm, Vector((0, c.get("y", 0.0), c["z"])),
                no if c.get("keep", "below") == "below" else -no, c.get("parts"))
        elif kind == "vneck":           # two planes from the front center up and out
            for s in (1, -1):
                d = Vector((s * c["spread"], 0.0, 1.0)).normalized()
                no = Vector((-s * d.z, 0.0, s * d.x))
                if no.z < 0:
                    no = -no
                fs = [f for f in bm.faces if f.calc_center_median().y < body.center.y]
                geom = list({v for f in fs for v in f.verts}) + \
                    list({e for f in fs for e in f.edges}) + fs
                bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector((0, 0, c["z"])),
                                       plane_no=no, clear_outer=True, dist=1e-5)
        elif kind == "neck":            # the outfit's neck opening, scaled
            neck_cut(bm, body, c, draft["ease"]["torso"])
        elif kind == "limb":            # square to a limb at a share of its length
            for side in ("l", "r"):
                a, b, cc = body.limb(c["limb"], side)
                L1, L2 = (b - a).length, (cc - b).length
                tt = c["t"]
                if c["limb"] == "arm" and body.outfit:
                    # (past the plain outfit's sleeve: the body has no skin under it)
                    tt = max(tt, body.outfit["sleeve"][side] + 0.035)
                s = tt * (L1 + L2)
                if s <= L1:
                    p, d = a + (b - a) * (s / L1), (b - a).normalized()
                else:
                    p, d = b + (cc - b) * min(1.0, (s - L1) / L2), (cc - b).normalized()
                parts = {f"{x}_{side}" for x, w in LIMB.items() if w == c["limb"]}
                cut(bm, p, d, parts)
        elif kind == "front":           # the front opening: a slot |x| < width / 2
            half = c["width"] / 2.0
            dele = []
            for f in bm.faces:
                m = f.calc_center_median()
                if abs(m.x) < half and m.y < body.center.y and m.z < c.get("z_max", 9.0) and \
                        get(f.verts[0], L)[0] in ("torso", "neck", "skirt"):
                    dele.append(f)
            if dele:
                bmesh.ops.delete(bm, geom=dele, context="FACES")
            for v in bm.verts:
                if v.is_boundary and abs(v.co.x) < half * 2.2 and v.co.y < body.center.y and \
                        v.co.z < c.get("z_max", 9.0) - 0.02:
                    v.co.x = half if v.co.x >= 0 else -half
        drop_small(bm)


# ------------------------------------------------------------------------------------------
# loose parts: flares (skirts, coat skirts), hoods, collars
# ------------------------------------------------------------------------------------------

def boundary_loops(bm):
    left = {e for e in bm.edges if e.is_boundary}
    loops = []
    while left:
        e = left.pop()
        loop = [e.verts[0], e.verts[1]]
        while True:
            nxt = next((f for f in loop[-1].link_edges if f in left), None)
            if nxt is None:
                break
            left.discard(nxt)
            w = nxt.other_vert(loop[-1])
            if w is loop[0]:
                break
            loop.append(w)
        loops.append(loop)
    return loops


def _last_hit(space, o, d, far=1.0):
    hit = space.bvh.ray_cast(o, d, far)
    if hit[0] is None:
        return None
    last = hit
    for _ in range(8):
        h2 = space.bvh.ray_cast(last[0] + d * 0.002, d, far)
        if h2[0] is None:
            break
        last = h2
    return (last[0] - o).length


def flare(bm, space, draft):
    """A skirt hung from the lowest open loop round the hips: rings down to the hem, each the
    loop's shape scaled about its middle by the flare and kept outside the legs (a front
    opening, when the pattern has one, carried down)."""
    f = draft.get("flare")
    if not f:
        return
    L = layers(bm)
    loops = [lp for lp in boundary_loops(bm) if len(lp) > 12]
    if not loops:
        return
    loop = min(loops, key=lambda lp: sum(v.co.z for v in lp) / len(lp))
    c = sum((v.co for v in loop), Vector()) / len(loop)
    c.z = 0.0
    n = len(loop)
    f = dict(f)
    if space.body.outfit:
        # (below the plain outfit's legs: the body has no skin under them)
        f["to_z"] = min(f["to_z"], space.body.outfit["hem_z"] - 0.05)
    rings = max(4, int((f["from_z"] - f["to_z"]) / 0.03))
    clear = draft.get("clear", 0.006) + 0.012
    prev = loop
    for k in range(1, rings + 1):
        s = k / rings
        z = f["from_z"] + (f["to_z"] - f["from_z"]) * s
        scale = 1.0 + f["scale"] * s
        ring = []
        for v in loop:
            d = Vector((v.co.x - c.x, v.co.y - c.y, 0.0))
            o = Vector((c.x, c.y, z))
            dirn = d.normalized() if d.length > 1e-6 else Vector((1, 0, 0))
            r = d.length * scale
            far = _last_hit(space, o, dirn)
            if far is not None:
                r = max(r, far + clear)
            nv = bm.verts.new(o + dirn * r)
            put(nv, L, ("skirt", "", z))
            ring.append(nv)
        for i in range(n):
            j = (i + 1) % n
            if (prev[i].co - prev[j].co).length > 0.06:    # (an opening carried down)
                continue
            try:
                bm.faces.new((prev[i], prev[j], ring[j], ring[i]))
            except ValueError:
                pass
        prev = ring


def hood(bm, space, body, draft):
    """A hood up round the head (the mannequin's head and neck behind the face, offset and
    smoothed into a loose shell), or down (a roll behind the neck)."""
    h = draft.get("hood")
    if not h:
        return
    L = layers(bm)
    H = body.head
    if h == "up":
        # (an ellipsoid round the head, open at the face and below the jaw, pushed out of the
        # head where it comes close)
        zc = H["eye"] + 0.01
        cy = H["cy"] + 0.012
        rx = H["rx"] + 0.045
        ryb = (H["back"] - H["cy"]) + 0.055
        ryf = (H["cy"] - H["front"]) + 0.03
        rzu = (H["top"] - zc) + 0.045
        rzd = zc - (body.z["neck"] - 0.05)
        nu, nv = 36, 18
        grid = []
        for i in range(nv + 1):
            el = -math.pi / 2 + math.pi * i / nv
            row = []
            for j in range(nu):
                az = 2 * math.pi * j / nu
                ce, se = math.cos(el), math.sin(el)
                dy = -math.cos(az) * ce
                p = Vector((math.sin(az) * ce * rx,
                            cy + dy * (ryf if dy < 0 else ryb),
                            zc + se * (rzu if se > 0 else rzd)))
                p = space.outside(p, 0.02)
                v = bm.verts.new(p)
                put(v, L, ("hood", "", p.z))
                row.append(v)
            grid.append(row)
        for i in range(nv):
            for j in range(nu):
                k = (j + 1) % nu
                q = (grid[i][j], grid[i][k], grid[i + 1][k], grid[i + 1][j])
                m = sum((v.co for v in q), Vector()) / 4
                # (open at the face, and below the jaw in front)
                if m.y < H["front"] + 0.04 and m.z > body.z["neck"] - 0.01:
                    continue
                if m.y < cy - 0.02 and m.z < body.z["neck"] + 0.01:
                    continue
                try:
                    bm.faces.new(q)
                except ValueError:
                    pass
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
    elif h == "down":
        c = Vector((0.0, body.bones["neck_01"].y + 0.025, body.z["neck"] - 0.01))
        segs, rings = 18, 8
        grid = []
        for i in range(segs + 1):
            a = math.radians(-115 + 230 * i / segs)
            ring = []
            for j in range(rings):
                b = 2 * math.pi * j / rings
                rr = 0.105 + 0.035 * math.cos(b)
                v = bm.verts.new(Vector((math.sin(a) * rr, c.y + math.cos(a) * rr * 0.85,
                                         c.z + 0.03 * math.sin(b))))
                put(v, L, ("hood", "", c.z))
                ring.append(v)
            grid.append(ring)
        for i in range(segs):
            for j in range(rings):
                k = (j + 1) % rings
                try:
                    bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][k], grid[i][k]))
                except ValueError:
                    pass


def _merge_into(bm, sub):
    L, Ls = layers(bm), layers(sub)
    vm = {}
    for v in sub.verts:
        nv = bm.verts.new(v.co)
        for a, b in zip(L, Ls):
            nv[a] = v[b]
        vm[v] = nv
    for f in sub.faces:
        try:
            bm.faces.new([vm[v] for v in f.verts])
        except ValueError:
            pass
    sub.free()


def collar(bm, body, draft):
    """A collar on the neckline (the open edges near the neck): a stand (`stand`), or a stand
    turned down over the shoulders (`fold`)."""
    kind = draft.get("collar")
    if not kind:
        return
    L = layers(bm)
    o = body.outfit["neck"] if body.outfit else None
    zmin = body.z["neck"] - 0.07

    def near_neck(p):
        if o is None:
            return p.z > zmin
        dy = p.y - o["cy"]
        r = math.sqrt((p.x / (o["rx"] + 0.03)) ** 2 + (dy / ((o["ryf"] if dy < 0 else o["ryb"]) + 0.03)) ** 2)
        return r < 1.35 and p.z > zmin
    edges = [e for e in bm.edges if e.is_boundary and all(near_neck(v.co) for v in e.verts)
             and (e.verts[0].co - e.verts[1].co).length < 0.06]
    if not edges:
        return
    nb = body.bones["neck_01"]
    up = (body.bones["head"] - nb).normalized()
    h = 0.026 if kind == "stand" else 0.018
    top, low = {}, {}
    for e in edges:
        for v in e.verts:
            if v in top:
                continue
            d = Vector((v.co.x - nb.x, v.co.y - nb.y, 0.0))
            dn = d.normalized() if d.length > 1e-6 else Vector((1, 0, 0))
            t = bm.verts.new(v.co + up * h + dn * 0.006)
            put(t, L, ("collar", "", v.co.z))
            top[v] = t
            if kind == "fold":
                w = bm.verts.new(t.co + dn * 0.035 - up * 0.03)
                put(w, L, ("collar", "", v.co.z))
                low[v] = w
    for e in edges:
        a, b = e.verts
        for quad in ((a, b, top[b], top[a]),) + (((top[a], top[b], low[b], low[a]),) if low else ()):
            try:
                bm.faces.new(quad)
            except ValueError:
                pass


# ------------------------------------------------------------------------------------------
# the drape
# ------------------------------------------------------------------------------------------

def to_object(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def labels_of(ob):
    me = ob.data
    pa = me.attributes["part"].data
    sa = me.attributes["side"].data
    ta = me.attributes["t"].data
    return [(PARTS[pa[i].value], SIDES[sa[i].value], ta[i].value) for i in range(len(me.vertices))]


def drape(ob, man, draft):
    """The cloth solver: the garment settles on the mannequin under gravity; fitted parts held
    by goal springs (the pin group's weight), loose parts free."""
    frames = draft.get("frames", FRAMES)
    if frames <= 0:
        return 0.0
    lab = labels_of(ob)
    before = [v.co.copy() for v in ob.data.vertices]
    vg = ob.vertex_groups.new(name="pin")
    loose = set(draft.get("loose", ())) | {"skirt", "hood"}
    for i, lb in enumerate(lab):
        w = 0.0 if lb[0] in loose else (0.55 if lb[0] in ("farm", "calf") else 0.8)
        vg.add([i], w, "REPLACE")
    if not any(m.type == "COLLISION" for m in man.modifiers):
        man.modifiers.new("col", "COLLISION")
        man.collision.thickness_outer = 0.004
        man.collision.cloth_friction = 8.0
    m = ob.modifiers.new("cloth", "CLOTH")
    s = m.settings
    s.quality = 5
    s.mass = 0.12
    s.tension_stiffness = s.compression_stiffness = 18.0
    s.shear_stiffness = 8.0
    s.bending_stiffness = draft.get("bend", 0.6)
    s.air_damping = 2.0
    s.vertex_group_mass = "pin"
    s.pin_stiffness = 3.0
    cs = m.collision_settings
    cs.distance_min = draft.get("col", 0.004)
    cs.collision_quality = 3
    cs.use_self_collision = False
    m.point_cache.frame_start = 1
    m.point_cache.frame_end = frames
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = 1, frames
    t = time.time()
    for f in range(1, frames + 1):
        scn.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)
    scn.frame_set(1)
    # (a vertex the solver threw far, caught between the legs or the arm and the side, goes
    # back to where it was)
    far = [i for i, (v, p, lb) in enumerate(zip(ob.data.vertices, before, lab))
           if (v.co - p).length > (MAX_MOVE["loose"] if lb[0] in loose else MAX_MOVE["fit"])]
    dropped = len(far) > 0.004 * len(before)
    for i in (range(len(before)) if dropped else far):
        ob.data.vertices[i].co = before[i]
    return {"s": round(time.time() - t, 1), "reverted": len(far), "dropped": dropped}


# ------------------------------------------------------------------------------------------
# finish: UVs, colors, slots
# ------------------------------------------------------------------------------------------

def pattern_uv(body, lb, p):
    """A point's place on its pattern piece (m): round its part and along it, and its angle."""
    part, side = lb[0], lb[1]
    if part in LIMB and side:
        a, b, c = body.limb(LIMB[part], side)
        ax = (c - a).normalized()
        ref = Vector((0, -1, 0))
        ref = (ref - ax * ref.dot(ax)).normalized()
        oth = ax.cross(ref)
        d = p - a
        ang = math.atan2(d.dot(oth), d.dot(ref))
        r = 0.05 if LIMB[part] == "arm" else 0.08
        return ang * r, d.dot(ax), ang, r
    if part in ("hood", "head", "acc"):
        d = p - body.bones["head"]
        ang = math.atan2(d.x, -d.y)
        return ang * 0.1, d.z, ang, 0.1
    c = body.center
    ang = math.atan2(p.x - c.x, -(p.y - c.y))      # 0 at the front, +-pi at the back
    return ang * 0.16, p.z, ang, 0.16


def finish(ob, body, draft, slots):
    """UVs from the pattern pieces, the material slots (textile, trims) and the vertex colors
    (rgb a multiplier, alpha the dye channel: 0 none, 1/3, 2/3, 1 the person's three)."""
    me = ob.data
    lab = labels_of(ob)
    uvl = me.uv_layers.new(name="UVMap")
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    a_code = {0: 1.0 / 3.0, 1: 2.0 / 3.0, 2: 1.0}.get(draft.get("channel", -1), 0.0)
    trims = draft.get("trims", [])
    for poly in me.polygons:
        lbs = [lab[i] for i in poly.vertices]
        lb = max(set(lbs), key=lbs.count)
        uvs = [pattern_uv(body, lb, me.vertices[me.loops[li].vertex_index].co)
               for li in poly.loop_indices]
        angs = [u[2] for u in uvs]
        if max(angs) - min(angs) > math.pi:          # (across the seam at the back)
            uvs = [(u + 2 * math.pi * r, v, a + 2 * math.pi, r) if a < 0 else (u, v, a, r)
                   for u, v, a, r in uvs]
        for li, (u, v, _, _) in zip(poly.loop_indices, uvs):
            uvl.data[li].uv = (u, v)
        slot, rgb, dyed = 0, draft.get("rgb", 1.0), a_code
        for t in trims:
            if trim_hit(t, poly.center, lb, body):
                slot = slots.index(t["textile"])
                rgb = t.get("rgb", 1.0)
                dyed = a_code if t.get("dyed") else 0.0
                break
        poly.material_index = slot
        c3 = rgb if isinstance(rgb, (list, tuple)) else (rgb, rgb, rgb)
        for li in poly.loop_indices:
            col.data[li].color = (c3[0], c3[1], c3[2], dyed)


def trim_hit(t, c, lb, body):
    w = t["where"]
    part = lb[0]
    if w == "front":
        return abs(c.x) < t.get("width", 0.02) and c.y < body.center.y and \
            part in ("torso", "neck", "skirt", "collar")
    if w == "hem":
        return part in ("torso", "skirt") and t["z"] - 0.02 < c.z < t["z"] + t.get("width", 0.05)
    if w == "cuff":
        return LIMB.get(part) == "arm" and lb[2] > t["t"] - t.get("width", 0.05) / 0.6
    if w == "ankle":
        return LIMB.get(part) == "leg" and c.z < t["z"] + t.get("width", 0.05)
    if w == "band_arm":
        return part in ("uarm", "farm") and abs(lb[2] - t["t"]) < t.get("width", 0.03) / 1.2
    if w == "band_leg":
        return LIMB.get(part) == "leg" and abs(c.z - t["z"]) < t.get("width", 0.03) / 2
    if w == "band_torso":
        return part in ("torso", "skirt") and abs(c.z - t["z"]) < t.get("width", 0.03) / 2
    if w == "collar":
        return part == "collar"
    if w == "hood":
        return part == "hood"
    if w == "sole":
        return c.z < t.get("z", 0.025)
    if w == "toe":
        return c.z < t.get("z", 0.05) and c.y < t.get("y", 0.0)
    if w == "pocket":
        sx = abs(c.x)
        return part in t.get("parts", ("torso", "thigh")) and t["x0"] < sx < t["x1"] and \
            t["z0"] < c.z < t["z1"] and ((c.y < body.center.y) == t.get("front", True))
    if w == "side_pocket":           # a cargo pocket on the outer thigh
        return part == "thigh" and t["z0"] < c.z < t["z1"] and abs(c.x) > t["x0"]
    return False


def rim(ob, thick):
    """A rim of the cloth's thickness at every open edge (hems, cuffs, openings)."""
    if thick <= 0:
        return
    me = ob.data
    n0 = len(me.vertices)
    vcol = {}
    if "Col" in me.color_attributes:
        col = me.color_attributes["Col"].data
        for li, lp in enumerate(me.loops):
            vcol.setdefault(lp.vertex_index, tuple(col[li].color))
    m = ob.modifiers.new("rim", "SOLIDIFY")
    m.thickness = thick
    m.offset = -1.0
    m.use_rim = True
    m.use_rim_only = True
    select_only(ob)
    bpy.ops.object.modifier_apply(modifier="rim")
    # (the rim's corners take the colors of the edge they hang from: the solidify leaves them
    # unset, which read as undyed white)
    me = ob.data
    if vcol and "Col" in me.color_attributes:
        col = me.color_attributes["Col"].data
        for poly in me.polygons:
            known = [vcol[me.loops[li].vertex_index] for li in poly.loop_indices
                     if me.loops[li].vertex_index < n0 and me.loops[li].vertex_index in vcol]
            if not known:
                continue
            for li in poly.loop_indices:
                c = tuple(col[li].color)
                if c == (0.0, 0.0, 0.0, 0.0) or me.loops[li].vertex_index >= n0:
                    col[li].color = vcol.get(me.loops[li].vertex_index, known[0])


def set_slots(ob, slots):
    ob.data.materials.clear()
    for s in slots:
        ob.data.materials.append(bpy.data.materials.get(s) or bpy.data.materials.new(s))


def tag_object(ob, layer, rigid_bone=-1, rigid_w=None):
    """Per-vertex attributes a look keeps through its joins: the garment's layer and the bone
    a vertex is held to (`rb` its index + 1 in the job's bone list, 0 none; `rw` how much)."""
    me = ob.data
    n = len(me.vertices)
    for name, typ in (("layer", "FLOAT"), ("rb", "FLOAT"), ("rw", "FLOAT")):
        if name not in me.attributes:
            me.attributes.new(name, typ, "POINT")
    me.attributes["layer"].data.foreach_set("value", [float(layer)] * n)
    me.attributes["rb"].data.foreach_set("value", [float(rigid_bone + 1)] * n)
    me.attributes["rw"].data.foreach_set("value", list(rigid_w) if rigid_w else [0.0] * n)


# ------------------------------------------------------------------------------------------
# a garment
# ------------------------------------------------------------------------------------------

def build_garment(space, man, draft, slots, bone_ix):
    t0 = time.time()
    body = space.body
    if draft["kind"] in ("sneakers", "boots", "dress_shoes"):
        ob = shoes(space, draft, slots)
        tag_object(ob, LAYER_ORDER["shoes"])
        return ob, {"s": round(time.time() - t0, 1), "tris": tris_of(ob)}
    bm = region(space, draft)
    offset(bm, space, draft)
    apply_cuts(bm, body, draft)
    flare(bm, space, draft)
    collar(bm, body, draft)
    hood(bm, space, body, draft)
    ob = to_object(draft["id"], bm)
    bm.free()
    info = drape(ob, man, draft)
    set_slots(ob, slots)
    finish(ob, body, draft, slots)
    # (a hood up follows the head: held to the head bone, more the higher up)
    lab = labels_of(ob)
    hb = bone_ix.get("head", -1)
    rw = [max(0.0, min(1.0, (lb[2] - body.z["neck"]) / 0.08)) if lb[0] == "hood" and
          draft.get("hood") == "up" else 0.0 for lb in lab]
    tag_object(ob, LAYER_ORDER[draft["layer"]], hb if any(rw) else -1, rw)
    rim(ob, draft.get("thick", 0.003))
    select_only(ob)
    bpy.ops.object.shade_smooth()
    return ob, {"drape": info, "s": round(time.time() - t0, 1), "tris": tris_of(ob)}


def tris_of(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def shoes(space, draft, slots):
    """Shoes from the feet: the foot's surface up to the shoe's top, offset, its sole flat at
    the ground (the body stands at z 0, so the sole lies inside the foot's bottom), a sole
    slot below `sole_z`, toe caps."""
    body = space.body
    top = draft["top_z"]
    bm = bmesh.new()
    L = layers(bm)
    vm = {}
    for tri in space.tris:
        ps = [space.co[i] for i in tri]
        if max(p.z for p in ps) > top + 0.02:
            continue
        if not all(space.lab[i][0] in ("foot", "calf") for i in tri):
            continue
        vs = []
        for i in tri:
            if i not in vm:
                p, n = space.co[i], space.no[i]
                q = p + n * draft["ease"]["leg"]
                q.z = max(q.z, 0.003)
                v = bm.verts.new(q)
                put(v, L, space.lab[i], i)
                vm[i] = v
            vs.append(vm[i])
        try:
            bm.faces.new(vs)
        except ValueError:
            pass
    cut(bm, Vector((0, 0, top)), Vector((0, 0, 1)))
    drop_small(bm, 20)
    ob = to_object(draft["id"], bm)
    bm.free()
    set_slots(ob, slots)
    finish(ob, body, draft, slots)
    rim(ob, draft.get("thick", 0.004))
    select_only(ob)
    bpy.ops.object.shade_smooth()
    return ob


# ------------------------------------------------------------------------------------------
# accessories (hard-surface, rigid on a bone; arm plates follow the skin)
# ------------------------------------------------------------------------------------------

def _box(bm, L, c, ax, ay, az, lab=("acc", "", 0.0)):
    """A box centred at c with half axes ax, ay, az (vectors)."""
    vs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                v = bm.verts.new(c + ax * sx + ay * sy + az * sz)
                put(v, L, lab)
                vs.append(v)
    idx = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
    out = []
    for q in idx:
        try:
            out.append(bm.faces.new([vs[i] for i in q]))
        except ValueError:
            pass
    return out


def _band(bm, L, c, r, z0, z1, a0, a1, thick, segs=24, ry=None):
    """A band round a vertical axis through c (radius r, ry front to back), from angle a0 to
    a1 (0 at the front), heights z0 to z1, `thick` deep; its faces."""
    ry = ry or r
    rows = []
    for rr, sc in ((0.0, 1.0), (thick, 1.0)):
        ring = []
        for i in range(segs + 1):
            a = a0 + (a1 - a0) * i / segs
            dx, dy = math.sin(a) * (r + rr), -math.cos(a) * (ry + rr)
            col = []
            for z in (z0, z1):
                v = bm.verts.new(Vector((c.x + dx, c.y + dy, z)))
                put(v, L, ("acc", "", z))
                col.append(v)
            ring.append(col)
        rows.append(ring)
    fs = []
    inner, outer = rows
    for i in range(segs):
        for q in ((outer[i][0], outer[i + 1][0], outer[i + 1][1], outer[i][1]),
                  (inner[i][1], inner[i + 1][1], inner[i + 1][0], inner[i][0]),
                  (inner[i][1], outer[i][1], outer[i + 1][1], inner[i + 1][1]),
                  (inner[i][0], inner[i + 1][0], outer[i + 1][0], outer[i][0])):
            try:
                fs.append(bm.faces.new(q))
            except ValueError:
                pass
    for i in (0, segs):
        q = (inner[i][0], outer[i][0], outer[i][1], inner[i][1])
        try:
            fs.append(bm.faces.new(q if i == 0 else tuple(reversed(q))))
        except ValueError:
            pass
    return fs


def _shell(space, L, bm, test, off, part="acc"):
    """The mannequin's faces whose vertices pass `test`, offset by `off`: a shell on the body."""
    vm = {}
    fs = []
    for tri in space.tris:
        if not all(test(space.co[i], space.lab[i]) for i in tri):
            continue
        vs = []
        for i in tri:
            if i not in vm:
                v = bm.verts.new(space.co[i] + space.no[i] * off)
                put(v, L, (part, space.lab[i][1], space.lab[i][2]), i)
                vm[i] = v
            vs.append(vm[i])
        try:
            fs.append(bm.faces.new(vs))
        except ValueError:
            pass
    return fs


def build_accessory(space, acc, bone_ix):
    """An accessory: its object (slots: the accessory's materials), rigid on its bone."""
    body = space.body
    H = body.head
    bm = bmesh.new()
    L = layers(bm)
    kind = acc["kind"]
    c = Vector((0.0, H["cy"], 0.0))
    eye = H["eye"]
    rx = H["rx"]
    slot_of = {}            # face -> slot index
    bone = "head"
    skin = False

    def mark(fs, k):
        for f in fs:
            slot_of[f] = k

    if kind == "visor":
        mark(_band(bm, L, c, rx + 0.016, eye - 0.022, eye + 0.025, -1.25, 1.25, 0.004,
                   ry=(c.y - H["front"]) + 0.012), 0)
        mark(_band(bm, L, c, rx + 0.021, eye - 0.026, eye - 0.019, -1.2, 1.2, 0.003,
                   ry=(c.y - H["front"]) + 0.017), 1)
    elif kind == "headset":
        mark(_band(bm, L, Vector((0, c.y, 0)), rx + 0.012, eye + 0.02, eye + 0.04,
                   -math.pi / 2, math.pi / 2, 0.006, ry=rx + 0.012), 0)
        for s in (-1, 1):
            mark(_box(bm, L, Vector((s * (rx + 0.012), c.y + 0.005, eye - 0.02)),
                      Vector((0.012, 0, 0)), Vector((0, 0.03, 0)), Vector((0, 0, 0.032))), 0)
            mark(_box(bm, L, Vector((s * (rx + 0.025), c.y + 0.005, eye - 0.02)),
                      Vector((0.002, 0, 0)), Vector((0, 0.02, 0)), Vector((0, 0, 0.02))), 1)
        # (the band over the head: a strip of the head's top)
        mark(_shell(space, L, bm, lambda p, lb: lb[0] == "head" and abs(p.x) < 0.02 * 0 + 1
                    and abs(p.y - c.y) < 0.018 and p.z > eye + 0.02, 0.012), 0)
    elif kind in ("cap", "beanie", "hardhat"):
        z0 = eye + (0.035 if kind == "cap" else 0.012 if kind == "beanie" else 0.04)
        off = {"cap": 0.014, "beanie": 0.012, "hardhat": 0.03}[kind]
        mark(_shell(space, L, bm, lambda p, lb: lb[0] == "head" and p.z > z0, off), 0)
        if kind == "cap":
            fs = []
            n = 12
            ring0, ring1 = [], []
            for i in range(n + 1):
                a = -1.1 + 2.2 * i / n
                for rr, ring in ((0.0, ring0), (0.075, ring1)):
                    v = bm.verts.new(Vector((math.sin(a) * (rx + 0.01 + rr * 0.6),
                                             c.y - math.cos(a) * (c.y - H["front"] + 0.01 + rr),
                                             z0 + 0.002 - rr * 0.12)))
                    put(v, L, ("acc", "", z0))
                    ring.append(v)
            for i in range(n):
                try:
                    fs.append(bm.faces.new((ring0[i], ring0[i + 1], ring1[i + 1], ring1[i])))
                except ValueError:
                    pass
            mark(fs, 1)
        if kind == "hardhat":
            fs = _band(bm, L, c, rx + 0.045, z0 - 0.004, z0 + 0.004, -math.pi, math.pi, 0.02,
                       segs=32, ry=(c.y - H["front"]) + 0.045)
            mark(fs, 0)
    elif kind == "respirator":
        f0 = H["front"]
        mz = eye - 0.075
        mark(_box(bm, L, Vector((0, f0 - 0.012, mz)), Vector((0.032, 0, 0)),
                  Vector((0, 0.018, 0)), Vector((0, 0, 0.03))), 0)
        for s in (-1, 1):
            mark(_box(bm, L, Vector((s * 0.045, f0 + 0.004, mz - 0.012)),
                      Vector((0.016, 0, 0)), Vector((0, 0.016, 0)), Vector((0, 0, 0.018))), 1)
        mark(_band(bm, L, c, rx + 0.008, mz + 0.01, mz + 0.022, 1.3, 2 * math.pi - 1.3, 0.003,
                   ry=(H["back"] - c.y) + 0.008), 0)
    elif kind == "mask":
        mark(_shell(space, L, bm, lambda p, lb: lb[0] == "head" and eye - 0.13 < p.z < eye - 0.03
                    and p.y < c.y - 0.02, 0.008), 0)
    elif kind == "implant":
        s = 1 if acc.get("side", "l") == "l" else -1
        mark(_shell(space, L, bm, lambda p, lb: lb[0] == "head" and s * p.x > rx - 0.025 and
                    eye - 0.01 < p.z < eye + 0.05 and abs(p.y - c.y) < 0.035, 0.004), 0)
        mark(_shell(space, L, bm, lambda p, lb: lb[0] == "head" and s * p.x > rx - 0.022 and
                    eye + 0.012 < p.z < eye + 0.017 and abs(p.y - c.y) < 0.03, 0.0055), 1)
    elif kind == "armplates":
        skin = True
        bone = None
        for k, (t0, t1) in enumerate(((0.62, 0.70), (0.72, 0.80), (0.82, 0.9))):
            mark(_shell(space, L, bm, lambda p, lb, t0=t0, t1=t1: lb[0] == "farm" and
                        lb[1] == acc.get("side", "l") and t0 < lb[2] < t1, 0.005), 0)
        mark(_shell(space, L, bm, lambda p, lb: lb[0] == "farm" and lb[1] == acc.get("side", "l")
                    and (0.705 < lb[2] < 0.715 or 0.805 < lb[2] < 0.815), 0.0065), 1)
    elif kind == "backpack":
        bone = "spine_04"
        B = body.bones
        back = max(p.y for p, lb in zip(space.co, space.lab)
                   if lb[0] == "torso" and abs(p.z - body.z["chest"]) < 0.04)
        mark(_box(bm, L, Vector((0, back + 0.085, body.z["chest"] - 0.02)),
                  Vector((0.14, 0, 0)), Vector((0, 0.06, 0)), Vector((0, 0, 0.19))), 0)
        mark(_box(bm, L, Vector((0, back + 0.15, body.z["chest"] - 0.08)),
                  Vector((0.11, 0, 0)), Vector((0, 0.012, 0)), Vector((0, 0, 0.08))), 1)
    elif kind == "bag":
        bone = "spine_02"
        side = -1
        hipx = max(abs(p.x) for p, lb in zip(space.co, space.lab)
                   if lb[0] in ("torso", "thigh") and abs(p.z - body.z["hip"]) < 0.03)
        back = max(p.y for p, lb in zip(space.co, space.lab)
                   if lb[0] == "torso" and abs(p.z - body.z["hip"]) < 0.04)
        mark(_box(bm, L, Vector((side * (hipx - 0.02), back + 0.05, body.z["hip"])),
                  Vector((0.12, 0, 0)), Vector((0, 0.04, 0)), Vector((0, 0, 0.09))), 0)
    else:
        raise ValueError(f"no accessory {kind}")
    for f, k in slot_of.items():
        f.material_index = k
    ob = to_object(acc["id"], bm)
    bm.free()
    set_slots(ob, acc["slots"])
    me = ob.data
    uvl = me.uv_layers.new(name="UVMap")
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    for poly in me.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            p = me.vertices[me.loops[li].vertex_index].co
            uvl.data[li].uv = (p.x + p.y * abs(n.x), p.z + p.y * abs(n.z))
            rgb = acc.get("rgb", [1.0, 1.0, 1.0])
            col.data[li].color = (rgb[0], rgb[1], rgb[2],
                                  {0: 1 / 3, 1: 2 / 3, 2: 1.0}.get(acc.get("channel", -1), 0.0)
                                  if poly.material_index == 0 else 0.0)
    if skin:
        tag_object(ob, LAYER_ORDER["skin"])
    else:
        tag_object(ob, LAYER_ORDER["acc"], bone_ix.get(bone, -1), [1.0] * len(me.vertices))
    select_only(ob)
    bpy.ops.object.shade_flat()
    return ob


# ------------------------------------------------------------------------------------------
# looks
# ------------------------------------------------------------------------------------------

def copy_object(ob, name):
    c = ob.copy()
    c.data = ob.data.copy()
    c.name = name
    bpy.context.scene.collection.objects.link(c)
    return c


def compose(look, obs, accs, slots):
    """A look: copies of its garments and accessories joined (each slot renamed to the
    library's), the faces of a layer another covers taken out."""
    parts = []
    for gid in look["garments"]:
        parts.append(copy_object(obs[gid], f"{look['id']}.{gid}"))
    for aid in look.get("accessories", []):
        parts.append(copy_object(accs[aid], f"{look['id']}.{aid}"))
    # (a piece its cuts left empty, as an accessory on a head too small for it, is left out)
    empty = [p for p in parts if not p.data.vertices]
    for p in empty:
        parts.remove(p)
        bpy.data.objects.remove(p)
    layered(parts, look)
    for k, p in enumerate(parts):
        me = p.data
        if "piece" not in me.attributes:
            me.attributes.new("piece", "FLOAT", "POINT")
        me.attributes["piece"].data.foreach_set("value", [float(k)] * len(me.vertices))
    # (one slot list for the look: each part's slots remapped onto it)
    for p in parts:
        names = [m.name for m in p.data.materials]
        remap = [slots.index(n) for n in names]
        idx = [0] * len(p.data.polygons)
        p.data.polygons.foreach_get("material_index", idx)
        p.data.materials.clear()
        for s in slots:
            p.data.materials.append(bpy.data.materials.get(s) or bpy.data.materials.new(s))
        p.data.polygons.foreach_set("material_index", [remap[i] for i in idx])
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = look["id"]
    removed = hide_covered(ob)
    return ob, removed


LAYER_GAP = 0.004


def layered(parts, look):
    """Each garment outside the ones under it: inner to outer (shoes, bottoms, the base top,
    the outer layer; a tucked top under its bottoms), every vertex of a layer pushed out to
    `LAYER_GAP` over the layers before it where it comes closer or lies inside them."""
    def order(p):
        v = p.data.attributes["layer"].data[0].value
        if look.get("tucked") and abs(v - LAYER_ORDER["base"]) < 0.01:
            return LAYER_ORDER["bottom"] - 0.5
        return v
    garments = sorted([p for p in parts if order(p) < LAYER_ORDER["acc"] - 0.01], key=order)
    done = []
    for p in garments:
        if done and order(p) > LAYER_ORDER["skin"]:
            co, tris = [], []
            for q in done:
                base = len(co)
                co += [v.co.copy() for v in q.data.vertices]
                tris += [tuple(base + i for i in f.vertices) for f in q.data.polygons]
            bvh = BVHTree.FromPolygons(co, tris)
            for v in p.data.vertices:
                q, n, _, d = bvh.find_nearest(v.co, 0.05)
                if q is None:
                    continue
                if (v.co - q).dot(n) < LAYER_GAP:
                    v.co = q + n * LAYER_GAP
        done.append(p)


def hide_covered(ob):
    """Takes out each face another piece covers: from its middle and its corners, along its
    normal, every ray meets another piece within `COVER_M`."""
    me = ob.data
    piece = [0.0] * len(me.vertices)
    me.attributes["piece"].data.foreach_get("value", piece)
    co = [v.co.copy() for v in me.vertices]
    tris = [tuple(p.vertices) for p in me.polygons]
    bvh = BVHTree.FromPolygons(co, [t for t in tris])
    fpiece = [piece[t[0]] for t in tris]
    drop = []
    for fi, poly in enumerate(me.polygons):
        n = poly.normal
        pts = [poly.center] + [co[i] * 0.8 + poly.center * 0.2 for i in poly.vertices]
        covered = True
        for p in pts:
            o = p + n * 0.0015
            hit = bvh.ray_cast(o, n, COVER_M)
            # (past hits of its own piece: a hood over its own shoulders)
            tries = 0
            while hit[0] is not None and fpiece[hit[2]] == fpiece[fi] and tries < 4:
                hit = bvh.ray_cast(hit[0] + n * 0.0015, n, COVER_M - (hit[0] - o).length)
                tries += 1
            if hit[0] is None or fpiece[hit[2]] == fpiece[fi]:
                covered = False
                break
        if covered:
            drop.append(fi)
    if drop:
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in drop], context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(me)
        bm.free()
        me.update()
    return len(drop)


def coverage(look_ob, data):
    """The share of the plain outfit's vertices (where the body has no skin) a look covers:
    out along the outfit's normals each meets the look within 0.2 m."""
    me = look_ob.data
    bvh = BVHTree.FromPolygons([v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    of = mesh_from("_outfit", data["outfit"])
    hit = tot = 0
    miss = []
    for v in of.data.vertices:
        tot += 1
        n = v.normal
        if bvh.ray_cast(v.co, n, 0.2)[0] is not None or bvh.ray_cast(v.co, -n, 0.2)[0] is not None:
            hit += 1
        else:
            miss.append(round(v.co.z, 2))
    bpy.data.objects.remove(of)
    zs = {}
    for z in miss:
        zs[round(z, 1)] = zs.get(round(z, 1), 0) + 1
    return hit / max(1, tot), dict(sorted(zs.items()))


def decimated(ob, ratio, name):
    c = copy_object(ob, name)
    if ratio < 1.0:
        m = c.modifiers.new("dec", "DECIMATE")
        m.ratio = ratio
        m.use_collapse_triangulate = True
        select_only(c)
        bpy.ops.object.modifier_apply(modifier="dec")
    return c


def export(ob, path, slots, bones, mid_colors=None, glow=()):
    """The object as the editor builds it (`people_library.make_looks`): unique corners
    (position, normal, uv, color) as vertices in Unreal's frame (cm, y negated, uv v
    negated), each triangle's slot, each vertex's rigid bone and weight.
    For the mid mesh (`mid_colors`) each slot's mean color goes into the vertex colors and the
    slots fold into `cloth` and `glow`."""
    me = ob.data
    me.calc_loop_triangles()
    uvl = me.uv_layers.active.data
    col = me.color_attributes["Col"].data
    nrm = me.corner_normals
    rb = me.attributes["rb"].data
    rw = me.attributes["rw"].data
    key_of = {}
    V, N, U, C, R, W, T, M = [], [], [], [], [], [], [], []
    out_slots = ["cloth", "glow"] if mid_colors is not None else list(slots)
    for lt in me.loop_triangles:
        slot = slots[lt.material_index]
        ms = (1 if slot in glow else 0) if mid_colors is not None else lt.material_index
        tri = []
        for li in lt.loops:
            vi = me.loops[li].vertex_index
            uv = uvl[li].uv
            c = col[li].color
            n = nrm[li].vector
            if mid_colors is not None:
                m = mid_colors.get(slot, (0.5, 0.5, 0.5))
                c = (c[0] * m[0], c[1] * m[1], c[2] * m[2], c[3])
            k = (vi, round(uv[0], 4), round(uv[1], 4), round(c[0], 3), round(c[1], 3),
                 round(c[2], 3), round(c[3], 3), round(n[0], 2), round(n[1], 2), round(n[2], 2))
            j = key_of.get(k)
            if j is None:
                j = len(V) // 3
                key_of[k] = j
                V += bl_to_ue(me.vertices[vi].co)
                N += [round(n[0], 4), round(-n[1], 4), round(n[2], 4)]
                U += [round(uv[0], 4), round(-uv[1], 4)]
                C += [round(x, 4) for x in c]
                R.append(int(round(rb[vi].value)) - 1)
                W.append(round(rw[vi].value, 3))
            tri.append(j)
        T += tri
        M.append(ms)
    rec = {"slots": out_slots, "vertices": V, "normals": N, "uv0": U, "colors": C,
           "triangles": T, "mats": M, "rigid_bone": R, "rigid_w": W, "bones": bones}
    Path(path).write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    return {"verts": len(V) // 3, "tris": len(T) // 3}


# ------------------------------------------------------------------------------------------
# renders (contact sheets)
# ------------------------------------------------------------------------------------------

def body_object(data):
    """The body as it is drawn (the assembled body with its holes and the face's skin), in a
    plain skin material, for the renders."""
    ob = mesh_from("skin_body", data["body"])
    fo = mesh_from("skin_face", data["face"], keep_mats={skin_material_id(data["face"])})
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    fo.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    bpy.ops.object.shade_smooth()
    ob.data.materials.clear()
    ob.data.materials.append(simple_material("skin_mat", (0.55, 0.40, 0.32), 0.5))
    ob.hide_render = True
    return ob


def simple_material(name, rgb, rough, use_vcol=False, emit=0.0):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs["Roughness"].default_value = rough
    if use_vcol:
        a = nt.nodes.new("ShaderNodeVertexColor")
        a.layer_name = "Col"
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs["A"].default_value = (*rgb, 1.0)
        nt.links.new(a.outputs["Color"], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    else:
        p.inputs["Base Color"].default_value = (*rgb, 1.0)
    if emit > 0:
        p.inputs["Emission Color"].default_value = (*rgb, 1.0)
        p.inputs["Emission Strength"].default_value = emit
    return m


_STAGE = {}


def stage(size=(520, 760)):
    """Lights, world and camera, made once."""
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = size
    if _STAGE:
        return _STAGE
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 24
    scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scn.cycles.device = "GPU"
    except Exception:                                               # noqa: BLE001
        scn.cycles.device = "CPU"
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.055, 0.065, 1)
    scn.world = w
    for name, loc, energy, sz in (("key", (2.0, -3.0, 3.2), 700, 2.5),
                                  ("rim", (-2.5, 2.5, 2.8), 400, 2.0),
                                  ("fill", (-2.5, -2.5, 1.2), 200, 3.0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size = energy, sz
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scn.collection.objects.link(lo)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 50
    scn.collection.objects.link(cam)
    scn.camera = cam
    _STAGE["cam"] = cam
    return _STAGE


VIEWS = (("front", (0.0, -4.6, 1.0)), ("34", (3.1, -3.4, 1.25)))


def dye_material(name, rgb, rough, dyes, emit=0.0):
    """A preview material: the textile's mean color times the vertex color, the dye channel
    (vertex alpha) picking one of the look's three preview colors."""
    key = name + "|" + "|".join(",".join(f"{x:.2f}" for x in d) for d in dyes)
    m = bpy.data.materials.get(key)
    if m is not None:
        return m
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs["Roughness"].default_value = rough
    a = nt.nodes.new("ShaderNodeVertexColor")
    a.layer_name = "Col"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (1, 1, 1, 1)
    els[1].position, els[1].color = 0.2, (*dyes[0], 1)
    for pos, c in ((0.5, dyes[1]), (0.85, dyes[2])):
        e = els.new(pos)
        e.color = (*c, 1)
    nt.links.new(a.outputs["Alpha"], ramp.inputs["Fac"])
    m1 = nt.nodes.new("ShaderNodeMix")
    m1.data_type, m1.blend_type = "RGBA", "MULTIPLY"
    m1.inputs["Factor"].default_value = 1.0
    nt.links.new(a.outputs["Color"], m1.inputs["A"])
    nt.links.new(ramp.outputs["Color"], m1.inputs["B"])
    m2 = nt.nodes.new("ShaderNodeMix")
    m2.data_type, m2.blend_type = "RGBA", "MULTIPLY"
    m2.inputs["Factor"].default_value = 1.0
    m2.inputs["A"].default_value = (*rgb, 1)
    nt.links.new(m1.outputs["Result"], m2.inputs["B"])
    nt.links.new(m2.outputs["Result"], p.inputs["Base Color"])
    if emit > 0:
        nt.links.new(m2.outputs["Result"], p.inputs["Emission Color"])
        p.inputs["Emission Strength"].default_value = emit
    return m


def render_set(objs, path, colors, views=VIEWS, size=(520, 760), target=0.92, dyes=None):
    st = stage(size)
    scn = bpy.context.scene
    shown = set(objs)
    for o in scn.objects:
        if o.type == "MESH":
            o.hide_render = o not in shown
    for o in objs:
        for i, m in enumerate(o.data.materials):
            if m is None or m.name == "skin_mat":
                continue
            c = colors.get(m.name, {"rgb": (0.5, 0.5, 0.52), "rough": 0.7})
            d = dyes or ((0.2, 0.3, 0.45), (0.12, 0.12, 0.13), (0.25, 0.22, 0.18))
            o.data.materials[i] = dye_material("v_" + m.name, tuple(c["rgb"]),
                                               c.get("rough", 0.7), d, emit=c.get("emit", 0.0))
    cam = st["cam"]
    files = []
    for name, eye in views:
        cam.location = eye
        cam.rotation_euler = (Vector((0, 0, target)) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
        scn.render.filepath = f"{path}_{name}.jpg"
        bpy.ops.render.render(write_still=True)
        files.append(scn.render.filepath)
    return files


# ------------------------------------------------------------------------------------------
# job
# ------------------------------------------------------------------------------------------

def main():
    job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    out = Path(job["out"])
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = json.loads(Path(job["body"]).read_text(encoding="utf-8"))
    t = time.time()
    body = Body(data)
    man = mannequin(data)
    space = Space(body, man)
    space.measure_outfit(data)
    log(f"mannequin {len(space.co)} verts, {len(space.tris)} faces, {time.time() - t:.1f} s")
    bones = job.get("bones") or ["head", "spine_04", "spine_02"]
    bone_ix = {b: i for i, b in enumerate(bones)}
    rep = {"character": job["character"], "garments": {}, "looks": {},
           "head": {k: round(v, 4) for k, v in body.head.items()},
           "z": {k: round(v, 4) for k, v in body.z.items()}}
    obs, accs = {}, {}
    for g in job["garments"]:
        slots = list(dict.fromkeys([g["textile"]] + [t["textile"] for t in g.get("trims", [])]))
        ob, info = build_garment(space, man, g, slots, bone_ix)
        ob.hide_render = True
        obs[g["id"]] = ob
        rep["garments"][g["id"]] = info
        log(f"garment {g['id']} {info}")
    for a in job.get("accessories", []):
        accs[a["id"]] = build_accessory(space, a, bone_ix)
        accs[a["id"]].hide_render = True
    colors = job.get("colors", {})
    skin = body_object(data) if job.get("render") else None
    if job.get("render") and job.get("render_garments", True):
        for g in job["garments"]:
            render_set([skin, obs[g["id"]]], out / f"g_{g['id']}", colors)
    glow = set(job.get("glow", ()))
    for look in job.get("looks", []):
        slots = []
        for gid in look["garments"]:
            slots += [m.name for m in obs[gid].data.materials]
        for aid in look.get("accessories", []):
            slots += [m.name for m in accs[aid].data.materials]
        slots = list(dict.fromkeys(slots))
        ob, removed = compose(look, obs, accs, slots)
        cov, miss = coverage(ob, data)
        info = {"hidden_faces": removed, "covers": round(cov, 4), "missed_z": miss,
                "tris": tris_of(ob)}
        info["near"] = export(ob, out / f"{look['id']}.near.json", slots, bones)
        l1 = decimated(ob, LOD1_RATIO, ob.name + "_lod1")
        info["lod1"] = export(l1, out / f"{look['id']}.lod1.json", slots, bones)
        mid = decimated(ob, min(1.0, MID_TRIS / max(1, tris_of(ob))), ob.name + "_mid")
        info["mid"] = export(mid, out / f"{look['id']}.mid.json", slots, bones,
                             mid_colors={k: v["rgb"] for k, v in colors.items()}, glow=glow)
        for o in (l1, mid):
            bpy.data.objects.remove(o)
        if job.get("render"):
            render_set([skin, ob], out / f"look_{look['id']}", colors, dyes=look.get("dyes"))
        ob.hide_render = True
        rep["looks"][look["id"]] = info
        log(f"look {look['id']} {info}")
    (out / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if job.get("save_blend"):
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "garments.blend"))
    print("CGGARMENT_DONE", flush=True)


if __name__ == "__main__":
    main()
