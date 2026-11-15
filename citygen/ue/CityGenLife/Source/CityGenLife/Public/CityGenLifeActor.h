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

private:
	// (LG5, CityGenLifeTraffic.cpp)
	void BuildTraffic();
	void SpawnCarPool();
	void UpdateTraffic(float Dt, bool bRefill);
	bool SpawnCar(int32 Lane, float Dist, FRandomStream& Rng);
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
	TArray<int32> TrafficLaneHave;
	TArray<FMassEntityHandle> CarEnts;
	FRandomStream TrafficRng;
	FVector LastTrafficView = FVector(1.0e12);
	float TrafficClock = 0.f, TrafficLiveScale = 1.f, TrafficWantLive = 0.f, RefillAcc = 0.f;
	int32 TrafficLiveLanes = 0, CarsActive = 0, CarsSpawned = 0, CarsRefilled = 0, CarsLost = 0, CarsLeftTotal = 0;
	int32 CarsWhyNow[7] = {0, 0, 0, 0, 0, 0, 0};
	int32 CarsMovingNow = 0, CarsForcedTotal = 0;
	double TrafficMs = 0.0, CarDrawMs = 0.0;
	FString LastShow;

	// (LG3, CityGenLifeCrowd.cpp)
	void BuildCrowd();
	void SpawnPool();
	void UpdateLive(float Dt, bool bRefill);
	int32 SpawnGroup(int32 Lane, float Dist, float Dir, int32 Size, int32 Door, FRandomStream& Rng);
	void DoorSpawns(float Dt);
	void TakeFreed();
	void FreeOnDeadLanes();
	float Want(int32 Lane) const;
	int32 GroupSize(FRandomStream& Rng) const;
	void ApplyLook(int32 Person, bool bStill);
	FString CrowdStatus() const;

	TArray<uint8> LaneKindArr;
	TArray<int32> LaneSignalArr, LaneDistrictArr, LaneDoorStarts, LaneHave, FreeSlots, Freed;
	TArray<float> HoldA, HoldB, DoorDists, DoorCum, LaneHalf;
	TArray<int32> DoorLive, DoorLanesSorted;
	TArray<float> DoorRatesSorted;
	TArray<FVector> LaneMid, DoorStreet, DoorInside;
	TArray<uint8> WalkState, PersonStill;
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
	void LookData(int32 Person, bool bStill, float Mid[7], float Far[5]) const;
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
		bool bIdle = false;        // (LG3: playing an idle, standing)
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
