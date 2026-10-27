"""Unreal export (M15): a built city into an Unreal 5.8 project, `citygen unreal BUILD_DIR
UPROJECT`.

BUILD_DIR is a `citygen build --blockout` (or `citygen blockout`) output: blockout_plan.json,
tiles.json, tiles/<tile>.glb, graphs.json and gameplay.json. This module (the venv side, no
Unreal needed) writes BUILD_DIR/unreal/:

- `manifest.json`: every blockout object of the glTF tiles as one actor (its key is the
  object's name, which M10 makes stable; its content hash is the sha256 of its plan entry,
  so a re-import touches only what changed), the props and plants as instanced meshes (one
  actor per kind and tile, the instances' transforms and citygen ids), a material per plan
  material (linear base color, roughness, emissive), the prototype mesh of each prop kind,
  the player start and the graph summary;
- `prototypes.glb`: one node per prop and plant kind, built here from the plan's prototype
  parts (boxes and prisms), since the glTF tiles leave props out;
- `graphs.json`: the lane, walkway and transit graphs flattened for data assets (ids, kinds,
  widths, points and links as offsets into flat arrays).

Then it runs the editor headless (`UnrealEditor-Cmd UPROJECT -run=pythonscript`) on
`citygen/ue/import_city.py`, which reads only those files (stdlib and the `unreal` module).
citygen itself makes no network call; the Unreal MCP plugin is the interactive route (a
session in a running editor runs the same script).

Frames: citygen is x east, y north, z up, meters; Unreal is X forward, Y right, Z up,
centimeters. The importer puts citygen (x, y, z) at Unreal (100 x, -100 y, 100 z), as the
glTF import of the tiles does, and a citygen yaw (counterclockwise from east) at Unreal yaw
-yaw.
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

MANIFEST_VERSION = 1
OUT_DIR = "unreal"            # BUILD_DIR/unreal (beside corporate_core_plan.json)
CONTENT_ROOT = "/Game/CityGen"
EMISSIVE = {"prop_light": 6.0, "prop_neon": 10.0, "prop_signal": 2.0}
ROUGHNESS = {"sea": 0.35, "water": 0.35, "prop_glass": 0.2}  # else 0.85, as in Blender
DOME_STEPS = [(1.0, 0.0), (0.92388, 0.382683), (0.707107, 0.707107), (0.382683, 0.92388)]
PLAYER_Z_M = 1.2              # player start above the walkway (capsule half height 0.96 m)
ENGINE_GLOBS = {
    "darwin": ["/Users/Shared/Epic Games/UE_5.*"],
    "win32": ["C:/Program Files/Epic Games/UE_5.*"],
    "linux": [os.path.expanduser("~/UnrealEngine*"), "/opt/UnrealEngine*"],
}
EDITOR_CMD = {"darwin": "Mac/UnrealEditor-Cmd", "win32": "Win64/UnrealEditor-Cmd.exe",
              "linux": "Linux/UnrealEditor-Cmd"}
EDITOR_GUI = {"darwin": "Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor",
              "win32": "Win64/UnrealEditor.exe", "linux": "Linux/UnrealEditor"}
PLUGINS = ["PythonScriptPlugin", "EditorScriptingUtilities"]
UE_DIR = Path(__file__).parent / "ue"


# --- names and hashes ---------------------------------------------------------------------

def content_hash(data) -> str:
    """16 hex digits of the sha256 of `data` as canonical JSON (the plan is the same bytes on
    every machine, so this is too)."""
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "city"


def pascal(name: str) -> str:
    """The city's content folder and map name: `Vesper Bay` -> `VesperBay`."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    out = "".join(w[:1].upper() + w[1:] for w in words) or "City"
    return out if out[0].isalpha() else "City" + out


def asset_name(object_name: str) -> str:
    """The static mesh asset name the glTF import gives a node (dots become underscores)."""
    return re.sub(r"[^A-Za-z0-9_+\-]", "_", object_name)


