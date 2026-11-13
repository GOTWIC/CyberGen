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
	SetFog(bFog);
	SetAir(bAir);
	SetRain(bRain);
	SetWet(bWet);
	SetMegaLights(bMegaLights);
	SetLightsOn(bLights);
}

void ACityGenAtmos::EndPlay(const EEndPlayReason::Type Reason)
{
	FinishSight();
	SetPlayLamps(true);
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
	if (N <= 0 && NV <= 0 && NE <= 0)
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

void ACityGenAtmos::SetLevel(ULocalLightComponent* C, int64 Key, const FCityGenAtmosLight& L, double T, uint32 Step) const
{
	// a light's intensity now: its own, the exposure's scale, its schedule, its blink, its
	// flicker's drop (a hash of its seed and the 1/12 s step: no state, the same at any frame
	// rate), and its fades by distance and in time
	float Drop = 0.f;
	if (L.Flicker > 0.f)
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
					const double D2 = FVector::DistSquared(L.Pos, View);
					if (D2 > Range2 || (L.bNearOnly && D2 > NearCm * NearCm))
					{
						continue;
					}
					FCityGenSightJob J;
					J.Key = LiveKey(Slot, i);
					J.A = FVector3f(L.Pos);
					const FVector Dir = L.Rot.Vector();
					const double Ground = Sight->GroundAt(L.Pos);
					FVector B = L.Pos;
					if (L.Shape == 0 && Dir.Z < -0.3)
					{
						// (a spot aimed down: its pool on the ground, at most 0.8 of its reach out)
						const double Along = FMath::Min((L.Pos.Z - Ground - 30.0) / -Dir.Z, 0.8 * L.ReachCm);
						B = L.Pos + Dir * FMath::Max(0.0, Along);
					}
					else if (L.Shape == 1)
					{
						B = L.Pos - FVector(0.0, 0.0, FMath::Clamp(L.Pos.Z - Ground - 30.0, 0.0, 0.5 * L.ReachCm));
					}
					else
					{
						// (a face, an uplight, a flood: a patch along its aim)
						B = L.Pos + Dir * FMath::Min(0.5 * L.ReachCm, L.Shape == 2 ? 600.0 : 1500.0);
					}
					J.B = FVector3f(B);
					J.bB = FVector::DistSquared(B, L.Pos) > 200.0 * 200.0;
					Jobs.Add(J);
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
	if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("CityGen.PlayLamps")))
	{
		V->Set(bOn ? 1 : (bFarPools ? 2 : 0), ECVF_SetByCode);
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
		const float K = ScheduleAt(V.Schedule) * VolumeGain * Fade;
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

void ACityGenAtmos::ShowPlumes(bool bOn)
{
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
		UKismetMaterialLibrary::SetScalarParameterValue(this, AtmosCollection, TEXT("SteamGain"), SteamGain);
	}
	if (CityCollection && ((bLights && HasPlan()) || (bSky && HasSky())))
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
		"\"fixtures\": %s, \"sky\": %s, \"night_now\": %.3f, \"ev100\": %.2f, \"sun_elev\": %.2f, "
		"\"moon_elev\": %.2f, \"moon_lux\": %.4f, \"time_speed\": %.3f, \"dome\": %s, \"deck_m\": %.0f, "
		"\"cover\": %.2f, \"glow\": %s, \"day_hour\": %.2f, \"dusk_hour\": %.2f, \"night_hour\": %.2f, "
		"\"air\": %s, \"volumes\": %d, \"volumes_live\": %d, \"candidates_volumes\": %d, \"emitters\": %d, "
		"\"plume_cards\": %d, \"plumes_shown\": %s, \"fog_share\": %.3f, \"fog_view_m\": %.0f, \"tuned\": %s, "
		"\"cvars\": %d, \"sight\": %s, \"sight_wanted\": %s, \"sight_raster\": %s, \"sight_m\": %.0f, "
		"\"sight_max\": %d, \"sight_seen\": %d, \"sight_picked\": %d, \"sight_tested\": %d, \"sight_rays\": %d, "
		"\"sight_ms\": %.3f, \"sight_ms_max\": %.3f, \"sight_launch_ms\": %.3f, \"sight_sweeps\": %d, "
		"\"walker\": %s, \"fading\": %d, \"fade_s\": %.2f, \"fixture_cells\": %d}"),
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
		IsWalker() ? TEXT("true") : TEXT("false"), FadingNow, FadeS, FixtureCells());
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
	EVNow = SceneEV100 + (DayEV100 - SceneEV100) * CurveAt(CurveEV, E);
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
		L->SetIntensity(bSunLight ? SunLux * SunWeight : MoonLux);
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

bool ACityGenAtmos::SetNamedHour(const FString& Name)
{
	const FString N = Name.ToLower();
	if (N == TEXT("day")) { SetHour(DayHour); }
	else if (N == TEXT("dusk")) { SetHour(DuskHour); }
	else if (N == TEXT("night")) { SetHour(NightHour); }
	else { return false; }
	return true;
}
