# M10 WIP 01: district regeneration

Vesper Bay built, then `citygen build cities/vesper_bay/city_spec.json OUT --base BUILD
--district "Neon Strand"` (a new seed for the district): 46.5 s on the Mac (3 workers), all 75
checks pass, all 2136 held road segments (border roads and everything outside the district)
come back byte for byte. Entities outside the district that change are on its seam: the
junctions where its new streets meet the held roads and what hangs on them.

Stable ids are in place (one renaming pass, `citygen/ids.py`); goldens not regenerated yet.
