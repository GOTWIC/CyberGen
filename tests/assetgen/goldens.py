"""Write tests/assetgen/data/golden_hashes.json (run by hand after a change that moves the
briefs, the shells, the spike or the triangulator, and say why in the PR):

    .venv/bin/python tests/assetgen/goldens.py [--builds DIR]

With --builds, the sample models are read from DIR/<city>/city_model.json (each must have
citygen's golden sha256) instead of being built. With --sections ag1 ag6, only those
sections are made again (the rest kept from the file).
"""

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]), str(HERE.parent), str(HERE)]

from assetgen import brief as B  # noqa: E402
from assetgen import canon as C  # noqa: E402
from assetgen import spike as SP  # noqa: E402
from assetgen.triangulate import triangulate  # noqa: E402
from citygen import dmath as M  # noqa: E402

from assetgen import build as BD  # noqa: E402

from agtools import CITIES, GOLDEN, ROOT, built_sample, small_assets, small_build  # noqa: E402

# AG1: the shells of these Vesper Bay buildings as GLB bytes (one per kind, chosen as AG0's
# brief goldens are, plus a curtain-wall tower, a shanty stack and a parking structure)
AG1_KINDS = ("building.landmark.", "building.podium_tower", "building.shopfront_row",
             "building.shanty_stack", "building.megabuilding", "building.villa",
             "building.warehouse", "building.parking_structure", "building.tower")

KINDS = ("building.landmark.", "building.podium_tower", "building.shopfront_row",
         "building.shanty_stack", "building.megabuilding", "building.villa")


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def tri_golden() -> str:
    holes = [rect(x, y, x + 600, y + 800) for x in range(300, 9300, 1000) for y in (300, 1500)]
    t1 = triangulate(rect(0, 0, 9300, 2700), holes)
    rnd = random.Random(7)
    n = 40
    star = [(int(rnd.randint(500, 1000) * M.cos(2 * M.PI * i / n)),
             int(rnd.randint(500, 1000) * M.sin(2 * M.PI * i / n))) for i in range(n)]
    t2 = triangulate(star, [rect(-50, -50, 50, 50)])
    return C.digest([t1, t2])


def model_of(path: Path, builds: Path | None):
    gold = json.loads((ROOT / "tests" / "data" / "golden_hashes.json").read_text())["cities"]
    name = path.parent.name
    if builds is not None:
        f = builds / name / "city_model.json"
        data = f.read_bytes()
        assert C.sha256_bytes(data) == gold[name], f"{f}: not citygen's golden model"
        from citygen.model import CityModel
        return CityModel.model_validate_json(data), data
    built, _, data = built_sample(path)
    return built.model, data


# AG6: decoded pixels of these maps of a 32 px/m library (test_ag_materials.small_library)
AG6_MAPS = (("sets", "brick_heritage", "base"), ("sets", "panel_brutalist", "orm"),
            ("sets", "asphalt_street", "normal"), ("atlases", "interiors", "night"),
            ("atlases", "decals", "base"), ("atlases", "road", "base"),
            ("atlases", "trim_heritage", "base"))
AG6_FILES = ("materials.json", "signs.json", "unreal_contribution.materials.json",
             "unreal_contribution.buildings.json", "unreal_contribution.streets.json")


def ag1_section() -> dict:
    base = small_assets()
    a = base / "assets"                    # the building packs (streets, props: their own)
    tree = {str(p.relative_to(a)): C.sha256_bytes(p.read_bytes())
            for p in sorted(a.rglob("*")) if p.is_file() and
            ((p.suffix == ".glb" and p.parent.parent == a and
              p.parent.name in ("tiles", "proxies")) or
             (p.parent == a and p.name in BD.DELIVERED))}
    return {"testport_manifest": C.sha256_bytes((a / "manifest.json").read_bytes()),
            "testport_files": C.digest(tree)}


def ag6_section() -> dict:
    from test_ag_materials import small_library
    lib = small_library()
    a = small_assets() / "assets"
    return {"library": {f"{g}.{k}.{m}": lib[g][k]["files"][m]["pixels_sha256"]
                        for g, k, m in AG6_MAPS},
            "testport_materials": C.digest({f: C.sha256_bytes((a / f).read_bytes())
                                            for f in AG6_FILES})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--builds", type=Path)
    ap.add_argument("--sections", nargs="*", help="only these sections (ag1, ag6)")
    args = ap.parse_args()
    if args.sections:
        out = json.loads(GOLDEN.read_text(encoding="utf-8"))
        if "ag1" in args.sections:
            out["ag1"].update(ag1_section())
        if "ag6" in args.sections:
            out["ag6"] = ag6_section()
        GOLDEN.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {GOLDEN} ({', '.join(args.sections)})")
        return
    out = {"about": "sha256 goldens of assetgen (AG0): the small test city's briefs.json "
                    "(tests/conftest.py SMALL built by the citygen CLI), brief hashes of a few "
                    "Vesper Bay buildings, the five samples' briefs.json, the two small spike "
                    "buildings' glTF files and a triangulation; (AG1, under ag1) the small "
                    "city's asset manifest and the digest of its asset files, and the shells "
                    "of a few Vesper Bay buildings as GLB. Made on the M4 Mac and confirmed "
                    "on x86_64 Linux (docker image citygen-x86).",
           "testport_briefs": C.sha256_bytes(
               (small_build() / "base" / "assets" / "briefs.json").read_bytes()),
           "triangulate": tri_golden(), "buildings": {}, "samples": {}, "spike": {}}
    out["ag1"] = {**ag1_section(), "buildings": {}}
    out["ag6"] = ag6_section()
    for path in CITIES:
        model, data = model_of(path, args.builds)
        res = B.build_briefs(model)
        with tempfile.TemporaryDirectory() as d:
            f = B.write_briefs(d, model, C.sha256_bytes(data), res)
            out["samples"][path.parent.name] = C.sha256_bytes(f.read_bytes())
        if path.parent.name == "vesper_bay":
            pick = {}
            for kind in KINDS:
                ids = sorted(b.id for b in model.buildings if b.type.startswith(kind))
                if ids:
                    pick[ids[0]] = B.brief_hash(res["briefs"][ids[0]])
            sky = sorted(s.building_ids[0] for s in model.skybridges)
            if sky:
                pick[sky[0]] = B.brief_hash(res["briefs"][sky[0]])
            out["buildings"]["vesper_bay"] = dict(sorted(pick.items()))
            shells = {}
            for kind in AG1_KINDS:
                ids = sorted(b.id for b in model.buildings if b.type.startswith(kind))
                if ids:
                    shells[ids[0]] = C.sha256_bytes(BD.building_glb(ids[0],
                                                                   res["briefs"][ids[0]]))
            out["ag1"]["buildings"]["vesper_bay"] = dict(sorted(shells.items()))
        print(path.parent.name, out["samples"][path.parent.name], flush=True)
    with tempfile.TemporaryDirectory() as d:
        rep = SP.write_spike(d, quantized=True, which=("shopfront_row", "shanty_stack"))
        for name, r in rep["buildings"].items():
            out["spike"][name] = r["sha256"]
            for v in ("quant", "gpuinst", "ubx"):
                out["spike"][f"{name}_{v}"] = r[f"{v}_sha256"]
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN}")


if __name__ == "__main__":
    main()
