// lifegen's city traffic (LG5): see CityGenLifeActor.h ("LG5: the city's traffic") and
// docs/unreal_export.md ("From LG5: traffic").
//
// The whole lane graph is ZoneGraph lanes; only the drive lanes within TrafficLiveM of the view
// are live. Every LiveStep s (UpdateTraffic) the live set is measured again: a lane coming
// alive (at TrafficLiveM, where cars are specks) gets its cars at the hour (the plan's cars per
// band times its district's day) times the scale that keeps the live cars within the pool; a
// lane going (past TrafficLiveM and a margin) loses its cars; a car driving onto a lane that is
// not live leaves there. Lanes far from the view (past TrafficRefillM) take new cars while the
// live cars are under their number. Every car is a slot of a fixed pool (Mass entities made
// once, each slot a model of AG18's fleet): no entity is made or destroyed while the game runs.
//
// Each frame the drive processor (ExecuteTraffic) moves every live car by the intelligent driver
// model against the nearest of: the car in front (on its lane, its next lane, the one after),
// its signal's stop line on red or amber, the end of its lane while a connector of the junction
// ahead that crosses its own is being driven or there is no room past the junction, and anyone
// (the crowd's people, the player) on its line ahead.

#include "CityGenLifeActor.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "CityGenLifeProcessors.h"
#include "CityGenLifeTypes.h"
#include "Algo/Sort.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "Misc/ScopeExit.h"
#include "MassEntityManager.h"
#include "MassEntitySubsystem.h"
#include "MassExecutionContext.h"
#include "ZoneGraphData.h"
#include "ZoneGraphQuery.h"
#include "ZoneGraphTypes.h"

namespace
{
	constexpr float LiveStep = 0.25f;      // s between live updates
	constexpr float PoolFill = 0.92f;      // the live cars at most this share of the pool
	constexpr float SpawnGapCm = 600.f;    // a new car this far clear of another (plus lengths)
	constexpr float FarCm = 25000.f;       // cars past this from the view step every second frame
	constexpr float FarterCm = 55000.f;    // (LG8) and past this every fourth
	constexpr float BodyNearCm = 30000.f;  // (LG8) a model's bodies sent every frame while one within this moved
	constexpr float CellCm = 800.f;        // the people's cells for the cars' look ahead

	int32 BandOf(const int32 Hour)
	{
		const int32 H = ((Hour % 24) + 24) % 24;
		return H < 6 ? 0 : (H < 10 ? 1 : (H < 16 ? 2 : (H < 20 ? 3 : 4)));
	}

	uint32 Rand(uint32& Seed)
	{
		Seed = Seed * 1664525u + 1013904223u;
		return Seed >> 8;
	}

	uint32 MixU(uint32 X)
	{
		X ^= X >> 16; X *= 0x7feb352du; X ^= X >> 15; X *= 0x846ca68bu; X ^= X >> 16;
		return X;
	}

	int64 CellOf(const double X, const double Y)
	{
		return (int64(FMath::FloorToInt64(X / CellCm)) << 32) ^ (int64)(uint32)FMath::FloorToInt64(Y / CellCm);
	}

	/** A random successor of a lane on the lane graph's main part, INDEX_NONE without one. */
	int32 PickMain(const FZoneGraphStorage& S, const TArray<uint8>& Main, const int32 Lane, uint32& Seed)
	{
		if (!S.Lanes.IsValidIndex(Lane))
		{
			return INDEX_NONE;
		}
		const FZoneLaneData& L = S.Lanes[Lane];
		int32 Cands[24];
		int32 N = 0;
		for (int32 K = L.LinksBegin; K < L.LinksEnd && N < 24; ++K)
		{
			const FZoneLaneLinkData& Link = S.LaneLinks[K];
			if (Link.Type == EZoneLaneLinkType::Outgoing && Main.IsValidIndex(Link.DestLaneIndex) && Main[Link.DestLaneIndex])
			{
				Cands[N++] = Link.DestLaneIndex;
			}
		}
		return N ? Cands[Rand(Seed) % N] : INDEX_NONE;
	}

	/** The lowest point speed (cm/s) from `Dist` along a lane to `Look` cm on (cars_steam's). */
	float SpeedOn(const FZoneGraphStorage& S, const TArray<float>* V, const int32 Lane, const float Dist, const float Look)
	{
		if (!V)
		{
			return 900.f;
		}
		const FZoneLaneData& L = S.Lanes[Lane];
		float Out = 1e9f;
		for (int32 P = L.PointsBegin; P < L.PointsEnd; ++P)
		{
			const float Prog = S.LanePointProgressions[P];
			if (P + 1 < L.PointsEnd && S.LanePointProgressions[P + 1] < Dist)
			{
				continue;
			}
			if (Prog > Dist + Look)
			{
				break;
			}
			if (V->IsValidIndex(P) && (*V)[P] > 0.f)
			{
				Out = FMath::Min(Out, (*V)[P]);
			}
		}
		return Out < 1e8f ? Out : 900.f;
	}

	/** A signal window's state now: 0 green, 1 amber, 2 red. */
	int32 SignalState(const TArray<float>& W, const int32 Sig, const double Time)
	{
		if (!W.IsValidIndex(5 * Sig + 4))
		{
			return 0;
		}
		const double Cycle = FMath::Max(1.0, (double)W[5 * Sig]);
		const float T = (float)FMath::Fmod(Time + (double)W[5 * Sig + 1] + 1000.0 * Cycle, Cycle);
		if (T >= W[5 * Sig + 2] && T < W[5 * Sig + 3])
		{
			return 0;
		}
		return (T >= W[5 * Sig + 3] && T < W[5 * Sig + 4]) ? 1 : 2;
	}

	FVector Ue(const float X, const float Y, const float Z)
	{
		return FVector(X * 100.0, -Y * 100.0, Z * 100.0);
	}

	struct FCellItem
	{
		int64 Cell;
		int32 Ped;
	};
}

// --- the actor: the pool, the live lanes ---------------------------------------------------------

void ACityGenLife::BuildTraffic()
{
	const FZoneGraphStorage& S = Lanes->GetStorage();
	const int32 N = WalkLaneCount + DriveLaneCount;
	DriveMainG.Init(0, N);
	DriveIsConnector.Init(0, N);
	DriveSignalG.Init(INDEX_NONE, N);
	DriveStopBackG.Init(0.f, N);
	ConflictStartsG.Init(0, N + 1);
	ConflictsG.Reset();
	DriveMid.SetNum(DriveLaneCount);
	DriveHalf.SetNumZeroed(DriveLaneCount);
	const int32 NumWindows = DriveWindows.Num() / 5;
	for (int32 G = 0; G < N; ++G)
	{
		const int32 J = G - WalkLaneCount;
		if (J >= 0)
		{
			DriveMainG[G] = DriveMain.IsValidIndex(J) ? DriveMain[J] : 1;
			DriveIsConnector[G] = DriveStartable.IsValidIndex(J) ? (DriveStartable[J] ? 0 : 1) : 0;
			const int32 Sg = DriveSignal.IsValidIndex(J) ? DriveSignal[J] : INDEX_NONE;
			if (Sg >= 0 && Sg < NumWindows)
			{
				DriveSignalG[G] = Sg;
				DriveStopBackG[G] = 100.f * (DriveStopBack.IsValidIndex(J) ? DriveStopBack[J] : 1.f);
			}
			const int32 A = DriveConflictStarts.IsValidIndex(J) ? DriveConflictStarts[J] : 0;
			const int32 B = DriveConflictStarts.IsValidIndex(J + 1) ? DriveConflictStarts[J + 1] : A;
			for (int32 K = A; K < B && DriveConflicts.IsValidIndex(K); ++K)
			{
				const int32 To = DriveConflicts[K];
				if (To >= 0 && To < DriveLaneCount && To != J)
				{
					ConflictsG.Add(WalkLaneCount + To);
				}
			}
			const FZoneLaneData& L = S.Lanes[G];
			FBox Box(ForceInit);
			for (int32 P = L.PointsBegin; P < L.PointsEnd; ++P)
			{
				Box += S.LanePoints[P];
			}
			DriveMid[J] = Box.GetCenter();
			DriveHalf[J] = (float)Box.GetExtent().Size();
			InRegion[G] = 0;
		}
		ConflictStartsG[G + 1] = ConflictsG.Num();
	}
	Frame.bTraffic = true;
	Frame.DriveMain = &DriveMainG;
	Frame.IsConnector = &DriveIsConnector;
	Frame.DriveSignal = &DriveSignalG;
	Frame.DriveStopBack = &DriveStopBackG;
	Frame.DriveWindows = &DriveWindows;
	Frame.ConflictStarts = &ConflictStartsG;
	Frame.Conflicts = &ConflictsG;
	Frame.CarShow = &CarShow;
	Frame.CarSpin = &CarSpin;
	Frame.CarFreed = &CarFreed;
	Frame.WalkState = &WalkState;
	Frame.Accel = 100.f * TrafficAccel;
	Frame.Brake = 100.f * TrafficBrake;
	Frame.BrakeMax = 100.f * TrafficBrakeMax;
	Frame.GapCm = 100.f * TrafficGapM;
	Frame.Headway = TrafficHeadwayS;
	Frame.Delta = TrafficDelta;
	Frame.AmberBrake = 100.f * AmberBrake;
	Frame.StarveS = StarveS;
	Frame.ForceS = ForceS;
	Frame.YieldCm = 100.f * YieldM;
	Frame.LookS = LookS;
	Frame.LookMinCm = 100.f * LookMinM;
	Frame.LookMaxCm = 100.f * LookMaxM;
	Frame.LatCm = 100.f * LateralM;
	Frame.PredictS = PredictS;
	Frame.MarginCm = 100.f * YieldMarginM;
}

