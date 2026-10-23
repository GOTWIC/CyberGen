import bpy, json, math, sys, random

args = sys.argv[sys.argv.index("--") + 1:]
GEO, OUT = args[0], args[1]
RES_X, RES_Y, SAMPLES = int(args[2]), int(args[3]), int(args[4])
geo = json.load(open(GEO))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

def mat(name, color, rough=0.7, emit=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1); b.inputs["Emission Strength"].default_value = 1.0
    return m

M = dict(land=mat("land", (0.36, 0.35, 0.32)), highway=mat("highway", (0.035, 0.037, 0.042), 0.6),
         avenue=mat("avenue", (0.05, 0.052, 0.058), 0.6), street=mat("street", (0.07, 0.072, 0.078), 0.6),
         elevated=mat("elevated", (0.05, 0.05, 0.06), 0.6), bridge=mat("bridge", (0.06, 0.062, 0.068), 0.6),
         water=mat("water", (0.012, 0.05, 0.085), 0.08), landmark=mat("landmark", (0.55, 0.40, 0.18), 0.4))
tower_mats = [mat(f"tower{i}", (0.30 + 0.04 * i, 0.32 + 0.04 * i, 0.36 + 0.04 * i), 0.45) for i in range(4)]

def curve_obj(name, poly_list, z, half_thickness, material):
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "2D"; cu.fill_mode = "BOTH"
    cu.extrude = half_thickness
    for p in poly_list:
        for ring in [p["exterior"]] + p["holes"]:
            sp = cu.splines.new("POLY"); sp.points.add(len(ring) - 1)
            for i, (x, y) in enumerate(ring):
                sp.points[i].co = (x, y, 0, 1)
            sp.use_cyclic_u = True
            sp.use_smooth = False
    ob = bpy.data.objects.new(name, cu); ob.location.z = z
    cu.materials.append(material); scene.collection.objects.link(ob)
    return ob

# water
bpy.ops.mesh.primitive_plane_add(size=6000, location=(0, 0, -2.0))
bpy.context.active_object.data.materials.append(M["water"])

curve_obj("land", geo["land"], -1.0, 1.0, M["land"])                 # top at z=0
for cat, plist in geo["roads"].items():
    curve_obj(cat, plist, 0.06, 0.05, M[cat])                         # thin slab just above ground
curve_obj("bridges", geo["bridges"], -0.65, 0.75, M["bridge"])

for b in geo["buildings"]:
    h = b["height"]
    m = M["landmark"] if b["cat"] == "landmark" else tower_mats[random.Random(b["id"]).randrange(4)]
    curve_obj(b["id"], [dict(exterior=b["footprint"], holes=[])], h / 2, h / 2, m)

# camera: orthographic isometric, looking north from the south
cam_data = bpy.data.cameras.new("cam"); cam_data.type = "ORTHO"; cam_data.ortho_scale = 1260
cam = bpy.data.objects.new("cam", cam_data); scene.collection.objects.link(cam); scene.camera = cam
tilt = math.radians(54.7356)
cam.rotation_euler = (tilt, 0, 0)
d = (0, math.sin(tilt), -math.cos(tilt))
target = (0, 20, 150)
cam.location = (target[0] - d[0] * 3000, target[1] - d[1] * 3000, target[2] - d[2] * 3000)
cam_data.clip_end = 10000

# lighting
sun_d = bpy.data.lights.new("sun", "SUN"); sun_d.energy = 2.6; sun_d.angle = math.radians(1.5)
sun = bpy.data.objects.new("sun", sun_d); scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.62, 0.72, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55

scene.render.engine = "CYCLES"; scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES; scene.cycles.use_denoising = True
scene.cycles.max_bounces = 4
scene.render.resolution_x, scene.render.resolution_y = RES_X, RES_Y
scene.render.resolution_percentage = 100
try:
    scene.view_settings.view_transform = "AgX"; scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass  # look names differ between Blender versions
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
