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

Stage 2 (assetgen): when BUILD_DIR/assets holds `unreal_contribution.*.json` (AG1's
buildings, AG7's streets), they are read in sorted file order as layer 2 over the blockout
(`stage2`, the manifest's `stage2`): an actor per entry at its own pivot in place of the
blockout actors of its key and its `replaces`, an instanced actor per entry and part kind,
the glTF packs to import (one static mesh per node) and a material per part and slot; their
walkway lines replace graphs.json's. From AG6, the materials carry textures (the
contributions' `textures`: the library's sets and atlases through `assets/library`, the
city's sign pages under `assets/textures`), texture, scalar and vector parameters, and a
building's entry maps its wall and roof slots to its era's instances (`materials`). Without them (or with `assets` off) the manifest is the
blockout's alone, byte for byte.

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
import threading
import time
from pathlib import Path

from . import progress as PG

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
# GeometryScripting: stage 2 building collision (convex hulls of the mass pieces)
PLUGINS = ["PythonScriptPlugin", "EditorScriptingUtilities", "GeometryScripting"]
UE_DIR = Path(__file__).parent / "ue"
# what Play puts you in: the fly pawn (free camera, no collision) or the project's own game
# mode and pawn (the First Person template's character with --new-project)
PLAY_MODES = ("fly", "walk")
FLY_SPEED_M_S = 50.0          # the fly pawn's top speed (a 4 km city in about 80 s)
VIEW_M = 1500.0               # how far the level streams in around the player


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


def glb_triangles(path: Path) -> dict[str, int]:
    """Each named node's triangles in a glTF binary, read from its JSON chunk alone."""
    with open(path, "rb") as f:
        n = struct.unpack("<I", f.read(20)[12:16])[0]
        js = json.loads(f.read(n))
    acc, meshes = js.get("accessors", []), js.get("meshes", [])
    out = {}
    for nd in js.get("nodes", []):
        prims = meshes[nd["mesh"]]["primitives"] if "mesh" in nd else []
        out[nd.get("name", "")] = sum(
            acc[p["indices"] if "indices" in p else p["attributes"]["POSITION"]]["count"] // 3
            for p in prims)
    return out


# --- graphs -----------------------------------------------------------------------------------

def _flat(elems: list[dict]) -> dict:
    """Elements (id, kind, ref, width, points, links by id, attrs) as flat arrays: element i
    has points[point_start[i]:point_start[i + 1]] and links[link_start[i]:link_start[i + 1]]
    (indices of other elements); links to ids not in the graph are dropped. M14: `levels`
    (0 the ground, 1 a deck) only when an element is off the ground."""
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
    if any(e.get("level") for e in elems):
        out["levels"] = [int(e.get("level") or 0) for e in elems]
    return out


def _walk_line(w: dict, line: list, absolute: bool) -> list:
    """A walkway's line from stage 2 (`graphs.walkways`: a raised road's sidewalk put on its
    deck, z over the ground as the model's). On a terrain city graphs.json is absolute and
    the model has these walkways at z 0, so their graphs.json z is the ground under them:
    added point by point when the lines match."""
    if absolute and len(line) == len(w["line"]):
        return [[p[0], p[1], round(p[2] + q[2], 2)] for p, q in zip(line, w["line"])]
    return [list(p) for p in line]


def doors_of(contribs: list) -> list[dict]:
    """Stage 2's doors (AG3: the street fronts' entries) as graph elements: id, kind (the
    entrance's, or `shop.<use>`), ref the walkway it opens to, width, its point (the
    threshold's middle on the facade, z over the building's pivot), attrs (building,
    entrance or unit index, outward yaw, height, flush, where its walkway came from)."""
    out = []
    for _, c, _ in contribs:
        for e in c.get("entries", []):
            px, py, pz = (float(v) for v in e.get("pivot", [0.0, 0.0, 0.0]))
            bid = (e.get("ids") or [e["key"]])[0]
            for d in e.get("doors") or []:
                x, y, z = d["position"]
                nx, ny = d["normal"]
                kind = d["kind"] if d["kind"] != "shop" else f"shop.{d.get('use') or 'unit'}"
                attrs = {"building": bid, "yaw": round(math.degrees(math.atan2(ny, nx)), 2),
                         "height": d["height_m"], "flush": bool(d.get("flush"))}
                for k in ("entrance", "unit", "walkway_from"):
                    if d.get(k) is not None:
                        attrs[k] = d[k]
                out.append({"id": d["id"], "kind": kind, "ref": d.get("walkway_id") or "",
                            "width": d["width_m"],
                            "points": [[round(px + x, 3), round(py + y, 3),
                                        round(pz + z, 3)]],
                            "attrs": attrs, "level": e.get("level", 0)})
    return sorted(out, key=lambda d: d["id"])


def flat_graphs(graphs: dict, walk_lines: dict | None = None,
                doors: list | None = None) -> dict:
    """graphs.json (M4 exports) as three flat graphs: lanes (lanes and junction connectors,
    linked to their successors), walkways (linked to their neighbors) and transit (lines
    and stations, linked to each other). `walk_lines`: stage 2's walkway lines by id, used
    over graphs.json's; `doors` (AG3, `doors_of`): a fourth graph, the doors, each with the
    walkway it opens to as its ref."""
    lanes = [{"id": x["id"], "kind": x["kind"], "ref": x["segment_id"] or x["node_id"],
              "width": x["width_m"], "points": x["centerline"], "links": x["successors"],
              "attrs": {"forward": x["forward"], "index": x["index"],
                        "adjacent_ids": x["adjacent_ids"]}, "level": x.get("level", 0)}
             for x in graphs["lanes"]]
    walk_lines = walk_lines or {}
    absolute = graphs.get("heights") == "absolute"
    walks = [{"id": w["id"], "kind": w["kind"], "width": w["width_m"],
              "points": (_walk_line(w, walk_lines[w["id"]], absolute) if w["id"] in walk_lines
                         else w["line"]),
              "links": w["neighbors"], "level": w.get("level", 0)} for w in graphs["walkways"]]
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
    if doors:
        out["doors"] = _flat(doors)        # (AG3: a door per entrance and unit, stage 4's)
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
    return [x for x in (ids.split(";") if isinstance(ids, str) else ids) if x]


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


# M14: the joined objects of a deck's streets, its slab and its ramps stand on level 1
DECK_LEVEL = {"deck_road": 1, "deck_junction": 1, "deck_crosswalk": 1, "deck_sidewalk": 1,
              "deck_slab": 1, "deck_ramp": 1}


def _level(category: str, props: dict) -> int:
    """The street level an object stands on: a deck's streets, slab and ramps, a building's
    `level` (on a deck). A road object's `level` is its road level (M7's viaducts 1 and 2,
    M9's tunnels -1), not a deck's, so it does not count."""
    if category in DECK_LEVEL:
        return int(props.get("level") or DECK_LEVEL[category])
    if category in ("building", "landmark"):
        return int(props.get("level") or 0)
    return 0


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


# --- stage 2 (assetgen): layer 2 over the blockout -------------------------------------------

ASSETS_DIR = "assets"                       # BUILD_DIR/assets: assetgen's packs
CONTRIBUTIONS = "unreal_contribution.*.json"
STAGE2_FOLDER = "Assets"                    # under the city's content root
# the Custom Primitive Data indices a stage 2 material may take its tint from (the masters
# read a color at each: AG1's wall, trim, glass, roof, spandrel and patch tints)
TINT_CPD = (0, 8, 11, 14, 17, 20)
SRGB_PARTS = ("streets", "water")          # AG7 and AG12 write their slot colors as sRGB
EMISSIVE2 = {"neon": 8.0, "emissive": 4.0, "holo": 3.0}  # a master's instances' emissive
# AG6: textures imported once per project (the shared library, `set.` and `atlas.`) or per
# city (its sign pages, `city.`), by pixel hash
TEXTURE_FOLDER_CORE = "Textures"            # under CONTENT_ROOT/Core
TEXTURE_FOLDER_CITY = f"{STAGE2_FOLDER}/Textures"
TEXTURE_KINDS = ("color", "normal", "mask")


def contributions(build_dir: str | Path) -> list[tuple[str, dict, str]]:
    """Stage 2's layer: every BUILD_DIR/assets/unreal_contribution.*.json in sorted file
    order, as (path from BUILD_DIR, contribution, sha256 of the file)."""
    d = Path(build_dir) / ASSETS_DIR
    out = []
    for f in sorted(d.glob(CONTRIBUTIONS)) if d.is_dir() else []:
        data = f.read_bytes()
        c = json.loads(data)
        if c.get("version") != 1 or c.get("layer") != 2:
            raise ValueError(f"{f}: not a version 1, layer 2 contribution")
        out.append((f"{ASSETS_DIR}/{f.name}", c, hashlib.sha256(data).hexdigest()))
    return out


def walk_lines(contribs: list) -> dict:
    """Stage 2's walkway lines by id (`graphs.walkways`), in contribution order."""
    out = {}
    for _, c, _ in contribs:
        out.update((c.get("graphs") or {}).get("walkways") or {})
    return out


def _linear(c) -> list[float]:
    return [round(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4, 6) for x in c]


def stage2(man: dict, build: Path, contribs: list) -> dict:
    """Stage 2's contributions layered over the blockout manifest `man` (scope: the
    exporter's contract, `docs/unreal_export.md`): a static mesh actor per entry with a mesh
    (at its pivot, Custom Primitive Data, its tags), an instanced actor per entry and part
    kind, the glTF packs to import (one static mesh per shell, proxy, street or part node;
    collision, Nanite and LODs by entry), the materials (one instance per part and slot)
    and the blockout actors dropped: every entry's own key and every key in its `replaces`
    (M15's prop and plant prototype actors too, by their keys: AG8's variants take their
    place; a `drop` entry only drops them). A key may be in one contribution only."""
    blockout = {o["key"]: (t["name"], o) for t in man["tiles"] for o in t["objects"]}
    blockout.update({i["key"]: (i["tile"], i) for i in man["instances"]})
    owner: dict[str, str] = {}
    mats, packs, actors, insts, chains, textures = {}, {}, [], [], [], {}
    replaced, missing, files = set(), 0, []
    under: dict[str, dict] = {}
    sha_of: dict[str, str] = {}
    tris_of: dict[str, dict[str, int]] = {}

    def pack(part, glb, use):
        stem = Path(glb).stem
        folder = {"mesh": f"{STAGE2_FOLDER}/{pascal(part)}/{stem}",
                  "proxy": f"{STAGE2_FOLDER}/{pascal(part)}Proxies/{stem}",
                  "part": f"{STAGE2_FOLDER}/{pascal(part)}Parts/{stem}"}[use]
        k = (glb, folder)
        if k not in packs:
            path = build / ASSETS_DIR / glb
            packs[k] = {"glb": f"{ASSETS_DIR}/{glb}" if path.is_file() else None,
                        "folder": folder, "part": part, "use": use, "meshes": {}}
        return packs[k]

    def file_sha(glb):
        if glb not in sha_of:
            p = build / ASSETS_DIR / glb
            sha_of[glb] = hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else ""
        return sha_of[glb]

    def node_tris(glb, node):
        # (a node's own triangles in its pack: an entry's `triangles` may count more, AG3's
        # shell entries count their street front's too)
        if glb not in tris_of:
            p = build / ASSETS_DIR / glb
            tris_of[glb] = glb_triangles(p) if p.is_file() else {}
        return tris_of[glb].get(node, 1)

    def mesh(pk, node, h, collision, nanite, shape=None, fallback=False):
        a = asset_name(node)
        pk["meshes"][a] = {"asset": a, "hash": content_hash([h, node, collision, nanite]),
                           "collision": collision, "nanite": nanite}
        if shape:
            # (AG8's plants: Nanite foliage, `voxelize`, AG0)
            pk["meshes"][a]["shape_preservation"] = shape
            pk["meshes"][a]["hash"] = content_hash([h, node, collision, nanite, shape])
        if fallback:
            # (AG3's street fronts: complex collision is built from the Nanite fallback, so
            # it keeps every triangle and doorways and steps collide as drawn)
            pk["meshes"][a]["fallback_full"] = True
            pk["meshes"][a]["hash"] = content_hash([h, node, collision, nanite, "full"])
        return f"{pk['folder']}/{a}", pk["meshes"][a]["hash"]

    for rel, c, sha in contribs:
        part = c.get("part") or c.get("stage") or "stage2"
        files.append({"file": rel, "part": part, "stage": c.get("stage"), "sha256": sha,
                      "entries": len(c["entries"])})
        under.update(c.get("underwater") or {})        # (AG12: per water body)
        for name, t in sorted((c.get("textures") or {}).items()):
            if t.get("kind") not in TEXTURE_KINDS:
                raise ValueError(f"{rel}: texture {name}: kind {t.get('kind')} is not one of "
                                 f"{list(TEXTURE_KINDS)}")
            rec = {"file": f"{ASSETS_DIR}/{t['file']}", "hash": t["pixels_sha256"][:16],
                   "kind": t["kind"], "srgb": bool(t.get("srgb", t["kind"] == "color")),
                   "size": t.get("size"),
                   "folder": (f"{man['content_root']}/{TEXTURE_FOLDER_CITY}"
                              if name.startswith("city.")
                              else f"{CONTENT_ROOT}/Core/{TEXTURE_FOLDER_CORE}"),
                   "asset": "T_" + asset_name(name)}
            if name in textures and textures[name]["hash"] != rec["hash"]:
                raise ValueError(f"{rel}: texture {name} differs from the one another "
                                 "contribution names")
            textures[name] = rec
        for name, p in sorted(c.get("materials", {}).items()):
            tint = p.get("tint_cpd")
            if tint is not None and tint not in TINT_CPD:
                raise ValueError(f"{rel}: material {name}: tint_cpd {tint} is not one of "
                                 f"{list(TINT_CPD)}")
            col = _linear(p["color"]) if part in SRGB_PARTS else list(p["color"])
            mats[f"{part}.{name}"] = {
                "asset": "MI_" + asset_name(f"{part}.{name}"), "part": part, "key": name,
                "slot": p.get("slot", name),
                "master": p["master"], "color": col, "roughness": p.get("roughness", 0.85),
                "metallic": p.get("metallic", 0.0),
                "emissive": EMISSIVE2.get(p["master"], 0.0),
                "tint_cpd": -1 if tint is None else tint,
                "tint_scale": p.get("tint_scale", 1.0),
                "tint_times_color": bool(p.get("tint_times_color", False))}
            if p.get("textures") or p.get("scalars") or p.get("vectors"):
                # AG6: texture parameters (by texture name, with its pixel hash, so the
                # instance changes when a texture does), scalars and vectors
                for t in (p.get("textures") or {}).values():
                    if t not in textures:
                        raise ValueError(f"{rel}: material {name}: no texture {t}")
                mats[f"{part}.{name}"].update(
                    textures={k: {"texture": t, "hash": textures[t]["hash"]}
                              for k, t in sorted((p.get("textures") or {}).items())},
                    scalars=dict(sorted((p.get("scalars") or {}).items())),
                    vectors=dict(sorted((p.get("vectors") or {}).items())))
        for e in c["entries"]:
            k = e["key"]
            if k in owner:
                raise ValueError(f"{k}: in {owner[k]} and {rel} (a key may be in one "
                                 "contribution only)")
            owner[k] = rel
            bo = blockout.get(k)
            if e.get("drop"):
                # (AG8: every instance of a prototype actor left out: it goes, nothing comes)
                for r in [k] + list(e.get("replaces", [])):
                    if r in blockout:
                        replaced.add(r)
                    elif r != k:
                        missing += 1
                continue
            tags = e.get("tags") or {}
            col = e.get("collision") or {}
            if col.get("simple") or col.get("convex"):
                collision = {"boxes": col.get("simple") or [], "convex": col.get("convex") or []}
            elif col.get("none"):
                collision = {"none": True}
            else:
                collision = {"complex": True}
            nanite = bool(e.get("nanite", True))
            path = h = None
            empty = False
            if e.get("lods"):
                # a non-Nanite LOD chain: each LOD node imported, the chain made as `asset`
                pk = pack(part, e["glb"], "mesh")
                lods = []
                for lo in e["lods"]:
                    p_, _ = mesh(pk, lo["node"], e["hash"], {"none": True}, False)
                    lods.append({"mesh": p_, "screen_size": lo["screen_size"]})
                path = f"{pk['folder']}/{asset_name(e['asset'])}"
                h = content_hash([e["hash"], lods, collision])
                chains.append({"mesh": path, "hash": h, "lods": lods, "collision": collision})
            elif e.get("node") and e.get("triangles", 0) > 0:
                if node_tris(e["glb"], e["node"]) > 0:
                    path, h = mesh(pack(part, e["glb"], "mesh"), e["node"], e["hash"],
                                   collision, nanite, fallback=bool(e.get("fallback_full")))
                else:
                    # (AG3: a one-floor building its street front takes whole has an empty
                    # shell node: no mesh, which Unreal refuses ("Bad MeshDescription", and
                    # the HLOD build fails on it), but it still takes the blockout's place)
                    empty = True
            if e.get("proxy"):
                px = e["proxy"]
                mesh(pack(part, px["glb"], "proxy"), px["node"], e["hash"], {"none": True},
                     False)
            tile = tags.get("cg.tile") or e.get("tile") or (bo[0] if bo else "")
            first = bo or next((blockout[r] for r in e.get("replaces", []) if r in blockout),
                               None)
            # the category, district and level of the blockout actor it takes the place of
            # (its own key's, else the first it replaces), so the check sees the same kinds
            base = {"category": first[1]["category"] if first else e["kind"].split(".")[0],
                    "type": tags.get("cg.type") or e["kind"], "tile": tile,
                    "district": (tags.get("cg.district") or (first[1]["district"] if first
                                                             else "") or _district(k, {})),
                    "ids": e.get("ids") or (bo[1]["ids"] if bo else [k])}
            if first and first[1].get("level"):
                base["level"] = first[1]["level"]
            elif e.get("level"):
                base["level"] = e["level"]          # (AG3: a street front on a deck)
            pivot = [float(v) for v in e.get("pivot", [0.0, 0.0, 0.0])]
            yaw = float(e.get("yaw_deg", 0.0))
            made = False
            if path:
                a = {"key": k, "mesh": path, "pivot": pivot, "yaw_deg": yaw,
                     "cpd": e.get("cpd") or [], **base}
                if e.get("materials"):
                    # AG6: the slots this actor gives another instance (its era's walls)
                    a["materials"] = {slot: "MI_" + asset_name(f"{part}.{m}")
                                      for slot, m in sorted(e["materials"].items())}
                if "none" in collision:
                    a["no_collision"] = True
                if e.get("hero"):
                    a["hero"] = e["hero"]["kind"]          # (AG5: a landmark's or the wheel's)
                if e.get("plinth_m"):
                    # (AG5: its stepped plinth reaches this far under the pivot, M13's slopes)
                    a["plinth_m"] = float(e["plinth_m"])
                if e.get("doors"):
                    # (AG3: the doors of a street front, tagged on its actor for stage 4)
                    a["doors"] = [f"{d['id']}@{d.get('walkway_id') or ''}" for d in e["doors"]]
                if e.get("links"):
                    # (AG4: what a skybridge joins, `building:<id>`, `walkway:<id>`, stage 4's)
                    a["links"] = list(e["links"])
                a["hash"] = content_hash([a, h])
                actors.append(a)
                made = True
            for p in e.get("parts") or []:
                glb = p.get("glb") or e["glb"]
                # a building's parts have none (AG2: its simple collision covers its masses;
                # a body per instance, 1.3 M in Vesper Bay, is more than play can stream)
                pcol = p.get("collision") or ({"none": True} if base["category"] in
                                              ("building", "landmark") else {"complex": True})
                mp, mh = mesh(pack(part, glb, "part"), p["node"], file_sha(glb), pcol,
                              p.get("nanite", True), p.get("shape_preservation"))
                a = {"key": f"{k}.{p['kind']}", "entry": k, "kind": p["kind"], "mesh": mp,
                     "pivot": pivot, "yaw_deg": yaw, "cpd": e.get("cpd") or [], **base}
                if p.get("xforms_file"):
                    # (AG13's grass: its transforms in a file of its tile's, by its node,
                    # so millions of clumps stay out of the manifest; the file's sha256 in
                    # the hash)
                    a.update(xforms_file=f"{ASSETS_DIR}/{p['xforms_file']}",
                             xforms_key=p["node"], count=int(p["count"]),
                             xforms_sha=file_sha(p["xforms_file"]))
                else:
                    a["xforms"] = p["xforms"]
                if p.get("cull_m"):
                    a["cull_m"] = [float(v) for v in p["cull_m"]]     # (AG13: the grass fades)
                if p.get("shadow") is False:
                    a["no_shadow"] = True
                if p.get("cull_m"):
                    a["no_hlod"] = True          # (faded out near the player: no HLOD)
                if p.get("ids"):
                    a["ids"] = p["ids"]          # (one citygen id per transform)
                if pcol.get("none"):
                    a["no_collision"] = True     # (AG8's plants, AG2's parts)
                if e.get("materials"):
                    # AG6: the era's walls on AG2's parts too (panels, concrete, plaster),
                    # as on the parts merged into the shell
                    a["materials"] = {slot: "MI_" + asset_name(f"{part}.{m}")
                                      for slot, m in sorted(e["materials"].items())}
                a["type"] = p["kind"]
                a["hash"] = content_hash([a, mh])
                insts.append(a)
                made = True
            if not made and not empty:
                continue
            if bo:
                replaced.add(k)
            for r in e.get("replaces", []):
                if r in blockout:
                    replaced.add(r)
                else:
                    missing += 1
    out_packs = []
    for k in sorted(packs):
        pk = packs[k]
        pk["meshes"] = [pk["meshes"][a] for a in sorted(pk["meshes"])]
        out_packs.append(pk)
    for k, m in mats.items():
        for t in (m.get("textures") or {}).values():
            if t["texture"] not in textures:
                raise ValueError(f"material {k}: no texture {t['texture']}")
    masters = sorted({m["master"] for m in mats.values()})
    # AG12: an underwater post-process volume beside each of M16's swim boxes of a body
    uw = []
    for s in man.get("swim", []):
        u = under.get(s["water_id"])
        if u is None:
            continue
        rec = {"key": "underwater." + s["key"].split(".", 1)[1], "water_id": s["water_id"],
               "tile": s["tile"], "box": s["box"], "z": s["z"], "water": u["water"],
               "tint": u["tint"], "fog": u["fog"]}
        rec["hash"] = content_hash(rec)
        uw.append(rec)
    return {"files": files, "masters": masters, "materials": mats, "packs": out_packs,
            "underwater": uw,
            "textures": dict(sorted(textures.items())),
            "lod_chains": sorted(chains, key=lambda x: x["mesh"]),
            "actors": sorted(actors, key=lambda a: a["key"]),
            "instances": sorted(insts, key=lambda a: a["key"]),
            "replaced": sorted(replaced),
            "counts": {"entries": len(owner), "actors": len(actors),
                       "instance_actors": len(insts),
                       "instances": sum(a["count"] if "count" in a else len(a["xforms"])
                                        for a in insts),
                       "replaced": len(replaced), "replaces_missing": missing,
                       "packs": len(out_packs),
                       "meshes": sum(len(p["meshes"]) for p in out_packs) + len(chains),
                       "materials": len(mats), "textures": len(textures),
                       "heroes": sum(1 for a in actors if a.get("hero")),
                       "underwater_volumes": len(uw)}}


def build_manifest(build_dir: str | Path, name: str | None = None,
                   assets: bool = True) -> dict:
    """The manifest of a blockout output (see the module docstring), with the prototypes'
    meshes and the flat graphs beside it: (manifest, prototype meshes, flat graphs). With
    `assets` (the default), stage 2's contributions in BUILD_DIR/assets are layered over the
    blockout (`stage2`); a build without them gives the blockout's manifest alone."""
    build = Path(build_dir)
    contribs = contributions(build) if assets else []
    plan = json.loads((build / "blockout_plan.json").read_text(encoding="utf-8"))
    city = name or plan["city"]
    mats = {k: material_params(k, v) for k, v in sorted(plan["materials"].items())}
    tiles: dict[str, dict] = {}
    for t in plan["tiles"]:
        tiles[t["name"]] = {"name": t["name"], "ix": t["ix"], "iy": t["iy"],
                            "bounds": t["bounds"], "glb": None, "objects": []}
    instances = []
    decks: dict[str, dict] = {}
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
            if props.get("form"):
                obj["form"] = props["form"]       # (M21: the building's form)
        if _level(o["category"], props):
            obj["level"] = _level(o["category"], props)
        if o["category"] == "deck_slab":
            dk = decks.setdefault(props["citygen_id"], {
                "id": props["citygen_id"], "level": int(props.get("level") or 1),
                "top_m": props.get("top_m"), "district": props.get("district", ""),
                "keys": []})
            dk["keys"].append(o["name"])
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
        graphs = flat_graphs(json.loads((build / "graphs.json").read_text(encoding="utf-8")),
                             walk_lines(contribs), doors_of(contribs))
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
    if decks:
        # M14: the decks (their slab actors by key), for stage 4's levels
        man["decks"] = [decks[k] for k in sorted(decks)]
    if plan.get("swim"):
        # M16: a swim volume (water physics volume) per box of a water body and tile
        man["swim"] = [{**s, "hash": content_hash(s)} for s in plan["swim"]]
        man["counts"]["swim_volumes"] = len(man["swim"])
    if contribs:
        man["stage2"] = stage2(man, build, contribs)
        man["counts"]["actors"] = len(actor_hashes(man))
    man["hash"] = content_hash({k: v for k, v in man.items() if k != "plan_sha256"})
    return man, meshes, graphs


# the importer's always-loaded lighting actors (`ue/import_city.py`, `Importer.lighting`)
LIGHTING = ("lighting.sun", "lighting.sky", "lighting.atmosphere")


def actor_hashes(man: dict) -> dict[str, str]:
    """Every actor an import of `man` makes, by key, with the content hash the importer
    compares it by (`ue/import_city.py` hashes the player start and the lights the same way)."""
    out = {o["key"]: o["hash"] for t in man["tiles"] for o in t["objects"]}
    out.update({i["key"]: i["hash"] for i in man["instances"]})
    out.update({s["key"]: s["hash"] for s in man.get("swim", [])})
    s2 = man.get("stage2")
    if s2:
        # stage 2's actors over the blockout's: the keys it replaces dropped, its own added
        for k in s2["replaced"]:
            out.pop(k, None)
        out.update({a["key"]: a["hash"] for a in s2["actors"] + s2["instances"]})
        out.update({u["key"]: u["hash"] for u in s2.get("underwater", [])})
    out["player_start"] = content_hash(man["player_start"])
    out.update({k: content_hash([k, "v1"]) for k in LIGHTING})
    return out


def actor_kinds(man: dict) -> dict[str, str]:
    """Every blockout and stage 2 actor's class by key: a static mesh actor (`mesh`) or an
    instanced one (`instances`, BP_CityGenInstances)."""
    out = {o["key"]: "mesh" for t in man["tiles"] for o in t["objects"]}
    out.update({i["key"]: "instances" for i in man["instances"]})
    out.update({s["key"]: "swim" for s in man.get("swim", [])})
    s2 = man.get("stage2")
    if s2:
        for k in s2["replaced"]:
            out.pop(k, None)
        out.update({a["key"]: "mesh" for a in s2["actors"]})
        out.update({i["key"]: "instances" for i in s2["instances"]})
        out.update({u["key"]: "underwater" for u in s2.get("underwater", [])})
    return out


def manifest_changes(old: dict, new: dict) -> dict[str, list[str]]:
    """The actors an import of `new` over an import of `old` creates, updates and deletes.
    A key whose actor changes class (AG8's exact props over M15's instanced ones) is
    deleted and created again, as the importer does."""
    a, b = actor_hashes(old), actor_hashes(new)
    ka, kb = actor_kinds(old), actor_kinds(new)
    moved = {k for k in a.keys() & b.keys() if ka.get(k) != kb.get(k)}
    return {"created": sorted((b.keys() - a.keys()) | moved),
            "updated": sorted(k for k in a.keys() & b.keys()
                              if a[k] != b[k] and k not in moved),
            "deleted": sorted((a.keys() - b.keys()) | moved)}


def write_manifest(build_dir: str | Path, name: str | None = None,
                   assets: bool = True) -> Path:
    """BUILD_DIR/unreal/manifest.json, prototypes.glb and graphs.json; the manifest's path.
    `assets` False: the blockout alone, stage 2's contributions left out."""
    build = Path(build_dir)
    for f in ("blockout_plan.json", "tiles.json"):
        if not (build / f).is_file():
            raise FileNotFoundError(f"{build / f}: not a blockout output (run citygen build "
                                    f"--blockout or citygen blockout)")
    man, meshes, graphs = build_manifest(build, name, assets)
    out = build / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    write_glb(meshes, man["materials"], out / "prototypes.glb")
    if graphs is not None:
        (out / "graphs.json").write_text(json.dumps(graphs, separators=(",", ":")) + "\n",
                                         encoding="utf-8", newline="\n")
    path = out / "manifest.json"
    path.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
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
        p.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8", newline="\n")
    return added


MAPS_SECTION = "[/Script/EngineSettings.GameMapsSettings]"


def set_startup_map(uproject: str | Path, level: str) -> bool:
    """Make `level` (/Game/CityGen/<City>/Maps/<City>) the map the editor opens and the game
    starts in: EditorStartupMap and GameDefaultMap in the project's Config/DefaultEngine.ini,
    the rest of the file as it was (its encoding and line endings too). True when it changed."""
    ini = Path(uproject).parent / "Config" / "DefaultEngine.ini"
    ref = f"{level}.{level.rsplit('/', 1)[-1]}"
    raw = ini.read_bytes() if ini.is_file() else b""
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    want = [("EditorStartupMap", ref), ("GameDefaultMap", ref)]
    start = next((i for i, ln in enumerate(lines) if ln.strip() == MAPS_SECTION), None)
    if start is None:
        lines += ([""] if lines and lines[-1].strip() else []) + [MAPS_SECTION] + \
            [f"{k}={v}" for k, v in want]
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")),
                   len(lines))
        for k, v in want:
            at = next((i for i in range(start + 1, end)
                       if lines[i].split("=", 1)[0].strip() == k), None)
            if at is None:
                lines.insert(start + 1, f"{k}={v}")
                end += 1
            else:
                lines[at] = f"{k}={v}"
    new = bom + (nl.join(lines) + nl).encode("utf-8")
    if new == raw:
        return False
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(new)
    return True


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
    up.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8", newline="\n")
    prepare_project(up)
    return up


# what the stages the editor scripts report are called on the progress line
STAGE_LABELS = {"start": "editor start", "materials": "materials and textures",
                "meshes": "blockout meshes", "meshes2": "stage 2 packs and meshes",
                "level": "level", "actors": "actors", "settings": "play, streaming and graphs",
                "save": "saving", "prune": "pruning unused meshes", "digests": "digests",
                "shutdown": "editor shutdown", "check_start": "check: editor start",
                "check_shutdown": "check: editor shutdown",
                "check_load": "check: loading the level",
                "check_shots": "check: shots", "check_walk": "check: walk",
                "check_fly": "check: flight", "hlod": "HLOD build"}
# rough seconds of a first import's stages on the M4 Mac (AG8's Unreal check, this
# importer) from the counts the importer reports first: the overall estimate, scaled by how
# long the stages done so far took against theirs (actors: every spawn looks at every actor
# already in the level)
FIRST_IMPORT_S = {
    "start": lambda c: 30.0,
    "materials": lambda c: 3.0 + 0.15 * c.get("textures", 0),
    "meshes": lambda c: 0.004 * c.get("objects", 0),
    "meshes2": lambda c: 0.018 * c.get("meshes2", 0),
    "level": lambda c: 0.0009 * c.get("actors", 0),
    "actors": lambda c: 0.0025 * c.get("actors", 0) + 2e-7 * c.get("actors", 0) ** 2,
    "settings": lambda c: 5.0,
    "save": lambda c: 0.0012 * c.get("actors", 0),
    "prune": lambda c: 0.003 * c.get("meshes2", 0),
    "digests": lambda c: 0.0002 * (c.get("actors", 0) + c.get("meshes2", 0)),
    "shutdown": lambda c: 10.0,
}


SPEED_DAMP_S = 300.0


class ImportEstimate:
    """The time an import has left in all: the importer's first line gives its counts
    (`plan`), each stage then its rate. Only for a first import (an import over an earlier
    one skips most of the work, in ways the counts do not show)."""

    def __init__(self, progress):
        self.p = progress
        self.prior: dict | None = None
        self.done: dict[str, float] = {}
        self.cur, self.stage = None, None

    def plan(self, msg: dict) -> None:
        if msg.get("op") != "plan" or not msg.get("first"):
            return
        self.prior = {k: f(msg) for k, f in FIRST_IMPORT_S.items()}
        what = ", ".join(x for x in (
            f"{msg['packs']} stage 2 packs ({msg['meshes2']} meshes)" if msg.get("packs") else "",
            f"{msg.get('objects', 0)} blockout objects", f"{msg.get('actors', 0)} actors") if x)
        self.p.note(f"first import: {what}; about {PG.fmt_s(self.left())} in all (an "
                    "estimate from this Mac's times)")
        self.p.set_extra(self.text)

    def begin(self, key, stage) -> None:
        self.cur, self.stage = key, stage

    def end(self, key, seconds) -> None:
        self.done[key] = self.done.get(key, 0.0) + seconds
        if key == self.cur:
            self.cur, self.stage = None, None

    def left(self) -> float:
        prior = self.prior or {}
        # how fast this machine goes: the stages done against their estimates (the editor's
        # start and shutdown aside), damped by SPEED_DAMP_S so one short stage does not
        # rescale the rest
        big = [k for k in self.done if k not in ("start", "shutdown") and
               prior.get(k, 0.0) >= 5.0]
        est = sum(prior[k] for k in big)
        act = sum(self.done[k] for k in big)
        speed = min(5.0, max(0.2, (act + SPEED_DAMP_S) / (est + SPEED_DAMP_S)))
        rest = sum(v * speed for k, v in prior.items() if k not in self.done and k != self.cur)
        if self.cur in prior and self.stage is not None:
            now = self.stage.left_s()
            rest += now if now is not None else max(0.0, prior[self.cur] * speed -
                                                    self.stage.elapsed())
        return rest

    def text(self) -> str:
        left = self.left() if self.prior else 0.0
        return f"about {PG.fmt_s(left)} left in all" if left >= 1.0 else ""


def _pump(proc, log_file, relay, done_marker="CITYGEN_UE_DONE"):
    """The editor's output into its log, byte for byte, its progress lines to `relay`; at
    the script's done line the editor's shutdown begins."""
    def on_line(line):
        if PG.MARKER in line:
            relay.feed(line)
        elif done_marker in line:
            relay.open("shutdown")

    _copy(proc, log_file, on_line)


def _copy(proc, log_file, on_line, stop=None):
    for raw in iter(proc.stdout.readline, b""):
        if stop is not None and stop.is_set():
            return
        try:
            log_file.write(raw)
        except ValueError:          # (the log closed: the editor is gone, see _streamed)
            return
        if on_line is None:
            continue
        try:
            on_line(raw.decode("utf-8", "replace"))
        except Exception as ex:
            # the progress is only shown: a fault in it must not stop this copy, or the
            # pipe fills and the editor blocks on its next line of output
            print(f"progress: {ex!r}; the editor's progress is no longer shown",
                  file=sys.stderr)
            on_line = None
    try:
        log_file.flush()
    except ValueError:
        pass


PIPE_GRACE_S = 15.0


def _streamed(cmd: list[str], log: Path, on_line, timeout: float, env=None) -> int:
    """Run `cmd` with its output copied to `log` byte for byte and each line to `on_line`
    as it comes; its exit code. A process the editor starts (a trace or cache server) can
    keep the pipe open after the editor exits: the copy is then given a few seconds."""
    stop = threading.Event()
    with open(log, "wb") as f:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        th = threading.Thread(target=_copy, args=(proc, f, on_line, stop), daemon=True)
        th.start()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            stop.set()
            th.join(10)
            raise
        th.join(PIPE_GRACE_S)
        stop.set()
    return proc.returncode


def run_editor(root: Path, uproject: Path, script: Path, job: dict, log: Path,
               timeout: float = 7200.0, gui: bool = False, extra: list[str] | None = None,
               estimate: bool = False) -> dict:
    """Run `script` in the editor on `uproject` (headless commandlet, or the full editor for
    play-in-editor checks and renders) with the job in $CITYGEN_UE_JOB; the job's result.
    The script's progress lines go to the active progress (`citygen.progress`), with an
    overall estimate for a first import when `estimate`."""
    job_path = log.with_suffix(".job.json")
    job_path.write_text(json.dumps(job, indent=1) + "\n", encoding="utf-8", newline="\n")
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
    p = PG.active()
    est = ImportEstimate(p) if estimate and not p.quiet else None    # (none shown: none)
    relay = PG.Relay(p, STAGE_LABELS, on_begin=est.begin if est else None,
                     on_end=est.end if est else None, on_other=est.plan if est else None)
    t = time.time()

    pre = "check_" if gui else ""          # (the full editor: the check's own start, quit)

    def on_line(line):
        if PG.MARKER in line:
            relay.feed(line)
        elif "CITYGEN_UE_DONE" in line:
            relay.open(pre + "shutdown")

    relay.open(pre + "start")
    try:
        code = _streamed(cmd, log, on_line, timeout, env)
    except subprocess.TimeoutExpired:
        relay.close(ok=False)
        p.set_extra("")
        raise
    relay.close(ok=code == 0)
    p.set_extra("")
    res = (json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file()
           else {"ok": False, "error": "the editor wrote no result (see the log)"})
    res["exit_code"] = code
    res["wall_s"] = round(time.time() - t, 1)     # the editor's start and quit included
    res["log"] = str(log)
    result_path.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


def import_city(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
                name: str | None = None, timeout: float = 7200.0,
                assets: bool = True, play: str = "fly", fly_speed: float = FLY_SPEED_M_S,
                startup: bool = True, view_m: float = VIEW_M) -> dict:
    """`citygen unreal`: the manifest, then the headless import; the importer's result
    (created, updated, deleted and unchanged actors and assets, timings). `assets` False
    imports the blockout alone (stage 2's actors, if imported before, go; its meshes
    stay for the next import with it). `play` is what Play puts you in: "fly" (the fly
    pawn at `fly_speed` m/s) or "walk" (the project's own game mode and pawn); `view_m` how
    far the level streams around the player; `startup` makes the city the project's
    startup and default map."""
    if play not in PLAY_MODES:
        raise ValueError(f"play: {play!r} is not one of {', '.join(PLAY_MODES)}")
    build = Path(build_dir).resolve()
    up = Path(uproject).resolve()
    root = find_engine(engine)
    if root is None:
        raise RuntimeError("no Unreal Engine found (pass --engine or set CITYGEN_UE_ROOT)")
    t = time.time()
    man_path = write_manifest(build, name, assets)
    manifest_s = round(time.time() - t, 1)
    added = prepare_project(up)
    out = man_path.parent
    job = {"mode": "import", "manifest": str(man_path), "build_dir": str(build),
           "result": str(out / "import_result.json"), "play": play,
           "fly_speed_m_s": float(fly_speed), "view_m": float(view_m)}
    res = run_editor(root, up, UE_DIR / "import_city.py", job, out / "import_log.txt",
                     timeout=timeout, estimate=True)
    res["manifest_s"] = manifest_s
    res["plugins_enabled"] = added
    if res.get("ok") and startup:
        res["startup_map_changed"] = set_startup_map(up, res["level"])
        res["startup_map"] = res["level"]
        Path(job["result"]).write_text(json.dumps(res, indent=1) + "\n",
                                       encoding="utf-8", newline="\n")
    return res


def check_city(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
               shots: str | Path | None = None, timeout: float = 3600.0,
               width: int = 3840, views: list[dict] | None = None) -> dict:
    """`citygen unreal --check`: the imported level played in the editor: World Partition
    streaming around the player, line traces onto the ground, streets and roofs, the
    player walked along a sidewalk; with `shots`, rendered views of the city (the isometric
    one, the blockout's street views and `views`: {name, eye, target} in citygen meters)."""
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
           "shots": str(Path(shots).resolve()) if shots else None, "width": width,
           "views": views or []}
    return run_editor(root, up, UE_DIR / "check_city.py", job, out / "check_log.txt",
                      timeout=timeout, gui=True, extra=["-RenderOffscreen"])


