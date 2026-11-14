// lifegen's Mass fragments (LG0): a stand-in walking a walkway lane and a car driving a lane,
// each an entity of the world's Mass entity manager, moved by CityGenLife's processors.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "CityGenLifeTypes.generated.h"

/** A person walking: on a walkway lane (an index into the life actor's ZoneGraph storage), a
 *  distance along it and a direction (walkways are walked both ways), a pace, a side of the
 *  lane (the share of its half width, signed: + on the walker's right). */
USTRUCT()
struct FCgLifeWalker : public FMassFragment
{
	GENERATED_BODY()

	int32 Lane = INDEX_NONE;
	int32 PrevLane = INDEX_NONE;
	float Dist = 0.f;
	float Dir = 1.f;
	float Speed = 130.f;           // cm/s
	float Side = 0.f;
	float ZOff = 0.f;              // cm over the lane: the surface found under it
	int32 Instance = 0;
	uint32 Seed = 0;
	FVector Pos = FVector::ZeroVector;
	float Yaw = 0.f;
};

/** A car driving: on a lane of the lane graph (directed), its next lane chosen ahead, its
 *  speed and cruise speed, its model and its instance among that model's cars. */
USTRUCT()
struct FCgLifeCar : public FMassFragment
{
	GENERATED_BODY()

	int32 Lane = INDEX_NONE;
	int32 Next = INDEX_NONE;
	float Dist = 0.f;
	float Speed = 0.f;             // cm/s
	float Cruise = 900.f;
	float Share = 1.f;             // (cars_steam: its share of each lane's speed)
	float ZOff = 0.f;
	int32 Model = 0;
	int32 Instance = 0;
	int32 Index = 0;               // among every car
	uint32 Seed = 0;
	FVector Pos = FVector::ZeroVector;
	float Yaw = 0.f;
};
