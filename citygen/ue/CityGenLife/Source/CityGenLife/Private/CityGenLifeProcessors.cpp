// lifegen's Mass processors (LG0): see CityGenLifeProcessors.h.

#include "CityGenLifeProcessors.h"
#include "CityGenLifeTypes.h"
#include "MassExecutionContext.h"
#include "ZoneGraphQuery.h"
#include "ZoneGraphTypes.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(CityGenLifeProcessors)

namespace CgLife
{
	uint32 Next(uint32& Seed)
	{
		Seed = Seed * 1664525u + 1013904223u;
		return Seed >> 8;
	}

	/** One of a lane's links of `Type`, at random, not `Avoid` unless it is the only one;
	 *  INDEX_NONE without one. */
	int32 PickLink(const FZoneGraphStorage& S, const int32 Lane, const EZoneLaneLinkType Type,
	               const int32 Avoid, uint32& Seed)
	{
		const FZoneLaneData& L = S.Lanes[Lane];
		int32 Cands[24];
		int32 N = 0;
		bool bAvoided = false;
		for (int32 K = L.LinksBegin; K < L.LinksEnd && N < 24; ++K)
		{
			const FZoneLaneLinkData& Link = S.LaneLinks[K];
			if (Link.Type != Type)
			{
				continue;
			}
			if (Link.DestLaneIndex == Avoid)
			{
				bAvoided = true;
				continue;
			}
			Cands[N++] = Link.DestLaneIndex;
		}
		if (N == 0)
		{
			return bAvoided ? Avoid : INDEX_NONE;
		}
		return Cands[Next(Seed) % N];
	}
}

// --- walking --------------------------------------------------------------------------------

UCityGenLifeWalkProcessor::UCityGenLifeWalkProcessor()
	: Query(*this)
{
	bAutoRegisterWithProcessingPhases = false;
	bRequiresGameThreadExecution = true;
	ExecutionFlags = (uint8)EProcessorExecutionFlags::All;
}

void UCityGenLifeWalkProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	Query.AddRequirement<FCgLifeWalker>(EMassFragmentAccess::ReadWrite);
}

void UCityGenLifeWalkProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	if (!Frame || !Frame->Storage)
	{
		return;
	}
	const FZoneGraphStorage& S = *Frame->Storage;
	const float Dt = FMath::Min(0.1f, Context.GetDeltaTimeSeconds());
	const TArray<float>& Len = *Frame->Lengths;
	const TArray<float>& Wid = *Frame->Widths;
	const TArray<uint8>& In = *Frame->InRegion;
	TArray<FVector>& OutPos = *Frame->WalkPos;
	TArray<float>& OutYaw = *Frame->WalkYaw;

	Query.ForEachEntityChunk(Context, [&](FMassExecutionContext& Ctx)
	{
		const TArrayView<FCgLifeWalker> List = Ctx.GetMutableFragmentView<FCgLifeWalker>();
		for (int32 I = 0; I < Ctx.GetNumEntities(); ++I)
		{
			FCgLifeWalker& W = List[I];
			if (!S.Lanes.IsValidIndex(W.Lane))
			{
				continue;
			}
			W.Dist += W.Dir * W.Speed * Dt;
			for (int32 Guard = 0; Guard < 4; ++Guard)
			{
				const float L = Len[W.Lane];
				if (W.Dist >= 0.f && W.Dist <= L)
				{
					break;
				}
				const bool bEnd = W.Dist > L;
				const float Over = FMath::Min(bEnd ? W.Dist - L : -W.Dist, 200.f);
				const int32 To = CgLife::PickLink(S, W.Lane, bEnd ? EZoneLaneLinkType::Outgoing : EZoneLaneLinkType::Incoming, W.PrevLane, W.Seed);
				if (To == INDEX_NONE || !In.IsValidIndex(To) || !In[To] || To >= Frame->WalkLanes)
				{
					// (a dead end, or the edge of the live region: turn back)
					W.Dir = -W.Dir;
					W.Dist = bEnd ? FMath::Max(0.f, L - Over) : FMath::Min(L, Over);
					W.PrevLane = INDEX_NONE;
					continue;
				}
				const FZoneLaneData& Cur = S.Lanes[W.Lane];
				const FVector Here = S.LanePoints[bEnd ? Cur.PointsEnd - 1 : Cur.PointsBegin];
				const FZoneLaneData& Nx = S.Lanes[To];
				const bool bAtStart = FVector::DistSquared(Here, S.LanePoints[Nx.PointsBegin]) <=
					FVector::DistSquared(Here, S.LanePoints[Nx.PointsEnd - 1]);
				W.PrevLane = W.Lane;
				W.Lane = To;
				W.Dir = bAtStart ? 1.f : -1.f;
				W.Dist = bAtStart ? Over : Len[To] - Over;
			}
			W.Dist = FMath::Clamp(W.Dist, 0.f, Len[W.Lane]);
			FZoneGraphLaneLocation Loc;
			if (!UE::ZoneGraph::Query::CalculateLocationAlongLane(S, W.Lane, W.Dist, Loc))
			{
				continue;
			}
			const FVector Fwd = Loc.Direction * W.Dir;
			const FVector Right = FVector::CrossProduct(Loc.Up, Fwd).GetSafeNormal();
			W.Pos = Loc.Position + Right * (W.Side * 0.5f * Wid[W.Lane]) + FVector(0.f, 0.f, W.ZOff);
			W.Yaw = FMath::RadiansToDegrees(FMath::Atan2(Fwd.Y, Fwd.X));
			if (OutPos.IsValidIndex(W.Instance))
			{
				OutPos[W.Instance] = W.Pos;
				OutYaw[W.Instance] = W.Yaw;
			}
		}
	});
}

