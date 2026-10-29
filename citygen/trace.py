"""Stage tracing (`citygen build --trace FILE`): a sha256 of every stage output and of the key
intermediates of the district search, in build order, so two machines can find the first
stage where they part.

Hashes cover exact bits (float64 bytes, WKB), not rounded values, so the first entry that
differs is the first place where the machines computed something different. Stage outputs
carry the full sha256, intermediates (raster weights per iteration, contour output, areas per
round) the first 16 hex digits. Tracing is off unless `start()` was called, and then costs
only the hashing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import platform
import struct
from contextlib import contextmanager
from pathlib import Path

import numpy as np

_LOG: list | None = None
_SCOPE: list[str] = []


def start() -> None:
    global _LOG
    _LOG = []
    _SCOPE.clear()


def stop() -> list:
    global _LOG
    out, _LOG = _LOG or [], None
    _SCOPE.clear()
    return out


def on() -> bool:
    return _LOG is not None


def extend(entries: list | None) -> None:
    """Entries recorded in a worker process, in their place."""
    if _LOG is not None and entries:
        _LOG.extend(entries)


@contextmanager
def scope(name: str):
    """Prefix for the entries recorded inside (variant, landmass, round)."""
    _SCOPE.append(name)
    try:
        yield
    finally:
        _SCOPE.pop()


def _feed(h, v) -> None:
    if v is None:
        h.update(b"N")
    elif isinstance(v, (bool, np.bool_)):
        h.update(b"B1" if v else b"B0")
    elif isinstance(v, (int, np.integer)):
        h.update(b"I" + str(int(v)).encode())
    elif isinstance(v, (float, np.floating)):
        h.update(b"F" + struct.pack("<d", float(v)))
    elif isinstance(v, str):
        h.update(b"S" + str(len(v)).encode() + b":" + v.encode())
    elif isinstance(v, np.ndarray):
        a = np.ascontiguousarray(v)
        if a.dtype.kind == "f":
            a = a.astype("<f8")
        elif a.dtype.kind in "iub":
            a = a.astype("<i8")
        else:
            a = np.ascontiguousarray([str(x) for x in a.ravel()])
            _feed(h, list(a))
            return
        h.update(b"A" + str(a.shape).encode() + a.tobytes())
    elif hasattr(v, "geom_type") and hasattr(v, "wkb"):
        import shapely  # the precision model changes how GEOS overlays a geometry

        h.update(b"G" + struct.pack("<d", float(shapely.get_precision(v))) + v.wkb)
    elif isinstance(v, dict):
        h.update(b"D" + str(len(v)).encode())
        for k in sorted(v, key=str):
            _feed(h, str(k))
            _feed(h, v[k])
    elif isinstance(v, (list, tuple)):
        h.update(b"L" + str(len(v)).encode())
        for x in v:
            _feed(h, x)
    elif dataclasses.is_dataclass(v):
        h.update(b"C" + type(v).__name__.encode())
        for f in dataclasses.fields(v):
            _feed(h, f.name)
            _feed(h, getattr(v, f.name))
    else:
        _feed(h, repr(v))


def digest(value) -> str:
    h = hashlib.sha256()
    _feed(h, value)
    return h.hexdigest()


def stage(name: str, value) -> None:
    """A stage output (full sha256)."""
    if _LOG is not None:
        _LOG.append(["/".join(_SCOPE + [name]), digest(value)])


def detail(name: str, value) -> None:
    """An intermediate (short hash)."""
    if _LOG is not None:
        _LOG.append(["/".join(_SCOPE + [name]), digest(value)[:16]])


def environment() -> dict:
    import shapely

    return {"machine": platform.machine(), "system": platform.system(),
            "python": platform.python_version(), "numpy": np.__version__,
            "shapely": shapely.__version__,
            "geos": ".".join(str(x) for x in shapely.geos_version)}


def write(path: str | Path, city: str, model_sha256: str, entries: list) -> None:
    data = {"about": "citygen build trace: sha256 of each stage output and of the district "
                     "search intermediates, in build order. Compare two traces with "
                     "`citygen trace diff A B`.",
            "city": city, "produced_on": environment(), "model_sha256": model_sha256,
            "entries": entries}
    head = json.dumps({k: v for k, v in data.items() if k != "entries"}, indent=2,
                      ensure_ascii=False)
    rows = ",\n".join("    " + json.dumps(e) for e in entries)
    text = head[:-2] + ',\n  "entries": [\n' + rows + "\n  ]\n}\n"
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def diff(a: dict, b: dict) -> list[str]:
    """Lines describing where trace `b` first differs from trace `a`."""
    out = []
    ea, eb = a["entries"], b["entries"]
    for i, (x, y) in enumerate(zip(ea, eb)):
        if x != y:
            out.append(f"first difference at entry {i}:")
            out.append(f"  A: {x[0]} {x[1]}")
            out.append(f"  B: {y[0]} {y[1]}")
            if i:
                out.append(f"  last equal: {ea[i - 1][0]}")
            break
    else:
        if len(ea) != len(eb):
            out.append(f"same first {min(len(ea), len(eb))} entries; lengths {len(ea)} and "
                       f"{len(eb)}")
    if a.get("model_sha256") != b.get("model_sha256"):
        out.append(f"model sha256: A {a.get('model_sha256')}  B {b.get('model_sha256')}")
    return out
