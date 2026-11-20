"""AG18's vehicles in the Unreal exporter (venv side: no Unreal, no network).

A vehicle library is a folder of game packs (`vehicles/game.py`, the contract in
`vehicles/GAME.md`), one folder per car with its `pack.json`, four LOD files, the collision
hulls and five textures per baked slot. By default it is `~/.cache/cybergen/vehicles/game`;
`CITYGEN_VEHICLES` or `citygen unreal --vehicles DIR` names another.

Vehicles come into a city by **placement entries** in any stage 2 contribution
(`BUILD/assets/unreal_contribution.*.json`, layer 2), an entry of kind `vehicles`:

    {"key": "vehicles.parked.t+01+00", "kind": "vehicles", "hash": "<16 hex>",
     "tile": "t+01+00", "pivot": [x, y, z], "replaces": ["prop.parked_car.t+01+00"],
     "vehicles": [{"car": "tanager_cab", "id": "d03.prop.parked_car.e12n34",
                   "xform": [x, y, z, yaw_deg],
                   "paint": [[r, g, b], [r, g, b], [r, g, b]],
                   "steer_deg": 0.0}]}

(`xform` from the entry's pivot, citygen meters and degrees as AG8's parts; `paint` the
primary, secondary and accent colors, linear, the pack's show colors where left out;
`steer_deg` turns the wheels that steer). The importer makes one actor per entry
(`BP_CityGenGroup`) with an instanced component per car model and part, its instances' paint
in per-instance custom data, so a tile's parked cars of one model are one component per part
(car_merge_followups: one component, the car's merged mesh, `merge_cars`).

`section` gives the manifest's `vehicles`: the cars the entries name (or, with `all_cars`, the
library's every car) with each file's sha256, the parts and pivots, the materials' parameters,
the show colors, the LODs and their screen sizes, the collision hulls (read from
`collision.glb`), and the placements with their hashes. A city whose contributions name no
vehicle gets no section, and its manifest is byte for byte what it was."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

PACK_FORMAT = "cybergen.vehicle_pack"
PACK_VERSION = 1
LIBRARY_ENV = "CITYGEN_VEHICLES"
DEFAULT_LIBRARY = Path.home() / ".cache" / "cybergen" / "vehicles" / "game"
# the cars out of every city until they are redesigned (vehicles/README.md): the Vex (no packs)
# and the Aurels (Swagnik, 2026-11-12); never imported, a placement naming one refused
EXCLUDED = ("vex_", "aurel_")
FOLDER = "/Game/CityGen/Vehicles"          # every city's vehicles, imported once a project
KIND = "vehicles"                           # a placement entry's kind
VERSION = "1"                               # of what the importer makes of a car (its hash)
LODS = 4
# the engine's LOD screen sizes (the bounding sphere's share of the screen height): LOD0 up
# close (a standard car within about 8 m at a 90 degree view), LOD1 to 20 m, LOD2 to 60 m,
# LOD3 beyond
SCREEN_SIZES = (1.0, 0.35, 0.15, 0.05)
SLOTS = ("body", "wheels")
TEXTURES = {"base_color": ("color", True), "normal": ("normal", False),
            "orm": ("mask", False), "mask": ("mask", False), "emissive": ("color", True)}
CHANNELS = ("primary", "secondary", "accent")
PAINT_CPD = 9                               # three linear colors, per instance


def content_hash(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()[:16]


def library_dir(explicit: str | Path | None = None) -> Path:
    """The vehicle library: `explicit`, else $CITYGEN_VEHICLES, else the packs' cache."""
    if explicit:
        return Path(explicit).expanduser()
    if os.environ.get(LIBRARY_ENV):
        return Path(os.environ[LIBRARY_ENV]).expanduser()
    return DEFAULT_LIBRARY


def library_cars(library: Path) -> list[str]:
    """The cars of a library: its folders holding a pack.json (never an `EXCLUDED` car's)."""
    if not library.is_dir():
        return []
    return sorted(d.name for d in library.iterdir() if (d / "pack.json").is_file()
                  and not d.name.startswith(EXCLUDED))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, _, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError(f"{path}: not a binary glTF")
    n, _ = struct.unpack_from("<I4s", data, 12)
    doc = json.loads(data[20:20 + n])
    off = 20 + n
    blob = b""
    if off < len(data):
        m, _ = struct.unpack_from("<I4s", data, off)
        blob = data[off + 8:off + 8 + m]
    return doc, blob


