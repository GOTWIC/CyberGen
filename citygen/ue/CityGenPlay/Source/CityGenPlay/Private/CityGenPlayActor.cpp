#include "CityGenPlayActor.h"

#include "Camera/PlayerCameraManager.h"
#include "CityGenFreeCam.h"
#include "Components/CapsuleComponent.h"
#include "Components/DecalComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialParameterCollection.h"
#include "SCityGenOverlay.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

DEFINE_LOG_CATEGORY_STATIC(LogCityGenPlay, Log, All);

namespace
{
	constexpr double LampEvery = 0.2;         // s between choosing the lamps that get lights
	constexpr double StreamWaitMax = 90.0;    // s a teleported player is held at most
	constexpr float FlyClearance = 3000.f;    // cm over the walkway a flying teleport keeps
	const FName SunKey(TEXT("cg.key=lighting.sun"));
	const FName SkyKey(TEXT("cg.key=lighting.sky"));
}

ACityGenPlay::ACityGenPlay()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	// an AInfo is hidden in the game, and a hidden actor's components draw nothing: the
	// lamps' spot lights, light pools and sign washes are its components (run-through 2:
	// Delta's streets stayed as dark with the lamps 20 times brighter)
	SetHidden(false);
#if WITH_EDITORONLY_DATA
	bIsSpatiallyLoaded = false;              // World Partition: always loaded
#endif
}

ACityGenPlay* ACityGenPlay::Find(const UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<ACityGenPlay> It(const_cast<UWorld*>(World)); It; ++It)
	{
		if (It->HasActorBegunPlay())
		{
			return *It;
		}
	}
	return nullptr;
}

// -- setup --

void ACityGenPlay::BeginPlay()
{
	Super::BeginPlay();
	Setup();
}

void ACityGenPlay::Setup()
{
	UWorld* World = GetWorld();
	if (bReady || !World || !World->IsGameWorld())
	{
		return;
	}
	PC = World->GetFirstPlayerController();
	if (!PC || !PC->IsLocalController())
	{
		return;                                 // (Tick tries again once the player is in)
	}
	bReady = true;
	BindKeys();
	Overlay = SNew(SCityGenOverlay).Play(this);
	if (UGameViewportClient* Viewport = World->GetGameViewport())
	{
		Viewport->AddViewportWidgetContent(Overlay.ToSharedRef(), 20);
	}
	// AG15: a spot light under each of the nearest lamp heads, pointing down (a spot shines
	// along its +X: pitch -90), the nearest few with shadows; light-pool decals under the
	// lamps past them (a decal projects along its +X too)
	for (int32 i = 0; i < LampLights; ++i)
	{
		USpotLightComponent* L = NewObject<USpotLightComponent>(this);
		L->SetMobility(EComponentMobility::Movable);
		L->SetupAttachment(RootComponent);
		L->SetUsingAbsoluteLocation(true);
		L->SetUsingAbsoluteRotation(true);
		L->SetWorldRotation(FRotator(-90.f, 0.f, 0.f));
		L->SetIntensityUnits(ELightUnits::Candelas);
		L->SetAttenuationRadius(LampRadiusM * 100.f);
		L->SetInnerConeAngle(LampInnerConeDeg);
		L->SetOuterConeAngle(LampOuterConeDeg);
		L->SetSourceRadius(12.f);
		L->SetCastShadows(i < ShadowedLamps);
		L->SetLightColor(FLinearColor(1.0f, 0.74f, 0.46f));
		L->SetVisibility(false);
		L->RegisterComponent();
		Lamps.Add(L);
	}
	for (int32 i = 0; i < WashLights && i < WashPoints.Num(); ++i)
	{
		UPointLightComponent* W = NewObject<UPointLightComponent>(this);
		W->SetMobility(EComponentMobility::Movable);
		W->SetupAttachment(RootComponent);
		W->SetUsingAbsoluteLocation(true);
		W->SetIntensityUnits(ELightUnits::Candelas);
		W->SetAttenuationRadius(WashRadiusM * 100.f);
		W->SetSourceRadius(150.f);
		W->SetCastShadows(false);
		W->SetVisibility(false);
		W->RegisterComponent();
		Washes.Add(W);
	}
	if (LightPoolMaterial)
	{
		for (int32 i = 0; i < LampPools; ++i)
		{
			UDecalComponent* D = NewObject<UDecalComponent>(this);
			D->SetupAttachment(RootComponent);
			D->SetUsingAbsoluteLocation(true);
			D->SetUsingAbsoluteRotation(true);
			D->SetUsingAbsoluteScale(true);
			D->SetWorldRotation(FRotator(-90.f, 0.f, 0.f));
			D->SetDecalMaterial(LightPoolMaterial);
			// (centered 4.5 m under the lamp head, 7 m deep: it reaches the ground under a
			// wall light 3 m up and under a street light 7.6 m up, however Unreal reads the
			// size, as the whole box or its half)
			D->DecalSize = FVector(700.f, PoolRadiusM * 100.f, PoolRadiusM * 100.f);
			D->SetFadeScreenSize(0.f);
			D->SetVisibility(false);
			D->RegisterComponent();
			Pools.Add(D);
		}
	}
	UE_LOG(LogCityGenPlay, Log, TEXT("CityGen play: %s, map %s, %d walkway points, %d lamps"),
		*City, MapTexture ? *MapTexture->GetName() : TEXT("none"), WalkPoints.Num(), LampPoints.Num());
	if (bStartAtNight)
	{
		SetNight(true);
	}
}

