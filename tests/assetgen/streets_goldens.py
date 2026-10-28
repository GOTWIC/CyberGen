"""Write tests/assetgen/data/golden_streets.json (by hand, after a change that moves the
street packs, and say why in the PR):

    .venv/bin/python tests/assetgen/streets_goldens.py [--builds DIR]

With --builds, Vesper Bay's model is read from DIR/vesper_bay/city_model.json (it must
have citygen's golden sha256) instead of being built.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]), str(HERE.parent), str(HERE)]

from assetgen import canon as C  # noqa: E402
from assetgen.brief import load_model  # noqa: E402
from assetgen.streets import build as SB  # noqa: E402

from agtools import CITIES, ROOT, built_sample, small_build  # noqa: E402

PICK = 6   # tiles of Vesper Bay named in the goldens: the ones with the most triangles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--builds", type=Path)
    args = ap.parse_args()
    from assetgen import spec as S
    from assetgen.materials.build import library_for
    lib = library_for(S.dump(S.fill(S.AssetSpec())))     # AG6: the contribution's textures
    base = small_build() / "base"
    with tempfile.TemporaryDirectory() as d:
        m, sha, _ = load_model(base)
        SB.build(m, sha, Path(d), None, workers=4, lib=lib)
        small = SB.outputs_digest(Path(d))
    if args.builds is not None:
        f = args.builds / "vesper_bay" / "city_model.json"
        data = f.read_bytes()
        gold = json.loads((ROOT / "tests" / "data" / "golden_hashes.json").read_text())
        assert C.sha256_bytes(data) == gold["cities"]["vesper_bay"], f"{f}: not the golden model"
        from citygen.model import CityModel
        model = CityModel.model_validate_json(data)
    else:
        path = next(p for p in CITIES if p.parent.name == "vesper_bay")
        built, _, data = built_sample(path)
        model = built.model
    with tempfile.TemporaryDirectory() as d:
        SB.build(model, C.sha256_bytes(data), Path(d), None, workers=4, lib=lib)
        vb = SB.outputs_digest(Path(d))
        man = json.loads((Path(d) / "streets" / "manifest.json").read_text())
    top = sorted(man["tiles"], key=lambda t: (-man["tiles"][t]["triangles"], t))[:PICK]
    out = {"about": "sha256 goldens of assetgen's street stage (AG7): the small test city's "
                    "packs (tests/conftest.py SMALL, built by the citygen CLI) and Vesper "
                    "Bay's, as `assetgen.streets.build.outputs_digest` measures them (every "
                    "tile pack, the parts pack and the Unreal contribution; `all` hashes "
                    "them together), with the tiles of Vesper Bay that hold the most "
                    "triangles, the contribution with AG6's textures (the 512 px/m "
                    "library). Made on the M4 Mac; x86 deferred (docs/determinism_check.md).",
           "testport": {"all": small["all"]},
           "vesper_bay": {"all": vb["all"], "tiles": {t: vb["tiles"][t] for t in sorted(top)}}}
    (HERE / "data" / "golden_streets.json").write_text(json.dumps(out, indent=2) + "\n",
                                                       encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