def srgb_to_linear(hex_color: str) -> list[float]:
    h = hex_color.lstrip("#")
    out = []
    for k in range(3):
        c = int(h[2 * k:2 * k + 2], 16) / 255.0
        out.append(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 6))
    return out


def material_params(name: str, hex_color: str) -> dict:
    return {"color": srgb_to_linear(hex_color), "roughness": ROUGHNESS.get(name, 0.85),
            "emissive": EMISSIVE.get(name, 0.0)}


# --- prototypes.glb ---------------------------------------------------------------------------

class _Mesh:
    """Flat-shaded triangles per material, in citygen coordinates (meters)."""

    def __init__(self):
        self.tris: dict[str, list] = {}

    def poly(self, pts, mat):
        """A convex polygon (counterclockwise seen from its front) as a triangle fan."""
        t = self.tris.setdefault(mat, [])
        for i in range(1, len(pts) - 1):
            t.append((pts[0], pts[i], pts[i + 1]))

    def cap(self, ring, z, mat, up=True):
        pts = [(x, y, z) for x, y in ring]
        if _area(ring) < 0:
            pts = pts[::-1]
        self.poly(pts if up else pts[::-1], mat)

    def walls(self, ring, z0, z1, mat):
        if _area(ring) < 0:
            ring = ring[::-1]
        n = len(ring)
        for i in range(n):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
            self.poly([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], mat)

    def box(self, c, d, yaw_deg, mat):
        a = math.radians(yaw_deg)
        ux, uy = math.cos(a), math.sin(a)
        hx, hy = d[0] / 2.0, d[1] / 2.0
        ring = [(c[0] + ux * x - uy * y, c[1] + uy * x + ux * y)
                for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
        z0, z1 = c[2], c[2] + d[2]
        self.cap(ring, z1, mat, up=True)
        self.cap(ring, z0, mat, up=False)
        self.walls(ring, z0, z1, mat)

    def prism(self, p, mat):
        ring, z0, z1, shape = p["r"], p["z0"], p["z1"], p.get("s", "prism")
        if _area(ring) < 0:
            ring = ring[::-1]
        if shape in ("cone", "dome"):
            cx = sum(x for x, _ in ring) / len(ring)
            cy = sum(y for _, y in ring) / len(ring)
            steps = DOME_STEPS if shape == "dome" else [(1.0, 0.0)]
            self.cap(ring, z0, mat, up=False)
            prev = [(x, y, z0) for x, y in ring]
            for f, s in steps[1:]:
                z = z0 + (z1 - z0) * s
                cur = [(cx + (x - cx) * f, cy + (y - cy) * f, z) for x, y in ring]
                for i in range(len(ring)):
                    j = (i + 1) % len(ring)
                    self.poly([prev[i], prev[j], cur[j], cur[i]], mat)
                prev = cur
            for i in range(len(ring)):
                j = (i + 1) % len(ring)
                self.poly([prev[i], prev[j], (cx, cy, z1)], mat)
            return
        self.cap(ring, z1, mat, up=True)
        self.cap(ring, z0, mat, up=False)
        self.walls(ring, z0, z1, mat)


def _area(ring) -> float:
    return sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1]
               for i in range(len(ring))) / 2.0


def prototype_mesh(parts: list[dict]) -> _Mesh:
    m = _Mesh()
    for p in parts:
        if p["k"] == "box":
            m.box(p["c"], p["d"], p["yaw"], p["m"])
        elif p["k"] == "prism":
            m.prism(p, p["m"])
        else:
            raise ValueError(f"prototype part {p['k']!r} is not supported")
    return m


def _gltf(v):
    """citygen (x east, y north, z up) to glTF (y up), as Blender's glTF export writes it."""
    return (v[0], v[2], -v[1])


