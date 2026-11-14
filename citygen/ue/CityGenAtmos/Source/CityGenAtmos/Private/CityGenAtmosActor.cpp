#include "CityGenAtmosActor.h"

#include "CityGenAtmosCell.h"

#include "Async/Async.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/DecalComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/LocalFogVolumeComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/SkyLight.h"
#include "Engine/Texture2D.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Math/RandomStream.h"

DEFINE_LOG_CATEGORY_STATIC(LogCityGenAtmos, Log, All);

namespace
{
	constexpr double LiveEvery = 0.2;        // s between choosing the live set
	constexpr float FadeShare = 0.2f;        // the farthest share of the mid range fades out
	// AT5: the wet streets' two decals round the view: recentred every 100 m, 1.2 km square,
	// their middle 30 m over the ground under the view, 50 m deep either side of it
	constexpr double WetSnapCm = 10000.0;
	constexpr float WetHalfCm = 60000.f;
	constexpr float WetDepthCm = 5000.f;
	constexpr double WetUpCm = 3000.0;
	constexpr float RainBoxCm = 2500.f;      // rain cards within 25 m of the view ...
	constexpr float RainTopCm = 1200.f;      // ... falling from 12 m over it (24 m in all)
	const TCHAR* AtmosMPC = TEXT("/Game/CityGen/Core/Atmos/MPC_CityGenAtmos.MPC_CityGenAtmos");
	const TCHAR* CityMPC = TEXT("/Game/CityGen/Core/MPC_CityGen.MPC_CityGen");
	const TCHAR* RainMaterial = TEXT("/Game/CityGen/Core/Atmos/M_CgRain.M_CgRain");
	const TCHAR* WetColorMaterial = TEXT("/Game/CityGen/Core/Atmos/M_CgWetColor.M_CgWetColor");
	const TCHAR* WetGlossMaterial = TEXT("/Game/CityGen/Core/Atmos/M_CgWetGloss.M_CgWetGloss");
	const TCHAR* SplashMaterial = TEXT("/Game/CityGen/Core/Atmos/M_CgSplash.M_CgSplash");
	const TCHAR* DripMaterial = TEXT("/Game/CityGen/Core/Atmos/M_CgDrip.M_CgDrip");
	constexpr int32 SplashData = 5;          // a splash card's data: its spot xyz, phase, size
	constexpr int32 DripData = 6;            // a drip card's: its top xyz, fall, phase, rate
	constexpr double SplashSkyCm = 4000.0;   // a splash's trace from 40 m over the view ...
	constexpr double SplashDownCm = 6000.0;  // ... to 60 m under it
	const TCHAR* RainMesh = TEXT("/Engine/BasicShapes/Plane.Plane");
	// AT2: the fixtures' stand-ins: a red glow per aviation light, a cone per searchlight's beam
	const TCHAR* BeaconMaterialPath = TEXT("/Game/CityGen/Core/Atmos/M_CgBeacon.M_CgBeacon");
	const TCHAR* BeamMaterialPath = TEXT("/Game/CityGen/Core/Atmos/M_CgBeam.M_CgBeam");
	const TCHAR* BeaconMesh = TEXT("/Engine/BasicShapes/Sphere.Sphere");
	const TCHAR* BeamMesh = TEXT("/Engine/BasicShapes/Cone.Cone");
	constexpr float BeaconCm = 90.f;         // a beacon's glow: 0.9 m across
	constexpr float BeamCm = 40000.f;        // a beam drawn 400 m long ...
	constexpr float BeamSpread = 1.6f;       // ... this times its cone wide, as the haze shows it
	constexpr float BeaconOn = 24.f;         // the glow's emissive on ...
	constexpr float BeamBase = 0.08f;        // ... and a beam's
	// AT3: the sky dome (M_CgSky on the engine's sphere, 50 cm across: 50 km round the view)
	const TCHAR* SkyMaterialPath = TEXT("/Game/CityGen/Core/Atmos/M_CgSky.M_CgSky");
	const TCHAR* DomeMesh = TEXT("/Engine/BasicShapes/Sphere.Sphere");
	constexpr float DomeScale = 100000.f;
	constexpr double DomeRecenterCm = 2000000.0; // (20 km: the dome is 50 km round)
	const FName SunKey(TEXT("cg.key=lighting.sun"));
	const FName SkyKey(TEXT("cg.key=lighting.sky"));
	constexpr double TimeEvery = 1.0 / 15.0; // s between moving the sun while the hour runs
	// AT4: the plumes' cards (M_CgSteam on the engine's plane, rising by world position offset)
	const TCHAR* SteamMaterialPath = TEXT("/Game/CityGen/Core/Atmos/M_CgSteam.M_CgSteam");
	constexpr int32 PlumeData = 11;          // a card's custom data: foot xyz, phase, period,
	                                         // rise, width, opacity, albedo rgb
	constexpr float VolumeFalloff = 250.f;   // a volume's height fog falloff (Unreal's units)
	constexpr float PlumeSpeedCm = 120.f;    // steam rises about 1.2 m/s ...
	constexpr float SmokeSpeedCm = 200.f;    // ... smoke 2 m/s
	constexpr double FixturesEvery = 0.5;    // s between making and dropping cells' fixtures
	// AT7: the far city's cards (M_CgFarGlow turned to the eye, M_CgFarFlat lying on its
	// surface), instanced on the engine's plane per 1 km block
	const TCHAR* FarGlowMaterialPath = TEXT("/Game/CityGen/Core/Atmos/M_CgFarGlow.M_CgFarGlow");
	const TCHAR* FarFlatMaterialPath = TEXT("/Game/CityGen/Core/Atmos/M_CgFarFlat.M_CgFarFlat");
	constexpr double FarBlockCm = 102400.0;
	constexpr int32 FarGlowData = 12;        // a glow's: middle xyz, rgb, size, tier, period,
	                                         // on share, phase, level
	constexpr int32 FarFlatData = 11;        // a pool's or wash's: middle xyz, rgb, type,
	                                         // radius (half width), falloff (half height),
	                                         // tier, level
	constexpr float FarGlowBoundCm = 2500.f; // a glow instance's bounds (its card grows with
	                                         // distance to a few pixels: 25 m at 10 km)
	constexpr double FarSettleS = 0.5;       // cells registering: the cards built once they rest
	// visible lights: the walker's class (the play features', by name) and the mode's switch
	const FName WalkerClass(TEXT("CityGenWalker"));
	TAutoConsoleVariable<int32> CVarSight(TEXT("CityGenAtmos.Sight"), -1,
		TEXT("The live set by sight: -1 round a walker (the play features' CityGenWalker), the circle round any other pawn; 0 the circle; 1 the lights in sight"),
		ECVF_Default);

	uint32 Hash(uint32 A, uint32 B)
	{
		uint32 H = A * 0x9E3779B1u ^ (B + 0x7F4A7C15u + (A << 6) + (A >> 2));
		H ^= H >> 16; H *= 0x85EBCA6Bu; H ^= H >> 13; H *= 0xC2B2AE35u; H ^= H >> 16;
		return H;
	}
}

ACityGenAtmos::ACityGenAtmos()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	// (an AInfo is hidden in the game, and a hidden actor's components draw nothing)
	SetHidden(false);
#if WITH_EDITORONLY_DATA
	bIsSpatiallyLoaded = false;
#endif
}

ACityGenAtmos* ACityGenAtmos::Find(const UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	// (the first; a loop that returns at once fails Clang's -Wunreachable-code-loop-increment,
	// an error on the Mac's build)
	TActorIterator<ACityGenAtmos> It(const_cast<UWorld*>(World));
	return It ? *It : nullptr;
}

void ACityGenAtmos::BeginPlay()
{
	Super::BeginPlay();
	bBegun = true;
	CoverNow = CloudCover;
	AtmosCollection = LoadObject<UMaterialParameterCollection>(nullptr, AtmosMPC);
	CityCollection = LoadObject<UMaterialParameterCollection>(nullptr, CityMPC);
	BeaconMaterial = LoadObject<UMaterialInterface>(nullptr, BeaconMaterialPath);
	BeamMaterial = LoadObject<UMaterialInterface>(nullptr, BeamMaterialPath);
	SteamMaterial = LoadObject<UMaterialInterface>(nullptr, SteamMaterialPath);
	// AT4: the engine settings the air's budget needs, while the controller runs
	ApplyCVars(bTuned);
	// visible lights: the plan's sight raster from its runs
	MakeSight();
	// (the cells streamed in before it began play: each later one registers itself)
	for (TActorIterator<ACityGenAtmosCell> It(GetWorld()); It; ++It)
	{
		if (It->HasActorBegunPlay() || It->IsActorBeginningPlay())
		{
			RegisterCell(*It);
		}
	}
	UE_LOG(LogCityGenAtmos, Display, TEXT("CityGen atmos: %s, %d schedules, %d cells with %d lights in at begin play, sight raster %s"),
		*City, ScheduleNames.Num(), SlotOfActor.Num(), RegisteredLights,
		Sight.IsValid() ? *FString::Printf(TEXT("%dx%d"), Sight->W, Sight->H) : TEXT("none"));
	UpdateFixtureCells(ViewLocation());
	EnsureVolume();
	// AT3: the sky and time (the importer's sun, sky light and a sky dome)
	FindLighting();
	EnsureDome();
	ApplyTime();
	// AT5: the plan's start weather, settled (the streets as wet as it leaves them)
	if (HasWeather())
	{
		SetWeatherState(WeatherIndex(WeatherStart) != INDEX_NONE ? WeatherStart : WeatherNames[0], true);
	}
	SetFog(bFog);
	SetAir(bAir);
	SetRain(bRain);
	SetWet(bWet);
	SetMegaLights(bMegaLights);
	SetLightsOn(bLights);
	// AT6: the look's post (its district raster from its runs)
	MakePostRaster();
	SetPost(bPost);
}

void ACityGenAtmos::EndPlay(const EEndPlayReason::Type Reason)
{
	FinishSight();
	SetPlayLamps(true);
	DropFar();
	ReleaseAll();
	ReleaseVolumes();
	ApplyCVars(false);
	Super::EndPlay(Reason);
}

// -- the cells --

FIntPoint ACityGenAtmos::CellOf(const FVector& P) const
{
	const double C = FMath::Max(1.0, double(CellM) * 100.0);
	return FIntPoint(FMath::FloorToInt32(P.X / C), FMath::FloorToInt32(P.Y / C));
}

void ACityGenAtmos::RegisterCell(ACityGenAtmosCell* Cell)
{
	if (!Cell || SlotOfActor.Contains(Cell))
	{
		return;
	}
	int32 N = Cell->LightInts.Num() / CityGenAtmosPack::Ints;
	if (Cell->LightFloats.Num() < N * CityGenAtmosPack::Floats)
	{
		N = 0;
	}
	// AT4: a cell may hold only fog volumes or plumes
	int32 NV = Cell->VolumeInts.Num() / CityGenAtmosPack::VolInts;
	if (Cell->VolumeFloats.Num() < NV * CityGenAtmosPack::VolFloats)
	{
		NV = 0;
	}
	int32 NE = Cell->EmitterInts.Num() / CityGenAtmosPack::EmitInts;
	if (Cell->EmitterFloats.Num() < NE * CityGenAtmosPack::EmitFloats)
	{
		NE = 0;
	}
	// AT5: or only drip lines
	const int32 ND = Cell->DripFloats.Num() / CityGenAtmosPack::DripFloats;
	// AT7: or only far cards
	int32 NF = Cell->FarInts.Num();
	if (Cell->FarFloats.Num() < NF * CityGenAtmosPack::FarFloats)
	{
		NF = 0;
	}
	if (N <= 0 && NV <= 0 && NE <= 0 && ND <= 0 && NF <= 0)
	{
		return;
	}
	const int32 Slot = FreeSlots.Num() ? FreeSlots.Pop(EAllowShrinking::No) : Slots.AddDefaulted();
	FSlot& S = Slots[Slot];
	S.Actor = Cell;
	S.Key = CellOf(Cell->GetActorLocation());
	S.bUsed = true;
	S.Lights.Reset(N);
	S.High.Reset();
	const float* F = Cell->LightFloats.GetData();
	const int32* I = Cell->LightInts.GetData();
	for (int32 k = 0; k < N; ++k)
	{
		const float* f = F + k * CityGenAtmosPack::Floats;
		const int32* i = I + k * CityGenAtmosPack::Ints;
		FCityGenAtmosLight L;
		L.Pos = FVector(f[0], f[1], f[2]);
		L.Rot = FRotator(f[3], f[4], 0.f);
		L.Size = FVector2f(f[5], f[6]);
		L.SourceCm = f[7];
		L.Intensity = f[8];
		L.Color = FLinearColor(f[9], f[10], f[11]);
		L.ReachCm = f[12];
		L.Inner = f[13];
		L.Outer = f[14];
		L.Flicker = f[15];
		L.AnimPeriod = f[16];
		L.AnimAmount = f[17];
		L.AnimPhase = f[18];
		const uint32 Flags = uint32(i[0]);
		L.Shape = uint8(Flags & 3u);
		L.bShadow = (Flags & 4u) != 0;
		L.bNearOnly = (Flags & 8u) != 0;
		L.bOn = (Flags & 16u) != 0;
		L.bNoSpecular = (Flags & 32u) != 0;
		L.bHigh = (Flags & 64u) != 0;
		L.Schedule = uint8((Flags >> 8) & 0xffu);
		L.Kind = uint8((Flags >> 16) & 0xffu);
		L.Anim = uint8((Flags >> 28) & 3u);
		L.Seed = uint32(i[1]);
		if (L.bHigh)
		{
			S.High.Add(S.Lights.Num());
		}
		S.Lights.Add(L);
	}
	S.Volumes.Reset(NV);
	for (int32 k = 0; k < NV; ++k)
	{
		const float* f = Cell->VolumeFloats.GetData() + k * CityGenAtmosPack::VolFloats;
		const uint32 Flags = uint32(Cell->VolumeInts[k * CityGenAtmosPack::VolInts]);
		FCityGenAtmosVolume V;
		V.Pos = FVector(f[0], f[1], f[2]);
		V.Yaw = f[3];
		V.Ext = FVector(FMath::Max(100.f, f[4]), FMath::Max(100.f, f[5]), FMath::Max(100.f, f[6]));
		V.Density = f[7];
		V.Floor = f[8];
		V.PhaseG = f[9];
		V.Albedo = FLinearColor(f[10], f[11], f[12]);
		V.Glow = f[13];
		V.Schedule = uint8(Flags & 0xffu);
		V.Kind = uint8((Flags >> 8) & 0xffu);
		S.Volumes.Add(V);
	}
	S.Emitters = NE;
	S.Drips.Reset();
	if (ND > 0)
	{
		S.Drips.Append(Cell->DripFloats.GetData(), ND * CityGenAtmosPack::DripFloats);
		DripLines += ND;
		DripsAt = -1.0;
	}
	// AT7: its far cards (drawn once the cells rest: RebuildFar)
	S.Far.Reset();
	S.FarFlags.Reset();
	if (NF > 0)
	{
		S.Far.Append(Cell->FarFloats.GetData(), NF * CityGenAtmosPack::FarFloats);
		S.FarFlags.Append(Cell->FarInts.GetData(), NF);
		FarCards += NF;
		bFarDirty = true;
		FarDirtyAt = FPlatformTime::Seconds();
	}
	// (its beacons, beams and plumes when the view comes near it: UpdateFixtureCells)
	S.bMade = false;
	FixturesAt = -1.0;
	SlotsAt.FindOrAdd(S.Key).Add(Slot);
	SlotOfActor.Add(Cell, Slot);
	RegisteredVolumes += NV;
	RegisteredEmitters += NE;
	VolumesAt = -1.0;
	RegisteredLights += N;
	++Registrations;
	LiveAt = -1.0;
}

void ACityGenAtmos::UnregisterCell(ACityGenAtmosCell* Cell)
{
	int32 Slot = INDEX_NONE;
	if (!Cell || !SlotOfActor.RemoveAndCopyValue(Cell, Slot) || !Slots.IsValidIndex(Slot))
	{
		return;
	}
	FSlot& S = Slots[Slot];
	TArray<int64> Keys;
	Live.GetKeys(Keys);
	for (int64 K : Keys)
	{
		if (int32(K >> 24) == Slot)
		{
			Release(K);
		}
	}
	Flickering.RemoveAll([Slot](int64 K) { return int32(K >> 24) == Slot; });
	// (visible lights: its keys go stale, so a sweep running now is not taken, nor what it saw)
	++SightGeneration;
	for (auto It = SeenAt.CreateIterator(); It; ++It)
	{
		if (int32(It.Key() >> 24) == Slot)
		{
			It.RemoveCurrent();
		}
	}
	S.bMade = false;
	if (TArray<int32>* At = SlotsAt.Find(S.Key))
	{
		At->Remove(Slot);
		if (At->Num() == 0)
		{
			SlotsAt.Remove(S.Key);
		}
	}
	RegisteredLights -= S.Lights.Num();
	DropFixtures(Slot);
	// AT4: its live fog volumes back to the pool, its plumes gone
	TArray<int64> VKeys;
	LiveVolumes.GetKeys(VKeys);
	for (int64 K : VKeys)
	{
		if (int32(K >> 24) == Slot)
		{
			TObjectPtr<USceneComponent> C;
			if (LiveVolumes.RemoveAndCopyValue(K, C) && C)
			{
				C->SetVisibility(false);
				FreeVolumes.Add(C);
			}
		}
	}
	DropPlumes(Slot);
	RegisteredVolumes -= S.Volumes.Num();
	RegisteredEmitters -= S.Emitters;
	S.Volumes.Reset();
	S.Emitters = 0;
	DripLines -= S.Drips.Num() / CityGenAtmosPack::DripFloats;
	S.Drips.Reset();
	DripsAt = -1.0;
	// AT7: its far cards out (drawn again once the cells rest)
	if (S.FarFlags.Num())
	{
		FarCards -= S.FarFlags.Num();
		bFarDirty = true;
		FarDirtyAt = FPlatformTime::Seconds();
	}
	S.Far.Reset();
	S.FarFlags.Reset();
	VolumesAt = -1.0;
	S.Lights.Reset();
	S.High.Reset();
	S.Actor.Reset();
	S.bUsed = false;
	FreeSlots.Add(Slot);
	LiveAt = -1.0;
}

const FCityGenAtmosLight* ACityGenAtmos::LightOf(int64 Key) const
{
	const int32 Slot = int32(Key >> 24);
	const int32 Index = int32(Key & 0xffffff);
	if (!Slots.IsValidIndex(Slot) || !Slots[Slot].bUsed || !Slots[Slot].Lights.IsValidIndex(Index))
	{
		return nullptr;
	}
	return &Slots[Slot].Lights[Index];
}

