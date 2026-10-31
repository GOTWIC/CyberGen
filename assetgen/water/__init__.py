"""AG12, water (scope 5.6, 14.13): every water body's surface, bed and banks as assets.

`assetgen water BUILD` (also a stage of `assetgen build`, after the streets): per water body
and 256 m tile a surface (non-Nanite, a LOD chain, carrying the flow, a foam mask and the
sea's wave weight) and a bed (M16's depth and profile, the banks' slopes under the water,
skirts where two bodies' beds meet), and per bank a piece by its kind (natural slopes,
beaches, marsh edges, riprap with its stones as instanced parts, road embankments, stone
walls along rivers and the sea; AG7 keeps the quays and the canal walls of the waterways).
"""
