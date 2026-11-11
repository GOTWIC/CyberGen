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
in per-instance custom data, so a tile's parked cars of one model are one component per part.

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
    """The cars of a library: its folders holding a pack.json."""
    if not library.is_dir():
        return []
    return sorted(d.name for d in library.iterdir() if (d / "pack.json").is_file())


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


def actor_hashes(sec: dict | None) -> dict[str, str]:
    """A placement's actor by key (BP_CityGenGroup), with the hash the importer compares."""
    return {r["key"]: r["hash"] for r in (sec or {}).get("placements", [])}


def actor_kinds(sec: dict | None) -> dict[str, str]:
    return {r["key"]: "vehicles" for r in (sec or {}).get("placements", [])}