def _accessor(doc: dict, blob: bytes, k: int) -> list:
    a = doc["accessors"][k]
    v = doc["bufferViews"][a["bufferView"]]
    size = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    fmt = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[a["componentType"]]
    width = struct.calcsize(fmt)
    stride = v.get("byteStride") or width * size
    base = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    out = []
    for i in range(a["count"]):
        row = struct.unpack_from(f"<{size}{fmt}", blob, base + i * stride)
        out.append(row if size > 1 else row[0])
    return out


def glass_box(path: Path) -> dict | None:
    """The box of a pack's glass at LOD0 in the car's frame (x forward, y left, z up, meters),
    {"min": [x, y, z], "max": [x, y, z]}, from the glTF's accessor bounds; None for a car with
    no glass. The importer's glass master takes an eye inside it for an eye in the cabin."""
    doc, blob = _glb(path)
    lo, hi = None, None
    for node in doc.get("nodes", []):
        if node.get("name") != "glass" or "mesh" not in node:
            continue
        t = node.get("translation", [0.0, 0.0, 0.0])
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            k = prim["attributes"]["POSITION"]
            a = doc["accessors"][k]
            amin, amax = a.get("min"), a.get("max")
            if amin is None or amax is None:
                rows = _accessor(doc, blob, k)
                if not rows:
                    continue
                amin = [min(r[i] for r in rows) for i in range(3)]
                amax = [max(r[i] for r in rows) for i in range(3)]
            # (glTF's x, y, z are the car's x, z, -y)
            g0 = [amin[i] + t[i] for i in range(3)]
            g1 = [amax[i] + t[i] for i in range(3)]
            b0, b1 = [g0[0], -g1[2], g0[1]], [g1[0], -g0[2], g1[1]]
            lo = b0 if lo is None else [min(x, y) for x, y in zip(lo, b0)]
            hi = b1 if hi is None else [max(x, y) for x, y in zip(hi, b1)]
    if lo is None:
        return None
    return {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]}


def tangents(path: Path) -> bool:
    """Whether every primitive of a glTF file carries its tangents (GAME.md says they are in
    the glTF; Blender's exporter leaves them out of a mesh it cannot compute them for, and
    the importer then has Unreal compute them, MikkTSpace as the bake's)."""
    doc, _ = _glb(path)
    return all("TANGENT" in p["attributes"] for m in doc.get("meshes", [])
               for p in m["primitives"])


def hulls(path: Path) -> list[dict]:
    """The convex hulls of a pack's collision.glb in the car's frame (x forward, y left, z up,
    meters; glTF's (x, y, z) is the car's (x, -z, y)): name, vertices and triangles."""
    doc, blob = _glb(path)
    out = []
    for node in doc.get("nodes", []):
        if "mesh" not in node or not node.get("name", "").startswith("UCX_"):
            continue
        t = node.get("translation") or [0.0, 0.0, 0.0]
        verts, tris, at = [], [], {}
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            # (welded by position: the file has a vertex per face corner, flat normals, and
            # the importer makes one convex element per connected piece)
            ids = []
            for x, y, z in _accessor(doc, blob, prim["attributes"]["POSITION"]):
                p = (round(x + t[0], 5), round(-(z + t[2]), 5), round(y + t[1], 5))
                if p not in at:
                    at[p] = len(verts)
                    verts.append(list(p))
                ids.append(at[p])
            idx = (_accessor(doc, blob, prim["indices"]) if "indices" in prim
                   else list(range(len(ids))))
            for i in range(0, len(idx) - 2, 3):
                tri = [ids[idx[i]], ids[idx[i + 1]], ids[idx[i + 2]]]
                if len(set(tri)) == 3:
                    tris.append(tri)
        out.append({"name": node["name"], "vertices": verts, "triangles": tris})
    return sorted(out, key=lambda h: h["name"])


