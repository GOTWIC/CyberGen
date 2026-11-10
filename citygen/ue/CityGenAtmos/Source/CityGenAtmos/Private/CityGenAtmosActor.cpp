#include "CityGenAtmosActor.h"

#include "Camera/PlayerCameraManager.h"
#include "Components/DecalComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SpotLightComponent.h"
#include "Dom/JsonObject.h"
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
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogCityGenAtmos, Log, All);

namespace
{
	constexpr double LiveEvery = 0.2;        // s between choosing the live set
	constexpr double CellCm = 6400.0;        // the spatial index's cells (64 m)
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

	FVector Cm(const TArray<TSharedPtr<FJsonValue>>& P)
	{
		return FVector(P[0]->AsNumber() * 100.0, -P[1]->AsNumber() * 100.0, P[2]->AsNumber() * 100.0);
	}

	FIntPoint CellOf(const FVector& P)
	{
		return FIntPoint(FMath::FloorToInt32(P.X / CellCm), FMath::FloorToInt32(P.Y / CellCm));
	}

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
	if (!bPlanLoaded && !PlanDir.IsEmpty())
	{
		LoadPlan(PlanDir);
	}
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
	Super::EndPlay(Reason);
}

// -- the plan --

bool ACityGenAtmos::LoadPlan(const FString& Dir)
{
	const double T = FPlatformTime::Seconds();
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *FPaths::Combine(Dir, TEXT("atmos_plan.json"))))
	{
		UE_LOG(LogCityGenAtmos, Error, TEXT("CityGen atmos: no atmos_plan.json in %s"), *Dir);
		return false;
	}
	TSharedPtr<FJsonObject> J;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), J) || !J.IsValid())
	{
		UE_LOG(LogCityGenAtmos, Error, TEXT("CityGen atmos: atmos_plan.json is not JSON"));
		return false;
	}
	ReleaseAll();
	Lights.Reset();
	Cells.Reset();
	Kinds.Reset();
	Schedules.Reset();
	ScheduleHours.Reset();
	PlanDir = Dir;
	PlanCity = J->GetStringField(TEXT("city"));
	double D = 0.0;
	if (J->TryGetNumberField(TEXT("night_ev100"), D)) { PlanEV100 = float(D); }
	if (J->TryGetNumberField(TEXT("hour"), D)) { Hour = float(D); }
	const TSharedPtr<FJsonObject>* W = nullptr;
	if (J->TryGetObjectField(TEXT("weather_state"), W))
	{
		if ((*W)->TryGetNumberField(TEXT("fog_density"), D)) { FogDensity = float(D); }
		if ((*W)->TryGetNumberField(TEXT("fog_falloff"), D)) { FogFalloff = float(D); }
		if ((*W)->TryGetNumberField(TEXT("volumetric"), D)) { FogVolumetric = float(D); }
		if ((*W)->TryGetNumberField(TEXT("rain"), D)) { RainRate = float(D); }
		if ((*W)->TryGetNumberField(TEXT("wind_m_s"), D)) { WindMS = float(D); }
		FString A;
		if ((*W)->TryGetStringField(TEXT("fog_albedo"), A))
		{
			FogAlbedo = FLinearColor(FColor::FromHex(A));
		}
	}
	const TSharedPtr<FJsonObject>* Tiers = nullptr;
	if (J->TryGetObjectField(TEXT("tiers"), Tiers))
	{
		if ((*Tiers)->TryGetNumberField(TEXT("mid_m"), D)) { MidRangeM = float(D); }
		if ((*Tiers)->TryGetNumberField(TEXT("near_m"), D)) { NearRangeM = float(D); }
		int32 N = 0;
		if ((*Tiers)->TryGetNumberField(TEXT("mid_max"), N)) { MaxLive = N; }
		if ((*Tiers)->TryGetNumberField(TEXT("near_max"), N)) { MaxShadowed = N; }
	}
	const TSharedPtr<FJsonObject>* Sch = nullptr;
	if (J->TryGetObjectField(TEXT("schedules"), Sch))
	{
		for (const auto& KV : (*Sch)->Values)
		{
			Schedules.Add(FString(*KV.Key));   // (5.8: the keys are shared strings)
			TArray<float> H;
			for (const TSharedPtr<FJsonValue>& V : KV.Value->AsArray()) { H.Add(float(V->AsNumber())); }
			ScheduleHours.Add(H);
		}
	}
	int32 Tiles = 0;
	for (const TSharedPtr<FJsonValue>& TV : J->GetArrayField(TEXT("tiles")))
	{
		const FString File = TV->AsObject()->GetStringField(TEXT("file"));
		FString TT;
		TSharedPtr<FJsonObject> TJ;
		if (!FFileHelper::LoadFileToString(TT, *FPaths::Combine(Dir, File)) ||
			!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(TT), TJ) || !TJ.IsValid())
		{
			UE_LOG(LogCityGenAtmos, Warning, TEXT("CityGen atmos: cannot read %s"), *File);
			continue;
		}
		++Tiles;
		for (const TSharedPtr<FJsonValue>& LV : TJ->GetArrayField(TEXT("lights")))
		{
			const TSharedPtr<FJsonObject>& O = LV->AsObject();
			FCityGenAtmosLight L;
			L.Pos = Cm(O->GetArrayField(TEXT("pos")));
			const TArray<TSharedPtr<FJsonValue>>& Aim = O->GetArrayField(TEXT("aim"));
			// citygen's yaw turns counterclockwise from east, Unreal's clockwise (Y south)
			L.Rot = FRotator(Aim[1]->AsNumber(), -Aim[0]->AsNumber(), 0.0);
			const FString Shape = O->GetStringField(TEXT("shape"));
			L.Shape = Shape == TEXT("spot") ? 0 : (Shape == TEXT("point") ? 1 : 2);
			L.Candela = float(O->GetNumberField(TEXT("cd")));
			const TArray<TSharedPtr<FJsonValue>>& C = O->GetArrayField(TEXT("color"));
			L.Color = FLinearColor(float(C[0]->AsNumber()), float(C[1]->AsNumber()), float(C[2]->AsNumber()));
			L.ReachCm = float(O->GetNumberField(TEXT("reach_m")) * 100.0);
			const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
			if (O->TryGetArrayField(TEXT("size"), Arr) && Arr->Num() == 2)
			{
				L.Size = FVector2f(float((*Arr)[0]->AsNumber() * 100.0), float((*Arr)[1]->AsNumber() * 100.0));
				const double Area = FMath::Max(0.01, (*Arr)[0]->AsNumber() * (*Arr)[1]->AsNumber());
				L.Nits = float(L.Candela / Area);
			}
			if (O->TryGetArrayField(TEXT("cone"), Arr) && Arr->Num() == 2)
			{
				L.Inner = float((*Arr)[0]->AsNumber());
				L.Outer = float((*Arr)[1]->AsNumber());
			}
			if (O->TryGetNumberField(TEXT("barn_deg"), D)) { L.Barn = float(D); }
			if (O->TryGetNumberField(TEXT("source_m"), D)) { L.SourceCm = float(D * 100.0); }
			O->TryGetBoolField(TEXT("shadow"), L.bShadow);
			O->TryGetBoolField(TEXT("on"), L.bOn);
			L.bNearOnly = O->GetStringField(TEXT("tier")) == TEXT("near");
			L.Flicker = float(O->GetNumberField(TEXT("flicker")));
			const FString Kind = O->GetStringField(TEXT("kind"));
			L.Kind = uint8(Kinds.AddUnique(Kind));
			const int32 S = Schedules.IndexOfByKey(O->GetStringField(TEXT("schedule")));
			L.Schedule = uint8(FMath::Max(0, S));
			L.Seed = GetTypeHash(O->GetStringField(TEXT("id")));
			const int32 Index = Lights.Add(L);
			Cells.FindOrAdd(CellOf(L.Pos)).Add(Index);
		}
	}
	bPlanLoaded = Lights.Num() > 0;
	LoadSeconds = FPlatformTime::Seconds() - T;
	LiveAt = -1.0;
	UE_LOG(LogCityGenAtmos, Display, TEXT("CityGen atmos: %s, %d lights in %d tiles, %d cells, loaded in %.2f s"),
		*PlanCity, Lights.Num(), Tiles, Cells.Num(), LoadSeconds);
	return bPlanLoaded;
}

