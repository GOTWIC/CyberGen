"""The vehicle library the parked cars draw on: a folder of AG18's game packs
(`vehicles/GAME.md`), one folder per car with its `pack.json`.

Where it is, in this order: the asset spec's `vehicles.library`; `$ASSETGEN_VEHICLES`;
`$CITYGEN_VEHICLES` (the Unreal exporter's); the packs' cache
`~/.cache/cybergen/vehicles/game`. `ASSETGEN_VEHICLES=off` (or `none`, `0`, empty) means no
library: AG8's parked car variants stay, as before AG18. A car is offered when its
`pack.json` is a version 1 vehicle pack whose four LOD files are present; the Vex and
Aurel cars never are (`table.EXCLUDED`).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import table as T

PACK_FORMAT = "cybergen.vehicle_pack"
PACK_VERSION = 1
ENV = "ASSETGEN_VEHICLES"
EXPORTER_ENV = "CITYGEN_VEHICLES"
DEFAULT = Path.home() / ".cache" / "cybergen" / "vehicles" / "game"
OFF = ("", "off", "none", "0", "no", "false")


def library_dir(spec_doc: dict | None = None) -> Path | None:
    """The library folder, or None when turned off (`ASSETGEN_VEHICLES=off`)."""
    v = (spec_doc or {}).get("vehicles") or {}
    if v.get("library"):
        return Path(v["library"]).expanduser()
    if ENV in os.environ:
        val = os.environ[ENV].strip()
        return None if val.lower() in OFF else Path(val).expanduser()
    if os.environ.get(EXPORTER_ENV):
        return Path(os.environ[EXPORTER_ENV]).expanduser()
    return DEFAULT


def read(folder: Path) -> dict | None:
    """A car's summary from its pack folder (None when it is not a usable pack): kind, size
    class, the plan box (min and max x, y; z), LOD files and triangles, part names, show
    colors, and the sha256 of its pack.json (what the placements' hashes see)."""
    p = folder / "pack.json"
    try:
        data = p.read_bytes()
        pk = json.loads(data)
    except (OSError, ValueError):
        return None
    if pk.get("format") != PACK_FORMAT or pk.get("version") != PACK_VERSION:
        return None
    lods = sorted(pk.get("lods") or [], key=lambda r: r["lod"])
    if [r["lod"] for r in lods] != [0, 1, 2, 3]:
        return None
    if not all((folder / r["file"]).is_file() for r in lods):
        return None
    d = pk["dimensions"]
    return {"car": pk["car"], "title": pk.get("title", pk["car"]), "kind": pk["kind"],
            "size_class": (pk.get("size_class") or {}).get("name", "standard"),
            "min": [round(float(x), 4) for x in d["min"]],
            "max": [round(float(x), 4) for x in d["max"]],
            "length": round(float(d["length"]), 4), "width": round(float(d["width"]), 4),
            "lods": [{"file": r["file"], "triangles": int(r["triangles"])} for r in lods],
            "parts": [q["name"] for q in pk.get("parts", [])],
            "colors": {k: v["color"] for k, v in (pk.get("colors") or {}).items()},
            "dir": str(folder.resolve()),
            "pack_sha256": hashlib.sha256(data).hexdigest()}


def load(spec_doc: dict | None = None) -> tuple[Path | None, dict]:
    """(the library folder or None, its usable cars by name)."""
    lib = library_dir(spec_doc)
    if lib is None or not lib.is_dir():
        return lib, {}
    cars = {}
    for d in sorted(lib.iterdir()):
        if not d.is_dir() or d.name in T.EXCLUDED:
            continue
        r = read(d)
        if r is not None and r["car"] == d.name and r["car"] not in T.EXCLUDED:
            cars[r["car"]] = r
    return lib, cars
