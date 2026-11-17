// The instanced HLODs' component (fix_hlod_streaming; docs/unreal_export.md, "HLOD
// streaming"). World Partition hides an HLOD actor while the main cell it stands for is
// shown and shows it again when the cell goes (AWorldPartitionHLOD::SetVisibility, each of
// its components' SetVisibility). The engine's component answers each flip by recreating its
// render state at the end of the frame: a new scene proxy, its instances sent again and its
// materials gathered (UStaticMesh::GetUsedMaterials) on the game thread. A dense HLOD actor
// has hundreds of components and a step across a 128 m cell flips a row of them, 2,000 and
// more in one frame (LG8's slow frames, 50 to 70 ms). This one keeps its proxy and flips only
// whether the scene draws it, on the render thread
// (FSceneInterface::UpdatePrimitivesIsDrawn_RenderThread, as the engine's FastGeo streaming
// does), so a flip costs a render command. The actor's components are attached to its root,
// whose own flip marked every other component's render state dirty (USceneComponent::
// SetVisibility's DirtyOnly propagation): in a game each is taken off the root as it begins
// to play, so each flip touches its own component alone. `citygen unreal` names it the HLOD builder's
// instanced component class (DefaultEditor.ini, [/Script/Engine.HLODBuilder]) when the play
// plugin is built, and builds the level's HLODs again with it.
//
// Console: CityGen.HLODFastVisibility 0|1 (1, the default: the flip above; 0 the engine's
// recreation), CityGen.HLODStatus (the flips each way since the start).

#pragma once

#include "CoreMinimal.h"
#include "WorldPartition/HLOD/HLODInstancedStaticMeshComponent.h"
#include "CityGenHLODComponent.generated.h"

UCLASS(HideDropDown, NotPlaceable)
class CITYGENPLAY_API UCityGenHLODComponent : public UHLODInstancedStaticMeshComponent
{
	GENERATED_UCLASS_BODY()

public:
	/** Flips since the start: drawn in place, by the render state recreated (no proxy yet or
	 *  the fast flip off). */
	static int64 FastFlips;
	static int64 SlowFlips;
	/** The recreated flips by why: the fast flip off, not a game, no render state yet, a
	 *  render state already dirty, no proxy (hidden, shown). */
	static int64 SlowWhy[6];
	/** Components taken off their HLOD actor's root as they began to play. */
	static int64 Detached;

protected:
	virtual void BeginPlay() override;
	virtual void OnVisibilityChanged() override;
};
