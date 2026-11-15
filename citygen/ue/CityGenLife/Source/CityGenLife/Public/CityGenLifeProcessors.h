// lifegen's Mass processors (LG0, LG3): run by the life actor each tick (dynamic processors,
// not in the world's processing phases, so the project needs no MassGameplay plugin), each
// moving its entities along the ZoneGraph lanes the actor built from the city's graphs and
// writing their transforms for the actor's instanced people and cars.

#pragma once

#include "CoreMinimal.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "CityGenLifeProcessors.generated.h"

struct FZoneGraphStorage;
struct FCgLifeWalker;

/** LG3: walkway kinds by the plan's code (lifegen/presets.py WALK_KIND_CODES). */
namespace CgKind
{
	enum : uint8
	{
		Sidewalk = 0, Crossing = 1, Crosswalk = 2, Path = 3, Alley = 4, Promenade = 5,
		PedestrianStreet = 6, Footbridge = 7, Stairs = 8, Escalator = 9, Elevator = 10,
		Skybridge = 11, Elevated = 12, Underpass = 13, Concourse = 14,
	};
}

/** What the processors read and write, owned by the life actor. */
struct FCgLifeFrame
{
	const FZoneGraphStorage* Storage = nullptr;
	/** Walkway lanes are [0, WalkLanes); drive lanes [WalkLanes, Lanes). */
	int32 WalkLanes = 0;
	/** Per lane: its length (cm) and width (cm). */
	const TArray<float>* Lengths = nullptr;
	const TArray<float>* Widths = nullptr;
	/** Per lane: whether it is in the live region (a lane outside it is left at once). LG3:
	 *  a walkway lane is live within LiveM of the view, the actor's live update keeps it. */
	const TArray<uint8>* InRegion = nullptr;
	/** Drive lanes to start a car on when it leaves the region or meets a dead end. */
	const TArray<int32>* CarStarts = nullptr;
	float CarGap = 900.f;
	/** cars_steam: per storage point the speed a car may drive at (cm/s; empty: none). */
	const TArray<float>* PointVmax = nullptr;
	/** Out: per walker instance, location and yaw (deg). */
	TArray<FVector>* WalkPos = nullptr;
	TArray<float>* WalkYaw = nullptr;
	/** Out: per car (its Index), location and yaw. */
	TArray<FVector>* CarPos = nullptr;
	TArray<float>* CarYaw = nullptr;

	// --- LG3: the city's crowd ------------------------------------------------------------------
	bool bCity = false;
	/** Per walkway lane: its kind (CgKind), its signal window (-1 none: an index into
	 *  SignalWindows, 4 floats each: cycle, offset, walk from, walk to, s), the curb points a
	 *  crosswalk waits at walked forward and back (cm along it), its district (-1 none). */
	const TArray<uint8>* LaneKind = nullptr;
	const TArray<int32>* LaneSignal = nullptr;
	const TArray<float>* SignalWindows = nullptr;
	const TArray<float>* HoldA = nullptr;
	const TArray<float>* HoldB = nullptr;
	const TArray<int32>* LaneDistrict = nullptr;
	const TArray<float>* DistrictDanger = nullptr;
	/** The doors (spawn and sink points): per walkway lane its doors [LaneDoorStarts[l],
	 *  LaneDoorStarts[l + 1]) sorted by their distance along it (DoorDists, cm), each door's
	 *  point on the walkway and inside its door (UE cm). */
	const TArray<int32>* LaneDoorStarts = nullptr;
	const TArray<float>* DoorDists = nullptr;
	const TArray<FVector>* DoorStreet = nullptr;
	const TArray<FVector>* DoorInside = nullptr;
	/** Per lane how many live people are on it (kept by the processor as they move). */
	TArray<int32>* LaneHave = nullptr;
	/** Per instance its draw tier last frame (0 near, 1 mid, 2 far, 3 none): far people move
	 *  every second frame, those drawn by no tier every fourth. */
	const TArray<uint8>* PersonTier = nullptr;
	/** Out: per instance what the drawing shows (CgShow); the pool slots freed this frame. */
	TArray<uint8>* WalkState = nullptr;
	TArray<int32>* Freed = nullptr;
	/** The view (UE cm), the player's pawn (to step aside from), the game's time (s), the frame. */
	FVector View = FVector::ZeroVector;
	FVector Player = FVector::ZeroVector;
	bool bPlayer = false;
	double Time = 0.0;
	int64 FrameNo = 0;
	/** The crowd's settings (cm, s, shares). */
	float ReachCm = 400.f, PersonalCm = 75.f, PlayerCm = 250.f, AvoidCm = 9000.f;
	float StairsShare = 0.6f, EscShare = 0.3f, EscAddCm = 50.f, ElevatorCm = 60.f;
	FVector2D Jaywalk = FVector2D(0.01, 0.30);
	/** lifegen_people_fixes: how fast a person turns (deg/s), and the walkways' corners
	 *  rounded for walking: at most CornerCm along each leg (and CornerLeg of it), cutting
	 *  the corner by at most CornerCut of the narrower walkway's half width. */
	float TurnDegS = 270.f, CornerCm = 150.f, CornerLeg = 0.45f, CornerCut = 0.5f;
	/** Out: counts this frame. */
	int32 Waiting = 0, Entered = 0, Exited = 0, Jaywalked = 0;
};

UCLASS()
class UCityGenLifeWalkProcessor : public UMassProcessor
{
	GENERATED_BODY()
public:
	UCityGenLifeWalkProcessor();
	FCgLifeFrame* Frame = nullptr;

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;
	void ExecuteCity(FMassExecutionContext& Context);

	FMassEntityQuery Query;
	TArray<FCgLifeWalker*> Near;
};

UCLASS()
class UCityGenLifeDriveProcessor : public UMassProcessor
{
	GENERATED_BODY()
public:
	UCityGenLifeDriveProcessor();
	FCgLifeFrame* Frame = nullptr;

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery Query;
};
