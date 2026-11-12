#include "CityGenAtmosActor.h"

#include "CityGenAtmosCell.h"

#include "Camera/PlayerCameraManager.h"
#include "Components/DecalComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Math/RandomStream.h"

DEFINE_LOG_CATEGORY_STATIC(LogCityGenAtmos, Log, All);

namespace
{
	constexpr double LiveEvery = 0.2;        // s between choosing the live set
	constexpr float FadeShare = 0.2f;        // the farthest share of the mid range fades out
	constexpr double WetSnapCm = 4000.0;     // the wet decal follows the view in 40 m steps
	constexpr float WetHalfCm = 30000.f;     // ... 600 m square
	constexpr float RainBoxCm = 2500.f;      // rain cards within 25 m of the view ...
	constexpr float RainTopCm = 1200.f;      // ... falling from 12 m over it (24 m in all)
	const TCHAR* AtmosMPC = TEXT("/Game/CityGen/Core/Atmos/MPC_CityGenAtmos.MPC_CityGenAtmos");
	const TCHAR* CityMPC = TEXT("/Game/CityGen/Core/MPC_CityGen.MPC_CityGen");
	const TCHAR* RainMaterial = TEXT("/Game/CityGen/Core/Atmos/M_CgRain.M_CgRain");
	const TCHAR* WetMaterial = TEXT("/Game/CityGen/Core/Atmos/M_CgWet.M_CgWet");
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
	for (TActorIterator<ACityGenAtmos> It(const_cast<UWorld*>(World)); It; ++It)
	{
		return *It;
	}
	return nullptr;
}

void ACityGenAtmos::BeginPlay()
{
	Super::BeginPlay();
	bBegun = true;
	AtmosCollection = LoadObject<UMaterialParameterCollection>(nullptr, AtmosMPC);
	CityCollection = LoadObject<UMaterialParameterCollection>(nullptr, CityMPC);
	BeaconMaterial = LoadObject<UMaterialInterface>(nullptr, BeaconMaterialPath);
	BeamMaterial = LoadObject<UMaterialInterface>(nullptr, BeamMaterialPath);
	// (the cells streamed in before it began play: each later one registers itself)
	for (TActorIterator<ACityGenAtmosCell> It(GetWorld()); It; ++It)
	{
		if (It->HasActorBegunPlay() || It->IsActorBeginningPlay())
		{
			RegisterCell(*It);
		}
	}
	UE_LOG(LogCityGenAtmos, Display, TEXT("CityGen atmos: %s, %d schedules, %d cells with %d lights in at begin play"),
		*City, ScheduleNames.Num(), SlotOfActor.Num(), RegisteredLights);
	EnsureVolume();
	SetFog(bFog);
	SetRain(bRain);
	SetWet(bWet);
	SetMegaLights(bMegaLights);
	SetLightsOn(bLights);
}

void ACityGenAtmos::EndPlay(const EEndPlayReason::Type Reason)
{
	SetPlayLamps(true);
	ReleaseAll();
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
	const int32 N = Cell->LightInts.Num() / CityGenAtmosPack::Ints;
	if (N <= 0 || Cell->LightFloats.Num() < N * CityGenAtmosPack::Floats)
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
	MakeFixtures(Slot);
	SlotsAt.FindOrAdd(S.Key).Add(Slot);
	SlotOfActor.Add(Cell, Slot);
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
	const int32 H = FMath::Clamp(FMath::FloorToInt32(FMath::Fmod(Hour + 24.f, 24.f)), 0, 23);
	return ScheduleHours[Base + H];
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
}

void ACityGenAtmos::ApplyLight(ULocalLightComponent* C, const FCityGenAtmosLight& L, float Fade, bool bShadowed)
{
	const float K = Scale() * Fade * ScheduleAt(L.Schedule);
	C->SetWorldLocationAndRotation(L.Pos, L.Rot);
	C->SetLightColor(L.Color);
	C->SetAttenuationRadius(L.ReachCm);
	C->SetVolumetricScatteringIntensity(VolumetricScattering);
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
	if (L.Anim != 0)
	{
		const double T = WorldTime();
		if (L.Anim == 2)
		{
			C->SetWorldRotation(AnimRot(L, T));
		}
		C->SetIntensity(L.Intensity * K * AnimGain(L, T));
	}
	else
	{
		C->SetIntensity(L.Intensity * K);
	}
	if (bool(C->CastShadows) != bShadowed)
	{
		C->SetCastShadows(bShadowed);
	}
	C->SetVisibility(true);
}