float ACityGenAtmos::ScheduleAt(uint8 Schedule) const
{
	const int32 Base = int32(Schedule) * 24;
	if (Base + 24 > ScheduleHours.Num())
	{
		return 1.f;
	}
	// (AT3: between one hour's value and the next, so lights come on as the hour runs)
	const float Hr = FMath::Fmod(Hour + 24.f, 24.f);
	const int32 H = FMath::Clamp(FMath::FloorToInt32(Hr), 0, 23);
	const float F = FMath::Clamp(Hr - float(H), 0.f, 1.f);
	return FMath::Lerp(ScheduleHours[Base + H], ScheduleHours[Base + (H + 1) % 24], F);
}

float ACityGenAtmos::Scale() const
{
	return FMath::Pow(2.f, SceneEV100 - PlanEV100) * Gain;
}

// -- the live set --

FVector ACityGenAtmos::ViewLocation(FRotator* OutRot) const
{
	const UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (PC && PC->PlayerCameraManager)
	{
		if (OutRot) { *OutRot = PC->PlayerCameraManager->GetCameraRotation(); }
		return PC->PlayerCameraManager->GetCameraLocation();
	}
	if (OutRot) { *OutRot = FRotator::ZeroRotator; }
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	return Pawn ? Pawn->GetActorLocation() : FVector::ZeroVector;
}

ULocalLightComponent* ACityGenAtmos::Take(uint8 Shape)
{
	TArray<TObjectPtr<ULocalLightComponent>>& Free = Shape == 0 ? FreeSpot : (Shape == 1 ? FreePoint : FreeRect);
	if (Free.Num())
	{
		return Free.Pop(EAllowShrinking::No);
	}
	ULocalLightComponent* C = nullptr;
	if (Shape == 0)
	{
		C = NewObject<USpotLightComponent>(this);
	}
	else if (Shape == 1)
	{
		C = NewObject<UPointLightComponent>(this);
	}
	else
	{
		C = NewObject<URectLightComponent>(this);
	}
	C->SetMobility(EComponentMobility::Movable);
	C->SetupAttachment(RootComponent);
	C->SetUsingAbsoluteLocation(true);
	C->SetUsingAbsoluteRotation(true);
	C->SetCastShadows(false);
	C->SetIntensityUnits(Shape == 2 ? ELightUnits::Nits : ELightUnits::Candelas);
	C->SetVisibility(false);
	C->RegisterComponent();
	AllLights.Add(C);
	return C;
}

void ACityGenAtmos::Release(int64 Key)
{
	TObjectPtr<ULocalLightComponent> C;
	Alpha.Remove(Key);
	FadeOf.Remove(Key);
	FlickerSet.Remove(Key);
	if (!Live.RemoveAndCopyValue(Key, C) || !C)
	{
		return;
	}
	C->SetVisibility(false);
	if (Shadowed.Remove(Key) > 0)
	{
		C->SetCastShadows(false);
	}
	// (back to the pool of its shape: its own class says which; a spot is a point light too)
	if (C->IsA<USpotLightComponent>())
	{
		FreeSpot.Add(C);
	}
	else if (C->IsA<URectLightComponent>())
	{
		FreeRect.Add(C);
	}
	else
	{
		FreePoint.Add(C);
	}
}

void ACityGenAtmos::ReleaseAll()
{
	TArray<int64> Keys;
	Live.GetKeys(Keys);
	for (int64 K : Keys)
	{
		Release(K);
	}
	Flickering.Reset();
	FlickerSet.Reset();
	FadeOf.Reset();
	Alpha.Reset();
	Wanted.Reset();
}

bool ACityGenAtmos::InBurst(const FCityGenAtmosLight& L, double T)
{
	// a flickering light flickers in bursts, steady between them (dlss_lamps_flicker: it
	// flickered a third of every second before): a burst of BurstS[0] to [1] s once every
	// CycleS[0] to [1] s, its cycle and length from the light's seed, the burst's place in
	// each cycle from the cycle's hash; a dying tube (flicker 0.8 and deeper) every
	// DyingCycleS, longer. Stateless: the same at any frame rate and on every machine.
	const bool bDying = L.Flicker >= 0.8f;
	const float U0 = float(Hash(L.Seed, 101u) & 0xffff) / 65536.f;
	const float U1 = float(Hash(L.Seed, 103u) & 0xffff) / 65536.f;
	const float U2 = float(Hash(L.Seed, 107u) & 0xffff) / 65536.f;
	const double Cycle = bDying ? 4.0 + 6.0 * U0 : 9.0 + 17.0 * U0;
	const double Burst = bDying ? 0.8 + 1.2 * U1 : 0.35 + 0.65 * U1;
	const double Tc = T / Cycle + U2;
	const double C = FMath::FloorToDouble(Tc);
	const uint32 Ci = uint32(int64(C) & 0x7fffffff);
	const double Start = (float(Hash(L.Seed ^ 0x5bd1e995u, Ci) & 0xffff) / 65536.f) * (Cycle - Burst);
	const double Off = (Tc - C) * Cycle;
	return Off >= Start && Off < Start + Burst;
}

void ACityGenAtmos::SetLevel(ULocalLightComponent* C, int64 Key, const FCityGenAtmosLight& L, double T, uint32 Step) const
{
	// a light's intensity now: its own, the exposure's scale, its schedule, its blink, its
	// flicker's drop (a hash of its seed and the 1/12 s step: no state, the same at any frame
	// rate), and its fades by distance and in time
	float Drop = 0.f;
	if (L.Flicker > 0.f && InBurst(L, T))
	{
		const float R = float(Hash(L.Seed, Step) & 0xffff) / 65535.f;
		Drop = R < 0.18f ? L.Flicker : (R < 0.3f ? 0.3f * L.Flicker : 0.f);
	}
	const float* Fade = FadeOf.Find(Key);
	const float* A = Alpha.Find(Key);
	C->SetIntensity(L.Intensity * Scale() * ScheduleAt(L.Schedule) * (1.f - Drop) * AnimGain(L, T) *
		(Fade ? *Fade : 1.f) * (A ? *A : 1.f));
}

void ACityGenAtmos::ApplyLight(ULocalLightComponent* C, const FCityGenAtmosLight& L, int64 Key, bool bShadowed)
{
	C->SetWorldLocationAndRotation(L.Pos, L.Rot);
	C->SetLightColor(L.Color);
	C->SetAttenuationRadius(L.ReachCm);
	// (AT4: light shafts by kind: the strong lights scatter in the haze, the small many none)
	C->SetVolumetricScatteringIntensity(VolumetricScattering * ScatterOf(L.Kind));
	// (a sign's or shopfront's stand-in leaves glossy surfaces to reflect the face itself)
	C->SetSpecularScale(L.bNoSpecular ? 0.f : 1.f);
	if (L.Shape == 2)
	{
		URectLightComponent* R = CastChecked<URectLightComponent>(C);
		R->SetSourceWidth(L.Size.X);
		R->SetSourceHeight(L.Size.Y);
		R->SetBarnDoorAngle(L.Inner);
	}
	else
	{
		if (L.Shape == 0)
		{
			USpotLightComponent* S = CastChecked<USpotLightComponent>(C);
			S->SetInnerConeAngle(L.Inner);
			S->SetOuterConeAngle(L.Outer);
		}
		CastChecked<UPointLightComponent>(C)->SetSourceRadius(L.SourceCm);
	}
	const double T = WorldTime();
	if (L.Anim == 2)
	{
		C->SetWorldRotation(AnimRot(L, T));
	}
	SetLevel(C, Key, L, T, uint32(FPlatformTime::Seconds() * 12.0));
	if (bool(C->CastShadows) != bShadowed)
	{
		C->SetCastShadows(bShadowed);
	}
	C->SetVisibility(true);
}

void ACityGenAtmos::PickCircle(const FVector& View, TArray<FPick>& Mid, TArray<FPick>& High) const
{
	// the nearest MaxLive within MidRangeM (a near-only light within NearRangeM), and AT2's
	// high tier, a pool of its own: the nearest MaxHigh within HighRangeM
	const double MidCm = double(MidRangeM) * 100.0;
	const double NearCm = double(NearRangeM) * 100.0;
	const double HighCm = double(HighRangeM) * 100.0;
	const double CellCm = FMath::Max(1.0, double(CellM) * 100.0);
	const int32 Reach = FMath::CeilToInt32(FMath::Max(MidCm, MaxHigh > 0 ? HighCm : 0.0) / CellCm);
	const FIntPoint VC = CellOf(View);
	for (int32 dx = -Reach; dx <= Reach; ++dx)
	{
		for (int32 dy = -Reach; dy <= Reach; ++dy)
		{
			const TArray<int32>* At = SlotsAt.Find(FIntPoint(VC.X + dx, VC.Y + dy));
			if (!At)
			{
				continue;
			}
			for (int32 Slot : *At)
			{
				const TArray<FCityGenAtmosLight>& Ls = Slots[Slot].Lights;
				for (int32 i = 0; i < Ls.Num(); ++i)
				{
					const FCityGenAtmosLight& L = Ls[i];
					if (!L.bOn || ScheduleAt(L.Schedule) < 0.05f)
					{
						continue;
					}
					const double D = FVector::Dist(L.Pos, View);
					if (L.bHigh)
					{
						// (a searchlight before the floods: its beam reads from afar)
						if (MaxHigh > 0 && D <= HighCm)
						{
							High.Add({L.Anim == 2 ? 0.25 * D : D, D, LiveKey(Slot, i)});
						}
						continue;
					}
					if (D > MidCm || (L.bNearOnly && D > NearCm))
					{
						continue;
					}
					Mid.Add({D, D, LiveKey(Slot, i)});
				}
			}
		}
	}
}

// -- visible lights --

bool FCityGenSight::Visible(const FVector& Eye, const FVector& Light) const
{
	const FVector D = Light - Eye;
	const double Len = D.Size();
	if (Len <= SkipEyeCm + SkipLightCm || W <= 0 || H <= 0)
	{
		return true;
	}
	const double Ta = SkipEyeCm / Len;
	const double Tb = 1.0 - SkipLightCm / Len;
	// the cells the segment crosses in plan (row 0 the raster's min Y), from Ta to Tb
	const double Ua = (Eye.X + Ta * D.X - X0) / CellCm;
	const double Wa = (Eye.Y + Ta * D.Y - Y0) / CellCm;
	const double Du = D.X / CellCm;
	const double Dw = D.Y / CellCm;
	int32 i = FMath::FloorToInt32(Ua);
	int32 j = FMath::FloorToInt32(Wa);
	const int32 Si = Du > 0.0 ? 1 : -1;
	const int32 Sj = Dw > 0.0 ? 1 : -1;
	constexpr double Big = 1e30;
	double Nu = Du != 0.0 ? (double(i + (Du > 0.0 ? 1 : 0)) - Ua) / Du + Ta : Big;
	double Nw = Dw != 0.0 ? (double(j + (Dw > 0.0 ? 1 : 0)) - Wa) / Dw + Ta : Big;
	const double StU = Du != 0.0 ? FMath::Abs(1.0 / Du) : Big;
	const double StW = Dw != 0.0 ? FMath::Abs(1.0 / Dw) : Big;
	double T = Ta;
	bool bFirst = true;
	while (T < Tb)
	{
		const double Out = FMath::Min3(Nu, Nw, Tb);
		// (the eye's own cell left out: a camera at a facade or in a doorway stands in it)
		if (!bFirst && i >= 0 && i < W && j >= 0 && j < H)
		{
			const uint32 V = Cells[int64(j) * W + i];
			if (V != 0u)
			{
				const double Za = Eye.Z + T * D.Z;
				const double Zb = Eye.Z + Out * D.Z;
				const double Lo = FMath::Min(Za, Zb);
				const double Hi = FMath::Max(Za, Zb);
				const double G = double((V >> 16) & 0xffu) * GroundCm;
				if (Lo < G)
				{
					return false;
				}
				const uint32 Top = V & 0xffu;
				if (Top != 0u)
				{
					const uint32 Bq = (V >> 8) & 0xffu;
					const double Bottom = Bq ? G + double(Bq) * BottomCm : -Big;
					if (Lo < double(Top) * TopCm && Hi > Bottom)
					{
						return false;
					}
				}
			}
		}
		bFirst = false;
		if (Out >= Tb)
		{
			break;
		}
		if (Nu < Nw)
		{
			i += Si;
			Nu += StU;
		}
		else
		{
			j += Sj;
			Nw += StW;
		}
		T = Out;
	}
	return true;
}

double FCityGenSight::GroundAt(const FVector& P) const
{
	const int32 i = FMath::FloorToInt32((P.X - X0) / CellCm);
	const int32 j = FMath::FloorToInt32((P.Y - Y0) / CellCm);
	if (i < 0 || i >= W || j < 0 || j >= H)
	{
		return 0.0;
	}
	return double((Cells[int64(j) * W + i] >> 16) & 0xffu) * GroundCm;
}

void ACityGenAtmos::MakeSight()
{
	Sight.Reset();
	const int64 N = int64(SightWidth) * int64(SightHeight);
	if (N <= 0 || SightBounds.Num() < 4 || SightRuns.Num() < 2 || SightCellM <= 0.f)
	{
		return;
	}
	TSharedPtr<FCityGenSight, ESPMode::ThreadSafe> G = MakeShared<FCityGenSight, ESPMode::ThreadSafe>();
	G->W = SightWidth;
	G->H = SightHeight;
	G->X0 = SightBounds[0];
	G->Y0 = SightBounds[1];
	G->CellCm = double(SightCellM) * 100.0;
	G->TopCm = double(SightTopStepM) * 100.0;
	G->BottomCm = double(SightBottomStepM) * 100.0;
	G->GroundCm = double(SightGroundStepM) * 100.0;
	G->SkipEyeCm = double(SightSkipEyeM) * 100.0;
	G->SkipLightCm = double(SightSkipLightM) * 100.0;
	G->Cells.SetNumUninitialized(N);
	int64 At = 0;
	for (int32 k = 0; k + 1 < SightRuns.Num(); k += 2)
	{
		const int64 C = SightRuns[k];
		const uint32 V = uint32(SightRuns[k + 1]);
		if (C <= 0 || At + C > N)
		{
			UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: the sight raster's runs overrun its %lldx%lld cells; walking keeps the circle"),
				int64(SightWidth), int64(SightHeight));
			return;
		}
		for (int64 c = 0; c < C; ++c)
		{
			G->Cells[At + c] = V;
		}
		At += C;
	}
	if (At != N)
	{
		UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: the sight raster's runs cover %lld of %lld cells; walking keeps the circle"), At, N);
		return;
	}
	Sight = G;
}

bool ACityGenAtmos::IsWalker() const
{
	// (the play features' walker by its class's name: no link between the plugins)
	const UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	for (const UClass* C = Pawn ? Pawn->GetClass() : nullptr; C; C = C->GetSuperClass())
	{
		if (C->GetFName() == WalkerClass)
		{
			return true;
		}
	}
	return false;
}

bool ACityGenAtmos::SightWanted() const
{
	if (!bSight || !Sight.IsValid() || SightRangeM <= 0.f)
	{
		return false;
	}
	const int32 Mode = CVarSight.GetValueOnGameThread();
	return Mode >= 0 ? Mode > 0 : IsWalker();
}

void ACityGenAtmos::SetSight(int32 Mode)
{
	// (under -1: the mode as it is, the range and size taken again)
	if (Mode >= -1)
	{
		CVarSight->Set(FMath::Min(Mode, 1), ECVF_SetByConsole);
	}
	LiveAt = -1.0;
	if (bLights)
	{
		SetPlayLamps(!bShowing);
	}
}

void ACityGenAtmos::LaunchSight(const FVector& View, double Now)
{
	// a sweep: every light on within SightRangeM (a near-only light within NearRangeM) tested
	// on a worker thread from the eye, at the light and, failing that, where its light lands (a
	// spot's pool on the ground or along its aim, a face's patch in front of it, the floor
	// under a point): a lamp round a corner whose pool shows stays
	if (!Sight.IsValid() || bSightRunning || (SightAt >= 0.0 && Now - SightAt < LiveEvery))
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	SightAt = Now;
	const double RangeCm = double(SightRangeM) * 100.0;
	const double Range2 = RangeCm * RangeCm;
	const double NearCm = double(NearRangeM) * 100.0;
	const double CellCm = FMath::Max(1.0, double(CellM) * 100.0);
	const int32 Reach = FMath::CeilToInt32(RangeCm / CellCm);
	const FIntPoint VC = CellOf(View);
	TArray<FCityGenSightJob> Jobs;
	Jobs.Reserve(FMath::Max(1024, SightTested));
	// (each schedule's level at the hour, once a sweep)
	TArray<float> Level;
	Level.SetNumUninitialized(256);
	for (int32 s = 0; s < 256; ++s)
	{
		Level[s] = ScheduleAt(uint8(s));
	}
	const double Near2 = NearCm * NearCm;
	for (int32 dx = -Reach; dx <= Reach; ++dx)
	{
		for (int32 dy = -Reach; dy <= Reach; ++dy)
		{
			const TArray<int32>* At = SlotsAt.Find(FIntPoint(VC.X + dx, VC.Y + dy));
			if (!At)
			{
				continue;
			}
			for (int32 Slot : *At)
			{
				TArray<FCityGenAtmosLight>& Ls = Slots[Slot].Lights;
				for (int32 i = 0; i < Ls.Num(); ++i)
				{
					FCityGenAtmosLight& L = Ls[i];
					if (!L.bOn || Level[L.Schedule] < 0.05f)
					{
						continue;
					}
					const double D2 = FVector::DistSquared(L.Pos, View);
					if (D2 > Range2 || (L.bNearOnly && D2 > Near2))
					{
						continue;
					}
					if (!L.bLandSet)
					{
						// where its light lands, found once: a spot aimed down its pool on the
						// ground (at most 0.8 of its reach out), a point the floor under it, a
						// face, an uplight or a flood a patch along its aim
						const FVector Dir = L.Rot.Vector();
						const double Ground = Sight->GroundAt(L.Pos);
						FVector B = L.Pos;
						if (L.Shape == 0 && Dir.Z < -0.3)
						{
							const double Along = FMath::Min((L.Pos.Z - Ground - 30.0) / -Dir.Z, 0.8 * L.ReachCm);
							B = L.Pos + Dir * FMath::Max(0.0, Along);
						}
						else if (L.Shape == 1)
						{
							B = L.Pos - FVector(0.0, 0.0, FMath::Clamp(L.Pos.Z - Ground - 30.0, 0.0, 0.5 * L.ReachCm));
						}
						else
						{
							B = L.Pos + Dir * FMath::Min(0.5 * L.ReachCm, L.Shape == 2 ? 600.0 : 1500.0);
						}
						L.Land = FVector3f(B);
						L.bLand = FVector::DistSquared(B, L.Pos) > 200.0 * 200.0;
						L.bLandSet = true;
					}
					FCityGenSightJob& J = Jobs.AddDefaulted_GetRef();
					J.Key = LiveKey(Slot, i);
					J.A = FVector3f(L.Pos);
					J.B = L.Land;
					J.bB = L.bLand;
				}
			}
		}
	}
	TSharedPtr<const FCityGenSight, ESPMode::ThreadSafe> G = Sight;
	const int32 Gen = SightGeneration;
	bSightRunning = true;
	SightTask = Async(EAsyncExecution::ThreadPool, [G, Jobs = MoveTemp(Jobs), View, Gen]()
	{
		const double S0 = FPlatformTime::Seconds();
		FCityGenSightResult R;
		R.Eye = View;
		R.Generation = Gen;
		R.Tested = Jobs.Num();
		for (const FCityGenSightJob& J : Jobs)
		{
			++R.Rays;
			bool bSeen = G->Visible(View, FVector(J.A));
			if (!bSeen && J.bB)
			{
				++R.Rays;
				bSeen = G->Visible(View, FVector(J.B));
			}
			if (bSeen)
			{
				R.Seen.Add(J.Key);
			}
		}
		R.Ms = (FPlatformTime::Seconds() - S0) * 1000.0;
		return R;
	});
	SightLaunchMs = (FPlatformTime::Seconds() - T0) * 1000.0;
}

