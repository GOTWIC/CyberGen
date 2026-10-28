# Deferred: cross-platform determinism check

**Runs only when Swagnik asks for it.** Milestone PRs do not run it (see "Validation" in
`CLAUDE.md`). It is the one place where builds are compared across platforms, done once when
he asks, for example after the current milestones are finished.

## What it checks

Every sample city builds to the same bytes on every platform:
- macOS on Apple silicon (where the recorded hashes are made);
- x86_64 Linux;
- Windows, which has never been checked. Its shapely and GEOS wheels are built with another
  compiler and C++ library, which is exactly where ordering differences come from.

Compared against the recorded hashes:
- `city_model.json` sha256 against `tests/data/golden_hashes.json` (`cities`, `terrain_cities`);
- the blockout plans (`blockout_plans`);
- assetgen's goldens (`tests/assetgen/data/golden_hashes.json`);
- for the demo cities (pinned, stacks), their `report.json` against the committed one,
  ignoring timings.

## How

1. On each platform, use Python 3.13 with `requirements.txt`. On x86 Linux, use the `citygen-x86`
   Docker image on the Mac (`--platform linux/amd64`).
2. Build every sample:
   - the four in `docs/progress/M1a2/<city>/city_spec.json`;
   - every `cities/<city>/city_spec.json`.
   For each: `python -m citygen build <spec> <out>/<city>`.
3. Hash every `city_model.json` and compare with the recorded hashes.
4. Where one differs, build again with `--trace FILE` on both platforms;
   `citygen trace diff A B` names the first stage where they part
   (`docs/progress/M1b_det/README.md`).
5. Write the result as a short table under `docs/progress/determinism/`, and fix what
   differs.
