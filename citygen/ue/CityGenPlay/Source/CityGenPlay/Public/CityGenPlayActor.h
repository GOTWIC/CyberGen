// citygen's play features in a level `citygen unreal` imported (docs/unreal_export.md, "Play
// features"): a minimap, the map (M: zoom, pan, click to teleport), a free camera (.), and a
// developer menu (Tab) with day and night. One actor per city level, always loaded; the
// importer (citygen/ue/import_city.py) sets its data. Frames: Unreal cm, X east, Y south.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Info.h"
#include "CityGenPlayActor.generated.h"

class ACityGenFreeCam;
class APlayerController;
class APostProcessVolume;
class SCityGenOverlay;
class UDecalComponent;
class UMaterialInterface;
class UMaterialParameterCollection;
class UPointLightComponent;
class USpotLightComponent;
class UTexture2D;

UCLASS(HideCategories = (Actor, Input, Replication, Rendering, Collision, HLOD, Physics,
	Networking, LevelInstance, DataLayers, Cooking))
class CITYGENPLAY_API ACityGenPlay : public AInfo
{
	GENERATED_BODY()

public:
	ACityGenPlay();

	// -- the city's data (set by the importer) --

	UPROPERTY(EditAnywhere, Category = "CityGen")
	FString City;

	/** The map image (citygen's unreal/map.png), north up. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TObjectPtr<UTexture2D> MapTexture;

	/** Where the map image's top left and bottom right corners are (Unreal cm). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	FVector2D MapTopLeft = FVector2D(-100000.0, -100000.0);

	UPROPERTY(EditAnywhere, Category = "CityGen")
	FVector2D MapBottomRight = FVector2D(100000.0, 100000.0);

	/** Points of the walkway graph (absolute heights): where a walking player lands. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FVector> WalkPoints;

	/** The street and wall lights' lamp heads. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FVector> LampPoints;

	/** Per lamp: 0 a street light, 1 a wall light. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<uint8> LampKinds;

	/** AG15: in front of each of M20's large facade signs (billboards, banners, holo-boards),
	 *  where its light washes its facade by night, and its color. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FVector> WashPoints;

	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FLinearColor> WashColors;

	/** District names on the map, at LabelPoints. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FString> LabelNames;

	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FVector2D> LabelPoints;

	/** /Game/CityGen/Core/MPC_CityGen: its Night lights the windows, neon and signs. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TObjectPtr<UMaterialParameterCollection> NightCollection;

	// -- settings --

	/** How far the minimap shows around the player (m). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float MinimapRadiusM = 250.f;

	/** The free camera's starting speed (m/s; the mouse wheel changes it). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float FreeCamSpeedMS = 30.f;

	/** The light-pool decal material (/Game/CityGen/Core/M_CgLightPool): a soft warm pool on
	 *  the ground under a lamp with no light of its own (AG15). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TObjectPtr<UMaterialInterface> LightPoolMaterial;

	/** AG15: how many lamps nearest the camera get a real light by night: a spot light under
	 *  the lamp head pointing down, outside the lamp mesh's shadow. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	int32 LampLights = 192;

	/** ... of which the nearest this many cast shadows. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	int32 ShadowedLamps = 8;

	/** How many lamps past the lit ones get a light-pool decal on the ground under them. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	int32 LampPools = 768;

	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float LampRadiusM = 30.f;

	/** How far under the lamp head the spot light hangs (cm): below the lamp's housing, so
	 *  the lamp mesh does not shadow its own light. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float LampDropCm = 45.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float LampInnerConeDeg = 50.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float LampOuterConeDeg = 78.f;

	/** 0.08 of the run-through's 1,500 and 400 (Swagnik, 2026-11-09): under the night's
	 *  fixed exposure those left near-white pools on the road. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float StreetLampCandela = 120.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float WallLampCandela = 32.f;

	/** How many of the large signs nearest the camera wash their facade with a light. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	int32 WashLights = 32;

	/** (600 before 2026-11-09: it painted whole facades in the sign's color) */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float WashCandela = 120.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float WashRadiusM = 25.f;

