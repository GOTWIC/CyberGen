"""Write tests/assetgen/data/golden_props.json (by hand, after a change that moves the props
stage's packs, and say why in the PR):

    .venv/bin/python tests/assetgen/props_goldens.py

The small test city's props, plants and signs (its street stage first, whose median
barriers the props stage reads), as `assetgen.props.build.outputs_digest` measures them.
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]), str(HERE.parent), str(HERE)]

from assetgen.brief import load_model  # noqa: E402
from assetgen.props import build as PB  # noqa: E402
from assetgen.streets import build as SB  # noqa: E402

from agtools import small_build  # noqa: E402


def main():
    base = small_build() / "base"
    m, sha, _ = load_model(base)
    with tempfile.TemporaryDirectory() as d:
        SB.build(m, sha, Path(d), None, workers=4)
        PB.build(m, sha, Path(d), None, workers=4)
        small = PB.outputs_digest(Path(d))
    out = {"about": "sha256 goldens of assetgen's props stage (AG8): the small test city's "
                    "family packs, exact prop and sign tiles and its two Unreal "
                    "contributions (tests/conftest.py SMALL, built by the citygen CLI, its "
                    "street stage run first), as `assetgen.props.build.outputs_digest` "
                    "measures them. Made on the M4 Mac (Mac = x86 deferred to "
                    "docs/determinism_check.md).",
           "small": {"all": small["all"], "files": len(small["files"])}}
    (HERE / "data" / "golden_props.json").write_text(json.dumps(out, indent=2) + "\n",
                                                     encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