float ACityGenLife::TrafficWant(const int32 J) const
{
	const int32 B = BandOf(Hour);
	const int32 D = DriveDistrict.IsValidIndex(J) ? DriveDistrict[J] : INDEX_NONE;
	const int32 H = ((Hour % 24) + 24) % 24;
	const float Shape = (D >= 0 && DistrictShape.IsValidIndex(24 * D + H)) ? DistrictShape[24 * D + H] : 1.f;
	// (LG8: the weather's share of the cars)
	return DriveCars.IsValidIndex(5 * J + B) ? DriveCars[5 * J + B] * Shape * TrafficScale * CarsNow : 0.f;
}

void ACityGenLife::SpawnCarPool()
{
	UMassEntitySubsystem* Sub = GetWorld()->GetSubsystem<UMassEntitySubsystem>();
	FMassEntityManager& EM = Sub->GetMutableEntityManager();
	int32 Models = 0;
	for (const int32 M : CarPartModels)
	{
		Models = FMath::Max(Models, M + 1);
	}
	const int32 NC = Models > 0 ? FMath::Clamp(TrafficPool, 0, TrafficSlots.Num()) : 0;
	ModelSlots.Reset();
	ModelSlots.SetNum(Models);
	PartsOfModel.Reset();
	PartsOfModel.SetNum(Models);
	for (int32 P = 0; P < CarPartModels.Num(); ++P)
	{
		if (CarPartModels[P] >= 0 && CarPartModels[P] < Models)
		{
			PartsOfModel[CarPartModels[P]].Add(P);
		}
	}
	CarSlotModel.SetNumZeroed(NC);
	CarInstance.SetNumZeroed(NC);
	CarModelCount.Init(0, Models);
	for (int32 K = 0; K < NC; ++K)
	{
		const int32 M = FMath::Clamp(TrafficSlots[K], 0, Models - 1);
		CarSlotModel[K] = M;
		CarInstance[K] = ModelSlots[M].Num();
		ModelSlots[M].Add(K);
		CarModelCount[M] = ModelSlots[M].Num();
	}
	FreeByModel.Reset();
	FreeByModel.SetNum(Models);
	// (LG4: the slots kept for patrol cars in a list of their own)
	CarIsPolice.Init(0, NC);
	FreePoliceCars.Reset();
	PoliceCarsActive = 0;
	for (int32 M = 0; M < Models; ++M)
	{
		for (int32 I = ModelSlots[M].Num() - 1; I >= 0; --I)
		{
			const int32 Slot = ModelSlots[M][I];
			if (TrafficPolice.IsValidIndex(Slot) && TrafficPolice[Slot] && PolicePaint.Num() >= PaintFloats)
			{
				CarIsPolice[Slot] = 1;
				FreePoliceCars.Add(Slot);
				continue;
			}
			FreeByModel[M].Add(Slot);
		}
	}
	PoliceCarPoolN = FreePoliceCars.Num();
	CarPos.Init(FVector::ZeroVector, NC);
	CarYaw.SetNumZeroed(NC);
	CarShow.Init(0, NC);
	CarSpin.SetNumZeroed(NC);
	CarDistrict.Init(INDEX_NONE, NC);
	CarFreed.Reset();
	CarOf.Reset();
	CarEnts.Reset();
	PartShown.Reset();
	if (NC)
	{
		const FMassArchetypeHandle Arch = EM.CreateArchetype({FCgLifeCar::StaticStruct()});
		EM.BatchCreateEntities(Arch, NC, CarEnts);
		for (int32 K = 0; K < CarEnts.Num(); ++K)
		{
			FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[K]);
			C = FCgLifeCar();
			C.Active = 0;
			C.Index = K;
			C.Model = CarSlotModel[K];
			C.Instance = CarInstance[K];
			C.Len = 100.f * (CarLengths.IsValidIndex(C.Model) ? CarLengths[C.Model] : 4.8f);
		}
		Entities.Append(CarEnts);
	}
	// (every slot an instance of its model's parts, drawn at no size until it drives)
	for (int32 P = 0; P < CarParts.Num(); ++P)
	{
		UInstancedStaticMeshComponent* Comp = CarParts[P];
		if (!Comp)
		{
			continue;
		}
		Comp->ClearInstances();
		const int32 M = CarPartModels.IsValidIndex(P) ? CarPartModels[P] : 0;
		const int32 Count = CarModelCount.IsValidIndex(M) ? CarModelCount[M] : 0;
		Scratch.Init(FTransform(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector), Count);
		Comp->AddInstances(Scratch, false, true, false);
		Comp->MarkRenderStateDirty();
	}
	CarsActive = 0;
	TrafficRng.Initialize((int32)(MixU(GetTypeHash(City) ^ GetTypeHash(PlanHash) ^ 0x5eedu) & 0x7fffffff));
	// (half a step after the crowd's live update, never on the same frame: each is a frame
	// longer than the rest, every 15th or so, which a 95th percentile sees)
	TrafficClock = 0.5f * LiveStep;
	LastTrafficView = FVector(1.0e12);
	RefillAcc = 0.f;
	for (int32 J = 0; J < DriveLaneCount; ++J)
	{
		InRegion[WalkLaneCount + J] = 0;
	}
}

void ACityGenLife::FreeCar(const int32 Slot, FCgLifeCar& C)
{
	C.Active = 0;
	C.Reserved = INDEX_NONE;
	C.Wait = 0.f;
	if (CarShow.IsValidIndex(Slot))
	{
		CarShow[Slot] = 0;
		CarPos[Slot] = FVector::ZeroVector;
	}
	if (CarIsPolice.IsValidIndex(Slot) && CarIsPolice[Slot])
	{
		FreePoliceCars.Add(Slot);
		--PoliceCarsActive;
	}
	else if (FreeByModel.IsValidIndex(C.Model))
	{
		FreeByModel[C.Model].Add(Slot);
	}
	--CarsActive;
}

