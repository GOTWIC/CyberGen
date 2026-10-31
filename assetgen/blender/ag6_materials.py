"""AG6's materials in Blender (stdlib and bpy only), node for node what the Unreal masters
compute (`citygen/ue/import_city.py`, `stage2_master`), so the previews show the textures:

- `facade`, `concrete`, `metal`, `foliage`: the set's maps on UV0 / TileM (offset per
  building by its seed), the tint over the set's tinted pixels (tint / ref where the mask is
  1), occlusion into the color, the macro map over world x, y / 64 m, grime from the ground
  up to the building's dirt height, rain streaks from the decal atlas below its top;
- `road`: the asphalt or paint set and, per 8 m cell of UV0, one stain of the road atlas
  (oil, cracks, patches, tar snakes, skid marks, a puddle, dust) where a hash says so;
- `glass`: reflective, with interior mapping: the building's room grid on UV0 (room width
  by floor height), the view ray into the room in the facade's frame (along the wall, up,
  into the wall), the hit point projected onto the interior atlas's one-point image, a room
  per cell by hash, its blinds, lit at night by the building's lit ratio;
- `neon`, `emissive`: emission; `sign`: an atlas page as emission; `translucent`;
- `leaves` (AG8's leaf cards): the leaf clump tile, tinted, cut by its leaf cover; `holo`
  (AG8's holo-ads): the holo ad page glowing, see-through by its brightness;
- `ground` (AG13): three sets (base, worn, shade) blended per pixel by the tile's mask on
  world x, y (wear and edges bare the worn set, broken up by the base set's height; shade
  and wet grow the shade set; wet darkens); `grass` (AG13's clumps): the slot's color toward
  its dry color by the vertex colors, darker at the root, two-sided.

A building's parameters come from the object's custom properties (`cg_wall`... tints from
the glTF node extras, the rest set by the preview script: `cg_room`, `cg_floorh`, `cg_row`,
`cg_streaks`, `cg_top`, `cg_blinds`, `cg_seed`, `cg_wear`, `cg_dirt`, `cg_lit`, `cg_neon`).
`NIGHT` (a node group value on every material, 0 by day, 1 by night) switches the lighting.
"""

import math

import bpy

IMAGES = {}
NIGHT = []                          # every Night value node, set by set_night()
ATTR = ["OBJECT"]                   # where `T.attr` reads: the object, or (AG2's part
                                    # instances, AG3's previews) the instance ("INSTANCER")


def image(path, color=True):
    key = (path, color)
    im = IMAGES.get(key)
    if im is None:
        im = bpy.data.images.load(path, check_existing=False)
        im.colorspace_settings.name = "sRGB" if color else "Non-Color"
        im.alpha_mode = "CHANNEL_PACKED"
        IMAGES[key] = im
    return im


