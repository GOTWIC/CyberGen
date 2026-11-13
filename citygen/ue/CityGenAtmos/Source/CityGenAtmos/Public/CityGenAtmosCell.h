// AT1: one 128 m cell's lights of a city's atmos plan (docs/unreal_export.md, "From AT1" and
// "From AT2"): a data actor the importer places at the cell's middle, spatially loaded, so
// World Partition streams it with its cell (the main grid's 128 m cells). It holds its
// lights' records packed
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
	// door angle in inner), flicker depth; AT2: its animation's period (s), amount (a
	// blink's on share, a sweep's swing in degrees either way) and phase (0 to 1)
	constexpr int32 Floats = 19;
	// ints: flags (bits 0-1 shape: 0 spot, 1 point, 2 rect; 2 may cast shadows; 3 near tier
	// only; 4 on, not broken; 5 no specular, a lit face's stand-in; 6 the high tier (AT2);
	// 8-15 schedule index; 16-23 kind index; 24-27 mount index; 28-29 animation (AT2):
	// 0 none, 1 blink, 2 sweep), seed (a hash of its id)
	constexpr int32 Ints = 2;
	// AT4: a fog volume's floats: its middle x, y, z (cm), yaw (deg), half sizes along its
	// yaw, across and up (cm), density (extinction at its middle, 1/m), floor (the share of
	// it that is height fog), phase g, albedo r, g, b (linear), glow (its emissive's share);
	// ints: flags (bits 0-7 schedule index, 8-15 kind: mist, smog, haze, tunnel_haze,
	// steam_bank)
	constexpr int32 VolFloats = 14;
	constexpr int32 VolInts = 1;
	// AT4: a plume's floats: its foot x, y, z (cm), width, rise (cm), opacity, albedo r, g, b;
	// ints: flags (bits 0-7 schedule index, 8-15 kind: steam, smoke, exhaust, cooking, 16-23
	// mount: manhole, drain, vent, roof, stall, chimney, stove), seed
	constexpr int32 EmitFloats = 9;
	constexpr int32 EmitInts = 2;
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

	/** AT4: its fog volumes, packed (CityGenAtmosPack::VolFloats and VolInts each). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Air")
	TArray<float> VolumeFloats;

	UPROPERTY(EditAnywhere, Category = "CityGen|Air")
	TArray<int32> VolumeInts;

	/** AT4: its steam and smoke plumes, packed (EmitFloats and EmitInts each). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Air")
	TArray<float> EmitterFloats;

	UPROPERTY(EditAnywhere, Category = "CityGen|Air")
	TArray<int32> EmitterInts;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
};