	/** A light pool's radius on the ground (m). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float PoolRadiusM = 7.f;

	/** The night's hour (MPC_CityGen's Hour: each building's rooms lit by its schedule). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float NightHour = 21.f;

	/** The night's exposure (EV100, fixed so the night stays dark). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float NightExposureEV100 = -3.f;

	/** The moon's share of the sun's intensity. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float MoonFraction = 0.03f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	bool bStartAtNight = false;

	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	bool bShowMinimap = true;

	// -- what the keys and the console commands do (also callable from Python) --

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetMapOpen(bool bOpen);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetFreeCam(bool bOn);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetDevMenuOpen(bool bOpen);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetNight(bool bOn);

	/** Teleport the player to an Unreal location (cm; Z ignored): a walking pawn onto the
	 *  nearest walkway, held there until the city has streamed in around it; a flying one
	 *  at its height (at least 30 m over the walkway there). */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	bool TeleportPlayer(FVector Location);

	/** The same at citygen's (x, y) in meters. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	bool TeleportPlayerToCitygen(float X, float Y);

	/** A JSON line of the state (the check reads it). */
	UFUNCTION(BlueprintPure, Category = "CityGen")
	FString GetStatus() const;

	bool IsMapOpen() const { return bMapOpen; }
	bool IsDevMenuOpen() const { return bDevOpen; }
	bool IsFreeCam() const;
	bool IsNight() const { return bNight; }
	bool IsWaitingForStreaming() const { return bWaiting; }
	float GetFreeCamSpeed() const;
	FString GetToast() const;

	/** The player's view: its location (cm) and yaw (degrees). */
	FVector ViewLocation() const;
	float ViewYaw() const;

	/** The first play actor that has begun play in `World`, else null. */
	static ACityGenPlay* Find(const UWorld* World);

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
	void Setup();
	void BindKeys();
	void UpdateInputMode();
	void OnKeyMap() { SetMapOpen(!bMapOpen); }
	void OnKeyFreeCam() { SetFreeCam(!IsFreeCam()); }
	void OnKeyDevMenu() { SetDevMenuOpen(!bDevOpen); }
	void OnWheel(float Factor);
	void OnWheelUp() { OnWheel(1.25f); }
	void OnWheelDown() { OnWheel(0.8f); }
	void Toast(const FString& Text, float Seconds = 2.5f);
	void Hold(APawn* Pawn, bool bHold);
	void WaitForStreaming(APawn* Pawn, const FVector& Target);
	void UpdateLamps();
	int32 NearestWalk(const FVector2D& At) const;

	UPROPERTY(Transient)
	TObjectPtr<APlayerController> PC;

	UPROPERTY(Transient)
	TObjectPtr<ACityGenFreeCam> FreeCam;

	UPROPERTY(Transient)
	TObjectPtr<APawn> SavedPawn;

	UPROPERTY(Transient)
	TObjectPtr<APostProcessVolume> NightVolume;

	UPROPERTY(Transient)
	TArray<TObjectPtr<USpotLightComponent>> Lamps;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UDecalComponent>> Pools;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UPointLightComponent>> Washes;

	TSharedPtr<SCityGenOverlay> Overlay;
	bool bReady = false;
	bool bMapOpen = false;
	bool bDevOpen = false;
	bool bNight = false;
	bool bUIInput = false;
	bool bWaiting = false;
	TWeakObjectPtr<APawn> WaitPawn;
	FVector WaitTarget = FVector::ZeroVector;
	double WaitStart = 0.0;
	double LampsAt = -1.0;
	int32 LampsOn = 0;
	int32 PoolsOn = 0;
	FString ToastText;
	double ToastUntil = 0.0;

	// the day's lighting, kept to go back to it
	bool bDaySaved = false;
	FRotator DaySunRotation = FRotator::ZeroRotator;
	float DaySunIntensity = 0.f;
	FLinearColor DaySunColor = FLinearColor::White;
	float DaySkyIntensity = 1.f;
};
