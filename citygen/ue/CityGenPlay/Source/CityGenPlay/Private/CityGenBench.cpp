#include "CityGenBench.h"
#include "CityGenUpscaler.h"

#include "CityGenPlayActor.h"
#include "Dom/JsonObject.h"
#include "DynamicRHI.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PawnMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMemory.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "ProfilingDebugging/CsvProfiler.h"
#include "RHIGlobals.h"
#include "RHIStats.h"
#include "RenderTimer.h"
#include "Rendering/NaniteStreamingManager.h"
#include "Scalability.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UnrealClient.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/WorldPartitionRuntimeCell.h"
#include "WorldPartition/WorldPartitionRuntimeHash.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

DEFINE_LOG_CATEGORY_STATIC(LogCityGenBench, Log, All);

namespace
{
	constexpr double PawnWaitS = 120.0;      // the longest wait for the player's pawn
	constexpr double CsvWaitS = 60.0;        // the longest wait for the CSV file's write
	constexpr double YawRate = 3.0;          // how fast the view turns toward the path (1/s)
	constexpr double LookS = 1.2;            // the view looks this far ahead along the path (s)
	constexpr double LookMinCm = 800.0;

	FVector Cm(const TArray<TSharedPtr<FJsonValue>>& P)
	{
		// citygen meters (x east, y north, z up) to Unreal cm (x east, y south)
		return FVector(P[0]->AsNumber() * 100.0, -P[1]->AsNumber() * 100.0, P[2]->AsNumber() * 100.0);
	}

	FString Esc(const FString& S)
	{
		return S.Replace(TEXT("\\"), TEXT("\\\\")).Replace(TEXT("\""), TEXT("\\\""));
	}

	double Ms(uint32 Cycles)
	{
		return FPlatformTime::ToMilliseconds(Cycles);
	}
}

bool UCityGenBench::ShouldCreateSubsystem(UObject* Outer) const
{
	FString P;
	return Super::ShouldCreateSubsystem(Outer) &&
		FParse::Value(FCommandLine::Get(), TEXT("CityGenBench="), P) && !P.IsEmpty();
}

bool UCityGenBench::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId UCityGenBench::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UCityGenBench, STATGROUP_Tickables);
}

