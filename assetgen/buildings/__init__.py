"""The building line (scope 5.1, AG1 on): genome, split grammar, shells, proxies and simple
collision for every building of a city, from its brief.

- `genome`: district palette (era presets and the asset spec), property family, building
  genes, all drawn from blake2b hashes of ids; the genome distance the uniqueness check uses.
- `systems`: the facade systems AG1 builds (six of scope 5.1.2's set), what every era and
  building type draws from, and the material slots.
- `grammar`: mass -> edges (the brief's facade regions) -> floor rows -> bays -> openings,
  panels, piers and mounts; ring strips for slabs, cornices and parapets.
- `shell`: the shell mesh (closed parts on integer millimeters, triangulated per bay and per
  face, welded on each face plane), roof equipment blocks until AG4.
- `proxy`, `collision`: far proxies (scope 8) and convex collision pieces from the masses.
"""
