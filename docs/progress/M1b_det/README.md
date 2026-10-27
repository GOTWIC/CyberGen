# M1b determinism pass: the same city on any machine

After M1b the five sample cities were byte-identical across x86 machines, but on the owner's
M4 Mac (ARM64, macOS, Python 3.13, the same pinned numpy 2.5.4 and shapely 2.2.0) only
`archipelago_free_port` matched its golden hash. This pass makes the district partition and
the separation channels independent of the machine, adds stage tracing to find any remaining
divergence, and regenerates the golden hashes and reports.

## Stage tracing

`citygen build <spec> <out> --trace trace.json` writes a sha256 of every stage output and of
the key intermediates of the district search, in build order:

- stages (full sha256): `coast`, `rivers`, `river_islands`, `deltas`, `delta_islands`,
  `sea_islands`, `landmasses`, `ideal_positions`, `assignment`, `partition` per landmass,
  `districts`, `separation_lines`, `districts_after_channels`, `waterways`, `checks`, and per
  road attempt `megasites` and `roads<k>`; every entry carries its hydrology variant (`v3/...`)
- district search intermediates (first 16 hex digits): raster grid, weights and seeds per
  iteration (`lm0/r1/it17/weights`), each marching squares region (`contour<i>`), areas per
  round, then inside the channel stage the boundary pieces, node labels, water budget split,
  channel bodies, rebuilt land, clipped districts and handed-over tips

Hashes cover exact bits (float64 bytes, WKB plus the precision model), so the first entry that
differs is the first computation that differs. `citygen trace diff A.json B.json` prints it
(exit 0 identical, 1 different).

Traces produced on the cloud machine (x86_64 Linux) for the five samples:

| City | Trace | Entries | Model sha256 |
|---|---|---|---|
| Saltreach Free Port | `archipelago_free_port/trace.json` | 30 | `9dc08512dd7408ebee953f6b111043ee4481c756597ee097688c2cc623d95832` |
| Delta Megacity | `delta_megacity/trace.json` | 2741 | `9e57bb01c326f7943b8725417e7a96d5af41cc576b3c494f1137453dd9e7b008` |
| Nexus City | `nexus_city/trace.json` | 8513 | `1a725ee5acf7f627ced6088fbab2587fab8be6cc125721b0b6e410c17fddb1c1` |
| Vesper Bay | `vesper_bay/trace.json` | 5868 | `60221a5a24138eb175681b2e52bdc64404cbe70680dab32261ec832a4af5b535` |
| Greyhook | `peninsula_city/trace.json` | 219 | `309dcb0bd14f97bf0186b266b1e2181a8654afa23714db71a5c7ede2cb05bffa` |

On another machine:

```
.venv/bin/python -m citygen build docs/progress/M1a2/nexus_city/city_spec.json /tmp/nexus \
    --trace /tmp/nexus_trace.json
.venv/bin/python -m citygen trace diff docs/progress/M1b_det/nexus_city/trace.json \
    /tmp/nexus_trace.json
```

