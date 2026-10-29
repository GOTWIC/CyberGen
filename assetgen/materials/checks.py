"""The texel density check (scope 5.2, section 9: "texel density within bounds", measured
from UVs) and the library budget check.

**Texel density.** For every triangle of the building shells and street pieces whose slot
has a texture set, the texels per meter it gets:

$$\\rho = \\sqrt{\\frac{A_{uv}}{A_{xyz}}}\\, \\frac{n}{t}$$

with $A_{uv}$ its area in UV0, $A_{xyz}$ in space, $n$ the set's pixels and $t$ the meters
it covers. A triangle within reach of the street (a building face less than 12 m over the
building's base that is not a roof, every street piece) needs the spec's
`texel_density_px_m` (512), the others `texel_density_upper_px_m` (256). A triangle meets it
at three quarters of that or more (UV0 runs along a road's center line, so the outer edge
of a curve, a bevel or a cylinder stretches it), and the check passes when at least 99.5 %
of each part's textured area (buildings, streets) meets it; it lists the slots and pieces
below it. The packs are read back (every triangle of every pack; positions and UV0 only).

**Library budget.** Section 11: the shared library at most 2.5 GB cooked (BC7 and BC5 at a
byte per texel, mips 4/3) and 7 GB of source images; a city's signage at most 0.3 GB
cooked.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import catalog as CT

STREET_BAND_M = 12.0
TOLERANCE = 0.75
AREA_SHARE = 0.995
LIB_COOKED = 2.5e9
LIB_SOURCE = 7.0e9
SIGNS_COOKED = 0.3e9
_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32,
       5126: np.float32}
_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_glb(path: Path):
    """Yield (node name, translation, material name, positions (n, 3) in citygen's frame,
    uv0 (n, 2), triangles (m, 3)) for every primitive of a GLB (meshes on nodes)."""
    data = path.read_bytes()
    jl = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + jl])
    bin_off = 20 + jl + 8
    views = doc["bufferViews"]

    def acc(i):
        a = doc["accessors"][i]
        v = views[a["bufferView"]]
        dt = _CT[a["componentType"]]
        k = _N[a["type"]]
        off = bin_off + v.get("byteOffset", 0) + a.get("byteOffset", 0)
        arr = np.frombuffer(data, dtype=dt, count=a["count"] * k, offset=off).reshape(-1, k)
        if a.get("normalized") and dt != np.float32:
            arr = arr.astype(np.float64) / float(np.iinfo(dt).max)
        return arr
    mats = [m.get("name", "") for m in doc.get("materials", [])]
    parent_t: dict[int, tuple] = {}
    for i, n in enumerate(doc.get("nodes", [])):
        t = n.get("translation", [0.0, 0.0, 0.0])
        for c in n.get("children", []):
            parent_t[c] = t
    for i, n in enumerate(doc.get("nodes", [])):
        if "mesh" not in n:
            continue
        t = n.get("translation") or parent_t.get(i, [0.0, 0.0, 0.0])
        for p in doc["meshes"][n["mesh"]]["primitives"]:
            at = p["attributes"]
            if "TEXCOORD_0" not in at or "indices" not in p:
                continue
            pos = acc(at["POSITION"]).astype(np.float64)
            if doc["accessors"][at["POSITION"]]["componentType"] != 5126:
                pass
            # glTF (x, y, z) is citygen (x, z, -y)
            pos = np.stack([pos[:, 0], -pos[:, 2], pos[:, 1]], axis=1)
            uv = acc(at["TEXCOORD_0"]).astype(np.float64)
            tri = acc(p["indices"]).astype(np.int64).reshape(-1, 3)
            yield n.get("name", ""), t, mats[p.get("material", 0)] if mats else "", pos, uv, tri


def _density(pos, uv, tri):
    a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
    cr = np.cross(b - a, c - a)
    area = np.sqrt((cr * cr).sum(axis=1)) / 2.0
    p, q, r = uv[tri[:, 0]], uv[tri[:, 1]], uv[tri[:, 2]]
    auv = np.abs((q[:, 0] - p[:, 0]) * (r[:, 1] - p[:, 1])
                 - (q[:, 1] - p[:, 1]) * (r[:, 0] - p[:, 0])) / 2.0
    ok = area > 1e-6
    rho = np.zeros(len(tri))
    rho[ok] = np.sqrt(auv[ok] / area[ok])
    nz = np.zeros(len(tri))
    nz[ok] = cr[ok, 2] / (2.0 * area[ok])
    zc = (a[:, 2] + b[:, 2] + c[:, 2]) / 3.0
    return rho, area, nz, zc, ok


def texel_density(assets: Path, lib: dict, street_px: int, upper_px: int) -> dict:
    """The check over every pack of a build's assets (tiles/, AG2's parts/ in their own
    frames, and streets/)."""
    per: dict[str, dict] = {}
    parts: dict[str, list[float]] = {}
    tris = 0
    worst: dict[str, tuple] = {}
    for part, folder in (("buildings", "tiles"), ("buildings", "parts"), ("streets", "streets")):
        d = assets / folder
        if not d.is_dir():
            continue
        for f in sorted(d.glob("t*.glb")):
            for node, t, mat, pos, uv, tri in read_glb(f):
                master, s = CT.set_for(mat, None, part)
                if s is None or s not in lib["sets"]:
                    continue
                st = lib["sets"][s]
                px_uv = st["files"]["base"]["size"][0] / st["tile_m"]
                rho, area, nz, zc, ok = _density(pos, uv, tri)
                rho = rho * px_uv
                if part == "buildings":
                    near = (zc < STREET_BAND_M) & (nz < 0.7)
                else:
                    near = np.ones(len(tri), dtype=bool)
                need = np.where(near, street_px, upper_px)
                bad = ok & (rho < need * TOLERANCE)
                tris += int(ok.sum())
                a_ok = float(area[ok].sum())
                a_bad = float(area[bad].sum())
                pa = parts.setdefault(part, [0.0, 0.0])
                pa[0] += a_ok
                pa[1] += a_bad
                rec = per.setdefault(f"{part}.{mat}", {"triangles": 0, "area_m2": 0.0,
                                                       "below_m2": 0.0, "min_px_m": None,
                                                       "set": s})
                rec["triangles"] += int(ok.sum())
                rec["area_m2"] += a_ok
                rec["below_m2"] += a_bad
                if ok.any():
                    v = float(rho[ok].min())
                    rec["min_px_m"] = v if rec["min_px_m"] is None else min(rec["min_px_m"], v)
                if bad.any():
                    i = int(np.flatnonzero(bad)[np.argmin(rho[bad])])
                    w = (float(rho[i]), node, f"{folder}/{f.name}")
                    if f"{part}.{mat}" not in worst or w < worst[f"{part}.{mat}"]:
                        worst[f"{part}.{mat}"] = w
    shares = {p: round(1.0 - b / a, 5) if a > 0 else 1.0 for p, (a, b) in parts.items()}
    for k, r in per.items():
        r["area_m2"] = round(r["area_m2"], 1)
        r["below_m2"] = round(r["below_m2"], 1)
        r["min_px_m"] = None if r["min_px_m"] is None else round(r["min_px_m"], 1)
        if k in worst:
            r["worst"] = {"px_m": round(worst[k][0], 1), "node": worst[k][1],
                          "pack": worst[k][2]}
    flagged = sorted(k for k, r in per.items() if r["area_m2"] > 0
                     and r["below_m2"] / r["area_m2"] > 0.01)
    return {"name": "texel_density", "ok": all(v >= AREA_SHARE for v in shares.values()),
            "triangles": tris, "street_px_m": street_px, "upper_px_m": upper_px,
            "meets_share": shares, "needs_share": AREA_SHARE, "tolerance": TOLERANCE,
            "flagged": flagged, "slots": dict(sorted(per.items()))}


def budget(lib_disk: dict, signs: dict, assets: Path) -> dict:
    texels = 0
    src = 0
    for f in signs["files"].values():
        texels += f["size"][0] * f["size"][1]
        p = assets / f["file"]
        src += p.stat().st_size if p.is_file() else 0
    signs_cooked = int(texels * 4 / 3)
    ok = lib_disk["cooked_bytes"] <= LIB_COOKED and lib_disk["source_bytes"] <= LIB_SOURCE \
        and signs_cooked <= SIGNS_COOKED
    return {"name": "texture_budget", "ok": ok,
            "library_cooked_bytes": lib_disk["cooked_bytes"],
            "library_source_bytes": lib_disk["source_bytes"],
            "signs_cooked_bytes": signs_cooked, "signs_source_bytes": src,
            "limits": {"library_cooked": LIB_COOKED, "library_source": LIB_SOURCE,
                       "signs_cooked": SIGNS_COOKED}}