void ACityGenPlay::BindKeys()
{
	EnableInput(PC);
	if (!InputComponent)
	{
		return;
	}
	InputComponent->BindKey(EKeys::M, IE_Pressed, this, &ACityGenPlay::OnKeyMap);
	InputComponent->BindKey(EKeys::Period, IE_Pressed, this, &ACityGenPlay::OnKeyFreeCam);
	InputComponent->BindKey(EKeys::Tab, IE_Pressed, this, &ACityGenPlay::OnKeyDevMenu);
	// the wheel sets the free camera's speed (it does nothing else in the game)
	FInputKeyBinding& Up = InputComponent->BindKey(EKeys::MouseScrollUp, IE_Pressed, this,
		&ACityGenPlay::OnWheelUp);
	Up.bConsumeInput = false;
	FInputKeyBinding& Down = InputComponent->BindKey(EKeys::MouseScrollDown, IE_Pressed, this,
		&ACityGenPlay::OnWheelDown);
	Down.bConsumeInput = false;
}

void ACityGenPlay::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Overlay.IsValid())
	{
		if (UWorld* World = GetWorld())
		{
			if (UGameViewportClient* Viewport = World->GetGameViewport())
			{
				Viewport->RemoveViewportWidgetContent(Overlay.ToSharedRef());
			}
		}
		Overlay.Reset();
	}
	if (FreeCam)
	{
		FreeCam->Destroy();
		FreeCam = nullptr;
	}
	Super::EndPlay(Reason);
}

// -- the map, the menu and the mouse --

void ACityGenPlay::UpdateInputMode()
{
	if (!PC)
	{
		return;
	}
	const bool bUI = bMapOpen || bDevOpen;
	if (bUI == bUIInput)
	{
		return;
	}
	bUIInput = bUI;
	if (bUI)
	{
		FInputModeGameAndUI Mode;
		Mode.SetWidgetToFocus(Overlay);
		Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		Mode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(Mode);
		PC->SetShowMouseCursor(true);
		PC->SetIgnoreLookInput(true);
		PC->SetIgnoreMoveInput(true);
	}
	else
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->SetShowMouseCursor(false);
		PC->SetIgnoreLookInput(false);
		PC->SetIgnoreMoveInput(false);
		FSlateApplication::Get().SetAllUserFocusToGameViewport();
	}
}

void ACityGenPlay::SetMapOpen(bool bOpen)
{
	if (!bReady || bOpen == bMapOpen)
	{
		return;
	}
	bMapOpen = bOpen;
	if (bOpen && Overlay.IsValid())
	{
		Overlay->ResetMapView();
	}
	UpdateInputMode();
}

void ACityGenPlay::SetDevMenuOpen(bool bOpen)
{
	if (!bReady || bOpen == bDevOpen)
	{
		return;
	}
	bDevOpen = bOpen;
	UpdateInputMode();
}