def write_glb(meshes: dict[str, _Mesh], materials: dict[str, dict], path: Path) -> Path:
    """A binary glTF with one node and mesh per entry (flat normals, one primitive per
    material); materials named after the plan's, with their base color."""
    bin_parts: list[bytes] = []
    views, accessors, gl_meshes, nodes = [], [], [], []
    mat_index: dict[str, int] = {}
    gl_mats = []
    offset = 0

    def add_view(data: bytes, target: int) -> int:
        nonlocal offset
        pad = (-len(data)) % 4
        bin_parts.append(data + b"\0" * pad)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data),
                      "target": target})
        offset += len(data) + pad
        return len(views) - 1

    for name in sorted(meshes):
        prims = []
        for mat in sorted(meshes[name].tris):
            tris = meshes[name].tris[mat]
            pos, nrm = [], []
            for a, b, c in tris:
                A, B, C = _gltf(a), _gltf(b), _gltf(c)
                u = [B[i] - A[i] for i in range(3)]
                w = [C[i] - A[i] for i in range(3)]
                n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2],
                     u[0] * w[1] - u[1] * w[0]]
                ln = math.sqrt(sum(x * x for x in n)) or 1.0
                n = [x / ln for x in n]
                for P in (A, B, C):
                    pos.append(P)
                    nrm.append(n)
            if mat not in mat_index:
                mat_index[mat] = len(gl_mats)
                col = materials.get(mat, {}).get("color", [0.5, 0.5, 0.5])
                gl_mats.append({"name": mat, "doubleSided": True, "pbrMetallicRoughness": {
                    "baseColorFactor": [*col, 1.0], "metallicFactor": 0.0,
                    "roughnessFactor": materials.get(mat, {}).get("roughness", 0.85)}})
            pv = add_view(struct.pack(f"<{3 * len(pos)}f", *[x for p in pos for x in p]),
                          34962)
            nv = add_view(struct.pack(f"<{3 * len(nrm)}f", *[x for p in nrm for x in p]),
                          34962)
            iv = add_view(struct.pack(f"<{len(pos)}I", *range(len(pos))), 34963)
            lo = [min(p[i] for p in pos) for i in range(3)]
            hi = [max(p[i] for p in pos) for i in range(3)]
            accessors.append({"bufferView": pv, "componentType": 5126, "count": len(pos),
                              "type": "VEC3", "min": lo, "max": hi})
            accessors.append({"bufferView": nv, "componentType": 5126, "count": len(pos),
                              "type": "VEC3"})
            accessors.append({"bufferView": iv, "componentType": 5125, "count": len(pos),
                              "type": "SCALAR"})
            k = len(accessors)
            prims.append({"attributes": {"POSITION": k - 3, "NORMAL": k - 2},
                          "indices": k - 1, "material": mat_index[mat]})
        gl_meshes.append({"name": name, "primitives": prims})
        nodes.append({"name": name, "mesh": len(gl_meshes) - 1})
    blob = b"".join(bin_parts)
    doc = {"asset": {"version": "2.0", "generator": "citygen unreal (M15)"},
           "scene": 0, "scenes": [{"name": "prototypes", "nodes": list(range(len(nodes)))}],
           "nodes": nodes, "meshes": gl_meshes, "materials": gl_mats, "accessors": accessors,
           "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((-len(js)) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    data = (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON")
            + js + struct.pack("<I4s", len(blob), b"BIN\0") + blob)
    path.write_bytes(data)
    return path


def read_glb_json(path: Path) -> dict:
    data = Path(path).read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + n])


# --- graphs -----------------------------------------------------------------------------------