def read_pack(folder: Path) -> dict:
    """A car's record for the manifest from its pack folder (refused when the pack is not a
    version 1 vehicle pack or a file it names is missing)."""
    folder = Path(folder)
    pk = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
    if pk.get("format") != PACK_FORMAT or pk.get("version") != PACK_VERSION:
        raise ValueError(f"{folder}: not a version {PACK_VERSION} {PACK_FORMAT}")
    car = pk["car"]
    files = {}
    lods = sorted(pk["lods"], key=lambda r: r["lod"])
    if [r["lod"] for r in lods] != list(range(LODS)):
        raise ValueError(f"{car}: LODs {[r['lod'] for r in lods]}, not 0 to {LODS - 1}")
    names = [r["file"] for r in lods] + [pk["collision"]["file"]]
    textures = {}
    # (a hover car has no wheels: its `wheels` slot is null)
    slots = [s for s in SLOTS if pk["materials"].get(s)]
    if "body" not in slots:
        raise ValueError(f"{car}: no body slot")
    for slot in slots:
        spec = (pk["materials"].get(slot) or {}).get("textures") or {}
        for key, (kind, srgb) in TEXTURES.items():
            if key not in spec:
                raise ValueError(f"{car}: slot {slot} has no {key} texture")
            f = spec[key]["file"]
            names.append(f)
            textures[f"{slot}.{key}"] = {"file": f, "kind": kind, "srgb": srgb,
                                         "size": spec[key].get("size"), "slot": slot,
                                         "map": key}
    for f in names:
        if not (folder / f).is_file():
            raise FileNotFoundError(f"{folder / f}: missing (remake the pack)")
        files[f] = _sha(folder / f)
    for t in textures.values():
        t["sha256"] = files[t["file"]]
    glass = (pk["materials"].get("glass") or {}).get("params") or {}
    parts = []
    for p in pk["parts"]:
        r = {"name": p["name"], "kind": p["kind"], "pivot": p["pivot"],
             "material": p.get("material")}
        for k in ("radius", "width", "side", "axle", "steers", "spins", "follows",
                  "uv_shared_with"):
            if k in p:
                r[k] = p[k]
        parts.append(r)
    rec = {
        "car": car, "title": pk.get("title", car), "kind": pk["kind"],
        "size_class": (pk.get("size_class") or {}).get("name", "standard"),
        "folder": f"{FOLDER}/{car}", "dir": str(folder.resolve()),
        "files": dict(sorted(files.items())), "textures": dict(sorted(textures.items())),
        "lods": [{"lod": r["lod"], "file": r["file"], "triangles": r["triangles"],
                  "parts": r.get("parts", {}), "screen_size": SCREEN_SIZES[r["lod"]],
                  "tangents": tangents(folder / r["file"])}
                 for r in lods],
        "parts": parts,
        "materials": {s: dict((pk["materials"].get(s) or {}).get("params") or {})
                      for s in slots},
        "glass": glass,
        "glass_box": glass_box(folder / lods[0]["file"]),
        "colors": {c: pk["colors"][c]["color"] for c in CHANNELS if c in pk["colors"]},
        "emissive_strength": pk.get("emissive_strength", 1.0),
        "micro_detail": pk.get("micro_detail") or {},
        "dimensions": pk.get("dimensions"),
        "hulls": hulls(folder / pk["collision"]["file"]),
    }
    # (what the importer makes of the car changes when a file or the import's version does,
    # not with the folder it was read from)
    rec["hash"] = content_hash([VERSION, {k: v for k, v in rec.items() if k != "dir"}])
    return rec


def is_placement(e: dict) -> bool:
    return e.get("kind") == KIND


def split(contribs: list) -> tuple[list, list]:
    """Stage 2's contributions without their vehicle placement entries, and those entries
    with the file each came from. A contribution left with no entries and nothing else for
    stage 2 (a placements file of its own) is left out of stage 2."""
    rest, placements = [], []
    for rel, c, sha in contribs:
        mine = [e for e in c.get("entries", []) if is_placement(e)]
        if not mine:
            rest.append((rel, c, sha))
            continue
        placements += [(rel, e) for e in mine]
        other = [e for e in c["entries"] if not is_placement(e)]
        if other or c.get("materials") or c.get("textures") or c.get("graphs") or \
                c.get("underwater"):
            rest.append((rel, {**c, "entries": other}, sha))
    return rest, placements


