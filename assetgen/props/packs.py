"""glTF packs of the props stage: the variant families (one pack per prop kind with every
style's variants, one per plant species) and the meshes per tile (exact props, signs).

A family pack's nodes sit at the origin, each named by its part kind
(`prop.street_light.sleek.v3`, `plant.oak.v5`); a tile pack's nodes are named by their
mesh's id and sit where their extras say (signs at the origin, made in their slot's frame;
exact props at their tile's middle).
"""

from __future__ import annotations

from .. import __version__
from .. import canon as C
from ..gltf import Gltf
from . import materials as MT
from . import styles as ST
from .shapes import check


def record(mesh) -> dict:
    lo, hi = mesh.bounds_mm()
    if lo[0] is None:
        return {"triangles": 0}
    return {"triangles": mesh.triangles, "slots": sorted(mesh.slots),
            "bounds": [[C.m(v / 1000.0) for v in lo], [C.m(v / 1000.0) for v in hi]],
            "checks": {k: v for k, v in check(mesh.slots).items() if v}}


def pack(meshes: list[tuple[str, object, dict | None]], what: str) -> tuple[bytes, dict]:
    """A glTF pack of (node name, Mesh, translation in mm or None) and a record per node."""
    g = Gltf(generator=f"assetgen {__version__} props {what}")
    slots = set()
    for _, m, _ in meshes:
        slots |= set(m.slots)
    mats = MT.gltf_materials(g, slots)
    info = {}
    for name, m, trans in meshes:
        if not m.triangles:
            continue
        mi = g.mesh(name, m.finish(mats))
        g.node(name, mi, translation=trans, root=True)
        info[name] = record(m)
    return (g.to_glb() if g.nodes else b""), info


def family(kind: str) -> list[tuple[str, object, None]]:
    """Every variant of a prop kind, all styles."""
    from . import variants as V
    out = []
    for st in ST.STYLES:
        for k in range(ST.PROP_VARIANTS[kind]):
            out.append((ST.variant_name(kind, st, k), V.make(kind, st, k), None))
    return out


def species(sp: str) -> list[tuple[str, object, None]]:
    from . import trees as T
    return [(ST.plant_name(sp, k), T.make(sp, k), None) for k in range(ST.PLANT_VARIANTS[sp])]


def family_job(args) -> dict:
    """(what, name) -> the pack's bytes and records (a worker's job)."""
    what, name = args
    meshes = family(name) if what == "prop" else species(name)
    data, info = pack(meshes, f"{what} {name}")
    return {"what": what, "name": name, "glb": data, "meshes": info}
