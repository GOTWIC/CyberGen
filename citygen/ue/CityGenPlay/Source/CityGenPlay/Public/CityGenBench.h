// AG16's benchmark (`citygen unreal BUILD UPROJECT --bench`, docs/unreal_export.md, "From
// AG16"): a world subsystem of the play plugin that, in a standalone game process started
// with -CityGenBench=<job.json>, moves the player along the job's fixed route (sidewalk
// walks, a drive at street level, a flight across the city, a teleport), by passes (day or
// night, a screen percentage), records every frame (frame, game, render, RHI and GPU
// times, draw calls, streaming, VRAM, RAM) and the engine's CSV profile beside it (Nanite
// root pages, GPU passes), writes them and quits. Python (citygen/bench.py) writes the job
// and reads the results. Frames: Unreal cm, X east, Y south.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "CityGenBench.generated.h"

class APawn;
class APlayerController;

/** One leg of the route: a path walked or flown at a speed, or a teleport. */
struct FCityGenBenchSegment
{
	FString Name;
	FString Kind;                 // "path" or "teleport"
	TArray<FVector> Points;       // the path (cm, the eye's height), or the teleport's target
	TArray<double> Along;         // cumulative length at each point (cm)
	double Speed = 500.0;         // cm/s
	double Pitch = 0.0;           // degrees (negative: looking down)
	double Hold = 5.0;            // s held after a teleport has streamed in
};

/** One pass over the route: day or night at a screen percentage. */
struct FCityGenBenchPass
{
	FString Name;
	bool bNight = false;
	float ScreenPercentage = 100.f;
	bool bWarm = false;           // a warm-up pass: recorded, left out of the results
};

UCLASS()
class CITYGENPLAY_API UCityGenBench : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

private:
	enum class EStage : uint8 { Start, Pass, Load, Settle, Move, Teleport, Hold, Done };

	bool ReadJob();
	void Begin();
	void StartPass();
	void StartSegment();
	void NextSegment();
	void Finish();
	void Record(double Dt, int32 Phase, bool bSampleStream);
	bool Streamed(const FVector& At, double RadiusCm) const;
	void Place(const FVector& Eye, double Yaw, double Pitch);
	FVector PointAt(const FCityGenBenchSegment& S, double D) const;
	void Event(const FString& Text);

	FString JobPath;
	FString OutDir;
	FString CsvName;
	TArray<FString> Commands;
	TArray<FCityGenBenchPass> Passes;
	TArray<FCityGenBenchSegment> Segments;
	double SettleS = 1.5;
	double LoadTimeoutS = 120.0;
	double LoadRadiusCm = 15000.0;
	double StreamRadiusCm = 10000.0;
	double StartWaitS = 10.0;
	int32 StreamEvery = 5;
	int32 MemoryEvery = 15;

	EStage Stage = EStage::Start;
	int32 PassIndex = 0;
	int32 SegIndex = 0;
	double StageStart = 0.0;
	double Travelled = 0.0;
	double Yaw = 0.0;
	double T0 = 0.0;
	int64 FrameCount = 0;
	int32 LastStreamed = -1;
	int32 LastPerf = -1;
	double LastVramMB = -1.0;
	double LastRamMB = -1.0;
	bool bFailed = false;
	FString Error;

	TArray<FString> Rows;         // the frames, as CSV lines
	TArray<FString> Events;       // JSON objects: segment starts, loads, teleports

	TWeakObjectPtr<APlayerController> PC;
	TWeakObjectPtr<APawn> Pawn;
};
