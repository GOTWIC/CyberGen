"""Canonical JSON, hashes and quantization (scope section 10).

Every document assetgen hashes or writes goes through `dumps`: sorted keys, no spaces, UTF-8,
no NaN, and numbers that are either integers or floats already quantized (`mm`, `deg`), so the
text is the same on every machine (Python prints a float as the shortest string that reads
back to the same double, which does not depend on the platform).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def dumps(data: Any) -> str:
    """Canonical JSON text: sorted keys, compact, no NaN or infinity."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(data: Any) -> str:
    """sha256 of the canonical JSON of `data`."""
    return sha256_text(dumps(data))


def mm(v: float) -> int:
    """Meters to integer millimeters (round half to even, the same everywhere)."""
    return int(round(v * 1000.0))


def m(v: float) -> float:
    """Meters quantized to the millimeter, as a float that prints exactly ("12.345")."""
    r = round(v * 1000.0) / 1000.0
    return 0.0 if r == 0.0 else r     # no -0.0


def m2(v: float) -> float:
    """Meters quantized to the centimeter (citygen's grid)."""
    r = round(v * 100.0) / 100.0
    return 0.0 if r == 0.0 else r


def deg(v: float) -> float:
    """Degrees quantized to 0.01."""
    r = round(v * 100.0) / 100.0
    return 0.0 if r == 0.0 else r


def pt(p, ox: float = 0.0, oy: float = 0.0) -> list[float]:
    """A 2D point in a frame with origin (ox, oy), to the millimeter."""
    return [m(p[0] - ox), m(p[1] - oy)]


def pt3(p, ox: float = 0.0, oy: float = 0.0) -> list[float]:
    return [m(p[0] - ox), m(p[1] - oy), m(p[2])]
