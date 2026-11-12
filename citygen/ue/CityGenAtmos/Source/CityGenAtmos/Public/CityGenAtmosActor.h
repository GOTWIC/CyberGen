// atmosgen's runtime controller (docs/atmosgen_scope.md 4.2, docs/unreal_export.md "From AT0"
// and "From AT1"): one actor per city level, always loaded, placed by the importer with the
// plan's settings (its schedules, tiers, exposure, hour and weather). The plan's lights live
// in its cells' data actors (CityGenAtmosCell, one per 128 m World Partition cell, streamed
// with it), which register their lights with the controller while loaded; the controller keeps
// the nearest of them live by tier (near: shadowed, mid: unshadowed, far: none) from pools of
// light components, drives the hour and the weather into the material parameter collections,
// and holds the air and weather effects AT0 prototyped (height and volumetric fog, rain cards,
// a wet decal). AT2 to AT5 grow each part; the play features (CityGenPlay) keep input, map,
// menu and free camera, and their light pools as the far tier past the live range (the
// console variable CityGen.PlayLamps). AT2 (neon and signs as light): a high tier of its own
// (crown floods, uplights, searchlights, high masts: the nearest MaxHigh within HighRangeM,
// never taking the street's place in the mid set), blinking aviation lights and sweeping
// searchlights (each animated from the world's time), and the stand-ins for their fixtures
// until stage 2 draws them: a red beacon per aviation light (an instanced glow per cell,
// blinking with its light in M_CgBeacon) and a beam per searchlight (a cone in M_CgBeam,
// additive, fading along it), shown by night. AT3 (sky and time): the hour drives the sun and
// the moon (the importer's `lighting.sun` is the sun by day and the moon by night), the sky
// light, the exposure (held per look and hour: no eye adaptation pumping), MPC_CityGen's Night
// and Hour, every light's schedule (interpolated between the hours) and a sky dome (M_CgSky:
// the sky atmosphere, the stars, the moon, the cloud deck lit by the city's glow); the play
// features' day and night button and their menu's time-of-day slider drive it. Frames:
// Unreal cm, X east, Y south.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Info.h"
#include "CityGenAtmosActor.generated.h"

class ACityGenAtmosCell;
class ADirectionalLight;
class ASkyLight;
class UMaterialInstanceDynamic;
class UTexture2D;
class AExponentialHeightFog;
class APostProcessVolume;
class UDecalComponent;
class UInstancedStaticMeshComponent;
class ULocalLightComponent;
class UStaticMeshComponent;
class UPrimitiveComponent;
class UMaterialInterface;
class UMaterialParameterCollection;

/** One light of the plan, as the runtime keeps it. */
struct FCityGenAtmosLight
{
	FVector Pos = FVector::ZeroVector;      // cm
	FRotator Rot = FRotator::ZeroRotator;   // the light's +X along its aim
	FVector2f Size = FVector2f::ZeroVector; // a rect's width and height (cm)
	float SourceCm = 0.f;
	float Intensity = 0.f;                  // spot, point: candela; rect: nits
	FLinearColor Color = FLinearColor::White;
	float ReachCm = 1000.f;
	float Inner = 40.f;                     // a spot's cones; a rect's barn door angle
	float Outer = 70.f;
	uint8 Shape = 0;                        // 0 spot, 1 point, 2 rect
	uint8 Kind = 0;                         // index into KindNames
	uint8 Schedule = 0;                     // index into ScheduleNames
	bool bShadow = false;
	bool bNearOnly = false;
	bool bOn = true;
	bool bNoSpecular = false;               // a lit face's stand-in: no highlight
	bool bHigh = false;                     // AT2: the high tier (its own pool)
	uint8 Anim = 0;                         // AT2: 0 none, 1 blink, 2 sweep
	float Flicker = 0.f;
	float AnimPeriod = 0.f;                 // s
	float AnimAmount = 0.f;                 // a blink's on share, a sweep's swing (deg)
	float AnimPhase = 0.f;                  // 0 to 1
	uint32 Seed = 0;
};

