// citygen's play features in a level `citygen unreal` imported (docs/unreal_export.md, "Play
// features"): a minimap, the map (M: zoom, pan, click to teleport), a free camera (.), and a
// developer menu (Tab) with the time of day. One actor per city level, always loaded; the
// importer (citygen/ue/import_city.py) sets its data. AT3: the sky, the moon, the hour and the
// exposure are atmosgen's (its CityGenAtmos controller, found by its class name): the day and
// night button and the menu's time-of-day slider drive it; the night switch here (the sun as
// a dim moon, NightHour, the held night exposure) is kept only for a level without it.
// Frames: Unreal cm, X east, Y south.

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

	/** The street and wall lights' lamp heads (the light pools stand under them). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FVector> LampPoints;

	/** Per lamp: 0 a street light, 1 a wall light. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<uint8> LampKinds;

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

	// (AT1: the lamps' lights are atmosgen's, the CityGenAtmos controller's live set, AG15's
	// spot lamps and sign washes gone for good; the play features keep the light pools as
	// the far tier, past atmosgen's live range, CityGen.PlayLamps 2, until AT7)

	/** How many lamps get a light-pool decal on the ground under them. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	int32 LampPools = 768;

	/** A light pool's radius on the ground (m). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Settings")
	float PoolRadiusM = 7.f;

	// (AT3: NightHour, NightExposureEV100 and MoonFraction serve only a level without
	// atmosgen's controller, whose sky and time replace them)

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

	/** Day or night: with atmosgen's controller its day or night hour (AT3), else the night
	 *  switch of a level without it. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetNight(bool bOn);

	/** AT3: the time of day (0 to 24) on atmosgen's controller (the menu's slider). False
	 *  without one. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	bool SetTimeOfDay(float InHour);

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

	// -- atmosgen's weather prototypes in the developer menu (AT5 replaces them with weather
	// states). The controller (CityGenAtmos) is found by its class name and driven through its
	// UFUNCTIONs and properties, so the play features build and run without that plugin. --

	/** What a click on a developer menu row does, by the row's name: night, freecam,
	 *  minimap, messages, and with an atmos controller fog, rain, wet, hour+ and hour-, and
	 *  AT3's time slider as hour=H (a number, or day, dusk or night); AT5's weather row,
	 *  weather+ and weather- (the next or the previous state, blended) and weather=NAME
	 *  (`weather=rain!` at once) (the overlay's clicks and the console's CityGen.MenuRow).
	 *  False for a row the menu does not show. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	bool ClickMenuRow(const FString& Row);

	/** The level's atmos controller, else null (the menu then shows no weather rows). */
	AActor* GetAtmos() const;

	/** One of the controller's switches: bFog, bRain, bWet. */
	bool GetAtmosFlag(FName Property) const;

	/** Calls SetFog, SetRain or SetWet on the controller. */
	void SetAtmosFlag(FName Function, bool bOn);

	/** AT5: the controller's weather now ("rain", "clear > rain" while it turns), "" without a
	 *  weather (the menu then shows AT0's fog, rain and wet rows). */
	FString GetAtmosWeather() const;

	/** The controller's hour (0 to 24), and SetHour. */
	float GetAtmosHour() const;
	void SetAtmosHour(float InHour);

	bool IsMapOpen() const { return bMapOpen; }
	bool IsDevMenuOpen() const { return bDevOpen; }
	bool IsFreeCam() const;
	/** Night: atmosgen's Night over a half (AT3), else the night switch. */
	bool IsNight() const;

	/** AT3: atmosgen's Night (0 by day, 1 by night), else the switch's 0 or 1. */
	float NightShare() const;
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
	void UpdateUnderwater();
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
	TArray<TObjectPtr<UDecalComponent>> Pools;

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
	double UnderwaterAt = -1.0;
	int32 UnderwaterOn = 0;
	int32 PoolsOn = 0;
	FString ToastText;
	double ToastUntil = 0.0;
	mutable TWeakObjectPtr<AActor> Atmos;
	mutable double AtmosLookAt = -1.0;

	// the day's lighting, kept to go back to it
	bool bDaySaved = false;
	FRotator DaySunRotation = FRotator::ZeroRotator;
	float DaySunIntensity = 0.f;
	FLinearColor DaySunColor = FLinearColor::White;
	float DaySkyIntensity = 1.f;
};
