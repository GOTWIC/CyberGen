"""Write tests/assetgen/data/golden_water.json (by hand, after a change that moves the water
packs, and say why in the PR):

    .venv/bin/python tests/assetgen/water_goldens.py [--builds DIR]

The small test city's water as `assetgen.water.build.outputs_digest` measures it (every tile
pack, the parts pack and the Unreal contribution, without AG6's textures: `all` hashes them
together), and with --builds Vesper Bay's (DIR/vesper_bay/city_model.json, which must have
citygen's golden sha256; its streets stage is run first, for the bridge piers' foam).
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
from assetgen.water import build as WB  # noqa: E402

from agtools import ROOT, small_build  # noqa: E402

PICK = 6   # tiles of Vesper Bay named in the goldens: the ones with the most triangles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--builds", type=Path)
    args = ap.parse_args()
    base = small_build() / "base"
    with tempfile.TemporaryDirectory() as d:
        m, sha, _ = load_model(base)
        WB.build(m, sha, Path(d), None, workers=4)
        small = WB.outputs_digest(Path(d))
    out = {"about": "sha256 goldens of assetgen's water stage (AG12): the small test city's "
                    "packs (tests/conftest.py SMALL, built by the citygen CLI) as "
                    "`assetgen.water.build.outputs_digest` measures them (every tile pack, "
                    "the parts pack and the Unreal contribution without AG6's textures; "
                    "`all` hashes them together), and Vesper Bay's with the tiles that hold "
                    "the most triangles. Made on the Windows PC; Mac = x86 deferred "
                    "(docs/determinism_check.md).",
           "small": {"all": small["all"]}}
    if args.builds is not None:
        f = args.builds / "vesper_bay" / "city_model.json"
        data = f.read_bytes()
        gold = json.loads((ROOT / "tests" / "data" / "golden_hashes.json").read_text())
        assert C.sha256_bytes(data) == gold["cities"]["vesper_bay"], f"{f}: not the golden model"
        from citygen.model import CityModel
        from assetgen.streets import build as SB
        model = CityModel.model_validate_json(data)
        with tempfile.TemporaryDirectory() as d:
            SB.build(model, C.sha256_bytes(data), Path(d), None, workers=4)
            WB.build(model, C.sha256_bytes(data), Path(d), None, workers=4)
            vb = WB.outputs_digest(Path(d))
            man = json.loads((Path(d) / "water" / "manifest.json").read_text())
        top = sorted(man["tiles"], key=lambda t: (-man["tiles"][t]["triangles"], t))[:PICK]
        out["vesper_bay"] = {"all": vb["all"], "tiles": {t: vb["tiles"][t] for t in top}}
    (HERE / "data" / "golden_water.json").write_text(json.dumps(out, indent=2) + "\n",
                                                     encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