void ACityGenPlay::Toast(const FString& Text, float Seconds)
{
	ToastText = Text;
	ToastUntil = FPlatformTime::Seconds() + Seconds;
}

FString ACityGenPlay::GetToast() const
{
	return FPlatformTime::Seconds() < ToastUntil ? ToastText : FString();
}

// -- the player's view --

FVector ACityGenPlay::ViewLocation() const
{
	if (PC && PC->PlayerCameraManager)
	{
		return PC->PlayerCameraManager->GetCameraLocation();
	}
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	return Pawn ? Pawn->GetActorLocation() : FVector::ZeroVector;
}

float ACityGenPlay::ViewYaw() const
{
	return PC ? float(PC->GetControlRotation().Yaw) : 0.f;
}

// -- the free camera --

bool ACityGenPlay::IsFreeCam() const
{
	return FreeCam != nullptr;
}

float ACityGenPlay::GetFreeCamSpeed() const
{
	return FreeCam ? FreeCam->GetSpeed() : FreeCamSpeedMS * 100.f;
}

void ACityGenPlay::Hold(APawn* Pawn, bool bHold)
{
	ACharacter* Character = Cast<ACharacter>(Pawn);
	UCharacterMovementComponent* Move = Character ? Character->GetCharacterMovement() : nullptr;
	if (!Move)
	{
		return;
	}
	if (bHold)
	{
		Move->StopMovementImmediately();
		Move->DisableMovement();
	}
	else if (Move->MovementMode == MOVE_None)
	{
		Move->SetMovementMode(MOVE_Falling);
	}
}

void ACityGenPlay::SetFreeCam(bool bOn)
{
	if (!bReady || !PC || bOn == IsFreeCam())
	{
		return;
	}
	UWorld* World = GetWorld();
	if (bOn)
	{
		SavedPawn = PC->GetPawn();
		const FVector At = ViewLocation();
		const FRotator Look = PC->GetControlRotation();
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		FreeCam = World->SpawnActor<ACityGenFreeCam>(ACityGenFreeCam::StaticClass(), At, Look, Params);
		if (!FreeCam)
		{
			return;
		}
		FreeCam->SetSpeed(FreeCamSpeedMS * 100.f);
		// the walker stays where it was, held (the city may stream out under it meanwhile)
		Hold(SavedPawn, true);
		PC->Possess(FreeCam);
		PC->SetControlRotation(Look);
		Toast(TEXT("Free camera: W A S D, E or Space up, Q or C down, wheel for speed, . to return"), 4.f);
	}
	else
	{
		APawn* Back = SavedPawn;
		ACityGenFreeCam* Cam = FreeCam;
		FreeCam = nullptr;
		SavedPawn = nullptr;
		if (Back && IsValid(Back))
		{
			PC->Possess(Back);
			// held until the city around it has streamed in again
			WaitForStreaming(Back, Back->GetActorLocation());
		}
		if (Cam)
		{
			Cam->Destroy();
		}
		Toast(TEXT("Back to the player"));
	}
}

void ACityGenPlay::OnWheel(float Factor)
{
	if (FreeCam && !bMapOpen && !bDevOpen)
	{
		const float Speed = FMath::Clamp(FreeCam->GetSpeed() * Factor, 200.f, 50000.f);
		FreeCam->SetSpeed(Speed);
		Toast(FString::Printf(TEXT("Free camera %.0f m/s"), Speed / 100.f), 1.2f);
	}
}

// -- teleporting --

int32 ACityGenPlay::NearestWalk(const FVector2D& At) const
{
	int32 Best = INDEX_NONE;
	double BestD = TNumericLimits<double>::Max();
	for (int32 i = 0; i < WalkPoints.Num(); ++i)
	{
		const double D = FVector2D::DistSquared(FVector2D(WalkPoints[i].X, WalkPoints[i].Y), At);
		if (D < BestD)
		{
			BestD = D;
			Best = i;
		}
	}
	return Best;
}

