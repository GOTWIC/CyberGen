"""Deterministic glTF 2.0 writer (scope sections 6, 8 and 10).

Meshes arrive as integer millimeters in a building's frame (citygen's: x east, y north, z
up); the writer turns them into glTF's frame (x, z, -y: y up, right-handed) in meters. The
same input gives the same bytes on every machine: attributes written to the buffer in a
fixed order (POSITION, NORMAL, TEXCOORD_0, TEXCOORD_1, COLOR_0), buffer views in that order,
4-byte alignment with zero padding, canonical JSON (sorted keys, no spaces) padded with spaces,
float32 values from correctly rounded conversions, accessor bounds from those float32
values.

Options: `quantized` writes positions as int16 and normals as int8 (KHR_mesh_quantization,
the node's scale and translation undo it); `EXT_mesh_gpu_instancing` nodes carry per
instance translation, rotation and scale.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

from . import canon as C

FLOAT, UBYTE, BYTE, USHORT, SHORT, UINT = 5126, 5121, 5120, 5123, 5122, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
ATTR_ORDER = ("POSITION", "NORMAL", "TEXCOORD_0", "TEXCOORD_1", "COLOR_0")
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def to_gltf_mm(p: np.ndarray) -> np.ndarray:
    """citygen (x, y, z) to glTF (x, z, -y), still integer millimeters."""
    p = np.asarray(p, dtype=np.int64).reshape(-1, 3)
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1)


def to_gltf_vec(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64).reshape(-1, 3)
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1)


def quat_z(yaw_deg: float) -> list[float]:
    """A citygen yaw (about z, counterclockwise from east) as a glTF rotation (about +y)."""
    from citygen import dmath as M
    h = M.radians(yaw_deg) / 2.0
    return [0.0, float(np.float32(M.sin(h))), 0.0, float(np.float32(M.cos(h)))]


@dataclass
class Primitive:
    """One material's triangles: positions in integer mm (citygen frame), the rest per
    vertex."""
    material: int
    positions: np.ndarray            # (n, 3) int64 mm
    indices: np.ndarray              # (m,) int
    normals: np.ndarray | None = None    # (n, 3) float, unit
    uv0: np.ndarray | None = None        # (n, 2) float
    uv1: np.ndarray | None = None        # (n, 2) float
    colors: np.ndarray | None = None     # (n, 4) uint8


@dataclass
class _Mesh:
    name: str
    prims: list[Primitive]
    extras: dict | None = None


@dataclass
class Gltf:
    generator: str = "assetgen"
    quantized: bool = False
    materials: list[dict] = field(default_factory=list)
    meshes: list[_Mesh] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    roots: list[int] = field(default_factory=list)
    extras: dict | None = None
    _mat_index: dict = field(default_factory=dict)
    _instancing: bool = False

    def material(self, name: str, color=(0.8, 0.8, 0.8, 1.0), metallic: float = 0.0,
                 roughness: float = 0.8, extras: dict | None = None) -> int:
        if name in self._mat_index:
            return self._mat_index[name]
        mat = {"name": name, "pbrMetallicRoughness": {
            "baseColorFactor": [_f32(c) for c in color], "metallicFactor": _f32(metallic),
            "roughnessFactor": _f32(roughness)}}
        if extras:
            mat["extras"] = extras
        self.materials.append(mat)
        self._mat_index[name] = len(self.materials) - 1
        return len(self.materials) - 1

    def mesh(self, name: str, prims: list[Primitive], extras: dict | None = None) -> int:
        self.meshes.append(_Mesh(name, [p for p in prims if len(p.indices)], extras))
        return len(self.meshes) - 1

    def node(self, name: str, mesh: int | None = None, translation=None, rotation=None,
             scale=None, children: list[int] | None = None, extras: dict | None = None,
             root: bool = False, instances: dict | None = None) -> int:
        """A node; `translation` in integer mm (citygen frame), `rotation` a glTF quaternion.
        `instances`: {"translation": (k, 3) mm, "yaw_deg": (k,), "scale": (k, 3)} for
        EXT_mesh_gpu_instancing."""
        n: dict = {"name": name}
        if mesh is not None:
            n["mesh"] = mesh
        if translation is not None:
            t = to_gltf_mm(np.array([translation]))[0]
            n["translation"] = [_f32(v / 1000.0) for v in t.tolist()]
        if rotation is not None:
            n["rotation"] = [_f32(v) for v in rotation]
        if scale is not None:
            n["scale"] = [_f32(v) for v in scale]
        if children:
            n["children"] = list(children)
        if extras:
            n["extras"] = extras
        if instances is not None:
            n["_instances"] = instances
            self._instancing = True
        self.nodes.append(n)
        if root:
            self.roots.append(len(self.nodes) - 1)
        return len(self.nodes) - 1

    # -- writing -----------------------------------------------------------------------

    def to_glb(self) -> bytes:
        w = _Writer()
        meshes = []
        quant_nodes: dict[int, tuple] = {}
        for mi, mesh in enumerate(self.meshes):
            prims = []
            qscale = qoff = None
            if self.quantized:
                allp = np.concatenate([to_gltf_mm(p.positions) for p in mesh.prims]) \
                    if mesh.prims else np.zeros((1, 3), dtype=np.int64)
                lo, hi = allp.min(axis=0), allp.max(axis=0)
                qoff = (lo + hi) // 2
                span = int(max((hi - lo).max(), 1))
                step = 1
                while span // step > 65000:
                    step *= 2
                qscale = step
                quant_nodes[mi] = (qoff, qscale)
            for p in mesh.prims:
                prims.append(self._prim(w, p, qoff, qscale))
            m = {"name": mesh.name, "primitives": prims}
            if mesh.extras:
                m["extras"] = mesh.extras
            meshes.append(m)
        nodes = []
        extra_nodes = []
        for ni, n in enumerate(self.nodes):
            n = dict(n)
            inst = n.pop("_instances", None)
            if inst is not None:
                n.setdefault("extensions", {})["EXT_mesh_gpu_instancing"] = {
                    "attributes": self._instances(w, inst)}
            if self.quantized and "mesh" in n:
                # the mesh moves to a child whose transform dequantizes it
                off, step = quant_nodes[n.pop("mesh")]
                child = {"name": n["name"] + ".q", "mesh": self.nodes[ni]["mesh"],
                         "translation": [_f32(v / 1000.0) for v in off.tolist()],
                         "scale": [_f32(step / 1000.0)] * 3}
                if inst is not None:
                    child["extensions"] = n.pop("extensions")
                extra_nodes.append((ni, child))
            nodes.append(n)
        for ni, child in extra_nodes:
            nodes.append(child)
            nodes[ni].setdefault("children", []).append(len(nodes) - 1)
        doc = {"asset": {"version": "2.0", "generator": self.generator},
               "scene": 0, "scenes": [{"nodes": list(self.roots)}],
               "nodes": nodes, "meshes": meshes}
        if self.materials:
            doc["materials"] = self.materials
        used = []
        if self.quantized:
            used.append("KHR_mesh_quantization")
        if self._instancing:
            used.append("EXT_mesh_gpu_instancing")
        if used:
            doc["extensionsUsed"] = used
        if self.quantized:
            doc["extensionsRequired"] = ["KHR_mesh_quantization"]
        if self.extras:
            doc["extras"] = self.extras
        doc.update(w.json_parts())
        js = C.dumps(doc).encode("utf-8")
        js += b" " * (-len(js) % 4)
        binary = bytes(w.buf)
        out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary))
        out += struct.pack("<II", len(js), 0x4E4F534A) + js
        out += struct.pack("<II", len(binary), 0x004E4942) + binary
        return out

    def _prim(self, w: "_Writer", p: Primitive, qoff, qscale) -> dict:
        attrs = {}
        pos = to_gltf_mm(p.positions)
        if qscale is None:
            f = (pos.astype(np.float64) / 1000.0).astype(np.float32)
            attrs["POSITION"] = w.accessor(f, FLOAT, "VEC3", bounds=True)
        else:
            q = ((pos - qoff + qscale // 2) // qscale).astype(np.int16)   # nearest step
            attrs["POSITION"] = w.accessor(q, SHORT, "VEC3", bounds=True)
        if p.normals is not None:
            n = to_gltf_vec(p.normals)
            if qscale is None:
                attrs["NORMAL"] = w.accessor(n.astype(np.float32), FLOAT, "VEC3")
            else:
                qn = np.clip(np.rint(n * 127.0), -127, 127).astype(np.int8)
                attrs["NORMAL"] = w.accessor(qn, BYTE, "VEC3", normalized=True)
        for key, arr in (("TEXCOORD_0", p.uv0), ("TEXCOORD_1", p.uv1)):
            if arr is not None:
                attrs[key] = w.accessor(np.asarray(arr, dtype=np.float64).astype(np.float32),
                                        FLOAT, "VEC2")
        if p.colors is not None:
            attrs["COLOR_0"] = w.accessor(np.asarray(p.colors, dtype=np.uint8), UBYTE,
                                          "VEC4", normalized=True)
        n_v = len(p.positions)
        idx = np.asarray(p.indices).astype(np.uint16 if n_v < 65536 else np.uint32)
        return {"attributes": {k: attrs[k] for k in ATTR_ORDER if k in attrs},
                "indices": w.accessor(idx, USHORT if idx.dtype == np.uint16 else UINT,
                                      "SCALAR", target=ELEMENT_ARRAY_BUFFER),
                "material": p.material, "mode": 4}

    def _instances(self, w: "_Writer", inst: dict) -> dict:
        t = to_gltf_mm(np.asarray(inst["translation"]))
        out = {"TRANSLATION": w.accessor((t.astype(np.float64) / 1000.0).astype(np.float32),
                                         FLOAT, "VEC3", target=None)}
        if "yaw_deg" in inst:
            q = np.array([quat_z(a) for a in inst["yaw_deg"]], dtype=np.float32)
            out["ROTATION"] = w.accessor(q, FLOAT, "VEC4", target=None)
        if "scale" in inst:
            s = np.asarray(inst["scale"], dtype=np.float64).reshape(-1, 3)
            s = np.stack([s[:, 0], s[:, 2], s[:, 1]], axis=1).astype(np.float32)
            out["SCALE"] = w.accessor(s, FLOAT, "VEC3", target=None)
        return out


def _f32(v: float) -> float:
    return float(np.float32(v))


class _Writer:
    def __init__(self):
        self.buf = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def accessor(self, arr: np.ndarray, ctype: int, atype: str, bounds: bool = False,
                 normalized: bool = False, target: int | None = ARRAY_BUFFER) -> int:
        arr = np.ascontiguousarray(arr)
        data = arr.astype(arr.dtype.newbyteorder("<"), copy=False).tobytes()
        self.buf += b"\0" * (-len(self.buf) % 4)
        view = {"buffer": 0, "byteOffset": len(self.buf), "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        ncomp = NCOMP[atype]
        if target == ARRAY_BUFFER and (arr.itemsize * ncomp) % 4:
            # vertex attribute strides must be multiples of 4: pad each element
            per = arr.reshape(len(arr), -1)
            pad = (-per.shape[1] * arr.itemsize) % 4 // arr.itemsize
            per = np.concatenate([per, np.zeros((len(per), pad), dtype=arr.dtype)], axis=1)
            data = per.tobytes()
            view["byteLength"] = len(data)
            view["byteStride"] = per.shape[1] * arr.itemsize
        self.buf += data
        self.views.append(view)
        acc = {"bufferView": len(self.views) - 1, "componentType": ctype,
               "count": int(len(arr)), "type": atype}
        if normalized:
            acc["normalized"] = True
        if bounds:
            a = arr.reshape(len(arr), ncomp)
            acc["min"] = [_num(v) for v in a.min(axis=0).tolist()]
            acc["max"] = [_num(v) for v in a.max(axis=0).tolist()]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def json_parts(self) -> dict:
        self.buf += b"\0" * (-len(self.buf) % 4)
        return {"buffers": [{"byteLength": len(self.buf)}], "bufferViews": self.views,
                "accessors": self.accessors}


def _num(v):
    return int(v) if isinstance(v, int) else float(np.float32(v))