UCLASS(HideCategories = (Actor, Input, Replication, Rendering, Collision, HLOD, Physics,
	Networking, LevelInstance, DataLayers, Cooking))
class CITYGENATMOS_API ACityGenAtmos : public AInfo
{
	GENERATED_BODY()

public:
	ACityGenAtmos();

	// -- the plan's settings (set by the importer from atmos_plan.json) --

	UPROPERTY(EditAnywhere, Category = "CityGen")
	FString City;

	/** The plan's hash (the importer's: an import of another plan updates the actor). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	FString PlanHash;

	/** Every schedule's name and its 24 hourly values (ScheduleHours: 24 per name). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FString> ScheduleNames;

	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<float> ScheduleHours;

	/** The light kinds the cells' records index (street_light, signal, corner, ...). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	TArray<FString> KindNames;

	/** The exposure the plan's lights are set for (EV100). */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	float PlanEV100 = 3.f;

	/** The weather the fog and rain start from (the plan's weather state). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	float FogDensity = 0.018f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	float FogFalloff = 0.08f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	float FogVolumetric = 1.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	FLinearColor FogAlbedo = FLinearColor(0.55f, 0.6f, 0.68f);

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	float RainRate = 0.8f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Weather")
	float WindMS = 6.f;

	/** The cells' size (m): World Partition's main grid. */
	UPROPERTY(EditAnywhere, Category = "CityGen")
	float CellM = 128.f;

	// -- the runtime's switches --

	/** Whether the plan's lights are on (they show by night: MPC_CityGen's Night). */
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

	/** AT2: the high tier (crown floods, uplights, searchlights, high masts), a pool of its
	 *  own: at most this many live ... */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	int32 MaxHigh = 48;

	/** ... within this distance (m): World Partition's loading range keeps its cells in. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float HighRangeM = 750.f;

	/** AT2: the aviation beacons' and searchlight beams' glow (art direction). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float BeaconGlow = 1.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float BeamGlow = 1.f;

	/** AT2: draw the beacons and beams (the fixtures' stand-ins). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	bool bFixtures = true;

	/** The night's exposure in the scene (EV100, held at -3 as the play features held it). The
	 *  plan's lights are set for its own night exposure; each is scaled by 2^(this - that) at
	 *  every hour (AT3: so at dusk, under a brighter exposure, they read dimmer). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	float SceneEV100 = -3.f;

	/** The far tier until AT7: past the live range the play features' light-pool decals stay
	 *  under the lamps (CityGen.PlayLamps 2), so the far streets still read lit. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Lights")
	bool bFarPools = true;

	/** A further gain on every light (art direction). */
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

	// -- AT3: the sky and time (the plan's `sky`; atmosgen/sky.py computes the same) --

