// The module and its console commands (the benchmark's passes drive them):
// CityGenAtmos.Lights, .Fog, .Rain, .Wet, .MegaLights, .FarPools, .Fixtures [0|1] (toggling without an
// argument), CityGenAtmos.Tiers LIVE RANGE_M SHADOWED, .High LIVE RANGE_M (AT2), .Hour H, .Gain G,
// .Scattering S,
// .Status (the state as one JSON line). AT3: .Hour also takes day, dusk or night; .Sky and
// .Exposure [0|1] (the sky and time; the exposure held at the hour's), .TimeSpeed H (hours a
// second), .Cover C (the cloud deck's cover for the session). AT4: .Air [0|1] (the fog volumes
// and plumes), .Tuned [0|1] (the plan's engine settings), .VolumeGain G, .FogView M. Visible
// lights: the console variable CityGenAtmos.Sight -1|0|1 (the live set by sight round a walker,
// the circle, by sight whatever the pawn; the actor's file defines it), .SightRange M [MAX]. AT5:
// .Weather NAME [now] (the weather state, + or - steps it), .WeatherSpeed S (the rain's age),
// .Wetness W [P] (held for shots); .Rain and .Wet switch the weather's rain (streaks, splashes,
// drips) and wet streets. AT1: the plan comes with the level (the importer's
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
	CG_ATMOS_TOGGLE(AirCmd, "CityGenAtmos.Air", "CityGenAtmos.Air [0|1]: AT4's fog volumes (mist, smog, haze) and steam and smoke plumes", bAir, SetAir)
	CG_ATMOS_TOGGLE(TunedCmd, "CityGenAtmos.Tuned", "CityGenAtmos.Tuned [0|1]: AT4's engine settings (the plan's cvars) applied, or the project's own", bTuned, SetTuned)
#undef CG_ATMOS_TOGGLE

	FAutoConsoleCommandWithWorldAndArgs VolumeGainCmd(TEXT("CityGenAtmos.VolumeGain"),
		TEXT("CityGenAtmos.VolumeGain G: AT4: a gain on every fog volume's density"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->VolumeGain = FCString::Atof(*Args[0]); A->SetAir(A->bAir); }
		}));

	FAutoConsoleCommandWithWorldAndArgs VolumeGlowCmd(TEXT("CityGenAtmos.VolumeGlow"),
		TEXT("CityGenAtmos.VolumeGlow G: AT4: the fog volumes' glow by night (their emissive, of their albedo)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->VolumeGlow = FCString::Atof(*Args[0]); A->SetAir(A->bAir); }
		}));

	FAutoConsoleCommandWithWorldAndArgs SteamGainCmd(TEXT("CityGenAtmos.SteamGain"),
		TEXT("CityGenAtmos.SteamGain G: AT4: the plumes' opacity"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->SteamGain = FCString::Atof(*Args[0]); A->SetFog(A->bFog); }
		}));

	FAutoConsoleCommandWithWorldAndArgs FogSetCmd(TEXT("CityGenAtmos.FogSet"),
		TEXT("CityGenAtmos.FogSet DENSITY [FALLOFF [EXTINCTION [PHASE_G]]]: AT4: the height fog's density and falloff, the volumetric fog's extinction scale and phase g (this session)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (!A || !Args.Num()) { return; }
			A->FogDensity = FCString::Atof(*Args[0]);
			if (Args.Num() > 1) { A->FogFalloff = FCString::Atof(*Args[1]); }
			if (Args.Num() > 2) { A->FogVolumetric = FCString::Atof(*Args[2]); }
			if (Args.Num() > 3) { A->FogPhaseG = FCString::Atof(*Args[3]); }
			A->SetFog(A->bFog);
		}));

	FAutoConsoleCommandWithWorldAndArgs FogViewCmd(TEXT("CityGenAtmos.FogView"),
		TEXT("CityGenAtmos.FogView M: AT4: the volumetric fog's reach (m)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->FogViewM = FCString::Atof(*Args[0]); A->SetFog(A->bFog); }
		}));

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

	FAutoConsoleCommandWithWorldAndArgs SightRangeCmd(TEXT("CityGenAtmos.SightRange"),
		TEXT("CityGenAtmos.SightRange M [MAX] [FADE_S]: visible lights: a walker's range (m), how many live at most, the fade's time (s)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num())
			{
				A->SightRangeM = FMath::Max(1.f, FCString::Atof(*Args[0]));
				if (Args.Num() > 1) { A->SightMax = FMath::Max(0, FCString::Atoi(*Args[1])); }
				if (Args.Num() > 2) { A->FadeS = FMath::Max(0.f, FCString::Atof(*Args[2])); }
				A->SetSight(-2);
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

	FAutoConsoleCommandWithWorldAndArgs PlumeDebugCmd(TEXT("CityGenAtmos.PlumeDebug"),
		TEXT("CityGenAtmos.PlumeDebug [MATERIAL]: AT4: log the plume components near the view (and draw them in MATERIAL, a material's path, to test)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenAtmos* A = AtmosIn(World))
			{
				UE_LOG(LogTemp, Display, TEXT("CITYGEN_ATMOS_PLUMES %s"), *A->PlumeDebug(Args.Num() ? Args[0] : FString()));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs WeatherCmd(TEXT("CityGenAtmos.Weather"),
		TEXT("CityGenAtmos.Weather NAME [now]: AT5: the weather state (clear, drizzle, rain, fog, smog), blended over the plan's transition, or at once with `now` (the streets as wet as it leaves them); + or - steps it"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (!A || !Args.Num())
			{
				return;
			}
			if (Args[0] == TEXT("+") || Args[0] == TEXT("-"))
			{
				A->StepWeather(Args[0] == TEXT("-") ? -1 : 1);
				return;
			}
			const bool bNow = Args.Num() > 1 && (Args[1] == TEXT("now") || Args[1] == TEXT("1"));
			if (!A->SetWeatherState(Args[0], bNow))
			{
				UE_LOG(LogTemp, Warning, TEXT("CityGenAtmos.Weather: no state %s"), *Args[0]);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs WeatherSpeedCmd(TEXT("CityGenAtmos.WeatherSpeed"),
		TEXT("CityGenAtmos.WeatherSpeed S: AT5: how fast the rain's age runs (1 real time): the streets wetting and drying, the puddles, the transitions"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num()) { A->WeatherSpeed = FMath::Max(0.f, FCString::Atof(*Args[0])); }
		}));

	FAutoConsoleCommandWithWorldAndArgs WetnessCmd(TEXT("CityGenAtmos.Wetness"),
		TEXT("CityGenAtmos.Wetness W [P]: AT5: the streets' wetness and the puddles' fill held (0 to 1; -1 by the rain's age again)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenAtmos* A = AtmosIn(World);
			if (A && Args.Num())
			{
				A->HoldWetness(FCString::Atof(*Args[0]), Args.Num() > 1 ? FCString::Atof(*Args[1]) : FCString::Atof(*Args[0]));
			}
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
