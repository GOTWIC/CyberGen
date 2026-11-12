// The module and its console commands (the benchmark's passes drive them):
// CityGenAtmos.Lights, .Fog, .Rain, .Wet, .MegaLights, .FarPools, .Fixtures [0|1] (toggling without an
// argument), CityGenAtmos.Tiers LIVE RANGE_M SHADOWED, .High LIVE RANGE_M (AT2), .Hour H, .Gain G,
// .Scattering S,
// .Status (the state as one JSON line). AT3: .Hour also takes day, dusk or night; .Sky and
// .Exposure [0|1] (the sky and time; the exposure held at the hour's), .TimeSpeed H (hours a
// second), .Cover C (the cloud deck's cover for the session). AT1: the plan comes with the level (the importer's
// controller and its cells' data actors), no longer from a folder (AT0's .Load and
// -CityGenAtmosPlan are gone).

#include "CityGenAtmosActor.h"
#include "HAL/IConsoleManager.h"
#include "Modules/ModuleManager.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, CityGenAtmos)

namespace
{
	ACityGenAtmos* AtmosIn(UWorld* World)
	{
		ACityGenAtmos* A = ACityGenAtmos::Find(World);
		if (!A)
		{
			UE_LOG(LogTemp, Warning, TEXT("CityGenAtmos: no CityGenAtmos actor in this world"));
		}
		return A;
	}

	bool Flag(const TArray<FString>& Args, bool bNow)
	{
		return Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !bNow;
	}

#define CG_ATMOS_TOGGLE(Var, Name, Help, Get, Set) \
	FAutoConsoleCommandWithWorldAndArgs Var(TEXT(Name), TEXT(Help), \
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World) \
		{ if (ACityGenAtmos* A = AtmosIn(World)) { A->Set(Flag(Args, A->Get)); } }));

	CG_ATMOS_TOGGLE(LightsCmd, "CityGenAtmos.Lights", "CityGenAtmos.Lights [0|1]: the plan's lights (the play features' lamps dark while on)", bLights, SetLightsOn)
	CG_ATMOS_TOGGLE(FogCmd, "CityGenAtmos.Fog", "CityGenAtmos.Fog [0|1]: height and volumetric fog by the plan's weather", bFog, SetFog)
	CG_ATMOS_TOGGLE(RainCmd, "CityGenAtmos.Rain", "CityGenAtmos.Rain [0|1]: rain streaks round the view", bRain, SetRain)
	CG_ATMOS_TOGGLE(WetCmd, "CityGenAtmos.Wet", "CityGenAtmos.Wet [0|1]: wet streets (a deferred decal round the view)", bWet, SetWet)
	CG_ATMOS_TOGGLE(PoolsCmd, "CityGenAtmos.FarPools", "CityGenAtmos.FarPools [0|1]: the play features' light pools past the live range (the far tier)", bFarPools, SetFarPools)
	CG_ATMOS_TOGGLE(MegaCmd, "CityGenAtmos.MegaLights", "CityGenAtmos.MegaLights [0|1]: MegaLights by the actor's post-process volume", bMegaLights, SetMegaLights)
	CG_ATMOS_TOGGLE(SkyCmd, "CityGenAtmos.Sky", "CityGenAtmos.Sky [0|1]: AT3's sky and time (the sun, the moon, the sky dome, the exposure by the hour)", bSky, SetSky)
	CG_ATMOS_TOGGLE(ExposureCmd, "CityGenAtmos.Exposure", "CityGenAtmos.Exposure [0|1]: the exposure held at the hour's (0: the engine's eye adaptation)", bLockExposure, SetLockExposure)
	CG_ATMOS_TOGGLE(FixturesCmd, "CityGenAtmos.Fixtures", "CityGenAtmos.Fixtures [0|1]: AT2's aviation beacons and searchlight beams", bFixtures, SetFixtures)
#undef CG_ATMOS_TOGGLE

	FAutoConsoleCommandWithWorldAndArgs HighCmd(TEXT("CityGenAtmos.High"),
		TEXT("CityGenAtmos.High LIVE RANGE_M: AT2's high tier (floods, searchlights, high masts): its size and range (m)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num() >= 2)
			{
				A->SetHigh(FCString::Atoi(*Args[0]), FCString::Atof(*Args[1]));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs TiersCmd(TEXT("CityGenAtmos.Tiers"),
		TEXT("CityGenAtmos.Tiers LIVE RANGE_M SHADOWED: the live set's size, its range (m) and how many cast shadows"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num() >= 3)
			{
				A->SetTiers(FCString::Atoi(*Args[0]), FCString::Atof(*Args[1]), FCString::Atoi(*Args[2]));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs HourCmd(TEXT("CityGenAtmos.Hour"),
		TEXT("CityGenAtmos.Hour H|day|dusk|night: the hour (the sun and the moon, the exposure, every light's schedule, MPC_CityGen's Night and Hour)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num() && !A->SetNamedHour(Args[0])) { A->SetHour(FCString::Atof(*Args[0])); }
		}));

	FAutoConsoleCommandWithWorldAndArgs TimeSpeedCmd(TEXT("CityGenAtmos.TimeSpeed"),
		TEXT("CityGenAtmos.TimeSpeed H: how fast the hour runs (game hours a second; 0 holds it)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->SetTimeSpeed(FCString::Atof(*Args[0])); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CoverCmd(TEXT("CityGenAtmos.Cover"),
		TEXT("CityGenAtmos.Cover C: the cloud deck's cover, 0 to 1 (this session)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->SetCloudCover(FCString::Atof(*Args[0])); }
		}));

	FAutoConsoleCommandWithWorldAndArgs GainCmd(TEXT("CityGenAtmos.Gain"),
		TEXT("CityGenAtmos.Gain G: a gain on every light"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->Gain = FCString::Atof(*Args[0]); A->SetTiers(A->MaxLive, A->MidRangeM, A->MaxShadowed); }
		}));

	FAutoConsoleCommandWithWorldAndArgs ScatterCmd(TEXT("CityGenAtmos.Scattering"),
		TEXT("CityGenAtmos.Scattering S: each live light's share in volumetric fog"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->VolumetricScattering = FCString::Atof(*Args[0]); A->SetTiers(A->MaxLive, A->MidRangeM, A->MaxShadowed); }
		}));

	FAutoConsoleCommandWithWorldAndArgs StatusCmd(TEXT("CityGenAtmos.Status"),
		TEXT("CityGenAtmos.Status: log the state as one JSON line"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenAtmos* A = AtmosIn(World))
			{
				UE_LOG(LogTemp, Display, TEXT("CITYGEN_ATMOS_STATUS %s"), *A->GetStatus());
			}
		}));
}