bool ACityGenAtmos::TakeSight(double Now)
{
	// a finished sweep: the lights it saw seen now, those no sweep saw for SightHoldS forgotten
	if (!bSightRunning || !SightTask.IsReady())
	{
		return false;
	}
	FCityGenSightResult R = SightTask.Consume();
	bSightRunning = false;
	++SightSweeps;
	SightRays = R.Rays;
	SightTested = R.Tested;
	SightMs = R.Ms;
	SightMsMax = FMath::Max(SightMsMax, R.Ms);
	if (!bSightNow || R.Generation != SightGeneration)
	{
		return false;
	}
	for (const int64 K : R.Seen)
	{
		SeenAt.Add(K, Now);
	}
	for (auto It = SeenAt.CreateIterator(); It; ++It)
	{
		if (Now - It.Value() > double(SightHoldS))
		{
			It.RemoveCurrent();
		}
	}
	bSightReady = true;
	return true;
}

void ACityGenAtmos::FinishSight()
{
	if (bSightRunning)
	{
		SightTask.Wait();
		SightTask.Consume();
		bSightRunning = false;
	}
}

void ACityGenAtmos::PickSight(const FVector& View, TArray<FPick>& Mid, TArray<FPick>& High) const
{
	// the lights in sight within SightRangeM: the street's by the size of their pools (the
	// nearest and the farthest reaching first), the high tier's by distance (a searchlight first)
	const double RangeCm = double(SightRangeM) * 100.0;
	const double NearCm = double(NearRangeM) * 100.0;
	for (const TPair<int64, double>& KV : SeenAt)
	{
		const FCityGenAtmosLight* L = LightOf(KV.Key);
		if (!L || !L->bOn || ScheduleAt(L->Schedule) < 0.05f)
		{
			continue;
		}
		const double D = FVector::Dist(L->Pos, View);
		if (D > RangeCm || (L->bNearOnly && D > NearCm))
		{
			continue;
		}
		if (L->bHigh)
		{
			High.Add({L->Anim == 2 ? 0.25 * D : D, D, KV.Key});
		}
		else
		{
			Mid.Add({D / FMath::Max(500.0, double(L->ReachCm)), D, KV.Key});
		}
	}
}

void ACityGenAtmos::UpdateLive()
{
	const double T = FPlatformTime::Seconds();
	const FVector View = ViewLocation();
	// visible lights: a walker's live set by sight once a sweep has come back, else the circle
	const bool bWantSight = SightWanted();
	if (bWantSight != bSightNow)
	{
		bSightNow = bWantSight;
		bSightReady = false;
		SeenAt.Reset();
	}
	if (bSightNow)
	{
		TakeSight(T);
		LaunchSight(View, T);
	}
	const bool bBySight = bSightNow && bSightReady;
	if (bBySight != bSightPicked)
	{
		bSightPicked = bBySight;
		// (the play features' light pools stand past the live range: 1,200 m by sight)
		SetPlayLamps(!bShowing);
	}
	TArray<FPick> Mid, High;
	if (bBySight)
	{
		PickSight(View, Mid, High);
	}
	else
	{
		PickCircle(View, Mid, High);
	}
	Candidates = Mid.Num();
	CandidatesHigh = High.Num();
	auto ByScore = [](const FPick& A, const FPick& B)
	{
		return A.Score < B.Score || (A.Score == B.Score && A.Key < B.Key);
	};
	Mid.Sort(ByScore);
	High.Sort(ByScore);
	Mid.SetNum(FMath::Min(Mid.Num(), FMath::Max(0, bBySight ? SightMax : MaxLive)));
	High.SetNum(FMath::Min(High.Num(), FMath::Max(0, MaxHigh)));
	LiveHigh = High.Num();
	SightPickedN = bBySight ? Mid.Num() + High.Num() : 0;
	TSet<int64> Want;
	Want.Reserve(Mid.Num() + High.Num());
	for (const FPick& P : Mid)
	{
		Want.Add(P.Key);
	}
	for (const FPick& P : High)
	{
		Want.Add(P.Key);
	}
	// the lights that left the set fade out (UpdateFades releases them at 0)
	Wanted = Want;
	// the nearest that may cast shadows do, within the near range
	const double NearCm = double(NearRangeM) * 100.0;
	TArray<FPick> ByDist = Mid;
	ByDist.Sort([](const FPick& A, const FPick& B) { return A.D < B.D || (A.D == B.D && A.Key < B.Key); });
	TSet<int64> Shadow;
	for (const FPick& P : ByDist)
	{
		if (Shadow.Num() >= MaxShadowed || P.D > NearCm)
		{
			break;
		}
		const FCityGenAtmosLight* L = LightOf(P.Key);
		if (L && L->bShadow)
		{
			Shadow.Add(P.Key);
		}
	}
	// the fades by distance: the farthest share of the range (the circle: of the live set's
	// reach, so a light entering it at its edge does not pop)
	const double MidCm = double(bBySight ? SightRangeM : MidRangeM) * 100.0;
	const double FarCm = bBySight ? MidCm : (ByDist.Num() ? FMath::Min(MidCm, ByDist.Last().D) : MidCm);
	const double HighCm = double(bBySight ? SightRangeM : HighRangeM) * 100.0;
	TArray<int64> Leaving;
	for (const TPair<int64, TObjectPtr<ULocalLightComponent>>& KV : Live)
	{
		if (!Want.Contains(KV.Key))
		{
			Leaving.Add(KV.Key);
		}
	}
	Flickering.Reset();
	FlickerSet.Reset();
	auto Place = [&](const FPick& P, float Fade, bool bShadow)
	{
		const FCityGenAtmosLight* L = LightOf(P.Key);
		if (!L)
		{
			return;
		}
		TObjectPtr<ULocalLightComponent>* Have = Live.Find(P.Key);
		ULocalLightComponent* C = Have ? Have->Get() : nullptr;
		if (!C)
		{
			C = Take(L->Shape);
			Live.Add(P.Key, C);
			// (a light joining the set fades in)
			Alpha.Add(P.Key, FadeS > 0.f ? 0.f : 1.f);
		}
		FadeOf.Add(P.Key, Fade);
		ApplyLight(C, *L, P.Key, bShadow);
		if (bShadow) { Shadowed.Add(P.Key); } else { Shadowed.Remove(P.Key); }
		if (L->Flicker > 0.f || L->Anim != 0)
		{
			Flickering.Add(P.Key);
			FlickerSet.Add(P.Key);
		}
	};
	for (const FPick& P : Mid)
	{
		Place(P, float(FMath::Clamp((FarCm - P.D) / (FadeShare * FarCm), 0.0, 1.0)), Shadow.Contains(P.Key));
	}
	// the high pool's: no shadows, the farthest fifth of its range fading
	for (const FPick& P : High)
	{
		Place(P, float(FMath::Clamp((HighCm - P.D) / (FadeShare * HighCm), 0.0, 1.0)), false);
	}
	// (a leaving light that flickers, blinks or sweeps goes on doing so while it fades)
	for (const int64 K : Leaving)
	{
		const FCityGenAtmosLight* L = LightOf(K);
		if (!L)
		{
			Release(K);
		}
		else if (L->Flicker > 0.f || L->Anim != 0)
		{
			Flickering.Add(K);
			FlickerSet.Add(K);
		}
	}
	UpdateMs = (FPlatformTime::Seconds() - T) * 1000.0;
	UpdateMsMax = FMath::Max(UpdateMsMax, UpdateMs);
}

void ACityGenAtmos::UpdateFades(float DeltaSeconds, double Now)
{
	// every live light toward 1 while wanted and toward 0 when it left the set, released there
	FadingNow = 0;
	if (Alpha.IsEmpty())
	{
		return;
	}
	const float Step = FadeS > 0.f ? DeltaSeconds / FadeS : 1.f;
	const double T = WorldTime();
	const uint32 Flick = uint32(Now * 12.0);
	TArray<int64> Done;
	for (TPair<int64, float>& KV : Alpha)
	{
		const bool bIn = Wanted.Contains(KV.Key);
		const float Target = bIn ? 1.f : 0.f;
		if (KV.Value == Target)
		{
			if (!bIn)
			{
				Done.Add(KV.Key);
			}
			continue;
		}
		KV.Value = bIn ? FMath::Min(1.f, KV.Value + Step) : FMath::Max(0.f, KV.Value - Step);
		if (!bIn && KV.Value <= 0.f)
		{
			Done.Add(KV.Key);
			continue;
		}
		++FadingNow;
		// (a flickering light's level is set by UpdateFlicker every frame)
		if (FlickerSet.Contains(KV.Key))
		{
			continue;
		}
		const TObjectPtr<ULocalLightComponent>* C = Live.Find(KV.Key);
		const FCityGenAtmosLight* L = LightOf(KV.Key);
		if (C && *C && L)
		{
			SetLevel(*C, KV.Key, *L, T, Flick);
		}
	}
	for (const int64 K : Done)
	{
		Release(K);
	}
}

void ACityGenAtmos::UpdateFlicker(double Now)
{
	// a flickering light drops for a moment now and then; AT2: a blink from the world's time,
	// as the beacon's material blinks; a sweep turns the light (SetLevel)
	const uint32 Step = uint32(Now * 12.0);
	const double T = WorldTime();
	for (int64 Key : Flickering)
	{
		TObjectPtr<ULocalLightComponent>* C = Live.Find(Key);
		const FCityGenAtmosLight* L = LightOf(Key);
		if (!C || !*C || !L)
		{
			continue;
		}
		if (L->Anim == 2)
		{
			(*C)->SetWorldRotation(AnimRot(*L, T));
		}
		SetLevel(*C, Key, *L, T, Step);
	}
}

void ACityGenAtmos::UpdateFixtureCells(const FVector& View)
{
	// a cell's beacons, beams and plumes near the view (the cells are always loaded since the
	// visible lights: their lights reach past World Partition's loading range, their fixtures
	// keep to it), made as the view comes within FixtureRangeM and dropped a cell past it
	const double In = double(FixtureRangeM) * 100.0;
	const double Out = In + FMath::Max(1.0, double(CellM) * 100.0);
	for (int32 Slot = 0; Slot < Slots.Num(); ++Slot)
	{
		FSlot& S = Slots[Slot];
		const ACityGenAtmosCell* Cell = S.Actor.Get();
		if (!S.bUsed || !Cell)
		{
			continue;
		}
		const double D = FVector::Dist2D(Cell->GetActorLocation(), View);
		if (!S.bMade && D <= In)
		{
			S.bMade = true;
			MakeFixtures(Slot);
			MakePlumes(Slot);
		}
		else if (S.bMade && D > Out)
		{
			S.bMade = false;
			DropFixtures(Slot);
			DropPlumes(Slot);
		}
	}
}

void ACityGenAtmos::SetPlayLamps(bool bOn) const
{
	// (while the plan's lights are on, the play features keep only their light pools under the
	// lamps past the live range: AT0's far tier, `bFarPools`)
	// (AT1: the play features keep only their light pools; with the plan's lights on, the
	// pools stand past the live range, AT0's far tier, `bFarPools`; with them off, from the
	// view out, as before atmosgen)
	// (AT7: with the far city's cards the pools go: the cards are the far tier)
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("CityGen.PlayLamps")))
	{
		V->Set(bOn ? 1 : ((bFarPools && !HasFar()) ? 2 : 0), ECVF_SetByCode);
	}
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("CityGen.PlayPoolsFromM")))
	{
		// (visible lights: past the walker's range, 1,200 m; within it a lamp out of sight is
		// dark, pool and all)
		V->Set(LiveRangeM(), ECVF_SetByCode);
	}
}

void ACityGenAtmos::SetLightsOn(bool bOn)
{
	bLights = bOn;
	if (!bOn)
	{
		ReleaseAll();
		bShowing = false;
		bSightNow = bSightReady = bSightPicked = false;
		SeenAt.Reset();
	}
	SetPlayLamps(!bShowing);
	LiveAt = -1.0;
}

void ACityGenAtmos::SetFarPools(bool bOn)
{
	bFarPools = bOn;
	if (bLights)
	{
		SetPlayLamps(!bShowing);
	}
}

// -- AT7: the far city --

void ACityGenAtmos::SetFar(bool bOn)
{
	bFar = bOn;
	if (bOn && FarComps.Num() == 0 && FarCards > 0)
	{
		bFarDirty = true;
		FarDirtyAt = -1.0;
	}
	ShowFar(bShowing && HasFar());
	if (bLights)
	{
		SetPlayLamps(!bShowing);
	}
}

void ACityGenAtmos::DropFar()
{
	for (UPrimitiveComponent* C : FarComps)
	{
		if (C)
		{
			C->DestroyComponent();
		}
	}
	FarComps.Reset();
	FarBlocks.Reset();
	FarGlows = FarFlats = 0;
	bFarShown = false;
	FarHourSet = -100.f;
}

void ACityGenAtmos::RebuildFar()
{
	// every registered cell's cards, by 1 km block: a glow component and a flat one each
	const double T0 = FPlatformTime::Seconds();
	DropFar();
	bFarDirty = false;
	if (!bFar || FarCards <= 0 || !GetWorld())
	{
		return;
	}
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, RainMesh);
	UMaterialInterface* GlowMat = LoadObject<UMaterialInterface>(nullptr, FarGlowMaterialPath);
	UMaterialInterface* FlatMat = LoadObject<UMaterialInterface>(nullptr, FarFlatMaterialPath);
	if (!Mesh || !GlowMat || !FlatMat)
	{
		UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: the far city's mesh or materials are missing (atmosgen's assets before AT7?)"));
		return;
	}
	struct FBuild
	{
		TArray<FTransform> GlowX, FlatX;
		TArray<float> GlowD, FlatD;
		TArray<uint8> GlowS, FlatS;
	};
	TMap<FIntPoint, FBuild> By;
	for (const FSlot& S : Slots)
	{
		if (!S.bUsed)
		{
			continue;
		}
		for (int32 k = 0; k < S.FarFlags.Num(); ++k)
		{
			const float* f = S.Far.GetData() + k * CityGenAtmosPack::FarFloats;
			const uint32 Flags = uint32(S.FarFlags[k]);
			const int32 Type = int32(Flags & 3u);
			const float Tier = float((Flags >> 2) & 3u);
			const bool bBlink = (Flags & 16u) != 0;
			const uint8 Sched = uint8((Flags >> 8) & 0xffu);
			const FVector P(f[0], f[1], f[2]);
			const FIntPoint B(FMath::FloorToInt32(P.X / FarBlockCm), FMath::FloorToInt32(P.Y / FarBlockCm));
			FBuild& Bd = By.FindOrAdd(B);
			if (Type == 0)
			{
				Bd.GlowX.Add(FTransform(FRotator::ZeroRotator, P, FVector(FarGlowBoundCm / 100.f)));
				Bd.GlowD.Append({f[0], f[1], f[2], f[3], f[4], f[5], f[6], Tier,
					bBlink ? f[9] : 0.f, bBlink ? f[10] : 1.f, bBlink ? f[11] : 0.f, 1.f});
				Bd.GlowS.Add(Sched);
			}
			else
			{
				// a pool lies on its surface; a wash stands on its facade, its face (+Z) along
				// its yaw (pitch -90 turns +Z onto +X), its height along the plane's X
				const float R = FMath::Max(10.f, f[6]);
				const float H = FMath::Max(10.f, f[7]);
				const FTransform X = Type == 1 ?
					FTransform(FRotator::ZeroRotator, P, FVector(2.f * R / 100.f, 2.f * R / 100.f, 1.f)) :
					FTransform(FRotator(-90.f, f[8], 0.f), P, FVector(2.f * H / 100.f, 2.f * R / 100.f, 1.f));
				Bd.FlatX.Add(X);
				Bd.FlatD.Append({f[0], f[1], f[2], f[3], f[4], f[5], float(Type), R, H, Tier, 1.f});
				Bd.FlatS.Add(Sched);
			}
		}
	}
	auto Make = [this, Mesh](UMaterialInterface* Mat, int32 NData, const TArray<FTransform>& X,
		const TArray<float>& D) -> UInstancedStaticMeshComponent*
	{
		UInstancedStaticMeshComponent* I = NewObject<UInstancedStaticMeshComponent>(this);
		I->SetupAttachment(RootComponent);
		I->SetUsingAbsoluteLocation(true);
		I->SetUsingAbsoluteRotation(true);
		I->SetUsingAbsoluteScale(true);
		I->SetStaticMesh(Mesh);
		I->SetMaterial(0, Mat);
		I->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		I->SetGenerateOverlapEvents(false);
		I->SetCastShadow(false);
		I->SetMobility(EComponentMobility::Movable);
		I->bAffectDynamicIndirectLighting = false;
		I->bAffectDistanceFieldLighting = false;
		I->bReceivesDecals = false;
		I->SetVisibleInRayTracing(false);
		I->NumCustomDataFloats = NData;
		I->AddInstances(X, false, true, false);
		for (int32 i = 0; i < X.Num(); ++i)
		{
			I->SetCustomData(i, TArrayView<const float>(D.GetData() + i * NData, NData), false);
		}
		I->SetVisibility(false);
		I->RegisterComponent();
		FarComps.Add(I);
		return I;
	};
	for (TPair<FIntPoint, FBuild>& KV : By)
	{
		FFarBlock& Blk = FarBlocks.FindOrAdd(KV.Key);
		if (KV.Value.GlowX.Num())
		{
			Blk.Glows = Make(GlowMat, FarGlowData, KV.Value.GlowX, KV.Value.GlowD);
			Blk.GlowSchedule = MoveTemp(KV.Value.GlowS);
			FarGlows += KV.Value.GlowX.Num();
		}
		if (KV.Value.FlatX.Num())
		{
			Blk.Flats = Make(FlatMat, FarFlatData, KV.Value.FlatX, KV.Value.FlatD);
			Blk.FlatSchedule = MoveTemp(KV.Value.FlatS);
			FarFlats += KV.Value.FlatX.Num();
		}
	}
	FarBuildMs = (FPlatformTime::Seconds() - T0) * 1000.0;
	UE_LOG(LogCityGenAtmos, Display, TEXT("CityGen atmos: the far city: %d glows and %d pools and washes in %d blocks (%.1f ms)"),
		FarGlows, FarFlats, FarBlocks.Num(), FarBuildMs);
	UpdateFarLevels();
	ShowFar(bShowing && HasFar());
}

