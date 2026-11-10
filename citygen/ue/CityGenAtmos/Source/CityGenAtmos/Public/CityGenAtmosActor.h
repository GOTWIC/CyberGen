// atmosgen's runtime controller (docs/atmosgen_scope.md 4.2, docs/unreal_export.md "From AT0"):
// one actor per city level, always loaded. It reads a city's atmos plan (BUILD/atmos:
// atmos_plan.json and lights/<tile>.json), keeps the plan's lights live near the view by tier
// (near: shadowed, mid: unshadowed, far: none), drives the hour and the weather into the
// material parameter collections, and holds the air and weather effects AT0 prototypes:
// exponential height fog with volumetric fog, rain as instanced streak cards round the view,
// wet streets as a deferred decal. AT1 to AT5 grow each part (tile spawners streamed with
// their World Partition cells, the sky, the effects); the play features (CityGenPlay) keep
// input, map, menu and free camera, their lamps going dark while the plan's lights are on
// (the console variable CityGen.PlayLamps). Frames: Unreal cm, X east, Y south.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Info.h"
#include "CityGenAtmosActor.generated.h"

class AExponentialHeightFog;
class APostProcessVolume;
class UDecalComponent;
class UInstancedStaticMeshComponent;
class ULocalLightComponent;
class UMaterialInterface;
class UMaterialParameterCollection;

/** One light of the plan, as the runtime keeps it. */
struct FCityGenAtmosLight
{
	FVector Pos = FVector::ZeroVector;      // cm
	FRotator Rot = FRotator::ZeroRotator;   // the light's +X along its aim
	FVector2f Size = FVector2f::ZeroVector; // a rect's width and height (cm)
	float SourceCm = 0.f;
	float Candela = 0.f;                    // spot, point: the peak; rect: luminance x area
	float Nits = 0.f;                       // a rect's luminance
	FLinearColor Color = FLinearColor::White;
	float ReachCm = 1000.f;
	float Inner = 40.f;
	float Outer = 70.f;
	float Barn = 80.f;
	uint8 Shape = 0;                        // 0 spot, 1 point, 2 rect
	uint8 Kind = 0;                         // index into Kinds
	uint8 Schedule = 0;                     // index into Schedules
	bool bShadow = false;
	bool bNearOnly = false;
	bool bOn = true;
	float Flicker = 0.f;
	uint32 Seed = 0;
};

UCLASS(HideCategories = (Actor, Input, Replication, Rendering, Collision, HLOD, Physics,
	Networking, LevelInstance, DataLayers, Cooking))
class CITYGENATMOS_API ACityGenAtmos : public AInfo
{
	GENERATED_BODY()

public:
	ACityGenAtmos();

	/** The plan's folder (BUILD/atmos). AT0's spike reads it from disk; AT1 moves the tiles'
	 *  lights into the level, streamed with their cells. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	FString PlanDir;

	/** Whether the plan's lights are on (the play features' lamps go dark while they are). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	bool bLights = true;

	/** The live set: at most this many lights near the view... */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	int32 MaxLive = 512;

	/** ... within this distance (m) ... */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float MidRangeM = 300.f;

	/** ... of which the nearest this many that may cast shadows do, within NearRangeM. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	int32 MaxShadowed = 16;

	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float NearRangeM = 60.f;

	/** The exposure the scene is shown at (EV100): the play features hold the night at -3. The
	 *  plan's lights are set for its own night exposure; each is scaled by 2^(this - that). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float SceneEV100 = -3.f;

	/** A further gain on every light (art direction, the spike's tuning). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float Gain = 1.f;

	/** Each live light's share in volumetric fog (0: none, the fog's cheapest). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float VolumetricScattering = 1.f;

	/** The hour (0 to 24): every light's schedule and MPC_CityGen's Hour. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Time")
	float Hour = 23.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	bool bFog = false;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	bool bVolumetricFog = true;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	bool bRain = false;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	bool bWet = false;

	/** MegaLights by the post-process volume the actor owns (needs hardware ray tracing:
	 *  r.RayTracing at startup; experimental in 5.8). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	bool bMegaLights = false;

	/** How many rain streak cards fall round the view. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	int32 RainCards = 4000;

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	bool LoadPlan(const FString& Dir);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetLightsOn(bool bOn);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetHour(float InHour);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetFog(bool bOn);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetRain(bool bOn);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetWet(bool bOn);

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetMegaLights(bool bOn);

	/** The tiers: live count, mid range (m), shadowed count. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetTiers(int32 Live, float RangeM, int32 Shadowed);

	/** The state as one JSON line. */
	UFUNCTION(BlueprintPure, Category = "CityGen")
	FString GetStatus() const;

	/** The first atmos actor in `World`, else null. */
	static ACityGenAtmos* Find(const UWorld* World);

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
	FVector ViewLocation(FRotator* OutRot = nullptr) const;
	void UpdateLive();
	void UpdateFlicker(double Now);
	void ApplyLight(ULocalLightComponent* C, const FCityGenAtmosLight& L, float Fade, bool bShadowed);
	ULocalLightComponent* Take(uint8 Shape);
	void Release(int32 LightIndex);
	void ReleaseAll();
	void SetPlayLamps(bool bOn) const;
	void EnsureFog();
	void EnsureRain();
	void EnsureWet();
	void EnsureVolume();
	void PushParameters();
	float ScheduleAt(uint8 Schedule) const;
	float Scale() const;

	// the plan
	TArray<FCityGenAtmosLight> Lights;
	TArray<FString> Kinds;
	TArray<FString> Schedules;
	TArray<TArray<float>> ScheduleHours;
	TMap<FIntPoint, TArray<int32>> Cells;   // 64 m cells -> light indices
	float PlanEV100 = 3.f;
	float FogDensity = 0.018f;
	float FogFalloff = 0.08f;
	float FogVolumetric = 1.f;
	FLinearColor FogAlbedo = FLinearColor(0.55f, 0.6f, 0.68f);
	float RainRate = 0.8f;
	float WindMS = 6.f;
	FString PlanCity;
	bool bPlanLoaded = false;
	double LoadSeconds = 0.0;

	// the live set
	TMap<int32, TObjectPtr<ULocalLightComponent>> Live;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> FreeSpot;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> FreePoint;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> FreeRect;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> AllLights;
	TSet<int32> Shadowed;
	TArray<int32> Flickering;
	double LiveAt = -1.0;
	double UpdateMs = 0.0;
	double UpdateMsMax = 0.0;
	int32 Candidates = 0;

	// the air and weather
	UPROPERTY(Transient)
	TObjectPtr<AExponentialHeightFog> Fog;
	UPROPERTY(Transient)
	TObjectPtr<UInstancedStaticMeshComponent> Rain;
	UPROPERTY(Transient)
	TObjectPtr<UDecalComponent> Wet;
	UPROPERTY(Transient)
	TObjectPtr<APostProcessVolume> Volume;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialParameterCollection> AtmosCollection;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialParameterCollection> CityCollection;
	FVector WetAt = FVector(1e12);
	bool bBegun = false;
};
