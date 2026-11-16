// lifegen's Mass fragments (LG0, LG3): a person walking a walkway lane and a car driving a
// lane, each an entity of the world's Mass entity manager, moved by CityGenLife's processors.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "CityGenLifeTypes.generated.h"

/** LG3: what a person is doing (FCgLifeWalker::State). */
namespace CgWalk
{
	enum : uint8
	{
		Walk = 0,      // along its walkway lane
		Wait = 1,      // at a crosswalk's curb for the signal
		Enter = 2,     // from its walkway through a door, then gone (a trip's end)
		Exit = 3,      // out of a door onto its walkway (a trip's start)
		// --- LG4: life at places
		ToSlot = 4,    // from its walkway to a place slot's point it claimed
		AtSlot = 5,    // using it (sitting, waiting, queueing, buying, eating, talking)
		FromSlot = 6,  // back to its walkway
		Inside = 7,    // in a shop on a visit (not drawn), then out of its door again
		// --- LG6: transit
		Board = 8,     // from its platform walkway into a train's open door, then gone
	};
}

/** LG4: what a person plays (ACityGenLife's WalkAnim, per instance): the near tier's clip, the
 *  mid and far tiers' held pose. */
namespace CgAnim
{
	enum : uint8
	{
		Walk = 0,      // walking (or LG3's idle while standing)
		Idle = 1,      // standing at a slot (a bus stop, a queue, a kiosk)
		Sit = 2,       // a bench
		Talk = 3,      // talking, smoking, eating (the sample's idle breaks)
	};
}

/** LG4: a person's role (the plan's pool slots kept for gangs and police). */
namespace CgRole
{
	enum : uint8
	{
		Crowd = 0,
		Gang = 1,
		Police = 2,
	};
}

/** LG3: per person what the drawing reads (ACityGenLife's WalkState, per instance). */
namespace CgShow
{
	enum : uint8
	{
		Off = 0,       // not in the city now (a free slot of the pool)
		Moving = 1,
		Still = 2,     // waiting at a signal, or held behind someone
		Hidden = 3,    // in an elevator
	};
}

/** A person walking: on a walkway lane (an index into the life actor's ZoneGraph storage), a
 *  distance along it and a direction (walkways are walked both ways), a pace, a side of the
 *  lane (the share of its half width, signed: + on the walker's right). LG3: a slot of the
 *  city's pool, live or free (`Active`), with its state, group, trip and avoidance. */
USTRUCT()
struct FCgLifeWalker : public FMassFragment
{
	GENERATED_BODY()

	int32 Lane = INDEX_NONE;
	int32 PrevLane = INDEX_NONE;
	float Dist = 0.f;
	float Dir = 1.f;
	float Speed = 130.f;           // cm/s: the pace (a group walks at its slowest member's)
	float Side = 0.f;
	float ZOff = 0.f;              // cm over the lane: the surface found under it
	int32 Instance = 0;
	uint32 Seed = 0;
	FVector Pos = FVector::ZeroVector;
	float Yaw = 0.f;

	// --- LG3 ---------------------------------------------------------------------------------
	uint8 Active = 1;              // (LG0's and LG1's people are always on)
	uint8 State = CgWalk::Walk;
	uint8 Crossed = 0;             // past this lane's signal (or none)
	uint8 Member = 0;              // its place in its group (0 leads)
	int32 Group = INDEX_NONE;
	float Lat = 0.f;               // cm right of the lane's own direction, now
	float Push = 0.f;              // cm the avoidance adds to where it keeps (this frame)
	float SpeedMul = 1.f;          // the avoidance's share of its pace (this frame)
	float TripLeft = 1.0e9f;       // s until it looks for a door to go in at
	int32 Door = INDEX_NONE;       // the door it comes out of or goes in at
	float T = 0.f;                 // s through the door
	FVector From = FVector::ZeroVector;   // where it left its walkway for the door
	float HoldBack = 0.f;          // cm short of a crosswalk's curb it waits
	float Pending = 0.f;           // s held back by a far person's skipped frames

	// --- lifegen_people_fixes: turning ----------------------------------------------------------
	uint8 Faced = 0;               // its yaw set once (a new person faces its way at once)
	uint8 NextAtStart = 1;         // it enters Next at Next's start (else at its end)
	uint8 bPrev = 0;               // PrevHead is the heading it left its last lane on
	int32 Next = INDEX_NONE;       // the walkway it goes on to, chosen as it nears its lane's end
	FVector3f PrevHead = FVector3f::ZeroVector;
	float PrevSegLen = 0.f;        // cm: that lane's last stretch
	float PrevHW = 0.f;            // cm: that lane's half width

	// --- LG4: life at places ------------------------------------------------------------------
	uint8 Role = 0;                // CgRole
	uint8 Visit = 0;               // through its door on a visit (it comes back out)
	uint8 Anim = 0;                // CgAnim, at a slot
	int32 Turf = INDEX_NONE;       // a gang member's turf (it walks only its walkways)
	int32 Slot = INDEX_NONE;       // the place slot it claimed
	int32 Point = INDEX_NONE;      // the slot's use point it claimed
	float Dwell = 0.f;             // s left at a slot or inside on a visit
	int32 PassedSlot = INDEX_NONE; // the last slot it passed (and chose not to use)

	// --- LG6: transit ------------------------------------------------------------------------------
	FVector To = FVector::ZeroVector;   // the train door it boards at (UE cm)
};

/** LG5: why a car drives slower than its lane allows now (FCgLifeCar::Why). */
namespace CgWhy
{
	enum : uint8
	{
		Free = 0,      // nothing in its way
		Leader = 1,    // the car in front
		Red = 2,       // a red (or amber) light at its stop line
		Person = 3,    // someone of the crowd on or entering its lane ahead
		Player = 4,    // the player
		Junction = 5,  // a junction's connector it would cross is being driven
		Box = 6,       // no room past the junction for it
	};
}

/** A car driving: on a lane of the lane graph (directed), its next lane chosen ahead, its
 *  speed and cruise speed, its model and its instance among that model's cars. LG5: a slot of
 *  the city's traffic pool, live or free (`Active`), its lane after next, its length, the
 *  junction connector it holds, why it is slowing, its wheels' turn. */
USTRUCT()
struct FCgLifeCar : public FMassFragment
{
	GENERATED_BODY()

	int32 Lane = INDEX_NONE;
	int32 Next = INDEX_NONE;
	float Dist = 0.f;              // cm along its lane (its middle)
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

	// --- LG5 -----------------------------------------------------------------------------------
	uint8 Active = 1;              // (LG0's spike cars are always on)
	uint8 Why = CgWhy::Free;
	int32 Next2 = INDEX_NONE;      // the lane after Next
	int32 Reserved = INDEX_NONE;   // the junction connector it holds (ahead of it)
	int32 Rank = INDEX_NONE;       // its place in the frame's cars sorted by lane and distance
	float Len = 480.f;             // cm, its model's length
	float Wait = 0.f;              // s waiting to enter a junction
	float Spin = 0.f;              // degrees its wheels have turned
	float Pending = 0.f;           // s held back by a far car's skipped frames
	float PedHit = 1.0e9f;         // cm ahead of its front to someone in its way (last look)
	uint8 PedPlayer = 0;           // that someone the player
};
