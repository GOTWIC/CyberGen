// lifegen's runtime controller (docs/lifegen_scope.md 4.2, docs/unreal_export.md "lifegen's
// runtime (LG0)"): one actor per city level, always loaded, placed by the importer with the
// life plan's spike (one district: its walkway lanes and drive lanes from the city's graphs,
// how many people and cars, AG18's car meshes and paint). At BeginPlay it builds ZoneGraph
// lanes from those graphs (an AZoneGraphData of its own, registered with the world's ZoneGraph
// subsystem: no hand-drawn shapes), makes the people and cars entities of the world's Mass
// entity manager and runs its processors each tick (UCityGenLifeWalkProcessor,
// UCityGenLifeDriveProcessor); the people are plain stand-ins (an instanced body and head in a
// color per person), the cars instanced parts of AG18's packs in their paint. LG1 to LG8 grow
// it: spawning by tile and hour, crowds, places, traffic by the signals, transit, air and
// water. Frames: the graphs in citygen meters (x east, y north, z up), Unreal cm (X east, Y
// south).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Mass/EntityHandle.h"
#include "CityGenLifeProcessors.h"
#include "CityGenLifeActor.generated.h"

class AZoneGraphData;
class UAnimSequence;
class UInstancedStaticMeshComponent;
class USkeletalMesh;
class USkeletalMeshComponent;
class UStaticMeshComponent;
class UMaterialInterface;
class UStaticMesh;
class UCityGenLifeWalkProcessor;
class UCityGenLifeDriveProcessor;

UCLASS()
class CITYGENLIFE_API ACityGenLife : public AActor
{
	GENERATED_BODY()

public:
	ACityGenLife();

	static ACityGenLife* Find(const UWorld* World);

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void Tick(float DeltaSeconds) override;

	// --- the plan (set by the importer) -----------------------------------------------------

	UPROPERTY(EditAnywhere, Category = "CityGen") FString City;
	UPROPERTY(EditAnywhere, Category = "CityGen") FString PlanHash;
	UPROPERTY(EditAnywhere, Category = "CityGen") FString DistrictId;
	UPROPERTY(EditAnywhere, Category = "CityGen") int32 People = 0;
	UPROPERTY(EditAnywhere, Category = "CityGen") int32 Cars = 0;
	/** The live region: the spike's middle (citygen m) and radius (m). */
	UPROPERTY(EditAnywhere, Category = "CityGen") FVector2D Center = FVector2D::ZeroVector;
	UPROPERTY(EditAnywhere, Category = "CityGen") float RadiusM = 450.f;
	/** People and cars are densest round the middle: a lane's share falls as
	 *  1 / (1 + (d / CrowdFalloffM)^2) with its distance d (m). */
	UPROPERTY(EditAnywhere, Category = "CityGen") float CrowdFalloffM = 150.f;
	UPROPERTY(EditAnywhere, Category = "CityGen") FVector2D WalkSpeed = FVector2D(1.15, 1.55);
	UPROPERTY(EditAnywhere, Category = "CityGen") FVector2D DriveSpeed = FVector2D(7.0, 11.0);
	UPROPERTY(EditAnywhere, Category = "CityGen") float CarGapM = 9.f;

	/** Walkway lanes (flat, as graphs.json's): lane i has points [WalkStarts[i],
	 *  WalkStarts[i + 1]) of WalkPoints (x, y, z, citygen m) and links [WalkLinkStarts[i],
	 *  WalkLinkStarts[i + 1]) of WalkLinks, each 2 * lane + (1 where it meets this lane's end,
	 *  0 its start). */
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> WalkPoints;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> WalkStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> WalkWidths;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> WalkLinks;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> WalkLinkStarts;
	/** Drive lanes (lanes and junction connectors), directed: links are successors. */
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> DrivePoints;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> DriveStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> DriveWidths;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> DriveLinks;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> DriveLinkStarts;
	/** 1 where a drive lane is a lane a car may start on (not a junction connector). */
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<uint8> DriveStartable;
	/** cars_steam: per drive lane point the speed a car may drive at (m/s: its road's class,
	 *  slower through a junction, at most what its bend allows, braking before it), per lane
	 *  its cruise speed, and a car's share of it (by hash); empty: `DriveSpeed` as in LG0. */
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> DriveVmax;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> DriveCruise;
	UPROPERTY(EditAnywhere, Category = "CityGen") FVector2D DriveVary = FVector2D(0.9, 1.08);

