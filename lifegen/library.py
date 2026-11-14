"""lifegen's population library (LG1, scope 4.2 and 13): who the people are.

The library is built once per project and shared by its cities (scope section 2). Its spec
is here, deterministic and offline (blake2b draws from the character's index): a set of
characters, each a MetaHuman made by script in the user's project from Epic's presets (the
engine's optional MetaHuman content: decision 2, never the repo), its face a blend of two
presets' face models, its body from a height and a build, its skin tone; the preset's own
hair, eyebrows and plain wardrobe (decision 5: MetaHuman's own outfit; LG2 dresses them).
The animation is Epic's Game Animation Sample (Swagnik, 2026-11-14: Unreal's own animations
for now), copied into the project from the user's sample by a step he runs, retargeted onto
the MetaHuman body by script.

Each person in a city is a character of the library drawn by the person's seed, with a
height scale, a tint of the outfit, a gait (one of the walk clips) and a pace of their own
(`person`): the plan writes the seeds and the draws (`people_rows`), the runtime places them.

The library's hash (`library_hash`) covers this spec, the editor scripts that build it and
the engine version: an unchanged library is not built again (`citygen/unreal_people.py`
keeps the built assets in a cache outside the repo, `~/.cache/cybergen/people/<hash>`, as
AG6's texture library is kept).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

LIB_VERSION = "lg1.1"
ROOT = Path(__file__).resolve().parent.parent

# The engine's MetaHuman presets (MetaHumanCharacter's optional content, /MetaHumanCharacter/
# Optional/Presets): a name and the body it has (f, m): faces are blended within a body.
PRESETS = (
    ("Ada", "f"), ("Aera", "f"), ("Aoi", "f"), ("Asha", "f"), ("Bo", "m"), ("Bruce", "m"),
    ("Cameron", "m"), ("Celeste", "f"), ("Dominic", "m"), ("Etta", "f"), ("Grace", "f"),
    ("Isaiah", "m"), ("Jelena", "f"), ("Jorge", "m"), ("Kelvin", "m"), ("Lani", "f"),
    ("Lorenzo", "m"), ("Mateo", "m"), ("Mikel", "m"), ("Omari", "m"), ("Orlando", "m"),
    ("Sook-ja", "f"), ("Sunita", "f"), ("Trey", "m"), ("Tuya", "f"), ("Victor", "m"),
    ("Vivian", "f"), ("Walter", "m"), ("Zuri", "f"),
)
PRESET_PATH = "/MetaHumanCharacter/Optional/Presets"

# how many characters the library makes (each rigged by Epic's cloud and assembled in the
# project; the presets' hair and wardrobe go round in turn)
CHARACTERS = 24
# height (cm) by body: mean and spread, clamped to the creator's range
HEIGHT = {"f": (163.0, 7.0), "m": (176.0, 7.5)}
HEIGHT_RANGE = (148.0, 198.0)
# how far a face moves from its first preset toward its second
FACE_BLEND = (0.15, 0.45)
# the build: chest, waist and hips scaled by (1 + share * b), b drawn in [-1, 1]
BUILD = {"chest": 0.08, "waist": 0.14, "hips": 0.08}
# skin tone on the creator's picker (u light to dark, v undertone)
SKIN_U = (0.04, 0.96)
SKIN_V = (0.25, 0.75)
# the assembly: the creator's Optimized build at this quality (fewer LODs and bones than
# Cinematic; the crowd needs no facial animation past a few meters)
BUILD_PIPELINE = ("OPTIMIZED", "MEDIUM")

# Epic's Game Animation Sample, the user's (decision 4; Unreal's own animations only for now,
# Swagnik 2026-11-14): the clips the people use, by their path in the sample, with the speed
# (m/s) each walks at its own rate, measured from its root motion by the build
GAS_ROOT = "/Game/Characters/UEFN_Mannequin"
CLIPS = {
    "walk_neutral": f"{GAS_ROOT}/Animations/Walk/M_Neutral_Walk_Loop_F",
    "walk_relaxed": f"{GAS_ROOT}/Animations/Walk/M_Relaxed_Walk_Loop_F",
    "idle_neutral": f"{GAS_ROOT}/Animations/Idle/M_Neutral_Stand_Idle_Loop",
    "idle_relaxed": f"{GAS_ROOT}/Animations/Idle/M_Relaxed_Stand_Idle_Loop",
}
WALKS = ("walk_neutral", "walk_relaxed")
GAS_MESH = f"{GAS_ROOT}/Meshes/SKM_UEFN_Mannequin"
GAS_SKELETON = f"{GAS_ROOT}/Meshes/SK_UEFN_Mannequin"
GAS_IK_RIG = f"{GAS_ROOT}/Rigs/IK_UEFN_Mannequin"

# where the library lives in a project
CONTENT = "/Game/CityGen/People"

# the far stand-ins (scope 6.1): beyond the near people (skeletal, animated) each person is
# its character's walk baked into textures (AnimToTexture, bone mode, `FAR_LOD` of its
# assembled body) and past `IMPOSTOR_M` a card showing it from its side and pace
# (`IMPOSTOR_VIEWS` directions round it, `IMPOSTOR_FRAMES` frames of the walk)
FAR_LOD = 3
FAR_FPS = 15.0
IMPOSTOR_VIEWS = 8
IMPOSTOR_FRAMES = 8
IMPOSTOR_CELL = (128, 256)

# the runtime's tiers (m from the view) and how many people each may draw: near people as
# skeletal meshes with their clips, mid as their baked walk, far as cards; the counts are
# what held 20 ms p95 at native 2560 x 1440 on the PC (docs/progress/LG1/README.md)
TIERS = {"near_m": 30.0, "near_max": 160, "mid_m": 90.0, "far_m": 300.0}

# per person (`person`): the height scale round the character's own, the outfit's tint, the
# walk's pace (m/s)
PERSON_SCALE = (0.96, 1.04)
PACE = (1.15, 1.55)


def _u(*parts) -> float:
    """A uniform draw in [0, 1) from the parts (blake2b, as the plan's)."""
    h = hashlib.blake2b(".".join(str(p) for p in parts).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big") / 2.0 ** 64


def _r(v: float, k: int = 4) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def _normal(*parts) -> float:
    """A standard normal draw (Box-Muller on two blake2b uniforms)."""
    a = max(1e-12, _u(*parts, "a"))
    b = _u(*parts, "b")
    return math.sqrt(-2.0 * math.log(a)) * math.cos(2.0 * math.pi * b)


def character(k: int) -> dict:
    """The library's k-th character: its presets, face blend, height, build and skin."""
    name, body = PRESETS[k % len(PRESETS)]
    same = [p for p, b in PRESETS if b == body and p != name]
    other = same[int(_u("lg1.face", k) * len(same))]
    blend = FACE_BLEND[0] + (FACE_BLEND[1] - FACE_BLEND[0]) * _u("lg1.blend", k)
    mu, sd = HEIGHT[body]
    height = min(HEIGHT_RANGE[1], max(HEIGHT_RANGE[0], mu + sd * _normal("lg1.height", k)))
    build = {m: _r(s * (2.0 * _u("lg1.build", m, k) - 1.0)) for m, s in sorted(BUILD.items())}
    return {"id": f"p{k:02d}", "index": k, "preset": name, "body": body, "face_with": other,
            "face_blend": _r(blend), "height_cm": _r(height, 1), "build": build,
            "skin": [_r(SKIN_U[0] + (SKIN_U[1] - SKIN_U[0]) * _u("lg1.skin.u", k)),
                     _r(SKIN_V[0] + (SKIN_V[1] - SKIN_V[0]) * _u("lg1.skin.v", k))]}


def characters(n: int = CHARACTERS) -> list[dict]:
    return [character(k) for k in range(n)]


def spec(n: int = CHARACTERS) -> dict:
    """The library's spec, everything the build depends on but the code."""
    return {"version": LIB_VERSION, "characters": characters(n), "presets": PRESET_PATH,
            "pipeline": list(BUILD_PIPELINE), "clips": dict(sorted(CLIPS.items())),
            "walks": list(WALKS), "gas": {"mesh": GAS_MESH, "skeleton": GAS_SKELETON,
                                          "ik_rig": GAS_IK_RIG},
            "content": CONTENT, "far": {"lod": FAR_LOD, "fps": FAR_FPS},
            "impostor": {"views": IMPOSTOR_VIEWS, "frames": IMPOSTOR_FRAMES,
                         "cell": list(IMPOSTOR_CELL)}}


CODE_FILES = ("lifegen/library.py", "citygen/ue/people_library.py", "citygen/ue/people_gas.py")


def library_hash(n: int = CHARACTERS, engine: str = "") -> str:
    """The hash of the library: its spec, the code that builds it, the engine's version."""
    h = hashlib.sha256()
    h.update(json.dumps(spec(n), sort_keys=True, separators=(",", ":")).encode("utf-8"))
    for f in CODE_FILES:
        p = ROOT / f
        h.update(f.encode("utf-8"))
        h.update(p.read_bytes() if p.is_file() else b"")
    h.update(engine.encode("utf-8"))
    return h.hexdigest()[:16]


def person(seed_parts: tuple, n: int, style: dict | None = None,
           palette: list[str] | None = None) -> dict:
    """A person drawn from their seed: a character of the library (`n` of them), a height
    scale, a gait (one of `WALKS`), a pace (m/s), the outfit's tint (a color of their
    district's style, `palette`, sRGB) and the seed itself (32 bits, for the runtime's own
    draws: the side of the walkway they keep to, where they start)."""
    seed = int.from_bytes(hashlib.blake2b(".".join(str(p) for p in seed_parts)
                                          .encode("utf-8"), digest_size=4).digest(), "big")
    out = {"seed": seed, "character": int(_u(*seed_parts, "char") * n),
           "scale": _r(PERSON_SCALE[0] + (PERSON_SCALE[1] - PERSON_SCALE[0])
                       * _u(*seed_parts, "scale")),
           "gait": int(_u(*seed_parts, "gait") * len(WALKS)),
           "pace": _r(PACE[0] + (PACE[1] - PACE[0]) * _u(*seed_parts, "pace"), 3)}
    if palette:
        out["tint"] = int(_u(*seed_parts, "tint") * len(palette))
    return out
