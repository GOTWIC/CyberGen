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
#include "CityGenLifePlaces.h"
#include "CityGenLifeActor.generated.h"

class AZoneGraphData;
class UAnimSequence;
class UInstancedStaticMeshComponent;
class USkeletalMesh;
class USkeletalMeshComponent;
class UStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
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
	/** lifegen_people_fixes: how fast a person turns (deg/s) and how far its walkway's
	 *  corners are rounded (m along each leg at most). */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") float TurnDegS = 270.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") float CornerM = 1.5f;
	/** The far cards: one quad (a person's height, standing on its origin), per character its
	 *  impostor sheet's material. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TObjectPtr<UStaticMesh> CardMesh;
	/** The cells of a sheet's stride (the library's impostor frames). */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") int32 CardFrames = 8;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<UMaterialInterface>> CardMaterials;
	/** people_idles (the places' second bakes, `citygen/ue/people_places.py`): per character
	 *  4 floats, the first and last frame of its standing idle and of its sitting loop in that
	 *  bake; its mid mesh's slots' materials reading it ([MidIdleStarts[c], MidIdleStarts[c +
	 *  1]) of MidIdleMaterials); the still cards' cells (6 floats: the walk's first cell and
	 *  cells, the sitting poses', the standing idle's), CardMaterials then the still sheets'.
	 *  Empty: a mid or far person standing or sitting holds its walk's passing pose. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<float> MidStillFrames;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<TObjectPtr<UMaterialInterface>> MidIdleMaterials;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<int32> MidIdleStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TArray<float> CardCells;
	/** Whether the mid tier has the idles' bakes (then a sitter is drawn by its tier, not near
	 *  out to MidM). */
	bool HasMidIdles() const { return MidStillFrames.Num() >= 4 * MidMeshes.Num() && MidMeshes.Num() > 0 && MidIdleStarts.Num() == MidMeshes.Num() + 1; }
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

	/** A debug switch until LG2's garments (lifegen_clothing_toggle): off, the people's clothes
	 *  are not drawn. The creator's assembled bodies have no triangles under their garments, so
	 *  near, each person's body and outfit are hidden and WholeBody (MetaHuman's whole template
	 *  body, in the character's own skin material) follows its pose, its face and hair kept,
	 *  and the near tier reaches out to MidM (at most NearMax people); mid, past that cap, the
	 *  baked mesh's garment slots are drawn with HiddenMaterial (the body under them is
	 *  missing there too); the far cards keep their clothes (their sheets were captured clothed).
	 *  On by default. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") bool bClothing = true;
	/** A material that draws nothing (masked, its mask 0): the importer's
	 *  Core/Life/M_CgLifeHidden, for the mid mesh's garment slots while bClothing is off. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TObjectPtr<UMaterialInterface> HiddenMaterial;
	/** MetaHuman's whole template body (the importer's /MetaHumanCharacter/Body/IdentityTemplate/
	 *  SKM_Body), drawn near in place of a person's body while bClothing is off. */
	UPROPERTY(EditAnywhere, Category = "CityGen|People") TObjectPtr<USkeletalMesh> WholeBody;
	/** The clothing switch at run time (CityGenLife.Clothing [0|1], the play menu's row). */
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetClothing(bool bOn);
	/** Whether the people are drawn unclothed now (the switch off, with a HiddenMaterial). */
	bool Unclothed() const { return !bClothing && HiddenMaterial != nullptr; }

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

	// --- LG3: the city's crowd (set by the importer from the plan's crowd) --------------------
	// Every walkway of the city is a lane (WalkPoints ... as above, the whole walkway graph,
	// every kind and level). The plan gives each its people per hour band (WalkPeople, 5 a lane)
	// and its district (WalkDistrict), whose day shapes the hours within a band
	// (DistrictShape, 24 a district). Round the view every walkway within LiveM is live: it
	// gets its people when it comes alive (past the far tier, so never in sight), loses them
	// when it goes; the rest of the city is a number per walkway. At most People (the pool,
	// each slot a person of the plan's draws) live at once: past that the density is scaled
	// down evenly. People come out of doors and go in at them (Door*), walk in groups, wait
	// at the signals of the crosswalks (WalkSignal, SignalWindows), keep right and out of
	// each other's way and the player's.

	/** Per walkway lane its kind (lifegen's WALK_KIND_CODES), district (-1 none), people per
	 *  hour band (5 floats) and signal window (-1 none; 4 floats each in SignalWindows: the
	 *  cycle, its offset, when people may start crossing, from and to, s). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<uint8> WalkKinds;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<int32> WalkDistrict;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> WalkPeople;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<int32> WalkSignal;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> SignalWindows;
	/** Per district its day (24 floats, each band's hours averaging 1), danger (0 to 1) and
	 *  clothes' colors (PaletteSize linear RGB colors). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DistrictShape;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DistrictDanger;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DistrictPalettes;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") int32 PaletteSize = 24;
	/** Per pool slot its tint's index into its district's palette (where it comes out). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<int32> PersonTintIndex;
	/** LG2: per pool slot its look's group (a person is spawned in a district by the
	 *  district's people by group, DistrictGroups, OutfitGroupCount floats each); per district
	 *  and group the colors a person's three dye channels draw from (OutfitColors linear RGB
	 *  colors each) and per district its wear (0 new, 1 worn). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<int32> PersonGroup;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> OutfitPalettes;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") int32 OutfitColors = 0;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") int32 OutfitGroupCount = 0;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DistrictGroups;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DistrictWear;
	/** The doors (spawn and sink points: AG3's doors, station stairs, garages, taxi stands):
	 *  per door its walkway lane, distance along it (m), point (citygen m, on the facade) and
	 *  people a hour coming out at the plan's hour. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<int32> DoorLanes;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DoorDistsM;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DoorPoints;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> DoorRates;
	/** The hour (0 to 23) the crowd lives at; the live radius (m from the view, 3D). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") int32 Hour = 23;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float LiveM = 340.f;
	/** A trip's mean length out of doors (s); the shares of groups of 1 to 5; their spacing. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float TripS = 600.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") TArray<float> GroupShares;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float GroupGapM = 0.9f;
	/** The share crossing against the signal at danger 0 and 1. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") FVector2D Jaywalk = FVector2D(0.01, 0.30);
	/** Avoidance (m): who is ahead, how far a person keeps, from the player, how far from the
	 *  view people avoid at all. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float ReachM = 4.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float PersonalM = 0.75f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float PlayerM = 2.5f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float AvoidM = 90.f;
	/** Stairs (share of the pace), escalators (share, plus m/s), elevators (m/s, hidden). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float StairsShare = 0.6f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") FVector2D Escalator = FVector2D(0.3, 0.5);
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float ElevatorMS = 0.6f;
	/** A multiplier on the plan's density (CityGenLife.Crowd SCALE). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Crowd") float CrowdScale = 1.f;

	/** Whether this is LG3's city crowd (else LG0's and LG1's spike). */
	bool IsCity() const { return WalkLaneCount > 0 && WalkPeople.Num() == 5 * WalkLaneCount; }
	/** The crowd's hour (CityGenLife.Hour H): the live walkways filled again at once. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetHour(int32 InHour);
	/** The density's multiplier (CityGenLife.Crowd SCALE): filled again at once. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetCrowdScale(float InScale);

	// --- LG5: the city's traffic (set by the importer from the plan's traffic) ------------------
	// Every lane and junction connector of the city's lane graph is a drive lane (DrivePoints
	// ... as above, the whole graph). The plan gives each lane its cars per hour band
	// (DriveCars, 5 a lane) and its district (DriveDistrict, whose day DistrictShape holds).
	// Round the view every drive lane within TrafficLiveM is live: it gets its cars when it
	// comes alive (past where they are seen), loses them when it goes, and a car driving onto a
	// lane that is not live leaves there; cars come in on the live lanes far from the view to
	// keep their number. At most TrafficPool cars live at once (each slot a model of AG18's
	// fleet, TrafficSlots), past that the density scaled down evenly. They follow the car in
	// front (the intelligent driver model), stop at red lights (DriveSignal, DriveWindows,
	// DriveStopBack), never drive two crossing connectors of a junction at once
	// (DriveConflicts), never enter a junction without room past it, and stop for people and
	// the player in their way.

	/** Per drive lane: cars per hour band (5 floats), district (-1 none), on the lane graph's
	 *  largest strongly connected part (1), the signal window it stops at (-1 none; 5 floats
	 *  each in DriveWindows: cycle, offset, green from, green to, amber to, s) and where (m back
	 *  from its end), the drive lanes it may not be driven at once with (a connector's
	 *  crossing, merging and leaving connectors: [DriveConflictStarts[l],
	 *  DriveConflictStarts[l + 1]) of DriveConflicts). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> DriveCars;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<int32> DriveDistrict;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<uint8> DriveMain;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<int32> DriveSignal;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> DriveStopBack;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> DriveWindows;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<int32> DriveConflicts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<int32> DriveConflictStarts;
	/** Per pool slot its model (an index of the car models: CarPartModels'); per district its
	 *  fleet (a weight per model) and paints (PaintsPer paints of PaintFloats per model); per
	 *  model its length (m); per part the radius its wheel rolls on (m, 0 none) and how far it
	 *  is drawn (m). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<int32> TrafficSlots;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> TrafficWeights;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> TrafficPaints;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") int32 PaintsPer = 6;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> CarLengths;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> CarPartSpin;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") TArray<float> CarPartCull;
	/** The pool, the live radius (m, 3D), its margin, how far off the view cars come in to keep
	 *  their number (m), a multiplier on the plan's density. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") int32 TrafficPool = 0;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficLiveM = 800.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficMarginM = 60.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficRefillM = 450.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficScale = 1.f;
	/** The car following model (the intelligent driver model): acceleration, comfortable and
	 *  hardest braking (m/s2), the gap kept standing (m), the time headway (s), the free road
	 *  exponent; signals (the hardest braking for an amber); junctions (s waiting before a car
	 *  claims its connector, and before it goes regardless); yielding (m from the view within
	 *  which cars look ahead for people, how far ahead: s of speed, at least and at most m;
	 *  how near their line, m; s people are looked ahead; the gap kept to them, m). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficAccel = 1.8f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficBrake = 2.6f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficBrakeMax = 8.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficGapM = 2.2f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficHeadwayS = 1.2f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float TrafficDelta = 4.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float AmberBrake = 3.5f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float StarveS = 6.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float ForceS = 25.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float YieldM = 180.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float LookS = 1.6f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float LookMinM = 8.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float LookMaxM = 45.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float LateralM = 1.45f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float PredictS = 1.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float YieldMarginM = 2.f;
	/** The traffic on or off (CityGenLife.Traffic [0|1], the play menu's row). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") bool bTraffic = true;

	/** Whether this is LG5's city traffic (else LG0's spike cars). */
	bool IsTraffic() const { return DriveLaneCount > 0 && DriveCars.Num() == 5 * DriveLaneCount && TrafficPool > 0 && TrafficSlots.Num() > 0; }
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetTraffic(bool bOn);
	/** The density's multiplier (CityGenLife.Traffic 1 SCALE): the live lanes filled again. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetTrafficScale(float InScale);
	/** For the check's shots: the camera moved to look at the nearest car stopped at a red
	 *  light with a queue behind it (`red`), stopped for a person (`person`), for the player
	 *  (`player`), or any moving car (`moving`); false when there is none. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool ShowTraffic(const FString& What);
	/** For the check's shots: the walker (the play features' pawn) stood in the lane of the
	 *  nearest moving car ahead of it, as far ahead as it needs to stop; false without one. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool BlockPlayer();
	/** LG3's share of people crossing against the signal at danger 0 and 1 (CityGenLife.Jaywalk). */
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetJaywalk(float AtSafe, float AtDanger);

	// --- LG4: life at places (set by the importer from the plan's places, gangs and police) ------
	// Place slots (benches, bus stops, kiosks, vending machines, food stalls, taxi stands, a
	// club's queue and a bar's smokers at their door, a gang's spots): each use point a Smart
	// Object of the world's Smart Object subsystem while its walkway is live (one slot each, its
	// definition by kind with a UCgPlaceBehaviorDefinition), claimed, occupied and freed through
	// the subsystem as people use it. People walking by a slot that wants users go to a free
	// point, sit, wait, queue, buy, eat, smoke or talk there for a while, and walk on (a club's
	// queue goes in at its door); a walkway coming alive gets its slots' users at once. Shops
	// by their hours: closed doors send no one out and take no one in, an open shop takes a
	// passer-by in for a visit by its chance, who comes back out. Gangs: the pool's gang slots
	// walk only their turf's walkways in groups in their faction's colors and stand at its
	// spots. Police: the pool's police slots walk the patrol walkways in pairs, out of and back
	// in at their station's doors; the traffic's police slots drive the lanes in the livery.

	/** Per slot: its kind (an index into SlotKindNames), walkway lane, distance along it (m),
	 *  use points [SlotPointStarts[s], SlotPointStarts[s + 1]) of SlotPoints (x, y, z, yaw:
	 *  citygen m and degrees), users per hour band (5), stay (2: s), role (CgRole), turf (-1),
	 *  clip (CgAnim - 1: 0 idle, 1 sit, 2 talk), the door a queue goes in at (an index of the
	 *  doors, -1). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<uint8> SlotKinds;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<int32> SlotLanes;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> SlotDists;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<int32> SlotPointStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> SlotPoints;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> SlotUse;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> SlotDwell;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<uint8> SlotRoles;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<int32> SlotTurfs;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<uint8> SlotAnims;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<int32> SlotDoors;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<FString> SlotKindNames;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<FString> SlotKindBehaviors;
	/** Per walkway lane: its gang turf (-1), gang members and police walking per band (5 each),
	 *  whether police patrol it. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<int32> WalkTurf;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> WalkGang;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> WalkPolice;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<uint8> WalkPatrol;
	/** Per turf its faction; per faction its members' dye colors (FactionColors linear RGB). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<int32> TurfFaction;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> FactionPalettes;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") int32 FactionColors = 0;
	/** Per pool slot its role (CgRole: the plan's slots kept for gangs and police). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<uint8> PersonRole;
	/** Per door (as DoorLanes): its people out a hour every hour (24), its place's open hours (24
	 *  bits), a passer-by's visit chance per band (5), a visit's stay (2: s; 0 none), a precinct
	 *  station's door. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> DoorRatesH;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<int32> DoorOpen;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> DoorVisit;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> DoorDwell;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<uint8> DoorPolice;
	/** The gangs' group sizes (shares of 1 to 4). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> GangGroups;
	/** The places' clips per clip group (the library's bodies): a bench's sitting loop, the
	 *  standing idle breaks people talk, smoke and eat by (TalkCount a group). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<TObjectPtr<UAnimSequence>> SitClips;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<TObjectPtr<UAnimSequence>> TalkClips;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") int32 TalkCount = 0;
	/** Where a sitter's root goes from its point (cm: forward along its facing, up). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") FVector2D SitOffset = FVector2D(0.0, 0.0);
	/** people_idles: the bench's sit-downs per clip group (SitInCount a group: from its front,
	 *  its left, its right, behind on its left and on its right) and its stand-up, in the
	 *  seat's frame; per group and sit-down where the stretch a person plays starts (4 floats:
	 *  x, y in cm in the mesh's frame, the turn in degrees, the stretch's length in s; the clips
	 *  walk up from 3 to 4 m off, a person plays the last 1.3 m) and that stretch's start in
	 *  the clip (SitInStart, s), per group where the stand-up's stretch ends. Empty: a sitter
	 *  sits down and stands up at once, as LG4's. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<TObjectPtr<UAnimSequence>> SitInClips;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") int32 SitInCount = 0;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> SitIn;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> SitInStart;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<TObjectPtr<UAnimSequence>> SitOutClips;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> SitOut;
	/** Patrol cars per drive lane and band (5); per traffic pool slot 1 where it is a patrol
	 *  car's; the livery (PaintFloats). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> DrivePolice;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<uint8> TrafficPolice;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") TArray<float> PolicePaint;
	/** The switches (CityGenLife.Places, .Gangs, .Police; the play menu's rows). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") bool bPlaces = true;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") bool bGangs = true;
	UPROPERTY(EditAnywhere, Category = "CityGen|Places") bool bPolice = true;

	/** Whether this is LG4's life at places (else LG3's crowd only). */
	bool IsPlaces() const { return IsCity() && SlotKinds.Num() > 0 && SlotPointStarts.Num() == SlotKinds.Num() + 1; }
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetPlaces(bool bOn);
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetGangs(bool bOn);
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetPolice(bool bOn);
	/** For the check's shots: the camera moved to the nearest person sitting (`sit`), queueing or
	 *  waiting at a slot (`queue`), at a stall or kiosk (`stall`), a gang at its spot (`gang`), a
	 *  police pair walking (`police`), a patrol car (`patrol`); false without one. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool ShowPlace(const FString& What);

	// --- LG6: transit (set by the importer from the plan's timetables) --------------------------
	// Every transit line of the city runs its timetable, driven by the world's time (so where a
	// train is depends on the time alone): a train's place along its line's cycle is the cycle's
	// sampled coordinate at (time + its phase) modulo the cycle, its phases spread evenly round
	// it by the hour band's trains. Its cars follow the track (each car by the track's points at
	// its ends), each way on its own track (its right), crossing over before a turn; they are
	// instanced stand-ins (TransitParts per mode). At a stop the doors open after it halts and
	// close before it leaves; at a stop whose platform walkway is live (LG3's live region) people
	// leave the train through its open doors onto the platform and walk on, and people of the
	// crowd on the platform walk into its doors and are gone. Far trains move as often as the
	// near ones (their place is read off the timetable, not simulated), their instances sent
	// every fourth frame.

	/** Per line: its mode (an index of the modes in TransitPartStarts' order), color (linear RGB),
	 *  loop (1), the train (12 floats: cars, car length, gap, width, height, floor, base over
	 *  the line, track off the middle, doors a side, door width, sides open (1 its right, 2
	 *  both), boarding at the walkway's level), the turn points (2: m along the track), the
	 *  cycle (s) and its samples' step (s), the trains per hour band (5). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitLineMode;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitLineColor;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitLineLoop;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitLineCar;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitLineTurn;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitLineCycle;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitLineDt;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitLineTrains;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<FString> TransitLineIds;
	/** The modes by their index (metro, elevated_rail, monorail, maglev, sky_tube: those the city
	 *  has, in the exporter's order). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<FString> TransitModes;
	/** Per line its track's points [TransitPointStarts[l], TransitPointStarts[l + 1]) of
	 *  TransitPoints (x, y, z citygen m; a loop closes on its first), its cycle's samples
	 *  [TransitSampleStarts[l], ...) of TransitSamples (m along the cycle), its stop events
	 *  [TransitEventStarts[l], ...) of TransitEvents (4 floats: arrive, depart (s into the
	 *  cycle), its stop (an index of the line's stops, -1 a turn without one), way (0 out, 1
	 *  back)), its stops [TransitStopStarts[l], ...). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitPointStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitPoints;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitSampleStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitSamples;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitEventStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitEvents;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitStopStarts;
	/** Per stop: its platform walkway (a walkway lane, -1), where along the track (m), people
	 *  boarding and leaving a train per band (5 each), the height they board at (citygen m),
	 *  whether at the walkway's level (1; 0: a concourse over the track, they go at the point
	 *  over a door). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitStopLane;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitStopS;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitStopBoard;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitStopAlight;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitStopZ;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitStopLevel;
	/** The stand-ins (the exporter's per mode model table): per mode its parts
	 *  [TransitPartStarts[m], TransitPartStarts[m + 1]) of TransitParts (8 floats: mesh (an index
	 *  of TransitMeshes), kind (0 body, 1 window, 2 accent, 3 dark), middle (3: m in the car's
	 *  frame, x forward, y left, z up from its body's bottom), scale (3)); their material
	 *  (Core/Life/M_CgTransit: base color and emission from per-instance custom data). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> TransitPartStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> TransitParts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<TObjectPtr<UStaticMesh>> TransitMeshes;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TObjectPtr<UMaterialInterface> TransitMaterial;
	/** Per walkway lane how far off its middle people keep (m: a platform's trains), 0 none;
	 *  per door (as DoorLanes) 1 where it is a served station's street access (its people come
	 *  off the trains while transit runs). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<float> WalkClear;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") TArray<int32> DoorTransit;
	/** A train crosses to the other way's track over this before it turns (m). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") float TransitCrossM = 90.f;
	/** Doors open this long after a train halts and close this long before it leaves (s),
	 *  sliding over TransitDoorSlideS; door leaves are drawn within TransitDoorsM of the view,
	 *  people board within the crowd's live region; trains past TransitFarM have their
	 *  instances sent every fourth frame. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") float TransitDoorOpenS = 2.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") float TransitDoorCloseS = 4.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") float TransitDoorSlideS = 1.5f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") float TransitDoorsM = 300.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") float TransitFarM = 1500.f;
	/** Transit on or off (CityGenLife.Transit [0|1], the play menu's row). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Transit") bool bTransit = true;

	/** Whether this is LG6's transit (lines with tracks and timetables). */
	bool IsTransit() const { return TransitLineMode.Num() > 0 && TransitPointStarts.Num() == TransitLineMode.Num() + 1 && TransitSampleStarts.Num() == TransitLineMode.Num() + 1; }
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetTransit(bool bOn);
	/** For the check's shots: the camera moved to the nearest train standing at a stop with its
	 *  doors open and people boarding or leaving (`board`), standing at a stop (`dwell`), or
	 *  moving on a line of a mode (`metro`, `monorail`, `maglev`, `sky_tube`, `elevated_rail`,
	 *  `moving` any), within 2 km of the view; false without one. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool ShowTransit(const FString& What);

	// --- LG7: air and water (set by the importer from the plan's airwater.json) --------------
	// Everything that flies or floats runs a route: a closed path (points with the heading the
	// vehicle faces there), its place along it by the world's time as LG6's trains (the route's
	// sampled cycle at (time + its phase) modulo the cycle, the band's vehicles evenly round it),
	// dwells where it lands on a pad, sets down on a roof, berths at a pier or lies at a berth.
	// A flier banks into its turns and pitches with its climb; a boat rolls and bobs on the water.
	// Drawn as instanced parts (AG18's hover cars' meshes in their paint, the stand-ins' basic
	// shapes in M_CgTransit), their nav lights, strobes, beacons and police bars flashing; far
	// vehicles' instances sent every fourth frame.

	/** Per route: its kind (an index of AwKinds: car, drone, police, media, aircraft, shuttle,
	 *  boat, taxi, ferry, ship), model (of AwModels), color (linear RGB), cycle (s), its samples'
	 *  step (s), vehicles per hour band (5), its points [AwPointStarts[r], ...) of AwPoints (4
	 *  floats: x, y, z citygen m absolute, heading degrees counterclockwise from east), samples
	 *  [AwSampleStarts[r], ...) of AwSamples (m along the path), dwells [AwEventStarts[r], ...)
	 *  of AwEvents (3 floats: arrive, depart, what: 0 pad, 1 roof, 2 pier, 3 berth, 4 launch
	 *  pad), its vehicles' paints [AwPaintStarts[r], ...) of AwPaints (9 floats each, a painted
	 *  model's). */
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwRouteKind;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwRouteModel;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwRouteColor;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwRouteCycle;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwRouteDt;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwRouteCount;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<FString> AwRouteIds;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwPointStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwPoints;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwSampleStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwSamples;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwEventStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwEvents;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwPaintStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwPaints;
	/** The kinds and models by their index; per model its parts [AwModelPartStarts[m], ...) of
	 *  AwParts (9 floats: mesh (of AwMeshes), kind (-1 painted: an AG18 mesh in its vehicle's
	 *  paint; else 0 body, 1 window, 2 accent, 3 dark, 4 nav red, 5 nav green, 6 strobe, 7 police
	 *  red, 8 police blue, 9 lamp, 10 hull, 11 beacon), middle (3: m in the vehicle's frame, x
	 *  forward, y left, z up), scale (3: the basic shapes are 1 m; 1 for a painted mesh, the
	 *  middle its pivot), cull distance (m, 0 none)); per mesh the custom floats its instances
	 *  carry (9 painted, 6 the stand-ins': base color and emission in AwMaterial). */
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<FString> AwKinds;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<FString> AwModels;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwModelPartStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<float> AwParts;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<TObjectPtr<UStaticMesh>> AwMeshes;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TArray<int32> AwMeshFloats;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") TObjectPtr<UMaterialInterface> AwMaterial;
	/** Vehicles past AwFarM have their instances sent every fourth frame. */
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") float AwFarM = 1500.f;
	/** A component is sent every frame while a vehicle within AwNearM moved in it, else every
	 *  fourth frame (the engine's cost is per moving component). */
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") float AwNearM = 600.f;
	/** What flies and what floats on or off (CityGenLife.Air, CityGenLife.Water, the play menu's
	 *  rows). */
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") bool bAir = true;
	UPROPERTY(EditAnywhere, Category = "CityGen|AirWater") bool bWater = true;

	/** Whether this is LG7's air and water (routes with points and samples). */
	bool IsAirWater() const { return AwRouteKind.Num() > 0 && AwPointStarts.Num() == AwRouteKind.Num() + 1 && AwSampleStarts.Num() == AwRouteKind.Num() + 1; }
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetAir(bool bOn);
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetWater(bool bOn);
	/** For the check's shots: the camera moved beside the nearest vehicle of a kind (`car`,
	 *  `drone`, `police`, `media`, `aircraft`, `shuttle`, `boat`, `taxi`, `ferry`, `ship`), a
	 *  car coming down onto its pad (`landing`), a boat at a pier (`pier`), the cars' layers
	 *  over an avenue from behind one (`layers`); false without one. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool ShowAirWater(const FString& What);

	// --- LG8: the hour, the weather and reactions (set by the importer from the plan's weather) --
	// The crowd, the traffic, the places, transit and what flies and floats live at the hour of
	// atmosgen's controller (its Hour, read every half second: a step of an hour as time runs
	// changes who comes out of the doors and who goes in, a jump fills the live walkways and
	// lanes again) and by its weather (its state and rain): people out (the rest go in at doors),
	// their pace, raincoats and umbrellas, people stopping under the covers their walkways pass
	// (the plan's stretches out of the rain: atmosgen's rain shadow), the cars' speed and
	// headway. Nightlife's people round the open bars, clubs and arcades by night. Reactions:
	// people standing near the player look at it; a danger (Panic, storygen's hook) sends them
	// running and draws a crowd to look after it.

	/** The weather's table: per state (WeatherNames) WeatherKeys floats (out, pace, rain_looks,
	 *  umbrella, shelter, cars, speed, headway_s) and its rain rate (WeatherRain); the plan's own
	 *  state (without atmosgen's controller); the rain looks' group. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<FString> WeatherNames;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<FString> WeatherKeys;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<float> WeatherLife;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<float> WeatherRain;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") FString WeatherPlan = TEXT("clear");
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") int32 RainGroup = -1;
	/** Per walkway lane its stretches out of the rain [WalkCoverStarts[l], WalkCoverStarts[l + 1])
	 *  of WalkCover (pairs: from, to, m along it); nightlife's people per band (5 a lane, or none). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<int32> WalkCoverStarts;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<float> WalkCover;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<float> WalkNight;
	/** Per walkway lane the side its road is on along its line (1 right, -1 left, 0 none):
	 *  people shelter on the other, against the buildings, facing the road. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<int32> WalkRoadSide;
	/** Umbrellas: canopy colors and lit shafts' colors (linear RGB), the settings (lit share,
	 *  canopy width and height, height over the feet in the person's heights, right, forward
	 *  (m), tilt (deg), shaft length (m)), the meshes and their material (M_CgTransit's six custom
	 *  floats: base color, emission). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<float> UmbrellaColors;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<float> UmbrellaLit;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TArray<float> Umbrella;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TObjectPtr<UStaticMesh> UmbrellaCanopy;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TObjectPtr<UStaticMesh> UmbrellaShaft;
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") TObjectPtr<UMaterialInterface> UmbrellaMaterial;
	/** How long a passer-by stands under a cover in the rain (s). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") FVector2D ShelterS = FVector2D(25.0, 140.0);
	/** The reactions: looking at the player (within LookM), fleeing a danger (within FleeM, for
	 *  FleeS, at FleePace times the pace) and gathering after it (for GatherS, a GatherShare of
	 *  the people within GatherM, on a ring RingM off it, for StayS). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") bool bLook = true;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") bool bFlee = true;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") bool bGather = true;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float LookM = 6.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float FleeM = 35.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float FleeS = 14.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float FleePace = 2.4f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float GatherM = 60.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float GatherS = 90.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float GatherShare = 0.35f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") FVector2D RingM = FVector2D(9.0, 22.0);
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") FVector2D StayS = FVector2D(15.0, 60.0);
	/** A car standing StuckS in a queue past StuckFarM of the view leaves. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float StuckS = 75.f;
	UPROPERTY(EditAnywhere, Category = "CityGen|Traffic") float StuckFarM = 150.f;
	/** The places' run clip per clip group (LG8: fleeing near the view; else the walk, faster). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") TArray<TObjectPtr<UAnimSequence>> RunClips;
	/** The run clip's own speed (m/s: its root's travel over its length before it was made in
	 *  place). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Reactions") float RunClipSpeed = 4.5f;
	/** Life follows atmosgen's hour and weather (CityGenLife.FollowAtmos [0|1]); off, its own Hour
	 *  and weather (CityGenLife.Hour, CityGenLife.Weather). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") bool bFollowAtmos = true;
	/** The weather's effects on life (CityGenLife.Weather off: clear whatever atmosgen shows). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather") bool bWeatherOn = true;

	bool IsWeather() const { return WeatherNames.Num() > 0 && WeatherKeys.Num() > 0 && WeatherLife.Num() == WeatherNames.Num() * WeatherKeys.Num(); }
	UFUNCTION(BlueprintCallable, Category = "CityGen") void SetFollowAtmos(bool bOn);
	/** Life's weather: a state's name (held, not following atmosgen's weather), `auto` (atmosgen's
	 *  again), `off` (clear, no weather's effect). */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool SetWeather(const FString& State);
	/** A danger at a point (UE cm), its reach (m) and how long people flee (s; 0: FleeM and FleeS):
	 *  storygen's hook. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") void Panic(FVector Where, float InRadiusM = 0.f, float InSeconds = 0.f);
	/** A danger where the player is (CityGenLife.Panic, the play menu's row). */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool PanicAtPlayer(float InRadiusM = 0.f, float InSeconds = 0.f);
	/** For the check's shots: the camera moved to the nearest person with an umbrella (`umbrella`),
	 *  standing under a cover (`shelter`), looking at the player (`look`), running from a danger
	 *  (`flee`), looking at it (`gather`), a bar's nightlife (`night`); false without one. */
	UFUNCTION(BlueprintCallable, Category = "CityGen") bool ShowWeather(const FString& What);