void ACityGenAtmos::UpdateLive()
{
	const double T = FPlatformTime::Seconds();
	const FVector View = ViewLocation();
	const double MidCm = double(MidRangeM) * 100.0;
	const double NearCm = double(NearRangeM) * 100.0;
	const int32 Reach = FMath::CeilToInt32(MidCm / FMath::Max(1.0, double(CellM) * 100.0));
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
				const TArray<FCityGenAtmosLight>& Ls = Slots[Slot].Lights;
				for (int32 i = 0; i < Ls.Num(); ++i)
				{
					const FCityGenAtmosLight& L = Ls[i];
					// (AT2: the high tier's lights are the high pool's, below)
					if (L.bHigh || !L.bOn || ScheduleAt(L.Schedule) < 0.05f)
					{
						continue;
					}
					const double D = FVector::Dist(L.Pos, View);
					if (D > MidCm || (L.bNearOnly && D > NearCm))
					{
						continue;
					}
					Near.Add(TPair<double, int64>(D, LiveKey(Slot, i)));
				}
			}
		}
	}
	Candidates = Near.Num();
	auto ByDist = [](const TPair<double, int64>& A, const TPair<double, int64>& B)
	{
		return A.Key < B.Key || (A.Key == B.Key && A.Value < B.Value);
	};
	Near.Sort(ByDist);
	const int32 N = FMath::Min(Near.Num(), MaxLive);
	TSet<int64> Want;
	Want.Reserve(N + MaxHigh);
	for (int32 k = 0; k < N; ++k)
	{
		Want.Add(Near[k].Value);
	}
	// AT2: the high tier, a pool of its own: the nearest MaxHigh within HighRangeM, from the
	// cells' lists of their high lights
	TArray<TPair<double, int64>> High;
	const double HighCm = double(HighRangeM) * 100.0;
	if (MaxHigh > 0)
	{
		const int32 HReach = FMath::CeilToInt32(HighCm / FMath::Max(1.0, double(CellM) * 100.0));
		for (int32 dx = -HReach; dx <= HReach; ++dx)
		{
			for (int32 dy = -HReach; dy <= HReach; ++dy)
			{
				const TArray<int32>* At = SlotsAt.Find(FIntPoint(VC.X + dx, VC.Y + dy));
				if (!At)
				{
					continue;
				}
				for (int32 Slot : *At)
				{
					const FSlot& S = Slots[Slot];
					for (int32 i : S.High)
					{
						const FCityGenAtmosLight& L = S.Lights[i];
						if (!L.bOn || ScheduleAt(L.Schedule) < 0.05f)
						{
							continue;
						}
						const double D = FVector::Dist(L.Pos, View);
						if (D <= HighCm)
						{
							High.Add(TPair<double, int64>(D, LiveKey(Slot, i)));
						}
					}
				}
			}
		}
	}
	CandidatesHigh = High.Num();
	High.Sort(ByDist);
	High.SetNum(FMath::Min(High.Num(), FMath::Max(0, MaxHigh)));
	LiveHigh = High.Num();
	for (const TPair<double, int64>& H : High)
	{
		Want.Add(H.Value);
	}
	TArray<int64> Keys;
	Live.GetKeys(Keys);
	for (int64 K : Keys)
	{
		if (!Want.Contains(K))
		{
			Release(K);
		}
	}
	// the nearest that may cast shadows do, within the near range
	TSet<int64> Shadow;
	for (int32 k = 0; k < N && Shadow.Num() < MaxShadowed; ++k)
	{
		const FCityGenAtmosLight* L = LightOf(Near[k].Value);
		if (L && L->bShadow && Near[k].Key <= NearCm)
		{
			Shadow.Add(Near[k].Value);
		}
	}
	const double FarCm = N > 0 ? FMath::Min(MidCm, Near[N - 1].Key) : MidCm;
	Flickering.Reset();
	for (int32 k = 0; k < N; ++k)
	{
		const int64 Key = Near[k].Value;
		const FCityGenAtmosLight* L = LightOf(Key);
		if (!L)
		{
			continue;
		}
		// (the farthest share of the live set fades out, so a light entering it does not pop)
		const float Fade = float(FMath::Clamp((FarCm - Near[k].Key) / (FadeShare * FarCm), 0.0, 1.0));
		TObjectPtr<ULocalLightComponent>* Have = Live.Find(Key);
		ULocalLightComponent* C = Have ? Have->Get() : nullptr;
		if (!C)
		{
			C = Take(L->Shape);
			Live.Add(Key, C);
		}
		const bool bShadow = Shadow.Contains(Key);
		ApplyLight(C, *L, Fade, bShadow);
		if (bShadow) { Shadowed.Add(Key); } else { Shadowed.Remove(Key); }
		if (L->Flicker > 0.f || L->Anim != 0)
		{
			Flickering.Add(Key);
		}
	}
	// the high pool's: no shadows, the farthest fifth of its range fading
	for (const TPair<double, int64>& H : High)
	{
		const FCityGenAtmosLight* L = LightOf(H.Value);
		if (!L)
		{
			continue;
		}
		const float Fade = float(FMath::Clamp((HighCm - H.Key) / (FadeShare * HighCm), 0.0, 1.0));
		TObjectPtr<ULocalLightComponent>* Have = Live.Find(H.Value);
		ULocalLightComponent* C = Have ? Have->Get() : nullptr;
		if (!C)
		{
			C = Take(L->Shape);
			Live.Add(H.Value, C);
		}
		ApplyLight(C, *L, Fade, false);
		Shadowed.Remove(H.Value);
		if (L->Flicker > 0.f || L->Anim != 0)
		{
			Flickering.Add(H.Value);
		}
	}
	UpdateMs = (FPlatformTime::Seconds() - T) * 1000.0;
	UpdateMsMax = FMath::Max(UpdateMsMax, UpdateMs);
}

