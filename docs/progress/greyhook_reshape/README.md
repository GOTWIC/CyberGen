# Greyhook reshape

Greyhook's coastline is reshaped to be more natural and interesting: a peninsula that fans out
into headlands. A new spec option, `water.coast.headlands` (2 to 5, peninsula only), gives a
shallow mainland strip, a short neck, then that many splayed headlands with a U-shaped cove
between each two. Greyhook (3.6 x 3.6 km) takes three: Lantern Strip on the west headland, Hook
Spaceport on the long middle one, Eastside Docks round the east cove, The Stacks on the body
where they meet, two islets (Gull Rock, Hook Islet) as parks. Other cities are unchanged.

<img src="peninsula_city/render_iso_city.jpg" width="840">

| Districts, streets and lots | Buildings |
|---|---|
| <img src="peninsula_city/preview_map.png" width="420"> | <img src="peninsula_city/preview_massing.png" width="420"> |

- Build: `peninsula_city/` (every preview, `report.txt`, `trace.json`, `blockout_report.txt`,
  8K `render_iso_city.jpg`, `city.lock.json`).
- Shapes tried (`wip/02_candidates/`): three headlands with islets (kept), four headlands (Lantern
  Strip and the spaceport each split over two lobes), three headlands on a wider 4.0 km map
  (mostly more empty sea).
- The spine now crosses the Neckwater on Wallgate Bridge beside the north exit: there is no
  room there for an immersed tube's approaches. The earlier layout, with its tube, is the test
  fixture `tests/data/peninsula_round_tip.json`.
- Sweep at Greyhook's seeds: [`sweep.md`](sweep.md), compared below with M10's.
