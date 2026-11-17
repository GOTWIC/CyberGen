// The module and its console commands (the benchmark's passes and the checks drive them):
// CityGenLife.Enable [0|1] (toggling without an argument): the people and cars moving and drawn;
// CityGenLife.Respawn PEOPLE CARS: as many again on the spike's lanes; CityGenLife.Clothing
// [0|1]: the people's clothes drawn or not (a debug switch); CityGenLife.Transit [0|1] and
// CityGenLife.TransitShow WHAT (LG6); CityGenLife.Air [0|1], CityGenLife.Water [0|1] and
// CityGenLife.AirShow WHAT (LG7); CityGenLife.Status: the state as one JSON line
// (CITYGEN_LIFE_STATUS).

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

	FAutoConsoleCommandWithWorldAndArgs TiersCmd(TEXT("CityGenLife.Tiers"),
		TEXT("CityGenLife.Tiers NEAR_M NEAR_MAX MID_M FAR_M: LG1's people tiers (m from the view; how many near at once)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenLife* A = LifeIn(World);
			if (A && Args.Num() >= 4)
			{
				A->SetTiers(FCString::Atof(*Args[0]), FCString::Atoi(*Args[1]), FCString::Atof(*Args[2]), FCString::Atof(*Args[3]));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs ClothingCmd(TEXT("CityGenLife.Clothing"),
		TEXT("CityGenLife.Clothing [0|1]: the people's clothes drawn (1, the default) or not (a debug switch until LG2: off, near people out to the mid tier as MetaHuman's whole template body, mid garment slots hidden, far cards as they were)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetClothing(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bClothing);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs HourCmd(TEXT("CityGenLife.Hour"),
		TEXT("CityGenLife.Hour H: LG3's crowd at hour H (0 to 23), the live walkways filled again"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenLife* A = LifeIn(World);
			if (A && Args.Num())
			{
				A->SetHour(FCString::Atoi(*Args[0]));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CrowdCmd(TEXT("CityGenLife.Crowd"),
		TEXT("CityGenLife.Crowd SCALE [TRIP_S]: LG3's crowd at SCALE times the plan's density (within the pool), its trips TRIP_S s long on average, filled again"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenLife* A = LifeIn(World);
			if (A && Args.Num())
			{
				if (Args.Num() > 1)
				{
					A->TripS = FMath::Max(1.f, FCString::Atof(*Args[1]));
				}
				A->SetCrowdScale(FCString::Atof(*Args[0]));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs TrafficCmd(TEXT("CityGenLife.Traffic"),
		TEXT("CityGenLife.Traffic [0|1] [SCALE]: LG5's traffic on or off (toggling without an argument), at SCALE times the plan's density (within the pool), the live lanes filled again"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetTraffic(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bTraffic);
				if (Args.Num() > 1)
				{
					A->SetTrafficScale(FCString::Atof(*Args[1]));
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs ShowCmd(TEXT("CityGenLife.TrafficShow"),
		TEXT("CityGenLife.TrafficShow red|person|player|moving: the camera moved to the nearest car stopped at a red light with a queue behind it, stopped for a person, for the player, or moving (the check's shots)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->ShowTraffic(Args.Num() ? Args[0] : FString(TEXT("moving")));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs BlockCmd(TEXT("CityGenLife.BlockPlayer"),
		TEXT("CityGenLife.BlockPlayer: the walker stood in the lane of the nearest moving car, ahead of it (the check's shots)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->BlockPlayer();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs JaywalkCmd(TEXT("CityGenLife.Jaywalk"),
		TEXT("CityGenLife.Jaywalk AT_0 AT_1: the share of people crossing against the signal at danger 0 and 1 (LG3's, from the plan)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenLife* A = LifeIn(World);
			if (A && Args.Num() >= 2)
			{
				A->SetJaywalk(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]));
			}
		}));

	// --- LG4: life at places
	FAutoConsoleCommandWithWorldAndArgs PlacesCmd(TEXT("CityGenLife.Places"),
		TEXT("CityGenLife.Places [0|1]: LG4's place slots (benches, stops, stalls, queues) and shop visits on or off (toggling without an argument), the live walkways filled again"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetPlaces(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bPlaces);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs GangsCmd(TEXT("CityGenLife.Gangs"),
		TEXT("CityGenLife.Gangs [0|1]: LG4's gangs on their turf on or off (toggling without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetGangs(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bGangs);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs PoliceCmd(TEXT("CityGenLife.Police"),
		TEXT("CityGenLife.Police [0|1]: LG4's police patrols on foot and in cars on or off (toggling without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetPolice(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bPolice);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs PlaceShowCmd(TEXT("CityGenLife.PlaceShow"),
		TEXT("CityGenLife.PlaceShow sit|queue|stall|smoke|gang|gangwalk|police|patrol: the camera moved to the nearest person sitting, queueing or waiting, at a stall or kiosk, smoking at a bar, a gang at its spot or walking, a police pair, a patrol car (the check's shots)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->ShowPlace(Args.Num() ? Args[0] : FString(TEXT("sit")));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs SitCmd(TEXT("CityGenLife.SitOffset"),
		TEXT("CityGenLife.SitOffset FORWARD_CM UP_CM: where a sitter's root goes from its bench point"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenLife* A = LifeIn(World);
			if (A && Args.Num() >= 2)
			{
				A->SitOffset = FVector2D(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]));
			}
		}));

	// --- LG6: transit
	FAutoConsoleCommandWithWorldAndArgs TransitCmd(TEXT("CityGenLife.Transit"),
		TEXT("CityGenLife.Transit [0|1]: LG6's transit (every line's trains on their timetables, boarding and leaving at the stops) on or off (toggling without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetTransit(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bTransit);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs TransitShowCmd(TEXT("CityGenLife.TransitShow"),
		TEXT("CityGenLife.TransitShow board|dwell|moving|metro|monorail|maglev|sky_tube|elevated_rail: the camera moved to the nearest train at a stop with people boarding or leaving, at a stop with its doors open, moving, or moving on a line of a mode (the check's shots)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->ShowTransit(Args.Num() ? Args[0] : FString(TEXT("moving")));
			}
		}));

	// --- LG7: air and water
	FAutoConsoleCommandWithWorldAndArgs AirCmd(TEXT("CityGenLife.Air"),
		TEXT("CityGenLife.Air [0|1]: LG7's fliers (flying cars, drones, police and media fliers, aircraft, shuttles on their routes) on or off (toggling without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetAir(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bAir);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs WaterCmd(TEXT("CityGenLife.Water"),
		TEXT("CityGenLife.Water [0|1]: LG7's boats (boats, water taxis, ferries, ships on their routes) on or off (toggling without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->SetWater(Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !A->bWater);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs AirShowCmd(TEXT("CityGenLife.AirShow"),
		TEXT("CityGenLife.AirShow car|landing|layers|drone|police|media|aircraft|shuttle|boat|taxi|ferry|ship|pier: the camera moved beside the nearest vehicle of a kind, a car coming down onto its pad, the cars' layers, a boat at a pier (the check's shots)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenLife* A = LifeIn(World))
			{
				A->ShowAirWater(Args.Num() ? Args[0] : FString(TEXT("car")));
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