void ACityGenAtmos::UpdateFlicker(double Now)
{
	// a flickering light drops for a moment now and then: a hash of its seed and the 1/12 s
	// step (no state, the same at any frame rate)
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
		float Drop = 0.f;
		if (L->Flicker > 0.f)
		{
			const float R = float(Hash(L->Seed, Step) & 0xffff) / 65535.f;
			Drop = R < 0.18f ? L->Flicker : (R < 0.3f ? 0.3f * L->Flicker : 0.f);
		}
		// (AT2: a blink from the world's time, as the beacon's material blinks; a sweep turns
		// the light; the live set's fade is left to its 0.2 s update)
		if (L->Anim == 2)
		{
			(*C)->SetWorldRotation(AnimRot(*L, T));
		}
		(*C)->SetIntensity(L->Intensity * Scale() * ScheduleAt(L->Schedule) * (1.f - Drop) *
			AnimGain(*L, T));
	}
}

void ACityGenAtmos::SetPlayLamps(bool bOn) const
{
	// (while the plan's lights are on, the play features keep only their light pools under the
	// lamps past the live range: AT0's far tier, `bFarPools`)
	// (AT1: the play features keep only their light pools; with the plan's lights on, the
	// pools stand past the live range, AT0's far tier, `bFarPools`; with them off, from the
	// view out, as before atmosgen)
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("CityGen.PlayLamps")))
	{
		V->Set(bOn ? 1 : (bFarPools ? 2 : 0), ECVF_SetByCode);
	}
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("CityGen.PlayPoolsFromM")))
	{
		V->Set(MidRangeM, ECVF_SetByCode);
	}
}

void ACityGenAtmos::SetLightsOn(bool bOn)
{
	bLights = bOn;
	if (!bOn)
	{
		ReleaseAll();
		bShowing = false;
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
	PushParameters();
	LiveAt = -1.0;
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
				B->SetCustomPrimitiveDataFloat(3, BeamBase * BeamGlow);
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
	for (TActorIterator<AExponentialHeightFog> It(GetWorld()); It; ++It)
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
	if (!bOn)
	{
		return;
	}
	F->SetFogDensity(FogDensity);
	F->SetFogHeightFalloff(FogFalloff);
	// (a dark night haze: the inscattering is the sky's, very low; the lights' own color
	// comes from the volumetric fog they light)
	F->SetFogInscatteringColor(FLinearColor(0.004f, 0.005f, 0.008f));
	F->SetVolumetricFog(bVolumetricFog);
	F->SetVolumetricFogScatteringDistribution(0.6f);
	F->SetVolumetricFogExtinctionScale(FogVolumetric);
	F->SetVolumetricFogAlbedo(FogAlbedo.ToFColor(true));
	F->SetVolumetricFogDistance(20000.f);
	PushParameters();
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
	Rain->SetMaterial(0, Mat);
	Rain->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Rain->SetCastShadow(false);
	Rain->SetMobility(EComponentMobility::Movable);
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
	}
	if (Rain)
	{
		Rain->SetVisibility(bOn);
	}
	PushParameters();
}