bool ACityGenLife::SpawnCar(const int32 G, float Dist, FRandomStream& Rng, const bool bPoliceCar)
{
	const int32 J = G - WalkLaneCount;
	if (J < 0 || J >= DriveLaneCount || !DriveMainG[G] || DriveIsConnector[G] || CarEnts.Num() == 0)
	{
		return false;
	}
	// (its model by its district's fleet, among the models with a free slot)
	const int32 Models = FreeByModel.Num();
	const int32 D = DriveDistrict.IsValidIndex(J) ? DriveDistrict[J] : INDEX_NONE;
	float Tot = 0.f;
	for (int32 M = 0; M < Models && !bPoliceCar; ++M)
	{
		const float W = (D >= 0 && TrafficWeights.IsValidIndex(D * Models + M)) ? TrafficWeights[D * Models + M] : 1.f;
		Tot += FreeByModel[M].Num() ? W : 0.f;
	}
	int32 Model = INDEX_NONE;
	int32 PoliceSlot = INDEX_NONE;
	if (bPoliceCar)
	{
		// (LG4: a patrol car: one of the slots kept for them, its model the plan's)
		if (!FreePoliceCars.Num())
		{
			return false;
		}
		PoliceSlot = FreePoliceCars.Pop(EAllowShrinking::No);
		Model = CarSlotModel[PoliceSlot];
	}
	else if (Tot > 0.f)
	{
		float X = Rng.FRand() * Tot;
		for (int32 M = 0; M < Models; ++M)
		{
			const float W = (D >= 0 && TrafficWeights.IsValidIndex(D * Models + M)) ? TrafficWeights[D * Models + M] : 1.f;
			if (!FreeByModel[M].Num())
			{
				continue;
			}
			Model = M;
			X -= W;
			if (X < 0.f)
			{
				break;
			}
		}
	}
	else
	{
		int32 Most = 0;
		for (int32 M = 0; M < Models; ++M)
		{
			if (FreeByModel[M].Num() > Most)
			{
				Most = FreeByModel[M].Num();
				Model = M;
			}
		}
	}
	if (Model == INDEX_NONE)
	{
		return false;
	}
	const int32 Slot = PoliceSlot != INDEX_NONE ? PoliceSlot : FreeByModel[Model].Pop(EAllowShrinking::No);
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
	const FZoneGraphStorage& S = *Frame.Storage;
	C = FCgLifeCar();
	C.Active = 1;
	C.Index = Slot;
	C.Model = Model;
	C.Instance = CarInstance[Slot];
	C.Len = 100.f * (CarLengths.IsValidIndex(Model) ? CarLengths[Model] : 4.8f);
	C.Lane = G;
	C.Dist = FMath::Clamp(Dist, 0.f, Lengths[G]);
	C.Seed = Rng.GetUnsignedInt() | 1u;
	C.Share = FMath::Lerp((float)DriveVary.X, (float)DriveVary.Y, Rng.FRand());
	C.Speed = 0.7f * C.Share * SpeedOn(S, Frame.PointVmax, G, C.Dist, 600.f);
	C.Next = PickMain(S, DriveMainG, G, C.Seed);
	C.Next2 = C.Next != INDEX_NONE ? PickMain(S, DriveMainG, C.Next, C.Seed) : INDEX_NONE;
	CarDistrict[Slot] = D;
	CarShow[Slot] = 0;
	CarPos[Slot] = FVector::ZeroVector;
	// (its paint: one of its district's for its model, as AG18's step H paints a parked car)
	const int32 K = FMath::Max(1, PaintsPer);
	const int32 Pk = (int32)(Rng.FRand() * K) % K;
	const int32 At = (((FMath::Max(0, D) * Models + Model) * K) + Pk) * PaintFloats;
	const float* Paint = PoliceSlot != INDEX_NONE ? PolicePaint.GetData() :
		((D >= 0 && TrafficPaints.IsValidIndex(At + PaintFloats - 1)) ? &TrafficPaints[At] : nullptr);
	if (Paint && PartsOfModel.IsValidIndex(Model))
	{
		for (const int32 P : PartsOfModel[Model])
		{
			if (CarParts.IsValidIndex(P) && CarParts[P])
			{
				CarParts[P]->SetCustomData(C.Instance, MakeArrayView(Paint, PaintFloats), false);
			}
		}
	}
	PoliceCarsActive += PoliceSlot != INDEX_NONE ? 1 : 0;
	++CarsActive;
	++CarsSpawned;
	return true;
}

void ACityGenLife::FreeCarsOnDeadLanes()
{
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	for (int32 Slot = 0; Slot < CarEnts.Num(); ++Slot)
	{
		FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
		if (!C.Active || (InRegion.IsValidIndex(C.Lane) && InRegion[C.Lane]))
		{
			continue;
		}
		FreeCar(Slot, C);
		++CarsLost;
	}
}

void ACityGenLife::TakeFreedCars()
{
	for (const int32 Slot : CarFreed)
	{
		if (CarShow.IsValidIndex(Slot))
		{
			CarShow[Slot] = 0;
			CarPos[Slot] = FVector::ZeroVector;
		}
		const int32 M = CarSlotModel.IsValidIndex(Slot) ? CarSlotModel[Slot] : 0;
		if (CarIsPolice.IsValidIndex(Slot) && CarIsPolice[Slot])
		{
			FreePoliceCars.Add(Slot);
			--PoliceCarsActive;
		}
		else if (FreeByModel.IsValidIndex(M))
		{
			FreeByModel[M].Add(Slot);
		}
		--CarsActive;
		++CarsLeftTotal;
	}
	CarFreed.Reset();
	for (int32 K = 0; K < 7; ++K)
	{
		CarsWhyNow[K] = Frame.CarsWhy[K];
	}
	CarsMovingNow = Frame.CarsMoving;
	CarsForcedTotal += Frame.CarsForced;
	CarsStuckTotal += Frame.CarsStuck;
	TrafficMs = TrafficMs > 0.0 ? 0.95 * TrafficMs + 0.05 * Frame.TrafficMs : Frame.TrafficMs;
	TrafficMsMax = FMath::Max(TrafficMsMax * 0.999, Frame.TrafficMs);
}

void ACityGenLife::UpdateTraffic(const float Dt, const bool bRefill)
{
	TRACE_CPUPROFILER_EVENT_SCOPE(CityGenLife_UpdateTraffic);
	const double T0 = FPlatformTime::Seconds();
	ON_SCOPE_EXIT
	{
		const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
		LiveMsMax = FMath::Max(LiveMsMax * 0.99, Ms);
		LiveMs = LiveMs > 0.0 ? 0.9 * LiveMs + 0.1 * Ms : Ms;
	};
	FVector View;
	if (!ViewPoint(View))
	{
		View = Ue(Center.X, Center.Y, 0.f);
	}
	LastTrafficView = View;
	const double In = 100.0 * TrafficLiveM;
	const double Out = 100.0 * (TrafficLiveM + TrafficMarginM);
	TArray<int32> Born;
	bool bDied = false;
	TrafficWantLive = 0.f;
	TrafficLiveLanes = 0;
	// (LG4: the patrol cars a live lane wants: the plan's by band, its district's day)
	WantPoliceCars = 0.f;
	auto PoliceWant = [this](const int32 J)
	{
		if (!bPolice || !IsPlaces() || PoliceCarPoolN == 0 || !DrivePolice.IsValidIndex(5 * J + 4))
		{
			return 0.f;
		}
		const int32 B = BandOf(Hour);
		const int32 D = DriveDistrict.IsValidIndex(J) ? DriveDistrict[J] : INDEX_NONE;
		const int32 H = ((Hour % 24) + 24) % 24;
		const float Shape = (D >= 0 && DistrictShape.IsValidIndex(24 * D + H)) ? DistrictShape[24 * D + H] : 1.f;
		return DrivePolice[5 * J + B] * Shape;
	};
	for (int32 J = 0; J < DriveLaneCount; ++J)
	{
		const int32 G = WalkLaneCount + J;
		if (!DriveMainG[G])
		{
			continue;
		}
		const double D = FMath::Max(0.0, FVector::Dist(DriveMid[J], View) - DriveHalf[J]);
		const bool bWas = InRegion[G] != 0;
		const bool bLive = bRefill ? D < In : (bWas ? D < Out : D < In);
		if (bLive != bWas || bRefill)
		{
			InRegion[G] = bLive ? 1 : 0;
			if (bLive)
			{
				Born.Add(J);
			}
			else if (bWas)
			{
				bDied = true;
			}
		}
		if (bLive)
		{
			TrafficWantLive += TrafficWant(J);
			WantPoliceCars += PoliceWant(J);
			++TrafficLiveLanes;
		}
	}
	TrafficLiveScale = TrafficWantLive > 0.f ? FMath::Min(1.f, PoolFill * (float)(CarEnts.Num() - PoliceCarPoolN) / TrafficWantLive) : 1.f;
	PoliceCarScaleNow = WantPoliceCars > 0.f ? FMath::Min(1.f, PoolFill * (float)PoliceCarPoolN / WantPoliceCars) : 1.f;
	if (bRefill || bDied)
	{
		FreeCarsOnDeadLanes();
	}
	if (bRefill)
	{
		// (everyone out, every live lane filled again: the hour, the scale or the view jumped)
		FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
		for (int32 Slot = 0; Slot < CarEnts.Num(); ++Slot)
		{
			FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
			if (C.Active)
			{
				FreeCar(Slot, C);
			}
		}
	}
	// (where the live cars are on the lanes cars may come out on now, so a new car keeps clear
	// of them: only those lanes, gathered once)
	const float Target = FMath::Min(TrafficWantLive, PoolFill * (float)CarEnts.Num());
	const bool bRefillNow = (float)CarsActive < 0.97f * Target && Dt > 0.f;
	TMultiMap<int32, float> Taken;
	if (Born.Num() || bRefillNow)
	{
		FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
		for (int32 Slot = 0; Slot < CarEnts.Num(); ++Slot)
		{
			if (!CarShow.IsValidIndex(Slot) || !CarShow[Slot])
			{
				continue;
			}
			const FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
			if (C.Active)
			{
				Taken.Add(C.Lane, C.Dist);
			}
		}
	}
	auto Clear = [&](const int32 G, const float Dist)
	{
		TArray<float> Ds;
		Taken.MultiFind(G, Ds);
		for (const float D : Ds)
		{
			if (FMath::Abs(D - Dist) < SpawnGapCm + 700.f)
			{
				return false;
			}
		}
		return true;
	};
	auto Place = [&](const int32 G, const bool bCop = false)
	{
		for (int32 Try = 0; Try < 4; ++Try)
		{
			const float Dist = TrafficRng.FRand() * Lengths[G];
			if (Clear(G, Dist))
			{
				if (SpawnCar(G, Dist, TrafficRng, bCop))
				{
					Taken.Add(G, Dist);
					return true;
				}
				return false;
			}
		}
		return false;
	};
	for (const int32 J : Born)
	{
		const int32 G = WalkLaneCount + J;
		if (DriveIsConnector[G])
		{
			continue;
		}
		const float N = TrafficWant(J) * TrafficLiveScale;
		int32 Count = (int32)N + (TrafficRng.FRand() < N - FMath::FloorToFloat(N) ? 1 : 0);
		for (; Count > 0; --Count)
		{
			Place(G);
		}
		// (LG4: its patrol cars)
		const float NP = PoliceWant(J) * PoliceCarScaleNow;
		for (int32 Cops = (int32)NP + (TrafficRng.FRand() < NP - FMath::FloorToFloat(NP) ? 1 : 0); Cops > 0; --Cops)
		{
			Place(G, true);
		}
	}
	// (LG4: patrol cars that drove out made up for on the lanes far from the view, by their want)
	const float PoliceTarget = WantPoliceCars * PoliceCarScaleNow;
	if (Dt > 0.f && (float)PoliceCarsActive < 0.97f * PoliceTarget && FreePoliceCars.Num())
	{
		PoliceRefillAcc += (PoliceTarget - (float)PoliceCarsActive) * Dt / 4.f;
		if (PoliceRefillAcc >= 1.f)
		{
			TArray<int32> Cands;
			TArray<float> Cum;
			float Tot = 0.f;
			for (int32 J = 0; J < DriveLaneCount; ++J)
			{
				const int32 G = WalkLaneCount + J;
				const float W = InRegion[G] && !DriveIsConnector[G] ? PoliceWant(J) : 0.f;
				if (W > 0.f && FVector::Dist(DriveMid[J], View) - DriveHalf[J] > 100.f * TrafficRefillM)
				{
					Tot += W;
					Cands.Add(G);
					Cum.Add(Tot);
				}
			}
			for (int32 Guard = 0; Guard < 8 && PoliceRefillAcc >= 1.f && Cands.Num(); ++Guard)
			{
				const float X = TrafficRng.FRand() * Tot;
				int32 Lo = 0, Hi = Cum.Num() - 1;
				while (Lo < Hi)
				{
					const int32 M = (Lo + Hi) / 2;
					if (Cum[M] < X) { Lo = M + 1; } else { Hi = M; }
				}
				PoliceRefillAcc -= 1.f;
				Place(Cands[Lo], true);
			}
		}
	}
	else
	{
		PoliceRefillAcc = 0.f;
	}
	// (the cars that drove out of the live region made up for on the lanes far from the view,
	// by their want)
	if (bRefillNow)
	{
		RefillAcc += (Target - (float)CarsActive) * Dt / 4.f;
		if (RefillAcc >= 1.f)
		{
			TArray<int32> Cands;
			TArray<float> Cum;
			float Tot = 0.f;
			for (float Reach = 100.f * TrafficRefillM; Reach > 1000.f && Cands.Num() == 0; Reach *= 0.5f)
			{
				for (int32 J = 0; J < DriveLaneCount; ++J)
				{
					const int32 G = WalkLaneCount + J;
					if (!InRegion[G] || DriveIsConnector[G])
					{
						continue;
					}
					const float W = TrafficWant(J);
					if (W > 0.f && FVector::Dist(DriveMid[J], View) - DriveHalf[J] > Reach)
					{
						Tot += W;
						Cands.Add(G);
						Cum.Add(Tot);
					}
				}
			}
			for (int32 Guard = 0; Guard < 64 && RefillAcc >= 1.f && Cands.Num(); ++Guard)
			{
				const float X = TrafficRng.FRand() * Tot;
				int32 Lo = 0, Hi = Cum.Num() - 1;
				while (Lo < Hi)
				{
					const int32 M = (Lo + Hi) / 2;
					if (Cum[M] < X) { Lo = M + 1; } else { Hi = M; }
				}
				RefillAcc -= 1.f;
				if (Place(Cands[Lo]))
				{
					++CarsRefilled;
				}
			}
		}
	}
	else
	{
		RefillAcc = 0.f;
	}
}

