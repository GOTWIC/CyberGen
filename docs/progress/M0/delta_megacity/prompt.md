# Delta Megacity

## Prompt (verbatim)

> Delta megacity: a huge river splits into four channels before it reaches the sea in the south. Every district sits on its own landmass between the channels. A transit nexus on the central island where every line meets. Corporate core on the east bank with a megatower and twin towers. A canal-laced old town on the west bank with floating markets. An industrial port at the river mouth with a freight terminal. Midtown with a central park in the north, upstream. A lush research campus on an island in the delta. Metro and maglev through the center, two sky tube loops, monorail along the waterfront.

Image: none. Seed: 4412.

## Interpretation

- Size: "megacity" read as the top of the default range, 3.5 x 3.5 km (12.25 km²).
- Coast: `delta` form, open sea to the south ("Southern Sea", invented name).
- River: one "Great River" from the north edge to the sea, width 120 to 150 m ("huge", the top of
  the river range), meander 0.35. "Four channels" read as the main channel plus 3 `delta_branches`
  (West, East and Far West Channel, invented names).
- "Every district on its own landmass": `district_separation: water_required`. With a single river
  this cannot hold for all six districts: Midtown and the Corporate Core share the east bank, Old Town
  and the Industrial Port share the west bank. Inventing extra rivers or tributaries to split the
  banks was tried (round 2, as sea channels) and dropped: it misstated the hydrology and the schematic
  did not separate the banks anyway.
- Central island: `Central Island`, a `mid_river` island at the center (0.55 km²) holding the Transit
  Nexus district (archetype `transit_hub`) and the `transit_nexus` megasite; it is the only hub.
- Corporate Core: east of the nexus, south of Midtown, across the Great River; `megatower` landmark
  (default 480 m) and a `twin_towers` complex.
- Old Town: west edge, west of the nexus, across the Great River; canal grid plus organic canals
  (density 0.75); "floating markets" as a `market` place named Floating Markets.
- Industrial Port: south edge, on the coast, along the river, south of the nexus and Old Town;
  `freight_terminal` megasite and harbor basins.
- Midtown: north east edge (upstream, north of the Corporate Core) with a `central_park` megasite.
  North east rather than plain north because one bank had to be chosen.
- Research Campus: on `Delta Island` (a `delta` island, 0.5 km²) at the mouth; "lush" as greenery 0.9.
- Transit, every line through the Transit Nexus:
  - Metro Line (metro): Old Town, Transit Nexus, Corporate Core (west to east through the center).
  - Maglev Line (maglev): north exit, Midtown, Transit Nexus, Industrial Port (north to south).
  - Skyline Loop (sky_tube, through towers): Transit Nexus, Corporate Core, Midtown, back.
  - Delta Loop (sky_tube): Transit Nexus, Old Town, Research Campus, Industrial Port, back.
  - Waterfront Monorail (monorail): West Quay (Old Town), Transit Nexus, East Quay (Corporate
    Core), Harbor Front (Industrial Port); it also serves the freight terminal.
- Left to presets: highways (ring plus spine), bridges, heights, block sizes, street patterns,
  area shares, other complexes and megasites.

## Result

Written by a separate subagent session that was given only the skill and this prompt (a test of
the skill). `citygen spec validate`: OK, 0 warnings. Schematic: `schematic.png`, re-rendered after
the renderer started fanning delta branches out along the coast.
