// The module and its console commands (also what `citygen unreal --check` drives):
// CityGen.Map, CityGen.FreeCam, CityGen.Menu, CityGen.Night [0|1] (toggling without an
// argument), CityGen.Teleport X Y (citygen meters) and CityGen.Status.

#include "CityGenPlayActor.h"
#include "HAL/IConsoleManager.h"
#include "Modules/ModuleManager.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, CityGenPlay)

namespace
{
	ACityGenPlay* PlayIn(UWorld* World)
	{
		ACityGenPlay* P = ACityGenPlay::Find(World);
		if (!P)
		{
			UE_LOG(LogTemp, Warning, TEXT("CityGen: no CityGenPlay actor playing in this world"));
		}
		return P;
	}

	bool Flag(const TArray<FString>& Args, bool bNow)
	{
		return Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !bNow;
	}

	FAutoConsoleCommandWithWorldAndArgs MapCommand(TEXT("CityGen.Map"),
		TEXT("CityGen.Map [0|1]: open or close the map (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetMapOpen(Flag(Args, P->IsMapOpen())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs FreeCamCommand(TEXT("CityGen.FreeCam"),
		TEXT("CityGen.FreeCam [0|1]: the free camera on or off (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetFreeCam(Flag(Args, P->IsFreeCam())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs MenuCommand(TEXT("CityGen.Menu"),
		TEXT("CityGen.Menu [0|1]: open or close the developer menu (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetDevMenuOpen(Flag(Args, P->IsDevMenuOpen())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs NightCommand(TEXT("CityGen.Night"),
		TEXT("CityGen.Night [0|1]: night or day (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetNight(Flag(Args, P->IsNight())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs TeleportCommand(TEXT("CityGen.Teleport"),
		TEXT("CityGen.Teleport X Y: teleport to citygen's (x, y) in meters"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenPlay* P = PlayIn(World);
			if (P && Args.Num() >= 2)
			{
				P->TeleportPlayerToCitygen(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs StatusCommand(TEXT("CityGen.Status"),
		TEXT("CityGen.Status: log the play features' state as one JSON line"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World))
			{
				UE_LOG(LogTemp, Display, TEXT("CITYGEN_PLAY_STATUS %s"), *P->GetStatus());
			}
		}));
}
