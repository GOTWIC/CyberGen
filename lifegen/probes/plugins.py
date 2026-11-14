"""LG0's probe of the engine pieces lifegen builds on (scope section 9): which are
experimental, beta or released in an engine, read from their plugin descriptors
(`IsExperimentalVersion`, `IsBetaVersion`); Mass Entity is an engine module (no descriptor).

    python -m lifegen.probes.plugins [ENGINE_ROOT] [--json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PIECES = {
    "Mass Entity": None,                         # engine module Runtime/MassEntity
    "Mass Gameplay (MassSimulation, MassSpawner, MassRepresentation, MassLOD)": "MassGameplay",
    "Mass AI": "MassAI",
    "Mass Crowd": "MassCrowd",
    "ZoneGraph": "ZoneGraph",
    "ZoneGraph Annotations": "ZoneGraphAnnotations",
    "Smart Objects": "SmartObjects",
    "Gameplay Behaviors (Smart Objects)": "GameplayBehaviorSmartObjects",
    "StateTree": "StateTree",
    "Gameplay StateTree": "GameplayStateTree",
    "Motion Matching (Pose Search)": "PoseSearch",
    "Chooser": "Chooser",
    "Motion Warping": "MotionWarping",
    "IK Rig and retargeting": "IKRig",
    "AnimToTexture": "AnimToTexture",
    "Mutable": "Mutable",
    "Chaos Cloth": "ChaosCloth",
    "Chaos Cloth Asset (panel cloth)": "ChaosClothAsset",
    "Chaos Outfit Asset": "ChaosOutfitAsset",
    "ML Deformer": "MLDeformerFramework",
    "Chaos Vehicles": "ChaosVehiclesPlugin",
    "MetaHuman Creator (MetaHumanCharacter)": "MetaHumanCharacter",
    "MetaHuman Crowd": "MetaHumanCrowd",
    "MetaHuman SDK": "MetaHumanSDK",
    "MetaHuman Generator (toolset)": "MetaHumanGenerator",
}


def status(root: Path) -> list[dict]:
    plugins = {p.stem: p for p in (root / "Engine" / "Plugins").rglob("*.uplugin")}
    out = []
    for name, stem in PIECES.items():
        if stem is None:
            mod = root / "Engine" / "Source" / "Runtime" / "MassEntity"
            out.append({"piece": name, "plugin": None, "state":
                        "engine module" if mod.is_dir() else "missing", "path": str(mod)})
            continue
        p = plugins.get(stem)
        if p is None:
            out.append({"piece": name, "plugin": stem, "state": "missing", "path": None})
            continue
        # (Unreal's descriptors allow trailing commas)
        d = json.loads(re.sub(r",(\s*[\]}])", r"\1", p.read_text(encoding="utf-8-sig")))
        state = "experimental" if d.get("IsExperimentalVersion") else \
            "beta" if d.get("IsBetaVersion") else "released"
        out.append({"piece": name, "plugin": stem, "state": state,
                    "path": str(p.relative_to(root)), "version": d.get("VersionName")})
    return out


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    root = Path(a[0]) if a else Path("C:/Games/UE_5.8")
    rows = status(root)
    if as_json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            print(f"{r['state']:13} {r['piece']}  ({r['path']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
