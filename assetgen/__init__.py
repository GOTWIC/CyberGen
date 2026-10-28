"""assetgen: unique building models, street elements and textures (stage 2 of CyberGen).

AG0 (contract and spike): the asset spec and its era presets, the brief of every building
(what its asset is made from, hashed), a deterministic glTF writer and an exact integer
triangulator, the edge preview, and the spike buildings that measure Unreal's import.
AG1 (building shells): the genome and split grammar (`buildings/`), a closed shell and a far
proxy for every building, `assetgen build` (tile packs, manifest, checks, the Unreal
contribution; unchanged assets kept) and `assetgen preview` (Blender).

Offline and deterministic like citygen: no network call, no LLM SDK. It reads citygen's city
model (and `citygen.dmath`, `citygen.geom`) and never writes back.
"""

__version__ = "0.1.0"
