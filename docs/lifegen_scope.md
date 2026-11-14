# lifegen: people, traffic, transit and air (scope, v1: decided 2026-11-13, LG0 done)

Stage 4 (lifegen) of CyberGen's five stages. It takes a built city with its assets (and,
once stage 3 is there, its hours and weather) and fills it with life: varied, realistic
people on every sidewalk, stair and deck, going about their day; cars, buses, taxis and
bikes on the roads; trains, pods and sky tubes running their lines; flying cars, drones,
aircraft and boats. All of it goes into Unreal through the shared exporter
(`docs/unreal_export.md`). Like the other stages it is city-agnostic, offline and
deterministic in what it generates; the simulation that moves it runs in Unreal. Its
milestones carry the prefix LG (LG0 to LG8, section 13). It starts after AG16
(performance), whose benchmark is its baseline. Swagnik decided section 12 on 2026-11-13;
LG0's findings and the recommendations for LG1 to LG8 are in `docs/progress/LG0/README.md`.

```
 citygen build  ──>  city_model.json          assetgen build  ──>  assets/ (doors,
        │            (graphs, densities,               │             parked car variants)
        │             places, factions)                 │
        └──────────────────────┬───────────────────────┘
                               v
 [lifegen plan, offline deterministic Python]
        ├──> population: who lives and works where, by district, wealth, danger and hour
        ├──> demand: trips by hour (home, work, shops, bars, transit, taxis), spawn and
        │     sink points at doors, stations, garages and the map edge
        ├──> traffic: fleet mix by street and hour, signal phases, parking, bus routes
        ├──> transit timetables, air lanes and pads, boat lanes and piers
        └──> places: slots at benches, stalls, stops and doors with their behaviors
        │
        ├──> checks (every trip reachable, densities met, nothing spawned in a wall,
        │     no conflicting greens, air lanes clear)
        ├──> previews (density and flow maps, a Blender crowd still)
        └──> Unreal exporter: layer 4 of the manifest, and the CityGenLife runtime
             plugin that simulates it on Unreal's Mass, ZoneGraph and Smart Objects

 [lifegen library, built once per project]  people (bodies, garments, accessories,
        cyberware, hair, animation, crowd stand-ins) and vehicles (cars to sky pods)

 life_spec.json (who lives in each district, styles, fleets, written by a Claude Code
 session through a `lifegen` skill from the city prompt; no API call)
```

## 1. Goal

A city that is lived in: dense crowds on the market streets at night and thin ones in the
port; office workers in the core at morning rush, partygoers in the entertainment district
after midnight; people waiting at crosswalks for the signal, queueing at a noodle stall,
sitting on a bench under an awning in the rain, climbing a deck's stairs, going in and out
of shops and bars by their opening hours; gangs on their own turf, police patrolling where
the city puts them. Traffic that stops at the lights, buses on their routes, taxis at
their stands, trains and pods on their timetables, flying cars between the towers,
drones, and boats on the canals.

Done, as the user sees it: walk any street at any hour and it has the people it should,
none of them alike, all doing something plausible; stand at a junction and the traffic
flows by the signals; fly over and the city moves.

## 2. What lifegen is

**A generator of who and what is where, with a simulation in the engine.** It keeps the
contract of the other stages (a spec in, a deterministic plan out keyed by M10's ids,
checks, previews, a layer of the manifest, district regeneration by hash) for everything
that can be decided offline: the population, its trips by hour, the fleet, the signals,
timetables, lanes in the air and on the water, the slots where people do things. The
moving is Unreal's: Mass Entity simulates crowds and traffic on ZoneGraph lanes built from
the city's own graphs, StateTree runs behaviors, Smart Objects are the benches, stalls and
doors.

It has four parts:

