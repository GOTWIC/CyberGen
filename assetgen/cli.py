"""Command line: `assetgen spec validate|schema`, `assetgen brief BUILD`, `assetgen brief
diff A B`, `assetgen brief schema`, `assetgen spike OUT`.

Exit codes: 0 valid (diff: no change), 1 invalid spec (diff: briefs differ), 2 usage or
file error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__

EXIT_OK, EXIT_INVALID, EXIT_USAGE = 0, 1, 2


def _write_json(data: dict, out: str | None) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def _model_of(build: str | None):
    if build is None:
        return None
    from .brief import load_model
    return load_model(build)[0]


def cmd_spec_validate(args: argparse.Namespace) -> int:
    from . import spec as S
    if not Path(args.spec).is_file():
        print(f"error: {args.spec}: file not found", file=sys.stderr)
        return EXIT_USAGE
    model = _model_of(args.build)
    res = S.load_spec(args.spec, model)
    for issue in res.errors:
        print(issue, file=sys.stderr)
    if not args.quiet:
        for issue in res.warnings:
            print(issue, file=sys.stderr)
    if not res.ok:
        print(f"INVALID: {args.spec}: {len(res.errors)} error(s)", file=sys.stderr)
        return EXIT_INVALID
    if args.filled:
        _write_json(S.dump(res.filled), args.filled)
    s = res.filled
    print(f"OK: {s.city or '(any city)'}: {s.uniqueness}, {s.texel_density_px_m} px/m, "
          f"{len(res.spec.eras)} eras set ({len(s.eras)} with presets), "
          f"{len(s.districts)} districts, {len(s.owners)} owners, {len(s.landmarks)} "
          f"landmarks, {len(res.warnings)} warnings")
    return EXIT_OK


def cmd_spec_schema(args: argparse.Namespace) -> int:
    from .spec import json_schema
    return _write_json(json_schema(), args.out)


def cmd_brief(args: argparse.Namespace) -> int:
    from . import brief as B
    from . import spec as S
    src = Path(args.build)
    if not (src / "city_model.json").is_file() and not src.is_file():
        print(f"error: {args.build}: no city_model.json", file=sys.stderr)
        return EXIT_USAGE
    t0 = time.perf_counter()
    model, sha, bdir = B.load_model(src)
    spec = None
    if args.spec:
        res = S.load_spec(args.spec, model)
        for issue in res.issues:
            print(issue, file=sys.stderr)
        if not res.ok:
            return EXIT_INVALID
        spec = res.spec
    ov = S.overrides_by_id(S.load_overrides(args.overrides)) if args.overrides else None
    t1 = time.perf_counter()
    result = B.build_briefs(model, spec, ov)
    out = Path(args.out) if args.out else bdir / "assets"
    path = B.write_briefs(out, model, sha, result)
    st = result["stats"]
    st["seconds"]["load"] = round(t1 - t0, 2)
    (out / "brief_report.json").write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8",
                                           newline="\n")
    if not args.no_preview:
        from .preview_edges import render
        render(model, result["briefs"], out / "preview_edges.png")
    print(f"wrote {path}: {st['buildings']} briefs in {time.perf_counter() - t0:.1f} s")
    print("edges: " + ", ".join(f"{k} {v}" for k, v in st["edges"].items()))
    return EXIT_OK


def cmd_brief_diff(args: argparse.Namespace) -> int:
    from . import briefdiff as D
    try:
        d = D.diff(args.a, args.b)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        Path(args.json).write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8",
                                   newline="\n")
    sys.stdout.write(D.text(d, None if args.all else 20))
    return EXIT_OK if not (d["added"] or d["removed"] or d["changed"]) else EXIT_INVALID


def cmd_brief_schema(args: argparse.Namespace) -> int:
    from .briefmodel import json_schema
    return _write_json(json_schema(), args.out)


def cmd_spike(args: argparse.Namespace) -> int:
    from . import spike
    rep = spike.write_spike(args.out, quantized=args.quantized)
    for name, r in rep["buildings"].items():
        print(f"{name}: {r['triangles']} triangles, {r['instances']} instances, "
              f"{r['bytes']} bytes, sha256 {r['sha256'][:16]}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="assetgen",
                                description="Offline building, street and texture assets.")
    p.add_argument("--version", action="version", version=f"assetgen {__version__}")
    sub = p.add_subparsers(dest="group", required=True)

    spec = sub.add_parser("spec", help="asset spec tools")
    ssub = spec.add_subparsers(dest="command", required=True)
    v = ssub.add_parser("validate", help="validate an asset spec and fill the era presets")
    v.add_argument("spec")
    v.add_argument("--build", metavar="BUILD", help="check names against this city build")
    v.add_argument("--filled", metavar="OUT.json", help="also write the filled spec")
    v.add_argument("-q", "--quiet", action="store_true", help="hide warnings")
    v.set_defaults(func=cmd_spec_validate)
    sc = ssub.add_parser("schema", help="print or write the asset spec JSON Schema")
    sc.add_argument("out", nargs="?")
    sc.set_defaults(func=cmd_spec_schema)

    br = sub.add_parser("brief", help="the brief of every building (briefs.json)")
    bsub = br.add_subparsers(dest="command", required=True)
    bm = bsub.add_parser("make", help="write BUILD/assets/briefs.json (also: assetgen brief "
                                      "BUILD)")
    bm.add_argument("build", help="a citygen build directory (or its city_model.json)")
    bm.add_argument("--spec", help="asset_spec.json (default: the era presets)")
    bm.add_argument("--overrides", help="asset_overrides.json")
    bm.add_argument("--out", help="output directory (default BUILD/assets)")
    bm.add_argument("--no-preview", action="store_true", help="skip preview_edges.png")
    bm.set_defaults(func=cmd_brief)
    bd = bsub.add_parser("diff", help="briefs added, removed and changed between two builds")
    bd.add_argument("a", help="briefs.json or a build directory")
    bd.add_argument("b")
    bd.add_argument("--json", metavar="FILE", help="also write the diff as JSON")
    bd.add_argument("--all", action="store_true", help="list every id")
    bd.set_defaults(func=cmd_brief_diff)
    bs = bsub.add_parser("schema", help="print or write the brief JSON Schema")
    bs.add_argument("out", nargs="?")
    bs.set_defaults(func=cmd_brief_schema)

    sp = sub.add_parser("spike", help="AG0's three test buildings as glTF (the Unreal spike)")
    sp.add_argument("out")
    sp.add_argument("--quantized", action="store_true",
                    help="also write KHR_mesh_quantization copies")
    sp.set_defaults(func=cmd_spike)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `assetgen brief BUILD` is short for `assetgen brief make BUILD`
    if len(argv) >= 2 and argv[0] == "brief" and argv[1] not in ("make", "diff", "schema",
                                                                 "-h", "--help"):
        argv.insert(1, "make")
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