	/** Where and when: the city's latitude, the sun's declination that day (degrees). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float LatitudeDeg = 35.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float DeclinationDeg = 23.44f;

	/** The moon: how far it trails the sun (hours), its declination, lit fraction, a full
	 *  moon's light as a share of the sun's, its light's color. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float MoonLagH = 14.88f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float MoonDeclinationDeg = -17.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float MoonLit = 0.86f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float MoonShare = 0.03f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	FLinearColor MoonColor = FLinearColor(0.27f, 0.39f, 1.f);

	/** Its disk: luminance in the scene's frame (cd/m2) and angular diameter (degrees). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float MoonDiskNits = 0.5f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float MoonDiskDeg = 0.53f;

	/** Its light fades in between these elevations (degrees). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> MoonRise;

	/** The share of its light the cloud deck's cover takes. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float MoonCloud = 0.75f;

	/** The sun's light by day in the scene's frame (lux). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float SunLux = 10.f;

	/** The day's exposure (EV100; SceneEV100 is the night's). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float DayEV100 = 1.6f;

	/** Curves over the sun's elevation (CurveElev, degrees), piecewise linear: the exposure
	 *  (0 the night's, 1 the day's), MPC_CityGen's Night, the sun's light (of SunLux), the sky
	 *  light (of its own), the stars (of Stars). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> CurveElev;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> CurveEV;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> CurveNight;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> CurveSun;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> CurveSky;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> CurveStars;

	/** How many stars a clear dark sky shows (0 to 1). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float Stars = 0.25f;

	/** The cloud deck: its height (m, 0 none) and the share of the sky it hides. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float CloudDeckM = 420.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float CloudCover = 0.8f;

	/** The deck's underside lit by the city (the plan's raster: linear, square-root encoded),
	 *  its bounds in Unreal's frame (cm: min X, min Y, max X, max Y) and a channel's value at
	 *  255 (cd/m2, physical). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TObjectPtr<UTexture2D> SkyGlow;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	TArray<float> GlowBounds;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float GlowMaxNits = 1.f;

	/** Art direction: a gain on the deck's glow, and how bright the sun or moon lights it. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float GlowGain = 1.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	float CloudLit = 0.1f;

	/** The named hours: the play features' day and night, and dusk (the sun just set). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Time")
	float DayHour = 16.f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Time")
	float DuskHour = 19.5f;

	UPROPERTY(EditAnywhere, Category = "CityGen|Time")
	float NightHour = 23.f;

	/** How fast the hour runs (game hours per real second; 0 holds it). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Time")
	float TimeSpeed = 0.f;

	/** The sky and time drive the level's sun, sky light, exposure and the sky dome (off:
	 *  the level's own, as before AT3). */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	bool bSky = true;

	/** The exposure held at the hour's (no eye adaptation pumping); off: the engine's own. */
	UPROPERTY(EditAnywhere, Category = "CityGen|Sky")
	bool bLockExposure = true;

	/** AT3: the sky and time on or off. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetSky(bool bOn);

	/** AT3: how fast the hour runs (hours per second). */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetTimeSpeed(float HoursPerSecond);

	/** AT3: the exposure held at the hour's, or the engine's eye adaptation. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetLockExposure(bool bOn);

	/** AT3: the cloud deck's cover (0 to 1) for this session (art direction, shots). */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetCloudCover(float Cover);

	/** AT3: the hour by its name: day, dusk or night (else false). */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	bool SetNamedHour(const FString& Name);

	/** AT3: MPC_CityGen's Night now (0 by day, 1 by night, between at dusk and dawn). */
	UFUNCTION(BlueprintPure, Category = "CityGen")
	float GetNight() const { return NightNow; }

	/** AT3: whether the plan gave a sky (an AT2 plan did not). */
	bool HasSky() const { return CurveElev.Num() >= 2; }

	// -- the cells --

	/** A cell's data actor brings its lights in (CityGenAtmosCell::BeginPlay). */
	void RegisterCell(ACityGenAtmosCell* Cell);

	/** ... and takes them out (EndPlay, as World Partition streams the cell out). */
	void UnregisterCell(ACityGenAtmosCell* Cell);

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

	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetFarPools(bool bOn);

	/** The tiers: live count, mid range (m), shadowed count. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetTiers(int32 Live, float RangeM, int32 Shadowed);

	/** AT2: the high tier: live count, range (m). */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetHigh(int32 InHigh, float RangeM);

	/** AT2: the beacons and beams on or off. */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	void SetFixtures(bool bOn);

	/** The state as one JSON line (the check and the benchmark read it). */
	UFUNCTION(BlueprintPure, Category = "CityGen")
	FString GetStatus() const;