bool UCityGenBench::ReadJob()
{
	FParse::Value(FCommandLine::Get(), TEXT("CityGenBench="), JobPath);
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *JobPath))
	{
		Error = FString::Printf(TEXT("cannot read the job %s"), *JobPath);
		return false;
	}
	TSharedPtr<FJsonObject> J;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), J) || !J.IsValid())
	{
		Error = TEXT("the job is not JSON");
		return false;
	}
	OutDir = J->GetStringField(TEXT("out_dir"));
	CsvName = J->GetStringField(TEXT("csv_name"));
	J->TryGetNumberField(TEXT("settle_s"), SettleS);
	J->TryGetNumberField(TEXT("load_timeout_s"), LoadTimeoutS);
	J->TryGetNumberField(TEXT("start_wait_s"), StartWaitS);
	J->TryGetNumberField(TEXT("stream_every"), StreamEvery);
	J->TryGetNumberField(TEXT("memory_every"), MemoryEvery);
	J->TryGetBoolField(TEXT("shots"), bShots);
	double M = 0.0;
	if (J->TryGetNumberField(TEXT("load_radius_m"), M)) { LoadRadiusCm = M * 100.0; }
	if (J->TryGetNumberField(TEXT("stream_radius_m"), M)) { StreamRadiusCm = M * 100.0; }
	StreamEvery = FMath::Max(1, StreamEvery);
	MemoryEvery = FMath::Max(1, MemoryEvery);
	const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
	if (J->TryGetArrayField(TEXT("commands"), Arr))
	{
		for (const TSharedPtr<FJsonValue>& V : *Arr) { Commands.Add(V->AsString()); }
	}
	if (J->TryGetArrayField(TEXT("passes"), Arr))
	{
		for (const TSharedPtr<FJsonValue>& V : *Arr)
		{
			const TSharedPtr<FJsonObject>& O = V->AsObject();
			FCityGenBenchPass P;
			P.Name = O->GetStringField(TEXT("name"));
			O->TryGetBoolField(TEXT("night"), P.bNight);
			double Sp = 100.0;
			O->TryGetNumberField(TEXT("screen_percentage"), Sp);
			P.ScreenPercentage = float(Sp);
			O->TryGetBoolField(TEXT("warm"), P.bWarm);
			const TArray<TSharedPtr<FJsonValue>>* Cmds = nullptr;
			if (O->TryGetArrayField(TEXT("commands"), Cmds))
			{
				for (const TSharedPtr<FJsonValue>& C : *Cmds) { P.Commands.Add(C->AsString()); }
			}
			const TArray<TSharedPtr<FJsonValue>>* Only = nullptr;
			if (O->TryGetArrayField(TEXT("segments"), Only))
			{
				for (const TSharedPtr<FJsonValue>& S : *Only) { P.Only.Add(int32(S->AsNumber())); }
			}
			Passes.Add(P);
		}
	}
	if (J->TryGetArrayField(TEXT("segments"), Arr))
	{
		for (const TSharedPtr<FJsonValue>& V : *Arr)
		{
			const TSharedPtr<FJsonObject>& O = V->AsObject();
			FCityGenBenchSegment S;
			S.Name = O->GetStringField(TEXT("name"));
			S.Kind = O->GetStringField(TEXT("kind"));
			double X = 0.0;
			if (O->TryGetNumberField(TEXT("speed_m_s"), X)) { S.Speed = X * 100.0; }
			O->TryGetNumberField(TEXT("pitch_deg"), S.Pitch);
			O->TryGetNumberField(TEXT("hold_s"), S.Hold);
			const TArray<TSharedPtr<FJsonValue>>* SegCmds = nullptr;
			if (O->TryGetArrayField(TEXT("commands"), SegCmds))
			{
				for (const TSharedPtr<FJsonValue>& C : *SegCmds) { S.Commands.Add(C->AsString()); }
			}
			for (const TSharedPtr<FJsonValue>& P : O->GetArrayField(TEXT("points")))
			{
				S.Points.Add(Cm(P->AsArray()));
			}
			double L = 0.0;
			for (int32 i = 0; i < S.Points.Num(); ++i)
			{
				L += i ? FVector::Dist(S.Points[i - 1], S.Points[i]) : 0.0;
				S.Along.Add(L);
			}
			if (S.Points.Num() >= (S.Kind == TEXT("path") ? 2 : 1))
			{
				Segments.Add(S);
			}
		}
	}
	if (Passes.IsEmpty() || Segments.IsEmpty())
	{
		Error = TEXT("the job has no passes or no segments");
		return false;
	}
	IFileManager::Get().MakeDirectory(*OutDir, true);
	return true;
}

void UCityGenBench::Event(const FString& Text)
{
	Events.Add(FString::Printf(TEXT("{\"t\": %.3f, \"frame\": %lld, \"pass\": %d, \"seg\": %d, %s}"),
		FPlatformTime::Seconds() - T0, FrameCount, PassIndex, SegIndex, *Text));
#if CSV_PROFILER
	FCsvProfiler::RecordEvent(CSV_CATEGORY_INDEX_GLOBAL,
		FString::Printf(TEXT("cg:%d:%d"), PassIndex, SegIndex), false);
#endif
}

void UCityGenBench::Begin()
{
	UWorld* World = GetWorld();
	for (const FString& C : Commands)
	{
		GEngine->Exec(World, *C);
	}
	// the route moves the pawn itself: nothing of its own moves or collides it
	if (APawn* P = Pawn.Get())
	{
		P->SetActorEnableCollision(false);
		if (UPawnMovementComponent* M = P->GetMovementComponent())
		{
			M->StopMovementImmediately();
			M->Deactivate();
		}
	}
#if CSV_PROFILER
	if (FCsvProfiler* Csv = FCsvProfiler::Get())
	{
		Csv->BeginCapture(-1, OutDir, CsvName);
	}
#endif
	T0 = FPlatformTime::Seconds();
	Rows.Reset();
	Rows.Add(TEXT("pass,seg,phase,t,frame_ms,game_ms,render_ms,rhi_ms,gpu_ms,draws,prims,streamed,perf,vram_mb,ram_mb,x,y,z,fg_hz,fg_presented,latency_ms"));
	PassIndex = 0;
	StartPass();
}

