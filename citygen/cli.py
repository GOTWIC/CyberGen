"""Command line: `citygen spec validate|render|schema|diff`, `citygen build`, `citygen
blockout`, `citygen review`, `citygen model schema`, `citygen trace diff`.

Exit codes: 0 valid (build: every check passed), 1 invalid spec or a failed build check,
2 usage or file error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__

MAX_VARIANTS = 20  # same as citygen.build.MAX_VARIANTS (kept here so `spec` stays light)
from .validate import Result, SpecError, dump_spec, load_spec

EXIT_OK, EXIT_INVALID, EXIT_USAGE = 0, 1, 2


def _print_issues(result: Result, quiet: bool = False) -> None:
    for issue in result.errors:
        print(issue, file=sys.stderr)
    if not quiet:
        for issue in result.warnings:
            print(issue, file=sys.stderr)


def _load(path: str) -> Result | int:
    if not Path(path).is_file():
        print(f"error: {path}: file not found", file=sys.stderr)
        return EXIT_USAGE
    try:
        return load_spec(path)
    except SpecError as e:
        for issue in e.issues:
            print(issue, file=sys.stderr)
        return EXIT_INVALID


def _summary(result: Result) -> str:
    s = result.filled
    lines = s.transit.lines
    modes = sorted({line.mode for line in lines})
    sites = sum(len(d.megasites or []) for d in s.districts)
    return (f"OK: {s.name}: seed {s.seed}, {s.size_km[0]:g} x {s.size_km[1]:g} km, "
            f"{len(s.districts)} districts, {len(s.water.rivers)} rivers, "
            f"{len(s.water.islands)} islands, {len(lines)} transit lines "
            f"({', '.join(modes) or 'none'}), {sites} megasites, "
            f"{len(result.warnings)} warnings")


def cmd_validate(args: argparse.Namespace) -> int:
    result = _load(args.spec)
    if isinstance(result, int):
        return result
    _print_issues(result, args.quiet)
    if not result.ok:
        print(f"INVALID: {args.spec}: {len(result.errors)} error(s)", file=sys.stderr)
        return EXIT_INVALID
    if args.filled:
        Path(args.filled).parent.mkdir(parents=True, exist_ok=True)
        Path(args.filled).write_text(dump_spec(result.filled), encoding="utf-8")
    print(_summary(result))
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    result = _load(args.spec)
    if isinstance(result, int):
        return result
    _print_issues(result, quiet=True)
    if not result.ok:
        print(f"INVALID: {args.spec}: {len(result.errors)} error(s); nothing rendered",
              file=sys.stderr)
        return EXIT_INVALID
    from .schematic import render  # matplotlib is only needed here

    render(result.filled, args.out, dpi=args.dpi)
    print(f"wrote {args.out}")
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    result = _load(args.spec)
    if isinstance(result, int):
        return result
    _print_issues(result, quiet=True)
    if not result.ok:
        print(f"INVALID: {args.spec}: {len(result.errors)} error(s); nothing built",
              file=sys.stderr)
        return EXIT_INVALID
    from . import trace
    from .build import build_city, write_outputs  # shapely, matplotlib only here

    if args.trace:
        trace.start()
    built = build_city(result, max_variants=args.variants)
    entries = trace.stop() if args.trace else None
    paths = write_outputs(built, args.out_dir, dpi=args.dpi)
    if args.trace:
        import hashlib

        sha = hashlib.sha256((built.model.to_json() + "\n").encode("utf-8")).hexdigest()
        trace.write(args.trace, built.spec.name, sha, entries)
        paths.append(Path(args.trace))
    for p in paths:
        print(f"wrote {p}")
    failed = [c for c in built.checks if not c.passed]
    if failed:
        for c in failed:
            for f in c.failures:
                print(f"check failed: {c.id}: {f}", file=sys.stderr)
        print(f"FAIL: {built.spec.name}: {len(failed)} check(s) failed; see "
              f"{Path(args.out_dir) / 'report.txt'}", file=sys.stderr)
        return EXIT_INVALID
    print(f"PASS: {built.spec.name}: all {len(built.checks)} checks passed")
    if args.blockout:
        return _blockout(Path(args.out_dir) / "city_model.json", args.out_dir, args)
    return EXIT_OK


def _blockout(model: Path, out_dir: str, args: argparse.Namespace) -> int:
    from .blockout import run_blockout

    rep = run_blockout(model, out_dir, blender=args.blender, render=not args.no_render,
                       export=not args.no_export, res=args.res, samples=args.samples)
    for c in rep["checks"]:
        if not c["passed"]:
            print(f"blockout check failed: {c['id']}: {c['detail']}", file=sys.stderr)
    out = Path(out_dir)
    b = rep.get("blender") or {}
    for f in ["blockout_plan.json", "map_2d.svg", "map_2d.png", "graphs.json", "tiles.json",
              "props.csv", "unreal/corporate_core_plan.json"]:
        print(f"wrote {out / f}")
    for k, v in (b.get("files") or {}).items():
        print(f"wrote {out / v}" if isinstance(v, str) else f"wrote {len(v)} {k} in {out}")
    if not rep["passed"]:
        print(f"FAIL: blockout of {rep['city']}; see {out / 'blockout_report.txt'}",
              file=sys.stderr)
        return EXIT_INVALID
    print(f"PASS: blockout of {rep['city']}: {rep['plan']['objects']} objects, "
          f"{rep['plan']['tiles']} tiles, {rep['timings']['total_s']} s")
    return EXIT_OK


def cmd_blockout(args: argparse.Namespace) -> int:
    if not Path(args.model).is_file():
        print(f"error: {args.model}: file not found", file=sys.stderr)
        return EXIT_USAGE
    return _blockout(Path(args.model), args.out_dir, args)


def _blockout_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--blender", help="Blender executable (default: $BLENDER, the newest "
                                     "/Applications/Blender*.app, or blender on PATH)")
    p.add_argument("--no-render", action="store_true", help="skip the preview renders")
    p.add_argument("--no-export", action="store_true", help="skip USD and glTF tiles")
    p.add_argument("--res", type=int, default=1600, help="render width in pixels")
    p.add_argument("--samples", type=int, default=16, help="EEVEE render samples")


def _write_json(data: dict, out: str | None) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def cmd_spec_schema(args: argparse.Namespace) -> int:
    from .spec import json_schema

    return _write_json(json_schema(), args.out)


def cmd_trace_diff(args: argparse.Namespace) -> int:
    from . import trace

    try:
        a, b = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (args.a, args.b))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    lines = trace.diff(a, b)
    if not lines:
        print(f"identical: {len(a['entries'])} entries, model {a.get('model_sha256')}")
        return EXIT_OK
    print("\n".join(lines))
    return EXIT_INVALID


def cmd_spec_diff(args: argparse.Namespace) -> int:
    from .review import spec_diff

    try:
        a, b = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (args.a, args.b))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    lines = spec_diff(a, b)
    print("\n".join(lines) if lines else "no changes")
    return EXIT_OK


def cmd_review(args: argparse.Namespace) -> int:
    from .review import review

    if not (Path(args.out_dir) / "report.json").is_file():
        print(f"error: {args.out_dir}: no report.json (build first)", file=sys.stderr)
        return EXIT_USAGE
    rec = review(args.out_dir, args.spec, args.prev)
    print(f"wrote {Path(args.out_dir) / 'review.md'} (round {rec['round']} of at most "
          f"{rec['max_rounds']}; checks {'PASS' if rec['passed'] else 'FAIL'}; "
          f"{len(rec['spec_changes'])} spec changes)")
    return EXIT_OK if rec["passed"] else EXIT_INVALID


def cmd_model_schema(args: argparse.Namespace) -> int:
    from .model import json_schema

    return _write_json(json_schema(), args.out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="citygen", description="Offline prompt-to-city generator.")
    p.add_argument("--version", action="version", version=f"citygen {__version__}")
    sub = p.add_subparsers(dest="group", required=True)

    spec = sub.add_parser("spec", help="city spec tools")
    ssub = spec.add_subparsers(dest="command", required=True)
    v = ssub.add_parser("validate", help="validate a spec and fill defaults")
    v.add_argument("spec")
    v.add_argument("--filled", metavar="OUT.json", help="also write the filled spec")
    v.add_argument("-q", "--quiet", action="store_true", help="hide warnings")
    v.set_defaults(func=cmd_validate)
    r = ssub.add_parser("render", help="2D debug schematic of a spec (PNG)")
    r.add_argument("spec")
    r.add_argument("out")
    r.add_argument("--dpi", type=int, default=110)
    r.set_defaults(func=cmd_render)
    sc = ssub.add_parser("schema", help="print or write the spec JSON Schema")
    sc.add_argument("out", nargs="?")
    sc.set_defaults(func=cmd_spec_schema)
    sd = ssub.add_parser("diff", help="parameter changes between two specs")
    sd.add_argument("a")
    sd.add_argument("b")
    sd.set_defaults(func=cmd_spec_diff)

    b = sub.add_parser("build", help="build the city model, checks and previews (water, "
                                     "districts, roads, streets, lots, buildings)")
    b.add_argument("spec")
    b.add_argument("out_dir")
    b.add_argument("--dpi", type=int, default=110)
    b.add_argument("--variants", type=int, default=MAX_VARIANTS,
                   help=f"hydrology variants to try at most (default {MAX_VARIANTS})")
    b.add_argument("--trace", metavar="FILE.json",
                   help="also write a sha256 of every stage output and of the district "
                        "search intermediates (compare machines with `citygen trace diff`)")
    b.add_argument("--blockout", action="store_true",
                   help="after a passing build, also build the Blender blockout (M4)")
    _blockout_args(b)
    b.set_defaults(func=cmd_build)

    bo = sub.add_parser("blockout", help="Blender blockout of a built city: .blend, USD, "
                                         "glTF tiles, renders, 2D map, exports")
    bo.add_argument("model", help="city_model.json from `citygen build`")
    bo.add_argument("out_dir")
    _blockout_args(bo)
    bo.set_defaults(func=cmd_blockout)

    rv = sub.add_parser("review", help="art-direction review sheet of a build (review.md): "
                                       "checks, numbers, changes since the last round")
    rv.add_argument("out_dir", help="a `citygen build` output folder")
    rv.add_argument("--spec", help="the spec it was built from (kept for the next round)")
    rv.add_argument("--prev", metavar="PREV_OUT_DIR", help="the previous round's folder")
    rv.set_defaults(func=cmd_review)

    tr = sub.add_parser("trace", help="build trace tools")
    tsub = tr.add_subparsers(dest="command", required=True)
    td = tsub.add_parser("diff", help="first entry where two build traces differ "
                                      "(exit 0 identical, 1 different)")
    td.add_argument("a")
    td.add_argument("b")
    td.set_defaults(func=cmd_trace_diff)

    model = sub.add_parser("model", help="city model tools")
    msub = model.add_subparsers(dest="command", required=True)
    ms = msub.add_parser("schema", help="print or write the city model JSON Schema")
    ms.add_argument("out", nargs="?")
    ms.set_defaults(func=cmd_model_schema)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on usage errors, 0 on --help
        return int(e.code or 0)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