	/** The first atmos actor in `World`, else null. */
	static ACityGenAtmos* Find(const UWorld* World);

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
	/** A registered cell: its actor, its 128 m key and its lights; AT2: its high tier's
	 *  lights, its beacons (one instanced component) and its beams (a component each, by
	 *  their light's index). */
	struct FSlot
	{
		TWeakObjectPtr<ACityGenAtmosCell> Actor;
		FIntPoint Key = FIntPoint::ZeroValue;
		TArray<FCityGenAtmosLight> Lights;
		TArray<int32> High;
		TWeakObjectPtr<UInstancedStaticMeshComponent> Beacons;
		TArray<TPair<int32, TWeakObjectPtr<UStaticMeshComponent>>> Beams;
		bool bUsed = false;
	};

	static int64 LiveKey(int32 Slot, int32 Light) { return (int64(Slot) << 24) | int64(Light); }
	const FCityGenAtmosLight* LightOf(int64 Key) const;
	FVector ViewLocation(FRotator* OutRot = nullptr) const;
	FIntPoint CellOf(const FVector& P) const;
	void UpdateLive();
	void UpdateFlicker(double Now);
	void UpdateBeams(double T);
	void MakeFixtures(int32 Slot);
	void DropFixtures(int32 Slot);
	void ShowFixtures(bool bOn);
	FRotator AnimRot(const FCityGenAtmosLight& L, double T) const;
	float AnimGain(const FCityGenAtmosLight& L, double T) const;
	double WorldTime() const;
	void ApplyLight(ULocalLightComponent* C, const FCityGenAtmosLight& L, float Fade, bool bShadowed);
	ULocalLightComponent* Take(uint8 Shape);
	void Release(int64 Key);
	void ReleaseAll();
	void SetPlayLamps(bool bOn) const;
	void EnsureFog();
	void EnsureRain();
	void EnsureWet();
	void EnsureVolume();
	void PushParameters();
	float ScheduleAt(uint8 Schedule) const;
	float Scale() const;
	bool HasPlan() const { return ScheduleNames.Num() > 0; }

	// the registered cells and their index
	TArray<FSlot> Slots;
	TArray<int32> FreeSlots;
	TMap<FIntPoint, TArray<int32>> SlotsAt;
	TMap<TWeakObjectPtr<ACityGenAtmosCell>, int32> SlotOfActor;
	int32 RegisteredLights = 0;
	int32 Registrations = 0;

	// the live set
	TMap<int64, TObjectPtr<ULocalLightComponent>> Live;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> FreeSpot;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> FreePoint;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> FreeRect;
	UPROPERTY(Transient)
	TArray<TObjectPtr<ULocalLightComponent>> AllLights;
	TSet<int64> Shadowed;
	TArray<int64> Flickering;               // (AT2: and the blinking and sweeping)
	TMap<int64, float> FadeOf;              // (their live set's fade)
	int32 LiveHigh = 0;
	int32 CandidatesHigh = 0;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UPrimitiveComponent>> Fixtures;   // (beacons and beams, kept from GC)
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> BeaconMaterial;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> BeamMaterial;
	bool bFixturesShown = false;
	int32 BeaconCount = 0;
	int32 BeamCount = 0;
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
	bool bShowing = false;                  // the lights live now (on, a plan, by night)

	// AT3: the sky and time
	void FindLighting();
	void EnsureDome();
	void ApplyTime();
	float CurveAt(const TArray<float>& Values, float Elev) const;
	static FVector Body(float LatDeg, float DecDeg, float HourAngleDeg, float& OutElevDeg);
	UPROPERTY(Transient)
	TObjectPtr<ADirectionalLight> Sun;
	UPROPERTY(Transient)
	TObjectPtr<ASkyLight> SkyLightActor;
	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> Dome;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> SkyMID;
	float DaySkyIntensity = 1.f;
	FLinearColor DaySunColor = FLinearColor::White;
	bool bLightingFound = false;
	float NightNow = 1.f;
	float EVNow = -3.f;
	float SunElev = -30.f;
	float MoonElev = 0.f;
	float SunWeight = 0.f;
	float MoonLux = 0.f;
	float CoverNow = 0.8f;
	double TimeAppliedAt = -1.0;
};