	/** The stand-ins: a body and a head, colors per person by their style's palette (linear
	 *  RGB, 3 floats a color). */
	UPROPERTY(EditAnywhere, Category = "CityGen") TObjectPtr<UStaticMesh> BodyMesh;
	UPROPERTY(EditAnywhere, Category = "CityGen") TObjectPtr<UStaticMesh> HeadMesh;
	UPROPERTY(EditAnywhere, Category = "CityGen") TObjectPtr<UMaterialInterface> StandInMaterial;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> Palette;
	/** The cars: every part of every model (its mesh, model index, pivot in the car's frame:
	 *  citygen m, x forward), each car's model and paint (9 floats: AG18's three linear
	 *  colors, per-instance custom data). */
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<TObjectPtr<UStaticMesh>> CarPartMeshes;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> CarPartModels;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> CarPartPivots;
	/** 1 where a part casts shadows (a body, not its glass or wheels: AG18's rule). */
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<uint8> CarPartShadows;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<int32> CarModels;
	UPROPERTY(EditAnywhere, Category = "CityGen") TArray<float> CarPaints;
	UPROPERTY(EditAnywhere, Category = "CityGen") int32 PaintFloats = 9;

	// --- LG1: the people library (set by the importer from the project's library) -------------
	// Each person is a character of the library (PersonChar, drawn by the plan from its seed)
	// drawn by the view's distance: near (NearM, at most NearMax of them) as the assembled
	// MetaHuman's skeletal meshes playing its gait's clip at its pace; mid (MidM) as the
	// character's walk baked into textures (AnimToTexture: one instanced static mesh per
	// character, its frame from per-instance custom data); far (FarM) as an impostor card
	// showing the walk from its side. Without a library (no MidMeshes) LG0's stand-ins.

	/** Per character its near skeletal meshes, flat: [NearMeshStarts[c], NearMeshStarts[c + 1])
	 *  of NearMeshes, the first the leader (the body), the rest following its pose. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<USkeletalMesh>> NearMeshes;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<int32> NearMeshStarts;
	/** Per character its hair as a static mesh of its groom's cards (in the face's frame at
	 *  its reference pose), carried on the face's head bone; null for none. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<UStaticMesh>> NearHair;
	/** Per character which of its near meshes carries the hair (the face: 1). */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") int32 HairOn = 1;
	/** Per character its clip group (characters on one body skeleton share their clips):
	 *  its walks are WalkClips[group * Gaits + gait]. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<int32> CharClipGroup;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") int32 Gaits = 2;
	/** The walk clips (per gait) on the characters' body skeleton, and the speed (m/s) each
	 *  walks at its own rate. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<UAnimSequence>> WalkClips;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<float> WalkClipSpeeds;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<UAnimSequence>> IdleClips;
	/** Per character its mid mesh (the baked walk) and 4 floats: the walk's first and last
	 *  baked frame, the bake's frames a second, the walk cycle's length (s). */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<UStaticMesh>> MidMeshes;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<float> MidFrames;
	/** The far cards: one quad (a person's height, standing on its origin), per character its
	 *  impostor sheet's material. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TObjectPtr<UStaticMesh> CardMesh;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<UMaterialInterface>> CardMaterials;
	/** The tiers (m from the view) and how many people may be near at once. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") float NearM = 30.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") int32 NearMax = 160;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") float MidM = 90.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") float FarM = 300.f;
	/** The skeletal meshes' yaw in their own frame (MetaHumans face +Y: -90). */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") float MeshYaw = -90.f;
	/** Per person (the plan's draws): character, height scale, gait (into WalkClips), pace
	 *  (m/s), the outfit's tint (3 floats, linear RGB) and seed. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<int32> PersonChar;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<float> PersonScale;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<int32> PersonGait;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<float> PersonPace;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<float> PersonTint;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<int32> PersonSeed;

	/** Whether the people library is in use (else LG0's stand-ins). */
	bool HasPeople() const { return MidMeshes.Num() > 0 && NearMeshStarts.Num() == MidMeshes.Num() + 1; }
	/** The tiers at run time (CityGenLife.Tiers NEAR_M NEAR_MAX MID_M FAR_M). */
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetTiers(float InNearM, int32 InNearMax, float InMidM, float InFarM);