void ACityGenAtmos::ShowFar(bool bOn)
{
	bFarShown = bOn && FarComps.Num() > 0;
	for (UPrimitiveComponent* C : FarComps)
	{
		if (C)
		{
			C->SetVisibility(bFarShown);
		}
	}
	UpdateFarParams();
}

void ACityGenAtmos::UpdateFarLevels()
{
	// each card's level: its schedule's share at the hour (set when the hour moves a little)
	FarHourSet = Hour;
	TArray<float> Level;
	Level.SetNumUninitialized(256);
	for (int32 s = 0; s < 256; ++s)
	{
		Level[s] = ScheduleAt(uint8(s));
	}
	auto Set = [&Level](UInstancedStaticMeshComponent* I, const TArray<uint8>& Sch, int32 Idx)
	{
		if (!I)
		{
			return;
		}
		for (int32 i = 0; i < Sch.Num(); ++i)
		{
			I->SetCustomDataValue(i, Idx, Level[Sch[i]], false);
		}
		I->MarkRenderStateDirty();
	};
	for (TPair<FIntPoint, FFarBlock>& KV : FarBlocks)
	{
		Set(KV.Value.Glows.Get(), KV.Value.GlowSchedule, FarGlowData - 1);
		Set(KV.Value.Flats.Get(), KV.Value.FlatSchedule, FarFlatData - 1);
	}
}

void ACityGenAtmos::UpdateFarParams()
{
	// MPC_CityGenAtmos's far city: the lights' scale (the scene's exposure against the plan's,
	// the gain) while they show, where each tier's cards fade in (the live ranges now: a
	// walker's by sight, else the circle's; the beacons' while they are drawn), how wide a few
	// pixels are per distance at the view's field of view
	if (!AtmosCollection)
	{
		return;
	}
	float Px = 0.f;
	const UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	int32 W = 0, Hh = 0;
	if (PC)
	{
		PC->GetViewportSize(W, Hh);
	}
	const float Fov = (PC && PC->PlayerCameraManager) ? PC->PlayerCameraManager->GetFOVAngle() : 90.f;
	if (W > 0)
	{
		Px = FarPx * 2.f * FMath::Tan(FMath::DegreesToRadians(0.5f * FMath::Clamp(Fov, 5.f, 170.f))) / float(W);
	}
	else
	{
		Px = FarPx * 2.f / 1920.f;
	}
	FarPxNow = Px;
	const float Sc = bFarShown ? Scale() * FarGain : 0.f;
	const float Mid = LiveRangeM();
	const float Hi = bSightPicked ? SightRangeM : HighRangeM;
	const float Fix = bFixturesShown ? FixtureRangeM : 0.f;
	const float Vals[7] = {Sc, Mid, Hi, Fix, FarFade, Px, FarSpread};
	static const TCHAR* Names[7] = {TEXT("FarScale"), TEXT("FarMidM"), TEXT("FarHighM"),
		TEXT("FarFixM"), TEXT("FarFade"), TEXT("FarPx"), TEXT("FarSpread")};
	for (int32 k = 0; k < 7; ++k)
	{
		if (FarSet[k] != Vals[k])
		{
			FarSet[k] = Vals[k];
			UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, Names[k], Vals[k]);
		}
	}
}

void ACityGenAtmos::SetTiers(int32 InLive, float RangeM, int32 InShadowed)
{
	MaxLive = FMath::Max(0, InLive);
	MidRangeM = FMath::Max(1.f, RangeM);
	MaxShadowed = FMath::Max(0, InShadowed);
	LiveAt = -1.0;
	if (bLights)
	{
		SetPlayLamps(!bShowing);
	}
}

void ACityGenAtmos::SetHour(float InHour)
{
	Hour = FMath::Fmod(InHour + 24.f, 24.f);
	ApplyTime();
	PushParameters();
	LiveAt = -1.0;
	// AT4: the fog by the hour, the volumes' and plumes' schedules
	if (bFog)
	{
		SetFog(true);
	}
	VolumesAt = -1.0;
	UpdatePlumeRates();
}

// -- AT2: animation, the high tier's settings, the fixtures' stand-ins --

double ACityGenAtmos::WorldTime() const
{
	const UWorld* World = GetWorld();
	return World ? double(World->GetTimeSeconds()) : FPlatformTime::Seconds();
}

float ACityGenAtmos::AnimGain(const FCityGenAtmosLight& L, double T) const
{
	if (L.Anim != 1 || L.AnimPeriod <= 0.f)
	{
		return 1.f;
	}
	// (the beacon's material blinks by the same rule from the same time)
	const double Ph = FMath::Frac(T / double(L.AnimPeriod) + double(L.AnimPhase));
	return Ph < double(L.AnimAmount) ? 1.f : 0.f;
}

FRotator ACityGenAtmos::AnimRot(const FCityGenAtmosLight& L, double T) const
{
	if (L.Anim != 2 || L.AnimPeriod <= 0.f)
	{
		return L.Rot;
	}
	// a sweep: the yaw swings AnimAmount either way, the pitch a little, out of step
	const double A = 2.0 * PI * (T / double(L.AnimPeriod) + double(L.AnimPhase));
	FRotator R = L.Rot;
	R.Yaw += L.AnimAmount * float(FMath::Sin(A));
	R.Pitch = FMath::Clamp(R.Pitch + 0.15f * L.AnimAmount * float(FMath::Sin(0.71 * A + 1.3)), -89.f, 89.f);
	return R;
}

void ACityGenAtmos::SetHigh(int32 InHigh, float RangeM)
{
	MaxHigh = FMath::Max(0, InHigh);
	HighRangeM = FMath::Max(1.f, RangeM);
	LiveAt = -1.0;
}

void ACityGenAtmos::SetFixtures(bool bOn)
{
	bFixtures = bOn;
	ShowFixtures(bShowing && bFixtures);
}

void ACityGenAtmos::MakeFixtures(int32 Slot)
{
	if (!Slots.IsValidIndex(Slot) || !GetWorld())
	{
		return;
	}
	FSlot& S = Slots[Slot];
	const int32 Aviation = KindNames.IndexOfByKey(FString(TEXT("aviation")));
	TArray<int32> Beacons, Beams;
	for (int32 i = 0; i < S.Lights.Num(); ++i)
	{
		const FCityGenAtmosLight& L = S.Lights[i];
		if (!L.bOn)
		{
			continue;
		}
		if (Aviation >= 0 && L.Kind == uint8(Aviation))
		{
			Beacons.Add(i);
		}
		else if (L.Anim == 2)
		{
			Beams.Add(i);
		}
	}
	if (Beacons.Num())
	{
		UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, BeaconMesh);
		if (!BeaconMaterial)
		{
			BeaconMaterial = LoadObject<UMaterialInterface>(nullptr, BeaconMaterialPath);
		}
		if (Mesh && BeaconMaterial)
		{
			UInstancedStaticMeshComponent* I = NewObject<UInstancedStaticMeshComponent>(this);
			I->SetupAttachment(RootComponent);
			I->SetUsingAbsoluteLocation(true);
			I->SetUsingAbsoluteRotation(true);
			I->SetUsingAbsoluteScale(true);
			I->SetStaticMesh(Mesh);
			I->SetMaterial(0, BeaconMaterial);
			I->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			I->SetCastShadow(false);
			I->SetMobility(EComponentMobility::Movable);
			I->NumCustomDataFloats = 4;
			const float Sc = BeaconCm / 100.f;
			for (int32 i : Beacons)
			{
				const FCityGenAtmosLight& L = S.Lights[i];
				const int32 k = I->AddInstance(FTransform(FRotator::ZeroRotator, L.Pos, FVector(Sc)), true);
				// (phase, period, on share, glow: a steady level's on share 1, its glow less)
				const bool bBlink = L.Anim == 1 && L.AnimPeriod > 0.f;
				I->SetCustomDataValue(k, 0, bBlink ? L.AnimPhase : 0.f, false);
				I->SetCustomDataValue(k, 1, bBlink ? L.AnimPeriod : 1.f, false);
				I->SetCustomDataValue(k, 2, bBlink ? L.AnimAmount : 1.f, false);
				I->SetCustomDataValue(k, 3, BeaconOn * BeaconGlow * (bBlink ? 1.f : 0.5f), false);
			}
			I->SetVisibility(bFixturesShown);
			I->RegisterComponent();
			Fixtures.Add(I);
			S.Beacons = I;
			BeaconCount += Beacons.Num();
		}
	}
	if (Beams.Num())
	{
		UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, BeamMesh);
		if (!BeamMaterial)
		{
			BeamMaterial = LoadObject<UMaterialInterface>(nullptr, BeamMaterialPath);
		}
		if (Mesh && BeamMaterial)
		{
			for (int32 i : Beams)
			{
				const FCityGenAtmosLight& L = S.Lights[i];
				UStaticMeshComponent* B = NewObject<UStaticMeshComponent>(this);
				B->SetupAttachment(RootComponent);
				B->SetUsingAbsoluteLocation(true);
				B->SetUsingAbsoluteRotation(true);
				B->SetUsingAbsoluteScale(true);
				B->SetStaticMesh(Mesh);
				B->SetMaterial(0, BeamMaterial);
				B->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				B->SetCastShadow(false);
				B->SetMobility(EComponentMobility::Movable);
				B->SetCustomPrimitiveDataFloat(0, L.Color.R);
				B->SetCustomPrimitiveDataFloat(1, L.Color.G);
				B->SetCustomPrimitiveDataFloat(2, L.Color.B);
				// (AT4: brighter in fog: the beam is the haze the light scatters in)
				B->SetCustomPrimitiveDataFloat(3, BeamBase * BeamGlow * (1.f + BeamFogGain * FogShare()));
				B->SetCustomPrimitiveDataFloat(4, BeamCm * 0.5f);
				B->SetVisibility(bFixturesShown);
				B->RegisterComponent();
				Fixtures.Add(B);
				S.Beams.Add(TPair<int32, TWeakObjectPtr<UStaticMeshComponent>>(i, B));
				++BeamCount;
			}
		}
	}
	if (S.Beams.Num())
	{
		UpdateBeams(WorldTime());
	}
}

void ACityGenAtmos::DropFixtures(int32 Slot)
{
	if (!Slots.IsValidIndex(Slot))
	{
		return;
	}
	FSlot& S = Slots[Slot];
	if (UInstancedStaticMeshComponent* I = S.Beacons.Get())
	{
		BeaconCount -= I->GetInstanceCount();
		Fixtures.Remove(I);
		I->DestroyComponent();
	}
	S.Beacons.Reset();
	for (const TPair<int32, TWeakObjectPtr<UStaticMeshComponent>>& B : S.Beams)
	{
		if (UStaticMeshComponent* C = B.Value.Get())
		{
			Fixtures.Remove(C);
			C->DestroyComponent();
		}
		--BeamCount;
	}
	S.Beams.Reset();
}

void ACityGenAtmos::ShowFixtures(bool bOn)
{
	bFixturesShown = bOn;
	for (UPrimitiveComponent* C : Fixtures)
	{
		if (C)
		{
			C->SetVisibility(bOn);
		}
	}
}

void ACityGenAtmos::UpdateBeams(double T)
{
	// each beam a cone from its searchlight along its aim (the mesh's apex at +Z, its pivot in
	// the middle: +Z turned back to the light), as long as BeamCm, as wide as its cone spread
	for (const FSlot& S : Slots)
	{
		if (!S.bUsed)
		{
			continue;
		}
		for (const TPair<int32, TWeakObjectPtr<UStaticMeshComponent>>& B : S.Beams)
		{
			UStaticMeshComponent* C = B.Value.Get();
			if (!C || !S.Lights.IsValidIndex(B.Key))
			{
				continue;
			}
			const FCityGenAtmosLight& L = S.Lights[B.Key];
			const FVector Dir = AnimRot(L, T).Vector();
			const float R = BeamCm * FMath::Tan(FMath::DegreesToRadians(FMath::Max(0.5f, L.Outer) * BeamSpread));
			C->SetWorldTransform(FTransform(FRotationMatrix::MakeFromZ(-Dir).Rotator(),
				L.Pos + Dir * (BeamCm * 0.5), FVector(2.f * R / 100.f, 2.f * R / 100.f, BeamCm / 100.f)));
		}
	}
}

// -- air and weather --

void ACityGenAtmos::EnsureVolume()
{
	if (Volume || !GetWorld())
	{
		return;
	}
	FActorSpawnParameters Params;
	Params.ObjectFlags |= RF_Transient;
	Volume = GetWorld()->SpawnActor<APostProcessVolume>(Params);
	if (Volume)
	{
		Volume->bUnbound = true;
		Volume->Priority = 50.f;
		Volume->Settings.bOverride_bMegaLights = true;
		Volume->Settings.bMegaLights = false;
	}
}

void ACityGenAtmos::SetMegaLights(bool bOn)
{
	bMegaLights = bOn;
	EnsureVolume();
	if (Volume)
	{
		Volume->Settings.bMegaLights = bOn;
	}
}

void ACityGenAtmos::EnsureFog()
{
	if (Fog || !GetWorld())
	{
		return;
	}
	TActorIterator<AExponentialHeightFog> It(GetWorld());
	if (It)
	{
		Fog = *It;
		return;
	}
	FActorSpawnParameters Params;
	Params.ObjectFlags |= RF_Transient;
	Fog = GetWorld()->SpawnActor<AExponentialHeightFog>(FVector(0.0, 0.0, 0.0), FRotator::ZeroRotator, Params);
}

void ACityGenAtmos::SetFog(bool bOn)
{
	bFog = bOn;
	if (bOn)
	{
		EnsureFog();
	}
	if (!Fog)
	{
		return;
	}
	UExponentialHeightFogComponent* F = Fog->GetComponent();
	F->SetVisibility(bOn);
	UpdateBeamGlow();
	if (!bOn)
	{
		PushParameters();
		return;
	}
	// AT4: the plan's fog by the hour (thicker in the cool night), its start, its reach and
	// its scattering (forward: halos round the lamps, shafts along the beams)
	F->SetFogDensity(FogDensity * FogShare());
	F->SetFogHeightFalloff(FogFalloff);
	F->SetStartDistance(FogStartM * 100.f);
	// (the inscattering is the sky's: a dark haze by night, the overcast's grey by day, between
	// at dusk in log space; the lights' own colors come from the volumetric fog they light)
	const FLinearColor NightIn(0.004f, 0.005f, 0.008f), DayIn(0.16f, 0.18f, 0.21f);
	const float D = FMath::Clamp(1.f - NightNow, 0.f, 1.f);
	F->SetFogInscatteringColor(FLinearColor(
		FMath::Exp(FMath::Lerp(FMath::Loge(NightIn.R), FMath::Loge(DayIn.R), D)),
		FMath::Exp(FMath::Lerp(FMath::Loge(NightIn.G), FMath::Loge(DayIn.G), D)),
		FMath::Exp(FMath::Lerp(FMath::Loge(NightIn.B), FMath::Loge(DayIn.B), D))));
	F->SetVolumetricFog(bVolumetricFog);
	F->SetVolumetricFogScatteringDistribution(FogPhaseG);
	F->SetVolumetricFogExtinctionScale(FogVolumetric);
	F->SetVolumetricFogAlbedo(FogAlbedo.ToFColor(true));
	F->SetVolumetricFogDistance(FogViewM * 100.f);
	PushParameters();
}

// -- AT4: the air: fog volumes, plumes, light shafts, the engine settings --

float ACityGenAtmos::FogShare() const
{
	if (!bFog)
	{
		return 0.f;
	}
	if (FogHours.Num() < 24)
	{
		return 1.f;
	}
	const float Hr = FMath::Fmod(Hour + 24.f, 24.f);
	const int32 H = FMath::Clamp(FMath::FloorToInt32(Hr), 0, 23);
	return FMath::Lerp(FogHours[H], FogHours[(H + 1) % 24], FMath::Clamp(Hr - float(H), 0.f, 1.f));
}

float ACityGenAtmos::ScatterOf(uint8 Kind) const
{
	return KindScatter.IsValidIndex(Kind) ? KindScatter[Kind] : 1.f;
}

void ACityGenAtmos::UpdateBeamGlow()
{
	const float G = BeamBase * BeamGlow * (1.f + BeamFogGain * FogShare());
	for (const FSlot& S : Slots)
	{
		for (const TPair<int32, TWeakObjectPtr<UStaticMeshComponent>>& B : S.Beams)
		{
			if (UStaticMeshComponent* C = B.Value.Get())
			{
				C->SetCustomPrimitiveDataFloat(3, G);
			}
		}
	}
}

void ACityGenAtmos::ApplyCVars(bool bOn)
{
	// (the tuned settings while the controller runs; each one's value before the first time,
	// the project's, kept to put back)
	if (bOn && !bCVarsApplied)
	{
		for (const FString& Line : TunedSettings)
		{
			FString Name, Value;
			if (!Line.Split(TEXT("="), &Name, &Value))
			{
				continue;
			}
			if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(*Name))
			{
				if (!SavedCVars.Contains(Name))
				{
					SavedCVars.Add(Name, V->GetString());
				}
				V->Set(*Value, ECVF_SetByCode);
				UE_LOG(LogCityGenAtmos, Display, TEXT("CityGen atmos: %s %s (was %s)"), *Name, *V->GetString(),
					*SavedCVars[Name]);
			}
			else
			{
				UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: no console variable %s"), *Name);
			}
		}
		bCVarsApplied = true;
	}
	else if (!bOn && bCVarsApplied)
	{
		for (const TPair<FString, FString>& KV : SavedCVars)
		{
			if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(*KV.Key))
			{
				V->Set(*KV.Value, ECVF_SetByCode);
			}
		}
		bCVarsApplied = false;
	}
}

void ACityGenAtmos::SetTuned(bool bOn)
{
	bTuned = bOn;
	ApplyCVars(bOn);
}

void ACityGenAtmos::SetAir(bool bOn)
{
	bAir = bOn;
	if (!bOn)
	{
		ReleaseVolumes();
	}
	ShowPlumes(bOn);
	VolumesAt = -1.0;
}

void ACityGenAtmos::ReleaseVolumes()
{
	for (const TPair<int64, TObjectPtr<USceneComponent>>& KV : LiveVolumes)
	{
		if (KV.Value)
		{
			KV.Value->SetVisibility(false);
			FreeVolumes.Add(KV.Value);
		}
	}
	LiveVolumes.Reset();
}