// --- driving --------------------------------------------------------------------------------

UCityGenLifeDriveProcessor::UCityGenLifeDriveProcessor()
	: Query(*this)
{
	bAutoRegisterWithProcessingPhases = false;
	bRequiresGameThreadExecution = true;
	ExecutionFlags = (uint8)EProcessorExecutionFlags::All;
}

void UCityGenLifeDriveProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	Query.AddRequirement<FCgLifeCar>(EMassFragmentAccess::ReadWrite);
}

void UCityGenLifeDriveProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	if (!Frame || !Frame->Storage || !Frame->CarStarts || Frame->CarStarts->Num() == 0)
	{
		return;
	}
	const FZoneGraphStorage& S = *Frame->Storage;
	const float Dt = FMath::Min(0.1f, Context.GetDeltaTimeSeconds());
	const TArray<float>& Len = *Frame->Lengths;
	const TArray<uint8>& In = *Frame->InRegion;
	const TArray<int32>& Starts = *Frame->CarStarts;
	const float Gap = Frame->CarGap;

	// (where every car is now: the cars ahead on a lane and on the lane each goes to next)
	TMap<int32, TArray<float>> ByLane;
	Query.ForEachEntityChunk(Context, [&](FMassExecutionContext& Ctx)
	{
		const TConstArrayView<FCgLifeCar> List = Ctx.GetFragmentView<FCgLifeCar>();
		for (int32 I = 0; I < Ctx.GetNumEntities(); ++I)
		{
			ByLane.FindOrAdd(List[I].Lane).Add(List[I].Dist);
		}
	});

	Query.ForEachEntityChunk(Context, [&](FMassExecutionContext& Ctx)
	{
		const TArrayView<FCgLifeCar> List = Ctx.GetMutableFragmentView<FCgLifeCar>();
		for (int32 I = 0; I < Ctx.GetNumEntities(); ++I)
		{
			FCgLifeCar& C = List[I];
			if (!S.Lanes.IsValidIndex(C.Lane))
			{
				continue;
			}
			float Ahead = 1e9f;
			if (const TArray<float>* Ds = ByLane.Find(C.Lane))
			{
				for (const float D : *Ds)
				{
					if (D > C.Dist + 1.f)
					{
						Ahead = FMath::Min(Ahead, D - C.Dist);
					}
				}
			}
			if (C.Next != INDEX_NONE)
			{
				if (const TArray<float>* Ds = ByLane.Find(C.Next))
				{
					for (const float D : *Ds)
					{
						Ahead = FMath::Min(Ahead, Len[C.Lane] - C.Dist + D);
					}
				}
			}
			// (full speed with two gaps clear, stopped at one)
			const float Want = C.Cruise * FMath::Clamp((Ahead - Gap) / Gap, 0.f, 1.f);
			C.Speed = FMath::Max(0.f, C.Speed + FMath::Clamp(Want - C.Speed, -900.f * Dt, 300.f * Dt));
			C.Dist += C.Speed * Dt;
			for (int32 Guard = 0; Guard < 4 && C.Dist > Len[C.Lane]; ++Guard)
			{
				const float Over = FMath::Min(C.Dist - Len[C.Lane], 300.f);
				if (C.Next == INDEX_NONE || !In.IsValidIndex(C.Next) || !In[C.Next])
				{
					// (a dead end or the edge of the live region: the car starts again on a lane
					// of the region, LG5's traffic will leave and enter at the region's edge)
					C.Lane = Starts[CgLife::Next(C.Seed) % Starts.Num()];
					C.Dist = 0.f;
					C.Speed = 0.f;
				}
				else
				{
					C.Lane = C.Next;
					C.Dist = Over;
				}
				C.Next = CgLife::PickLink(S, C.Lane, EZoneLaneLinkType::Outgoing, INDEX_NONE, C.Seed);
			}
			C.Dist = FMath::Clamp(C.Dist, 0.f, Len[C.Lane]);
			FZoneGraphLaneLocation Loc;
			if (!UE::ZoneGraph::Query::CalculateLocationAlongLane(S, C.Lane, C.Dist, Loc))
			{
				continue;
			}
			C.Pos = Loc.Position + FVector(0.f, 0.f, C.ZOff);
			C.Yaw = FMath::RadiansToDegrees(FMath::Atan2(Loc.Direction.Y, Loc.Direction.X));
			if (Frame->CarPos->IsValidIndex(C.Index))
			{
				(*Frame->CarPos)[C.Index] = C.Pos;
				(*Frame->CarYaw)[C.Index] = C.Yaw;
			}
		}
	});
}