def build_hlods(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
                timeout: float = 7200.0) -> dict:
    """`citygen unreal --hlod`: World Partition's HLOD builder on the imported level (a
    commandlet that renders, so not -nullrhi): the instanced and merged HLOD actors of the
    level's default HLOD layers, set up and built in the HLOD partitions `streaming` sized;
    a second run rebuilds only those whose actors changed."""
    build = Path(build_dir).resolve()
    up = Path(uproject).resolve()
    root = find_engine(engine)
    if root is None:
        raise RuntimeError("no Unreal Engine found (pass --engine or set CITYGEN_UE_ROOT)")
    out = build / OUT_DIR
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    level = f"{man['content_root']}/Maps/{man['folder']}"
    log = out / "hlod_log.txt"
    cmd = [str(editor_binary(root)), str(up), "-run=WorldPartitionBuilderCommandlet", level,
           "-Builder=WorldPartitionHLODsBuilder", "-AllowCommandletRendering", "-unattended",
           "-nosplash", "-stdout", "-FullStdOutLogOutput"]
    t = time.time()
    p = PG.active()
    stage = p.begin(STAGE_LABELS["hlod"])

    def on_line(line):
        # the builder's count of HLOD actors, then a decision per actor (built or kept)
        m = re.search(r"World contains (\d+) HLOD actors", line)
        if m:
            stage.set_total(int(m.group(1)))
        elif "final decision:" in line:
            stage.advance()

    try:
        code = _streamed(cmd, log, on_line, timeout)
    except subprocess.TimeoutExpired:
        stage.finish(ok=False)
        raise
    stage.finish(ok=code == 0)
    text = log.read_text(encoding="utf-8", errors="replace")
    have = re.findall(r"World contains (\d+) HLOD actors", text)
    res = {"ok": code == 0, "exit_code": code, "level": level,
           "hlod_actors": int(have[-1]) if have else None,
           # the builder looks at every HLOD actor and rebuilds those whose input changed
           "rebuilt": text.count("final decision: ApproveRebuild"),
           "wall_s": round(time.time() - t, 1), "log": str(log)}
    (out / "hlod_result.json").write_text(json.dumps(res, indent=1) + "\n",
                                          encoding="utf-8", newline="\n")
    return res