void ACityGenAtmos::UpdateVolumes()
{
	// the nearest MaxVolumes fog volumes within VolumeRangeM of the view (by the distance to
	// their bound), each at its schedule's share, the farthest fifth fading
	const FVector View = ViewLocation();
	const double RangeCm = double(VolumeRangeM) * 100.0;
	const double CellCm = FMath::Max(1.0, double(CellM) * 100.0);
	// (a volume belongs to the cell of its middle; a smog puff reaches 2 cells past it)
	const int32 Reach = FMath::CeilToInt32(RangeCm / CellCm) + 2;
	const FIntPoint VC = CellOf(View);
	TArray<TPair<double, int64>> Near;
	for (int32 dx = -Reach; dx <= Reach; ++dx)
	{
		for (int32 dy = -Reach; dy <= Reach; ++dy)
		{
			const TArray<int32>* At = SlotsAt.Find(FIntPoint(VC.X + dx, VC.Y + dy));
			if (!At)
			{
				continue;
			}
			for (int32 Slot : *At)
			{
				const TArray<FCityGenAtmosVolume>& Vs = Slots[Slot].Volumes;
				for (int32 i = 0; i < Vs.Num(); ++i)
				{
					const FCityGenAtmosVolume& V = Vs[i];
					if (ScheduleAt(V.Schedule) < 0.02f)
					{
						continue;
					}
					const double D = FMath::Max(0.0, FVector::Dist(V.Pos, View) - double(V.Ext.GetMax()));
					if (D <= RangeCm)
					{
						Near.Add(TPair<double, int64>(D, LiveKey(Slot, i)));
					}
				}
			}
		}
	}
	CandidatesVolumes = Near.Num();
	Near.Sort([](const TPair<double, int64>& A, const TPair<double, int64>& B)
	{
		return A.Key < B.Key || (A.Key == B.Key && A.Value < B.Value);
	});
	Near.SetNum(FMath::Min(Near.Num(), FMath::Max(0, MaxVolumes)));
	TSet<int64> Want;
	for (const TPair<double, int64>& N : Near)
	{
		Want.Add(N.Value);
	}
	TArray<int64> Keys;
	LiveVolumes.GetKeys(Keys);
	for (int64 K : Keys)
	{
		if (!Want.Contains(K))
		{
			TObjectPtr<USceneComponent> C;
			LiveVolumes.RemoveAndCopyValue(K, C);
			if (C)
			{
				C->SetVisibility(false);
				FreeVolumes.Add(C);
			}
		}
	}
	for (const TPair<double, int64>& N : Near)
	{
		const int32 Slot = int32(N.Value >> 24);
		const FCityGenAtmosVolume& V = Slots[Slot].Volumes[int32(N.Value & 0xffffff)];
		TObjectPtr<USceneComponent>* Have = LiveVolumes.Find(N.Value);
		ULocalFogVolumeComponent* C = Have ? Cast<ULocalFogVolumeComponent>(Have->Get()) : nullptr;
		if (!C)
		{
			C = FreeVolumes.Num() ? Cast<ULocalFogVolumeComponent>(FreeVolumes.Pop(EAllowShrinking::No).Get()) : nullptr;
			if (!C)
			{
				C = NewObject<ULocalFogVolumeComponent>(this);
				C->SetupAttachment(RootComponent);
				C->SetUsingAbsoluteLocation(true);
				C->SetUsingAbsoluteRotation(true);
				C->SetUsingAbsoluteScale(true);
				C->SetVisibility(false);
				C->RegisterComponent();
				AllVolumes.Add(C);
			}
			LiveVolumes.Add(N.Value, C);
		}
		const float Fade = float(FMath::Clamp((RangeCm - N.Key) / (FadeShare * RangeCm), 0.0, 1.0));
		// (AT5: the weather's gain: mist and smog thicker in fog and smog)
		const float K = ScheduleAt(V.Schedule) * VolumeGain * Fade * (HasWeather() ? WeatherNow[WVolumes] : 1.f);
		const FTransform Xf(FRotator(0.f, V.Yaw, 0.f), V.Pos, V.Ext / ULocalFogVolumeComponent::GetBaseVolumeSize());
		if (!C->GetComponentTransform().Equals(Xf, 0.5))
		{
			C->SetWorldTransform(Xf);
		}
		C->SetRadialFogExtinction(V.Density * (1.f - V.Floor) * K);
		C->SetHeightFogExtinction(V.Density * V.Floor * K);
		C->SetHeightFogFalloff(VolumeFalloff);
		C->SetFogPhaseG(V.PhaseG);
		C->SetFogAlbedo(V.Albedo);
		// (mist and smog glow with the lit city by night; haze under a deck and in a tunnel,
		// kinds 2 and 3, always: their own lights)
		const float Lit = V.Kind >= 2 ? 1.f : NightNow;
		C->SetFogEmissive(V.Albedo * (VolumeGlow * V.Glow * Lit * Fade));
		if (!C->IsVisible())
		{
			C->SetVisibility(true);
		}
	}
}

void ACityGenAtmos::MakePlumes(int32 Slot)
{
	// a cell's plumes: one instanced component of cards, Puffs[kind] a plume, each card a puff
	// rising from its foot by world position offset (M_CgSteam), its life a phase of the
	// plume's period, shown within EmitterRangeM
	if (!Slots.IsValidIndex(Slot) || !GetWorld())
	{
		return;
	}
	FSlot& S = Slots[Slot];
	ACityGenAtmosCell* Cell = S.Actor.Get();
	if (!Cell || S.Emitters <= 0)
	{
		return;
	}
	if (!SteamMaterial)
	{
		SteamMaterial = LoadObject<UMaterialInterface>(nullptr, SteamMaterialPath);
	}
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, RainMesh);
	if (!Mesh || !SteamMaterial)
	{
		return;
	}
	UInstancedStaticMeshComponent* I = NewObject<UInstancedStaticMeshComponent>(this);
	I->SetupAttachment(RootComponent);
	I->SetUsingAbsoluteLocation(true);
	I->SetUsingAbsoluteRotation(true);
	I->SetUsingAbsoluteScale(true);
	I->SetStaticMesh(Mesh);
	I->SetMaterial(0, SteamMaterial);
	I->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	I->SetCastShadow(false);
	I->SetMobility(EComponentMobility::Movable);
	I->bAffectDistanceFieldLighting = false;
	I->bAffectDynamicIndirectLighting = false;
	I->bVisibleInRayTracing = false;
	I->NumCustomDataFloats = PlumeData;
	I->SetCullDistances(0, int32(EmitterRangeM * 100.f));
	S.PlumeSchedule.Reset();
	S.PlumeRate.Reset();
	const float* F = Cell->EmitterFloats.GetData();
	const int32* N = Cell->EmitterInts.GetData();
	for (int32 e = 0; e < S.Emitters; ++e)
	{
		const float* f = F + e * CityGenAtmosPack::EmitFloats;
		const uint32 Flags = uint32(N[e * CityGenAtmosPack::EmitInts]);
		const uint32 Seed = uint32(N[e * CityGenAtmosPack::EmitInts + 1]);
		const uint8 Kind = uint8((Flags >> 8) & 0xffu);
		const int32 K = FMath::Clamp(Puffs.IsValidIndex(Kind) ? Puffs[Kind] : 4, 1, 12);
		const FVector Foot(f[0], f[1], f[2]);
		const float Width = FMath::Max(10.f, f[3]);
		const float Rise = FMath::Max(50.f, f[4]);
		const bool bSmoke = EmitterKinds.IsValidIndex(Kind) && EmitterKinds[Kind] == TEXT("smoke");
		const float Period = Rise / (bSmoke ? SmokeSpeedCm : PlumeSpeedCm);
		// (the card's bounds hold its plume: a stood-up plane round its middle, scaled to it)
		const float Sc = 1.3f * FMath::Max(Rise, 4.f * Width) / 100.f;
		const float Ph0 = float(Hash(Seed, 7u) & 0xffff) / 65536.f;
		for (int32 k = 0; k < K; ++k)
		{
			const int32 Idx = I->AddInstance(FTransform(FRotator(-90.f, 0.f, 0.f),
				Foot + FVector(0.0, 0.0, 0.5 * Rise), FVector(Sc)), true);
			const float D[PlumeData] = {float(Foot.X), float(Foot.Y), float(Foot.Z),
				FMath::Frac(Ph0 + float(k) / float(K)), Period, Rise, Width, f[5], f[6], f[7], f[8]};
			for (int32 c = 0; c < PlumeData; ++c)
			{
				I->SetCustomDataValue(Idx, c, D[c], false);
			}
			S.PlumeSchedule.Add(uint8(Flags & 0xffu));
			S.PlumeRate.Add(f[5]);
		}
		PlumeCards += K;
	}
	I->SetVisibility(bPlumesShown);
	I->RegisterComponent();
	PlumeComps.Add(I);
	S.Plumes = I;
	PlumeHour = -100.f;
	UpdatePlumeRates();
}

void ACityGenAtmos::DropPlumes(int32 Slot)
{
	if (!Slots.IsValidIndex(Slot))
	{
		return;
	}
	FSlot& S = Slots[Slot];
	if (UInstancedStaticMeshComponent* I = S.Plumes.Get())
	{
		PlumeCards -= I->GetInstanceCount();
		PlumeComps.Remove(I);
		I->DestroyComponent();
	}
	S.Plumes.Reset();
	S.PlumeSchedule.Reset();
	S.PlumeRate.Reset();
}

void ACityGenAtmos::SetSteam(bool bOn)
{
	bSteam = bOn;
	ShowPlumes(bAir);
}

void ACityGenAtmos::ShowPlumes(bool bOn)
{
	// (cars_steam: only with the steam on, issue #223)
	bOn = bOn && bSteam;
	bPlumesShown = bOn;
	for (UPrimitiveComponent* C : PlumeComps)
	{
		if (C)
		{
			C->SetVisibility(bOn);
		}
	}
}

FString ACityGenAtmos::PlumeDebug(const FString& Material)
{
	UMaterialInterface* Test = Material.IsEmpty() ? nullptr : LoadObject<UMaterialInterface>(nullptr, *Material);
	const FVector View = ViewLocation();
	FString Out;
	TArray<TPair<double, UInstancedStaticMeshComponent*>> Near;
	for (UPrimitiveComponent* C : PlumeComps)
	{
		if (UInstancedStaticMeshComponent* I = Cast<UInstancedStaticMeshComponent>(C))
		{
			if (Test)
			{
				I->SetMaterial(0, Test);
			}
			Near.Add(TPair<double, UInstancedStaticMeshComponent*>(FVector::Dist(I->Bounds.Origin, View), I));
		}
	}
	Near.Sort([](const auto& A, const auto& B) { return A.Key < B.Key; });
	for (int32 k = 0; k < FMath::Min(3, Near.Num()); ++k)
	{
		UInstancedStaticMeshComponent* I = Near[k].Value;
		FTransform X;
		if (I->GetInstanceCount() > 0)
		{
			I->GetInstanceTransform(0, X, true);
		}
		const UMaterialInterface* M = I->GetMaterial(0);
		Out += FString::Printf(TEXT("%s{\"dist_m\": %.0f, \"instances\": %d, \"visible\": %s, \"registered\": %s, "
			"\"proxy\": %s, \"bounds_r_m\": %.1f, \"cull\": [%d, %d], \"custom\": %d, \"data\": %d, "
			"\"first\": [%.0f, %.0f, %.0f], \"scale\": %.2f, \"material\": \"%s\"}"),
			Out.IsEmpty() ? TEXT("") : TEXT(", "), Near[k].Key / 100.0, I->GetInstanceCount(),
			I->IsVisible() ? TEXT("true") : TEXT("false"), I->IsRegistered() ? TEXT("true") : TEXT("false"),
			I->SceneProxy ? TEXT("true") : TEXT("false"), I->Bounds.SphereRadius / 100.0,
			I->InstanceStartCullDistance, I->InstanceEndCullDistance, I->NumCustomDataFloats,
			I->PerInstanceSMCustomData.Num(), X.GetLocation().X, X.GetLocation().Y, X.GetLocation().Z,
			X.GetScale3D().X, M ? *M->GetPathName() : TEXT("none"));
	}
	FString First;
	if (Near.Num() && Near[0].Value->GetInstanceCount() > 0)
	{
		const UInstancedStaticMeshComponent* I = Near[0].Value;
		for (int32 c = 0; c < FMath::Min(I->NumCustomDataFloats, I->PerInstanceSMCustomData.Num()); ++c)
		{
			First += FString::Printf(TEXT("%s%.3f"), First.IsEmpty() ? TEXT("") : TEXT(", "), I->PerInstanceSMCustomData[c]);
		}
	}
	const float MPCGain = AtmosCollection ? UKismetMaterialLibrary::GetScalarParameterValue(
		const_cast<ACityGenAtmos*>(this), AtmosCollection, TEXT("SteamGain")) : -1.f;
	return FString::Printf(TEXT("{\"components\": %d, \"shown\": %s, \"steam_gain\": %.2f, \"mpc_steam_gain\": %.2f, "
		"\"first_data\": [%s], \"near\": [%s]}"), PlumeComps.Num(), bPlumesShown ? TEXT("true") : TEXT("false"),
		SteamGain, MPCGain, *First, *Out);
}

void ACityGenAtmos::UpdatePlumeRates()
{
	// each card's opacity: its plume's at its schedule's share of the hour (again only when
	// the hour has moved a tenth)
	if (FMath::Abs(Hour - PlumeHour) < 0.1f)
	{
		return;
	}
	PlumeHour = Hour;
	for (FSlot& S : Slots)
	{
		UInstancedStaticMeshComponent* I = S.Plumes.Get();
		if (!S.bUsed || !I)
		{
			continue;
		}
		const int32 N = FMath::Min(I->GetInstanceCount(), S.PlumeRate.Num());
		for (int32 k = 0; k < N; ++k)
		{
			I->SetCustomDataValue(k, 7, S.PlumeRate[k] * ScheduleAt(S.PlumeSchedule[k]), false);
		}
		I->MarkRenderStateDirty();
	}
}

void ACityGenAtmos::EnsureRain()
{
	if (Rain)
	{
		return;
	}
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, RainMesh);
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, RainMaterial);
	if (!Mesh || !Mat)
	{
		UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: no rain (%s or %s missing: run the atmos assets)"),
			RainMesh, RainMaterial);
		return;
	}
	Rain = NewObject<UInstancedStaticMeshComponent>(this);
	Rain->SetupAttachment(RootComponent);
	Rain->SetUsingAbsoluteLocation(true);
	Rain->SetUsingAbsoluteRotation(true);
	Rain->SetStaticMesh(Mesh);
	// AT5: an instance of its own, for the covers' texture (the rain kept out of what is covered)
	RainMID = UMaterialInstanceDynamic::Create(Mat, this);
	SetCoverParams(RainMID);
	Rain->SetMaterial(0, RainMID ? static_cast<UMaterialInterface*>(RainMID) : Mat);
	Rain->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Rain->SetCastShadow(false);
	Rain->SetMobility(EComponentMobility::Movable);
	Rain->bAffectDistanceFieldLighting = false;
	Rain->bAffectDynamicIndirectLighting = false;
	Rain->bVisibleInRayTracing = false;
	// (falling by world position offset over the box: bounds that hold it)
	Rain->SetBoundsScale(4.f);
	FRandomStream R(1234);
	TArray<FTransform> Xf;
	for (int32 i = 0; i < RainCards; ++i)
	{
		const FVector P(R.FRandRange(-RainBoxCm, RainBoxCm), R.FRandRange(-RainBoxCm, RainBoxCm), RainTopCm);
		// the plane (100 cm square, its normal +Z) stood up facing +X: a streak 1.5 cm wide,
		// 70 to 110 cm long
		const float Len = R.FRandRange(0.7f, 1.1f);
		Xf.Add(FTransform(FRotator(-90.f, 0.f, 0.f), P, FVector(Len, 0.015, 1.0)));
	}
	Rain->AddInstances(Xf, false);
	Rain->RegisterComponent();
}

void ACityGenAtmos::SetRain(bool bOn)
{
	bRain = bOn;
	if (bOn)
	{
		EnsureRain();
		if (HasWeather())
		{
			EnsureSplashes();
			EnsureDrips();
		}
	}
	// (AT5: shown while the weather's rain falls: UpdateWeather)
	const bool bFalls = bOn && (!HasWeather() || WeatherNow[WRain] * WeatherNow[WDrops] > 0.005f);
	if (Rain)
	{
		Rain->SetVisibility(bFalls);
	}
	if (Splashes)
	{
		Splashes->SetVisibility(bFalls);
	}
	if (DripCards)
	{
		DripCards->SetVisibility(bOn && (bFalls || WetNow > 0.3f));
	}
	PushParameters();
}

void ACityGenAtmos::SetCoverParams(UMaterialInstanceDynamic* M) const
{
	// AT5: the plan's masks (the cover, the surface) and where they lie, the cover's datum
	if (!M)
	{
		return;
	}
	if (WetCover)
	{
		M->SetTextureParameterValue(TEXT("WetCover"), WetCover);
	}
	if (WetSurface)
	{
		M->SetTextureParameterValue(TEXT("WetSurface"), WetSurface);
	}
	if (WetBounds.Num() >= 3)
	{
		M->SetVectorParameterValue(TEXT("WetBounds"), FLinearColor(WetBounds[0], WetBounds[1], WetBounds[2], 0.f));
	}
	else
	{
		// (no masks: an empty window, every pixel past it)
		M->SetVectorParameterValue(TEXT("WetBounds"), FLinearColor(-1e9f, -1e9f, 1.f, 0.f));
	}
	M->SetVectorParameterValue(TEXT("CoverZ"), FLinearColor(CoverZ0Cm, CoverStepCm, 0.f, 0.f));
	M->SetScalarParameterValue(TEXT("FarGloss"), FarGloss);
}

void ACityGenAtmos::EnsureWet()
{
	EnsureWetDecals();
}

void ACityGenAtmos::EnsureWetDecals()
{
	// AT5: two deferred decals round the view reading the plan's masks: one darkens the wet
	// surfaces (the DBuffer's color), the other makes them glossy and the puddles mirrors with
	// the rain's rings (its roughness and normal); AT0's single decal painted the markings over
	if (Wet && WetGloss)
	{
		return;
	}
	UMaterialInterface* MC = LoadObject<UMaterialInterface>(nullptr, WetColorMaterial);
	UMaterialInterface* MG = LoadObject<UMaterialInterface>(nullptr, WetGlossMaterial);
	if (!MC || !MG)
	{
		UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: no wet streets (%s or %s missing: run the atmos assets)"),
			WetColorMaterial, WetGlossMaterial);
		return;
	}
	WetColorMID = UMaterialInstanceDynamic::Create(MC, this);
	WetGlossMID = UMaterialInstanceDynamic::Create(MG, this);
	SetCoverParams(WetColorMID);
	SetCoverParams(WetGlossMID);
	UDecalComponent* D[2] = {nullptr, nullptr};
	for (int32 k = 0; k < 2; ++k)
	{
		UDecalComponent* C = NewObject<UDecalComponent>(this);
		C->SetupAttachment(RootComponent);
		C->SetUsingAbsoluteLocation(true);
		C->SetUsingAbsoluteRotation(true);
		C->SetUsingAbsoluteScale(true);
		// (a decal projects along its +X: down; WetDepthCm either side of its middle, which
		// stands WetUpCm over the ground under the view: the streets, sidewalks, roofs and decks
		// of the city near the ground, and the walls a share)
		C->SetWorldRotation(FRotator(-90.f, 0.f, 0.f));
		C->DecalSize = FVector(WetDepthCm, WetHalfCm, WetHalfCm);
		C->SetDecalMaterial(k == 0 ? static_cast<UMaterialInterface*>(WetColorMID) : static_cast<UMaterialInterface*>(WetGlossMID));
		C->SetFadeScreenSize(0.f);
		C->SetSortOrder(-10 + k);
		C->RegisterComponent();
		D[k] = C;
	}
	Wet = D[0];
	WetGloss = D[1];
}