void UCityGenBench::StartPass()
{
	const FCityGenBenchPass& P = Passes[PassIndex];
	if (IConsoleVariable* SP = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage")))
	{
		SP->Set(P.ScreenPercentage, ECVF_SetByConsole);
	}
	if (ACityGenPlay* Play = ACityGenPlay::Find(GetWorld()))
	{
		Play->SetNight(P.bNight);
	}
	// AT0: the pass's own console commands (atmosgen's runtime: its lights, fog, rain, wet
	// streets, MegaLights), after the night is set
	for (const FString& C : P.Commands)
	{
		GEngine->Exec(GetWorld(), *C);
	}
	SegIndex = 0;
	Event(FString::Printf(TEXT("\"op\": \"pass\", \"name\": \"%s\", \"night\": %s, \"screen_percentage\": %.1f, \"warm\": %s, \"upscaler\": %s"),
		*Esc(P.Name), P.bNight ? TEXT("true") : TEXT("false"), P.ScreenPercentage,
		P.bWarm ? TEXT("true") : TEXT("false"), *CityGenUpscaler::StatusJson(FIntPoint(0, 0))));
	while (SegIndex < Segments.Num() && !P.Only.IsEmpty() && !P.Only.Contains(SegIndex))
	{
		++SegIndex;
	}
	if (SegIndex >= Segments.Num())
	{
		SegIndex = Segments.Num() - 1;
		NextSegment();
		return;
	}
	StartSegment();
}

void UCityGenBench::StartSegment()
{
	const FCityGenBenchSegment& S = Segments[SegIndex];
	for (const FString& C : S.Commands)
	{
		GEngine->Exec(GetWorld(), *C);
	}
	Event(FString::Printf(TEXT("\"op\": \"segment\", \"name\": \"%s\", \"kind\": \"%s\""), *Esc(S.Name), *S.Kind));
	StageStart = FPlatformTime::Seconds();
	Travelled = 0.0;
	if (S.Kind == TEXT("path"))
	{
		const FVector D = S.Points[1] - S.Points[0];
		Yaw = FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X));
		Place(S.Points[0], Yaw, S.Pitch);
		Stage = EStage::Load;
	}
	else
	{
		Place(S.Points[0], Yaw, S.Pitch);
		Stage = EStage::Teleport;
	}
}

void UCityGenBench::NextSegment()
{
	Event(TEXT("\"op\": \"end\""));
	const TArray<int32>& Only = Passes[PassIndex].Only;
	++SegIndex;
	while (SegIndex < Segments.Num() && !Only.IsEmpty() && !Only.Contains(SegIndex))
	{
		++SegIndex;
	}
	if (SegIndex < Segments.Num())
	{
		StartSegment();
		return;
	}
	if (++PassIndex < Passes.Num())
	{
		StartPass();
		return;
	}
	Finish();
}

FVector UCityGenBench::PointAt(const FCityGenBenchSegment& S, double D) const
{
	const int32 N = S.Points.Num();
	if (D <= 0.0)
	{
		return S.Points[0];
	}
	if (D >= S.Along[N - 1])
	{
		return S.Points[N - 1];
	}
	int32 i = 1;
	while (i < N - 1 && S.Along[i] < D)
	{
		++i;
	}
	const double L = S.Along[i] - S.Along[i - 1];
	const double F = L > 0.0 ? (D - S.Along[i - 1]) / L : 0.0;
	return FMath::Lerp(S.Points[i - 1], S.Points[i], F);
}

void UCityGenBench::Place(const FVector& Eye, double InYaw, double Pitch)
{
	APawn* P = Pawn.Get();
	APlayerController* C = PC.Get();
	if (!P || !C)
	{
		return;
	}
	P->SetActorLocation(Eye - FVector(0.0, 0.0, P->BaseEyeHeight), false, nullptr, ETeleportType::TeleportPhysics);
	C->SetControlRotation(FRotator(Pitch, InYaw, 0.0));
}

