# WIP 04: same bytes on macOS (libc++)

The final previews are the milestone outputs themselves (not copied here):
`docs/progress/M2/<city>/preview_map.png` and `preview_detail.png`.

- The owner's Mac failed `test_golden_hashes` at Delta Megacity; emulated aarch64 Linux had
  matched x86, so it could not show the cause.
- Reproduced on x86 with GEOS rebuilt against libc++ (the C++ library of macOS builds): Delta,
  Vesper Bay and Nexus City differ at their blocks, Saltreach and Greyhook match, as on the Mac.
- Cause: the snap-rounded union of many right-of-way pieces, merged in an STRtree order that
  depends on how `std::sort` orders ties. `geom.union` now merges in its own fixed order.
- State: all five cities identical with libstdc++ and libc++ GEOS; previews look as before (a
  junction or lot more or less per city); all 31 checks pass.