void ACityGenLife::GatherPlayers()
{
	// (every pawn but the free camera: the walker, a fly pawn; the cars stop for it when it is
	// at their height, so a fly pawn high up is passed under)
	Frame.Players.Reset();
	for (TActorIterator<APawn> It(GetWorld()); It; ++It)
	{
		const APawn* P = *It;
		if (!P || P->GetClass()->GetName().Contains(TEXT("FreeCam")))
		{
			continue;
		}
		Frame.Players.Add(P->GetActorLocation());
	}
}

void ACityGenLife::UpdateCarInstances()
{
	TRACE_CPUPROFILER_EVENT_SCOPE(CityGenLife_UpdateCarInstances);
	// (the engine's cost is in the instances sent each frame: a part drawn as far as the cars
	// live (a body) is sent over its model's instances in use, the lowest first (a free slot is
	// taken lowest first); a part drawn nearer (glass, wheels, trims) only for the cars within
	// its draw distance, each one by itself, and hidden once as its car leaves that distance)
	const double T0 = FPlatformTime::Seconds();
	const FTransform Hidden(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector);
	const FVector View = Frame.View;
	if (PartShown.Num() != CarParts.Num())
	{
		PartShown.SetNum(CarParts.Num());
		for (int32 P = 0; P < CarParts.Num(); ++P)
		{
			const int32 M = CarPartModels.IsValidIndex(P) ? CarPartModels[P] : 0;
			PartShown[P].Init(0, ModelSlots.IsValidIndex(M) ? ModelSlots[M].Num() : 0);
		}
	}
	int32 Sent = 0;
	for (int32 P = 0; P < CarParts.Num(); ++P)
	{
		UInstancedStaticMeshComponent* Comp = CarParts[P];
		const int32 M = CarPartModels.IsValidIndex(P) ? CarPartModels[P] : 0;
		if (!Comp || !ModelSlots.IsValidIndex(M) || ModelSlots[M].Num() == 0)
		{
			continue;
		}
		const FVector Pivot = CarPartPivots.Num() >= 3 * (P + 1) ? Ue(CarPartPivots[3 * P], CarPartPivots[3 * P + 1], CarPartPivots[3 * P + 2]) : FVector::ZeroVector;
		const float R = CarPartSpin.IsValidIndex(P) ? 100.f * CarPartSpin[P] : 0.f;
		const float Cull = CarPartCull.IsValidIndex(P) ? 100.f * CarPartCull[P] : 0.f;
		const bool bNear = Cull > 0.f && Cull < 100.f * TrafficLiveM;
		const double Reach2 = FMath::Square((double)Cull + 3000.0);
		// (car_merge: a merged car's wheels roll by its travel, sent with its transform within
		// RollCm of the view; past it they stand still, too small to see turn. The travel wraps
		// at 64 turns of the model's wheel, which the material turns them by: no jump)
		const float RollCm = CarPartRoll.IsValidIndex(P) ? 100.f * CarPartRoll[P] : 0.f;
		const bool bRoll = RollCm > 0.f && R > 1.f && Comp->NumCustomDataFloats > PaintFloats;
		const double Roll2 = FMath::Square((double)RollCm);
		const float Wrap = 64.f * 2.f * UE_PI * R;
		const TArray<int32>& Slots = ModelSlots[M];
		TArray<uint8>& Shown = PartShown[P];
		auto Of = [&](const int32 Slot)
		{
			const FTransform Car(FRotator(0.f, CarYaw[Slot], 0.f), CarPos[Slot]);
			// (a wheel rolls: its turn the car's travel over its radius)
			const FTransform Local = (R > 1.f && RollCm <= 0.f) ? FTransform(FRotator(-FMath::RadiansToDegrees(FMath::Fmod(CarSpin[Slot] / R, 2.0 * UE_PI)), 0.f, 0.f), Pivot) : FTransform(Pivot);
			return Local * Car;
		};
		if (bNear)
		{
			int32 On = 0;
			for (const int32 Slot : Slots)
			{
				const int32 I = CarInstance[Slot];
				const bool bOn = bTraffic && CarShow[Slot] && FVector::DistSquared(CarPos[Slot], View) < Reach2;
				if (bOn)
				{
					Comp->UpdateInstanceTransform(I, Of(Slot), false, bRebuildRenderState, false);
					Shown[I] = 1;
					++Sent;
					++On;
				}
				else if (Shown[I])
				{
					Comp->UpdateInstanceTransform(I, Hidden, false, bRebuildRenderState, false);
					Shown[I] = 0;
					++Sent;
				}
			}
			// (a part with no car near enough to draw it is not drawn at all: no draw calls)
			const bool bVis = On > 0 && bEnabled;
			if (Comp->IsVisible() != bVis)
			{
				Comp->SetVisibility(bVis);
			}
			continue;
		}
		int32 Hi = 0;
		bool bNearCar = false;
		for (const int32 Slot : Slots)
		{
			const int32 I = CarInstance[Slot];
			if ((bTraffic && CarShow[Slot]) || Shown[I])
			{
				Hi = FMath::Max(Hi, I + 1);
				bNearCar |= bTraffic && CarShow[Slot] && FVector::DistSquared(CarPos[Slot], View) < FMath::Square((double)BodyNearCm);
			}
		}
		if (Hi == 0)
		{
			continue;
		}
		// (LG8's performance pass: a model's bodies with none of its cars within 300 m are sent
		// every third frame, the models taking turns: the engine's cost is per component sent,
		// and those cars move a step every second or fourth frame anyway)
		if (!bNearCar && ((CarFrame + P) % 3) != 0)
		{
			continue;
		}
		Scratch.SetNum(Hi);
		for (const int32 Slot : Slots)
		{
			const int32 I = CarInstance[Slot];
			if (I >= Hi)
			{
				continue;
			}
			const bool bOn = bTraffic && CarShow[Slot];
			Scratch[I] = bOn ? Of(Slot) : Hidden;
			Shown[I] = bOn ? 1 : 0;
			if (bRoll && bOn && FVector::DistSquared(CarPos[Slot], View) < Roll2)
			{
				Comp->SetCustomDataValue(I, PaintFloats, FMath::Fmod(CarSpin[Slot], Wrap), false);
			}
		}
		Comp->BatchUpdateInstancesTransforms(0, Scratch, false, bRebuildRenderState, false);
		Sent += Hi;
	}
	InstancesSent = Sent;
	++CarFrame;
	CarDrawMs = 0.95 * CarDrawMs + 0.05 * (FPlatformTime::Seconds() - T0) * 1000.0;
}

