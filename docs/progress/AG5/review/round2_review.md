# Art direction (assets): Vesper Bay, round 2 of at most 3

Checks: all passed.

## Spec changes since the last round

- `districts.The Stacks.systems.capsule_stack: 0.2 -> 0.45`
- `districts.The Stacks.wear: 1.1 -> 1.3`
- `eras.heritage.crowns: added ["pitched", "pitched", "pagoda_roof", "parapet"]`
- `owners.aurum_bank.brand_colors: ["#2b2d42", "#d4af37"] -> ["#2b2d42", "#5c5446", "#d4af37"]`
- `owners.orbis_logistics.brand_colors: ["#1d3557", "#f1a208"] -> ["#1d3557", "#4a5568", "#f1a208"]`
- `owners.sable_systems.brand_colors: ["#0b0b0f", "#c1121f"] -> ["#0b0b0f", "#3a3d44", "#c1121f"]`

## City

| Number | This round | Last round |
|---|---|---|
| buildings | 5793 | 5793 |
| triangles_m | 34.5 | 34.5 |
| instances_m | 1.3 | 1.29 |
| heroes | 1 | 1 |
| type_features | 8170 | 8276 |
| on_slopes | 0 | 0 |

## Districts

| District | Buildings | Eras | Facade systems (body) | Type generators (buildings) | Wear |
|---|---|---|---|---|---|
| Corporate Core | 201 | corporate_glass 100% | unitized_curtain_wall 44%, spandrel_ribbon 21%, fin_wall 17% | terraced 15, parking 5, hero.megatower 1 | 0.13 |
| Highcrest | 586 | suburban_modern 100% | stucco_shutters 59%, precast_panel 32%, timber_infill 10% | villa 561, terraced 9 | 0.16 |
| Launch Key | 18 | aerospace 100% | hangar_cladding 56%, - 11%, punched_concrete 11% | hangar 9, parking 2, control_tower 1, shed 1 | 0.36 |
| Neon Strand | 1814 | neon_retro 100% | precast_panel 32%, shanty_patchwork 32%, punched_concrete 19% | shanty 516, straddle 2 | 0.9 |
| Old Town | 2921 | heritage 100% | shanty_patchwork 43%, punched_brick 25%, stucco_shutters 18% | shanty 1251, temple 3, pagoda 1 | 1.08 |
| Scholar Isle | 57 | clean_tech 100% | perforated_skin 42%, unitized_curtain_wall 26%, fin_wall 14% | lab 39, terraced 7 | 0.14 |
| The Stacks | 102 | brutalist 100% | precast_panel 48%, board_marked_concrete 35%, punched_concrete 16% (was precast_panel 43%, board_marked_concrete 34%, punched_concrete 22%) | megablock 81 | 0.81 (was 0.72) |
| Vess Docks | 94 | industrial 100% | corrugated 54%, standing_seam 16%, - 15% | warehouse 55, yard 23, shed 14, gatehouse 1 | 1.03 |

## Previews to open

- `previews_ag6/iso_d01.jpg`: a district textured by day: eras, systems, colours, signs
- `previews_ag6/iso_d02.jpg`: a district textured by day: eras, systems, colours, signs
- `previews_ag6/iso_d04.jpg`: a district textured by day: eras, systems, colours, signs
- `previews_ag6/iso_d07.jpg`: a district textured by day: eras, systems, colours, signs
- `previews_ag6/street_4.jpg`: street level, textured: fronts, signs, props, wear

## If something reads wrong, change the asset spec (never the code)

| What you see | Spec parameters |
|---|---|
| a district in the wrong era (heritage where it should be corporate glass ...) | `districts.<name>.era` |
| a district's facades too uniform, or the wrong facade systems | `districts.<name>.systems, eras.<era>.systems` |
| too clean or too worn, too little or too much grime | `districts.<name>.wear, eras.<era>.wear` |
| too many or too few signs and ads | `districts.<name>.ad_density` |
| the neon colours of a district | `districts.<name>.neon_palette` |
| signs in the wrong scripts | `districts.<name>.signage_scripts, eras.<era>.signage_scripts` |
| too much or too little glass | `eras.<era>.window_to_wall` |
| bays too wide or too narrow | `eras.<era>.bay_m` |
| wall and trim colours off for an era | `eras.<era>.palette` |
| the wrong crowns on the towers (flat, stepped, spire, halo ...) | `eras.<era>.crowns` |
| an owner's buildings not reading as one brand | `owners.<owner>.brand_colors, owners.<owner>.facade_bias` |
| a landmark off its brief (colours, crown) | `landmarks.<name>.palette, landmarks.<name>.crown, landmarks.<name>.brief` |
| neighbours too alike | `min_gene_distance` |

Stop when the checks pass and the previews match the prompt (and the concept image), or after the last round; say what is still off.