bool UCityGenBench::Streamed(const FVector& At, double RadiusCm) const
{
	UWorld* World = GetWorld();
	UWorldPartitionSubsystem* WPS = World ? World->GetSubsystem<UWorldPartitionSubsystem>() : nullptr;
	if (!WPS)
	{
		return true;
	}
	FWorldPartitionStreamingQuerySource Q;
	Q.Location = At;
	Q.Radius = RadiusCm;
	Q.bUseGridLoadingRange = false;
	Q.bSpatialQuery = true;
	Q.bIncludeAnyDataLayer = true;
	return WPS->IsStreamingCompleted(EWorldPartitionRuntimeCellState::Activated, { Q }, false);
}

void UCityGenBench::Record(double Dt, int32 Phase, bool bSampleStream)
{
	const UWorld* World = GetWorld();
	const APawn* P = Pawn.Get();
	const FVector L = P ? P->GetActorLocation() + FVector(0.0, 0.0, P->BaseEyeHeight) : FVector::ZeroVector;
	if (bSampleStream && FrameCount % StreamEvery == 0)
	{
		LastStreamed = Streamed(L, StreamRadiusCm) ? 1 : 0;
	}
	if (const UWorldPartition* WP = World ? World->GetWorldPartition() : nullptr)
	{
		LastPerf = int32(WP->GetStreamingPerformance());
	}
	if (FrameCount % MemoryEvery == 0)
	{
		FRHIMemoryStats Mem;
		RHIGetMemoryStats(Mem);
		LastVramMB = Mem.IsValid() ? double(Mem.UsedLocal) / 1048576.0 : -1.0;
		LastRamMB = double(FPlatformMemory::GetStats().UsedPhysical) / 1048576.0;
		// (dlss_lamps_flicker: with DLSS Frame Generation the frames shown per second and
		// presented per rendered frame, and Reflex's game to render latency; -1 without)
		LastFgHz = -1.f;
		LastFgPresented = 0;
		if (CityGenUpscaler::FrameGenOn())
		{
			CityGenUpscaler::FrameGenTiming(LastFgHz, LastFgPresented);
		}
		LastLatencyMs = CityGenUpscaler::LatencyMs();
	}
	Rows.Add(FString::Printf(TEXT("%d,%d,%d,%.4f,%.3f,%.3f,%.3f,%.3f,%.3f,%d,%d,%d,%d,%.0f,%.0f,%.0f,%.0f,%.0f,%.2f,%d,%.2f"),
		PassIndex, SegIndex, Phase, FPlatformTime::Seconds() - T0, Dt * 1000.0,
		Ms(GGameThreadTime), Ms(GRenderThreadTime), Ms(GRHIThreadTime), Ms(RHIGetGPUFrameCycles(0)),
		GNumDrawCallsRHI[0], GNumPrimitivesDrawnRHI[0], bSampleStream ? LastStreamed : -1, LastPerf,
		LastVramMB, LastRamMB, L.X, L.Y, L.Z, LastFgHz, LastFgPresented, LastLatencyMs));
	++FrameCount;
}

void UCityGenBench::Finish()
{
	Stage = EStage::Done;
	StageStart = FPlatformTime::Seconds();
#if CSV_PROFILER
	if (FCsvProfiler* Csv = FCsvProfiler::Get())
	{
		if (FCsvProfiler::IsCapturing())
		{
			// (the file is written on the profiler's own thread: its future is set once written)
			CsvDone = Csv->EndCapture();
		}
	}
#endif
}