void ACityGenLife::SetTraffic(bool bOn)
{
	bTraffic = bOn;
	if (bBuilt && IsTraffic())
	{
		if (!bOn)
		{
			FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
			for (int32 Slot = 0; Slot < CarEnts.Num(); ++Slot)
			{
				FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
				if (C.Active)
				{
					FreeCar(Slot, C);
				}
			}
			for (int32 J = 0; J < DriveLaneCount; ++J)
			{
				InRegion[WalkLaneCount + J] = 0;
			}
			UpdateCarInstances();
		}
		else
		{
			UpdateTraffic(0.f, true);
		}
	}
	for (UInstancedStaticMeshComponent* C : CarParts)
	{
		if (C)
		{
			C->SetVisibility(bOn && bEnabled);
		}
	}
}

void ACityGenLife::SetTrafficScale(const float InScale)
{
	TrafficScale = FMath::Max(0.f, InScale);
	if (bBuilt && IsTraffic() && bTraffic)
	{
		UpdateTraffic(0.f, true);
	}
}

FString ACityGenLife::TrafficStatus() const
{
	if (!IsTraffic())
	{
		return TEXT(",\"traffic\":null");
	}
	return FString::Printf(TEXT(",\"traffic\":{\"on\":%s,\"hour\":%d,\"pool\":%d,\"live_m\":%.0f,\"live_lanes\":%d,\"want\":%.1f,\"scale\":%.3f,\"traffic_scale\":%.2f,\"active\":%d,\"moving\":%d,\"leader\":%d,\"red\":%d,\"person\":%d,\"player\":%d,\"junction\":%d,\"box\":%d,\"spawned\":%d,\"refilled\":%d,\"left_edge\":%d,\"lost\":%d,\"forced\":%d,\"stuck\":%d,\"conflicts\":%d,\"signal_lanes\":%d,\"traffic_ms\":%.3f,\"traffic_ms_max\":%.3f,\"draw_ms\":%.3f,\"live_ms\":%.3f,\"live_ms_max\":%.3f,\"instances_sent\":%d,\"components\":%d,\"show\":\"%s\"}"),
		bTraffic ? TEXT("true") : TEXT("false"), Hour, CarEnts.Num(), TrafficLiveM, TrafficLiveLanes, TrafficWantLive, TrafficLiveScale, TrafficScale,
		CarsActive, CarsMovingNow, CarsWhyNow[CgWhy::Leader], CarsWhyNow[CgWhy::Red], CarsWhyNow[CgWhy::Person], CarsWhyNow[CgWhy::Player],
		CarsWhyNow[CgWhy::Junction], CarsWhyNow[CgWhy::Box], CarsSpawned, CarsRefilled, CarsLeftTotal, CarsLost, CarsForcedTotal, CarsStuckTotal,
		ConflictsG.Num() / 2, DriveSignal.Num() ? DriveSignal.FilterByPredicate([](int32 V) { return V >= 0; }).Num() : 0,
		TrafficMs, TrafficMsMax, CarDrawMs, LiveMs, LiveMsMax, InstancesSent, CarParts.Num(), *LastShow);
}

void ACityGenLife::SetJaywalk(const float AtSafe, const float AtDanger)
{
	Jaywalk = FVector2D(FMath::Clamp(AtSafe, 0.f, 1.f), FMath::Clamp(AtDanger, 0.f, 1.f));
	Frame.Jaywalk = Jaywalk;
}

// --- the check's shots ---------------------------------------------------------------------------

bool ACityGenLife::FrameCar(const FVector& At, const FVector& Toward, const float Back, const float Up, const float Side)
{
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	APawn* Cam = PC ? PC->GetPawn() : nullptr;
	if (!Cam)
	{
		return false;
	}
	const FVector Fwd = FVector(Toward.X, Toward.Y, 0.0).GetSafeNormal();
	const FVector Right = FVector::CrossProduct(FVector::UpVector, Fwd).GetSafeNormal();
	const FVector Eye = At - Fwd * Back + Right * Side + FVector(0.0, 0.0, Up);
	Cam->SetActorLocation(Eye, false, nullptr, ETeleportType::TeleportPhysics);
	PC->SetControlRotation((At + FVector(0.0, 0.0, 80.0) - Eye).Rotation());
	return true;
}

bool ACityGenLife::ShowTraffic(const FString& What)
{
	if (!bBuilt || !IsTraffic())
	{
		return false;
	}
	FVector View;
	if (!ViewPoint(View))
	{
		View = LastTrafficView;
	}
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	int32 Best = INDEX_NONE;
	double Score = -1.0e18;
	int32 BestQueue = 0;
	for (int32 Slot = 0; Slot < CarEnts.Num(); ++Slot)
	{
		const FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
		if (!C.Active || !CarShow[Slot])
		{
			continue;
		}
		const double D = FVector::Dist(C.Pos, View);
		bool bWant = false;
		int32 Queue = 0;
		if (What == TEXT("red"))
		{
			bWant = C.Why == CgWhy::Red && C.Speed < 50.f;
			if (bWant)
			{
				// (the cars stopped behind it on its lane within 60 m)
				for (int32 O = 0; O < CarEnts.Num(); ++O)
				{
					const FCgLifeCar& B = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[O]);
					Queue += (O != Slot && B.Active && B.Lane == C.Lane && B.Dist < C.Dist && C.Dist - B.Dist < 6000.f && B.Speed < 150.f) ? 1 : 0;
				}
			}
		}
		else if (What == TEXT("person"))
		{
			bWant = C.Why == CgWhy::Person && C.Speed < 150.f;
		}
		else if (What == TEXT("player"))
		{
			bWant = C.Why == CgWhy::Player && C.Speed < 150.f;
		}
		else
		{
			bWant = C.Speed > 500.f;
		}
		if (!bWant || D > 100.0 * TrafficLiveM)
		{
			continue;
		}
		const double Sc = 1.0e6 * FMath::Min(Queue, 4) - D;
		if (Sc > Score)
		{
			Score = Sc;
			Best = Slot;
			BestQueue = Queue;
		}
	}
	if (Best == INDEX_NONE)
	{
		LastShow = What + TEXT(":none");
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":false}"), *What);
		return false;
	}
	const FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Best]);
	const FVector Fwd(FMath::Cos(FMath::DegreesToRadians(C.Yaw)), FMath::Sin(FMath::DegreesToRadians(C.Yaw)), 0.0);
	bool bOk;
	if (What == TEXT("red"))
	{
		// (from behind the queue and above, the light's junction ahead)
		bOk = FrameCar(C.Pos + Fwd * 400.0, Fwd, 1800.0 + 450.0 * FMath::Min(BestQueue, 4), 700.0, 650.0);
	}
	else if (What == TEXT("person") || What == TEXT("player"))
	{
		// (from ahead and to the side, looking back at the car and who it stops for)
		bOk = FrameCar(C.Pos + Fwd * 350.0, -Fwd, 1100.0, 550.0, 450.0);
	}
	else
	{
		bOk = FrameCar(C.Pos, Fwd, 900.0, 300.0, 700.0);
	}
	const FVector P = C.Pos / 100.0;
	LastShow = FString::Printf(TEXT("%s:%d"), *What, Best);
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":true,\"car\":%d,\"at\":[%.1f,%.1f,%.1f],\"speed\":%.2f,\"queue\":%d,\"why\":%d}"),
		*What, Best, P.X, -P.Y, P.Z, C.Speed / 100.0, BestQueue, (int32)C.Why);
	return bOk;
}

