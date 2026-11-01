#include "CityGenFreeCam.h"

#include "Components/SphereComponent.h"
#include "GameFramework/FloatingPawnMovement.h"

ACityGenFreeCam::ACityGenFreeCam(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// through walls, as a camera should
	if (USphereComponent* Sphere = GetCollisionComponent())
	{
		Sphere->SetCollisionProfileName(TEXT("NoCollision"));
	}
	SetActorEnableCollision(false);
	bAddDefaultMovementBindings = true;
}

void ACityGenFreeCam::SetSpeed(float CmPerSecond)
{
	if (UFloatingPawnMovement* Move = Cast<UFloatingPawnMovement>(GetMovementComponent()))
	{
		Move->MaxSpeed = CmPerSecond;
		Move->Acceleration = CmPerSecond * 4.f;     // full speed in a quarter second
		Move->Deceleration = CmPerSecond * 8.f;
	}
}

float ACityGenFreeCam::GetSpeed() const
{
	const UFloatingPawnMovement* Move = Cast<UFloatingPawnMovement>(GetMovementComponent());
	return Move ? Move->MaxSpeed : 0.f;
}
