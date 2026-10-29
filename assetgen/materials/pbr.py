"""Packing a generated surface into the library's maps (scope 5.2), and PNG writing.

Per set, three RGBA or RGB images:
- `<name>_base.png`: base color (sRGB) and height in alpha;
- `<name>_normal.png`: tangent-space normal, OpenGL convention (green up the image; the
  Unreal importer flips the green channel on import, as Unreal reads DirectX normals);
- `<name>_orm.png`: occlusion, roughness, metallic (linear) and the tint mask in alpha.

Image rows run with v of the meshes' UV0 (glTF: row 0 at v = 0, so on a wall, whose v is
the height, row 0 is the bottom): the generators draw with rows going up the wall, and both
engines then show them the right way up.

Every value is quantized as floor(255 x + 0.5) from float32 arithmetic in a fixed order;
`pixels_sha256` hashes the decoded pixels (PNG bytes depend on the zlib build).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from . import noise as N
from .surfaces import Surface

F = np.float32


def u8(a: np.ndarray) -> np.ndarray:
    return np.floor(np.clip(a, 0.0, 1.0) * F(255.0) + F(0.5)).astype(np.uint8)


def occlusion(height: np.ndarray, n: int) -> np.ndarray:
    """Cavity occlusion from height: darker where the surface sits below its surroundings."""
    r = max(1, n // 256)
    near = N.blur(height, r)
    far = N.blur(height, 4 * r)
    cav = np.maximum(near - height, F(0.0)) * F(4.0) + np.maximum(far - height, F(0.0)) * F(1.5)
    return np.clip(F(1.0) - cav, F(0.35), F(1.0)).astype(F)


def normal(height: np.ndarray, bump_mm: float, tile_m: float) -> np.ndarray:
    """OpenGL tangent-space normal (n, n, 3) in 0..1 from height 0..1 spanning bump_mm."""
    n = height.shape[0]
    k = F((bump_mm / 1000.0) / (2.0 * tile_m / n))
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * k
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * k
    # rows go up the surface (+v); OpenGL's green is +v up the image, i.e. -row: +dh/drow
    nx = -dx
    ny = dy
    inv = F(1.0) / np.sqrt(nx * nx + ny * ny + F(1.0))
    return np.stack([nx * inv * F(0.5) + F(0.5), ny * inv * F(0.5) + F(0.5),
                     inv * F(0.5) + F(0.5)], axis=2).astype(F)


def pack(s: Surface, tile_m: float) -> dict[str, np.ndarray]:
    n = s.height.shape[0]
    ao = s.ao if s.ao is not None else occlusion(s.height, n)
    base = np.concatenate([u8(s.color), u8(s.height)[:, :, None]], axis=2)
    nrm = u8(normal(s.height, s.bump, tile_m))
    orm = np.stack([u8(ao), u8(s.rough), u8(s.metal), u8(s.mask)], axis=2)
    return {"base": base, "normal": nrm, "orm": orm}


def pixels_sha256(a: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(f"{a.shape}|{a.dtype}".encode())
    h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def save_png(path: Path, a: np.ndarray) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = {2: "L", 3: "RGB", 4: "RGBA"}[a.shape[2] if a.ndim == 3 else 2]
    img = Image.fromarray(a if a.ndim == 3 else a, mode)
    tmp = path.with_name(path.name + ".tmp")
    img.save(tmp, "PNG", compress_level=6)
    tmp.replace(path)
    return path.stat().st_size


def ref_color(base: np.ndarray, mask: np.ndarray) -> list[float]:
    """The mean sRGB color (0..1) of the tinted pixels (mask over one half), from integer
    sums (exact everywhere): what a tint replaces."""
    m = mask >= 128
    cnt = int(m.sum())
    if cnt == 0:
        m = np.ones(mask.shape, dtype=bool)
        cnt = int(m.sum())
    out = []
    for k in range(3):
        s = int(base[:, :, k][m].astype(np.int64).sum())
        out.append(round(s / cnt / 255.0, 4))
    return out


def mean_u8(a: np.ndarray) -> float:
    return round(int(a.astype(np.int64).sum()) / a.size / 255.0, 4)