(Vesper Bay's spec is `cities/vesper_bay/city_spec.json`.)

## Divergence sources found

- **contourpy (confirmed first divergence).** Reproduced the Mac's failure on the cloud
  machine by running the build under emulated aarch64 Linux (qemu user mode, aarch64 wheels of
  the same pins). Before this pass, Greyhook's trace matched x86 through the coast, rivers,
  islands, landmasses, ideal positions, assignment and all 120 weight iterations of the first
  landmass, and first differed at `v0/lm0/contour0`, the first contourpy output: its compiled
  interpolation $x_0 + t\,(x_1 - x_0)$ is fused into one rounding on ARM.
- **GEOS measures in decisions.** `area` (shoelace sums), `length`, `distance`, `centroid`,
  `interpolate` and nearest points round differently when a compiler fuses multiply-adds,
  and the partition loop, the channel budget, the gap and tip hand-overs, the landmass choice
  and the variant score compared them directly.
- **Unsnapped GEOS outputs fed to further GEOS calls.** The land rebuild after the channels
  (union, difference, opening), buffers (round joins use `sin` and `cos` from the platform
  libm), channel polygons measured before quantization. Found with the noise test below:
  first at the rebuilt land in Greyhook.
- **coverage_simplify.** Visvalingam triangle areas $\tfrac12\,|(b - a) \times (c - a)|$ and
  their ties decide which vertices go.
- **Order-sensitive float sums.** The weight mean, per-cell centroid sums (`np.bincount`
  with weights), the boundary lengths of the water budget, the road principal axis.
- **Precision model attached by `shapely.set_precision`.** GEOS runs every later overlay of
  such a geometry snap-rounded, and WKB and pickling drop the model, so the same coordinates
  overlaid differently once they crossed a process boundary.
- Not present: BLAS or `linalg` calls (dot products already avoid BLAS), dict or set order in
  float accumulation (all loops run in spec or sorted order).

## What changed

- **Marching squares in the repo** (`citygen/marching.py`) instead of contourpy: crossing
  points $t = \frac{z_0}{z_0 - z_1}$, $x = x_0 + t\,(x_1 - x_0)$ as separate elementwise numpy
  operations, snapped to the 0.01 m grid at once; each crossing point is computed once per
  raster edge, so neighboring districts share identical boundary vertices; saddles resolved by
  the cell center; rings combined even-odd. contourpy is no longer imported.
- **Exact measures** (`citygen/geom.py`): `area` is the integer shoelace on grid units,
  $A = \frac{1}{2 \cdot 100^2}\left|\sum_i (X_i Y_{i+1} - X_{i+1} Y_i)\right|$ with
  $X = 100x$, $Y = 100y$ integers (exact in int64); `length` uses exact squared segment
  lengths, correctly rounded square roots and `math.fsum`; `along` places points along a line
  the same way; distances are rounded to $10^{-6}$ m, and distance thresholds use prepared
  `dwithin` with a $10^{-6}$ m margin, so a distance that is exactly the threshold (common on
  the grid) counts everywhere.
- **Snapped overlays**: `geom.inter`, `diff`, `union`, `line_inter`, `opening`, `qpoly`,
  `qpoint`, `nearest`, `centroid` snap every GEOS output to the grid before anything measures
  or compares it. Overlays run in floating point on grid inputs (GEOS decides topology with
  exact predicates and computes intersection points in double-double precision) and are
  snapped after; the snap-rounded overlays of `grid_size` were as deterministic but left
  0.01 m zigzags where two outlines nearly coincide, which bent separation channels and roads.
- **Floating precision model everywhere**: `geom.snap` rounds with `set_precision` and drops
  the attached grid again, so a geometry behaves the same in any process.
- **`coverage_simplify` on integer coordinates** (grid units), where its triangle areas are
  exact.
- **Partition loop**: weights rounded to 0.01 per iteration, Lloyd seeds to 0.01 m, means and
  per-cell sums with `math.fsum`, landmass and cell areas exact; assignment costs and channel
  scores rounded to $10^{-9}$ before comparison.
- **Ideal positions**: positions snapped every iteration; nearest points, representative
  points and centroids snapped; inner buffers snapped and cached per landmass.
- **Separation channels**: shared boundaries, node labels, near-water shares and the budget
  from exact lengths and margin distances; channel polygons snapped before they are measured.
- **Checks**: district and land areas exact (the variant score reads them).
- **Worker processes** (`citygen/build.py`): hydrology variants and road attempts run in
  batches in worker processes (`CITYGEN_WORKERS`, default the CPU count up to 8; 1 runs in
  one process). Batches are scanned in index order with the same rules as one at a time, and
  trace entries are recorded in that order, so the model and the trace do not depend on the
  number of workers. This keeps every sample under 30 s on the 4-CPU cloud container (Nexus
  City took about 50 s before this pass, one variant after another).
- **Road fallback**: the district boundaries moved by up to a raster cell, which redraws the
  roads, and the road layer is chaotic in its input (M1b "Still weak"): road variant 0 passed
  on 2 of the 6 Nexus City and Delta Megacity variants that pass the water and district
  checks. When no road variant passes on the best hydrology variant, the next two best
  variants that passed the water and district checks get their road variants too; the first
  attempt that passes wins. Delta Megacity uses it (hydrology variant 0, road variant 3).

## Verification

- **Emulated aarch64**: all five cities built under qemu with the Linux aarch64 wheels of the
  pinned versions (GEOS and numpy compiled for ARM, with fused multiply-adds). Every trace is
  identical to the x86 one, entry for entry, and so are every model and report.
- **Noise test** (`tests/test_determinism.py`): perturbs every float that GEOS computes during
  the district search (new vertices, areas, lengths, distances, centroids, interpolated and
  nearest points) and the raster field the marching squares sees by up to 4 ULP; the
  Greyhook model stays byte-identical. Run by hand on all five cities: identical. Values on
  the 0.001 m grid are not moved (grid vertices GEOS copies, and exact points such as
  midpoints, which double-double intersection computes the same everywhere).
- **Workers**: one process and several give the same bytes (test, and traces of Greyhook and
  Vesper Bay compared).
- `tests/test_roads.py::test_golden_hashes` asserts the hashes in
  `tests/data/golden_hashes.json`; every check passes for all five cities.

## Reports

`docs/progress/M1b/<city>/` holds the regenerated `preview_map.png`, `report.json` and
`report.txt` (table in `docs/progress/M1b/README.md`). The previews look as before or close
to it: Vesper Bay barely moved; Saltreach keeps its islands and roads with redrawn inner
waterways (Kettle Island's slips face west); Greyhook keeps its districts, and its separation
channel now runs between Lantern Strip and The Stacks (57% of the district boundary on water,
target 60%, was 63%); Nexus City now uses hydrology variant 1 (the Kurosawa River runs between
Northridge and Midtown); Delta Megacity variant 0 (a canal grid in Old Town, two marshes).

## Still open

- Not run on macOS here: the Mac's numpy and GEOS are built by clang against Apple's libm.
  The fixes do not depend on which operations a compiler fuses, but the owner's run is the
  real test.
- A snapped value can still round differently when a non-exact computation (a buffer vertex
  from `sin` and `cos`) lands within about $10^{-12}$ m of a half-grid value: about
  $10^{-10}$ per vertex.
- Hydrology, waterways and roads were already quantized at their stage boundaries and agree
  under emulation, but still compare some GEOS measures directly inside the stage; they get
  the same treatment if a trace ever points there.