| Part | What it is | Per city? | Where it lives |
|---|---|---|---|
| The plan | population, demand, fleet, signals, timetables, air and water lanes, place slots | yes, generated from the city | `lifegen/`, written to `BUILD/life/` |
| The library | the people (bodies, faces, garments, accessories, cyberware, hair, animation, crowd stand-ins) and the vehicles, built from the life spec's styles | once per project (and again when a style changes), shared by its cities | `lifegen/library/`, written to a cache as AG6's texture library is |
| The runtime | a C++ runtime plugin, `CityGenLife`, beside `CityGenPlay` and `CityGenAtmos`: lanes from the graphs, spawning by tile and hour, crowd and traffic processors, behaviors, LODs | no, shared by every city | `citygen/ue/CityGenLife`, built and copied by the exporter |
| The styles | who lives where: fashion, jobs, gangs' colors, fleets, per district and archetype | chosen per city in the life spec | `lifegen/presets.py`, `life_spec.json` |

Options weighed:

- **Unreal's City Sample as is.** Epic's sample city has crowds and traffic on Mass, but its
  traffic is a plugin of that sample, made for its city, and its content is Epic's; neither
  can be copied into a repo anyone may use. Its engine plugins (Mass Entity, Mass Crowd,
  ZoneGraph, Smart Objects, StateTree) are what lifegen builds on.
- **Hand-placed crowds and traffic per city.** Does not scale and does not follow a
  regenerated district.
- **A generator plus a runtime plugin** (this scope): the plan says how many of whom are
  where at each hour and where they go, from data stage 1 already has; the plugin moves
  them.

## 3. Where it starts (main, 2026-11-04)

| Already there | From | Use |
|---|---|---|
| Walkway graph per level: sidewalks, crosswalks, crossings, alleys, paths, promenades, footbridges, skybridges, stairs, escalators, elevators, underpasses, with widths | M2, M14, M5, M9 | crowd lanes (ZoneGraph) |
| Lane graph: lanes per road and direction, connectors through nodes, successors, adjacent lanes for lane changes, levels | M2, M7, M12, M14 | traffic lanes |
| Signalized junctions and crosswalks by need | M18 | where traffic stops; the phases are not modeled yet |
| Density per street and hour band (night, morning, day, evening, late): vehicles per hour and per 100 m, pedestrians, gang members and police per 100 m | M11 | how many, where, when |
| Points of interest with opening hours and access (door, walkway, drive lane, curb point); parking (garages, lots, curb, capacity, entrances); taxi stands; fast travel | M11 | trip ends, spawn and sink points |
| Factions, turfs, precincts; wealth, danger and police fields | M11 | who is where, gangs and patrols |
| Transit lines (metro, elevated rail, monorail, maglev, sky tube) with stations, stairs, elevators and platforms | M5, M19 | trains and pods, boarding |
| Benches, bus shelters, kiosks, vending machines, food stalls, parked cars, boats | M6, M20 | place slots, the fleet's starting cars |
| Roof helipads and AV pads; the spaceport and port megasites | M3, AG4 | air lanes' ends, aircraft, ships |
| Water with flow; Single Layer Water | M16, AG12 | boat lanes, wakes |
| Every door with its walkway (`cg.door` tags and the doors graph) | AG3 | people in and out of buildings |
| Parked car variants per district style | AG8 | the fleet's look, until the fleet replaces them |
| The graphs in Unreal as data assets (`BP_CityGenGraph`: lanes, walkways, transit, doors, levels) | M15, AG3, M14 | the runtime's input |
| A C++ runtime plugin pattern (`CityGenPlay`, built with UnrealBuildTool) | play features | how `CityGenLife` is built |
| Hours and weather | atmosgen (planned) | crowds by hour, umbrellas and shelter in rain |

What is missing goes into asks of citygen (section 4.1): signal phases and their timing,
bus routes and stops, turn restrictions where a junction needs them, lobbies (where a door
leads inside), ferry piers.

## 4. How it fits

### 4.1 Inputs it reads (read only)