def hlod_summary(res: dict) -> str:
    if not res.get("ok"):
        return f"FAIL: HLOD build ({res.get('wall_s')} s); log {res.get('log')}"
    return (f"PASS: HLODs of {res['level']}: {res['hlod_actors']} HLOD actors, "
            f"{res['rebuilt']} built (the rest unchanged); {res['wall_s']} s")


def play_summary(res: dict) -> str:
    """What Play puts you in and where, after an import."""
    p, s = res.get("play") or {}, res.get("streaming") or {}
    line = ("Play: flying (the fly pawn, {:g} m/s)".format(p.get("fly_speed_m_s", 0.0))
            if p.get("mode") == "fly" else "Play: walking (the project's own game mode and pawn)")
    if s.get("set"):
        line += f"; the level streams in {s['loading_ranges_m'][0]:g} m around the player"
    if res.get("startup_map"):
        line += f"; startup and default map {res['startup_map']}"
    return line


def import_summary(res: dict) -> str:
    if not res.get("ok"):
        return f"FAIL: Unreal import ({res.get('wall_s')} s); log {res.get('log')}"
    a, m = res["actors"], res["meshes"]
    return (f"PASS: {res['city']} into {res['level']}: actors {a['created']} created, "
            f"{a['updated']} updated, {a['deleted']} deleted, {a['unchanged']} unchanged "
            f"({res['actor_count']} in all); meshes {m['imported']} imported, "
            f"{m['kept']} kept, {m['deleted']} deleted; {res['tiles_imported']} glTF files "
            f"imported; {res['dirty_packages']} packages saved; {res['wall_s']} s"
            + _stage2_summary(res))


def _stage2_summary(res: dict) -> str:
    s = res.get("stage2")
    if not s:
        return ""
    m = s["meshes"]
    t = s.get("textures") or {}
    return (f"; stage 2: {s['actors']} actors over {s['replaced']} blockout actors, "
            f"meshes {m['imported']} imported, {m['kept']} kept, {m['deleted']} deleted "
            f"from {s['packs_imported']} glTF packs"
            + (f", textures {t.get('imported', 0)} imported, {t.get('kept', 0)} kept"
               if t else ""))


def check_summary(res: dict) -> str:
    if not res.get("ok"):
        return f"FAIL: Unreal check ({res.get('wall_s')} s); log {res.get('log')}"
    return f"PASS: {res.get('city')}: " + "; ".join(res.get("lines", [])) + \
        f"; {res['wall_s']} s"