private:
	// (LG8, CityGenLifeWeather.cpp)
	void BuildWeather();
	void FollowAtmos(float Dt, bool bNow);
	void ApplyWeatherNow();
	float WeatherKey(int32 State, const TCHAR* Key) const;
	void ThinOut();
	void MakeUmbrellas();
	void UpdateUmbrellas(const FVector& View);
	bool HasUmbrella(int32 Person) const;
	FString WeatherStatus() const;
	TWeakObjectPtr<AActor> AtmosActor;
	bool bAtmosLooked = false;
	float AtmosClock = 0.f;
	float AtmosHour = -1.f;
	float RainNow = 0.f;
	FString WeatherState = TEXT("clear");
	FString WeatherHeld;                       // a state held by CityGenLife.Weather, else empty
	float OutNow = 1.f, PaceNow = 1.f, RainLooksNow = 0.f, UmbrellaNow = 0.f, ShelterNow = 0.f;
	float CarsNow = 1.f, SpeedNow = 1.f, HeadwayNow = 0.f;
	float ThinClock = 0.f;
	int32 HourSteps = 0, HourJumps = 0, Thinned = 0;
	TArray<int32> CoverStartsG;
	TArray<float> CoverCm;
	TArray<uint8> WalkCovered;
	UPROPERTY(Transient) TObjectPtr<UInstancedStaticMeshComponent> UmbCanopy;
	UPROPERTY(Transient) TObjectPtr<UInstancedStaticMeshComponent> UmbShaft;
	TArray<FTransform> UmbCanXf, UmbShaftXf;
	TArray<uint8> UmbShown;
	int32 UmbrellasNow = 0;
	bool bUmbSeen = false;
	int32 PanicCount = 0;
	FVector LastPanicAt = FVector::ZeroVector;
	FString LastWeatherShow;
	// (LG8's performance pass: the near people's garments' dynamic material instances kept, one
	// per slot and parent material, reused as a slot takes another person; each made once, so
	// near people coming and going make no garbage)
	UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> NearMIDs;
	TMap<uint64, TObjectPtr<UMaterialInstanceDynamic>> NearMIDOf;