float ACityGenAtmos::ScheduleAt(uint8 Schedule) const
{
	if (!ScheduleHours.IsValidIndex(Schedule) || ScheduleHours[Schedule].Num() != 24)
	{
		return 1.f;
	}
	const int32 H = FMath::Clamp(FMath::FloorToInt32(FMath::Fmod(Hour + 24.f, 24.f)), 0, 23);
	return ScheduleHours[Schedule][H];
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

void ACityGenAtmos::Release(int32 LightIndex)
{
	TObjectPtr<ULocalLightComponent> C;
	if (!Live.RemoveAndCopyValue(LightIndex, C) || !C)
	{
		return;
	}
	C->SetVisibility(false);
	if (Shadowed.Remove(LightIndex) > 0)
	{
		C->SetCastShadows(false);
	}
	const uint8 Shape = Lights[LightIndex].Shape;
	(Shape == 0 ? FreeSpot : (Shape == 1 ? FreePoint : FreeRect)).Add(C);
}

void ACityGenAtmos::ReleaseAll()
{
	TArray<int32> Keys;
	Live.GetKeys(Keys);
	for (int32 K : Keys)
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
	if (L.Shape == 2)
	{
		URectLightComponent* R = CastChecked<URectLightComponent>(C);
		R->SetSourceWidth(L.Size.X);
		R->SetSourceHeight(L.Size.Y);
		R->SetBarnDoorAngle(L.Barn);
		R->SetIntensity(L.Nits * K);
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
		C->SetIntensity(L.Candela * K);
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
	const int32 Reach = FMath::CeilToInt32(MidCm / CellCm);
	const FIntPoint VC = CellOf(View);
	TArray<TPair<double, int32>> Near;
	for (int32 dx = -Reach; dx <= Reach; ++dx)
	{
		for (int32 dy = -Reach; dy <= Reach; ++dy)
		{
			const TArray<int32>* In = Cells.Find(FIntPoint(VC.X + dx, VC.Y + dy));
			if (!In)
			{
				continue;
			}
			for (int32 i : *In)
			{
				const FCityGenAtmosLight& L = Lights[i];
				if (!L.bOn || ScheduleAt(L.Schedule) < 0.05f)
				{
					continue;
				}
				const double D = FVector::Dist(L.Pos, View);
				if (D > MidCm || (L.bNearOnly && D > NearCm))
				{
					continue;
				}
				Near.Add(TPair<double, int32>(D, i));
			}
		}
	}
	Candidates = Near.Num();
	Near.Sort([](const TPair<double, int32>& A, const TPair<double, int32>& B)
	{
		return A.Key < B.Key || (A.Key == B.Key && A.Value < B.Value);
	});
	const int32 N = FMath::Min(Near.Num(), MaxLive);
	TSet<int32> Want;
	Want.Reserve(N);
	for (int32 k = 0; k < N; ++k)
	{
		Want.Add(Near[k].Value);
	}
	TArray<int32> Keys;
	Live.GetKeys(Keys);
	for (int32 K : Keys)
	{
		if (!Want.Contains(K))
		{
			Release(K);
		}
	}
	// the nearest that may cast shadows do, within the near range
	TSet<int32> Shadow;
	for (int32 k = 0; k < N && Shadow.Num() < MaxShadowed; ++k)
	{
		if (Lights[Near[k].Value].bShadow && Near[k].Key <= NearCm)
		{
			Shadow.Add(Near[k].Value);
		}
	}
	const double FarCm = N > 0 ? FMath::Min(MidCm, Near[N - 1].Key) : MidCm;
	Flickering.Reset();
	for (int32 k = 0; k < N; ++k)
	{
		const int32 i = Near[k].Value;
		const FCityGenAtmosLight& L = Lights[i];
		// (the farthest share of the live set fades out, so a light entering it does not pop)
		const float Fade = float(FMath::Clamp((FarCm - Near[k].Key) / (FadeShare * FarCm), 0.0, 1.0));
		TObjectPtr<ULocalLightComponent>* Have = Live.Find(i);
		ULocalLightComponent* C = Have ? Have->Get() : nullptr;
		if (!C)
		{
			C = Take(L.Shape);
			Live.Add(i, C);
		}
		const bool bShadow = Shadow.Contains(i);
		ApplyLight(C, L, Fade, bShadow);
		if (bShadow) { Shadowed.Add(i); } else { Shadowed.Remove(i); }
		if (L.Flicker > 0.f)
		{
			Flickering.Add(i);
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
	for (int32 i : Flickering)
	{
		TObjectPtr<ULocalLightComponent>* C = Live.Find(i);
		if (!C || !*C)
		{
			continue;
		}
		const FCityGenAtmosLight& L = Lights[i];
		const float R = float(Hash(L.Seed, Step) & 0xffff) / 65535.f;
		const float Drop = R < 0.18f ? L.Flicker : (R < 0.3f ? 0.3f * L.Flicker : 0.f);
		const float Base = L.Shape == 2 ? L.Nits : L.Candela;
		(*C)->SetIntensity(Base * Scale() * ScheduleAt(L.Schedule) * (1.f - Drop));
	}
}

void ACityGenAtmos::SetPlayLamps(bool bOn) const
{
	// (while the plan's lights are on, the play features keep only their light pools under the
	// lamps past the live range: AT0's far tier, `bFarPools`)
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
	}
	SetPlayLamps(!bOn || !bPlanLoaded);
	LiveAt = -1.0;
}

void ACityGenAtmos::SetFarPools(bool bOn)
{
	bFarPools = bOn;
	if (bLights)
	{
		SetPlayLamps(!bPlanLoaded);
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
		SetPlayLamps(!bPlanLoaded);
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
	if (CityCollection && bLights && bPlanLoaded)
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
	if (bLights && bPlanLoaded)
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
	for (const auto& KV : Live)
	{
		const uint8 S = Lights[KV.Key].Shape;
		Spots += S == 0 ? 1 : 0;
		Points += S == 1 ? 1 : 0;
		Rects += S == 2 ? 1 : 0;
	}
	const IConsoleVariable* RT = IConsoleManager::Get().FindConsoleVariable(TEXT("r.RayTracing"));
	return FString::Printf(TEXT("{\"plan\": %s, \"city\": \"%s\", \"lights\": %d, \"cells\": %d, "
		"\"load_s\": %.2f, \"on\": %s, \"live\": %d, \"spot\": %d, \"point\": %d, \"rect\": %d, "
		"\"shadowed\": %d, \"candidates\": %d, \"max_live\": %d, \"mid_m\": %.0f, \"max_shadowed\": %d, "
		"\"update_ms\": %.3f, \"update_ms_max\": %.3f, \"scale\": %.5f, \"hour\": %.2f, \"fog\": %s, "
		"\"rain\": %s, \"wet\": %s, \"megalights\": %s, \"ray_tracing\": %d, \"components\": %d}"),
		bPlanLoaded ? TEXT("true") : TEXT("false"), *PlanCity, Lights.Num(), Cells.Num(), LoadSeconds,
		bLights ? TEXT("true") : TEXT("false"), Live.Num(), Spots, Points, Rects, Shadowed.Num(),
		Candidates, MaxLive, MidRangeM, MaxShadowed, UpdateMs, UpdateMsMax, Scale(), Hour,
		bFog ? TEXT("true") : TEXT("false"), bRain ? TEXT("true") : TEXT("false"),
		bWet ? TEXT("true") : TEXT("false"), bMegaLights ? TEXT("true") : TEXT("false"),
		RT ? RT->GetInt() : -1, AllLights.Num());
}