void ACityGenAtmos::SetWet(bool bOn)
{
	bWet = bOn;
	if (bOn)
	{
		EnsureWet();
	}
	const bool bShow = bOn && (!HasWeather() || WetNow > 0.003f || PuddleNow > 0.003f);
	if (Wet)
	{
		Wet->SetVisibility(bShow);
	}
	if (WetGloss)
	{
		WetGloss->SetVisibility(bShow);
	}
	WetAt = FVector(1e12);
	PushParameters();
}

void ACityGenAtmos::UpdateWetDecals(const FVector& View)
{
	if (!Wet || !WetGloss)
	{
		return;
	}
	// (recentred as the view moves WetSnapCm; its middle WetUpCm over the ground under the view)
	const FVector Snap(FMath::GridSnap(View.X, WetSnapCm), FMath::GridSnap(View.Y, WetSnapCm),
		FMath::GridSnap(double(GroundAt(View)), 500.0) + WetUpCm);
	if (!Snap.Equals(WetAt, 1.0))
	{
		WetAt = Snap;
		Wet->SetWorldLocation(Snap);
		WetGloss->SetWorldLocation(Snap);
	}
}

float ACityGenAtmos::GroundAt(const FVector& P) const
{
	return Sight.IsValid() ? float(Sight->GroundAt(P)) : 0.f;
}

// -- AT5: splashes and drips --

void ACityGenAtmos::EnsureSplashes()
{
	if (Splashes || !GetWorld())
	{
		return;
	}
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, RainMesh);
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, SplashMaterial);
	if (!Mesh || !Mat)
	{
		return;
	}
	UInstancedStaticMeshComponent* I = NewObject<UInstancedStaticMeshComponent>(this);
	I->SetupAttachment(RootComponent);
	I->SetUsingAbsoluteLocation(true);
	I->SetUsingAbsoluteRotation(true);
	I->SetUsingAbsoluteScale(true);
	I->SetStaticMesh(Mesh);
	I->SetMaterial(0, Mat);
	I->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	I->SetCastShadow(false);
	I->SetMobility(EComponentMobility::Movable);
	I->bAffectDistanceFieldLighting = false;
	I->bAffectDynamicIndirectLighting = false;
	I->bVisibleInRayTracing = false;
	I->NumCustomDataFloats = SplashData;
	// (the cards follow the view: each one's own spot is in its data; bounds round the range)
	const float Sc = 2.f * SplashRangeM;
	TArray<FTransform> Xf;
	const int32 N = FMath::Clamp(MaxSplashes, 0, 4096);
	for (int32 k = 0; k < N; ++k)
	{
		Xf.Add(FTransform(FRotator::ZeroRotator, FVector::ZeroVector, FVector(Sc, Sc, 1.0)));
	}
	I->AddInstances(Xf, false);
	FRandomStream R(4321);
	for (int32 k = 0; k < N; ++k)
	{
		const float D[SplashData] = {0.f, 0.f, -1e9f, R.FRand(), 0.f};
		for (int32 c = 0; c < SplashData; ++c)
		{
			I->SetCustomDataValue(k, c, D[c], false);
		}
	}
	I->RegisterComponent();
	Splashes = I;
	SplashAt.Init(FVector(0.0, 0.0, -1e9), N);
	SplashNext = 0;
}

void ACityGenAtmos::UpdateSplashes(const FVector& View)
{
	// a few spots a tick, round robin: each one's spot is where a trace down from the sky over
	// a random point within SplashRangeM lands (the rain's own landing spot: under a cover
	// there is none, on an awning its top); a spot out of range or not facing up has none
	UWorld* World = GetWorld();
	if (!Splashes || !World || SplashAt.Num() == 0)
	{
		return;
	}
	Splashes->SetWorldLocation(FVector(View.X, View.Y, View.Z - 100.0));
	// (in batches five times a second: each batch sends the cards' data to the render thread
	// once; every frame cost the render thread a fraction of a millisecond)
	const double Now = FPlatformTime::Seconds();
	if (SplashesAt >= 0.0 && Now - SplashesAt < 0.2)
	{
		return;
	}
	SplashesAt = Now;
	const double R = SplashRangeM * 100.0;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(CityGenSplash), false);
	if (const APlayerController* PC = World->GetFirstPlayerController())
	{
		if (const APawn* Pawn = PC->GetPawn())
		{
			Q.AddIgnoredActor(Pawn);
		}
	}
	bool bAny = false;
	const int32 N = SplashAt.Num();
	const int32 Per = FMath::Clamp(N / 3, 8, 192);
	for (int32 n = 0; n < Per; ++n)
	{
		const int32 k = SplashNext;
		SplashNext = (SplashNext + 1) % N;
		const FVector& At = SplashAt[k];
		const bool bValid = At.Z > -1e8 && FVector::DistSquared2D(At, View) < R * R;
		// (a valid spot is kept for a while, then moved: the splashes do not repeat in place)
		if (bValid && FMath::FRand() < 0.85f)
		{
			continue;
		}
		const double A = FMath::FRand() * 2.0 * UE_PI;
		const double D = R * FMath::Sqrt(FMath::Max(0.02, double(FMath::FRand())));
		const FVector P(View.X + D * FMath::Cos(A), View.Y + D * FMath::Sin(A), View.Z);
		FHitResult Hit;
		FVector Spot(0.0, 0.0, -1e9);
		if (World->LineTraceSingleByChannel(Hit, P + FVector(0.0, 0.0, SplashSkyCm),
			P - FVector(0.0, 0.0, SplashDownCm), ECC_Visibility, Q) && Hit.ImpactNormal.Z > 0.7)
		{
			Spot = Hit.ImpactPoint + FVector(0.0, 0.0, 1.0);
		}
		SplashAt[k] = Spot;
		Splashes->SetCustomDataValue(k, 0, float(Spot.X), false);
		Splashes->SetCustomDataValue(k, 1, float(Spot.Y), false);
		Splashes->SetCustomDataValue(k, 2, float(Spot.Z), false);
		Splashes->SetCustomDataValue(k, 4, Spot.Z > -1e8 ? FMath::FRandRange(9.f, 16.f) : 0.f, false);
		bAny = true;
	}
	if (bAny)
	{
		// (the changed instances' data alone, not the whole proxy made again: that hitched a frame)
		Splashes->MarkRenderInstancesDirty();
		SplashesLive = 0;
		for (const FVector& S : SplashAt)
		{
			SplashesLive += S.Z > -1e8 ? 1 : 0;
		}
	}
}

void ACityGenAtmos::EnsureDrips()
{
	if (DripCards || !GetWorld())
	{
		return;
	}
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, RainMesh);
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, DripMaterial);
	if (!Mesh || !Mat)
	{
		return;
	}
	UInstancedStaticMeshComponent* I = NewObject<UInstancedStaticMeshComponent>(this);
	I->SetupAttachment(RootComponent);
	I->SetUsingAbsoluteLocation(true);
	I->SetUsingAbsoluteRotation(true);
	I->SetUsingAbsoluteScale(true);
	I->SetStaticMesh(Mesh);
	I->SetMaterial(0, Mat);
	I->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	I->SetCastShadow(false);
	I->SetMobility(EComponentMobility::Movable);
	I->bAffectDistanceFieldLighting = false;
	I->bAffectDynamicIndirectLighting = false;
	I->bVisibleInRayTracing = false;
	I->NumCustomDataFloats = DripData;
	I->RegisterComponent();
	DripCards = I;
}

void ACityGenAtmos::UpdateDrips(const FVector& View, double Now)
{
	// the drip lines near the view: a card every DripStepM along each (a hash of where it is
	// jitters it and phases it), the nearest MaxDrips within DripRangeM, again every half a
	// second once the view has moved 4 m
	if (!DripCards || (Now - DripsAt < 0.5 && DripsAt >= 0.0) ||
		(DripsAt >= 0.0 && FVector::DistSquared(View, DripsView) < 400.0 * 400.0))
	{
		return;
	}
	DripsAt = Now;
	DripsView = View;
	const double R = DripRangeM * 100.0;
	const double Step = FMath::Max(10.0, double(DripStepM) * 100.0);
	struct FDrop { double D; FVector Top; float Fall; float Phase; float Rate; };
	TArray<FDrop> Drops;
	const FIntPoint C = CellOf(View);
	const int32 Reach = FMath::Max(1, FMath::CeilToInt32(DripRangeM / CellM) + 1);
	for (int32 dx = -Reach; dx <= Reach; ++dx)
	{
		for (int32 dy = -Reach; dy <= Reach; ++dy)
		{
			const TArray<int32>* At = SlotsAt.Find(FIntPoint(C.X + dx, C.Y + dy));
			if (!At)
			{
				continue;
			}
			for (int32 Slot : *At)
			{
				const FSlot& S = Slots[Slot];
				const int32 ND = S.Drips.Num() / CityGenAtmosPack::DripFloats;
				for (int32 d = 0; d < ND; ++d)
				{
					const float* f = S.Drips.GetData() + d * CityGenAtmosPack::DripFloats;
					const FVector A(f[0], f[1], f[4]), B(f[2], f[3], f[4]);
					const FVector Mid = (A + B) * 0.5;
					const double Half = FVector::Dist(A, B) * 0.5;
					if (FVector::Dist2D(Mid, View) > R + Half)
					{
						continue;
					}
					const float Rate = FMath::Fmod(f[6], 8.f);
					const float Fall = FMath::Max(50.f, f[4] - f[5]);
					const int32 K = FMath::Max(1, FMath::FloorToInt32(2.0 * Half / Step));
					for (int32 k = 0; k < K; ++k)
					{
						const uint32 H = Hash(uint32(Slot * 4096 + d), uint32(k));
						const double U = (double(k) + 0.25 + 0.5 * double(H & 0xff) / 255.0) / double(K);
						const FVector Top = FMath::Lerp(A, B, U);
						const double Dist = FVector::Dist(Top, View);
						if (Dist > R)
						{
							continue;
						}
						Drops.Add({Dist, Top, Fall, float((H >> 8) & 0xffff) / 65536.f, Rate});
					}
				}
			}
		}
	}
	Drops.Sort([](const FDrop& X, const FDrop& Y) { return X.D < Y.D; });
	const int32 N = FMath::Min(Drops.Num(), FMath::Clamp(MaxDrips, 0, 4096));
	DripCards->ClearInstances();
	TArray<FTransform> Xf;
	Xf.Reserve(N);
	for (int32 k = 0; k < N; ++k)
	{
		const FDrop& D = Drops[k];
		// (the card's bounds hold its fall: stood on its middle, as tall as it)
		Xf.Add(FTransform(FRotator(0.f, 0.f, 90.f), D.Top - FVector(0.0, 0.0, 0.5 * D.Fall),
			FVector(0.3, D.Fall / 100.0, 1.0)));
	}
	DripCards->AddInstances(Xf, false);
	for (int32 k = 0; k < N; ++k)
	{
		const FDrop& D = Drops[k];
		const float V[DripData] = {float(D.Top.X), float(D.Top.Y), float(D.Top.Z), D.Fall, D.Phase, D.Rate};
		for (int32 c = 0; c < DripData; ++c)
		{
			DripCards->SetCustomDataValue(k, c, V[c], false);
		}
	}
	DripCards->MarkRenderStateDirty();
	DripsLive = N;
}

// -- AT5: the weather's states --

int32 ACityGenAtmos::WeatherIndex(const FString& Name) const
{
	for (int32 k = 0; k < WeatherNames.Num(); ++k)
	{
		if (WeatherNames[k].Equals(Name, ESearchCase::IgnoreCase))
		{
			return k;
		}
	}
	return INDEX_NONE;
}

void ACityGenAtmos::StateValues(int32 Index, float* Out) const
{
	for (int32 k = 0; k < WeatherKeyCount; ++k)
	{
		const int32 i = Index * WeatherKeyCount + k;
		Out[k] = WeatherValues.IsValidIndex(i) ? WeatherValues[i] : WeatherNow[k];
	}
}

bool ACityGenAtmos::SetWeatherState(const FString& Name, bool bNow)
{
	const int32 Index = WeatherIndex(Name);
	if (Index == INDEX_NONE || !HasWeather())
	{
		return false;
	}
	FMemory::Memcpy(WeatherFrom, WeatherNow, sizeof(WeatherNow));
	StateValues(Index, WeatherTo);
	WeatherCur = WeatherTarget == INDEX_NONE ? Index : WeatherTarget;
	WeatherTarget = Index;
	TransitionT = 0.f;
	if (bNow || TransitionS <= 0.f)
	{
		FMemory::Memcpy(WeatherNow, WeatherTo, sizeof(WeatherNow));
		WeatherCur = Index;
		TransitionT = 1.f;
		WetNow = WeatherTo[WWetness];
		PuddleNow = WeatherTo[WPuddles];
	}
	UE_LOG(LogCityGenAtmos, Display, TEXT("CityGen atmos: weather %s%s"), *WeatherNames[Index],
		bNow ? TEXT(" (now)") : TEXT(""));
	ApplyWeather();
	return true;
}

void ACityGenAtmos::StepWeather(int32 Dir)
{
	if (!HasWeather())
	{
		return;
	}
	const int32 N = WeatherNames.Num();
	const int32 From = WeatherTarget == INDEX_NONE ? 0 : WeatherTarget;
	SetWeatherState(WeatherNames[((From + (Dir < 0 ? -1 : 1)) % N + N) % N], false);
}

FString ACityGenAtmos::GetWeatherLabel() const
{
	if (!HasWeather() || WeatherTarget == INDEX_NONE)
	{
		return FString();
	}
	if (TransitionT < 1.f && WeatherCur != INDEX_NONE && WeatherCur != WeatherTarget)
	{
		return FString::Printf(TEXT("%s > %s"), *WeatherNames[WeatherCur], *WeatherNames[WeatherTarget]);
	}
	return WeatherNames[WeatherTarget];
}

void ACityGenAtmos::HoldWetness(float InWet, float InPuddles)
{
	HeldWet = InWet;
	HeldPuddles = InPuddles;
	if (InWet >= 0.f)
	{
		WetNow = FMath::Clamp(InWet, 0.f, 1.f);
	}
	if (InPuddles >= 0.f)
	{
		PuddleNow = FMath::Clamp(InPuddles, 0.f, 1.f);
	}
	SetWet(bWet);
}

void ACityGenAtmos::UpdateWeather(float DeltaSeconds, const FVector& View)
{
	// the state's values blended through a change, the wind's gusts, the rain's age (the
	// streets wetting and drying, the puddles filling and draining), pushed to the material
	// parameter collections 15 times a second, the fog when it changed
	if (!HasWeather())
	{
		return;
	}
	const float Dt = DeltaSeconds * FMath::Max(0.f, WeatherSpeed);
	bool bFog0 = false;
	if (TransitionT < 1.f)
	{
		TransitionT = FMath::Min(1.f, TransitionT + Dt / FMath::Max(0.1f, TransitionS));
		const float S = FMath::SmoothStep(0.f, 1.f, TransitionT);
		for (int32 k = 0; k < WeatherKeyCount; ++k)
		{
			WeatherNow[k] = FMath::Lerp(WeatherFrom[k], WeatherTo[k], S);
		}
		if (TransitionT >= 1.f)
		{
			WeatherCur = WeatherTarget;
		}
		bFog0 = true;
	}
	const double T = WorldTime();
	const float G = 0.5f * FMath::Sin(float(T) * 0.37f) + 0.3f * FMath::Sin(float(T) * 1.13f + 1.f)
		+ 0.2f * FMath::Sin(float(T) * 2.9f + 2.f);
	WindNow = FMath::Max(0.f, WeatherNow[WWind] * (1.f + WeatherNow[WGust] * G));
	// the rain's age: the open surfaces toward the state's wetness, the puddles toward its fill
	// (faster in heavy rain, slower to dry and drain)
	const float RainF = FMath::Max(0.3f, WeatherNow[WRain] / 0.8f);
	auto Toward = [Dt, RainF](float& V, float Target, float Up, float Down)
	{
		if (V < Target)
		{
			V = FMath::Min(Target, V + Dt * RainF / FMath::Max(0.1f, Up));
		}
		else
		{
			V = FMath::Max(Target, V - Dt / FMath::Max(0.1f, Down));
		}
	};
	const bool bWasDry = WetNow <= 0.003f && PuddleNow <= 0.003f;
	if (HeldWet < 0.f)
	{
		Toward(WetNow, WeatherNow[WWetness], WetS, DryS);
	}
	if (HeldPuddles < 0.f)
	{
		Toward(PuddleNow, WeatherNow[WPuddles], FillS, DrainS);
	}
	const double Now = FPlatformTime::Seconds();
	if (WeatherPushedAt < 0.0 || Now - WeatherPushedAt > TimeEvery || bFog0)
	{
		WeatherPushedAt = Now;
		ApplyWeather();
	}
	const bool bDry = WetNow <= 0.003f && PuddleNow <= 0.003f;
	if (bDry != bWasDry)
	{
		SetWet(bWet);
	}
	if (bRain)
	{
		UpdateSplashes(View);
		UpdateDrips(View, Now);
	}
}

void ACityGenAtmos::ApplyWeather()
{
	if (!HasWeather())
	{
		return;
	}
	// the fog of the state (the look's), the clouds, the fog volumes' gain, the rain shown
	// while it falls, the parameters
	const bool bFogChanged = !FMath::IsNearlyEqual(FogDensity, WeatherNow[WFogDensity], 1e-5f) ||
		!FMath::IsNearlyEqual(FogFalloff, WeatherNow[WFogFalloff], 1e-4f) ||
		!FMath::IsNearlyEqual(FogVolumetric, WeatherNow[WFogExtinction], 1e-4f);
	FogDensity = WeatherNow[WFogDensity];
	FogFalloff = WeatherNow[WFogFalloff];
	FogVolumetric = WeatherNow[WFogExtinction];
	FogAlbedo = FLinearColor(WeatherNow[WAlbR], WeatherNow[WAlbG], WeatherNow[WAlbB]);
	RainRate = WeatherNow[WRain];
	WindMS = WindNow;
	if (bFog && bFogChanged)
	{
		SetFog(true);
	}
	if (!FMath::IsNearlyEqual(CoverApplied, WeatherNow[WCover], 1e-3f))
	{
		CoverApplied = WeatherNow[WCover];
		SetCloudCover(WeatherNow[WCover]);
	}
	// (shown, or not, as the rain starts and stops)
	const bool bFalls = bRain && WeatherNow[WRain] * WeatherNow[WDrops] > 0.005f;
	if (Rain && Rain->IsVisible() != bFalls)
	{
		Rain->SetVisibility(bFalls);
	}
	if (Splashes && Splashes->IsVisible() != bFalls)
	{
		Splashes->SetVisibility(bFalls);
	}
	const bool bDrips = bRain && (bFalls || WetNow > 0.3f);
	if (DripCards && DripCards->IsVisible() != bDrips)
	{
		DripCards->SetVisibility(bDrips);
	}
	PushParameters();
}

