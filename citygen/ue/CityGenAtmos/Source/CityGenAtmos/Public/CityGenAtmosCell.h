// AT1: one 128 m cell's lights of a city's atmos plan (docs/unreal_export.md, "From AT1"): a
// data actor the importer places at the cell's middle, spatially loaded, so World Partition
// streams it with its cell (the main grid's 128 m cells). It holds its lights' records packed
// (no light component of its own) and registers them with the level's CityGenAtmos
// controller while it is loaded; the controller's pooled live set renders the nearest.
// Frames: Unreal cm, X east, Y south.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CityGenAtmosCell.generated.h"

/** The packed record of one light: CityGenAtmosCell::Floats floats and Ints ints. */
namespace CityGenAtmosPack
{
	// floats: x, y, z (cm), pitch, yaw (deg; the light's +X along its aim), width, height
	// (cm, a rect's), source radius (cm), intensity (cd for a spot or point, nits for a
	// rect), r, g, b (linear), reach (cm), inner, outer (deg, a spot's cones; a rect's barn
	// door angle in inner), flicker depth
	constexpr int32 Floats = 16;
	// ints: flags (bits 0-1 shape: 0 spot, 1 point, 2 rect; 2 may cast shadows; 3 near tier
	// only; 4 on, not broken; 8-15 schedule index; 16-23 kind index; 24-27 mount index),
	// seed (a hash of its id)
	constexpr int32 Ints = 2;
}

UCLASS(HideCategories = (Input, Replication, Rendering, Collision, HLOD, Physics, Networking,
	LevelInstance, DataLayers, Cooking))
class CITYGENATMOS_API ACityGenAtmosCell : public AActor
{
	GENERATED_BODY()

public:
	ACityGenAtmosCell();

	/** The cell's name (`<tile>.<quarter>`, citygen's 256 m tile and its 128 m quarter). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	FString Cell;

	/** How many lights it holds. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	int32 Count = 0;

	/** Its lights' packed floats (CityGenAtmosPack::Floats each). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<float> LightFloats;

	/** Its lights' packed ints (CityGenAtmosPack::Ints each). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<int32> LightInts;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
};