private:
	// (LG7, CityGenLifeAir.cpp)
	struct FCgAwVehicle
	{
		int32 Route = INDEX_NONE;
		int32 K = 0;                // its index among the route's vehicles
		bool bOn = false;
		bool bAir = true;
		int32 Event = INDEX_NONE;   // the dwell it is in, else none
		double U = 0.0;             // s into the cycle
		double Sm = 0.0;            // m along the path
		float Speed = 0.f;          // m/s
		FTransform Xf;              // its frame (UE)
		int64 Sent = -100;
		int32 Paint = INDEX_NONE;   // its paint (of AwPaints), a painted model's
	};
	void BuildAirWater();
	void UpdateAirWater(float Dt);
	void PlaceAw(FCgAwVehicle& V, double Time);
	void AwPathAt(int32 Route, double Sm, FVector& Pos, float& YawDeg) const;
	double AwSampleAt(int32 Route, double U) const;
	FString AirWaterStatus() const;
	TArray<FCgAwVehicle> AwVehicles;
	TArray<TArray<double>> AwCum;                      // per route its points' distances (3D)
	// (one component per mesh and cull distance; per vehicle per part its component and
	// instance)
	UPROPERTY(Transient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> AwComps;
	TArray<int32> AwVehPartStart;                      // per vehicle its first of AwPartComp/Inst
	TArray<int32> AwPartComp, AwPartInst, AwPartIdx;
	TArray<TArray<FTransform>> AwXf;                   // per component its instances' transforms
	TArray<TPair<int32, int32>> AwBlinkers;            // (component, instance) of flashing parts
	TArray<int32> AwBlinkKind, AwBlinkVeh;
	TArray<uint8> AwBlinkOn;
	int64 AwFrame = 0;
	int32 AwAirOn = 0, AwWaterOn = 0, AwDwelling = 0, AwNear = 0;
	double AwMs = 0.0, AwMsMax = 0.0;
	FString LastAwShow;

private:
	// (LG6, CityGenLifeTransit.cpp)
	struct FCgTrack
	{
		TArray<FVector> P;          // citygen m, a loop's first again at its end
		TArray<double> S;           // m along it (3D)
		double L = 0.0;
		bool bLoop = false;
		FVector At(double Sm) const;
	};
	struct FCgTrain
	{
		int32 Line = INDEX_NONE;
		int32 K = 0;                // its index among the line's trains
		bool bOn = false;           // running in this hour band
		int32 Event = INDEX_NONE;   // the stop event it stands at (the line's), else none
		float Open = 0.f;           // its doors open (0 shut, 1 open)
		int32 Way = 0;
		double Sm = 0.0;            // m along the track (its middle)
		double U = 0.0;             // s into the cycle
		FVector Mid = FVector::ZeroVector;   // UE cm, its middle car's
		FVector Fwd = FVector::ForwardVector;
		bool bNear = false;
		int64 Sent = -100;          // the frame its instances were last sent
		TArray<FTransform> Cars;    // per car: its body's bottom middle, travel heading (UE)
		int32 InstStart = 0;        // its parts' first instance in each mesh's component (per mesh)
	};
	void BuildTransit();
	void UpdateTransit(float Dt);
	void PlaceTrain(FCgTrain& T, double Time);
	void TrainArrives(FCgTrain& T);
	void DrawTrains();
	void DrawDoors();
	bool DoorPoint(const FCgTrain& T, int32 Car, int32 Door, float Side, FVector& Out) const;
	float LatOf(int32 Line, int32 Way, double Sm) const;
	FString TransitStatus() const;
	TArray<FCgTrack> Tracks;
	TArray<FCgTrain> Trains;
	TArray<int32> LineTrainStart;                      // (per line its first train)
	TArray<TArray<int32>> TrainInst;                   // (per train, per mesh its first instance)
	TArray<uint8> DoorTransitSorted;
	TArray<float> WalkClearCm;
	UPROPERTY(Transient) TArray<TObjectPtr<UInstancedStaticMeshComponent>> TransitComps;
	UPROPERTY(Transient) TObjectPtr<UInstancedStaticMeshComponent> DoorComp;
	int32 DoorInstUsed = 0;
	int32 TransitArrivals = 0, TransitBoarded = 0, TransitAlighted = 0, TransitBoardingNow = 0;
	int32 TrainsOn = 0, TrainsMoving = 0, TrainsDwelling = 0, TrainsNear = 0;
	int64 TransitFrame = 0;
	double TransitMs = 0.0, TransitMsMax = 0.0;
	FString LastTransitShow;
	FRandomStream TransitRng;

private:
	// (LG4, CityGenLifePlaces.cpp)
	void BuildPlaces();
	void MakeDefinitions();
	void SlotsAlive(int32 Lane, bool bAlive);
	int32 ClaimPoint(int32 Slot, int32 Person);
	void OccupyPoint(int32 Slot, int32 Point);
	void ReleasePoint(int32 Slot, int32 Point);
	void UpdateSlotWants();
	void FillLaneRoles(int32 Lane);
	void FillSlot(int32 Slot);
	void PoliceFromStations(float Dt);
	void DressFaction(int32 Slot, int32 Faction, FRandomStream& Rng);
	void ApplyHour();
	float RoleWant(int32 Lane, uint8 PRole) const;
	FString PlacesStatus() const;
	TArray<int32> LaneSlotStarts, LaneSlotList, SlotPointStartG;
	TArray<float> SlotDistCm, SlotWantNow, PointYawG;
	TArray<int32> SlotUsersNow, PointUser, SlotDoorSorted;
	TArray<uint8> SlotLiveNow, SlotAnimG, WalkAnimG;
	TArray<FVector> PointPosG;
	TArray<int32> DoorSortedOf;              // (an exported door's sorted index)
	TArray<uint8> DoorOpenNow, DoorPoliceSorted;
	TArray<float> DoorVisitNow, DoorDwellSorted, DoorRatesHSorted, DoorVisitSorted;
	TArray<int32> DoorOpenSorted;
	TArray<int32> FreeGang, FreePolice;      // (the role slots of the pool, free)
	TArray<int32> FreePoliceCars;
	TArray<uint8> CarIsPolice;
	TArray<FCgPointSO> PointSO;              // (each live point's Smart Object, its slot, claim)
	UPROPERTY(Transient) TArray<TObjectPtr<UObject>> Definitions;
	float GangScaleNow = 1.f, PoliceScaleNow = 1.f, WantGang = 0.f, WantPolice = 0.f, PoliceAcc = 0.f;
	float PoliceCarScaleNow = 1.f, WantPoliceCars = 0.f, PoliceRefillAcc = 0.f;
	int32 GangActive = 0, PoliceActive = 0, PoliceCarsActive = 0, SlotsLiveNow = 0, PointsSO = 0;
	int32 CrowdPoolN = 0, GangPoolN = 0, PolicePoolN = 0, PoliceCarPoolN = 0;
	float SlotWantOf(int32 Slot) const;
	int32 SlotsTakenTotal = 0, SlotsLeftTotal = 0, VisitsTotal = 0, PoliceOut = 0, ClaimsRefused = 0;

private:
	// (LG5, CityGenLifeTraffic.cpp)
	void BuildTraffic();
	void SpawnCarPool();
	void UpdateTraffic(float Dt, bool bRefill);
	bool SpawnCar(int32 Lane, float Dist, FRandomStream& Rng, bool bPoliceCar = false);
	void FreeCarsOnDeadLanes();
	void TakeFreedCars();
	void FreeCar(int32 Slot, FCgLifeCar& C);
	float TrafficWant(int32 J) const;
	void UpdateCarInstances();
	void GatherPlayers();
	FString TrafficStatus() const;
	bool FrameCar(const FVector& At, const FVector& Toward, float Back, float Up, float Side);
	TArray<uint8> DriveMainG, DriveIsConnector, CarShow;
	TArray<int32> DriveSignalG, ConflictStartsG, ConflictsG, CarFreed, CarSlotModel, CarDistrict;
	TArray<float> DriveStopBackG, CarSpin, DriveHalf;
	TArray<FVector> DriveMid;
	TArray<TArray<int32>> ModelSlots, FreeByModel, PartsOfModel;
	TArray<TArray<uint8>> PartShown;          // (per part, per instance: drawn now)
	int32 InstancesSent = 0;
	int64 CarFrame = 0;
	TArray<int32> TrafficLaneHave;
	TArray<FMassEntityHandle> CarEnts;
	FRandomStream TrafficRng;
	FVector LastTrafficView = FVector(1.0e12);
	float TrafficClock = 0.f, TrafficLiveScale = 1.f, TrafficWantLive = 0.f, RefillAcc = 0.f;
	int32 TrafficLiveLanes = 0, CarsActive = 0, CarsSpawned = 0, CarsRefilled = 0, CarsLost = 0, CarsLeftTotal = 0;
	int32 CarsWhyNow[7] = {0, 0, 0, 0, 0, 0, 0};
	int32 CarsMovingNow = 0, CarsForcedTotal = 0, CarsStuckTotal = 0;
	double TrafficMs = 0.0, TrafficMsMax = 0.0, CarDrawMs = 0.0, LiveMs = 0.0, LiveMsMax = 0.0;
	FString LastShow;

	// (LG3, CityGenLifeCrowd.cpp)
	void BuildCrowd();
	void SpawnPool();
	void UpdateLive(float Dt, bool bRefill);
	int32 SpawnGroup(int32 Lane, float Dist, float Dir, int32 Size, int32 Door, FRandomStream& Rng,
		uint8 PRole = 0, int32 Turf = INDEX_NONE, TArray<int32>* OutSlots = nullptr);
	void FreeRole(int32 Slot);
	void DoorSpawns(float Dt);
	void TakeFreed();
	void FreeOnDeadLanes();
	float Want(int32 Lane) const;
	int32 GroupSize(FRandomStream& Rng) const;
	/** The mid and far instances' custom data for a person's look (CgLook). */
	void ApplyLook(int32 Person, uint8 Look);
	FString CrowdStatus() const;

	TArray<uint8> LaneKindArr;
	TArray<int32> LaneSignalArr, LaneDistrictArr, LaneDoorStarts, LaneHave, FreeSlots, Freed;
	TArray<float> HoldA, HoldB, DoorDists, DoorCum, LaneHalf;
	TArray<int32> DoorLive, DoorLanesSorted;
	TArray<float> DoorRatesSorted;
	TArray<FVector> LaneMid, DoorStreet, DoorInside;
	TArray<uint8> WalkState, PersonStill;
	TArray<float> PersonWear;
	FVector LastLiveView = FVector(1.0e12);
	float LiveClock = 0.f, DoorAcc = 0.f, LiveScale = 1.f, WantLive = 0.f;
	int32 LiveLanes = 0, ActiveNow = 0, GroupCounter = 0, Spawned = 0, DoorOut = 0, DoorIn = 0, Lost = 0;
	int32 WaitingNow = 0, JaywalkTotal = 0;
	int64 Frames = 0;
	FRandomStream CrowdRng;

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
	// (lifegen_people_fixes: per character the baked walk's own loop, [MidFirst, MidLast]: the
	// bake samples AnimToTexture's frame count, the clip's 30 fps keys, at 15 fps, so it ran
	// past the clip's end and its second half held the last pose; and the frame a standing
	// person holds, the walk's passing pose, found from the clip's thighs. The instances'
	// custom data for a person walking or standing, mid and far.)
	void MakeMidLoops();
	// (LG2: the instances' custom data carry the person's three dye colors and wear: mid
	// 4 anim + 9 + 1 floats, far 2 + 9 + 1; TintOf a person's dye channel's color)
	// (people_idles: the look, CgLook: walking, standing, running, sitting; the far card's
	// first cell and cells after them, 14 floats)
	void LookData(int32 Person, uint8 Look, float Mid[14], float Far[14]) const;
	void TintOf(int32 Person, int32 Channel, float Out[3]) const;
	// (people_idles: a mid mesh slot's material, the idles' bake's where there is one; the
	// sit-downs' and the stand-up's starts and ends in the walk processor's seat frame, from
	// SitIn and SitOut and MeshYaw; per person what it played last and since when, s)
	UMaterialInterface* MidSlotMaterial(int32 Char, int32 Slot) const;
	void MakeSitFrames();
	TArray<float> SitInSeat, SitOutSeat;
	TArray<uint8> PersonAnimPrev;
	TArray<float> PersonAnimT;
	int32 TakeSlot(int32 District, FRandomStream& Rng);
	void DressSlot(int32 Slot, int32 District, FRandomStream& Rng);
	TArray<float> MidFirst, MidLast, MidStand, StandShare;
	// (lifegen_clothing_toggle)
	void ApplyClothing();

	/** A near person's components: the leader (the body) and its followers. */
	struct FNearSlot
	{
		TArray<USkeletalMeshComponent*> Comps;
		UStaticMeshComponent* Hair = nullptr;
		USkeletalMeshComponent* Whole = nullptr;   // (lifegen_clothing_toggle: the whole body)
		int32 Person = INDEX_NONE;
		int32 Char = INDEX_NONE;
		int32 Gait = INDEX_NONE;
		uint8 Clip = 0;            // (LG3: 0 its walk, 1 an idle; LG4: 2 sitting, 3 + k a talk clip)
	};
	/** A near slot's components by the clothing switch (lifegen_clothing_toggle). */
	void SlotClothing(FNearSlot& Slot);
	/** Per character the mid mesh's garment slots (lifegen_clothing_toggle). */
	TArray<TArray<int32>> MidGarment;
	bool bHiddenWarned = false;
	TArray<uint8> MidSeen, FarSeen;
	TArray<FNearSlot> NearSlots;
	UPROPERTY(Transient) TArray<TObjectPtr<USkeletalMeshComponent>> NearComps;
	UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> HairComps;
	UPROPERTY(Transient) TArray<TObjectPtr<USkeletalMeshComponent>> WholeComps;
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
	/** LG8: the box every instanced component's instances stay within (the lanes' bounds, wide
	 *  and high enough for what flies), their fixed bounds (UCgLifeISM). */
	FBox CityBox = FBox(ForceInit);
	void FixBounds(UInstancedStaticMeshComponent* C) const;
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
