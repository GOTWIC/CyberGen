"""Write tests/assetgen/data/golden_ground.json (by hand, after a change that moves the
ground stage's outputs, and say why in the PR):

    .venv/bin/python tests/assetgen/ground_goldens.py
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]), str(HERE.parent), str(HERE)]

from assetgen.brief import load_model  # noqa: E402
from assetgen.ground import build as GB  # noqa: E402

from agtools import small_build  # noqa: E402


def main():
    base = small_build() / "base"
    with tempfile.TemporaryDirectory() as d:
        m, sha, _ = load_model(base)
        GB.build(m, sha, Path(d), None, workers=4)
        small = GB.outputs_digest(Path(d))
    out = {"about": "sha256 goldens of assetgen's ground stage (AG13): the small test city's "
                    "ground packs, mask pixels, grass files and Unreal contribution "
                    "(tests/conftest.py SMALL, built by the citygen CLI), as "
                    "`assetgen.ground.build.outputs_digest` measures them (`all` hashes them "
                    "together). Written on the Windows PC; Mac = x86 waits for the deferred "
                    "determinism check.",
           "small_city": {"all": small["all"], "files": len(small["files"])}}
    (HERE / "data" / "golden_ground.json").write_text(json.dumps(out, indent=1) + "\n",
                                                      encoding="utf-8")
    print(out["small_city"])


if __name__ == "__main__":
    main()
