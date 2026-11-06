# Fix: quay stairs closed (issue #131)

AG7's quay stairs (`assetgen/streets/water.py`, `_stair`, every 60 m along a quay wall) were
drawn as treads, risers and one outer side whose top ran straight above the treads, with both
ends open. Seen from along the water, one looked into the flight's top end and through it to
the water, and the side stood above the treads as a sheet with no back.

A flight is now a solid from the quay wall's foot:
- a tread per step, and a riser per step but the first;
- its outer side, one polygon from the foot up to each tread, meeting every tread and riser on
  their own edges;
- both its ends closed (the top end facing back along the wall, the foot facing on).

It starts one step under the paving, so no riser stands alone above the first tread.

[`stair_before_after.jpg`](stair_before_after.jpg): Neon Strand's canal in Vesper Bay, the
flight on its west wall seen from the water (`assetgen materials preview --only-night --eye
-407 835 1.1 --target -410 900 -0.9 --lens 24`); on main, then fixed.

**Validation:**
- `tests/assetgen/test_ag_streets.py` (13 passed), with the new
  `test_quay_stairs_are_closed`: the only open edges of each flight lie on the quay wall's face
  or at its foot, and its faces point up, along the flight or out to the water, for water on
  either side. It fails on main with the open ends.
- `assetgen streets` and `assetgen fit` on all nine cities with quays, from main's full builds:
  every check passes.
- `tests/assetgen/data/golden_streets.json` rewritten (the small test city's and Vesper Bay's
  digests; none of the Vesper Bay tiles it names has a quay).
- AG8's quay tops on terrain cities read only the quay's paving and coping, so they are
  unchanged.