void UCityGenBench::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const double Now = FPlatformTime::Seconds();
	const double Dt = FApp::GetDeltaTime();
	UWorld* World = GetWorld();
	if (!World || bFailed)
	{
		return;
	}
	switch (Stage)
	{
	case EStage::Start:
	{
		if (StageStart == 0.0)
		{
			StageStart = Now;
			if (!ReadJob())
			{
				bFailed = true;
				UE_LOG(LogCityGenBench, Error, TEXT("CITYGEN_BENCH_FAILED %s"), *Error);
				FPlatformMisc::RequestExitWithStatus(false, 3, TEXT("CityGenBench"));
				return;
			}
			UE_LOG(LogCityGenBench, Display, TEXT("CityGen bench: %d passes over %d segments"), Passes.Num(), Segments.Num());
		}
		APlayerController* C = World->GetFirstPlayerController();
		if (!C || !C->GetPawn())
		{
			if (Now - StageStart > PawnWaitS)
			{
				bFailed = true;
				UE_LOG(LogCityGenBench, Error, TEXT("CITYGEN_BENCH_FAILED no player pawn"));
				FPlatformMisc::RequestExitWithStatus(false, 3, TEXT("CityGenBench"));
			}
			return;
		}
		PC = C;
		Pawn = C->GetPawn();
		// (the game's own start: the level's first streaming and shaders)
		if (Now - StageStart < StartWaitS || !Streamed(Pawn->GetActorLocation(), LoadRadiusCm))
		{
			if (Now - StageStart < StartWaitS + LoadTimeoutS)
			{
				return;
			}
		}
		Begin();
		return;
	}
	case EStage::Load:
	case EStage::Settle:
	{
		const FCityGenBenchSegment& S = Segments[SegIndex];
		Record(Dt, 1, false);
		if (Stage == EStage::Load)
		{
			const bool bDone = Now - StageStart > 0.25 && Streamed(S.Points[0], LoadRadiusCm);
			if (bDone || Now - StageStart > LoadTimeoutS)
			{
				Event(FString::Printf(TEXT("\"op\": \"loaded\", \"seconds\": %.3f, \"timeout\": %s"),
					Now - StageStart, bDone ? TEXT("false") : TEXT("true")));
				Stage = EStage::Settle;
				StageStart = Now;
			}
		}
		else if (Now - StageStart >= SettleS)
		{
			if (bShots)
			{
				// (the view as it stands once loaded: the same view before and after a change)
				const FString Shot = FPaths::Combine(OutDir, TEXT("shots"), FString::Printf(TEXT("%s_%s.png"),
					*Passes[PassIndex].Name, *S.Name));
				FScreenshotRequest::RequestScreenshot(Shot, false, false);
				Event(FString::Printf(TEXT("\"op\": \"shot\", \"file\": \"%s\""), *Esc(Shot)));
				// (AT0: atmosgen's runtime state at the shot, if it is in the game)
				if (!Passes[PassIndex].Commands.IsEmpty())
				{
					UE_LOG(LogCityGenBench, Display, TEXT("atmos at %s:"), *FPaths::GetBaseFilename(Shot));
					GEngine->Exec(GetWorld(), TEXT("CityGenAtmos.Status"));
				}
				Stage = EStage::Shot;
				ShotFrames = 0;
				return;
			}
			Event(TEXT("\"op\": \"move\""));
			if (!Passes[PassIndex].Commands.IsEmpty())
			{
				GEngine->Exec(GetWorld(), TEXT("CityGenAtmos.Status"));
			}
			Stage = EStage::Move;
			StageStart = Now;
			bMoveShot = false;
		}
		return;
	}
	case EStage::Shot:
	{
		Record(Dt, 1, false);
		if (++ShotFrames >= 3)
		{
			Event(TEXT("\"op\": \"move\""));
			if (!Passes[PassIndex].Commands.IsEmpty())
			{
				GEngine->Exec(GetWorld(), TEXT("CityGenAtmos.Status"));
			}
			Stage = EStage::Move;
			StageStart = Now;
			bMoveShot = false;
		}
		return;
	}
	case EStage::Move:
	{
		const FCityGenBenchSegment& S = Segments[SegIndex];
		Travelled += S.Speed * Dt;
		const double Total = S.Along.Last();
		const FVector At = PointAt(S, Travelled);
		const FVector Ahead = PointAt(S, Travelled + FMath::Max(S.Speed * LookS, LookMinCm));
		const FVector D = Ahead - At;
		if (D.SizeSquared2D() > 1.0)
		{
			const double Want = FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X));
			const double Delta = FMath::FindDeltaAngleDegrees(Yaw, Want);
			Yaw += Delta * FMath::Min(1.0, Dt * YawRate);
		}
		Place(At, Yaw, S.Pitch);
		Record(Dt, 2, true);
		if (bShots && !bMoveShot && Now - StageStart >= MoveShotS)
		{
			// (dlss_lamps_flicker: the view in motion, where an upscaler's shimmer and ghosting
			// show: the same moment of the route in every pass)
			bMoveShot = true;
			const FString Shot = FPaths::Combine(OutDir, TEXT("shots"), FString::Printf(TEXT("%s_%s_moving.png"),
				*Passes[PassIndex].Name, *S.Name));
			FScreenshotRequest::RequestScreenshot(Shot, false, false);
			Event(FString::Printf(TEXT("\"op\": \"shot\", \"file\": \"%s\", \"moving\": true"), *Esc(Shot)));
		}
		if (Travelled >= Total)
		{
			NextSegment();
		}
		return;
	}
	case EStage::Teleport:
	case EStage::Hold:
	{
		const FCityGenBenchSegment& S = Segments[SegIndex];
		Record(Dt, 3, true);
		if (Stage == EStage::Teleport)
		{
			const bool bDone = Now - StageStart > 0.25 && Streamed(S.Points[0], LoadRadiusCm);
			if (bDone || Now - StageStart > LoadTimeoutS)
			{
				Event(FString::Printf(TEXT("\"op\": \"loaded\", \"seconds\": %.3f, \"timeout\": %s"),
					Now - StageStart, bDone ? TEXT("false") : TEXT("true")));
				Stage = EStage::Hold;
				StageStart = Now;
			}
		}
		else if (Now - StageStart >= S.Hold)
		{
			NextSegment();
		}
		return;
	}
	case EStage::Done:
	{
#if CSV_PROFILER
		if ((FCsvProfiler::IsCapturing() || (CsvDone.IsValid() && !CsvDone.IsReady())) &&
			Now - StageStart < CsvWaitS)
		{
			return;          // (the CSV is written on its own thread once the capture ends)
		}
#endif
		FString Info = TEXT("{\n");
		const FIntPoint Size = (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
			? GEngine->GameViewport->Viewport->GetSizeXY() : FIntPoint::ZeroValue;
		const Scalability::FQualityLevels Q = Scalability::GetQualityLevels();
		Info += FString::Printf(TEXT("  \"viewport\": [%d, %d],\n"), Size.X, Size.Y);
		Info += FString::Printf(TEXT("  \"adapter\": \"%s\",\n"), *Esc(GRHIAdapterName));
		Info += FString::Printf(TEXT("  \"rhi\": \"%s\",\n"), GDynamicRHI ? GDynamicRHI->GetName() : TEXT(""));
		Info += FString::Printf(TEXT("  \"nanite_max_root_pages\": %u,\n"), Nanite::GStreamingManager.GetMaxRootPages());
		Info += FString::Printf(TEXT("  \"nanite_max_streaming_pages\": %u,\n"), Nanite::GStreamingManager.GetMaxStreamingPages());
		Info += FString::Printf(TEXT("  \"scalability\": {\"resolution\": %.1f, \"view_distance\": %d, \"anti_aliasing\": %d, \"shadow\": %d, \"global_illumination\": %d, \"reflection\": %d, \"post_process\": %d, \"texture\": %d, \"effects\": %d, \"foliage\": %d, \"shading\": %d},\n"),
			Q.ResolutionQuality, Q.ViewDistanceQuality, Q.AntiAliasingQuality, Q.ShadowQuality,
			Q.GlobalIlluminationQuality, Q.ReflectionQuality, Q.PostProcessQuality, Q.TextureQuality,
			Q.EffectsQuality, Q.FoliageQuality, Q.ShadingQuality);
		Info += FString::Printf(TEXT("  \"frames\": %lld,\n  \"seconds\": %.2f,\n"), FrameCount, Now - T0);
		Info += TEXT("  \"events\": [\n    ") + FString::Join(Events, TEXT(",\n    ")) + TEXT("\n  ]\n}\n");
		FFileHelper::SaveStringToFile(Info, *FPaths::Combine(OutDir, TEXT("bench_events.json")),
			FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		FFileHelper::SaveStringToFile(FString::Join(Rows, TEXT("\n")) + TEXT("\n"),
			*FPaths::Combine(OutDir, TEXT("frames.csv")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		UE_LOG(LogCityGenBench, Display, TEXT("CITYGEN_BENCH_DONE %lld frames"), FrameCount);
		bFailed = true;      // (nothing more to do)
		FPlatformMisc::RequestExit(false, TEXT("CityGenBench"));
		return;
	}
	default:
		return;
	}
}