void ACityGenAtmos::EnsureWet()
{
	if (Wet)
	{
		return;
	}
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, WetMaterial);
	if (!Mat)
	{
		UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: no wet streets (%s missing: run the atmos assets)"),
			WetMaterial);
		return;
	}
	Wet = NewObject<UDecalComponent>(this);
	Wet->SetupAttachment(RootComponent);
	Wet->SetUsingAbsoluteLocation(true);
	Wet->SetUsingAbsoluteRotation(true);
	Wet->SetUsingAbsoluteScale(true);
	// (a decal projects along its +X: down; 1.4 m deep round the street level, from 0.3 m
	// under it to 1.1 m over it: roads, sidewalks and curbs, and a splash band on the walls)
	Wet->SetWorldRotation(FRotator(-90.f, 0.f, 0.f));
	Wet->DecalSize = FVector(70.f, WetHalfCm, WetHalfCm);
	Wet->SetDecalMaterial(Mat);
	Wet->SetFadeScreenSize(0.f);
	Wet->SetSortOrder(-10);
	Wet->RegisterComponent();
}

void ACityGenAtmos::SetWet(bool bOn)
{
	bWet = bOn;
	if (bOn)
	{
		EnsureWet();
	}
	if (Wet)
	{
		Wet->SetVisibility(bOn);
	}
	WetAt = FVector(1e12);
	PushParameters();
}

void ACityGenAtmos::PushParameters()
{
	if (AtmosCollection)
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, TEXT("Rain"), bRain ? RainRate : 0.f);
		UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, TEXT("Wetness"), bWet ? 1.f : 0.f);
		UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, TEXT("FogDensity"), bFog ? FogDensity : 0.f);
		UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, TEXT("WindMS"), WindMS);
	}
	if (CityCollection && bLights && HasPlan())
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, CityCollection, TEXT("Hour"), Hour);
	}
}

// -- the tick --

void ACityGenAtmos::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const double Now = FPlatformTime::Seconds();
	FRotator ViewRot;
	const FVector View = ViewLocation(&ViewRot);
	// the plan's lights show by night (MPC_CityGen's Night, which the play features' day and
	// night switch sets until AT3 drives the time): by day they cost nothing
	const bool bWant = bLights && HasPlan() &&
		(!CityCollection || UKismetMaterialLibrary::GetScalarParameterValue(this, CityCollection, TEXT("Night")) > 0.5f);
	if (bWant != bShowing)
	{
		bShowing = bWant;
		if (!bWant)
		{
			ReleaseAll();
		}
		SetPlayLamps(!bWant);
		LiveAt = -1.0;
	}
	if ((bShowing && bFixtures) != bFixturesShown)
	{
		ShowFixtures(bShowing && bFixtures);
	}
	if (bShowing)
	{
		if (LiveAt < 0.0 || Now - LiveAt > LiveEvery)
		{
			LiveAt = Now;
			UpdateLive();
		}
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
	if (bWet && Wet)
	{
		const FVector Snap(FMath::GridSnap(View.X, WetSnapCm), FMath::GridSnap(View.Y, WetSnapCm), 40.0);
		if (!Snap.Equals(WetAt, 1.0))
		{
			WetAt = Snap;
			Wet->SetWorldLocation(Snap);
		}
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
		"\"fixtures\": %s}"),
		HasPlan() ? TEXT("true") : TEXT("false"), *City, *PlanHash, RegisteredLights, SlotOfActor.Num(),
		Registrations, bLights ? TEXT("true") : TEXT("false"), Live.Num(), Spots, Points, Rects, *Kinds,
		Shadowed.Num(), Candidates, MaxLive, MidRangeM, MaxShadowed, UpdateMs, UpdateMsMax, Scale(), Hour,
		bFog ? TEXT("true") : TEXT("false"), bRain ? TEXT("true") : TEXT("false"),
		bWet ? TEXT("true") : TEXT("false"), bMegaLights ? TEXT("true") : TEXT("false"),
		RT ? RT->GetInt() : -1, AllLights.Num(), bShowing ? TEXT("true") : TEXT("false"), LiveHigh, MaxHigh,
		HighRangeM, CandidatesHigh, Flickering.Num(), BeaconCount, BeamCount,
		bFixturesShown ? TEXT("true") : TEXT("false"));
}
