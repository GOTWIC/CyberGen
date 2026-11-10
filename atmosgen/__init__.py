"""atmosgen: CyberGen's stage 3, light, sky, air and weather (docs/atmosgen_scope.md).

A generator of light and air, not of geometry: a deterministic plan per city (every light
that casts light, fog and smog volumes, steam emitters, rain shadow and wetness masks, sky
glow, schedules by hour) keyed by M10's stable ids, checked and previewed, layer 3 of the
exporter's manifest, rendered in Unreal by the `CityGenAtmos` runtime plugin
(citygen/ue/CityGenAtmos). It reads citygen's model and assetgen's outputs, read only.
"""