def named_library(contribs: list) -> Path | None:
    """The library a placements' contribution names (`library`, AG18 step H's), when
    $CITYGEN_VEHICLES names none and that folder is there; else None (the default)."""
    if os.environ.get(LIBRARY_ENV):
        return None
    for _, c, _ in contribs:
        lib = c.get("library")
        if lib and any(is_placement(e) for e in c.get("entries", [])) and Path(lib).is_dir():
            return Path(lib)
    return None


def without_replaced(contribs: list, placements: list) -> list:
    """Stage 2's contributions without the entries a placement replaces (AG8's parked car
    variants of a tile, `prop.parked_vehicle.<tile>`), so they go with the blockout's
    prototype of that key; as they were when no placement replaces any."""
    gone = {k for _, e in placements for k in e.get("replaces", [])}
    if not gone:
        return contribs
    out = []
    for rel, c, sha in contribs:
        es = [e for e in c.get("entries", []) if e.get("key") not in gone]
        out.append((rel, c if len(es) == len(c.get("entries", [])) else {**c, "entries": es},
                    sha))
    return out


def _paint(e: dict, car: dict) -> list[float]:
    cols = e.get("paint") or [car["colors"].get(c, [0.5, 0.5, 0.5]) for c in CHANNELS]
    if len(cols) != 3 or any(len(c) != 3 for c in cols):
        raise ValueError(f"{e.get('id')}: paint is three [r, g, b] colors")
    return [round(float(v), 5) for c in cols for v in c]


def placement(rel: str, e: dict, cars: dict) -> dict:
    """A placement entry as the manifest's record: per car model the instances' ids,
    transforms ([x, y, z, yaw] from the pivot), paint (nine floats) and steer angles."""
    for k in ("key", "tile", "pivot", "vehicles"):
        if k not in e:
            raise ValueError(f"{rel}: a vehicles entry without {k}")
    models: dict[str, dict] = {}
    for v in e["vehicles"]:
        car = cars.get(v.get("car"))
        if car is None:
            raise ValueError(f"{rel}: {e['key']}: no vehicle pack {v.get('car')!r} in the "
                             "library")
        xf = [float(x) for x in v["xform"]]
        if len(xf) != 4:
            raise ValueError(f"{rel}: {e['key']}: xform is [x, y, z, yaw_deg]")
        m = models.setdefault(car["car"], {"ids": [], "xforms": [], "paint": [], "steer": []})
        m["ids"].append(v.get("id") or f"{e['key']}.{len(m['ids'])}")
        m["xforms"].append(xf)
        m["paint"].append(_paint(v, car))
        m["steer"].append(float(v.get("steer_deg", 0.0)))
    rec = {"key": e["key"], "file": rel, "tile": e["tile"], "pivot": list(e["pivot"]),
           "yaw_deg": float(e.get("yaw_deg", 0.0)), "replaces": sorted(e.get("replaces", [])),
           "models": dict(sorted(models.items())),
           "count": sum(len(m["ids"]) for m in models.values())}
    rec["hash"] = content_hash([VERSION, e.get("hash"),
                                {k: v for k, v in rec.items() if k != "file"},
                                {c: cars[c]["hash"] for c in rec["models"]}])
    return rec