void ACityGenAtmos::PushParameters()
{
	if (AtmosCollection)
	{
		const bool bW = HasWeather();
		const float Heading = FMath::DegreesToRadians(WindHeadingDeg);
		auto Set = [this](const TCHAR* Name, float V)
		{
			UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, Name, V);
		};
		Set(TEXT("Rain"), bRain ? RainRate : 0.f);
		Set(TEXT("Wetness"), bWet ? (bW ? WetNow : 1.f) : 0.f);
		Set(TEXT("Puddles"), bWet ? (bW ? PuddleNow : 1.f) : 0.f);
		Set(TEXT("FogDensity"), bFog ? FogDensity : 0.f);
		Set(TEXT("WindMS"), WindMS);
		// (Unreal's Y is citygen's south: the heading's y turns over)
		Set(TEXT("WindX"), FMath::Cos(Heading));
		Set(TEXT("WindY"), -FMath::Sin(Heading));
		Set(TEXT("SteamGain"), SteamGain);
		// (AT6: the plumes' opacity kept far off)
		Set(TEXT("SteamFar"), SteamFar);
		Set(TEXT("SteamFarM"), SteamFarM);
		Set(TEXT("Streak"), bW ? WeatherNow[WStreak] : 1.f);
		Set(TEXT("Drops"), bW ? WeatherNow[WDrops] : 1.f);
	}
	if (CityCollection && ((bLights && HasPlan()) || (bSky && HasSky())))
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, CityCollection, TEXT("Hour"), Hour);
	}
	// AT5: the wind sways AG13's grass (MPC_CityGen's Wind: 1 a gale)
	if (CityCollection && HasWeather())
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, CityCollection, TEXT("Wind"),
			FMath::Clamp(WindMS / FMath::Max(1.f, GaleMS), 0.f, 1.f));
	}
}

// -- the tick --

void ACityGenAtmos::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const double Now = FPlatformTime::Seconds();
	FRotator ViewRot;
	const FVector View = ViewLocation(&ViewRot);
	// AT3: the hour runs (TimeSpeed hours a second), the sun moved 15 times a second
	if (TimeSpeed != 0.f)
	{
		Hour = FMath::Fmod(Hour + DeltaSeconds * TimeSpeed + 24.f, 24.f);
		if (TimeAppliedAt < 0.0 || Now - TimeAppliedAt > TimeEvery)
		{
			ApplyTime();
			PushParameters();
			// (AT4: the fog by the hour, the plumes' schedules)
			if (bFog)
			{
				SetFog(true);
			}
			UpdatePlumeRates();
		}
	}
	// AT4: the live fog volumes near the view, by day and by night
	if (bAir && (VolumesAt < 0.0 || Now - VolumesAt > LiveEvery))
	{
		VolumesAt = Now;
		UpdateVolumes();
	}
	// (the dome stays where it is, round the city: its material meets the deck along the view
	// ray from the camera's own position, so only a camera DomeRecenterCm from its middle moves
	// it: no render state sent for it frame after frame)
	if (Dome && FVector::Dist(Dome->GetComponentLocation(), View) > DomeRecenterCm)
	{
		Dome->SetWorldLocation(View);
	}
	// the plan's lights show by night (AT3: the controller's own Night, from the sun; a plan
	// without a sky, MPC_CityGen's, which the play features' switch sets): by day they cost
	// nothing
	const bool bNightNow = (bSky && HasSky()) ? NightNow > 0.02f :
		(!CityCollection || UKismetMaterialLibrary::GetScalarParameterValue(this, CityCollection, TEXT("Night")) > 0.5f);
	const bool bWant = bLights && HasPlan() && bNightNow;
	if (bWant != bShowing)
	{
		bShowing = bWant;
		if (!bWant)
		{
			ReleaseAll();
			// (visible lights: picked afresh when the lights come on again)
			bSightNow = bSightReady = bSightPicked = false;
			SeenAt.Reset();
		}
		SetPlayLamps(!bWant);
		LiveAt = -1.0;
	}
	if ((bShowing && bFixtures) != bFixturesShown)
	{
		ShowFixtures(bShowing && bFixtures);
	}
	// AT7: the far city's cards: built once the cells rest, shown with the lights, each card's
	// level as the hour moves, where they fade in as the live ranges move
	if (bFar && bFarDirty && (FarDirtyAt < 0.0 || Now - FarDirtyAt > FarSettleS))
	{
		RebuildFar();
	}
	const bool bFarWant = bShowing && HasFar() && FarComps.Num() > 0;
	if (bFarWant != bFarShown)
	{
		ShowFar(bFarWant);
	}
	if (bFarShown)
	{
		if (FMath::Abs(Hour - FarHourSet) > 0.05f)
		{
			UpdateFarLevels();
		}
		UpdateFarParams();
	}
	// a cell's beacons, beams and plumes near the view, by day too
	if (FixturesAt < 0.0 || Now - FixturesAt > FixturesEvery)
	{
		FixturesAt = Now;
		UpdateFixtureCells(View);
	}
	if (bShowing)
	{
		// (visible lights: a sweep come back is picked from at once)
		const bool bSwept = bSightNow && TakeSight(Now);
		if (bSwept || LiveAt < 0.0 || Now - LiveAt > LiveEvery)
		{
			LiveAt = Now;
			UpdateLive();
		}
		UpdateFades(DeltaSeconds, Now);
		UpdateFlicker(Now);
		if (bFixturesShown && BeamCount > 0)
		{
			UpdateBeams(WorldTime());
		}
	}
	if (bRain && Rain)
	{
		// (the cards round the view, turned to face it)
		Rain->SetWorldLocationAndRotation(View - FVector(0.0, 0.0, RainTopCm * 0.25),
			FRotator(0.0, ViewRot.Yaw + 180.0, 0.0));
	}
	// AT5: the weather (its states blending, the rain's age, splashes and drips near the view)
	UpdateWeather(DeltaSeconds, View);
	// AT6: the look's post, the districts' by where the view stands
	UpdatePost(DeltaSeconds, View, false);
	if (bWet && Wet)
	{
		UpdateWetDecals(View);
	}
}

FString ACityGenAtmos::GetStatus() const
{
	int32 Spots = 0, Points = 0, Rects = 0;
	TMap<uint8, int32> ByKind;
	for (const auto& KV : Live)
	{
		const FCityGenAtmosLight* L = LightOf(KV.Key);
		if (!L)
		{
			continue;
		}
		Spots += L->Shape == 0 ? 1 : 0;
		Points += L->Shape == 1 ? 1 : 0;
		Rects += L->Shape == 2 ? 1 : 0;
		ByKind.FindOrAdd(L->Kind) += 1;
	}
	FString Kinds;
	for (int32 k = 0; k < KindNames.Num(); ++k)
	{
		if (const int32* N = ByKind.Find(uint8(k)))
		{
			Kinds += FString::Printf(TEXT("%s\"%s\": %d"), Kinds.IsEmpty() ? TEXT("") : TEXT(", "),
				*KindNames[k], *N);
		}
	}
	const IConsoleVariable* RT = IConsoleManager::Get().FindConsoleVariable(TEXT("r.RayTracing"));
	return FString::Printf(TEXT("{\"plan\": %s, \"city\": \"%s\", \"plan_hash\": \"%s\", \"lights\": %d, "
		"\"cells\": %d, \"registrations\": %d, \"on\": %s, \"live\": %d, \"spot\": %d, \"point\": %d, "
		"\"rect\": %d, \"live_kinds\": {%s}, \"shadowed\": %d, \"candidates\": %d, \"max_live\": %d, "
		"\"mid_m\": %.0f, \"max_shadowed\": %d, \"update_ms\": %.3f, \"update_ms_max\": %.3f, "
		"\"scale\": %.5f, \"hour\": %.2f, \"fog\": %s, \"rain\": %s, \"wet\": %s, \"megalights\": %s, "
		"\"ray_tracing\": %d, \"components\": %d, \"showing\": %s, \"high\": %d, \"max_high\": %d, "
		"\"high_m\": %.0f, \"candidates_high\": %d, \"animated\": %d, \"beacons\": %d, \"beams\": %d, "
		"\"fixtures\": %s, \"sky\": %s, \"night_now\": %.3f, \"ev100\": %.2f, \"sun_elev\": %.2f, "
		"\"moon_elev\": %.2f, \"moon_lux\": %.4f, \"time_speed\": %.3f, \"dome\": %s, \"deck_m\": %.0f, "
		"\"cover\": %.2f, \"glow\": %s, \"day_hour\": %.2f, \"dusk_hour\": %.2f, \"night_hour\": %.2f, "
		"\"air\": %s, \"volumes\": %d, \"volumes_live\": %d, \"candidates_volumes\": %d, \"emitters\": %d, "
		"\"plume_cards\": %d, \"plumes_shown\": %s, \"fog_share\": %.3f, \"fog_view_m\": %.0f, \"tuned\": %s, "
		"\"cvars\": %d, \"sight\": %s, \"sight_wanted\": %s, \"sight_raster\": %s, \"sight_m\": %.0f, "
		"\"sight_max\": %d, \"sight_seen\": %d, \"sight_picked\": %d, \"sight_tested\": %d, \"sight_rays\": %d, "
		"\"sight_ms\": %.3f, \"sight_ms_max\": %.3f, \"sight_launch_ms\": %.3f, \"sight_sweeps\": %d, "
		"\"walker\": %s, \"fading\": %d, \"fade_s\": %.2f, \"fixture_cells\": %d, %s}"),
		HasPlan() ? TEXT("true") : TEXT("false"), *City, *PlanHash, RegisteredLights, SlotOfActor.Num(),
		Registrations, bLights ? TEXT("true") : TEXT("false"), Live.Num(), Spots, Points, Rects, *Kinds,
		Shadowed.Num(), Candidates, MaxLive, MidRangeM, MaxShadowed, UpdateMs, UpdateMsMax, Scale(), Hour,
		bFog ? TEXT("true") : TEXT("false"), bRain ? TEXT("true") : TEXT("false"),
		bWet ? TEXT("true") : TEXT("false"), bMegaLights ? TEXT("true") : TEXT("false"),
		RT ? RT->GetInt() : -1, AllLights.Num(), bShowing ? TEXT("true") : TEXT("false"), LiveHigh, MaxHigh,
		HighRangeM, CandidatesHigh, Flickering.Num(), BeaconCount, BeamCount,
		bFixturesShown ? TEXT("true") : TEXT("false"),
		(bSky && HasSky()) ? TEXT("true") : TEXT("false"), NightNow, EVNow, SunElev, MoonElev, MoonLux,
		TimeSpeed, Dome ? TEXT("true") : TEXT("false"), CloudDeckM, CoverNow,
		SkyGlow ? TEXT("true") : TEXT("false"), DayHour, DuskHour, NightHour,
		bAir ? TEXT("true") : TEXT("false"), RegisteredVolumes, LiveVolumes.Num(), CandidatesVolumes,
		RegisteredEmitters, PlumeCards, bPlumesShown ? TEXT("true") : TEXT("false"), FogShare(), FogViewM,
		bCVarsApplied ? TEXT("true") : TEXT("false"), SavedCVars.Num(),
		bSightPicked ? TEXT("true") : TEXT("false"), bSightNow ? TEXT("true") : TEXT("false"),
		Sight.IsValid() ? TEXT("true") : TEXT("false"), SightRangeM, SightMax, SeenAt.Num(), SightPickedN,
		SightTested, SightRays, SightMs, SightMsMax, SightLaunchMs, SightSweeps,
		IsWalker() ? TEXT("true") : TEXT("false"), FadingNow, FadeS, FixtureCells(),
		*FString::Printf(TEXT("\"weather\": %s, \"weather_now\": \"%s\", \"weather_target\": \"%s\", "
			"\"transition\": %.3f, \"rain_now\": %.3f, \"drops\": %.3f, \"streak\": %.3f, \"wetness\": %.3f, "
			"\"puddles\": %.3f, \"wind_ms\": %.2f, \"cloud_cover\": %.3f, \"volume_gain\": %.3f, "
			"\"fog_density\": %.4f, \"rain_shown\": %s, \"wet_shown\": %s, \"splashes\": %d, "
			"\"splashes_live\": %d, \"drips\": %d, \"drip_lines\": %d, \"wet_textures\": %s, "
			"\"weather_speed\": %.2f, \"post\": %s, \"post_districts\": %s, \"post_where\": \"%s\", "
			"\"post_bloom\": %.3f, \"post_grain\": %.3f, \"post_fringe\": %.3f, \"post_saturation\": %.3f, "
			"\"post_contrast\": %.3f, \"post_sharpen\": %.3f, \"overcast_shift\": %.3f, %s"),
			HasWeather() ? TEXT("true") : TEXT("false"), *GetWeatherLabel(),
			WeatherNames.IsValidIndex(WeatherTarget) ? *WeatherNames[WeatherTarget] : TEXT(""),
			TransitionT, WeatherNow[WRain], WeatherNow[WDrops], WeatherNow[WStreak], WetNow, PuddleNow,
			WindNow, CoverNow, WeatherNow[WVolumes], FogDensity,
			(Rain && Rain->IsVisible()) ? TEXT("true") : TEXT("false"),
			(Wet && Wet->IsVisible()) ? TEXT("true") : TEXT("false"),
			Splashes ? Splashes->GetInstanceCount() : 0, SplashesLive, DripsLive, DripLines,
			(WetCover && WetSurface) ? TEXT("true") : TEXT("false"), WeatherSpeed,
			HasPost() ? TEXT("true") : TEXT("false"), bDistrictPost ? TEXT("true") : TEXT("false"),
			*PostWhere, PostNow[PBloom], PostNow[PGrain], PostNow[PChromatic], PostNow[PSaturation],
			PostNow[PContrast], PostNow[PSharpen], OvercastShift(),
			// AT7: the far city
			*FString::Printf(TEXT("\"far\": %s, \"far_cards\": %d, \"far_glows\": %d, \"far_flats\": %d, "
				"\"far_blocks\": %d, \"far_shown\": %s, \"far_build_ms\": %.1f, \"far_px\": %.6f, "
				"\"far_gain\": %.3f, \"far_mid_m\": %.0f, \"far_high_m\": %.0f, \"far_fix_m\": %.0f"),
				HasFar() ? TEXT("true") : TEXT("false"), FarCards, FarGlows, FarFlats, FarBlocks.Num(),
				bFarShown ? TEXT("true") : TEXT("false"), FarBuildMs, FarPxNow, FarGain, FarSet[1],
				FarSet[2], FarSet[3])));
}

// -- AT3: the sky and time --

FVector ACityGenAtmos::Body(float LatDeg, float DecDeg, float HourAngleDeg, float& OutElevDeg)
{
	// (atmosgen/sky.py's `body`): elevation and azimuth from north, clockwise; the direction
	// toward the body in Unreal's frame (X east, Y south, Z up)
	const double La = FMath::DegreesToRadians(double(LatDeg));
	const double De = FMath::DegreesToRadians(double(DecDeg));
	const double Ha = FMath::DegreesToRadians(double(HourAngleDeg));
	const double Se = FMath::Sin(La) * FMath::Sin(De) + FMath::Cos(La) * FMath::Cos(De) * FMath::Cos(Ha);
	const double E = FMath::Asin(FMath::Clamp(Se, -1.0, 1.0));
	const double Az = FMath::Atan2(-FMath::Sin(Ha) * FMath::Cos(De),
		FMath::Cos(La) * FMath::Sin(De) - FMath::Sin(La) * FMath::Cos(De) * FMath::Cos(Ha));
	OutElevDeg = float(FMath::RadiansToDegrees(E));
	const double Ce = FMath::Cos(E);
	return FVector(Ce * FMath::Sin(Az), -Ce * FMath::Cos(Az), FMath::Sin(E));
}

float ACityGenAtmos::CurveAt(const TArray<float>& Values, float Elev) const
{
	const int32 N = FMath::Min(CurveElev.Num(), Values.Num());
	if (N == 0)
	{
		return 0.f;
	}
	if (Elev <= CurveElev[0])
	{
		return Values[0];
	}
	for (int32 k = 1; k < N; ++k)
	{
		if (Elev <= CurveElev[k])
		{
			const float T = (Elev - CurveElev[k - 1]) / FMath::Max(1e-4f, CurveElev[k] - CurveElev[k - 1]);
			return FMath::Lerp(Values[k - 1], Values[k], T);
		}
	}
	return Values[N - 1];
}

void ACityGenAtmos::FindLighting()
{
	UWorld* World = GetWorld();
	if (bLightingFound || !World)
	{
		return;
	}
	// the importer's sun and sky light (by their keys), else the first of each
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		if (!Sun || It->Tags.Contains(SunKey))
		{
			Sun = *It;
		}
	}
	for (TActorIterator<ASkyLight> It(World); It; ++It)
	{
		if (!SkyLightActor || It->Tags.Contains(SkyKey))
		{
			SkyLightActor = *It;
		}
	}
	if (UDirectionalLightComponent* L = Sun ? Cast<UDirectionalLightComponent>(Sun->GetLightComponent()) : nullptr)
	{
		DaySunColor = L->GetLightColor();
		L->SetMobility(EComponentMobility::Movable);
	}
	if (USkyLightComponent* S = SkyLightActor ? SkyLightActor->GetLightComponent() : nullptr)
	{
		DaySkyIntensity = S->Intensity;
	}
	bLightingFound = true;
}