bool ACityGenLife::BlockPlayer()
{
	if (!bBuilt || !IsTraffic())
	{
		return false;
	}
	APawn* Walker = nullptr;
	for (TActorIterator<APawn> It(GetWorld()); It; ++It)
	{
		if (It->GetClass()->GetName().Contains(TEXT("Walker")))
		{
			Walker = *It;
			break;
		}
	}
	FVector View;
	if (!Walker || !ViewPoint(View))
	{
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_BLOCK {\"found\":false,\"why\":\"no walker or view\"}"));
		return false;
	}
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	const FZoneGraphStorage& S = *Frame.Storage;
	const float Ahead = 4500.f;
	int32 Best = INDEX_NONE;
	double BestD = 1.0e18;
	for (int32 Slot = 0; Slot < CarEnts.Num(); ++Slot)
	{
		const FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
		if (!C.Active || C.Speed < 300.f || DriveIsConnector[C.Lane] || C.Why != CgWhy::Free)
		{
			continue;
		}
		if (Lengths[C.Lane] - C.Dist - 0.5f * C.Len < Ahead + 1000.f)
		{
			continue;
		}
		const double D = FVector::Dist(C.Pos, View);
		if (D < BestD && D < 15000.0)
		{
			BestD = D;
			Best = Slot;
		}
	}
	if (Best == INDEX_NONE)
	{
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_BLOCK {\"found\":false,\"why\":\"no moving car with room ahead\"}"));
		return false;
	}
	const FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Best]);
	FZoneGraphLaneLocation Loc;
	UE::ZoneGraph::Query::CalculateLocationAlongLane(S, C.Lane, C.Dist + 0.5f * C.Len + Ahead, Loc);
	const FVector At = Loc.Position + FVector(0.0, 0.0, 100.0 + C.ZOff);
	Walker->SetActorLocation(At, false, nullptr, ETeleportType::TeleportPhysics);
	Walker->SetActorRotation(FRotator(0.f, C.Yaw + 90.f, 0.f));
	const FVector P = At / 100.0;
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_BLOCK {\"found\":true,\"car\":%d,\"walker\":[%.1f,%.1f,%.1f],\"speed\":%.2f}"),
		Best, P.X, -P.Y, P.Z, C.Speed / 100.0);
	return true;
}

// --- the processor: every live car's step ------------------------------------------------------