class T:
    """A small node-tree builder."""

    def __init__(self, mat):
        self.nt = mat.node_tree
        self.n = self.nt.nodes
        self.l = self.nt.links

    def new(self, kind, **kw):
        node = self.n.new(kind)
        for k, v in kw.items():
            setattr(node, k, v)
        return node

    def link(self, a, b):
        self.l.new(a, b)

    def val(self, v):
        n = self.new("ShaderNodeValue")
        n.outputs[0].default_value = v
        return n.outputs[0]

    def _in(self, sock, v):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, (tuple, list)):
            sock.default_value = tuple(v)
        else:
            self.link(v, sock)

    def m(self, op, a, b=None, c=None):
        n = self.new("ShaderNodeMath", operation=op)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        if c is not None:
            self._in(n.inputs[2], c)
        return n.outputs[0]

    def v(self, op, a, b=None, scale=None):
        n = self.new("ShaderNodeVectorMath", operation=op)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        if scale is not None:
            self._in(n.inputs["Scale"], scale)
        return n.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else \
            n.outputs["Vector"]

    def xyz(self, vec):
        n = self.new("ShaderNodeSeparateXYZ")
        self._in(n.inputs[0], vec)
        return n.outputs["X"], n.outputs["Y"], n.outputs["Z"]

    def comb(self, x, y, z=0.0):
        n = self.new("ShaderNodeCombineXYZ")
        for s, v in zip(n.inputs, (x, y, z)):
            self._in(s, v)
        return n.outputs[0]

    def attr(self, name, out="Fac"):
        n = self.new("ShaderNodeAttribute", attribute_type=ATTR[0], attribute_name=name)
        return n.outputs[out]

    def mix(self, fac, a, b):
        n = self.new("ShaderNodeMix", data_type="RGBA")
        self._in(n.inputs["Factor"], fac)
        self._in(n.inputs["A"], a)
        self._in(n.inputs["B"], b)
        return n.outputs["Result"]

    def tex(self, path, vec, color=True, interp="Linear"):
        n = self.new("ShaderNodeTexImage", interpolation=interp)
        n.image = image(path, color)
        self._in(n.inputs["Vector"], vec)
        return n.outputs["Color"], n.outputs["Alpha"]

    def clamp(self, x, lo=0.0, hi=1.0):
        n = self.new("ShaderNodeClamp")
        self._in(n.inputs[0], x)
        n.inputs[1].default_value = lo
        n.inputs[2].default_value = hi
        return n.outputs[0]

    def hash3(self, vec):
        n = self.new("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
        self._in(n.inputs["Vector"], vec)
        return n.outputs["Value"]


def _night(t):
    n = t.new("ShaderNodeValue", label="Night")
    n.outputs[0].default_value = 0.0
    NIGHT.append(n)
    return n.outputs[0]


def set_night(v):
    for n in NIGHT:
        n.outputs[0].default_value = v


def srgb_linear(c):
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


LINEAR_PARTS = ("buildings", "connections", "props", "signs", "ground")  # (AG7: sRGB)


def _lin(rec, part):
    return rec["color"] if part in LINEAR_PARTS else srgb_linear(rec["color"])


def _tint(t, rec, part):
    """The tint (linear RGB) a textured material puts over its set's tinted pixels."""
    tc = rec.get("tint_cpd")
    if part == "buildings" and tc is not None and tc >= 0:
        name = {0: "cg_wall", 8: "cg_trim", 11: "cg_glass", 14: "cg_roof", 17: "cg_spandrel",
                20: "cg_patch"}[tc]
        col = t.attr(name, "Vector")
        if rec.get("tint_times_color"):
            col = t.v("MULTIPLY", t.v("SCALE", col, scale=rec.get("tint_scale", 1.0)),
                      tuple(rec["color"]))
        return col
    return tuple(_lin(rec, part))


def textured(mat, rec, files, part):
    """facade, concrete, metal, foliage, road."""
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    sc = rec.get("scalars", {})
    uvn = t.new("ShaderNodeUVMap", uv_map="UVMap")
    uv = uvn.outputs["UV"]
    seed = t.attr("cg_seed") if part == "buildings" else t.val(0.0)
    off = t.comb(t.m("MULTIPLY", seed, 37.3), t.m("MULTIPLY", seed, 71.9), 0.0)
    tuv = t.v("ADD", t.v("SCALE", uv, scale=1.0 / sc.get("TileM", 2.0)), off)
    tx = rec["textures"]
    base, height = t.tex(files[tx["BaseTex"]], tuv, True)
    nrm, _ = t.tex(files[tx["NormalTex"]], tuv, False)
    orm, mask = t.tex(files[tx["OrmTex"]], tuv, False)
    ao, rough, metal = t.xyz(orm)
    ref = rec.get("vectors", {}).get("RefColor", [0.2, 0.2, 0.2])          # linear
    tint = _tint(t, rec, part)
    ratio = t.v("DIVIDE", tint, tuple(max(c, 0.02) for c in ref))
    col = t.mix(mask, base, t.v("MULTIPLY", base, ratio))
    col = t.v("SCALE", col, scale=t.m("ADD", 0.35, t.m("MULTIPLY", ao, 0.65)))
    # macro variation over world x, y
    geo = t.new("ShaderNodeNewGeometry")
    wx, wy, wz = t.xyz(geo.outputs["Position"])
    mac, mac_a = t.tex(files[tx["Macro"]], t.comb(t.m("DIVIDE", wx, 64.0),
                                                  t.m("DIVIDE", wy, 64.0)), False)
    mr, mg, mb = t.xyz(mac)
    col = t.v("SCALE", col, scale=t.m("ADD", 0.86, t.m("MULTIPLY", mr, 0.28)))
    rough = t.m("ADD", rough, t.m("MULTIPLY", t.m("SUBTRACT", mg, 0.5), 0.12))
    # grime from the ground (object z, the building's pivot at its base)
    tco = t.new("ShaderNodeTexCoord")
    ox, oy, oz = t.xyz(tco.outputs["Object"])
    nz = t.xyz(geo.outputs["Normal"])[2]
    vert = t.m("SUBTRACT", 1.0, t.m("ABSOLUTE", nz))
    if part == "buildings":
        dirt = t.attr("cg_dirt")
        wear = t.attr("cg_wear")
    else:
        dirt, wear = t.val(0.8), t.val(0.5)
    g = t.clamp(t.m("SUBTRACT", 1.0, t.m("DIVIDE", oz, t.m("MAXIMUM", dirt, 0.1))))
    g = t.m("MULTIPLY", t.m("MULTIPLY", g, g), t.m("ADD", 0.25, t.m("MULTIPLY", wear, 0.6)))
    g = t.m("MULTIPLY", g, t.m("ADD", 0.5, mb))
    grime = (0.045, 0.04, 0.032, 1.0)
    col = t.mix(t.m("MULTIPLY", g, 0.75), col, grime)
    # rain streaks under the top (decal atlas, leaks cell: column 2, row 0, 1 m wide)
    if part == "buildings" and sc.get("Streaks", 0.0) > 0 and "Decals" in tx:
        top = t.attr("cg_top")
        d = t.m("DIVIDE", t.m("SUBTRACT", top, oz), 6.0)
        inside = t.m("MULTIPLY", t.m("GREATER_THAN", d, 0.0), t.m("LESS_THAN", d, 1.0))
        u = t.m("FRACT", t.m("ADD", t.xyz(uv)[0], t.m("MULTIPLY", seed, 13.0)))
        auv = t.comb(t.m("DIVIDE", t.m("ADD", 2.0, u), 4.0),
                     t.m("SUBTRACT", 1.0, t.m("DIVIDE", t.clamp(d, 0.002, 0.998), 4.0)))
        _, la = t.tex(files[tx["Decals"]], auv, True)
        s = t.m("MULTIPLY", t.m("MULTIPLY", la, inside),
                t.m("MULTIPLY", t.attr("cg_streaks"), vert))
        col = t.mix(t.m("MULTIPLY", s, 0.6), col, (0.03, 0.03, 0.028, 1.0))
    if rec["master"] == "road" and sc.get("Stains", 0.0) > 0 and "RoadAtlas" in tx:
        col, rough = _stains(t, uv, col, rough, files[tx["RoadAtlas"]])
    if sc.get("HeroMaskOn", 0.0) > 0 and "HeroMask" in tx:
        col = _hero(t, col, files[tx["HeroMask"]])
    t.link(col, bsdf.inputs["Base Color"])
    t.link(t.clamp(rough, 0.02, 1.0), bsdf.inputs["Roughness"])
    t.link(metal, bsdf.inputs["Metallic"])
    nm = t.new("ShaderNodeNormalMap", space="TANGENT", uv_map="UVMap")
    t.link(nrm, nm.inputs["Color"])
    nm.inputs["Strength"].default_value = 1.0
    t.link(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _hero(t, col, path):
    """AG5: a hero's U2 mask on UV1 (`UVMap.001`): grime darkens, leaks stain, wear
    lightens (the Unreal masters' `HERO_CODE`)."""
    uv1 = t.new("ShaderNodeUVMap", uv_map="UVMap.001").outputs["UV"]
    m, _ = t.tex(path, uv1, False)
    g, lk, w = t.xyz(m)
    col = t.mix(t.m("MULTIPLY", g, 0.55), col, (0.045, 0.04, 0.032, 1.0))
    col = t.mix(t.m("MULTIPLY", lk, 0.7), col, t.v("MULTIPLY", col, (0.62, 0.58, 0.52)))
    return t.mix(t.m("MULTIPLY", w, 0.35), col,
                 t.v("ADD", t.v("SCALE", col, scale=1.18), (0.02, 0.02, 0.02)))


ROAD_STAINS = (0, 1, 2, 3, 4, 5, 6, 7, 13, 15)      # cells of the road atlas a road lays


def _stains(t, uv, col, rough, path):
    """One road-atlas stain per 8 m cell of UV0 (oil, cracks, patch, tar, skid, puddle,
    dust), placed and picked by a hash of the cell; its alpha over the asphalt."""
    ux, uy, _ = t.xyz(uv)
    cx = t.m("FLOOR", t.m("DIVIDE", ux, 8.0))
    cy = t.m("FLOOR", t.m("DIVIDE", uy, 8.0))
    h1 = t.hash3(t.comb(cx, cy, 1.0))
    h2 = t.hash3(t.comb(cx, cy, 2.0))
    h3 = t.hash3(t.comb(cx, cy, 3.0))
    on = t.m("LESS_THAN", h1, 0.55)
    k = t.m("FLOOR", t.m("MULTIPLY", h2, len(ROAD_STAINS) - 0.001))
    # the k-th stain's atlas cell, as a small lookup by sums of steps
    cell = t.val(float(ROAD_STAINS[0]))
    for i in range(1, len(ROAD_STAINS)):
        step = t.m("GREATER_THAN", k, i - 0.5)
        cell = t.m("ADD", cell, t.m("MULTIPLY", step, float(ROAD_STAINS[i] -
                                                             ROAD_STAINS[i - 1])))
    col_i = t.m("MODULO", cell, 4.0)
    row_i = t.m("FLOOR", t.m("DIVIDE", cell, 4.0))
    lx = t.m("SUBTRACT", t.m("DIVIDE", t.m("SUBTRACT", ux, t.m("MULTIPLY", cx, 8.0)), 2.0),
             t.m("MULTIPLY", h3, 2.0))
    ly = t.m("SUBTRACT", t.m("DIVIDE", t.m("SUBTRACT", uy, t.m("MULTIPLY", cy, 8.0)), 2.0),
             t.m("MULTIPLY", h1, 2.0))
    ins = t.m("MULTIPLY", t.m("MULTIPLY", t.m("GREATER_THAN", lx, 0.0), t.m("LESS_THAN", lx, 1.0)),
              t.m("MULTIPLY", t.m("GREATER_THAN", ly, 0.0), t.m("LESS_THAN", ly, 1.0)))
    au = t.m("DIVIDE", t.m("ADD", col_i, t.clamp(lx, 0.003, 0.997)), 4.0)
    av = t.m("SUBTRACT", 1.0, t.m("DIVIDE", t.m("ADD", row_i, t.clamp(ly, 0.003, 0.997)), 4.0))
    sc, sa = t.tex(path, t.comb(au, av), True)
    a = t.m("MULTIPLY", t.m("MULTIPLY", sa, ins), on)
    col = t.mix(a, col, sc)
    rough = t.m("ADD", rough, t.m("MULTIPLY", a, -0.3))
    return col, rough


def glass(mat, rec, files, part, sky=(0.24, 0.34, 0.48)):
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    sc = rec.get("scalars", {})
    tint = _tint(t, rec, part)
    base = t.v("SCALE", tint if not isinstance(tint, tuple) else t.comb(*tint), scale=2.0)
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["Metallic"].default_value = 0.15
    night = _night(t)
    if part != "buildings" or not sc.get("Interior") or "InteriorDay" not in rec["textures"]:
        t.link(t.mix(0.5, base, sky + (1.0,)), bsdf.inputs["Base Color"])
        return mat
    tx = rec["textures"]
    uv = t.new("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    ux, uy, _ = t.xyz(uv)
    uy = t.m("SUBTRACT", 1.0, uy)       # Blender's glTF import flips v: back to the height
    W = t.attr("cg_room")
    H = t.attr("cg_floorh")
    D = t.m("MAXIMUM", t.m("MULTIPLY", W, 1.1), 3.0)
    fx = t.m("DIVIDE", ux, W)
    fy = t.m("DIVIDE", uy, H)
    cx, cy = t.m("FLOOR", fx), t.m("FLOOR", fy)
    px, py = t.m("FRACT", fx), t.m("FRACT", fy)
    geo = t.new("ShaderNodeNewGeometry")
    N = geo.outputs["Normal"]
    V = geo.outputs["Incoming"]                 # toward the camera
    Tn = t.v("NORMALIZE", t.v("CROSS_PRODUCT", (0.0, 0.0, 1.0), N))
    rx = t.m("DIVIDE", t.m("MULTIPLY", t.v("DOT_PRODUCT", V, Tn), -1.0), W)
    ry = t.m("DIVIDE", t.m("MULTIPLY", t.xyz(V)[2], -1.0), H)
    rz = t.m("DIVIDE", t.m("MAXIMUM", t.v("DOT_PRODUCT", V, N), 0.03), D)

    def axis(p, r):
        sgn = t.m("GREATER_THAN", r, 0.0)
        safe = t.m("ADD", r, t.m("MULTIPLY", t.m("LESS_THAN", t.m("ABSOLUTE", r), 1e-5), 1e-5))
        return t.m("DIVIDE", t.m("SUBTRACT", sgn, p), safe)
    tt = t.m("MINIMUM", t.m("MINIMUM", axis(px, rx), axis(py, ry)), t.m("DIVIDE", 1.0, rz))
    hx = t.clamp(t.m("ADD", px, t.m("MULTIPLY", tt, rx)))
    hy = t.clamp(t.m("ADD", py, t.m("MULTIPLY", tt, ry)))
    hz = t.clamp(t.m("MULTIPLY", tt, rz))
    s = sc.get("InteriorBack", 0.5)
    f = t.m("DIVIDE", s, t.m("ADD", s, t.m("MULTIPLY", hz, 1.0 - s)))
    iu = t.clamp(t.m("ADD", 0.5, t.m("MULTIPLY", t.m("SUBTRACT", hx, 0.5), f)), 0.004, 0.996)
    iv = t.clamp(t.m("ADD", 0.5, t.m("MULTIPLY", t.m("SUBTRACT", hy, 0.5), f)), 0.004, 0.996)
    nx, ny, _ = t.xyz(N)
    fid = t.m("ADD", t.m("MULTIPLY", t.m("ROUND", t.m("MULTIPLY", nx, 8.0)), 17.0),
              t.m("ROUND", t.m("MULTIPLY", ny, 8.0)))
    seed = t.m("ADD", t.m("MULTIPLY", t.attr("cg_seed"), 1000.0), fid)
    h1 = t.hash3(t.comb(cx, cy, seed))
    h2 = t.hash3(t.comb(cx, cy, t.m("ADD", seed, 0.37)))
    h3 = t.hash3(t.comb(cx, cy, t.m("ADD", seed, 0.71)))
    cols, rows = sc.get("InteriorCols", 8.0), sc.get("InteriorRows", 6.0)
    row = t.attr("cg_row") if sc.get("RowOverride", -1.0) < 0 else t.val(sc["RowOverride"])
    col_i = t.m("FLOOR", t.m("MULTIPLY", h1, cols - 0.001))
    au = t.m("DIVIDE", t.m("ADD", col_i, iu), cols)
    av = t.m("DIVIDE", t.m("ADD", t.m("SUBTRACT", rows - 1.0, row), iv), rows)
    day, _ = t.tex(files[tx["InteriorDay"]], t.comb(au, av), True)
    nite, _ = t.tex(files[tx["InteriorNight"]], t.comb(au, av), True)
    # a lit room at 0.35 to 1 of full brightness (lamps differ), else dark
    lit = t.m("MULTIPLY", t.m("LESS_THAN", h2, t.attr("cg_lit")),
              t.m("ADD", 0.35, t.m("MULTIPLY", t.m("FRACT", t.m("MULTIPLY", h1, 7.31)), 0.65)))
    # blinds: a share of rooms with a blind down to a height
    blind = t.m("MULTIPLY", t.m("LESS_THAN", h3, t.attr("cg_blinds")),
                t.m("GREATER_THAN", py, t.m("SUBTRACT", 1.0, t.m("MULTIPLY", h2, 0.9))))
    slat = t.m("ADD", 0.75, t.m("MULTIPLY", t.m("FRACT", t.m("MULTIPLY", uy, 25.0)), 0.25))
    bl_day = t.comb(t.m("MULTIPLY", slat, 0.55), t.m("MULTIPLY", slat, 0.53),
                    t.m("MULTIPLY", slat, 0.5))
    room_day = t.mix(blind, day, bl_day)
    room_nite = t.mix(blind, t.v("SCALE", nite, scale=lit),
                      t.v("SCALE", t.comb(1.0, 0.85, 0.65), scale=t.m("MULTIPLY", lit, 0.45)))
    room_nite = t.v("ADD", room_nite, t.v("SCALE", nite, scale=0.02))
    t.link(t.mix(0.35, base, sky + (1.0,)), bsdf.inputs["Base Color"])
    emit = t.mix(night, t.v("SCALE", room_day, scale=0.2),
                 t.v("SCALE", room_nite, scale=1.2))
    t.link(emit, bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0
    return mat


def emissive(mat, rec, part, strength):
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    c = _lin(rec, part)
    bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    bsdf.inputs["Emission Color"].default_value = (c[0], c[1], c[2], 1.0)
    night = _night(t)
    t.link(t.m("MULTIPLY", t.m("ADD", 0.15, t.m("MULTIPLY", night, 0.85)), strength),
           bsdf.inputs["Emission Strength"])
    return mat


def sign(mat, path, strength):
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    uv = t.new("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    c, _ = t.tex(path, uv, True)
    t.link(c, bsdf.inputs["Base Color"])
    t.link(c, bsdf.inputs["Emission Color"])
    night = _night(t)
    t.link(t.m("MULTIPLY", t.m("ADD", 0.25, t.m("MULTIPLY", night, 0.75)), strength),
           bsdf.inputs["Emission Strength"])
    bsdf.inputs["Roughness"].default_value = 0.35
    return mat


def leaves(mat, rec, files, part):
    """AG8's leaf cards: the leaf clump tile on UV0 / TileM, the tint over its leaves, cut
    where the tile has no leaf (the tint mask: ORM alpha), two-sided."""
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    sc = rec.get("scalars", {})
    uv = t.new("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    tuv = t.v("SCALE", uv, scale=1.0 / sc.get("TileM", 1.0))
    tx = rec["textures"]
    base, _ = t.tex(files[tx["BaseTex"]], tuv, True)
    nrm, _ = t.tex(files[tx["NormalTex"]], tuv, False)
    orm, mask = t.tex(files[tx["OrmTex"]], tuv, False)
    ao, rough, _ = t.xyz(orm)
    ref = rec.get("vectors", {}).get("RefColor", [0.2, 0.2, 0.2])
    ratio = t.v("DIVIDE", _tint(t, rec, part), tuple(max(c, 0.02) for c in ref))
    col = t.v("SCALE", t.v("MULTIPLY", base, ratio),
              scale=t.m("ADD", 0.35, t.m("MULTIPLY", ao, 0.65)))
    t.link(col, bsdf.inputs["Base Color"])
    t.link(rough, bsdf.inputs["Roughness"])
    t.link(t.m("GREATER_THAN", mask, 0.5), bsdf.inputs["Alpha"])
    nm = t.new("ShaderNodeNormalMap", space="TANGENT", uv_map="UVMap")
    t.link(nrm, nm.inputs["Color"])
    t.link(nm.outputs["Normal"], bsdf.inputs["Normal"])
    try:
        mat.surface_render_method = "DITHERED"
    except AttributeError:
        mat.blend_method = "CLIP"
    mat.use_backface_culling = False
    return mat


def _smooth(t, e0, e1, x):
    """smoothstep(e0, e1, x) with sockets or numbers."""
    n = t.new("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
    t._in(n.inputs["Value"], x)
    t._in(n.inputs["From Min"], e0)
    t._in(n.inputs["From Max"], e1)
    return n.outputs["Result"]


def ground(mat, rec, files, part):
    """AG13's ground, node for node `ground_master` (citygen/ue/import_city.py): its mask's
    row 0 is the tile's south edge, sampled on world x, y."""
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    sc = rec.get("scalars", {})
    vec = rec.get("vectors", {})
    tx = rec["textures"]
    uv = t.new("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    sets = {}
    for pre in ("", "Worn", "Shade"):
        tuv = t.v("SCALE", uv, scale=1.0 / sc.get(f"{pre}TileM", 2.0))
        b, h = t.tex(files[tx[f"{pre}BaseTex"]], tuv, True)
        n, _ = t.tex(files[tx[f"{pre}NormalTex"]], tuv, False)
        o, om = t.tex(files[tx[f"{pre}OrmTex"]], tuv, False)
        sets[pre] = (b, h, n, o, om)
    geo = t.new("ShaderNodeNewGeometry")
    wx, wy, _ = t.xyz(geo.outputs["Position"])
    S = sc.get("MaskSize", 256.0)
    muv = t.comb(t.m("DIVIDE", t.m("SUBTRACT", wx, sc.get("MaskX0", 0.0)), S),
                 t.m("DIVIDE", t.m("SUBTRACT", sc.get("MaskY0", 0.0) + S, wy), S))
    mk, ma = t.tex(files[tx["Mask"]], muv, False, "Linear")
    mr, mg, mb = t.xyz(mk)
    h = sets[""][1]
    wear = t.clamp(t.m("ADD", t.m("MULTIPLY", mr, sc.get("WearK", 1.0) * 1.25),
                       t.m("MULTIPLY", mb, sc.get("EdgeK", 0.5) * 0.45)))
    lo = t.m("ADD", t.m("MULTIPLY", h, 0.6), 0.1)
    ww = _smooth(t, lo, t.m("ADD", lo, 0.25), wear)
    wet = t.m("MULTIPLY", ma, sc.get("WetK", 0.6))
    ws = t.m("MULTIPLY", t.m("MULTIPLY", t.clamp(t.m("MULTIPLY", t.m("SUBTRACT", mg, 0.45), 1.8)),
                             sc.get("MossK", 0.5)),
             t.m("MULTIPLY", t.m("ADD", 0.5, t.m("MULTIPLY", wet, 0.5)), t.m("SUBTRACT", 1.0, ww)))
    b, _, bn, bo, bom = sets[""]
    bao, brough, _ = t.xyz(bo)
    if sc.get("Tinted", 0.0) > 0:
        ref = vec.get("RefColor", [0.3, 0.3, 0.3])
        ratio = t.v("DIVIDE", tuple(rec["color"]), tuple(max(c, 0.02) for c in ref))
        b = t.mix(bom, b, t.v("MULTIPLY", b, ratio))
    b = t.v("SCALE", b, scale=t.m("ADD", 0.4, t.m("MULTIPLY", bao, 0.6)))
    w, _, wn, wo, _ = sets["Worn"]
    wao, wrough, _ = t.xyz(wo)
    w = t.v("SCALE", w, scale=t.m("ADD", 0.4, t.m("MULTIPLY", wao, 0.6)))
    s, _, sn, so, _ = sets["Shade"]
    sao, srough, _ = t.xyz(so)
    s = t.v("SCALE", s, scale=t.m("ADD", 0.4, t.m("MULTIPLY", sao, 0.6)))
    col = t.mix(ws, t.mix(ww, b, w), s)
    mac, _ = t.tex(files[tx["Macro"]], t.comb(t.m("DIVIDE", wx, 64.0),
                                              t.m("DIVIDE", wy, 64.0)), False)
    col = t.v("SCALE", col, scale=t.m("ADD", 0.86, t.m("MULTIPLY", t.xyz(mac)[0], 0.28)))
    col = t.v("SCALE", col, scale=t.m("SUBTRACT", 1.0, t.m("MULTIPLY", wet, 0.28)))
    col = t.v("SCALE", col, scale=t.m("SUBTRACT", 1.0, t.m("MULTIPLY",
                                                          t.clamp(t.m("SUBTRACT", mg, 0.5)), 0.25)))
    rough = t.m("MULTIPLY", t.m("ADD", t.m("MULTIPLY", t.m("ADD", t.m("MULTIPLY", brough,
                                                                     t.m("SUBTRACT", 1.0, ww)),
                                                              t.m("MULTIPLY", wrough, ww)),
                                                       t.m("SUBTRACT", 1.0, ws)),
                                         t.m("MULTIPLY", srough, ws)),
                t.m("SUBTRACT", 1.0, t.m("MULTIPLY", wet, 0.35)))
    nrm = t.mix(ws, t.mix(ww, bn, wn), sn)
    t.link(col, bsdf.inputs["Base Color"])
    t.link(t.clamp(rough, 0.05, 1.0), bsdf.inputs["Roughness"])
    nm = t.new("ShaderNodeNormalMap", space="TANGENT", uv_map="UVMap")
    t.link(nrm, nm.inputs["Color"])
    t.link(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def grass(mat, rec, part):
    """AG13's clumps, as `grass_master`: the slot's color toward its dry color by the vertex
    colors (R height share, G tone, B dryness), two-sided; no sway (a still frame)."""
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    vc = t.new("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="Color")
    r, g, b = t.xyz(vc.outputs["Vector"])
    base = (*rec["color"][:3], 1.0)
    dry = (*rec.get("vectors", {}).get("DryColor", rec["color"])[:3], 1.0)
    col = t.mix(b, base, dry)
    k = t.m("MULTIPLY", t.m("ADD", 0.7, t.m("MULTIPLY", r, 0.3)),
            t.m("ADD", 0.9, t.m("MULTIPLY", g, 0.2)))
    t.link(t.v("SCALE", col, scale=k), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rec.get("roughness", 0.8)
    mat.use_backface_culling = False
    return mat


def holo(mat, rec, files, part):
    """A holo-ad screen: its color, AG6's holo ad page where it has one, glowing and
    see-through by its brightness."""
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    sc = rec.get("scalars", {})
    c = _lin(rec, part)
    strength = sc.get("Emissive", 3.0)
    path = files.get((rec.get("textures") or {}).get("SignTex", ""))
    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    if path:
        uv = t.new("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
        tc, _ = t.tex(path, uv, True)
        t.link(t.v("MULTIPLY", tc, tuple(2.0 * x for x in c)), bsdf.inputs["Emission Color"])
        cx, cy, cz = t.xyz(tc)
        lum = t.m("MAXIMUM", cx, t.m("MAXIMUM", cy, cz))
        t.link(t.m("MULTIPLY", sc.get("Opacity", 0.6), t.m("ADD", 0.25, t.m("MULTIPLY", lum, 0.75))),
               bsdf.inputs["Alpha"])
    else:
        bsdf.inputs["Emission Color"].default_value = (c[0], c[1], c[2], 1.0)
        bsdf.inputs["Alpha"].default_value = sc.get("Opacity", 0.45)
    bsdf.inputs["Emission Strength"].default_value = strength
    try:
        mat.surface_render_method = "BLENDED"
    except AttributeError:
        mat.blend_method = "BLEND"
    mat.use_backface_culling = False
    return mat


def flat(mat, rec, part):
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    c = _lin(rec, part)
    bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    bsdf.inputs["Roughness"].default_value = rec.get("roughness", 0.8)
    bsdf.inputs["Metallic"].default_value = rec.get("metallic", 0.0)
    if rec["master"] == "translucent":
        bsdf.inputs["Alpha"].default_value = 0.3
        try:
            mat.surface_render_method = "BLENDED"
        except AttributeError:
            pass
    return mat


def proxy(mat):
    """A far proxy: the wall tint with a window grid from the building's bay and floor
    height (UV0 in meters), the windows lit at night by its lit ratio."""
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    uv = t.new("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    ux, uy, _ = t.xyz(uv)
    uy = t.m("SUBTRACT", 1.0, uy)
    bay = t.m("MAXIMUM", t.attr("cg_bay"), 1.0)
    flo = t.m("MAXIMUM", t.attr("cg_floor"), 2.5)
    fu = t.m("FRACT", t.m("DIVIDE", ux, bay))
    fv = t.m("FRACT", t.m("DIVIDE", uy, flo))
    w = t.m("MULTIPLY", t.m("MULTIPLY", t.m("GREATER_THAN", fu, 0.2), t.m("LESS_THAN", fu, 0.8)),
            t.m("MULTIPLY", t.m("GREATER_THAN", fv, 0.3), t.m("LESS_THAN", fv, 0.82)))
    w = t.m("MULTIPLY", w, t.m("GREATER_THAN", uy, 1.0))
    wall = t.attr("cg_wall", "Vector")
    glass_c = t.v("SCALE", t.attr("cg_glass", "Vector"), scale=2.0)
    t.link(t.mix(w, wall, glass_c), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    cell = t.comb(t.m("FLOOR", t.m("DIVIDE", ux, bay)), t.m("FLOOR", t.m("DIVIDE", uy, flo)),
                  t.m("MULTIPLY", t.attr("cg_seed"), 1000.0))
    lit = t.m("LESS_THAN", t.hash3(cell), t.attr("cg_lit"))
    night = _night(t)
    t.link(t.m("MULTIPLY", t.m("MULTIPLY", w, lit), t.m("MULTIPLY", night, 0.9)),
           bsdf.inputs["Emission Strength"])
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.8, 0.55, 1.0)
    return mat


def decal(mat, rec, files):
    """AG3's mesh decals: a cell of the decal atlas over the quad (UV0 0 to 1, v down in
    glTF), its coverage as alpha, blended over the wall behind."""
    t = T(mat)
    bsdf = t.n["Principled BSDF"]
    sc = rec.get("scalars", {})
    cols, rows = sc.get("Cols", 4.0), sc.get("Rows", 4.0)
    cell = int(sc.get("Cell", 0.0))
    col, row = cell % int(cols), cell // int(cols)
    uv = t.new("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    u, v, _ = t.xyz(uv)
    auv = t.comb(t.m("DIVIDE", t.m("ADD", u, float(col)), cols),
                 t.m("DIVIDE", t.m("ADD", v, float(rows - 1 - row)), rows))
    tx = rec.get("textures", {})
    c, a = t.tex(files[tx["BaseTex"]], auv, True)
    t.link(c, bsdf.inputs["Base Color"])
    t.link(a, bsdf.inputs["Alpha"])
    if "NormalTex" in tx:
        nc, _ = t.tex(files[tx["NormalTex"]], auv, False)
        nm = t.new("ShaderNodeNormalMap")
        t.link(nc, nm.inputs["Color"])
        t.link(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if "OrmTex" in tx:
        oc, _ = t.tex(files[tx["OrmTex"]], auv, False)
        _, g, _ = t.xyz(oc)
        t.link(g, bsdf.inputs["Roughness"])
    try:
        mat.surface_render_method = "BLENDED"
    except AttributeError:
        pass
    try:
        mat.use_backface_culling = True
    except AttributeError:
        pass
    return mat


def make(name, rec, files, part):
    """A Blender material for one record of materials.json."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    master = rec["master"]
    if part == "buildings" and name.endswith("_proxy"):
        return proxy(mat)
    if master in ("facade", "concrete", "metal", "road", "foliage") and \
            rec.get("scalars", {}).get("Textured", 0.0) > 0:
        return textured(mat, rec, files, part)
    if master == "decal" and "BaseTex" in rec.get("textures", {}):
        return decal(mat, rec, files)
    if master == "leaves" and rec.get("scalars", {}).get("Textured", 0.0) > 0:
        return leaves(mat, rec, files, part)
    if master == "holo":
        return holo(mat, rec, files, part)
    if master == "ground" and rec.get("scalars", {}).get("Textured", 0.0) > 0 and \
            "Mask" in (rec.get("textures") or {}):
        return ground(mat, rec, files, part)
    if master == "grass":
        return grass(mat, rec, part)
    if master == "sign" and "SignTex" in (rec.get("textures") or {}):
        return sign(mat, files[rec["textures"]["SignTex"]],
                    rec.get("scalars", {}).get("SignStrength", 4.0))
    if master == "glass":
        return glass(mat, rec, files, part)
    if master in ("neon", "emissive"):
        return emissive(mat, rec, part, rec.get("scalars", {}).get("NeonStrength", 6.0))
    return flat(mat, rec, part)
