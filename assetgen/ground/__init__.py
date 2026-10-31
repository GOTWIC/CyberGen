"""AG13, ground cover and grass (scope 5.6, 14.14): every piece of M16's open land drawn with
its cover kind's texture sets, blended by its wear, shade, edges and moisture, and grass and
small plants scattered on it as instanced clumps, per 256 m tile.

- `kinds`: the surfaces (texture sets per cover kind), the densities and clump mixes, the
  budgets;
- `clumps`: the clump meshes (short lawn, long meadow, reeds, cattails, weeds, clover,
  flowers in a district's palette, ferns, and AG8's scrub and sedum);
- `gather`: what each tile reads from the model (its pieces, desire lines, decks, trees,
  water, shade and ground), and the blockout objects it replaces;
- `tile`: one tile in a worker: its mask texture, its ground mesh, its grass;
- `build`: the stage (`assetgen ground BUILD`, the last stage of `assetgen build`);
- `contribution`, `checks`, `preview`: the Unreal contribution, the checks and report, a
  top-down preview.
"""
