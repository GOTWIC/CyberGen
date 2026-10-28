"""The glTF writer and the mesh builder: a valid GLB (header, chunks, accessors, bounds,
alignment), glTF's frame, the extensions, the same bytes every time; the spike buildings."""

import json
import struct

import numpy as np

from assetgen import gltf as G
from assetgen import spike as SP
from assetgen.mesh import MeshBuilder, wall_frame

from agtools import golden


def parse_glb(data: bytes):
    magic, ver, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and ver == 2 and length == len(data)
    jlen, jtype = struct.unpack_from("<II", data, 12)
    assert jtype == 0x4E4F534A and jlen % 4 == 0
    doc = json.loads(data[20:20 + jlen])
    blen, btype = struct.unpack_from("<II", data, 20 + jlen)
    assert btype == 0x004E4942 and blen % 4 == 0
    return doc, data[28 + jlen:28 + jlen + blen]


def read_acc(doc, binary, i):
    acc = doc["accessors"][i]
    view = doc["bufferViews"][acc["bufferView"]]
    dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8,
          5122: np.int16, 5120: np.int8}[acc["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    item = np.dtype(dt).itemsize
    stride = view.get("byteStride", item * n)
    raw = np.frombuffer(binary, dtype=np.uint8, count=view["byteLength"],
                        offset=view["byteOffset"])
    rows = raw[:acc["count"] * stride].reshape(acc["count"], stride)[:, :item * n]
    return np.frombuffer(rows.tobytes(), dtype=dt).reshape(acc["count"], n)


def small_scene(quantized=False, inst=False) -> bytes:
    g = G.Gltf(quantized=quantized)
    m = g.material("concrete", (0.5, 0.5, 0.5, 1.0))
    mb = MeshBuilder()
    fr = wall_frame((0, 0), (10000, 0), 0)
    mb.face("concrete", fr, [(0, 0), (10000, 0), (10000, 3000), (0, 3000)],
            [[(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]])
    mb.box("concrete", 0, 1000, 0, 2000, 3000, 4000)
    mesh = g.mesh("wall", mb.primitives({"concrete": m}))
    kw = {"instances": {"translation": [(0, 0, 0), (5000, 0, 0)], "yaw_deg": [0.0, 90.0]}} \
        if inst else {}
    g.node("b.bld", mesh=mesh, root=True, extras={"cg": {"key": "b.bld"}}, **kw)
    return g.to_glb()


def test_glb_structure_and_frame():
    data = small_scene()
    doc, binary = parse_glb(data)
    assert doc["asset"]["version"] == "2.0"
    prim = doc["meshes"][0]["primitives"][0]
    # the binary layout is in a fixed attribute order (the JSON keys are sorted)
    order = ["POSITION", "NORMAL", "TEXCOORD_0", "TEXCOORD_1", "COLOR_0"]
    assert [prim["attributes"][k] for k in order] == sorted(prim["attributes"].values())
    pos = read_acc(doc, binary, prim["attributes"]["POSITION"])
    acc = doc["accessors"][prim["attributes"]["POSITION"]]
    assert acc["min"] == pos.min(axis=0).tolist() and acc["max"] == pos.max(axis=0).tolist()
    # citygen z up -> glTF y up; citygen y north -> glTF -z
    assert pos[:, 1].max() == np.float32(4.0)
    assert pos[:, 2].min() == np.float32(-3.0) and pos[:, 2].max() == np.float32(0.0)
    nrm = read_acc(doc, binary, prim["attributes"]["NORMAL"])
    # the wall faces south (right of west -> east): glTF +z
    assert np.allclose(nrm[0], [0.0, 0.0, 1.0])
    idx = read_acc(doc, binary, prim["indices"])
    assert idx.max() < len(pos) and len(idx) % 3 == 0
    for v in doc["bufferViews"]:
        assert v["byteOffset"] % 4 == 0
    assert doc["nodes"][0]["extras"] == {"cg": {"key": "b.bld"}}


def test_same_bytes_twice():
    assert small_scene() == small_scene()
    assert small_scene(True, True) == small_scene(True, True)


def test_quantized_positions_round_trip():
    doc, binary = parse_glb(small_scene(quantized=True))
    assert doc["extensionsRequired"] == ["KHR_mesh_quantization"]
    child = doc["nodes"][doc["nodes"][0]["children"][0]]
    prim = doc["meshes"][child["mesh"]]["primitives"][0]
    q = read_acc(doc, binary, prim["attributes"]["POSITION"]).astype(np.float64)
    pos = q * child["scale"][0] + np.array(child["translation"])
    ref_doc, ref_bin = parse_glb(small_scene())
    ref = read_acc(ref_doc, ref_bin,
                   ref_doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"])
    assert np.abs(pos - ref).max() < 0.0011


def test_gpu_instancing_extension():
    doc, binary = parse_glb(small_scene(inst=True))
    assert "EXT_mesh_gpu_instancing" in doc["extensionsUsed"]
    attrs = doc["nodes"][0]["extensions"]["EXT_mesh_gpu_instancing"]["attributes"]
    t = read_acc(doc, binary, attrs["TRANSLATION"])
    r = read_acc(doc, binary, attrs["ROTATION"])
    assert t.tolist() == [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]]
    assert np.allclose(r[1], [0.0, np.sqrt(0.5), 0.0, np.sqrt(0.5)])


def test_spike_small_buildings_golden(tmp_path):
    """The shopfront row and the shanty stack: the same bytes on every machine (the tower,
    a million triangles, is in the spike report)."""
    rep = SP.write_spike(tmp_path, quantized=True, which=("shopfront_row", "shanty_stack"))
    g = golden()["spike"]
    for name in ("shopfront_row", "shanty_stack"):
        r = rep["buildings"][name]
        assert r["sha256"] == g[name], name
        assert r["quant_sha256"] == g[name + "_quant"], name
        assert r["gpuinst_sha256"] == g[name + "_gpuinst"], name
        doc, _ = parse_glb((tmp_path / f"{name}.glb").read_bytes())
        assert doc["nodes"][-1]["name"] == f"spike.{name}.bld"
    con = json.loads((tmp_path / "unreal_contribution.json").read_text())
    assert con["stage"] == "assetgen" and len(con["entries"]) == 2
    for e in con["entries"]:
        assert e["collision"]["simple"] and len(e["cpd"]) == 8
        assert all(p["count"] == len(p["xforms"]) for p in e["parts"])
