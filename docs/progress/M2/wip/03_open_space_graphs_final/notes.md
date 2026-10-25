# WIP 03: open space, graphs, final samples

The final previews are the milestone outputs themselves (not copied here):
`docs/progress/M2/<city>/preview_map.png` and `preview_detail.png` for Nyxllor, Saltreach Free
Port, Delta Megacity, Nexus City and Greyhook.

- Open space joined to the walkway graph (paths from every park, plaza and promenade); walkway
  islands linked on each landmass; lane graph strongly connected in all five cities.
- Campus loops (with a smaller fallback loop on small islands), grid dead ends extended to the
  next road, port and spaceport stubs kept as yard spurs.
- Determinism: string set order no longer reaches the model (junction classes); the same bytes
  under different `PYTHONHASHSEED` values.
- State: all 31 checks pass in all five cities.