def section(placements: list, library: Path | None = None, all_cars: bool = False) -> dict | None:
    """The manifest's `vehicles`, or None when no entry names a vehicle and `all_cars` is
    off (the manifest is then as it was before AG18)."""
    if not placements and not all_cars:
        return None
    lib = library_dir(library)
    want = set(library_cars(lib)) if all_cars else set()
    for rel, e in placements:
        want |= {v.get("car") for v in e.get("vehicles", [])}
    cars = {}
    for c in sorted(want):
        if c and c.startswith(EXCLUDED):
            raise ValueError(f"{c}: out of the cities until it is redesigned (vehicles/README.md;"
                             " run assetgen vehicles on the build again)")
        if not c or not (lib / c / "pack.json").is_file():
            raise FileNotFoundError(f"{lib / str(c)}: no vehicle pack (make it with "
                                    f"vehicles/blender.sh vehicles/game.py --car {c})")
        cars[c] = read_pack(lib / c)
    recs, keys = [], set()
    for rel, e in placements:
        if e["key"] in keys:
            raise ValueError(f"{rel}: {e['key']}: a vehicles key placed twice")
        keys.add(e["key"])
        recs.append(placement(rel, e, cars))
    recs.sort(key=lambda r: r["key"])
    sec = {"version": 1, "library": str(lib.resolve()), "folder": FOLDER,
           "paint_cpd": PAINT_CPD, "cars": cars, "placements": recs,
           "replaced": sorted({k for r in recs for k in r["replaces"]}),
           "counts": {"cars": len(cars), "placements": len(recs),
                      "vehicles": sum(r["count"] for r in recs)}}
    sec["hash"] = content_hash([VERSION, {c: v["hash"] for c, v in cars.items()},
                                [r["hash"] for r in recs]])
    return sec


def check(build_dir: str | Path, uproject: str | Path, engine: str | None = None,
          shots: str | Path | None = None, timeout: float = 3600.0, width: int = 1920,
          lod_cars: list[str] | None = None, wheel_car: str | None = None,
          hull_car: str | None = None) -> dict:
    """`citygen unreal --check-vehicles`: the imported level's vehicles checked in the
    editor (`ue/check_vehicles.py`): meshes, LODs, glass, hulls, placements, pivots, traces;
    with `shots`, views by day and night (the line-up, each car from its pack's hero camera,
    `lod_cars` at each LOD, `wheel_car`'s wheel spun and steered, `hull_car`'s hulls)."""
    from . import unreal as U
    build = Path(build_dir).resolve()
    man_path = build / U.OUT_DIR / "manifest.json"
    root = U.find_engine(engine)
    if root is None:
        raise RuntimeError("no Unreal Engine found (pass --engine or set CITYGEN_UE_ROOT)")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    cars = sorted((man.get("vehicles") or {}).get("cars", {}))
    if not cars:
        raise RuntimeError(f"{man_path}: no vehicles (import a build with placements)")
    job = {"mode": "check_vehicles", "manifest": str(man_path),
           "result": str(build / U.OUT_DIR / "check_vehicles_result.json"),
           "shots": str(Path(shots).resolve()) if shots else None, "width": int(width),
           "lod_cars": lod_cars if lod_cars is not None else cars[:1],
           "wheel_car": wheel_car or next(
               (c for c in cars if any(p["kind"] == "wheel"
                                       for p in man["vehicles"]["cars"][c]["parts"])), None),
           "hull_car": hull_car or cars[0]}
    return U.run_editor(root, Path(uproject).resolve(), U.UE_DIR / "check_vehicles.py", job,
                        build / U.OUT_DIR / "check_vehicles_log.txt", timeout=timeout,
                        gui=True, extra=["-RenderOffscreen"])


def check_summary(res: dict) -> str:
    """One line per check of `check` and the shots."""
    if not res.get("checks"):
        return f"FAIL: vehicle check: {(res.get('error') or 'no result').strip()[-300:]}"
    lines = []
    for k, c in res["checks"].items():
        lines.append(f"{'PASS' if c.get('ok') else 'FAIL'}: vehicles {k}"
                     + (f": {'; '.join(c['bad'][:3])}" if c.get("bad") else ""))
    lines.append(f"vehicle shots: {len(res.get('shots') or [])}; log {res.get('log')}")
    return "\n".join(lines)


# --- car_merge: each car's parts as one mesh, for the moving traffic -------------------------

MERGE_VERSION = 2            # of the merged files (their bytes; 2, car_merge_followups: the
                             # dark glass and the last LOD in the body's section)