bool ACityGenPlay::TeleportPlayer(FVector Location)
{
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	if (!bReady || !Pawn)
	{
		return false;
	}
	const FVector2D At(Location.X, Location.Y);
	const int32 Walk = NearestWalk(At);
	ACharacter* Character = Cast<ACharacter>(Pawn);
	if (Character && Character->GetCharacterMovement() &&
		Character->GetCharacterMovement()->MovementMode != MOVE_Flying)
	{
		if (Walk == INDEX_NONE)
		{
			Toast(TEXT("No walkway to land on"));
			return false;
		}
		const float Half = Character->GetCapsuleComponent()
			? Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 96.f;
		const FVector Target = WalkPoints[Walk] + FVector(0.0, 0.0, Half + 20.0);
		Character->TeleportTo(Target, Character->GetActorRotation(), false, true);
		WaitForStreaming(Character, Target);
		if (FVector2D::Distance(FVector2D(Target.X, Target.Y), At) > 2000.0)
		{
			Toast(TEXT("Teleported to the nearest walkway"));
		}
	}
	else
	{
		// a flying pawn keeps its height, at least FlyClearance over the walkway there
		const double Ground = Walk == INDEX_NONE ? 0.0 : WalkPoints[Walk].Z;
		const FVector Target(At.X, At.Y, FMath::Max(Pawn->GetActorLocation().Z, Ground + FlyClearance));
		Pawn->TeleportTo(Target, Pawn->GetActorRotation(), false, true);
	}
	UE_LOG(LogCityGenPlay, Log, TEXT("CityGen play: teleported to %.0f, %.0f (citygen m)"),
		Pawn->GetActorLocation().X / 100.0, -Pawn->GetActorLocation().Y / 100.0);
	return true;
}

bool ACityGenPlay::TeleportPlayerToCitygen(float X, float Y)
{
	return TeleportPlayer(FVector(X * 100.0, -Y * 100.0, 0.0));
}

void ACityGenPlay::WaitForStreaming(APawn* Pawn, const FVector& Target)
{
	if (!Cast<ACharacter>(Pawn))
	{
		return;
	}
	Hold(Pawn, true);
	bWaiting = true;
	WaitPawn = Pawn;
	WaitTarget = Target;
	WaitStart = FPlatformTime::Seconds();
}

// -- day and night --

void ACityGenPlay::SetNight(bool bOn)
{
	UWorld* World = GetWorld();
	if (!World || !World->IsGameWorld())
	{
		return;
	}
	bNight = bOn;
	if (NightCollection)
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, NightCollection, TEXT("Night"), bOn ? 1.f : 0.f);
	}
	// the sun (the importer's, else the first one) becomes the moon: high, dim and blue
	ADirectionalLight* Sun = nullptr;
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		if (!Sun || It->Tags.Contains(SunKey))
		{
			Sun = *It;
		}
	}
	ASkyLight* Sky = nullptr;
	for (TActorIterator<ASkyLight> It(World); It; ++It)
	{
		if (!Sky || It->Tags.Contains(SkyKey))
		{
			Sky = *It;
		}
	}
	UDirectionalLightComponent* SunLight = Sun ? Cast<UDirectionalLightComponent>(Sun->GetLightComponent()) : nullptr;
	USkyLightComponent* SkyLight = Sky ? Sky->GetLightComponent() : nullptr;
	if (!bDaySaved)
	{
		if (SunLight)
		{
			DaySunRotation = Sun->GetActorRotation();
			DaySunIntensity = SunLight->Intensity;
			DaySunColor = SunLight->GetLightColor();
		}
		if (SkyLight)
		{
			DaySkyIntensity = SkyLight->Intensity;
		}
		bDaySaved = true;
	}
	if (SunLight)
	{
		Sun->SetActorRotation(bOn ? FRotator(-55.f, DaySunRotation.Yaw + 150.f, 0.f) : DaySunRotation);
		SunLight->SetIntensity(bOn ? DaySunIntensity * MoonFraction : DaySunIntensity);
		SunLight->SetLightColor(bOn ? FLinearColor(0.5f, 0.62f, 1.0f) : DaySunColor);
	}
	if (SkyLight)
	{
		SkyLight->SetIntensity(bOn ? DaySkyIntensity * 0.6f : DaySkyIntensity);
	}
	// a fixed exposure by night, or the eye adapts until the night looks like the day
	if (!NightVolume)
	{
		FActorSpawnParameters Params;
		Params.ObjectFlags |= RF_Transient;
		NightVolume = World->SpawnActor<APostProcessVolume>(Params);
		if (NightVolume)
		{
			NightVolume->bUnbound = true;
			NightVolume->Priority = 100.f;
			FPostProcessSettings& S = NightVolume->Settings;
			S.bOverride_AutoExposureMinBrightness = true;
			S.bOverride_AutoExposureMaxBrightness = true;
			S.bOverride_AutoExposureBias = true;
			S.AutoExposureBias = 0.f;
		}
	}
	if (NightVolume)
	{
		NightVolume->Settings.AutoExposureMinBrightness = NightExposureEV100;
		NightVolume->Settings.AutoExposureMaxBrightness = NightExposureEV100;
		NightVolume->bEnabled = bOn;
	}
	if (NightCollection && bOn)
	{
		UKismetMaterialLibrary::SetScalarParameterValue(this, NightCollection, TEXT("Hour"), NightHour);
	}
	LampsAt = -1.0;
	if (!bOn)
	{
		for (USpotLightComponent* L : Lamps)
		{
			L->SetVisibility(false);
		}
		for (UDecalComponent* D : Pools)
		{
			D->SetVisibility(false);
		}
		for (UPointLightComponent* W : Washes)
		{
			W->SetVisibility(false);
		}
		LampsOn = 0;
		PoolsOn = 0;
	}
	Toast(bOn ? TEXT("Night") : TEXT("Day"), 1.5f);
	UE_LOG(LogCityGenPlay, Log, TEXT("CityGen play: %s"), bOn ? TEXT("night") : TEXT("day"));
}

