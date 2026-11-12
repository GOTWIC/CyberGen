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
	AtmosCollection = LoadObject<UMaterialParameterCollection>(nullptr, AtmosMPC);
	CityCollection = LoadObject<UMaterialParameterCollection>(nullptr, CityMPC);
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
		const uint32 Flags = uint32(i[0]);
		L.Shape = uint8(Flags & 3u);
		L.bShadow = (Flags & 4u) != 0;
		L.bNearOnly = (Flags & 8u) != 0;
		L.bOn = (Flags & 16u) != 0;
		L.bNoSpecular = (Flags & 32u) != 0;
		L.Schedule = uint8((Flags >> 8) & 0xffu);
		L.Kind = uint8((Flags >> 16) & 0xffu);
		L.Seed = uint32(i[1]);
		S.Lights.Add(L);
	}
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
	S.Lights.Reset();
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
	C->SetIntensity(L.Intensity * K);
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
					if (!L.bOn || ScheduleAt(L.Schedule) < 0.05f)
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
	Near.Sort([](const TPair<double, int64>& A, const TPair<double, int64>& B)
	{
		return A.Key < B.Key || (A.Key == B.Key && A.Value < B.Value);
	});
	const int32 N = FMath::Min(Near.Num(), MaxLive);
	TSet<int64> Want;
	Want.Reserve(N);
	for (int32 k = 0; k < N; ++k)
	{
		Want.Add(Near[k].Value);
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
		if (L->Flicker > 0.f)
		{
			Flickering.Add(Key);
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
	for (int64 Key : Flickering)
	{
		TObjectPtr<ULocalLightComponent>* C = Live.Find(Key);
		const FCityGenAtmosLight* L = LightOf(Key);
		if (!C || !*C || !L)
		{
			continue;
		}
		const float R = float(Hash(L->Seed, Step) & 0xffff) / 65535.f;
		const float Drop = R < 0.18f ? L->Flicker : (R < 0.3f ? 0.3f * L->Flicker : 0.f);
		(*C)->SetIntensity(L->Intensity * Scale() * ScheduleAt(L->Schedule) * (1.f - Drop));
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
	if (bShowing)
	{
		if (LiveAt < 0.0 || Now - LiveAt > LiveEvery)
		{
			LiveAt = Now;
			UpdateLive();
		}
		UpdateFlicker(Now);
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
		"\"ray_tracing\": %d, \"components\": %d, \"showing\": %s}"),
		HasPlan() ? TEXT("true") : TEXT("false"), *City, *PlanHash, RegisteredLights, SlotOfActor.Num(),
		Registrations, bLights ? TEXT("true") : TEXT("false"), Live.Num(), Spots, Points, Rects, *Kinds,
		Shadowed.Num(), Candidates, MaxLive, MidRangeM, MaxShadowed, UpdateMs, UpdateMsMax, Scale(), Hour,
		bFog ? TEXT("true") : TEXT("false"), bRain ? TEXT("true") : TEXT("false"),
		bWet ? TEXT("true") : TEXT("false"), bMegaLights ? TEXT("true") : TEXT("false"),
		RT ? RT->GetInt() : -1, AllLights.Num(), bShowing ? TEXT("true") : TEXT("false"));
}