MERGE_DIR = "unreal/vehicles"  # under the build: <car>/lod<k>.glb
MERGED_PART = "merged"         # the merged mesh's node and mesh name (SM_<car>_merged)
ROLL_SUFFIX = "_roll"          # a rolling wheel's material: the pack's own, "_roll" added
_NP = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1", 5122: "<i2", 5120: "i1"}
_NORM = {5121: 255.0, 5123: 65535.0, 5120: 127.0, 5122: 32767.0}
_ATTRS = ("POSITION", "NORMAL", "TEXCOORD_0")
# car_merge_followups: the merged mesh's last LOD (the pack's LOD3, from about 90 m) is one
# section, the body's: every other part's primitives (the glass, dark and opaque there already,
# folded from the pack's opaque_from_lod on; the wheels and brakes) join the body's group in a
# flat color, their UV1 (gray, -1 - roughness)
# (no rolling wheel's middle has a y under 0), which M_CgVehicle draws flat (`FLAT` in the
# importer). Each section of every LOD is a draw in every pass of every view the component is
# in (the traffic's components are the whole city's box, LG8): the glass and wheels sections
# out to the body's 900 m were car_merge's added draws; two more LODs dropping them (this
# milestone's first try) added more draws than they saved triangles.
FLAT_TIRE = (0.03, 0.7)        # the wheels and brakes: gray, roughness
FLAT_GLASS = 0.06              # the glass: its color's mean times this (M_CgVehicleGlassDark's)
FLAT_GLASS_ROUGH = 0.05


def _array(doc: dict, blob: bytes, k: int):
    """An accessor as a float64 (or, for indices, int64) numpy array (count, size)."""
    import numpy as np
    a = doc["accessors"][k]
    v = doc["bufferViews"][a["bufferView"]]
    size = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dt = np.dtype(_NP[a["componentType"]])
    stride = v.get("byteStride") or dt.itemsize * size
    base = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    arr = np.ndarray((a["count"], size), dtype=dt, buffer=blob, offset=base,
                     strides=(stride, dt.itemsize))
    if a.get("normalized"):
        return np.maximum(arr.astype(np.float64) / _NORM[a["componentType"]], -1.0)
    return arr.astype(np.int64 if a["componentType"] in (5125, 5123, 5121) and size == 1
                      else np.float64)


def rolls(p: dict) -> bool:
    """Whether a pack part rolls with the car (a wheel that spins: the brakes, which follow a
    wheel to steer, do not)."""
    return p.get("kind") == "wheel" and p.get("spins", True) is not False


