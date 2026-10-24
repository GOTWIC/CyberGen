# Saltreach Free Port (archipelago)

## Prompt

> Archipelago free port: a city spread over five islands in a warm sea. The largest island holds
> a corporate core with twin towers and a skyport. A container port on the eastern island. A
> research campus on its own small island. An old town of creeks and canals on the western
> island. A monorail hops between the islands on long bridges, and a maglev runs to the mainland
> in the north.

## Interpretation

- Coast form `archipelago` with the open sea to the south and `sea_share` 0.8; the strip of
  mainland in the north is outside the city (unassigned), reached by the maglev and the only
  highway exit.
- Five named islands, one district each (`district_separation: water_required`). The prompt
  named four roles; the fifth island became Palm Key, a residential island.
- Area shares follow the island areas (the first validation run warned that Palm Key's share did
  not match its island).
- Crown Exchange is a small transit nexus megasite on Crown Island and the hub for both lines;
  the skyport comes from the prompt; twin towers as the corporate complex.
- Monorail Island Hopper visits every island; the bridges are `road_rail` with
  `transit_crossing: shared_deck` ("long bridges").
- After the first schematic put Lumen Key north of Crown Island, its position moved to
  south_west and the monorail route was reordered.

## Result

`citygen spec validate`: OK, 0 warnings. Schematic: `schematic.png`.
