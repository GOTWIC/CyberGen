# LG2: clothing (lifegen)

Stage 4's clothing milestone (`docs/lifegen_scope.md` 6.2 and section 13): every person of the
city in generated clothing, in all three tiers, city-wide. Garments cut from pattern
parameters on each character's own body and draped in Blender's cloth solver, generated
textiles, accessories and cyberware, outfits drawn by district, group, wealth and weather,
the variety check. Built on the Windows PC (RTX 4070 Ti, 12700K, UE 5.8.4) on 2026-11-14 and
15, on main after LG5 (#230).

## What LG2 built

| Part | Where | What |
|---|---|---|
| Garment patterns and looks | `lifegen/garments.py` | 15 garment kinds (tee, long tee, shirt, hoodie, coveralls, bomber, jacket, trench, raincoat, cargo, trousers, skirt, sneakers, boots, dress shoes) as pattern parameters (parts covered, ease per region by fit, hem, sleeve, neckline, flare, hood, collar, opening, trims); 11 accessories; 10 look groups (`presets.GROUPS` and `rain`) with their outfits, textiles and accessories; 6 looks a character, 144 in all; `draft` cuts a garment for one body's landmarks |
| Textiles | `lifegen/textiles.py` | denim, leather, vinyl, nylon, knit, rib, canvas, wool, mesh, reflective, LED trim, rubber, metal, plastic, visor: tileable PBR sets in AG6's style (integer-hash noise, `pbr.pack`), dyed ones a light weave the person's colors multiply |
| The Blender stage | `lifegen/blender/garments.py` | per character: the mannequin (body, plain outfit and face as one surface), every garment built on it, draped, finished; accessories; each look composed (layers pushed apart, covered faces out) and written as near (LOD 0, 1) and mid meshes; renders |
| The library's build | `citygen/ue/people_library.py`, `citygen/unreal_people.py` | the bodies exported, the clothing dressed in Blender between two editor runs, the looks' skeletal meshes (weights from the body and the plain outfit), mid meshes and cards per look |
| The plan | `lifegen/plan.py`, `presets.py`, `spec.py` | each pool person's look and group (the pool by the city's groups), per district its people by group (and the weather's share in raincoats), its colors per group, its wear; the check `variety` |
| Exporter and runtime | `citygen/unreal_life.py` (`PACK_VERSION` 5), `ue/import_city.py` (`LIFE_VERSION` life6), `CityGenLife` | a person spawned in a district takes a pool slot of a group the district wears and three dye colors of it; near garments tinted per person, mid and far by per-instance data and the cards' dye mask |

## How a garment is made

The scope's plan was flat sewing panels hung round the body and sewn shut by the cloth
solver's springs, as LG0's tee was. That tee crumpled wherever its one-size cut and the body
disagreed; cutting flat panels to fit 24 bodies of every build (and pants round a crotch) by
springs is fragile. So a garment is **cut from its pattern on the body it dresses** and the
cloth solver drapes it from there (`lifegen/blender/garments.py`):

1. **The mannequin.** The character's assembled body has no skin under MetaHuman's plain tee
   and shorts (the creator's assembly takes those triangles out), so the body, the plain
   outfit and the face's skin become one closed surface (a voxel remesh at 9 mm, about 15,000
   faces); every vertex is labelled with its part (torso, neck, head, upper and lower arm,
   hand, thigh, calf, foot: the nearest bone segment less the part's own radius) and its
   place along it. The plain outfit's openings are measured too (its neck opening, sleeve
   ends, leg hems): the body has no skin inside them, so every look reaches past each.
2. **The pattern** (`lifegen/garments.py`, `draft`): the parts a garment covers, its ease per
   region (fitted to loose by the look's draw; an outer layer always looser than any base
   layer), its cuts by the body's landmarks (hem, sleeve and ankle lengths, the neckline at
   the plain outfit's, a front opening), a skirt's or coat's flare, a hood (up: an ellipsoid
   open at the face; down: a roll), a collar (stand or turned down), trims (ribbed cuffs and
   hems, zips, plackets, pockets, reflective and LED bands, soles).
3. **The build**: the mannequin's faces of those parts offset by the ease (at most 45% of the
   room to the next part, so arms and legs keep apart), smoothed over the body's hollows and
   held outside it, cut by the pattern's planes on the parts each belongs to; the panels'
   coordinates round each part and along it (meters) are the UVs, so a textile lies on the
   garment as on its pattern piece.
4. **The drape**: Blender's cloth solver (28 frames, gravity on, the mannequin a collision
   object) settles it, fitted parts held by goal springs, skirts, coat tails and hoods free; a
   drape that throws vertices is dropped.
5. **The finish**: a rim of the textile's thickness at every open edge, the trims as their own
   slots, the vertex colors (a multiplier, and in alpha the dye channel: base layer, outer
   layer, bottom, or none for fixed colors such as soles, police blue, metal).
6. **The look**: its garments and accessories joined; each layer pushed 4 mm outside the
   layers under it (shoes, bottoms, the base top, the outer layer; a tucked shirt under its
   trousers), the faces another layer covers taken out; written as the near mesh (LOD 0,
   about 17,000 to 27,000 triangles), LOD 1 (45%) and the mid mesh (4,500 triangles, the
   textiles' mean colors in its vertex colors).

Accessories are hard-surface, built on the head's measures (visor, respirator, mask,
headset, cap, beanie, hard hat, implant plates with a glowing line) or the torso (backpack,
bag), held rigidly to their bone (head, spine_04, spine_02); arm plates (cyberware with a
glowing seam) follow the forearm's skin and only on bare forearms. A hood up is held to the
head more the higher it goes. Looks with a hood up, a cap, a beanie or a hard hat leave the
hair out.
