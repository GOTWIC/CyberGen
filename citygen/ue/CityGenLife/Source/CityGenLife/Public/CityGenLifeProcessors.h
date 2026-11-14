// lifegen's Mass processors (LG0): run by the life actor each tick (dynamic processors, not in
// the world's processing phases, so the project needs no MassGameplay plugin), each moving its
// entities along the ZoneGraph lanes the actor built from the city's graphs and writing their
// transforms for the actor's instanced stand-ins.

#pragma once

#include "CoreMinimal.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "CityGenLifeProcessors.generated.h"

struct FZoneGraphStorage;

/** What the processors read and write, owned by the life actor. */
struct FCgLifeFrame
{
	const FZoneGraphStorage* Storage = nullptr;
	/** Walkway lanes are [0, WalkLanes); drive lanes [WalkLanes, Lanes). */
	int32 WalkLanes = 0;
	/** Per lane: its length (cm) and width (cm). */
	const TArray<float>* Lengths = nullptr;
	const TArray<float>* Widths = nullptr;
	/** Per lane: whether it is in the live region (a lane outside it is left at once). */
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

	FMassEntityQuery Query;
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
