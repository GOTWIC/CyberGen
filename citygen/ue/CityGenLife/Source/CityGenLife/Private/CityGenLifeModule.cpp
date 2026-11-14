// The module and its console commands (the benchmark's passes and the checks drive them):
// CityGenLife.Enable [0|1] (toggling without an argument): the people and cars moving and drawn;
// CityGenLife.Respawn PEOPLE CARS: as many again on the spike's lanes; CityGenLife.Status: the
// state as one JSON line (CITYGEN_LIFE_STATUS).

#include "CityGenLifeActor.h"
#include "HAL/IConsoleManager.h"
#include "Modules/ModuleManager.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, CityGenLife)

namespace
{
	ACityGenLife* LifeIn(UWorld* World)
	{
		ACityGenLife* A = ACityGenLife::Find(World);
		if (!A)
		{
			UE_LOG(LogTemp, Warning, TEXT("CityGenLife: no CityGenLife actor in this world"));
		}
		return A;
	}

	FAutoConsoleCommandWithWorldAndArgs EnableCmd(TEXT("CityGenLife.Enable"),
		TEXT("CityGenLife.Enable [0|1]: lifegen's people and cars moving and drawn"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetEnabled(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bEnabled);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs ShadowsCmd(TEXT("CityGenLife.Shadows"),
		TEXT("CityGenLife.Shadows [0|1]: the stand-ins and the cars' bodies casting shadows"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetShadows(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bShadows);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs LumenCmd(TEXT("CityGenLife.Lumen"),
		TEXT("CityGenLife.Lumen [0|1]: the people and cars in Lumen's scene and the distance fields"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetLumen(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bInLumen);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs RebuildCmd(TEXT("CityGenLife.Rebuild"),
		TEXT("CityGenLife.Rebuild [0|1]: each frame's move also recreating the instanced components' render state"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->bRebuildRenderState = Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bRebuildRenderState;
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs RespawnCmd(TEXT("CityGenLife.Respawn"),
		TEXT("CityGenLife.Respawn PEOPLE CARS: the stand-ins and cars again, as many as given, on the spike's lanes"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenLife* A = LifeIn(World);
			if (A && Args.Num())
			{
				A->Respawn(FCString::Atoi(*Args[0]), Args.Num() > 1 ? FCString::Atoi(*Args[1]) : A->Cars);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs StatusCmd(TEXT("CityGenLife.Status"),
		TEXT("CityGenLife.Status: log the state as one JSON line"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_STATUS %s"), *A->GetStatus());
			}
		}));
}