def _flat(elems: list[dict]) -> dict:
    """Elements (id, kind, ref, width, points, links by id, attrs) as flat arrays: element i
    has points[point_start[i]:point_start[i + 1]] and links[link_start[i]:link_start[i + 1]]
    (indices of other elements); links to ids not in the graph are dropped."""
    index = {e["id"]: i for i, e in enumerate(elems)}
    out = {"ids": [], "kinds": [], "refs": [], "widths": [], "point_start": [0],
           "points": [], "link_start": [0], "links": [], "attrs": []}
    for e in elems:
        out["ids"].append(e["id"])
        out["kinds"].append(e["kind"])
        out["refs"].append(e.get("ref") or "")
        out["widths"].append(float(e.get("width", 0.0)))
        for p in e["points"]:
            out["points"].extend([float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0])
        out["point_start"].append(len(out["points"]) // 3)
        out["links"].extend(index[x] for x in e.get("links", []) if x in index)
        out["link_start"].append(len(out["links"]))
        out["attrs"].append(json.dumps(e.get("attrs", {}), sort_keys=True,
                                       separators=(",", ":")) if e.get("attrs") else "")
    out["count"] = len(elems)
    return out


def flat_graphs(graphs: dict) -> dict:
    """graphs.json (M4 exports) as three flat graphs: lanes (lanes and junction connectors,
    linked to their successors), walkways (linked to their neighbors) and transit (lines
    and stations, linked to each other)."""
    lanes = [{"id": x["id"], "kind": x["kind"], "ref": x["segment_id"] or x["node_id"],
              "width": x["width_m"], "points": x["centerline"], "links": x["successors"],
              "attrs": {"forward": x["forward"], "index": x["index"],
                        "adjacent_ids": x["adjacent_ids"]}} for x in graphs["lanes"]]
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"], "points": w["line"],
              "links": w["neighbors"]} for w in graphs["walkways"]]
    transit = []
    for t in graphs["transit_lines"]:
        transit.append({"id": t["id"], "kind": t.get("mode") or "line", "ref": t.get("name"),
                        "points": t.get("path") or [], "links": t.get("station_ids", []),
                        "attrs": {"loop": t.get("loop", False), "color": t.get("color"),
                                  "stops": (t.get("attrs") or {}).get("stops", [])}})
    for s in graphs["stations"]:
        transit.append({"id": s["id"], "kind": "station." + (s.get("kind") or "stop"),
                        "ref": s.get("name"), "points": [s["position"]],
                        "links": s.get("line_ids", []),
                        "attrs": {"building_id": s.get("building_id")}})
    out = {"lanes": _flat(lanes), "walkways": _flat(walks), "transit": _flat(transit)}
    for g in out.values():
        g["hash"] = content_hash(g)
    return out


# --- manifest ---------------------------------------------------------------------------------

def _district(name: str, props: dict) -> str:
    d = props.get("district")
    if d:
        return d
    m = re.match(r"(d\d+)\.", name)
    return m.group(1) if m else ""


def _ids(props: dict) -> list[str]:
    if props.get("citygen_id"):
        return [props["citygen_id"]]
    ids = props.get("citygen_ids") or ""
    return [x for x in ids.split(";") if x]


