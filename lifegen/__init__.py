"""lifegen: CyberGen's stage 4, people, traffic, transit and air (docs/lifegen_scope.md).

A generator of who and what is where, with a simulation in the engine: a deterministic plan
per city (population by district and hour, spawn and sink points, place slots, the fleet's
mix, the asks of citygen) keyed by M10's stable ids, checked, layer 4 of the exporter's
manifest, moved in Unreal by the `CityGenLife` runtime plugin (citygen/ue/CityGenLife) on
Mass and ZoneGraph lanes built from the city's own graphs. It reads citygen's model and
assetgen's outputs, read only.
"""