void ACityGenPlay::UpdateLamps()
{
	// the lamps nearest the view get the lights; the farthest of them fade, so a lamp
	// coming into the set does not pop
	const FVector View = ViewLocation();
	const int32 N = FMath::Min(Lamps.Num(), LampPoints.Num());
	TArray<TPair<double, int32>> Near;
	Near.Reserve(LampPoints.Num());
	for (int32 i = 0; i < LampPoints.Num(); ++i)
	{
		Near.Add(TPair<double, int32>(FVector::DistSquared(LampPoints[i], View), i));
	}
	// (a few thousand lamps: sorting them all five times a second costs nothing)
	Near.Sort([](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
	double Far = 1.0;
	for (int32 k = 0; k < N; ++k)
	{
		Far = FMath::Max(Far, FMath::Sqrt(Near[k].Key));
	}
	for (int32 k = 0; k < Lamps.Num(); ++k)
	{
		USpotLightComponent* L = Lamps[k];
		if (k >= N)
		{
			L->SetVisibility(false);
			continue;
		}
		const int32 i = Near[k].Value;
		const bool bWall = LampKinds.IsValidIndex(i) && LampKinds[i] == 1;
		const double D = FMath::Sqrt(Near[k].Key);
		// (the farthest quarter fades out, where the light-pool decals take over)
		const float Fade = float(FMath::Clamp((Far - D) / (0.25 * Far), 0.0, 1.0));
		L->SetWorldLocation(LampPoints[i] - FVector(0.0, 0.0, LampDropCm));
		L->SetIntensity((bWall ? WallLampCandela : StreetLampCandela) * Fade);
		L->SetAttenuationRadius(LampRadiusM * (bWall ? 60.f : 100.f));
		L->SetVisibility(Fade > 0.f);
	}
	LampsOn = N;
	// the light pools under the lamps past the lit ones (and under the fading ones)
	const int32 P0 = FMath::Max(0, N - N / 4);
	const int32 P = FMath::Min(Pools.Num(), FMath::Max(0, LampPoints.Num() - P0));
	for (int32 k = 0; k < Pools.Num(); ++k)
	{
		UDecalComponent* Dc = Pools[k];
		if (k >= P)
		{
			Dc->SetVisibility(false);
			continue;
		}
		const int32 i = Near[P0 + k].Value;
		const bool bWall = LampKinds.IsValidIndex(i) && LampKinds[i] == 1;
		Dc->SetWorldLocation(LampPoints[i] - FVector(0.0, 0.0, 450.0));
		Dc->SetWorldScale3D(FVector(1.0, bWall ? 0.6 : 1.0, bWall ? 0.6 : 1.0));
		Dc->SetVisibility(true);
	}
	PoolsOn = P;
	// the large signs nearest the view wash their facades in their color
	if (Washes.Num() > 0)
	{
		TArray<TPair<double, int32>> NearW;
		NearW.Reserve(WashPoints.Num());
		for (int32 i = 0; i < WashPoints.Num(); ++i)
		{
			NearW.Add(TPair<double, int32>(FVector::DistSquared(WashPoints[i], View), i));
		}
		NearW.Sort([](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
		for (int32 k = 0; k < Washes.Num(); ++k)
		{
			UPointLightComponent* W = Washes[k];
			if (k >= NearW.Num())
			{
				W->SetVisibility(false);
				continue;
			}
			const int32 i = NearW[k].Value;
			W->SetWorldLocation(WashPoints[i]);
			W->SetLightColor(WashColors.IsValidIndex(i) ? WashColors[i] : FLinearColor::White);
			W->SetIntensity(WashCandela);
			W->SetVisibility(true);
		}
	}
}

// -- the tick --

void ACityGenPlay::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bReady)
	{
		Setup();
		return;
	}
	const double Now = FPlatformTime::Seconds();
	if (bWaiting)
	{
		APawn* Pawn = WaitPawn.Get();
		UWorldPartitionSubsystem* WP = GetWorld()->GetSubsystem<UWorldPartitionSubsystem>();
		const double Waited = Now - WaitStart;
		const bool bDone = Waited > 0.5 && (!WP || WP->IsStreamingCompleted(PC));
		if (!Pawn || bDone || Waited > StreamWaitMax)
		{
			bWaiting = false;
			if (Pawn)
			{
				Pawn->SetActorLocation(WaitTarget, false, nullptr, ETeleportType::TeleportPhysics);
				Hold(Pawn, false);
			}
		}
	}
	if (bNight && (LampsAt < 0.0 || Now - LampsAt > LampEvery))
	{
		LampsAt = Now;
		UpdateLamps();
	}
}

FString ACityGenPlay::GetStatus() const
{
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	const FVector At = Pawn ? Pawn->GetActorLocation() : FVector::ZeroVector;
	int32 Lit = 0;
	int32 Shadowed = 0;
	for (const USpotLightComponent* L : Lamps)
	{
		Lit += L->IsVisible() ? 1 : 0;
		Shadowed += (L->IsVisible() && L->CastShadows) ? 1 : 0;
	}
	int32 PoolsVisible = 0;
	for (const UDecalComponent* D : Pools)
	{
		PoolsVisible += D->IsVisible() ? 1 : 0;
	}
	return FString::Printf(TEXT("{\"ready\": %s, \"night\": %s, \"map\": %s, \"menu\": %s, "
		"\"free_cam\": %s, \"waiting\": %s, \"pawn\": \"%s\", \"x\": %.2f, \"y\": %.2f, \"z\": %.2f, "
		"\"lamps_lit\": %d, \"lamps_shadowed\": %d, \"light_pools\": %d, "
		"\"lamp_points\": %d, \"walk_points\": %d, \"map_texture\": %s, "
		"\"overlay\": %s}"),
		bReady ? TEXT("true") : TEXT("false"), bNight ? TEXT("true") : TEXT("false"),
		bMapOpen ? TEXT("true") : TEXT("false"), bDevOpen ? TEXT("true") : TEXT("false"),
		IsFreeCam() ? TEXT("true") : TEXT("false"), bWaiting ? TEXT("true") : TEXT("false"),
		Pawn ? *Pawn->GetClass()->GetName() : TEXT(""), At.X / 100.0, -At.Y / 100.0, At.Z / 100.0,
		Lit, Shadowed, PoolsVisible, LampPoints.Num(), WalkPoints.Num(), MapTexture ? TEXT("true") : TEXT("false"),
		Overlay.IsValid() ? TEXT("true") : TEXT("false"));
}
