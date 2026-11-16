// lifegen's life at places (LG4): the Smart Object side of the place slots. Each use point of a
// live slot is a Smart Object of the world's Smart Object subsystem (USmartObjectSubsystem::
// CreateSmartObject, no actor), one slot each, its definition one per slot kind made at
// BeginPlay with a UCgPlaceBehaviorDefinition naming the kind, its behavior and clip; the
// people the walk processor sends there claim, occupy and free it through the subsystem, so
// any other user of Smart Objects in the game (an AI of the project's, storygen later) finds
// lifegen's benches, stops, stalls and queues and sees who uses them.

#pragma once

#include "CoreMinimal.h"
#include "SmartObjectDefinition.h"
#include "SmartObjectRuntime.h"
#include "SmartObjectTypes.h"
#include "CityGenLifePlaces.generated.h"

/** What a lifegen place slot is used for (each of its points' Smart Object's default behavior). */
UCLASS(EditInlineNew)
class CITYGENLIFE_API UCgPlaceBehaviorDefinition : public USmartObjectBehaviorDefinition
{
	GENERATED_BODY()
public:
	/** The slot's kind (bench, bus_stop, kiosk, vending, stall, taxi_stand, bar_queue, smoke,
	 *  gang_spot), what its user does there (sit, wait, buy, eat, queue, smoke, talk: the
	 *  plan's), the clip it plays (idle, sit, talk). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen") FName Kind;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen") FName Behavior;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen") FName Clip;
};

/** A live use point's Smart Object, its one slot, the claim lifegen holds on it. */
struct FCgPointSO
{
	FSmartObjectHandle Object;
	FSmartObjectSlotHandle Slot;
	FSmartObjectClaimHandle Claim;
};