def merge_lod(path: Path, parts: list[dict], flat: dict | None = None) -> bytes:
    """One LOD file of a pack as one mesh (node and mesh `MERGED_PART`): every part's
    primitives in the car's frame (in its node's own frame, as the importer takes a part, moved
    to its pivot, as the runtime places it: glTF's (x, y, z) is the car's (x, z, -y)), grouped
    by material in
    the parts' order, a rolling wheel's under its material's name with `ROLL_SUFFIX`;
    POSITION, NORMAL, TEXCOORD_0 and TEXCOORD_1, the wheel's middle a rolling wheel's
    vertices turn about (Unreal's x and z in cm: glTF's x and y times 100; 0 on every other
    vertex). Tangents are left out (the importer has Unreal compute them, MikkTSpace, as it
    does for the parts). `flat` (car_merge_followups): {"into": the body's material, material:
    [gray, roughness]}: a primitive of such a material (the glass, the wheels), a rolling
    wheel's too, joins the body's group with UV1 (gray, -1 - roughness), drawn flat. The bytes
    are a function of the file, the parts and `flat` alone."""
    import numpy as np
    doc, blob = _glb(path)
    names = {n.get("name"): k for k, n in enumerate(doc.get("nodes", [])) if "mesh" in n}
    groups: dict[str, dict] = {}
    flat = flat or {}
    own = {}                      # a node's first material
    for k in names.values():
        for q in doc["meshes"][doc["nodes"][k]["mesh"]]["primitives"]:
            if "material" in q:
                own[k] = doc["materials"][q["material"]]["name"]
                break
    for p in parts:
        k = names.get(p["name"])
        if k is None:
            raise ValueError(f"{path}: part {p['name']} has no node")
        px, py, pz = (float(v) for v in p.get("pivot", [0.0, 0.0, 0.0]))
        at = np.array([px, pz, -py])
        roll = rolls(p)
        mid = at * 100.0
        for prim in doc["meshes"][doc["nodes"][k]["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4:
                raise ValueError(f"{path}: part {p['name']}: not triangles")
            va = prim["attributes"]
            pos = _array(doc, blob, va["POSITION"]) + at
            n = len(pos)
            nrm = _array(doc, blob, va["NORMAL"]) if "NORMAL" in va else np.zeros((n, 3))
            uv0 = _array(doc, blob, va["TEXCOORD_0"]) if "TEXCOORD_0" in va else np.zeros((n, 2))
            idx = (_array(doc, blob, prim["indices"]).reshape(-1) if "indices" in prim
                   else np.arange(n, dtype=np.int64))
            # (a primitive with no material takes its part's: some packs' LOD3 bodies have a
            # few such triangles, which made a section of their own)
            mat = doc["materials"][prim["material"]]["name"] if "material" in prim \
                else own.get(k, p["name"])
            if mat in flat and mat != flat.get("into"):
                gray, rough = flat[mat]
                uv1 = np.tile([float(gray), -1.0 - float(rough)], (n, 1))
                key = flat["into"]
            else:
                uv1 = np.tile([mid[0], mid[1]] if roll else [0.0, 0.0], (n, 1))
                key = mat + (ROLL_SUFFIX if roll else "")
            g = groups.setdefault(key,
                                  {"POSITION": [], "NORMAL": [], "TEXCOORD_0": [],
                                   "TEXCOORD_1": [], "idx": [], "n": 0})
            g["idx"].append(idx + g["n"])
            g["n"] += n
            for key, arr in (("POSITION", pos), ("NORMAL", nrm), ("TEXCOORD_0", uv0),
                             ("TEXCOORD_1", uv1)):
                g[key].append(arr)
    out = {"asset": {"version": "2.0", "generator": f"citygen car_merge {MERGE_VERSION}"},
           "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": MERGED_PART, "mesh": 0}],
           "meshes": [{"name": MERGED_PART, "primitives": []}],
           "materials": [], "accessors": [], "bufferViews": [], "buffers": []}
    data = bytearray()

    def put(arr, ctype, kind, target, minmax=False):
        raw = np.ascontiguousarray(arr).tobytes()
        while len(data) % 4:
            data.append(0)
        out["bufferViews"].append({"buffer": 0, "byteOffset": len(data),
                                   "byteLength": len(raw), "target": target})
        data.extend(raw)
        acc = {"bufferView": len(out["bufferViews"]) - 1, "componentType": ctype,
               "count": int(arr.shape[0]), "type": kind}
        if minmax:
            acc["min"] = [float(v) for v in arr.min(axis=0)]
            acc["max"] = [float(v) for v in arr.max(axis=0)]
        out["accessors"].append(acc)
        return len(out["accessors"]) - 1

    for mat, g in groups.items():
        out["materials"].append({"name": mat})
        attrs = {}
        for key, kind in (("POSITION", "VEC3"), ("NORMAL", "VEC3"), ("TEXCOORD_0", "VEC2"),
                          ("TEXCOORD_1", "VEC2")):
            arr = np.concatenate(g[key]).astype("<f4")
            attrs[key] = put(arr, 5126, kind, 34962, minmax=key == "POSITION")
        idx = np.concatenate(g["idx"]).astype("<u4")
        out["meshes"][0]["primitives"].append(
            {"attributes": attrs, "indices": put(idx, 5125, "SCALAR", 34963),
             "material": len(out["materials"]) - 1, "mode": 4})
    while len(data) % 4:
        data.append(0)
    out["buffers"].append({"byteLength": len(data)})
    js = json.dumps(out, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(data)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON")
            + js + struct.pack("<I4s", len(data), b"BIN\x00") + bytes(data))


