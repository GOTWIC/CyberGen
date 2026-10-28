"""Street pieces: one per citygen id, each made from its own inputs.

A piece is gathered from the city (`Ctx`) into `inputs`, plain canonical data holding
everything its generator reads (the entity, its neighbors, the district style, the ground
under it), and then made from `inputs` alone. The sha256 of the inputs and the generator's
version is the piece's hash, as a brief's is a building's (scope 4.4): same hash, same
mesh bytes, so a tile whose pieces all keep their hashes is not made again.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .. import canon as C
from .kit import Mesh


@dataclass
class Piece:
    id: str
    kind: str              # street.road, street.junction, ...
    maker: str
    tile: str
    replaces: list[str]
    inputs: dict
    covers: list[str] = field(default_factory=list)   # model ids it stands for besides id

    def digest(self) -> str:
        return C.digest({"maker": self.maker, "v": VERSIONS.get(self.maker, 1),
                         "inputs": self.inputs})


@dataclass
class Out:
    mesh: Mesh | None = None
    nanite: bool = True
    # extra meshes: {"suffix": ".glass", "lods": [Mesh, ...], "nanite": False}
    extra: list = field(default_factory=list)
    # instanced parts: {"kind": "part.container.c0", "xforms": [[x, y, z, yaw_deg], ...]}
    # in the piece's frame (meters)
    parts: list = field(default_factory=list)
    notes: dict = field(default_factory=dict)
    empty: str | None = None      # why a piece has no mesh (covered by another piece)


MAKERS: dict = {}
VERSIONS: dict[str, int] = {}


def maker(name: str, version: int = 1):
    def wrap(fn):
        MAKERS[name] = fn
        VERSIONS[name] = version
        return fn
    return wrap


def rnd(*parts) -> float:
    """A uniform number in [0, 1) from a blake2b hash of ids and purposes (as `props._u`)."""
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"),
                        digest_size=8).digest()
    return int.from_bytes(h, "big") / 18446744073709551616.0


def pts2(line) -> list[list[float]]:
    return [[float(p[0]), float(p[1])] for p in line]
