// The free camera (`.`): a spectator pawn with no collision, flown with the engine's default
// bindings (W A S D, E or Space up, Q or C down, the mouse to look; the wheel sets its speed).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SpectatorPawn.h"
#include "CityGenFreeCam.generated.h"

UCLASS(NotPlaceable)
class CITYGENPLAY_API ACityGenFreeCam : public ASpectatorPawn
{
	GENERATED_BODY()

public:
	ACityGenFreeCam(const FObjectInitializer& ObjectInitializer);

	/** Top speed in cm/s (acceleration and braking follow it). */
	void SetSpeed(float CmPerSecond);
	float GetSpeed() const;
};