void UCityGenLifeDriveProcessor::ExecuteTraffic(FMassExecutionContext& Context)
{
	TRACE_CPUPROFILER_EVENT_SCOPE(CityGenLife_ExecuteTraffic);
	FCgLifeFrame& F = *Frame;
	const double T0 = FPlatformTime::Seconds();
	const FZoneGraphStorage& S = *F.Storage;
	const float Dt0 = FMath::Min(0.1f, Context.GetDeltaTimeSeconds());
	const TArray<float>& Len = *F.Lengths;
	const TArray<uint8>& In = *F.InRegion;
	const TArray<uint8>& Main = *F.DriveMain;
	const TArray<uint8>& Conn = *F.IsConnector;
	const TArray<int32>& Sig = *F.DriveSignal;
	const TArray<float>& Back = *F.DriveStopBack;
	const TArray<float>& Win = *F.DriveWindows;
	const TArray<int32>& CS = *F.ConflictStarts;
	const TArray<int32>& CL = *F.Conflicts;
	const int32 NL = S.Lanes.Num();
	for (int32 K = 0; K < 7; ++K)
	{
		F.CarsWhy[K] = 0;
	}
	F.CarsMoving = F.CarsActive = F.CarsLeft = F.CarsForced = F.CarsStuck = 0;

	// (1) the live cars sorted by lane and distance; who drives, holds or claims each connector
	if (LaneFirst.Num() != NL)
	{
		LaneFirst.Init(INDEX_NONE, NL);
		Occ.Init(0, NL);
		ClaimBy.Init(INDEX_NONE, NL);
		ClaimWait.Init(0.f, NL);
		Touched.Reset();
	}
	for (const int32 L : Touched)
	{
		LaneFirst[L] = INDEX_NONE;
		Occ[L] = 0;
		ClaimBy[L] = INDEX_NONE;
		ClaimWait[L] = 0.f;
	}
	Touched.Reset();
	Sorted.Reset();
	Query.ForEachEntityChunk(Context, [&](FMassExecutionContext& Ctx)
	{
		const TArrayView<FCgLifeCar> List = Ctx.GetMutableFragmentView<FCgLifeCar>();
		for (int32 I = 0; I < Ctx.GetNumEntities(); ++I)
		{
			if (List[I].Active && S.Lanes.IsValidIndex(List[I].Lane))
			{
				Sorted.Add(&List[I]);
			}
		}
	});
	Algo::Sort(Sorted, [](const FCgLifeCar* A, const FCgLifeCar* B)
	{
		return A->Lane < B->Lane || (A->Lane == B->Lane && (A->Dist < B->Dist || (A->Dist == B->Dist && A->Index < B->Index)));
	});
	auto Touch = [&](const int32 L) { Touched.Add(L); };
	for (int32 I = 0; I < Sorted.Num(); ++I)
	{
		FCgLifeCar& C = *Sorted[I];
		C.Rank = I;
		if (LaneFirst[C.Lane] == INDEX_NONE)
		{
			LaneFirst[C.Lane] = I;
			Touch(C.Lane);
		}
		if (Conn[C.Lane])
		{
			++Occ[C.Lane];
			Touch(C.Lane);
		}
		if (C.Reserved != INDEX_NONE && C.Reserved != C.Lane && Occ.IsValidIndex(C.Reserved))
		{
			++Occ[C.Reserved];
			Touch(C.Reserved);
		}
		// (LG8: a car waiting for room past the junction claims nothing: its claim would hold the
		// crossing cars that make the room)
		if (C.Wait > F.StarveS && C.Why != CgWhy::Box && C.Next != INDEX_NONE && Conn[C.Next] && C.Reserved != C.Next)
		{
			if (ClaimBy[C.Next] == INDEX_NONE || ClaimWait[C.Next] < C.Wait)
			{
				ClaimBy[C.Next] = C.Index;
				ClaimWait[C.Next] = C.Wait;
				Touch(C.Next);
			}
		}
	}

	// (2) the people near the view (and the player), in cells, where they are and a little on
	PedPos.Reset();
	PedAhead.Reset();
	TArray<FCellItem> Items;
	const double Look2 = FMath::Square((double)F.YieldCm + F.LookMaxCm + 2000.0);
	if (F.WalkPos && F.WalkState)
	{
		const TArray<FVector>& WP = *F.WalkPos;
		const TArray<uint8>& WS = *F.WalkState;
		for (int32 K = 0; K < WP.Num() && K < WS.Num(); ++K)
		{
			if ((WS[K] != CgShow::Moving && WS[K] != CgShow::Still) || WP[K].IsZero() || FVector::DistSquared(WP[K], F.View) > Look2)
			{
				continue;
			}
			FVector Ahead = WP[K];
			if (WS[K] == CgShow::Moving && F.WalkYaw && F.WalkYaw->IsValidIndex(K))
			{
				const float Y = FMath::DegreesToRadians((*F.WalkYaw)[K]);
				Ahead += FVector(FMath::Cos(Y), FMath::Sin(Y), 0.0) * (130.0 * F.PredictS);
			}
			PedPos.Add(WP[K]);
			PedAhead.Add(Ahead);
		}
	}
	const int32 NumPeople = PedPos.Num();
	for (const FVector& P : F.Players)
	{
		// (a pawn's middle is about 90 cm over its feet)
		PedPos.Add(P - FVector(0.0, 0.0, 90.0));
		PedAhead.Add(P - FVector(0.0, 0.0, 90.0));
	}
	for (int32 K = 0; K < PedPos.Num(); ++K)
	{
		const int64 A = CellOf(PedPos[K].X, PedPos[K].Y);
		const int64 B = CellOf(PedAhead[K].X, PedAhead[K].Y);
		Items.Add({A, K});
		if (B != A)
		{
			Items.Add({B, K});
		}
	}
	Algo::Sort(Items, [](const FCellItem& A, const FCellItem& B) { return A.Cell < B.Cell || (A.Cell == B.Cell && A.Ped < B.Ped); });
	CellStart.Reset();
	for (int32 K = 0; K < Items.Num(); ++K)
	{
		if (K == 0 || Items[K].Cell != Items[K - 1].Cell)
		{
			CellStart.Add(Items[K].Cell, K);
		}
	}
	const double Yield2 = FMath::Square((double)F.YieldCm);
	const float SqrtAB = FMath::Sqrt(F.Accel * F.Brake);

	// (3) each car's step
	for (int32 I = 0; I < Sorted.Num(); ++I)
	{
		FCgLifeCar& C = *Sorted[I];
		const double DView2 = FVector::DistSquared(C.Pos, F.View);
		// (LG8's performance pass: past 250 m every second frame, past 550 m every fourth)
		const int32 Every = DView2 > FMath::Square((double)FarterCm) ? 4 : (DView2 > FMath::Square((double)FarCm) ? 2 : 1);
		C.Pending += Dt0;
		if (Every > 1 && ((F.FrameNo + C.Index) % Every) != 0)
		{
			++F.CarsActive;
			F.CarsMoving += C.Speed > 50.f ? 1 : 0;
			continue;
		}
		const float Dt = FMath::Min(C.Pending, 0.4f);
		C.Pending = 0.f;
		const float L = Len[C.Lane];
		const float V = C.Speed;
		// (LG8: slower in rain and fog, by the weather's share)
		const float V0 = FMath::Max(150.f, F.SpeedMul * C.Share * SpeedOn(S, F.PointVmax, C.Lane, C.Dist, FMath::Max(400.f, V * 0.6f)));
		const float Front = C.Dist + 0.5f * C.Len;
		const float ToEnd = L - Front;
		float Term = 0.f;           // the strongest interaction (s* / s)^2
		uint8 Why = CgWhy::Free;
		bool bHalt = false;
		auto Consider = [&](const float Gap, const float VLead, const uint8 Reason)
		{
			if (Gap <= 5.f)
			{
				bHalt = true;
				if (Term < 1.0e6f)
				{
					Term = 1.0e6f;
					Why = Reason;
				}
				return;
			}
			const float SStar = F.GapCm + FMath::Max(0.f, V * (F.Headway + F.HeadwayAdd) + V * (V - VLead) / (2.f * SqrtAB));
			const float T = FMath::Square(SStar / Gap);
			if (T > Term)
			{
				Term = T;
				Why = Reason;
			}
		};
		// the car in front: on its lane, the next, the one after
		float LeadV = 1.0e9f, LeadGap = 1.0e9f;
		auto Lead = [&](const float Gap, const FCgLifeCar& O)
		{
			LeadV = O.Speed;
			LeadGap = Gap;
			Consider(Gap, O.Speed, CgWhy::Leader);
		};
		if (I + 1 < Sorted.Num() && Sorted[I + 1]->Lane == C.Lane)
		{
			const FCgLifeCar& O = *Sorted[I + 1];
			Lead(O.Dist - C.Dist - 0.5f * (O.Len + C.Len), O);
		}
		else if (C.Next != INDEX_NONE)
		{
			const int32 A = LaneFirst[C.Next];
			if (A != INDEX_NONE)
			{
				const FCgLifeCar& O = *Sorted[A];
				Lead(L - C.Dist + O.Dist - 0.5f * (O.Len + C.Len), O);
			}
			else if (C.Next2 != INDEX_NONE && LaneFirst[C.Next2] != INDEX_NONE)
			{
				const FCgLifeCar& O = *Sorted[LaneFirst[C.Next2]];
				Lead(L - C.Dist + Len[C.Next] + O.Dist - 0.5f * (O.Len + C.Len), O);
			}
		}
		// its signal: stopped short of the crosswalk on red, and on amber where it can
		bool bAtLight = false;
		const int32 Sg = Sig.IsValidIndex(C.Lane) ? Sig[C.Lane] : INDEX_NONE;
		const float StopAt = Sg != INDEX_NONE ? L - Back[C.Lane] : L - 50.f;
		const float DStop = StopAt - Front;
		if (Sg != INDEX_NONE && DStop > -60.f)
		{
			const int32 St = SignalState(Win, Sg, F.Time);
			if (St == 2 || (St == 1 && DStop > 0.f && V * V / (2.f * DStop) <= F.AmberBrake))
			{
				bAtLight = true;
				C.Reserved = INDEX_NONE;
				Consider(FMath::Max(DStop, 0.f) + F.GapCm - 50.f, 0.f, CgWhy::Red);
			}
		}
		// the junction ahead: its connector held only while no connector crossing it is driven
		// or claimed by a car that waited longer, and with room past it
		// (not while the car in front holds it back: it would hold the junction from a queue;
		// it stops at the junction's edge until it holds its connector)
		const bool bQueued = LeadV < 100.f && LeadGap < 1500.f;
		if (!bAtLight && C.Next != INDEX_NONE && Conn[C.Next] && C.Reserved != C.Next && !Conn[C.Lane])
		{
			const float Reach = FMath::Max(1000.f, V * V / (2.f * F.Brake) + 600.f);
			if (ToEnd < Reach && bQueued)
			{
				Consider(FMath::Max(DStop, 0.f) + F.GapCm - 50.f, 0.f, CgWhy::Leader);
			}
			else if (ToEnd < Reach)
			{
				bool bFree = true;
				uint8 Reason = CgWhy::Junction;
				for (int32 K = CS[C.Next]; K < CS[C.Next + 1] && bFree; ++K)
				{
					const int32 X = CL[K];
					if (Occ[X] > 0 || (ClaimBy[X] != INDEX_NONE && ClaimBy[X] != C.Index && ClaimWait[X] > C.Wait))
					{
						bFree = false;
					}
				}
				// (room past the junction: the lane it leads to has the car's length and gap
				// clear at its start, counting the cars already on the connector; LG8: on every
				// exit, not only the long ones: an exit lane shorter than the car and its gap (Old
				// Town's 5.8 m lanes between two junctions of a cluster) has room only while it is
				// empty and the lanes past it start clear by what the car would stick out of it, so
				// no car waits inside a junction behind one waiting at the next, the gridlock LG5's
				// cars met there)
				const int32 Exit = C.Next2;
				if (bFree && Exit != INDEX_NONE && !Conn[Exit])
				{
					const float Need = C.Len + F.GapCm;
					float Room = LaneFirst[Exit] != INDEX_NONE ? Sorted[LaneFirst[Exit]]->Dist - 0.5f * Sorted[LaneFirst[Exit]]->Len : Len[Exit];
					if (LaneFirst[C.Next] != INDEX_NONE)
					{
						for (int32 K = LaneFirst[C.Next]; K < Sorted.Num() && Sorted[K]->Lane == C.Next; ++K)
						{
							Room -= Sorted[K]->Len + F.GapCm;
						}
					}
					bool bRoom = Room >= FMath::Min(Need, Len[Exit] - 30.f);
					if (bRoom && Len[Exit] < Need)
					{
						// (a short exit: empty, and the lanes after it clear at their starts)
						bRoom = LaneFirst[Exit] == INDEX_NONE;
						const FZoneLaneData& XL = S.Lanes[Exit];
						for (int32 Q = XL.LinksBegin; Q < XL.LinksEnd && bRoom; ++Q)
						{
							const FZoneLaneLinkData& Lk = S.LaneLinks[Q];
							const int32 To = Lk.DestLaneIndex;
							if (Lk.Type != EZoneLaneLinkType::Outgoing || !LaneFirst.IsValidIndex(To) || LaneFirst[To] == INDEX_NONE)
							{
								continue;
							}
							const FCgLifeCar& O = *Sorted[LaneFirst[To]];
							bRoom = O.Dist - 0.5f * O.Len >= Need - Len[Exit];
						}
					}
					if (!bRoom)
					{
						bFree = false;
						Reason = CgWhy::Box;
					}
				}
				// (forced after ForceS of waiting for a crossing connector; never into a full box:
				// that only blocks the junction for the others)
				if (!bFree && C.Wait > F.ForceS && Reason != CgWhy::Box)
				{
					bFree = true;
					++F.CarsForced;
				}
				if (bFree)
				{
					C.Reserved = C.Next;
					++Occ[C.Next];
					Touch(C.Next);
				}
				else
				{
					Consider(FMath::Max(DStop, 0.f) + F.GapCm - 50.f, 0.f, Reason);
				}
			}
		}
		// anyone in its way: the crowd's people and the player on its line ahead, where they
		// are and where they will be in PredictS (cars near the view only)
		// (near the view, or near a pawn: the player in the road is seen however far the camera)
		bool bNearPawn = false;
		for (const FVector& P : F.Players)
		{
			bNearPawn |= FVector::DistSquared(C.Pos, P) < FMath::Square((double)F.LookMaxCm + 2000.0);
		}
		// (looked for every second frame, and only up to the car in front or a red light's stop
		// line: nobody past them is in its way; between looks, the last one carried on)
		float Look = FMath::Clamp(V * F.LookS + V * V / (2.f * F.Brake), F.LookMinCm, F.LookMaxCm);
		if (LeadGap < 1.0e8f)
		{
			Look = FMath::Min(Look, LeadGap + 100.f);
		}
		if (bAtLight)
		{
			Look = FMath::Min(Look, FMath::Max(DStop, 0.f) + 100.f);
		}
		const bool bLookNow = bNearPawn || ((F.FrameNo + C.Index) & 1) == 0;
		if ((DView2 < Yield2 || bNearPawn) && PedPos.Num() && !bLookNow)
		{
			if (C.PedHit < 1.0e8f)
			{
				C.PedHit -= V * Dt;
				if (C.PedPlayer || C.Wait < F.ForceS)
				{
					Consider(C.PedHit + F.GapCm - F.MarginCm, 0.f, C.PedPlayer ? CgWhy::Player : CgWhy::Person);
				}
			}
		}
		else if ((DView2 < Yield2 || bNearPawn) && PedPos.Num() && Look > 150.f)
		{
			FVector Pts[48];
			float Along[48];
			int32 Np = 0;
			FZoneGraphLaneLocation Loc;
			UE::ZoneGraph::Query::CalculateLocationAlongLane(S, C.Lane, FMath::Min(Front, L), Loc);
			Pts[Np] = Loc.Position;
			Along[Np++] = 0.f;
			int32 Lane = C.Lane;
			float Base = -Front;             // a lane's start, measured from the car's front
			for (int32 Hop = 0; Hop < 3 && Lane != INDEX_NONE && Np < 48; ++Hop)
			{
				const FZoneLaneData& LD = S.Lanes[Lane];
				for (int32 P = LD.PointsBegin; P < LD.PointsEnd && Np < 48; ++P)
				{
					const float A = Base + S.LanePointProgressions[P];
					if (A <= Along[Np - 1] + 1.f)
					{
						continue;
					}
					Pts[Np] = S.LanePoints[P];
					Along[Np++] = A;
					if (A > Look)
					{
						break;
					}
				}
				if (Along[Np - 1] > Look)
				{
					break;
				}
				Base += Len[Lane];
				Lane = Hop == 0 ? C.Next : (Hop == 1 ? C.Next2 : INDEX_NONE);
			}
			FBox2D Box(ForceInit);
			for (int32 K = 0; K < Np; ++K)
			{
				Box += FVector2D(Pts[K].X, Pts[K].Y);
			}
			Box = Box.ExpandBy(F.LatCm);
			float Hit = 1.0e9f;
			bool bPlayerHit = false;
			const int32 X0 = FMath::FloorToInt(Box.Min.X / CellCm), X1 = FMath::FloorToInt(Box.Max.X / CellCm);
			const int32 Y0 = FMath::FloorToInt(Box.Min.Y / CellCm), Y1 = FMath::FloorToInt(Box.Max.Y / CellCm);
			for (int32 Cx = X0; Cx <= X1 && Np >= 2; ++Cx)
			{
				for (int32 Cy = Y0; Cy <= Y1; ++Cy)
				{
					const int64 Key = (int64(Cx) << 32) ^ (int64)(uint32)Cy;
					const int32* Start = CellStart.Find(Key);
					if (!Start)
					{
						continue;
					}
					for (int32 K = *Start; K < Items.Num() && Items[K].Cell == Key; ++K)
					{
						const int32 Pd = Items[K].Ped;
						for (const FVector& Q : {PedPos[Pd], PedAhead[Pd]})
						{
							if (!Box.IsInside(FVector2D(Q.X, Q.Y)))
							{
								continue;
							}
							for (int32 Sgi = 0; Sgi + 1 < Np; ++Sgi)
							{
								const FVector2D A2(Pts[Sgi].X, Pts[Sgi].Y), B2(Pts[Sgi + 1].X, Pts[Sgi + 1].Y);
								const FVector2D Ab = B2 - A2;
								const double L2 = Ab.SizeSquared();
								const double T = L2 > 1.0 ? FMath::Clamp(FVector2D::DotProduct(FVector2D(Q.X, Q.Y) - A2, Ab) / L2, 0.0, 1.0) : 0.0;
								const FVector2D Near = A2 + Ab * T;
								if (FVector2D::DistSquared(Near, FVector2D(Q.X, Q.Y)) > FMath::Square((double)F.LatCm))
								{
									continue;
								}
								const double Z = FMath::Lerp(Pts[Sgi].Z, Pts[Sgi + 1].Z, T);
								if (FMath::Abs(Q.Z - Z) > 250.0)
								{
									continue;
								}
								const float At = FMath::Lerp(Along[Sgi], Along[Sgi + 1], (float)T);
								if (At < Hit)
								{
									Hit = At;
									bPlayerHit = Pd >= NumPeople;
								}
								break;
							}
						}
					}
				}
			}
			C.PedHit = Hit;
			C.PedPlayer = bPlayerHit ? 1 : 0;
			if (Hit < 1.0e8f)
			{
				// (a car stopped long for someone standing still in its way, past ForceS, goes on
				// slowly; never for the player)
				if (bPlayerHit || C.Wait < F.ForceS)
				{
					Consider(Hit + F.GapCm - F.MarginCm, 0.f, bPlayerHit ? CgWhy::Player : CgWhy::Person);
				}
			}
		}
		else
		{
			C.PedHit = 1.0e9f;
		}
		// the step (the intelligent driver model)
		float Acc = F.Accel * (1.f - FMath::Pow(FMath::Min(V / V0, 3.f), F.Delta)) - F.Accel * FMath::Min(Term, 1.0e4f);
		Acc = FMath::Clamp(Acc, -F.BrakeMax, F.Accel);
		float NewV = bHalt ? 0.f : FMath::Max(0.f, V + Acc * Dt);
		C.Dist += 0.5f * (V + NewV) * Dt;
		C.Speed = NewV;
		C.Why = (Term > 0.25f || bHalt) ? Why : CgWhy::Free;
		// (the time it waits at a junction or for someone standing in its way: a red light's
		// wait is not counted, so a car never claims or forces a junction for it)
		if (NewV < 30.f && (C.Why == CgWhy::Junction || C.Why == CgWhy::Box || C.Why == CgWhy::Person))
		{
			C.Wait += Dt;
		}
		else if (C.Why == CgWhy::Red || NewV > 200.f)
		{
			C.Wait = 0.f;
		}
		C.Spin = FMath::Fmod(C.Spin + 0.5f * (V + NewV) * Dt, 1.0e6f);
		// onto its next lane at its end; off the live region, it leaves
		bool bGone = false;
		// (LG8: standing still too long where nobody sees it (a queue held by a jam), it leaves:
		// its lane is refilled as any)
		C.Stuck = NewV < 30.f && C.Why != CgWhy::Red ? C.Stuck + Dt : 0.f;
		if (C.Stuck > F.StuckS && DView2 > FMath::Square((double)F.StuckFarCm))
		{
			bGone = true;
			++F.CarsStuck;
		}
		for (int32 Guard = 0; Guard < 4 && C.Dist > Len[C.Lane]; ++Guard)
		{
			const float Over = FMath::Min(C.Dist - Len[C.Lane], 300.f);
			const int32 To = C.Next;
			if (To == INDEX_NONE || !In.IsValidIndex(To) || !In[To] || !Main[To])
			{
				bGone = true;
				break;
			}
			if (C.Reserved == To)
			{
				C.Reserved = INDEX_NONE;
			}
			C.Lane = To;
			C.Dist = Over;
			C.Next = C.Next2 != INDEX_NONE ? C.Next2 : PickMain(S, Main, To, C.Seed);
			C.Next2 = C.Next != INDEX_NONE ? PickMain(S, Main, C.Next, C.Seed) : INDEX_NONE;
			C.Wait = 0.f;
		}
		if (bGone)
		{
			C.Active = 0;
			C.Reserved = INDEX_NONE;
			if (F.CarFreed)
			{
				F.CarFreed->Add(C.Index);
			}
			++F.CarsLeft;
			continue;
		}
		C.Dist = FMath::Clamp(C.Dist, 0.f, Len[C.Lane]);
		FZoneGraphLaneLocation Loc;
		if (!UE::ZoneGraph::Query::CalculateLocationAlongLane(S, C.Lane, C.Dist, Loc))
		{
			continue;
		}
		C.Pos = Loc.Position + FVector(0.f, 0.f, C.ZOff);
		const FVector Hd = Loc.Tangent.IsNearlyZero() ? Loc.Direction : Loc.Tangent;
		C.Yaw = FMath::RadiansToDegrees(FMath::Atan2(Hd.Y, Hd.X));
		if (F.CarPos->IsValidIndex(C.Index))
		{
			(*F.CarPos)[C.Index] = C.Pos;
			(*F.CarYaw)[C.Index] = C.Yaw;
			(*F.CarShow)[C.Index] = 1;
			(*F.CarSpin)[C.Index] = C.Spin;
		}
		++F.CarsActive;
		F.CarsMoving += C.Speed > 50.f ? 1 : 0;
		++F.CarsWhy[FMath::Min<int32>(C.Why, 6)];
	}
	F.TrafficMs = (FPlatformTime::Seconds() - T0) * 1000.0;
}
