"""Reading assetgen's own packs back (AG14's fit checks): every node's mesh in world space,
in citygen's frame (x east, y north, z up, meters).

Handles what assetgen's writer (`assetgen/gltf.py`) puts in a pack: node hierarchies with
translation, rotation and scale (or a matrix), KHR_mesh_quantization (integer positions the
node's scale undoes), interleaved or tight buffer views, and EXT_mesh_gpu_instancing.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32,
       5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
# glTF (x, y, z) is citygen (x, -z, y)
G2C = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0]])


@dataclass
class Node:
    """A node with a mesh: its name, its root's name, extras, the world matrix (glTF frame)
    and its primitives [(material name, positions (n, 3) in the mesh's frame, triangles
    (m, 3))]; `instances` (k, 4, 4) for an instanced node (EXT_mesh_gpu_instancing)."""
    name: str
    root: str
    extras: dict
    world: np.ndarray
    prims: list = field(default_factory=list)
    instances: np.ndarray | None = None

    def triangles(self, materials=None) -> np.ndarray:
        """(m, 3, 3) world triangles in citygen's frame (every instance), optionally only
        of the materials named (a set of names, or a predicate)."""
        out = []
        mats = [M_ @ self.world for M_ in self.instances] if self.instances is not None \
            else [self.world]
        for mname, pos, tri in self.prims:
            if materials is not None and not _match(materials, mname):
                continue
            if not len(tri):
                continue
            P = np.c_[pos, np.ones(len(pos))]
            for W in mats:
                Q = (P @ (G2C @ W).T)[:, :3]
                out.append(Q[tri])
        if not out:
            return np.zeros((0, 3, 3))
        return np.concatenate(out)


def _match(materials, name: str) -> bool:
    if callable(materials):
        return materials(name)
    return name in materials


def _quat(q) -> np.ndarray:
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _trs(t, r, s) -> np.ndarray:
    M = np.eye(4)
    M[:3, :3] = _quat(r) @ np.diag(s)
    M[:3, 3] = t
    return M


def _local(n: dict) -> np.ndarray:
    if "matrix" in n:
        return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
    return _trs(n.get("translation", [0.0, 0.0, 0.0]), n.get("rotation", [0, 0, 0, 1]),
                n.get("scale", [1.0, 1.0, 1.0]))


def read(path: Path | str) -> list[Node]:
    """Every node with a mesh in a GLB, world matrices composed from the roots."""
    data = Path(path).read_bytes()
    if len(data) < 20:
        return []
    jl, = struct.unpack_from("<I", data, 12)
    doc = json.loads(data[20:20 + jl].decode("utf-8"))
    off = 20 + jl
    binary = b""
    if off + 8 <= len(data):
        bl, = struct.unpack_from("<I", data, off)
        binary = data[off + 8:off + 8 + bl]

    def acc(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        dt = np.dtype(_CT[a["componentType"]])
        n = _NC[a["type"]]
        stride = v.get("byteStride")
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        if stride and stride != dt.itemsize * n:
            raw = np.frombuffer(binary, dtype=np.uint8, count=stride * a["count"],
                                offset=start).reshape(a["count"], stride)
            arr = raw[:, :dt.itemsize * n].copy().view(dt).reshape(a["count"], n)
        else:
            arr = np.frombuffer(binary, dtype=dt, count=a["count"] * n,
                                offset=start).reshape(a["count"], n)
        arr = arr.astype(np.float64)
        if a.get("normalized") and dt != np.float32:
            arr = arr / float(np.iinfo(dt).max)
        return arr

    nodes = doc.get("nodes", [])
    mats = [m.get("name", "") for m in doc.get("materials", [])]
    meshes: dict[int, list] = {}

    def mesh(i):
        if i not in meshes:
            prims = []
            for p in doc["meshes"][i]["primitives"]:
                if "indices" not in p or "POSITION" not in p["attributes"]:
                    continue
                pos = acc(p["attributes"]["POSITION"])
                tri = acc(p["indices"]).astype(np.int64).reshape(-1, 3)
                prims.append((mats[p["material"]] if mats and "material" in p else "",
                              pos, tri))
            meshes[i] = prims
        return meshes[i]

    children = set()
    for n in nodes:
        children.update(n.get("children", []))
    roots = [i for i in range(len(nodes)) if i not in children]
    out: list[Node] = []
    stack = [(i, np.eye(4), nodes[i].get("name", "")) for i in roots]
    while stack:
        i, parent, root = stack.pop()
        n = nodes[i]
        W = parent @ _local(n)
        if "mesh" in n:
            inst = None
            ext = (n.get("extensions") or {}).get("EXT_mesh_gpu_instancing")
            if ext:
                at = ext["attributes"]
                T = acc(at["TRANSLATION"]) if "TRANSLATION" in at else None
                R = acc(at["ROTATION"]) if "ROTATION" in at else None
                S = acc(at["SCALE"]) if "SCALE" in at else None
                k = len(T if T is not None else R if R is not None else S)
                inst = np.stack([_trs(T[j] if T is not None else (0, 0, 0),
                                      R[j] if R is not None else (0, 0, 0, 1),
                                      S[j] if S is not None else (1, 1, 1))
                                 for j in range(k)]) if k else np.zeros((0, 4, 4))
                # (an instanced node: world = node world times the instance's own)
                inst = np.stack([W @ m for m in inst]) if k else inst
            out.append(Node(n.get("name", ""), root, n.get("extras") or {},
                            W if inst is None else np.eye(4), mesh(n["mesh"]), inst))
        for c in n.get("children", []):
            stack.append((c, W, root))
    out.sort(key=lambda nd: nd.name)
    return out


def local_mesh(path: Path | str) -> dict[str, list]:
    """{node name: [(material, positions in citygen's frame (n, 3), triangles)]} of a pack
    of meshes made to be instanced (parts, variants): each in its node's own frame."""
    out = {}
    for nd in read(path):
        prims = []
        for mname, pos, tri in nd.prims:
            P = np.c_[pos, np.ones(len(pos))] @ (G2C @ nd.world).T
            prims.append((mname, P[:, :3], tri))
        out[nd.name] = prims
    return out
