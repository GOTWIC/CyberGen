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
struct FCgLifeCar;

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

	// --- LG5: the city's traffic ----------------------------------------------------------------
	bool bTraffic = false;
	/** Per lane (every lane of the storage; walkways 0): on the lane graph's largest strongly
	 *  connected part (cars drive only there), a junction connector, the signal window it stops
	 *  at (-1 none; 5 floats each in DriveWindows: cycle, offset, green from, green to, amber
	 *  to, s) and where (cm back from its end), the connectors it may not be driven at once
	 *  with ([ConflictStarts[l], ConflictStarts[l + 1]) of Conflicts). */
	const TArray<uint8>* DriveMain = nullptr;
	const TArray<uint8>* IsConnector = nullptr;
	const TArray<int32>* DriveSignal = nullptr;
	const TArray<float>* DriveStopBack = nullptr;
	const TArray<float>* DriveWindows = nullptr;
	const TArray<int32>* ConflictStarts = nullptr;
	const TArray<int32>* Conflicts = nullptr;
	/** The people's places (the crowd's WalkPos, WalkYaw, WalkState by pool slot), for the
	 *  cars to stop for; and the pawns the cars stop for (the walker, a fly pawn: UE cm). */
	TArray<FVector> Players;
	/** Out: per car slot whether it is drawn, its wheels' turn (deg); the slots freed. */
	TArray<uint8>* CarShow = nullptr;
	TArray<float>* CarSpin = nullptr;
	TArray<int32>* CarFreed = nullptr;
	/** The car following model (cm, s), signals, junctions, yielding (presets.TRAFFIC). */
	float Accel = 180.f, Brake = 260.f, BrakeMax = 800.f, GapCm = 220.f, Headway = 1.2f, Delta = 4.f;
	float AmberBrake = 350.f, StarveS = 6.f, ForceS = 25.f;
	float YieldCm = 18000.f, LookS = 1.6f, LookMinCm = 800.f, LookMaxCm = 4500.f, LatCm = 145.f;
	float PredictS = 1.f, MarginCm = 200.f;
	/** Out: counts this frame (cars by why they slow, moving, freed at the live region's edge). */
	int32 CarsWhy[7] = {0, 0, 0, 0, 0, 0, 0};
	int32 CarsMoving = 0, CarsActive = 0, CarsLeft = 0, CarsForced = 0;
	/** The cars' step's own time (ms, this frame). */
	double TrafficMs = 0.0;
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
	/** LG5: the city's traffic (CityGenLifeTraffic.cpp). */
	void ExecuteTraffic(FMassExecutionContext& Context);

	FMassEntityQuery Query;
	// (LG5: the frame's cars sorted by lane and distance, each lane's first; who holds or
	// claims each connector; the people near the view in cells)
	TArray<FCgLifeCar*> Sorted;
	TArray<int32> LaneFirst, Occ, ClaimBy;
	TArray<float> ClaimWait;
	TArray<int32> Touched;
	TArray<FVector> PedPos, PedAhead;
	TArray<int64> PedCell;
	TArray<int32> PedOrder;
	TMap<int64, int32> CellStart;
};
