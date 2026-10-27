# WIP 02: junctions, sidewalks, blocks, lots, open space, graphs

Real previews from `citygen build` (not yet final): `<city>_map.png` (full map: blocks tinted
by district, lot lines, streets to scale, alleys, service lanes, promenades, footbridges,
crosswalks, open space) and `<city>_detail.png` (four 400 m insets: asphalt with curbs,
sidewalks, medians, lane markings, zebra crosswalks, one-way arrows, lots).

- Junction polygons from cross-sections with corner fillets by class; signals by junction
  class; crosswalks; sidewalks with clear path; one-way loops in the old town and markets.
- Lane graph (lanes, connectors, lane changes) and walkway graph (sidewalks, crossings,
  promenades, footbridges, alleys, paths into open space).
- Blocks from the right of way; lots by OBB splits with frontage, courtyards in perimeter
  blocks; parks, plazas, markets and courtyards; named places.
- State: Vesper Bay and Greyhook pass every check; Saltreach and Delta have one oversized lot
  each, Nexus a few lanes outside the main lane graph. Build times 19 to 53 s; tuning next.