- **citygen model:** everything in section 3's table.
- **assetgen outputs:** doors, the parked car variants, the deck stairs and elevators
  (AG10), what blocks a walkway (AG14's fit report), surfaces people stand on.
- **atmosgen** (when there): the hour and weather the runtime reads from `MPC_CityGen`.
- **life spec:** section 5.
- **Asks of citygen:** signal phases and timing per signalized junction (with the
  crosswalks they serve), bus routes and their stops, turn restrictions, lobby points
  behind main doors, piers for ferries and water taxis, air corridors where a city wants
  them (else lifegen draws its own over the roads).

### 4.2 Outputs and the exporter

- `BUILD/life/`: `life_plan.json` (canonical, a hash per entry), per tile
  `spawns/<tile>.json` (spawn and sink points with their rates by hour, place slots),
  `signals.json`, `timetables.json`, `air_lanes.json`, `boat_lanes.json`,
  `life_report.json/.txt`, previews (`preview_crowds.png` by hour, `preview_traffic.png`,
  `preview_air.png`), `unreal_contribution.life.json`.
- **Layer 4 of the manifest:** spawners, place slots (Smart Objects at benches, stalls,
  stops, doors), signal controllers, transit vehicles, air and boat lanes, keyed by the ids
  of what they belong to (`slot.<bench id>`, `sig.<junction id>`, `train.<line id>.<n>`).
- **The runtime plugin** (`CityGenLife`, C++): ZoneGraph lanes built from the graphs'
  data assets (no hand-drawn shapes), spawning by tile as cells stream in and by the hour,
  Mass processors for walking, avoidance, crossing at signals, traffic following, lane
  changes, parking, StateTree behaviors (go to a place, use a slot, wait, board, shelter),
  LODs from full characters near to cheap stand-ins far, the vehicles' lights hooked to
  atmosgen's night.
- **The library's Unreal side:** people as skeletal meshes with their materials and
  animation, assembled per person (Mutable, Unreal's customizable character system, or
  lifegen's own merge, decided in LG1), vehicles as meshes with wheels and lights.

### 4.3 The line with the other stages

| Stage | Owns | lifegen owns |
|---|---|---|
| citygen | where things are: walkways, lanes, places, densities, factions | who uses them, when, how |
| assetgen | the city's static models: buildings, street elements, props; AG18's hand-designed vehicles (one roster, parked by step H) | everything that moves: people, and AG18's vehicles driven (decision 12.6: one fleet, parked and moving) |
| atmosgen | light, air, weather, hour | people and traffic reacting to them; the vehicles' and aircraft's own lights as light sources go through atmosgen's tiers |
| storygen | story, characters, events | the background life a story plays over; storygen's characters are lifegen people with a story |

## 5. The life spec

Written from the city prompt by a Claude Code session (a `lifegen` skill); never required
to edit. Fields, all with defaults:

- `population`: per district archetype the mix of residents, workers and visitors (ages,
  jobs, wealth), defaulting from archetype, wealth and danger; how busy each hour band is
  relative to M11's densities.
- `styles`: fashion per district and group (corporate, street, market, industrial,
  nightlife, gang colors from M11's factions, police uniforms), how much cyberware, how
  worn; a city palette.
- `fleet`: vehicle mix per district as weights of AG18's models (default the parked cars'
  table, `assetgen/parked/table.py`), how many fly, how old and worn.
- `transit`: service frequency per line and hour.
- `air` and `water`: how busy the sky and the canals are.

## 6. Feature catalog

### 6.1 People

- **Bodies and faces:** realistic adults of every build, age and skin tone, each person
  their own (a seed draws body, face, skin, hair, height, gait).
- **Clothing:** section 6.2.
- **Animation:** walking at the person's own pace and gait, idles, waiting, talking in
  groups, phone, smoking, eating at a stall, sitting, climbing stairs, riding escalators,
  carrying bags, holding an umbrella; motion matching near the view, cheaper shared or
  baked animation far.
- **Crowd stand-ins:** past a few dozen meters people become cheaper (fewer bones, baked
  vertex animation, then impostor cards), so the far crowd still moves.

### 6.2 Clothing

Clothing is the largest art problem in lifegen: a crowd of clones reads fake at once, and a
cyberpunk crowd needs street fashion, jackets, visors and cyberware that no stock wardrobe
has. The plan, from most generated to least:

- **Garments from sewing patterns, generated.** A garment template is a set of flat panels
  in code (front, back, sleeves, hood, collar, pockets), with parameters for fit, length,
  cut and layering (tee, shirt, hoodie, bomber, trench coat, poncho, cargo pants, skirt,
  coveralls, suit). Each is draped once per body type in Blender's cloth solver (headless,
  as the previews are), as tailoring software does, then baked to a mesh, skinned by
  weights taken from the body, given LODs, and hashed. Blender is already in the
  toolchain, so nothing is downloaded and nothing is hand-made.
- **Textiles, generated:** denim, leather, vinyl, nylon, knits, mesh, reflective and
  LED-trimmed fabrics as tileable sets in AG6's library style (integer-hash noise, PBR),
  prints and logos from AG6's brand logos and signage, wear and grime by wealth and
  danger, gang colors from the factions.
- **Accessories and cyberware, generated:** hard-surface pieces in the way AG2 and AG8 make
  parts: visors, masks, respirators for the smog, implants, arm and face plates, glowing
  lines (emissive decals), headsets, backpacks, bags, hats, umbrellas.
- **Outfits:** layering rules (a base layer, an outer layer, accessories) drawn per
  person from the style of their district, group, job, wealth and the weather (raincoats
  and umbrellas in rain); a variety check keeps people near each other distinct.
- **Simulation:** cloth simulated (Unreal's Chaos Cloth) only on the few people nearest the
  view with long coats, ponchos or skirts; everyone else's clothing moves with their body.
- **What Unreal gives:** MetaHuman comes with a plain wardrobe; recent versions added
  outfits that refit to any MetaHuman body, Chaos Cloth and its panel cloth tools,
  learned cloth deformation (ML Deformer) and Mutable for assembling many characters from
  parts cheaply. Fab sells MetaHuman-compatible clothing, which a user may use in their own
  project but which cannot ship in this repo. What 5.8 offers for scripted refitting is
  LG0's question.
- **Fallback:** if generated garments do not hold up up close, a small authored base kit
  (made or bought for the user's project, kept out of the repo), with lifegen's textiles,
  accessories, cyberware and outfit rules on top. Decision 12.3.

### 6.3 Crowds

- People on every walkway at each street's density for the hour, on every level, using
  stairs, escalators and elevators between them, crossing at crosswalks with the signals
  (and jaywalking more where danger is high), in groups of one to five, at their own pace,
  keeping right, avoiding each other and the player.
- Trips with a reason: home to work in the morning, to shops by day, to bars and clubs by
  night, to stations and taxi stands; spawned at doors, station exits and garages, and
  despawned there, so a crowd is never conjured out of nowhere in view.

### 6.4 Life at places

- Smart Object slots at benches, bus shelters, stalls, kiosks, vending machines, taxi
  stands, shop doors and bar entrances: sit, queue, buy, eat, wait, smoke, talk.
- Points of interest by their hours: shops open and close, bars fill at night, clinics
  lit and busy.
- Gangs on their turf (M11), loitering and moving in groups in their colors; police
  patrolling by the police field, on foot and in cars.

### 6.5 Traffic

- **The fleet is AG18's hand-designed vehicles** (decision 6, changed from the draft):
  `vehicles/`, their game packs fetched by `vehicles/packs.py`, the same models moving and
  parked (AG18's step H parks them in place of AG8's variants; LG5 drives them). The kinds
  the roster lacks (buses, trucks, motorbikes, bikes, flying cars, drones, boats) are
  designed on the Mac the same way, one Blender script each, and join the roster as packs.
  lifegen draws a model per vehicle from its district's weights (`assetgen/parked/table.py`,
  the parked cars' table) and paints it per vehicle; it generates no vehicle geometry.
- A fleet per district (section 5) on the lane graph: following, lane changes, turns by
  the connectors, stopping at signals by their phases, yielding at crossings, parking at
  the curb and in garages and leaving again; buses on their routes, stopping at shelters;
  taxis at their stands; rush hour and the night's thin traffic by M11's densities.
- Vehicles as kinematic movers on lanes by default; real physics only near the player.
- Their head and tail lights, brake lights and indicators at night (as light through
  atmosgen near the view, emissive beyond).

### 6.6 Transit

- Trains, metro, monorail and maglev sets and sky tube pods on M5's lines to timetables by
  hour, accelerating and braking into stations, doors opening, people boarding and leaving
  from the platforms' walkways.

### 6.7 Air and water

- Flying cars on air lanes in layers above the roads and between towers, landing on AV
  pads and helipads; drones; police and media fliers; aircraft and shuttles over the
  spaceport.
- Boats and water taxis on the canals and rivers by M16's flow, ships at the port, ferries
  between piers.

### 6.8 Reactions

- To the hour and weather: nightlife, empty streets at dawn, umbrellas and shelter under
  awnings and decks in rain (atmosgen's rain shadow).
- To the player: stepping aside, looking, moving away from danger. Anything deeper
  (combat, dialogue) is not lifegen's.

## 7. Outputs (canonical)

As in 4.2. Every plan entry carries the id of what it belongs to, its tile and the hash of
its inputs, so a district regeneration changes only its district's and seam's entries. The
library carries the hash of its spec styles and its code; an unchanged library is not
built again.

## 8. Checks (every run; a failure means the plan is not delivered)

- **Reachability:** every trip's origin reaches its destination on the walkway or lane
  graph at its level; every spawn point is on a walkway or lane.
- **Densities:** the plan's people and vehicles per street and hour band within a
  tolerance of M11's.
- **Placement:** no spawn, slot or parked vehicle inside a building, prop or plant (AG14's
  fit data), every slot facing its object.
- **Signals:** no two conflicting movements green at once; every crosswalk served; cycle
  times within limits.
- **Timetables:** dwell and run times feasible for the line's length, curves and speeds;
  no two trains closer than their headway.
- **Air and water lanes:** clear of buildings, masts, sky tubes and bridges by their
  margins; every pad reachable; boats in water deep enough (M16's beds).
- **Variety:** no two people within 50 m alike in body, face and outfit; no outfit more
  than a set share of a district; the library's people by style.
- **Budgets:** people and vehicles live per cell and within the view range, full-detail
  characters near the view, against the runtime budget (section 9).

## 9. Unreal, hardware and performance

- **Where it runs:** Unreal checks and sign-off on the Windows PC, as the second
  run-through did; the plugin builds there with Visual Studio 2022 as `CityGenPlay` does.
  The Mac builds the plan and the library, runs the checks and the Blender previews.
- **Baseline:** AG16's benchmark (`--bench`), by day and by night, before LG0 and after every
  LG milestone. AG16's scope already gives lifegen's crowds and traffic (game thread, CPU)
  a pass of their own.
- **Scale:** up to 2,000 simulated people and 500 vehicles within 300 m, 150 to 250 people
  at full detail (the goal). The frame budget is 20 ms p95 at native 2560 x 1440 on the PC
  (decision 12.7): no tuning rounds unless a milestone goes over it.
- **Engine pieces:** Mass Entity, Mass Crowd, ZoneGraph, Smart Objects, StateTree,
  Motion Matching, AnimToTexture (baked animation for far crowds), Mutable, Chaos Cloth,
  Chaos Vehicles near the player. Which of them are experimental in 5.8 is LG0's to check.

## 10. Determinism and scale

The plan and the library are deterministic (blake2b draws from ids and seeds, canonical
JSON, hashed meshes; Blender's cloth drape is baked once and its result hashed, so a
library is rebuilt only when its inputs change). The simulation in Unreal is not, and
nothing downstream depends on its exact frames.

## 11. Out of scope

The player's own character and controls; combat, dialogue, quests and story events
(storygen); people inside buildings beyond their doors (AG11, interiors); sound; driving
by the player (a later option); seasons.

## 12. Decisions (Swagnik, 2026-11-13)

1. **The shape:** a generator of the plan and a library, with the `CityGenLife` runtime
   plugin on Unreal's Mass, ZoneGraph, Smart Objects and StateTree. Decided as recommended.
2. **Bodies and faces:** MetaHuman, if 5.8's tools can be driven from a script (LG0 found
   out: `docs/progress/LG0/README.md`), made by script into the user's project, never the
   repo. Fully generated bodies (CyberGen's own) only if that fails.
3. **Clothing:** generated garments from sewing patterns draped in Blender's cloth solver
   (6.2; LG0 draped a test garment), with an authored or bought base kit kept out of the repo
   as the fallback.
4. **Animation:** both. Epic's Game Animation Sample near the view (in the user's project,
   never the repo) and free motion capture libraries (CMU-style, licenses that let anyone
   use them) for the rest, retargeted to the bodies.
5. **Third-party content:** nothing goes in the repo unless its license lets anyone use it.
   A user's own content (MetaHumans, Fab clothing, Epic's animation) is imported into their
   project by a step they run once.
6. **Vehicles (changed from the draft):** the fleet is AG18's hand-designed vehicles
   (`vehicles/`, game packs fetched by `vehicles/packs.py`), moving and parked. The kinds the
   roster lacks (buses, trucks, motorbikes, bikes, flying cars, drones, boats) are designed
   on the Mac the same way. lifegen generates no vehicle geometry (6.5).
7. **Budget (changed):** the frame budget for lifegen is **20 ms p95** at native 2560 x 1440
   on the PC for now (atmosgen held 16.7 ms; Delta's night was 15.0 ms after AT7). "Instead
   of wasting time optimizing at every step, we can allow a larger budget and then optimize
   later as needed": no tuning rounds unless a milestone goes over 20 ms. The people and
   vehicle counts of section 9 stay the goal.
8. **Reactions:** stepping aside and looking first; fleeing and gathering later, as a hook
   for storygen.

## 13. Milestones

| | Milestone | Adds | Needs |
|---|---|---|---|
| LG0 | Groundwork and spike (done, 2026-11-13) | life spec and styles, plan format, the asks of citygen; the `CityGenLife` plugin's skeleton with ZoneGraph lanes built from the graphs; plain stand-in people walking one district of Delta and a few cars on its lanes, measured with AG16's benchmark; what MetaHuman and Mutable can do from a script in 5.8; a garment draped in Blender's cloth solver as a test | AG16 |
| LG1 | People | the population library: bodies, faces, skin and hair by seed, the animation set retargeted, LODs and far stand-ins (baked animation, impostors), assembly (Mutable or lifegen's merge); people in a plain base outfit | LG0 |
| LG2 | Clothing | garments from sewing patterns draped in Blender, generated textiles, accessories and cyberware, outfits by district, group, job, wealth and weather, the variety check, cloth simulation near the view | LG1 |
| LG3 | Crowds on the streets | people on every walkway at each street's density by hour, every level, stairs, escalators and elevators, crosswalks with the signals, groups, pace, avoidance; trips spawned and ended at doors, stations and garages | LG1 |
| LG4 | Life at places | Smart Object slots at benches, stops, stalls, kiosks, vending machines and doors; places by their hours; gangs on their turf, police patrols | LG3 |
| LG5 | Traffic | AG18's fleet (cars and vans now; buses, trucks, motorbikes and bikes as the Mac designs them) on the lanes; signal phases; parking; bus routes; taxis; densities by hour; lights at night | LG0 |
| LG6 | Transit | trains, metro, monorail, maglev and sky tube pods on their lines to timetables, stations, boarding | LG3, LG5 |
| LG7 | Air and water | flying cars on air lanes and pads, drones, police fliers, aircraft over the spaceport, boats, water taxis, ships and ferries | LG5 |
| LG8 | Weather, reactions and release | crowds and traffic by atmosgen's hour and weather (umbrellas, shelter, nightlife), reactions to the player, the crowd and traffic performance pass, every sample city alive, Unreal checks on the PC, README | LG2 to LG7, AT3, AT5 |

Each milestone updates the exporter and the plugin in its own PR and runs AG16's benchmark,
as stages 1 and 2 update the exporter. LG2 and LG3 can run side by side after LG1 (crowds
start in plain clothes), and LG5 (traffic) can run beside the people milestones from LG0.
lifegen can run alongside stage 3; only LG8 waits for atmosgen's hour and weather.