def _inside(rings: list) -> list[float] | None:
    """A point inside a polygon (outer ring and holes): the middle of the widest chord along a
    horizontal line through it (half way up, else a quarter or three eighths up or down)."""
    ys = [p[1] for p in rings[0]]
    lo, hi = min(ys), max(ys)
    best = None
    for f in (0.5, 0.25, 0.75, 0.375, 0.625):
        y = lo + (hi - lo) * f
        xs = []
        for ring in rings:
            for a, b in zip(ring, ring[1:] + ring[:1]):
                if (a[1] <= y < b[1]) or (b[1] <= y < a[1]):
                    xs.append(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            if best is None or b - a > best[0]:
                best = (b - a, (a + b) / 2.0, y)
        if best is not None and best[0] > 2.0:
            break
    return None if best is None else [round(best[1], 2), round(best[2], 2)]


def _roof(parts: list[dict]) -> list[float] | None:
    """A point on a building's highest prism, inside its footprint: [x, y, top] (the check
    traces down onto it)."""
    prisms = [p for p in parts if p["k"] == "prism" and len(p.get("r", [])) >= 3]
    if not prisms:
        return None
    top = max(prisms, key=lambda p: p["z1"])
    xy = _inside([top["r"]] + list(top.get("h", [])))
    return None if xy is None else xy + [top["z1"]]


def player_start(build: Path, plan: dict) -> dict:
    """On the walkway of the fast-travel point nearest the city's middle (the city center
    if there is none), facing the middle."""
    b = plan["bounds"]
    mx, my = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    pos, src = (mx, my), "center"
    gp = build / "gameplay.json"
    if gp.is_file():
        tps = json.loads(gp.read_text(encoding="utf-8")).get("travel_points", [])
        tps = [t for t in tps if t.get("kind") == "fast_travel"] or tps
        if tps:
            def d2(t):
                q = (t.get("access") or {}).get("position") or t["position"]
                return ((q[0] - mx) ** 2 + (q[1] - my) ** 2, t["id"])
            t = min(tps, key=d2)
            pos = tuple((t.get("access") or {}).get("position") or t["position"])[:2]
            src = t["id"]
    z = 0.0
    gr = build / "graphs.json"
    if gr.is_file():
        best = None
        for w in json.loads(gr.read_text(encoding="utf-8"))["walkways"]:
            if w["kind"] not in ("sidewalk", "path", "promenade", "pedestrian_street",
                                 "crossing", "plaza"):
                continue
            for p in w["line"]:
                d = (p[0] - pos[0]) ** 2 + (p[1] - pos[1]) ** 2
                if best is None or d < best[0]:
                    best = (d, p[2] if len(p) > 2 else 0.0)
        if best is not None and best[0] < 30.0 ** 2:
            z = best[1]
    yaw = math.degrees(math.atan2(my - pos[1], mx - pos[0])) if (pos != (mx, my)) else 0.0
    return {"position": [round(pos[0], 2), round(pos[1], 2), round(z + PLAYER_Z_M, 2)],
            "yaw_deg": round(yaw, 2), "source": src}


def build_manifest(build_dir: str | Path, name: str | None = None) -> dict:
    """The manifest of a blockout output (see the module docstring), with the prototypes'
    meshes and the flat graphs beside it: (manifest, prototype meshes, flat graphs)."""
    build = Path(build_dir)
    plan = json.loads((build / "blockout_plan.json").read_text(encoding="utf-8"))
    city = name or plan["city"]
    mats = {k: material_params(k, v) for k, v in sorted(plan["materials"].items())}
    tiles: dict[str, dict] = {}
    for t in plan["tiles"]:
        tiles[t["name"]] = {"name": t["name"], "ix": t["ix"], "iy": t["iy"],
                            "bounds": t["bounds"], "glb": None, "objects": []}
    instances = []
    for o in plan["objects"]:
        props = o.get("props", {})
        h = content_hash(o)
        if o["parts"] and o["parts"][0]["k"] == "inst":
            p = o["parts"][0]
            instances.append({
                "key": o["name"], "hash": h, "proto": p["proto"], "tile": o["tile"],
                "category": o["category"], "type": props.get("citygen_type", ""),
                "district": _district(o["name"], props), "count": len(p["pts"]),
                "ids": _ids(props), "xforms": p["pts"]})
            continue
        ids = _ids(props)
        obj = {"key": o["name"], "asset": asset_name(o["name"]), "hash": h,
               "category": o["category"], "type": props.get("citygen_type", ""),
               "district": _district(o["name"], props), "ids": ids,
               "materials": sorted({p["m"] for p in o["parts"]})}
        if o["category"] in ("building", "landmark"):
            obj["roof"] = _roof(o["parts"])
        tiles[o["tile"]]["objects"].append(obj)
    out_tiles = []
    for t in tiles.values():
        if not t["objects"]:
            continue
        glb = build / "tiles" / f"{t['name']}.glb"
        t["glb"] = f"tiles/{t['name']}.glb" if glb.is_file() else None
        t["hash"] = content_hash([o["hash"] for o in t["objects"]])
        out_tiles.append(t)
    protos = {}
    meshes = {}
    for kind, parts in sorted(plan.get("prototypes", {}).items()):
        node = f"proto.{kind}"
        meshes[node] = prototype_mesh(parts)
        protos[kind] = {"node": node, "asset": asset_name(node), "hash": content_hash(parts)}
    graphs = None
    if (build / "graphs.json").is_file():
        graphs = flat_graphs(json.loads((build / "graphs.json").read_text(encoding="utf-8")))
    man = {
        "version": MANIFEST_VERSION, "generator": "citygen unreal (M15)",
        "city": city, "slug": slug(city), "folder": pascal(city),
        "content_root": f"{CONTENT_ROOT}/{pascal(city)}", "seed": plan.get("seed"),
        "frame": "citygen x east, y north, z up, m -> Unreal (100 x, -100 y, 100 z) cm, "
                 "yaw -> -yaw",
        "tile_size_m": plan["tile_size_m"], "bounds": plan["bounds"],
        "plan_sha256": hashlib.sha256((build / "blockout_plan.json").read_bytes()).hexdigest(),
        "materials": mats, "prototypes": {"glb": "unreal/prototypes.glb", "kinds": protos},
        "tiles": out_tiles, "instances": instances,
        "graphs": ({k: {"count": g["count"], "hash": g["hash"]} for k, g in graphs.items()}
                   if graphs else {}),
        "player_start": player_start(build, plan),
        "cameras": {"iso_dir": plan.get("cameras", {}).get("iso_dir"),
                    "street": plan.get("cameras", {}).get("street", [])},
        "counts": {"tiles": len(out_tiles),
                   "objects": sum(len(t["objects"]) for t in out_tiles),
                   "instance_actors": len(instances),
                   "instances": sum(i["count"] for i in instances),
                   "prototypes": len(protos)},
    }
    man["hash"] = content_hash({k: v for k, v in man.items() if k != "plan_sha256"})
    return man, meshes, graphs


# the importer's always-loaded lighting actors (`ue/import_city.py`, `Importer.lighting`)
LIGHTING = ("lighting.sun", "lighting.sky", "lighting.atmosphere")


def actor_hashes(man: dict) -> dict[str, str]:
    """Every actor an import of `man` makes, by key, with the content hash the importer
    compares it by (`ue/import_city.py` hashes the player start and the lights the same way)."""
    out = {o["key"]: o["hash"] for t in man["tiles"] for o in t["objects"]}
    out.update({i["key"]: i["hash"] for i in man["instances"]})
    out["player_start"] = content_hash(man["player_start"])
    out.update({k: content_hash([k, "v1"]) for k in LIGHTING})
    return out


def manifest_changes(old: dict, new: dict) -> dict[str, list[str]]:
    """The actors an import of `new` over an import of `old` creates, updates and deletes."""
    a, b = actor_hashes(old), actor_hashes(new)
    return {"created": sorted(b.keys() - a.keys()),
            "updated": sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
            "deleted": sorted(a.keys() - b.keys())}


def write_manifest(build_dir: str | Path, name: str | None = None) -> Path:
    """BUILD_DIR/unreal/manifest.json, prototypes.glb and graphs.json; the manifest's path."""
    build = Path(build_dir)
    for f in ("blockout_plan.json", "tiles.json"):
        if not (build / f).is_file():
            raise FileNotFoundError(f"{build / f}: not a blockout output (run citygen build "
                                    f"--blockout or citygen blockout)")
    man, meshes, graphs = build_manifest(build, name)
    out = build / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    write_glb(meshes, man["materials"], out / "prototypes.glb")
    if graphs is not None:
        (out / "graphs.json").write_text(json.dumps(graphs, separators=(",", ":")) + "\n",
                                         encoding="utf-8")
    path = out / "manifest.json"
    path.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --- the engine -------------------------------------------------------------------------------

def _version_key(path: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", Path(path).name))


def find_engine(explicit: str | None = None) -> Path | None:
    """The engine root: `explicit` (a root or an editor binary), $CITYGEN_UE_ROOT, else the
    newest UE_5.* in the platform's usual place."""
    for cand in (explicit, os.environ.get("CITYGEN_UE_ROOT")):
        if cand:
            p = Path(cand)
            while p != p.parent and not (p / "Engine" / "Binaries").is_dir():
                p = p.parent
            return p if (p / "Engine" / "Binaries").is_dir() else None
    roots = []
    for g in ENGINE_GLOBS.get(sys.platform, []):
        roots += [r for r in glob.glob(g) if (Path(r) / "Engine" / "Binaries").is_dir()]
    roots.sort(key=_version_key, reverse=True)
    return Path(roots[0]) if roots else None


def editor_binary(root: Path, gui: bool = False) -> Path:
    rel = (EDITOR_GUI if gui else EDITOR_CMD).get(sys.platform, EDITOR_CMD["linux"])
    return root / "Engine" / "Binaries" / rel


def prepare_project(uproject: str | Path) -> list[str]:
    """Enable the editor plugins the importer needs in the .uproject (Python scripting and
    editor scripting utilities); the ones added."""
    p = Path(uproject)
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    have = {x.get("Name") for x in data.setdefault("Plugins", [])}
    added = [n for n in PLUGINS if n not in have]
    for n in PLUGINS:
        for x in data["Plugins"]:
            if x.get("Name") == n and not x.get("Enabled", False):
                x["Enabled"] = True
                added.append(n)
    data["Plugins"] += [{"Name": n, "Enabled": True} for n in added if n not in have]
    if added:
        p.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8")
    return added


def new_project(dest: str | Path, root: Path | None = None,
                template: str = "TP_FirstPersonBP") -> Path:
    """A project at `dest` from one of the engine's templates (default: the Blueprint First
    Person one) as the New Project dialog makes it: the template's config and content, its
    shared content packs (mannequins, input, level prototyping) and the importer's plugins.
    Returns the .uproject (dest/<folder name>.uproject); an existing one is kept."""
    root = root or find_engine()
    if root is None:
        raise RuntimeError("no Unreal Engine found")
    dest = Path(dest)
    up = dest / f"{dest.name}.uproject"
    if up.is_file():
        return up
    tdir = root / "Templates" / template
    if not tdir.is_dir():
        raise FileNotFoundError(f"{tdir}: no such template")
    import shutil

    dest.mkdir(parents=True, exist_ok=True)
    for sub in ("Config", "Content"):
        if (tdir / sub).is_dir():
            shutil.copytree(tdir / sub, dest / sub, dirs_exist_ok=True)
    defs = (tdir / "Config" / "TemplateDefs.ini")
    text = defs.read_text(encoding="utf-8-sig") if defs.is_file() else ""
    for f in ("TemplateDefs.ini", "config.ini"):
        (dest / "Config" / f).unlink(missing_ok=True)
    for line in text.splitlines():
        m = re.match(r'SharedContentPacks=\(MountName="([^"]+)",DetailLevels=\("?(\w+)', line)
        if m:
            src = root / "Templates" / "TemplateResources" / m.group(2) / m.group(1) / "Content"
            if src.is_dir():
                shutil.copytree(src, dest / "Content" / m.group(1), dirs_exist_ok=True)
    data = json.loads((tdir / f"{template}.uproject").read_text(encoding="utf-8-sig"))
    ver = json.loads((root / "Engine" / "Build" / "Build.version").read_text())
    data["EngineAssociation"] = f"{ver['MajorVersion']}.{ver['MinorVersion']}"
    up.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8")
    prepare_project(up)
    return up


def run_editor(root: Path, uproject: Path, script: Path, job: dict, log: Path,
               timeout: float = 7200.0, gui: bool = False, extra: list[str] | None = None
               ) -> dict:
    """Run `script` in the editor on `uproject` (headless commandlet, or the full editor for
    play-in-editor checks and renders) with the job in $CITYGEN_UE_JOB; the job's result."""
    job_path = log.with_suffix(".job.json")
    job_path.write_text(json.dumps(job, indent=1) + "\n", encoding="utf-8")
    result_path = Path(job["result"])
    if result_path.exists():
        result_path.unlink()
    exe = editor_binary(root, gui)
    if gui:
        # -ExecCmds, not -ExecutePythonScript (which closes the editor once the script
        # returns): the script runs on the editor's tick and quits the editor itself
        cmd = [str(exe), str(uproject), f"-ExecCmds=py {script}", "-unattended",
               "-nosplash", "-stdout", "-FullStdOutLogOutput", "-NoSound"]
    else:
        cmd = [str(exe), str(uproject), "-run=pythonscript", f"-script={script}",
               "-unattended", "-nosplash", "-nullrhi", "-stdout", "-FullStdOutLogOutput"]
    cmd += extra or []
    env = {**os.environ, "CITYGEN_UE_JOB": str(job_path)}
    t = time.time()
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env,
                              timeout=timeout)
    res = (json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file()
           else {"ok": False, "error": "the editor wrote no result (see the log)"})
    res["exit_code"] = proc.returncode
    res["wall_s"] = round(time.time() - t, 1)     # the editor's start and quit included
    res["log"] = str(log)
    result_path.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return res


def import_city(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
                name: str | None = None, timeout: float = 7200.0) -> dict:
    """`citygen unreal`: the manifest, then the headless import; the importer's result
    (created, updated, deleted and unchanged actors and assets, timings)."""
    build = Path(build_dir).resolve()
    up = Path(uproject).resolve()
    root = find_engine(engine)
    if root is None:
        raise RuntimeError("no Unreal Engine found (pass --engine or set CITYGEN_UE_ROOT)")
    t = time.time()
    man_path = write_manifest(build, name)
    manifest_s = round(time.time() - t, 1)
    added = prepare_project(up)
    out = man_path.parent
    job = {"mode": "import", "manifest": str(man_path), "build_dir": str(build),
           "result": str(out / "import_result.json")}
    res = run_editor(root, up, UE_DIR / "import_city.py", job, out / "import_log.txt",
                     timeout=timeout)
    res["manifest_s"] = manifest_s
    res["plugins_enabled"] = added
    return res


def check_city(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
               shots: str | Path | None = None, timeout: float = 3600.0,
               width: int = 3840) -> dict:
    """`citygen unreal --check`: the imported level played in the editor: World Partition
    streaming around the player, line traces onto the ground, streets and roofs, the
    player walked along a sidewalk; with `shots`, rendered views of the city."""
    build = Path(build_dir).resolve()
    up = Path(uproject).resolve()
    root = find_engine(engine)
    if root is None:
        raise RuntimeError("no Unreal Engine found (pass --engine or set CITYGEN_UE_ROOT)")
    out = build / OUT_DIR
    man_path = out / "manifest.json"
    if not man_path.is_file():
        raise FileNotFoundError(f"{man_path}: import the city first")
    job = {"mode": "check", "manifest": str(man_path), "build_dir": str(build),
           "result": str(out / "check_result.json"),
           "shots": str(Path(shots).resolve()) if shots else None, "width": width}
    return run_editor(root, up, UE_DIR / "check_city.py", job, out / "check_log.txt",
                      timeout=timeout, gui=True, extra=["-RenderOffscreen"])


def import_summary(res: dict) -> str:
    if not res.get("ok"):
        return f"FAIL: Unreal import ({res.get('wall_s')} s); log {res.get('log')}"
    a, m = res["actors"], res["meshes"]
    return (f"PASS: {res['city']} into {res['level']}: actors {a['created']} created, "
            f"{a['updated']} updated, {a['deleted']} deleted, {a['unchanged']} unchanged "
            f"({res['actor_count']} in all); meshes {m['imported']} imported, "
            f"{m['kept']} kept, {m['deleted']} deleted; {res['tiles_imported']} glTF files "
            f"imported; {res['dirty_packages']} packages saved; {res['wall_s']} s")


def check_summary(res: dict) -> str:
    if not res.get("ok"):
        return f"FAIL: Unreal check ({res.get('wall_s')} s); log {res.get('log')}"
    return f"PASS: {res.get('city')}: " + "; ".join(res.get("lines", [])) + \
        f"; {res['wall_s']} s"
