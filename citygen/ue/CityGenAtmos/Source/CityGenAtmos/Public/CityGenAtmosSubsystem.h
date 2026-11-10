// AT0: in a game started with -CityGenAtmosPlan=<BUILD/atmos> (the spike's benchmark runs,
// `citygen unreal ... --bench-atmos DIR`), a world without a CityGenAtmos actor gets one, with
// the plan read from that folder. AT1 places the actor and the tiles' lights in the level at
// import instead.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "CityGenAtmosSubsystem.generated.h"

UCLASS()
class CITYGENATMOS_API UCityGenAtmosSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
};