def flat_of(path: Path, rec: dict) -> tuple[dict, set]:
    """car_merge_followups: how the last LOD file `path` of car `rec` folds into one section:
    {"into": the body part's material, <material>: [gray, roughness]} for every other material
    of its parts (a glass part's at `FLAT_GLASS` of the pack's glass color, the rest at
    `FLAT_TIRE`), and the glass parts' materials."""
    doc, _ = _glb(path)
    nodes = {n.get("name"): n for n in doc.get("nodes", []) if "mesh" in n}

    def mats(p):
        n = nodes.get(p["name"])
        return [] if n is None else [doc["materials"][q["material"]]["name"]
                                     for q in doc["meshes"][n["mesh"]]["primitives"]
                                     if "material" in q]
    body = next((m for p in rec["parts"] if p["kind"] == "body" for m in mats(p)), None)
    if body is None:
        return {}, set()
    col = (rec.get("glass") or {}).get("color") or [0.3, 0.33, 0.36]
    flat_glass = [round(FLAT_GLASS * sum(col) / len(col), 4), FLAT_GLASS_ROUGH]
    out, glass = {"into": body}, set()
    for p in rec["parts"]:
        for m in mats(p):
            if m != body and m not in out:
                out[m] = flat_glass if p["kind"] == "glass" else list(FLAT_TIRE)
                if p["kind"] == "glass":
                    glass.add(m)
    return dict(sorted(out.items())), glass


def merge_cars(sec: dict | None, build: str | Path) -> dict:
    """car_merge: each car of the manifest's `vehicles` as one mesh a LOD for the moving
    traffic and the fliers (`merge_lod`), written to BUILD/`MERGE_DIR`/<car>/lod<k>.glb only
    when their bytes change, and the car's record given `merged`: the files (relative to the
    build) with their sha256, the materials (the pack's slot names, a rolling wheel's with
    `ROLL_SUFFIX`), the radius the runtime rolls its wheels by (the first rolling wheel's,
    m; 0 for a car with none) and a hash (what the importer compares). The car's own hash is
    left as it was. car_merge_followups: the last LOD is one section and the glass joins the
    body's from the pack's `opaque_from_lod` (`flat_of`, the record's `flat`: the body's
    material and each folded material's gray and roughness); the parked cars take the merged
    mesh too. {car: hash}."""
    out = {}
    if not sec:
        return out
    build = Path(build)
    for car, rec in sorted(sec["cars"].items()):
        folder = Path(rec["dir"])
        files, shas, mats = [], [], []
        flat, glass = flat_of(folder / rec["lods"][-1]["file"], rec)
        opaque_from = int((rec.get("glass") or {}).get("opaque_from_lod", 99))
        for k, lo in enumerate(rec["lods"]):
            # (the glass from the LOD it is dark and opaque in, the rest in the last LOD)
            last = k == len(rec["lods"]) - 1
            sub = {m: v for m, v in flat.items()
                   if m == "into" or last or (k >= opaque_from and m in glass)}
            data = merge_lod(folder / lo["file"], rec["parts"], sub if len(sub) > 1 else None)
            rel = f"{MERGE_DIR}/{car}/lod{lo['lod']}.glb"
            dest = build / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.is_file() or dest.read_bytes() != data:
                dest.write_bytes(data)
            files.append(rel)
            shas.append(hashlib.sha256(data).hexdigest())
            if not mats:
                doc, _ = _glb(dest)
                mats = [m["name"] for m in doc["materials"]]
        wheels = [p for p in rec["parts"] if rolls(p)]
        radius = float(wheels[0].get("radius") or wheels[0]["pivot"][2]) if wheels else 0.0
        m = {"files": files, "sha256": shas, "materials": mats, "roll_radius": round(radius, 4),
             "part": MERGED_PART, "flat": flat}
        m["hash"] = content_hash([MERGE_VERSION, m])
        rec["merged"] = m
        out[car] = m["hash"]
    return out


def actor_hashes(sec: dict | None) -> dict[str, str]:
    """A placement's actor by key (BP_CityGenGroup), with the hash the importer compares."""
    return {r["key"]: r["hash"] for r in (sec or {}).get("placements", [])}


def actor_kinds(sec: dict | None) -> dict[str, str]:
    return {r["key"]: "vehicles" for r in (sec or {}).get("placements", [])}
