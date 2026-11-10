#include "CityGenAtmosSubsystem.h"

#include "CityGenAtmosActor.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

namespace
{
	bool PlanArg(FString& Out)
	{
		return FParse::Value(FCommandLine::Get(), TEXT("CityGenAtmosPlan="), Out) && !Out.IsEmpty();
	}
}

bool UCityGenAtmosSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	FString P;
	return Super::ShouldCreateSubsystem(Outer) && PlanArg(P);
}

bool UCityGenAtmosSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UCityGenAtmosSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	FString Dir;
	if (!PlanArg(Dir) || ACityGenAtmos::Find(&InWorld))
	{
		return;
	}
	FActorSpawnParameters Params;
	Params.ObjectFlags |= RF_Transient;
	ACityGenAtmos* A = InWorld.SpawnActorDeferred<ACityGenAtmos>(ACityGenAtmos::StaticClass(),
		FTransform::Identity, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (!A)
	{
		return;
	}
	A->PlanDir = Dir;
	// (the spike's passes switch everything on and off by console commands; it starts dark,
	// the play features' lamps lit, unless -CityGenAtmosOn)
	A->bLights = FParse::Param(FCommandLine::Get(), TEXT("CityGenAtmosOn"));
	A->FinishSpawning(FTransform::Identity);
}