void ACityGenAtmos::EnsureDome()
{
	if (Dome || !bSky || !HasSky() || !GetWorld())
	{
		return;
	}
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, DomeMesh);
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, SkyMaterialPath);
	if (!Mesh || !Mat)
	{
		UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: no sky dome (%s or %s missing: run the atmos assets)"),
			DomeMesh, SkyMaterialPath);
		return;
	}
	SkyMID = UMaterialInstanceDynamic::Create(Mat, this);
	if (SkyGlow)
	{
		SkyMID->SetTextureParameterValue(TEXT("Glow"), SkyGlow);
	}
	if (GlowBounds.Num() >= 4)
	{
		SkyMID->SetVectorParameterValue(TEXT("GlowLo"), FLinearColor(GlowBounds[0], GlowBounds[1], 0.f, 0.f));
		SkyMID->SetVectorParameterValue(TEXT("GlowHi"), FLinearColor(GlowBounds[2], GlowBounds[3], 0.f, 0.f));
	}
	Dome = NewObject<UStaticMeshComponent>(this);
	Dome->SetupAttachment(RootComponent);
	Dome->SetUsingAbsoluteLocation(true);
	Dome->SetUsingAbsoluteRotation(true);
	Dome->SetUsingAbsoluteScale(true);
	Dome->SetStaticMesh(Mesh);
	Dome->SetMaterial(0, SkyMID);
	Dome->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Dome->SetCastShadow(false);
	Dome->bAffectDistanceFieldLighting = false;
	Dome->bAffectDynamicIndirectLighting = false;
	Dome->bVisibleInRayTracing = false;
	Dome->SetMobility(EComponentMobility::Movable);
	Dome->SetWorldScale3D(FVector(DomeScale));
	// (round the glow's middle, the city's, else the view)
	Dome->SetWorldLocation(GlowBounds.Num() >= 4
		? FVector(0.5 * (GlowBounds[0] + GlowBounds[2]), 0.5 * (GlowBounds[1] + GlowBounds[3]), 0.0)
		: ViewLocation());
	Dome->RegisterComponent();
}

void ACityGenAtmos::ApplyTime()
{
	TimeAppliedAt = FPlatformTime::Seconds();
	if (!bSky || !HasSky())
	{
		return;
	}
	FindLighting();
	float E = 0.f, ME = 0.f;
	const FVector S = Body(LatitudeDeg, DeclinationDeg, 15.f * (Hour - 12.f), E);
	const FVector M = Body(LatitudeDeg, MoonDeclinationDeg, 15.f * (Hour - 12.f - MoonLagH), ME);
	SunElev = E;
	MoonElev = ME;
	NightNow = FMath::Clamp(CurveAt(CurveNight, E), 0.f, 1.f);
	SunWeight = FMath::Clamp(CurveAt(CurveSun, E), 0.f, 1.f);
	const float DayShare = CurveAt(CurveEV, E);
	EVNow = SceneEV100 + (DayEV100 - SceneEV100) * DayShare;
	// (AT6: by day the weather's overcast partly given back)
	EVNow += DayShare * OvercastShift();
	const float R0 = MoonRise.Num() >= 2 ? MoonRise[0] : -1.f;
	const float R1 = MoonRise.Num() >= 2 ? MoonRise[1] : 6.f;
	const float MoonUp = FMath::SmoothStep(R0, R1, ME);
	// the one directional light: the sun while its light lasts (it still lights the twilight
	// sky from under the horizon), then the moon, faded in from the sun at -12 degrees to -16
	const float MoonIn = FMath::Clamp((-12.f - E) / 4.f, 0.f, 1.f);
	MoonLux = SunLux * MoonShare * MoonLit * MoonUp * MoonIn * (1.f - MoonCloud * CoverNow);
	if (UDirectionalLightComponent* L = Sun ? Cast<UDirectionalLightComponent>(Sun->GetLightComponent()) : nullptr)
	{
		const bool bSunLight = SunWeight > 0.f;
		const FVector To = bSunLight ? S : M;
		Sun->SetActorRotation((-To).Rotation());
		// (AT5: the weather's overcast takes the sun's direct light: a rainy, foggy day's light
		// comes from the sky, not hard sun shadows; a clear day keeps it all)
		const float Overcast = HasWeather() ? 1.f - 0.75f * FMath::Clamp((CoverNow - 0.5f) / 0.5f, 0.f, 1.f) : 1.f;
		L->SetIntensity(bSunLight ? SunLux * SunWeight * Overcast : MoonLux);
		L->SetLightColor(bSunLight ? DaySunColor : MoonColor);
	}
	if (USkyLightComponent* SL = SkyLightActor ? SkyLightActor->GetLightComponent() : nullptr)
	{
		SL->SetIntensity(DaySkyIntensity * CurveAt(CurveSky, E));
	}
	// the exposure held at the hour's (no eye adaptation at night: it would pump)
	EnsureVolume();
	if (Volume)
	{
		FPostProcessSettings& P = Volume->Settings;
		P.bOverride_AutoExposureMinBrightness = bLockExposure;
		P.bOverride_AutoExposureMaxBrightness = bLockExposure;
		P.bOverride_AutoExposureBias = bLockExposure;
		P.bOverride_AutoExposureSpeedUp = bLockExposure;
		P.bOverride_AutoExposureSpeedDown = bLockExposure;
		P.AutoExposureMinBrightness = EVNow;
		P.AutoExposureMaxBrightness = EVNow;
		P.AutoExposureBias = 0.f;
		P.AutoExposureSpeedUp = 20.f;
		P.AutoExposureSpeedDown = 20.f;
	}
	if (CityCollection)
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, CityCollection, TEXT("Night"), NightNow);
		UKismetMaterialLibrary::SetScalarParameterValue(this, CityCollection, TEXT("Hour"), Hour);
	}
	// AT6: the plumes lit by the city by night
	if (AtmosCollection)
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, TEXT("SteamGlow"),
			SteamGlow * NightNow);
	}
	if (SkyMID)
	{
		SkyMID->SetVectorParameterValue(TEXT("SunDir"), FLinearColor(S.X, S.Y, S.Z, 0.f));
		SkyMID->SetVectorParameterValue(TEXT("MoonDir"), FLinearColor(M.X, M.Y, M.Z, 0.f));
		SkyMID->SetVectorParameterValue(TEXT("MoonTint"), FMath::Lerp(FLinearColor::White, MoonColor, 0.25f));
		SkyMID->SetScalarParameterValue(TEXT("MoonVis"), MoonShare > 0.f ? MoonUp : 0.f);
		SkyMID->SetScalarParameterValue(TEXT("MoonLum"), MoonDiskNits);
		SkyMID->SetScalarParameterValue(TEXT("MoonRad"), FMath::DegreesToRadians(0.5f * MoonDiskDeg));
		SkyMID->SetScalarParameterValue(TEXT("SunDiskOn"), SunWeight > 0.f ? 1.f : 0.f);
		SkyMID->SetScalarParameterValue(TEXT("Stars"), Stars * FMath::Clamp(CurveAt(CurveStars, E), 0.f, 1.f));
		SkyMID->SetScalarParameterValue(TEXT("DeckCm"), CloudDeckM * 100.f);
		SkyMID->SetScalarParameterValue(TEXT("Cover"), CloudDeckM > 0.f ? CoverNow : 0.f);
		SkyMID->SetScalarParameterValue(TEXT("GlowMax"), GlowMaxNits);
		// (the glow in physical units, shown as the plan's lights are, by night)
		SkyMID->SetScalarParameterValue(TEXT("GlowScale"), Scale() * NightNow * GlowGain);
		SkyMID->SetScalarParameterValue(TEXT("CloudLit"), CloudLit);
		SkyMID->SetScalarParameterValue(TEXT("Wind"), 0.4f * WindMS);
	}
}

void ACityGenAtmos::SetSky(bool bOn)
{
	bSky = bOn;
	if (bOn)
	{
		EnsureDome();
		ApplyTime();
	}
	// (off: the dome hidden, the level's lighting and the exposure left as the last hour set
	// them, so the night without the sky costs what the sky costs)
	if (Dome)
	{
		Dome->SetVisibility(bOn);
	}
	LiveAt = -1.0;
}

void ACityGenAtmos::SetTimeSpeed(float HoursPerSecond)
{
	TimeSpeed = HoursPerSecond;
}

void ACityGenAtmos::SetLockExposure(bool bOn)
{
	bLockExposure = bOn;
	ApplyTime();
}

void ACityGenAtmos::SetCloudCover(float Cover)
{
	CoverNow = FMath::Clamp(Cover, 0.f, 1.f);
	ApplyTime();
}

// -- AT6: the look --

void ACityGenAtmos::MakePostRaster()
{
	PostIdx.Reset();
	const int64 N = int64(PostWidth) * int64(PostHeight);
	if (N <= 0 || PostBounds.Num() < 4 || PostRuns.Num() < 2 || PostCellM <= 0.f)
	{
		return;
	}
	PostIdx.SetNumUninitialized(N);
	int64 At = 0;
	for (int32 k = 0; k + 1 < PostRuns.Num(); k += 2)
	{
		const int64 C = PostRuns[k];
		if (C <= 0 || At + C > N)
		{
			UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: the post raster's runs overrun its cells; the look's post alone"));
			PostIdx.Reset();
			return;
		}
		FMemory::Memset(PostIdx.GetData() + At, uint8(PostRuns[k + 1]), C);
		At += C;
	}
	if (At != N)
	{
		PostIdx.Reset();
	}
}

void ACityGenAtmos::PostTarget(const FVector& View)
{
	// each district's weight where the view stands: the raster sampled on a 5 x 5 grid over
	// a disc PostBlendM wide round it, a tent from its middle (a cell under no district, or a
	// view off the raster, counts for the look's own)
	const int32 ND = PostNames.Num();
	PostWTarget.Init(0.f, ND + 1);
	if (!bDistrictPost || PostIdx.Num() == 0 || PostDistricts.Num() < ND * 2 * PostFloats)
	{
		PostWTarget[ND] = 1.f;
		return;
	}
	const double Cell = double(PostCellM) * 100.0;
	const double R = double(PostBlendM) * 100.0;
	float Sum = 0.f;
	for (int32 j = -2; j <= 2; ++j)
	{
		for (int32 i = -2; i <= 2; ++i)
		{
			const double dx = R * i / 2.0, dy = R * j / 2.0;
			const double r = FMath::Sqrt(dx * dx + dy * dy) / FMath::Max(1.0, R);
			if (r > 1.0001)
			{
				continue;
			}
			const float W = float(1.25 - r);
			const int32 cx = FMath::FloorToInt32((View.X + dx - PostBounds[0]) / Cell);
			const int32 cy = FMath::FloorToInt32((View.Y + dy - PostBounds[1]) / Cell);
			int32 D = ND;
			if (cx >= 0 && cy >= 0 && cx < PostWidth && cy < PostHeight)
			{
				const uint8 V = PostIdx[int64(cy) * PostWidth + cx];
				D = V < ND ? int32(V) : ND;
			}
			PostWTarget[D] += W;
			Sum += W;
		}
	}
	for (float& W : PostWTarget)
	{
		W /= FMath::Max(1e-6f, Sum);
	}
}

void ACityGenAtmos::UpdatePost(float DeltaSeconds, const FVector& View, bool bNow)
{
	if (!HasPost())
	{
		return;
	}
	const double Now = FPlatformTime::Seconds();
	if (bNow || PostAt < 0.0 || Now - PostAt > LiveEvery)
	{
		PostAt = Now;
		PostTarget(View);
	}
	const int32 ND = PostNames.Num();
	if (PostW.Num() != ND + 1 || bNow)
	{
		PostW = PostWTarget;
	}
	else
	{
		const float A = 1.f - FMath::Exp(-DeltaSeconds / FMath::Max(0.05f, PostEaseS));
		for (int32 k = 0; k <= ND; ++k)
		{
			PostW[k] += (PostWTarget[k] - PostW[k]) * A;
		}
	}
	// the sets blended: night and day by Night, the districts by their weights
	const float Nt = FMath::Clamp(NightNow, 0.f, 1.f);
	float S[PostFloats] = {};
	float Best = -1.f;
	for (int32 k = 0; k <= ND; ++k)
	{
		const float W = PostW[k];
		if (W > Best)
		{
			Best = W;
			PostWhere = k < ND ? PostNames[k] : TEXT("");
		}
		if (W <= 1e-4f)
		{
			continue;
		}
		const float* Src = k < ND ? PostDistricts.GetData() + k * 2 * PostFloats : PostBase.GetData();
		for (int32 f = 0; f < PostFloats; ++f)
		{
			S[f] += W * (Nt * Src[f] + (1.f - Nt) * Src[PostFloats + f]);
		}
	}
	// (art direction: a key held at a value for the session, CityGenAtmos.PostSet)
	for (const TPair<int32, float>& O : PostOverride)
	{
		if (O.Key >= 0 && O.Key < PostFloats)
		{
			S[O.Key] = O.Value;
		}
	}
	// (applied only when something moved: the volume's settings are read every frame)
	float Moved = bPostApplied ? 0.f : 1.f;
	for (int32 f = 0; f < PostFloats; ++f)
	{
		Moved = FMath::Max(Moved, FMath::Abs(S[f] - PostNow[f]));
	}
	if (Moved > 1e-4f)
	{
		FMemory::Memcpy(PostNow, S, sizeof(S));
		ApplyPostSettings(PostNow);
	}
}

void ACityGenAtmos::ApplyPostSettings(const float* S)
{
	EnsureVolume();
	if (!Volume)
	{
		return;
	}
	FPostProcessSettings& P = Volume->Settings;
	P.bOverride_BloomIntensity = true;
	P.BloomIntensity = S[PBloom];
	P.bOverride_LensFlareIntensity = true;
	P.LensFlareIntensity = S[PFlare];
	P.bOverride_LensFlareThreshold = true;
	P.LensFlareThreshold = S[PFlareThreshold];
	P.bOverride_FilmGrainIntensity = true;
	P.FilmGrainIntensity = S[PGrain];
	P.bOverride_SceneFringeIntensity = true;
	P.SceneFringeIntensity = S[PChromatic];
	P.bOverride_ChromaticAberrationStartOffset = true;
	P.ChromaticAberrationStartOffset = S[PChromaticStart];
	P.bOverride_VignetteIntensity = true;
	P.VignetteIntensity = S[PVignette];
	P.bOverride_Sharpen = true;
	P.Sharpen = S[PSharpen];
	P.bOverride_ColorSaturation = true;
	P.ColorSaturation = FVector4(1.0, 1.0, 1.0, S[PSaturation]);
	P.bOverride_ColorContrast = true;
	P.ColorContrast = FVector4(1.0, 1.0, 1.0, S[PContrast]);
	P.bOverride_ColorSaturationHighlights = true;
	P.ColorSaturationHighlights = FVector4(1.0, 1.0, 1.0, S[PHighlightSat]);
	P.bOverride_ColorOffsetShadows = true;
	P.ColorOffsetShadows = FVector4(0.0, 0.0, 0.0, S[PLift]);
	P.bOverride_ColorGainShadows = true;
	P.ColorGainShadows = FVector4(S[PShadowR], S[PShadowG], S[PShadowB], 1.0);
	P.bOverride_ColorGainHighlights = true;
	P.ColorGainHighlights = FVector4(S[PHighR], S[PHighG], S[PHighB], 1.0);
	P.bOverride_LocalExposureShadowContrastScale = true;
	P.LocalExposureShadowContrastScale = S[PLocalShadows];
	P.bOverride_LocalExposureHighlightContrastScale = true;
	P.LocalExposureHighlightContrastScale = S[PLocalHighlights];
	bPostApplied = true;
}

void ACityGenAtmos::ClearPostSettings()
{
	if (!Volume)
	{
		return;
	}
	FPostProcessSettings& P = Volume->Settings;
	P.bOverride_BloomIntensity = P.bOverride_LensFlareIntensity = P.bOverride_LensFlareThreshold = false;
	P.bOverride_FilmGrainIntensity = P.bOverride_SceneFringeIntensity = false;
	P.bOverride_ChromaticAberrationStartOffset = P.bOverride_VignetteIntensity = false;
	P.bOverride_Sharpen = P.bOverride_ColorSaturation = P.bOverride_ColorContrast = false;
	P.bOverride_ColorSaturationHighlights = P.bOverride_ColorOffsetShadows = false;
	P.bOverride_ColorGainShadows = P.bOverride_ColorGainHighlights = false;
	P.bOverride_LocalExposureShadowContrastScale = false;
	P.bOverride_LocalExposureHighlightContrastScale = false;
	bPostApplied = false;
}

void ACityGenAtmos::SetPost(bool bOn)
{
	bPost = bOn;
	if (HasPost())
	{
		bPostApplied = false;
		UpdatePost(0.f, ViewLocation(), true);
	}
	else
	{
		ClearPostSettings();
	}
	ApplyTime();
}

void ACityGenAtmos::SetPostDistricts(bool bOn)
{
	bDistrictPost = bOn;
	if (HasPost())
	{
		UpdatePost(0.f, ViewLocation(), true);
	}
}

bool ACityGenAtmos::SetPostValue(const FString& Key, float Value, bool bClear)
{
	static const TCHAR* Names[PostFloats] = {TEXT("bloom"), TEXT("flare"), TEXT("flare_threshold"),
		TEXT("grain"), TEXT("chromatic"), TEXT("chromatic_start"), TEXT("vignette"), TEXT("sharpen"),
		TEXT("saturation"), TEXT("contrast"), TEXT("highlight_sat"), TEXT("lift"), TEXT("local_shadows"),
		TEXT("local_highlights"), TEXT("shadows_r"), TEXT("shadows_g"), TEXT("shadows_b"),
		TEXT("highlights_r"), TEXT("highlights_g"), TEXT("highlights_b")};
	if (Key == TEXT("clear") || Key == TEXT("all"))
	{
		PostOverride.Reset();
	}
	else
	{
		int32 K = INDEX_NONE;
		for (int32 k = 0; k < PostFloats; ++k)
		{
			K = Key.Equals(Names[k], ESearchCase::IgnoreCase) ? k : K;
		}
		if (K == INDEX_NONE)
		{
			return false;
		}
		if (bClear)
		{
			PostOverride.Remove(K);
		}
		else
		{
			PostOverride.Add(K, Value);
		}
	}
	if (HasPost())
	{
		UpdatePost(0.f, ViewLocation(), true);
	}
	return true;
}

void ACityGenAtmos::SetDayEV(float EV)
{
	DayEV100 = EV;
	ApplyTime();
}

float ACityGenAtmos::OvercastShift() const
{
	// AT6: by day the exposure gives back OvercastComp of the light the weather's clouds take
	// off the sun (AT5's overcast) past the plan's own cover, a day street's light SkyShare
	// the sky's (in stops: under 0 a brighter exposure)
	if (!HasPost() || OvercastComp <= 0.f)
	{
		return 0.f;
	}
	const float C0 = OvercastTake.Num() >= 2 ? OvercastTake[0] : 0.5f;
	const float Take = OvercastTake.Num() >= 2 ? OvercastTake[1] : 0.75f;
	auto Light = [&](float Cover)
	{
		const float Sun = 1.f - Take * FMath::Clamp((Cover - C0) / FMath::Max(1e-3f, 1.f - C0), 0.f, 1.f);
		return (1.f - SkyShare) * Sun + SkyShare;
	};
	return OvercastComp * FMath::Log2(FMath::Max(1e-3f, Light(CoverNow)) / FMath::Max(1e-3f, Light(RefCover)));
}

bool ACityGenAtmos::SetNamedHour(const FString& Name)
{
	const FString N = Name.ToLower();
	if (N == TEXT("day")) { SetHour(DayHour); }
	else if (N == TEXT("dusk")) { SetHour(DuskHour); }
	else if (N == TEXT("night")) { SetHour(NightHour); }
	else { return false; }
	return true;
}