	// --- the session --------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, Category = "CityGen") bool bEnabled = true;
	/** How many entities have their ground found each frame (a line trace each). */
	UPROPERTY(EditAnywhere, Category = "CityGen") int32 TracesPerFrame = 96;

	/** Whether the stand-ins and the cars' bodies cast shadows. */
	UPROPERTY(EditAnywhere, Category = "CityGen") bool bShadows = true;
	/** Whether each frame's move also recreates the instanced components' render state (the
	 *  engine's MarkRenderStateDirty); off, the moves reach the GPU scene through the
	 *  components' instance data alone. */
	UPROPERTY(EditAnywhere, Category = "CityGen") bool bRebuildRenderState = false;
	/** Whether the instanced people and cars are in Lumen's scene and the distance fields
	 *  (off: they take Lumen's light but give none back, as characters in games). */
	UPROPERTY(EditAnywhere, Category = "CityGen") bool bInLumen = false;

	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetEnabled(bool bOn);
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetShadows(bool bOn);
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetLumen(bool bOn);
	UFUNCTION(BlueprintCallable, Category = "CityGen") void Respawn(int32 InPeople, int32 InCars);
	/** The state as one JSON line (lanes, entities, the game thread's time in the actor). */
	UFUNCTION(BlueprintCallable, Category = "CityGen") FString GetStatus() const;

private:
	void BuildLanes();
	void SpawnAll();
	void ClearEntities();
	void MakeComponents();
	void UpdateInstances();
	void FindGround();
	// (LG1, CityGenLifePeople.cpp)
	void MakePeople();
	void SpawnPeople(int32 NP);
	void UpdatePeople();
	bool ViewPoint(FVector& Out) const;
	void Release(int32 Slot);
	void Assign(int32 Slot, int32 Person);
	float WalkRate(int32 Person) const;
	float PhaseOffset(int32 Person) const;

	/** A near person's components: the leader (the body) and its followers. */
	struct FNearSlot
	{
		TArray<USkeletalMeshComponent*> Comps;
		UStaticMeshComponent* Hair = nullptr;
		int32 Person = INDEX_NONE;
		int32 Char = INDEX_NONE;
		int32 Gait = INDEX_NONE;
	};
	TArray<FNearSlot> NearSlots;
	UPROPERTY(Transient) TArray<TObjectPtr<USkeletalMeshComponent>> NearComps;
	UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> HairComps;
	UPROPERTY(Transient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> MidComps;
	UPROPERTY(Transient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> FarComps;
	TArray<int32> PersonInst, PersonSlot, CharCount;
	TArray<uint8> PersonTier;
	TArray<TArray<FTransform>> MidXf, FarXf;
	TArray<TPair<float, int32>> NearCand;
	int32 NearNow = 0, MidNow = 0, FarNow = 0;
	double PeopleMs = 0.0;

	UPROPERTY(Transient) TObjectPtr<AZoneGraphData> Lanes;
	UPROPERTY(Transient) TObjectPtr<UInstancedStaticMeshComponent> Bodies;
	UPROPERTY(Transient) TObjectPtr<UInstancedStaticMeshComponent> Heads;
	UPROPERTY(Transient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> CarParts;
	UPROPERTY(Transient) TObjectPtr<UCityGenLifeWalkProcessor> WalkProc;
	UPROPERTY(Transient) TObjectPtr<UCityGenLifeDriveProcessor> DriveProc;

	FCgLifeFrame Frame;
	TArray<float> Lengths, Widths;
	TArray<float> PointVmax;       // (cars_steam: per storage point, cm/s; walkways 0)
	TArray<uint8> InRegion;
	TArray<int32> CarStarts;
	TArray<FVector> WalkPos, CarPos;
	TArray<float> WalkYaw, CarYaw, WalkZ, CarZ;
	TArray<int32> CarModelCount, CarInstance, CarOf;
	TArray<FMassEntityHandle> Entities;
	TArray<FTransform> Scratch;
	int32 TraceCursor = 0;
	int32 WalkLaneCount = 0, DriveLaneCount = 0;
	bool bBuilt = false;
	double TickMs = 0.0, TickMsMax = 0.0;
	int64 Ticks = 0;
};
